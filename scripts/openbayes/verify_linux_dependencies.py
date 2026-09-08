"""Verify the locked dependency surface and Parquet round trip on a Linux OpenBayes workspace."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REQUIRED_PACKAGES = (
    "pydantic",
    "pyarrow",
    "PyYAML",
    "datasketch",
    "duckdb",
    "dvc",
    "huggingface-hub",
    "ray",
    "Pint",
    "smolagents",
    "mlflow",
    "peft",
    "transformers",
    "trl",
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", required=True, type=Path)
    return result


def package_versions() -> tuple[dict[str, str], list[str]]:
    versions: dict[str, str] = {}
    missing: list[str] = []
    for package in REQUIRED_PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            missing.append(package)
    return versions, missing


def parquet_round_trip(output_dir: Path) -> bool:
    import pyarrow as pa
    import pyarrow.parquet as pq
    from pydantic import BaseModel

    class Probe(BaseModel):
        value: int

    with tempfile.TemporaryDirectory(dir=output_dir) as temporary:
        path = Path(temporary) / "probe.parquet"
        pq.write_table(pa.table({"value": [Probe(value=7).value]}), path)
        return bool(pq.read_table(path).to_pylist() == [{"value": 7}])


def main() -> int:
    arguments = parser().parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    versions, missing = package_versions()
    report: dict[str, Any] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "required_versions": versions,
        "missing_packages": missing,
        "parquet_round_trip": None,
        "status": "FAILED",
    }
    if platform.system() != "Linux":
        report["reason"] = "Linux probe must run on Linux"
    elif missing:
        report["reason"] = "locked packages are missing"
    else:
        report["parquet_round_trip"] = parquet_round_trip(arguments.output.parent)
        report["status"] = "PASSED" if report["parquet_round_trip"] else "FAILED"
    arguments.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "PASSED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
