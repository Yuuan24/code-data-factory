"""Explicit, hash-checked input manifests for data builds."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from code_data_factory.contracts.artifacts import sha256_file


class BuildInputError(ValueError):
    """A build input is incomplete, missing, or outside its manifest directory."""


@dataclass(frozen=True)
class BuildInput:
    path: Path
    source_manifests: tuple[Path, ...]
    task_manifests: tuple[Path, ...]
    attempt_manifests: tuple[Path, ...]
    verification_manifests: tuple[Path, ...]
    split_registry: Path
    rule_version: str
    content_hashes: dict[str, str]


def _paths(root: Path, raw: object, label: str) -> tuple[Path, ...]:
    if not isinstance(raw, list) or not raw:
        raise BuildInputError(f"{label} must be a non-empty list")
    paths: list[Path] = []
    for item in raw:
        if not isinstance(item, str):
            raise BuildInputError(f"{label} entries must be relative paths")
        path = (root / item).resolve()
        if root not in path.parents or not path.is_file():
            raise BuildInputError(f"{label} reference is missing or escapes manifest root: {item}")
        paths.append(path)
    return tuple(paths)


def load_build_input(path: Path) -> BuildInput:
    """Load all four fact streams; historical-only sources cannot be silently substituted."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BuildInputError("build input must be an object")
    root = path.parent.resolve()
    source = _paths(root, payload.get("source_manifests"), "source_manifests")
    tasks = _paths(root, payload.get("task_manifests"), "task_manifests")
    attempts = _paths(root, payload.get("attempt_manifests"), "attempt_manifests")
    verifications = _paths(root, payload.get("verification_manifests"), "verification_manifests")
    split_ref = payload.get("split_registry_ref")
    if not isinstance(split_ref, str):
        raise BuildInputError("split_registry_ref must be a relative path")
    split = (root / split_ref).resolve()
    if root not in split.parents or not split.is_file():
        raise BuildInputError("split registry is missing or escapes manifest root")
    version = payload.get("rule_version")
    if not isinstance(version, str) or not version:
        raise BuildInputError("rule_version is required")
    all_paths = (*source, *tasks, *attempts, *verifications, split)
    return BuildInput(
        path=path,
        source_manifests=source,
        task_manifests=tasks,
        attempt_manifests=attempts,
        verification_manifests=verifications,
        split_registry=split,
        rule_version=version,
        content_hashes={item.relative_to(root).as_posix(): sha256_file(item) for item in all_paths},
    )
