"""Fixed-denominator interactive evaluation receipts."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from code_data_factory.contracts.artifacts import canonical_json_bytes

from .suites import EvaluationSuite, EvaluationTask, SuiteError, load_suite


class InfrastructureFailure(RuntimeError):
    """A retryable evaluator infrastructure failure."""


Executor = Callable[[EvaluationTask], dict[str, object]]


def run_evaluation(*, suite_manifest: Path, split: Literal["DEVELOPMENT", "TEST"], executor: Executor, output_dir: Path, model_identity: dict[str, object], test_unlock: Path | None = None) -> dict[str, object]:
    """Run every frozen task once, retrying only one infrastructure failure."""
    suite: EvaluationSuite = load_suite(suite_manifest)
    if split == "TEST" and test_unlock is None:
        raise SuiteError("final test is locked until preregistration and data freeze")
    tasks = suite.development if split == "DEVELOPMENT" else suite.test
    records: list[dict[str, object]] = []
    for task in tasks:
        attempts: list[dict[str, object]] = []
        started = time.monotonic()
        result: dict[str, object] | None = None
        infrastructure_error: str | None = None
        for attempt_number in range(2):
            try:
                result = executor(task)
                attempts.append({"kind": "MODEL_EVALUATION", "attempt_number": attempt_number + 1, "status": "COMPLETED"})
                infrastructure_error = None
                break
            except InfrastructureFailure as error:
                infrastructure_error = str(error)
                attempts.append({"kind": "INFRASTRUCTURE", "attempt_number": attempt_number + 1, "status": "ERROR", "error": str(error)})
        success = result is not None and result.get("value") == task.expected_value and result.get("unit") == task.expected_unit and result.get("evidence") == list(task.document_ids)
        records.append({"task_id": task.task_id, "group_id": task.group_id, "family": task.family, "recovery_condition": task.recovery_condition, "unseen_combination": task.unseen_combination, "attempts": attempts, "task_success": success, "effective_execution": result is not None, "unresolved_infrastructure": infrastructure_error, "elapsed_seconds": round(time.monotonic() - started, 6), "constraint_violation": result is None or not success})
    denominator = len(records)
    successes = sum(bool(item["task_success"]) for item in records)
    effective = sum(bool(item["effective_execution"]) for item in records)
    receipt: dict[str, object] = {"kind": "interactive-evaluation", "suite_id": suite.suite_id, "suite_version": suite.version, "split": split, "model": model_identity, "fixed_denominator": denominator, "records": records, "metrics": {"task_success_at_1": successes / denominator, "effective_execution_coverage": effective / denominator, "conditional_success": successes / effective if effective else None, "recovery_success": sum(bool(item["task_success"]) for item in records if item["recovery_condition"]) / max(1, sum(bool(item["recovery_condition"]) for item in records)), "unseen_combination_success": sum(bool(item["task_success"]) for item in records if item["unseen_combination"]) / max(1, sum(bool(item["unseen_combination"]) for item in records))}, "unresolved_infrastructure_count": sum(item["unresolved_infrastructure"] is not None for item in records), "evidence_level": "EXECUTION_VALIDATED" if split == "DEVELOPMENT" else "TRAINING_EVIDENCED"}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation_run.json").write_bytes(canonical_json_bytes(receipt))
    return receipt
