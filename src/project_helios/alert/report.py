"""Weekly churn/payment ops report: stats + optional LLM narrative -> HTML.

Usage:
    uv run python -m project_helios.alert.report --as-of 2026-07-25
"""

from __future__ import annotations

import argparse
import html
from datetime import date
from pathlib import Path

import duckdb

from project_helios.alert.llm import generate_insight
from project_helios.warehouse.db import get_connection

STATS_SQL = """
SELECT
    COUNT(*) AS n_customers,
    ROUND(100.0 * SUM(CASE WHEN c.churn = 'Yes' THEN 1 ELSE 0 END) / COUNT(*), 2)
        AS churn_rate_pct,
    ROUND(AVG(f.avg_data_usage_mb_30d), 1) AS avg_data_usage_mb_30d,
    ROUND(AVG(f.avg_voice_minutes_30d), 1) AS avg_voice_minutes_30d,
    SUM(f.late_payment_count_90d) AS total_late_payments_90d,
    ROUND(100.0 * SUM(CASE WHEN f.late_payment_count_90d > 0 THEN 1 ELSE 0 END) / COUNT(*), 2)
        AS pct_customers_with_late_payment_90d
FROM customer_daily_features f
JOIN raw_customers c USING (customer_id)
WHERE f.as_of_date = ?
"""

REPORT_TEMPLATE = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Weekly CVM Report — {as_of}</title></head>
<body style="font-family: sans-serif; max-width: 720px; margin: 2rem auto;">
<h1>Weekly CVM Report — {as_of}</h1>
<h2>Key metrics</h2>
<table border="1" cellpadding="6" cellspacing="0">
{rows}
</table>
<h2>Narrative</h2>
<p>{summary}</p>
<ul>
{watch_items}
</ul>
</body>
</html>
"""


def compute_stats(conn: duckdb.DuckDBPyConnection, as_of_date: str) -> dict:
    row = conn.execute(STATS_SQL, [as_of_date]).fetchone()
    cols = [d[0] for d in conn.description]
    return dict(zip(cols, row, strict=True))


def render_html(as_of_date: str, stats: dict, insight: dict) -> str:
    rows = "\n".join(
        f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in stats.items()
    )
    watch_items = "\n".join(f"<li>{html.escape(item)}</li>" for item in insight["watch_items"])
    return REPORT_TEMPLATE.format(
        as_of=as_of_date,
        rows=rows,
        summary=html.escape(insight["summary"]),
        watch_items=watch_items or "<li>None</li>",
    )


def run(as_of_date: str, db_path: Path, out_path: Path) -> None:
    conn = get_connection(db_path)
    stats = compute_stats(conn, as_of_date)
    insight = generate_insight(stats)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html(as_of_date, stats, insight))
    print(f"Wrote report to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=str(date.today()))
    parser.add_argument("--db", type=Path, default=Path("data/warehouse.duckdb"))
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    out = args.out or Path("outputs") / f"cvm_report_{args.as_of}.html"
    run(args.as_of, args.db, out)


if __name__ == "__main__":
    main()
