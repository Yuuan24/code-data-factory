from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_data_factory.contracts.experiments import BatchShape, ExperimentPlan, ExperimentStatus
from code_data_factory.datasets.batch_schedule import (
    BatchScheduleError,
    ScheduledExample,
    build_equal_schedule,
)


def _plan(*, preregistration_sha256: str, status: ExperimentStatus) -> ExperimentPlan:
    return ExperimentPlan(
        experiment_id="sft-main",
        revision=1,
        hypothesis="feedback selection improves the declared failure slice",
        target_data_difference="failure coverage",
        candidate_pool_version="pool-v1",
        recipes=("SFT-RandomMatched", "SFT-ClosedLoop"),
        seeds=(17, 29, 43),
        model={
            "model_id": "model",
            "model_revision": "rev",
            "tokenizer_revision": "tok",
            "template_sha256": "a" * 64,
            "thinking_mode": "disabled",
        },
        method="lora",
        method_selection_sha256="b" * 64,
        batch_shape=BatchShape(
            per_device_batch_size=1,
            gradient_accumulation_steps=1,
            max_context_tokens=64,
            precision="bf16",
        ),
        planned_loss_tokens=4,
        planned_optimizer_steps=2,
        input_compute_budget="two bf16 steps",
        evaluation_version="ToolTaskBench-v1",
        guardrails={"max_regression": 0.02},
        preregistration_sha256=preregistration_sha256,
        status=status,
    )


def test_frozen_plan_requires_two_recipes_three_seeds_and_its_own_hash() -> None:
    draft = _plan(preregistration_sha256="c" * 64, status=ExperimentStatus.DRAFT)
    registered = _plan(
        preregistration_sha256=draft.frozen_conditions_sha256, status=ExperimentStatus.PREREGISTERED
    )
    assert registered.frozen_conditions_sha256 == draft.frozen_conditions_sha256
    invalid = _plan(preregistration_sha256="c" * 64, status=ExperimentStatus.DRAFT).model_dump()
    invalid["seeds"] = (17, 17, 43)
    with pytest.raises(ValueError, match="three distinct seeds"):
        ExperimentPlan.model_validate(invalid)


def test_schedule_requires_equal_whole_targets_and_never_uses_test_or_padding(
    tmp_path: Path,
) -> None:
    random = [
        ScheduledExample("external-random", (1, 2), (False, True)),
        ScheduledExample("external-random-2", (1, 2), (False, True)),
    ]
    closed = [
        ScheduledExample("external-closed", (3, 4), (False, True)),
        ScheduledExample("external-closed-2", (3, 4), (False, True)),
    ]
    receipt = build_equal_schedule(
        random_examples=random,
        closed_loop_examples=closed,
        batch_size=1,
        steps=2,
        max_context_tokens=8,
        output_path=tmp_path / "schedule.json",
    )
    assert receipt["effective_loss_tokens"] == 2
    assert receipt["no_target_padding"] is True
    assert receipt["equal_input_compute_budget"] is True
    assert receipt["fixed_context_tokens"] == 2
    assert receipt["padded_input_tokens_per_recipe"] == 4
    assert "test" not in json.dumps(receipt).lower()
    with pytest.raises(BatchScheduleError, match="exactly match"):
        build_equal_schedule(
            random_examples=random[:1],
            closed_loop_examples=[ScheduledExample("external-closed", (3, 4), (False, True, True))],
            batch_size=1,
            steps=1,
            max_context_tokens=8,
            output_path=tmp_path / "bad.json",
        )
