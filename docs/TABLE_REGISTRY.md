# Table Registry — Index & Quick Reference

> Load this first for any SQL/pipeline task. Mirrors the "check the registry
> before writing a query" discipline used on production data teams — it
> catches schema/type mistakes before they become a bad query, and it's the
> single source of truth for what each table means.

## Tables

| Table | Layer | Grain | Source | Refresh |
|---|---|---|---|---|
| `raw_customers` | raw | 1 row per `customer_id` | Kaggle Telco Customer Churn CSV | Full replace (static reference dataset) |
| `raw_usage_events` | raw | 1 row per (`customer_id`, `event_date`) | Synthetic generator (`ingest/synthetic_usage.py`) | Full replace |
| `customer_daily_features` | feature | 1 row per (`as_of_date`, `customer_id`) | `warehouse/etl.py::refresh_customer_daily_features` | Idempotent DELETE+INSERT per `as_of_date` |

## Key guarantees

| Check | Enforced by |
|---|---|
| `customer_id` uniqueness in `raw_customers` | DQ check `customers_unique_id` |
| Every `raw_usage_events.customer_id` exists in `raw_customers` | DQ check `events_reference_known_customers` |
| `(as_of_date, customer_id)` uniqueness in `customer_daily_features` | `PRIMARY KEY` + DELETE-before-INSERT pattern |

## `customer_daily_features` columns

| Column | Type | Meaning |
|---|---|---|
| `as_of_date` | DATE | Feature computation date (part of primary key) |
| `customer_id` | VARCHAR | Joins to `raw_customers.customer_id` |
| `avg_data_usage_mb_30d` | DOUBLE | Mean daily data usage, trailing 30 days |
| `avg_voice_minutes_30d` | DOUBLE | Mean daily voice minutes, trailing 30 days |
| `billing_events_90d` | INTEGER | Count of billing-cycle events, trailing 90 days |
| `avg_days_to_pay_90d` | DOUBLE | Mean days-to-pay across billing events, trailing 90 days |
| `late_payment_count_90d` | INTEGER | Billing events with `days_to_pay` > 14, trailing 90 days |

## Pipeline pattern

`warehouse/pipeline.py` runs: load raw → DQ gate (abort on critical failure,
never silently consume bad data) → idempotent feature refresh. Re-running
for the same `as_of_date` is always safe.
