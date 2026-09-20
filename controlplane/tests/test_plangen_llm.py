"""Hermetic -- MockModelProvider only, zero network. The single model call that proposes a
phase's side_effect_class/description/additional_scope/checks -- the 2026-09-20 pivot's
replacement for fixed node templates."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from controlplane import plangen_llm  # noqa: E402
from controlplane.model_provider import MockModelProvider, ModelResponse  # noqa: E402

SAMPLE_FINDINGS = [
    {"id": "FIND-001", "category": "config-format", "severity": "medium", "affected_paths": ["Web.config"], "description": "legacy config file", "evidence": {}},
]
SAMPLE_CHECK_SET = [{"id": "build", "command": ["true"], "result_artifact": "x", "result_format": "junit"}]


def _response(payload) -> ModelResponse:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return ModelResponse(content=content, input_tokens=10, output_tokens=10, latency_seconds=0.01)


class ProposePhaseTests(unittest.TestCase):
    def test_well_formed_proposal_parses(self):
        provider = MockModelProvider(responses=[_response({
            "side_effect_class": "file-only", "description": "migrate config", "additional_scope": ["appsettings.json"], "checks": None,
        })])
        proposal = plangen_llm.propose_phase(provider, "modernize", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET)
        self.assertEqual(proposal.side_effect_class, "file-only")
        self.assertEqual(proposal.description, "migrate config")
        self.assertEqual(proposal.additional_scope, ["appsettings.json"])
        self.assertIsNone(proposal.checks)

    def test_proposal_with_checks_parses_into_check_proposals(self):
        provider = MockModelProvider(responses=[_response({
            "side_effect_class": "file-only", "description": "d", "additional_scope": [],
            "checks": [{"id": "c1", "python_script": "import sys; sys.exit(0)"}],
        })])
        proposal = plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET)
        self.assertEqual(len(proposal.checks), 1)
        self.assertEqual(proposal.checks[0].id, "c1")

    def test_non_json_response_raises(self):
        provider = MockModelProvider(responses=[_response("not json")])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET)

    def test_invalid_side_effect_class_raises(self):
        provider = MockModelProvider(responses=[_response({
            "side_effect_class": "made-up-class", "description": "d", "additional_scope": [], "checks": None,
        })])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET)

    def test_missing_description_raises(self):
        provider = MockModelProvider(responses=[_response({
            "side_effect_class": "file-only", "additional_scope": [], "checks": None,
        })])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET)

    def test_empty_description_raises(self):
        provider = MockModelProvider(responses=[_response({
            "side_effect_class": "file-only", "description": "   ", "additional_scope": [], "checks": None,
        })])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET)

    def test_non_list_additional_scope_raises(self):
        provider = MockModelProvider(responses=[_response({
            "side_effect_class": "file-only", "description": "d", "additional_scope": "not-a-list", "checks": None,
        })])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET)

    def test_check_missing_python_script_raises(self):
        provider = MockModelProvider(responses=[_response({
            "side_effect_class": "file-only", "description": "d", "additional_scope": [],
            "checks": [{"id": "c1"}],
        })])
        with self.assertRaises(plangen_llm.MalformedPlanProposal):
            plangen_llm.propose_phase(provider, "t", "(repo-root)", SAMPLE_FINDINGS, SAMPLE_CHECK_SET)

    def test_prompt_includes_finding_details_and_remediation_tag(self):
        provider = MockModelProvider(responses=[_response({
            "side_effect_class": "file-only", "description": "d", "additional_scope": [], "checks": None,
        })])
        plangen_llm.propose_phase(provider, "modernize-config", "src/A", SAMPLE_FINDINGS, SAMPLE_CHECK_SET)
        _system, user_prompt = provider.calls[0]
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


if __name__ == "__main__":
    unittest.main()
