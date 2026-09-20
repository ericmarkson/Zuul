"""Model provider abstraction -- FRD PROVIDER-1 (config-driven backend selection, one interface),
BUDGET-1/2 (hard per-phase and per-run ceilings enforced by the wrapper itself, never relied
upon from the model's own behavior), TEST-1 (a deterministic mock provider, so the whole cycle
is testable without tokens). The orchestration core never imports the concrete OpenAI SDK
directly outside this module -- runner.py only ever sees the ModelProvider protocol."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol


class BudgetExceeded(RuntimeError):
    def __init__(self, kind: str, limit: float, actual: float):
        self.kind = kind
        self.limit = limit
        self.actual = actual
        super().__init__(f"{kind} budget exceeded: {actual} > {limit}")


@dataclass(frozen=True)
class ModelResponse:
    content: str
    input_tokens: int
    output_tokens: int
    latency_seconds: float


class ModelProvider(Protocol):
    def complete(self, system_prompt: str, user_prompt: str, max_output_tokens: int) -> ModelResponse: ...


@dataclass
class MockModelProvider:
    """TEST-1: deterministic, scripted responses, zero network. Each entry in `responses` is
    either a ModelResponse to return or an Exception instance to raise -- malformed/truncated
    payloads are just ModelResponses with unparseable content, and injected timeouts are just
    scripted TimeoutError instances, rather than special-cased branches in this class."""

    responses: list[ModelResponse | Exception] = field(default_factory=list)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, system_prompt: str, user_prompt: str, max_output_tokens: int) -> ModelResponse:
        self.calls.append((system_prompt, user_prompt))
        if not self.responses:
            raise RuntimeError("MockModelProvider: no more scripted responses")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@dataclass
class OpenAIProvider:
    """The only module in this project that imports the `openai` SDK."""

    api_key: str
    model: str
    reasoning_effort: str = "low"

    def __post_init__(self) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=self.api_key)

    def complete(self, system_prompt: str, user_prompt: str, max_output_tokens: int) -> ModelResponse:
        start = time.monotonic()
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_completion_tokens=max_output_tokens,
            reasoning_effort=self.reasoning_effort,
            response_format={"type": "json_object"},
        )
        latency = time.monotonic() - start
        content = response.choices[0].message.content or ""
        usage = response.usage
        return ModelResponse(
            content=content,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_seconds=latency,
        )


# Published pricing for gpt-5.6-sol as of 2026-09-20 (promotional rate through 2026-11-21):
# https://developers.openai.com/api/docs/models/gpt-5.6-sol
GPT_5_6_SOL_INPUT_PER_MILLION_USD = 4.0
GPT_5_6_SOL_OUTPUT_PER_MILLION_USD = 20.0


def estimate_cost_usd(input_tokens: int, output_tokens: int, input_per_million: float = GPT_5_6_SOL_INPUT_PER_MILLION_USD, output_per_million: float = GPT_5_6_SOL_OUTPUT_PER_MILLION_USD) -> float:
    return (input_tokens / 1_000_000) * input_per_million + (output_tokens / 1_000_000) * output_per_million


@dataclass
class BudgetedProvider:
    """BUDGET-1/2, wrapping any ModelProvider. Tracks tokens and wall-clock time both per-phase
    (reset via start_phase()) and per-run (from construction), and raises BudgetExceeded --
    never silently truncates or continues -- the instant either ceiling is crossed."""

    inner: ModelProvider
    max_tokens_per_phase: int
    max_tokens_per_run: int
    wall_clock_limit_per_phase_seconds: float
    wall_clock_limit_per_run_seconds: float

    def __post_init__(self) -> None:
        self._run_start = time.monotonic()
        self._phase_start = self._run_start
        self._run_tokens = 0
        self._phase_tokens = 0
        self._run_input_tokens = 0
        self._run_output_tokens = 0

    def start_phase(self) -> None:
        self._phase_start = time.monotonic()
        self._phase_tokens = 0

    @property
    def run_tokens_used(self) -> int:
        return self._run_tokens

    @property
    def phase_tokens_used(self) -> int:
        return self._phase_tokens

    @property
    def run_input_tokens(self) -> int:
        return self._run_input_tokens

    @property
    def run_output_tokens(self) -> int:
        return self._run_output_tokens

    def complete(self, system_prompt: str, user_prompt: str, max_output_tokens: int) -> ModelResponse:
        now = time.monotonic()
        run_elapsed = now - self._run_start
        if run_elapsed > self.wall_clock_limit_per_run_seconds:
            raise BudgetExceeded("wall_clock_run", self.wall_clock_limit_per_run_seconds, run_elapsed)
        phase_elapsed = now - self._phase_start
        if phase_elapsed > self.wall_clock_limit_per_phase_seconds:
            raise BudgetExceeded("wall_clock_phase", self.wall_clock_limit_per_phase_seconds, phase_elapsed)

        capped_max_output = min(max_output_tokens, self.max_tokens_per_phase - self._phase_tokens)
        if capped_max_output <= 0:
            raise BudgetExceeded("token_phase", self.max_tokens_per_phase, self._phase_tokens)

        response = self.inner.complete(system_prompt, user_prompt, capped_max_output)

        used = response.input_tokens + response.output_tokens
        self._run_tokens += used
        self._phase_tokens += used
        self._run_input_tokens += response.input_tokens
        self._run_output_tokens += response.output_tokens

        if self._phase_tokens > self.max_tokens_per_phase:
            raise BudgetExceeded("token_phase", self.max_tokens_per_phase, self._phase_tokens)
        if self._run_tokens > self.max_tokens_per_run:
            raise BudgetExceeded("token_run", self.max_tokens_per_run, self._run_tokens)

        return response
