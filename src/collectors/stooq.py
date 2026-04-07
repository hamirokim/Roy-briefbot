"""Stooq 일봉 CSV 수집기.

사용법:
    from src.collectors.stooq import fetch_daily_closes, fetch_daily_ohlcv

    # M2용: 종가만
    df = fetch_daily_closes("xlk.us", lookback=100)
    # df: pd.DataFrame  columns=[Date, Close]  sorted by Date asc

    # M3용: OHLCV 전체
    df = fetch_daily_ohlcv("xlk.us", lookback=260)
    # df: pd.DataFrame  columns=[Date, Open, High, Low, Close, Volume]
"""

from __future__ import annotations

import io
import time
from datetime import timedelta
from typing import Optional

import pandas as pd
import requests

from src.utils import now_kst

# ── 메모리 캐시 (같은 런 내 중복 호출 방지) ──
# key: (stooq_ticker, lookback) → raw OHLCV DataFrame
_cache: dict[tuple[str, int], pd.DataFrame] = {}

_STOOQ_URL = "https://stooq.com/q/d/l/"
_SLEEP_SEC = 0.25  # rate-limit 대응
_YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BriefBot/1.0)"}


def _stooq_to_yahoo(stooq_ticker: str) -> str:
    """Stooq 티커 → Yahoo 티커 변환. 예: 'xlk.us' → 'XLK', 'acwi.us' → 'ACWI'."""
    t = stooq_ticker.strip().lower()
    if t.endswith(".us"):
        return t[:-3].upper()
    if t.startswith("^"):
        return "%5E" + t[1:].upper()
    return t.upper()


def _fetch_yahoo_ohlcv(stooq_ticker: str, lookback: int) -> Optional[pd.DataFrame]:
    """Yahoo Finance chart API → Stooq 호환 OHLCV DataFrame. 실패 시 None."""
    yahoo_ticker = _stooq_to_yahoo(stooq_ticker)
    # lookback 영업일 → 달력일 환산 + 여유
    cal_days = int(lookback * 1.6) + 30
    range_map = {60: "3mo", 120: "6mo", 200: "1y", 300: "2y"}
    range_str = "1y"
    for threshold, rng in sorted(range_map.items()):
        if cal_days <= threshold * 1.6 + 30:
            range_str = rng
            break
    else:
        range_str = "2y"

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}?range={range_str}&interval=1d"
    for attempt in range(2):
        try:
            resp = requests.get(url, timeout=20, headers=_YAHOO_HEADERS)
            if resp.status_code != 200:
                return None
            data = resp.json()
            result = data.get("chart", {}).get("result", [])
            if not result:
                return None

            timestamps = result[0].get("timestamp", [])
            quote = result[0].get("indicators", {}).get("quote", [{}])[0]

            if not timestamps or not quote.get("close"):
                return None

            df = pd.DataFrame({
                "Date": pd.to_datetime(timestamps, unit="s", utc=True),
                "Open": quote.get("open", [None] * len(timestamps)),
                "High": quote.get("high", [None] * len(timestamps)),
                "Low": quote.get("low", [None] * len(timestamps)),
                "Close": quote.get("close", [None] * len(timestamps)),
                "Volume": quote.get("volume", [None] * len(timestamps)),
            })
            df["Date"] = df["Date"].dt.tz_localize(None).dt.normalize()
            df = df.dropna(subset=["Date", "Close"]).sort_values("Date").reset_index(drop=True)

            if len(df) < 20:
                print(f"[WARN] Yahoo 데이터 부족: {yahoo_ticker} ({len(df)}행)")
                return None

            print(f"[OK] Yahoo 폴백 성공: {stooq_ticker} → {yahoo_ticker} ({len(df)}행)")
            return df

        except requests.exceptions.Timeout:
            print(f"[WARN] Yahoo 타임아웃 ({yahoo_ticker}, 시도 {attempt+1}/2)")
            if attempt == 0:
                time.sleep(2)
        except Exception as e:
            print(f"[WARN] Yahoo 폴백 실패 ({yahoo_ticker}): {e}")
            return None
    return None


def _fetch_raw(
    stooq_ticker: str,
    lookback: int = 120,
    *,
    retries: int = 2,
) -> Optional[pd.DataFrame]:
    """Stooq에서 일봉 OHLCV 원본 수집 (내부용).

    Returns:
        pd.DataFrame with columns [Date, Open, High, Low, Close, Volume]
        sorted by Date ascending. 실패 시 None.
    """
    cache_key = (stooq_ticker, lookback)
    if cache_key in _cache:
        return _cache[cache_key]

    end_dt = now_kst()
    # lookback 영업일 ≈ lookback * 1.5 달력일 + 여유
    start_dt = end_dt - timedelta(days=int(lookback * 1.6) + 10)

    params = {
        "s": stooq_ticker,
        "d1": start_dt.strftime("%Y%m%d"),
        "d2": end_dt.strftime("%Y%m%d"),
        "i": "d",  # daily
    }

    for attempt in range(retries + 1):
        try:
            time.sleep(_SLEEP_SEC)
            resp = requests.get(_STOOQ_URL, params=params, timeout=15)
            resp.raise_for_status()
            text = resp.text.strip()

            # Stooq 에러 응답 체크 (HTML이 오면 CSV가 아님)
            if "<html" in text.lower() or "No data" in text:
                print(f"[WARN] Stooq 데이터 없음: {stooq_ticker}")
                return None

            df = pd.read_csv(io.StringIO(text))

            # 컬럼명 정규화 (Stooq: Date,Open,High,Low,Close,Volume)
            required = {"Date", "Close"}
            if not required.issubset(set(df.columns)):
                print(f"[WARN] Stooq 컬럼 이상: {stooq_ticker} -> {list(df.columns)}")
                return None

            df["Date"] = pd.to_datetime(df["Date"])

            # OHLCV 컬럼 정리 — 없는 컬럼은 NaN으로 채움
            for col in ["Open", "High", "Low", "Volume"]:
                if col not in df.columns:
                    df[col] = float("nan")

            df = (
                df[["Date", "Open", "High", "Low", "Close", "Volume"]]
                .dropna(subset=["Date", "Close"])
                .sort_values("Date")
                .reset_index(drop=True)
            )

            if len(df) < 20:
                print(f"[WARN] Stooq 데이터 부족: {stooq_ticker} ({len(df)}행)")
                return None

            _cache[cache_key] = df
            return df

        except requests.RequestException as e:
            print(f"[WARN] Stooq 요청 실패 ({stooq_ticker}, 시도 {attempt+1}): {e}")
            if attempt < retries:
                time.sleep(1)

    # ── Stooq 전부 실패 → Yahoo 폴백 ──
    print(f"[INFO] Stooq 실패 → Yahoo 폴백 시도: {stooq_ticker}")
    yahoo_df = _fetch_yahoo_ohlcv(stooq_ticker, lookback)
    if yahoo_df is not None:
        _cache[cache_key] = yahoo_df
        return yahoo_df

    return None


def fetch_daily_closes(
    stooq_ticker: str,
    lookback: int = 120,
    *,
    retries: int = 2,
) -> Optional[pd.DataFrame]:
    """Stooq에서 일봉 종가 수집 (M2 호환).

    Returns:
        pd.DataFrame with columns [Date(datetime), Close(float)]
        sorted by Date ascending. 실패 시 None.
    """
    raw = _fetch_raw(stooq_ticker, lookback, retries=retries)
    if raw is None:
        return None
    return raw[["Date", "Close"]].copy()


def fetch_daily_ohlcv(
    stooq_ticker: str,
    lookback: int = 260,
    *,
    retries: int = 2,
) -> Optional[pd.DataFrame]:
    """Stooq에서 일봉 OHLCV 전체 수집 (M3용).

    Returns:
        pd.DataFrame with columns [Date, Open, High, Low, Close, Volume]
        sorted by Date ascending. 실패 시 None.
    """
    raw = _fetch_raw(stooq_ticker, lookback, retries=retries)
    if raw is None:
        return None
    return raw.copy()


def clear_cache() -> None:
    """캐시 초기화 (테스트용)."""
    _cache.clear()
