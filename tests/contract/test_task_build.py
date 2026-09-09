from __future__ import annotations

from pathlib import Path

from code_data_factory.tasks.build import build_pilot_tasks
from code_data_factory.tasks.splits import SplitRegistry


def test_task_builder_creates_one_hundred_non_executable_drafts_with_preassigned_groups(
    tmp_path: Path,
) -> None:
    registry = SplitRegistry(policy_version="split-v1")
    result = build_pilot_tasks(
        Path("configs/tasks/pilot.yaml"),
        output_dir=tmp_path,
        producer_run_id="test-build",
        split_registry=registry,
    )

    assert len(result.tasks) == 100
    assert {task.task_family for task in result.tasks} == {
        "lookup",
        "calculation_conversion",
        "cross_document_comparison",
    }
    assert all(task.status.value == "DRAFT" for task in result.tasks)
    assert all(task.initial_state_ref is None for task in result.tasks)
    assert all(task.split_group_id for task in result.tasks)
    assert len({item["value"] for item in result.expected_results.values()}) == 100
    assert all(
        len(task.source_record_ids) == 2
        for task in result.tasks
        if task.task_family == "cross_document_comparison"
    )
    assert (tmp_path / "task_manifest.json").is_file()
    assert (tmp_path / "private_expected_results.json").is_file()
