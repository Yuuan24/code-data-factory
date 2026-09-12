from __future__ import annotations

from pathlib import Path

import pytest

from code_data_factory.datasets.export_sft import ExportError, export_sft_examples


class FakeChatTokenizer:
    chat_template = "fake-v1"

    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]:
        del add_special_tokens
        return list(text.encode("utf-8"))

    def apply_chat_template(
        self, conversation: list[dict[str, str]], *, tokenize: bool, add_generation_prompt: bool
    ) -> list[int]:
        assert tokenize is True
        assert add_generation_prompt is False
        return self.encode(
            "".join(f"<{message['role']}>\n{message['content']}<eos>\n" for message in conversation),
            add_special_tokens=False,
        )


def _attempt(attempt_id: str, *, unknown_action: bool = False) -> dict[str, object]:
    return {
        "attempt_id": attempt_id,
        "task_id": "task-1",
        "messages": [
            {"role": "user", "content": "How many centimetres are in one metre?"},
            {
                "role": "assistant",
                "content": "",
                "tool_call": {"name": "read_document", "arguments": {"document_id": "units"}},
            },
            {"role": "tool", "content": "One metre is 100 centimetres."},
            {"role": "assistant", "content": "One metre is 100 centimetres.<eos>"},
        ],
        "unknown_action_location": unknown_action,
    }


def test_sft_export_preserves_context_and_trains_only_model_output(tmp_path: Path) -> None:
    result = export_sft_examples(
        [_attempt("attempt-1")],
        output_dir=tmp_path,
        tokenizer_name="test-byte-tokenizer",
        tokenizer_revision="v1",
        template_version="tool-chat-v1",
        tokenizer=FakeChatTokenizer(),
    )

    example = result.examples[0]
    assert [message["role"] for message in example.messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert any(example.loss_mask)
    assert example.loss_mask[: example.role_token_counts["user"]] == [False] * example.role_token_counts[
        "user"
    ]
    assert example.role_loss_counts["tool"] == 0
    assert example.role_loss_counts["assistant"] > 0
    assert example.control_token_count > 0
    assert (tmp_path / "training_examples.parquet").is_file()
    assert (tmp_path / "target_mapping.parquet").is_file()
    assert (tmp_path / "loss_mask_audit.json").is_file()


def test_sft_export_rejects_unknown_error_position_without_mutating_source(tmp_path: Path) -> None:
    source = [_attempt("attempt-unknown", unknown_action=True)]

    with pytest.raises(ExportError, match="unknown action location"):
        export_sft_examples(
            source,
            output_dir=tmp_path,
            tokenizer_name="test-byte-tokenizer",
            tokenizer_revision="v1",
            template_version="tool-chat-v1",
            tokenizer=FakeChatTokenizer(),
        )

    assert source[0]["unknown_action_location"] is True


def test_external_sft_export_requires_admitted_external_material_not_execution_pass(tmp_path: Path) -> None:
    external = _attempt("unused") | {
        "demonstration_id": "demo-1",
        "source_origin": "PUBLIC_ORIGINAL",
        "eligibility_action": "ACCEPT",
        "upstream_message_refs": ["messages/demo-1.json"],
        "review_checks": [
            "source_identity",
            "upstream_tool_definition",
            "message_context",
            "target_answer_mapping",
            "split_registration",
            "sensitive_review",
        ],
    }
    external.pop("attempt_id")
    external.pop("task_id")

    result = export_sft_examples(
        [external],
        output_dir=tmp_path,
        tokenizer_name="test-byte-tokenizer",
        tokenizer_revision="v1",
        template_version="tool-chat-v1",
        tokenizer=FakeChatTokenizer(),
    )

    assert result.examples[0].demonstration_id == "demo-1"
    assert result.examples[0].attempt_id is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_origin": "PROJECT_SAMPLING"},
        {"source_origin": "MODEL_GENERATION"},
        {"eligibility_action": "REJECT"},
        {"upstream_message_refs": []},
    ],
)
def test_external_sft_export_rejects_non_external_or_unadmitted_input(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    external = _attempt("unused") | {
        "demonstration_id": "demo-1",
        "source_origin": "PUBLIC_ORIGINAL",
        "eligibility_action": "ACCEPT",
        "upstream_message_refs": ["messages/demo-1.json"],
        "review_checks": [
            "source_identity",
            "upstream_tool_definition",
            "message_context",
            "target_answer_mapping",
            "split_registration",
            "sensitive_review",
        ],
    }
    external.pop("attempt_id")
    external.pop("task_id")
    external.update(overrides)

    with pytest.raises(ExportError):
        export_sft_examples(
            [external],
            output_dir=tmp_path,
            tokenizer_name="test-byte-tokenizer",
            tokenizer_revision="v1",
            template_version="tool-chat-v1",
            tokenizer=FakeChatTokenizer(),
        )
