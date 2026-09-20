"""Hermetic -- MockModelProvider only, zero network."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane.llm_implementer import MalformedResponse, request_edits  # noqa: E402
from controlplane.model_provider import MockModelProvider, ModelResponse  # noqa: E402


def _response(payload: dict | str) -> ModelResponse:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return ModelResponse(content=content, input_tokens=10, output_tokens=10, latency_seconds=0.01)


class LlmImplementerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_well_formed_response_parses_into_proposed_edits(self):
        mock = MockModelProvider(responses=[_response({"edits": [{"path": "a.py", "content": "print(1)"}]})])
        result = request_edits(mock, "do a thing", ["a.py"], self.repo, [["echo", "ok"]], max_output_tokens=100)
        self.assertEqual(len(result.edits), 1)
        self.assertEqual(result.edits[0].path, "a.py")
        self.assertEqual(result.edits[0].content, "print(1)")
        self.assertEqual(result.input_tokens, 10)

    def test_non_json_response_raises_malformed(self):
        mock = MockModelProvider(responses=[_response("not json at all")])
        with self.assertRaises(MalformedResponse):
            request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100)

    def test_json_missing_edits_key_raises_malformed(self):
        mock = MockModelProvider(responses=[_response({"something_else": []})])
        with self.assertRaises(MalformedResponse):
            request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100)

    def test_empty_edits_list_raises_malformed(self):
        mock = MockModelProvider(responses=[_response({"edits": []})])
        with self.assertRaises(MalformedResponse):
            request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100)

    def test_edit_missing_content_field_raises_malformed(self):
        mock = MockModelProvider(responses=[_response({"edits": [{"path": "a.py"}]})])
        with self.assertRaises(MalformedResponse):
            request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100)

    def test_prompt_includes_existing_file_content(self):
        (self.repo / "a.py").write_text("original content", encoding="utf-8")
        mock = MockModelProvider(responses=[_response({"edits": [{"path": "a.py", "content": "new"}]})])
        request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100)
        _system, user_prompt = mock.calls[0]
        self.assertIn("original content", user_prompt)

    def test_prompt_notes_nonexistent_files_as_new(self):
        mock = MockModelProvider(responses=[_response({"edits": [{"path": "new.py", "content": "x"}]})])
        request_edits(mock, "d", ["new.py"], self.repo, [], max_output_tokens=100)
        _system, user_prompt = mock.calls[0]
        self.assertIn("does not exist yet", user_prompt)

    def test_prior_failure_feedback_is_included_on_retry(self):
        mock = MockModelProvider(responses=[_response({"edits": [{"path": "a.py", "content": "x"}]})])
        request_edits(mock, "d", ["a.py"], self.repo, [], max_output_tokens=100, prior_failure_feedback="build failed: syntax error")
        _system, user_prompt = mock.calls[0]
        self.assertIn("build failed: syntax error", user_prompt)


if __name__ == "__main__":
    unittest.main()
