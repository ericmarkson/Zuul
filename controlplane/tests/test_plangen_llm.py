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


class DiagnosticLoggingTests(unittest.TestCase):
    """Plan generation had zero logging until a real investigation (2026-09-21) hit a wall: a
    phase came back with checks: null, and there was no way to tell "the model deliberately
    judged this sufficient" apart from "a self-correction retry quietly gave up instead of
    fixing the specific problem." `diag_log` is optional (every existing test above passes it as
    None implicitly) and purely observational -- DIAG-1's local-only philosophy, applied here."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.log_path = Path(self._tmp.name) / "diag.log"

    def tearDown(self):
        self._tmp.cleanup()

    def _read_log(self) -> str:
        return self.log_path.read_text(encoding="utf-8") if self.log_path.exists() else ""

    def test_no_diag_log_means_no_file_is_created(self):
        provider = MockModelProvider(responses=[_finalize()])
        plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo)
        self.assertFalse(self.log_path.exists())

    def test_successful_finalize_is_logged_with_its_checks_decision(self):
        from controlplane.eventlog import DiagnosticLog
        diag_log = DiagnosticLog(self.log_path)
        provider = MockModelProvider(responses=[_finalize(checks=None)])
        plangen_llm.propose_phase(provider, "port", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, diag_log=diag_log)
        log = self._read_log()
        self.assertIn("tag=port", log)
        self.assertIn("ACCEPTED: side_effect_class=file-only, checks=null", log)

    def test_a_malformed_finalize_that_self_corrects_logs_both_the_rejection_and_the_final_decision(self):
        """The exact scenario the investigation couldn't distinguish without this: does the log
        show a rejection followed by a *fixed* retry, or a rejection followed by a retreat to
        checks: null? Both are now visible, not just the final plan output."""
        from controlplane.eventlog import DiagnosticLog
        diag_log = DiagnosticLog(self.log_path)
        provider = MockModelProvider(responses=[
            _finalize(side_effect_class="made-up-class"),
            _finalize(checks=None),
        ])
        plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, diag_log=diag_log)
        log = self._read_log()
        self.assertIn("finalize_proposal REJECTED", log)
        self.assertIn("'side_effect_class' must be one of", log)
        self.assertIn("ACCEPTED: side_effect_class=file-only, checks=null", log)

    def test_tool_calls_and_their_results_are_logged(self):
        from controlplane.eventlog import DiagnosticLog
        diag_log = DiagnosticLog(self.log_path)
        (self.repo / "sub").mkdir()
        provider = MockModelProvider(responses=[
            _tool_call("list_directory", {"path": "sub"}),
            _finalize(),
        ])
        plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, diag_log=diag_log)
        log = self._read_log()
        self.assertIn("tool_calls=['list_directory']", log)
        self.assertIn("tool=list_directory", log)

    def test_exhausting_rounds_without_finalize_is_logged(self):
        from controlplane.eventlog import DiagnosticLog
        diag_log = DiagnosticLog(self.log_path)
        provider = MockModelProvider(responses=[_tool_call("grep_repo", {"pattern": "x"})] * 2)
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, max_tool_rounds=2, diag_log=diag_log)
        self.assertIn("FAILED: exhausted 2 round(s)", self._read_log())


SAMPLE_MCP_SERVERS = [{"type": "mcp", "server_label": "docs", "server_url": "https://example.com/mcp", "require_approval": "never"}]


def _mcp_finalize(side_effect_class="file-only", description="migrate config", additional_scope=None, checks=None, call_id="call-1", response_id="resp-1") -> ModelResponse:
    return ModelResponse(
        content="", input_tokens=10, output_tokens=10, latency_seconds=0.01,
        tool_calls=(ToolCall(id=call_id, name="finalize_proposal", arguments={
            "side_effect_class": side_effect_class, "description": description,
            "additional_scope": additional_scope or [], "checks": checks,
        }),),
        response_id=response_id,
    )


def _mcp_tool_call(name: str, arguments: dict, call_id: str = "call-1", response_id: str = "resp-1") -> ModelResponse:
    return ModelResponse(
        content="", input_tokens=10, output_tokens=10, latency_seconds=0.01,
        tool_calls=(ToolCall(id=call_id, name=name, arguments=arguments),), response_id=response_id,
    )


class McpResearchLoopTests(unittest.TestCase):
    """`KNOWLEDGE-1`'s v2 promotion, 2026-09-21: an optional, knowledge-pack-declared remote MCP
    server (e.g. an authoritative docs search) available to the researcher alongside its
    existing local tools, before PLAN-5 freezes scope and checks. Dispatches to a mechanically
    different loop (Responses API's stateful `previous_response_id`, not the local stateless
    growing-message-list shape) but the same validation/self-correction/return-shape guarantees."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_mcp_servers_uses_the_local_loop(self):
        provider = MockModelProvider(responses=[_finalize()])
        plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, mcp_servers=None)
        self.assertEqual(len(provider.tool_calls_log), 1)
        self.assertEqual(provider.mcp_calls_log, [])

    def test_mcp_servers_provided_uses_the_mcp_loop(self):
        provider = MockModelProvider(responses=[_mcp_finalize()])
        plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, mcp_servers=SAMPLE_MCP_SERVERS)
        self.assertEqual(provider.tool_calls_log, [])
        self.assertEqual(len(provider.mcp_calls_log), 1)

    def test_mcp_loop_immediate_finalize_parses(self):
        provider = MockModelProvider(responses=[_mcp_finalize(additional_scope=["appsettings.json"])])
        proposal = plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, mcp_servers=SAMPLE_MCP_SERVERS)
        self.assertEqual(proposal.additional_scope, ["appsettings.json"])

    def test_mcp_servers_are_passed_through_to_the_provider_call(self):
        provider = MockModelProvider(responses=[_mcp_finalize()])
        plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, mcp_servers=SAMPLE_MCP_SERVERS)
        self.assertEqual(provider.mcp_calls_log[0]["mcp_servers"], SAMPLE_MCP_SERVERS)

    def test_system_prompt_addendum_is_included_only_for_the_mcp_loop(self):
        provider = MockModelProvider(responses=[_mcp_finalize()])
        plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, mcp_servers=SAMPLE_MCP_SERVERS)
        system_content = provider.mcp_calls_log[0]["input_items"][0]["content"]
        self.assertIn("authoritative documentation source", system_content)

        provider2 = MockModelProvider(responses=[_finalize()])
        plangen_llm.propose_phase(provider2, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, mcp_servers=None)
        self.assertNotIn("authoritative documentation source", plangen_llm.SYSTEM_PROMPT)

    def test_previous_response_id_threads_across_rounds(self):
        provider = MockModelProvider(responses=[
            _mcp_tool_call("grep_repo", {"pattern": "x"}, response_id="resp-round-1"),
            _mcp_finalize(response_id="resp-round-2"),
        ])
        plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, mcp_servers=SAMPLE_MCP_SERVERS)
        self.assertIsNone(provider.mcp_calls_log[0]["previous_response_id"])
        self.assertEqual(provider.mcp_calls_log[1]["previous_response_id"], "resp-round-1")

    def test_round_2_input_items_hold_only_the_new_tool_output_not_the_whole_history(self):
        """The whole point of the stateful design: unlike the local loop, which resends every
        message every round, only the *new* tool result should be sent -- the rest lives on
        OpenAI's server under previous_response_id."""
        (self.repo / "a.txt").write_text("hello", encoding="utf-8")
        provider = MockModelProvider(responses=[
            _mcp_tool_call("read_file", {"path": "a.txt"}),
            _mcp_finalize(),
        ])
        plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, mcp_servers=SAMPLE_MCP_SERVERS)
        round_2_items = provider.mcp_calls_log[1]["input_items"]
        self.assertEqual(round_2_items, [{"type": "function_call_output", "call_id": "call-1", "output": "hello"}])

    def test_malformed_finalize_self_corrects_within_the_mcp_loop(self):
        provider = MockModelProvider(responses=[
            _mcp_finalize(side_effect_class="made-up-class", response_id="resp-1"),
            _mcp_finalize(response_id="resp-2"),
        ])
        proposal = plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, mcp_servers=SAMPLE_MCP_SERVERS, max_tool_rounds=5)
        self.assertEqual(proposal.side_effect_class, "file-only")
        round_2_items = provider.mcp_calls_log[1]["input_items"]
        self.assertEqual(len(round_2_items), 1)
        self.assertIn("invalid", round_2_items[0]["output"])

    def test_exhausting_rounds_without_finalize_raises(self):
        provider = MockModelProvider(responses=[_mcp_tool_call("grep_repo", {"pattern": "x"})] * 2)
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, mcp_servers=SAMPLE_MCP_SERVERS, max_tool_rounds=2)
        self.assertEqual(len(provider.mcp_calls_log), 2)

    def test_response_with_no_tool_call_raises(self):
        provider = MockModelProvider(responses=[ModelResponse(content="no tool call", input_tokens=5, output_tokens=5, latency_seconds=0.01, response_id="resp-1")])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, mcp_servers=SAMPLE_MCP_SERVERS)

    def test_diag_log_records_mcp_specific_lines(self):
        from controlplane.eventlog import DiagnosticLog
        log_path = Path(self._tmp.name) / "diag.log"
        diag_log = DiagnosticLog(log_path)
        provider = MockModelProvider(responses=[_mcp_finalize()])
        plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET, self.repo, mcp_servers=SAMPLE_MCP_SERVERS, diag_log=diag_log)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn("propose_phase[mcp]", log)
        self.assertIn("starting MCP-enabled research loop", log)
        self.assertIn("servers=['docs']", log)


if __name__ == "__main__":
    unittest.main()
