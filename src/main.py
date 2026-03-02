import os
import sys
import time
import json
import html
import traceback
import re
from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional

import requests
import feedparser
from openpyxl import load_workbook


VERSION = "0.4.3"
TELEGRAM_API = "https://api.telegram.org"

ETF_MAP_PATH = Path("config/etf_map.json")
STATE_PATH = Path("data/state.json")

STOOQ_BASE = "https://stooq.com/q/d/l/"
SSGA_HOLDINGS_TMPL = "https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-{}.xlsx"

HANGUL_RE = re.compile(r"[가-힣]")


def now_kst() -> datetime:
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9)))


def env(name: str, default: str = "") -> str:
    v = os.getenv(name, default)
    return v.strip() if isinstance(v, str) else default


def get_lang() -> str:
    lang = (env("BRIEF_LANG", "ko") or "ko").lower()
    return "en" if lang.startswith("en") else "ko"


def tr(key: str) -> str:
    ko = {
        "title": "데일리 브리핑",
        "status_ok": "정상",
        "status_err": "오류",
        "etf_loaded": "ETF 지도 로드",

        "s2": "S2. ETF 지도",
        "benchmark": "벤치마크",
        "source": "소스",
        "sector_a": "섹터 A (지속 강세)",
        "sector_b": "섹터 B (회복 시도)",
        "country_a": "국가/지역 A (지속 강세)",
        "country_b": "국가/지역 B (회복 시도)",

        "s3a": "S3-A. 진입 임박 후보(0~4)",
        "s3b": "S3-B. 바닥 형성 후보(승급 대기)",
        "s3_none": "• 오늘 후보 없음 (조건 미충족/데이터 부족)",
        "s3_note": "※ 후보는 'ENTRY 신호'가 아니라 '환경(급락+눌림+추격방지+리스크)' 기반. 타이밍은 TradingView 4H 지표로 최종 확인.",

        "s1": "S1. 오늘 체크(제목 기반 요약)",
        "s1_note": "※ 본문 요약이 아니라 제목 키워드로 '리스크/이벤트'만 압축. (원문 클릭은 선택)",
        "no_news": "• (시장 관련 헤드라인 없음)",
        "raw_headlines": "원문 헤드라인",

        "s4_log": "S4. 로그",
        "s4_err": "S4. 에러",
        "state_missing": "• state.json이 없어 새로 생성(정상)",
    }
    en = {
        "title": "Daily Briefing",
        "status_ok": "OK",
        "status_err": "ERROR",
    }
    table = ko if get_lang() == "ko" else en
    return table.get(key, key)


# -----------------------
# State
# -----------------------
def load_state() -> Tuple[dict, List[str]]:
    logs = []
    default_state = {"last_run_kst": "", "seen_links": [], "candidate_history": []}
    try:
        if not STATE_PATH.exists():
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(json.dumps(default_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            logs.append(tr("state_missing"))
            return default_state, logs
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default_state, logs
        data.setdefault("last_run_kst", "")
        data.setdefault("seen_links", [])
        data.setdefault("candidate_history", [])
        return data, logs
    except Exception:
        logs.append("• state.json 로드 실패(무시하고 진행)")
        return default_state, logs


def save_state(state: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        print("[WARN] Failed to save state.json", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)


def prune_state(state: dict) -> None:
    max_links = int(env("STATE_MAX_LINKS", "1500") or "1500")
    seen = state.get("seen_links", []) or []
    if len(seen) > max_links:
        state["seen_links"] = seen[-max_links:]


def mark_links_seen(state: dict, links: List[str]) -> None:
    seen = state.get("seen_links", []) or []
    for l in links:
        if l and l not in seen:
            seen.append(l)
    state["seen_links"] = seen
    prune_state(state)


def add_candidate_history(state: dict, items: List[dict]) -> None:
    hist = state.get("candidate_history", []) or []
    today = now_kst().date()
    cutoff = today - timedelta(days=60)

    kept = []
    for h in hist:
        try:
            d = datetime.strptime(h.get("date_kst", ""), "%Y-%m-%d").date()
            if d >= cutoff:
                kept.append(h)
        except Exception:
            continue

    kept.extend(items)
    state["candidate_history"] = kept


def was_recently_recommended(state: dict, ticker: str, days: int) -> bool:
    hist = state.get("candidate_history", []) or []
    today = now_kst().date()
    for h in reversed(hist):
        if h.get("ticker") == ticker:
            try:
                d = datetime.strptime(h.get("date_kst", ""), "%Y-%m-%d").date()
                return (today - d).days <= days
            except Exception:
                return True
    return False


# -----------------------
# Config / RSS
# -----------------------
def load_etf_map() -> dict:
    fallback = {"benchmark": ["ACWI"], "sectors_11": [], "countries_regions_16": {"developed": [], "emerging": []}}
    try:
        with ETF_MAP_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        print("[WARN] Failed to load config/etf_map.json", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return fallback


def load_rss_urls() -> List[str]:
    raw = env("RSS_URLS")
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]
    return [
        "https://www.hankyung.com/feed/finance",
        "https://www.hankyung.com/feed/economy",
        "https://www.yonhapnewseconomytv.com/rss/allArticle.xml",
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko",
    ]


def _keyword_list() -> List[str]:
    custom = env("NEWS_KEYWORDS")
    if custom:
        return [k.strip() for k in custom.split(",") if k.strip()]
    return [
        "FOMC", "연준", "금리", "CPI", "PCE", "고용", "실업", "국채", "채권", "달러", "환율",
        "실적", "어닝", "가이던스", "반도체", "AI", "유가", "OPEC",
        "코스피", "코스닥", "나스닥", "S&P", "VIX", "리밸런싱", "지정학", "전쟁", "제재",
    ]


def is_korean_title(title: str) -> bool:
    return bool(HANGUL_RE.search(title or ""))


def fetch_headlines(
    rss_urls: List[str],
    top_n: int = 16,
    timeout: int = 12,
    state: Optional[dict] = None
) -> Tuple[List[dict], List[str]]:
    items = []
    logs = []
    per_feed = []

    for url in rss_urls:
        try:
            headers = {"User-Agent": env("USER_AGENT", "RoyBriefbot/0.4.3 (+GitHub Actions)")}
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()

            feed = feedparser.parse(resp.text)
            source = (feed.feed.get("title") or url).strip()

            count = 0
            for e in feed.entries[: max(top_n, 80)]:
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
                count += 1

            per_feed.append((source, count))
        except Exception:
            logs.append(f"RSS 실패: {url}")
            per_feed.append((url, 0))

    ok_cnt = sum(1 for _, c in per_feed if c > 0)
    logs.append(f"RSS 상태: {ok_cnt}/{len(per_feed)} 피드 수집")
    for s, c in per_feed[:3]:
        logs.append(f"{s[:28]}…: {c}개")

    items.sort(key=lambda x: x.get("_ts", 0), reverse=True)
    seen_title = set()
    dedup = []
    for it in items:
        key = it["title"].lower()
        if key in seen_title:
            continue
        seen_title.add(key)
        it.pop("_ts", None)
        dedup.append(it)

    if env("NEWS_FILTER", "1") != "0":
        kws = [k.lower() for k in _keyword_list()]
        filtered = []
        for it in dedup:
            t = it["title"].lower()
            if any(k in t for k in kws):
                filtered.append(it)
        dedup = filtered if len(filtered) >= 3 else dedup

    if get_lang() == "ko" and env("NEWS_REQUIRE_KOREAN", "1") != "0":
        ko_only = [it for it in dedup if is_korean_title(it.get("title", ""))]
        if len(ko_only) >= 2:
            dedup = ko_only
        else:
            logs.append("한글 뉴스 부족: 일부 영문이 섞일 수 있음")

    if state is not None and env("STATE_DEDUPE_NEWS", "1") != "0":
        seen_links = set(state.get("seen_links", []) or [])
        fresh = [it for it in dedup if it.get("link") and it["link"] not in seen_links]
        if len(fresh) >= 3:
            return fresh[:top_n], logs
        return (fresh + dedup)[:top_n], logs

    return dedup[:top_n], logs


def truncate_telegram(text: str, limit: int = 3900) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…(truncated)"


def news_score(title: str) -> Tuple[int, List[str], str]:
    t = (title or "").lower()
    tags: List[str] = []
    score = 0

    def hit(words: List[str], pts: int, tag: str):
        nonlocal score
        if any(w.lower() in t for w in words):
            score += pts
            tags.append(tag)

    hit(["fomc", "fed", "연준"], 6, "🟧통화정책")
    hit(["cpi", "pce", "inflation", "물가"], 6, "🟧물가지표")
    hit(["jobs", "employment", "실업", "고용"], 5, "🟨고용지표")
    hit(["yield", "treasury", "국채", "채권"], 5, "🟨금리/채권")
    hit(["usd", "dollar", "환율", "달러"], 4, "🟨환율")
    hit(["earnings", "guidance", "실적", "어닝", "가이던스"], 5, "🟦실적")
    hit(["vix", "volatility", "변동성"], 5, "🟥변동성")
    hit(["oil", "opec", "유가"], 4, "🟩원자재")
    hit(["war", "전쟁", "제재", "지정학"], 5, "🟥지정학")
    hit(["rebalanc", "리밸런싱", "월마감"], 4, "🟪수급")
    hit(["semiconductor", "chip", "반도체"], 4, "🟦섹터")
    hit(["ai", "인공지능"], 3, "🟦테마")

    if "🟥" in "".join(tags):
        note = "변동성/리스크 이벤트 가능. 신규 진입 보수."
    elif "🟧통화정책" in tags or "🟧물가지표" in tags or "🟨고용지표" in tags:
        note = "매크로 변동 구간. 사이즈/무효화 기준 엄격."
    elif "🟦실적" in tags:
        note = "실적 갭 리스크. 익일 시초가 변동 주의."
    elif "🟪수급" in tags:
        note = "월말/리밸런싱 수급 왜곡 가능."
    else:
        note = "시장 영향 가능. 필요시 원문 확인."

    tags = sorted(set(tags))
    return score, tags, note


def build_news_digest(headlines: List[dict]) -> Tuple[List[str], List[str]]:
    top_k = int(env("NEWS_DIGEST_TOP", "3") or "3")
    show_raw = env("SHOW_RAW_HEADLINES", "0") != "0"

    scored = []
    for h in headlines:
        s, tags, note = news_score(h.get("title", ""))
        scored.append((s, tags, note, h))

    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [x for x in scored if x[0] > 0][:top_k]
    if not picked:
        picked = scored[:min(top_k, len(scored))]

    lines: List[str] = []
    lines.append(f"<b>{html.escape(tr('s1'))}</b>")
    lines.append(html.escape(tr("s1_note")))
    if not picked:
        lines.append(html.escape(tr("no_news")))
        return lines, []

    used_links: List[str] = []
    for i, (s, tags, note, h) in enumerate(picked, 1):
        title = h.get("title", "")
        link = h.get("link", "")
        src = h.get("source", "")
        tag_str = " ".join(tags) if tags else "🟦시장"
        if link:
            lines.append(f"{i}) {tag_str} <a href=\"{html.escape(link)}\">{html.escape(title)}</a> <i>({html.escape(src)})</i>")
            used_links.append(link)
        else:
            lines.append(f"{i}) {tag_str} {html.escape(title)} <i>({html.escape(src)})</i>")
        lines.append(f"   • {html.escape(note)}")

    if show_raw:
        lines.append("")
        lines.append(f"<b>{html.escape(tr('raw_headlines'))}</b>")
        for i, h in enumerate(headlines[:8], 1):
            src = html.escape(h.get("source", ""))
            title = html.escape(h.get("title", ""))
            link = h.get("link", "")
            if link:
                lines.append(f'{i}) <a href="{html.escape(link)}">{title}</a> <i>({src})</i>')
            else:
                lines.append(f"{i}) {title} <i>({src})</i>")

    return lines, used_links


# -----------------------
# S2 (ETF map)
# -----------------------
def _stooq_symbol(ticker: str) -> str:
    t = ticker.strip().lower()
    if t.endswith(".us") or t.endswith(".uk") or t.endswith(".jp") or t.endswith(".de") or t.endswith(".pl"):
        return t
    return f"{t}.us"


def _fetch_stooq_daily_ohlcv(ticker: str, timeout: int = 12) -> List[dict]:
    sym = _stooq_symbol(ticker)
    url = f"{STOOQ_BASE}?s={sym}&i=d"
    headers = {"User-Agent": env("USER_AGENT", "RoyBriefbot/0.4.3 (+GitHub Actions)")}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()

    text = resp.text.strip()
    if not text or "Date,Open,High,Low,Close,Volume" not in text:
        return []

    lines = text.splitlines()
    if len(lines) < 3:
        return []

    out: List[dict] = []
    for row in lines[1:]:
        cols = row.split(",")
        if len(cols) < 6:
            continue
        try:
            out.append({"date": cols[0].strip(), "open": float(cols[1]), "high": float(cols[2]), "low": float(cols[3]), "close": float(cols[4]), "volume": float(cols[5])})
        except Exception:
            continue
    return out


def _closes(series: List[dict]) -> List[float]:
    return [x["close"] for x in series]


def _pct_change(closes: List[float], lookback: int) -> Optional[float]:
    if len(closes) < lookback + 1:
        return None
    last = closes[-1]
    prev = closes[-(lookback + 1)]
    if prev == 0:
        return None
    return (last / prev - 1.0) * 100.0


def _fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "NA"
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.1f}%"


def build_etf_rankings(tickers: List[str], benchmark: str, timeout: int = 12) -> Tuple[List[dict], List[str]]:
    failed: List[str] = []
    cache: Dict[str, List[dict]] = {}

    def get_series(t: str) -> List[dict]:
        if t in cache:
            return cache[t]
        s = _fetch_stooq_daily_ohlcv(t, timeout=timeout)
        cache[t] = s
        return s

    bench_series = get_series(benchmark)
    bench_closes = _closes(bench_series) if bench_series else []
    if not bench_closes:
        failed.append(benchmark)

    horizons = {"1w": 5, "1m": 21, "3m": 63, "6m": 126}
    bench_ret = {k: _pct_change(bench_closes, v) for k, v in horizons.items()} if bench_closes else {}

    rows: List[dict] = []
    for t in tickers:
        try:
            series = get_series(t)
            closes = _closes(series) if series else []
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
            rows.append({"ticker": t, "rs": rs})
        except Exception:
            failed.append(t)

    return rows, failed


def pick_top_tracks(rows: List[dict], top_n: int = 3) -> Tuple[List[dict], List[dict]]:
    def score_a(r: dict) -> float:
        rs6 = r["rs"].get("6m")
        rs3 = r["rs"].get("3m")
        if rs6 is None or rs3 is None:
            return -1e9
        return 0.6 * rs6 + 0.4 * rs3

    def score_b(r: dict) -> float:
        rs1w = r["rs"].get("1w")
        rs1m = r["rs"].get("1m")
        rs3m = r["rs"].get("3m")
        if rs1w is None or rs1m is None or rs3m is None:
            return -1e9
        if rs1w <= 0:
            return -1e9
        bonus = 0.5 if rs3m < 0 else 0.0
        return (rs1w - rs1m) + bonus

    a_sorted = sorted(rows, key=score_a, reverse=True)
    b_sorted = sorted(rows, key=score_b, reverse=True)
    top_a = [r for r in a_sorted if score_a(r) > -1e8][:top_n]
    top_b = [r for r in b_sorted if score_b(r) > -1e8][:top_n]
    return top_a, top_b


def compute_s2_picks(etf_map: dict) -> Tuple[List[str], List[str], List[str], List[str], List[str]]:
    warnings: List[str] = []
    benchmark = (etf_map.get("benchmark", []) or ["ACWI"])[0]

    sectors = etf_map.get("sectors_11", []) or []
    cr = etf_map.get("countries_regions_16", {}) or {}
    countries = (cr.get("developed", []) or []) + (cr.get("emerging", []) or [])

    timeout = int(env("DATA_TIMEOUT", "12") or "12")

    sector_a: List[str] = []
    sector_b: List[str] = []
    country_a: List[str] = []
    country_b: List[str] = []

    if sectors:
        rows, failed = build_etf_rankings(sectors, benchmark=benchmark, timeout=timeout)
        if failed:
            warnings.append("S2 sectors data missing: " + ", ".join(sorted(set(failed))[:8]))
        top_a, top_b = pick_top_tracks(rows, top_n=3)
        sector_a = [r["ticker"] for r in top_a]
        sector_b = [r["ticker"] for r in top_b]

    if countries:
        rows, failed = build_etf_rankings(countries, benchmark=benchmark, timeout=timeout)
        if failed:
            warnings.append("S2 countries data missing: " + ", ".join(sorted(set(failed))[:8]))
        top_a, top_b = pick_top_tracks(rows, top_n=3)
        country_a = [r["ticker"] for r in top_a]
        country_b = [r["ticker"] for r in top_b]

    return sector_a, sector_b, country_a, country_b, warnings


def build_s2_section(etf_map: dict, sector_a: List[str], sector_b: List[str], country_a: List[str], country_b: List[str]) -> List[str]:
    benchmark = (etf_map.get("benchmark", []) or ["ACWI"])[0]
    lines: List[str] = []
    lines.append(f"<b>{tr('s2')}</b>")
    lines.append(f"<i>{html.escape(tr('benchmark'))}</i>: {html.escape(benchmark)}  <i>{html.escape(tr('source'))}</i>: Stooq (daily)")
    lines.append("")
    lines.append(f"<b>{tr('sector_a')}</b>")
    lines.extend([f"• {html.escape(t)}" for t in sector_a] or ["• (없음)"])
    lines.append(f"<b>{tr('sector_b')}</b>")
    lines.extend([f"• {html.escape(t)}" for t in sector_b] or ["• (없음)"])
    lines.append("")
    lines.append(f"<b>{tr('country_a')}</b>")
    lines.extend([f"• {html.escape(t)}" for t in country_a] or ["• (없음)"])
    lines.append(f"<b>{tr('country_b')}</b>")
    lines.extend([f"• {html.escape(t)}" for t in country_b] or ["• (없음)"])
    return lines


# -----------------------
# S3 (candidates)
# -----------------------
def sma(values: List[float], n: int) -> Optional[float]:
    if len(values) < n:
        return None
    return sum(values[-n:]) / float(n)


def atr14(series: List[dict]) -> Optional[float]:
    if len(series) < 15:
        return None
    trs: List[float] = []
    for i in range(1, len(series)):
        h = series[i]["high"]
        l = series[i]["low"]
        pc = series[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < 14:
        return None
    return sum(trs[-14:]) / 14.0


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def grade(score: float) -> str:
    if score >= 90:
        return "SSS"
    if score >= 80:
        return "SS"
    if score >= 70:
        return "S"
    return "C"


def _passes_liquidity(series: List[dict], close: float) -> bool:
    vol20 = sum([x["volume"] for x in series[-20:]]) / 20.0
    dollar_vol20 = vol20 * close
    min_price = float(env("S3_MIN_PRICE", "5") or "5")
    min_dv = float(env("S3_MIN_DOLLAR_VOL", "20000000") or "20000000")
    return (close >= min_price) and (dollar_vol20 >= min_dv)


def score_stock(series: List[dict]) -> Optional[dict]:
    closes = _closes(series)
    if len(closes) < 260:
        return None
    close = closes[-1]
    if close <= 0:
        return None
    if not _passes_liquidity(series, close):
        return None

    high252 = max(closes[-252:])
    dd = (close / high252) - 1.0

    hard_dd = float(env("S3_MIN_DD", "-0.30") or "-0.30")
    pre_dd = float(env("S3_PRE_DD", "-0.27") or "-0.27")

    kind = None
    if dd <= hard_dd:
        kind = "entry"
    elif dd <= pre_dd:
        kind = "base"
    else:
        return None

    r5 = _pct_change(closes, 5)
    r21 = _pct_change(closes, 21)
    if r5 is None or r5 <= 0:
        return None
    if env("S3_REQUIRE_1M_NEG", "1") != "0":
        if r21 is None or r21 >= 0:
            return None

    low20 = min([x["low"] for x in series[-20:]])
    bounce = (close / low20) - 1.0 if low20 > 0 else 999.0
    max_bounce = float(env("S3_MAX_BOUNCE_FROM_20D_LOW", "0.10") or "0.10")
    if bounce > max_bounce:
        return None

    a14 = atr14(series)
    if a14 is None:
        return None
    atrpct = (a14 / close) * 100.0
    if atrpct < float(env("S3_MIN_ATR_PCT", "2.0") or "2.0") or atrpct > float(env("S3_MAX_ATR_PCT", "8.0") or "8.0"):
        return None

    s200 = sma(closes, 200)
    if s200 is None:
        return None
    if env("S3_REQUIRE_ABOVE_200SMA", "1") != "0":
        if close <= s200:
            return None

    slope200 = None
    if len(closes) >= 220:
        s200_prev = sum(closes[-220:-20]) / 200.0
        slope200 = s200 - s200_prev
    if env("S3_REQUIRE_SLOPE200_POS", "1") != "0":
        if slope200 is None or slope200 <= 0:
            return None

    s50 = sma(closes, 50)

    dd_score = clamp((-dd) / 0.6, 0.0, 1.0)
    late_score = clamp(1.0 - (bounce / max_bounce), 0.0, 1.0)
    risk_score = clamp(1.0 - abs(atrpct - 4.0) / 6.0, 0.0, 1.0)
    pullback = 0.0
    if s50 is not None and close < s50:
        pullback += 0.6
    pullback += 0.2
    if slope200 is not None and slope200 > 0:
        pullback += 0.2
    pullback = clamp(pullback, 0.0, 1.0)

    score = 100.0 * (0.35 * dd_score + 0.30 * late_score + 0.20 * pullback + 0.15 * risk_score)
    return {"kind": kind, "dd52": dd, "r5": r5, "r21": r21, "atrpct": atrpct, "bounce20": bounce, "score": score, "grade": grade(score)}


def build_s3(sector_etfs: List[str], state: dict) -> Tuple[List[str], List[str], List[dict]]:
    warnings: List[str] = []
    timeout = int(env("DATA_TIMEOUT", "12") or "12")

    holdings_per_etf = int(env("S3_HOLDINGS_PER_ETF", "30") or "30")
    top_n = int(env("S3_TOP_N", "4") or "4")
    max_universe = int(env("S3_MAX_UNIVERSE", "120") or "120")
    cooldown_days = int(env("S3_COOLDOWN_DAYS", "10") or "10")

    dbg = {"etf": 0, "hold": 0, "tickers": 0, "scored": 0, "entry": 0, "base": 0, "cooldown_skip": 0}

    universe: Dict[str, dict] = {}
    for etf in sector_etfs:
        try:
            hs = fetch_spdr_holdings(etf, timeout=timeout)
            dbg["etf"] += 1
            if not hs:
                warnings.append(f"S3 holdings missing: {etf}")
                continue
            dbg["hold"] += min(len(hs), holdings_per_etf)
            for h in hs[:holdings_per_etf]:
                t = h["ticker"]
                if t not in universe:
                    universe[t] = {"name": h.get("name", ""), "from": set([etf])}
                else:
                    universe[t]["from"].add(etf)
        except Exception:
            warnings.append(f"S3 holdings error: {etf}")
            print(traceback.format_exc(), file=sys.stderr)

    tickers = list(universe.keys())[:max_universe]
    dbg["tickers"] = len(tickers)
    if not tickers:
        return [tr("s3_none"), tr("s3_note")], warnings, []

    entry_list: List[dict] = []
    base_list: List[dict] = []

    for t in tickers:
        try:
            series = _fetch_stooq_daily_ohlcv(t, timeout=timeout)
            if not series:
                continue
            m = score_stock(series)
            if not m:
                continue
            dbg["scored"] += 1

            m["ticker"] = t
            m["name"] = universe[t].get("name", "")
            m["from"] = ",".join(sorted(list(universe[t]["from"])))

            if m["grade"] != "SSS" and was_recently_recommended(state, t, cooldown_days):
                dbg["cooldown_skip"] += 1
                continue

            if m["kind"] == "entry":
                dbg["entry"] += 1
                entry_list.append(m)
            else:
                dbg["base"] += 1
                base_list.append(m)

        except Exception:
            continue

    entry_list.sort(key=lambda x: x["score"], reverse=True)
    base_list.sort(key=lambda x: x["score"], reverse=True)

    entry_pick = entry_list[:top_n]
    base_pick = base_list[:top_n]

    today_str = now_kst().strftime("%Y-%m-%d")
    hist_items: List[dict] = []

    lines: List[str] = []
    lines.append(f"<b>{html.escape(tr('s3a'))}</b>")
    if not entry_pick:
        lines.append("• (없음)")
    else:
        for i, m in enumerate(entry_pick, 1):
            t = m["ticker"]; g = m["grade"]
            name = (m.get("name","") or "").strip()
            name_short = (name[:28] + "…") if len(name) > 28 else name
            dd = m["dd52"] * 100.0
            bounce = m.get("bounce20", 0.0) * 100.0
            lines.append(f"{i}) <b>[{g}] {html.escape(t)}</b> {html.escape(name_short)}")
            lines.append(f"   • 급락: {dd:.1f}% / 추격: +{bounce:.1f}% / 1W: {_fmt_pct(m.get('r5'))} / 1M: {_fmt_pct(m.get('r21'))}")
            lines.append(f"   • 리스크: ATR% {m.get('atrpct'):.1f} / 출처(ETF): {html.escape(m.get('from',''))} / 점수: {m.get('score'):.0f}")
            hist_items.append({"date_kst": today_str, "ticker": t, "grade": g, "score": int(m.get("score",0))})

    lines.append("")
    lines.append(f"<b>{html.escape(tr('s3b'))}</b>")
    if not base_pick:
        lines.append("• (없음)")
    else:
        for i, m in enumerate(base_pick, 1):
            t = m["ticker"]; g = m["grade"]
            name = (m.get("name","") or "").strip()
            name_short = (name[:28] + "…") if len(name) > 28 else name
            dd = m["dd52"] * 100.0
            bounce = m.get("bounce20", 0.0) * 100.0
            lines.append(f"{i}) <b>[{g}] {html.escape(t)}</b> {html.escape(name_short)}")
            lines.append(f"   • 급락(버퍼): {dd:.1f}% / 추격: +{bounce:.1f}% / 1W: {_fmt_pct(m.get('r5'))} / 1M: {_fmt_pct(m.get('r21'))}")
            lines.append(f"   • 리스크: ATR% {m.get('atrpct'):.1f} / 출처(ETF): {html.escape(m.get('from',''))} / 점수: {m.get('score'):.0f}")

    lines.append(tr("s3_note"))

    if env("DEBUG_S3", "0") != "0":
        warnings.append(f"S3 스캔: ETF={dbg['etf']}, holdings={dbg['hold']}, tickers={dbg['tickers']}, scored={dbg['scored']}, entry={dbg['entry']}, base={dbg['base']}, cooldown_skip={dbg['cooldown_skip']}")

    return lines, warnings, hist_items


# -----------------------
# Telegram + Message
# -----------------------
def send_telegram(text: str) -> None:
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    resp = requests.post(url, json=payload, timeout=12)
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram send failed: {resp.status_code} {resp.text}")


def build_message(etf_map: dict, state: dict) -> str:
    logs: List[str] = []
    kst = now_kst().strftime("%Y-%m-%d %H:%M:%S KST")
    sha = env("GITHUB_SHA")
    sha_short = sha[:7] if sha else "local"

    benchmark = (etf_map.get("benchmark", []) or ["ACWI"])[0]
    sectors = etf_map.get("sectors_11", []) or []
    cr = etf_map.get("countries_regions_16", {}) or {}
    countries_cnt = len((cr.get("developed", []) or [])) + len((cr.get("emerging", []) or []))

    lines: List[str] = []
    lines.append(f"<b>{html.escape(tr('title'))}</b>  <code>{html.escape(tr('status_ok'))}</code>")
    lines.append(f"⏱️ {html.escape(kst)}")
    lines.append(f"🧩 v{VERSION} / {html.escape(sha_short)}")
    lines.append(f"🗺️ {html.escape(tr('etf_loaded'))}: benchmark={html.escape(benchmark)} / sectors={len(sectors)} / countries={countries_cnt}")
    lines.append("")

    sector_a: List[str] = []; sector_b: List[str] = []; country_a: List[str] = []; country_b: List[str] = []
    try:
        sector_a, sector_b, country_a, country_b, w = compute_s2_picks(etf_map)
        logs.extend(w)
        lines.extend(build_s2_section(etf_map, sector_a, sector_b, country_a, country_b))
        lines.append("")
    except Exception:
        lines.append(f"<b>{html.escape(tr('s2'))}</b>")
        lines.append("• (ETF 지도 계산 실패)")
        lines.append("")
        logs.append("S2 failed")
        print(traceback.format_exc(), file=sys.stderr)

    chosen: List[str] = []
    if sector_a:
        chosen.append(sector_a[0])
    if sector_b and sector_b[0] not in chosen:
        chosen.append(sector_b[0])

    try:
        s3_lines, w, hist_items = build_s3(chosen, state)
        logs.extend(w)
        lines.extend(s3_lines)
        lines.append("")
        if hist_items:
            add_candidate_history(state, hist_items)
    except Exception:
        lines.append(f"<b>{html.escape(tr('s3a'))}</b>")
        lines.append("• (후보 계산 실패)")
        lines.append("")
        logs.append("S3 failed")
        print(traceback.format_exc(), file=sys.stderr)

    rss_urls = load_rss_urls()
    headlines, rss_logs = fetch_headlines(rss_urls, top_n=16, timeout=12, state=state)
    logs.extend(rss_logs)
    digest_lines, used_links = build_news_digest(headlines)
    lines.extend(digest_lines)

    if used_links:
        mark_links_seen(state, used_links)

    state["last_run_kst"] = now_kst().strftime("%Y-%m-%d %H:%M:%S")
    prune_state(state)

    if logs:
        lines.append("")
        lines.append(f"<b>{html.escape(tr('s4_log'))}</b>")
        for w in logs[:10]:
            lines.append(f"• {html.escape(w)}")

    return truncate_telegram("\n".join(lines))


def main() -> int:
    state, state_logs = load_state()
    etf_map = load_etf_map()
    try:
        msg = build_message(etf_map, state)
        save_state(state)
        send_telegram(msg)
        print("[OK] Briefing sent.")
        return 0
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:300]}"
        print("[ERROR] " + err, file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        try:
            kst = now_kst().strftime("%Y-%m-%d %H:%M:%S KST")
            text = f"<b>{html.escape(tr('title'))}</b>  <code>{html.escape(tr('status_err'))}</code>\n⏱️ {html.escape(kst)}\n<b>{html.escape(tr('s4_err'))}</b>\n<code>{html.escape(err)}</code>"
            send_telegram(text)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
