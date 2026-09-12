"""Token-level evidence emitted by an actual training-framework sampler."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from code_data_factory.contracts.artifacts import canonical_json_bytes


class SamplingRecordError(ValueError):
    """Raised when a purported sampling record cannot be consumed safely."""


class SamplingStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BUDGET_TRUNCATED = "BUDGET_TRUNCATED"


class SamplingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    tokenizer_revision: str = Field(min_length=1)
    template_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    thinking_mode: str = Field(min_length=1)


class SamplingFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(min_length=1)
    message: str = Field(min_length=1)


class SamplingCost(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gpu_seconds: float = Field(ge=0)
    provider_charge_cny: float | None = Field(default=None, ge=0)
    unavailable_reason: str | None = None

    @model_validator(mode="after")
    def cost_is_measured_or_explicitly_unavailable(self) -> SamplingCost:
        if self.provider_charge_cny is None and not self.unavailable_reason:
            raise SamplingRecordError("unknown provider charge requires an explicit reason")
        if self.provider_charge_cny is not None and self.unavailable_reason is not None:
            raise SamplingRecordError("known provider charge must not carry an unavailable reason")
        return self


class SamplingAttachment(BaseModel):
    """A consumable attachment, never a reconstruction from historical messages."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    provenance: str
    runner_kind: str
    policy: SamplingPolicy
    input_token_ids: tuple[int, ...]
    output_token_ids: tuple[int, ...]
    output_mask: tuple[int, ...]
    optimizer_step_count: int = Field(ge=0)
    sampling_status: SamplingStatus
    failure: SamplingFailure | None = None
    cost: SamplingCost

    @model_validator(mode="after")
    def actual_sampler_evidence_is_complete(self) -> SamplingAttachment:
        if self.provenance != "ACTUAL_TRAINER_SAMPLER":
            raise SamplingRecordError("sampling attachment requires an actual trainer sampler provenance")
        if self.runner_kind != "TRL_GRPO_TRAINER":
            raise SamplingRecordError("sampling attachment must identify the TRL trainer runner")
        if not self.input_token_ids:
            raise SamplingRecordError("sampling attachment requires actual input token ids")
        if len(self.output_token_ids) != len(self.output_mask):
            raise SamplingRecordError("output token ids and output mask must have the same length")
        if any(mask not in {0, 1} for mask in self.output_mask):
            raise SamplingRecordError("output mask values must be zero or one")
        if self.optimizer_step_count != 0:
            raise SamplingRecordError("sampling probe must not update optimizer steps")
        if self.sampling_status is SamplingStatus.FAILED and self.failure is None:
            raise SamplingRecordError("failed sampling requires a preserved failure record")
        if self.sampling_status is not SamplingStatus.FAILED and self.failure is not None:
            raise SamplingRecordError("only failed sampling may carry a failure record")
        return self


def write_sampling_attachment(attachment: SamplingAttachment, output_path: Path) -> None:
    """Persist exactly the attachment supplied by the trainer boundary."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_json_bytes(attachment.model_dump(mode="json")))


def load_sampling_attachment(path: Path) -> SamplingAttachment:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SamplingRecordError("sampling attachment cannot be read") from error
    return SamplingAttachment.model_validate(payload)
