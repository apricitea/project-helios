# project-helios

A telco Customer Value Management (CVM) analytics & ML lab: synthetic-scale ETL, data
quality checks, LLM-narrative alerting, and churn / late-payment risk models — built on
DuckDB with public and synthetic data only.

This project is a from-scratch reimplementation of engineering *patterns* (idempotent
pipeline design, data-quality gating, templated pipeline routing, documentation-first
repo structure for AI-agent collaboration, graceful-degradation LLM integration, and
calibrated binary-classifier decomposition for ambiguous risk labels) commonly used in
production telco analytics. No proprietary code, schemas, or data are used anywhere in
this repo — subscriber data is the public [IBM Telco Customer Churn dataset](https://www.kaggle.com/datasets/blastchar/telco-customer-churn),
and usage/billing event volume is synthetically generated (seeded, ~1M rows at 150 days)
to demonstrate pipeline behavior at warehouse scale.

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

## Results (real data, IBM Telco Customer Churn + synthetic usage)

| Model | AUC | Brier score |
|---|---|---|
| Churn | 0.823 | 0.147 |
| Late payment (30-day forward window) | 0.628 | 0.065 |

Late-payment label is built from a strictly forward-looking window after the feature
`as_of_date` — verified by test (`tests/test_dataset.py`) that a longer forward horizon
can only add positives, never remove them, which would be impossible if the label leaked
from the same backward-looking window used to build the features.
