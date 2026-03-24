"""Stooq 일봉 CSV 수집기.

사용법:
    from src.collectors.stooq import fetch_daily_closes
    df = fetch_daily_closes("xlk.us", lookback=100)
    # df: pd.DataFrame  columns=[Date, Close]  sorted by Date asc
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
_cache: dict[str, pd.DataFrame] = {}

_STOOQ_URL = "https://stooq.com/q/d/l/"
_SLEEP_SEC = 0.25  # rate-limit 대응


def fetch_daily_closes(
    stooq_ticker: str,
    lookback: int = 120,
    *,
    retries: int = 2,
) -> Optional[pd.DataFrame]:
    """Stooq에서 일봉 종가 수집.

    Returns:
        pd.DataFrame with columns [Date(datetime), Close(float)]
        sorted by Date ascending. 실패 시 None.
    """
    if stooq_ticker in _cache:
        return _cache[stooq_ticker]

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

            # 컬럼명 정규화 (Stooq은 Date,Open,High,Low,Close,Volume)
            if "Date" not in df.columns or "Close" not in df.columns:
                print(f"[WARN] Stooq 컬럼 이상: {stooq_ticker} -> {list(df.columns)}")
                return None

            df["Date"] = pd.to_datetime(df["Date"])
            df = df[["Date", "Close"]].dropna().sort_values("Date").reset_index(drop=True)

            if len(df) < 20:
                print(f"[WARN] Stooq 데이터 부족: {stooq_ticker} ({len(df)}행)")
                return None

            _cache[stooq_ticker] = df
            return df

        except requests.RequestException as e:
            print(f"[WARN] Stooq 요청 실패 ({stooq_ticker}, 시도 {attempt+1}): {e}")
            if attempt < retries:
                time.sleep(1)

    return None


def clear_cache() -> None:
    """캐시 초기화 (테스트용)."""
    _cache.clear()
