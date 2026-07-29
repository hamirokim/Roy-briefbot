"""Leakage-controlled outcome memory for SCOUT cohorts."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Optional

import pandas as pd
import yaml


BASE_DIR = Path(__file__).resolve().parents[2]
SCOUT_DATA_DIR = BASE_DIR / "data" / "scout"
CONFIG_PATH = BASE_DIR / "config" / "ronin_settings.yaml"
SCHEMA_VERSION = "scout_outcome_memory_v0_1"


def load_outcome_memory_config() -> dict:
    try:
        payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        return (((payload.get("scout") or {}).get("outcome_memory")) or {})
    except Exception:
        return {}


def _parse_date(value: Any) -> Optional[date]:
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _safe_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 8) if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return str(value)


def classify_market_regime(history: pd.DataFrame) -> dict:
    """Classify a benchmark using observations available at decision time."""
    if history is None or len(history) < 21:
        return {"status": "UNKNOWN", "reason": "benchmark_history_short"}
    frame = history.copy()
    columns = {str(column).lower(): column for column in frame.columns}
    close_column = columns.get("close")
    if close_column is None:
        return {"status": "UNKNOWN", "reason": "benchmark_close_missing"}
    close = pd.to_numeric(frame[close_column], errors="coerce").dropna()
    if len(close) < 21:
        return {"status": "UNKNOWN", "reason": "benchmark_history_short"}
    current = float(close.iloc[-1])
    ret_20d = current / float(close.iloc[-21]) - 1
    ma200 = float(close.iloc[-200:].mean()) if len(close) >= 200 else None
    if ma200 is None:
        status = "POSITIVE" if ret_20d > 0 else "NEGATIVE" if ret_20d < 0 else "MIXED"
        reason = "20d_return_only"
    elif current > ma200 and ret_20d > 0:
        status = "BULL"
        reason = "above_ma200_and_positive_20d"
    elif current < ma200 and ret_20d < 0:
        status = "BEAR"
        reason = "below_ma200_and_negative_20d"
    else:
        status = "MIXED"
        reason = "trend_and_momentum_diverge"
    date_column = columns.get("date")
    as_of = ""
    if date_column is not None:
        try:
            as_of = pd.to_datetime(frame[date_column].iloc[-1]).strftime("%Y-%m-%d")
        except Exception:
            as_of = ""
    elif isinstance(frame.index, pd.DatetimeIndex):
        as_of = pd.to_datetime(frame.index[-1]).strftime("%Y-%m-%d")
    return {
        "status": status,
        "reason": reason,
        "as_of": as_of,
        "ret_20d_pct": round(ret_20d * 100, 2),
        "close_vs_ma200_pct": (
            round((current / ma200 - 1) * 100, 2)
            if ma200 and ma200 > 0
            else None
        ),
    }


def _market_regime(record: dict) -> str:
    return str(
        (((record.get("benchmark") or {}).get("market_regime") or {}).get("status"))
        or ((record.get("decision_context") or {}).get("market_regime") or {}).get("status")
        or "UNKNOWN"
    ).upper()


def _liquidity_bucket(record: dict) -> str:
    positives = {str(value) for value in (record.get("factor_positives") or [])}
    negatives = {str(value) for value in (record.get("factor_negatives") or [])}
    if "liquidity_good" in positives:
        return "DEEP"
    if "liquidity_weak" in negatives:
        return "WEAK"
    return "ADEQUATE"


def _event_timing(record: dict) -> str:
    event_types = {str(value).lower() for value in (record.get("catalyst_event_types") or [])}
    if "earnings" not in event_types:
        return "NO_EARNINGS_EVENT"
    return "EARNINGS_UPCOMING" if bool(record.get("catalyst_has_upcoming")) else "EARNINGS_RECENT"


def _condition_sets(record: dict) -> list[tuple[str, dict]]:
    country = str(record.get("country", "") or "UNKNOWN").upper()
    lane = str(record.get("primary_lane", "") or "unknown")
    regime = _market_regime(record)
    sector = str(record.get("sector", "") or "unknown")
    sector_rrg = str(record.get("sector_rrg_quadrant", "") or "UNKNOWN").upper()
    theme_status = str(record.get("theme_industry_status", "") or "unknown")
    quality = str(record.get("quality_auditor_status", "") or "unknown")
    liquidity = _liquidity_bucket(record)
    catalyst = str(record.get("catalyst_classification", "") or "NO_DATA")
    timing = _event_timing(record)
    signals = sorted({str(value) for value in (record.get("signal_keys") or []) if value})
    themes = sorted({str(value) for value in (record.get("theme_keys") or []) if value})

    cohorts = [
        ("setup", {"country": country, "primary_lane": lane}),
        ("catalyst_timing", {
            "country": country,
            "catalyst": catalyst,
            "event_timing": timing,
        }),
    ]
    if regime != "UNKNOWN":
        cohorts.append(("market_regime", {"country": country, "market_regime": regime}))
        cohorts.append(("setup_regime", {
            "country": country,
            "primary_lane": lane,
            "market_regime": regime,
        }))
    if sector != "unknown" and sector_rrg != "UNKNOWN":
        cohorts.append(("sector_state", {
            "country": country,
            "sector": sector,
            "sector_rrg_quadrant": sector_rrg,
        }))
    if quality != "unknown":
        cohorts.append(("quality_liquidity", {
            "country": country,
            "quality": quality,
            "liquidity": liquidity,
        }))
    if regime != "UNKNOWN" and theme_status != "unknown":
        cohorts.append(("setup_environment", {
            "country": country,
            "primary_lane": lane,
            "market_regime": regime,
            "theme_status": theme_status,
        }))
    for signal in signals:
        cohorts.append(("signal", {"country": country, "signal": signal}))
        if regime != "UNKNOWN":
            cohorts.append(("signal_regime", {
                "country": country,
                "signal": signal,
                "market_regime": regime,
            }))
        if signal == "bb_squeeze" and quality != "unknown":
            cohorts.append(("bb_quality_liquidity", {
                "country": country,
                "signal": signal,
                "quality": quality,
                "liquidity": liquidity,
            }))
    for theme in themes:
        if regime != "UNKNOWN":
            cohorts.append(("theme_regime", {
                "country": country,
                "theme": theme,
                "market_regime": regime,
            }))
        if sector_rrg != "UNKNOWN":
            cohorts.append(("theme_sector_state", {
                "country": country,
                "theme": theme,
                "sector_rrg_quadrant": sector_rrg,
            }))
    return cohorts


def candidate_condition_sets(item: dict) -> set[tuple[str, str]]:
    theme = item.get("theme_industry") or {}
    catalyst = item.get("catalyst_context") or {}
    record = {
        "country": item.get("country"),
        "primary_lane": (item.get("top3_selection") or {}).get("primary_lane"),
        "sector": item.get("sector"),
        "sector_rrg_quadrant": (theme.get("sector") or {}).get("quadrant"),
        "theme_industry_status": theme.get("status"),
        "quality_auditor_status": (item.get("quality_auditor") or {}).get("status"),
        "factor_positives": (item.get("factor_context") or {}).get("positives") or [],
        "factor_negatives": (item.get("factor_context") or {}).get("negatives") or [],
        "catalyst_classification": catalyst.get("classification"),
        "catalyst_event_types": [
            row.get("event_type")
            for row in (catalyst.get("news") or [])
            if isinstance(row, dict) and row.get("event_type")
        ],
        "catalyst_has_upcoming": bool((catalyst.get("freshness") or {}).get("has_upcoming")),
        "signal_keys": item.get("signal_keys") or [],
        "theme_keys": [
            row.get("theme_key")
            for row in (theme.get("themes") or [])
            if isinstance(row, dict) and row.get("theme_key")
        ],
        "decision_context": item.get("decision_context") or {},
    }
    return {
        (cohort_type, json.dumps(dimensions, sort_keys=True, ensure_ascii=False))
        for cohort_type, dimensions in _condition_sets(record)
    }


def _alpha(record: dict, horizon: int) -> Optional[float]:
    return _safe_float(
        ((((record.get("benchmark") or {}).get("alpha") or {}).get(f"d{horizon}") or {}).get("alpha_pct"))
    )


def _cluster_by_date(samples: list[dict]) -> list[dict]:
    by_date: dict[str, list[float]] = defaultdict(list)
    for sample in samples:
        by_date[str(sample["date"])].append(float(sample["alpha"]))
    return [
        {"date": date_key, "alpha": mean(values), "record_count": len(values)}
        for date_key, values in sorted(by_date.items())
    ]


def _weighted_mean(rows: list[dict], as_of: date, half_life_days: float) -> tuple[Optional[float], float]:
    if not rows:
        return None, 0.0
    weights = []
    values = []
    for row in rows:
        row_date = _parse_date(row.get("date")) or as_of
        age = max(0, (as_of - row_date).days)
        weight = math.exp(-math.log(2) * age / max(1.0, half_life_days))
        weights.append(weight)
        values.append(float(row["alpha"]))
    total = sum(weights)
    weighted = sum(value * weight for value, weight in zip(values, weights)) / total
    effective_n = total * total / sum(weight * weight for weight in weights)
    return weighted, effective_n


def _cohort_result(
    cohort_type: str,
    dimensions: dict,
    horizon: int,
    samples: list[dict],
    as_of: date,
    global_prior: float,
    cfg: dict,
) -> dict:
    clusters = _cluster_by_date(samples)
    values = [float(row["alpha"]) for row in clusters]
    unique_dates = len(values)
    record_count = len(samples)
    raw_mean = mean(values)
    weighted_mean, effective_n = _weighted_mean(
        clusters,
        as_of,
        float(cfg.get("half_life_days", 30) or 30),
    )
    prior_strength = float(cfg.get("prior_strength_dates", 5) or 5)
    shrunk_mean = (
        ((weighted_mean or 0.0) * effective_n + global_prior * prior_strength)
        / (effective_n + prior_strength)
    )
    standard_error = (stdev(values) / math.sqrt(unique_dates)) if unique_dates >= 2 else None
    ci_low = raw_mean - 1.96 * standard_error if standard_error is not None else None
    ci_high = raw_mean + 1.96 * standard_error if standard_error is not None else None
    latest_date = max((_parse_date(row["date"]) for row in clusters), default=None)
    age_days = (as_of - latest_date).days if latest_date else None
    recent_window_days = int(cfg.get("recent_window_days", 20) or 20) + (2 * horizon)
    recent_cutoff = as_of - timedelta(days=recent_window_days)
    recent = [row["alpha"] for row in clusters if (_parse_date(row["date"]) or as_of) >= recent_cutoff]
    older = [row["alpha"] for row in clusters if (_parse_date(row["date"]) or as_of) < recent_cutoff]
    drift_gap = (mean(recent) - mean(older)) if recent and older else None

    min_records = int(cfg.get("min_records", 20) or 20)
    min_dates = int(cfg.get("min_independent_dates", 10) or 10)
    min_recent_dates = int(cfg.get("min_recent_dates", 4) or 4)
    stale_after = int(cfg.get("stale_after_days", 60) or 60)
    min_drift = float(cfg.get("min_drift_alpha_pct", 2.0) or 2.0)
    enough = record_count >= min_records and unique_dates >= min_dates
    invalidated = (
        enough
        and len(recent) >= min_recent_dates
        and len(older) >= min_recent_dates
        and mean(older) > 0
        and mean(recent) < 0
        and drift_gap is not None
        and drift_gap <= -min_drift
    )
    if not enough:
        status = "COLLECTING"
    elif age_days is not None and age_days > stale_after:
        status = "STALE"
    elif invalidated:
        status = "INVALIDATED_BY_DRIFT"
    elif ci_high is not None and ci_high < 0 and shrunk_mean < 0:
        status = "ACTIVE_CAUTION"
    elif ci_low is not None and ci_low > 0 and shrunk_mean > 0:
        status = "ACTIVE_SUPPORT"
    else:
        status = "MIXED"

    policy_effect = (
        "SUPPORT" if status == "ACTIVE_SUPPORT"
        else "WEAKEN" if status in {"ACTIVE_CAUTION", "INVALIDATED_BY_DRIFT"}
        else "NONE"
    )
    dimension_key = json.dumps(dimensions, sort_keys=True, ensure_ascii=False)
    lesson_id = hashlib.sha256(
        f"{cohort_type}|{dimension_key}|d{horizon}".encode("utf-8")
    ).hexdigest()[:16]
    return _json_value({
        "lesson_id": lesson_id,
        "cohort_type": cohort_type,
        "dimensions": dimensions,
        "horizon": f"d{horizon}",
        "status": status,
        "policy_effect": policy_effect,
        "record_count": record_count,
        "independent_date_count": unique_dates,
        "effective_date_count": round(effective_n, 2),
        "latest_observation_date": latest_date.isoformat() if latest_date else "",
        "age_days": age_days,
        "raw_mean_alpha_pct": round(raw_mean, 3),
        "median_alpha_pct": round(median(values), 3),
        "recency_weighted_alpha_pct": round(weighted_mean, 3) if weighted_mean is not None else None,
        "shrunk_alpha_pct": round(shrunk_mean, 3),
        "positive_date_rate": round(sum(value > 0 for value in values) / unique_dates, 3),
        "ci95_alpha_pct": {
            "low": round(ci_low, 3) if ci_low is not None else None,
            "high": round(ci_high, 3) if ci_high is not None else None,
        },
        "drift": {
            "recent_window_days": recent_window_days,
            "older_mean_alpha_pct": round(mean(older), 3) if older else None,
            "recent_mean_alpha_pct": round(mean(recent), 3) if recent else None,
            "gap_pct": round(drift_gap, 3) if drift_gap is not None else None,
            "recent_date_count": len(recent),
            "older_date_count": len(older),
        },
    })


def build_outcome_memory(
    records: list[dict],
    as_of_date: str,
    cfg: Optional[dict] = None,
    output_dir: Optional[Path] = None,
    persist: bool = True,
) -> dict:
    cfg = cfg or {}
    as_of = _parse_date(as_of_date) or date.today()
    horizons = [int(value) for value in (cfg.get("horizons") or [5, 10, 20])]
    eligible = [
        record for record in records
        if record.get("bucket") == "candidate" and record.get("status") == "OK"
    ]
    global_samples: dict[int, list[dict]] = defaultdict(list)
    cohort_samples: dict[tuple[str, str, int], list[dict]] = defaultdict(list)
    for record in eligible:
        snapshot_date = str(record.get("snapshot_date", "") or "")
        if not _parse_date(snapshot_date):
            continue
        for horizon in horizons:
            alpha = _alpha(record, horizon)
            if alpha is None:
                continue
            sample = {"date": snapshot_date, "alpha": alpha, "ticker": record.get("ticker", "")}
            global_samples[horizon].append(sample)
            for cohort_type, dimensions in _condition_sets(record):
                dimension_key = json.dumps(dimensions, sort_keys=True, ensure_ascii=False)
                cohort_samples[(cohort_type, dimension_key, horizon)].append(sample)

    global_priors = {}
    for horizon, samples in global_samples.items():
        clusters = _cluster_by_date(samples)
        global_priors[f"d{horizon}"] = round(mean(row["alpha"] for row in clusters), 3) if clusters else 0.0

    lessons = []
    for (cohort_type, dimension_key, horizon), samples in sorted(cohort_samples.items()):
        dimensions = json.loads(dimension_key)
        lessons.append(_cohort_result(
            cohort_type,
            dimensions,
            horizon,
            samples,
            as_of,
            float(global_priors.get(f"d{horizon}", 0.0) or 0.0),
            cfg,
        ))
    status_counts: dict[str, int] = defaultdict(int)
    for lesson in lessons:
        status_counts[str(lesson["status"])] += 1
    source_fingerprint_payload = sorted([
        {
            "snapshot_date": record.get("snapshot_date"),
            "ticker": record.get("ticker"),
            "d5_alpha": _alpha(record, 5),
            "d10_alpha": _alpha(record, 10),
            "d20_alpha": _alpha(record, 20),
        }
        for record in eligible
    ], key=lambda row: (str(row.get("snapshot_date", "")), str(row.get("ticker", ""))))
    source_record_fingerprint = hashlib.sha256(
        json.dumps(
            source_fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    payload = _json_value({
        "schema_version": SCHEMA_VERSION,
        "as_of_date": as_of.isoformat(),
        "source": {
            "performance_schema": "scout_performance_v0_5",
            "candidate_records": len(eligible),
            "point_in_time": True,
            "benchmark_relative": True,
            "date_clustered": True,
            "record_fingerprint": source_record_fingerprint,
        },
        "governance": {
            "influence_mode": str(cfg.get("influence_mode", "advisory") or "advisory"),
            "policy_authority": False,
            "min_records": int(cfg.get("min_records", 20) or 20),
            "min_independent_dates": int(cfg.get("min_independent_dates", 10) or 10),
            "half_life_days": float(cfg.get("half_life_days", 30) or 30),
            "prior_strength_dates": float(cfg.get("prior_strength_dates", 5) or 5),
        },
        "global_prior_alpha_pct": global_priors,
        "summary": {
            "lesson_count": len(lessons),
            "status_counts": dict(status_counts),
            "actionable_count": sum(lesson.get("policy_effect") != "NONE" for lesson in lessons),
        },
        "lessons": lessons,
    })
    if persist:
        target = Path(output_dir) if output_dir is not None else SCOUT_DATA_DIR
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"outcome_memory_{as_of.isoformat()}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["path"] = str(path)
    return payload


def load_latest_outcome_memory(
    before_date: str,
    directory: Optional[Path] = None,
) -> dict:
    cutoff = _parse_date(before_date)
    target = Path(directory) if directory is not None else SCOUT_DATA_DIR
    if not cutoff or not target.exists():
        return {}
    choices = []
    for path in target.glob("outcome_memory_*.json"):
        memory_date = _parse_date(path.stem.replace("outcome_memory_", ""))
        if memory_date and memory_date < cutoff:
            choices.append((memory_date, path))
    if not choices:
        return {}
    _, path = max(choices, key=lambda item: item[0])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        source = payload.get("source") or {}
        if payload.get("schema_version") != SCHEMA_VERSION:
            return {}
        if not bool(source.get("point_in_time")) or not bool(source.get("benchmark_relative")):
            return {}
        if _parse_date(payload.get("as_of_date")) != _parse_date(
            path.stem.replace("outcome_memory_", "")
        ):
            return {}
        return payload
    except Exception:
        return {}


def match_outcome_lessons(item: dict, memory: dict, max_lessons: int = 6) -> list[dict]:
    condition_keys = candidate_condition_sets(item)
    matched = []
    for lesson in memory.get("lessons", []) or []:
        if lesson.get("policy_effect") not in {"SUPPORT", "WEAKEN"}:
            continue
        key = (
            str(lesson.get("cohort_type", "")),
            json.dumps(lesson.get("dimensions") or {}, sort_keys=True, ensure_ascii=False),
        )
        if key not in condition_keys:
            continue
        matched.append(lesson)
    matched.sort(
        key=lambda lesson: (
            len(lesson.get("dimensions") or {}),
            int(lesson.get("independent_date_count", 0) or 0),
            abs(float(lesson.get("shrunk_alpha_pct", 0.0) or 0.0)),
        ),
        reverse=True,
    )
    return matched[:max(0, int(max_lessons or 0))]
