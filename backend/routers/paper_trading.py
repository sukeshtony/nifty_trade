from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database.connection import get_db
from database.models import PaperTrade, TradeStatus
from services.paper_trade_service import paper_trade_service
from services.market_data_service import market_service
from services.market_state import market_state_manager
from utils.helpers import attach_metadata
from utils.cache import cache
import time
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/paper", tags=["Paper Trading"])


class InitAccountRequest(BaseModel):
    balance: float


class PlacePaperTradeRequest(BaseModel):
    symbol: str = "NIFTY"
    strike: int
    option_type: str
    entry_price: float
    qty: int = 25
    trade_type: str = "INTRADAY"
    notes: str = ""


class ClosePaperTradeRequest(BaseModel):
    exit_price: Optional[float] = None


@router.get("/option-chain")
def get_paper_option_chain():
    """Get live Nifty option chain for paper trading (ATM ±5 strikes)."""
    start_time = time.time()
    try:
        cached = cache.get("paper_option_chain:NIFTY")
        if cached:
            return attach_metadata({**cached}, "CACHE", start_time)

        chain = market_service.get_option_chain("NIFTY", num_strikes=5)
        if not chain:
            return {"status": "error", "data": [], "spot_price": 0, "message": "Option chain data not available"}

        state = market_state_manager.get_state("NIFTY")
        spot = state.get("current_price", 0)
        if not spot:
            ltp_data = market_service.get_ltp("NIFTY")
            spot = ltp_data.get("ltp", 0) if ltp_data else 0

        result = {"status": "success", "data": chain, "spot_price": spot}
        cache.set("paper_option_chain:NIFTY", result, ttl=5)
        return attach_metadata({**result}, "LIVE", start_time)
    except Exception as e:
        logger.error(f"Option chain fetch error: {e}")
        return {"status": "error", "data": [], "spot_price": 0}


@router.post("/account/init")
def initialize_account(req: InitAccountRequest, db: Session = Depends(get_db)):
    """Reset the paper trading account with a specific balance."""
    start_time = time.time()
    try:
        account = paper_trade_service.initialize_account(db, req.balance)
        response = {"status": "success", "message": f"Account initialized to {account.balance}"}
        logger.info("[DATA_SOURCE] endpoint=/paper/account/init source=DB")
        return attach_metadata(response, "DB", start_time)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/account")
def get_account_summary(db: Session = Depends(get_db)):
    """Get paper account balance, realized PnL and high-level stats."""
    start_time = time.time()
    try:
        response = {"status": "success", "data": paper_trade_service.get_account_summary(db)}
        logger.info("[DATA_SOURCE] endpoint=/paper/account source=DB")
        return attach_metadata(response, "DB", start_time)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trade/place")
def place_paper_trade(req: PlacePaperTradeRequest, db: Session = Depends(get_db)):
    """Place a new paper trade at live LTP."""
    start_time = time.time()
    try:
        trade = paper_trade_service.place_paper_trade(db, req.model_dump())
        response = {"status": "success", "trade_id": trade.id}
        logger.info("[DATA_SOURCE] endpoint=/paper/trade/place source=DB")
        return attach_metadata(response, "DB", start_time)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trade/close/{trade_id}")
def close_paper_trade(trade_id: int, req: ClosePaperTradeRequest, db: Session = Depends(get_db)):
    """Close an open paper trade. If exit_price is omitted, auto-fetches current LTP."""
    start_time = time.time()
    try:
        exit_price = req.exit_price

        # Auto-fetch live LTP from option chain when no exit_price supplied
        if exit_price is None:
            trade = db.query(PaperTrade).filter(
                PaperTrade.id == trade_id,
                PaperTrade.status == TradeStatus.OPEN
            ).first()
            if trade:
                try:
                    chain = market_service.get_option_chain("NIFTY", num_strikes=5)
                    if chain:
                        for row in chain:
                            if row["strike"] == trade.strike:
                                ltp_key = "callLTP" if trade.option_type == "CE" else "putLTP"
                                exit_price = row.get(ltp_key) or None
                                break
                except Exception as e:
                    logger.warning(f"Failed to auto-fetch LTP for close: {e}")

            if not exit_price:
                raise HTTPException(
                    status_code=400,
                    detail="Could not determine exit price. Please provide exit_price."
                )

        trade = paper_trade_service.close_paper_trade(db, trade_id, exit_price)
        if not trade:
            raise HTTPException(status_code=404, detail="Open trade not found")

        response = {
            "status": "success",
            "pnl": trade.pnl,
            "net_pnl": trade.net_pnl,
            "exit_price": trade.exit_price
        }
        logger.info(f"[DATA_SOURCE] endpoint=/paper/trade/close/{trade_id} source=DB")
        return attach_metadata(response, "DB", start_time)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades/active")
def get_active_paper_trades(db: Session = Depends(get_db)):
    """Get all open paper trades with live LTP and unrealized P&L."""
    start_time = time.time()
    try:
        # Build (strike, option_type) → ltp map from live option chain
        chain_ltp_map: Dict = {}
        try:
            chain = market_service.get_option_chain("NIFTY", num_strikes=5)
            if chain:
                for row in chain:
                    chain_ltp_map[(row["strike"], "CE")] = row.get("callLTP", 0)
                    chain_ltp_map[(row["strike"], "PE")] = row.get("putLTP", 0)
        except Exception as e:
            logger.warning(f"Could not fetch live LTPs for active trades: {e}")

        trades = paper_trade_service.get_active_trades_with_pnl(db, chain_ltp_map)
        response = {"status": "success", "data": trades}
        logger.info("[DATA_SOURCE] endpoint=/paper/trades/active source=DB")
        return attach_metadata(response, "DB", start_time)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades/history")
def get_paper_trade_history(db: Session = Depends(get_db)):
    """Get closed paper trades."""
    start_time = time.time()
    try:
        response = {"status": "success", "data": paper_trade_service.get_paper_trade_history(db, limit=100)}
        logger.info("[DATA_SOURCE] endpoint=/paper/trades/history source=DB")
        return attach_metadata(response, "DB", start_time)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
