"""Pre-call budget accounting for models, batches of tools, and forced final answers."""

from __future__ import annotations

from dataclasses import dataclass, field


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class ExecutionBudget:
    max_model_calls: int = 8
    max_tool_calls: int = 8
    max_input_tokens: int = 4096
    max_output_tokens: int = 8192
    max_bytes: int = 65536
    timeout_seconds: int = 120
    _model_calls: int = field(init=False, default=0)
    _tool_calls: int = field(init=False, default=0)
    _input_tokens: int = field(init=False, default=0)
    _output_tokens: int = field(init=False, default=0)
    _bytes: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        if min(
            self.max_model_calls,
            self.max_tool_calls,
            self.max_input_tokens,
            self.max_output_tokens,
            self.max_bytes,
            self.timeout_seconds,
        ) < 0:
            raise ValueError("budget limits must be non-negative")

    def _reserve(self, *, models: int, tools: int, inputs: int, outputs: int, bytes_: int) -> None:
        proposed = (
            self._model_calls + models,
            self._tool_calls + tools,
            self._input_tokens + inputs,
            self._output_tokens + outputs,
            self._bytes + bytes_,
        )
        limits = (self.max_model_calls, self.max_tool_calls, self.max_input_tokens, self.max_output_tokens, self.max_bytes)
        if any(value > limit for value, limit in zip(proposed, limits, strict=True)):
            raise BudgetExceeded("pre-call budget guard rejected the action")
        self._model_calls = proposed[0]
        self._tool_calls = proposed[1]
        self._input_tokens = proposed[2]
        self._output_tokens = proposed[3]
        self._bytes = proposed[4]

    def reserve_model(self, *, input_tokens: int, output_tokens: int, payload_bytes: int) -> None:
        self._reserve(models=1, tools=0, inputs=input_tokens, outputs=output_tokens, bytes_=payload_bytes)

    def reserve_tools(self, *, count: int, payload_bytes: int) -> None:
        self._reserve(models=0, tools=count, inputs=0, outputs=0, bytes_=payload_bytes)

    def reserve_final_answer(self, *, input_tokens: int, output_tokens: int, payload_bytes: int) -> None:
        self.reserve_model(input_tokens=input_tokens, output_tokens=output_tokens, payload_bytes=payload_bytes)

    def snapshot(self) -> dict[str, int]:
        return {"model_calls": self._model_calls, "tool_calls": self._tool_calls, "input_tokens": self._input_tokens, "output_tokens": self._output_tokens, "bytes": self._bytes}
