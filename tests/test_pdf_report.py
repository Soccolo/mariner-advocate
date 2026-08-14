import io
import re
import unittest

from pypdf import PdfReader

from mariner_core import AppError, FIELD_LABELS, ProviderConfig, analyze_case, demo_response
from pdf_report import build_case_pdf, build_document_pdf

CASE = {
    "situation": (
        "Inginerul-șef a căzut pe scări în timpul unei furtuni și a suferit o "
        "fractură de femur."
    ),
    "shipName": "Amalfi",
    "flagState": "Malta",
    "desiredOutcome": "Plata tratamentului, repatriere și despăgubire.",
}


def read(data: bytes) -> str:
    """Extract PDF text with whitespace normalized, since line wrapping splits phrases."""
    reader = PdfReader(io.BytesIO(data))
    return re.sub(r"\s+", " ", "\n".join(page.extract_text() for page in reader.pages))


class CasePdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel = analyze_case(CASE, ProviderConfig(demo_mode=True))
        cls.data = build_case_pdf(
            CASE,
            cls.panel,
            field_labels=FIELD_LABELS,
            discussion=[
                {"question": "Ce trimitem astăzi?", "response": demo_response("followup")}
            ],
        )
        cls.text = read(cls.data)

    def test_produces_a_valid_pdf(self):
        self.assertTrue(self.data.startswith(b"%PDF-"))
        self.assertGreater(len(PdfReader(io.BytesIO(self.data)).pages), 0)

    def test_carries_every_part_of_the_answer(self):
        for section in (
            "Executive summary",
            "What to do next",
            "Possible rights and claims",
            "Do not do these yet",
            "Questions no model should guess",
            "Evidence preservation checklist",
            "Sources surfaced",
            "First analysis",
            "Independent analysis",
            "Next-step discussion",
            "Case as submitted",
        ):
            with self.subTest(section=section):
                self.assertIn(section, self.text)

    def test_romanian_text_is_not_corrupted(self):
        # A PDF core font cannot encode s-comma or t-comma, so this is the
        # regression guard for the embedded font.
        self.assertIn("Inginerul-șef", self.text)
        self.assertIn("fractură de femur", self.text)
        self.assertIn("repatriere și despăgubire", self.text)
        self.assertIn("astăzi", self.text)

    def test_states_it_is_not_legal_advice(self):
        self.assertIn("not legal advice", self.text)
        self.assertIn("has not been reviewed by a qualified maritime lawyer", self.text)

    def test_reports_reduced_coverage_on_the_page(self):
        panel = dict(self.panel)
        panel["workflow"] = {**panel["workflow"], "status": "degraded"}
        panel["providerWarnings"] = [
            {
                "stage": "firstAnalysis",
                "provider": "Z.AI",
                "model": "glm-5.3",
                "errorType": "truncated_response",
                "message": "Ran out of output allowance mid-answer.",
            }
        ]
        panel["first"] = {**panel["first"], "responseTruncated": True}

        text = read(build_case_pdf(CASE, panel, field_labels=FIELD_LABELS))

        self.assertIn("Review coverage", text)
        self.assertIn("Reduced coverage", text)
        self.assertIn("Ran out of output allowance mid-answer.", text)
        self.assertIn("hit its output limit mid-answer", text)

    def test_missing_arbitration_is_stated_rather_than_faked(self):
        panel = dict(self.panel)
        panel["arbitration"] = None
        panel["workflow"] = {**panel["workflow"], "status": "partial"}

        text = read(build_case_pdf(CASE, panel, field_labels=FIELD_LABELS))

        self.assertIn("no arbitrated synthesis", text)
        self.assertIn("First analysis", text)

    def test_unbreakable_tokens_do_not_break_layout(self):
        panel = dict(self.panel)
        panel["first"] = {
            "issues": [
                {
                    "issue": "Long source",
                    "sources": [
                        {
                            "title": "T",
                            "url": "https://example.test/" + "a" * 400,
                            "status": "needs-verification",
                        }
                    ],
                }
            ]
        }

        self.assertTrue(
            build_case_pdf(CASE, panel, field_labels=FIELD_LABELS).startswith(b"%PDF-")
        )

    def test_malformed_panel_values_do_not_crash(self):
        panel = {
            "generatedAt": "not-a-date",
            "workflow": "not-a-dict",
            "first": ["not", "a", "dict"],
            "critique": {"disagreements": [None, {"topic": "t"}]},
            "providerFailures": ["junk"],
            "arbitration": {
                "executiveSummary": {"nested": "dict"},
                "recommendedActions": ["string", 42, None],
                "provisionalRights": None,
            },
        }

        self.assertTrue(build_case_pdf({"situation": None}, panel).startswith(b"%PDF-"))

    def test_empty_panel_is_refused_with_a_usable_message(self):
        with self.assertRaisesRegex(AppError, "Run the panel analysis"):
            build_case_pdf(CASE, {})


class DocumentPdfTests(unittest.TestCase):
    def test_renders_the_draft_with_its_checklists(self):
        draft = demo_response("draft")
        text = read(build_document_pdf(draft))

        self.assertIn("NOTICE OF SHIPBOARD ACCIDENT", text)
        self.assertIn("Attachments checklist", text)
        self.assertIn("Confirm before use", text)
        self.assertIn("Medical note", text)
        # The model's own review warning must reach the printed page.
        self.assertIn(draft["reviewWarning"], text)
        self.assertIn("not legal advice", text)

    def test_supplies_a_review_warning_when_the_draft_omits_one(self):
        draft = dict(demo_response("draft"))
        draft["reviewWarning"] = ""

        text = read(build_document_pdf(draft))

        self.assertIn("review this draft before it is sent or signed", text)

    def test_exports_edited_wording_rather_than_the_original(self):
        draft = dict(demo_response("draft"))
        draft["documentText"] = "Text edited by the family before sending."

        text = read(build_document_pdf(draft))

        self.assertIn("Text edited by the family before sending.", text)
        self.assertNotIn("NOTICE OF SHIPBOARD ACCIDENT, MEDICAL", text.split("Draft")[-1])

    def test_empty_draft_is_refused(self):
        with self.assertRaisesRegex(AppError, "Create a draft"):
            build_document_pdf({})


if __name__ == "__main__":
    unittest.main()
