"""Paper Trade Service — Handles mock trades and account capital for paper trading."""

from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
import logging

from database.models import PaperAccount, PaperTrade, TradeStatus
from utils.helpers import ist_now, ESTIMATED_CHARGES_PER_LOT

logger = logging.getLogger(__name__)

class PaperTradeService:
    """Manages paper trading account and order execution."""

    def get_or_create_account(self, db: Session, balance: float = 100000.0) -> PaperAccount:
        """Gets the single paper account or creates one if it doesn't exist."""
        account = db.query(PaperAccount).first()
        if not account:
            account = PaperAccount(initial_balance=balance, balance=balance, total_pnl=0.0)
            db.add(account)
            db.commit()
            db.refresh(account)
        return account

    def initialize_account(self, db: Session, balance: float) -> PaperAccount:
        """Reset or initialize the paper account with a specific balance."""
        account = self.get_or_create_account(db, balance)
        account.initial_balance = balance
        account.balance = balance
        account.total_pnl = 0.0
        
        # Close all active paper trades on reset
        open_trades = db.query(PaperTrade).filter(PaperTrade.status == TradeStatus.OPEN).all()
        for t in open_trades:
            t.status = TradeStatus.CLOSED
            t.exit_time = ist_now()
            t.exit_price = t.entry_price # mock close
            
        db.commit()
        db.refresh(account)
        logger.info(f"Paper account initialized with balance {balance}")
        return account

    def get_account_summary(self, db: Session) -> Dict[str, Any]:
        """Get paper account balance, realized PnL and high-level stats."""
        account = self.get_or_create_account(db)
        
        closed_trades = db.query(PaperTrade).filter(PaperTrade.status == TradeStatus.CLOSED).all()
        pnls = [t.pnl or 0 for t in closed_trades]
        winning = sum(1 for p in pnls if p > 0)
        losing = sum(1 for p in pnls if p < 0)
        total_pnl = sum(pnls)
        total_charges = sum(t.charges or 0 for t in closed_trades)

        return {
            "initial_balance": account.initial_balance,
            "available_balance": account.balance,
            "realized_pnl": account.total_pnl,
            "total_trades": len(closed_trades),
            "winning_trades": winning,
            "losing_trades": losing,
            "win_rate": round((winning / len(closed_trades)) * 100, 1) if closed_trades else 0,
            "total_charges": round(total_charges, 2)
        }

    def place_paper_trade(self, db: Session, trade_data: Dict) -> PaperTrade:
        """Record a new paper trade entry."""
        account = self.get_or_create_account(db)
        
        trade = PaperTrade(
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
        logger.info(f"Paper Trade recorded: {trade.id} — {trade.option_type} {trade.strike}")
        return trade

    def close_paper_trade(self, db: Session, trade_id: int, exit_price: float) -> Optional[PaperTrade]:
        """Close a paper trade, calculate P&L, update account balance."""
        trade = db.query(PaperTrade).filter(PaperTrade.id == trade_id, PaperTrade.status == TradeStatus.OPEN).first()
        if not trade:
            return None

        account = self.get_or_create_account(db)

        trade.exit_price = exit_price
        trade.exit_time = ist_now()
        trade.status = TradeStatus.CLOSED

        # P&L calculation
        if trade.option_type == "CE":
             trade.pnl = round((exit_price - trade.entry_price) * trade.qty, 2)
        else:  # PE
             trade.pnl = round((exit_price - trade.entry_price) * trade.qty, 2)

        # Charges (approx: brokerage + STT + GST + etc.)
        lots = trade.qty / 25
        trade.charges = round(ESTIMATED_CHARGES_PER_LOT * lots * 2, 2)
        trade.net_pnl = round(trade.pnl - trade.charges, 2)

        # Update account balance
        account.total_pnl += trade.net_pnl
        account.balance += trade.net_pnl

        db.commit()
        db.refresh(trade)
        logger.info(f"Paper Trade closed: {trade.id} — PnL: {trade.pnl}, Net: {trade.net_pnl}")
        return trade

    def get_active_paper_trades(self, db: Session) -> List[Dict]:
        """Get all open paper trades."""
        trades = db.query(PaperTrade).filter(PaperTrade.status == TradeStatus.OPEN).all()
        return [self._trade_to_dict(t) for t in trades]

    def get_paper_trade_history(self, db: Session, limit: int = 50) -> List[Dict]:
        """Get closed paper trades."""
        trades = (
            db.query(PaperTrade)
            .filter(PaperTrade.status == TradeStatus.CLOSED)
            .order_by(PaperTrade.exit_time.desc())
            .limit(limit)
            .all()
        )
        return [self._trade_to_dict(t) for t in trades]

    def _trade_to_dict(self, trade: PaperTrade) -> Dict:
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
paper_trade_service = PaperTradeService()
