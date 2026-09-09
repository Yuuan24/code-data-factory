from __future__ import annotations

from pathlib import Path

import pytest

from code_data_factory.processing.commit import BuildIdentity, CommitError, commit_build
from code_data_factory.tasks.splits import BridgeConflict, SplitRegistry


def test_split_registry_keeps_source_template_and_duplicate_groups_together() -> None:
    registry = SplitRegistry(policy_version="split-v1")
    registry.assign(
        [
            {"task_id": "a", "source_groups": ["source-1"], "template_root": "template-a"},
            {"task_id": "b", "source_groups": ["source-1"], "template_root": "template-b"},
            {"task_id": "c", "source_groups": ["source-2"], "template_root": "template-a"},
        ]
    )

    assignments = {item.task_id: item.scope for item in registry.assignments}
    assert assignments["a"] == assignments["b"] == assignments["c"]


def test_bridge_between_frozen_scopes_is_quarantined_not_reshuffled() -> None:
    registry = SplitRegistry(policy_version="split-v1")
    registry.freeze({"a": "TRAIN", "b": "TEST"})

    result = registry.assign(
        [
            {
                "task_id": "bridge",
                "source_groups": ["group-a", "group-b"],
                "template_root": "bridge-template",
                "related_task_ids": ["a", "b"],
            }
        ]
    )

    assert result.conflicts == [
        BridgeConflict(task_id="bridge", conflicting_scopes=("TEST", "TRAIN"), related_task_ids=("a", "b"))
    ]
    assert result.quarantined_task_ids == ["bridge"]
    assert registry.frozen_assignments == {"a": "TRAIN", "b": "TEST"}
    assert result.invalidated_task_ids == ("a", "b")


def test_split_registry_persists_frozen_assignments_and_conflict_receipt(tmp_path: Path) -> None:
    registry = SplitRegistry(policy_version="split-v1")
    result = registry.assign(
        [{"task_id": "a", "source_groups": ["source-1"], "template_root": "template-a"}]
    )
    path = tmp_path / "split_registry.json"
    registry.write(path, result=result)

    restored = SplitRegistry.load(path)

    assert restored.policy_version == "split-v1"
    assert restored.frozen_assignments == registry.frozen_assignments


def test_incremental_and_full_commit_are_equivalent_and_recover_after_precommit_failure(
    tmp_path: Path,
) -> None:
    inputs = [
        {"task_id": "a", "projection": "lookup length", "scope": "TRAIN"},
        {"task_id": "b", "projection": "convert cm metre", "scope": "TEST"},
    ]
    full = commit_build(inputs, destination=tmp_path / "full", run_id="full", fail_at=None)
    incremental = commit_build(
        inputs[:1],
        destination=tmp_path / "incremental",
        run_id="incremental-1",
        fail_at=None,
    )
    incremental = commit_build(
        inputs[1:],
        destination=tmp_path / "incremental",
        run_id="incremental-2",
        previous=incremental,
        fail_at=None,
    )

    assert full.logical_content_hash == incremental.logical_content_hash
    with pytest.raises(CommitError, match="injected precommit failure"):
        commit_build(inputs, destination=tmp_path / "failed", run_id="failed", fail_at="precommit")
    assert not (tmp_path / "failed" / "manifest.json").exists()
    recovered = commit_build(inputs, destination=tmp_path / "failed", run_id="recovered", fail_at=None)
    assert recovered.logical_content_hash == full.logical_content_hash


def test_postcommit_retry_is_idempotent_and_conflicting_publication_is_rejected(tmp_path: Path) -> None:
    rows = [{"task_id": "a", "projection": "lookup", "scope": "TRAIN"}]
    first = commit_build(rows, destination=tmp_path / "published", run_id="run-1", fail_at=None)
    retry = commit_build(rows, destination=tmp_path / "published", run_id="run-1", fail_at=None)
    assert retry.logical_content_hash == first.logical_content_hash
    with pytest.raises(CommitError, match="immutable"):
        commit_build(
            [{"task_id": "a", "projection": "different", "scope": "TRAIN"}],
            destination=tmp_path / "published",
            run_id="run-2",
            fail_at=None,
        )


def test_commit_records_build_identity_and_rejects_a_rule_change_in_place(tmp_path: Path) -> None:
    identity = BuildIdentity("input-hash", "quality-v1", "split-hash")
    result = commit_build(
        [{"task_id": "a", "projection": "lookup", "scope": "TEST"}],
        destination=tmp_path / "published",
        run_id="run-1",
        fail_at=None,
        build_identity=identity,
    )

    assert result.recovery_event == "NEW_COMMIT"
    with pytest.raises(CommitError, match="build identity"):
        commit_build(
            [{"task_id": "a", "projection": "lookup", "scope": "TEST"}],
            destination=tmp_path / "published",
            run_id="run-1",
            fail_at=None,
            build_identity=BuildIdentity("input-hash", "quality-v2", "split-hash"),
        )
