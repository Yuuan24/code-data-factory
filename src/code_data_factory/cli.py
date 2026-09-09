"""Fail-closed command envelope for the implemented US1 data-governance slice."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import yaml

from code_data_factory.datasets.build import build_draft
from code_data_factory.datasets.build_input import BuildInputError, load_build_input
from code_data_factory.datasets.export_sft import ExportError, export_sft_examples
from code_data_factory.datasets.publish import PublicationGateError, publish_dataset
from code_data_factory.sources.audit import audit_sources
from code_data_factory.sources.revoke import revoke_source
from code_data_factory.sources.toucan import import_toucan_records
from code_data_factory.tasks.build import build_pilot_tasks
from code_data_factory.tasks.splits import SplitRegistry

EXIT_INPUT_ERROR = 2
EXIT_DEPENDENCY_ERROR = 3
EXIT_INFRASTRUCTURE_ERROR = 4
EXIT_CANCELLED = 5
EXIT_INTEGRITY_ERROR = 6
EXIT_BUDGET_ERROR = 7
EXIT_GATE_FAILED = 8


@dataclass(frozen=True)
class CommandEnvelope:
    command: str
    run_id: str
    status: str
    evidence_level: str
    artifact_refs: list[str]
    counts: dict[str, int]
    warnings: list[str]
    errors: list[str]


def _emit(envelope: CommandEnvelope, as_json: bool) -> None:
    payload = asdict(envelope)
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"{envelope.command}: {envelope.status} ({envelope.run_id})")
    for error in envelope.errors:
        print(error, file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cdf", description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--adapter")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--backend", choices=("local", "ray"))
    parser.add_argument("--draft", type=Path)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--resume")
    parser.add_argument("--source-record-id")
    parser.add_argument("command", nargs="*")
    return parser


def _require_output(parsed: argparse.Namespace) -> Path:
    if parsed.output_dir is None:
        raise ValueError("--output-dir is required")
    return cast(Path, parsed.output_dir)


def _completed(command: str, run_id: str, paths: list[Path], counts: dict[str, int]) -> CommandEnvelope:
    return CommandEnvelope(command, run_id, "COMPLETED", "SOFTWARE_VALIDATED", [str(path) for path in paths], counts, [], [])


def _execute(parsed: argparse.Namespace, run_id: str) -> CommandEnvelope:
    command = " ".join(parsed.command)
    if parsed.dry_run:
        return CommandEnvelope(command, run_id, "VALIDATED", "UNVERIFIED", [], {}, [], [])
    output = _require_output(parsed)
    if parsed.command == ["source", "audit"]:
        if parsed.manifest is None:
            raise ValueError("source audit requires --manifest")
        report = audit_sources(parsed.manifest, output_dir=output, fetch_remote=True)
        return _completed(command, run_id, [output / "source_report.json"], {"sources": len(report.sources)})
    if parsed.command == ["source", "revoke"]:
        if not parsed.source_record_id:
            raise ValueError("source revoke requires --source-record-id")
        ledger = revoke_source(parsed.source_record_id, releases_root=Path("data/releases"), ledger_root=output)
        return _completed(command, run_id, [ledger.path], {"affected_datasets": len(ledger.affected_dataset_ids)})
    if parsed.command == ["task", "build"]:
        if parsed.config is None:
            raise ValueError("task build requires --config")
        task_result = build_pilot_tasks(parsed.config, output_dir=output, producer_run_id=run_id, split_registry=SplitRegistry(policy_version="split-v1"))
        return _completed(
            command,
            run_id,
            [output / name for name in ("task_manifest.json", "source_manifest.json", "attempt_manifest.json", "verification_manifest.json", "split_registry.json")],
            {"tasks": len(task_result.tasks), "task_assets": len(list((output / "task-assets").glob("*.json")) )},
        )
    if parsed.command == ["trajectory", "import"]:
        if parsed.source is None or parsed.adapter != "toucan":
            raise ValueError("trajectory import requires --source and --adapter toucan")
        import_result = import_toucan_records(parsed.source, snapshot_id="toucan-import", producer_run_id=run_id)
        output.mkdir(parents=True, exist_ok=True)
        summary = output / "import_summary.json"
        summary.write_text(json.dumps({"records": len(import_result.records), "quarantine": len(import_result.quarantine)}), encoding="utf-8")
        return _completed(command, run_id, [summary], {"records": len(import_result.records), "quarantine": len(import_result.quarantine)})
    if parsed.command == ["data", "build"]:
        if parsed.input is None or parsed.backend is None:
            raise ValueError("data build requires --input and --backend")
        build_input = load_build_input(parsed.input)
        result = build_draft(build_input=build_input, output_dir=output, backend=parsed.backend, run_id=run_id)
        return _completed(command, run_id, [output / "build_receipt.json", output / "membership.json", output / "quality_decisions.json"], {"inputs": len(build_input.content_hashes), "members": result.member_count})
    if parsed.command == ["dataset", "publish"]:
        if parsed.draft is None:
            raise ValueError("dataset publish requires --draft")
        members = json.loads(parsed.draft.read_text(encoding="utf-8"))
        if not isinstance(members, list):
            raise ValueError("--draft must contain a JSON member list")
        publication = publish_dataset(dataset_id="software-draft", members=members, output_dir=output, input_manifest_hash="0" * 64, rule_version="quality-v1")
        return _completed(command, run_id, [publication.path / "dataset_manifest.json"], {"members": len(members)})
    if parsed.command == ["dataset", "export-sft"]:
        if parsed.dataset is None or parsed.config is None:
            raise ValueError("dataset export-sft requires --dataset and --config")
        attempts = json.loads(parsed.dataset.read_text(encoding="utf-8"))
        config = yaml.safe_load(parsed.config.read_text(encoding="utf-8"))
        export_result = export_sft_examples(attempts, output_dir=output, tokenizer_name=config["tokenizer_name"], tokenizer_revision=config["tokenizer_revision"], template_version=config["template_version"])
        return _completed(command, run_id, [output / "loss_mask_audit.json"], {"examples": len(export_result.examples)})
    raise ValueError("unsupported command; expected source/task/trajectory/data/dataset US1 subcommand")


def main(argv: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(argv)
    command = " ".join(parsed.command)
    run_id = str(uuid.uuid4())
    if not parsed.command:
        return 0
    try:
        envelope = _execute(parsed, run_id)
    except (BuildInputError, ExportError, PublicationGateError, ValueError, FileNotFoundError, json.JSONDecodeError) as error:
        _emit(CommandEnvelope(command, run_id, "INPUT_ERROR", "UNVERIFIED", [], {}, [], [str(error)]), parsed.json)
        return EXIT_INPUT_ERROR
    except ImportError as error:
        _emit(CommandEnvelope(command, run_id, "DEPENDENCY_ERROR", "UNVERIFIED", [], {}, [], [str(error)]), parsed.json)
        return EXIT_DEPENDENCY_ERROR
    _emit(envelope, parsed.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
