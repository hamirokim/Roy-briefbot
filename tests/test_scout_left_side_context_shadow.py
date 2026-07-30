from __future__ import annotations

import unittest

from src.agents import scout


def _item(
    ticker: str,
    *,
    country: str = "US",
    lane: str = "left_side",
    lane_status: str = "STAGE2_PASS",
    sector_quadrant: str = "IMPROVING",
    theme_status: str | None = "GROUP_SUPPORT",
    production_passed: bool = True,
    opportunity: float = 1.0,
) -> dict:
    themes = []
    if theme_status is not None:
        themes.append(
            {
                "theme_key": "example_theme",
                "theme_group": "example_group",
                "parent_theme_etf": "EXM",
                "status": theme_status,
            }
        )
    return {
        "ticker": ticker,
        "country": country,
        "score": opportunity,
        "signal_count": 2,
        "market_cap": 1_000_000_000,
        "production_gate_passed": production_passed,
        "top3_selection": {
            "tier": "A",
            "tier_rank": 4,
            "primary_lane": lane,
            "primary_lane_status": lane_status,
            "lane_rank": 5 if lane_status == "STAGE2_STRONG_PASS" else 4,
            "catalyst_freshness_rank": 0,
            "support_count": 2,
            "opportunity_score": opportunity,
            "excluded": False,
            "production_gate_passed": production_passed,
        },
        "theme_industry": {
            "status": "STRONG_SUPPORT",
            "sector": {"quadrant": sector_quadrant},
            "themes": themes,
        },
    }


def _config() -> dict:
    return {
        "left_side_context_shadow": {
            "enabled": True,
            "policy_id": "left_side_context_v1",
            "max_picks": 2,
            "allowed_countries": ["US", "KR"],
            "required_primary_lane": "left_side",
            "allowed_lane_statuses": ["STAGE2_PASS", "STAGE2_STRONG_PASS"],
            "allowed_sector_quadrants": ["LEADING", "IMPROVING"],
            "mapped_theme_statuses": ["GROUP_SUPPORT"],
            "allow_unmapped_theme": True,
            "require_production_gate": True,
            "backfill": False,
        }
    }


class LeftSideContextShadowTests(unittest.TestCase):
    def test_selects_at_most_two_and_freezes_candidates(self):
        radar = [
            _item("LOW", opportunity=1.0),
            _item("TOP", lane_status="STAGE2_STRONG_PASS", opportunity=4.0),
            _item("MID", opportunity=3.0),
        ]
        selected, audit = scout._select_left_side_context_shadow_candidates(radar, _config())

        self.assertEqual([item["ticker"] for item in selected], ["TOP", "MID"])
        self.assertEqual([item["shadow_selection"]["rank"] for item in selected], [1, 2])
        self.assertFalse(audit["criteria"]["backfill"])
        self.assertFalse(audit["no_signal"])
        radar[1]["top3_selection"]["primary_lane"] = "strength"
        self.assertEqual(selected[0]["top3_selection"]["primary_lane"], "left_side")

    def test_rejects_non_executable_or_unsupported_context(self):
        radar = [
            _item("GOOD"),
            _item("NO_GATE", production_passed=False),
            _item("STRENGTH", lane="strength"),
            _item("WAIT", lane_status="WAIT_CONFIRM"),
            _item("LAGGING", sector_quadrant="LAGGING"),
            _item("ONE_ETF", theme_status="PARENT_SUPPORT"),
        ]
        selected, audit = scout._select_left_side_context_shadow_candidates(radar, _config())

        self.assertEqual([item["ticker"] for item in selected], ["GOOD"])
        self.assertEqual(audit["rejection_counts"]["production_gate"], 1)
        self.assertEqual(audit["rejection_counts"]["primary_lane"], 1)
        self.assertEqual(audit["rejection_counts"]["lane_status"], 1)
        self.assertEqual(audit["rejection_counts"]["sector"], 1)
        self.assertEqual(audit["rejection_counts"]["mapped_theme"], 1)

    def test_allows_unmapped_company_when_sector_supports_it(self):
        selected, audit = scout._select_left_side_context_shadow_candidates(
            [_item("PLAIN", theme_status=None)],
            _config(),
        )

        self.assertEqual([item["ticker"] for item in selected], ["PLAIN"])
        self.assertEqual(audit["eligible_before_cap"], 1)

    def test_zero_candidates_is_a_valid_result(self):
        selected, audit = scout._select_left_side_context_shadow_candidates(
            [_item("BAD", sector_quadrant="WEAKENING")],
            _config(),
        )

        self.assertEqual(selected, [])
        self.assertTrue(audit["no_signal"])
        self.assertEqual(audit["selected"], 0)


if __name__ == "__main__":
    unittest.main()
