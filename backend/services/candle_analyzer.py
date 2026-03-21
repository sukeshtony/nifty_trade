"""
Candle Strength Analyzer — classifies candles by body/wick structure.

Used as an entry confirmation filter.
Strong directional candles confirm signal direction.
Doji / long-wick / indecisive candles reduce or block entry.

Thresholds:
  - Strong body   ≥ 60% of range
  - Moderate body  35–60% of range
  - Doji body     ≤ 15% of range
  - Long wick     ≥ 45% of range on one side
"""

from typing import Dict, Any, List, Optional

# Body-to-range ratio thresholds
STRONG_BODY_RATIO   = 0.60
MODERATE_BODY_RATIO = 0.35
DOJI_BODY_RATIO     = 0.15
LONG_WICK_THRESHOLD = 0.45


def analyze_last_candle(candles: List) -> Dict[str, Any]:
    """
    Analyze the most recent candle's strength and direction.

    Args:
        candles: List of candles (each as [ts, open, high, low, close, vol] or dict)

    Returns dict with:
        candle_type    — STRONG_BULLISH | STRONG_BEARISH | MODERATE_BULLISH |
                         MODERATE_BEARISH | DOJI | SHOOTING_STAR | HAMMER |
                         INDECISIVE | UNKNOWN
        body_ratio     — body / range  (0–1)
        upper_wick_ratio
        lower_wick_ratio
        close_location — (close - low) / range  (1 = closed at high)
        is_decisive    — False if entry should be blocked or penalized
        direction      — "bullish" | "bearish" | "neutral"
        strength_score — 0 (doji) → 3 (strong)
        penalty        — score multiplier 0.2–1.0 (1.0 = no penalty)
    """
    if not candles:
        return _unknown("No candle data")

    last = candles[-1]
    try:
        if isinstance(last, (list, tuple)) and len(last) >= 5:
            open_  = float(last[1])
            high   = float(last[2])
            low    = float(last[3])
            close  = float(last[4])
        elif isinstance(last, dict):
            open_  = float(last.get("open",  last.get("o", 0)))
            high   = float(last.get("high",  last.get("h", 0)))
            low    = float(last.get("low",   last.get("l", 0)))
            close  = float(last.get("close", last.get("c", 0)))
        else:
            return _unknown("Unrecognized candle format")
    except (TypeError, ValueError):
        return _unknown("Invalid candle values")

    candle_range = high - low
    if candle_range <= 0:
        return _unknown("Zero-range candle — no price movement")

    body          = abs(close - open_)
    upper_wick    = high - max(close, open_)
    lower_wick    = min(close, open_) - low
    body_ratio    = body / candle_range
    upper_wick_r  = upper_wick / candle_range
    lower_wick_r  = lower_wick / candle_range
    close_loc     = (close - low) / candle_range

    is_bullish = close > open_
    is_bearish = close < open_

    # ── Classification ────────────────────────────────────────────────────────

    if body_ratio <= DOJI_BODY_RATIO:
        return _result(
            candle_type="DOJI",
            direction="neutral",
            strength=0,
            is_decisive=False,
            penalty=0.20,
            body_ratio=body_ratio,
            upper_wick_r=upper_wick_r,
            lower_wick_r=lower_wick_r,
            close_loc=close_loc,
        )

    # Long upper wick on bullish body → shooting star / rejection from top
    if upper_wick_r >= LONG_WICK_THRESHOLD and is_bullish:
        return _result(
            candle_type="SHOOTING_STAR",
            direction="neutral",   # conflicted — bullish body but strong rejection
            strength=1,
            is_decisive=False,
            penalty=0.40,
            body_ratio=body_ratio,
            upper_wick_r=upper_wick_r,
            lower_wick_r=lower_wick_r,
            close_loc=close_loc,
        )

    # Long lower wick on bearish body → hammer-like rejection from bottom
    if lower_wick_r >= LONG_WICK_THRESHOLD and is_bearish:
        return _result(
            candle_type="HAMMER",
            direction="neutral",   # conflicted — bearish body but strong support
            strength=1,
            is_decisive=False,
            penalty=0.40,
            body_ratio=body_ratio,
            upper_wick_r=upper_wick_r,
            lower_wick_r=lower_wick_r,
            close_loc=close_loc,
        )

    # Long upper wick on bearish body → double bearish (bearish body + rejection at top)
    if upper_wick_r >= LONG_WICK_THRESHOLD and is_bearish:
        return _result(
            candle_type="BEARISH_REJECTION",
            direction="bearish",
            strength=2,
            is_decisive=True,
            penalty=1.0,
            body_ratio=body_ratio,
            upper_wick_r=upper_wick_r,
            lower_wick_r=lower_wick_r,
            close_loc=close_loc,
        )

    # Long lower wick on bullish body → double bullish (bullish body + support bounce)
    if lower_wick_r >= LONG_WICK_THRESHOLD and is_bullish:
        return _result(
            candle_type="BULLISH_SUPPORT",
            direction="bullish",
            strength=2,
            is_decisive=True,
            penalty=1.0,
            body_ratio=body_ratio,
            upper_wick_r=upper_wick_r,
            lower_wick_r=lower_wick_r,
            close_loc=close_loc,
        )

    # Strong body
    if body_ratio >= STRONG_BODY_RATIO:
        return _result(
            candle_type="STRONG_BULLISH" if is_bullish else "STRONG_BEARISH",
            direction="bullish" if is_bullish else "bearish",
            strength=3,
            is_decisive=True,
            penalty=1.0,
            body_ratio=body_ratio,
            upper_wick_r=upper_wick_r,
            lower_wick_r=lower_wick_r,
            close_loc=close_loc,
        )

    # Moderate body
    if body_ratio >= MODERATE_BODY_RATIO:
        return _result(
            candle_type="MODERATE_BULLISH" if is_bullish else "MODERATE_BEARISH",
            direction="bullish" if is_bullish else "bearish",
            strength=2,
            is_decisive=True,
            penalty=0.80,
            body_ratio=body_ratio,
            upper_wick_r=upper_wick_r,
            lower_wick_r=lower_wick_r,
            close_loc=close_loc,
        )

    # Small body — indecisive
    return _result(
        candle_type="INDECISIVE",
        direction="neutral",
        strength=1,
        is_decisive=False,
        penalty=0.35,
        body_ratio=body_ratio,
        upper_wick_r=upper_wick_r,
        lower_wick_r=lower_wick_r,
        close_loc=close_loc,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _result(
    candle_type:  str,
    direction:    str,
    strength:     int,
    is_decisive:  bool,
    penalty:      float,
    body_ratio:   float,
    upper_wick_r: float,
    lower_wick_r: float,
    close_loc:    float,
) -> Dict[str, Any]:
    return {
        "candle_type":      candle_type,
        "body_ratio":       round(body_ratio, 3),
        "upper_wick_ratio": round(upper_wick_r, 3),
        "lower_wick_ratio": round(lower_wick_r, 3),
        "close_location":   round(close_loc, 3),
        "is_decisive":      is_decisive,
        "direction":        direction,
        "strength_score":   strength,
        "penalty":          penalty,
    }


def _unknown(reason: str) -> Dict[str, Any]:
    return {
        "candle_type":      "UNKNOWN",
        "body_ratio":       0.0,
        "upper_wick_ratio": 0.0,
        "lower_wick_ratio": 0.0,
        "close_location":   0.5,
        "is_decisive":      False,
        "direction":        "neutral",
        "strength_score":   0,
        "penalty":          0.30,
        "reason":           reason,
    }
