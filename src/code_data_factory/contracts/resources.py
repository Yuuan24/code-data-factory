"""External-resource authorisation and cost records, separate from local software tests."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .tasks import ArtifactRef


class ResourceKind(StrEnum):
    CPU = "CPU"
    GPU = "GPU"
    STORAGE = "STORAGE"
    EXTERNAL_MODEL = "EXTERNAL_MODEL"


class Quote(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    quote_id: str = Field(min_length=1)
    resource_kind: ResourceKind
    provider: str = Field(min_length=1)
    quoted_at: date
    unit: str = Field(min_length=1)
    unit_price_cny_fen: int = Field(ge=0)
    evidence_ref: ArtifactRef


class Authorization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    authorization_id: str = Field(min_length=1)
    resource_kind: ResourceKind
    authorized_by: str = Field(min_length=1)
    authorized_at: datetime
    stop_limit_cny_fen: int = Field(gt=0)
    evidence_ref: ArtifactRef


class CostEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cost_entry_id: str = Field(min_length=1)
    resource_kind: ResourceKind
    amount_cny_fen: int = Field(ge=0)
    occurred_at: datetime
    outcome: str = Field(min_length=1)
    retry_of: str | None = None
    evidence_ref: ArtifactRef | None = None


class ResourcePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: str = Field(min_length=1)
    quotes: list[Quote] = Field(default_factory=list)
    authorizations: list[Authorization] = Field(default_factory=list)
    cost_entries: list[CostEntry] = Field(default_factory=list)

    def external_run_allowed(self, resource_kinds: set[ResourceKind]) -> tuple[bool, str | None]:
        for kind in resource_kinds:
            quotes = [quote for quote in self.quotes if quote.resource_kind is kind]
            authorizations = [item for item in self.authorizations if item.resource_kind is kind]
            if not quotes:
                return False, f"missing quote for {kind.value}"
            if not authorizations:
                return False, f"missing authorization for {kind.value}"
            spent = sum(
                entry.amount_cny_fen for entry in self.cost_entries if entry.resource_kind is kind
            )
            if spent >= max(item.stop_limit_cny_fen for item in authorizations):
                return False, f"stop limit reached for {kind.value}"
        return True, None

    @model_validator(mode="after")
    def ledger_has_no_negative_costs(self) -> ResourcePolicy:
        return self
