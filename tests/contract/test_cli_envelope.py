from __future__ import annotations

import json

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
