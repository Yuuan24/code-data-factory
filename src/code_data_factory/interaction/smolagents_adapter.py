"""A deliberately thin smolagents entry point, without a replacement agent loop."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .budgets import ExecutionBudget
from .events import EventLedger


def build_tool_calling_agent(
    model: Any,
    tools: list[Any],
    *,
    max_steps: int,
    step_callbacks: list[Callable[[Any], None]],
) -> Any:
    """Construct the upstream ToolCallingAgent with no implicit planning or base tools."""
    from smolagents import ToolCallingAgent  # type: ignore[import-untyped]

    return ToolCallingAgent(
        model=model,
        tools=tools,
        max_steps=max_steps,
        add_base_tools=False,
        planning_interval=None,
        step_callbacks=step_callbacks,
    )


def record_model_boundary(
    ledger: EventLedger,
    budget: ExecutionBudget,
    *,
    actual_visible_input: object,
    invoke: Callable[[], object],
    input_tokens: int,
    maximum_output_tokens: int,
) -> object:
    """Reserve before an actual external request, then persist request and raw output."""
    payload_bytes = len(repr(actual_visible_input).encode("utf-8"))
    budget.reserve_model(
        input_tokens=input_tokens,
        output_tokens=maximum_output_tokens,
        payload_bytes=payload_bytes,
    )
    call_id = ledger.record_model_request(actual_visible_input)
    try:
        output = invoke()
    except Exception as error:
        ledger.record_model_output(call_id, {"error": type(error).__name__, "message": str(error)})
        raise
    ledger.record_model_output(call_id, output)
    return output
