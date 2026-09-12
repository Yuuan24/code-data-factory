from __future__ import annotations

import pytest

from code_data_factory.contracts.tasks import (
    AccessScope,
    ArtifactRef,
    ExternalDemonstration,
    ReplayCapability,
    UsageScope,
)
from code_data_factory.contracts.verification import EligibilityAction
from code_data_factory.processing.quality import (
    assess_external_eligibility,
    repair_external_demonstration,
)


def _ref(name: str, *, scope: AccessScope = AccessScope.MODEL_VISIBLE) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=name,
        uri=f"data/normalized/{name}.json",
        sha256="a" * 64,
        byte_size=1,
        media_type="application/json",
        producer_run_id="external-import",
        access_scope=scope,
    )


def _demonstration(**overrides: object) -> ExternalDemonstration:
    values: dict[str, object] = {
        "demonstration_id": "toucan:example-1",
        "source_record_id": "toucan:example-1",
        "upstream_task_ref": _ref("task"),
        "upstream_tool_bundle_ref": _ref("tools"),
        "message_refs": [_ref("message-0"), _ref("message-1")],
        "call_result_refs": [_ref("result-0")],
        "answer_ref": _ref("answer"),
        "upstream_synthetic_status": "source_reported_success",
        "replay_capability": ReplayCapability.UNSUPPORTED,
        "usage_scope": UsageScope.TRAIN,
        "source_origin": "PUBLIC_ORIGINAL",
    }
    values.update(overrides)
    return ExternalDemonstration.model_validate(values)


def test_complete_non_replayable_external_demonstration_can_be_admitted() -> None:
    decision = assess_external_eligibility(
        _demonstration(), policy_version="external-sft-v1"
    )

    assert decision.action is EligibilityAction.ACCEPT
    assert decision.replay_capability is ReplayCapability.UNSUPPORTED
    assert not hasattr(decision, "outcome")
    assert not hasattr(decision, "reward")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("upstream_tool_bundle_ref", None, "MISSING_TOOL_DEFINITION"),
        ("message_refs", [], "MISSING_MESSAGE_CONTEXT"),
    ],
)
def test_missing_external_tool_definition_or_context_is_rejected(
    field: str, value: object, reason: str
) -> None:
    payload = _demonstration().model_dump(mode="python")
    payload[field] = value

    decision = assess_external_eligibility(payload, policy_version="external-sft-v1")

    assert decision.action is EligibilityAction.REJECT
    assert reason in decision.reason_codes


def test_source_reported_status_does_not_become_project_pass_or_reward() -> None:
    decision = assess_external_eligibility(
        _demonstration(upstream_synthetic_status="passed"),
        policy_version="external-sft-v1",
    )

    assert decision.action is EligibilityAction.ACCEPT
    assert decision.upstream_synthetic_status == "passed"
    assert "PASS" not in decision.model_dump_json()
    assert "reward" not in decision.model_dump_json()


def test_deterministic_repair_creates_a_new_external_demonstration_with_parent_chain() -> None:
    original = _demonstration()
    repaired = repair_external_demonstration(
        original,
        demonstration_id="toucan:example-1:repair-1",
        repair_rule_ref=_ref("repair-unique-call-link", scope=AccessScope.INTERNAL),
    )

    assert repaired.demonstration_id != original.demonstration_id
    assert repaired.parent_demonstration_id == original.demonstration_id
    assert repaired.repair_rule_ref is not None


def test_project_sampling_cannot_be_admitted_to_external_training() -> None:
    decision = assess_external_eligibility(
        _demonstration(source_origin="PROJECT_SAMPLING"),
        policy_version="external-sft-v1",
    )

    assert decision.action is EligibilityAction.REJECT
    assert "PROJECT_SAMPLING_INGRESS" in decision.reason_codes
