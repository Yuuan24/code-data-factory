"""Frozen ToolTaskBench suite construction with development/test isolation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

import yaml

from code_data_factory.contracts.artifacts import canonical_json_bytes


class SuiteError(ValueError):
    """The frozen evaluation suite violates its split or coverage contract."""


Family = Literal["lookup", "calculation_conversion", "cross_document_comparison"]
FAMILIES: tuple[Family, ...] = ("lookup", "calculation_conversion", "cross_document_comparison")


@dataclass(frozen=True)
class EvaluationTask:
    task_id: str
    split: Literal["DEVELOPMENT", "TEST"]
    family: Family
    group_id: str
    template_family_id: str
    dependency_depth: int
    tool_signature: tuple[str, ...]
    unseen_combination: bool
    recovery_condition: bool
    instruction: str
    document_ids: tuple[str, ...]
    documents: tuple[tuple[str, str], ...]
    expected_value: str
    expected_unit: str

    def public_record(self) -> dict[str, object]:
        value = asdict(self)
        value.pop("expected_value")
        value.pop("expected_unit")
        return value


@dataclass(frozen=True)
class EvaluationSuite:
    suite_id: str
    version: str
    development: tuple[EvaluationTask, ...]
    test: tuple[EvaluationTask, ...]

    @property
    def families(self) -> tuple[Family, ...]:
        return FAMILIES


def _config(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    required = {
        "suite_id", "version", "development_task_count", "test_task_count", "source_template_group_count",
        "minimum_family_count", "minimum_unseen_test_count",
    }
    if not isinstance(value, dict) or required - value.keys():
        raise SuiteError("tool-task suite config is incomplete")
    if any(not isinstance(value[key], int) for key in required - {"suite_id", "version"}):
        raise SuiteError("tool-task suite counts must be integers")
    if not all(isinstance(value[key], str) and value[key] for key in ("suite_id", "version")):
        raise SuiteError("tool-task suite identity is invalid")
    return value


def _task(index: int, *, split: Literal["DEVELOPMENT", "TEST"], group_count: int, unseen: bool) -> EvaluationTask:
    family = FAMILIES[index % len(FAMILIES)]
    group_id = f"{split.lower()}-source-template-{index % group_count:03d}"
    value = str((index % 19) + 2)
    unit = ("cm", "s", "B")[index % 3]
    document_ids = (f"document-{index % group_count:03d}",) if family != "cross_document_comparison" else (f"document-{index % group_count:03d}", f"companion-{index % group_count:03d}")
    signature: tuple[str, ...] = (
        ("read_document", "calculate") if family == "lookup" else
        ("read_document", "convert") if family == "calculation_conversion" else
        ("search_documents", "read_document", "calculate")
    )
    if unseen:
        signature = ("search_documents", "read_document", "calculate", "convert")
    primary_id = f"document-{index % group_count:03d}"
    companion_id = f"companion-{index % group_count:03d}"
    documents = (
        ((primary_id, f"Recorded reading: {value} {unit}."),)
        if family == "lookup"
        else ((document_ids[0], f"Base reading: {int(value) - 1} {unit}. Add one {unit}."),)
        if family == "calculation_conversion"
        else (
            (primary_id, f"Candidate reading: {int(value) - 1} {unit}."),
            (companion_id, f"Adjustment: add 1 {unit}."),
        )
    )
    instruction = (
        f"Read {document_ids[0]} and return its recorded value with a document citation."
        if family == "lookup"
        else "Read the visible document(s), calculate the requested adjusted value, and cite every visible document."
    )
    return EvaluationTask(
        task_id=f"tooltask-{split.lower()}-{index:03d}", split=split, family=family, group_id=group_id,
        template_family_id=f"{family}-template-{index % 5}", dependency_depth=3 if unseen else (2 if family != "lookup" else 1),
        tool_signature=signature, unseen_combination=unseen, recovery_condition=index % 7 == 0,
        instruction=instruction, document_ids=document_ids, documents=documents,
        expected_value=value, expected_unit=unit,
    )


def _validate(tasks: tuple[EvaluationTask, ...], *, minimum_family_count: int, minimum_unseen: int = 0) -> None:
    if len(tasks) < 200:
        raise SuiteError("each frozen evaluation split requires at least 200 tasks")
    if any(sum(task.family == family for task in tasks) < minimum_family_count for family in FAMILIES):
        raise SuiteError("evaluation split lacks required family coverage")
    if sum(task.unseen_combination for task in tasks) < minimum_unseen:
        raise SuiteError("test split lacks required unseen combinations")


def build_tool_task_suite(config_path: Path, *, output_dir: Path) -> Path:
    config = _config(config_path)
    dev_count, test_count, groups = (cast(int, config[key]) for key in ("development_task_count", "test_task_count", "source_template_group_count"))
    if groups < 20:
        raise SuiteError("test requires at least 20 independent source-template groups")
    development = tuple(_task(index, split="DEVELOPMENT", group_count=groups, unseen=False) for index in range(dev_count))
    test = tuple(_task(index, split="TEST", group_count=groups, unseen=index < cast(int, config["minimum_unseen_test_count"])) for index in range(test_count))
    _validate(development, minimum_family_count=cast(int, config["minimum_family_count"]))
    _validate(test, minimum_family_count=cast(int, config["minimum_family_count"]), minimum_unseen=cast(int, config["minimum_unseen_test_count"]))
    if {task.group_id for task in development} & {task.group_id for task in test}:
        raise SuiteError("source-template groups cannot cross evaluation splits")
    output_dir.mkdir(parents=True, exist_ok=True)
    private = output_dir / "private-references"
    private.mkdir(exist_ok=True)
    for task in (*development, *test):
        (private / f"{task.task_id}.json").write_bytes(canonical_json_bytes({"value": task.expected_value, "unit": task.expected_unit, "evidence": list(task.document_ids)}))
    manifest = {"suite_id": config["suite_id"], "version": config["version"], "development": [task.public_record() for task in development], "test": [task.public_record() for task in test], "private_reference_dir": "private-references", "sft_ingress_count": 0}
    path = output_dir / "suite_manifest.json"
    path.write_bytes(canonical_json_bytes(manifest))
    return path


def load_suite(path: Path) -> EvaluationSuite:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("suite_id"), str) or not isinstance(value.get("version"), str):
        raise SuiteError("suite manifest is invalid")
    private = path.parent / str(value.get("private_reference_dir", ""))
    def load(split: Literal["DEVELOPMENT", "TEST"], records: object) -> tuple[EvaluationTask, ...]:
        if not isinstance(records, list):
            raise SuiteError("suite split is invalid")
        items: list[EvaluationTask] = []
        for record in records:
            if not isinstance(record, dict) or any(key not in record for key in ("task_id", "family", "group_id", "template_family_id", "dependency_depth", "tool_signature", "unseen_combination", "recovery_condition", "instruction", "document_ids", "documents")):
                raise SuiteError("suite task is incomplete")
            if record["family"] not in FAMILIES:
                raise SuiteError("suite task family is invalid")
            ref = json.loads((private / f"{record['task_id']}.json").read_text(encoding="utf-8"))
            documents = record["documents"]
            if not isinstance(documents, list) or any(not isinstance(item, list) or len(item) != 2 or not all(isinstance(part, str) for part in item) for item in documents):
                raise SuiteError("suite task documents are invalid")
            items.append(EvaluationTask(task_id=str(record["task_id"]), split=split, family=cast(Family, record["family"]), group_id=str(record["group_id"]), template_family_id=str(record["template_family_id"]), dependency_depth=int(record["dependency_depth"]), tool_signature=tuple(str(item) for item in record["tool_signature"]), unseen_combination=bool(record["unseen_combination"]), recovery_condition=bool(record["recovery_condition"]), instruction=str(record["instruction"]), document_ids=tuple(str(item) for item in record["document_ids"]), documents=tuple((str(item[0]), str(item[1])) for item in documents), expected_value=str(ref["value"]), expected_unit=str(ref["unit"])))
        return tuple(items)
    suite = EvaluationSuite(str(value["suite_id"]), str(value["version"]), load("DEVELOPMENT", value.get("development")), load("TEST", value.get("test")))
    _validate(suite.development, minimum_family_count=40)
    _validate(suite.test, minimum_family_count=40, minimum_unseen=50)
    if {task.group_id for task in suite.development} & {task.group_id for task in suite.test}:
        raise SuiteError("source-template groups cannot cross evaluation splits")
    return suite
