from __future__ import annotations

from pathlib import Path

import pytest

from code_data_factory.contracts.artifacts import (
    ArtifactIntegrityError,
    atomic_commit_manifest,
    build_manifest,
    canonical_json_bytes,
    canonical_yaml_hash,
    logical_content_hash,
)


def test_canonical_content_ignores_mapping_and_yaml_comment_order() -> None:
    assert canonical_json_bytes({"b": 2, "a": 1}) == canonical_json_bytes({"a": 1, "b": 2})
    assert canonical_yaml_hash("a: 1 # comment\nb: 2\n") == canonical_yaml_hash("b: 2\na: 1\n")
    assert logical_content_hash([{"id": "b"}, {"id": "a"}], "id") == logical_content_hash(
        [{"id": "a"}, {"id": "b"}], "id"
    )


def test_atomic_commit_rejects_tampering_and_accepts_same_retry(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "record.json").write_text('{"a":1}\n', encoding="utf-8")
    manifest = build_manifest("bundle", "run-1", staging)
    destination = tmp_path / "published"
    atomic_commit_manifest(staging, destination, manifest)
    assert atomic_commit_manifest(staging, destination, manifest) == destination
    (destination / "record.json").write_text('{"a":2}\n', encoding="utf-8")
    with pytest.raises(ArtifactIntegrityError, match="digest mismatch"):
        atomic_commit_manifest(staging, destination, manifest)


def test_atomic_commit_rejects_existing_partial_destination(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "record.json").write_text('{"a":1}\n', encoding="utf-8")
    manifest = build_manifest("bundle", "run-1", staging)
    destination = tmp_path / "partial"
    destination.mkdir()
    with pytest.raises(ArtifactIntegrityError, match="without a complete manifest"):
        atomic_commit_manifest(staging, destination, manifest)
