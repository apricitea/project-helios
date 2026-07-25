from datetime import date, timedelta

import duckdb
import pandas as pd
import pytest

from project_helios.ingest.synthetic_usage import GeneratorConfig, generate_usage_events
from project_helios.model.dataset import build_training_frame
from project_helios.model.train import MODEL_COLUMNS, train_classifier
from project_helios.warehouse.etl import load_raw, refresh_customer_daily_features

N_CUSTOMERS = 60


@pytest.fixture
def training_frame(tmp_path):
    customer_ids = [f"CUST-{i:04d}" for i in range(N_CUSTOMERS)]
    customers = pd.DataFrame(
        {
            "customerID": customer_ids,
            "gender": ["Female", "Male"] * (N_CUSTOMERS // 2),
            "SeniorCitizen": ([0, 1] * (N_CUSTOMERS // 2)),
            "Partner": ["Yes", "No"] * (N_CUSTOMERS // 2),
            "Dependents": ["No"] * N_CUSTOMERS,
            "tenure": list(range(1, N_CUSTOMERS + 1)),
            "Contract": (["Month-to-month", "One year", "Two year"] * N_CUSTOMERS)[
                :N_CUSTOMERS
            ],
            "PaymentMethod": (["Electronic check", "Mailed check"] * N_CUSTOMERS)[:N_CUSTOMERS],
            "MonthlyCharges": [20.0 + i for i in range(N_CUSTOMERS)],
            "TotalCharges": [str(200.0 + i * 10) for i in range(N_CUSTOMERS)],
            "Churn": (["Yes", "No"] * (N_CUSTOMERS // 2)),
        }
    )
    customers_csv = tmp_path / "customers.csv"
    customers.to_csv(customers_csv, index=False)

    events = generate_usage_events(
        pd.Series(customer_ids), GeneratorConfig(days=150, seed=5)
    )
    events_parquet = tmp_path / "events.parquet"
    events.to_parquet(events_parquet, index=False)

    conn = duckdb.connect(":memory:")
    load_raw(conn, customers_csv, events_parquet)
    train_date = str(date.today() - timedelta(days=40))
    refresh_customer_daily_features(conn, train_date)
    return build_training_frame(conn, train_date)


def test_train_classifier_produces_valid_metrics(training_frame):
    _, result = train_classifier(training_frame, "churn_label")
    assert 0.0 <= result.auc <= 1.0
    assert 0.0 <= result.brier_score <= 1.0
    assert result.n_train + result.n_holdout == len(training_frame)
    assert set(result.feature_importances.keys()) == set(MODEL_COLUMNS)


def test_train_classifier_is_deterministic(training_frame):
    # churn_label is guaranteed balanced by the fixture (alternating Yes/No);
    # late_payment_label is rare enough in 60 rows that a stratified holdout
    # can degenerate to a single class, making AUC undefined (NaN) rather
    # than merely nondeterministic.
    _, result_a = train_classifier(training_frame, "churn_label")
    _, result_b = train_classifier(training_frame, "churn_label")
    assert result_a.auc == result_b.auc
