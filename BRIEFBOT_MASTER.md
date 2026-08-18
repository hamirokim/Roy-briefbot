# Roy-briefbot Master

Last updated: 2026-08-13

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

Status as of 2026-07-29:

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
- Selective Research v1 reviews only production finalists (maximum 5) with deterministic evidence
  IDs, source provenance, separate bull/bear/risk/invalidation cases, and a fact fingerprint lock.
  Unsupported evidence references or any deterministic-fact mutation fall back to rule selection.
- Outcome Memory v1 converts mature benchmark-alpha results into date-clustered condition cohorts.
  It separates setup, market regime, signal, sector/theme state, liquidity/quality, and catalyst
  timing; applies recency decay, global-mean shrinkage, confidence intervals, and drift invalidation.
  Only a prior-date memory file may enter Selective Research, and memory has no hard-gate or score
  authority.
- Broad Radar Pool remains intentionally wide for learning. Tightness is applied at Top3/WATCHLIST first.
- Integrity Reset v1 uses the common-gate OHLCV 20-day traded value as the single liquidity
  evidence source for quality/factor checks. The universe `avg_volume_value` remains descriptive
  fallback only.
- Every candidate whose price lane can enter a production-allowed tier receives quality-auditor
  coverage even when that exceeds the ordinary cost-control `eval_limit`.
- REGIME separates `AI·반도체` from `클라우드·소프트웨어`; Telegram theme evidence includes every
  ETF used by the displayed judgment.
- Zero-recommendation output records `HEALTHY_ABSTENTION`, `DEGRADED_DATA`, or `PIPELINE_EMPTY`
  so policy abstention is not confused with missing evaluation data.
- Evaluation Harness v1 replays the first executable session open, measures benchmark alpha and
  pre-entry market regime, and audits rejected-radar opportunity cost and abstention quality.
- Step4 precision shadow is implemented as a non-user-visible comparison lane. It does not replace Telegram, Sheets, cooldown, or final Top3.
- Left-side Context Shadow v1 reads the common-gate-passed `left_side` Stage 2 pool before the
  signal-based Radar threshold. It separately checks sector RRG, mapped-theme group breadth,
  quality, catalyst risk, and factor extremes. It allows 0 to 2 picks without backfill and remains
  snapshot-only.
- Pre-Entry v1 is the live TradingView-opening lane. It selects at most two `STAGE1_WAIT`,
  `WAIT_CONFIRM`, or non-extended `STAGE2_PASS` candidates before Entry50/Entry100 confirmation.
  It has a separate 10-day cooldown, never backfills slots, and excludes `LATE`/`MISSED` setups.
- Each Pre-Entry candidate carries an OHLCV-only price map: confirmed swing support, nearest and
  core resistance zones, ATR-buffered close invalidation, price room, first setup date, and move
  since setup. Volume-profile levels are not claimed because Briefbot does not collect the
  TradingView volume-profile contract.
- A 20-day high is recorded only as `higher_high_context`; it no longer upgrades a left-side
  candidate to `STAGE2_STRONG_PASS`. Volume reversal remains the only strong left-side bonus.
- The production recommendation gate allows 0 to 2 live recommendations and only permits
  `left_side` Stage 2 candidates until TradingView has a separately validated breakout route.
  Tier B/C/D candidates remain internal and are never used as slot backfill.
- Telegram is a one-screen decision board, not a prose summary or a second Journal sheet. It shows
  one operating verdict, at most two opportunity sectors, two themes, two risk sectors, two changes,
  FX as `적극/분할/대기`, 0-2 charts worth opening, holding alerts, the next event, and degraded-data
  warnings. Event interpretation, learning notes, valuation explanations, full RRG/theme tables,
  WATCHLIST, and SCOUT detail remain outside Telegram.
- FX action uses both the recent 90-day and 52-week USD/KRW distributions. `적극` or `대기`
  requires both windows to agree; mixed windows return `분할`. Telegram also shows the 52-week
  percentile as plain `상위/하위 N%`; ranges and medians remain in the Journal.
- Core ETF relative valuation is disabled. Cross-fund multiples did not answer Roy's requested
  own-history valuation question and therefore must not appear in Telegram or the Journal. Do not
  re-enable it until a reliable historical valuation series for each ETF is available.
- Market operating language is derived only from collected REGIME evidence. The bot must not present
  Roy's discretionary view as an operating mode. No manual market-view input or override is planned;
  Roy compares the bot's independent conclusion with his own judgment outside the bot.
- GUARD separates deterministic daily-chart structure from news tone. Structure is diagnostic and
  never claims TradingView parity. News tone must not be converted into `hold`, `sell`, or
  `investment thesis unchanged`. Until a structured thesis contract exists, thesis impact is
  explicitly `UNVERIFIED`.

## TradingView Validation Lab

The first TradingView integration step is a bounded validation experiment, not a global alert rollout.

- Ground truth signal: `Entry50` and `Entry100`. They are separate event types but neither receives a
  higher quality label by number alone.
- Decision context recorded separately: core-filter pass/block, Gate progression, nearby
  support/resistance, volume-profile context, and market regime.
- Initial cohort: 16 symbols frozen for 20 trading days.
  - 4 current holdings.
  - 4 highest signal-readiness SCOUT cases.
  - 4 matched low-readiness controls.
  - 4 market representatives covering broad market, weak/risk sector, defensive sector, and an
    active theme.
- Sector/theme watchboards remain market context and are not all alert targets.
- Phase 1 compares historical TradingView chart markers with briefbot calculations. Webhook ingestion
  is considered only after Phase 1 shows useful recall, tolerable false positives, and stable lead
  time.
- Required comparison fields: symbol, timeframe, preset signature, bar date, Entry type, briefbot
  readiness state, lead bars, filter result, Gate stage dates, and later outcome.
- The 2026-08-13 six-symbol CSV audit confirmed material delivery lag: GFI Entry50 to briefing
  `26` four-hour bars / `+26.5%`, EQX `27` bars / `+28.5%`, and CDE Entry100 `28` bars / `+18.6%`.
  `RCI` versus `RCI.B` is treated as a cross-listing date comparison, not a price comparison.
  Old ZS/CMCSA markers require signal-episode validity checks and are not used as price-lag
  calibration anchors.
- This lab is shadow-only. It cannot change Telegram candidates, cooldown, Sheets candidates, or
  production recommendation policy until separately approved.

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
  → left-side Stage 2 shadow pool (common-gate branch)
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
- production gate allowed tier: `A`
- production gate requires quality support and excludes overextension, weak liquidity, extreme volatility, and chasing flags
- weak liquidity has one production veto path (`low_liquidity_buffer`); factor-layer
  `liquidity_weak` remains diagnostic and is not a duplicate production veto
- zero recommendations are valid; backfill is disabled
- tier order remains descriptive for Radar/WATCHLIST ordering: `A`, `B`, `C`, `D`

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

1. Rule-based production-gate candidates only.
2. WATCHLIST, lane representatives, and RISK_CATALYST candidates are not selectable by LLM.

Current input limit:

- `candidate_limit: 5`
- `max_tokens: 1200`
- `additions_allowed: false`

Required LLM output:

```json
{
  "schema_version": "scout_top3_llm_review_v0_4",
  "selected_top3": [
    {
      "rank": 1,
      "ticker": "AVGO"
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
  "research_reviews": [
    {
      "ticker": "AVGO",
      "disposition": "KEEP",
      "memory_effect": "NONE",
      "memory_evidence_refs": [],
      "bull_case": {"summary": "upside case", "evidence_refs": ["AVGO:E001"]},
      "bear_case": {"summary": "counter case", "evidence_refs": ["AVGO:E002"]},
      "risk_case": {"summary": "main risk", "evidence_refs": ["AVGO:E003"]},
      "invalidation": {"summary": "observable invalidation", "evidence_refs": ["AVGO:E004"]}
    }
  ],
  "llm_override": true
}
```

Selective Research evidence contract:

- Every evidence item stores `evidence_id`, `category`, `claim`, `value`, `as_of`, `source`, and
  optional `url`.
- Deterministic inputs cover price/liquidity, price lane, signals, factor risk, quality, theme,
  production selection, catalyst news, and known data gaps.
- Every bull, bear, risk, and invalidation case must cite evidence IDs belonging to the same ticker.
- LLM prose may be attached to a candidate, but ticker, price, score, tier, lane, source metrics,
  and gate results are protected by a before/after SHA-256 fact fingerprint.
- Evidence packets and validated reviews are stored under
  `top3_selection_audit.llm_review.selective_research`.

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
- `selective_research`

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
- missing candidate review, unsupported evidence reference, or disposition/selection mismatch.
- deterministic fact fingerprint mismatch.
- selected ticker not in LLM input pool.
- selected ticker is Top3-excluded / RISK_CATALYST.

Fallback behavior:

- final Top3 remains rule-based Top3.
- `llm_review.status` records `fallback_*`.
- `llm_override` is `false`.
- raw response excerpt is saved for debugging with length limit.

Live LLM boundary:

- LLM may reorder or reduce the rule-based production candidates.
- LLM may return zero final candidates when every finalist has a validated `DROP` review.
- LLM cannot add or replace a ticker from WATCHLIST or Radar Pool.
- Empty production-gate output bypasses LLM selection and remains an empty recommendation day.
- Telegram labels WATCHLIST output as `관찰 레이더 (추천 아님)`.

## SCOUT Precision Shadow

Purpose:

- Test the Step3 US precision hypothesis on future unseen data before changing live recommendations.
- Treat zero candidates as a valid result. The shadow lane never fills an empty slot with a weaker candidate.
- Keep the live Top3, Telegram, Sheets, cooldown, and LLM review behavior unchanged during shadow validation.

Current policy id:

- `us_precision_v1`

Frozen shadow criteria:

- country is `US`;
- Top3 tier is `A`;
- theme/industry status is `SUPPORT` or `STRONG_SUPPORT`;
- quality status is `QUALITY_SUPPORT` or `STRONG_QUALITY`;
- factor negatives do not include `volatility_extreme`, `chasing_extreme`, or `chasing_hot`;
- `RISK_CATALYST` and all normal Top3 exclusions remain excluded;
- maximum 3 picks, with no minimum count and no backfill.

LLM boundary:

- LLM cannot add, replace, or reorder precision shadow candidates.
- Shadow candidates are selected only from frozen rule fields already present in the Radar Pool.
- `llm_additions_allowed` must be stored as `false` in the shadow audit and snapshot payload.

Persistence:

- Recommendation snapshots use schema `scout_recommendation_snapshot_v0_5`.
- Top-level `generated_at`, `timezone`, and `data_as_of` preserve the decision-time context.
- Top-level `policy.production_policy_id` identifies the live policy used for the decision.
- `summary.decision_health` preserves recommendation, abstention, and degraded-data state.
- Top-level `shadow_policies.us_precision_v1` stores the full frozen candidate objects and audit.
- `top3_selection_audit.precision_shadow` stores compact counts and selected tickers.
- Shadow output is file-only. It must not appear in Telegram or Journal Sheets until Roy explicitly approves a production switch.

## Performance Ledger

Source: `src/modules/scout_performance.py`

Current schema:

- `scout_performance_v0_6`

Tracks:

- 1/3/5/10/20 trading-day follow-up prices and returns.
- first executable session `Open` entry; recommendation-date `Close` is never used as an executable price.
- SPY / KOSPI / KOSDAQ benchmark return and D5/D10/D20 alpha.
- market regime calculated only from benchmark observations before entry.
- rejected Radar Top comparison, opportunity cost, and abstention quality.
- opportunity cost uses the highest-ranked rejected alternative known at decision time; the
  hindsight-best rejected candidate is reported separately as an ex-post upper-bound gap.
- recorded production policy, precision shadow, and non-selected Radar baseline cohorts.
- policy comparison never auto-declares a winner while forward evidence is still accumulating.
- frozen support/resistance maps are evaluated by the first 20-session touch of target or invalidation;
  a same-bar touch is recorded as ambiguous, never guessed.
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
- Telegram combines `FAILED_FAST` and `FALSE_POSITIVE` into a human-readable failure total while preserving both raw ledger categories.
- actual buy status separately from candidate performance.
- lane/auditor aggregate results.
- LLM override fields for later comparison.
- LLM override comparison cohort:
  - normal Top3 candidates remain in bucket `candidate`;
  - rule-based candidates dropped by LLM are included in a separate `llm_dropped` bucket even when full `radar_top` tracking is disabled;
  - candidate headline counts and aggregates must use only `candidate` rows, so comparison rows do not distort normal SCOUT win/loss statistics;
  - reports should show dropped vs added candidates side by side so LLM override quality can be checked after D1/D3/D5/D10/D20 data accumulates.
- Precision shadow candidates are loaded from `shadow_policies` into separate `shadow:<policy_id>` buckets.
- Shadow rows are reported separately and never change normal candidate headline counts or aggregates.
- Legacy snapshots without `generated_at` remain clearly labeled `snapshot_date_legacy`; new
  snapshots use market-clock-aware execution timing.

## Outcome Memory

Source: `src/modules/scout_outcome_memory.py`

Purpose:

- Convert accumulated outcomes into condition-specific experience instead of ticker anecdotes.
- Use benchmark alpha, not raw return alone.
- Prevent several candidates from the same briefing date from masquerading as independent samples.
- Detect conditions that worked historically but reversed in recent observations.

Current cohort families:

- market regime;
- setup and setup × regime;
- signal and signal × regime;
- sector RRG state;
- theme × regime and theme × sector state;
- quality × liquidity;
- BB compression × quality × liquidity;
- catalyst classification × earnings timing.

Current temporary governance:

- lookback: `180` calendar days;
- horizons: D5, D10, D20;
- minimum `12` records and `8` independent briefing dates;
- same-date candidates are averaged into one date cluster;
- recency half-life: `30` days;
- small cohorts are shrunk toward the global date-cluster alpha using `5` prior dates;
- positive/negative lessons require a 95% confidence interval on the same side of zero;
- an older positive condition becomes `INVALIDATED_BY_DRIFT` when enough recent dates turn negative;
- `COLLECTING`, `MIXED`, and `STALE` cohorts cannot influence a finalist review.

The `12 records / 8 dates` checkpoint is not a permanent trading threshold. On the saved
2026-07-29 Evaluation Harness replay, `20/10` activated no lessons, `10/6` activated conflicting
small-sample lessons, and `12/8` activated only 7 of 254 valid cohorts after unknown-state removal
and horizon-adjusted recency windows.

Runtime order:

```text
Day T SCOUT
  → loads only outcome_memory files dated before Day T
  → attaches matched SUPPORT/WEAKEN lessons as provenance evidence
  → Selective Research may use them as advisory context

Day T M6
  → refreshes performance ledger
  → writes outcome_memory_Day-T.json for Day T+1 or later
```

Authority boundary:

- Outcome Memory cannot add a ticker.
- Outcome Memory cannot edit price, score, tier, lane, quality, or production-gate facts.
- Outcome Memory cannot directly veto a candidate.
- Historical lessons appear only as evidence for the existing Selective Research auditor.
- Every finalist review records `memory_effect` (`SUPPORT`, `WEAKEN`, or `NONE`) and the exact
  historical evidence IDs used. Unsupported or mismatched memory-effect claims fail validation.
- The performance ledger keeps separate memory-effect cohorts with
  `COLLECTING_UNTOUCHED_WINDOW`; it never declares a winner automatically.
- A live policy-weight or hard-veto change still requires untouched-window validation.

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

- DART OpenAPI is the KR quality/catalyst backbone.
- Quality uses DART periodic financial statements when `DART_API_KEY` is available.
- Catalyst uses DART disclosure search when `DART_API_KEY` is available.
- KR valuation/growth fields are annual and derived approximations, not one-to-one equivalents of US FMP forward metrics.
- KR PE is derived from universe market cap in USD converted back to KRW with the same Yahoo USD/KRW source used by REGIME, then divided by positive DART net income. If FX or net income is missing/non-positive, PE remains unknown.
- pykrx / KRX / Naver scraping sources are not the KR backbone because GitHub Actions data-center IPs can be blocked. They may remain best-effort universe fallbacks only.

Status:

- Operational for price/OHLCV gate and lanes.
- Quality/catalyst can be populated from DART, but confidence is still lower than US until performance ledger evidence proves comparability.

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
- `DART_API_KEY`: preferred KR quality/catalyst data.
- Google service account / Sheets credentials as configured in workflow secrets.

Rule:

- Never hardcode secrets into source files.

## Brief Decision Contract

Telegram is an action-first view. It does not change SCOUT selection authority or the detailed
Sheets record.

- Lead with verdict, opportunity, risk, and changes in fixed one-line rows.
- Show at most two final recommendations and only the evidence and invalidation needed to open a chart.
- The primary recommendation must show entry confirmation, invalidation, evidence health, and
  the nearest alternative comparison.
- Keep final ranks 2-3 on one explicitly subordinate line.
- Keep zero recommendations as a healthy operational result.
- Keep the watch radar out of Telegram.
- Surface Outcome Memory only when a validated prior-date lesson has `SUPPORT` or `WEAKEN`
  effect in selective research.
- Require LLM-generated human-readable research summaries to be concise Korean; deterministic
  facts, ticker symbols, and evidence IDs remain unchanged.

## Current Next Work Order

### Support / Resistance Engine v2

- Live `pre_entry_v1` keeps the confirmed-swing map but now preserves resistance zones while price
  is inside them and explicitly labels `IN_RESISTANCE`, `NEAR_RESISTANCE`, `IN_SUPPORT`, and
  `BROKEN_SUPPORT`.
- Live selection rejects broken support, resistance-zone entry, and resistance-near candidates.
  This prevents an already-compressed upside such as the ADBE case from being presented as an
  Entry-leading chart candidate.
- Resistance-near means the lower edge of the first resistance is within one current daily ATR;
  the six Roy-provided TradingView CSV cases were used as the initial regression audit set.
- The old rolling-low fallback is removed. Missing confirmed support or resistance is an incomplete
  map, not invented evidence.
- Every left-side episode stores four frozen maps under `price_map_shadow`: live confirmed swings,
  rolling extrema baseline, prominence plus independent reaction v2, and ATR reversal clusters.
- `prominence_reaction_v2` uses local ATR at each reaction, collapses flat plateaus, separates nearby
  reactions, and applies time decay. It remains shadow-only until forward first-touch evidence is
  sufficient; no engine winner is auto-declared.

Priority 1: Validate the one-screen Telegram contract on one live brief.

- Confirm both FX windows are present and mixed windows cannot produce `적극`.
- Confirm Telegram contains no ETF relative-valuation section, event essay, WATCHLIST, or learning note.
- Confirm the output remains scannable without truncation and preserves 0-2 left-side chart candidates.

Priority 2: Accumulate untouched Left-side Context Shadow outcomes.

- Confirm the new snapshot stores `shadow_policies.left_side_context_v1`.
- Confirm the policy returns 0 to 2 candidates, never backfills, and does not alter Telegram,
  Sheets, cooldown, or final Top3.
- Confirm every selected row passed the production gate, is `left_side` Stage 2, and has supportive
  sector RRG plus group breadth when a theme is mapped.

Priority 3: Accumulate untouched future outcomes.

- Historical replay currently has no mature D5/D10 sample for this policy; do not infer performance
  from the two recent `LVS` selections.
- Compare D5/D10 raw return and benchmark alpha against live candidates, rejected alternatives, and
  zero-recommendation dates.
- Keep Outcome Memory advisory and do not let it override a current hard gate.

Priority 4: Propose a live left-side-only switch only after forward evidence is useful.

- The agreed target is 0 to 2 executable left-side candidates, with strength/breakout candidates
  remaining internal until TradingView gains a separately validated breakout route.
- Redesign Telegram around market opportunity/risk, separate FX judgment, and only candidates worth
  opening in TradingView after the selection policy itself is validated.
- Continue the existing US precision shadow as an independent comparison policy.

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
