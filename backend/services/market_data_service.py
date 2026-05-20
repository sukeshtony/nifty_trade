"""Market Data Service — Angel One Smart API integration for real-time Nifty data."""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import pyotp
import json
import threading

from config import get_settings
from utils.cache import cache
from utils.helpers import SYMBOL_TOKENS, ist_now

logger = logging.getLogger(__name__)
settings = get_settings()


# Minimum delay between REST API calls to avoid Angel One rate-limiting (AB1019)
_API_THROTTLE_SECONDS = 0.35
_last_api_call_time = 0.0


def _throttle():
    """Enforce minimum delay between Angel One REST API calls."""
    global _last_api_call_time
    elapsed = time.time() - _last_api_call_time
    if elapsed < _API_THROTTLE_SECONDS:
        time.sleep(_API_THROTTLE_SECONDS - elapsed)
    _last_api_call_time = time.time()


class MarketDataService:
    """Handles all Angel One Smart API interactions for Nifty."""

    def __init__(self):
        self.smart_api: Optional[SmartConnect] = None
        self.ws: Optional[SmartWebSocketV2] = None
        self.auth_token: str = ""
        self.feed_token: str = ""
        self._connected = False
        self._login_lock = threading.Lock()
        self._last_login_attempt: float = 0   # epoch timestamp of last attempt
        self._login_cooldown_s: int = 60       # wait 60 s before retrying a failed login
        self._ws_callbacks = []
        self._depth_callbacks = []           # depth-specific callbacks
        self._nifty_fut_token: Optional[str] = None
        self._nifty_fut_symbol: Optional[str] = None
        self._instrument_master: Optional[List] = None
        self._instrument_master_lock = threading.Lock()
        self._oi_baselines = {}  # {token: initial_oi_of_day}
        self._baseline_date = None
        # Maps token → display label for depth subscription
        self._depth_token_labels: Dict[str, str] = {}

    # ── Authentication ──

    def login(self) -> bool:
        """Authenticate with Angel One Smart API."""
        with self._login_lock:
            if self._connected:
                return True
            # Cooldown: don't hammer Angel One if login recently failed
            if self._last_login_attempt > 0:
                elapsed = time.time() - self._last_login_attempt
                if elapsed < self._login_cooldown_s:
                    return False  # silently skip — cooldown active
            self._last_login_attempt = time.time()
            try:
                self.smart_api = SmartConnect(api_key=settings.ANGEL_API_KEY)
                totp = pyotp.TOTP(settings.ANGEL_TOTP_SECRET).now()
                data = self.smart_api.generateSession(
                    settings.ANGEL_CLIENT_ID,
                    settings.ANGEL_PASSWORD,
                    totp,
                )
                if data["status"]:
                    self.auth_token = data["data"]["jwtToken"]
                    self.feed_token = self.smart_api.getfeedToken()
                    self._connected = True
                    self._last_login_attempt = 0  # reset on success
                    logger.info("Angel One login successful")
                    return True
                logger.error(f"Angel One login failed: {data}")
                return False
            except Exception as e:
                logger.error(f"Angel One login error: {e}")
                return False

    def ensure_connected(self):
        if not self._connected:
            self.login()

    # ── Futures Token Resolution ──

    def get_nifty_futures_token(self) -> Optional[Dict[str, str]]:
        """Resolve nearest Nifty Futures contract from instrument master.
        Returns {"token": "...", "symbol": "NIFTY30MAR26FUT"} or None.
        Cached for the entire trading day.
        """
        if self._nifty_fut_token:
            return {"token": self._nifty_fut_token, "symbol": self._nifty_fut_symbol}

        master = self._load_instrument_master()
        if not master:
            return None

        from datetime import datetime as dt
        today = ist_now().date()

        futures = [
            d for d in master
            if d.get("exch_seg") == "NFO"
            and d.get("name") == "NIFTY"
            and d.get("instrumenttype") == "FUTIDX"
        ]

        # Find nearest future expiry
        nearest = None
        for f in futures:
            try:
                exp = dt.strptime(f.get("expiry", ""), "%d%b%Y").date()
                if exp >= today:
                    if nearest is None or exp < dt.strptime(nearest.get("expiry", ""), "%d%b%Y").date():
                        nearest = f
            except ValueError:
                continue

        if nearest:
            self._nifty_fut_token = nearest.get("token", "")
            self._nifty_fut_symbol = nearest.get("symbol", "")
            # Update the global SYMBOL_TOKENS so other parts of the code can use it
            SYMBOL_TOKENS["NIFTY_FUT"]["token"] = self._nifty_fut_token
            SYMBOL_TOKENS["NIFTY_FUT"]["symbol"] = self._nifty_fut_symbol
            logger.info(f"Nifty Futures resolved: {self._nifty_fut_symbol} token={self._nifty_fut_token}")
            return {"token": self._nifty_fut_token, "symbol": self._nifty_fut_symbol}

        logger.warning("Could not resolve Nifty Futures token from instrument master")
        return None

    # ── REST API Methods ──

    def get_ltp(self, symbol: str, exchange: str = "NSE", token: str = "") -> Optional[Dict]:
        """Get Last Traded Price for a symbol."""
        self.ensure_connected()
        try:
            sym_info = SYMBOL_TOKENS.get(symbol.upper(), {})
            token = token or sym_info.get("token", "")
            exchange = sym_info.get("exchange", exchange)

            _throttle()
            data = self.smart_api.ltpData(exchange, symbol, token)
            if data and data.get("status"):
                ltp_data = data["data"]
                cache.set(f"ltp:{symbol}", ltp_data, ttl=10)
                return ltp_data
            return None
        except Exception as e:
            logger.error(f"LTP fetch error for {symbol}: {e}")
            return cache.get(f"ltp:{symbol}")

    def get_full_market_data(self, symbol: str) -> Optional[Dict]:
        """Get FULL market data (LTP, OHLC, change, volume) using getMarketData API."""
        self.ensure_connected()
        try:
            sym_info = SYMBOL_TOKENS.get(symbol.upper(), {})
            token = sym_info.get("token", "")
            exchange = sym_info.get("exchange", "NSE")

            _throttle()
            data = self.smart_api.getMarketData(
                mode="FULL",
                exchangeTokens={exchange: [token]}
            )

            if data and data.get("status") and data.get("data"):
                fetched = data["data"].get("fetched", [])

                if fetched and len(fetched) > 0:
                    item = fetched[0]
                    result = {
                        "ltp": item.get("ltp", 0),
                        "open": item.get("opnPrice", 0),
                        "high": item.get("high", 0),
                        "low": item.get("low", 0),
                        "close": item.get("close", 0),
                        "prevClose": item.get("close", 0),
                        "change": round(item.get("ltp", 0) - item.get("close", 0), 2),
                        "changePct": round(
                            ((item.get("ltp", 0) - item.get("close", 0)) / item.get("close", 1)) * 100, 2
                        ) if item.get("close", 0) != 0 else 0,
                        "volume": item.get("totTrdQnty", 0),
                    }
                    cache.set(f"market_full:{symbol}", result, ttl=15)
                    return result

            logger.warning(f"getMarketData returned no data for {symbol}")
            return cache.get(f"market_full:{symbol}")
        except Exception as e:
            logger.error(f"Full market data error for {symbol}: {e}")
            return cache.get(f"market_full:{symbol}")

    def get_candle_data(
        self,
        symbol: str,
        token: str = "",
        exchange: str = "NSE",
        interval: str = "ONE_MINUTE",
        from_date: str = "",
        to_date: str = "",
    ) -> List:
        """Fetch historical candle data."""
        self.ensure_connected()
        try:
            sym_info = SYMBOL_TOKENS.get(symbol.upper(), {})
            token = token or sym_info.get("token", "")
            exchange = sym_info.get("exchange", exchange)

            now = ist_now()
            if not to_date:
                to_date = now.strftime("%Y-%m-%d %H:%M")
            if not from_date:
                from_date = (now - timedelta(days=5)).strftime("%Y-%m-%d 09:15")

            params = {
                "exchange": exchange,
                "symboltoken": token,
                "interval": interval,
                "fromdate": from_date,
                "todate": to_date,
            }
            _throttle()
            data = self.smart_api.getCandleData(params)
            if data and data.get("status"):
                candles = data["data"]
                if candles:
                    cache.set(f"candles:{symbol}:{interval}", candles, ttl=60)
                    return candles
            return cache.get_or_default(f"candles:{symbol}:{interval}", [])
        except Exception as e:
            logger.error(f"Candle data error for {symbol}: {e}")
            return cache.get_or_default(f"candles:{symbol}:{interval}", [])

    # ── Instrument Master & Option Chain ──

    def _load_instrument_master(self) -> List[Dict]:
        """Download and cache Angel One instrument master file (once per day)."""
        # Fast path: instance-level cache (no lock needed for reads)
        if self._instrument_master:
            return self._instrument_master

        # Check TTL-based cache
        cached = cache.get("instrument_master")
        if cached:
            self._instrument_master = cached
            return cached

        # Serialize downloads — only one thread downloads at a time
        with self._instrument_master_lock:
            # Double-check after acquiring lock (another thread may have finished)
            if self._instrument_master:
                return self._instrument_master
            cached = cache.get("instrument_master")
            if cached:
                self._instrument_master = cached
                return cached

            try:
                import requests as req
                url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
                logger.info("Downloading Angel One instrument master...")
                resp = req.get(url, timeout=30)
                resp.raise_for_status()
                master = resp.json()
                cache.set("instrument_master", master, ttl=43200)  # 12 hours
                self._instrument_master = master
                logger.info(f"Instrument master loaded: {len(master)} instruments")
                return master
            except Exception as e:
                logger.error(f"Failed to load instrument master: {e}")
                return []

    def _get_option_contracts(self, symbol: str, expiry: str = "") -> Dict:
        """Filter instrument master for NFO option contracts."""
        master = self._load_instrument_master()
        if not master:
            return {"expiry": "", "ce": {}, "pe": {}}

        idx_name = symbol.upper()
        options = [
            d for d in master
            if d.get("exch_seg") == "NFO"
            and d.get("name") == idx_name
            and d.get("instrumenttype") == "OPTIDX"
        ]

        if not options:
            return {"expiry": "", "ce": {}, "pe": {}}

        from datetime import datetime as dt
        expiry_dates = sorted(set(d.get("expiry", "") for d in options))

        if expiry:
            selected_expiry = expiry
        else:
            # Prefer the nearest WEEKLY expiry (within 7 days) for maximum OI/liquidity.
            # Far-month options often have near-zero OI, breaking PCR/MaxPain/OI calculations.
            today = ist_now().date()
            weekly_cutoff = today + timedelta(days=7)
            selected_expiry = None
            nearest_any = None  # fallback: nearest future expiry regardless of type

            for exp in expiry_dates:
                try:
                    exp_dt = dt.strptime(exp, "%d%b%Y").date()
                except ValueError:
                    continue

                if exp_dt < today:
                    continue

                # Track nearest future expiry as fallback
                if nearest_any is None:
                    nearest_any = exp

                # Prefer expiry within 7 days (weekly)
                if exp_dt <= weekly_cutoff:
                    selected_expiry = exp
                    break

            if not selected_expiry:
                selected_expiry = nearest_any or (expiry_dates[0] if expiry_dates else "")

            logger.info(f"Option chain expiry selected: {selected_expiry} (weekly preference, {len(expiry_dates)} available)")

        expiry_options = [d for d in options if d.get("expiry") == selected_expiry]

        ce_map = {}
        pe_map = {}
        for d in expiry_options:
            try:
                raw_strike = float(d.get("strike", 0))
                strike_int = int(raw_strike / 100)
            except (ValueError, TypeError):
                continue

            sym = d.get("symbol", "")
            token = d.get("token", "")

            if sym.endswith("CE"):
                ce_map[strike_int] = {"token": token, "symbol": sym}
            elif sym.endswith("PE"):
                pe_map[strike_int] = {"token": token, "symbol": sym}

        return {"expiry": selected_expiry, "ce": ce_map, "pe": pe_map}

    def get_option_chain(self, symbol: str = "NIFTY", num_strikes: int = 3) -> Optional[List[Dict]]:
        """Build option chain — ATM ± num_strikes only for performance."""
        self.ensure_connected()
        cache_key = f"option_chain:{symbol}"

        try:
            ltp_data = self.get_ltp(symbol)
            spot = ltp_data.get("ltp", 0) if ltp_data else 0
            if not spot:
                return cache.get(cache_key)

            contracts = self._get_option_contracts(symbol)
            ce_map = contracts["ce"]
            pe_map = contracts["pe"]

            if not ce_map and not pe_map:
                return cache.get(cache_key)

            strike_interval = 50
            atm_strike = round(spot / strike_interval) * strike_interval
            strikes = [atm_strike + (i * strike_interval) for i in range(-num_strikes, num_strikes + 1)]

            # Collect tokens
            all_tokens = []
            token_info = {}
            for strike in strikes:
                if strike in ce_map:
                    t = ce_map[strike]["token"]
                    all_tokens.append(t)
                    token_info[t] = {"strike": strike, "type": "CE"}
                if strike in pe_map:
                    t = pe_map[strike]["token"]
                    all_tokens.append(t)
                    token_info[t] = {"strike": strike, "type": "PE"}

            if not all_tokens:
                return cache.get(cache_key)

            # Batch fetch market data
            all_market_data = {}
            try:
                md = self.smart_api.getMarketData(
                    mode="FULL",
                    exchangeTokens={"NFO": all_tokens}
                )
                if md and md.get("status") and md.get("data"):
                    fetched = md["data"].get("fetched", [])
                    unfulfilled = md["data"].get("unfulfilled", [])
                    if unfulfilled:
                        logger.warning(
                            f"NFO getMarketData: {len(fetched)} fetched, "
                            f"{len(unfulfilled)} unfulfilled tokens — "
                            f"likely subscription/entitlement issue. "
                            f"Sample unfulfilled: {unfulfilled[:3]}"
                        )
                    elif not fetched:
                        logger.warning(
                            f"NFO getMarketData returned 0 items for {len(all_tokens)} tokens. "
                            f"Full response: status={md.get('status')}, "
                            f"message={md.get('message')}"
                        )
                    else:
                        logger.info(f"NFO getMarketData: {len(fetched)} items fetched successfully")
                    for item in fetched:
                        all_market_data[str(item.get("symbolToken", ""))] = item
                else:
                    logger.error(
                        f"NFO getMarketData failed: status={md.get('status') if md else None}, "
                        f"message={md.get('message') if md else 'no response'}"
                    )
            except Exception as e:
                logger.error(f"Option market data batch error: {e}")

            # ── Stateful OI tracking for buildup ──
            # Use today's date to manage daily reset
            today = ist_now().date()
            if self._baseline_date != today:
                self._oi_baselines = {}
                self._baseline_date = today

            # Build chain
            chain = []
            for strike in sorted(strikes):
                row = {
                    "strike": strike,
                    "isATM": strike == atm_strike,
                    "callOI": 0, "callOIChg": 0, "callLTP": 0, "callVolume": 0,
                    "putOI": 0, "putOIChg": 0, "putLTP": 0, "putVolume": 0,
                    "callBuild": None, "putBuild": None,
                }

                ce_info = ce_map.get(strike)
                if ce_info:
                    token = str(ce_info["token"])
                    ce_data = all_market_data.get(token, {})
                    if ce_data:
                        current_oi = ce_data.get("opnInterest", 0) or 0
                        # Set baseline if not present (first fetch of the day)
                        if token not in self._oi_baselines:
                            self._oi_baselines[token] = current_oi
                        
                        row["callOI"] = current_oi
                        # Calculate change since first fetch of the day
                        row["callOIChg"] = (ce_data.get("opnInterestChng") or 
                                            (current_oi - self._oi_baselines[token]) or 0)
                        row["callLTP"] = ce_data.get("ltp", 0) or 0
                        row["callVolume"] = ce_data.get("totTrdQnty", 0) or 0
                        
                        p_chg = ce_data.get("netChng") or ce_data.get("netChange") or 0
                        row["callBuild"] = self._detect_buildup(p_chg, row["callOIChg"])

                pe_info = pe_map.get(strike)
                if pe_info:
                    token = str(pe_info["token"])
                    pe_data = all_market_data.get(token, {})
                    if pe_data:
                        current_oi = pe_data.get("opnInterest", 0) or 0
                        if token not in self._oi_baselines:
                            self._oi_baselines[token] = current_oi

                        row["putOI"] = current_oi
                        row["putOIChg"] = (pe_data.get("opnInterestChng") or 
                                           (current_oi - self._oi_baselines[token]) or 0)
                        row["putLTP"] = pe_data.get("ltp", 0) or 0
                        row["putVolume"] = pe_data.get("totTrdQnty", 0) or 0
                        
                        p_chg = pe_data.get("netChng") or pe_data.get("netChange") or 0
                        row["putBuild"] = self._detect_buildup(p_chg, row["putOIChg"])

                chain.append(row)

            if chain:
                total_oi = sum((r.get("callOI") or 0) + (r.get("putOI") or 0) for r in chain)
                if total_oi > 0:
                    cache.set(cache_key, chain, ttl=30)
                    return chain
                # OI is all-zero (NFO batch data failed) — preserve previous cached chain
                prev = cache.get(cache_key)
                return prev if prev else chain

            return cache.get(cache_key)

        except Exception as e:
            logger.error(f"Option chain build error for {symbol}: {e}")
            return cache.get(cache_key)

    @staticmethod
    def _detect_buildup(price_chg: float, oi_chg: float) -> Optional[str]:
        """Detect OI build-up pattern from price and OI changes."""
        if price_chg > 0 and oi_chg > 0:
            return "LONG_BUILD_UP"
        elif price_chg < 0 and oi_chg > 0:
            return "SHORT_BUILD_UP"
        elif price_chg > 0 and oi_chg < 0:
            return "SHORT_COVERING"
        elif price_chg < 0 and oi_chg < 0:
            return "LONG_UNWINDING"
        return None

    # ── WebSocket ──

    def _resolve_atm_option_tokens(self) -> Dict[str, str]:
        """Return {token: label} for ATM CE + PE of the nearest weekly expiry.
        Used to subscribe these tokens on the depth (mode=3) feed.
        """
        try:
            ltp_data = self.get_ltp("NIFTY")
            spot = ltp_data.get("ltp", 0) if ltp_data else 0
            if not spot:
                return {}

            contracts = self._get_option_contracts("NIFTY")
            ce_map = contracts["ce"]
            pe_map = contracts["pe"]

            strike_interval = 50
            atm = round(spot / strike_interval) * strike_interval

            result: Dict[str, str] = {}
            for offset in (0, 1, -1, 2, -2):   # ATM ±2 strikes
                strike = atm + offset * strike_interval
                if strike in ce_map:
                    t = str(ce_map[strike]["token"])
                    sym = ce_map[strike]["symbol"]
                    result[t] = f"NIFTY {strike} CE"
                    SYMBOL_TOKENS[sym] = {"token": t, "symbol": sym, "exchange": "NFO"}
                if strike in pe_map:
                    t = str(pe_map[strike]["token"])
                    sym = pe_map[strike]["symbol"]
                    result[t] = f"NIFTY {strike} PE"
                    SYMBOL_TOKENS[sym] = {"token": t, "symbol": sym, "exchange": "NFO"}

            logger.info(f"Depth subscription: resolved {len(result)} ATM option tokens around {atm}")
            return result
        except Exception as e:
            logger.error(f"ATM token resolution error: {e}")
            return {}

    def start_websocket(self, on_data_callback=None):
        """Start real-time WebSocket feed.

        Two simultaneous subscriptions:
          • mode=1 (LTP)       — NIFTY + INDIAVIX + NIFTY_FUT  (existing behaviour)
          • mode=3 (SNAP_QUOTE) — NIFTY + NIFTY_FUT + ATM options  (new depth feed)
        """
        if not self._connected:
            self.login()

        # Resolve Nifty Futures token (needed for volume/OI data)
        fut_info = self.get_nifty_futures_token()
        fut_token = fut_info["token"] if fut_info else None

        # Initialize state manager from FUTURES candles (they have volume for VWAP)
        from services.market_state import market_state_manager
        logger.info("Initializing Market State Manager from historical candles...")
        if fut_token:
            candles = self.get_candle_data(
                "NIFTY_FUT", token=fut_token, exchange="NFO", interval="ONE_MINUTE"
            )
        else:
            candles = self.get_candle_data("NIFTY", interval="ONE_MINUTE")
        if candles:
            market_state_manager.initialize_from_history("NIFTY", candles)
        logger.info("Market State Manager initialized.")

        # ── Build depth token labels: NIFTY + FUT + ATM options ──
        self._depth_token_labels = {
            SYMBOL_TOKENS["NIFTY"]["token"]: "NIFTY",
        }
        if fut_token:
            self._depth_token_labels[fut_token] = "NIFTY_FUT"

        atm_tokens = self._resolve_atm_option_tokens()
        self._depth_token_labels.update(atm_tokens)

        try:
            self.ws = SmartWebSocketV2(
                self.auth_token,
                settings.ANGEL_API_KEY,
                settings.ANGEL_CLIENT_ID,
                self.feed_token,
            )

            # ── Subscription lists ──
            # mode=1: LTP feed (existing)
            nse_ltp_tokens = [SYMBOL_TOKENS["NIFTY"]["token"]]
            if SYMBOL_TOKENS.get("INDIAVIX", {}).get("token"):
                nse_ltp_tokens.append(SYMBOL_TOKENS["INDIAVIX"]["token"])
            nfo_ltp_tokens = [fut_token] if fut_token else []

            ltp_token_list = [{"exchangeType": 1, "tokens": nse_ltp_tokens}]
            if nfo_ltp_tokens:
                ltp_token_list.append({"exchangeType": 2, "tokens": nfo_ltp_tokens})

            # mode=3: SNAP_QUOTE depth feed (NIFTY + FUT + ATM options)
            depth_nse_tokens = [SYMBOL_TOKENS["NIFTY"]["token"]]
            depth_nfo_tokens = [t for t in self._depth_token_labels if t != SYMBOL_TOKENS["NIFTY"]["token"]]

            depth_token_list = [{"exchangeType": 1, "tokens": depth_nse_tokens}]
            if depth_nfo_tokens:
                depth_token_list.append({"exchangeType": 2, "tokens": depth_nfo_tokens})

            def _parse_depth_levels(raw_levels: list, price_divisor: float = 100.0) -> list:
                """Normalise best_5_buy/sell_data from WS tick into clean dicts."""
                result = []
                for lvl in (raw_levels or []):
                    try:
                        raw_price = lvl.get("price", 0)
                        qty       = int(lvl.get("quantity", 0) or 0)
                        orders    = int(lvl.get("num_orders", lvl.get("numOrders", 0)) or 0)
                        # WS prices come as integers (paisa) like LTP
                        price_val = float(raw_price) / price_divisor if raw_price else 0.0
                        result.append({"price": price_val, "quantity": qty, "orders": orders})
                    except Exception:
                        continue
                return result

            def _compute_depth_payload(token: str, tick: dict) -> Optional[dict]:
                """Extract and compute depth metrics from a SNAP_QUOTE tick."""
                label = self._depth_token_labels.get(token, token)

                buy_raw  = tick.get("best_5_buy_data")  or tick.get("best5BuyData")  or []
                sell_raw = tick.get("best_5_sell_data") or tick.get("best5SellData") or []

                # Some versions of SmartAPI WS send depth as snake_case or camelCase
                total_buy_qty  = int(tick.get("total_buy_quantity")  or tick.get("totalBuyQty")  or 0)
                total_sell_qty = int(tick.get("total_sell_quantity") or tick.get("totalSellQty") or 0)

                # If WS didn't send aggregates, sum from depth levels
                if (not total_buy_qty) and buy_raw:
                    total_buy_qty = sum(int(l.get("quantity", 0) or 0) for l in buy_raw)
                if (not total_sell_qty) and sell_raw:
                    total_sell_qty = sum(int(l.get("quantity", 0) or 0) for l in sell_raw)

                if not buy_raw and not sell_raw and not total_buy_qty and not total_sell_qty:
                    return None  # no depth in this tick

                buy_levels  = _parse_depth_levels(buy_raw)
                sell_levels = _parse_depth_levels(sell_raw)

                # Order Book Imbalance: +1 = pure buy pressure, -1 = pure sell pressure
                total = total_buy_qty + total_sell_qty
                obi = round((total_buy_qty - total_sell_qty) / total, 4) if total else 0.0

                # Best bid/ask spread
                best_bid = buy_levels[0]["price"]  if buy_levels  else 0.0
                best_ask = sell_levels[0]["price"] if sell_levels else 0.0
                spread   = round(best_ask - best_bid, 2) if best_bid and best_ask else 0.0

                # Pressure label
                if obi > 0.25:
                    pressure = "STRONG_BUY"
                elif obi > 0.08:
                    pressure = "MILD_BUY"
                elif obi < -0.25:
                    pressure = "STRONG_SELL"
                elif obi < -0.08:
                    pressure = "MILD_SELL"
                else:
                    pressure = "NEUTRAL"

                # LTP for the instrument
                raw_ltp = tick.get("last_traded_price") or tick.get("ltp", 0)
                ltp_val = float(raw_ltp) / 100.0 if raw_ltp else 0.0

                payload = {
                    "token":           token,
                    "label":           label,
                    "ltp":             ltp_val,
                    "buy_depth":       buy_levels,
                    "sell_depth":      sell_levels,
                    "total_buy_qty":   total_buy_qty,
                    "total_sell_qty":  total_sell_qty,
                    "obi":             obi,
                    "pressure":        pressure,
                    "bid_ask_spread":  spread,
                }
                cache.set(f"depth:{token}", payload, ttl=10)
                return payload

            def on_data(wsapp, message):
                try:
                    data = json.loads(message) if isinstance(message, str) else message
                    ticks = data if isinstance(data, list) else [data]

                    for tick in ticks:
                        # Smart API v2 WebSocket uses "token" (long name), fallback to "tk"
                        token = tick.get("token") or tick.get("tk")
                        if not token:
                            continue
                        token = str(token)

                        # ── Depth path: token belongs to our depth subscription ──
                        if token in self._depth_token_labels:
                            depth_payload = _compute_depth_payload(token, tick)
                            if depth_payload:
                                for cb in self._depth_callbacks:
                                    cb(depth_payload)

                        # ── LTP / price path (existing, unchanged) ──
                        # Resolve symbol from token
                        symbol = None
                        for sym_name, info in SYMBOL_TOKENS.items():
                            if str(info.get("token")) == token:
                                symbol = sym_name
                                break
                        if not symbol:
                            continue

                        # Smart API v2 WebSocket sends prices as integers (paisa).
                        # e.g. last_traded_price=2300125 means ₹23,001.25
                        raw_ltp = tick.get("last_traded_price") or tick.get("ltp", 0)
                        if not raw_ltp:
                            continue

                        raw_vol = (
                            tick.get("volume_trade_for_the_day")
                            or tick.get("v")
                            or 0
                        )
                        raw_high = (
                            tick.get("high_price_of_the_day")
                            or tick.get("h")
                        )
                        raw_low = (
                            tick.get("low_price_of_the_day")
                            or tick.get("l")
                        )

                        try:
                            price = float(raw_ltp) / 100.0
                            vol   = int(raw_vol) if raw_vol else 0
                            high  = float(raw_high) / 100.0 if raw_high else None
                            low   = float(raw_low)  / 100.0 if raw_low  else None
                        except (ValueError, TypeError):
                            continue

                        # For NIFTY_FUT ticks, update the NIFTY state (same underlying)
                        state_symbol = "NIFTY" if symbol == "NIFTY_FUT" else symbol

                        from services.market_state import market_state_manager
                        market_state_manager.update_tick(
                            state_symbol, price, vol, high=high, low=low
                        )

                        cache.set(f"ws:{symbol}", tick, ttl=30)

                        if on_data_callback:
                            on_data_callback(tick)
                        for cb in self._ws_callbacks:
                            cb(tick)

                except Exception as e:
                    logger.error(f"WS data parse error: {e}")

            def on_open(wsapp):
                logger.info("WebSocket connected")
                # Subscribe mode=1 (LTP) — existing behaviour
                self.ws.subscribe("ltp_feed", 1, ltp_token_list)
                # Subscribe mode=3 (SNAP_QUOTE) — new depth feed
                self.ws.subscribe("depth_feed", 3, depth_token_list)
                logger.info(
                    f"Depth feed subscribed for {len(self._depth_token_labels)} tokens: "
                    + ", ".join(self._depth_token_labels.values())
                )

            def on_error(wsapp, error):
                logger.error(f"WebSocket error: {error}")

            def on_close(wsapp):
                logger.info("WebSocket closed")

            self.ws.on_open = on_open
            self.ws.on_data = on_data
            self.ws.on_error = on_error
            self.ws.on_close = on_close

            self.ws.connect()
        except Exception as e:
            logger.error(f"WebSocket start error: {e}")

    def register_ws_callback(self, callback):
        self._ws_callbacks.append(callback)

    def register_depth_callback(self, callback):
        """Register a callback for depth tick payloads from mode=3 subscription."""
        self._depth_callbacks.append(callback)

    # ── Trade Book & Positions ──

    def get_trade_book(self) -> List[Dict]:
        """Fetch today's executed trades from Angel One.
        Returns all trades; caller should filter for Nifty NFO options.
        """
        self.ensure_connected()
        try:
            _throttle()
            data = self.smart_api.tradeBook()
            if data and data.get("status") and data.get("data"):
                trades = data["data"] or []
                logger.info(f"Trade book fetched: {len(trades)} trades")
                return trades
            logger.warning(f"Trade book returned no data: {data.get('message') if data else 'no response'}")
            return []
        except Exception as e:
            logger.error(f"Trade book fetch error: {e}")
            return []

    def get_positions(self) -> List[Dict]:
        """Fetch current positions with realised & unrealised P&L from Angel One."""
        self.ensure_connected()
        try:
            _throttle()
            data = self.smart_api.position()
            if data and data.get("status") and data.get("data"):
                positions = data["data"] or []
                logger.info(f"Positions fetched: {len(positions)} positions")
                return positions
            logger.warning(f"Positions returned no data: {data.get('message') if data else 'no response'}")
            return []
        except Exception as e:
            logger.error(f"Positions fetch error: {e}")
            return []

    def get_order_book(self) -> List[Dict]:
        """Fetch today's order book (includes pending/cancelled orders)."""
        self.ensure_connected()
        try:
            _throttle()
            data = self.smart_api.orderBook()
            if data and data.get("status") and data.get("data"):
                orders = data["data"] or []
                logger.info(f"Order book fetched: {len(orders)} orders")
                return orders
            return []
        except Exception as e:
            logger.error(f"Order book fetch error: {e}")
            return []

    def stop_websocket(self):
        if self.ws:
            try:
                self.ws.close_connection()
            except Exception:
                pass


# Global singleton
market_service = MarketDataService()
