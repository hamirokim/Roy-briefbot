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
- `SCOUT 후보발굴` uses two separate position mappings:
  - `진입여부`: historical entry mapping, including OPEN/CLOSED non-draft positions.
  - `현재보유`: current holding mapping, OPEN positions only.
- A successful run must distinguish Sheets save success, Telegram send success, and partial data-source errors.

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
