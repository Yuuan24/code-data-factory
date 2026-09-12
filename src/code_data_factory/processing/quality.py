"""Independent quality dimensions and immutable decision ledger rows."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes
from code_data_factory.contracts.tasks import ExternalDemonstration, ReplayCapability
from code_data_factory.contracts.verification import (
    EligibilityAction,
    EligibilityDecision,
    Outcome,
    VerificationRecord,
    VerificationStatus,
)

EXTERNAL_PUBLICATION_REVIEW_CHECKS = frozenset(
    {
        "source_identity",
        "upstream_tool_definition",
        "message_context",
        "target_answer_mapping",
        "split_registration",
        "sensitive_review",
    }
)


@dataclass(frozen=True)
class QualityDecision:
    decision_id: str
    subject_id: str
    action: str
    reason_codes: tuple[str, ...]
    policy_version: str
    parent_decision_id: str | None = None
    reliable_error_fragment: bool = False


@dataclass(frozen=True)
class QualityResult:
    decisions: list[QualityDecision]
    accepted_attempt_ids: list[str]
    quarantined_attempt_ids: list[str]
    rejected_attempt_ids: list[str]


def _eligibility_decision(
    *,
    demonstration_id: str,
    policy_version: str,
    action: EligibilityAction,
    reason_codes: tuple[str, ...],
    demonstration: ExternalDemonstration | None = None,
) -> EligibilityDecision:
    identifier = sha256_bytes(
        canonical_json_bytes(
            {
                "demonstration_id": demonstration_id,
                "policy_version": policy_version,
                "action": action.value,
                "reason_codes": reason_codes,
            }
        )
    )
    return EligibilityDecision(
        decision_id=f"eligibility-{identifier[:16]}",
        demonstration_id=demonstration_id,
        policy_version=policy_version,
        action=action,
        reason_codes=reason_codes,
        evidence_refs=[] if demonstration is None else [demonstration.upstream_task_ref],
        review_checks=(
            ()
            if demonstration is None
            else (
                "source_identity",
                "upstream_tool_definition",
                "message_context",
                "target_answer_mapping",
            )
        ),
        replay_capability=(
            demonstration.replay_capability
            if demonstration is not None
            else ReplayCapability.UNKNOWN
        ),
        upstream_synthetic_status=(
            demonstration.upstream_synthetic_status if demonstration is not None else None
        ),
    )


def assess_external_eligibility(
    demonstration: ExternalDemonstration | dict[str, Any], *, policy_version: str
) -> EligibilityDecision:
    """Admit external data from immutable evidence without executing it locally."""

    payload = (
        demonstration.model_dump(mode="python")
        if isinstance(demonstration, ExternalDemonstration)
        else demonstration
    )
    demonstration_id = str(payload.get("demonstration_id", "<unknown>"))
    if not payload.get("upstream_tool_bundle_ref"):
        return _eligibility_decision(
            demonstration_id=demonstration_id,
            policy_version=policy_version,
            action=EligibilityAction.REJECT,
            reason_codes=("MISSING_TOOL_DEFINITION",),
        )
    if not payload.get("message_refs"):
        return _eligibility_decision(
            demonstration_id=demonstration_id,
            policy_version=policy_version,
            action=EligibilityAction.REJECT,
            reason_codes=("MISSING_MESSAGE_CONTEXT",),
        )
    try:
        normalized = ExternalDemonstration.model_validate(payload)
    except ValueError:
        return _eligibility_decision(
            demonstration_id=demonstration_id,
            policy_version=policy_version,
            action=EligibilityAction.REJECT,
            reason_codes=("MALFORMED_EXTERNAL_DEMONSTRATION",),
        )
    if normalized.source_origin in {"PROJECT_SAMPLING", "MODEL_GENERATION"}:
        return _eligibility_decision(
            demonstration_id=normalized.demonstration_id,
            policy_version=policy_version,
            action=EligibilityAction.REJECT,
            reason_codes=("PROJECT_SAMPLING_INGRESS",),
            demonstration=normalized,
        )
    return _eligibility_decision(
        demonstration_id=normalized.demonstration_id,
        policy_version=policy_version,
        action=EligibilityAction.ACCEPT,
        reason_codes=("COMPLETE_EXTERNAL_DEMONSTRATION",),
        demonstration=normalized,
    )


def repair_external_demonstration(
    demonstration: ExternalDemonstration,
    *,
    demonstration_id: str,
    repair_rule_ref: Any,
) -> ExternalDemonstration:
    """Create a new deterministic repair record without changing its parent."""

    return demonstration.model_copy(
        update={
            "demonstration_id": demonstration_id,
            "parent_demonstration_id": demonstration.demonstration_id,
            "repair_rule_ref": repair_rule_ref,
            "eligibility_decision_ref": None,
        }
    )


def _decision(
    subject_id: str,
    action: str,
    reasons: tuple[str, ...],
    policy_version: str,
    *,
    parent_decision_id: str | None = None,
    reliable_error_fragment: bool = False,
) -> QualityDecision:
    identifier = sha256_bytes(
        canonical_json_bytes(
            {
                "subject_id": subject_id,
                "action": action,
                "reasons": reasons,
                "policy_version": policy_version,
                "parent_decision_id": parent_decision_id,
            }
        )
    )
    return QualityDecision(
        decision_id=f"decision-{identifier[:16]}",
        subject_id=subject_id,
        action=action,
        reason_codes=reasons,
        policy_version=policy_version,
        parent_decision_id=parent_decision_id,
        reliable_error_fragment=reliable_error_fragment,
    )


def repair_decision(
    *, old_decision: QualityDecision, replacement_subject_id: str, policy_version: str
) -> QualityDecision:
    """Record repair as a new subject; old rejected/unknown evidence stays immutable."""

    if not replacement_subject_id or replacement_subject_id == old_decision.subject_id:
        raise ValueError("repair requires a distinct replacement subject")
    return _decision(
        replacement_subject_id,
        "REPAIR",
        ("REPLACEMENT_CREATED",),
        policy_version,
        parent_decision_id=old_decision.decision_id,
    )


def write_quality_ledger(decisions: list[QualityDecision], *, output_dir: Path) -> Path:
    """Write an immutable, recomputable decision ledger with stable identifiers."""

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "quality_decisions.parquet"
    pq.write_table(pa.Table.from_pylist([decision.__dict__ for decision in decisions]), path)
    (output_dir / "quality_decisions.json").write_bytes(
        canonical_json_bytes({"decisions": [decision.__dict__ for decision in decisions]})
    )
    return path


def decide_quality(
    *,
    attempts: list[dict[str, str]],
    verifications: Sequence[VerificationRecord | dict[str, Any]],
    duplicate_representatives: dict[str, str],
    policy_version: str,
) -> QualityResult:
    """Accept only independently verified pass records; preserve unknowns as quarantine."""

    by_attempt = {
        record.attempt_id if isinstance(record, VerificationRecord) else str(record["attempt_id"]): record
        for record in verifications
    }
    decisions: list[QualityDecision] = []
    accepted: list[str] = []
    quarantined: list[str] = []
    rejected: list[str] = []
    for attempt in attempts:
        attempt_id = attempt["attempt_id"]
        verification = by_attempt.get(attempt_id)
        if verification is None:
            decision = _decision(attempt_id, "QUARANTINE", ("MISSING_VERIFICATION",), policy_version)
            quarantined.append(attempt_id)
        else:
            status = verification.status if isinstance(verification, VerificationRecord) else VerificationStatus(str(verification["status"]))
            outcome = verification.outcome if isinstance(verification, VerificationRecord) else Outcome(str(verification["outcome"]))
            if status is not VerificationStatus.VERIFIED or outcome is Outcome.UNKNOWN:
                decision = _decision(attempt_id, "QUARANTINE", ("VERIFICATION_UNKNOWN",), policy_version)
                quarantined.append(attempt_id)
            elif outcome is Outcome.FAIL:
                decision = _decision(attempt_id, "REJECT", ("VERIFICATION_FAIL",), policy_version, reliable_error_fragment=True)
                rejected.append(attempt_id)
            elif duplicate_representatives.get(attempt_id) != attempt_id:
                decision = _decision(attempt_id, "REJECT", ("DUPLICATE_NON_REPRESENTATIVE",), policy_version)
                rejected.append(attempt_id)
            else:
                decision = _decision(attempt_id, "ACCEPT", ("VERIFIED_PASS",), policy_version)
                accepted.append(attempt_id)
        decisions.append(decision)
    return QualityResult(
        decisions=decisions,
        accepted_attempt_ids=accepted,
        quarantined_attempt_ids=quarantined,
        rejected_attempt_ids=rejected,
    )
