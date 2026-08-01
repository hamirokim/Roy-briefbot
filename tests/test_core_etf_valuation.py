import unittest
from unittest.mock import patch

import pandas as pd

from src.agents.digest import DigestAgent
from src.collectors.core_etf_valuation import (
    _collect_non_equity,
    classify_equity_metrics,
    collect_core_etf_valuations,
    extract_equity_metrics,
)


def _table(ticker: str, fund: list[float], category=None) -> pd.DataFrame:
    data = {ticker: fund}
    if category is not None:
        data["Category Average"] = category
    return pd.DataFrame(
        data,
        index=["Price/Earnings", "Price/Book", "Price/Sales", "Price/Cashflow"],
    )


def _metrics(values):
    return {
        key: {"label": key.upper(), "fund": value}
        for key, value in zip(("pe", "pb", "ps", "pcf"), values)
    }


class CoreEtfValuationTests(unittest.TestCase):
    def test_extracts_fund_multiples_without_category_average(self):
        metrics = extract_equity_metrics(
            _table("VTI", [0.04, 0.25, 0.5, 0.1]),
            "VTI",
        )
        self.assertEqual(set(metrics), {"pe", "pb", "ps", "pcf"})
        self.assertEqual(metrics["pe"]["fund"], 25.0)
        self.assertEqual(metrics["pb"]["fund"], 4.0)

    def test_three_lower_multiples_are_relative_low(self):
        result = classify_equity_metrics(
            _metrics([20, 3, 2, 20]),
            _metrics([25, 4, 2.5, 15]),
            "VT",
        )
        self.assertEqual(result["status"], "RELATIVE_LOW")
        self.assertEqual(result["peer_ticker"], "VT")

    def test_two_lower_and_two_higher_are_mixed(self):
        result = classify_equity_metrics(
            _metrics([20, 5, 2, 20]),
            _metrics([25, 4, 2.5, 15]),
            "VT",
        )
        self.assertEqual(result["status"], "MIXED")

    @patch("src.collectors.core_etf_valuation._collect_equity_ticker")
    @patch("src.collectors.core_etf_valuation._collect_non_equity")
    @patch("src.collectors.core_etf_valuation._real_yield_context")
    def test_all_eight_use_role_or_asset_specific_contracts(
        self,
        real_yield_mock,
        non_equity_mock,
        equity_mock,
    ):
        real_yield_mock.return_value = {"value": 1.8, "percentile_5y": 65}
        equity_mock.side_effect = lambda ticker: {
            "ticker": ticker,
            "asset_type": "equity_etf",
            "source": "test",
            "metrics": _metrics([20, 3, 2, 12]),
        }
        non_equity_mock.side_effect = lambda ticker, asset_type, real_yield, cfg: {
            "ticker": ticker,
            "asset_type": asset_type,
            "status": "ASSET_SPECIFIC_OK",
            "label": "자산별 판정",
            "reason": "test",
            "metrics": {},
        }
        cfg = {
            "enabled": True,
            "tickers": ["VTI", "IXUS", "AVUV", "AVDV", "QQQM", "SCHP", "IAUM", "VT"],
            "equity_tickers": ["VTI", "IXUS", "AVUV", "AVDV", "QQQM", "VT"],
            "non_equity": {"SCHP": "tips_bond", "IAUM": "gold"},
            "min_comparable_metrics": 3,
        }
        result = collect_core_etf_valuations(cfg)
        self.assertEqual(result["complete_count"], 8)
        self.assertEqual(result["total_count"], 8)
        self.assertEqual(result["items"][-1]["status"], "PORTFOLIO_BASELINE")

    @patch("src.collectors.core_etf_valuation._price_context")
    def test_tips_and_gold_have_different_labels(self, price_mock):
        price_mock.return_value = {
            "price": 40,
            "price_percentile_5y": 80,
            "price_percentile_52w": 70,
            "nav": 40,
            "nav_premium_pct": 0,
        }
        real_yield = {"value": 2.0, "percentile_5y": 80, "change_20obs": 0.2}
        cfg = {"percentile_low_pct": 30, "percentile_high_pct": 70}
        schp = _collect_non_equity("SCHP", "tips_bond", real_yield, cfg)
        iaum = _collect_non_equity("IAUM", "gold", real_yield, cfg)
        self.assertEqual(schp["label"], "실질금리 기회 높음")
        self.assertEqual(iaum["label"], "가격 부담 높음")

    def test_telegram_explains_asset_specific_output_and_blockers(self):
        items = [
            {"ticker": "VTI", "label": "상대 낮음", "status": "RELATIVE_LOW", "asset_type": "equity_etf"},
            {"ticker": "VT", "label": "글로벌 기준", "status": "PORTFOLIO_BASELINE", "asset_type": "equity_etf"},
            {"ticker": "SCHP", "label": "실질금리 기회 높음", "status": "INCOME_OPPORTUNITY_HIGH", "asset_type": "tips_bond", "reason": "10년 실질금리 2.00% · 5년 80백분위"},
            {"ticker": "IAUM", "label": "가격 부담 높음", "status": "PRICE_BURDEN_HIGH", "asset_type": "gold", "reason": "5년 가격 80백분위 · 실질금리 상승"},
        ]
        agent = DigestAgent.__new__(DigestAgent)
        agent.settings = {"digest": {"telegram": {"max_chars": 4000}}}
        message = agent._build_telegram(
            [], {},
            {"core_valuation": {"enabled": True, "items": items, "complete_count": 4, "total_count": 4}},
            scout_out={"radar_summary": {"decision_health": {"blockers": {"tier_not_allowed": 80, "lane_not_allowed": 14}}}},
        )
        self.assertIn("메인포트 가격·估值 상태 | 4/4 판정", message)
        self.assertIn("SCHP: 실질금리 기회 높음", message)
        self.assertIn("품질·근거 Tier 미달 80개", message)
        self.assertIn("좌측진입 단계 미달 14개", message)
        self.assertIn("절대 적정가 아님", message)

    def test_journal_detail_accepts_non_equity_scalar_metrics(self):
        agent = DigestAgent.__new__(DigestAgent)
        lines = agent._build_journal_regime({
            "core_valuation": {
                "enabled": True,
                "items": [
                    {
                        "ticker": "VTI",
                        "label": "상대 높음",
                        "reason": "VT 대비",
                        "peer_ticker": "VT",
                        "metrics": {"pe": {"label": "P/E", "fund": 25.0}},
                    },
                    {
                        "ticker": "SCHP",
                        "label": "실질금리 기회 높음",
                        "reason": "10년 실질금리 2.0%",
                        "metrics": {"price": 26.0, "real_yield": {"value": 2.0}},
                    },
                ],
            }
        })
        text = "\n".join(lines)
        self.assertIn("ETF 배수: P/E 25.0 · 비교 기준 VT", text)
        self.assertIn("SCHP: 실질금리 기회 높음", text)


if __name__ == "__main__":
    unittest.main()
