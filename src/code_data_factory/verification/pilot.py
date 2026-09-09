"""Independent scoring of sealed fixed-action pilot attempts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from code_data_factory.contracts.artifacts import canonical_json_bytes
from code_data_factory.contracts.tasks import TaskPackage

from .tasks import VerificationInput, verify_result


def verify_pilot_attempts(
    *,
    tasks: list[TaskPackage],
    task_assets_root: Path,
    attempts_manifest: Path,
    output_dir: Path,
    verifier_version: str,
) -> dict[str, object]:
    """Read private expected assets only in the verifier process and emit a new immutable view."""
    payload = json.loads(attempts_manifest.read_text(encoding="utf-8"))
    attempts = payload.get("attempts") if isinstance(payload, dict) else None
    if not isinstance(attempts, list):
        raise ValueError("attempt manifest must contain attempts")
    tasks_by_id = {task.task_id: task for task in tasks}
    if len(tasks_by_id) != len(tasks):
        raise ValueError("task manifest contains duplicate task ids")
    records: list[dict[str, object]] = []
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise ValueError("attempt manifest contains an invalid attempt")
        task = tasks_by_id.get(str(attempt.get("task_id")))
        actual = attempt.get("actual")
        if task is None or not isinstance(actual, dict):
            raise ValueError("attempt lacks a known task or a sealed final output")
        expected_path = task_assets_root / task.expected_result_ref.uri
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        if not isinstance(expected, dict):
            raise ValueError("private expected result must be a mapping")
        required_evidence = json.loads(
            (task_assets_root / task.initial_resources_ref.uri).read_text(encoding="utf-8")
        ).get("document_ids")
        expected["required_evidence"] = required_evidence
        result = verify_result(
            VerificationInput(
                attempt_id=str(attempt.get("attempt_id")),
                expected=expected,
                actual=actual,
                verifier_version=verifier_version,
                forced_status="VERIFIED",
                verified_at=datetime.now(UTC),
            )
        )
        records.append(
            {
                "attempt_id": result.attempt_id,
                "task_id": task.task_id,
                "verifier_version": result.verifier_version,
                "status": result.status,
                "outcome": result.outcome,
                "checks": result.checks,
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "kind": "pilot-verifications",
        "verifier_version": verifier_version,
        "attempt_count": len(records),
        "pass_count": sum(record["outcome"] == "PASS" for record in records),
        "fail_count": sum(record["outcome"] == "FAIL" for record in records),
        "unknown_count": sum(record["outcome"] == "UNKNOWN" for record in records),
        "verifications": records,
    }
    (output_dir / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    return manifest
