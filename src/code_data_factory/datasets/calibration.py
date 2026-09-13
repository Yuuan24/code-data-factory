"""Single-card method and two-recipe calibration gates."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import yaml

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_file
from code_data_factory.evaluation.interactive import run_evaluation
from code_data_factory.evaluation.local_model import LocalTransformersExecutor
from code_data_factory.evaluation.suites import build_tool_task_suite

from .batch_schedule import build_equal_schedule, load_sft_examples
from .training_adapter import execute_sft_run, release_cuda_memory


class CalibrationError(ValueError):
    """Calibration input is not a frozen, auditable SFT comparison."""


def _load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("calibration_version") != "sft-calibration-v1":
        raise CalibrationError("calibration config must freeze sft-calibration-v1")
    return value


def _model(config: dict[str, Any]) -> dict[str, str]:
    value = config.get("model")
    required = {
        "model_id",
        "model_revision",
        "tokenizer_revision",
        "template_sha256",
        "thinking_mode",
    }
    if (
        not isinstance(value, dict)
        or required - value.keys()
        or not all(isinstance(value[key], str) and value[key] for key in required)
    ):
        raise CalibrationError("calibration requires frozen model/template identity")
    return {key: value[key] for key in required}


def _recipe_rows(config: dict[str, Any], *, examples_path: Path) -> tuple[list[Any], list[Any]]:
    recipes = config.get("calibration_recipes")
    if not isinstance(recipes, dict):
        raise CalibrationError("calibration requires frozen recipe selections")
    values: dict[str, list[Any]] = {}
    for name in ("random_matched", "closed_loop"):
        selected = recipes.get(name)
        if (
            not isinstance(selected, list)
            or not selected
            or not all(isinstance(item, str) and item for item in selected)
        ):
            raise CalibrationError(
                f"calibration recipe {name} must contain stable demonstration IDs"
            )
        values[name] = load_sft_examples(examples_path, selected_ids=set(selected))
    return values["random_matched"], values["closed_loop"]


def _interaction_config(config: dict[str, Any]) -> tuple[Path, tuple[str, ...], int, int]:
    value = config.get("calibration_interaction")
    if not isinstance(value, dict):
        raise CalibrationError("calibration requires a frozen interaction probe")
    suite, task_ids = value.get("suite_config"), value.get("development_task_ids")
    max_calls, max_tokens = value.get("max_model_calls"), value.get("max_completion_tokens")
    if (
        not isinstance(suite, str)
        or not isinstance(task_ids, list)
        or not task_ids
        or not all(isinstance(item, str) and item for item in task_ids)
        or len(set(task_ids)) != len(task_ids)
        or not isinstance(max_calls, int)
        or max_calls < 1
        or not isinstance(max_tokens, int)
        or max_tokens < 1
    ):
        raise CalibrationError("calibration interaction probe is invalid")
    return Path(suite), tuple(task_ids), max_calls, max_tokens


def _run_interaction_probe(
    *,
    model: dict[str, str],
    suite_config: Path,
    task_ids: tuple[str, ...],
    max_calls: int,
    max_tokens: int,
    checkpoint: Path,
    output_dir: Path,
) -> dict[str, object]:
    profile = {
        "kind": "LOCAL_TRANSFORMERS",
        **model,
        "adapter_checkpoint": str(checkpoint.resolve()),
        "max_model_calls": max_calls,
        "max_completion_tokens": max_tokens,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_path = output_dir / "model_profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=True), encoding="utf-8")
    suite_path = build_tool_task_suite(suite_config, output_dir=output_dir / "suite")
    executor = LocalTransformersExecutor(profile_path)
    try:
        return run_evaluation(
            suite_manifest=suite_path,
            split="DEVELOPMENT",
            executor=executor,
            output_dir=output_dir,
            model_identity=executor.identity,
            task_ids=task_ids,
        )
    finally:
        executor.close()
        release_cuda_memory()


def run_calibration(*, config_path: Path, output_dir: Path) -> dict[str, object]:
    """First select a viable method, then measure each equal-budget recipe once."""
    config = _load_config(config_path)
    model = _model(config)
    suite_config, interaction_task_ids, max_calls, max_tokens = _interaction_config(config)
    source = config.get("sft_view")
    schedule = config.get("schedule")
    methods = config.get("method_order")
    if (
        not isinstance(source, str)
        or not isinstance(schedule, dict)
        or not isinstance(methods, list)
        or methods != ["full_finetune", "lora", "qlora"]
    ):
        raise CalibrationError(
            "calibration requires SFT view, batch schedule, and ordered full/LoRA/QLoRA methods"
        )
    batch_size_raw, steps_raw = schedule.get("batch_size"), schedule.get("optimizer_steps")
    max_context_raw = schedule.get("max_context_tokens")
    gradient_checkpointing = schedule.get("gradient_checkpointing")
    if (
        not isinstance(batch_size_raw, int)
        or not isinstance(steps_raw, int)
        or not isinstance(max_context_raw, int)
        or batch_size_raw < 1
        or steps_raw < 1
        or max_context_raw < 1
        or not isinstance(gradient_checkpointing, bool)
    ):
        raise CalibrationError("calibration schedule values must be positive integers")
    batch_size, steps, max_context = int(batch_size_raw), int(steps_raw), int(max_context_raw)
    examples_path = Path(source).resolve() if not Path(source).is_absolute() else Path(source)
    random_rows, closed_rows = _recipe_rows(config, examples_path=examples_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    schedule_path = output_dir / "schedule.json"
    plan = build_equal_schedule(
        random_examples=random_rows,
        closed_loop_examples=closed_rows,
        batch_size=batch_size,
        steps=steps,
        max_context_tokens=max_context,
        output_path=schedule_path,
    )
    selection_attempts: list[dict[str, object]] = []
    selected_method: str | None = None
    selected_run: dict[str, object] | None = None
    probe_rows = [random_rows[index % len(random_rows)] for index in range(batch_size * steps)]
    for method in methods:
        attempt_dir = output_dir / "method-gate" / method
        try:
            run = execute_sft_run(
                run_id=f"calibration-method-{method}",
                experiment_id="calibration-method-selection",
                recipe="method_probe",
                seed=11,
                dataset_id="external-calibration",
                model_identity=model,
                method=method,
                schedule_rows=probe_rows,
                planned_loss_tokens=sum(row.loss_tokens for row in probe_rows),
                optimizer_steps=steps,
                batch_size=batch_size,
                gradient_checkpointing=gradient_checkpointing,
                output_dir=attempt_dir,
            )
            runtime = json.loads(
                (attempt_dir / "training_runtime.json").read_text(encoding="utf-8")
            )
            free, total = runtime.get("gpu_free_bytes_after_reload"), runtime.get("gpu_total_bytes")
            margin = isinstance(free, int) and isinstance(total, int) and free / total >= 0.10
            selection_attempts.append(
                {
                    "method": method,
                    "status": "PASSED" if margin else "REJECTED",
                    "run_ref": str((attempt_dir / "training_run.json").relative_to(output_dir)),
                    "ten_percent_vram_margin": margin,
                }
            )
            if margin:
                selected_method, selected_run = method, run.model_dump(mode="json")
                break
        except Exception as error:  # noqa: BLE001 - retain every upstream method-gate failure.
            selection_attempts.append(
                {
                    "method": method,
                    "status": "REJECTED",
                    "reason": f"{type(error).__name__}: {error}",
                }
            )
        finally:
            release_cuda_memory()
    selection = {
        "kind": "single-card-method-selection",
        "config_sha256": sha256_file(config_path),
        "attempts": selection_attempts,
        "selected_method": selected_method,
        "selected_run": selected_run,
        "requirements": {
            "actual_backward_propagation": selected_method is not None,
            "finite_loss": selected_method is not None,
            "checkpoint_reload": selected_method is not None,
            "ten_percent_vram_margin": selected_method is not None,
        },
        "evidence_level": "EXECUTION_VALIDATED" if selected_method else "UNVERIFIED",
    }
    (output_dir / "method_selection.json").write_bytes(canonical_json_bytes(selection))
    if selected_method is None:
        return {"terminal_status": "GATE_FAILED", "method_selection": selection, "schedule": plan}
    effective_loss_tokens = plan.get("effective_loss_tokens")
    if not isinstance(effective_loss_tokens, int):
        raise CalibrationError("schedule lacks effective loss token count")
    recipe_runs: list[dict[str, object]] = []
    for name, rows in (
        (
            "SFT-RandomMatched",
            [random_rows[index % len(random_rows)] for index in range(batch_size * steps)],
        ),
        (
            "SFT-ClosedLoop",
            [closed_rows[index % len(closed_rows)] for index in range(batch_size * steps)],
        ),
    ):
        started = time.monotonic()
        try:
            run = execute_sft_run(
                run_id=f"calibration-{name}",
                experiment_id="calibration-two-recipe",
                recipe=name,
                seed=17,
                dataset_id="external-calibration",
                model_identity=model,
                method=selected_method,
                schedule_rows=rows,
                planned_loss_tokens=effective_loss_tokens,
                optimizer_steps=steps,
                batch_size=batch_size,
                gradient_checkpointing=gradient_checkpointing,
                output_dir=output_dir / "recipes" / name,
            )
        finally:
            release_cuda_memory()
        recipe_runs.append(
            {
                "recipe": name,
                "run": run.model_dump(mode="json"),
                "elapsed_seconds": round(time.monotonic() - started, 6),
            }
        )
    interaction_runs: list[dict[str, object]] = []
    for item in recipe_runs:
        recipe = item["recipe"]
        if not isinstance(recipe, str):
            raise CalibrationError("calibration recipe identifier is invalid")
        evaluation_dir = output_dir / "recipes" / recipe / "interaction"
        receipt = _run_interaction_probe(
            model=model,
            suite_config=suite_config,
            task_ids=interaction_task_ids,
            max_calls=max_calls,
            max_tokens=max_tokens,
            checkpoint=output_dir / "recipes" / recipe / "checkpoint",
            output_dir=evaluation_dir,
        )
        interaction_runs.append(
            {
                "recipe": recipe,
                "evaluation_ref": str((evaluation_dir / "evaluation_run.json").relative_to(output_dir)),
                "evaluation_sha256": sha256_file(evaluation_dir / "evaluation_run.json"),
                "fixed_denominator": receipt["fixed_denominator"],
                "unresolved_infrastructure_count": receipt["unresolved_infrastructure_count"],
            }
        )
    total_seconds = sum(
        float(item["elapsed_seconds"])
        for item in recipe_runs
        if isinstance(item["elapsed_seconds"], float)
    )
    manifest = {
        "kind": "two-recipe-single-seed-calibration",
        "terminal_status": "COMPLETED",
        "config_sha256": sha256_file(config_path),
        "method_selection_sha256": sha256_file(output_dir / "method_selection.json"),
        "schedule_sha256": plan["schedule_sha256"],
        "equal_effective_loss_tokens": effective_loss_tokens,
        "equal_optimizer_steps": steps,
        "batch_size": batch_size,
        "gradient_checkpointing": gradient_checkpointing,
        "recipe_runs": recipe_runs,
        "interaction_runs": interaction_runs,
        "throughput_loss_tokens_per_second": (2 * effective_loss_tokens) / total_seconds
        if total_seconds
        else None,
        "six_run_seconds_prediction": total_seconds * 3,
        "six_run_seconds_with_failure_reserve": total_seconds * 3 * 1.15,
        "failure_reserve_fraction": 0.15,
        "limitations": [
            "Calibration scores are not used for method or hyperparameter selection.",
            "This calibration contains only one feedback pair and cannot support confirmation attribution.",
            "Interaction checks use three frozen development tasks and are not formal model-value results.",
        ],
        "evidence_level": "EXECUTION_VALIDATED",
    }
    (output_dir / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    return manifest
