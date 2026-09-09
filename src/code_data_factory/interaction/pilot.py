"""Fixed-action pilot execution used to validate tasks before any model collection."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from uuid import uuid4

import yaml

from code_data_factory.contracts.artifacts import canonical_json_bytes
from code_data_factory.contracts.tasks import TaskPackage

from .environment import EnvironmentPreflight
from .events import EventLedger
from .tools import RestrictedTools


class PilotExecutionError(RuntimeError):
    pass


def load_facts(config_path: Path) -> dict[str, dict[str, str]]:
    """Load frozen visible document facts; private expected-result assets are never consulted."""
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, Mapping) or not isinstance(config.get("facts"), list):
        raise ValueError("pilot facts config must contain a facts list")
    facts: dict[str, dict[str, str]] = {}
    for item in config["facts"]:
        if not isinstance(item, Mapping):
            raise ValueError("every pilot fact must be a mapping")
        required = ("document_id", "value", "unit")
        if any(field not in item for field in required):
            raise ValueError("pilot fact misses a required document/value/unit field")
        document_id = str(item["document_id"])
        if document_id in facts:
            raise ValueError("pilot document ids must be unique")
        facts[document_id] = {
            "value": str(item["value"]),
            "unit": str(item["unit"]),
            "content": f"Frozen fact: one declared base quantity equals {item['value']} {item['unit']}.",
        }
        companion_id = item.get("companion_document_id")
        if companion_id is not None:
            if not isinstance(companion_id, str) or companion_id in facts:
                raise ValueError("pilot companion document ids must be unique strings")
            facts[companion_id] = {
                "value": "0",
                "unit": str(item["unit"]),
                "content": "Frozen companion fact: the declared comparison value is 0.",
            }
    return facts


def _task_multiplier(task_id: str) -> str:
    match = re.fullmatch(r"pilot-(\d{3})", task_id)
    if match is None or int(match.group(1)) < 1:
        raise PilotExecutionError("task_id must use the frozen pilot-NNN form")
    return str(int(match.group(1)))


def _fixed_attempt(
    task: TaskPackage,
    *,
    facts: Mapping[str, Mapping[str, str]],
    output_dir: Path,
    task_assets_root: Path,
) -> dict[str, object]:
    resources = json.loads((task_assets_root / task.initial_resources_ref.uri).read_text(encoding="utf-8"))
    document_ids = resources.get("document_ids") if isinstance(resources, dict) else None
    if not isinstance(document_ids, list) or not document_ids or not all(isinstance(item, str) for item in document_ids):
        raise PilotExecutionError("task must declare visible document ids")
    document_id = document_ids[0]
    if any(document_id not in facts for document_id in document_ids):
        raise PilotExecutionError("task references a document not present in the frozen fact bundle")
    tools = RestrictedTools({key: value["content"] for key, value in facts.items()})
    attempt_id = str(uuid4())
    ledger = EventLedger(output_dir / attempt_id, attempt_id=attempt_id, task_id=task.task_id)
    for resource_id in document_ids:
        read_call = ledger.record_tool_call("read_document", {"document_id": resource_id})
        document = tools.read_document(resource_id)
        ledger.record_tool_result(read_call, {"document_id": resource_id, "content": document})
    multiplier = _task_multiplier(task.task_id)
    fact = facts[document_id]
    if task.task_family == "calculation_conversion":
        base_units = {"cm": "m", "s": "min", "B": "KiB"}
        base_unit = base_units.get(fact["unit"])
        if base_unit is None:
            raise PilotExecutionError("no fixed conversion path exists for the document unit")
        call_id = ledger.record_tool_call(
            "convert", {"value": multiplier, "from_unit": base_unit, "to_unit": fact["unit"]}
        )
        value = tools.convert(multiplier, base_unit, fact["unit"])
        ledger.record_tool_result(call_id, {"value": value, "unit": fact["unit"]})
    else:
        call_id = ledger.record_tool_call(
            "calculate", {"operation": "MULTIPLY", "operands": [multiplier, fact["value"]]}
        )
        value = tools.calculate("MULTIPLY", [multiplier, fact["value"]])
        ledger.record_tool_result(call_id, {"value": value, "unit": fact["unit"]})
        if task.task_family == "cross_document_comparison":
            companion = facts[document_ids[1]]
            call_id = ledger.record_tool_call(
                "calculate", {"operation": "SUBTRACT", "operands": [value, companion["value"]]}
            )
            value = tools.calculate("SUBTRACT", [value, companion["value"]])
            ledger.record_tool_result(call_id, {"value": value, "unit": fact["unit"]})
    actual = {"value": value, "unit": fact["unit"], "evidence": document_ids}
    ledger.seal("COMPLETED", final_output=actual)
    return {
        "attempt_id": attempt_id,
        "task_id": task.task_id,
        "actor_kind": "SCRIPTED_FIXED_ACTION",
        "end_reason": "COMPLETED",
        "manifest_ref": f"{attempt_id}/manifest.json",
        "actual": actual,
        "event_count": len(ledger.events),
    }


def execute_fixed_actions(
    tasks: Sequence[TaskPackage],
    *,
    facts: Mapping[str, Mapping[str, str]],
    output_dir: Path,
    task_assets_root: Path,
    preflight: EnvironmentPreflight,
) -> dict[str, object]:
    """Execute each supplied task twice only after an already-passed environment preflight."""
    if preflight.status != "PASSED":
        raise PilotExecutionError("fixed actions require a passed Linux container preflight")
    if not tasks:
        raise PilotExecutionError("fixed actions require at least one task")
    task_ids = [task.task_id for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise PilotExecutionError("fixed actions reject duplicate task identities")
    attempts = [
        _fixed_attempt(task, facts=facts, output_dir=output_dir, task_assets_root=task_assets_root)
        for task in tasks
        for _ in range(2)
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "kind": "fixed-action-pilot",
        "preflight": preflight.findings,
        "task_count": len(tasks),
        "attempt_count": len(attempts),
        "attempts": attempts,
    }
    (output_dir / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    return manifest
