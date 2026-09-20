"""Hermetic -- MockModelProvider only, zero network. The bounded research-and-propose loop that
authors a phase's side_effect_class/description/additional_scope/checks -- the 2026-09-20 pivot's
replacement for fixed node templates, extended the same day into a research loop with read-only
repo-search tools so scope isn't limited to whatever the static analyzer's findings already knew."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane import plangen_llm  # noqa: E402
from controlplane.model_provider import MockModelProvider, ModelResponse, ToolCall  # noqa: E402

SAMPLE_FINDINGS = [
    {"id": "FIND-001", "category": "config-format", "severity": "medium", "affected_paths": ["Web.config"], "description": "legacy config file", "evidence": {}},
]
SAMPLE_CHECK_SET = [{"id": "build", "command": ["true"], "result_artifact": "x", "result_format": "junit"}]


def _finalize(side_effect_class="file-only", description="migrate config", additional_scope=None, checks=None, call_id="call-1") -> ModelResponse:
    return ModelResponse(
        content="", input_tokens=10, output_tokens=10, latency_seconds=0.01,
        tool_calls=(ToolCall(id=call_id, name="finalize_proposal", arguments={
            "side_effect_class": side_effect_class, "description": description,
            "additional_scope": additional_scope or [], "checks": checks,
        }),),
    )


def _tool_call(name: str, arguments: dict, call_id: str = "call-1") -> ModelResponse:
    return ModelResponse(
        content="", input_tokens=10, output_tokens=10, latency_seconds=0.01,
        tool_calls=(ToolCall(id=call_id, name=name, arguments=arguments),),
    )


def _no_tool_call(content: str = "here is my proposal in plain text") -> ModelResponse:
    return ModelResponse(content=content, input_tokens=10, output_tokens=10, latency_seconds=0.01)


class ProposePhaseTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_immediate_finalize_parses(self):
        provider = MockModelProvider(responses=[_finalize(additional_scope=["appsettings.json"])])
        proposal = plangen_llm.propose_phase(provider, "modernize", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)
        self.assertEqual(proposal.side_effect_class, "file-only")
        self.assertEqual(proposal.description, "migrate config")
        self.assertEqual(proposal.additional_scope, ["appsettings.json"])
        self.assertIsNone(proposal.checks)

    def test_finalize_with_checks_parses_into_check_proposals(self):
        provider = MockModelProvider(responses=[_finalize(checks=[{"id": "c1", "python_script": "import sys; sys.exit(0)"}])])
        proposal = plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)
        self.assertEqual(len(proposal.checks), 1)
        self.assertEqual(proposal.checks[0].id, "c1")

    def test_response_with_no_tool_call_raises(self):
        provider = MockModelProvider(responses=[_no_tool_call()])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)

    def test_invalid_side_effect_class_raises(self):
        provider = MockModelProvider(responses=[_finalize(side_effect_class="made-up-class")])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)

    def test_missing_description_raises(self):
        response = ModelResponse(
            content="", input_tokens=10, output_tokens=10, latency_seconds=0.01,
            tool_calls=(ToolCall(id="c1", name="finalize_proposal", arguments={"side_effect_class": "file-only", "additional_scope": [], "checks": None}),),
        )
        provider = MockModelProvider(responses=[response])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)

    def test_empty_description_raises(self):
        provider = MockModelProvider(responses=[_finalize(description="   ")])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)

    def test_non_list_additional_scope_raises(self):
        provider = MockModelProvider(responses=[_finalize(additional_scope="not-a-list")])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)

    def test_check_missing_python_script_raises(self):
        provider = MockModelProvider(responses=[_finalize(checks=[{"id": "c1"}])])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)

    def test_prompt_includes_finding_details_and_remediation_tag(self):
        provider = MockModelProvider(responses=[_finalize()])
        plangen_llm.propose_phase(provider, "modernize-config", "src/A", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)
        user_prompt = provider.tool_calls_log[0][1]["content"]
        self.assertIn("modernize-config", user_prompt)
        self.assertIn("src/A", user_prompt)
        self.assertIn("FIND-001", user_prompt)
        self.assertIn("legacy config file", user_prompt)

    def test_materialize_check_produces_a_qa2_compliant_command(self):
        check = plangen_llm.CheckProposal(id="my-check", python_script="import sys; sys.exit(1)")
        materialized = plangen_llm.materialize_check(check)
        self.assertEqual(materialized["command"][0], sys.executable)
        self.assertEqual(materialized["result_format"], "junit")
        self.assertIn("my-check", materialized["result_artifact"])


class ResearchLoopTests(unittest.TestCase):
    """The actual point of this pivot: the model can search the real repo across file types the
    audit's static findings never mentioned, before committing to a scope."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        (self.repo / "Views").mkdir()
        (self.repo / "Views" / "Index.cshtml").write_text("@using System.Web.Mvc\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_grep_repo_tool_call_is_executed_and_fed_back_before_finalize(self):
        provider = MockModelProvider(responses=[
            _tool_call("grep_repo", {"pattern": "System.Web.Mvc", "path_glob": "**/*.cshtml"}),
            _finalize(additional_scope=["Views/Index.cshtml"]),
        ])
        proposal = plangen_llm.propose_phase(provider, "incompatible-api", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)
        self.assertIn("Views/Index.cshtml", proposal.additional_scope)
        second_call_messages = provider.tool_calls_log[1]
        tool_results = [m["content"] for m in second_call_messages if m.get("role") == "tool"]
        self.assertTrue(any("Views/Index.cshtml:1:" in r for r in tool_results))

    def test_read_file_and_list_directory_are_also_available(self):
        provider = MockModelProvider(responses=[
            _tool_call("list_directory", {"path": "Views"}),
            _tool_call("read_file", {"path": "Views/Index.cshtml"}),
            _finalize(),
        ])
        plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)
        second_results = [m["content"] for m in provider.tool_calls_log[1] if m.get("role") == "tool"]
        self.assertEqual(second_results, ["Index.cshtml"])
        third_results = [m["content"] for m in provider.tool_calls_log[2] if m.get("role") == "tool"]
        self.assertTrue(any("System.Web.Mvc" in r for r in third_results))

    def test_exceeding_max_tool_rounds_without_finalize_raises(self):
        provider = MockModelProvider(responses=[_tool_call("grep_repo", {"pattern": "x"})] * 3)
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, max_tool_rounds=3)
        self.assertEqual(len(provider.tool_calls_log), 3)


if __name__ == "__main__":
    unittest.main()
