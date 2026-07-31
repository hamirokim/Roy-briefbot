import unittest
from unittest.mock import patch

import pandas as pd

from src.agents.digest import DigestAgent
from src.collectors.core_etf_valuation import (
    classify_equity_metrics,
    collect_core_etf_valuations,
    extract_equity_metrics,
)


def _table(ticker: str, fund: list[float], category: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            ticker: fund,
            "Category Average": category,
        },
        index=["Price/Earnings", "Price/Book", "Price/Sales", "Price/Cashflow"],
    )


class CoreEtfValuationTests(unittest.TestCase):
    def test_extracts_yfinance_equity_holding_multiples(self):
        metrics = extract_equity_metrics(
            _table("VTI", [20, 3, 2, 12], [25, 4, 2.5, 15]),
            "VTI",
        )
        self.assertEqual(set(metrics), {"pe", "pb", "ps", "pcf"})
        self.assertEqual(metrics["pe"]["difference_pct"], -20.0)

    def test_three_lower_multiples_are_relative_low(self):
        metrics = extract_equity_metrics(
            _table("VTI", [20, 3, 2, 20], [25, 4, 2.5, 15]),
            "VTI",
        )
        result = classify_equity_metrics(metrics)
        self.assertEqual(result["status"], "RELATIVE_LOW")

    def test_two_lower_and_two_higher_are_mixed(self):
        metrics = extract_equity_metrics(
            _table("VTI", [20, 5, 2, 20], [25, 4, 2.5, 15]),
            "VTI",
        )
        result = classify_equity_metrics(metrics)
        self.assertEqual(result["status"], "MIXED")

    def test_non_equity_assets_fail_closed(self):
        cfg = {
            "enabled": True,
            "tickers": ["SCHP", "IAUM"],
            "equity_tickers": [],
            "non_equity": {"SCHP": "tips_bond", "IAUM": "gold"},
        }
        result = collect_core_etf_valuations(cfg)
        self.assertEqual([item["ticker"] for item in result["items"]], ["SCHP", "IAUM"])
        self.assertTrue(all(item["status"] == "NOT_COMPARABLE" for item in result["items"]))

    def test_telegram_lists_all_eight_without_calling_them_fair_value(self):
        items = []
        for ticker, label, status in [
            ("VTI", "상대 낮음", "RELATIVE_LOW"),
            ("IXUS", "상대 낮음", "RELATIVE_LOW"),
            ("AVUV", "혼재", "MIXED"),
            ("AVDV", "혼재", "MIXED"),
            ("QQQM", "상대 높음", "RELATIVE_HIGH"),
            ("SCHP", "판정 보류", "NOT_COMPARABLE"),
            ("IAUM", "판정 보류", "NOT_COMPARABLE"),
            ("VT", "혼재", "MIXED"),
        ]:
            asset_type = "tips_bond" if ticker == "SCHP" else ("gold" if ticker == "IAUM" else "equity_etf")
            items.append({"ticker": ticker, "label": label, "status": status, "asset_type": asset_type})

        agent = DigestAgent.__new__(DigestAgent)
        agent.settings = {"digest": {"telegram": {"max_chars": 4000}}}
        message = agent._build_telegram(
            [],
            {},
            {
                "core_valuation": {
                    "enabled": True,
                    "items": items,
                    "complete_count": 6,
                    "total_count": 8,
                }
            },
            scout_out={"radar_summary": {"no_candidate_reason": "추천 기준 미달"}},
        )

        for ticker in ["VTI", "IXUS", "AVUV", "AVDV", "QQQM", "SCHP", "IAUM", "VT"]:
            self.assertIn(ticker, message)
        self.assertIn("메인포트 估值 | 6/8 판정", message)
        self.assertIn("절대 적정가 아님", message)


if __name__ == "__main__":
    unittest.main()
