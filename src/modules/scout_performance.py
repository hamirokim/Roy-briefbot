"""SCOUT recommendation performance ledger.

추천 스냅샷을 원장으로 삼아 후보 자체의 사후 반응을 추적한다.
실제 매수 여부는 별도 필드로 분리하고, 성과 판단에는 포함하지 않는다.
"""

from __future__ import annotations

import json
import logging
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.collectors.global_ohlcv import fetch_daily_ohlcv_yf
from src.utils import now_kst, today_kst_str

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
SCOUT_DATA_DIR = BASE_DIR / "data" / "scout"

FOLLOWUP_DAYS = [1, 3, 5, 10, 20]

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


def _extract_record(snapshot_date: str, bucket: str, rank: int, item: dict, historical_pos: dict, open_pos: dict) -> dict:
    ticker = _ticker_key(item.get("ticker", ""))
    primary_lane, primary_lane_status = _primary_lane_from_item(item)
    catalyst = item.get("catalyst_context") or {}
    top3 = item.get("top3_selection") or {}
    price_lanes = item.get("price_lanes") or {}
    primary_lane_data = price_lanes.get(primary_lane) or {}
    primary_lane_metrics = primary_lane_data.get("metrics") or {}
    factor_context = item.get("factor_context") or {}
    factor_metrics = factor_context.get("metrics") or {}
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
    return {
        "snapshot_date": snapshot_date,
        "bucket": bucket,
        "rank": int(rank),
        "ticker": ticker,
        "name": item.get("name", ""),
        "country": item.get("country", ""),
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
        "opportunity_score": opportunity_score,
        "drawdown_from_high": drawdown_from_high,
        "factor_ret_20d": _metric_from(factor_metrics, key="ret_20d", default=None),
        "factor_atr_pct": _metric_from(factor_metrics, key="atr_pct", default=None),
        "factor_positives": _safe_list(factor_context.get("positives", [])),
        "factor_negatives": _safe_list(factor_context.get("negatives", [])),
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
        "quality_auditor_status": _nested_status(item, "quality_auditor_status", "quality_auditor"),
        "catalyst_classification": str(item.get("catalyst_classification") or catalyst.get("classification", "") or ""),
        "catalyst_freshness": str(item.get("catalyst_freshness") or ((catalyst.get("freshness") or {}).get("status", "")) or ""),
        "actually_bought": ticker in historical_pos,
        "currently_open": ticker in open_pos,
        "position_id": historical_pos.get(ticker, ""),
        "lane_key": lane,
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
                base_records.append(_extract_record(snap_date, bucket, rank, item, historical_pos, open_pos))
    return base_records


def _evaluate_record(record: dict, ohlcv_cache: dict[str, Optional[pd.DataFrame]]) -> dict:
    ticker = record.get("ticker", "")
    if ticker not in ohlcv_cache:
        ohlcv_cache[ticker] = _normalise_ohlcv(fetch_daily_ohlcv_yf(ticker, lookback=120))
    df = ohlcv_cache.get(ticker)
    if df is None:
        return {**record, "status": "NO_PRICE_DATA", "final_verdict": "PENDING"}

    start_idx = _first_trade_index(df, record.get("snapshot_date", ""))
    if start_idx is None:
        return {**record, "status": "NO_START_BAR", "final_verdict": "PENDING"}

    entry_price = float(df["Close"].iloc[start_idx])
    followups, available_day = _followup_returns(df, start_idx, entry_price)
    mfe_mae = _mfe_mae(df, start_idx, entry_price, horizon=20)
    structure = _structure_events(df, start_idx, horizon=20)
    verdict = _verdict(followups, mfe_mae, structure, available_day)
    return _json_safe({
        **record,
        "status": "OK",
        "entry_date_used": pd.to_datetime(df["Date"].iloc[start_idx]).strftime("%Y-%m-%d"),
        "entry_price_used": round(entry_price, 4),
        "available_trading_days": int(available_day),
        "followup": followups,
        "mfe_mae": mfe_mae,
        "structure_events": structure,
        "final_verdict": verdict,
    })


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
            "winner_rate": round(winners / len(items), 3) if items else 0,
            "failed_fast_rate": round(failed_fast / len(items), 3) if items else 0,
            "actually_bought_count": int(bought),
        })
    rows.sort(key=lambda r: (-int(r["count"]), -(r["avg_d20_return_pct"] or -999)))
    return rows


def _summary(records: list[dict]) -> dict:
    candidates = [r for r in records if r.get("bucket") == "candidate"]
    ok = [r for r in candidates if r.get("status") == "OK"]
    verdicts = Counter(str(r.get("final_verdict", "")) for r in ok)
    bought = [r for r in ok if r.get("actually_bought")]
    d20 = [_safe_float((r.get("followup", {}).get("d20") or {}).get("return_pct")) for r in ok]
    d20_clean = [v for v in d20 if v is not None]
    return {
        "candidate_count": len(candidates),
        "evaluated_count": len(ok),
        "actually_bought_count": len(bought),
        "verdict_counts": dict(verdicts),
        "avg_d20_return_pct": round(sum(d20_clean) / len(d20_clean), 2) if d20_clean else None,
        "aggregates": {
            "by_lane": _aggregate(records, "lane"),
            "by_lane_status": _aggregate(records, "lane_status"),
            "by_theme_industry": _aggregate(records, "theme"),
            "by_quality_auditor": _aggregate(records, "quality"),
            "by_catalyst": _aggregate(records, "catalyst"),
        },
        "llm_override_comparison": _llm_override_comparison(records),
        "shadow_policy_comparison": _shadow_policy_comparison(records),
    }


def _record_result_brief(record: dict) -> dict:
    followup = record.get("followup") or {}
    mfe_mae = record.get("mfe_mae") or {}
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
        f"- verdicts: {summary.get('verdict_counts', {})}",
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
    lines.append("## Precision Shadow Comparison")
    shadow_comparison = summary.get("shadow_policy_comparison") or {}
    if not shadow_comparison:
        lines.append("- no precision shadow rows")
    else:
        for policy_id, policy in shadow_comparison.items():
            lines.append(
                f"- {policy_id}: n={policy.get('evaluated_count', 0)}/{policy.get('count', 0)}, "
                f"avgD5={policy.get('avg_d5_return_pct')}, avgD10={policy.get('avg_d10_return_pct')}, "
                f"avgD20={policy.get('avg_d20_return_pct')}"
            )
    lines.append("")
    lines.append("## Recent Candidate Records")
    for r in records:
        if r.get("bucket") != "candidate":
            continue
        d20 = (r.get("followup", {}).get("d20") or {}).get("return_pct")
        lines.append(
            f"- {r.get('snapshot_date')} {r.get('ticker')} {r.get('final_verdict')} "
            f"D20={d20} MFE={r.get('mfe_mae', {}).get('mfe_pct')} MAE={r.get('mfe_mae', {}).get('mae_pct')} "
            f"bought={r.get('actually_bought')} lane={r.get('primary_lane')} catalyst={r.get('catalyst_classification')}"
        )
    return "\n".join(lines) + "\n"


def run_scout_performance(days: int = 45, include_radar_top: bool = False) -> dict[str, Any]:
    """추천 스냅샷 기반 사후 성과표를 생성하고 파일로 저장한다."""
    today = today_kst_str()
    SCOUT_DATA_DIR.mkdir(parents=True, exist_ok=True)
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
    ohlcv_cache: dict[str, Optional[pd.DataFrame]] = {}
    for record in base_records:
        evaluated.append(_evaluate_record(record, ohlcv_cache))

    summary = _summary(evaluated)
    payload = _json_safe({
        "date": today,
        "schema_version": "scout_performance_v0_3",
        "lookback_days": int(days),
        "followup_days": FOLLOWUP_DAYS,
        "summary": summary,
        "records": evaluated,
    })

    json_path = SCOUT_DATA_DIR / f"scout_performance_{today}.json"
    md_path = SCOUT_DATA_DIR / f"scout_performance_report_{today}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    md_path.write_text(_markdown_report(today, summary, evaluated), encoding="utf-8")

    parquet_path = SCOUT_DATA_DIR / f"scout_performance_{today}.parquet"
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
                "selection_tier": r.get("selection_tier"),
                "selection_rank": r.get("selection_rank"),
                "rule_selection_rank": r.get("rule_selection_rank"),
                "selection_lane_rank": r.get("selection_lane_rank"),
                "selection_support_count": r.get("selection_support_count"),
                "llm_selected": r.get("llm_selected"),
                "llm_override": r.get("llm_override"),
                "llm_dropped": r.get("llm_dropped"),
                "opportunity_score": r.get("opportunity_score"),
                "drawdown_from_high": r.get("drawdown_from_high"),
                "factor_ret_20d": r.get("factor_ret_20d"),
                "factor_atr_pct": r.get("factor_atr_pct"),
                "d1_return_pct": (r.get("followup", {}).get("d1") or {}).get("return_pct"),
                "d3_return_pct": (r.get("followup", {}).get("d3") or {}).get("return_pct"),
                "d5_return_pct": (r.get("followup", {}).get("d5") or {}).get("return_pct"),
                "d10_return_pct": (r.get("followup", {}).get("d10") or {}).get("return_pct"),
                "d20_return_pct": (r.get("followup", {}).get("d20") or {}).get("return_pct"),
                "mfe_pct": (r.get("mfe_mae") or {}).get("mfe_pct"),
                "mae_pct": (r.get("mfe_mae") or {}).get("mae_pct"),
                "higher_low": (r.get("structure_events") or {}).get("higher_low"),
                "higher_high": (r.get("structure_events") or {}).get("higher_high"),
                "ma50_recover": (r.get("structure_events") or {}).get("ma50_recover"),
                "volume_breakout": (r.get("structure_events") or {}).get("volume_breakout"),
                "primary_lane": r.get("primary_lane"),
                "primary_lane_status": r.get("primary_lane_status"),
                "theme_industry_status": r.get("theme_industry_status"),
                "quality_auditor_status": r.get("quality_auditor_status"),
                "catalyst_classification": r.get("catalyst_classification"),
                "actually_bought": r.get("actually_bought"),
                "currently_open": r.get("currently_open"),
                "position_id": r.get("position_id"),
            }
            flat_rows.append(row)
        pd.DataFrame(flat_rows).to_parquet(parquet_path, index=False)
        parquet_ok = True
    except Exception as e:
        logger.debug("[scout performance] parquet 저장 실패(json/md는 저장됨): %s", e)

    verdicts = summary.get("verdict_counts", {}) or {}
    comparison = summary.get("llm_override_comparison", {}) or {}
    comparison_suffix = ""
    if comparison.get("dropped_count") or comparison.get("added_count"):
        comparison_suffix = (
            f" · LLM비교 dropped {int(comparison.get('dropped_count', 0) or 0)}"
            f"/added {int(comparison.get('added_count', 0) or 0)}"
        )
    summary_text = (
        f"SCOUT 성과표: 후보 {summary.get('evaluated_count', 0)}/{summary.get('candidate_count', 0)}개 평가, "
        f"WINNER {int(verdicts.get('WINNER', 0) or 0)}, "
        f"FAILED_FAST {int(verdicts.get('FAILED_FAST', 0) or 0)}, "
        f"FALSE_POSITIVE {int(verdicts.get('FALSE_POSITIVE', 0) or 0)}, "
        f"실제매수 {summary.get('actually_bought_count', 0)}"
        f"{comparison_suffix}"
    )
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
