"""
main.py — Roy-briefbot v2.0 메인 엔트리포인트

LangGraph 기반 4 에이전트 워크플로:
  SCOUT (발굴) → GUARD (모니터) → REGIME (매크로 + 해석) → DIGEST (종합)

기존 M1~M7 직접 호출은 제거. 각 모듈은 에이전트 안에서 흡수됨:
  - M2 (섹터 RRG) → REGIME 안에서 호출
  - M4 (트래커) → GUARD 안에서 흡수
  - M5 (리스크) → REGIME 안에서 흡수
  - M6 (피드백) → 향후 SCOUT cooldown으로 통합 (현재 미사용)
  - M7 (상관) → GUARD 안에서 호출

GitHub Actions 스케줄: KST 07:10 (.github/workflows/daily.yml)
"""

import json
import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

# 로깅 설정 (가장 먼저)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


# ═══════════════════════════════════════════════════════════
# 경로 설정
# ═══════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "state.json"
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


# ═══════════════════════════════════════════════════════════
# State 영속화
# ═══════════════════════════════════════════════════════════

def load_state() -> dict:
    """state.json 로드 — 없으면 빈 dict."""
    if not STATE_PATH.exists():
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("state.json 로드 실패: %s — 빈 state로 시작", e)
        return {}


def save_state(state: dict) -> None:
    """state.json 저장."""
    try:
        # LangGraph state는 너무 커서 저장 시 필터
        persistable = {
            "last_run_date": state.get("date"),
            "last_run_at": datetime.now().isoformat(),
            "m2_history": state.get("m2_history", {}),
            "scout_cooldown": state.get("scout_cooldown", {}),
            "prev_day": {
                "candidates": state.get("scout_out", {}).get("candidates", []),
                "alerts_count": len(state.get("guard_out", {}).get("alerts", [])),
                "vix": state.get("regime_out", {}).get("vix"),
            },
        }
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(persistable, f, ensure_ascii=False, indent=2)
        logger.info("state.json 저장 완료")
    except Exception as e:
        logger.error("state.json 저장 실패: %s", e)


def update_m2_history_from_regime(state: dict) -> None:
    """REGIME 출력에서 RRG 스냅샷 추출 → m2_history 누적."""
    try:
        rrg = state.get("regime_out", {}).get("rrg", {})
        snapshot = rrg.get("snapshot", {})
        if not snapshot:
            return
        m2_history = state.get("m2_history", {})
        today = state.get("date") or datetime.now().strftime("%Y-%m-%d")
        m2_history[today] = snapshot
        # 30일치만 유지 (메모리 절약)
        sorted_dates = sorted(m2_history.keys(), reverse=True)
        m2_history = {d: m2_history[d] for d in sorted_dates[:30]}
        state["m2_history"] = m2_history
    except Exception as e:
        logger.warning("m2_history 업데이트 실패: %s", e)


def update_cooldown_from_scout(state: dict) -> None:
    """SCOUT new_cooldown → state에 저장."""
    new_cooldown = state.get("scout_out", {}).get("new_cooldown")
    if new_cooldown is not None:
        state["scout_cooldown"] = new_cooldown


# ═══════════════════════════════════════════════════════════
# 텔레그램 발송
# ═══════════════════════════════════════════════════════════

def send_telegram(text: str) -> bool:
    """기존 src.telegram 모듈 활용."""
    try:
        from src.telegram import send_telegram
        return send_telegram(text)
    except Exception as e:
        logger.error("텔레그램 발송 실패: %s", e)
        return False


# ═══════════════════════════════════════════════════════════
# 저널 BRIEFING 시트 저장
# ═══════════════════════════════════════════════════════════

def save_to_sheets(detailed_text: str, mode: str = "daily") -> None:
    """기존 sheets.save_briefing 활용."""
    try:
        from src.collectors.sheets import save_briefing
        date_str = datetime.now().strftime("%Y-%m-%d")
        save_briefing(date_str, detailed_text, mode)
        logger.info("저널 BRIEFING 저장 완료")
    except Exception as e:
        logger.warning("저널 BRIEFING 저장 실패 (텔레그램은 정상): %s", e)


# ═══════════════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════════════

def main(briefing_mode: str = "daily") -> int:
    """Roy-briefbot v2.0 메인 실행.

    Args:
        briefing_mode: "daily" | "weekly" | "monthly"

    Returns:
        0 = 성공, 1 = 실패
    """
    logger.info("=" * 60)
    logger.info("Roy-briefbot v2.0 시작 (mode=%s)", briefing_mode)
    logger.info("=" * 60)

    # 1. State 로드
    state = load_state()
    state["date"] = datetime.now().strftime("%Y-%m-%d")
    state["briefing_mode"] = briefing_mode
    state["errors"] = []

    # 2. LangGraph 빌드 + 실행
    try:
        from src.graph import build_graph
        app = build_graph()
        logger.info("LangGraph compile OK")
    except Exception as e:
        logger.error("LangGraph 빌드 실패: %s\n%s", e, traceback.format_exc())
        send_telegram(f"⚠️ Roy-briefbot 시작 실패: {e}")
        return 1

    # 3. 워크플로 실행
    try:
        result = app.invoke(state)
        logger.info("LangGraph invoke 완료")
    except Exception as e:
        logger.error("LangGraph invoke 실패: %s\n%s", e, traceback.format_exc())
        send_telegram(f"⚠️ Roy-briefbot 실행 실패: {e}")
        return 1

    # 4. State 영속화 (다음 실행에서 사용)
    update_m2_history_from_regime(result)
    update_cooldown_from_scout(result)
    save_state(result)

    # 5. 출력 발송
    digest_out = result.get("digest_out", {})
    telegram_text = digest_out.get("telegram_text", "")
    sheets_text = digest_out.get("sheets_text", "")

    if not telegram_text:
        logger.warning("DIGEST 출력 없음 — fallback 사용")
        telegram_text = "⚠️ Roy-briefbot — DIGEST 출력 없음. 시스템 점검 필요."

    # 텔레그램
    sent = send_telegram(telegram_text)
    if sent:
        logger.info("텔레그램 발송 OK (%d자)", len(telegram_text))
    else:
        logger.error("텔레그램 발송 실패")

    # 저널 BRIEFING 시트
    if sheets_text:
        save_to_sheets(sheets_text, briefing_mode)

    # 6. 결과 로깅
    errors = result.get("errors", [])
    if errors:
        logger.warning("실행 중 에러 %d건:", len(errors))
        for e in errors:
            logger.warning("  - %s", e)

    logger.info("=" * 60)
    logger.info("Roy-briefbot v2.0 종료")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    # CLI 인자 처리 (briefing_mode)
    mode = "daily"
    if len(sys.argv) > 1 and sys.argv[1] in ("daily", "weekly", "monthly"):
        mode = sys.argv[1]

    exit_code = main(briefing_mode=mode)
    sys.exit(exit_code)
