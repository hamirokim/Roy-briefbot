"""Relative valuation snapshot for Roy's core ETFs.

Equity ETFs are compared with their Yahoo fund category across four portfolio
multiples. Bond and gold ETFs deliberately fail closed because equity
multiples do not describe their valuation.
"""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

logger = logging.getLogger(__name__)

EQUITY_METRICS = (
    ("pe", "Price/Earnings", "P/E"),
    ("pb", "Price/Book", "P/B"),
    ("ps", "Price/Sales", "P/S"),
    ("pcf", "Price/Cashflow", "P/CF"),
)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def extract_equity_metrics(table: Any, ticker: str) -> dict[str, dict[str, float]]:
    """Extract fund and category multiples from yfinance equity_holdings."""
    if table is None or not hasattr(table, "loc"):
        return {}

    metrics: dict[str, dict[str, float]] = {}
    for key, row_name, label in EQUITY_METRICS:
        try:
            row = table.loc[row_name]
            fund_value = _number(row[ticker])
            category_value = _number(row["Category Average"])
        except (KeyError, TypeError, IndexError):
            continue
        if fund_value is None or category_value is None:
            continue
        metrics[key] = {
            "label": label,
            "fund": round(fund_value, 2),
            "category": round(category_value, 2),
            "difference_pct": round(
                ((fund_value - category_value) / category_value) * 100,
                1,
            ),
        }
    return metrics


def classify_equity_metrics(metrics: dict, min_metrics: int = 3) -> dict:
    """Classify direction only; this is not an intrinsic fair-value estimate."""
    available = list(metrics.values())
    if len(available) < min_metrics:
        return {
            "status": "UNAVAILABLE",
            "label": "판정 보류",
            "reason": f"비교 배수 부족 ({len(available)}/{len(EQUITY_METRICS)})",
        }

    lower = sum(item["fund"] < item["category"] for item in available)
    higher = sum(item["fund"] > item["category"] for item in available)
    if lower >= 3:
        status, label = "RELATIVE_LOW", "상대 낮음"
    elif higher >= 3:
        status, label = "RELATIVE_HIGH", "상대 높음"
    else:
        status, label = "MIXED", "혼재"
    return {
        "status": status,
        "label": label,
        "reason": f"카테고리 대비 낮은 배수 {lower}개 · 높은 배수 {higher}개",
    }


def _collect_equity_ticker(ticker: str, min_metrics: int) -> dict:
    try:
        import yfinance as yf

        table = yf.Ticker(ticker).funds_data.equity_holdings
        metrics = extract_equity_metrics(table, ticker)
        classification = classify_equity_metrics(metrics, min_metrics=min_metrics)
        return {
            "ticker": ticker,
            "asset_type": "equity_etf",
            "source": "yfinance_funds_data",
            "metrics": metrics,
            **classification,
        }
    except Exception as exc:
        logger.warning("[core valuation] %s 수집 실패: %s", ticker, exc)
        return {
            "ticker": ticker,
            "asset_type": "equity_etf",
            "status": "UNAVAILABLE",
            "label": "판정 보류",
            "reason": "ETF 카테고리 비교 데이터 수집 실패",
            "source": "yfinance_funds_data",
            "metrics": {},
        }


def collect_core_etf_valuations(cfg: dict) -> dict:
    """Collect all configured ETFs while preserving configured display order."""
    tickers = [str(t).upper() for t in cfg.get("tickers", [])]
    equity_tickers = {
        str(t).upper() for t in cfg.get("equity_tickers", [])
    }
    min_metrics = int(cfg.get("min_comparable_metrics", 3))
    non_equity = cfg.get("non_equity", {}) or {}

    if not cfg.get("enabled", False):
        return {"enabled": False, "items": []}

    collected: dict[str, dict] = {}
    workers = max(1, min(int(cfg.get("max_workers", 4)), len(equity_tickers) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_collect_equity_ticker, ticker, min_metrics): ticker
            for ticker in equity_tickers
            if ticker in tickers
        }
        for future in as_completed(futures):
            item = future.result()
            collected[item["ticker"]] = item

    for ticker in tickers:
        if ticker in collected:
            continue
        asset_type = str(non_equity.get(ticker, "unsupported"))
        if asset_type == "tips_bond":
            reason = "물가채는 주식 배수 적용 불가 · 실질금리 기준 미연결"
        elif asset_type == "gold":
            reason = "금은 이익 배수 적용 불가 · 실질금리 기준 미연결"
        else:
            reason = "자산별 估值 기준 미연결"
        collected[ticker] = {
            "ticker": ticker,
            "asset_type": asset_type,
            "status": "NOT_COMPARABLE",
            "label": "판정 보류",
            "reason": reason,
            "source": None,
            "metrics": {},
        }

    items = [collected[ticker] for ticker in tickers]
    return {
        "enabled": True,
        "method": "equity_category_multiples",
        "disclaimer": "상대 비교이며 절대 적정가 판정이 아님",
        "items": items,
        "complete_count": sum(
            item["status"] in {"RELATIVE_LOW", "MIXED", "RELATIVE_HIGH"}
            for item in items
        ),
        "total_count": len(items),
    }
