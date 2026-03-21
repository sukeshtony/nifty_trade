"""Options API router — option chain analysis."""

from fastapi import APIRouter
from services.market_data_service import market_service
from services.market_state import market_state_manager
from services.options_engine import options_engine
from utils.cache import cache

router = APIRouter(prefix="/api/options", tags=["Options"])


@router.get("/analysis")
def get_options_analysis():
    """Get processed options analysis — PCR, Max Pain, OI levels, ATM ± 3 strikes.
    Heavy processing done server-side; sends only processed results.
    """
    # Check cache first
    cached = cache.get("options_analysis:NIFTY")
    if cached:
        return cached

    # Fetch option chain (ATM ± 3 strikes only)
    chain = market_service.get_option_chain("NIFTY", num_strikes=3)
    if not chain:
        return {"error": "Option chain data not available"}

    # Get spot price
    state = market_state_manager.get_state("NIFTY")
    spot = state.get("current_price", 0)
    if not spot:
        ltp_data = market_service.get_ltp("NIFTY")
        spot = ltp_data.get("ltp", 0) if ltp_data else 0

    # Analyze
    analysis = options_engine.analyze(chain, spot)
    cache.set("options_analysis:NIFTY", analysis, ttl=30)

    return analysis
