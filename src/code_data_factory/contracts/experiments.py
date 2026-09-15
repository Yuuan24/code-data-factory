"""Frozen contracts for controlled SFT comparisons."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .artifacts import canonical_json_bytes, sha256_bytes


class ExperimentStatus(StrEnum):
    DRAFT = "DRAFT"
    PREREGISTERED = "PREREGISTERED"
    RUNNING = "RUNNING"
    CLOSED = "CLOSED"


class RunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BUDGET_BLOCKED = "BUDGET_BLOCKED"


class BatchShape(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    per_device_batch_size: int = Field(ge=1)
    gradient_accumulation_steps: int = Field(ge=1)
    max_context_tokens: int = Field(ge=1)
    precision: str = Field(min_length=1)


class ExperimentPlan(BaseModel):
    """Every field affecting comparability is immutable inside one plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    hypothesis: str = Field(min_length=1)
    target_data_difference: str = Field(min_length=1)
    candidate_pool_version: str = Field(min_length=1)
    recipes: tuple[str, str]
    seeds: tuple[int, int, int]
    model: dict[str, str]
    method: str = Field(min_length=1)
    method_selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_shape: BatchShape
    planned_loss_tokens: int = Field(gt=0)
    planned_optimizer_steps: int = Field(gt=0)
    input_compute_budget: str = Field(min_length=1)
    evaluation_version: str = Field(min_length=1)
    matching: dict[str, Any] = Field(min_length=1)
    tool_protocol: dict[str, Any] = Field(min_length=1)
    exposure_budget: dict[str, Any] = Field(min_length=1)
    test_unlock_rule: dict[str, Any] = Field(min_length=1)
    guardrails: dict[str, Any] = Field(min_length=1)
    calibration_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    formalization: dict[str, Any] | None = None
    preregistration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: ExperimentStatus = ExperimentStatus.DRAFT

    @field_validator("recipes")
    @classmethod
    def two_distinct_recipes(cls, value: tuple[str, str]) -> tuple[str, str]:
        if len(set(value)) != 2 or any(not item for item in value):
            raise ValueError("experiment plan requires two distinct recipes")
        return value

    @field_validator("seeds")
    @classmethod
    def three_distinct_seeds(cls, value: tuple[int, int, int]) -> tuple[int, int, int]:
        if len(set(value)) != 3:
            raise ValueError("experiment plan requires three distinct seeds")
        return value

    @model_validator(mode="after")
    def frozen_identity_is_consistent(self) -> ExperimentPlan:
        required_model = {
            "model_id",
            "model_revision",
            "tokenizer_revision",
            "template_sha256",
            "thinking_mode",
        }
        if required_model - self.model.keys() or not all(self.model[key] for key in required_model):
            raise ValueError("experiment plan lacks a frozen model and template identity")
        if (
            self.status is not ExperimentStatus.DRAFT
            and self.preregistration_sha256 != self.frozen_conditions_sha256
        ):
            raise ValueError("preregistered plan hash must bind all frozen conditions")
        return self

    @property
    def frozen_conditions(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "revision": self.revision,
            "hypothesis": self.hypothesis,
            "target_data_difference": self.target_data_difference,
            "candidate_pool_version": self.candidate_pool_version,
            "recipes": self.recipes,
            "seeds": self.seeds,
            "model": self.model,
            "method": self.method,
            "method_selection_sha256": self.method_selection_sha256,
            "batch_shape": self.batch_shape,
            "planned_loss_tokens": self.planned_loss_tokens,
            "planned_optimizer_steps": self.planned_optimizer_steps,
            "input_compute_budget": self.input_compute_budget,
            "evaluation_version": self.evaluation_version,
            "matching": self.matching,
            "tool_protocol": self.tool_protocol,
            "exposure_budget": self.exposure_budget,
            "test_unlock_rule": self.test_unlock_rule,
            "guardrails": self.guardrails,
            "calibration_manifest_sha256": self.calibration_manifest_sha256,
            "formalization": self.formalization,
        }

    @property
    def frozen_conditions_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.frozen_conditions))


class TrainingRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    recipe: str = Field(min_length=1)
    seed: int
    dataset_id: str = Field(min_length=1)
    initial_model_ref: str = Field(min_length=1)
    method_config_ref: str = Field(min_length=1)
    batch_schedule_ref: str = Field(min_length=1)
    planned_loss_tokens: int = Field(gt=0)
    observed_loss_tokens: int = Field(ge=0)
    optimizer_steps: int = Field(ge=0)
    checkpoint_ref: str | None = None
    reload_verified: bool = False
    status: RunStatus

    @model_validator(mode="after")
    def completed_run_is_a_real_equal_budget_update(self) -> TrainingRun:
        if self.status is RunStatus.COMPLETED:
            if self.observed_loss_tokens != self.planned_loss_tokens or self.optimizer_steps < 1:
                raise ValueError(
                    "completed training requires exact planned loss tokens and optimizer steps"
                )
            if not self.checkpoint_ref or not self.reload_verified:
                raise ValueError("completed training requires a saved and reloaded checkpoint")
        return self


class EvaluationRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evaluation_run_id: str = Field(min_length=1)
    training_run_id: str = Field(min_length=1)
    suite_version: str = Field(min_length=1)
    split: str = Field(pattern=r"^(DEVELOPMENT|TEST)$")
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fixed_denominator: int = Field(gt=0)
    raw_results_ref: str = Field(min_length=1)
    status: RunStatus
