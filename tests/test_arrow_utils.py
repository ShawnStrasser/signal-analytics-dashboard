"""Unit tests for Arrow serialization (no database required)."""

from datetime import datetime

import pyarrow as pa

from utils.arrow_utils import snowflake_result_to_arrow


def _roundtrip(table: pa.Table) -> pa.Table:
    return pa.ipc.open_stream(snowflake_result_to_arrow(table)).read_all()


def test_naive_timestamps_become_timezone_aware():
    table = pa.table({
        "TIMESTAMP": pa.array([datetime(2026, 7, 1, 8, 0)], pa.timestamp("ns")),
        "VALUE": [1.5],
    })
    result = _roundtrip(table)
    assert result.schema.field("TIMESTAMP").type.tz == "America/Los_Angeles"
    assert result.column("VALUE").to_pylist() == [1.5]


def test_tables_without_timestamps_pass_through():
    table = pa.table({"XD": pa.array([1, 2], pa.int64()), "ID": ["a", "b"]})
    result = _roundtrip(table)
    assert result.equals(table)
