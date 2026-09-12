from __future__ import annotations

import pytest

from code_data_factory.interaction.sampling_records import (
    SamplingAttachment,
    SamplingRecordError,
)


def _actual_attachment() -> dict[str, object]:
    return {
        "attempt_id": "attempt-1",
        "task_id": "task-1",
        "provenance": "ACTUAL_TRAINER_SAMPLER",
        "runner_kind": "TRL_GRPO_TRAINER",
        "policy": {
            "model_id": "Qwen/Qwen3-8B",
            "model_revision": "frozen-revision",
            "tokenizer_revision": "frozen-tokenizer",
            "template_sha256": "a" * 64,
            "thinking_mode": "disabled",
        },
        "input_token_ids": [1, 2, 3],
        "output_token_ids": [4, 5],
        "output_mask": [1, 1],
        "optimizer_step_count": 0,
        "sampling_status": "COMPLETED",
        "cost": {
            "gpu_seconds": 1.0,
            "provider_charge_cny": None,
            "unavailable_reason": "fixture has no platform billing record",
        },
    }


def test_training_consumer_requires_actual_tokens_masks_and_policy_identity() -> None:
    attachment = SamplingAttachment.model_validate(_actual_attachment())

    assert attachment.provenance == "ACTUAL_TRAINER_SAMPLER"
    assert attachment.output_mask == (1, 1)
    assert attachment.optimizer_step_count == 0


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("provenance", "SCRIPTED_FIXTURE", "actual trainer sampler"),
        ("output_mask", [1], "same length"),
        ("optimizer_step_count", 1, "must not update"),
        ("input_token_ids", [], "input token ids"),
    ],
)
def test_training_consumer_rejects_non_actual_or_incomplete_sampling_evidence(
    field: str, value: object, message: str
) -> None:
    payload = _actual_attachment()
    payload[field] = value

    with pytest.raises((SamplingRecordError, ValueError), match=message):
        SamplingAttachment.model_validate(payload)


def test_failed_real_sampling_keeps_the_actual_empty_output_instead_of_a_fake_trajectory() -> None:
    payload = _actual_attachment()
    payload.update(
        {
            "output_token_ids": [],
            "output_mask": [],
            "sampling_status": "FAILED",
            "failure": {"kind": "MODEL_ERROR", "message": "generation interrupted"},
        }
    )

    attachment = SamplingAttachment.model_validate(payload)

    assert attachment.sampling_status == "FAILED"
    assert attachment.output_token_ids == ()
