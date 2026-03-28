"""
M6 피드백 루프 — 과거 추천 종목 성과 추적
==========================================
역할: M3에서 추천된 종목의 사후 성과를 추적.
      추천 시점 대비 현재가 수익률 계산 → M1 GPT 컨텍스트에 주입.
원칙: 20영업일(~4주) 추적 후 자동 만료.
      추적 종목 0개면 빈 문자열 반환 (희소 원칙).
위치: src/modules/m6_feedback.py
"""

import os
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.collectors.stooq import fetch_daily_closes
from src.utils import now_kst, today_kst_str

# ── 환경변수 ──────────────────────────────────────────────
TRACK_DAYS = int(os.getenv("M6_TRACK_DAYS", "28"))  # 캘린더일 기준 만료 (≈20영업일)
MAX_HISTORY = int(os.getenv("M6_MAX_HISTORY", "20"))  # 최대 추적 종목 수

# Stooq 요청 딜레이
_STOOQ_DELAY = 0.3


# ═══════════════════════════════════════════════════════════
# M3 후보 → m6_history 기록용 변환
# ═══════════════════════════════════════════════════════════
def candidates_to_history_entries(candidates: list[dict]) -> list[dict]:
    """M3 run_m3() 반환 candidates → m6_history 저장용 엔트리 변환.
    중복 방지는 main.py에서 처리.
    """
    today = today_kst_str()
    entries = []
    for c in candidates:
        entries.append({
            "ticker": c.get("stooq_ticker", ""),
            "name": c.get("ticker", ""),  # 표시명 (예: ENPH)
            "date_added": today,
            "price_at_add": c.get("close", 0),
            "dd_pct": c.get("dd_pct", 0),
            "sector": c.get("sector", ""),
            "source": "M3",
        })
    return entries


# ═══════════════════════════════════════════════════════════
# 만료 정리
# ═══════════════════════════════════════════════════════════
def prune_history(history: list[dict]) -> list[dict]:
    """TRACK_DAYS 초과 항목 제거."""
    cutoff = (now_kst() - timedelta(days=TRACK_DAYS)).strftime("%Y-%m-%d")
    pruned = [h for h in history if h.get("date_added", "") >= cutoff]
    removed = len(history) - len(pruned)
    if removed > 0:
        print(f"[M6] 만료 정리: {removed}개 제거 (cutoff={cutoff})")
    return pruned


# ═══════════════════════════════════════════════════════════
# 중복 체크
# ═══════════════════════════════════════════════════════════
def deduplicate_entries(
    existing: list[dict], new_entries: list[dict]
) -> list[dict]:
    """이미 추적 중인 티커는 추가하지 않음. 새로 추가된 것만 반환."""
    existing_tickers = {h.get("ticker", "") for h in existing}
    added = []
    for entry in new_entries:
        if entry["ticker"] and entry["ticker"] not in existing_tickers:
            added.append(entry)
            existing_tickers.add(entry["ticker"])
    return added


# ═══════════════════════════════════════════════════════════
# 현재가 수집 + 수익률 계산
# ═══════════════════════════════════════════════════════════
def _normalize_closes(raw) -> pd.Series | None:
    """fetch_daily_closes 반환값 → 숫자 Series (M7과 동일 방어 로직)."""
    if raw is None:
        return None

    if isinstance(raw, pd.DataFrame):
        close_col = None
        for col in raw.columns:
            if col.lower() == "close":
                close_col = col
                break
        if close_col is None:
            numeric_cols = raw.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) == 0:
                return None
            close_col = numeric_cols[-1]
        series = raw[close_col].copy()
    elif isinstance(raw, pd.Series):
        series = raw.copy()
    else:
        try:
            series = pd.Series(raw)
        except Exception:
            return None

    series = series.apply(
        lambda x: float(x) if isinstance(x, (int, float, np.integer, np.floating)) else np.nan
    )
    series = series.dropna()
    return series if len(series) > 0 else None


def _fetch_current_price(ticker: str) -> float | None:
    """Stooq에서 최신 종가 1개 수집."""
    try:
        raw = fetch_daily_closes(ticker, lookback=5)
        series = _normalize_closes(raw)
        if series is not None and len(series) > 0:
            return float(series.iloc[-1])
    except Exception as e:
        print(f"[M6] {ticker} 현재가 수집 실패: {e}")
    return None


def _compute_performance(history: list[dict]) -> list[dict]:
    """각 추적 종목의 현재가 수집 → 수익률 계산."""
    results = []
    for h in history:
        ticker = h.get("ticker", "")
        price_at_add = h.get("price_at_add", 0)
        if not ticker or price_at_add <= 0:
            continue

        current_price = _fetch_current_price(ticker)
        time.sleep(_STOOQ_DELAY)

        if current_price is None:
            print(f"[M6] {h['name']}: 현재가 수집 실패 — 스킵")
            continue

        pnl_pct = ((current_price - price_at_add) / price_at_add) * 100.0
        days_held = (
            now_kst().date()
            - datetime.strptime(h["date_added"], "%Y-%m-%d").date()
        ).days

        results.append({
            "name": h.get("name", ""),
            "ticker": ticker,
            "date_added": h["date_added"],
            "price_at_add": price_at_add,
            "current_price": round(current_price, 2),
            "pnl_pct": round(pnl_pct, 1),
            "days_held": days_held,
            "dd_pct": h.get("dd_pct", 0),
            "sector": h.get("sector", ""),
        })

    return results


# ═══════════════════════════════════════════════════════════
# context_text 생성
# ═══════════════════════════════════════════════════════════
def _build_context(results: list[dict]) -> str:
    """성과 데이터 → M1 GPT 컨텍스트."""
    if not results:
        return ""

    lines = ["[과거 추천 성과]"]

    for r in results:
        sign = "+" if r["pnl_pct"] >= 0 else ""
        lines.append(
            f"- {r['name']}: 추천일 {r['date_added']} (${r['price_at_add']:.2f}) → "
            f"현재 ${r['current_price']:.2f} ({sign}{r['pnl_pct']}%, {r['days_held']}일 경과). "
            f"추천 당시 DD {r['dd_pct']}%."
        )

    # 요약 통계
    pnls = [r["pnl_pct"] for r in results]
    avg_pnl = sum(pnls) / len(pnls) if pnls else 0
    winners = sum(1 for p in pnls if p > 0)
    lines.append("")
    lines.append(
        f"요약: {len(results)}건 추적 중, 평균 수익률 {avg_pnl:+.1f}%, "
        f"상승 {winners}건 / 하락 {len(results) - winners}건."
    )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════════════
def run_m6(state: dict) -> dict:
    """M6 피드백 루프 실행.
    반환: {"context_text": str, "track_count": int}
    """
    print("=" * 50)
    print("[M6] 피드백 루프 시작")

    # 1. m6_history 로드
    history = state.get("m6_history", [])
    if history is None:
        history = []

    # 2. 만료 정리
    history = prune_history(history)

    print(f"[M6] 추적 종목: {len(history)}개")

    if not history:
        print("[M6] 추적 종목 없음 — 스킵 (희소 원칙)")
        # state에 정리된 history 저장
        state["m6_history"] = history
        return {"context_text": "", "track_count": 0}

    # 3. 현재가 수집 + 수익률 계산
    results = _compute_performance(history)
    print(f"[M6] 성과 계산 완료: {len(results)}/{len(history)}개")

    # 4. context 생성
    context = _build_context(results)
    if context:
        print(f"[M6] context 생성: {len(context)}자")
    else:
        print("[M6] context 빈 문자열")

    # state에 정리된 history 저장
    state["m6_history"] = history

    print("[M6] 피드백 루프 완료")
    print("=" * 50)

    return {
        "context_text": context,
        "track_count": len(results),
    }
