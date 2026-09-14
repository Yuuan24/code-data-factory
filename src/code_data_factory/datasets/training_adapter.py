"""Thin audited adapter around the upstream Transformers/PEFT SFT trainer."""

from __future__ import annotations

import math
import time
from gc import collect
from pathlib import Path
from typing import Any

from code_data_factory.contracts.artifacts import canonical_json_bytes
from code_data_factory.contracts.experiments import RunStatus, TrainingRun

from .batch_schedule import ScheduledExample


class TrainingAdapterError(RuntimeError):
    """A real SFT update could not satisfy its declared evidence contract."""


def release_cuda_memory() -> None:
    """Release completed-run Python references and reusable CUDA allocations."""
    collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        return


def _method_model(*, method: str, model_id: str, revision: str) -> tuple[Any, dict[str, object]]:
    try:
        import torch
        from peft import LoraConfig, get_peft_model
        from transformers import AutoModelForCausalLM, BitsAndBytesConfig
    except ImportError as error:
        raise TrainingAdapterError(
            "SFT adapter requires Transformers, PEFT, and PyTorch"
        ) from error
    kwargs: dict[str, object] = {"revision": revision, "torch_dtype": torch.bfloat16}
    if method == "qlora":
        kwargs["quantization_config"] = BitsAndBytesConfig(  # type: ignore[no-untyped-call]
            load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16
        )
    model: Any = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
    method_config: dict[str, object] = {
        "method": method,
        "model_id": model_id,
        "revision": revision,
    }
    if method in {"lora", "qlora"}:
        lora = LoraConfig(
            r=16,
            lora_alpha=32,
            lora_dropout=0.0,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        )
        model = get_peft_model(model, lora)
        method_config["peft"] = {
            "r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.0,
            "bias": "none",
            "task_type": "CAUSAL_LM",
            "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
        }
    elif method != "full_finetune":
        raise TrainingAdapterError(f"unsupported training method: {method}")
    return model, method_config


def _collator(tokenizer: Any, *, fixed_context_tokens: int) -> Any:
    def collate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        import torch

        max_length = fixed_context_tokens
        pad_id = (
            tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
        )
        input_ids, attention_mask, labels = [], [], []
        for row in rows:
            tokens = row["input_ids"]
            loss_mask = row["loss_mask"]
            if len(tokens) > max_length:
                raise TrainingAdapterError("scheduled example exceeds fixed context budget")
            padding = max_length - len(tokens)
            input_ids.append(tokens + [pad_id] * padding)
            attention_mask.append([1] * len(tokens) + [0] * padding)
            labels.append(
                [
                    token if include else -100
                    for token, include in zip(tokens, loss_mask, strict=True)
                ]
                + [-100] * padding
            )
        return {
            "input_ids": torch.tensor(input_ids),
            "attention_mask": torch.tensor(attention_mask),
            "labels": torch.tensor(labels),
        }

    return collate


def _dataset(rows: list[ScheduledExample]) -> Any:
    try:
        from datasets import Dataset  # type: ignore[import-untyped]
    except ImportError as error:
        raise TrainingAdapterError("SFT adapter requires datasets") from error
    return Dataset.from_list(
        [{"input_ids": list(row.input_ids), "loss_mask": list(row.loss_mask)} for row in rows]
    )


def execute_sft_run(
    *,
    run_id: str,
    experiment_id: str,
    recipe: str,
    seed: int,
    dataset_id: str,
    model_identity: dict[str, str],
    method: str,
    schedule_rows: list[ScheduledExample],
    planned_loss_tokens: int,
    optimizer_steps: int,
    batch_size: int,
    fixed_context_tokens: int,
    gradient_checkpointing: bool,
    output_dir: Path,
) -> TrainingRun:
    """Run the upstream trainer once and retain exact observed loss-token evidence."""
    try:
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            Trainer,
            TrainingArguments,
            set_seed,
        )
    except ImportError as error:
        raise TrainingAdapterError("SFT adapter requires Transformers and PyTorch") from error
    if not torch.cuda.is_available():
        raise TrainingAdapterError("SFT adapter requires a CUDA-visible GPU")
    if len(schedule_rows) != batch_size * optimizer_steps:
        raise TrainingAdapterError("schedule slots must equal batch size times optimizer steps")
    observed = sum(row.loss_tokens for row in schedule_rows)
    if observed != planned_loss_tokens:
        raise TrainingAdapterError("schedule effective loss tokens differ from declared plan")
    if fixed_context_tokens < 1 or any(
        len(row.input_ids) > fixed_context_tokens for row in schedule_rows
    ):
        raise TrainingAdapterError("schedule exceeds fixed context budget")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "schedule.json").write_bytes(
        canonical_json_bytes(
            {
                "recipe": recipe,
                "slots": [
                    {
                        "demonstration_id": row.demonstration_id,
                        "input_tokens": len(row.input_ids),
                        "padded_input_tokens": fixed_context_tokens,
                        "loss_tokens": row.loss_tokens,
                    }
                    for row in schedule_rows
                ],
            }
        )
    )
    set_seed(seed)
    started = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(
        model_identity["model_id"], revision=model_identity["tokenizer_revision"]
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model, method_config = _method_model(
        method=method,
        model_id=model_identity["model_id"],
        revision=model_identity["model_revision"],
    )
    if gradient_checkpointing:
        model.config.use_cache = False
        model.gradient_checkpointing_enable()
        if method in {"lora", "qlora"}:
            model.enable_input_require_grads()
    method_config["gradient_checkpointing"] = gradient_checkpointing
    method_config["fixed_context_tokens"] = fixed_context_tokens
    arguments = TrainingArguments(
        output_dir=output_dir.as_posix(),
        max_steps=optimizer_steps,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=1,
        learning_rate=2e-5,
        bf16=True,
        gradient_checkpointing=gradient_checkpointing,
        logging_steps=1,
        save_strategy="no",
        report_to="none",
        remove_unused_columns=False,
        seed=seed,
    )
    try:
        import mlflow
    except ImportError as error:
        raise TrainingAdapterError("SFT adapter requires MLflow for run indexing") from error
    mlflow.set_tracking_uri(f"sqlite:///{(output_dir / 'mlflow.db').resolve()}")
    mlflow.set_experiment("code-data-factory-sft-calibration")
    trainer = Trainer(
        model=model,
        args=arguments,
        train_dataset=_dataset(schedule_rows),
        data_collator=_collator(tokenizer, fixed_context_tokens=fixed_context_tokens),
    )
    with mlflow.start_run(run_name=run_id) as mlflow_run:
        mlflow.log_params(
            {
                "experiment_id": experiment_id,
                "recipe": recipe,
                "seed": seed,
                "method": method,
                "planned_loss_tokens": planned_loss_tokens,
                "optimizer_steps": optimizer_steps,
                "fixed_context_tokens": fixed_context_tokens,
            }
        )
        result = trainer.train()
        if result.training_loss is None:
            raise TrainingAdapterError("trainer did not return training loss")
        mlflow.log_metric("training_loss", float(result.training_loss))
        mlflow_run_id = mlflow_run.info.run_id
    losses = [
        entry.get("loss")
        for entry in trainer.state.log_history
        if isinstance(entry.get("loss"), (int, float))
    ]
    numeric_losses = [float(loss) for loss in losses if loss is not None]
    if not numeric_losses or not all(math.isfinite(loss) for loss in numeric_losses):
        raise TrainingAdapterError("trainer did not retain finite training loss")
    checkpoint = output_dir / "checkpoint"
    trainer.save_model(checkpoint.as_posix())
    tokenizer.save_pretrained(checkpoint.as_posix())
    del trainer
    del model
    release_cuda_memory()
    reloaded: Any
    if method == "full_finetune":
        reloaded = AutoModelForCausalLM.from_pretrained(checkpoint, torch_dtype=torch.bfloat16)
    else:
        from peft import PeftModel

        base, _ = _method_model(
            method="qlora" if method == "qlora" else "full_finetune",
            model_id=model_identity["model_id"],
            revision=model_identity["model_revision"],
        )
        reloaded = PeftModel.from_pretrained(base, checkpoint)
    del reloaded
    if method != "full_finetune":
        del base
    del tokenizer
    release_cuda_memory()
    free_bytes, total_bytes = torch.cuda.mem_get_info(0)
    runtime = {
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "gpu_free_bytes_after_reload": free_bytes,
        "gpu_total_bytes": total_bytes,
        "losses": numeric_losses,
        "trainer_loss": float(result.training_loss),
        "mlflow_run_id": mlflow_run_id,
    }
    (output_dir / "training_runtime.json").write_bytes(canonical_json_bytes(runtime))
    (output_dir / "method_config.json").write_bytes(canonical_json_bytes(method_config))
    receipt = TrainingRun(
        run_id=run_id,
        experiment_id=experiment_id,
        recipe=recipe,
        seed=seed,
        dataset_id=dataset_id,
        initial_model_ref=f"hf://{model_identity['model_id']}@{model_identity['model_revision']}",
        method_config_ref="method_config.json",
        batch_schedule_ref="schedule.json",
        planned_loss_tokens=planned_loss_tokens,
        observed_loss_tokens=observed,
        optimizer_steps=optimizer_steps,
        checkpoint_ref="checkpoint",
        reload_verified=True,
        status=RunStatus.COMPLETED,
    )
    (output_dir / "training_run.json").write_bytes(canonical_json_bytes(receipt))
    return receipt
