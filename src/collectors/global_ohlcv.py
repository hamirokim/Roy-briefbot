"""
src/collectors/global_ohlcv.py — 4개국 일봉 OHLCV (v2 — pykrx 제거)

v2 (2026-04-21): pykrx 차단 회피 — 모든 국가 yfinance 통일
v1 (2026-04-19): US/JP/CN yfinance + KR pykrx

역할:
  - 종목 리스트 받아서 일봉 OHLCV 일괄 수집
  - 모든 국가 yfinance batch (KR도 .KS/.KQ 접미사로 처리)
  - 캐시 (당일 1회만 fetch)
  - SCOUT의 Stage 3 정밀 신호 계산용
"""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "ohlcv"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════
# 캐시 헬퍼 (당일 1회만 fetch)
# ═══════════════════════════════════════════════════════════

def _cache_path(ticker: str, country: str) -> Path:
    safe_ticker = ticker.replace("/", "_").replace(".", "_")
    today = datetime.now().strftime("%Y%m%d")
    return CACHE_DIR / f"{country}_{safe_ticker}_{today}.parquet"


def _load_cache(ticker: str, country: str) -> Optional[pd.DataFrame]:
    p = _cache_path(ticker, country)
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception:
        return None


def _save_cache(ticker: str, country: str, df: pd.DataFrame) -> None:
    p = _cache_path(ticker, country)
    try:
        df.to_parquet(p, index=False)
    except Exception as e:
        logger.warning("[ohlcv] %s 캐시 저장 실패: %s", ticker, e)


def cleanup_old_cache(days_old: int = 3) -> int:
    cutoff = datetime.now() - timedelta(days=days_old)
    removed = 0
    for f in CACHE_DIR.glob("*.parquet"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            continue
    if removed > 0:
        logger.info("[ohlcv] 캐시 정리: %d개 제거", removed)
    return removed


# ═══════════════════════════════════════════════════════════
# yfinance batch — 모든 국가 통일 (v2)
# ═══════════════════════════════════════════════════════════

def _fetch_yfinance_batch(tickers: list[str], lookback_days: int = 260) -> dict[str, pd.DataFrame]:
    if not tickers:
        return {}

    try:
        import yfinance as yf
    except ImportError:
        logger.error("[ohlcv] yfinance 미설치")
        return {}

    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    result: dict[str, pd.DataFrame] = {}

    CHUNK = 50
    for i in range(0, len(tickers), CHUNK):
        batch = tickers[i:i + CHUNK]
        batch_str = " ".join(batch)
        try:
            raw = yf.download(
                batch_str,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False,
                group_by="ticker",
                auto_adjust=False,
                threads=True,
            )

            if raw is None or raw.empty:
                logger.warning("[ohlcv yf] 청크 %d 빈 결과", i // CHUNK)
                continue

            if len(batch) == 1:
                df = raw.reset_index()
                df.columns = [c.lower() if isinstance(c, str) else (c[0].lower() if isinstance(c, tuple) else c) for c in df.columns]
                if "date" not in df.columns and "Date" in df.columns:
                    df = df.rename(columns={"Date": "date"})
                if not df.empty and all(c in df.columns for c in ["open", "high", "low", "close", "volume"]):
                    result[batch[0]] = df[["date", "open", "high", "low", "close", "volume"]].dropna()
            else:
                for ticker in batch:
                    if ticker not in raw.columns.get_level_values(0):
                        continue
                    sub = raw[ticker].reset_index()
                    sub.columns = [c.lower() if isinstance(c, str) else c for c in sub.columns]
                    if "date" not in sub.columns and "Date" in sub.columns:
                        sub = sub.rename(columns={"Date": "date"})
                    if all(c in sub.columns for c in ["open", "high", "low", "close", "volume"]):
                        sub = sub[["date", "open", "high", "low", "close", "volume"]].dropna()
                        if not sub.empty:
                            result[ticker] = sub

            time.sleep(1.0)

        except Exception as e:
            logger.error("[ohlcv yf] 청크 %d 실패: %s", i // CHUNK, e)
            continue

    logger.info("[ohlcv yf] %d/%d 종목 수집", len(result), len(tickers))
    return result


# ═══════════════════════════════════════════════════════════
# 메인 진입점 — 국가별 캐시 + yfinance 통일 (v2)
# ═══════════════════════════════════════════════════════════

def fetch_ohlcv(
    tickers_by_country: dict[str, list[str]],
    lookback_days: int = 260,
    use_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """4개국 종목 OHLCV 일괄 fetch — 모두 yfinance.

    KR 종목은 .KS/.KQ 접미사 그대로 사용 (yfinance가 한국 거래소 지원).
    """
    all_result: dict[str, pd.DataFrame] = {}

    for country, tickers in tickers_by_country.items():
        if not tickers:
            continue

        from_cache: dict[str, pd.DataFrame] = {}
        to_fetch: list[str] = []

        if use_cache:
            for t in tickers:
                cached = _load_cache(t, country)
                if cached is not None:
                    from_cache[t] = cached
                else:
                    to_fetch.append(t)
        else:
            to_fetch = list(tickers)

        if from_cache:
            logger.info("[ohlcv] %s 캐시 사용: %d종목", country, len(from_cache))

        # v2: 모든 국가 yfinance batch (pykrx 제거)
        if to_fetch:
            fetched = _fetch_yfinance_batch(to_fetch, lookback_days)
            for t, df in fetched.items():
                _save_cache(t, country, df)
            from_cache.update(fetched)

        all_result.update(from_cache)

    logger.info("[ohlcv] 합본: %d종목", len(all_result))
    return all_result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    test_input = {
        "US": ["AAPL", "MSFT"],
        "KR": ["005930.KS"],
        "JP": ["7203.T"],
        "CN_ADR": ["BABA"],
    }
    result = fetch_ohlcv(test_input, lookback_days=60, use_cache=False)
    print(f"\n총 {len(result)}종목 수집")    cutoff = datetime.now() - timedelta(days=days_old)
    removed = 0
    for f in CACHE_DIR.glob("*.parquet"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            continue
    if removed > 0:
        logger.info("[ohlcv] 캐시 정리: %d개 제거", removed)
    return removed


# ═══════════════════════════════════════════════════════════
# US/JP/CN_ADR — yfinance 배치 다운로드 (가장 안정적)
# ═══════════════════════════════════════════════════════════

def _fetch_yfinance_batch(tickers: list[str], lookback_days: int = 260) -> dict[str, pd.DataFrame]:
    """yfinance batch download — 한 번 호출로 여러 종목 동시 수집.

    Returns:
        dict[ticker, DataFrame(date, open, high, low, close, volume)]
    """
    if not tickers:
        return {}

    try:
        import yfinance as yf
    except ImportError:
        logger.error("[ohlcv] yfinance 미설치")
        return {}

    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    result: dict[str, pd.DataFrame] = {}

    # yfinance는 한 번에 너무 많이 요청하면 rate limit. 50개씩 청크
    CHUNK = 50
    for i in range(0, len(tickers), CHUNK):
        batch = tickers[i:i + CHUNK]
        batch_str = " ".join(batch)
        try:
            raw = yf.download(
                batch_str,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False,
                group_by="ticker",
                auto_adjust=False,
                threads=True,
            )

            if raw is None or raw.empty:
                logger.warning("[ohlcv yf] 청크 %d 빈 결과", i // CHUNK)
                continue

            # 단일 종목 vs 다중 종목 처리 분기
            if len(batch) == 1:
                df = raw.reset_index()
                df.columns = [c.lower() for c in df.columns]
                df = df.rename(columns={"date": "date"})
                if not df.empty:
                    result[batch[0]] = df[["date", "open", "high", "low", "close", "volume"]].dropna()
            else:
                # 멀티 인덱스 칼럼: (ticker, field)
                for ticker in batch:
                    if ticker not in raw.columns.get_level_values(0):
                        continue
                    sub = raw[ticker].reset_index()
                    sub.columns = [c.lower() for c in sub.columns]
                    sub = sub.rename(columns={"date": "date"})
                    sub = sub[["date", "open", "high", "low", "close", "volume"]].dropna()
                    if not sub.empty:
                        result[ticker] = sub

            time.sleep(1.0)  # rate limit 방지

        except Exception as e:
            logger.error("[ohlcv yf] 청크 %d 실패: %s", i // CHUNK, e)
            continue

    logger.info("[ohlcv yf] %d/%d 종목 수집", len(result), len(tickers))
    return result


# ═══════════════════════════════════════════════════════════
# KR — pykrx (한국 종목)
# ═══════════════════════════════════════════════════════════

def _fetch_pykrx_batch(tickers: list[str], lookback_days: int = 260) -> dict[str, pd.DataFrame]:
    """pykrx로 한국 종목 일봉 수집.

    Args:
        tickers: 'NNNNNN.KS' 또는 'NNNNNN.KQ' 형식

    Returns:
        dict[ticker, DataFrame]
    """
    if not tickers:
        return {}

    try:
        from pykrx import stock
    except ImportError:
        logger.error("[ohlcv kr] pykrx 미설치")
        return {}

    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")
    result: dict[str, pd.DataFrame] = {}

    for full_ticker in tickers:
        # 'NNNNNN.KS' → 'NNNNNN'
        ticker_code = full_ticker.split(".")[0]
        try:
            df_raw = stock.get_market_ohlcv(start_str, end_str, ticker_code)
            if df_raw is None or df_raw.empty:
                continue
            df = df_raw.reset_index()
            df.columns = ["date", "open", "high", "low", "close", "volume", "trade_value"]
            df = df[["date", "open", "high", "low", "close", "volume"]].dropna()
            df["date"] = pd.to_datetime(df["date"])
            if not df.empty:
                result[full_ticker] = df
            time.sleep(0.3)
        except Exception as e:
            logger.warning("[ohlcv kr] %s 실패: %s", full_ticker, e)
            continue

    logger.info("[ohlcv kr] %d/%d 종목 수집", len(result), len(tickers))
    return result


# ═══════════════════════════════════════════════════════════
# 메인 진입점 — 국가별 자동 라우팅 + 캐시
# ═══════════════════════════════════════════════════════════

def fetch_ohlcv(
    tickers_by_country: dict[str, list[str]],
    lookback_days: int = 260,
    use_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """4개국 종목 OHLCV 일괄 fetch.

    Args:
        tickers_by_country: {"US": [...], "KR": [...], "JP": [...], "CN_ADR": [...]}
        lookback_days: 과거 N일 데이터
        use_cache: 당일 캐시 우선 사용

    Returns:
        dict[ticker, DataFrame(date, open, high, low, close, volume)]
    """
    all_result: dict[str, pd.DataFrame] = {}

    for country, tickers in tickers_by_country.items():
        if not tickers:
            continue

        # 캐시 분리
        from_cache: dict[str, pd.DataFrame] = {}
        to_fetch: list[str] = []

        if use_cache:
            for t in tickers:
                cached = _load_cache(t, country)
                if cached is not None:
                    from_cache[t] = cached
                else:
                    to_fetch.append(t)
        else:
            to_fetch = list(tickers)

        if from_cache:
            logger.info("[ohlcv] %s 캐시 사용: %d종목", country, len(from_cache))

        # 국가별 라우팅
        if to_fetch:
            if country == "KR":
                fetched = _fetch_pykrx_batch(to_fetch, lookback_days)
            else:  # US, JP, CN_ADR — 모두 yfinance
                fetched = _fetch_yfinance_batch(to_fetch, lookback_days)

            # 캐시 저장
            for t, df in fetched.items():
                _save_cache(t, country, df)

            from_cache.update(fetched)

        all_result.update(from_cache)

    logger.info("[ohlcv] 합본: %d종목", len(all_result))
    return all_result


# ═══════════════════════════════════════════════════════════
# CLI 테스트용
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    # 테스트: 4개국 각 1~2종목
    test_input = {
        "US": ["AAPL", "MSFT"],
        "KR": ["005930.KS"],  # 삼성전자
        "JP": ["7203.T"],     # Toyota
        "CN_ADR": ["BABA"],
    }
    result = fetch_ohlcv(test_input, lookback_days=60, use_cache=False)
    print(f"\n총 {len(result)}종목 수집")
    for ticker, df in result.items():
        print(f"\n{ticker}: {len(df)}일")
        print(df.tail(3))
