"""Bounded, privacy-preserving review receipts for deduplication candidates."""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes
from code_data_factory.contracts.tasks import TaskPackage
from code_data_factory.processing.dedup import deduplicate_tasks


class DedupReviewError(ValueError):
    """The audit corpus cannot support the required review sample."""


@dataclass(frozen=True)
class DedupReviewReceipt:
    candidate_pairs_generated: int
    reviewed_candidate_pairs: int
    reviewed_probe_pairs: int
    reviewed_duplicates: int
    missed_duplicates: int
    semantic_vector_review: str
    review_sha256: str


def _review_tasks(
    tasks: list[TaskPackage], expected_results: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, tuple[Any, ...]]]:
    rows: list[dict[str, Any]] = []
    semantic_keys: dict[str, tuple[Any, ...]] = {}
    for task in tasks:
        expected = expected_results.get(task.task_id)
        if not isinstance(expected, dict) or not isinstance(expected.get("input_value"), int):
            raise DedupReviewError(f"missing fixed review input for {task.task_id}")
        if not isinstance(expected.get("value"), int) or not isinstance(expected.get("unit"), str):
            raise DedupReviewError(f"missing fixed expected result for {task.task_id}")
        semantic_key = (
            task.task_family,
            tuple(sorted(task.source_record_ids)),
            expected["input_value"],
            expected["value"],
            expected["unit"],
        )
        semantic_keys[task.task_id] = semantic_key
        rows.append(
            {
                "task_id": task.task_id,
                "task_family": task.task_family,
                "instruction": f"{task.task_family} {expected['input_value']}",
                "facts": {
                    "source_record_ids": sorted(task.source_record_ids),
                    "expected_value": expected["value"],
                    "unit": expected["unit"],
                },
            }
        )
    return rows, semantic_keys


def review_dedup_candidates(
    *,
    tasks: list[TaskPackage],
    expected_results: dict[str, dict[str, Any]],
    output_dir: Path,
    reviewer: str,
    decisions: dict[tuple[str, str, str], dict[str, str]],
    seed: int,
    num_perm: int,
    threshold: float,
    review_size: int = 100,
) -> DedupReviewReceipt:
    """Persist externally supplied review decisions for fixed candidate pairs.

    The review basis is bounded task metadata plus private expected numeric results;
    no source prompt, tool argument, observation, or historical raw record is copied.
    This function deliberately never derives ``outcome`` from task fields: a
    caller must supply every human/independent-review decision for the fixed
    sample or the audit fails closed.
    """

    rows, semantic_keys = _review_tasks(tasks, expected_results)
    result = deduplicate_tasks(rows, num_perm=num_perm, threshold=threshold, seed=seed)
    candidates = result.candidate_pairs
    if len(candidates) < review_size:
        raise DedupReviewError(
            f"candidate pool has {len(candidates)} pairs; requires at least {review_size}"
        )
    all_pairs = [
        (left, right)
        for index, left in enumerate(sorted(semantic_keys))
        for right in sorted(semantic_keys)[index + 1 :]
    ]
    candidate_set = set(candidates)
    non_candidates = [pair for pair in all_pairs if pair not in candidate_set]
    if len(non_candidates) < review_size:
        raise DedupReviewError(
            f"non-candidate pool has {len(non_candidates)} pairs; requires {review_size} probes"
        )
    probe_pairs = random.Random(seed).sample(non_candidates, review_size)
    records: list[dict[str, Any]] = []
    for review_kind, pairs in (("CANDIDATE", candidates[:review_size]), ("MISS_PROBE", probe_pairs)):
        for left, right in pairs:
            decision = decisions.get((review_kind, left, right))
            if not isinstance(decision, dict):
                raise DedupReviewError(f"missing external decision for {review_kind}:{left}:{right}")
            outcome = decision.get("outcome")
            reason_code = decision.get("reason_code")
            if outcome not in {"DUPLICATE", "DISTINCT"} or not isinstance(reason_code, str) or not reason_code:
                raise DedupReviewError(f"invalid external decision for {review_kind}:{left}:{right}")
            left_key, right_key = semantic_keys[left], semantic_keys[right]
            records.append(
                {
                    "review_kind": review_kind,
                    "left_task_id": left,
                    "right_task_id": right,
                    "left_task_family": left_key[0],
                    "right_task_family": right_key[0],
                    "left_input_value": left_key[2],
                    "right_input_value": right_key[2],
                    "left_expected_value": left_key[3],
                    "right_expected_value": right_key[3],
                    "outcome": outcome,
                    "reason_code": reason_code,
                    "reviewer": reviewer,
                    "review_basis": "TASK_METADATA_AND_PRIVATE_EXPECTED_RESULT",
                }
            )
    reviewed_duplicates = sum(item["outcome"] == "DUPLICATE" for item in records)
    missed_duplicates = sum(
        item["review_kind"] == "MISS_PROBE" and item["outcome"] == "DUPLICATE"
        for item in records
    )
    review_sha256 = sha256_bytes(canonical_json_bytes(records))
    receipt = DedupReviewReceipt(
        candidate_pairs_generated=len(candidates),
        reviewed_candidate_pairs=review_size,
        reviewed_probe_pairs=review_size,
        reviewed_duplicates=reviewed_duplicates,
        missed_duplicates=missed_duplicates,
        semantic_vector_review="NOT_REQUIRED_NO_OBSERVED_MISS"
        if missed_duplicates == 0
        else "REQUIRED_AFTER_OBSERVED_MISS",
        review_sha256=review_sha256,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(records), output_dir / "dedup_review.parquet")
    (output_dir / "dedup_review_summary.json").write_bytes(
        canonical_json_bytes(asdict(receipt))
    )
    return receipt
