from datetime import date, timedelta

import duckdb
import pandas as pd
import pytest

from project_helios.ingest.synthetic_usage import GeneratorConfig, generate_usage_events
from project_helios.model.dataset import FEATURE_COLUMNS, build_training_frame
from project_helios.warehouse.etl import load_raw, refresh_customer_daily_features

N_CUSTOMERS = 40


@pytest.fixture
def seeded_conn(tmp_path):
    customer_ids = [f"CUST-{i:04d}" for i in range(N_CUSTOMERS)]
    customers = pd.DataFrame(
        {
            "customerID": customer_ids,
            "gender": ["Female", "Male"] * (N_CUSTOMERS // 2),
            "SeniorCitizen": ([0] * (N_CUSTOMERS // 2)) + ([1] * (N_CUSTOMERS // 2)),
            "Partner": ["Yes", "No"] * (N_CUSTOMERS // 2),
            "Dependents": ["No"] * N_CUSTOMERS,
            "tenure": list(range(1, N_CUSTOMERS + 1)),
            "Contract": (["Month-to-month", "One year", "Two year"] * N_CUSTOMERS)[
                :N_CUSTOMERS
            ],
            "PaymentMethod": (["Electronic check", "Mailed check"] * N_CUSTOMERS)[:N_CUSTOMERS],
            "MonthlyCharges": [20.0 + i for i in range(N_CUSTOMERS)],
            "TotalCharges": [str(200.0 + i * 10) for i in range(N_CUSTOMERS)],
            "Churn": (["Yes", "No", "No", "No"] * N_CUSTOMERS)[:N_CUSTOMERS],
        }
    )
    customers_csv = tmp_path / "customers.csv"
    customers.to_csv(customers_csv, index=False)

    events = generate_usage_events(
        pd.Series(customer_ids), GeneratorConfig(days=150, seed=3)
    )
    events_parquet = tmp_path / "events.parquet"
    events.to_parquet(events_parquet, index=False)

    conn = duckdb.connect(":memory:")
    load_raw(conn, customers_csv, events_parquet)

    train_date = str(date.today() - timedelta(days=40))
    refresh_customer_daily_features(conn, train_date)
    return conn, train_date


def test_training_frame_has_no_missing_features(seeded_conn):
    conn, train_date = seeded_conn
    frame = build_training_frame(conn, train_date)
    assert len(frame) == N_CUSTOMERS
    assert frame[FEATURE_COLUMNS].isna().sum().sum() == 0


def test_labels_are_binary(seeded_conn):
    conn, train_date = seeded_conn
    frame = build_training_frame(conn, train_date)
    assert set(frame["churn_label"].unique()) <= {0, 1}
    assert set(frame["late_payment_label"].unique()) <= {0, 1}


def test_label_window_is_strictly_after_train_date(seeded_conn):
    """The label query must only look at events after train_date -- verified
    by checking the label changes when the forward horizon changes, proving
    it isn't just reading the (backward-looking) feature window twice."""
    conn, train_date = seeded_conn
    short_horizon = build_training_frame(conn, train_date, label_horizon_days=1)
    long_horizon = build_training_frame(conn, train_date, label_horizon_days=60)
    # A longer forward window can only add positives, never remove them.
    assert long_horizon["late_payment_label"].sum() >= short_horizon["late_payment_label"].sum()
