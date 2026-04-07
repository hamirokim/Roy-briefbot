"""
M5 리스크 대시보드 — 시장 스냅샷 + VIX 레짐 + 경제 캘린더
================================================================
v3: SPY 거래량(20일 평균 대비) 추가
"""

import json
import os
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from src.utils import now_kst

# ── 환경변수 ─────────────────────────────────────────
VIX_LOW = float(os.getenv("M5_VIX_LOW", "15"))
VIX_HIGH = float(os.getenv("M5_VIX_HIGH", "25"))
VIX_EXTREME = float(os.getenv("M5_VIX_EXTREME", "35"))
VIX_LOOKBACK = int(os.getenv("M5_VIX_LOOKBACK", "10"))
CALENDAR_LOOKAHEAD = int(os.getenv("M5_CAL_LOOKAHEAD", "7"))

_WEEKDAYS_KR = ["월", "화", "수", "목", "금", "토", "일"]
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BriefBot/1.0)"}

_SNAPSHOT_ASSETS = [
    {"yahoo": "SPY", "name": "S&P500(SPY)", "unit": "$", "volume": True},
    {"yahoo": "%5EIXIC", "name": "나스닥", "unit": "", "volume": False},
    {"yahoo": "%5ERUT",  "name": "러셀2000", "unit": "", "volume": False},
    {"yahoo": "%5EDJI",  "name": "다우", "unit": "", "volume": False},
    {"yahoo": "GLD",     "name": "금(GLD)", "unit": "$", "volume": False},
    {"yahoo": "CL%3DF",  "name": "WTI유가", "unit": "$", "volume": False},
    {"yahoo": "USDKRW%3DX", "name": "원/달러", "unit": "₩", "volume": False},
]


# ═══════════════════════════════════════════════════════════
# Yahoo Finance 차트 수집 (종가 + 거래량)
# ═══════════════════════════════════════════════════════════
def _fetch_yahoo_chart(ticker: str, range_str: str = "3mo", interval: str = "1d", _retries: int = 2) -> dict | None:
    """Yahoo Finance chart API → {"closes": [...], "volumes": [...]} 반환. 타임아웃 시 1회 재시도."""
    import time
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_str}&interval={interval}"
    for attempt in range(_retries):
        try:
            resp = requests.get(url, timeout=20, headers=_HEADERS)
            if resp.status_code != 200:
                return None
            data = resp.json()
            result = data.get("chart", {}).get("result", [])
            if not result:
                return None
            quote = result[0].get("indicators", {}).get("quote", [{}])[0]
            closes = quote.get("close", [])
            volumes = quote.get("volume", [])
            valid_closes = [float(c) for c in closes if c is not None]
            valid_volumes = [int(v) if v is not None else 0 for v in volumes]
            if len(valid_closes) < 2:
                return None
            return {"closes": valid_closes, "volumes": valid_volumes}
        except requests.exceptions.Timeout:
            print(f"[M5] Yahoo {ticker} 타임아웃 (시도 {attempt + 1}/{_retries})")
            if attempt < _retries - 1:
                time.sleep(2)
            continue
        except Exception as e:
            print(f"[M5] Yahoo {ticker} 실패: {e}")
            return None
    print(f"[M5] Yahoo {ticker} 재시도 소진")
    return None


# ═══════════════════════════════════════════════════════════
# 시장 스냅샷 수집
# ═══════════════════════════════════════════════════════════
def _fetch_market_snapshot() -> list[dict]:
    results = []
    for asset in _SNAPSHOT_ASSETS:
        chart = _fetch_yahoo_chart(asset["yahoo"], range_str="3mo")
        if not chart:
            print(f"[M5] 스냅샷 수집 실패: {asset['name']}")
            continue

        closes = chart["closes"]
        volumes = chart["volumes"]
        last = closes[-1]
        prev = closes[-2]
        daily_pct = ((last - prev) / prev) * 100

        w_idx = max(0, len(closes) - 6)
        weekly_pct = ((last - closes[w_idx]) / closes[w_idx]) * 100

        m_idx = max(0, len(closes) - 23)
        monthly_pct = ((last - closes[m_idx]) / closes[m_idx]) * 100

        entry = {
            "name": asset["name"],
            "unit": asset["unit"],
            "close": last,
            "daily_pct": round(daily_pct, 2),
            "weekly_pct": round(weekly_pct, 2),
            "monthly_pct": round(monthly_pct, 2),
        }

        # SPY 거래량: 20일 평균 대비 비율
        if asset.get("volume") and len(volumes) >= 21:
            last_vol = volumes[-1]
            avg_vol_20 = sum(volumes[-21:-1]) / 20 if sum(volumes[-21:-1]) > 0 else 1
            vol_ratio = last_vol / avg_vol_20 if avg_vol_20 > 0 else None
            if vol_ratio is not None:
                entry["volume"] = last_vol
                entry["vol_ratio"] = round(vol_ratio, 2)
                entry["vol_avg20"] = int(avg_vol_20)
                print(f"[M5] {asset['name']} 거래량: {last_vol:,} (20일 평균 대비 {vol_ratio:.2f}x)")

        results.append(entry)
        print(f"[M5] 스냅샷: {asset['name']} {last:.2f} (일{daily_pct:+.2f}% 주{weekly_pct:+.2f}%)")

    return results


def _format_snapshot(snapshot: list[dict]) -> str:
    if not snapshot:
        return ""
    lines = ["[시장 스냅샷]"]
    for s in snapshot:
        if s["name"] == "원/달러":
            price_str = f"{s['close']:,.0f}원"
        elif s["unit"] == "$":
            price_str = f"${s['close']:,.2f}"
        else:
            price_str = f"{s['close']:,.2f}"

        line = (
            f"- {s['name']}: {price_str} "
            f"(일간 {s['daily_pct']:+.1f}%, 주간 {s['weekly_pct']:+.1f}%, 월간 {s['monthly_pct']:+.1f}%)"
        )

        # 거래량 (SPY만)
        if "vol_ratio" in s:
            vol_tag = "평균 이상" if s["vol_ratio"] >= 1.0 else "평균 이하"
            line += f" | 거래량 {s['vol_ratio']:.1f}x ({vol_tag})"

        lines.append(line)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# VIX 수집 (기존 유지)
# ═══════════════════════════════════════════════════════════
_VIX_STOOQ_TICKERS = ["^vix", "vix.us"]


def _fetch_vix_stooq(days: int = 10) -> float | None:
    end = datetime.utcnow()
    start = end - timedelta(days=days + 30)
    d1, d2 = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    for ticker in _VIX_STOOQ_TICKERS:
        try:
            url = f"https://stooq.com/q/d/l/?s={ticker}&d1={d1}&d2={d2}&i=d"
            resp = requests.get(url, timeout=15, headers=_HEADERS)
            if resp.status_code != 200:
                continue
            text = resp.text.strip()
            if "No data" in text or "Exceeded" in text or len(text) < 30:
                print(f"[M5] Stooq VIX 데이터 없음/한도초과 ({ticker})")
                continue
            df = pd.read_csv(StringIO(text))
            if df.empty or "Close" not in df.columns:
                continue
            vix_val = float(df["Close"].iloc[-1])
            print(f"[M5] VIX 수집 성공 (Stooq {ticker}): {vix_val:.2f}")
            return vix_val
        except Exception as e:
            print(f"[M5] Stooq VIX 실패 ({ticker}): {e}")
    print("[M5] Stooq VIX 전체 실패 -> Yahoo 폴백")
    return None


def _fetch_vix_yahoo() -> float | None:
    chart = _fetch_yahoo_chart("%5EVIX", range_str="5d")
    if chart and chart["closes"]:
        vix = chart["closes"][-1]
        print(f"[M5] VIX 수집 성공 (Yahoo): {vix:.2f}")
        return vix
    return None


def _fetch_vix(days: int = 10) -> float | None:
    vix = _fetch_vix_stooq(days)
    return vix if vix is not None else _fetch_vix_yahoo()


def _classify_vix(vix: float) -> tuple[str, str]:
    if vix < VIX_LOW:
        return "LOW", "낮은 변동성"
    elif vix < VIX_HIGH:
        return "NORMAL", "보통"
    elif vix < VIX_EXTREME:
        return "HIGH", "높은 변동성 — 경계 구간"
    else:
        return "EXTREME", "극단적 공포 — 역사적 변곡점 가능"


# ═══════════════════════════════════════════════════════════
# 경제 캘린더 (기존 유지)
# ═══════════════════════════════════════════════════════════
def _calendar_path() -> Path:
    base = Path(__file__).resolve().parents[2] / "config"
    year = now_kst().year
    for p in [base / f"calendar_{year}.json", base / "calendar.json"]:
        if p.exists():
            return p
    return base / f"calendar_{year}.json"


def _load_calendar() -> dict:
    path = _calendar_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _get_events_in_range(cal, start_date, end_date):
    events = cal.get("events", [])
    result = []
    for evt in events:
        try:
            d = datetime.strptime(evt["date"], "%Y-%m-%d").date()
            if start_date <= d <= end_date:
                result.append(evt)
        except (ValueError, KeyError):
            continue
    return sorted(result, key=lambda e: e["date"])


def _check_calendar_expiry(cal, today_date):
    meta = cal.get("meta", {})
    expires_str = meta.get("expires")
    if not expires_str:
        return None
    try:
        exp_date = datetime.strptime(expires_str, "%Y-%m-%d").date()
    except ValueError:
        return None
    if today_date > exp_date:
        return "⚠️ 경제 캘린더 만료됨 — 업데이트 필요."
    days_left = (exp_date - today_date).days
    if days_left <= meta.get("warning_days", 14):
        return f"⚠️ 경제 캘린더 업데이트 필요 (D-{days_left})"
    return None


def _format_event(evt):
    marker = "🔴" if evt.get("impact") == "high" else "🟡"
    return f"{marker} {evt.get('name', '?')}"


def _format_event_with_day(evt):
    try:
        wd = _WEEKDAYS_KR[datetime.strptime(evt["date"], "%Y-%m-%d").weekday()]
    except (ValueError, KeyError):
        wd = "?"
    return f"{_format_event(evt)}({wd})"


# ═══════════════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════════════
def run(state: dict) -> dict:
    now = now_kst()
    today = now.date()

    print("[M5] 시장 스냅샷 수집 시작")
    snapshot = _fetch_market_snapshot()
    snapshot_text = _format_snapshot(snapshot)

    vix = _fetch_vix(days=VIX_LOOKBACK)
    vix_lines = []
    vix_val = None
    vix_regime = None
    if vix is not None:
        vix_val = vix
        regime, desc = _classify_vix(vix)
        vix_regime = regime
        vix_lines.append(f"VIX: {vix:.1f} ({regime} 레짐 — {desc})")
        if vix >= 30:
            vix_lines.append("  참고: VIX 30+ 구간. 단기 추가 하락 가능, 장기 분할 매수 검토 구간.")
    else:
        vix_lines.append("VIX: 수집 실패")

    cal_lines = []
    cal = _load_calendar()
    if cal:
        expiry = _check_calendar_expiry(cal, today)
        if expiry:
            cal_lines.append(expiry)
        today_events = _get_events_in_range(cal, today, today)
        if today_events:
            names = [_format_event(e) for e in today_events]
            cal_lines.append(f"⚡ 오늘: {', '.join(names)}")
        week_end = today + timedelta(days=CALENDAR_LOOKAHEAD)
        week_events = _get_events_in_range(cal, today + timedelta(days=1), week_end)
        if week_events:
            parts = [_format_event_with_day(e) for e in week_events]
            cal_lines.append(f"이번 주: {', '.join(parts)}")

    risk_text = "[리스크 데이터]\n" + "\n".join(f"- {l}" for l in vix_lines + cal_lines)
    context_text = snapshot_text + "\n\n" + risk_text if snapshot_text else risk_text

    print(f"[M5] context 완료 (스냅샷 {len(snapshot)}개, VIX {'OK' if vix else 'FAIL'})")

    return {
        "context_text": context_text,
        "snapshot": snapshot,
        "vix": vix_val,
        "vix_regime": vix_regime,
    }
