"""MinHash candidate generation followed by exact semantic equality checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes


class DedupDependencyError(RuntimeError):
    """The declared datasketch dependency is unavailable for a deduplication run."""


@dataclass(frozen=True)
class DedupResult:
    candidate_pairs: list[tuple[str, str]]
    representatives: dict[str, str]
    projection_hashes: dict[str, str]
    seed: int
    threshold: float
    num_perm: int


def write_dedup_evidence(result: DedupResult, *, output_dir: Path) -> dict[str, Path]:
    """Persist candidate, representative, projection, and rule evidence."""

    output_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = output_dir / "dedup_candidates.parquet"
    representatives_path = output_dir / "dedup_representatives.parquet"
    manifest_path = output_dir / "dedup_manifest.json"
    pq.write_table(
        pa.Table.from_pylist(
            [{"left_task_id": left, "right_task_id": right} for left, right in result.candidate_pairs],
            schema=pa.schema([("left_task_id", pa.string()), ("right_task_id", pa.string())]),
        ),
        candidates_path,
    )
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "task_id": task_id,
                    "representative_task_id": representative,
                    "projection_sha256": result.projection_hashes[task_id],
                }
                for task_id, representative in sorted(result.representatives.items())
            ],
            schema=pa.schema(
                [
                    ("task_id", pa.string()),
                    ("representative_task_id", pa.string()),
                    ("projection_sha256", pa.string()),
                ]
            ),
        ),
        representatives_path,
    )
    manifest_path.write_bytes(
        canonical_json_bytes(
            {
                "seed": result.seed,
                "threshold": result.threshold,
                "num_perm": result.num_perm,
                "candidate_count": len(result.candidate_pairs),
                "representative_count": len(set(result.representatives.values())),
                "candidates_path": candidates_path.name,
                "representatives_path": representatives_path.name,
            }
        )
    )
    return {"candidates": candidates_path, "representatives": representatives_path, "manifest": manifest_path}


def _projection(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_family": task["task_family"],
        "instruction": re.findall(r"[a-z0-9]+", str(task["instruction"]).lower()),
        "facts": task.get("facts", {}),
    }


def deduplicate_tasks(
    tasks: list[dict[str, Any]], *, num_perm: int, threshold: float, seed: int
) -> DedupResult:
    """Use datasketch only for candidates, then retain semantically distinct tasks."""

    try:
        from datasketch import MinHash, MinHashLSH  # type: ignore[import-untyped]
    except ImportError as error:
        raise DedupDependencyError("datasketch is required; run with the data dependency group") from error
    projections = {str(task["task_id"]): _projection(task) for task in tasks}
    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    signatures: dict[str, Any] = {}
    for task_id, projection in projections.items():
        signature = MinHash(num_perm=num_perm, seed=seed)
        for token in sorted(set(re.findall(r"[a-z0-9]+", canonical_json_bytes(projection).decode("utf-8").lower()))):
            signature.update(token.encode("utf-8"))
        lsh.insert(task_id, signature)
        signatures[task_id] = signature
    candidates = sorted(
        {
            tuple(sorted((task_id, match)))
            for task_id, signature in signatures.items()
            for match in lsh.query(signature)
            if task_id != match
        }
    )
    parent = {task_id: task_id for task_id in projections}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    for left, right in candidates:
        if canonical_json_bytes(projections[left]) == canonical_json_bytes(projections[right]):
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parent[max(left_root, right_root)] = min(left_root, right_root)
    return DedupResult(
        candidate_pairs=candidates,
        representatives={task_id: find(task_id) for task_id in projections},
        projection_hashes={task_id: sha256_bytes(canonical_json_bytes(value)) for task_id, value in projections.items()},
        seed=seed,
        threshold=threshold,
        num_perm=num_perm,
    )
