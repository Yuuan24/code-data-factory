"""Evidence-first development findings; hypotheses never overwrite observed facts."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from code_data_factory.contracts.artifacts import canonical_json_bytes


class FindingError(ValueError):
    """Evaluation evidence cannot support a feedback finding."""


def build_findings(evaluation_path: Path, *, output_dir: Path) -> dict[str, object]:
    """Aggregate failed development items into reproducible, explicitly non-causal findings."""
    payload = json.loads(evaluation_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("split") != "DEVELOPMENT":
        raise FindingError("findings require a development evaluation receipt")
    records = payload.get("records")
    if not isinstance(records, list):
        raise FindingError("evaluation receipt lacks item records")
    connection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE records(task_id VARCHAR, family VARCHAR, task_success BOOLEAN, unresolved_infrastructure VARCHAR)")
    connection.executemany(
        "INSERT INTO records VALUES (?, ?, ?, ?)",
        [(str(item.get("task_id")), str(item.get("family")), bool(item.get("task_success")), item.get("unresolved_infrastructure")) for item in records if isinstance(item, dict)],
    )
    rows = connection.execute("SELECT family, count(*) FILTER (WHERE NOT task_success), count(*) FILTER (WHERE task_success), list(task_id) FILTER (WHERE NOT task_success) FROM records GROUP BY family ORDER BY family").fetchall()
    findings: list[dict[str, object]] = []
    for family, failures, successes, task_ids in rows:
        if not failures:
            continue
        category = "INFRASTRUCTURE" if all(item.get("unresolved_infrastructure") for item in records if isinstance(item, dict) and item.get("family") == family and not item.get("task_success")) else "CONSTRAINT_FAILURE"
        findings.append({"finding_id": f"finding-{family}", "evaluation_ref": evaluation_path.name, "family": family, "raw_task_ids": sorted(str(item) for item in task_ids), "observed_failure_count": int(failures), "counterevidence_success_count": int(successes), "error_category": category, "cause_hypothesis": f"The current policy may under-cover {family} {category.lower()} patterns.", "hypothesis_status": "UNPROVEN", "confidence": "LOW" if successes else "MEDIUM", "target_slice": {"task_family": family, "failure_type": category}})
    receipt: dict[str, object] = {"kind": "development-findings", "evaluation_split": "DEVELOPMENT", "findings": findings, "causal_claim": "NOT_ESTABLISHED"}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "findings.json").write_bytes(canonical_json_bytes(receipt))
    return receipt
