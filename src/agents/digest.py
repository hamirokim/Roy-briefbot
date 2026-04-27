"""
src/agents/digest.py — DIGEST 오케스트레이터

미션: SCOUT + GUARD + REGIME 출력 종합 → 텔레그램(요약) + 저널(상세) 메시지 생성

원칙:
  - 새 정보 생성 금지 — 입력 데이터만 가공
  - 텔레그램 4000자 한도 (settings.digest.telegram.max_chars)
  - SCOUT 0개여도 GUARD/REGIME 있으면 발송
  - 모든 에이전트 실패 시 fallback 메시지

LLM 역할: SCOUT 후보의 "왜 후보인지" 1줄 자연어 + 전체 톤 정리
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agents.base import BaseAgent
from src.utils import now_kst

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
# 국가별 이모지/표시
# ═══════════════════════════════════════════════════════════

_COUNTRY_FLAG = {
    "US": "🇺🇸",
    "KR": "🇰🇷",
    "JP": "🇯🇵",
    "CN_ADR": "🇨🇳",
}

# ─── 저널 한글 매핑 (v4: 한글 통일) ───
_COUNTRY_KO = {
    "US": "미국",
    "KR": "한국",
    "JP": "일본",
    "CN_ADR": "중국ADR",
}
_QUADRANT_KO = {
    "LEADING": "주도",
    "IMPROVING": "개선",
    "WEAKENING": "약화",
    "LAGGING": "부진",
}
_VIX_REGIME_KO = {
    "LOW": "낮음",
    "NORMAL": "정상",
    "ELEVATED": "상승",
    "HIGH": "높음",
    "EXTREME": "극단",
    "UNKNOWN": "알수없음",
}
_STATUS_KO = {
    "OPEN": "오픈",
    "CLOSED": "청산",
    "PARTIAL": "부분",
    "open": "오픈",
    "closed": "청산",
}
_SIGNAL_KO = {
    "bb_squeeze": "BB 압축 (변동성 응축)",
    "volume_compression": "거래량 위축",
    "after_low_consolidation": "신저가 후 횡보 (바닥다지기)",
    "insider_buying": "내부자 매수",
    "rrg_improving": "섹터 상대강도 개선",
}


def _format_signal_ko(sig_name: str, sig_info: Any) -> str:
    """신호 한글 라벨 + 핵심 수치 디테일."""
    ko = _SIGNAL_KO.get(sig_name, sig_name)
    if not isinstance(sig_info, dict):
        return ko
    parts = []
    for k, v in sig_info.items():
        if isinstance(v, float):
            parts.append(f"{k}={v:.2f}")
        elif isinstance(v, int):
            parts.append(f"{k}={v}")
        elif isinstance(v, bool) and v:
            parts.append(k)
        elif isinstance(v, str) and v:
            parts.append(f"{k}={v[:30]}")
    if parts:
        return f"{ko} — {', '.join(parts[:4])}"
    return ko


def _circled_num(n: int) -> str:
    """1~20을 ①②③… 원형 숫자로."""
    table = ["①","②","③","④","⑤","⑥","⑦","⑧","⑨","⑩",
             "⑪","⑫","⑬","⑭","⑮","⑯","⑰","⑱","⑲","⑳"]
    if 1 <= n <= len(table):
        return table[n - 1]
    return f"({n})"


def _format_market_cap(value: float) -> str:
    """시총 포맷 ($1.2B / $234M)."""
    if value >= 1e12:
        return f"${value / 1e12:.1f}T"
    elif value >= 1e9:
        return f"${value / 1e9:.1f}B"
    elif value >= 1e6:
        return f"${value / 1e6:.0f}M"
    return f"${value:.0f}"


def _format_signals_short(signals: dict) -> str:
    """신호 요약 — 'BB압축, 거래량↓, RRG↑' 식."""
    label_map = {
        "bb_squeeze": "BB압축",
        "volume_compression": "거래량↓",
        "after_low_consolidation": "바닥다지기",
        "insider_buying": "내부매수",
        "rrg_improving": "섹터RRG↑",
    }
    parts = [label_map.get(k, k) for k in signals.keys()]
    return ", ".join(parts)


# ═══════════════════════════════════════════════════════════
# DIGEST 에이전트
# ═══════════════════════════════════════════════════════════

class DigestAgent(BaseAgent):
    """DIGEST — 3개 출력 종합 + 텔레그램/저널 메시지 생성."""

    def __init__(self):
        super().__init__("digest")
        self.settings = _load_settings()

    def run(self, state: dict) -> dict:
        scout_out = state.get("scout_out", {})
        guard_out = state.get("guard_out", {})
        regime_out = state.get("regime_out", {})
        briefing_mode = state.get("briefing_mode", "daily")

        # 모든 에이전트 실패 체크
        all_empty = (
            not scout_out.get("candidates")
            and not guard_out.get("alerts")
            and not regime_out.get("vix")
        )
        if all_empty:
            self.log.warning("[digest] 모든 에이전트 빈 결과 — fallback")
            return {
                "telegram_text": self.settings["digest"]["telegram"]["fallback_message"],
                "sheets_text": "",
                "all_empty": True,
            }

        # ── LLM 호출 1 — SCOUT 후보 자연어 해석 ──
        candidates_with_explanation = self._enrich_candidates_llm(scout_out.get("candidates", []))

        # ── LLM 호출 2 — GUARD 영문 뉴스 한국어 요약 (v3 신규) ──
        guard_out_translated = self._translate_news_korean(guard_out)

        # ── LLM 호출 3 (조건부) — 주간/월간 종합 + 방향 안내 ──
        period_summary = ""
        if briefing_mode == "weekly":
            period_summary = self._build_weekly_summary(state, regime_out, scout_out)
            self.log.info("[digest] 주간 종합 생성: %d자", len(period_summary))
        elif briefing_mode == "monthly":
            period_summary = self._build_monthly_summary(state, regime_out, scout_out)
            self.log.info("[digest] 월간 정리 생성: %d자", len(period_summary))

        # ── 텔레그램 메시지 생성 ──
        telegram_text = self._build_telegram(
            candidates_with_explanation, guard_out_translated, regime_out,
            briefing_mode=briefing_mode,
            period_summary=period_summary,
        )

        # ── 저널 BRIEFING 시트 메시지 생성 (상세) ──
        sheets_text = self._build_sheets_detailed(
            scout_out, guard_out_translated, regime_out, candidates_with_explanation,
            briefing_mode=briefing_mode,
            period_summary=period_summary,
        )

        return {
            "telegram_text": telegram_text,
            "sheets_text": sheets_text,
            "candidates_count": len(scout_out.get("candidates", [])),
            "alerts_count": len(guard_out.get("alerts", [])),
            "briefing_mode": briefing_mode,
            "all_empty": False,
        }

    # ─────────────────────────────────────────────
    # LLM — 주간 종합 + 새 주 방향 안내 (weekly 모드)
    # ─────────────────────────────────────────────
    def _build_weekly_summary(self, state: dict, regime_out: dict, scout_out: dict) -> str:
        """지난 주 시장 변화 종합 + 새 주 좌측거래 관점 방향 안내.

        입력:
        - state.m2_history: 최근 30일 RRG 스냅샷
        - regime_out: 현재 VIX/환율/매크로 상태
        - scout_out: 이번 주 후보 (있으면)
        - regime_out.macro.upcoming: 이번 주 매크로 일정

        출력: 한국어 2~3문단 (실패 시 빈 문자열).
        """
        m2_history = state.get("m2_history", {}) or {}
        sorted_dates = sorted(m2_history.keys(), reverse=True)[:7]

        rrg_lines = []
        for d in sorted_dates:
            snap = m2_history[d]
            if isinstance(snap, dict):
                quad_summary = {}
                for ticker, info in snap.items():
                    if isinstance(info, dict):
                        q = info.get("quadrant", "?")
                        quad_summary.setdefault(q, []).append(ticker)
                rrg_lines.append(f"  {d}: {quad_summary}")

        upcoming = (regime_out.get("macro", {}) or {}).get("upcoming", []) or []
        upcoming_str = "\n".join(
            f"  - {evt.get('date')} {evt.get('name')} (영향: {evt.get('impact', '?')})"
            for evt in upcoming[:5]
        ) or "  (없음)"

        vix_data = regime_out.get("vix_data", {}) or {}
        fx = regime_out.get("fx", {}) or {}
        vix_str = f"VIX {vix_data.get('value', '?')} ({vix_data.get('regime', '?')})"
        fx_str = f"원/달러 {fx.get('current', '?')}원 ({fx.get('label', '')})"

        system = (
            "당신은 RONIN 트레이딩 시스템의 주간 정리 분석가입니다.\n"
            "역할: 지난 주 시장 변화 종합 + 새 주 좌측거래 관점 방향 안내.\n"
            "원칙:\n"
            "1. 한국어로만 작성. 결론·구체 수치 우선.\n"
            "2. 2~3문단 구조: ① 지난 주 핵심 변화 ② 새 주 좌측거래 키포인트 ③ 주의할 매크로 이벤트.\n"
            "3. 각 문단 80~150자.\n"
            "4. 진입/exit 명령 금지 — 환경 평가와 관찰 포인트만.\n"
            "5. 환각 금지. 입력 데이터에 없는 수치 만들지 마.\n"
            "6. 빈 데이터는 빈 데이터로 표시 (가짜로 채우지 말 것)."
        )

        user = (
            "다음은 지난 주 데이터입니다. 주간 정리 + 새 주 방향 안내를 작성해주세요.\n\n"
            f"[현재 매크로 환경]\n  {vix_str}\n  {fx_str}\n\n"
            f"[최근 RRG 분면 추이 (최신 → 과거)]\n{chr(10).join(rrg_lines) or '  (데이터 누적 중)'}\n\n"
            f"[이번 주 매크로 일정]\n{upcoming_str}\n\n"
            "출력 형식: 마크다운/번호 없이 자연 한국어 문단만."
        )

        result = self.call_llm(system, user, max_tokens=600)
        return (result or "").strip()

    # ─────────────────────────────────────────────
    # LLM — 월간 정리 + 새 달 방향 안내 (monthly 모드)
    # ─────────────────────────────────────────────
    def _build_monthly_summary(self, state: dict, regime_out: dict, scout_out: dict) -> str:
        """지난 달 종합 + 새 달 좌측거래 관점 방향 안내."""
        m2_history = state.get("m2_history", {}) or {}
        # 지난 30일 RRG (분면별 누적 카운트)
        quadrant_counts: dict = {"LEADING": {}, "IMPROVING": {}, "WEAKENING": {}, "LAGGING": {}}
        for d, snap in m2_history.items():
            if not isinstance(snap, dict):
                continue
            for ticker, info in snap.items():
                if not isinstance(info, dict):
                    continue
                q = info.get("quadrant", "")
                if q in quadrant_counts:
                    quadrant_counts[q][ticker] = quadrant_counts[q].get(ticker, 0) + 1

        quad_lines = []
        for q in ["LEADING", "IMPROVING", "WEAKENING", "LAGGING"]:
            top = sorted(quadrant_counts[q].items(), key=lambda x: -x[1])[:5]
            top_str = ", ".join(f"{t}({n}일)" for t, n in top) or "(없음)"
            quad_lines.append(f"  {q}: {top_str}")

        upcoming = (regime_out.get("macro", {}) or {}).get("upcoming", []) or []
        upcoming_str = "\n".join(
            f"  - {evt.get('date')} {evt.get('name')} (영향: {evt.get('impact', '?')})"
            for evt in upcoming[:7]
        ) or "  (없음)"

        vix_data = regime_out.get("vix_data", {}) or {}
        fx = regime_out.get("fx", {}) or {}
        vix_str = f"VIX {vix_data.get('value', '?')} ({vix_data.get('regime', '?')})"
        fx_str = f"원/달러 {fx.get('current', '?')}원 ({fx.get('label', '')})"

        system = (
            "당신은 RONIN 트레이딩 시스템의 월간 정리 분석가입니다.\n"
            "역할: 지난 달 시장 흐름 종합 + 새 달 좌측거래 관점 방향 안내.\n"
            "원칙:\n"
            "1. 한국어로만 작성. 결론·구체 수치 우선.\n"
            "2. 3~4문단 구조:\n"
            "   ① 지난 달 매크로 핵심 변화 (VIX/환율/금리 추세)\n"
            "   ② 섹터 강도 변화 (RRG 누적 빈도 기반)\n"
            "   ③ 새 달 좌측거래 키포인트 2~3개\n"
            "   ④ 주의할 매크로 이벤트\n"
            "3. 각 문단 100~180자.\n"
            "4. 진입/exit 명령 금지.\n"
            "5. 환각 금지."
        )

        user = (
            "다음은 지난 달 데이터입니다. 월간 정리 + 새 달 방향 안내를 작성해주세요.\n\n"
            f"[현재 매크로 환경]\n  {vix_str}\n  {fx_str}\n\n"
            f"[지난 30일 섹터 RRG 분면별 출현 빈도]\n{chr(10).join(quad_lines)}\n\n"
            f"[새 달 매크로 일정 (최대 7개)]\n{upcoming_str}\n\n"
            "출력 형식: 마크다운/번호 없이 자연 한국어 문단만."
        )

        result = self.call_llm(system, user, max_tokens=900)
        return (result or "").strip()

    # ─────────────────────────────────────────────
    # LLM — 영문 뉴스 한국어 요약 (v3 신규)
    # ─────────────────────────────────────────────
    def _translate_news_korean(self, guard_out: dict) -> dict:
        """GUARD alerts의 영문 뉴스 → 한국어 1줄 요약.

        한 번의 LLM 호출로 여러 종목 뉴스 동시 처리 (효율).
        실패 시 영문 그대로 유지 (fallback).
        """
        alerts = guard_out.get("alerts", [])
        if not alerts:
            return guard_out

        # 영문 뉴스 있는 종목만
        news_to_translate = []
        for a in alerts:
            for n in a.get("news", []):
                headline = n.get("headline", "").strip()
                if headline:
                    news_to_translate.append({
                        "ticker": a["ticker"],
                        "headline": headline,
                        "summary": n.get("summary", "")[:200],
                    })

        if not news_to_translate:
            return guard_out

        system = (
            "당신은 RONIN 트레이딩 시스템의 뉴스 요약자입니다.\n"
            "역할: 영문 종목 뉴스 헤드라인을 한국어 1줄로 압축.\n"
            "원칙:\n"
            "1. 핵심 사실만 전달 (가격 영향 위주).\n"
            "2. 30~50자 이내. 너무 짧으면 의미 손실, 너무 길면 안 됨.\n"
            "3. 종목 영향 톤 명시 (호재/악재/중립 또는 단순 사실).\n"
            "4. 환각 금지. 헤드라인에 없는 정보 추가 X.\n"
            "5. 회사명은 영문 약어 그대로 (예: NVO, MSFT).\n"
        )

        user = (
            "다음 영문 뉴스 헤드라인을 각각 한국어 1줄로 요약해주세요.\n"
            "JSON 배열 형식으로만 출력 (마크다운 금지).\n"
            f"형식: [{{\"ticker\": \"...\", \"headline\": \"<원문>\", \"ko\": \"<한국어 요약>\"}}, ...]\n"
            f"입력 순서대로 같은 개수의 항목을 반환해주세요.\n\n"
            f"뉴스:\n{json.dumps(news_to_translate, ensure_ascii=False, indent=2)}"
        )

        raw = self.call_llm(system, user, max_tokens=600)
        if not raw:
            return guard_out

        try:
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            translations = json.loads(cleaned)
            # 매핑: (ticker, headline) → ko_summary
            ko_map: dict[tuple, str] = {}
            for t in translations:
                key = (t.get("ticker", ""), t.get("headline", ""))
                ko_map[key] = t.get("ko", "")
        except Exception as e:
            self.log.warning("[digest news ko] JSON 파싱 실패: %s", e)
            return guard_out

        # alerts 깊은 복사 후 ko_summary 주입
        new_alerts = []
        for a in alerts:
            new_a = dict(a)
            new_news = []
            for n in a.get("news", []):
                new_n = dict(n)
                ko = ko_map.get((a["ticker"], n.get("headline", "")), "")
                new_n["ko_summary"] = ko
                new_news.append(new_n)
            new_a["news"] = new_news
            new_alerts.append(new_a)

        new_guard = dict(guard_out)
        new_guard["alerts"] = new_alerts
        return new_guard

    # ─────────────────────────────────────────────
    # LLM — 후보 자연어 해석
    # ─────────────────────────────────────────────
    def _enrich_candidates_llm(self, candidates: list) -> list:
        """후보 종목들에 LLM 1줄 해석 추가 (v2 — 구체 데이터 노출)."""
        if not candidates:
            return []

        system = (
            "당신은 RONIN 트레이딩 시스템의 후보 해설자입니다.\n"
            "역할: 사전 감지 신호가 켜진 종목 각각에 대해 한국어 1줄 해석.\n"
            "원칙:\n"
            "1. 신호 데이터의 구체 수치를 포함 (예: 'BBW 0.4% — 평균의 32%까지 압축').\n"
            "2. 좌측거래(역추세 바닥 포착) 시스템 관점.\n"
            "3. 진입 명령 금지 — '관찰가치' 수준의 평가만.\n"
            "4. 1줄 = 60자 이내.\n"
            "5. 환각 금지. 데이터에 없는 숫자 만들지 마."
        )

        # 후보 데이터 — 신호 디테일까지 노출
        cand_summaries = []
        for c in candidates:
            summary = {
                "ticker": c["ticker"],
                "name": c.get("name", ""),
                "country": c["country"],
                "sector": c.get("sector", ""),
                "score": c["score"],
                "signals_detail": c["signals"],  # ← 구체 수치 포함
            }
            cand_summaries.append(summary)

        user = (
            "다음 후보 종목들에 대해 각각 1줄 해석을 한국어로 만들어주세요.\n"
            "각 종목의 'signals_detail' 안의 구체 수치를 활용하세요.\n"
            "JSON 배열 형식으로만 출력 (마크다운 금지).\n"
            f"형식: [{{\"ticker\": \"...\", \"comment\": \"...\"}}, ...]\n\n"
            f"후보:\n{json.dumps(cand_summaries, ensure_ascii=False, indent=2)}"
        )

        raw = self.call_llm(system, user, max_tokens=800)
        if not raw:
            # LLM 실패 시 후보 그대로 반환
            return [{**c, "comment": ""} for c in candidates]

        try:
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            comments = json.loads(cleaned)
            comment_map = {c["ticker"]: c.get("comment", "") for c in comments}
            return [
                {**c, "comment": comment_map.get(c["ticker"], "")}
                for c in candidates
            ]
        except Exception as e:
            self.log.warning("[digest llm] 파싱 실패: %s", e)
            return [{**c, "comment": ""} for c in candidates]

    # ─────────────────────────────────────────────
    # 텔레그램 메시지 (4000자 한도)
    # ─────────────────────────────────────────────
    def _build_telegram(
        self,
        candidates: list,
        guard_out: dict,
        regime_out: dict,
        briefing_mode: str = "daily",
        period_summary: str = "",
    ) -> str:
        max_chars = self.settings["digest"]["telegram"]["max_chars"]
        date_str = now_kst().strftime("%Y-%m-%d (%a)")

        # 모드별 헤더 라벨
        mode_badge = ""
        if briefing_mode == "monthly":
            mode_badge = " · 월간 정리"
        elif briefing_mode == "weekly":
            mode_badge = " · 주간 종합"

        lines = [f"<b>📊 RONIN BRIEF — {date_str}{mode_badge}</b>", ""]

        # ── 0. 주간/월간 종합 (있을 때만) ──
        if period_summary:
            if briefing_mode == "monthly":
                lines.append("<b>📅 월간 정리 + 새 달 방향</b>")
            else:
                lines.append("<b>📅 주간 종합 + 새 주 방향</b>")
            # 텔레그램은 너무 길지 않게 자름 (저널은 풀버전)
            short = period_summary if len(period_summary) <= 600 else period_summary[:580] + "…"
            lines.append(f"<i>{short}</i>")
            lines.append("")

        # ── 1. 매크로 환경 (REGIME) ──
        vix = regime_out.get("vix")
        vix_data = regime_out.get("vix_data", {})
        if vix is not None:
            vix_label = vix_data.get("label", "")
            side_note = vix_data.get("side_note", "")
            lines.append(f"<b>🌡 환경</b>")
            lines.append(f"VIX {vix} ({vix_data.get('regime', '?')} — {vix_label})")
            if side_note:
                lines.append(f"<i>{side_note}</i>")
            lines.append("")

        # 환율
        fx = regime_out.get("fx", {})
        if fx.get("current"):
            lines.append(
                f"<b>💱 환율</b> {fx['current']}원 — {fx.get('label', '')}"
            )
            judgment = fx.get("judgment", "")
            if judgment:
                lines.append(f"<i>{judgment}</i>")
            lines.append("")

        # 어제 발표 + 해석
        macro = regime_out.get("macro", {})
        yesterday = macro.get("yesterday_announced", [])
        if yesterday:
            interp = regime_out.get("interpretation", {}).get("announcements_interpretation", "")
            lines.append(f"<b>📅 어제 발표</b>")
            for evt in yesterday[:2]:
                lines.append(f"• {evt.get('name')}")
            if interp:
                lines.append(f"<i>{interp[:400]}</i>")
            lines.append("")

        # 이번 주 예정
        upcoming = macro.get("upcoming", [])
        if upcoming:
            lines.append(f"<b>📆 이번 주</b>")
            for evt in upcoming[:3]:
                impact = evt.get("impact", "")
                marker = "🔴" if impact == "high" else "🟡"
                lines.append(f"{marker} {evt.get('date')} {evt.get('name')}")
            lines.append("")

        # ── 2. SCOUT 후보 ──
        if candidates:
            lines.append(f"<b>🎯 신규 후보 ({len(candidates)}개)</b>")
            for c in candidates:
                flag = _COUNTRY_FLAG.get(c["country"], "·")
                cap = _format_market_cap(c.get("market_cap", 0))
                sig_short = _format_signals_short(c["signals"])
                lines.append(
                    f"{flag} <b>{c['ticker']}</b> ({c.get('name', '')[:30]}) {cap} | 점수 {c['score']}/5"
                )
                lines.append(f"  신호: {sig_short}")
                if c.get("comment"):
                    lines.append(f"  <i>{c['comment']}</i>")
            lines.append("")
        else:
            lines.append(f"<b>🎯 신규 후보</b> 오늘 없음 (사전 감지 임계 미달)")
            lines.append("")

        # ── 3. GUARD 보유 포지션 ──
        alerts = guard_out.get("alerts", [])
        quiet = guard_out.get("quiet", [])
        if alerts:
            lines.append(f"<b>📌 보유 ({guard_out.get('held_count', 0)}종목 — 주목 {len(alerts)})</b>")
            for a in alerts:
                price = a.get("price", {})
                if price:
                    lines.append(
                        f"• <b>{a['ticker']}</b> ${price.get('close', '?')} "
                        f"({price.get('daily_pct', 0):+.1f}%)"
                    )
                else:
                    lines.append(f"• <b>{a['ticker']}</b> 가격 수집 실패")
                if a.get("news"):
                    n = a["news"][0]
                    # 한국어 요약 우선, 없으면 영문 헤드라인 (v3 패치)
                    ko = n.get("ko_summary", "").strip()
                    if ko:
                        lines.append(f"  📰 {ko}")
                    else:
                        lines.append(f"  📰 {n['headline'][:80]}")
            if quiet:
                lines.append(f"<i>변동 없음: {', '.join(quiet)}</i>")
            lines.append("")
        elif guard_out.get("held_count", 0) > 0:
            lines.append(
                f"<b>📌 보유 {guard_out.get('held_count', 0)}종목</b> 모두 변동 없음"
            )
            lines.append("")

        # ── 4. M7 상관관계 (GUARD에서 흡수됨) ──
        m7 = guard_out.get("m7_context", "")
        if m7:
            # M7은 raw 텍스트라 짧게
            m7_short = m7.split("\n")[1] if "\n" in m7 else m7
            lines.append(f"<i>{m7_short[:200]}</i>")
            lines.append("")

        # ── 5. 학습 노트 ──
        notes = regime_out.get("interpretation", {}).get("learning_notes", [])
        if notes:
            lines.append(f"<b>📚 학습</b>")
            for n in notes[:2]:
                term = n.get("term", "")
                explain = n.get("explain", "")
                if term and explain:
                    lines.append(f"• <b>{term}</b>: {explain[:100]}")

        # 길이 제한
        text = "\n".join(lines)
        if len(text) > max_chars:
            self.log.warning("[digest] 텔레그램 길이 초과 (%d > %d), 자르기", len(text), max_chars)
            text = text[:max_chars - 50] + "\n\n... (이하 저널 BRIEFING 시트 참조)"

        return text

    # ─────────────────────────────────────────────
    # 저널 BRIEFING 시트 (상세, 한국어 통일, 길이 제한 없음)
    # ─────────────────────────────────────────────
    def _build_sheets_detailed(
        self,
        scout_out,
        guard_out,
        regime_out,
        candidates_with_comment,
        briefing_mode: str = "daily",
        period_summary: str = "",
    ) -> str:
        """저널 본문 빌드.

        원칙 (v4 한글화):
        - 모든 라벨/섹션명 한국어 통일
        - 영문 ETF/티커 코드는 한글 라벨 동반 (정보 보존)
        - 영문 뉴스 → ko_summary 우선 사용 (alerts에서 직접)
        - guard_out["context_text"] / regime_out["context_text"] 의존 X
        - 디테일 강화: 모든 데이터 노출
        - briefing_mode in (weekly, monthly) → period_summary 상단 섹션 추가
        """
        SEP = "═" * 60

        now = now_kst()
        date_str = now.strftime("%Y-%m-%d (%a) %H:%M KST")

        # 헤더 라벨
        if briefing_mode == "monthly":
            header_label = "RONIN 월간 정리 브리핑"
        elif briefing_mode == "weekly":
            header_label = "RONIN 주간 종합 브리핑"
        else:
            header_label = "RONIN 일일 브리핑"

        lines = [
            SEP,
            f"■ {header_label} — {date_str}",
            SEP,
            "",
        ]

        # ▣ 주간/월간 종합 섹션 (있을 때만, 매크로 환경 위)
        if period_summary:
            if briefing_mode == "monthly":
                lines.append("▣ 월간 정리 + 새 달 방향")
            else:
                lines.append("▣ 주간 종합 + 새 주 방향")
            lines.append("")
            for ln in period_summary.split("\n"):
                lines.append(f"  {ln}" if ln.strip() else "")
            lines.append("")

        # ▣ 매크로 환경
        lines.extend(self._build_journal_regime(regime_out))

        # ■ 정찰 (SCOUT)
        lines.extend(self._build_journal_scout(scout_out, candidates_with_comment))

        # ■ 감시 (GUARD)
        lines.extend(self._build_journal_guard(guard_out))

        # ■ 메타
        lines.extend(self._build_journal_meta(scout_out, guard_out, regime_out))

        return "\n".join(lines)

    # ─────────────────────────────────────────────
    # 저널 섹션 빌더 — 매크로 환경
    # ─────────────────────────────────────────────
    def _build_journal_regime(self, regime_out: dict) -> list:
        lines = ["▣ 매크로 환경", ""]

        # VIX
        vix_data = regime_out.get("vix_data", {}) or {}
        vix_val = vix_data.get("value")
        if vix_val is None:
            vix_val = regime_out.get("vix")
        if vix_val is not None:
            regime_code = vix_data.get("regime", "UNKNOWN")
            regime_ko = _VIX_REGIME_KO.get(regime_code, regime_code)
            label = vix_data.get("label", "")
            side_note = vix_data.get("side_note", "")
            label_part = f" — {label}" if label else ""
            side_part = f", {side_note}" if side_note else ""
            lines.append(f"  • VIX {vix_val} ({regime_ko}{label_part}{side_part})")

        # 환율
        fx = regime_out.get("fx", {}) or {}
        if fx.get("current") is not None:
            label = fx.get("label", "")
            judgment = fx.get("judgment", "")
            label_part = f" — {label}" if label else ""
            judg_part = f" / {judgment}" if judgment else ""
            lines.append(f"  • 원/달러 {fx['current']}원{label_part}{judg_part}")

        # 섹터 RRG (4분면)
        rrg = regime_out.get("rrg", {}) or {}
        by_quad = rrg.get("by_quadrant", {}) or {}
        if by_quad:
            lines.append("")
            lines.append("  • 섹터 상대강도 (4분면):")
            for q in ["LEADING", "IMPROVING", "WEAKENING", "LAGGING"]:
                items = by_quad.get(q, [])
                if not items:
                    continue
                ko = _QUADRANT_KO.get(q, q)
                tickers = ", ".join(
                    f"{i.get('label', i.get('ticker', '?'))}({i.get('ticker', '?')})"
                    for i in items[:6]
                )
                lines.append(f"      {ko}({q}) : {tickers}")

            transitions = rrg.get("transitions", []) or []
            if transitions:
                lines.append("")
                lines.append("  • 분면 전환:")
                for t in transitions:
                    lines.append(
                        f"      {t.get('label', t.get('ticker', '?'))}"
                        f"({t.get('ticker', '?')}): {t.get('transition', '')}"
                    )

        # ▣ 어제 발표 + 해석
        macro = regime_out.get("macro", {}) or {}
        yesterday = macro.get("yesterday_announced", []) or []
        interp = (regime_out.get("interpretation", {}) or {}).get(
            "announcements_interpretation", ""
        )
        if yesterday:
            lines.append("")
            lines.append("▣ 어제 발표")
            for evt in yesterday:
                name = evt.get("name", "")
                actual = evt.get("actual", "")
                actual_part = f" — 실제 {actual}" if actual else ""
                lines.append(f"  • {name}{actual_part}")
            if interp:
                lines.append("")
                lines.append(f"  해석: {interp}")

        # ▣ 이번 주 예정
        upcoming = macro.get("upcoming", []) or []
        if upcoming:
            lines.append("")
            lines.append("▣ 이번 주 예정")
            for evt in upcoming[:5]:
                impact = evt.get("impact", "")
                marker = "🔴" if impact == "high" else ("🟡" if impact == "medium" else "·")
                lines.append(f"  {marker} {evt.get('date')}  {evt.get('name')}")

        # ▣ 학습 노트
        notes = (regime_out.get("interpretation", {}) or {}).get("learning_notes", []) or []
        if notes:
            lines.append("")
            lines.append("▣ 학습 노트")
            for n in notes:
                term = n.get("term", "")
                explain = n.get("explain", "")
                if term and explain:
                    lines.append(f"  • {term}: {explain}")

        lines.append("")
        return lines

    # ─────────────────────────────────────────────
    # 저널 섹션 빌더 — 정찰 (SCOUT)
    # ─────────────────────────────────────────────
    def _build_journal_scout(self, scout_out: dict, candidates: list) -> list:
        SEP = "═" * 60
        lines = [
            SEP,
            "■ 정찰 (SCOUT) — 신규 후보 발굴",
            SEP,
            "",
        ]

        scanned = scout_out.get("scanned_total", 0)
        cooldown = scout_out.get("cooldown_skipped", 0)
        ohlcv_eval = scout_out.get("ohlcv_evaluated", 0)
        by_country = scout_out.get("by_country", {}) or {}
        passed = len(candidates)

        lines.append(f"  • 스캔 종목   : {scanned:,}개 (재선정대기 제외 {cooldown}개)")
        lines.append(f"  • 시세 평가   : {ohlcv_eval:,}개")
        lines.append(f"  • 통과 후보   : {passed}개")
        if by_country:
            parts = [f"{_COUNTRY_KO.get(k, k)} {v}" for k, v in by_country.items()]
            lines.append(f"  • 국가별     : {' / '.join(parts)}")
        lines.append("")

        if candidates:
            for idx, c in enumerate(candidates, 1):
                country_ko = _COUNTRY_KO.get(c.get("country", ""), c.get("country", ""))
                cap = _format_market_cap(c.get("market_cap", 0))
                name = (c.get("name", "") or "")[:40]
                lines.append(f"▷ 후보 {idx}: {c['ticker']} ({name}) — {country_ko}")
                lines.append(f"    섹터    : {c.get('sector', '미분류')} | 시총 : {cap}")
                lines.append(f"    점수    : {c['score']}/5")

                sigs = c.get("signals", {}) or {}
                if sigs:
                    lines.append(f"    사전감지 신호 ({len(sigs)}개):")
                    for sig_name, sig_info in sigs.items():
                        label = _format_signal_ko(sig_name, sig_info)
                        lines.append(f"      • {label}")

                if c.get("comment"):
                    lines.append(f"    해석    : {c['comment']}")
                lines.append("")
        else:
            lines.append("  (오늘 채택 후보 없음 — 사전 감지 임계 미달)")
            lines.append("")

        return lines

    # ─────────────────────────────────────────────
    # 저널 섹션 빌더 — 감시 (GUARD)
    # ─────────────────────────────────────────────
    def _build_journal_guard(self, guard_out: dict) -> list:
        SEP = "═" * 60
        lines = [
            SEP,
            "■ 감시 (GUARD) — 보유 포지션",
            SEP,
            "",
        ]

        held_count = guard_out.get("held_count", 0)
        alerts = guard_out.get("alerts", []) or []
        quiet = guard_out.get("quiet", []) or []
        threshold = self.settings.get("guard", {}).get("alert_threshold_pct", 2.0)

        lines.append(
            f"  • 보유: {held_count}종목 | "
            f"주목 (변동 ±{threshold}% 또는 뉴스): {len(alerts)}개"
        )
        lines.append("")

        if alerts:
            lines.append("▶ 주목 종목")
            lines.append("")
            for idx, a in enumerate(alerts, 1):
                ticker = a.get("ticker", "?")
                status_ko = _STATUS_KO.get(a.get("status", ""), a.get("status", ""))
                price = a.get("price", {}) or {}
                close = price.get("close", "?")
                d_pct = price.get("daily_pct", 0) or 0
                w_pct = price.get("weekly_pct", 0) or 0

                num = _circled_num(idx)
                status_part = f"  [{status_ko}]" if status_ko else ""
                lines.append(f"  {num} {ticker}{status_part}  ${close}")
                try:
                    lines.append(f"      변동   : 일간 {d_pct:+.1f}%, 주간 {w_pct:+.1f}%")
                except Exception:
                    lines.append(f"      변동   : 일간 {d_pct}, 주간 {w_pct}")

                news_list = a.get("news", []) or []
                if news_list:
                    lines.append(f"      뉴스   :")
                    for n in news_list:
                        ko = (n.get("ko_summary") or "").strip()
                        if ko:
                            lines.append(f"        📰 {ko}")
                        else:
                            head = (n.get("headline", "") or "")[:80]
                            if head:
                                lines.append(f"        📰 {head}")

                memo = a.get("memo", "")
                if memo:
                    lines.append(f"      메모   : {memo}")
                lines.append("")

        if quiet:
            lines.append(
                f"▷ 변동 없음 ({len(quiet)}종목): {', '.join(quiet)}"
            )
            lines.append("")

        # M7 상관관계 경고 (있을 때만)
        m7 = guard_out.get("m7_context", "")
        if m7:
            lines.append("▶ 상관관계 (M7)")
            for ml in m7.split("\n"):
                if ml.strip():
                    lines.append(f"  {ml}")
            lines.append("")

        return lines

    # ─────────────────────────────────────────────
    # 저널 섹션 빌더 — 메타
    # ─────────────────────────────────────────────
    def _build_journal_meta(self, scout_out, guard_out, regime_out) -> list:
        SEP = "═" * 60
        lines = [
            SEP,
            "■ 메타",
            SEP,
            "",
        ]

        errors = []
        if scout_out.get("error"):
            errors.append(f"SCOUT: {scout_out['error']}")
        if guard_out.get("error"):
            errors.append(f"GUARD: {guard_out['error']}")
        if regime_out.get("error"):
            errors.append(f"REGIME: {regime_out['error']}")

        if errors:
            lines.append("  • 에러:")
            for e in errors:
                lines.append(f"      - {e}")
        else:
            lines.append("  • 에러: 없음")
        lines.append("")
        return lines

    def _error_output(self, error_msg: str) -> dict:
        return {
            "telegram_text": self.settings["digest"]["telegram"]["fallback_message"],
            "sheets_text": f"[DIGEST 에러] {error_msg}",
            "candidates_count": 0,
            "alerts_count": 0,
            "all_empty": True,
            "error": error_msg,
        }
