"""Financial Modeling Prep collector.

FMP is an optional paid data source. The bot must keep working without it:
every public function returns ``None`` or a non-fatal status when
``FMP_API_KEY`` is missing or an endpoint fails.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/stable"


def fmp_enabled() -> bool:
    return bool(FMP_API_KEY)


def _symbol(ticker: str, country: str = "US") -> str:
    if country and country != "US":
        return ""
    symbol = (ticker or "").strip().upper()
    if symbol.endswith(".US"):
        symbol = symbol[:-3]
    return symbol.split(".")[0]


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value: Any) -> Optional[float]:
    val = _safe_float(value)
    if val is None:
        return None
    # FMP growth fields are usually decimal ratios. Keep already-percent data.
    return val * 100.0 if abs(val) <= 5 else val


def _request(path: str, params: Optional[dict] = None, version: str = "stable") -> Any:
    if not FMP_API_KEY:
        return None

    params = dict(params or {})
    params["apikey"] = FMP_API_KEY
    try:
        resp = requests.get(f"{FMP_BASE}/{path.lstrip('/')}", params=params, timeout=12)
        if resp.status_code != 200:
            logger.debug("[FMP] %s HTTP %s", path, resp.status_code)
            return None
        data = resp.json()
        if isinstance(data, dict) and data.get("Error Message"):
            logger.debug("[FMP] %s error: %s", path, data.get("Error Message"))
            return None
        return data
    except Exception as e:
        logger.debug("[FMP] %s failed: %s", path, e)
        return None


def _first(data: Any) -> dict:
    if isinstance(data, list) and data:
        return data[0] if isinstance(data[0], dict) else {}
    if isinstance(data, dict):
        return data
    return {}


def fetch_fundamental_data(ticker: str, country: str = "US") -> Optional[dict]:
    """Fetch US quality/fundamental data in the Finviz-compatible shape.

    Returns ``None`` when FMP is disabled, unsupported, or empty so callers can
    fall back to Finviz without branching on failure details.
    """
    symbol = _symbol(ticker, country)
    if not symbol or not FMP_API_KEY:
        return None

    profile = _first(_request("profile", {"symbol": symbol}))
    ratios = _first(_request("ratios-ttm", {"symbol": symbol}))
    metrics = _first(_request("key-metrics-ttm", {"symbol": symbol}))
    income_growth = _first(_request("income-statement-growth", {"symbol": symbol, "limit": 1}))
    cash_growth = _first(_request("cash-flow-statement-growth", {"symbol": symbol, "limit": 1}))
    rating = _first(_request("ratings-snapshot", {"symbol": symbol}))

    if not any([profile, ratios, metrics, income_growth, cash_growth, rating]):
        return None

    pe = (
        _safe_float(ratios.get("priceToEarningsRatioTTM"))
        or _safe_float(ratios.get("priceEarningsRatioTTM"))
        or _safe_float(metrics.get("peRatioTTM"))
    )
    peg = (
        _safe_float(ratios.get("priceToEarningsGrowthRatioTTM"))
        or _safe_float(ratios.get("priceEarningsGrowthRatioTTM"))
        or _safe_float(metrics.get("pegRatioTTM"))
    )
    eps_growth = (
        _pct(income_growth.get("growthEPS"))
        or _pct(income_growth.get("growthNetIncome"))
        or _pct(income_growth.get("growthRevenue"))
    )

    return {
        "pe": pe,
        "forward_pe": None,
        "eps_next_y": None,
        "eps_growth_next_y": eps_growth,
        "peg": peg,
        "insider_trans": None,
        "inst_trans": None,
        "short_float": None,
        "rsi14": None,
        "sector": str(profile.get("sector", "") or ""),
        "industry": str(profile.get("industry", "") or ""),
        "market_cap": _safe_float(profile.get("marketCap")) or _safe_float(profile.get("mktCap")),
        "earnings_date": "",
        "source": "fmp",
        "fmp_quality": {
            "revenue_growth_pct": _pct(income_growth.get("growthRevenue")),
            "eps_growth_pct": _pct(income_growth.get("growthEPS")),
            "free_cash_flow_growth_pct": _pct(cash_growth.get("growthFreeCashFlow")),
            "gross_margin_ttm": _pct(ratios.get("grossProfitMarginTTM")),
            "operating_margin_ttm": _pct(ratios.get("operatingProfitMarginTTM")),
            "net_margin_ttm": _pct(ratios.get("netProfitMarginTTM")),
            "roe_ttm": _pct(ratios.get("returnOnEquityTTM")),
            "roa_ttm": _pct(ratios.get("returnOnAssetsTTM")),
            "debt_equity_ttm": _safe_float(ratios.get("debtEquityRatioTTM")),
            "current_ratio_ttm": _safe_float(ratios.get("currentRatioTTM")),
            "rating": rating.get("rating"),
            "rating_score": _safe_float(rating.get("overallScore")) or _safe_float(rating.get("ratingScore")),
        },
    }


def _parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).replace("T", " ").replace("Z", "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if "%H" in fmt else text[:10], fmt)
        except ValueError:
            continue
    return None


def _epoch(value: Any) -> int:
    dt = _parse_date(value)
    return int(dt.timestamp()) if dt else 0


def fetch_catalyst_news(
    ticker: str,
    country: str = "US",
    lookback_days: int = 14,
    max_items: int = 3,
) -> tuple[str, list[dict]]:
    """Fetch catalyst candidates from FMP news, grades, and earnings.

    Output matches the scout catalyst schema used by Finnhub fallback.
    """
    symbol = _symbol(ticker, country)
    if not symbol:
        return "non_us", []
    if not FMP_API_KEY:
        return "no_key", []

    cutoff = datetime.utcnow() - timedelta(days=max(1, int(lookback_days or 14)))
    items: list[dict] = []

    news = _request("news/stock", {"symbols": symbol, "limit": max(5, max_items * 2)}) or []
    if isinstance(news, list):
        for it in news:
            published = it.get("publishedDate") or it.get("date")
            dt = _parse_date(published)
            if dt and dt < cutoff:
                continue
            headline = str(it.get("title", "") or "").strip()
            if not headline:
                continue
            items.append({
                "headline": headline[:180],
                "summary": str(it.get("text", "") or "").strip()[:300],
                "source": f"FMP:{str(it.get('publisher', '') or it.get('site', '') or 'news')}",
                "datetime": _epoch(published),
                "url": str(it.get("url", "") or "").strip(),
                "event_type": "news",
            })

    grades = _request("grades", {"symbol": symbol}) or []
    if isinstance(grades, list):
        for it in grades[:10]:
            date_val = it.get("date") or it.get("publishedDate")
            dt = _parse_date(date_val)
            if dt and dt < cutoff:
                continue
            action = str(it.get("action", "") or it.get("actionGrade", "") or "").strip()
            new_grade = str(it.get("newGrade", "") or it.get("newRating", "") or "").strip()
            old_grade = str(it.get("previousGrade", "") or it.get("previousRating", "") or "").strip()
            firm = str(it.get("gradingCompany", "") or it.get("analyst", "") or "").strip()
            headline = f"Analyst {action or 'rating'}: {old_grade or '?'} -> {new_grade or '?'}"
            if firm:
                headline += f" ({firm})"
            items.append({
                "headline": headline[:180],
                "summary": "",
                "source": "FMP:upgrades_downgrades",
                "datetime": _epoch(date_val),
                "url": "",
                "event_type": "analyst_rating",
            })

    earnings = _request("earnings", {"symbol": symbol, "limit": 4}) or []
    if isinstance(earnings, list):
        for it in earnings[:4]:
            date_val = it.get("date")
            dt = _parse_date(date_val)
            if dt and dt < cutoff:
                continue
            actual = _safe_float(it.get("epsActual") or it.get("actualEarningResult"))
            estimate = _safe_float(it.get("epsEstimated") or it.get("estimatedEarning"))
            surprise = actual - estimate if actual is not None and estimate is not None else None
            direction = "beat" if surprise is not None and surprise > 0 else "miss" if surprise is not None and surprise < 0 else "reported"
            items.append({
                "headline": f"Earnings {direction}: actual {actual}, estimate {estimate}"[:180],
                "summary": "",
                "source": "FMP:earnings_surprise",
                "datetime": _epoch(date_val),
                "url": "",
                "event_type": "earnings",
            })

    items.sort(key=lambda x: x.get("datetime", 0), reverse=True)
    if not items:
        return "empty", []
    return "ok", items[:max_items]
