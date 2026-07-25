"""Raw ingest + idempotent feature refresh.

`refresh_customer_daily_features` follows the standard DELETE+INSERT
refresh pattern: re-running it for the same as_of_date is safe and
produces no duplicates, because the target window is deleted before the
new rows are inserted.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

RAW_CUSTOMERS_SQL = """
CREATE OR REPLACE TABLE raw_customers AS
SELECT
    "customerID" AS customer_id,
    gender,
    SeniorCitizen AS senior_citizen,
    Partner AS partner,
    Dependents AS dependents,
    tenure,
    Contract AS contract,
    PaymentMethod AS payment_method,
    MonthlyCharges AS monthly_charges,
    TRY_CAST(TotalCharges AS DOUBLE) AS total_charges,
    Churn AS churn
FROM read_csv_auto(?)
"""

RAW_EVENTS_SQL = "CREATE OR REPLACE TABLE raw_usage_events AS SELECT * FROM read_parquet(?)"

FEATURE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS customer_daily_features (
    as_of_date DATE NOT NULL,
    customer_id VARCHAR NOT NULL,
    avg_data_usage_mb_30d DOUBLE,
    avg_voice_minutes_30d DOUBLE,
    billing_events_90d INTEGER,
    avg_days_to_pay_90d DOUBLE,
    late_payment_count_90d INTEGER,
    PRIMARY KEY (as_of_date, customer_id)
)
"""

LATE_PAYMENT_THRESHOLD_DAYS = 14


def load_raw(conn: duckdb.DuckDBPyConnection, customers_csv: Path, events_parquet: Path) -> None:
    conn.execute(RAW_CUSTOMERS_SQL, [str(customers_csv)])
    conn.execute(RAW_EVENTS_SQL, [str(events_parquet)])


def refresh_customer_daily_features(conn: duckdb.DuckDBPyConnection, as_of_date: str) -> int:
    """Idempotent DELETE+INSERT refresh of features for a single as_of_date."""
    conn.execute(FEATURE_TABLE_DDL)
    conn.execute("DELETE FROM customer_daily_features WHERE as_of_date = ?", [as_of_date])
    conn.execute(
        """
        INSERT INTO customer_daily_features
        WITH window_events AS (
            SELECT *
            FROM raw_usage_events
            WHERE event_date BETWEEN CAST(?::DATE - INTERVAL 90 DAY AS DATE) AND ?::DATE
        )
        SELECT
            ?::DATE AS as_of_date,
            customer_id,
            AVG(data_usage_mb) FILTER (WHERE event_date > ?::DATE - INTERVAL 30 DAY)
                AS avg_data_usage_mb_30d,
            AVG(voice_minutes) FILTER (WHERE event_date > ?::DATE - INTERVAL 30 DAY)
                AS avg_voice_minutes_30d,
            COUNT(*) FILTER (WHERE is_billing_event) AS billing_events_90d,
            AVG(days_to_pay) FILTER (WHERE is_billing_event) AS avg_days_to_pay_90d,
            COUNT(*) FILTER (WHERE is_billing_event AND days_to_pay > ?)
                AS late_payment_count_90d
        FROM window_events
        GROUP BY customer_id
        """,
        [as_of_date, as_of_date, as_of_date, as_of_date, as_of_date, LATE_PAYMENT_THRESHOLD_DAYS],
    )
    return conn.execute(
        "SELECT COUNT(*) FROM customer_daily_features WHERE as_of_date = ?", [as_of_date]
    ).fetchone()[0]
