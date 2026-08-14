import unittest
from unittest.mock import patch

from mariner_core import (
    AppError,
    ProviderConfig,
    analyze_case,
    answer_followup,
    draft_document,
)


CASE = {
    "situation": (
        "A fictional chief engineer fell on shipboard stairs while working and "
        "suffered a femur fracture."
    )
}

FIRST = {"summary": "Z.AI first analysis", "missingFacts": [], "issues": []}
INDEPENDENT = {
    "summary": "Claude independent analysis",
    "missingFacts": [],
    "issues": [],
}
CRITIQUE = {
    "agreements": [],
    "disagreements": [],
    "unsupportedClaims": [],
    "omissions": [],
    "questionsForArbiter": [],
}
ARBITRATION = {
    "executiveSummary": "Arbitrated result",
    "overallConfidence": "high",
    "resolvedDisputes": [],
    "unresolvedQuestions": [],
    "provisionalRights": [],
    "recommendedActions": [],
    "documentPlan": [],
    "doNotDoYet": [],
    "lawyerEscalationTriggers": [],
    "disclaimer": "",
}


class PanelFaultToleranceTests(unittest.TestCase):
    def setUp(self):
        self.config = ProviderConfig(
            openai_key="openai",
            anthropic_key="anthropic",
            zai_key="zai",
        )

    def run_panel(self, failures=None):
        failures = failures or {}
        prompts = {}
        responses = {
            "first": FIRST,
            "independent": INDEPENDENT,
            "critique": CRITIQUE,
            "arbitration": ARBITRATION,
        }

        def fake_call(_provider, prompt, _config, **kwargs):
            kind = kwargs["demo_kind"]
            prompts[kind] = prompt
            if kind in failures:
                raise failures[kind]
            return dict(responses[kind])

        with patch("mariner_core.call_provider", side_effect=fake_call):
            panel = analyze_case(CASE, self.config)
        return panel, prompts

    def failure_stages(self, panel):
        return {failure["stage"] for failure in panel["providerFailures"]}

    def test_zai_failure_preserves_claude_and_continues(self):
        panel, prompts = self.run_panel(
            {"first": AppError("Z.AI returned an unreadable response.")}
        )

        self.assertIsNone(panel["first"])
        self.assertEqual(panel["independent"], INDEPENDENT)
        self.assertEqual(panel["critique"], CRITIQUE)
        self.assertIsNotNone(panel["arbitration"])
        self.assertEqual(panel["arbitration"]["overallConfidence"], "medium")
        self.assertEqual(panel["workflow"]["status"], "degraded")
        self.assertEqual(panel["stageStatus"]["firstAnalysis"], "failed")
        self.assertIn("firstAnalysis", self.failure_stages(panel))
        self.assertIn("One of the blind first-stage analyses is unavailable", prompts["critique"])
        self.assertIn('"stage": "firstAnalysis"', prompts["critique"])
        self.assertIn("overallConfidence must not exceed medium", prompts["arbitration"])

    def test_claude_independent_failure_preserves_zai_and_retries_critique_stage(self):
        panel, prompts = self.run_panel(
            {"independent": AppError("Anthropic request timed out.")}
        )

        self.assertEqual(panel["first"], FIRST)
        self.assertIsNone(panel["independent"])
        self.assertEqual(panel["critique"], CRITIQUE)
        self.assertIsNotNone(panel["arbitration"])
        self.assertEqual(panel["arbitration"]["overallConfidence"], "medium")
        self.assertIn("critique", prompts)
        self.assertIn("independentAnalysis", self.failure_stages(panel))
        self.assertIn("no independent reviewer view should be inferred", panel["workflow"]["anchoringControl"])

    def test_both_first_stage_failures_skip_critique_and_arbitration(self):
        panel, prompts = self.run_panel(
            {
                "first": AppError("Z.AI failed."),
                "independent": AppError("Anthropic failed."),
            }
        )

        self.assertIsNone(panel["first"])
        self.assertIsNone(panel["independent"])
        self.assertIsNone(panel["critique"])
        self.assertIsNone(panel["arbitration"])
        self.assertNotIn("critique", prompts)
        self.assertNotIn("arbitration", prompts)
        self.assertEqual(panel["stageStatus"]["critique"], "skipped")
        self.assertEqual(panel["stageStatus"]["arbitration"], "skipped")
        self.assertEqual(panel["workflow"]["status"], "failed")
        self.assertEqual(
            self.failure_stages(panel), {"firstAnalysis", "independentAnalysis"}
        )

    def test_critique_failure_still_arbitrates_both_independent_views(self):
        panel, prompts = self.run_panel(
            {"critique": AppError("Anthropic returned unreadable critique JSON.")}
        )

        self.assertEqual(panel["first"], FIRST)
        self.assertEqual(panel["independent"], INDEPENDENT)
        self.assertIsNone(panel["critique"])
        self.assertIsNotNone(panel["arbitration"])
        self.assertEqual(panel["arbitration"]["overallConfidence"], "medium")
        self.assertEqual(panel["stageStatus"]["critique"], "failed")
        self.assertIn("critique", self.failure_stages(panel))
        self.assertIn('"stage": "critique"', prompts["arbitration"])

    def test_arbiter_failure_returns_earlier_outputs_and_blocks_downstream(self):
        panel, _prompts = self.run_panel(
            {"arbitration": AppError("OpenAI request timed out.")}
        )

        self.assertEqual(panel["first"], FIRST)
        self.assertEqual(panel["independent"], INDEPENDENT)
        self.assertEqual(panel["critique"], CRITIQUE)
        self.assertIsNone(panel["arbitration"])
        self.assertEqual(panel["workflow"]["status"], "partial")
        self.assertEqual(panel["stageStatus"]["arbitration"], "failed")
        self.assertIn("arbitration", self.failure_stages(panel))

        with self.assertRaisesRegex(AppError, "Run the panel analysis"):
            draft_document(
                CASE,
                panel,
                ProviderConfig(demo_mode=True),
                document_type="Incident notice",
                recipient="Employer",
            )
        with self.assertRaisesRegex(AppError, "Run the panel analysis"):
            answer_followup(
                CASE,
                panel,
                ProviderConfig(demo_mode=True),
                question="What next?",
            )

    def test_complete_panel_has_no_failure_metadata_or_confidence_cap(self):
        panel, _prompts = self.run_panel()

        self.assertEqual(panel["workflow"]["status"], "complete")
        self.assertEqual(panel["providerFailures"], [])
        self.assertTrue(all(value == "completed" for value in panel["stageStatus"].values()))
        self.assertEqual(panel["arbitration"]["overallConfidence"], "high")

    def test_single_analysis_clears_fabricated_agreements_and_disagreements(self):
        fabricated = dict(CRITIQUE)
        fabricated["agreements"] = [{"point": "Invented agreement"}]
        fabricated["disagreements"] = [{"topic": "Invented disagreement"}]

        def fake_call(_provider, _prompt, _config, **kwargs):
            kind = kwargs["demo_kind"]
            if kind == "first":
                raise AppError("Z.AI failed")
            if kind == "independent":
                return dict(INDEPENDENT)
            if kind == "critique":
                return fabricated
            return dict(ARBITRATION)

        with patch("mariner_core.call_provider", side_effect=fake_call):
            panel = analyze_case(CASE, self.config)

        self.assertEqual(panel["critique"]["agreements"], [])
        self.assertEqual(panel["critique"]["disagreements"], [])

    def test_degraded_confidence_is_never_promoted_and_disputes_are_capped(self):
        arbitration = dict(ARBITRATION)
        arbitration["overallConfidence"] = ""
        arbitration["resolvedDisputes"] = [
            {"topic": "One", "confidence": "high"},
            {"topic": "Two", "confidence": "unknown"},
        ]

        def fake_call(_provider, _prompt, _config, **kwargs):
            kind = kwargs["demo_kind"]
            if kind == "first":
                raise AppError("Z.AI failed")
            if kind == "independent":
                return dict(INDEPENDENT)
            if kind == "critique":
                return dict(CRITIQUE)
            return arbitration

        with patch("mariner_core.call_provider", side_effect=fake_call):
            panel = analyze_case(CASE, self.config)

        self.assertEqual(panel["arbitration"]["overallConfidence"], "low")
        self.assertEqual(
            [item["confidence"] for item in panel["arbitration"]["resolvedDisputes"]],
            ["medium", "low"],
        )

    def test_truncated_analysis_is_used_but_flagged_to_the_reviewer(self):
        truncated = dict(FIRST)
        truncated["responseTruncated"] = True

        def fake_call(_provider, prompt, _config, **kwargs):
            kind = kwargs["demo_kind"]
            prompts[kind] = prompt
            if kind == "first":
                return dict(truncated)
            return dict(
                {
                    "independent": INDEPENDENT,
                    "critique": CRITIQUE,
                    "arbitration": ARBITRATION,
                }[kind]
            )

        prompts: dict[str, str] = {}
        with patch("mariner_core.call_provider", side_effect=fake_call):
            panel = analyze_case(CASE, self.config)

        self.assertEqual(panel["first"], truncated)
        self.assertEqual(panel["providerFailures"], [])
        self.assertEqual(panel["stageStatus"]["firstAnalysis"], "completed")
        self.assertEqual(
            [warning["stage"] for warning in panel["providerWarnings"]],
            ["firstAnalysis"],
        )
        self.assertEqual(panel["workflow"]["status"], "degraded")
        # The arbiter must know a source analysis was cut short before weighing it.
        self.assertIn('"errorType": "truncated_response"', prompts["arbitration"])

    def test_truncated_arbitration_is_flagged_to_the_reader(self):
        truncated = dict(ARBITRATION)
        truncated["responseTruncated"] = True

        def fake_call(_provider, _prompt, _config, **kwargs):
            kind = kwargs["demo_kind"]
            if kind == "arbitration":
                return dict(truncated)
            return dict({"first": FIRST, "independent": INDEPENDENT, "critique": CRITIQUE}[kind])

        with patch("mariner_core.call_provider", side_effect=fake_call):
            panel = analyze_case(CASE, self.config)

        self.assertEqual(panel["providerFailures"], [])
        self.assertEqual(
            [warning["stage"] for warning in panel["providerWarnings"]], ["arbitration"]
        )
        self.assertEqual(panel["workflow"]["status"], "degraded")

    def test_provider_error_text_is_redacted_before_reuse(self):
        secret_echo = "SECRET-CASE-TEXT"
        panel, prompts = self.run_panel(
            {"first": AppError(f"Z.AI request failed: upstream echoed {secret_echo}")}
        )

        serialized_failures = str(panel["providerFailures"])
        self.assertNotIn(secret_echo, serialized_failures)
        self.assertNotIn(secret_echo, prompts["critique"])
        self.assertNotIn(secret_echo, prompts["arbitration"])
        self.assertEqual(panel["providerFailures"][0]["errorType"], "request_rejected")


if __name__ == "__main__":
    unittest.main()
