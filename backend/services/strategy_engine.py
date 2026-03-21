"""Strategy Engine — Pure logic-based BUY CE / BUY PE / NO TRADE signal generation.

NO AI/ML. Uses rule-based conditions with confidence scoring.
"""

from typing import Dict, Any, List
import logging
import json

logger = logging.getLogger(__name__)


class StrategyEngine:
    """Generates clear trading signals from market data + indicators + options."""

    def generate_signal(
        self,
        market_state: Dict[str, Any],
        options_data: Dict[str, Any],
        indicators: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate BUY CE / BUY PE / NO TRADE signal with explanation."""

        conditions = self._evaluate_conditions(market_state, options_data, indicators)
        signal, confidence, direction, reasons = self._decide(conditions)

        # Determine trade type based on time
        from utils.helpers import ist_now
        now = ist_now()
        hour = now.hour
        minute = now.minute
        trade_type = "POSITIONAL" if (hour > 15 or (hour == 15 and minute > 15)) else "INTRADAY"

        return {
            "signal": signal,
            "direction": direction,
            "trade_type": trade_type,
            "confidence": confidence,
            "conditions": conditions,
            "reasons": reasons,
            "explanation": self._build_explanation(conditions, signal, reasons),
        }

    def _evaluate_conditions(
        self,
        state: Dict[str, Any],
        options: Dict[str, Any],
        indicators: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Evaluate each condition from the strategy rules."""
        conditions = []
        price = state.get("current_price", 0)

        # ── 1. EMA Alignment ──
        ema_9 = state.get("ema_9") or indicators.get("ema", {}).get("ema_9")
        ema_21 = state.get("ema_21") or indicators.get("ema", {}).get("ema_21")

        if ema_9 and ema_21:
            if ema_9 > ema_21:
                conditions.append({
                    "name": "EMA Trend",
                    "status": "EMA9 > EMA21 (Bullish crossover)",
                    "bias": "bullish",
                    "weight": 2,
                })
            elif ema_9 < ema_21:
                conditions.append({
                    "name": "EMA Trend",
                    "status": "EMA9 < EMA21 (Bearish crossover)",
                    "bias": "bearish",
                    "weight": 2,
                })
            else:
                conditions.append({
                    "name": "EMA Trend",
                    "status": "EMA9 ≈ EMA21 (No trend)",
                    "bias": "neutral",
                    "weight": 2,
                })

        # ── 2. VWAP ──
        vwap = state.get("vwap") or indicators.get("vwap")
        if vwap and price:
            vwap_dist = ((price - vwap) / vwap) * 100 if vwap else 0

            if vwap_dist > 0.1:
                conditions.append({
                    "name": "VWAP",
                    "status": f"Price ABOVE VWAP ({vwap_dist:+.2f}%)",
                    "bias": "bullish",
                    "weight": 2,
                })
            elif vwap_dist < -0.1:
                conditions.append({
                    "name": "VWAP",
                    "status": f"Price BELOW VWAP ({vwap_dist:+.2f}%)",
                    "bias": "bearish",
                    "weight": 2,
                })
            else:
                conditions.append({
                    "name": "VWAP",
                    "status": f"Price NEAR VWAP ({vwap_dist:+.2f}%) — Sideways",
                    "bias": "neutral",
                    "weight": 2,
                })

        # ── 3. PCR ──
        pcr = options.get("pcr", 0)
        if pcr:
            if pcr > 1.0:
                conditions.append({
                    "name": "PCR",
                    "status": f"PCR = {pcr} (Put writing dominant → Bullish)",
                    "bias": "bullish",
                    "weight": 1.5,
                })
            elif pcr < 0.7:
                conditions.append({
                    "name": "PCR",
                    "status": f"PCR = {pcr} (Call writing dominant → Bearish)",
                    "bias": "bearish",
                    "weight": 1.5,
                })
            else:
                conditions.append({
                    "name": "PCR",
                    "status": f"PCR = {pcr} (Neutral zone)",
                    "bias": "neutral",
                    "weight": 1.5,
                })

        # ── 4. OI Buildup ──
        dominant_build = options.get("dominant_buildup", "NONE")
        if dominant_build in ["LONG_BUILD_UP", "SHORT_COVERING"]:
            conditions.append({
                "name": "OI Buildup",
                "status": f"{dominant_build.replace('_', ' ').title()} → Bullish",
                "bias": "bullish",
                "weight": 1.5,
            })
        elif dominant_build in ["SHORT_BUILD_UP", "LONG_UNWINDING"]:
            conditions.append({
                "name": "OI Buildup",
                "status": f"{dominant_build.replace('_', ' ').title()} → Bearish",
                "bias": "bearish",
                "weight": 1.5,
            })

        # ── 5. Support/Resistance Proximity ──
        oi_support = options.get("oi_support")
        oi_resistance = options.get("oi_resistance")
        sup_res = indicators.get("support_resistance", {})
        session_support = sup_res.get("support") or state.get("session_low")
        session_resistance = sup_res.get("resistance") or state.get("session_high")

        if oi_support and price:
            dist_to_support = ((price - oi_support) / oi_support) * 100
            if 0 < dist_to_support < 0.5:
                conditions.append({
                    "name": "Support Proximity",
                    "status": f"Near OI support {oi_support} — Potential bounce",
                    "bias": "bullish",
                    "weight": 1,
                })

        if oi_resistance and price:
            dist_to_resistance = ((oi_resistance - price) / oi_resistance) * 100
            if 0 < dist_to_resistance < 0.5:
                conditions.append({
                    "name": "Resistance Proximity",
                    "status": f"Near OI resistance {oi_resistance} — Potential rejection",
                    "bias": "bearish",
                    "weight": 1,
                })

        # Check for breakout above resistance
        if session_resistance and price and price > session_resistance:
            conditions.append({
                "name": "Breakout",
                "status": f"Price broke above session high {session_resistance}",
                "bias": "bullish",
                "weight": 1.5,
            })

        if session_support and price and price < session_support:
            conditions.append({
                "name": "Breakdown",
                "status": f"Price broke below session low {session_support}",
                "bias": "bearish",
                "weight": 1.5,
            })

        # ── 6. Momentum ──
        momentum = state.get("momentum") or indicators.get("momentum")
        if momentum is not None:
            if momentum > 10:
                conditions.append({
                    "name": "Momentum",
                    "status": f"Strong upward momentum ({momentum:+.2f} pts)",
                    "bias": "bullish",
                    "weight": 1,
                })
            elif momentum < -10:
                conditions.append({
                    "name": "Momentum",
                    "status": f"Strong downward momentum ({momentum:+.2f} pts)",
                    "bias": "bearish",
                    "weight": 1,
                })

        # ── 7. Volume Spike ──
        vol = indicators.get("volume", {})
        if vol.get("spike"):
            conditions.append({
                "name": "Volume",
                "status": f"Volume spike detected ({vol.get('relative_volume', 0)}x average)",
                "bias": "neutral",  # confirms direction, doesn't set it
                "weight": 0.5,
            })

        return conditions

    def _decide(self, conditions: List[Dict]) -> tuple:
        """Decide signal based on weighted conditions."""
        bullish_weight = sum(c["weight"] for c in conditions if c["bias"] == "bullish")
        bearish_weight = sum(c["weight"] for c in conditions if c["bias"] == "bearish")
        total_weight = bullish_weight + bearish_weight

        if total_weight == 0:
            return "NO_TRADE", 0, "SIDEWAYS", ["Insufficient data to generate a signal"]

        bull_reasons = [c["status"] for c in conditions if c["bias"] == "bullish"]
        bear_reasons = [c["status"] for c in conditions if c["bias"] == "bearish"]
        neutral_reasons = [c["status"] for c in conditions if c["bias"] == "neutral"]

        # Check for conflicting signals
        max_possible_weight = sum(c["weight"] for c in conditions)

        if bullish_weight > bearish_weight * 1.5 and bullish_weight >= 3:
            confidence = min(round((bullish_weight / max_possible_weight) * 100, 1), 95)
            return "BUY_CE", confidence, "UP", bull_reasons

        elif bearish_weight > bullish_weight * 1.5 and bearish_weight >= 3:
            confidence = min(round((bearish_weight / max_possible_weight) * 100, 1), 95)
            return "BUY_PE", confidence, "DOWN", bear_reasons

        else:
            reasons = ["Conflicting or weak signals — no clear direction"]
            if neutral_reasons:
                reasons.extend(neutral_reasons)
            return "NO_TRADE", 0, "SIDEWAYS", reasons

    def _build_explanation(self, conditions: List[Dict], signal: str, reasons: List[str]) -> Dict:
        """Build human-readable explanation for the signal."""
        cond_map = {c["name"]: c for c in conditions}

        return {
            "ema_status": cond_map.get("EMA Trend", {}).get("status", "N/A"),
            "vwap_status": cond_map.get("VWAP", {}).get("status", "N/A"),
            "pcr_status": cond_map.get("PCR", {}).get("status", "N/A"),
            "oi_status": cond_map.get("OI Buildup", {}).get("status", "N/A"),
            "momentum_status": cond_map.get("Momentum", {}).get("status", "N/A"),
            "support_resistance": (
                cond_map.get("Support Proximity", {}).get("status")
                or cond_map.get("Resistance Proximity", {}).get("status")
                or cond_map.get("Breakout", {}).get("status")
                or cond_map.get("Breakdown", {}).get("status")
                or "N/A"
            ),
            "volume_status": cond_map.get("Volume", {}).get("status", "Normal"),
            "final_reasoning": f"{signal}: {'; '.join(reasons[:3])}",
        }


# Global singleton
strategy_engine = StrategyEngine()
