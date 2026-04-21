"""
M2 섹터 RRG (Relative Rotation Graph) — v3 (2026-04-21)
==========================================================
v3: yfinance 기반 신규 작성 (Stooq 차단 회피)
v1~v2: Stooq 의존 (deprecated)

역할: SPY 벤치마크 대비 미국 섹터 ETF 11개의 4분면 분류.
출력: REGIME 에이전트가 "매크로 환경" 컨텍스트로 활용.

4분면:
  LEADING: 상대강도 + 모멘텀 모두 강함 (이미 leader)
  WEAKENING: 상대강도 강하지만 모멘텀 약화 (cooling)
  LAGGING: 상대강도 + 모멘텀 모두 약함 (avoid)
  IMPROVING: 상대강도 약하지만 모멘텀 회복 중 (bottoming, 좌측거래 후보)

위치: src/modules/m2_rotation.py
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 섹터 ETF 매핑 (etf_map.json 미사용 시 fallback)
# ═══════════════════════════════════════════════════════════

_DEFAULT_SECTOR_MAP = {
    "XLK": {"label": "기술", "group": "growth"},
    "XLV": {"label": "헬스케어", "group": "defensive"},
    "XLF": {"label": "금융", "group": "cyclical"},
    "XLY": {"label": "임의소비재", "group": "cyclical"},
    "XLP": {"label": "필수소비재", "group": "defensive"},
    "XLE": {"label": "에너지", "group": "cyclical"},
    "XLI": {"label": "산업재", "group": "cyclical"},
    "XLB": {"label": "소재", "group": "cyclical"},
    "XLC": {"label": "통신", "group": "growth"},
    "XLU": {"label": "유틸리티", "group": "defensive"},
    "XLRE": {"label": "리츠", "group": "defensive"},
}

BENCHMARK = "SPY"
LOOKBACK_DAYS = 90       # 90일 일봉
RATIO_WINDOW = 14        # ratio 모멘텀 계산 기간


# ═══════════════════════════════════════════════════════════
# yfinance batch fetch
# ═══════════════════════════════════════════════════════════

def _fetch_closes(tickers: list[str]) -> dict[str, pd.Series]:
    """yfinance batch — 여러 종목 동시 일봉 종가 fetch."""
    if not tickers:
        return {}

    try:
        import yfinance as yf
    except ImportError:
        logger.error("[M2] yfinance 미설치")
        return {}

    end = datetime.now()
    start = end - timedelta(days=LOOKBACK_DAYS)

    try:
        df = yf.download(
            " ".join(tickers),
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            group_by="ticker" if len(tickers) > 1 else "column",
            auto_adjust=False,
            threads=True,
        )

        if df is None or df.empty:
            logger.warning("[M2] yfinance 빈 결과")
            return {}

        result: dict[str, pd.Series] = {}

        if len(tickers) == 1:
            ticker = tickers[0]
            if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            if "Close" in df.columns:
                close = df["Close"].astype(float).dropna()
                if len(close) >= RATIO_WINDOW + 5:
                    result[ticker] = close
        else:
            for ticker in tickers:
                if ticker not in df.columns.get_level_values(0):
                    continue
                sub = df[ticker]
                if "Close" not in sub.columns:
                    continue
                close = sub["Close"].astype(float).dropna()
                if len(close) >= RATIO_WINDOW + 5:
                    result[ticker] = close

        logger.info("[M2] %d/%d 종목 종가 수집", len(result), len(tickers))
        return result

    except Exception as e:
        logger.error("[M2] yfinance 실패: %s", e)
        return {}


# ═══════════════════════════════════════════════════════════
# RRG 계산 — 상대강도 + 모멘텀
# ═══════════════════════════════════════════════════════════

def _compute_rrg(sector_closes: dict[str, pd.Series], benchmark_close: pd.Series) -> dict[str, dict]:
    """각 섹터의 RS-Ratio, RS-Momentum, 4분면 계산.

    표준 RRG 공식:
      ratio = sector / benchmark (정규화: 평균 100)
      momentum = ratio의 N일 변화율
      4분면: ratio > 100 + momentum > 0 = LEADING, 등
    """
    result: dict[str, dict] = {}

    for ticker, close in sector_closes.items():
        try:
            df = pd.DataFrame({
                "sector": close,
                "bench": benchmark_close,
            }).dropna()

            if len(df) < RATIO_WINDOW + 5:
                logger.debug("[M2] %s: 데이터 부족 (%d일)", ticker, len(df))
                continue

            # ratio = sector / benchmark, 평균 100으로 정규화
            ratio = df["sector"] / df["bench"]
            ratio_norm = (ratio / ratio.rolling(RATIO_WINDOW).mean()) * 100

            # momentum = ratio_norm의 N일 변화율 (100 기준)
            momentum = ratio_norm.pct_change(RATIO_WINDOW) * 100 + 100

            # 최근 값
            rs_ratio = float(ratio_norm.iloc[-1])
            rs_momentum = float(momentum.iloc[-1])

            if np.isnan(rs_ratio) or np.isnan(rs_momentum):
                continue

            # 4분면 분류 (100 기준)
            if rs_ratio >= 100 and rs_momentum >= 100:
                quadrant = "LEADING"
            elif rs_ratio >= 100 and rs_momentum < 100:
                quadrant = "WEAKENING"
            elif rs_ratio < 100 and rs_momentum < 100:
                quadrant = "LAGGING"
            else:  # rs_ratio < 100 and rs_momentum >= 100
                quadrant = "IMPROVING"

            sector_info = _DEFAULT_SECTOR_MAP.get(ticker, {"label": ticker, "group": ""})
            result[ticker] = {
                "quadrant": quadrant,
                "label": sector_info["label"],
                "group": sector_info["group"],
                "ratio": round(rs_ratio, 2),
                "momentum": round(rs_momentum, 2),
            }
        except Exception as e:
            logger.warning("[M2] %s 계산 실패: %s", ticker, e)
            continue

    return result


# ═══════════════════════════════════════════════════════════
# 분면 전환 감지 (어제 → 오늘)
# ═══════════════════════════════════════════════════════════

def _detect_transitions(today_snapshot: dict, m2_history: dict) -> list[dict]:
    """state의 m2_history 보고 분면 변경된 종목 찾기."""
    if not m2_history:
        return []

    sorted_dates = sorted(m2_history.keys(), reverse=True)
    if not sorted_dates:
        return []

    yesterday = sorted_dates[0]
    yesterday_snapshot = m2_history.get(yesterday, {})

    transitions = []
    for ticker, today_info in today_snapshot.items():
        prev = yesterday_snapshot.get(ticker, {}).get("quadrant")
        curr = today_info.get("quadrant")
        if prev and curr and prev != curr:
            transitions.append({
                "ticker": ticker,
                "label": today_info.get("label", ""),
                "transition": f"{prev} → {curr}",
                "prev": prev,
                "curr": curr,
            })
    return transitions


# ═══════════════════════════════════════════════════════════
# context 생성
# ═══════════════════════════════════════════════════════════

def _build_context(snapshot: dict, transitions: list[dict]) -> str:
    if not snapshot:
        return ""

    by_quad = {"LEADING": [], "IMPROVING": [], "WEAKENING": [], "LAGGING": []}
    for ticker, info in snapshot.items():
        quad = info.get("quadrant")
        if quad in by_quad:
            by_quad[quad].append(f"{ticker}({info.get('label', '')})")

    lines = ["[섹터 회전 (RRG) — 미국 11개 섹터 ETF]"]
    for q in ["LEADING", "IMPROVING", "WEAKENING", "LAGGING"]:
        items = by_quad.get(q, [])
        if items:
            lines.append(f"  {q}: {', '.join(items)}")

    if transitions:
        lines.append("")
        lines.append("[분면 전환]")
        for t in transitions:
            lines.append(f"  {t['ticker']} ({t['label']}): {t['transition']}")

    lines.append("")
    lines.append(
        "참고: IMPROVING = 약세에서 회복 중 (좌측거래 후보 영역). "
        "LEADING = 이미 강함. LAGGING = 약세 지속. WEAKENING = 강세 식음."
    )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════════════

def run_m2(etf_map: Optional[dict] = None, state: Optional[dict] = None) -> dict:
    """M2 섹터 RRG 실행.

    Args:
        etf_map: config/etf_map.json (선택 — 미사용 시 _DEFAULT_SECTOR_MAP)
        state: LangGraph state (m2_history 추출용)

    Returns:
        {
            "today_snapshot": dict[ticker, {quadrant, label, group, ratio, momentum}],
            "transitions": list,
            "context_text": str,
        }
    """
    logger.info("=" * 50)
    logger.info("[M2] 섹터 RRG 시작 (yfinance v3)")

    # 종목 리스트
    sector_tickers = list(_DEFAULT_SECTOR_MAP.keys())
    all_tickers = [BENCHMARK] + sector_tickers

    # yfinance batch fetch
    closes = _fetch_closes(all_tickers)

    if BENCHMARK not in closes:
        logger.warning("[M2] %s 벤치마크 없음 — 빈 결과", BENCHMARK)
        return {"today_snapshot": {}, "transitions": [], "context_text": ""}

    benchmark_close = closes.pop(BENCHMARK)

    if len(closes) < 2:
        logger.warning("[M2] 섹터 ETF 2개 미만 — 빈 결과")
        return {"today_snapshot": {}, "transitions": [], "context_text": ""}

    # RRG 계산
    snapshot = _compute_rrg(closes, benchmark_close)
    logger.info("[M2] %d개 섹터 RRG 분류 완료", len(snapshot))

    # 4분면 분포 로깅
    quad_count = {}
    for info in snapshot.values():
        q = info.get("quadrant", "?")
        quad_count[q] = quad_count.get(q, 0) + 1
    logger.info("[M2] 분포: %s", quad_count)

    # 분면 전환
    m2_history = (state or {}).get("m2_history", {})
    transitions = _detect_transitions(snapshot, m2_history)
    if transitions:
        logger.info("[M2] 분면 전환: %d개", len(transitions))

    context = _build_context(snapshot, transitions)

    logger.info("[M2] 섹터 RRG 완료")
    logger.info("=" * 50)

    return {
        "today_snapshot": snapshot,
        "transitions": transitions,
        "context_text": context,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    result = run_m2()
    print(result["context_text"])
