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

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.agents.base import BaseAgent
from src.utils import today_kst_str

logger = logging.getLogger(__name__)


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
        "Technology": "xlk.us",
        "Healthcare": "xlv.us",
        "Health Care": "xlv.us",
        "Financials": "xlf.us",
        "Financial": "xlf.us",
        "Consumer Cyclical": "xly.us",
        "Consumer Discretionary": "xly.us",
        "Consumer Defensive": "xlp.us",
        "Consumer Staples": "xlp.us",
        "Energy": "xle.us",
        "Industrials": "xli.us",
        "Materials": "xlb.us",
        "Basic Materials": "xlb.us",
        "Communication Services": "xlc.us",
        "Utilities": "xlu.us",
        "Real Estate": "xlre.us",
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
        signals_required = scout_cfg["signals_required"]
        max_output = scout_cfg["max_candidates_output"]
        cooldown_days = scout_cfg["cooldown_days"]
        today = state.get("date", today_kst_str())
        cooldown_map = dict(state.get("scout_cooldown", {}))
        m2_history = state.get("m2_history", {})

        # ── Stage 1: 글로벌 종목 마스터 ──
        from src.collectors.global_universe import fetch_global_universe
        universe = fetch_global_universe(force_refresh=False)
        if universe is None or universe.empty:
            self.log.warning("[scout] universe 비어있음 — 빈 결과 반환")
            return self._empty_result()

        scanned_total = len(universe)
        by_country_total = universe.groupby("country").size().to_dict()
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
        prelim_scores: dict[str, dict] = {}
        for row in survivors:
            ticker = row["ticker"]
            country = row["country"]
            sector = row.get("sector", "")
            score = 0
            sigs: dict[str, Any] = {}

            # Insider (US만)
            if scout_cfg["signals"]["insider_buying"]["enabled"]:
                hit, info = _signal_insider_buying(ticker, country, scout_cfg["signals"]["insider_buying"])
                if hit:
                    score += 1
                    sigs["insider_buying"] = info

            # RRG (섹터 매핑된 것만)
            if scout_cfg["signals"]["rrg_improving"]["enabled"]:
                hit, info = _signal_rrg_improving(ticker, sector, m2_history, scout_cfg["signals"]["rrg_improving"])
                if hit:
                    score += 1
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

                # bb_squeeze
                if scout_cfg["signals"]["bb_squeeze"]["enabled"]:
                    hit, sig_info = _signal_bb_squeeze(df, scout_cfg["signals"]["bb_squeeze"])
                    if hit:
                        info["score"] += 1
                        info["signals"]["bb_squeeze"] = sig_info

                # volume_compression
                if scout_cfg["signals"]["volume_compression"]["enabled"]:
                    hit, sig_info = _signal_volume_compression(df, scout_cfg["signals"]["volume_compression"])
                    if hit:
                        info["score"] += 1
                        info["signals"]["volume_compression"] = sig_info

                # after_low_consolidation
                if scout_cfg["signals"]["after_low_consolidation"]["enabled"]:
                    hit, sig_info = _signal_after_low_consolidation(df, scout_cfg["signals"]["after_low_consolidation"])
                    if hit:
                        info["score"] += 1
                        info["signals"]["after_low_consolidation"] = sig_info

        # ── Stage 4: 최종 후보 선정 ──
        candidates = []
        for ticker, info in prelim_scores.items():
            if info["score"] >= signals_required:
                row = info["row"]
                candidates.append({
                    "ticker": ticker,
                    "name": row.get("name", ""),
                    "country": row["country"],
                    "sector": row.get("sector", ""),
                    "market_cap": float(row.get("market_cap", 0)),
                    "score": info["score"],
                    "signals": info["signals"],
                })

        # 점수 높은 순, 동점 시 시총 큰 순
        candidates.sort(key=lambda x: (-x["score"], -x["market_cap"]))
        candidates = candidates[:max_output]

        # === Z1 신규: 신호 명명 강화 + Track D 提前布局 매핑 ===
        themes = _load_themes()
        ticker_themes = _build_ticker_to_themes_map(themes)
        
        for c in candidates:
            ticker = c["ticker"]
            
            # 신호 한글 라벨 추가
            sig_dict = c.get("signals", {})
            labeled_signals = {}
            for sig_key, sig_info in sig_dict.items():
                label_data = SIGNAL_LABELS.get(sig_key, {})
                labeled_signals[sig_key] = {
                    **sig_info,
                    "label_ko": label_data.get("ko", sig_key),
                    "phase": label_data.get("zh_phase", ""),
                }
            c["signals"] = labeled_signals
            
            # Track D: themes.yaml 매핑된 종목인가?
            theme_matches = ticker_themes.get(ticker, [])
            if theme_matches:
                c["track_d"] = {
                    "is_theme_beneficiary": True,
                    "matches": theme_matches,
                    "track": "D (提前布局)",
                }
            else:
                c["track_d"] = {"is_theme_beneficiary": False}

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

        # 국가별 시총 상위 200종목씩
        by_country: dict[str, list] = {}
        for t, info in zero_score:
            country = info["row"]["country"]
            by_country.setdefault(country, []).append((t, info))

        top_picks = {}
        for country, items in by_country.items():
            items.sort(key=lambda x: -float(x[1]["row"].get("market_cap", 0)))
            for t, info in items[:200]:
                top_picks[t] = info

        # 합본
        result = {**confirmed, **top_picks}
        return result

    def _empty_result(self, scanned_total: int = 0, cooldown_skipped: int = 0) -> dict:
        return {
            "candidates": [],
            "scanned_total": scanned_total,
            "by_country": {},
            "cooldown_skipped": cooldown_skipped,
            "new_cooldown": {},
            "ohlcv_evaluated": 0,
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
            "today": today_kst_str(),
            "error": error_msg,
        }
