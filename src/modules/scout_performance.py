"""SCOUT recommendation performance ledger.

추천 스냅샷을 원장으로 삼아 후보 자체의 사후 반응을 추적한다.
실제 매수 여부는 별도 필드로 분리하고, 성과 판단에는 포함하지 않는다.
"""

from __future__ import annotations

import json
import logging
import math
from collections import Counter, defaultdict
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from src.collectors.global_ohlcv import fetch_daily_ohlcv_yf, fetch_ohlcv
from src.modules.scout_outcome_memory import classify_market_regime
from src.utils import now_kst, today_kst_str

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
SCOUT_DATA_DIR = BASE_DIR / "data" / "scout"

FOLLOWUP_DAYS = [1, 3, 5, 10, 20]
PRODUCTION_POLICY_ID = "integrity_v1"
LEGACY_POLICY_ID = "legacy_recorded"

WINNER_RET_20D = 0.05
WINNER_MFE = 0.08
FAST_FAIL_RET_5D = -0.05
FAST_FAIL_MAE = -0.07
FALSE_POSITIVE_MAX_MFE = 0.03


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value in ("", None):
            return default
        val = float(value)
        if math.isnan(val) or math.isinf(val):
            return default
        return val
    except Exception:
        return default


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def _parse_date(value: Any):
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        return parsed
    except Exception:
        return None


def _load_snapshots(days: int) -> list[dict]:
    today = now_kst().date()
    cutoff = today - timedelta(days=days)
    out = []
    if not SCOUT_DATA_DIR.exists():
        return out
    for path in sorted(SCOUT_DATA_DIR.glob("recommendation_snapshot_*.json")):
        date_part = path.stem.replace("recommendation_snapshot_", "")
        snap_date = _parse_date(date_part)
        if not snap_date or snap_date < cutoff:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            out.append(payload)
        except Exception as e:
            logger.debug("[scout performance] snapshot read 실패 %s: %s", path, e)
    return out


def _snapshot_policy_id(snapshot: dict) -> str:
    explicit = str(
        ((snapshot.get("policy") or {}).get("production_policy_id"))
        or snapshot.get("production_policy_id")
        or ""
    )
    if explicit:
        return explicit
    quality_audit = ((snapshot.get("summary") or {}).get("quality_audit") or {})
    if "production_coverage_complete" in quality_audit:
        return f"{PRODUCTION_POLICY_ID}_unversioned"
    return LEGACY_POLICY_ID


def _position_mapping() -> tuple[dict[str, str], dict[str, str]]:
    """실제 매수 여부 매핑. 실패 시 빈 매핑으로 계속한다."""
    try:
        from src.collectors.sheets import read_positions_for_mapping

        historical = read_positions_for_mapping(open_only=False) or {}
        open_only = read_positions_for_mapping(open_only=True) or {}
        return (
            {str(k).upper(): str(v) for k, v in historical.items() if v},
            {str(k).upper(): str(v) for k, v in open_only.items() if v},
        )
    except Exception as e:
        logger.debug("[scout performance] position mapping unavailable: %s", e)
        return {}, {}


def _ticker_key(ticker: str) -> str:
    return str(ticker or "").strip().upper()


def _primary_lane_from_item(item: dict) -> tuple[str, str]:
    if item.get("primary_lane") or item.get("primary_lane_status"):
        return str(item.get("primary_lane", "") or ""), str(item.get("primary_lane_status", "") or "")
    lanes = item.get("price_lanes") or {}
    rank = {
        "STAGE2_STRONG_PASS": 5,
        "STRONG_PASS": 5,
        "STAGE2_PASS": 4,
        "PASS": 4,
        "WAIT_CONFIRM": 2,
        "STAGE1_WAIT": 1,
        "WAIT": 1,
        "FAIL": 0,
    }
    best_lane = ""
    best_status = ""
    best_score = -1
    for lane in ["strength", "pullback", "left_side"]:
        status = str((lanes.get(lane) or {}).get("status", "") or "")
        score = rank.get(status, -1)
        if score > best_score:
            best_lane, best_status, best_score = lane, status, score
    return best_lane, best_status


def _nested_status(item: dict, flat_key: str, nested_key: str, child: str = "status") -> str:
    if item.get(flat_key):
        return str(item.get(flat_key) or "")
    nested = item.get(nested_key) or {}
    return str(nested.get(child, "") or "")


def _signal_keys(item: dict) -> list[str]:
    keys = item.get("signal_keys", [])
    if isinstance(keys, str):
        return [k for k in keys.split(",") if k]
    return [str(k) for k in (keys or []) if k]


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value in ("", None):
        return []
    return [value]


def _metric_from(*sources: dict, key: str, default: Optional[float] = None) -> Optional[float]:
    for source in sources:
        if not isinstance(source, dict):
            continue
        val = _safe_float(source.get(key), None)
        if val is not None:
            return val
    return default


def _normalise_ohlcv(df: Any) -> Optional[pd.DataFrame]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    rename = {c: str(c).title() for c in df.columns}
    out = df.rename(columns=rename).copy()
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(set(out.columns)):
        return None
    out = out[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    out["Date"] = pd.to_datetime(out["Date"]).dt.tz_localize(None)
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["Date", "Close"]).sort_values("Date").reset_index(drop=True)
    return out if not out.empty else None


def _first_trade_index(df: pd.DataFrame, date_value: str) -> Optional[int]:
    d = _parse_date(date_value)
    if d is None:
        return None
    dates = pd.to_datetime(df["Date"]).dt.date
    matches = np.where(dates >= d)[0]
    if len(matches) == 0:
        return None
    return int(matches[0])


def _first_executable_index(df: pd.DataFrame, record: dict) -> tuple[Optional[int], dict]:
    """Choose the first daily open that was still executable when the snapshot was generated."""
    snapshot_date = _parse_date(record.get("snapshot_date", ""))
    generated_at = _parse_datetime(record.get("generated_at", ""))
    country = str(record.get("country", "") or "")
    if snapshot_date is None:
        return None, {"status": "INVALID_DECISION_DATE"}

    earliest_date = snapshot_date
    timing_basis = "snapshot_date_legacy"
    if generated_at is not None:
        timing_basis = "generated_at_market_clock"
        if country == "KR":
            local = generated_at.astimezone(ZoneInfo("Asia/Seoul"))
            earliest_date = local.date()
            if local.time() >= dt_time(9, 0):
                earliest_date += timedelta(days=1)
        elif country == "US":
            local = generated_at.astimezone(ZoneInfo("America/New_York"))
            earliest_date = local.date()
            if local.time() >= dt_time(9, 30):
                earliest_date += timedelta(days=1)

    dates = pd.to_datetime(df["Date"]).dt.date
    matches = np.where(dates >= earliest_date)[0]
    if len(matches) == 0:
        return None, {
            "status": "NO_EXECUTABLE_SESSION",
            "timing_basis": timing_basis,
            "earliest_date": earliest_date.isoformat(),
        }
    return int(matches[0]), {
        "status": "OK",
        "timing_basis": timing_basis,
        "earliest_date": earliest_date.isoformat(),
        "price_field": "Open",
    }


def _benchmark_ticker(item: dict, country: str) -> str:
    lanes = item.get("price_lanes") or {}
    benchmark = str(lanes.get("benchmark", "") or "")
    if benchmark:
        return benchmark
    if country == "US":
        return "SPY"
    if country == "KR":
        ticker = str(item.get("ticker", "") or "").upper()
        return "^KQ11" if ticker.endswith(".KQ") else "^KS11"
    return ""


def _followup_returns(df: pd.DataFrame, start_idx: int, entry_price: float) -> tuple[dict[str, Any], int]:
    returns: dict[str, Any] = {}
    max_horizon_available = 0
    for day in FOLLOWUP_DAYS:
        idx = start_idx + day
        key = f"d{day}"
        if idx < len(df):
            price = float(df["Close"].iloc[idx])
            returns[key] = {
                "price": round(price, 4),
                "return_pct": round((price / entry_price - 1) * 100, 2),
                "date": pd.to_datetime(df["Date"].iloc[idx]).strftime("%Y-%m-%d"),
            }
            max_horizon_available = day
        else:
            returns[key] = {"price": None, "return_pct": None, "date": ""}
    return returns, max_horizon_available


def _mfe_mae(df: pd.DataFrame, start_idx: int, entry_price: float, horizon: int = 20) -> dict[str, Any]:
    end_idx = min(len(df) - 1, start_idx + horizon)
    if end_idx < start_idx:
        return {"mfe_pct": None, "mae_pct": None}
    window = df.iloc[start_idx:end_idx + 1]
    max_high = float(window["High"].max())
    min_low = float(window["Low"].min())
    mfe = max_high / entry_price - 1
    mae = min_low / entry_price - 1
    return {
        "mfe_pct": round(mfe * 100, 2),
        "mae_pct": round(mae * 100, 2),
        "mfe_price": round(max_high, 4),
        "mae_price": round(min_low, 4),
        "window_days": int(end_idx - start_idx),
    }


def _pivot_events(series: pd.Series, start_idx: int, end_idx: int, kind: str) -> list[tuple[int, float]]:
    pivots: list[tuple[int, float]] = []
    for i in range(max(2, start_idx + 2), min(len(series) - 2, end_idx)):
        prev2 = series.iloc[i - 2:i]
        next2 = series.iloc[i + 1:i + 3]
        val = float(series.iloc[i])
        if kind == "low" and val <= float(prev2.min()) and val <= float(next2.min()):
            pivots.append((i, val))
        elif kind == "high" and val >= float(prev2.max()) and val >= float(next2.max()):
            pivots.append((i, val))
    return pivots


def _structure_events(df: pd.DataFrame, start_idx: int, horizon: int = 20) -> dict[str, Any]:
    end_idx = min(len(df) - 1, start_idx + horizon)
    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    volume = df["Volume"].astype(float)
    ma50 = close.rolling(50).mean()
    vol20 = volume.rolling(20).mean()

    low_pivots = _pivot_events(low, start_idx, end_idx, "low")
    high_pivots = _pivot_events(high, start_idx, end_idx, "high")
    higher_low = len(low_pivots) >= 2 and low_pivots[-1][1] > low_pivots[-2][1]
    higher_high = len(high_pivots) >= 2 and high_pivots[-1][1] > high_pivots[-2][1]

    ma50_recover_date = ""
    volume_breakout_date = ""
    for i in range(start_idx + 1, end_idx + 1):
        if not ma50_recover_date and not pd.isna(ma50.iloc[i]) and close.iloc[i - 1] <= ma50.iloc[i - 1] and close.iloc[i] > ma50.iloc[i]:
            ma50_recover_date = pd.to_datetime(df["Date"].iloc[i]).strftime("%Y-%m-%d")
        if not volume_breakout_date and not pd.isna(vol20.iloc[i]) and volume.iloc[i] >= vol20.iloc[i] * 1.5 and close.iloc[i] > close.iloc[i - 1]:
            volume_breakout_date = pd.to_datetime(df["Date"].iloc[i]).strftime("%Y-%m-%d")

    events = {
        "higher_low": bool(higher_low),
        "higher_high": bool(higher_high),
        "ma50_recover": bool(ma50_recover_date),
        "volume_breakout": bool(volume_breakout_date),
        "higher_low_date": pd.to_datetime(df["Date"].iloc[low_pivots[-1][0]]).strftime("%Y-%m-%d") if higher_low else "",
        "higher_high_date": pd.to_datetime(df["Date"].iloc[high_pivots[-1][0]]).strftime("%Y-%m-%d") if higher_high else "",
        "ma50_recover_date": ma50_recover_date,
        "volume_breakout_date": volume_breakout_date,
    }
    events["event_count"] = sum(1 for k in ["higher_low", "higher_high", "ma50_recover", "volume_breakout"] if events[k])
    return events


def _verdict(followups: dict[str, Any], mfe_mae: dict[str, Any], structure: dict[str, Any], available_day: int) -> str:
    if available_day < 5:
        return "PENDING"
    d5 = _safe_float((followups.get("d5") or {}).get("return_pct"))
    d10 = _safe_float((followups.get("d10") or {}).get("return_pct"))
    d20 = _safe_float((followups.get("d20") or {}).get("return_pct"))
    mfe = (_safe_float(mfe_mae.get("mfe_pct")) or 0.0) / 100.0
    mae = (_safe_float(mfe_mae.get("mae_pct")) or 0.0) / 100.0
    event_count = int(structure.get("event_count", 0) or 0)

    if (d5 is not None and d5 <= FAST_FAIL_RET_5D * 100) or mae <= FAST_FAIL_MAE:
        return "FAILED_FAST"
    if (d20 is not None and d20 >= WINNER_RET_20D * 100) or mfe >= WINNER_MFE:
        return "WINNER"
    if d10 is not None and d10 >= 3.0 and event_count >= 1:
        return "WINNER"
    if available_day >= 20 and d20 is not None and d20 <= 0 and mfe < FALSE_POSITIVE_MAX_MFE and event_count == 0:
        return "FALSE_POSITIVE"
    if available_day < 20:
        return "WATCH"
    return "NEUTRAL"


def _extract_record(
    snapshot_date: str,
    bucket: str,
    rank: int,
    item: dict,
    historical_pos: dict,
    open_pos: dict,
    snapshot_meta: Optional[dict] = None,
) -> dict:
    ticker = _ticker_key(item.get("ticker", ""))
    primary_lane, primary_lane_status = _primary_lane_from_item(item)
    catalyst = item.get("catalyst_context") or {}
    top3 = item.get("top3_selection") or {}
    selective_research = top3.get("selective_research") or item.get("selective_research") or {}
    price_lanes = item.get("price_lanes") or {}
    primary_lane_data = price_lanes.get(primary_lane) or {}
    primary_lane_metrics = primary_lane_data.get("metrics") or {}
    factor_context = item.get("factor_context") or {}
    factor_metrics = factor_context.get("metrics") or {}
    common_metrics = ((item.get("common_gate") or {}).get("metrics") or {})
    theme_industry = item.get("theme_industry") or {}
    theme_sector = theme_industry.get("sector") or {}
    catalyst_news = [
        row for row in (catalyst.get("news") or [])
        if isinstance(row, dict)
    ]
    strength_lane = price_lanes.get("strength") or {}
    pullback_lane = price_lanes.get("pullback") or {}
    left_side_lane = price_lanes.get("left_side") or {}
    drawdown_from_high = _metric_from(
        factor_metrics,
        primary_lane_metrics,
        key="drawdown_from_high",
        default=None,
    )
    if drawdown_from_high is None:
        drawdown_from_high = _metric_from(primary_lane_metrics, key="drawdown_from_252d_high", default=None)
    opportunity_score = _safe_float(
        top3.get("opportunity_score", item.get("selection_opportunity_score", None)),
        None,
    )
    lane = str(primary_lane or primary_lane_status or "")
    snapshot_meta = snapshot_meta or {}
    country = str(item.get("country", "") or "")
    return {
        "snapshot_date": snapshot_date,
        "generated_at": str(snapshot_meta.get("generated_at", "") or ""),
        "snapshot_schema_version": str(snapshot_meta.get("schema_version", "") or ""),
        "production_policy_id": str(
            snapshot_meta.get("production_policy_id")
            or LEGACY_POLICY_ID
        ),
        "snapshot_candidate_count": int(snapshot_meta.get("candidate_count", 0) or 0),
        "snapshot_decision_health": snapshot_meta.get("decision_health", {}) or {},
        "bucket": bucket,
        "rank": int(rank),
        "ticker": ticker,
        "name": item.get("name", ""),
        "country": country,
        "sector": item.get("sector", ""),
        "score": item.get("score", 0),
        "selection_tier": str(top3.get("tier", item.get("selection_tier", "")) or ""),
        "selection_rank": item.get("selection_rank"),
        "rule_selection_rank": top3.get("rule_selection_rank", item.get("rule_selection_rank")),
        "selection_lane_rank": int(top3.get("lane_rank", 0) or 0),
        "selection_support_count": int(top3.get("support_count", 0) or 0),
        "selection_support_reasons": _safe_list(top3.get("support_reasons", [])),
        "selection_catalyst_freshness_rank": int(top3.get("catalyst_freshness_rank", 0) or 0),
        "llm_selected": bool(top3.get("llm_selected", item.get("llm_selected", False))),
        "llm_override": bool(top3.get("llm_override", item.get("llm_override", False))),
        "llm_reason": str(top3.get("llm_reason", item.get("llm_reason", "")) or ""),
        "llm_risk": str(top3.get("llm_risk", item.get("llm_risk", "")) or ""),
        "llm_dropped": bool(top3.get("llm_dropped", item.get("llm_dropped", False))),
        "llm_drop_reason": str(top3.get("llm_drop_reason", item.get("llm_drop_reason", "")) or ""),
        "outcome_memory_effect": str(selective_research.get("memory_effect", "NONE") or "NONE"),
        "outcome_memory_evidence_refs": _safe_list(
            selective_research.get("memory_evidence_refs", [])
        ),
        "opportunity_score": opportunity_score,
        "drawdown_from_high": drawdown_from_high,
        "factor_ret_20d": _metric_from(factor_metrics, key="ret_20d", default=None),
        "factor_atr_pct": _metric_from(factor_metrics, key="atr_pct", default=None),
        "factor_positives": _safe_list(factor_context.get("positives", [])),
        "factor_negatives": _safe_list(factor_context.get("negatives", [])),
        "liquidity_buffer_multiple": _metric_from(
            factor_metrics,
            key="liquidity_buffer_multiple",
            default=None,
        ),
        "avg_traded_value_20d": _metric_from(
            common_metrics,
            key="avg_traded_value_20d",
            default=None,
        ),
        "primary_lane": primary_lane,
        "primary_lane_status": primary_lane_status,
        "primary_lane_reasons": _safe_list(primary_lane_data.get("reasons", [])),
        "primary_lane_review_flags": _safe_list(primary_lane_data.get("review_flags", [])),
        "primary_lane_metrics": primary_lane_metrics,
        "strength_lane_status": str(strength_lane.get("status", "") or ""),
        "strength_lane_metrics": strength_lane.get("metrics", {}) or {},
        "pullback_lane_status": str(pullback_lane.get("status", "") or ""),
        "pullback_lane_metrics": pullback_lane.get("metrics", {}) or {},
        "left_side_lane_status": str(left_side_lane.get("status", "") or ""),
        "left_side_stage": str(left_side_lane.get("stage", "") or ""),
        "left_side_lane_metrics": left_side_lane.get("metrics", {}) or {},
        "signal_keys": _signal_keys(item),
        "theme_industry_status": _nested_status(item, "theme_industry_status", "theme_industry"),
        "sector_rrg_quadrant": str(theme_sector.get("quadrant", "") or ""),
        "theme_keys": [
            str(row.get("theme_key"))
            for row in (theme_industry.get("themes") or [])
            if isinstance(row, dict) and row.get("theme_key")
        ],
        "quality_auditor_status": _nested_status(item, "quality_auditor_status", "quality_auditor"),
        "catalyst_classification": str(item.get("catalyst_classification") or catalyst.get("classification", "") or ""),
        "catalyst_freshness": str(item.get("catalyst_freshness") or ((catalyst.get("freshness") or {}).get("status", "")) or ""),
        "catalyst_event_types": sorted({
            str(row.get("event_type"))
            for row in catalyst_news
            if row.get("event_type")
        }),
        "catalyst_has_upcoming": bool((catalyst.get("freshness") or {}).get("has_upcoming")),
        "decision_context": item.get("decision_context") or {},
        "price_map": item.get("price_map") or {},
        "price_map_shadow": item.get("price_map_shadow") or {},
        "actually_bought": ticker in historical_pos,
        "currently_open": ticker in open_pos,
        "position_id": historical_pos.get(ticker, ""),
        "lane_key": lane,
        "benchmark_ticker": _benchmark_ticker(item, country),
    }


def _price_map_first_touch(
    price_map: dict,
    df: pd.DataFrame,
    start_idx: int,
    entry_price: float,
    horizon: int = 20,
) -> dict:
    if not bool(price_map.get("available")):
        return {"status": "UNAVAILABLE", "realized_r": None}
    resistance = price_map.get("first_resistance") or {}
    target = _safe_float(resistance.get("lower"))
    invalidation = _safe_float(price_map.get("invalidation_close_below"))
    if target is None or invalidation is None:
        return {"status": "LEVELS_MISSING", "realized_r": None}
    if target <= entry_price:
        return {
            "status": "TARGET_ALREADY_PASSED",
            "target": round(target, 4),
            "invalidation": round(invalidation, 4),
            "realized_r": None,
        }
    risk = entry_price - invalidation
    if risk <= 0:
        return {
            "status": "INVALID_GEOMETRY",
            "target": round(target, 4),
            "invalidation": round(invalidation, 4),
            "realized_r": None,
        }
    planned_r = (target - entry_price) / risk
    end_idx = min(len(df) - 1, start_idx + horizon)
    for idx in range(start_idx, end_idx + 1):
        target_hit = float(df["High"].iloc[idx]) >= target
        stop_hit = float(df["Low"].iloc[idx]) <= invalidation
        event_date = pd.to_datetime(df["Date"].iloc[idx]).strftime("%Y-%m-%d")
        if target_hit and stop_hit:
            return {
                "status": "AMBIGUOUS_SAME_BAR",
                "date": event_date,
                "target": round(target, 4),
                "invalidation": round(invalidation, 4),
                "planned_r": round(planned_r, 2),
                "realized_r": None,
            }
        if target_hit:
            return {
                "status": "TARGET_FIRST",
                "date": event_date,
                "target": round(target, 4),
                "invalidation": round(invalidation, 4),
                "planned_r": round(planned_r, 2),
                "realized_r": round(planned_r, 2),
            }
        if stop_hit:
            return {
                "status": "INVALIDATION_FIRST",
                "date": event_date,
                "target": round(target, 4),
                "invalidation": round(invalidation, 4),
                "planned_r": round(planned_r, 2),
                "realized_r": -1.0,
            }
    return {
        "status": "OPEN",
        "target": round(target, 4),
        "invalidation": round(invalidation, 4),
        "planned_r": round(planned_r, 2),
        "realized_r": None,
        "observed_sessions": int(end_idx - start_idx + 1),
    }


def _evaluate_price_map_engines(
    record: dict,
    df: pd.DataFrame,
    start_idx: int,
    entry_price: float,
) -> dict:
    shadow = record.get("price_map_shadow") or {}
    engines = dict(shadow.get("engines") or {})
    if "confirmed_swings_v1" not in engines and record.get("price_map"):
        engines["confirmed_swings_v1"] = record.get("price_map") or {}
    return {
        engine_id: _price_map_first_touch(price_map, df, start_idx, entry_price)
        for engine_id, price_map in sorted(engines.items())
        if isinstance(price_map, dict)
    }


def _snapshot_record_groups(snap: dict, include_radar_top: bool) -> list[tuple[str, list[dict]]]:
    groups = [("candidate", snap.get("candidates", []) or [])]
    llm_dropped = []
    for item in snap.get("radar_top", []) or []:
        top3 = item.get("top3_selection") or {}
        if bool(top3.get("llm_dropped", item.get("llm_dropped", False))):
            llm_dropped.append(item)
    if llm_dropped:
        groups.append(("llm_dropped", llm_dropped))
    if include_radar_top:
        groups.append(("radar_top", snap.get("radar_top", []) or []))
    for policy_key, policy in sorted((snap.get("shadow_policies") or {}).items()):
        if not isinstance(policy, dict):
            continue
        policy_id = str(policy.get("policy_id", policy_key) or policy_key)
        groups.append((f"shadow:{policy_id}", policy.get("candidates", []) or []))
    return groups


def _build_records(days: int, include_radar_top: bool) -> list[dict]:
    snapshots = _load_snapshots(days)
    historical_pos, open_pos = _position_mapping()
    base_records = []
    seen = set()
    for snap in snapshots:
        snap_date = str(snap.get("date", "") or "")
        summary = snap.get("summary") or {}
        snapshot_meta = {
            "generated_at": snap.get("generated_at", ""),
            "schema_version": snap.get("schema_version", ""),
            "production_policy_id": _snapshot_policy_id(snap),
            "candidate_count": len(snap.get("candidates", []) or []),
            "decision_health": summary.get("decision_health", {}) or {},
        }
        groups = _snapshot_record_groups(snap, include_radar_top)
        for bucket, items in groups:
            for rank, item in enumerate(items, 1):
                ticker = _ticker_key(item.get("ticker", ""))
                if not ticker:
                    continue
                key = (snap_date, bucket, ticker)
                if key in seen:
                    continue
                seen.add(key)
                base_records.append(
                    _extract_record(
                        snap_date,
                        bucket,
                        rank,
                        item,
                        historical_pos,
                        open_pos,
                        snapshot_meta=snapshot_meta,
                    )
                )
    return base_records


def _market_regime(df: pd.DataFrame, entry_idx: int) -> dict:
    """Classify the market using benchmark data strictly before the executable entry."""
    return classify_market_regime(df.iloc[:entry_idx])


def _benchmark_outcome(
    record: dict,
    candidate_followups: dict,
    ohlcv_cache: dict[str, Optional[pd.DataFrame]],
) -> dict:
    ticker = str(record.get("benchmark_ticker", "") or "")
    if not ticker:
        return {"status": "NO_BENCHMARK_MAPPING", "ticker": "", "followup": {}, "alpha": {}}
    df = ohlcv_cache.get(ticker)
    if df is None:
        return {"status": "NO_BENCHMARK_DATA", "ticker": ticker, "followup": {}, "alpha": {}}

    entry_date = record.get("entry_date_used", "")
    start_idx = _first_trade_index(df, entry_date)
    if start_idx is None:
        return {"status": "NO_BENCHMARK_START_BAR", "ticker": ticker, "followup": {}, "alpha": {}}
    entry_open = _safe_float(df["Open"].iloc[start_idx], None)
    if entry_open is None or entry_open <= 0:
        return {"status": "NO_BENCHMARK_OPEN", "ticker": ticker, "followup": {}, "alpha": {}}

    followups, available_day = _followup_returns(df, start_idx, entry_open)
    alpha = {}
    for day in FOLLOWUP_DAYS:
        key = f"d{day}"
        candidate_return = _safe_float((candidate_followups.get(key) or {}).get("return_pct"))
        benchmark_return = _safe_float((followups.get(key) or {}).get("return_pct"))
        alpha[key] = {
            "alpha_pct": (
                round(candidate_return - benchmark_return, 2)
                if candidate_return is not None and benchmark_return is not None
                else None
            ),
            "candidate_return_pct": candidate_return,
            "benchmark_return_pct": benchmark_return,
        }
    return {
        "status": "OK",
        "ticker": ticker,
        "entry_date": pd.to_datetime(df["Date"].iloc[start_idx]).strftime("%Y-%m-%d"),
        "entry_price": round(entry_open, 4),
        "available_trading_days": int(available_day),
        "followup": followups,
        "alpha": alpha,
        "market_regime": _market_regime(df, start_idx),
    }


def _evaluate_record(record: dict, ohlcv_cache: dict[str, Optional[pd.DataFrame]]) -> dict:
    ticker = record.get("ticker", "")
    if ticker not in ohlcv_cache:
        ohlcv_cache[ticker] = _normalise_ohlcv(fetch_daily_ohlcv_yf(ticker, lookback=260))
    df = ohlcv_cache.get(ticker)
    if df is None:
        return {**record, "status": "NO_PRICE_DATA", "final_verdict": "PENDING"}

    start_idx, execution = _first_executable_index(df, record)
    if start_idx is None:
        return {
            **record,
            "status": "NO_EXECUTABLE_SESSION",
            "execution_policy": execution,
            "final_verdict": "PENDING",
        }

    entry_price = _safe_float(df["Open"].iloc[start_idx], None)
    if entry_price is None or entry_price <= 0:
        return {
            **record,
            "status": "NO_EXECUTABLE_OPEN",
            "execution_policy": execution,
            "final_verdict": "PENDING",
        }
    followups, available_day = _followup_returns(df, start_idx, entry_price)
    mfe_mae = _mfe_mae(df, start_idx, entry_price, horizon=20)
    structure = _structure_events(df, start_idx, horizon=20)
    verdict = _verdict(followups, mfe_mae, structure, available_day)
    evaluated = {
        **record,
        "status": "OK",
        "entry_date_used": pd.to_datetime(df["Date"].iloc[start_idx]).strftime("%Y-%m-%d"),
        "entry_price_used": round(entry_price, 4),
        "execution_policy": execution,
        "available_trading_days": int(available_day),
        "followup": followups,
        "mfe_mae": mfe_mae,
        "structure_events": structure,
        "price_map_engine_outcomes": _evaluate_price_map_engines(
            record,
            df,
            start_idx,
            entry_price,
        ),
        "final_verdict": verdict,
    }
    evaluated["benchmark"] = _benchmark_outcome(evaluated, followups, ohlcv_cache)
    return _json_safe(evaluated)


def _bucket_value(record: dict, key: str) -> str:
    if key == "lane":
        return str(record.get("primary_lane") or "unknown")
    if key == "lane_status":
        return str(record.get("primary_lane_status") or "unknown")
    if key == "theme":
        return str(record.get("theme_industry_status") or "unknown")
    if key == "quality":
        return str(record.get("quality_auditor_status") or "unknown")
    if key == "catalyst":
        return str(record.get("catalyst_classification") or "unknown")
    if key == "market_regime":
        return str(
            (((record.get("benchmark") or {}).get("market_regime") or {}).get("status"))
            or "unknown"
        )
    return "unknown"


def _aggregate(records: list[dict], key: str) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if r.get("bucket") != "candidate" or r.get("status") != "OK":
            continue
        buckets[_bucket_value(r, key)].append(r)

    rows = []
    for name, items in buckets.items():
        d20 = [
            _safe_float((r.get("followup", {}).get("d20") or {}).get("return_pct"))
            for r in items
        ]
        d20_clean = [v for v in d20 if v is not None]
        winners = sum(1 for r in items if r.get("final_verdict") == "WINNER")
        failed_fast = sum(1 for r in items if r.get("final_verdict") == "FAILED_FAST")
        bought = sum(1 for r in items if r.get("actually_bought"))
        rows.append({
            "key": name,
            "count": len(items),
            "avg_d20_return_pct": round(sum(d20_clean) / len(d20_clean), 2) if d20_clean else None,
            "avg_d20_alpha_pct": _avg_alpha(items, "d20"),
            "positive_d20_alpha_rate": _positive_alpha_rate(items, "d20"),
            "winner_rate": round(winners / len(items), 3) if items else 0,
            "failed_fast_rate": round(failed_fast / len(items), 3) if items else 0,
            "actually_bought_count": int(bought),
        })
    rows.sort(key=lambda r: (-int(r["count"]), -(r["avg_d20_return_pct"] or -999)))
    return rows


def _outcome_memory_comparison(records: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        if record.get("bucket") != "candidate":
            continue
        effect = str(record.get("outcome_memory_effect", "NONE") or "NONE").upper()
        if effect not in {"NONE", "SUPPORT", "WEAKEN"}:
            effect = "NONE"
        groups[effect].append(record)
    return {
        "evidence_status": "COLLECTING_UNTOUCHED_WINDOW",
        "counterfactual_proven": False,
        "winner_declared": False,
        "groups": {
            effect: _cohort_metrics(rows)
            for effect, rows in sorted(groups.items())
        },
    }


def _summary(records: list[dict], snapshots: Optional[list[dict]] = None) -> dict:
    candidates = [r for r in records if r.get("bucket") == "candidate"]
    ok = [r for r in candidates if r.get("status") == "OK"]
    verdicts = Counter(str(r.get("final_verdict", "")) for r in ok)
    bought = [r for r in ok if r.get("actually_bought")]
    d20 = [_safe_float((r.get("followup", {}).get("d20") or {}).get("return_pct")) for r in ok]
    d20_clean = [v for v in d20 if v is not None]
    decision_audits = _decision_audits(records, snapshots or []) if snapshots is not None else []
    return {
        "candidate_count": len(candidates),
        "evaluated_count": len(ok),
        "actually_bought_count": len(bought),
        "verdict_counts": dict(verdicts),
        "avg_d20_return_pct": round(sum(d20_clean) / len(d20_clean), 2) if d20_clean else None,
        "avg_alpha_pct": {day: _avg_alpha(ok, day) for day in ("d5", "d10", "d20")},
        "positive_alpha_rate": {
            day: _positive_alpha_rate(ok, day)
            for day in ("d5", "d10", "d20")
        },
        "aggregates": {
            "by_lane": _aggregate(records, "lane"),
            "by_lane_status": _aggregate(records, "lane_status"),
            "by_theme_industry": _aggregate(records, "theme"),
            "by_quality_auditor": _aggregate(records, "quality"),
            "by_catalyst": _aggregate(records, "catalyst"),
            "by_market_regime": _aggregate(records, "market_regime"),
        },
        "llm_override_comparison": _llm_override_comparison(records),
        "outcome_memory_comparison": _outcome_memory_comparison(records),
        "shadow_policy_comparison": _shadow_policy_comparison(records),
        "price_map_engine_comparison": _price_map_engine_comparison(records),
        "policy_comparison": _policy_comparison(records),
        "decision_audit": _decision_audit_summary(decision_audits),
        "decision_audits": decision_audits,
    }


def _price_map_engine_comparison(records: list[dict]) -> dict:
    """Compare frozen SR maps without declaring a winner from immature samples."""
    rows_by_engine: dict[str, list[dict]] = defaultdict(list)
    seen = set()
    ordered = sorted(
        records,
        key=lambda row: (
            0 if str(row.get("bucket", "")).startswith("shadow:pre_entry") else 1,
            str(row.get("snapshot_date", "")),
            str(row.get("ticker", "")),
        ),
    )
    for record in ordered:
        for engine_id, outcome in (record.get("price_map_engine_outcomes") or {}).items():
            key = (record.get("snapshot_date"), record.get("ticker"), engine_id)
            if key in seen or not isinstance(outcome, dict):
                continue
            seen.add(key)
            rows_by_engine[str(engine_id)].append(outcome)

    comparison = {}
    for engine_id, outcomes in sorted(rows_by_engine.items()):
        statuses = Counter(str(row.get("status", "")) for row in outcomes)
        realized = [
            _safe_float(row.get("realized_r"))
            for row in outcomes
            if _safe_float(row.get("realized_r")) is not None
        ]
        resolved = int(statuses.get("TARGET_FIRST", 0)) + int(statuses.get("INVALIDATION_FIRST", 0))
        comparison[engine_id] = {
            "count": len(outcomes),
            "resolved_count": resolved,
            "target_first": int(statuses.get("TARGET_FIRST", 0)),
            "invalidation_first": int(statuses.get("INVALIDATION_FIRST", 0)),
            "target_already_passed": int(statuses.get("TARGET_ALREADY_PASSED", 0)),
            "ambiguous_same_bar": int(statuses.get("AMBIGUOUS_SAME_BAR", 0)),
            "open": int(statuses.get("OPEN", 0)),
            "avg_realized_r": round(sum(realized) / len(realized), 2) if realized else None,
            "winner_declared": False,
        }
    return {
        "evidence_status": "COLLECTING_FORWARD_EVIDENCE",
        "winner_declared": False,
        "engines": comparison,
    }


def _record_result_brief(record: dict) -> dict:
    followup = record.get("followup") or {}
    mfe_mae = record.get("mfe_mae") or {}
    alpha = ((record.get("benchmark") or {}).get("alpha") or {})
    return {
        "snapshot_date": record.get("snapshot_date"),
        "ticker": record.get("ticker"),
        "bucket": record.get("bucket"),
        "status": record.get("status"),
        "final_verdict": record.get("final_verdict"),
        "rule_selection_rank": record.get("rule_selection_rank"),
        "selection_rank": record.get("selection_rank"),
        "selection_tier": record.get("selection_tier"),
        "primary_lane": record.get("primary_lane"),
        "primary_lane_status": record.get("primary_lane_status"),
        "llm_reason": record.get("llm_reason"),
        "llm_risk": record.get("llm_risk"),
        "llm_drop_reason": record.get("llm_drop_reason"),
        "d1_return_pct": (followup.get("d1") or {}).get("return_pct"),
        "d3_return_pct": (followup.get("d3") or {}).get("return_pct"),
        "d5_return_pct": (followup.get("d5") or {}).get("return_pct"),
        "d10_return_pct": (followup.get("d10") or {}).get("return_pct"),
        "d20_return_pct": (followup.get("d20") or {}).get("return_pct"),
        "d5_alpha_pct": (alpha.get("d5") or {}).get("alpha_pct"),
        "d10_alpha_pct": (alpha.get("d10") or {}).get("alpha_pct"),
        "d20_alpha_pct": (alpha.get("d20") or {}).get("alpha_pct"),
        "benchmark_ticker": (record.get("benchmark") or {}).get("ticker"),
        "market_regime": (
            ((record.get("benchmark") or {}).get("market_regime") or {}).get("status")
        ),
        "mfe_pct": mfe_mae.get("mfe_pct"),
        "mae_pct": mfe_mae.get("mae_pct"),
    }


def _avg_return(records: list[dict], day_key: str) -> Optional[float]:
    values = [
        _safe_float((r.get("followup", {}).get(day_key) or {}).get("return_pct"))
        for r in records
        if r.get("status") == "OK"
    ]
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def _alpha_value(record: dict, day_key: str) -> Optional[float]:
    return _safe_float(
        ((((record.get("benchmark") or {}).get("alpha") or {}).get(day_key) or {}).get("alpha_pct")),
        None,
    )


def _avg_alpha(records: list[dict], day_key: str) -> Optional[float]:
    values = [_alpha_value(record, day_key) for record in records if record.get("status") == "OK"]
    clean = [value for value in values if value is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def _positive_alpha_rate(records: list[dict], day_key: str) -> Optional[float]:
    values = [_alpha_value(record, day_key) for record in records if record.get("status") == "OK"]
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return round(sum(1 for value in clean if value > 0) / len(clean), 3)


def _cohort_metrics(records: list[dict]) -> dict:
    ok = [record for record in records if record.get("status") == "OK"]
    return {
        "count": len(records),
        "evaluated_count": len(ok),
        "snapshot_dates": sorted({str(record.get("snapshot_date", "") or "") for record in records}),
        "avg_return_pct": {day: _avg_return(ok, day) for day in ("d5", "d10", "d20")},
        "avg_alpha_pct": {day: _avg_alpha(ok, day) for day in ("d5", "d10", "d20")},
        "positive_alpha_rate": {
            day: _positive_alpha_rate(ok, day)
            for day in ("d5", "d10", "d20")
        },
    }


def _policy_comparison(records: list[dict]) -> dict:
    cohorts: dict[str, list[dict]] = defaultdict(list)
    radar_by_date: dict[str, list[dict]] = defaultdict(list)
    selected_by_date: dict[str, set[str]] = defaultdict(set)
    for record in records:
        bucket = str(record.get("bucket", "") or "")
        date_key = str(record.get("snapshot_date", "") or "")
        if bucket == "candidate":
            policy_id = str(record.get("production_policy_id", "") or LEGACY_POLICY_ID)
            cohorts[f"production:{policy_id}"].append(record)
            lane = str(record.get("primary_lane", "") or "unknown")
            lane_status = str(record.get("primary_lane_status", "") or "unknown")
            cohorts[f"production_lane:{policy_id}:{lane}"].append(record)
            cohorts[f"production_lane_status:{policy_id}:{lane}:{lane_status}"].append(record)
            selected_by_date[date_key].add(str(record.get("ticker", "") or ""))
        elif bucket.startswith("shadow:"):
            cohorts[bucket].append(record)
        elif bucket == "radar_top":
            radar_by_date[date_key].append(record)

    for date_key, rows in radar_by_date.items():
        baseline = [
            row for row in sorted(rows, key=lambda item: int(item.get("rank", 999) or 999))
            if str(row.get("ticker", "") or "") not in selected_by_date.get(date_key, set())
        ][:3]
        cohorts["baseline:radar_top3_not_selected"].extend(baseline)

    return {
        "evidence_status": "COLLECTING_FORWARD_EVIDENCE",
        "winner_declared": False,
        "winner": "",
        "reason": "정책별 동일 기간의 만기 초과수익 표본을 축적 중이며 자동 승자 선언은 하지 않음",
        "cohorts": {
            cohort_id: _cohort_metrics(items)
            for cohort_id, items in sorted(cohorts.items())
        },
    }


def _decision_audits(records: list[dict], snapshots: list[dict]) -> list[dict]:
    records_by_date: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        records_by_date[str(record.get("snapshot_date", "") or "")].append(record)

    audits = []
    for snapshot in snapshots:
        date_key = str(snapshot.get("date", "") or "")
        day_records = records_by_date.get(date_key, [])
        selected = [record for record in day_records if record.get("bucket") == "candidate"]
        selected_tickers = {str(record.get("ticker", "") or "") for record in selected}
        rejected = []
        seen = set()
        for record in day_records:
            ticker = str(record.get("ticker", "") or "")
            if record.get("bucket") != "radar_top" or ticker in selected_tickers or ticker in seen:
                continue
            seen.add(ticker)
            rejected.append(record)

        horizon_audits = {}
        for day_key in ("d5", "d10", "d20"):
            selected_alpha = [
                value for value in (_alpha_value(record, day_key) for record in selected)
                if value is not None
            ]
            rejected_with_alpha = [
                (record, value)
                for record in rejected
                for value in [_alpha_value(record, day_key)]
                if value is not None
            ]
            rejected_alpha = [value for _, value in rejected_with_alpha]
            best_selected = max(selected_alpha) if selected_alpha else None
            best_rejected = max(rejected_alpha) if rejected_alpha else None
            selected_avg = (
                sum(selected_alpha) / len(selected_alpha)
                if selected_alpha
                else 0.0
            )
            ranked_alternative = min(
                rejected_with_alpha,
                key=lambda pair: int(pair[0].get("rank", 999) or 999),
                default=None,
            )
            ranked_alternative_alpha = ranked_alternative[1] if ranked_alternative else None
            opportunity_cost = None
            if ranked_alternative_alpha is not None:
                opportunity_cost = round(
                    max(0.0, ranked_alternative_alpha - selected_avg),
                    2,
                )
            ex_post_upper_bound_gap = None
            if best_rejected is not None:
                ex_post_upper_bound_gap = round(
                    max(0.0, best_rejected - (best_selected if best_selected is not None else 0.0)),
                    2,
                )
            horizon_audits[day_key] = {
                "selected_evaluated": len(selected_alpha),
                "rejected_evaluated": len(rejected_alpha),
                "selected_positive_alpha": sum(1 for value in selected_alpha if value > 0),
                "selected_nonpositive_alpha": sum(1 for value in selected_alpha if value <= 0),
                "rejected_positive_alpha": sum(1 for value in rejected_alpha if value > 0),
                "best_selected_alpha_pct": round(best_selected, 2) if best_selected is not None else None,
                "best_rejected_alpha_pct": round(best_rejected, 2) if best_rejected is not None else None,
                "ranked_alternative_ticker": (
                    ranked_alternative[0].get("ticker")
                    if ranked_alternative
                    else ""
                ),
                "ranked_alternative_alpha_pct": (
                    round(ranked_alternative_alpha, 2)
                    if ranked_alternative_alpha is not None
                    else None
                ),
                "opportunity_cost_pct": opportunity_cost,
                "ex_post_upper_bound_gap_pct": ex_post_upper_bound_gap,
            }

        decision_health = ((snapshot.get("summary") or {}).get("decision_health") or {})
        candidate_count = len(snapshot.get("candidates", []) or [])
        abstention_status = "NOT_ABSTENTION"
        abstention_horizon = ""
        if candidate_count == 0:
            if str(decision_health.get("status", "")) == "DEGRADED_DATA":
                abstention_status = "DEGRADED_DATA"
            else:
                for day_key in ("d20", "d10", "d5"):
                    if horizon_audits[day_key]["rejected_evaluated"] > 0:
                        abstention_horizon = day_key
                        break
                if not abstention_horizon:
                    abstention_status = "PENDING"
                elif (horizon_audits[abstention_horizon]["best_rejected_alpha_pct"] or 0) > 0:
                    abstention_status = "MISSED_OPPORTUNITY"
                else:
                    abstention_status = "GOOD_ABSTENTION"

        audits.append({
            "snapshot_date": date_key,
            "production_policy_id": str(
                _snapshot_policy_id(snapshot)
            ),
            "candidate_count": candidate_count,
            "radar_comparison_count": len(rejected),
            "decision_health": decision_health,
            "abstention_status": abstention_status,
            "abstention_horizon": abstention_horizon,
            "horizons": horizon_audits,
        })
    return audits


def _decision_audit_summary(audits: list[dict]) -> dict:
    abstentions = [audit for audit in audits if audit.get("candidate_count", 0) == 0]
    d20_ready = [
        audit for audit in audits
        if int(((audit.get("horizons") or {}).get("d20") or {}).get("rejected_evaluated", 0)) > 0
    ]
    opportunity_costs = [
        _safe_float(((audit.get("horizons") or {}).get("d20") or {}).get("opportunity_cost_pct"))
        for audit in d20_ready
    ]
    opportunity_costs = [value for value in opportunity_costs if value is not None]
    upper_bound_gaps = [
        _safe_float(((audit.get("horizons") or {}).get("d20") or {}).get("ex_post_upper_bound_gap_pct"))
        for audit in d20_ready
    ]
    upper_bound_gaps = [value for value in upper_bound_gaps if value is not None]
    return {
        "snapshot_count": len(audits),
        "abstention_count": len(abstentions),
        "abstention_status_counts": dict(Counter(str(audit.get("abstention_status", "")) for audit in abstentions)),
        "d20_ready_count": len(d20_ready),
        "avg_d20_opportunity_cost_pct": (
            round(sum(opportunity_costs) / len(opportunity_costs), 2)
            if opportunity_costs
            else None
        ),
        "avg_d20_ex_post_upper_bound_gap_pct": (
            round(sum(upper_bound_gaps) / len(upper_bound_gaps), 2)
            if upper_bound_gaps
            else None
        ),
        "selected_d20_nonpositive_alpha_count": sum(
            int(((audit.get("horizons") or {}).get("d20") or {}).get("selected_nonpositive_alpha", 0))
            for audit in audits
        ),
        "rejected_d20_positive_alpha_count": sum(
            int(((audit.get("horizons") or {}).get("d20") or {}).get("rejected_positive_alpha", 0))
            for audit in audits
        ),
    }


def _llm_override_comparison(records: list[dict]) -> dict:
    """LLM이 뺀 규칙 후보와 LLM이 새로 넣은 후보의 별도 비교군."""
    dropped_raw = [
        r for r in records
        if r.get("bucket") == "llm_dropped" or bool(r.get("llm_dropped"))
    ]
    dropped = []
    seen_dropped = set()
    for r in dropped_raw:
        key = (r.get("snapshot_date"), r.get("ticker"))
        if key in seen_dropped:
            continue
        seen_dropped.add(key)
        dropped.append(r)
    added = [
        r for r in records
        if r.get("bucket") == "candidate"
        and bool(r.get("llm_selected"))
        and not r.get("rule_selection_rank")
    ]
    kept = [
        r for r in records
        if r.get("bucket") == "candidate"
        and bool(r.get("llm_selected"))
        and bool(r.get("rule_selection_rank"))
    ]
    return {
        "dropped_count": len(dropped),
        "added_count": len(added),
        "kept_count": len(kept),
        "dropped_tickers": [r.get("ticker") for r in dropped],
        "added_tickers": [r.get("ticker") for r in added],
        "kept_tickers": [r.get("ticker") for r in kept],
        "avg_d5_return_pct": {
            "dropped": _avg_return(dropped, "d5"),
            "added": _avg_return(added, "d5"),
            "kept": _avg_return(kept, "d5"),
        },
        "avg_d20_return_pct": {
            "dropped": _avg_return(dropped, "d20"),
            "added": _avg_return(added, "d20"),
            "kept": _avg_return(kept, "d20"),
        },
        "dropped": [_record_result_brief(r) for r in dropped],
        "added": [_record_result_brief(r) for r in added],
        "kept": [_record_result_brief(r) for r in kept],
    }


def _shadow_policy_comparison(records: list[dict]) -> dict:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        bucket = str(record.get("bucket", "") or "")
        if bucket.startswith("shadow:"):
            buckets[bucket.split(":", 1)[1]].append(record)

    comparison = {}
    for policy_id, items in sorted(buckets.items()):
        ok = [record for record in items if record.get("status") == "OK"]
        comparison[policy_id] = {
            "count": len(items),
            "evaluated_count": len(ok),
            "avg_d5_return_pct": _avg_return(ok, "d5"),
            "avg_d10_return_pct": _avg_return(ok, "d10"),
            "avg_d20_return_pct": _avg_return(ok, "d20"),
            "avg_d5_alpha_pct": _avg_alpha(ok, "d5"),
            "avg_d10_alpha_pct": _avg_alpha(ok, "d10"),
            "avg_d20_alpha_pct": _avg_alpha(ok, "d20"),
            "tickers": [record.get("ticker") for record in items],
            "records": [_record_result_brief(record) for record in items],
        }
    return comparison


def _markdown_report(today: str, summary: dict, records: list[dict]) -> str:
    lines = [
        "# SCOUT Performance Report",
        "",
        f"- date: {today}",
        f"- evaluated candidates: {summary.get('evaluated_count', 0)} / {summary.get('candidate_count', 0)}",
        f"- actually bought: {summary.get('actually_bought_count', 0)}",
        f"- avg D20 return: {summary.get('avg_d20_return_pct')}",
        f"- avg alpha: {summary.get('avg_alpha_pct', {})}",
        f"- positive alpha rate: {summary.get('positive_alpha_rate', {})}",
        f"- verdicts: {summary.get('verdict_counts', {})}",
        "- execution: first executable session open; no same-day close entry",
        "- benchmark: stored lane benchmark, with country fallback",
        "",
        "## Aggregates",
    ]
    for title, rows in (summary.get("aggregates") or {}).items():
        lines.append("")
        lines.append(f"### {title}")
        if not rows:
            lines.append("- no data")
            continue
        for row in rows[:8]:
            lines.append(
                f"- {row['key']}: n={row['count']}, avgD20={row['avg_d20_return_pct']}, "
                f"avgAlphaD20={row.get('avg_d20_alpha_pct')}, "
                f"winner={row['winner_rate']}, failed_fast={row['failed_fast_rate']}, bought={row['actually_bought_count']}"
            )
    comparison = summary.get("llm_override_comparison") or {}
    lines.append("")
    lines.append("## LLM Override Comparison")
    if not comparison or (not comparison.get("dropped") and not comparison.get("added")):
        lines.append("- no LLM override comparison rows")
    else:
        lines.append(
            f"- counts: dropped={comparison.get('dropped_count', 0)}, "
            f"added={comparison.get('added_count', 0)}, kept={comparison.get('kept_count', 0)}"
        )
        lines.append(
            f"- avg D5: dropped={comparison.get('avg_d5_return_pct', {}).get('dropped')}, "
            f"added={comparison.get('avg_d5_return_pct', {}).get('added')}, "
            f"kept={comparison.get('avg_d5_return_pct', {}).get('kept')}"
        )
        lines.append(
            f"- avg D20: dropped={comparison.get('avg_d20_return_pct', {}).get('dropped')}, "
            f"added={comparison.get('avg_d20_return_pct', {}).get('added')}, "
            f"kept={comparison.get('avg_d20_return_pct', {}).get('kept')}"
        )
        for label, key in [("Dropped by LLM", "dropped"), ("Added by LLM", "added")]:
            rows = comparison.get(key, []) or []
            lines.append("")
            lines.append(f"### {label}")
            if not rows:
                lines.append("- no data")
                continue
            for row in rows:
                lines.append(
                    f"- {row.get('snapshot_date')} {row.get('ticker')} {row.get('final_verdict')} "
                    f"D5={row.get('d5_return_pct')} D20={row.get('d20_return_pct')} "
                    f"MFE={row.get('mfe_pct')} MAE={row.get('mae_pct')} "
                    f"lane={row.get('primary_lane')}:{row.get('primary_lane_status')}"
                )
    lines.append("")
    lines.append("## Outcome Memory Comparison")
    memory_comparison = summary.get("outcome_memory_comparison") or {}
    lines.append(f"- evidence status: {memory_comparison.get('evidence_status', '')}")
    lines.append(f"- counterfactual proven: {memory_comparison.get('counterfactual_proven', False)}")
    lines.append(f"- winner declared: {memory_comparison.get('winner_declared', False)}")
    for effect, metrics in (memory_comparison.get("groups") or {}).items():
        lines.append(
            f"- {effect}: n={metrics.get('evaluated_count', 0)}/{metrics.get('count', 0)}, "
            f"alpha={metrics.get('avg_alpha_pct', {})}, "
            f"positiveAlpha={metrics.get('positive_alpha_rate', {})}"
        )
    lines.append("")
    lines.append("## Precision Shadow Comparison")
    shadow_comparison = summary.get("shadow_policy_comparison") or {}
    if not shadow_comparison:
        lines.append("- no precision shadow rows")
    else:
        for policy_id, policy in shadow_comparison.items():
            lines.append(
                f"- {policy_id}: n={policy.get('evaluated_count', 0)}/{policy.get('count', 0)}, "
                f"avgD5={policy.get('avg_d5_return_pct')}, avgD10={policy.get('avg_d10_return_pct')}, "
                f"avgD20={policy.get('avg_d20_return_pct')}, "
                f"alphaD20={policy.get('avg_d20_alpha_pct')}"
            )
    lines.append("")
    lines.append("## Support Resistance Engine Comparison")
    sr_comparison = summary.get("price_map_engine_comparison") or {}
    lines.append(f"- evidence status: {sr_comparison.get('evidence_status', '')}")
    lines.append(f"- winner declared: {sr_comparison.get('winner_declared', False)}")
    for engine_id, metrics in (sr_comparison.get("engines") or {}).items():
        lines.append(
            f"- {engine_id}: resolved={metrics.get('resolved_count', 0)}/{metrics.get('count', 0)}, "
            f"target={metrics.get('target_first', 0)}, stop={metrics.get('invalidation_first', 0)}, "
            f"late={metrics.get('target_already_passed', 0)}, avgR={metrics.get('avg_realized_r')}"
        )
    lines.append("")
    lines.append("## Policy Comparison")
    policy_comparison = summary.get("policy_comparison") or {}
    lines.append(f"- evidence status: {policy_comparison.get('evidence_status', '')}")
    lines.append(f"- winner declared: {policy_comparison.get('winner_declared', False)}")
    lines.append(f"- reason: {policy_comparison.get('reason', '')}")
    for cohort_id, metrics in (policy_comparison.get("cohorts") or {}).items():
        lines.append(
            f"- {cohort_id}: n={metrics.get('evaluated_count', 0)}/{metrics.get('count', 0)}, "
            f"alpha={metrics.get('avg_alpha_pct', {})}, "
            f"positiveAlpha={metrics.get('positive_alpha_rate', {})}"
        )
    lines.append("")
    lines.append("## Decision And Abstention Audit")
    decision_audit = summary.get("decision_audit") or {}
    lines.append(f"- snapshots: {decision_audit.get('snapshot_count', 0)}")
    lines.append(f"- abstentions: {decision_audit.get('abstention_status_counts', {})}")
    lines.append(
        f"- D20 selected nonpositive alpha: "
        f"{decision_audit.get('selected_d20_nonpositive_alpha_count', 0)}"
    )
    lines.append(
        f"- D20 rejected positive alpha: "
        f"{decision_audit.get('rejected_d20_positive_alpha_count', 0)}"
    )
    lines.append(
        f"- avg D20 opportunity cost: "
        f"{decision_audit.get('avg_d20_opportunity_cost_pct')}"
    )
    lines.append(
        f"- avg D20 ex-post upper-bound gap: "
        f"{decision_audit.get('avg_d20_ex_post_upper_bound_gap_pct')}"
    )
    lines.append("")
    lines.append("## Recent Candidate Records")
    for r in records:
        if r.get("bucket") != "candidate":
            continue
        d20 = (r.get("followup", {}).get("d20") or {}).get("return_pct")
        d20_alpha = (
            ((((r.get("benchmark") or {}).get("alpha") or {}).get("d20") or {}).get("alpha_pct"))
        )
        lines.append(
            f"- {r.get('snapshot_date')} {r.get('ticker')} {r.get('final_verdict')} "
            f"D20={d20} alphaD20={d20_alpha} "
            f"MFE={r.get('mfe_mae', {}).get('mfe_pct')} MAE={r.get('mfe_mae', {}).get('mae_pct')} "
            f"bought={r.get('actually_bought')} lane={r.get('primary_lane')} catalyst={r.get('catalyst_classification')}"
        )
    return "\n".join(lines) + "\n"


def _performance_summary_text(summary: dict) -> str:
    verdicts = summary.get("verdict_counts", {}) or {}
    failed_fast = int(verdicts.get("FAILED_FAST", 0) or 0)
    false_positive = int(verdicts.get("FALSE_POSITIVE", 0) or 0)
    failed_total = failed_fast + false_positive
    comparison = summary.get("llm_override_comparison", {}) or {}
    comparison_suffix = ""
    if comparison.get("dropped_count") or comparison.get("added_count"):
        comparison_suffix = (
            f" · LLM비교 dropped {int(comparison.get('dropped_count', 0) or 0)}"
            f"/added {int(comparison.get('added_count', 0) or 0)}"
        )
    d20_alpha = (summary.get("avg_alpha_pct") or {}).get("d20")
    alpha_text = f"D20 알파 {d20_alpha}" if d20_alpha is not None else "D20 알파 평가 대기"
    return (
        f"SCOUT 성과표: 후보 {summary.get('evaluated_count', 0)}/{summary.get('candidate_count', 0)}개 평가, "
        f"WINNER {int(verdicts.get('WINNER', 0) or 0)}, "
        f"실패 {failed_total} (조기 {failed_fast} / 20일 무진전 {false_positive}), "
        f"{alpha_text}, "
        f"실제매수 {summary.get('actually_bought_count', 0)}"
        f"{comparison_suffix}"
    )


def _build_ohlcv_cache(records: list[dict]) -> dict[str, Optional[pd.DataFrame]]:
    tickers_by_country: dict[str, list[str]] = defaultdict(list)
    seen = set()
    for record in records:
        country = str(record.get("country", "") or "US")
        for ticker in [record.get("ticker", ""), record.get("benchmark_ticker", "")]:
            ticker = str(ticker or "")
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            tickers_by_country[country].append(ticker)
    raw = fetch_ohlcv(
        {country: sorted(set(tickers)) for country, tickers in tickers_by_country.items()},
        lookback_days=400,
        use_cache=True,
    )
    return {ticker: _normalise_ohlcv(df) for ticker, df in raw.items()}


def run_scout_performance(
    days: int = 45,
    include_radar_top: bool = False,
    output_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """추천 스냅샷 기반 사후 성과표를 생성하고 파일로 저장한다."""
    today = today_kst_str()
    target_dir = Path(output_dir) if output_dir is not None else SCOUT_DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    snapshots = _load_snapshots(days)
    base_records = _build_records(days=days, include_radar_top=include_radar_top)
    if not base_records:
        summary_text = (
            "SCOUT 성과표: 추천 후보 없음"
            if snapshots
            else "SCOUT 성과표: 추천 스냅샷 없음"
        )
        return {
            "summary_text": summary_text,
            "records": [],
            "summary": {
                "snapshot_count": int(len(snapshots)),
                "candidate_count": 0,
                "evaluated_count": 0,
            },
            "paths": {},
        }

    evaluated = []
    ohlcv_cache = _build_ohlcv_cache(base_records)
    for record in base_records:
        evaluated.append(_evaluate_record(record, ohlcv_cache))

    summary = _summary(evaluated, snapshots=snapshots)
    payload = _json_safe({
        "date": today,
        "schema_version": "scout_performance_v0_6",
        "lookback_days": int(days),
        "followup_days": FOLLOWUP_DAYS,
        "evaluation_protocol": {
            "point_in_time": True,
            "entry_execution": "first_executable_session_open",
            "same_day_close_entry_allowed": False,
            "benchmark_relative": True,
            "regime_uses_pre_entry_benchmark_data_only": True,
            "policy_winner_auto_declared": False,
            "price_map_first_touch_horizon": 20,
            "price_map_same_bar_order": "ambiguous",
        },
        "summary": summary,
        "records": evaluated,
    })

    json_path = target_dir / f"scout_performance_{today}.json"
    md_path = target_dir / f"scout_performance_report_{today}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    md_path.write_text(_markdown_report(today, summary, evaluated), encoding="utf-8")

    parquet_path = target_dir / f"scout_performance_{today}.parquet"
    parquet_ok = False
    try:
        flat_rows = []
        for r in evaluated:
            row = {
                "date": today,
                "snapshot_date": r.get("snapshot_date"),
                "bucket": r.get("bucket"),
                "ticker": r.get("ticker"),
                "rank": r.get("rank"),
                "status": r.get("status"),
                "final_verdict": r.get("final_verdict"),
                "entry_price_used": r.get("entry_price_used"),
                "entry_date_used": r.get("entry_date_used"),
                "execution_timing_basis": (r.get("execution_policy") or {}).get("timing_basis"),
                "production_policy_id": r.get("production_policy_id"),
                "benchmark_ticker": (r.get("benchmark") or {}).get("ticker"),
                "market_regime": (
                    ((r.get("benchmark") or {}).get("market_regime") or {}).get("status")
                ),
                "selection_tier": r.get("selection_tier"),
                "selection_rank": r.get("selection_rank"),
                "rule_selection_rank": r.get("rule_selection_rank"),
                "selection_lane_rank": r.get("selection_lane_rank"),
                "selection_support_count": r.get("selection_support_count"),
                "llm_selected": r.get("llm_selected"),
                "llm_override": r.get("llm_override"),
                "llm_dropped": r.get("llm_dropped"),
                "outcome_memory_effect": r.get("outcome_memory_effect"),
                "outcome_memory_evidence_refs": ",".join(
                    r.get("outcome_memory_evidence_refs", []) or []
                ),
                "opportunity_score": r.get("opportunity_score"),
                "drawdown_from_high": r.get("drawdown_from_high"),
                "factor_ret_20d": r.get("factor_ret_20d"),
                "factor_atr_pct": r.get("factor_atr_pct"),
                "liquidity_buffer_multiple": r.get("liquidity_buffer_multiple"),
                "avg_traded_value_20d": r.get("avg_traded_value_20d"),
                "d1_return_pct": (r.get("followup", {}).get("d1") or {}).get("return_pct"),
                "d3_return_pct": (r.get("followup", {}).get("d3") or {}).get("return_pct"),
                "d5_return_pct": (r.get("followup", {}).get("d5") or {}).get("return_pct"),
                "d10_return_pct": (r.get("followup", {}).get("d10") or {}).get("return_pct"),
                "d20_return_pct": (r.get("followup", {}).get("d20") or {}).get("return_pct"),
                "d5_alpha_pct": (
                    (((r.get("benchmark") or {}).get("alpha") or {}).get("d5") or {}).get("alpha_pct")
                ),
                "d10_alpha_pct": (
                    (((r.get("benchmark") or {}).get("alpha") or {}).get("d10") or {}).get("alpha_pct")
                ),
                "d20_alpha_pct": (
                    (((r.get("benchmark") or {}).get("alpha") or {}).get("d20") or {}).get("alpha_pct")
                ),
                "mfe_pct": (r.get("mfe_mae") or {}).get("mfe_pct"),
                "mae_pct": (r.get("mfe_mae") or {}).get("mae_pct"),
                "higher_low": (r.get("structure_events") or {}).get("higher_low"),
                "higher_high": (r.get("structure_events") or {}).get("higher_high"),
                "ma50_recover": (r.get("structure_events") or {}).get("ma50_recover"),
                "volume_breakout": (r.get("structure_events") or {}).get("volume_breakout"),
                "primary_lane": r.get("primary_lane"),
                "primary_lane_status": r.get("primary_lane_status"),
                "theme_industry_status": r.get("theme_industry_status"),
                "sector_rrg_quadrant": r.get("sector_rrg_quadrant"),
                "theme_keys": ",".join(r.get("theme_keys", []) or []),
                "quality_auditor_status": r.get("quality_auditor_status"),
                "catalyst_classification": r.get("catalyst_classification"),
                "catalyst_event_types": ",".join(r.get("catalyst_event_types", []) or []),
                "catalyst_has_upcoming": r.get("catalyst_has_upcoming"),
                "actually_bought": r.get("actually_bought"),
                "currently_open": r.get("currently_open"),
                "position_id": r.get("position_id"),
            }
            flat_rows.append(row)
        pd.DataFrame(flat_rows).to_parquet(parquet_path, index=False)
        parquet_ok = True
    except Exception as e:
        logger.debug("[scout performance] parquet 저장 실패(json/md는 저장됨): %s", e)

    summary_text = _performance_summary_text(summary)
    return {
        "summary_text": summary_text,
        "records": evaluated,
        "summary": summary,
        "paths": {
            "json": str(json_path),
            "markdown": str(md_path),
            "parquet": str(parquet_path) if parquet_ok else "",
        },
    }
