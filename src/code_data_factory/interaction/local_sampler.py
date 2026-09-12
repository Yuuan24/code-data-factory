"""Bounded local TRL sampling probe; deliberately no training or optimizer step."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import yaml

from code_data_factory.contracts.artifacts import canonical_json_bytes
from code_data_factory.contracts.tasks import TaskPackage

from .model_profile import ModelProfileError
from .pilot import load_facts
from .sampling_records import (
    SamplingAttachment,
    SamplingCost,
    SamplingFailure,
    SamplingPolicy,
    SamplingStatus,
    write_sampling_attachment,
)
from .trl_adapter import build_environment_factory


class LocalSamplerError(RuntimeError):
    """The selected local trainer cannot produce a bounded, auditable sampling probe."""


def _load_profile(path: Path) -> dict[str, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LocalSamplerError("local model profile cannot be read") from error
    model = value.get("model") if isinstance(value, dict) else None
    selected = value.get("selected_candidate") if isinstance(value, dict) else None
    required = {"model_id", "model_revision", "tokenizer_revision", "template_sha256", "thinking_mode"}
    if not isinstance(model, dict) or not isinstance(selected, str) or required - model.keys():
        raise LocalSamplerError("local model profile lacks a frozen selected model identity")
    if not all(isinstance(model[key], str) and model[key] for key in required):
        raise LocalSamplerError("local model profile has an invalid frozen identity")
    return {key: model[key] for key in required}


def _sampling_profile(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("profile_version") != "trl-tools-v1":
        raise LocalSamplerError("sampling requires the frozen trl-tools-v1 profile")
    sampling = value.get("sampling")
    if not isinstance(sampling, dict):
        raise LocalSamplerError("sampling profile lacks limits")
    required = ("max_model_calls", "max_completion_tokens", "temperature", "top_p")
    if any(key not in sampling for key in required):
        raise LocalSamplerError("sampling profile lacks generation limits")
    facts_config = value.get("facts_config", "../tasks/pilot.yaml")
    if not isinstance(facts_config, str):
        raise LocalSamplerError("sampling profile facts_config must be a path")
    return {**sampling, "facts_config": facts_config}


def _load_tasks(path: Path) -> tuple[list[TaskPackage], Path]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LocalSamplerError("task manifest cannot be read") from error
    items = value.get("tasks") if isinstance(value, dict) else None
    if not isinstance(items, list):
        raise LocalSamplerError("task manifest requires tasks")
    tasks = [TaskPackage.model_validate(item) for item in items]
    by_family: dict[str, TaskPackage] = {}
    for task in tasks:
        by_family.setdefault(task.task_family, task)
    selected = list(by_family.values())[:2]
    if len(selected) != 2:
        raise LocalSamplerError("sampling requires at least two distinct task families")
    return selected, path.parent


def _task_prompt(task: TaskPackage, assets_root: Path) -> tuple[str, list[str]]:
    try:
        instruction = json.loads((assets_root / task.instruction_ref.uri).read_text(encoding="utf-8"))
        resources = json.loads((assets_root / task.initial_resources_ref.uri).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LocalSamplerError("task sampling requires its frozen visible assets") from error
    text = instruction.get("instruction") if isinstance(instruction, dict) else None
    document_ids = resources.get("document_ids") if isinstance(resources, dict) else None
    if not isinstance(text, str) or not isinstance(document_ids, list) or not all(isinstance(item, str) for item in document_ids):
        raise LocalSamplerError("task visible assets are invalid")
    return text, document_ids


def _load_model(profile: dict[str, str]) -> tuple[Any, Any, Any]:
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as error:
        raise LocalSamplerError("local sampling requires torch and transformers") from error
    if not torch.cuda.is_available():
        raise LocalSamplerError("local sampling requires a CUDA-visible GPU")
    tokenizer = AutoTokenizer.from_pretrained(profile["model_id"], revision=profile["tokenizer_revision"])
    if not getattr(tokenizer, "response_template", None):
        tokenizer.response_template = "<|im_start|>assistant\n"
    model: Any = AutoModelForCausalLM.from_pretrained(
        profile["model_id"],
        revision=profile["model_revision"],
        torch_dtype=torch.bfloat16,
        device_map="cuda:0",
    )
    model.eval()
    return torch, tokenizer, model


def _build_trainer(*, model: Any, tokenizer: Any, factory: Any, output_dir: Path, max_completion_tokens: int) -> Any:
    try:
        from datasets import Dataset  # type: ignore[import-untyped]
        from trl import GRPOConfig, GRPOTrainer  # type: ignore[attr-defined]
    except ImportError as error:
        raise LocalSamplerError("local sampling requires datasets and TRL") from error
    args = GRPOConfig(
        output_dir=output_dir.as_posix(),
        report_to="none",
        per_device_train_batch_size=2,
        num_generations=2,
        max_completion_length=max_completion_tokens,
        max_steps=1,
        bf16=True,
        use_vllm=False,
        remove_unused_columns=False,
    )

    def terminal_placeholder_reward(prompts: list[Any], completions: list[Any]) -> list[float]:
        del prompts
        return [0.0] * len(completions)

    return GRPOTrainer(
        model=model,
        reward_funcs=terminal_placeholder_reward,
        args=args,
        train_dataset=Dataset.from_list([{"prompt": [{"role": "user", "content": "probe"}]}]),
        processing_class=tokenizer,
        environment_factory=factory,
        optimizers=(None, None),
    )


def _attachment_from_generation(
    *,
    task_id: str,
    profile: dict[str, str],
    prompt_ids: list[int],
    completion_ids: list[int],
    tool_mask: list[int] | None,
    elapsed_seconds: float,
) -> SamplingAttachment:
    return SamplingAttachment(
        attempt_id=str(uuid4()),
        task_id=task_id,
        provenance="ACTUAL_TRAINER_SAMPLER",
        runner_kind="TRL_GRPO_TRAINER",
        policy=SamplingPolicy(
            model_id=profile["model_id"],
            model_revision=profile["model_revision"],
            tokenizer_revision=profile["tokenizer_revision"],
            template_sha256=profile["template_sha256"],
            thinking_mode=profile["thinking_mode"],
        ),
        input_token_ids=tuple(prompt_ids),
        output_token_ids=tuple(completion_ids),
        output_mask=tuple(tool_mask if tool_mask is not None else [1] * len(completion_ids)),
        optimizer_step_count=0,
        sampling_status=SamplingStatus.COMPLETED,
        cost=SamplingCost(
            gpu_seconds=elapsed_seconds,
            provider_charge_cny=None,
            unavailable_reason="AutoDL price is not exposed to the sampler process; runtime seconds are retained.",
        ),
    )


def run_local_sampling_probe(
    *,
    sampling_profile_path: Path,
    model_profile_path: Path,
    tasks_path: Path,
    output_dir: Path,
) -> dict[str, object]:
    """Perform two actual TRL samplings for each of two frozen task packages without ``train()``."""

    profile = _load_profile(model_profile_path)
    limits = _sampling_profile(sampling_profile_path)
    selected_tasks, assets_root = _load_tasks(tasks_path)
    facts_path = (sampling_profile_path.parent / str(limits["facts_config"])).resolve()
    facts = load_facts(facts_path)
    try:
        torch, tokenizer, model = _load_model(profile)
    except ModelProfileError as error:
        raise LocalSamplerError(str(error)) from error
    attachments: list[SamplingAttachment] = []
    tool_traces: dict[str, list[dict[str, object]]] = {}
    for task in selected_tasks:
        instruction, document_ids = _task_prompt(task, assets_root)
        documents = {document_id: facts[document_id]["content"] for document_id in document_ids if document_id in facts}
        if len(documents) != len(document_ids):
            raise LocalSamplerError("task documents are absent from the frozen facts bundle")
        for repetition in range(2):
            factory, environments = build_environment_factory(
                documents=documents,
                workspace_root=output_dir / "workspaces" / task.task_id / str(repetition),
            )
            trainer = _build_trainer(
                model=model,
                tokenizer=tokenizer,
                factory=factory,
                output_dir=output_dir / "trainer-state" / task.task_id / str(repetition),
                max_completion_tokens=cast(int, limits["max_completion_tokens"]),
            )
            if getattr(trainer, "optimizer", None) is not None:
                raise LocalSamplerError("sampling probe unexpectedly constructed an optimizer")
            environment = environments[0]
            prompt = [{"role": "user", "content": instruction + environment.reset()}]
            started = time.monotonic()
            try:
                prompt_ids, completion_ids, tool_mask, _, _, _, _ = trainer._generate([prompt])
                attachment = _attachment_from_generation(
                    task_id=task.task_id,
                    profile=profile,
                    prompt_ids=[int(item) for item in prompt_ids[0]],
                    completion_ids=[int(item) for item in completion_ids[0]],
                    tool_mask=[int(item) for item in tool_mask[0]] if tool_mask is not None else None,
                    elapsed_seconds=round(time.monotonic() - started, 6),
                )
            except Exception as error:
                token_ids = tokenizer.apply_chat_template(
                    prompt, tokenize=True, add_generation_prompt=True, enable_thinking=False
                )
                if hasattr(token_ids, "get"):
                    token_ids = token_ids["input_ids"]
                attachment = SamplingAttachment(
                    attempt_id=str(uuid4()),
                    task_id=task.task_id,
                    provenance="ACTUAL_TRAINER_SAMPLER",
                    runner_kind="TRL_GRPO_TRAINER",
                    policy=SamplingPolicy(
                        model_id=profile["model_id"],
                        model_revision=profile["model_revision"],
                        tokenizer_revision=profile["tokenizer_revision"],
                        template_sha256=profile["template_sha256"],
                        thinking_mode=profile["thinking_mode"],
                    ),
                    input_token_ids=tuple(int(item) for item in token_ids),
                    output_token_ids=(),
                    output_mask=(),
                    optimizer_step_count=0,
                    sampling_status=SamplingStatus.FAILED,
                    failure=SamplingFailure(kind=type(error).__name__, message=str(error)),
                    cost=SamplingCost(
                        gpu_seconds=round(time.monotonic() - started, 6),
                        provider_charge_cny=None,
                        unavailable_reason="AutoDL price is not exposed to the sampler process; runtime seconds are retained.",
                    ),
                )
            path = output_dir / "attachments" / f"{attachment.attempt_id}.json"
            write_sampling_attachment(attachment, path)
            attachments.append(attachment)
            tool_traces[attachment.attempt_id] = environment.calls
            del trainer
            torch.cuda.empty_cache()
    counts_by_task = {task.task_id: sum(item.task_id == task.task_id for item in attachments) for task in selected_tasks}
    if len(attachments) != 4 or any(count != 2 for count in counts_by_task.values()):
        raise LocalSamplerError("local sampling must retain two attempts for each of two tasks")
    receipt: dict[str, object] = {
        "kind": "local-trl-sampling-probe",
        "provenance": "ACTUAL_TRAINER_SAMPLER",
        "runner_kind": "TRL_GRPO_TRAINER",
        "model_profile": profile,
        "attempt_count": len(attachments),
        "task_attempt_counts": counts_by_task,
        "optimizer_step_count": 0,
        "attachments": [attachment.model_dump(mode="json") for attachment in attachments],
        "tool_traces": tool_traces,
        "sft_pool_ingress_count": 0,
        "limitations": [
            "This is a compatibility probe only; it does not call trainer.train or update model parameters.",
            "Sampling output is prohibited from formal external SFT releases.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_bytes(canonical_json_bytes(receipt))
    return receipt
