from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from project_helios.ingest.synthetic_usage import GeneratorConfig, generate_usage_events
from project_helios.warehouse.etl import load_raw, refresh_customer_daily_features

CUSTOMER_IDS = ["C0001", "C0002", "C0003"]


def _write_fixtures(tmp_path: Path) -> tuple[Path, Path]:
    customers = pd.DataFrame(
        {
            "customerID": CUSTOMER_IDS,
            "gender": ["Female", "Male", "Male"],
            "SeniorCitizen": [0, 0, 1],
            "Partner": ["Yes", "No", "No"],
            "Dependents": ["No", "No", "Yes"],
            "tenure": [12, 24, 3],
            "Contract": ["Month-to-month", "One year", "Two year"],
            "PaymentMethod": ["Electronic check", "Mailed check", "Bank transfer"],
            "MonthlyCharges": [29.85, 56.95, 53.85],
            "TotalCharges": ["358.20", "1366.8", "161.55"],
            "Churn": ["No", "No", "Yes"],
        }
    )
    customers_csv = tmp_path / "customers.csv"
    customers.to_csv(customers_csv, index=False)

    events = generate_usage_events(pd.Series(CUSTOMER_IDS), GeneratorConfig(days=100, seed=1))
    events_parquet = tmp_path / "events.parquet"
    events.to_parquet(events_parquet, index=False)

    return customers_csv, events_parquet


def test_refresh_produces_one_row_per_customer(tmp_path: Path):
    customers_csv, events_parquet = _write_fixtures(tmp_path)
    conn = duckdb.connect(":memory:")
    load_raw(conn, customers_csv, events_parquet)

    as_of = str(date.today())
    n = refresh_customer_daily_features(conn, as_of)

    assert n == len(CUSTOMER_IDS)
    rows = conn.execute(
        "SELECT customer_id FROM customer_daily_features WHERE as_of_date = ?", [as_of]
    ).fetchall()
    assert {r[0] for r in rows} == set(CUSTOMER_IDS)


def test_refresh_is_idempotent(tmp_path: Path):
    customers_csv, events_parquet = _write_fixtures(tmp_path)
    conn = duckdb.connect(":memory:")
    load_raw(conn, customers_csv, events_parquet)

    as_of = str(date.today())
    refresh_customer_daily_features(conn, as_of)
    refresh_customer_daily_features(conn, as_of)  # re-run must not duplicate

    total = conn.execute(
        "SELECT COUNT(*) FROM customer_daily_features WHERE as_of_date = ?", [as_of]
    ).fetchone()[0]
    assert total == len(CUSTOMER_IDS)
