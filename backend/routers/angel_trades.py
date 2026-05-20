"""Angel Trades API router — real trade history from Angel One."""

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import AngelTrade
from services.angel_trade_sync import (
    parse_nifty_trades,
    match_round_trips,
    calculate_charges,
    sync_todays_trades,
)
from services.market_data_service import market_service
from utils.cache import cache
from utils.helpers import attach_metadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/angel/trades", tags=["Angel Trades"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _trade_to_dict(t: AngelTrade) -> dict:
    """Serialize an AngelTrade ORM row to a JSON-friendly dict."""
    return {
        "id":              t.id,
        "symbol":          t.symbol,
        "strike":          t.strike,
        "option_type":     t.option_type,
        "trade_type":      t.trade_type,
        "entry_price":     t.entry_price,
        "exit_price":      t.exit_price,
        "qty":             t.qty,
        "lots":            t.qty // 25,
        "gross_pnl":       t.gross_pnl,
        "net_pnl":         t.net_pnl,
        "charges": {
            "brokerage":       t.brokerage,
            "stt":             t.stt,
            "exchange_charge": t.exchange_charge,
            "gst":             t.gst,
            "sebi_fee":        t.sebi_fee,
            "stamp_duty":      t.stamp_duty,
            "total":           t.total_charges,
        },
        "buy_trade_id":    t.buy_trade_id,
        "sell_trade_id":   t.sell_trade_id,
        "buy_order_id":    t.buy_order_id,
        "sell_order_id":   t.sell_order_id,
        "entry_time":      t.entry_time.isoformat() if t.entry_time else None,
        "exit_time":       t.exit_time.isoformat() if t.exit_time else None,
        "synced_at":       t.synced_at.isoformat() if t.synced_at else None,
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/today/live")
def get_live_today_trades():
    """Fetch today's Nifty option trades directly from Angel One (live, not DB).

    Returns raw parsed trades (individual BUY/SELL legs) for today.
    Does NOT persist to DB — use /sync for that.
    """
    start_time = time.time()
    raw = market_service.get_trade_book()
    parsed = parse_nifty_trades(raw)

    # Enrich each leg with charge calculation
    enriched = []
    for t in parsed:
        charges = calculate_charges(t["price"], t["qty"], t["transaction_type"])
        enriched.append({
            "trade_id":        t["trade_id"],
            "order_id":        t["order_id"],
            "symbol":          t["symbol"],
            "strike":          t["strike"],
            "option_type":     t["option_type"],
            "transaction_type": t["transaction_type"],
            "price":           t["price"],
            "qty":             t["qty"],
            "lots":            t["qty"] // 25,
            "fill_time":       t["fill_time"].isoformat() if t["fill_time"] else None,
            "product_type":    t["product_type"],
            "charges":         charges,
        })

    result = {
        "trades":      enriched,
        "count":       len(enriched),
        "raw_total":   len(raw),
    }
    return attach_metadata(result, "LIVE", start_time)


@router.get("/today/positions")
def get_live_positions():
    """Fetch current open positions with realised & unrealised P&L from Angel One.

    Returns Nifty NFO positions only.
    """
    start_time = time.time()
    positions = market_service.get_positions()

    nifty_positions = [
        p for p in positions
        if (p.get("exchange") or "").upper() == "NFO"
        and str(p.get("tradingsymbol") or "").upper().startswith("NIFTY")
    ]

    enriched = []
    for p in nifty_positions:
        enriched.append({
            "symbol":               p.get("tradingsymbol"),
            "exchange":             p.get("exchange"),
            "net_qty":              p.get("netqty", 0),
            "buy_qty":              p.get("buyqty", 0),
            "sell_qty":             p.get("sellqty", 0),
            "buy_avg_price":        p.get("buyavgprice", 0),
            "sell_avg_price":       p.get("sellavgprice", 0),
            "ltp":                  p.get("ltp", 0),
            "realised_pnl":         p.get("realisedprofitloss") or p.get("realised", 0),
            "unrealised_pnl":       p.get("unrealisedprofitloss") or p.get("unrealised", 0),
            "total_pnl":            round(
                float(p.get("realisedprofitloss") or 0) +
                float(p.get("unrealisedprofitloss") or 0), 2
            ),
        })

    result = {"positions": enriched, "count": len(enriched)}
    return attach_metadata(result, "LIVE", start_time)


@router.post("/sync")
def sync_angel_trades(db: Session = Depends(get_db)):
    """Trigger a manual sync: fetch today's trades from Angel One and save to DB.

    - Fetches the trade book from Angel One
    - Filters for Nifty NFO options only
    - Pairs BUY + SELL legs into closed round-trips
    - Persists to the angel_trades table (skips duplicates)
    """
    start_time = time.time()
    summary = sync_todays_trades(db)
    # Invalidate the history cache so the next GET reflects new data
    cache.delete("angel_trades:history")
    cache.delete("angel_trades:summary")
    return attach_metadata(summary, "API", start_time)


@router.get("/history")
def get_angel_trade_history(
    limit: int = Query(default=100, ge=1, le=500),
    option_type: Optional[str] = Query(default=None, description="Filter: CE or PE"),
    db: Session = Depends(get_db),
):
    """Retrieve synced Nifty trades from the local DB (most recent first).

    Args:
        limit:       Max number of records to return (1–500, default 100).
        option_type: Optional filter — "CE" or "PE".
    """
    start_time = time.time()
    cache_key = f"angel_trades:history:{limit}:{option_type}"
    cached = cache.get(cache_key)
    if cached:
        return attach_metadata(cached, "CACHE", start_time)

    query = db.query(AngelTrade).order_by(AngelTrade.entry_time.desc())
    if option_type:
        query = query.filter(AngelTrade.option_type == option_type.upper())
    trades = query.limit(limit).all()

    result = {
        "trades": [_trade_to_dict(t) for t in trades],
        "count":  len(trades),
    }
    cache.set(cache_key, result, ttl=60)
    return attach_metadata(result, "DB", start_time)


@router.get("/summary")
def get_angel_trade_summary(db: Session = Depends(get_db)):
    """Overall trading performance summary from synced Angel One trades.

    Returns:
        - Total trades, win/loss counts, win rate
        - Gross P&L, total charges breakdown, net P&L
        - Best and worst trade
        - Average trade metrics
    """
    start_time = time.time()
    cached = cache.get("angel_trades:summary")
    if cached:
        return attach_metadata(cached, "CACHE", start_time)

    trades = db.query(AngelTrade).all()

    if not trades:
        result = {
            "total_trades":    0,
            "winning":         0,
            "losing":          0,
            "breakeven":       0,
            "win_rate":        0,
            "gross_pnl":       0,
            "net_pnl":         0,
            "total_charges":   0,
            "charge_breakdown": {
                "brokerage":       0,
                "stt":             0,
                "exchange_charge": 0,
                "gst":             0,
                "sebi_fee":        0,
                "stamp_duty":      0,
            },
            "avg_gross_pnl":   0,
            "avg_net_pnl":     0,
            "best_trade":      None,
            "worst_trade":     None,
        }
        return attach_metadata(result, "DB", start_time)

    winning  = [t for t in trades if t.net_pnl > 0]
    losing   = [t for t in trades if t.net_pnl < 0]
    breakeven= [t for t in trades if t.net_pnl == 0]

    best  = max(trades, key=lambda t: t.net_pnl)
    worst = min(trades, key=lambda t: t.net_pnl)

    total_gross   = round(sum(t.gross_pnl    for t in trades), 2)
    total_net     = round(sum(t.net_pnl      for t in trades), 2)
    total_charges = round(sum(t.total_charges for t in trades), 2)

    result = {
        "total_trades":  len(trades),
        "winning":       len(winning),
        "losing":        len(losing),
        "breakeven":     len(breakeven),
        "win_rate":      round(len(winning) / len(trades) * 100, 1) if trades else 0,
        "gross_pnl":     total_gross,
        "net_pnl":       total_net,
        "total_charges": total_charges,
        "charge_breakdown": {
            "brokerage":       round(sum(t.brokerage       for t in trades), 2),
            "stt":             round(sum(t.stt             for t in trades), 4),
            "exchange_charge": round(sum(t.exchange_charge for t in trades), 4),
            "gst":             round(sum(t.gst             for t in trades), 4),
            "sebi_fee":        round(sum(t.sebi_fee        for t in trades), 6),
            "stamp_duty":      round(sum(t.stamp_duty      for t in trades), 4),
        },
        "avg_gross_pnl": round(total_gross / len(trades), 2),
        "avg_net_pnl":   round(total_net   / len(trades), 2),
        "best_trade": {
            "id":         best.id,
            "symbol":     best.symbol,
            "strike":     best.strike,
            "option_type": best.option_type,
            "net_pnl":    best.net_pnl,
            "entry_time": best.entry_time.isoformat() if best.entry_time else None,
        },
        "worst_trade": {
            "id":         worst.id,
            "symbol":     worst.symbol,
            "strike":     worst.strike,
            "option_type": worst.option_type,
            "net_pnl":    worst.net_pnl,
            "entry_time": worst.entry_time.isoformat() if worst.entry_time else None,
        },
    }
    cache.set("angel_trades:summary", result, ttl=120)
    return attach_metadata(result, "DB", start_time)
