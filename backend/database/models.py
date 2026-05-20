"""SQLAlchemy ORM models for the Nifty Trading application."""

from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, Enum
)
from sqlalchemy.sql import func
from database.connection import Base
import enum


# ── Enums ──

class SignalType(str, enum.Enum):
    BUY_CE = "BUY_CE"
    BUY_PE = "BUY_PE"
    NO_TRADE = "NO_TRADE"


class TradeType(str, enum.Enum):
    INTRADAY = "INTRADAY"
    POSITIONAL = "POSITIONAL"


class DirectionType(str, enum.Enum):
    UP = "UP"
    DOWN = "DOWN"
    SIDEWAYS = "SIDEWAYS"


class TradeStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


# ── Trades ──

class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, default="NIFTY")
    strike = Column(Integer, nullable=False)
    option_type = Column(String(5), nullable=False)  # CE or PE
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float)
    qty = Column(Integer, default=25)  # Nifty lot size
    pnl = Column(Float, default=0.0)
    net_pnl = Column(Float, default=0.0)
    charges = Column(Float, default=0.0)
    status = Column(Enum(TradeStatus), default=TradeStatus.OPEN)
    entry_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime)
    trade_type = Column(Enum(TradeType), default=TradeType.INTRADAY)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ── Signals ──

class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal = Column(Enum(SignalType), nullable=False)
    trade_type = Column(Enum(TradeType), nullable=False)
    direction = Column(Enum(DirectionType), nullable=False)
    confidence = Column(Float, default=0.0)
    reason = Column(Text)
    indicators_snapshot = Column(Text)  # JSON string of indicator values at signal time
    created_at = Column(DateTime, server_default=func.now())


# ── Paper Trading ──

class PaperAccount(Base):
    __tablename__ = "paper_account"

    id = Column(Integer, primary_key=True, autoincrement=True)
    initial_balance = Column(Float, nullable=False, default=100000.0)
    balance = Column(Float, nullable=False, default=100000.0)
    total_pnl = Column(Float, default=0.0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, default="NIFTY")
    strike = Column(Integer, nullable=False)
    option_type = Column(String(5), nullable=False)  # CE or PE
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float)
    qty = Column(Integer, default=25)
    pnl = Column(Float, default=0.0)
    net_pnl = Column(Float, default=0.0)
    charges = Column(Float, default=0.0)
    status = Column(Enum(TradeStatus), default=TradeStatus.OPEN)
    entry_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime)
    trade_type = Column(Enum(TradeType), default=TradeType.INTRADAY)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ── Angel One Synced Trades ──

class AngelTrade(Base):
    """Stores real executed trades fetched from Angel One's trade book API.

    Each row represents one closed round-trip (BUY + SELL pair) for a
    Nifty options position.  The pair is uniquely identified by the
    combination of buy_trade_id and sell_trade_id from Angel One.
    """
    __tablename__ = "angel_trades"

    id             = Column(Integer, primary_key=True, autoincrement=True)

    # Angel One identifiers (for deduplication)
    buy_trade_id   = Column(String(50), nullable=False, index=True)
    sell_trade_id  = Column(String(50), nullable=False, index=True)
    buy_order_id   = Column(String(50), nullable=True)
    sell_order_id  = Column(String(50), nullable=True)

    # Instrument details
    symbol         = Column(String(50), nullable=False, default="NIFTY")
    strike         = Column(Integer, nullable=False)
    option_type    = Column(String(5), nullable=False)   # CE or PE
    trade_type     = Column(String(20), default="INTRADAY")  # INTRADAY / POSITIONAL

    # Prices & quantity
    entry_price    = Column(Float, nullable=False)
    exit_price     = Column(Float, nullable=False)
    qty            = Column(Integer, nullable=False, default=25)

    # P&L
    gross_pnl      = Column(Float, default=0.0)   # before charges
    net_pnl        = Column(Float, default=0.0)   # after all charges

    # Charge breakdown (BUY leg + SELL leg combined)
    brokerage      = Column(Float, default=0.0)   # ₹20 × 2 = ₹40 typically
    stt            = Column(Float, default=0.0)   # Securities Transaction Tax
    exchange_charge= Column(Float, default=0.0)   # NSE exchange transaction charge
    gst            = Column(Float, default=0.0)   # 18% on brokerage + exchange
    sebi_fee       = Column(Float, default=0.0)   # SEBI regulatory fee
    stamp_duty     = Column(Float, default=0.0)   # State stamp duty (buy side)
    total_charges  = Column(Float, default=0.0)   # Sum of all above

    # Timestamps
    entry_time     = Column(DateTime, nullable=True)
    exit_time      = Column(DateTime, nullable=True)
    synced_at      = Column(DateTime, nullable=True)   # when this record was fetched
    created_at     = Column(DateTime, server_default=func.now())

