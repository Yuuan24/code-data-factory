from __future__ import annotations

import json
from pathlib import Path

from code_data_factory.checkpoints.us3 import run_us3_checkpoint
from code_data_factory.datasets.feedback import build_data_actions
from code_data_factory.datasets.recipes import build_recipe_drafts
from code_data_factory.evaluation.findings import build_findings
from code_data_factory.evaluation.interactive import run_evaluation
from code_data_factory.evaluation.suites import build_tool_task_suite


def _bfcl_development_receipt(tmp_path: Path) -> Path:
    payload = {
        "kind": "bfcl-v4-development-evaluation", "split": "DEVELOPMENT", "terminal_status": "COMPLETED",
        "official_commit": "f7cf7359b7ac615a0b294831c5ba2bc95ee4a000", "source_method": "GITHUB_EXACT_COMMIT_ARCHIVE",
        "official_archive_sha256": "c57136de766f16462414b86e0b3892c751e10f47db7e34fa84e2d7c4571f54de", "runner_package": "bfcl-eval==2025.12.17",
        "selected_task_count": 4, "infrastructure_failure_count": 0, "full_bfcl_score_claimed": False, "protocol_deviations": ["fixture subset"],
        "categories": {
            "multi_turn_base": {"selected_ids": ["multi_turn_base_0", "multi_turn_base_1"], "selected_count": 2, "accuracy": 0.0, "result_sha256": "a" * 64, "score_sha256": "b" * 64},
            "irrelevance": {"selected_ids": ["irrelevance_0", "irrelevance_1"], "selected_count": 2, "accuracy": 1.0, "result_sha256": "c" * 64, "score_sha256": "d" * 64},
        },
    }
    path = tmp_path / "bfcl-development.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_us3_software_checkpoint_binds_development_findings_actions_and_recipes(tmp_path: Path) -> None:
    suite = build_tool_task_suite(Path("configs/evaluation/tool-tasks.yaml"), output_dir=tmp_path / "suite")
    def executor(task: object) -> dict[str, object]:
        if task.family == "lookup":  # type: ignore[attr-defined]
            return {"value": "wrong", "unit": "cm", "evidence": []}
        return {"value": task.expected_value, "unit": task.expected_unit, "evidence": list(task.document_ids)}  # type: ignore[attr-defined]
    run_evaluation(suite_manifest=suite, split="DEVELOPMENT", executor=executor, output_dir=tmp_path / "evaluation", model_identity={"model_id": "fixture"})
    build_findings(tmp_path / "evaluation" / "evaluation_run.json", output_dir=tmp_path / "findings")
    external = _bfcl_development_receipt(tmp_path)
    build_data_actions(evaluation_path=tmp_path / "evaluation" / "evaluation_run.json", external_evaluation_path=external, external_config_path=Path("configs/evaluation/bfcl-local-v4.yaml"), findings_path=tmp_path / "findings" / "findings.json", candidate_pool_path=Path("tests/fixtures/evaluation/candidate_pool.json"), output_dir=tmp_path / "actions", policy_path=Path("configs/quality/feedback.yaml"))
    build_recipe_drafts(actions_path=tmp_path / "actions" / "data_actions.json", candidate_pool_path=Path("tests/fixtures/evaluation/candidate_pool.json"), output_dir=tmp_path / "recipes")
    receipt = run_us3_checkpoint(output_path=tmp_path / "us3.json", suite_manifest=suite, evaluation_path=tmp_path / "evaluation" / "evaluation_run.json", external_evaluation_path=external, external_config_path=Path("configs/evaluation/bfcl-local-v4.yaml"), findings_path=tmp_path / "findings" / "findings.json", actions_path=tmp_path / "actions" / "data_actions.json", recipes_path=tmp_path / "recipes" / "recipe_drafts.json")
    assert all(receipt["checks"].values())
