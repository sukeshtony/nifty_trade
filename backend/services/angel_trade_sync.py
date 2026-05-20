"""Angel Trade Sync — fetch, parse, charge-calculate and persist Angel One trades.

Supports only Nifty NFO options (CE / PE).
Angel One flat brokerage plan: ₹20 per executed order.

Charge formula (per trade leg):
  brokerage        = ₹20.00 flat (per executed order)
  stt              = 0.05% × turnover  (SELL side only for options)
  exchange_charge  = 0.053% × premium turnover
  gst              = 18% × (brokerage + exchange_charge)
  sebi_fee         = ₹10 per crore of turnover  → (turnover / 1_00_00_000) × 10
  stamp_duty       = 0.003% × turnover (BUY side only)
  total            = sum of all above

Typical flow:
  1.  sync_todays_trades(db)  — called at startup and at 15:35 IST
  2.  parse_nifty_trades()    — filter & normalize raw Angel One trade book rows
  3.  calculate_charges()     — compute each charge component
  4.  match_round_trips()     — pair BUY + SELL legs into closed positions
  5.  save_to_db()            — upsert into `angel_trades` table (skip duplicates)
"""

import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.orm import Session

from database.models import AngelTrade
from utils.helpers import ist_now

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

NIFTY_LOT_SIZE = 25

# Regex to parse Angel One NFO option symbols like:
#   NIFTY08MAY25C24000  → strike=24000, type=CE
#   NIFTY08MAY25P23500  → strike=23500, type=PE
_NIFTY_OPT_RE = re.compile(
    r"^NIFTY\d{2}[A-Z]{3}\d{2}([CP])(\d+)$",
    re.IGNORECASE,
)


# ── Charge Calculator ──────────────────────────────────────────────────────────

def calculate_charges(
    price: float,
    qty: int,
    transaction_type: str,   # "BUY" or "SELL"
) -> Dict[str, float]:
    """Calculate all statutory charges for one executed Nifty options trade leg.

    Args:
        price: Execution price per unit (premium in ₹)
        qty:   Quantity (in lots × lot_size, e.g., 25 or 50)
        transaction_type: "BUY" or "SELL"

    Returns:
        Dict with individual charge components and a "total" key.
    """
    turnover = round(price * qty, 2)
    side = transaction_type.upper()

    brokerage       = 20.00                                      # flat per order
    exchange_charge = round(turnover * 0.00053, 4)               # 0.053% of premium turnover
    stt             = round(turnover * 0.0005, 4) if side == "SELL" else 0.0   # 0.05% sell side
    gst             = round((brokerage + exchange_charge) * 0.18, 4)            # 18%
    sebi_fee        = round((turnover / 1_00_00_000) * 10, 6)   # ₹10 per crore
    stamp_duty      = round(turnover * 0.00003, 4) if side == "BUY" else 0.0   # 0.003% buy side

    total = round(brokerage + exchange_charge + stt + gst + sebi_fee + stamp_duty, 2)

    return {
        "brokerage":       brokerage,
        "exchange_charge": exchange_charge,
        "stt":             stt,
        "gst":             gst,
        "sebi_fee":        sebi_fee,
        "stamp_duty":      stamp_duty,
        "total":           total,
        "turnover":        turnover,
    }


# ── Symbol Parser ──────────────────────────────────────────────────────────────

def _parse_nifty_option_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """Extract strike price and option type from a Nifty option trading symbol.

    Returns {"strike": int, "option_type": "CE"/"PE"} or None if not a Nifty option.
    """
    m = _NIFTY_OPT_RE.match(symbol.upper().strip())
    if not m:
        return None
    opt_char, strike_str = m.group(1), m.group(2)
    return {
        "strike":      int(strike_str),
        "option_type": "CE" if opt_char.upper() == "C" else "PE",
    }


def parse_nifty_trades(raw_trades: List[Dict]) -> List[Dict]:
    """Filter and normalize raw Angel One trade book entries for Nifty NFO options.

    Angel One tradeBook returns all executed trades across all segments.
    We keep only:
      - exchange == "NFO"
      - tradingsymbol starts with "NIFTY" and matches CE/PE regex
      - status == "complete" (skip partial fills that may re-appear)

    Returns a list of normalized trade dicts ready for processing.
    """
    result = []
    for t in raw_trades:
        exchange = (t.get("exchange") or "").upper()
        symbol   = (t.get("tradingsymbol") or "").strip()

        # Only NFO Nifty options
        if exchange != "NFO":
            continue

        parsed = _parse_nifty_option_symbol(symbol)
        if not parsed:
            continue

        trade_id  = str(t.get("tradeid") or t.get("tradeId") or "")
        order_id  = str(t.get("orderid") or t.get("orderId") or "")
        txn_type  = (t.get("transactiontype") or t.get("transactionType") or "").upper()
        qty_raw   = t.get("quantity") or t.get("qty") or 0
        price_raw = t.get("price") or t.get("tradeprice") or 0
        fill_time = t.get("filltime") or t.get("updatetime") or t.get("tradeTime") or ""
        product   = (t.get("producttype") or t.get("productType") or "INTRADAY").upper()

        try:
            qty   = int(qty_raw)
            price = float(price_raw)
        except (ValueError, TypeError):
            logger.warning(f"Skipping trade with invalid qty/price: {t}")
            continue

        if not trade_id or qty <= 0 or price <= 0:
            continue

        if txn_type not in ("BUY", "SELL"):
            continue

        # Parse fill time
        fill_dt = None
        for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
            try:
                fill_dt = datetime.strptime(fill_time, fmt)
                break
            except (ValueError, AttributeError):
                continue

        result.append({
            "trade_id":       trade_id,
            "order_id":       order_id,
            "symbol":         symbol,
            "strike":         parsed["strike"],
            "option_type":    parsed["option_type"],
            "transaction_type": txn_type,
            "price":          price,
            "qty":            qty,
            "product_type":   "INTRADAY" if "INTRADAY" in product or "MIS" in product else "POSITIONAL",
            "fill_time":      fill_dt,
        })

    logger.info(f"Parsed {len(result)} Nifty NFO trades from {len(raw_trades)} raw entries")
    return result


# ── Round-Trip Matcher ─────────────────────────────────────────────────────────

def match_round_trips(trades: List[Dict]) -> List[Dict]:
    """Pair BUY and SELL legs for the same symbol into closed round-trip positions.

    Uses a simple FIFO queue per symbol:
    - BUY legs are pushed into a queue
    - SELL legs are matched against the earliest unmatched BUY

    Returns a list of closed position dicts with gross P&L and combined charges.
    Also returns unpaired legs (open positions) separately.

    Output format for each matched pair:
    {
        "buy_trade_id", "sell_trade_id",
        "symbol", "strike", "option_type",
        "entry_price", "exit_price", "qty",
        "gross_pnl", "buy_charges", "sell_charges",
        "total_charges", "net_pnl",
        "entry_time", "exit_time", "product_type"
    }
    """
    from collections import defaultdict, deque

    buy_queue: Dict[str, deque] = defaultdict(deque)
    matched = []

    # Sort by fill time so FIFO is time-based
    sorted_trades = sorted(trades, key=lambda x: x.get("fill_time") or datetime.min)

    for t in sorted_trades:
        sym = t["symbol"]
        if t["transaction_type"] == "BUY":
            buy_queue[sym].append(t)
        elif t["transaction_type"] == "SELL":
            if buy_queue[sym]:
                buy_leg = buy_queue[sym].popleft()
                qty     = min(buy_leg["qty"], t["qty"])

                gross_pnl = round((t["price"] - buy_leg["price"]) * qty, 2)

                buy_charges  = calculate_charges(buy_leg["price"],  qty, "BUY")
                sell_charges = calculate_charges(t["price"],        qty, "SELL")
                total_charges = round(buy_charges["total"] + sell_charges["total"], 2)

                matched.append({
                    "buy_trade_id":   buy_leg["trade_id"],
                    "sell_trade_id":  t["trade_id"],
                    "buy_order_id":   buy_leg["order_id"],
                    "sell_order_id":  t["order_id"],
                    "symbol":         sym,
                    "strike":         buy_leg["strike"],
                    "option_type":    buy_leg["option_type"],
                    "entry_price":    buy_leg["price"],
                    "exit_price":     t["price"],
                    "qty":            qty,
                    "gross_pnl":      gross_pnl,
                    "buy_charges":    buy_charges,
                    "sell_charges":   sell_charges,
                    "total_charges":  total_charges,
                    "net_pnl":        round(gross_pnl - total_charges, 2),
                    "entry_time":     buy_leg["fill_time"],
                    "exit_time":      t["fill_time"],
                    "product_type":   buy_leg.get("product_type", "INTRADAY"),
                })
            else:
                # Sell without matching buy — short position (unusual for retail)
                logger.debug(f"Unmatched SELL for {sym} trade {t['trade_id']}")

    return matched


# ── DB Persistence ─────────────────────────────────────────────────────────────

def save_matched_trades(db: Session, matched: List[Dict]) -> Tuple[int, int]:
    """Upsert matched round-trip trades into the angel_trades table.

    Returns (inserted, skipped) counts.
    """
    inserted = 0
    skipped  = 0

    for m in matched:
        # Idempotent: skip if this pair already exists (keyed by buy+sell trade IDs)
        existing = (
            db.query(AngelTrade)
            .filter(
                AngelTrade.buy_trade_id  == m["buy_trade_id"],
                AngelTrade.sell_trade_id == m["sell_trade_id"],
            )
            .first()
        )
        if existing:
            skipped += 1
            continue

        buy_c  = m["buy_charges"]
        sell_c = m["sell_charges"]

        record = AngelTrade(
            buy_trade_id   = m["buy_trade_id"],
            sell_trade_id  = m["sell_trade_id"],
            buy_order_id   = m.get("buy_order_id", ""),
            sell_order_id  = m.get("sell_order_id", ""),
            symbol         = m["symbol"],
            strike         = m["strike"],
            option_type    = m["option_type"],
            entry_price    = m["entry_price"],
            exit_price     = m["exit_price"],
            qty            = m["qty"],
            gross_pnl      = m["gross_pnl"],
            net_pnl        = m["net_pnl"],
            # Charges (combined buy + sell)
            brokerage      = round(buy_c["brokerage"]       + sell_c["brokerage"],       2),
            stt            = round(buy_c["stt"]             + sell_c["stt"],             4),
            exchange_charge= round(buy_c["exchange_charge"] + sell_c["exchange_charge"], 4),
            gst            = round(buy_c["gst"]             + sell_c["gst"],             4),
            sebi_fee       = round(buy_c["sebi_fee"]        + sell_c["sebi_fee"],        6),
            stamp_duty     = round(buy_c["stamp_duty"]      + sell_c["stamp_duty"],      4),
            total_charges  = m["total_charges"],
            entry_time     = m["entry_time"],
            exit_time      = m["exit_time"],
            trade_type     = m.get("product_type", "INTRADAY"),
            synced_at      = ist_now(),
        )
        db.add(record)
        inserted += 1

    db.commit()
    logger.info(f"Angel trades sync: {inserted} inserted, {skipped} skipped (duplicates)")
    return inserted, skipped


# ── Main Sync Entry Point ──────────────────────────────────────────────────────

def sync_todays_trades(db: Session) -> Dict[str, Any]:
    """Full sync pipeline: fetch → parse → match → persist.

    Called at startup and at 15:35 IST by the background scheduler.
    Returns a summary dict.
    """
    from services.market_data_service import market_service

    if not market_service._connected:
        logger.warning("Angel One not connected — skipping trade sync")
        return {"status": "skipped", "reason": "not_connected"}

    raw = market_service.get_trade_book()
    if not raw:
        return {"status": "ok", "raw_trades": 0, "inserted": 0, "skipped": 0}

    parsed  = parse_nifty_trades(raw)
    matched = match_round_trips(parsed)
    inserted, skipped = save_matched_trades(db, matched)

    return {
        "status":        "ok",
        "raw_trades":    len(raw),
        "nifty_trades":  len(parsed),
        "round_trips":   len(matched),
        "inserted":      inserted,
        "skipped":       skipped,
        "synced_at":     ist_now().isoformat(),
    }
