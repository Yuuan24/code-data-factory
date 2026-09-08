"""Independent verifier and terminal-reward record contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .tasks import ArtifactRef


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    ERROR = "ERROR"
    INSUFFICIENT = "INSUFFICIENT"
    UNSTABLE = "UNSTABLE"


class Outcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class VerificationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verification_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    evidence_manifest_ref: ArtifactRef
    verifier_version: str = Field(min_length=1)
    check_results_ref: ArtifactRef
    status: VerificationStatus
    outcome: Outcome
    replay_consistency: str | None = None
    mutation_audit_ref: ArtifactRef | None = None
    verified_at: datetime

    @model_validator(mode="after")
    def unknown_is_not_a_decision(self) -> VerificationRecord:
        if self.status is not VerificationStatus.VERIFIED and self.outcome is not Outcome.UNKNOWN:
            raise ValueError(
                "error, insufficient, and unstable verification must have UNKNOWN outcome"
            )
        return self


class RewardAvailability(StrEnum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


class RewardRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reward_record_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    verification_id: str = Field(min_length=1)
    reward_policy_version: str = Field(min_length=1)
    reward_scope: str = Field(pattern=r"^(TERMINAL|STEP)$")
    components_ref: ArtifactRef | None = None
    total_reward: float | None = None
    availability: RewardAvailability
    unavailable_reason: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def reward_is_never_silently_zero(self) -> RewardRecord:
        if self.availability is RewardAvailability.KNOWN and self.total_reward is None:
            raise ValueError("known reward requires a numeric value")
        if self.availability is RewardAvailability.UNKNOWN and self.total_reward is not None:
            raise ValueError("unknown reward must be null, not zero")
        return self


def terminal_reward(
    verification: VerificationRecord, policy_version: str, created_at: datetime
) -> RewardRecord:
    """Create a new terminal reward record without mutating verifier evidence."""

    if verification.status is VerificationStatus.VERIFIED:
        value = 1.0 if verification.outcome is Outcome.PASS else 0.0
        availability = RewardAvailability.KNOWN
        reason = None
    else:
        value = None
        availability = RewardAvailability.UNKNOWN
        reason = verification.status.value
    return RewardRecord(
        reward_record_id=f"reward-{verification.verification_id}-{policy_version}",
        attempt_id=verification.attempt_id,
        verification_id=verification.verification_id,
        reward_policy_version=policy_version,
        reward_scope="TERMINAL",
        total_reward=value,
        availability=availability,
        unavailable_reason=reason,
        created_at=created_at,
    )
