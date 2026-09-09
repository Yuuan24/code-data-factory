from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from code_data_factory.contracts.artifacts import sha256_file
from code_data_factory.sources.audit import audit_sources, freeze_document_sources


def test_source_audit_records_fixed_metadata_and_missing_optional_dependency(tmp_path: Path) -> None:
    fixture = tmp_path / "records.json"
    fixture.write_text('[{"id":"one","messages":[]}]', encoding="utf-8")
    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "fixture",
                        "source_uri": "https://example.invalid/fixture",
                        "revision": "fixture-v1",
                        "license": "CC-BY-4.0",
                        "usage_scope": "HISTORICAL_ONLY",
                        "source_kind": "history",
                        "local_path": str(fixture),
                        "expected_sha256": sha256_file(fixture),
                        "required_tools": ["read_document"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = audit_sources(manifest, output_dir=tmp_path / "audit", fetch_remote=False)

    assert report.sources[0].status == "AUDITED_LOCAL"
    assert report.sources[0].record_count == 1
    assert report.sources[0].content_hash_status == "MATCHED"
    assert report.sources[0].usage_scope == "HISTORICAL_ONLY"
    assert (tmp_path / "audit" / "source_report.json").is_file()
    assert (tmp_path / "audit" / "source_report.parquet").is_file()


def test_source_audit_reads_parquet_tool_scope_without_preserving_records(tmp_path: Path) -> None:
    fixture = tmp_path / "records.parquet"
    pq.write_table(
        pa.table(
            {
                "question": ["private fixture text"],
                "messages": ["private fixture messages"],
                "target_tools": ['[{"name":"read_document"},{"tool_name":"calculate"}]'],
            }
        ),
        fixture,
    )
    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "parquet-fixture",
                        "source_uri": "https://example.invalid/fixture",
                        "revision": "fixture-v1",
                        "license": "CC-BY-4.0",
                        "usage_scope": "HISTORICAL_ONLY",
                        "source_kind": "history",
                        "local_path": str(fixture),
                        "expected_sha256": sha256_file(fixture),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    source = audit_sources(manifest, output_dir=tmp_path / "audit", fetch_remote=False).sources[0]

    assert source.record_count == 1
    assert source.actual_tool_scope == ("calculate", "read_document")
    assert source.sensitive_check_status == "POTENTIAL_FREE_TEXT_REVIEW_REQUIRED"


def test_document_freeze_writes_content_addressed_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import code_data_factory.sources.audit as audit

    class Response:
        headers = type("Headers", (), {"get_content_type": staticmethod(lambda: "text/html")})()

        def read(self) -> bytes:
            return b"<html>frozen document</html>"

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(audit, "urlopen", lambda *_args, **_kwargs: Response())
    manifest = tmp_path / "documents.json"
    manifest.write_text(
        json.dumps({"sources": [{"source_id": "docs", "source_uri": "https://example.invalid/docs", "revision": "v1", "license": "PSF-2.0", "usage_scope": "TRAIN", "source_kind": "public-documentation"}]}),
        encoding="utf-8",
    )

    frozen = freeze_document_sources(manifest, output_dir=tmp_path / "raw")

    snapshot = json.loads(frozen.read_text(encoding="utf-8"))["sources"][0]
    assert snapshot["content_sha256"] == sha256_file(tmp_path / "raw" / snapshot["path"])
    assert snapshot["byte_size"] == len(b"<html>frozen document</html>")
    assert snapshot["content_hash_status"] == "UNDECLARED"
