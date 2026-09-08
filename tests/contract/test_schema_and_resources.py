from __future__ import annotations

import json
from pathlib import Path

from code_data_factory.contracts.resources import ResourceKind, ResourcePolicy
from code_data_factory.contracts.schema_export import export_schemas


def test_arrow_schemas_export_under_contract_major(tmp_path: Path) -> None:
    paths = export_schemas(tmp_path)
    assert {path.stem for path in paths} == {
        "attempts",
        "contexts",
        "events",
        "rewards",
        "tasks",
        "verifications",
    }
    task_schema = json.loads((tmp_path / "2.0.0" / "tasks.json").read_text(encoding="utf-8"))
    assert "task_id" in task_schema["schema"]


def test_committed_arrow_schemas_match_the_current_contract(tmp_path: Path) -> None:
    export_schemas(tmp_path)
    committed = Path("schemas/2.0.0")
    generated = tmp_path / "2.0.0"
    assert sorted(path.name for path in committed.glob("*.json")) == sorted(
        path.name for path in generated.glob("*.json")
    )
    for generated_path in generated.glob("*.json"):
        assert generated_path.read_bytes() == (committed / generated_path.name).read_bytes()


def test_external_run_is_blocked_without_quote_and_authorization() -> None:
    policy = ResourcePolicy(policy_version="1")
    allowed, reason = policy.external_run_allowed({ResourceKind.GPU})
    assert not allowed
    assert reason == "missing quote for GPU"
