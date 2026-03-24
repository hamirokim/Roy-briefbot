"""텔레그램 Bot API 전송."""

from __future__ import annotations

import requests

from src.utils import env, truncate


def send_telegram(text: str) -> bool:
    """HTML parse_mode로 텔레그램 메시지 전송. 성공 여부 반환."""
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[WARN] TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 미설정. 전송 건너뜀.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": truncate(text),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"[ERROR] 텔레그램 전송 실패: {e}")
        return False
