from __future__ import annotations

from pathlib import Path


def test_openbayes_bootstrap_only_uses_persistent_workspace_paths() -> None:
    script = Path("scripts/openbayes/bootstrap.sh").read_text(encoding="utf-8")
    assert "/openbayes/home/code-data-factory" in script
    assert "/openbayes/home/.uv/python" in script
    assert "/openbayes/home/.cache/uv" in script
    assert "/openbayes/home/.pylibs/bin/uv" in script
    assert "/openbayes/home/cdf-wheelhouse" in script
    assert "https://repo.huaweicloud.com/repository/pypi/simple" in script
    assert "venv .venv --python 3.12 --allow-existing" in script
    assert "pip install --python .venv/bin/python --require-hashes" in script
    assert "sync --frozen --all-groups --offline --no-build-isolation --no-editable" in script
    assert "--no-index --find-links" in script
    assert "curl" not in script
    assert " /tmp" not in script


def test_openbayes_guide_keeps_the_evidence_boundary_explicit() -> None:
    guide = Path("docs/openbayes-environment.md").read_text(encoding="utf-8")
    assert "linux_probe.json" in guide
    assert "does not run a model" in guide
    assert "/openbayes/home" in guide
    assert "Huawei Cloud mirror" in guide
    assert "new rented instance" in guide
