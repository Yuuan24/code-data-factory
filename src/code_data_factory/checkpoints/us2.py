"""US2 execution-evidence checkpoint without importing data-release evidence."""

from __future__ import annotations

import json
import xml.etree.ElementTree as xml
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_file


def _object(path: Path, *, label: str, keys: set[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"US2 checkpoint cannot read {label}") from error
    if not isinstance(value, dict) or not keys <= set(value):
        raise ValueError(f"US2 checkpoint {label} lacks required evidence fields")
    return value


def _control_counts(path: Path) -> tuple[int, int, int, int]:
    try:
        root = xml.parse(path).getroot()
    except (OSError, xml.ParseError) as error:
        raise ValueError("US2 checkpoint cannot read verifier controls JUnit") from error
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise ValueError("US2 checkpoint verifier controls JUnit has no suite")
    tests = sum(int(suite.get("tests", "0")) for suite in suites)
    failures = sum(int(suite.get("failures", "0")) for suite in suites)
    errors = sum(int(suite.get("errors", "0")) for suite in suites)
    skipped = sum(int(suite.get("skipped", "0")) for suite in suites)
    return tests, failures, errors, skipped


def run_us2_checkpoint(
    *,
    output_path: Path,
    preflight_path: Path,
    verification_manifest: Path,
    task_audit_path: Path,
    controls_junit: Path,
    migration_baseline_commit: str,
    changed_execution_paths: list[str],
) -> dict[str, Any]:
    """Record actual fixed-action evidence after a bounded migration-impact review."""

    preflight = _object(preflight_path, label="preflight", keys={"status", "findings"})
    verification = _object(
        verification_manifest,
        label="verification manifest",
        keys={"attempt_count", "pass_count", "fail_count", "unknown_count", "verifications"},
    )
    audit = _object(
        task_audit_path,
        label="task audit",
        keys={"task_count", "attempt_count", "all_tasks_passed_twice", "tasks"},
    )
    findings = preflight["findings"]
    tasks = audit["tasks"]
    verifications = verification["verifications"]
    if not isinstance(findings, dict) or not isinstance(tasks, list) or not isinstance(verifications, list):
        raise ValueError("US2 checkpoint evidence has invalid collection fields")
    every_task_twice = all(
        isinstance(task, dict)
        and isinstance(task.get("attempts"), list)
        and len(task["attempts"]) == 2
        and all(
            isinstance(attempt, dict)
            and attempt.get("end_reason") == "COMPLETED"
            and attempt.get("verification_status") == "VERIFIED"
            and attempt.get("outcome") == "PASS"
            for attempt in task["attempts"]
        )
        for task in tasks
    )
    every_verification_pass = all(
        isinstance(item, dict)
        and item.get("status") == "VERIFIED"
        and item.get("outcome") == "PASS"
        for item in verifications
    )
    control_tests, control_failures, control_errors, control_skipped = _control_counts(controls_junit)
    checks = {
        "passed_linux_preflight": preflight["status"] == "PASSED"
        and findings.get("platform") == "Linux"
        and findings.get("effective_uid") != 0
        and findings.get("source_read_only") is True
        and findings.get("network_default") == "disabled",
        "one_hundred_tasks_twice": audit["task_count"] == 100
        and audit["attempt_count"] == 200
        and verification["attempt_count"] == 200
        and len(verifications) == 200
        and audit["all_tasks_passed_twice"] is True
        and every_task_twice,
        "independent_verifier_all_pass": verification["pass_count"] == 200
        and verification["fail_count"] == 0
        and verification["unknown_count"] == 0
        and every_verification_pass,
        "at_least_thirty_five_positive_negative_controls": control_tests >= 35
        and control_failures == 0
        and control_errors == 0
        and control_skipped == 0,
        "migration_did_not_change_execution_semantics_or_environment": not changed_execution_paths,
    }
    if not all(checks.values()):
        raise ValueError("US2 checkpoint facts are inconsistent")
    receipt = {
        "checkpoint": "US2_EXECUTION",
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_level": "EXECUTION_VALIDATED",
        "counts": {
            "fixed_action_tasks": 100,
            "fixed_action_attempts": 200,
            "verified_pass": 200,
            "verified_fail": 0,
            "verified_unknown": 0,
            "positive_negative_control_cases": control_tests,
        },
        "checks": checks,
        "migration_impact_review": {
            "baseline_commit": migration_baseline_commit,
            "reviewed_paths": [
                "src/code_data_factory/interaction",
                "src/code_data_factory/verification",
                "configs/execution",
                "configs/quality/verifier.yaml",
            ],
            "changed_execution_paths": changed_execution_paths,
            "action": "existing T044 execution receipt remains applicable",
        },
        "asset_purpose": {
            "fixed_action_tasks": "validation_and_evaluation_only",
            "model_sampling": "not_run; reserved for T058",
            "external_training_release": "not_input; covered separately by T047",
        },
        "input_hashes": {
            "preflight": sha256_file(preflight_path),
            "verification_manifest": sha256_file(verification_manifest),
            "task_audit": sha256_file(task_audit_path),
            "verifier_controls_junit": sha256_file(controls_junit),
        },
        "limitations": [
            "This receipt does not prove model sampling, model training, or model improvement.",
            "This receipt is not training-data admission or external-data release evidence.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_json_bytes(receipt))
    return receipt
