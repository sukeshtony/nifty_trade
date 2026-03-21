"""Technical Indicator Engine — batch computation from OHLCV candle data.

Simplified for Nifty trading: EMA(9,21), VWAP, Momentum, ATR, Volume spike,
Support/Resistance.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List


def _to_dataframe(candles: List) -> pd.DataFrame:
    """Convert Angel One candle data to pandas DataFrame.
    Candle format: [timestamp, open, high, low, close, volume]
    """
    if not candles:
        return pd.DataFrame()

    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


# ── EMA ──

def calculate_ema(df: pd.DataFrame, periods: List[int] = [9, 21]) -> Dict[str, float]:
    """Exponential Moving Averages for given periods."""
    result = {}
    for p in periods:
        if len(df) >= p:
            ema = df["close"].ewm(span=p, adjust=False).mean()
            result[f"ema_{p}"] = round(float(ema.iloc[-1]), 2)
        else:
            result[f"ema_{p}"] = None
    return result


# ── VWAP ──

def calculate_vwap(df: pd.DataFrame) -> Optional[float]:
    """Volume Weighted Average Price — resets daily for intraday."""
    if df.empty or "volume" not in df.columns:
        return None

    today = df["timestamp"].dt.date.max()
    intraday = df[df["timestamp"].dt.date == today].copy()

    if intraday.empty or intraday["volume"].sum() == 0:
        return None

    typical_price = (intraday["high"] + intraday["low"] + intraday["close"]) / 3
    vwap = (typical_price * intraday["volume"]).sum() / intraday["volume"].sum()
    return round(float(vwap), 2)


# ── Momentum ──

def calculate_momentum(df: pd.DataFrame, period: int = 5) -> Optional[float]:
    """Momentum = Close(now) - Close(n candles ago)."""
    if len(df) < period + 1:
        return None
    return round(float(df["close"].iloc[-1] - df["close"].iloc[-period - 1]), 2)


# ── Support / Resistance ──

def calculate_support_resistance(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    """Session high (resistance) and low (support)."""
    if df.empty:
        return {"support": None, "resistance": None}

    today = df["timestamp"].dt.date.max()
    today_data = df[df["timestamp"].dt.date == today]

    if today_data.empty:
        return {"support": None, "resistance": None}

    return {
        "support": round(float(today_data["low"].min()), 2),
        "resistance": round(float(today_data["high"].max()), 2),
    }


# ── ATR ──

def calculate_atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    """Average True Range."""
    if len(df) < period + 1:
        return None

    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return round(float(atr.iloc[-1]), 2)


# ── Volume Spike Detection ──

def detect_volume_spike(df: pd.DataFrame, threshold: float = 2.0) -> Dict[str, Any]:
    """
    Detect if current volume is significantly above average.

    Also determines directional bias of the spike based on last candle
    body direction and size.  A volume spike only counts as directional
    confirmation when the triggering candle has a meaningful body.
    """
    if len(df) < 20:
        return {"spike": False, "relative_volume": None, "direction": "neutral"}

    # Use prior 19 candles (exclude current) to avoid comparing a candle to itself
    avg_vol     = df["volume"].iloc[-20:-1].mean()
    current_vol = float(df["volume"].iloc[-1])

    if avg_vol == 0:
        return {"spike": False, "relative_volume": None, "direction": "neutral"}

    relative = current_vol / avg_vol

    # Determine candle direction for the spike bar
    last        = df.iloc[-1]
    body        = last["close"] - last["open"]
    rng         = last["high"] - last["low"]
    body_ratio  = abs(body) / rng if rng > 0 else 0

    if body_ratio >= 0.35:
        direction = "bullish" if body > 0 else "bearish"
    else:
        direction = "neutral"  # indecisive candle — spike is ambiguous

    return {
        "spike":           relative >= threshold,
        "relative_volume": round(relative, 2),
        "current_volume":  int(current_vol),
        "avg_volume":      int(avg_vol),
        "direction":       direction,
        "body_ratio":      round(body_ratio, 3),
    }


# ── Master Function ──

def compute_all_indicators(candles: List) -> Dict[str, Any]:
    """Compute all indicators from raw candle data."""
    df = _to_dataframe(candles)
    if df.empty:
        return {"error": "No data available"}

    ema = calculate_ema(df, [9, 21])
    vwap = calculate_vwap(df)
    momentum = calculate_momentum(df)
    sup_res = calculate_support_resistance(df)
    atr = calculate_atr(df)
    volume = detect_volume_spike(df)

    current_price = float(df["close"].iloc[-1])

    return {
        "current_price": current_price,
        "timestamp": str(df["timestamp"].iloc[-1]),
        "ema": ema,
        "vwap": vwap,
        "momentum": momentum,
        "support_resistance": sup_res,
        "atr": atr,
        "volume": volume,
        "trend": {
            "ema_alignment": _check_ema_alignment(ema, current_price),
            "above_vwap": current_price > vwap if vwap else None,
            "vwap_distance_pct": round(((current_price - vwap) / vwap) * 100, 3) if vwap else None,
        },
    }


def _check_ema_alignment(ema: Dict, price: float) -> str:
    """Check EMA trend alignment."""
    e9 = ema.get("ema_9")
    e21 = ema.get("ema_21")

    if not all([e9, e21]):
        return "INSUFFICIENT_DATA"

    if price > e9 > e21:
        return "BULLISH"
    elif price < e9 < e21:
        return "BEARISH"
    else:
        return "SIDEWAYS"
