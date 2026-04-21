"""
M7 상관관계 경고 — 보유 종목 간 집중 리스크 감지 (v2.9 — Sheets 연동 패치)
==========================================================================
역할: OPEN/ADD/EXIT_WATCH 종목 간 60영업일 피어슨 상관계수 계산.
0.85 이상이면 "사실상 동일 베팅" 경고 → M1 GPT 컨텍스트에 주입.

원칙: 팩트만 전달. "위험!" 톤이 아니라 "인지해둬" 톤.
경고 쌍 0개면 빈 문자열 반환 → M1에서 자동 생략 (희소 원칙).

v2.9 변경 (D27):
  - portfolio.json 단독 → Sheets 우선 + portfolio.json fallback (M4 패턴 통합)
  - _load_held_tickers()만 재작성, 나머지 로직은 원본 유지

위치: src/modules/m7_correlation.py
"""

import json
import os
import time
import logging
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from src.collectors.stooq import fetch_daily_closes

logger = logging.getLogger(__name__)

# ── 환경변수 ──
CORR_THRESHOLD = float(os.getenv("M7_CORR_THRESHOLD", "0.85"))
CORR_LOOKBACK = int(os.getenv("M7_CORR_LOOKBACK", "90"))  # 캘린더일 (Stooq 요청용)
CORR_MIN_DAYS = 40  # 최소 영업일 데이터. 이 미만이면 상관계수 신뢰 불가.

_HELD_STATES = {"OPEN", "ADD", "EXIT_WATCH"}
_STOOQ_DELAY = 0.3

PORTFOLIO_PATH = Path(__file__).resolve().parents[2] / "config" / "portfolio.json"


# ═══════════════════════════════════════════════════════════
# v2.9 신규: Sheets 우선 로드 (M4 패턴)
# ═══════════════════════════════════════════════════════════

def _load_from_sheets() -> list[str] | None:
    """Sheets에서 OPEN/ADD/EXIT_WATCH 종목 티커 로드. 실패 시 None.

    Sheets에서 받은 티커는 'NVO' 같은 순수 형식 → '.us' 접미사 추가.
    """
    try:
        from src.collectors.sheets import read_positions
        positions = read_positions()
        if positions is None:
            return None
        tickers = []
        for p in positions:
            status = (p.get("status") or "").upper()
            ticker = (p.get("ticker") or "").strip()
            if status in _HELD_STATES and ticker:
                # Stooq 형식으로 변환
                if not ticker.lower().endswith(".us"):
                    ticker = f"{ticker.lower()}.us"
                tickers.append(ticker)
        logger.info("[M7] Sheets에서 %d개 보유 종목 로드", len(tickers))
        return tickers
    except Exception as e:
        logger.warning("[M7] Sheets 로드 실패 → portfolio.json fallback: %s", e)
        return None


def _load_from_portfolio_json() -> list[str]:
    """portfolio.json fallback (원본 로직 유지)."""
    if not PORTFOLIO_PATH.exists():
        logger.info("[M7] portfolio.json 없음 — 빈 리스트")
        return []
    try:
        with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error("[M7] portfolio.json 로드 실패: %s", e)
        return []
    positions = data.get("positions", [])
    tickers = []
    for pos in positions:
        status = pos.get("status", "").upper()
        ticker = pos.get("ticker", "").strip()
        if status in _HELD_STATES and ticker:
            tickers.append(ticker)
    return tickers


def _load_held_tickers() -> list[str]:
    """Sheets 우선 → portfolio.json fallback (v2.9 패치)."""
    sheets_tickers = _load_from_sheets()
    if sheets_tickers is not None:
        return sheets_tickers
    return _load_from_portfolio_json()


# ═══════════════════════════════════════════════════════════
# fetch_daily_closes 반환값 → 숫자 Series로 정규화 (원본 유지)
# ═══════════════════════════════════════════════════════════

def _normalize_closes(raw) -> pd.Series | None:
    """fetch_daily_closes() 반환값을 숫자 Series로 변환."""
    if raw is None:
        return None

    # DataFrame인 경우 → Close 열 추출
    if isinstance(raw, pd.DataFrame):
        close_col = None
        for col in raw.columns:
            if col.lower() == "close":
                close_col = col
                break
        if close_col is None:
            numeric_cols = raw.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) == 0:
                logger.debug("[M7] DataFrame에 숫자 열 없음")
                return None
            close_col = numeric_cols[-1]

        series = raw[close_col].copy()

        # Date 열이 있으면 인덱스로 설정
        date_col = None
        for col in raw.columns:
            if col.lower() == "date":
                date_col = col
                break
        if date_col is not None:
            series.index = pd.to_datetime(raw[date_col])

    elif isinstance(raw, pd.Series):
        series = raw.copy()
    else:
        try:
            series = pd.Series(raw)
        except Exception:
            return None

    # float 강제 변환
    series = series.apply(
        lambda x: float(x) if isinstance(x, (int, float, np.integer, np.floating)) else np.nan
    )
    series = series.dropna()
    return series if len(series) > 0 else None


# ═══════════════════════════════════════════════════════════
# 종가 시계열 수집 (원본 유지)
# ═══════════════════════════════════════════════════════════

def _fetch_close_series(tickers: list[str]) -> dict[str, pd.Series]:
    """각 티커의 일봉 종가 시계열을 수집."""
    result = {}
    for ticker in tickers:
        try:
            raw = fetch_daily_closes(ticker, lookback=CORR_LOOKBACK)
            closes = _normalize_closes(raw)
            if closes is not None and len(closes) >= CORR_MIN_DAYS:
                result[ticker] = closes
                logger.info("[M7] %s: %d일 종가 수집 OK", ticker, len(closes))
            else:
                n = len(closes) if closes is not None else 0
                logger.warning("[M7] %s: 데이터 부족 (%d일 < %d일 최소)", ticker, n, CORR_MIN_DAYS)
        except Exception as e:
            logger.warning("[M7] %s 수집 실패: %s", ticker, e)
        time.sleep(_STOOQ_DELAY)
    return result


# ═══════════════════════════════════════════════════════════
# 상관계수 계산 (원본 유지)
# ═══════════════════════════════════════════════════════════

def _compute_correlations(series_map: dict[str, pd.Series]) -> list[dict]:
    """모든 종목 쌍의 피어슨 상관계수 계산. threshold 이상만 반환."""
    tickers = list(series_map.keys())
    alerts = []

    for t1, t2 in combinations(tickers, 2):
        try:
            df = pd.DataFrame({
                "a": series_map[t1],
                "b": series_map[t2],
            }).dropna()
            n_common = len(df)
            if n_common < CORR_MIN_DAYS:
                logger.debug("[M7] %s-%s: 공통 날짜 부족 (%d일 < %d일)", t1, t2, n_common, CORR_MIN_DAYS)
                continue

            v1 = df["a"].values.astype(float)
            v2 = df["b"].values.astype(float)
            r1 = (v1[1:] - v1[:-1]) / v1[:-1]
            r2 = (v2[1:] - v2[:-1]) / v2[:-1]

            valid = np.isfinite(r1) & np.isfinite(r2)
            r1 = r1[valid]
            r2 = r2[valid]

            if len(r1) < CORR_MIN_DAYS - 1:
                logger.debug("[M7] %s-%s: 유효 수익률 부족 (%d일)", t1, t2, len(r1))
                continue

            corr = float(np.corrcoef(r1, r2)[0, 1])
            if np.isnan(corr):
                logger.debug("[M7] %s-%s: 상관계수 NaN", t1, t2)
                continue

            logger.info("[M7] %s-%s: 상관계수 %.3f (공통 %d일)", t1, t2, corr, n_common)

            if corr >= CORR_THRESHOLD:
                alerts.append({
                    "pair": (t1, t2),
                    "corr": corr,
                    "days": n_common,
                })

        except Exception as e:
            logger.warning("[M7] %s-%s 계산 실패: %s", t1, t2, e)
            continue

    alerts.sort(key=lambda x: x["corr"], reverse=True)
    return alerts


# ═══════════════════════════════════════════════════════════
# 표시명 변환 + context 생성 (원본 유지)
# ═══════════════════════════════════════════════════════════

def _display_ticker(ticker: str) -> str:
    return ticker.replace(".us", "").upper()


def _build_context(alerts: list[dict]) -> str:
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
# 메인 실행 (원본 유지)
# ═══════════════════════════════════════════════════════════

def run_m7() -> dict:
    """M7 상관관계 경고 실행.

    반환: {"context_text": str, "alert_count": int, "held_count": int}
    """
    logger.info("=" * 50)
    logger.info("[M7] 상관관계 경고 시작")

    tickers = _load_held_tickers()
    held_count = len(tickers)
    logger.info("[M7] 보유 종목: %d개 — %s", held_count, tickers)

    if held_count < 2:
        logger.info("[M7] 보유 종목 2개 미만 — 상관관계 계산 불필요. 스킵.")
        return {"context_text": "", "alert_count": 0, "held_count": held_count}

    series_map = _fetch_close_series(tickers)
    valid_count = len(series_map)
    logger.info("[M7] 유효 데이터: %d/%d개 종목", valid_count, held_count)

    if valid_count < 2:
        logger.info("[M7] 유효 데이터 2개 미만 — 상관관계 계산 불가.")
        return {"context_text": "", "alert_count": 0, "held_count": held_count}

    alerts = _compute_correlations(series_map)
    logger.info("[M7] 경고 쌍: %d개 (threshold=%.2f)", len(alerts), CORR_THRESHOLD)

    context = _build_context(alerts)
    if context:
        logger.info("[M7] context 생성: %d자", len(context))
    else:
        logger.info("[M7] 경고 쌍 없음 — context 빈 문자열 (희소 원칙)")

    logger.info("[M7] 상관관계 경고 완료")
    logger.info("=" * 50)

    return {
        "context_text": context,
        "alert_count": len(alerts),
        "held_count": held_count,
    }
