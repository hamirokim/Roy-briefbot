"""
M5 리스크 대시보드 — 시장 스냅샷 + VIX 레짐 + 경제 캘린더
================================================================
v2: 시장 스냅샷 추가 (주요 지수/자산 일간·주간 변동률)
원칙: 팩트만 전달. 판단은 GPT.
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

# ── 시장 스냅샷 자산 목록 (Yahoo Finance 티커) ──────────
_SNAPSHOT_ASSETS = [
    {"yahoo": "%5EGSPC", "name": "S&P500", "unit": ""},
    {"yahoo": "%5EIXIC", "name": "나스닥", "unit": ""},
    {"yahoo": "%5ERUT",  "name": "러셀2000", "unit": ""},
    {"yahoo": "%5EDJI",  "name": "다우", "unit": ""},
    {"yahoo": "GLD",     "name": "금(GLD)", "unit": "$"},
    {"yahoo": "CL%3DF",  "name": "WTI유가", "unit": "$"},
    {"yahoo": "USDKRW%3DX", "name": "원/달러", "unit": "₩"},
]


# ═══════════════════════════════════════════════════════════
# Yahoo Finance 범용 차트 수집
# ═══════════════════════════════════════════════════════════
def _fetch_yahoo_chart(ticker: str, range_str: str = "3mo", interval: str = "1d") -> list[float] | None:
    """Yahoo Finance chart API → 종가 리스트 반환. 최신이 마지막."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_str}&interval={interval}"
    try:
        resp = requests.get(url, timeout=15, headers=_HEADERS)
        if resp.status_code != 200:
            return None
        data = resp.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
        valid = [float(c) for c in closes if c is not None]
        return valid if len(valid) >= 2 else None
    except Exception as e:
        print(f"[M5] Yahoo {ticker} 실패: {e}")
        return None


# ═══════════════════════════════════════════════════════════
# 시장 스냅샷 수집
# ═══════════════════════════════════════════════════════════
def _fetch_market_snapshot() -> list[dict]:
    """주요 자산 시장 스냅샷 수집. 일간/주간/월간 변동률 계산."""
    results = []
    for asset in _SNAPSHOT_ASSETS:
        closes = _fetch_yahoo_chart(asset["yahoo"], range_str="3mo")
        if not closes or len(closes) < 2:
            print(f"[M5] 스냅샷 수집 실패: {asset['name']}")
            continue

        last = closes[-1]
        prev = closes[-2]
        daily_pct = ((last - prev) / prev) * 100

        # 주간: ~5영업일 전
        w_idx = max(0, len(closes) - 6)
        weekly_pct = ((last - closes[w_idx]) / closes[w_idx]) * 100

        # 월간: ~22영업일 전
        m_idx = max(0, len(closes) - 23)
        monthly_pct = ((last - closes[m_idx]) / closes[m_idx]) * 100

        results.append({
            "name": asset["name"],
            "unit": asset["unit"],
            "close": last,
            "daily_pct": round(daily_pct, 2),
            "weekly_pct": round(weekly_pct, 2),
            "monthly_pct": round(monthly_pct, 2),
        })
        print(f"[M5] 스냅샷: {asset['name']} {last:.2f} (일{daily_pct:+.2f}% 주{weekly_pct:+.2f}%)")

    return results


def _format_snapshot(snapshot: list[dict]) -> str:
    """스냅샷 데이터 → context 텍스트."""
    if not snapshot:
        return ""
    lines = ["[시장 스냅샷]"]
    for s in snapshot:
        unit = s["unit"]
        if s["name"] == "원/달러":
            price_str = f"{s['close']:,.0f}원"
        elif unit == "$":
            price_str = f"${s['close']:,.2f}"
        else:
            price_str = f"{s['close']:,.2f}"
        lines.append(
            f"- {s['name']}: {price_str} "
            f"(일간 {s['daily_pct']:+.1f}%, 주간 {s['weekly_pct']:+.1f}%, 월간 {s['monthly_pct']:+.1f}%)"
        )
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
    print("[M5] Stooq VIX 전체 실패 -> Yahoo Finance 폴백 시도")
    return None


def _fetch_vix_yahoo() -> float | None:
    closes = _fetch_yahoo_chart("%5EVIX", range_str="5d")
    if closes:
        vix = closes[-1]
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
    warning_days = meta.get("warning_days", 14)
    cal_year = meta.get("year", "??")
    if today_date > exp_date:
        return f"⚠️ 경제 캘린더 만료됨 — 업데이트 필요."
    days_left = (exp_date - today_date).days
    if days_left <= warning_days:
        return f"⚠️ 경제 캘린더 업데이트 필요 (D-{days_left})"
    return None


def _format_event(evt):
    marker = "🔴" if evt.get("impact") == "high" else "🟡"
    return f"{marker} {evt.get('name', '?')}"


def _format_event_with_day(evt):
    try:
        d = datetime.strptime(evt["date"], "%Y-%m-%d")
        wd = _WEEKDAYS_KR[d.weekday()]
    except (ValueError, KeyError):
        wd = "?"
    return f"{_format_event(evt)}({wd})"


# ═══════════════════════════════════════════════════════════
# 메인 실행 (v2: dict 반환)
# ═══════════════════════════════════════════════════════════
def run(state: dict) -> dict:
    """M5 실행. dict 반환 (context_text + snapshot + vix)."""
    now = now_kst()
    today = now.date()

    # ── 1. 시장 스냅샷 ──
    print("[M5] 시장 스냅샷 수집 시작")
    snapshot = _fetch_market_snapshot()
    snapshot_text = _format_snapshot(snapshot)

    # ── 2. VIX ──
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

    # ── 3. 경제 캘린더 ──
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

    # ── 4. 조립 ──
    risk_text = "[리스크 데이터]\n" + "\n".join(f"- {l}" for l in vix_lines + cal_lines)
    context_text = snapshot_text + "\n\n" + risk_text if snapshot_text else risk_text

    print(f"[M5] context 생성 완료 (스냅샷 {len(snapshot)}개 자산, VIX {'OK' if vix else 'FAIL'})")

    return {
        "context_text": context_text,
        "snapshot": snapshot,
        "vix": vix_val,
        "vix_regime": vix_regime,
    }
