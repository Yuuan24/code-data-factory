from __future__ import annotations

import subprocess
import tarfile
from pathlib import Path

import pytest

from code_data_factory.evaluation.bfcl import BfclError, freeze_bfcl_subset


def test_bfcl_subset_requires_exact_checkout_and_excludes_executable_categories(tmp_path: Path) -> None:
    checkout = tmp_path / "bfcl"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    (checkout / "LICENSE").write_text("Apache-2.0", encoding="utf-8")
    subprocess.run(["git", "-C", str(checkout), "add", "LICENSE"], check=True)
    subprocess.run(["git", "-C", str(checkout), "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-qm", "fixture"], check=True)
    sha = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    config = tmp_path / "bfcl.yaml"
    config.write_text(f"benchmark: BFCL-V4\nofficial_commit: '{sha}'\ncategories: [multi_turn, irrelevance]\nexcluded_categories: [executable, live]\nprotocol_deviations: [fixture]\n", encoding="utf-8")
    receipt = freeze_bfcl_subset(config_path=config, checkout=checkout, output_dir=tmp_path / "out")
    assert receipt["official_commit"] == sha
    config.write_text(config.read_text(encoding="utf-8").replace(sha, "a" * 40), encoding="utf-8")
    with pytest.raises(BfclError, match="does not match"):
        freeze_bfcl_subset(config_path=config, checkout=checkout, output_dir=tmp_path / "bad")


def test_bfcl_subset_accepts_only_the_configured_exact_commit_archive(tmp_path: Path) -> None:
    commit = "b" * 40
    source = tmp_path / f"gorilla-{commit}"
    source.mkdir()
    (source / "LICENSE").write_text("Apache-2.0", encoding="utf-8")
    archive = tmp_path / "gorilla.tar.gz"
    with tarfile.open(archive, "w:gz") as target:
        target.add(source, arcname=source.name)
    from code_data_factory.contracts.artifacts import sha256_file

    config = tmp_path / "bfcl-archive.yaml"
    config.write_text(f"benchmark: BFCL-V4\nofficial_commit: '{commit}'\nofficial_archive_url: https://codeload.example/gorilla/tar.gz/{commit}\nofficial_archive_sha256: {sha256_file(archive)}\ncategories: [multi_turn, irrelevance]\nexcluded_categories: [executable, live]\nprotocol_deviations: [fixture]\n", encoding="utf-8")
    receipt = freeze_bfcl_subset(config_path=config, archive_path=archive, output_dir=tmp_path / "out")
    assert receipt["source_method"] == "GITHUB_EXACT_COMMIT_ARCHIVE"
