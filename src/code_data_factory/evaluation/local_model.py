"""Bounded local Transformers executor for development-only tool evaluation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from code_data_factory.interaction.tools import RestrictedTools, ToolInputError

from .interactive import InfrastructureFailure
from .suites import EvaluationTask


class LocalEvaluationError(RuntimeError):
    """The frozen local-model evaluator cannot execute the declared protocol."""


class LocalTransformersExecutor:
    """Generate one bounded action at a time and execute only the four project tools."""

    def __init__(self, profile_path: Path) -> None:
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        if not isinstance(profile, dict) or profile.get("kind") != "LOCAL_TRANSFORMERS":
            raise LocalEvaluationError("local evaluation requires a LOCAL_TRANSFORMERS profile")
        required = ("model_id", "model_revision", "tokenizer_revision", "template_sha256")
        if any(not isinstance(profile.get(key), str) or not profile[key] for key in required):
            raise LocalEvaluationError("local evaluation profile lacks a frozen model identity")
        max_calls = profile.get("max_model_calls", 4)
        max_tokens = profile.get("max_completion_tokens", 128)
        if not isinstance(max_calls, int) or max_calls < 1 or not isinstance(max_tokens, int) or max_tokens < 1:
            raise LocalEvaluationError("local evaluation profile has invalid bounds")
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as error:
            raise LocalEvaluationError("local evaluation requires torch and transformers") from error
        if not torch.cuda.is_available():
            raise LocalEvaluationError("local evaluation requires a CUDA-visible GPU")
        self._torch = torch
        self._tokenizer: Any = AutoTokenizer.from_pretrained(profile["model_id"], revision=profile["tokenizer_revision"])
        self._model: Any = AutoModelForCausalLM.from_pretrained(
            profile["model_id"], revision=profile["model_revision"], torch_dtype=torch.bfloat16, device_map="cuda:0"
        )
        self._model.eval()  # type: ignore[no-untyped-call]
        self._identity = {key: profile[key] for key in required}
        self._identity["kind"] = profile["kind"]
        self._max_calls = max_calls
        self._max_tokens = max_tokens

    @property
    def identity(self) -> dict[str, object]:
        return dict(self._identity)

    def close(self) -> None:
        del self._model
        self._torch.cuda.empty_cache()

    def _generate(self, messages: list[dict[str, str]]) -> tuple[str, int]:
        try:
            rendered = self._tokenizer.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True, enable_thinking=False, return_tensors="pt"
            )
            input_ids = rendered["input_ids"] if isinstance(rendered, Mapping) else rendered
            input_ids = input_ids.to("cuda:0")
            with self._torch.inference_mode():
                generated = self._model.generate(input_ids, do_sample=False, max_new_tokens=self._max_tokens)
            completion = generated[0, input_ids.shape[-1] :].tolist()
            return self._tokenizer.decode(completion, skip_special_tokens=True).strip(), len(completion)
        except (OSError, RuntimeError) as error:
            raise InfrastructureFailure(f"local Transformers generation failed: {type(error).__name__}: {error}") from error

    @staticmethod
    def _json_object(text: str) -> dict[str, object] | None:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            return None
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _execute(tools: RestrictedTools, request: dict[str, object]) -> tuple[object, str] | None:
        name, arguments = request.get("tool"), request.get("arguments")
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return None
        try:
            if name == "search_documents":
                query = arguments.get("query")
                if not isinstance(query, str):
                    return None
                return tools.search_documents(query), name
            if name == "read_document":
                document_id = arguments.get("document_id")
                if not isinstance(document_id, str):
                    return None
                return tools.read_document(document_id), name
            if name == "calculate":
                operation, operands = arguments.get("operation"), arguments.get("operands")
                if not isinstance(operation, str) or not isinstance(operands, list) or not all(isinstance(item, str) for item in operands):
                    return None
                return tools.calculate(operation, operands), name
            if name == "convert":
                value, from_unit, to_unit = arguments.get("value"), arguments.get("from_unit"), arguments.get("to_unit")
                if not all(isinstance(item, str) for item in (value, from_unit, to_unit)):
                    return None
                return tools.convert(str(value), str(from_unit), str(to_unit)), name
        except ToolInputError as error:
            return {"tool_error": str(error)}, name
        return None

    def __call__(self, task: EvaluationTask) -> dict[str, object]:
        tools = RestrictedTools(dict(task.documents))
        messages = [
            {"role": "system", "content": "You are in a bounded tool evaluation. Respond with exactly one JSON object. To use a tool, emit {\"tool\": name, \"arguments\": object}. After tool results, emit {\"final\": {\"value\": string, \"unit\": string, \"evidence\": [document ids]}}. Never invent document content or call other tools."},
            {"role": "user", "content": task.instruction + " Available tools: " + ", ".join(task.tool_signature)},
        ]
        trace: list[dict[str, object]] = []
        completion_tokens = 0
        model_calls = 0
        final: dict[str, object] = {}
        for _ in range(self._max_calls):
            raw, tokens = self._generate(messages)
            model_calls += 1
            completion_tokens += tokens
            response = self._json_object(raw)
            if response is None:
                trace.append({"kind": "MODEL_RESPONSE", "raw": raw, "parse_status": "INVALID"})
                break
            final_value = response.get("final")
            if isinstance(final_value, dict):
                final = final_value
                trace.append({"kind": "MODEL_RESPONSE", "raw": raw, "parse_status": "FINAL"})
                break
            executed = self._execute(tools, response)
            if executed is None:
                trace.append({"kind": "MODEL_RESPONSE", "raw": raw, "parse_status": "UNSUPPORTED"})
                break
            result, name = executed
            trace.append({"kind": "TOOL_CALL", "tool": name, "request": response, "result": result})
            messages.extend(({"role": "assistant", "content": raw}, {"role": "tool", "content": json.dumps({"tool": name, "result": result}, sort_keys=True)}))
        return {
            "value": final.get("value"), "unit": final.get("unit"), "evidence": final.get("evidence"),
            "model_calls": model_calls,
            "completion_tokens": completion_tokens,
            "provider_cost_cny": None,
            "tool_trace": trace,
            "constraint_valid": bool(trace) and all(item.get("tool") in task.tool_signature for item in trace if item.get("kind") == "TOOL_CALL"),
        }
