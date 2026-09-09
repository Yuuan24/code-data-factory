"""Fixed-source metadata audit with optional Hugging Face revision inspection."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from code_data_factory.contracts.artifacts import canonical_json_bytes, sha256_bytes, sha256_file


@dataclass(frozen=True)
class AuditedSource:
    source_id: str
    source_uri: str
    revision: str
    license: str
    usage_scope: str
    source_kind: str
    required_tools: tuple[str, ...]
    status: str
    record_count: int | None
    dependency_status: str
    content_sha256: str | None
    content_hash_status: str
    sensitive_check_status: str
    actual_tool_scope: tuple[str, ...] | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SourceAuditReport:
    manifest_sha256: str
    sources: list[AuditedSource]


def _load(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(content) if path.suffix in {".yaml", ".yml"} else json.loads(content)
    if not isinstance(loaded, dict) or not isinstance(loaded.get("sources"), list):
        raise ValueError("source manifest must contain a sources list")
    return loaded


def _remote_hf_status(source_uri: str, revision: str) -> tuple[str, tuple[str, ...]]:
    if importlib.util.find_spec("huggingface_hub") is None:
        return "MISSING_DEPENDENCY", ("huggingface_hub is not installed",)
    prefix = "https://huggingface.co/datasets/"
    if not source_uri.startswith(prefix):
        return "REMOTE_NOT_FETCHED", ("remote audit is supported only for Hugging Face datasets",)
    repo_id = source_uri.removeprefix(prefix).strip("/")
    from huggingface_hub import HfApi

    try:
        info = HfApi().dataset_info(repo_id=repo_id, revision=revision)
    except Exception as error:  # network/auth failures are data facts, not synthetic success
        return "REMOTE_UNAVAILABLE", (f"{type(error).__name__}: {error}",)
    if getattr(info, "sha", None) != revision:
        return "REVISION_MISMATCH", (f"resolved revision {getattr(info, 'sha', None)!r}",)
    return "AUDITED_REMOTE", ()


def _tool_names(value: object) -> set[str]:
    """Extract declared target-tool names without retaining source payload text."""

    if isinstance(value, str):
        try:
            return _tool_names(json.loads(value))
        except json.JSONDecodeError:
            return {name.strip() for name in value.split(",") if name.strip()}
    if isinstance(value, list):
        return set().union(*(_tool_names(item) for item in value)) if value else set()
    if isinstance(value, dict):
        names = {
            str(value[key]).strip()
            for key in ("name", "tool_name")
            if isinstance(value.get(key), str) and value[key].strip()
        }
        if names:
            return names
        return set().union(*(_tool_names(item) for item in value.values())) if value else set()
    return set()


def audit_sources(manifest_path: Path, *, output_dir: Path, fetch_remote: bool) -> SourceAuditReport:
    """Audit declared immutable source metadata without promoting it to executable data."""

    manifest = _load(manifest_path)
    audited: list[AuditedSource] = []
    for source in manifest["sources"]:
        if not isinstance(source, dict):
            raise ValueError("every source declaration must be an object")
        required = ("source_id", "source_uri", "revision", "license", "usage_scope", "source_kind")
        missing = [name for name in required if not isinstance(source.get(name), str) or not source[name]]
        if missing:
            raise ValueError(f"source declaration is missing {', '.join(missing)}")
        local_path = source.get("local_path")
        count: int | None = None
        actual_tools: tuple[str, ...] | None = None
        sensitive_status = "UNAVAILABLE_NO_RECORD_SAMPLE"
        warnings: tuple[str, ...] = ()
        dependency_status = "NOT_REQUIRED"
        content_sha256: str | None = None
        content_hash_status = "NOT_APPLICABLE"
        if isinstance(local_path, str):
            local = Path(local_path)
            if not local.is_file():
                raise ValueError(f"local source is missing: {local}")
            content_sha256 = sha256_file(local)
            expected_hash = source.get("expected_sha256")
            content_hash_status = (
                "MATCHED"
                if isinstance(expected_hash, str) and expected_hash == content_sha256
                else "UNDECLARED" if expected_hash is None else "MISMATCH"
            )
            if content_hash_status == "MISMATCH":
                raise ValueError(f"local source digest mismatch: {source['source_id']}")
            if local.suffix == ".parquet":
                parquet = pq.ParquetFile(local)
                count = parquet.metadata.num_rows
                names = set(parquet.schema_arrow.names)
                sensitive_names = {"email", "phone", "password", "token", "address", "user_id"} & names
                free_text = {"question", "messages"} & names
                sensitive_status = (
                    "POTENTIAL_FREE_TEXT_REVIEW_REQUIRED" if free_text else "NO_DECLARED_SENSITIVE_FIELD_NAMES"
                )
                if sensitive_names:
                    sensitive_status = "SENSITIVE_FIELD_NAMES_PRESENT"
                tools: set[str] = set()
                if "target_tools" in names:
                    sample = parquet.read(columns=["target_tools"]).column("target_tools").slice(0, 1000)
                    for item in sample.to_pylist():
                        tools.update(_tool_names(item))
                actual_tools = tuple(sorted(tools))
            else:
                records = json.loads(local.read_text(encoding="utf-8"))
                if not isinstance(records, list):
                    raise ValueError(f"local source {source['source_id']} must be a JSON array")
                count = len(records)
                actual_tools = tuple(sorted({str(call.get("name")) for record in records if isinstance(record, dict) for message in record.get("messages", []) if isinstance(message, dict) for call in message.get("tool_calls", []) if isinstance(call, dict) and isinstance(call.get("name"), str)}))
                sensitive_status = "NO_DECLARED_SENSITIVE_FIELD_NAMES"
            if fetch_remote:
                remote_status, remote_warnings = _remote_hf_status(
                    source["source_uri"], source["revision"]
                )
                status = "AUDITED_LOCAL_AND_REMOTE" if remote_status == "AUDITED_REMOTE" else remote_status
                dependency_status = "AVAILABLE" if remote_status == "AUDITED_REMOTE" else remote_status
                warnings = remote_warnings
            else:
                status = "AUDITED_LOCAL"
        elif fetch_remote:
            status, warnings = _remote_hf_status(source["source_uri"], source["revision"])
            dependency_status = "AVAILABLE" if status == "AUDITED_REMOTE" else status
        else:
            status = "METADATA_ONLY"
            warnings = ("remote access was not requested",)
        audited.append(
            AuditedSource(
                source_id=source["source_id"],
                source_uri=source["source_uri"],
                revision=source["revision"],
                license=source["license"],
                usage_scope=source["usage_scope"],
                source_kind=source["source_kind"],
                required_tools=tuple(str(tool) for tool in source.get("required_tools", [])),
                status=status,
                record_count=count,
                dependency_status=dependency_status,
                content_sha256=content_sha256,
                content_hash_status=content_hash_status,
                sensitive_check_status=sensitive_status,
                actual_tool_scope=actual_tools,
                warnings=warnings,
            )
        )
    report = SourceAuditReport(
        manifest_sha256=sha256_bytes(canonical_json_bytes(manifest)), sources=audited
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    serialized = {"manifest_sha256": report.manifest_sha256, "sources": [asdict(item) for item in audited]}
    (output_dir / "source_report.json").write_bytes(canonical_json_bytes(serialized))
    pq.write_table(pa.Table.from_pylist(serialized["sources"]), output_dir / "source_report.parquet")
    return report
