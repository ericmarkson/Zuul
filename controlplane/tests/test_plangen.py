"""FRD PLAN-1 path (a) / PLAN-2 v1 scope: findings group into phases by remediation tag plus
declared-path overlap, purely lexically. Hermetic -- synthetic findings and templates, no real
pack or repo involved."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane import plangen  # noqa: E402

SAMPLE_CHECK_SET = [{"id": "build", "command": ["true"], "result_artifact": "nonexistent.xml", "result_format": "junit"}]


def _write_template(templates_dir: Path, template_id: str, side_effect_class: str, **extra) -> None:
    data = {"id": template_id, "side_effect_class": side_effect_class, **extra}
    (templates_dir / f"{template_id}.json").write_text(json.dumps(data), encoding="utf-8")


class PlanGenTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.templates_dir = Path(self._tmp.name) / "templates"
        self.templates_dir.mkdir()
        _write_template(self.templates_dir, "fix-a", "file-only")
        _write_template(self.templates_dir, "fix-b", "package-manager-mutating")

    def tearDown(self):
        self._tmp.cleanup()

    def _doc(self, findings: list[dict]) -> dict:
        return {
            "generated_at": "2026-09-21T00:00:00Z",
            "pack": "test-pack",
            "pack_content_hash": "deadbeef" * 8,
            "target_repo": "/fake/repo",
            "findings": findings,
        }

    def test_findings_with_no_remediation_tag_are_dropped_not_silently(self):
        doc = self._doc([
            {"id": "FIND-001", "category": "x", "affected_paths": ["a.csproj"], "description": "d", "remediation_tag": None},
        ])
        phases, dropped = plangen.generate_phases(doc, self.templates_dir, SAMPLE_CHECK_SET)
        self.assertEqual(phases, [])
        self.assertEqual(dropped, ["FIND-001"])

    def test_findings_sharing_tag_and_project_are_grouped_into_one_phase(self):
        doc = self._doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "fix-a"},
            {"id": "FIND-002", "category": "target-framework", "affected_paths": ["src/A/A.csproj"], "description": "d2", "remediation_tag": "fix-a"},
        ])
        phases, dropped = plangen.generate_phases(doc, self.templates_dir, SAMPLE_CHECK_SET)
        self.assertEqual(len(phases), 1)
        self.assertEqual(dropped, [])
        self.assertEqual(phases[0]["side_effect_class"], "file-only")
        self.assertIn("src/A/A.csproj", phases[0]["declared_scope"])

    def test_same_tag_different_projects_produce_separate_phases(self):
        doc = self._doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "fix-a"},
            {"id": "FIND-002", "category": "project-format", "affected_paths": ["src/B/B.csproj"], "description": "d2", "remediation_tag": "fix-a"},
        ])
        phases, _ = plangen.generate_phases(doc, self.templates_dir, SAMPLE_CHECK_SET)
        self.assertEqual(len(phases), 2)
        scopes = [set(p["declared_scope"]) for p in phases]
        self.assertIn({"src/A/A.csproj"}, scopes)
        self.assertIn({"src/B/B.csproj"}, scopes)

    def test_different_tags_produce_separate_phases_even_in_same_project(self):
        doc = self._doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "fix-a"},
            {"id": "FIND-002", "category": "package-management", "affected_paths": ["src/A/A.csproj", "src/A/packages.config"], "description": "d2", "remediation_tag": "fix-b"},
        ])
        phases, _ = plangen.generate_phases(doc, self.templates_dir, SAMPLE_CHECK_SET)
        self.assertEqual(len(phases), 2)
        tags = {p["id"].rsplit("-", 1)[-1] for p in phases}
        self.assertEqual(tags, {"a", "b"})
        side_effect_classes = {p["side_effect_class"] for p in phases}
        self.assertEqual(side_effect_classes, {"file-only", "package-manager-mutating"})

    def test_every_generated_phase_has_all_plan5_fields(self):
        doc = self._doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "fix-a"},
        ])
        phases, _ = plangen.generate_phases(doc, self.templates_dir, SAMPLE_CHECK_SET)
        for phase in phases:
            for key in ("id", "description", "declared_scope", "side_effect_class", "edits", "checks"):
                self.assertIn(key, phase)
            self.assertEqual(phase["edits"], [])
            self.assertIsNone(phase["checks"])  # no expected_new_paths declared -> use plan default

    def test_unknown_remediation_tag_raises_rather_than_silently_dropping(self):
        doc = self._doc([
            {"id": "FIND-001", "category": "x", "affected_paths": ["a.csproj"], "description": "d", "remediation_tag": "no-such-template"},
        ])
        with self.assertRaises(ValueError):
            plangen.generate_phases(doc, self.templates_dir, SAMPLE_CHECK_SET)

    def test_config_format_finding_attaches_to_nearest_project_by_path_prefix(self):
        doc = self._doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "fix-a"},
            {"id": "FIND-002", "category": "config-format", "affected_paths": ["src/A/Web.config"], "description": "d2", "remediation_tag": "fix-a"},
        ])
        phases, _ = plangen.generate_phases(doc, self.templates_dir, SAMPLE_CHECK_SET)
        self.assertEqual(len(phases), 1)  # same component (src/A) + same tag -> merged
        self.assertEqual(set(phases[0]["declared_scope"]), {"src/A/A.csproj", "src/A/Web.config"})

    def test_generate_plan_produces_a_plan_a_loadable_shape(self):
        """The whole point: this must be loadable by Phase A's plan.py without any changes to
        it. Exercise the actual loader, not just a structural assertion."""
        doc = self._doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "fix-a"},
        ])
        findings_path = Path(self._tmp.name) / "findings.json"
        findings_path.write_text(json.dumps(doc), encoding="utf-8")

        plan_dict = plangen.generate_plan(
            findings_path=findings_path,
            templates_dir=self.templates_dir,
            check_set=SAMPLE_CHECK_SET,
            run_id_prefix="test-gen",
        )
        plan_path = Path(self._tmp.name) / "plan.json"
        plangen.write_plan_file(plan_path, plan_dict)

        from controlplane.plan import load_plan
        loaded = load_plan(plan_path)
        self.assertEqual(loaded.run_id_prefix, "test-gen")
        self.assertEqual(len(loaded.phases), 1)
        self.assertEqual(loaded.phases[0].side_effect_class, "file-only")


class ExpectedNewPathsTests(unittest.TestCase):
    """The Phase F fix: a template that promises to create a file gets that promise checked."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.templates_dir = Path(self._tmp.name) / "templates"
        self.templates_dir.mkdir()
        _write_template(
            self.templates_dir, "modernize", "file-only",
            description="Extracts settings into appsettings.json.",
            expected_new_paths=["appsettings.json"],
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _doc(self, findings: list[dict]) -> dict:
        return {
            "generated_at": "2026-09-21T00:00:00Z", "pack": "test-pack",
            "pack_content_hash": "deadbeef" * 8, "target_repo": "/fake/repo", "findings": findings,
        }

    def test_expected_path_is_added_to_declared_scope(self):
        doc = self._doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "modernize"},
            {"id": "FIND-002", "category": "config-format", "affected_paths": ["src/A/Web.config"], "description": "d2", "remediation_tag": "modernize"},
        ])
        phases, _ = plangen.generate_phases(doc, self.templates_dir, SAMPLE_CHECK_SET)
        self.assertEqual(len(phases), 1)
        self.assertIn("src/A/appsettings.json", phases[0]["declared_scope"])

    def test_generated_check_verifies_the_expected_path_and_is_added_on_top_of_defaults(self):
        doc = self._doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/A/A.csproj"], "description": "d1", "remediation_tag": "modernize"},
        ])
        phases, _ = plangen.generate_phases(doc, self.templates_dir, SAMPLE_CHECK_SET)
        checks = phases[0]["checks"]
        self.assertIsNotNone(checks)
        check_ids = {c["id"] for c in checks}
        self.assertIn("build", check_ids)  # the plan default is still there, not replaced
        self.assertIn("modernize-produced-output", check_ids)

    def test_generated_check_actually_fails_when_the_expected_file_is_missing(self):
        """Not just present in the plan -- actually run it and confirm it enforces what it
        claims to, the same failure this whole fix exists to catch."""
        doc = self._doc([
            {"id": "FIND-001", "category": "config-format", "affected_paths": ["src/A/Web.config"], "description": "d1", "remediation_tag": "modernize"},
        ])
        phases, _ = plangen.generate_phases(doc, self.templates_dir, SAMPLE_CHECK_SET)
        check = next(c for c in phases[0]["checks"] if c["id"] == "modernize-produced-output")

        with tempfile.TemporaryDirectory() as run_repo:
            import subprocess
            command = [part.format(run_dir="unused", phase_id="phase-1") for part in check["command"]]
            result = subprocess.run(command, cwd=run_repo, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)  # appsettings.json was never created

    def test_generated_check_passes_when_the_expected_file_exists_and_is_non_empty(self):
        # a bare config-format finding with no project-format anchor resolves to "(repo-root)",
        # so the expected path is "appsettings.json" at the repo root -- confirmed by the
        # companion test below, not assumed here.
        doc = self._doc([
            {"id": "FIND-001", "category": "config-format", "affected_paths": ["src/A/Web.config"], "description": "d1", "remediation_tag": "modernize"},
        ])
        phases, _ = plangen.generate_phases(doc, self.templates_dir, SAMPLE_CHECK_SET)
        self.assertIn("appsettings.json", phases[0]["declared_scope"])
        check = next(c for c in phases[0]["checks"] if c["id"] == "modernize-produced-output")

        with tempfile.TemporaryDirectory() as run_repo:
            import subprocess
            (Path(run_repo) / "appsettings.json").write_text("{}", encoding="utf-8")
            command = [part.format(run_dir="unused", phase_id="phase-1") for part in check["command"]]
            result = subprocess.run(command, cwd=run_repo, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)

    def test_template_description_is_folded_into_the_phase_description(self):
        doc = self._doc([
            {"id": "FIND-001", "category": "config-format", "affected_paths": ["src/A/Web.config"], "description": "d1", "remediation_tag": "modernize"},
        ])
        phases, _ = plangen.generate_phases(doc, self.templates_dir, SAMPLE_CHECK_SET)
        self.assertIn("Extracts settings into appsettings.json.", phases[0]["description"])

    def test_a_phase_without_expected_new_paths_still_gets_none_for_checks(self):
        templates_dir = self.templates_dir
        _write_template(templates_dir, "plain", "file-only")
        doc = self._doc([
            {"id": "FIND-001", "category": "project-format", "affected_paths": ["src/B/B.csproj"], "description": "d1", "remediation_tag": "plain"},
        ])
        phases, _ = plangen.generate_phases(doc, templates_dir, SAMPLE_CHECK_SET)
        self.assertIsNone(phases[0]["checks"])


if __name__ == "__main__":
    unittest.main()
