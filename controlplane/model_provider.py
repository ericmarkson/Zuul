"""Model provider abstraction -- FRD PROVIDER-1 (config-driven backend selection, one interface),
BUDGET-1/2 (hard per-phase and per-run ceilings enforced by the wrapper itself, never relied
upon from the model's own behavior), TEST-1 (a deterministic mock provider, so the whole cycle
is testable without tokens). The orchestration core never imports the concrete OpenAI SDK
directly outside this module -- runner.py only ever sees the ModelProvider protocol."""

from __future__ import annotations

import json
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
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ModelResponse:
    content: str
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    # Populated only by complete_with_tools -- the bounded multi-step agentic implementer
    # (2026-09-20 pivot, point 2). Empty for every plain complete() response.
    tool_calls: tuple[ToolCall, ...] = ()
    # Populated only by complete_with_mcp (2026-09-21, KNOWLEDGE-1's v2 promotion trigger) --
    # the Responses API's own conversation-state marker. Remote MCP tool calls (e.g. a docs
    # search) are executed entirely server-side by OpenAI against the declared MCP server, never
    # by this project's own code; passing this id back on the next call is what lets the model
    # keep that context without us having to re-transmit or even see the MCP call's contents.
    response_id: str | None = None


class ModelProvider(Protocol):
    def complete(self, system_prompt: str, user_prompt: str, max_output_tokens: int) -> ModelResponse: ...

    def complete_with_tools(self, messages: list[dict], max_output_tokens: int, tools: list[dict]) -> ModelResponse: ...

    def complete_with_mcp(
        self,
        input_items: list[dict],
        max_output_tokens: int,
        tools: list[dict],
        mcp_servers: list[dict],
        previous_response_id: str | None = None,
    ) -> ModelResponse: ...


@dataclass
class MockModelProvider:
    """TEST-1: deterministic, scripted responses, zero network. Each entry in `responses` is
    either a ModelResponse to return or an Exception instance to raise -- malformed/truncated
    payloads are just ModelResponses with unparseable content, and injected timeouts are just
    scripted TimeoutError instances, rather than special-cased branches in this class."""

    responses: list[ModelResponse | Exception] = field(default_factory=list)
    calls: list[tuple[str, str]] = field(default_factory=list)
    tool_calls_log: list[list[dict]] = field(default_factory=list)
    mcp_calls_log: list[dict] = field(default_factory=list)

    def _next(self) -> ModelResponse:
        if not self.responses:
            raise RuntimeError("MockModelProvider: no more scripted responses")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def complete(self, system_prompt: str, user_prompt: str, max_output_tokens: int) -> ModelResponse:
        self.calls.append((system_prompt, user_prompt))
        return self._next()

    def complete_with_tools(self, messages: list[dict], max_output_tokens: int, tools: list[dict]) -> ModelResponse:
        # A snapshot, not the live list -- callers keep mutating (appending to) `messages` after
        # this call returns, and a stored reference to the same list object would silently make
        # every earlier log entry retroactively show the FINAL round's state too. Found live by
        # a stricter equality assertion in test_plangen_llm.py; prior tests only ever used
        # assertIn against these logs, which happens to pass either way and never caught it.
        self.tool_calls_log.append(list(messages))
        return self._next()

    def complete_with_mcp(
        self,
        input_items: list[dict],
        max_output_tokens: int,
        tools: list[dict],
        mcp_servers: list[dict],
        previous_response_id: str | None = None,
    ) -> ModelResponse:
        self.mcp_calls_log.append({
            "input_items": list(input_items), "mcp_servers": mcp_servers,
            "previous_response_id": previous_response_id,
        })
        return self._next()


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

    def complete_with_tools(self, messages: list[dict], max_output_tokens: int, tools: list[dict]) -> ModelResponse:
        """Translates this project's generic message/tool-call shape to and from the OpenAI SDK's
        own schema -- this stays the only module that speaks that schema, per this class's own
        docstring. An assistant message may carry `tool_calls` (our ToolCall shape); a tool
        result message carries `tool_call_id` + `content`, same as the OpenAI wire format."""
        start = time.monotonic()
        openai_messages = []
        for m in messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                openai_messages.append({
                    "role": "assistant",
                    "content": m.get("content") or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])},
                        }
                        for tc in m["tool_calls"]
                    ],
                })
            else:
                openai_messages.append(m)

        response = self._client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            max_completion_tokens=max_output_tokens,
            # gpt-5.6-sol's chat.completions endpoint rejects function tools combined with any
            # non-"none" reasoning_effort ("use /v1/responses or set reasoning_effort to 'none'")
            # -- found live, 2026-09-20, the first time this path was actually exercised against
            # the real API. self.reasoning_effort still governs the plain complete() path.
            reasoning_effort="none",
            tools=tools,
            tool_choice="auto",
        )
        latency = time.monotonic() - start
        message = response.choices[0].message
        tool_calls = tuple(
            ToolCall(id=tc.id, name=tc.function.name, arguments=json.loads(tc.function.arguments or "{}"))
            for tc in (message.tool_calls or [])
        )
        usage = response.usage
        return ModelResponse(
            content=message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_seconds=latency,
            tool_calls=tool_calls,
        )

    @staticmethod
    def _to_responses_api_tool_shape(tools: list[dict]) -> list[dict]:
        """The Responses API's function-tool declaration is flat (`{"type", "name", ...}`) --
        Chat Completions nests the same fields under a `"function"` key. This project's own
        TOOLS lists (llm_implementer.py, plangen_llm.py) are written once, in the Chat
        Completions shape, since that is still the primary path; this re-shapes them for the one
        method that needs the Responses API instead of introducing a second copy to maintain."""
        reshaped = []
        for t in tools:
            if t.get("type") == "function" and "function" in t:
                fn = t["function"]
                reshaped.append({"type": "function", "name": fn["name"], "description": fn.get("description", ""), "parameters": fn.get("parameters", {})})
            else:
                reshaped.append(t)
        return reshaped

    def complete_with_mcp(
        self,
        input_items: list[dict],
        max_output_tokens: int,
        tools: list[dict],
        mcp_servers: list[dict],
        previous_response_id: str | None = None,
    ) -> ModelResponse:
        """The Responses API is the only place OpenAI's native remote-MCP tool support lives
        (2026-09-21, `KNOWLEDGE-1`'s v2 promotion trigger). A remote MCP tool call (e.g. a real
        docs search against a knowledge-pack-declared server) is executed entirely server-side --
        this project's own code never sees its contents, never dispatches it, and never needs to
        translate it -- only `previous_response_id` needs to flow forward so the model keeps that
        context on the next call, same as the growing `messages` list does for the local-only
        `complete_with_tools` path. `input_items` on every call after the first should therefore
        only be the *new* items since the last call (typically this project's own local tool
        results) -- the rest of the conversation, including any MCP call, is already on OpenAI's
        server under `previous_response_id`."""
        start = time.monotonic()
        response = self._client.responses.create(
            model=self.model,
            input=input_items,
            previous_response_id=previous_response_id,
            max_output_tokens=max_output_tokens,
            # Mirrors complete_with_tools' finding: function tools plus a non-"none"
            # reasoning_effort were rejected on the chat-completions endpoint for this model;
            # applied here defensively pending live confirmation against the Responses API.
            reasoning_effort="none",
            tools=[*self._to_responses_api_tool_shape(tools), *mcp_servers],
            tool_choice="auto",
        )
        latency = time.monotonic() - start

        tool_calls = tuple(
            ToolCall(id=item.call_id, name=item.name, arguments=json.loads(item.arguments or "{}"))
            for item in response.output
            if item.type == "function_call"
        )
        content = "\n".join(
            part.text
            for item in response.output
            if item.type == "message"
            for part in item.content
            if part.type == "output_text"
        )
        usage = response.usage
        return ModelResponse(
            content=content,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            latency_seconds=latency,
            tool_calls=tool_calls,
            response_id=response.id,
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

    def _pre_call_cap(self, max_output_tokens: int) -> int:
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
        return capped_max_output

    def _record_usage(self, response: ModelResponse) -> None:
        used = response.input_tokens + response.output_tokens
        self._run_tokens += used
        self._phase_tokens += used
        self._run_input_tokens += response.input_tokens
        self._run_output_tokens += response.output_tokens

        if self._phase_tokens > self.max_tokens_per_phase:
            raise BudgetExceeded("token_phase", self.max_tokens_per_phase, self._phase_tokens)
        if self._run_tokens > self.max_tokens_per_run:
            raise BudgetExceeded("token_run", self.max_tokens_per_run, self._run_tokens)

    def complete(self, system_prompt: str, user_prompt: str, max_output_tokens: int) -> ModelResponse:
        capped_max_output = self._pre_call_cap(max_output_tokens)
        response = self.inner.complete(system_prompt, user_prompt, capped_max_output)
        self._record_usage(response)
        return response

    def complete_with_tools(self, messages: list[dict], max_output_tokens: int, tools: list[dict]) -> ModelResponse:
        capped_max_output = self._pre_call_cap(max_output_tokens)
        response = self.inner.complete_with_tools(messages, capped_max_output, tools)
        self._record_usage(response)
        return response

    def complete_with_mcp(
        self,
        input_items: list[dict],
        max_output_tokens: int,
        tools: list[dict],
        mcp_servers: list[dict],
        previous_response_id: str | None = None,
    ) -> ModelResponse:
        capped_max_output = self._pre_call_cap(max_output_tokens)
        response = self.inner.complete_with_mcp(input_items, capped_max_output, tools, mcp_servers, previous_response_id)
        self._record_usage(response)
        return response
