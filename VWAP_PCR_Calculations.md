# VWAP & PCR — How Calculations Work in This Application

A deep-dive into exactly how **VWAP** (Volume Weighted Average Price) and **PCR** (Put-Call Ratio) are
computed, updated, and displayed as signals in the Nifty Trading platform.

---

## 1. VWAP — Volume Weighted Average Price

### What granularity? → **Intraday (Per-Session, Per-Minute Accumulation)**

VWAP here is a **classic intraday VWAP** — it resets every trading day at 9:15 AM IST and
accumulates tick-by-tick throughout the session. It does **not** use daily bars; it builds up
from 1-minute candles and live WebSocket ticks.

---

### Phase 1 — Seed from History (App Startup)

**File:** `services/market_state.py` → `initialize_from_history()`

When the WebSocket is started (or the app boots), `start_websocket()` fetches the last 5 days
of **1-minute candles** from the Angel One API for **Nifty Futures** (preferred, because futures
carry actual volume data; the cash index candles often have zero volume).

```
candles = get_candle_data("NIFTY_FUT", interval="ONE_MINUTE")
market_state_manager.initialize_from_history("NIFTY", candles)
```

Inside `initialize_from_history()`, only **today's candles** (matched by `YYYY-MM-DD`) are
used for the VWAP seed:

```python
vwap_candles = [c for c in candles if today_str in str(c[0])]

tv = 0   # cumulative (typical_price × volume)
v  = 0   # cumulative volume

for c in vwap_candles:
    high  = c[2]
    low   = c[3]
    close = c[4]
    vol   = c[5]

    typical_price = (high + low + close) / 3   # TP
    tv += typical_price * vol
    v  += vol

vwap = tv / v   # if v > 0
```

| Candle field | Index | Meaning            |
|-------------|-------|--------------------|
| Timestamp   | `[0]` | Used to filter today |
| Open        | `[1]` | (unused for VWAP)  |
| High        | `[2]` | Used in TP         |
| Low         | `[3]` | Used in TP         |
| Close       | `[4]` | Used in TP         |
| Volume      | `[5]` | Weight             |

> **Typical Price (TP) = (High + Low + Close) / 3**
> **VWAP = Σ(TP × Volume) / Σ(Volume)**

The running totals are stored in state:
- `state["typical_price_volume"]` = Σ(TP × Volume) accumulated so far
- `state["volume_today"]` = Σ(Volume) accumulated so far
- `state["vwap"]` = current ratio

---

### Phase 2 — Live Tick Updates (During Market Hours)

**File:** `services/market_state.py` → `update_tick()`

Every WebSocket tick from Angel One (for NIFTY or NIFTY_FUT) calls `update_tick()`, which
**incrementally** updates VWAP in O(1) time (no recalculation of history):

```python
def update_tick(self, symbol, price, volume, high, low):
    if volume > 0 and high is not None and low is not None:
        tp = (high + low + price) / 3           # price = ltp (acts as close)
        state["typical_price_volume"] += tp * volume
        state["volume_today"]         += volume
        state["vwap"] = round(
            state["typical_price_volume"] / state["volume_today"], 2
        )
```

The WebSocket provides prices in **paisa** (integer), divided by 100:
```python
price = float(raw_ltp) / 100.0
high  = float(raw_high) / 100.0
low   = float(raw_low)  / 100.0
```

> **VWAP resets to 0 at app startup** and is rebuilt fresh each day. It does NOT persist
> across restarts mid-day unless the history seed candles from today are available.

---

### VWAP Signal Interpretation

**File:** `routers/signals.py`

| VWAP Signal | Condition | Meaning |
|---|---|---|
| `Bullish (Above ₹XXXX)` | `price > vwap` | Market sentiment above day's average cost |
| `Bearish (Below ₹XXXX)` | `price < vwap` | Market is trading below average cost — weakness |
| `N/A (No Volume)` | `vwap == 0` | Not enough volume data (market just opened or futures data unavailable) |

**File:** `services/market_state.py` → `_sync_state_from_indicators()`

The `trend.above_vwap` boolean is also tracked:
```python
state["trend"]["above_vwap"] = state["current_price"] > state["vwap"]
```

This boolean is used by the **Strategy Engine** when scoring bullish/bearish setups.

---

### VWAP Data Flow Summary

```
Angel One Futures Candles (1-min, last 5 days)
         │
         ▼
initialize_from_history()  ──► Seeds VWAP from today's candles only
         │
         ▼
Live WebSocket Ticks (every few seconds)
         │
         ▼
update_tick()  ──► Incrementally adds (TP × Volume) to running totals
         │
         ▼
market_state["vwap"]  ──► Served via GET /api/market/nifty-price
         │
         ▼
Frontend polls /nifty-price every 2–3 seconds → displays live VWAP
```

---

## 2. PCR — Put-Call Ratio

### What granularity? → **Snapshot-Based (Every ~30 seconds per poll)**

PCR is **not per-minute** nor per-day. It is a **point-in-time snapshot** of the current
Open Interest (OI) across the nearest weekly Nifty options expiry. It is refreshed every
time the option chain is fetched (cached for **30 seconds**).

---

### Step 1 — Select the Expiry

**File:** `services/market_data_service.py` → `_get_option_contracts()`

The system picks the **nearest weekly expiry within 7 days**. Weekly options have far more
liquidity and OI than monthly contracts, making PCR more meaningful:

```python
weekly_cutoff = today + timedelta(days=7)
# Selects the first expiry date ≤ 7 days away
# Falls back to the nearest future expiry if no weekly exists
```

---

### Step 2 — Fetch Option Chain (ATM ± 3 Strikes)

**File:** `services/market_data_service.py` → `get_option_chain()`

For performance, only **7 strikes** are fetched (ATM − 3 to ATM + 3, at 50-point intervals):

```python
atm_strike = round(spot / 50) * 50
strikes = [atm_strike + (i * 50) for i in range(-3, 4)]
```

Market data (LTP, OI, Volume) for all CE and PE tokens at these strikes is batch-fetched
via `getMarketData(mode="FULL")` from Angel One.

---

### Step 3 — Calculate PCR

**File:** `services/options_engine.py` → `analyze()`

```python
total_call_oi = sum(row["callOI"] for row in chain_data)
total_put_oi  = sum(row["putOI"]  for row in chain_data)

pcr = round(total_put_oi / total_call_oi, 2)   # if call_oi > 0
```

This is the **OI-based PCR**, calculated over the ATM ± 3 strikes of the nearest weekly expiry.

> **PCR = Total Put OI / Total Call OI**

It is **not** volume-based PCR. It uses `opnInterest` (open interest contracts outstanding).

---

### Step 4 — Interpret PCR

**File:** `services/options_engine.py` → `_interpret_pcr()`

| PCR Value | Interpretation | Market Bias |
|---|---|---|
| `> 1.3` | `STRONGLY_BULLISH` | Heavy put writing → market expects up move |
| `1.0 – 1.3` | `BULLISH` | More puts than calls outstanding |
| `0.7 – 1.0` | `NEUTRAL` | Balanced OI |
| `0.5 – 0.7` | `BEARISH` | More calls being written → downward bias |
| `< 0.5` | `STRONGLY_BEARISH` | Heavy call writing → sellers dominate |

**File:** `routers/signals.py` (quick signal display):

```python
if pcr > 1.1:
    pcr_status = f"Bullish ({pcr})"
elif pcr > 0:
    pcr_status = f"Bearish/Neutral ({pcr})"
else:
    pcr_status = "N/A"
```

> Note: The signal router uses a simplified threshold (`> 1.1`) for its display label,
> while the options engine uses a full 5-level scale for deeper analysis.

---

### OI Change Tracking (Buildup Detection)

**File:** `services/market_data_service.py`

To detect whether OI is building or unwinding, the system stores a **baseline OI per token**
at the first fetch of each day:

```python
if token not in self._oi_baselines:
    self._oi_baselines[token] = current_oi   # first fetch of the day

oi_change = current_oi - self._oi_baselines[token]
```

This enables detection of 4 buildup patterns per strike:

| Price Change | OI Change | Pattern |
|---|---|---|
| ↑ Up | ↑ Increasing | `LONG_BUILD_UP` |
| ↓ Down | ↑ Increasing | `SHORT_BUILD_UP` |
| ↑ Up | ↓ Decreasing | `SHORT_COVERING` |
| ↓ Down | ↓ Decreasing | `LONG_UNWINDING` |

The **dominant buildup** across all strikes is reported as `dominant_buildup` in the options
analysis response.

---

### PCR Data Flow Summary

```
Angel One Instrument Master (downloaded once, cached 12 hrs)
         │
         ▼
_get_option_contracts()  ──► Selects nearest weekly expiry
         │  Builds CE map {strike → token} and PE map {strike → token}
         ▼
get_option_chain()  ──► Fetches ATM ± 3 strikes via getMarketData(FULL)
         │  Extracts callOI, putOI, callLTP, putLTP per strike
         ▼
options_engine.analyze()
         │  PCR = total_put_oi / total_call_oi
         │  Max Pain, OI Support/Resistance, Dominant Buildup
         ▼
Cache for 30 seconds  ──► GET /api/options/analysis
         │
         ▼
Also used by GET /api/signals/current (if cache hit, no re-fetch)
```

---

## 3. Quick Reference — Frequencies & Reset Behaviour

| Indicator | Granularity | Resets | Data Source |
|---|---|---|---|
| **VWAP** | Continuous (per-tick) | Daily at session start | Nifty Futures 1-min candles + WebSocket ticks |
| **PCR** | Every ~30 seconds | No daily reset (OI baseline resets daily) | Nifty weekly options OI via REST API |
| **EMA 9 / EMA 21** | Per-tick (incremental) | App restart | 1-min close prices |
| **ATR** | Per-tick | App restart | Rolling last 14 true ranges |
| **Momentum** | Per-tick | Rolling 5-tick window | Last 5 close prices |
| **OI Baseline** | First fetch of day | Daily | Angel One instrument master |

---

## 4. Key Design Decisions

1. **VWAP uses Futures volume, not Cash index volume**  
   Nifty Cash index candles from Angel One often return `volume = 0`. Futures candles carry
   real traded volume, making VWAP meaningful. The state is still stored under the `"NIFTY"`
   key so the frontend doesn't need to know the difference.

2. **PCR is ATM-centric (ATM ± 3 strikes)**  
   Fetching the full option chain (hundreds of strikes) would hit Angel One rate limits and
   slow the system. ATM ± 3 strikes contain the majority of active OI and are sufficient
   for intraday signal generation.

3. **VWAP is O(1) per tick**  
   Instead of re-summing all past ticks, the system keeps two running accumulators
   (`typical_price_volume` and `volume_today`). Each tick does exactly one multiplication
   and two additions.

4. **PCR cache is 30 seconds**  
   Option chain REST calls are expensive (rate-limited by Angel One). The 30-second TTL
   means the `/api/signals/current` endpoint and `/api/options/analysis` share the same
   cached result without duplicating API calls.

---

*Generated from source analysis of `services/market_state.py`, `services/market_data_service.py`,
`services/options_engine.py`, and `routers/signals.py`.*
