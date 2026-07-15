from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents import scout
from src.modules import scout_performance


def _item(
    ticker: str,
    *,
    country: str = "US",
    tier: str = "A",
    opportunity: float = 1.0,
    theme: str = "SUPPORT",
    quality: str = "QUALITY_SUPPORT",
    negatives: list[str] | None = None,
    risk: bool = False,
) -> dict:
    return {
        "ticker": ticker,
        "country": country,
        "score": opportunity,
        "signal_count": 1,
        "market_cap": 1_000_000_000,
        "top3_selection": {
            "tier": tier,
            "tier_rank": 4 if tier == "A" else 3,
            "primary_lane": "strength",
            "primary_lane_status": "STRONG_PASS",
            "lane_rank": 5 if tier == "A" else 4,
            "catalyst_freshness_rank": 0,
            "support_count": 2,
            "opportunity_score": opportunity,
            "excluded": risk,
            "exclude_reason": "RISK_CATALYST" if risk else "",
        },
        "theme_industry": {
            "status": theme,
            "theme_snapshot_date": "2026-07-14",
            "sector": {"snapshot_date": "2026-07-14"},
        },
        "quality_auditor": {"status": quality},
        "factor_context": {"negatives": negatives or []},
        "catalyst_context": {"top3_excluded_reason": "RISK_CATALYST" if risk else ""},
        "common_gate": {"metrics": {"latest_date": "2026-07-14"}},
    }


def _config() -> dict:
    return {
        "precision_shadow": {
            "enabled": True,
            "policy_id": "us_precision_v1",
            "max_picks": 3,
            "allowed_countries": ["US"],
            "allowed_tiers": ["A"],
            "theme_statuses": ["SUPPORT", "STRONG_SUPPORT"],
            "quality_statuses": ["QUALITY_SUPPORT", "STRONG_QUALITY"],
            "excluded_factor_negatives": ["volatility_extreme", "chasing_extreme", "chasing_hot"],
        }
    }


class PrecisionShadowSelectionTests(unittest.TestCase):
    def test_zero_candidates_is_valid_and_never_backfilled(self):
        radar = [
            _item("005930.KS", country="KR"),
            _item("TIERB", tier="B"),
            _item("HOT", negatives=["chasing_hot"]),
            _item("RISK", risk=True),
        ]
        selected, audit = scout._select_precision_shadow_candidates(radar, _config())
        self.assertEqual(selected, [])
        self.assertTrue(audit["no_signal"])
        self.assertEqual(audit["selected"], 0)
        self.assertFalse(audit["criteria"]["backfill"])

    def test_selects_at_most_three_and_freezes_before_llm(self):
        radar = [
            _item("LOW", opportunity=1.0),
            _item("TOP", opportunity=4.0),
            _item("MID", opportunity=3.0),
            _item("THIRD", opportunity=2.0),
        ]
        selected, audit = scout._select_precision_shadow_candidates(radar, _config())
        self.assertEqual([item["ticker"] for item in selected], ["TOP", "MID", "THIRD"])
        self.assertEqual([item["shadow_selection"]["rank"] for item in selected], [1, 2, 3])
        self.assertFalse(audit["llm_additions_allowed"])
        radar[1]["top3_selection"]["llm_dropped"] = True
        radar[1]["top3_selection"]["llm_drop_reason"] = "later mutation"
        self.assertNotIn("llm_dropped", selected[0]["top3_selection"])
        self.assertNotIn("shadow_selection", radar[1])

    def test_rejects_missing_confirmations_and_extremes(self):
        radar = [
            _item("GOOD"),
            _item("NO_THEME", theme="NO_MAPPING"),
            _item("NO_QUALITY", quality="not_checked"),
            _item("EXTREME", negatives=["volatility_extreme"]),
        ]
        selected, audit = scout._select_precision_shadow_candidates(radar, _config())
        self.assertEqual([item["ticker"] for item in selected], ["GOOD"])
        self.assertEqual(audit["rejection_counts"]["theme"], 1)
        self.assertEqual(audit["rejection_counts"]["quality"], 1)
        self.assertEqual(audit["rejection_counts"]["factor_extreme"], 1)


class PrecisionShadowPersistenceTests(unittest.TestCase):
    def test_snapshot_v03_preserves_metadata_and_shadow_candidates(self):
        final_candidate = _item("LIVE")
        shadow_candidate = _item("SHADOW")
        shadow_candidate["shadow_selection"] = {
            "policy_id": "us_precision_v1",
            "rank": 1,
            "shadow_only": True,
            "llm_additions_allowed": False,
        }
        shadow_policies = {
            "us_precision_v1": {
                "policy_id": "us_precision_v1",
                "shadow_only": True,
                "llm_additions_allowed": False,
                "audit": {"selected": 1},
                "candidates": [shadow_candidate],
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(scout, "RADAR_DIR", Path(tmpdir)):
            paths = scout._save_recommendation_snapshot(
                today="2026-07-15",
                candidates=[final_candidate],
                radar_pool=[final_candidate, shadow_candidate],
                radar_summary={"filter_audit": {}},
                snapshot_cfg={"enabled": True, "include_radar_top": 2, "parquet_enabled": False},
                shadow_policies=shadow_policies,
                generated_at="2026-07-15T07:10:00+09:00",
            )
            payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], "scout_recommendation_snapshot_v0_3")
        self.assertEqual(payload["generated_at"], "2026-07-15T07:10:00+09:00")
        self.assertEqual(payload["timezone"], "Asia/Seoul")
        self.assertEqual(payload["data_as_of"]["ohlcv_latest_by_country"]["US"], "2026-07-14")
        self.assertEqual(payload["summary"]["candidate_count"], 1)
        self.assertEqual(payload["summary"]["shadow_policy_counts"]["us_precision_v1"], 1)
        self.assertEqual(payload["shadow_policies"]["us_precision_v1"]["candidates"][0]["ticker"], "SHADOW")

    def test_performance_groups_shadow_without_changing_candidate_bucket(self):
        snapshot = {
            "candidates": [_item("LIVE")],
            "radar_top": [],
            "shadow_policies": {
                "us_precision_v1": {
                    "policy_id": "us_precision_v1",
                    "candidates": [_item("SHADOW")],
                }
            },
        }
        groups = dict(scout_performance._snapshot_record_groups(snapshot, include_radar_top=False))
        self.assertEqual([item["ticker"] for item in groups["candidate"]], ["LIVE"])
        self.assertEqual([item["ticker"] for item in groups["shadow:us_precision_v1"]], ["SHADOW"])

        records = [
            {"bucket": "candidate", "ticker": "LIVE", "status": "OK", "followup": {"d5": {"return_pct": -1.0}}},
            {"bucket": "shadow:us_precision_v1", "ticker": "SHADOW", "status": "OK", "followup": {"d5": {"return_pct": 2.0}}},
        ]
        summary = scout_performance._summary(records)
        self.assertEqual(summary["candidate_count"], 1)
        self.assertEqual(summary["shadow_policy_comparison"]["us_precision_v1"]["count"], 1)
        self.assertEqual(summary["shadow_policy_comparison"]["us_precision_v1"]["avg_d5_return_pct"], 2.0)


if __name__ == "__main__":
    unittest.main()
