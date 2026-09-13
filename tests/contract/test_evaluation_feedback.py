from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_data_factory.cli import EXIT_INPUT_ERROR, main
from code_data_factory.datasets.feedback import FeedbackError, build_data_actions
from code_data_factory.datasets.recipes import build_recipe_drafts, prepare_recipe_candidate_pool
from code_data_factory.evaluation.findings import build_findings
from code_data_factory.evaluation.interactive import InfrastructureFailure, run_evaluation
from code_data_factory.evaluation.suites import SuiteError, build_tool_task_suite, load_suite


def _suite(tmp_path: Path) -> Path:
    config = tmp_path / "suite.yaml"
    config.write_text(
        """suite_id: ToolTaskBench-v1\nversion: v1\ndevelopment_task_count: 200\ntest_task_count: 200\nsource_template_group_count: 20\nminimum_family_count: 40\nminimum_unseen_test_count: 50\n""",
        encoding="utf-8",
    )
    return build_tool_task_suite(config, output_dir=tmp_path / "suite")


def test_suite_freezes_disjoint_groups_and_required_coverage(tmp_path: Path) -> None:
    suite = load_suite(_suite(tmp_path))
    assert len(suite.development) == len(suite.test) == 200
    assert {item.group_id for item in suite.development}.isdisjoint(item.group_id for item in suite.test)
    assert sum(item.unseen_combination for item in suite.test) >= 50
    assert all(sum(item.family == family for item in suite.test) >= 40 for family in suite.families)


def test_evaluation_keeps_fixed_denominator_and_retries_only_infrastructure_once(tmp_path: Path) -> None:
    suite = _suite(tmp_path)
    calls: dict[str, int] = {}

    def executor(task: object) -> dict[str, object]:
        task_id = task.task_id  # type: ignore[attr-defined]
        calls[task_id] = calls.get(task_id, 0) + 1
        if task_id.endswith("000") and calls[task_id] == 1:
            raise InfrastructureFailure("temporary runner failure")
        return {"value": task.expected_value, "unit": task.expected_unit, "evidence": list(task.document_ids)}  # type: ignore[attr-defined]

    receipt = run_evaluation(
        suite_manifest=suite,
        split="DEVELOPMENT",
        executor=executor,
        output_dir=tmp_path / "run",
        model_identity={"model_id": "fixture"},
    )
    assert receipt["metrics"]["task_success_at_1"] == 1.0
    assert receipt["fixed_denominator"] == 200
    assert max(calls.values()) == 2
    assert (tmp_path / "run" / "evaluation_run.json").is_file()


def test_test_split_is_locked_and_expected_values_are_not_in_manifest(tmp_path: Path) -> None:
    suite_path = _suite(tmp_path)
    payload = json.loads(suite_path.read_text(encoding="utf-8"))
    assert "expected_value" not in json.dumps(payload)
    with pytest.raises(SuiteError, match="final test is locked"):
        run_evaluation(
            suite_manifest=suite_path,
            split="TEST",
            executor=lambda _: {},
            output_dir=tmp_path / "test",
            model_identity={"model_id": "fixture"},
        )


def test_findings_actions_and_recipes_keep_test_out_and_bind_every_targeted_selection(tmp_path: Path) -> None:
    suite = _suite(tmp_path)
    receipt = run_evaluation(
        suite_manifest=suite,
        split="DEVELOPMENT",
        executor=lambda _: {"value": "wrong", "unit": "cm", "evidence": []},
        output_dir=tmp_path / "evaluation",
        model_identity={"model_id": "fixture"},
    )
    assert receipt["split"] == "DEVELOPMENT"
    build_findings(tmp_path / "evaluation" / "evaluation_run.json", output_dir=tmp_path / "findings")
    pool = [
        {"demonstration_id": f"demo-{index}", "candidate_pool_version": "pool-v1", "source_id": "source-a", "task_family": "lookup", "dependency_depth": 1, "length_bin": "short", "verification_strength": "strong", "baseline_difficulty": "medium", "failure_types": ["CONSTRAINT_FAILURE"] if index % 2 == 0 else ["OTHER"]}
        for index in range(4)
    ]
    pool_path = tmp_path / "pool.json"
    pool_path.write_text(json.dumps(pool), encoding="utf-8")
    actions = build_data_actions(
        evaluation_path=tmp_path / "evaluation" / "evaluation_run.json",
        findings_path=tmp_path / "findings" / "findings.json",
        candidate_pool_path=pool_path,
        output_dir=tmp_path / "actions",
        policy_path=Path("configs/quality/feedback.yaml"),
    )
    assert actions["actions"] and all(action["finding_id"] for action in actions["actions"])
    recipes = build_recipe_drafts(actions_path=tmp_path / "actions" / "data_actions.json", candidate_pool_path=pool_path, output_dir=tmp_path / "recipes")
    assert recipes["paired_member_count"] > 0
    with pytest.raises(FeedbackError, match="development"):
        build_data_actions(evaluation_path=tmp_path / "suite" / "suite_manifest.json", findings_path=tmp_path / "findings" / "findings.json", candidate_pool_path=pool_path, output_dir=tmp_path / "bad", policy_path=Path("configs/quality/feedback.yaml"))


def test_evaluate_and_feedback_cli_are_wired_and_test_cannot_be_unlocked_by_split_flag(tmp_path: Path, capsys: object) -> None:
    model = tmp_path / "fixture-model.json"
    model.write_text(json.dumps({"kind": "FIXTURE_EVALUATOR", "model_id": "fixture"}), encoding="utf-8")
    output = tmp_path / "evaluation"
    assert main(["--json", "--suite", "configs/evaluation/tool-tasks.yaml", "--model", str(model), "--output-dir", str(output), "evaluate", "run"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"] == {"tasks": 200}
    assert main(["--json", "--suite", "configs/evaluation/tool-tasks.yaml", "--model", str(model), "--split", "TEST", "--output-dir", str(tmp_path / "test"), "evaluate", "run"]) == EXIT_INPUT_ERROR


def test_recipe_pool_profile_uses_only_frozen_external_membership(tmp_path: Path) -> None:
    membership = [{"demonstration_id": "demo", "eligibility_action": "ACCEPT", "messages": [{"role": "user", "content": "check a social media alert"}, {"role": "assistant", "content": "", "tool_call": {"raw_content": "{'name': 'weather-get_alerts', 'arguments': '{}'}"}}, {"role": "tool", "content": "ok"}], "review_checks": ["a"] * 6}]
    members = tmp_path / "membership.json"
    manifest = tmp_path / "manifest.json"
    members.write_text(json.dumps(membership), encoding="utf-8")
    manifest.write_text(json.dumps({"candidate_kind": "EXTERNAL_DEMONSTRATION", "logical_content_hash": "pool-v1"}), encoding="utf-8")
    rows = prepare_recipe_candidate_pool(membership_path=members, candidate_manifest_path=manifest, output_path=tmp_path / "profile.json")
    assert rows[0]["candidate_pool_version"] == "pool-v1"
    assert rows[0]["failure_types"] == ["CONSTRAINT_FAILURE"]
