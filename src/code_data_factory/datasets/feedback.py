"""Development-finding to same-pool DataAction linkage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_file
from code_data_factory.evaluation.bfcl import BfclError, validate_bfcl_development_receipt


class FeedbackError(ValueError):
    """A feedback action would consume final-test content or an unfrozen pool."""


def _object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FeedbackError(f"{label} must be an object")
    return value


def build_data_actions(*, evaluation_path: Path, external_evaluation_path: Path, external_config_path: Path, findings_path: Path, candidate_pool_path: Path, output_dir: Path, policy_path: Path) -> dict[str, object]:
    evaluation = _object(evaluation_path, "evaluation")
    findings = _object(findings_path, "findings")
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    if evaluation.get("split") != "DEVELOPMENT" or findings.get("evaluation_split") != "DEVELOPMENT":
        raise FeedbackError("feedback actions require development-only evidence")
    try:
        external_evaluation = validate_bfcl_development_receipt(receipt_path=external_evaluation_path, config_path=external_config_path)
    except BfclError as error:
        raise FeedbackError(f"feedback requires terminal BFCL development evidence: {error}") from error
    if not isinstance(policy, dict) or policy.get("policy_version") != "feedback-v1":
        raise FeedbackError("feedback policy must freeze feedback-v1")
    pool = json.loads(candidate_pool_path.read_text(encoding="utf-8"))
    if not isinstance(pool, list) or not pool:
        raise FeedbackError("feedback requires a non-empty frozen candidate pool")
    versions = {item.get("candidate_pool_version") for item in pool if isinstance(item, dict)}
    if len(versions) != 1 or None in versions:
        raise FeedbackError("feedback candidates must belong to exactly one frozen pool")
    actions: list[dict[str, object]] = []
    for finding in findings.get("findings", []):
        if not isinstance(finding, dict) or not isinstance(finding.get("finding_id"), str) or not isinstance(finding.get("target_slice"), dict):
            raise FeedbackError("finding is incomplete")
        actions.append({"action_id": f"action-{finding['finding_id']}", "finding_id": finding["finding_id"], "candidate_pool_version": next(iter(versions)), "action": "RESELECT_SAME_POOL", "target_slice": finding["target_slice"], "status": "ACTIONED", "retest_ref": None, "prohibited_ingress": ["PROJECT_SAMPLING", "MODEL_GENERATION", "MODEL_EVALUATION"]})
    receipt = {"kind": "development-feedback-actions", "evaluation_split": "DEVELOPMENT", "candidate_pool_version": next(iter(versions)), "external_evaluation": {"kind": external_evaluation["kind"], "official_commit": external_evaluation["official_commit"], "receipt_sha256": sha256_file(external_evaluation_path), "config_sha256": sha256_file(external_config_path)}, "actions": actions, "final_test_ingress_count": 0}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "data_actions.json").write_bytes(canonical_json_bytes(receipt))
    return receipt
