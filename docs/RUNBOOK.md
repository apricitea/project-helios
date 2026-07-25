# Runbook — Failure Diagnosis & Recovery

> **Scope**: what to do when something breaks. For architecture, see
> `ARCHITECTURE.md`. For table schemas, see `TABLE_REGISTRY.md`.

## 1. Execution order & dependencies

```
1. ingest/kaggle_churn.py  ─┐
                             ├─▶ 2. ingest/synthetic_usage.py
                             │
3. warehouse/pipeline.py ◀──┘   (needs both raw sources on disk)
        │
        ├──▶ 4. alert/report.py
        └──▶ 5. model/train.py
```

**Rule**: if step 3 fails, do not run 4 or 5 — they will read stale or missing
`customer_daily_features` and either error outright or silently produce misleading
output. The pipeline already enforces this for its own DQ checks (exits non-zero on
critical failure); this rule is about *you*, the operator, not re-running downstream
steps against a warehouse you know is broken.

## 2. Common failures

### `kaggle datasets download` fails with an auth error

Symptom: `403` or an auth-help message from the `kaggle` CLI.

Cause: no Kaggle credentials configured.

Fix: generate a token at kaggle.com/settings under "API" and save it to
`~/.kaggle/access_token` (or export `KAGGLE_API_TOKEN`). See
`src/project_helios/ingest/kaggle_churn.py` docstring.

### `warehouse.pipeline` exits non-zero with `[FAIL] events_reference_known_customers`

Symptom: DQ check fails, pipeline aborts before refreshing features.

Cause: `usage_events.parquet` was generated against a different (or stale)
`WA_Fn-UseC_-Telco-Customer-Churn.csv` than the one currently in `data/raw/` — the
`customer_id` sets no longer match.

Fix: regenerate the synthetic events from the *current* customers CSV:

```bash
uv run python -m project_helios.ingest.synthetic_usage \
  --customers data/raw/WA_Fn-UseC_-Telco-Customer-Churn.csv \
  --days 150 --out data/raw/usage_events.parquet
```

### `model.train` errors with "Only one class is present in y_true" / AUC is `nan`

Symptom: `roc_auc_score` warns or returns `nan` for one of the two labels.

Cause: the stratified holdout split degenerated to a single class — happens when the
positive class is rare relative to the sample size (this is a real risk with small
synthetic fixtures in tests; on the full 7,043-row dataset it doesn't occur).

Fix: use more data, or for `late_payment_label` specifically, increase
`--days` on the synthetic generator (more days -> more billing events -> more positive
labels) or check `LATE_PAYMENT_THRESHOLD_DAYS` in `model/dataset.py` hasn't been
tightened to the point of near-zero positives.

### `alert.report` narrative always says "AI narrative unavailable this run"

Symptom: the report renders fine, but the narrative section is always the fallback
text.

Cause: this is the intended graceful-degradation behavior when `ANTHROPIC_API_KEY`
isn't set — not a bug. Confirmed working as designed if the numeric table above it is
populated correctly.

Fix (if you want the LLM narrative): `export ANTHROPIC_API_KEY=...` before running the
report.

### `refresh_customer_daily_features` returns 0 rows for a given `as_of_date`

Symptom: pipeline runs clean (all DQ checks pass) but `customer_daily_features` has no
rows for the requested date.

Cause: `as_of_date` is outside the range covered by the generated
`usage_events.parquet` — the 90-day backward window and any 30-day forward window (for
model training) need to fit inside the days you generated.

Fix: check the generated event date range (`event_date` min/max in
`usage_events.parquet`), and either pick an `as_of_date`/`--train-date` inside that
range with enough buffer, or regenerate with a larger `--days`.

## 3. Re-run commands

```bash
# Re-run warehouse pipeline for a specific date (idempotent — safe to repeat)
uv run python -m project_helios.warehouse.pipeline --as-of 2026-07-25

# Re-run the report for a specific date
uv run python -m project_helios.alert.report --as-of 2026-07-25

# Re-train models for a specific feature snapshot
uv run python -m project_helios.model.train --train-date 2026-06-15

# Full local verification (matches CI)
uv run ruff check .
uv run pytest -q
```
