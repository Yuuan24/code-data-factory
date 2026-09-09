from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_data_factory.checkpoints.us1 import run_us1_software_checkpoint


def test_us1_checkpoint_rebuilds_fixture_boundaries_and_writes_receipt(tmp_path: Path) -> None:
    source = tmp_path / "source_report.json"
    dedup = tmp_path / "dedup_review_summary.json"
    equivalence = tmp_path / "equivalence.json"
    source.write_text('{"sources":[{"source_id":"fixture"}]}', encoding="utf-8")
    dedup.write_text(
        '{"reviewed_candidate_pairs":100,"reviewed_probe_pairs":100,"review_sha256":"a"}',
        encoding="utf-8",
    )
    equivalence.write_text(
        '{"local_hash":"same","ray_hash":"same","full_hash":"same","incremental_hash":"same","precommit_recovery":"RECOVERED","postcommit_recovery":"RECOVERED"}',
        encoding="utf-8",
    )

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


def test_us1_checkpoint_rejects_empty_evidence_placeholders(tmp_path: Path) -> None:
    source = tmp_path / "source_report.json"
    dedup = tmp_path / "dedup_review_summary.json"
    equivalence = tmp_path / "equivalence.json"
    for path in (source, dedup, equivalence):
        path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="lacks required evidence fields"):
        run_us1_software_checkpoint(
            output_path=tmp_path / "us1-software.json",
            source_report=source,
            dedup_review_summary=dedup,
            equivalence_manifest=equivalence,
            task_config=Path("configs/tasks/pilot.yaml"),
        )
