from __future__ import annotations

import json
from pathlib import Path

from code_data_factory.checkpoints.us1 import run_us1_software_checkpoint


def test_us1_checkpoint_rebuilds_fixture_boundaries_and_writes_receipt(tmp_path: Path) -> None:
    source = tmp_path / "source_report.json"
    dedup = tmp_path / "dedup_review_summary.json"
    equivalence = tmp_path / "equivalence.json"
    for path in (source, dedup, equivalence):
        path.write_text("{}", encoding="utf-8")

    receipt = run_us1_software_checkpoint(
        output_path=tmp_path / "us1-software.json",
        source_report=source,
        dedup_review_summary=dedup,
        equivalence_manifest=equivalence,
        task_config=Path("configs/tasks/pilot.yaml"),
    )

    assert receipt["evidence_level"] == "SOFTWARE_VALIDATED"
    assert receipt["counts"]["pilot_draft_tasks"] == 100
    assert all(receipt["checks"].values())
    assert json.loads((tmp_path / "us1-software.json").read_text())["limitations"]
