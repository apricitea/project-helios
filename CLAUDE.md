# project-helios — AI Assistant Entry Point

You are an AI coding agent working in this repo. **Load context in this order**
before starting any non-trivial task:

1. This file — dispatch rules, conventions, safety boundaries
2. `docs/TABLE_REGISTRY.md` — always load before writing any SQL; table grain, source,
   refresh cadence, and key guarantees live here, not in your memory of past sessions
3. `docs/ARCHITECTURE.md` — repo structure, pipeline patterns, execution order
4. `docs/RUNBOOK.md` — load when diagnosing a failure, not before

> **Never write SQL using table/column names from memory.** Verify against
> `TABLE_REGISTRY.md` every time — it is the single source of truth, not this file.

## Identity & rules

- Python: `uv run` for everything — never bare `python`/`pip`. Dev deps via
  `uv add --group dev`.
- **Never commit**: `.env`, credentials, anything under `data/` or `outputs/`
  (already gitignored — don't work around it).
- No proprietary code, schemas, or data anywhere in this repo — subscriber data is the
  public Kaggle churn dataset; usage/billing volume is synthetically generated. If you
  find yourself about to paste in a real telco schema, table name, or metric from
  somewhere else — stop.
- Seed everything ML-adjacent (`numpy`/`sklearn` `random_state=42` throughout) and log
  the seed in code, not just in your head.

## Where does new work belong?

| Task | Directory | Template to follow |
|---|---|---|
| New raw data source | `ingest/` | `kaggle_churn.py` (static) or `synthetic_usage.py` (generated, seeded) |
| New derived/feature table | `warehouse/` | `etl.py`'s idempotent DELETE+INSERT pattern |
| New DQ check | `warehouse/pipeline.py` | Add a `DQCheck` to `RAW_CHECKS`; SQL must return a single row/column, pass if `>= min_value` |
| New report / narrative | `alert/` | `report.py` (stats) + `llm.py` (graceful-degradation LLM call) |
| New model | `model/` | `dataset.py` (leakage-safe frame) + `train.py` (train/holdout, permutation importance) |

**Hard rule**: if it writes to `customer_daily_features` or reads it for training, it
must go through the DQ-gated pipeline in `warehouse/pipeline.py` — don't bypass it with
a one-off script that loads raw data directly.

## Coding conventions

- **Idempotency for anything writing to the warehouse.** If a script can be re-run for
  the same `as_of_date`/`train_date` and produce different row counts, it's a bug, not
  a feature. Follow `warehouse/etl.py`'s DELETE-before-INSERT pattern.
- **DQ-gate before transforming, don't just hope the data is fine.** See
  `warehouse/pipeline.py` — critical failures abort with a non-zero exit code before
  any downstream table is touched.
- **LLM integrations degrade gracefully, always.** No API key, an API error, a refusal,
  or unparseable output must all fall back to a safe default — never let a narrative
  feature crash or block a pipeline with real numeric output to deliver. See
  `alert/llm.py` for the reference pattern (three explicit failure modes, one success
  path, all converging on the same `Insight` shape).
- **No leakage, ever, and prove it with a test.** Any model feature must come from data
  available *at or before* the label's reference point. `model/dataset.py`'s label
  query looks strictly forward from `train_date`; `tests/test_dataset.py` verifies this
  by checking that widening the forward window can only add positive labels, never
  remove them — write an equivalent test for any new label.
- Plain text output, no decorative Unicode. State the change, not a narrated process.

## New pipeline protocol

Before considering a new pipeline (ingest/warehouse/alert/model) complete:

1. **Idempotency**: re-running it for the same date/parameters produces the same
   result, verified by a test that runs it twice.
2. **DQ checks**: if it writes to the warehouse, it goes through `pipeline.py`'s
   DQ-gate — add checks for row counts and referential integrity, not just "did it not
   crash."
3. **Table registry**: add or update the relevant entry in `docs/TABLE_REGISTRY.md` —
   grain, source, refresh cadence.
4. **Tests**: one test file per module (see `tests/` for the existing pattern —
   idempotency, correctness of a specific SQL/logic decision, and edge cases).
5. **CI green**: `uv run ruff check .` and `uv run pytest -q` both pass — this is what
   `.github/workflows/ci.yml` runs on every push/PR.

## Known state

Nothing is paused, decommissioned, or resource-gated — this is a small, fully-active
repo (unlike a large production system that accumulates masked units over time). If
that changes (e.g. a model becomes too slow to run in CI), document it here rather than
silently skipping it.
