# NiftyTrader Dashboard Indicators & Calculation Logic

This document details how the indicators on the NiftyTrader dashboard are calculated, what data sources they use, what results they display, and how frequently they update on the UI.

## Overview

The dashboard gets its data from a combination of **live WebSocket ticks** (for instant price updates) and **REST API polling** (for complex aggregations and 1-minute historical data).

- **Data Sources:** 
  - **Live Ticks (Smart API V2 WebSocket):** Provides real-time Last Traded Price (LTP), volume, session highs/lows.
  - **1-Minute Candles:** Used extensively to seed baseline values (VWAP, previous close) and calculate volume spikes or regime shifts.
  - **Full Option Chain:** Angel One `getMarketData` API for NFO contracts (ATM ± 3 strikes).

---

## Indicators Breakdown

### 1. EMA Status (EMA 9 & EMA 21)
- **Calculation:** Exponential Moving Average (EMA) of the prices. The system uses a highly optimized `IncrementalEMA` algorithm. It seeds the EMAs using the 1-minute candle closes and then mathematically updates them in `O(1)` time on every incoming live tick.
- **Data Used:** 1-min historical candles (seed) + Live tick prices (updates).
- **Update Frequency:** **Instant** (updates on every WebSocket tick).
- **Displayed Results:**
  - `Strong Bullish`: Current Price > EMA 9 > EMA 21
  - `Mild Bullish`: EMA 9 > EMA 21 AND Current Price > EMA 21
  - `Strong Bearish`: Current Price < EMA 9 < EMA 21
  - `Mild Bearish`: EMA 9 < EMA 21 AND Current Price < EMA 21
  - `Neutral / Sideways`: Any other tangled variation.

### 2. VWAP Status (Volume Weighted Average Price)
- **Calculation:** `(Typical Price * Volume) / Total Volume` where Typical Price = `(High + Low + Close) / 3`. Starts calculating daily from 1-min candles and adds volume/price incrementally using live futures ticks (since spot indices do not report direct intraday volume).
- **Data Used:** Intraday 1-min candles + Live tick volume data.
- **Update Frequency:** **Instant** (updates on every WebSocket tick).
- **Displayed Results:**
  - `Bullish (Above {vwap})`: Current Price is above VWAP.
  - `Bearish (Below {vwap})`: Current Price is below VWAP.
  - `N/A (No Volume)`: If volume data is unavailable (e.g., fallback to cash index).

### 3. PCR (Put-Call Ratio)
- **Calculation:** Total Open Interest (OI) of Puts divided by Total OI of Calls across the tracked strikes (ATM ± 3 active strikes for the nearest weekly expiry).
- **Data Used:** Option Chain NFO API data.
- **Update Frequency:** **Medium** (Every 10 seconds via WebSocket, or every 30 seconds via REST fallback).
- **Displayed Results:**
  - Numeric Value colored dynamically (Green if > 1, Red if < 0.7, Gray/White otherwise).
  - Status Text: `Strongly Bullish` (> 1.3), `Bullish` (> 1.0), `Neutral` (0.7 to 1.0), `Bearish` (0.5 to 0.7), `Strongly Bearish` (< 0.5).

### 4. OI Buildup (Dominant Buildup)
- **Calculation:** The system calculates the OI change and Price Change for all CE and PE options in the ATM ± 3 range. Based on the price and OI changes, it decides the buildup nature:
  - `Long Build Up` (Price ↑, OI ↑)
  - `Short Build Up` (Price ↓, OI ↑)
  - `Short Covering` (Price ↑, OI ↓)
  - `Long Unwinding` (Price ↓, OI ↓)
  - The dominant (most frequent) pattern across the monitored strikes is selected.
- **Data Used:** Option Chain NFO API data (LTP and OI changes against day's baseline).
- **Update Frequency:** **Medium** (Every 10 seconds via WebSocket).
- **Displayed Results:** e.g., "Long Build Up", "Short Covering", "Neutral", etc.

### 5. Momentum
- **Calculation:** Close distance over recent ticks: `Current Price - Close(5 periods ago)`. In the live state manager, it uses a sliding window of recent closes.
- **Data Used:** 1-min candles + Live tick sliding history.
- **Update Frequency:** **Instant** (Updates on each new tick).
- **Displayed Results:**
  - `Bullish (+X)`: Positive value (colored Green).
  - `Bearish (-X)`: Negative value (colored Red).
  - `Neutral (0)`: No momentum.

### 6. Sup/Res (Support & Resistance)
- **Calculation:**
  - *Candle Sup/Res:* Takes the highest `high` (Resistance) and lowest `low` (Support) of the current day's candles/ticks.
  - *OI Sup/Res (in Key Indicators):* Scans Option Chain data; Strike with the highest Put OI acts as Support, highest Call OI acts as Resistance.
- **Data Used:** Intraday 1-min candles + Live tick High/Low.
- **Update Frequency:** **Instant** (for price breakout/breakdowns), 10 seconds (for Option Chain OI levels).
- **Displayed Results:** Formatted as `{Support_Value} / {Resistance_Value}` (e.g., "22800 / 23100").

### 7. Volume Spike
- **Calculation:** Evaluates the last 1-minute candle against the average volume of the preceding 19 candles. If `Current Volume >= (Average Volume * 2)`, a spike is detected. It also checks if the candle body is large enough (body vs. wick ratio >= 35%) to attribute a direction to the spike.
- **Data Used:** 1-min historical candles.
- **Update Frequency:** **Slower** (Relies on /api/signals/current polling on a 15-second interval).
- **Displayed Results:**
  - `Spike (2.5x)`: Significant spike detected.
  - `Normal`: Below threshold or normal trading volume.

### 8. Max Pain
- **Calculation:** Computes the theoretical financial pain for option buyers at every tracked strike. It assumes the stock expires at Strike X, sums up the intrinsic value multiplied by open interest of all in-the-money calls and puts. The strike resulting in the lowest total value paid out (minimum pain to option *writers/sellers*) is considered "Max Pain".
- **Data Used:** Option Chain NFO API data.
- **Update Frequency:** **Medium** (Every 10 seconds via WebSocket).
- **Displayed Results:** Strike price (e.g., `22950`).

---

## UI Update Frequencies Summary

| Category | Update Source | Approx. UI Delay |
| :--- | :--- | :--- |
| **Price & Instant Trend** (PriceBox, EMA, VWAP, Momentum, H/L) | WebSocket (`priceData`) | **< 1 second / Instant** |
| **Option Greek & Dynamics** (PCR, Max Pain, Buildup, OI Sup/Res) | WebSocket (`optionChain`) | **~ 10 seconds** |
| **Complex Aggregated Signalling** (Signal Engine, Strategy, Volume spikes) | REST Polling (`fetchSignal`) | **~ 15 seconds** |

*Note: The system gracefully handles fallback. If WebSocket is down or reconnecting, it safely falls back to polling REST endpoints to ensure the dashboard rarely shows blank data.*
