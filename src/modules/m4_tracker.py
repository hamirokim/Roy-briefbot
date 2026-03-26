"""
src/modules/m4_tracker.py
M4 포지션 트래커 — 관심 종목 상태 추적 + 현재가 수집 + M1 context 생성

사용법:
    from src.modules.m4_tracker import run_m4
    result = run_m4()
    # result = {"context_text": str, "position_count": int}

상태머신:
    WATCH     → 관심 종목 (브리프봇 추천, 미진입)
    ARMED     → 메인지표 arm 진행 중 (로이가 수동 변경)
    OPEN      → 진입 완료 (진입가/날짜/SL 기록)
    ADD       → 추가 매수 구간
    EXIT_WATCH → TP 신호 접근 중
"""

import json
import logging
import os
import time
from pathlib import Path

from src.collectors.stooq import fetch_closes
from src.utils import now_kst

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────
PORTFOLIO_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "portfolio.json"
MAX_POSITIONS = 5
VALID_STATUSES = {"WATCH", "ARMED", "OPEN", "ADD", "EXIT_WATCH"}

# Stooq 요청 간 딜레이 (초) — rate limit 방지
STOOQ_DELAY = 0.3


# ─────────────────────────────────────────────
# portfolio.json 로드
# ─────────────────────────────────────────────
def _load_portfolio() -> list[dict]:
    """
    config/portfolio.json에서 포지션 목록 로드.
    파일 없거나 비어 있으면 빈 리스트 반환.
    max_positions 초과 시 added 날짜 기준으로 최신 5개만 유지.
    """
    if not PORTFOLIO_PATH.exists():
        logger.info("portfolio.json 없음 — M4 스킵")
        return []

    try:
        raw = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception) as e:
        logger.error("portfolio.json 파싱 실패: %s", e)
        return []

    positions = raw.get("positions", [])
    if not positions:
        logger.info("포지션 0개 — M4 스킵")
        return []

    # 유효성 검증: 필수 필드 체크
    valid = []
    for p in positions:
        ticker = p.get("ticker", "").strip()
        status = p.get("status", "").strip().upper()

        if not ticker:
            logger.warning("ticker 비어 있는 항목 무시")
            continue
        if status not in VALID_STATUSES:
            logger.warning("잘못된 상태 '%s' (종목: %s) — 무시", status, ticker)
            continue

        # OPEN/ADD/EXIT_WATCH 상태에서 entry_price 필수
        if status in ("OPEN", "ADD", "EXIT_WATCH"):
            if not p.get("entry_price"):
                logger.warning("%s 상태인데 entry_price 없음 (%s) — WATCH로 강제 변환", status, ticker)
                p["status"] = "WATCH"

        valid.append(p)

    # max_positions 초과 시 → added 날짜 최신 순으로 자르기
    max_pos = raw.get("max_positions", MAX_POSITIONS)
    if len(valid) > max_pos:
        logger.warning("포지션 %d개 > 최대 %d개 — 최신 %d개만 사용", len(valid), max_pos, max_pos)
        valid.sort(key=lambda x: x.get("added", ""), reverse=True)
        valid = valid[:max_pos]

    return valid


# ─────────────────────────────────────────────
# Stooq 현재가 수집
# ─────────────────────────────────────────────
def _fetch_current_prices(tickers: list[str]) -> dict[str, float | None]:
    """
    Stooq에서 종목별 최근 종가 수집.
    Returns: {ticker: close_price or None}
    """
    prices = {}
    for ticker in tickers:
        try:
            closes = fetch_closes(ticker, days=5)
            if closes is not None and len(closes) > 0:
                prices[ticker] = float(closes.iloc[-1])
            else:
                logger.warning("Stooq 데이터 없음: %s", ticker)
                prices[ticker] = None
        except Exception as e:
            logger.warning("Stooq 수집 실패 (%s): %s", ticker, e)
            prices[ticker] = None

        time.sleep(STOOQ_DELAY)

    return prices


# ─────────────────────────────────────────────
# 상태별 context 텍스트 생성
# ─────────────────────────────────────────────
def _format_position(pos: dict, current_price: float | None) -> str:
    """개별 포지션의 context 텍스트 생성."""
    ticker = pos["ticker"].upper().replace(".US", "")
    status = pos["status"]
    entry_price = pos.get("entry_price")
    sl_price = pos.get("sl_price")
    memo = pos.get("memo", "")

    parts = [f"• {ticker} [{status}]"]

    # 현재가 정보
    if current_price is not None:
        parts.append(f"  현재가: ${current_price:.2f}")

        # OPEN 이상: 진입가 대비 수익률
        if entry_price and status in ("OPEN", "ADD", "EXIT_WATCH"):
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            pnl_sign = "+" if pnl_pct >= 0 else ""
            parts.append(f"  진입가: ${entry_price:.2f} → 수익률: {pnl_sign}{pnl_pct:.1f}%")

            # SL 거리
            if sl_price:
                sl_dist_pct = ((current_price - sl_price) / current_price) * 100
                parts.append(f"  SL: ${sl_price:.2f} (현재가 대비 -{sl_dist_pct:.1f}%)")
    else:
        parts.append("  현재가: 수집 실패")

    # 메모
    if memo:
        parts.append(f"  메모: {memo}")

    # 상태별 GPT 지시 힌트
    hint_map = {
        "WATCH": "→ 지시: 진입 타이밍 접근 여부 판단. 메인지표 arm 떴는지 체크하라는 톤.",
        "ARMED": "→ 지시: gate 진입 조건 충족 임박. 긴장감 유지, 뉴스 리스크 체크.",
        "OPEN": "→ 지시: 홀딩 근거 유지 여부 + SL 거리 리스크. 방어적 톤.",
        "ADD": "→ 지시: 추가 매수 신중하게. 집중 리스크 경고.",
        "EXIT_WATCH": "→ 지시: TP 접근 중. 수익 실현 준비. 탈출 타이밍 판단.",
    }
    parts.append(hint_map.get(status, ""))

    return "\n".join(parts)


# ─────────────────────────────────────────────
# 메인 실행 함수
# ─────────────────────────────────────────────
def run_m4() -> dict:
    """
    M4 포지션 트래커 실행.

    Returns:
        {
            "context_text": str,      # M1 GPT에 주입할 컨텍스트 (빈 문자열이면 생략)
            "position_count": int,    # 유효 포지션 수
        }
    """
    logger.info("=" * 50)
    logger.info("M4 포지션 트래커 시작")
    logger.info("=" * 50)

    positions = _load_portfolio()

    if not positions:
        logger.info("포지션 없음 — M4 컨텍스트 생략 (희소 원칙)")
        return {"context_text": "", "position_count": 0}

    # 종목별 현재가 수집
    tickers = [p["ticker"] for p in positions]
    logger.info("현재가 수집: %s", ", ".join(tickers))
    prices = _fetch_current_prices(tickers)

    # 상태별 분류
    status_order = ["OPEN", "ADD", "EXIT_WATCH", "ARMED", "WATCH"]
    positions.sort(key=lambda x: status_order.index(x["status"]) if x["status"] in status_order else 99)

    # context 텍스트 조립
    date_str = now_kst().strftime("%Y-%m-%d")
    lines = [f"[포지션 트래커 — {date_str}]"]
    lines.append(f"추적 종목: {len(positions)}개")
    lines.append("")

    # 상태별 요약 카운트
    status_counts = {}
    for p in positions:
        s = p["status"]
        status_counts[s] = status_counts.get(s, 0) + 1
    summary_parts = [f"{s}: {c}개" for s, c in status_counts.items()]
    lines.append("상태 요약: " + " / ".join(summary_parts))
    lines.append("")

    # 개별 포지션 상세
    for p in positions:
        price = prices.get(p["ticker"])
        lines.append(_format_position(p, price))
        lines.append("")

    # GPT 전체 지시
    lines.append("─── M4 해석 가이드 (GPT용) ───")
    lines.append("위 포지션에 대해 [포지션 체크] 섹션을 작성하라.")
    lines.append("상태별로 다른 톤과 액션을 제시하라. 각 종목별 '→ 지시' 힌트를 참고.")
    lines.append("포지션이 없는 상태(예: OPEN 0개)는 언급하지 마라.")
    lines.append("이 데이터는 스크리닝 참고용일 뿐, 매매 시그널이 아니다.")

    context_text = "\n".join(lines)

    logger.info("M4 완료: %d개 포지션, %d자 컨텍스트", len(positions), len(context_text))

    return {
        "context_text": context_text,
        "position_count": len(positions),
    }


# ─────────────────────────────────────────────
# 단독 테스트
# ─────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
    result = run_m4()
    print(f"\n=== M4 결과 (포지션: {result['position_count']}개) ===\n")
    print(result["context_text"])
