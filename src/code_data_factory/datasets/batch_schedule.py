"""Deterministic, whole-example SFT batch schedules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes


class BatchScheduleError(ValueError):
    """The two recipes cannot be made exactly comparable without altering targets."""


@dataclass(frozen=True)
class ScheduledExample:
    demonstration_id: str
    input_ids: tuple[int, ...]
    loss_mask: tuple[bool, ...]

    @property
    def loss_tokens(self) -> int:
        return sum(self.loss_mask)


def load_sft_examples(path: Path, *, selected_ids: set[str]) -> list[ScheduledExample]:
    """Read frozen exported examples and reject missing or truncated selections."""
    rows = pq.read_table(path).to_pylist()
    selected: list[ScheduledExample] = []
    found: set[str] = set()
    for row in rows:
        demonstration_id = row.get("demonstration_id")
        input_ids, loss_mask = row.get("input_ids"), row.get("loss_mask")
        if demonstration_id not in selected_ids:
            continue
        if (
            not isinstance(demonstration_id, str)
            or not isinstance(input_ids, list)
            or not isinstance(loss_mask, list)
        ):
            raise BatchScheduleError("SFT view has invalid token columns")
        if len(input_ids) != len(loss_mask) or not input_ids or not any(loss_mask):
            raise BatchScheduleError("SFT view needs complete non-empty target masks")
        selected.append(
            ScheduledExample(
                demonstration_id,
                tuple(int(value) for value in input_ids),
                tuple(bool(value) for value in loss_mask),
            )
        )
        found.add(demonstration_id)
    missing = selected_ids - found
    if missing:
        raise BatchScheduleError(
            f"selected recipe demonstrations are absent from frozen SFT view: {sorted(missing)}"
        )
    return sorted(selected, key=lambda item: item.demonstration_id)


def _cycle(examples: list[ScheduledExample], count: int) -> list[ScheduledExample]:
    return [examples[index % len(examples)] for index in range(count)]


def build_equal_schedule(
    *,
    random_examples: list[ScheduledExample],
    closed_loop_examples: list[ScheduledExample],
    batch_size: int,
    steps: int,
    max_context_tokens: int,
    output_path: Path,
) -> dict[str, object]:
    """Use complete messages only; exact equality is required, never padded target tokens."""
    if batch_size < 1 or steps < 1 or max_context_tokens < 1:
        raise BatchScheduleError("batch size, steps, and context length must be positive")
    slots = batch_size * steps
    filtered = {
        "random": [item for item in random_examples if len(item.input_ids) <= max_context_tokens],
        "closed_loop": [
            item for item in closed_loop_examples if len(item.input_ids) <= max_context_tokens
        ],
    }
    if not filtered["random"] or not filtered["closed_loop"]:
        raise BatchScheduleError("no complete recipe example fits the frozen context window")
    schedules = {name: _cycle(rows, slots) for name, rows in filtered.items()}
    totals = {name: sum(item.loss_tokens for item in rows) for name, rows in schedules.items()}
    if totals["random"] != totals["closed_loop"]:
        raise BatchScheduleError(
            "whole-example schedule cannot exactly match effective loss tokens; jointly downgrade or reject"
        )
    payload: dict[str, object] = {
        "kind": "equal-sft-batch-schedule",
        "batch_size": batch_size,
        "optimizer_steps": steps,
        "max_context_tokens": max_context_tokens,
        "effective_loss_tokens": totals["random"],
        "recipes": {
            name: [
                {
                    "demonstration_id": item.demonstration_id,
                    "input_tokens": len(item.input_ids),
                    "loss_tokens": item.loss_tokens,
                }
                for item in rows
            ]
            for name, rows in schedules.items()
        },
        "no_target_padding": True,
        "complete_trajectory_only": True,
    }
    payload["schedule_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_json_bytes(payload))
    return payload


def recipe_ids(path: Path) -> tuple[set[str], set[str]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BatchScheduleError("recipe draft must be an object")
    random_rows, closed_rows = value.get("random_matched"), value.get("closed_loop")
    if (
        not isinstance(random_rows, list)
        or not isinstance(closed_rows, list)
        or not random_rows
        or not closed_rows
    ):
        raise BatchScheduleError("recipe draft needs both non-empty recipes")

    def ids(rows: list[Any]) -> set[str]:
        result = {row.get("demonstration_id") for row in rows if isinstance(row, dict)}
        if not result or not all(isinstance(item, str) and item for item in result):
            raise BatchScheduleError("recipe entries require stable demonstration identities")
        return {item for item in result if isinstance(item, str)}

    return ids(random_rows), ids(closed_rows)
