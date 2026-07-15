from __future__ import annotations

import json
import logging
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents import digest, scout
from src.agents.digest import DigestAgent
from src.collectors import macro_calendar
from src.modules import scout_performance


ROOT = Path(__file__).resolve().parents[1]


def _candidate(ticker: str, tier: str = "A", quality: str = "STRONG_QUALITY") -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "country": "US",
        "score": 3.0,
        "signal_count": 3,
        "signals": {},
        "quality_flags": [],
        "quality_auditor": {"status": quality},
        "factor_context": {"negatives": []},
        "catalyst_context": {},
        "top3_selection": {
            "tier": tier,
            "tier_rank": 4 if tier == "A" else 3,
            "primary_lane": "strength",
            "primary_lane_status": "STRONG_PASS" if tier == "A" else "PASS",
            "lane_rank": 5 if tier == "A" else 4,
            "catalyst_freshness_rank": 0,
            "support_count": 1,
            "opportunity_score": 3.0,
            "excluded": False,
            "exclude_reason": "",
        },
    }


def _selection_config() -> dict:
    return {
        "enabled": True,
        "max_picks": 3,
        "tier_order": ["A", "B", "C", "D"],
        "production_gate": {
            "enabled": True,
            "allowed_tiers": ["A"],
            "quality_statuses": ["QUALITY_SUPPORT", "STRONG_QUALITY"],
            "excluded_quality_flags": ["overextended_20d", "low_liquidity_buffer"],
            "excluded_factor_negatives": ["liquidity_weak", "volatility_extreme", "chasing_extreme", "chasing_hot"],
            "backfill": False,
        },
        "llm_review": {"enabled": True, "additions_allowed": False, "candidate_limit": 12},
    }


class ProductionGateTests(unittest.TestCase):
    def test_2026_07_15_replay_returns_zero_without_backfill(self):
        payload = json.loads((ROOT / "data/scout/radar_pool_2026-07-15.json").read_text(encoding="utf-8"))
        selected, audit = scout._select_top3_candidates(
            payload["items"], 3, lambda item: True, _selection_config()
        )
        watchlist = scout._build_watchlist_candidates(payload["items"], selected, limit=5)

        self.assertEqual(selected, [])
        self.assertTrue(audit["production_gate"]["no_signal"])
        self.assertFalse(audit["production_gate"]["backfill"])
        self.assertEqual(audit["production_gate"]["rejection_counts"]["tier_not_allowed"], 48)
        self.assertEqual([item["selection_tier"] for item in watchlist[:3]], ["B", "B", "B"])

    def test_allows_only_confirmed_tier_a_without_risk_flags(self):
        good = _candidate("GOOD")
        tier_b = _candidate("TIERB", tier="B")
        no_quality = _candidate("NOQUALITY", quality="NEUTRAL")
        risky = _candidate("RISKY")
        risky["factor_context"]["negatives"] = ["liquidity_weak"]
        radar = [good, tier_b, no_quality, risky]

        with patch.object(scout, "_annotate_top3_selection", side_effect=lambda item: item["top3_selection"]):
            selected, audit = scout._select_top3_candidates(
                radar, 3, lambda item: True, _selection_config()
            )

        self.assertEqual([item["ticker"] for item in selected], ["GOOD"])
        self.assertEqual(audit["production_gate"]["rejection_counts"]["tier_not_allowed"], 1)
        self.assertEqual(audit["production_gate"]["rejection_counts"]["quality_not_confirmed"], 1)
        self.assertEqual(audit["production_gate"]["rejection_counts"]["factor_risk"], 1)

    def test_disabled_gate_does_not_mark_legacy_candidates_as_passed(self):
        legacy = _candidate("LEGACY", tier="B")
        config = _selection_config()
        config["production_gate"]["enabled"] = False

        with patch.object(scout, "_annotate_top3_selection", return_value=legacy["top3_selection"]):
            selected, _ = scout._select_top3_candidates(
                [legacy], 3, lambda item: True, config
            )

        self.assertEqual([item["ticker"] for item in selected], ["LEGACY"])
        self.assertFalse(selected[0]["production_gate_passed"])

    def test_llm_cannot_promote_watchlist_candidate(self):
        rule = _candidate("RULE")
        watch = _candidate("WATCH", tier="B")
        raw = json.dumps({
            "schema_version": "scout_top3_llm_review_v0_1",
            "selected_top3": [{"rank": 1, "ticker": "WATCH", "reason": "replace", "risk": ""}],
            "rejected": [],
            "overrides": [{"dropped_ticker": "RULE", "added_ticker": "WATCH", "reason": "replace"}],
            "llm_override": True,
        })

        with patch.dict("os.environ", {"GPT_API_KEY": "test"}):
            final, audit = scout._apply_llm_top3_review(
                "2026-07-15",
                [rule, watch],
                [rule],
                [watch],
                _selection_config(),
                {},
                lambda *args, **kwargs: raw,
            )

        self.assertEqual([item["ticker"] for item in final], ["RULE"])
        self.assertEqual(audit["status"], "fallback_validation_failed")
        self.assertFalse(audit["llm_additions_allowed"])
        self.assertEqual(audit["final_top3"], ["RULE"])

    def test_llm_may_reduce_rule_candidates_without_adding(self):
        first = _candidate("FIRST")
        second = _candidate("SECOND")
        raw = json.dumps({
            "schema_version": "scout_top3_llm_review_v0_1",
            "selected_top3": [{"rank": 1, "ticker": "SECOND", "reason": "lower risk", "risk": ""}],
            "rejected": [{"ticker": "FIRST", "reason": "remaining risk"}],
            "overrides": [],
            "llm_override": True,
        })

        with patch.dict("os.environ", {"GPT_API_KEY": "test"}):
            final, audit = scout._apply_llm_top3_review(
                "2026-07-15",
                [first, second],
                [first, second],
                [],
                _selection_config(),
                {},
                lambda *args, **kwargs: raw,
            )

        self.assertEqual([item["ticker"] for item in final], ["SECOND"])
        self.assertEqual(audit["status"], "ok")
        self.assertEqual(audit["dropped_tickers"], ["FIRST"])
        self.assertEqual(audit["added_tickers"], [])


class DigestContractTests(unittest.TestCase):
    def test_zero_day_is_explicit_and_watchlist_is_not_a_recommendation(self):
        agent = DigestAgent.__new__(DigestAgent)
        agent.settings = {"digest": {"telegram": {"max_chars": 10000}}}
        agent.log = logging.getLogger("test.digest")
        message = agent._build_telegram(
            [],
            {},
            {},
            scout_out={
                "watchlist_candidates": [{
                    "ticker": "HWM",
                    "country": "US",
                    "selection_tier": "B",
                    "selection_lane": "pullback",
                    "selection_lane_status": "PASS",
                    "score": 2.2,
                    "signals": {},
                    "watch_reason": "Tier B",
                }],
                "radar_summary": {
                    "radar_pool_count": 52,
                    "no_candidate_reason": "Tier A 확실 후보 없음",
                    "filter_audit": {"top3_selection_audit": {
                        "llm_review": {
                            "enabled": True,
                            "status": "fallback_empty_pool",
                            "rule_based_top3": [],
                            "final_top3": [],
                            "llm_additions_allowed": False,
                        }
                    }},
                },
            },
        )

        self.assertIn("신규 추천</b> 오늘 없음", message)
        self.assertIn("관찰 레이더 (추천 아님)", message)
        self.assertIn("추천 기준 통과 후보 없음", message)
        self.assertNotIn("52개 중 엄선", message)

    def test_macro_degraded_coverage_is_visible(self):
        agent = DigestAgent.__new__(DigestAgent)
        agent.settings = {"digest": {"telegram": {"max_chars": 10000}}}
        agent.log = logging.getLogger("test.digest")
        message = agent._build_telegram(
            [],
            {},
            {
                "macro": {
                    "yesterday_announced": [{"name": "CPI"}],
                    "source_coverage": {
                        "status": "DEGRADED",
                        "fred_collected": 0,
                        "fred_requested": 6,
                        "market_collected": 5,
                        "market_requested": 5,
                    },
                },
                "interpretation": {},
            },
            scout_out={"radar_summary": {"no_candidate_reason": "추천 기준 미달"}},
        )

        self.assertIn("FRED 0/6", message)
        self.assertIn("해석 신뢰도 하향", message)

    def test_malformed_earnings_placeholder_is_not_displayed(self):
        candidate = {
            "catalyst_context": {
                "status": "found",
                "news": [
                    {"headline": "Earnings reported: actual None, estimate 1.24", "classification": "NOISE"},
                    {"headline": "Commercial aerospace demand improves", "classification": "POSITIVE_REVALUATION"},
                ],
            }
        }
        self.assertFalse(digest._has_real_catalyst("Earnings reported: actual None, estimate 1.24"))
        self.assertEqual(digest._candidate_catalyst_headline(candidate), "Commercial aerospace demand improves")

    def test_performance_summary_explains_failure_categories(self):
        text = scout_performance._performance_summary_text({
            "evaluated_count": 113,
            "candidate_count": 117,
            "actually_bought_count": 0,
            "verdict_counts": {"WINNER": 23, "FAILED_FAST": 56, "FALSE_POSITIVE": 0},
            "llm_override_comparison": {"dropped_count": 5, "added_count": 17},
        })
        self.assertIn("실패 56 (조기 56 / 20일 무진전 0)", text)
        self.assertNotIn("FALSE_POSITIVE 0", text)


class MacroCoverageTests(unittest.TestCase):
    def test_source_coverage_marks_fred_failure(self):
        with patch.object(macro_calendar, "get_events_in_range", return_value=[{"name": "CPI", "date": "2026-07-14"}]), \
             patch.object(macro_calendar, "fetch_macro_indicators", return_value={}), \
             patch.object(macro_calendar, "fetch_market_reaction", return_value={key: {} for key in macro_calendar.MARKET_REACTION_SYMBOLS}), \
             patch.object(macro_calendar, "_load_settings", return_value={"regime": {"macro_calendar": {"fred_series": ["A", "B"]}}}):
            events = macro_calendar.get_yesterday_announced_events()

        coverage = events[0]["source_coverage"]
        self.assertEqual(coverage["status"], "DEGRADED")
        self.assertEqual(coverage["fred_collected"], 0)
        self.assertEqual(coverage["fred_requested"], 2)


if __name__ == "__main__":
    unittest.main()
