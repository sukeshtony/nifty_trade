from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database.connection import get_db
from services.paper_trade_service import paper_trade_service
from utils.helpers import attach_metadata
import time
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/paper", tags=["Paper Trading"])


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
    exit_price: float


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
    """Place a new paper trade."""
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
    """Close an open paper trade."""
    start_time = time.time()
    try:
        trade = paper_trade_service.close_paper_trade(db, trade_id, req.exit_price)
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
    """Get all open paper trades."""
    start_time = time.time()
    try:
        response = {"status": "success", "data": paper_trade_service.get_active_paper_trades(db)}
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
