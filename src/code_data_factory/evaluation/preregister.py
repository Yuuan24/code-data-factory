"""Freeze the analysis rules for the controlled SFT comparison before training."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_file
from code_data_factory.contracts.experiments import BatchShape, ExperimentPlan, ExperimentStatus


class PreregistrationError(ValueError):
    """The proposed formal comparison is not completely frozen."""


def _mapping(value: object, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise PreregistrationError(f"preregistration requires {name}")
    return value


def _load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    config = _mapping(value, name="a mapping configuration")
    if config.get("preregistration_version") != "sft-main-preregister-v1":
        raise PreregistrationError("preregistration config must freeze sft-main-preregister-v1")
    return config


def _load_calibration(path: Path, *, expected_method: str) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        selection = json.loads((path.parent / "method_selection.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PreregistrationError("preregistration requires a readable completed calibration") from error
    if not isinstance(manifest, dict) or not isinstance(selection, dict):
        raise PreregistrationError("calibration evidence must contain objects")
    if (
        manifest.get("kind") != "two-recipe-single-seed-calibration"
        or manifest.get("terminal_status") != "COMPLETED"
        or manifest.get("evidence_level") != "EXECUTION_VALIDATED"
        or manifest.get("method_selection_sha256") != sha256_file(path.parent / "method_selection.json")
        or selection.get("selected_method") != expected_method
        or selection.get("evidence_level") != "EXECUTION_VALIDATED"
    ):
        raise PreregistrationError("calibration does not prove the configured selected method")
    return manifest


def _require_exact(value: object, *, name: str, expected: object) -> None:
    if value != expected:
        raise PreregistrationError(f"preregistration {name} must be fixed to {expected!r}")


def _plan_from_config(
    config: dict[str, Any], *, calibration_sha256: str, method_selection_sha256: str
) -> ExperimentPlan:
    recipes = config.get("recipes")
    seeds = config.get("seeds")
    model = _mapping(config.get("model"), name="a frozen model/template identity")
    schedule = _mapping(config.get("schedule"), name="an equal-budget schedule")
    analysis = _mapping(config.get("analysis"), name="an analysis rule")
    matching = _mapping(config.get("matching"), name="a matching rule")
    tool_protocol = _mapping(config.get("tool_protocol"), name="a tool protocol")
    exposure_budget = _mapping(config.get("exposure_budget"), name="an exposure budget")
    test_unlock_rule = _mapping(config.get("test_unlock_rule"), name="a test unlock rule")
    guardrails = _mapping(config.get("guardrails"), name="guardrails")
    if recipes != ["SFT-RandomMatched", "SFT-ClosedLoop"]:
        raise PreregistrationError("preregistration requires the declared random and closed-loop recipes")
    if seeds != [17, 29, 43]:
        raise PreregistrationError("preregistration requires seeds 17, 29, and 43")
    _require_exact(analysis.get("minimum_connected_groups"), name="minimum_connected_groups", expected=20)
    _require_exact(analysis.get("paired_bootstrap_resamples"), name="paired_bootstrap_resamples", expected=10000)
    if not isinstance(analysis.get("paired_bootstrap_seed"), int):
        raise PreregistrationError("preregistration requires a fixed paired bootstrap seed")
    _require_exact(analysis.get("practical_effect_pp"), name="practical_effect_pp", expected=2.0)
    _require_exact(matching.get("tolerance"), name="matching tolerance", expected="exact")
    if "failure_types" not in matching.get("excluded_fields", []):
        raise PreregistrationError("the target data difference must not be matched away")
    _require_exact(test_unlock_rule.get("enabled"), name="test unlock", expected=False)
    _require_exact(test_unlock_rule.get("single_use"), name="test unlock single_use", expected=True)
    _require_exact(exposure_budget.get("formal_training_runs"), name="formal_training_runs", expected=6)
    if not isinstance(schedule.get("batch_shape"), dict):
        raise PreregistrationError("preregistration schedule requires a batch shape")
    if not all(isinstance(schedule.get(key), int) and schedule[key] > 0 for key in ("planned_loss_tokens", "optimizer_steps")):
        raise PreregistrationError("preregistration schedule requires positive loss tokens and steps")
    draft = ExperimentPlan(
        experiment_id=str(config["experiment_id"]),
        revision=int(config["revision"]),
        hypothesis=str(config["hypothesis"]),
        target_data_difference=str(config["target_data_difference"]),
        candidate_pool_version=str(config["candidate_pool_version"]),
        recipes=tuple(recipes),
        seeds=tuple(seeds),
        model={str(key): str(value) for key, value in model.items()},
        method=str(config["method"]),
        method_selection_sha256=method_selection_sha256,
        batch_shape=BatchShape.model_validate(schedule["batch_shape"]),
        planned_loss_tokens=int(schedule["planned_loss_tokens"]),
        planned_optimizer_steps=int(schedule["optimizer_steps"]),
        input_compute_budget=str(schedule["input_compute_budget"]),
        evaluation_version=str(config["evaluation_version"]),
        matching=matching,
        tool_protocol=tool_protocol,
        exposure_budget=exposure_budget,
        test_unlock_rule=test_unlock_rule,
        guardrails={**guardrails, "analysis": analysis},
        calibration_manifest_sha256=calibration_sha256,
        preregistration_sha256="0" * 64,
    )
    return ExperimentPlan.model_validate(
        {
            **draft.model_dump(mode="json"),
            "preregistration_sha256": draft.frozen_conditions_sha256,
            "status": ExperimentStatus.PREREGISTERED,
        }
    )


def preregister_experiment(
    *, config_path: Path, calibration_path: Path, output_dir: Path
) -> dict[str, object]:
    """Write an immutable plan; this grants neither training nor final-test access."""
    config = _load_config(config_path)
    method = config.get("method")
    if not isinstance(method, str) or not method:
        raise PreregistrationError("preregistration requires the selected method")
    calibration = _load_calibration(calibration_path, expected_method=method)
    plan = _plan_from_config(
        config,
        calibration_sha256=sha256_file(calibration_path),
        method_selection_sha256=str(calibration["method_selection_sha256"]),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = output_dir / "experiment_plan.json"
    plan_path.write_bytes(canonical_json_bytes(plan.model_dump(mode="json")))
    receipt = {
        "kind": "sft-main-preregistration",
        "terminal_status": "PREREGISTERED",
        "evidence_level": "SOFTWARE_VALIDATED",
        "config_sha256": sha256_file(config_path),
        "calibration_manifest_sha256": sha256_file(calibration_path),
        "calibration_method": method,
        "calibration_schedule_sha256": calibration.get("schedule_sha256"),
        "experiment_plan_sha256": sha256_file(plan_path),
        "training_runs": 6,
        "minimum_connected_groups": 20,
        "paired_bootstrap_resamples": 10000,
        "test_unlocked": False,
        "limitations": [
            "This registers analysis conditions only; no formal training run has started.",
            "Final test remains locked until T078 freezes the released views and schedule.",
        ],
    }
    (output_dir / "preregistration_receipt.json").write_bytes(canonical_json_bytes(receipt))
    return receipt


def validate_preregistered_run_request(*, plan_path: Path, recipe: str, seed: int) -> ExperimentPlan:
    """Validate a future T079 run request without starting a training process."""
    try:
        plan = ExperimentPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PreregistrationError("experiment run requires a valid preregistered plan") from error
    if plan.status is not ExperimentStatus.PREREGISTERED:
        raise PreregistrationError("experiment run requires a preregistered plan")
    if recipe not in plan.recipes or seed not in plan.seeds:
        raise PreregistrationError("experiment run recipe and seed must be declared by the preregistered plan")
    return plan
