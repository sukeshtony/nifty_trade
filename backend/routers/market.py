"""Market data API router — Nifty price, overview."""

from fastapi import APIRouter
from services.market_data_service import market_service
from services.market_state import market_state_manager
from utils.cache import cache
from utils.helpers import attach_metadata
import time
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["Market"])


@router.get("/nifty-price")
def get_nifty_price():
    """Get real-time Nifty price from cache (populated by WebSocket/background).
    Frontend polls this every 2-3 seconds.
    """
    start_time = time.time()
    # Try live state first (from WebSocket ticks)
    state = market_state_manager.get_state("NIFTY")
    if state and state.get("current_price"):
        # Supplement change from REST cache when state hasn't computed it yet
        full_cached = cache.get("market_full:NIFTY") or {}
        data = {
            "ltp": state["current_price"],
            "change": state.get("change") or full_cached.get("change", 0),
            "changePct": state.get("change_pct") or full_cached.get("changePct", 0),
            "vwap": state.get("vwap") or None,
            "ema_9": state.get("ema_9"),
            "ema_21": state.get("ema_21"),
            "session_high": state.get("session_high", 0),
            "session_low": state.get("session_low", 0),
        }
        logger.info("[DATA_SOURCE] endpoint=/api/market/nifty-price source=LIVE")
        return attach_metadata(data, "LIVE", start_time)

    # Fallback to cached market data
    cached = cache.get("market_full:NIFTY")
    if cached:
        logger.info("[DATA_SOURCE] endpoint=/api/market/nifty-price source=CACHE")
        return attach_metadata(cached, "CACHE", start_time)

    # Last resort: fetch fresh data (only happens on first load)
    data = market_service.get_full_market_data("NIFTY")
    if data:
        logger.info("[DATA_SOURCE] endpoint=/api/market/nifty-price source=API")
        return attach_metadata(data, "API", start_time)

    logger.info("[DATA_SOURCE] endpoint=/api/market/nifty-price source=DB")
    return attach_metadata({"ltp": 0, "change": 0, "changePct": 0, "error": "No data available"}, "DB", start_time)


@router.get("/overview")
def get_market_overview():
    """Get market overview including VIX."""
    start_time = time.time()
    overview = {}

    nifty_source = "CACHE"
    # Nifty
    nifty_data = cache.get("market_full:NIFTY")
    if not nifty_data:
        nifty_data = market_service.get_full_market_data("NIFTY")
        nifty_source = "API"
    overview["NIFTY"] = nifty_data or {}

    # VIX
    vix_data = cache.get("market_full:INDIAVIX")
    overview["VIX"] = vix_data or {}

    logger.info(f"[DATA_SOURCE] endpoint=/api/market/overview source={nifty_source}")
    return attach_metadata(overview, nifty_source, start_time)
