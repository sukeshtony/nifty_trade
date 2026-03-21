# Nifty Trading Platform — Complete API Documentation

## PHASE 2 — API INVENTORY TABLE

| API Name | File Location | Route / Endpoint | HTTP Method | Purpose | Main Internal Function/Handler | Related Services | External Integrations | Authentication Required? | Status |
|---|---|---|---|---|---|---|---|---|---|
| Get Nifty Price | `routers/market.py` | `/api/market/nifty-price` | GET | Returns real-time LTP and basic indicators for Nifty | `get_nifty_price` | `market_state_manager`, `market_service` | Angel One Smart API / WebSocket | No | Complete |
| Get Market Overview | `routers/market.py` | `/api/market/overview` | GET | Returns Nifty and VIX full market data | `get_market_overview` | `market_service` | Angel One Smart API | No | Complete |
| Get Options Analysis | `routers/options.py` | `/api/options/analysis` | GET | Returns analyzed option chain data (PCR, Max Pain, standard deviation) | `get_options_analysis` | `options_engine`, `market_service`, `market_state_manager` | Angel One Smart API | No | Complete |
| Get Current Signal | `routers/signals.py` | `/api/signals/current` | GET | The core trading engine: computes signals based on indicators, PA, options data, and risk. | `get_current_signal` | `strategy_engine`, `risk_engine`, `regime_detector`, `indicator_engine`, `options_engine`, `candle_analyzer` | None (reads entirely from cache/local state) | No | Complete |
| Get Signal History | `routers/signals.py` | `/api/signals/history` | GET | Fetches recently triggered and recorded signals from the database. | `get_signal_history` | None | None (Database) | No | Complete |
| Create Trade | `routers/trades.py` | `/api/trades` | POST | Records a newly executed manual or automated trade. | `create_trade` | `trade_service` | None (Database) | No | Complete |
| Close Trade | `routers/trades.py` | `/api/trades/{trade_id}/close` | PUT | Closes an open trade and calculates PnL. | `close_trade` | `trade_service` | None (Database) | No | Complete |
| Get Active Trades | `routers/trades.py` | `/api/trades/active` | GET | Retrieves a list of all currently open trades. | `get_active_trades` | `trade_service` | None (Database) | No | Complete |
| Get Trade History | `routers/trades.py` | `/api/trades/history` | GET | Retrieves a list of closed trades. | `get_trade_history` | `trade_service` | None (Database) | No | Complete |
| Get Trade Summary | `routers/trades.py` | `/api/trades/summary` | GET | Calculates win rate, total PnL, and ROI on live trades. | `get_trade_summary` | `trade_service` | None (Database) | No | Complete |
| Init Paper Account | `routers/paper_trading.py`| `/paper/account/init` | POST | Sets or resets paper money account balance. | `initialize_account` | `paper_trade_service` | None (Database) | No | Complete |
| Get Paper Account | `routers/paper_trading.py`| `/paper/account` | GET | Returns paper money balance and total PnL. | `get_account_summary` | `paper_trade_service` | None (Database) | No | Complete |
| Place Paper Trade | `routers/paper_trading.py`| `/paper/trade/place` | POST | Places a simulated trade. | `place_paper_trade` | `paper_trade_service` | None (Database) | No | Complete |
| Close Paper Trade | `routers/paper_trading.py`| `/paper/trade/close/{trade_id}` | POST | Closes a simulated trade and updates balance. | `close_paper_trade` | `paper_trade_service` | None (Database) | No | Complete |
| Active Paper Trades | `routers/paper_trading.py`| `/paper/trades/active` | GET | Retrieves a list of open paper trades. | `get_active_paper_trades` | `paper_trade_service` | None (Database) | No | Complete |
| Paper Trade History | `routers/paper_trading.py`| `/paper/trades/history` | GET | Retrieves a list of closed paper trades. | `get_paper_trade_history`| `paper_trade_service` | None (Database) | No | Complete |

*(Note on WebSocket)*: There is no incoming WebSocket API layer for the frontend right now. The backend connects to an Angel One WebSocket running in a background thread to update the internal state, and frontend polls via REST.

---

## PHASE 3 — DETAILED API DOCUMENTATION

---

### API: Get Nifty Price

#### 1. Endpoint Overview
- **Route:** `/api/market/nifty-price`
- **Method:** GET
- **Module/File:** `backend/routers/market.py`
- **Handler Function:** `get_nifty_price`
- **Purpose in simple words:** Fetches the real-time Last Traded Price (LTP) and some technical values (VWAP, session highs/lows) of Nifty so the frontend can display the current market moving.

#### 2. Business Requirement
- The dashboard needs a live ticker showing the exact current Nifty price and daily change.
- Called every 2-3 seconds by the frontend continuously.

#### 3. Request Details
- **Path parameters:** None
- **Query parameters:** None
- **Headers:** Just standard CORS. No auth mechanism.
- **Request body:** None
- **Required fields:** None
- **Optional fields:** None
- **Example request:** `GET /api/market/nifty-price`

#### 4. Response Details
- **Success response (200 OK):**
- **Error response:** Returns empty structure with error message or zero values if broker down.
- **Response fields explained:**
  - `ltp`: Last traded price of Nifty Index.
  - `change`: Points gained/lost since yesterday close.
  - `changePct`: Percentage gain/loss.
  - `vwap`, `ema_9`, `ema_21`, `session_high`, `session_low`: Current technical values.
- **Example response:**
  ```json
  {
      "ltp": 22450.50,
      "change": 120.30,
      "changePct": 0.54,
      "vwap": 22410.00,
      "ema_9": 22435.10,
      "ema_21": 22420.50,
      "session_high": 22500.00,
      "session_low": 22350.00
  }
  ```

#### 5. Internal Flow
1. Receives GET request.
2. Checks `market_state_manager.get_state("NIFTY")`. This state is continuously updated in memory by an external background thread running the Angel One WebSocket listening for ticks.
3. If not found in live state, it checks a cached full dictionary (`cache.get("market_full:NIFTY")`).
4. If cache empty, it actively hits Angel One API using `market_service.get_full_market_data("NIFTY")` as a last resort.
5. Transforms values into a flat JSON and returns.

#### 6. Methods and Functions Used
- `market_state_manager.get_state` (in `services/market_state.py`): In-memory dictionary tracking live prices from WS.
- `market_service.get_full_market_data` (in `services/market_data_service.py`): REST call to Angel One.

#### 7. Validations / Security / Error Handling
- **Auth checks:** NONE. Open API.
- **Error Handling:** Has fallbacks (Memory -> Cache -> API). If everything fails, returns dict with `{"ltp": 0, "error": "No data..."}`. Never crashes.

#### 8. Side Effects
- Uses Angel One Smart API purely to read data (if cache expires). Does not mutate the DB.

#### 9. Dependency Mapping
- Relies heavily on `market_service` running in the background. If Angel One is disconnected, this route will serve stale cache. Configured by `ANGEL_API_KEY` etc.

#### 10. Requirement Fit Analysis
- Correctly optimized. Hitting an external API every 2 seconds will ban the server, so it uses internal memory updated by WebSocket. Excellent design for this requirement.

#### 11. Beginner Explanation
When the frontend wants to know the latest price of Nifty, it constantly hits this route. To avoid getting banned by the broker for asking too fast, this route just checks our own internal memory (RAM) which is silently being kept up-to-date in the background.

---

### API: Get Current Signal

#### 1. Endpoint Overview
- **Route:** `/api/signals/current`
- **Method:** GET
- **Module/File:** `backend/routers/signals.py`
- **Handler Function:** `get_current_signal`
- **Purpose in simple words:** The absolute "brain" of the application. It looks at the price, the options data, the indicators, and decides whether the user should Buy a Call (BUY_CE), Buy a Put (BUY_PE), or Wait (NO_TRADE). 

#### 2. Business Requirement
- The core offering of this project is auto-calculating trade signals based on logic like VWAP, EMAs, Support/Resistance, and Option Chain.
- The UI calls this to tell the user "We detected a strong bullish trend, Buy CE with Stop Loss X and Target Y".

#### 3. Request Details
- **Methods:** GET
- **None required** (Relies entirely on server's internal state)

#### 4. Response Details
- **Response fields explained:**
  - `signal`: "BUY_CE", "BUY_PE", or "NO_TRADE"
  - `direction`: "UP", "DOWN", or "SIDEWAYS"
  - `trade_type`: "INTRADAY" or "POSITIONAL"
  - `signal_strength`: 0 to 100 pointing out how strong the setup is based on 5 parameters.
  - `setup_quality`: Label like "STRONG" or "INVALID"
  - `explanation`: Detailed reasons explaining WHY this signal was generated.
  - `risk_plan`: Target and Stop Loss points!
  - `market_state` & `options_summary`: Data context.

#### 5. Internal Flow
1. Grabs live state from `market_state_manager` (from RAM).
2. Grabs recent 1-minute candle history from the Cache. (If missing, fetches from Angel One).
3. Computes technical indicators (EMA, VWAP, ATR, S/R, volume spikes) using `indicator_engine.compute_all_indicators()`.
4. Grabs option chain analysis from the Cache (PCR, max pain, etc) -> `options_engine`.
5. Passes the candles to `regime_detector.detect()` to understand if we are in trending or sideways markets.
6. Passes the last candle to `candle_analyzer.analyze_last_candle()` to find DOJI or Marubozu bars.
7. Calls `strategy_engine.generate_signal()` -> This is a massive rule-based engine that assigns points (out of 100) based on 5 categories (Price Action, Volume, Structure, Options, Session).
8. If the strategy spits out a BUY signal, the `risk_engine` takes over to see if a Stop Loss vs Target trade makes mathematical sense (1.5 R:R Ratio). It computes SL and Target.
9. Calls `_maybe_store_signal()` to secretly record this signal change into the database.
10. Returns massive payload to frontend.

#### 6. Methods and Functions Used
- `compute_all_indicators()` (`services/indicator_engine.py`): Heavy Pandas math to calculate EMA, VWAP, Support, Resistance, Volume Spikes.
- `options_engine.analyze()` (`services/options_engine.py`): Finds PCR, Max Pain, and Call/Put Buildups.
- `strategy_engine.generate_signal()` (`services/strategy_engine.py`): Houses all trading rules (e.g. if price > VWAP and EMA9 > EMA21 -> Add 15 Bullish points).
- `risk_engine.calculate_trade_plan()` (`services/risk_engine.py`): Maps ATR to points, factors slippage, tells exactly where to put Stop Loss.

#### 7. Validations / Security / Error Handling
- No auth check.
- High level of data-validity checks (e.g., handles cases where ATR is somehow 300, or Nifty price drops below 10,000, filtering out bad data).

#### 8. Side Effects
- **Database Write**: `_maybe_store_signal()` checks if the signal changed since last time, or 60 seconds passed. If yes, writes a new `Signal` row to the database.

#### 9. Requirement Fit Analysis
- Excellent execution of a "Category-based scoring algorithm". It perfectly solves the requirement.

#### 10. Beginner Explanation
This API is a giant "Checklist" bot. Without asking for user input, it silently reads current prices, past 20 minutes of history, and the options chain. It fills out a 100-point checklist. If "bullish" score > 60, it says BUY CE. It prevents bad trades by refusing to signal if Stop Loss is too wide, or if the market is too slow.

---

### APIs: Trade & Paper Trade Service (Grouped)

(Applies identically to `/api/trades/*` and `/paper/*`)

#### 1. Endpoint Overview
- **Routes:** `POST /api/trades`, `PUT /api/trades/{trade_id}/close`, `GET /api/trades/history` (and their paper equivalents)
- **Method:** POST / PUT / GET
- **Handler module:** `routers/trades.py` & `routers/paper_trading.py`
- **Purpose**: Creates an open trade log based on current price. Later on, closes the trade, subtracts broker charges, records the total PNL (profit and loss), and adjusts account balance (for paper trades).

#### 2. Business Requirement
Allow users to click "Paper Trade" from a generated signal to track how the signal performs without paying real money, or to log a trade taken in their real broker account.

#### 3. Request Details (Example: POST Place Trade)
- **Request body:**
  ```json
  {
    "symbol": "NIFTY",
    "strike": 22500,
    "option_type": "CE",
    "entry_price": 105.5,
    "qty": 50,
    "trade_type": "INTRADAY"
  }
  ```

#### 4. Response Details (Example: PUT Close Trade)
- **Response fields:**
  ```json
  {
     "status": "success",
     "entry_price": 105.5,
     "exit_price": 120.0,
     "pnl": 725.0,
     "charges": 40.0,
     "net_pnl": 685.0
  }
  ```

#### 5. Internal Flow
- For `/paper/trade/place`:
  1. Calls `paper_trade_service.place_paper_trade()`.
  2. Ensures paper account exists.
  3. Inserts `PaperTrade` record with `status='OPEN'`.
- For `/paper/trade/close/{id}`:
  1. Finds open trade. Updates exit price.
  2. Math: `(exit_price - entry_price) * qty` = Gross PNL.
  3. Math: Subtracts hypothetical charges based on lots.
  4. Updates `PaperAccount.balance`. Sets Trade to `CLOSED`.

#### 6. Methods and Functions Used
- `trade_service.py` / `paper_trade_service.py`: Basic DB CRUD wrappers. No complex logic.

#### 7. Side Effects
- Mutates Database (`trades`, `paper_trades`, `paper_account` tables).

#### 8. Requirement Fit Analysis
- Does what it says. Very clean, separated logic for real vs paper trades.

---

## PHASE 4 — CROSS-API ARCHITECTURE SUMMARY

### A. End-to-End Architecture Summary
- **Framework:** Python FastAPI.
- **Boot Sequence:** On server start (`main.py` lifespan), the backend starts **two background threads**:
  1. A thread running an Angel One WebSocket to receive live LTP and push it to a global dictionary `market_state_manager` and update OHLC ticks.
  2. A thread running every 60 seconds to download historical 1-minute candles and the full Option Chain, dumping the results to an in-memory `cache` (`utils.cache`).
- **Frontend Interaction:** The Frontend polling mechanism hits REST endpoints. 
  - To show UI values -> `/api/market/nifty-price` (returns RAM data instantly).
  - To show "BUY/SELL" recommendations -> `/api/signals/current`. This route takes the data living in RAM, runs giant mathematical logic graphs across it (`strategy_engine`), and returns an immediate response.
- **Database:** SQLite/Postgres using SQLAlchemy (`models.py`). Used purely for tracking history (Logs of signals generated, paper trades performed). Not used for high-frequency price data.

### B. Shared Components
- **`cache` (utils/cache.py):** Likely a singleton dictionary with TTLs. Every service reads and writes to it. E.g., options engine, candle fetching, signaling.
- **`market_service` (services/market_data_service.py):** Main data pipeline. Contains `login()`, Smart API calls, and WebSockets.
- **`market_state_manager`:** RAM data structure for the absolute latest price (changes multiple times a second).
- **Engines Pipeline:** `strategy_engine` requires output from `indicator_engine`, `options_engine`, `regime_detector`, and `candle_analyzer`.

### C. External Integrations
- **Angel One Smart API (SmartConnect / SmartWebSocketV2):**
  - Dependency: Real-time price and options chain via authorized REST and WebSockets.
  - Required Environment Variables: `ANGEL_API_KEY`, `ANGEL_CLIENT_ID`, `ANGEL_PASSWORD`, `ANGEL_TOTP_SECRET`.
  - Frequency: WebSocket runs constantly. Optional REST routes are queried if cache is missing. 

### D. Risk / Confusion Areas
1. **Thread Safety & Missing Async:** The websocket thread writes to a normal python dictionary (`market_state_manager.update_tick`). The API routes are synchronous `def` functions, not async, so FastAPI runs them in a ThreadPool. The cache uses basic dictionary logic. This can lead to race conditions under heavy load. The system isn't strictly async (`await`), meaning lots of internal blocking happens during DB writes or DB reads.
2. **"Real" vs "Paper" code duplication:** `trade_service.py` and `paper_trade_service.py` are basically identical copies of the exact same code, only one touches `trades` table and one touches `paper_trades`. 
3. **No Authentication:** None of the APIs (`/api/signals`, `/api/trades`) have JWT, API Keys, or user tokens. The entire backend relies purely on CORS. If exposed to the internet, anyone can dump trades into the database or read the signals. Total absence of multi-tenancy.
4. **Heavy Route Processing:** `/api/signals/current` calls `compute_all_indicators()` and `regime_detector.detect()` on EVERY GET request. If the frontend polls this every 2 seconds, pandas is recalculating 20 EMA, VWAP, and Regimes every 2 seconds on the main thread loop. This should ideally be calculated once every 60 seconds in the background thread.

### E. Suggested Documentation Improvements
- Missing docstrings in `candle_analyzer.py` and `indicator_engine.py` pandas manipulation. 
- Needs an architecture diagram showing the relationship between the background threads, the cache, and the active polling routes.

---

## PHASE 5 — OPEN QUESTIONS FOR A NEW DEVELOPER

1. **How is the system deployed?** Currently, it relies on local caching and standard dictionary state (`cache = {}`, `market_state_manager`). If we run multiple load-balanced workers (e.g., `uvicorn main:app --workers 4`), state will be duplicated/lost across workers. How can we migrate the caching to Redis?
2. **Why is `/api/signals/current` calculating Pandas logic on demand?** Every GET request spins up pandas datasets to rebuild indicators. Should we move the `strategy_engine` to be evaluated constantly in the background thread, and have `/api/signals/current` just return a pre-computed JSON blob?
3. **Who is allowed to place trades?** `routers/trades.py` lacks User IDs. If multiple users use this software, their paper trades will merge into one giant account. Does this app intend to serve one trader entirely? If so, why build a decoupled Web API?
4. **How do we handle Angel One disconnects?** Angel one drops websockets daily. Does the `start_websocket` function have an auto-reconnect logic if `on_close` triggers aggressively? 
5. **How robust is the Totp authentication?** The system passes `pyotp.TOTP(secret).now()`. Angel One sometimes invalidates sessions; what triggers a re-login flow if a REST request suddenly returns "Invalid Token"?
