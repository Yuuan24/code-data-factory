from __future__ import annotations

import json
from pathlib import Path

from code_data_factory.cli import main


def _envelope(capsys: object) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]


def test_compatibility_cli_emits_separate_contract_and_long_horizon_receipts(tmp_path: Path, capsys: object) -> None:
    contract_dir = tmp_path / "contract"
    assert main([
        "--json",
        "--profile", "configs/execution/trl-tools.yaml",
        "--mode", "contract",
        "--output-dir", str(contract_dir),
        "compatibility", "check",
    ]) == 0
    contract = _envelope(capsys)
    assert contract["status"] == "COMPLETED"
    assert (contract_dir / "manifest.json").is_file()

    long_dir = tmp_path / "long"
    assert main([
        "--json",
        "--profile", "configs/execution/long-horizon.yaml",
        "--mode", "long-horizon",
        "--output-dir", str(long_dir),
        "compatibility", "check",
    ]) == 0
    long_receipt = _envelope(capsys)
    assert long_receipt["counts"] == {"cases": 2, "steps": 160}
    assert (long_dir / "manifest.json").is_file()


def test_reward_rescore_cli_writes_a_new_projection_without_rewriting_fixed_evidence(tmp_path: Path, capsys: object) -> None:
    assert main([
        "--json",
        "--evidence", "tests/fixtures/sparse-rewards/manifest.json",
        "--policy", "configs/quality/reward-terminal-v2.yaml",
        "--output-dir", str(tmp_path),
        "reward", "rescore",
    ]) == 0
    envelope = _envelope(capsys)
    assert envelope["counts"] == {"success": 2, "known_zero": 2, "unknown": 2, "truncated": 2}
    assert (tmp_path / "manifest.json").is_file()
