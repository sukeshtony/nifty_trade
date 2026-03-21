"""Signals API router — current signal and signal history."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict
import json

from database.connection import get_db
from database.models import Signal
from services.market_state import market_state_manager
from services.market_data_service import market_service
from services.indicator_engine import compute_all_indicators
from services.options_engine import options_engine
from services.strategy_engine import strategy_engine
from utils.cache import cache

router = APIRouter(prefix="/api/signals", tags=["Signals"])


@router.get("/current")
def get_current_signal(db: Session = Depends(get_db)):
    """Generate current trading signal from live data.
    All heavy processing done here — frontend just displays result.
    """
    # 1. Get market state (from WebSocket ticks)
    state = market_state_manager.get_state("NIFTY")

    # 2. Get indicators from candle data (cached)
    candles = cache.get("candles:NIFTY:ONE_MINUTE")
    if not candles:
        candles = market_service.get_candle_data("NIFTY", interval="ONE_MINUTE")
    indicators = compute_all_indicators(candles) if candles else {}

    # 3. Get options analysis (cached)
    options_data = cache.get("options_analysis:NIFTY")
    if not options_data:
        chain = market_service.get_option_chain("NIFTY", num_strikes=3)
        if chain:
            spot = state.get("current_price", 0) or indicators.get("current_price", 0)
            options_data = options_engine.analyze(chain, spot)
            cache.set("options_analysis:NIFTY", options_data, ttl=30)
        else:
            options_data = {}

    # 4. Generate signal
    signal_result = strategy_engine.generate_signal(state, options_data, indicators)

    # 5. Store signal in DB (throttled — only if changed or every 60s)
    _maybe_store_signal(db, signal_result)

    return {
        "signal": signal_result["signal"],
        "direction": signal_result["direction"],
        "trade_type": signal_result["trade_type"],
        "confidence": signal_result["confidence"],
        "conditions": signal_result["conditions"],
        "explanation": signal_result["explanation"],
        "market_state": {
            "price": state.get("current_price", 0),
            "vwap": state.get("vwap", 0),
            "ema_9": state.get("ema_9"),
            "ema_21": state.get("ema_21"),
            "momentum": state.get("momentum", 0),
        },
        "options_summary": {
            "pcr": options_data.get("pcr", 0),
            "max_pain": options_data.get("max_pain"),
            "oi_support": options_data.get("oi_support"),
            "oi_resistance": options_data.get("oi_resistance"),
        },
    }


def _maybe_store_signal(db: Session, signal_result: Dict):
    """Store signal to DB only when it changes or every 60 seconds."""
    import time
    cache_key = "last_signal_store"
    last = cache.get(cache_key)

    current_signal = signal_result["signal"]
    if last and last.get("signal") == current_signal:
        return  # Same signal, skip

    try:
        sig = Signal(
            signal=current_signal,
            trade_type=signal_result["trade_type"],
            direction=signal_result["direction"],
            confidence=signal_result["confidence"],
            reason=signal_result["explanation"].get("final_reasoning", ""),
            indicators_snapshot=json.dumps(signal_result.get("conditions", []), default=str),
        )
        db.add(sig)
        db.commit()
        cache.set(cache_key, {"signal": current_signal}, ttl=60)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to store signal: {e}")




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
            "id": s.id,
            "signal": s.signal.value if s.signal else None,
            "trade_type": s.trade_type.value if s.trade_type else None,
            "direction": s.direction.value if s.direction else None,
            "confidence": s.confidence,
            "reason": s.reason,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in signals
    ]
