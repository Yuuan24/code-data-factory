from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_data_factory.processing.dedup_review import (
    DedupReviewError,
    load_external_review_submission,
    prepare_dedup_review_queue,
    review_dedup_candidates,
)
from code_data_factory.tasks.build import build_pilot_tasks
from code_data_factory.tasks.splits import SplitRegistry


def test_dedup_review_has_one_hundred_candidates_and_one_hundred_miss_probes(tmp_path: Path) -> None:
    build = build_pilot_tasks(
        Path("configs/tasks/pilot.yaml"),
        output_dir=tmp_path / "pilot",
        producer_run_id="review-test",
        split_registry=SplitRegistry(policy_version="split-v1"),
    )
    task_ids = [task.task_id for task in build.tasks]
    decisions = {
        (review_kind, left, right): {
            "outcome": "DISTINCT",
            "reason_code": "INDEPENDENT_TEST_REVIEW",
        }
        for review_kind in ("CANDIDATE", "MISS_PROBE")
        for index, left in enumerate(task_ids)
        for right in task_ids[index + 1 :]
    }

    queue = prepare_dedup_review_queue(
        tasks=build.tasks,
        expected_results=build.expected_results,
        output_dir=tmp_path / "audit",
        seed=7,
        num_perm=64,
        threshold=0.8,
    )
    assert len(queue.records) == 200
    assert all("outcome" not in item for item in queue.records)
    template = json.loads(
        (tmp_path / "audit" / "dedup_review_decisions.template.json").read_text(encoding="utf-8")
    )
    assert len(template["decisions"]) == 200
    assert all(item["outcome"] is None for item in template["decisions"])
    receipt = review_dedup_candidates(
        tasks=build.tasks,
        expected_results=build.expected_results,
        output_dir=tmp_path / "audit",
        reviewer="test-reviewer",
        decisions=decisions,
        review_queue_sha256=queue.queue_sha256,
        seed=7,
        num_perm=64,
        threshold=0.8,
    )

    assert receipt.candidate_pairs_generated >= 100
    assert receipt.reviewed_candidate_pairs == 100
    assert receipt.reviewed_probe_pairs == 100
    assert receipt.missed_duplicates == 0
    assert receipt.semantic_vector_review == "NOT_REQUIRED_NO_OBSERVED_MISS"
    assert receipt.review_queue_sha256 == queue.queue_sha256
    assert (tmp_path / "audit" / "dedup_review.parquet").is_file()


def test_dedup_review_rejects_automatically_missing_external_decisions(tmp_path: Path) -> None:
    build = build_pilot_tasks(
        Path("configs/tasks/pilot.yaml"),
        output_dir=tmp_path / "pilot",
        producer_run_id="review-test",
        split_registry=SplitRegistry(policy_version="split-v1"),
    )

    queue = prepare_dedup_review_queue(
        tasks=build.tasks,
        expected_results=build.expected_results,
        output_dir=tmp_path / "audit",
        seed=7,
        num_perm=64,
        threshold=0.8,
    )
    with pytest.raises(DedupReviewError, match="missing external decision"):
        review_dedup_candidates(
            tasks=build.tasks,
            expected_results=build.expected_results,
            output_dir=tmp_path / "audit",
            reviewer="test-reviewer",
            decisions={},
            review_queue_sha256=queue.queue_sha256,
            seed=7,
            num_perm=64,
            threshold=0.8,
        )


def test_external_review_submission_rejects_blank_template_and_duplicate_pair(tmp_path: Path) -> None:
    template = tmp_path / "submission.json"
    template.write_text(
        json.dumps(
            {
                "reviewer": "reviewer-1",
                "review_queue_sha256": "queue",
                "decisions": [
                    {
                        "review_kind": "CANDIDATE",
                        "left_task_id": "left",
                        "right_task_id": "right",
                        "outcome": None,
                        "reason_code": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(DedupReviewError, match="incomplete"):
        load_external_review_submission(template)

    template.write_text(
        json.dumps(
            {
                "reviewer": "reviewer-1",
                "review_queue_sha256": "queue",
                "decisions": [
                    {
                        "review_kind": "CANDIDATE",
                        "left_task_id": "left",
                        "right_task_id": "right",
                        "outcome": "DISTINCT",
                        "reason_code": "REVIEWED",
                    },
                    {
                        "review_kind": "CANDIDATE",
                        "left_task_id": "left",
                        "right_task_id": "right",
                        "outcome": "DISTINCT",
                        "reason_code": "REVIEWED",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(DedupReviewError, match="duplicate pair"):
        load_external_review_submission(template)
