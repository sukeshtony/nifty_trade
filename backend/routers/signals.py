"""Signals API router — current signal and signal history."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict
import json
import logging

from database.connection import get_db
from database.models import Signal
from services.market_state import market_state_manager
from services.market_data_service import market_service
from services.indicator_engine import compute_all_indicators
from services.options_engine import options_engine
from services.strategy_engine import strategy_engine
from services.regime_detector import regime_detector
from services.candle_analyzer import analyze_last_candle
from services.risk_engine import risk_engine
from utils.cache import cache
from utils.helpers import attach_metadata
import time

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/signals", tags=["Signals"])


@router.get("/current")
def get_current_signal(db: Session = Depends(get_db)):
    """
    Generate current trading signal from live data.
    """
    start_time = time.time()
    # ── 1. Market state ───────────────────────────────────────────────────────
    state = market_state_manager.get_state("NIFTY")
    
    source = "LIVE" if state and state.get("current_price") else "CACHE"

    # ── 2. Candle indicators (prefer futures candles — they have volume for VWAP) ──
    candles = cache.get("candles:NIFTY_FUT:ONE_MINUTE")
    if not candles:
        # Try futures candles first (have volume for VWAP/volume spike)
        fut_info = market_service.get_nifty_futures_token()
        if fut_info:
            candles = market_service.get_candle_data(
                "NIFTY_FUT", token=fut_info["token"], exchange="NFO", interval="ONE_MINUTE"
            )
        # Fallback to cash index candles if futures unavailable
        if not candles:
            candles = cache.get("candles:NIFTY:ONE_MINUTE")
        if not candles:
            candles = market_service.get_candle_data("NIFTY", interval="ONE_MINUTE")
    indicators = compute_all_indicators(candles) if candles else {}

    # ── 3. Options analysis ───────────────────────────────────────────────────
    options_data = cache.get("options_analysis:NIFTY")
    if not options_data:
        chain = market_service.get_option_chain("NIFTY", num_strikes=3)
        if chain:
            spot = state.get("current_price", 0) or indicators.get("current_price", 0)
            options_data = options_engine.analyze(chain, spot)
            cache.set("options_analysis:NIFTY", options_data, ttl=30)
        else:
            options_data = {}

    # ── 4. Regime detection ───────────────────────────────────────────────────
    atr          = state.get("atr") or indicators.get("atr")
    regime_info  = regime_detector.detect(candles or [], atr)

    # ── 5. Candle strength ────────────────────────────────────────────────────
    candle_info = analyze_last_candle(candles) if candles else {}

    # ── 6. Strategy decision ──────────────────────────────────────────────────
    signal_result = strategy_engine.generate_signal(
        market_state = state,
        options_data = options_data,
        indicators   = indicators,
        candles      = candles,
        regime_info  = regime_info,
        candle_info  = candle_info,
    )

    # ── 7. Risk plan (BUY_CE / BUY_PE only) ──────────────────────────────────
    final_signal = signal_result.get("final_signal", "NO_TRADE")
    if final_signal in ("BUY_CE", "BUY_PE"):
        # Check session-level guardrails
        allowed, block_reason = risk_engine.validate_trade_allowed()
        if not allowed:
            signal_result["final_signal"] = "NO_TRADE"
            signal_result["why_not_trade"] = f"Risk guardrail: {block_reason}"
            logger.warning("Risk engine blocked trade: %s", block_reason)
        else:
            atm_premium   = _estimate_atm_premium(options_data, final_signal)
            spot_price    = state.get("current_price", 0)
            plan, err     = risk_engine.calculate_trade_plan(
                signal         = final_signal,
                option_premium = atm_premium,
                atr            = atr or 0,
                spot_price     = spot_price,
            )
            if plan:
                signal_result["risk_plan"] = plan
            else:
                # Poor R:R — demote to NO_TRADE
                signal_result["final_signal"] = "NO_TRADE"
                signal_result["why_not_trade"] = f"Risk plan rejected: {err}"
                logger.info("Signal demoted to NO_TRADE — risk plan: %s", err)

    # ── 8. Store signal in DB (throttled) ─────────────────────────────────────
    _maybe_store_signal(db, signal_result)

    # ── Enhance explanation with frontend UI statuses ─────────────────────────
    explanation_dict = signal_result.get("explanation", {})

    _ema = indicators.get("ema", {}) or {}
    ema_9 = state.get("ema_9") or _ema.get("ema_9", 0)
    ema_21 = state.get("ema_21") or _ema.get("ema_21", 0)
    price = state.get("current_price") or indicators.get("current_price", 0)

    if ema_9 and ema_21:
        if price > ema_9 > ema_21:
            ema_status = f"Strong Bullish (Price > {ema_9} > {ema_21})"
        elif ema_9 > ema_21 and price > ema_21:
            ema_status = "Mild Bullish"
        elif price < ema_9 < ema_21:
            ema_status = f"Strong Bearish (Price < {ema_9} < {ema_21})"
        elif ema_9 < ema_21 and price < ema_21:
            ema_status = "Mild Bearish"
        else:
            ema_status = "Neutral / Sideways"
    else:
        ema_status = "N/A"

    candle_ema_9 = _ema.get("ema_9", 0)
    candle_ema_21 = _ema.get("ema_21", 0)
    if candle_ema_9 and candle_ema_21:
        if price > candle_ema_9 > candle_ema_21:
            candle_ema_status = f"Strong Bullish (Price > {candle_ema_9} > {candle_ema_21})"
        elif candle_ema_9 > candle_ema_21 and price > candle_ema_21:
            candle_ema_status = "Mild Bullish"
        elif price < candle_ema_9 < candle_ema_21:
            candle_ema_status = f"Strong Bearish (Price < {candle_ema_9} < {candle_ema_21})"
        elif candle_ema_9 < candle_ema_21 and price < candle_ema_21:
            candle_ema_status = "Mild Bearish"
        else:
            candle_ema_status = "Neutral / Sideways"
    else:
        candle_ema_status = "N/A"

    vwap = state.get("vwap") or indicators.get("vwap", 0)
    if vwap and vwap > 0:
        if price > vwap:
            vwap_status = f"Bullish (Above {vwap})"
        else:
            vwap_status = f"Bearish (Below {vwap})"
    else:
        vwap_status = "N/A (No Volume)"

    pcr = options_data.get("pcr", 0)
    if pcr > 1.1: pcr_status = f"Bullish ({pcr})"
    elif pcr > 0: pcr_status = f"Bearish/Neutral ({pcr})"
    else: pcr_status = "N/A"

    oi_status = options_data.get("dominant_buildup", "N/A").replace("_", " ").title()

    momentum = state.get("momentum") or indicators.get("momentum") or 0
    if momentum > 0: momentum_status = f"Bullish (+{momentum})"
    elif momentum < 0: momentum_status = f"Bearish ({momentum})"
    else: momentum_status = "Neutral (0)"

    sup = indicators.get("support_resistance", {}).get("support")
    res = indicators.get("support_resistance", {}).get("resistance")
    if sup and res:
        sr_status = f"{sup} / {res}"
    else:
        sr_status = "N/A"

    vol_spike = indicators.get("volume", {}).get("spike")
    vol_rel = indicators.get("volume", {}).get("relative_volume")
    if vol_spike:
        volume_status = f"Spike ({vol_rel}x)"
    else:
        volume_status = f"Normal" if vol_rel else "N/A"

    explanation_dict.update({
        "ema_status": ema_status,
        "candle_ema_status": candle_ema_status,
        "vwap_status": vwap_status,
        "pcr_status": pcr_status,
        "oi_status": oi_status,
        "momentum_status": momentum_status,
        "support_resistance": sr_status,
        "volume_status": volume_status
    })

    signal_result["explanation"] = explanation_dict

    # ── Build response ────────────────────────────────────────────────────────
    response_data = {
        # Core signal
        "signal":          signal_result.get("final_signal", "NO_TRADE"),
        "direction":       signal_result.get("direction", "SIDEWAYS"),
        "trade_type":      signal_result.get("trade_type", "INTRADAY"),
        "signal_strength": signal_result.get("signal_strength", 0),
        "setup_quality":   signal_result.get("setup_quality", "INVALID"),

        # Backward-compat alias (equals signal_strength; not a win probability)
        "confidence":      signal_result.get("confidence", 0),

        # Market context
        "market_regime":   signal_result.get("market_regime", "UNKNOWN"),
        "session_window":  signal_result.get("session_window", "CLOSED"),

        # Category scores (for dashboard / logging)
        "category_scores": signal_result.get("explanation", {}).get("category_scores", {}),

        # Explainability
        "explanation":     signal_result.get("explanation", {}),
        "blockers":        signal_result.get("blockers", []),
        "why_not_trade":   signal_result.get("why_not_trade", ""),

        # Risk plan
        "risk_plan":       signal_result.get("risk_plan"),

        # Raw diagnostics
        "candle_quality":  signal_result.get("candle_quality", "UNKNOWN"),
        "regime_info":     regime_info,
        "candle_info":     candle_info,

        # Market snapshot — state from WebSocket, indicators from candles as fallback
        "market_state": {
            "price":    state.get("current_price") or indicators.get("current_price", 0),
            "vwap":     state.get("vwap") or None,
            "ema_9":    state.get("ema_9") or _ema.get("ema_9"),
            "ema_21":   state.get("ema_21") or _ema.get("ema_21"),
            "candle_ema_9":  _ema.get("ema_9"),
            "candle_ema_21": _ema.get("ema_21"),
            "atr":      state.get("atr") or indicators.get("atr"),
            "momentum": state.get("momentum") or indicators.get("momentum") or 0,
        },
        "options_summary": {
            "pcr":          options_data.get("pcr", 0),
            "max_pain":     options_data.get("max_pain"),
            "oi_support":   options_data.get("oi_support"),
            "oi_resistance": options_data.get("oi_resistance"),
        },
    }

    logger.info(f"[DATA_SOURCE] endpoint=/api/signals/current source={source}")
    return attach_metadata(response_data, source, start_time)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _estimate_atm_premium(options_data: Dict, signal: str) -> float:
    """
    Estimate ATM option premium from option chain data.
    Returns the LTP of the closest ATM CE or PE strike.
    Falls back to 0 if not available (risk engine will reject).
    """
    if not options_data:
        return 0.0

    strikes = options_data.get("strikes", [])
    spot    = options_data.get("spot_price", 0)

    if not strikes or not spot:
        return 0.0

    # Find nearest strike to spot
    nearest = min(strikes, key=lambda s: abs(s.get("strike", 0) - spot), default=None)
    if not nearest:
        return 0.0

    if signal == "BUY_CE":
        return float(nearest.get("callLTP", nearest.get("callPrice", 0)) or 0)
    else:
        return float(nearest.get("putLTP", nearest.get("putPrice", 0)) or 0)


def _maybe_store_signal(db: Session, signal_result: Dict):
    """Store signal to DB only when it changes or every 60 seconds."""
    cache_key    = "last_signal_store"
    last         = cache.get(cache_key)
    curr_signal  = signal_result.get("final_signal", "NO_TRADE")

    if last and last.get("signal") == curr_signal:
        return

    try:
        explanation = signal_result.get("explanation", {})
        snapshot = {
            "total_bull":      signal_result.get("total_bull", 0),
            "total_bear":      signal_result.get("total_bear", 0),
            "market_regime":   signal_result.get("market_regime", "UNKNOWN"),
            "session_window":  signal_result.get("session_window", "CLOSED"),
            "candle_quality":  signal_result.get("candle_quality", "UNKNOWN"),
            "category_scores": explanation.get("category_scores", {}),
            "blockers":        signal_result.get("blockers", []),
        }
        sig = Signal(
            signal               = curr_signal,
            trade_type           = signal_result.get("trade_type", "INTRADAY"),
            direction            = signal_result.get("direction", "SIDEWAYS"),
            confidence           = signal_result.get("signal_strength", 0),
            reason               = explanation.get("final_reasoning", ""),
            indicators_snapshot  = json.dumps(snapshot, default=str),
        )
        db.add(sig)
        db.commit()
        cache.set(cache_key, {"signal": curr_signal}, ttl=60)
    except Exception as exc:
        logger.error("Failed to store signal: %s", exc)


@router.get("/history")
def get_signal_history(limit: int = 20, db: Session = Depends(get_db)):
    """Get recent signal history."""
    signals = (
        db.query(Signal)
        .order_by(Signal.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id":         s.id,
            "signal":     s.signal.value  if s.signal    else None,
            "trade_type": s.trade_type.value if s.trade_type else None,
            "direction":  s.direction.value if s.direction  else None,
            "signal_strength": s.confidence,
            "reason":     s.reason,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in signals
    ]
