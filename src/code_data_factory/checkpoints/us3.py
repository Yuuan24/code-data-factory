"""US3 software checkpoint that refuses final-test feedback ingress."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_file
from code_data_factory.evaluation.bfcl import validate_bfcl_development_receipt


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"invalid US3 input: {path.name}")
    return value


def run_us3_checkpoint(*, output_path: Path, suite_manifest: Path, evaluation_path: Path, external_evaluation_path: Path, external_config_path: Path, findings_path: Path, actions_path: Path, recipes_path: Path) -> dict[str, object]:
    suite, evaluation, findings, actions, recipes = (_object(path) for path in (suite_manifest, evaluation_path, findings_path, actions_path, recipes_path))
    external_evaluation = validate_bfcl_development_receipt(receipt_path=external_evaluation_path, config_path=external_config_path)
    action_rows = actions.get("actions")
    checks = {
        "frozen_development_suite": isinstance(suite.get("development"), list) and len(suite["development"]) >= 200,
        "development_only_feedback": evaluation.get("split") == "DEVELOPMENT" and findings.get("evaluation_split") == "DEVELOPMENT" and actions.get("evaluation_split") == "DEVELOPMENT" and actions.get("final_test_ingress_count") == 0,
        "terminal_external_development": external_evaluation.get("split") == "DEVELOPMENT" and external_evaluation.get("terminal_status") == "COMPLETED",
        "finding_bound_actions": isinstance(action_rows, list) and all(isinstance(item, dict) and item.get("finding_id") for item in action_rows),
        "same_pool_recipes": recipes.get("candidate_pool_version") == actions.get("candidate_pool_version") and isinstance(recipes.get("paired_member_count"), int) and recipes["paired_member_count"] > 0,
    }
    if not all(checks.values()):
        raise ValueError("US3 software checkpoint facts are inconsistent")
    receipt: dict[str, object] = {"checkpoint": "US3_SOFTWARE", "evidence_level": "SOFTWARE_VALIDATED", "checks": checks, "input_hashes": {name: sha256_file(path) for name, path in {"suite": suite_manifest, "evaluation": evaluation_path, "external_evaluation": external_evaluation_path, "external_config": external_config_path, "findings": findings_path, "actions": actions_path, "recipes": recipes_path}.items()}, "limitations": ["This fixture checkpoint does not unlock final test or establish a training feedback loop.", "SC-008 requires T079, T083, and T084 real training and reevaluation evidence."]}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_json_bytes(receipt))
    return receipt
