from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from code_data_factory.sources.toucan import (
    AssociationAmbiguity,
    import_toucan_records,
    write_import_result,
)


def _write_source(path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "id": "unique",
                    "tools": [
                        {
                            "name": "read_document",
                            "parameters": {"type": "object"},
                        }
                    ],
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
                    "tools": [],
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
                    "tools": [],
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


def test_import_keeps_historical_execution_evidence_outside_external_candidate_scope(tmp_path: Path) -> None:
    source = tmp_path / "missing-environment.json"
    source.write_text(
        json.dumps(
            [
                {
                    "id": "missing-environment",
                    "tools": [],
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

    assert imported.records[0].usage_scope == "TRAIN"
    assert imported.demonstrations[0].usage_scope.value == "TRAIN"
    assert imported.demonstrations[0].replay_capability.value == "UNSUPPORTED"
    assert imported.trajectories[0].attempt.actor_kind.value == "HISTORICAL_IMPORT"
    assert imported.trajectories[0].attempt.policy_ref is None


def test_import_reads_parquet_history_without_evaluating_message_text(tmp_path: Path) -> None:
    source = tmp_path / "toucan.parquet"
    pq.write_table(
        pa.table(
            {
                "id": ["parquet-safe"],
                "messages": [
                    json.dumps(
                        [
                            {"role": "user", "content": "__import__('os').system('false')"},
                            {"role": "assistant", "content": "plain text only"},
                        ]
                    )
                ],
                "tools": [json.dumps([])],
            }
        ),
        source,
    )

    imported = import_toucan_records(source, snapshot_id="toucan-test", producer_run_id="run-1")

    assert [record.upstream_id for record in imported.records] == ["parquet-safe"]
    assert imported.trajectories[0].attempt.actor_kind.value == "HISTORICAL_IMPORT"


def test_import_writes_consumable_manifests_without_raw_message_payload(tmp_path: Path) -> None:
    source = tmp_path / "toucan.json"
    _write_source(source)
    imported = import_toucan_records(source, snapshot_id="toucan-test", producer_run_id="run-1")

    paths = write_import_result(imported, output_dir=tmp_path / "normalized")

    assert all(path.is_file() for path in paths.values())
    assert "Find the length" not in paths["source_records"].read_text(encoding="utf-8")
    assert json.loads(paths["external_demonstrations"].read_text(encoding="utf-8"))["external_demonstrations"][0]["usage_scope"] == "TRAIN"
    assert json.loads(paths["attempts"].read_text(encoding="utf-8"))["attempts"][0]["actor_kind"] == "HISTORICAL_IMPORT"


def test_import_requires_an_explicit_upstream_tool_definition(tmp_path: Path) -> None:
    source = tmp_path / "missing-tools.json"
    source.write_text(
        json.dumps(
            [
                {
                    "id": "missing-tools",
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

    assert imported.records == []
    assert imported.demonstrations == []
    assert imported.quarantine[0].reason == "MISSING_TOOL_DEFINITION"


def test_import_normalizes_toucan_tool_call_and_response_roles_without_evaluation(tmp_path: Path) -> None:
    source = tmp_path / "toucan-roles.json"
    source.write_text(
        json.dumps(
            [
                {
                    "id": "toucan-role-example",
                    "question": "Find a rhyme.",
                    "tools": [{"type": "function", "function": {"name": "find_rhymes"}}],
                    "messages": [
                        {"role": "user", "content": "Find a rhyme."},
                        {
                            "role": "tool_call",
                            "content": "{'name': '__import__(\"os\").system(\"false\")'}",
                        },
                        {"role": "tool_response", "content": "plain tool result"},
                        {"role": "assistant", "content": "answer"},
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    imported = import_toucan_records(source, snapshot_id="toucan-test", producer_run_id="run-1")

    assert imported.quarantine == []
    assert [event.event_type.value for event in imported.trajectories[0].events] == [
        "OBSERVATION",
        "TOOL_CALL",
        "TOOL_RESULT",
        "MODEL_OUTPUT",
    ]
    material = imported.materials[0]["messages"]
    assert material[1]["role"] == "assistant"
    assert material[1]["tool_call"]["raw_content"].startswith("{'name'")
    assert material[2]["role"] == "tool"


def test_import_accepts_toucan_uuid_when_legacy_id_is_absent(tmp_path: Path) -> None:
    source = tmp_path / "uuid.json"
    source.write_text(
        json.dumps(
            [
                {
                    "uuid": "source-uuid",
                    "tools": [],
                    "messages": [
                        {"role": "user", "content": "question"},
                        {"role": "assistant", "content": "answer"},
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    imported = import_toucan_records(source, snapshot_id="toucan-test", producer_run_id="run-1")

    assert imported.records[0].upstream_id == "source-uuid"
