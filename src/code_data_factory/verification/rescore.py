"""Read-only terminal-reward rescoring for fixed sparse-evidence records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_file


class RescoreError(ValueError):
    """The supplied fixed evidence cannot safely receive a terminal projection."""


def _policy(path: Path) -> tuple[str, float, float]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RescoreError("reward policy must be a mapping")
    version = value.get("policy_version")
    success = value.get("pass_reward")
    known_zero = value.get("fail_reward")
    if not isinstance(version, str) or not version or not isinstance(success, (int, float)) or not isinstance(known_zero, (int, float)):
        raise RescoreError("reward policy requires versioned numeric terminal pass and fail values")
    if value.get("unknown_reward") is not None or value.get("dense_reward") not in {None, False}:
        raise RescoreError("terminal policy must preserve unknown rewards and disable dense rewards")
    return version, float(success), float(known_zero)


def _classify(record: dict[str, Any]) -> str:
    required = {"attempt_id", "task_id", "end_reason", "verification_status", "outcome", "total_reward"}
    if required - record.keys() or not all(isinstance(record[key], str) for key in required - {"total_reward"}):
        raise RescoreError("fixed evidence record lacks terminal fields")
    if record["end_reason"] == "BUDGET_TRUNCATED":
        return "truncated"
    if record["verification_status"] == "VERIFIED" and record["outcome"] == "PASS":
        return "success"
    if record["verification_status"] == "VERIFIED" and record["outcome"] == "FAIL":
        return "known_zero"
    if record["outcome"] == "UNKNOWN":
        return "unknown"
    raise RescoreError("fixed evidence has an unsupported terminal state")


def rescore_fixed_evidence(*, evidence_path: Path, policy_path: Path, output_dir: Path) -> dict[str, object]:
    """Project a new reward version without writing or replacing the source evidence."""

    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RescoreError("fixed reward evidence cannot be read") from error
    records = evidence.get("records") if isinstance(evidence, dict) else None
    source_policy = evidence.get("reward_policy_version") if isinstance(evidence, dict) else None
    if not isinstance(records, list) or not records or not isinstance(source_policy, str):
        raise RescoreError("fixed reward evidence requires a source policy and non-empty records")
    policy_version, pass_reward, fail_reward = _policy(policy_path)
    counts = {"success": 0, "known_zero": 0, "unknown": 0, "truncated": 0}
    rescored: list[dict[str, object]] = []
    same_values = 0
    for record_value in records:
        if not isinstance(record_value, dict):
            raise RescoreError("fixed reward evidence contains an invalid record")
        record = dict(record_value)
        category = _classify(record)
        counts[category] += 1
        total_reward: float | None
        availability: str
        if category == "success":
            total_reward, availability = pass_reward, "KNOWN"
        elif category == "known_zero":
            total_reward, availability = fail_reward, "KNOWN"
        else:
            total_reward, availability = None, "UNKNOWN"
        if record["total_reward"] == total_reward:
            same_values += 1
        rescored.append(
            {
                "attempt_id": record["attempt_id"],
                "task_id": record["task_id"],
                "reward_policy_version": policy_version,
                "reward_scope": "TERMINAL",
                "category": category,
                "availability": availability,
                "total_reward": total_reward,
                "source_evidence_policy_version": source_policy,
                "source_end_reason": record["end_reason"],
                "source_verification_status": record["verification_status"],
                "source_outcome": record["outcome"],
            }
        )
    if any(count < 2 for count in counts.values()):
        raise RescoreError("sparse reward evidence requires at least two tasks in every terminal category")
    receipt: dict[str, object] = {
        "kind": "fixed-evidence-terminal-rescore",
        "source_evidence_sha256": sha256_file(evidence_path),
        "source_policy_version": source_policy,
        "policy_version": policy_version,
        "counts": counts,
        "policy_comparison": {
            "same_terminal_values": same_values,
            "changed_terminal_values": len(rescored) - same_values,
            "explanation": "Both versions retain the same sparse terminal values; the new projection records categories explicitly.",
        },
        "rescored_records": rescored,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_bytes(canonical_json_bytes(receipt))
    return receipt
