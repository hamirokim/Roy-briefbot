# Roy-briefbot Master

Last updated: 2026-05-29

This is the single source of truth for Roy-briefbot. Codex and Claude should read this file before changing the bot.

## Document Rule

- Update this file first when implementation status, operating rules, source-of-truth decisions, or SCOUT design changes.
- `README_SYSTEM.md` and `docs/SCOUT_TOP3_LLM_REVIEW.md` are compatibility pointers only.
- `PROJECT_STATUS.md` is not present in the current GitHub working tree. Project status lives here.
- Do not create parallel design notes unless Roy explicitly asks for a temporary draft.

## Purpose

Roy-briefbot is Roy's automated market briefing and candidate discovery system.

It does not issue investment orders. It does:

- scan global equity candidates,
- monitor current holdings,
- summarize market regime,
- write Telegram and Journal briefing output,
- write SCOUT candidates and WATCHLIST to Journal Sheets,
- store recommendation snapshots,
- track post-recommendation performance.

## Runtime Structure

Key files:

- `main.py`: entrypoint.
- `src/graph.py`: LangGraph workflow.
- `src/agents/scout.py`: candidate discovery and SCOUT auditors.
- `src/agents/guard.py`: current holdings monitor and news check.
- `src/agents/regime.py`: VIX, FX, sector/theme RRG, macro interpretation.
- `src/agents/digest.py`: final Telegram / Journal briefing text.
- `src/modules/m6_feedback.py`: legacy SCOUT follow-up summary.
- `src/modules/scout_performance.py`: recommendation snapshot based performance ledger.
- `src/collectors/`: data sources for universe, OHLCV, FMP, Finviz, Sheets, RSS.
- `config/ronin_settings.yaml`: numeric thresholds and operating config.
- `config/themes.yaml`: theme/industry mapping.
- `.github/workflows/daily.yml`: scheduled GitHub Actions run.
- `state.json`: root runtime state.
- `data/scout/`: radar pools, recommendation snapshots, performance reports.

Workflow:

```text
SCOUT + GUARD + REGIME
        ↓
       M6
        ↓
     DIGEST
        ↓
Telegram + Journal Sheets + state.json
```

## Operating Rules

- Primary runtime state is root `state.json`.
- `src/state.py` is legacy-compatible and must point to the same root `state.json`.
- `data/cache/` is generated market data and should not be treated as source truth.
- `data/scout/radar_pool_YYYY-MM-DD.json` is the wide internal SCOUT pool.
- `data/scout/recommendation_snapshot_YYYY-MM-DD.json` is the source ledger for post-recommendation performance tracking.
- `data/scout/scout_performance_YYYY-MM-DD.json` and `scout_performance_report_YYYY-MM-DD.md` store 1/3/5/10/20 trading-day follow-up, MFE/MAE, structure events, verdicts, and lane/auditor aggregates.
- `SCOUT 후보발굴` separates:
  - `진입여부`: historical entry mapping, including OPEN/CLOSED non-draft positions.
  - `현재보유`: current holding mapping, OPEN positions only.
- `SCOUT WATCHLIST` stores top waiting candidates when Top3 is empty or when candidates are not selected.
- A successful run must distinguish Sheets save success, Telegram send success, and partial data-source errors.
- Do not hardcode secrets. Use GitHub Secrets / environment variables.
- Do not claim live market accuracy without fresh data.

## Current Implementation Status

Status as of 2026-05-28:

- GitHub Actions scheduled daily run is active.
- SCOUT, GUARD, REGIME, M6, DIGEST workflow is implemented.
- Root `state.json` is the normalized runtime state.
- SCOUT position mapping now separates historical entry history from current OPEN holdings.
- Common gate and three price lanes are implemented.
- Theme/industry auditor is implemented as confidence support only.
- Quality auditor is implemented with FMP first, Finviz fallback.
- Catalyst auditor is implemented with FMP first, Finnhub fallback, LLM JSON headline classification, and RISK_CATALYST review-pool handling.
- Recommendation snapshot and performance ledger are implemented.
- Top3 selection is tier-based. Legacy `brief_min_score` / `signals_required` final-candidate gates are removed.
- Optional LLM Top3 review is implemented with structured JSON, validation, and rule-based fallback.
- Broad Radar Pool remains intentionally wide for learning. Tightness is applied at Top3/WATCHLIST first.

## SCOUT Candidate Pipeline

High-level flow:

```text
Universe
  → cooldown filter
  → low-cost pre-signals
  → OHLCV evaluation
  → common gate
  → price lanes
  → theme / quality / catalyst auditors
  → Radar Pool
  → rule-based Top3
  → optional LLM Top3 review
  → final Top3 + WATCHLIST
  → recommendation snapshot
  → performance ledger
```

## Common Gate

Source: `config/ronin_settings.yaml > scout.common_gate`

Current hard filters:

- supported countries: `US`, `KR`
- minimum market cap:
  - US: `$1B`
  - KR: `$200M`
- minimum price:
  - US: `$5`
  - KR: `₩2,000`
- minimum 20-day traded value:
  - US: `$10M`
  - KR: `₩2B`
- minimum close history: `120` days
- stale trading days max: `3`
- zero-volume days in last 20 days max: `2`

Current review flag:

- 5-day drop <= `-25%` becomes `needs_review`, not hard reject.

Important:

- JP and CN are collected into the universe, but the current common gate allows only US/KR into the operational SCOUT lane system.
- This is deliberate until JP/CN data quality and catalyst/quality sources are made reliable enough.

## Price Lanes

The SCOUT price structure has three lanes:

1. Strength
   - Finds strong names near highs with relative strength.
   - Uses relative strength vs benchmark, 52-week high proximity, trend confirmation, volume confirmation.

2. Pullback
   - Finds names still in an uptrend but pulled back.
   - Uses drawdown depth, MA50/support proximity, volume dry-up, sell-volume review flags.

3. Left-side
   - Finds early reversal candidates near large drawdowns / low zones.
   - Stage 1 is watch/wait.
   - Stage 2 is the practical pass zone.
   - Actual buy timing still belongs to RONIN/TradingView signal logic.

## Auditors

Auditor roles:

- Common gate: has hard reject authority.
- Price lanes: primary lane classification and Top3 tier basis.
- Theme/industry: no reject authority; confidence support only.
- Quality: no reject authority; confidence support only.
- Catalyst: no reject authority by itself; however `RISK_CATALYST` is excluded from Top3 by Top3 selection rules and placed in review pool.
- Performance ledger: evaluates whether candidates later moved in a useful direction, independent of actual buy status.

## Top3 Selection

Source: `config/ronin_settings.yaml > scout.top3_selection`

Current settings:

- enabled: `true`
- max picks: `3`
- watchlist size: `5`
- RISK_CATALYST review pool: `true`
- tier order: `A`, `B`, `C`, `D`

Ranking hierarchy:

1. lane strength
2. catalyst freshness
3. support auditor count
4. opportunity score
5. lane balance

Legacy final gates removed:

- `brief_min_score`
- `signals_required`

Old score and signal counts remain descriptive inputs only.

## SCOUT LLM Top3 Review

Purpose:

- LLM is a final review auditor, not the first-stage scanner.
- It reviews only the narrowed candidate set so cost and consistency stay controlled.
- Its decision is stored so later performance can measure whether LLM overrides helped.

Input scope:

1. Rule-based Top3.
2. Rule-based next WATCHLIST candidates.
3. Best representative from each lane if not already included.
4. RISK_CATALYST summary only; RISK_CATALYST candidates are not selectable.

Current input limit:

- `candidate_limit: 12`
- `max_tokens: 1200`

Required LLM output:

```json
{
  "schema_version": "scout_top3_llm_review_v0_1",
  "selected_top3": [
    {
      "rank": 1,
      "ticker": "AVGO",
      "reason": "why selected",
      "risk": "remaining risk"
    }
  ],
  "rejected": [
    {
      "ticker": "IRDM",
      "reason": "why rejected"
    }
  ],
  "overrides": [
    {
      "dropped_ticker": "IRDM",
      "added_ticker": "NET",
      "reason": "why override"
    }
  ],
  "llm_override": true
}
```

Stored fields:

- `rule_based_top3`
- `final_top3`
- `llm_selected`
- `llm_reason`
- `llm_risk`
- `llm_dropped`
- `llm_drop_reason`
- `llm_override`
- `rule_selection_rank`

Telegram visibility:

- The daily Telegram brief must show one compact LLM review audit line when Top3 selection audit exists.
- Required content: review status, override/keep result, and final Top3 tickers when available.
- Fallback must be visible with a short reason; do not silently hide `fallback_*` states.
- The line must be safe when Top3 is empty or LLM review is disabled/missing.

Fallback conditions:

- `GPT_API_KEY` missing.
- LLM call failure or timeout.
- JSON parsing failure.
- missing or empty `selected_top3`.
- selected ticker not in LLM input pool.
- selected ticker is Top3-excluded / RISK_CATALYST.

Fallback behavior:

- final Top3 remains rule-based Top3.
- `llm_review.status` records `fallback_*`.
- `llm_override` is `false`.
- raw response excerpt is saved for debugging with length limit.

## Performance Ledger

Source: `src/modules/scout_performance.py`

Current schema:

- `scout_performance_v0_2`

Tracks:

- 1/3/5/10/20 trading-day follow-up prices and returns.
- MFE / MAE.
- structure events:
  - higher low,
  - higher high,
  - MA50 recovery,
  - volume breakout.
- final verdict:
  - `WINNER`
  - `FAILED_FAST`
  - `FALSE_POSITIVE`
  - `WATCH`
  - `NEUTRAL`
  - `PENDING`
- actual buy status separately from candidate performance.
- lane/auditor aggregate results.
- LLM override fields for later comparison.
- LLM override comparison cohort:
  - normal Top3 candidates remain in bucket `candidate`;
  - rule-based candidates dropped by LLM are included in a separate `llm_dropped` bucket even when full `radar_top` tracking is disabled;
  - candidate headline counts and aggregates must use only `candidate` rows, so comparison rows do not distort normal SCOUT win/loss statistics;
  - reports should show dropped vs added candidates side by side so LLM override quality can be checked after D1/D3/D5/D10/D20 data accumulates.

Core purpose:

```text
recommendation condition at time T
  → later price / structure result
  → improve formulas and auditor weights
```

## Data Source Status By Country

### US

Universe:

- Nasdaq Trader official listed symbols.
- Finviz universe and fundamentals.
- yfinance OHLCV.

Quality:

- FMP first when `FMP_API_KEY` exists.
- Finviz fallback.

Catalyst:

- FMP news, upgrades/downgrades, earnings surprise first.
- Finnhub company news fallback.
- LLM JSON classification for top news candidates.

Status:

- Best-supported market.
- Operational for common gate, lanes, quality, catalyst, theme, Top3, LLM review.

### KR

Universe:

- Naver market-cap pages primary free fallback.
- pykrx fallback when available.
- yfinance seed fallback.

OHLCV:

- yfinance `.KS` / `.KQ`.

Quality / Catalyst:

- not as complete as US.
- KR-specific DART / Naver deeper catalyst quality is not fully connected yet.

Status:

- Operational for price/OHLCV gate and lanes.
- Quality/catalyst confidence is weaker than US.

### JP

Universe:

- JPX official listed issues + yfinance enrichment.
- yfinance seed fallback.

OHLCV:

- yfinance `.T`.

Quality / Catalyst:

- limited.

Status:

- collected into universe and radar context, but not currently allowed through the common gate for final operational SCOUT lanes.

### CN

Universe:

- CN ADR yfinance seeds.
- AkShare Eastmoney A-share / HK when available.
- yfinance HK / A-share fallback seeds.

OHLCV:

- yfinance.

Quality / Catalyst:

- limited and less stable.

Status:

- collected into universe and radar context, but not currently allowed through the common gate for final operational SCOUT lanes.

## Secrets / Environment Variables

Important variables:

- `GPT_API_KEY`: LLM calls.
- `GPT_MODEL`: default model from runtime config.
- `GPT_TIMEOUT`: LLM timeout.
- `GPT_TEMPERATURE`: LLM temperature.
- `FMP_API_KEY`: preferred US quality/catalyst data.
- `FINNHUB_API_KEY`: fallback news source.
- Google service account / Sheets credentials as configured in workflow secrets.

Rule:

- Never hardcode secrets into source files.

## Current Next Work Order

Priority 1: Run the next daily brief and inspect the LLM Top3 audit.

- Confirm `top3_selection_audit.llm_review.status`.
- Confirm `rule_based_top3` and `final_top3`.
- Confirm Telegram audit line shows LLM review status.
- Confirm recommendation snapshot stores LLM fields.

Priority 2: Validate whether LLM overrides improve results.

- After enough samples, compare:
  - rule-based dropped names,
  - LLM added names,
  - D5/D10/D20 return,
  - MFE/MAE,
  - FALSE_POSITIVE rate.
- `llm_dropped` comparison rows must be present in the performance ledger without changing candidate headline counts.

Priority 3: Improve KR data depth.

- Add or harden KR quality/catalyst support using DART / Naver free sources.
- Do not widen JP/CN operational gate until source quality is validated.

Priority 4: Tune Top3 criteria only after data accumulates.

- Do not tighten common gate immediately.
- First adjust lane-level penalties if repeated false positives appear.
- Especially monitor overextended strength candidates.

## Verification Rules

Minimum local verification:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/roy_pycache python3 -m py_compile main.py src/graph.py src/agents/scout.py src/agents/digest.py src/modules/scout_performance.py
```

YAML verification:

```bash
python3 - <<'PY'
import yaml
from pathlib import Path
yaml.safe_load(Path("config/ronin_settings.yaml").read_text())
print("yaml ok")
PY
```

If API keys and network are available:

```bash
python main.py auto
```

## Change Policy

- For code changes, update this file when behavior, source-of-truth, or operating status changes.
- For threshold-only changes, update the relevant config and note the reason here if it changes operating behavior.
- For data-source changes, update the country data-source section.
- For LLM prompt/schema changes, update the SCOUT LLM Top3 Review section before implementation.
- For deployment-sensitive changes, push to GitHub and verify the next GitHub Actions run.
