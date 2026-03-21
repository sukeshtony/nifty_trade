"""
Market Regime Detector — detects TRENDING vs SIDEWAYS market regime.

Logic:
  - ATR expansion/compression (recent 5 vs prior 15 candles)
  - Directional consistency of last 10 candles
  - Range expansion (recent half vs older half)
  - Approximate short/long EMA alignment

No ML. Pure rule-based. Works candle-by-candle.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Thresholds
ATR_EXPANSION_THRESHOLD     = 1.15   # recent ATR > 1.15× older → expanding
ATR_COMPRESSION_THRESHOLD   = 0.90   # recent ATR < 0.90× older → compressing
DIRECTIONAL_MIN_TRENDING    = 0.65   # ≥65% candles same direction = trending
DIRECTIONAL_MAX_SIDEWAYS    = 0.55   # <55% = clearly sideways


class RegimeDetector:
    """
    Returns one of:
      TRENDING_UP   — confirmed uptrend with expanding range
      TRENDING_DOWN — confirmed downtrend with expanding range
      SIDEWAYS      — range-bound / consolidation
      UNKNOWN       — insufficient data
    """

    def detect(self, candles: List, atr: Optional[float]) -> Dict[str, Any]:
        """
        Analyze candles and return regime classification.

        Args:
            candles: List of [ts, open, high, low, close, volume] or dicts
            atr:     Current ATR value from indicator engine

        Returns dict with keys:
            regime, regime_strength (0-100), atr_state, directional_consistency, reason
        """
        if not candles or len(candles) < 20:
            return self._unknown("Insufficient candle history (need ≥20 candles)")

        if atr is None or atr <= 0:
            return self._unknown("ATR unavailable — cannot assess volatility regime")

        opens, highs, lows, closes = self._extract_ohlc(candles)
        if not closes:
            return self._unknown("Could not parse candle data")

        atr_state                       = self._atr_state(highs, lows, closes)
        dir_consistency, primary_dir    = self._directional_consistency(opens[-10:], closes[-10:])
        range_expanding                 = self._range_expansion(highs[-20:], lows[-20:])
        ema_bias                        = self._ema_bias(closes[-25:])

        # ── Decision logic ──
        is_trending = (
            atr_state == "EXPANDING"
            and dir_consistency >= DIRECTIONAL_MIN_TRENDING
            and range_expanding
            and (ema_bias == primary_dir or ema_bias is None)
        )

        is_sideways = (
            atr_state == "COMPRESSING"
            or dir_consistency < DIRECTIONAL_MAX_SIDEWAYS
            or (not range_expanding and dir_consistency < DIRECTIONAL_MIN_TRENDING)
        )

        if is_trending:
            regime = f"TRENDING_{primary_dir}"
            strength = min(100, int(
                30 * min(1.0, (dir_consistency - 0.5) / 0.35) +
                35 * (1 if atr_state == "EXPANDING" else 0) +
                25 * (1 if range_expanding else 0) +
                10 * (1 if ema_bias == primary_dir else 0)
            ))
            reason = (
                f"ATR {atr_state}, {int(dir_consistency * 100)}% directional consistency, "
                f"range {'expanding' if range_expanding else 'stable'}"
            )

        elif is_sideways:
            regime = "SIDEWAYS"
            raw = (
                0.35 * (1 if atr_state == "COMPRESSING" else 0.4) +
                0.40 * max(0, (DIRECTIONAL_MIN_TRENDING - dir_consistency) / DIRECTIONAL_MIN_TRENDING) +
                0.25 * (0 if range_expanding else 1)
            )
            strength = min(100, int(raw * 100))
            reason = (
                f"ATR {atr_state}, {int(dir_consistency * 100)}% consistency, "
                f"range {'expanding' if range_expanding else 'not expanding'}"
            )

        else:
            # Borderline — treat as SIDEWAYS for safety
            regime   = "SIDEWAYS"
            strength = 35
            reason   = "Borderline regime signals — defaulting SIDEWAYS (safer)"

        return {
            "regime":                  regime,
            "regime_strength":         strength,
            "atr_state":               atr_state,
            "directional_consistency": round(dir_consistency, 2),
            "reason":                  reason,
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_ohlc(candles: List) -> Tuple[List, List, List, List]:
        opens, highs, lows, closes = [], [], [], []
        for c in candles:
            try:
                if isinstance(c, (list, tuple)) and len(c) >= 5:
                    opens.append(float(c[1]))
                    highs.append(float(c[2]))
                    lows.append(float(c[3]))
                    closes.append(float(c[4]))
                elif isinstance(c, dict):
                    opens.append(float(c.get("open",  0)))
                    highs.append(float(c.get("high",  0)))
                    lows.append(float(c.get("low",   0)))
                    closes.append(float(c.get("close", 0)))
            except (TypeError, ValueError):
                continue
        return opens, highs, lows, closes

    @staticmethod
    def _atr_state(highs: List, lows: List, closes: List) -> str:
        if len(closes) < 20:
            return "STABLE"

        trs = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i]  - closes[i - 1]),
            )
            trs.append(tr)

        if len(trs) < 19:
            return "STABLE"

        recent_atr = sum(trs[-5:]) / 5
        older_atr  = sum(trs[-19:-5]) / 14

        if older_atr <= 0:
            return "STABLE"

        ratio = recent_atr / older_atr
        if ratio >= ATR_EXPANSION_THRESHOLD:
            return "EXPANDING"
        if ratio <= ATR_COMPRESSION_THRESHOLD:
            return "COMPRESSING"
        return "STABLE"

    @staticmethod
    def _directional_consistency(opens: List, closes: List) -> Tuple[float, str]:
        if len(opens) < 5:
            return 0.5, "UP"

        bullish = sum(1 for o, c in zip(opens, closes) if c > o)
        bearish = sum(1 for o, c in zip(opens, closes) if c < o)
        n       = len(opens)

        if bullish >= bearish:
            return round(bullish / n, 3), "UP"
        return round(bearish / n, 3), "DOWN"

    @staticmethod
    def _range_expansion(highs: List, lows: List) -> bool:
        if len(highs) < 10:
            return False
        mid           = len(highs) // 2
        recent_range  = max(highs[mid:]) - min(lows[mid:])
        older_range   = max(highs[:mid]) - min(lows[:mid])
        return older_range > 0 and recent_range > older_range * 1.05

    @staticmethod
    def _ema_bias(closes: List) -> Optional[str]:
        """Approximate EMA bias (short-period > long-period average)."""
        if len(closes) < 10:
            return None
        short_avg = sum(closes[-5:])  / 5
        long_avg  = sum(closes[-10:]) / 10
        if short_avg > long_avg * 1.001:
            return "UP"
        if short_avg < long_avg * 0.999:
            return "DOWN"
        return None

    @staticmethod
    def _unknown(reason: str) -> Dict[str, Any]:
        return {
            "regime":                  "UNKNOWN",
            "regime_strength":         0,
            "atr_state":               "STABLE",
            "directional_consistency": 0.5,
            "reason":                  reason,
        }


# Global singleton
regime_detector = RegimeDetector()
