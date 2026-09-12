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
        columns_in_membership = {
            row[0] for row in connection.execute("DESCRIBE membership").fetchall()
        }
        if "demonstration_id" in columns_in_membership:
            result = connection.execute(
                """
                SELECT
                  COUNT(DISTINCT demonstration_id) AS external_demonstration_count,
                  COUNT(DISTINCT source_record_id) AS source_record_count,
                  COUNT(*) FILTER (WHERE eligibility_action = 'ACCEPT') AS accepted_count,
                  COUNT(*) FILTER (WHERE usage_scope = 'TRAIN') AS train_member_count,
                  COUNT(*) FILTER (WHERE replay_capability = 'SUPPORTED') AS replay_supported_count,
                  COUNT(*) FILTER (WHERE replay_capability = 'UNSUPPORTED') AS replay_unsupported_count,
                  NULL::BIGINT AS cost_cny_fen,
                  NULL::DOUBLE AS cost_cny_fen_per_accepted_member
                FROM membership
                """
            ).fetchone()
        else:
            result = connection.execute(sql).fetchone()
        columns = [item[0] for item in connection.description]
    if result is None:
        raise RuntimeError("quality report returned no aggregate row")
    return dict(zip(columns, result, strict=True))
