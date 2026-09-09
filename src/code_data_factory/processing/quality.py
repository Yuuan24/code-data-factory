"""Independent quality dimensions and immutable decision ledger rows."""

from __future__ import annotations

from dataclasses import dataclass

from code_data_factory.contracts.verification import Outcome, VerificationRecord, VerificationStatus


@dataclass(frozen=True)
class QualityDecision:
    subject_id: str
    action: str
    reason_codes: tuple[str, ...]
    policy_version: str


@dataclass(frozen=True)
class QualityResult:
    decisions: list[QualityDecision]
    accepted_attempt_ids: list[str]
    quarantined_attempt_ids: list[str]
    rejected_attempt_ids: list[str]


def decide_quality(
    *,
    attempts: list[dict[str, str]],
    verifications: list[VerificationRecord],
    duplicate_representatives: dict[str, str],
    policy_version: str,
) -> QualityResult:
    """Accept only independently verified pass records; preserve unknowns as quarantine."""

    by_attempt = {record.attempt_id: record for record in verifications}
    decisions: list[QualityDecision] = []
    accepted: list[str] = []
    quarantined: list[str] = []
    rejected: list[str] = []
    for attempt in attempts:
        attempt_id = attempt["attempt_id"]
        verification = by_attempt.get(attempt_id)
        if verification is None:
            decision = QualityDecision(attempt_id, "QUARANTINE", ("MISSING_VERIFICATION",), policy_version)
            quarantined.append(attempt_id)
        elif verification.status is not VerificationStatus.VERIFIED or verification.outcome is Outcome.UNKNOWN:
            decision = QualityDecision(attempt_id, "QUARANTINE", ("VERIFICATION_UNKNOWN",), policy_version)
            quarantined.append(attempt_id)
        elif verification.outcome is Outcome.FAIL:
            decision = QualityDecision(attempt_id, "REJECT", ("VERIFICATION_FAIL",), policy_version)
            rejected.append(attempt_id)
        elif duplicate_representatives.get(attempt_id) != attempt_id:
            decision = QualityDecision(attempt_id, "REJECT", ("DUPLICATE_NON_REPRESENTATIVE",), policy_version)
            rejected.append(attempt_id)
        else:
            decision = QualityDecision(attempt_id, "ACCEPT", ("VERIFIED_PASS",), policy_version)
            accepted.append(attempt_id)
        decisions.append(decision)
    return QualityResult(
        decisions=decisions,
        accepted_attempt_ids=accepted,
        quarantined_attempt_ids=quarantined,
        rejected_attempt_ids=rejected,
    )
