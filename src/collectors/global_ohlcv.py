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


# ═══════════════════════════════════════════════════════════
# 단순 종가 fetcher — m4_tracker / m6_feedback 용 (stooq 대체)
# v4.2 (2026-04-28): stooq 폐기 → yfinance 통일 (D52 정합)
# stooq DB가 NY 마감 후 ~3시간 늦게 갱신되어 KST 07:10 발송 시 1일 지연 발생.
# yfinance는 NY 마감 후 ~30분 내 갱신되어 최신 데이터 보장.
# ═══════════════════════════════════════════════════════════

def _stooq_to_yahoo_ticker(stooq_ticker: str) -> str:
    """Stooq 호환 티커 (xxx.us) → yfinance 티커 (XXX) 변환.

    호환성: 기존 m4_tracker/m6_feedback 가 'msft.us' 형식으로 호출하는 것 유지.
    """
    t = stooq_ticker.strip()
    if t.lower().endswith(".us"):
        return t[:-3].upper()
    if t.startswith("^"):
        return t  # ^VIX 같은 인덱스는 그대로
    return t.upper()


def fetch_daily_closes_yf(stooq_ticker: str, lookback: int = 30) -> Optional[pd.DataFrame]:
    """yfinance 단일 종목 일봉 종가 fetch (m4_tracker / m6_feedback 용).

    인터페이스: stooq.fetch_daily_closes 와 동일 (DataFrame [Date, Close]).
    내부: yfinance 직접 호출. 캐시 X (단일 호출, 빠름).

    Returns:
        pd.DataFrame [Date(datetime), Close(float)] sorted asc. 실패 시 None.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("[ohlcv] yfinance 미설치")
        return None

    yahoo_ticker = _stooq_to_yahoo_ticker(stooq_ticker)
    end = datetime.now()
    start = end - timedelta(days=int(lookback * 1.6) + 10)

    try:
        df = yf.download(
            yahoo_ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        if df is None or df.empty:
            logger.warning("[ohlcv yf] %s 빈 결과", yahoo_ticker)
            return None

        df = df.reset_index()
        # 다중 인덱스 칼럼 정리 (yfinance batch=False여도 가끔 발생)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

        if "Close" not in df.columns or "Date" not in df.columns:
            logger.warning("[ohlcv yf] %s 컬럼 이상: %s", yahoo_ticker, list(df.columns))
            return None

        out = df[["Date", "Close"]].dropna().reset_index(drop=True)
        out["Date"] = pd.to_datetime(out["Date"]).dt.tz_localize(None)
        return out

    except Exception as e:
        logger.warning("[ohlcv yf] %s 실패: %s", yahoo_ticker, e)
        return None


def fetch_daily_ohlcv_yf(stooq_ticker: str, lookback: int = 260) -> Optional[pd.DataFrame]:
    """yfinance 단일 종목 OHLCV fetch (m3_contrarian 용).

    인터페이스: stooq.fetch_daily_ohlcv 와 동일 (DataFrame [Date, Open, High, Low, Close, Volume]).

    Returns:
        pd.DataFrame [Date, Open, High, Low, Close, Volume] sorted asc. 실패 시 None.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("[ohlcv] yfinance 미설치")
        return None

    yahoo_ticker = _stooq_to_yahoo_ticker(stooq_ticker)
    end = datetime.now()
    start = end - timedelta(days=int(lookback * 1.6) + 10)

    try:
        df = yf.download(
            yahoo_ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        if df is None or df.empty:
            logger.warning("[ohlcv yf] %s 빈 결과", yahoo_ticker)
            return None

        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

        required = {"Date", "Open", "High", "Low", "Close", "Volume"}
        if not required.issubset(set(df.columns)):
            logger.warning("[ohlcv yf] %s OHLCV 컬럼 부족: %s", yahoo_ticker, list(df.columns))
            return None

        out = df[["Date", "Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Date", "Close"]).reset_index(drop=True)
        out["Date"] = pd.to_datetime(out["Date"]).dt.tz_localize(None)
        return out

    except Exception as e:
        logger.warning("[ohlcv yf] %s OHLCV 실패: %s", yahoo_ticker, e)
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    test_input = {
        "US": ["AAPL", "MSFT"],
        "KR": ["005930.KS"],
        "JP": ["7203.T"],
        "CN_ADR": ["BABA"],
    }
    result = fetch_ohlcv(test_input, lookback_days=60, use_cache=False)
    print(f"\n총 {len(result)}종목 수집")
