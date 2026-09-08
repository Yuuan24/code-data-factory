from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from code_data_factory.contracts.tasks import (
    AccessScope,
    ArtifactRef,
    Capabilities,
    CapabilityState,
    TaskPackage,
    TaskStatus,
    UsageScope,
)
from code_data_factory.contracts.trajectory import (
    ActorKind,
    Attempt,
    AttemptState,
    EndReason,
    EventType,
    Trajectory,
    TrajectoryEvent,
)
from code_data_factory.contracts.verification import Outcome, VerificationRecord, VerificationStatus


def ref(name: str, scope: AccessScope = AccessScope.MODEL_VISIBLE) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=name,
        uri=f"artifacts/{name}.json",
        sha256="a" * 64,
        byte_size=1,
        media_type="application/json",
        producer_run_id="run-1",
        access_scope=scope,
    )


def task(**overrides: object) -> TaskPackage:
    values: dict[str, object] = {
        "task_id": "task-1",
        "task_revision": "1",
        "source_record_ids": ["source-1"],
        "instruction_ref": ref("instruction"),
        "initial_resources_ref": ref("resources"),
        "tool_bundle_ref": ref("tools"),
        "environment_ref": ref("environment", AccessScope.INTERNAL),
        "verifier_spec_ref": ref("verifier", AccessScope.VERIFIER_PRIVATE),
        "expected_result_ref": ref("expected", AccessScope.VERIFIER_PRIVATE),
        "task_family": "lookup",
        "template_family_id": "template-1",
        "source_group_ids": ["source-group"],
        "derivation_root_ids": ["root-1"],
        "usage_scope": UsageScope.TRAIN,
        "split_group_id": "split-1",
        "split_policy_version": "1",
        "dependency_depth": 1,
        "tool_set": ["search_documents"],
        "interaction_budget_ref": ref("budget", AccessScope.INTERNAL),
        "initial_state_ref": ref("initial-state"),
        "capabilities": Capabilities(
            reset=CapabilityState.SUPPORTED, evidence_refs=[ref("capability", AccessScope.INTERNAL)]
        ),
        "status": TaskStatus.EXECUTABLE,
    }
    values.update(overrides)
    return TaskPackage.model_validate(values)


def test_task_rejects_private_reference_in_model_context() -> None:
    with pytest.raises(ValidationError, match="model-visible"):
        task(instruction_ref=ref("instruction", AccessScope.VERIFIER_PRIVATE))


def test_handwritten_contract_fixtures_cover_required_rejection_cases() -> None:
    fixtures = Path("tests/fixtures/contracts")
    expected = {
        "invalid_private_reference.json": "REJECT",
        "missing_tool_call.json": "REJECT",
        "multi_turn_attempt.json": "ACCEPT",
        "old_major_version.json": None,
        "out_of_order_events.json": "REJECT",
        "unknown_reward.json": None,
        "valid_task.json": None,
    }
    for name, outcome in expected.items():
        record = json.loads((fixtures / name).read_text(encoding="utf-8"))
        if outcome is not None:
            assert record["expected"] == outcome


def test_task_rejects_old_contract_major() -> None:
    with pytest.raises(ValidationError, match="major version 2"):
        task(contract_version="1.9.0")


def test_task_requires_initial_state_when_executable() -> None:
    with pytest.raises(ValidationError, match="initial_state_ref"):
        task(initial_state_ref=None)


def test_attempt_and_trajectory_keep_execution_state_separate_from_outcome() -> None:
    now = datetime.now(UTC)
    attempt = Attempt(
        attempt_id="attempt-1",
        task_id="task-1",
        task_revision="1",
        actor_kind=ActorKind.SCRIPTED_FIXTURE,
        harness_ref=ref("harness", AccessScope.INTERNAL),
        environment_ref=ref("environment", AccessScope.INTERNAL),
        preflight_ref=ref("preflight", AccessScope.INTERNAL),
        budget_ref=ref("budget", AccessScope.INTERNAL),
        started_at=now,
        finished_at=now,
        end_reason=EndReason.COMPLETED,
        state=AttemptState.SEALED,
    )
    trajectory = Trajectory(
        attempt=attempt,
        events=[
            TrajectoryEvent(
                event_id="request",
                attempt_id="attempt-1",
                seq=0,
                event_type=EventType.MODEL_REQUEST,
                timestamp=now,
                model_call_id="call-1",
                origin="fixture",
            ),
            TrajectoryEvent(
                event_id="output",
                attempt_id="attempt-1",
                seq=1,
                event_type=EventType.MODEL_OUTPUT,
                timestamp=now,
                model_call_id="call-1",
                origin="fixture",
            ),
        ],
    )
    assert trajectory.attempt.end_reason is EndReason.COMPLETED
    verification = VerificationRecord(
        verification_id="verification-1",
        attempt_id="attempt-1",
        evidence_manifest_ref=ref("evidence"),
        verifier_version="1",
        check_results_ref=ref("checks"),
        status=VerificationStatus.VERIFIED,
        outcome=Outcome.FAIL,
        verified_at=now,
    )
    assert verification.outcome is Outcome.FAIL


def test_tool_result_requires_corresponding_call() -> None:
    now = datetime.now(UTC)
    attempt = Attempt(
        attempt_id="attempt-1",
        task_id="task-1",
        task_revision="1",
        actor_kind=ActorKind.SCRIPTED_FIXTURE,
        harness_ref=ref("harness"),
        environment_ref=ref("environment"),
        preflight_ref=ref("preflight"),
        budget_ref=ref("budget"),
        started_at=now,
    )
    with pytest.raises(ValidationError, match="tool result must reference"):
        Trajectory(
            attempt=attempt,
            events=[
                TrajectoryEvent(
                    event_id="result",
                    attempt_id="attempt-1",
                    seq=0,
                    event_type=EventType.TOOL_RESULT,
                    timestamp=now,
                    tool_call_id="missing",
                    origin="fixture",
                )
            ],
        )


def test_events_must_be_in_sequence_order() -> None:
    now = datetime.now(UTC)
    attempt = Attempt(
        attempt_id="attempt-1",
        task_id="task-1",
        task_revision="1",
        actor_kind=ActorKind.SCRIPTED_FIXTURE,
        harness_ref=ref("harness"),
        environment_ref=ref("environment"),
        preflight_ref=ref("preflight"),
        budget_ref=ref("budget"),
        started_at=now,
    )
    with pytest.raises(ValidationError, match="strictly increasing"):
        Trajectory(
            attempt=attempt,
            events=[
                TrajectoryEvent(
                    event_id="later",
                    attempt_id="attempt-1",
                    seq=1,
                    event_type=EventType.OBSERVATION,
                    timestamp=now,
                    origin="fixture",
                ),
                TrajectoryEvent(
                    event_id="earlier",
                    attempt_id="attempt-1",
                    seq=0,
                    event_type=EventType.OBSERVATION,
                    timestamp=now,
                    origin="fixture",
                ),
            ],
        )
