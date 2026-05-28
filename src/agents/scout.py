"""
src/agents/scout.py — SCOUT 발굴 에이전트

미션: NYSE/NASDAQ/KOSPI/KOSDAQ/TSE/CN-ADR 수천 종목 → 메인지표 신호 임박 후보 1~3개

5개 사전 감지 신호 (모두 가격 움직이기 전):
  1. BB Width < 20일 평균 × 0.5 (변동성 압축 → 폭발 직전)
  2. 5일 거래량 < 20일 평균 × 0.7 (관심 부족 → 곧 attention)
  3. 52주 신저가 후 7~14일 횡보 (바닥 다지기)
  4. Insider Buying 1주 내 발생 (미국만, Finviz)
  5. 섹터 RRG IMPROVING 진입 (M2 결과 활용)

Cooldown: 같은 종목 5일간 재출현 금지 (settings.cooldown_days)
출력: 점수 순 상위 N개 (settings.max_candidates_output)

Q1 (Roy 지시): 메인포트/AUTO_TICKER 제외 필터 없음. 본업에 충실.
Q2 (Roy 지시): Daily 통일.
"""

import json
import logging
import os
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
import requests

from src.agents.base import BaseAgent
from src.utils import today_kst_str

logger = logging.getLogger(__name__)

RADAR_DIR = Path(__file__).resolve().parents[2] / "data" / "scout"
FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
FINNHUB_BASE = "https://finnhub.io/api/v1"


# ═══════════════════════════════════════════════════════════
# Settings 로드
# ═══════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
# Z1 신규 — 신호 명명 강화 (한글 + 主力运作 단계)
# D55 정합: SCOUT 5신호 ↔ 主力运作 5단계 매핑
# ═══════════════════════════════════════════════════════════
SIGNAL_LABELS = {
    "bb_squeeze": {
        "ko": "변동성 압축",
        "zh_phase": "拉升 직전 (매집 완료)",
        "desc": "BB Width < 평균 0.5× — 변동성 폭발 임박",
    },
    "volume_compression": {
        "ko": "거래량 압축",
        "zh_phase": "建仓 진행 중",
        "desc": "5일 거래량 < 20일 평균 0.7× — 매집 단계 거래량 흡수",
    },
    "after_low_consolidation": {
        "ko": "横盘建仓 (저점 후 횡보)",
        "zh_phase": "建仓 단계 (主力 매집 의심)",
        "desc": "52주 신저가 후 7~14일 횡보 — 바닥 다지기",
    },
    "insider_buying": {
        "ko": "메인자금 진입 흔적",
        "zh_phase": "主力 진입",
        "desc": "Insider 1주 내 매수 발생",
    },
    "rrg_improving": {
        "ko": "활성 섹터 진입 (회전)",
        "zh_phase": "拉离 (메인자금 회전 시작)",
        "desc": "섹터 RRG 3일 내 LAGGING→IMPROVING 전환",
    },
    "ronin_entry_v2": {
        "ko": "RONIN Entry v2 근접",
        "zh_phase": "ENTRY 공진",
        "desc": "WT/MFI/BB 2개 이상 공진 + ST DOWN",
    },
    "ronin_structure_support": {
        "ko": "RONIN 구조 지지 근접",
        "zh_phase": "구조존 재진입",
        "desc": "피벗 지지/돌파 저항 지지 전환 근처",
    },
}

SECTOR_ETF_MAP = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Health Care": "XLV",
    "Financials": "XLF",
    "Financial": "XLF",
    "Financial Services": "XLF",
    "Consumer Cyclical": "XLY",
    "Consumer Discretionary": "XLY",
    "Consumer Defensive": "XLP",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Basic Materials": "XLB",
    "Communication Services": "XLC",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
}


# ═══════════════════════════════════════════════════════════
# Z1 신규 — themes.yaml 로드 (Track D 提前布局용)
# ═══════════════════════════════════════════════════════════
def _load_themes() -> dict:
    """themes.yaml 로드 (Track D 가치사슬 매핑)."""
    import yaml
    from pathlib import Path
    
    themes_path = Path(__file__).parent.parent.parent / "config" / "themes.yaml"
    if not themes_path.exists():
        return {}
    
    try:
        with open(themes_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data.get("themes", {})
    except Exception as e:
        return {}


def _build_ticker_to_themes_map(themes: dict) -> dict:
    """ticker → list of (theme_key, role, priority, layer) 역인덱스 구축."""
    result = {}
    for theme_key, theme_data in themes.items():
        peer_tickers = []
        for peer_layer in ["upstream", "midstream", "downstream", "enabling_layer"]:
            for peer in theme_data.get(peer_layer, []) or []:
                if isinstance(peer, dict) and peer.get("ticker"):
                    peer_tickers.append(_theme_lookup_key(peer.get("ticker", "")))
        for layer in ["upstream", "midstream", "downstream", "enabling_layer"]:
            tickers = theme_data.get(layer, [])
            for t in tickers:
                if isinstance(t, dict):
                    ticker = t.get("ticker", "")
                    if ticker:
                        result.setdefault(ticker, []).append({
                            "theme_key": theme_key,
                            "theme_label": theme_data.get("label_ko", theme_key),
                            "role": t.get("role", ""),
                            "priority": t.get("priority", "B"),
                            "layer": layer,
                            "parent_sector": theme_data.get("parent_sector", ""),
                            "parent_theme_etf": theme_data.get("parent_theme_etf", ""),
                            "peer_tickers": sorted(set(peer_tickers)),
                        })
    return result


def _theme_lookup_key(ticker: str) -> str:
    """테마 매핑용 티커 정규화."""
    t = (ticker or "").strip().upper()
    if t.endswith(".US"):
        t = t[:-3]
    return t


def _theme_bonus(matches: list[dict], weights: dict) -> float:
    """themes.yaml 우선순위 → 레이더 점수 보너스."""
    if not matches:
        return 0.0
    priority_order = {"A+": 4, "A": 3, "B+": 2, "B": 1, "C": 0}
    best = max(matches, key=lambda m: priority_order.get(str(m.get("priority", "B")), 1))
    priority = str(best.get("priority", "B"))
    key = {
        "A+": "theme_A_plus",
        "A": "theme_A",
        "B+": "theme_B_plus",
        "B": "theme_B",
    }.get(priority, "theme_B")
    return float(weights.get(key, 0.0))


def _latest_snapshot(history: dict) -> tuple[str, dict]:
    if not history:
        return "", {}
    try:
        latest = sorted(history.keys(), reverse=True)[0]
        return latest, dict(history.get(latest) or {})
    except Exception:
        return "", {}


def _sector_etf_for_name(sector: str) -> str:
    return SECTOR_ETF_MAP.get(str(sector or "").strip(), "")


def _quadrant_support(quadrant: str, cfg: dict) -> str:
    q = str(quadrant or "")
    if q in set(cfg.get("support_quadrants", []) or ["LEADING", "IMPROVING"]):
        return "SUPPORT"
    if q in set(cfg.get("caution_quadrants", []) or ["WEAKENING"]):
        return "CAUTION"
    if q in set(cfg.get("fail_quadrants", []) or ["LAGGING"]):
        return "UNSUPPORTED"
    return "UNKNOWN"


def _theme_group_context(parent_theme_etf: str, theme_snapshot: dict, cfg: dict) -> dict:
    if not parent_theme_etf or not theme_snapshot:
        return {
            "parent_theme_etf": parent_theme_etf,
            "parent_quadrant": "",
            "theme_group": "",
            "group_label": "",
            "supporting_etfs": [],
            "caution_etfs": [],
            "unsupported_etfs": [],
            "status": "NO_RRG_DATA",
        }

    parent = dict(theme_snapshot.get(parent_theme_etf) or {})
    group_key = parent.get("theme_group") or parent.get("category") or ""
    group_label = parent.get("group_label") or parent.get("label") or parent_theme_etf
    supporting = []
    caution = []
    unsupported = []
    for etf, info in (theme_snapshot or {}).items():
        info = dict(info or {})
        if (info.get("theme_group") or info.get("category") or "") != group_key:
            continue
        q = str(info.get("quadrant", "") or "")
        row = {
            "etf": etf,
            "label": info.get("label", etf),
            "quadrant": q,
            "ratio": info.get("ratio"),
            "momentum": info.get("momentum"),
        }
        support = _quadrant_support(q, cfg)
        if support == "SUPPORT":
            supporting.append(row)
        elif support == "CAUTION":
            caution.append(row)
        elif support == "UNSUPPORTED":
            unsupported.append(row)

    min_support = int(cfg.get("min_group_support_etfs", 2) or 2)
    parent_support = _quadrant_support(str(parent.get("quadrant", "") or ""), cfg)
    if len(supporting) >= min_support:
        status = "GROUP_SUPPORT"
    elif parent_support == "SUPPORT":
        status = "PARENT_SUPPORT"
    elif parent_support == "CAUTION":
        status = "GROUP_CAUTION"
    elif parent_support == "UNSUPPORTED":
        status = "GROUP_UNSUPPORTED"
    else:
        status = "NO_RRG_DATA"

    return {
        "parent_theme_etf": parent_theme_etf,
        "parent_quadrant": parent.get("quadrant", ""),
        "theme_group": group_key,
        "group_label": group_label,
        "supporting_etfs": supporting[:6],
        "caution_etfs": caution[:6],
        "unsupported_etfs": unsupported[:6],
        "status": status,
    }


def _assess_theme_industry(
    ticker: str,
    row: pd.Series,
    matches: list[dict],
    m2_history: dict,
    m2_theme_history: dict,
    cfg: dict,
) -> dict:
    """테마/산업 보조 감사관.

    탈락 권한은 없다. 섹터/테마가 종목을 밀어주는지, 아니면 혼자 튀는지
    브리핑과 사후 성과표에 남기는 용도다.
    """
    if not bool((cfg or {}).get("enabled", False)):
        return {}

    sector_date, sector_snapshot = _latest_snapshot(m2_history)
    theme_date, theme_snapshot = _latest_snapshot(m2_theme_history)
    sector = str(row.get("sector", "") or "")
    sector_etf = _sector_etf_for_name(sector)
    sector_info = dict(sector_snapshot.get(sector_etf) or {}) if sector_etf else {}
    sector_quadrant = str(sector_info.get("quadrant", "") or "")
    sector_support = _quadrant_support(sector_quadrant, cfg)

    theme_contexts = []
    lookup_ticker = _theme_lookup_key(ticker)
    for match in matches[:5]:
        parent_theme_etf = str(match.get("parent_theme_etf", "") or "")
        ctx = _theme_group_context(parent_theme_etf, theme_snapshot, cfg)
        theme_contexts.append({
            "theme_key": match.get("theme_key", ""),
            "theme_label": match.get("theme_label", ""),
            "role": match.get("role", ""),
            "priority": match.get("priority", ""),
            "layer": match.get("layer", ""),
            "parent_sector": match.get("parent_sector", ""),
            "peer_tickers": [t for t in (match.get("peer_tickers") or []) if t != lookup_ticker][:12],
            **ctx,
        })

    group_statuses = {str(t.get("status", "")) for t in theme_contexts}
    has_theme_support = bool(group_statuses & {"GROUP_SUPPORT", "PARENT_SUPPORT"})
    has_theme_caution = "GROUP_CAUTION" in group_statuses
    has_theme_unsupported = "GROUP_UNSUPPORTED" in group_statuses
    has_sector_support = sector_support == "SUPPORT"
    has_sector_caution = sector_support == "CAUTION"
    has_sector_unsupported = sector_support == "UNSUPPORTED"

    confidence_delta = 0
    reasons = []
    warnings = []
    if has_theme_support:
        confidence_delta += 2
        reasons.append("theme_group_support")
    if has_sector_support:
        confidence_delta += 1
        reasons.append("sector_rrg_support")
    if has_theme_caution or has_sector_caution:
        warnings.append("theme_or_sector_weakening")
    if has_theme_unsupported or has_sector_unsupported:
        confidence_delta -= 1
        warnings.append("theme_or_sector_lagging")

    if has_theme_support and has_sector_support:
        status = "STRONG_SUPPORT"
    elif has_theme_support or has_sector_support:
        status = "SUPPORT"
    elif matches:
        status = "THEME_UNSUPPORTED" if has_theme_unsupported or has_sector_unsupported else "THEME_NEUTRAL"
    elif sector_etf:
        status = "SECTOR_UNSUPPORTED" if has_sector_unsupported else "SECTOR_NEUTRAL"
    else:
        status = "NO_MAPPING"

    return {
        "enabled": True,
        "status": status,
        "confidence_delta": int(confidence_delta),
        "reasons": reasons,
        "warnings": warnings,
        "sector": {
            "name": sector,
            "etf": sector_etf,
            "snapshot_date": sector_date,
            "quadrant": sector_quadrant,
            "support": sector_support,
            "ratio": sector_info.get("ratio"),
            "momentum": sector_info.get("momentum"),
        },
        "themes": theme_contexts,
        "theme_snapshot_date": theme_date,
        "peer_confirmation": {
            "static_peer_count": len(sorted({p for t in theme_contexts for p in (t.get("peer_tickers") or [])})),
            "active_peer_count": 0,
            "active_peers": [],
        },
        "reject_authority": False,
    }


def _attach_theme_peer_confirmation(items: list[dict], top_n: int = 30) -> None:
    """같은 테마 가치사슬 동료가 관찰풀 상위권에 같이 올라왔는지 표시한다."""
    if not items:
        return
    ticker_to_item = {_theme_lookup_key(str(item.get("ticker", "") or "")): item for item in items[:top_n]}
    for item in items:
        auditor = item.get("theme_industry") or {}
        if not auditor:
            continue
        peer_hits = []
        for theme in auditor.get("themes", []) or []:
            peers = set(theme.get("peer_tickers") or [])
            for peer in sorted(peers & set(ticker_to_item.keys())):
                if peer == _theme_lookup_key(str(item.get("ticker", "") or "")):
                    continue
                peer_item = ticker_to_item.get(peer) or {}
                peer_hits.append({
                    "ticker": peer,
                    "score": peer_item.get("score", 0),
                    "theme_key": theme.get("theme_key", ""),
                    "theme_label": theme.get("theme_label", ""),
                })
        dedup = []
        seen = set()
        for hit in peer_hits:
            key = (hit.get("ticker"), hit.get("theme_key"))
            if key in seen:
                continue
            seen.add(key)
            dedup.append(hit)
        auditor.setdefault("peer_confirmation", {})
        auditor["peer_confirmation"]["active_peer_count"] = len(dedup)
        auditor["peer_confirmation"]["active_peers"] = dedup[:8]
        if dedup:
            auditor["confidence_delta"] = int(auditor.get("confidence_delta", 0) or 0) + 1
            auditor.setdefault("reasons", []).append("active_theme_peers")
            if auditor.get("status") == "SUPPORT":
                auditor["status"] = "STRONG_SUPPORT"


def _liquidity_boost(row: pd.Series, min_liquidity: float, weight: float) -> float:
    """거래대금이 기준을 넘으면 작은 보너스만 준다."""
    try:
        value = float(row.get("avg_volume_value", 0) or 0)
    except (TypeError, ValueError):
        value = 0.0
    if min_liquidity <= 0 or value >= min_liquidity:
        return float(weight)
    return 0.0


def _label_signal_dict(signals: dict) -> dict:
    """신호 dict에 한글 라벨을 붙인다."""
    labeled = {}
    for sig_key, sig_info in (signals or {}).items():
        label_data = SIGNAL_LABELS.get(sig_key, {})
        labeled[sig_key] = {
            **sig_info,
            "label_ko": label_data.get("ko", sig_key),
            "phase": label_data.get("zh_phase", ""),
        }
    return labeled


def _assess_quality_context(df: pd.DataFrame, row: pd.Series, min_liquidity: float) -> dict:
    """후보를 차단하지 않고, 나중에 판단할 품질 태그를 붙인다.

    v1 원칙: 매수/매도 제안이 아니라 감사용 태그다. 태그가 있어도 후보 탈락은 하지 않는다.
    """
    flags = []
    metrics: dict[str, float | int] = {}

    try:
        close = df["close"].astype(float).dropna()
    except Exception:
        close = pd.Series(dtype=float)

    if len(close) < 60:
        flags.append("data_short")
        metrics["close_days"] = int(len(close))
    if not close.empty:
        current = float(close.iloc[-1])
        metrics["last_close"] = round(current, 3)

        if len(close) >= 21:
            prev_20 = float(close.iloc[-21])
            if prev_20 > 0:
                ret_20d = current / prev_20 - 1
                metrics["ret_20d"] = round(ret_20d, 4)
                if ret_20d >= 0.20:
                    flags.append("overextended_20d")

        if len(close) >= 200:
            ma50 = float(close.iloc[-50:].mean())
            ma200 = float(close.iloc[-200:].mean())
            metrics["ma50"] = round(ma50, 3)
            metrics["ma200"] = round(ma200, 3)
            if current < ma50 and ma50 < ma200:
                flags.append("left_side_context")

            high_252 = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())
            if high_252 > 0:
                drawdown_from_high = current / high_252 - 1
                metrics["drawdown_from_high"] = round(drawdown_from_high, 4)
                if drawdown_from_high > -0.03:
                    flags.append("near_52w_high")

    try:
        avg_value = float(row.get("avg_volume_value", 0) or 0)
    except Exception:
        avg_value = 0.0
    metrics["avg_volume_value"] = round(avg_value, 2)
    if min_liquidity > 0 and avg_value < min_liquidity * 5:
        flags.append("low_liquidity_buffer")

    return {
        "flags": sorted(set(flags)),
        "metrics": metrics,
    }


def _as_float(value: Any, default: float = 0.0) -> float:
    """숫자 변환 실패를 공통 필터 실패로 번지지 않게 막는다."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _trading_day_gap(last_date: Any, today: str) -> Optional[int]:
    """휴장일 캘린더 없이 대략적인 영업일 gap을 계산한다."""
    try:
        last = pd.to_datetime(last_date).date()
        current = pd.to_datetime(today).date()
    except Exception:
        return None
    if last > current:
        return 0
    # pandas bdate_range는 양 끝을 포함하므로 같은 날이면 0으로 보정한다.
    return max(0, len(pd.bdate_range(last, current)) - 1)


def _assess_common_gate(df: pd.DataFrame, row: pd.Series, gate_cfg: dict, today: str) -> dict:
    """SCOUT v3 공통 문지기.

    v0.1 hard reject:
      - 지원 시장 아님
      - 시총/가격/20일 거래대금 미달
      - OHLCV 길이/신선도/거래량 결측 문제

    needs_review:
      - 최근 5거래일 -25% 급락. 뉴스 자동 확인 전까지 탈락시키지 않는다.
    """
    if not bool((gate_cfg or {}).get("enabled", False)):
        return {"status": "PASS", "hard_fail_reasons": [], "review_flags": [], "metrics": {}}

    country = str(row.get("country", "") or "")
    allowed = set(gate_cfg.get("allowed_countries", []) or [])
    hard_fail_reasons: list[str] = []
    review_flags: list[str] = []
    metrics: dict[str, Any] = {"country": country}

    if allowed and country not in allowed:
        hard_fail_reasons.append("unsupported_country")

    close = pd.Series(dtype=float)
    volume = pd.Series(dtype=float)
    if df is not None and not df.empty:
        try:
            close = df["close"].astype(float).dropna()
            volume = df["volume"].astype(float).reindex(close.index).fillna(0)
        except Exception:
            close = pd.Series(dtype=float)
            volume = pd.Series(dtype=float)

    close_days = int(len(close))
    metrics["close_days"] = close_days
    min_close_days = int(gate_cfg.get("min_close_days", 120) or 120)
    if close_days < min_close_days:
        hard_fail_reasons.append("data_short")

    latest_close = float(close.iloc[-1]) if close_days else 0.0
    metrics["latest_close"] = round(latest_close, 4)
    min_price_map = gate_cfg.get("min_price", {}) or {}
    min_price = _as_float(min_price_map.get(country), 0.0)
    if min_price > 0 and latest_close < min_price:
        hard_fail_reasons.append("price_below_min")

    market_cap = _as_float(row.get("market_cap"), 0.0)
    metrics["market_cap_usd"] = round(market_cap, 2)
    min_cap_map = gate_cfg.get("min_market_cap_usd", {}) or {}
    min_cap = _as_float(min_cap_map.get(country), 0.0)
    if min_cap > 0 and market_cap < min_cap:
        hard_fail_reasons.append("market_cap_below_min")

    if close_days and "date" in df.columns:
        latest_date = df["date"].dropna().iloc[-1] if not df["date"].dropna().empty else None
        stale_days = _trading_day_gap(latest_date, today)
        metrics["latest_date"] = str(pd.to_datetime(latest_date).date()) if latest_date is not None else ""
        metrics["stale_trading_days"] = stale_days
        max_stale = int(gate_cfg.get("max_stale_trading_days", 3) or 3)
        if stale_days is None or stale_days > max_stale:
            hard_fail_reasons.append("data_stale")
    else:
        hard_fail_reasons.append("date_missing")

    if close_days >= 20 and not volume.empty:
        traded_value = close.tail(20) * volume.tail(20)
        avg_traded_value_20d = float(traded_value.mean())
        zero_volume_days_20d = int((volume.tail(20) <= 0).sum())
    else:
        avg_traded_value_20d = 0.0
        zero_volume_days_20d = 20
    metrics["avg_traded_value_20d"] = round(avg_traded_value_20d, 2)
    metrics["zero_volume_days_20d"] = zero_volume_days_20d

    min_value_map = gate_cfg.get("min_avg_traded_value_20d", {}) or {}
    min_value = _as_float(min_value_map.get(country), 0.0)
    if min_value > 0 and avg_traded_value_20d < min_value:
        hard_fail_reasons.append("traded_value_below_min")

    max_zero = int(gate_cfg.get("max_zero_volume_days_20d", 2) or 2)
    if zero_volume_days_20d > max_zero:
        hard_fail_reasons.append("zero_volume_too_many")

    if close_days >= 6:
        ret_5d = latest_close / float(close.iloc[-6]) - 1 if float(close.iloc[-6]) > 0 else 0.0
        metrics["ret_5d"] = round(ret_5d, 4)
        drop_review = float(gate_cfg.get("drop_5d_needs_review_pct", -0.25) or -0.25)
        if ret_5d <= drop_review:
            review_flags.append("sharp_drop_needs_news_review")

    status = "FAIL" if hard_fail_reasons else "NEEDS_REVIEW" if review_flags else "PASS"
    return {
        "status": status,
        "hard_fail_reasons": sorted(set(hard_fail_reasons)),
        "review_flags": sorted(set(review_flags)),
        "metrics": metrics,
    }


def _bench_key_for_row(row: pd.Series) -> str:
    """US/KR 벤치마크 티커. KR 시장 구분이 부족하면 KOSPI를 기본값으로 둔다."""
    country = str(row.get("country", "") or "")
    ticker = str(row.get("ticker", "") or "").upper()
    if country == "US":
        return "SPY"
    if country == "KR" and ticker.endswith(".KQ"):
        return "^KQ11"
    if country == "KR":
        return "^KS11"
    return ""


def _close_series(df: Optional[pd.DataFrame]) -> pd.Series:
    if df is None or df.empty or "close" not in df.columns:
        return pd.Series(dtype=float)
    return df["close"].astype(float).dropna()


def _volume_series(df: Optional[pd.DataFrame], idx: pd.Index) -> pd.Series:
    if df is None or df.empty or "volume" not in df.columns:
        return pd.Series(dtype=float)
    return df["volume"].astype(float).reindex(idx).fillna(0)


def _high_low_series(df: Optional[pd.DataFrame], idx: pd.Index) -> tuple[pd.Series, pd.Series]:
    if df is None or df.empty or "high" not in df.columns or "low" not in df.columns:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    return (
        df["high"].astype(float).reindex(idx),
        df["low"].astype(float).reindex(idx),
    )


def _period_return(close: pd.Series, days: int) -> Optional[float]:
    if len(close) <= days:
        return None
    prev = float(close.iloc[-days - 1])
    if prev <= 0:
        return None
    return float(close.iloc[-1]) / prev - 1


def _atr_pct_series(df: pd.DataFrame, close: pd.Series, length: int) -> pd.Series:
    high, low = _high_low_series(df, close.index)
    if close.empty or high.empty or low.empty:
        return pd.Series(dtype=float)
    prev_close = close.shift(1).fillna(close)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = _rma(tr, length)
    return atr / close.replace(0, np.nan)


def _volume_ratio(volume: pd.Series, short_days: int = 5, long_days: int = 20) -> Optional[float]:
    if len(volume) < long_days or float(volume.tail(long_days).mean()) <= 0:
        return None
    return float(volume.tail(short_days).mean()) / float(volume.tail(long_days).mean())


def _recent_upper_close_count(df: pd.DataFrame, close: pd.Series, days: int = 5) -> int:
    high, low = _high_low_series(df, close.index)
    if len(close) < days or high.empty or low.empty:
        return 0
    recent = pd.DataFrame({"close": close, "high": high, "low": low}).tail(days)
    rng = (recent["high"] - recent["low"]).replace(0, np.nan)
    pos = (recent["close"] - recent["low"]) / rng
    return int((pos >= 0.60).sum())


def _assess_strength_lane(df: pd.DataFrame, bench_df: Optional[pd.DataFrame], cfg: dict) -> dict:
    close = _close_series(df)
    bench = _close_series(bench_df)
    volume = _volume_series(df, close.index)
    metrics: dict[str, Any] = {}
    reasons: list[str] = []
    review_flags: list[str] = []
    if len(close) < 126 or len(bench) < 126:
        return {"status": "FAIL", "reasons": [], "review_flags": ["benchmark_or_price_data_short"], "metrics": metrics}

    ret_20 = _period_return(close, 20)
    ret_63 = _period_return(close, 63)
    ret_126 = _period_return(close, 126)
    b_ret_20 = _period_return(bench, 20)
    b_ret_63 = _period_return(bench, 63)
    b_ret_126 = _period_return(bench, 126)
    rs_20 = (ret_20 - b_ret_20) if ret_20 is not None and b_ret_20 is not None else None
    rs_63 = (ret_63 - b_ret_63) if ret_63 is not None and b_ret_63 is not None else None
    rs_126 = (ret_126 - b_ret_126) if ret_126 is not None and b_ret_126 is not None else None
    metrics.update({
        "ret_20d": round(ret_20 or 0, 4),
        "ret_63d": round(ret_63 or 0, 4),
        "ret_126d": round(ret_126 or 0, 4),
        "rs_20d": round(rs_20 or 0, 4),
        "rs_63d": round(rs_63 or 0, 4),
        "rs_126d": round(rs_126 or 0, 4),
    })

    rs_pass = (
        (rs_63 is not None and rs_63 >= float(cfg.get("rs_63d_min_pctp", 0.05))) or
        (rs_126 is not None and rs_126 >= float(cfg.get("rs_126d_min_pctp", 0.10)))
    )
    if not rs_pass:
        return {"status": "FAIL", "reasons": [], "review_flags": ["relative_strength_fail"], "metrics": metrics}
    reasons.append("relative_strength")

    current = float(close.iloc[-1])
    high_252 = float(close.tail(min(len(close), 252)).max())
    drawdown = current / high_252 - 1 if high_252 > 0 else 0.0
    vol_ratio = _volume_ratio(volume)
    metrics["drawdown_from_252d_high"] = round(drawdown, 4)
    metrics["volume_ratio_5d_20d"] = round(vol_ratio or 0, 4)

    aux_pass = 0
    if drawdown >= float(cfg.get("near_high_pass_drawdown", -0.15)):
        aux_pass += 1
        reasons.append("near_52w_high")
    if vol_ratio is not None and vol_ratio >= float(cfg.get("volume_ratio_5d_20d_min", 1.3)):
        aux_pass += 1
        reasons.append("volume_expansion")
    ma50 = float(close.tail(50).mean()) if len(close) >= 50 else current
    ma200 = float(close.tail(200).mean()) if len(close) >= 200 else ma50
    if current > ma50 and ma50 >= ma200:
        aux_pass += 1
        reasons.append("trend_confirmed")
    if ret_20 is not None and ret_20 >= float(cfg.get("hot_ret_20d_needs_review", 0.25)):
        review_flags.append("hot_needs_pullback")

    status = "STRONG_PASS" if aux_pass >= 3 or drawdown >= float(cfg.get("near_high_strong_drawdown", -0.07)) else "PASS" if aux_pass >= 2 else "FAIL"
    return {"status": status, "reasons": reasons, "review_flags": review_flags, "metrics": metrics}


def _assess_pullback_lane(df: pd.DataFrame, cfg: dict) -> dict:
    close = _close_series(df)
    volume = _volume_series(df, close.index)
    metrics: dict[str, Any] = {}
    reasons: list[str] = []
    review_flags: list[str] = []
    if len(close) < 200:
        return {"status": "FAIL", "reasons": [], "review_flags": ["price_data_short"], "metrics": metrics}

    current = float(close.iloc[-1])
    ma50 = float(close.tail(50).mean())
    ma200 = float(close.tail(200).mean())
    ma50_prev = float(close.iloc[-70:-20].mean()) if len(close) >= 70 else ma50
    high_252 = float(close.tail(min(len(close), 252)).max())
    drawdown = current / high_252 - 1 if high_252 > 0 else 0.0
    vol_ratio = _volume_ratio(volume)
    metrics.update({
        "ma50": round(ma50, 4),
        "ma200": round(ma200, 4),
        "drawdown_from_252d_high": round(drawdown, 4),
        "volume_ratio_5d_20d": round(vol_ratio or 0, 4),
    })

    trend_pass = current >= ma200 and current >= ma50 * (1 + float(cfg.get("ma50_fail_pct", -0.08))) and ma50 >= ma50_prev * 0.98
    if not trend_pass:
        return {"status": "FAIL", "reasons": [], "review_flags": ["trend_not_intact"], "metrics": metrics}
    reasons.append("uptrend_intact")

    aux_pass = 0
    dd_min = float(cfg.get("drawdown_min", -0.25))
    dd_max = float(cfg.get("drawdown_max", -0.08))
    if dd_min <= drawdown <= dd_max:
        aux_pass += 1
        reasons.append("pullback_depth")
        if float(cfg.get("ideal_drawdown_min", -0.20)) <= drawdown <= float(cfg.get("ideal_drawdown_max", -0.10)):
            reasons.append("ideal_pullback_depth")
    if vol_ratio is not None and vol_ratio <= float(cfg.get("volume_ratio_5d_20d_max", 0.75)):
        aux_pass += 1
        reasons.append("volume_dry_up")
    support_near = False
    if abs(current / ma50 - 1) <= float(cfg.get("ma50_near_pct", 0.03)):
        support_near = True
    recent_low = float(close.tail(60).min())
    if recent_low > 0 and abs(current / recent_low - 1) <= float(cfg.get("support_near_pct", 0.04)):
        support_near = True
    if support_near:
        aux_pass += 1
        reasons.append("support_near")

    if vol_ratio is not None and vol_ratio >= float(cfg.get("sell_volume_ratio_review", 1.5)) and drawdown < 0:
        review_flags.append("sell_volume_needs_review")

    status = "STRONG_PASS" if aux_pass >= 3 else "PASS" if aux_pass >= 2 else "WAIT"
    return {"status": status, "reasons": reasons, "review_flags": review_flags, "metrics": metrics}


def _assess_left_side_lane(df: pd.DataFrame, bench_df: Optional[pd.DataFrame], cfg: dict) -> dict:
    close = _close_series(df)
    volume = _volume_series(df, close.index)
    metrics: dict[str, Any] = {}
    reasons: list[str] = []
    review_flags: list[str] = []
    if len(close) < 120:
        return {"status": "FAIL", "stage": "FAIL", "reasons": [], "review_flags": ["price_data_short"], "metrics": metrics}

    current = float(close.iloc[-1])
    lookback = close.tail(min(len(close), 252))
    high_252 = float(lookback.max())
    low_252 = float(lookback.min())
    drawdown = current / high_252 - 1 if high_252 > 0 else 0.0
    from_low = current / low_252 - 1 if low_252 > 0 else 0.0
    metrics.update({
        "drawdown_from_252d_high": round(drawdown, 4),
        "distance_from_252d_low": round(from_low, 4),
    })
    low_zone = from_low <= float(cfg.get("low_252_near_pct", 0.20)) or drawdown <= float(cfg.get("high_252_drawdown_max", -0.30))
    if not low_zone:
        return {"status": "FAIL", "stage": "FAIL", "reasons": [], "review_flags": ["not_low_zone"], "metrics": metrics}
    reasons.append("low_zone")
    if drawdown <= float(cfg.get("extreme_drawdown_review", -0.50)):
        review_flags.append("extreme_drawdown_needs_review")

    decel = 0
    ret_10 = _period_return(close, 10)
    ret_20 = _period_return(close, 20)
    ret_prev20 = None
    if len(close) >= 41 and float(close.iloc[-41]) > 0:
        ret_prev20 = float(close.iloc[-21]) / float(close.iloc[-41]) - 1
    if ret_20 is not None and ret_prev20 is not None and ret_20 < 0 and abs(ret_20) <= abs(ret_prev20) * 0.5:
        decel += 1
        reasons.append("downside_speed_slowing")
    if ret_10 is not None and ret_20 is not None and ret_10 > ret_20:
        decel += 1
        reasons.append("short_return_improving")
    atr_pct = _atr_pct_series(df, close, 14)
    if len(atr_pct.dropna()) >= 20:
        atr10 = float(atr_pct.dropna().tail(10).mean())
        atr20 = float(atr_pct.dropna().tail(20).mean())
        metrics["atr_ratio_10d_20d"] = round(atr10 / atr20, 4) if atr20 > 0 else 0
        if atr20 > 0 and atr10 / atr20 <= float(cfg.get("atr_ratio_10d_20d_max", 0.85)):
            decel += 1
            reasons.append("atr_contracting")
    returns = close.pct_change().dropna()
    if len(returns) >= 30:
        recent_down = float((returns.tail(10) < 0).mean())
        prev_down = float((returns.iloc[-30:-10] < 0).mean())
        metrics["down_day_ratio_10d"] = round(recent_down, 4)
        metrics["down_day_ratio_prev20d"] = round(prev_down, 4)
        if recent_down < prev_down:
            decel += 1
            reasons.append("down_days_decreasing")
    upper_count = _recent_upper_close_count(df, close)
    metrics["upper_close_days_5d"] = upper_count
    if upper_count >= int(cfg.get("upper_close_days_min", 3) or 3):
        decel += 1
        reasons.append("upper_range_closes")
    metrics["deceleration_count"] = decel
    if decel < 2:
        return {"status": "STAGE1_WAIT", "stage": "STAGE1", "reasons": reasons, "review_flags": review_flags, "metrics": metrics}

    higher_low = False
    if len(close) >= 20:
        recent_low = float(close.tail(10).min())
        prev_low = float(close.iloc[-20:-10].min())
        metrics["recent_10d_low"] = round(recent_low, 4)
        metrics["prev_10d_low"] = round(prev_low, 4)
        higher_low = recent_low > prev_low and current >= prev_low
    market_weak = False
    bench = _close_series(bench_df)
    if len(bench) >= 200:
        b_current = float(bench.iloc[-1])
        b_ma200 = float(bench.tail(200).mean())
        b_ret20 = _period_return(bench, 20) or 0.0
        market_weak = b_current < b_ma200 or b_ret20 <= float(cfg.get("sharp_market_ret20_wait", -0.08))
        metrics["benchmark_above_ma200"] = bool(b_current >= b_ma200)
        metrics["benchmark_ret_20d"] = round(b_ret20, 4)

    if not higher_low:
        return {"status": "WAIT_CONFIRM", "stage": "STAGE1", "reasons": reasons, "review_flags": review_flags, "metrics": metrics}
    reasons.append("higher_low")
    if market_weak:
        review_flags.append("market_weak_wait_confirm")
        return {"status": "WAIT_CONFIRM", "stage": "STAGE2", "reasons": reasons, "review_flags": review_flags, "metrics": metrics}

    strong_bonus = False
    if len(close) >= 21 and current > float(close.iloc[-21:-1].max()):
        strong_bonus = True
        reasons.append("higher_high_bonus")
    if len(volume) >= 20 and _volume_ratio(volume) and _volume_ratio(volume) >= 1.5:
        strong_bonus = True
        reasons.append("volume_reversal_bonus")
    status = "STAGE2_STRONG_PASS" if strong_bonus else "STAGE2_PASS"
    return {"status": status, "stage": "STAGE2", "reasons": reasons, "review_flags": review_flags, "metrics": metrics}


def _assess_price_lanes(df: pd.DataFrame, row: pd.Series, benchmark_data: dict[str, pd.DataFrame], lane_cfg: dict) -> dict:
    if not bool((lane_cfg or {}).get("enabled", False)):
        return {}
    bench_key = _bench_key_for_row(row)
    bench_df = benchmark_data.get(bench_key)
    return {
        "benchmark": bench_key,
        "strength": _assess_strength_lane(df, bench_df, lane_cfg.get("strength", {}) or {}),
        "pullback": _assess_pullback_lane(df, lane_cfg.get("pullback", {}) or {}),
        "left_side": _assess_left_side_lane(df, bench_df, lane_cfg.get("left_side", {}) or {}),
    }


def _assess_factor_profile(df: pd.DataFrame, row: pd.Series, factor_cfg: dict, min_liquidity: float) -> dict:
    """가격/거래량 기반 저비용 因子 점수.

    목적: 좋은 종목을 새로 찾기보다, 애매한 후보가 최종 브리핑을 채우는 일을 줄인다.
    """
    if not bool((factor_cfg or {}).get("enabled", False)):
        return {"score": 0.0, "positives": [], "negatives": [], "metrics": {}}

    weights = factor_cfg.get("weights", {}) or {}
    score = 0.0
    positives: list[str] = []
    negatives: list[str] = []
    metrics: dict[str, float | int] = {}

    try:
        close = df["close"].astype(float).dropna()
        high = df["high"].astype(float).reindex(close.index)
        low = df["low"].astype(float).reindex(close.index)
    except Exception:
        close = pd.Series(dtype=float)
        high = pd.Series(dtype=float)
        low = pd.Series(dtype=float)

    close_days = int(len(close))
    metrics["close_days"] = close_days
    if close_days < int(factor_cfg.get("min_close_days", 120) or 120):
        score += float(weights.get("data_short", -0.3))
        negatives.append("data_short")

    try:
        avg_value = float(row.get("avg_volume_value", 0) or 0)
    except Exception:
        avg_value = 0.0
    metrics["avg_volume_value"] = round(avg_value, 2)
    good_liq = min_liquidity * float(factor_cfg.get("liquidity_good_multiple", 10) or 10)
    weak_liq = min_liquidity * float(factor_cfg.get("liquidity_weak_multiple", 3) or 3)
    if min_liquidity > 0 and avg_value >= good_liq:
        score += float(weights.get("liquidity_good", 0.2))
        positives.append("liquidity_good")
    elif min_liquidity > 0 and avg_value < weak_liq:
        score += float(weights.get("liquidity_weak", -0.25))
        negatives.append("liquidity_weak")

    if close_days >= 21:
        current = float(close.iloc[-1])
        prev_20 = float(close.iloc[-21])
        ret_20d = current / prev_20 - 1 if prev_20 > 0 else 0.0
        metrics["ret_20d"] = round(ret_20d, 4)
        max_ret_20d = float(factor_cfg.get("max_ret_20d", 0.20) or 0.20)
        severe_ret_20d = float(factor_cfg.get("severe_ret_20d", 0.35) or 0.35)
        if ret_20d >= severe_ret_20d:
            score += float(weights.get("chasing_extreme", -0.4))
            negatives.append("chasing_extreme")
        elif ret_20d >= max_ret_20d:
            score += float(weights.get("chasing_hot", -0.25))
            negatives.append("chasing_hot")

        high_252 = float(close.iloc[-252:].max()) if close_days >= 252 else float(close.max())
        drawdown = current / high_252 - 1 if high_252 > 0 else 0.0
        metrics["drawdown_from_high"] = round(drawdown, 4)
        if ret_20d < max_ret_20d and drawdown <= float(factor_cfg.get("min_drawdown_from_high", -0.03) or -0.03):
            score += float(weights.get("not_chasing", 0.2))
            positives.append("not_chasing")

    if close_days >= 22 and not high.empty and not low.empty:
        prev_close = close.shift(1).fillna(close)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr20 = _rma(tr, 20)
        current = float(close.iloc[-1])
        atr_pct = float(atr20.iloc[-1]) / current if current > 0 and not np.isnan(atr20.iloc[-1]) else 0.0
        metrics["atr_pct"] = round(atr_pct, 4)
        low_thr = float(factor_cfg.get("atr_pct_low", 0.015) or 0.015)
        high_thr = float(factor_cfg.get("atr_pct_high", 0.09) or 0.09)
        if low_thr <= atr_pct <= high_thr:
            score += float(weights.get("volatility_healthy", 0.2))
            positives.append("volatility_healthy")
        elif atr_pct > high_thr:
            score += float(weights.get("volatility_extreme", -0.25))
            negatives.append("volatility_extreme")

    cap = abs(float(factor_cfg.get("score_cap", 0.6) or 0.6))
    score = max(-cap, min(cap, score))
    return {
        "score": round(score, 3),
        "positives": sorted(set(positives)),
        "negatives": sorted(set(negatives)),
        "metrics": metrics,
    }


def _build_radar_item(
    ticker: str,
    info: dict,
    ticker_themes: dict,
    weights: dict,
    min_liquidity: float,
    m2_history: dict,
    m2_theme_history: dict,
    theme_industry_cfg: dict,
) -> dict:
    """SCOUT 내부 관찰풀/브리핑 공용 후보 객체."""
    row = info["row"]
    matches = ticker_themes.get(_theme_lookup_key(ticker), [])
    theme_score = _theme_bonus(matches, weights)
    liquidity_score = _liquidity_boost(row, min_liquidity, float(weights.get("liquidity_boost", 0.0)))
    factor_score = float((info.get("factor") or {}).get("score", 0.0) or 0.0) * float(weights.get("factor_quality", 1.0))
    signal_score = float(info.get("score", 0.0))
    radar_score = round(signal_score + theme_score + liquidity_score + factor_score, 3)
    signals = _label_signal_dict(info.get("signals", {}))
    signal_keys = list(signals.keys())
    shadow_signals = _label_signal_dict(info.get("shadow_signals", {}))
    shadow_signal_keys = list(shadow_signals.keys())

    item = {
        "ticker": ticker,
        "name": row.get("name", ""),
        "country": row["country"],
        "sector": row.get("sector", ""),
        "market_cap": float(row.get("market_cap", 0) or 0),
        "avg_volume_value": float(row.get("avg_volume_value", 0) or 0),
        "score": radar_score,
        "signal_score": round(signal_score, 3),
        "theme_score": round(theme_score, 3),
        "liquidity_score": round(liquidity_score, 3),
        "factor_score": round(factor_score, 3),
        "factor_context": dict(info.get("factor") or {}),
        "common_gate": dict(info.get("common_gate") or {}),
        "price_lanes": dict(info.get("price_lanes") or {}),
        "signal_count": len(signal_keys),
        "signal_keys": signal_keys,
        "signals": signals,
        "shadow_signal_count": len(shadow_signal_keys),
        "shadow_signal_keys": shadow_signal_keys,
        "shadow_signals": shadow_signals,
        "quality_flags": list((info.get("quality") or {}).get("flags", [])),
        "quality_metrics": dict((info.get("quality") or {}).get("metrics", {})),
        "catalyst_context": {"status": "not_checked", "score": 0.0},
        "theme_industry": _assess_theme_industry(
            ticker=ticker,
            row=row,
            matches=matches,
            m2_history=m2_history,
            m2_theme_history=m2_theme_history,
            cfg=theme_industry_cfg,
        ),
    }

    if matches:
        item["track_d"] = {
            "is_theme_beneficiary": True,
            "matches": matches,
            "track": "D (提前布局)",
        }
    else:
        item["track_d"] = {"is_theme_beneficiary": False}

    return item


CATALYST_POSITIVE_KEYWORDS = {
    "approval", "approved", "beat", "beats", "contract", "deal", "dividend",
    "earnings", "guidance", "launch", "merger", "partnership", "raises",
    "raised", "upgrade", "upgraded", "buyback", "repurchase", "record",
    "expands", "expansion", "acquisition", "order", "profit",
}

CATALYST_RISK_KEYWORDS = {
    "bankruptcy", "cuts", "cut", "downgrade", "downgraded", "fraud", "lawsuit",
    "miss", "misses", "probe", "recall", "investigation", "warning", "slump",
    "plunge", "decline", "halts", "sanction", "fine", "layoff",
}


def _news_symbol(ticker: str, country: str) -> str:
    """Finnhub 뉴스 조회용 심볼. v1은 미국 심볼만 적극 연결한다."""
    symbol = (ticker or "").strip().upper()
    if symbol.lower().endswith(".us"):
        symbol = symbol[:-3]
    if country != "US":
        return ""
    return symbol.split(".")[0]


def _fetch_catalyst_news(ticker: str, country: str, lookback_days: int, max_items: int) -> tuple[str, list[dict]]:
    """SCOUT 촉매 확인용 뉴스 수집.

    v2 범위: FMP가 있으면 미국 후보는 FMP 뉴스/등급/실적을 먼저 보고,
    실패하거나 비어 있으면 기존 Finnhub 뉴스로 폴백한다. 비미국은 별도 소스가
    붙을 때까지 점수에 영향을 주지 않는다.
    """
    try:
        from src.collectors.fmp import fetch_catalyst_news as fetch_fmp_catalyst_news
        fmp_status, fmp_news = fetch_fmp_catalyst_news(
            ticker=ticker,
            country=country,
            lookback_days=lookback_days,
            max_items=max_items,
        )
        if fmp_status == "ok" and fmp_news:
            return "ok", fmp_news
    except Exception as e:
        logger.debug("[scout catalyst] %s FMP 촉매 수집 실패: %s", ticker, e)

    if not bool(FINNHUB_KEY):
        return "no_key", []

    symbol = _news_symbol(ticker, country)
    if not symbol:
        return "non_us", []

    end = datetime.utcnow().date()
    start = end - timedelta(days=max(1, int(lookback_days or 14)))
    params = {
        "symbol": symbol,
        "from": start.strftime("%Y-%m-%d"),
        "to": end.strftime("%Y-%m-%d"),
        "token": FINNHUB_KEY,
    }

    try:
        resp = requests.get(f"{FINNHUB_BASE}/company-news", params=params, timeout=12)
        if resp.status_code != 200:
            return f"http_{resp.status_code}", []
        raw_items = resp.json()
        if not isinstance(raw_items, list):
            return "bad_response", []
        items = []
        for it in raw_items:
            headline = str(it.get("headline", "") or "").strip()
            if not headline:
                continue
            items.append({
                "headline": headline[:180],
                "summary": str(it.get("summary", "") or "").strip()[:300],
                "source": str(it.get("source", "") or "").strip(),
                "datetime": int(it.get("datetime", 0) or 0),
                "url": str(it.get("url", "") or "").strip(),
            })
        items.sort(key=lambda x: x.get("datetime", 0), reverse=True)
        return "ok", items[:max_items]
    except Exception as e:
        logger.debug("[scout catalyst] %s 뉴스 수집 실패: %s", ticker, e)
        return "error", []


def _score_catalyst_news(news: list[dict], score_boost: float, risk_penalty: float) -> dict:
    """뉴스 헤드라인/요약에서 촉매 후보와 리스크 단어를 가볍게 판정한다."""
    positive_hits = []
    risk_hits = []

    for item in news:
        text = f"{item.get('headline', '')} {item.get('summary', '')}".lower()
        pos = sorted({kw for kw in CATALYST_POSITIVE_KEYWORDS if kw in text})
        risk = sorted({kw for kw in CATALYST_RISK_KEYWORDS if kw in text})
        if pos:
            positive_hits.append({"headline": item.get("headline", ""), "keywords": pos[:4]})
        if risk:
            risk_hits.append({"headline": item.get("headline", ""), "keywords": risk[:4]})

    if positive_hits and not risk_hits:
        score = float(score_boost or 0)
    elif risk_hits and not positive_hits:
        score = -float(risk_penalty or 0)
    elif positive_hits and risk_hits:
        score = 0.0
    else:
        score = 0.0

    status = "found" if positive_hits else "risk" if risk_hits else "none"
    return {
        "status": status,
        "score": round(score, 3),
        "positive_hits": positive_hits[:3],
        "risk_hits": risk_hits[:3],
        "news": news[:3],
    }


def _apply_catalyst_layer(radar_items: list[dict], catalyst_cfg: dict) -> dict:
    """레이더 상위 일부에만 촉매 레이어를 적용한다."""
    audit = {
        "enabled": bool((catalyst_cfg or {}).get("enabled", False)),
        "eval_limit": int((catalyst_cfg or {}).get("eval_limit", 0) or 0),
        "evaluated": 0,
        "found": 0,
        "risk": 0,
        "none": 0,
        "non_us": 0,
        "no_key": 0,
        "error": 0,
        "score_boost": float((catalyst_cfg or {}).get("score_boost", 0.0) or 0.0),
        "risk_penalty": float((catalyst_cfg or {}).get("risk_penalty", 0.0) or 0.0),
    }
    if not audit["enabled"] or audit["eval_limit"] <= 0:
        return audit

    lookback_days = int(catalyst_cfg.get("lookback_days", 14) or 14)
    max_news = int(catalyst_cfg.get("max_news_per_ticker", 3) or 3)
    score_boost = float(catalyst_cfg.get("score_boost", 0.3) or 0.0)
    risk_penalty = float(catalyst_cfg.get("risk_penalty", 0.3) or 0.0)

    targets = radar_items[:audit["eval_limit"]]
    for item in targets:
        audit["evaluated"] += 1
        status, news = _fetch_catalyst_news(
            item.get("ticker", ""),
            item.get("country", ""),
            lookback_days=lookback_days,
            max_items=max_news,
        )
        if status == "ok":
            context = _score_catalyst_news(news, score_boost, risk_penalty)
        else:
            context = {"status": status, "score": 0.0, "positive_hits": [], "risk_hits": [], "news": []}

        item["catalyst_context"] = context
        item["catalyst_score"] = round(float(context.get("score", 0.0) or 0.0), 3)
        item["score"] = round(float(item.get("score", 0.0) or 0.0) + item["catalyst_score"], 3)

        ctx_status = str(context.get("status", status) or status)
        if ctx_status == "found":
            audit["found"] += 1
        elif ctx_status == "risk":
            audit["risk"] += 1
        elif ctx_status == "none":
            audit["none"] += 1
        elif ctx_status == "non_us":
            audit["non_us"] += 1
        elif ctx_status == "no_key":
            audit["no_key"] += 1
        else:
            audit["error"] += 1

        time.sleep(0.05)

    return audit


def _rma(series: pd.Series, length: int) -> pd.Series:
    """TradingView ta.rma 근사. 정확한 시각 복제보다 후보 품질 필터 용도."""
    return series.astype(float).ewm(alpha=1 / max(1, int(length)), adjust=False).mean()


def _mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, length: int) -> pd.Series:
    typical = (high.astype(float) + low.astype(float) + close.astype(float)) / 3.0
    money = typical * volume.astype(float)
    direction = typical.diff()
    pos = money.where(direction > 0, 0.0).rolling(length).sum()
    neg = money.where(direction < 0, 0.0).rolling(length).sum().abs()
    ratio = pos / neg.replace(0, np.nan)
    out = 100 - (100 / (1 + ratio))
    return out.fillna(50.0)


def _cross_up(a: pd.Series, b: pd.Series, i: int) -> bool:
    if i <= 0:
        return False
    return bool(a.iloc[i - 1] <= b.iloc[i - 1] and a.iloc[i] > b.iloc[i])


def _cross_down(a: pd.Series, b: pd.Series, i: int) -> bool:
    if i <= 0:
        return False
    return bool(a.iloc[i - 1] >= b.iloc[i - 1] and a.iloc[i] < b.iloc[i])


def _ronin_st_state(df: pd.DataFrame, params: dict) -> pd.Series:
    """메인지표 HA2 SuperTrend 방향 근사. -1=DOWN, 1=UP."""
    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    ha1_close = (open_ + high + low + close) / 4.0
    ha1_open = pd.Series(index=df.index, dtype=float)
    for i in range(len(df)):
        if i == 0 or pd.isna(ha1_open.iloc[i - 1]):
            ha1_open.iloc[i] = (open_.iloc[i] + close.iloc[i]) / 2.0
        else:
            ha1_open.iloc[i] = (ha1_open.iloc[i - 1] + ha1_close.iloc[i - 1]) / 2.0
    ha1_high = pd.concat([high, ha1_open, ha1_close], axis=1).max(axis=1)
    ha1_low = pd.concat([low, ha1_open, ha1_close], axis=1).min(axis=1)

    ha2_close = (ha1_open + ha1_high + ha1_low + ha1_close) / 4.0
    ha2_open = pd.Series(index=df.index, dtype=float)
    for i in range(len(df)):
        if i == 0 or pd.isna(ha2_open.iloc[i - 1]):
            ha2_open.iloc[i] = (ha1_open.iloc[i] + ha1_close.iloc[i]) / 2.0
        else:
            ha2_open.iloc[i] = (ha2_open.iloc[i - 1] + ha2_close.iloc[i - 1]) / 2.0
    ha2_high = pd.concat([ha1_high, ha2_open, ha2_close], axis=1).max(axis=1)
    ha2_low = pd.concat([ha1_low, ha2_open, ha2_close], axis=1).min(axis=1)
    prev_close = ha2_close.shift(1).fillna(ha2_close)
    tr = pd.concat([
        ha2_high - ha2_low,
        (ha2_high - prev_close).abs(),
        (ha2_low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr_st = _rma(tr, int(params.get("st_atr_len", 16)))
    st_mid = (ha2_high + ha2_low) * 0.5
    upper_basic = st_mid + float(params.get("st_factor", 3.8)) * atr_st
    lower_basic = st_mid - float(params.get("st_factor", 3.8)) * atr_st
    hys_atr = float(params.get("st_hys_atr", 0.14))
    st_confirm = int(params.get("st_confirm", 1))

    states = []
    st_upper = np.nan
    st_lower = np.nan
    st_state: int | None = None
    st_candidate: int | None = None
    cand_count = 0
    lock_band = np.nan
    lock_h = np.nan

    for i in range(len(df)):
        if st_state is None:
            st_state = 1 if ha2_close.iloc[i] >= st_mid.iloc[i] else -1
            st_upper = upper_basic.iloc[i]
            st_lower = lower_basic.iloc[i]
            states.append(st_state)
            continue

        prev_upper = st_upper
        prev_lower = st_lower
        if st_state == 1:
            st_lower = lower_basic.iloc[i] if np.isnan(prev_lower) else max(lower_basic.iloc[i], prev_lower)
            st_upper = upper_basic.iloc[i]
        else:
            st_upper = upper_basic.iloc[i] if np.isnan(prev_upper) else min(upper_basic.iloc[i], prev_upper)
            st_lower = lower_basic.iloc[i]

        hys_dist = hys_atr * (atr_st.iloc[i - 1] if i > 0 and not np.isnan(atr_st.iloc[i - 1]) else atr_st.iloc[i])
        ref_line = prev_lower if st_state == 1 else prev_upper
        start_dn = st_state == 1 and not np.isnan(ref_line) and ha2_close.iloc[i] < (ref_line - hys_dist)
        start_up = st_state == -1 and not np.isnan(ref_line) and ha2_close.iloc[i] > (ref_line + hys_dist)

        if st_candidate is None:
            if start_dn:
                st_candidate = -1
                lock_band = ref_line
                lock_h = hys_dist
                cand_count = 1
            elif start_up:
                st_candidate = 1
                lock_band = ref_line
                lock_h = hys_dist
                cand_count = 1
        else:
            passed = ha2_close.iloc[i] < (lock_band - lock_h) if st_candidate == -1 else ha2_close.iloc[i] > (lock_band + lock_h)
            if passed:
                cand_count += 1
                if cand_count >= st_confirm:
                    st_state = st_candidate
                    st_candidate = None
                    cand_count = 0
                    st_upper = upper_basic.iloc[i]
                    st_lower = lower_basic.iloc[i]
            else:
                st_candidate = None
                cand_count = 0

        states.append(st_state)

    return pd.Series(states, index=df.index)


def _ronin_entry_events(df: pd.DataFrame, params: dict) -> dict:
    """메인지표 Entry 원형 중 브리프봇에서 안정적으로 이식 가능한 부분만 근사."""
    min_len = max(
        int(params.get("bb_len", 40)) + int(params.get("bb_reentry_bars", 6)) + 5,
        int(params.get("wt_n1", 18)) + int(params.get("wt_n2", 28)) + int(params.get("wt_n3", 5)) + 5,
        int(params.get("mfi_len", 14)) + int(params.get("mfi_smooth", 5)) + 5,
        int(params.get("st_atr_len", 16)) + 10,
    )
    if len(df) < min_len:
        return {"hit": False, "reason": f"data short ({len(df)} < {min_len})"}

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    volume = df["volume"].astype(float)

    wt_n1 = int(params.get("wt_n1", 18))
    wt_n2 = int(params.get("wt_n2", 28))
    wt_n3 = int(params.get("wt_n3", 5))
    wt_ob = float(params.get("wt_ob", 52.5))
    wt_os = float(params.get("wt_os", -45.0))
    wt_esa = close.ewm(span=wt_n1, adjust=False).mean()
    wt_d = (close - wt_esa).abs().ewm(span=wt_n1, adjust=False).mean()
    wt_ci = (close - wt_esa) / (0.015 * wt_d.replace(0, np.nan))
    wt_tci = wt_ci.ewm(span=wt_n2, adjust=False).mean()
    wt_sig = wt_tci.rolling(wt_n3).mean()

    mfi_len = int(params.get("mfi_len", 14))
    mfi_smooth = int(params.get("mfi_smooth", 5))
    mfi_linger = int(params.get("mfi_linger", 1))
    mfi_os = float(params.get("mfi_os", 38.5))
    mfi_ob = float(params.get("mfi_ob", 64.5))
    mfi_raw = _mfi(high, low, close, volume, mfi_len)
    mfi_val = mfi_raw if mfi_smooth <= 1 else mfi_raw.rolling(mfi_smooth).mean().fillna(mfi_raw)

    bb_len = int(params.get("bb_len", 40))
    bb_mult = float(params.get("bb_mult", 2.08))
    bb_rein = max(1, int(params.get("bb_rein", 2)))
    bb_reentry_bars = int(params.get("bb_reentry_bars", 6))
    bb_basis = close.rolling(bb_len).mean()
    bb_dev = close.rolling(bb_len).std() * bb_mult
    bb_up = bb_basis + bb_dev
    bb_dn = bb_basis - bb_dev
    ttl = int(params.get("ttl_cluster", 2))

    st_state = _ronin_st_state(df, params)

    wt_arm_up = wt_arm_dn = False
    wt_arm_up_outside = wt_arm_dn_outside = 0
    mfi_arm_l = mfi_arm_h = False
    mfi_arm_l_age = mfi_arm_h_age = 0
    mfi_allow_buy = mfi_allow_sell = True
    bb_buy_armed = False
    bb_buy_in_cnt = bb_buy_age = 0
    last_wt_buy = last_mfi_buy = last_bb_buy = None
    entry_events = []
    detail_by_bar = {}

    for i in range(len(df)):
        sig_wt_buy = False
        sig_mfi_buy = False
        sig_bb_buy = False

        if not np.isnan(wt_tci.iloc[i]) and not np.isnan(wt_sig.iloc[i]):
            in_os = wt_tci.iloc[i] <= wt_os
            in_ob = wt_tci.iloc[i] >= wt_ob
            if in_os:
                wt_arm_dn = True
                wt_arm_dn_outside = 0
                wt_arm_up = False
                wt_arm_up_outside = 0
            elif wt_arm_dn:
                wt_arm_dn_outside += 1
                if wt_arm_dn_outside > 2:
                    wt_arm_dn = False
                    wt_arm_dn_outside = 0
            if in_ob:
                wt_arm_up = True
                wt_arm_up_outside = 0
                wt_arm_dn = False
                wt_arm_dn_outside = 0
            elif wt_arm_up:
                wt_arm_up_outside += 1
                if wt_arm_up_outside > 2:
                    wt_arm_up = False
                    wt_arm_up_outside = 0
            if wt_arm_dn and _cross_up(wt_tci, wt_sig, i):
                if in_os or 1 <= wt_arm_dn_outside <= 2:
                    sig_wt_buy = True
                    if not in_os:
                        wt_arm_dn = False
                        wt_arm_dn_outside = 0

        mfi_now = mfi_val.iloc[i]
        if not np.isnan(mfi_now):
            mfi_zone_low = mfi_now <= mfi_os
            mfi_zone_high = mfi_now >= mfi_ob
            pivot_up = i >= 2 and (mfi_val.iloc[i - 1] - mfi_val.iloc[i - 2] < 0) and (mfi_val.iloc[i] - mfi_val.iloc[i - 1] > 0)
            pivot_down = i >= 2 and (mfi_val.iloc[i - 1] - mfi_val.iloc[i - 2] > 0) and (mfi_val.iloc[i] - mfi_val.iloc[i - 1] < 0)
            if mfi_zone_low:
                mfi_arm_l = True
                mfi_arm_h = False
                mfi_arm_l_age = 0
                mfi_arm_h_age = 0
                mfi_allow_buy = True
                mfi_allow_sell = True
            elif mfi_arm_l and not mfi_zone_low:
                mfi_arm_l_age += 1
                if mfi_arm_l_age > mfi_linger:
                    mfi_arm_l = False
                    mfi_arm_l_age = 0
            if mfi_zone_high:
                mfi_arm_h = True
                mfi_arm_l = False
                mfi_arm_h_age = 0
                mfi_arm_l_age = 0
                mfi_allow_buy = True
                mfi_allow_sell = True
            elif mfi_arm_h and not mfi_zone_high:
                mfi_arm_h_age += 1
                if mfi_arm_h_age > mfi_linger:
                    mfi_arm_h = False
                    mfi_arm_h_age = 0
            if pivot_up:
                mfi_allow_sell = True
            if pivot_down:
                mfi_allow_buy = True
            if mfi_arm_l and mfi_allow_buy and pivot_up:
                sig_mfi_buy = True
                mfi_allow_buy = False
                mfi_arm_l = False
                mfi_arm_l_age = 0

        if not np.isnan(bb_dn.iloc[i]) and not np.isnan(bb_up.iloc[i]):
            touch_dn = low.iloc[i] <= bb_dn.iloc[i] <= high.iloc[i]
            outside_dn = close.iloc[i] < bb_dn.iloc[i]
            inside_close = bb_dn.iloc[i] <= close.iloc[i] <= bb_up.iloc[i]
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
                if bb_buy_armed and bb_buy_age >= bb_reentry_bars:
                    bb_buy_armed = False
                    bb_buy_in_cnt = 0
                    bb_buy_age = 0

        if sig_wt_buy:
            last_wt_buy = i
        if sig_mfi_buy:
            last_mfi_buy = i
        if sig_bb_buy:
            last_bb_buy = i

        active = []
        for name, last_idx in [("WT", last_wt_buy), ("MFI", last_mfi_buy), ("BB", last_bb_buy)]:
            if last_idx is not None and i - last_idx <= ttl:
                active.append(name)
        buy_cnt = len(active)
        prev_cnt = detail_by_bar.get(i - 1, {}).get("buy_cnt", 0)
        raw100 = buy_cnt == 3 and prev_cnt != 3
        raw50 = buy_cnt >= 2 and prev_cnt < 2 and not raw100
        final_entry = (raw100 or raw50) and int(st_state.iloc[i]) == -1
        detail_by_bar[i] = {
            "buy_cnt": buy_cnt,
            "active": active,
            "st_state": int(st_state.iloc[i]),
            "raw_type": "3/3" if raw100 else "2/3" if raw50 else "",
        }
        if final_entry:
            entry_events.append(i)

    recent_bars = int(params.get("recent_bars", 5))
    if not entry_events:
        return {
            "hit": False,
            "last_buy_cnt": detail_by_bar.get(len(df) - 1, {}).get("buy_cnt", 0),
            "st_state": int(st_state.iloc[-1]),
        }
    last_event = entry_events[-1]
    age = len(df) - 1 - last_event
    last_detail = detail_by_bar.get(last_event, {})
    return {
        "hit": age <= recent_bars,
        "last_entry_age": int(age),
        "entry_type": last_detail.get("raw_type", ""),
        "active_components": last_detail.get("active", []),
        "st_state": int(st_state.iloc[-1]),
        "recent_bars": recent_bars,
    }


def _signal_ronin_entry_v2(df: pd.DataFrame, params: dict) -> tuple[bool, dict]:
    result = _ronin_entry_events(df, params)
    hit = bool(result.pop("hit", False))
    if not hit and "reason" not in result:
        result["reason"] = "no recent RONIN entry cluster"
    return hit, result


def _signal_ronin_structure_support(df: pd.DataFrame, params: dict) -> tuple[bool, dict]:
    pivot_len = int(params.get("pivot_len", 12))
    volume_ma = int(params.get("volume_ma", 6))
    atr_len = int(params.get("atr_len", 14))
    margin_atr = float(params.get("margin_atr", 0.5))
    max_zones = int(params.get("max_zones", 6))
    if len(df) < pivot_len * 2 + atr_len + 5:
        return False, {"reason": "data short"}

    high = df["high"].astype(float).reset_index(drop=True)
    low = df["low"].astype(float).reset_index(drop=True)
    open_ = df["open"].astype(float).reset_index(drop=True)
    close = df["close"].astype(float).reset_index(drop=True)
    volume = df["volume"].astype(float).reset_index(drop=True)
    tr = pd.concat([
        high - low,
        (high - close.shift(1).fillna(close)).abs(),
        (low - close.shift(1).fillna(close)).abs(),
    ], axis=1).max(axis=1)
    atr = _rma(tr, atr_len)
    vol_sma = volume.rolling(volume_ma).mean()

    supports: list[dict] = []
    resistances: list[dict] = []
    for i in range(pivot_len, len(df) - pivot_len):
        win_low = low.iloc[i - pivot_len:i + pivot_len + 1]
        win_high = high.iloc[i - pivot_len:i + pivot_len + 1]
        vol_ok = volume.iloc[i] > (vol_sma.iloc[i] if not np.isnan(vol_sma.iloc[i]) else 0)
        if vol_ok and low.iloc[i] <= win_low.min():
            zlo = float(low.iloc[i])
            zhi = float(min(open_.iloc[i], close.iloc[i]))
            if zhi <= zlo:
                zhi = zlo
            supports.insert(0, {"lo": zlo, "hi": zhi, "broken": False, "bar": i})
            supports = supports[:max_zones]
        if vol_ok and high.iloc[i] >= win_high.max():
            zhi = float(high.iloc[i])
            zlo = float(max(open_.iloc[i], close.iloc[i]))
            if zlo >= zhi:
                zlo = zhi
            resistances.insert(0, {"lo": zlo, "hi": zhi, "broken": False, "bar": i})
            resistances = resistances[:max_zones]

        for zone in supports:
            if not zone["broken"] and close.iloc[i] < (zone["lo"] + zone["hi"]) / 2:
                zone["broken"] = True
        for zone in resistances:
            if not zone["broken"] and close.iloc[i] > (zone["lo"] + zone["hi"]) / 2:
                zone["broken"] = True

    last_low = float(low.iloc[-1])
    last_close = float(close.iloc[-1])
    margin = float(atr.iloc[-1] if not np.isnan(atr.iloc[-1]) else 0) * margin_atr

    checks = []
    for zone in supports:
        if not zone["broken"]:
            checks.append(("support", zone))
    for zone in resistances:
        if zone["broken"] and zone["hi"] < last_close:
            checks.append(("reclaimed_resistance", zone))

    nearest = None
    for kind, zone in checks:
        in_zone = zone["lo"] <= last_low <= zone["hi"]
        above_near = zone["hi"] < last_low <= zone["hi"] + margin
        if in_zone or above_near:
            dist = 0.0 if in_zone else last_low - zone["hi"]
            if nearest is None or dist < nearest["distance"]:
                nearest = {
                    "kind": kind,
                    "zone_lo": round(zone["lo"], 3),
                    "zone_hi": round(zone["hi"], 3),
                    "distance": round(dist, 3),
                    "margin": round(margin, 3),
                    "bar_age": int(len(df) - 1 - zone["bar"]),
                }

    if nearest:
        return True, nearest
    return False, {"reason": "not near support/reclaimed resistance", "margin": round(margin, 3)}


def _summarize_radar(
    radar_pool: list[dict],
    candidates: list[dict],
    scanned_total: int,
    ohlcv_evaluated: int,
    cooldown_skipped: int,
    by_country: dict,
    by_source: dict,
    filter_audit: dict,
    coverage_thresholds: dict,
) -> dict:
    """브리핑이 '후보 없음'의 이유까지 말할 수 있게 요약한다."""
    signal_counter = Counter()
    country_counter = Counter()
    quality_counter = Counter()
    factor_positive_counter = Counter()
    factor_negative_counter = Counter()
    theme_industry_counter = Counter()
    theme_count = 0
    for item in radar_pool:
        country_counter[item.get("country", "")] += 1
        if item.get("track_d", {}).get("is_theme_beneficiary"):
            theme_count += 1
        for key in item.get("signal_keys", []):
            signal_counter[key] += 1
        for flag in item.get("quality_flags", []):
            quality_counter[flag] += 1
        factor = item.get("factor_context", {}) or {}
        for key in factor.get("positives", []) or []:
            factor_positive_counter[key] += 1
        for key in factor.get("negatives", []) or []:
            factor_negative_counter[key] += 1
        ti_status = str((item.get("theme_industry") or {}).get("status", "") or "")
        if ti_status:
            theme_industry_counter[ti_status] += 1

    coverage_warnings = []
    for country, threshold in (coverage_thresholds or {}).items():
        count = int(by_country.get(country, 0) or 0)
        if count < int(threshold):
            coverage_warnings.append({
                "country": country,
                "count": count,
                "threshold": int(threshold),
            })

    if candidates:
        no_candidate_reason = ""
    elif not radar_pool:
        no_candidate_reason = "관찰풀 기준을 넘은 종목이 없음"
    else:
        no_candidate_reason = "관찰풀은 있으나 최종 보고 기준 미달"

    return {
        "scanned_total": scanned_total,
        "ohlcv_evaluated": ohlcv_evaluated,
        "cooldown_skipped": cooldown_skipped,
        "radar_pool_count": len(radar_pool),
        "brief_pick_count": len(candidates),
        "theme_count": theme_count,
        "top_signals": signal_counter.most_common(5),
        "top_quality_flags": quality_counter.most_common(5),
        "top_factor_positives": factor_positive_counter.most_common(5),
        "top_factor_negatives": factor_negative_counter.most_common(5),
        "theme_industry_status_counts": {str(k): int(v) for k, v in theme_industry_counter.items()},
        "radar_by_country": dict(country_counter),
        "source_counts": by_source,
        "filter_audit": filter_audit,
        "coverage_warnings": coverage_warnings,
        "no_candidate_reason": no_candidate_reason,
    }


def _save_radar_pool(today: str, radar_pool: list[dict], summary: dict) -> dict:
    """넓은 관찰풀은 로이가 보는 시트가 아니라 내부 파일에 저장한다."""
    RADAR_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": today,
        "summary": summary,
        "items": radar_pool,
    }
    json_path = RADAR_DIR / f"radar_pool_{today}.json"
    parquet_path = RADAR_DIR / f"radar_pool_{today}.parquet"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    parquet_ok = False
    try:
        flat_rows = []
        for item in radar_pool:
            flat_rows.append({
                "date": today,
                "ticker": item.get("ticker"),
                "name": item.get("name"),
                "country": item.get("country"),
                "sector": item.get("sector"),
                "market_cap": item.get("market_cap"),
                "avg_volume_value": item.get("avg_volume_value"),
                "score": item.get("score"),
                "signal_score": item.get("signal_score"),
                "theme_score": item.get("theme_score"),
                "liquidity_score": item.get("liquidity_score"),
                "factor_score": item.get("factor_score", 0.0),
                "factor_positives": ",".join(item.get("factor_context", {}).get("positives", [])),
                "factor_negatives": ",".join(item.get("factor_context", {}).get("negatives", [])),
                "common_gate_status": item.get("common_gate", {}).get("status", ""),
                "common_gate_fail_reasons": ",".join(item.get("common_gate", {}).get("hard_fail_reasons", [])),
                "common_gate_review_flags": ",".join(item.get("common_gate", {}).get("review_flags", [])),
                "strength_lane_status": item.get("price_lanes", {}).get("strength", {}).get("status", ""),
                "pullback_lane_status": item.get("price_lanes", {}).get("pullback", {}).get("status", ""),
                "left_side_lane_status": item.get("price_lanes", {}).get("left_side", {}).get("status", ""),
                "theme_industry_status": item.get("theme_industry", {}).get("status", ""),
                "theme_industry_confidence_delta": item.get("theme_industry", {}).get("confidence_delta", 0),
                "sector_rrg_quadrant": item.get("theme_industry", {}).get("sector", {}).get("quadrant", ""),
                "theme_peer_active_count": item.get("theme_industry", {}).get("peer_confirmation", {}).get("active_peer_count", 0),
                "catalyst_score": item.get("catalyst_score", 0.0),
                "catalyst_status": item.get("catalyst_context", {}).get("status", ""),
                "signal_count": item.get("signal_count"),
                "signal_keys": ",".join(item.get("signal_keys", [])),
                "shadow_signal_count": item.get("shadow_signal_count", 0),
                "shadow_signal_keys": ",".join(item.get("shadow_signal_keys", [])),
                "quality_flags": ",".join(item.get("quality_flags", [])),
                "is_theme_beneficiary": item.get("track_d", {}).get("is_theme_beneficiary", False),
            })
        pd.DataFrame(flat_rows).to_parquet(parquet_path, index=False)
        parquet_ok = True
    except Exception as e:
        logger.warning("[scout] radar parquet 저장 실패(json은 저장됨): %s", e)

    return {
        "json": str(json_path),
        "parquet": str(parquet_path) if parquet_ok else "",
    }


def _primary_lane(price_lanes: dict) -> dict:
    """후보의 대표 레인을 하나 고른다. Top3 정식 선발 전까지 스냅샷 표기용."""
    rank = {
        "STAGE2_STRONG_PASS": 5,
        "STRONG_PASS": 5,
        "STAGE2_PASS": 4,
        "PASS": 4,
        "WAIT_CONFIRM": 2,
        "STAGE1_WAIT": 1,
        "WAIT": 1,
        "FAIL": 0,
    }
    best = {"lane": "", "status": "", "rank": -1, "reasons": [], "review_flags": []}
    for lane in ["strength", "pullback", "left_side"]:
        data = dict((price_lanes or {}).get(lane) or {})
        status = str(data.get("status", "") or "")
        score = rank.get(status, -1)
        if score > best["rank"]:
            best = {
                "lane": lane,
                "status": status,
                "rank": score,
                "reasons": list(data.get("reasons") or []),
                "review_flags": list(data.get("review_flags") or []),
            }
    return best


def _snapshot_flat_row(today: str, item: dict, rank_no: int, bucket: str) -> dict:
    lane = _primary_lane(item.get("price_lanes") or {})
    gate = item.get("common_gate") or {}
    catalyst = item.get("catalyst_context") or {}
    factor = item.get("factor_context") or {}
    theme_industry = item.get("theme_industry") or {}
    theme_sector = theme_industry.get("sector") or {}
    theme_peer = theme_industry.get("peer_confirmation") or {}
    return {
        "date": today,
        "bucket": bucket,
        "rank": rank_no,
        "ticker": item.get("ticker", ""),
        "name": item.get("name", ""),
        "country": item.get("country", ""),
        "sector": item.get("sector", ""),
        "score": item.get("score", 0),
        "signal_score": item.get("signal_score", 0),
        "signal_keys": ",".join(item.get("signal_keys", []) or []),
        "primary_lane": lane["lane"],
        "primary_lane_status": lane["status"],
        "primary_lane_reasons": ",".join(lane["reasons"]),
        "primary_lane_review_flags": ",".join(lane["review_flags"]),
        "common_gate_status": gate.get("status", ""),
        "common_gate_review_flags": ",".join(gate.get("review_flags", []) or []),
        "theme_industry_status": theme_industry.get("status", ""),
        "theme_industry_confidence_delta": theme_industry.get("confidence_delta", 0),
        "sector_rrg_quadrant": theme_sector.get("quadrant", ""),
        "theme_peer_active_count": theme_peer.get("active_peer_count", 0),
        "catalyst_status": catalyst.get("status", ""),
        "catalyst_score": catalyst.get("score", 0),
        "factor_score": item.get("factor_score", 0),
        "factor_positives": ",".join(factor.get("positives", []) or []),
        "factor_negatives": ",".join(factor.get("negatives", []) or []),
        "quality_flags": ",".join(item.get("quality_flags", []) or []),
        "market_cap": item.get("market_cap", 0),
        "avg_volume_value": item.get("avg_volume_value", 0),
    }


def _save_recommendation_snapshot(
    today: str,
    candidates: list[dict],
    radar_pool: list[dict],
    radar_summary: dict,
    snapshot_cfg: dict,
) -> dict:
    """최종 추천 당시의 판정 근거를 저장한다.

    이 파일은 사후 성과표의 출발점이다. 나중에 가격 반응/구조 이벤트/실제 진입 여부를
    붙일 때, '그날 왜 추천됐는지'가 사라지지 않게 한다.
    """
    if not bool((snapshot_cfg or {}).get("enabled", False)):
        return {}

    RADAR_DIR.mkdir(parents=True, exist_ok=True)
    radar_top_n = int((snapshot_cfg or {}).get("include_radar_top", 20) or 20)
    payload = {
        "date": today,
        "schema_version": "scout_recommendation_snapshot_v0_1",
        "summary": {
            "candidate_count": int(len(candidates)),
            "radar_top_count": int(min(len(radar_pool), radar_top_n)),
            "common_gate_audit": (radar_summary.get("filter_audit") or {}).get("common_gate_audit", {}),
            "price_lane_audit": (radar_summary.get("filter_audit") or {}).get("price_lane_audit", {}),
            "theme_industry_audit": (radar_summary.get("filter_audit") or {}).get("theme_industry_audit", {}),
            "catalyst_audit": (radar_summary.get("filter_audit") or {}).get("catalyst_audit", {}),
        },
        "candidates": candidates,
        "radar_top": radar_pool[:radar_top_n],
    }

    json_path = RADAR_DIR / f"recommendation_snapshot_{today}.json"
    parquet_path = RADAR_DIR / f"recommendation_snapshot_{today}.parquet"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    parquet_ok = False
    if bool((snapshot_cfg or {}).get("parquet_enabled", True)):
        try:
            flat_rows = []
            for i, item in enumerate(candidates, 1):
                flat_rows.append(_snapshot_flat_row(today, item, i, "candidate"))
            for i, item in enumerate(radar_pool[:radar_top_n], 1):
                flat_rows.append(_snapshot_flat_row(today, item, i, "radar_top"))
            pd.DataFrame(flat_rows).to_parquet(parquet_path, index=False)
            parquet_ok = True
        except Exception as e:
            logger.warning("[scout] recommendation snapshot parquet 저장 실패(json은 저장됨): %s", e)

    return {"json": str(json_path), "parquet": str(parquet_path) if parquet_ok else ""}


def _load_settings() -> dict:
    import yaml
    path = Path(__file__).resolve().parents[2] / "config" / "ronin_settings.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ═══════════════════════════════════════════════════════════
# 사전 감지 신호 — 5개 함수
# ═══════════════════════════════════════════════════════════

def _signal_bb_squeeze(df: pd.DataFrame, params: dict) -> tuple[bool, dict]:
    """BB Width < 20일 평균 × 0.5 → 변동성 압축."""
    length = params["bb_length"]
    mult = params["bb_mult"]
    threshold = params["width_pct_threshold"]
    lookback = params["lookback_avg"]

    needed = length + lookback + 5
    if len(df) < needed:
        return False, {"reason": f"data short ({len(df)} < {needed})"}

    close = df["close"].astype(float)
    sma = close.rolling(length).mean()
    std = close.rolling(length).std()
    upper = sma + mult * std
    lower = sma - mult * std
    bb_width = (upper - lower) / sma  # normalized width

    bb_width_clean = bb_width.dropna()
    if len(bb_width_clean) < lookback + 1:
        return False, {"reason": "bb_width insufficient"}

    current_width = float(bb_width_clean.iloc[-1])
    avg_width = float(bb_width_clean.iloc[-lookback:].mean())

    if avg_width <= 0:
        return False, {"reason": "avg_width zero"}

    ratio = current_width / avg_width
    triggered = ratio < threshold
    return triggered, {
        "current_width": round(current_width, 4),
        "avg_width": round(avg_width, 4),
        "ratio": round(ratio, 3),
        "threshold": threshold,
    }


def _signal_volume_compression(df: pd.DataFrame, params: dict) -> tuple[bool, dict]:
    """5일 거래량 < 20일 평균 × 0.7 → 시장 무관심."""
    short = params["short_days"]
    long_ = params["long_days"]
    threshold = params["ratio_threshold"]

    if len(df) < long_ + 1:
        return False, {"reason": f"data short ({len(df)} < {long_ + 1})"}

    vol = df["volume"].astype(float)
    short_avg = float(vol.iloc[-short:].mean())
    long_avg = float(vol.iloc[-long_:].mean())

    if long_avg <= 0:
        return False, {"reason": "long_avg zero"}

    ratio = short_avg / long_avg
    triggered = ratio < threshold
    return triggered, {
        "short_avg": int(short_avg),
        "long_avg": int(long_avg),
        "ratio": round(ratio, 3),
        "threshold": threshold,
    }


def _signal_after_low_consolidation(df: pd.DataFrame, params: dict) -> tuple[bool, dict]:
    """52주 신저가 후 7~14일 횡보 → 바닥 다지기."""
    low_lookback = params["low_lookback_days"]
    cons_min = params["consolidation_min_days"]
    cons_max = params["consolidation_max_days"]
    range_pct = params["range_pct"]

    if len(df) < low_lookback + cons_max + 5:
        return False, {"reason": "data short"}

    close = df["close"].astype(float)
    low = df["low"].astype(float)

    # 52주 신저가 인덱스 찾기
    window = low.iloc[-low_lookback:]
    low_idx = window.idxmin()
    days_since_low = len(df) - df.index.get_loc(low_idx) - 1

    if days_since_low < cons_min or days_since_low > cons_max:
        return False, {"reason": f"days_since_low={days_since_low} outside [{cons_min},{cons_max}]"}

    # 신저가 이후 횡보 검증
    after_low = close.iloc[-(days_since_low + 1):]
    range_close = (after_low.max() - after_low.min()) / after_low.iloc[0]

    triggered = range_close < range_pct
    return triggered, {
        "days_since_low": days_since_low,
        "range_pct": round(float(range_close), 3),
        "threshold": range_pct,
    }


def _signal_insider_buying(ticker: str, country: str, params: dict) -> tuple[bool, dict]:
    """Insider Buying 1주 내 발생 (미국만, Finviz)."""
    if country != "US":
        return False, {"reason": "non-US"}

    lookback = params["lookback_days"]
    min_count = params["min_count"]

    try:
        from src.collectors.finviz import fetch_fundamental_data
        fund = fetch_fundamental_data(ticker)
        if not fund:
            return False, {"reason": "no fundamental data"}

        # Finviz "Insider Trans" = 6개월 net % (간접 지표)
        # 더 정확히는 fetch_insider_trades 같은 별도 API 필요. 일단 양수면 매수 우세
        insider_trans = fund.get("insider_trans")
        if insider_trans is None:
            return False, {"reason": "no insider_trans"}

        triggered = insider_trans > 0
        return triggered, {
            "insider_trans_pct": insider_trans,
            "lookback_days": lookback,
        }
    except Exception as e:
        logger.debug("[scout insider] %s 실패: %s", ticker, e)
        return False, {"reason": f"error: {e}"}


def _signal_rrg_improving(ticker: str, sector: str, m2_history: dict, params: dict) -> tuple[bool, dict]:
    """섹터 RRG IMPROVING 진입 (최근 N일 내 LAGGING→IMPROVING)."""
    if not sector or not m2_history:
        return False, {"reason": "no sector or m2_history"}

    lookback = params["transition_lookback_days"]

    etf_ticker = _sector_etf_for_name(sector)
    if not etf_ticker:
        return False, {"reason": f"sector '{sector}' not mapped"}

    # 최근 N일 히스토리 확인
    sorted_dates = sorted(m2_history.keys(), reverse=True)
    recent_dates = sorted_dates[:lookback + 1]
    if len(recent_dates) < 2:
        return False, {"reason": "m2_history short"}

    # 어제 LAGGING + 오늘 IMPROVING이면 trigger
    today_q = m2_history.get(recent_dates[0], {}).get(etf_ticker, {}).get("quadrant", "")
    found_transition = False
    for d in recent_dates[1:]:
        prev_q = m2_history.get(d, {}).get(etf_ticker, {}).get("quadrant", "")
        if prev_q == "LAGGING" and today_q == "IMPROVING":
            found_transition = True
            break

    return found_transition, {
        "etf": etf_ticker,
        "today_quadrant": today_q,
        "transition_found": found_transition,
    }


# ═══════════════════════════════════════════════════════════
# Cooldown 관리
# ═══════════════════════════════════════════════════════════

def _is_in_cooldown(ticker: str, cooldown_map: dict, cooldown_days: int, today: str) -> bool:
    """ticker가 최근 N일 내 후보로 출현했는지 확인."""
    last_alert = cooldown_map.get(ticker)
    if not last_alert:
        return False
    try:
        last_date = datetime.strptime(last_alert, "%Y-%m-%d").date()
        today_date = datetime.strptime(today, "%Y-%m-%d").date()
        days_passed = (today_date - last_date).days
        return days_passed < cooldown_days
    except Exception:
        return False


def _update_cooldown(cooldown_map: dict, candidates: list[dict], today: str) -> dict:
    """오늘 출력된 후보를 cooldown에 등록."""
    for c in candidates:
        cooldown_map[c["ticker"]] = today
    # 30일 이상 된 항목 정리
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
    cooldown_map = {k: v for k, v in cooldown_map.items() if v >= cutoff}
    return cooldown_map


# ═══════════════════════════════════════════════════════════
# SCOUT 에이전트
# ═══════════════════════════════════════════════════════════

class ScoutAgent(BaseAgent):
    """SCOUT — 4개국 종목 발굴 + 사전 감지."""

    def __init__(self):
        super().__init__("scout")
        self.settings = _load_settings()

    def run(self, state: dict) -> dict:
        """SCOUT 메인 실행.

        state 입력:
          - date: "2026-04-19"
          - m2_history: dict (REGIME 또는 기존 M2가 채움)
          - scout_cooldown: dict[ticker, last_alert_date]

        반환:
          - candidates: list[dict] 상위 N개
          - scanned_total: int 전체 스캔 수
          - by_country: dict[country, count]
          - cooldown_skipped: int
          - new_cooldown: dict (state에 다시 저장됨)
        """
        scout_cfg = self.settings["scout"]
        signals_required = int(scout_cfg["signals_required"])
        max_output = int(scout_cfg.get("brief_pick_size", scout_cfg["max_candidates_output"]))
        cooldown_days = int(scout_cfg["cooldown_days"])
        radar_pool_size = int(scout_cfg.get("radar_pool_size", 100))
        radar_min_score = float(scout_cfg.get("radar_min_score", 1.0))
        brief_min_score = float(scout_cfg.get("brief_min_score", 2.0))
        weights = scout_cfg.get("scoring_weights", {}) or {}
        min_liquidity = float(scout_cfg.get("avg_volume_value_min_usd", 0) or 0)
        theme_boost_enabled = bool(scout_cfg.get("theme_boost_enabled", True))
        coverage_thresholds = scout_cfg.get("coverage_warning_threshold", {}) or {}
        today = state.get("date", today_kst_str())
        cooldown_map = dict(state.get("scout_cooldown", {}))
        m2_history = state.get("m2_history", {})
        m2_theme_history = state.get("m2_theme_history", {})
        theme_industry_cfg = scout_cfg.get("theme_industry_auditor", {}) or {}
        themes = _load_themes() if theme_boost_enabled else {}
        ticker_themes = _build_ticker_to_themes_map(themes)

        # ── Stage 1: 글로벌 종목 마스터 ──
        from src.collectors.global_universe import fetch_global_universe
        universe = fetch_global_universe(force_refresh=False)
        if universe is None or universe.empty:
            self.log.warning("[scout] universe 비어있음 — 빈 결과 반환")
            return self._empty_result()

        scanned_total = len(universe)
        by_country_total = {
            str(k): int(v) for k, v in universe.groupby("country").size().to_dict().items()
        }
        by_source_total = (
            {str(k): int(v) for k, v in universe.groupby("source").size().to_dict().items()}
            if "source" in universe.columns else {}
        )
        self.log.info("[scout] universe: %d종목 (%s)", scanned_total, by_country_total)

        # ── Stage 2: cooldown 필터링 ──
        cooldown_skipped = 0
        survivors = []
        for _, row in universe.iterrows():
            if _is_in_cooldown(row["ticker"], cooldown_map, cooldown_days, today):
                cooldown_skipped += 1
                continue
            survivors.append(row)
        self.log.info("[scout] cooldown 필터: %d → %d (스킵 %d)",
                      scanned_total, len(survivors), cooldown_skipped)

        if not survivors:
            return self._empty_result(scanned_total=scanned_total, cooldown_skipped=cooldown_skipped)

        # ── Stage 3: 신호 평가 ──
        # OHLCV 필요한 신호 = bb_squeeze, volume_compression, after_low_consolidation
        # OHLCV 불필요 신호 = insider_buying (Finviz), rrg_improving (m2_history)
        # 효율: 모든 종목에 OHLCV 안 주고 일단 OHLCV 무관 신호 먼저 평가, 점수 1+ 인 것만 OHLCV

        # 단계 3a: OHLCV 무관 신호 사전 평가
        insider_cfg = scout_cfg["signals"].get("insider_buying", {}) or {}
        insider_eval_top_us = int(insider_cfg.get("eval_top_us", 250) or 0)
        insider_eval_tickers: set[str] = set()
        if bool(insider_cfg.get("enabled", False)) and insider_eval_top_us > 0:
            us_rows = [row for row in survivors if row.get("country") == "US"]
            us_rows.sort(key=lambda row: -float(row.get("market_cap", 0) or 0))
            insider_eval_tickers = {str(row.get("ticker", "")) for row in us_rows[:insider_eval_top_us]}

        prelim_scores: dict[str, dict] = {}
        insider_skipped_cost_limit = 0
        for row in survivors:
            ticker = row["ticker"]
            country = row["country"]
            sector = row.get("sector", "")
            score = 0
            sigs: dict[str, Any] = {}

            # Insider (US만)
            if bool(insider_cfg.get("enabled", False)) and country == "US":
                if ticker not in insider_eval_tickers:
                    insider_skipped_cost_limit += 1
                    hit, info = False, {"reason": "insider cost limit"}
                else:
                    hit, info = _signal_insider_buying(ticker, country, insider_cfg)
                if hit:
                    score += float(weights.get("insider_buying", 1.0))
                    sigs["insider_buying"] = info

            # RRG (섹터 매핑된 것만)
            if scout_cfg["signals"]["rrg_improving"]["enabled"]:
                hit, info = _signal_rrg_improving(ticker, sector, m2_history, scout_cfg["signals"]["rrg_improving"])
                if hit:
                    score += float(weights.get("rrg_improving", 1.0))
                    sigs["rrg_improving"] = info

            prelim_scores[ticker] = {
                "row": row,
                "score": score,
                "signals": sigs,
                "shadow_signals": {},
            }

        # OHLCV 평가는 — 효율 위해 prelim_scores 점수 0이 아니거나, 무작위 샘플링 통과한 것만
        # 실제 운용: 모든 종목에 OHLCV 평가하면 너무 무거움. 우선 prelim score >= 1 인 것 + 시총 상위 30%
        ohlcv_targets = self._select_ohlcv_targets(prelim_scores, signals_required)
        self.log.info("[scout] OHLCV 평가 대상: %d종목", len(ohlcv_targets))

        # ── Stage 3b: OHLCV 신호 평가 ──
        factor_cfg = scout_cfg.get("factor_layer", {}) or {}
        common_gate_cfg = scout_cfg.get("common_gate", {}) or {}
        price_lanes_cfg = scout_cfg.get("price_lanes", {}) or {}
        if ohlcv_targets:
            from src.collectors.global_ohlcv import fetch_ohlcv
            tickers_by_country: dict[str, list[str]] = {}
            for t, info in ohlcv_targets.items():
                country = info["row"]["country"]
                tickers_by_country.setdefault(country, []).append(t)
            if bool(price_lanes_cfg.get("enabled", False)):
                countries = {str(info["row"].get("country", "")) for info in ohlcv_targets.values()}
                if "US" in countries:
                    tickers_by_country.setdefault("US", []).append("SPY")
                if "KR" in countries:
                    tickers_by_country.setdefault("KR", []).extend(["^KS11", "^KQ11"])

            ohlcv_data = fetch_ohlcv(tickers_by_country, lookback_days=260, use_cache=True)
            benchmark_data = {
                key: ohlcv_data.get(key)
                for key in ["SPY", "^KS11", "^KQ11"]
                if ohlcv_data.get(key) is not None
            }

            for ticker, info in ohlcv_targets.items():
                df = ohlcv_data.get(ticker)
                if df is None or df.empty:
                    info["common_gate"] = {
                        "status": "FAIL",
                        "hard_fail_reasons": ["ohlcv_missing"],
                        "review_flags": [],
                        "metrics": {"country": str(info["row"].get("country", ""))},
                    }
                    info["score"] = 0.0
                    info["signals"] = {}
                    info["shadow_signals"] = {}
                    continue

                common_gate = _assess_common_gate(df, info["row"], common_gate_cfg, today)
                info["common_gate"] = common_gate
                if common_gate.get("status") == "FAIL":
                    info["score"] = 0.0
                    info["signals"] = {}
                    info["shadow_signals"] = {}
                    continue

                info["quality"] = _assess_quality_context(df, info["row"], min_liquidity)
                info["factor"] = _assess_factor_profile(df, info["row"], factor_cfg, min_liquidity)
                info["price_lanes"] = _assess_price_lanes(df, info["row"], benchmark_data, price_lanes_cfg)

                # bb_squeeze
                if scout_cfg["signals"]["bb_squeeze"]["enabled"]:
                    hit, sig_info = _signal_bb_squeeze(df, scout_cfg["signals"]["bb_squeeze"])
                    if hit:
                        info["score"] += float(weights.get("bb_squeeze", 1.0))
                        info["signals"]["bb_squeeze"] = sig_info

                # volume_compression
                if scout_cfg["signals"]["volume_compression"]["enabled"]:
                    hit, sig_info = _signal_volume_compression(df, scout_cfg["signals"]["volume_compression"])
                    if hit:
                        info["score"] += float(weights.get("volume_compression", 1.0))
                        info["signals"]["volume_compression"] = sig_info

                # after_low_consolidation
                if scout_cfg["signals"]["after_low_consolidation"]["enabled"]:
                    hit, sig_info = _signal_after_low_consolidation(df, scout_cfg["signals"]["after_low_consolidation"])
                    if hit:
                        info["score"] += float(weights.get("after_low_consolidation", 1.0))
                        info["signals"]["after_low_consolidation"] = sig_info

                # RONIN Entry v2 근사: WT/MFI/BB 공진 + ST DOWN
                ronin_entry_cfg = scout_cfg["signals"].get("ronin_entry_v2", {}) or {}
                if bool(ronin_entry_cfg.get("enabled", False)):
                    hit, sig_info = _signal_ronin_entry_v2(df, ronin_entry_cfg)
                    if hit:
                        if bool(ronin_entry_cfg.get("shadow_mode", False)):
                            info.setdefault("shadow_signals", {})["ronin_entry_v2"] = sig_info
                        else:
                            info["score"] += float(weights.get("ronin_entry_v2", 1.0))
                            info["signals"]["ronin_entry_v2"] = sig_info

                # 구조 지지 근접 근사: 피벗 지지/돌파 저항 근처
                structure_cfg = scout_cfg["signals"].get("ronin_structure_support", {}) or {}
                if bool(structure_cfg.get("enabled", False)):
                    hit, sig_info = _signal_ronin_structure_support(df, structure_cfg)
                    if hit:
                        if bool(structure_cfg.get("shadow_mode", False)):
                            info.setdefault("shadow_signals", {})["ronin_structure_support"] = sig_info
                        else:
                            info["score"] += float(weights.get("ronin_structure_support", 1.0))
                            info["signals"]["ronin_structure_support"] = sig_info

        # ── Stage 4: 내부 Radar Pool 구성 ──
        signal_counter = Counter()
        shadow_signal_counter = Counter()
        with_signal_count = 0
        with_shadow_signal_count = 0
        for info in prelim_scores.values():
            sig_keys = list((info.get("signals") or {}).keys())
            if sig_keys:
                with_signal_count += 1
            for key in sig_keys:
                signal_counter[key] += 1
            shadow_keys = list((info.get("shadow_signals") or {}).keys())
            if shadow_keys:
                with_shadow_signal_count += 1
            for key in shadow_keys:
                shadow_signal_counter[key] += 1

        ohlcv_missing = []
        if ohlcv_targets:
            ohlcv_missing = [t for t in ohlcv_targets if t not in ohlcv_data]

        survivors_by_country = Counter()
        for row in survivors:
            survivors_by_country[str(row.get("country", ""))] += 1

        ohlcv_by_country = Counter()
        missing_by_country = Counter()
        for ticker, info in ohlcv_targets.items():
            country = str(info["row"].get("country", ""))
            ohlcv_by_country[country] += 1
            if ticker in ohlcv_missing:
                missing_by_country[country] += 1

        radar_eligible = []
        common_gate_counter = Counter()
        common_gate_fail_counter = Counter()
        common_gate_review_counter = Counter()
        lane_status_counter = Counter()
        for ticker, info in prelim_scores.items():
            gate = info.get("common_gate") or {}
            gate_status = str(gate.get("status", "NOT_EVALUATED"))
            common_gate_counter[gate_status] += 1
            for reason in gate.get("hard_fail_reasons", []) or []:
                common_gate_fail_counter[str(reason)] += 1
            for flag in gate.get("review_flags", []) or []:
                common_gate_review_counter[str(flag)] += 1

            if bool(common_gate_cfg.get("enabled", False)) and gate_status in {"FAIL", "NOT_EVALUATED"}:
                continue

            item = _build_radar_item(
                ticker,
                info,
                ticker_themes,
                weights,
                min_liquidity,
                m2_history,
                m2_theme_history,
                theme_industry_cfg,
            )
            for lane_key in ["strength", "pullback", "left_side"]:
                lane_status = item.get("price_lanes", {}).get(lane_key, {}).get("status", "")
                if lane_status:
                    lane_status_counter[f"{lane_key}:{lane_status}"] += 1
            if item["score"] >= radar_min_score and (item["signal_count"] > 0 or item["theme_score"] > 0):
                radar_eligible.append(item)

        radar_eligible.sort(key=lambda x: (-x["score"], -x["signal_count"], -x["market_cap"]))
        _attach_theme_peer_confirmation(
            radar_eligible,
            top_n=int((theme_industry_cfg or {}).get("peer_confirm_top_n", 30) or 30),
        )
        catalyst_audit = _apply_catalyst_layer(radar_eligible, scout_cfg.get("catalyst", {}) or {})
        radar_eligible.sort(key=lambda x: (-x["score"], -x["signal_count"], -x["market_cap"]))
        radar_pool = radar_eligible[:radar_pool_size]

        # ── Stage 5: 로이에게 보고할 엄선 후보만 추출 ──
        quality_gate = scout_cfg.get("brief_quality_gate", {}) or {}

        def _passes_brief_quality_gate(item: dict) -> bool:
            if not bool(quality_gate.get("enabled", False)):
                return True
            signal_keys = set(item.get("signal_keys", []) or [])
            if bool(quality_gate.get("allow_ronin_entry_v2", True)) and "ronin_entry_v2" in signal_keys:
                return True
            if bool(quality_gate.get("allow_catalyst_found", True)) and item.get("catalyst_context", {}).get("status") == "found":
                return True
            min_signal_count = int(quality_gate.get("allow_signal_count_at_least", 4) or 0)
            if min_signal_count > 0 and int(item.get("signal_count", 0) or 0) >= min_signal_count:
                return True
            return False

        candidates = [
            item for item in radar_pool
            if (item["score"] >= brief_min_score or item["signal_count"] >= signals_required)
            and _passes_brief_quality_gate(item)
        ][:max_output]

        filter_audit = {
            "hard_filter": {
                "universe": int(scanned_total),
                "cooldown_skipped": int(cooldown_skipped),
                "after_cooldown": int(len(survivors)),
                "after_cooldown_by_country": dict(survivors_by_country),
            },
            "cost_control": {
                "insider_eval_top_us": int(insider_eval_top_us),
                "insider_skipped_cost_limit": int(insider_skipped_cost_limit),
            },
            "factor_audit": {
                "enabled": bool(factor_cfg.get("enabled", False)),
                "score_cap": float(factor_cfg.get("score_cap", 0.0) or 0.0),
                "score_weight": float(weights.get("factor_quality", 0.0) or 0.0),
            },
            "common_gate_audit": {
                "enabled": bool(common_gate_cfg.get("enabled", False)),
                "status_counts": {str(k): int(v) for k, v in common_gate_counter.items()},
                "fail_reasons": {str(k): int(v) for k, v in common_gate_fail_counter.items()},
                "review_flags": {str(k): int(v) for k, v in common_gate_review_counter.items()},
                "allowed_countries": list(common_gate_cfg.get("allowed_countries", []) or []),
            },
            "price_lane_audit": {
                "enabled": bool(price_lanes_cfg.get("enabled", False)),
                "status_counts": {str(k): int(v) for k, v in lane_status_counter.items()},
            },
            "theme_industry_audit": {
                "enabled": bool(theme_industry_cfg.get("enabled", False)),
                "reject_authority": False,
                "uses_m2_history": bool(m2_history),
                "uses_m2_theme_history": bool(m2_theme_history),
                "support_quadrants": list(theme_industry_cfg.get("support_quadrants", []) or []),
                "min_group_support_etfs": int(theme_industry_cfg.get("min_group_support_etfs", 2) or 2),
            },
            "evaluation_scope": {
                "ohlcv_selected": int(len(ohlcv_targets)),
                "ohlcv_not_selected": int(max(0, len(survivors) - len(ohlcv_targets))),
                "ohlcv_missing": int(len(ohlcv_missing)),
                "ohlcv_selected_by_country": dict(ohlcv_by_country),
                "ohlcv_missing_by_country": dict(missing_by_country),
            },
            "signal_audit": {
                "with_signal": int(with_signal_count),
                "without_signal": int(max(0, len(prelim_scores) - with_signal_count)),
                "hit_counts": {str(k): int(v) for k, v in signal_counter.items()},
                "with_shadow_signal": int(with_shadow_signal_count),
                "shadow_hit_counts": {str(k): int(v) for k, v in shadow_signal_counter.items()},
            },
            "radar_audit": {
                "radar_min_score": float(radar_min_score),
                "radar_eligible_before_cap": int(len(radar_eligible)),
                "radar_pool_cap": int(radar_pool_size),
                "radar_cap_dropped": int(max(0, len(radar_eligible) - radar_pool_size)),
                "brief_min_score": float(brief_min_score),
                "signals_required": int(signals_required),
                "brief_quality_gate": dict(quality_gate),
                "brief_rejected_after_radar": int(max(0, len(radar_pool) - len(candidates))),
                "brief_picks": int(len(candidates)),
            },
            "catalyst_audit": catalyst_audit,
        }

        radar_summary = _summarize_radar(
            radar_pool=radar_pool,
            candidates=candidates,
            scanned_total=scanned_total,
            ohlcv_evaluated=len(ohlcv_targets),
            cooldown_skipped=cooldown_skipped,
            by_country=by_country_total,
            by_source=by_source_total,
            filter_audit=filter_audit,
            coverage_thresholds=coverage_thresholds,
        )

        try:
            radar_paths = _save_radar_pool(today, radar_pool, radar_summary)
        except Exception as e:
            radar_paths = {}
            self.log.warning("[scout] radar pool 저장 실패: %s", e)

        self.log.info("[scout] 최종 후보: %d개 (Track D 매핑 %d개)", 
                      len(candidates), 
                      sum(1 for c in candidates if c.get("track_d", {}).get("is_theme_beneficiary")))

        # ── M1.5 买入三问 LLM 보강 (Z3-4, D74/D78/D80) ──
        # 후보별 풀 분석 (산업/thesis/catalyst/Q1-Q3/리스크/별점) LLM 호출.
        # 실패해도 SCOUT 결과는 그대로 반환 (안정성).
        if candidates:
            try:
                from src.modules.m1_5_buyquestions import run_m1_5_buy_questions
                run_m1_5_buy_questions(candidates, today=today)
            except Exception as e:
                self.log.warning("[scout] M1.5 LLM 보강 실패 (계속 진행): %s", e)

        try:
            snapshot_paths = _save_recommendation_snapshot(
                today=today,
                candidates=candidates,
                radar_pool=radar_pool,
                radar_summary=radar_summary,
                snapshot_cfg=scout_cfg.get("recommendation_snapshot", {}) or {},
            )
        except Exception as e:
            snapshot_paths = {}
            self.log.warning("[scout] recommendation snapshot 저장 실패: %s", e)

        # ── cooldown 갱신 ──
        new_cooldown = _update_cooldown(cooldown_map, candidates, today)

        return {
            "candidates": candidates,
            "scanned_total": scanned_total,
            "by_country": by_country_total,
            "cooldown_skipped": cooldown_skipped,
            "new_cooldown": new_cooldown,
            "ohlcv_evaluated": len(ohlcv_targets),
            "radar_pool": radar_pool[:10],
            "radar_summary": radar_summary,
            "radar_paths": radar_paths,
            "recommendation_snapshot_paths": snapshot_paths,
            "today": today,
        }

    def _select_ohlcv_targets(self, prelim_scores: dict, signals_required: int) -> dict:
        """OHLCV 평가 대상 선별 (효율).

        조건:
          - prelim_score 이미 >= 1 → 무조건 포함 (확실한 후보)
          - 나머지: 각 국가별 시총 상위 200종목
        """
        # 우선순위 1: 이미 점수 있는 종목
        confirmed = {t: i for t, i in prelim_scores.items() if i["score"] >= 1}

        # 우선순위 2: 점수 0인데 시총 상위만 선별
        zero_score = [(t, i) for t, i in prelim_scores.items() if i["score"] == 0]

        scout_cfg = self.settings["scout"]
        top_per_country = int(scout_cfg.get("ohlcv_top_per_country", 200))

        # 국가별 시총 상위 N종목씩
        by_country: dict[str, list] = {}
        for t, info in zero_score:
            country = info["row"]["country"]
            by_country.setdefault(country, []).append((t, info))

        top_picks = {}
        for country, items in by_country.items():
            items.sort(key=lambda x: -float(x[1]["row"].get("market_cap", 0)))
            for t, info in items[:top_per_country]:
                top_picks[t] = info

        # 합본
        result = {**confirmed, **top_picks}
        return result

    def _empty_result(self, scanned_total: int = 0, cooldown_skipped: int = 0) -> dict:
        radar_summary = {
            "scanned_total": scanned_total,
            "ohlcv_evaluated": 0,
            "cooldown_skipped": cooldown_skipped,
            "radar_pool_count": 0,
            "brief_pick_count": 0,
            "theme_count": 0,
            "top_signals": [],
            "top_quality_flags": [],
            "top_factor_positives": [],
            "top_factor_negatives": [],
            "radar_by_country": {},
            "source_counts": {},
            "filter_audit": {},
            "coverage_warnings": [],
            "no_candidate_reason": "유니버스가 비었거나 재선정대기 필터 후 남은 종목이 없음",
        }
        return {
            "candidates": [],
            "scanned_total": scanned_total,
            "by_country": {},
            "cooldown_skipped": cooldown_skipped,
            "new_cooldown": {},
            "ohlcv_evaluated": 0,
            "radar_pool": [],
            "radar_summary": radar_summary,
            "radar_paths": {},
            "today": today_kst_str(),
        }

    def _error_output(self, error_msg: str) -> dict:
        return {
            "candidates": [],
            "scanned_total": 0,
            "by_country": {},
            "cooldown_skipped": 0,
            "new_cooldown": {},
            "ohlcv_evaluated": 0,
            "radar_pool": [],
            "radar_summary": {
                "radar_pool_count": 0,
                "brief_pick_count": 0,
                "no_candidate_reason": error_msg,
                "top_signals": [],
                "top_quality_flags": [],
                "top_factor_positives": [],
                "top_factor_negatives": [],
                "source_counts": {},
                "filter_audit": {},
                "coverage_warnings": [],
            },
            "radar_paths": {},
            "today": today_kst_str(),
            "error": error_msg,
        }
