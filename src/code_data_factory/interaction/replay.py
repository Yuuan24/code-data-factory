"""Separate log inspection from frozen fixed-action replay."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path


def inspect_manifest(manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("events"), list):
        raise ValueError("manifest must contain recorded events")
    return {"attempt_id": manifest.get("attempt_id"), "event_count": len(manifest["events"]), "end_reason": manifest.get("end_reason")}


def replay_fixed_actions(manifest_path: Path, *, environment_available: bool, execute: Callable[[dict[str, object]], object]) -> list[object]:
    if not environment_available:
        raise RuntimeError("UNSUPPORTED_CAPABILITY: original frozen environment is unavailable")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output: list[object] = []
    for event in manifest.get("events", []):
        if event.get("event_type") == "TOOL_CALL":
            output.append(execute(event))
    return output


def replay_receipt(
    manifest_path: Path,
    *,
    environment_available: bool,
    execute: Callable[[dict[str, object]], object],
) -> dict[str, object]:
    """Write no historical event: replay is a new attempt with an explicit result comparison."""
    original = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = replay_fixed_actions(manifest_path, environment_available=environment_available, execute=execute)
    return {
        "parent_attempt_id": original.get("attempt_id"),
        "replay_attempt_id": f"replay-{original.get('attempt_id')}",
        "fixed_action_count": len(results),
        "original_end_reason": original.get("end_reason"),
        "replay_results": results,
    }
