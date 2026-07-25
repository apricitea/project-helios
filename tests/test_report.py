import duckdb

from project_helios.alert.report import compute_stats, render_html


def _seeded_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE raw_customers (customer_id VARCHAR, churn VARCHAR)")
    conn.execute(
        "INSERT INTO raw_customers VALUES ('C1', 'Yes'), ('C2', 'No'), ('C3', 'No')"
    )
    conn.execute(
        """
        CREATE TABLE customer_daily_features (
            as_of_date DATE, customer_id VARCHAR,
            avg_data_usage_mb_30d DOUBLE, avg_voice_minutes_30d DOUBLE,
            late_payment_count_90d INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO customer_daily_features VALUES
            ('2026-07-25', 'C1', 100.0, 50.0, 2),
            ('2026-07-25', 'C2', 200.0, 60.0, 0),
            ('2026-07-25', 'C3', 300.0, 70.0, 0)
        """
    )
    return conn


def test_compute_stats_shape():
    stats = compute_stats(_seeded_conn(), "2026-07-25")
    assert stats["n_customers"] == 3
    assert stats["churn_rate_pct"] == 33.33
    assert stats["total_late_payments_90d"] == 2
    assert stats["pct_customers_with_late_payment_90d"] == 33.33


def test_render_html_escapes_and_includes_content():
    stats = {"n_customers": 3, "churn_rate_pct": 33.33}
    insight = {"summary": "Churn <up> & watch it", "watch_items": ["Item A", "Item B"]}
    out = render_html("2026-07-25", stats, insight)
    assert "Churn &lt;up&gt; &amp; watch it" in out
    assert "<li>Item A</li>" in out
    assert "<li>Item B</li>" in out
    assert "n_customers" in out


def test_render_html_no_watch_items():
    out = render_html("2026-07-25", {"n": 1}, {"summary": "ok", "watch_items": []})
    assert "<li>None</li>" in out
