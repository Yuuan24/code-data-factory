"""Freeze external SFT views and cost evidence before formal training."""

from __future__ import annotations

import json
from importlib import metadata
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_file
from code_data_factory.contracts.experiments import ExperimentPlan, ExperimentStatus
from code_data_factory.datasets.batch_schedule import build_equal_schedule, load_sft_examples


class FormalizationError(ValueError):
    """Formal SFT inputs do not meet the preregistered comparison contract."""


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FormalizationError(f"cannot read {path}") from error
    if not isinstance(value, dict):
        raise FormalizationError(f"{path.name} must be an object")
    return value


def _config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FormalizationError("formalization config must be an object")
    return value


def _views(config: dict[str, Any]) -> dict[str, list[str]]:
    value = config.get("formal_recipe_views")
    if not isinstance(value, dict):
        raise FormalizationError("formalization requires declared recipe views")
    result: dict[str, list[str]] = {}
    for key, recipe in (("SFT-RandomMatched", "random_matched"), ("SFT-ClosedLoop", "closed_loop")):
        ids = value.get(recipe)
        if (
            not isinstance(ids, list)
            or not ids
            or not all(isinstance(item, str) and item for item in ids)
        ):
            raise FormalizationError(f"formalization requires stable {recipe} ids")
        result[key] = list(ids)
    return result


def _validate_membership(
    membership_path: Path, selected_ids: set[str]
) -> dict[str, dict[str, Any]]:
    try:
        rows = json.loads(membership_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FormalizationError("formalization requires readable external membership") from error
    if not isinstance(rows, list):
        raise FormalizationError("external membership must be a list")
    selected = {
        str(row.get("demonstration_id")): row
        for row in rows
        if isinstance(row, dict) and row.get("demonstration_id") in selected_ids
    }
    if set(selected) != selected_ids:
        raise FormalizationError(
            "formal views contain a demonstration absent from external membership"
        )
    for item in selected.values():
        origin = item.get("source_origin")
        if (
            origin not in {"PUBLIC_ORIGINAL", "DERIVED"}
            or item.get("eligibility_action") != "ACCEPT"
        ):
            raise FormalizationError("formal views require accepted external demonstrations only")
        if not item.get("upstream_message_refs"):
            raise FormalizationError("formal views require upstream message lineage")
        if origin == "DERIVED" and (
            not item.get("parent_demonstration_id") or not item.get("repair_rule_ref")
        ):
            raise FormalizationError(
                "derived external demonstrations require parent and repair lineage"
            )
    return selected


def _validate_recipe(
    recipe_path: Path, *, plan: ExperimentPlan, views: dict[str, list[str]]
) -> dict[str, Any]:
    recipe = _object(recipe_path)
    if recipe.get("candidate_pool_version") != plan.candidate_pool_version:
        raise FormalizationError("recipe candidate pool differs from preregistered plan")
    if recipe.get("match_fields") != plan.matching.get("fields") or recipe.get(
        "target_intervention"
    ) != plan.matching.get("target_intervention"):
        raise FormalizationError("recipe matching rule differs from preregistered plan")
    if set(recipe.get("sft_ingress_prohibited", [])) != {
        "PROJECT_SAMPLING",
        "MODEL_GENERATION",
        "MODEL_EVALUATION",
    }:
        raise FormalizationError("recipe must explicitly prohibit project/model sampling ingress")
    random, closed = recipe.get("random_matched"), recipe.get("closed_loop")
    if (
        not isinstance(random, list)
        or not isinstance(closed, list)
        or len(random) != len(closed)
        or not random
    ):
        raise FormalizationError("formal recipe needs supported matched pairs")
    if any(not isinstance(row, dict) for row in [*random, *closed]):
        raise FormalizationError("formal recipe rows are invalid")
    if [row.get("demonstration_id") for row in random] != views["SFT-RandomMatched"][
        : len(random)
    ] or [row.get("demonstration_id") for row in closed] != views["SFT-ClosedLoop"][: len(closed)]:
        raise FormalizationError("formal views must retain the feedback-matched pair first")
    return recipe


def _validate_quote(quote_path: Path, *, reserve: float, seconds: float) -> dict[str, Any]:
    quote = _object(quote_path)
    required = ("observed_at", "source_url", "price_cny_per_hour", "total_cash_stop_cny")
    if any(
        not isinstance(quote.get(key), (str, int, float)) or not quote.get(key) for key in required
    ):
        raise FormalizationError("formalization requires a current price and total cash stop")
    price, stop = quote["price_cny_per_hour"], quote["total_cash_stop_cny"]
    if (
        not isinstance(price, (int, float))
        or not isinstance(stop, (int, float))
        or price <= 0
        or stop <= 0
    ):
        raise FormalizationError("price quote values must be positive")
    predicted = price * seconds / 3600
    if predicted * (1 + reserve) > stop:
        raise FormalizationError(
            "cash stop is below the calibrated six-run prediction with reserve"
        )
    return {**quote, "predicted_gpu_compute_cny": predicted, "failure_reserve_fraction": reserve}


def _validate_calibration(calibration_path: Path, *, plan: ExperimentPlan) -> dict[str, Any]:
    calibration = _object(calibration_path)
    selection_path = calibration_path.parent / "method_selection.json"
    selection = _object(selection_path)
    if (
        sha256_file(calibration_path) != plan.calibration_manifest_sha256
        or calibration.get("kind") != "two-recipe-single-seed-calibration"
        or calibration.get("terminal_status") != "COMPLETED"
        or calibration.get("evidence_level") != "EXECUTION_VALIDATED"
        or calibration.get("method_selection_sha256") != plan.method_selection_sha256
        or sha256_file(selection_path) != plan.method_selection_sha256
        or selection.get("selected_method") != plan.method
        or selection.get("evidence_level") != "EXECUTION_VALIDATED"
    ):
        raise FormalizationError("formalization calibration differs from the preregistered method")
    if float(calibration.get("six_run_seconds_prediction", 0)) <= 0:
        raise FormalizationError("formalization requires the calibrated six-run prediction")
    return calibration


def _runtime_dependencies() -> dict[str, str]:
    packages = ("torch", "transformers", "peft", "trl", "pyarrow")
    try:
        return {package: metadata.version(package) for package in packages}
    except metadata.PackageNotFoundError as error:
        raise FormalizationError(
            f"formalization runtime lacks required dependency {error.name}"
        ) from error


def freeze_formal_experiment(
    *,
    plan_path: Path,
    config_path: Path,
    sft_view_path: Path,
    membership_path: Path,
    recipe_path: Path,
    price_quote_path: Path,
    calibration_path: Path,
    output_dir: Path,
) -> dict[str, object]:
    """Publish private formal views and a replacement preregistered revision."""
    plan = ExperimentPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    if plan.status is not ExperimentStatus.PREREGISTERED or plan.formalization is not None:
        raise FormalizationError("formalization requires an unfinalized preregistered plan")
    config = _config(config_path)
    views = _views(config)
    if config.get("candidate_pool_version") != plan.candidate_pool_version:
        raise FormalizationError("config candidate pool differs from preregistered plan")
    selected_ids = set().union(*map(set, views.values()))
    membership = _validate_membership(membership_path, selected_ids)
    recipe = _validate_recipe(recipe_path, plan=plan, views=views)
    table = pq.read_table(sft_view_path)
    required = {
        "demonstration_id",
        "input_ids",
        "loss_mask",
        "tokenizer_name",
        "tokenizer_revision",
        "template_version",
    }
    if required - set(table.column_names):
        raise FormalizationError("frozen SFT view lacks training identity columns")
    identity = plan.model
    if set(table["tokenizer_name"].to_pylist()) != {identity["model_id"]} or set(
        table["tokenizer_revision"].to_pylist()
    ) != {identity["tokenizer_revision"]}:
        raise FormalizationError("frozen SFT view model/tokenizer differs from plan")
    template_version = config.get("training_template_version")
    if not isinstance(template_version, str) or set(table["template_version"].to_pylist()) != {
        template_version
    }:
        raise FormalizationError("frozen SFT view template version differs from plan")
    output_dir.mkdir(parents=True, exist_ok=True)
    view_paths: dict[str, Path] = {}
    for recipe_name, ids in views.items():
        selected = [value in set(ids) for value in table["demonstration_id"].to_pylist()]
        subset = table.filter(pa.array(selected))
        if subset.num_rows != len(ids):
            raise FormalizationError("formal view is missing selected complete demonstrations")
        destination = output_dir / "views" / recipe_name / "training_examples.parquet"
        destination.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(subset, destination)
        view_paths[recipe_name] = destination
    schedule_config = config.get("schedule")
    if not isinstance(schedule_config, dict) or not isinstance(
        schedule_config.get("batch_shape"), dict
    ):
        raise FormalizationError("formalization requires the preregistered schedule")
    shape = schedule_config["batch_shape"]
    random_rows = load_sft_examples(
        view_paths["SFT-RandomMatched"], selected_ids=set(views["SFT-RandomMatched"])
    )
    closed_rows = load_sft_examples(
        view_paths["SFT-ClosedLoop"], selected_ids=set(views["SFT-ClosedLoop"])
    )
    schedule = build_equal_schedule(
        random_examples=random_rows,
        closed_loop_examples=closed_rows,
        batch_size=int(shape["per_device_batch_size"]),
        steps=int(schedule_config["optimizer_steps"]),
        max_context_tokens=int(shape["max_context_tokens"]),
        output_path=output_dir / "schedule.json",
    )
    if (
        schedule["effective_loss_tokens"] != plan.planned_loss_tokens
        or schedule["optimizer_steps"] != plan.planned_optimizer_steps
    ):
        raise FormalizationError("formal schedule differs from preregistered exposure")
    calibration = _validate_calibration(calibration_path, plan=plan)
    seconds = float(calibration["six_run_seconds_prediction"])
    quote = _validate_quote(
        price_quote_path,
        reserve=float(plan.exposure_budget["failure_reserve_fraction"]),
        seconds=seconds,
    )
    report = {
        "kind": "formal-external-view-matching-report",
        "candidate_pool_version": plan.candidate_pool_version,
        "selected_demonstrations": {name: ids for name, ids in views.items()},
        "membership": {
            key: {
                "source_origin": row["source_origin"],
                "source_record_id": row.get("source_record_id"),
                "parent_demonstration_id": row.get("parent_demonstration_id"),
                "repair_rule_ref": row.get("repair_rule_ref"),
                "upstream_message_ref_count": len(row["upstream_message_refs"]),
            }
            for key, row in membership.items()
        },
        "recipe_sha256": sha256_file(recipe_path),
        "recipe_pair_count": recipe["paired_member_count"],
        "common_exclusions": recipe.get("common_exclusions", []),
        "prohibited_ingress": recipe["sft_ingress_prohibited"],
    }
    report_path = output_dir / "matching_report.json"
    report_path.write_bytes(canonical_json_bytes(report))
    formalization = {
        "sft_view_sha256": sha256_file(sft_view_path),
        "membership_sha256": sha256_file(membership_path),
        "views": {name: sha256_file(path) for name, path in view_paths.items()},
        "schedule_sha256": sha256_file(output_dir / "schedule.json"),
        "matching_report_sha256": sha256_file(report_path),
        "calibration_manifest_sha256": sha256_file(calibration_path),
        "runtime_dependencies": _runtime_dependencies(),
        "price_quote": quote,
        "model_identity_verified": True,
    }
    draft = plan.model_copy(update={"revision": plan.revision + 1, "formalization": formalization})
    final = ExperimentPlan.model_validate(
        {**draft.model_dump(mode="json"), "preregistration_sha256": draft.frozen_conditions_sha256}
    )
    final_path = output_dir / "experiment_plan.json"
    final_path.write_bytes(canonical_json_bytes(final.model_dump(mode="json")))
    receipt = {
        "kind": "formal-sft-freeze",
        "terminal_status": "FROZEN",
        "evidence_level": "SOFTWARE_VALIDATED",
        "supersedes_preregistration_revision": plan.revision,
        "experiment_plan_sha256": sha256_file(final_path),
        "schedule_sha256": formalization["schedule_sha256"],
        "matching_report_sha256": formalization["matching_report_sha256"],
        "test_unlocked": False,
        "training_started": False,
    }
    (output_dir / "freeze_receipt.json").write_bytes(canonical_json_bytes(receipt))
    return receipt
