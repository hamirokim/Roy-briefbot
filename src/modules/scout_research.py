"""Selective SCOUT research contracts.

Deterministic code owns facts. The LLM may only attach evidence-backed review
prose to the already selected production finalists.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from src.modules.scout_outcome_memory import match_outcome_lessons


SCHEMA_VERSION = "scout_selective_research_v0_1"
MAX_FINALISTS = 5


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return round(value, 8)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, set):
        return sorted((_json_value(item) for item in value), key=lambda item: str(item))
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_value(value.item())
        except Exception:
            pass
    return str(value)


def _ticker(item: dict) -> str:
    return str(item.get("ticker", "") or "").strip().upper()


def _locked_facts(item: dict) -> dict:
    """Return only deterministic fields that an LLM is never allowed to edit."""
    selection = item.get("top3_selection") or {}
    catalyst = item.get("catalyst_context") or {}
    theme = item.get("theme_industry") or {}
    quality = item.get("quality_auditor") or {}
    return _json_value({
        "ticker": _ticker(item),
        "country": item.get("country", ""),
        "market_cap": item.get("market_cap"),
        "score": item.get("score"),
        "signal_count": item.get("signal_count"),
        "signal_keys": item.get("signal_keys") or [],
        "decision_context": item.get("decision_context") or {},
        "common_gate": item.get("common_gate") or {},
        "price_lanes": item.get("price_lanes") or {},
        "factor_context": item.get("factor_context") or {},
        "quality_flags": item.get("quality_flags") or [],
        "quality_auditor": quality,
        "theme_industry": theme,
        "catalyst_context": catalyst,
        "selection": {
            "tier": selection.get("tier"),
            "primary_lane": selection.get("primary_lane"),
            "primary_lane_status": selection.get("primary_lane_status"),
            "lane_rank": selection.get("lane_rank"),
            "support_count": selection.get("support_count"),
            "support_reasons": selection.get("support_reasons") or [],
            "opportunity_score": selection.get("opportunity_score"),
            "excluded": selection.get("excluded"),
            "exclude_reason": selection.get("exclude_reason"),
            "production_gate_passed": selection.get("production_gate_passed"),
            "production_gate_rejection_reason": selection.get("production_gate_rejection_reason"),
        },
    })


def fact_fingerprint(candidates: list[dict]) -> str:
    facts = [_locked_facts(item) for item in candidates]
    encoded = json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _news_as_of(value: Any) -> str:
    try:
        timestamp = int(value or 0)
        if timestamp > 0:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        pass
    return ""


def build_evidence_packet(
    item: dict,
    decision_date: str,
    outcome_memory: Optional[dict] = None,
    max_outcome_lessons: int = 6,
) -> dict:
    ticker = _ticker(item)
    common = item.get("common_gate") or {}
    common_metrics = common.get("metrics") or {}
    selection = item.get("top3_selection") or {}
    primary_lane = str(selection.get("primary_lane", "") or "")
    lane = (item.get("price_lanes") or {}).get(primary_lane) or {}
    factor = item.get("factor_context") or {}
    quality = item.get("quality_auditor") or {}
    theme = item.get("theme_industry") or {}
    sector = theme.get("sector") or {}
    catalyst = item.get("catalyst_context") or {}
    latest_date = str(common_metrics.get("latest_date", "") or decision_date)
    entries: list[dict] = []

    def add(category: str, claim: str, value: Any, source: str, as_of: str = "", url: str = ""):
        evidence_id = f"{ticker}:E{len(entries) + 1:03d}"
        entries.append(_json_value({
            "evidence_id": evidence_id,
            "category": category,
            "claim": claim,
            "value": value,
            "as_of": as_of or decision_date,
            "source": source,
            "url": url,
        }))

    add(
        "price",
        "Latest executable market observations used by the common gate",
        {
            "latest_close": common_metrics.get("latest_close"),
            "avg_traded_value_20d": common_metrics.get("avg_traded_value_20d"),
            "stale_trading_days": common_metrics.get("stale_trading_days"),
        },
        "yfinance_ohlcv",
        latest_date,
    )
    market_regime = ((item.get("decision_context") or {}).get("market_regime") or {})
    add(
        "market_regime",
        "Benchmark regime calculated from observations available at decision time",
        market_regime,
        "derived:benchmark.market_regime",
        str(market_regime.get("as_of", "") or latest_date),
    )
    add(
        "technical",
        "Primary price-lane decision and deterministic metrics",
        {
            "lane": primary_lane,
            "status": selection.get("primary_lane_status"),
            "reasons": lane.get("reasons") or [],
            "review_flags": lane.get("review_flags") or [],
            "metrics": lane.get("metrics") or {},
        },
        "derived:scout.price_lanes",
        latest_date,
    )
    add(
        "signals",
        "Predefined SCOUT signals present at decision time",
        {
            "signal_count": item.get("signal_count"),
            "signal_keys": item.get("signal_keys") or [],
            "signals": item.get("signals") or {},
        },
        "derived:scout.signal_rules",
        latest_date,
    )
    add(
        "risk",
        "Deterministic factor positives, negatives, and quality flags",
        {
            "positives": factor.get("positives") or [],
            "negatives": factor.get("negatives") or [],
            "metrics": factor.get("metrics") or {},
            "quality_flags": item.get("quality_flags") or [],
        },
        "derived:scout.factor_layer",
        latest_date,
    )
    add(
        "quality",
        "Fundamental quality audit",
        {
            "status": quality.get("status"),
            "score": quality.get("score"),
            "categories": quality.get("categories") or {},
            "missing_count": quality.get("data_missing_count"),
        },
        str(quality.get("source", "") or "quality_source_missing"),
        decision_date,
    )
    add(
        "theme",
        "Sector and theme rotation context",
        {
            "status": theme.get("status"),
            "warnings": theme.get("warnings") or [],
            "sector": sector,
            "themes": theme.get("themes") or [],
        },
        "derived:regime.rrg",
        str(sector.get("snapshot_date", "") or theme.get("theme_snapshot_date", "") or decision_date),
    )
    add(
        "selection",
        "Rule-based production eligibility and rank inputs",
        {
            "tier": selection.get("tier"),
            "support_count": selection.get("support_count"),
            "support_reasons": selection.get("support_reasons") or [],
            "opportunity_score": selection.get("opportunity_score"),
            "production_gate_passed": selection.get("production_gate_passed"),
        },
        "derived:scout.production_gate",
        decision_date,
    )

    news_rows = catalyst.get("news") or []
    for news in news_rows[:3]:
        if not isinstance(news, dict):
            continue
        add(
            "catalyst",
            "News or event evidence available at decision time",
            {
                "headline": news.get("headline", ""),
                "event_type": news.get("event_type", ""),
                "classification": news.get("classification", ""),
                "classification_reason": news.get("classification_reason", ""),
            },
            str(news.get("source", "") or "news_source_missing"),
            _news_as_of(news.get("datetime")) or decision_date,
            str(news.get("url", "") or ""),
        )

    coverage = item.get("data_coverage") or {}
    fundamental_coverage = coverage.get("fundamental") or item.get("fundamental_status") or {}
    add(
        "coverage",
        "Known missing or partial evidence",
        {
            "fundamental_status": fundamental_coverage.get("status"),
            "missing_fields": fundamental_coverage.get("missing_fields") or [],
            "catalyst_status": (coverage.get("catalyst") or {}).get("status"),
        },
        "derived:scout.data_coverage",
        decision_date,
    )
    matched_lessons = match_outcome_lessons(
        item,
        outcome_memory or {},
        max_lessons=max_outcome_lessons,
    )
    for lesson in matched_lessons:
        add(
            "historical_outcome",
            "Benchmark-relative cohort outcome from prior independent decision dates",
            {
                "lesson_id": lesson.get("lesson_id"),
                "cohort_type": lesson.get("cohort_type"),
                "dimensions": lesson.get("dimensions") or {},
                "horizon": lesson.get("horizon"),
                "status": lesson.get("status"),
                "policy_effect": lesson.get("policy_effect"),
                "record_count": lesson.get("record_count"),
                "independent_date_count": lesson.get("independent_date_count"),
                "shrunk_alpha_pct": lesson.get("shrunk_alpha_pct"),
                "ci95_alpha_pct": lesson.get("ci95_alpha_pct") or {},
                "drift": lesson.get("drift") or {},
            },
            "derived:scout.outcome_memory",
            str((outcome_memory or {}).get("as_of_date", "") or decision_date),
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker,
        "decision_date": decision_date,
        "fact_fingerprint": fact_fingerprint([item]),
        "outcome_memory_as_of": str((outcome_memory or {}).get("as_of_date", "") or ""),
        "matched_outcome_lesson_count": len(matched_lessons),
        "evidence": entries,
    }


def build_research_packets(
    candidates: list[dict],
    decision_date: str,
    limit: int = MAX_FINALISTS,
    outcome_memory: Optional[dict] = None,
    max_outcome_lessons: int = 6,
) -> list[dict]:
    capped = max(0, min(int(limit or MAX_FINALISTS), MAX_FINALISTS))
    return [
        build_evidence_packet(
            item,
            decision_date,
            outcome_memory=outcome_memory,
            max_outcome_lessons=max_outcome_lessons,
        )
        for item in candidates[:capped]
    ]


def validate_research_reviews(rows: Any, packets: list[dict]) -> tuple[dict[str, dict], str]:
    if not isinstance(rows, list):
        return {}, "research_reviews_missing"

    packet_by_ticker = {str(packet.get("ticker", "")): packet for packet in packets}
    valid_ids = {
        ticker: {str(entry.get("evidence_id", "")) for entry in packet.get("evidence", [])}
        for ticker, packet in packet_by_ticker.items()
    }
    historical_effect_by_id = {
        ticker: {
            str(entry.get("evidence_id", "")): str(
                ((entry.get("value") or {}).get("policy_effect", ""))
                or ""
            ).upper()
            for entry in packet.get("evidence", [])
            if entry.get("category") == "historical_outcome"
        }
        for ticker, packet in packet_by_ticker.items()
    }
    reviews: dict[str, dict] = {}
    required_cases = ("bull_case", "bear_case", "risk_case", "invalidation")

    for row in rows:
        if not isinstance(row, dict):
            return {}, "research_review_not_object"
        ticker = str(row.get("ticker", "") or "").strip().upper()
        if ticker not in packet_by_ticker:
            return {}, f"research_ticker_not_in_input:{ticker}"
        if ticker in reviews:
            return {}, f"duplicate_research_ticker:{ticker}"
        disposition = str(row.get("disposition", "") or "").upper()
        if disposition not in {"KEEP", "DROP"}:
            return {}, f"invalid_disposition:{ticker}"

        memory_effect = str(row.get("memory_effect", "") or "").upper()
        memory_refs = row.get("memory_evidence_refs")
        if memory_effect not in {"NONE", "SUPPORT", "WEAKEN"}:
            return {}, f"invalid_memory_effect:{ticker}"
        if not isinstance(memory_refs, list):
            return {}, f"memory_evidence_refs_missing:{ticker}"
        normalized_memory_refs = list(dict.fromkeys(str(ref) for ref in memory_refs))[:8]
        if memory_effect == "NONE" and normalized_memory_refs:
            return {}, f"memory_none_with_refs:{ticker}"
        if memory_effect != "NONE":
            if not normalized_memory_refs:
                return {}, f"memory_effect_unsupported:{ticker}"
            effects = historical_effect_by_id[ticker]
            if any(ref not in effects for ref in normalized_memory_refs):
                return {}, f"memory_effect_invalid_ref:{ticker}"
            if memory_effect not in {effects[ref] for ref in normalized_memory_refs}:
                return {}, f"memory_effect_mismatch:{ticker}"

        normalized = {
            "ticker": ticker,
            "disposition": disposition,
            "memory_effect": memory_effect,
            "memory_evidence_refs": normalized_memory_refs,
        }
        for case_name in required_cases:
            case = row.get(case_name)
            if not isinstance(case, dict):
                return {}, f"{case_name}_missing:{ticker}"
            summary = str(case.get("summary", "") or "").strip()[:800]
            refs = case.get("evidence_refs")
            if not summary or not isinstance(refs, list) or not refs:
                return {}, f"{case_name}_unsupported:{ticker}"
            normalized_refs = [str(ref) for ref in refs]
            if any(ref not in valid_ids[ticker] for ref in normalized_refs):
                return {}, f"{case_name}_invalid_evidence_ref:{ticker}"
            normalized[case_name] = {
                "summary": summary,
                "evidence_refs": list(dict.fromkeys(normalized_refs))[:8],
            }
        reviews[ticker] = normalized

    missing = sorted(set(packet_by_ticker) - set(reviews))
    if missing:
        return {}, f"research_review_missing_tickers:{','.join(missing)}"
    return reviews, ""
