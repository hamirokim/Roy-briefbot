from __future__ import annotations

import unittest

from src.modules.scout_research import (
    MAX_FINALISTS,
    build_research_packets,
    fact_fingerprint,
    validate_research_reviews,
)


def _candidate(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "country": "US",
        "market_cap": 2_000_000_000,
        "score": 4.2,
        "signal_count": 2,
        "signal_keys": ["bb_squeeze", "volume_compression"],
        "signals": {"bb_squeeze": {"ratio": 0.4}},
        "common_gate": {
            "status": "PASS",
            "metrics": {
                "latest_date": "2026-07-28",
                "latest_close": 50.0,
                "avg_traded_value_20d": 20_000_000,
                "stale_trading_days": 1,
            },
        },
        "price_lanes": {
            "strength": {
                "status": "STRONG_PASS",
                "reasons": ["relative_strength"],
                "metrics": {"rs_20d": 0.08},
            },
        },
        "factor_context": {
            "positives": ["not_chasing"],
            "negatives": [],
            "metrics": {"ret_20d": 0.05},
        },
        "quality_flags": [],
        "quality_auditor": {
            "source": "fmp",
            "status": "QUALITY_SUPPORT",
            "score": 3,
            "categories": {},
        },
        "theme_industry": {
            "status": "SUPPORT",
            "sector": {
                "etf": "XLK",
                "quadrant": "IMPROVING",
                "snapshot_date": "2026-07-29",
            },
        },
        "catalyst_context": {
            "news": [{
                "headline": "Company raises guidance",
                "source": "FMP:Business Wire",
                "datetime": 1785210319,
                "url": "https://example.test/news",
                "classification": "POSITIVE_REVALUATION",
            }],
        },
        "data_coverage": {
            "fundamental": {"status": "partial", "missing_fields": ["Forward PE"]},
            "catalyst": {"status": "found"},
        },
        "top3_selection": {
            "tier": "A",
            "primary_lane": "strength",
            "primary_lane_status": "STRONG_PASS",
            "lane_rank": 5,
            "support_count": 3,
            "support_reasons": ["quality:QUALITY_SUPPORT"],
            "opportunity_score": 5.0,
            "excluded": False,
            "production_gate_passed": True,
        },
    }


def _review(ticker: str, evidence_ids: list[str]) -> dict:
    return {
        "ticker": ticker,
        "disposition": "KEEP",
        "bull_case": {"summary": "supported bull case", "evidence_refs": [evidence_ids[0]]},
        "bear_case": {"summary": "supported bear case", "evidence_refs": [evidence_ids[1]]},
        "risk_case": {"summary": "supported risk", "evidence_refs": [evidence_ids[2]]},
        "invalidation": {"summary": "observable invalidation", "evidence_refs": [evidence_ids[3]]},
    }


class SelectiveResearchTests(unittest.TestCase):
    def test_packet_preserves_source_time_and_missing_data(self):
        packet = build_research_packets([_candidate("TEST")], "2026-07-29")[0]
        entries = packet["evidence"]

        self.assertEqual(packet["ticker"], "TEST")
        self.assertTrue(packet["fact_fingerprint"])
        self.assertTrue(all(row["source"] and row["as_of"] for row in entries))
        self.assertTrue(any(row["source"] == "fmp" for row in entries))
        self.assertTrue(any(row["url"] == "https://example.test/news" for row in entries))
        self.assertTrue(any("Forward PE" in row["value"].get("missing_fields", []) for row in entries))

    def test_only_five_finalists_are_packetized(self):
        candidates = [_candidate(f"T{index}") for index in range(8)]
        packets = build_research_packets(candidates, "2026-07-29", limit=20)

        self.assertEqual(len(packets), MAX_FINALISTS)
        self.assertEqual([packet["ticker"] for packet in packets], ["T0", "T1", "T2", "T3", "T4"])

    def test_review_requires_valid_same_ticker_evidence(self):
        packets = build_research_packets([_candidate("TEST")], "2026-07-29")
        evidence_ids = [row["evidence_id"] for row in packets[0]["evidence"]]
        reviews, error = validate_research_reviews([_review("TEST", evidence_ids)], packets)

        self.assertFalse(error)
        self.assertEqual(reviews["TEST"]["disposition"], "KEEP")

        bad = _review("TEST", evidence_ids)
        bad["risk_case"]["evidence_refs"] = ["OTHER:E001"]
        _, error = validate_research_reviews([bad], packets)
        self.assertEqual(error, "risk_case_invalid_evidence_ref:TEST")

    def test_fact_fingerprint_ignores_review_prose_but_detects_number_change(self):
        candidate = _candidate("TEST")
        before = fact_fingerprint([candidate])
        candidate["top3_selection"]["selective_research"] = {"bull_case": "new prose"}
        candidate["llm_reason"] = "new prose"
        self.assertEqual(fact_fingerprint([candidate]), before)

        candidate["score"] = 9.9
        self.assertNotEqual(fact_fingerprint([candidate]), before)


if __name__ == "__main__":
    unittest.main()
