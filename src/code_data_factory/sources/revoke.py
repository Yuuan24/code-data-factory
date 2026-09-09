"""Source revocation impact discovery without mutating immutable publication facts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes


@dataclass(frozen=True)
class RevocationLedger:
    source_record_id: str
    affected_dataset_ids: list[str]
    affected_run_ids: list[str]
    affected_claim_ids: list[str]
    path: Path


def _json_records(root: Path) -> list[dict[str, object]]:
    """Read only explicit JSON relationship records, never raw trajectory payloads."""

    if not root.exists():
        return []
    records: list[dict[str, object]] = []
    for path in sorted(root.rglob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        values = value if isinstance(value, list) else [value]
        records.extend(item for item in values if isinstance(item, dict))
    return records


def _matches_relationship(
    record: dict[str, object], *, source_record_id: str, dataset_ids: set[str], attempt_ids: set[str], decision_ids: set[str]
) -> bool:
    source_ids = record.get("source_record_ids", record.get("source_records", []))
    return (
        isinstance(source_ids, list)
        and source_record_id in source_ids
        or record.get("dataset_id") in dataset_ids
        or record.get("attempt_id") in attempt_ids
        or record.get("quality_decision_id") in decision_ids
    )


def _affected_ids(
    root: Path | None,
    *,
    id_field: str,
    source_record_id: str,
    dataset_ids: set[str],
    attempt_ids: set[str],
    decision_ids: set[str],
) -> list[str]:
    if root is None:
        return []
    return sorted(
        {
            str(record[id_field])
            for record in _json_records(root)
            if isinstance(record.get(id_field), str)
            and _matches_relationship(
                record,
                source_record_id=source_record_id,
                dataset_ids=dataset_ids,
                attempt_ids=attempt_ids,
                decision_ids=decision_ids,
            )
        }
    )


def revoke_source(
    source_record_id: str,
    *,
    releases_root: Path,
    ledger_root: Path,
    runs_root: Path | None = None,
    claims_root: Path | None = None,
) -> RevocationLedger:
    """Write an append-only invalidation ledger through source, release, run, and claim links."""

    affected: list[str] = []
    affected_attempts: set[str] = set()
    affected_decisions: set[str] = set()
    for release in sorted(releases_root.iterdir()) if releases_root.exists() else []:
        lineage = release / "lineage_index.json"
        if not lineage.is_file():
            continue
        index = json.loads(lineage.read_text(encoding="utf-8"))
        if source_record_id not in index.get("source_records", []):
            continue
        affected.append(release.name)
        for attempt in index.get("attempts", []):
            if isinstance(attempt, dict) and source_record_id in attempt.get("source_record_ids", []):
                attempt_id = attempt.get("attempt_id")
                decision_id = attempt.get("quality_decision_id")
                if isinstance(attempt_id, str):
                    affected_attempts.add(attempt_id)
                if isinstance(decision_id, str):
                    affected_decisions.add(decision_id)
    dataset_ids = set(affected)
    affected_runs = _affected_ids(
        runs_root,
        id_field="run_id",
        source_record_id=source_record_id,
        dataset_ids=dataset_ids,
        attempt_ids=affected_attempts,
        decision_ids=affected_decisions,
    )
    affected_claims = _affected_ids(
        claims_root,
        id_field="claim_id",
        source_record_id=source_record_id,
        dataset_ids=dataset_ids,
        attempt_ids=affected_attempts,
        decision_ids=affected_decisions,
    )
    payload = {
        "source_record_id": source_record_id,
        "affected_dataset_ids": affected,
        "affected_run_ids": affected_runs,
        "affected_claim_ids": affected_claims,
        "actions": {
            "datasets": "INVALIDATE_DISTRIBUTION",
            "runs": "INVALIDATE_EVIDENCE",
            "claims": "INVALIDATE_CLAIM",
        },
        "created_at": datetime.now(UTC).isoformat(),
    }
    digest = sha256_bytes(canonical_json_bytes(payload))
    ledger_root.mkdir(parents=True, exist_ok=True)
    path = ledger_root / f"{source_record_id}-{digest[:12]}.json"
    path.write_bytes(canonical_json_bytes(payload))
    return RevocationLedger(
        source_record_id=source_record_id,
        affected_dataset_ids=affected,
        affected_run_ids=affected_runs,
        affected_claim_ids=affected_claims,
        path=path,
    )
