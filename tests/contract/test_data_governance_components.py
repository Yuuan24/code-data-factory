from __future__ import annotations

from datetime import UTC, datetime

from code_data_factory.contracts.tasks import AccessScope, ArtifactRef
from code_data_factory.contracts.verification import Outcome, VerificationRecord, VerificationStatus
from code_data_factory.processing.dedup import deduplicate_tasks
from code_data_factory.processing.quality import decide_quality


def _ref(name: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=name,
        uri=f"artifacts/{name}.json",
        sha256="a" * 64,
        byte_size=1,
        media_type="application/json",
        producer_run_id="test",
        access_scope=AccessScope.INTERNAL,
    )


def test_dedup_uses_semantic_projection_not_tool_sequence() -> None:
    result = deduplicate_tasks(
        [
            {
                "task_id": "same-a",
                "task_family": "lookup",
                "instruction": "What is one metre in centimetres?",
                "facts": {"metre": 100, "unit": "cm"},
                "tool_sequence": ["search_documents", "read_document"],
            },
            {
                "task_id": "same-b",
                "task_family": "lookup",
                "instruction": "What is one metre in centimetres?",
                "facts": {"metre": 100, "unit": "cm"},
                "tool_sequence": ["read_document"],
            },
            {
                "task_id": "different-value",
                "task_family": "lookup",
                "instruction": "What is one metre in centimetres?",
                "facts": {"metre": 1000, "unit": "mm"},
                "tool_sequence": ["search_documents", "read_document"],
            },
        ],
        num_perm=64,
        threshold=0.5,
        seed=7,
    )

    assert result.representatives == {"same-a": "same-a", "same-b": "same-a", "different-value": "different-value"}
    assert ("same-a", "same-b") in result.candidate_pairs


def test_quality_decisions_consume_verification_records_and_keep_unknown_out_of_accepted_pool() -> None:
    now = datetime.now(UTC)
    verified = VerificationRecord(
        verification_id="verify-pass",
        attempt_id="attempt-pass",
        evidence_manifest_ref=_ref("evidence"),
        verifier_version="v1",
        check_results_ref=_ref("checks"),
        status=VerificationStatus.VERIFIED,
        outcome=Outcome.PASS,
        verified_at=now,
    )
    unknown = VerificationRecord(
        verification_id="verify-unknown",
        attempt_id="attempt-unknown",
        evidence_manifest_ref=_ref("evidence-unknown"),
        verifier_version="v1",
        check_results_ref=_ref("checks-unknown"),
        status=VerificationStatus.INSUFFICIENT,
        outcome=Outcome.UNKNOWN,
        verified_at=now,
    )

    result = decide_quality(
        attempts=[{"attempt_id": "attempt-pass"}, {"attempt_id": "attempt-unknown"}],
        verifications=[verified, unknown],
        duplicate_representatives={"attempt-pass": "attempt-pass", "attempt-unknown": "attempt-unknown"},
        policy_version="quality-v1",
    )

    assert result.accepted_attempt_ids == ["attempt-pass"]
    assert result.quarantined_attempt_ids == ["attempt-unknown"]
    assert result.decisions[1].reason_codes == ("VERIFICATION_UNKNOWN",)
