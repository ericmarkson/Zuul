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
        provider = MockModelProvider(responses=[_finalize(checks=[{"id": "c1", "command": ["{python}", "-c", "import sys; sys.exit(0)"], "supporting_files": []}])])
        proposal = plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)
        self.assertEqual(len(proposal.checks), 1)
        self.assertEqual(proposal.checks[0].id, "c1")
        self.assertEqual(proposal.checks[0].command, ["{python}", "-c", "import sys; sys.exit(0)"])

    def test_finalize_with_supporting_files_parses(self):
        provider = MockModelProvider(responses=[_finalize(checks=[{
            "id": "behavioral-check",
            "command": ["dotnet", "test", "tests/Foo.Tests/Foo.Tests.csproj"],
            "supporting_files": [{"path": "tests/Foo.Tests/FooTests.cs", "content": "// test content"}],
        }])])
        proposal = plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)
        self.assertEqual(proposal.checks[0].command, ["dotnet", "test", "tests/Foo.Tests/Foo.Tests.csproj"])
        self.assertEqual(len(proposal.checks[0].supporting_files), 1)
        self.assertEqual(proposal.checks[0].supporting_files[0].path, "tests/Foo.Tests/FooTests.cs")
        self.assertEqual(proposal.checks[0].supporting_files[0].content, "// test content")

    def test_response_with_no_tool_call_raises(self):
        provider = MockModelProvider(responses=[_no_tool_call()])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)

    def test_invalid_side_effect_class_raises(self):
        provider = MockModelProvider(responses=[_finalize(side_effect_class="made-up-class")])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, max_tool_rounds=1)

    def test_missing_description_raises(self):
        response = ModelResponse(
            content="", input_tokens=10, output_tokens=10, latency_seconds=0.01,
            tool_calls=(ToolCall(id="c1", name="finalize_proposal", arguments={"side_effect_class": "file-only", "additional_scope": [], "checks": None}),),
        )
        provider = MockModelProvider(responses=[response])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, max_tool_rounds=1)

    def test_empty_description_raises(self):
        provider = MockModelProvider(responses=[_finalize(description="   ")])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, max_tool_rounds=1)

    def test_non_list_additional_scope_raises(self):
        provider = MockModelProvider(responses=[_finalize(additional_scope="not-a-list")])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, max_tool_rounds=1)

    def test_check_missing_command_raises(self):
        provider = MockModelProvider(responses=[_finalize(checks=[{"id": "c1"}])])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, max_tool_rounds=1)

    def test_check_command_must_be_a_non_empty_list_of_strings(self):
        provider = MockModelProvider(responses=[_finalize(checks=[{"id": "c1", "command": "not-a-list", "supporting_files": []}])])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, max_tool_rounds=1)

    def test_check_with_syntax_error_raises_malformed(self):
        """Regression for a real bug found live, 2026-09-20: a check script the model wrote had
        an invalid raw string literal (r'..\\..\\packages\\', which can't end in a backslash) --
        it failed identically on every implementer attempt, wasting the whole retry budget on an
        unwinnable check rather than a real content problem."""
        provider = MockModelProvider(responses=[_finalize(checks=[{"id": "c1", "command": ["{python}", "-c", "def broken(:\n    pass"], "supporting_files": []}])])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, max_tool_rounds=1)

    def test_check_with_non_python_command_is_not_syntax_checked(self):
        """A dotnet/npm/etc. command's own correctness is discovered by its real exit code at
        check time -- this project can't and shouldn't try to statically validate arbitrary
        tools' syntax, only the {python} -c <script> shape it can actually compile-check."""
        provider = MockModelProvider(responses=[_finalize(checks=[{
            "id": "behavioral-check", "command": ["dotnet", "test", "this is not valid C# but that's not this check's job"], "supporting_files": [],
        }])])
        proposal = plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, max_tool_rounds=1)
        self.assertEqual(proposal.checks[0].command[0], "dotnet")

    def test_supporting_file_missing_content_raises(self):
        provider = MockModelProvider(responses=[_finalize(checks=[{
            "id": "c1", "command": ["dotnet", "test"], "supporting_files": [{"path": "x.cs"}],
        }])])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, max_tool_rounds=1)

    def test_prompt_includes_finding_details_and_remediation_tag(self):
        provider = MockModelProvider(responses=[_finalize()])
        plangen_llm.propose_phase(provider, "modernize-config", "src/A", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)
        user_prompt = provider.tool_calls_log[0][1]["content"]
        self.assertIn("modernize-config", user_prompt)
        self.assertIn("src/A", user_prompt)
        self.assertIn("FIND-001", user_prompt)
        self.assertIn("legacy config file", user_prompt)

    def test_materialize_check_resolves_the_python_placeholder(self):
        check = plangen_llm.CheckProposal(id="my-check", command=["{python}", "-c", "import sys; sys.exit(1)"], supporting_files=[])
        materialized = plangen_llm.materialize_check(check)
        self.assertEqual(materialized["command"][0], sys.executable)
        self.assertEqual(materialized["result_format"], "junit")
        self.assertIn("my-check", materialized["result_artifact"])

    def test_materialize_check_leaves_a_non_python_command_untouched(self):
        check = plangen_llm.CheckProposal(id="my-check", command=["dotnet", "test", "Foo.Tests.csproj"], supporting_files=[])
        materialized = plangen_llm.materialize_check(check)
        self.assertEqual(materialized["command"], ["dotnet", "test", "Foo.Tests.csproj"])

    def test_materialize_fixtures_flattens_supporting_files_across_checks(self):
        checks = [
            plangen_llm.CheckProposal(id="c1", command=["dotnet", "test"], supporting_files=[
                plangen_llm.SupportingFile(path="tests/A.cs", content="a"),
            ]),
            plangen_llm.CheckProposal(id="c2", command=["dotnet", "test"], supporting_files=[
                plangen_llm.SupportingFile(path="tests/B.cs", content="b"),
            ]),
        ]
        fixtures = plangen_llm.materialize_fixtures(checks)
        self.assertEqual(
            sorted(fixtures, key=lambda f: f["path"]),
            [{"path": "tests/A.cs", "content": "a"}, {"path": "tests/B.cs", "content": "b"}],
        )

    def test_materialize_fixtures_returns_empty_list_when_no_check_has_supporting_files(self):
        checks = [plangen_llm.CheckProposal(id="c1", command=["dotnet", "build"], supporting_files=[])]
        self.assertEqual(plangen_llm.materialize_fixtures(checks), [])


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


class SelfCorrectionTests(unittest.TestCase):
    """A malformed finalize_proposal call (including a check script that doesn't compile) gets
    fed back to the model within the same bounded loop, rather than failing the whole
    generation outright -- the same self-correction shape EXEC-3's retry loop gives the
    implementer, applied to plan generation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_invalid_side_effect_class_gets_a_second_chance_and_succeeds(self):
        provider = MockModelProvider(responses=[
            _finalize(side_effect_class="made-up-class"),
            _finalize(side_effect_class="file-only"),
        ])
        proposal = plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, max_tool_rounds=5)
        self.assertEqual(proposal.side_effect_class, "file-only")
        self.assertEqual(len(provider.tool_calls_log), 2)

    def test_the_error_message_is_fed_back_to_the_model(self):
        provider = MockModelProvider(responses=[
            _finalize(side_effect_class="made-up-class"),
            _finalize(),
        ])
        plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, max_tool_rounds=5)
        second_round_messages = provider.tool_calls_log[1]
        tool_results = [m["content"] for m in second_round_messages if m.get("role") == "tool"]
        self.assertTrue(any("invalid" in r for r in tool_results))

    def test_check_syntax_error_gets_a_second_chance_and_succeeds(self):
        provider = MockModelProvider(responses=[
            _finalize(checks=[{"id": "c1", "command": ["{python}", "-c", "def broken(:\n    pass"], "supporting_files": []}]),
            _finalize(checks=[{"id": "c1", "command": ["{python}", "-c", "import sys; sys.exit(0)"], "supporting_files": []}]),
        ])
        proposal = plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, max_tool_rounds=5)
        self.assertEqual(proposal.checks[0].command, ["{python}", "-c", "import sys; sys.exit(0)"])

    def test_exhausting_rounds_on_repeated_malformed_finalize_still_raises(self):
        provider = MockModelProvider(responses=[_finalize(side_effect_class="made-up-class")] * 2)
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, max_tool_rounds=2)
        self.assertEqual(len(provider.tool_calls_log), 2)


class DefinitionOfDoneGuidanceTests(unittest.TestCase):
    """Anchors the system prompt's guidance against a real failure found live, 2026-09-20: a
    model-authored check that only proves a forbidden pattern is GONE is trivially satisfied by
    deleting the code that used it, not just by porting it. Not a behavioral test (prompt wording
    can't be asserted against model behavior hermetically) -- this exists so a future edit to
    SYSTEM_PROMPT can't silently drop the distinction between a REMOVAL phase (absence is
    correct) and a TRANSFORM phase (presence of surviving content must also be checked) without
    a test noticing."""

    def test_prompt_distinguishes_removal_from_transform_phases(self):
        self.assertIn("REMOVAL", plangen_llm.SYSTEM_PROMPT)
        self.assertIn("TRANSFORM", plangen_llm.SYSTEM_PROMPT)

    def test_prompt_requires_a_positive_survival_check_for_transform_phases(self):
        self.assertIn("MUST include at least one check that positively confirms", plangen_llm.SYSTEM_PROMPT)

    def test_prompt_warns_that_absence_only_checks_are_satisfied_by_deletion(self):
        self.assertIn("deleting the code that used it", plangen_llm.SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
