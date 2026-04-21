"""
src/graph.py — LangGraph 메인 워크플로

4 에이전트 병렬 실행 구조:
  scout, guard, regime → digest

조건부 라우팅 예시 (향후 확장):
  - VIX EXTREME (>40) → SCOUT 스킵
  - 모든 에이전트 실패 → fallback 메시지
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
    scout_cooldown: dict               # 신호별 cooldown {ticker: last_alert_date}
    prev_day: dict                     # 어제 브리핑 데이터
    macro_pending: dict                # 발표 대기 매크로 이벤트

    # ── 각 에이전트 출력 ──
    scout_out: dict                    # SCOUT: candidates, scanned_total, by_country
    guard_out: dict                    # GUARD: positions_status, news_events
    regime_out: dict                   # REGIME: vix, sectors, macro_events, fx
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
    workflow.add_node("digest", digest_node)

    # 엣지: START → 3개 병렬 → digest → END
    workflow.set_entry_point("scout")
    workflow.add_edge("scout", "guard")
    workflow.add_edge("guard", "regime")
    workflow.add_edge("regime", "digest")
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
