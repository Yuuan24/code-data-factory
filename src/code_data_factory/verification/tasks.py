"""Independent fixed-value verifier for the bounded first-version task families."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class VerificationInput:
    attempt_id: str
    expected: Mapping[str, object]
    actual: Mapping[str, object]
    verifier_version: str
    forced_status: str
    verified_at: datetime


@dataclass(frozen=True)
class VerificationResult:
    attempt_id: str
    verifier_version: str
    status: str
    outcome: str
    checks: dict[str, bool]
    checks_for_model: dict[str, bool]
    verified_at: datetime


def verify_result(record: VerificationInput) -> VerificationResult:
    if record.forced_status not in {"VERIFIED", "ERROR", "INSUFFICIENT", "UNSTABLE"}:
        raise ValueError("invalid verification status")
    checks: dict[str, bool] = {"value": False, "unit": False, "evidence": False}
    if record.forced_status == "VERIFIED":
        try:
            checks["value"] = Decimal(str(record.actual.get("value"))) == Decimal(str(record.expected["value"]))
        except (InvalidOperation, KeyError):
            checks["value"] = False
        checks["unit"] = record.actual.get("unit") == record.expected.get("unit")
        evidence = record.actual.get("evidence")
        required = record.expected.get("required_evidence", [])
        checks["evidence"] = isinstance(evidence, list) and isinstance(required, list) and all(item in evidence for item in required if isinstance(item, str))
        outcome = "PASS" if all(checks.values()) else "FAIL"
    else:
        outcome = "UNKNOWN"
    return VerificationResult(
        attempt_id=record.attempt_id,
        verifier_version=record.verifier_version,
        status=record.forced_status,
        outcome=outcome,
        checks=checks,
        checks_for_model={"verified": record.forced_status == "VERIFIED"},
        verified_at=record.verified_at,
    )
