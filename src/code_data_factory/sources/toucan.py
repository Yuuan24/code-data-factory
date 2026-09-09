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
from typing import Any

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes
from code_data_factory.contracts.tasks import AccessScope, ArtifactRef
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
    if role == "tool":
        return EventType.TOOL_RESULT
    if role == "assistant" and message.get("tool_calls"):
        return EventType.TOOL_CALL
    if role == "assistant":
        return EventType.MODEL_OUTPUT
    return EventType.OBSERVATION


def import_toucan_records(
    source: Path, *, snapshot_id: str, producer_run_id: str
) -> ImportedToucan:
    """Import a JSON array of history records and isolate ambiguous call links."""

    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Toucan source must be a JSON array")

    records: list[ImportedSourceRecord] = []
    trajectories: list[Trajectory] = []
    quarantine: list[QuarantinedRecord] = []
    now = datetime.now(UTC)
    for row in raw:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            quarantine.append(QuarantinedRecord(upstream_id="<unknown>", reason=AssociationAmbiguity.INVALID_MESSAGE))
            continue
        upstream_id = row["id"]
        messages = row.get("messages")
        if not isinstance(messages, list) or not all(isinstance(item, dict) for item in messages):
            quarantine.append(QuarantinedRecord(upstream_id=upstream_id, reason=AssociationAmbiguity.INVALID_MESSAGE))
            continue
        calls: set[str] = set()
        ambiguous: AssociationAmbiguity | None = None
        events: list[TrajectoryEvent] = []
        attempt_id = f"{snapshot_id}:{upstream_id}:historical"
        for seq, message in enumerate(messages):
            kind = _event_type(message)
            tool_call_id: str | None = None
            if kind is EventType.TOOL_CALL:
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
            elif kind is EventType.TOOL_RESULT:
                tool_call_id = message.get("tool_call_id")
                if not isinstance(tool_call_id, str) or tool_call_id not in calls:
                    ambiguous = AssociationAmbiguity.ORPHAN_TOOL_RESULT
                    break
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
                usage_scope="HISTORICAL_ONLY",
                raw_ref=raw_ref,
            )
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
    return ImportedToucan(records=records, trajectories=trajectories, quarantine=quarantine)
