"""US6 compatibility checkpoint that binds runtime receipts without claiming training."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_file


def _object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"US6 checkpoint cannot read {label}") from error
    if not isinstance(value, dict):
        raise ValueError(f"US6 checkpoint {label} must be an object")
    return value


def _sampling_checks(manifest: dict[str, Any]) -> dict[str, bool]:
    attachments = manifest.get("attachments")
    task_counts = manifest.get("task_attempt_counts")
    if not isinstance(attachments, list) or not isinstance(task_counts, dict):
        raise ValueError("US6 sampling receipt lacks attachments or task counts")
    completed = [item for item in attachments if isinstance(item, dict) and item.get("sampling_status") == "COMPLETED"]
    def has_token_mask_record(item: dict[str, Any]) -> bool:
        input_ids = item.get("input_token_ids")
        output_ids = item.get("output_token_ids")
        output_mask = item.get("output_mask")
        return (
            isinstance(input_ids, list)
            and bool(input_ids)
            and isinstance(output_ids, list)
            and isinstance(output_mask, list)
            and len(output_ids) == len(output_mask)
            and all(mask in (0, 1) for mask in output_mask)
        )

    tokens_and_masks = all(has_token_mask_record(item) for item in completed)
    identity = all(
        isinstance(item.get("policy"), dict)
        and all(isinstance(item["policy"].get(field), str) and item["policy"][field] for field in ("model_id", "model_revision", "tokenizer_revision", "template_sha256", "thinking_mode"))
        for item in attachments
        if isinstance(item, dict)
    )
    return {
        "two_tasks_twice": len(task_counts) == 2 and len(attachments) == 4 and all(value == 2 for value in task_counts.values()),
        "actual_trainer_sampler": manifest.get("provenance") == "ACTUAL_TRAINER_SAMPLER" and manifest.get("runner_kind") == "TRL_GRPO_TRAINER",
        "completed_token_mask_records": len(completed) == 4 and tokens_and_masks,
        "frozen_model_identity": identity,
        "no_optimizer_or_sft_ingress": manifest.get("optimizer_step_count") == 0 and manifest.get("sft_pool_ingress_count") == 0,
    }


def run_us6_checkpoint(
    *,
    output_path: Path,
    contract_manifest: Path,
    long_horizon_manifest: Path,
    rescore_manifest: Path,
    model_profile: Path,
    sampling_manifest: Path,
) -> dict[str, Any]:
    """Verify SC-011--013 evidence, explicitly retaining the no-training boundary."""

    contract = _object(contract_manifest, label="contract manifest")
    horizon = _object(long_horizon_manifest, label="long-horizon manifest")
    rescore = _object(rescore_manifest, label="rescore manifest")
    profile = _object(model_profile, label="model profile")
    sampling = _object(sampling_manifest, label="sampling manifest")
    cases = horizon.get("cases")
    counts = rescore.get("counts")
    if not isinstance(cases, list) or not isinstance(counts, dict):
        raise ValueError("US6 checkpoint horizon or rescore receipt is malformed")
    horizon_checks = {
        "steps_32_and_128": {item.get("step_count") for item in cases if isinstance(item, dict)} == {32, 128},
        "dependencies_rewrite_truncation_and_restore": all(
            isinstance(item, dict)
            and item.get("dependency_edges") == item.get("step_count", 0) - 1
            and item.get("context_rewrite_count") == 1
            and item.get("truncation_count") == 1
            and isinstance(item.get("visible_context_hash"), str)
            and isinstance(item.get("controlled_restore"), dict)
            for item in cases
        ),
    }
    rescore_checks = {
        "four_sparse_categories_twice": counts == {"success": 2, "known_zero": 2, "unknown": 2, "truncated": 2},
        "terminal_only_immutable_source": rescore.get("kind") == "fixed-evidence-terminal-rescore"
        and isinstance(rescore.get("source_evidence_sha256"), str)
        and all(item.get("reward_scope") == "TERMINAL" for item in rescore.get("rescored_records", []) if isinstance(item, dict)),
    }
    sampling_checks = _sampling_checks(sampling)
    checks = {
        "SC-011": contract.get("semantic_match") is True
        and contract.get("direct_fixed_action_calls") == 4
        and contract.get("tool_calls") == 4
        and all(sampling_checks[key] for key in ("two_tasks_twice", "actual_trainer_sampler", "completed_token_mask_records", "frozen_model_identity", "no_optimizer_or_sft_ingress")),
        "SC-012": all(horizon_checks.values()),
        "SC-013": all(rescore_checks.values()),
    }
    if not all(checks.values()):
        raise ValueError("US6 checkpoint facts are inconsistent")
    receipt: dict[str, Any] = {
        "checkpoint": "US6_COMPATIBILITY",
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_level": "REAL_SAMPLING_VALIDATED",
        "checks": checks,
        "sc_011": {"contract": contract.get("semantic_hash"), "sampling": sampling_checks},
        "sc_012": horizon_checks,
        "sc_013": rescore_checks,
        "model": profile.get("model"),
        "input_hashes": {
            "contract": sha256_file(contract_manifest),
            "long_horizon": sha256_file(long_horizon_manifest),
            "rescore": sha256_file(rescore_manifest),
            "model_profile": sha256_file(model_profile),
            "sampling": sha256_file(sampling_manifest),
        },
        "limitations": [
            "This checkpoint proves bounded compatibility sampling, not SFT feasibility or training.",
            "No optimizer update or RL parameter update was executed.",
            "A later RL phase may add only an algorithm and budget attachment; real long-horizon ability remains unverified.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_json_bytes(receipt))
    return receipt
