"""Fail-closed BFCL V4 pinned-subset provenance gate."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_file


class BfclError(ValueError):
    """The supplied official BFCL runner cannot prove its frozen provenance."""


def freeze_bfcl_subset(*, config_path: Path, checkout: Path, output_dir: Path) -> dict[str, object]:
    """Record only the official, pinned, non-executable local subset."""
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("benchmark") != "BFCL-V4":
        raise BfclError("BFCL config is invalid")
    expected = config.get("official_commit")
    if not isinstance(expected, str) or len(expected) != 40:
        raise BfclError("BFCL config must pin a full official commit")
    try:
        observed = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    except subprocess.CalledProcessError as error:
        raise BfclError("BFCL checkout is not a readable Git checkout") from error
    if observed != expected:
        raise BfclError("BFCL checkout does not match the frozen official commit")
    license_files = [path for path in checkout.glob("LICENSE*") if path.is_file()]
    if not license_files:
        raise BfclError("BFCL checkout lacks a license file")
    categories = config.get("categories")
    excluded = config.get("excluded_categories")
    if not isinstance(categories, list) or not isinstance(excluded, list) or "multi_turn" not in categories or "irrelevance" not in categories or "executable" not in excluded:
        raise BfclError("BFCL subset must freeze local multi-turn, irrelevance, and executable exclusion")
    receipt: dict[str, object] = {"kind": "bfcl-v4-pinned-subset", "official_commit": observed, "license_files": [{"name": path.name, "sha256": sha256_file(path)} for path in license_files], "categories": categories, "excluded_categories": excluded, "protocol_deviations": config.get("protocol_deviations"), "full_bfcl_score_claimed": False, "untrusted_execution_status": "NOT_SELECTED"}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_bytes(canonical_json_bytes(receipt))
    return receipt
