"""Deterministic SFT export with token-level ownership masks."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import pyarrow as pa
import pyarrow.parquet as pq

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes


class ExportError(ValueError):
    """An attempt cannot produce a safe, complete SFT target view."""


class ChatTokenizer(Protocol):
    chat_template: str | None

    def apply_chat_template(
        self, conversation: list[dict[str, str]], *, tokenize: bool, add_generation_prompt: bool
    ) -> list[int]: ...

    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]: ...


@dataclass(frozen=True)
class SftExample:
    attempt_id: str
    task_id: str
    messages: list[dict[str, Any]]
    input_ids: list[int]
    loss_mask: list[bool]
    role_token_counts: dict[str, int]
    role_loss_counts: dict[str, int]
    control_token_count: int


def _content(message: dict[str, Any]) -> str:
    if "tool_call" in message:
        return json.dumps(message["tool_call"], sort_keys=True, separators=(",", ":"))
    content = message.get("content")
    if not isinstance(content, str):
        raise ExportError("message content must be text or a structured tool call")
    return content


def _load_tokenizer(name: str, revision: str) -> ChatTokenizer:
    try:
        from transformers import AutoTokenizer
    except ImportError as error:
        raise ExportError("transformers is required for a real SFT tokenizer") from error
    tokenizer = AutoTokenizer.from_pretrained(name, revision=revision)
    if not getattr(tokenizer, "chat_template", None):
        raise ExportError("frozen tokenizer does not provide a chat template")
    return tokenizer  # type: ignore[return-value]


def _template_message(message: dict[str, Any]) -> dict[str, str]:
    return {"role": str(message["role"]), "content": _content(message)}


def _render(tokenizer: ChatTokenizer, messages: list[dict[str, str]]) -> list[int]:
    value = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
    if hasattr(value, "get"):
        value = value.get("input_ids")
    if not isinstance(value, list) or not all(isinstance(token, int) for token in value):
        raise ExportError("tokenizer chat template did not produce token ids")
    return value


def export_sft_examples(
    attempts: list[dict[str, Any]],
    *,
    output_dir: Path,
    tokenizer_name: str,
    tokenizer_revision: str,
    template_version: str,
    tokenizer: ChatTokenizer | None = None,
    template_sha256: str | None = None,
) -> SftExportResult:
    """Write a reproducible SFT view without modifying source attempts."""

    if not tokenizer_name or not tokenizer_revision or not template_version:
        raise ExportError("a frozen tokenizer identity and template version are required")
    if any(bool(attempt.get("unknown_action_location")) for attempt in attempts):
        raise ExportError("unknown action location cannot be exported")
    active_tokenizer = tokenizer or _load_tokenizer(tokenizer_name, tokenizer_revision)
    template = active_tokenizer.chat_template
    if template_sha256 is not None and (template is None or sha256_bytes(template.encode("utf-8")) != template_sha256):
        raise ExportError("frozen tokenizer chat template digest mismatch")
    examples: list[SftExample] = []
    mappings: list[dict[str, Any]] = []
    for attempt in attempts:
        messages = attempt.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ExportError("attempt needs complete messages")
        template_messages: list[dict[str, str]] = []
        input_ids: list[int] = []
        loss_mask: list[bool] = []
        role_token_counts: dict[str, int] = {}
        role_loss_counts: dict[str, int] = {}
        controls = 0
        for message_index, message in enumerate(messages):
            if not isinstance(message, dict) or message.get("role") not in {"user", "assistant", "tool"}:
                raise ExportError("messages must use user, assistant, or tool roles")
            role = str(message["role"])
            prefix_ids = _render(active_tokenizer, template_messages) if template_messages else []
            rendered_message = _template_message(message)
            rendered_ids = _render(active_tokenizer, [*template_messages, rendered_message])
            if rendered_ids[: len(prefix_ids)] != prefix_ids:
                raise ExportError("chat template is not prefix-stable for this message sequence")
            encoded = rendered_ids[len(prefix_ids) :]
            if not encoded:
                raise ExportError("chat template produced an empty message span")
            model_output = role == "assistant"
            mask = [model_output] * len(encoded)
            input_ids.extend(encoded)
            loss_mask.extend(mask)
            role_token_counts[role] = role_token_counts.get(role, 0) + len(encoded)
            role_loss_counts[role] = role_loss_counts.get(role, 0) + sum(mask)
            if role == "assistant":
                content_ids = active_tokenizer.encode(
                    rendered_message["content"], add_special_tokens=False
                )
                controls += max(0, len(encoded) - len(content_ids))
            mappings.append(
                {
                    "attempt_id": str(attempt["attempt_id"]),
                    "message_index": message_index,
                    "role": role,
                    "target_token_count": sum(mask),
                }
            )
            template_messages.append(rendered_message)
        if input_ids != _render(active_tokenizer, template_messages):
            raise ExportError("chat template token boundaries are not reproducible")
        examples.append(
            SftExample(
                attempt_id=str(attempt["attempt_id"]),
                task_id=str(attempt["task_id"]),
                messages=messages,
                input_ids=input_ids,
                loss_mask=loss_mask,
                role_token_counts=role_token_counts,
                role_loss_counts=role_loss_counts,
                control_token_count=controls,
            )
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "attempt_id": example.attempt_id,
                    "task_id": example.task_id,
                    "messages_json": json.dumps(example.messages, sort_keys=True),
                    "input_ids": example.input_ids,
                    "loss_mask": example.loss_mask,
                    "tokenizer_name": tokenizer_name,
                    "tokenizer_revision": tokenizer_revision,
                    "template_version": template_version,
                }
                for example in examples
            ]
        ),
        output_dir / "training_examples.parquet",
    )
    pq.write_table(pa.Table.from_pylist(mappings), output_dir / "target_mapping.parquet")
    audit = {
        "tokenizer_name": tokenizer_name,
        "tokenizer_revision": tokenizer_revision,
        "template_version": template_version,
        "example_count": len(examples),
        "source_attempt_count": len(attempts),
        "source_digest": sha256_bytes(canonical_json_bytes(attempts)),
        "examples": [asdict(example) for example in examples],
    }
    (output_dir / "loss_mask_audit.json").write_bytes(canonical_json_bytes(audit))
    return SftExportResult(examples=examples, audit=audit)


@dataclass(frozen=True)
class SftExportResult:
    examples: list[SftExample]
    audit: dict[str, Any]
