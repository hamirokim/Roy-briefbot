"""
main.py — Roy-브리프봇 오케스트레이션
실행 순서: M2(섹터 로테이션) → M3(역발상 필터) → M1(AI 종합 브리핑) → 텔레그램 전송
"""

import logging
import sys

from src.state import load_state, save_state
from src.telegram import send_message
from src.utils import now_kst, truncate

# 모듈 임포트
from src.modules.m2_rotation import run_m2
from src.modules.m3_contrarian import run_m3
from src.modules.m1_briefing import run_m1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def main():
    logger.info("=" * 60)
    logger.info("Roy-브리프봇 시작 — %s", now_kst().strftime("%Y-%m-%d %H:%M KST"))
    logger.info("=" * 60)

    state = load_state()

    # ───────────────────────────────────────
    # M2: 섹터 로테이션 (context_text만 반환, 텔레그램 X)
    # ───────────────────────────────────────
    logger.info("─── M2 섹터 로테이션 ───")
    try:
        m2_result = run_m2(state)
        m2_context = m2_result.get("context_text", "")
        logger.info("M2 완료: %d자 컨텍스트", len(m2_context))
    except Exception as e:
        logger.error("M2 실패: %s", e)
        m2_context = ""

    # ───────────────────────────────────────
    # M3: 역발상 필터 (context_text만 반환, 텔레그램 X)
    # ───────────────────────────────────────
    logger.info("─── M3 역발상 필터 ───")
    try:
        m3_result = run_m3(state)
        m3_context = m3_result.get("context_text", "")
        logger.info("M3 완료: %d자 컨텍스트", len(m3_context))
    except Exception as e:
        logger.error("M3 실패: %s", e)
        m3_context = ""

    # ───────────────────────────────────────
    # M1: AI 종합 브리핑 (뉴스 수집 + GPT + 텔레그램)
    # ───────────────────────────────────────
    logger.info("─── M1 AI 브리핑 ───")
    try:
        m1_result = run_m1(m2_context=m2_context, m3_context=m3_context)
        briefing = m1_result.get("briefing", "")
        used_llm = m1_result.get("used_llm", False)
        news_count = m1_result.get("news_count", 0)

        logger.info(
            "M1 완료: LLM=%s, 뉴스=%d건, 브리핑=%d자",
            used_llm, news_count, len(briefing),
        )
    except Exception as e:
        logger.error("M1 실패: %s", e)
        briefing = ""
        used_llm = False

    # ───────────────────────────────────────
    # 텔레그램 전송 (단일 메시지)
    # ───────────────────────────────────────
    if briefing:
        # 텔레그램 4096자 제한
        msg = truncate(briefing, 4000)
        ok = send_message(msg)
        if ok:
            logger.info("텔레그램 전송 성공")
        else:
            logger.error("텔레그램 전송 실패")
    else:
        logger.error("브리핑 내용 없음 — 전송 스킵")

    # ───────────────────────────────────────
    # 상태 저장
    # ───────────────────────────────────────
    state["last_run_kst"] = now_kst().strftime("%Y-%m-%d %H:%M:%S")
    save_state(state)

    logger.info("=" * 60)
    logger.info("Roy-브리프봇 완료")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
