"""Paired SFT recipe drafts from one frozen external candidate pool."""

from __future__ import annotations

import json
from pathlib import Path

from code_data_factory.contracts.artifacts import canonical_json_bytes


class RecipeError(ValueError):
    """A same-pool recipe cannot satisfy its declared support constraints."""


MATCH_FIELDS = ("source_id", "task_family", "dependency_depth", "length_bin", "verification_strength", "baseline_difficulty")


def build_recipe_drafts(*, actions_path: Path, candidate_pool_path: Path, output_dir: Path) -> dict[str, object]:
    actions = json.loads(actions_path.read_text(encoding="utf-8"))
    pool = json.loads(candidate_pool_path.read_text(encoding="utf-8"))
    if not isinstance(actions, dict) or not isinstance(actions.get("actions"), list) or not isinstance(pool, list):
        raise RecipeError("recipe inputs are malformed")
    action_pool = actions.get("candidate_pool_version")
    if not isinstance(action_pool, str) or any(not isinstance(item, dict) or item.get("candidate_pool_version") != action_pool for item in pool):
        raise RecipeError("recipes must use exactly the feedback action's frozen pool")
    closed: list[dict[str, object]] = []
    random: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    used: set[str] = set()
    for action in actions["actions"]:
        if not isinstance(action, dict) or not isinstance(action.get("finding_id"), str) or not isinstance(action.get("target_slice"), dict):
            raise RecipeError("non-random recipe selection requires a finding-backed action")
        target = action["target_slice"].get("failure_type")
        eligible = [item for item in pool if str(item.get("demonstration_id")) not in used and item.get("task_family") == action["target_slice"].get("task_family")]
        selected = next((item for item in eligible if target in item.get("failure_types", [])), None)
        if selected is None:
            excluded.append({"finding_id": action["finding_id"], "reason": "NO_TARGET_SUPPORT"})
            continue
        key = tuple(selected.get(field) for field in MATCH_FIELDS)
        control = next((item for item in eligible if tuple(item.get(field) for field in MATCH_FIELDS) == key and target not in item.get("failure_types", [])), None)
        if control is None:
            excluded.append({"finding_id": action["finding_id"], "reason": "NO_MATCHED_CONTROL"})
            continue
        used.update({str(selected["demonstration_id"]), str(control["demonstration_id"])})
        closed.append({"demonstration_id": selected["demonstration_id"], "finding_id": action["finding_id"], "match_key": key, "target_failure_type": target})
        random.append({"demonstration_id": control["demonstration_id"], "matched_to": selected["demonstration_id"], "match_key": key})
    if not closed:
        raise RecipeError("no jointly supported matched recipe pair exists")
    receipt = {"kind": "same-pool-recipe-drafts", "candidate_pool_version": action_pool, "target_intervention": "development-failure-type coverage", "match_fields": list(MATCH_FIELDS), "closed_loop": closed, "random_matched": random, "paired_member_count": len(closed), "common_exclusions": excluded, "sft_ingress_prohibited": ["PROJECT_SAMPLING", "MODEL_GENERATION", "MODEL_EVALUATION"]}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "recipe_drafts.json").write_bytes(canonical_json_bytes(receipt))
    return receipt
