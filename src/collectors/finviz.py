"""Finviz 스크리너 수집기.

사용법:
    from src.collectors.finviz import fetch_contrarian_candidates

    candidates = fetch_contrarian_candidates()
    # [{"ticker": "FMC", "sector": "Basic Materials", "industry": "...",
    #   "market_cap": "2.1B", "pe": -5.2, "eps_growth": ..., "insider_trans": ...}, ...]

Finviz 무료 스크리너 기반. 공식 API 아님 (스크래핑).
실패 시 빈 리스트 반환 — Stage 1(Stooq 고정 유니버스)으로 폴백.
"""

from __future__ import annotations

import time
from typing import Any, Optional

# ── Finviz 라이브러리 (없으면 graceful 폴백) ──
try:
    from finvizfinance.screener.overview import Overview
    from finvizfinance.quote import finvizfinance
    FINVIZ_AVAILABLE = True
except ImportError:
    FINVIZ_AVAILABLE = False
    print("[WARN] finvizfinance 미설치 — Finviz 스크리닝 비활성화")


def _safe_float(val: Any) -> Optional[float]:
    """문자열/숫자를 float로 변환. 실패 시 None."""
    if val is None or val == "" or val == "-":
        return None
    try:
        if isinstance(val, str):
            val = val.replace("%", "").replace(",", "").strip()
        return float(val)
    except (ValueError, TypeError):
        return None


def fetch_contrarian_candidates(
    max_results: int = 30,
) -> list[dict]:
    """Finviz 스크리너로 역발상 후보 동적 수집.

    필터 조건:
    - 52주 최저 근처 (20-Week Low 이하)
    - 최근 1주 반등 (Performance Week: Up)
    - 시총 $300M 이상 (너무 소형 제외)

    Returns:
        [{ticker, company, sector, industry, market_cap, price, change,
          volume, pe, eps_growth_next_y, insider_trans, perf_week, perf_month,
          from_high_52w}, ...]
        실패 시 빈 리스트.
    """
    if not FINVIZ_AVAILABLE:
        return []

    try:
        print("[Finviz] 스크리너 실행 중...")
        foverview = Overview()

        # Finviz 필터 설정
        filters_dict = {
            "Market Cap.": "+Small (over $300mln)",      # 시총 $300M+
            "Performance": "Week Up",                     # 최근 1주 양수
            "52-Week High/Low": "0-10% above Low",       # 52주 최저 근처
        }
        foverview.set_filter(filters_dict=filters_dict)

        # 스크리너 실행
        df = foverview.screener_view()
        time.sleep(1)  # rate-limit 대응

        if df is None or df.empty:
            print("[Finviz] 스크리너 결과 없음")
            return []

        print(f"[Finviz] 스크리너 결과: {len(df)}개")

        results = []
        for _, row in df.head(max_results).iterrows():
            results.append({
                "ticker": str(row.get("Ticker", "")),
                "company": str(row.get("Company", "")),
                "sector": str(row.get("Sector", "")),
                "industry": str(row.get("Industry", "")),
                "market_cap": str(row.get("Market Cap", "")),
                "price": _safe_float(row.get("Price")),
                "change": _safe_float(row.get("Change")),
                "volume": _safe_float(row.get("Volume")),
            })

        return results

    except Exception as e:
        print(f"[WARN] Finviz 스크리너 실패: {e}")
        return []


def fetch_fundamental_data(ticker: str) -> Optional[dict]:
    """개별 종목의 펀더멘탈 데이터 수집.

    Returns:
        {pe, forward_pe, eps_next_y, eps_growth_next_y, peg,
         insider_trans, inst_trans, short_float, rsi14,
         sector, industry, market_cap, earnings_date}
        실패 시 None.
    """
    if not FINVIZ_AVAILABLE:
        return None

    try:
        time.sleep(0.5)  # rate-limit
        stock = finvizfinance(ticker)
        info = stock.ticker_fundament()

        if not info:
            return None

        return {
            "pe": _safe_float(info.get("P/E")),
            "forward_pe": _safe_float(info.get("Forward P/E")),
            "eps_next_y": _safe_float(info.get("EPS next Y")),
            "eps_growth_next_y": _safe_float(info.get("EPS next Y", "").replace("%", "")),
            "peg": _safe_float(info.get("PEG")),
            "insider_trans": _safe_float(info.get("Insider Trans")),
            "inst_trans": _safe_float(info.get("Inst Trans")),
            "short_float": _safe_float(info.get("Short Float")),
            "rsi14": _safe_float(info.get("RSI (14)")),
            "sector": str(info.get("Sector", "")),
            "industry": str(info.get("Industry", "")),
            "market_cap": str(info.get("Market Cap", "")),
            "earnings_date": str(info.get("Earnings", "")),
        }

    except Exception as e:
        print(f"[WARN] Finviz 펀더멘탈 실패 ({ticker}): {e}")
        return None
