"""Incremental build snapshots with fail-closed immutable task identities."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from code_data_factory.contracts.artifacts import (
    ArtifactIntegrityError,
    atomic_commit_manifest,
    build_manifest,
    canonical_json_bytes,
    logical_content_hash,
)


class CommitError(RuntimeError):
    """A build cannot be committed or safely resumed."""


@dataclass(frozen=True)
class BuildIdentity:
    """The immutable inputs that govern membership, beyond member row bytes."""

    input_manifest_hash: str = "UNSPECIFIED"
    rule_version: str = "UNSPECIFIED"
    split_registry_hash: str = "UNSPECIFIED"


@dataclass(frozen=True)
class CommitResult:
    logical_content_hash: str
    rows: tuple[dict[str, Any], ...]
    snapshot_dir: Path
    recovery_event: str


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stream.write(content)
        temporary = Path(stream.name)
    os.replace(temporary, path)


def _existing_rows(destination: Path, *, primary_key: str) -> dict[str, dict[str, Any]]:
    registry = destination / "registry.json"
    if not registry.is_file():
        return {}
    stored = json.loads(registry.read_text(encoding="utf-8"))
    if stored.get("primary_key", "task_id") != primary_key:
        raise CommitError("existing registry uses a different immutable member identity")
    return {str(row[primary_key]): row for row in stored["rows"]}


def _existing_identity(destination: Path) -> BuildIdentity | None:
    registry = destination / "registry.json"
    if not registry.is_file():
        return None
    stored = json.loads(registry.read_text(encoding="utf-8"))
    identity = stored.get("build_identity")
    if identity is None:
        return None
    if not isinstance(identity, dict):
        raise CommitError("registry build identity is invalid")
    fields = ("input_manifest_hash", "rule_version", "split_registry_hash")
    if any(not isinstance(identity.get(field), str) for field in fields):
        raise CommitError("registry build identity is incomplete")
    return BuildIdentity(**{field: identity[field] for field in fields})


def commit_build(
    rows: list[dict[str, Any]],
    *,
    destination: Path,
    run_id: str,
    previous: CommitResult | None = None,
    fail_at: str | None,
    build_identity: BuildIdentity = BuildIdentity(),
    primary_key: str = "task_id",
) -> CommitResult:
    """Publish a content-addressed snapshot; retries are idempotent and mutations fail."""

    existing = (
        {str(row[primary_key]): row for row in previous.rows}
        if previous
        else _existing_rows(destination, primary_key=primary_key)
    )
    existing_identity = None if previous else _existing_identity(destination)
    if existing_identity is not None and existing_identity != build_identity:
        raise CommitError("immutable build identity conflicts with existing registry")
    for row in rows:
        member_id = str(row[primary_key])
        if member_id in existing and canonical_json_bytes(existing[member_id]) != canonical_json_bytes(row):
            raise CommitError(f"immutable member identity conflicts for {member_id}")
        existing[member_id] = row
    merged = tuple(existing[key] for key in sorted(existing))
    content_hash = logical_content_hash(merged, primary_key)
    if fail_at == "precommit":
        raise CommitError("injected precommit failure")

    staging = destination.parent / f".{destination.name}-{content_hash[:12]}-staging"
    if staging.exists():
        raise CommitError("staging directory unexpectedly exists")
    staging.mkdir(parents=True)
    try:
        _write_atomic(staging / "rows.json", canonical_json_bytes(list(merged)))
        _write_atomic(
            staging / "commit.json",
            canonical_json_bytes(
                {
                    "run_id": run_id,
                    "logical_content_hash": content_hash,
                    "row_count": len(merged),
                    "primary_key": primary_key,
                    "build_identity": asdict(build_identity),
                }
            ),
        )
        manifest = build_manifest(f"build-{content_hash[:12]}", run_id, staging)
        snapshot = destination / "builds" / content_hash
        recovery_event = "POSTCOMMIT_RECOVERED" if snapshot.exists() else "NEW_COMMIT"
        try:
            atomic_commit_manifest(staging, snapshot, manifest)
        except ArtifactIntegrityError as error:
            raise CommitError(str(error)) from error
        if fail_at == "postcommit":
            raise CommitError("injected postcommit failure")
        _write_atomic(
            destination / "registry.json",
            canonical_json_bytes(
                {
                    "rows": list(merged),
                    "primary_key": primary_key,
                    "build_identity": asdict(build_identity),
                    "recovery_event": recovery_event,
                }
            ),
        )
        return CommitResult(
            logical_content_hash=content_hash,
            rows=merged,
            snapshot_dir=snapshot,
            recovery_event=recovery_event,
        )
    finally:
        if staging.exists():
            for path in sorted(staging.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            staging.rmdir()
