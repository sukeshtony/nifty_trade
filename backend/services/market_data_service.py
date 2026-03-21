"""Market Data Service — Angel One Smart API integration for real-time Nifty data."""

import logging
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


class MarketDataService:
    """Handles all Angel One Smart API interactions for Nifty."""

    def __init__(self):
        self.smart_api: Optional[SmartConnect] = None
        self.ws: Optional[SmartWebSocketV2] = None
        self.auth_token: str = ""
        self.feed_token: str = ""
        self._connected = False
        self._login_lock = threading.Lock()
        self._ws_callbacks = []

    # ── Authentication ──

    def login(self) -> bool:
        """Authenticate with Angel One Smart API."""
        with self._login_lock:
            if self._connected:
                return True
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

    # ── REST API Methods ──

    def get_ltp(self, symbol: str, exchange: str = "NSE", token: str = "") -> Optional[Dict]:
        """Get Last Traded Price for a symbol."""
        self.ensure_connected()
        try:
            sym_info = SYMBOL_TOKENS.get(symbol.upper(), {})
            token = token or sym_info.get("token", "")
            exchange = sym_info.get("exchange", exchange)

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
        cached = cache.get("instrument_master")
        if cached:
            return cached

        try:
            import requests as req
            url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
            logger.info("Downloading Angel One instrument master...")
            resp = req.get(url, timeout=30)
            resp.raise_for_status()
            master = resp.json()
            cache.set("instrument_master", master, ttl=43200)  # 12 hours
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
            selected_expiry = None
            for exp in expiry_dates:
                try:
                    exp_dt = dt.strptime(exp, "%d%b%Y")
                    if exp_dt.date() >= ist_now().date():
                        selected_expiry = exp
                        break
                except ValueError:
                    continue

        if not selected_expiry:
            selected_expiry = expiry_dates[0] if expiry_dates else ""

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
                    for item in md["data"].get("fetched", []):
                        all_market_data[str(item.get("symbolToken", ""))] = item
            except Exception as e:
                logger.error(f"Option market data batch error: {e}")

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
                    ce_data = all_market_data.get(ce_info["token"], {})
                    if ce_data:
                        row["callOI"] = ce_data.get("opnInterest", 0)
                        row["callOIChg"] = ce_data.get("opnInterestChng", 0)
                        row["callLTP"] = ce_data.get("ltp", 0)
                        row["callVolume"] = ce_data.get("totTrdQnty", 0)
                        row["callBuild"] = self._detect_buildup(
                            ce_data.get("netChng", 0), ce_data.get("opnInterestChng", 0)
                        )

                pe_info = pe_map.get(strike)
                if pe_info:
                    pe_data = all_market_data.get(pe_info["token"], {})
                    if pe_data:
                        row["putOI"] = pe_data.get("opnInterest", 0)
                        row["putOIChg"] = pe_data.get("opnInterestChng", 0)
                        row["putLTP"] = pe_data.get("ltp", 0)
                        row["putVolume"] = pe_data.get("totTrdQnty", 0)
                        row["putBuild"] = self._detect_buildup(
                            pe_data.get("netChng", 0), pe_data.get("opnInterestChng", 0)
                        )

                chain.append(row)

            if chain:
                cache.set(cache_key, chain, ttl=30)
                return chain

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

    def start_websocket(self, on_data_callback=None):
        """Start real-time WebSocket feed."""
        if not self._connected:
            self.login()

        # Initialize state manager from history BEFORE accepting ticks
        from services.market_state import market_state_manager
        logger.info("Initializing Market State Manager from historical candles...")
        candles = self.get_candle_data("NIFTY", interval="ONE_MINUTE")
        if candles:
            market_state_manager.initialize_from_history("NIFTY", candles)
        logger.info("Market State Manager initialized.")

        try:
            self.ws = SmartWebSocketV2(
                self.auth_token,
                settings.ANGEL_API_KEY,
                settings.ANGEL_CLIENT_ID,
                self.feed_token,
            )

            token_list = [
                {"exchangeType": 1, "tokens": [v["token"] for v in SYMBOL_TOKENS.values()]}
            ]

            def on_data(wsapp, message):
                try:
                    data = json.loads(message) if isinstance(message, str) else message
                    ticks = data if isinstance(data, list) else [data]

                    for tick in ticks:
                        token = tick.get("tk")
                        if not token:
                            continue

                        symbol = None
                        for sym_name, info in SYMBOL_TOKENS.items():
                            if str(info.get("token")) == str(token):
                                symbol = sym_name
                                break

                        if not symbol:
                            continue

                        price = tick.get("ltp") or tick.get("last_traded_price", 0)
                        if not price:
                            continue

                        vol = tick.get("v") or tick.get("volume", 0)
                        high = tick.get("h") or tick.get("high")
                        low = tick.get("l") or tick.get("low")

                        try:
                            price = float(price)
                            vol = int(vol) if vol else 0
                            if high: high = float(high)
                            if low: low = float(low)
                        except (ValueError, TypeError):
                            pass

                        from services.market_state import market_state_manager
                        market_state_manager.update_tick(symbol, price, vol, high=high, low=low)

                        cache.set(f"ws:{symbol}", tick, ttl=30)

                        if on_data_callback:
                            on_data_callback(tick)

                        for cb in self._ws_callbacks:
                            cb(tick)

                except Exception as e:
                    logger.error(f"WS data parse error: {e}")

            def on_open(wsapp):
                logger.info("WebSocket connected")
                self.ws.subscribe("abc123", 1, token_list)

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

    def stop_websocket(self):
        if self.ws:
            try:
                self.ws.close_connection()
            except Exception:
                pass


# Global singleton
market_service = MarketDataService()
