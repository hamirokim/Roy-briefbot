"""
src/agents/base.py — BaseAgent 공통 클래스

모든 에이전트(SCOUT/GUARD/REGIME/DIGEST)가 상속.
공통: 로깅, 에러 처리, 출력 스키마 검증, LLM 호출 헬퍼.
"""

import os
import logging
import json
import time
from typing import Any, Optional
from abc import ABC, abstractmethod

import requests

logger = logging.getLogger(__name__)

# ── LLM 공통 설정 (모든 에이전트 같은 모델 — Q5 결정) ──
GPT_API_KEY = os.environ.get("GPT_API_KEY", "")
GPT_MODEL = os.environ.get("GPT_MODEL", "gpt-5.4-mini")
GPT_TIMEOUT = int(os.environ.get("GPT_TIMEOUT", "60"))
GPT_TEMPERATURE = float(os.environ.get("GPT_TEMPERATURE", "0.3"))


class BaseAgent(ABC):
    """모든 에이전트의 공통 베이스."""

    def __init__(self, name: str):
        self.name = name
        self.log = logging.getLogger(f"agent.{name}")
        self.start_time: float = 0.0
        self.errors: list[str] = []

    @abstractmethod
    def run(self, state: dict) -> dict:
        """에이전트 실행. state 받아서 출력 dict 반환."""
        ...

    def execute(self, state: dict) -> dict:
        """run() 래퍼 — 로깅 + 에러 캐치 + 시간 측정."""
        self.start_time = time.time()
        self.log.info("─" * 50)
        self.log.info("[%s] 시작", self.name)
        try:
            result = self.run(state)
            elapsed = time.time() - self.start_time
            self.log.info("[%s] 완료 (%.1fs)", self.name, elapsed)
            return result
        except Exception as e:
            elapsed = time.time() - self.start_time
            self.log.error("[%s] 실패 (%.1fs): %s", self.name, elapsed, e, exc_info=True)
            return self._error_output(str(e))

    @abstractmethod
    def _error_output(self, error_msg: str) -> dict:
        """에이전트 실패 시 fallback 출력 구조."""
        ...

    # ── LLM 호출 헬퍼 (4 에이전트 공통) ──
    def call_llm(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1500,
    ) -> Optional[str]:
        """OpenAI API 호출. 실패 시 None 반환."""
        if not GPT_API_KEY:
            self.log.error("GPT_API_KEY 없음")
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
            "max_completion_tokens": max_tokens,
            "temperature": GPT_TEMPERATURE,
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
            self.log.info(
                "LLM 호출: in=%d out=%d total=%d",
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                usage.get("total_tokens", 0),
            )
            return content.strip()
        except requests.exceptions.Timeout:
            self.log.error("LLM 타임아웃")
            self.errors.append("llm_timeout")
            return None
        except requests.exceptions.HTTPError as e:
            self.log.error("LLM HTTP 에러: %s", e)
            self.errors.append(f"llm_http_{e.response.status_code if e.response else 'unknown'}")
            return None
        except Exception as e:
            self.log.error("LLM 실패: %s", e)
            self.errors.append(f"llm_error_{type(e).__name__}")
            return None
