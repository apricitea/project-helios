"""Orchestrates the warehouse ETL: load raw -> DQ gate -> refresh features.

Usage:
    uv run python -m project_helios.warehouse.pipeline --as-of 2026-07-25
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from project_helios.warehouse.db import get_connection
from project_helios.warehouse.dq import DQCheck, critical_failures, run_dq_checks
from project_helios.warehouse.etl import load_raw, refresh_customer_daily_features

RAW_CHECKS = [
    DQCheck(
        "customers_nonempty",
        "SELECT COUNT(*) FROM raw_customers",
        critical=True,
        desc="raw_customers must have rows",
    ),
    DQCheck(
        "customers_unique_id",
        "SELECT CASE WHEN COUNT(*) = COUNT(DISTINCT customer_id) THEN 1 ELSE 0 END "
        "FROM raw_customers",
        critical=True,
        desc="customer_id must be unique",
    ),
    DQCheck(
        "events_nonempty",
        "SELECT COUNT(*) FROM raw_usage_events",
        critical=True,
        desc="raw_usage_events must have rows",
    ),
    DQCheck(
        "events_reference_known_customers",
        "SELECT CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END FROM raw_usage_events e "
        "LEFT JOIN raw_customers c USING (customer_id) WHERE c.customer_id IS NULL",
        critical=True,
        desc="no usage events for an unknown customer_id (referential integrity)",
    ),
]


def run(customers_csv: Path, events_parquet: Path, as_of_date: str, db_path: Path) -> None:
    conn = get_connection(db_path)
    load_raw(conn, customers_csv, events_parquet)

    results = run_dq_checks(conn, RAW_CHECKS)
    for r in results:
        print(f"[{r.status}] {r.name} = {r.value}")
    failures = critical_failures(results)
    if failures:
        print(f"Aborting: {len(failures)} critical DQ check(s) failed", file=sys.stderr)
        sys.exit(1)

    n = refresh_customer_daily_features(conn, as_of_date)
    print(f"Refreshed customer_daily_features for {as_of_date}: {n:,} rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--customers", type=Path, default=Path("data/raw/WA_Fn-UseC_-Telco-Customer-Churn.csv")
    )
    parser.add_argument("--events", type=Path, default=Path("data/raw/usage_events.parquet"))
    parser.add_argument("--as-of", default=str(date.today()))
    parser.add_argument("--db", type=Path, default=Path("data/warehouse.duckdb"))
    args = parser.parse_args()
    run(args.customers, args.events, args.as_of, args.db)


if __name__ == "__main__":
    main()
