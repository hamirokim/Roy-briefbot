"""
src/modules/m1_briefing.py
M1 시장 테마 AI 브리핑 — GPT API 호출 + 종합 판단 생성

사용법:
    from src.modules.m1_briefing import run_m1
    result = run_m1(m2_context, m3_context, m5_context)
    # result = {"briefing": str, "used_llm": bool, "news_count": int}
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from src.collectors.rss import collect_news, format_news_context
from src.utils import now_kst

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────
GPT_API_KEY = os.environ.get("GPT_API_KEY", "")
GPT_MODEL = os.environ.get("GPT_MODEL", "gpt-5.4-mini")
GPT_MAX_TOKENS = int(os.environ.get("GPT_MAX_TOKENS", "2000"))
GPT_TEMPERATURE = float(os.environ.get("GPT_TEMPERATURE", "0.3"))
GPT_TIMEOUT = int(os.environ.get("GPT_TIMEOUT", "60"))

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "prompts"

# ─────────────────────────────────────────────
# 프롬프트 로드
# ─────────────────────────────────────────────
def _load_prompt(filename: str) -> str:
    """config/prompts/ 에서 프롬프트 파일 읽기."""
    path = PROMPTS_DIR / filename
    if not path.exists():
        logger.error("프롬프트 파일 없음: %s", path)
        return ""
    return path.read_text(encoding="utf-8")


def _build_user_message(
    news_context: str,
    news_count: int,
    lookback_hours: int,
    m2_context: str,
    m3_context: str,
    m5_context: str,
    date_str: str,
) -> str:
    """analysis.txt 템플릿에 동적 데이터를 삽입."""
    template = _load_prompt("analysis.txt")
    if not template:
        return (
            f"오늘은 {date_str}입니다.\n\n"
            f"뉴스 ({news_count}건):\n{news_context}\n\n"
            f"M2 섹터 로테이션:\n{m2_context}\n\n"
            f"M3 역발상 후보:\n{m3_context}\n\n"
            f"M5 리스크 데이터:\n{m5_context}\n\n"
            "위 데이터를 종합하여 한국어 아침 시장 브리핑을 작성하세요."
        )

    return template.format(
        date=date_str,
        news_context=news_context,
        news_count=news_count,
        lookback_hours=lookback_hours,
        m2_context=m2_context,
        m3_context=m3_context,
        m5_context=m5_context,
    )


# ─────────────────────────────────────────────
# GPT API 호출
# ─────────────────────────────────────────────
def _call_gpt(system_prompt: str, user_message: str) -> str | None:
    """
    OpenAI Chat Completions API 호출.
    성공 시 응답 텍스트, 실패 시 None.
    """
    if not GPT_API_KEY:
        logger.error("GPT_API_KEY가 설정되지 않음")
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
        "max_completion_tokens": GPT_MAX_TOKENS,
        "temperature": GPT_TEMPERATURE,
    }

    logger.info("GPT 호출: model=%s, input_chars=%d", GPT_MODEL, len(user_message))

    resp = None
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=GPT_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        # 응답 추출
        choices = data.get("choices", [])
        if not choices:
            logger.error("GPT 응답에 choices 없음: %s", json.dumps(data, ensure_ascii=False)[:500])
            return None

        content = choices[0].get("message", {}).get("content", "")

        # 사용량 로깅
        usage = data.get("usage", {})
        logger.info(
            "GPT 완료: input=%d tokens, output=%d tokens, total=%d tokens",
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            usage.get("total_tokens", 0),
        )

        return content.strip()

    except requests.exceptions.Timeout:
        logger.error("GPT 호출 타임아웃 (%ds)", GPT_TIMEOUT)
        return None
    except requests.exceptions.HTTPError as e:
        # 에러 응답 본문을 반드시 로깅
        body = ""
        if resp is not None:
            try:
                body = resp.text[:1000]
            except Exception:
                body = "(응답 본문 읽기 실패)"
        logger.error("GPT HTTP 에러: %s — 응답: %s", e, body)
        return None
    except Exception as e:
        logger.error("GPT 호출 실패: %s", e)
        return None


# ─────────────────────────────────────────────
# 폴백 브리핑 (GPT 실패 시)
# ─────────────────────────────────────────────
def _build_fallback_briefing(
    m2_context: str,
    m3_context: str,
    m5_context: str,
    news_context: str,
    news_count: int,
    date_str: str,
) -> str:
    """GPT 호출 실패 시 M2+M3+M5 원문을 그대로 전송."""
    parts = [
        f"📊 시장 브리핑 — {date_str}",
        "",
        "⚠️ AI 분석 불가 (GPT API 오류) — 원문 데이터 전송",
        "",
        "━━━ 섹터 로테이션 (M2) ━━━",
        m2_context if m2_context else "(데이터 없음)",
        "",
        "━━━ 역발상 후보 (M3) ━━━",
        m3_context if m3_context else "(데이터 없음)",
        "",
        "━━━ 리스크 데이터 (M5) ━━━",
        m5_context if m5_context else "(데이터 없음)",
    ]

    if news_count > 0:
        parts.extend([
            "",
            f"━━━ 뉴스 ({news_count}건) ━━━",
            news_context[:1500],
        ])

    parts.append("\n⚠️ 본 브리핑은 AI 스크리닝이며 매매 시그널이 아닙니다.")

    return "\n".join(parts)


# ─────────────────────────────────────────────
# 메인 실행 함수
# ─────────────────────────────────────────────
def run_m1(
    m2_context: str = "",
    m3_context: str = "",
    m5_context: str = "",
) -> dict:
    """
    M1 시장 테마 AI 브리핑 실행.

    Args:
        m2_context: M2 섹터 로테이션 컨텍스트 텍스트
        m3_context: M3 역발상 후보 컨텍스트 텍스트
        m5_context: M5 리스크 대시보드 컨텍스트 텍스트

    Returns:
        {
            "briefing": str,
            "used_llm": bool,
            "news_count": int,
            "context_text": str,
        }
    """
    date_str = now_kst().strftime("%Y-%m-%d (%a)")

    # 1) 뉴스 수집
    logger.info("=" * 50)
    logger.info("M1 브리핑 시작: %s", date_str)
    logger.info("=" * 50)

    try:
        articles, lookback_hours = collect_news()
    except Exception as e:
        logger.error("뉴스 수집 실패: %s", e)
        articles, lookback_hours = [], 28

    news_count = len(articles)
    news_context = format_news_context(articles)

    logger.info("뉴스 %d건 수집 (lookback %dh)", news_count, lookback_hours)

    # 2) GPT 호출 시도
    system_prompt = _load_prompt("system.txt")
    if not system_prompt:
        logger.warning("시스템 프롬프트 로드 실패 — 폴백 전송")
        briefing = _build_fallback_briefing(
            m2_context, m3_context, m5_context, news_context, news_count, date_str
        )
        return {
            "briefing": briefing,
            "used_llm": False,
            "news_count": news_count,
            "context_text": briefing,
        }

    user_message = _build_user_message(
        news_context=news_context,
        news_count=news_count,
        lookback_hours=lookback_hours,
        m2_context=m2_context,
        m3_context=m3_context,
        m5_context=m5_context,
        date_str=date_str,
    )

    gpt_result = _call_gpt(system_prompt, user_message)

    # 3) 결과 처리
    if gpt_result:
        briefing = gpt_result
        used_llm = True
        logger.info("M1 GPT 브리핑 생성 성공 (%d자)", len(briefing))
    else:
        logger.warning("GPT 실패 → 폴백 브리핑 전송")
        briefing = _build_fallback_briefing(
            m2_context, m3_context, m5_context, news_context, news_count, date_str
        )
        used_llm = False

    return {
        "briefing": briefing,
        "used_llm": used_llm,
        "news_count": news_count,
        "context_text": briefing,
    }


# ─────────────────────────────────────────────
# 단독 테스트
# ─────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

    dummy_m2 = """[섹터 RRG 4분면 — 2026-03-24]
LEADING: XLE(Energy), XLI(Industrials)
IMPROVING: XLV(Healthcare), XLF(Financials)"""

    dummy_m3 = """[역발상 후보 — 2026-03-24]
1. FMC — DD: -74.7% | 반등: +3.2%"""

    dummy_m5 = """[리스크 데이터]
- VIX: 22.4 (NORMAL 레짐 — 보통)
- 이번 주 예정: 🔴 FOMC 금리결정(수)"""

    result = run_m1(m2_context=dummy_m2, m3_context=dummy_m3, m5_context=dummy_m5)
    print(f"\n=== M1 결과 (LLM: {result['used_llm']}, 뉴스: {result['news_count']}건) ===\n")
    print(result["briefing"])
