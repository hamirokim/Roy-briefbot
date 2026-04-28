"""M3 역발상 필터 (Contrarian Screen) — Stage 2.

2단계 파이프라인:
  Step 1: Finviz 스크리너 → 동적 후보 수집 (급락+반등+시총)
  Step 2: Stooq OHLCV → 정밀 검증 (DD/반등/거래량/SMA)
  + Finviz 펀더멘탈 보강 (P/E, EPS, 인사이더)

Finviz 실패 시 → Stage 1 (Stooq 고정 유니버스) 자동 폴백.
스크리닝일 뿐, 매매 시그널이 아님.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.collectors.global_ohlcv import fetch_daily_ohlcv_yf as fetch_daily_ohlcv
from src.collectors.finviz import fetch_contrarian_candidates, fetch_fundamental_data, FINVIZ_AVAILABLE
from src.utils import now_kst, today_kst_str

# ── 환경변수 기반 설정 (튜닝 가능) ──
def _env_float(key: str, default: float) -> float:
    return float(os.environ.get(key, default))

def _env_int(key: str, default: int) -> int:
    return int(os.environ.get(key, default))

# DD 등급 기준 (52주 고점 대비)
DD_WATCH_PCT   = _env_float("M3_DD_WATCH_PCT", 20.0)
DD_ALERT_PCT   = _env_float("M3_DD_ALERT_PCT", 30.0)

# 반등 기준
BOUNCE_DAYS    = _env_int("M3_BOUNCE_DAYS", 5)
BOUNCE_MIN_PCT = _env_float("M3_BOUNCE_MIN_PCT", 0.0)

# 거래량 기준
VOL_SHORT_DAYS = _env_int("M3_VOL_SHORT_DAYS", 5)
VOL_LONG_DAYS  = _env_int("M3_VOL_LONG_DAYS", 20)
VOL_SURGE_MULT = _env_float("M3_VOL_SURGE_MULT", 1.5)

# SMA 기준
SMA_PERIOD     = _env_int("M3_SMA_PERIOD", 20)
SMA_PROX_PCT   = _env_float("M3_SMA_PROX_PCT", 3.0)

# 출력 제한
MAX_RESULTS    = _env_int("M3_MAX_RESULTS", 5)

# Finviz 동적 스크리닝 최대 수집
FINVIZ_MAX     = _env_int("M3_FINVIZ_MAX", 30)

# ── 프로젝트 루트 ──
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UNIVERSE_PATH = os.path.join(ROOT, "config", "universe.json")
ETF_MAP_PATH  = os.path.join(ROOT, "config", "etf_map.json")


# ====================================================================
# 유니버스 로드 (Stage 1 폴백용)
# ====================================================================

def _load_static_universe() -> list[dict]:
    """universe.json + etf_map.json에서 고정 스캔 대상 로드."""
    items: list[dict] = []

    # 개별주
    if os.path.exists(UNIVERSE_PATH):
        with open(UNIVERSE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for sector, info in data.get("stocks", {}).items():
            tickers = info.get("tickers", [])
            labels  = info.get("labels", [])
            for i, t in enumerate(tickers):
                lbl = labels[i] if i < len(labels) else t.replace(".us", "").upper()
                items.append({
                    "ticker": t.replace(".us", "").upper(),
                    "stooq_ticker": t,
                    "label": lbl,
                    "sector": sector,
                    "type": "stock",
                    "source": "static",
                })

    # ETF
    if os.path.exists(ETF_MAP_PATH):
        with open(ETF_MAP_PATH, "r", encoding="utf-8") as f:
            etf_map = json.load(f)
        for group_key in ["sectors_11", "countries_regions_16"]:
            group = etf_map.get(group_key, {})
            for sub_name, etfs in group.items():
                if isinstance(etfs, dict):
                    for region_name, etf_list in etfs.items():
                        if isinstance(etf_list, list):
                            for ei in etf_list:
                                t = ei.get("stooq", "")
                                if t:
                                    items.append({
                                        "ticker": t.replace(".us", "").upper(),
                                        "stooq_ticker": t,
                                        "label": ei.get("label", t),
                                        "sector": "ETF",
                                        "type": "etf",
                                        "source": "static",
                                    })
                elif isinstance(etfs, list):
                    for ei in etfs:
                        t = ei.get("stooq", "")
                        if t:
                            items.append({
                                "ticker": t.replace(".us", "").upper(),
                                "stooq_ticker": t,
                                "label": ei.get("label", t),
                                "sector": "ETF",
                                "type": "etf",
                                "source": "static",
                            })
    return items


# ====================================================================
# Finviz 동적 유니버스 (Stage 2)
# ====================================================================

def _load_finviz_universe() -> list[dict]:
    """Finviz 스크리너로 동적 후보 수집."""
    if not FINVIZ_AVAILABLE:
        return []

    raw = fetch_contrarian_candidates(max_results=FINVIZ_MAX)
    if not raw:
        return []

    items = []
    for r in raw:
        ticker = r.get("ticker", "")
        if not ticker:
            continue
        items.append({
            "ticker": ticker,
            "stooq_ticker": f"{ticker.lower()}.us",
            "label": r.get("company", ticker),
            "sector": r.get("sector", "Unknown"),
            "type": "stock",
            "source": "finviz",
            "finviz_meta": r,
        })

    return items


# ====================================================================
# Stooq 정밀 검증
# ====================================================================

def _screen_stooq(ticker: str, stooq_ticker: str) -> Optional[dict]:
    """Stooq OHLCV 기반 정밀 스크리닝."""
    df = fetch_daily_ohlcv(stooq_ticker, lookback=260)
    if df is None or len(df) < 60:
        return None

    close = df["Close"].values
    high  = df["High"].values
    volume = df["Volume"].values
    last_close = close[-1]

    # 1) 52주 고점 대비 DD
    high_52w = float(np.nanmax(high))
    if high_52w <= 0:
        return None
    dd_pct = ((high_52w - last_close) / high_52w) * 100.0

    if dd_pct < DD_WATCH_PCT:
        return None

    dd_grade = "ALERT" if dd_pct >= DD_ALERT_PCT else "WATCH"

    # 2) 최근 N일 반등
    if len(close) < BOUNCE_DAYS + 1:
        return None
    bounce_pct = ((last_close / close[-(BOUNCE_DAYS + 1)]) - 1.0) * 100.0
    if bounce_pct <= BOUNCE_MIN_PCT:
        return None

    # 3) 거래량 급증
    if len(volume) < VOL_LONG_DAYS or np.all(np.isnan(volume[-VOL_LONG_DAYS:])):
        vol_ratio = None
    else:
        vol_short = np.nanmean(volume[-VOL_SHORT_DAYS:])
        vol_long  = np.nanmean(volume[-VOL_LONG_DAYS:])
        if vol_long <= 0:
            vol_ratio = None
        else:
            vol_ratio = vol_short / vol_long
            if vol_ratio < VOL_SURGE_MULT:
                return None

    # 4) SMA 근접/돌파
    if len(close) < SMA_PERIOD:
        return None
    sma = float(np.mean(close[-SMA_PERIOD:]))
    if sma <= 0:
        return None
    sma_dist_pct = ((last_close - sma) / sma) * 100.0
    if sma_dist_pct < -SMA_PROX_PCT:
        return None

    return {
        "dd_pct": round(dd_pct, 1),
        "dd_grade": dd_grade,
        "bounce_pct": round(bounce_pct, 1),
        "vol_ratio": round(vol_ratio, 2) if vol_ratio is not None else None,
        "sma_dist_pct": round(sma_dist_pct, 1),
        "close": round(last_close, 2),
        "high_52w": round(high_52w, 2),
    }


# ====================================================================
# 펀더멘탈 보강
# ====================================================================

def _enrich_fundamental(candidate: dict) -> dict:
    """Finviz 펀더멘탈 데이터로 후보 정보 보강."""
    ticker = candidate["ticker"]
    fund = fetch_fundamental_data(ticker)

    if fund:
        candidate["pe"] = fund.get("pe")
        candidate["forward_pe"] = fund.get("forward_pe")
        candidate["eps_growth"] = fund.get("eps_growth_next_y")
        candidate["insider_trans"] = fund.get("insider_trans")
        candidate["short_float"] = fund.get("short_float")
        candidate["rsi14"] = fund.get("rsi14")
        candidate["earnings_date"] = fund.get("earnings_date")
        candidate["industry"] = fund.get("industry", "")
        candidate["has_fundamental"] = True
    else:
        candidate["has_fundamental"] = False

    return candidate


# ====================================================================
# M2 이중확인
# ====================================================================

def _check_m2_double_confirm(ticker: str, sector: str, state: dict) -> bool:
    """M2에서 해당 섹터 ETF가 LAGGING→IMPROVING 전환했는지 확인."""
    m2_history = state.get("m2_history", {})
    sorted_dates = sorted(m2_history.keys(), reverse=True)
    if len(sorted_dates) < 2:
        return False

    today_snap = m2_history.get(sorted_dates[0], {})
    yesterday_snap = m2_history.get(sorted_dates[1], {})

    _sector_etf_map = {
        "Technology": "xlk.us", "Health Care": "xlv.us",
        "Financials": "xlf.us", "Consumer Discretionary": "xly.us",
        "Communication Services": "xlc.us", "Industrials": "xli.us",
        "Consumer Staples": "xlp.us", "Energy": "xle.us",
        "Utilities": "xlu.us", "Real Estate": "xlre.us",
        "Materials": "xlb.us",
        # Finviz 섹터명 매핑 (Finviz는 섹터명이 다름)
        "Basic Materials": "xlb.us",
        "Healthcare": "xlv.us",
        "Financial": "xlf.us",
        "Consumer Cyclical": "xly.us",
        "Consumer Defensive": "xlp.us",
    }

    etf_ticker = _sector_etf_map.get(sector, "")
    if not etf_ticker:
        return False

    today_q = today_snap.get(etf_ticker, {}).get("quadrant", "")
    yesterday_q = yesterday_snap.get(etf_ticker, {}).get("quadrant", "")

    return yesterday_q == "LAGGING" and today_q == "IMPROVING"


# ====================================================================
# 메인 실행
# ====================================================================

def run_m3(state: dict) -> dict[str, Any]:
    """M3 역발상 필터 실행 (Stage 2).

    파이프라인:
    1. Finviz 동적 유니버스 수집 시도
    2. 고정 유니버스도 합산
    3. 중복 제거 (Finviz 우선)
    4. Stooq 정밀 검증
    5. 통과 종목에 Finviz 펀더멘탈 보강
    6. M2 이중확인 태그
    7. 정렬 + 출력
    """
    # ── 유니버스 수집 ──
    finviz_items = _load_finviz_universe()
    static_items = _load_static_universe()

    # 중복 제거: 같은 ticker면 Finviz 버전 우선
    seen_tickers: set[str] = set()
    merged: list[dict] = []

    for item in finviz_items:
        t = item["ticker"]
        if t not in seen_tickers:
            seen_tickers.add(t)
            merged.append(item)

    for item in static_items:
        t = item["ticker"]
        if t not in seen_tickers:
            seen_tickers.add(t)
            merged.append(item)

    finviz_count = len(finviz_items)
    static_count = len(static_items)
    total_count  = len(merged)

    print(f"[M3] 유니버스: Finviz {finviz_count} + Static {static_count} = 합산 {total_count}")

    if finviz_count == 0:
        print("[M3] ⚠️ Finviz 비활성 — Stage 1 폴백")

    # ── Stooq 정밀 검증 ──
    candidates: list[dict] = []
    scan_count = 0

    for item in merged:
        scan_count += 1
        result = _screen_stooq(item["ticker"], item["stooq_ticker"])
        if result is None:
            continue

        double_confirmed = _check_m2_double_confirm(
            item["ticker"], item["sector"], state
        )

        candidate = {
            "ticker": item["ticker"],
            "stooq_ticker": item["stooq_ticker"],
            "label": item["label"],
            "sector": item["sector"],
            "type": item["type"],
            "source": item["source"],
            "double_confirmed": double_confirmed,
            **result,
        }
        candidates.append(candidate)

    print(f"[M3] Stooq 검증: {scan_count}개 → {len(candidates)}개 통과")

    # ── 펀더멘탈 보강 (통과 종목만) ──
    if FINVIZ_AVAILABLE and candidates:
        print(f"[M3] 펀더멘탈 보강: {len(candidates)}개")
        for i, c in enumerate(candidates):
            if c["type"] == "stock":
                candidates[i] = _enrich_fundamental(c)

    # ── 정렬 ──
    candidates.sort(
        key=lambda x: (
            x["dd_grade"] == "ALERT",
            x["double_confirmed"],
            x.get("insider_trans") is not None and (x.get("insider_trans") or 0) > 0,
            x["dd_pct"],
        ),
        reverse=True,
    )
    candidates = candidates[:MAX_RESULTS]

    print(f"[M3] 최종: {len(candidates)}개")

    context_text  = _build_context(candidates, scan_count, finviz_count)
    telegram_text = _build_telegram(candidates, scan_count, finviz_count)

    return {
        "candidates": candidates,
        "context_text": context_text,
        "telegram_text": telegram_text,
        "scan_count": scan_count,
        "finviz_count": finviz_count,
    }


# ====================================================================
# 출력 포맷
# ====================================================================

def _fmt_fundamental(c: dict) -> str:
    """펀더멘탈 한 줄 요약."""
    if not c.get("has_fundamental"):
        return ""
    parts = []
    if c.get("pe") is not None:
        parts.append(f"P/E {c['pe']}")
    if c.get("forward_pe") is not None:
        parts.append(f"Fwd {c['forward_pe']}")
    if c.get("insider_trans") is not None:
        sign = "+" if c["insider_trans"] > 0 else ""
        parts.append(f"Insider {sign}{c['insider_trans']}%")
    if c.get("short_float") is not None:
        parts.append(f"Short {c['short_float']}%")
    if c.get("rsi14") is not None:
        parts.append(f"RSI {c['rsi14']}")
    return " | ".join(parts)


def _build_context(candidates: list[dict], scan_count: int, finviz_count: int) -> str:
    """LLM 컨텍스트 텍스트."""
    today = today_kst_str()
    source = "Finviz+Static" if finviz_count > 0 else "Static only"

    lines = [
        f"## CONTRARIAN SCREEN ({today})",
        f"Source: {source} | Scanned: {scan_count} | Passed: {len(candidates)}",
        f"Criteria: DD≥{DD_WATCH_PCT}% + {BOUNCE_DAYS}d bounce>0% "
        f"+ vol≥{VOL_SURGE_MULT}x + SMA({SMA_PERIOD}) ±{SMA_PROX_PCT}%",
        "",
    ]

    if not candidates:
        lines.append("No contrarian candidates. Normal — fewer = higher quality.")
        return "\n".join(lines)

    for c in candidates:
        dc_tag = " ⚡M2" if c["double_confirmed"] else ""
        vol_str = f"vol {c['vol_ratio']}x" if c["vol_ratio"] else "vol N/A"
        fund_str = _fmt_fundamental(c)
        fund_line = f"\n  Fund: {fund_str}" if fund_str else ""

        lines.append(
            f"• {c['ticker']} ({c['label']}) [{c['sector']}] via {c['source']}"
            f"\n  DD {c['dd_pct']}% [{c['dd_grade']}] | "
            f"{BOUNCE_DAYS}d +{c['bounce_pct']}% | {vol_str} | "
            f"SMA({SMA_PERIOD}) {c['sma_dist_pct']:+.1f}% | "
            f"${c['close']} (52wH ${c['high_52w']}){dc_tag}"
            f"{fund_line}"
        )

    lines.append("")
    lines.append("NOTE: Pre-screen only. Verify with R-ONE main indicator.")
    return "\n".join(lines)


def _build_telegram(candidates: list[dict], scan_count: int, finviz_count: int) -> str:
    """텔레그램 HTML 출력."""
    today = today_kst_str()
    src_label = "Finviz+고정" if finviz_count > 0 else "고정"

    parts = [f"<b>🔄 M3 역발상 필터</b>  <i>{today}</i>"]
    parts.append(f"소스: {src_label} | 스캔 {scan_count} → 통과 {len(candidates)}")
    parts.append("")

    if not candidates:
        parts.append("역발상 후보 없음")
        parts.append("<i>극단적 낙폭 + 반등 징후 없음. 정상.</i>")
        return "\n".join(parts)

    for i, c in enumerate(candidates, 1):
        dc_tag = " ⚡이중확인" if c["double_confirmed"] else ""
        grade_emoji = "🔴" if c["dd_grade"] == "ALERT" else "🟡"
        vol_str = f"거래량 {c['vol_ratio']}x" if c["vol_ratio"] else ""
        src_tag = "🌐" if c["source"] == "finviz" else "📋"

        parts.append(f"{i}. {src_tag} <b>{c['ticker']}</b> ({c['label']}){dc_tag}")
        parts.append(f"   {grade_emoji} DD {c['dd_pct']}% | 반등 +{c['bounce_pct']}% | {vol_str}")
        parts.append(f"   SMA20 {c['sma_dist_pct']:+.1f}% | ${c['close']} (52w高 ${c['high_52w']})")

        fund = _fmt_fundamental(c)
        if fund:
            parts.append(f"   📊 {fund}")
        parts.append("")

    parts.append("<i>⚠️ 스크리닝일 뿐 — 메인지표 확인 후 판단</i>")
    return "\n".join(parts)
