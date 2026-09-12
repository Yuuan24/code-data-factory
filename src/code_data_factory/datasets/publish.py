"""Local immutable dataset publication with evidence-level gates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from code_data_factory.contracts.artifacts import canonical_json_bytes, logical_content_hash
from code_data_factory.datasets.quality_reports import quality_report
from code_data_factory.processing.quality import EXTERNAL_PUBLICATION_REVIEW_CHECKS


class PublicationGateError(ValueError):
    """Publication violates a membership, evidence, or immutability invariant."""


@dataclass(frozen=True)
class DatasetPublication:
    dataset_id: str
    status: str
    logical_content_hash: str
    path: Path


def _validate_external_members(members: list[dict[str, Any]]) -> None:
    for member in members:
        required = (
            "demonstration_id",
            "source_record_id",
            "source_record_ids",
            "usage_scope",
            "eligibility_decision_id",
            "eligibility_action",
            "upstream_message_refs",
            "source_origin",
            "replay_capability",
            "review_checks",
        )
        if any(name not in member for name in required):
            raise PublicationGateError("external member is missing admission or lineage fields")
        if member["usage_scope"] != "TRAIN":
            raise PublicationGateError("external training members must have TRAIN usage scope")
        if member["eligibility_action"] != "ACCEPT":
            raise PublicationGateError("external member requires an accepted eligibility decision")
        if member["source_origin"] not in {"PUBLIC_ORIGINAL", "DERIVED"}:
            raise PublicationGateError("project sampling or model generation cannot enter external training")
        if not isinstance(member["source_record_ids"], list) or not member["source_record_ids"]:
            raise PublicationGateError("external member must retain source record lineage")
        if not isinstance(member["upstream_message_refs"], list) or not member["upstream_message_refs"]:
            raise PublicationGateError("external member must retain upstream message lineage")
        if not isinstance(member["eligibility_decision_id"], str) or not member["eligibility_decision_id"]:
            raise PublicationGateError("external member must retain an eligibility decision")
        if not isinstance(member["review_checks"], list) or not EXTERNAL_PUBLICATION_REVIEW_CHECKS <= set(member["review_checks"]):
            raise PublicationGateError("external member lacks required source, split, or sensitive review")


def _validate_members(members: list[dict[str, Any]]) -> str:
    if not members:
        raise PublicationGateError("dataset publication requires at least one member")
    external = ["demonstration_id" in member for member in members]
    if any(external):
        if not all(external):
            raise PublicationGateError("cannot mix external demonstrations with execution attempts")
        _validate_external_members(members)
        return "EXTERNAL_DEMONSTRATION"
    for member in members:
        required = (
            "task_id",
            "attempt_id",
            "source_record_ids",
            "usage_scope",
            "verification_status",
            "outcome",
            "decision",
            "quality_decision_id",
        )
        if any(name not in member for name in required):
            raise PublicationGateError("member is missing required lineage or decision fields")
        if not isinstance(member["source_record_ids"], list) or not member["source_record_ids"]:
            raise PublicationGateError("member must retain at least one source record reference")
        if not isinstance(member["quality_decision_id"], str) or not member["quality_decision_id"]:
            raise PublicationGateError("member must retain an immutable quality decision reference")
        if member["decision"] != "ACCEPT" or member["verification_status"] != "VERIFIED" or member["outcome"] != "PASS":
            raise PublicationGateError("only independently verified accepted members may publish")
        if member["usage_scope"] == "TRAIN":
            raise PublicationGateError("training publication requires execution-validated evidence from T047")
    return "EXECUTION_ATTEMPT"


def publish_dataset(
    *,
    dataset_id: str,
    members: list[dict[str, Any]],
    output_dir: Path,
    input_manifest_hash: str,
    rule_version: str,
) -> DatasetPublication:
    """Publish a software-test-only immutable release; real training is explicitly gated."""

    member_kind = _validate_members(members)
    primary_key = "demonstration_id" if member_kind == "EXTERNAL_DEMONSTRATION" else "attempt_id"
    if len({item[primary_key] for item in members}) != len(members):
        raise PublicationGateError("membership contains duplicate task/attempt pairs")
    logical_hash = logical_content_hash(members, primary_key)
    path = output_dir / dataset_id
    manifest = {
        "dataset_id": dataset_id,
        "status": "PUBLISHED",
        "evidence_level": "SOFTWARE_VALIDATED",
        "input_manifest_hash": input_manifest_hash,
        "rule_version": rule_version,
        "logical_content_hash": logical_hash,
        "member_count": len(members),
        "member_kind": member_kind,
    }
    manifest_bytes = canonical_json_bytes(manifest)
    if path.exists():
        existing = path / "dataset_manifest.json"
        if not existing.is_file() or existing.read_bytes() != manifest_bytes:
            raise PublicationGateError("immutable dataset publication conflicts with existing content")
        return DatasetPublication(dataset_id, "PUBLISHED", logical_hash, path)
    path.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(members), path / "membership.parquet")
    (path / "dataset_manifest.json").write_bytes(manifest_bytes)
    (path / "recipe.json").write_bytes(canonical_json_bytes({"rule_version": rule_version}))
    (path / "quality_report.json").write_bytes(
        canonical_json_bytes(quality_report(path / "membership.parquet"))
    )
    diversity_key = "demonstration_id" if member_kind == "EXTERNAL_DEMONSTRATION" else "task_id"
    diversity_label = "unique_demonstrations" if member_kind == "EXTERNAL_DEMONSTRATION" else "unique_tasks"
    (path / "diversity_report.json").write_bytes(
        canonical_json_bytes({diversity_label: len({item[diversity_key] for item in members})})
    )
    (path / "cost_report.json").write_bytes(canonical_json_bytes({"cost_cny_fen": None}))
    if member_kind == "EXTERNAL_DEMONSTRATION":
        external_demonstrations = sorted(
            (
                {
                    "demonstration_id": item["demonstration_id"],
                    "eligibility_decision_id": item["eligibility_decision_id"],
                    "parent_demonstration_id": item.get("parent_demonstration_id"),
                    "source_record_id": item["source_record_id"],
                    "upstream_message_refs": item["upstream_message_refs"],
                }
                for item in members
            ),
            key=lambda item: str(item["demonstration_id"]),
        )
        (path / "lineage_index.json").write_bytes(
            canonical_json_bytes(
                {
                    "external_demonstrations": external_demonstrations,
                    "source_records": sorted(
                        {source for item in members for source in item["source_record_ids"]}
                    ),
                }
            )
        )
        (path / "data_card.md").write_text(
            "# External demonstration dataset\n\n"
            "This release is governed by external-SFT admission decisions; replay, "
            "result evidence, and rewards remain independent evidence streams.\n",
            encoding="utf-8",
        )
    else:
        attempts = sorted(
            (
                {
                    "attempt_id": item["attempt_id"],
                    "task_id": item["task_id"],
                    "quality_decision_id": item["quality_decision_id"],
                    "source_record_ids": sorted(item["source_record_ids"]),
                }
                for item in members
            ),
            key=lambda item: str(item["attempt_id"]),
        )
        decisions = sorted(
            (
                {
                    "quality_decision_id": item["quality_decision_id"],
                    "attempt_id": item["attempt_id"],
                }
                for item in members
            ),
            key=lambda item: str(item["quality_decision_id"]),
        )
        (path / "lineage_index.json").write_bytes(
            canonical_json_bytes(
                {
                    "source_records": sorted({source for item in members for source in item["source_record_ids"]}),
                    "attempts": attempts,
                    "quality_decisions": decisions,
                }
            )
        )
        (path / "data_card.md").write_text(
            "# Software-test dataset\n\nThis release is SOFTWARE_VALIDATED and is not eligible for training.\n",
            encoding="utf-8",
        )
    return DatasetPublication(dataset_id, "PUBLISHED", logical_hash, path)
