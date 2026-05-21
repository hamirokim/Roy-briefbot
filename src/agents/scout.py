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
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.agents.base import BaseAgent
from src.utils import today_kst_str

logger = logging.getLogger(__name__)

RADAR_DIR = Path(__file__).resolve().parents[2] / "data" / "scout"


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


def _build_radar_item(ticker: str, info: dict, ticker_themes: dict, weights: dict, min_liquidity: float) -> dict:
    """SCOUT 내부 관찰풀/브리핑 공용 후보 객체."""
    row = info["row"]
    matches = ticker_themes.get(_theme_lookup_key(ticker), [])
    theme_score = _theme_bonus(matches, weights)
    liquidity_score = _liquidity_boost(row, min_liquidity, float(weights.get("liquidity_boost", 0.0)))
    signal_score = float(info.get("score", 0.0))
    radar_score = round(signal_score + theme_score + liquidity_score, 3)
    signals = _label_signal_dict(info.get("signals", {}))
    signal_keys = list(signals.keys())

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
        "signal_count": len(signal_keys),
        "signal_keys": signal_keys,
        "signals": signals,
        "quality_flags": list((info.get("quality") or {}).get("flags", [])),
        "quality_metrics": dict((info.get("quality") or {}).get("metrics", {})),
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
    theme_count = 0
    for item in radar_pool:
        country_counter[item.get("country", "")] += 1
        if item.get("track_d", {}).get("is_theme_beneficiary"):
            theme_count += 1
        for key in item.get("signal_keys", []):
            signal_counter[key] += 1
        for flag in item.get("quality_flags", []):
            quality_counter[flag] += 1

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
                "signal_count": item.get("signal_count"),
                "signal_keys": ",".join(item.get("signal_keys", [])),
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

    # 섹터명 → ETF 매핑 (주요 미국 섹터)
    sector_etf_map = {
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
    etf_ticker = sector_etf_map.get(sector)
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
            }

        # OHLCV 평가는 — 효율 위해 prelim_scores 점수 0이 아니거나, 무작위 샘플링 통과한 것만
        # 실제 운용: 모든 종목에 OHLCV 평가하면 너무 무거움. 우선 prelim score >= 1 인 것 + 시총 상위 30%
        ohlcv_targets = self._select_ohlcv_targets(prelim_scores, signals_required)
        self.log.info("[scout] OHLCV 평가 대상: %d종목", len(ohlcv_targets))

        # ── Stage 3b: OHLCV 신호 평가 ──
        if ohlcv_targets:
            from src.collectors.global_ohlcv import fetch_ohlcv
            tickers_by_country: dict[str, list[str]] = {}
            for t, info in ohlcv_targets.items():
                country = info["row"]["country"]
                tickers_by_country.setdefault(country, []).append(t)

            ohlcv_data = fetch_ohlcv(tickers_by_country, lookback_days=260, use_cache=True)

            for ticker, info in ohlcv_targets.items():
                df = ohlcv_data.get(ticker)
                if df is None or df.empty:
                    continue

                info["quality"] = _assess_quality_context(df, info["row"], min_liquidity)

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

        # ── Stage 4: 내부 Radar Pool 구성 ──
        signal_counter = Counter()
        with_signal_count = 0
        for info in prelim_scores.values():
            sig_keys = list((info.get("signals") or {}).keys())
            if sig_keys:
                with_signal_count += 1
            for key in sig_keys:
                signal_counter[key] += 1

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
        for ticker, info in prelim_scores.items():
            item = _build_radar_item(ticker, info, ticker_themes, weights, min_liquidity)
            if item["score"] >= radar_min_score and (item["signal_count"] > 0 or item["theme_score"] > 0):
                radar_eligible.append(item)

        radar_eligible.sort(key=lambda x: (-x["score"], -x["signal_count"], -x["market_cap"]))
        radar_pool = radar_eligible[:radar_pool_size]

        # ── Stage 5: 로이에게 보고할 엄선 후보만 추출 ──
        candidates = [
            item for item in radar_pool
            if item["score"] >= brief_min_score or item["signal_count"] >= signals_required
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
            },
            "radar_audit": {
                "radar_min_score": float(radar_min_score),
                "radar_eligible_before_cap": int(len(radar_eligible)),
                "radar_pool_cap": int(radar_pool_size),
                "radar_cap_dropped": int(max(0, len(radar_eligible) - radar_pool_size)),
                "brief_min_score": float(brief_min_score),
                "signals_required": int(signals_required),
                "brief_rejected_after_radar": int(max(0, len(radar_pool) - len(candidates))),
                "brief_picks": int(len(candidates)),
            },
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
                "source_counts": {},
                "filter_audit": {},
                "coverage_warnings": [],
            },
            "radar_paths": {},
            "today": today_kst_str(),
            "error": error_msg,
        }
