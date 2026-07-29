from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.modules.scout_outcome_memory import (
    build_outcome_memory,
    classify_market_regime,
    load_latest_outcome_memory,
    match_outcome_lessons,
)
from src.modules import scout_performance
from src.modules.scout_research import build_research_packets, validate_research_reviews


def _record(
    snapshot_date: str,
    alpha: float,
    ticker: str = "TEST",
    regime: str = "BEAR",
) -> dict:
    return {
        "snapshot_date": snapshot_date,
        "bucket": "candidate",
        "status": "OK",
        "ticker": ticker,
        "country": "US",
        "sector": "Technology",
        "primary_lane": "pullback",
        "signal_keys": ["bb_squeeze"],
        "factor_positives": ["liquidity_good"],
        "factor_negatives": [],
        "theme_industry_status": "CAUTION",
        "sector_rrg_quadrant": "LAGGING",
        "theme_keys": ["semiconductors"],
        "quality_auditor_status": "STRONG_QUALITY",
        "catalyst_classification": "NOISE",
        "catalyst_event_types": ["earnings"],
        "catalyst_has_upcoming": True,
        "benchmark": {
            "market_regime": {"status": regime},
            "alpha": {"d5": {"alpha_pct": alpha}},
        },
    }


def _candidate() -> dict:
    return {
        "ticker": "NOW",
        "country": "US",
        "sector": "Technology",
        "signal_keys": ["bb_squeeze"],
        "factor_context": {"positives": ["liquidity_good"], "negatives": []},
        "quality_auditor": {"status": "STRONG_QUALITY", "source": "fmp"},
        "theme_industry": {
            "status": "CAUTION",
            "sector": {"quadrant": "LAGGING"},
            "themes": [{"theme_key": "semiconductors"}],
        },
        "catalyst_context": {
            "classification": "NOISE",
            "freshness": {"has_upcoming": True},
            "news": [{"event_type": "earnings"}],
        },
        "top3_selection": {
            "primary_lane": "pullback",
            "primary_lane_status": "PASS",
            "tier": "A",
            "production_gate_passed": True,
        },
        "decision_context": {"market_regime": {"status": "BEAR"}},
    }


def _cfg(**overrides) -> dict:
    base = {
        "horizons": [5],
        "min_records": 4,
        "min_independent_dates": 4,
        "min_recent_dates": 2,
        "recent_window_days": 20,
        "half_life_days": 30,
        "prior_strength_dates": 2,
        "stale_after_days": 60,
        "min_drift_alpha_pct": 2,
        "influence_mode": "advisory",
    }
    base.update(overrides)
    return base


def _lesson(memory: dict, cohort_type: str) -> dict:
    return next(
        row for row in memory["lessons"]
        if row["cohort_type"] == cohort_type and row["horizon"] == "d5"
    )


class OutcomeMemoryTests(unittest.TestCase):
    def test_same_day_candidates_count_as_one_independent_date(self):
        records = [_record("2026-07-01", 5.0, ticker=f"T{index}") for index in range(5)]
        memory = build_outcome_memory(
            records,
            "2026-07-29",
            cfg=_cfg(min_records=1, min_independent_dates=2),
            persist=False,
        )
        lesson = _lesson(memory, "signal")

        self.assertEqual(lesson["record_count"], 5)
        self.assertEqual(lesson["independent_date_count"], 1)
        self.assertEqual(lesson["status"], "COLLECTING")

    def test_repeated_negative_alpha_becomes_active_caution(self):
        records = [
            _record(f"2026-07-0{day}", -4.0 - day)
            for day in range(1, 5)
        ]
        memory = build_outcome_memory(records, "2026-07-29", cfg=_cfg(), persist=False)
        lesson = _lesson(memory, "signal_regime")

        self.assertEqual(lesson["status"], "ACTIVE_CAUTION")
        self.assertEqual(lesson["policy_effect"], "WEAKEN")
        self.assertLess(lesson["ci95_alpha_pct"]["high"], 0)

    def test_one_or_two_wins_never_become_skill(self):
        records = [
            _record("2026-07-01", 12.0),
            _record("2026-07-02", 15.0),
        ]
        memory = build_outcome_memory(records, "2026-07-29", cfg=_cfg(), persist=False)
        lesson = _lesson(memory, "setup")

        self.assertEqual(lesson["status"], "COLLECTING")
        self.assertEqual(lesson["policy_effect"], "NONE")

    def test_old_success_is_invalidated_after_recent_sign_flip(self):
        records = [
            _record("2026-05-01", 5.0),
            _record("2026-05-03", 6.0),
            _record("2026-05-05", 4.0),
            _record("2026-05-07", 7.0),
            _record("2026-07-20", -4.0),
            _record("2026-07-22", -5.0),
            _record("2026-07-24", -6.0),
            _record("2026-07-26", -3.0),
        ]
        memory = build_outcome_memory(
            records,
            "2026-07-29",
            cfg=_cfg(min_records=8, min_independent_dates=8),
            persist=False,
        )
        lesson = _lesson(memory, "setup_regime")

        self.assertEqual(lesson["status"], "INVALIDATED_BY_DRIFT")
        self.assertEqual(lesson["policy_effect"], "WEAKEN")
        self.assertGreater(lesson["drift"]["older_mean_alpha_pct"], 0)
        self.assertLess(lesson["drift"]["recent_mean_alpha_pct"], 0)

    def test_only_prior_day_memory_is_loadable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            for day in ("2026-07-27", "2026-07-28", "2026-07-29"):
                (directory / f"outcome_memory_{day}.json").write_text(
                    json.dumps({
                        "schema_version": "scout_outcome_memory_v0_1",
                        "as_of_date": day,
                        "source": {
                            "point_in_time": True,
                            "benchmark_relative": True,
                        },
                    }),
                    encoding="utf-8",
                )
            memory = load_latest_outcome_memory("2026-07-29", directory=directory)

        self.assertEqual(memory["as_of_date"], "2026-07-28")

    def test_actionable_cohort_is_attached_as_provenance_evidence(self):
        records = [
            _record(f"2026-07-0{day}", -4.0 - day)
            for day in range(1, 5)
        ]
        memory = build_outcome_memory(records, "2026-07-10", cfg=_cfg(), persist=False)
        matched = match_outcome_lessons(_candidate(), memory, max_lessons=6)
        packets = build_research_packets(
            [_candidate()],
            "2026-07-11",
            outcome_memory=memory,
            max_outcome_lessons=6,
        )
        historical = [
            row for row in packets[0]["evidence"]
            if row["category"] == "historical_outcome"
        ]

        self.assertTrue(matched)
        self.assertTrue(all(row["value"]["policy_effect"] == "WEAKEN" for row in historical))
        self.assertTrue(all(row["source"] == "derived:scout.outcome_memory" for row in historical))
        self.assertEqual(packets[0]["outcome_memory_as_of"], "2026-07-10")

        historical_id = historical[0]["evidence_id"]
        current_id = next(
            row["evidence_id"] for row in packets[0]["evidence"]
            if row["category"] != "historical_outcome"
        )
        review = {
            "ticker": "NOW",
            "disposition": "DROP",
            "memory_effect": "WEAKEN",
            "memory_evidence_refs": [historical_id],
            "bull_case": {"summary": "bull", "evidence_refs": [current_id]},
            "bear_case": {"summary": "bear", "evidence_refs": [historical_id]},
            "risk_case": {"summary": "risk", "evidence_refs": [historical_id]},
            "invalidation": {"summary": "invalidate", "evidence_refs": [current_id]},
        }
        reviews, error = validate_research_reviews([review], packets)
        self.assertFalse(error)
        self.assertEqual(reviews["NOW"]["memory_effect"], "WEAKEN")

        review["memory_effect"] = "SUPPORT"
        _, error = validate_research_reviews([review], packets)
        self.assertEqual(error, "memory_effect_mismatch:NOW")

    def test_market_regime_uses_only_supplied_history(self):
        frame = pd.DataFrame({
            "Date": pd.date_range("2026-01-01", periods=220),
            "Close": [100 + index * 0.2 for index in range(220)],
        })
        full = classify_market_regime(frame)
        prefix = classify_market_regime(frame.iloc[:200])

        self.assertEqual(full["as_of"], "2026-08-08")
        self.assertEqual(prefix["as_of"], "2026-07-19")
        self.assertEqual(prefix["status"], "BULL")

    def test_performance_keeps_memory_effect_as_unproven_comparison(self):
        weaken = _record("2026-07-01", -3.0)
        weaken["outcome_memory_effect"] = "WEAKEN"
        neutral = _record("2026-07-02", 2.0)
        neutral["outcome_memory_effect"] = "NONE"
        comparison = scout_performance._outcome_memory_comparison([weaken, neutral])

        self.assertEqual(comparison["evidence_status"], "COLLECTING_UNTOUCHED_WINDOW")
        self.assertFalse(comparison["counterfactual_proven"])
        self.assertFalse(comparison["winner_declared"])
        self.assertEqual(comparison["groups"]["WEAKEN"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
