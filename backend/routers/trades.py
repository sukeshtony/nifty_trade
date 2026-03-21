"""Trades API router — trade recording, closing, and history."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from database.connection import get_db
from services.trade_service import trade_service

router = APIRouter(prefix="/api/trades", tags=["Trades"])


# ── Request Models ──

class TradeCreate(BaseModel):
    symbol: str = "NIFTY"
    strike: int
    option_type: str  # CE or PE
    entry_price: float
    qty: int = 25
    trade_type: str = "INTRADAY"
    notes: Optional[str] = ""


class TradeClose(BaseModel):
    exit_price: float


# ── Endpoints ──

@router.post("")
def create_trade(trade_data: TradeCreate, db: Session = Depends(get_db)):
    """Record a new trade."""
    trade = trade_service.record_trade(db, trade_data.model_dump())
    return {"message": "Trade recorded", "trade_id": trade.id}


@router.put("/{trade_id}/close")
def close_trade(trade_id: int, data: TradeClose, db: Session = Depends(get_db)):
    """Close an open trade with exit price."""
    trade = trade_service.close_trade(db, trade_id, data.exit_price)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found or already closed")
    return {
        "message": "Trade closed",
        "trade_id": trade.id,
        "pnl": trade.pnl,
        "net_pnl": trade.net_pnl,
        "charges": trade.charges,
    }


@router.get("/active")
def get_active_trades(db: Session = Depends(get_db)):
    """Get all open trades."""
    trades = trade_service.get_active_trades(db)
    return {"trades": trades, "count": len(trades)}


@router.get("/history")
def get_trade_history(limit: int = 50, db: Session = Depends(get_db)):
    """Get closed trade history."""
    trades = trade_service.get_trade_history(db, limit)
    return {"trades": trades, "count": len(trades)}


@router.get("/summary")
def get_trade_summary(db: Session = Depends(get_db)):
    """Get overall trading performance summary."""
    return trade_service.get_trade_summary(db)
