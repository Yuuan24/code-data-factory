from __future__ import annotations

import json
from pathlib import Path

from code_data_factory.sources.toucan import AssociationAmbiguity, import_toucan_records


def _write_source(path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "id": "unique",
                    "messages": [
                        {"role": "user", "content": "Find the length."},
                        {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "name": "read_document",
                                    "arguments": {"document_id": "units"},
                                }
                            ],
                        },
                        {
                            "role": "tool",
                            "tool_call_id": "call-1",
                            "content": "100 cm equals one metre.",
                        },
                        {"role": "assistant", "content": "It is one metre."},
                    ],
                },
                {
                    "id": "ambiguous",
                    "messages": [
                        {"role": "tool", "content": "orphan result"},
                    ],
                },
            ]
        ),
        encoding="utf-8",
    )


def test_import_maps_unique_history_and_quarantines_ambiguous_records(tmp_path: Path) -> None:
    source = tmp_path / "toucan.json"
    _write_source(source)

    imported = import_toucan_records(source, snapshot_id="toucan-test", producer_run_id="run-1")

    assert [record.source_record_id for record in imported.records] == ["toucan-test:unique"]
    assert imported.records[0].association_origin == "inferred_unique"
    assert len(imported.trajectories) == 1
    assert imported.trajectories[0].events[1].tool_call_id == "call-1"
    assert [item.upstream_id for item in imported.quarantine] == ["ambiguous"]
    assert imported.quarantine[0].reason == AssociationAmbiguity.ORPHAN_TOOL_RESULT.value


def test_import_never_executes_source_text(tmp_path: Path) -> None:
    source = tmp_path / "unsafe.json"
    source.write_text(
        json.dumps(
            [
                {
                    "id": "unsafe",
                    "messages": [
                        {"role": "user", "content": "__import__('os').system('false')"},
                        {"role": "assistant", "content": "plain text only"},
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    imported = import_toucan_records(source, snapshot_id="toucan-test", producer_run_id="run-1")

    assert len(imported.records) == 1
    assert imported.records[0].origin_kind == "PUBLIC_ORIGINAL"


def test_import_keeps_missing_environment_in_historical_only(tmp_path: Path) -> None:
    source = tmp_path / "missing-environment.json"
    source.write_text(
        json.dumps(
            [
                {
                    "id": "missing-environment",
                    "messages": [
                        {"role": "user", "content": "look up a fact"},
                        {"role": "assistant", "content": "answer"},
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    imported = import_toucan_records(source, snapshot_id="toucan-test", producer_run_id="run-1")

    assert imported.records[0].usage_scope == "HISTORICAL_ONLY"
    assert imported.trajectories[0].attempt.actor_kind.value == "HISTORICAL_IMPORT"
    assert imported.trajectories[0].attempt.policy_ref is None
