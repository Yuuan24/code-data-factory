"""Fail-closed preflight for a platform-provided Linux container."""

from __future__ import annotations

import errno
import os
import platform
import resource
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class EnvironmentPreflight:
    status: str
    findings: dict[str, object]


def _configured_limits(limits: object) -> dict[str, int] | None:
    if not isinstance(limits, dict):
        return None
    keys = {"cpu_seconds", "memory_mib", "pids"}
    if set(limits) != keys or not all(isinstance(limits[key], int) and limits[key] > 0 for key in keys):
        return None
    return {key: limits[key] for key in keys}


def _actual_limits() -> dict[str, int | None]:
    def soft_limit(kind: int) -> int | None:
        value = resource.getrlimit(kind)[0]
        return value if value != resource.RLIM_INFINITY else None

    return {
        "cpu_seconds": soft_limit(resource.RLIMIT_CPU),
        "memory_mib": (value // (1024 * 1024)) if (value := soft_limit(resource.RLIMIT_AS)) is not None else None,
        "pids": soft_limit(resource.RLIMIT_NPROC),
    }


def _platform_container() -> bool:
    return Path("/.dockerenv").exists()


def _source_is_read_only(source_root: Path) -> bool:
    if not source_root.is_dir() or os.access(source_root, os.W_OK):
        return False
    return all(not os.access(path, os.W_OK) for path in source_root.rglob("*") if path.is_file())


def _network_syscalls_blocked() -> bool:
    try:
        candidate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError as error:
        return error.errno in {errno.EACCES, errno.EPERM}
    candidate.close()
    return False


def check_environment(config_path: Path) -> EnvironmentPreflight:
    config: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("execution config must be a mapping")
    limits = _configured_limits(config.get("limits"))
    source_root_value = config.get("source_root")
    source_root = (config_path.parent / source_root_value).resolve() if isinstance(source_root_value, str) else None
    actual_limits = _actual_limits()
    findings: dict[str, object] = {
        "platform": platform.system(),
        "effective_uid": os.geteuid() if hasattr(os, "geteuid") else None,
        "container_runtime": config.get("container_runtime"),
        "platform_container": _platform_container(),
        "source_root": str(source_root) if source_root else None,
        "source_read_only": _source_is_read_only(source_root) if source_root else False,
        "network_default": config.get("network_default"),
        "network_syscalls_blocked": _network_syscalls_blocked(),
        "configured_limits": limits,
        "actual_limits": actual_limits,
    }
    limits_enforced = limits is not None
    if limits is not None:
        for key, maximum in limits.items():
            actual = actual_limits[key]
            if not isinstance(actual, int) or actual > maximum:
                limits_enforced = False
                break
    valid = (
        findings["platform"] == "Linux"
        and findings["effective_uid"] not in {0, None}
        and findings["container_runtime"] == "platform"
        and findings["platform_container"] is True
        and findings["source_read_only"] is True
        and findings["network_default"] == "disabled"
        and findings["network_syscalls_blocked"] is True
        and limits_enforced
    )
    return EnvironmentPreflight("PASSED" if valid else "FAILED", findings)
