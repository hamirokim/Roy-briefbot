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

        # ── LLM 호출 — SCOUT 후보 자연어 해석 ──
        candidates_with_explanation = self._enrich_candidates_llm(scout_out.get("candidates", []))

        # ── 텔레그램 메시지 생성 ──
        telegram_text = self._build_telegram(
            candidates_with_explanation, guard_out, regime_out
        )

        # ── 저널 BRIEFING 시트 메시지 생성 (상세) ──
        sheets_text = self._build_sheets_detailed(
            scout_out, guard_out, regime_out, candidates_with_explanation
        )

        return {
            "telegram_text": telegram_text,
            "sheets_text": sheets_text,
            "candidates_count": len(scout_out.get("candidates", [])),
            "alerts_count": len(guard_out.get("alerts", [])),
            "all_empty": False,
        }

    # ─────────────────────────────────────────────
    # LLM — 후보 자연어 해석
    # ─────────────────────────────────────────────
    def _enrich_candidates_llm(self, candidates: list) -> list:
        """후보 종목들에 LLM 1줄 해석 추가."""
        if not candidates:
            return []

        system = (
            "당신은 RONIN 트레이딩 시스템의 후보 해설자입니다.\n"
            "역할: 사전 감지 신호가 켜진 종목 각각에 대해 한국어 1줄 해석.\n"
            "원칙:\n"
            "1. 신호 데이터에 기반. 환각 금지.\n"
            "2. 좌측거래(역추세 바닥 포착) 시스템 관점.\n"
            "3. 진입 명령 금지 — '관찰 가치' 수준의 평가만.\n"
            "4. 1줄 = 50자 이내."
        )

        # 후보 데이터 요약
        cand_summaries = []
        for c in candidates:
            summary = {
                "ticker": c["ticker"],
                "name": c.get("name", ""),
                "country": c["country"],
                "sector": c.get("sector", ""),
                "score": c["score"],
                "signals": list(c["signals"].keys()),
            }
            cand_summaries.append(summary)

        user = (
            "다음 후보 종목들에 대해 각각 1줄 해석을 한국어로 만들어주세요.\n"
            "JSON 배열 형식으로만 출력 (마크다운 금지).\n"
            f"형식: [{{\"ticker\": \"...\", \"comment\": \"...\"}}, ...]\n\n"
            f"후보:\n{json.dumps(cand_summaries, ensure_ascii=False, indent=2)}"
        )

        raw = self.call_llm(system, user, max_tokens=500)
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
    def _build_telegram(self, candidates: list, guard_out: dict, regime_out: dict) -> str:
        max_chars = self.settings["digest"]["telegram"]["max_chars"]
        date_str = datetime.now().strftime("%Y-%m-%d (%a)")

        lines = [f"<b>📊 RONIN BRIEF — {date_str}</b>", ""]

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
    # 저널 BRIEFING 시트 (상세, 길이 제한 없음)
    # ─────────────────────────────────────────────
    def _build_sheets_detailed(self, scout_out, guard_out, regime_out, candidates_with_comment) -> str:
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"=== RONIN BRIEFING — {date_str} ===", ""]

        # 매크로 환경 (REGIME context 그대로)
        regime_ctx = regime_out.get("context_text", "")
        if regime_ctx:
            lines.append(regime_ctx)
            lines.append("")

        # SCOUT — 채택 후보
        lines.append("=" * 50)
        lines.append("SCOUT — 채택 후보")
        lines.append("=" * 50)
        scanned = scout_out.get("scanned_total", 0)
        by_country = scout_out.get("by_country", {})
        passed = len(candidates_with_comment)
        cooldown = scout_out.get("cooldown_skipped", 0)
        ohlcv_eval = scout_out.get("ohlcv_evaluated", 0)
        lines.append(
            f"스캔: {scanned}종목 (cooldown 제외 {cooldown}) | "
            f"OHLCV 평가 {ohlcv_eval} | 통과 {passed}"
        )
        lines.append(f"국가별: {by_country}")
        lines.append("")

        if candidates_with_comment:
            for c in candidates_with_comment:
                lines.append(f"• [{c['country']}] {c['ticker']} ({c.get('name', '')})")
                lines.append(f"  섹터: {c.get('sector', 'N/A')} | 시총: {_format_market_cap(c.get('market_cap', 0))}")
                lines.append(f"  점수: {c['score']}/5 | 신호: {list(c['signals'].keys())}")
                if c.get("comment"):
                    lines.append(f"  해석: {c['comment']}")
                # 신호별 디테일
                for sig_name, sig_info in c["signals"].items():
                    lines.append(f"    {sig_name}: {sig_info}")
                lines.append("")
        else:
            lines.append("(채택 후보 없음 — 임계 미달)")
            lines.append("")

        # GUARD — 보유 포지션 전체 (변동 없는 것 포함)
        lines.append("=" * 50)
        lines.append("GUARD — 보유 포지션")
        lines.append("=" * 50)
        guard_ctx = guard_out.get("context_text", "")
        if guard_ctx:
            lines.append(guard_ctx)
        else:
            lines.append("(보유 종목 없음)")

        # 메타 (디버그)
        lines.append("")
        lines.append("=" * 50)
        lines.append("메타")
        lines.append("=" * 50)
        errors = []
        if scout_out.get("error"):
            errors.append(f"SCOUT: {scout_out['error']}")
        if guard_out.get("error"):
            errors.append(f"GUARD: {guard_out['error']}")
        if regime_out.get("error"):
            errors.append(f"REGIME: {regime_out['error']}")
        if errors:
            lines.append("에러:")
            for e in errors:
                lines.append(f"  - {e}")
        else:
            lines.append("에러 없음")

        return "\n".join(lines)

    def _error_output(self, error_msg: str) -> dict:
        return {
            "telegram_text": self.settings["digest"]["telegram"]["fallback_message"],
            "sheets_text": f"[DIGEST 에러] {error_msg}",
            "candidates_count": 0,
            "alerts_count": 0,
            "all_empty": True,
            "error": error_msg,
        }
