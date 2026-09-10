from __future__ import annotations

from datetime import UTC, datetime

import pytest

from code_data_factory.cli import EXIT_GATE_FAILED, main
from code_data_factory.interaction import environment, network_guard
from code_data_factory.interaction.budgets import BudgetExceeded, ExecutionBudget
from code_data_factory.interaction.events import EventLedger
from code_data_factory.interaction.tools import RestrictedTools, ToolInputError
from code_data_factory.verification.rewards import reward_from_verification
from code_data_factory.verification.tasks import VerificationInput, verify_result


def test_restricted_tools_only_accept_typed_operations_and_known_documents() -> None:
    tools = RestrictedTools(
        {
            "units-length": "A metre contains 100 centimetres.",
            "time-minute": "A minute contains 60 seconds.",
        }
    )
    assert tools.search_documents("metre") == ["units-length"]
    assert tools.read_document("units-length").startswith("A metre")
    assert tools.calculate("MULTIPLY", ["2", "100"]) == "200"
    assert tools.convert("1", "m", "cm") == "100"
    with pytest.raises(ToolInputError):
        tools.calculate("__import__", ["os.system('id')"])
    with pytest.raises(ToolInputError):
        tools.read_document("missing")


def test_budget_counts_batch_tools_and_framework_final_answer_before_execution() -> None:
    budget = ExecutionBudget(max_model_calls=1, max_tool_calls=2, max_input_tokens=10, max_output_tokens=10, max_bytes=20, timeout_seconds=120)
    budget.reserve_model(input_tokens=4, output_tokens=4, payload_bytes=8)
    budget.reserve_tools(count=2, payload_bytes=4)
    with pytest.raises(BudgetExceeded):
        budget.reserve_final_answer(input_tokens=1, output_tokens=1, payload_bytes=1)


def test_event_ledger_pairs_every_model_and_tool_call_and_seals_partial_tail(tmp_path: object) -> None:
    ledger = EventLedger(tmp_path, attempt_id="attempt-1", task_id="task-1")  # type: ignore[arg-type]
    model_call_id = ledger.record_model_request({"messages": ["visible"]})
    ledger.record_model_output(model_call_id, {"text": "call tool"})
    tool_call_id = ledger.record_tool_call("calculate", {"operation": "MULTIPLY"})
    ledger.record_tool_result(tool_call_id, {"value": "200"})
    ledger.record_interruption("runner stopped")
    manifest = ledger.seal("INTERRUPTED")
    assert manifest["end_reason"] == "INTERRUPTED"
    assert [event["event_type"] for event in manifest["events"]] == [
        "MODEL_REQUEST",
        "MODEL_OUTPUT",
        "TOOL_CALL",
        "TOOL_RESULT",
        "INTERRUPTION",
    ]
    assert manifest["events"][-1]["status"] == "INCOMPLETE"
    assert ledger.retry_attempt_id(action_name="calculate") != "attempt-1"
    with pytest.raises(ValueError):
        ledger.retry_attempt_id(action_name="write_document")


@pytest.mark.parametrize(
    ("actual", "status", "outcome"),
    [
        ({"value": "100", "unit": "cm", "evidence": ["units-length"]}, "VERIFIED", "PASS"),
        ({"value": "1", "unit": "m", "evidence": ["units-length"]}, "VERIFIED", "FAIL"),
        ({"value": "100", "unit": "cm", "evidence": []}, "VERIFIED", "FAIL"),
        ({"value": "100", "unit": "cm"}, "INSUFFICIENT", "UNKNOWN"),
    ],
)
def test_verifier_checks_value_constraints_and_evidence_without_exposing_truth(
    actual: dict[str, object], status: str, outcome: str
) -> None:
    result = verify_result(
        VerificationInput(
            attempt_id="attempt-1",
            expected={"value": "100", "unit": "cm", "required_evidence": ["units-length"]},
            actual=actual,
            verifier_version="fixed-value-v2",
            forced_status=status,
            verified_at=datetime.now(UTC),
        )
    )
    assert result.status == status
    assert result.outcome == outcome
    assert "expected" not in result.checks_for_model


def test_terminal_rewards_keep_unknown_null_and_never_overwrite_verification() -> None:
    unknown = reward_from_verification(
        attempt_id="attempt-1",
        verification_id="verify-1",
        verification_status="INSUFFICIENT",
        outcome="UNKNOWN",
        policy_version="reward-terminal-v1",
        created_at=datetime.now(UTC),
    )
    assert unknown["total_reward"] is None
    assert unknown["availability"] == "UNKNOWN"


def test_environment_check_uses_the_command_envelope_and_fails_closed(tmp_path: object, capsys: object) -> None:
    config = tmp_path / "environment.yaml"  # type: ignore[operator]
    config.write_text("container_runtime: platform\nsource_root: .\nnetwork_default: disabled\nlimits: {}\n")
    assert main(["--json", "--config", str(config), "--output-dir", str(tmp_path / "result"), "environment", "check"]) == EXIT_GATE_FAILED  # type: ignore[operator]
    assert '"status": "GATE_FAILED"' in capsys.readouterr().out  # type: ignore[attr-defined]


def test_platform_container_preflight_requires_actual_limits_and_read_only_source(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "environment.yaml"  # type: ignore[operator]
    config.write_text(
        "container_runtime: platform\nsource_root: .\nnetwork_default: disabled\nlimits:\n  cpu_seconds: 120\n  memory_mib: 1024\n  pids: 64\n"
    )
    monkeypatch.setattr(environment.platform, "system", lambda: "Linux")
    monkeypatch.setattr(environment.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(environment, "_platform_container", lambda: True)
    monkeypatch.setattr(environment, "_source_is_read_only", lambda _: True)
    monkeypatch.setattr(environment, "_network_syscalls_blocked", lambda: True)
    monkeypatch.setattr(environment, "_actual_limits", lambda: {"cpu_seconds": 120, "memory_mib": 1024, "pids": 64})
    assert environment.check_environment(config).status == "PASSED"  # type: ignore[arg-type]


def test_network_guard_installs_before_executing_the_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(network_guard, "install", lambda: calls.append("guard"))
    monkeypatch.setattr(network_guard.os, "execv", lambda path, args: calls.append((path, args)))
    network_guard.main(["--", "--json", "environment", "check"])
    assert calls[0] == "guard"
    assert calls[1] == (network_guard.sys.executable, [network_guard.sys.executable, "-m", "code_data_factory.cli", "--json", "environment", "check"])


def test_collect_uses_a_separate_execution_config(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    collection = tmp_path / "collect.yaml"  # type: ignore[operator]
    execution = tmp_path / "execution.yaml"  # type: ignore[operator]
    collection.write_text("facts_config: facts.yaml\n")
    execution.write_text("container_runtime: platform\n")
    observed: list[object] = []
    monkeypatch.setattr("code_data_factory.cli.check_environment", lambda path: observed.append(path) or environment.EnvironmentPreflight("FAILED", {}))
    assert main([
        "--config", str(collection), "--execution-config", str(execution), "--tasks", str(tmp_path / "tasks.json"),
        "--output-dir", str(tmp_path / "output"), "trajectory", "collect",
    ]) == EXIT_GATE_FAILED  # type: ignore[operator]
    assert observed == [execution]  # type: ignore[arg-type]
