"""Bounded, privacy-preserving review receipts for deduplication candidates."""

from __future__ import annotations

import json
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
class DedupReviewQueue:
    records: tuple[dict[str, Any], ...]
    candidate_pairs_generated: int
    queue_sha256: str


@dataclass(frozen=True)
class ExternalReviewSubmission:
    reviewer: str
    review_queue_sha256: str
    decisions: dict[tuple[str, str, str], dict[str, str]]


@dataclass(frozen=True)
class DedupReviewReceipt:
    candidate_pairs_generated: int
    reviewed_candidate_pairs: int
    reviewed_probe_pairs: int
    reviewed_duplicates: int
    missed_duplicates: int
    semantic_vector_review: str
    review_queue_sha256: str
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


def prepare_dedup_review_queue(
    *,
    tasks: list[TaskPackage],
    expected_results: dict[str, dict[str, Any]],
    output_dir: Path,
    seed: int,
    num_perm: int,
    threshold: float,
    review_size: int = 100,
    write_template: bool = True,
) -> DedupReviewQueue:
    """Persist the fixed, outcome-free review packet before any external decision.

    The queue hash is later required when accepting decisions, so an answer for
    one candidate/probe sample cannot be silently reused for another sample.
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
    records = tuple(
        {
            "review_kind": review_kind,
            "left_task_id": left,
            "right_task_id": right,
            "left_task_family": semantic_keys[left][0],
            "right_task_family": semantic_keys[right][0],
            "left_input_value": semantic_keys[left][2],
            "right_input_value": semantic_keys[right][2],
            "left_expected_value": semantic_keys[left][3],
            "right_expected_value": semantic_keys[right][3],
            "review_basis": "TASK_METADATA_AND_PRIVATE_EXPECTED_RESULT",
        }
        for review_kind, pairs in (
            ("CANDIDATE", candidates[:review_size]),
            ("MISS_PROBE", probe_pairs),
        )
        for left, right in pairs
    )
    queue_sha256 = sha256_bytes(canonical_json_bytes(records))
    output_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(list(records)), output_dir / "dedup_review_queue.parquet")
    (output_dir / "dedup_review_queue.json").write_bytes(
        canonical_json_bytes(
            {
                "candidate_pairs_generated": len(candidates),
                "queue_sha256": queue_sha256,
                "records": records,
            }
        )
    )
    if write_template:
        (output_dir / "dedup_review_decisions.template.json").write_bytes(
            canonical_json_bytes(
                {
                    "reviewer": "",
                    "review_queue_sha256": queue_sha256,
                    "decisions": [
                        {
                            "review_kind": item["review_kind"],
                            "left_task_id": item["left_task_id"],
                            "right_task_id": item["right_task_id"],
                            "outcome": None,
                            "reason_code": None,
                        }
                        for item in records
                    ],
                }
            )
        )
    return DedupReviewQueue(records, len(candidates), queue_sha256)


def load_external_review_submission(path: Path) -> ExternalReviewSubmission:
    """Load a human-editable decision file without trusting its pair coverage."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DedupReviewError("external review submission is unreadable") from error
    if not isinstance(payload, dict):
        raise DedupReviewError("external review submission must be an object")
    reviewer = payload.get("reviewer")
    queue_sha256 = payload.get("review_queue_sha256")
    raw_decisions = payload.get("decisions")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise DedupReviewError("external review submission requires reviewer")
    if not isinstance(queue_sha256, str) or not queue_sha256:
        raise DedupReviewError("external review submission requires review_queue_sha256")
    if not isinstance(raw_decisions, list):
        raise DedupReviewError("external review submission requires decisions")
    decisions: dict[tuple[str, str, str], dict[str, str]] = {}
    for item in raw_decisions:
        if not isinstance(item, dict):
            raise DedupReviewError("external review decision must be an object")
        kind, left, right = item.get("review_kind"), item.get("left_task_id"), item.get("right_task_id")
        outcome, reason_code = item.get("outcome"), item.get("reason_code")
        if (
            not isinstance(kind, str)
            or not kind
            or not isinstance(left, str)
            or not left
            or not isinstance(right, str)
            or not right
            or not isinstance(outcome, str)
            or not outcome
            or not isinstance(reason_code, str)
            or not reason_code
        ):
            raise DedupReviewError("external review decision is incomplete")
        key = (kind, left, right)
        if key in decisions:
            raise DedupReviewError("external review submission contains duplicate pair")
        decisions[key] = {"outcome": outcome, "reason_code": reason_code}
    return ExternalReviewSubmission(reviewer, queue_sha256, decisions)


def review_dedup_candidates(
    *,
    tasks: list[TaskPackage],
    expected_results: dict[str, dict[str, Any]],
    output_dir: Path,
    reviewer: str,
    decisions: dict[tuple[str, str, str], dict[str, str]],
    review_queue_sha256: str,
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

    queue = prepare_dedup_review_queue(
        tasks=tasks,
        expected_results=expected_results,
        output_dir=output_dir,
        seed=seed,
        num_perm=num_perm,
        threshold=threshold,
        review_size=review_size,
        write_template=False,
    )
    if review_queue_sha256 != queue.queue_sha256:
        raise DedupReviewError("external decisions do not match the fixed review queue")
    records: list[dict[str, Any]] = []
    for item in queue.records:
        review_kind = str(item["review_kind"])
        left, right = str(item["left_task_id"]), str(item["right_task_id"])
        decision = decisions.get((review_kind, left, right))
        if not isinstance(decision, dict):
            raise DedupReviewError(f"missing external decision for {review_kind}:{left}:{right}")
        outcome = decision.get("outcome")
        reason_code = decision.get("reason_code")
        if outcome not in {"DUPLICATE", "DISTINCT"} or not isinstance(reason_code, str) or not reason_code:
            raise DedupReviewError(f"invalid external decision for {review_kind}:{left}:{right}")
        records.append(
            {
                **item,
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
        candidate_pairs_generated=queue.candidate_pairs_generated,
        reviewed_candidate_pairs=review_size,
        reviewed_probe_pairs=review_size,
        reviewed_duplicates=reviewed_duplicates,
        missed_duplicates=missed_duplicates,
        semantic_vector_review="NOT_REQUIRED_NO_OBSERVED_MISS"
        if missed_duplicates == 0
        else "REQUIRED_AFTER_OBSERVED_MISS",
        review_queue_sha256=queue.queue_sha256,
        review_sha256=review_sha256,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(records), output_dir / "dedup_review.parquet")
    (output_dir / "dedup_review_summary.json").write_bytes(
        canonical_json_bytes(asdict(receipt))
    )
    return receipt


def review_dedup_submission(
    *,
    tasks: list[TaskPackage],
    expected_results: dict[str, dict[str, Any]],
    output_dir: Path,
    submission_path: Path,
    seed: int,
    num_perm: int,
    threshold: float,
    review_size: int = 100,
) -> DedupReviewReceipt:
    """Apply a validated external review file to the frozen queue."""

    submission = load_external_review_submission(submission_path)
    return review_dedup_candidates(
        tasks=tasks,
        expected_results=expected_results,
        output_dir=output_dir,
        reviewer=submission.reviewer,
        decisions=submission.decisions,
        review_queue_sha256=submission.review_queue_sha256,
        seed=seed,
        num_perm=num_perm,
        threshold=threshold,
        review_size=review_size,
    )
