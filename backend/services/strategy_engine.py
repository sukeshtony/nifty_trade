"""
Strategy Engine — Category-based rule engine for Nifty options signal generation.

Architecture:
  Five independent scoring categories (each capped):
    1. Price Action Bias      (EMA + VWAP)          cap=30
    2. Volume Confirmation    (directional spike)    cap=20
    3. Structure / Breakout   (OI levels + S/R)      cap=25
    4. Options Sentiment      (PCR zones + OI build) cap=20
    5. Regime + Session       (regime alignment)     cap= 5

Decision flow:
  Data quality → Session window → Category scoring → Candle penalty
  → Hard filters → Conflict detection → Decision logic → Output

Signal output: BUY_CE | BUY_PE | NO_TRADE
Confidence is NOT a win probability. Use signal_strength + setup_quality instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
import logging

from utils.helpers import ist_now

logger = logging.getLogger(__name__)

# ── Category caps ──────────────────────────────────────────────────────────────
CAP_PRICE_ACTION    = 30
CAP_VOLUME          = 20
CAP_STRUCTURE       = 25
CAP_OPTIONS         = 20
CAP_REGIME_SESSION  =  5
MAX_SCORE_TOTAL     = 100  # sum of all caps

# ── Decision thresholds ────────────────────────────────────────────────────────
SIGNAL_MIN_SCORE       = 60    # minimum score to trigger a trade
SIGNAL_DOMINANCE_RATIO = 1.5   # winning side must be ≥ 1.5× losing side
SIDEWAYS_EXTRA_THRESH  = 15    # extra points required in SIDEWAYS regime
OPENING_EXTRA_THRESH   = 15    # extra points required during opening window

# ── PCR zone thresholds ────────────────────────────────────────────────────────
PCR_STRONG_BULL = 1.30
PCR_MILD_BULL   = 1.10
PCR_MILD_BEAR   = 0.70
PCR_STRONG_BEAR = 0.60

# ── VWAP distance thresholds ───────────────────────────────────────────────────
VWAP_STRONG_DIST = 0.30   # % away from VWAP for strong signal
VWAP_MILD_DIST   = 0.10   # % away from VWAP for mild signal

# ── Momentum threshold (used only as tie-breaker) ─────────────────────────────
MOMENTUM_CONFIRM_THRESH = 15.0


# ── Session windows ────────────────────────────────────────────────────────────

class SessionWindow(str, Enum):
    OPENING   = "OPENING"    # 09:15–09:30 — high noise, strict filters
    MORNING   = "MORNING"    # 09:30–13:00 — prime time
    AFTERNOON = "AFTERNOON"  # 13:00–14:30 — mixed, slightly tighter
    CLOSING   = "CLOSING"    # 14:30–15:30 — reversal-sensitive
    CLOSED    = "CLOSED"     # outside market hours


def _get_session() -> SessionWindow:
    now = ist_now()
    t   = now.hour * 60 + now.minute
    if   t < 9 * 60 + 15:   return SessionWindow.CLOSED
    elif t < 9 * 60 + 30:   return SessionWindow.OPENING
    elif t < 13 * 60:        return SessionWindow.MORNING
    elif t < 14 * 60 + 30:  return SessionWindow.AFTERNOON
    elif t <= 15 * 60 + 30: return SessionWindow.CLOSING
    else:                    return SessionWindow.CLOSED


_SESSION_CONFIG: Dict[SessionWindow, Dict] = {
    SessionWindow.OPENING:   {"extra_thresh": OPENING_EXTRA_THRESH, "label": "Opening (09:15–09:30)"},
    SessionWindow.MORNING:   {"extra_thresh": 0,                    "label": "Morning  (09:30–13:00)"},
    SessionWindow.AFTERNOON: {"extra_thresh": 5,                    "label": "Afternoon(13:00–14:30)"},
    SessionWindow.CLOSING:   {"extra_thresh": 2,                    "label": "Closing  (14:30–15:30)"},
    SessionWindow.CLOSED:    {"extra_thresh": 999,                  "label": "Closed"},
}


# ── Internal scoring container ─────────────────────────────────────────────────

@dataclass
class _Category:
    name:        str
    bull:        float = 0.0
    bear:        float = 0.0
    cap:         float = 0.0
    reasons:     List[str] = field(default_factory=list)

    def clamp(self):
        self.bull = min(self.bull, self.cap)
        self.bear = min(self.bear, self.cap)


# ── Public output model ────────────────────────────────────────────────────────

@dataclass
class SignalOutput:
    # Core decision
    final_signal:    str   = "NO_TRADE"
    signal_strength: float = 0.0          # 0–100 (raw category sum, winning side)
    setup_quality:   str   = "INVALID"    # STRONG | MODERATE | WEAK | INVALID
    direction:       str   = "SIDEWAYS"   # UP | DOWN | SIDEWAYS

    # Backward compat alias (not a win probability)
    confidence:      float = 0.0          # equals signal_strength; do not interpret as %

    # Market context
    market_regime:   str   = "UNKNOWN"
    regime_strength: int   = 0
    session_window:  str   = "CLOSED"
    trade_type:      str   = "INTRADAY"

    # Category-level scores (for diagnostics / logging)
    price_action_bull:   float = 0.0
    price_action_bear:   float = 0.0
    volume_bull:         float = 0.0
    volume_bear:         float = 0.0
    structure_bull:      float = 0.0
    structure_bear:      float = 0.0
    options_bull:        float = 0.0
    options_bear:        float = 0.0
    regime_session_bull: float = 0.0
    regime_session_bear: float = 0.0
    total_bull:          float = 0.0
    total_bear:          float = 0.0

    # Filters
    hard_filters_passed: bool       = False
    blockers:            List[str]  = field(default_factory=list)
    why_not_trade:       str        = ""

    # Reasons
    bullish_reasons: List[str] = field(default_factory=list)
    bearish_reasons: List[str] = field(default_factory=list)
    neutral_notes:   List[str] = field(default_factory=list)

    # Risk plan (populated only for BUY_CE / BUY_PE signals)
    risk_plan: Optional[Dict] = None

    # Diagnostics
    candle_quality:  str  = "UNKNOWN"
    data_quality_ok: bool = True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Build human-readable explanation for backward compat
        winning_reasons = self.bullish_reasons if self.final_signal == "BUY_CE" else self.bearish_reasons
        d["explanation"] = {
            "market_regime":          self.market_regime,
            "session_window":         self.session_window,
            "setup_quality":          self.setup_quality,
            "signal_strength":        self.signal_strength,
            "category_scores": {
                "price_action":  {"bull": self.price_action_bull, "bear": self.price_action_bear, "cap": CAP_PRICE_ACTION},
                "volume":        {"bull": self.volume_bull,        "bear": self.volume_bear,        "cap": CAP_VOLUME},
                "structure":     {"bull": self.structure_bull,     "bear": self.structure_bear,     "cap": CAP_STRUCTURE},
                "options":       {"bull": self.options_bull,       "bear": self.options_bear,       "cap": CAP_OPTIONS},
                "regime_session":{"bull": self.regime_session_bull,"bear": self.regime_session_bear,"cap": CAP_REGIME_SESSION},
            },
            "bullish_reasons":    self.bullish_reasons,
            "bearish_reasons":    self.bearish_reasons,
            "neutral_notes":      self.neutral_notes,
            "blockers":           self.blockers,
            "why_not_trade":      self.why_not_trade or "",
            "final_reasoning":    (
                f"{self.final_signal}: {'; '.join(winning_reasons[:3])}"
                if winning_reasons else f"{self.final_signal}: {self.why_not_trade}"
            ),
        }
        return d


# ── Strategy Engine ────────────────────────────────────────────────────────────

class StrategyEngine:
    """
    Category-based, regime-aware, session-gated signal engine.

    Call generate_signal() with all available context.
    Returns a SignalOutput.to_dict() for API consumption.
    """

    def generate_signal(
        self,
        market_state: Dict[str, Any],
        options_data: Dict[str, Any],
        indicators:   Dict[str, Any],
        candles:      Optional[List] = None,
        regime_info:  Optional[Dict] = None,
        candle_info:  Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point.  All parameters are dicts from their respective engines.
        candles      — raw candle list for breakout confirmation (optional but preferred)
        regime_info  — output of RegimeDetector.detect()
        candle_info  — output of candle_analyzer.analyze_last_candle()
        """
        out     = SignalOutput()
        session = _get_session()
        cfg     = _SESSION_CONFIG[session]

        out.session_window = session.value

        now = ist_now()
        out.trade_type = (
            "POSITIONAL"
            if (now.hour > 15 or (now.hour == 15 and now.minute > 15))
            else "INTRADAY"
        )

        # ── Market closed ────────────────────────────────────────────────────
        if session == SessionWindow.CLOSED:
            out.why_not_trade = "Market is closed"
            return out.to_dict()

        # ── Regime ──────────────────────────────────────────────────────────
        if regime_info:
            out.market_regime   = regime_info.get("regime", "UNKNOWN")
            out.regime_strength = regime_info.get("regime_strength", 0)
        else:
            out.market_regime = "UNKNOWN"

        # ── Candle quality ───────────────────────────────────────────────────
        if candle_info:
            out.candle_quality = candle_info.get("candle_type", "UNKNOWN")

        # ── Data quality gate ────────────────────────────────────────────────
        dq_ok, dq_reason = self._check_data_quality(market_state, indicators)
        out.data_quality_ok = dq_ok
        if not dq_ok:
            out.why_not_trade = f"Data quality: {dq_reason}"
            out.blockers.append(dq_reason)
            return out.to_dict()

        price = (
            market_state.get("current_price")
            or indicators.get("current_price", 0)
        )

        # ── Score each category ───────────────────────────────────────────────
        pa   = self._score_price_action(market_state, indicators, price)
        vol  = self._score_volume(indicators, candle_info)
        strx = self._score_structure(market_state, indicators, options_data, price, candles)
        opts = self._score_options(options_data)
        reg  = self._score_regime_session(out.market_regime, session)

        for cat in (pa, vol, strx, opts, reg):
            cat.clamp()

        # Transfer to output
        out.price_action_bull    = pa.bull;   out.price_action_bear    = pa.bear
        out.volume_bull          = vol.bull;  out.volume_bear          = vol.bear
        out.structure_bull       = strx.bull; out.structure_bear       = strx.bear
        out.options_bull         = opts.bull; out.options_bear         = opts.bear
        out.regime_session_bull  = reg.bull;  out.regime_session_bear  = reg.bear

        out.total_bull = round(
            out.price_action_bull + out.volume_bull + out.structure_bull
            + out.options_bull + out.regime_session_bull, 1
        )
        out.total_bear = round(
            out.price_action_bear + out.volume_bear + out.structure_bear
            + out.options_bear + out.regime_session_bear, 1
        )

        # Bucket reasons
        for cat in (pa, vol, strx, opts, reg):
            for r in cat.reasons:
                rl = r.lower()
                if any(k in rl for k in ("bullish", "above vwap", "above ema", "support bounce",
                                          "long build", "short cover", "pcr=", "above session",
                                          "confirmed breakout", "above oi resist")):
                    out.bullish_reasons.append(r)
                elif any(k in rl for k in ("bearish", "below vwap", "below ema", "rejection",
                                            "short build", "long unwinding", "below session",
                                            "confirmed breakdown", "below oi support")):
                    out.bearish_reasons.append(r)
                else:
                    out.neutral_notes.append(r)

        # ── Apply candle penalty ──────────────────────────────────────────────
        penalty = (candle_info or {}).get("penalty", 1.0)
        if penalty < 1.0:
            out.total_bull = round(out.total_bull * penalty, 1)
            out.total_bear = round(out.total_bear * penalty, 1)
            out.neutral_notes.append(
                f"Candle penalty {penalty:.2f}× applied ({out.candle_quality})"
            )

        # ── Hard filters ──────────────────────────────────────────────────────
        filters_ok, filter_failures = self._hard_filters(
            out, session, cfg, market_state, options_data, indicators, candle_info
        )
        out.hard_filters_passed = filters_ok
        out.blockers.extend(filter_failures)

        # ── Conflict detection ────────────────────────────────────────────────
        conflicts = self._detect_conflicts(out, indicators)
        out.blockers.extend(conflicts)

        # ── Effective minimum score ───────────────────────────────────────────
        min_score = SIGNAL_MIN_SCORE + cfg["extra_thresh"]
        if out.market_regime == "SIDEWAYS":
            min_score = max(min_score, SIGNAL_MIN_SCORE + SIDEWAYS_EXTRA_THRESH)

        # ── Decision ─────────────────────────────────────────────────────────
        can_trade     = filters_ok and len(conflicts) == 0
        bull_dominates = (
            out.total_bull >= min_score
            and out.total_bull >= out.total_bear * SIGNAL_DOMINANCE_RATIO
        )
        bear_dominates = (
            out.total_bear >= min_score
            and out.total_bear >= out.total_bull * SIGNAL_DOMINANCE_RATIO
        )

        if can_trade and bull_dominates:
            out.final_signal    = "BUY_CE"
            out.direction       = "UP"
            out.signal_strength = out.total_bull
            out.setup_quality   = _quality_label(out.total_bull, min_score)

        elif can_trade and bear_dominates:
            out.final_signal    = "BUY_PE"
            out.direction       = "DOWN"
            out.signal_strength = out.total_bear
            out.setup_quality   = _quality_label(out.total_bear, min_score)

        else:
            out.final_signal    = "NO_TRADE"
            out.direction       = "SIDEWAYS"
            out.signal_strength = max(out.total_bull, out.total_bear)
            out.setup_quality   = "INVALID"
            if not out.why_not_trade:
                if not can_trade and out.blockers:
                    out.why_not_trade = out.blockers[0]
                elif bull_dominates or bear_dominates:
                    out.why_not_trade = f"Hard filter blocked trade: {out.blockers[0] if out.blockers else 'unknown'}"
                else:
                    gap = min_score - max(out.total_bull, out.total_bear)
                    out.why_not_trade = (
                        f"Score insufficient (bull={out.total_bull:.0f}, "
                        f"bear={out.total_bear:.0f}, need≥{min_score:.0f}, gap={gap:.0f}pts) "
                        f"or signals too evenly matched"
                    )

        out.confidence = out.signal_strength  # backward-compat alias

        return out.to_dict()

    # ── Category 1: Price Action Bias ─────────────────────────────────────────

    def _score_price_action(
        self,
        state:      Dict,
        indicators: Dict,
        price:      float,
    ) -> _Category:
        """
        EMA alignment (up to 15 pts) + VWAP relationship (up to 12 pts)
        + Momentum as tie-breaker (up to 3 pts, only when EMA agrees).

        Cap: 30 pts.  EMA, VWAP, and Momentum are all price-derived — capping
        prevents three correlated signals from tripling up the score.
        """
        cat = _Category(name="Price Action", cap=CAP_PRICE_ACTION)

        ema_9  = state.get("ema_9")  or (indicators.get("ema") or {}).get("ema_9")
        ema_21 = state.get("ema_21") or (indicators.get("ema") or {}).get("ema_21")
        vwap   = state.get("vwap")   or indicators.get("vwap")
        mom    = state.get("momentum") or indicators.get("momentum")

        # ── EMA alignment (up to 15 pts) ──
        if ema_9 and ema_21:
            if price > ema_9 > ema_21:
                cat.bull += 15.0
                cat.reasons.append(
                    f"Strong bullish EMA stack: price({price:.0f}) > EMA9({ema_9:.0f}) > EMA21({ema_21:.0f})"
                )
            elif ema_9 > ema_21 and price > ema_21:
                cat.bull += 7.0
                cat.reasons.append(
                    f"Mild bullish EMA: EMA9({ema_9:.0f}) > EMA21({ema_21:.0f}), price above EMA21"
                )
            elif price < ema_9 < ema_21:
                cat.bear += 15.0
                cat.reasons.append(
                    f"Strong bearish EMA stack: price({price:.0f}) < EMA9({ema_9:.0f}) < EMA21({ema_21:.0f})"
                )
            elif ema_9 < ema_21 and price < ema_21:
                cat.bear += 7.0
                cat.reasons.append(
                    f"Mild bearish EMA: EMA9({ema_9:.0f}) < EMA21({ema_21:.0f}), price below EMA21"
                )
            else:
                cat.reasons.append(
                    f"EMA9({ema_9:.0f}) ≈ EMA21({ema_21:.0f}) — no clear EMA trend"
                )
        else:
            cat.reasons.append("EMA values not available")

        # ── VWAP relationship (up to 12 pts) ──
        if vwap and vwap > 0:
            dist_pct = ((price - vwap) / vwap) * 100
            if dist_pct > VWAP_STRONG_DIST:
                cat.bull += 12.0
                cat.reasons.append(f"Price well above VWAP ({dist_pct:+.2f}%) — strong bullish VWAP")
            elif dist_pct > VWAP_MILD_DIST:
                cat.bull += 5.0
                cat.reasons.append(f"Price above VWAP ({dist_pct:+.2f}%) — mild bullish VWAP")
            elif dist_pct < -VWAP_STRONG_DIST:
                cat.bear += 12.0
                cat.reasons.append(f"Price well below VWAP ({dist_pct:+.2f}%) — strong bearish VWAP")
            elif dist_pct < -VWAP_MILD_DIST:
                cat.bear += 5.0
                cat.reasons.append(f"Price below VWAP ({dist_pct:+.2f}%) — mild bearish VWAP")
            else:
                cat.reasons.append(f"Price near VWAP ({dist_pct:+.2f}%) — neutral zone")
        else:
            cat.reasons.append("VWAP unavailable")

        # ── Momentum as tie-breaker (up to 3 pts, only confirms existing bias) ──
        if mom is not None:
            if mom > MOMENTUM_CONFIRM_THRESH and cat.bull > cat.bear:
                cat.bull += 3.0
                cat.reasons.append(f"Momentum confirming bullish bias (+{mom:.1f} pts)")
            elif mom < -MOMENTUM_CONFIRM_THRESH and cat.bear > cat.bull:
                cat.bear += 3.0
                cat.reasons.append(f"Momentum confirming bearish bias ({mom:.1f} pts)")

        return cat

    # ── Category 2: Volume Confirmation ───────────────────────────────────────

    def _score_volume(
        self,
        indicators:  Dict,
        candle_info: Optional[Dict],
    ) -> _Category:
        """
        Volume spike must align with candle direction to score fully.
        Spike on indecisive candle → minimal ambiguous credit.
        No spike → 0 pts.

        Cap: 20 pts.
        """
        cat = _Category(name="Volume", cap=CAP_VOLUME)

        vol   = indicators.get("volume", {})
        spike = vol.get("spike", False)
        rel   = vol.get("relative_volume") or 2.0

        if not spike:
            cat.reasons.append("No significant volume spike")
            return cat

        c_dir       = (candle_info or {}).get("direction", "neutral")
        is_decisive = (candle_info or {}).get("is_decisive", False)

        if c_dir == "bullish" and is_decisive:
            pts = min(CAP_VOLUME, 10.0 + (rel - 2.0) * 2.5)
            cat.bull += pts
            cat.reasons.append(
                f"Volume spike ({rel:.1f}×) on decisive bullish candle — bullish volume confirmation"
            )
        elif c_dir == "bearish" and is_decisive:
            pts = min(CAP_VOLUME, 10.0 + (rel - 2.0) * 2.5)
            cat.bear += pts
            cat.reasons.append(
                f"Volume spike ({rel:.1f}×) on decisive bearish candle — bearish volume confirmation"
            )
        elif c_dir == "bullish" and not is_decisive:
            cat.bull += 5.0
            cat.reasons.append(
                f"Volume spike ({rel:.1f}×) on moderate bullish candle — weak bullish confirmation"
            )
        elif c_dir == "bearish" and not is_decisive:
            cat.bear += 5.0
            cat.reasons.append(
                f"Volume spike ({rel:.1f}×) on moderate bearish candle — weak bearish confirmation"
            )
        else:
            # Indecisive / neutral candle — ambiguous
            cat.bull += 3.0
            cat.bear += 3.0
            cat.reasons.append(
                f"Volume spike ({rel:.1f}×) on indecisive candle — direction ambiguous, minimal weight"
            )

        return cat

    # ── Category 3: Structure / Breakout Context ───────────────────────────────

    def _score_structure(
        self,
        state:       Dict,
        indicators:  Dict,
        options:     Dict,
        price:       float,
        candles:     Optional[List],
    ) -> _Category:
        """
        OI support/resistance proximity + session S/R breakout validation.
        Breakout is only confirmed when CLOSE > level AND held for 2 candles.
        Single-candle intrabar spikes receive minimal credit.

        Cap: 25 pts.
        """
        cat = _Category(name="Structure", cap=CAP_STRUCTURE)

        oi_sup  = options.get("oi_support")
        oi_res  = options.get("oi_resistance")
        sup_res = indicators.get("support_resistance", {})
        s_sup   = sup_res.get("support")  or state.get("session_low")
        s_res   = sup_res.get("resistance") or state.get("session_high")

        # ── OI level proximity ──
        if oi_sup and price > 0:
            dist = ((price - oi_sup) / oi_sup) * 100
            if 0 < dist < 0.40:
                cat.bull += 10.0
                cat.reasons.append(
                    f"Near OI put support {oi_sup} (+{dist:.2f}%) — potential bounce"
                )
            elif dist <= 0:
                cat.bear += 6.0
                cat.reasons.append(
                    f"Below OI support {oi_sup} — support failed, bearish pressure"
                )

        if oi_res and price > 0:
            dist = ((oi_res - price) / oi_res) * 100
            if 0 < dist < 0.40:
                cat.bear += 10.0
                cat.reasons.append(
                    f"Near OI call resistance {oi_res} (+{dist:.2f}%) — potential rejection"
                )
            elif dist <= 0:
                cat.bull += 6.0
                cat.reasons.append(
                    f"Above OI resistance {oi_res} — resistance cleared, bullish"
                )

        # ── Session S/R breakout (requires candle close confirmation) ──
        if candles and len(candles) >= 2:
            def _close(c):
                if isinstance(c, (list, tuple)) and len(c) >= 5:
                    return float(c[4])
                if isinstance(c, dict):
                    return float(c.get("close", c.get("c", price)))
                return price

            last_close = _close(candles[-1])
            prev_close = _close(candles[-2])

            if s_res and s_res > 0:
                if last_close > s_res and prev_close > s_res:
                    # Two consecutive closes above resistance → confirmed breakout
                    cat.bull += 20.0
                    cat.reasons.append(
                        f"Confirmed breakout above session resistance {s_res:.0f} "
                        f"(2 consecutive closes above)"
                    )
                elif price > s_res and last_close <= s_res:
                    # Intrabar spike — not confirmed
                    cat.bull += 3.0
                    cat.reasons.append(
                        f"Unconfirmed intrabar spike above {s_res:.0f} — candle not closed above (potential fake)"
                    )
                elif last_close > s_res and prev_close <= s_res:
                    # First candle closed above — partial credit, await confirmation
                    cat.bull += 10.0
                    cat.reasons.append(
                        f"First candle closed above session resistance {s_res:.0f} — awaiting 2nd candle confirmation"
                    )

            if s_sup and s_sup > 0:
                if last_close < s_sup and prev_close < s_sup:
                    cat.bear += 20.0
                    cat.reasons.append(
                        f"Confirmed breakdown below session support {s_sup:.0f} "
                        f"(2 consecutive closes below)"
                    )
                elif price < s_sup and last_close >= s_sup:
                    cat.bear += 3.0
                    cat.reasons.append(
                        f"Unconfirmed intrabar dip below {s_sup:.0f} — candle not closed below (potential fake)"
                    )
                elif last_close < s_sup and prev_close >= s_sup:
                    cat.bear += 10.0
                    cat.reasons.append(
                        f"First candle closed below session support {s_sup:.0f} — awaiting confirmation"
                    )
        else:
            # Fallback: single candle / no candle history
            if s_res and price > s_res:
                cat.bull += 7.0
                cat.reasons.append(
                    f"Price above session resistance {s_res:.0f} (unconfirmed — no prior candle data)"
                )
            elif s_sup and price < s_sup:
                cat.bear += 7.0
                cat.reasons.append(
                    f"Price below session support {s_sup:.0f} (unconfirmed — no prior candle data)"
                )

        return cat

    # ── Category 4: Options Sentiment ─────────────────────────────────────────

    def _score_options(self, options: Dict) -> _Category:
        """
        PCR zones (up to 10 pts) + OI buildup pattern (up to 10 pts).
        PCR neutral zone (0.9–1.1) = 0 pts.
        Options sentiment alone cannot trigger a trade — it is confirmation only.

        Cap: 20 pts.
        """
        cat = _Category(name="Options Sentiment", cap=CAP_OPTIONS)

        if not options:
            cat.reasons.append("Options data unavailable — skipping sentiment")
            return cat

        pcr   = options.get("pcr", 0)
        build = options.get("dominant_buildup", "NONE")

        # ── PCR scoring (up to 10 pts) ──
        if pcr and pcr > 0:
            if pcr > PCR_STRONG_BULL:
                cat.bull += 10.0
                cat.reasons.append(
                    f"PCR={pcr:.2f} (>{PCR_STRONG_BULL}) — strong put writing → bullish market sentiment"
                )
            elif pcr > PCR_MILD_BULL:
                cat.bull += 5.0
                cat.reasons.append(f"PCR={pcr:.2f} — mild bullish sentiment")
            elif pcr < PCR_STRONG_BEAR:
                cat.bear += 10.0
                cat.reasons.append(
                    f"PCR={pcr:.2f} (<{PCR_STRONG_BEAR}) — strong call writing → bearish market sentiment"
                )
            elif pcr < PCR_MILD_BEAR:
                cat.bear += 5.0
                cat.reasons.append(f"PCR={pcr:.2f} — mild bearish sentiment")
            else:
                cat.reasons.append(
                    f"PCR={pcr:.2f} in neutral zone (0.7–1.1) — no directional confirmation"
                )
        else:
            cat.reasons.append("PCR unavailable or zero")

        # ── OI buildup (up to 10 pts) ──
        if build in ("LONG_BUILD_UP", "SHORT_COVERING"):
            cat.bull += 10.0
            cat.reasons.append(
                f"OI buildup: {build.replace('_', ' ').title()} — bullish positioning"
            )
        elif build in ("SHORT_BUILD_UP", "LONG_UNWINDING"):
            cat.bear += 10.0
            cat.reasons.append(
                f"OI buildup: {build.replace('_', ' ').title()} — bearish positioning"
            )
        else:
            cat.reasons.append("OI buildup: no dominant pattern detected")

        return cat

    # ── Category 5: Regime + Session Alignment ────────────────────────────────

    def _score_regime_session(
        self,
        regime:  str,
        session: SessionWindow,
    ) -> _Category:
        """
        Small bonus for regime alignment — decisive only in borderline cases.
        Cap: 5 pts.
        """
        cat = _Category(name="Regime/Session", cap=CAP_REGIME_SESSION)

        if regime == "TRENDING_UP":
            cat.bull = 5.0
            cat.reasons.append("Regime TRENDING_UP — bullish alignment bonus")
        elif regime == "TRENDING_DOWN":
            cat.bear = 5.0
            cat.reasons.append("Regime TRENDING_DOWN — bearish alignment bonus")
        elif regime == "SIDEWAYS":
            cat.reasons.append("Regime SIDEWAYS — no bonus; minimum score threshold raised")
        else:
            cat.reasons.append(f"Regime {regime} — no bonus applied")

        if session == SessionWindow.OPENING:
            cat.reasons.append("Opening session: minimum score threshold raised (+15 pts required)")
        elif session == SessionWindow.AFTERNOON:
            cat.reasons.append("Afternoon session: slightly tighter filters active")

        return cat

    # ── Hard Filters ──────────────────────────────────────────────────────────

    def _hard_filters(
        self,
        out:         SignalOutput,
        session:     SessionWindow,
        cfg:         Dict,
        state:       Dict,
        options:     Dict,
        indicators:  Dict,
        candle_info: Optional[Dict],
    ) -> Tuple[bool, List[str]]:
        """
        Binary gates.  Any failure → NO_TRADE regardless of score.
        """
        failures: List[str] = []

        # 1. Opening session noise — require very high score
        if session == SessionWindow.OPENING:
            eff_score = max(out.total_bull, out.total_bear)
            if eff_score < SIGNAL_MIN_SCORE + OPENING_EXTRA_THRESH:
                failures.append(
                    f"Opening session noise filter: score {eff_score:.0f} < "
                    f"{SIGNAL_MIN_SCORE + OPENING_EXTRA_THRESH} required (09:15–09:30)"
                )

        # 2. Sideways regime + breakout without price action basis
        if out.market_regime == "SIDEWAYS":
            if out.structure_bull >= 15 and out.price_action_bull < 8:
                failures.append(
                    "SIDEWAYS + breakout without price action support — high fake-breakout risk"
                )
            if out.structure_bear >= 15 and out.price_action_bear < 8:
                failures.append(
                    "SIDEWAYS + breakdown without price action support — high fake-breakdown risk"
                )

        # 3. Decisive candle requirement
        if candle_info:
            ct = candle_info.get("candle_type", "UNKNOWN")
            if ct == "DOJI":
                failures.append("DOJI candle on signal bar — no entry directional confirmation")
            elif ct == "INDECISIVE":
                failures.append("Indecisive candle on signal bar — avoid entry")

        # 4. Options data sanity
        if options:
            pcr = options.get("pcr", 0)
            if pcr <= 0:
                failures.append("PCR = 0 or missing — options data suspect")
            call_oi = options.get("total_call_oi", 0)
            put_oi  = options.get("total_put_oi", 0)
            if call_oi == 0 and put_oi == 0:
                failures.append("Call OI and Put OI both zero — option chain data unavailable")
        else:
            failures.append("Options data missing — cannot confirm with derivatives")

        # 5. ATR sanity
        atr = state.get("atr") or indicators.get("atr")
        if atr is None or atr <= 0:
            failures.append("ATR unavailable — cannot validate risk plan")
        elif atr > 300:
            failures.append(
                f"ATR={atr:.1f} is abnormally high — extreme volatility or data error"
            )

        # 6. Price range sanity
        price = state.get("current_price", 0)
        if price < 10_000 or price > 35_000:
            failures.append(
                f"Nifty price {price:.0f} outside expected range (10000–35000) — possible data issue"
            )

        return len(failures) == 0, failures

    # ── Conflict Detection ────────────────────────────────────────────────────

    def _detect_conflicts(
        self,
        out:        SignalOutput,
        indicators: Dict,
    ) -> List[str]:
        """
        Explicit conflict rules.  Any confirmed conflict → NO_TRADE.
        Reducing score slightly is not enough — conflicts must veto the trade.
        """
        conflicts: List[str] = []

        # Conflict A: Strong bullish price action + strong bearish options sentiment
        if out.price_action_bull >= 15 and out.options_bear >= 10:
            conflicts.append(
                f"Conflict A: bullish price action (PA={out.price_action_bull:.0f}) "
                f"vs bearish options sentiment (Opts_bear={out.options_bear:.0f}) — ambiguous"
            )

        # Conflict B: Strong bearish price action + strong bullish options sentiment
        if out.price_action_bear >= 15 and out.options_bull >= 10:
            conflicts.append(
                f"Conflict B: bearish price action (PA={out.price_action_bear:.0f}) "
                f"vs bullish options sentiment (Opts_bull={out.options_bull:.0f}) — ambiguous"
            )

        # Conflict C: Breakout signal in SIDEWAYS without supporting category
        if out.market_regime == "SIDEWAYS":
            if out.structure_bull >= 15 and out.price_action_bull < 10 and out.volume_bull < 10:
                conflicts.append(
                    "Conflict C: Breakout in SIDEWAYS regime — no price action or volume support "
                    "(potential liquidity trap)"
                )
            if out.structure_bear >= 15 and out.price_action_bear < 10 and out.volume_bear < 10:
                conflicts.append(
                    "Conflict C: Breakdown in SIDEWAYS regime — no price action or volume support "
                    "(potential stop hunt)"
                )

        # Conflict D: Volume direction opposes dominant price action
        vol = indicators.get("volume", {})
        if vol.get("spike"):
            if out.volume_bull > out.volume_bear and out.price_action_bear > out.price_action_bull + 8:
                conflicts.append(
                    "Conflict D: bullish volume spike but bearish price action — possible distribution"
                )
            if out.volume_bear > out.volume_bull and out.price_action_bull > out.price_action_bear + 8:
                conflicts.append(
                    "Conflict D: bearish volume spike but bullish price action — possible stop hunt"
                )

        return conflicts

    # ── Data Quality Check ────────────────────────────────────────────────────

    @staticmethod
    def _check_data_quality(
        state:      Dict,
        indicators: Dict,
    ) -> Tuple[bool, str]:
        price = state.get("current_price", 0)
        if not price or price <= 0:
            return False, "No current price in market state"

        ema_9  = state.get("ema_9")  or (indicators.get("ema") or {}).get("ema_9")
        ema_21 = state.get("ema_21") or (indicators.get("ema") or {}).get("ema_21")
        if not ema_9 or not ema_21:
            return False, "EMA values not computed yet (insufficient candle history)"

        vwap = state.get("vwap") or indicators.get("vwap")
        if not vwap:
            return False, "VWAP unavailable (no volume data?)"

        return True, "OK"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _quality_label(score: float, min_score: float) -> str:
    gap = score - min_score
    if gap >= 20:  return "STRONG"
    if gap >= 10:  return "MODERATE"
    if gap >= 0:   return "WEAK"
    return "INVALID"


# Global singleton
strategy_engine = StrategyEngine()
