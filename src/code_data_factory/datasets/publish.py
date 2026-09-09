"""Local immutable dataset publication with evidence-level gates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from code_data_factory.contracts.artifacts import canonical_json_bytes, logical_content_hash
from code_data_factory.datasets.quality_reports import quality_report


class PublicationGateError(ValueError):
    """Publication violates a membership, evidence, or immutability invariant."""


@dataclass(frozen=True)
class DatasetPublication:
    dataset_id: str
    status: str
    logical_content_hash: str
    path: Path


def _validate_members(members: list[dict[str, Any]]) -> None:
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


def publish_dataset(
    *,
    dataset_id: str,
    members: list[dict[str, Any]],
    output_dir: Path,
    input_manifest_hash: str,
    rule_version: str,
) -> DatasetPublication:
    """Publish a software-test-only immutable release; real training is explicitly gated."""

    _validate_members(members)
    if len({(item["task_id"], item["attempt_id"]) for item in members}) != len(members):
        raise PublicationGateError("membership contains duplicate task/attempt pairs")
    logical_hash = logical_content_hash(members, "attempt_id")
    path = output_dir / dataset_id
    manifest = {
        "dataset_id": dataset_id,
        "status": "PUBLISHED",
        "evidence_level": "SOFTWARE_VALIDATED",
        "input_manifest_hash": input_manifest_hash,
        "rule_version": rule_version,
        "logical_content_hash": logical_hash,
        "member_count": len(members),
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
    (path / "diversity_report.json").write_bytes(canonical_json_bytes({"unique_tasks": len({item['task_id'] for item in members})}))
    (path / "cost_report.json").write_bytes(canonical_json_bytes({"cost_cny_fen": None}))
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
