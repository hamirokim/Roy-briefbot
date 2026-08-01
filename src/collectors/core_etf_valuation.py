"""Price and relative-valuation snapshot for Roy's core ETFs.

Equity ETFs use portfolio-role peers because Yahoo's category-average column is
not reliably populated. TIPS and gold use asset-specific market inputs and
never inherit equity multiples.
"""

from __future__ import annotations

import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

logger = logging.getLogger(__name__)

EQUITY_METRICS = (
    ("pe", "Price/Earnings", "P/E"),
    ("pb", "Price/Book", "P/B"),
    ("ps", "Price/Sales", "P/S"),
    ("pcf", "Price/Cashflow", "P/CF"),
)

DEFAULT_PEERS = {
    "VTI": "VT",
    "IXUS": "VT",
    "AVUV": "VTI",
    "AVDV": "IXUS",
    "QQQM": "VTI",
}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _multiple(value: Any) -> float | None:
    """Normalize Yahoo fund yields (0.xx) into human-readable multiples."""
    number = _number(value)
    if number is None:
        return None
    return 1.0 / number if number < 1.0 else number


def extract_equity_metrics(table: Any, ticker: str) -> dict[str, dict[str, float]]:
    """Extract the ETF's own multiples even when category averages are absent."""
    if table is None or not hasattr(table, "loc"):
        return {}

    metrics: dict[str, dict[str, float]] = {}
    for key, row_name, label in EQUITY_METRICS:
        try:
            fund_value = _multiple(table.loc[row_name][ticker])
        except (KeyError, TypeError, IndexError):
            continue
        if fund_value is None:
            continue
        metrics[key] = {"label": label, "fund": round(fund_value, 2)}
    return metrics


def classify_equity_metrics(
    metrics: dict,
    peer_metrics: dict,
    peer_ticker: str,
    min_metrics: int = 3,
) -> dict:
    """Classify direction against a portfolio-role peer, not fair value."""
    comparable = [
        key for key in metrics
        if key in peer_metrics
        and _number(metrics[key].get("fund")) is not None
        and _number(peer_metrics[key].get("fund")) is not None
    ]
    if len(comparable) < min_metrics:
        return {
            "status": "UNAVAILABLE",
            "label": "판정 보류",
            "reason": f"{peer_ticker} 비교 배수 부족 ({len(comparable)}/{len(EQUITY_METRICS)})",
        }

    lower = sum(metrics[key]["fund"] < peer_metrics[key]["fund"] for key in comparable)
    higher = sum(metrics[key]["fund"] > peer_metrics[key]["fund"] for key in comparable)
    needed = max(2, math.ceil(len(comparable) * 0.75))
    if lower >= needed:
        status, label = "RELATIVE_LOW", "상대 낮음"
    elif higher >= needed:
        status, label = "RELATIVE_HIGH", "상대 높음"
    else:
        status, label = "MIXED", "혼재"
    return {
        "status": status,
        "label": label,
        "peer_ticker": peer_ticker,
        "reason": f"{peer_ticker} 대비 낮은 배수 {lower}개 · 높은 배수 {higher}개",
    }


def _collect_equity_ticker(ticker: str) -> dict:
    import yfinance as yf

    last_error: Optional[Exception] = None
    for attempt in range(3):
        try:
            table = yf.Ticker(ticker).funds_data.equity_holdings
            metrics = extract_equity_metrics(table, ticker)
            if metrics:
                return {
                    "ticker": ticker,
                    "asset_type": "equity_etf",
                    "source": "yfinance_funds_data",
                    "metrics": metrics,
                }
        except Exception as exc:
            last_error = exc
        if attempt < 2:
            time.sleep(0.75 * (attempt + 1))

    logger.warning("[core valuation] %s 수집 실패(3회): %s", ticker, last_error or "empty metrics")
    return {
        "ticker": ticker,
        "asset_type": "equity_etf",
        "source": "yfinance_funds_data",
        "metrics": {},
    }


def _percentile(values: list[float], current: float) -> float | None:
    clean = [float(value) for value in values if _number(value) is not None]
    if not clean:
        return None
    return round(sum(value <= current for value in clean) / len(clean) * 100, 1)


def _price_context(ticker: str, period: str = "5y") -> dict:
    import yfinance as yf

    obj = yf.Ticker(ticker)
    history = obj.history(period=period, auto_adjust=False)
    if history is None or history.empty or "Close" not in history:
        return {}
    closes = [float(value) for value in history["Close"].dropna().tolist()]
    if not closes:
        return {}
    current = closes[-1]
    info = obj.info or {}
    nav = _number(info.get("navPrice"))
    return {
        "price": round(current, 2),
        "price_percentile_5y": _percentile(closes, current),
        "price_percentile_52w": _percentile(closes[-252:], current),
        "nav": round(nav, 2) if nav is not None else None,
        "nav_premium_pct": round((current - nav) / nav * 100, 2) if nav else None,
    }


def _real_yield_context() -> dict:
    try:
        from src.collectors.macro_calendar import fetch_fred_series

        observations = fetch_fred_series("DFII10", lookback_days=366 * 5) or []
        values = [float(row["value"]) for row in observations if row.get("value") not in {None, "."}]
        if not values:
            return {}
        current = values[0]
        prior = values[min(19, len(values) - 1)]
        return {
            "series": "DFII10",
            "value": round(current, 2),
            "percentile_5y": _percentile(values, current),
            "change_20obs": round(current - prior, 2),
        }
    except Exception as exc:
        logger.warning("[core valuation] DFII10 수집 실패: %s", exc)
        return {}


def _collect_non_equity(ticker: str, asset_type: str, real_yield: dict, cfg: dict) -> dict:
    try:
        price = _price_context(ticker)
    except Exception as exc:
        logger.warning("[core valuation] %s 가격 수집 실패: %s", ticker, exc)
        price = {}
    low = float(cfg.get("percentile_low_pct", 30))
    high = float(cfg.get("percentile_high_pct", 70))

    if not price or not real_yield:
        return {
            "ticker": ticker,
            "asset_type": asset_type,
            "status": "UNAVAILABLE",
            "label": "판정 보류",
            "reason": "가격 또는 10년 실질금리 수집 실패",
            "source": "yfinance+FRED_DFII10",
            "metrics": {**price, "real_yield": real_yield},
        }

    if asset_type == "tips_bond":
        pct = real_yield.get("percentile_5y")
        if pct is None:
            status, label = "UNAVAILABLE", "판정 보류"
        elif pct >= high:
            status, label = "INCOME_OPPORTUNITY_HIGH", "실질금리 기회 높음"
        elif pct <= low:
            status, label = "INCOME_OPPORTUNITY_LOW", "실질금리 기회 낮음"
        else:
            status, label = "INCOME_OPPORTUNITY_NEUTRAL", "실질금리 기회 중립"
        reason = (
            f"10년 실질금리 {real_yield['value']:.2f}% · 5년 {pct:.0f}백분위"
            if pct is not None else "10년 실질금리 위치 계산 실패"
        )
    else:
        pct = price.get("price_percentile_5y")
        if pct is None:
            status, label = "UNAVAILABLE", "판정 보류"
        elif pct <= low:
            status, label = "PRICE_BURDEN_LOW", "가격 부담 낮음"
        elif pct >= high:
            status, label = "PRICE_BURDEN_HIGH", "가격 부담 높음"
        else:
            status, label = "PRICE_BURDEN_NEUTRAL", "가격 부담 중립"
        direction = "상승해 금에 부담" if real_yield.get("change_20obs", 0) > 0 else "하락해 금에 우호"
        reason = f"5년 가격 {pct:.0f}백분위 · 실질금리 20관측일 {direction}"

    return {
        "ticker": ticker,
        "asset_type": asset_type,
        "status": status,
        "label": label,
        "reason": reason,
        "source": "yfinance+FRED_DFII10",
        "metrics": {**price, "real_yield": real_yield},
    }


def collect_core_etf_valuations(cfg: dict) -> dict:
    """Collect all configured ETFs while preserving display order."""
    tickers = [str(t).upper() for t in cfg.get("tickers", [])]
    equity_tickers = {str(t).upper() for t in cfg.get("equity_tickers", [])}
    min_metrics = int(cfg.get("min_comparable_metrics", 3))
    non_equity = cfg.get("non_equity", {}) or {}
    peers = {**DEFAULT_PEERS, **(cfg.get("equity_peers", {}) or {})}

    if not cfg.get("enabled", False):
        return {"enabled": False, "items": []}

    collected: dict[str, dict] = {}
    workers = max(1, min(int(cfg.get("max_workers", 4)), len(equity_tickers) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_collect_equity_ticker, ticker): ticker
            for ticker in equity_tickers if ticker in tickers
        }
        for future in as_completed(futures):
            item = future.result()
            collected[item["ticker"]] = item

    for ticker in equity_tickers:
        if ticker not in collected:
            continue
        if ticker == "VT":
            collected[ticker].update({
                "status": "PORTFOLIO_BASELINE",
                "label": "글로벌 기준",
                "reason": "다른 주식 ETF의 포트 역할 비교 기준",
            })
            continue
        peer = str(peers.get(ticker, "VT")).upper()
        peer_metrics = (collected.get(peer) or {}).get("metrics", {})
        collected[ticker].update(
            classify_equity_metrics(
                collected[ticker].get("metrics", {}),
                peer_metrics,
                peer,
                min_metrics=min_metrics,
            )
        )

    real_yield = _real_yield_context() if non_equity else {}
    for ticker in tickers:
        if ticker in collected:
            continue
        asset_type = str(non_equity.get(ticker, "unsupported"))
        if asset_type in {"tips_bond", "gold"}:
            collected[ticker] = _collect_non_equity(ticker, asset_type, real_yield, cfg)
        else:
            collected[ticker] = {
                "ticker": ticker,
                "asset_type": asset_type,
                "status": "UNAVAILABLE",
                "label": "판정 보류",
                "reason": "자산별 판정 기준 미연결",
                "source": None,
                "metrics": {},
            }

    items = [collected[ticker] for ticker in tickers]
    return {
        "enabled": True,
        "method": "portfolio_role_peers_and_asset_specific_context",
        "disclaimer": "상대 비교와 시장 위치이며 절대 적정가 판정이 아님",
        "items": items,
        "complete_count": sum(item["status"] not in {"UNAVAILABLE"} for item in items),
        "total_count": len(items),
    }
