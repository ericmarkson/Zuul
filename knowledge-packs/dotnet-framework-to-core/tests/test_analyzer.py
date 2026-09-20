"""Hermetic tests for the analyzer -- no network, no target repo required beyond files this
test writes itself. TEST-1's ethos applies here too even though this pack lives outside
controlplane/."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analyzer  # noqa: E402

LEGACY_CSPROJ = """<?xml version="1.0" encoding="utf-8"?>
<Project ToolsVersion="4.0" DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <TargetFrameworkVersion>v4.6.1</TargetFrameworkVersion>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="System" />
    <Reference Include="System.Web.Mvc, Version=5.0.0.0" />
    <Reference Include="System.Web.Abstractions" />
  </ItemGroup>
</Project>
"""

SDK_STYLE_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
</Project>
"""


class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_project(self, rel_dir: str, name: str, content: str) -> Path:
        project_dir = self.repo / rel_dir
        project_dir.mkdir(parents=True, exist_ok=True)
        csproj = project_dir / name
        csproj.write_text(content, encoding="utf-8")
        return csproj

    def test_legacy_project_flagged(self):
        self._write_project("src/Legacy", "Legacy.csproj", LEGACY_CSPROJ)
        findings = analyzer.analyze_repo(self.repo)
        categories = {f.category for f in findings}
        self.assertIn("project-format", categories)
        project_format = next(f for f in findings if f.category == "project-format")
        self.assertEqual(project_format.severity, "high")

    def test_sdk_style_project_not_flagged_as_legacy(self):
        self._write_project("src/Modern", "Modern.csproj", SDK_STYLE_CSPROJ)
        findings = analyzer.analyze_repo(self.repo)
        categories = {f.category for f in findings}
        self.assertNotIn("project-format", categories)

    def test_target_framework_recorded_for_both_styles(self):
        self._write_project("src/Legacy", "Legacy.csproj", LEGACY_CSPROJ)
        self._write_project("src/Modern", "Modern.csproj", SDK_STYLE_CSPROJ)
        findings = analyzer.analyze_repo(self.repo)
        tf_findings = [f for f in findings if f.category == "target-framework"]
        self.assertEqual(len(tf_findings), 2)
        values = {f.evidence["value"] for f in tf_findings}
        self.assertEqual(values, {"v4.6.1", "net8.0"})

    def test_incompatible_api_grouped_by_assembly_family(self):
        self._write_project("src/Legacy", "Legacy.csproj", LEGACY_CSPROJ)
        findings = analyzer.analyze_repo(self.repo)
        incompatible = [f for f in findings if f.category == "incompatible-api"]
        self.assertEqual(len(incompatible), 1)  # System.Web.Mvc + System.Web.Abstractions -> one System.Web group
        self.assertIn("System.Web.Mvc", incompatible[0].evidence["assemblies"])
        self.assertNotIn("System", incompatible[0].evidence["assemblies"])  # bare "System" must not match

    def test_packages_config_detected(self):
        csproj = self._write_project("src/Legacy", "Legacy.csproj", LEGACY_CSPROJ)
        (csproj.parent / "packages.config").write_text("<packages/>", encoding="utf-8")
        findings = analyzer.analyze_repo(self.repo)
        self.assertTrue(any(f.category == "package-management" for f in findings))

    def test_no_packages_config_no_finding(self):
        self._write_project("src/Modern", "Modern.csproj", SDK_STYLE_CSPROJ)
        findings = analyzer.analyze_repo(self.repo)
        self.assertFalse(any(f.category == "package-management" for f in findings))

    def test_legacy_config_file_detected(self):
        (self.repo / "Web.config").write_text("<configuration/>", encoding="utf-8")
        findings = analyzer.analyze_repo(self.repo)
        config_findings = [f for f in findings if f.category == "config-format"]
        self.assertEqual(len(config_findings), 1)
        self.assertEqual(config_findings[0].affected_paths, ["Web.config"])

    def test_bin_and_obj_directories_are_skipped(self):
        self._write_project("bin/Debug", "ShouldBeIgnored.csproj", LEGACY_CSPROJ)
        (self.repo / "obj").mkdir()
        (self.repo / "obj" / "Web.config").write_text("<configuration/>", encoding="utf-8")
        findings = analyzer.analyze_repo(self.repo)
        self.assertEqual(findings, [])

    def test_every_finding_has_affected_paths(self):
        """AUDIT-1: every finding must carry at least one affected path."""
        self._write_project("src/Legacy", "Legacy.csproj", LEGACY_CSPROJ)
        findings = analyzer.analyze_repo(self.repo)
        for f in findings:
            self.assertTrue(f.affected_paths, f"{f.id} has no affected_paths")


if __name__ == "__main__":
    unittest.main()
