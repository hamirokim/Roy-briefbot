import os
import datetime as dt
import requests

def send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Secrets에 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID가 없습니다.")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True
    }
    r = requests.post(url, json=payload, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"텔레그램 전송 실패: {r.status_code} {r.text}")

if __name__ == "__main__":
    now_kst = dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    msg = (
        f"[ROY BRIEF BOT] 테스트 성공\n"
        f"- 실행시간(KST): {now_kst.isoformat(timespec='seconds')}\n"
        f"- 다음: 브리핑 포맷/스캐너 로직 삽입"
    )
    send_telegram(msg)
    print("OK")
