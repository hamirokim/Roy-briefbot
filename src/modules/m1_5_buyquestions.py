"""
M1.5 买入三问 (Buy Three Questions) — Z1 신규 (D55 정합)
========================================================

목적: SCOUT 후보 1개당 매수 의사결정 3 질문 자동 답변.

PPT 北大 65장 분석 결과 (D55) 응용:
  1번. 为什么涨? (왜 오르나 — 논리)
  2번. 谁在买? (누가 사는가 — 자금 흐름)
  3번. 还能涨吗? (더 오를 수 있나 — 공간)

데이터 소스:
  - Finviz: PE, EPS Growth, Insider Trans, 52주 위치
  - 후보 신호 정보: SCOUT 5신호 통과 결과
  - 섹터 평균 (선택): 비교용

출력: 후보별 dict 추가
  {
    "buy_questions": {
      "q1_why": "P/E 22 (섹터 평균 28 ↓), EPS YoY +18% ↑, ...",
      "q2_who": "Insider 3건 매수 ($2.4M), Vol 5일 1.4× ↑",
      "q3_space": "52주 고점 -34% (충분), PE 저평가",
      "summary": "★★★ 매수 검토 가치 큼"
    }
  }
"""

from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)


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


def _format_q1_why(fundamental: dict, signals: dict) -> str:
    """1번: 为什么涨? — 논리/펀더멘털.
    
    체크 항목:
      - PE / Forward PE
      - EPS Growth (next Y)
      - PEG
      - 통과한 SCOUT 신호 (어떤 신호로 후보가 됐나)
    """
    parts = []
    
    pe = _safe_float(fundamental.get("pe"))
    fwd_pe = _safe_float(fundamental.get("forward_pe"))
    eps_g = _safe_float(fundamental.get("eps_growth_next_y"))
    peg = _safe_float(fundamental.get("peg"))
    
    if pe and 0 < pe < 100:
        if fwd_pe and fwd_pe < pe:
            parts.append(f"P/E {pe:.0f}→{fwd_pe:.0f} (이익 성장)")
        else:
            parts.append(f"P/E {pe:.0f}")
    
    if eps_g:
        if eps_g > 20:
            parts.append(f"EPS YoY +{eps_g:.0f}% ★")
        elif eps_g > 0:
            parts.append(f"EPS YoY +{eps_g:.0f}%")
        else:
            parts.append(f"EPS YoY {eps_g:.0f}% ⚠")
    
    if peg and 0 < peg < 1.5:
        parts.append(f"PEG {peg:.1f} (저평가)")
    
    # 통과한 신호 = "왜 후보가 됐나"
    sig_keys = list(signals.keys())
    if sig_keys:
        sig_summary = ", ".join([signals[k].get("label_ko", k) for k in sig_keys[:2]])
        parts.append(f"신호: {sig_summary}")
    
    return " | ".join(parts) if parts else "데이터 부족"


def _format_q2_who(fundamental: dict, signals: dict) -> str:
    """2번: 谁在买? — 자금 흐름.
    
    체크 항목:
      - Insider Trans (% of shares insider trading)
      - Inst Trans (Institutional)
      - Volume Compression / Volume 변화
    """
    parts = []
    
    insider = _safe_float(fundamental.get("insider_trans"))
    inst = _safe_float(fundamental.get("inst_trans"))
    
    if insider:
        if insider > 5:
            parts.append(f"Insider +{insider:.1f}% ★★ (강한 매수)")
        elif insider > 0:
            parts.append(f"Insider +{insider:.1f}%")
        else:
            parts.append(f"Insider {insider:.1f}% ⚠ (매도)")
    
    if inst:
        if inst > 1:
            parts.append(f"Institutional +{inst:.1f}%")
        elif inst < -1:
            parts.append(f"Institutional {inst:.1f}% ⚠")
    
    # Insider Buying 신호 통과 여부
    if "insider_buying" in signals:
        info = signals["insider_buying"]
        count = info.get("count", 0)
        if count:
            parts.append(f"최근 1주 Insider {count}건 매수 ★")
    
    # Volume Compression 통과 = 매집 단계 (조용한 매수)
    if "volume_compression" in signals:
        ratio = signals["volume_compression"].get("ratio", 0)
        if ratio:
            parts.append(f"거래량 압축 ({ratio:.2f}× — 조용한 매집)")
    
    return " | ".join(parts) if parts else "자금 흐름 데이터 부족"


def _format_q3_space(fundamental: dict, signals: dict) -> str:
    """3번: 还能涨吗? — 공간.
    
    체크 항목:
      - 52주 고점 거리
      - PE 저평가 여부
      - RSI (과매수 X)
    """
    parts = []
    
    pe = _safe_float(fundamental.get("pe"))
    fwd_pe = _safe_float(fundamental.get("forward_pe"))
    rsi = _safe_float(fundamental.get("rsi14"))
    
    # PE 저평가 = 공간 큼
    if pe and 0 < pe < 15:
        parts.append(f"P/E {pe:.0f} (저평가, 공간 ★)")
    elif pe and pe > 50:
        parts.append(f"P/E {pe:.0f} (고평가, 공간 ⚠)")
    
    # RSI = 과매수 위험
    if rsi:
        if rsi < 50:
            parts.append(f"RSI {rsi:.0f} (과매수 X, 여유)")
        elif 50 <= rsi <= 70:
            parts.append(f"RSI {rsi:.0f} (정상)")
        elif rsi > 70:
            parts.append(f"RSI {rsi:.0f} ⚠ (과매수)")
    
    # After Low Consolidation = 52주 신저가 후 = 공간 매우 큼
    if "after_low_consolidation" in signals:
        days = signals["after_low_consolidation"].get("days_since_low", 0)
        parts.append(f"52주 저점 후 {days}일 (큰 공간 ★★)")
    
    return " | ".join(parts) if parts else "공간 데이터 부족"


def _build_summary(q1: str, q2: str, q3: str) -> str:
    """3 질문 결과 종합 요약."""
    score = 0
    if "★" in q1:
        score += 1
    if "★" in q2:
        score += 1
    if "★" in q3:
        score += 1
    
    if score >= 3:
        return "★★★ 매수 적극 검토"
    elif score >= 2:
        return "★★ 매수 검토 가치"
    elif score >= 1:
        return "★ 관찰"
    else:
        return "보류 (추가 데이터 필요)"


def answer_buy_questions(candidate: dict, fundamental: Optional[dict] = None) -> dict:
    """SCOUT 후보 1개에 买入三问 자동 답변.
    
    Args:
        candidate: SCOUT 후보 dict (ticker, signals 등)
        fundamental: Finviz 펀더멘털 dict (선택, 없으면 신호 정보만 사용)
    
    Returns:
        candidate dict + buy_questions 추가
    """
    signals = candidate.get("signals", {})
    fund = fundamental or {}
    
    q1 = _format_q1_why(fund, signals)
    q2 = _format_q2_who(fund, signals)
    q3 = _format_q3_space(fund, signals)
    summary = _build_summary(q1, q2, q3)
    
    candidate["buy_questions"] = {
        "q1_why": q1,
        "q2_who": q2,
        "q3_space": q3,
        "summary": summary,
    }
    
    return candidate


def run_m1_5_buy_questions(candidates: list[dict]) -> list[dict]:
    """SCOUT 후보 리스트 전체에 买入三问 적용.
    
    Args:
        candidates: SCOUT.candidates 리스트
    
    Returns:
        candidates with buy_questions field added
    """
    if not candidates:
        return candidates
    
    logger.info("[M1.5] 买入三问 시작: %d개 후보", len(candidates))
    
    # Finviz fundamental 일괄 수집
    try:
        from src.collectors.finviz import fetch_fundamental_data
        for c in candidates:
            ticker = c.get("ticker", "")
            country = c.get("country", "")
            
            # 미국 종목만 Finviz 가능
            fund = None
            if country == "US":
                fund = fetch_fundamental_data(ticker)
            
            answer_buy_questions(c, fund)
    except ImportError:
        logger.warning("[M1.5] finviz 모듈 import 실패 — 신호 정보만으로 답변")
        for c in candidates:
            answer_buy_questions(c, None)
    
    logger.info("[M1.5] 买入三问 완료")
    return candidates


def format_buy_questions_text(candidate: dict) -> str:
    """텔레그램 출력용 텍스트 포맷."""
    bq = candidate.get("buy_questions", {})
    if not bq:
        return ""
    
    ticker = candidate.get("ticker", "?")
    lines = [
        f"  [{ticker}] 买入三问:",
        f"    Q1 왜 오르나: {bq.get('q1_why', '-')}",
        f"    Q2 누가 사나: {bq.get('q2_who', '-')}",
        f"    Q3 공간: {bq.get('q3_space', '-')}",
        f"    종합: {bq.get('summary', '-')}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    # 테스트
    logging.basicConfig(level=logging.INFO)
    sample = {
        "ticker": "TEST",
        "country": "US",
        "signals": {
            "after_low_consolidation": {
                "days_since_low": 12,
                "label_ko": "横盘建仓",
            },
            "insider_buying": {
                "count": 2,
                "label_ko": "메인자금 진입",
            },
        }
    }
    sample_fund = {"pe": 18, "eps_growth_next_y": 22, "rsi14": 48, "insider_trans": 6.2}
    result = answer_buy_questions(sample, sample_fund)
    print(format_buy_questions_text(result))
