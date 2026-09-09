from __future__ import annotations

from pathlib import Path

import yaml


def test_dvc_build_stages_require_explicit_full_input_manifest() -> None:
    pipeline = yaml.safe_load(Path("dvc.yaml").read_text(encoding="utf-8"))
    stages = pipeline["stages"]
    for name in ("build_us1_local", "build_us1_ray"):
        stage = stages[name]
        assert "data/build-inputs/pilot.json" in stage["cmd"]
        assert "data/build-inputs/pilot.json" in stage["deps"]
        assert any("data/draft/" in output for output in stage["outs"])
