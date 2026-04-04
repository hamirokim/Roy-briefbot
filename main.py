"""
main.py — Roy-브리프봇 오케스트레이션 v3
실행 순서: M2 → M3 → M5 → M4 → M7 → M6 → M1 → 텔레그램
신규: 시장 스냅샷 + 직전 데이터 저장 + 주간/월간 모드
"""

import json
import logging
from pathlib import Path

from src.state import load_state, save_state
from src.telegram import send_telegram
from src.utils import now_kst, today_kst_str, truncate

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

ETF_MAP_PATH = Path(__file__).resolve().parent / "config" / "etf_map.json"


def _load_etf_map() -> dict:
    try:
        with open(ETF_MAP_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("etf_map.json 로드 실패: %s", e)
        return {}


def _sanitize_state(state: dict) -> dict:
    if state.get("m2_history") is None:
        state["m2_history"] = {}
    if state.get("m6_history") is None:
        state["m6_history"] = []
    if state.get("prev_day") is None:
        state["prev_day"] = {}
    return state


def _build_prev_summary(state: dict) -> str:
    """직전 브리핑 데이터 → GPT context용 요약 텍스트."""
    prev = state.get("prev_day", {})
    if not prev or not prev.get("date"):
        return ""

    lines = [f"[직전 브리핑 데이터 — {prev['date']}]"]

    snap = prev.get("snapshot", {})
    for name, info in snap.items():
        if isinstance(info, dict):
            lines.append(f"- {name}: {info.get('close', '?')} (일간 {info.get('daily_pct', '?')}%)")

    vix = prev.get("vix")
    regime = prev.get("vix_regime", "")
    if vix:
        lines.append(f"- VIX: {vix} ({regime})")

    pos = prev.get("positions", "")
    if pos:
        lines.append(f"- 포지션: {pos}")

    return "\n".join(lines)


def _detect_briefing_mode() -> str:
    """요일/날짜 기반 브리핑 모드 결정."""
    now = now_kst()
    if now.day == 1:
        return "monthly"
    if now.weekday() == 0:  # 월요일
        return "weekly"
    return "daily"


def main():
    now = now_kst()
    logger.info("=" * 60)
    logger.info("Roy-브리프봇 시작 — %s", now.strftime("%Y-%m-%d %H:%M KST"))
    logger.info("=" * 60)

    state = load_state()
    state = _sanitize_state(state)
    etf_map = _load_etf_map()

    briefing_mode = _detect_briefing_mode()
    logger.info("브리핑 모드: %s", briefing_mode)

    prev_summary = _build_prev_summary(state)
    if prev_summary:
        logger.info("직전 데이터 로드: %d자", len(prev_summary))

    # ─── M2 ───
    logger.info("─── M2 섹터 로테이션 ───")
    m2_context = ""
    m2_snapshot = {}
    try:
        m2_result = run_m2(etf_map, state)
        m2_context = m2_result.get("context_text", "")
        m2_snapshot = m2_result.get("today_snapshot", {})
        logger.info("M2 완료: %d자, %d ETF", len(m2_context), len(m2_snapshot))
    except Exception as e:
        logger.error("M2 실패: %s", e)

    if m2_snapshot:
        from src.state import prune_m2_history
        m2h = state.get("m2_history", {}) or {}
        m2h[today_kst_str()] = m2_snapshot
        pruned = prune_m2_history(m2h)
        state["m2_history"] = pruned if pruned is not None else m2h

    # ─── M3 ───
    logger.info("─── M3 역발상 필터 ───")
    m3_context = ""
    m3_candidates = []
    try:
        m3_result = run_m3(state)
        m3_context = m3_result.get("context_text", "")
        m3_candidates = m3_result.get("candidates", [])
        logger.info("M3 완료: %d자, %d개 후보", len(m3_context), len(m3_candidates))
    except Exception as e:
        logger.error("M3 실패: %s", e)

    # M3 → M6 기록
    if m3_candidates:
        try:
            new_entries = candidates_to_history_entries(m3_candidates)
            m6h = state.get("m6_history", []) or []
            added = deduplicate_entries(m6h, new_entries)
            if added:
                m6h.extend(added)
                state["m6_history"] = m6h
                logger.info("M6 기록: %d개 추가 (총 %d개)", len(added), len(m6h))
        except Exception as e:
            logger.error("M6 기록 실패: %s", e)

    # ─── M5 (시장 스냅샷 + VIX + 캘린더) ───
    logger.info("─── M5 리스크 대시보드 ───")
    m5_context = ""
    m5_snapshot = []
    m5_vix = None
    m5_vix_regime = None
    try:
        m5_result = run_m5(state)
        m5_context = m5_result.get("context_text", "")
        m5_snapshot = m5_result.get("snapshot", [])
        m5_vix = m5_result.get("vix")
        m5_vix_regime = m5_result.get("vix_regime")
        logger.info("M5 완료: %d자, %d자산, VIX=%s", len(m5_context), len(m5_snapshot), m5_vix)
    except Exception as e:
        logger.error("M5 실패: %s", e)

    # ─── M4 ───
    logger.info("─── M4 포지션 트래커 ───")
    m4_context = ""
    try:
        m4_result = run_m4()
        m4_context = m4_result.get("context_text", "")
        pos_count = m4_result.get("position_count", 0)
        logger.info("M4 완료: %d개 포지션, %d자", pos_count, len(m4_context))
    except Exception as e:
        logger.error("M4 실패: %s", e)

    # ─── ANALYTICS (지표 피드백 루프) ───
    analytics_context = ""
    if briefing_mode in ("weekly", "monthly"):
        logger.info("─── ANALYTICS 지표 성과 ───")
        try:
            from src.collectors.sheets import read_analytics
            analytics_context = read_analytics(min_closed=10)
            if analytics_context:
                logger.info("ANALYTICS 로드: %d자", len(analytics_context))
            else:
                logger.info("ANALYTICS 스킵 (CLOSED < 10건 또는 데이터 없음)")
        except Exception as e:
            logger.warning("ANALYTICS 실패: %s", e)

    # ─── M7 ───
    logger.info("─── M7 상관관계 경고 ───")
    m7_context = ""
    try:
        m7_result = run_m7()
        m7_context = m7_result.get("context_text", "")
        logger.info("M7 완료: %d개 보유, %d개 경고쌍", m7_result.get("held_count", 0), m7_result.get("alert_count", 0))
    except Exception as e:
        logger.error("M7 실패: %s", e)

    # ─── M6 ───
    logger.info("─── M6 피드백 루프 ───")
    m6_context = ""
    try:
        m6_result = run_m6(state)
        m6_context = m6_result.get("context_text", "")
        logger.info("M6 완료: %d개 추적, %d자", m6_result.get("track_count", 0), len(m6_context))
    except Exception as e:
        logger.error("M6 실패: %s", e)

    # ─── M1 AI 브리핑 ───
    logger.info("─── M1 AI 브리핑 ───")
    try:
        m1_result = run_m1(
            m2_context=m2_context,
            m3_context=m3_context,
            m5_context=m5_context,
            m4_context=m4_context,
            m7_context=m7_context,
            m6_context=m6_context,
            prev_summary=prev_summary,
            briefing_mode=briefing_mode,
            analytics_context=analytics_context,
        )
        briefing = m1_result.get("briefing", "")
        used_llm = m1_result.get("used_llm", False)
        news_count = m1_result.get("news_count", 0)
        logger.info("M1 완료: LLM=%s, 뉴스=%d건, %d자", used_llm, news_count, len(briefing))
    except Exception as e:
        logger.error("M1 실패: %s", e)
        briefing = ""

    # ─── 텔레그램 ───
    if briefing:
        ok = send_telegram(truncate(briefing, 4000))
        logger.info("텔레그램 %s", "성공" if ok else "실패")
    else:
        logger.error("브리핑 없음 — 전송 스킵")

    # ─── 직전 데이터 저장 (다음 브리핑용) ───
    snap_dict = {}
    for s in m5_snapshot:
        snap_dict[s["name"]] = {"close": s["close"], "daily_pct": s["daily_pct"]}

    state["prev_day"] = {
        "date": now.strftime("%Y-%m-%d"),
        "snapshot": snap_dict,
        "vix": m5_vix,
        "vix_regime": m5_vix_regime,
        "positions": m4_context[:200] if m4_context else "",  # 압축 저장
    }

    state["last_run_kst"] = now.strftime("%Y-%m-%d %H:%M:%S")
    save_state(state)

    logger.info("=" * 60)
    logger.info("Roy-브리프봇 완료")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
