# Roy-briefbot System

Purpose: automated market briefing, candidate discovery, position monitoring, regime interpretation, and digest delivery.

## Key Files

- `main.py`: entrypoint.
- `src/graph.py`: LangGraph workflow.
- `src/agents/`: SCOUT, GUARD, REGIME, DIGEST agents.
- `src/modules/`: reusable market modules.
- `config/ronin_settings.yaml`: thresholds and tuning source of truth.
- `config/prompts/system.txt`: briefing voice and output rules.
- `.github/workflows/daily.yml`: scheduled run.
- `state.json`: persisted state.
- `data/cache/`: cached market data.

## Workflow

```text
SCOUT + GUARD + REGIME -> M6 -> DIGEST
```

## Current Operating Rules

- Primary runtime state is root `state.json`.
- `src/state.py` is legacy-compatible but must point to the same root `state.json`.
- `data/cache/` is generated market data and is not committed by the scheduled workflow.
- `data/scout/radar_pool_YYYY-MM-DD.json` stores the wide internal SCOUT pool.
- `data/scout/recommendation_snapshot_YYYY-MM-DD.json` is the source ledger for post-recommendation performance tracking.
- `data/scout/scout_performance_YYYY-MM-DD.json` and `scout_performance_report_YYYY-MM-DD.md` store 1/3/5/10/20 trading-day follow-up, MFE/MAE, structure events, verdicts, and lane/auditor aggregates.
- `docs/SCOUT_TOP3_LLM_REVIEW.md` defines the LLM final-review scope and JSON audit schema: rules engine narrows the pool, LLM reviews only the top 8-12 candidates plus market context, and parsing failures fall back to the rule-based Top3.
- `SCOUT 후보발굴` uses two separate position mappings:
  - `진입여부`: historical entry mapping, including OPEN/CLOSED non-draft positions.
  - `현재보유`: current holding mapping, OPEN positions only.
- A successful run must distinguish Sheets save success, Telegram send success, and partial data-source errors.
- `FMP_API_KEY` is optional but preferred for US SCOUT quality/catalyst enrichment.
  - If present: FMP is checked before Finnhub/Finviz for US catalyst and quality facts.
  - If absent or empty: existing Finnhub/Finviz/yfinance/Naver/pykrx fallbacks keep the run alive.
- Top3 selection is tier-based. Legacy `brief_min_score` / `signals_required` final-candidate gates are removed; old score/signal counts remain descriptive inputs only.
- Optional Top3 LLM review writes structured fields (`rule_based_top3`, `final_top3`, `llm_override`, reasons, risks) into the recommendation snapshot so later performance reports can evaluate whether LLM overrides helped.
- The broad Radar Pool is intentionally kept for learning. Tightness belongs first to Top3/WATCHLIST selection, then later to lane thresholds after enough performance records exist.

## Schedule

GitHub Actions runs KST 07:10 Mon-Sat.

## Before Editing

Check:

- Whether the change affects live alerts or sheet writes.
- Config threshold source.
- State/cache behavior.
- Required environment variables.
- Daily/weekly/monthly mode detection.

## Verification

Minimum:

```bash
python -m py_compile main.py src/graph.py
```

If API keys and network are available:

```bash
python main.py auto
```

## Do Not

- Hardcode secrets.
- Move thresholds from config into code.
- Claim live market accuracy without fresh data.
- Treat cached market data as proof of a fresh data run.
