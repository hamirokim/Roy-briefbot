"""
M7 상관관계 경고 — 보유 종목 간 집중 리스크 감지
=================================================
역할: OPEN/ADD/EXIT_WATCH 종목 간 60영업일 피어슨 상관계수 계산.
      0.85 이상이면 "사실상 동일 베팅" 경고 → M1 GPT 컨텍스트에 주입.
원칙: 팩트만 전달. "위험!" 톤이 아니라 "인지해둬" 톤.
      경고 쌍 0개면 빈 문자열 반환 → M1에서 자동 생략 (희소 원칙).
위치: src/modules/m7_correlation.py
"""

import json
import os
import time
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from src.collectors.stooq import fetch_daily_closes

# ── 환경변수 ──────────────────────────────────────────────
CORR_THRESHOLD = float(os.getenv("M7_CORR_THRESHOLD", "0.85"))
CORR_LOOKBACK = int(os.getenv("M7_CORR_LOOKBACK", "90"))  # 캘린더일 (Stooq 요청용)
CORR_MIN_DAYS = 40  # 최소 영업일 데이터. 이 미만이면 상관계수 신뢰 불가.

# 보유 종목으로 간주할 상태 (미보유 상태 WATCH/ARMED 제외)
_HELD_STATES = {"OPEN", "ADD", "EXIT_WATCH"}

# Stooq 요청 간 딜레이 (초)
_STOOQ_DELAY = 0.3


# ═══════════════════════════════════════════════════════════
# portfolio.json 로드
# ═══════════════════════════════════════════════════════════
def _portfolio_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "portfolio.json"


def _load_held_tickers() -> list[str]:
    """portfolio.json에서 OPEN/ADD/EXIT_WATCH 종목 티커 추출.
    반환: ['mos.us', 'nvo.us', ...] 형태의 Stooq 티커 리스트.
    """
    path = _portfolio_path()
    if not path.exists():
        print("[M7] portfolio.json 없음 — 스킵")
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[M7] portfolio.json 로드 실패: {e}")
        return []

    positions = data.get("positions", [])
    tickers = []
    for pos in positions:
        status = pos.get("status", "").upper()
        ticker = pos.get("ticker", "").strip()
        if status in _HELD_STATES and ticker:
            tickers.append(ticker)

    return tickers


# ═══════════════════════════════════════════════════════════
# 종가 시계열 수집
# ═══════════════════════════════════════════════════════════
def _fetch_close_series(tickers: list[str]) -> dict[str, pd.Series]:
    """각 티커의 일봉 종가 시계열을 수집. {ticker: pd.Series(날짜 인덱스)}"""
    result = {}
    for ticker in tickers:
        try:
            closes = fetch_daily_closes(ticker, lookback=CORR_LOOKBACK)
            if closes is not None and len(closes) >= CORR_MIN_DAYS:
                result[ticker] = closes
                print(f"[M7] {ticker}: {len(closes)}일 종가 수집 OK")
            else:
                n = len(closes) if closes is not None else 0
                print(f"[M7] {ticker}: 데이터 부족 ({n}일 < {CORR_MIN_DAYS}일 최소)")
        except Exception as e:
            print(f"[M7] {ticker} 수집 실패: {e}")
        time.sleep(_STOOQ_DELAY)

    return result


# ═══════════════════════════════════════════════════════════
# 상관계수 계산
# ═══════════════════════════════════════════════════════════
def _compute_correlations(
    series_map: dict[str, pd.Series],
) -> list[dict]:
    """모든 종목 쌍의 피어슨 상관계수 계산. threshold 이상만 반환.
    반환: [{"pair": ("mos.us", "nvo.us"), "corr": 0.91, "days": 58}, ...]
    """
    tickers = list(series_map.keys())
    alerts = []

    for t1, t2 in combinations(tickers, 2):
        s1 = series_map[t1]
        s2 = series_map[t2]

        # 날짜 교집합으로 정렬
        common = s1.index.intersection(s2.index)
        if len(common) < CORR_MIN_DAYS:
            print(
                f"[M7] {t1}-{t2}: 공통 날짜 부족 ({len(common)}일 < {CORR_MIN_DAYS}일)"
            )
            continue

        # numpy array로 직접 수익률 계산
        # (pct_change()는 DatetimeArray 인덱스에서 __truediv__ 에러 발생)
        v1 = s1.loc[common].values.astype(float)
        v2 = s2.loc[common].values.astype(float)

        # 일간 수익률: (today - yesterday) / yesterday
        r1 = (v1[1:] - v1[:-1]) / v1[:-1]
        r2 = (v2[1:] - v2[:-1]) / v2[:-1]

        # NaN/Inf 제거
        valid = np.isfinite(r1) & np.isfinite(r2)
        r1 = r1[valid]
        r2 = r2[valid]

        if len(r1) < CORR_MIN_DAYS - 1:
            print(f"[M7] {t1}-{t2}: 유효 수익률 부족 ({len(r1)}일)")
            continue

        corr = float(np.corrcoef(r1, r2)[0, 1])

        if np.isnan(corr):
            print(f"[M7] {t1}-{t2}: 상관계수 NaN — 스킵")
            continue

        print(f"[M7] {t1}-{t2}: 상관계수 {corr:.3f} (공통 {len(common)}일)")

        if corr >= CORR_THRESHOLD:
            alerts.append({
                "pair": (t1, t2),
                "corr": corr,
                "days": len(common),
            })

    # 상관계수 높은 순 정렬
    alerts.sort(key=lambda x: x["corr"], reverse=True)
    return alerts


# ═══════════════════════════════════════════════════════════
# 티커 → 표시명 변환
# ═══════════════════════════════════════════════════════════
def _display_ticker(ticker: str) -> str:
    """'mos.us' → 'MOS' 형태로 변환."""
    return ticker.replace(".us", "").upper()


# ═══════════════════════════════════════════════════════════
# context_text 생성
# ═══════════════════════════════════════════════════════════
def _build_context(alerts: list[dict]) -> str:
    """경고 쌍 → M1 GPT에 주입할 context 텍스트 생성."""
    if not alerts:
        return ""

    lines = ["[상관관계 데이터]"]
    for a in alerts:
        t1 = _display_ticker(a["pair"][0])
        t2 = _display_ticker(a["pair"][1])
        corr = a["corr"]
        days = a["days"]
        lines.append(
            f"- {t1}와 {t2}: 60일 수익률 상관계수 {corr:.2f} "
            f"(공통 {days}영업일 기준). "
            f"상관계수 {CORR_THRESHOLD} 이상 — 사실상 유사한 방향성."
        )

    lines.append("")
    lines.append(
        "참고: 시장 전체 급락 환경(VIX HIGH/EXTREME)에서는 "
        "대부분 종목의 상관관계가 일시적으로 높아질 수 있음. "
        "이 경우 '집중 리스크'보다 '시장 리스크'에 해당."
    )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════════════
def run_m7() -> dict:
    """M7 상관관계 경고 모듈 실행.
    반환: {"context_text": str, "alert_count": int, "held_count": int}
    """
    print("=" * 50)
    print("[M7] 상관관계 경고 시작")

    # 1. 보유 종목 추출
    tickers = _load_held_tickers()
    held_count = len(tickers)
    print(f"[M7] 보유 종목: {held_count}개 — {tickers}")

    if held_count < 2:
        print("[M7] 보유 종목 2개 미만 — 상관관계 계산 불필요. 스킵.")
        return {"context_text": "", "alert_count": 0, "held_count": held_count}

    # 2. 종가 시계열 수집
    series_map = _fetch_close_series(tickers)
    valid_count = len(series_map)
    print(f"[M7] 유효 데이터: {valid_count}/{held_count}개 종목")

    if valid_count < 2:
        print("[M7] 유효 데이터 2개 미만 — 상관관계 계산 불가.")
        return {"context_text": "", "alert_count": 0, "held_count": held_count}

    # 3. 상관계수 계산
    alerts = _compute_correlations(series_map)
    print(f"[M7] 경고 쌍: {len(alerts)}개 (threshold={CORR_THRESHOLD})")

    # 4. context 생성
    context = _build_context(alerts)
    if context:
        print(f"[M7] context 생성: {len(context)}자")
    else:
        print("[M7] 경고 쌍 없음 — context 빈 문자열 (희소 원칙)")

    print("[M7] 상관관계 경고 완료")
    print("=" * 50)

    return {
        "context_text": context,
        "alert_count": len(alerts),
        "held_count": held_count,
    }
