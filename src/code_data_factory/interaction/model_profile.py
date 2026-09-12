"""Freeze and probe the local model identity used only for compatibility sampling."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from code_data_factory.contracts.artifacts import canonical_json_bytes


class ModelProfileError(RuntimeError):
    """A local sampling model cannot be frozen or probed under the declared policy."""


@dataclass(frozen=True)
class LocalModelCandidate:
    name: str
    model_id: str
    revision: str
    tokenizer_revision: str
    thinking_mode: str
    torch_dtype: str


@dataclass(frozen=True)
class LocalModelCandidates:
    primary: LocalModelCandidate
    fallback: LocalModelCandidate
    max_new_tokens: int
    max_input_tokens: int
    require_cuda: bool
    fallback_on_resource_failure_only: bool


def _candidate(name: str, value: object) -> LocalModelCandidate:
    if not isinstance(value, dict):
        raise ModelProfileError(f"candidate {name} must be a mapping")
    fields = ("model_id", "revision", "tokenizer_revision", "thinking_mode", "torch_dtype")
    if any(not isinstance(value.get(field), str) or not value[field] for field in fields):
        raise ModelProfileError(f"candidate {name} lacks a frozen model identity")
    return LocalModelCandidate(name=name, **{field: value[field] for field in fields})


def load_model_candidates(path: Path) -> LocalModelCandidates:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("profile_version") != "local-sampling-model-v1":
        raise ModelProfileError("model candidates must freeze profile_version local-sampling-model-v1")
    order = value.get("candidate_order")
    candidates = value.get("candidates")
    probe = value.get("probe")
    if not isinstance(order, list) or len(order) != 2 or not all(isinstance(item, str) for item in order):
        raise ModelProfileError("model candidates require exactly a primary and fallback ordering")
    if not isinstance(candidates, dict) or not isinstance(probe, dict):
        raise ModelProfileError("model candidates require candidates and probe mappings")
    primary = _candidate(order[0], candidates.get(order[0]))
    fallback = _candidate(order[1], candidates.get(order[1]))
    max_new_tokens = probe.get("max_new_tokens")
    max_input_tokens = probe.get("max_input_tokens")
    if not isinstance(max_new_tokens, int) or max_new_tokens < 1 or not isinstance(max_input_tokens, int) or max_input_tokens < 1:
        raise ModelProfileError("model probe must set positive token limits")
    if probe.get("require_cuda") is not True or probe.get("fallback_on_resource_failure_only") is not True:
        raise ModelProfileError("model probe must require CUDA and forbid performance-driven fallback")
    return LocalModelCandidates(
        primary=primary,
        fallback=fallback,
        max_new_tokens=max_new_tokens,
        max_input_tokens=max_input_tokens,
        require_cuda=True,
        fallback_on_resource_failure_only=True,
    )


def _template_sha256(tokenizer: Any) -> str:
    template = getattr(tokenizer, "chat_template", None)
    if not isinstance(template, str) or not template:
        raise ModelProfileError("frozen tokenizer does not expose a chat template")
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


def probe_local_model(*, candidates_path: Path, output_path: Path) -> dict[str, object]:
    """Load the declared primary model on CUDA and save a minimal real token-channel probe."""

    candidates = load_model_candidates(candidates_path)
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as error:
        raise ModelProfileError("local model probe requires torch and transformers") from error
    if not torch.cuda.is_available():
        raise ModelProfileError("local model probe requires a CUDA-visible GPU")
    candidate = candidates.primary
    started = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(candidate.model_id, revision=candidate.tokenizer_revision)
    model: Any = AutoModelForCausalLM.from_pretrained(
        candidate.model_id,
        revision=candidate.revision,
        torch_dtype=torch.bfloat16,
        device_map="cuda:0",
    )
    model.eval()
    rendered = cast(Any, tokenizer.apply_chat_template(
        [{"role": "user", "content": "Reply with the word ready."}],
        tokenize=True,
        add_generation_prompt=True,
        enable_thinking=False,
        return_tensors="pt",
    )).to("cuda:0")
    if rendered.shape[-1] > candidates.max_input_tokens:
        raise ModelProfileError("frozen token probe exceeds its configured input limit")
    with torch.inference_mode():
        generated: Any = model.generate(rendered, do_sample=False, max_new_tokens=candidates.max_new_tokens)
    output_ids = generated[0, rendered.shape[-1] :].tolist()
    free_bytes, total_bytes = torch.cuda.mem_get_info(0)
    receipt: dict[str, object] = {
        "kind": "local-model-profile",
        "candidate_order": [candidates.primary.name, candidates.fallback.name],
        "selected_candidate": candidate.name,
        "selection_reason": "frozen primary candidate completed the CUDA token-channel probe",
        "model": {
            "model_id": candidate.model_id,
            "model_revision": candidate.revision,
            "tokenizer_revision": candidate.tokenizer_revision,
            "template_sha256": _template_sha256(tokenizer),
            "thinking_mode": candidate.thinking_mode,
            "torch_dtype": candidate.torch_dtype,
        },
        "runtime": {
            "torch_version": torch.__version__,
            "cuda_version": torch.version.cuda,
            "device_name": torch.cuda.get_device_name(0),
            "free_memory_bytes_after_probe": free_bytes,
            "total_memory_bytes": total_bytes,
            "probe_seconds": round(time.monotonic() - started, 6),
        },
        "token_channel_probe": {
            "input_token_ids": rendered[0].tolist(),
            "output_token_ids": output_ids,
            "input_token_count": int(rendered.shape[-1]),
            "output_token_count": len(output_ids),
        },
        "evidence_level": "SOFTWARE_VALIDATED",
        "limitations": [
            "This probe does not update model parameters and does not establish SFT feasibility.",
            "Provider charge is recorded by the sampling receipt when the platform price is available.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_json_bytes(receipt))
    return receipt
