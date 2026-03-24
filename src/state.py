"""state.json 로드 · 저장 · 정리."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from typing import Any

from src.utils import env_int, now_kst

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "state.json")

_DEFAULT: dict[str, Any] = {
    "last_run_kst": "",
    "m2_history": {},
}


def load_state() -> dict[str, Any]:
    """state.json 로드. 파일이 없거나 깨졌으면 기본값 반환."""
    path = os.path.abspath(STATE_PATH)
    if not os.path.exists(path):
        return _DEFAULT.copy()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _DEFAULT.copy()
    # 누락 키 보완
    for k, v in _DEFAULT.items():
        if k not in data:
            data[k] = v if not isinstance(v, dict) else {}
    return data


def save_state(state: dict[str, Any]) -> None:
    """state.json 저장."""
    path = os.path.abspath(STATE_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    state["last_run_kst"] = now_kst().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def prune_m2_history(state: dict[str, Any]) -> None:
    """m2_history에서 오래된 날짜 제거. RS_HISTORY_KEEP_DAYS 기준."""
    keep_days = env_int("RS_HISTORY_KEEP_DAYS", 7)
    cutoff = (now_kst() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    history: dict = state.get("m2_history", {})
    old_keys = [d for d in history if d < cutoff]
    for k in old_keys:
        del history[k]
