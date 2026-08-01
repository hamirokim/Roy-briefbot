from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.modules import scout_performance


def _ohlcv(start: str, periods: int, open_start: float, close_step: float) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=periods)
    opens = np.full(periods, open_start, dtype=float)
    closes = open_start + np.arange(periods, dtype=float) * close_step
    return pd.DataFrame({
        "Date": dates,
        "Open": opens,
        "High": np.maximum(opens, closes) + 1,
        "Low": np.minimum(opens, closes) - 1,
        "Close": closes,
        "Volume": np.full(periods, 1_000_000),
    })


def _alpha_record(
    date: str,
    ticker: str,
    bucket: str,
    d20_alpha: float,
    rank: int = 1,
) -> dict:
    return {
        "snapshot_date": date,
        "ticker": ticker,
        "bucket": bucket,
        "rank": rank,
        "status": "OK",
        "production_policy_id": "integrity_v1",
        "followup": {"d5": {}, "d10": {}, "d20": {}},
        "benchmark": {
            "alpha": {
                "d5": {"alpha_pct": d20_alpha},
                "d10": {"alpha_pct": d20_alpha},
                "d20": {"alpha_pct": d20_alpha},
            }
        },
    }


class ExecutableSessionTests(unittest.TestCase):
    def setUp(self):
        self.df = _ohlcv("2026-07-14", 5, 100, 1)

    def test_us_morning_kst_uses_same_us_calendar_date_open(self):
        idx, policy = scout_performance._first_executable_index(
            self.df,
            {
                "snapshot_date": "2026-07-15",
                "generated_at": "2026-07-15T07:10:00+09:00",
                "country": "US",
            },
        )
        self.assertEqual(pd.Timestamp(self.df["Date"].iloc[idx]).date().isoformat(), "2026-07-15")
        self.assertEqual(policy["price_field"], "Open")

    def test_kr_after_close_uses_next_session(self):
        idx, _ = scout_performance._first_executable_index(
            self.df,
            {
                "snapshot_date": "2026-07-15",
                "generated_at": "2026-07-15T18:15:00+09:00",
                "country": "KR",
            },
        )
        self.assertEqual(pd.Timestamp(self.df["Date"].iloc[idx]).date().isoformat(), "2026-07-16")

    def test_evaluation_uses_open_and_calculates_benchmark_alpha(self):
        candidate = _ohlcv("2026-07-01", 35, 100, 2)
        benchmark = _ohlcv("2026-07-01", 35, 200, 1)
        record = {
            "snapshot_date": "2026-07-02",
            "generated_at": "2026-07-02T07:10:00+09:00",
            "ticker": "TEST",
            "country": "US",
            "benchmark_ticker": "SPY",
        }
        evaluated = scout_performance._evaluate_record(
            record,
            {"TEST": candidate, "SPY": benchmark},
        )

        self.assertEqual(evaluated["entry_price_used"], 100)
        self.assertEqual(evaluated["execution_policy"]["price_field"], "Open")
        expected_alpha = (
            evaluated["followup"]["d5"]["return_pct"]
            - evaluated["benchmark"]["followup"]["d5"]["return_pct"]
        )
        self.assertEqual(evaluated["benchmark"]["alpha"]["d5"]["alpha_pct"], round(expected_alpha, 2))

    def test_regime_ignores_prices_after_entry(self):
        benchmark = _ohlcv("2025-01-01", 240, 100, 0.2)
        entry_idx = 220
        before = scout_performance._market_regime(benchmark, entry_idx)
        mutated = benchmark.copy()
        mutated.loc[entry_idx:, "Close"] = 1
        after = scout_performance._market_regime(mutated, entry_idx)
        self.assertEqual(before, after)


class DecisionAuditTests(unittest.TestCase):
    def test_zero_pick_with_positive_rejected_alpha_is_missed_opportunity(self):
        snapshot = {
            "date": "2026-07-01",
            "candidates": [],
            "summary": {"decision_health": {"status": "HEALTHY_ABSTENTION"}},
        }
        audits = scout_performance._decision_audits(
            [_alpha_record("2026-07-01", "MISSED", "radar_top", 5.0)],
            [snapshot],
        )
        self.assertEqual(audits[0]["abstention_status"], "MISSED_OPPORTUNITY")
        self.assertEqual(audits[0]["abstention_horizon"], "d20")
        self.assertEqual(audits[0]["horizons"]["d20"]["opportunity_cost_pct"], 5.0)

    def test_abstention_uses_latest_mature_horizon(self):
        snapshot = {
            "date": "2026-07-03",
            "candidates": [],
            "summary": {"decision_health": {"status": "HEALTHY_ABSTENTION"}},
        }
        record = _alpha_record("2026-07-03", "EARLY", "radar_top", 2.0)
        record["benchmark"]["alpha"]["d20"]["alpha_pct"] = None
        record["benchmark"]["alpha"]["d10"]["alpha_pct"] = -1.0
        audits = scout_performance._decision_audits([record], [snapshot])
        self.assertEqual(audits[0]["abstention_horizon"], "d10")
        self.assertEqual(audits[0]["abstention_status"], "GOOD_ABSTENTION")

    def test_selected_loser_and_rejected_winner_are_both_counted(self):
        snapshot = {
            "date": "2026-07-02",
            "candidates": [{"ticker": "SELECTED"}],
            "summary": {},
        }
        records = [
            _alpha_record("2026-07-02", "SELECTED", "candidate", -2.0),
            _alpha_record("2026-07-02", "REJECTED", "radar_top", 4.0),
        ]
        audits = scout_performance._decision_audits(records, [snapshot])
        d20 = audits[0]["horizons"]["d20"]
        self.assertEqual(d20["selected_nonpositive_alpha"], 1)
        self.assertEqual(d20["rejected_positive_alpha"], 1)
        self.assertEqual(d20["opportunity_cost_pct"], 6.0)

    def test_opportunity_cost_uses_ranked_alternative_not_hindsight_best(self):
        snapshot = {
            "date": "2026-07-04",
            "candidates": [{"ticker": "SELECTED"}],
            "summary": {},
        }
        records = [
            _alpha_record("2026-07-04", "SELECTED", "candidate", -2.0),
            _alpha_record("2026-07-04", "NEXT", "radar_top", -1.0, rank=1),
            _alpha_record("2026-07-04", "LUCKY", "radar_top", 10.0, rank=2),
        ]
        d20 = scout_performance._decision_audits(records, [snapshot])[0]["horizons"]["d20"]
        self.assertEqual(d20["ranked_alternative_ticker"], "NEXT")
        self.assertEqual(d20["opportunity_cost_pct"], 1.0)
        self.assertEqual(d20["ex_post_upper_bound_gap_pct"], 12.0)

    def test_policy_comparison_never_declares_winner_automatically(self):
        records = [
            _alpha_record("2026-07-02", "LIVE", "candidate", 1.0),
            _alpha_record("2026-07-02", "SHADOW", "shadow:us_precision_v1", 3.0),
        ]
        comparison = scout_performance._policy_comparison(records)
        self.assertFalse(comparison["winner_declared"])
        self.assertEqual(comparison["evidence_status"], "COLLECTING_FORWARD_EVIDENCE")

    def test_policy_comparison_separates_production_lanes(self):
        left = _alpha_record("2026-07-02", "LEFT", "candidate", 1.0)
        left.update({"primary_lane": "left_side", "primary_lane_status": "STAGE2_PASS"})
        strength = _alpha_record("2026-07-02", "STRONG", "candidate", -1.0)
        strength.update({"primary_lane": "strength", "primary_lane_status": "PASS"})
        cohorts = scout_performance._policy_comparison([left, strength])["cohorts"]
        self.assertEqual(cohorts["production_lane:integrity_v1:left_side"]["count"], 1)
        self.assertEqual(cohorts["production_lane:integrity_v1:strength"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
