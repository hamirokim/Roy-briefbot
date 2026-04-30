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

# 테마 ETF 매핑 (Z1 신규 — D55/D58 정합)
# 섹터(11개) 안의 sub-industry 또는 cross-sector 테마 추적용
# AAPL/NVDA 같은 주도주가 매집 단계 못 통과해도 테마 RRG로 잡힘
_DEFAULT_THEME_MAP = {
    # 반도체 (Tech 안의 sub-industry, 가장 핫)
    "SOXX": {"label": "반도체 (iShares)",        "category": "tech_subindustry"},
    "SMH":  {"label": "반도체 (VanEck)",         "category": "tech_subindustry"},
    # AI/로봇
    "AIQ":  {"label": "AI & 빅데이터",            "category": "ai_robotics"},
    "BOTZ": {"label": "로봇 & AI",                "category": "ai_robotics"},
    "IRBO": {"label": "AI & 로봇 (iShares)",      "category": "ai_robotics"},
    # 클라우드/소프트웨어
    "SKYY": {"label": "클라우드 컴퓨팅",          "category": "tech_subindustry"},
    "IGV":  {"label": "소프트웨어",               "category": "tech_subindustry"},
    # 사이버보안
    "HACK": {"label": "사이버보안 (ETFMG)",       "category": "tech_subindustry"},
    "CIBR": {"label": "사이버보안 (First Trust)", "category": "tech_subindustry"},
    # 핀테크
    "FINX": {"label": "핀테크",                   "category": "fintech"},
    "ARKF": {"label": "핀테크 혁신 (ARK)",        "category": "fintech"},
    # 에너지 전환
    "TAN":  {"label": "태양광",                   "category": "energy_transition"},
    "LIT":  {"label": "리튬 & 배터리",            "category": "energy_transition"},
    "ICLN": {"label": "클린에너지",               "category": "energy_transition"},
    # 우주/방산
    "ITA":  {"label": "항공우주 & 방산",          "category": "space_defense"},
    # 바이오
    "XBI":  {"label": "바이오테크 (S&P)",         "category": "biotech"},
    "IBB":  {"label": "바이오테크 (NASDAQ)",      "category": "biotech"},
}

# RRG 4분면 한글 + 中文 번역 (Z1 신규 — 사용자 가독성)
QUADRANT_LABELS = {
    "LEADING":   {"ko": "선도",   "zh": "拉升", "desc": "이미 강세, 보유/추격"},
    "IMPROVING": {"ko": "개선",   "zh": "拉离", "desc": "★ 회복 진입, 매수 황금 시점"},
    "WEAKENING": {"ko": "약화",   "zh": "出货", "desc": "강세 식음, 익절/회피"},
    "LAGGING":   {"ko": "후행",   "zh": "建仓", "desc": "약세 지속, 관찰/예비"},
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

    # D89 근본 해결: period 사용 (시간대 무관)
    # LOOKBACK_DAYS=90 → "3mo" (~62 거래일 ≈ 90 캘린더일)

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

def _build_context(snapshot: dict, transitions: list[dict], header: str = "섹터 회전 (RRG) — 미국 11개 섹터 ETF") -> str:
    if not snapshot:
        return ""

    by_quad = {"LEADING": [], "IMPROVING": [], "WEAKENING": [], "LAGGING": []}
    for ticker, info in snapshot.items():
        quad = info.get("quadrant")
        if quad in by_quad:
            by_quad[quad].append(f"{ticker}({info.get('label', '')})")

    lines = [f"[{header}]"]
    # 4분면 출력: 한글/중문 번역 포함 (Z1 신규)
    for q in ["LEADING", "IMPROVING", "WEAKENING", "LAGGING"]:
        items = by_quad.get(q, [])
        if items:
            label_info = QUADRANT_LABELS.get(q, {})
            ko = label_info.get("ko", "")
            zh = label_info.get("zh", "")
            tag = f"{q} ({ko}/{zh})" if ko else q
            lines.append(f"  {tag}: {', '.join(items)}")

    if transitions:
        lines.append("")
        lines.append("[분면 전환]")
        for t in transitions:
            lines.append(f"  {t['ticker']} ({t['label']}): {t['transition']}")

    lines.append("")
    lines.append(
        "참고: LEADING(선도/拉升)=이미강함, IMPROVING(개선/拉离)=★회복진입(매수황금), "
        "WEAKENING(약화/出货)=강세식음, LAGGING(후행/建仓)=약세지속."
    )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════════════

def run_m2(etf_map: Optional[dict] = None, state: Optional[dict] = None) -> dict:
    """M2 섹터 RRG + 테마 RRG 실행 (Z1 확장).

    Args:
        etf_map: config/etf_map.json (선택 — 미사용 시 _DEFAULT_SECTOR_MAP)
        state: LangGraph state (m2_history 추출용)

    Returns:
        {
            "today_snapshot": dict (섹터 전용, 호환성 유지),
            "theme_snapshot": dict (테마 RRG, 신규),
            "transitions": list,
            "theme_transitions": list,
            "context_text": str (섹터 + 테마 통합),
        }
    """
    logger.info("=" * 50)
    logger.info("[M2] 섹터 + 테마 RRG 시작 (yfinance v3, Z1 확장)")

    # === 1. 섹터 RRG (기존 11개) ===
    sector_tickers = list(_DEFAULT_SECTOR_MAP.keys())
    all_sector = [BENCHMARK] + sector_tickers
    sector_closes = _fetch_closes(all_sector)

    if BENCHMARK not in sector_closes:
        logger.warning("[M2] %s 벤치마크 없음 — 빈 결과", BENCHMARK)
        return {"today_snapshot": {}, "theme_snapshot": {}, "transitions": [], "theme_transitions": [], "context_text": ""}

    benchmark_close = sector_closes.pop(BENCHMARK)

    sector_snapshot = {}
    if len(sector_closes) >= 2:
        sector_snapshot = _compute_rrg(sector_closes, benchmark_close)
        logger.info("[M2] 섹터 RRG: %d개 분류", len(sector_snapshot))

    # === 2. 테마 RRG (신규, 17개) ===
    theme_tickers = list(_DEFAULT_THEME_MAP.keys())
    theme_closes = _fetch_closes(theme_tickers)

    theme_snapshot = {}
    if len(theme_closes) >= 2:
        # _compute_rrg 는 _DEFAULT_SECTOR_MAP 만 lookup. 테마용 변형
        theme_snapshot = _compute_rrg_for_themes(theme_closes, benchmark_close)
        logger.info("[M2] 테마 RRG: %d개 분류", len(theme_snapshot))

    # 4분면 분포 로깅
    quad_count_s = {}
    for info in sector_snapshot.values():
        q = info.get("quadrant", "?")
        quad_count_s[q] = quad_count_s.get(q, 0) + 1
    quad_count_t = {}
    for info in theme_snapshot.values():
        q = info.get("quadrant", "?")
        quad_count_t[q] = quad_count_t.get(q, 0) + 1
    logger.info("[M2] 섹터 분포: %s | 테마 분포: %s", quad_count_s, quad_count_t)

    # === 3. 분면 전환 (섹터 + 테마 별도) ===
    m2_history = (state or {}).get("m2_history", {})
    transitions = _detect_transitions(sector_snapshot, m2_history)

    m2_theme_history = (state or {}).get("m2_theme_history", {})
    theme_transitions = _detect_transitions(theme_snapshot, m2_theme_history)

    if transitions:
        logger.info("[M2] 섹터 분면 전환: %d개", len(transitions))
    if theme_transitions:
        logger.info("[M2] 테마 분면 전환: %d개", len(theme_transitions))

    # === 4. context 통합 (섹터 + 테마) ===
    sector_ctx = _build_context(sector_snapshot, transitions, "섹터 회전 (RRG) — 미국 11개 섹터 ETF")
    theme_ctx = _build_context(theme_snapshot, theme_transitions, f"테마 회전 (RRG) — {len(_DEFAULT_THEME_MAP)}개 테마 ETF")

    context = sector_ctx + ("\n\n" + theme_ctx if theme_ctx else "")

    logger.info("[M2] 섹터 + 테마 RRG 완료")
    logger.info("=" * 50)

    return {
        "today_snapshot": sector_snapshot,
        "theme_snapshot": theme_snapshot,
        "transitions": transitions,
        "theme_transitions": theme_transitions,
        "context_text": context,
    }


# ═══════════════════════════════════════════════════════════
# 테마용 RRG 계산 (Z1 신규)
# _compute_rrg와 동일 로직이지만 _DEFAULT_THEME_MAP 사용
# ═══════════════════════════════════════════════════════════
def _compute_rrg_for_themes(theme_closes: dict, benchmark_close) -> dict:
    """테마 RRG 계산 (_compute_rrg 변형, _DEFAULT_THEME_MAP lookup)."""
    import pandas as pd
    result = {}
    for ticker, close in theme_closes.items():
        try:
            df = pd.DataFrame({"theme": close, "bench": benchmark_close}).dropna()
            if len(df) < 50:
                continue
            ratio = df["theme"] / df["bench"]
            ratio = ratio / ratio.mean() * 100
            momentum = ratio.pct_change(periods=5) * 100 + 100

            rs_ratio = float(ratio.iloc[-1])
            rs_momentum = float(momentum.iloc[-1])

            if rs_ratio >= 100 and rs_momentum >= 100:
                quadrant = "LEADING"
            elif rs_ratio >= 100 and rs_momentum < 100:
                quadrant = "WEAKENING"
            elif rs_ratio < 100 and rs_momentum < 100:
                quadrant = "LAGGING"
            else:
                quadrant = "IMPROVING"

            theme_info = _DEFAULT_THEME_MAP.get(ticker, {"label": ticker, "category": ""})
            result[ticker] = {
                "quadrant": quadrant,
                "label": theme_info["label"],
                "category": theme_info["category"],
                "ratio": round(rs_ratio, 2),
                "momentum": round(rs_momentum, 2),
            }
        except Exception as e:
            logger.warning("[M2] 테마 %s 계산 실패: %s", ticker, e)
            continue

    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    result = run_m2()
    print(result["context_text"])
