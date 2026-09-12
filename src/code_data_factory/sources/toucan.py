"""Safe, lossless-enough import of Toucan-style message histories.

This adapter treats source text as data.  It intentionally does not evaluate
arguments, snippets, or tool payloads from a historical record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import pyarrow.parquet as pq

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes
from code_data_factory.contracts.tasks import (
    AccessScope,
    ArtifactRef,
    ExternalDemonstration,
    ReplayCapability,
    UsageScope,
)
from code_data_factory.contracts.trajectory import (
    ActorKind,
    Attempt,
    AttemptState,
    EndReason,
    EventStatus,
    EventType,
    Trajectory,
    TrajectoryEvent,
)


class AssociationAmbiguity(StrEnum):
    ORPHAN_TOOL_RESULT = "ORPHAN_TOOL_RESULT"
    DUPLICATE_TOOL_CALL = "DUPLICATE_TOOL_CALL"
    INVALID_MESSAGE = "INVALID_MESSAGE"
    MISSING_TOOL_DEFINITION = "MISSING_TOOL_DEFINITION"
    MISSING_ANSWER = "MISSING_ANSWER"


@dataclass(frozen=True)
class ImportedSourceRecord:
    source_record_id: str
    source_snapshot_id: str
    upstream_id: str
    origin_kind: str
    association_origin: str
    usage_scope: str
    raw_ref: ArtifactRef


@dataclass(frozen=True)
class QuarantinedRecord:
    upstream_id: str
    reason: str


@dataclass(frozen=True)
class ImportedToucan:
    records: list[ImportedSourceRecord]
    demonstrations: list[ExternalDemonstration]
    materials: list[dict[str, Any]]
    trajectories: list[Trajectory]
    quarantine: list[QuarantinedRecord]


def _ref(name: str, value: Any, scope: AccessScope, producer_run_id: str) -> ArtifactRef:
    payload = canonical_json_bytes(value)
    return ArtifactRef(
        artifact_id=name,
        uri=f"data/normalized/{name}.json",
        sha256=sha256_bytes(payload),
        byte_size=len(payload),
        media_type="application/json",
        producer_run_id=producer_run_id,
        access_scope=scope,
    )


def _event_type(message: dict[str, Any]) -> EventType:
    role = message.get("role")
    if role in {"tool", "tool_response"}:
        return EventType.TOOL_RESULT
    if role == "tool_call" or (role == "assistant" and message.get("tool_calls")):
        return EventType.TOOL_CALL
    if role == "assistant":
        return EventType.MODEL_OUTPUT
    return EventType.OBSERVATION


def _training_message(message: dict[str, Any], *, tool_call_id: str | None = None) -> dict[str, Any]:
    """Normalize known Toucan role labels without evaluating source payload text."""

    role = message.get("role")
    if role == "tool_call":
        return {
            "role": "assistant",
            "content": "",
            "tool_call": {"id": tool_call_id, "raw_content": message.get("content", "")},
        }
    if role == "tool_response":
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": message.get("content", ""),
        }
    return dict(message)


def _records_from_source(source: Path) -> list[object]:
    """Load JSON or Parquet history rows without interpreting source payloads."""

    if source.suffix == ".parquet":
        table = pq.read_table(source)
        return cast(list[object], table.to_pylist())
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Toucan source must be a JSON array or a Parquet table")
    return raw


def _messages(value: object) -> list[dict[str, Any]] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        return None
    return value


def import_toucan_records(
    source: Path, *, snapshot_id: str, producer_run_id: str
) -> ImportedToucan:
    """Import JSON/Parquet history records and isolate ambiguous call links."""

    raw = _records_from_source(source)

    records: list[ImportedSourceRecord] = []
    demonstrations: list[ExternalDemonstration] = []
    materials: list[dict[str, Any]] = []
    trajectories: list[Trajectory] = []
    quarantine: list[QuarantinedRecord] = []
    now = datetime.now(UTC)
    for row in raw:
        if not isinstance(row, dict):
            quarantine.append(QuarantinedRecord(upstream_id="<unknown>", reason=AssociationAmbiguity.INVALID_MESSAGE))
            continue
        upstream_id = row.get("id", row.get("uuid"))
        if not isinstance(upstream_id, str) or not upstream_id:
            quarantine.append(QuarantinedRecord(upstream_id="<unknown>", reason=AssociationAmbiguity.INVALID_MESSAGE))
            continue
        messages = _messages(row.get("messages"))
        if messages is None:
            quarantine.append(QuarantinedRecord(upstream_id=upstream_id, reason=AssociationAmbiguity.INVALID_MESSAGE))
            continue
        tools = row.get("tools")
        if isinstance(tools, str):
            try:
                tools = json.loads(tools)
            except json.JSONDecodeError:
                tools = None
        if not isinstance(tools, (list, dict)):
            quarantine.append(
                QuarantinedRecord(
                    upstream_id=upstream_id,
                    reason=AssociationAmbiguity.MISSING_TOOL_DEFINITION.value,
                )
            )
            continue
        calls: set[str] = set()
        pending_calls: list[str] = []
        ambiguous: AssociationAmbiguity | None = None
        events: list[TrajectoryEvent] = []
        attempt_id = f"{snapshot_id}:{upstream_id}:historical"
        normalized_messages: list[dict[str, Any]] = []
        for seq, message in enumerate(messages):
            kind = _event_type(message)
            tool_call_id: str | None = None
            if kind is EventType.TOOL_CALL:
                if message.get("role") == "tool_call":
                    tool_call_id = f"{attempt_id}:source-call:{seq}"
                else:
                    tool_calls = message.get("tool_calls")
                    if not isinstance(tool_calls, list) or len(tool_calls) != 1:
                        ambiguous = AssociationAmbiguity.INVALID_MESSAGE
                        break
                    call = tool_calls[0]
                    if not isinstance(call, dict) or not isinstance(call.get("id"), str):
                        ambiguous = AssociationAmbiguity.INVALID_MESSAGE
                        break
                    tool_call_id = call["id"]
                if tool_call_id in calls:
                    ambiguous = AssociationAmbiguity.DUPLICATE_TOOL_CALL
                    break
                calls.add(tool_call_id)
                pending_calls.append(tool_call_id)
            elif kind is EventType.TOOL_RESULT:
                tool_call_id = message.get("tool_call_id")
                if message.get("role") == "tool_response":
                    tool_call_id = pending_calls.pop(0) if pending_calls else None
                elif isinstance(tool_call_id, str) and tool_call_id in pending_calls:
                    pending_calls.remove(tool_call_id)
                if not isinstance(tool_call_id, str) or tool_call_id not in calls:
                    ambiguous = AssociationAmbiguity.ORPHAN_TOOL_RESULT
                    break
            normalized_messages.append(
                _training_message(message, tool_call_id=tool_call_id)
            )
            events.append(
                TrajectoryEvent(
                    event_id=f"{attempt_id}:event:{seq}",
                    attempt_id=attempt_id,
                    seq=seq,
                    event_type=kind,
                    timestamp=now,
                    model_call_id=f"{attempt_id}:call:{seq}" if kind is EventType.MODEL_OUTPUT else None,
                    tool_call_id=tool_call_id,
                    payload_ref=_ref(
                        f"{snapshot_id}-{upstream_id}-event-{seq}",
                        message,
                        AccessScope.INTERNAL,
                        producer_run_id,
                    ),
                    status=EventStatus.COMPLETE,
                    origin="toucan_history",
                )
            )
        if ambiguous is not None:
            quarantine.append(QuarantinedRecord(upstream_id=upstream_id, reason=ambiguous.value))
            continue
        answer = next(
            (
                message
                for message in reversed(normalized_messages)
                if message.get("role") == "assistant" and not message.get("tool_calls")
            ),
            None,
        )
        if answer is None:
            quarantine.append(
                QuarantinedRecord(
                    upstream_id=upstream_id,
                    reason=AssociationAmbiguity.MISSING_ANSWER.value,
                )
            )
            continue
        raw_ref = _ref(
            f"{snapshot_id}-{upstream_id}-raw", row, AccessScope.INTERNAL, producer_run_id
        )
        records.append(
            ImportedSourceRecord(
                source_record_id=f"{snapshot_id}:{upstream_id}",
                source_snapshot_id=snapshot_id,
                upstream_id=upstream_id,
                origin_kind="PUBLIC_ORIGINAL",
                association_origin="inferred_unique",
                usage_scope="TRAIN",
                raw_ref=raw_ref,
            )
        )
        message_refs = [
            _ref(
                f"{snapshot_id}-{upstream_id}-message-{seq}",
                message,
                AccessScope.MODEL_VISIBLE,
                producer_run_id,
            )
            for seq, message in enumerate(normalized_messages)
        ]
        demonstrations.append(
            ExternalDemonstration(
                demonstration_id=f"{snapshot_id}:{upstream_id}",
                source_record_id=f"{snapshot_id}:{upstream_id}",
                upstream_task_ref=_ref(
                    f"{snapshot_id}-{upstream_id}-task",
                    row.get("question", row.get("task", normalized_messages[0])),
                    AccessScope.MODEL_VISIBLE,
                    producer_run_id,
                ),
                upstream_tool_bundle_ref=_ref(
                    f"{snapshot_id}-{upstream_id}-tools",
                    tools,
                    AccessScope.MODEL_VISIBLE,
                    producer_run_id,
                ),
                message_refs=message_refs,
                call_result_refs=[
                    message_refs[seq]
                    for seq, message in enumerate(normalized_messages)
                    if message.get("role") == "tool"
                ],
                answer_ref=_ref(
                    f"{snapshot_id}-{upstream_id}-answer",
                    answer,
                    AccessScope.MODEL_VISIBLE,
                    producer_run_id,
                ),
                upstream_synthetic_status=(
                    str(row["status"]) if row.get("status") is not None else None
                ),
                replay_capability=ReplayCapability.UNSUPPORTED,
                usage_scope=UsageScope.TRAIN,
                source_origin="PUBLIC_ORIGINAL",
            )
        )
        materials.append(
            {
                "demonstration_id": f"{snapshot_id}:{upstream_id}",
                "messages": normalized_messages,
            }
        )
        attempt = Attempt(
            attempt_id=attempt_id,
            task_id=f"historical:{upstream_id}",
            task_revision="historical",
            actor_kind=ActorKind.HISTORICAL_IMPORT,
            harness_ref=_ref("historical-importer", {"adapter": "toucan"}, AccessScope.INTERNAL, producer_run_id),
            environment_ref=_ref("missing-environment", {"available": False}, AccessScope.INTERNAL, producer_run_id),
            preflight_ref=_ref("historical-preflight", {"available": False}, AccessScope.INTERNAL, producer_run_id),
            budget_ref=_ref("historical-budget", {"available": False}, AccessScope.INTERNAL, producer_run_id),
            started_at=now,
            finished_at=now,
            end_reason=EndReason.COMPLETED,
            state=AttemptState.SEALED,
        )
        trajectories.append(Trajectory(attempt=attempt, events=events))
    return ImportedToucan(
        records=records,
        demonstrations=demonstrations,
        materials=materials,
        trajectories=trajectories,
        quarantine=quarantine,
    )


def write_import_result(result: ImportedToucan, *, output_dir: Path) -> dict[str, Path]:
    """Persist consumable manifests without emitting historical raw payload text."""

    output_dir.mkdir(parents=True, exist_ok=True)
    records_path = output_dir / "source_records.json"
    demonstrations_path = output_dir / "external_demonstrations.json"
    material_path = output_dir / "external_material.json"
    attempts_path = output_dir / "attempt_manifest.json"
    events_path = output_dir / "event_manifest.json"
    quarantine_path = output_dir / "quarantine.json"
    records_path.write_bytes(
        canonical_json_bytes(
            {"source_records": [record.__dict__ | {"raw_ref": record.raw_ref.model_dump(mode="json")} for record in result.records]}
        )
    )
    demonstrations_path.write_bytes(
        canonical_json_bytes(
            {
                "external_demonstrations": [
                    item.model_dump(mode="json") for item in result.demonstrations
                ]
            }
        )
    )
    material_path.write_bytes(
        canonical_json_bytes({"external_material": result.materials})
    )
    attempts_path.write_bytes(
        canonical_json_bytes(
            {"attempts": [trajectory.attempt.model_dump(mode="json") for trajectory in result.trajectories]}
        )
    )
    events_path.write_bytes(
        canonical_json_bytes(
            {"events": [event.model_dump(mode="json") for trajectory in result.trajectories for event in trajectory.events]}
        )
    )
    quarantine_path.write_bytes(
        canonical_json_bytes({"quarantine": [item.__dict__ for item in result.quarantine]})
    )
    return {
        "source_records": records_path,
        "external_demonstrations": demonstrations_path,
        "external_material": material_path,
        "attempts": attempts_path,
        "events": events_path,
        "quarantine": quarantine_path,
    }
