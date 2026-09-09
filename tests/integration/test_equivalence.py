from __future__ import annotations

from pathlib import Path

from code_data_factory.processing.equivalence import run_equivalence


def test_equivalence_receipt_covers_backends_incremental_and_recovery(tmp_path: Path) -> None:
    receipt = run_equivalence(
        [
            {"task_id": "task-a", "projection": "one metre is 100 centimetres", "scope": "TRAIN"},
            {"task_id": "task-b", "projection": "one minute is 60 seconds", "scope": "TEST"},
        ],
        output_dir=tmp_path / "equivalence",
    )

    assert receipt.local_hash == receipt.ray_hash
    assert receipt.full_hash == receipt.incremental_hash
    assert receipt.precommit_recovery == "REJECTED_THEN_RECOVERED"
    assert receipt.postcommit_recovery == "REJECTED_THEN_RECOVERED"
    assert receipt.postcommit_retry == "IDEMPOTENT"
    assert (tmp_path / "equivalence" / "manifest.json").is_file()
