"""Stable Arrow schemas exported with the contract-major directory."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa

SCHEMA_VERSION = "2.0.0"


def contract_schemas() -> dict[str, pa.Schema]:
    artifact_ref = pa.struct(
        [
            ("artifact_id", pa.string()),
            ("uri", pa.string()),
            ("sha256", pa.string()),
            ("byte_size", pa.int64()),
            ("media_type", pa.string()),
            ("producer_run_id", pa.string()),
            ("access_scope", pa.string()),
        ]
    )
    return {
        "tasks": pa.schema(
            [
                ("contract_version", pa.string()),
                ("task_id", pa.string()),
                ("task_revision", pa.string()),
                ("source_record_ids", pa.list_(pa.string())),
                ("instruction_ref", artifact_ref),
                ("usage_scope", pa.string()),
                ("split_group_id", pa.string()),
                ("status", pa.string()),
            ]
        ),
        "attempts": pa.schema(
            [
                ("attempt_id", pa.string()),
                ("task_id", pa.string()),
                ("actor_kind", pa.string()),
                ("end_reason", pa.string()),
                ("state", pa.string()),
            ]
        ),
        "events": pa.schema(
            [
                ("event_id", pa.string()),
                ("attempt_id", pa.string()),
                ("seq", pa.int64()),
                ("event_type", pa.string()),
                ("model_call_id", pa.string()),
                ("tool_call_id", pa.string()),
                ("status", pa.string()),
            ]
        ),
        "contexts": pa.schema(
            [
                ("context_id", pa.string()),
                ("model_call_id", pa.string()),
                ("ordered_message_refs", pa.list_(artifact_ref)),
                ("content_hash", pa.string()),
            ]
        ),
        "verifications": pa.schema(
            [
                ("verification_id", pa.string()),
                ("attempt_id", pa.string()),
                ("status", pa.string()),
                ("outcome", pa.string()),
            ]
        ),
        "rewards": pa.schema(
            [
                ("reward_record_id", pa.string()),
                ("attempt_id", pa.string()),
                ("verification_id", pa.string()),
                ("availability", pa.string()),
                ("total_reward", pa.float64()),
            ]
        ),
    }


def export_schemas(output_root: Path) -> list[Path]:
    destination = output_root / SCHEMA_VERSION
    destination.mkdir(parents=True, exist_ok=True)
    exported = []
    for name, schema in contract_schemas().items():
        path = destination / f"{name}.json"
        path.write_text(
            json.dumps({"name": name, "schema": str(schema)}, indent=2) + "\n", encoding="utf-8"
        )
        exported.append(path)
    return exported
