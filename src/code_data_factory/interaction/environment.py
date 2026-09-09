"""Fail-closed Linux container preflight; a developer machine cannot impersonate it."""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class EnvironmentPreflight:
    status: str
    findings: dict[str, object]


def check_environment(config_path: Path) -> EnvironmentPreflight:
    config: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("execution config must be a mapping")
    runtime = config.get("container_runtime")
    runtime_path = shutil.which(str(runtime)) if runtime else None
    findings: dict[str, object] = {
        "platform": platform.system(),
        "effective_uid": os.geteuid() if hasattr(os, "geteuid") else None,
        "container_runtime": runtime,
        "container_runtime_path": runtime_path,
        "network_default": config.get("network_default"),
        "read_only_root": config.get("read_only_root"),
        "privileged": config.get("privileged"),
        "limits": config.get("limits"),
    }
    valid = (
        findings["platform"] == "Linux"
        and findings["effective_uid"] not in {0, None}
        and runtime_path is not None
        and findings["network_default"] == "disabled"
        and findings["read_only_root"] is True
        and findings["privileged"] is False
        and isinstance(findings["limits"], dict)
    )
    return EnvironmentPreflight("PASSED" if valid else "FAILED", findings)
