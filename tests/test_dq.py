import duckdb

from project_helios.warehouse.dq import DQCheck, critical_failures, run_dq_checks


def _conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.execute("INSERT INTO t VALUES (1), (2), (3)")
    return conn


def test_passing_check_is_ok():
    checks = [DQCheck("nonempty", "SELECT COUNT(*) FROM t")]
    results = run_dq_checks(_conn(), checks)
    assert results[0].status == "OK"
    assert results[0].value == 3


def test_failing_check_is_fail():
    checks = [DQCheck("too_many", "SELECT COUNT(*) FROM t", min_value=10)]
    results = run_dq_checks(_conn(), checks)
    assert results[0].status == "FAIL"


def test_bad_sql_is_error_not_exception():
    checks = [DQCheck("broken", "SELECT * FROM nonexistent_table")]
    results = run_dq_checks(_conn(), checks)
    assert results[0].status == "ERROR"


def test_critical_failures_filters_correctly():
    checks = [
        DQCheck("ok_critical", "SELECT COUNT(*) FROM t", critical=True),
        DQCheck("fail_critical", "SELECT COUNT(*) FROM t", min_value=10, critical=True),
        DQCheck("fail_noncritical", "SELECT COUNT(*) FROM t", min_value=10, critical=False),
    ]
    results = run_dq_checks(_conn(), checks)
    failures = critical_failures(results)
    assert [f.name for f in failures] == ["fail_critical"]
