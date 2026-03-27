# Nifty Trading Pipeline: Prediction & Calculation Guide

This document explains the technical calculations, predictive logic, and scoring systems used to generate trading signals and how they are represented in the user interface.

---

## 1. Technical Indicators (Market Pulse)

The system computes real-time indicators from 1-minute OHLCV candles (preferring Nifty Futures for volume accuracy).

| Indicator | Calculation / Formula | Purpose |
| :--- | :--- | :--- |
| **EMA 9 & 21** | Exponential Moving Average over 9 and 21 periods. | Identifies short-term trend direction and "stacks" (Bullish: Price > 9 > 21). |
| **VWAP** | `SUM(Typical Price * Volume) / SUM(Volume)` | Volume Weighted Average Price. Acts as the "Fair Value" of the day. |
| **ATR (14)** | Average True Range (14 periods). | Measures "True Range" volatility to set dynamic Stop Loss and Take Profit levels. |
| **Momentum** | `Price(Current) - Price(5 candles ago)` | Measures the velocity of price movement to confirm a trend's strength. |
| **Volume Spike** | `Current Volume / Average Volume (Last 20)` | Detects institutional activity. A spike > 2x confirms valid breakouts. |

---

## 2. Options Analytics (Sentiment & Liquidity)

The system analyzes the Nifty Option Chain (ATM ± 10 strikes) to gauge the positioning of big players (Option Writers).

| Metric | Calculation | Interpretation |
| :--- | :--- | :--- |
| **PCR (Ratio)** | `Total Put Open Interest / Total Call Open Interest` | **PCR > 1.3**: Strongly Bullish (Support); **PCR < 0.6**: Strongly Bearish (Resistance). |
| **Max Pain** | The strike where option buyers (retail) lose the most money. | The price magnet where Nifty often settles at expiry. |
| **OI Support** | Strike price with the highest **Put Open Interest**. | Acts as a hard floor for price movement. |
| **OI Resistance** | Strike price with the highest **Call Open Interest**. | Acts as a hard ceiling for price movement. |
| **OI Buildup** | Relationship between Price Change and OI Change. | Identifies if positions are being added (Build Up) or removed (Covering). |

### OI Buildup Patterns
*   **LONG BUILD UP**: Price ↑ + OI ↑ (New Longs entering)
*   **SHORT BUILD UP**: Price ↓ + OI ↑ (New Shorts entering)
*   **SHORT COVERING**: Price ↑ + OI ↓ (Shorts exiting in panic)
*   **LONG UNWINDING**: Price ↓ + OI ↓ (Longs exiting/profit booking)

---

## 3. The Strategy Scoring System (100-Point Rule)

Instead of a simple "Yes/No", the app uses a **Category Scoring System** to evaluate setup quality. Every signal must cross a **60-point threshold** to trigger.

| Category | Max Score | Key Rules |
| :--- | :--- | :--- |
| **Price Action** | 30 pts | EMA alignment (15 pts) + VWAP proximity (12 pts) + Momentum (3 pts). |
| **Volume** | 20 pts | Directional spike alignment with candle body decisive-ness. |
| **Structure** | 25 pts | OI level proximity (10 pts) + 2-candle breakout confirmation (15 pts). |
| **Options** | 20 pts | PCR zone alignment (10 pts) + Buildup pattern confirmation (10 pts). |
| **Regime** | 5 pts | Bonus points for alignment with the dominant market trend. |

### Decision Logic
*   **Trigger**: Winning side score (Bull vs Bear) must be **≥ 60**.
*   **Dominance**: The winning side must be at least **1.5x stronger** than the losing side.
*   **Extra Thresh**: During the **Opening Window** (09:15–09:30) or **Sideways regimes**, the threshold increases to **75** to avoid noise.

---

## 4. UI Representation (The Dashboard)

The backend simplifies these complex numbers into readable statuses for the **Signal Explanation** panel:

| UI Label | Logic Source | Display Example |
| :--- | :--- | :--- |
| **EMA Status** | EMA 9/21 alignment | "Strong Bullish (Price > 9 > 21)" |
| **VWAP Status** | Price vs VWAP | "Bullish (Above 25430)" |
| **OI Status** | Options Engine | "Long Build Up" / "Short Covering" |
| **Momentum** | 5-period change | "Bullish (+15.4)" |
| **Confidence** | Total Score (0-100) | "85" (This is NOT a win %, it is setup quality) |
| **Setup Quality** | Score Gap from Min | **STRONG** (Score > 80), **MODERATE**, **WEAK** |
| **S / R** | Session High / Low | "25400 / 25550" |

---

## 5. Risk Management (The Filter)

Even a high-scoring signal is blocked if it fails the **Risk Engine** check:
1.  **Risk:Reward (R:R)**: If the distance to the next Resistance (Target) is less than 1.5x the Stop Loss (ATR-based), the trade is rejected.
2.  **Candle Quality**: Signals triggered on "Doji" or "Indecisive" candles are penalized or blocked.
3.  **Conflict Detector**: If Price Action is Bullish but Options Sentiment is Bearish, the trade is vetoed as "Ambiguous Conflict".
