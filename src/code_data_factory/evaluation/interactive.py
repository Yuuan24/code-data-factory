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


def _integer(value: object) -> int:
    return value if isinstance(value, int) else 0


def run_evaluation(
    *,
    suite_manifest: Path,
    split: Literal["DEVELOPMENT", "TEST"],
    executor: Executor,
    output_dir: Path,
    model_identity: dict[str, object],
    test_unlock: Path | None = None,
    task_ids: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Run a frozen split (or declared development subset) with one retry at most."""
    suite: EvaluationSuite = load_suite(suite_manifest)
    if split == "TEST" and test_unlock is None:
        raise SuiteError("final test is locked until preregistration and data freeze")
    tasks = suite.development if split == "DEVELOPMENT" else suite.test
    if task_ids is not None:
        if split != "DEVELOPMENT" or not task_ids or len(set(task_ids)) != len(task_ids):
            raise SuiteError("a selected evaluation subset must be unique non-empty development tasks")
        by_id = {task.task_id: task for task in tasks}
        if any(task_id not in by_id for task_id in task_ids):
            raise SuiteError("selected evaluation task is absent from the frozen development split")
        tasks = tuple(by_id[task_id] for task_id in task_ids)
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
        success = result is not None and result.get("value") == task.expected_value and result.get("unit") == task.expected_unit and result.get("evidence") == list(task.document_ids) and bool(result.get("constraint_valid", True))
        records.append({"task_id": task.task_id, "group_id": task.group_id, "family": task.family, "recovery_condition": task.recovery_condition, "unseen_combination": task.unseen_combination, "attempts": attempts, "task_success": success, "effective_execution": result is not None, "unresolved_infrastructure": infrastructure_error, "elapsed_seconds": round(time.monotonic() - started, 6), "constraint_violation": result is None or not success, "model_calls": _integer(result.get("model_calls")) if result else 0, "completion_tokens": _integer(result.get("completion_tokens")) if result else 0, "provider_cost_cny": result.get("provider_cost_cny") if result else None, "tool_trace": result.get("tool_trace", []) if result else []})
    denominator = len(records)
    successes = sum(bool(item["task_success"]) for item in records)
    effective = sum(bool(item["effective_execution"]) for item in records)
    receipt: dict[str, object] = {"kind": "interactive-evaluation", "suite_id": suite.suite_id, "suite_version": suite.version, "split": split, "scope": "FULL_SPLIT" if task_ids is None else "DECLARED_DEVELOPMENT_SUBSET", "selected_task_ids": list(task_ids) if task_ids is not None else None, "model": model_identity, "fixed_denominator": denominator, "records": records, "metrics": {"task_success_at_1": successes / denominator, "effective_execution_coverage": effective / denominator, "conditional_success": successes / effective if effective else None, "recovery_success": sum(bool(item["task_success"]) for item in records if item["recovery_condition"]) / max(1, sum(bool(item["recovery_condition"]) for item in records)), "unseen_combination_success": sum(bool(item["task_success"]) for item in records if item["unseen_combination"]) / max(1, sum(bool(item["unseen_combination"]) for item in records)), "model_calls": sum(_integer(item["model_calls"]) for item in records), "completion_tokens": sum(_integer(item["completion_tokens"]) for item in records), "provider_cost_cny": sum(float(item["provider_cost_cny"]) for item in records if isinstance(item["provider_cost_cny"], (int, float)))}, "unresolved_infrastructure_count": sum(item["unresolved_infrastructure"] is not None for item in records), "evidence_level": "EXECUTION_VALIDATED"}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation_run.json").write_bytes(canonical_json_bytes(receipt))
    return receipt
