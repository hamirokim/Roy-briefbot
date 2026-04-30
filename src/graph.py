"""
src/graph.py — LangGraph 메인 워크플로

4 에이전트 병렬 실행 구조:
  scout, guard, regime → digest

조건부 라우팅 예시 (향후 확장):
  - VIX EXTREME (>40) → SCOUT 스킵
  - 모든 에이전트 실패 → fallback 메시지

D91 박제 (2026-04-30): m6_node에 SCOUT 시트 적재 hook 추가.
  - SCOUT 후보 발화 시 자동으로 'SCOUT 후보발굴' / 'SCOUT 통계' 시트 생성/업데이트
  - 매일 follow-up 가격 (+5d/+28d) + POSITIONS 매핑 동기화
  - 시트 작업 실패해도 메인 워크플로 영향 X (try/except)
"""

import logging
import operator
from typing import TypedDict, Annotated, Optional

from langgraph.graph import StateGraph, END

from src.agents.scout import ScoutAgent
from src.agents.guard import GuardAgent
from src.agents.regime import RegimeAgent
from src.agents.digest import DigestAgent

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# State 스키마 — 4 에이전트가 공유
# ═══════════════════════════════════════════════════════════

class BriefBotState(TypedDict, total=False):
    """LangGraph 상태 객체.

    각 노드는 자기 영역만 write, 다른 영역은 read-only.
    공유 데이터(date, portfolio)는 read 전용.
    """

    # ── 입력 (main.py에서 주입) ──
    date: str                          # "2026-04-19"
    briefing_mode: str                 # "daily" | "weekly" | "monthly"
    portfolio: list                    # Sheets에서 읽은 보유 포지션

    # ── 영속 상태 (state.json 누적) ──
    m2_history: dict                   # 섹터 RRG 히스토리 (REGIME 사용)
    m6_history: list                   # SCOUT 후보 추적 history (M6 D86)
    scout_cooldown: dict               # 신호별 cooldown {ticker: last_alert_date}
    prev_day: dict                     # 어제 브리핑 데이터
    macro_pending: dict                # 발표 대기 매크로 이벤트

    # ── 각 에이전트 출력 ──
    scout_out: dict                    # SCOUT: candidates, scanned_total, by_country
    guard_out: dict                    # GUARD: positions_status, news_events
    regime_out: dict                   # REGIME: vix, sectors, macro_events, fx
    m6_out: dict                       # M6: summary_text, detailed_lines, track_count
    digest_out: dict                   # DIGEST: telegram_text, sheets_text

    # ── 메타 ──
    errors: Annotated[list, operator.add]   # 에이전트별 에러 누적
    skipped: Annotated[list, operator.add]  # 조건부 스킵된 노드


# ═══════════════════════════════════════════════════════════
# 노드 함수 — 각 에이전트를 LangGraph 노드로 wrap
# ═══════════════════════════════════════════════════════════

def scout_node(state: BriefBotState) -> dict:
    """SCOUT — 4개국 종목 발굴 + 사전 감지."""
    agent = ScoutAgent()
    out = agent.execute(dict(state))
    update: dict = {"scout_out": out}
    if agent.errors:
        update["errors"] = [f"scout:{e}" for e in agent.errors]
    return update


def guard_node(state: BriefBotState) -> dict:
    """GUARD — 보유 포지션 모니터링 + 뉴스 매칭."""
    agent = GuardAgent()
    out = agent.execute(dict(state))
    update: dict = {"guard_out": out}
    if agent.errors:
        update["errors"] = [f"guard:{e}" for e in agent.errors]
    return update


def regime_node(state: BriefBotState) -> dict:
    """REGIME — 매크로 환경 + 해석 + 학습 노트."""
    agent = RegimeAgent()
    out = agent.execute(dict(state))
    update: dict = {"regime_out": out}
    if agent.errors:
        update["errors"] = [f"regime:{e}" for e in agent.errors]
    return update


def digest_node(state: BriefBotState) -> dict:
    """DIGEST — 3개 출력 종합 → 텔레그램/저널 메시지 생성."""
    agent = DigestAgent()
    out = agent.execute(dict(state))
    update: dict = {"digest_out": out}
    if agent.errors:
        update["errors"] = [f"digest:{e}" for e in agent.errors]
    return update


def m6_node(state: BriefBotState) -> dict:
    """M6 — SCOUT 후보 사후 추적 (Z3-4 재설계, D86).

    SCOUT 결과 + 옛 m6_history → 28일 추적 → DIGEST 컨텍스트.
    DIGEST 직전 호출 (DIGEST가 결과 사용).

    D91 (2026-04-30): m6 처리 후 SCOUT 시트 자동 적재 hook 추가.
      1. SCOUT 후보 → 'SCOUT 후보발굴' 시트 1행씩 적재 (price_at_add 동봉)
      2. 매일 follow-up: +5d/+28d 가격 자동 채움
      3. POSITIONS → SCOUT 시트 진입여부 컬럼 자동 동기화
      모든 작업 try/except — 실패해도 봇 메인 워크플로 영향 X.
    """
    update: dict = {}
    candidates_with_price = []
    try:
        from src.modules.m6_feedback import run_m6
        scout_out = state.get("scout_out") or {}
        candidates = scout_out.get("candidates") or []
        # state는 dict 복사로 전달 (run_m6가 m6_history in-place 수정)
        m6_state_dict = {"m6_history": state.get("m6_history", [])}
        m6_out = run_m6(m6_state_dict, scout_candidates=candidates)
        # 갱신된 history는 state에 다시 반영
        update["m6_history"] = m6_state_dict["m6_history"]
        update["m6_out"] = m6_out

        # ── D91: SCOUT 시트 적재용 — m6_history에서 오늘 추가된 가격 찾아 candidate에 주입 ──
        # m6는 _fetch_current_price를 이미 수행하므로 m6_history에서 매칭
        history = m6_state_dict["m6_history"]
        today_str = state.get("date", "")
        history_index = {
            (h.get("ticker", ""), h.get("date_added", "")): h.get("price_at_add")
            for h in history
        }
        for c in candidates:
            ticker = (c.get("ticker") or "").upper()
            price = history_index.get((ticker, today_str))
            if price is not None:
                c["price_at_add"] = price
        candidates_with_price = candidates
    except Exception as e:
        logger.warning("[m6_node] 실행 실패 (계속 진행): %s", e)
        update["m6_out"] = {
            "summary_text": "",
            "detailed_lines": [],
            "track_count": 0,
            "results": [],
        }
        update["errors"] = [f"m6:{e}"]

    # ═══════════════════════════════════════════════════════════
    # D91: SCOUT 시트 자동 적재 (실패해도 워크플로 영향 X)
    # ═══════════════════════════════════════════════════════════
    try:
        from src.collectors.sheets import (
            save_candidates_eval,
            update_followup_prices,
            sync_position_mapping,
        )
        date_str = state.get("date", "")

        # 1. 신규 후보 적재 (price_at_add 이미 주입됨)
        if candidates_with_price and date_str:
            try:
                added = save_candidates_eval(candidates_with_price, date_str)
                if added > 0:
                    logger.info("[m6_node] SCOUT 시트 신규 적재: %d행", added)
            except Exception as e:
                logger.warning("[m6_node] save_candidates_eval 실패: %s", e)

        # 2. 매일 follow-up: +5d/+28d 가격 자동 채움
        try:
            history = update.get("m6_history") or state.get("m6_history") or []
            n = update_followup_prices(history)
            if n > 0:
                logger.info("[m6_node] follow-up 가격 갱신: %d행", n)
        except Exception as e:
            logger.warning("[m6_node] update_followup_prices 실패: %s", e)

        # 3. POSITIONS → SCOUT 진입여부 동기화
        try:
            n = sync_position_mapping()
            if n > 0:
                logger.info("[m6_node] 진입 매핑 동기화: %d행", n)
        except Exception as e:
            logger.warning("[m6_node] sync_position_mapping 실패: %s", e)

    except ImportError as e:
        logger.warning("[m6_node] SCOUT 시트 모듈 import 실패: %s", e)
    except Exception as e:
        logger.warning("[m6_node] SCOUT 시트 작업 전체 실패: %s", e)

    return update


# ═══════════════════════════════════════════════════════════
# 그래프 구성
# ═══════════════════════════════════════════════════════════

def build_graph():
    """LangGraph 워크플로 생성.

    구조:
      START → [scout, guard, regime 병렬] → digest → END

    LangGraph는 같은 출발점에서 여러 노드로 fan-out, 모두 끝나면 join 가능.
    """
    workflow = StateGraph(BriefBotState)

    # 노드 등록
    workflow.add_node("scout", scout_node)
    workflow.add_node("guard", guard_node)
    workflow.add_node("regime", regime_node)
    workflow.add_node("m6", m6_node)
    workflow.add_node("digest", digest_node)

    # 엣지: scout → guard → regime → m6 → digest → END
    # M6는 SCOUT 후보 받아 추적 + 옛 history 성과 계산 → DIGEST가 사용
    workflow.set_entry_point("scout")
    workflow.add_edge("scout", "guard")
    workflow.add_edge("guard", "regime")
    workflow.add_edge("regime", "m6")
    workflow.add_edge("m6", "digest")
    workflow.add_edge("digest", END)

    # ※ 진짜 병렬 fan-out은 langgraph 0.2+ 의 add_edge_parallel 활용 가능.
    #   당장은 순차 실행이 더 디버깅 쉬움. 안정화 후 병렬 전환.

    return workflow.compile()


# ═══════════════════════════════════════════════════════════
# 향후 조건부 라우팅 (지금은 주석)
# ═══════════════════════════════════════════════════════════

def _vix_router(state: BriefBotState) -> str:
    """REGIME 결과 보고 SCOUT 실행 여부 결정.
    VIX EXTREME (>40) 시 SCOUT 스킵 — 좌측거래 신호 신뢰도 ↓
    """
    regime_out = state.get("regime_out", {})
    vix = regime_out.get("vix", 0)
    if vix and vix > 40:
        return "skip_scout"
    return "do_scout"


# 사용 예 (지금은 활성화 안 함):
# workflow.add_conditional_edges("regime", _vix_router, {
#     "do_scout": "scout",
#     "skip_scout": "digest",
# })
