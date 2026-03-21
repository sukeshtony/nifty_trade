# Nifty Options Trading System — Complete Calculations & Signal Logic

**Version:** Post-Refactor (March 2026)
**Type:** Rule-based, deterministic, candle-by-candle, no ML

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Data Pipeline](#2-data-pipeline)
3. [Indicator Calculations](#3-indicator-calculations)
   - 3.1 EMA (Exponential Moving Average)
   - 3.2 VWAP (Volume Weighted Average Price)
   - 3.3 ATR (Average True Range)
   - 3.4 Momentum
   - 3.5 Volume Spike Detection
   - 3.6 Session Support & Resistance
4. [Options Chain Calculations](#4-options-chain-calculations)
   - 4.1 Put-Call Ratio (PCR)
   - 4.2 Max Pain
   - 4.3 OI Support & Resistance
   - 4.4 OI Buildup Pattern
5. [Market Regime Detection](#5-market-regime-detection)
6. [Candle Strength Analysis](#6-candle-strength-analysis)
7. [Category-Based Signal Scoring](#7-category-based-signal-scoring)
   - 7.1 Category 1 — Price Action Bias
   - 7.2 Category 2 — Volume Confirmation
   - 7.3 Category 3 — Structure / Breakout Context
   - 7.4 Category 4 — Options Sentiment
   - 7.5 Category 5 — Regime & Session Alignment
8. [Hard Filters](#8-hard-filters)
9. [Conflict Detection](#9-conflict-detection)
10. [Final Decision Logic](#10-final-decision-logic)
11. [Risk Management Calculations](#11-risk-management-calculations)
12. [Complete Worked Example](#12-complete-worked-example)
13. [Signal Output Structure](#13-signal-output-structure)
14. [Session Windows & Thresholds](#14-session-windows--thresholds)

---

## 1. System Overview

This is a **rule-based Nifty index options signal engine**. It processes live 1-minute OHLCV candles and option chain data to generate one of three outputs every time the signal endpoint is called:

```
BUY_CE  — Buy a Call Option (bullish view on Nifty spot)
BUY_PE  — Buy a Put Option  (bearish view on Nifty spot)
NO_TRADE — Do not enter; conditions are insufficient or conflicting
```

The engine is **deterministic** — the same market data always produces the same signal. There is no machine learning, no prediction, and no lookahead bias. Every signal is computed from data that is already available at the time the candle closes.

### What the System Does NOT Do
- It does not predict price targets
- It does not guarantee a win rate
- The `signal_strength` score is NOT a win probability
- It does not place orders automatically (it generates signals for manual or automated execution)

---

## 2. Data Pipeline

```
Angel One API (WebSocket ticks)
        |
        v
MarketStateManager
   - Receives every price tick
   - Incrementally updates EMA, VWAP, ATR, Momentum in O(1) time
   - Stores session high/low
        |
        v
Candle Data (1-minute OHLCV)
   - Fetched via REST API every 60 seconds
   - Also cached from previous fetch (120-second cache)
        |
        v
IndicatorEngine (batch from candles)          OptionsEngine (option chain)
   - EMA(9), EMA(21)                              - PCR
   - VWAP                                         - Max Pain
   - ATR(14)                                      - OI Support/Resistance
   - Momentum(5)                                  - OI Buildup Pattern
   - Volume Spike
   - Session S/R
        |                                               |
        +-------------------+---------------------------+
                            |
                            v
                    RegimeDetector
                    - TRENDING_UP / TRENDING_DOWN / SIDEWAYS
                            |
                            v
                    CandleAnalyzer
                    - STRONG_BULLISH / DOJI / INDECISIVE / etc.
                            |
                            v
                    StrategyEngine
                    - 5 category scores
                    - Hard filters
                    - Conflict detection
                    - Decision logic
                            |
                            v
                    RiskEngine
                    - Stop Loss / Target / R:R
                    - Position sizing
                    - Daily guardrails
                            |
                            v
                    Final Signal Output
                    (BUY_CE / BUY_PE / NO_TRADE)
```

---

## 3. Indicator Calculations

All indicators are computed from 1-minute OHLCV candles unless stated otherwise.
Each candle is structured as: `[timestamp, open, high, low, close, volume]`

---

### 3.1 EMA — Exponential Moving Average

**Periods used:** EMA(9) and EMA(21)

**Why EMA instead of SMA?**
EMA gives more weight to recent prices. It reacts faster to new price moves than a Simple Moving Average, making it more useful for intraday trading.

#### Initialization (first calculation from historical data)

```
Step 1: SMA seed = sum of first N closing prices / N
        where N = period (9 or 21)

Step 2: For each remaining close price after the seed:
        EMA = (Price - Previous_EMA) × Multiplier + Previous_EMA

        where Multiplier = 2 / (Period + 1)
```

**Multiplier values:**
```
EMA(9)  multiplier = 2 / (9  + 1) = 2/10 = 0.2000
EMA(21) multiplier = 2 / (21 + 1) = 2/22 = 0.0909
```

#### Live update (on every new tick or candle close)

```
EMA_new = (Current_Price - EMA_old) × Multiplier + EMA_old
```

**Numerical Example:**
```
Previous EMA(9)  = 22,450
Current price    = 22,480
Multiplier       = 0.2

EMA(9)_new = (22,480 - 22,450) × 0.2 + 22,450
           = 30 × 0.2 + 22,450
           = 6 + 22,450
           = 22,456
```

#### How EMA generates signals

The system uses a 3-tier alignment check:

| Condition | Label | Score |
|---|---|---|
| Price > EMA9 > EMA21 | Strong Bullish Stack | +15 pts bullish |
| EMA9 > EMA21 but Price between them | Mild Bullish | +7 pts bullish |
| Price < EMA9 < EMA21 | Strong Bearish Stack | +15 pts bearish |
| EMA9 < EMA21 but Price between them | Mild Bearish | +7 pts bearish |
| EMA9 ≈ EMA21 or mixed | No Clear Trend | 0 pts |

---

### 3.2 VWAP — Volume Weighted Average Price

VWAP resets to zero at the start of each trading day (9:15 AM IST).

#### Formula

```
Typical Price (TP) = (High + Low + Close) / 3

VWAP = Sum(TP × Volume) / Sum(Volume)
     = Cumulative(TP × Vol) / Cumulative(Volume)
```

This is calculated cumulatively from the first candle of the day.

#### Incremental update (on each new tick)

```
typical_price_volume_cumulative += TP × new_volume
volume_cumulative               += new_volume

VWAP = typical_price_volume_cumulative / volume_cumulative
```

**Numerical Example:**
```
Candle 1: H=22,400, L=22,360, C=22,385, Vol=5,000
  TP1 = (22,400 + 22,360 + 22,385) / 3 = 22,381.67
  TPxVol1 = 22,381.67 × 5,000 = 111,908,333

Candle 2: H=22,430, L=22,390, C=22,420, Vol=7,000
  TP2 = (22,430 + 22,390 + 22,420) / 3 = 22,413.33
  TPxVol2 = 22,413.33 × 7,000 = 156,893,333

VWAP after Candle 2:
  = (111,908,333 + 156,893,333) / (5,000 + 7,000)
  = 268,801,666 / 12,000
  = 22,400.14
```

#### How VWAP generates signals

VWAP distance is measured as a percentage:
```
VWAP_distance% = ((Current_Price - VWAP) / VWAP) × 100
```

| Distance | Label | Score |
|---|---|---|
| > +0.30% | Well above VWAP | +12 pts bullish |
| +0.10% to +0.30% | Mildly above VWAP | +5 pts bullish |
| -0.10% to +0.10% | Near VWAP (neutral zone) | 0 pts |
| -0.30% to -0.10% | Mildly below VWAP | +5 pts bearish |
| < -0.30% | Well below VWAP | +12 pts bearish |

**VWAP as institutional reference:**
Institutional traders use VWAP as their execution benchmark. Price consistently above VWAP means buyers are in control (paid above average). Price below VWAP means sellers dominate.

---

### 3.3 ATR — Average True Range

**Period:** 14 candles

ATR measures the average price range per candle, capturing actual volatility.

#### True Range (TR) for each candle

```
TR = Maximum of:
     (1) High - Low                     (current candle range)
     (2) |High - Previous Close|        (gap-up scenario)
     (3) |Low  - Previous Close|        (gap-down scenario)

TR = max(High - Low,  |High - Prev_Close|,  |Low - Prev_Close|)
```

**Why three components?**
A candle that gaps up or down has a larger "effective range" than just its own high-low. TR captures this.

#### ATR Calculation (EMA-smoothed)

```
ATR(14) = EMA of last 14 True Range values
        = TR.ewm(span=14, adjust=False).mean()

This uses the same EMA formula as price EMAs:
  ATR_new = (TR_current - ATR_old) × (2/15) + ATR_old
  Multiplier = 2 / (14 + 1) = 2/15 = 0.1333
```

**Numerical Example:**
```
Candle data:
  Today:    H=22,500, L=22,420, C=22,490
  Previous: C=22,450

TR1 = H - L             = 22,500 - 22,420 = 80
TR2 = |H - Prev_Close|  = |22,500 - 22,450| = 50
TR3 = |L - Prev_Close|  = |22,420 - 22,450| = 30

TR = max(80, 50, 30) = 80

If previous ATR(14) = 45:
  ATR_new = (80 - 45) × 0.1333 + 45
          = 35 × 0.1333 + 45
          = 4.67 + 45
          = 49.67
```

**How ATR is used:**
- Input for regime detection (ATR expansion = trending, compression = sideways)
- Input for risk management (stop-loss and target calculation)
- Hard filter: ATR > 300 = data error / extreme volatility → NO_TRADE

---

### 3.4 Momentum

**Period:** 5 candles (5-minute lookback on 1-minute data)

#### Formula

```
Momentum = Close(current) - Close(5 candles ago)
```

This measures how much the price has moved in the last 5 minutes.

**Numerical Example:**
```
Current close   = 22,500
Close 5 min ago = 22,460

Momentum = 22,500 - 22,460 = +40 points
```

Negative momentum means price has fallen over the last 5 minutes.

#### How Momentum is used in scoring

Momentum is a **tie-breaker only** — it adds points only when the EMA alignment already agrees with the direction. It cannot override a bearish EMA setup.

```
If Momentum > +15 AND EMA alignment is already bullish:
    Add +3 pts to bullish score

If Momentum < -15 AND EMA alignment is already bearish:
    Add +3 pts to bearish score

Otherwise: 0 pts (momentum ignored)
```

Maximum contribution: 3 pts (out of 100 total possible)

---

### 3.5 Volume Spike Detection

#### Formula

```
Average Volume = Mean of previous 19 candle volumes
                 (current candle excluded to avoid self-comparison)

Relative Volume = Current_Candle_Volume / Average_Volume

Spike = True  if Relative_Volume >= 2.0  (volume is 2× or more than normal)
      = False otherwise
```

#### Directional Assignment

The spike direction is determined by the candle body:

```
Body       = Close - Open
Range      = High - Low
Body_Ratio = |Body| / Range

If Body_Ratio >= 0.35:
    Direction = "bullish" if Close > Open
    Direction = "bearish" if Close < Open
Else:
    Direction = "neutral"  (indecisive candle, spike is ambiguous)
```

**Numerical Example:**
```
Previous 19 candles average volume = 80,000
Current candle volume               = 200,000

Relative Volume = 200,000 / 80,000 = 2.5x  → SPIKE = True

Current candle: O=22,450, H=22,510, L=22,440, C=22,495
Body      = 22,495 - 22,450 = 45 (positive = bullish)
Range     = 22,510 - 22,440 = 70
Body_Ratio = 45 / 70 = 0.643  (>= 0.35, so directional)
Direction = "bullish"
```

#### How Volume Spike is scored

| Spike + Candle Direction | Decisive? | Points |
|---|---|---|
| Spike + Bullish + Decisive candle (body ≥ 60%) | Yes | +10 to +20 pts bullish |
| Spike + Bearish + Decisive candle | Yes | +10 to +20 pts bearish |
| Spike + Bullish + Moderate candle | Partial | +5 pts bullish |
| Spike + Bearish + Moderate candle | Partial | +5 pts bearish |
| Spike on Doji / Neutral candle | No | +3/+3 (ambiguous, both sides) |
| No spike | — | 0 pts |

**Exact points formula for decisive spike:**
```
Points = min(20,  10 + (Relative_Volume - 2.0) × 2.5)

Example: Relative_Volume = 2.5x
  Points = min(20, 10 + (2.5 - 2.0) × 2.5)
         = min(20, 10 + 1.25)
         = 11.25 pts
```

Volume cap: 20 pts maximum.

---

### 3.6 Session Support & Resistance

These are the **intraday high and low** from today's candles only.

```
Session Resistance = max(all today's candle Highs)
Session Support    = min(all today's candle Lows)
```

These update with every new candle throughout the day. They represent the price boundaries the market has established so far in the session.

---

## 4. Options Chain Calculations

The option chain covers **ATM ± 3 strikes** (7 strikes total, at 50-point intervals for Nifty).

For example, if Nifty spot = 22,487:
- ATM strike = 22,500
- Chain analyzed: 22,250 / 22,300 / 22,350 / 22,400 / 22,450 / 22,500 / 22,550 / 22,600 / 22,650 / 22,700 / 22,750

---

### 4.1 PCR — Put-Call Ratio

#### Formula

```
PCR = Total Put Open Interest / Total Call Open Interest
    = Sum(putOI across all analyzed strikes) / Sum(callOI across all analyzed strikes)
```

**Numerical Example:**
```
Strike  | Call OI  | Put OI
22,400  | 120,000  | 80,000
22,450  |  90,000  | 110,000
22,500  | 200,000  | 180,000
22,550  | 150,000  |  60,000
22,600  |  80,000  |  40,000

Total Call OI = 120+90+200+150+80 = 640,000
Total Put OI  = 80+110+180+60+40  = 470,000

PCR = 470,000 / 640,000 = 0.734
```

#### What PCR means

Option writers (sellers) are usually institutional money. When Put OI is high relative to Call OI, it means institutions are writing (selling) puts, effectively betting the market won't fall below those strikes. This is a bullish signal for the spot market.

#### PCR Scoring Zones

| PCR Value | Interpretation | Score |
|---|---|---|
| > 1.30 | Strong put writing → institutions bullish | +10 pts bullish |
| 1.10 – 1.30 | Mild put writing → mild bullish | +5 pts bullish |
| 0.70 – 1.10 | Neutral zone — ignore | 0 pts |
| 0.60 – 0.70 | Mild call writing → mild bearish | +5 pts bearish |
| < 0.60 | Heavy call writing → strong bearish | +10 pts bearish |

**Critical rule:** PCR alone cannot trigger a trade. It is a confirmation signal only.

---

### 4.2 Max Pain

Max Pain is the price level at which the maximum number of option buyers lose money at expiry. Market makers have incentive to keep the price near max pain as expiry approaches.

#### Formula

For each test strike K, calculate total payout to all option buyers if expiry is at K:

```
For all Call options with strike S where K > S:
    Call_payout(S) = (K - S) × Call_OI(S)    [these calls are ITM at expiry K]

For all Put options with strike S where K < S:
    Put_payout(S)  = (S - K) × Put_OI(S)     [these puts are ITM at expiry K]

Total_pain(K) = Sum of all Call_payout + Sum of all Put_payout

Max Pain Strike = K where Total_pain(K) is MINIMUM
```

**Numerical Example (simplified, 3 strikes):**
```
Strike  | Call OI | Put OI
22,400  | 100,000 |  50,000
22,500  | 200,000 | 150,000
22,600  |  80,000 | 200,000

Testing K = 22,500 as expiry:
  Call 22,400 is ITM by 100pts: 100 × 100,000 = 10,000,000
  Put  22,600 is ITM by 100pts: 100 × 200,000 = 20,000,000
  Total pain at 22,500 = 30,000,000

Testing K = 22,400:
  Put 22,500 is ITM by 100pts: 100 × 150,000 = 15,000,000
  Put 22,600 is ITM by 200pts: 200 × 200,000 = 40,000,000
  Total pain at 22,400 = 55,000,000

Max Pain = 22,500 (lowest total payout to buyers)
```

Max Pain is informational — it tells you where the market might gravitate as expiry approaches. It is not directly used in scoring but is displayed in the options summary.

---

### 4.3 OI Support & Resistance

These are the **option-chain-derived** support and resistance levels, separate from the session price-based levels.

```
OI Resistance = Strike with highest Call OI that is ABOVE or AT spot price
               (highest call writing = options sellers protecting that level)

OI Support    = Strike with highest Put OI that is BELOW or AT spot price
               (highest put writing = options sellers protecting that level)
```

**Logic:** Massive call OI at a strike means many call writers (usually institutional) are positioned there — they will lose money if price crosses that strike. So the market tends to face resistance at that level. Similarly, heavy put OI provides support.

#### How OI Levels are scored

**Near OI Support (price 0% to +0.40% above support):**
```
Score = +10 pts bullish
Reason: Price is testing support, potential bounce zone
```

**Below OI Support (price < support level):**
```
Score = +6 pts bearish
Reason: Support level has broken, bearish pressure likely
```

**Near OI Resistance (price within -0.40% below resistance):**
```
Score = +10 pts bearish
Reason: Price approaching resistance, potential rejection
```

**Above OI Resistance (price > resistance level):**
```
Score = +6 pts bullish
Reason: Resistance has been cleared, bullish momentum
```

---

### 4.4 OI Buildup Pattern

Each strike is tagged with a buildup pattern based on change in OI and price change:

| Pattern | Condition | Meaning |
|---|---|---|
| LONG_BUILD_UP | OI increasing + Price rising | Fresh buying, bullish |
| SHORT_COVERING | OI decreasing + Price rising | Bears exiting, bullish |
| SHORT_BUILD_UP | OI increasing + Price falling | Fresh selling, bearish |
| LONG_UNWINDING | OI decreasing + Price falling | Bulls exiting, bearish |

The engine counts the frequency of each pattern across all analyzed strikes and returns the most common one as the **dominant buildup**.

#### How OI Buildup is scored

| Dominant Pattern | Score |
|---|---|
| LONG_BUILD_UP | +10 pts bullish |
| SHORT_COVERING | +10 pts bullish |
| SHORT_BUILD_UP | +10 pts bearish |
| LONG_UNWINDING | +10 pts bearish |
| NONE | 0 pts |

---

## 5. Market Regime Detection

The regime detector runs on the candle history to determine whether the market is trending or ranging. This gates the strategy differently.

### Output
```
TRENDING_UP   — confirmed uptrend with expanding range
TRENDING_DOWN — confirmed downtrend with expanding range
SIDEWAYS      — range-bound / consolidating
UNKNOWN       — insufficient data (<20 candles)
```

### Three Checks

#### Check 1: ATR State (Expansion vs Compression)

```
Recent ATR   = Average TR of last 5 candles
Older ATR    = Average TR of prior 15 candles (candles -20 to -5)

Ratio = Recent_ATR / Older_ATR

EXPANDING    if Ratio >= 1.15  (recent volatility 15%+ higher)
COMPRESSING  if Ratio <= 0.90  (recent volatility 10%+ lower)
STABLE       otherwise
```

**Numerical Example:**
```
Last 5 candle TRs:  70, 75, 65, 80, 72  → avg = 72.4
Prior 15 candle TRs average = 55.0

Ratio = 72.4 / 55.0 = 1.316  → EXPANDING
```

#### Check 2: Directional Consistency

```
Last 10 candles examined:
Bullish candle count = number where Close > Open
Bearish candle count = number where Close < Open

If Bullish > Bearish:
    Consistency = Bullish_count / 10
    Direction   = "UP"
Else:
    Consistency = Bearish_count / 10
    Direction   = "DOWN"
```

**Threshold:** Consistency >= 0.65 (65% of candles agree) = trending directionally

```
Example: 7 of last 10 candles are bullish
  Consistency = 7/10 = 0.70  → Trending UP (0.70 >= 0.65)
```

#### Check 3: Range Expansion

```
Split candle history into two halves:
  Recent half (last 10): max(highs) - min(lows)
  Older half (prior 10): max(highs) - min(lows)

Range_Expanding = True if Recent_range > Older_range × 1.05
                       (recent range is 5%+ wider)
```

### Regime Decision Logic

```
TRENDING_{direction} if ALL THREE are true:
    ATR_state == EXPANDING
    Directional_Consistency >= 0.65
    Range_Expanding == True

SIDEWAYS if ANY of:
    ATR_state == COMPRESSING
    Directional_Consistency < 0.55
    (Not range expanding AND consistency < 0.65)

Otherwise: SIDEWAYS (default to safer classification)
```

### Impact on Signal Thresholds

| Regime | Effect |
|---|---|
| TRENDING_UP | Bullish entry minimum stays at 60. Regime bonus: +5 pts bullish |
| TRENDING_DOWN | Bearish entry minimum stays at 60. Regime bonus: +5 pts bearish |
| SIDEWAYS | Minimum score raised by 15 pts (to 75). Breakout without PA support is blocked |
| UNKNOWN | Same as SIDEWAYS (conservative) |

---

## 6. Candle Strength Analysis

Every signal evaluation analyzes the most recent completed candle to assess whether it is a valid entry confirmation.

### Raw Measurements

```
Body         = |Close - Open|
Range        = High - Low
Upper Wick   = High - max(Close, Open)
Lower Wick   = min(Close, Open) - Low

Body_Ratio       = Body / Range           (0 to 1)
Upper_Wick_Ratio = Upper_Wick / Range     (0 to 1)
Lower_Wick_Ratio = Lower_Wick / Range     (0 to 1)
Close_Location   = (Close - Low) / Range  (0=closed at low, 1=closed at high)
```

### Classification Rules

| Candle Type | Condition | Is Decisive | Penalty |
|---|---|---|---|
| DOJI | Body_Ratio <= 0.15 | NO | 0.20 (80% penalty) |
| INDECISIVE | Body_Ratio 0.15–0.35, mixed wicks | NO | 0.35 (65% penalty) |
| SHOOTING_STAR | Body_Ratio > 0.15, bullish body, upper wick >= 45% | NO | 0.40 |
| HAMMER | Body_Ratio > 0.15, bearish body, lower wick >= 45% | NO | 0.40 |
| BEARISH_REJECTION | Bearish body + upper wick >= 45% | YES | 1.00 (double bearish) |
| BULLISH_SUPPORT | Bullish body + lower wick >= 45% | YES | 1.00 (double bullish) |
| MODERATE_BULLISH/BEARISH | Body_Ratio 0.35–0.60 | YES | 0.80 |
| STRONG_BULLISH/BEARISH | Body_Ratio >= 0.60 | YES | 1.00 |

### Penalty Application

The candle penalty is applied to both bull and bear total scores:

```
Final_bull_score = Raw_bull_score × Penalty
Final_bear_score = Raw_bear_score × Penalty
```

**Example — DOJI candle on otherwise strong bullish setup:**
```
Raw bull score = 68 pts
DOJI penalty   = 0.20

Adjusted bull = 68 × 0.20 = 13.6 pts  → falls below 60 threshold → NO_TRADE
```

This prevents entering trades on indecisive candles even when all other signals are bullish.

### Hard Blocks

If the signal candle is `DOJI` or `INDECISIVE`, the hard filter also blocks the trade regardless of score — the penalty and the filter work in combination.

---

## 7. Category-Based Signal Scoring

The total signal score is built from **5 independent categories**. Each has a maximum cap.

```
Category                 Cap     Source
────────────────────────────────────────────────────
1. Price Action Bias      30     EMA + VWAP + Momentum
2. Volume Confirmation    20     Directional volume spike
3. Structure / Breakout   25     OI levels + Session S/R
4. Options Sentiment      20     PCR + OI Buildup
5. Regime / Session        5     Regime alignment bonus
────────────────────────────────────────────────────
Total Maximum            100
```

Each category produces **bullish points** and **bearish points** independently. They are never mixed. At the end:

```
Total_Bull = sum of bullish pts from all categories
Total_Bear = sum of bearish pts from all categories
```

---

### 7.1 Category 1 — Price Action Bias (cap: 30 pts)

**Why capped?** EMA, VWAP, and Momentum are all derived from price. Without a cap, a strong uptrend would give +2 (EMA) + +2 (VWAP) + +1 (Momentum) = +5 from a single price move. The cap prevents one market factor (price direction) from dominating the entire score.

| Sub-indicator | Max | Formula |
|---|---|---|
| EMA Alignment | 15 | 3-tier stack check |
| VWAP Distance | 12 | % distance zones |
| Momentum | 3 | Tie-breaker only when EMA agrees |

**EMA scoring** (as shown in Section 3.1):
- Strong stack (Price > EMA9 > EMA21): +15 bull or +15 bear
- Weak alignment: +7

**VWAP scoring** (as shown in Section 3.2):
- Well above (>0.30%): +12 bull
- Mildly above (0.10–0.30%): +5 bull
- Well below (<-0.30%): +12 bear
- Mildly below: +5 bear

**Momentum** (Section 3.4):
- Only +3 when confirming existing bias. Never standalone.

**After all sub-scores, cap is applied:**
```
Bullish_PA = min(raw_bullish_PA, 30)
Bearish_PA = min(raw_bearish_PA, 30)
```

---

### 7.2 Category 2 — Volume Confirmation (cap: 20 pts)

Scoring as shown in Section 3.5. Key principle: volume without directional context is worthless. A volume spike on a doji gives only 3 pts to each side.

**Full points formula:**
```
pts = min(20,  10 + (Relative_Volume - 2.0) × 2.5)
```

This scales the score with the magnitude of the spike — a 3x volume spike scores higher than a 2.1x spike.

---

### 7.3 Category 3 — Structure / Breakout Context (cap: 25 pts)

This category rewards confirmed breakouts and penalizes proximity to resistance.

#### OI Level Scoring (max 20 pts from OI levels)

```
Near OI Support (0% to +0.40% above it):   +10 pts bullish
Below OI Support (price < support):         +6 pts bearish

Near OI Resistance (0% to -0.40% below):   +10 pts bearish
Above OI Resistance (price > resistance):   +6 pts bullish
```

**Distance formula:**
```
Distance_from_support%   = ((Price - OI_Support) / OI_Support) × 100
Distance_from_resistance% = ((OI_Resistance - Price) / OI_Resistance) × 100
```

#### Session Breakout Scoring (max 20 pts from breakout)

This is the most nuanced part — breakout quality determines the score:

```
CONFIRMED BREAKOUT (2 consecutive candle closes above resistance):
    Score = +20 pts bullish
    Condition: last_close > session_resistance AND prev_close > session_resistance

PARTIAL BREAKOUT (only the most recent candle closed above):
    Score = +10 pts bullish
    Condition: last_close > session_resistance AND prev_close <= session_resistance

UNCONFIRMED INTRABAR SPIKE (price above but candle not closed above):
    Score = +3 pts bullish (minimal — potential fake breakout)
    Condition: current_price > session_resistance AND last_close <= session_resistance
```

Same logic applies for breakdown to bearish side.

**Why this matters:**
A price that temporarily spikes above a level intrabar and then falls back is a classic fake breakout / liquidity trap. The 2-candle confirmation rule filters out most of these.

---

### 7.4 Category 4 — Options Sentiment (cap: 20 pts)

Two sub-components, each contributing up to 10 pts:

```
PCR scoring:     0 to 10 pts  (Section 4.1 zones)
OI Buildup:      0 to 10 pts  (Section 4.4 patterns)

Maximum bullish: PCR_bull(10) + OI_bull(10) = 20 pts
Maximum bearish: PCR_bear(10) + OI_bear(10) = 20 pts
```

**Important rule:** Options sentiment has a cap of 20 pts. Even with perfect PCR and perfect OI buildup, options sentiment can only contribute 20% of the total score. This prevents a bullish option chain from triggering a trade when price action is conflicting.

---

### 7.5 Category 5 — Regime & Session Alignment (cap: 5 pts)

Small bonus to reward alignment with the detected regime. Acts as a tie-breaker.

```
TRENDING_UP:   +5 pts bullish
TRENDING_DOWN: +5 pts bearish
SIDEWAYS:      0 pts (no bonus, thresholds raised instead)
UNKNOWN:       0 pts
```

---

## 8. Hard Filters

Hard filters are **binary gates** — if any one fails, the output is forced to NO_TRADE regardless of the score. They cannot be overridden by a high score.

### Filter 1: Opening Session Noise (9:15 – 9:30 AM)

```
If session == OPENING:
    If max(total_bull, total_bear) < 75:
        BLOCK → "Opening session noise: score below 75 threshold"
```

The first 15 minutes of trading have erratic price action driven by overnight news, gap adjustments, and order imbalances. The threshold is raised from 60 to 75 during this window.

### Filter 2: Sideways + Breakout Mismatch

```
If regime == SIDEWAYS:
    If structure_bull >= 15 AND price_action_bull < 8:
        BLOCK → "Breakout without price action in SIDEWAYS — fake breakout risk"
    If structure_bear >= 15 AND price_action_bear < 8:
        BLOCK → "Breakdown without price action in SIDEWAYS — fake breakdown risk"
```

In a sideways market, breakout signals frequently fail. A breakout must have price action (EMA alignment, VWAP) support to be trusted.

### Filter 3: Indecisive Candle

```
If candle_type == "DOJI":
    BLOCK → "DOJI candle on signal bar — no directional confirmation"
If candle_type == "INDECISIVE":
    BLOCK → "Indecisive candle — avoid entry"
```

A doji or spinning top candle means buyers and sellers are in balance. Entering on such a candle is entering blind.

### Filter 4: Options Data Sanity

```
If PCR == 0 or PCR is missing:
    BLOCK → "PCR missing — options data suspect"
If Total_Call_OI == 0 AND Total_Put_OI == 0:
    BLOCK → "Option chain data unavailable"
If options_data is entirely absent:
    BLOCK → "Options data missing — cannot confirm with derivatives"
```

### Filter 5: ATR Sanity

```
If ATR is None or ATR <= 0:
    BLOCK → "ATR unavailable — cannot validate risk plan"
If ATR > 300:
    BLOCK → "ATR abnormally high — extreme volatility or data error"
```

An ATR above 300 for Nifty would mean 300+ point candles, which either means a data error or a circuit-breaker event. In either case, trading is inappropriate.

### Filter 6: Price Sanity

```
If Current_Price < 10,000 OR Current_Price > 35,000:
    BLOCK → "Nifty price outside expected range — data issue"
```

---

## 9. Conflict Detection

Conflicts are situations where two different categories give directly opposing signals. The engine resolves these by blocking the trade rather than averaging the signals.

### Conflict A: Bullish Price Action + Bearish Options Sentiment

```
If price_action_bull >= 15 AND options_bear >= 10:
    CONFLICT → NO_TRADE

Meaning: Price EMA/VWAP is bullish but option writers are positioning bearishly.
Could indicate: Smart money distributing into the rally.
```

### Conflict B: Bearish Price Action + Bullish Options Sentiment

```
If price_action_bear >= 15 AND options_bull >= 10:
    CONFLICT → NO_TRADE

Meaning: Price is falling but OI data shows bullish positioning.
Could indicate: Institutional accumulation in a pullback, or data lag.
```

### Conflict C: Breakout in Sideways Regime

```
If regime == SIDEWAYS AND (structure_bull >= 15 OR structure_bear >= 15):
    If (regime_strength < 50) AND (price_action < 10) AND (volume < 10):
        CONFLICT → NO_TRADE

Meaning: A large breakout signal is firing in what is detected as a sideways market.
This is the classic liquidity trap / stop hunt pattern.
```

### Conflict D: Volume Opposes Price Action

```
If volume spike is bullish (bullish candle) AND price_action_bear > price_action_bull + 8:
    CONFLICT → "Bullish volume spike but bearish price action — possible distribution"

If volume spike is bearish AND price_action_bull > price_action_bear + 8:
    CONFLICT → "Bearish volume spike but bullish price action — possible accumulation"
```

---

## 10. Final Decision Logic

After all categories are scored and penalties applied:

### Step 1: Apply minimum score threshold

```
base_threshold = 60

If regime == SIDEWAYS:
    threshold = max(base_threshold, 75)  → 75 pts required

If session == OPENING:
    threshold = max(threshold, 75)       → 75 pts required

If session == AFTERNOON:
    threshold = base_threshold + 5 = 65

If session == CLOSING:
    threshold = base_threshold + 2 = 62
```

### Step 2: Check dominance

```
Bull_dominates = (total_bull >= threshold) AND (total_bull >= total_bear × 1.5)
Bear_dominates = (total_bear >= threshold) AND (total_bear >= total_bull × 1.5)
```

The `1.5× dominance ratio` means the winning side must be at least 50% stronger than the losing side. This prevents 51 vs 49 situations from generating a trade.

### Step 3: Check filters and conflicts

```
can_trade = (all hard filters passed) AND (no conflicts detected)
```

### Step 4: Generate final output

```
If can_trade AND Bull_dominates:
    signal = BUY_CE
    signal_strength = total_bull
    setup_quality = STRONG/MODERATE/WEAK

Elif can_trade AND Bear_dominates:
    signal = BUY_PE
    signal_strength = total_bear
    setup_quality = STRONG/MODERATE/WEAK

Else:
    signal = NO_TRADE
    why_not_trade = [specific reason]
```

### Setup Quality Labels

```
STRONG   if signal_strength >= threshold + 20  (e.g., >= 80 for MORNING session)
MODERATE if signal_strength >= threshold + 10  (e.g., >= 70)
WEAK     if signal_strength >= threshold       (e.g., >= 60)
INVALID  if below threshold
```

---

## 11. Risk Management Calculations

Risk management runs **after** the signal decision. A BUY_CE or BUY_PE signal is further validated by checking if the trade has a mathematically acceptable risk profile. If not, it is demoted to NO_TRADE.

### Step 1: Option ATR Proxy

```
Spot_ATR      = ATR from indicator engine (14-period, in Nifty points)
Option_ATR    = Spot_ATR × 0.60

Reasoning: An ATM Nifty option at delta ~0.50 moves approximately
           50–65% of the spot price move. 0.60 is used as a
           conservative proxy.
```

**Example:**
```
Spot_ATR = 45 points
Option_ATR = 45 × 0.60 = 27 points
```

### Step 2: Stop-Loss and Target in Premium Points

```
SL_points     = 1.2 × Option_ATR
Target_points = 2.0 × Option_ATR
```

**Example:**
```
Option_ATR = 27
SL_points     = 1.2 × 27 = 32.4 pts
Target_points = 2.0 × 27 = 54.0 pts
```

### Step 3: Execution Cost Deduction

```
Execution_Cost = (Slippage_per_side × 2) + Spread_cost
               = (0.50 × 2) + 1.00
               = 2.00 pts per trade (entry + exit combined)

Net_Gain = Target_points - Execution_Cost  = 54.0 - 2.0 = 52.0
Net_Loss = SL_points     + Execution_Cost  = 32.4 + 2.0 = 34.4
```

### Step 4: Risk:Reward Validation

```
RR_ratio = Net_Gain / Net_Loss

RR_ratio = 52.0 / 34.4 = 1.51

Minimum required: 1.5
Result: ACCEPTED (1.51 >= 1.5)
```

If RR < 1.5, the trade is rejected and the signal is demoted to NO_TRADE with the reason logged.

### Step 5: Premium-Based SL and Target Prices

```
SL_price     = Entry_Premium - SL_points
Target_price = Entry_Premium + Target_points
```

**Example with entry premium of 150:**
```
SL_price     = 150 - 32.4 = 117.60
Target_price = 150 + 54.0 = 204.00
```

### Step 6: Position Sizing

```
Risk_per_lot   = SL_points × Lot_Size
               = 32.4 × 25 = 810 Rs

Max lots = Floor(Fixed_Risk_Per_Trade / Risk_per_lot)
         = Floor(1000 / 810) = 1 lot

Capped at: max(1, min(result, 4 lots))
```

**Fixed risk per trade** is set to Rs 1,000. This means the maximum loss on any single trade will not exceed Rs 1,000 (before slippage/spread).

### Step 7: Daily Guardrails

Before any trade is executed, two guardrails are checked:

```
Guardrail 1: Daily Loss Limit
    If |total_daily_loss| >= Rs 3,000:
        BLOCK all new trades for the session

Guardrail 2: Consecutive Loss Limit
    If consecutive_losses >= 3:
        BLOCK all new trades (pause trading)
```

These protect against a bad trading day turning into a catastrophic loss.

---

## 12. Complete Worked Example

**Market situation at 11:15 AM IST:**

```
Nifty spot:   22,500
EMA(9):       22,480
EMA(21):      22,450
VWAP:         22,370
Session High: 22,520
Session Low:  22,350
ATR:          45
Momentum:     +28 pts (price 28 pts higher than 5 min ago)

Volume:       Current candle = 180,000 lots
              20-candle avg  = 72,000 lots
              Relative Vol   = 2.5x → SPIKE
              Candle: O=22,460, H=22,510, L=22,450, C=22,495
              Body = 35 pts, Range = 60 pts, Body_ratio = 0.583 → STRONG_BULLISH

Options:
  PCR = 1.38
  Dominant OI Buildup = LONG_BUILD_UP
  OI Support    = 22,400
  OI Resistance = 22,600

Last 2 candle closes: 22,490 and 22,495 (both above session high 22,480? No, 22,520 is session high)
  Actually: session high = 22,520, last close = 22,495 (still below)

Regime: TRENDING_UP (ATR expanding, 7/10 bullish candles, range expanding)
```

**Scoring:**

```
CATEGORY 1 — Price Action (cap 30)
  EMA: price(22,500) > EMA9(22,480) > EMA21(22,450)  → +15 bull
  VWAP: dist = (22,500 - 22,370)/22,370 × 100 = +0.581% → well above → +12 bull
  Momentum: +28 > 15 AND EMA already bullish → +3 bull
  Raw bull = 30, Bear = 0
  After cap: Bull = 30, Bear = 0

CATEGORY 2 — Volume (cap 20)
  Spike: 2.5x → YES, Candle: STRONG_BULLISH (body_ratio 0.583, decisive)
  pts = min(20, 10 + (2.5 - 2.0) × 2.5) = min(20, 11.25) = 11.25
  Bull = 11.25, Bear = 0

CATEGORY 3 — Structure (cap 25)
  OI Support at 22,400: dist = (22,500 - 22,400)/22,400 × 100 = +0.446% (just outside 0.40%)
    → No score (outside zone)
  OI Resistance at 22,600: dist = (22,600 - 22,500)/22,600 × 100 = +0.443%
    → Within 0.44% below resistance → bearish? No, +0.443% is just outside 0.40%
    → No score for resistance proximity
  Session breakout: price 22,500 vs session high 22,520 → not broken yet
    → No breakout score
  Structure Bull = 0, Bear = 0

CATEGORY 4 — Options (cap 20)
  PCR = 1.38 > 1.30 → +10 bull
  OI Buildup = LONG_BUILD_UP → +10 bull
  Bull = 20, Bear = 0

CATEGORY 5 — Regime (cap 5)
  TRENDING_UP → +5 bull
  Bull = 5, Bear = 0

CANDLE PENALTY:
  STRONG_BULLISH candle → penalty = 1.0 (no reduction)

TOTALS:
  Total_Bull = 30 + 11.25 + 0 + 20 + 5 = 66.25
  Total_Bear = 0
  After penalty: Bull = 66.25, Bear = 0
```

**Hard filters:**

```
Session: MORNING (11:15 AM) → threshold = 60 ✓
DOJI/Indecisive: NO (STRONG_BULLISH) ✓
ATR: 45, within 0–300 ✓
PCR: 1.38, not zero ✓
Price: 22,500, within 10,000–35,000 ✓
Sideways mismatch: regime is TRENDING_UP, not SIDEWAYS ✓

All filters PASSED
```

**Conflict detection:**

```
Conflict A: PA_bull(30) >= 15 AND options_bear(0) >= 10? → NO
Conflict B: PA_bear(0) >= 15? → NO
Conflict C: SIDEWAYS? → NO (TRENDING_UP)
Conflict D: Volume bullish (11.25 bull, 0 bear). PA_bear(0) > PA_bull(30) + 8? → NO

No conflicts detected
```

**Decision:**

```
Threshold = 60 (MORNING session, TRENDING_UP)
Bull_dominates = (66.25 >= 60) AND (66.25 >= 0 × 1.5) → TRUE AND TRUE → TRUE
Bear_dominates = (0 >= 60) → FALSE

Signal = BUY_CE
Signal_Strength = 66.25
Setup_Quality = WEAK (66.25 - 60 = 6.25, which is < 10)
```

**Risk plan:**

```
Option_ATR = 45 × 0.60 = 27 pts
SL_pts     = 1.2 × 27 = 32.4 pts
Target_pts = 2.0 × 27 = 54.0 pts
Exec_cost  = 2.0 pts

Net_gain = 54.0 - 2.0 = 52.0
Net_loss = 32.4 + 2.0 = 34.4
RR       = 52.0 / 34.4 = 1.51 → ACCEPTED

Assume entry premium = 150:
  SL_price     = 150 - 32.4 = 117.60
  Target_price = 150 + 54.0 = 204.00

Risk_per_lot = 32.4 × 25 = 810 Rs
Lots = floor(1000/810) = 1 lot
Total risk = Rs 810
```

**Final output:**

```json
{
  "signal": "BUY_CE",
  "signal_strength": 66.25,
  "setup_quality": "WEAK",
  "market_regime": "TRENDING_UP",
  "session_window": "MORNING",
  "category_scores": {
    "price_action":  {"bull": 30,    "bear": 0, "cap": 30},
    "volume":        {"bull": 11.25, "bear": 0, "cap": 20},
    "structure":     {"bull": 0,     "bear": 0, "cap": 25},
    "options":       {"bull": 20,    "bear": 0, "cap": 20},
    "regime_session":{"bull": 5,     "bear": 0, "cap":  5}
  },
  "risk_plan": {
    "entry_premium":     150.00,
    "stop_loss_premium": 117.60,
    "target_premium":    204.00,
    "sl_points":         32.4,
    "target_points":     54.0,
    "rr_ratio":          1.51,
    "lots":              1,
    "total_risk":        810.00
  }
}
```

---

## 13. Signal Output Structure

Every API call to `GET /api/signals/current` returns:

```json
{
  "signal":           "BUY_CE | BUY_PE | NO_TRADE",
  "direction":        "UP | DOWN | SIDEWAYS",
  "trade_type":       "INTRADAY | POSITIONAL",
  "signal_strength":  0-100,
  "setup_quality":    "STRONG | MODERATE | WEAK | INVALID",
  "confidence":       "same as signal_strength (backward-compat, NOT a win probability)",

  "market_regime":    "TRENDING_UP | TRENDING_DOWN | SIDEWAYS | UNKNOWN",
  "session_window":   "OPENING | MORNING | AFTERNOON | CLOSING | CLOSED",

  "category_scores": {
    "price_action":   {"bull": float, "bear": float, "cap": 30},
    "volume":         {"bull": float, "bear": float, "cap": 20},
    "structure":      {"bull": float, "bear": float, "cap": 25},
    "options":        {"bull": float, "bear": float, "cap": 20},
    "regime_session": {"bull": float, "bear": float, "cap": 5}
  },

  "explanation": {
    "bullish_reasons": ["list of reasons contributing to bull score"],
    "bearish_reasons": ["list of reasons contributing to bear score"],
    "neutral_notes":   ["observations that don't contribute to either side"],
    "blockers":        ["reasons why a trade was blocked"],
    "why_not_trade":   "primary reason if NO_TRADE",
    "final_reasoning": "summary string"
  },

  "risk_plan": {
    "entry_premium":      float,
    "stop_loss_premium":  float,
    "target_premium":     float,
    "sl_points":          float,
    "target_points":      float,
    "rr_ratio":           float,
    "lots":               int,
    "lot_size":           25,
    "total_qty":          int,
    "total_risk":         float
  },

  "candle_quality":  "candle type of last bar",
  "regime_info":     { "regime": ..., "regime_strength": ..., "atr_state": ... },
  "market_state":    { "price": ..., "vwap": ..., "ema_9": ..., "ema_21": ..., "atr": ... },
  "options_summary": { "pcr": ..., "max_pain": ..., "oi_support": ..., "oi_resistance": ... }
}
```

---

## 14. Session Windows & Thresholds

| Window | Time (IST) | Min Score | Notes |
|---|---|---|---|
| OPENING | 9:15 – 9:30 | **75** | High noise. Strict filter. |
| MORNING | 9:30 – 13:00 | **60** | Prime trading window. Normal thresholds. |
| AFTERNOON | 13:00 – 14:30 | **65** | Mixed liquidity. Slightly tighter. |
| CLOSING | 14:30 – 15:30 | **62** | Reversal-sensitive. Watch for direction changes. |
| CLOSED | After 15:30 | **N/A** | System returns NO_TRADE immediately. |

**SIDEWAYS regime override:** Adds +15 pts to the effective threshold in any session.

Example: SIDEWAYS + AFTERNOON = max(65, 75) = **75 pts required**

---

*Document generated from source code analysis — March 2026.*
*All formulas are directly derived from the live codebase. No approximations.*
