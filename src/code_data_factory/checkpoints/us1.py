"""US1 software checkpoint that keeps fixture-only proof distinct from real data."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes, sha256_file
from code_data_factory.datasets.export_sft import export_sft_examples
from code_data_factory.datasets.publish import publish_dataset
from code_data_factory.sources.revoke import revoke_source
from code_data_factory.sources.toucan import import_toucan_records
from code_data_factory.tasks.build import build_pilot_tasks
from code_data_factory.tasks.splits import SplitRegistry


class _FixtureChatTokenizer:
    """Checkpoint-only tokenizer: never stands in for the frozen training tokenizer."""

    chat_template: str | None = "us1-checkpoint-fixture-v1"

    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]:
        del add_special_tokens
        return list(text.encode("utf-8"))

    def apply_chat_template(
        self, conversation: list[dict[str, str]], *, tokenize: bool, add_generation_prompt: bool
    ) -> list[int]:
        if not tokenize or add_generation_prompt:
            raise ValueError("fixture tokenizer only supports completed tokenized conversations")
        return self.encode(
            "".join(f"<{message['role']}>\n{message['content']}<eos>\n" for message in conversation),
            add_special_tokens=False,
        )


def _fixture_history() -> list[dict[str, Any]]:
    return [
        {
            "id": "unique",
            "messages": [
                {"role": "user", "content": "Find the declared conversion."},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "read_document",
                            "arguments": {"document_id": "units-length"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": "100"},
                {"role": "assistant", "content": "100<eos>"},
            ],
        },
        {"id": "orphan", "messages": [{"role": "tool", "content": "unlinked"}]},
    ]


def run_us1_software_checkpoint(
    *,
    output_path: Path,
    source_report: Path,
    dedup_review_summary: Path,
    equivalence_manifest: Path,
    task_config: Path,
) -> dict[str, Any]:
    """Rebuild bounded fixture paths and write a factual US1 software receipt."""

    required = (source_report, dedup_review_summary, equivalence_manifest, task_config)
    if any(not path.is_file() for path in required):
        raise ValueError("US1 checkpoint requires source, dedup, equivalence, and task-config inputs")
    with TemporaryDirectory(prefix="cdf-us1-checkpoint-") as temporary:
        root = Path(temporary)
        history_path = root / "history.json"
        history_path.write_bytes(canonical_json_bytes(_fixture_history()))
        imported = import_toucan_records(
            history_path, snapshot_id="us1-checkpoint", producer_run_id="us1-checkpoint"
        )
        build = build_pilot_tasks(
            task_config,
            output_dir=root / "pilot",
            producer_run_id="us1-checkpoint",
            split_registry=SplitRegistry(policy_version="split-v1"),
        )
        attempts = [
            {
                "attempt_id": "fixture-attempt",
                "task_id": "fixture-task",
                "messages": [
                    {"role": "user", "content": "Find the declared conversion."},
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_call": {
                            "name": "read_document",
                            "arguments": {"document_id": "units-length"},
                        },
                    },
                    {"role": "tool", "content": "100"},
                    {"role": "assistant", "content": "100<eos>"},
                ],
            }
        ]
        original_attempts_sha256 = sha256_bytes(canonical_json_bytes(attempts))
        exported = export_sft_examples(
            attempts,
            output_dir=root / "export",
            tokenizer_name="test-byte-tokenizer",
            tokenizer_revision="v1",
            template_version="tool-chat-v1",
            tokenizer=_FixtureChatTokenizer(),
        )
        source_record_id = imported.records[0].source_record_id
        publication = publish_dataset(
            dataset_id="us1-fixture-release",
            members=[
                {
                    "task_id": "fixture-task",
                    "attempt_id": "fixture-attempt",
                    "source_record_ids": [source_record_id],
                    "usage_scope": "TEST",
                    "verification_status": "VERIFIED",
                    "outcome": "PASS",
                    "decision": "ACCEPT",
                }
            ],
            output_dir=root / "releases",
            input_manifest_hash=sha256_file(source_report),
            rule_version="quality-v1",
        )
        revocation = revoke_source(
            source_record_id, releases_root=root / "releases", ledger_root=root / "revocations"
        )
        checks = {
            "historical_import_preserved_raw_failure": len(imported.records) == 1
            and len(imported.quarantine) == 1,
            "historical_import_remains_non_executable": imported.records[0].usage_scope
            == "HISTORICAL_ONLY",
            "pilot_rebuild_has_one_hundred_drafts": len(build.tasks) == 100
            and all(task.status.value == "DRAFT" for task in build.tasks),
            "sft_mask_has_model_output_only": exported.examples[0].role_loss_counts["tool"] == 0
            and exported.examples[0].role_loss_counts["assistant"] > 0,
            "sft_export_did_not_mutate_source": original_attempts_sha256
            == sha256_bytes(canonical_json_bytes(attempts)),
            "revocation_propagates_without_rewriting_release": revocation.affected_dataset_ids
            == [publication.dataset_id]
            and publication.path.joinpath("dataset_manifest.json").is_file(),
        }
    if not all(checks.values()):
        raise RuntimeError("US1 checkpoint invariant failed")
    receipt = {
        "checkpoint": "US1_SOFTWARE",
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_level": "SOFTWARE_VALIDATED",
        "counts": {
            "historical_records_imported": 1,
            "historical_records_quarantined": 1,
            "pilot_draft_tasks": 100,
            "fixture_sft_examples": 1,
            "fixture_revocation_impacts": 1,
        },
        "checks": checks,
        "input_hashes": {
            "source_report": sha256_file(source_report),
            "dedup_review_summary": sha256_file(dedup_review_summary),
            "equivalence_manifest": sha256_file(equivalence_manifest),
            "task_config": sha256_file(task_config),
        },
        "limitations": [
            "Historical Toucan data remains HISTORICAL_ONLY and was not published.",
            "The 100 pilot tasks are DRAFT and were not executed or independently verified.",
            "No training-eligible release, model execution, training result, or model-value claim is evidenced.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_json_bytes(receipt))
    return receipt
