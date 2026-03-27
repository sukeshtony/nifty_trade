"""Market State Manager — maintains real-time mathematical state for indicators.

Uses EMA(9, 21) per spec. Tracks VWAP, momentum, session support/resistance.
"""

import logging
from typing import Dict, Any, Optional
from utils.helpers import ist_now

logger = logging.getLogger(__name__)


class IncrementalEMA:
    def __init__(self, period: int):
        self.period = period
        self.multiplier = 2.0 / (period + 1)
        self.ema = None
        self.prices_history = []
        self.initialized = False

    def initialize(self, prices: list):
        if len(prices) < self.period:
            return
        self.ema = sum(prices[:self.period]) / self.period
        for price in prices[self.period:]:
            self.ema = (price - self.ema) * self.multiplier + self.ema
        self.initialized = True

    def update(self, current_price: float) -> Optional[float]:
        if not self.initialized:
            self.prices_history.append(current_price)
            if len(self.prices_history) >= self.period:
                self.initialize(self.prices_history)
            return self.ema
        self.ema = (current_price - self.ema) * self.multiplier + self.ema
        return round(self.ema, 2)


class MarketStateManager:
    """Manages real-time state for NIFTY — O(1) incremental indicator updates."""

    def __init__(self):
        self.state = {}
        self._indicators = {}
        self._callbacks = []

    def register_callback(self, callback):
        self._callbacks.append(callback)

    def _init_symbol_state(self, symbol: str):
        if symbol not in self.state:
            self.state[symbol] = {
                "current_price": 0,
                "prev_close": 0,
                "change": 0,
                "change_pct": 0,
                "volume_today": 0,
                "typical_price_volume": 0,
                "vwap": 0,
                "ema_9": None,
                "ema_21": None,
                "momentum": 0,
                "session_high": 0,
                "session_low": 0,
                "atr": None,
                "trend": {"ema_alignment": "SIDEWAYS", "above_vwap": None},
            }
            self._indicators[symbol] = {
                "ema_9": IncrementalEMA(9),
                "ema_21": IncrementalEMA(21),
                "close_history": [],  # For momentum calculation
                "tr_history": [],     # For ATR
            }

    def initialize_from_history(self, symbol: str, candles: list):
        """Seed incremental calculators with historical close prices."""
        self._init_symbol_state(symbol)
        if not candles:
            return

        def _get_val(c, idx):
            if isinstance(c, list) and len(c) > idx:
                return float(c[idx])
            return 0.0

        closes = [_get_val(c, 4) for c in candles]
        highs = [_get_val(c, 2) for c in candles]
        lows = [_get_val(c, 3) for c in candles]

        inds = self._indicators[symbol]
        inds["ema_9"].initialize(closes)
        inds["ema_21"].initialize(closes)

        # Store last N closes for momentum
        inds["close_history"] = closes[-20:]

        # Calculate ATR from history
        if len(candles) >= 15:
            trs = []
            for i in range(1, len(candles)):
                h = highs[i]
                l = lows[i]
                pc = closes[i - 1]
                tr = max(h - l, abs(h - pc), abs(l - pc))
                trs.append(tr)
            if trs:
                inds["tr_history"] = trs[-14:]
                self.state[symbol]["atr"] = round(sum(inds["tr_history"]) / len(inds["tr_history"]), 2)

        # Session high/low and prev_close from today's vs previous day candles
        today_str = ist_now().strftime("%Y-%m-%d")
        today_highs, today_lows, today_closes = [], [], []
        prev_day_closes = []
        for i, c in enumerate(candles):
            ts = c[0] if isinstance(c, list) and len(c) > 0 else ""
            if today_str in str(ts):
                today_highs.append(highs[i])
                today_lows.append(lows[i])
                today_closes.append(closes[i])
            else:
                prev_day_closes.append(closes[i])

        if today_highs:
            self.state[symbol]["session_high"] = max(today_highs)
            self.state[symbol]["session_low"] = min(today_lows)
        else:
            self.state[symbol]["session_high"] = max(highs) if highs else 0
            self.state[symbol]["session_low"] = min(lows) if lows else 0

        # Compute change from previous day's last close
        if prev_day_closes:
            prev_close = prev_day_closes[-1]
            self.state[symbol]["prev_close"] = prev_close
            current = today_closes[-1] if today_closes else closes[-1]
            if prev_close > 0:
                self.state[symbol]["change"] = round(current - prev_close, 2)
                self.state[symbol]["change_pct"] = round(((current - prev_close) / prev_close) * 100, 2)

        # Initialize VWAP (today's candles only for accuracy)
        vwap_candles = [c for c in candles if today_str in str(c[0])]
        tv = 0
        v = 0
        for c in vwap_candles:
            high = _get_val(c, 2)
            low = _get_val(c, 3)
            close = _get_val(c, 4)
            vol = _get_val(c, 5)
            tp = (high + low + close) / 3
            tv += tp * vol
            v += vol

        self.state[symbol]["typical_price_volume"] = tv
        self.state[symbol]["volume_today"] = v
        if v > 0:
            self.state[symbol]["vwap"] = round(tv / v, 2)

        # Set current price
        if closes:
            self.state[symbol]["current_price"] = closes[-1]

        # Calculate momentum
        if len(closes) >= 5:
            self.state[symbol]["momentum"] = round(closes[-1] - closes[-5], 2)

        self._sync_state_from_indicators(symbol)

    def _sync_state_from_indicators(self, symbol: str):
        inds = self._indicators[symbol]
        st = self.state[symbol]

        st["ema_9"] = round(inds["ema_9"].ema, 2) if inds["ema_9"].ema else None
        st["ema_21"] = round(inds["ema_21"].ema, 2) if inds["ema_21"].ema else None

        st["trend"]["ema_alignment"] = self._check_ema_alignment(st, st["current_price"])

        if st["vwap"]:
            st["trend"]["above_vwap"] = st["current_price"] > st["vwap"]

    def update_tick(self, symbol: str, price: float, volume: int = 0,
                    is_new_candle: bool = False, high: float = None, low: float = None):
        """Update indicators with O(1) complexity on a new tick."""
        self._init_symbol_state(symbol)
        st = self.state[symbol]
        inds = self._indicators[symbol]

        st["current_price"] = price

        # Update change from prev_close
        prev_close = st.get("prev_close", 0)
        if prev_close > 0:
            st["change"] = round(price - prev_close, 2)
            st["change_pct"] = round(((price - prev_close) / prev_close) * 100, 2)

        # Update EMAs
        inds["ema_9"].update(price)
        inds["ema_21"].update(price)

        # Update VWAP
        if volume > 0 and high is not None and low is not None:
            tp = (high + low + price) / 3
            st["typical_price_volume"] += (tp * volume)
            st["volume_today"] += volume
            if st["volume_today"] > 0:
                st["vwap"] = round(st["typical_price_volume"] / st["volume_today"], 2)

        # Update session high/low
        if high and high > st["session_high"]:
            st["session_high"] = high
        if low and low > 0 and (st["session_low"] == 0 or low < st["session_low"]):
            st["session_low"] = low

        # Update momentum (close-to-close)
        inds["close_history"].append(price)
        if len(inds["close_history"]) > 20:
            inds["close_history"] = inds["close_history"][-20:]
        if len(inds["close_history"]) >= 5:
            st["momentum"] = round(price - inds["close_history"][-5], 2)

        # Update ATR (simplified — using last TR values)
        if high is not None and low is not None and len(inds["close_history"]) >= 2:
            prev_close = inds["close_history"][-2]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            inds["tr_history"].append(tr)
            if len(inds["tr_history"]) > 14:
                inds["tr_history"] = inds["tr_history"][-14:]
            st["atr"] = round(sum(inds["tr_history"]) / len(inds["tr_history"]), 2)

        # Sync state
        self._sync_state_from_indicators(symbol)

        # Broadcast
        for cb in self._callbacks:
            cb(symbol, self.state[symbol])

    def get_state(self, symbol: str) -> Dict[str, Any]:
        """Get the current O(1) state without any recalculations."""
        raw = self.state.get(symbol, {})
        # Sanitize inf/nan — Python JSON encoder rejects them
        import math
        def _safe(v):
            if isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
                return 0
            return v
        return {k: _safe(v) for k, v in raw.items()}

    def _check_ema_alignment(self, state: dict, price: float) -> str:
        """Check EMA trend alignment using EMA 9 and 21."""
        e9 = state.get("ema_9")
        e21 = state.get("ema_21")

        if not all([e9, e21]):
            return "INSUFFICIENT_DATA"

        if price > e9 > e21:
            return "BULLISH"
        elif price < e9 < e21:
            return "BEARISH"
        else:
            return "SIDEWAYS"


# Global singleton
market_state_manager = MarketStateManager()
