"""US1 software checkpoint that keeps fixture-only proof distinct from real data."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import yaml

from code_data_factory.contracts.artifacts import (
    canonical_json_bytes,
    canonical_yaml_hash,
    sha256_bytes,
    sha256_file,
)
from code_data_factory.datasets.export_sft import export_sft_examples
from code_data_factory.datasets.publish import PublicationGateError, publish_dataset
from code_data_factory.processing.quality import EXTERNAL_PUBLICATION_REVIEW_CHECKS
from code_data_factory.sources.revoke import revoke_source
from code_data_factory.sources.toucan import import_toucan_records
from code_data_factory.tasks.build import build_pilot_tasks
from code_data_factory.tasks.splits import SplitRegistry


class _FixtureChatTokenizer:
    """Checkpoint-only tokenizer: never stands in for the frozen training tokenizer."""

    chat_template: str | None = "us1-checkpoint-fixture-v1"

    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]:
        del add_special_tokens
        return list(text.encode("utf-8"))

    def apply_chat_template(
        self, conversation: list[dict[str, str]], *, tokenize: bool, add_generation_prompt: bool
    ) -> list[int]:
        if not tokenize or add_generation_prompt:
            raise ValueError("fixture tokenizer only supports completed tokenized conversations")
        return self.encode(
            "".join(f"<{message['role']}>\n{message['content']}<eos>\n" for message in conversation),
            add_special_tokens=False,
        )


def _fixture_history() -> list[dict[str, Any]]:
    return [
        {
            "id": "unique",
            "tools": [{"name": "read_document", "parameters": {"type": "object"}}],
            "messages": [
                {"role": "user", "content": "Find the declared conversion."},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "read_document",
                            "arguments": {"document_id": "units-length"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": "100"},
                {"role": "assistant", "content": "100<eos>"},
            ],
        },
        {"id": "orphan", "tools": [], "messages": [{"role": "tool", "content": "unlinked"}]},
    ]


def _required_object(path: Path, *, label: str, required_keys: set[str]) -> dict[str, Any]:
    import json

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"US1 checkpoint cannot read {label}") from error
    if not isinstance(value, dict) or not required_keys <= set(value):
        raise ValueError(f"US1 checkpoint {label} lacks required evidence fields")
    return value


def run_external_migration_checkpoint(
    *,
    output_path: Path,
    build_receipt: Path,
    release_manifest: Path,
    export_audit: Path,
) -> dict[str, Any]:
    """Record software migration evidence without pretending a real source was published."""

    build = _required_object(
        build_receipt,
        label="external build receipt",
        required_keys={"member_kind", "accepted_count", "raw_external_demonstration_count"},
    )
    release = _required_object(
        release_manifest,
        label="external release manifest",
        required_keys={"member_kind", "member_count"},
    )
    export = _required_object(
        export_audit,
        label="external export audit",
        required_keys={"source_external_demonstration_count"},
    )
    checks = {
        "external_member_identity_preserved": build["member_kind"] == "EXTERNAL_DEMONSTRATION"
        and release["member_kind"] == "EXTERNAL_DEMONSTRATION",
        "admission_count_reaches_release": build["accepted_count"] == release["member_count"],
        "export_reads_external_demonstrations": export["source_external_demonstration_count"]
        == release["member_count"],
        "no_execution_attempt_required": "attempt_count" not in build
        and "verification_count" not in build,
    }
    if not all(checks.values()):
        raise ValueError("external migration checkpoint facts are inconsistent")
    receipt = {
        "checkpoint": "EXTERNAL_MIGRATION_SOFTWARE",
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_level": "SOFTWARE_VALIDATED",
        "real_external_delivery": False,
        "checks": checks,
        "input_hashes": {
            "build_receipt": sha256_file(build_receipt),
            "release_manifest": sha256_file(release_manifest),
            "export_audit": sha256_file(export_audit),
        },
        "limitations": [
            "This receipt verifies migration software only; it does not prove a real external source, review, candidate pool, or release.",
            "SC-016 through SC-018 remain open until T045 through T047 use real frozen external inputs.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_json_bytes(receipt))
    return receipt


def _json_list(path: Path, *, label: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"US1 external checkpoint cannot read {label}") from error
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"US1 external checkpoint {label} must be a JSON object list")
    return value


def run_us1_external_checkpoint(
    *,
    output_path: Path,
    production_config: Path,
    candidate_manifest: Path,
    build_receipt: Path,
    membership: Path,
    release_manifest: Path,
    release_lineage: Path,
    release_quality: Path,
    release_cost: Path,
    export_manifest: Path,
    export_audit: Path,
) -> dict[str, Any]:
    """Bind the real external candidate, immutable release, and SFT view.

    This is data-delivery evidence only.  It deliberately does not invoke a
    task environment, a sampler, a model, or a trainer.
    """

    candidate = _required_object(
        candidate_manifest,
        label="external candidate manifest",
        required_keys={"status", "counts", "logical_content_hash", "membership_sha256"},
    )
    build = _required_object(
        build_receipt,
        label="external build receipt",
        required_keys={
            "accepted_count",
            "pending_review_count",
            "project_sampling_ingress_count",
            "project_task_ingress_count",
            "raw_external_demonstration_count",
        },
    )
    release = _required_object(
        release_manifest,
        label="external release manifest",
        required_keys={"member_count", "member_kind", "input_manifest_hash", "logical_content_hash"},
    )
    lineage = _required_object(
        release_lineage,
        label="external release lineage",
        required_keys={"external_demonstrations", "source_records"},
    )
    quality = _required_object(
        release_quality,
        label="external release quality report",
        required_keys={"external_demonstration_count", "train_member_count"},
    )
    cost = _required_object(release_cost, label="external release cost report", required_keys={"cost_cny_fen"})
    exported = _required_object(
        export_manifest,
        label="external export manifest",
        required_keys={"example_count", "member_kind", "source_digest"},
    )
    audit = _required_object(
        export_audit,
        label="external loss-mask audit",
        required_keys={"example_count", "examples", "source_external_demonstration_count", "source_digest"},
    )
    config_text = production_config.read_text(encoding="utf-8")
    config = yaml.safe_load(config_text)
    if not isinstance(config, dict):
        raise ValueError("US1 external checkpoint production config must be a mapping")
    members = _json_list(membership, label="external membership")
    if not members:
        raise ValueError("US1 external checkpoint requires a non-empty real external membership")
    candidate_counts = candidate["counts"]
    if not isinstance(candidate_counts, dict):
        raise ValueError("US1 external checkpoint candidate counts must be a mapping")
    member_digest = sha256_bytes(canonical_json_bytes(members))
    member_ids = {str(item.get("demonstration_id")) for item in members}
    lineage_rows = lineage["external_demonstrations"]
    if not isinstance(lineage_rows, list) or not all(isinstance(item, dict) for item in lineage_rows):
        raise ValueError("US1 external checkpoint lineage must list external demonstrations")
    lineage_by_id = {str(item.get("demonstration_id")): item for item in lineage_rows}
    if len(member_ids) != len(members) or set(lineage_by_id) != member_ids:
        raise ValueError("US1 external checkpoint release lineage does not match the candidate membership")
    target_token_count = 0
    input_token_count = 0
    examples = audit["examples"]
    if not isinstance(examples, list) or len(examples) != len(members):
        raise ValueError("US1 external checkpoint export audit does not cover every released member")
    for member in members:
        demonstration_id = str(member.get("demonstration_id", ""))
        review_checks = member.get("review_checks")
        message_refs = member.get("upstream_message_refs")
        if not demonstration_id or member.get("source_origin") not in {"PUBLIC_ORIGINAL", "DERIVED"}:
            raise ValueError("US1 external checkpoint found non-external candidate ingress")
        if not isinstance(review_checks, list) or not EXTERNAL_PUBLICATION_REVIEW_CHECKS <= set(review_checks):
            raise ValueError("US1 external checkpoint found a member without complete review evidence")
        if not isinstance(message_refs, list) or not message_refs:
            raise ValueError("US1 external checkpoint found a member without upstream messages")
        lineage_row = lineage_by_id[demonstration_id]
        if lineage_row.get("upstream_message_refs") != message_refs:
            raise ValueError("US1 external checkpoint found mismatched upstream message lineage")
        parent = member.get("parent_demonstration_id")
        if parent is not None and lineage_row.get("parent_demonstration_id") != parent:
            raise ValueError("US1 external checkpoint found a mismatched repair parent")
    for example in examples:
        if not isinstance(example, dict):
            raise ValueError("US1 external checkpoint export examples must be objects")
        input_ids = example.get("input_ids")
        loss_mask = example.get("loss_mask")
        if not isinstance(input_ids, list) or not isinstance(loss_mask, list) or len(input_ids) != len(loss_mask):
            raise ValueError("US1 external checkpoint found invalid exported token arrays")
        input_token_count += len(input_ids)
        target_token_count += sum(bool(value) for value in loss_mask)
    if target_token_count <= 0:
        raise ValueError("US1 external checkpoint exported no effective loss tokens")
    negative_member = dict(members[0])
    negative_member.pop("review_checks", None)
    missing_review_rejected = False
    with TemporaryDirectory(prefix="cdf-us1-external-gate-") as temporary:
        try:
            publish_dataset(
                dataset_id="missing-review-evidence",
                members=[negative_member],
                output_dir=Path(temporary),
                input_manifest_hash=member_digest,
                rule_version=str(release["rule_version"]),
            )
        except PublicationGateError:
            missing_review_rejected = True
    checks = {
        "real_external_source_is_nonempty": build["raw_external_demonstration_count"] > 0,
        "candidate_counts_reconcile": candidate_counts.get("accepted") == len(members)
        and candidate_counts.get("accepted") == build["accepted_count"],
        "pending_and_rejected_are_outside_release": candidate_counts.get("pending_review")
        == build["pending_review_count"],
        "no_project_ingress": build["project_task_ingress_count"] == 0
        and build["project_sampling_ingress_count"] == 0
        and candidate_counts.get("model_generation_ingress") == 0,
        "release_preserves_candidate_membership": candidate.get("membership_sha256") == member_digest
        and release["input_manifest_hash"] == member_digest
        and candidate["logical_content_hash"] == release["logical_content_hash"],
        "every_member_has_upstream_message_and_repair_lineage": True,
        "release_quality_reconciles": quality["external_demonstration_count"] == len(members)
        and quality["train_member_count"] == len(members),
        "export_reuses_exact_member_set": exported["member_kind"] == "EXTERNAL_DEMONSTRATION"
        and exported["example_count"] == len(members)
        and audit["source_external_demonstration_count"] == len(members)
        and exported["source_digest"] == member_digest
        and audit["source_digest"] == member_digest,
        "effective_loss_tokens_are_nonzero": target_token_count > 0,
        "missing_review_evidence_is_rejected": missing_review_rejected,
        "no_environment_or_model_rebuild": True,
    }
    if not all(checks.values()):
        raise ValueError("US1 external checkpoint facts are inconsistent")
    receipt = {
        "checkpoint": "US1_EXTERNAL_RELEASE",
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_level": "SOFTWARE_VALIDATED",
        "real_external_delivery": True,
        "scope": "real external demonstration governance, immutable release, and tokenizer export",
        "counts": {
            "raw_external_demonstrations": build["raw_external_demonstration_count"],
            "accepted_external_demonstrations": len(members),
            "rejected_external_demonstrations": candidate_counts.get("rejected"),
            "pending_review_external_demonstrations": candidate_counts.get("pending_review"),
            "released_external_demonstrations": release["member_count"],
            "sft_examples": exported["example_count"],
            "sft_input_tokens": input_token_count,
            "sft_effective_loss_tokens": target_token_count,
            "provider_charge_cny_fen": cost["cost_cny_fen"],
        },
        "checks": checks,
        "input_hashes": {
            "production_config": canonical_yaml_hash(config_text),
            "candidate_manifest": sha256_file(candidate_manifest),
            "build_receipt": sha256_file(build_receipt),
            "membership": sha256_file(membership),
            "release_manifest": sha256_file(release_manifest),
            "release_lineage": sha256_file(release_lineage),
            "export_manifest": sha256_file(export_manifest),
            "export_audit": sha256_file(export_audit),
        },
        "limitations": [
            "This proves real external-data delivery, not model training, model improvement, or execution replay.",
            "The frozen pilot has pending-review members outside the release; they were not silently admitted.",
            "T044 validation assets and T058 model sampling are not inputs to this receipt.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_json_bytes(receipt))
    return receipt


def run_us1_software_checkpoint(
    *,
    output_path: Path,
    source_report: Path,
    dedup_review_summary: Path,
    equivalence_manifest: Path,
    task_config: Path,
) -> dict[str, Any]:
    """Rebuild bounded fixture paths and write a factual US1 software receipt."""

    required = (source_report, dedup_review_summary, equivalence_manifest, task_config)
    if any(not path.is_file() for path in required):
        raise ValueError("US1 checkpoint requires source, dedup, equivalence, and task-config inputs")
    source_evidence = _required_object(source_report, label="source report", required_keys={"sources"})
    dedup_evidence = _required_object(
        dedup_review_summary,
        label="dedup review summary",
        required_keys={
            "reviewed_candidate_pairs",
            "reviewed_probe_pairs",
            "review_queue_sha256",
            "review_sha256",
        },
    )
    equivalence_evidence = _required_object(
        equivalence_manifest,
        label="equivalence manifest",
        required_keys={"local_hash", "ray_hash", "full_hash", "incremental_hash", "precommit_recovery", "postcommit_recovery"},
    )
    if not isinstance(source_evidence["sources"], list) or not source_evidence["sources"]:
        raise ValueError("US1 checkpoint source report has no audited sources")
    if dedup_evidence["reviewed_candidate_pairs"] < 100 or dedup_evidence["reviewed_probe_pairs"] < 100:
        raise ValueError("US1 checkpoint requires one hundred candidate and probe reviews")
    if not isinstance(dedup_evidence["review_queue_sha256"], str) or not dedup_evidence["review_queue_sha256"]:
        raise ValueError("US1 checkpoint requires a bound dedup review queue")
    if equivalence_evidence["local_hash"] != equivalence_evidence["ray_hash"] or equivalence_evidence["full_hash"] != equivalence_evidence["incremental_hash"]:
        raise ValueError("US1 checkpoint equivalence hashes disagree")
    with TemporaryDirectory(prefix="cdf-us1-checkpoint-") as temporary:
        root = Path(temporary)
        history_path = root / "history.json"
        history_path.write_bytes(canonical_json_bytes(_fixture_history()))
        imported = import_toucan_records(
            history_path, snapshot_id="us1-checkpoint", producer_run_id="us1-checkpoint"
        )
        build = build_pilot_tasks(
            task_config,
            output_dir=root / "pilot",
            producer_run_id="us1-checkpoint",
            split_registry=SplitRegistry(policy_version="split-v1"),
        )
        attempts = [
            {
                "attempt_id": "fixture-attempt",
                "task_id": "fixture-task",
                "messages": [
                    {"role": "user", "content": "Find the declared conversion."},
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_call": {
                            "name": "read_document",
                            "arguments": {"document_id": "units-length"},
                        },
                    },
                    {"role": "tool", "content": "100"},
                    {"role": "assistant", "content": "100<eos>"},
                ],
            }
        ]
        original_attempts_sha256 = sha256_bytes(canonical_json_bytes(attempts))
        exported = export_sft_examples(
            attempts,
            output_dir=root / "export",
            tokenizer_name="test-byte-tokenizer",
            tokenizer_revision="v1",
            template_version="tool-chat-v1",
            tokenizer=_FixtureChatTokenizer(),
        )
        source_record_id = imported.records[0].source_record_id
        publication = publish_dataset(
            dataset_id="us1-fixture-release",
            members=[
                {
                    "task_id": "fixture-task",
                    "attempt_id": "fixture-attempt",
                    "source_record_ids": [source_record_id],
                    "usage_scope": "TEST",
                    "verification_status": "VERIFIED",
                    "outcome": "PASS",
                    "decision": "ACCEPT",
                    "quality_decision_id": "fixture-quality-decision",
                }
            ],
            output_dir=root / "releases",
            input_manifest_hash=sha256_file(source_report),
            rule_version="quality-v1",
        )
        revocation = revoke_source(
            source_record_id, releases_root=root / "releases", ledger_root=root / "revocations"
        )
        checks = {
            "historical_import_preserved_raw_failure": len(imported.records) == 1
            and len(imported.quarantine) == 1,
            "external_candidate_is_not_execution_evidence": len(imported.demonstrations) == 1
            and imported.demonstrations[0].replay_capability.value == "UNSUPPORTED",
            "pilot_rebuild_has_one_hundred_drafts": len(build.tasks) == 100
            and all(task.status.value == "DRAFT" for task in build.tasks),
            "sft_mask_has_model_output_only": exported.examples[0].role_loss_counts["tool"] == 0
            and exported.examples[0].role_loss_counts["assistant"] > 0,
            "sft_export_did_not_mutate_source": original_attempts_sha256
            == sha256_bytes(canonical_json_bytes(attempts)),
            "revocation_propagates_without_rewriting_release": revocation.affected_dataset_ids
            == [publication.dataset_id]
            and publication.path.joinpath("dataset_manifest.json").is_file(),
        }
    if not all(checks.values()):
        raise RuntimeError("US1 checkpoint invariant failed")
    receipt = {
        "checkpoint": "US1_SOFTWARE",
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_level": "SOFTWARE_VALIDATED",
        "counts": {
            "historical_records_imported": 1,
            "historical_records_quarantined": 1,
            "pilot_draft_tasks": 100,
            "fixture_sft_examples": 1,
            "fixture_revocation_impacts": 1,
        },
        "checks": checks,
        "input_hashes": {
            "source_report": sha256_file(source_report),
            "dedup_review_summary": sha256_file(dedup_review_summary),
            "equivalence_manifest": sha256_file(equivalence_manifest),
            "task_config": sha256_file(task_config),
        },
        "limitations": [
            "The fixture external candidate has no independent eligibility review and was not published.",
            "The 100 pilot tasks are DRAFT and were not executed or independently verified.",
            "No training-eligible release, model execution, training result, or model-value claim is evidenced.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_json_bytes(receipt))
    return receipt
