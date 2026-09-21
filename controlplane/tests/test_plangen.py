"""FRD PLAN-1 path (a) / PLAN-2 v1 scope: findings group into phases by remediation tag plus
declared-path overlap, purely lexically -- unchanged by the 2026-09-20 pivot. What changed is
covered here too: each group's side_effect_class/description/additional_scope/checks now comes
from one `plangen_llm.propose_phase` model call instead of a fixed node-template lookup.
Hermetic -- MockModelProvider only, zero network, no real pack or repo involved."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane import plangen  # noqa: E402
from controlplane.model_provider import MockModelProvider, ModelResponse, ToolCall  # noqa: E402

SAMPLE_CHECK_SET = [{"id": "build", "command": ["true"], "result_artifact": "nonexistent.xml", "result_format": "junit"}]


def _proposal_response(side_effect_class: str, description: str = "do the remediation", additional_scope=None, checks=None) -> ModelResponse:
    return ModelResponse(
        content="", input_tokens=10, output_tokens=10, latency_seconds=0.01,
        tool_calls=(ToolCall(id="call-1", name="finalize_proposal", arguments={
            "side_effect_class": side_effect_class, "description": description,
            "additional_scope": additional_scope or [], "checks": checks,
        }),),
    )


def _doc(findings: list[dict]) -> dict:
    return {
        "generated_at": "2026-09-21T00:00:00Z",
        "pack": "test-pack",
        "pack_content_hash": "deadbeef" * 8,
        "target_repo": "/fake/repo",
        "findings": findings,
    }


class PlanGenTests(unittest.TestCase):
    def test_findings_with_no_remediation_tag_are_dropped_not_silently(self):
        doc = _doc([
            {"id": "FIND-001", "category": "x", "affected_paths": ["a.csproj"], "description": "d", "remediation_tag": None},
        ])
        provider = MockModelProvider(responses=[])
        phases, dropped = plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)
        self.assertEqual(phases, [])
        self.assertEqual(dropped, ["FIND-001"])

    def test_findings_sharing_tag_and_project_are_grouped_into_one_phase(self):
        doc = _doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "fix-a"},
            {"id": "FIND-002", "category": "target-framework", "affected_paths": ["src/A/A.csproj"], "description": "d2", "remediation_tag": "fix-a"},
        ])
        provider = MockModelProvider(responses=[_proposal_response("file-only")])
        phases, dropped = plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)
        self.assertEqual(len(phases), 1)
        self.assertEqual(dropped, [])
        self.assertEqual(phases[0]["side_effect_class"], "file-only")
        self.assertIn("src/A/A.csproj", phases[0]["declared_scope"])
        self.assertEqual(len(provider.tool_calls_log), 1)  # one model call per group, not per finding

    def test_same_tag_different_projects_produce_separate_phases_and_separate_calls(self):
        doc = _doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "fix-a"},
            {"id": "FIND-002", "category": "project-format", "affected_paths": ["src/B/B.csproj"], "description": "d2", "remediation_tag": "fix-a"},
        ])
        provider = MockModelProvider(responses=[_proposal_response("file-only"), _proposal_response("file-only")])
        phases, _ = plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)
        self.assertEqual(len(phases), 2)
        scopes = [set(p["declared_scope"]) for p in phases]
        self.assertIn({"src/A/A.csproj"}, scopes)
        self.assertIn({"src/B/B.csproj"}, scopes)
        self.assertEqual(len(provider.tool_calls_log), 2)

    def test_different_tags_produce_separate_phases_even_in_same_project(self):
        doc = _doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "fix-a"},
            {"id": "FIND-002", "category": "package-management", "affected_paths": ["src/A/A.csproj", "src/A/packages.config"], "description": "d2", "remediation_tag": "fix-b"},
        ])
        provider = MockModelProvider(responses=[_proposal_response("file-only"), _proposal_response("package-manager-mutating")])
        phases, _ = plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)
        self.assertEqual(len(phases), 2)
        tags = {p["id"].rsplit("-", 1)[-1] for p in phases}
        self.assertEqual(tags, {"a", "b"})
        side_effect_classes = {p["side_effect_class"] for p in phases}
        self.assertEqual(side_effect_classes, {"file-only", "package-manager-mutating"})

    def test_every_generated_phase_has_all_plan5_fields(self):
        doc = _doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "fix-a"},
        ])
        provider = MockModelProvider(responses=[_proposal_response("file-only")])
        phases, _ = plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)
        for phase in phases:
            for key in ("id", "description", "declared_scope", "side_effect_class", "edits", "checks"):
                self.assertIn(key, phase)
            self.assertEqual(phase["edits"], [])
            self.assertIsNone(phase["checks"])  # model proposed no checks -> use plan default

    def test_malformed_side_effect_class_raises_rather_than_silently_accepting(self):
        doc = _doc([
            {"id": "FIND-001", "category": "x", "affected_paths": ["a.csproj"], "description": "d", "remediation_tag": "fix-a"},
        ])
        provider = MockModelProvider(responses=[_proposal_response("not-a-real-class")])
        with self.assertRaises(Exception):
            plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)

    def test_config_format_finding_attaches_to_nearest_project_by_path_prefix(self):
        doc = _doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "fix-a"},
            {"id": "FIND-002", "category": "config-format", "affected_paths": ["src/A/Web.config"], "description": "d2", "remediation_tag": "fix-a"},
        ])
        provider = MockModelProvider(responses=[_proposal_response("file-only")])
        phases, _ = plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)
        self.assertEqual(len(phases), 1)  # same component (src/A) + same tag -> merged
        self.assertEqual(set(phases[0]["declared_scope"]), {"src/A/A.csproj", "src/A/Web.config"})

    def test_generate_plan_produces_a_plan_a_loadable_shape(self):
        """The whole point: this must be loadable by Phase A's plan.py without any changes to
        it. Exercise the actual loader, not just a structural assertion."""
        doc = _doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "fix-a"},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            findings_path = Path(tmp) / "findings.json"
            findings_path.write_text(json.dumps(doc), encoding="utf-8")

            provider = MockModelProvider(responses=[_proposal_response("file-only")])
            plan_dict = plangen.generate_plan(
                findings_path=findings_path,
                model_provider=provider,
                check_set=SAMPLE_CHECK_SET,
                run_id_prefix="test-gen",
            )
            plan_path = Path(tmp) / "plan.json"
            plangen.write_plan_file(plan_path, plan_dict)

            from controlplane.plan import load_plan
            loaded = load_plan(plan_path)
            self.assertEqual(loaded.run_id_prefix, "test-gen")
            self.assertEqual(len(loaded.phases), 1)
            self.assertEqual(loaded.phases[0].side_effect_class, "file-only")


class ModelAuthoredChecksTests(unittest.TestCase):
    """The Phase F fix, generalized: a proposal that declares a check gets that check wired in
    and actually enforced -- no longer a template's `expected_new_paths`, now the model's own
    Python script, still QA-2-compliant (subprocess exit code governs, nothing else)."""

    def test_proposed_additional_scope_is_added_to_declared_scope(self):
        doc = _doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "modernize"},
            {"id": "FIND-002", "category": "config-format", "affected_paths": ["src/A/Web.config"], "description": "d2", "remediation_tag": "modernize"},
        ])
        provider = MockModelProvider(responses=[_proposal_response("file-only", additional_scope=["src/A/appsettings.json"])])
        phases, _ = plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)
        self.assertEqual(len(phases), 1)
        self.assertIn("src/A/appsettings.json", phases[0]["declared_scope"])

    def test_proposed_check_is_added_on_top_of_plan_defaults(self):
        script = "import pathlib, sys\nsys.exit(0 if pathlib.Path('src/A/appsettings.json').is_file() else 1)\n"
        doc = _doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "modernize"},
        ])
        provider = MockModelProvider(responses=[_proposal_response(
            "file-only", checks=[{"id": "modernize-produced-output", "command": ["{python}", "-c", script], "supporting_files": []}],
        )])
        phases, _ = plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)
        checks = phases[0]["checks"]
        self.assertIsNotNone(checks)
        check_ids = {c["id"] for c in checks}
        self.assertIn("build", check_ids)  # the plan default is still there, not replaced
        self.assertIn("modernize-produced-output", check_ids)

    def test_proposed_check_actually_fails_when_its_own_condition_is_unmet(self):
        """Not just present in the plan -- actually run it and confirm exit code governs."""
        script = "import pathlib, sys\nsys.exit(0 if pathlib.Path('appsettings.json').is_file() else 1)\n"
        doc = _doc([
            {"id": "FIND-001", "category": "config-format", "affected_paths": ["Web.config"], "description": "d1", "remediation_tag": "modernize"},
        ])
        provider = MockModelProvider(responses=[_proposal_response(
            "file-only", checks=[{"id": "modernize-produced-output", "command": ["{python}", "-c", script], "supporting_files": []}],
        )])
        phases, _ = plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)
        check = next(c for c in phases[0]["checks"] if c["id"] == "modernize-produced-output")

        with tempfile.TemporaryDirectory() as run_repo:
            import subprocess
            command = [part.format(run_dir="unused", phase_id="phase-1") for part in check["command"]]
            result = subprocess.run(command, cwd=run_repo, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)  # appsettings.json was never created

    def test_proposed_check_passes_when_its_own_condition_is_met(self):
        script = "import pathlib, sys\nsys.exit(0 if pathlib.Path('appsettings.json').is_file() else 1)\n"
        doc = _doc([
            {"id": "FIND-001", "category": "config-format", "affected_paths": ["Web.config"], "description": "d1", "remediation_tag": "modernize"},
        ])
        provider = MockModelProvider(responses=[_proposal_response(
            "file-only", checks=[{"id": "modernize-produced-output", "command": ["{python}", "-c", script], "supporting_files": []}],
        )])
        phases, _ = plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)
        check = next(c for c in phases[0]["checks"] if c["id"] == "modernize-produced-output")

        with tempfile.TemporaryDirectory() as run_repo:
            import subprocess
            (Path(run_repo) / "appsettings.json").write_text("{}", encoding="utf-8")
            command = [part.format(run_dir="unused", phase_id="phase-1") for part in check["command"]]
            result = subprocess.run(command, cwd=run_repo, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)

    def test_model_description_is_folded_into_the_phase_description(self):
        doc = _doc([
            {"id": "FIND-001", "category": "config-format", "affected_paths": ["src/A/Web.config"], "description": "d1", "remediation_tag": "modernize"},
        ])
        provider = MockModelProvider(responses=[_proposal_response("file-only", description="Extracts settings into appsettings.json.")])
        phases, _ = plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)
        self.assertIn("Extracts settings into appsettings.json.", phases[0]["description"])

    def test_a_proposal_with_no_checks_still_gets_none_for_checks(self):
        doc = _doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/B/B.csproj"], "description": "d1", "remediation_tag": "plain"},
        ])
        provider = MockModelProvider(responses=[_proposal_response("file-only", checks=None)])
        phases, _ = plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)
        self.assertIsNone(phases[0]["checks"])


class BehavioralCheckFixtureTests(unittest.TestCase):
    """A check's supporting_files (e.g. a real test source file backing a behavioral check --
    the 2026-09-20 fix for a check that could be satisfied by a hollow stub) end up as the
    phase's own frozen check_fixtures, and are never allowed into declared_scope even if the
    model's own additional_scope names the same path -- INTEGRITY-3 must have something to
    protect them from the implementer, which only works if they are never in scope to begin with."""

    def test_supporting_files_become_the_phase_check_fixtures(self):
        doc = _doc([
            {"id": "FIND-001", "category": "incompatible-api", "affected_paths": ["src/A/Foo.cs"], "description": "d1", "remediation_tag": "port"},
        ])
        provider = MockModelProvider(responses=[_proposal_response(
            "file-only",
            checks=[{
                "id": "behavioral-check",
                "command": ["dotnet", "test", "tests/Foo.Tests/Foo.Tests.csproj"],
                "supporting_files": [{"path": "tests/Foo.Tests/FooTests.cs", "content": "// real test"}],
            }],
        )])
        phases, _ = plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)
        self.assertEqual(phases[0]["check_fixtures"], [{"path": "tests/Foo.Tests/FooTests.cs", "content": "// real test"}])

    def test_fixture_paths_are_excluded_from_declared_scope_even_if_additional_scope_names_them(self):
        doc = _doc([
            {"id": "FIND-001", "category": "incompatible-api", "affected_paths": ["src/A/Foo.cs"], "description": "d1", "remediation_tag": "port"},
        ])
        provider = MockModelProvider(responses=[_proposal_response(
            "file-only",
            additional_scope=["tests/Foo.Tests/FooTests.cs"],  # deliberately conflicting with the fixture below
            checks=[{
                "id": "behavioral-check",
                "command": ["dotnet", "test", "tests/Foo.Tests/Foo.Tests.csproj"],
                "supporting_files": [{"path": "tests/Foo.Tests/FooTests.cs", "content": "// real test"}],
            }],
        )])
        phases, _ = plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)
        self.assertNotIn("tests/Foo.Tests/FooTests.cs", phases[0]["declared_scope"])

    def test_a_phase_with_no_supporting_files_gets_an_empty_check_fixtures_list(self):
        doc = _doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "fix-a"},
        ])
        provider = MockModelProvider(responses=[_proposal_response("file-only")])
        phases, _ = plangen.generate_phases(doc, provider, SAMPLE_CHECK_SET)
        self.assertEqual(phases[0]["check_fixtures"], [])

    def test_generated_plan_with_check_fixtures_loads_through_the_real_plan_loader(self):
        doc = _doc([
            {"id": "FIND-001", "category": "incompatible-api", "affected_paths": ["src/A/Foo.cs"], "description": "d1", "remediation_tag": "port"},
        ])
        provider = MockModelProvider(responses=[_proposal_response(
            "file-only",
            checks=[{
                "id": "behavioral-check",
                "command": ["dotnet", "test", "tests/Foo.Tests/Foo.Tests.csproj"],
                "supporting_files": [{"path": "tests/Foo.Tests/FooTests.cs", "content": "// real test"}],
            }],
        )])
        with tempfile.TemporaryDirectory() as tmp:
            findings_path = Path(tmp) / "findings.json"
            findings_path.write_text(json.dumps(doc), encoding="utf-8")
            plan_dict = plangen.generate_plan(findings_path=findings_path, model_provider=provider, check_set=SAMPLE_CHECK_SET, run_id_prefix="test-gen")
            plan_path = Path(tmp) / "plan.json"
            plangen.write_plan_file(plan_path, plan_dict)

            from controlplane.plan import load_plan
            loaded = load_plan(plan_path)
            self.assertEqual(len(loaded.phases[0].check_fixtures), 1)
            self.assertEqual(loaded.phases[0].check_fixtures[0].path, "tests/Foo.Tests/FooTests.cs")
            self.assertEqual(loaded.phases[0].check_fixtures[0].content, "// real test")


if __name__ == "__main__":
    unittest.main()
