"""Immutable attempt, event, visible-context, and dependency-edge contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .tasks import CONTRACT_VERSION, ArtifactRef, _is_current_contract


class ActorKind(StrEnum):
    HISTORICAL_IMPORT = "HISTORICAL_IMPORT"
    SCRIPTED_FIXTURE = "SCRIPTED_FIXTURE"
    MODEL_GENERATION = "MODEL_GENERATION"
    MODEL_EVALUATION = "MODEL_EVALUATION"
    TRAINER_SAMPLING = "TRAINER_SAMPLING"


class AttemptState(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SEALED = "SEALED"


class EndReason(StrEnum):
    COMPLETED = "COMPLETED"
    BUDGET_TRUNCATED = "BUDGET_TRUNCATED"
    ENVIRONMENT_ERROR = "ENVIRONMENT_ERROR"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


class Attempt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: str = CONTRACT_VERSION
    attempt_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    task_revision: str = Field(min_length=1)
    parent_attempt_id: str | None = None
    branch_event_id: str | None = None
    actor_kind: ActorKind
    policy_ref: ArtifactRef | None = None
    sampling_config_ref: ArtifactRef | None = None
    harness_ref: ArtifactRef
    environment_ref: ArtifactRef
    preflight_ref: ArtifactRef
    budget_ref: ArtifactRef
    started_at: datetime
    finished_at: datetime | None = None
    event_manifest_ref: ArtifactRef | None = None
    final_output_ref: ArtifactRef | None = None
    end_reason: EndReason | None = None
    cost_record_ref: ArtifactRef | None = None
    state: AttemptState = AttemptState.CREATED

    _contract_version = field_validator("contract_version")(_is_current_contract)

    @model_validator(mode="after")
    def sealed_attempt_is_explicit(self) -> Attempt:
        if self.actor_kind is ActorKind.HISTORICAL_IMPORT and self.policy_ref is not None:
            raise ValueError("historical imports must not claim a current policy")
        if self.state is AttemptState.SEALED and (
            self.finished_at is None or self.end_reason is None
        ):
            raise ValueError("sealed attempts need finished_at and end_reason")
        return self


class EventType(StrEnum):
    OBSERVATION = "OBSERVATION"
    MODEL_REQUEST = "MODEL_REQUEST"
    MODEL_OUTPUT = "MODEL_OUTPUT"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    CONTEXT_REWRITE = "CONTEXT_REWRITE"
    CHECKPOINT = "CHECKPOINT"
    FINAL_OUTPUT = "FINAL_OUTPUT"
    INTERRUPTION = "INTERRUPTION"


class EventStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    ISOLATED = "ISOLATED"


class TrajectoryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    seq: int = Field(ge=0)
    event_type: EventType
    timestamp: datetime
    model_call_id: str | None = None
    tool_call_id: str | None = None
    parent_event_id: str | None = None
    payload_ref: ArtifactRef | None = None
    visible_context_ref: ArtifactRef | None = None
    raw_output_ref: ArtifactRef | None = None
    status: EventStatus = EventStatus.COMPLETE
    origin: str = Field(min_length=1)

    @model_validator(mode="after")
    def event_has_its_required_link(self) -> TrajectoryEvent:
        if (
            self.event_type in {EventType.MODEL_REQUEST, EventType.MODEL_OUTPUT}
            and not self.model_call_id
        ):
            raise ValueError("model request/output needs model_call_id")
        if (
            self.event_type in {EventType.TOOL_CALL, EventType.TOOL_RESULT}
            and not self.tool_call_id
        ):
            raise ValueError("tool call/result needs tool_call_id")
        return self


class DependencyProvenance(StrEnum):
    FIXED_TASK_TRUTH = "FIXED_TASK_TRUTH"
    DETERMINISTIC_PARSE = "DETERMINISTIC_PARSE"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    HUMAN_CONFIRMATION = "HUMAN_CONFIRMATION"


class DependencyEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    from_event_id: str = Field(min_length=1)
    to_event_id: str = Field(min_length=1)
    source_field: str = Field(min_length=1)
    target_field: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    provenance: DependencyProvenance
    evidence_ref: ArtifactRef | None = None


class VisibleContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    context_id: str = Field(min_length=1)
    model_call_id: str = Field(min_length=1)
    ordered_message_refs: list[ArtifactRef] = Field(min_length=1)
    tool_schema_ref: ArtifactRef
    render_config_ref: ArtifactRef
    input_token_ref: ArtifactRef | None = None
    parent_context_id: str | None = None
    rewrite_event_id: str | None = None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    checkpoint_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    event_seq: int = Field(ge=0)
    snapshot_ref: ArtifactRef | None = None
    environment_ref: ArtifactRef
    context_ref: ArtifactRef
    restore_capability: str = Field(pattern=r"^(SUPPORTED|UNSUPPORTED)$")
    state_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def checkpoint_does_not_fake_restore(self) -> Checkpoint:
        if self.restore_capability == "SUPPORTED" and (
            self.snapshot_ref is None or self.state_hash is None
        ):
            raise ValueError("supported restore needs snapshot and state hash")
        return self


class Trajectory(BaseModel):
    """Cross-record validation that cannot be inferred from an isolated event."""

    model_config = ConfigDict(extra="forbid")

    attempt: Attempt
    events: list[TrajectoryEvent]
    dependency_edges: list[DependencyEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_event_links(self) -> Trajectory:
        if any(event.attempt_id != self.attempt.attempt_id for event in self.events):
            raise ValueError("every event must belong to the trajectory attempt")
        sequences = [event.seq for event in self.events]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise ValueError("event sequence must be strictly increasing and unique")
        event_ids = {event.event_id for event in self.events}
        calls = {
            event.tool_call_id for event in self.events if event.event_type is EventType.TOOL_CALL
        }
        for event in self.events:
            if event.event_type is EventType.TOOL_RESULT and event.tool_call_id not in calls:
                raise ValueError("tool result must reference a tool call in the same attempt")
        for edge in self.dependency_edges:
            if (
                edge.attempt_id != self.attempt.attempt_id
                or {
                    edge.from_event_id,
                    edge.to_event_id,
                }
                - event_ids
            ):
                raise ValueError("dependency edges must connect events in the same attempt")
        return self
