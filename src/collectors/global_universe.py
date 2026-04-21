"""
src/collectors/global_universe.py — 4개국 종목 마스터

역할:
  - 미국/한국/일본/중국 종목 리스트 수집
  - 시총·거래대금 거시 필터로 압축 (Stage 1)
  - 캐시 7일 (마스터 데이터는 매일 안 변함)

Q2 (Roy 지시): 글로벌 4개국 + 제외 없음 + 한도/효율 내 최대한
Q3 (Roy 지시): 중국은 ADR만 (akshare 본토는 매매 불가)
Daily 통일 (Q2): 모든 데이터 D 단위
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ── 캐시 ──
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── 설정 로드 ──
def _load_settings() -> dict:
    import yaml
    path = Path(__file__).resolve().parents[2] / "config" / "ronin_settings.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ═══════════════════════════════════════════════════════════
# 캐시 헬퍼
# ═══════════════════════════════════════════════════════════

def _cache_path(country: str) -> Path:
    return CACHE_DIR / f"universe_{country.lower()}.parquet"


def _is_cache_fresh(country: str, ttl_days: int) -> bool:
    p = _cache_path(country)
    if not p.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)
    return age < timedelta(days=ttl_days)


def _save_cache(country: str, df: pd.DataFrame) -> None:
    p = _cache_path(country)
    try:
        df.to_parquet(p, index=False)
        logger.info("[universe] %s 캐시 저장: %d종목", country, len(df))
    except Exception as e:
        logger.warning("[universe] %s 캐시 저장 실패: %s", country, e)


def _load_cache(country: str) -> Optional[pd.DataFrame]:
    p = _cache_path(country)
    try:
        return pd.read_parquet(p)
    except Exception as e:
        logger.warning("[universe] %s 캐시 로드 실패: %s", country, e)
        return None


# ═══════════════════════════════════════════════════════════
# 미국 — Finviz 스크리너 (시총 + 거래대금 필터 한 번에)
# ═══════════════════════════════════════════════════════════

def _fetch_us_universe(market_cap_min: float, max_n: int) -> pd.DataFrame:
    """Finviz 스크리너로 미국 종목 마스터 수집.

    columns: ticker, name, sector, industry, market_cap, avg_volume_value, country
    """
    try:
        from finvizfinance.screener.overview import Overview

        screener = Overview()
        # Finviz 시총 필터: Mid+ ($2B+), Large ($10B+), Mega ($200B+)
        # $1B 이상 = small_over (정확히 매핑되는 옵션 없으면 sma_over)
        filters = {"Market Cap.": "+Small (over $300mln)"}  # $1B 이상이면 small over로 충분
        screener.set_filter(filters_dict=filters)
        df_raw = screener.screener_view(order="Market Cap.", ascend=False)

        if df_raw is None or df_raw.empty:
            logger.warning("[US] Finviz 스크리너 빈 결과")
            return pd.DataFrame()

        # 컬럼 정규화
        df = pd.DataFrame({
            "ticker": df_raw.get("Ticker", "").astype(str).str.upper(),
            "name": df_raw.get("Company", ""),
            "sector": df_raw.get("Sector", ""),
            "industry": df_raw.get("Industry", ""),
            "market_cap": pd.to_numeric(df_raw.get("Market Cap", 0), errors="coerce"),
            "avg_volume_value": pd.to_numeric(df_raw.get("Avg Volume", 0), errors="coerce"),
            "country": "US",
        })
        df = df[df["market_cap"] >= market_cap_min].head(max_n).reset_index(drop=True)
        logger.info("[US] Finviz: %d종목 (시총 ≥ $%.0fB)", len(df), market_cap_min / 1e9)
        return df

    except ImportError:
        logger.error("[US] finvizfinance 미설치 — pip install finvizfinance")
        return pd.DataFrame()
    except Exception as e:
        logger.error("[US] Finviz 실패: %s", e)
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
# 한국 — pykrx (KRX 직접)
# ═══════════════════════════════════════════════════════════

def _fetch_kr_universe(market_cap_min_usd: float, max_n: int, fx_krw: float = 1480) -> pd.DataFrame:
    """KRX 종목 마스터 수집. 시총은 KRW → USD 변환.

    pykrx는 selenium 없이 KRX API 직접 호출 (안전).
    """
    try:
        from pykrx import stock

        today = datetime.now().strftime("%Y%m%d")
        # KOSPI + KOSDAQ 모든 종목
        rows = []
        for market in ("KOSPI", "KOSDAQ"):
            try:
                tickers = stock.get_market_ticker_list(today, market=market)
                cap_df = stock.get_market_cap_by_ticker(today, market=market)
                # 일평균 거래대금 = 60일 평균
                fundamental = stock.get_market_fundamental_by_ticker(today, market=market)

                for ticker in tickers:
                    name = stock.get_market_ticker_name(ticker)
                    market_cap_krw = cap_df.loc[ticker, "시가총액"] if ticker in cap_df.index else 0
                    market_cap_usd = market_cap_krw / fx_krw
                    if market_cap_usd < market_cap_min_usd:
                        continue
                    rows.append({
                        "ticker": f"{ticker}.KS" if market == "KOSPI" else f"{ticker}.KQ",
                        "name": name,
                        "sector": "",  # pykrx 기본 미제공, 별도 API 필요
                        "industry": market,
                        "market_cap": market_cap_usd,
                        "avg_volume_value": 0,  # 추후 보강
                        "country": "KR",
                    })
                logger.info("[KR] %s: %d종목 (시총 ≥ $%.0fM)", market, len(rows), market_cap_min_usd / 1e6)
            except Exception as e:
                logger.error("[KR] %s 수집 실패: %s", market, e)

        df = pd.DataFrame(rows).sort_values("market_cap", ascending=False).head(max_n).reset_index(drop=True)
        return df

    except ImportError:
        logger.error("[KR] pykrx 미설치 — pip install pykrx")
        return pd.DataFrame()
    except Exception as e:
        logger.error("[KR] pykrx 실패: %s", e)
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
# 일본 — yfinance + 닛케이 225 + TOPIX 100 시드
# ═══════════════════════════════════════════════════════════

# 닛케이 225 + TOPIX Core 30 시드 (시총 큰 일본 종목)
# 실전: TSE 전체는 유료 데이터 필요. 시드 + 점진 확장.
_JP_SEED_TICKERS = [
    # 닛케이 225 상위 + 글로벌 인지도
    "7203.T", "6758.T", "9984.T", "8306.T", "6098.T", "9432.T", "8035.T",
    "6861.T", "4063.T", "7974.T", "9433.T", "8316.T", "8411.T", "8058.T",
    "6367.T", "6981.T", "4543.T", "6594.T", "8001.T", "4502.T", "6273.T",
    "7741.T", "4519.T", "9434.T", "4661.T", "7267.T", "4901.T", "6920.T",
    "8031.T", "6701.T", "6503.T", "9020.T", "9022.T", "6178.T", "4568.T",
    "4523.T", "6178.T", "8002.T", "5108.T", "4732.T", "2914.T", "4324.T",
    # TOPIX Core 30 추가
    "9983.T", "4452.T", "6724.T", "6502.T", "9101.T", "5401.T", "8053.T",
    "8801.T", "8802.T", "1605.T", "3382.T", "5020.T", "6326.T", "7011.T",
    "7270.T", "8267.T", "4755.T", "6504.T",
]


def _fetch_jp_universe(market_cap_min_usd: float, max_n: int) -> pd.DataFrame:
    """일본 — yfinance 시드 기반.

    참고: TSE 전체 종목 무료 데이터 어려움. 시드 100개 시작 → 추후 확장.
    """
    try:
        import yfinance as yf

        rows = []
        for ticker in _JP_SEED_TICKERS[:max_n]:
            try:
                info = yf.Ticker(ticker).info
                market_cap = info.get("marketCap", 0)
                if market_cap < market_cap_min_usd:
                    continue
                rows.append({
                    "ticker": ticker,
                    "name": info.get("longName", ticker),
                    "sector": info.get("sector", ""),
                    "industry": info.get("industry", ""),
                    "market_cap": market_cap,
                    "avg_volume_value": info.get("averageVolume", 0) * info.get("currentPrice", 0),
                    "country": "JP",
                })
                time.sleep(0.2)  # rate limit
            except Exception as e:
                logger.debug("[JP] %s 실패: %s", ticker, e)
                continue
        df = pd.DataFrame(rows).sort_values("market_cap", ascending=False).reset_index(drop=True)
        logger.info("[JP] yfinance: %d종목", len(df))
        return df

    except ImportError:
        logger.error("[JP] yfinance 미설치")
        return pd.DataFrame()
    except Exception as e:
        logger.error("[JP] yfinance 실패: %s", e)
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
# 중국 — ADR만 (Q3 결정. 본토 A주 매매 불가 종목 제외)
# ═══════════════════════════════════════════════════════════

# 미국 상장 중국 ADR — 시총 큰 종목 위주
# 실전: 매매 가능 + 유동성 충분 종목만
_CN_ADR_TICKERS = [
    "BABA",   # Alibaba
    "JD",     # JD.com
    "PDD",    # Pinduoduo
    "BIDU",   # Baidu
    "NIO",    # NIO Auto
    "LI",     # Li Auto
    "XPEV",   # XPeng
    "TME",    # Tencent Music
    "BILI",   # Bilibili
    "YMM",    # Full Truck Alliance
    "TCOM",   # Trip.com
    "VIPS",   # Vipshop
    "EDU",    # New Oriental Education
    "TAL",    # TAL Education
    "BEKE",   # KE Holdings
    "ZH",     # Zhihu
    "MNSO",   # Miniso
    "WB",     # Weibo
    "IQ",     # iQIYI
    "DIDI",   # DiDi (OTC)
    "LU",     # Lufax
    "FUTU",   # Futu Holdings
    "TIGR",   # UP Fintech
    "NTES",   # NetEase
    "ATAT",   # Atour Lifestyle
]


def _fetch_cn_universe(market_cap_min_usd: float, max_n: int) -> pd.DataFrame:
    """중국 — 미국 상장 ADR만 (매매 가능 종목).

    데이터 소스: yfinance (미국 거래소 종목이라 동일하게 처리).
    """
    try:
        import yfinance as yf

        rows = []
        for ticker in _CN_ADR_TICKERS[:max_n]:
            try:
                info = yf.Ticker(ticker).info
                market_cap = info.get("marketCap", 0)
                if market_cap < market_cap_min_usd:
                    continue
                rows.append({
                    "ticker": ticker,
                    "name": info.get("longName", ticker),
                    "sector": info.get("sector", ""),
                    "industry": info.get("industry", ""),
                    "market_cap": market_cap,
                    "avg_volume_value": info.get("averageVolume", 0) * info.get("currentPrice", 0),
                    "country": "CN_ADR",
                })
                time.sleep(0.2)
            except Exception as e:
                logger.debug("[CN] %s 실패: %s", ticker, e)
                continue
        df = pd.DataFrame(rows).sort_values("market_cap", ascending=False).reset_index(drop=True)
        logger.info("[CN] ADR: %d종목", len(df))
        return df

    except Exception as e:
        logger.error("[CN] ADR 수집 실패: %s", e)
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
# 메인 진입점 — 4개국 합본
# ═══════════════════════════════════════════════════════════

def fetch_global_universe(force_refresh: bool = False) -> pd.DataFrame:
    """4개국 종목 마스터 통합 fetch.

    캐시 우선 (TTL 7일). force_refresh=True 시 재수집.

    Returns:
        DataFrame columns:
          ticker, name, sector, industry, market_cap, avg_volume_value, country
    """
    settings = _load_settings()
    cap_min = float(settings["scout"]["market_cap_min_usd"])
    cache_ttl = int(settings["cache"]["ticker_master_ttl_days"])
    enabled = settings["universe"]["enabled_countries"]
    max_per = settings["universe"]["max_per_country"]

    parts: list[pd.DataFrame] = []

    fetchers = {
        "US": lambda: _fetch_us_universe(cap_min, max_per.get("US", 2000)),
        "KR": lambda: _fetch_kr_universe(cap_min, max_per.get("KR", 600)),
        "JP": lambda: _fetch_jp_universe(cap_min, max_per.get("JP", 1500)),
        "CN": lambda: _fetch_cn_universe(cap_min, max_per.get("CN", 400)),
    }

    for country in enabled:
        if not force_refresh and _is_cache_fresh(country, cache_ttl):
            df = _load_cache(country)
            if df is not None and not df.empty:
                logger.info("[universe] %s 캐시 사용: %d종목", country, len(df))
                parts.append(df)
                continue

        # fetch fresh
        fetcher = fetchers.get(country)
        if fetcher is None:
            logger.warning("[universe] %s 수집기 없음 — 스킵", country)
            continue
        df = fetcher()
        if not df.empty:
            _save_cache(country, df)
            parts.append(df)

    if not parts:
        logger.error("[universe] 전 국가 수집 실패")
        return pd.DataFrame()

    combined = pd.concat(parts, ignore_index=True)
    logger.info("[universe] 합본: %d종목 (%s)", len(combined),
                ", ".join(f"{c}={len(p)}" for c, p in zip(enabled, parts)))
    return combined


# ═══════════════════════════════════════════════════════════
# CLI 테스트용
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    df = fetch_global_universe(force_refresh=True)
    print(f"\n총 {len(df)}종목")
    print(df.groupby("country").size())
    print("\n상위 20종목:")
    print(df.nlargest(20, "market_cap")[["ticker", "name", "country", "market_cap"]])
