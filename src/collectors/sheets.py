"""Google Sheets 연동 — gspread 기반. src/collectors/sheets.py에 배치.

D91 박제 추가 (2026-04-30): SCOUT 후보발굴 + SCOUT 통계 시트 자동 적재.
- save_candidates_eval(): SCOUT 결과 시트 1행 적재 (시트 없으면 자동 생성)
- read_positions_for_mapping(): POSITIONS → ticker:position_id dict (자동 매핑용)
- update_followup_prices(): m6_history 활용 D+5 / D+28 가격 자동 채움
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SPREADSHEET_ID = os.environ.get(
    "GOOGLE_SHEETS_ID",
    "1JRw_UKcofejBdEmypQ-FN-cMUvDD-pEywCpnH_g3yZo",
)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    creds_json = os.environ.get("GOOGLE_CREDENTIALS", "")
    if not creds_json:
        raise RuntimeError("GOOGLE_CREDENTIALS 환경변수 없음")

    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    _client = gspread.authorize(creds)
    return _client


def get_sheet(sheet_name: str):
    """특정 시트 워크시트 반환."""
    client = _get_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    return spreadsheet.worksheet(sheet_name)


# ═══════════════════════════════════════════════════════════
# POSITIONS 읽기 (M4용)
# ═══════════════════════════════════════════════════════════
def read_positions() -> list[dict]:
    """POSITIONS 시트에서 OPEN 포지션 → portfolio.json 호환 형식으로 반환."""
    ws = get_sheet("POSITIONS 포지션")
    all_data = ws.get_all_values()
    if len(all_data) < 3:
        return []

    # Row 1=headers, Row 2=descriptions, Row 3+=data
    # A=id, B=ticker, C=status, D=entryDate, F=sl1, G=sl2,
    # Q=avgPrice(16), Y=memo(24)
    positions = []
    for row in all_data[2:]:
        if len(row) < 7 or not row[1]:
            continue
        if row[2] != "OPEN":
            continue

        ticker_raw = row[1].strip().upper()
        stooq_ticker = ticker_raw.lower() + ".us"

        positions.append({
            "ticker": stooq_ticker,
            "status": "OPEN",
            "added": row[3] if len(row) > 3 else "",
            "entry_price": _safe_float(row[16]) if len(row) > 16 else None,
            "entry_date": row[3] if len(row) > 3 else "",
            "sl_price": _safe_float(row[5]),
            "memo": row[24] if len(row) > 24 else "",
        })

    return positions


# ═══════════════════════════════════════════════════════════
# BRIEFING 저장 (M1용)
# ═══════════════════════════════════════════════════════════
def save_briefing(date_str: str, briefing_text: str, mode: str = "daily"):
    """BRIEFING 시트에 브리핑 저장. 시트 없으면 생성."""
    client = _get_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    # 시트 존재 확인, 없으면 생성
    try:
        ws = spreadsheet.worksheet("BRIEFING 브리핑")
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title="BRIEFING 브리핑", rows=500, cols=3)
        ws.update("A1:C1", [["날짜", "모드", "브리핑"]])
        logger.info("BRIEFING 시트 자동 생성 완료")

    # 다음 빈 행 찾기
    all_data = ws.get_all_values()
    next_row = len(all_data) + 1
    if next_row < 2:
        next_row = 2

    ws.update(f"A{next_row}:C{next_row}", [[date_str, mode, briefing_text]])
    logger.info("브리핑 Sheets 저장: row %d (%d자)", next_row, len(briefing_text))


def _safe_float(val):
    try:
        return float(val) if val else None
    except (ValueError, TypeError):
        return None


def _fmt_pct(val: str) -> str:
    """소수(0.72) → '72.0%' 변환. 실패 시 '–'."""
    try:
        return f"{float(val) * 100:.1f}%" if val else "–"
    except (ValueError, TypeError):
        return "–"


def _fmt_r(val: str) -> str:
    """R배수 포맷. 실패 시 '–'."""
    try:
        return f"{float(val):+.2f}R" if val else "–"
    except (ValueError, TypeError):
        return "–"


def _fmt_cnt(val: str) -> str:
    """건수 포맷."""
    try:
        return f"{int(float(val))}건" if val else "0건"
    except (ValueError, TypeError):
        return "0건"


def _row_val(all_data: list, row_idx: int, col: int) -> str:
    """안전한 셀 값 접근."""
    try:
        return all_data[row_idx][col] if len(all_data) > row_idx and len(all_data[row_idx]) > col else ""
    except (IndexError, TypeError):
        return ""


# ═══════════════════════════════════════════════════════════
# ANALYTICS 읽기 (M1 피드백 루프용)
# ═══════════════════════════════════════════════════════════
def read_analytics(min_closed: int = 10) -> str:
    """ANALYTICS 시트 → GPT context 텍스트 반환.

    CLOSED 건수가 min_closed 미만이면 빈 문자열 반환 (게이트).
    weekly/monthly 브리핑에서만 호출됨.
    """
    try:
        ws = get_sheet("ANALYTICS 분석")
        all_data = ws.get_all_values()
    except Exception as e:
        logger.warning("ANALYTICS 읽기 실패: %s", e)
        return ""

    if len(all_data) < 9:
        return ""

    # Row 4 (index 3) col B = CLOSED 건수
    closed_raw = _row_val(all_data, 3, 1)
    try:
        closed_count = int(float(closed_raw)) if closed_raw else 0
    except (ValueError, TypeError):
        closed_count = 0

    if closed_count < min_closed:
        logger.info("ANALYTICS 스킵: CLOSED %d건 < %d건", closed_count, min_closed)
        return ""

    lines = [f"[RONIN 지표 성과 — CLOSED {closed_count}건]", ""]

    # ── 전체 성과 (row 2~9, index 1~8) ──
    lines.append("■ 전체 성과")
    for i in range(1, min(9, len(all_data))):
        label = _row_val(all_data, i, 0)
        val = _row_val(all_data, i, 1)
        if not label or val == "":
            continue
        if label == "승률":
            val = _fmt_pct(val)
        lines.append(f"  {label}: {val}")

    # ── CONF별 (row 12~14, index 11~13) ──
    if len(all_data) > 13:
        lines.append("")
        lines.append("■ CONF별 성과 (승률 / 평균R)")
        for i in range(11, min(15, len(all_data))):
            label = _row_val(all_data, i, 0)
            if not label:
                continue
            wr = _row_val(all_data, i, 1)
            ar = _row_val(all_data, i, 2)
            if wr or ar:
                lines.append(f"  {label}: {_fmt_pct(wr)} / {_fmt_r(ar)}")

    # ── Base 구간별 (row 17~18, index 16~17) ──
    if len(all_data) > 17:
        lines.append("")
        lines.append("■ Base 구간별 성과 (승률 / 평균R)")
        for i in range(16, min(19, len(all_data))):
            label = _row_val(all_data, i, 0)
            if not label:
                continue
            wr = _row_val(all_data, i, 1)
            ar = _row_val(all_data, i, 2)
            if wr or ar:
                lines.append(f"  {label}: {_fmt_pct(wr)} / {_fmt_r(ar)}")

    # ── 청산사유별 (row 21~24, index 20~23) ──
    if len(all_data) > 23:
        lines.append("")
        lines.append("■ 청산사유별 분포 (건수 / 평균R)")
        for i in range(20, min(25, len(all_data))):
            label = _row_val(all_data, i, 0)
            if not label:
                continue
            cnt = _row_val(all_data, i, 1)
            ar = _row_val(all_data, i, 2)
            if cnt or ar:
                lines.append(f"  {label}: {_fmt_cnt(cnt)} / {_fmt_r(ar)}")

    # ── Gate별 (row 27~30, index 26~29) ──
    if len(all_data) > 29:
        lines.append("")
        lines.append("■ Gate별 성과 (승률 / 평균R)")
        for i in range(26, min(31, len(all_data))):
            label = _row_val(all_data, i, 0)
            if not label:
                continue
            wr = _row_val(all_data, i, 1)
            ar = _row_val(all_data, i, 2)
            if wr or ar:
                lines.append(f"  {label}: {_fmt_pct(wr)} / {_fmt_r(ar)}")

    result = "\n".join(lines)
    logger.info("ANALYTICS 로드 완료: %d자", len(result))
    return result


# ═══════════════════════════════════════════════════════════
# ════════════ SCOUT 후보발굴 + 통계 시트 (D91, 2026-04-30) ════════════
# ═══════════════════════════════════════════════════════════

# SCOUT 후보발굴 시트 헤더 (21 컬럼)
SCOUT_CANDIDATES_HEADERS = [
    "No",          # A: 자동 (=ROW()-2)
    "발생일",       # B: KST YYYY-MM-DD
    "티커",         # C: NKE
    "국가",         # D: US/KR/JP/CN
    "Score",       # E: Track A 0~5
    "별점",         # F: ★/★★/★★★
    "Summary",     # G: LLM 한 줄 (15자)
    "Industry",    # H: LLM 산업 분류
    "Catalyst",    # I: LLM catalyst
    "Q1 왜",        # J: q1_why
    "Q2 누가",      # K: q2_who
    "Q3 공간",      # L: q3_space
    "Risk Flags",  # M: risk_flags join
    "발생가($)",     # N: yfinance close
    "+5d 가($)",    # O: yfinance D+5 (follow-up)
    "+5d %",       # P: 자동 (=(O-N)/N)
    "+28d 가($)",   # Q: yfinance D+28 (follow-up)
    "+28d %",      # R: 자동 (=(Q-N)/N)
    "방향 적중",     # S: O/X/△ (D+28 후 자동 판정)
    "진입여부",      # T: Position ID 또는 빈 (POSITIONS 매핑 자동)
    "Model",       # U: gpt-5.4-mini 등 모델 버전
]

# SCOUT 통계 시트 셀 박제 (수식 자동)
def _build_scout_stats_layout():
    """통계 시트 초기 박제용 [(셀, 값)] 리스트 반환.

    표본 0 상태에서도 깨지지 않도록 IFERROR로 감쌈.
    'SCOUT 후보발굴'!C3:C = 티커 컬럼 = COUNTA 기준
    """
    SC = "'SCOUT 후보발굴'"  # 시트 이름 (작은따옴표 필수, 공백 포함)
    return [
        # ── 헤더 ──
        ("A1", "RONIN SCOUT 통계"),
        ("A2", "자동 갱신 — 봇 매일 실행 시"),

        # ── 전체 성과 ──
        ("A4", "■ 전체 성과"),
        ("A5", "총 후보"),       ("B5", f"=COUNTA({SC}!C3:C)"),
        ("A6", "방향 적중 (O)"),  ("B6", f"=COUNTIF({SC}!S3:S,\"O\")"),
        ("A7", "방향 빗나감 (X)"),("B7", f"=COUNTIF({SC}!S3:S,\"X\")"),
        ("A8", "방향 모호 (△)"),  ("B8", f"=COUNTIF({SC}!S3:S,\"△\")"),
        ("A9", "적중률"),         ("B9", f"=IFERROR(B6/(B6+B7),0)"),

        # ── 별점별 성과 ──
        ("A11", "■ 별점별 +28d 평균"),
        ("A12", "★★★"), ("B12", f"=IFERROR(AVERAGEIF({SC}!F3:F,\"★★★\",{SC}!R3:R),\"표본 0\")"), ("C12", f"=COUNTIF({SC}!F3:F,\"★★★\")"),
        ("A13", "★★"),  ("B13", f"=IFERROR(AVERAGEIF({SC}!F3:F,\"★★\",{SC}!R3:R),\"표본 0\")"),  ("C13", f"=COUNTIF({SC}!F3:F,\"★★\")"),
        ("A14", "★"),    ("B14", f"=IFERROR(AVERAGEIF({SC}!F3:F,\"★\",{SC}!R3:R),\"표본 0\")"),    ("C14", f"=COUNTIF({SC}!F3:F,\"★\")"),

        # ── 별점별 적중률 ──
        ("A16", "■ 별점별 적중률"),
        ("A17", "★★★"), ("B17", f"=IFERROR(COUNTIFS({SC}!F3:F,\"★★★\",{SC}!S3:S,\"O\")/COUNTIFS({SC}!F3:F,\"★★★\",{SC}!S3:S,\"<>\"),0)"),
        ("A18", "★★"),  ("B18", f"=IFERROR(COUNTIFS({SC}!F3:F,\"★★\",{SC}!S3:S,\"O\")/COUNTIFS({SC}!F3:F,\"★★\",{SC}!S3:S,\"<>\"),0)"),
        ("A19", "★"),    ("B19", f"=IFERROR(COUNTIFS({SC}!F3:F,\"★\",{SC}!S3:S,\"O\")/COUNTIFS({SC}!F3:F,\"★\",{SC}!S3:S,\"<>\"),0)"),

        # ── Score(Track A) × 별점 상관 ──
        ("A21", "■ SCORE × ★★★ 비율"),
        ("A22", "Score 5"), ("B22", f"=IFERROR(COUNTIFS({SC}!E3:E,5,{SC}!F3:F,\"★★★\")/COUNTIF({SC}!E3:E,5),\"표본 0\")"),
        ("A23", "Score 4"), ("B23", f"=IFERROR(COUNTIFS({SC}!E3:E,4,{SC}!F3:F,\"★★★\")/COUNTIF({SC}!E3:E,4),\"표본 0\")"),
        ("A24", "Score 3"), ("B24", f"=IFERROR(COUNTIFS({SC}!E3:E,3,{SC}!F3:F,\"★★★\")/COUNTIF({SC}!E3:E,3),\"표본 0\")"),

        # ── 국가별 ──
        ("A26", "■ 국가별 +28d 평균"),
        ("A27", "US"), ("B27", f"=IFERROR(AVERAGEIF({SC}!D3:D,\"US\",{SC}!R3:R),\"표본 0\")"), ("C27", f"=COUNTIF({SC}!D3:D,\"US\")"),
        ("A28", "KR"), ("B28", f"=IFERROR(AVERAGEIF({SC}!D3:D,\"KR\",{SC}!R3:R),\"표본 0\")"), ("C28", f"=COUNTIF({SC}!D3:D,\"KR\")"),
        ("A29", "JP"), ("B29", f"=IFERROR(AVERAGEIF({SC}!D3:D,\"JP\",{SC}!R3:R),\"표본 0\")"), ("C29", f"=COUNTIF({SC}!D3:D,\"JP\")"),
        ("A30", "CN"), ("B30", f"=IFERROR(AVERAGEIF({SC}!D3:D,\"CN\",{SC}!R3:R),\"표본 0\")"), ("C30", f"=COUNTIF({SC}!D3:D,\"CN\")"),

        # ── 진입 매핑 ──
        ("A32", "■ 진입 매핑"),
        ("A33", "후보 발생"),    ("B33", f"=COUNTA({SC}!C3:C)"),
        ("A34", "진입한 후보"),  ("B34", f"=COUNTIF({SC}!T3:T,\"P*\")"),
        ("A35", "진입 변환율"),  ("B35", "=IFERROR(B34/B33,0)"),
        ("A36", "진입 +28d 평균"), ("B36", f"=IFERROR(AVERAGEIFS({SC}!R3:R,{SC}!T3:T,\"P*\",{SC}!R3:R,\"<>\"),\"표본 0\")"),
        ("A37", "미진입 +28d 평균"), ("B37", f"=IFERROR(AVERAGEIFS({SC}!R3:R,{SC}!T3:T,\"\",{SC}!R3:R,\"<>\"),\"표본 0\")"),

        # ── 모델 버전 ──
        ("A39", "■ 모델 버전 추적"),
        ("A40", "(자동: U 컬럼 unique 값 표시)"),
    ]


def _ensure_scout_sheets():
    """SCOUT 후보발굴 + SCOUT 통계 시트 존재 보장. 없으면 생성 + 헤더/수식 박제.

    Returns:
        (ws_cands, ws_stats): 두 워크시트 객체
    """
    client = _get_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    # ── SCOUT 후보발굴 ──
    try:
        ws_cands = spreadsheet.worksheet("SCOUT 후보발굴")
    except gspread.exceptions.WorksheetNotFound:
        ws_cands = spreadsheet.add_worksheet(
            title="SCOUT 후보발굴", rows=2000, cols=len(SCOUT_CANDIDATES_HEADERS)
        )
        # Row 1 = 헤더
        ws_cands.update(
            f"A1:U1", [SCOUT_CANDIDATES_HEADERS]
        )
        # Row 2 = 입력 가이드 (POSITIONS 패턴 차용)
        ws_cands.update(
            f"A2:U2",
            [[
                "자동", "봇 자동", "봇 자동", "봇 자동", "봇 자동",
                "LLM", "LLM", "LLM", "LLM", "LLM",
                "LLM", "LLM", "LLM", "yf 자동", "follow-up",
                "수식", "follow-up", "수식", "D+28 후",
                "POSITIONS 매핑", "환경변수",
            ]],
        )
        logger.info("[SCOUT] 'SCOUT 후보발굴' 시트 자동 생성 (21 컬럼)")

    # ── SCOUT 통계 ──
    try:
        ws_stats = spreadsheet.worksheet("SCOUT 통계")
    except gspread.exceptions.WorksheetNotFound:
        ws_stats = spreadsheet.add_worksheet(title="SCOUT 통계", rows=60, cols=4)
        # 셀별 박제
        for cell, value in _build_scout_stats_layout():
            ws_stats.update(cell, value, raw=False)
            time.sleep(0.05)  # API rate limit 회피
        logger.info("[SCOUT] 'SCOUT 통계' 시트 자동 생성 + 수식 박제")

    return ws_cands, ws_stats


def read_positions_for_mapping() -> dict:
    """POSITIONS → {ticker_upper: position_id} 자동 매핑 dict.

    OPEN/CLOSED 모두 포함 (CLOSED도 진입 이력으로 표기).
    DRAFT는 제외 (실제 진입 X).

    Returns:
        {"NKE": "P004", "MSFT": "P002", ...}
    """
    try:
        ws = get_sheet("POSITIONS 포지션")
        all_data = ws.get_all_values()
    except Exception as e:
        logger.warning("[SCOUT] POSITIONS 매핑 읽기 실패: %s", e)
        return {}

    if len(all_data) < 3:
        return {}

    mapping = {}
    for row in all_data[2:]:
        if len(row) < 3:
            continue
        pid = (row[0] or "").strip()
        ticker = (row[1] or "").strip().upper()
        status = (row[2] or "").strip().upper()
        if not pid or not ticker:
            continue
        if status == "DRAFT":
            continue
        # 같은 티커 여러 포지션이면 가장 최근 것만 남김 (덮어쓰기)
        mapping[ticker] = pid

    logger.info("[SCOUT] POSITIONS 매핑: %d개 티커", len(mapping))
    return mapping


def _format_signal_keys(signals: dict) -> str:
    """signals dict → 짧은 키 join 'INSIDER, BB, VOL'."""
    if not signals:
        return ""
    short_map = {
        "insider_buying": "INSIDER",
        "bb_squeeze": "BB",
        "volume_compression": "VOL",
        "after_low_consolidation": "LOW",
        "rrg_improving": "RRG",
    }
    keys = []
    for k in signals.keys():
        keys.append(short_map.get(k, k.upper()[:6]))
    return ", ".join(keys)


def save_candidates_eval(candidates: list[dict], date_str: str) -> int:
    """SCOUT 결과를 'SCOUT 후보발굴' 시트에 1행씩 적재 + 'SCOUT 통계' 갱신.

    Args:
        candidates: ScoutAgent.run() 반환의 candidates 리스트.
                    각 dict: ticker, name, country, sector, score, signals,
                             buy_questions(LLM 출력), price_at_add(m6 entry 추가 시).
        date_str: 발생일 KST YYYY-MM-DD

    Returns:
        적재된 행 수.

    동작:
        1. 시트 자동 생성 (없으면)
        2. POSITIONS 매핑 자동 로드 → 진입여부 컬럼 자동 매핑
        3. (티커 + 발생일) 중복 시 skip
        4. 신규 행만 append
    """
    if not candidates:
        return 0

    try:
        ws_cands, _ = _ensure_scout_sheets()
    except Exception as e:
        logger.error("[SCOUT] 시트 보장 실패: %s", e)
        return 0

    # 진입 매핑 로드
    pos_map = read_positions_for_mapping()

    # 기존 데이터 (중복 체크)
    try:
        existing = ws_cands.get_all_values()
    except Exception as e:
        logger.error("[SCOUT] 기존 데이터 read 실패: %s", e)
        return 0

    # (티커, 발생일) 중복 체크 set
    seen = set()
    for row in existing[2:]:  # row 1=헤더, row 2=가이드
        if len(row) >= 3:
            seen.add((row[2].strip().upper(), row[1].strip()))

    next_row = len(existing) + 1
    if next_row < 3:
        next_row = 3

    model_name = os.environ.get("GPT_MODEL", "gpt-5.4-mini")

    rows_to_append = []
    for c in candidates:
        ticker = (c.get("ticker") or "").strip().upper()
        if not ticker:
            continue

        # 중복 skip (같은 티커가 같은 날 두 번 안 들어가도록)
        if (ticker, date_str) in seen:
            continue

        bq = c.get("buy_questions") or {}
        signals = c.get("signals") or {}
        risk_flags = bq.get("risk_flags") or []
        if isinstance(risk_flags, list):
            risk_str = " / ".join(str(r) for r in risk_flags[:3])
        else:
            risk_str = str(risk_flags)[:200]

        # 발생가: c["price_at_add"] (m6_node에서 추가됨) 우선, 없으면 빈
        price_at_add = c.get("price_at_add") or c.get("close")
        try:
            price_str = f"{float(price_at_add):.4f}" if price_at_add else ""
        except (ValueError, TypeError):
            price_str = ""

        # 진입여부 매핑
        entry_pid = pos_map.get(ticker, "")

        # 21 컬럼 한 행
        row = [
            f"=ROW()-2",                              # A: No (수식)
            date_str,                                 # B: 발생일
            ticker,                                   # C: 티커
            (c.get("country") or "").upper(),         # D: 국가
            int(c.get("score") or 0),                 # E: Score
            bq.get("star_rating", ""),                # F: 별점
            (bq.get("summary") or "")[:30],           # G: Summary
            (bq.get("industry") or "")[:50],          # H: Industry
            (bq.get("catalyst") or "")[:200],         # I: Catalyst
            (bq.get("q1_why") or "")[:200],           # J: Q1
            (bq.get("q2_who") or "")[:200],           # K: Q2
            (bq.get("q3_space") or "")[:200],         # L: Q3
            risk_str,                                 # M: Risk Flags
            price_str,                                # N: 발생가
            "",                                       # O: +5d 가 (follow-up)
            f"=IFERROR((O{next_row + len(rows_to_append)}-N{next_row + len(rows_to_append)})/N{next_row + len(rows_to_append)},\"\")",  # P: +5d %
            "",                                       # Q: +28d 가
            f"=IFERROR((Q{next_row + len(rows_to_append)}-N{next_row + len(rows_to_append)})/N{next_row + len(rows_to_append)},\"\")",  # R: +28d %
            "",                                       # S: 방향 적중
            entry_pid,                                # T: 진입여부
            model_name,                               # U: Model
        ]
        rows_to_append.append(row)
        seen.add((ticker, date_str))

    if not rows_to_append:
        logger.info("[SCOUT] 시트 적재 skip (모두 중복)")
        return 0

    # 일괄 append (USER_ENTERED 모드 → 수식 평가)
    end_row = next_row + len(rows_to_append) - 1
    range_str = f"A{next_row}:U{end_row}"
    try:
        ws_cands.update(range_str, rows_to_append, raw=False)
        logger.info("[SCOUT] 시트 적재 완료: %d행 (range=%s)", len(rows_to_append), range_str)
    except Exception as e:
        logger.error("[SCOUT] 시트 적재 실패: %s", e)
        return 0

    return len(rows_to_append)


def update_followup_prices(m6_history: list[dict]) -> int:
    """m6_history 활용해 SCOUT 후보발굴 시트의 +5d / +28d 가격 자동 채움.

    매일 호출됨. m6는 이미 가격 추적 중이므로 D+5/D+28 시점 가격 활용.

    Args:
        m6_history: state.m6_history. 각 entry: {ticker, date_added, price_at_add, ...}

    Returns:
        업데이트된 행 수.

    로직:
        1. SCOUT 후보발굴 시트 read
        2. 각 행 (티커, 발생일) → m6 entry 매칭
        3. 오늘 - 발생일 >= 5 + +5d 가 비어있음 → m6 가격 fetch → O 컬럼 채움
        4. 오늘 - 발생일 >= 28 + +28d 가 비어있음 → 마지막 가격 fetch → Q 컬럼 채움
        5. +28d 채워진 행 = S 컬럼 적중 자동 판정 (별점 vs +28d%)
    """
    try:
        from src.modules.m6_feedback import _fetch_current_price
    except ImportError:
        logger.warning("[SCOUT] _fetch_current_price import 실패 — follow-up skip")
        return 0

    try:
        ws_cands, _ = _ensure_scout_sheets()
        all_data = ws_cands.get_all_values()
    except Exception as e:
        logger.warning("[SCOUT] follow-up read 실패: %s", e)
        return 0

    if len(all_data) < 3:
        return 0

    today = datetime.now().date()
    updates_o = []  # (cell, value) for +5d
    updates_q = []  # +28d
    updates_s = []  # 적중 판정

    for idx, row in enumerate(all_data[2:], start=3):  # row 3부터 데이터
        if len(row) < 14:
            continue
        ticker = (row[2] or "").strip().upper()
        date_str = (row[1] or "").strip()
        if not ticker or not date_str:
            continue

        try:
            occur_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        days_passed = (today - occur_date).days

        price_at_add_raw = row[13] if len(row) > 13 else ""  # N
        try:
            price_at_add = float(price_at_add_raw) if price_at_add_raw else 0.0
        except (ValueError, TypeError):
            price_at_add = 0.0

        # +5d 채움
        plus5d_raw = row[14] if len(row) > 14 else ""  # O
        if days_passed >= 5 and not plus5d_raw and price_at_add > 0:
            current = _fetch_current_price(ticker)
            if current and current > 0:
                updates_o.append((f"O{idx}", round(current, 4)))
                time.sleep(0.3)  # yfinance rate limit

        # +28d 채움 + 적중 판정
        plus28d_raw = row[16] if len(row) > 16 else ""  # Q
        if days_passed >= 28 and not plus28d_raw and price_at_add > 0:
            current = _fetch_current_price(ticker)
            if current and current > 0:
                updates_q.append((f"Q{idx}", round(current, 4)))
                # 적중 판정: 별점 vs +28d%
                star = (row[5] or "").strip()  # F
                pct = (current - price_at_add) / price_at_add
                if star == "★★★":
                    verdict = "O" if pct > 0.02 else ("X" if pct < -0.02 else "△")
                elif star == "★":
                    verdict = "O" if pct < -0.02 else ("X" if pct > 0.05 else "△")
                else:  # ★★
                    verdict = "△"  # 중립
                updates_s.append((f"S{idx}", verdict))
                time.sleep(0.3)

    # 일괄 업데이트
    total = 0
    for cell, value in updates_o + updates_q + updates_s:
        try:
            ws_cands.update(cell, value, raw=False)
            total += 1
            time.sleep(0.05)
        except Exception as e:
            logger.warning("[SCOUT] cell %s 업데이트 실패: %s", cell, e)

    if total:
        logger.info("[SCOUT] follow-up 갱신: +5d %d개, +28d %d개, 적중 %d개",
                    len(updates_o), len(updates_q), len(updates_s))

    return total


def sync_position_mapping() -> int:
    """POSITIONS 매핑을 SCOUT 후보발굴 T 컬럼에 자동 동기화.

    매일 호출됨. 진입 후 동기화 위함.

    Returns:
        업데이트된 행 수.
    """
    try:
        ws_cands, _ = _ensure_scout_sheets()
        all_data = ws_cands.get_all_values()
    except Exception as e:
        logger.warning("[SCOUT] sync read 실패: %s", e)
        return 0

    if len(all_data) < 3:
        return 0

    pos_map = read_positions_for_mapping()
    if not pos_map:
        return 0

    updates = []
    for idx, row in enumerate(all_data[2:], start=3):
        if len(row) < 3:
            continue
        ticker = (row[2] or "").strip().upper()
        current_pid = (row[19] or "").strip() if len(row) > 19 else ""  # T
        if not ticker:
            continue

        new_pid = pos_map.get(ticker, "")
        if new_pid and new_pid != current_pid:
            updates.append((f"T{idx}", new_pid))

    for cell, value in updates:
        try:
            ws_cands.update(cell, value, raw=False)
            time.sleep(0.05)
        except Exception as e:
            logger.warning("[SCOUT] T 컬럼 업데이트 실패 %s: %s", cell, e)

    if updates:
        logger.info("[SCOUT] 진입 매핑 동기화: %d행", len(updates))

    return len(updates)
