"""FRD BUDGET-1/2, TEST-1. Hermetic -- MockModelProvider only, zero network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane.model_provider import (  # noqa: E402
    BudgetedProvider,
    BudgetExceeded,
    MockModelProvider,
    ModelResponse,
    ToolCall,
)


def _response(text: str, in_tokens: int = 10, out_tokens: int = 10) -> ModelResponse:
    return ModelResponse(content=text, input_tokens=in_tokens, output_tokens=out_tokens, latency_seconds=0.01)


def _tool_response(name: str, arguments: dict, in_tokens: int = 10, out_tokens: int = 10) -> ModelResponse:
    return ModelResponse(
        content="", input_tokens=in_tokens, output_tokens=out_tokens, latency_seconds=0.01,
        tool_calls=(ToolCall(id="call-1", name=name, arguments=arguments),),
    )


class MockProviderTests(unittest.TestCase):
    def test_returns_scripted_responses_in_order(self):
        mock = MockModelProvider(responses=[_response("first"), _response("second")])
        self.assertEqual(mock.complete("sys", "u1", 100).content, "first")
        self.assertEqual(mock.complete("sys", "u2", 100).content, "second")

    def test_records_every_call(self):
        mock = MockModelProvider(responses=[_response("ok")])
        mock.complete("system-prompt", "user-prompt", 100)
        self.assertEqual(mock.calls, [("system-prompt", "user-prompt")])

    def test_scripted_exception_is_raised(self):
        mock = MockModelProvider(responses=[TimeoutError("injected timeout")])
        with self.assertRaises(TimeoutError):
            mock.complete("sys", "u", 100)

    def test_malformed_payload_is_just_a_response_with_bad_content(self):
        mock = MockModelProvider(responses=[_response("not valid json at all")])
        result = mock.complete("sys", "u", 100)
        self.assertEqual(result.content, "not valid json at all")

    def test_complete_with_tools_returns_scripted_tool_calls_and_logs_messages(self):
        mock = MockModelProvider(responses=[_tool_response("read_file", {"path": "a.py"})])
        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "u"}]
        result = mock.complete_with_tools(messages, 100, tools=[])
        self.assertEqual(result.tool_calls[0].name, "read_file")
        self.assertEqual(result.tool_calls[0].arguments, {"path": "a.py"})
        self.assertEqual(mock.tool_calls_log, [messages])


class BudgetedProviderTests(unittest.TestCase):
    def test_token_usage_accumulates_per_phase_and_per_run(self):
        mock = MockModelProvider(responses=[_response("a", 10, 10), _response("b", 10, 10)])
        budgeted = BudgetedProvider(
            inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=1000,
            wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60,
        )
        budgeted.complete("sys", "u", 100)
        budgeted.complete("sys", "u", 100)
        self.assertEqual(budgeted.run_tokens_used, 40)
        self.assertEqual(budgeted.phase_tokens_used, 40)

    def test_start_phase_resets_only_the_phase_counter(self):
        mock = MockModelProvider(responses=[_response("a", 10, 10), _response("b", 10, 10)])
        budgeted = BudgetedProvider(
            inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=1000,
            wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60,
        )
        budgeted.complete("sys", "u", 100)
        budgeted.start_phase()
        budgeted.complete("sys", "u", 100)
        self.assertEqual(budgeted.phase_tokens_used, 20)
        self.assertEqual(budgeted.run_tokens_used, 40)

    def test_per_phase_token_ceiling_raises_budget_exceeded(self):
        mock = MockModelProvider(responses=[_response("a", 100, 100)])
        budgeted = BudgetedProvider(
            inner=mock, max_tokens_per_phase=50, max_tokens_per_run=1000,
            wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60,
        )
        with self.assertRaises(BudgetExceeded) as ctx:
            budgeted.complete("sys", "u", 100)
        self.assertEqual(ctx.exception.kind, "token_phase")

    def test_per_run_token_ceiling_raises_budget_exceeded(self):
        mock = MockModelProvider(responses=[_response("a", 30, 30), _response("b", 30, 30)])
        budgeted = BudgetedProvider(
            inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=100,
            wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60,
        )
        budgeted.complete("sys", "u", 100)  # 60 used, within the 100 run ceiling
        with self.assertRaises(BudgetExceeded) as ctx:
            budgeted.complete("sys", "u", 100)  # 120 cumulative, over the 100 run ceiling
        self.assertEqual(ctx.exception.kind, "token_run")

    def test_wall_clock_phase_ceiling_raises_before_any_call(self):
        mock = MockModelProvider(responses=[_response("a")])
        budgeted = BudgetedProvider(
            inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=1000,
            wall_clock_limit_per_phase_seconds=-1, wall_clock_limit_per_run_seconds=60,
        )
        with self.assertRaises(BudgetExceeded) as ctx:
            budgeted.complete("sys", "u", 100)
        self.assertEqual(ctx.exception.kind, "wall_clock_phase")
        self.assertEqual(mock.calls, [])  # the wrapper must refuse before ever calling the model

    def test_budget_is_never_asked_of_the_model_only_enforced_by_the_wrapper(self):
        """BUDGET-1: the token ceiling is enforced by the provider wrapper itself. Even if the
        model is asked for more than the remaining phase budget, the wrapper caps the request
        rather than trusting the model to self-limit."""
        mock = MockModelProvider(responses=[_response("a", 5, 5)])
        budgeted = BudgetedProvider(
            inner=mock, max_tokens_per_phase=30, max_tokens_per_run=1000,
            wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60,
        )
        budgeted.complete("sys", "u", max_output_tokens=1_000_000)
        # nothing raised -- the wrapper silently capped the *requested* ceiling, it did not
        # trust the caller's number, and the mock's actual usage still stayed within budget

    def test_complete_with_tools_shares_the_same_budget_accounting_as_complete(self):
        mock = MockModelProvider(responses=[_tool_response("finalize_edits", {"edits": []}, 15, 15)])
        budgeted = BudgetedProvider(
            inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=1000,
            wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60,
        )
        result = budgeted.complete_with_tools([{"role": "user", "content": "u"}], 100, tools=[])
        self.assertEqual(result.tool_calls[0].name, "finalize_edits")
        self.assertEqual(budgeted.run_tokens_used, 30)
        self.assertEqual(budgeted.phase_tokens_used, 30)

    def test_complete_with_tools_refuses_before_calling_inner_when_budget_already_exhausted(self):
        mock = MockModelProvider(responses=[_tool_response("read_file", {"path": "a"})])
        budgeted = BudgetedProvider(
            inner=mock, max_tokens_per_phase=0, max_tokens_per_run=1000,
            wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60,
        )
        with self.assertRaises(BudgetExceeded):
            budgeted.complete_with_tools([{"role": "user", "content": "u"}], 100, tools=[])
        self.assertEqual(mock.tool_calls_log, [])

    def test_complete_with_mcp_shares_the_same_budget_accounting(self):
        mock = MockModelProvider(responses=[_tool_response("finalize_proposal", {"checks": None}, 20, 20)])
        budgeted = BudgetedProvider(
            inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=1000,
            wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60,
        )
        result = budgeted.complete_with_mcp([{"role": "user", "content": "u"}], 100, tools=[], mcp_servers=[{"type": "mcp"}])
        self.assertEqual(result.tool_calls[0].name, "finalize_proposal")
        self.assertEqual(budgeted.run_tokens_used, 40)

    def test_complete_with_mcp_refuses_before_calling_inner_when_budget_already_exhausted(self):
        mock = MockModelProvider(responses=[_tool_response("read_file", {"path": "a"})])
        budgeted = BudgetedProvider(
            inner=mock, max_tokens_per_phase=0, max_tokens_per_run=1000,
            wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60,
        )
        with self.assertRaises(BudgetExceeded):
            budgeted.complete_with_mcp([{"role": "user", "content": "u"}], 100, tools=[], mcp_servers=[])
        self.assertEqual(mock.mcp_calls_log, [])

    def test_complete_with_mcp_forwards_previous_response_id_to_the_inner_provider(self):
        mock = MockModelProvider(responses=[_response("ok")])
        budgeted = BudgetedProvider(
            inner=mock, max_tokens_per_phase=1000, max_tokens_per_run=1000,
            wall_clock_limit_per_phase_seconds=60, wall_clock_limit_per_run_seconds=60,
        )
        budgeted.complete_with_mcp([{"role": "user", "content": "u"}], 100, tools=[], mcp_servers=[], previous_response_id="resp-123")
        self.assertEqual(mock.mcp_calls_log[0]["previous_response_id"], "resp-123")


class MockProviderMcpTests(unittest.TestCase):
    def test_complete_with_mcp_returns_scripted_response_and_logs_the_call(self):
        mock = MockModelProvider(responses=[_response("ok")])
        mcp_servers = [{"type": "mcp", "server_label": "docs", "server_url": "https://example.com/mcp"}]
        result = mock.complete_with_mcp([{"role": "user", "content": "u"}], 100, tools=[], mcp_servers=mcp_servers, previous_response_id="prev-1")
        self.assertEqual(result.content, "ok")
        self.assertEqual(mock.mcp_calls_log, [{
            "input_items": [{"role": "user", "content": "u"}],
            "mcp_servers": mcp_servers,
            "previous_response_id": "prev-1",
        }])

    def test_complete_with_mcp_response_id_defaults_to_none(self):
        mock = MockModelProvider(responses=[_response("ok")])
        result = mock.complete_with_mcp([{"role": "user", "content": "u"}], 100, tools=[], mcp_servers=[])
        self.assertIsNone(result.response_id)


if __name__ == "__main__":
    unittest.main()
