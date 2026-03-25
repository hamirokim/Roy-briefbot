"""
M5 리스크 대시보드 — VIX 레짐 + 경제 캘린더
==============================================
역할: 시장 전체 리스크 수준을 데이터로 요약 → M1 GPT에 context 전달.
원칙: 팩트만 전달. 매수/매도 판단은 GPT가 프롬프트 기반으로 수행.
위치: src/modules/m5_risk.py
"""

import json
import os
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from src.utils import now_kst

# ── 환경변수 (daily.yml에서 오버라이드 가능) ─────────────────
VIX_LOW = float(os.getenv("M5_VIX_LOW", "15"))
VIX_HIGH = float(os.getenv("M5_VIX_HIGH", "25"))
VIX_EXTREME = float(os.getenv("M5_VIX_EXTREME", "35"))
VIX_LOOKBACK = int(os.getenv("M5_VIX_LOOKBACK", "10"))
CALENDAR_LOOKAHEAD = int(os.getenv("M5_CAL_LOOKAHEAD", "7"))

# VIX 티커 후보 (Stooq) — 순서대로 시도
_VIX_TICKERS = ["^vix", "vix.us"]

# 요일 한글
_WEEKDAYS_KR = ["월", "화", "수", "목", "금", "토", "일"]


# ═══════════════════════════════════════════════════════════
# VIX 수집
# ═══════════════════════════════════════════════════════════
def _fetch_vix(days: int = 10) -> float | None:
    """Stooq에서 VIX 최신 종가 수집. ^vix → vix.us 순서로 시도."""
    end = datetime.utcnow()
    start = end - timedelta(days=days + 30)  # 주말/공휴일 여유
    d1 = start.strftime("%Y%m%d")
    d2 = end.strftime("%Y%m%d")

    for ticker in _VIX_TICKERS:
        try:
            url = (
                f"https://stooq.com/q/d/l/"
                f"?s={ticker}&d1={d1}&d2={d2}&i=d"
            )
            resp = requests.get(
                url,
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0 (compatible; BriefBot/1.0)"},
            )
            if resp.status_code != 200:
                print(f"[M5] VIX HTTP {resp.status_code} ({ticker})")
                continue
            if "No data" in resp.text or len(resp.text.strip()) < 20:
                print(f"[M5] VIX 데이터 없음 ({ticker})")
                continue

            df = pd.read_csv(StringIO(resp.text))
            if df.empty or "Close" not in df.columns:
                print(f"[M5] VIX CSV 파싱 실패 ({ticker})")
                continue

            vix_val = float(df["Close"].iloc[-1])
            vix_date = df["Date"].iloc[-1] if "Date" in df.columns else "?"
            print(f"[M5] VIX 수집 성공: {ticker} → {vix_val:.2f} ({vix_date})")
            return vix_val

        except Exception as e:
            print(f"[M5] VIX 시도 실패 ({ticker}): {e}")
            continue

    print("[M5] ⚠️ VIX 수집 전체 실패")
    return None


# ═══════════════════════════════════════════════════════════
# VIX 레짐 분류
# ═══════════════════════════════════════════════════════════
def _classify_vix(vix: float) -> tuple[str, str]:
    """VIX 값 → (레짐명, 설명). 판단 없이 사실만."""
    if vix < VIX_LOW:
        return "LOW", "낮은 변동성"
    elif vix < VIX_HIGH:
        return "NORMAL", "보통"
    elif vix < VIX_EXTREME:
        return "HIGH", "높은 변동성 — 경계 구간"
    else:
        return "EXTREME", "극단적 공포 — 역사적 변곡점 가능"


# ═══════════════════════════════════════════════════════════
# 경제 캘린더
# ═══════════════════════════════════════════════════════════
def _calendar_path() -> Path:
    """calendar JSON 경로. 연도별 파일명."""
    base = Path(__file__).resolve().parents[2] / "config"
    # 현재 연도 파일 우선, 없으면 고정 파일명
    year = now_kst().year
    candidates = [
        base / f"calendar_{year}.json",
        base / "calendar.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]  # 없으면 첫 번째 경로 반환 (에러 메시지용)


def _load_calendar() -> dict:
    """캘린더 JSON 로드. 파일 없으면 빈 dict."""
    path = _calendar_path()
    if not path.exists():
        print(f"[M5] 캘린더 파일 없음: {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[M5] 캘린더 로드 실패: {e}")
        return {}


def _get_events_in_range(
    cal: dict, start_date, end_date
) -> list[dict]:
    """start_date ~ end_date (inclusive) 이벤트 추출, 날짜순 정렬."""
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


def _check_calendar_expiry(cal: dict, today_date) -> str | None:
    """캘린더 만료 경고. 만료 14일 전부터 경고, 만료 후 강한 경고."""
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

    # 이미 만료
    if today_date > exp_date:
        next_year = cal_year + 1 if isinstance(cal_year, int) else "??"
        return (
            f"⚠️ 경제 캘린더 만료됨 — {next_year}년 파일로 업데이트 필요. "
            f"이벤트 데이터 신뢰 불가."
        )

    # 만료 임박
    days_left = (exp_date - today_date).days
    if days_left <= warning_days:
        next_year = cal_year + 1 if isinstance(cal_year, int) else "??"
        return f"⚠️ 경제 캘린더 {next_year}년 업데이트 필요 (D-{days_left})"

    return None


def _format_event(evt: dict) -> str:
    """이벤트 → 표시 문자열. impact에 따라 아이콘."""
    impact = evt.get("impact", "medium")
    marker = "🔴" if impact == "high" else "🟡"
    name = evt.get("name", "?")
    return f"{marker} {name}"


def _format_event_with_day(evt: dict) -> str:
    """이벤트 → 요일 포함 표시 문자열."""
    try:
        d = datetime.strptime(evt["date"], "%Y-%m-%d")
        weekday = _WEEKDAYS_KR[d.weekday()]
    except (ValueError, KeyError):
        weekday = "?"
    return f"{_format_event(evt)}({weekday})"


# ═══════════════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════════════
def run(state: dict) -> str:
    """
    M5 실행 → context_text 반환.
    main.py에서 호출, M1 GPT 프롬프트에 {m5_context}로 주입.
    """
    now = now_kst()
    today = now.date()
    lines = []

    # ── 1. VIX ──────────────────────────────────────────
    vix = _fetch_vix(days=VIX_LOOKBACK)
    if vix is not None:
        regime, desc = _classify_vix(vix)
        lines.append(f"VIX: {vix:.1f} ({regime} 레짐 — {desc})")
        lines.append(
            f"  기준: LOW<{VIX_LOW:.0f} / NORMAL {VIX_LOW:.0f}-{VIX_HIGH:.0f} "
            f"/ HIGH {VIX_HIGH:.0f}-{VIX_EXTREME:.0f} / EXTREME {VIX_EXTREME:.0f}+"
        )
        # VIX 30+ 양면성 팩트 (판단은 GPT가 한다)
        if vix >= 30:
            lines.append(
                "  참고: VIX 30+ 구간 진입 후 12개월 S&P500 수익률은 "
                "역사적으로 양호하나, 단기 추가 하락 가능성 공존."
            )
    else:
        lines.append("VIX: 수집 실패 — 데이터 없음")

    # ── 2. 경제 캘린더 ──────────────────────────────────
    cal = _load_calendar()
    if cal:
        # 만료 경고
        expiry_msg = _check_calendar_expiry(cal, today)
        if expiry_msg:
            lines.append(expiry_msg)

        # 오늘 이벤트
        today_events = _get_events_in_range(cal, today, today)
        if today_events:
            names = [_format_event(e) for e in today_events]
            lines.append(
                f"⚡ 오늘: {', '.join(names)} — 발표 전후 변동성 주의"
            )

        # 이번 주 이벤트 (내일 ~ lookahead일 후)
        tomorrow = today + timedelta(days=1)
        week_end = today + timedelta(days=CALENDAR_LOOKAHEAD)
        week_events = _get_events_in_range(cal, tomorrow, week_end)
        if week_events:
            parts = [_format_event_with_day(e) for e in week_events]
            lines.append(f"이번 주 예정: {', '.join(parts)}")

        if not today_events and not week_events:
            lines.append("이번 주 이벤트: 주요 예정 없음")
    else:
        lines.append("경제 캘린더: 파일 없음 — config/calendar_2026.json 확인")

    # ── 조립 ────────────────────────────────────────────
    context = "[리스크 데이터]\n" + "\n".join(f"- {line}" for line in lines)
    print(f"[M5] context 생성 완료 ({len(lines)}줄)")
    return context
