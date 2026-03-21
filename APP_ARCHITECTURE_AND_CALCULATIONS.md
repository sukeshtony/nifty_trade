# Nifty Trading Application: Complete Calculations & Architecture Guide

This document provides a comprehensive overview of **every file** in the application that performs mathematical calculations, detailing exactly what indicators it computes and how it functions.

---

## 1. `services/market_state.py` (Real-Time Tick Engine)
This file handles **O(1) incremental calculations**. Because WebSocket data streams in hundreds of ticks per second, recalculating indicators from scratch every time is too slow. This file maintains a continuous state and updates math formulas on the fly.

### Indicators Calculated Here:
- **Incremental EMA (9 & 21)**: Instead of a full Pandas loop, it uses the formula: `ema = (current_price - prev_ema) * multiplier + prev_ema` with a multiplier of `2 / (period + 1)`.
- **Tick-Based VWAP**: As new ticks arrive with volume, it calculates the Typical Price `(High+Low+Close)/3`, adds `TypicalPrice * Volume` to a running total, and divides by running `TotalVolume`.
- **Session Support & Resistance**: Continuously checks if the incoming tick's `High` is greater than the recorded `session_high`, or if the `Low` is less than `session_low`, updating the intraday extremes instantly.
- **Incremental Momentum**: Keeps a rolling memory of the last 20 close prices and continuously subtracts `current_price - closes[-5]`.
- **Simplified ATR**: Keeps a rolling window of the last 14 True Ranges (TR). On every new 1-minute candle tick, it calculates `max(high-low, abs(high-prev_close), abs(low-prev_close))` and averages them.

---

## 2. `services/indicator_engine.py` (Batch Historical Engine)
Unlike the tick engine, this file is used on system startup or periodic background syncs to process large sets of historical 1-minute OHLCV candles using Pandas DataFrames.

### Indicators Calculated Here:
- **EMA (9 & 21)**: Uses pandas `df["close"].ewm(span=p, adjust=False).mean()`.
- **Daily VWAP**: Filters dataframe to the current day, calculating `sum(TypicalPrice * Volume) / sum(Volume)` for the whole session.
- **Momentum**: Performs a fast vector subtraction on the dataframe using `df["close"].iloc[-1] - df["close"].iloc[-6]`.
- **Support & Resistance**: Takes the absolute `.max()` and `.min()` of the daily dataframe frame.
- **ATR (14)**: Computes the massive standard ATR formula across the entire historical dataframe using pandas shifting and expanding mean smoothing.
- **Volume Spike**: Finds the mean of the last 20 volume candles. Returns `True` if the current candle's volume is $\ge 2.0x$ the mean.

---

## 3. `services/options_engine.py` (Derivatives Engine)
This file strictly deals with mathematics regarding the Options Chain (NFO segment: Call and Put contracts). 

### Indicators Calculated Here:
- **Put-Call Ratio (PCR)**: 
  - Iterates through all tracked strikes (ATM $\pm$ 3 strikes).
  - Sums Total Put Open Interest (PE OI) and Total Call Open Interest (CE OI).
  - Formula: `PCR = Total PE OI / Total CE OI`.
  - Interpreted as: $> 1.0$ Bullish, $< 0.7$ Bearish.
- **Max Pain**:
  - The strike price where option buyers would lose the maximum money (and sellers gain max profit) at expiry.
  - Formula: It iterates through every strike representing potential settlement. For each test strike, it calculates the intrinsic loss paid out to all ITM Calls and ITM Puts. The strike generating the **lowest total payout** is determined as Max Pain.
- **OI Support & Resistance**: 
  - Scanning strikes below the spot price, it finds the strike with the maximum Put OI (Support).
  - Scanning strikes above the spot price, it finds the strike with the maximum Call OI (Resistance).
- **Dominant Buildup**: 
  - Analyzes the net change in open interest and net change in premium across all strikes. Counts occurrences of "Long Build Up", "Short Covering", "Short Build Up", and "Long Unwinding", returning the pattern that occurs most frequently.

---

## 4. `services/strategy_engine.py` (Decision Engine)
This file contains the **Scoring & Weighting Mathematics** that translates all the numbers above into a trade signal.

### Logic Framework:
It evaluates the outputs from the three engines above against predetermined thresholds to assign a "Bias" and a "Weight".

1. **EMA Trend**: Bullish (+2) if $EMA_9 > EMA_{21}$. Bearish (+2) if reversed.
2. **VWAP**: Extracted from `market_state` or `indicator_engine`. Bullish (+2) if price $> 0.1\%$ above VWAP. Bearish (+2) if price $< -0.1\%$ below.
3. **PCR**: Bullish (+1.5) if PCR $> 1.0$. Bearish (+1.5) if PCR $< 0.7$.
4. **OI Buildup**: Extracted from `options_engine`. Bullish (+1.5) if dominating pattern is Long Buildup or Short Covering.
5. **Support/Resistance Breakdown**: Bullish (+1.5) if price $>$ session resistance. Bearish (+1.5) if price $<$ session support. (Proximity bounces get +1 weight).
6. **Momentum**: Bullish (+1) if Momentum $> 10$. Bearish (+1) if $< -10$.

### The Final Signal Formula:
All active bullish weights are summed ($\Sigma W_{bull}$). All active bearish weights are summed ($\Sigma W_{bear}$).

- Transacts a **`BUY_CE`** (Long Call) if: $\Sigma W_{bull} > (\Sigma W_{bear} \times 1.5)$ AND $\Sigma W_{bull} \ge 3.0$
- Transacts a **`BUY_PE`** (Long Put) if: $\Sigma W_{bear} > (\Sigma W_{bull} \times 1.5)$ AND $\Sigma W_{bear} \ge 3.0$
- Generates **`NO_TRADE`** if conditions equalize or total weight is near 0.
