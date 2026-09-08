"""Canonical serialization, hashing, artifact checks, and atomic manifest publication."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
from collections.abc import Iterable, Mapping
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .tasks import AccessScope, ArtifactRef


class ArtifactIntegrityError(ValueError):
    """Raised when a bundle is incomplete, altered, or conflicts with an immutable publication."""


def _normalise(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalise(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {
            str(key): _normalise(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ArtifactIntegrityError("canonical JSON rejects non-finite numbers")
        return value
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Encode deterministic UTF-8 JSON suitable for content identities."""

    return json.dumps(
        _normalise(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_yaml_hash(text: str) -> str:
    """Hash parsed YAML so comments and formatting do not change configuration identity."""

    parsed = yaml.safe_load(text)
    return hashlib.sha256(canonical_json_bytes(parsed)).hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def logical_content_hash(rows: Iterable[Mapping[str, Any]], primary_key: str) -> str:
    """Hash canonical rows ordered by their stable primary key, independent of shard or row order."""

    materialised = list(rows)
    if any(primary_key not in row for row in materialised):
        raise ArtifactIntegrityError(f"every logical row needs primary key {primary_key!r}")
    values = [
        canonical_json_bytes(row)
        for row in sorted(materialised, key=lambda row: str(row[primary_key]))
    ]
    return sha256_bytes(b"\n".join(values))


class BundleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
    media_type: str = Field(min_length=1)
    producer_run_id: str = Field(min_length=1)
    access_scope: AccessScope

    @field_validator("relative_path")
    @classmethod
    def path_is_relative(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("bundle entries must be relative paths")
        return value


class ArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_id: str = Field(min_length=1)
    producer_run_id: str = Field(min_length=1)
    entries: list[BundleEntry] = Field(min_length=1)
    logical_content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    def as_artifact_refs(self) -> list[ArtifactRef]:
        return [
            ArtifactRef(
                artifact_id=entry.artifact_id,
                uri=entry.relative_path,
                sha256=entry.sha256,
                byte_size=entry.byte_size,
                media_type=entry.media_type,
                producer_run_id=entry.producer_run_id,
                access_scope=entry.access_scope,
            )
            for entry in self.entries
        ]


def build_manifest(bundle_id: str, producer_run_id: str, directory: Path) -> ArtifactManifest:
    entries = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            entries.append(
                BundleEntry(
                    artifact_id=f"{bundle_id}:{path.relative_to(directory).as_posix()}",
                    relative_path=path.relative_to(directory).as_posix(),
                    sha256=sha256_file(path),
                    byte_size=path.stat().st_size,
                    media_type="application/json"
                    if path.suffix == ".json"
                    else "application/octet-stream",
                    producer_run_id=producer_run_id,
                    access_scope=AccessScope.INTERNAL,
                )
            )
    return ArtifactManifest(bundle_id=bundle_id, producer_run_id=producer_run_id, entries=entries)


def validate_manifest(directory: Path, manifest: ArtifactManifest) -> None:
    seen = set()
    for entry in manifest.entries:
        if entry.relative_path in seen:
            raise ArtifactIntegrityError("manifest contains a duplicate path")
        seen.add(entry.relative_path)
        path = directory / entry.relative_path
        if not path.is_file():
            raise ArtifactIntegrityError(f"missing artifact: {entry.relative_path}")
        if path.stat().st_size != entry.byte_size or sha256_file(path) != entry.sha256:
            raise ArtifactIntegrityError(f"artifact digest mismatch: {entry.relative_path}")


def atomic_commit_manifest(
    staging_directory: Path, destination: Path, manifest: ArtifactManifest
) -> Path:
    """Publish a validated directory once; identical retries are accepted and partial destinations rejected."""

    validate_manifest(staging_directory, manifest)
    manifest_bytes = canonical_json_bytes(manifest)
    temporary_parent = destination.parent
    temporary_parent.mkdir(parents=True, exist_ok=True)
    temporary_path = Path(mkdtemp(prefix=f".{destination.name}.", dir=temporary_parent))
    try:
        shutil.copytree(staging_directory, temporary_path, dirs_exist_ok=True)
        (temporary_path / "manifest.json").write_bytes(manifest_bytes)
        if destination.exists():
            existing_manifest = destination / "manifest.json"
            if not existing_manifest.is_file():
                raise ArtifactIntegrityError("destination exists without a complete manifest")
            if existing_manifest.read_bytes() != manifest_bytes:
                raise ArtifactIntegrityError(
                    "immutable destination conflicts with a different manifest"
                )
            validate_manifest(destination, manifest)
            return destination
        os.replace(temporary_path, destination)
        return destination
    finally:
        if temporary_path.exists():
            shutil.rmtree(temporary_path)
