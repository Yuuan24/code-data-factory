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

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes
from code_data_factory.contracts.tasks import TaskPackage
from code_data_factory.datasets.build import build_draft
from code_data_factory.datasets.build_input import BuildInputError, load_build_input
from code_data_factory.datasets.export_sft import ExportError, export_sft_examples
from code_data_factory.datasets.publish import PublicationGateError, publish_dataset
from code_data_factory.interaction.environment import check_environment
from code_data_factory.interaction.pilot import execute_fixed_actions, load_facts
from code_data_factory.interaction.replay import inspect_manifest
from code_data_factory.sources.audit import audit_sources, freeze_document_sources
from code_data_factory.sources.revoke import revoke_source
from code_data_factory.sources.toucan import import_toucan_records, write_import_result
from code_data_factory.tasks.build import build_pilot_tasks
from code_data_factory.tasks.splits import SplitRegistry
from code_data_factory.verification.pilot import verify_pilot_attempts

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
    parser.add_argument("--execution-config", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--adapter")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--backend", choices=("local", "ray"))
    parser.add_argument("--draft", type=Path)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--attempts", type=Path)
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


def _load_task_packages(path: Path) -> list[TaskPackage]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("task manifest must contain tasks")
    return [TaskPackage.model_validate(item) for item in items]


def _resumed_build(output: Path, *, run_id: str, backend: str, input_manifest_hash: str) -> tuple[int, int] | None:
    """Return a completed identical build, or let an incomplete one resume normally."""

    receipt_path = output / "build_receipt.json"
    if not receipt_path.is_file():
        return None
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict) or any(
        receipt.get(field) != expected
        for field, expected in {
            "run_id": run_id,
            "backend": backend,
            "input_manifest_hash": input_manifest_hash,
        }.items()
    ):
        raise ValueError("--resume conflicts with the completed build receipt")
    membership = output / "membership.json"
    decisions = output / "quality_decisions.json"
    if not membership.is_file() or not decisions.is_file():
        raise ValueError("--resume found an incomplete completed-build receipt")
    member_count = receipt.get("member_count")
    accepted_count = receipt.get("accepted_count")
    if not isinstance(member_count, int) or not isinstance(accepted_count, int):
        raise ValueError("--resume found an invalid completed-build receipt")
    return member_count, accepted_count


def _execute(parsed: argparse.Namespace, run_id: str) -> CommandEnvelope:
    command = " ".join(parsed.command)
    if parsed.dry_run:
        return CommandEnvelope(command, run_id, "VALIDATED", "UNVERIFIED", [], {}, [], [])
    output = _require_output(parsed)
    if parsed.command == ["environment", "check"]:
        if parsed.config is None:
            raise ValueError("environment check requires --config")
        preflight = check_environment(parsed.config)
        output.mkdir(parents=True, exist_ok=True)
        preflight_path = output / "preflight.json"
        preflight_path.write_text(
            json.dumps({"status": preflight.status, "findings": preflight.findings}, sort_keys=True),
            encoding="utf-8",
        )
        if preflight.status != "PASSED":
            return CommandEnvelope(
                command,
                run_id,
                "GATE_FAILED",
                "UNVERIFIED",
                [str(preflight_path)],
                {},
                ["Linux non-root platform-container preflight did not pass"],
                [],
            )
        return _completed(command, run_id, [preflight_path], {"checks": len(preflight.findings)})
    if parsed.command == ["trajectory", "inspect"]:
        manifest_path = parsed.attempts or parsed.input
        if manifest_path is None:
            raise ValueError("trajectory inspect requires --attempts")
        inspection = inspect_manifest(manifest_path)
        output.mkdir(parents=True, exist_ok=True)
        inspect_path = output / "inspection.json"
        inspect_path.write_text(json.dumps(inspection, sort_keys=True), encoding="utf-8")
        event_count = inspection["event_count"]
        if not isinstance(event_count, int):
            raise ValueError("trajectory inspection returned an invalid event count")
        return _completed(command, run_id, [inspect_path], {"events": event_count})
    if parsed.command == ["trajectory", "collect"]:
        if parsed.tasks is None or parsed.config is None:
            raise ValueError("trajectory collect requires --tasks and --config")
        preflight = check_environment(parsed.execution_config or parsed.config)
        if preflight.status != "PASSED":
            return CommandEnvelope(
                command,
                run_id,
                "GATE_FAILED",
                "UNVERIFIED",
                [],
                {},
                ["fixed-action collection requires a passed Linux platform-container preflight"],
                [],
            )
        config = yaml.safe_load(parsed.config.read_text(encoding="utf-8"))
        facts_value = config.get("facts_config") if isinstance(config, dict) else None
        if not isinstance(facts_value, str):
            raise ValueError("collection config requires facts_config")
        tasks = _load_task_packages(parsed.tasks)
        execute_fixed_actions(
            tasks,
            facts=load_facts(parsed.config.parent / facts_value),
            output_dir=output,
            task_assets_root=parsed.tasks.parent,
            preflight=preflight,
        )
        return _completed(command, run_id, [output / "manifest.json"], {"tasks": len(tasks), "attempts": len(tasks) * 2})
    if parsed.command == ["verify", "run"]:
        if parsed.tasks is None or parsed.attempts is None or parsed.config is None:
            raise ValueError("verify run requires --tasks, --attempts, and --config")
        config = yaml.safe_load(parsed.config.read_text(encoding="utf-8"))
        version = config.get("verifier_version") if isinstance(config, dict) else None
        if not isinstance(version, str):
            raise ValueError("verifier config requires verifier_version")
        manifest = verify_pilot_attempts(
            tasks=_load_task_packages(parsed.tasks),
            task_assets_root=parsed.tasks.parent,
            attempts_manifest=parsed.attempts,
            output_dir=output,
            verifier_version=version,
        )
        attempt_count = manifest["attempt_count"]
        if not isinstance(attempt_count, int):
            raise ValueError("verification manifest returned an invalid attempt count")
        return _completed(command, run_id, [output / "manifest.json"], {"attempts": attempt_count})
    if parsed.command == ["trajectory", "replay"]:
        raise ValueError(
            f"{command} is fail-closed until a verified execution environment and its task-specific input manifest are supplied"
        )
    if parsed.command == ["source", "audit"]:
        if parsed.manifest is None:
            raise ValueError("source audit requires --manifest")
        report = audit_sources(parsed.manifest, output_dir=output, fetch_remote=True)
        return _completed(command, run_id, [output / "source_report.json"], {"sources": len(report.sources)})
    if parsed.command == ["source", "freeze"]:
        if parsed.manifest is None:
            raise ValueError("source freeze requires --manifest")
        frozen_manifest = freeze_document_sources(parsed.manifest, output_dir=output)
        return _completed(command, run_id, [frozen_manifest], {"sources": len(json.loads(frozen_manifest.read_text(encoding="utf-8"))["sources"])})
    if parsed.command == ["source", "revoke"]:
        if not parsed.source_record_id:
            raise ValueError("source revoke requires --source-record-id")
        ledger = revoke_source(
            parsed.source_record_id,
            releases_root=Path("data/releases"),
            ledger_root=output,
            runs_root=Path("artifacts/runs"),
            claims_root=Path("artifacts/claims"),
        )
        return _completed(
            command,
            run_id,
            [ledger.path],
            {
                "affected_datasets": len(ledger.affected_dataset_ids),
                "affected_runs": len(ledger.affected_run_ids),
                "affected_claims": len(ledger.affected_claim_ids),
            },
        )
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
        paths = write_import_result(import_result, output_dir=output)
        summary = output / "import_summary.json"
        summary.write_text(
            json.dumps(
                {
                    "records": len(import_result.records),
                    "external_demonstrations": len(import_result.demonstrations),
                    "quarantine": len(import_result.quarantine),
                }
            ),
            encoding="utf-8",
        )
        return _completed(
            command,
            run_id,
            [summary, *paths.values()],
            {
                "records": len(import_result.records),
                "external_demonstrations": len(import_result.demonstrations),
                "quarantine": len(import_result.quarantine),
            },
        )
    if parsed.command == ["data", "build"]:
        if parsed.input is None or parsed.backend is None:
            raise ValueError("data build requires --input and --backend")
        build_input = load_build_input(parsed.input)
        input_manifest_hash = sha256_bytes(canonical_json_bytes(build_input.content_hashes))
        if parsed.resume:
            resumed = _resumed_build(
                output,
                run_id=run_id,
                backend=parsed.backend,
                input_manifest_hash=input_manifest_hash,
            )
            if resumed is not None:
                members, accepted = resumed
                return _completed(
                    command,
                    run_id,
                    [output / "build_receipt.json", output / "membership.json", output / "quality_decisions.json"],
                    {"inputs": len(build_input.content_hashes), "members": members, "accepted": accepted},
                )
        result = build_draft(build_input=build_input, output_dir=output, backend=parsed.backend, run_id=run_id)
        return _completed(command, run_id, [output / "build_receipt.json", output / "membership.json", output / "quality_decisions.json"], {"inputs": len(build_input.content_hashes), "members": result.member_count})
    if parsed.command == ["dataset", "publish"]:
        if parsed.draft is None:
            raise ValueError("dataset publish requires --draft")
        members = json.loads(parsed.draft.read_text(encoding="utf-8"))
        if not isinstance(members, list):
            raise ValueError("--draft must contain a JSON member list")
        external = bool(members) and all("demonstration_id" in member for member in members)
        if external and parsed.config is None:
            raise ValueError("external dataset publish requires --config with the frozen eligibility policy")
        rule_version = "quality-v1"
        if parsed.config is not None:
            config = yaml.safe_load(parsed.config.read_text(encoding="utf-8"))
            configured_rule = config.get("policy_version") if isinstance(config, dict) else None
            if not isinstance(configured_rule, str) or not configured_rule:
                raise ValueError("dataset publish config requires policy_version")
            rule_version = configured_rule
        publication = publish_dataset(
            dataset_id="external" if external else "software-draft",
            members=members,
            output_dir=output,
            input_manifest_hash=sha256_bytes(canonical_json_bytes(members)),
            rule_version=rule_version,
        )
        return _completed(command, run_id, [publication.path / "dataset_manifest.json"], {"members": len(members)})
    if parsed.command == ["dataset", "export-sft"]:
        if parsed.dataset is None or parsed.config is None:
            raise ValueError("dataset export-sft requires --dataset and --config")
        attempts = json.loads(parsed.dataset.read_text(encoding="utf-8"))
        config = yaml.safe_load(parsed.config.read_text(encoding="utf-8"))
        export_result = export_sft_examples(attempts, output_dir=output, tokenizer_name=config["tokenizer_name"], tokenizer_revision=config["tokenizer_revision"], template_version=config["template_version"], template_sha256=config.get("template_sha256"))
        return _completed(command, run_id, [output / "loss_mask_audit.json"], {"examples": len(export_result.examples)})
    raise ValueError("unsupported command; expected source/task/trajectory/data/dataset US1 subcommand")


def main(argv: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(argv)
    command = " ".join(parsed.command)
    run_id = parsed.resume if parsed.command == ["data", "build"] and parsed.resume else str(uuid.uuid4())
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
    return EXIT_GATE_FAILED if envelope.status == "GATE_FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
