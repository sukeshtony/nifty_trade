# Prediction Logic & Trading Strategy
This document explains the prediction calculations, buy conditions, and the data fetched to generate trading signals in the Nifty Trading Application.

## Overview
The application does **not** use AI or Machine Learning predictive models. Instead, it relies on a **Rule-Based Engine** that computes technical indicators and option chain metrics, assigns confidence weights to bullish / bearish / neutral biases, and generates deterministic signals (`BUY_CE`, `BUY_PE`, or `NO_TRADE`).

---

## 1. Data Fetched
The application fetches real-time and historical data primarily via the **Angel One Smart API**. 

The main data sources fetched are:
1. **Historical Candle Data (OHLCV)**: `open`, `high`, `low`, `close`, `volume` timestamps (typically 1-minute intervals).
2. **Real-time Ticks / Full Market Data**: Last Traded Price (LTP), day's open/high/low, price change, and traded volume.
3. **Instrument Master File**: Fetched once a day to locate all current Nifty Option Contracts (NFO segment) with their strikes and expiries.
4. **Option Chain Data**: The system checks the spot price, extracts ATM (At-The-Money) and surrounding strikes (CE/PE), and fetches Open Interest (OI), OI change, LTP, and Option Volume for those specific contracts.

---

## 2. Technical / Prediction Calculations
Calculations are handled by the `Indicator Engine` (`indicator_engine.py`), translating the raw OHLCV and market data into actionable values.

### A. Exponential Moving Average (EMA)
- **Calculation**: Computes EMA for periods `9` and `21`. EMA gives more weight to recent prices.
- **Purpose**: Identifies the short-term trend alignment. 

### B. Volume Weighted Average Price (VWAP)
- **Calculation**: Daily typical price `(High + Low + Close) / 3` multiplied by volume, divided by total volume. Resets daily.
- **Purpose**: A benchmark for intraday trend. Price above VWAP is bullish, below is bearish.

### C. Momentum
- **Calculation**: Current Close minus the Close of `N` periods ago (default `5` periods).
- **Purpose**: Measures the strength and velocity of price movement. 

### D. Support & Resistance Proximity
- **Calculation**: 
  - **Price-Based**: Tracks the active session high (resistance) and low (support).
  - **OI-Based**: Derived from the highest call open interest (OI Resistance) and highest put open interest (OI Support) in the Options Chain.
- **Purpose**: Detects proximity to major zones to anticipate bounces, rejections, breakouts, or breakdowns.

### E. Put-Call Ratio (PCR)
- **Calculation**: Total Put Open Interest divided by Total Call Open Interest.
- **Purpose**: 
  - `PCR > 1.0` implies more puts are written than calls (bullish sentitment).
  - `PCR < 0.7` implies more calls are written (bearish sentiment).

### F. Average True Range (ATR) & Volume Spike
- **ATR Calculation**: 14-period EMA of the True Range. Helps gauge market volatility.
- **Volume Spike**: Checks if the current 1-minute volume is `>= 2.0x` the average volume over the last 20 periods.

---

## 3. Buy Conditions & Confidence Scoring
The core decision logic resides in the `Strategy Engine` (`strategy_engine.py`). Each condition is evaluated and assigned a bias (`bullish`, `bearish`, or `neutral`) with a specific **weight**. 

### The Weights System
- **EMA Trend**: EMA9 > EMA21 (`bullish`, weight 2), EMA9 < EMA21 (`bearish`, weight 2).
- **VWAP**: Distance `> 0.1%` (`bullish`, weight 2), `< -0.1%` (`bearish`, weight 2).
- **PCR**: `> 1.0` (`bullish`, weight 1.5), `< 0.7` (`bearish`, weight 1.5).
- **OI Buildup Pattern**: 
  - Long Build Up / Short Covering (`bullish`, weight 1.5).
  - Short Build Up / Long Unwinding (`bearish`, weight 1.5).
- **Support / Resistance Breakouts**: Price breaks above session high (`bullish`, weight 1.5), breaks below session low (`bearish`, weight 1.5). Proximity bounces are weighted 1.
- **Momentum Strength**: `> +10 pts` (`bullish`, weight 1), `< -10 pts` (`bearish`, weight 1).

### Giving the Buy Signal
A unified total score is calculated for both the `bullish_weight` and `bearish_weight`. The final signal is based on these conditions:

1. **`BUY_CE` (Buy Call Option - Bullish Trade)**
   - The combined `bullish_weight` must be **at least 1.5x greater** than the `bearish_weight`.
   - The absolute `bullish_weight` must be **>= 3.0**.

2. **`BUY_PE` (Buy Put Option - Bearish Trade)**
   - The combined `bearish_weight` must be **at least 1.5x greater** than the `bullish_weight`.
   - The absolute `bearish_weight` must be **>= 3.0**.

3. **`NO_TRADE` (Sideways / Weak conviction)**
   - If total weight is `0` or if signals roughly equalize without passing the 1.5x dominance margin.
   
Whenever a trade passes the criteria, the system also returns a `confidence` level (0 to 95%) which is a ratio of the winning side's weight relative to the maximum possible weight, letting you know precisely how strong the setup is before proceeding with an order.
