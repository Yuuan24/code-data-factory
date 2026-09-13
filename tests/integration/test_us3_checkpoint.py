from __future__ import annotations

from pathlib import Path

from code_data_factory.checkpoints.us3 import run_us3_checkpoint
from code_data_factory.datasets.feedback import build_data_actions
from code_data_factory.datasets.recipes import build_recipe_drafts
from code_data_factory.evaluation.findings import build_findings
from code_data_factory.evaluation.interactive import run_evaluation
from code_data_factory.evaluation.suites import build_tool_task_suite


def test_us3_software_checkpoint_binds_development_findings_actions_and_recipes(tmp_path: Path) -> None:
    suite = build_tool_task_suite(Path("configs/evaluation/tool-tasks.yaml"), output_dir=tmp_path / "suite")
    def executor(task: object) -> dict[str, object]:
        if task.family == "lookup":  # type: ignore[attr-defined]
            return {"value": "wrong", "unit": "cm", "evidence": []}
        return {"value": task.expected_value, "unit": task.expected_unit, "evidence": list(task.document_ids)}  # type: ignore[attr-defined]
    run_evaluation(suite_manifest=suite, split="DEVELOPMENT", executor=executor, output_dir=tmp_path / "evaluation", model_identity={"model_id": "fixture"})
    build_findings(tmp_path / "evaluation" / "evaluation_run.json", output_dir=tmp_path / "findings")
    build_data_actions(evaluation_path=tmp_path / "evaluation" / "evaluation_run.json", findings_path=tmp_path / "findings" / "findings.json", candidate_pool_path=Path("tests/fixtures/evaluation/candidate_pool.json"), output_dir=tmp_path / "actions", policy_path=Path("configs/quality/feedback.yaml"))
    build_recipe_drafts(actions_path=tmp_path / "actions" / "data_actions.json", candidate_pool_path=Path("tests/fixtures/evaluation/candidate_pool.json"), output_dir=tmp_path / "recipes")
    receipt = run_us3_checkpoint(output_path=tmp_path / "us3.json", suite_manifest=suite, evaluation_path=tmp_path / "evaluation" / "evaluation_run.json", findings_path=tmp_path / "findings" / "findings.json", actions_path=tmp_path / "actions" / "data_actions.json", recipes_path=tmp_path / "recipes" / "recipe_drafts.json")
    assert all(receipt["checks"].values())
