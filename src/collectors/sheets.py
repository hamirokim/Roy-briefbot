"""Google Sheets 연동 — gspread 기반. src/collectors/sheets.py에 배치."""

import json
import logging
import os

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SPREADSHEET_ID = os.environ.get(
    "GOOGLE_SHEET_ID",
    "1AqTovu36EHZL8NcQSr-zPqZGEtQpJ1eeNyMWhstTntU",
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
