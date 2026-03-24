"""공통 유틸리티 — env, 시간, 텍스트 헬퍼."""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def env(key: str, default: str = "") -> str:
    """환경 변수 읽기. 없으면 default 반환."""
    return os.environ.get(key, default)


def env_int(key: str, default: int = 0) -> int:
    """환경 변수를 int로 읽기."""
    raw = os.environ.get(key, "")
    if raw.strip() == "":
        return default
    return int(raw)


def now_kst() -> datetime:
    """현재 KST 시각."""
    return datetime.now(KST)


def today_kst_str() -> str:
    """오늘 날짜 문자열 (YYYY-MM-DD)."""
    return now_kst().strftime("%Y-%m-%d")


def truncate(text: str, limit: int = 4096) -> str:
    """텔레그램 메시지 길이 제한. 초과 시 말줄임."""
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n\n… (잘림)"
