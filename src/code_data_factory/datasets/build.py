"""Deterministic US1 draft build from explicit immutable input manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes
from code_data_factory.datasets.build_input import BuildInput
from code_data_factory.processing.backends import process_events
from code_data_factory.processing.commit import commit_build


@dataclass(frozen=True)
class DraftBuild:
    output_dir: Path
    logical_content_hash: str
    member_count: int


def _object(path: Path, field: str) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get(field), list):
        raise ValueError(f"{path} must contain a {field} list")
    return [item for item in value[field] if isinstance(item, dict)]


def build_draft(*, build_input: BuildInput, output_dir: Path, backend: str, run_id: str) -> DraftBuild:
    """Join task/attempt/verifier streams and commit an immutable, resumable draft.

    Scripted fixtures remain explicitly SOFTWARE_VALIDATED and cannot later be
    promoted to a TRAIN release by this build.
    """

    tasks = [item for path in build_input.task_manifests for item in _object(path, "tasks")]
    attempts = [item for path in build_input.attempt_manifests for item in _object(path, "attempts")]
    verifications = [item for path in build_input.verification_manifests for item in _object(path, "verifications")]
    task_by_id = {str(item["task_id"]): item for item in tasks}
    verification_by_attempt = {str(item["attempt_id"]): item for item in verifications}
    if len(task_by_id) != len(tasks):
        raise ValueError("task manifests contain duplicate task_id values")
    rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for attempt in attempts:
        task_id = str(attempt.get("task_id", ""))
        attempt_id = str(attempt.get("attempt_id", ""))
        task = task_by_id.get(task_id)
        verification = verification_by_attempt.get(attempt_id)
        if task is None or verification is None:
            raise ValueError(f"attempt {attempt_id} lacks a task or verification record")
        status, outcome = str(verification.get("status")), str(verification.get("outcome"))
        decision = "ACCEPT" if status == "VERIFIED" and outcome == "PASS" else "QUARANTINE"
        # Fixture records may support software integration tests, never training.
        usage_scope = str(attempt.get("usage_scope", task.get("usage_scope", "DEVELOPMENT")))
        if str(attempt.get("actor_kind")) == "SCRIPTED_FIXTURE" and usage_scope == "TRAIN":
            usage_scope = "DEVELOPMENT"
        rows.append(
            {
                "task_id": task_id,
                "attempt_id": attempt_id,
                "source_record_ids": task["source_record_ids"],
                "usage_scope": usage_scope,
                "verification_status": status,
                "outcome": outcome,
                "decision": decision,
                "actor_kind": attempt.get("actor_kind"),
                "evidence_level": "SOFTWARE_VALIDATED",
            }
        )
        events.append({"attempt_id": attempt_id, "seq": 0, "event_type": "FINAL_OUTPUT", "payload": outcome})
    processed = process_events(events, backend=backend, observation_inline_limit=4096)
    commit = commit_build(rows, destination=output_dir / "snapshots", run_id=run_id, previous=None, fail_at=None)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_hash = sha256_bytes(canonical_json_bytes(build_input.content_hashes))
    (output_dir / "membership.json").write_bytes(canonical_json_bytes(list(commit.rows)))
    (output_dir / "events.json").write_bytes(canonical_json_bytes(processed.rows))
    (output_dir / "quality_decisions.json").write_bytes(
        canonical_json_bytes(
            [
                {"attempt_id": row["attempt_id"], "action": row["decision"], "policy_version": build_input.rule_version}
                for row in commit.rows
            ]
        )
    )
    (output_dir / "build_receipt.json").write_bytes(
        canonical_json_bytes(
            {
                "run_id": run_id,
                "backend": backend,
                "evidence_level": "SOFTWARE_VALIDATED",
                "input_manifest_hash": input_hash,
                "logical_content_hash": commit.logical_content_hash,
                "member_count": len(commit.rows),
                "accepted_count": sum(row["decision"] == "ACCEPT" for row in commit.rows),
                "train_eligible_count": 0,
                "source_manifest_count": len(build_input.source_manifests),
            }
        )
    )
    return DraftBuild(output_dir, commit.logical_content_hash, len(commit.rows))
