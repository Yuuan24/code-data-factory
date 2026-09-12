from __future__ import annotations

import json
from pathlib import Path

from code_data_factory.cli import EXIT_INPUT_ERROR, _resumed_build, main


def test_business_command_without_required_artifacts_fails_closed(capsys: object) -> None:
    assert main(["--json", "source", "audit"]) == EXIT_INPUT_ERROR
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    envelope = json.loads(captured.out)
    assert envelope["status"] == "INPUT_ERROR"
    assert envelope["evidence_level"] == "UNVERIFIED"


def test_unknown_command_is_input_error(capsys: object) -> None:
    assert main(["--json", "invent"]) == EXIT_INPUT_ERROR
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert json.loads(captured.out)["status"] == "INPUT_ERROR"


def test_data_build_resume_rejects_a_completed_receipt_with_different_identity(
    tmp_path: Path, capsys: object
) -> None:
    for name in ("source", "task", "attempt", "verification", "split"):
        (tmp_path / f"{name}.json").write_text("{}", encoding="utf-8")
    (tmp_path / "input.json").write_text(
        json.dumps(
            {
                "source_manifests": ["source.json"],
                "task_manifests": ["task.json"],
                "attempt_manifests": ["attempt.json"],
                "verification_manifests": ["verification.json"],
                "split_registry_ref": "split.json",
                "rule_version": "v1",
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    output.mkdir()
    (output / "build_receipt.json").write_text(
        json.dumps({"run_id": "another-run", "backend": "local", "input_manifest_hash": "bad"}),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--json",
                "--output-dir",
                str(output),
                "--input",
                str(tmp_path / "input.json"),
                "--backend",
                "local",
                "--resume",
                "resume-run",
                "data",
                "build",
            ]
        )
        == EXIT_INPUT_ERROR
    )
    assert "--resume conflicts" in json.loads(capsys.readouterr().out)["errors"][0]


def test_external_build_resume_rebuilds_when_its_derived_candidate_manifest_is_missing(
    tmp_path: Path,
) -> None:
    output = tmp_path / "candidate"
    output.mkdir()
    (output / "build_receipt.json").write_text(
        json.dumps(
            {
                "run_id": "external-run",
                "backend": "local",
                "input_manifest_hash": "input-hash",
                "member_kind": "EXTERNAL_DEMONSTRATION",
                "member_count": 1,
                "accepted_count": 1,
            }
        ),
        encoding="utf-8",
    )
    (output / "membership.json").write_text("[]", encoding="utf-8")
    (output / "eligibility_decisions.json").write_text("{}", encoding="utf-8")

    assert (
        _resumed_build(
            output,
            run_id="external-run",
            backend="local",
            input_manifest_hash="input-hash",
        )
        is None
    )


def test_external_build_and_publish_need_no_execution_environment(
    tmp_path: Path, capsys: object
) -> None:
    for name, value in {
        "source.json": {"source_records": [{"source_record_id": "source-1"}]},
        "demonstrations.json": {
            "external_demonstrations": [
                {
                    "demonstration_id": "demo-1",
                    "source_record_id": "source-1",
                    "message_refs": [{"uri": "messages/demo-1.json"}],
                    "source_origin": "PUBLIC_ORIGINAL",
                    "replay_capability": "UNSUPPORTED",
                }
            ]
        },
        "eligibility.json": {
            "eligibility_decisions": [
                {
                    "decision_id": "eligibility-demo-1",
                    "demonstration_id": "demo-1",
                    "action": "ACCEPT",
                    "review_checks": [
                        "source_identity",
                        "upstream_tool_definition",
                        "message_context",
                        "target_answer_mapping",
                        "split_registration",
                        "sensitive_review",
                    ],
                }
            ]
        },
        "materials.json": {
            "external_material": [
                {
                    "demonstration_id": "demo-1",
                    "messages": [
                        {"role": "user", "content": "question"},
                        {"role": "assistant", "content": "answer"},
                    ],
                }
            ]
        },
        "split.json": {"policy": "external-split-v1"},
    }.items():
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    (tmp_path / "input.json").write_text(
        json.dumps(
            {
                "source_manifests": ["source.json"],
                "external_demonstration_manifests": ["demonstrations.json"],
                "external_material_manifests": ["materials.json"],
                "eligibility_manifests": ["eligibility.json"],
                "split_registry_ref": "split.json",
                "rule_version": "external-sft-v1",
            }
        ),
        encoding="utf-8",
    )
    candidate = tmp_path / "candidate"
    assert (
        main(
            [
                "--json",
                "--output-dir",
                str(candidate),
                "--input",
                str(tmp_path / "input.json"),
                "--backend",
                "local",
                "data",
                "build",
            ]
        )
        == 0
    )
    build_envelope = json.loads(capsys.readouterr().out)
    assert build_envelope["counts"]["members"] == 1
    assert any(path.endswith("eligibility_decisions.json") for path in build_envelope["artifact_refs"])
    assert any(path.endswith("manifest.json") for path in build_envelope["artifact_refs"])
    policy = tmp_path / "external-sft.yaml"
    policy.write_text("policy_version: external-sft-v1\n", encoding="utf-8")
    assert (
        main(
            [
                "--json",
                "--output-dir",
                str(tmp_path / "releases"),
                "--draft",
                str(candidate / "membership.json"),
                "--config",
                str(policy),
                "dataset",
                "publish",
            ]
        )
        == 0
    )
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["counts"] == {"members": 1}
    assert (tmp_path / "releases" / "external" / "dataset_manifest.json").is_file()
