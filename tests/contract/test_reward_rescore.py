from __future__ import annotations

import hashlib
from pathlib import Path

from code_data_factory.verification.rescore import rescore_fixed_evidence


def test_rescore_preserves_fixed_evidence_and_reports_all_sparse_reward_states(tmp_path: Path) -> None:
    source = Path("tests/fixtures/sparse-rewards/manifest.json")
    before = hashlib.sha256(source.read_bytes()).hexdigest()

    receipt = rescore_fixed_evidence(
        evidence_path=source,
        policy_path=Path("configs/quality/reward-terminal-v2.yaml"),
        output_dir=tmp_path,
    )

    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert receipt["counts"] == {
        "success": 2,
        "known_zero": 2,
        "unknown": 2,
        "truncated": 2,
    }
    assert receipt["policy_comparison"]["same_terminal_values"] == 8
    assert all(record["reward_scope"] == "TERMINAL" for record in receipt["rescored_records"])
