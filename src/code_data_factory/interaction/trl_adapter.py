"""Thin TRL environment-factory adapter over the project's four bounded tools."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml

from .checkpoints import SessionWorkspace
from .tools import RestrictedTools


class TrlAdapterError(RuntimeError):
    """The selected TRL interface cannot consume the bounded tool environment."""


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class ToolTaskEnvironment:
    """One independent task state for TRL's experimental ``environment_factory`` hook."""

    def __init__(self, *, documents: Mapping[str, str], workspace_root: Path) -> None:
        self._documents = dict(documents)
        self._tools = RestrictedTools(self._documents)
        self._workspace = SessionWorkspace(workspace_root, initial_documents=self._documents)
        self.calls: list[dict[str, object]] = []

    def reset(self, **_: object) -> str:
        """Reset this independent task environment and expose no hidden verifier state."""
        self.calls.clear()
        return "\nUse only the supplied tools and cite the visible document identifier."

    def search_documents(self, query: str) -> list[str]:
        """Search the task's visible read-only documents for an alphanumeric query."""
        result = self._tools.search_documents(query)
        self.calls.append({"tool": "search_documents", "arguments": {"query": query}, "result": result})
        return result

    def read_document(self, document_id: str) -> str:
        """Read one visible document by its task-local identifier."""
        result = self._workspace.read_document(document_id)
        self.calls.append({"tool": "read_document", "arguments": {"document_id": document_id}, "result": result})
        return result

    def calculate(self, operation: str, operands: list[str]) -> str:
        """Apply ADD, SUBTRACT, MULTIPLY, or DIVIDE to decimal-literal operands."""
        result = self._tools.calculate(operation, operands)
        self.calls.append({"tool": "calculate", "arguments": {"operation": operation, "operands": operands}, "result": result})
        return result

    def convert(self, value: str, from_unit: str, to_unit: str) -> str:
        """Convert one decimal value between compatible units."""
        result = self._tools.convert(value, from_unit, to_unit)
        self.calls.append(
            {
                "tool": "convert",
                "arguments": {"value": value, "from_unit": from_unit, "to_unit": to_unit},
                "result": result,
            }
        )
        return result


def build_environment_factory(
    *, documents: Mapping[str, str], workspace_root: Path
) -> tuple[Callable[[], ToolTaskEnvironment], list[ToolTaskEnvironment]]:
    """Return the exact zero-argument factory required by ``GRPOTrainer`` and retain instances for receipts."""

    environments: list[ToolTaskEnvironment] = []

    def factory() -> ToolTaskEnvironment:
        environment = ToolTaskEnvironment(documents=documents, workspace_root=workspace_root / f"rollout-{len(environments)}")
        environments.append(environment)
        return environment

    return factory, environments


def assert_trl_environment_factory_supported() -> None:
    """Fail before sampling if the installed trainer no longer exposes the selected integration point."""

    try:
        from inspect import signature

        from trl import GRPOTrainer  # type: ignore[attr-defined]
    except ImportError as error:
        raise TrlAdapterError("TRL GRPOTrainer is required for compatibility sampling") from error
    if "environment_factory" not in signature(GRPOTrainer).parameters:
        raise TrlAdapterError("installed GRPOTrainer no longer supports environment_factory")


def run_contract_check(*, profile_path: Path, output_dir: Path) -> dict[str, object]:
    """Exercise the same bounded tool semantics through the trainer-entry environment."""

    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    if not isinstance(profile, dict) or profile.get("profile_version") != "trl-tools-v1":
        raise TrlAdapterError("TRL tools profile must freeze profile_version trl-tools-v1")
    trainer = profile.get("trainer")
    tools = profile.get("tools")
    if not isinstance(trainer, dict) or trainer.get("kind") != "TRL_GRPO_TRAINER" or trainer.get("interface") != "environment_factory":
        raise TrlAdapterError("TRL tools profile must select the GRPO environment_factory interface")
    if tools != ["search_documents", "read_document", "calculate", "convert"]:
        raise TrlAdapterError("TRL tools profile must expose exactly the four bounded project tools")
    assert_trl_environment_factory_supported()
    factory, environments = build_environment_factory(
        documents={"units": "A metre contains 100 centimetres."}, workspace_root=output_dir / "workspaces"
    )
    environment = factory()
    environment.reset()
    observed = {
        "search": environment.search_documents("metre"),
        "document": environment.read_document("units"),
        "calculation": environment.calculate("MULTIPLY", ["2", "3"]),
        "conversion": environment.convert("1", "m", "cm"),
    }
    receipt: dict[str, object] = {
        "kind": "trl-environment-factory-contract",
        "profile_version": profile["profile_version"],
        "runner_kind": trainer["kind"],
        "environment_instances": len(environments),
        "tool_calls": len(environment.calls),
        "observed": observed,
        "optimizer_updates_allowed": trainer.get("optimizer_updates_allowed"),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    return receipt


def _load_case(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TrlAdapterError("long-horizon fixture cannot be read") from error
    required = {"case_id", "step_count", "document_id", "document_content", "rewrite_at", "truncate_at"}
    if not isinstance(value, dict) or required - value.keys():
        raise TrlAdapterError("long-horizon fixture lacks required fields")
    if value["step_count"] not in {32, 128} or not all(isinstance(value[key], int) for key in ("step_count", "rewrite_at", "truncate_at")):
        raise TrlAdapterError("long-horizon fixture must declare a 32- or 128-step case")
    if not isinstance(value["document_id"], str) or not isinstance(value["document_content"], str):
        raise TrlAdapterError("long-horizon fixture document is invalid")
    return value


def run_fixed_long_horizon_case(case_path: Path, *, config_path: Path, output_dir: Path | None = None) -> dict[str, object]:
    """Exercise deterministic dependency, context rewrite, truncation, and controlled-restore semantics."""

    case = _load_case(case_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("profile_version") != "long-horizon-v1":
        raise TrlAdapterError("long-horizon config must freeze profile_version long-horizon-v1")
    step_count = case["step_count"]
    assert isinstance(step_count, int)
    workspace_root = (output_dir or case_path.parent / ".runtime") / str(case["case_id"])
    workspace = SessionWorkspace(
        workspace_root,
        initial_documents={str(case["document_id"]): str(case["document_content"])},
    )
    contexts: list[dict[str, object]] = []
    values: list[int] = []
    rewrite_count = 0
    truncation_count = 0
    for step in range(step_count):
        previous = values[-1] if values else 0
        value = previous + 1
        values.append(value)
        workspace.write_session_value(f"value-{step}", str(value))
        visible: list[dict[str, object]] = [
            {"role": "user", "content": f"step={step}; previous_value={previous}"},
            {"role": "tool", "content": f"value={value}", "depends_on_step": step - 1 if step else None},
        ]
        if step == case["truncate_at"]:
            visible.insert(1, {"role": "tool", "content_ref": f"document:{case['document_id']}", "truncated": True})
            truncation_count += 1
        if step == case["rewrite_at"]:
            before = list(contexts)
            contexts = [{"role": "system", "content": f"summary: values 1..{value}; retained_step={step}"}]
            visible.insert(0, {"role": "system", "rewrite_from": _digest(before), "rewrite_to": _digest(contexts)})
            rewrite_count += 1
        contexts.extend(visible)
    snapshot = workspace.snapshot(attempt_id=f"{case['case_id']}-attempt", event_seq=step_count - 1)
    restored = workspace.restore(
        snapshot,
        parent_attempt_id=f"{case['case_id']}-attempt",
        branch_event_id=f"{case['case_id']}-event-{step_count - 1}",
    )
    receipt: dict[str, object] = {
        "kind": "fixed-long-horizon-case",
        "case_id": case["case_id"],
        "step_count": step_count,
        "dependency_edges": step_count - 1,
        "context_rewrite_count": rewrite_count,
        "truncation_count": truncation_count,
        "visible_context_hash": _digest(contexts),
        "final_value": values[-1],
        "controlled_restore": restored,
    }
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{case['case_id']}.json").write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    return receipt
