"""DuckDB-backed recomputable quality and cost report for membership facts."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def quality_report(membership_path: Path) -> dict[str, Any]:
    """Run the versioned SQL report rather than duplicating metrics in Python."""

    try:
        import duckdb
    except ImportError as error:
        raise RuntimeError("duckdb is required for quality reporting") from error
    sql = Path(__file__).with_name("quality_reports.sql").read_text(encoding="utf-8")
    with duckdb.connect() as connection:
        connection.from_parquet(str(membership_path)).create_view("membership")
        result = connection.execute(sql).fetchone()
        columns = [item[0] for item in connection.description]
    if result is None:
        raise RuntimeError("quality report returned no aggregate row")
    return dict(zip(columns, result, strict=True))
