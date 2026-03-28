"""
main.py — Roy-브리프봇 오케스트레이션
실행 순서: M2 → M3 → M5 → M4 → M7 → M6 → M1 → 텔레그램
"""

import json
import logging
import sys
from pathlib import Path

from src.state import load_state, save_state
from src.telegram import send_telegram
from src.utils import now_kst, today_kst_str, truncate

# 모듈 임포트
from src.modules.m2_rotation import run_m2
from src.modules.m3_contrarian import run_m3
from src.modules.m5_risk import run as run_m5
from src.modules.m4_tracker import run_m4
from src.modules.m7_correlation import run_m7
from src.modules.m6_feedback import run_m6, candidates_to_history_entries, deduplicate_entries
from src.modules.m1_briefing import run_m1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# ── ETF 맵 경로 ──
ETF_MAP_PATH = Path(__file__).resolve().parent / "config" / "etf_map.json"


def _load_etf_map() -> dict:
    """config/etf_map.json 로드."""
    try:
        with open(ETF_MAP_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("etf_map.json 로드 실패: %s", e)
        return {}


def _sanitize_state(state: dict) -> dict:
    """state의 None 값들을 안전한 기본값으로 보정."""
    if state.get("m2_history") is None:
        state["m2_history"] = {}
        logger.warning("state.m2_history가 None → {} 로 보정")
    if state.get("m6_history") is None:
        state["m6_history"] = []
        logger.warning("state.m6_history가 None → [] 로 보정")
    return state


def main():
    logger.info("=" * 60)
    logger.info("Roy-브리프봇 시작 — %s", now_kst().strftime("%Y-%m-%d %H:%M KST"))
    logger.info("=" * 60)

    state = load_state()
    state = _sanitize_state(state)
    etf_map = _load_etf_map()

    if not etf_map:
        logger.error("etf_map이 비어있음 — M2 실행 불가")

    # ───────────────────────────────────────
    # M2: 섹터 로테이션
    # ───────────────────────────────────────
    logger.info("─── M2 섹터 로테이션 ───")
    m2_context = ""
    m2_snapshot = {}
    try:
        m2_result = run_m2(etf_map, state)
        m2_context = m2_result.get("context_text", "")
        m2_snapshot = m2_result.get("today_snapshot", {})
        logger.info("M2 완료: %d자 컨텍스트, %d ETF 분류", len(m2_context), len(m2_snapshot))
    except Exception as e:
        logger.error("M2 실패: %s", e)

    # M2 히스토리 업데이트
    if m2_snapshot:
        from src.state import prune_m2_history
        m2_history = state.get("m2_history", {})
        if m2_history is None:
            m2_history = {}
        m2_history[today_kst_str()] = m2_snapshot
        pruned = prune_m2_history(m2_history)
        state["m2_history"] = pruned if pruned is not None else m2_history

    # ───────────────────────────────────────
    # M3: 역발상 필터
    # ───────────────────────────────────────
    logger.info("─── M3 역발상 필터 ───")
    m3_context = ""
    m3_candidates = []
    try:
        m3_result = run_m3(state)
        m3_context = m3_result.get("context_text", "")
        m3_candidates = m3_result.get("candidates", [])
        logger.info("M3 완료: %d자 컨텍스트, %d개 후보", len(m3_context), len(m3_candidates))
    except Exception as e:
        logger.error("M3 실패: %s", e)

    # ── M3 후보 → m6_history에 기록 ──
    if m3_candidates:
        try:
            new_entries = candidates_to_history_entries(m3_candidates)
            m6_history = state.get("m6_history", [])
            if m6_history is None:
                m6_history = []
            added = deduplicate_entries(m6_history, new_entries)
            if added:
                m6_history.extend(added)
                state["m6_history"] = m6_history
                logger.info("M6 기록: %d개 신규 추가 (총 %d개)", len(added), len(m6_history))
            else:
                logger.info("M6 기록: 신규 없음 (이미 추적 중)")
        except Exception as e:
            logger.error("M6 기록 실패: %s", e)

    # ───────────────────────────────────────
    # M5: 리스크 대시보드
    # ───────────────────────────────────────
    logger.info("─── M5 리스크 대시보드 ───")
    m5_context = ""
    try:
        m5_context = run_m5(state)
        logger.info("M5 완료: %d자 컨텍스트", len(m5_context))
    except Exception as e:
        logger.error("M5 실패: %s", e)

    # ───────────────────────────────────────
    # M4: 포지션 트래커
    # ───────────────────────────────────────
    logger.info("─── M4 포지션 트래커 ───")
    m4_context = ""
    try:
        m4_result = run_m4()
        m4_context = m4_result.get("context_text", "")
        pos_count = m4_result.get("position_count", 0)
        logger.info("M4 완료: %d개 포지션, %d자 컨텍스트", pos_count, len(m4_context))
    except Exception as e:
        logger.error("M4 실패: %s", e)

    # ───────────────────────────────────────
    # M7: 상관관계 경고
    # ───────────────────────────────────────
    logger.info("─── M7 상관관계 경고 ───")
    m7_context = ""
    try:
        m7_result = run_m7()
        m7_context = m7_result.get("context_text", "")
        alert_count = m7_result.get("alert_count", 0)
        held_count = m7_result.get("held_count", 0)
        logger.info("M7 완료: %d개 보유, %d개 경고쌍, %d자 컨텍스트", held_count, alert_count, len(m7_context))
    except Exception as e:
        logger.error("M7 실패: %s", e)

    # ───────────────────────────────────────
    # M6: 피드백 루프
    # ───────────────────────────────────────
    logger.info("─── M6 피드백 루프 ───")
    m6_context = ""
    try:
        m6_result = run_m6(state)
        m6_context = m6_result.get("context_text", "")
        track_count = m6_result.get("track_count", 0)
        logger.info("M6 완료: %d개 추적, %d자 컨텍스트", track_count, len(m6_context))
    except Exception as e:
        logger.error("M6 실패: %s", e)

    # ───────────────────────────────────────
    # M1: AI 종합 브리핑
    # ───────────────────────────────────────
    logger.info("─── M1 AI 브리핑 ───")
    try:
        m1_result = run_m1(
            m2_context=m2_context,
            m3_context=m3_context,
            m5_context=m5_context,
            m4_context=m4_context,
            m7_context=m7_context,
            m6_context=m6_context,
        )
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

    # ───────────────────────────────────────
    # 텔레그램 전송
    # ───────────────────────────────────────
    if briefing:
        msg = truncate(briefing, 4000)
        ok = send_telegram(msg)
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
