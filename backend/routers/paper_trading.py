from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database.connection import get_db
from services.paper_trade_service import paper_trade_service

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
    try:
        account = paper_trade_service.initialize_account(db, req.balance)
        return {"status": "success", "message": f"Account initialized to {account.balance}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/account")
def get_account_summary(db: Session = Depends(get_db)):
    """Get paper account balance, realized PnL and high-level stats."""
    try:
        return {"status": "success", "data": paper_trade_service.get_account_summary(db)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trade/place")
def place_paper_trade(req: PlacePaperTradeRequest, db: Session = Depends(get_db)):
    """Place a new paper trade."""
    try:
        trade = paper_trade_service.place_paper_trade(db, req.dict())
        return {"status": "success", "trade_id": trade.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trade/close/{trade_id}")
def close_paper_trade(trade_id: int, req: ClosePaperTradeRequest, db: Session = Depends(get_db)):
    """Close an open paper trade."""
    try:
        trade = paper_trade_service.close_paper_trade(db, trade_id, req.exit_price)
        if not trade:
            raise HTTPException(status_code=404, detail="Open trade not found")
        return {
            "status": "success",
            "pnl": trade.pnl,
            "net_pnl": trade.net_pnl,
            "exit_price": trade.exit_price
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades/active")
def get_active_paper_trades(db: Session = Depends(get_db)):
    """Get all open paper trades."""
    try:
        return {"status": "success", "data": paper_trade_service.get_active_paper_trades(db)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades/history")
def get_paper_trade_history(db: Session = Depends(get_db)):
    """Get closed paper trades."""
    try:
        return {"status": "success", "data": paper_trade_service.get_paper_trade_history(db, limit=100)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
