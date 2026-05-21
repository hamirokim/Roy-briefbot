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
Q3: 중국 ADR/HK/A주 주요주
v2: KR 시드 종목 30개 + yfinance .KS (pykrx GitHub Actions 차단 회피)
v3: US 공식 심볼, KR Naver fallback, JPX 공식 목록, CN AkShare optional + yfinance fallback
"""

import io
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
CACHE_VERSION = "v3"

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NASDAQ_OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
NAVER_MARKET_SUM_URL = "https://finance.naver.com/sise/sise_market_sum.naver"
JPX_LISTED_XLS_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"

# Free-source universe collection only needs rough USD normalization for filtering/sorting.
# Fresh FX comes from REGIME elsewhere; here we avoid treating JPY/HKD/CNY market caps as USD.
FX_JPY_PER_USD = 155.0
FX_HKD_PER_USD = 7.8
FX_CNY_PER_USD = 7.2


def _load_settings() -> dict:
    import yaml
    path = Path(__file__).resolve().parents[2] / "config" / "ronin_settings.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ═══════════════════════════════════════════════════════════
# 캐시 헬퍼
# ═══════════════════════════════════════════════════════════

def _cache_path(country: str) -> Path:
    return CACHE_DIR / f"universe_{country.lower()}_{CACHE_VERSION}.parquet"


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


def _read_pipe_text_table(url: str) -> pd.DataFrame:
    """Nasdaq Trader pipe-delimited text table loader."""
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    lines = [
        line for line in resp.text.splitlines()
        if line and not line.startswith("File Creation Time")
    ]
    if not lines:
        return pd.DataFrame()
    return pd.read_csv(io.StringIO("\n".join(lines)), sep="|")


def _fetch_us_official_symbols() -> pd.DataFrame:
    """미국 공식 상장 심볼 목록.

    Source: Nasdaq Trader Symbol Directory
    - nasdaqlisted.txt: Nasdaq-listed issues
    - otherlisted.txt: NYSE/NYSE American/other exchange issues
    """
    parts = []
    try:
        nasdaq = _read_pipe_text_table(NASDAQ_LISTED_URL)
        if not nasdaq.empty:
            nasdaq = nasdaq[
                (nasdaq.get("Test Issue", "N") == "N")
                & (nasdaq.get("ETF", "N") != "Y")
            ]
            parts.append(pd.DataFrame({
                "ticker": nasdaq["Symbol"].astype(str).str.upper(),
                "name": nasdaq["Security Name"].astype(str),
                "exchange": "NASDAQ",
                "official_source": "nasdaqtrader:nasdaqlisted",
            }))
    except Exception as e:
        logger.warning("[US] Nasdaq listed 공식 목록 실패: %s", e)

    try:
        other = _read_pipe_text_table(NASDAQ_OTHER_LISTED_URL)
        if not other.empty:
            other = other[
                (other.get("Test Issue", "N") == "N")
                & (other.get("ETF", "N") != "Y")
            ]
            symbol_col = "ACT Symbol" if "ACT Symbol" in other.columns else "NASDAQ Symbol"
            parts.append(pd.DataFrame({
                "ticker": other[symbol_col].astype(str).str.upper(),
                "name": other["Security Name"].astype(str),
                "exchange": other.get("Exchange", ""),
                "official_source": "nasdaqtrader:otherlisted",
            }))
    except Exception as e:
        logger.warning("[US] Other listed 공식 목록 실패: %s", e)

    if not parts:
        return pd.DataFrame()

    df = pd.concat(parts, ignore_index=True)
    df = df[~df["ticker"].str.contains(r"[$^/]", regex=True, na=False)]
    name_lower = df["name"].astype(str).str.lower()
    exclude_name = (
        name_lower.str.contains("warrant", na=False)
        | name_lower.str.contains(" right", na=False)
        | name_lower.str.contains("unit", na=False)
        | name_lower.str.contains("preferred", na=False)
        | name_lower.str.contains("acquisition corp", na=False)
        | name_lower.str.contains("blank check", na=False)
    )
    df = df[~exclude_name]
    df = df.drop_duplicates("ticker").reset_index(drop=True)
    logger.info("[US] Nasdaq Trader 공식 심볼: %d개", len(df))
    return df


# ═══════════════════════════════════════════════════════════
# 미국 — Finviz 스크리너
# ═══════════════════════════════════════════════════════════

def _fetch_us_universe(market_cap_min: float, max_n: int) -> pd.DataFrame:
    official = _fetch_us_official_symbols()
    official_symbols = set(official["ticker"]) if not official.empty else set()

    try:
        from finvizfinance.screener.overview import Overview

        screener = Overview()
        filters = {"Market Cap.": "+Small (over $300mln)"}
        screener.set_filter(filters_dict=filters)
        df_raw = screener.screener_view(
            order="Market Cap.",
            ascend=False,
            limit=max_n,
            verbose=0,
            sleep_sec=0.1,
        )

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
            "source": "finviz+nasdaqtrader" if official_symbols else "finviz",
        })
        if official_symbols:
            before = len(df)
            df = df[df["ticker"].isin(official_symbols)]
            logger.info("[US] 공식 심볼 교차검증: %d → %d", before, len(df))
        df = df[df["market_cap"] >= market_cap_min].head(max_n).reset_index(drop=True)
        logger.info("[US] Finviz: %d종목 (시총 ≥ $%.0fB)", len(df), market_cap_min / 1e9)
        return df

    except ImportError:
        logger.error("[US] finvizfinance 미설치")
        return pd.DataFrame()
    except Exception as e:
        logger.error("[US] Finviz 실패: %s", e)
        if official.empty:
            return pd.DataFrame()
        fallback = official.head(max_n).copy()
        fallback["sector"] = ""
        fallback["industry"] = ""
        fallback["market_cap"] = 0.0
        fallback["avg_volume_value"] = 0.0
        fallback["country"] = "US"
        fallback["source"] = "nasdaqtrader:fallback_no_cap"
        logger.warning("[US] Finviz 실패로 공식 심볼 fallback 사용: %d종목", len(fallback))
        return fallback


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
    """KR universe collection.

    Naver market-cap pages are the primary free path in this runtime. pykrx is
    kept as a fallback because the KRX endpoint often returns empty/blocked
    results in GitHub Actions and local runs.
    """
    naver_df = _fetch_kr_universe_naver(market_cap_min_usd, max_n, fx_krw)
    if not naver_df.empty:
        return naver_df

    pykrx_df = _fetch_kr_universe_pykrx(market_cap_min_usd, max_n, fx_krw)
    if not pykrx_df.empty:
        return pykrx_df

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
                    "source": "yfinance_seed_fallback",
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


def _parse_int_text(value: str) -> int:
    try:
        cleaned = str(value).replace(",", "").replace("%", "").strip()
        if cleaned in ("", "-", "nan"):
            return 0
        return int(float(cleaned))
    except Exception:
        return 0


def _parse_float_text(value) -> float:
    try:
        cleaned = str(value).replace(",", "").replace("%", "").strip()
        if cleaned in ("", "-", "nan", "None"):
            return 0.0
        return float(cleaned)
    except Exception:
        return 0.0


def _fetch_kr_universe_naver(market_cap_min_usd: float, max_n: int, fx_krw: float = 1471) -> pd.DataFrame:
    """Naver Finance 시총 상위 fallback.

    KRX 공식 endpoint가 403 또는 빈 결과일 때 쓰는 무료 보조 소스다.
    시총 상위 + 거래량을 가져와 yfinance용 .KS/.KQ 티커로 변환한다.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("[KR] beautifulsoup4 미설치 — Naver fallback 불가")
        return pd.DataFrame()

    rows = []
    # Naver: sosok=0 KOSPI, sosok=1 KOSDAQ, page당 50개.
    pages_per_market = max(1, min(10, (max_n // 2 + 49) // 50 + 1))
    for sosok, market, suffix in [(0, "KOSPI", ".KS"), (1, "KOSDAQ", ".KQ")]:
        for page in range(1, pages_per_market + 1):
            try:
                resp = requests.get(
                    NAVER_MARKET_SUM_URL,
                    params={"sosok": sosok, "page": page},
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=15,
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                found = 0
                for tr in soup.select("table.type_2 tr"):
                    a = tr.select_one("a.tltle")
                    if not a:
                        continue
                    href = a.get("href", "")
                    if "code=" not in href:
                        continue
                    code = href.split("code=")[-1].strip()[:6]
                    cols = [td.get_text(strip=True) for td in tr.select("td")]
                    if len(cols) < 10:
                        continue
                    name = a.get_text(strip=True)
                    if any(token in name.upper() for token in ["ETF", "ETN", "TIGER", "KODEX", "ACE ", "SOL ", "RISE ", "KBSTAR", "HANARO"]):
                        continue
                    price_krw = _parse_int_text(cols[2])
                    market_cap_krw = _parse_int_text(cols[6]) * 100_000_000
                    volume = _parse_int_text(cols[9])
                    market_cap_usd = market_cap_krw / fx_krw if market_cap_krw else 0
                    if market_cap_usd < market_cap_min_usd:
                        continue
                    rows.append({
                        "ticker": f"{code}{suffix}",
                        "name": name,
                        "sector": "",
                        "industry": market,
                        "market_cap": market_cap_usd,
                        "avg_volume_value": (price_krw * volume) / fx_krw if price_krw and volume else 0,
                        "country": "KR",
                        "source": "naver_market_sum_fallback",
                    })
                    found += 1
                if found == 0:
                    break
                time.sleep(0.2)
            except Exception as e:
                logger.warning("[KR] Naver %s page %d 실패: %s", market, page, e)
                break

    if not rows:
        logger.warning("[KR] Naver fallback 결과 0개 — seed fallback")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.drop_duplicates("ticker")
    df = df.sort_values(["market_cap", "avg_volume_value"], ascending=False).head(max_n).reset_index(drop=True)
    logger.info("[KR] Naver 시총 fallback: %d종목", len(df))
    return df


def _fetch_kr_universe_pykrx(market_cap_min_usd: float, max_n: int, fx_krw: float = 1471) -> pd.DataFrame:
    """pykrx로 KRX 전체 시총/거래대금 테이블 수집.

    pykrx는 KRX 데이터를 감싼 라이브러리다. GitHub Actions에서 막힐 수 있어
    실패하면 기존 seed fallback을 사용한다.
    """
    try:
        from pykrx import stock
    except ImportError:
        logger.warning("[KR] pykrx 미설치 — seed fallback")
        return pd.DataFrame()

    cap_df = pd.DataFrame()
    used_date = ""
    for i in range(10):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        try:
            df = stock.get_market_cap_by_ticker(day, market="ALL")
            if df is not None and not df.empty:
                cap_df = df.copy()
                used_date = day
                break
        except Exception as e:
            logger.debug("[KR] pykrx %s 실패: %s", day, e)
            continue

    if cap_df.empty:
        logger.warning("[KR] pykrx KRX 테이블 비어있음 — seed fallback")
        return pd.DataFrame()

    try:
        kosdaq_codes = set(stock.get_market_ticker_list(used_date, market="KOSDAQ"))
    except Exception:
        kosdaq_codes = set()

    rows = []
    for code, row in cap_df.iterrows():
        try:
            market_cap_krw = float(row.get("시가총액", 0) or 0)
            volume_value_krw = float(row.get("거래대금", 0) or 0)
            market_cap_usd = market_cap_krw / fx_krw
            if market_cap_usd < market_cap_min_usd:
                continue

            market = "KOSDAQ" if code in kosdaq_codes else "KOSPI"
            suffix = ".KQ" if market == "KOSDAQ" else ".KS"
            name = ""
            try:
                name = stock.get_market_ticker_name(code)
            except Exception:
                name = code

            rows.append({
                "ticker": f"{code}{suffix}",
                "name": name,
                "sector": "",
                "industry": market,
                "market_cap": market_cap_usd,
                "avg_volume_value": volume_value_krw / fx_krw,
                "country": "KR",
                "source": f"pykrx:{used_date}",
            })
        except Exception:
            continue

    if not rows:
        logger.warning("[KR] pykrx 필터 통과 종목 0개 — seed fallback")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values(["market_cap", "avg_volume_value"], ascending=False).head(max_n).reset_index(drop=True)
    logger.info("[KR] pykrx KRX: %d종목 (date=%s)", len(df), used_date)
    return df


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
    jpx_df = _fetch_jp_universe_jpx(market_cap_min_usd, max_n)
    if not jpx_df.empty:
        return jpx_df

    try:
        import yfinance as yf
        rows = []
        for ticker in _JP_SEED_TICKERS[:max_n]:
            try:
                info = yf.Ticker(ticker).info
                market_cap_jpy = float(info.get("marketCap", 0) or 0)
                market_cap_usd = market_cap_jpy / FX_JPY_PER_USD if market_cap_jpy else 0
                if market_cap_usd < market_cap_min_usd:
                    continue
                current_price_jpy = float(info.get("currentPrice", 0) or 0)
                avg_volume = float(info.get("averageVolume", 0) or 0)
                rows.append({
                    "ticker": ticker,
                    "name": info.get("longName", ticker),
                    "sector": info.get("sector", ""),
                    "industry": info.get("industry", ""),
                    "market_cap": market_cap_usd,
                    "avg_volume_value": (avg_volume * current_price_jpy) / FX_JPY_PER_USD,
                    "country": "JP",
                    "source": "yfinance_seed_fallback",
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


def _fetch_jp_universe_jpx(market_cap_min_usd: float, max_n: int) -> pd.DataFrame:
    """JPX official listed issues + yfinance market-cap enrichment."""
    try:
        import yfinance as yf
        listed = pd.read_excel(JPX_LISTED_XLS_URL)
    except Exception as e:
        logger.warning("[JP] JPX 공식 상장목록 실패 — seed fallback: %s", e)
        return pd.DataFrame()

    if listed.empty or "コード" not in listed.columns:
        logger.warning("[JP] JPX 공식 상장목록 비어있음 — seed fallback")
        return pd.DataFrame()

    product = listed["市場・商品区分"].astype(str)
    listed = listed[
        product.str.contains("内国株式", na=False)
        & ~product.str.contains("ETF|ETN|REIT|インフラ", na=False)
    ].copy()
    if listed.empty:
        return pd.DataFrame()

    # JPX 목록은 시총이 없으므로 먼저 Prime/Standard/Growth 순으로 넓게 잡고,
    # yfinance info로 시총/거래대금을 붙여 주류 종목만 남긴다.
    market_rank = {
        "プライム（内国株式）": 0,
        "スタンダード（内国株式）": 1,
        "グロース（内国株式）": 2,
    }
    listed["_rank"] = listed["市場・商品区分"].map(market_rank).fillna(9)
    listed = listed.sort_values(["_rank", "規模コード"]).head(max(max_n * 2, 300))

    rows = []
    for _, row in listed.iterrows():
        code = str(row.get("コード", "")).strip()
        if not code or code == "nan":
            continue
        ticker = f"{code}.T"
        try:
            info = yf.Ticker(ticker).info
            market_cap_jpy = float(info.get("marketCap", 0) or 0)
            market_cap_usd = market_cap_jpy / FX_JPY_PER_USD if market_cap_jpy else 0
            if market_cap_usd and market_cap_usd < market_cap_min_usd:
                continue
            avg_value = ((info.get("averageVolume") or 0) * (info.get("currentPrice") or 0)) / FX_JPY_PER_USD
            rows.append({
                "ticker": ticker,
                "name": str(row.get("銘柄名", ticker)),
                "sector": str(row.get("17業種区分", "")),
                "industry": str(row.get("33業種区分", "")),
                "market_cap": market_cap_usd,
                "avg_volume_value": avg_value,
                "country": "JP",
                "source": "jpx_official+yfinance",
            })
            time.sleep(0.15)
        except Exception as e:
            logger.debug("[JP] %s yfinance 보강 실패: %s", ticker, e)
            continue

        if len(rows) >= max_n:
            break

    if not rows:
        logger.warning("[JP] JPX+yfinance 결과 0개 — seed fallback")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values(["market_cap", "avg_volume_value"], ascending=False).head(max_n).reset_index(drop=True)
    logger.info("[JP] JPX official+yfinance: %d종목", len(df))
    return df


# ═══════════════════════════════════════════════════════════
# 중국 ADR
# ═══════════════════════════════════════════════════════════

_CN_ADR_TICKERS = [
    "BABA", "JD", "PDD", "BIDU", "NIO", "LI", "XPEV", "TME", "BILI", "YMM",
    "TCOM", "VIPS", "EDU", "TAL", "BEKE", "ZH", "MNSO", "WB", "IQ", "DIDI",
    "LU", "FUTU", "TIGR", "NTES", "ATAT", "QFIN", "ZTO", "HTHT", "BZ", "VNET",
    "KC", "DAO", "GDS", "RLX", "DOYU", "HUYA", "MOMO", "YSG", "NOAH", "DDL",
    "ZLAB", "BGNE", "MFIN", "LX", "JKS", "DQ", "HCM", "ATHM", "FINV",
]


_CN_HK_TICKERS = [
    "0700.HK", "9988.HK", "3690.HK", "9618.HK", "1211.HK", "1810.HK",
    "9999.HK", "1024.HK", "9868.HK", "2015.HK", "9888.HK", "2318.HK",
    "0939.HK", "1398.HK", "3988.HK", "3968.HK", "1299.HK", "0388.HK",
    "0883.HK", "0857.HK", "0386.HK", "0941.HK", "0762.HK", "0728.HK",
    "2319.HK", "1177.HK", "1093.HK", "2269.HK", "2331.HK", "2020.HK",
    "6690.HK", "0005.HK", "0016.HK", "0001.HK", "0027.HK", "1928.HK",
    "6862.HK", "9633.HK", "6618.HK", "9961.HK", "0241.HK", "1818.HK",
    "2899.HK", "2601.HK", "2628.HK", "1919.HK", "1088.HK", "3328.HK",
    "2382.HK", "1347.HK", "1801.HK", "6030.HK", "1658.HK", "2202.HK",
]


_CN_A_TICKERS = [
    "600519.SS", "300750.SZ", "601318.SS", "600036.SS", "601398.SS",
    "601288.SS", "601988.SS", "601857.SS", "600028.SS", "600900.SS",
    "601899.SS", "601668.SS", "601728.SS", "600030.SS", "600276.SS",
    "600309.SS", "600887.SS", "600690.SS", "601012.SS", "601166.SS",
    "600031.SS", "601919.SS", "600050.SS", "601688.SS", "601088.SS",
    "600406.SS", "600438.SS", "688981.SS", "603259.SS", "601888.SS",
    "601211.SS", "601633.SS", "601225.SS", "601816.SS", "601390.SS",
    "601800.SS", "601328.SS", "601601.SS", "600104.SS", "600019.SS",
    "600585.SS", "601985.SS", "600011.SS", "600150.SS", "600760.SS",
    "000001.SZ", "000002.SZ", "000333.SZ", "000651.SZ", "000858.SZ",
    "002415.SZ", "002594.SZ", "002714.SZ", "002475.SZ", "002230.SZ",
    "002352.SZ", "002142.SZ", "002304.SZ", "002371.SZ", "002460.SZ",
    "002129.SZ", "300059.SZ", "300014.SZ", "300015.SZ", "300122.SZ",
    "300124.SZ", "300274.SZ", "300308.SZ", "300347.SZ", "300408.SZ",
    "300498.SZ", "300760.SZ", "300782.SZ", "300896.SZ", "300919.SZ",
]


def _fetch_yfinance_bucket(
    yf_module,
    tickers: list[str],
    country: str,
    source: str,
    market_cap_min_usd: float,
    max_n: int,
    fx_per_usd: float = 1.0,
) -> pd.DataFrame:
    rows = []
    for ticker in tickers[:max_n]:
        try:
            info = yf_module.Ticker(ticker).info
            market_cap_local = float(info.get("marketCap", 0) or 0)
            market_cap_usd = market_cap_local / fx_per_usd if market_cap_local else 0
            if market_cap_usd < market_cap_min_usd:
                continue
            current_price = float(info.get("currentPrice", 0) or 0)
            avg_volume = float(info.get("averageVolume", 0) or 0)
            rows.append({
                "ticker": ticker,
                "name": info.get("longName") or info.get("shortName") or ticker,
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "market_cap": market_cap_usd,
                "avg_volume_value": (avg_volume * current_price) / fx_per_usd,
                "country": country,
                "source": source,
            })
            time.sleep(0.15)
        except Exception as e:
            logger.debug("[%s] %s 실패: %s", country, ticker, e)
            continue

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["market_cap", "avg_volume_value"], ascending=False).reset_index(drop=True)


def _fetch_cn_universe_akshare(market_cap_min_usd: float, max_n: int) -> pd.DataFrame:
    """Eastmoney/AkShare China universe.

    This is the wide China path. It can return hundreds or thousands of names,
    but the public endpoint may occasionally reject requests, so yfinance seeds
    remain the stable fallback.
    """
    try:
        import akshare as ak
    except ImportError:
        logger.info("[CN] akshare 미설치 — yfinance seed fallback")
        return pd.DataFrame()

    parts = []

    try:
        a_raw = ak.stock_zh_a_spot_em()
        if a_raw is not None and not a_raw.empty:
            rows = []
            for _, row in a_raw.iterrows():
                code = str(row.get("代码", "")).strip()
                if not code or code == "nan":
                    continue
                if code.startswith(("688", "600", "601", "603")):
                    ticker = f"{code}.SS"
                elif code.startswith(("000", "001", "002", "003", "300", "301")):
                    ticker = f"{code}.SZ"
                else:
                    continue

                market_cap_cny = _parse_float_text(row.get("总市值", 0))
                market_cap_usd = market_cap_cny / FX_CNY_PER_USD if market_cap_cny else 0
                if market_cap_usd < market_cap_min_usd:
                    continue
                rows.append({
                    "ticker": ticker,
                    "name": str(row.get("名称", ticker)),
                    "sector": "",
                    "industry": "A-share",
                    "market_cap": market_cap_usd,
                    "avg_volume_value": _parse_float_text(row.get("成交额", 0)) / FX_CNY_PER_USD,
                    "country": "CN_A",
                    "source": "akshare_eastmoney_a",
                })
            if rows:
                parts.append(pd.DataFrame(rows))
    except Exception as e:
        logger.warning("[CN] AkShare A주 수집 실패: %s", e)

    try:
        hk_raw = ak.stock_hk_spot_em()
        if hk_raw is not None and not hk_raw.empty:
            rows = []
            for _, row in hk_raw.iterrows():
                code = str(row.get("代码", "")).strip().zfill(4)
                if not code or code == "nan":
                    continue
                market_cap_hkd = _parse_float_text(row.get("总市值", 0))
                market_cap_usd = market_cap_hkd / FX_HKD_PER_USD if market_cap_hkd else 0
                if market_cap_usd < market_cap_min_usd:
                    continue
                rows.append({
                    "ticker": f"{code}.HK",
                    "name": str(row.get("名称", f"{code}.HK")),
                    "sector": "",
                    "industry": "HK-listed",
                    "market_cap": market_cap_usd,
                    "avg_volume_value": _parse_float_text(row.get("成交额", 0)) / FX_HKD_PER_USD,
                    "country": "CN_HK",
                    "source": "akshare_eastmoney_hk",
                })
            if rows:
                parts.append(pd.DataFrame(rows))
    except Exception as e:
        logger.warning("[CN] AkShare 홍콩 수집 실패: %s", e)

    if not parts:
        return pd.DataFrame()

    df = pd.concat(parts, ignore_index=True)
    df = df.drop_duplicates("ticker")
    df = df.sort_values(["market_cap", "avg_volume_value"], ascending=False).head(max_n).reset_index(drop=True)
    counts = df.groupby("country").size().to_dict()
    logger.info("[CN] AkShare wide: %d종목 %s", len(df), counts)
    return df


def _fetch_cn_universe(market_cap_min_usd: float, max_n: int) -> pd.DataFrame:
    try:
        import yfinance as yf

        adr_limit = min(len(_CN_ADR_TICKERS), max(40, max_n // 4))
        adr_df = _fetch_yfinance_bucket(
            yf, _CN_ADR_TICKERS, "CN_ADR", "yfinance_cn_adr", market_cap_min_usd, adr_limit
        )

        akshare_df = _fetch_cn_universe_akshare(market_cap_min_usd, max_n)
        if not akshare_df.empty:
            parts = [df for df in [adr_df, akshare_df] if df is not None and not df.empty]
            df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
            if df.empty:
                return pd.DataFrame()
            df = df.drop_duplicates("ticker")
            df = df.sort_values(["market_cap", "avg_volume_value"], ascending=False).head(max_n).reset_index(drop=True)
            counts = df.groupby("country").size().to_dict()
            logger.info("[CN] ADR + AkShare wide: %d종목 %s", len(df), counts)
            return df

        # China is split intentionally:
        # - CN_ADR: US-listed Chinese ADRs
        # - CN_HK: Hong Kong-listed China/H-share leaders
        # - CN_A: Shanghai/Shenzhen A-share leaders
        hk_limit = min(len(_CN_HK_TICKERS), max(60, max_n // 3))
        a_limit = min(len(_CN_A_TICKERS), max_n)

        parts = [
            adr_df,
            _fetch_yfinance_bucket(yf, _CN_HK_TICKERS, "CN_HK", "yfinance_hk_china_seed", market_cap_min_usd, hk_limit, FX_HKD_PER_USD),
            _fetch_yfinance_bucket(yf, _CN_A_TICKERS, "CN_A", "yfinance_cn_a_seed", market_cap_min_usd, a_limit, FX_CNY_PER_USD),
        ]
        parts = [df for df in parts if df is not None and not df.empty]
        if not parts:
            logger.warning("[CN] ADR/HK/A 수집 결과 0개")
            return pd.DataFrame()

        df = pd.concat(parts, ignore_index=True)
        df = df.drop_duplicates("ticker")
        df = df.sort_values(["market_cap", "avg_volume_value"], ascending=False).head(max_n).reset_index(drop=True)
        counts = df.groupby("country").size().to_dict()
        logger.info("[CN] ADR/HK/A: %d종목 %s", len(df), counts)
        return df
    except Exception as e:
        logger.error("[CN] ADR/HK/A 수집 실패: %s", e)
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
