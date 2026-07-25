# project-helios

A telco Customer Value Management (CVM) analytics & ML lab: synthetic-scale ETL, data
quality checks, LLM-narrative alerting, and churn / late-payment risk models — built on
DuckDB with public and synthetic data only.

This project is a from-scratch reimplementation of engineering *patterns* (idempotent
pipeline design, data-quality gating, templated pipeline routing, documentation-first
repo structure for AI-agent collaboration, graceful-degradation LLM integration, and
calibrated binary-classifier decomposition for ambiguous risk labels) commonly used in
production telco analytics. No proprietary code, schemas, or data are used anywhere in
this repo — subscriber data is the public [IBM Telco Customer Churn dataset]
(https://www.kaggle.com/datasets/blastchar/telco-customer-churn), and usage/billing
event volume is synthetically generated to demonstrate pipeline behavior at scale.

## Status

Early scaffold — architecture and docs in progress. See `docs/ARCHITECTURE.md` (once
written) for the full design.

## Quickstart

```bash
uv sync
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
