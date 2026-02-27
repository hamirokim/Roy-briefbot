import os
import sys
import time
import json
import html
import traceback
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional

import requests
import feedparser


VERSION = "0.3.0"
TELEGRAM_API = "https://api.telegram.org"
ETF_MAP_PATH = Path("config/etf_map.json")

# Data source for ETF map performance (free, no key). Best-effort.
# Stooq daily CSV endpoint: https://stooq.com/q/d/l/?s=spy.us&i=d
STOOQ_BASE = "https://stooq.com/q/d/l/"


def now_kst() -> datetime:
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9)))


def env(name: str, default: str = "") -> str:
    v = os.getenv(name, default)
    return v.strip() if isinstance(v, str) else default


def load_etf_map() -> dict:
    """Load ETF map from config/etf_map.json. Safe fallback if missing/invalid."""
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


def load_rss_urls() -> List[str]:
    raw = env("RSS_URLS")
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]

    # Default RSS sources (replace later)
    return [
        "https://news.ycombinator.com/rss",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
    ]


def fetch_headlines(rss_urls: List[str], top_n: int = 8, timeout: int = 12) -> List[dict]:
    items = []

    for url in rss_urls:
        try:
            headers = {"User-Agent": env("USER_AGENT", "RoyBriefbot/0.3 (+GitHub Actions)")}
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

    items.sort(key=lambda x: x.get("_ts", 0), reverse=True)

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
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…(truncated)"


# -----------------------
# S2: ETF Map (Sector/Country) Rankings
# -----------------------
def _stooq_symbol(ticker: str) -> str:
    # Stooq uses lowercase and often requires ".us" suffix for US-listed ETFs.
    # Example: SPY -> spy.us
    t = ticker.strip().lower()
    if "." in t:
        return t  # already supplied
    return f"{t}.us"


def _fetch_stooq_daily_closes(ticker: str, timeout: int = 12) -> List[Tuple[str, float]]:
    """Return list of (date, close) ascending by date. Best effort."""
    sym = _stooq_symbol(ticker)
    url = f"{STOOQ_BASE}?s={sym}&i=d"
    headers = {"User-Agent": env("USER_AGENT", "RoyBriefbot/0.3 (+GitHub Actions)")}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()

    text = resp.text.strip()
    if not text or "Date,Open,High,Low,Close,Volume" not in text:
        return []

    lines = text.splitlines()
    if len(lines) < 3:
        return []

    out: List[Tuple[str, float]] = []
    for row in lines[1:]:
        cols = row.split(",")
        if len(cols) < 5:
            continue
        date = cols[0].strip()
        close_str = cols[4].strip()
        try:
            close = float(close_str)
        except Exception:
            continue
        out.append((date, close))

    return out


def _pct_change(closes: List[Tuple[str, float]], lookback: int) -> Optional[float]:
    """Percent change vs N trading days ago."""
    if len(closes) < lookback + 1:
        return None
    last = closes[-1][1]
    prev = closes[-(lookback + 1)][1]
    if prev == 0:
        return None
    return (last / prev - 1.0) * 100.0


def _fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "NA"
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.1f}%"


def build_etf_rankings(
    tickers: List[str],
    benchmark: str,
    timeout: int = 12,
) -> Tuple[List[dict], List[str]]:
    """Return per-ticker perf/RS metrics and list of failed tickers."""
    failed: List[str] = []
    cache: Dict[str, List[Tuple[str, float]]] = {}

    def get_closes(t: str) -> List[Tuple[str, float]]:
        if t in cache:
            return cache[t]
        closes = _fetch_stooq_daily_closes(t, timeout=timeout)
        cache[t] = closes
        return closes

    bench_closes = get_closes(benchmark)
    if not bench_closes:
        # If benchmark fails, we still compute absolute returns but RS becomes NA.
        failed.append(benchmark)

    horizons = {
        "1w": 5,
        "1m": 21,
        "3m": 63,
        "6m": 126,
    }

    bench_ret = {k: _pct_change(bench_closes, v) for k, v in horizons.items()} if bench_closes else {}

    rows: List[dict] = []
    for t in tickers:
        try:
            closes = get_closes(t)
            if not closes:
                failed.append(t)
                continue

            ret = {k: _pct_change(closes, v) for k, v in horizons.items()}
            rs = {}
            for k in horizons.keys():
                if bench_closes and ret.get(k) is not None and bench_ret.get(k) is not None:
                    rs[k] = ret[k] - bench_ret[k]
                else:
                    rs[k] = None

            rows.append(
                {
                    "ticker": t,
                    "ret": ret,
                    "rs": rs,
                }
            )
        except Exception:
            failed.append(t)

    return rows, failed


def pick_top_tracks(rows: List[dict], top_n: int = 3) -> Tuple[List[dict], List[dict]]:
    """Pick A track (sustained strength) and B track (revival) using RS metrics."""
    # A track: weighted RS (6m,3m)
    def score_a(r: dict) -> float:
        rs6 = r["rs"].get("6m")
        rs3 = r["rs"].get("3m")
        if rs6 is None or rs3 is None:
            return -1e9
        return 0.6 * rs6 + 0.4 * rs3

    # B track: "revival" - short-term RS flips positive while medium-term still negative/weak
    # Conditions are soft; we score improvement.
    def score_b(r: dict) -> float:
        rs1w = r["rs"].get("1w")
        rs1m = r["rs"].get("1m")
        rs3m = r["rs"].get("3m")
        if rs1w is None or rs1m is None or rs3m is None:
            return -1e9
        # revival preference: rs1w positive and rs1m/rs3m not strongly positive yet
        if rs1w <= 0:
            return -1e9
        # improvement score: rs1w - rs1m plus a small bonus if rs3m < 0 (still in pullback)
        bonus = 0.5 if rs3m < 0 else 0.0
        return (rs1w - rs1m) + bonus

    a_sorted = sorted(rows, key=score_a, reverse=True)
    b_sorted = sorted(rows, key=score_b, reverse=True)

    top_a = [r for r in a_sorted if score_a(r) > -1e8][:top_n]
    top_b = [r for r in b_sorted if score_b(r) > -1e8][:top_n]
    return top_a, top_b


def format_track_list(rows: List[dict], track: str) -> List[str]:
    lines: List[str] = []
    for r in rows:
        t = r["ticker"]
        if track == "A":
            lines.append(
                f"• {t}: RS3M {_fmt_pct(r['rs'].get('3m'))}, RS6M {_fmt_pct(r['rs'].get('6m'))}"
            )
        else:
            lines.append(
                f"• {t}: RS1W {_fmt_pct(r['rs'].get('1w'))}, RS1M {_fmt_pct(r['rs'].get('1m'))}"
            )
    return lines


def build_s2_section(etf_map: dict) -> Tuple[List[str], List[str]]:
    """Return (s2_lines, warnings)."""
    warnings: List[str] = []
    benchmark_list = etf_map.get("benchmark", []) or ["ACWI"]
    benchmark = benchmark_list[0] if benchmark_list else "ACWI"

    sectors = etf_map.get("sectors_11", []) or []
    cr = etf_map.get("countries_regions_16", {}) or {}
    developed = cr.get("developed", []) or []
    emerging = cr.get("emerging", []) or []
    countries = developed + emerging

    # If config is empty, don't crash
    if not sectors and not countries:
        return ["(ETF map is empty)"], warnings

    # Build rankings
    lines: List[str] = []
    timeout = int(env("DATA_TIMEOUT", "12") or "12")

    # Sectors
    if sectors:
        rows, failed = build_etf_rankings(sectors, benchmark=benchmark, timeout=timeout)
        if failed:
            warnings.append(f"S2 sectors data missing: {', '.join(sorted(set(failed))[:8])}" + ("…" if len(set(failed)) > 8 else ""))
        top_a, top_b = pick_top_tracks(rows, top_n=3)
        lines.append("<b>S2. ETF Map</b>")
        lines.append(f"<i>Benchmark</i>: {html.escape(benchmark)}  <i>Source</i>: Stooq (daily)")
        lines.append("")
        lines.append("<b>Sector A (Sustained)</b>")
        lines.extend([html.escape(s) for s in format_track_list(top_a, "A")] or ["• (no data)"])
        lines.append("<b>Sector B (Revival)</b>")
        lines.extend([html.escape(s) for s in format_track_list(top_b, "B")] or ["• (no data)"])
        lines.append("")

    # Countries
    if countries:
        rows, failed = build_etf_rankings(countries, benchmark=benchmark, timeout=timeout)
        if failed:
            warnings.append(f"S2 countries data missing: {', '.join(sorted(set(failed))[:8])}" + ("…" if len(set(failed)) > 8 else ""))
        top_a, top_b = pick_top_tracks(rows, top_n=3)
        lines.append("<b>Country/Region A (Sustained)</b>")
        lines.extend([html.escape(s) for s in format_track_list(top_a, "A")] or ["• (no data)"])
        lines.append("<b>Country/Region B (Revival)</b>")
        lines.extend([html.escape(s) for s in format_track_list(top_b, "B")] or ["• (no data)"])

    return lines, warnings


def build_message(headlines: List[dict], etf_map: dict, ok: bool = True, error_summary: str = "", include_s2: bool = True) -> str:
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

    lines: List[str] = []

    # S0 Meta
    lines.append(f"<b>Daily Briefing</b>  <code>{status}</code>")
    lines.append(f"⏱️ {html.escape(kst)}")
    lines.append(f"🧩 v{VERSION} / {html.escape(sha_short)}")
    lines.append(f"🗺️ ETF map loaded: benchmark={','.join(benchmark)} / sectors={len(sectors)} / countries={countries_cnt}")
    lines.append("")

    # S2 ETF map (optional)
    if include_s2 and ok:
        try:
            s2_lines, warnings = build_s2_section(etf_map)
            lines.extend(s2_lines)
            if warnings:
                lines.append("")
                lines.append("<b>S4. Log</b>")
                for w in warnings[:3]:
                    lines.append(f"• {html.escape(w)}")
            lines.append("")
        except Exception:
            lines.append("<b>S2. ETF Map</b>")
            lines.append("• (failed to compute ETF map rankings)")
            lines.append("")
            print("[WARN] S2 ETF map failed", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)

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

    # Error summary
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

    include_s2 = env("INCLUDE_S2", "1") != "0"

    try:
        headlines = fetch_headlines(rss_urls, top_n=top_n)
        msg = build_message(headlines, etf_map=etf_map, ok=True, include_s2=include_s2)
        send_telegram(msg)
        print("[OK] Briefing sent.")
        return 0

    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:300]}"
        print("[ERROR] " + err, file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)

        try:
            msg = build_message([], etf_map=etf_map, ok=False, error_summary=err, include_s2=False)
            send_telegram(msg)
            print("[OK] Error notification sent.")
        except Exception:
            print("[FATAL] Also failed to send error notification.", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
