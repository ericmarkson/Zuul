"""FRD SECRET-1: surfaces findings, never masks or filters them."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane import gitops  # noqa: E402
from controlplane.secrets_scan import scan  # noqa: E402


class SecretScanTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        gitops.git(self.repo, "init", "-q")
        gitops.git(self.repo, "config", "user.email", "test@local")
        gitops.git(self.repo, "config", "user.name", "test")

    def tearDown(self):
        self._tmp.cleanup()

    def _commit(self, files: dict[str, str]) -> str:
        for rel_path, content in files.items():
            path = self.repo / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return gitops.commit_all(self.repo, "test commit")

    def test_clean_repo_has_no_findings(self):
        sha = self._commit({"README.md": "nothing to see here"})
        self.assertEqual(scan(self.repo, sha), [])

    def test_connection_string_password_detected(self):
        sha = self._commit({"appsettings.json": '{"cs": "Server=.;Password=Sup3rSecret!"}'})
        findings = scan(self.repo, sha)
        self.assertTrue(any(f.kind == "connection_string_password" for f in findings))

    def test_credential_shaped_path_detected_even_with_no_content_match(self):
        sha = self._commit({".env": "irrelevant content"})
        findings = scan(self.repo, sha)
        self.assertTrue(any(f.kind == "credential_shaped_path" for f in findings))


if __name__ == "__main__":
    unittest.main()
