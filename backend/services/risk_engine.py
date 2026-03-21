"""
Risk Engine — stop-loss, target, R:R validation, and position sizing.

Rules:
  Stop Loss   = 1.2 × (ATR × option_delta_proxy)
  Target      = 2.0 × (ATR × option_delta_proxy)
  Min R:R     = 1.5 after slippage + spread
  Position    = integer lots, risk-capped, max MAX_LOTS

Daily guardrails:
  MAX_DAILY_RISK       = ₹3000 (hard stop for the session)
  MAX_CONSECUTIVE_LOSS = 3 losses in a row → pause trading
"""

from typing import Dict, Any, Optional, Tuple
from utils.helpers import LOT_SIZES
import logging

logger = logging.getLogger(__name__)

# ── Risk parameters (tune per account size) ───────────────────────────────────
FIXED_RISK_PER_TRADE  = 1000.0   # Max ₹ loss per individual trade
SL_ATR_MULT           = 1.2      # Stop loss = 1.2 × option-ATR proxy
TARGET_ATR_MULT       = 2.0      # Target   = 2.0 × option-ATR proxy
OPTION_DELTA_PROXY    = 0.60     # ATM Nifty option moves ~60% of spot ATR
MIN_RR_RATIO          = 1.5      # Minimum R:R after execution costs
MAX_LOTS              = 4        # Hard cap on lot size per trade
SLIPPAGE_PER_SIDE     = 0.50     # Points slippage per fill (Nifty ATM is liquid)
SPREAD_COST           = 1.00     # Bid-ask spread (Nifty ATM typical)
MAX_DAILY_RISK        = 3000.0   # Session-level loss limit (₹)
MAX_CONSECUTIVE_LOSS  = 3        # Consecutive loss limit before pause


class RiskEngine:
    """Calculates trade plan and enforces session-level guardrails."""

    def __init__(self):
        self._daily_loss       = 0.0
        self._consecutive_loss = 0
        self._trades_today     = 0

    def reset_daily(self):
        """Call at start of each session."""
        self._daily_loss       = 0.0
        self._consecutive_loss = 0
        self._trades_today     = 0
        logger.info("Risk engine daily counters reset")

    def record_trade_result(self, pnl: float):
        """Update daily tracking after a trade closes."""
        self._daily_loss   += min(pnl, 0.0)
        self._trades_today += 1
        if pnl < 0:
            self._consecutive_loss += 1
        else:
            self._consecutive_loss = 0

    @property
    def daily_loss(self) -> float:
        return self._daily_loss

    @property
    def consecutive_losses(self) -> int:
        return self._consecutive_loss

    @property
    def trades_today(self) -> int:
        return self._trades_today

    def validate_trade_allowed(self) -> Tuple[bool, str]:
        """
        Check session-level guardrails before allowing a new entry.
        Returns (allowed, reason_if_blocked).
        """
        if abs(self._daily_loss) >= MAX_DAILY_RISK:
            return False, (
                f"Daily loss limit reached: ₹{abs(self._daily_loss):.0f} "
                f"≥ ₹{MAX_DAILY_RISK:.0f} — trading paused for session"
            )
        if self._consecutive_loss >= MAX_CONSECUTIVE_LOSS:
            return False, (
                f"Consecutive loss limit: {self._consecutive_loss} losses in a row "
                f"— trading paused (reset manually or next session)"
            )
        return True, "OK"

    def calculate_trade_plan(
        self,
        signal:          str,           # "BUY_CE" or "BUY_PE"
        option_premium:  float,         # ATM option LTP (entry premium)
        atr:             float,         # Spot ATR from indicator engine
        spot_price:      float,
        symbol:          str = "NIFTY",
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Compute SL, target, R:R, and lot size for an options trade.

        Returns (plan, error).  error is None when plan is valid.
        """
        if not atr or atr <= 0:
            return None, "ATR unavailable — cannot size trade safely"

        if not option_premium or option_premium <= 0:
            return None, "Invalid option premium — cannot calculate plan"

        lot_size = LOT_SIZES.get(symbol, 25)

        # Option ATR proxy: spot ATR × delta
        opt_atr = atr * OPTION_DELTA_PROXY

        sl_pts     = round(SL_ATR_MULT   * opt_atr, 1)
        target_pts = round(TARGET_ATR_MULT * opt_atr, 1)

        # Execution cost (entry slippage + exit slippage + spread)
        exec_cost  = SLIPPAGE_PER_SIDE * 2 + SPREAD_COST

        net_gain = target_pts - exec_cost
        net_loss = sl_pts     + exec_cost

        if net_gain <= 0:
            return None, (
                f"Net gain after costs is negative or zero "
                f"(target={target_pts}pts, exec_cost={exec_cost}pts) — skip"
            )

        rr = round(net_gain / net_loss, 2)
        if rr < MIN_RR_RATIO:
            return None, (
                f"R:R {rr:.2f} below minimum {MIN_RR_RATIO} after slippage/spread "
                f"(sl={sl_pts}pts, target={target_pts}pts, cost={exec_cost}pts)"
            )

        # Position sizing: cap at FIXED_RISK_PER_TRADE
        risk_per_lot = sl_pts * lot_size
        if risk_per_lot <= 0:
            return None, "Risk per lot is zero — cannot size position"

        lots      = max(1, min(MAX_LOTS, int(FIXED_RISK_PER_TRADE / risk_per_lot)))
        total_risk = round(lots * risk_per_lot, 2)

        # Validate daily headroom
        if abs(self._daily_loss) + total_risk > MAX_DAILY_RISK:
            affordable = max(0, MAX_DAILY_RISK - abs(self._daily_loss))
            lots = max(1, int(affordable / risk_per_lot))
            if lots < 1:
                return None, (
                    f"Not enough daily risk budget left "
                    f"(used ₹{abs(self._daily_loss):.0f} of ₹{MAX_DAILY_RISK:.0f})"
                )
            total_risk = round(lots * risk_per_lot, 2)

        sl_price     = round(option_premium - sl_pts,     2)
        target_price = round(option_premium + target_pts, 2)

        return {
            "signal":             signal,
            "entry_premium":      round(option_premium, 2),
            "stop_loss_premium":  max(0.05, sl_price),
            "target_premium":     target_price,
            "sl_points":          sl_pts,
            "target_points":      target_pts,
            "rr_ratio":           rr,
            "lots":               lots,
            "lot_size":           lot_size,
            "total_qty":          lots * lot_size,
            "risk_per_lot":       round(risk_per_lot, 2),
            "total_risk":         total_risk,
            "atr_used":           atr,
            "spot_price":         spot_price,
            "exec_cost_estimate": round(exec_cost * lots * lot_size, 2),
            "invalidation_note":  (
                "Exit immediately if spot retraces back through entry EMA9 level "
                "or if premium drops below stop_loss_premium"
            ),
        }, None


# Global singleton
risk_engine = RiskEngine()
