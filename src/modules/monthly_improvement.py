"""
Monthly Improvement Report — 운영/데이터수집/개선 루프.

월간 브리핑 때 SCOUT 후보 성과와 shadow 실험 레이어를 자동 점검한다.
원칙: 표본이 부족하면 승격/제거를 확정하지 않고, 다음 달 검증 과제로 남긴다.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.utils import now_kst

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
SCOUT_DATA_DIR = BASE_DIR / "data" / "scout"

REPORT_DAYS = 35
MIN_DAYS_FOR_DECISION = 7
MIN_SAMPLE_FOR_DECISION = 5
TARGET_DAILY_PICKS = 3.0


def _parse_date(value: str):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except Exception:
        return default


def _pct(value: float) -> str:
    return f"{value:+.1f}%"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _recent_results(m6_out: dict, days: int = REPORT_DAYS) -> list[dict]:
    today = now_kst().date()
    cutoff = today - timedelta(days=days)
    results = []
    for item in (m6_out or {}).get("results", []) or []:
        added = _parse_date(item.get("date_added", ""))
        if added and added >= cutoff:
            results.append(item)
    return results


def _days_since_added(item: dict) -> int:
    added = _parse_date(item.get("date_added", ""))
    if added:
        return (now_kst().date() - added).days
    return int(_safe_float(item.get("days_held"), 0))


def _mature_results(results: list[dict], min_days: int = MIN_DAYS_FOR_DECISION) -> list[dict]:
    """성과 판단용 표본. 너무 최근 후보는 기록만 하고 판단에서 제외."""
    return [r for r in results if _days_since_added(r) >= min_days]


def _summarize_performance(results: list[dict]) -> dict:
    if not results:
        return {"count": 0, "avg": 0.0, "win_rate": 0.0, "best": None, "worst": None}
    pnls = [_safe_float(r.get("pnl_pct")) for r in results]
    winners = sum(1 for p in pnls if p > 0)
    return {
        "count": len(results),
        "avg": _mean(pnls),
        "win_rate": winners / len(results),
        "best": max(results, key=lambda r: _safe_float(r.get("pnl_pct"))),
        "worst": min(results, key=lambda r: _safe_float(r.get("pnl_pct"))),
    }


def _aggregate_by_list_field(results: list[dict], field: str, min_count: int = 2) -> list[dict]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for r in results:
        for key in r.get(field, []) or []:
            buckets[str(key)].append(_safe_float(r.get("pnl_pct")))

    rows = []
    for key, values in buckets.items():
        if len(values) < min_count:
            continue
        wins = sum(1 for v in values if v > 0)
        rows.append({
            "key": key,
            "count": len(values),
            "avg": _mean(values),
            "win_rate": wins / len(values),
        })
    rows.sort(key=lambda r: (-r["count"], -r["avg"]))
    return rows


def _load_recent_radar_summaries(days: int = REPORT_DAYS) -> list[dict]:
    today = now_kst().date()
    cutoff = today - timedelta(days=days)
    out = []
    if not SCOUT_DATA_DIR.exists():
        return out

    for path in sorted(SCOUT_DATA_DIR.glob("radar_pool_*.json")):
        date_part = path.stem.replace("radar_pool_", "")
        d = _parse_date(date_part)
        if not d or d < cutoff:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            summary = payload.get("summary", {}) or {}
            items = payload.get("items", []) or []
            out.append({"date": date_part, "summary": summary, "items": items})
        except Exception as e:
            logger.debug("[monthly improvement] radar json read 실패 %s: %s", path, e)
    return out


def _summarize_radar(snapshots: list[dict]) -> dict:
    if not snapshots:
        return {
            "days": 0,
            "avg_scanned": 0,
            "avg_ohlcv": 0,
            "avg_radar": 0,
            "avg_picks": 0,
            "top_signals": [],
            "top_shadow": [],
            "top_quality": [],
        }

    scanned = []
    ohlcv = []
    radar = []
    picks = []
    signal_counter = Counter()
    shadow_counter = Counter()
    quality_counter = Counter()

    for snap in snapshots:
        s = snap.get("summary", {}) or {}
        scanned.append(_safe_float(s.get("scanned_total")))
        ohlcv.append(_safe_float(s.get("ohlcv_evaluated")))
        radar.append(_safe_float(s.get("radar_pool_count")))
        picks.append(_safe_float(s.get("brief_pick_count")))

        for key, count in s.get("top_signals", []) or []:
            signal_counter[str(key)] += int(count or 0)
        audit = (s.get("filter_audit", {}) or {}).get("signal_audit", {}) or {}
        for key, count in (audit.get("shadow_hit_counts", {}) or {}).items():
            shadow_counter[str(key)] += int(count or 0)
        for key, count in s.get("top_quality_flags", []) or []:
            quality_counter[str(key)] += int(count or 0)

    return {
        "days": len(snapshots),
        "avg_scanned": _mean(scanned),
        "avg_ohlcv": _mean(ohlcv),
        "avg_radar": _mean(radar),
        "avg_picks": _mean(picks),
        "top_signals": signal_counter.most_common(5),
        "top_shadow": shadow_counter.most_common(5),
        "top_quality": quality_counter.most_common(5),
    }


def _decision_for_bucket(row: dict, label: str) -> str:
    count = int(row.get("count", 0) or 0)
    avg = float(row.get("avg", 0) or 0)
    win_rate = float(row.get("win_rate", 0) or 0)
    if count < MIN_SAMPLE_FOR_DECISION:
        return f"{label}: 표본 {count}개라 판단 보류"
    if avg >= 1.0 and win_rate >= 0.55:
        return f"{label}: 성과 우위 후보, 다음 달 가중치 상향 검토"
    if avg <= -1.0 and win_rate <= 0.40:
        return f"{label}: 성과 열위 후보, 다음 달 감점/제거 검토"
    return f"{label}: 뚜렷한 우위 없음, 현상 유지"


def build_monthly_improvement_report(state: dict, scout_out: dict, m6_out: dict) -> dict[str, Any]:
    """월간 개선 리포트 생성.

    반환값:
      summary_text: 텔레그램용 압축 결론
      detailed_lines: BRIEFING 시트용 상세
      metrics: 기계 판독용 숫자
    """
    all_results = _recent_results(m6_out, REPORT_DAYS)
    results = _mature_results(all_results, MIN_DAYS_FOR_DECISION)
    immature_count = max(0, len(all_results) - len(results))
    perf = _summarize_performance(results)
    signal_rows = _aggregate_by_list_field(results, "signal_keys")
    shadow_rows = _aggregate_by_list_field(results, "shadow_signal_keys", min_count=1)
    factor_pos_rows = _aggregate_by_list_field(results, "factor_positives", min_count=1)
    factor_neg_rows = _aggregate_by_list_field(results, "factor_negatives", min_count=1)
    quality_rows = _aggregate_by_list_field(results, "quality_flags", min_count=1)

    radar_summary = _summarize_radar(_load_recent_radar_summaries(REPORT_DAYS))

    actions = []
    if perf["count"] < MIN_SAMPLE_FOR_DECISION:
        actions.append(
            f"판단 표본 {perf['count']}개: 이번 달은 승격/제거보다 데이터 축적 우선"
        )
    else:
        if perf["avg"] > 0 and perf["win_rate"] >= 0.5:
            actions.append("SCOUT 기본 후보선정은 유지: 월간 평균과 승률이 최소 기준을 통과")
        else:
            actions.append("SCOUT 기본 후보선정 재점검: 평균 성과 또는 승률이 약함")

    if radar_summary["days"]:
        avg_picks = radar_summary["avg_picks"]
        if avg_picks >= 4.5:
            actions.append("Top5가 거의 매번 꽉 참: 자리 채우기 가능성 점검 필요")
        elif avg_picks <= 1.0:
            actions.append("후보가 너무 적음: 필터가 과하게 좁은지 점검 필요")
        else:
            actions.append("후보 수는 적정권: 너무 많지도 적지도 않음")

    if signal_rows:
        actions.append(_decision_for_bucket(signal_rows[0], f"핵심 신호 {signal_rows[0]['key']}"))
    if shadow_rows:
        actions.append(_decision_for_bucket(shadow_rows[0], f"Shadow 신호 {shadow_rows[0]['key']}"))
    else:
        actions.append("Shadow 신호: 아직 후보 성과와 연결된 표본 없음")

    lines = ["▣ 월간 개선 리포트", ""]
    lines.append(
        f"  • 표본 기준: 최근 {REPORT_DAYS}일 후보 {len(all_results)}개 중 "
        f"{MIN_DAYS_FOR_DECISION}일 이상 지난 {perf['count']}개만 성과 판단"
    )
    if immature_count:
        lines.append(f"    참고: 최근 후보 {immature_count}개는 기록만 하고 판단에서 제외")
    if perf["count"]:
        best = perf.get("best") or {}
        worst = perf.get("worst") or {}
        lines.append(
            f"  • 판단 표본 성과: {perf['count']}개 / 평균 {_pct(perf['avg'])} / "
            f"상승 {perf['win_rate'] * 100:.0f}%"
        )
        if best:
            lines.append(f"    최고: {best.get('ticker')} {_pct(_safe_float(best.get('pnl_pct')))}")
        if worst:
            lines.append(f"    최저: {worst.get('ticker')} {_pct(_safe_float(worst.get('pnl_pct')))}")
    else:
        lines.append("  • 판단 표본 성과: 아직 월간 판단 표본 없음")

    if radar_summary["days"]:
        lines.append(
            f"  • 운영량: {radar_summary['days']}일 기록 / "
            f"평균 스캔 {radar_summary['avg_scanned']:.0f}개 / "
            f"시세평가 {radar_summary['avg_ohlcv']:.0f}개 / "
            f"엄선 {radar_summary['avg_picks']:.1f}개"
        )

    if signal_rows:
        lines.append("")
        lines.append("  • 신호별 성과:")
        for row in signal_rows[:5]:
            lines.append(
                f"    - {row['key']}: {row['count']}개 / 평균 {_pct(row['avg'])} / "
                f"상승 {row['win_rate'] * 100:.0f}%"
            )

    if shadow_rows or factor_pos_rows or factor_neg_rows:
        lines.append("")
        lines.append("  • 실험 레이어:")
        for row in shadow_rows[:3]:
            lines.append(
                f"    - Shadow {row['key']}: {row['count']}개 / 평균 {_pct(row['avg'])} / "
                f"상승 {row['win_rate'] * 100:.0f}%"
            )
        for row in factor_pos_rows[:2]:
            lines.append(
                f"    - 因子+ {row['key']}: {row['count']}개 / 평균 {_pct(row['avg'])}"
            )
        for row in factor_neg_rows[:2]:
            lines.append(
                f"    - 因子- {row['key']}: {row['count']}개 / 평균 {_pct(row['avg'])}"
            )

    if quality_rows:
        lines.append("")
        lines.append("  • 자주 붙은 관찰 태그:")
        for row in quality_rows[:4]:
            lines.append(f"    - {row['key']}: {row['count']}개 / 평균 {_pct(row['avg'])}")

    lines.append("")
    lines.append("  • 다음 달 액션:")
    for idx, action in enumerate(actions[:5], 1):
        lines.append(f"    {idx}. {action}")

    if perf["count"]:
        summary = (
            f"월간 개선: 판단 표본 {perf['count']}/{len(all_results)}개 평균 {_pct(perf['avg'])}, "
            f"상승 {perf['win_rate'] * 100:.0f}%. "
            f"다음 액션: {actions[0] if actions else '표본 축적'}"
        )
    else:
        summary = (
            f"월간 개선: 최근 후보 {len(all_results)}개 중 "
            f"{MIN_DAYS_FOR_DECISION}일 이상 지난 판단 표본이 부족. "
            "이번 달은 shadow 검증 데이터 축적이 우선."
        )

    return {
        "summary_text": summary,
        "detailed_lines": lines,
        "metrics": {
            "performance": perf,
            "total_tracked": len(all_results),
            "immature_count": immature_count,
            "min_days_for_decision": MIN_DAYS_FOR_DECISION,
            "radar": radar_summary,
            "signals": signal_rows,
            "shadow": shadow_rows,
            "factor_positive": factor_pos_rows,
            "factor_negative": factor_neg_rows,
            "quality": quality_rows,
        },
        "actions": actions,
    }
