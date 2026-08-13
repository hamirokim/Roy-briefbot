from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.agents import scout
from main import update_cooldown_from_scout


def _ohlcv(closes: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(closes), freq="B")
    close = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volumes or [1_000_000.0] * len(close),
        },
        index=index,
    )


def _candidate(ticker: str, *, timing: str = "EARLY", quality: str = "STRONG_QUALITY") -> dict:
    return {
        "ticker": ticker,
        "country": "US",
        "market_cap": 5_000_000_000,
        "quality_auditor": {"status": quality, "source": "fmp"},
        "catalyst_context": {"classification": "NOISE"},
        "factor_context": {"negatives": []},
        "quality_flags": [],
        "price_lanes": {
            "left_side": {
                "status": "WAIT_CONFIRM",
                "reasons": ["low_zone", "down_days_decreasing"],
                "review_flags": [],
                "metrics": {"deceleration_count": 2},
            }
        },
        "pre_entry_timing": {
            "status": timing,
            "setup_date": "2026-07-01",
            "move_from_setup_pct": 0.02,
        },
        "price_map": {
            "available": True,
            "support": {"lower": 30.0, "upper": 31.0},
            "first_resistance": {"lower": 35.0, "upper": 36.0},
            "reward_risk_to_first_resistance": 2.0,
        },
        "theme_industry": {
            "status": "SUPPORT",
            "sector": {"name": "Technology", "quadrant": "IMPROVING"},
            "themes": [],
        },
    }


def _selection_config() -> dict:
    return {
        "pre_entry": {
            "enabled": True,
            "policy_id": "pre_entry_v1",
            "max_picks": 2,
            "cooldown_days": 10,
            "allowed_countries": ["US", "KR"],
            "allowed_lane_statuses": ["STAGE1_WAIT", "WAIT_CONFIRM", "STAGE2_PASS"],
            "allowed_timeliness": ["EARLY", "READY"],
            "allowed_sector_quadrants": ["LEADING", "IMPROVING"],
            "mapped_theme_statuses": ["GROUP_SUPPORT"],
            "allow_unmapped_theme": True,
            "quality_statuses": ["QUALITY_SUPPORT", "STRONG_QUALITY"],
            "excluded_factor_negatives": ["chasing_hot"],
            "excluded_quality_flags": ["overextended_20d"],
            "excluded_lane_review_flags": ["market_weak_wait_confirm"],
            "risk_catalyst_excluded": True,
        }
    }


class PreEntryTests(unittest.TestCase):
    def test_twenty_day_high_does_not_promote_left_side_candidate(self):
        closes = list(np.linspace(100, 50, 100))
        closes += [45, 44, 43, 42, 41, 40, 41, 42, 43, 44]
        closes += [42, 43, 44, 45, 46, 47, 48, 49, 50, 55]
        result = scout._assess_left_side_lane(_ohlcv(closes), None, {})

        self.assertEqual(result["status"], "STAGE2_PASS")
        self.assertIn("higher_high_context", result["reasons"])
        self.assertNotIn("higher_high_bonus", result["reasons"])

    def test_price_map_uses_confirmed_swings_and_atr_zones(self):
        closes = list(np.linspace(60, 40, 80))
        closes += [42, 40, 41, 39, 41, 43, 42, 45, 44, 47, 45, 48, 46, 49, 47, 48, 47, 48, 47, 48]
        result = scout._assess_price_map(_ohlcv(closes), {})

        self.assertTrue(result["available"])
        self.assertEqual(result["method"], "confirmed_swings_plus_atr")
        self.assertLess(result["support"]["lower"], result["support"]["upper"])
        self.assertLessEqual(result["support"]["center"], result["current"])
        self.assertGreater(result["invalidation_close_below"], 0)

    def test_selector_rejects_late_and_missed_candidates(self):
        selected, audit, cooldown = scout._select_pre_entry_candidates(
            [
                _candidate("EARLY"),
                _candidate("READY", timing="READY"),
                _candidate("LATE", timing="LATE"),
                _candidate("MISSED", timing="MISSED"),
            ],
            _selection_config(),
            {},
            "2026-08-13",
        )

        self.assertEqual([item["ticker"] for item in selected], ["EARLY", "READY"])
        self.assertEqual(audit["rejection_counts"]["timeliness_late"], 1)
        self.assertEqual(audit["rejection_counts"]["timeliness_missed"], 1)
        self.assertEqual(cooldown, {"EARLY": "2026-08-13", "READY": "2026-08-13"})

    def test_pre_entry_cooldown_is_separate_and_does_not_backfill(self):
        selected, audit, _ = scout._select_pre_entry_candidates(
            [_candidate("COOL"), _candidate("GOOD")],
            _selection_config(),
            {"COOL": "2026-08-10"},
            "2026-08-13",
        )

        self.assertEqual([item["ticker"] for item in selected], ["GOOD"])
        self.assertEqual(audit["rejection_counts"]["cooldown"], 1)
        self.assertFalse(audit["criteria"]["backfill"])

    def test_pre_entry_cooldown_is_persisted_separately(self):
        state = {
            "scout_out": {
                "new_cooldown": {"FINAL": "2026-08-13"},
                "new_pre_entry_cooldown": {"EARLY": "2026-08-13"},
            }
        }

        update_cooldown_from_scout(state)

        self.assertEqual(state["scout_cooldown"], {"FINAL": "2026-08-13"})
        self.assertEqual(state["scout_pre_entry_cooldown"], {"EARLY": "2026-08-13"})


if __name__ == "__main__":
    unittest.main()
