import os
import sys
import time
import json
import html
import traceback
from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional

import requests
import feedparser
from openpyxl import load_workbook


VERSION = "0.4.1"
TELEGRAM_API = "https://api.telegram.org"
ETF_MAP_PATH = Path("config/etf_map.json")

# Free, no-key data source for daily prices (best-effort)
# Stooq daily CSV endpoint: https://stooq.com/q/d/l/?s=spy.us&i=d
STOOQ_BASE = "https://stooq.com/q/d/l/"

# SPDR (SSGA) daily holdings XLSX (free, no-key)
# Example: https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xlk.xlsx
SSGA_HOLDINGS_TMPL = "https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-{}.xlsx"


def now_kst() -> datetime:
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9)))


def env(name: str, default: str = "") -> str:
    v = os.getenv(name, default)
    return v.strip() if isinstance(v, str) else default


def get_lang() -> str:
    # "ko" (default) or "en"
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
        "s3": "S3. 오늘 후보 종목",
        "s3_none": "• 오늘 후보 없음 (조건 미충족/데이터 부족)",
        "s3_note": "※ 후보는 '신호(ENTRY)'가 아니라 '환경(급락+반등기미+리스크)' 기반입니다. 타이밍은 TradingView 4H 지표로 최종 확인.",
        "s1": "S1. 시장 헤드라인",
        "no_news": "• (시장 관련 헤드라인 없음)",
        "s4_log": "S4. 로그",
        "s4_err": "S4. 에러",
        "no_data": "• (데이터 없음)",
        "failed_s2": "• (ETF 지도 계산 실패)",
        "failed_s3": "• (후보 종목 계산 실패)",
    }
    en = {
        "title": "Daily Briefing",
        "status_ok": "OK",
        "status_err": "ERROR",
        "etf_loaded": "ETF map loaded",
        "s2": "S2. ETF Map",
        "benchmark": "Benchmark",
        "source": "Source",
        "sector_a": "Sector A (Sustained)",
        "sector_b": "Sector B (Revival)",
        "country_a": "Country/Region A (Sustained)",
        "country_b": "Country/Region B (Revival)",
        "s3": "S3. Candidates",
        "s3_none": "• No candidates (filters not met / missing data)",
        "s3_note": "Note: candidates are environment-based; timing confirmed on TradingView 4H.",
        "s1": "S1. Market Headlines",
        "no_news": "• (no market-related headlines)",
        "s4_log": "S4. Log",
        "s4_err": "S4. Error",
        "no_data": "• (no data)",
        "failed_s2": "• (failed to compute ETF map)",
        "failed_s3": "• (failed to compute candidates)",
    }
    table = ko if get_lang() == "ko" else en
    return table.get(key, key)


def load_etf_map() -> dict:
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

    # Default = market-oriented, Korean-friendly (no API key)
    return [
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko",
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en",
        "https://www.yonhapnewseconomytv.com/rss/allArticle.xml",
    ]


def _keyword_list() -> List[str]:
    custom = env("NEWS_KEYWORDS")
    if custom:
        return [k.strip() for k in custom.split(",") if k.strip()]
    if get_lang() == "ko":
        return [
            "증시", "주식", "코스피", "코스닥", "나스닥", "S&P", "연준", "금리", "CPI", "PCE",
            "고용", "실업", "국채", "채권", "달러", "환율", "실적", "어닝", "FOMC", "반도체", "AI",
        ]
    return [
        "stock", "market", "S&P", "Nasdaq", "Dow", "Fed", "rate", "CPI", "PCE", "yields",
        "treasury", "dollar", "earnings", "inflation", "recession", "oil", "chip", "AI",
    ]


def fetch_headlines(rss_urls: List[str], top_n: int = 8, timeout: int = 12) -> List[dict]:
    items = []

    for url in rss_urls:
        try:
            headers = {"User-Agent": env("USER_AGENT", "RoyBriefbot/0.4.0 (+GitHub Actions)")}
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()

            feed = feedparser.parse(resp.text)
            source = (feed.feed.get("title") or url).strip()

            for e in feed.entries[: max(top_n, 30)]:
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
        it.pop("_ts", None)
        dedup.append(it)

    use_filter = env("NEWS_FILTER", "1") != "0"
    if use_filter:
        kws = _keyword_list()
        low_kws = [k.lower() for k in kws]
        filtered = []
        for it in dedup:
            t = it["title"].lower()
            if any(k in t for k in low_kws):
                filtered.append(it)
            if len(filtered) >= top_n:
                break
        if len(filtered) >= min(3, top_n):
            return filtered[:top_n]

    return dedup[:top_n]


def truncate_telegram(text: str, limit: int = 3900) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…(truncated)"

# -----------------------
# S1: News digest (title-based, no full-article summary)
# -----------------------
def news_score(title: str) -> Tuple[int, List[str], str]:
    t = (title or "").lower()
    tags: List[str] = []
    score = 0

    def hit(words: List[str], pts: int, tag: str):
        nonlocal score
        if any(w.lower() in t for w in words):
            score += pts
            tags.append(tag)

    hit(["fomc", "fed", "연준"], 5, "🟧통화정책")
    hit(["cpi", "pce", "inflation", "물가"], 5, "🟧물가지표")
    hit(["jobs", "employment", "실업", "고용"], 4, "🟨고용지표")
    hit(["yield", "treasury", "국채", "채권"], 4, "🟨금리/채권")
    hit(["usd", "dollar", "환율", "달러"], 3, "🟨환율")
    hit(["earnings", "guidance", "실적", "어닝", "가이던스"], 4, "🟦실적")
    hit(["vix", "volatility", "변동성"], 4, "🟥변동성")
    hit(["oil", "opec", "유가"], 3, "🟩원자재")
    hit(["war", "전쟁", "제재", "지정학"], 4, "🟥지정학")
    hit(["rebalanc", "리밸런싱", "월마감"], 3, "🟪수급")
    hit(["semiconductor", "chip", "반도체"], 3, "🟦섹터")
    hit(["ai"], 2, "🟦테마")

    if "🟥" in "".join(tags):
        note = "오늘 변동성 리스크 가능. 신규 진입은 보수적으로."
    elif "🟧통화정책" in tags or "🟧물가지표" in tags:
        note = "매크로 이벤트 영향 큼. 포지션/사이즈 점검."
    elif "🟦실적" in tags:
        note = "실적/가이던스 변수. 종목별 갭 리스크 주의."
    elif "🟪수급" in tags:
        note = "수급 이벤트(리밸런싱)로 왜곡 가능."
    else:
        note = "시장 관련 이슈. 필요시 원문 확인."

    tags = sorted(set(tags))
    return score, tags, note


def build_news_digest(headlines: List[dict]) -> List[str]:
    top_k = int(env("NEWS_DIGEST_TOP", "3") or "3")
    show_raw = env("SHOW_RAW_HEADLINES", "0") != "0"

    scored = []
    for h in headlines:
        s, tags, note = news_score(h.get("title", ""))
        scored.append((s, tags, note, h))

    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [x for x in scored if x[0] > 0][:top_k]
    if not picked:
        picked = scored[: min(top_k, len(scored))]

    lines: List[str] = []
    lines.append(f"<b>{html.escape(tr('s1'))}</b>")
    lines.append("※ 기사 내용 요약이 아니라 '제목 키워드'로 중요도/리스크만 분류합니다. (원문 클릭은 선택)")

    if not picked:
        lines.append(html.escape(tr("no_news")))
        return lines

    for i, (s, tags, note, h) in enumerate(picked, 1):
        title = h.get("title", "")
        link = h.get("link", "")
        tag_str = " ".join(tags) if tags else "🟦시장"
        if link:
            lines.append(f'{i}) {tag_str} <a href="{html.escape(link)}">{html.escape(title)}</a>')
        else:
            lines.append(f"{i}) {tag_str} {html.escape(title)}")
        lines.append(f"   • {html.escape(note)}")

    if show_raw:
        lines.append("")
        lines.append("<b>원문 헤드라인</b>")
        for i, h in enumerate(headlines[:8], 1):
            src = html.escape(h.get("source", ""))
            title = html.escape(h.get("title", ""))
            link = h.get("link", "")
            if link:
                lines.append(f'{i}) <a href="{html.escape(link)}">{title}</a> <i>({src})</i>')
            else:
                lines.append(f"{i}) {title} <i>({src})</i>")

    return lines



# -----------------------
# S2: ETF Map Rankings (daily)
# -----------------------
def _stooq_symbol(ticker: str) -> str:
    """
    Stooq uses lowercase and often needs a market suffix.
    For US-listed tickers/ETFs: use ".us"
    """
    t = ticker.strip().lower()
    if t.endswith(".us") or t.endswith(".uk") or t.endswith(".jp") or t.endswith(".de") or t.endswith(".pl"):
        return t
    return f"{t}.us"


def _fetch_stooq_daily_ohlcv(ticker: str, timeout: int = 12) -> List[dict]:
    """Return list of dict: {date, open, high, low, close, volume} ascending by date."""
    sym = _stooq_symbol(ticker)
    url = f"{STOOQ_BASE}?s={sym}&i=d"
    headers = {"User-Agent": env("USER_AGENT", "RoyBriefbot/0.4.0 (+GitHub Actions)")}
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
            out.append(
                {
                    "date": cols[0].strip(),
                    "open": float(cols[1]),
                    "high": float(cols[2]),
                    "low": float(cols[3]),
                    "close": float(cols[4]),
                    "volume": float(cols[5]),
                }
            )
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


def build_etf_rankings(
    tickers: List[str],
    benchmark: str,
    timeout: int = 12,
) -> Tuple[List[dict], List[str]]:
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

            rows.append({"ticker": t, "ret": ret, "rs": rs})
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
    """Return (sector_A, sector_B, country_A, country_B, warnings)."""
    warnings: List[str] = []
    benchmark_list = etf_map.get("benchmark", []) or ["ACWI"]
    benchmark = benchmark_list[0] if benchmark_list else "ACWI"

    sectors = etf_map.get("sectors_11", []) or []
    cr = etf_map.get("countries_regions_16", {}) or {}
    developed = cr.get("developed", []) or []
    emerging = cr.get("emerging", []) or []
    countries = developed + emerging

    timeout = int(env("DATA_TIMEOUT", "12") or "12")

    sector_a: List[str] = []
    sector_b: List[str] = []
    country_a: List[str] = []
    country_b: List[str] = []

    if sectors:
        rows, failed = build_etf_rankings(sectors, benchmark=benchmark, timeout=timeout)
        if failed:
            warnings.append("S2 sectors data missing: " + ", ".join(sorted(set(failed))[:8]) + ("…" if len(set(failed)) > 8 else ""))
        top_a, top_b = pick_top_tracks(rows, top_n=3)
        sector_a = [r["ticker"] for r in top_a]
        sector_b = [r["ticker"] for r in top_b]

    if countries:
        rows, failed = build_etf_rankings(countries, benchmark=benchmark, timeout=timeout)
        if failed:
            warnings.append("S2 countries data missing: " + ", ".join(sorted(set(failed))[:8]) + ("…" if len(set(failed)) > 8 else ""))
        top_a, top_b = pick_top_tracks(rows, top_n=3)
        country_a = [r["ticker"] for r in top_a]
        country_b = [r["ticker"] for r in top_b]

    return sector_a, sector_b, country_a, country_b, warnings


def build_s2_section(etf_map: dict, sector_a: List[str], sector_b: List[str], country_a: List[str], country_b: List[str]) -> List[str]:
    benchmark_list = etf_map.get("benchmark", []) or ["ACWI"]
    benchmark = benchmark_list[0] if benchmark_list else "ACWI"

    lines: List[str] = []
    lines.append(f"<b>{tr('s2')}</b>")
    lines.append(f"<i>{html.escape(tr('benchmark'))}</i>: {html.escape(benchmark)}  <i>{html.escape(tr('source'))}</i>: Stooq (daily)")
    lines.append("")

    # Keep S2 compact (tickers only) since S3 will carry the actionable part.
    if sector_a or sector_b:
        lines.append(f"<b>{tr('sector_a')}</b>")
        lines.extend([f"• {html.escape(t)}" for t in sector_a] or [tr("no_data")])
        lines.append(f"<b>{tr('sector_b')}</b>")
        lines.extend([f"• {html.escape(t)}" for t in sector_b] or [tr("no_data")])
        lines.append("")

    if country_a or country_b:
        lines.append(f"<b>{tr('country_a')}</b>")
        lines.extend([f"• {html.escape(t)}" for t in country_a] or [tr("no_data")])
        lines.append(f"<b>{tr('country_b')}</b>")
        lines.extend([f"• {html.escape(t)}" for t in country_b] or [tr("no_data")])

    return lines


# -----------------------
# S3: Candidates (from top sector ETFs holdings)
# -----------------------
def fetch_spdr_holdings(etf_ticker: str, timeout: int = 12) -> List[dict]:
    """
    Fetch daily holdings for SPDR ETFs via SSGA XLSX.
    Returns list of {ticker, name, weight} sorted by weight desc.
    """
    t = etf_ticker.strip().lower()
    url = SSGA_HOLDINGS_TMPL.format(t)
    headers = {"User-Agent": env("USER_AGENT", "RoyBriefbot/0.4.0 (+GitHub Actions)")}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()

    wb = load_workbook(filename=BytesIO(resp.content), read_only=True, data_only=True)
    ws = wb.active

    header_row = None
    col_ticker = None
    col_name = None
    col_weight = None

    # Find header row (robust)
    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=80, values_only=True), start=1):
        if not row:
            continue
        norm = [str(c).strip().lower() if c is not None else "" for c in row]
        if any("ticker" in x or x == "symbol" for x in norm) and any("weight" in x for x in norm):
            header_row = i
            for j, x in enumerate(norm):
                if col_ticker is None and ("ticker" in x or x == "symbol"):
                    col_ticker = j
                if col_name is None and ("name" == x or "security name" in x or x.endswith("name")):
                    col_name = j
                if col_weight is None and ("weight" in x):
                    col_weight = j
            break

    if header_row is None or col_ticker is None or col_weight is None:
        return []

    out: List[dict] = []
    blank_streak = 0
    for row in ws.iter_rows(min_row=header_row + 1, max_row=header_row + 5000, values_only=True):
        if not row:
            blank_streak += 1
            if blank_streak >= 20:
                break
            continue

        raw_t = row[col_ticker] if col_ticker < len(row) else None
        raw_w = row[col_weight] if col_weight < len(row) else None
        raw_n = row[col_name] if (col_name is not None and col_name < len(row)) else None

        if raw_t is None or str(raw_t).strip() == "":
            blank_streak += 1
            if blank_streak >= 20:
                break
            continue

        blank_streak = 0
        ticker = str(raw_t).strip().upper()

        # Filter obvious non-equity rows
        if len(ticker) > 10:
            continue
        if not ticker[0].isalpha():
            continue

        try:
            weight = float(raw_w)
        except Exception:
            try:
                weight = float(str(raw_w).replace("%", "").strip())
            except Exception:
                continue

        name = str(raw_n).strip() if raw_n is not None else ""
        out.append({"ticker": ticker, "name": name, "weight": weight})

    out.sort(key=lambda x: x.get("weight", 0.0), reverse=True)
    return out


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
        trv = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(trv)
    if len(trs) < 14:
        return None
    return sum(trs[-14:]) / 14.0


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def score_stock(series: List[dict]) -> Optional[dict]:
    closes = _closes(series)
    if len(closes) < 260:
        return None

    close = closes[-1]
    if close <= 0:
        return None

    # Liquidity proxy using Stooq volume
    vol20 = sum([x["volume"] for x in series[-20:]]) / 20.0
    dollar_vol20 = vol20 * close

    min_price = float(env("S3_MIN_PRICE", "5") or "5")
    min_dv = float(env("S3_MIN_DOLLAR_VOL", "20000000") or "20000000")  # $20M/day

    if close < min_price or dollar_vol20 < min_dv:
        return None

    # Drawdown vs 52w high
    high252 = max(closes[-252:])
    dd52 = (close / high252) - 1.0  # negative if below high
    min_dd = float(env("S3_MIN_DD", "-0.15") or "-0.15")  # -15% or deeper
    if dd52 > min_dd:
        return None

    r5 = _pct_change(closes, 5)
    r21 = _pct_change(closes, 21)
    r63 = _pct_change(closes, 63)

    # Rebound signal: short-term positive
    if r5 is None or r5 <= 0:
        return None


    if env("S3_REQUIRE_1M_NEG", "1") != "0":
        if r21 is None or r21 >= 0:
            return None

    low20 = min([x["low"] for x in series[-20:]])
    bounce20 = (close / low20 - 1.0) if low20 > 0 else 999.0
    max_bounce = float(env("S3_MAX_BOUNCE_FROM_20D_LOW", "0.08") or "0.08")
    if bounce20 > max_bounce:
        return None
    # Risk (ATR%)
    a14 = atr14(series)
    if a14 is None:
        return None
    atrpct = (a14 / close) * 100.0
    if atrpct < float(env("S3_MIN_ATR_PCT", "1.5") or "1.5") or atrpct > float(env("S3_MAX_ATR_PCT", "10") or "10"):
        return None

    s20 = sma(closes, 20)
    s50 = sma(closes, 50)
    s200 = sma(closes, 200)
    if s200 is None:
        return None
    if env("S3_REQUIRE_ABOVE_200SMA", "1") != "0" and close <= s200:
        return None

    slope200 = None
    if s200 is not None and len(closes) >= 220:
        s200_prev = sum(closes[-220:-20]) / 200.0
        slope200 = s200 - s200_prev

    pullback = 0.0
    if s50 is not None and close < s50:
        pullback += 0.4
    if slope200 is not None and slope200 > 0:
        pullback += 0.4
    if s200 is not None and close > s200:
        pullback += 0.2
    pullback = clamp(pullback, 0.0, 1.0)

    revival = 0.0
    revival += clamp(r5 / 8.0, 0.0, 1.0)
    if r21 is not None and r21 < 0:
        revival += 0.3
    if s20 is not None and close > s20:
        revival += 0.3
    revival = clamp(revival, 0.0, 1.0)

    dd_score = clamp((-dd52) / 0.4, 0.0, 1.0)
    risk_score = clamp(1.0 - abs(atrpct - 4.0) / 6.0, 0.0, 1.0)

    score = 100.0 * (0.35 * pullback + 0.35 * revival + 0.2 * dd_score + 0.1 * risk_score)

    return {
        "close": close,
        "dd52": dd52,
        "r5": r5,
        "r21": r21,
        "r63": r63,
        "atrpct": atrpct,
        "dollar_vol20": dollar_vol20,
        "bounce20": bounce20,
        "score": score,
    }


def grade(score: float) -> str:
    if score >= 80:
        return "SSS"
    if score >= 65:
        return "SS"
    if score >= 55:
        return "S"
    return "C"


def build_s3_candidates(sector_etfs: List[str]) -> Tuple[List[str], List[str]]:
    warnings: List[str] = []
    timeout = int(env("DATA_TIMEOUT", "12") or "12")

    holdings_per_etf = int(env("S3_HOLDINGS_PER_ETF", "15") or "15")
    top_n = int(env("S3_TOP_N", "3") or "3")
    max_universe = int(env("S3_MAX_UNIVERSE", "60") or "60")

    universe: Dict[str, dict] = {}
    for etf in sector_etfs:
        try:
            hs = fetch_spdr_holdings(etf, timeout=timeout)
            if not hs:
                warnings.append(f"S3 holdings missing: {etf}")
                continue
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
    if not tickers:
        return [], warnings

    scored: List[dict] = []
    cache: Dict[str, List[dict]] = {}
    for t in tickers:
        try:
            series = cache.get(t)
            if series is None:
                series = _fetch_stooq_daily_ohlcv(t, timeout=timeout)
                cache[t] = series
            if not series:
                continue
            m = score_stock(series)
            if not m:
                continue
            m["ticker"] = t
            m["name"] = universe[t].get("name", "")
            m["from"] = ",".join(sorted(list(universe[t]["from"])))
            m["grade"] = grade(m["score"])
            if m["grade"] in ("SSS", "SS", "S"):
                scored.append(m)
        except Exception:
            continue

    scored.sort(key=lambda x: x["score"], reverse=True)
    scored = scored[:top_n]

    lines: List[str] = []
    if not scored:
        return [tr("s3_none"), tr("s3_note")], warnings

    for i, m in enumerate(scored, 1):
        t = m["ticker"]
        g = m["grade"]
        name = m.get("name", "").strip()
        name_short = (name[:28] + "…") if len(name) > 28 else name
        dd = m["dd52"] * 100.0
        lines.append(f"{i}) <b>[{g}] {html.escape(t)}</b> {html.escape(name_short)}")
        lines.append(
            f"   • 급락(52주고점 대비): {dd:.1f}% / 1W: {_fmt_pct(m.get('r5'))} / 1M: {_fmt_pct(m.get('r21'))} / ATR%: {m.get('atrpct'):.1f} / 20D저점대비: +{(m.get('bounce20',0.0)*100):.1f}%"
        )
        lines.append(f"   • 출처(섹터ETF): {html.escape(m.get('from',''))} / 점수: {m.get('score'):.0f}")
    lines.append(tr("s3_note"))
    return lines, warnings


def build_message(headlines: List[dict], etf_map: dict, ok: bool = True, error_summary: str = "", include_s2: bool = True, include_s3: bool = True) -> str:
    kst = now_kst().strftime("%Y-%m-%d %H:%M:%S KST")
    sha = env("GITHUB_SHA")
    sha_short = sha[:7] if sha else "local"
    status = tr("status_ok") if ok else tr("status_err")

    benchmark = etf_map.get("benchmark", []) or []
    sectors = etf_map.get("sectors_11", []) or []
    cr = etf_map.get("countries_regions_16", {}) or {}
    developed = cr.get("developed", []) or []
    emerging = cr.get("emerging", []) or []
    countries_cnt = len(developed) + len(emerging)

    lines: List[str] = []
    lines.append(f"<b>{html.escape(tr('title'))}</b>  <code>{html.escape(status)}</code>")
    lines.append(f"⏱️ {html.escape(kst)}")
    lines.append(f"🧩 v{VERSION} / {html.escape(sha_short)}")
    lines.append(f"🗺️ {html.escape(tr('etf_loaded'))}: benchmark={','.join(benchmark)} / sectors={len(sectors)} / countries={countries_cnt}")
    lines.append("")

    warnings: List[str] = []
    sector_a: List[str] = []
    sector_b: List[str] = []
    country_a: List[str] = []
    country_b: List[str] = []

    if include_s2 and ok:
        try:
            sector_a, sector_b, country_a, country_b, w = compute_s2_picks(etf_map)
            warnings.extend(w)
            lines.extend(build_s2_section(etf_map, sector_a, sector_b, country_a, country_b))
            lines.append("")
        except Exception:
            lines.append(f"<b>{html.escape(tr('s2'))}</b>")
            lines.append(html.escape(tr("failed_s2")))
            lines.append("")
            print("[WARN] S2 failed", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)

    if include_s3 and ok:
        try:
            chosen: List[str] = []
            for t in sector_a[:1]:
                if t not in chosen:
                    chosen.append(t)
            for t in sector_b[:1]:
                if t not in chosen:
                    chosen.append(t)

            lines.append(f"<b>{html.escape(tr('s3'))}</b>")
            if chosen:
                s3_lines, w = build_s3_candidates(chosen)
                warnings.extend(w)
                # s3_lines already includes HTML in some lines; keep as-is.
                lines.extend(s3_lines)
            else:
                lines.append(tr("s3_none"))
            lines.append("")
        except Exception:
            lines.append(f"<b>{html.escape(tr('s3'))}</b>")
            lines.append(html.escape(tr("failed_s3")))
            lines.append("")
            print("[WARN] S3 failed", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)

    lines.append(f"<b>{html.escape(tr('s1'))}</b>")
    if not headlines:
        lines.append(html.escape(tr("no_news")))
    else:
        for i, h in enumerate(headlines, 1):
            src = html.escape(h.get("source", ""))
            title = html.escape(h.get("title", ""))
            link = h.get("link", "")
            if link:
                lines.append(f'{i}) <a href="{html.escape(link)}">{title}</a> <i>({src})</i>')
            else:
                lines.append(f"{i}) {title} <i>({src})</i>")

    if warnings and ok:
        lines.append("")
        lines.append(f"<b>{html.escape(tr('s4_log'))}</b>")
        for w in warnings[:6]:
            lines.append(f"• {html.escape(w)}")

    if not ok and error_summary:
        lines.append("")
        lines.append(f"<b>{html.escape(tr('s4_err'))}</b>")
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
    include_s3 = env("INCLUDE_S3", "1") != "0"

    try:
        headlines = fetch_headlines(rss_urls, top_n=top_n)
        msg = build_message(headlines, etf_map=etf_map, ok=True, include_s2=include_s2, include_s3=include_s3)
        send_telegram(msg)
        print("[OK] Briefing sent.")
        return 0

    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:300]}"
        print("[ERROR] " + err, file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)

        try:
            msg = build_message([], etf_map=etf_map, ok=False, error_summary=err, include_s2=False, include_s3=False)
            send_telegram(msg)
            print("[OK] Error notification sent.")
        except Exception:
            print("[FATAL] Also failed to send error notification.", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
