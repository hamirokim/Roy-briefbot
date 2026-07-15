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

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agents.base import BaseAgent
from src.utils import now_kst

logger = logging.getLogger(__name__)

_MISSING_CATALYST_TEXTS = {
    "정보 부족",
    "촉매 데이터 미연결",
    "정보 부족 (LLM 실패)",
}


def _has_real_catalyst(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if cleaned in _MISSING_CATALYST_TEXTS:
        return False
    if "촉매 데이터 미연결" in cleaned:
        return False
    lowered = cleaned.lower()
    if any(token in lowered for token in ["actual none", "actual null", "actual n/a", "estimate none", "estimate null"]):
        return False
    return True


def _candidate_catalyst_headline(candidate: dict) -> str:
    catalyst = candidate.get("catalyst_context", {}) or {}
    if catalyst.get("status") != "found":
        return ""
    news = catalyst.get("news", []) or []
    preferred = [
        item for item in news
        if str(item.get("classification", "") or "") == "POSITIVE_REVALUATION"
    ]
    for item in preferred + news:
        headline = str(item.get("headline", "") or "").strip()
        if _has_real_catalyst(headline):
            return headline[:90]
    return ""


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
    "CN_HK": "🇭🇰",
    "CN_A": "🇨🇳",
}

# ─── 저널 한글 매핑 (v4: 한글 통일) ───
_COUNTRY_KO = {
    "US": "미국",
    "KR": "한국",
    "JP": "일본",
    "CN_ADR": "중국ADR",
    "CN_HK": "중국/홍콩",
    "CN_A": "중국A주",
}
_SOURCE_KO = {
    "finviz+nasdaqtrader": "미국 공식상장+Finviz",
    "finviz": "미국 Finviz",
    "nasdaqtrader:fallback_no_cap": "미국 공식상장 fallback",
    "naver_market_sum_fallback": "한국 Naver 시총",
    "pykrx": "한국 KRX",
    "jpx_official+yfinance": "일본 JPX+yfinance",
    "yfinance_seed_fallback": "yfinance seed fallback",
    "yfinance_cn_adr": "중국 ADR seed",
    "yfinance_hk_china_seed": "중국/홍콩 seed",
    "yfinance_cn_a_seed": "중국 A주 seed",
    "akshare_eastmoney_a": "중국 A주 Eastmoney",
    "akshare_eastmoney_hk": "중국/홍콩 Eastmoney",
}
_QUALITY_FLAG_KO = {
    "overextended_20d": "20일 급등",
    "near_52w_high": "52주 고점 근처",
    "left_side_context": "좌측 관찰 구간",
    "low_liquidity_buffer": "유동성 여유 부족",
    "data_short": "시세 데이터 짧음",
}
_FACTOR_KO = {
    "liquidity_good": "유동성 충분",
    "liquidity_weak": "유동성 약함",
    "not_chasing": "추격매수 위험 낮음",
    "chasing_hot": "20일 급등 추격 위험",
    "chasing_extreme": "단기 과열 심함",
    "volatility_healthy": "변동성 정상",
    "volatility_extreme": "변동성 과도",
    "data_short": "데이터 짧음",
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
    "ronin_entry_v2": "RONIN Entry v2 근접",
    "ronin_structure_support": "RONIN 구조 지지 근접",
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


def _format_theme_etfs(etfs: list[dict], limit: int = 4) -> str:
    """테마 내부 ETF 상태를 짧게 표시."""
    parts = []
    for etf in (etfs or [])[:limit]:
        q = _QUADRANT_KO.get(etf.get("quadrant", ""), etf.get("quadrant", ""))
        parts.append(f"{etf.get('ticker')} {q}")
    return ", ".join(parts)


def _theme_counts_text(counts: dict) -> str:
    return (
        f"강함 {int(counts.get('강함', 0) or 0)} / "
        f"관찰 {int(counts.get('관찰', 0) or 0)} / "
        f"보류 {int(counts.get('보류', 0) or 0)}"
    )


def _candidate_judgment(candidate: dict) -> dict:
    """텔레그램 첫 화면용 후보 판단 라벨."""
    score = float(candidate.get("score", 0) or 0)
    signal_count = int(candidate.get("signal_count", len(candidate.get("signals", {}) or {})) or 0)
    quality_flags = set(candidate.get("quality_flags", []) or [])
    bq = candidate.get("buy_questions", {}) or {}
    star = str(bq.get("star_rating", "") or "")
    data_coverage = candidate.get("data_coverage", {}) or {}
    fund_status = str((data_coverage.get("fundamental", {}) or {}).get("status", ""))
    cat_status = str((data_coverage.get("catalyst", {}) or {}).get("status", ""))

    data_problem = fund_status in {
        "not_supported_non_us",
        "collector_import_failed",
        "collection_failed",
        "empty_result",
    } or cat_status in {"no_key", "non_us", "error", "bad_response", "http_400", "http_401", "http_429", "http_500"}
    hard_risk = bool(quality_flags & {"overextended_20d", "low_liquidity_buffer"})
    production_passed = bool((candidate.get("top3_selection") or {}).get("production_gate_passed"))

    if production_passed and not data_problem and not hard_risk:
        label = "강함"
        reason = "실전 추천 게이트를 통과한 강한 가격 구조와 품질 확인 후보"
    elif score >= 3.0 and signal_count >= 3 and not data_problem and not hard_risk and star in {"★★", "★★★"}:
        label = "강함"
        reason = "신호가 여러 개 겹치고, 확인 데이터도 크게 비지 않음"
    elif hard_risk:
        label = "보류"
        reason = "신호는 있지만 과열이나 유동성 같은 흠이 먼저 보임"
    elif data_problem:
        label = "관찰"
        reason = "가격 신호는 있지만 확인 데이터가 부족하거나 아직 수집 미지원"
    else:
        label = "관찰"
        reason = "조건 일부는 맞지만 강한 후보라고 보기엔 근거가 더 필요"

    return {"label": label, "reason": reason}


def _candidate_judgment_summary(candidates: list) -> dict:
    counts = {"강함": 0, "관찰": 0, "보류": 0}
    judged = []
    for c in candidates:
        judgment = _candidate_judgment(c)
        counts[judgment["label"]] = counts.get(judgment["label"], 0) + 1
        judged.append((c, judgment))
    if counts.get("강함", 0):
        conclusion = "검토할 만한 후보 있음"
    elif counts.get("관찰", 0):
        conclusion = "오늘은 관찰 중심"
    else:
        conclusion = "오늘은 무리해서 볼 후보 없음"
    return {"counts": counts, "judged": judged, "conclusion": conclusion}


def _top3_audit_from_scout(scout_out: dict) -> dict:
    radar_summary = (scout_out or {}).get("radar_summary", {}) or {}
    filter_audit = radar_summary.get("filter_audit", {}) or {}
    return filter_audit.get("top3_selection_audit", {}) or {}


def _format_llm_review_line(scout_out: dict) -> str:
    """텔레그램/저널에 쓰는 SCOUT LLM Top3 재심사 한 줄 요약."""
    top3 = _top3_audit_from_scout(scout_out)
    llm_review = top3.get("llm_review", {}) or {}
    if not llm_review:
        return ""

    status = str(llm_review.get("status", "") or "")
    enabled = llm_review.get("enabled")
    if enabled is False and status == "disabled":
        return "LLM 재심사: 비활성"
    if not status:
        return ""

    rule_based = llm_review.get("rule_based_top3") or top3.get("rule_based_top3") or []
    if not rule_based and status == "fallback_empty_pool":
        return "LLM 재심사: 추천 기준 통과 후보 없음"

    additions_allowed = bool(llm_review.get("llm_additions_allowed", False))
    override = "조정" if llm_review.get("llm_override") else "유지"
    if not additions_allowed:
        override = "축소/재정렬" if llm_review.get("llm_override") else "유지"
    final_top3 = (
        llm_review.get("final_top3")
        or top3.get("final_top3")
        or []
    )
    if isinstance(final_top3, str):
        final_top3 = [final_top3]
    final_text = "/".join(str(t).upper() for t in final_top3[:3] if t)

    parts = [f"LLM 재심사: {status}", override]
    if final_text:
        parts.append(f"최종 {final_text}")
    if status.startswith("fallback"):
        reason = str(llm_review.get("fallback_reason", "") or "").strip()
        if reason:
            parts.append(f"사유 {reason[:48]}")
    return " · ".join(parts)


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
        m6_out = state.get("m6_out", {}) or {}
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
        improvement_report = {}
        if briefing_mode == "weekly":
            period_summary = self._build_weekly_summary(state, regime_out, scout_out)
            self.log.info("[digest] 주간 종합 생성: %d자", len(period_summary))
        elif briefing_mode == "monthly":
            period_summary = self._build_monthly_summary(state, regime_out, scout_out)
            self.log.info("[digest] 월간 정리 생성: %d자", len(period_summary))
            try:
                from src.modules.monthly_improvement import build_monthly_improvement_report
                improvement_report = build_monthly_improvement_report(state, scout_out, m6_out)
                self.log.info(
                    "[digest] 월간 개선 리포트 생성: %d자",
                    len(improvement_report.get("summary_text", "")),
                )
            except Exception as e:
                self.log.warning("[digest] 월간 개선 리포트 생성 실패: %s", e)
                improvement_report = {}

        # ── LLM 호출 4 (Z3-4 D87 신규) — 매일 매크로 1줄 해석 ──
        # 후보 0일/알람 0일에도 콘텐츠 풍성하게 만들기 위함
        macro_interp = self._build_macro_interpretation_llm(regime_out, scout_out, guard_out_translated)
        self.log.info("[digest] 매크로 해석 생성: %d자", len(macro_interp))

        # ── 텔레그램 메시지 생성 ──
        telegram_text = self._build_telegram(
            candidates_with_explanation, guard_out_translated, regime_out,
            scout_out=scout_out,
            briefing_mode=briefing_mode,
            period_summary=period_summary,
            macro_interp=macro_interp,
            m6_out=m6_out,
            improvement_report=improvement_report,
        )

        # ── 저널 BRIEFING 시트 메시지 생성 (상세) ──
        sheets_text = self._build_sheets_detailed(
            scout_out, guard_out_translated, regime_out, candidates_with_explanation,
            briefing_mode=briefing_mode,
            period_summary=period_summary,
            macro_interp=macro_interp,
            m6_out=m6_out,
            improvement_report=improvement_report,
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
    # LLM — 매일 매크로 1~2줄 해석 (Z3-4 D87 신규)
    # 후보 0일/알람 0일 풍성 브리핑용
    # ─────────────────────────────────────────────
    def _build_macro_interpretation_llm(
        self, regime_out: dict, scout_out: dict, guard_out: dict
    ) -> str:
        """오늘 매크로 환경의 좌측거래 관점 1~2문단 해석.

        매일 호출. 후보/알람 없는 날에도 사용자가 가치 느끼도록.
        실패 시 빈 문자열.
        """
        vix_data = regime_out.get("vix_data", {}) or {}
        fx = regime_out.get("fx", {}) or {}
        rrg = regime_out.get("rrg", {}) or {}
        by_quad = rrg.get("by_quadrant", {}) or {}
        theme_intel = rrg.get("theme_intelligence", {}) or {}
        theme_focus = theme_intel.get("focus", []) or []
        macro = regime_out.get("macro", {}) or {}
        upcoming = macro.get("upcoming", []) or []

        quad_lines = []
        for q in ["LEADING", "IMPROVING", "WEAKENING", "LAGGING"]:
            items = by_quad.get(q, [])
            if not items:
                continue
            ko = _QUADRANT_KO.get(q, q)
            tickers = ", ".join(i.get("label", i.get("ticker", "?")) for i in items[:5])
            quad_lines.append(f"  {ko}: {tickers}")

        theme_lines = []
        for theme in theme_focus[:3]:
            theme_lines.append(
                f"  {theme.get('label')}: {theme.get('judgment')} — {theme.get('reason')}"
            )

        upcoming_lines = []
        for evt in upcoming[:3]:
            impact = evt.get("impact", "")
            marker = "🔴" if impact == "high" else ("🟡" if impact == "medium" else "·")
            upcoming_lines.append(f"  {marker} {evt.get('date')} {evt.get('name')}")

        n_candidates = len(scout_out.get("candidates", []) or [])
        n_alerts = len(guard_out.get("alerts", []) or [])

        system = (
            "당신은 RONIN 트레이딩 시스템의 매일 매크로 해석가입니다.\n"
            "역할: 오늘 매크로 환경 (VIX/환율/섹터 RRG/매크로 일정)을 좌측거래 관점에서 2문단으로 해석.\n"
            "원칙:\n"
            "1. 한국어. 결론·관찰 포인트 우선.\n"
            "2. 2문단 (각 80~150자):\n"
            "   ① 오늘 환경 핵심 (어떤 신호가 강한가, 어디 주목해야 하나)\n"
            "   ② 좌측거래 관점 관찰 포인트 (베어/강세 어느 쪽 매집/분배 가능성)\n"
            "3. 진입/exit 명령 X. 환경 평가 + 관찰만.\n"
            "4. 환각 X. 입력 데이터에 있는 수치만.\n"
            "5. 자연 한국어 문단 (마크다운/번호 X)."
        )

        user = (
            f"[오늘 매크로 환경]\n"
            f"  VIX: {vix_data.get('value', '?')} ({vix_data.get('regime', '?')})\n"
            f"  원/달러: {fx.get('current', '?')}원 ({fx.get('label', '')})\n"
            f"\n[섹터 RRG 4분면]\n"
            + ("\n".join(quad_lines) or "  (데이터 부족)")
            + f"\n\n[테마 흐름판]\n"
            + ("\n".join(theme_lines) or "  (뚜렷한 주목 테마 없음)")
            + f"\n\n[이번 주 매크로 일정]\n"
            + ("\n".join(upcoming_lines) or "  (없음)")
            + f"\n\n[오늘 시스템 상태]\n"
            f"  SCOUT 후보: {n_candidates}개\n"
            f"  GUARD 알람: {n_alerts}개\n\n"
            "위 환경에 대한 매크로 해석 (2문단)을 작성해주세요."
        )

        result = self.call_llm(system, user, max_tokens=400)
        return (result or "").strip()

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
        """GUARD alerts + quiet_full의 영문 뉴스 → 한국어 1줄 요약.

        D88 (Z3-4): quiet_full 종목 뉴스도 번역 (텔레그램/시트 보유 뉴스 한글 일관).
        한 번의 LLM 호출로 alerts + quiet_full 모두 동시 처리 (효율).
        실패 시 영문 그대로 유지 (fallback).
        """
        alerts = guard_out.get("alerts", []) or []
        quiet_full = guard_out.get("quiet_full", []) or []

        # 번역 대상 후보 = alerts + quiet_full (둘 다)
        all_targets = alerts + quiet_full
        if not all_targets:
            return guard_out

        # 영문 뉴스 있는 종목만 일괄 수집
        news_to_translate = []
        for entry in all_targets:
            for n in entry.get("news", []) or []:
                headline = (n.get("headline", "") or "").strip()
                if headline:
                    news_to_translate.append({
                        "ticker": entry.get("ticker", ""),
                        "headline": headline,
                        "summary": (n.get("summary", "") or "")[:200],
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

        # 입력 뉴스가 많으면 max_tokens 동적 증가
        n_news = len(news_to_translate)
        max_tok = max(600, n_news * 80)

        raw = self.call_llm(system, user, max_tokens=max_tok)
        if not raw:
            return guard_out

        try:
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            translations = json.loads(cleaned)
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
            for n in a.get("news", []) or []:
                new_n = dict(n)
                ko = ko_map.get((a.get("ticker", ""), n.get("headline", "")), "")
                new_n["ko_summary"] = ko
                new_news.append(new_n)
            new_a["news"] = new_news
            new_alerts.append(new_a)

        # quiet_full 동일 처리 (D88)
        new_quiet_full = []
        for q in quiet_full:
            new_q = dict(q)
            new_news = []
            for n in q.get("news", []) or []:
                new_n = dict(n)
                ko = ko_map.get((q.get("ticker", ""), n.get("headline", "")), "")
                new_n["ko_summary"] = ko
                new_news.append(new_n)
            new_q["news"] = new_news
            new_quiet_full.append(new_q)

        new_guard = dict(guard_out)
        new_guard["alerts"] = new_alerts
        new_guard["quiet_full"] = new_quiet_full
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
        scout_out: dict | None = None,
        briefing_mode: str = "daily",
        period_summary: str = "",
        macro_interp: str = "",
        m6_out: dict | None = None,
        improvement_report: dict | None = None,
    ) -> str:
        """텔레그램 메시지 생성.

        D87 (Z3-4): 텔레그램 = 시트 동일화 원칙. 풀 콘텐츠 빌드 후 텔레그램용 변환.
        후보 0일에도 풍성: RRG 4분면 + 매크로 LLM 해석 + m6 추적 + quiet 뉴스 노출.
        """
        max_chars = self.settings["digest"]["telegram"]["max_chars"]
        date_str = now_kst().strftime("%Y-%m-%d (%a)")
        scout_out = scout_out or {}
        m6_out = m6_out or {}
        improvement_report = improvement_report or {}

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

        # ── 1-A. 섹터 RRG 4분면 (D87 신규: 텔레그램에도 노출) ──
        rrg = regime_out.get("rrg", {}) or {}
        by_quad = rrg.get("by_quadrant", {}) or {}
        if by_quad:
            lines.append("<b>📊 섹터 RRG (4분면)</b>")
            for q in ["LEADING", "IMPROVING", "WEAKENING", "LAGGING"]:
                items = by_quad.get(q, [])
                if not items:
                    continue
                ko = _QUADRANT_KO.get(q, q)
                tickers = ", ".join(
                    i.get("label", i.get("ticker", "?")) for i in items[:6]
                )
                emoji = {"LEADING": "🟢", "IMPROVING": "🔵", "WEAKENING": "🟡", "LAGGING": "🔴"}.get(q, "·")
                lines.append(f"{emoji} {ko}: <i>{tickers}</i>")
            lines.append("")

        # ── 1-A-2. Theme Intelligence Layer ──
        theme_intel = rrg.get("theme_intelligence", {}) or {}
        theme_focus = theme_intel.get("focus", []) or []
        theme_counts = theme_intel.get("counts", {}) or {}
        if theme_focus:
            lines.append("<b>🧬 테마 흐름판</b>")
            lines.append(f"<i>기준: 강함=같은 테마 ETF 2개 이상 주도/개선 / 관찰=1개만 먼저 개선 / 보류=대부분 약화·부진</i>")
            lines.append(f"<i>오늘 분포: {_theme_counts_text(theme_counts)}</i>")
            for theme in theme_focus[:3]:
                etf_text = _format_theme_etfs(theme.get("etfs", []), 4)
                lines.append(
                    f"• <b>{theme.get('label')}</b> [{theme.get('judgment')}] "
                    f"<i>{theme.get('reason')}</i>"
                )
                if etf_text:
                    lines.append(f"  ETF: <i>{etf_text}</i>")
            lines.append("")
        elif theme_counts:
            lines.append("<b>🧬 테마 흐름판</b>")
            lines.append(f"<i>뚜렷한 주목 테마 없음 — {_theme_counts_text(theme_counts)}</i>")
            lines.append("")

        # 어제 발표 + 해석
        macro = regime_out.get("macro", {})
        yesterday = macro.get("yesterday_announced", [])
        if yesterday:
            interp = regime_out.get("interpretation", {}).get("announcements_interpretation", "")
            lines.append(f"<b>📅 어제 발표</b>")
            for evt in yesterday[:2]:
                lines.append(f"• {evt.get('name')}")
            source_coverage = macro.get("source_coverage", {}) or {}
            if source_coverage.get("status") == "DEGRADED":
                lines.append(
                    "<i>데이터 주의: "
                    f"FRED {source_coverage.get('fred_collected', 0)}/{source_coverage.get('fred_requested', 0)}, "
                    f"시장반응 {source_coverage.get('market_collected', 0)}/{source_coverage.get('market_requested', 0)} 수집 · "
                    "해석 신뢰도 하향</i>"
                )
            if interp:
                lines.append(f"<i>{interp[:400]}</i>")
            lines.append("")

        # ── 1-B. 매크로 해석 LLM (D87 신규: 매일 1~2문단) ──
        if macro_interp:
            lines.append(f"<b>🧠 매크로 해석</b>")
            # 텔레그램은 압축 (시트는 풀버전)
            interp_short = macro_interp if len(macro_interp) <= 500 else macro_interp[:480] + "…"
            lines.append(f"<i>{interp_short}</i>")
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
        radar_summary = scout_out.get("radar_summary", {}) or {}
        radar_count = int(radar_summary.get("radar_pool_count", 0) or 0)
        top_signals = radar_summary.get("top_signals", []) or []
        watchlist = scout_out.get("watchlist_candidates", []) or []
        llm_review_line = _format_llm_review_line(scout_out)
        if candidates:
            judgment_summary = _candidate_judgment_summary(candidates)
            counts = judgment_summary["counts"]
            lines.append(f"<b>🎯 신규 추천 판단</b>")
            lines.append(
                f"{judgment_summary['conclusion']} — "
                f"강함 {counts.get('강함', 0)} / 관찰 {counts.get('관찰', 0)} / 보류 {counts.get('보류', 0)}"
            )
            lines.append(
                "<i>기준: 강함=신호 여러 개+데이터 확인 양호 / "
                "관찰=신호는 있으나 확인 데이터 부족 / 보류=과열·유동성·수집 실패 같은 흠 우선</i>"
            )
            if radar_count:
                lines.append(f"<i>내부 관찰풀 {radar_count}개 중 엄선</i>")
            if llm_review_line:
                lines.append(f"<i>{llm_review_line}</i>")
            for c, judgment in judgment_summary["judged"]:
                flag = _COUNTRY_FLAG.get(c["country"], "·")
                cap = _format_market_cap(c.get("market_cap", 0))
                sig_short = _format_signals_short(c["signals"])
                lines.append(
                    f"{flag} <b>{c['ticker']}</b> [{judgment['label']}] {cap} | 레이더 {c.get('score', 0)}"
                )
                lines.append(f"  판단: <i>{judgment['reason']}</i>")
                lines.append(f"  신호: {sig_short or '신호 요약 없음'}")
                try:
                    from src.modules.m1_5_buyquestions import summarize_data_coverage
                    coverage_text = summarize_data_coverage(c)
                    if coverage_text:
                        lines.append(f"  데이터: <i>{coverage_text[:160]}</i>")
                except Exception as e:
                    self.log.debug("[digest] 데이터 커버리지 포맷 실패: %s", e)
                headline = _candidate_catalyst_headline(c)
                if headline:
                    lines.append(f"  촉매: <i>{headline}</i>")
            lines.append("")
        else:
            reason = radar_summary.get("no_candidate_reason") or "최종 보고 기준 미달"
            lines.append(f"<b>🎯 신규 추천</b> 오늘 없음")
            lines.append(f"<i>{reason}</i>")
            if radar_count:
                lines.append(f"내부 관찰풀은 {radar_count}개 쌓임")
            if llm_review_line:
                lines.append(f"<i>{llm_review_line}</i>")
            if top_signals:
                sig_name = top_signals[0][0] if isinstance(top_signals[0], (list, tuple)) else ""
                count = top_signals[0][1] if isinstance(top_signals[0], (list, tuple)) and len(top_signals[0]) > 1 else 0
                lines.append(f"가장 많이 나온 조짐: {_SIGNAL_KO.get(sig_name, sig_name)} {count}개")
            if watchlist:
                lines.append("")
                lines.append("<b>👀 관찰 레이더 (추천 아님)</b>")
                for w in watchlist[:3]:
                    flag = _COUNTRY_FLAG.get(w.get("country", ""), "·")
                    sig_text = _format_signals_short(w.get("signals", {}) or {})
                    lane = f"{w.get('selection_lane', '')}:{w.get('selection_lane_status', '')}".strip(":")
                    lines.append(
                        f"{flag} <b>{w.get('ticker')}</b> [{w.get('selection_tier')}] "
                        f"{lane} | 레이더 {w.get('score', 0)}"
                    )
                    reason = w.get("watch_reason") or sig_text
                    if reason:
                        lines.append(f"  대기 이유: <i>{reason}</i>")
                    if sig_text:
                        lines.append(f"  신호: {sig_text}")
            lines.append("")

        # ── 2-A. M6 SCOUT 추적 (D86 신규) ──
        m6_summary = m6_out.get("summary_text", "")
        performance_summary = ((m6_out.get("performance") or {}).get("summary_text", "") or "")
        if m6_summary:
            lines.append(f"<b>🔄 SCOUT 추적</b>")
            lines.append(f"<i>{m6_summary}</i>")
            if performance_summary:
                lines.append(f"<i>{performance_summary}</i>")
            lines.append("")

        if briefing_mode == "monthly" and improvement_report.get("summary_text"):
            lines.append("<b>🛠 월간 개선 리포트</b>")
            lines.append(f"<i>{improvement_report['summary_text'][:700]}</i>")
            actions = improvement_report.get("actions", []) or []
            for action in actions[:3]:
                lines.append(f"• {action}")
            lines.append("")

        # ── 3. GUARD 보유 포지션 ──
        alerts = guard_out.get("alerts", [])
        quiet_full = guard_out.get("quiet_full", []) or []  # D87: 전체 quiet 데이터 (티커+가격+뉴스)
        quiet = guard_out.get("quiet", [])
        held_count = guard_out.get("held_count", 0)

        if alerts:
            lines.append(f"<b>📌 보유 ({held_count}종목 — 주목 {len(alerts)})</b>")
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
                    ko = n.get("ko_summary", "").strip()
                    if ko:
                        lines.append(f"  📰 {ko}")
                    else:
                        lines.append(f"  📰 {n['headline'][:80]}")
            lines.append("")
        elif held_count > 0:
            lines.append(f"<b>📌 보유 {held_count}종목</b> 모두 변동 없음")
            lines.append("")

        # ── 3-A. Quiet 종목 뉴스 (D87 신규: 변동 X여도 의미 뉴스 있으면 push) ──
        if quiet_full:
            quiet_with_news = [q for q in quiet_full if q.get("news")]
            if quiet_with_news:
                lines.append(f"<b>📰 보유 종목 주요 뉴스</b>")
                for q in quiet_with_news[:4]:
                    ticker = q.get("ticker", "?")
                    price = q.get("price", {})
                    pct = price.get("daily_pct", 0) if price else 0
                    news_list = q.get("news", []) or []
                    if news_list:
                        n = news_list[0]
                        ko = n.get("ko_summary", "").strip()
                        head = ko or (n.get("headline", "") or "")[:100]
                        lines.append(f"• <b>{ticker}</b> ({pct:+.1f}%) — <i>{head}</i>")
                lines.append("")
        elif quiet:
            # quiet_full 없으면 옛 로직 (이름만)
            lines.append(f"<i>변동 없음: {', '.join(quiet)}</i>")
            lines.append("")

        # ── 4. M7 상관관계 (GUARD에서 흡수됨) ──
        m7 = guard_out.get("m7_context", "")
        if m7:
            m7_short = m7.split("\n")[1] if "\n" in m7 else m7
            lines.append(f"<i>{m7_short[:200]}</i>")
            lines.append("")

        # ── 5. 학습 노트 ──
        notes = regime_out.get("interpretation", {}).get("learning_notes", [])
        if notes:
            lines.append(f"<b>📚 학습</b>")
            for n in notes[:3]:  # D87: 2 → 3개로 확장
                term = n.get("term", "")
                explain = n.get("explain", "")
                if term and explain:
                    lines.append(f"• <b>{term}</b>: {explain[:120]}")

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
        macro_interp: str = "",
        m6_out: dict | None = None,
        improvement_report: dict | None = None,
    ) -> str:
        """저널 본문 빌드.

        D87 원칙: 텔레그램 = 시트 동일화. 풀 콘텐츠 노출 (시트는 길이 제한 X).
        텔레그램과 동일한 콘텐츠 + 추가 디테일 (RRG 분면 전환, m6 종목별 상세, quiet 뉴스 풀버전).
        """
        SEP = "═" * 60
        m6_out = m6_out or {}
        improvement_report = improvement_report or {}

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

        if briefing_mode == "monthly" and improvement_report.get("detailed_lines"):
            lines.extend(improvement_report.get("detailed_lines", []))
            lines.append("")

        # ▣ 매크로 환경 (D87: macro_interp 풀버전 포함)
        lines.extend(self._build_journal_regime(regime_out, macro_interp=macro_interp))

        # ■ 정찰 (SCOUT) (D87: m6_out 통합)
        lines.extend(self._build_journal_scout(scout_out, candidates_with_comment, m6_out=m6_out))

        # ■ 감시 (GUARD) (D87: quiet 뉴스 풀버전)
        lines.extend(self._build_journal_guard(guard_out))

        # ■ 메타
        lines.extend(self._build_journal_meta(scout_out, guard_out, regime_out))

        return "\n".join(lines)

    # ─────────────────────────────────────────────
    # 저널 섹션 빌더 — 매크로 환경
    # ─────────────────────────────────────────────
    def _build_journal_regime(self, regime_out: dict, macro_interp: str = "") -> list:
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

            theme_intel = rrg.get("theme_intelligence", {}) or {}
            theme_groups = theme_intel.get("groups", []) or []
            theme_counts = theme_intel.get("counts", {}) or {}
            if theme_groups:
                lines.append("")
                lines.append("  • 테마 흐름판:")
                lines.append(f"      기준: 강함=같은 테마 ETF 2개 이상 주도/개선, 관찰=1개만 먼저 개선, 보류=대부분 약화·부진")
                lines.append(f"      분포: {_theme_counts_text(theme_counts)}")
                for theme in theme_groups[:7]:
                    etf_text = _format_theme_etfs(theme.get("etfs", []), 6)
                    lines.append(
                        f"      {theme.get('label')} [{theme.get('judgment')}]: "
                        f"{theme.get('reason')}"
                    )
                    if etf_text:
                        lines.append(f"        ETF: {etf_text}")

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

        # ▣ 매크로 해석 (D87 신규: 풀버전, 시트는 길이 제한 X)
        if macro_interp:
            lines.append("")
            lines.append("▣ 매크로 해석 (오늘 좌측거래 관점)")
            for ln in macro_interp.split("\n"):
                if ln.strip():
                    lines.append(f"  {ln}")

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
    def _build_journal_scout(self, scout_out: dict, candidates: list, m6_out: dict | None = None) -> list:
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
        radar_summary = scout_out.get("radar_summary", {}) or {}
        radar_count = int(radar_summary.get("radar_pool_count", 0) or 0)
        theme_count = int(radar_summary.get("theme_count", 0) or 0)
        top_signals = radar_summary.get("top_signals", []) or []
        top_quality_flags = radar_summary.get("top_quality_flags", []) or []
        top_factor_positives = radar_summary.get("top_factor_positives", []) or []
        top_factor_negatives = radar_summary.get("top_factor_negatives", []) or []
        coverage_warnings = radar_summary.get("coverage_warnings", []) or []
        source_counts = radar_summary.get("source_counts", {}) or {}
        filter_audit = radar_summary.get("filter_audit", {}) or {}
        no_candidate_reason = radar_summary.get("no_candidate_reason", "")
        watchlist = scout_out.get("watchlist_candidates", []) or []
        passed = len(candidates)

        lines.append(f"  • 스캔 종목   : {scanned:,}개 (재선정대기 제외 {cooldown}개)")
        lines.append(f"  • 시세 평가   : {ohlcv_eval:,}개")
        lines.append(f"  • 관찰풀     : {radar_count:,}개 (테마 가치사슬 {theme_count:,}개)")
        lines.append(f"  • 엄선 후보   : {passed}개")
        if by_country:
            parts = [f"{_COUNTRY_KO.get(k, k)} {v}" for k, v in by_country.items()]
            lines.append(f"  • 국가별     : {' / '.join(parts)}")
        if source_counts:
            parts = []
            for source, count in sorted(source_counts.items(), key=lambda item: -int(item[1] or 0))[:5]:
                label = _SOURCE_KO.get(source, source)
                parts.append(f"{label} {count}")
            if parts:
                lines.append(f"  • 데이터 경로 : {' / '.join(parts)}")
        if filter_audit:
            hard = filter_audit.get("hard_filter", {}) or {}
            cost = filter_audit.get("cost_control", {}) or {}
            factor_audit = filter_audit.get("factor_audit", {}) or {}
            scope = filter_audit.get("evaluation_scope", {}) or {}
            signal = filter_audit.get("signal_audit", {}) or {}
            radar = filter_audit.get("radar_audit", {}) or {}
            catalyst = filter_audit.get("catalyst_audit", {}) or {}
            top3 = filter_audit.get("top3_selection_audit", {}) or {}
            lines.append(
                "  • 필터 감사 : "
                f"수집 {int(hard.get('universe', scanned) or 0):,}"
                f" → 대기제외 후 {int(hard.get('after_cooldown', 0) or 0):,}"
                f" → 시세평가 {int(scope.get('ohlcv_selected', ohlcv_eval) or 0):,}"
                f" → 신호발생 {int(signal.get('with_signal', 0) or 0):,}"
                f" → 관찰후보 {int(radar.get('radar_eligible_before_cap', radar_count) or 0):,}"
                f" → 엄선 {int(radar.get('brief_picks', passed) or 0):,}"
            )
            skipped = int(scope.get("ohlcv_not_selected", 0) or 0)
            missing = int(scope.get("ohlcv_missing", 0) or 0)
            capped = int(radar.get("radar_cap_dropped", 0) or 0)
            if skipped or missing or capped:
                parts = []
                if skipped:
                    parts.append(f"시세 미평가 {skipped:,}")
                if missing:
                    parts.append(f"시세누락 {missing:,}")
                if capped:
                    parts.append(f"관찰풀 상한 제외 {capped:,}")
                lines.append(f"  • 감사 메모   : {' / '.join(parts)}")
            insider_skipped = int(cost.get("insider_skipped_cost_limit", 0) or 0)
            if insider_skipped:
                lines.append(
                    f"  • 비용 제어   : 내부자/펀더멘털 사전조회 {insider_skipped:,}개 생략"
                    f" (미국 상위 {int(cost.get('insider_eval_top_us', 0) or 0):,}개만)"
                )
            gate = radar.get("brief_quality_gate", {}) or {}
            if gate.get("enabled"):
                lines.append(
                    "  • 최종 게이트 : RONIN Entry v2 / 촉매 확인 / 신호 "
                    f"{int(gate.get('allow_signal_count_at_least', 4) or 4)}개 이상 중 하나 필요"
                )
            if top3 and top3.get("enabled"):
                tier_counts = top3.get("tier_counts", {}) or {}
                tier_text = " / ".join(
                    f"{tier} {int(tier_counts.get(tier, 0) or 0)}"
                    for tier in ["A", "B", "C", "D", "REVIEW"]
                    if int(tier_counts.get(tier, 0) or 0)
                )
                lane_text = ", ".join(x for x in (top3.get("selected_lanes", []) or []) if x)
                lines.append(
                    f"  • Top3 선발 : {int(top3.get('selected', 0) or 0)}개"
                    + (f" ({tier_text})" if tier_text else "")
                    + (f" · 레인 {lane_text}" if lane_text else "")
                )
                if int(top3.get("review_pool_risk_catalyst", 0) or 0):
                    lines.append(
                        f"  • 리뷰풀     : RISK_CATALYST {int(top3.get('review_pool_risk_catalyst', 0) or 0):,}개"
                        " Top3 제외"
                    )
                llm_review = top3.get("llm_review", {}) or {}
                if llm_review.get("enabled"):
                    status = llm_review.get("status", "")
                    override = "override" if llm_review.get("llm_override") else "keep"
                    final_top3 = ", ".join(llm_review.get("final_top3", []) or [])
                    lines.append(
                        f"  • LLM 재심사 : {status} · {override}"
                        + (f" · 최종 {final_top3}" if final_top3 else "")
                    )
            shadow_hits = signal.get("shadow_hit_counts", {}) or {}
            if shadow_hits:
                parts = []
                for key, count in sorted(shadow_hits.items(), key=lambda item: -int(item[1] or 0))[:3]:
                    parts.append(f"{_SIGNAL_KO.get(str(key), str(key))} {int(count or 0):,}")
                if parts:
                    lines.append(f"  • Shadow 검증 : {' / '.join(parts)} (점수/후보선정 미반영)")
            if catalyst and catalyst.get("enabled"):
                catalyst_mode = (
                    "shadow"
                    if float(catalyst.get("score_boost", 0) or 0) == 0 and float(catalyst.get("risk_penalty", 0) or 0) == 0
                    else "score"
                )
                lines.append(
                    f"  • 촉매 확인   : 상위 {int(catalyst.get('evaluated', 0) or 0):,}개 평가"
                    f" / 확인 {int(catalyst.get('found', 0) or 0):,}"
                    f" / 리스크 {int(catalyst.get('risk', 0) or 0):,}"
                    f" / 없음 {int(catalyst.get('none', 0) or 0):,}"
                    f" / 미연결 {int(catalyst.get('non_us', 0) or 0) + int(catalyst.get('no_key', 0) or 0):,}"
                    f" / {catalyst_mode}"
                )
                if int(catalyst.get("top3_excluded_risk", 0) or 0):
                    lines.append(
                        f"  • 촉매 리뷰풀 : 위험촉매 {int(catalyst.get('top3_excluded_risk', 0) or 0):,}개 Top3 제외"
                        " (감사관 탈락 아님)"
                    )
                if catalyst.get("llm_enabled"):
                    lines.append(
                        f"  • 촉매 LLM    : JSON 분류 {int(catalyst.get('llm_evaluated', 0) or 0):,}개"
                        f" / 성공 {int(catalyst.get('llm_ok', 0) or 0):,}"
                    )
            if factor_audit and factor_audit.get("enabled"):
                factor_mode = "shadow" if float(factor_audit.get("score_weight", 0) or 0) == 0 else "score"
                lines.append(
                    f"  • 因子 보정   : 유동성/추격위험/변동성/데이터 품질"
                    f" ({factor_mode}, 상한 ±{float(factor_audit.get('score_cap', 0) or 0):.1f})"
                )
        if top_signals:
            parts = []
            for item in top_signals[:3]:
                sig_name = item[0] if isinstance(item, (list, tuple)) and item else ""
                count = item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else 0
                parts.append(f"{_SIGNAL_KO.get(sig_name, sig_name)} {count}")
            if parts:
                lines.append(f"  • 자주 나온 신호: {' / '.join(parts)}")
        if top_quality_flags:
            parts = []
            for item in top_quality_flags[:3]:
                flag = item[0] if isinstance(item, (list, tuple)) and item else ""
                count = item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else 0
                parts.append(f"{_QUALITY_FLAG_KO.get(flag, flag)} {count}")
            if parts:
                lines.append(f"  • 관찰 태그   : {' / '.join(parts)}")
        if top_factor_positives or top_factor_negatives:
            pos_parts = []
            neg_parts = []
            for item in top_factor_positives[:2]:
                key = item[0] if isinstance(item, (list, tuple)) and item else ""
                count = item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else 0
                pos_parts.append(f"{_FACTOR_KO.get(key, key)} {count}")
            for item in top_factor_negatives[:2]:
                key = item[0] if isinstance(item, (list, tuple)) and item else ""
                count = item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else 0
                neg_parts.append(f"{_FACTOR_KO.get(key, key)} {count}")
            factor_text = []
            if pos_parts:
                factor_text.append("가산 " + " / ".join(pos_parts))
            if neg_parts:
                factor_text.append("감점 " + " / ".join(neg_parts))
            if factor_text:
                lines.append(f"  • 因子 요약   : {' | '.join(factor_text)}")
        if coverage_warnings:
            warn_parts = []
            for w in coverage_warnings[:4]:
                country = _COUNTRY_KO.get(w.get("country", ""), w.get("country", ""))
                warn_parts.append(f"{country} {w.get('count', 0)}/{w.get('threshold', 0)}")
            lines.append(f"  • 커버리지 경고: {' / '.join(warn_parts)}")
        lines.append("")

        if candidates:
            for idx, c in enumerate(candidates, 1):
                country_ko = _COUNTRY_KO.get(c.get("country", ""), c.get("country", ""))
                cap = _format_market_cap(c.get("market_cap", 0))
                name = (c.get("name", "") or "")[:40]
                lines.append(f"▷ 후보 {idx}: {c['ticker']} ({name}) — {country_ko}")
                lines.append(f"    섹터    : {c.get('sector', '미분류')} | 시총 : {cap}")
                lines.append(f"    레이더 점수: {c.get('score', 0)} | 신호 {c.get('signal_count', len(c.get('signals', {}) or {}))}개")
                selection = c.get("top3_selection", {}) or {}
                if selection:
                    sel_bits = [
                        f"Tier {selection.get('tier', '')}",
                        f"{selection.get('primary_lane', '')}:{selection.get('primary_lane_status', '')}",
                        f"촉매 {selection.get('catalyst_freshness_rank', 0)}",
                        f"보조 {selection.get('support_count', 0)}",
                        f"기회 {selection.get('opportunity_score', 0)}",
                    ]
                    lines.append(f"    선발 근거 : {' · '.join(str(x) for x in sel_bits if x)}")
                track_d = c.get("track_d", {}) or {}
                if track_d.get("is_theme_beneficiary"):
                    matches = track_d.get("matches", []) or []
                    match_text = []
                    for m in matches[:3]:
                        if isinstance(m, dict):
                            theme_label = m.get("theme_label") or m.get("theme_key") or "테마"
                            role = m.get("role", "")
                            priority = m.get("priority", "")
                            detail = " / ".join(str(x) for x in [role, priority] if x)
                            match_text.append(f"{theme_label}" + (f" ({detail})" if detail else ""))
                        else:
                            match_text.append(str(m))
                    if match_text:
                        lines.append(f"    테마 연결 : {', '.join(match_text)}")
                theme_industry = c.get("theme_industry", {}) or {}
                if theme_industry:
                    ti_status = str(theme_industry.get("status", "") or "")
                    ti_label = {
                        "STRONG_SUPPORT": "강한 지원",
                        "SUPPORT": "지원",
                        "THEME_NEUTRAL": "중립",
                        "SECTOR_NEUTRAL": "중립",
                        "THEME_UNSUPPORTED": "테마 비지원",
                        "SECTOR_UNSUPPORTED": "섹터 비지원",
                        "NO_MAPPING": "매핑 없음",
                    }.get(ti_status, ti_status)
                    sector_ctx = theme_industry.get("sector", {}) or {}
                    sector_bits = []
                    if sector_ctx.get("etf"):
                        sector_bits.append(str(sector_ctx.get("etf")))
                    if sector_ctx.get("quadrant"):
                        sector_bits.append(str(sector_ctx.get("quadrant")))
                    peer_count = int((theme_industry.get("peer_confirmation", {}) or {}).get("active_peer_count", 0) or 0)
                    peer_text = f" · 동료 {peer_count}개" if peer_count else ""
                    sector_text = f" ({' / '.join(sector_bits)})" if sector_bits else ""
                    lines.append(f"    테마/산업 : {ti_label}{sector_text}{peer_text}")
                quality_auditor = c.get("quality_auditor", {}) or {}
                if quality_auditor:
                    qa_status = str(quality_auditor.get("status", "") or "")
                    qa_label = {
                        "STRONG_QUALITY": "품질 강함",
                        "QUALITY_SUPPORT": "품질 우호",
                        "NEUTRAL": "중립",
                        "DATA_LIGHT": "데이터 부족",
                        "NEEDS_REVIEW": "검토 필요",
                        "not_checked": "미확인",
                    }.get(qa_status, qa_status)
                    qa_source = str(quality_auditor.get("source", "") or "").upper()
                    qa_delta = int(quality_auditor.get("confidence_delta", 0) or 0)
                    qa_bits = [qa_label]
                    if qa_source:
                        qa_bits.append(qa_source)
                    qa_bits.append(f"신뢰도 {qa_delta:+d}")
                    lines.append(f"    품질 감사 : {' · '.join(qa_bits)}")
                try:
                    from src.modules.m1_5_buyquestions import summarize_data_coverage
                    coverage_text = summarize_data_coverage(c)
                    if coverage_text:
                        lines.append(f"    데이터 상태: {coverage_text}")
                except Exception as e:
                    self.log.debug("[digest] 데이터 커버리지 포맷 실패: %s", e)
                factor = c.get("factor_context", {}) or {}
                if factor:
                    positives = [_FACTOR_KO.get(k, k) for k in (factor.get("positives", []) or [])[:2]]
                    negatives = [_FACTOR_KO.get(k, k) for k in (factor.get("negatives", []) or [])[:2]]
                    factor_bits = []
                    if positives:
                        factor_bits.append("가산 " + ", ".join(positives))
                    if negatives:
                        factor_bits.append("감점 " + ", ".join(negatives))
                    if factor_bits or factor.get("score"):
                        lines.append(f"    因子 점수 : {float(factor.get('score', 0) or 0):+.1f}" + (f" ({' / '.join(factor_bits)})" if factor_bits else ""))
                catalyst = c.get("catalyst_context", {}) or {}
                if catalyst.get("score"):
                    lines.append(f"    촉매 점수 : {catalyst.get('score'):+.1f}")
                if catalyst.get("classification"):
                    class_label = {
                        "POSITIVE_REVALUATION": "긍정 재평가",
                        "RISK_CATALYST": "위험 촉매",
                        "NOISE": "노이즈",
                        "NO_DATA": "데이터 없음",
                    }.get(str(catalyst.get("classification", "")), str(catalyst.get("classification", "")))
                    fresh = (catalyst.get("freshness") or {}).get("status", "")
                    reaction = (catalyst.get("price_volume_reaction") or {}).get("status", "")
                    bits = [class_label]
                    if fresh:
                        bits.append(str(fresh))
                    if reaction:
                        bits.append(str(reaction))
                    if catalyst.get("llm_status"):
                        bits.append(f"LLM {catalyst.get('llm_status')}")
                    lines.append(f"    촉매 감사 : {' · '.join(bits)}")
                if catalyst.get("status") == "found" and catalyst.get("news"):
                    lines.append("    촉매 확인 :")
                    for n in catalyst.get("news", [])[:2]:
                        headline = str(n.get("headline", "") or "").strip()
                        source = str(n.get("source", "") or "").strip()
                        if headline:
                            source_part = f" ({source})" if source else ""
                            lines.append(f"      • {headline}{source_part}")
                elif catalyst.get("status") == "risk" and catalyst.get("risk_hits"):
                    lines.append("    촉매 리스크:")
                    for hit in catalyst.get("risk_hits", [])[:2]:
                        headline = str(hit.get("headline", "") or "").strip()
                        if headline:
                            lines.append(f"      • {headline}")
                flags = c.get("quality_flags", []) or []
                if flags:
                    labels = [_QUALITY_FLAG_KO.get(flag, flag) for flag in flags[:3]]
                    lines.append(f"    관찰 태그 : {', '.join(labels)}")

                sigs = c.get("signals", {}) or {}
                if sigs:
                    lines.append(f"    사전감지 신호 ({len(sigs)}개):")
                    for sig_name, sig_info in sigs.items():
                        label = _format_signal_ko(sig_name, sig_info)
                        lines.append(f"      • {label}")

                if c.get("comment"):
                    lines.append(f"    해석    : {c['comment']}")

                # M1.5 买入三问 풀 분석 (Z3-4)
                bq = c.get("buy_questions") or {}
                if bq:
                    star = bq.get("star_rating", "★")
                    summary = bq.get("summary", "")
                    lines.append(f"    买入三问 ({star} {summary}):")
                    if bq.get("industry"):
                        lines.append(f"      📂 산업    : {bq['industry']}")
                    if bq.get("thesis"):
                        lines.append(f"      💡 thesis  : {bq['thesis']}")
                    if _has_real_catalyst(bq.get("catalyst", "")):
                        lines.append(f"      🎯 catalyst: {bq['catalyst']}")
                    lines.append(f"      Q1 왜 오르나: {bq.get('q1_why', '')}")
                    lines.append(f"      Q2 누가 사나: {bq.get('q2_who', '')}")
                    lines.append(f"      Q3 공간    : {bq.get('q3_space', '')}")
                    risks = bq.get("risk_flags") or []
                    if risks:
                        risk_text = " / ".join(str(r) for r in risks[:3])
                        lines.append(f"      ⚠️ 리스크 : {risk_text}")
                lines.append("")
        else:
            reason = no_candidate_reason or "최종 보고 기준 미달"
            lines.append(f"  (오늘 엄선 후보 없음 — {reason})")
            if radar_count > 0:
                lines.append("  관찰풀은 쌓였으니 억지로 종목을 찾기보다 다음 신호 확인을 기다리는 구간입니다.")
            if watchlist:
                lines.append("")
                lines.append("▷ 대기 후보 (WATCHLIST)")
                for idx, w in enumerate(watchlist[:5], 1):
                    sigs = w.get("signal_keys") or []
                    sig_text = ", ".join(str(x) for x in sigs[:4]) if isinstance(sigs, list) else str(sigs)
                    lines.append(
                        f"  {idx}. {w.get('ticker')} [{w.get('selection_tier')}] "
                        f"{w.get('selection_lane')}:{w.get('selection_lane_status')} "
                        f"score={w.get('score')} opp={w.get('selection_opportunity_score')}"
                    )
                    if w.get("watch_reason"):
                        lines.append(f"     이유: {w.get('watch_reason')}")
                    if sig_text:
                        lines.append(f"     신호: {sig_text}")
            lines.append("")

        # ── M6 SCOUT 추적 (D86 신규: 시트는 풀버전, 종목별 상세) ──
        m6_out = m6_out or {}
        m6_summary = m6_out.get("summary_text", "")
        m6_detailed = m6_out.get("detailed_lines", []) or []
        performance_summary = ((m6_out.get("performance") or {}).get("summary_text", "") or "")
        performance_paths = ((m6_out.get("performance") or {}).get("paths", {}) or {})
        m6_count = m6_out.get("track_count", 0)
        if m6_summary or m6_detailed or performance_summary:
            lines.append("─" * 60)
            lines.append(f"▷ SCOUT 후보 추적 (M6, {m6_count}개)")
            if m6_summary:
                lines.append(f"  요약: {m6_summary}")
            if performance_summary:
                lines.append(f"  성과표: {performance_summary}")
            if performance_paths.get("markdown"):
                lines.append(f"  리포트: {performance_paths.get('markdown')}")
            if m6_detailed:
                lines.append("")
                lines.extend(m6_detailed)
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

        # ── Quiet 종목 풀 노출 (D87 신규: 변동 X여도 뉴스/가격 정보 노출) ──
        quiet_full = guard_out.get("quiet_full", []) or []
        if quiet_full:
            lines.append(f"▷ 변동 없음 ({len(quiet_full)}종목)")
            lines.append("")
            for q in quiet_full:
                ticker = q.get("ticker", "?")
                price = q.get("price", {}) or {}
                close = price.get("close", "?")
                d_pct = price.get("daily_pct", 0) or 0
                w_pct = price.get("weekly_pct", 0) or 0
                try:
                    lines.append(f"  • {ticker}  ${close}  (일 {d_pct:+.1f}%, 주 {w_pct:+.1f}%)")
                except Exception:
                    lines.append(f"  • {ticker}  ${close}  (일 {d_pct}, 주 {w_pct})")

                news_list = q.get("news", []) or []
                if news_list:
                    for n in news_list[:3]:
                        ko = (n.get("ko_summary") or "").strip()
                        if ko:
                            lines.append(f"      📰 {ko}")
                        else:
                            head = (n.get("headline", "") or "")[:100]
                            if head:
                                lines.append(f"      📰 {head}")
            lines.append("")
        elif quiet:
            # quiet_full 없으면 옛 로직 (이름만)
            lines.append(f"▷ 변동 없음 ({len(quiet)}종목): {', '.join(quiet)}")
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
