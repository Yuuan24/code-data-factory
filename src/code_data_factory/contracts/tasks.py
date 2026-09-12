"""Source and task-package records for contract version 2."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

CONTRACT_MAJOR = 2
CONTRACT_VERSION = "2.1.0"


def _is_current_contract(value: str) -> str:
    if value.split(".", 1)[0] != str(CONTRACT_MAJOR):
        raise ValueError(f"contract_version must have major version {CONTRACT_MAJOR}")
    return value


class EvidenceLevel(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    SOFTWARE_VALIDATED = "SOFTWARE_VALIDATED"
    EXECUTION_VALIDATED = "EXECUTION_VALIDATED"
    TRAINING_EVIDENCED = "TRAINING_EVIDENCED"


class UsageScope(StrEnum):
    TRAIN = "TRAIN"
    DEVELOPMENT = "DEVELOPMENT"
    TEST = "TEST"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"
    BENCHMARK_ONLY = "BENCHMARK_ONLY"


class AccessScope(StrEnum):
    MODEL_VISIBLE = "MODEL_VISIBLE"
    VERIFIER_PRIVATE = "VERIFIER_PRIVATE"
    INTERNAL = "INTERNAL"


class ArtifactRef(BaseModel):
    """A content-addressed artifact without machine-local or secret-bearing location data."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str = Field(min_length=1)
    uri: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
    media_type: str = Field(min_length=1)
    producer_run_id: str = Field(min_length=1)
    access_scope: AccessScope

    @field_validator("uri")
    @classmethod
    def uri_is_safe_and_portable(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.username or parsed.password or "@" in parsed.netloc:
            raise ValueError("artifact URI must not contain credentials")
        if parsed.scheme in {"", "cas"}:
            path = parsed.path if parsed.scheme else value
            if path.startswith("/") or PurePosixPath(path).is_absolute():
                raise ValueError("artifact URI must not be an absolute path")
            if ".." in PurePosixPath(path).parts:
                raise ValueError("artifact URI must not traverse parent directories")
        elif parsed.scheme not in {"s3", "gs", "https"}:
            raise ValueError(
                "artifact URI must be project-relative or a supported content-store URI"
            )
        return value


class SourceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INVALIDATED = "INVALIDATED"


class ReplayCapability(StrEnum):
    """Whether a source demonstration can be replayed in its original environment."""

    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class SourceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = CONTRACT_VERSION
    source_snapshot_id: str = Field(min_length=1)
    source_uri: HttpUrl
    upstream_revision: str = Field(min_length=1)
    captured_at: datetime
    license_ref: ArtifactRef
    usage_scope: UsageScope
    manifest_ref: ArtifactRef
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_kind: str = Field(min_length=1)
    status: SourceStatus = SourceStatus.ACTIVE

    _contract_version = field_validator("contract_version")(_is_current_contract)


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = CONTRACT_VERSION
    source_record_id: str = Field(min_length=1)
    source_snapshot_id: str = Field(min_length=1)
    raw_ref: ArtifactRef
    upstream_id: str = Field(min_length=1)
    origin_kind: str = Field(pattern=r"^(PUBLIC_ORIGINAL|PROJECT_SYNTHETIC|DERIVED)$")
    parent_source_record_ids: list[str] = Field(default_factory=list)
    association_origin: str | None = None

    _contract_version = field_validator("contract_version")(_is_current_contract)


class ExternalDemonstration(BaseModel):
    """An existing upstream demonstration with independently governed SFT admission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: str = CONTRACT_VERSION
    demonstration_id: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    upstream_task_ref: ArtifactRef
    upstream_tool_bundle_ref: ArtifactRef
    message_refs: list[ArtifactRef] = Field(min_length=1)
    call_result_refs: list[ArtifactRef] = Field(default_factory=list)
    answer_ref: ArtifactRef
    upstream_synthetic_status: str | None = None
    parent_demonstration_id: str | None = None
    repair_rule_ref: ArtifactRef | None = None
    eligibility_decision_ref: ArtifactRef | None = None
    replay_capability: ReplayCapability = ReplayCapability.UNKNOWN
    result_evidence_ref: ArtifactRef | None = None
    reward_evidence_ref: ArtifactRef | None = None
    usage_scope: UsageScope
    source_origin: str = Field(
        pattern=r"^(PUBLIC_ORIGINAL|DERIVED|PROJECT_SAMPLING|MODEL_GENERATION)$"
    )

    _contract_version = field_validator("contract_version")(_is_current_contract)

    @model_validator(mode="after")
    def external_material_is_complete_and_repair_is_immutable(self) -> ExternalDemonstration:
        visible = (
            self.upstream_task_ref,
            self.upstream_tool_bundle_ref,
            *self.message_refs,
            *self.call_result_refs,
            self.answer_ref,
        )
        if any(ref.access_scope is not AccessScope.MODEL_VISIBLE for ref in visible):
            raise ValueError("external task, tools, messages, results, and answer must be model-visible")
        if (self.parent_demonstration_id is None) != (self.repair_rule_ref is None):
            raise ValueError("a repaired demonstration needs both parent_demonstration_id and repair_rule_ref")
        if self.parent_demonstration_id == self.demonstration_id:
            raise ValueError("a repaired demonstration must have a distinct parent")
        return self


class CapabilityState(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class Capabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reset: CapabilityState = CapabilityState.UNKNOWN
    action_replay: CapabilityState = CapabilityState.UNKNOWN
    snapshot_restore: CapabilityState = CapabilityState.UNKNOWN
    evidence_refs: list[ArtifactRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def supported_capabilities_need_evidence(self) -> Capabilities:
        if CapabilityState.SUPPORTED in self.__dict__.values() and not self.evidence_refs:
            raise ValueError("supported capabilities require evidence_refs")
        return self


class TaskStatus(StrEnum):
    DRAFT = "DRAFT"
    AUDITED = "AUDITED"
    EXECUTABLE = "EXECUTABLE"
    FROZEN = "FROZEN"
    INVALIDATED = "INVALIDATED"


class TaskPackage(BaseModel):
    """An independently verifiable task; demonstrations and private answers stay outside it."""

    model_config = ConfigDict(extra="forbid")

    contract_version: str = CONTRACT_VERSION
    task_id: str = Field(min_length=1)
    task_revision: str = Field(min_length=1)
    source_record_ids: list[str] = Field(min_length=1)
    instruction_ref: ArtifactRef
    initial_resources_ref: ArtifactRef
    tool_bundle_ref: ArtifactRef
    environment_ref: ArtifactRef
    verifier_spec_ref: ArtifactRef
    expected_result_ref: ArtifactRef
    task_family: str = Field(min_length=1)
    template_family_id: str = Field(min_length=1)
    source_group_ids: list[str] = Field(min_length=1)
    derivation_root_ids: list[str] = Field(min_length=1)
    usage_scope: UsageScope
    split_group_id: str = Field(min_length=1)
    split_policy_version: str = Field(min_length=1)
    dependency_depth: int = Field(ge=0)
    tool_set: list[str] = Field(min_length=1)
    recovery_condition: str | None = None
    difficulty_bin: str | None = None
    interaction_budget_ref: ArtifactRef
    initial_state_ref: ArtifactRef | None = None
    capabilities: Capabilities
    status: TaskStatus = TaskStatus.DRAFT

    _contract_version = field_validator("contract_version")(_is_current_contract)

    @model_validator(mode="after")
    def separate_model_and_private_resources(self) -> TaskPackage:
        visible = (self.instruction_ref, self.initial_resources_ref, self.tool_bundle_ref)
        private = (self.verifier_spec_ref, self.expected_result_ref)
        if any(ref.access_scope is not AccessScope.MODEL_VISIBLE for ref in visible):
            raise ValueError("instruction, resources, and tools must be model-visible")
        if any(ref.access_scope is not AccessScope.VERIFIER_PRIVATE for ref in private):
            raise ValueError("verifier specification and expected result must be verifier-private")
        if (
            self.status in {TaskStatus.EXECUTABLE, TaskStatus.FROZEN}
            and self.initial_state_ref is None
        ):
            raise ValueError("executable tasks require initial_state_ref")
        return self


class TaskGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    split_group_id: str = Field(min_length=1)
    member_task_ids_ref: ArtifactRef
    reason_edges_ref: ArtifactRef
    assigned_scope: UsageScope


TaskLike = Annotated[TaskPackage, Field(discriminator=None)]
