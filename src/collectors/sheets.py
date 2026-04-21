"""Google Sheets 연동 — gspread 기반. src/collectors/sheets.py에 배치."""

import json
import logging
import os

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
