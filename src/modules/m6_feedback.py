"""
M6 피드백 루프 — SCOUT 후보 사후 성과 추적 (Z3-4 재설계, D86)
================================================================
역할: SCOUT 후보 (Track A 매집)의 사후 성과를 추적.
      후보 시점 대비 현재가 수익률 계산 → DIGEST 컨텍스트에 주입.

원칙:
  - 28일 (≈20영업일) 추적 후 자동 만료
  - 최대 50개 추적
  - 추적 종목 0개면 빈 컨텍스트 반환 (희소 원칙)
  - yfinance 단일화 (D32)
  - source = "SCOUT" (M3 폐기 D82 정합)

박제:
  - D82: m3_contrarian.py 폐기
  - D83: m4_tracker.py 폐기 (agents/guard.py 흡수)
  - D86 (이 파일): m6_feedback 재설계 = SCOUT 추적
  - D87: digest.py 컨텍스트 수신 자리 추가 (다음 작업)

위치: src/modules/m6_feedback.py
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from src.collectors.global_ohlcv import fetch_daily_closes_yf as fetch_daily_closes
from src.utils import now_kst, today_kst_str

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 환경변수
# ═══════════════════════════════════════════════════════════

TRACK_DAYS = int(os.getenv("M6_TRACK_DAYS", "28"))   # 캘린더일 기준 만료 (≈20영업일)
MAX_HISTORY = int(os.getenv("M6_MAX_HISTORY", "50")) # 최대 추적 종목 수 (옛 20 → 50)
FETCH_DELAY = float(os.getenv("M6_FETCH_DELAY", "0.3"))  # yfinance 요청 간격
MIN_DAYS_FOR_REPORT = int(os.getenv("M6_MIN_DAYS_FOR_REPORT", "3"))  # 최소 N일 경과 종목만 리포트


# ═══════════════════════════════════════════════════════════
# SCOUT 후보 → m6_history 엔트리 변환 (신규, M3 함수 대체)
# ═══════════════════════════════════════════════════════════

def scout_candidates_to_m6_entries(candidates: list[dict]) -> list[dict]:
    """SCOUT.run() candidates → m6_history 저장용 엔트리.

    SCOUT 후보 dict (scout.py line 469):
      {ticker, name, country, sector, market_cap, score, signals, track_d?, buy_questions?}

    m6_history entry:
      {ticker, name, country, sector, date_added, price_at_add, score, signal_keys, source: "SCOUT"}
    """
    today = today_kst_str()
    entries = []
    for c in candidates:
        ticker = c.get("ticker", "")
        if not ticker:
            continue

        # price_at_add: 신호 시점 종가가 후보 dict에 직접 없으므로 별도 fetch
        # (SCOUT 단계에서 row 정보 무시되어 close 미보존)
        # → 추가 시점에 _fetch_current_price 1회 호출
        price = _fetch_current_price(ticker)
        if price is None or price <= 0:
            logger.warning("[M6] %s: 추가 시점 가격 fetch 실패 — 스킵", ticker)
            continue

        sig_keys = list((c.get("signals") or {}).keys())
        track_d_match = ""
        td = c.get("track_d") or {}
        if td.get("is_theme_beneficiary"):
            matches = td.get("matches", [])
            track_d_match = ", ".join(str(m) for m in matches[:2])

        entries.append({
            "ticker": ticker,
            "name": c.get("name", "")[:50],
            "country": c.get("country", ""),
            "sector": c.get("sector", "")[:30],
            "date_added": today,
            "price_at_add": round(price, 4),
            "score": c.get("score", 0),
            "signal_keys": sig_keys,
            "track_d": track_d_match,
            "source": "SCOUT",
        })

    return entries


# ═══════════════════════════════════════════════════════════
# 만료 정리 + 중복 체크 (옛 함수 유지, TRACK_DAYS만 환경변수)
# ═══════════════════════════════════════════════════════════

def prune_history(history: list[dict]) -> list[dict]:
    """TRACK_DAYS 초과 항목 제거."""
    if not history:
        return []
    cutoff = (now_kst() - timedelta(days=TRACK_DAYS)).strftime("%Y-%m-%d")
    pruned = [h for h in history if h.get("date_added", "") >= cutoff]
    removed = len(history) - len(pruned)
    if removed > 0:
        logger.info("[M6] 만료 정리: %d개 제거 (cutoff=%s)", removed, cutoff)
    # MAX_HISTORY 초과 시 최근순 잘라냄
    if len(pruned) > MAX_HISTORY:
        pruned = sorted(pruned, key=lambda x: x.get("date_added", ""), reverse=True)[:MAX_HISTORY]
        logger.info("[M6] MAX_HISTORY 초과 → %d개로 자름", MAX_HISTORY)
    return pruned


def deduplicate_entries(existing: list[dict], new_entries: list[dict]) -> list[dict]:
    """이미 추적 중인 ticker는 추가하지 않음. 새로 추가될 entry만 반환."""
    existing_tickers = {h.get("ticker", "") for h in existing}
    fresh = []
    for entry in new_entries:
        t = entry.get("ticker", "")
        if t and t not in existing_tickers:
            fresh.append(entry)
            existing_tickers.add(t)
    if len(new_entries) - len(fresh) > 0:
        logger.info("[M6] 중복 제거: %d → %d (이미 추적 중)",
                    len(new_entries), len(fresh))
    return fresh


# ═══════════════════════════════════════════════════════════
# 가격 fetch + 정규화 (yfinance 단일화)
# ═══════════════════════════════════════════════════════════

def _normalize_closes(raw) -> pd.Series | None:
    """fetch_daily_closes 반환 → 숫자 Series (옛 m6/m7 방어 로직)."""
    if raw is None:
        return None
    if isinstance(raw, pd.DataFrame):
        close_col = None
        for col in raw.columns:
            if str(col).lower() == "close":
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
    """yfinance 최신 종가 1개 (5일 lookback)."""
    try:
        raw = fetch_daily_closes(ticker, lookback=5)
        series = _normalize_closes(raw)
        if series is not None and len(series) > 0:
            return float(series.iloc[-1])
    except Exception as e:
        logger.debug("[M6] %s 가격 fetch 실패: %s", ticker, e)
    return None


# ═══════════════════════════════════════════════════════════
# 성과 계산
# ═══════════════════════════════════════════════════════════

def _compute_performance(history: list[dict]) -> list[dict]:
    """각 추적 종목의 현재가 fetch → 수익률."""
    results = []
    for h in history:
        ticker = h.get("ticker", "")
        price_at_add = float(h.get("price_at_add", 0) or 0)
        if not ticker or price_at_add <= 0:
            continue

        current_price = _fetch_current_price(ticker)
        time.sleep(FETCH_DELAY)

        if current_price is None:
            logger.debug("[M6] %s: 현재가 X — 스킵", ticker)
            continue

        pnl_pct = ((current_price - price_at_add) / price_at_add) * 100.0

        try:
            d_added = datetime.strptime(h["date_added"], "%Y-%m-%d").date()
            days_held = (now_kst().date() - d_added).days
        except (ValueError, KeyError):
            days_held = 0

        results.append({
            "ticker": ticker,
            "name": h.get("name", ticker),
            "country": h.get("country", ""),
            "sector": h.get("sector", ""),
            "date_added": h.get("date_added", ""),
            "price_at_add": price_at_add,
            "current_price": round(current_price, 4),
            "pnl_pct": round(pnl_pct, 2),
            "days_held": days_held,
            "score": h.get("score", 0),
            "track_d": h.get("track_d", ""),
            "signal_keys": h.get("signal_keys", []),
        })

    return results


# ═══════════════════════════════════════════════════════════
# 컨텍스트 빌더 (DIGEST 텔레그램 + 시트 동시 사용)
# ═══════════════════════════════════════════════════════════

def _build_summary_text(results: list[dict]) -> str:
    """SCOUT 추적 요약 한 줄 (텔레그램용 압축)."""
    if not results:
        return ""
    eligible = [r for r in results if r["days_held"] >= MIN_DAYS_FOR_REPORT]
    if not eligible:
        return ""

    pnls = [r["pnl_pct"] for r in eligible]
    avg = sum(pnls) / len(pnls)
    winners = sum(1 for p in pnls if p > 0)
    best = max(eligible, key=lambda x: x["pnl_pct"])

    return (
        f"지난 {TRACK_DAYS}일 SCOUT 후보 {len(eligible)}개 추적 · "
        f"평균 {avg:+.1f}% · 상승 {winners}/{len(eligible)} · "
        f"최고 {best['ticker']} {best['pnl_pct']:+.1f}%"
    )


def _build_detailed_lines(results: list[dict]) -> list[str]:
    """SCOUT 추적 종목별 상세 (시트용)."""
    if not results:
        return []
    eligible = [r for r in results if r["days_held"] >= MIN_DAYS_FOR_REPORT]
    if not eligible:
        return []

    eligible.sort(key=lambda x: -x["pnl_pct"])

    lines = []
    for r in eligible:
        sign = "+" if r["pnl_pct"] >= 0 else ""
        td_text = f" [Track D: {r['track_d']}]" if r["track_d"] else ""
        lines.append(
            f"  • {r['ticker']} ({r['name'][:25]}): "
            f"{r['date_added']} ${r['price_at_add']:.2f} → "
            f"${r['current_price']:.2f} ({sign}{r['pnl_pct']}%, {r['days_held']}일){td_text}"
        )
    return lines


# ═══════════════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════════════

def run_m6(state: dict[str, Any], scout_candidates: list[dict] | None = None) -> dict[str, Any]:
    """M6 피드백 루프 실행.

    Parameters
    ----------
    state : dict
        LangGraph state. m6_history 필드 사용.
    scout_candidates : list[dict] or None
        오늘 SCOUT 결과. None이면 state["scout_out"]["candidates"]에서 가져옴.

    Returns
    -------
    dict: {
        "summary_text": str,        # 텔레그램용 한 줄
        "detailed_lines": list[str],# 시트용 종목별 상세
        "track_count": int,
        "results": list[dict],      # 디버그/분석용
    }
    """
    logger.info("=" * 50)
    logger.info("[M6] 피드백 루프 시작 (SCOUT 추적)")

    # 1. m6_history 로드
    history = state.get("m6_history") or []
    if not isinstance(history, list):
        logger.warning("[M6] m6_history 타입 이상 (%s) — 빈 list로 시작", type(history))
        history = []

    # 2. 만료 정리
    history = prune_history(history)
    logger.info("[M6] 정리 후 추적: %d개", len(history))

    # 3. 오늘 SCOUT 후보 추가 (있을 때만)
    if scout_candidates is None:
        scout_candidates = (state.get("scout_out") or {}).get("candidates") or []

    if scout_candidates:
        logger.info("[M6] SCOUT 후보 %d개 추가 검토", len(scout_candidates))
        new_entries = scout_candidates_to_m6_entries(scout_candidates)
        fresh = deduplicate_entries(history, new_entries)
        history.extend(fresh)
        logger.info("[M6] 신규 추가: %d개 (중복/실패 제외)", len(fresh))
    else:
        logger.info("[M6] 오늘 SCOUT 후보 없음 — 신규 추가 X")

    # 4. state 갱신 (성과 계산 전에도 history는 저장)
    state["m6_history"] = history

    # 5. 추적 종목 0개면 빈 컨텍스트 반환
    if not history:
        logger.info("[M6] 추적 종목 0 — 빈 컨텍스트 반환")
        logger.info("=" * 50)
        return {
            "summary_text": "",
            "detailed_lines": [],
            "track_count": 0,
            "results": [],
        }

    # 6. 현재가 fetch + 수익률 계산
    results = _compute_performance(history)
    logger.info("[M6] 성과 계산: %d/%d개 성공", len(results), len(history))

    # 7. 컨텍스트 빌드
    summary = _build_summary_text(results)
    detailed = _build_detailed_lines(results)

    if summary:
        logger.info("[M6] 요약: %s", summary)
    else:
        logger.info("[M6] 요약 빈 문자열 (모든 종목 < %d일 경과)", MIN_DAYS_FOR_REPORT)

    logger.info("[M6] 피드백 루프 완료")
    logger.info("=" * 50)

    return {
        "summary_text": summary,
        "detailed_lines": detailed,
        "track_count": len(results),
        "results": results,
    }


# ═══════════════════════════════════════════════════════════
# 단위 테스트 (직접 실행 시)
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    # 가짜 SCOUT 후보 (NVDA, AAPL)
    fake_candidates = [
        {
            "ticker": "NVDA",
            "name": "Nvidia Corp",
            "country": "US",
            "sector": "Technology",
            "score": 3,
            "signals": {"bb_squeeze": {}, "volume_compression": {}, "rrg_improving": {}},
            "track_d": {"is_theme_beneficiary": True, "matches": ["AI 반도체"]},
        },
    ]

    # 가짜 state (옛 history 포함)
    test_state = {
        "m6_history": [
            {
                "ticker": "AAPL",
                "name": "Apple Inc",
                "country": "US",
                "sector": "Technology",
                "date_added": (now_kst() - timedelta(days=10)).strftime("%Y-%m-%d"),
                "price_at_add": 195.50,
                "score": 3,
                "signal_keys": ["bb_squeeze", "rrg_leading"],
                "track_d": "",
                "source": "SCOUT",
            },
        ],
    }

    out = run_m6(test_state, scout_candidates=fake_candidates)
    print("\n=== M6 결과 ===")
    print(f"track_count: {out['track_count']}")
    print(f"summary: {out['summary_text']}")
    print("detailed:")
    for line in out["detailed_lines"]:
        print(line)
    print(f"\nupdated m6_history: {len(test_state['m6_history'])}개")
    for h in test_state["m6_history"]:
        print(f"  {h['ticker']} ({h['date_added']}, ${h['price_at_add']})")
