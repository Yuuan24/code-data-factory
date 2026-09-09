"""Incremental build snapshots with fail-closed immutable task identities."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
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
class CommitResult:
    logical_content_hash: str
    rows: tuple[dict[str, Any], ...]
    snapshot_dir: Path


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stream.write(content)
        temporary = Path(stream.name)
    os.replace(temporary, path)


def _existing_rows(destination: Path) -> dict[str, dict[str, Any]]:
    registry = destination / "registry.json"
    if not registry.is_file():
        return {}
    stored = json.loads(registry.read_text(encoding="utf-8"))
    return {str(row["task_id"]): row for row in stored["rows"]}


def commit_build(
    rows: list[dict[str, Any]],
    *,
    destination: Path,
    run_id: str,
    previous: CommitResult | None = None,
    fail_at: str | None,
) -> CommitResult:
    """Publish a content-addressed snapshot; retries are idempotent and mutations fail."""

    existing = {row["task_id"]: row for row in previous.rows} if previous else _existing_rows(destination)
    for row in rows:
        task_id = str(row["task_id"])
        if task_id in existing and canonical_json_bytes(existing[task_id]) != canonical_json_bytes(row):
            raise CommitError(f"immutable task identity conflicts for {task_id}")
        existing[task_id] = row
    merged = tuple(existing[key] for key in sorted(existing))
    content_hash = logical_content_hash(merged, "task_id")
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
            canonical_json_bytes({"run_id": run_id, "logical_content_hash": content_hash, "row_count": len(merged)}),
        )
        manifest = build_manifest(f"build-{content_hash[:12]}", run_id, staging)
        snapshot = destination / "builds" / content_hash
        try:
            atomic_commit_manifest(staging, snapshot, manifest)
        except ArtifactIntegrityError as error:
            raise CommitError(str(error)) from error
        if fail_at == "postcommit":
            raise CommitError("injected postcommit failure")
        _write_atomic(destination / "registry.json", canonical_json_bytes({"rows": list(merged)}))
        return CommitResult(logical_content_hash=content_hash, rows=merged, snapshot_dir=snapshot)
    finally:
        if staging.exists():
            for path in sorted(staging.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            staging.rmdir()
