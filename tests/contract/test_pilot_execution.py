from __future__ import annotations

from pathlib import Path

import pytest

from code_data_factory.interaction.environment import EnvironmentPreflight
from code_data_factory.interaction.pilot import execute_fixed_actions, load_facts
from code_data_factory.tasks.build import build_pilot_tasks
from code_data_factory.tasks.splits import SplitRegistry
from code_data_factory.verification.pilot import verify_pilot_attempts


def test_fixed_action_pilot_rejects_an_unqualified_environment(tmp_path: Path) -> None:
    build = build_pilot_tasks(
        Path("configs/tasks/pilot.yaml"),
        output_dir=tmp_path / "tasks",
        producer_run_id="test-run",
        split_registry=SplitRegistry(policy_version="split-v1"),
    )
    with pytest.raises(RuntimeError, match="preflight"):
        execute_fixed_actions(
            build.tasks,
            facts=load_facts(Path("configs/tasks/pilot.yaml")),
            output_dir=tmp_path / "attempts",
            task_assets_root=tmp_path / "tasks",
            preflight=EnvironmentPreflight("FAILED", {}),
        )


def test_fixed_action_pilot_records_two_new_attempts_per_task_without_private_truth(tmp_path: Path) -> None:
    build = build_pilot_tasks(
        Path("configs/tasks/pilot.yaml"),
        output_dir=tmp_path / "tasks",
        producer_run_id="test-run",
        split_registry=SplitRegistry(policy_version="split-v1"),
    )
    selected = [build.tasks[0], build.tasks[67]]
    result = execute_fixed_actions(
        selected,
        facts=load_facts(Path("configs/tasks/pilot.yaml")),
        output_dir=tmp_path / "attempts",
        task_assets_root=tmp_path / "tasks",
        preflight=EnvironmentPreflight("PASSED", {"test_double": True}),
    )
    assert len(result["attempts"]) == 4
    assert {attempt["task_id"] for attempt in result["attempts"]} == {"pilot-001", "pilot-068"}
    assert all(attempt["actor_kind"] == "SCRIPTED_FIXED_ACTION" for attempt in result["attempts"])
    assert all(attempt["end_reason"] == "COMPLETED" for attempt in result["attempts"])
    assert not any("expected" in str(attempt) for attempt in result["attempts"])
    verifications = verify_pilot_attempts(
        tasks=selected,
        task_assets_root=tmp_path / "tasks",
        attempts_manifest=tmp_path / "attempts" / "manifest.json",
        output_dir=tmp_path / "verifications",
        verifier_version="fixed-value-v2",
    )
    assert verifications["pass_count"] == 4
