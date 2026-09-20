"""Hermetic -- MockModelProvider only, zero network. Covers the bounded multi-step tool-calling
loop added by the 2026-09-20 pivot (point 2): read-only context tools (read_file,
list_directory) plus the single required finalize_edits call that ends the loop."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane.llm_implementer import MalformedResponse, request_edits  # noqa: E402
from controlplane.model_provider import MockModelProvider, ModelResponse, ToolCall  # noqa: E402


def _finalize(edits, call_id: str = "call-1", in_tok: int = 10, out_tok: int = 10) -> ModelResponse:
    return ModelResponse(
        content="", input_tokens=in_tok, output_tokens=out_tok, latency_seconds=0.01,
        tool_calls=(ToolCall(id=call_id, name="finalize_edits", arguments={"edits": edits}),),
    )


def _tool_call(name: str, arguments: dict, call_id: str = "call-1") -> ModelResponse:
    return ModelResponse(
        content="", input_tokens=10, output_tokens=10, latency_seconds=0.01,
        tool_calls=(ToolCall(id=call_id, name=name, arguments=arguments),),
    )


def _no_tool_call(content: str = "here are the edits in plain text") -> ModelResponse:
    return ModelResponse(content=content, input_tokens=10, output_tokens=10, latency_seconds=0.01)


def _first_user_prompt(mock: MockModelProvider) -> str:
    return mock.tool_calls_log[0][1]["content"]


class LlmImplementerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_immediate_finalize_call_parses_into_proposed_edits(self):
        mock = MockModelProvider(responses=[_finalize([{"path": "a.py", "content": "print(1)"}])])
        result = request_edits(mock, "do a thing", ["a.py"], self.repo, [["echo", "ok"]], max_output_tokens=100)
        self.assertEqual(len(result.edits), 1)
        self.assertEqual(result.edits[0].path, "a.py")
        self.assertEqual(result.edits[0].content, "print(1)")
        self.assertEqual(result.input_tokens, 10)

    def test_response_with_no_tool_call_raises_malformed(self):
        mock = MockModelProvider(responses=[_no_tool_call()])
        with self.assertRaises(MalformedResponse):
            request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100)

    def test_finalize_missing_edits_key_raises_malformed(self):
        mock = MockModelProvider(responses=[_tool_call("finalize_edits", {"something_else": []})])
        with self.assertRaises(MalformedResponse):
            request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100)

    def test_finalize_with_empty_edits_list_raises_malformed(self):
        mock = MockModelProvider(responses=[_finalize([])])
        with self.assertRaises(MalformedResponse):
            request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100)

    def test_edit_missing_content_field_raises_malformed(self):
        mock = MockModelProvider(responses=[_finalize([{"path": "a.py"}])])
        with self.assertRaises(MalformedResponse):
            request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100)

    def test_null_content_parses_as_a_deletion_marker_not_malformed(self):
        """Regression: a real bug found live during Phase F's third run, 2026-09-20 -- the model
        correctly wanted to delete a file a check demanded be absent, submitted content=null, and
        the old code path crashed downstream trying to write None as file content. Null content
        is now an explicit, documented deletion instruction, not an error."""
        mock = MockModelProvider(responses=[_finalize([{"path": "packages.config", "content": None}])])
        result = request_edits(mock, "d", ["packages.config"], self.repo, [], max_output_tokens=100)
        self.assertEqual(result.edits[0].path, "packages.config")
        self.assertIsNone(result.edits[0].content)

    def test_non_string_non_null_content_raises_malformed(self):
        mock = MockModelProvider(responses=[_finalize([{"path": "a.py", "content": 42}])])
        with self.assertRaises(MalformedResponse):
            request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100)

    def test_prompt_includes_existing_file_content(self):
        (self.repo / "a.py").write_text("original content", encoding="utf-8")
        mock = MockModelProvider(responses=[_finalize([{"path": "a.py", "content": "new"}])])
        request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100)
        self.assertIn("original content", _first_user_prompt(mock))

    def test_prompt_notes_nonexistent_files_as_new(self):
        mock = MockModelProvider(responses=[_finalize([{"path": "new.py", "content": "x"}])])
        request_edits(mock, "d", ["new.py"], self.repo, [], max_output_tokens=100)
        self.assertIn("does not exist yet", _first_user_prompt(mock))

    def test_prior_failure_feedback_is_included_on_retry(self):
        mock = MockModelProvider(responses=[_finalize([{"path": "a.py", "content": "x"}])])
        request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100, prior_failure_feedback="build failed: syntax error")
        self.assertIn("build failed: syntax error", _first_user_prompt(mock))

    def test_read_file_tool_call_is_executed_and_fed_back_before_finalize(self):
        (self.repo / "context.txt").write_text("the answer is 42", encoding="utf-8")
        mock = MockModelProvider(responses=[
            _tool_call("read_file", {"path": "context.txt"}),
            _finalize([{"path": "a.py", "content": "print(42)"}]),
        ])
        result = request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100)
        self.assertEqual(result.edits[0].content, "print(42)")
        # the second complete_with_tools call must have seen the tool result in its messages
        second_call_messages = mock.tool_calls_log[1]
        tool_results = [m["content"] for m in second_call_messages if m.get("role") == "tool"]
        self.assertIn("the answer is 42", tool_results)

    def test_list_directory_tool_call_lists_entries(self):
        (self.repo / "sub").mkdir()
        (self.repo / "sub" / "one.py").write_text("", encoding="utf-8")
        mock = MockModelProvider(responses=[
            _tool_call("list_directory", {"path": "sub"}),
            _finalize([{"path": "a.py", "content": "x"}]),
        ])
        request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100)
        tool_results = [m["content"] for m in mock.tool_calls_log[1] if m.get("role") == "tool"]
        self.assertEqual(tool_results, ["one.py"])

    def test_read_file_outside_repo_is_refused_not_raised(self):
        mock = MockModelProvider(responses=[
            _tool_call("read_file", {"path": "../../etc/passwd"}),
            _finalize([{"path": "a.py", "content": "x"}]),
        ])
        request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100)
        tool_results = [m["content"] for m in mock.tool_calls_log[1] if m.get("role") == "tool"]
        self.assertEqual(tool_results, ["error: path is outside the target repository"])

    def test_exceeding_max_tool_rounds_without_finalize_raises_malformed(self):
        mock = MockModelProvider(responses=[_tool_call("read_file", {"path": "a.py"})] * 3)
        with self.assertRaises(MalformedResponse):
            request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100, max_tool_rounds=3)
        self.assertEqual(len(mock.tool_calls_log), 3)


if __name__ == "__main__":
    unittest.main()
