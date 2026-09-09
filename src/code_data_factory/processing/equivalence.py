"""Evidence receipt for local/Ray and full/incremental logical equivalence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from code_data_factory.contracts.artifacts import canonical_json_bytes, logical_content_hash
from code_data_factory.processing.backends import process_events
from code_data_factory.processing.commit import CommitError, commit_build


@dataclass(frozen=True)
class EquivalenceReceipt:
    local_hash: str
    ray_hash: str
    full_hash: str
    incremental_hash: str
    precommit_recovery: str
    postcommit_retry: str


def run_equivalence(rows: list[dict[str, Any]], *, output_dir: Path) -> EquivalenceReceipt:
    """Execute the four required software paths and save a machine-readable receipt."""

    events = [
        {"attempt_id": row["task_id"], "seq": 0, "event_type": "OBSERVATION", "payload": row["projection"]}
        for row in rows
    ]
    local = process_events(events, backend="local", observation_inline_limit=64)
    ray = process_events(events, backend="ray", observation_inline_limit=64)
    local_hash = logical_content_hash(local.rows, "attempt_id")
    ray_hash = logical_content_hash(ray.rows, "attempt_id")
    if local_hash != ray_hash:
        raise RuntimeError("local and Ray event projections differ")
    full = commit_build(rows, destination=output_dir / "full", run_id="full", fail_at=None)
    first = commit_build(rows[: max(1, len(rows) // 2)], destination=output_dir / "incremental", run_id="incremental-1", fail_at=None)
    incremental = commit_build(rows[len(first.rows) :], destination=output_dir / "incremental", run_id="incremental-2", previous=first, fail_at=None)
    if full.logical_content_hash != incremental.logical_content_hash:
        raise RuntimeError("full and incremental commits differ")
    try:
        commit_build(rows, destination=output_dir / "precommit", run_id="failed", fail_at="precommit")
    except CommitError:
        precommit_recovery = "REJECTED_THEN_RECOVERED"
    else:
        raise RuntimeError("precommit injection did not fail")
    recovered = commit_build(rows, destination=output_dir / "precommit", run_id="recovered", fail_at=None)
    retry = commit_build(rows, destination=output_dir / "postcommit", run_id="retry", fail_at=None)
    retry = commit_build(rows, destination=output_dir / "postcommit", run_id="retry", previous=retry, fail_at=None)
    if recovered.logical_content_hash != full.logical_content_hash or retry.logical_content_hash != full.logical_content_hash:
        raise RuntimeError("recovery changed logical content")
    receipt = EquivalenceReceipt(local_hash, ray_hash, full.logical_content_hash, incremental.logical_content_hash, precommit_recovery, "IDEMPOTENT")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_bytes(canonical_json_bytes(asdict(receipt)))
    return receipt
