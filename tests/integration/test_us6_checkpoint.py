from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_data_factory.checkpoints.us6 import run_us6_checkpoint


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    contract = _write(tmp_path / "contract.json", {"semantic_match": True, "direct_fixed_action_calls": 4, "tool_calls": 4, "semantic_hash": "hash"})
    horizon = _write(tmp_path / "horizon.json", {"cases": [{"step_count": 32, "dependency_edges": 31, "context_rewrite_count": 1, "truncation_count": 1, "visible_context_hash": "a", "controlled_restore": {}}, {"step_count": 128, "dependency_edges": 127, "context_rewrite_count": 1, "truncation_count": 1, "visible_context_hash": "b", "controlled_restore": {}}]})
    rescore = _write(tmp_path / "rescore.json", {"kind": "fixed-evidence-terminal-rescore", "source_evidence_sha256": "source", "counts": {"success": 2, "known_zero": 2, "unknown": 2, "truncated": 2}, "rescored_records": [{"reward_scope": "TERMINAL"}]})
    profile = _write(tmp_path / "profile.json", {"model": {"model_id": "Qwen/Qwen3-8B"}})
    policy = {"model_id": "Qwen/Qwen3-8B", "model_revision": "revision", "tokenizer_revision": "revision", "template_sha256": "template", "thinking_mode": "disabled"}
    attachment = {"sampling_status": "COMPLETED", "input_token_ids": [1], "output_token_ids": [2], "output_mask": [1], "policy": policy}
    sampling = _write(tmp_path / "sampling.json", {"provenance": "ACTUAL_TRAINER_SAMPLER", "runner_kind": "TRL_GRPO_TRAINER", "task_attempt_counts": {"one": 2, "two": 2}, "attachments": [attachment] * 4, "optimizer_step_count": 0, "sft_pool_ingress_count": 0})
    return contract, horizon, rescore, profile, sampling


def test_us6_checkpoint_binds_contract_horizon_rewards_and_real_sampling(tmp_path: Path) -> None:
    contract, horizon, rescore, profile, sampling = _inputs(tmp_path)
    receipt = run_us6_checkpoint(output_path=tmp_path / "us6.json", contract_manifest=contract, long_horizon_manifest=horizon, rescore_manifest=rescore, model_profile=profile, sampling_manifest=sampling)
    assert receipt["evidence_level"] == "REAL_SAMPLING_VALIDATED"
    assert all(receipt["checks"].values())


def test_us6_checkpoint_rejects_uncompleted_sampling(tmp_path: Path) -> None:
    contract, horizon, rescore, profile, sampling = _inputs(tmp_path)
    value = json.loads(sampling.read_text(encoding="utf-8"))
    value["attachments"][0]["sampling_status"] = "FAILED"
    _write(sampling, value)
    with pytest.raises(ValueError, match="facts are inconsistent"):
        run_us6_checkpoint(output_path=tmp_path / "us6.json", contract_manifest=contract, long_horizon_manifest=horizon, rescore_manifest=rescore, model_profile=profile, sampling_manifest=sampling)
