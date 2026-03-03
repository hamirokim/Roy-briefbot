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

import numpy as np
import pandas as pd
import yfinance as yf


VERSION = "0.5.1"
TELEGRAM_API = "https://api.telegram.org"

ETF_MAP_PATH = Path("config/etf_map.json")
STATE_PATH = Path("data/state.json")

STOOQ_BASE = "https://stooq.com/q/d/l/"
SSGA_HOLDINGS_TMPL = "https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-{}.xlsx"

HANGUL_RE = re.compile(r"[가-힣]")


# -----------------------
# Helpers
# -----------------------
def now_kst() -> datetime:
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9)))


def env(name: str, default: str = "") -> str:
    v = os.getenv(name, default)
    return v.strip() if isinstance(v, str) else default


def env_int(name: str, default: int) -> int:
    try:
        return int(float(env(name, str(default))))
    except Exception:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(env(name, str(default)))
    except Exception:
        return default


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
        "s3_note": "※ 후보는 'ENTRY(100/50) 맹신'이 아니라 '메인지표 준비도(arm) + 최근 트리거(WT/MFI/BB)' 기반. 최종 진입은 TradingView 4H 메인지표로 확인.",

        "s1": "S1. 오늘 체크(제목 기반 요약)",
        "s1_note": "※ 본문 요약이 아니라 제목 키워드로 '리스크/이벤트'만 압축. (원문 클릭은 선택)",
        "no_news": "• (시장 관련 헤드라인 없음)",

        "s4_log": "S4. 로그",
        "s4_err": "S4. 에러",
        "state_missing": "• state.json이 없어 새로 생성(정상)",
    }
    return ko.get(key, key)


def truncate_telegram(text: str, limit: int = 3900) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…(truncated)"


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


def prune_state(state: dict) -> None:
    max_links = env_int("STATE_MAX_LINKS", 1500)
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
# ETF map / holdings
# -----------------------
def load_etf_map() -> dict:
    fallback = {"benchmark": ["ACWI"], "sectors_11": [], "countries_regions_16": {"developed": [], "emerging": []}}
    try:
        with ETF_MAP_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


def fetch_spdr_holdings(etf_ticker: str, timeout: int = 12) -> List[dict]:
    t = etf_ticker.strip().lower()
    url = SSGA_HOLDINGS_TMPL.format(t)
    headers = {"User-Agent": env("USER_AGENT", "RoyBriefbot/0.5.1 (+GitHub Actions)")}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()

    wb = load_workbook(filename=BytesIO(resp.content), read_only=True, data_only=True)
    ws = wb.active

    header_row = None
    col_ticker = None
    col_name = None
    col_weight = None

    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=80, values_only=True), start=1):
        if not row:
            continue
        norm = [str(c).strip().lower() if c is not None else "" for c in row]
        if any(("ticker" in x) or (x == "symbol") for x in norm) and any("weight" in x for x in norm):
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
    blank = 0
    for row in ws.iter_rows(min_row=header_row + 1, max_row=header_row + 5000, values_only=True):
        if not row:
            blank += 1
            if blank >= 20:
                break
            continue

        raw_t = row[col_ticker] if col_ticker < len(row) else None
        raw_w = row[col_weight] if col_weight < len(row) else None
        raw_n = row[col_name] if (col_name is not None and col_name < len(row)) else None

        if raw_t is None or str(raw_t).strip() == "":
            blank += 1
            if blank >= 20:
                break
            continue

        blank = 0
        ticker = str(raw_t).strip().upper()
        if len(ticker) > 15 or not ticker[0].isalpha():
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


# -----------------------
# News (RSS)
# -----------------------
def load_rss_urls() -> List[str]:
    raw = env("RSS_URLS")
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]
    return []


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


def fetch_headlines(rss_urls: List[str], top_n: int = 16, timeout: int = 12, state: Optional[dict] = None) -> Tuple[List[dict], List[str]]:
    items = []
    logs = []
    per_feed = []

    for url in rss_urls:
        try:
            headers = {"User-Agent": env("USER_AGENT", "RoyBriefbot/0.5.1 (+GitHub Actions)")}
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
        filtered = [it for it in dedup if any(k in it["title"].lower() for k in kws)]
        dedup = filtered if len(filtered) >= 3 else dedup

    if env("NEWS_REQUIRE_KOREAN", "1") != "0":
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
    top_k = env_int("NEWS_DIGEST_TOP", 3)

    scored = []
    for h in headlines:
        s, tags, note = news_score(h.get("title", ""))
        scored.append((s, tags, note, h))
    scored.sort(key=lambda x: x[0], reverse=True)

    picked = [x for x in scored if x[0] > 0][:top_k] or scored[:min(top_k, len(scored))]

    lines: List[str] = []
    lines.append(f"<b>{html.escape(tr('s1'))}</b>")
    lines.append(html.escape(tr("s1_note")))
    if not picked:
        lines.append(html.escape(tr("no_news")))
        return lines, []

    used_links: List[str] = []
    for i, (_, tags, note, h) in enumerate(picked, 1):
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

    return lines, used_links


# -----------------------
# S2 (ETF map, daily RS)
# -----------------------
def _stooq_symbol(ticker: str) -> str:
    t = ticker.strip().lower()
    if t.endswith(".us") or t.endswith(".uk") or t.endswith(".jp") or t.endswith(".de") or t.endswith(".pl"):
        return t
    return f"{t}.us"


def _fetch_stooq_daily_ohlcv(ticker: str, timeout: int = 12) -> List[dict]:
    sym = _stooq_symbol(ticker)
    url = f"{STOOQ_BASE}?s={sym}&i=d"
    headers = {"User-Agent": env("USER_AGENT", "RoyBriefbot/0.5.1 (+GitHub Actions)")}
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
                rs[k] = (ret[k] - bench_ret[k]) if (bench_closes and ret.get(k) is not None and bench_ret.get(k) is not None) else None
            rows.append({"ticker": t, "rs": rs})
        except Exception:
            failed.append(t)

    return rows, failed


def pick_top_tracks(rows: List[dict], top_n: int = 3) -> Tuple[List[dict], List[dict]]:
    def score_a(r: dict) -> float:
        rs6 = r["rs"].get("6m"); rs3 = r["rs"].get("3m")
        if rs6 is None or rs3 is None:
            return -1e9
        return 0.6 * rs6 + 0.4 * rs3

    def score_b(r: dict) -> float:
        rs1w = r["rs"].get("1w"); rs1m = r["rs"].get("1m"); rs3m = r["rs"].get("3m")
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
    timeout = env_int("DATA_TIMEOUT", 12)

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
# 4H main-indicator replica: WT/MFI/BB arms + buy triggers
# -----------------------
def _ema(series: np.ndarray, n: int) -> np.ndarray:
    if n <= 1:
        return series.astype(float)
    alpha = 2.0 / (n + 1.0)
    out = np.empty_like(series, dtype=float)
    out[:] = np.nan
    acc = float(series[0])
    out[0] = acc
    for i in range(1, len(series)):
        acc = alpha * float(series[i]) + (1 - alpha) * acc
        out[i] = acc
    return out


def _sma(series: np.ndarray, n: int) -> np.ndarray:
    if n <= 1:
        return series.astype(float)
    return pd.Series(series).rolling(n, min_periods=n).mean().to_numpy(dtype=float)


def _stdev(series: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(series).rolling(n, min_periods=n).std(ddof=0).to_numpy(dtype=float)


def _mfi(high: np.ndarray, low: np.ndarray, close: np.ndarray, vol: np.ndarray, n: int) -> np.ndarray:
    tp = (high + low + close) / 3.0
    mf = tp * vol
    pos = np.zeros_like(tp, dtype=float)
    neg = np.zeros_like(tp, dtype=float)
    for i in range(1, len(tp)):
        if tp[i] > tp[i - 1]:
            pos[i] = mf[i]
        elif tp[i] < tp[i - 1]:
            neg[i] = mf[i]
    pos_sum = pd.Series(pos).rolling(n, min_periods=n).sum().to_numpy(dtype=float)
    neg_sum = pd.Series(neg).rolling(n, min_periods=n).sum().to_numpy(dtype=float)
    mfi = np.full_like(tp, np.nan, dtype=float)
    for i in range(len(tp)):
        if np.isnan(pos_sum[i]) or np.isnan(neg_sum[i]):
            continue
        if neg_sum[i] == 0:
            mfi[i] = 100.0
        else:
            r = pos_sum[i] / neg_sum[i]
            mfi[i] = 100.0 - (100.0 / (1.0 + r))
    return mfi


def normalize_yahoo_ticker(t: str) -> str:
    # Yahoo uses '-' instead of '.' for class shares (BRK.B -> BRK-B)
    t = (t or "").strip().upper()
    t = t.replace(".", "-")
    t = t.replace("/", "-")
    t = t.replace(" ", "")
    return t


def yf_fetch_1h(ticker: str, period: str, interval: str) -> Tuple[Optional[pd.DataFrame], str]:
    """
    Returns (df, used_symbol). df columns: open/high/low/close/volume in lower-case.
    """
    sym = normalize_yahoo_ticker(ticker)
    try:
        tk = yf.Ticker(sym)
        df = tk.history(period=period, interval=interval, auto_adjust=False, prepost=False)
        if df is None or df.empty:
            return None, sym
        # standardize
        df = df.rename(columns={c: str(c).lower() for c in df.columns})
        need = ["open", "high", "low", "close", "volume"]
        if not all(k in df.columns for k in need):
            return None, sym
        df = df[need].dropna()
        if len(df) < 80:
            return None, sym
        return df, sym
    except Exception:
        return None, sym


def resample_4h(df_1h: pd.DataFrame) -> Optional[pd.DataFrame]:
    try:
        df = df_1h.copy()
        df.index = pd.to_datetime(df.index)
        agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        df4 = df.resample("4H").agg(agg).dropna()
        if len(df4) < 80:
            return None
        return df4
    except Exception:
        return None


def compute_main_setup(df4: pd.DataFrame) -> Optional[dict]:
    """
    Approx replicate MAIN indicator for scanning:
    - WT arm_dn + buy trigger
    - MFI arm_low + buy trigger
    - BB buy armed + buy trigger
    We DO NOT use ST/TTL execution logic here. TTL is only 'recent buy cluster count'.
    """
    wt_n1 = env_int("WT_N1", 24)
    wt_n2 = env_int("WT_N2", 41)
    wt_n3 = env_int("WT_N3", 5)
    wt_ob = env_float("WT_OB", 50.5)
    wt_os = env_float("WT_OS", -41.0)

    mfi_len = env_int("MFI_LEN", 11)
    mfi_smooth = env_int("MFI_SMOOTH", 6)
    mfi_linger = env_int("MFI_LINGER", 1)
    mfi_ob = env_float("MFI_OB", 68.0)
    mfi_os = env_float("MFI_OS", 32.0)

    bb_len = env_int("BB_LEN", 20)
    bb_mult = env_float("BB_MULT", 2.2)
    bb_rein = max(env_int("BB_REIN", 2), 1)
    bb_reentry = env_int("BB_REENTRY_BARS", 6)

    ttl = env_int("TTL_CLUSTER", 3)

    h = df4["high"].to_numpy(dtype=float)
    l = df4["low"].to_numpy(dtype=float)
    c = df4["close"].to_numpy(dtype=float)
    v = df4["volume"].to_numpy(dtype=float)

    n = len(c)
    if n < 120:
        return None

    # WT
    src = (h + l + c) / 3.0
    esa = _ema(src, wt_n1)
    d = _ema(np.abs(src - esa), wt_n1)
    ci = (src - esa) / (0.015 * np.where(d == 0, np.nan, d))
    tci = _ema(ci, wt_n2)
    sig = _sma(tci, wt_n3)

    # MFI
    mfi_raw = _mfi(h, l, c, v, mfi_len)
    mfi_val = mfi_raw if mfi_smooth <= 1 else _sma(mfi_raw, mfi_smooth)

    # BB
    bb_basis = _sma(c, bb_len)
    bb_dev = _stdev(c, bb_len) * bb_mult
    bb_up = bb_basis + bb_dev
    bb_dn = bb_basis - bb_dev

    # state vars
    wt_arm_dn = False
    sig_wt_buy = False
    last_wt_buy = None

    mfi_armL = False
    mfi_armL_age = 0
    mfi_allow_buy = True
    sig_mfi_buy = False
    last_mfi_buy = None

    bb_buy_armed = False
    bb_buy_in_cnt = 0
    bb_buy_age = 0
    sig_bb_buy = False
    last_bb_buy = None

    for i in range(n):
        if np.isnan(tci[i]) or np.isnan(sig[i]) or np.isnan(mfi_val[i]) or np.isnan(bb_dn[i]) or np.isnan(bb_up[i]):
            continue
        confirmed = True

        # WT arm + buy
        sig_wt_buy = False
        wt_touch_bot = tci[i] <= wt_os
        wt_cross_up = (tci[i-1] <= sig[i-1]) and (tci[i] > sig[i]) if i > 0 and not np.isnan(tci[i-1]) and not np.isnan(sig[i-1]) else False
        wt_touch_top = tci[i] >= wt_ob
        wt_cross_dn = (tci[i-1] >= sig[i-1]) and (tci[i] < sig[i]) if i > 0 and not np.isnan(tci[i-1]) and not np.isnan(sig[i-1]) else False

        if confirmed:
            if wt_touch_bot:
                wt_arm_dn = True
            if wt_touch_top and wt_cross_dn:
                wt_arm_dn = False
            if wt_arm_dn and wt_cross_up:
                sig_wt_buy = True
                wt_arm_dn = False

        if sig_wt_buy:
            last_wt_buy = i

        # MFI arm + buy (pivot up)
        sig_mfi_buy = False
        zone_low = mfi_val[i] <= mfi_os
        zone_high = mfi_val[i] >= mfi_ob

        pivot_up = False
        if i >= 2 and not np.isnan(mfi_val[i-2]) and not np.isnan(mfi_val[i-1]):
            d_prev = mfi_val[i-1] - mfi_val[i-2]
            d_now = mfi_val[i] - mfi_val[i-1]
            pivot_up = (d_prev < 0) and (d_now > 0)

        if confirmed:
            if zone_low:
                mfi_armL = True
                mfi_armL_age = 0
                mfi_allow_buy = True
            elif mfi_armL and (not zone_low):
                mfi_armL_age += 1
                if mfi_armL_age > mfi_linger:
                    mfi_armL = False
                    mfi_armL_age = 0

            # (sell side omitted)

            if mfi_armL and mfi_allow_buy and pivot_up:
                sig_mfi_buy = True
                mfi_allow_buy = False
                mfi_armL = False
                mfi_armL_age = 0

            if zone_high:
                # reset buy permission around extremes
                mfi_allow_buy = True

        if sig_mfi_buy:
            last_mfi_buy = i

        # BB arm + buy (re-in)
        sig_bb_buy = False
        if confirmed:
            touch_dn = (l[i] <= bb_dn[i]) and (bb_dn[i] <= h[i])
            outside_dn = c[i] < bb_dn[i]
            inside_close = (c[i] >= bb_dn[i]) and (c[i] <= bb_up[i])

            if (not bb_buy_armed) and (touch_dn or outside_dn):
                bb_buy_armed = True
                bb_buy_in_cnt = 0
                bb_buy_age = 0

            if bb_buy_armed:
                bb_buy_age += 1
                if inside_close:
                    bb_buy_in_cnt += 1
                    if bb_buy_in_cnt >= bb_rein:
                        sig_bb_buy = True
                        bb_buy_armed = False
                        bb_buy_in_cnt = 0
                        bb_buy_age = 0
                else:
                    bb_buy_in_cnt = 0

                if bb_buy_armed and (bb_buy_age >= bb_reentry):
                    bb_buy_armed = False
                    bb_buy_in_cnt = 0
                    bb_buy_age = 0

        if sig_bb_buy:
            last_bb_buy = i

    # snapshot at last valid bar
    i = n - 1
    while i > 0 and (np.isnan(tci[i]) or np.isnan(sig[i]) or np.isnan(mfi_val[i]) or np.isnan(bb_dn[i]) or np.isnan(bb_up[i])):
        i -= 1
    if i <= 0:
        return None

    arm_flags = {"WT": bool(wt_arm_dn), "MFI": bool(mfi_armL), "BB": bool(bb_buy_armed)}
    arm_cnt = int(sum(1 for _, v in arm_flags.items() if v))

    def within(last_idx: Optional[int]) -> bool:
        return (last_idx is not None) and (i - last_idx <= ttl)

    buy_cnt = (1 if within(last_wt_buy) else 0) + (1 if within(last_mfi_buy) else 0) + (1 if within(last_bb_buy) else 0)

    # rough risk proxy: 4H candle range / close (last bar)
    rng = float(max(h[i] - l[i], 0.0))
    atrp = (rng / c[i]) * 100.0 if c[i] > 0 else np.nan

    return {"arm_flags": arm_flags, "arm_cnt": arm_cnt, "buy_cnt": buy_cnt, "atrp4h": atrp, "bars_4h": int(n)}


# -----------------------
# S3: Candidate selection
# -----------------------
def daily_prefilter(ticker: str) -> Optional[dict]:
    timeout = env_int("DATA_TIMEOUT", 12)
    series = _fetch_stooq_daily_ohlcv(ticker, timeout=timeout)
    if not series or len(series) < 260:
        return None
    closes = _closes(series)
    close = closes[-1]
    if close <= 0:
        return None

    vol20 = sum([x["volume"] for x in series[-20:]]) / 20.0
    dv20 = vol20 * close
    if close < env_float("MIN_PRICE", 5):
        return None
    if dv20 < env_float("MIN_DOLLAR_VOL", 10000000):
        return None

    high252 = max(closes[-252:])
    dd = (close / high252) - 1.0

    dd_soft = env_float("DD_SOFT", -0.12)
    if dd > dd_soft:
        return None

    r5 = _pct_change(closes, 5)
    r21 = _pct_change(closes, 21)

    if env("REQUIRE_1W_POS", "1") != "0":
        if r5 is None or r5 <= 0:
            return None
    if env("REQUIRE_1M_NEG", "1") != "0":
        if r21 is None or r21 >= 0:
            return None

    return {"dd": dd, "r5": r5, "r21": r21, "dv20": dv20}


def build_s3(chosen_etfs: List[str], state: dict) -> Tuple[List[str], List[str], List[dict]]:
    warnings: List[str] = []
    timeout = env_int("DATA_TIMEOUT", 12)

    holdings_per_etf = env_int("S3_HOLDINGS_PER_ETF", 50)
    max_universe = env_int("S3_MAX_UNIVERSE", 200)

    top_n = env_int("S3_TOP_N", 4)
    base_top_n = env_int("S3_BASE_TOP_N", 4)

    cooldown_days = env_int("S3_COOLDOWN_DAYS", 7)

    a_min_arm = env_int("A_MIN_ARM", 2)
    b_min_arm = env_int("B_MIN_ARM", 1)

    dd_hard = env_float("DD_HARD", -0.20)
    dd_soft = env_float("DD_SOFT", -0.12)

    yf_period = env("YF_PERIOD", "120d") or "120d"
    yf_interval = env("YF_INTERVAL", "1h") or "1h"
    yf_sleep = env_float("YF_SLEEP_SEC", 0.2)

    dbg = {
        "etf": 0, "hold": 0, "universe": 0,
        "prefilter_ok": 0, "yf_ok": 0,
        "yf_empty": 0, "yf_short": 0, "yf_err": 0,
        "A": 0, "B": 0, "cooldown_skip": 0
    }
    yf_fail_examples: List[str] = []

    universe: Dict[str, dict] = {}
    for etf in chosen_etfs:
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

    tickers = list(universe.keys())[:max_universe]
    dbg["universe"] = len(tickers)
    if not tickers:
        return [tr("s3_none"), tr("s3_note")], warnings, []

    pre = []
    for t in tickers:
        m = daily_prefilter(t)
        if not m:
            continue
        m["ticker"] = t
        m["name"] = universe[t].get("name", "")
        m["from"] = ",".join(sorted(list(universe[t]["from"])))
        pre.append(m)

    dbg["prefilter_ok"] = len(pre)
    pre.sort(key=lambda x: x["dd"])
    pre = pre[: min(len(pre), 35)]  # cap calls

    A_list: List[dict] = []
    B_list: List[dict] = []

    for it in pre:
        t = it["ticker"]

        if was_recently_recommended(state, t, cooldown_days):
            dbg["cooldown_skip"] += 1
            continue

        df1, sym = yf_fetch_1h(t, period=yf_period, interval=yf_interval)
        if df1 is None:
            dbg["yf_empty"] += 1
            if len(yf_fail_examples) < 6:
                yf_fail_examples.append(f"{t}->{sym}")
            time.sleep(yf_sleep)
            continue

        df4 = resample_4h(df1)
        if df4 is None:
            dbg["yf_short"] += 1
            time.sleep(yf_sleep)
            continue

        setup = compute_main_setup(df4)
        if setup is None:
            dbg["yf_err"] += 1
            time.sleep(yf_sleep)
            continue

        dbg["yf_ok"] += 1

        arm_cnt = setup["arm_cnt"]
        dd = it["dd"]

        is_A = (arm_cnt >= a_min_arm) and (dd <= dd_hard)
        is_B = (arm_cnt >= b_min_arm) and (dd <= dd_soft) and (not is_A)

        # scoring: arm + recent triggers + dd depth + volatility sweet spot
        atrp = setup.get("atrp4h", np.nan)
        vol_pen = 0.0
        if not np.isnan(atrp):
            vol_pen = min(max(abs(atrp - 4.5) / 6.0, 0.0), 1.0)

        dd_score = min(max((-dd) / 0.6, 0.0), 1.0)
        score = 100.0 * (0.50 * (arm_cnt / 3.0) + 0.25 * (setup["buy_cnt"] / 3.0) + 0.20 * dd_score + 0.05 * (1.0 - vol_pen))
        grade = "SSS" if score >= 90 else "SS" if score >= 80 else "S" if score >= 70 else "C"

        rec = {
            "ticker": t,
            "name": it.get("name", ""),
            "from": it.get("from", ""),
            "dd": dd,
            "r5": it.get("r5", None),
            "r21": it.get("r21", None),
            "arm_cnt": arm_cnt,
            "arms": setup["arm_flags"],
            "buy_cnt": setup["buy_cnt"],
            "atrp4h": atrp,
            "score": score,
            "grade": grade,
        }

        if is_A:
            A_list.append(rec)
            dbg["A"] += 1
        elif is_B:
            B_list.append(rec)
            dbg["B"] += 1

        time.sleep(yf_sleep)

    A_list.sort(key=lambda x: x["score"], reverse=True)
    B_list.sort(key=lambda x: x["score"], reverse=True)

    A_pick = A_list[:top_n]
    B_pick = B_list[:base_top_n]

    def fmt_pct(x: Optional[float]) -> str:
        if x is None:
            return "NA"
        sign = "+" if x >= 0 else ""
        return f"{sign}{x:.1f}%"

    def arms_str(arms: Dict[str, bool]) -> str:
        on = [k for k, v in arms.items() if v]
        return "+".join(on) if on else "-"

    lines: List[str] = []
    today_str = now_kst().strftime("%Y-%m-%d")
    hist_items: List[dict] = []

    lines.append(f"<b>{html.escape(tr('s3a'))}</b>")
    if not A_pick:
        lines.append("• (없음)")
    else:
        for i, r in enumerate(A_pick, 1):
            t = r["ticker"]
            name = (r.get("name","") or "").strip()
            name_short = (name[:28] + "…") if len(name) > 28 else name
            ddp = r["dd"] * 100.0
            lines.append(f"{i}) <b>[{r['grade']}] {html.escape(t)}</b> {html.escape(name_short)}")
            lines.append(f"   • arm({r['arm_cnt']}): {html.escape(arms_str(r['arms']))} / 최근 트리거(≤{env_int('TTL_CLUSTER',3)} bars): {r['buy_cnt']}/3")
            lines.append(f"   • 급락(52W): {ddp:.1f}% / 1W: {fmt_pct(r.get('r5'))} / 1M: {fmt_pct(r.get('r21'))}")
            lines.append(f"   • 리스크(4H): range% {r.get('atrp4h', float('nan')):.1f} / 출처(ETF): {html.escape(r.get('from',''))} / 점수: {r['score']:.0f}")
            hist_items.append({"date_kst": today_str, "ticker": t, "grade": r["grade"], "score": int(r["score"])})

    lines.append("")
    lines.append(f"<b>{html.escape(tr('s3b'))}</b>")
    if not B_pick:
        lines.append("• (없음)")
    else:
        for i, r in enumerate(B_pick, 1):
            t = r["ticker"]
            name = (r.get("name","") or "").strip()
            name_short = (name[:28] + "…") if len(name) > 28 else name
            ddp = r["dd"] * 100.0
            lines.append(f"{i}) <b>[{r['grade']}] {html.escape(t)}</b> {html.escape(name_short)}")
            lines.append(f"   • arm({r['arm_cnt']}): {html.escape(arms_str(r['arms']))} / 최근 트리거(≤{env_int('TTL_CLUSTER',3)} bars): {r['buy_cnt']}/3")
            lines.append(f"   • 급락(52W): {ddp:.1f}% / 1W: {fmt_pct(r.get('r5'))} / 1M: {fmt_pct(r.get('r21'))}")
            lines.append(f"   • 리스크(4H): range% {r.get('atrp4h', float('nan')):.1f} / 출처(ETF): {html.escape(r.get('from',''))} / 점수: {r['score']:.0f}")

    lines.append(tr("s3_note"))

    if hist_items:
        add_candidate_history(state, hist_items)

    if env("DEBUG_S3", "0") != "0":
        warnings.append(
            "S3 스캔: "
            f"ETF={dbg['etf']}, holdings={dbg['hold']}, universe={dbg['universe']}, "
            f"prefilter={dbg['prefilter_ok']}, yfinance_ok={dbg['yf_ok']}, "
            f"yf_empty={dbg['yf_empty']}, yf_short={dbg['yf_short']}, yf_err={dbg['yf_err']}, "
            f"A={dbg['A']}, B={dbg['B']}, cooldown_skip={dbg['cooldown_skip']}"
        )
        if yf_fail_examples:
            warnings.append("yfinance 빈 데이터 예시: " + ", ".join(yf_fail_examples[:6]))

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

    # S2
    sector_a: List[str] = []
    sector_b: List[str] = []
    country_a: List[str] = []
    country_b: List[str] = []
    try:
        sector_a, sector_b, country_a, country_b, w = compute_s2_picks(etf_map)
        logs.extend(w)
        lines.extend(build_s2_section(etf_map, sector_a, sector_b, country_a, country_b))
        lines.append("")
    except Exception:
        logs.append("S2 failed")

    # S3: use sector A 1 + sector B 1
    chosen: List[str] = []
    if sector_a:
        chosen.append(sector_a[0])
    if sector_b and sector_b[0] not in chosen:
        chosen.append(sector_b[0])

    try:
        s3_lines, w, _ = build_s3(chosen, state)
        logs.extend(w)
        lines.extend(s3_lines)
        lines.append("")
    except Exception:
        lines.append(tr("s3_none"))
        logs.append("S3 failed")
        print(traceback.format_exc(), file=sys.stderr)

    # S1
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
        for w in logs[:12]:
            lines.append(f"• {html.escape(w)}")

    return truncate_telegram("\n".join(lines))


def main() -> int:
    state, _ = load_state()
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
