from __future__ import annotations

import json
import logging
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.agents import digest, scout
from src.agents import regime
from src.agents.digest import DigestAgent
from src.collectors import macro_calendar
from src.modules import m2_rotation, scout_performance


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
        "quality_auditor": {"status": quality, "source": "fmp"},
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
            "excluded_factor_negatives": ["volatility_extreme", "chasing_extreme", "chasing_hot"],
            "backfill": False,
        },
        "llm_review": {"enabled": True, "additions_allowed": False, "candidate_limit": 5},
    }


def _research_review(ticker: str, disposition: str) -> dict:
    return {
        "ticker": ticker,
        "disposition": disposition,
        "memory_effect": "NONE",
        "memory_evidence_refs": [],
        "bull_case": {"summary": "bull", "evidence_refs": [f"{ticker}:E001"]},
        "bear_case": {"summary": "bear", "evidence_refs": [f"{ticker}:E002"]},
        "risk_case": {"summary": "risk", "evidence_refs": [f"{ticker}:E003"]},
        "invalidation": {"summary": "invalidate", "evidence_refs": [f"{ticker}:E004"]},
    }


class ProductionGateTests(unittest.TestCase):
    def test_llm_prompt_requires_korean_human_readable_summaries(self):
        _, user = scout._top3_llm_prompts(
            today="2026-07-29",
            market_context={},
            rule_candidates=[],
            research_packets=[],
            additions_allowed=False,
        )
        payload = json.loads(user)

        self.assertEqual(payload["schema_version"], "scout_top3_llm_prompt_v0_4")
        self.assertEqual(
            payload["required_output_schema"]["schema_version"],
            "scout_top3_llm_review_v0_4",
        )
        self.assertTrue(any("concise Korean" in rule for rule in payload["rules"]))

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
        risky["factor_context"]["negatives"] = ["volatility_extreme"]
        diagnostic_only = _candidate("LIQUIDITY_DIAGNOSTIC")
        diagnostic_only["factor_context"]["negatives"] = ["liquidity_weak"]
        radar = [good, tier_b, no_quality, risky]
        radar.append(diagnostic_only)

        with patch.object(scout, "_annotate_top3_selection", side_effect=lambda item: item["top3_selection"]):
            selected, audit = scout._select_top3_candidates(
                radar, 3, lambda item: True, _selection_config()
            )

        self.assertEqual(
            [item["ticker"] for item in selected],
            ["GOOD", "LIQUIDITY_DIAGNOSTIC"],
        )
        self.assertEqual(audit["production_gate"]["rejection_counts"]["tier_not_allowed"], 1)
        self.assertEqual(audit["production_gate"]["rejection_counts"]["quality_not_confirmed"], 1)
        self.assertEqual(audit["production_gate"]["rejection_counts"]["factor_risk"], 1)

    def test_not_checked_quality_is_reported_as_not_evaluated(self):
        item = _candidate("UNCHECKED", quality="not_checked")
        reason = scout._production_gate_rejection_reason(
            item,
            item["top3_selection"],
            _selection_config(),
        )
        self.assertEqual(reason, "quality_not_evaluated")

    def test_missing_quality_source_cannot_pass_on_price_context_alone(self):
        item = _candidate("SOURCELESS")
        item["quality_auditor"]["source"] = "empty"
        reason = scout._production_gate_rejection_reason(
            item,
            item["top3_selection"],
            _selection_config(),
        )
        self.assertEqual(reason, "quality_source_missing")

    def test_live_gate_can_restrict_delivery_to_left_side_stage2(self):
        config = _selection_config()
        config["production_gate"]["allowed_primary_lanes"] = ["left_side"]
        config["production_gate"]["allowed_lane_statuses"] = [
            "STAGE2_PASS",
            "STAGE2_STRONG_PASS",
        ]
        strength = _candidate("STRENGTH")
        left_side = _candidate("LEFT")
        left_side["top3_selection"]["primary_lane"] = "left_side"
        left_side["top3_selection"]["primary_lane_status"] = "STAGE2_STRONG_PASS"

        self.assertEqual(
            scout._production_gate_rejection_reason(
                strength,
                strength["top3_selection"],
                config,
            ),
            "lane_not_allowed",
        )
        self.assertEqual(
            scout._production_gate_rejection_reason(
                left_side,
                left_side["top3_selection"],
                config,
            ),
            "",
        )

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
            "schema_version": "scout_top3_llm_review_v0_4",
            "selected_top3": [{"rank": 1, "ticker": "WATCH"}],
            "rejected": [],
            "overrides": [{"dropped_ticker": "RULE", "added_ticker": "WATCH", "reason": "replace"}],
            "research_reviews": [_research_review("RULE", "KEEP")],
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
            "schema_version": "scout_top3_llm_review_v0_4",
            "selected_top3": [{"rank": 1, "ticker": "SECOND"}],
            "rejected": [{"ticker": "FIRST", "reason": "remaining risk"}],
            "overrides": [],
            "research_reviews": [
                _research_review("FIRST", "DROP"),
                _research_review("SECOND", "KEEP"),
            ],
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
        self.assertTrue(audit["selective_research"]["fact_lock"]["unchanged"])
        self.assertEqual(final[0]["selective_research"]["bear_case"]["summary"], "bear")
        self.assertEqual(first["llm_drop_reason"], "bear")

    def test_llm_may_abstain_when_every_evidence_review_says_drop(self):
        only = _candidate("ONLY")
        raw = json.dumps({
            "schema_version": "scout_top3_llm_review_v0_4",
            "selected_top3": [],
            "rejected": [{"ticker": "ONLY", "reason": "free-form text is ignored"}],
            "overrides": [],
            "research_reviews": [_research_review("ONLY", "DROP")],
            "llm_override": True,
        })

        with patch.dict("os.environ", {"GPT_API_KEY": "test"}):
            final, audit = scout._apply_llm_top3_review(
                "2026-07-15",
                [only],
                [only],
                [],
                _selection_config(),
                {},
                lambda *args, **kwargs: raw,
            )

        self.assertEqual(final, [])
        self.assertEqual(audit["status"], "ok")
        self.assertEqual(audit["final_top3"], [])
        self.assertEqual(only["llm_drop_reason"], "bear")


class DigestContractTests(unittest.TestCase):
    @staticmethod
    def _digest_agent():
        agent = DigestAgent.__new__(DigestAgent)
        agent.settings = {"digest": {"telegram": {"max_chars": 10000}}}
        agent.log = logging.getLogger("test.digest")
        return agent

    def test_run_uses_one_canonical_body_for_telegram_and_journal(self):
        agent = self._digest_agent()
        agent._enrich_candidates_llm = lambda items: items
        agent._translate_news_korean = lambda payload: payload
        agent._build_macro_interpretation_llm = lambda *args: ""
        out = agent.run({
            "scout_out": {"candidates": [], "pre_entry_candidates": [], "watchlist_candidates": []},
            "guard_out": {},
            "regime_out": {"vix": 18.0},
            "briefing_mode": "daily",
        })
        self.assertEqual(out["telegram_text"], out["sheets_text"])

    def test_zero_day_is_explicit_and_watchlist_is_visible(self):
        agent = self._digest_agent()
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
                    "decision_health": {
                        "status": "HEALTHY_ABSTENTION",
                        "label": "정상 관망",
                    },
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

        self.assertIn("판정 |", message)
        self.assertIn("환전 | 대기", message)
        self.assertIn("최종 후보 | 0개", message)
        self.assertIn("오늘 TV 확인 후보 | 0개", message)
        self.assertIn("없음 | Entry 전에 볼 후보 없음", message)
        self.assertIn("막힘 | Tier A 확실 후보 없음", message)
        self.assertIn("행동 | 오늘은 새 차트 열지 말고 보유 종목만 점검", message)
        self.assertIn("Tier A 확실 후보 없음", message)
        self.assertIn("관찰 후보 | 1개", message)
        self.assertIn("HWM | Tier B", message)

    def test_pre_entry_board_shows_price_evidence_with_execution_prompt(self):
        agent = self._digest_agent()
        candidate = {
            "ticker": "EARLY",
            "country": "US",
            "sector": "Technology",
            "price_lanes": {"left_side": {
                "status": "WAIT_CONFIRM",
                "reasons": ["low_zone", "down_days_decreasing"],
            }},
            "pre_entry_selection": {"rank": 1},
            "pre_entry_timing": {
                "status": "EARLY",
                "setup_date": "2026-08-01",
                "move_from_setup_pct": 0.03,
            },
            "price_map": {
                "current": 32.4,
                "position": "NEAR_SUPPORT",
                "support": {"lower": 31.0, "upper": 31.4},
                "first_resistance": {"lower": 34.0, "upper": 34.5},
                "core_resistance": {"lower": 39.5, "upper": 40.2},
                "invalidation_close_below": 30.8,
                "downside_to_invalidation_pct": -0.049,
                "upside_to_first_resistance_pct": 0.049,
                "reward_risk_to_first_resistance": 1.0,
            },
            "theme_industry": {
                "sector": {"name": "Technology", "quadrant": "IMPROVING"},
            },
        }
        message = agent._build_telegram(
            [],
            {},
            {},
            scout_out={"pre_entry_candidates": [candidate], "radar_summary": {}},
        )

        self.assertIn("오늘 TV 확인 후보 | 1개", message)
        self.assertIn("지지 $31.00~$31.40", message)
        self.assertIn("저항 $34.00~$34.50", message)
        self.assertIn("핵심 저항 | $39.50~$40.20", message)
        self.assertIn("선행 | 2026-08-01 최초 조짐 후 +3.0%", message)
        self.assertIn("무효 | $30.80 아래 종가", message)
        self.assertIn(
            "행동 | 지금 차트 열기 · Entry50/100 점등과 Gate 통과까지 대기",
            message,
        )

    def test_primary_pick_is_expanded_and_other_picks_are_compact(self):
        agent = self._digest_agent()
        candidates = [
            {
                "ticker": "AAA",
                "country": "US",
                "selection_rank": 1,
                "selection_lane": "left_side",
                "selection_lane_status": "STAGE2_STRONG_PASS",
                "score": 4.2,
                "market_cap": 10_000_000_000,
                "signals": {"bb_squeeze": True},
                "top3_selection": {
                    "tier": "A",
                    "tier_rank": 4,
                    "primary_lane": "left_side",
                    "primary_lane_status": "STAGE2_STRONG_PASS",
                    "lane_rank": 3,
                    "support_count": 4,
                    "production_gate_passed": True,
                    "selection_rank": 1,
                },
                "selective_research": {
                    "disposition": "KEEP",
                    "memory_effect": "SUPPORT",
                    "bull_case": {"summary": "가격 구조와 품질 근거가 함께 확인됨"},
                    "invalidation": {"summary": "지지 구간 이탈 시 무효"},
                },
            },
            {
                "ticker": "BBB",
                "country": "US",
                "selection_rank": 2,
                "selection_lane": "left_side",
                "selection_lane_status": "STAGE2_PASS",
                "score": 3.8,
                "signals": {"rrg_improving": True},
                "top3_selection": {
                    "tier": "A",
                    "tier_rank": 4,
                    "primary_lane": "left_side",
                    "primary_lane_status": "STAGE2_PASS",
                    "lane_rank": 2,
                    "support_count": 3,
                    "production_gate_passed": True,
                    "selection_rank": 2,
                },
            },
            {
                "ticker": "CCC",
                "country": "KR",
                "selection_rank": 3,
                "selection_lane": "left_side",
                "selection_lane_status": "STAGE2_PASS",
                "score": 3.5,
                "signals": {},
                "top3_selection": {
                    "tier": "A",
                    "tier_rank": 4,
                    "primary_lane": "left_side",
                    "primary_lane_status": "STAGE2_PASS",
                    "lane_rank": 2,
                    "support_count": 2,
                    "production_gate_passed": True,
                    "selection_rank": 3,
                },
            },
        ]

        message = agent._build_telegram(
            candidates,
            {"held_count": 4, "alerts": [{"ticker": "HELD"}]},
            {},
            scout_out={"radar_summary": {"radar_pool_count": 58}},
        )

        self.assertIn("최종 후보 | 2개", message)
        self.assertIn("1. AAA | STAGE2_STRONG_PASS", message)
        self.assertIn("2. BBB | STAGE2_PASS", message)
        self.assertNotIn("CCC", message)
        self.assertIn("행동 | TV Entry 신호와 현재 Gate를 다시 확인", message)
        self.assertIn("무효 | 지지 구간 이탈 시 무효", message)
        self.assertIn("보유 경보", message)
        self.assertIn("HELD", message)
        self.assertNotIn("후순위", message)

    def test_macro_degraded_coverage_is_visible(self):
        agent = self._digest_agent()
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

        self.assertIn("자료 | 금리·물가 원자료 누락", message)
        self.assertNotIn("FRED 0/6", message)

    def test_macro_jargon_is_translated_for_telegram(self):
        agent = self._digest_agent()
        message = agent._build_telegram(
            [],
            {},
            {
                "macro": {"yesterday_announced": [{"name": "FOMC"}]},
                "interpretation": {
                    "announcements_interpretation": (
                        "긴축 잔존으로 해석했습니다. DXY는 보합이고 "
                        "USDKRW는 1435.86원입니다."
                    )
                },
            },
            scout_out={"radar_summary": {"no_candidate_reason": "추천 기준 미달"}},
        )

        self.assertNotIn("높은 금리가 더 오래 갈 가능성", message)
        self.assertNotIn("달러지수(DXY)", message)
        self.assertNotIn("원/달러는 1435.86원", message)
        self.assertNotIn("긴축 잔존", message)

    def test_fx_output_shows_both_windows_and_52w_context(self):
        agent = self._digest_agent()
        message = agent._build_telegram(
            [],
            {},
            {
                "fx": {
                    "current": 1431.18,
                    "action": "적극",
                    "percentile_90d": 0.0,
                    "percentile_52w": 18.0,
                    "median_52w": 1478.2,
                    "median_diff_pct_52w": -3.18,
                    "min_52w": 1395.4,
                    "max_52w": 1518.6,
                }
            },
            scout_out={"radar_summary": {"no_candidate_reason": "추천 기준 미달"}},
        )

        self.assertIn("환전 | 적극", message)
        self.assertIn("90일 하위 0% · 52주 하위 18%", message)
        self.assertIn("행동 | 이번 달 필요한 달러는 지금부터 확보", message)
        self.assertNotIn("52주 범위", message)
        self.assertNotIn("중앙값", message)
        self.assertNotIn("52주 비교는 아직 미수집", message)

    def test_holding_alert_separates_structure_news_and_unverified_thesis(self):
        agent = self._digest_agent()
        message = agent._build_telegram(
            [],
            {
                "alerts": [{
                    "ticker": "NOW",
                    "price": {"daily_pct": 4.7},
                    "technical_structure": {
                        "status": "BREAKOUT_HOLD",
                        "label": "소고점 돌파 구조 유지",
                        "breakout_level": 104.2,
                        "support": 103.8,
                        "resistance": 118.0,
                        "up_streak": 4,
                        "extension_atr": 1.7,
                        "pause_watch": True,
                    },
                    "news": [{"ko_summary": "NOW 관련 뉴스 영향은 중립"}],
                    "thesis_impact": {
                        "status": "UNVERIFIED",
                        "label": "투자 근거 영향 판정 불가",
                    },
                }],
            },
            {},
            scout_out={"radar_summary": {"no_candidate_reason": "추천 기준 미달"}},
        )

        self.assertIn("구조 | 소고점 돌파 구조 유지", message)
        self.assertIn("연속 상승 4일", message)
        self.assertIn("행동 | 보유 관찰 · 표시 지지선 종가 이탈 때 다시 판단", message)
        self.assertIn("뉴스 | NOW 관련 뉴스 영향은 중립", message)
        self.assertNotIn("투자 근거 영향", message)
        self.assertNotIn("기존 투자 근거를 바꿀 새 정보 없음", message)

    def test_theme_label_without_two_supportive_etfs_cannot_drive_opportunity(self):
        agent = self._digest_agent()
        message = agent._build_telegram(
            [],
            {},
            {
                "vix": 18.0,
                "rrg": {
                    "by_quadrant": {
                        "LEADING": [{"label": "헬스케어"}, {"label": "금융"}],
                        "IMPROVING": [{"label": "소비재"}],
                        "LAGGING": [{"label": "기술"}],
                    },
                    "theme_intelligence": {
                        "counts": {"강함": 1},
                        "focus": [{
                            "label": "AI·반도체",
                            "judgment": "강함",
                            "etfs": [
                                {"ticker": "SMH", "quadrant": "LAGGING"},
                                {"ticker": "SOXX", "quadrant": "LAGGING"},
                            ],
                        }],
                    },
                },
            },
            scout_out={"radar_summary": {"no_candidate_reason": "추천 기준 미달"}},
        )

        self.assertIn("판정 | 선별 관찰", message)
        self.assertIn("행동 | 시장 전체를 따라가지 말고 표시된 후보만 확인", message)
        self.assertNotIn("테마 | AI·반도체", message)

    def test_one_screen_market_map_caps_each_row_at_two_items(self):
        agent = self._digest_agent()
        message = agent._build_telegram(
            [],
            {},
            {
                "vix": 18.0,
                "fx": {
                    "current": 1436.6,
                    "action": "분할",
                    "percentile_90d": 2,
                    "percentile_52w": 34,
                },
                "rrg": {
                    "by_quadrant": {
                        "LEADING": [{"label": "임의소비재"}],
                        "IMPROVING": [{"label": "기술"}, {"label": "산업재"}],
                        "LAGGING": [{"label": "필수소비재"}, {"label": "통신"}, {"label": "리츠"}],
                    },
                    "transitions": [
                        {"label": "기술", "prev": "LAGGING", "curr": "IMPROVING"},
                        {"label": "임의소비재", "prev": "IMPROVING", "curr": "LEADING"},
                        {"label": "리츠", "prev": "WEAKENING", "curr": "LAGGING"},
                    ],
                    "theme_intelligence": {"groups": [
                        {"label": "클라우드", "judgment": "강함"},
                        {"label": "사이버보안", "judgment": "강함"},
                        {"label": "로봇", "judgment": "강함"},
                    ]},
                },
            },
            scout_out={"radar_summary": {"no_candidate_reason": "추천 기준 미달"}},
        )
        self.assertIn("기회 | 임의소비재 주도 · 기술 개선", message)
        self.assertIn("테마 | 클라우드 · 사이버보안", message)
        self.assertNotIn("로봇", message)
        self.assertIn("위험 | 필수소비재 부진 · 통신 부진", message)
        self.assertNotIn("리츠", message)
        self.assertIn("변화 | 기술 부진>개선 · 임의소비재 개선>주도", message)
        self.assertLess(len(message), 700)

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


class FxWindowTests(unittest.TestCase):
    @staticmethod
    def _agent():
        return regime.RegimeAgent.__new__(regime.RegimeAgent)

    def test_aggressive_requires_low_90d_and_low_52w(self):
        short = list(range(1400, 1461)) + [1390.0]
        year = list(range(1350, 1601)) + [1390.0]
        cfg = {
            "history_range_90d": "3mo",
            "history_range_52w": "1y",
            "percentile_high_pct": 70,
            "percentile_low_pct": 30,
        }

        with patch.object(regime, "_fetch_fx_history", side_effect=[short, year]):
            result = self._agent()._compute_fx(cfg)

        self.assertEqual(result["action"], "적극")
        self.assertLessEqual(result["percentile_90d"], 30)
        self.assertLessEqual(result["percentile_52w"], 30)

    def test_mixed_windows_are_split_not_aggressive(self):
        short = list(range(1400, 1461)) + [1390.0]
        year = list(range(1200, 1451)) + [1390.0]
        cfg = {
            "history_range_90d": "3mo",
            "history_range_52w": "1y",
            "percentile_high_pct": 70,
            "percentile_low_pct": 30,
        }

        with patch.object(regime, "_fetch_fx_history", side_effect=[short, year]):
            result = self._agent()._compute_fx(cfg)

        self.assertEqual(result["action"], "분할")
        self.assertLessEqual(result["percentile_90d"], 30)
        self.assertGreater(result["percentile_52w"], 30)


class IntegrityResetTests(unittest.TestCase):
    @staticmethod
    def _ohlcv() -> pd.DataFrame:
        size = 260
        close = np.linspace(80.0, 100.0, size)
        return pd.DataFrame({
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.full(size, 12_500_000.0),
        })

    def test_liquidity_uses_common_gate_ohlcv_instead_of_zero_universe_field(self):
        row = pd.Series({
            "ticker": "ACN",
            "country": "US",
            "avg_volume_value": 0,
        })
        common_gate = {"metrics": {"avg_traded_value_20d": 1_246_000_000}}
        common_gate_cfg = {"min_avg_traded_value_20d": {"US": 10_000_000}}

        quality = scout._assess_quality_context(
            self._ohlcv(),
            row,
            5_000_000,
            common_gate=common_gate,
            common_gate_cfg=common_gate_cfg,
        )
        factor = scout._assess_factor_profile(
            self._ohlcv(),
            row,
            {"enabled": True, "weights": {}},
            5_000_000,
            common_gate=common_gate,
            common_gate_cfg=common_gate_cfg,
        )

        self.assertNotIn("low_liquidity_buffer", quality["flags"])
        self.assertNotIn("liquidity_weak", factor["negatives"])
        self.assertIn("liquidity_good", factor["positives"])
        self.assertEqual(quality["metrics"]["liquidity_source"], "common_gate_ohlcv")
        self.assertEqual(quality["metrics"]["liquidity_buffer_multiple"], 124.6)

    def test_quality_auditor_covers_all_production_eligible_items_beyond_cost_limit(self):
        radar = []
        for index in range(35):
            radar.append({
                "ticker": f"T{index:02d}",
                "country": "US",
                "market_cap": 1_000_000_000,
                "price_lanes": {"strength": {"status": "STRONG_PASS"}},
            })
        cfg = {"enabled": True, "eval_limit": 30}
        production = {"enabled": True, "allowed_tiers": ["A"]}

        with patch.object(scout, "_fetch_quality_fundamental", return_value=("fmp", {})), \
             patch.object(scout, "_assess_quality_auditor", return_value={"status": "NEUTRAL"}), \
             patch.object(scout.time, "sleep", return_value=None):
            audit = scout._apply_quality_auditor(radar, cfg, production)

        self.assertEqual(audit["evaluated"], 35)
        self.assertEqual(audit["production_required"], 35)
        self.assertEqual(audit["production_required_missing"], 0)
        self.assertTrue(audit["production_coverage_complete"])
        self.assertTrue(all("quality_auditor" in item for item in radar))

    def test_disabled_quality_auditor_is_not_reported_as_complete(self):
        radar = [{
            "ticker": "A_ONLY",
            "country": "US",
            "price_lanes": {"strength": {"status": "STRONG_PASS"}},
        }]
        audit = scout._apply_quality_auditor(
            radar,
            {"enabled": False, "eval_limit": 30},
            {"enabled": True, "allowed_tiers": ["A"]},
        )

        self.assertEqual(audit["production_required"], 1)
        self.assertEqual(audit["production_required_missing"], 1)
        self.assertFalse(audit["production_coverage_complete"])
        self.assertFalse(audit["production_data_complete"])

    def test_theme_groups_do_not_mix_semiconductor_weakness_with_cloud_strength(self):
        quadrants = {
            "SMH": "lagging",
            "SOXX": "lagging",
            "AIQ": "lagging",
            "ARTY": "lagging",
            "SKYY": "leading",
            "IGV": "improving",
        }
        snapshot = {}
        for ticker, quadrant in quadrants.items():
            snapshot[ticker] = {
                **m2_rotation._DEFAULT_THEME_MAP[ticker],
                "quadrant": quadrant,
                "ratio": 100,
                "momentum": 100,
            }

        grouped = regime._group_theme_snapshot(snapshot)
        judgments = {group["label"]: group["judgment"] for group in grouped["groups"]}

        self.assertEqual(judgments["AI·반도체"], "보류")
        self.assertEqual(judgments["클라우드·소프트웨어"], "강함")
        self.assertNotIn("AI·반도체·클라우드", judgments)
        self.assertEqual(
            digest._format_theme_etfs(grouped["groups"][0]["etfs"], 6).count(",") + 1,
            len(grouped["groups"][0]["etfs"]),
        )

    def test_decision_health_distinguishes_abstention_from_missing_quality_data(self):
        radar = [{"ticker": "WAIT"}]
        healthy = scout._decision_health_summary(
            radar,
            [],
            {
                "quality_audit": {
                    "production_required_missing": 0,
                    "production_required_source_missing": 0,
                },
                "top3_selection_audit": {
                    "production_gate": {"rejection_counts": {"tier_not_allowed": 1}}
                },
            },
        )
        degraded = scout._decision_health_summary(
            radar,
            [],
            {
                "quality_audit": {
                    "production_required_missing": 0,
                    "production_required_source_missing": 2,
                },
                "top3_selection_audit": {"production_gate": {"rejection_counts": {}}},
            },
        )

        self.assertEqual(healthy["status"], "HEALTHY_ABSTENTION")
        self.assertEqual(degraded["status"], "DEGRADED_DATA")
        self.assertIn("품질 원천데이터 없음 2개", degraded["reason"])


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
