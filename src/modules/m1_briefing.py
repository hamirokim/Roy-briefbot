"""
M1 시장 테마 AI 브리핑 v4 — Sheets 저장 추가
변경: GPT 브리핑 완료 후 BRIEFING 시트에 자동 저장.
"""

import json
import logging
import os
from pathlib import Path

import requests

from src.collectors.rss import collect_news, format_news_context
from src.utils import now_kst

logger = logging.getLogger(__name__)

GPT_API_KEY = os.environ.get("GPT_API_KEY", "")
GPT_MODEL = os.environ.get("GPT_MODEL", "gpt-5.4-mini")
GPT_MAX_TOKENS = int(os.environ.get("GPT_MAX_TOKENS", "2500"))
GPT_TEMPERATURE = float(os.environ.get("GPT_TEMPERATURE", "0.3"))
GPT_TIMEOUT = int(os.environ.get("GPT_TIMEOUT", "60"))

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "prompts"


def _load_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        logger.error("프롬프트 없음: %s", path)
        return ""
    return path.read_text(encoding="utf-8")


def _build_user_message(
    news_context: str, news_count: int, lookback_hours: int,
    m2_context: str, m3_context: str, m5_context: str,
    m4_context: str, m7_context: str, m6_context: str,
    prev_summary: str, briefing_mode: str, date_str: str,
    analytics_context: str = "",
) -> str:
    template = _load_prompt("analysis.txt")
    if not template:
        return f"오늘 {date_str}. 데이터:\n{m5_context}\n{m2_context}\n{m4_context}\n{news_context}"

    return template.format(
        date=date_str,
        news_context=news_context,
        news_count=news_count,
        lookback_hours=lookback_hours,
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


def _call_gpt(system_prompt: str, user_message: str) -> str | None:
    if not GPT_API_KEY:
        logger.error("GPT_API_KEY 없음")
        return None
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GPT_API_KEY}", "Content-Type": "application/json"}
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
        choices = data.get("choices", [])
        if not choices:
            return None
        content = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        logger.info("GPT 완료: in=%d out=%d total=%d", usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), usage.get("total_tokens", 0))
        return content.strip()
    except requests.exceptions.Timeout:
        logger.error("GPT 타임아웃")
        return None
    except requests.exceptions.HTTPError as e:
        body = resp.text[:500] if resp else ""
        logger.error("GPT HTTP 에러: %s — %s", e, body)
        return None
    except Exception as e:
        logger.error("GPT 실패: %s", e)
        return None


def _build_fallback(m2, m3, m5, m4, m7, m6, news, news_count, date_str):
    parts = [f"📊 브리핑 — {date_str}", "", "⚠️ GPT 오류 — 원문 데이터:", ""]
    for label, ctx in [("시장 스냅샷+리스크", m5), ("섹터 로테이션", m2), ("역발상", m3), ("포지션", m4), ("상관관계", m7), ("피드백", m6)]:
        if ctx:
            parts.extend([f"━━━ {label} ━━━", ctx, ""])
    if news_count > 0:
        parts.extend([f"━━━ 뉴스 ({news_count}건) ━━━", news[:1500]])
    parts.append("\n⚠️ AI 스크리닝이며 매매 시그널이 아닙니다.")
    return "\n".join(parts)


def _save_to_sheets(briefing: str, briefing_mode: str):
    """브리핑을 Sheets에 저장. 실패해도 무시 (텔레그램 전송이 메인)."""
    try:
        from src.collectors.sheets import save_briefing
        date_str = now_kst().strftime("%Y-%m-%d")
        save_briefing(date_str, briefing, briefing_mode)
    except Exception as e:
        logger.warning("Sheets 저장 스킵 (텔레그램은 정상): %s", e)


def run_m1(
    m2_context: str = "", m3_context: str = "", m5_context: str = "",
    m4_context: str = "", m7_context: str = "", m6_context: str = "",
    prev_summary: str = "", briefing_mode: str = "daily",
    analytics_context: str = "",
) -> dict:
    date_str = now_kst().strftime("%Y-%m-%d (%a)")
    logger.info("=" * 50)
    logger.info("M1 시작: %s [%s]", date_str, briefing_mode)

    try:
        articles, lookback_hours = collect_news()
    except Exception as e:
        logger.error("뉴스 수집 실패: %s", e)
        articles, lookback_hours = [], 28

    news_count = len(articles)
    news_context = format_news_context(articles)
    logger.info("뉴스 %d건 (lookback %dh)", news_count, lookback_hours)

    system_prompt = _load_prompt("system.txt")
    if not system_prompt:
        briefing = _build_fallback(m2_context, m3_context, m5_context, m4_context, m7_context, m6_context, news_context, news_count, date_str)
        return {"briefing": briefing, "used_llm": False, "news_count": news_count, "context_text": briefing}

    user_message = _build_user_message(
        news_context=news_context, news_count=news_count, lookback_hours=lookback_hours,
        m2_context=m2_context, m3_context=m3_context, m5_context=m5_context,
        m4_context=m4_context, m7_context=m7_context, m6_context=m6_context,
        prev_summary=prev_summary, briefing_mode=briefing_mode, date_str=date_str,
        analytics_context=analytics_context,
    )

    gpt_result = _call_gpt(system_prompt, user_message)

    if gpt_result:
        logger.info("M1 GPT 성공 (%d자)", len(gpt_result))
        # ★ Sheets 저장
        _save_to_sheets(gpt_result, briefing_mode)
        return {"briefing": gpt_result, "used_llm": True, "news_count": news_count, "context_text": gpt_result}
    else:
        briefing = _build_fallback(m2_context, m3_context, m5_context, m4_context, m7_context, m6_context, news_context, news_count, date_str)
        # fallback도 저장
        _save_to_sheets(briefing, briefing_mode)
        return {"briefing": briefing, "used_llm": False, "news_count": news_count, "context_text": briefing}        logger.error("GPT_API_KEY 없음")
        return None
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GPT_API_KEY}", "Content-Type": "application/json"}
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
        choices = data.get("choices", [])
        if not choices:
            return None
        content = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        logger.info("GPT 완료: in=%d out=%d total=%d", usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), usage.get("total_tokens", 0))
        return content.strip()
    except requests.exceptions.Timeout:
        logger.error("GPT 타임아웃")
        return None
    except requests.exceptions.HTTPError as e:
        body = resp.text[:500] if resp else ""
        logger.error("GPT HTTP 에러: %s — %s", e, body)
        return None
    except Exception as e:
        logger.error("GPT 실패: %s", e)
        return None


def _build_fallback(m2, m3, m5, m4, m7, m6, news, news_count, date_str):
    parts = [f"📊 브리핑 — {date_str}", "", "⚠️ GPT 오류 — 원문 데이터:", ""]
    for label, ctx in [("시장 스냅샷+리스크", m5), ("섹터 로테이션", m2), ("역발상", m3), ("포지션", m4), ("상관관계", m7), ("피드백", m6)]:
        if ctx:
            parts.extend([f"━━━ {label} ━━━", ctx, ""])
    if news_count > 0:
        parts.extend([f"━━━ 뉴스 ({news_count}건) ━━━", news[:1500]])
    parts.append("\n⚠️ AI 스크리닝이며 매매 시그널이 아닙니다.")
    return "\n".join(parts)


def _save_to_sheets(briefing: str, briefing_mode: str):
    """브리핑을 Sheets에 저장. 실패해도 무시 (텔레그램 전송이 메인)."""
    try:
        from src.collectors.sheets import save_briefing
        date_str = now_kst().strftime("%Y-%m-%d")
        save_briefing(date_str, briefing, briefing_mode)
    except Exception as e:
        logger.warning("Sheets 저장 스킵 (텔레그램은 정상): %s", e)


def run_m1(
    m2_context: str = "", m3_context: str = "", m5_context: str = "",
    m4_context: str = "", m7_context: str = "", m6_context: str = "",
    prev_summary: str = "", briefing_mode: str = "daily",
) -> dict:
    date_str = now_kst().strftime("%Y-%m-%d (%a)")
    logger.info("=" * 50)
    logger.info("M1 시작: %s [%s]", date_str, briefing_mode)

    try:
        articles, lookback_hours = collect_news()
    except Exception as e:
        logger.error("뉴스 수집 실패: %s", e)
        articles, lookback_hours = [], 28

    news_count = len(articles)
    news_context = format_news_context(articles)
    logger.info("뉴스 %d건 (lookback %dh)", news_count, lookback_hours)

    system_prompt = _load_prompt("system.txt")
    if not system_prompt:
        briefing = _build_fallback(m2_context, m3_context, m5_context, m4_context, m7_context, m6_context, news_context, news_count, date_str)
        return {"briefing": briefing, "used_llm": False, "news_count": news_count, "context_text": briefing}

    user_message = _build_user_message(
        news_context=news_context, news_count=news_count, lookback_hours=lookback_hours,
        m2_context=m2_context, m3_context=m3_context, m5_context=m5_context,
        m4_context=m4_context, m7_context=m7_context, m6_context=m6_context,
        prev_summary=prev_summary, briefing_mode=briefing_mode, date_str=date_str,
    )

    gpt_result = _call_gpt(system_prompt, user_message)

    if gpt_result:
        logger.info("M1 GPT 성공 (%d자)", len(gpt_result))
        # ★ Sheets 저장
        _save_to_sheets(gpt_result, briefing_mode)
        return {"briefing": gpt_result, "used_llm": True, "news_count": news_count, "context_text": gpt_result}
    else:
        briefing = _build_fallback(m2_context, m3_context, m5_context, m4_context, m7_context, m6_context, news_context, news_count, date_str)
        # fallback도 저장
        _save_to_sheets(briefing, briefing_mode)
        return {"briefing": briefing, "used_llm": False, "news_count": news_count, "context_text": briefing}
