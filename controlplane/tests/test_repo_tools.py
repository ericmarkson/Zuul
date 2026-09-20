"""Hermetic -- no model involved. The read-only, repo-confined tools shared by both bounded
tool-calling loops (plan-generation research and phase implementation)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane import repo_tools  # noqa: E402


class ResolveWithinRepoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        (self.repo / "sub").mkdir()
        (self.repo / "sub" / "a.txt").write_text("hi", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_path_inside_the_repo_resolves(self):
        result = repo_tools.resolve_within_repo(self.repo, "sub/a.txt")
        self.assertEqual(result, (self.repo / "sub" / "a.txt").resolve())

    def test_a_traversal_attempt_is_refused_not_raised(self):
        result = repo_tools.resolve_within_repo(self.repo, "../../etc/passwd")
        self.assertIsNone(result)

    def test_the_repo_root_itself_resolves(self):
        result = repo_tools.resolve_within_repo(self.repo, ".")
        self.assertEqual(result, self.repo.resolve())


class ReadAndListToolTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        (self.repo / "a.txt").write_text("hello", encoding="utf-8")
        (self.repo / "sub").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_read_file_tool_returns_contents(self):
        self.assertEqual(repo_tools.read_file_tool(self.repo, "a.txt"), "hello")

    def test_read_file_tool_reports_missing_file(self):
        self.assertEqual(repo_tools.read_file_tool(self.repo, "missing.txt"), "error: no such file")

    def test_read_file_tool_refuses_traversal(self):
        self.assertEqual(repo_tools.read_file_tool(self.repo, "../outside.txt"), "error: path is outside the target repository")

    def test_list_directory_tool_lists_entries(self):
        result = repo_tools.list_directory_tool(self.repo, ".")
        self.assertEqual(result, "a.txt\nsub/")

    def test_list_directory_tool_reports_missing_directory(self):
        self.assertEqual(repo_tools.list_directory_tool(self.repo, "nope"), "error: no such directory")


class GrepRepoToolTests(unittest.TestCase):
    """The whole point of this pivot: proving the search generalizes across file types, not
    hardcoded to any one extension."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        (self.repo / "Controllers").mkdir()
        (self.repo / "Views").mkdir()
        (self.repo / "Controllers" / "Home.cs").write_text("using System.Web.Mvc;\nclass Home {}\n", encoding="utf-8")
        (self.repo / "Views" / "Index.cshtml").write_text("@using System.Web.Mvc\n<div>hi</div>\n", encoding="utf-8")
        (self.repo / "readme.md").write_text("no mention here\n", encoding="utf-8")
        (self.repo / "bin").mkdir()
        (self.repo / "bin" / "generated.cs").write_text("System.Web.Mvc leftover\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_finds_matches_across_different_file_extensions(self):
        result = repo_tools.grep_repo_tool(self.repo, "System.Web.Mvc")
        self.assertIn("Controllers/Home.cs:1:", result)
        self.assertIn("Views/Index.cshtml:1:", result)

    def test_search_is_case_insensitive(self):
        result = repo_tools.grep_repo_tool(self.repo, "system.web.mvc")
        self.assertIn("Controllers/Home.cs:1:", result)

    def test_path_glob_restricts_the_search(self):
        result = repo_tools.grep_repo_tool(self.repo, "System.Web.Mvc", path_glob="**/*.cshtml")
        self.assertIn("Views/Index.cshtml:1:", result)
        self.assertNotIn("Controllers/Home.cs", result)

    def test_ignored_directories_are_skipped(self):
        result = repo_tools.grep_repo_tool(self.repo, "System.Web.Mvc")
        self.assertNotIn("bin/generated.cs", result)

    def test_no_matches_reports_clearly(self):
        result = repo_tools.grep_repo_tool(self.repo, "NoSuchTokenAnywhere")
        self.assertEqual(result, "no matches found")

    def test_empty_pattern_is_refused_not_a_match_everything(self):
        result = repo_tools.grep_repo_tool(self.repo, "")
        self.assertEqual(result, "error: empty pattern")

    def test_missing_repo_reports_clearly(self):
        result = repo_tools.grep_repo_tool(Path("/no/such/repo/at/all"), "x")
        self.assertEqual(result, "error: target repository not found")

    def test_max_matches_truncates_rather_than_returning_unbounded_output(self):
        many = self.repo / "many.txt"
        many.write_text("\n".join(f"needle {i}" for i in range(20)), encoding="utf-8")
        result = repo_tools.grep_repo_tool(self.repo, "needle", max_matches=5)
        self.assertEqual(len(result.splitlines()), 6)  # 5 matches + the truncation note
        self.assertIn("truncated", result)


if __name__ == "__main__":
    unittest.main()
