"""One deterministic event transformation for local Python and Ray Data."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from logging import ERROR
from typing import Any

from code_data_factory.contracts.artifacts import sha256_bytes


@dataclass(frozen=True)
class BackendResult:
    rows: list[dict[str, Any]]
    backend: str


def _normalise_event(row: dict[str, Any], observation_inline_limit: int) -> dict[str, Any]:
    value = dict(row)
    payload = value.get("payload")
    if value.get("event_type") == "OBSERVATION" and isinstance(payload, str):
        encoded = payload.encode("utf-8")
        if len(encoded) > observation_inline_limit:
            value["payload"] = None
            value["payload_ref"] = {
                "sha256": sha256_bytes(encoded),
                "byte_size": len(encoded),
                "media_type": "text/plain",
            }
    return value


def process_events(
    events: list[dict[str, Any]], *, backend: str, observation_inline_limit: int
) -> BackendResult:
    """Apply the same safe event projection on local Python or Ray Data.

    No generated code is accepted as a transform: the only transform is this
    package-owned function and its fixed byte limit.
    """

    if observation_inline_limit <= 0:
        raise ValueError("observation_inline_limit must be positive")
    if backend == "local":
        rows = [_normalise_event(row, observation_inline_limit) for row in events]
    elif backend == "ray":
        try:
            import ray
        except ImportError as error:
            raise RuntimeError("ray data dependency is required") from error
        # When invoked through `uv run`, Ray otherwise recursively launches
        # workers through uv, which can stall while it re-resolves the project.
        os.environ.setdefault("RAY_PYTHON_EXECUTABLE", sys.executable)
        ray.init(
            ignore_reinit_error=True,
            include_dashboard=False,
            logging_level=ERROR,
            num_cpus=1,
        )
        try:
            rows = ray.data.from_items(events).map(
                lambda row: _normalise_event(row, observation_inline_limit)
            ).take_all()
        finally:
            ray.shutdown()
    else:
        raise ValueError("backend must be local or ray")
    rows.sort(key=lambda row: (str(row["attempt_id"]), int(row["seq"])))
    return BackendResult(rows=rows, backend=backend)
