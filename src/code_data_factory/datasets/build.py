"""Deterministic US1 draft build from explicit immutable input manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes, sha256_file
from code_data_factory.datasets.build_input import BuildInput
from code_data_factory.processing.backends import process_events
from code_data_factory.processing.commit import BuildIdentity, commit_build
from code_data_factory.processing.dedup import deduplicate_tasks, write_dedup_evidence
from code_data_factory.processing.quality import (
    EXTERNAL_PUBLICATION_REVIEW_CHECKS,
    decide_quality,
    write_quality_ledger,
)


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


def _build_external_draft(
    *, build_input: BuildInput, output_dir: Path, backend: str, run_id: str
) -> DraftBuild:
    """Build a candidate pool solely from frozen external demonstrations and reviews."""

    demonstrations = [
        item
        for path in build_input.external_demonstration_manifests
        for item in _object(path, "external_demonstrations")
    ]
    decisions = [
        item
        for path in build_input.eligibility_manifests
        for item in _object(path, "eligibility_decisions")
    ]
    materials = [
        item
        for path in build_input.external_material_manifests
        for item in _object(path, "external_material")
    ]
    decision_by_demo = {str(item.get("demonstration_id")): item for item in decisions}
    material_by_demo = {str(item.get("demonstration_id")): item for item in materials}
    rows: list[dict[str, Any]] = []
    rejected_count = 0
    for demonstration in demonstrations:
        demonstration_id = str(demonstration.get("demonstration_id", ""))
        decision = decision_by_demo.get(demonstration_id)
        if decision is None:
            raise ValueError(f"external demonstration {demonstration_id} lacks an eligibility decision")
        material = material_by_demo.get(demonstration_id)
        if material is None or not isinstance(material.get("messages"), list) or not material["messages"]:
            raise ValueError(f"external demonstration {demonstration_id} lacks frozen message material")
        if decision.get("action") != "ACCEPT":
            rejected_count += 1
            continue
        review_checks = decision.get("review_checks")
        if not isinstance(review_checks, list) or not EXTERNAL_PUBLICATION_REVIEW_CHECKS <= set(review_checks):
            raise ValueError(
                f"external demonstration {demonstration_id} lacks required source, split, or sensitive review"
            )
        if demonstration.get("source_origin") not in {"PUBLIC_ORIGINAL", "DERIVED"}:
            raise ValueError("project sampling or model generation cannot enter an external candidate pool")
        message_refs = demonstration.get("message_refs")
        if not isinstance(message_refs, list) or not message_refs:
            raise ValueError(f"external demonstration {demonstration_id} lacks message lineage")
        source_record_id = demonstration.get("source_record_id")
        if not isinstance(source_record_id, str) or not source_record_id:
            raise ValueError(f"external demonstration {demonstration_id} lacks source lineage")
        decision_id = decision.get("decision_id")
        if not isinstance(decision_id, str) or not decision_id:
            raise ValueError(f"external demonstration {demonstration_id} has an invalid eligibility decision")
        rows.append(
            {
                "demonstration_id": demonstration_id,
                "source_record_id": source_record_id,
                "source_record_ids": [source_record_id],
                "usage_scope": "TRAIN",
                "eligibility_decision_id": decision_id,
                "eligibility_action": "ACCEPT",
                "upstream_message_refs": [
                    ref["uri"] if isinstance(ref, dict) and isinstance(ref.get("uri"), str) else ref
                    for ref in message_refs
                ],
                "source_origin": demonstration["source_origin"],
                "replay_capability": demonstration.get("replay_capability", "UNKNOWN"),
                "parent_demonstration_id": demonstration.get("parent_demonstration_id"),
                "messages": material["messages"],
                "review_checks": sorted(review_checks),
            }
        )
    if not rows:
        raise ValueError("external candidate build has no accepted external demonstrations")
    if len({row["demonstration_id"] for row in rows}) != len(rows):
        raise ValueError("external candidate build contains duplicate demonstration_id values")
    # The external route deliberately has no local tool/event execution.  Calling
    # the shared backend with an empty event stream preserves the same declared
    # local/Ray processing boundary without inventing interaction records.
    process_events([], backend=backend, observation_inline_limit=4096)
    input_hash = sha256_bytes(canonical_json_bytes(build_input.content_hashes))
    commit = commit_build(
        rows,
        destination=output_dir / "snapshots",
        run_id=run_id,
        previous=None,
        fail_at=None,
        build_identity=BuildIdentity(
            input_manifest_hash=input_hash,
            rule_version=build_input.rule_version,
            split_registry_hash=sha256_file(build_input.split_registry),
        ),
        primary_key="demonstration_id",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "membership.json").write_bytes(canonical_json_bytes(list(commit.rows)))
    (output_dir / "eligibility_decisions.json").write_bytes(
        canonical_json_bytes({"eligibility_decisions": decisions})
    )
    (output_dir / "build_receipt.json").write_bytes(
        canonical_json_bytes(
            {
                "run_id": run_id,
                "backend": backend,
                "evidence_level": "SOFTWARE_VALIDATED",
                "input_manifest_hash": input_hash,
                "logical_content_hash": commit.logical_content_hash,
                "member_kind": "EXTERNAL_DEMONSTRATION",
                "member_count": len(rows),
                "raw_external_demonstration_count": len(demonstrations),
                "frozen_material_count": len(materials),
                "accepted_count": len(rows),
                "rejected_or_quarantined_count": rejected_count,
                "train_eligible_count": len(rows),
                "source_manifest_count": len(build_input.source_manifests),
                "recovery_event": commit.recovery_event,
            }
        )
    )
    return DraftBuild(output_dir, commit.logical_content_hash, len(rows))


def build_draft(*, build_input: BuildInput, output_dir: Path, backend: str, run_id: str) -> DraftBuild:
    """Join task/attempt/verifier streams and commit an immutable, resumable draft.

    Scripted fixtures remain explicitly SOFTWARE_VALIDATED and cannot later be
    promoted to a TRAIN release by this build.
    """

    if build_input.external_demonstration_manifests:
        return _build_external_draft(
            build_input=build_input, output_dir=output_dir, backend=backend, run_id=run_id
        )

    tasks = [item for path in build_input.task_manifests for item in _object(path, "tasks")]
    attempts = [item for path in build_input.attempt_manifests for item in _object(path, "attempts")]
    verifications = [item for path in build_input.verification_manifests for item in _object(path, "verifications")]
    task_by_id = {str(item["task_id"]): item for item in tasks}
    verification_by_attempt = {str(item["attempt_id"]): item for item in verifications}
    if len(task_by_id) != len(tasks):
        raise ValueError("task manifests contain duplicate task_id values")
    task_roots = {str(item["task_id"]): path.parent for path in build_input.task_manifests for item in _object(path, "tasks")}
    dedup_input: list[dict[str, Any]] = []
    for task in tasks:
        instruction_ref = task.get("instruction_ref")
        if not isinstance(instruction_ref, dict) or not isinstance(instruction_ref.get("uri"), str):
            raise ValueError(f"task {task['task_id']} lacks a materialized instruction reference")
        instruction_path = task_roots[str(task["task_id"])] / instruction_ref["uri"]
        instruction_payload = json.loads(instruction_path.read_text(encoding="utf-8"))
        dedup_input.append(
            {
                "task_id": task["task_id"],
                "task_family": task["task_family"],
                "instruction": instruction_payload.get("instruction", ""),
                "facts": {
                    "source_record_ids": task["source_record_ids"],
                    "derivation_root_ids": task["derivation_root_ids"],
                },
            }
        )
    dedup = deduplicate_tasks(dedup_input, num_perm=64, threshold=0.8, seed=7)
    attempt_by_task = {str(attempt["task_id"]): str(attempt["attempt_id"]) for attempt in attempts}
    attempt_representatives = {
        attempt_id: attempt_by_task.get(task_representative, attempt_id)
        for task_id, task_representative in dedup.representatives.items()
        for attempt_id in [attempt_by_task.get(task_id)]
        if attempt_id is not None
    }
    quality = decide_quality(
        attempts=[{"attempt_id": str(attempt["attempt_id"])} for attempt in attempts],
        verifications=verifications,
        duplicate_representatives=attempt_representatives,
        policy_version=build_input.rule_version,
    )
    decision_by_attempt = {decision.subject_id: decision for decision in quality.decisions}
    rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for attempt in attempts:
        task_id = str(attempt.get("task_id", ""))
        attempt_id = str(attempt.get("attempt_id", ""))
        task_entry = task_by_id.get(task_id)
        verification = verification_by_attempt.get(attempt_id)
        if task_entry is None or verification is None:
            raise ValueError(f"attempt {attempt_id} lacks a task or verification record")
        status, outcome = str(verification.get("status")), str(verification.get("outcome"))
        quality_decision = decision_by_attempt[attempt_id]
        decision = quality_decision.action
        # Fixture records may support software integration tests, never training.
        usage_scope = str(attempt.get("usage_scope", task_entry.get("usage_scope", "DEVELOPMENT")))
        if str(attempt.get("actor_kind")) == "SCRIPTED_FIXTURE" and usage_scope == "TRAIN":
            usage_scope = "DEVELOPMENT"
        rows.append(
            {
                "task_id": task_id,
                "attempt_id": attempt_id,
                "source_record_ids": task_entry["source_record_ids"],
                "usage_scope": usage_scope,
                "verification_status": status,
                "outcome": outcome,
                "decision": decision,
                "quality_decision_id": quality_decision.decision_id,
                "actor_kind": attempt.get("actor_kind"),
                "evidence_level": "SOFTWARE_VALIDATED",
            }
        )
        events.append({"attempt_id": attempt_id, "seq": 0, "event_type": "FINAL_OUTPUT", "payload": outcome})
    processed = process_events(events, backend=backend, observation_inline_limit=4096)
    input_hash = sha256_bytes(canonical_json_bytes(build_input.content_hashes))
    commit = commit_build(
        rows,
        destination=output_dir / "snapshots",
        run_id=run_id,
        previous=None,
        fail_at=None,
        build_identity=BuildIdentity(
            input_manifest_hash=input_hash,
            rule_version=build_input.rule_version,
            split_registry_hash=sha256_file(build_input.split_registry),
        ),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    write_dedup_evidence(dedup, output_dir=output_dir / "dedup")
    write_quality_ledger(quality.decisions, output_dir=output_dir)
    (output_dir / "membership.json").write_bytes(canonical_json_bytes(list(commit.rows)))
    (output_dir / "events.json").write_bytes(canonical_json_bytes(processed.rows))
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
                "recovery_event": commit.recovery_event,
            }
        )
    )
    return DraftBuild(output_dir, commit.logical_content_hash, len(commit.rows))
