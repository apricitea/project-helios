"""Data quality pre-flight check framework.

Runs a list of named SQL checks against the warehouse before downstream
transforms run. Each check's SQL must return a single row with a single
numeric column; the check passes if that value is >= min_value. Critical
failures should abort the pipeline rather than let it silently consume
bad data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import duckdb


@dataclass(frozen=True)
class DQCheck:
    name: str
    sql: str
    critical: bool = True
    desc: str = ""
    min_value: float = 1.0


@dataclass(frozen=True)
class DQResult:
    name: str
    status: str  # "OK" | "FAIL" | "ERROR"
    value: Any
    critical: bool
    desc: str


def run_dq_checks(conn: duckdb.DuckDBPyConnection, checks: list[DQCheck]) -> list[DQResult]:
    results = []
    for check in checks:
        try:
            value = conn.execute(check.sql).fetchone()[0]
            status = "OK" if value is not None and value >= check.min_value else "FAIL"
        except Exception as e:  # DQ checks must never crash the pipeline
            value, status = str(e), "ERROR"
        results.append(DQResult(check.name, status, value, check.critical, check.desc))
    return results


def critical_failures(results: list[DQResult]) -> list[DQResult]:
    return [r for r in results if r.critical and r.status != "OK"]
