# Architecture & Engineering Guide

> **Scope**: repo structure, pipeline execution patterns, data flow between
> modules, and change-safety guidance.
> - For table schemas and column meanings: see `TABLE_REGISTRY.md`
> - For AI-agent dispatch rules: see the root `CLAUDE.md`
> - For failure diagnosis and re-run commands: see `RUNBOOK.md`

## 1. Repository structure

```
src/project_helios/
├── ingest/
│   ├── kaggle_churn.py       # Downloads the public churn dataset (dimension table)
│   └── synthetic_usage.py    # Seeded synthetic usage/billing event generator (fact table)
├── warehouse/
│   ├── db.py                 # DuckDB connection helper
│   ├── dq.py                 # DQCheck framework: critical/non-critical gating
│   ├── etl.py                 # Idempotent DELETE+INSERT feature refresh
│   └── pipeline.py           # Orchestrates: load raw -> DQ gate -> feature refresh
├── alert/
│   ├── llm.py                 # Claude narrative insight, graceful degradation
│   └── report.py              # Stats computation + HTML report rendering
└── model/
    ├── dataset.py             # Feature/label frame construction (leakage-safe)
    └── train.py                # Two independently-calibrated binary classifiers

docs/                          # This file, table registry, runbook
tests/                         # pytest — one file per module, 24 tests total
.github/workflows/ci.yml       # ruff + pytest gate on push/PR
```

## 2. Pipeline execution order

```
1. ingest/kaggle_churn.py       (one-time / on-demand — static reference data)
2. ingest/synthetic_usage.py    (one-time / on-demand — depends on (1) for customer IDs)
        │
        ▼
3. warehouse/pipeline.py        (scheduled — DQ-gated idempotent refresh)
        │
        ├──▶ 4. alert/report.py       (scheduled — reads customer_daily_features)
        └──▶ 5. model/train.py        (ad-hoc / periodic — reads customer_daily_features
                                        + raw_usage_events for forward-looking labels)
```

**Rule**: if step 3 fails a critical DQ check, it aborts before refreshing
`customer_daily_features` — steps 4 and 5 must not run against stale/partial data.
The pipeline enforces this itself (`sys.exit(1)` on critical failure); it isn't a
manual convention.

## 3. Pipeline patterns

### Pattern A: Idempotent DELETE+INSERT (warehouse/etl.py)

```
1. DELETE FROM customer_daily_features WHERE as_of_date = ?
2. INSERT ... WITH window_events AS (...) SELECT ... GROUP BY customer_id
```

Re-running for the same `as_of_date` is always safe — no duplicate rows, no manual
cleanup. Verified in `tests/test_etl.py` by running the refresh twice and asserting
the row count doesn't change.

### Pattern B: DQ-gated pipeline (warehouse/pipeline.py)

```
1. Load raw (full replace — static/regenerable sources, no incremental merge needed)
2. Run DQCheck list; abort with a non-zero exit code on any critical failure
3. Only then run the idempotent feature refresh
```

Mirrors the real production discipline of never letting a pipeline silently consume
bad data — a failed check stops the pipeline rather than producing a table that looks
fine but isn't.

### Pattern C: Graceful-degradation LLM integration (alert/llm.py)

```
1. No API key -> return fallback immediately, no network call
2. API/network error -> catch, return fallback
3. Refusal stop_reason -> return fallback
4. Unparseable response -> return fallback
5. Success -> merge into fallback defaults for any missing keys, return
```

The report pipeline never crashes or blocks on the LLM step — narrative generation is
strictly additive to the numeric report.

### Pattern D: Leakage-safe label construction (model/dataset.py)

```
features: as_of_date = T, computed from a BACKWARD-looking window (T-90 .. T)
label:    computed from a FORWARD-looking window (T .. T+30), strictly after T
```

The two windows never overlap. Verified in `tests/test_dataset.py` by asserting that
widening the forward horizon can only add positive labels, never remove them — a
property that would be violated if the label were secretly reading the same backward
window used for features.

## 4. Why two binary classifiers instead of one multiclass model

`model/train.py` trains `churn_label` and `late_payment_label` as two independent
`HistGradientBoostingClassifier` pipelines rather than one shared 3-class model. This
mirrors a real production lesson: a shared multiclass score space conflates distinct
risk types (a customer can be a churn risk without being a late-payment risk, or vice
versa) and produces miscalibrated joint predictions. Two independent models let each
optimize its own decision boundary and threshold, at the cost of training two models
instead of one — a deliberate engineering trade-off, not an oversight.

Feature importance uses **permutation importance** on the holdout set rather than
impurity-based importance, because `HistGradientBoostingClassifier` doesn't expose
`feature_importances_`, and permutation importance is unbiased toward high-cardinality
features regardless of estimator.

## 5. Change-safety guidance

- Any new pipeline should follow Pattern B (DQ gate before touching production tables).
- Any new derived table needs an entry in `TABLE_REGISTRY.md` — grain, source, refresh
  cadence, and key guarantees.
- Any new LLM integration should follow Pattern C — never let a narrative/insight
  feature block or crash a pipeline that has real numeric output to deliver.
- Any new model needs a leakage check (Pattern D) in its test file before being
  considered done, not just a metric that "looks reasonable."
