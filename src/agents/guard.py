"""
src/agents/guard.py — GUARD 포지션 모니터 에이전트 (v2 patch — yfinance 전환)

미션: 보유 종목(Sheets에서 읽음)을 매일 모니터 → 의미있는 이벤트만 보고

룰:
  - 일간 변동 ±2% 미만 + 뉴스 없음 → 빈 출력 (현재 "유지/유지" 단조로움 해결)
  - 일간 변동 ±2% 이상 → 뉴스 매칭 + LLM 1줄 해석
  - 뉴스 헤드라인만 있어도 LLM 해석 (가격 변동 무관)

데이터 소스 (v2 패치):
  - Sheets read_positions() — 보유 종목 마스터
  - **yfinance** (Stooq 차단 회피) — 가격 변동
  - Finnhub /company-news — 종목별 뉴스 (이미 키 있음)

GUARD ≠ M4 트래커 (단순 가격 표시) — 뉴스 해석까지 포함된 "의미있는 보고"
M7 상관관계 결과도 GUARD가 흡수 (이미 보유 중이니 GUARD 영역)

v2 변경 (2026-04-21):
  - _fetch_price_change: Stooq → yfinance (GitHub Actions IP 차단 회피)
"""

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import requests

from src.agents.base import BaseAgent
from src.utils import today_kst_str

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════

def _load_settings() -> dict:
    import yaml
    path = Path(__file__).resolve().parents[2] / "config" / "ronin_settings.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ═══════════════════════════════════════════════════════════
# Sheets에서 보유 포지션 로드 (M4와 동일 패턴)
# ═══════════════════════════════════════════════════════════

def _load_positions_from_sheets() -> Optional[list[dict]]:
    try:
        from src.collectors.sheets import read_positions
        positions = read_positions()
        if positions is None:
            return None
        return positions
    except Exception as e:
        logger.warning("[guard] Sheets 로드 실패: %s", e)
        return None


def _load_positions_fallback() -> list[dict]:
    """portfolio.json fallback."""
    p = Path(__file__).resolve().parents[2] / "config" / "portfolio.json"
    if not p.exists():
        return []
    try:
        import json
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("positions", [])
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════
# 가격 변동 수집 — v2: yfinance 전용 (Stooq 차단 회피)
# ═══════════════════════════════════════════════════════════

def _normalize_ticker_for_yf(ticker: str) -> str:
    """저널/Stooq 형식 → yfinance 형식 변환.

    예: 'nvo.us' → 'NVO'
        'NVO' → 'NVO' (그대로)
        '005930.KS' → '005930.KS' (그대로)
    """
    t = ticker.strip()
    # Stooq 형식 (.us 접미사) 제거
    if t.lower().endswith(".us"):
        t = t[:-3]
    return t.upper()


def _fetch_price_change(ticker: str) -> Optional[dict]:
    """일간/주간 변동률 — yfinance 사용 (v2 패치)."""
    try:
        import yfinance as yf

        yf_ticker = _normalize_ticker_for_yf(ticker)
        end = datetime.now()
        start = end - timedelta(days=15)

        # yfinance batch download 형식
        df = yf.download(
            yf_ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False,
        )

        if df is None or df.empty:
            logger.warning("[guard yf] %s 빈 결과", ticker)
            return None

        # Close 열 추출 (단일 종목이라 멀티인덱스 평탄화)
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

        if "Close" not in df.columns:
            return None

        closes = df["Close"].astype(float).dropna().values
        if len(closes) < 2:
            return None

        last = float(closes[-1])
        prev = float(closes[-2])
        daily_pct = ((last - prev) / prev) * 100 if prev else 0
        w_idx = max(0, len(closes) - 6)
        weekly_pct = ((last - float(closes[w_idx])) / float(closes[w_idx])) * 100 if closes[w_idx] else 0

        return {
            "close": round(last, 2),
            "prev_close": round(prev, 2),
            "daily_pct": round(daily_pct, 2),
            "weekly_pct": round(weekly_pct, 2),
        }
    except Exception as e:
        logger.warning("[guard yf] %s 실패: %s", ticker, e)
        return None


# ═══════════════════════════════════════════════════════════
# Finnhub 종목별 뉴스
# ═══════════════════════════════════════════════════════════

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
FINNHUB_BASE = "https://finnhub.io/api/v1"


def _fetch_company_news(ticker: str, lookback_hours: int = 24, max_items: int = 3) -> list[dict]:
    """Finnhub /company-news. ticker는 'NVO' 같은 raw 형식."""
    if not FINNHUB_KEY:
        return []
    end = datetime.now().date()
    start = end - timedelta(days=2)

    try:
        symbol = _normalize_ticker_for_yf(ticker)
        params = {
            "symbol": symbol.split(".")[0],  # .KS 접미사 제거
            "from": start.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
            "token": FINNHUB_KEY,
        }
        resp = requests.get(f"{FINNHUB_BASE}/company-news", params=params, timeout=15)
        if resp.status_code != 200:
            return []
        items = resp.json()
        if not isinstance(items, list):
            return []

        cutoff = datetime.now().timestamp() - (lookback_hours * 3600)
        recent = [
            {
                "headline": it.get("headline", ""),
                "summary": it.get("summary", "")[:300],
                "source": it.get("source", ""),
                "datetime": it.get("datetime", 0),
                "url": it.get("url", ""),
            }
            for it in items
            if it.get("datetime", 0) >= cutoff
        ]
        recent.sort(key=lambda x: x["datetime"], reverse=True)
        return recent[:max_items]
    except Exception as e:
        logger.warning("[guard news] %s 실패: %s", ticker, e)
        return []


# ═══════════════════════════════════════════════════════════
# GUARD 에이전트
# ═══════════════════════════════════════════════════════════

class GuardAgent(BaseAgent):
    """GUARD — 보유 포지션 모니터 + 뉴스 해석."""

    def __init__(self):
        super().__init__("guard")
        self.settings = _load_settings()

    def run(self, state: dict) -> dict:
        guard_cfg = self.settings["guard"]
        threshold_pct = guard_cfg["daily_change_threshold_pct"]
        news_lookback = guard_cfg["news_lookback_hours"]
        max_news = guard_cfg["max_news_per_ticker"]

        # 1. 보유 종목 로드
        positions = _load_positions_from_sheets()
        if positions is None:
            self.log.info("[guard] Sheets fallback → portfolio.json")
            positions = _load_positions_fallback()

        if not positions:
            self.log.info("[guard] 보유 종목 없음")
            return self._empty_result()

        held = [p for p in positions if p.get("status", "").upper() in {"OPEN", "ADD", "EXIT_WATCH"}]
        if not held:
            self.log.info("[guard] 보유 상태 종목 없음")
            return self._empty_result()

        self.log.info("[guard] 보유 %d종목 모니터", len(held))

        # 2. 종목별 가격 + 뉴스
        # D87 (Z3-4): 모든 보유 종목 뉴스 fetch (변동 X여도). LLM 1회로 의미 판정.
        results = []
        alerts = []
        quiet = []         # 옛 호환: ticker만
        quiet_full = []    # D87 신규: 가격 + 뉴스 디테일 (digest가 노출)

        for pos in held:
            ticker = pos.get("ticker", "").strip()
            if not ticker:
                continue
            entry = {
                "ticker": ticker,
                "status": pos.get("status", ""),
                "entry_price": pos.get("entry_price"),
                "sl_price": pos.get("sl_price"),
                "memo": pos.get("memo", ""),
            }

            price = _fetch_price_change(ticker)
            if price:
                entry["price"] = price
            time.sleep(0.3)

            # 변동 여부와 무관하게 뉴스 fetch (D87)
            news = _fetch_company_news(ticker, news_lookback, max_news)
            time.sleep(0.5)
            entry["news"] = news

            is_significant = (
                price is not None
                and abs(price.get("daily_pct", 0)) >= threshold_pct
            )
            entry["is_significant"] = is_significant
            results.append(entry)

            # 1차 분류: 변동 있으면 alerts 무조건
            if is_significant:
                alerts.append(entry)
            else:
                # 변동 X — 일단 quiet 후보. 뉴스 있으면 의미 판정 단계로
                quiet_full.append(entry)

        # 3. LLM 의미 판정 — 변동 X + 뉴스 있는 종목만 (D87)
        # 의미 있으면 alerts 승격, 의미 X면 quiet_full 그대로
        if quiet_full:
            promoted = self._classify_quiet_news_significance(quiet_full)
            for tic in promoted:
                # quiet_full에서 제거 + alerts로 이동
                for q in list(quiet_full):
                    if q.get("ticker") == tic:
                        quiet_full.remove(q)
                        alerts.append(q)
                        self.log.info("[guard] %s: 변동 X but 뉴스 의미 → alerts 승격", tic)
                        break

        # quiet (옛 호환): quiet_full에 남은 종목 ticker만
        quiet = [q.get("ticker", "") for q in quiet_full if q.get("ticker")]

        # 4. M7 흡수 — 상관관계 경고
        m7_context = ""
        try:
            from src.modules.m7_correlation import run_m7
            m7_result = run_m7()
            m7_context = m7_result.get("context_text", "")
        except Exception as e:
            self.log.warning("[guard m7] 실패 (무시): %s", e)

        # 5. context_text 생성 (DIGEST/LLM 입력)
        context = self._build_context(results, alerts, quiet, m7_context, threshold_pct)

        return {
            "positions": results,
            "alerts": alerts,
            "quiet": quiet,
            "quiet_full": quiet_full,    # D87 신규: digest가 풍성 노출
            "m7_context": m7_context,
            "context_text": context,
            "held_count": len(held),
        }

    # ─────────────────────────────────────────────
    # LLM — Quiet 종목 뉴스 의미 판정 (D87 신규)
    # 변동 X but 뉴스 있는 종목 일괄 판정
    # ─────────────────────────────────────────────
    def _classify_quiet_news_significance(self, quiet_entries: list[dict]) -> list[str]:
        """변동 X + 뉴스 있는 종목 일괄 LLM 판정.

        Returns: 의미 있는 뉴스 보유 ticker list (alerts 승격 대상).
        실패 시 빈 list (안전: 옛 동작 유지).
        """
        # 뉴스 있는 종목만 추출
        with_news = [q for q in quiet_entries if q.get("news")]
        if not with_news:
            return []

        # 종목별 뉴스 짧게 정리
        items_text = []
        for q in with_news:
            ticker = q.get("ticker", "?")
            news_list = q.get("news", []) or []
            heads = []
            for n in news_list[:3]:
                head = (n.get("headline", "") or "")[:120]
                if head:
                    heads.append(head)
            if heads:
                items_text.append(f"[{ticker}]\n" + "\n".join(f"  - {h}" for h in heads))

        if not items_text:
            return []

        system = (
            "당신은 미국 주식 보유 종목 뉴스 영향도 판정 전문가입니다.\n"
            "역할: 각 종목 뉴스가 단기 주가에 의미 있는 영향을 줄 가능성 판정.\n"
            "원칙:\n"
            "1. 의미 있음 = (실적 발표/예고, 가이던스 변경, 인수합병, 신제품 출시, 규제/소송, 등급 변경, 핵심 인물 변화)\n"
            "2. 의미 없음 = (일반 시장 분석, 주가 가십, 단순 가격 변동 보도, 무관 산업 뉴스)\n"
            "3. 보수적 판정 (애매하면 의미 없음)\n"
            "\n"
            "출력 형식: ticker만 줄별로 (의미 있는 종목만 출력). 의미 없으면 빈 출력.\n"
            "예시 출력:\n"
            "NVDA\n"
            "MSFT\n"
            "(설명/이유 X. ticker만.)"
        )

        user = (
            "다음은 변동 ±2% 미만이지만 뉴스가 있는 종목들입니다. "
            "단기 주가 영향 가능성 있는 ticker만 출력해주세요.\n\n"
            + "\n\n".join(items_text)
        )

        try:
            result = self.call_llm(system, user, max_tokens=200)
            if not result:
                return []
            promoted = []
            for ln in result.strip().split("\n"):
                ln = ln.strip().upper()
                # 코드/노이즈 제거 (영문 + 숫자 + 점만 허용, 1~10자)
                if 1 <= len(ln) <= 10 and all(c.isalnum() or c in ".-" for c in ln):
                    promoted.append(ln)
            return promoted
        except Exception as e:
            self.log.warning("[guard] quiet 뉴스 LLM 판정 실패 (무시): %s", e)
            return []

    def _build_context(self, results, alerts, quiet, m7_context, threshold_pct) -> str:
        date_str = today_kst_str()
        lines = [f"[보유 포지션 — {date_str}]"]
        lines.append(f"총 {len(results)}종목 보유. 변동 {threshold_pct}% 이상 또는 뉴스 있음: {len(alerts)}개")
        lines.append("")

        if alerts:
            lines.append("** 주목 종목 **")
            for a in alerts:
                ticker = a["ticker"]
                price = a.get("price", {})
                if price:
                    lines.append(
                        f"- {ticker} [{a['status']}] ${price.get('close', '?')} "
                        f"일간 {price.get('daily_pct', 0):+.1f}%, 주간 {price.get('weekly_pct', 0):+.1f}%"
                    )
                else:
                    lines.append(f"- {ticker} [{a['status']}] 가격 수집 실패")

                if a.get("news"):
                    for n in a["news"]:
                        lines.append(f"  뉴스 ({n['source']}): {n['headline']}")
                        if n.get("summary"):
                            lines.append(f"    요약: {n['summary'][:200]}")

                if a.get("memo"):
                    lines.append(f"  메모: {a['memo']}")
            lines.append("")

        if quiet:
            lines.append(f"[변동 없음 ({len(quiet)}종목): {', '.join(quiet)}] — 별도 코멘트 불필요")
            lines.append("")

        if m7_context:
            lines.append(m7_context)
            lines.append("")

        return "\n".join(lines)

    def _empty_result(self) -> dict:
        return {
            "positions": [],
            "alerts": [],
            "quiet": [],
            "quiet_full": [],
            "m7_context": "",
            "context_text": "",
            "held_count": 0,
        }

    def _error_output(self, error_msg: str) -> dict:
        return {
            "positions": [],
            "alerts": [],
            "quiet": [],
            "m7_context": "",
            "context_text": f"[GUARD 에러] {error_msg}",
            "held_count": 0,
            "error": error_msg,
        }
