"""Shared helper utilities."""

from datetime import datetime, time as dtime
import pytz

IST = pytz.timezone("Asia/Kolkata")


def ist_now() -> datetime:
    return datetime.now(IST)


def is_market_open() -> bool:
    """Check if Indian stock market is currently open (9:15 AM – 3:30 PM IST, Mon–Fri)."""
    now = ist_now()
    if now.weekday() >= 5:
        return False
    market_open = dtime(9, 15)
    market_close = dtime(15, 30)
    return market_open <= now.time() <= market_close


def format_currency(value: float) -> str:
    """Format to Indian rupee style."""
    if value < 0:
        return f"-₹{abs(value):,.2f}"
    return f"₹{value:,.2f}"


def round_to_tick(price: float, tick_size: float = 0.05) -> float:
    """Round price to nearest tick size."""
    return round(round(price / tick_size) * tick_size, 2)


def calculate_change_percent(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return round(((current - previous) / previous) * 100, 2)


# Nifty lot size
LOT_SIZES = {
    "NIFTY": 25,
    "NIFTY 50": 25,
}

# Angel One symbol tokens for Nifty
SYMBOL_TOKENS = {
    "NIFTY": {"symbol": "NIFTY", "token": "99926000", "exchange": "NSE"},
    "INDIAVIX": {"symbol": "India VIX", "token": "99926009", "exchange": "NSE"},
    # NIFTY_FUT token is resolved dynamically at runtime from instrument master.
    # See MarketDataService.get_nifty_futures_token()
    "NIFTY_FUT": {"symbol": "", "token": "", "exchange": "NFO"},
}

# Estimated brokerage charges per trade (one side)
ESTIMATED_CHARGES_PER_LOT = 40.0  # Approx brokerage + taxes per lot per side


import time

def attach_metadata(data: dict, source: str, start_time: float) -> dict:
    """Attach data source and staleness metadata to a dictionary."""
    now = time.time()
    latency = (now - start_time) * 1000

    data["data_source"] = source
    data["timestamp"] = now
    data["latency_ms"] = round(latency, 2)

    # staleness logic
    if source == "LIVE":
        data["is_stale"] = False
    elif source == "CACHE":
        data["is_stale"] = True
    elif source == "API":
        data["is_stale"] = True
    else:
        data["is_stale"] = False # Default or DB

    return data
