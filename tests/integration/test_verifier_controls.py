from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from code_data_factory.verification.tasks import VerificationInput, verify_result

FIXTURES = Path("tests/fixtures/verification")


def test_seven_control_families_have_at_least_five_independent_cases() -> None:
    cases = json.loads((FIXTURES / "controls.json").read_text(encoding="utf-8"))
    families: dict[str, list[dict[str, object]]] = {}
    for case in cases:
        families.setdefault(str(case["family"]), []).append(case)
    assert set(families) == {
        "correct",
        "wrong_parameter",
        "wrong_dependency",
        "false_success",
        "truncated",
        "environment_failure",
        "unknown",
    }
    assert all(len(group) >= 5 for group in families.values())
    assert len({str(case["case_id"]) for case in cases}) == 35


@pytest.mark.parametrize("case", json.loads((FIXTURES / "controls.json").read_text(encoding="utf-8")))
def test_verifier_controls_match_frozen_expected_classification(case: dict[str, object]) -> None:
    result = verify_result(
        VerificationInput(
            attempt_id=str(case["case_id"]),
            expected=case["expected"],  # type: ignore[arg-type]
            actual=case["actual"],  # type: ignore[arg-type]
            verifier_version="fixed-value-v2",
            forced_status=str(case["forced_status"]),
            verified_at=datetime.now(UTC),
        )
    )
    assert result.outcome == case["outcome"]


def test_two_distinct_valid_paths_pass_the_same_private_verifier() -> None:
    expected = {"value": "100", "unit": "cm", "required_evidence": ["units-length"]}
    direct = {"value": "100", "unit": "cm", "evidence": ["units-length"], "path": "calculation"}
    converted = {"value": "100", "unit": "cm", "evidence": ["units-length"], "path": "conversion"}
    assert verify_result(VerificationInput("a", expected, direct, "v2", "VERIFIED", datetime.now(UTC))).outcome == "PASS"
    assert verify_result(VerificationInput("b", expected, converted, "v2", "VERIFIED", datetime.now(UTC))).outcome == "PASS"
