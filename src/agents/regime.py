"""
src/agents/regime.py — REGIME 매크로 환경 에이전트

미션: 오늘의 매크로 환경 평가 + 어제 발표 결과 해석 + 환전 객관 데이터 + 학습 노트

5개 영역:
  1. VIX 레짐 (Q2: 30+ = 위험만 아니라 기회 구간도 표시)
  2. 섹터 RRG (M2 흡수)
  3. 환율 90일 분위수 (Q4: "비싸다/평균이다" 객관화)
  4. 매크로 캘린더 — 어제 발표 결과 + 이번 주 예정 (Q3: FOMC 해석 부재 해결)
  5. 학습 노트 — 매번 용어 1~2개 풀이 (Q3 답변)

LLM 역할 (Q3 결정 — "판단 금지" 폐기):
  - 어제 발표 매크로 이벤트의 시장 영향 해석
  - 좌측거래 시스템 관점에서의 함의
  - 학습 노트 (용어 설명)
  ※ 메인지표 신호 직접 명령은 안 함 — 환경 평가만
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import requests

from src.agents.base import BaseAgent

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
# 환율 90일 분위수
# ═══════════════════════════════════════════════════════════

def _fetch_fx_history(days: int = 90) -> Optional[list[float]]:
    """USD/KRW 90일 종가 히스토리."""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/USDKRW%3DX?range=3mo&interval=1d"
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return None
        data = resp.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
        valid = [float(c) for c in closes if c is not None]
        return valid if len(valid) >= 30 else None
    except Exception as e:
        logger.warning("[regime fx] 실패: %s", e)
        return None


def _compute_fx_percentile(history: list[float], current: float) -> dict:
    """현재 환율의 90일 분포 내 위치."""
    import bisect
    sorted_hist = sorted(history)
    pos = bisect.bisect_left(sorted_hist, current)
    pct = (pos / len(sorted_hist)) * 100

    avg = sum(history) / len(history)
    avg_diff_pct = ((current - avg) / avg) * 100 if avg else 0

    return {
        "current": round(current, 2),
        "percentile": round(pct, 1),
        "avg_90d": round(avg, 2),
        "avg_diff_pct": round(avg_diff_pct, 2),
        "min_90d": round(min(history), 2),
        "max_90d": round(max(history), 2),
    }


# ═══════════════════════════════════════════════════════════
# 섹터 RRG — M2 모듈 직접 호출
# ═══════════════════════════════════════════════════════════

def _fetch_sector_rrg(state: dict) -> dict:
    """기존 M2 호출 → 결과 + 4분면 요약 반환."""
    try:
        from src.modules.m2_rotation import run_m2
        # etf_map 로드
        etf_map_path = Path(__file__).resolve().parents[2] / "config" / "etf_map.json"
        with open(etf_map_path, "r", encoding="utf-8") as f:
            etf_map = json.load(f)

        result = run_m2(etf_map, state)
        snapshot = result.get("today_snapshot", {})
        transitions = result.get("transitions", [])

        # 4분면 요약
        by_quad = {"LEADING": [], "WEAKENING": [], "LAGGING": [], "IMPROVING": []}
        for ticker, info in snapshot.items():
            quad = info.get("quadrant")
            if quad in by_quad:
                by_quad[quad].append({
                    "ticker": ticker,
                    "label": info.get("label", ""),
                    "group": info.get("group", ""),
                    "ratio": info.get("ratio", 0),
                    "momentum": info.get("momentum", 0),
                })

        return {
            "snapshot": snapshot,
            "transitions": transitions,
            "by_quadrant": by_quad,
            "context_text": result.get("context_text", ""),
        }
    except Exception as e:
        logger.warning("[regime rrg] M2 호출 실패: %s", e)
        return {"snapshot": {}, "transitions": [], "by_quadrant": {}, "context_text": ""}


# ═══════════════════════════════════════════════════════════
# REGIME 에이전트
# ═══════════════════════════════════════════════════════════

class RegimeAgent(BaseAgent):
    """REGIME — 매크로 환경 + 해석 + 학습 노트."""

    def __init__(self):
        super().__init__("regime")
        self.settings = _load_settings()

    def run(self, state: dict) -> dict:
        regime_cfg = self.settings["regime"]

        # ── 1. VIX 레짐 ──
        vix_data = self._fetch_vix(regime_cfg["vix"])

        # ── 2. 섹터 RRG (M2) ──
        rrg_data = _fetch_sector_rrg(state)

        # ── 3. 환율 90일 분위수 ──
        fx_data = self._compute_fx(regime_cfg["fx"])

        # ── 4. 매크로 캘린더 — 어제 발표 + 이번 주 예정 ──
        macro_data = self._fetch_macro_events(regime_cfg["macro_calendar"])

        # ── 5. LLM 해석 호출 ──
        interpretation = self._interpret_with_llm(
            vix_data, rrg_data, fx_data, macro_data, regime_cfg
        )

        # ── 6. context_text (DIGEST 입력용) ──
        context = self._build_context(vix_data, rrg_data, fx_data, macro_data, interpretation)

        return {
            "vix": vix_data.get("value"),
            "vix_regime": vix_data.get("regime"),
            "vix_data": vix_data,
            "rrg": rrg_data,
            "fx": fx_data,
            "macro": macro_data,
            "interpretation": interpretation,
            "context_text": context,
        }

    # ─────────────────────────────────────────────
    # VIX
    # ─────────────────────────────────────────────
    def _fetch_vix(self, cfg: dict) -> dict:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?range=5d&interval=1d"
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                return {"value": None, "regime": "UNKNOWN", "label": "수집 실패"}
            data = resp.json()
            result = data.get("chart", {}).get("result", [])
            if not result:
                return {"value": None, "regime": "UNKNOWN", "label": "수집 실패"}
            closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
            valid = [float(c) for c in closes if c is not None]
            if not valid:
                return {"value": None, "regime": "UNKNOWN", "label": "수집 실패"}
            vix = valid[-1]

            # 레짐 분류 — Q2 결정 반영
            if vix < cfg["low_threshold"]:
                regime, label, side_note = "LOW", "낮은 변동성", "과열 주의"
            elif vix < cfg["normal_max"]:
                regime, label, side_note = "NORMAL", "보통", "좌측거래 우호"
            elif vix < cfg["high_max"]:
                regime, label, side_note = "ELEVATED", "변동성 상승", "변동성 기회 구간"
            elif vix < cfg["extreme_threshold"]:
                regime, label, side_note = (
                    "HIGH", "높은 변동성",
                    "ETF 분할 매수 우위 구간 (SPY 등). 개별주는 변동성 ↑ 주의"
                )
            else:
                regime, label, side_note = (
                    "EXTREME", "극단적 공포",
                    "역사적 변곡점 가능. 좌측거래 신뢰도 일시 ↓ — 메인지표 신호도 보수적으로"
                )

            return {
                "value": round(vix, 2),
                "regime": regime,
                "label": label,
                "side_note": side_note,
            }
        except Exception as e:
            logger.warning("[regime vix] 실패: %s", e)
            return {"value": None, "regime": "UNKNOWN", "label": "수집 실패"}

    # ─────────────────────────────────────────────
    # 환율
    # ─────────────────────────────────────────────
    def _compute_fx(self, cfg: dict) -> dict:
        history = _fetch_fx_history(days=cfg["history_days"])
        if not history or len(history) < 30:
            return {"current": None, "label": "수집 실패"}

        current = history[-1]
        stat = _compute_fx_percentile(history[:-1], current)

        # 라벨링
        pct = stat["percentile"]
        high_pct = cfg["percentile_high_pct"]
        low_pct = cfg["percentile_low_pct"]

        if pct >= high_pct:
            label = f"평균 위 (90일 분포 상위 {round(100 - pct)}%)"
            judgment = "달러 매수 보류 권장"
        elif pct <= low_pct:
            label = f"평균 아래 (90일 분포 하위 {round(pct)}%)"
            judgment = "달러 매수 적정 구간"
        else:
            label = f"평균 근처 (90일 분포 {round(pct)}%)"
            judgment = "분할 매수 가능"

        return {
            **stat,
            "label": label,
            "judgment": judgment,
        }

    # ─────────────────────────────────────────────
    # 매크로 캘린더
    # ─────────────────────────────────────────────
    def _fetch_macro_events(self, cfg: dict) -> dict:
        try:
            from src.collectors.macro_calendar import (
                get_yesterday_announced_events,
                get_upcoming_events,
            )
            yesterday = get_yesterday_announced_events()
            upcoming = get_upcoming_events(lookahead_days=cfg["lookahead_days"])
            return {
                "yesterday_announced": yesterday,
                "upcoming": upcoming,
            }
        except Exception as e:
            logger.warning("[regime macro] 실패: %s", e)
            return {"yesterday_announced": [], "upcoming": []}

    # ─────────────────────────────────────────────
    # LLM 해석 호출
    # ─────────────────────────────────────────────
    def _interpret_with_llm(self, vix_data, rrg_data, fx_data, macro_data, regime_cfg) -> dict:
        """LLM 호출 — 어제 발표 해석 + 학습 노트.

        호출 조건: 어제 발표 이벤트 있을 때만 (없으면 LLM 호출 비용 아낌)
        """
        yesterday_events = macro_data.get("yesterday_announced", [])
        learning_enabled = regime_cfg["learning_notes"]["enabled"]
        max_notes = regime_cfg["learning_notes"]["max_per_brief"]

        if not yesterday_events and not learning_enabled:
            return {"announcements_interpretation": "", "learning_notes": []}

        # 시스템 프롬프트
        system = (
            "당신은 RONIN 트레이딩 시스템의 매크로 분석가입니다.\n"
            "역할: 객관 데이터를 한국어로 해석. 메인지표(좌측거래 60% + 우측거래 40%) 시스템 관점.\n"
            "원칙:\n"
            "1. 객관 데이터(FRED + 시장반응)에 기반. 데이터 없으면 '데이터 부족 — 보류' 명시\n"
            "2. 메인지표 신호 직접 명령 금지 (예: '진입해라' X). 환경 평가만.\n"
            "3. 좌측거래 시스템 관점에서의 함의 명시 (예: '비둘기파 → 기술주 좌측 매수 우호')\n"
            "4. 확신도 표기 (높음/중간/낮음)\n"
            "5. 학습 노트: 매번 용어 1~2개를 로이가 학습할 수 있도록 풀이"
        )

        # 사용자 메시지
        user_parts = ["오늘의 매크로 데이터:"]

        # 어제 발표 이벤트
        if yesterday_events:
            user_parts.append("\n[어제 발표 이벤트]")
            for evt in yesterday_events:
                user_parts.append(f"- {evt.get('name')}: {evt.get('date')}")
                if evt.get("related_fred"):
                    for sid, sd in evt["related_fred"].items():
                        chg = sd.get("change")
                        chg_str = f" (변화 {chg:+.4f})" if chg is not None else ""
                        user_parts.append(
                            f"  FRED {sid}: 최신 {sd['latest_value']} ({sd['latest_date']}){chg_str}"
                        )
                if evt.get("market_reaction"):
                    user_parts.append("  시장 반응 (어제→오늘):")
                    for label, md in evt["market_reaction"].items():
                        if md.get("change_pct") is not None:
                            user_parts.append(
                                f"    {label}: {md['yesterday_close']} → {md['today_close']} "
                                f"({md['change_pct']:+.2f}%)"
                            )
        else:
            user_parts.append("\n[어제 발표 이벤트] 없음")

        # 시장 환경 요약
        user_parts.append(f"\n[VIX] {vix_data.get('value')} ({vix_data.get('regime')} — {vix_data.get('label')})")
        user_parts.append(f"[환율] {fx_data.get('current')}원 — {fx_data.get('label', 'N/A')}")

        if learning_enabled:
            user_parts.append(
                f"\n출력 요청:\n"
                f"1) 어제 발표 이벤트가 있으면 한국어 해석 (3~5줄, 시장 반응 + 좌측거래 함의)\n"
                f"2) 학습 노트: 위 내용 중 등장한 용어 {max_notes}개 풀이.\n"
                f"   ★ 중요: VIX, GDP 같은 **누구나 아는 용어는 피하세요**.\n"
                f"   매크로/금리/정책/RRG 4분면 같은 좀 더 까다로운 개념을 우선.\n"
                f"   예: '비둘기파 = 금리 인하/완화 선호하는 정책 입장',\n"
                f"        'IMPROVING 분면 = 상대 강도 약하지만 모멘텀 회복 중',\n"
                f"        'PCE = 연준이 가장 중시하는 물가 지표 (CPI보다 폭 좁음)'.\n"
                f"   1~2줄씩, 한국어.\n"
                f"3) JSON 형식: {{\"interpretation\": \"...\", \"learning_notes\": [{{\"term\": \"...\", \"explain\": \"...\"}}]}}\n"
                f"4) JSON만 출력. 마크다운 ```json 같은 거 사용하지 마."
            )

        user_msg = "\n".join(user_parts)

        # LLM 호출
        raw = self.call_llm(system, user_msg, max_tokens=1200)
        if not raw:
            return {"announcements_interpretation": "", "learning_notes": []}

        # JSON 파싱 시도
        try:
            # ```json ... ``` 제거
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(cleaned)
            return {
                "announcements_interpretation": parsed.get("interpretation", ""),
                "learning_notes": parsed.get("learning_notes", []),
            }
        except Exception as e:
            logger.warning("[regime llm] JSON 파싱 실패 — raw 텍스트로 반환: %s", e)
            return {
                "announcements_interpretation": raw[:1000],
                "learning_notes": [],
            }

    # ─────────────────────────────────────────────
    # context_text 생성
    # ─────────────────────────────────────────────
    def _build_context(self, vix_data, rrg_data, fx_data, macro_data, interpretation) -> str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        lines = [f"[매크로 환경 — {date_str}]", ""]

        # VIX
        if vix_data.get("value") is not None:
            lines.append(
                f"VIX {vix_data['value']} {vix_data['regime']} — {vix_data['label']} ({vix_data.get('side_note', '')})"
            )

        # 섹터 RRG
        by_quad = rrg_data.get("by_quadrant", {})
        if by_quad:
            lines.append("\n섹터 4분면 (RRG):")
            for q in ["LEADING", "IMPROVING", "WEAKENING", "LAGGING"]:
                items = by_quad.get(q, [])
                if items:
                    tickers = ", ".join(f"{i['ticker']}({i['label']})" for i in items[:5])
                    lines.append(f"  {q}: {tickers}")
            transitions = rrg_data.get("transitions", [])
            if transitions:
                lines.append("  분면 전환:")
                for t in transitions:
                    lines.append(f"    {t['ticker']} ({t['label']}): {t['transition']}")

        # 환율
        if fx_data.get("current"):
            lines.append(
                f"\n원/달러 {fx_data['current']}원 — {fx_data['label']}\n  판단: {fx_data.get('judgment', '')}"
            )

        # 어제 발표 이벤트 + LLM 해석
        yesterday = macro_data.get("yesterday_announced", [])
        if yesterday:
            lines.append("\n[어제 발표]")
            for evt in yesterday:
                lines.append(f"- {evt.get('name')}")
            interp = interpretation.get("announcements_interpretation", "")
            if interp:
                lines.append(f"\n해석:\n{interp}")

        # 이번 주 예정
        upcoming = macro_data.get("upcoming", [])
        if upcoming:
            lines.append("\n[이번 주 예정]")
            for evt in upcoming[:5]:
                impact = evt.get("impact", "")
                marker = "🔴" if impact == "high" else "🟡" if impact == "medium" else "·"
                lines.append(f"{marker} {evt.get('date')} {evt.get('name')}")

        # 학습 노트
        notes = interpretation.get("learning_notes", [])
        if notes:
            lines.append("\n[학습 노트]")
            for n in notes:
                term = n.get("term", "")
                explain = n.get("explain", "")
                if term and explain:
                    lines.append(f"- {term}: {explain}")

        return "\n".join(lines)

    def _error_output(self, error_msg: str) -> dict:
        return {
            "vix": None,
            "vix_regime": "UNKNOWN",
            "vix_data": {},
            "rrg": {},
            "fx": {},
            "macro": {"yesterday_announced": [], "upcoming": []},
            "interpretation": {"announcements_interpretation": "", "learning_notes": []},
            "context_text": f"[REGIME 에러] {error_msg}",
            "error": error_msg,
        }    except Exception as e:
        logger.warning("[regime fx] 실패: %s", e)
        return None


def _compute_fx_percentile(history: list[float], current: float) -> dict:
    """현재 환율의 90일 분포 내 위치."""
    import bisect
    sorted_hist = sorted(history)
    pos = bisect.bisect_left(sorted_hist, current)
    pct = (pos / len(sorted_hist)) * 100

    avg = sum(history) / len(history)
    avg_diff_pct = ((current - avg) / avg) * 100 if avg else 0

    return {
        "current": round(current, 2),
        "percentile": round(pct, 1),
        "avg_90d": round(avg, 2),
        "avg_diff_pct": round(avg_diff_pct, 2),
        "min_90d": round(min(history), 2),
        "max_90d": round(max(history), 2),
    }


# ═══════════════════════════════════════════════════════════
# 섹터 RRG — M2 모듈 직접 호출
# ═══════════════════════════════════════════════════════════

def _fetch_sector_rrg(state: dict) -> dict:
    """기존 M2 호출 → 결과 + 4분면 요약 반환."""
    try:
        from src.modules.m2_rotation import run_m2
        # etf_map 로드
        etf_map_path = Path(__file__).resolve().parents[2] / "config" / "etf_map.json"
        with open(etf_map_path, "r", encoding="utf-8") as f:
            etf_map = json.load(f)

        result = run_m2(etf_map, state)
        snapshot = result.get("today_snapshot", {})
        transitions = result.get("transitions", [])

        # 4분면 요약
        by_quad = {"LEADING": [], "WEAKENING": [], "LAGGING": [], "IMPROVING": []}
        for ticker, info in snapshot.items():
            quad = info.get("quadrant")
            if quad in by_quad:
                by_quad[quad].append({
                    "ticker": ticker,
                    "label": info.get("label", ""),
                    "group": info.get("group", ""),
                    "ratio": info.get("ratio", 0),
                    "momentum": info.get("momentum", 0),
                })

        return {
            "snapshot": snapshot,
            "transitions": transitions,
            "by_quadrant": by_quad,
            "context_text": result.get("context_text", ""),
        }
    except Exception as e:
        logger.warning("[regime rrg] M2 호출 실패: %s", e)
        return {"snapshot": {}, "transitions": [], "by_quadrant": {}, "context_text": ""}


# ═══════════════════════════════════════════════════════════
# REGIME 에이전트
# ═══════════════════════════════════════════════════════════

class RegimeAgent(BaseAgent):
    """REGIME — 매크로 환경 + 해석 + 학습 노트."""

    def __init__(self):
        super().__init__("regime")
        self.settings = _load_settings()

    def run(self, state: dict) -> dict:
        regime_cfg = self.settings["regime"]

        # ── 1. VIX 레짐 ──
        vix_data = self._fetch_vix(regime_cfg["vix"])

        # ── 2. 섹터 RRG (M2) ──
        rrg_data = _fetch_sector_rrg(state)

        # ── 3. 환율 90일 분위수 ──
        fx_data = self._compute_fx(regime_cfg["fx"])

        # ── 4. 매크로 캘린더 — 어제 발표 + 이번 주 예정 ──
        macro_data = self._fetch_macro_events(regime_cfg["macro_calendar"])

        # ── 5. LLM 해석 호출 ──
        interpretation = self._interpret_with_llm(
            vix_data, rrg_data, fx_data, macro_data, regime_cfg
        )

        # ── 6. context_text (DIGEST 입력용) ──
        context = self._build_context(vix_data, rrg_data, fx_data, macro_data, interpretation)

        return {
            "vix": vix_data.get("value"),
            "vix_regime": vix_data.get("regime"),
            "vix_data": vix_data,
            "rrg": rrg_data,
            "fx": fx_data,
            "macro": macro_data,
            "interpretation": interpretation,
            "context_text": context,
        }

    # ─────────────────────────────────────────────
    # VIX
    # ─────────────────────────────────────────────
    def _fetch_vix(self, cfg: dict) -> dict:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?range=5d&interval=1d"
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                return {"value": None, "regime": "UNKNOWN", "label": "수집 실패"}
            data = resp.json()
            result = data.get("chart", {}).get("result", [])
            if not result:
                return {"value": None, "regime": "UNKNOWN", "label": "수집 실패"}
            closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
            valid = [float(c) for c in closes if c is not None]
            if not valid:
                return {"value": None, "regime": "UNKNOWN", "label": "수집 실패"}
            vix = valid[-1]

            # 레짐 분류 — Q2 결정 반영
            if vix < cfg["low_threshold"]:
                regime, label, side_note = "LOW", "낮은 변동성", "과열 주의"
            elif vix < cfg["normal_max"]:
                regime, label, side_note = "NORMAL", "보통", "좌측거래 우호"
            elif vix < cfg["high_max"]:
                regime, label, side_note = "ELEVATED", "변동성 상승", "변동성 기회 구간"
            elif vix < cfg["extreme_threshold"]:
                regime, label, side_note = (
                    "HIGH", "높은 변동성",
                    "ETF 분할 매수 우위 구간 (SPY 등). 개별주는 변동성 ↑ 주의"
                )
            else:
                regime, label, side_note = (
                    "EXTREME", "극단적 공포",
                    "역사적 변곡점 가능. 좌측거래 신뢰도 일시 ↓ — 메인지표 신호도 보수적으로"
                )

            return {
                "value": round(vix, 2),
                "regime": regime,
                "label": label,
                "side_note": side_note,
            }
        except Exception as e:
            logger.warning("[regime vix] 실패: %s", e)
            return {"value": None, "regime": "UNKNOWN", "label": "수집 실패"}

    # ─────────────────────────────────────────────
    # 환율
    # ─────────────────────────────────────────────
    def _compute_fx(self, cfg: dict) -> dict:
        history = _fetch_fx_history(days=cfg["history_days"])
        if not history or len(history) < 30:
            return {"current": None, "label": "수집 실패"}

        current = history[-1]
        stat = _compute_fx_percentile(history[:-1], current)

        # 라벨링
        pct = stat["percentile"]
        high_pct = cfg["percentile_high_pct"]
        low_pct = cfg["percentile_low_pct"]

        if pct >= high_pct:
            label = f"평균 위 (90일 분포 상위 {round(100 - pct)}%)"
            judgment = "달러 매수 보류 권장"
        elif pct <= low_pct:
            label = f"평균 아래 (90일 분포 하위 {round(pct)}%)"
            judgment = "달러 매수 적정 구간"
        else:
            label = f"평균 근처 (90일 분포 {round(pct)}%)"
            judgment = "분할 매수 가능"

        return {
            **stat,
            "label": label,
            "judgment": judgment,
        }

    # ─────────────────────────────────────────────
    # 매크로 캘린더
    # ─────────────────────────────────────────────
    def _fetch_macro_events(self, cfg: dict) -> dict:
        try:
            from src.collectors.macro_calendar import (
                get_yesterday_announced_events,
                get_upcoming_events,
            )
            yesterday = get_yesterday_announced_events()
            upcoming = get_upcoming_events(lookahead_days=cfg["lookahead_days"])
            return {
                "yesterday_announced": yesterday,
                "upcoming": upcoming,
            }
        except Exception as e:
            logger.warning("[regime macro] 실패: %s", e)
            return {"yesterday_announced": [], "upcoming": []}

    # ─────────────────────────────────────────────
    # LLM 해석 호출
    # ─────────────────────────────────────────────
    def _interpret_with_llm(self, vix_data, rrg_data, fx_data, macro_data, regime_cfg) -> dict:
        """LLM 호출 — 어제 발표 해석 + 학습 노트.

        호출 조건: 어제 발표 이벤트 있을 때만 (없으면 LLM 호출 비용 아낌)
        """
        yesterday_events = macro_data.get("yesterday_announced", [])
        learning_enabled = regime_cfg["learning_notes"]["enabled"]
        max_notes = regime_cfg["learning_notes"]["max_per_brief"]

        if not yesterday_events and not learning_enabled:
            return {"announcements_interpretation": "", "learning_notes": []}

        # 시스템 프롬프트
        system = (
            "당신은 RONIN 트레이딩 시스템의 매크로 분석가입니다.\n"
            "역할: 객관 데이터를 한국어로 해석. 메인지표(좌측거래 60% + 우측거래 40%) 시스템 관점.\n"
            "원칙:\n"
            "1. 객관 데이터(FRED + 시장반응)에 기반. 데이터 없으면 '데이터 부족 — 보류' 명시\n"
            "2. 메인지표 신호 직접 명령 금지 (예: '진입해라' X). 환경 평가만.\n"
            "3. 좌측거래 시스템 관점에서의 함의 명시 (예: '비둘기파 → 기술주 좌측 매수 우호')\n"
            "4. 확신도 표기 (높음/중간/낮음)\n"
            "5. 학습 노트: 매번 용어 1~2개를 로이가 학습할 수 있도록 풀이"
        )

        # 사용자 메시지
        user_parts = ["오늘의 매크로 데이터:"]

        # 어제 발표 이벤트
        if yesterday_events:
            user_parts.append("\n[어제 발표 이벤트]")
            for evt in yesterday_events:
                user_parts.append(f"- {evt.get('name')}: {evt.get('date')}")
                if evt.get("related_fred"):
                    for sid, sd in evt["related_fred"].items():
                        chg = sd.get("change")
                        chg_str = f" (변화 {chg:+.4f})" if chg is not None else ""
                        user_parts.append(
                            f"  FRED {sid}: 최신 {sd['latest_value']} ({sd['latest_date']}){chg_str}"
                        )
                if evt.get("market_reaction"):
                    user_parts.append("  시장 반응 (어제→오늘):")
                    for label, md in evt["market_reaction"].items():
                        if md.get("change_pct") is not None:
                            user_parts.append(
                                f"    {label}: {md['yesterday_close']} → {md['today_close']} "
                                f"({md['change_pct']:+.2f}%)"
                            )
        else:
            user_parts.append("\n[어제 발표 이벤트] 없음")

        # 시장 환경 요약
        user_parts.append(f"\n[VIX] {vix_data.get('value')} ({vix_data.get('regime')} — {vix_data.get('label')})")
        user_parts.append(f"[환율] {fx_data.get('current')}원 — {fx_data.get('label', 'N/A')}")

        if learning_enabled:
            user_parts.append(
                f"\n출력 요청:\n"
                f"1) 어제 발표 이벤트가 있으면 한국어 해석 (3~5줄, 시장 반응 + 좌측거래 함의)\n"
                f"2) 학습 노트: 위 내용 중 등장한 용어 {max_notes}개 풀이 (한국어, 1~2줄씩)\n"
                f"   (예: '비둘기파 = 금리 인하/완화 선호하는 정책 입장')\n"
                f"3) JSON 형식: {{\"interpretation\": \"...\", \"learning_notes\": [{{\"term\": \"...\", \"explain\": \"...\"}}]}}\n"
                f"4) JSON만 출력. 마크다운 ```json 같은 거 사용하지 마."
            )

        user_msg = "\n".join(user_parts)

        # LLM 호출
        raw = self.call_llm(system, user_msg, max_tokens=1200)
        if not raw:
            return {"announcements_interpretation": "", "learning_notes": []}

        # JSON 파싱 시도
        try:
            # ```json ... ``` 제거
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(cleaned)
            return {
                "announcements_interpretation": parsed.get("interpretation", ""),
                "learning_notes": parsed.get("learning_notes", []),
            }
        except Exception as e:
            logger.warning("[regime llm] JSON 파싱 실패 — raw 텍스트로 반환: %s", e)
            return {
                "announcements_interpretation": raw[:1000],
                "learning_notes": [],
            }

    # ─────────────────────────────────────────────
    # context_text 생성
    # ─────────────────────────────────────────────
    def _build_context(self, vix_data, rrg_data, fx_data, macro_data, interpretation) -> str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        lines = [f"[매크로 환경 — {date_str}]", ""]

        # VIX
        if vix_data.get("value") is not None:
            lines.append(
                f"VIX {vix_data['value']} {vix_data['regime']} — {vix_data['label']} ({vix_data.get('side_note', '')})"
            )

        # 섹터 RRG
        by_quad = rrg_data.get("by_quadrant", {})
        if by_quad:
            lines.append("\n섹터 4분면 (RRG):")
            for q in ["LEADING", "IMPROVING", "WEAKENING", "LAGGING"]:
                items = by_quad.get(q, [])
                if items:
                    tickers = ", ".join(f"{i['ticker']}({i['label']})" for i in items[:5])
                    lines.append(f"  {q}: {tickers}")
            transitions = rrg_data.get("transitions", [])
            if transitions:
                lines.append("  분면 전환:")
                for t in transitions:
                    lines.append(f"    {t['ticker']} ({t['label']}): {t['transition']}")

        # 환율
        if fx_data.get("current"):
            lines.append(
                f"\n원/달러 {fx_data['current']}원 — {fx_data['label']}\n  판단: {fx_data.get('judgment', '')}"
            )

        # 어제 발표 이벤트 + LLM 해석
        yesterday = macro_data.get("yesterday_announced", [])
        if yesterday:
            lines.append("\n[어제 발표]")
            for evt in yesterday:
                lines.append(f"- {evt.get('name')}")
            interp = interpretation.get("announcements_interpretation", "")
            if interp:
                lines.append(f"\n해석:\n{interp}")

        # 이번 주 예정
        upcoming = macro_data.get("upcoming", [])
        if upcoming:
            lines.append("\n[이번 주 예정]")
            for evt in upcoming[:5]:
                impact = evt.get("impact", "")
                marker = "🔴" if impact == "high" else "🟡" if impact == "medium" else "·"
                lines.append(f"{marker} {evt.get('date')} {evt.get('name')}")

        # 학습 노트
        notes = interpretation.get("learning_notes", [])
        if notes:
            lines.append("\n[학습 노트]")
            for n in notes:
                term = n.get("term", "")
                explain = n.get("explain", "")
                if term and explain:
                    lines.append(f"- {term}: {explain}")

        return "\n".join(lines)

    def _error_output(self, error_msg: str) -> dict:
        return {
            "vix": None,
            "vix_regime": "UNKNOWN",
            "vix_data": {},
            "rrg": {},
            "fx": {},
            "macro": {"yesterday_announced": [], "upcoming": []},
            "interpretation": {"announcements_interpretation": "", "learning_notes": []},
            "context_text": f"[REGIME 에러] {error_msg}",
            "error": error_msg,
        }
