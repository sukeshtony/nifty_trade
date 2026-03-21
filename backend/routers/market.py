"""Market data API router — Nifty price, overview."""

from fastapi import APIRouter
from services.market_data_service import market_service
from services.market_state import market_state_manager
from utils.cache import cache

router = APIRouter(prefix="/api/market", tags=["Market"])


@router.get("/nifty-price")
def get_nifty_price():
    """Get real-time Nifty price from cache (populated by WebSocket/background).
    Frontend polls this every 2-3 seconds.
    """
    # Try live state first (from WebSocket ticks)
    state = market_state_manager.get_state("NIFTY")
    if state and state.get("current_price"):
        return {
            "ltp": state["current_price"],
            "change": state.get("change", 0),
            "changePct": state.get("change_pct", 0),
            "vwap": state.get("vwap", 0),
            "ema_9": state.get("ema_9"),
            "ema_21": state.get("ema_21"),
            "session_high": state.get("session_high", 0),
            "session_low": state.get("session_low", 0),
        }

    # Fallback to cached market data
    cached = cache.get("market_full:NIFTY")
    if cached:
        return cached

    # Last resort: fetch fresh data (only happens on first load)
    data = market_service.get_full_market_data("NIFTY")
    if data:
        return data

    return {"ltp": 0, "change": 0, "changePct": 0, "error": "No data available"}


@router.get("/overview")
def get_market_overview():
    """Get market overview including VIX."""
    overview = {}

    # Nifty
    nifty_data = cache.get("market_full:NIFTY")
    if not nifty_data:
        nifty_data = market_service.get_full_market_data("NIFTY")
    overview["NIFTY"] = nifty_data or {}

    # VIX
    vix_data = cache.get("market_full:INDIAVIX")
    overview["VIX"] = vix_data or {}

    return overview
