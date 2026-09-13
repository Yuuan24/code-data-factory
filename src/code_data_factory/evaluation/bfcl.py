"""Fail-closed BFCL V4 pinned-subset provenance gate."""

from __future__ import annotations

import subprocess
import tarfile
from pathlib import Path

import yaml

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes, sha256_file


class BfclError(ValueError):
    """The supplied official BFCL runner cannot prove its frozen provenance."""


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
