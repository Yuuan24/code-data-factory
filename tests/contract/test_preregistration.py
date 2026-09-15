from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from code_data_factory import cli
from code_data_factory.contracts.artifacts import sha256_file
from code_data_factory.contracts.experiments import ExperimentPlan, ExperimentStatus
from code_data_factory.evaluation.preregister import PreregistrationError, preregister_experiment


def _calibration(tmp_path: Path) -> Path:
    selection = {
        "selected_method": "lora",
        "evidence_level": "EXECUTION_VALIDATED",
    }
    selection_path = tmp_path / "method_selection.json"
    selection_path.write_text(json.dumps(selection), encoding="utf-8")
    manifest = {
        "kind": "two-recipe-single-seed-calibration",
        "terminal_status": "COMPLETED",
        "evidence_level": "EXECUTION_VALIDATED",
        "method_selection_sha256": sha256_file(selection_path),
        "schedule_sha256": "a" * 64,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _config(tmp_path: Path) -> Path:
    source = Path("configs/experiments/sft-main.yaml")
    destination = tmp_path / source.name
    shutil.copyfile(source, destination)
    return destination


def test_preregister_binds_all_rules_and_leaves_test_locked(tmp_path: Path) -> None:
    config, calibration = _config(tmp_path), _calibration(tmp_path)
    receipt = preregister_experiment(
        config_path=config, calibration_path=calibration, output_dir=tmp_path / "registered"
    )
    plan = ExperimentPlan.model_validate_json(
        (tmp_path / "registered" / "experiment_plan.json").read_text(encoding="utf-8")
    )
    assert plan.status is ExperimentStatus.PREREGISTERED
    assert plan.preregistration_sha256 == plan.frozen_conditions_sha256
    assert plan.seeds == (17, 29, 43)
    assert plan.matching["tolerance"] == "exact"
    assert plan.tool_protocol["tools"] == ["search_documents", "read_document", "calculate", "convert"]
    assert plan.test_unlock_rule["enabled"] is False
    assert plan.guardrails["analysis"]["minimum_connected_groups"] == 20
    assert plan.guardrails["analysis"]["paired_bootstrap_resamples"] == 10000
    assert receipt["test_unlocked"] is False


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ("minimum_connected_groups: 19", "minimum_connected_groups"),
        ("paired_bootstrap_resamples: 9999", "paired_bootstrap_resamples"),
        ("tolerance: exact", "matching tolerance"),
    ],
)
def test_preregister_rejects_unfrozen_statistics_or_matching(
    tmp_path: Path, replacement: str, message: str
) -> None:
    config, calibration = _config(tmp_path), _calibration(tmp_path)
    text = config.read_text(encoding="utf-8")
    if replacement == "tolerance: exact":
        text = text.replace(replacement, "tolerance: nearest")
    else:
        key = replacement.split(":", 1)[0]
        text = text.replace(f"{key}: " + ("20" if key.startswith("minimum") else "10000"), replacement)
    config.write_text(text, encoding="utf-8")
    with pytest.raises(PreregistrationError, match=message):
        preregister_experiment(config_path=config, calibration_path=calibration, output_dir=tmp_path / "bad")


def test_cli_preregister_and_registered_run_fail_closed_before_t079(
    tmp_path: Path, capsys: object
) -> None:
    config, calibration = _config(tmp_path), _calibration(tmp_path)
    output = tmp_path / "registered"
    assert cli.main(["--json", "--config", str(config), "--calibration", str(calibration), "--output-dir", str(output), "experiment", "preregister"]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["counts"] == {
        "minimum_connected_groups": 20,
        "paired_bootstrap_resamples": 10000,
        "training_runs": 6,
    }
    assert cli.main(["--json", "--output-dir", str(tmp_path / "training"), "--plan", str(output / "experiment_plan.json"), "--recipe", "SFT-ClosedLoop", "--seed", "17", "experiment", "run"]) == cli.EXIT_INPUT_ERROR
    assert "implemented in T079" in json.loads(capsys.readouterr().out)["errors"][0]
