"""Small, fail-closed command envelope for the future pipeline commands."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

EXIT_INPUT_ERROR = 2
EXIT_DEPENDENCY_ERROR = 3
EXIT_INFRASTRUCTURE_ERROR = 4
EXIT_CANCELLED = 5
EXIT_INTEGRITY_ERROR = 6
EXIT_BUDGET_ERROR = 7
EXIT_GATE_FAILED = 8

IMPLEMENTATION_ROOTS = {
    "source",
    "task",
    "trajectory",
    "data",
    "dataset",
    "environment",
    "verify",
    "reward",
    "compatibility",
    "benchmark",
    "evaluate",
    "feedback",
    "experiment",
    "report",
    "evidence",
    "reproduce",
}


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
    parser.add_argument("--json", action="store_true", help="emit the structured command envelope")
    parser.add_argument("--output-dir", type=Path, help="reserved artifact output directory")
    parser.add_argument(
        "--dry-run", action="store_true", help="validate only; never issues execution evidence"
    )
    parser.add_argument("command", nargs="*", help="pipeline command and subcommand")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(argv)
    command = " ".join(parsed.command)
    if not command:
        return 0
    root = parsed.command[0]
    run_id = str(uuid.uuid4())
    if root not in IMPLEMENTATION_ROOTS:
        _emit(
            CommandEnvelope(
                command=command,
                run_id=run_id,
                status="INPUT_ERROR",
                evidence_level="UNVERIFIED",
                artifact_refs=[],
                counts={},
                warnings=[],
                errors=[f"unknown command root: {root}"],
            ),
            parsed.json,
        )
        return EXIT_INPUT_ERROR
    detail = (
        "dry-run validation is not implemented"
        if parsed.dry_run
        else "business command is not implemented"
    )
    _emit(
        CommandEnvelope(
            command=command,
            run_id=run_id,
            status="GATE_FAILED",
            evidence_level="UNVERIFIED",
            artifact_refs=[],
            counts={},
            warnings=[],
            errors=[detail],
        ),
        parsed.json,
    )
    return EXIT_GATE_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
