"""Narrow, controlled state snapshots for the supported session workspace only."""

from __future__ import annotations

import ast
import json
import random
from pathlib import Path
from uuid import uuid4

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes


class CheckpointError(RuntimeError):
    """A restore request is outside the one supported controlled workspace."""


class SessionWorkspace:
    """A read-only document bundle plus a separately mutable session-state directory."""

    def __init__(self, root: Path, *, initial_documents: dict[str, str]) -> None:
        if not initial_documents or any(not key or not isinstance(value, str) for key, value in initial_documents.items()):
            raise CheckpointError("controlled workspace requires non-empty named documents")
        self.root = root
        self.documents_root = root / "documents"
        self.session_path = root / "session.json"
        self.documents_root.mkdir(parents=True, exist_ok=True)
        for document_id, content in initial_documents.items():
            path = self.documents_root / f"{document_id}.txt"
            path.write_text(content, encoding="utf-8")
            path.chmod(0o444)
        if not self.session_path.exists():
            self._write_session({})

    def _read_session(self) -> dict[str, str]:
        value = json.loads(self.session_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
            raise CheckpointError("controlled session state is invalid")
        return value

    def _write_session(self, state: dict[str, str]) -> None:
        self.session_path.write_bytes(canonical_json_bytes(state))

    def read_document(self, document_id: str) -> str:
        path = self.documents_root / f"{document_id}.txt"
        if not path.is_file():
            raise CheckpointError("document is not available in this controlled workspace")
        return path.read_text(encoding="utf-8")

    def write_document(self, document_id: str, content: str) -> None:
        del document_id, content
        raise CheckpointError("controlled corpus is read-only")

    def read_session_value(self, key: str) -> str | None:
        return self._read_session().get(key)

    def write_session_value(self, key: str, value: str) -> None:
        if not key or not isinstance(value, str):
            raise CheckpointError("session values require a non-empty key and string value")
        state = self._read_session()
        state[key] = value
        self._write_session(state)

    def snapshot(self, *, attempt_id: str, event_seq: int) -> dict[str, object]:
        if not attempt_id or event_seq < 0:
            raise CheckpointError("snapshot requires an attempt identity and non-negative event sequence")
        document_bytes = canonical_json_bytes(
            {path.stem: path.read_text(encoding="utf-8") for path in sorted(self.documents_root.glob("*.txt"))}
        )
        snapshot = {
            "checkpoint_id": str(uuid4()),
            "attempt_id": attempt_id,
            "event_seq": event_seq,
            "workspace_kind": "CONTROLLED_SESSION_WORKSPACE",
            "documents_sha256": sha256_bytes(document_bytes),
            "session": self._read_session(),
            "random_state": repr(random.getstate()),
        }
        snapshot_path = self.root / "checkpoints" / f"{snapshot['checkpoint_id']}.json"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_bytes(canonical_json_bytes(snapshot))
        snapshot["snapshot_path"] = snapshot_path.as_posix()
        return snapshot

    def restore(
        self,
        snapshot: dict[str, object],
        *,
        parent_attempt_id: str,
        branch_event_id: str,
    ) -> dict[str, object]:
        if snapshot.get("workspace_kind") != "CONTROLLED_SESSION_WORKSPACE":
            raise CheckpointError("UNSUPPORTED_CAPABILITY: snapshot does not describe the controlled workspace")
        if snapshot.get("attempt_id") != parent_attempt_id or not branch_event_id:
            raise CheckpointError("restore must link its parent attempt and branch event")
        documents = {path.stem: path.read_text(encoding="utf-8") for path in sorted(self.documents_root.glob("*.txt"))}
        if sha256_bytes(canonical_json_bytes(documents)) != snapshot.get("documents_sha256"):
            raise CheckpointError("controlled workspace documents changed since snapshot")
        session = snapshot.get("session")
        random_state = snapshot.get("random_state")
        if not isinstance(session, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in session.items()):
            raise CheckpointError("snapshot session state is invalid")
        if not isinstance(random_state, str):
            raise CheckpointError("snapshot random state is invalid")
        self._write_session(session)
        random.setstate(ast.literal_eval(random_state))
        return {
            "attempt_id": str(uuid4()),
            "parent_attempt_id": parent_attempt_id,
            "branch_event_id": branch_event_id,
            "restore_capability": "SUPPORTED",
            "checkpoint_id": snapshot.get("checkpoint_id"),
        }

    @staticmethod
    def unsupported_restore(environment_kind: str) -> None:
        raise CheckpointError(f"UNSUPPORTED_CAPABILITY: {environment_kind} does not support controlled restore")
