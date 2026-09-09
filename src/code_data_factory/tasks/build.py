"""Deterministic construction of non-executable pilot task drafts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes
from code_data_factory.contracts.tasks import (
    AccessScope,
    ArtifactRef,
    Capabilities,
    TaskPackage,
    TaskStatus,
    UsageScope,
)
from code_data_factory.tasks.splits import SplitRegistry


@dataclass(frozen=True)
class PilotTaskBuild:
    tasks: list[TaskPackage]
    expected_results: dict[str, dict[str, Any]]


def _ref(name: str, value: Any, scope: AccessScope, producer_run_id: str) -> ArtifactRef:
    payload = canonical_json_bytes(value)
    return ArtifactRef(
        artifact_id=name,
        uri=f"data/pilot/{name}.json",
        sha256=sha256_bytes(payload),
        byte_size=len(payload),
        media_type="application/json",
        producer_run_id=producer_run_id,
        access_scope=scope,
    )


def build_pilot_tasks(
    config_path: Path,
    *,
    output_dir: Path,
    producer_run_id: str,
    split_registry: SplitRegistry,
) -> PilotTaskBuild:
    """Build exactly 100 drafts across the frozen three families without execution claims."""

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("facts"), list):
        raise ValueError("pilot config needs a facts list")
    facts = [fact for fact in config["facts"] if isinstance(fact, dict)]
    if not facts:
        raise ValueError("pilot config needs at least one fact")
    family_counts = {
        "lookup": 34,
        "calculation_conversion": 33,
        "cross_document_comparison": 33,
    }
    preassign_input: list[dict[str, Any]] = []
    specs: list[tuple[str, int, dict[str, Any]]] = []
    index = 0
    for family, count in family_counts.items():
        for occurrence in range(count):
            fact = facts[index % len(facts)]
            task_id = f"pilot-{index + 1:03d}"
            template_root = f"{family}-template-{occurrence % 5}"
            source_groups = [str(fact["source_group_id"])]
            if family == "cross_document_comparison":
                source_groups.append(str(fact["companion_source_group_id"]))
            preassign_input.append(
                {
                    "task_id": task_id,
                    "source_groups": source_groups,
                    "template_root": template_root,
                    "related_task_ids": [],
                }
            )
            specs.append((task_id, index, {**fact, "family": family, "template_root": template_root}))
            index += 1
    assigned = split_registry.assign(preassign_input)
    assignments = {item.task_id: item for item in assigned.assignments}
    tasks: list[TaskPackage] = []
    expected: dict[str, dict[str, Any]] = {}
    for task_id, index, fact in specs:
        family = str(fact["family"])
        input_value = index + 1
        expected_value = int(fact["value"]) * input_value
        tools = {
            "lookup": ["search_documents", "read_document", "calculate"],
            "calculation_conversion": ["read_document", "calculate", "convert"],
            "cross_document_comparison": ["search_documents", "read_document", "calculate"],
        }[family]
        instruction = {
            "lookup": (
                f"Read {fact['document_id']} and calculate {input_value} times "
                f"{fact['label']}."
            ),
            "calculation_conversion": (
                f"Read {fact['document_id']}, then convert {input_value} declared "
                f"base quantities into {fact['unit']}."
            ),
            "cross_document_comparison": (
                f"Read {fact['document_id']} and {fact['companion_document_id']}, then "
                f"calculate the difference between {input_value} times {fact['label']} "
                "and the companion's zero value."
            ),
        }[family]
        source_record_ids = [str(fact["source_record_id"])]
        source_group_ids = [str(fact["source_group_id"])]
        document_ids = [str(fact["document_id"])]
        if family == "cross_document_comparison":
            source_record_ids.append(str(fact["companion_source_record_id"]))
            source_group_ids.append(str(fact["companion_source_group_id"]))
            document_ids.append(str(fact["companion_document_id"]))
        assignment = assignments[task_id]
        task = TaskPackage(
            task_id=task_id,
            task_revision="pilot-v1",
            source_record_ids=source_record_ids,
            instruction_ref=_ref(f"{task_id}-instruction", {"instruction": instruction}, AccessScope.MODEL_VISIBLE, producer_run_id),
            initial_resources_ref=_ref(f"{task_id}-resources", {"document_ids": document_ids}, AccessScope.MODEL_VISIBLE, producer_run_id),
            tool_bundle_ref=_ref(f"{task_id}-tools", {"tools": tools}, AccessScope.MODEL_VISIBLE, producer_run_id),
            environment_ref=_ref(f"{task_id}-environment", {"status": "not_executed"}, AccessScope.INTERNAL, producer_run_id),
            verifier_spec_ref=_ref(f"{task_id}-verifier", {"kind": "fixed_value"}, AccessScope.VERIFIER_PRIVATE, producer_run_id),
            expected_result_ref=_ref(f"{task_id}-expected", {"value": expected_value, "unit": fact["unit"]}, AccessScope.VERIFIER_PRIVATE, producer_run_id),
            task_family=family,
            template_family_id=str(fact["template_root"]),
            source_group_ids=source_group_ids,
            derivation_root_ids=[f"{fact['document_id']}:{input_value}"],
            usage_scope=UsageScope(assignment.scope),
            split_group_id=assignment.split_group_id,
            split_policy_version=split_registry.policy_version,
            dependency_depth=1 if family == "lookup" else 2,
            tool_set=tools,
            interaction_budget_ref=_ref(f"{task_id}-budget", {"status": "not_executed"}, AccessScope.INTERNAL, producer_run_id),
            capabilities=Capabilities(),
            status=TaskStatus.DRAFT,
        )
        tasks.append(task)
        expected[task_id] = {
            "value": expected_value,
            "unit": fact["unit"],
            "family": family,
            "input_value": input_value,
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "task_manifest.json").write_bytes(
        canonical_json_bytes({"tasks": [task.model_dump(mode="json") for task in tasks]})
    )
    (output_dir / "private_expected_results.json").write_bytes(canonical_json_bytes(expected))
    return PilotTaskBuild(tasks=tasks, expected_results=expected)
