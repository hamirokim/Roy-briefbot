"""
M1.5 买入三问 (Buy Three Questions) — Z3-4 LLM 통합 버전 (D74/D78/D80)
========================================================================

목적: SCOUT 후보 1개당 매수 의사결정 풀 분석 (LLM 동적).

기존 정적 룰 → Z3-4에서 LLM 통합 재작성.
재사용: BaseAgent.call_llm() (src/agents/base.py).
환경변수: GPT_API_KEY (기존), GPT_MODEL (default gpt-5.4-mini).
SDK 추가 없음. requests + JSON 모드로 호출.

출력 (candidate dict 추가):
  {
    "buy_questions": {
      "industry": "산업/테마 분류",
      "thesis": "왜 매집되고 있나 (1-2 문장)",
      "catalyst": "최근 6개월 가능 catalyst",
      "q1_why": "왜 오를까 (PE/EPS Growth)",
      "q2_who": "누가 사는가 (insider/inst)",
      "q3_space": "더 오를 여지 (PE/RSI/52w)",
      "risk_flags": ["리스크1", "리스크2"],
      "star_rating": "★ | ★★ | ★★★",
      "summary": "한 줄 요약 (15자 이내)",
    }
  }

비용 (gpt-5.4-mini 기준):
  - 신호당 input ~600 + output ~600 tokens = $0.0005
  - 연간 Track A 6-8건 = $0.005 (사실상 무료)

박제: D74 (1년 견고), D78 (pctChange 운영 자산), D80 (OpenAI GPT 채택).
"""

from __future__ import annotations
import json
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# ── LLM 설정 (BaseAgent와 일치) ──
GPT_API_KEY = os.environ.get("GPT_API_KEY", "")
GPT_MODEL = os.environ.get("GPT_MODEL", "gpt-5.4-mini")
GPT_TIMEOUT = int(os.environ.get("GPT_TIMEOUT", "60"))
GPT_TEMPERATURE = float(os.environ.get("GPT_TEMPERATURE", "0.3"))


# ── 시스템 프롬프트 ──
SYSTEM_PROMPT = """당신은 미국 주식 매집 신호 분석 전문가입니다.
입력된 종목의 매집 가능성을 검증하고 한국어 JSON으로 답변합니다.

규칙:
1. 사실 기반 답변. 모르면 "정보 부족" 명시. 추측 금지
2. 입력된 PE/EPS Growth/RSI/insider/기관 fact 활용
3. 최근 6개월 가능 catalyst만 (먼 미래 예측 X)
4. 각 필드 1-2 문장 압축
5. 한국어 답변

답변은 반드시 valid JSON. 스키마:

{
  "industry": "산업/테마 분류 (예: AI 반도체)",
  "thesis": "1-2 문장. 왜 지금 매집되고 있는가",
  "catalyst": "최근 6개월 가능 catalyst 1-2개. 모르면 '정보 부족'",
  "q1_why": "왜 오를까 - PE/EPS Growth 기반",
  "q2_who": "누가 사는가 - insider/기관 매집 기반",
  "q3_space": "더 오를 여지 - PE/RSI/52w 저점 기반",
  "risk_flags": ["주요 리스크 1", "주요 리스크 2"],
  "star_rating": "★ 또는 ★★ 또는 ★★★",
  "summary": "한 줄 요약 (15자 이내)"
}

★★★ = 매수 적극 검토 (모든 fact 강력 매집)
★★ = 매수 검토 (대부분 fact 매집)
★ = 관찰 (일부 fact 매집, 일부 약함)
"""


# ─────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────

def _safe_float(val) -> Optional[float]:
    """안전 float 변환."""
    if val is None or val == "" or val == "-":
        return None
    try:
        if isinstance(val, str):
            val = val.replace("%", "").replace(",", "").strip()
        return float(val)
    except (ValueError, TypeError):
        return None


def _build_user_prompt(candidate: dict, fundamental: dict, today: str) -> str:
    """LLM에 전달할 fact 정리. 없는 fact는 생략 (hallucination 차단)."""
    ticker = candidate.get("ticker", "?")
    sector = candidate.get("sector", "")
    country = candidate.get("country", "")
    score = candidate.get("score", 0)

    facts = [
        f"종목: {ticker}",
        f"신호일: {today}",
        f"매집 신호 통과: {score}/5 (Track A)",
    ]
    if sector:
        facts.append(f"섹터: {sector}")
    if country:
        facts.append(f"국가: {country}")

    # 통과한 사전 감지 신호 (한글 라벨)
    signals = candidate.get("signals", {}) or {}
    if signals:
        labels = []
        for sig_key, sig_info in signals.items():
            ko = sig_info.get("label_ko") or sig_key
            labels.append(ko)
        if labels:
            facts.append(f"통과 신호: {', '.join(labels)}")

    # Track D (정적 큐레이션 매핑)
    track_d = candidate.get("track_d", {})
    if track_d.get("is_theme_beneficiary"):
        matches = track_d.get("matches", [])
        if matches:
            facts.append(f"테마 매핑: {', '.join(str(m) for m in matches[:3])}")

    # Fundamental fact (Finviz)
    pe = _safe_float(fundamental.get("pe"))
    fwd_pe = _safe_float(fundamental.get("forward_pe"))
    eps_g = _safe_float(fundamental.get("eps_growth_next_y"))
    peg = _safe_float(fundamental.get("peg"))
    rsi = _safe_float(fundamental.get("rsi14"))
    insider_trans = _safe_float(fundamental.get("insider_trans"))
    inst_trans = _safe_float(fundamental.get("inst_trans"))

    if pe is not None and 0 < pe < 200:
        facts.append(f"PE: {pe:.1f}")
    if fwd_pe is not None and 0 < fwd_pe < 200:
        facts.append(f"Forward PE: {fwd_pe:.1f}")
    if eps_g is not None:
        facts.append(f"EPS Growth (next Y): {eps_g:.1f}%")
    if peg is not None and 0 < peg < 10:
        facts.append(f"PEG: {peg:.2f}")
    if rsi is not None:
        facts.append(f"RSI(14): {rsi:.1f}")
    if insider_trans is not None:
        facts.append(f"Insider Trans: {insider_trans:+.1f}%")
    if inst_trans is not None:
        facts.append(f"Institutional Trans: {inst_trans:+.1f}%")

    # Insider Buying 신호 통과 시 횟수
    if "insider_buying" in signals:
        count = signals["insider_buying"].get("count", 0)
        if count:
            facts.append(f"Insider 1주 내 매수: {count}건")

    facts_text = "\n".join(facts)
    return f"{facts_text}\n\n매집 가능성 분석 → 위 스키마 JSON 답변"


def _call_gpt_json(system_prompt: str, user_message: str) -> Optional[str]:
    """OpenAI JSON mode 호출. 실패 시 None."""
    if not GPT_API_KEY:
        logger.error("[M1.5] GPT_API_KEY 없음")
        return None

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GPT_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GPT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_completion_tokens": 800,
        "temperature": GPT_TEMPERATURE,
        "response_format": {"type": "json_object"},
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=GPT_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            return None
        content = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        logger.info(
            "[M1.5] LLM 호출: in=%d out=%d total=%d",
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            usage.get("total_tokens", 0),
        )
        return content.strip()
    except requests.exceptions.Timeout:
        logger.error("[M1.5] LLM 타임아웃")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error("[M1.5] LLM HTTP 에러: %s", e)
        return None
    except Exception as e:
        logger.error("[M1.5] LLM 실패: %s", e)
        return None


# ─────────────────────────────────────────────
# Fallback (LLM 실패 시 정적 룰 답변)
# ─────────────────────────────────────────────

def _fallback_buy_questions(candidate: dict, fundamental: dict) -> dict:
    """LLM 실패 시 정적 룰 답변. 풀 스키마 반환."""
    signals = candidate.get("signals", {}) or {}
    sig_summary = ", ".join(
        s.get("label_ko") or k for k, s in signals.items()
    ) if signals else "신호 정보 부족"

    pe = _safe_float(fundamental.get("pe"))
    eps_g = _safe_float(fundamental.get("eps_growth_next_y"))
    rsi = _safe_float(fundamental.get("rsi14"))
    insider = _safe_float(fundamental.get("insider_trans"))

    q1 = f"신호 {sig_summary}" + (f", PE {pe:.0f}" if pe else "") + (f", EPS YoY {eps_g:+.0f}%" if eps_g else "")
    q2 = ("Insider " + (f"{insider:+.1f}%" if insider else "정보 부족"))
    q3 = ("RSI " + (f"{rsi:.0f}" if rsi else "?")) + (", PE 저평가" if pe and pe < 15 else "")

    score = candidate.get("score", 0)
    star = "★★★" if score >= 4 else "★★" if score >= 3 else "★"

    return {
        "industry": candidate.get("sector", "정보 부족"),
        "thesis": "LLM 미사용 — 신호 통과 기반 후보",
        "catalyst": "정보 부족 (LLM 실패)",
        "q1_why": q1,
        "q2_who": q2,
        "q3_space": q3,
        "risk_flags": ["LLM 실패", "정적 룰 답변만"],
        "star_rating": star,
        "summary": f"신호 {score}/5",
        "_llm_used": False,
    }


# ─────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────

def answer_buy_questions(
    candidate: dict,
    fundamental: Optional[dict] = None,
    today: str = "",
) -> dict:
    """SCOUT 후보 1개에 买入三问 LLM 답변.

    Args:
        candidate: SCOUT 후보 dict (ticker, signals, sector, score, track_d 등)
        fundamental: Finviz 펀더멘털 (선택)
        today: 신호일 ('YYYY-MM-DD')

    Returns:
        candidate dict (in-place 수정) + buy_questions 필드 추가
    """
    fund = fundamental or {}
    ticker = candidate.get("ticker", "?")

    user_prompt = _build_user_prompt(candidate, fund, today or "today")
    raw = _call_gpt_json(SYSTEM_PROMPT, user_prompt)

    if not raw:
        logger.warning("[M1.5] %s: LLM 실패 → fallback 사용", ticker)
        candidate["buy_questions"] = _fallback_buy_questions(candidate, fund)
        return candidate

    # JSON 파싱
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning("[M1.5] %s: JSON 파싱 실패 (%s) → fallback", ticker, e)
        candidate["buy_questions"] = _fallback_buy_questions(candidate, fund)
        return candidate

    # 스키마 키 점검 (누락 시 fallback 키로 채움)
    required_keys = ["industry", "thesis", "catalyst", "q1_why", "q2_who",
                     "q3_space", "risk_flags", "star_rating", "summary"]
    for key in required_keys:
        if key not in result:
            result[key] = "정보 부족"
    if not isinstance(result.get("risk_flags"), list):
        result["risk_flags"] = [str(result.get("risk_flags", "정보 부족"))]

    result["_llm_used"] = True
    candidate["buy_questions"] = result
    return candidate


def run_m1_5_buy_questions(candidates: list[dict], today: str = "") -> list[dict]:
    """SCOUT 후보 리스트 전체에 买入三问 LLM 적용.

    Args:
        candidates: SCOUT.candidates 리스트
        today: 신호일

    Returns:
        candidates with buy_questions field added (in-place)
    """
    if not candidates:
        return candidates

    logger.info("[M1.5] 买入三问 LLM 시작: %d개 후보", len(candidates))

    # Finviz fundamental 일괄 수집 (미국만)
    fund_cache = {}
    try:
        from src.collectors.finviz import fetch_fundamental_data
        for c in candidates:
            ticker = c.get("ticker", "")
            country = c.get("country", "")
            if country == "US" and ticker:
                try:
                    fund_cache[ticker] = fetch_fundamental_data(ticker) or {}
                except Exception as e:
                    logger.debug("[M1.5] Finviz 실패 %s: %s", ticker, e)
                    fund_cache[ticker] = {}
    except ImportError:
        logger.warning("[M1.5] finviz 모듈 import 실패 — fundamental 없이 진행")

    # 후보별 LLM 호출
    n_llm_ok = 0
    for c in candidates:
        ticker = c.get("ticker", "")
        fund = fund_cache.get(ticker, {})
        answer_buy_questions(c, fund, today=today)
        if c.get("buy_questions", {}).get("_llm_used"):
            n_llm_ok += 1

    logger.info("[M1.5] 完了: LLM 성공 %d/%d", n_llm_ok, len(candidates))
    return candidates


def format_buy_questions_text(candidate: dict) -> str:
    """텔레그램 출력용 텍스트 포맷."""
    bq = candidate.get("buy_questions", {})
    if not bq:
        return ""

    ticker = candidate.get("ticker", "?")
    star = bq.get("star_rating", "★")
    summary = bq.get("summary", "")
    industry = bq.get("industry", "정보 부족")
    thesis = bq.get("thesis", "")
    catalyst = bq.get("catalyst", "정보 부족")
    q1 = bq.get("q1_why", "")
    q2 = bq.get("q2_who", "")
    q3 = bq.get("q3_space", "")
    risks = bq.get("risk_flags", [])
    risk_text = " / ".join(str(r) for r in risks) if risks else "명시 X"

    return (
        f"  [{ticker}] {star} {summary}\n"
        f"    📂 {industry}\n"
        f"    💡 {thesis}\n"
        f"    🎯 Catalyst: {catalyst}\n"
        f"    Q1 왜 오르나: {q1}\n"
        f"    Q2 누가 사나: {q2}\n"
        f"    Q3 공간: {q3}\n"
        f"    ⚠️ 리스크: {risk_text}"
    )


def format_buy_questions_telegram(candidate: dict) -> str:
    """텔레그램 4000자 한도 압축 포맷 (digest용)."""
    bq = candidate.get("buy_questions", {})
    if not bq:
        return ""

    star = bq.get("star_rating", "★")
    summary = bq.get("summary", "")
    catalyst = bq.get("catalyst", "")
    q1 = bq.get("q1_why", "")
    q2 = bq.get("q2_who", "")
    q3 = bq.get("q3_space", "")
    risks = bq.get("risk_flags", [])
    risk_text = " / ".join(str(r) for r in risks[:2]) if risks else ""

    lines = [f"  {star} {summary}"]
    if catalyst and catalyst != "정보 부족":
        lines.append(f"  🎯 {catalyst}")
    lines.append(f"  Q1 {q1}")
    lines.append(f"  Q2 {q2}")
    lines.append(f"  Q3 {q3}")
    if risk_text:
        lines.append(f"  ⚠️ {risk_text}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# 단위 테스트 (이 파일 직접 실행 시)
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample = {
        "ticker": "NVDA",
        "country": "US",
        "sector": "Technology",
        "score": 3,
        "signals": {
            "bb_squeeze": {"label_ko": "변동성 압축"},
            "volume_compression": {"ratio": 0.55, "label_ko": "거래량 압축"},
            "rrg_improving": {"label_ko": "활성 섹터 진입"},
        },
        "track_d": {"is_theme_beneficiary": True, "matches": ["AI 반도체"]},
    }
    sample_fund = {
        "pe": 45.2, "forward_pe": 32.0, "eps_growth_next_y": 35.0,
        "rsi14": 58.5, "insider_trans": 2.1,
    }
    result = answer_buy_questions(sample, sample_fund, today="2026-04-29")
    print("\n[FULL TEXT]")
    print(format_buy_questions_text(result))
    print("\n[TELEGRAM]")
    print(format_buy_questions_telegram(result))
    print("\n[RAW JSON]")
    print(json.dumps(result.get("buy_questions"), indent=2, ensure_ascii=False))
