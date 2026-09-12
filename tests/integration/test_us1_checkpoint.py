from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_data_factory.checkpoints.us1 import (
    run_external_migration_checkpoint,
    run_us1_external_checkpoint,
    run_us1_software_checkpoint,
)
from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes


def test_us1_checkpoint_rebuilds_fixture_boundaries_and_writes_receipt(tmp_path: Path) -> None:
    source = tmp_path / "source_report.json"
    dedup = tmp_path / "dedup_review_summary.json"
    equivalence = tmp_path / "equivalence.json"
    source.write_text('{"sources":[{"source_id":"fixture"}]}', encoding="utf-8")
    dedup.write_text(
        '{"reviewed_candidate_pairs":100,"reviewed_probe_pairs":100,"review_queue_sha256":"queue","review_sha256":"a"}',
        encoding="utf-8",
    )
    equivalence.write_text(
        '{"local_hash":"same","ray_hash":"same","full_hash":"same","incremental_hash":"same","precommit_recovery":"RECOVERED","postcommit_recovery":"RECOVERED"}',
        encoding="utf-8",
    )

    receipt = run_us1_software_checkpoint(
        output_path=tmp_path / "us1-software.json",
        source_report=source,
        dedup_review_summary=dedup,
        equivalence_manifest=equivalence,
        task_config=Path("configs/tasks/pilot.yaml"),
    )

    assert receipt["evidence_level"] == "SOFTWARE_VALIDATED"
    assert receipt["counts"]["pilot_draft_tasks"] == 100
    assert all(receipt["checks"].values())
    assert json.loads((tmp_path / "us1-software.json").read_text())["limitations"]


def test_us1_checkpoint_rejects_empty_evidence_placeholders(tmp_path: Path) -> None:
    source = tmp_path / "source_report.json"
    dedup = tmp_path / "dedup_review_summary.json"
    equivalence = tmp_path / "equivalence.json"
    for path in (source, dedup, equivalence):
        path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="lacks required evidence fields"):
        run_us1_software_checkpoint(
            output_path=tmp_path / "us1-software.json",
            source_report=source,
            dedup_review_summary=dedup,
            equivalence_manifest=equivalence,
            task_config=Path("configs/tasks/pilot.yaml"),
        )


def test_external_migration_checkpoint_stays_software_validated_without_real_source_data(
    tmp_path: Path,
) -> None:
    build = tmp_path / "build.json"
    release = tmp_path / "release.json"
    export = tmp_path / "export.json"
    build.write_text(
        '{"member_kind":"EXTERNAL_DEMONSTRATION","accepted_count":1,"raw_external_demonstration_count":1}',
        encoding="utf-8",
    )
    release.write_text('{"member_kind":"EXTERNAL_DEMONSTRATION","member_count":1}', encoding="utf-8")
    export.write_text('{"source_external_demonstration_count":1}', encoding="utf-8")

    receipt = run_external_migration_checkpoint(
        output_path=tmp_path / "external-migration.json",
        build_receipt=build,
        release_manifest=release,
        export_audit=export,
    )

    assert receipt["evidence_level"] == "SOFTWARE_VALIDATED"
    assert receipt["real_external_delivery"] is False
    assert receipt["checks"]["no_execution_attempt_required"] is True


def test_external_checkpoint_binds_real_membership_release_and_export(tmp_path: Path) -> None:
    source = tmp_path / "candidate.json"
    build = tmp_path / "build.json"
    membership = tmp_path / "membership.json"
    release = tmp_path / "release.json"
    lineage = tmp_path / "lineage.json"
    quality = tmp_path / "quality.json"
    cost = tmp_path / "cost.json"
    exported = tmp_path / "export.json"
    audit = tmp_path / "audit.json"
    config = tmp_path / "external-production.yaml"
    member = {
        "demonstration_id": "demo-1",
        "source_record_id": "source-1",
        "source_record_ids": ["source-1"],
        "usage_scope": "TRAIN",
        "eligibility_decision_id": "decision-1",
        "eligibility_action": "ACCEPT",
        "upstream_message_refs": ["messages/demo-1.json"],
        "source_origin": "PUBLIC_ORIGINAL",
        "replay_capability": "UNSUPPORTED",
        "parent_demonstration_id": None,
        "review_checks": [
            "source_identity",
            "upstream_tool_definition",
            "message_context",
            "target_answer_mapping",
            "split_registration",
            "sensitive_review",
        ],
    }
    member_digest = sha256_bytes(canonical_json_bytes([member]))
    source.write_text(
        json.dumps(
            {
                "status": "CANDIDATE",
                "logical_content_hash": "a" * 64,
                "membership_sha256": member_digest,
                "counts": {
                    "accepted": 1,
                    "rejected": 0,
                    "pending_review": 0,
                    "model_generation_ingress": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    build.write_text(
        json.dumps(
            {
                "raw_external_demonstration_count": 1,
                "accepted_count": 1,
                "pending_review_count": 0,
                "project_sampling_ingress_count": 0,
                "project_task_ingress_count": 0,
            }
        ),
        encoding="utf-8",
    )
    membership.write_text(json.dumps([member]), encoding="utf-8")
    release.write_text(
        json.dumps(
            {
                "member_count": 1,
                "member_kind": "EXTERNAL_DEMONSTRATION",
                "input_manifest_hash": member_digest,
                "logical_content_hash": "a" * 64,
                "rule_version": "external-sft-v1",
            }
        ),
        encoding="utf-8",
    )
    lineage.write_text(
        json.dumps({"external_demonstrations": [member], "source_records": ["source-1"]}),
        encoding="utf-8",
    )
    quality.write_text('{"external_demonstration_count":1,"train_member_count":1}', encoding="utf-8")
    cost.write_text('{"cost_cny_fen":null}', encoding="utf-8")
    exported.write_text(
        json.dumps({"example_count": 1, "member_kind": "EXTERNAL_DEMONSTRATION", "source_digest": member_digest}),
        encoding="utf-8",
    )
    audit.write_text(
        json.dumps(
            {
                "example_count": 1,
                "source_external_demonstration_count": 1,
                "source_digest": member_digest,
                "examples": [{"input_ids": [1, 2], "loss_mask": [False, True]}],
            }
        ),
        encoding="utf-8",
    )
    config.write_text("candidate_version: fixture\n", encoding="utf-8")

    receipt = run_us1_external_checkpoint(
        output_path=tmp_path / "checkpoint.json",
        production_config=config,
        candidate_manifest=source,
        build_receipt=build,
        membership=membership,
        release_manifest=release,
        release_lineage=lineage,
        release_quality=quality,
        release_cost=cost,
        export_manifest=exported,
        export_audit=audit,
    )

    assert receipt["real_external_delivery"] is True
    assert receipt["counts"]["sft_effective_loss_tokens"] == 1
    assert all(receipt["checks"].values())


def test_us1_checkpoint_rejects_a_review_summary_without_a_bound_queue(tmp_path: Path) -> None:
    source = tmp_path / "source_report.json"
    dedup = tmp_path / "dedup_review_summary.json"
    equivalence = tmp_path / "equivalence.json"
    source.write_text('{"sources":[{"source_id":"fixture"}]}', encoding="utf-8")
    dedup.write_text(
        '{"reviewed_candidate_pairs":100,"reviewed_probe_pairs":100,"review_sha256":"legacy"}',
        encoding="utf-8",
    )
    equivalence.write_text(
        '{"local_hash":"same","ray_hash":"same","full_hash":"same","incremental_hash":"same","precommit_recovery":"RECOVERED","postcommit_recovery":"RECOVERED"}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="lacks required evidence fields"):
        run_us1_software_checkpoint(
            output_path=tmp_path / "us1-software.json",
            source_report=source,
            dedup_review_summary=dedup,
            equivalence_manifest=equivalence,
            task_config=Path("configs/tasks/pilot.yaml"),
        )
