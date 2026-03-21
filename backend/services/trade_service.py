"""Trade Service — Trade execution tracking and P&L calculations."""

from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
import logging

from database.models import Trade, TradeStatus
from utils.helpers import ist_now, ESTIMATED_CHARGES_PER_LOT

logger = logging.getLogger(__name__)


class TradeService:
    """Manages trade CRUD, P&L, and execution tracking."""

    def record_trade(self, db: Session, trade_data: Dict) -> Trade:
        """Record a new trade entry."""
        trade = Trade(
            symbol=trade_data.get("symbol", "NIFTY"),
            strike=trade_data["strike"],
            option_type=trade_data["option_type"],  # CE or PE
            entry_price=trade_data["entry_price"],
            qty=trade_data.get("qty", 25),
            entry_time=trade_data.get("entry_time", ist_now()),
            trade_type=trade_data.get("trade_type", "INTRADAY"),
            notes=trade_data.get("notes", ""),
            status=TradeStatus.OPEN,
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)
        logger.info(f"Trade recorded: {trade.id} — {trade.option_type} {trade.strike}")
        return trade

    def close_trade(self, db: Session, trade_id: int, exit_price: float) -> Optional[Trade]:
        """Close a trade and calculate P&L."""
        trade = db.query(Trade).filter(Trade.id == trade_id, Trade.status == TradeStatus.OPEN).first()
        if not trade:
            return None

        trade.exit_price = exit_price
        trade.exit_time = ist_now()
        trade.status = TradeStatus.CLOSED

        # P&L calculation
        if trade.option_type == "CE":
            trade.pnl = round((exit_price - trade.entry_price) * trade.qty, 2)
        else:  # PE
            trade.pnl = round((exit_price - trade.entry_price) * trade.qty, 2)

        # Charges (approx: brokerage + STT + GST + etc.)
        lots = trade.qty / 25  # Nifty lot size
        trade.charges = round(ESTIMATED_CHARGES_PER_LOT * lots * 2, 2)  # Both sides
        trade.net_pnl = round(trade.pnl - trade.charges, 2)

        db.commit()
        db.refresh(trade)
        logger.info(f"Trade closed: {trade.id} — PnL: {trade.pnl}, Net: {trade.net_pnl}")
        return trade

    def get_active_trades(self, db: Session) -> List[Dict]:
        """Get all open trades."""
        trades = db.query(Trade).filter(Trade.status == TradeStatus.OPEN).all()
        return [self._trade_to_dict(t) for t in trades]

    def get_trade_history(self, db: Session, limit: int = 50) -> List[Dict]:
        """Get closed trades."""
        trades = (
            db.query(Trade)
            .filter(Trade.status == TradeStatus.CLOSED)
            .order_by(Trade.exit_time.desc())
            .limit(limit)
            .all()
        )
        return [self._trade_to_dict(t) for t in trades]

    def get_trade_summary(self, db: Session) -> Dict[str, Any]:
        """Calculate overall trading performance."""
        closed = db.query(Trade).filter(Trade.status == TradeStatus.CLOSED).all()
        if not closed:
            return {
                "total_trades": 0,
                "winning": 0,
                "losing": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "total_net_pnl": 0,
                "avg_pnl": 0,
            }

        pnls = [t.pnl or 0 for t in closed]
        winning = sum(1 for p in pnls if p > 0)
        losing = sum(1 for p in pnls if p < 0)
        total_pnl = sum(pnls)
        total_charges = sum(t.charges or 0 for t in closed)

        return {
            "total_trades": len(closed),
            "winning": winning,
            "losing": losing,
            "win_rate": round((winning / len(closed)) * 100, 1) if closed else 0,
            "total_pnl": round(total_pnl, 2),
            "total_charges": round(total_charges, 2),
            "total_net_pnl": round(total_pnl - total_charges, 2),
            "avg_pnl": round(total_pnl / len(closed), 2) if closed else 0,
        }

    def calculate_live_pnl(self, trade: Trade, current_ltp: float) -> Dict:
        """Calculate live P&L for an open trade."""
        live_pnl = round((current_ltp - trade.entry_price) * trade.qty, 2)
        lots = trade.qty / 25
        estimated_charges = round(ESTIMATED_CHARGES_PER_LOT * lots * 2, 2)
        roi = round((live_pnl / (trade.entry_price * trade.qty)) * 100, 2) if trade.entry_price else 0

        return {
            "live_pnl": live_pnl,
            "estimated_charges": estimated_charges,
            "estimated_net_pnl": round(live_pnl - estimated_charges, 2),
            "roi_pct": roi,
        }

    def _trade_to_dict(self, trade: Trade) -> Dict:
        return {
            "id": trade.id,
            "symbol": trade.symbol,
            "strike": trade.strike,
            "option_type": trade.option_type,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "qty": trade.qty,
            "pnl": trade.pnl,
            "net_pnl": trade.net_pnl,
            "charges": trade.charges,
            "status": trade.status.value if trade.status else "OPEN",
            "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
            "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
            "trade_type": trade.trade_type.value if trade.trade_type else "INTRADAY",
            "notes": trade.notes,
        }


# Global singleton
trade_service = TradeService()
