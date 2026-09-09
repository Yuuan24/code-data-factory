"""Stable source/template/duplicate-connected split assignment."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SplitAssignment:
    task_id: str
    scope: str
    split_group_id: str


@dataclass(frozen=True)
class BridgeConflict:
    task_id: str
    conflicting_scopes: tuple[str, ...]
    related_task_ids: tuple[str, ...]


@dataclass(frozen=True)
class AssignmentResult:
    assignments: list[SplitAssignment]
    conflicts: list[BridgeConflict]
    quarantined_task_ids: list[str]
    invalidated_task_ids: tuple[str, ...] = ()


class SplitRegistry:
    """A frozen registry that quarantines, rather than rebalances, bridge edges."""

    def __init__(self, *, policy_version: str) -> None:
        self.policy_version = policy_version
        self.frozen_assignments: dict[str, str] = {}
        self.assignments: list[SplitAssignment] = []

    def freeze(self, assignments: dict[str, str]) -> None:
        self.frozen_assignments.update(assignments)

    @classmethod
    def load(cls, path: Path) -> SplitRegistry:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("policy_version"), str):
            raise ValueError("split registry must have a policy_version")
        assignments = payload.get("frozen_assignments")
        if not isinstance(assignments, dict) or not all(
            isinstance(task_id, str) and isinstance(scope, str) for task_id, scope in assignments.items()
        ):
            raise ValueError("split registry must have string frozen assignments")
        registry = cls(policy_version=payload["policy_version"])
        registry.freeze(assignments)
        return registry

    def write(self, path: Path, *, result: AssignmentResult) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "policy_version": self.policy_version,
                    "frozen_assignments": dict(sorted(self.frozen_assignments.items())),
                    "new_assignments": [item.__dict__ for item in result.assignments],
                    "bridge_conflicts": [item.__dict__ for item in result.conflicts],
                    "quarantined_task_ids": result.quarantined_task_ids,
                    "invalidated_task_ids": list(result.invalidated_task_ids),
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _scope(group_id: str) -> str:
        values = ("TRAIN", "DEVELOPMENT", "TEST")
        return values[int(hashlib.sha256(group_id.encode("utf-8")).hexdigest(), 16) % len(values)]

    def assign(self, tasks: list[dict[str, Any]]) -> AssignmentResult:
        task_by_id = {str(task["task_id"]): task for task in tasks}
        parent = {task_id: task_id for task_id in task_by_id}

        def find(value: str) -> str:
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value

        def union(left: str, right: str) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        anchors: dict[tuple[str, str], str] = {}
        for task_id, task in task_by_id.items():
            for source in task.get("source_groups", []):
                key = ("source", str(source))
                if key in anchors:
                    union(task_id, anchors[key])
                anchors[key] = task_id
            template = task.get("template_root")
            if template:
                key = ("template", str(template))
                if key in anchors:
                    union(task_id, anchors[key])
                anchors[key] = task_id
            for related in task.get("related_task_ids", []):
                if related in parent:
                    union(task_id, str(related))

        members: dict[str, list[str]] = {}
        for task_id in task_by_id:
            members.setdefault(find(task_id), []).append(task_id)
        conflicts: list[BridgeConflict] = []
        quarantined: list[str] = []
        assignments: list[SplitAssignment] = []
        for group_members in members.values():
            frozen_scopes = {self.frozen_assignments[item] for item in group_members if item in self.frozen_assignments}
            external_related = {
                str(related)
                for item in group_members
                for related in task_by_id[item].get("related_task_ids", [])
                if str(related) in self.frozen_assignments
            }
            frozen_scopes.update(self.frozen_assignments[item] for item in external_related)
            related = tuple(sorted(external_related or set(group_members)))
            if len(frozen_scopes) > 1:
                scopes = tuple(sorted(frozen_scopes))
                for task_id in group_members:
                    if task_id not in self.frozen_assignments:
                        conflicts.append(
                            BridgeConflict(task_id=task_id, conflicting_scopes=scopes, related_task_ids=related)
                        )
                        quarantined.append(task_id)
                continue
            canonical = "|".join(sorted(group_members))
            group_id = f"{self.policy_version}:{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"
            scope = next(iter(frozen_scopes), self._scope(group_id))
            for task_id in sorted(group_members):
                if task_id in self.frozen_assignments:
                    scope = self.frozen_assignments[task_id]
                else:
                    self.frozen_assignments[task_id] = scope
                    assignment = SplitAssignment(task_id=task_id, scope=scope, split_group_id=group_id)
                    self.assignments.append(assignment)
                    assignments.append(assignment)
        invalidated = tuple(sorted({related for conflict in conflicts for related in conflict.related_task_ids}))
        return AssignmentResult(
            assignments=assignments,
            conflicts=conflicts,
            quarantined_task_ids=quarantined,
            invalidated_task_ids=invalidated,
        )
