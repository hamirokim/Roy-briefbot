"""M2 섹터 로테이션 맵.

RRG(Relative Rotation Graph) 방식으로 섹터/국가 ETF를 4분면 분류.
- RS-Ratio: 벤치마크 대비 상대 수준 (100 기준)
- RS-Momentum: RS-Ratio의 변화 속도 (100 기준)
- 4분면: LEADING / WEAKENING / LAGGING / IMPROVING
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from src.collectors.stooq import fetch_daily_closes
from src.utils import env_int, today_kst_str

# ── 분면 정의 ──
QUADRANTS = {
    "LEADING":   {"emoji": "🟢", "label": "강세 지속"},
    "WEAKENING": {"emoji": "🟡", "label": "약세 전환 ⚠️"},
    "LAGGING":   {"emoji": "🔴", "label": "약세 지속"},
    "IMPROVING": {"emoji": "⚡", "label": "회복 초기 ⚡ 주목"},
}


# ─────────────────────────────────────────────
# 계산 함수
# ─────────────────────────────────────────────

def compute_rs(
    etf_closes: pd.Series,
    bench_closes: pd.Series,
    ratio_period: int = 63,
    mom_period: int = 10,
) -> Optional[dict]:
    """RS-Ratio, RS-Momentum 계산."""
    if len(etf_closes) < ratio_period + mom_period + 5:
        return None
    if len(bench_closes) < ratio_period + mom_period + 5:
        return None

    # 1. Relative Performance (누적 비율)
    rp = etf_closes / bench_closes

    # 2. RS-Ratio = (RP / SMA(RP, ratio_period)) * 100
    rp_sma = rp.rolling(window=ratio_period).mean()
    rs_ratio = (rp / rp_sma) * 100

    # 3. RS-Momentum = (RS-Ratio / SMA(RS-Ratio, mom_period)) * 100
    rs_ratio_sma = rs_ratio.rolling(window=mom_period).mean()
    rs_momentum = (rs_ratio / rs_ratio_sma) * 100

    # 최신 값
    latest_ratio = rs_ratio.iloc[-1]
    latest_momentum = rs_momentum.iloc[-1]

    if np.isnan(latest_ratio) or np.isnan(latest_momentum):
        return None

    return {
        "ratio": round(float(latest_ratio), 2),
        "momentum": round(float(latest_momentum), 2),
    }


def classify_quadrant(ratio: float, momentum: float) -> str:
    """RS-Ratio x RS-Momentum -> 4분면 분류."""
    if ratio > 100 and momentum > 100:
        return "LEADING"
    elif ratio > 100 and momentum <= 100:
        return "WEAKENING"
    elif ratio <= 100 and momentum <= 100:
        return "LAGGING"
    else:  # ratio <= 100 and momentum > 100
        return "IMPROVING"


def detect_transition(
    ticker: str,
    today_quad: str,
    yesterday_data: Optional[dict],
) -> Optional[str]:
    """분면 전환 감지. 전환 있으면 문자열, 없으면 None."""
    if yesterday_data is None:
        return None
    prev_quad = yesterday_data.get("quadrant", "")
    if prev_quad and prev_quad != today_quad:
        return f"{prev_quad}->{today_quad}"
    return None


# ─────────────────────────────────────────────
# 체류 일수 계산
# ─────────────────────────────────────────────

def count_quadrant_days(
    ticker: str,
    current_quad: str,
    history: dict[str, dict],
) -> int:
    """현재 분면에 연속 체류한 일수. 최소 1 (오늘 포함)."""
    days = 1
    sorted_dates = sorted(history.keys(), reverse=True)
    for date_str in sorted_dates:
        day_data = history[date_str]
        ticker_data = day_data.get(ticker)
        if ticker_data is None:
            break
        if ticker_data.get("quadrant") != current_quad:
            break
        days += 1
    return days


# ─────────────────────────────────────────────
# M2 메인 실행
# ─────────────────────────────────────────────

def run_m2(etf_map: dict, state: dict) -> dict:
    """M2 모듈 실행."""
    ratio_period = env_int("RS_RATIO_PERIOD", 63)
    mom_period = env_int("RS_MOM_PERIOD", 10)
    lookback = ratio_period + mom_period + 30

    # 벤치마크 수집
    bench_cfg = etf_map["benchmark"]
    bench_df = fetch_daily_closes(bench_cfg["stooq"], lookback=lookback)
    if bench_df is None:
        return _error_result("벤치마크(ACWI) 데이터 수집 실패")

    # 히스토리
    m2_history = state.get("m2_history", {})
    sorted_dates = sorted(m2_history.keys(), reverse=True)
    yesterday_snapshot = m2_history[sorted_dates[0]] if sorted_dates else {}

    today_str = today_kst_str()
    today_snapshot: dict[str, dict] = {}
    transitions: list[dict] = []

    # 섹터 + 국가 합쳐서 처리
    all_groups = [
        ("섹터", etf_map.get("sectors", {})),
        ("국가/지역", etf_map.get("countries", {})),
    ]

    for group_name, group_map in all_groups:
        for ticker, cfg in group_map.items():
            etf_df = fetch_daily_closes(cfg["stooq"], lookback=lookback)
            if etf_df is None:
                print(f"[WARN] {ticker} 수집 실패, 건너뜀")
                continue

            # 날짜 정렬 맞추기: 벤치마크와 ETF의 공통 날짜만 사용
            merged = pd.merge(
                bench_df.rename(columns={"Close": "bench"}),
                etf_df.rename(columns={"Close": "etf"}),
                on="Date",
                how="inner",
            ).sort_values("Date").reset_index(drop=True)

            if len(merged) < ratio_period + mom_period + 5:
                print(f"[WARN] {ticker} 공통 데이터 부족 ({len(merged)}행), 건너뜀")
                continue

            rs = compute_rs(
                merged["etf"],
                merged["bench"],
                ratio_period=ratio_period,
                mom_period=mom_period,
            )
            if rs is None:
                continue

            quadrant = classify_quadrant(rs["ratio"], rs["momentum"])
            transition = detect_transition(ticker, quadrant, yesterday_snapshot.get(ticker))
            quad_days = count_quadrant_days(ticker, quadrant, m2_history)

            today_snapshot[ticker] = {
                "ratio": rs["ratio"],
                "momentum": rs["momentum"],
                "quadrant": quadrant,
                "group": group_name,
                "label": cfg["label"],
            }

            if transition:
                transitions.append({
                    "ticker": ticker,
                    "label": cfg["label"],
                    "transition": transition,
                    "ratio": rs["ratio"],
                    "momentum": rs["momentum"],
                    "group": group_name,
                })

    # 출력 생성
    context_text = _build_context(today_snapshot, transitions, m2_history, today_str)
    telegram_text = _build_telegram(today_snapshot, transitions, m2_history, today_str)

    return {
        "context_text": context_text,
        "telegram_text": telegram_text,
        "today_snapshot": today_snapshot,
        "transitions": transitions,
    }


# ─────────────────────────────────────────────
# 출력 빌더
# ─────────────────────────────────────────────

def _build_context(
    snapshot: dict,
    transitions: list,
    history: dict,
    date_str: str,
) -> str:
    """LLM 컨텍스트용 텍스트 생성."""
    lines = [f"## SECTOR ROTATION (vs ACWI, {date_str})", ""]

    for quad_key in ["LEADING", "IMPROVING", "WEAKENING", "LAGGING"]:
        q = QUADRANTS[quad_key]
        items = [
            (t, d) for t, d in snapshot.items()
            if d["quadrant"] == quad_key
        ]
        if not items:
            continue

        lines.append(f"[{quad_key} -- {q['label']}]")
        for ticker, data in sorted(items, key=lambda x: x[1]["ratio"], reverse=True):
            days = count_quadrant_days(ticker, quad_key, history)
            trans = _find_transition(ticker, transitions)
            trans_str = f" / {trans} 전환" if trans else ""
            lines.append(
                f"* {ticker}({data['label']}): "
                f"Ratio {data['ratio']:.1f} / Mom {data['momentum']:.1f} / "
                f"{quad_key} {days}일째{trans_str}"
            )
        lines.append("")

    return "\n".join(lines)


def _build_telegram(
    snapshot: dict,
    transitions: list,
    history: dict,
    date_str: str,
) -> str:
    """텔레그램 직접 출력 (M1 합류 전 임시)."""
    lines = [f"<b>📊 섹터 로테이션 맵</b>  ({date_str})", ""]

    # 전환 이벤트 먼저 (있으면)
    if transitions:
        lines.append("<b>🔄 분면 전환</b>")
        for t in transitions:
            target_quad = t["transition"].split("->")[-1]
            emoji = QUADRANTS.get(target_quad, {}).get("emoji", "")
            lines.append(
                f"  {emoji} <b>{t['ticker']}</b> ({t['label']}): "
                f"{t['transition']}  "
                f"[R:{t['ratio']:.1f} M:{t['momentum']:.1f}]"
            )
        lines.append("")

    # 분면별 리스트
    for group_name in ["섹터", "국가/지역"]:
        group_items = {t: d for t, d in snapshot.items() if d["group"] == group_name}
        if not group_items:
            continue

        lines.append(f"<b>{'🏭' if group_name == '섹터' else '🌍'} {group_name}</b>")
        for quad_key in ["LEADING", "IMPROVING", "WEAKENING", "LAGGING"]:
            q = QUADRANTS[quad_key]
            items = [
                (t, d) for t, d in group_items.items()
                if d["quadrant"] == quad_key
            ]
            if not items:
                continue
            tickers_str = ", ".join(
                f"{t}({d['ratio']:.0f}/{d['momentum']:.0f})"
                for t, d in sorted(items, key=lambda x: x[1]["ratio"], reverse=True)
            )
            lines.append(f"  {q['emoji']} {quad_key}: {tickers_str}")
        lines.append("")

    # 요약 한 줄
    improving = [t for t, d in snapshot.items() if d["quadrant"] == "IMPROVING"]
    if improving:
        lines.append(f"💡 <b>IMPROVING 주목:</b> {', '.join(improving)}")
    else:
        lines.append("💡 현재 IMPROVING 분면 진입 ETF 없음.")

    return "\n".join(lines)


def _find_transition(ticker: str, transitions: list) -> Optional[str]:
    """전환 리스트에서 해당 티커의 전환 문자열 찾기."""
    for t in transitions:
        if t["ticker"] == ticker:
            return t["transition"]
    return None


def _error_result(msg: str) -> dict:
    """에러 시 반환 구조."""
    return {
        "context_text": f"## SECTOR ROTATION\n⚠️ {msg}",
        "telegram_text": f"<b>📊 섹터 로테이션 맵</b>\n⚠️ {msg}",
        "today_snapshot": {},
        "transitions": [],
    }
