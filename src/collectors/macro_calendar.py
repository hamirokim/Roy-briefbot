"""
src/collectors/macro_calendar.py — 매크로 캘린더 + 결과 자동 수집

역할:
  - 이번 주 예정 이벤트 (FOMC, CPI, PCE, 실업 등) 로드
  - 이미 발표된 이벤트의 결과 자동 수집 (FRED 무료 API)
  - 시장 반응 데이터 (SPY/금리/달러 변화)
  - REGIME 에이전트의 LLM 해석 입력으로 사용

데이터 소스:
  - FRED API (https://fred.stlouisfed.org/docs/api/fred/) — 무료, 키 필요 없음 (rate limit 있음)
    ※ 키 발급 시 더 안정적: https://fred.stlouisfed.org/docs/api/api_key.html
  - Yahoo Finance chart API — 시장 반응 (SPY, ^TNX, USD/KRW)
  - config/calendar_2026.json — 예정 이벤트 마스터

원칙: 객관 데이터만 수집. 해석은 REGIME 에이전트의 LLM이 담당.
Q3 (Roy): "발표 후 해석 없음" 문제 해결 — 결과 데이터 + LLM 해석 가이드
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

# ── 설정 ──
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")  # 선택. 없으면 공개 엔드포인트 사용
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
TIMEOUT = 15
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BriefBot/2.0)"}

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


# ═══════════════════════════════════════════════════════════
# Settings 로드
# ═══════════════════════════════════════════════════════════

def _load_settings() -> dict:
    import yaml
    path = CONFIG_DIR / "ronin_settings.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ═══════════════════════════════════════════════════════════
# 캘린더 JSON 로드 (기존 M5 로직 재사용)
# ═══════════════════════════════════════════════════════════

def _calendar_path() -> Path:
    year = datetime.now().year
    candidates = [CONFIG_DIR / f"calendar_{year}.json", CONFIG_DIR / "calendar.json"]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def _load_calendar_json() -> dict:
    path = _calendar_path()
    if not path.exists():
        logger.warning("[macro] calendar JSON 없음: %s", path)
        return {"events": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("[macro] calendar JSON 파싱 실패: %s", e)
        return {"events": []}


def get_events_in_range(start_date: str, end_date: str) -> list[dict]:
    """[start_date, end_date] 범위 이벤트 반환 (날짜순)."""
    cal = _load_calendar_json()
    events = cal.get("events", [])
    result = []
    try:
        sd = datetime.strptime(start_date, "%Y-%m-%d").date()
        ed = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError as e:
        logger.error("[macro] 날짜 파싱 실패: %s", e)
        return []

    for evt in events:
        try:
            d = datetime.strptime(evt["date"], "%Y-%m-%d").date()
            if sd <= d <= ed:
                result.append(evt)
        except (ValueError, KeyError):
            continue
    return sorted(result, key=lambda e: e["date"])


# ═══════════════════════════════════════════════════════════
# FRED API — 발표된 매크로 데이터 결과 수집
# ═══════════════════════════════════════════════════════════

def fetch_fred_series(series_id: str, lookback_days: int = 30) -> Optional[list[dict]]:
    """FRED에서 최근 데이터 N일 가져오기.

    Returns:
        [{"date": "2026-04-19", "value": "4.25"}, ...]  최신순
    """
    end = datetime.now()
    start = end - timedelta(days=lookback_days)

    params = {
        "series_id": series_id,
        "file_type": "json",
        "observation_start": start.strftime("%Y-%m-%d"),
        "observation_end": end.strftime("%Y-%m-%d"),
        "sort_order": "desc",
    }
    if FRED_API_KEY:
        params["api_key"] = FRED_API_KEY

    try:
        resp = requests.get(FRED_BASE, params=params, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code != 200:
            logger.warning("[fred] %s HTTP %d", series_id, resp.status_code)
            return None
        data = resp.json()
        obs = data.get("observations", [])
        # 결측치(.) 제거
        clean = [o for o in obs if o.get("value", ".") != "."]
        return clean
    except Exception as e:
        logger.warning("[fred] %s 실패: %s", series_id, e)
        return None


def fetch_macro_indicators() -> dict[str, dict]:
    """settings에 정의된 FRED 시리즈 일괄 수집.

    Returns:
        {series_id: {"latest_date": "...", "latest_value": "...", "prev_value": "...", "change": ...}}
    """
    settings = _load_settings()
    series_list = settings["regime"]["macro_calendar"]["fred_series"]
    result = {}

    for series_id in series_list:
        obs = fetch_fred_series(series_id, lookback_days=90)
        if not obs or len(obs) < 1:
            continue
        try:
            latest = obs[0]
            latest_val = float(latest["value"])
            prev_val = float(obs[1]["value"]) if len(obs) > 1 else None
            change = (latest_val - prev_val) if prev_val is not None else None
            result[series_id] = {
                "latest_date": latest["date"],
                "latest_value": latest_val,
                "prev_value": prev_val,
                "change": round(change, 4) if change is not None else None,
                "obs_count": len(obs),
            }
        except (ValueError, KeyError, IndexError) as e:
            logger.warning("[fred] %s 파싱 실패: %s", series_id, e)
            continue

    logger.info("[fred] %d/%d 시리즈 수집", len(result), len(series_list))
    return result


# ═══════════════════════════════════════════════════════════
# Yahoo — 어제~오늘 시장 반응 (SPY, 10년물 금리, USD/KRW)
# ═══════════════════════════════════════════════════════════

def _fetch_yahoo_chart(symbol: str, range_str: str = "5d") -> Optional[list[float]]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_str}&interval=1d"
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
        if resp.status_code != 200:
            return None
        data = resp.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        quote = result[0].get("indicators", {}).get("quote", [{}])[0]
        closes = quote.get("close", [])
        valid = [float(c) for c in closes if c is not None]
        return valid if valid else None
    except Exception as e:
        logger.warning("[yahoo] %s 실패: %s", symbol, e)
        return None


def fetch_market_reaction() -> dict[str, dict]:
    """어제 발표 직후 시장 반응 — SPY, 10년물 금리, USD/KRW.

    Returns:
        {"SPY": {"yesterday_close": ..., "today_close": ..., "change_pct": ...}, ...}
    """
    symbols = {
        "SPY": "SPY",
        "TNX_10Y_YIELD": "%5ETNX",  # ^TNX
        "USDKRW": "USDKRW%3DX",     # USDKRW=X
        "DXY_USD_INDEX": "DX-Y.NYB",
        "VIX": "%5EVIX",
    }

    result = {}
    for label, symbol in symbols.items():
        closes = _fetch_yahoo_chart(symbol, range_str="5d")
        if not closes or len(closes) < 2:
            continue
        prev = closes[-2]
        curr = closes[-1]
        change_pct = ((curr - prev) / prev) * 100 if prev else None
        change_abs = curr - prev
        result[label] = {
            "yesterday_close": round(prev, 4),
            "today_close": round(curr, 4),
            "change_pct": round(change_pct, 3) if change_pct is not None else None,
            "change_abs": round(change_abs, 4),
        }

    logger.info("[market] %d개 자산 반응 수집", len(result))
    return result


# ═══════════════════════════════════════════════════════════
# 어제 발표 이벤트 + 결과 매칭 (REGIME LLM 입력용)
# ═══════════════════════════════════════════════════════════

def get_yesterday_announced_events() -> list[dict]:
    """어제 (T-1) 발표 일정에 있던 이벤트 + FRED/시장 결과 첨부."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    events = get_events_in_range(yesterday, yesterday)
    if not events:
        return []

    macro_data = fetch_macro_indicators()
    market_data = fetch_market_reaction()

    enriched = []
    for evt in events:
        evt_copy = dict(evt)
        # 이벤트 이름과 FRED 시리즈 매칭 (간단한 키워드 매칭)
        evt_name_lower = evt.get("name", "").lower()
        related_fred = {}
        if "fomc" in evt_name_lower or "rate" in evt_name_lower or "금리" in evt_name_lower:
            for s in ["FEDFUNDS", "DGS10"]:
                if s in macro_data:
                    related_fred[s] = macro_data[s]
        if "cpi" in evt_name_lower:
            if "CPIAUCSL" in macro_data:
                related_fred["CPIAUCSL"] = macro_data["CPIAUCSL"]
        if "pce" in evt_name_lower:
            if "PCE" in macro_data:
                related_fred["PCE"] = macro_data["PCE"]
        if "unemployment" in evt_name_lower or "실업" in evt_name_lower:
            if "UNRATE" in macro_data:
                related_fred["UNRATE"] = macro_data["UNRATE"]

        evt_copy["related_fred"] = related_fred
        evt_copy["market_reaction"] = market_data  # 모든 이벤트에 동일 시장 반응 첨부
        enriched.append(evt_copy)

    return enriched


# ═══════════════════════════════════════════════════════════
# 이번 주 예정 이벤트
# ═══════════════════════════════════════════════════════════

def get_upcoming_events(lookahead_days: int = 7) -> list[dict]:
    """오늘부터 N일 내 예정 이벤트."""
    today = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=lookahead_days)).strftime("%Y-%m-%d")
    return get_events_in_range(today, end_date)


# ═══════════════════════════════════════════════════════════
# CLI 테스트
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    print("\n=== 어제 발표 이벤트 ===")
    yesterday = get_yesterday_announced_events()
    print(json.dumps(yesterday, ensure_ascii=False, indent=2))

    print("\n=== 이번 주 예정 이벤트 ===")
    upcoming = get_upcoming_events()
    print(json.dumps(upcoming, ensure_ascii=False, indent=2))

    print("\n=== FRED 매크로 지표 ===")
    macro = fetch_macro_indicators()
    print(json.dumps(macro, ensure_ascii=False, indent=2))

    print("\n=== 시장 반응 ===")
    market = fetch_market_reaction()
    print(json.dumps(market, ensure_ascii=False, indent=2))
