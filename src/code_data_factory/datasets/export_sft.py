"""Deterministic SFT export with token-level ownership masks."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import pyarrow as pa
import pyarrow.parquet as pq

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes
from code_data_factory.processing.quality import EXTERNAL_PUBLICATION_REVIEW_CHECKS


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
    attempt_id: str | None
    demonstration_id: str | None
    task_id: str
    messages: list[dict[str, Any]]
    input_ids: list[int]
    loss_mask: list[bool]
    role_token_counts: dict[str, int]
    role_loss_counts: dict[str, int]
    control_token_count: int


def _content(message: dict[str, Any]) -> str:
    if message.get("tool_call") is not None:
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


def _unique_subsequence_start(haystack: list[int], needle: list[int]) -> int:
    """Find one exact content-token span or fail rather than mislabel context."""

    if not needle:
        raise ExportError("assistant message has no trainable content tokens")
    starts = [
        index
        for index in range(len(haystack) - len(needle) + 1)
        if haystack[index : index + len(needle)] == needle
    ]
    if len(starts) != 1:
        raise ExportError("chat template cannot map assistant content to one token span")
    return starts[0]


def _fallback_content_masks(
    tokenizer: ChatTokenizer, *, input_ids: list[int], messages: list[dict[str, str]]
) -> tuple[list[bool], dict[int, int], dict[str, int], int]:
    """Mask exact assistant content when a tokenizer rewrites adjacent turns.

    Some official tool-use templates reformat earlier assistant turns when a
    following tool call is appended, so cumulative prefix subtraction is not
    valid.  A unique content-token match preserves the full official rendering
    and fails closed if a source answer could be confused with context.
    """

    mask = [False] * len(input_ids)
    message_loss_counts: dict[int, int] = {}
    role_token_counts: dict[str, int] = {}
    source_content_tokens = 0
    for index, message in enumerate(messages):
        role = message["role"]
        content_ids = tokenizer.encode(message["content"], add_special_tokens=False)
        role_token_counts[role] = role_token_counts.get(role, 0) + len(content_ids)
        source_content_tokens += len(content_ids)
        if role != "assistant":
            message_loss_counts[index] = 0
            continue
        start = _unique_subsequence_start(input_ids, content_ids)
        if any(mask[start : start + len(content_ids)]):
            raise ExportError("assistant content spans overlap in the rendered chat template")
        mask[start : start + len(content_ids)] = [True] * len(content_ids)
        message_loss_counts[index] = len(content_ids)
    if not any(mask):
        raise ExportError("chat template produced no assistant target tokens")
    return mask, message_loss_counts, role_token_counts, len(input_ids) - source_content_tokens


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
        demonstration_id = attempt.get("demonstration_id")
        if demonstration_id is not None:
            if not isinstance(demonstration_id, str) or not demonstration_id:
                raise ExportError("external demonstration needs a stable demonstration_id")
            if attempt.get("source_origin") not in {"PUBLIC_ORIGINAL", "DERIVED"}:
                raise ExportError("project sampling or model generation cannot be exported as external SFT")
            if attempt.get("eligibility_action") != "ACCEPT":
                raise ExportError("external SFT export requires an accepted eligibility decision")
            if not isinstance(attempt.get("review_checks"), list) or not EXTERNAL_PUBLICATION_REVIEW_CHECKS <= set(attempt["review_checks"]):
                raise ExportError("external SFT export requires source, split, and sensitive review")
            if not isinstance(attempt.get("upstream_message_refs"), list) or not attempt["upstream_message_refs"]:
                raise ExportError("external SFT export requires upstream message lineage")
        attempt_id = None if demonstration_id is not None else attempt.get("attempt_id")
        if attempt_id is not None and (not isinstance(attempt_id, str) or not attempt_id):
            raise ExportError("attempt export needs a stable attempt_id")
        if demonstration_id is None and attempt_id is None:
            raise ExportError("SFT export needs an attempt or external demonstration identity")
        task_id = attempt.get("task_id", demonstration_id)
        if not isinstance(task_id, str) or not task_id:
            raise ExportError("SFT export needs a task or external demonstration identity")
        messages = attempt.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ExportError("attempt needs complete messages")
        template_messages: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, dict) or message.get("role") not in {"user", "assistant", "tool"}:
                raise ExportError("messages must use user, assistant, or tool roles")
            template_messages.append(_template_message(message))

        rendered_ids = _render(active_tokenizer, template_messages)
        input_ids: list[int] = []
        loss_mask: list[bool] = []
        role_token_counts: dict[str, int] = {}
        role_loss_counts: dict[str, int] = {}
        message_loss_counts: dict[int, int] = {}
        controls = 0
        prefix_stable = True
        for message_index, rendered_message in enumerate(template_messages):
            role = rendered_message["role"]
            # Render only the current prefix.  The full template was rendered
            # above so an unstable template can fall back without changing its
            # official representation.
            prefix_ids = _render(active_tokenizer, template_messages[:message_index]) if message_index else []
            prefix_rendered = _render(active_tokenizer, template_messages[: message_index + 1])
            if prefix_rendered[: len(prefix_ids)] != prefix_ids:
                prefix_stable = False
                break
            encoded = prefix_rendered[len(prefix_ids) :]
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
            message_loss_counts[message_index] = sum(mask)
        if prefix_stable and input_ids != rendered_ids:
            raise ExportError("chat template token boundaries are not reproducible")
        if not prefix_stable:
            input_ids = rendered_ids
            loss_mask, message_loss_counts, role_token_counts, controls = _fallback_content_masks(
                active_tokenizer, input_ids=input_ids, messages=template_messages
            )
            role_loss_counts = {"assistant": sum(loss_mask), "tool": 0, "user": 0}
        for message_index, rendered_message in enumerate(template_messages):
            mappings.append(
                {
                    "attempt_id": attempt_id,
                    "demonstration_id": demonstration_id,
                    "message_index": message_index,
                    "role": rendered_message["role"],
                    "target_token_count": message_loss_counts[message_index],
                }
            )
        examples.append(
            SftExample(
                attempt_id=attempt_id,
                demonstration_id=demonstration_id,
                task_id=task_id,
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
                    "demonstration_id": example.demonstration_id,
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
        "source_attempt_count": sum(item.get("demonstration_id") is None for item in attempts),
        "source_external_demonstration_count": sum(
            item.get("demonstration_id") is not None for item in attempts
        ),
        "source_digest": sha256_bytes(canonical_json_bytes(attempts)),
        "examples": [asdict(example) for example in examples],
    }
    (output_dir / "loss_mask_audit.json").write_bytes(canonical_json_bytes(audit))
    (output_dir / "export_manifest.json").write_bytes(
        canonical_json_bytes(
            {
                "status": "EXPORTED",
                "member_kind": (
                    "EXTERNAL_DEMONSTRATION"
                    if audit["source_external_demonstration_count"]
                    else "EXECUTION_ATTEMPT"
                ),
                "example_count": len(examples),
                "source_digest": audit["source_digest"],
                "tokenizer_name": tokenizer_name,
                "tokenizer_revision": tokenizer_revision,
                "template_version": template_version,
            }
        )
    )
    return SftExportResult(examples=examples, audit=audit)


@dataclass(frozen=True)
class SftExportResult:
    examples: list[SftExample]
    audit: dict[str, Any]
