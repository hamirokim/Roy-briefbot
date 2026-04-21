"""
src/collectors/global_universe.py — 4개국 종목 마스터 (v2 — pykrx 제거)

v2 (2026-04-21): pykrx KRX 차단 회피 — KR도 yfinance .KS 시드로 전환
v1 (2026-04-19): 4개국 (US Finviz / KR pykrx / JP+CN yfinance)

역할:
  - 미국/한국/일본/중국 종목 리스트 수집
  - 시총·거래대금 거시 필터로 압축 (Stage 1)
  - 캐시 7일

Q1: 본업 충실 — 메인포트/AUTO_TICKER 자동 제외 X
Q2: Daily 통일
Q3: 중국 ADR만
v2: KR 시드 종목 30개 + yfinance .KS (pykrx GitHub Actions 차단 회피)
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── 캐시 ──
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


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
# 미국 — Finviz 스크리너
# ═══════════════════════════════════════════════════════════

def _fetch_us_universe(market_cap_min: float, max_n: int) -> pd.DataFrame:
    try:
        from finvizfinance.screener.overview import Overview

        screener = Overview()
        filters = {"Market Cap.": "+Small (over $300mln)"}
        screener.set_filter(filters_dict=filters)
        df_raw = screener.screener_view(order="Market Cap.", ascend=False)

        if df_raw is None or df_raw.empty:
            logger.warning("[US] Finviz 스크리너 빈 결과")
            return pd.DataFrame()

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
        logger.error("[US] finvizfinance 미설치")
        return pd.DataFrame()
    except Exception as e:
        logger.error("[US] Finviz 실패: %s", e)
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
# 한국 (v2) — yfinance + 시드 종목 (pykrx 제거)
# ═══════════════════════════════════════════════════════════

# KOSPI 시총 상위 + KOSDAQ 시총 상위 (글로벌 인지도 + 거래량 충분)
_KR_SEED_TICKERS = [
    # KOSPI 대형주
    "005930.KS",  # 삼성전자
    "000660.KS",  # SK하이닉스
    "373220.KS",  # LG에너지솔루션
    "207940.KS",  # 삼성바이오로직스
    "005935.KS",  # 삼성전자우
    "005380.KS",  # 현대차
    "000270.KS",  # 기아
    "068270.KS",  # 셀트리온
    "035420.KS",  # NAVER
    "005490.KS",  # POSCO홀딩스
    "012330.KS",  # 현대모비스
    "028260.KS",  # 삼성물산
    "066570.KS",  # LG전자
    "035720.KS",  # 카카오
    "051910.KS",  # LG화학
    "006400.KS",  # 삼성SDI
    "055550.KS",  # 신한지주
    "105560.KS",  # KB금융
    "086790.KS",  # 하나금융지주
    "138040.KS",  # 메리츠금융지주
    "032830.KS",  # 삼성생명
    "017670.KS",  # SK텔레콤
    "030200.KS",  # KT
    "015760.KS",  # 한국전력
    "034730.KS",  # SK
    "009150.KS",  # 삼성전기
    "000810.KS",  # 삼성화재
    "036570.KS",  # 엔씨소프트
    "018260.KS",  # 삼성에스디에스
    "003550.KS",  # LG
    # KOSDAQ 대형주
    "247540.KQ",  # 에코프로비엠
    "086520.KQ",  # 에코프로
    "091990.KQ",  # 셀트리온헬스케어
    "196170.KQ",  # 알테오젠
    "041510.KQ",  # SM
    "035900.KQ",  # JYP Ent.
    "112040.KQ",  # 위메이드
    "263750.KQ",  # 펄어비스
    "066970.KQ",  # 엘앤에프
    "058470.KQ",  # 리노공업
]


def _fetch_kr_universe(market_cap_min_usd: float, max_n: int, fx_krw: float = 1471) -> pd.DataFrame:
    """KR 시드 종목 — yfinance (.KS / .KQ 접미사). v2 패치."""
    try:
        import yfinance as yf

        rows = []
        for ticker in _KR_SEED_TICKERS[:max_n]:
            try:
                info = yf.Ticker(ticker).info
                market_cap_krw = info.get("marketCap", 0)
                if not market_cap_krw:
                    continue
                # KRW로 받을 수도 USD로 받을 수도 — 큰 값이면 KRW로 가정
                if market_cap_krw > 1e10:  # 100억 이상 = KRW 기준
                    market_cap_usd = market_cap_krw / fx_krw
                else:
                    market_cap_usd = market_cap_krw
                if market_cap_usd < market_cap_min_usd:
                    continue

                rows.append({
                    "ticker": ticker,
                    "name": info.get("longName") or info.get("shortName") or ticker,
                    "sector": info.get("sector", ""),
                    "industry": info.get("industry", ""),
                    "market_cap": market_cap_usd,
                    "avg_volume_value": (info.get("averageVolume") or 0) * (info.get("currentPrice") or 0),
                    "country": "KR",
                })
                time.sleep(0.2)
            except Exception as e:
                logger.debug("[KR] %s 실패: %s", ticker, e)
                continue

        df = pd.DataFrame(rows).sort_values("market_cap", ascending=False).reset_index(drop=True) if rows else pd.DataFrame()
        logger.info("[KR] yfinance 시드: %d종목 (시총 ≥ $%.0fM)", len(df), market_cap_min_usd / 1e6)
        return df

    except ImportError:
        logger.error("[KR] yfinance 미설치")
        return pd.DataFrame()
    except Exception as e:
        logger.error("[KR] yfinance 실패: %s", e)
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
# 일본 — yfinance 시드
# ═══════════════════════════════════════════════════════════

_JP_SEED_TICKERS = [
    "7203.T", "6758.T", "9984.T", "8306.T", "6098.T", "9432.T", "8035.T",
    "6861.T", "4063.T", "7974.T", "9433.T", "8316.T", "8411.T", "8058.T",
    "6367.T", "6981.T", "4543.T", "6594.T", "8001.T", "4502.T", "6273.T",
    "7741.T", "4519.T", "9434.T", "4661.T", "7267.T", "4901.T", "6920.T",
    "8031.T", "6701.T", "6503.T", "9020.T", "9022.T", "6178.T", "4568.T",
    "4523.T", "8002.T", "5108.T", "4732.T", "2914.T", "4324.T",
    "9983.T", "4452.T", "6724.T", "6502.T", "9101.T", "5401.T", "8053.T",
    "8801.T", "8802.T", "1605.T", "3382.T", "5020.T", "6326.T", "7011.T",
    "7270.T", "8267.T", "4755.T", "6504.T",
]


def _fetch_jp_universe(market_cap_min_usd: float, max_n: int) -> pd.DataFrame:
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
                time.sleep(0.2)
            except Exception as e:
                logger.debug("[JP] %s 실패: %s", ticker, e)
                continue
        df = pd.DataFrame(rows).sort_values("market_cap", ascending=False).reset_index(drop=True) if rows else pd.DataFrame()
        logger.info("[JP] yfinance: %d종목", len(df))
        return df
    except ImportError:
        logger.error("[JP] yfinance 미설치")
        return pd.DataFrame()
    except Exception as e:
        logger.error("[JP] yfinance 실패: %s", e)
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
# 중국 ADR
# ═══════════════════════════════════════════════════════════

_CN_ADR_TICKERS = [
    "BABA", "JD", "PDD", "BIDU", "NIO", "LI", "XPEV", "TME", "BILI", "YMM",
    "TCOM", "VIPS", "EDU", "TAL", "BEKE", "ZH", "MNSO", "WB", "IQ", "DIDI",
    "LU", "FUTU", "TIGR", "NTES", "ATAT",
]


def _fetch_cn_universe(market_cap_min_usd: float, max_n: int) -> pd.DataFrame:
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
        df = pd.DataFrame(rows).sort_values("market_cap", ascending=False).reset_index(drop=True) if rows else pd.DataFrame()
        logger.info("[CN] ADR: %d종목", len(df))
        return df
    except Exception as e:
        logger.error("[CN] ADR 수집 실패: %s", e)
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
# 메인 진입점
# ═══════════════════════════════════════════════════════════

def fetch_global_universe(force_refresh: bool = False) -> pd.DataFrame:
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
    logger.info("[universe] 합본: %d종목", len(combined))
    return combined


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    df = fetch_global_universe(force_refresh=True)
    print(f"\n총 {len(df)}종목")
    print(df.groupby("country").size())
