"""M3 역발상 필터 (Contrarian Screen).

"시장이 버리고 있는데 바닥 징후가 보이는" 종목을 잡아내는 모듈.
로이 메인지표의 arm 상태(눌림 후 진입 대기)와 같은 방향.

스크리닝일 뿐, 매매 시그널이 아님.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.collectors.stooq import fetch_daily_ohlcv
from src.utils import now_kst, today_kst_str

# ── 환경변수 기반 설정 (튜닝 가능) ──
def _env_float(key: str, default: float) -> float:
    return float(os.environ.get(key, default))

def _env_int(key: str, default: int) -> int:
    return int(os.environ.get(key, default))

# DD 등급 기준 (52주 고점 대비)
DD_WATCH_PCT   = _env_float("M3_DD_WATCH_PCT", 20.0)    # ≥20% = WATCH
DD_ALERT_PCT   = _env_float("M3_DD_ALERT_PCT", 30.0)    # ≥30% = ALERT

# 반등 기준
BOUNCE_DAYS    = _env_int("M3_BOUNCE_DAYS", 5)           # 최근 N일 수익률 체크
BOUNCE_MIN_PCT = _env_float("M3_BOUNCE_MIN_PCT", 0.0)    # 반등 최소 % (0 = 양수면 통과)

# 거래량 기준
VOL_SHORT_DAYS = _env_int("M3_VOL_SHORT_DAYS", 5)        # 단기 평균 거래량 기간
VOL_LONG_DAYS  = _env_int("M3_VOL_LONG_DAYS", 20)        # 장기 평균 거래량 기간
VOL_SURGE_MULT = _env_float("M3_VOL_SURGE_MULT", 1.5)    # 단기/장기 배수

# SMA 기준
SMA_PERIOD     = _env_int("M3_SMA_PERIOD", 20)           # SMA 기간
SMA_PROX_PCT   = _env_float("M3_SMA_PROX_PCT", 3.0)     # SMA 근접 기준 %

# 출력 제한
MAX_RESULTS    = _env_int("M3_MAX_RESULTS", 5)            # 최대 출력 종목 수

# ── 프로젝트 루트 ──
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UNIVERSE_PATH = os.path.join(ROOT, "config", "universe.json")
ETF_MAP_PATH  = os.path.join(ROOT, "config", "etf_map.json")


# ====================================================================
# 데이터 로드
# ====================================================================

def _load_universe() -> dict[str, list[dict]]:
    """universe.json + etf_map.json에서 스캔 대상 로드.

    Returns:
        {"Technology": [{"ticker": "aapl.us", "label": "Apple", "type": "stock"}, ...],
         "섹터": [{"ticker": "xlk.us", "label": "Technology", "type": "etf"}, ...]}
    """
    universe: dict[str, list[dict]] = {}

    # 1) 개별주 (universe.json)
    if os.path.exists(UNIVERSE_PATH):
        with open(UNIVERSE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for sector, info in data.get("stocks", {}).items():
            tickers = info.get("tickers", [])
            labels  = info.get("labels", [])
            items = []
            for i, t in enumerate(tickers):
                lbl = labels[i] if i < len(labels) else t.replace(".us", "").upper()
                items.append({"ticker": t, "label": lbl, "type": "stock"})
            universe[sector] = items

    # 2) ETF (etf_map.json) — 섹터 ETF만 (국가 ETF도 포함 가능)
    if os.path.exists(ETF_MAP_PATH):
        with open(ETF_MAP_PATH, "r", encoding="utf-8") as f:
            etf_map = json.load(f)

        for group_key in ["sectors_11", "countries_regions_16"]:
            group = etf_map.get(group_key, {})
            for sub_group_name, etfs in group.items():
                if isinstance(etfs, dict):
                    # dev_8 / em_8 같은 하위 그룹
                    for region_name, etf_list in etfs.items():
                        if isinstance(etf_list, list):
                            for etf_info in etf_list:
                                ticker = etf_info.get("stooq", "")
                                label  = etf_info.get("label", ticker)
                                if ticker:
                                    universe.setdefault("ETF", []).append(
                                        {"ticker": ticker, "label": label, "type": "etf"}
                                    )
                elif isinstance(etfs, list):
                    for etf_info in etfs:
                        ticker = etf_info.get("stooq", "")
                        label  = etf_info.get("label", ticker)
                        if ticker:
                            universe.setdefault("ETF", []).append(
                                {"ticker": ticker, "label": label, "type": "etf"}
                            )

    return universe


# ====================================================================
# 스크리닝 로직
# ====================================================================

def _screen_single(ticker: str) -> Optional[dict]:
    """단일 종목 역발상 스크리닝.

    Returns:
        통과 시: {dd_pct, dd_grade, bounce_pct, vol_ratio, sma_dist_pct, close, high_52w}
        미통과 시: None
    """
    df = fetch_daily_ohlcv(ticker, lookback=260)
    if df is None or len(df) < 60:
        return None

    close = df["Close"].values
    high  = df["High"].values
    volume = df["Volume"].values
    last_close = close[-1]

    # ── 1) 52주 고점 대비 DD ──
    high_52w = float(np.nanmax(high))
    if high_52w <= 0:
        return None
    dd_pct = ((high_52w - last_close) / high_52w) * 100.0

    if dd_pct < DD_WATCH_PCT:
        return None  # 낙폭 부족 — 역발상 대상 아님

    dd_grade = "ALERT" if dd_pct >= DD_ALERT_PCT else "WATCH"

    # ── 2) 최근 N일 반등 ──
    if len(close) < BOUNCE_DAYS + 1:
        return None
    bounce_pct = ((last_close / close[-(BOUNCE_DAYS + 1)]) - 1.0) * 100.0
    if bounce_pct <= BOUNCE_MIN_PCT:
        return None  # 반등 없음

    # ── 3) 거래량 급증 ──
    if len(volume) < VOL_LONG_DAYS or np.all(np.isnan(volume[-VOL_LONG_DAYS:])):
        # 거래량 데이터 없으면 이 조건은 패스 (ETF 일부 해당)
        vol_ratio = None
    else:
        vol_short = np.nanmean(volume[-VOL_SHORT_DAYS:])
        vol_long  = np.nanmean(volume[-VOL_LONG_DAYS:])
        if vol_long <= 0:
            vol_ratio = None
        else:
            vol_ratio = vol_short / vol_long
            if vol_ratio < VOL_SURGE_MULT:
                return None  # 거래량 급증 없음

    # ── 4) SMA 근접/돌파 ──
    if len(close) < SMA_PERIOD:
        return None
    sma = float(np.mean(close[-SMA_PERIOD:]))
    if sma <= 0:
        return None
    sma_dist_pct = ((last_close - sma) / sma) * 100.0

    # SMA 위에 있거나, 아래지만 근접(±N%) 이내
    sma_ok = sma_dist_pct > -SMA_PROX_PCT
    if not sma_ok:
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


def _check_m2_double_confirm(
    ticker: str,
    sector: str,
    state: dict,
) -> bool:
    """M2에서 해당 섹터 ETF가 LAGGING→IMPROVING 전환했는지 확인.

    ETF 타입이면 해당 ETF 자체의 전환을, 개별주면 섹터 ETF의 전환을 본다.
    """
    m2_history = state.get("m2_history", {})
    if len(m2_history) < 2:
        return False

    # 최근 2일 가져오기
    sorted_dates = sorted(m2_history.keys(), reverse=True)
    if len(sorted_dates) < 2:
        return False

    today_snap = m2_history.get(sorted_dates[0], {})
    yesterday_snap = m2_history.get(sorted_dates[1], {})

    # 섹터명 → ETF 티커 매핑 (간단 버전)
    _sector_etf_map = {
        "Technology": "xlk.us", "Health Care": "xlv.us",
        "Financials": "xlf.us", "Consumer Discretionary": "xly.us",
        "Communication Services": "xlc.us", "Industrials": "xli.us",
        "Consumer Staples": "xlp.us", "Energy": "xle.us",
        "Utilities": "xlu.us", "Real Estate": "xlre.us",
        "Materials": "xlb.us",
    }

    etf_ticker = _sector_etf_map.get(sector, ticker)
    today_q = today_snap.get(etf_ticker, {}).get("quadrant", "")
    yesterday_q = yesterday_snap.get(etf_ticker, {}).get("quadrant", "")

    return yesterday_q == "LAGGING" and today_q == "IMPROVING"


# ====================================================================
# 메인 실행
# ====================================================================

def run_m3(state: dict) -> dict[str, Any]:
    """M3 역발상 필터 실행.

    Returns:
        {
            "candidates": [...],        # 통과 종목 리스트
            "context_text": str,         # LLM 컨텍스트
            "telegram_text": str,        # 텔레그램 출력
            "scan_count": int,           # 스캔한 총 종목 수
        }
    """
    print("[M3] 유니버스 로드 중...")
    universe = _load_universe()

    total_tickers = sum(len(items) for items in universe.values())
    print(f"[M3] 스캔 대상: {total_tickers}개 ({len(universe)}개 그룹)")

    candidates: list[dict] = []
    scan_count = 0
    fail_count = 0

    for sector, items in universe.items():
        for item in items:
            ticker = item["ticker"]
            label  = item["label"]
            itype  = item["type"]
            scan_count += 1

            result = _screen_single(ticker)
            if result is None:
                continue

            # M2 이중확인
            double_confirmed = _check_m2_double_confirm(ticker, sector, state)

            display_ticker = ticker.replace(".us", "").upper()
            candidates.append({
                "ticker": display_ticker,
                "stooq_ticker": ticker,
                "label": label,
                "sector": sector,
                "type": itype,
                "double_confirmed": double_confirmed,
                **result,
            })

    # 정렬: ALERT > WATCH, 이중확인 우선, DD 높은 순
    candidates.sort(
        key=lambda x: (
            x["dd_grade"] == "ALERT",       # ALERT이 뒤 = 높은 우선순위
            x["double_confirmed"],           # 이중확인 뒤 = 높은 우선순위
            x["dd_pct"],                     # DD 높을수록 뒤 = 높은 우선순위
        ),
        reverse=True,
    )

    # 최대 출력 제한
    candidates = candidates[:MAX_RESULTS]

    # 로그
    print(f"[M3] 스캔 완료: {scan_count}개 중 {len(candidates)}개 통과")

    # 출력 생성
    context_text  = _build_context(candidates, scan_count)
    telegram_text = _build_telegram(candidates, scan_count)

    return {
        "candidates": candidates,
        "context_text": context_text,
        "telegram_text": telegram_text,
        "scan_count": scan_count,
    }


# ====================================================================
# 출력 포맷
# ====================================================================

def _build_context(candidates: list[dict], scan_count: int) -> str:
    """LLM 컨텍스트 텍스트 생성."""
    today = today_kst_str()
    lines = [
        f"## CONTRARIAN SCREEN ({today})",
        f"Scanned: {scan_count} tickers | Passed: {len(candidates)}",
        f"Criteria: DD≥{DD_WATCH_PCT}% from 52w high + {BOUNCE_DAYS}d bounce>0% "
        f"+ vol surge≥{VOL_SURGE_MULT}x + close within {SMA_PROX_PCT}% of SMA({SMA_PERIOD})",
        "",
    ]

    if not candidates:
        lines.append("No contrarian candidates found. "
                      "No extreme drawdown + recovery signals in current market.")
        lines.append("")
        lines.append("This is normal — fewer signals = higher quality screening.")
        return "\n".join(lines)

    for c in candidates:
        dc_tag = " ⚡M2-CONFIRMED" if c["double_confirmed"] else ""
        vol_str = f"vol surge {c['vol_ratio']}x" if c["vol_ratio"] else "vol N/A"
        lines.append(
            f"• {c['ticker']} ({c['label']}) [{c['sector']}] "
            f"— DD {c['dd_pct']}% [{c['dd_grade']}] | "
            f"{BOUNCE_DAYS}d bounce +{c['bounce_pct']}% | "
            f"{vol_str} | "
            f"SMA({SMA_PERIOD}) {c['sma_dist_pct']:+.1f}% | "
            f"Close ${c['close']}{dc_tag}"
        )

    lines.append("")
    lines.append("NOTE: This is a pre-screen, NOT a trade signal. "
                  "Verify with R-ONE main indicator before any entry.")
    return "\n".join(lines)


def _build_telegram(candidates: list[dict], scan_count: int) -> str:
    """텔레그램 HTML 출력 생성."""
    today = today_kst_str()
    parts = [f"<b>🔄 M3 역발상 필터</b>  <i>{today}</i>"]
    parts.append(f"스캔: {scan_count}개 → 통과: {len(candidates)}개")
    parts.append("")

    if not candidates:
        parts.append("역발상 후보 없음")
        parts.append("<i>극단적 낙폭 + 반등 징후 조합 없음. 정상.</i>")
        return "\n".join(parts)

    for i, c in enumerate(candidates, 1):
        dc_tag = " ⚡이중확인" if c["double_confirmed"] else ""
        grade_emoji = "🔴" if c["dd_grade"] == "ALERT" else "🟡"
        vol_str = f"거래량 {c['vol_ratio']}x" if c["vol_ratio"] else ""

        parts.append(
            f"{i}. <b>{c['ticker']}</b> ({c['label']}){dc_tag}"
        )
        parts.append(
            f"   {grade_emoji} DD {c['dd_pct']}% | "
            f"반등 +{c['bounce_pct']}% | "
            f"{vol_str}"
        )
        parts.append(
            f"   SMA20 {c['sma_dist_pct']:+.1f}% | "
            f"${c['close']} (52w高 ${c['high_52w']})"
        )
        parts.append("")

    parts.append("<i>⚠️ 스크리닝일 뿐 — 메인지표 확인 후 판단</i>")
    return "\n".join(parts)
