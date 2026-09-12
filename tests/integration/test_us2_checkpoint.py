from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_data_factory.checkpoints.us2 import run_us2_checkpoint


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _valid_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    preflight = tmp_path / "preflight.json"
    verification = tmp_path / "verification.json"
    audit = tmp_path / "audit.json"
    controls = tmp_path / "controls.xml"
    _write(
        preflight,
        {
            "status": "PASSED",
            "findings": {
                "platform": "Linux",
                "effective_uid": 1000,
                "source_read_only": True,
                "network_default": "disabled",
            },
        },
    )
    _write(
        verification,
        {
            "attempt_count": 200,
            "pass_count": 200,
            "fail_count": 0,
            "unknown_count": 0,
            "verifications": [{"status": "VERIFIED", "outcome": "PASS"}] * 200,
        },
    )
    _write(
        audit,
        {
            "task_count": 100,
            "attempt_count": 200,
            "all_tasks_passed_twice": True,
            "tasks": [
                {
                    "attempts": [
                        {"end_reason": "COMPLETED", "verification_status": "VERIFIED", "outcome": "PASS"},
                        {"end_reason": "COMPLETED", "verification_status": "VERIFIED", "outcome": "PASS"},
                    ]
                }
            ]
            * 100,
        },
    )
    controls.write_text('<testsuite tests="37" failures="0" errors="0" skipped="0"/>', encoding="utf-8")
    return preflight, verification, audit, controls


def test_us2_checkpoint_binds_fixed_actions_controls_and_unaffected_migration(tmp_path: Path) -> None:
    preflight, verification, audit, controls = _valid_inputs(tmp_path)

    receipt = run_us2_checkpoint(
        output_path=tmp_path / "us2.json",
        preflight_path=preflight,
        verification_manifest=verification,
        task_audit_path=audit,
        controls_junit=controls,
        migration_baseline_commit="baseline",
        changed_execution_paths=[],
    )

    assert receipt["evidence_level"] == "EXECUTION_VALIDATED"
    assert receipt["counts"]["positive_negative_control_cases"] == 37
    assert all(receipt["checks"].values())


def test_us2_checkpoint_requires_a_reexecution_if_migration_changed_runtime_paths(tmp_path: Path) -> None:
    preflight, verification, audit, controls = _valid_inputs(tmp_path)

    with pytest.raises(ValueError, match="facts are inconsistent"):
        run_us2_checkpoint(
            output_path=tmp_path / "us2.json",
            preflight_path=preflight,
            verification_manifest=verification,
            task_audit_path=audit,
            controls_junit=controls,
            migration_baseline_commit="baseline",
            changed_execution_paths=["src/code_data_factory/interaction/pilot.py"],
        )
