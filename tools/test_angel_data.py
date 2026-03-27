"""
Angel One Smart API — Data Availability Tester
===============================================
Runs every available REST API call + a 30-second WebSocket capture,
then writes the full results to  tools/angel_one_report.txt

Run from project root:
    cd backend
    .\\venv\\Scripts\\python ..\\tools\\test_angel_data.py
"""

import os
import sys
import json
import time
import pyotp
import threading
import traceback
import requests as req
from datetime import datetime, timedelta
from pathlib import Path

# ── Resolve credentials from backend/.env ─────────────────────────────────────
TOOLS_DIR   = Path(__file__).parent
PROJECT_DIR = TOOLS_DIR.parent
BACKEND_DIR = PROJECT_DIR / "backend"
ENV_FILE    = BACKEND_DIR / ".env"
REPORT_FILE = TOOLS_DIR / "angel_one_report.txt"

# Load .env manually (no dependency on python-dotenv being on PATH)
def _load_env(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())

_load_env(ENV_FILE)

API_KEY     = os.environ.get("ANGEL_API_KEY", "")
CLIENT_ID   = os.environ.get("ANGEL_CLIENT_ID", "")
PASSWORD    = os.environ.get("ANGEL_PASSWORD", "")
TOTP_SECRET = os.environ.get("ANGEL_TOTP_SECRET", "")

# ── Angel One SDK ──────────────────────────────────────────────────────────────
sys.path.insert(0, str(BACKEND_DIR / "venv" / "Lib" / "site-packages"))
try:
    from SmartApi import SmartConnect
    from SmartApi.smartWebSocketV2 import SmartWebSocketV2
except ImportError:
    print("ERROR: SmartApi not found. Run from backend venv.")
    sys.exit(1)

# ── Tokens ─────────────────────────────────────────────────────────────────────
# NSE cash index (no traded volume — this is the core question we're testing)
NIFTY_TOKEN    = "99926000"
NIFTY_EXCHANGE = "NSE"

INDIAVIX_TOKEN    = "99926009"   # Correct India VIX (99926004 = Nifty 500)
INDIAVIX_EXCHANGE = "NSE"

# Sensex for comparison
SENSEX_TOKEN    = "99919000"
SENSEX_EXCHANGE = "BSE"

# ── Report writer ──────────────────────────────────────────────────────────────
_lines = []

def _h(title: str):
    sep = "=" * 70
    _log(f"\n{sep}\n  {title}\n{sep}")

def _s(title: str):
    _log(f"\n--- {title} ---")

def _log(msg: str = ""):
    ts  = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}]  {msg}" if msg.strip() else msg
    print(line)
    _lines.append(line)

def _dump(label: str, obj):
    _log(f"{label}:")
    if obj is None:
        _log("  <None>")
        return
    text = json.dumps(obj, indent=4, default=str)
    for l in text.splitlines():
        _log(f"  {l}")

def _check_fields(label: str, obj: dict, required: list):
    if not obj:
        _log(f"  [MISSING] {label} — no data")
        return
    for f in required:
        val = obj.get(f)
        status = "OK" if val not in (None, 0, "") else "ZERO/EMPTY"
        _log(f"  [{status:^12}]  {f} = {val}")

def _save():
    REPORT_FILE.write_text("\n".join(_lines), encoding="utf-8")
    print(f"\nReport saved → {REPORT_FILE}")

# ── API throttle (0.35s between calls to avoid AB1019 rate-limit errors) ──────
_last_api_ts = 0.0

def _api_throttle():
    global _last_api_ts
    elapsed = time.time() - _last_api_ts
    if elapsed < 0.35:
        time.sleep(0.35 - elapsed)
    _last_api_ts = time.time()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    _h("ANGEL ONE SMART API — DATA AVAILABILITY TEST")
    _log(f"Run time : {datetime.now()}")
    _log(f"Client ID: {CLIENT_ID}")
    _log(f"API Key  : {API_KEY[:4]}****")

    # ── 1. AUTH ───────────────────────────────────────────────────────────────
    _h("1. AUTHENTICATION")
    smart = SmartConnect(api_key=API_KEY)
    try:
        totp = pyotp.TOTP(TOTP_SECRET).now()
        _log(f"Generated TOTP: {totp}")
        session = smart.generateSession(CLIENT_ID, PASSWORD, totp)
        _log(f"Session status : {session.get('status')}")
        _log(f"Session message: {session.get('message')}")
        if not session.get("status"):
            _log("FATAL: Login failed. Check credentials.")
            _save()
            return
        auth_token = session["data"]["jwtToken"]
        feed_token = smart.getfeedToken()
        _log(f"JWT token  : {auth_token[:30]}...")
        _log(f"Feed token : {feed_token[:20] if feed_token else 'NONE'}...")
    except Exception as e:
        _log(f"EXCEPTION during login: {e}")
        traceback.print_exc()
        _save()
        return

    # ── 2. PROFILE ────────────────────────────────────────────────────────────
    _h("2. USER PROFILE")
    try:
        profile = smart.getProfile(session["data"]["refreshToken"])
        _log(f"Name        : {profile.get('data', {}).get('name', 'N/A')}")
        _log(f"Exchanges   : {profile.get('data', {}).get('exchanges', [])}")
        _log(f"Products    : {profile.get('data', {}).get('products', [])}")
        _log(f"Broker      : {profile.get('data', {}).get('broker', 'N/A')}")
        _dump("Full profile response", profile.get("data", {}))
    except Exception as e:
        _log(f"Profile error: {e}")

    # ── 3. LTP DATA ───────────────────────────────────────────────────────────
    _h("3. LTP DATA (ltpData)")

    symbols_to_test = [
        ("NIFTY 50 index",   NIFTY_EXCHANGE,    "NIFTY",     NIFTY_TOKEN),
        ("India VIX",        INDIAVIX_EXCHANGE, "INDIA VIX", INDIAVIX_TOKEN),
    ]

    for label, exch, sym, tok in symbols_to_test:
        _s(f"ltpData — {label}")
        try:
            _api_throttle()
            resp = smart.ltpData(exch, sym, tok)
            _dump("Response", resp)
            if resp and resp.get("status") and resp.get("data"):
                d = resp["data"]
                _check_fields("LTP fields", d, [
                    "ltp", "open", "high", "low", "close",
                    "tradingSymbol", "symbolToken", "exchange",
                ])
                _log(f"  Volume field present? {'YES — ' + str(d.get('netQuantity', d.get('volume', 'N/A'))) if 'netQuantity' in d or 'volume' in d else 'NO'}")
            else:
                _log("  FAILED or empty response")
        except Exception as e:
            _log(f"  EXCEPTION: {e}")

    # ── 4. FULL MARKET DATA (REST) ────────────────────────────────────────────
    _h("4. FULL MARKET DATA (getMarketData mode=FULL)")

    test_sets = [
        ("NSE:NIFTY index",     "NSE", [NIFTY_TOKEN]),
        ("NSE:INDIAVIX",        "NSE", [INDIAVIX_TOKEN]),
    ]

    for label, exch, tokens in test_sets:
        _s(f"getMarketData FULL — {label}")
        try:
            _api_throttle()
            resp = smart.getMarketData(mode="FULL", exchangeTokens={exch: tokens})
            _log(f"  status  = {resp.get('status')}")
            _log(f"  message = {resp.get('message')}")
            if resp and resp.get("data"):
                fetched     = resp["data"].get("fetched", [])
                unfulfilled = resp["data"].get("unfulfilled", [])
                _log(f"  fetched     = {len(fetched)} items")
                _log(f"  unfulfilled = {len(unfulfilled)} items: {unfulfilled}")
                if fetched:
                    item = fetched[0]
                    _dump("First fetched item (all fields)", item)
                    _check_fields("Key market data fields", item, [
                        "ltp", "open", "high", "low", "close",
                        "totTrdQnty",        # total traded quantity = VOLUME
                        "totTrdVal",         # total traded value
                        "opnInterest",       # OI (for derivatives)
                        "opnInterestChng",   # OI change
                        "netChng",           # price change
                        "pctChng",           # % change
                    ])
                    vol = item.get("totTrdQnty", 0)
                    _log(f"\n  >>> VOLUME (totTrdQnty) = {vol}  {'<-- HAS VOLUME' if vol else '<-- ZERO / NO VOLUME'}")
        except Exception as e:
            _log(f"  EXCEPTION: {e}")

    # ── 5. CANDLE DATA (historical) ───────────────────────────────────────────
    _h("5. CANDLE DATA (getCandleData)")

    now     = datetime.now()
    to_str  = now.strftime("%Y-%m-%d %H:%M")
    fr_str  = now.strftime("%Y-%m-%d 09:15")

    candle_tests = [
        ("NIFTY 50 index — 1min", NIFTY_EXCHANGE, NIFTY_TOKEN, "ONE_MINUTE"),
        ("NIFTY 50 index — 5min", NIFTY_EXCHANGE, NIFTY_TOKEN, "FIVE_MINUTE"),
    ]

    for label, exch, tok, interval in candle_tests:
        _s(f"getCandleData — {label}")
        try:
            params = {
                "exchange": exch,
                "symboltoken": tok,
                "interval": interval,
                "fromdate": fr_str,
                "todate": to_str,
            }
            _api_throttle()
            resp = smart.getCandleData(params)
            _log(f"  status  = {resp.get('status')}")
            _log(f"  message = {resp.get('message')}")
            if resp and resp.get("status") and resp.get("data"):
                data = resp["data"]
                _log(f"  Candles returned: {len(data)}")
                if data:
                    _log(f"  First candle : {data[0]}")
                    _log(f"  Last  candle : {data[-1]}")
                    _log(f"  Candle format: [timestamp, open, high, low, close, volume]")
                    sample = data[-1]  # latest candle
                    _log(f"\n  Sample (latest candle):")
                    _log(f"    timestamp = {sample[0]}")
                    _log(f"    open      = {sample[1]}")
                    _log(f"    high      = {sample[2]}")
                    _log(f"    low       = {sample[3]}")
                    _log(f"    close     = {sample[4]}")
                    vol = sample[5] if len(sample) > 5 else "MISSING"
                    _log(f"    volume    = {vol}  {'<-- HAS VOLUME' if vol and vol != 0 else '<-- ZERO / NO VOLUME'}")

                    # Check if any candle has non-zero volume
                    non_zero_vol = sum(1 for c in data if len(c) > 5 and c[5] and c[5] != 0)
                    _log(f"\n  >>> Candles with non-zero volume: {non_zero_vol} / {len(data)}")
            else:
                _log(f"  FAILED: {resp}")
        except Exception as e:
            _log(f"  EXCEPTION: {e}")

    # ── 6. INSTRUMENT MASTER + NIFTY FUTURES ─────────────────────────────────
    _h("6. INSTRUMENT MASTER — Find Nifty Futures & Options Tokens")
    futures_token    = None
    futures_symbol   = None
    option_ce_token  = None
    option_pe_token  = None
    option_atm       = None

    try:
        _s("Download instrument master from Angel One CDN")
        url    = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        r      = req.get(url, timeout=30)
        master = r.json()
        _log(f"  Total instruments: {len(master)}")

        # Filter NFO instruments
        nfo_instruments = [d for d in master if d.get("exch_seg") == "NFO"]
        _log(f"  NFO instruments: {len(nfo_instruments)}")

        # Find NIFTY FUTIDX (Nifty Futures)
        nifty_futures = [
            d for d in nfo_instruments
            if d.get("name") == "NIFTY"
            and d.get("instrumenttype") == "FUTIDX"
        ]
        _log(f"  NIFTY Futures contracts found: {len(nifty_futures)}")

        if nifty_futures:
            # Sort by expiry to get nearest
            try:
                nifty_futures.sort(key=lambda x: datetime.strptime(x.get("expiry", "01JAN2099"), "%d%b%Y"))
            except Exception:
                pass
            nearest_fut = nifty_futures[0]
            futures_token  = nearest_fut["token"]
            futures_symbol = nearest_fut["symbol"]
            _log(f"\n  Nearest Nifty Futures:")
            _log(f"    symbol   = {futures_symbol}")
            _log(f"    token    = {futures_token}")
            _log(f"    expiry   = {nearest_fut.get('expiry')}")
            _log(f"    lotsize  = {nearest_fut.get('lotsize')}")

        # Find ATM NIFTY options (near-expiry)
        nifty_options = [
            d for d in nfo_instruments
            if d.get("name") == "NIFTY"
            and d.get("instrumenttype") == "OPTIDX"
        ]
        _log(f"\n  NIFTY Options contracts found: {len(nifty_options)}")

        if nifty_options:
            # Prefer nearest WEEKLY expiry (within 7 days) — has highest OI
            today = datetime.now().date()
            weekly_cutoff = today + timedelta(days=7)
            expiry_dates = sorted(set(d.get("expiry", "") for d in nifty_options))

            nearest_expiry = None
            for exp_str in expiry_dates:
                try:
                    exp_dt = datetime.strptime(exp_str, "%d%b%Y").date()
                except ValueError:
                    continue
                if exp_dt < today:
                    continue
                if exp_dt <= weekly_cutoff:
                    nearest_expiry = exp_str
                    break
            if not nearest_expiry:
                nearest_expiry = expiry_dates[0] if expiry_dates else ""

            _log(f"  Selected expiry (weekly preference): {nearest_expiry}")
            _log(f"  All expiries (first 5): {expiry_dates[:5]}")

            # Get strikes for selected expiry
            exp_opts = [d for d in nifty_options if d.get("expiry") == nearest_expiry]
            strikes  = sorted(set(int(float(d["strike"]) / 100) for d in exp_opts))
            _log(f"  Strikes available (selected expiry, sample): {strikes[:10]}")

            # Pick 2 option tokens for market data test (CE + PE at first available strike)
            if exp_opts:
                ce_opts = [d for d in exp_opts if d.get("symbol", "").endswith("CE")]
                pe_opts = [d for d in exp_opts if d.get("symbol", "").endswith("PE")]
                if ce_opts:
                    option_ce_token = ce_opts[len(ce_opts)//2]["token"]  # mid-chain
                    option_atm      = int(float(ce_opts[len(ce_opts)//2]["strike"]) / 100)
                    _log(f"\n  Sample CE option: {ce_opts[len(ce_opts)//2].get('symbol')} token={option_ce_token}")
                if pe_opts:
                    option_pe_token = pe_opts[len(pe_opts)//2]["token"]
                    _log(f"  Sample PE option: {pe_opts[len(pe_opts)//2].get('symbol')} token={option_pe_token}")
    except Exception as e:
        _log(f"  EXCEPTION: {e}")
        traceback.print_exc()

    # ── 7. NIFTY FUTURES MARKET DATA ─────────────────────────────────────────
    _h("7. NIFTY FUTURES — Full Market Data (with Volume)")
    if futures_token:
        _s(f"getMarketData FULL — {futures_symbol} (NFO)")
        try:
            _api_throttle()
            resp = smart.getMarketData(mode="FULL", exchangeTokens={"NFO": [futures_token]})
            _log(f"  status  = {resp.get('status')}")
            _log(f"  message = {resp.get('message')}")
            if resp and resp.get("data"):
                fetched     = resp["data"].get("fetched", [])
                unfulfilled = resp["data"].get("unfulfilled", [])
                _log(f"  fetched     = {len(fetched)}")
                _log(f"  unfulfilled = {len(unfulfilled)}: {unfulfilled}")
                if fetched:
                    item = fetched[0]
                    _dump("Futures full data (all fields)", item)
                    vol = item.get("tradeVolume", 0)
                    oi  = item.get("opnInterest", 0)
                    _log(f"\n  >>> VOLUME (totTrdQnty) = {vol}  {'<-- HAS VOLUME' if vol else '<-- ZERO'}")
                    _log(f"  >>> OI     (opnInterest)= {oi}   {'<-- HAS OI'     if oi  else '<-- ZERO'}")
        except Exception as e:
            _log(f"  EXCEPTION: {e}")
    else:
        _log("  SKIPPED — no futures token found")

    # ── 8. NIFTY FUTURES CANDLE DATA ─────────────────────────────────────────
    _h("8. NIFTY FUTURES CANDLE DATA (with Volume)")
    if futures_token:
        _s(f"getCandleData 1min — {futures_symbol}")
        try:
            params = {
                "exchange": "NFO",
                "symboltoken": futures_token,
                "interval": "ONE_MINUTE",
                "fromdate": fr_str,
                "todate": to_str,
            }
            _api_throttle()
            resp = smart.getCandleData(params)
            _log(f"  status  = {resp.get('status')}")
            if resp and resp.get("status") and resp.get("data"):
                data = resp["data"]
                _log(f"  Candles: {len(data)}")
                if data:
                    sample = data[-1]
                    _log(f"  Latest: {sample}")
                    vol = sample[5] if len(sample) > 5 else "MISSING"
                    _log(f"\n  >>> Volume on futures candle = {vol}  {'<-- HAS VOLUME' if vol and vol != 0 else '<-- ZERO'}")
                    non_zero = sum(1 for c in data if len(c) > 5 and c[5] and c[5] != 0)
                    _log(f"  Non-zero volume candles: {non_zero}/{len(data)}")
        except Exception as e:
            _log(f"  EXCEPTION: {e}")
    else:
        _log("  SKIPPED — no futures token found")

    # ── 9. NFO OPTION CHAIN OI DATA ──────────────────────────────────────────
    _h("9. OPTION CHAIN — OI DATA (getMarketData on NFO options)")
    option_tokens = [t for t in [option_ce_token, option_pe_token] if t]
    if option_tokens:
        _s("getMarketData FULL — NFO options (CE + PE)")
        try:
            _api_throttle()
            resp = smart.getMarketData(mode="FULL", exchangeTokens={"NFO": option_tokens})
            _log(f"  status     = {resp.get('status')}")
            _log(f"  message    = {resp.get('message')}")
            if resp and resp.get("data"):
                fetched     = resp["data"].get("fetched", [])
                unfulfilled = resp["data"].get("unfulfilled", [])
                _log(f"  fetched     = {len(fetched)}")
                _log(f"  unfulfilled = {len(unfulfilled)}: {unfulfilled[:5]}")

                for item in fetched:
                    _log(f"\n  Symbol: {item.get('tradingSymbol', item.get('symbolToken'))}")
                    _dump("  Option data (all fields)", item)
                    _check_fields("  Option fields", item, [
                        "ltp", "high", "low", "close",
                        "totTrdQnty",       # option volume
                        "opnInterest",      # OI — KEY for PCR
                        "opnInterestChng",  # OI change — KEY for buildup
                        "netChng",          # price change — KEY for buildup
                    ])
                    oi = item.get("opnInterest", 0)
                    _log(f"\n  >>> OI (opnInterest) = {oi}  {'<-- HAS OI' if oi else '<-- ZERO — PCR WILL BE 0'}")

                if unfulfilled:
                    _log("\n  >>> UNFULFILLED TOKENS — SUBSCRIPTION ISSUE:")
                    _log("      These tokens were requested but NOT returned by the API.")
                    _log("      This typically means your Angel One plan does not include")
                    _log("      real-time NFO / derivatives market data.")
                    for t in unfulfilled:
                        _log(f"      Token: {t}")
        except Exception as e:
            _log(f"  EXCEPTION: {e}")
    else:
        _log("  SKIPPED — no option tokens found")

    # ── 10. WEBSOCKET TICK TEST ───────────────────────────────────────────────
    _h("10. WEBSOCKET TICK TEST (30-second capture)")
    _log("Subscribing to NIFTY ticks for 30 seconds...")
    _log("Will capture all fields from every tick received.\n")

    ws_ticks     = []
    ws_connected = threading.Event()
    ws_done      = threading.Event()

    token_list = [
        {"exchangeType": 1, "tokens": [NIFTY_TOKEN]},  # NSE
    ]
    if futures_token:
        token_list.append({"exchangeType": 2, "tokens": [futures_token]})  # NFO
        if option_ce_token and option_pe_token:
            token_list.append({
                "exchangeType": 2,
                "tokens": [option_ce_token, option_pe_token]
            })
    def _on_data(wsapp, message):
        try:
            import json as _json
            data = _json.loads(message) if isinstance(message, str) else message
            ticks = data if isinstance(data, list) else [data]
            for tick in ticks:
                ws_ticks.append(tick)
                if len(ws_ticks) <= 5:  # Print first 5 ticks live
                    # Smart API v2 uses long field names; show both for diagnostics
                    raw_ltp = tick.get("last_traded_price") or tick.get("ltp")
                    raw_vol = tick.get("volume_trade_for_the_day") or tick.get("v")
                    raw_oi  = tick.get("open_interest") or tick.get("oi")
                    raw_oic = tick.get("open_interest_change_percentage") or tick.get("oic")
                    _log(f"""
                        TICK #{len(ws_ticks)}:
                            token  = {tick.get("token") or tick.get("tk")}
                            ltp    = {raw_ltp}  (raw, divide by 100 for ₹)
                            volume = {raw_vol}
                            oi     = {raw_oi}
                            oic    = {raw_oic}
                        """)
        except Exception as e:
            _log(f"  WS parse error: {e}")

    def _on_open(wsapp):
        _log("  WebSocket CONNECTED")
        ws_connected.set()
        try:
            ws.subscribe("test123", 3, token_list)
            _log(f"  Subscribed to {[t['tokens'] for t in token_list]}")
        except Exception as e:
            _log(f"  Subscribe error: {e}")

    def _on_error(wsapp, error):
        _log(f"  WebSocket ERROR: {error}")
        ws_done.set()

    def _on_close(wsapp):
        _log("  WebSocket CLOSED")
        ws_done.set()

    try:
        ws = SmartWebSocketV2(auth_token, API_KEY, CLIENT_ID, feed_token)
        ws.on_open  = _on_open
        ws.on_data  = _on_data
        ws.on_error = _on_error
        ws.on_close = _on_close

        ws_thread = threading.Thread(target=ws.connect, daemon=True)
        ws_thread.start()

        connected = ws_connected.wait(timeout=15)
        if not connected:
            _log("  TIMEOUT — WebSocket did not connect within 15s")
        else:
            _log("  Waiting 30s for ticks...")
            time.sleep(30)
            try:
                ws.close_connection()
            except Exception:
                pass
            ws_done.wait(timeout=5)

        _log(f"\n  Total ticks received: {len(ws_ticks)}")

        if ws_ticks:
            # Collect all unique field names across all ticks
            all_keys = set()
            for tick in ws_ticks:
                if isinstance(tick, dict):
                    all_keys.update(tick.keys())

            _log(f"  Unique fields seen across all ticks: {sorted(all_keys)}")

            # Show a complete sample tick
            sample = ws_ticks[-1]
            _dump("  Sample tick (latest)", sample)

            _log("\n  Field Analysis (Smart API v2 uses LONG field names):")
            # Map both short AND long field names so we can see which the API sends
            field_map = {
                # Long form (Smart API v2)    Short form    Description
                "token"                      : "Token (symbol token)",
                "last_traded_price"          : "Last Traded Price (÷100 for ₹)",
                "last_traded_timestamp"      : "Last Trade Time",
                "last_traded_quantity"       : "Last Trade Quantity",
                "volume_trade_for_the_day"   : "Total Traded Volume (session)",
                "best_bid_price"             : "Best Bid Price",
                "best_bid_quantity"          : "Best Bid Quantity",
                "best_ask_price"             : "Best Ask Price",
                "best_ask_quantity"          : "Best Ask Quantity",
                "high_price_of_the_day"      : "Session High (÷100 for ₹)",
                "low_price_of_the_day"       : "Session Low (÷100 for ₹)",
                "open_price_of_the_day"      : "Open Price (÷100 for ₹)",
                "closed_price"               : "Close / prev day (÷100 for ₹)",
                "open_interest"              : "Open Interest",
                "open_interest_change_percentage" : "OI Change %",
                # Legacy short forms (may still appear in some SDK versions)
                "tk"  : "Token (short)",
                "ltp" : "LTP (short)",
                "v"   : "Volume (short)",
                "h"   : "High (short)",
                "l"   : "Low (short)",
                "oi"  : "OI (short)",
            }
            for field, description in field_map.items():
                present = field in all_keys
                sample_val = sample.get(field) if isinstance(sample, dict) else None
                status = "PRESENT" if present else "ABSENT"
                _log(f"    [{status:^9}]  '{field}'  ({description}) = {sample_val}")
        else:
            _log("  NO TICKS RECEIVED during 30-second window")
            _log("  Possible reasons:")
            _log("    - Market is closed")
            _log("    - WebSocket subscription failed")
            _log("    - Market data feed not included in subscription")

    except Exception as e:
        _log(f"  EXCEPTION: {e}")
        traceback.print_exc()

    # ── 11. SUMMARY ───────────────────────────────────────────────────────────
    _h("11. SUMMARY — DATA AVAILABILITY FOR THIS APPLICATION")

    _log("""
  INDICATOR / FEATURE          SOURCE                  STATUS
  ─────────────────────────────────────────────────────────────────────
  Nifty spot price (LTP)       NSE:NIFTY REST/WS       Check Section 3/10
  Nifty spot change %          NSE:NIFTY REST/WS       Check Section 3/10
  EMA 9, EMA 21                Computed from candles   Derived (no API needed)
  ATR                          Computed from candles   Derived
  Momentum                     Computed from candles   Derived
  Session High/Low             Computed from candles   Derived
  Support / Resistance         Computed from candles   Derived

  VWAP (via cash index)        NSE:NIFTY candles       Check Section 5 volume
  VWAP (via futures)           NFO:NIFTYFUT candles    Check Section 8 volume

  PCR (Put-Call Ratio)         NFO options OI          Check Section 9
  OI Buildup pattern           NFO options OI change   Check Section 9
  Max Pain                     NFO options OI          Check Section 9
  OI Support/Resistance        NFO options OI          Check Section 9

  WebSocket volume (v field)   NSE/NFO WS feed         Check Section 10
  WebSocket high/low (h, l)    NSE/NFO WS feed         Check Section 10
  WebSocket OI (oi field)      NFO WS feed             Check Section 10
  ─────────────────────────────────────────────────────────────────────
  Read each section above for the actual values returned.
""")

    # ── SAVE ─────────────────────────────────────────────────────────────────
    _save()


if __name__ == "__main__":
    main()
