"""
⚠️ DEPRECATED (D83) — Z3-4 폐기 박제

호출 0건 죽은 코드. 운영 영향 X.
폐기 사유: GUARD 에이전트가 보유 종목 모니터 직접 처리.
기능 흡수 위치: src/agents/guard.py

자세한 내용: src/modules/legacy/README.md

옛 코드 그대로 보존. import 추가 금지.
"""

"""
M4 포지션 트래커 v3 — Sheets 연동 + portfolio.json fallback
변경: Sheets에서 OPEN 포지션 읽기. 실패 시 portfolio.json fallback.
"""

import json
import logging
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.collectors.global_ohlcv import fetch_daily_closes_yf as fetch_daily_closes
from src.utils import now_kst

logger = logging.getLogger(__name__)

PORTFOLIO_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "portfolio.json"
MAX_POSITIONS = 5
VALID_STATUSES = {"WATCH", "ARMED", "OPEN", "ADD", "EXIT_WATCH"}
STOOQ_DELAY = 0.3


# ═══════════════════════════════════════════════════════════
# Sheets에서 포지션 로드 (우선)
# ═══════════════════════════════════════════════════════════
def _load_from_sheets() -> list[dict] | None:
    """Sheets에서 OPEN 포지션 로드. 실패 시 None 반환."""
    try:
        from src.collectors.sheets import read_positions
        positions = read_positions()
        if positions:
            logger.info("Sheets에서 %d개 포지션 로드", len(positions))
            return positions
        logger.info("Sheets 포지션 비어 있음")
        return positions  # 빈 리스트 반환 (정상 — 포지션 없음)
    except Exception as e:
        logger.warning("Sheets 로드 실패 → fallback: %s", e)
        return None


# ═══════════════════════════════════════════════════════════
# portfolio.json fallback (기존 유지)
# ═══════════════════════════════════════════════════════════
def _load_portfolio() -> list[dict]:
    if not PORTFOLIO_PATH.exists():
        logger.info("portfolio.json 없음 — M4 스킵")
        return []
    try:
        raw = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("portfolio.json 파싱 실패: %s", e)
        return []

    positions = raw.get("positions", [])
    if not positions:
        return []

    valid = []
    for p in positions:
        ticker = p.get("ticker", "").strip()
        status = p.get("status", "").strip().upper()
        if not ticker or status not in VALID_STATUSES:
            continue
        if status in ("OPEN", "ADD", "EXIT_WATCH") and not p.get("entry_price"):
            p["status"] = "WATCH"
        valid.append(p)

    max_pos = raw.get("max_positions", MAX_POSITIONS)
    if len(valid) > max_pos:
        valid.sort(key=lambda x: x.get("added", ""), reverse=True)
        valid = valid[:max_pos]
    return valid


# ═══════════════════════════════════════════════════════════
# DataFrame → 숫자 Series 정규화
# ═══════════════════════════════════════════════════════════
def _normalize_closes(raw) -> pd.Series | None:
    if raw is None:
        return None
    if isinstance(raw, pd.DataFrame):
        close_col = None
        for col in raw.columns:
            if col.lower() == "close":
                close_col = col
                break
        if close_col is None:
            numeric_cols = raw.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) == 0:
                return None
            close_col = numeric_cols[-1]
        series = raw[close_col].copy()
    elif isinstance(raw, pd.Series):
        series = raw.copy()
    else:
        try:
            series = pd.Series(raw)
        except Exception:
            return None

    series = series.apply(
        lambda x: float(x) if isinstance(x, (int, float, np.integer, np.floating)) else np.nan
    )
    return series.dropna()


# ═══════════════════════════════════════════════════════════
# 가격 + 변동률 수집
# ═══════════════════════════════════════════════════════════
def _fetch_price_data(tickers: list[str]) -> dict[str, dict]:
    results = {}
    for ticker in tickers:
        try:
            raw = fetch_daily_closes(ticker, lookback=30)
            series = _normalize_closes(raw)
            if series is None or len(series) < 2:
                logger.warning("데이터 부족: %s", ticker)
                results[ticker] = None
                continue

            closes = series.values
            last = float(closes[-1])
            prev = float(closes[-2])
            daily_pct = ((last - prev) / prev) * 100

            w_idx = max(0, len(closes) - 6)
            weekly_pct = ((last - float(closes[w_idx])) / float(closes[w_idx])) * 100

            results[ticker] = {
                "close": round(last, 2),
                "daily_pct": round(daily_pct, 1),
                "weekly_pct": round(weekly_pct, 1),
            }
        except Exception as e:
            logger.warning("수집 실패 (%s): %s", ticker, e)
            results[ticker] = None
        time.sleep(STOOQ_DELAY)

    return results


# ═══════════════════════════════════════════════════════════
# 압축 context 생성
# ═══════════════════════════════════════════════════════════
def _format_position(pos: dict, price_data: dict | None) -> str:
    ticker = pos["ticker"].upper().replace(".US", "")
    status = pos["status"]
    entry_price = pos.get("entry_price")
    sl_price = pos.get("sl_price")

    if price_data is None:
        return f"• {ticker} [{status}] — 가격 수집 실패"

    close = price_data["close"]
    daily = price_data["daily_pct"]
    weekly = price_data["weekly_pct"]

    parts = [f"• {ticker} [{status}] ${close:.2f}"]
    parts.append(f"일간 {daily:+.1f}%, 주간 {weekly:+.1f}%")

    if entry_price and status in ("OPEN", "ADD", "EXIT_WATCH"):
        pnl = ((close - entry_price) / entry_price) * 100
        parts.append(f"진입 ${entry_price:.2f} → {pnl:+.1f}%")
        if sl_price:
            sl_dist = ((close - sl_price) / close) * 100
            parts.append(f"SL ${sl_price:.2f} (-{sl_dist:.1f}%)")

    memo = pos.get("memo", "")
    if memo:
        parts.append(f"메모: {memo}")

    return " | ".join(parts)


# ═══════════════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════════════
def run_m4() -> dict:
    logger.info("=" * 50)
    logger.info("M4 포지션 트래커 시작")
    logger.info("=" * 50)

    # Sheets 우선, 실패 시 portfolio.json fallback
    positions = _load_from_sheets()
    if positions is None:
        logger.info("Sheets fallback → portfolio.json")
        positions = _load_portfolio()

    if not positions:
        return {"context_text": "", "position_count": 0}

    tickers = [p["ticker"] for p in positions]
    logger.info("현재가 수집: %s", ", ".join(tickers))
    price_map = _fetch_price_data(tickers)

    status_order = ["OPEN", "ADD", "EXIT_WATCH", "ARMED", "WATCH"]
    positions.sort(key=lambda x: status_order.index(x["status"]) if x["status"] in status_order else 99)

    date_str = now_kst().strftime("%Y-%m-%d")
    lines = [f"[포지션 — {date_str}]"]
    lines.append(f"{len(positions)}개 보유")
    lines.append("")

    for p in positions:
        pd_item = price_map.get(p["ticker"])
        lines.append(_format_position(p, pd_item))

    lines.append("")
    lines.append("GPT 지시: 가격 변동이 있는 종목만 상세 코멘트. 변동 없으면 '유지' 한마디. 변동 원인을 뉴스와 연결해서 해석. SL 체크하라는 빈 말 금지 — 위험한 거리일 때만 구체 숫자로.")

    context_text = "\n".join(lines)
    logger.info("M4 완료: %d개 포지션, %d자 컨텍스트", len(positions), len(context_text))

    return {"context_text": context_text, "position_count": len(positions)}
