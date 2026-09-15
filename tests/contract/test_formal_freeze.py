from __future__ import annotations

import json
import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from code_data_factory import cli
from code_data_factory.contracts.artifacts import sha256_file
from code_data_factory.contracts.experiments import ExperimentPlan
from code_data_factory.evaluation.freeze import FormalizationError, freeze_formal_experiment
from code_data_factory.evaluation.preregister import preregister_experiment

RANDOM = [
    "toucan-import:7a96ca26-d68a-5572-b735-3f131d1546a5",
    "toucan-import:3a0b2b58-a834-5d86-8feb-828544b5e430",
    "toucan-import:ae86fdc5-ecde-52ef-b494-2d3f80555774",
]
CLOSED = [
    "toucan-import:0cf84c4e-3bef-5d3e-87f6-8981fbef57a2",
    "toucan-import:5e8b35d3-7b88-572c-8b8b-502901c86491",
    "toucan-import:baf41d1a-6568-5440-a10d-b4fa1d8b40d4",
]


def _config(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[2] / "configs/experiments/sft-main.yaml"
    destination = tmp_path / source.name
    shutil.copyfile(source, destination)
    return destination


def _calibration(tmp_path: Path) -> Path:
    selection_path = tmp_path / "method_selection.json"
    selection_path.write_text(
        json.dumps({"selected_method": "lora", "evidence_level": "EXECUTION_VALIDATED"}),
        encoding="utf-8",
    )
    manifest = {
        "kind": "two-recipe-single-seed-calibration",
        "terminal_status": "COMPLETED",
        "evidence_level": "EXECUTION_VALIDATED",
        "method_selection_sha256": sha256_file(selection_path),
        "schedule_sha256": "a" * 64,
        "six_run_seconds_prediction": 97.25,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    membership = [
        {
            "demonstration_id": demonstration_id,
            "source_origin": "PUBLIC_ORIGINAL",
            "eligibility_action": "ACCEPT",
            "source_record_id": f"source-{index}",
            "upstream_message_refs": [f"message-{index}"],
        }
        for index, demonstration_id in enumerate([*RANDOM, *CLOSED])
    ]
    membership_path = tmp_path / "membership.json"
    membership_path.write_text(json.dumps(membership), encoding="utf-8")
    recipe_path = tmp_path / "recipe_drafts.json"
    recipe_path.write_text(
        json.dumps(
            {
                "candidate_pool_version": "17bf4731dd7b510e8d8fa5c7a8a324d4f2e3f8ef842070d251271d6cc88a9a91",
                "match_fields": [
                    "source_id",
                    "task_family",
                    "dependency_depth",
                    "length_bin",
                    "verification_strength",
                    "baseline_difficulty",
                ],
                "target_intervention": "development-failure-type coverage",
                "sft_ingress_prohibited": [
                    "PROJECT_SAMPLING",
                    "MODEL_GENERATION",
                    "MODEL_EVALUATION",
                ],
                "paired_member_count": 1,
                "random_matched": [{"demonstration_id": RANDOM[0]}],
                "closed_loop": [{"demonstration_id": CLOSED[0]}],
                "common_exclusions": ["unsupported"],
            }
        ),
        encoding="utf-8",
    )
    rows = []
    for index, demonstration_id in enumerate([*RANDOM, *CLOSED]):
        loss_tokens = 597 if index in {2, 5} else 598
        rows.append(
            {
                "demonstration_id": demonstration_id,
                "input_ids": [index] * 2560,
                "loss_mask": [True] * loss_tokens + [False] * (2560 - loss_tokens),
                "tokenizer_name": "Qwen/Qwen3-8B",
                "tokenizer_revision": "b968826d9c46dd6066d109eabc6255188de91218",
                "template_version": "qwen3-chat-template-a55ee1b1",
            }
        )
    sft_path = tmp_path / "training_examples.parquet"
    pq.write_table(pa.Table.from_pylist(rows), sft_path)
    quote_path = tmp_path / "price_quote.json"
    quote_path.write_text(
        json.dumps(
            {
                "observed_at": "2026-09-15T12:00:00+08:00",
                "source_url": "https://www.autodl.com/market/list",
                "price_cny_per_hour": 1.58,
                "total_cash_stop_cny": 100.0,
            }
        ),
        encoding="utf-8",
    )
    return membership_path, recipe_path, sft_path, quote_path


def _preregistered(tmp_path: Path) -> tuple[Path, Path, Path]:
    config, calibration = _config(tmp_path), _calibration(tmp_path)
    preregister_experiment(
        config_path=config, calibration_path=calibration, output_dir=tmp_path / "registered"
    )
    return config, calibration, tmp_path / "registered" / "experiment_plan.json"


def test_freeze_publishes_equal_external_views_and_revisions_plan(tmp_path: Path) -> None:
    config, calibration, plan_path = _preregistered(tmp_path)
    membership, recipe, sft_view, quote = _inputs(tmp_path)
    output = tmp_path / "frozen"
    receipt = freeze_formal_experiment(
        plan_path=plan_path,
        config_path=config,
        calibration_path=calibration,
        sft_view_path=sft_view,
        membership_path=membership,
        recipe_path=recipe,
        price_quote_path=quote,
        output_dir=output,
    )
    plan = ExperimentPlan.model_validate_json(
        (output / "experiment_plan.json").read_text(encoding="utf-8")
    )
    schedule = json.loads((output / "schedule.json").read_text(encoding="utf-8"))
    report = json.loads((output / "matching_report.json").read_text(encoding="utf-8"))
    assert plan.revision == 4
    assert plan.preregistration_sha256 == plan.frozen_conditions_sha256
    assert plan.test_unlock_rule["enabled"] is False
    assert plan.formalization is not None
    assert plan.formalization["membership_sha256"] == sha256_file(membership)
    assert plan.formalization["price_quote"]["predicted_gpu_compute_cny"] < 1
    assert schedule["effective_loss_tokens"] == 1793
    assert schedule["equal_input_compute_budget"] is True
    assert report["prohibited_ingress"] == [
        "PROJECT_SAMPLING",
        "MODEL_GENERATION",
        "MODEL_EVALUATION",
    ]
    assert receipt["supersedes_preregistration_revision"] == 3
    assert (
        pq.read_table(output / "views" / "SFT-RandomMatched" / "training_examples.parquet").num_rows
        == 3
    )


def test_freeze_rejects_sft_view_with_different_model_revision(tmp_path: Path) -> None:
    config, calibration, plan_path = _preregistered(tmp_path)
    membership, recipe, sft_view, quote = _inputs(tmp_path)
    table = pq.read_table(sft_view).set_column(4, "tokenizer_revision", pa.array(["wrong"] * 6))
    pq.write_table(table, sft_view)
    with pytest.raises(FormalizationError, match="model/tokenizer"):
        freeze_formal_experiment(
            plan_path=plan_path,
            config_path=config,
            calibration_path=calibration,
            sft_view_path=sft_view,
            membership_path=membership,
            recipe_path=recipe,
            price_quote_path=quote,
            output_dir=tmp_path / "bad",
        )


def test_cli_freeze_requires_calibration(tmp_path: Path, capsys: object) -> None:
    config, _, plan_path = _preregistered(tmp_path)
    membership, recipe, sft_view, quote = _inputs(tmp_path)
    assert (
        cli.main(
            [
                "--json",
                "--output-dir",
                str(tmp_path / "frozen"),
                "--config",
                str(config),
                "--plan",
                str(plan_path),
                "--sft-view",
                str(sft_view),
                "--membership",
                str(membership),
                "--recipe-drafts",
                str(recipe),
                "--price-quote",
                str(quote),
                "experiment",
                "freeze",
            ]
        )
        == cli.EXIT_INPUT_ERROR
    )
    assert "--calibration" in json.loads(capsys.readouterr().out)["errors"][0]
