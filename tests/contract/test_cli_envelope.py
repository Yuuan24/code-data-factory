from __future__ import annotations

import json
from pathlib import Path

from code_data_factory.cli import EXIT_INPUT_ERROR, main


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
