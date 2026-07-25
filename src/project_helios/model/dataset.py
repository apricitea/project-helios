"""Training dataset construction: features + forward-looking labels.

Labels are built from a window strictly *after* the feature as_of_date to
avoid leakage: `customer_daily_features` at train_date summarizes payment
and usage history up to that date; the late-payment label looks only at
what happens in the label_horizon_days after it.
"""

from __future__ import annotations

from datetime import date, timedelta

import duckdb
import pandas as pd

LATE_PAYMENT_THRESHOLD_DAYS = 14

FEATURE_COLUMNS = [
    "avg_data_usage_mb_30d",
    "avg_voice_minutes_30d",
    "billing_events_90d",
    "avg_days_to_pay_90d",
    "late_payment_count_90d",
    "tenure",
    "monthly_charges",
    "total_charges",
    "senior_citizen",
]
CATEGORICAL_COLUMNS = ["contract", "payment_method"]

FEATURES_SQL = """
SELECT
    f.customer_id,
    f.avg_data_usage_mb_30d, f.avg_voice_minutes_30d, f.billing_events_90d,
    f.avg_days_to_pay_90d, f.late_payment_count_90d,
    c.tenure, c.monthly_charges, c.total_charges, c.senior_citizen,
    c.contract, c.payment_method,
    CASE WHEN c.churn = 'Yes' THEN 1 ELSE 0 END AS churn_label
FROM customer_daily_features f
JOIN raw_customers c USING (customer_id)
WHERE f.as_of_date = ?
"""

LABEL_SQL = """
SELECT
    customer_id,
    MAX(CASE WHEN is_billing_event AND days_to_pay > ? THEN 1 ELSE 0 END) AS late_payment_label
FROM raw_usage_events
WHERE event_date > ?::DATE AND event_date <= ?::DATE
GROUP BY customer_id
"""


def build_training_frame(
    conn: duckdb.DuckDBPyConnection, train_date: str, label_horizon_days: int = 30
) -> pd.DataFrame:
    frame = conn.execute(FEATURES_SQL, [train_date]).df()

    label_end = date.fromisoformat(train_date) + timedelta(days=label_horizon_days)
    labels = conn.execute(
        LABEL_SQL, [LATE_PAYMENT_THRESHOLD_DAYS, train_date, str(label_end)]
    ).df()

    frame = frame.merge(labels, on="customer_id", how="left")
    frame["late_payment_label"] = frame["late_payment_label"].fillna(0).astype(int)
    return frame.dropna(subset=FEATURE_COLUMNS)
