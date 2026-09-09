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
    path: Path


def revoke_source(source_record_id: str, *, releases_root: Path, ledger_root: Path) -> RevocationLedger:
    """Create an append-only invalidation ledger for every release using a source record."""

    affected: list[str] = []
    for release in sorted(releases_root.iterdir()) if releases_root.exists() else []:
        lineage = release / "lineage_index.json"
        if lineage.is_file() and source_record_id in json.loads(lineage.read_text(encoding="utf-8")).get("source_records", []):
            affected.append(release.name)
    payload = {
        "source_record_id": source_record_id,
        "affected_dataset_ids": affected,
        "action": "INVALIDATE_DISTRIBUTION",
        "created_at": datetime.now(UTC).isoformat(),
    }
    digest = sha256_bytes(canonical_json_bytes(payload))
    ledger_root.mkdir(parents=True, exist_ok=True)
    path = ledger_root / f"{source_record_id}-{digest[:12]}.json"
    path.write_bytes(canonical_json_bytes(payload))
    return RevocationLedger(source_record_id=source_record_id, affected_dataset_ids=affected, path=path)
