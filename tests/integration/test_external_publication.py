from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_data_factory.datasets.build import build_draft
from code_data_factory.datasets.build_input import load_build_input
from code_data_factory.datasets.publish import PublicationGateError, publish_dataset


def _member(**overrides: object) -> dict[str, object]:
    member: dict[str, object] = {
        "demonstration_id": "toucan:example-1",
        "source_record_id": "toucan:example-1",
        "source_record_ids": ["toucan:example-1"],
        "usage_scope": "TRAIN",
        "eligibility_decision_id": "eligibility-1",
        "eligibility_action": "ACCEPT",
        "upstream_message_refs": ["message-0", "message-1"],
        "source_origin": "PUBLIC_ORIGINAL",
        "replay_capability": "UNSUPPORTED",
        "review_checks": [
            "source_identity",
            "upstream_tool_definition",
            "message_context",
            "target_answer_mapping",
            "split_registration",
            "sensitive_review",
        ],
    }
    member.update(overrides)
    return member


def test_external_training_release_uses_admission_not_execution_and_keeps_lineage(tmp_path: Path) -> None:
    publication = publish_dataset(
        dataset_id="external-fixture-v1",
        members=[_member()],
        output_dir=tmp_path / "releases",
        input_manifest_hash="a" * 64,
        rule_version="external-sft-v1",
    )

    lineage = json.loads(
        publication.path.joinpath("lineage_index.json").read_text(encoding="utf-8")
    )
    assert lineage["external_demonstrations"] == [
        {
            "demonstration_id": "toucan:example-1",
            "eligibility_decision_id": "eligibility-1",
            "parent_demonstration_id": None,
            "source_record_id": "toucan:example-1",
            "upstream_message_refs": ["message-0", "message-1"],
        }
    ]
    manifest = json.loads(
        publication.path.joinpath("dataset_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["member_kind"] == "EXTERNAL_DEMONSTRATION"
    assert "environment" not in manifest
    assert "model_generation" not in manifest


@pytest.mark.parametrize(
    "member",
    [
        _member(source_origin="PROJECT_SAMPLING"),
        _member(source_origin="MODEL_GENERATION"),
        _member(eligibility_action="REJECT"),
        _member(upstream_message_refs=[]),
    ],
)
def test_external_training_release_rejects_project_generation_or_missing_admission_evidence(
    tmp_path: Path, member: dict[str, object]
) -> None:
    with pytest.raises(PublicationGateError):
        publish_dataset(
            dataset_id="external-fixture-v1",
            members=[member],
            output_dir=tmp_path / "releases",
            input_manifest_hash="a" * 64,
            rule_version="external-sft-v1",
        )


def test_external_build_reads_only_frozen_demonstrations_and_eligibility_records(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.json"
    demonstrations = tmp_path / "demonstrations.json"
    materials = tmp_path / "materials.json"
    eligibility = tmp_path / "eligibility.json"
    split = tmp_path / "split.json"
    manifest = tmp_path / "input.json"
    source.write_text('{"source_records":[{"source_record_id":"source-1"}]}', encoding="utf-8")
    demonstrations.write_text(
        json.dumps(
            {
                "external_demonstrations": [
                    {
                        "demonstration_id": "demo-1",
                        "source_record_id": "source-1",
                        "message_refs": [{"uri": "messages/demo-1.json"}],
                        "source_origin": "PUBLIC_ORIGINAL",
                        "replay_capability": "UNSUPPORTED",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    eligibility.write_text(
        json.dumps(
            {
                "eligibility_decisions": [
                    {
                        "decision_id": "eligibility-demo-1",
                        "demonstration_id": "demo-1",
                        "action": "ACCEPT",
                        "review_checks": [
                            "source_identity",
                            "upstream_tool_definition",
                            "message_context",
                            "target_answer_mapping",
                            "split_registration",
                            "sensitive_review",
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    materials.write_text(
        json.dumps(
            {
                "external_material": [
                    {
                        "demonstration_id": "demo-1",
                        "messages": [
                            {"role": "user", "content": "question"},
                            {"role": "assistant", "content": "answer"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    split.write_text('{"policy":"external-split-v1"}', encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "source_manifests": ["source.json"],
                "external_demonstration_manifests": ["demonstrations.json"],
                "external_material_manifests": ["materials.json"],
                "eligibility_manifests": ["eligibility.json"],
                "split_registry_ref": "split.json",
                "rule_version": "external-sft-v1",
            }
        ),
        encoding="utf-8",
    )

    result = build_draft(
        build_input=load_build_input(manifest),
        output_dir=tmp_path / "candidate",
        backend="local",
        run_id="external-build-1",
    )

    assert result.member_count == 1
    candidate_manifest = json.loads((tmp_path / "candidate" / "manifest.json").read_text(encoding="utf-8"))
    assert candidate_manifest["status"] == "CANDIDATE"
    assert candidate_manifest["counts"] == {
        "accepted": 1,
        "accepted_repaired": 0,
        "frozen_material": 1,
        "model_generation_ingress": 0,
        "pending_review": 0,
        "project_sampling_ingress": 0,
        "project_task_ingress": 0,
        "quarantined": 0,
        "raw_external_demonstrations": 1,
        "rejected": 0,
        "repaired": 0,
    }
    members = json.loads((tmp_path / "candidate" / "membership.json").read_text(encoding="utf-8"))
    assert members == [
        {
            "demonstration_id": "demo-1",
            "eligibility_action": "ACCEPT",
            "eligibility_decision_id": "eligibility-demo-1",
            "messages": [
                {"content": "question", "role": "user"},
                {"content": "answer", "role": "assistant"},
            ],
            "parent_demonstration_id": None,
            "replay_capability": "UNSUPPORTED",
            "review_checks": [
                "message_context",
                "sensitive_review",
                "source_identity",
                "split_registration",
                "target_answer_mapping",
                "upstream_tool_definition",
            ],
            "source_origin": "PUBLIC_ORIGINAL",
            "source_record_id": "source-1",
            "source_record_ids": ["source-1"],
            "upstream_message_refs": ["messages/demo-1.json"],
            "usage_scope": "TRAIN",
        }
    ]
