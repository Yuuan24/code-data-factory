"""Fail-closed BFCL V4 pinned-subset provenance gate."""

from __future__ import annotations

import json
import subprocess
import tarfile
from pathlib import Path
from typing import Any

import yaml

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes, sha256_file


class BfclError(ValueError):
    """The supplied official BFCL runner cannot prove its frozen provenance."""


def _object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BfclError(f"BFCL {label} must be an object")
    return value


def validate_bfcl_development_receipt(*, receipt_path: Path, config_path: Path) -> dict[str, Any]:
    """Fail closed unless the frozen local BFCL development subset completed."""
    receipt = _object(receipt_path, "development receipt")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise BfclError("BFCL config must be an object")
    subset = config.get("development_subset")
    if not isinstance(subset, dict) or not all(isinstance(ids, list) and ids for ids in subset.values()):
        raise BfclError("BFCL config must freeze a non-empty development subset")
    expected = {
        "kind": "bfcl-v4-development-evaluation",
        "split": "DEVELOPMENT",
        "terminal_status": "COMPLETED",
        "official_commit": config.get("official_commit"),
        "official_archive_sha256": config.get("official_archive_sha256"),
        "runner_package": config.get("package"),
        "full_bfcl_score_claimed": False,
        "infrastructure_failure_count": 0,
    }
    if any(receipt.get(field) != value for field, value in expected.items()):
        raise BfclError("BFCL development receipt is not the frozen completed development run")
    categories = receipt.get("categories")
    if not isinstance(categories, dict) or set(categories) != set(subset):
        raise BfclError("BFCL development receipt categories do not match the frozen subset")
    selected_total = 0
    for category, ids in subset.items():
        result = categories.get(category)
        if not isinstance(category, str) or not isinstance(ids, list) or not isinstance(result, dict):
            raise BfclError("BFCL development receipt has malformed category evidence")
        if result.get("selected_ids") != ids or result.get("selected_count") != len(ids):
            raise BfclError("BFCL development receipt task IDs do not match the frozen subset")
        if not isinstance(result.get("accuracy"), (int, float)) or not 0 <= result["accuracy"] <= 1:
            raise BfclError("BFCL development receipt has invalid category accuracy")
        if any(not isinstance(result.get(field), str) or len(result[field]) != 64 for field in ("result_sha256", "score_sha256")):
            raise BfclError("BFCL development receipt lacks result or score hashes")
        selected_total += len(ids)
    if receipt.get("selected_task_count") != selected_total:
        raise BfclError("BFCL development receipt denominator does not match the frozen subset")
    if not isinstance(receipt.get("protocol_deviations"), list):
        raise BfclError("BFCL development receipt must state protocol deviations")
    return receipt


def freeze_bfcl_subset(*, config_path: Path, output_dir: Path, checkout: Path | None = None, archive_path: Path | None = None) -> dict[str, object]:
    """Record only the official, pinned, non-executable local subset."""
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("benchmark") != "BFCL-V4":
        raise BfclError("BFCL config is invalid")
    expected = config.get("official_commit")
    if not isinstance(expected, str) or len(expected) != 40:
        raise BfclError("BFCL config must pin a full official commit")
    if (checkout is None) == (archive_path is None):
        raise BfclError("provide exactly one BFCL checkout or exact-commit archive")
    if checkout is not None:
        try:
            observed = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        except subprocess.CalledProcessError as error:
            raise BfclError("BFCL checkout is not a readable Git checkout") from error
        if observed != expected:
            raise BfclError("BFCL checkout does not match the frozen official commit")
        license_files = [path for path in checkout.glob("LICENSE*") if path.is_file()]
        if not license_files:
            raise BfclError("BFCL checkout lacks a license file")
        licenses = [{"name": path.name, "sha256": sha256_file(path)} for path in license_files]
        source_method = "GIT_EXACT_COMMIT"
    else:
        assert archive_path is not None
        source_url, expected_archive_hash = config.get("official_archive_url"), config.get("official_archive_sha256")
        if not isinstance(source_url, str) or expected not in source_url or not isinstance(expected_archive_hash, str):
            raise BfclError("BFCL archive fallback must pin an exact-commit URL and SHA-256")
        if sha256_file(archive_path) != expected_archive_hash:
            raise BfclError("BFCL exact-commit archive SHA-256 does not match")
        prefix = f"gorilla-{expected}/"
        try:
            with tarfile.open(archive_path, "r:gz") as source:
                license_member = source.getmember(prefix + "LICENSE")
                handle = source.extractfile(license_member)
                if handle is None:
                    raise BfclError("BFCL archive lacks a readable license file")
                licenses = [{"name": "LICENSE", "sha256": sha256_bytes(handle.read())}]
        except (OSError, tarfile.TarError, KeyError) as error:
            raise BfclError("BFCL archive is not the pinned official source layout") from error
        observed = expected
        source_method = "GITHUB_EXACT_COMMIT_ARCHIVE"
    categories = config.get("categories")
    excluded = config.get("excluded_categories")
    if not isinstance(categories, list) or not isinstance(excluded, list) or "multi_turn" not in categories or "irrelevance" not in categories or "executable" not in excluded:
        raise BfclError("BFCL subset must freeze local multi-turn, irrelevance, and executable exclusion")
    receipt: dict[str, object] = {"kind": "bfcl-v4-pinned-subset", "official_commit": observed, "source_method": source_method, "official_archive_url": config.get("official_archive_url"), "license_files": licenses, "categories": categories, "excluded_categories": excluded, "protocol_deviations": config.get("protocol_deviations"), "runner_package": config.get("package"), "full_bfcl_score_claimed": False, "untrusted_execution_status": "NOT_SELECTED"}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_bytes(canonical_json_bytes(receipt))
    return receipt
