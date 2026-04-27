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

from src.utils import now_kst, today_kst_str

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
            "last_run_at": now_kst().isoformat(),
            "last_monthly_run": state.get("last_monthly_run", ""),
            "last_weekly_run": state.get("last_weekly_run", ""),
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


def _detect_briefing_mode(state: dict) -> str:
    """발송 모드 자동 감지.

    우선순위: monthly > weekly > daily
    - monthly: 매월 첫 발송 (state["last_monthly_run"] 월이 다르면 트리거)
              요일 무관 — 1일이 평일이면 1일, 주말이면 다음 발송일에 자동
    - weekly:  월요일 첫 발송에만 (전주 종합 + 새 주 방향 — 월요일 컨셉 고정)
              화~토 첫 발송이 weekly 되는 사고 방지
    - daily:   그 외 모든 발송 (화~금 + 토)

    토요일은 미국 금요일 close 신선 데이터를 받는 daily.
    월요일은 같은 금요일 close 데이터지만 + 주말 뉴스 + 종합 = weekly.
    """
    now = now_kst()
    today = now.date()
    today_yyyymm = today.strftime("%Y-%m")

    # 1. 매월 첫 발송 → monthly (요일 무관)
    last_monthly = state.get("last_monthly_run", "") or ""
    if not last_monthly or last_monthly[:7] != today_yyyymm:
        return "monthly"

    # 2. 월요일이고 이번 주 weekly 아직 안 돌았으면 → weekly
    if today.weekday() == 0:  # 0 = 월요일
        iso_year, iso_week, _ = today.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        last_weekly = state.get("last_weekly_run", "") or ""
        if last_weekly != week_key:
            return "weekly"

    # 3. 그 외 → daily
    return "daily"


def _stamp_mode_run(state: dict, mode: str) -> None:
    """발송 후 last_*_run 기록. monthly이면 weekly까지 함께 갱신 (포함 관계)."""
    today = today_kst_str()
    today_dt = now_kst().date()
    iso_year, iso_week, _ = today_dt.isocalendar()
    week_key = f"{iso_year}-W{iso_week:02d}"

    if mode == "monthly":
        state["last_monthly_run"] = today
        state["last_weekly_run"] = week_key
    elif mode == "weekly":
        state["last_weekly_run"] = week_key


def update_m2_history_from_regime(state: dict) -> None:
    """REGIME 출력에서 RRG 스냅샷 추출 → m2_history 누적."""
    try:
        rrg = state.get("regime_out", {}).get("rrg", {})
        snapshot = rrg.get("snapshot", {})
        if not snapshot:
            return
        m2_history = state.get("m2_history", {})
        today = state.get("date") or today_kst_str()
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
        from src.telegram import send_telegram as _send_tg
        return _send_tg(text)
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
        date_str = today_kst_str()
        save_briefing(date_str, detailed_text, mode)
        logger.info("저널 BRIEFING 저장 완료")
    except Exception as e:
        logger.warning("저널 BRIEFING 저장 실패 (텔레그램은 정상): %s", e)


# ═══════════════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════════════

def main(briefing_mode: str = "auto") -> int:
    """Roy-briefbot v2.0 메인 실행.

    Args:
        briefing_mode: "auto" | "daily" | "weekly" | "monthly"
                       "auto"이면 state 기반 자동 감지

    Returns:
        0 = 성공, 1 = 실패
    """
    logger.info("=" * 60)
    logger.info("Roy-briefbot v2.0 시작 (요청 mode=%s)", briefing_mode)
    logger.info("=" * 60)

    # 1. State 로드
    state = load_state()

    # 1-2. 모드 자동 감지 (cli가 'auto'이거나 미지정 시)
    if briefing_mode == "auto" or briefing_mode not in ("daily", "weekly", "monthly"):
        briefing_mode = _detect_briefing_mode(state)
        logger.info("자동 감지 mode = %s", briefing_mode)

    state["date"] = today_kst_str()
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

    # 4-2. 모드별 last_*_run 기록 (다음 실행 시 자동 감지의 근거)
    # state.last_*_run은 load_state로 가져온 값이 result에는 없을 수 있어 명시 복사
    result["last_monthly_run"] = state.get("last_monthly_run", "")
    result["last_weekly_run"] = state.get("last_weekly_run", "")
    _stamp_mode_run(result, briefing_mode)
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
    logger.info("Roy-briefbot v2.0 종료 (실행 mode=%s)", briefing_mode)
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    # CLI 인자 처리 (briefing_mode)
    # 'auto'(기본) = 자동 감지, 명시 모드 = 그대로 사용
    mode = "auto"
    if len(sys.argv) > 1 and sys.argv[1] in ("auto", "daily", "weekly", "monthly"):
        mode = sys.argv[1]

    exit_code = main(briefing_mode=mode)
    sys.exit(exit_code)
