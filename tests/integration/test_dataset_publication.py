from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_data_factory.datasets.build_input import BuildInputError, load_build_input
from code_data_factory.datasets.publish import PublicationGateError, publish_dataset
from code_data_factory.datasets.quality_reports import quality_report
from code_data_factory.sources.revoke import revoke_source


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def test_build_input_requires_source_task_actual_attempt_and_verification_manifests(tmp_path: Path) -> None:
    for name in ("source", "task", "attempt", "verification", "split"):
        _write(tmp_path / f"{name}.json", {"name": name})
    manifest = tmp_path / "input.json"
    _write(
        manifest,
        {
            "source_manifests": ["source.json"],
            "task_manifests": ["task.json"],
            "attempt_manifests": ["attempt.json"],
            "verification_manifests": ["verification.json"],
            "split_registry_ref": "split.json",
            "rule_version": "v1",
        },
    )

    build_input = load_build_input(manifest)

    assert len(build_input.attempt_manifests) == 1
    broken = json.loads(manifest.read_text(encoding="utf-8"))
    broken["verification_manifests"] = []
    _write(manifest, broken)
    with pytest.raises(BuildInputError, match="verification"):
        load_build_input(manifest)


def test_publish_is_immutable_and_blocks_unverified_training_members(tmp_path: Path) -> None:
    members = [
        {
            "task_id": "task-test",
            "attempt_id": "attempt-test",
            "source_record_ids": ["source-1"],
            "usage_scope": "TEST",
            "verification_status": "VERIFIED",
            "outcome": "PASS",
            "decision": "ACCEPT",
            "quality_decision_id": "decision-test",
        }
    ]
    result = publish_dataset(
        dataset_id="fixture-v1",
        members=members,
        output_dir=tmp_path / "releases",
        input_manifest_hash="a" * 64,
        rule_version="v1",
    )
    assert result.status == "PUBLISHED"
    assert result.path.joinpath("dataset_manifest.json").is_file()
    assert json.loads(result.path.joinpath("lineage_index.json").read_text(encoding="utf-8")) == {
        "source_records": ["source-1"],
        "attempts": [
            {
                "attempt_id": "attempt-test",
                "task_id": "task-test",
                "quality_decision_id": "decision-test",
                "source_record_ids": ["source-1"],
            }
        ],
        "quality_decisions": [
            {"quality_decision_id": "decision-test", "attempt_id": "attempt-test"}
        ],
    }
    assert publish_dataset(
        dataset_id="fixture-v1",
        members=members,
        output_dir=tmp_path / "releases",
        input_manifest_hash="a" * 64,
        rule_version="v1",
    ).logical_content_hash == result.logical_content_hash
    members[0]["usage_scope"] = "TRAIN"
    with pytest.raises(PublicationGateError, match="execution-validated"):
        publish_dataset(
            dataset_id="train-v1",
            members=members,
            output_dir=tmp_path / "releases",
            input_manifest_hash="a" * 64,
            rule_version="v1",
        )


def test_source_revocation_creates_an_immutable_impact_ledger(tmp_path: Path) -> None:
    publication = publish_dataset(
        dataset_id="fixture-v1",
        members=[
            {
                "task_id": "task-test",
                "attempt_id": "attempt-test",
                "source_record_ids": ["source-1"],
                "usage_scope": "TEST",
                "verification_status": "VERIFIED",
                "outcome": "PASS",
                "decision": "ACCEPT",
                "quality_decision_id": "decision-test",
            }
        ],
        output_dir=tmp_path / "releases",
        input_manifest_hash="a" * 64,
        rule_version="v1",
    )

    _write(tmp_path / "runs.json", {"run_id": "run-1", "dataset_id": "fixture-v1"})
    _write(tmp_path / "claims.json", {"claim_id": "claim-1", "quality_decision_id": "decision-test"})
    ledger = revoke_source(
        "source-1",
        releases_root=tmp_path / "releases",
        ledger_root=tmp_path / "ledgers",
        runs_root=tmp_path,
        claims_root=tmp_path,
    )

    assert ledger.affected_dataset_ids == ["fixture-v1"]
    assert ledger.affected_run_ids == ["run-1"]
    assert ledger.affected_claim_ids == ["claim-1"]
    assert json.loads(ledger.path.read_text(encoding="utf-8"))["actions"] == {
        "datasets": "INVALIDATE_DISTRIBUTION",
        "runs": "INVALIDATE_EVIDENCE",
        "claims": "INVALIDATE_CLAIM",
    }
    assert publication.path.joinpath("dataset_manifest.json").is_file()
    assert ledger.path.is_file()


def test_quality_report_recomputes_quality_and_unknown_counts_from_membership(tmp_path: Path) -> None:
    publication = publish_dataset(
        dataset_id="fixture-report",
        members=[
            {
                "task_id": "task-test",
                "attempt_id": "attempt-test",
                "source_record_ids": ["source-1"],
                "usage_scope": "TEST",
                "verification_status": "VERIFIED",
                "outcome": "PASS",
                "decision": "ACCEPT",
                "quality_decision_id": "decision-test",
            }
        ],
        output_dir=tmp_path / "releases",
        input_manifest_hash="a" * 64,
        rule_version="v1",
    )

    report = quality_report(publication.path / "membership.parquet")

    assert report == {
        "independent_task_count": 1,
        "attempt_count": 1,
        "accepted_count": 1,
        "rejected_count": 0,
        "quarantined_count": 0,
        "verified_pass_count": 1,
        "unknown_outcome_count": 0,
        "train_member_count": 0,
        "development_member_count": 0,
        "test_member_count": 1,
        "cost_cny_fen": None,
        "cost_cny_fen_per_accepted_member": None,
    }
