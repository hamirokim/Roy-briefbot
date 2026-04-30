"""
M7 상관관계 경고 — 보유 종목 간 집중 리스크 감지
================================================
v3 (2026-04-21): Stooq → yfinance 전환 (GitHub Actions IP 차단 회피)
v2.9 (2026-04-19): portfolio.json → Sheets 우선

역할: OPEN/ADD/EXIT_WATCH 종목 간 60영업일 피어슨 상관계수 계산.
0.85 이상이면 "사실상 동일 베팅" 경고 → DIGEST 컨텍스트에 주입.

원칙: 팩트만 전달. "위험!" 톤이 아니라 "인지해둬" 톤.
경고 쌍 0개면 빈 문자열 반환 → DIGEST에서 자동 생략 (희소 원칙).

위치: src/modules/m7_correlation.py
"""

import json
import os
import logging
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── 환경변수 ──
CORR_THRESHOLD = float(os.getenv("M7_CORR_THRESHOLD", "0.85"))
CORR_LOOKBACK_DAYS = int(os.getenv("M7_CORR_LOOKBACK", "90"))
CORR_MIN_DAYS = 40

_HELD_STATES = {"OPEN", "ADD", "EXIT_WATCH"}

PORTFOLIO_PATH = Path(__file__).resolve().parents[2] / "config" / "portfolio.json"


# ═══════════════════════════════════════════════════════════
# Sheets 우선 + portfolio.json fallback (v2.9 유지)
# ═══════════════════════════════════════════════════════════

def _normalize_ticker(t: str) -> str:
    """다양한 형식 → yfinance 형식 ('NVO' 또는 '005930.KS')."""
    t = t.strip()
    if t.lower().endswith(".us"):
        t = t[:-3]
    return t.upper()


def _load_from_sheets() -> list[str] | None:
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
                tickers.append(_normalize_ticker(ticker))
        logger.info("[M7] Sheets에서 %d개 보유 종목 로드", len(tickers))
        return tickers
    except Exception as e:
        logger.warning("[M7] Sheets 로드 실패 → portfolio.json fallback: %s", e)
        return None


def _load_from_portfolio_json() -> list[str]:
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
            tickers.append(_normalize_ticker(ticker))
    return tickers


def _load_held_tickers() -> list[str]:
    sheets_tickers = _load_from_sheets()
    if sheets_tickers is not None:
        return sheets_tickers
    return _load_from_portfolio_json()


# ═══════════════════════════════════════════════════════════
# yfinance batch 종가 시계열 (v3 신규)
# ═══════════════════════════════════════════════════════════

def _fetch_close_series(tickers: list[str]) -> dict[str, pd.Series]:
    """yfinance batch download — 여러 종목 한 번에."""
    if not tickers:
        return {}

    try:
        import yfinance as yf
    except ImportError:
        logger.error("[M7] yfinance 미설치")
        return {}

    # D89 근본 해결: period 사용 (시간대 무관)
    # CORR_LOOKBACK_DAYS=90 → "3mo"

    try:
        df = yf.download(
            " ".join(tickers),
            period="3mo",
            progress=False,
            group_by="ticker" if len(tickers) > 1 else "column",
            auto_adjust=False,
            threads=True,
        )

        if df is None or df.empty:
            logger.warning("[M7] yfinance 빈 결과")
            return {}

        result: dict[str, pd.Series] = {}

        # 단일 종목 vs 다중 종목 처리 분기
        if len(tickers) == 1:
            ticker = tickers[0]
            if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            if "Close" in df.columns:
                close = df["Close"].astype(float).dropna()
                if len(close) >= CORR_MIN_DAYS:
                    result[ticker] = close
                    logger.info("[M7] %s: %d일 종가 수집", ticker, len(close))
        else:
            # 멀티 인덱스: (ticker, field)
            for ticker in tickers:
                if ticker not in df.columns.get_level_values(0):
                    logger.warning("[M7] %s: yfinance 응답에 없음", ticker)
                    continue
                sub = df[ticker]
                if "Close" not in sub.columns:
                    continue
                close = sub["Close"].astype(float).dropna()
                if len(close) >= CORR_MIN_DAYS:
                    result[ticker] = close
                    logger.info("[M7] %s: %d일 종가 수집", ticker, len(close))
                else:
                    logger.warning("[M7] %s: 데이터 부족 (%d일 < %d)", ticker, len(close), CORR_MIN_DAYS)

        return result

    except Exception as e:
        logger.error("[M7] yfinance batch 실패: %s", e)
        return {}


# ═══════════════════════════════════════════════════════════
# 상관계수 계산 (원본 유지)
# ═══════════════════════════════════════════════════════════

def _compute_correlations(series_map: dict[str, pd.Series]) -> list[dict]:
    tickers = list(series_map.keys())
    alerts = []

    for t1, t2 in combinations(tickers, 2):
        try:
            df = pd.DataFrame({"a": series_map[t1], "b": series_map[t2]}).dropna()
            n_common = len(df)
            if n_common < CORR_MIN_DAYS:
                continue

            v1 = df["a"].values.astype(float)
            v2 = df["b"].values.astype(float)
            r1 = (v1[1:] - v1[:-1]) / v1[:-1]
            r2 = (v2[1:] - v2[:-1]) / v2[:-1]

            valid = np.isfinite(r1) & np.isfinite(r2)
            r1 = r1[valid]
            r2 = r2[valid]

            if len(r1) < CORR_MIN_DAYS - 1:
                continue

            corr = float(np.corrcoef(r1, r2)[0, 1])
            if np.isnan(corr):
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
# context 생성
# ═══════════════════════════════════════════════════════════

def _build_context(alerts: list[dict]) -> str:
    if not alerts:
        return ""

    lines = ["[상관관계 데이터]"]
    for a in alerts:
        t1, t2 = a["pair"]
        corr = a["corr"]
        days = a["days"]
        lines.append(
            f"- {t1}와 {t2}: 60일 수익률 상관계수 {corr:.2f} "
            f"(공통 {days}영업일 기준). 사실상 유사한 방향성."
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
    logger.info("=" * 50)
    logger.info("[M7] 상관관계 경고 시작 (yfinance v3)")

    tickers = _load_held_tickers()
    held_count = len(tickers)
    logger.info("[M7] 보유 종목: %d개 — %s", held_count, tickers)

    if held_count < 2:
        logger.info("[M7] 보유 종목 2개 미만 — 스킵")
        return {"context_text": "", "alert_count": 0, "held_count": held_count}

    series_map = _fetch_close_series(tickers)
    valid_count = len(series_map)
    logger.info("[M7] 유효 데이터: %d/%d개 종목", valid_count, held_count)

    if valid_count < 2:
        logger.info("[M7] 유효 데이터 2개 미만 — 계산 불가")
        return {"context_text": "", "alert_count": 0, "held_count": held_count}

    alerts = _compute_correlations(series_map)
    logger.info("[M7] 경고 쌍: %d개 (threshold=%.2f)", len(alerts), CORR_THRESHOLD)

    context = _build_context(alerts)
    logger.info("[M7] 상관관계 경고 완료")
    logger.info("=" * 50)

    return {
        "context_text": context,
        "alert_count": len(alerts),
        "held_count": held_count,
    }
