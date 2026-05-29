"""KR DART collector for SCOUT quality and catalyst auditors.

DART is the KR backbone because KRX/Naver scraping can be blocked in GitHub
Actions. All functions are best-effort and must never fail the whole run.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import zipfile
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

DART_API_KEY = os.environ.get("DART_API_KEY", "")
DART_BASE = "https://opendart.fss.or.kr/api"
DART_VIEWER_BASE = "https://dart.fss.or.kr/dsaf001/main.do"
YAHOO_FX_URL = "https://query1.finance.yahoo.com/v8/finance/chart/USDKRW%3DX?range=5d&interval=1d"

ROOT_DIR = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT_DIR / "data" / "cache"
CORP_CODE_CACHE = CACHE_DIR / "dart_corp_codes.json"
FX_CACHE = CACHE_DIR / "usdkrw_latest.json"

REPORT_CODES = ["11011", "11014", "11012", "11013"]  # annual, Q3, half, Q1
FS_DIVS = ["CFS", "OFS"]


def dart_enabled() -> bool:
    return bool(DART_API_KEY)


def _ticker_code(ticker: str) -> str:
    code = str(ticker or "").strip().upper()
    for suffix in (".KS", ".KQ", ".KR"):
        if code.endswith(suffix):
            code = code[: -len(suffix)]
    code = re.sub(r"\D", "", code)
    return code.zfill(6) if code else ""


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", "-", "nan", "NaN"):
        return None
    try:
        text = str(value).replace(",", "").replace(" ", "").strip()
        if text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1]
        return float(text)
    except Exception:
        return None


def _pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous is None or previous <= 0:
        return None
    return (current / previous - 1.0) * 100.0


def _get_json(url: str, params: dict, timeout: int = 15) -> tuple[str, dict]:
    try:
        import requests
        resp = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return f"http_{resp.status_code}", {}
        data = resp.json()
        if not isinstance(data, dict):
            return "bad_response", {}
        status = str(data.get("status", "ok") or "ok")
        if status in {"000", "ok"}:
            return "ok", data
        if status == "013":
            return "empty", data
        if status == "020":
            return "rate_limited", data
        return f"dart_{status}", data
    except Exception as e:
        logger.debug("[DART] request failed: %s", e)
        return "error", {}


def _load_cached_corp_codes() -> dict[str, dict]:
    try:
        if not CORP_CODE_CACHE.exists():
            return {}
        with open(CORP_CODE_CACHE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        updated_at = str(data.get("_updated_at", "") or "")
        if updated_at:
            dt = datetime.fromisoformat(updated_at)
            if (datetime.utcnow() - dt).days <= 30:
                return data.get("codes", {}) if isinstance(data.get("codes"), dict) else {}
        return data.get("codes", {}) if isinstance(data.get("codes"), dict) else {}
    except Exception:
        return {}


def _save_corp_codes(codes: dict[str, dict]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"_updated_at": datetime.utcnow().isoformat(), "codes": codes}
        with open(CORP_CODE_CACHE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception as e:
        logger.debug("[DART] corp code cache save failed: %s", e)


def _download_corp_codes() -> tuple[str, dict[str, dict]]:
    if not DART_API_KEY:
        return "no_key", {}
    try:
        import requests
        resp = requests.get(
            f"{DART_BASE}/corpCode.xml",
            params={"crtfc_key": DART_API_KEY},
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code != 200:
            return f"http_{resp.status_code}", {}
        with zipfile.ZipFile(BytesIO(resp.content)) as zf:
            xml_bytes = zf.read("CORPCODE.xml")
        root = ET.fromstring(xml_bytes)
        codes: dict[str, dict] = {}
        for node in root.findall("list"):
            stock_code = (node.findtext("stock_code") or "").strip()
            if not stock_code:
                continue
            stock_code = stock_code.zfill(6)
            corp_code = (node.findtext("corp_code") or "").strip()
            if not corp_code:
                continue
            codes[stock_code] = {
                "corp_code": corp_code,
                "corp_name": (node.findtext("corp_name") or "").strip(),
                "stock_code": stock_code,
                "modify_date": (node.findtext("modify_date") or "").strip(),
            }
        if codes:
            _save_corp_codes(codes)
            return "ok", codes
        return "empty", {}
    except zipfile.BadZipFile:
        return "bad_zip", {}
    except Exception as e:
        logger.debug("[DART] corp code download failed: %s", e)
        return "error", {}


def get_corp_code(ticker: str) -> tuple[str, dict]:
    code = _ticker_code(ticker)
    if not code:
        return "bad_ticker", {}
    cached = _load_cached_corp_codes()
    if code in cached:
        return "ok", dict(cached[code])
    status, downloaded = _download_corp_codes()
    if status == "ok" and code in downloaded:
        return "ok", dict(downloaded[code])
    return status if status != "ok" else "corp_code_missing", {}


def _latest_usdkrw() -> Optional[float]:
    try:
        if FX_CACHE.exists():
            with open(FX_CACHE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            updated_at = datetime.fromisoformat(str(cached.get("updated_at", "")))
            if (datetime.utcnow() - updated_at).total_seconds() <= 12 * 3600:
                val = _safe_float(cached.get("usdkrw"))
                if val and val > 0:
                    return val
    except Exception:
        pass

    try:
        import requests
        resp = requests.get(YAHOO_FX_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return None
        data = resp.json()
        result = data.get("chart", {}).get("result", [])
        quote = result[0].get("indicators", {}).get("quote", [{}])[0] if result else {}
        closes = [_safe_float(v) for v in quote.get("close", [])]
        valid = [v for v in closes if v and v > 0]
        if not valid:
            return None
        fx = float(valid[-1])
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(FX_CACHE, "w", encoding="utf-8") as f:
                json.dump({"updated_at": datetime.utcnow().isoformat(), "usdkrw": fx}, f)
        except Exception:
            pass
        return fx
    except Exception as e:
        logger.debug("[DART] USDKRW fetch failed: %s", e)
        return None


def _normalize_account_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[\s\(\)\[\]{}·ㆍ/\\_-]", "", text)
    return text


def _row_amount(row: dict, key: str) -> Optional[float]:
    return _safe_float(row.get(key))


def _pick_account(rows: list[dict], kind: str, amount_key: str = "thstrm_amount") -> Optional[dict]:
    selectors = {
        "revenue": {
            "sj": {"IS", "CIS"},
            "ids": ["revenue", "salesrevenue", "operatingrevenue"],
            "names": ["매출액", "수익매출액", "영업수익", "매출", "수익"],
            "exclude": ["매출원가", "원가", "총이익", "금융수익", "이자수익", "기타수익"],
        },
        "operating_income": {
            "sj": {"IS", "CIS"},
            "ids": ["operatingincomeloss", "profitlossfromoperatingactivities"],
            "names": ["영업이익", "영업이익손실"],
            "exclude": ["계속영업", "중단영업"],
        },
        "net_income": {
            "sj": {"IS", "CIS"},
            "ids": ["profitlossattributabletoownersofparent", "profitloss"],
            "names": ["당기순이익", "당기순이익손실", "분기순이익", "반기순이익", "연결당기순이익", "지배기업의소유주에게귀속되는당기순이익"],
            "exclude": ["기타포괄", "총포괄", "법인세", "주당", "비지배"],
        },
        "equity": {
            "sj": {"BS"},
            "ids": ["equity"],
            "names": ["자본총계", "총자본", "자본"],
            "exclude": ["비지배", "지배기업", "부채", "liabilitiesandequity"],
        },
        "liabilities": {
            "sj": {"BS"},
            "ids": ["liabilities"],
            "names": ["부채총계", "총부채", "부채"],
            "exclude": ["유동", "비유동", "자본", "liabilitiesandequity"],
        },
        "assets": {
            "sj": {"BS"},
            "ids": ["assets"],
            "names": ["자산총계", "총자산", "자산"],
            "exclude": ["유동", "비유동"],
        },
    }
    spec = selectors.get(kind, {})
    candidates = []
    for row in rows:
        amount = _row_amount(row, amount_key)
        if amount is None:
            continue
        sj_div = str(row.get("sj_div", "") or "").upper()
        if spec.get("sj") and sj_div not in spec["sj"]:
            continue
        account_id = _normalize_account_text(row.get("account_id"))
        account_nm = _normalize_account_text(row.get("account_nm"))
        text = account_id + "|" + account_nm
        if any(x in text for x in spec.get("exclude", [])):
            continue
        id_hit = any(x in account_id for x in spec.get("ids", []))
        name_hit = any(x in account_nm for x in spec.get("names", []))
        if id_hit or name_hit:
            candidates.append((0 if id_hit else 1, len(account_nm), row))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]))
    return dict(candidates[0][2])


def _fetch_financial_rows(corp_code: str) -> tuple[str, list[dict], dict]:
    if not DART_API_KEY:
        return "no_key", [], {}
    current_year = datetime.utcnow().year
    last_payload: dict = {}
    for year in range(current_year - 1, current_year - 5, -1):
        for report_code in REPORT_CODES:
            for fs_div in FS_DIVS:
                status, data = _get_json(
                    f"{DART_BASE}/fnlttSinglAcntAll.json",
                    {
                        "crtfc_key": DART_API_KEY,
                        "corp_code": corp_code,
                        "bsns_year": str(year),
                        "reprt_code": report_code,
                        "fs_div": fs_div,
                    },
                    timeout=20,
                )
                last_payload = data
                if status == "ok" and isinstance(data.get("list"), list) and data["list"]:
                    meta = {"bsns_year": year, "reprt_code": report_code, "fs_div": fs_div}
                    return "ok", data["list"], meta
                if status == "rate_limited":
                    return status, [], {"bsns_year": year, "reprt_code": report_code, "fs_div": fs_div}
                time.sleep(0.03)
    return "empty", [], {"message": last_payload.get("message", "")}


def fetch_kr_fundamental_data(ticker: str, market_cap_usd: Optional[float] = None) -> tuple[str, dict]:
    """Return KR DART fundamentals in the existing SCOUT quality shape."""
    if not DART_API_KEY:
        return "dart_no_key", {}
    corp_status, corp = get_corp_code(ticker)
    if corp_status != "ok":
        return f"dart_{corp_status}", {}

    status, rows, meta = _fetch_financial_rows(str(corp.get("corp_code", "")))
    if status != "ok" or not rows:
        return f"dart_{status}", {"source": "dart", "dart_meta": {"corp": corp, **meta}}

    revenue_row = _pick_account(rows, "revenue")
    operating_row = _pick_account(rows, "operating_income")
    net_row = _pick_account(rows, "net_income")
    equity_row = _pick_account(rows, "equity")
    liabilities_row = _pick_account(rows, "liabilities")
    assets_row = _pick_account(rows, "assets")

    revenue = _row_amount(revenue_row or {}, "thstrm_amount")
    revenue_prev = _row_amount(revenue_row or {}, "frmtrm_amount")
    operating_income = _row_amount(operating_row or {}, "thstrm_amount")
    net_income = _row_amount(net_row or {}, "thstrm_amount")
    net_income_prev = _row_amount(net_row or {}, "frmtrm_amount")
    equity = _row_amount(equity_row or {}, "thstrm_amount")
    liabilities = _row_amount(liabilities_row or {}, "thstrm_amount")
    assets = _row_amount(assets_row or {}, "thstrm_amount")

    usdkrw = _latest_usdkrw()
    market_cap_krw = None
    pe = None
    if market_cap_usd is not None and market_cap_usd > 0 and usdkrw and usdkrw > 0:
        market_cap_krw = float(market_cap_usd) * float(usdkrw)
    if market_cap_krw and net_income and net_income > 0:
        pe = market_cap_krw / net_income

    revenue_growth = _pct_change(revenue, revenue_prev)
    net_income_growth = _pct_change(net_income, net_income_prev)
    roe = (net_income / equity * 100.0) if net_income is not None and equity and equity > 0 else None
    roa = (net_income / assets * 100.0) if net_income is not None and assets and assets > 0 else None
    debt_equity = (liabilities / equity) if liabilities is not None and equity and equity > 0 else None
    operating_margin = (operating_income / revenue * 100.0) if operating_income is not None and revenue and revenue > 0 else None
    net_margin = (net_income / revenue * 100.0) if net_income is not None and revenue and revenue > 0 else None

    return "dart", {
        "pe": pe,
        "forward_pe": None,
        "eps_next_y": None,
        "eps_growth_next_y": None,
        "peg": None,
        "insider_trans": None,
        "inst_trans": None,
        "short_float": None,
        "rsi14": None,
        "sector": "",
        "industry": "",
        "market_cap": market_cap_usd,
        "earnings_date": "",
        "source": "dart",
        "fmp_quality": {
            "revenue_growth_pct": revenue_growth,
            "eps_growth_pct": net_income_growth,
            "free_cash_flow_growth_pct": None,
            "gross_margin_ttm": None,
            "operating_margin_ttm": operating_margin,
            "net_margin_ttm": net_margin,
            "roe_ttm": roe,
            "roa_ttm": roa,
            "debt_equity_ttm": debt_equity,
            "current_ratio_ttm": None,
            "rating": None,
            "rating_score": None,
        },
        "dart_quality": {
            "corp_code": corp.get("corp_code", ""),
            "corp_name": corp.get("corp_name", ""),
            "stock_code": corp.get("stock_code", ""),
            "bsns_year": meta.get("bsns_year"),
            "reprt_code": meta.get("reprt_code"),
            "fs_div": meta.get("fs_div"),
            "usdkrw": usdkrw,
            "market_cap_usd": market_cap_usd,
            "market_cap_krw": market_cap_krw,
            "revenue": revenue,
            "revenue_prev": revenue_prev,
            "operating_income": operating_income,
            "net_income": net_income,
            "net_income_prev": net_income_prev,
            "equity": equity,
            "liabilities": liabilities,
            "assets": assets,
            "pe_note": "unknown_if_fx_missing_or_net_income_non_positive",
        },
    }


def _parse_yyyymmdd(value: Any) -> int:
    text = str(value or "").strip()
    try:
        return int(datetime.strptime(text[:8], "%Y%m%d").timestamp())
    except Exception:
        return 0


def fetch_kr_catalyst_news(
    ticker: str,
    lookback_days: int = 14,
    max_items: int = 3,
) -> tuple[str, list[dict]]:
    """Fetch recent KR DART disclosures in the SCOUT catalyst news shape."""
    if not DART_API_KEY:
        return "no_key", []
    corp_status, corp = get_corp_code(ticker)
    if corp_status != "ok":
        return f"dart_{corp_status}", []

    end = datetime.utcnow().date()
    start = end - timedelta(days=max(1, int(lookback_days or 14)))
    status, data = _get_json(
        f"{DART_BASE}/list.json",
        {
            "crtfc_key": DART_API_KEY,
            "corp_code": corp.get("corp_code", ""),
            "bgn_de": start.strftime("%Y%m%d"),
            "end_de": end.strftime("%Y%m%d"),
            "last_reprt_at": "Y",
            "sort": "date",
            "sort_mth": "desc",
            "page_no": "1",
            "page_count": str(max(10, min(100, int(max_items or 3) * 3))),
        },
        timeout=15,
    )
    if status != "ok":
        return status, []
    raw_items = data.get("list")
    if not isinstance(raw_items, list) or not raw_items:
        return "empty", []

    items = []
    for it in raw_items:
        report_nm = str(it.get("report_nm", "") or "").strip()
        rcept_no = str(it.get("rcept_no", "") or "").strip()
        if not report_nm or not rcept_no:
            continue
        rcept_dt = str(it.get("rcept_dt", "") or "").strip()
        corp_name = str(it.get("corp_name", "") or corp.get("corp_name", "") or "").strip()
        source_kind = str(it.get("pblntf_ty", "") or "").strip()
        items.append({
            "headline": report_nm[:180],
            "summary": f"{corp_name} DART 공시 {rcept_dt} {source_kind}".strip()[:300],
            "source": "DART",
            "datetime": _parse_yyyymmdd(rcept_dt),
            "date": rcept_dt,
            "url": f"{DART_VIEWER_BASE}?rcpNo={rcept_no}",
            "event_type": "disclosure",
            "rcept_no": rcept_no,
            "corp_code": corp.get("corp_code", ""),
        })
    items.sort(key=lambda x: x.get("datetime", 0), reverse=True)
    if not items:
        return "empty", []
    return "ok", items[:max_items]
