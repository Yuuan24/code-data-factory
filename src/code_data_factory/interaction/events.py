"""Append-only, content-addressed interaction event persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes


class EventLedger:
    """Records actual interaction boundaries; it never reconstructs them from agent memory."""

    def __init__(self, output_dir: Path, *, attempt_id: str, task_id: str) -> None:
        self.output_dir = output_dir
        self.attempt_id = attempt_id
        self.task_id = task_id
        self.events: list[dict[str, object]] = []
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _record(
        self,
        event_type: str,
        payload: object,
        *,
        model_call_id: str | None = None,
        tool_call_id: str | None = None,
        status: str = "COMPLETE",
    ) -> str:
        event_id = str(uuid4())
        payload_bytes = canonical_json_bytes(payload)
        payload_path = self.output_dir / "payloads" / f"{event_id}.json"
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_bytes(payload_bytes)
        self.events.append(
            {
                "event_id": event_id,
                "attempt_id": self.attempt_id,
                "seq": len(self.events),
                "event_type": event_type,
                "timestamp": datetime.now(UTC).isoformat(),
                "model_call_id": model_call_id,
                "tool_call_id": tool_call_id,
                "status": status,
                "payload_ref": {
                    "uri": payload_path.relative_to(self.output_dir).as_posix(),
                    "sha256": sha256_bytes(payload_bytes),
                    "byte_size": len(payload_bytes),
                },
            }
        )
        return event_id

    def record_model_request(self, actual_visible_input: object) -> str:
        model_call_id = str(uuid4())
        self._record("MODEL_REQUEST", actual_visible_input, model_call_id=model_call_id)
        return model_call_id

    def record_model_output(self, model_call_id: str, raw_output: object) -> str:
        return self._record("MODEL_OUTPUT", raw_output, model_call_id=model_call_id)

    def record_tool_call(self, tool_name: str, arguments: object) -> str:
        tool_call_id = str(uuid4())
        self._record("TOOL_CALL", {"tool_name": tool_name, "arguments": arguments}, tool_call_id=tool_call_id)
        return tool_call_id

    def record_tool_result(self, tool_call_id: str, raw_result: object) -> str:
        return self._record("TOOL_RESULT", raw_result, tool_call_id=tool_call_id)

    def record_interruption(self, reason: str) -> str:
        return self._record("INTERRUPTION", {"reason": reason}, status="INCOMPLETE")

    @staticmethod
    def retry_attempt_id(*, action_name: str) -> str:
        """Only a read-only action can be retried, and it always receives a new attempt identity."""
        if action_name not in {"search_documents", "read_document", "calculate", "convert"}:
            raise ValueError("only idempotent read-only actions may be retried")
        return str(uuid4())

    def seal(self, end_reason: str, *, final_output: object | None = None) -> dict[str, object]:
        if end_reason not in {"COMPLETED", "BUDGET_TRUNCATED", "ENVIRONMENT_ERROR", "CANCELLED", "INTERRUPTED"}:
            raise ValueError("unrecognised end reason")
        if final_output is not None:
            self._record("FINAL_OUTPUT", final_output)
        manifest: dict[str, object] = {
            "attempt_id": self.attempt_id,
            "task_id": self.task_id,
            "sealed_at": datetime.now(UTC).isoformat(),
            "end_reason": end_reason,
            "events": self.events,
        }
        (self.output_dir / "manifest.json").write_bytes(canonical_json_bytes(manifest))
        return manifest
