# Mathematical Calculations & Formulas

This document outlines the exact mathematical formulas used natively in the Nifty Options Trading Application's Indicator Engine. It details how the calculations are derived step-by-step from raw 1-minute OHLCV (Open, High, Low, Close, Volume) data and how those numbers translate into trading signals.

---

## 1. Exponential Moving Average (EMA)
The application calculates a 9-period EMA and a 21-period EMA to determine short-term trend alignment. It uses Pandas' `ewm(span=p, adjust=False).mean()` which translates to standard EMA math.

**Mathematical Formula:**
```math
K = \frac{2}{N + 1}
```
```math
EMA_{current} = (Close_{current} \times K) + (EMA_{previous} \times (1 - K))
```
*Where:*
- `N`: Period length (either 9 or 21).
- `K`: The smoothing constant. For a 9-EMA, `K = 2 / 10 = 0.2`. For a 21-EMA, `K = 2 / 22 = 0.0909`.

**What Results It Shows:**
- Returns exactly two values in points: `ema_9` and `ema_21`.
- **Signal Condition:**
  - If `Current Price > EMA_9 > EMA_21` $\rightarrow$ **BULLISH** Trend
  - If `Current Price < EMA_9 < EMA_21` $\rightarrow$ **BEARISH** Trend
  - Otherwise $\rightarrow$ **SIDEWAYS**

---

## 2. Volume Weighted Average Price (VWAP)
The VWAP is calculated specifically for the current day's intraday trading session. 

**Mathematical Formula:**
1. First, calculate the **Typical Price** for each 1-minute candle:
```math
Typical Price_i = \frac{High_i + Low_i + Close_i}{3}
```
2. Then, sum the volume-weighted typical prices and divide by the cumulative volume for the day:
```math
VWAP = \frac{\sum_{i=1}^{n} (Typical Price_i \times Volume_i)}{\sum_{i=1}^{n} (Volume_i)}
```

**What Results It Shows:**
- Returns the exact `vwap` price level.
- Calculates `vwap_distance_pct`: 
  ```math
  Distance \% = \left(\frac{Current Price - VWAP}{VWAP}\right) \times 100
  ```
- **Signal Condition:** 
  - If Distance > +0.1% $\rightarrow$ **BULLISH**
  - If Distance < -0.1% $\rightarrow$ **BEARISH**

---

## 3. Momentum
Measures the absolute price change over a specific period. The application specifically uses a **5-candle lookback** period.

**Mathematical Formula:**
```math
Momentum = Close_{current} - Close_{current - 5}
```

**What Results It Shows:**
- Returns the absolute point difference (e.g., `+15.5` or `-12.3`).
- **Signal Condition:**
  - If `Momentum > 10` $\rightarrow$ Strong Upward Momentum (**BULLISH**)
  - If `Momentum < -10` $\rightarrow$ Strong Downward Momentum (**BEARISH**)

---

## 4. Support and Resistance (Session Extremes)
A highly localized calculation using Intraday (from 09:15 AM today) market extremes.

**Mathematical Formula:**
```math
Resistance = \max(High_{09:15}, High_{09:16}, \dots, High_{current})
```
```math
Support = \min(Low_{09:15}, Low_{09:16}, \dots, Low_{current})
```

**What Results It Shows:**
- Returns the absolute highest peak and lowest trough for the day.
- **Signal Condition:**
  - `Price > Resistance` $\rightarrow$ Breakout (**BULLISH**)
  - `Price < Support` $\rightarrow$ Breakdown (**BEARISH**)

---

## 5. Average True Range (ATR)
The Average True Range calculates market volatility. The system uses a **14-period** default.

**Mathematical Formula:**
1. First, find individual True Range (`TR`) for every candle. It takes the greatest of three values:
```math
TR = \max \begin{cases} High_{current} - Low_{current} \\ | High_{current} - Close_{previous} | \\ | Low_{current} - Close_{previous} | \end{cases}
```
2. Calculate the 14-period EMA of those True Ranges:
```math
ATR_{14} = EMA_{14}(TR)
```

**What Results It Shows:**
- Returns a raw point value representing average movement (e.g., `12.5` points per 1-minute candle).
- It is primarily used to measure the current pulse of the market's volatility rather than providing direct directional bias.

---

## 6. Volume Spike Detection
Determines if sudden institutional buying or selling is occurring by comparing exactly current volume against a moving average base line.

**Mathematical Formula:**
1. Calculate the moving average of volume across the prior 20 candles:
```math
AvgVol_{20} = \frac{\sum_{i=1}^{20} Volume_{current-i}}{20}
```
2. Calculate the Relative Volume:
```math
Relative Volume = \frac{Volume_{current}}{AvgVol_{20}}
```

**What Results It Shows:**
- Returns `Relative Volume` multiplier. 
- Evaluates if there is a `spike`. The threshold hardcoded into the system is **2.0x**.
- **Signal Condition:** If `Relative Volume >= 2.0`, it signals a volume spike, which adds a **NEUTRAL** confirmatory weight to existing directional biases (Confirming that the move has high participation).

---

## 7. Put-Call Ratio (Options Engine)
Calculated from the fetch in the `market_data_service` targeting NFO Option chains.

**Mathematical Formula:**
```math
PCR = \frac{\sum_{strikes} \text{Total Put Open Interest (PE OI)}}{\sum_{strikes} \text{Total Call Open Interest (CE OI)}}
```

**What Results It Shows:**
- Returns a decimal scalar.
- **Signal Condition:**
  - `PCR > 1.0` $\rightarrow$ Put writers dominate $\rightarrow$ **BULLISH**
  - `PCR < 0.7` $\rightarrow$ Call writers dominate $\rightarrow$ **BEARISH**
