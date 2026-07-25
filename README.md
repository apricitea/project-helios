# project-helios

A telco Customer Value Management (CVM) analytics & ML lab built on the [IBM Telco Customer
Churn dataset](https://www.kaggle.com/datasets/blastchar/telco-customer-churn) (Kaggle) and a
synthetically generated usage/billing event stream (seeded, ~1M rows across 150 days).

Idempotent DuckDB warehouse ETL with a data-quality gate, an LLM-narrative ops report with
explicit graceful degradation, and two independently-calibrated risk models — churn and late
payment — instead of one shared multiclass model. Domain and engineering patterns (idempotent
pipelines, DQ gating, documentation-first repo structure for AI-agent collaboration,
leakage-safe label construction) draw on production telco CVM engineering; all code, schemas,
and data in this repo are original and public.

## Status

Feature-complete for its scope: data ingest, warehouse ETL with DQ gating, LLM-narrative
alerting, two ML models, tests, and CI are all in place. See `docs/ARCHITECTURE.md` for
the full design and `docs/TABLE_REGISTRY.md` for schema details.

## Quickstart

```bash
uv sync

# 1. Data: Kaggle churn dataset + synthetic usage/billing events
uv run python -m project_helios.ingest.kaggle_churn
uv run python -m project_helios.ingest.synthetic_usage \
  --customers data/raw/WA_Fn-UseC_-Telco-Customer-Churn.csv --days 150 \
  --out data/raw/usage_events.parquet

# 2. Warehouse: load raw -> DQ gate -> idempotent feature refresh
uv run python -m project_helios.warehouse.pipeline

# 3. Weekly ops report (HTML + optional LLM narrative if ANTHROPIC_API_KEY is set)
uv run python -m project_helios.alert.report

# 4. Train churn + late-payment risk models
uv run python -m project_helios.model.train --train-date 2026-06-15

uv run pytest
```

## Layout

```
src/project_helios/
├── ingest/      # Kaggle download + synthetic usage/billing event generator
├── warehouse/   # DuckDB ETL: idempotent transforms, table registry, DQ checks
├── alert/       # HTML report generation + optional LLM narrative insight
└── model/       # Churn / late-payment risk models (calibrated binary classifiers)
```

## Results (IBM Telco Customer Churn + synthetic usage)

| Model | AUC | Brier score |
|---|---|---|
| Churn | 0.823 | 0.147 |
| Late payment (30-day forward window) | 0.628 | 0.065 |

The late-payment label is built from a strictly forward-looking window after the feature
`as_of_date` — verified by test (`tests/test_dataset.py`) that widening the forward horizon
can only add positive labels, never remove them, a property that would break if the label
were secretly reading the same backward-looking window used to build the features.
