"""Options Analytics Engine — PCR, Max Pain, OI analysis for Nifty options."""

from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class OptionsEngine:
    """Analyzes option chain data for Nifty — ATM ± 3 strikes only."""

    def analyze(self, chain_data: List[Dict], spot_price: float) -> Dict[str, Any]:
        """Master analysis from option chain data."""
        if not chain_data:
            return {"error": "No option chain data available"}

        total_call_oi = sum(r.get("callOI", 0) for r in chain_data)
        total_put_oi = sum(r.get("putOI", 0) for r in chain_data)
        pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0

        max_pain = self._calculate_max_pain(chain_data)
        support_resistance = self._find_oi_support_resistance(chain_data, spot_price)
        dominant_build = self._dominant_buildup(chain_data)

        return {
            "spot_price": spot_price,
            "total_call_oi": total_call_oi,
            "total_put_oi": total_put_oi,
            "pcr": pcr,
            "pcr_interpretation": self._interpret_pcr(pcr),
            "max_pain": max_pain,
            "oi_support": support_resistance.get("support"),
            "oi_resistance": support_resistance.get("resistance"),
            "dominant_buildup": dominant_build,
            "strikes": chain_data,
        }

    def _calculate_max_pain(self, chain: List[Dict]) -> Optional[float]:
        """Max Pain = strike where total option buyer loss is minimum."""
        if not chain:
            return None

        strikes = [r["strike"] for r in chain]
        min_pain = float("inf")
        max_pain_strike = None

        for test_strike in strikes:
            total_pain = 0
            for row in chain:
                sp = row["strike"]
                call_oi = row.get("callOI", 0)
                put_oi = row.get("putOI", 0)
                if test_strike > sp:
                    total_pain += (test_strike - sp) * call_oi
                if test_strike < sp:
                    total_pain += (sp - test_strike) * put_oi
            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = test_strike

        return max_pain_strike

    def _find_oi_support_resistance(self, chain: List[Dict], spot: float) -> Dict:
        """Highest put OI = support, highest call OI = resistance."""
        above = [r for r in chain if r["strike"] >= spot]
        below = [r for r in chain if r["strike"] <= spot]

        resistance = max(above, key=lambda x: x.get("callOI", 0))["strike"] if above else None
        support = max(below, key=lambda x: x.get("putOI", 0))["strike"] if below else None

        return {"support": support, "resistance": resistance}

    def _dominant_buildup(self, chain: List[Dict]) -> str:
        """Find dominant OI buildup pattern across strikes."""
        counts = {}
        for row in chain:
            for key in ["callBuild", "putBuild"]:
                b = row.get(key)
                if b:
                    counts[b] = counts.get(b, 0) + 1
        if counts:
            return max(counts, key=counts.get)
        return "NONE"

    def _interpret_pcr(self, pcr: float) -> str:
        if pcr > 1.3:
            return "STRONGLY_BULLISH"
        elif pcr > 1.0:
            return "BULLISH"
        elif pcr > 0.7:
            return "NEUTRAL"
        elif pcr > 0.5:
            return "BEARISH"
        else:
            return "STRONGLY_BEARISH"


# Global singleton
options_engine = OptionsEngine()
