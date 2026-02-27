import os
import sys
import time
import json
import html
import traceback
from pathlib import Path
from datetime import datetime, timedelta, timezone

import requests
import feedparser


VERSION = "0.2.0"
TELEGRAM_API = "https://api.telegram.org"
ETF_MAP_PATH = Path("config/etf_map.json")


def now_kst() -> datetime:
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9)))


def env(name: str, default: str = "") -> str:
    v = os.getenv(name, default)
    return v.strip() if isinstance(v, str) else default


def load_etf_map() -> dict:
    """
    Load ETF map from config/etf_map.json.
    If the file is missing or invalid, return a safe fallback without crashing.
    """
    fallback = {
        "benchmark": ["ACWI"],
        "sectors_11": [],
        "countries_regions_16": {"developed": [], "emerging": []},
    }
    try:
        with ETF_MAP_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception:
        print("[WARN] Failed to load config/etf_map.json", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return fallback


def load_rss_urls() -> list[str]:
    raw = env("RSS_URLS")
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]

    # Default RSS sources (you can replace later)
    return [
        "https://news.ycombinator.com/rss",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
    ]


def fetch_headlines(rss_urls: list[str], top_n: int = 8, timeout: int = 12) -> list[dict]:
    items = []

    for url in rss_urls:
        try:
            headers = {"User-Agent": env("USER_AGENT", "RoyBriefbot/0.2 (+GitHub Actions)")}
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()

            feed = feedparser.parse(resp.text)
            source = (feed.feed.get("title") or url).strip()

            for e in feed.entries[: max(top_n, 20)]:
                title = (e.get("title") or "").strip()
                link = (e.get("link") or "").strip()
                if not title:
                    continue

                ts = 0
                if "published_parsed" in e and e.published_parsed:
                    ts = int(time.mktime(e.published_parsed))
                elif "updated_parsed" in e and e.updated_parsed:
                    ts = int(time.mktime(e.updated_parsed))

                items.append({"source": source, "title": title, "link": link, "_ts": ts})

        except Exception:
            print(f"[WARN] RSS fetch failed: {url}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)

    # Sort by time desc; missing timestamps go last
    items.sort(key=lambda x: x.get("_ts", 0), reverse=True)

    # Deduplicate by title
    seen = set()
    dedup = []
    for it in items:
        key = it["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(it)
        if len(dedup) >= top_n:
            break

    for it in dedup:
        it.pop("_ts", None)
    return dedup


def truncate_telegram(text: str, limit: int = 3900) -> str:
    # Telegram hard limit is 4096; keep a buffer.
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…(truncated)"


def build_message(headlines: list[dict], etf_map: dict, ok: bool = True, error_summary: str = "") -> str:
    kst = now_kst().strftime("%Y-%m-%d %H:%M:%S KST")
    sha = env("GITHUB_SHA")
    sha_short = sha[:7] if sha else "local"
    status = "OK" if ok else "ERROR"

    benchmark = etf_map.get("benchmark", []) or []
    sectors = etf_map.get("sectors_11", []) or []
    cr = etf_map.get("countries_regions_16", {}) or {}
    developed = cr.get("developed", []) or []
    emerging = cr.get("emerging", []) or []
    countries_cnt = len(developed) + len(emerging)

    lines = []

    # S0 Meta
    lines.append(f"<b>Daily Briefing</b>  <code>{status}</code>")
    lines.append(f"⏱️ {html.escape(kst)}")
    lines.append(f"🧩 v{VERSION} / {html.escape(sha_short)}")
    lines.append(f"🗺️ ETF map loaded: benchmark={','.join(benchmark)} / sectors={len(sectors)} / countries={countries_cnt}")
    lines.append("")

    # S1 Headlines
    lines.append("<b>S1. Headlines</b>")
    if not headlines:
        lines.append("• (no headlines fetched)")
    else:
        for i, h in enumerate(headlines, 1):
            src = html.escape(h.get("source", ""))
            title = html.escape(h.get("title", ""))
            link = h.get("link", "")
            if link:
                lines.append(f'{i}) <a href="{html.escape(link)}">{title}</a> <i>({src})</i>')
            else:
                lines.append(f"{i}) {title} <i>({src})</i>")

    # S4 Error
    if not ok and error_summary:
        lines.append("")
        lines.append("<b>S4. Error</b>")
        lines.append(f"<code>{html.escape(error_summary)}</code>")

    return truncate_telegram("\n".join(lines))


def send_telegram(text: str) -> None:
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=12)
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram send failed: {resp.status_code} {resp.text}")


def main() -> int:
    top_n = int(env("TOP_N", "8") or "8")
    rss_urls = load_rss_urls()
    etf_map = load_etf_map()

    try:
        headlines = fetch_headlines(rss_urls, top_n=top_n)
        msg = build_message(headlines, etf_map=etf_map, ok=True)
        send_telegram(msg)
        print("[OK] Briefing sent.")
        return 0

    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:300]}"
        print("[ERROR] " + err, file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)

        try:
            msg = build_message([], etf_map=etf_map, ok=False, error_summary=err)
            send_telegram(msg)
            print("[OK] Error notification sent.")
        except Exception:
            print("[FATAL] Also failed to send error notification.", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
