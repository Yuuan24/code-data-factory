from __future__ import annotations

from pathlib import Path

import pytest

from code_data_factory.interaction.checkpoints import CheckpointError, SessionWorkspace
from code_data_factory.interaction.trl_adapter import (
    assert_trl_environment_factory_supported,
    build_environment_factory,
    run_fixed_long_horizon_case,
)


def test_controlled_session_checkpoint_restores_state_and_links_a_new_attempt(tmp_path: Path) -> None:
    workspace = SessionWorkspace(tmp_path / "workspace", initial_documents={"doc-1": "frozen fact"})
    workspace.write_session_value("current", "first")
    snapshot = workspace.snapshot(attempt_id="attempt-parent", event_seq=3)
    workspace.write_session_value("current", "changed")

    restored = workspace.restore(snapshot, parent_attempt_id="attempt-parent", branch_event_id="event-3")

    assert restored["attempt_id"] != "attempt-parent"
    assert restored["parent_attempt_id"] == "attempt-parent"
    assert workspace.read_session_value("current") == "first"
    with pytest.raises(CheckpointError, match="read-only"):
        workspace.write_document("doc-1", "mutate frozen input")


@pytest.mark.parametrize("fixture_name", ["steps-32.json", "steps-128.json"])
def test_long_horizon_cases_preserve_dependencies_visible_context_and_rewrites(
    fixture_name: str, tmp_path: Path
) -> None:
    receipt = run_fixed_long_horizon_case(
        Path("tests/fixtures/long_horizon") / fixture_name,
        config_path=Path("configs/execution/long-horizon.yaml"),
        output_dir=tmp_path,
    )

    assert receipt["step_count"] in {32, 128}
    assert receipt["dependency_edges"] >= 1
    assert receipt["visible_context_hash"]
    assert receipt["context_rewrite_count"] == 1


def test_uncontrolled_environment_fails_closed_for_restore() -> None:
    with pytest.raises(CheckpointError, match="UNSUPPORTED_CAPABILITY"):
        SessionWorkspace.unsupported_restore("external-browser")


def test_trl_environment_factory_reuses_the_four_bounded_tools(tmp_path: Path) -> None:
    assert_trl_environment_factory_supported()
    factory, environments = build_environment_factory(
        documents={"units": "A metre contains 100 centimetres."},
        workspace_root=tmp_path / "trl",
    )

    environment = factory()
    assert environment.reset().startswith("\nUse only")
    assert environment.search_documents("metre") == ["units"]
    assert environment.read_document("units").startswith("A metre")
    assert environment.calculate("MULTIPLY", ["2", "3"]) == "6"
    assert environment.convert("1", "m", "cm") == "100"
    assert environments == [environment]
    assert [call["tool"] for call in environment.calls] == [
        "search_documents",
        "read_document",
        "calculate",
        "convert",
    ]
