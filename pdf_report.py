"""Printable PDF export of the panel record.

This module deliberately imports neither Streamlit nor any provider client. It
renders the same dictionaries the web UI renders, so the export can be tested
without a browser, API keys, or network access, and so nothing here can leak
case facts off the machine.

Text is drawn with an embedded DejaVu face rather than a PDF core font: the app
drafts in Romanian, and the core fonts cannot represent s-comma or t-comma, so a
core-font export would silently corrupt legal wording.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from mariner_core import AppError

FONT_DIR = Path(__file__).resolve().parent / "assets"
REGULAR_FONT = FONT_DIR / "DejaVuSans.ttf"
BOLD_FONT = FONT_DIR / "DejaVuSans-Bold.ttf"

DISCLAIMER = (
    "Mariner Advocate is decision support, not legal representation. This document "
    "was produced by AI models and has not been reviewed by a qualified maritime "
    "lawyer. Verify the flag-state law, the seafarer employment agreement, any "
    "applicable collective bargaining agreement, and the insurance position before "
    "relying on anything here. Do not sign a release, settlement, medical "
    "declaration, resignation, or repatriation waiver without qualified review."
)

STAGE_LABELS = {
    "firstAnalysis": "First analysis",
    "independentAnalysis": "Independent analysis",
    "critique": "Comparison and critique",
    "arbitration": "Senior arbitration",
}

COVERAGE_NOTICES = {
    "complete": "All review stages completed.",
    "degraded": (
        "Reduced coverage: at least one review stage failed or was cut short. The "
        "conclusions below rest on fewer independent views than intended."
    ),
    "partial": (
        "Partial review only: senior arbitration did not complete, so there is no "
        "arbitrated synthesis. The individual analyses are reproduced as they were "
        "returned."
    ),
    "failed": (
        "No usable review was produced. Treat this document as a record of the "
        "attempt, not as analysis."
    ),
}


def _text(value: Any) -> str:
    """Normalize provider text into something a PDF line can hold."""
    if value is None or isinstance(value, (dict, list)):
        return ""
    cleaned = str(value).replace("\r\n", "\n").replace("\r", "\n")
    cleaned = "".join(
        char
        for char in cleaned
        if char == "\n" or unicodedata.category(char)[0] != "C"
    )
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _field(item: Any, key: str, default: str = "") -> str:
    if not isinstance(item, dict):
        return default
    return _text(item.get(key)) or default


def _dedupe(items: list[Any], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        marker = _field(item, key).lower()
        if not marker or marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def _joined(*parts: str, separator: str = " · ") -> str:
    return separator.join(part for part in parts if part)


class _Report(FPDF):
    def __init__(self, subtitle: str):
        super().__init__(format="A4", unit="mm")
        self.subtitle = subtitle
        if not REGULAR_FONT.exists() or not BOLD_FONT.exists():
            raise AppError(
                "The PDF fonts are missing from this deployment, so the export was "
                "not produced. Expected assets/DejaVuSans.ttf and "
                "assets/DejaVuSans-Bold.ttf."
            )
        self.add_font("DejaVu", "", str(REGULAR_FONT))
        self.add_font("DejaVu", "B", str(BOLD_FONT))
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(18, 16, 18)
        self.set_title("Mariner Advocate")
        # The panel record is the user's own case material; no author or
        # producer metadata is added that could identify the machine.
        self.set_creator("Mariner Advocate")
        self.alias_nb_pages()
        self.add_page()

    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("DejaVu", "", 7.5)
        self.set_text_color(120)
        self.cell(
            0, 6, self.subtitle, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )
        self.set_draw_color(210)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)
        self.set_text_color(0)

    def footer(self) -> None:
        self.set_y(-16)
        self.set_font("DejaVu", "", 7)
        self.set_text_color(120)
        self.multi_cell(
            0,
            3.4,
            "Decision support, not legal advice. Have a qualified maritime lawyer, "
            "union representative, or competent authority review before acting.",
            align="L",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        self.cell(0, 4, f"Page {self.page_no()} of {{nb}}", align="R")
        self.set_text_color(0)

    def title_block(self, title: str, meta: list[str]) -> None:
        self.set_font("DejaVu", "B", 19)
        self.multi_cell(
            0, 8.5, _text(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )
        self.ln(1)
        self.set_font("DejaVu", "", 8.5)
        self.set_text_color(90)
        for line in meta:
            if line:
                self.multi_cell(
                    0, 4.4, _text(line), new_x=XPos.LMARGIN, new_y=YPos.NEXT
                )
        self.set_text_color(0)
        self.ln(3)

    def section(self, title: str) -> None:
        # Keep a heading with at least the first lines of its content.
        if self.get_y() > self.h - 52:
            self.add_page()
        self.ln(3)
        self.set_font("DejaVu", "B", 12)
        self.multi_cell(0, 6, _text(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(180)
        self.line(self.l_margin, self.get_y() + 0.5, self.w - self.r_margin, self.get_y() + 0.5)
        self.ln(3)

    def subheading(self, text: str) -> None:
        if not text:
            return
        if self.get_y() > self.h - 40:
            self.add_page()
        self.set_font("DejaVu", "B", 9.5)
        self.multi_cell(0, 5, _text(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def body(self, text: str, *, size: float = 9.5, gap: float = 1.5) -> None:
        content = _text(text)
        if not content:
            return
        self.set_font("DejaVu", "", size)
        self.multi_cell(0, 4.8, content, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(gap)

    def note(self, text: str) -> None:
        content = _text(text)
        if not content:
            return
        self.set_font("DejaVu", "", 8.5)
        self.set_text_color(105)
        self.multi_cell(0, 4.2, content, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0)
        self.ln(1.5)

    def bullet(self, text: str, *, marker: str = "•") -> None:
        content = _text(text)
        if not content:
            return
        if self.get_y() > self.h - 34:
            self.add_page()
        self.set_font("DejaVu", "", 9.5)
        indent = 5.5
        self.cell(indent, 4.8, marker)
        self.multi_cell(
            self.w - self.l_margin - self.r_margin - indent,
            4.8,
            content,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    def callout(self, text: str) -> None:
        content = _text(text)
        if not content:
            return
        if self.get_y() > self.h - 42:
            self.add_page()
        self.set_font("DejaVu", "", 9.5)
        self.set_fill_color(238, 240, 242)
        self.multi_cell(
            0, 5, content, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )
        self.ln(2)

    def empty(self, text: str) -> None:
        self.note(text)


def _timestamp(panel: dict[str, Any]) -> str:
    raw = _text(_mapping(panel).get("generatedAt"))
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        moment = datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%d %B %Y, %H:%M UTC")


def _render_coverage(pdf: _Report, panel: dict[str, Any]) -> None:
    workflow = _mapping(panel.get("workflow"))
    status = _text(workflow.get("status")) or "failed"
    failures = _items(panel.get("providerFailures"))
    warnings = _items(panel.get("providerWarnings"))

    if status != "complete" or failures or warnings:
        pdf.section("Review coverage")
        pdf.callout(COVERAGE_NOTICES.get(status, COVERAGE_NOTICES["failed"]))
        for entry in failures + warnings:
            stage = STAGE_LABELS.get(_field(entry, "stage"), _field(entry, "stage"))
            heading = _joined(stage, _field(entry, "provider"), _field(entry, "model"))
            pdf.bullet(_joined(heading, _field(entry, "message"), separator=" — "))
        pdf.ln(1)
        pdf.note(_text(workflow.get("anchoringControl")))


def _render_arbitration(pdf: _Report, arbitration: dict[str, Any]) -> None:
    pdf.section("Executive summary")
    pdf.body(
        _field(arbitration, "executiveSummary", "No synthesis was returned."),
        size=10.5,
    )
    confidence = _field(arbitration, "overallConfidence", "unclear")
    pdf.note(f"Overall confidence: {confidence}")

    actions = _items(arbitration.get("recommendedActions"))
    pdf.section("What to do next")
    if not actions:
        pdf.empty("No recommended actions were returned.")
    for index, action in enumerate(actions, start=1):
        order = _field(action, "order") or str(index)
        pdf.subheading(f"{order}. {_field(action, 'action', 'Action')}")
        pdf.body(_field(action, "purpose"), size=9)
        detail = _joined(
            f"Owner: {_field(action, 'owner')}" if _field(action, "owner") else "",
            f"Timing: {_field(action, 'timing')}" if _field(action, "timing") else "",
        )
        pdf.note(detail)

    rights = _items(arbitration.get("provisionalRights"))
    if rights:
        pdf.section("Possible rights and claims")
        for right in rights:
            pdf.subheading(
                _joined(
                    _field(right, "rightOrClaim", "Possible claim"),
                    _field(right, "status", "unclear"),
                    separator=" — ",
                )
            )
            pdf.body(_field(right, "basis"), size=9)
            verification = _field(right, "verification")
            if verification:
                pdf.note(f"Verification needed: {verification}")

    warnings = _items(arbitration.get("doNotDoYet"))
    if warnings:
        pdf.section("Do not do these yet")
        for warning in warnings:
            pdf.bullet(
                _joined(
                    _field(warning, "action"),
                    _field(warning, "reason"),
                    separator=" — ",
                )
            )

    questions = _items(arbitration.get("unresolvedQuestions"))
    if questions:
        pdf.section("Questions no model should guess")
        for question in questions:
            pdf.subheading(_field(question, "question", "Open question"))
            needed = _field(question, "neededEvidence")
            consequence = _field(question, "consequence")
            if needed:
                pdf.body(f"Needed: {needed}", size=9, gap=0.5)
            if consequence:
                pdf.note(f"Why it matters: {consequence}")

    resolutions = _items(arbitration.get("resolvedDisputes"))
    if resolutions:
        pdf.section("Senior resolutions")
        for resolution in resolutions:
            pdf.subheading(_field(resolution, "topic", "Dispute"))
            pdf.body(_field(resolution, "resolution"), size=9)
            pdf.note(
                _joined(
                    _field(resolution, "reason"),
                    f"Confidence: {_field(resolution, 'confidence', 'unclear')}",
                )
            )

    triggers = [_text(item) for item in _items(arbitration.get("lawyerEscalationTriggers"))]
    triggers = [item for item in triggers if item]
    if triggers:
        pdf.section("Get qualified help promptly if")
        for trigger in triggers:
            pdf.bullet(trigger)


def _render_disputes(pdf: _Report, critique: dict[str, Any]) -> None:
    disagreements = _items(critique.get("disagreements"))
    unsupported = _items(critique.get("unsupportedClaims"))
    if not disagreements and not unsupported:
        return

    pdf.section("Where the models disagreed")
    for disagreement in disagreements:
        pdf.subheading(
            _joined(
                _field(disagreement, "topic", "Disagreement"),
                f"{_field(disagreement, 'materiality', 'unclear')} materiality",
                separator=" — ",
            )
        )
        pdf.body(
            f"First analyst: {_field(disagreement, 'firstPosition', 'Not returned.')}",
            size=9,
            gap=0.5,
        )
        pdf.body(
            "Independent reviewer: "
            f"{_field(disagreement, 'reviewerPosition', 'Not returned.')}",
            size=9,
            gap=0.5,
        )
        pdf.note(
            _joined(
                _field(disagreement, "reason"),
                f"Would be resolved by: {_field(disagreement, 'evidenceThatWouldResolve')}"
                if _field(disagreement, "evidenceThatWouldResolve")
                else "",
            )
        )

    if unsupported:
        pdf.subheading("Unsupported claims caught")
        for claim in unsupported:
            pdf.bullet(
                _joined(
                    _field(claim, "claim"),
                    _field(claim, "problem"),
                    f"Correction: {_field(claim, 'correction')}"
                    if _field(claim, "correction")
                    else "",
                    separator=" — ",
                )
            )


def _render_evidence(pdf: _Report, panel: dict[str, Any]) -> None:
    first = _mapping(panel.get("first"))
    independent = _mapping(panel.get("independent"))

    missing = _dedupe(
        _items(first.get("missingFacts")) + _items(independent.get("missingFacts")),
        "question",
    )
    if missing:
        pdf.section("Questions to answer")
        for item in missing:
            pdf.subheading(
                _joined(
                    _field(item, "question"),
                    f"priority: {_field(item, 'priority', 'unclear')}",
                    separator=" — ",
                )
            )
            pdf.note(_field(item, "whyItMatters"))

    evidence = _dedupe(
        _items(first.get("evidenceChecklist"))
        + _items(independent.get("evidenceChecklist")),
        "item",
    )
    if evidence:
        pdf.section("Evidence preservation checklist")
        for item in evidence:
            pdf.bullet(_field(item, "item", "Evidence item"), marker="☐")
            detail = _joined(_field(item, "reason"), _field(item, "howToPreserve"))
            if detail:
                pdf.note("    " + detail)

    sources: list[Any] = []
    for analysis in (first, independent):
        for issue in _items(analysis.get("issues")):
            if isinstance(issue, dict):
                sources.extend(_items(issue.get("sources")))
    sources = _dedupe(sources, "url")
    if sources:
        pdf.section("Sources surfaced — verify with counsel")
        for source in sources:
            pdf.bullet(
                _joined(
                    _field(source, "title", "Source"),
                    _field(source, "status", "needs-verification"),
                    separator=" — ",
                )
            )
            url = _field(source, "url")
            if url:
                pdf.note("    " + url)


def _render_analyses(pdf: _Report, panel: dict[str, Any]) -> None:
    workflow = _mapping(panel.get("workflow"))
    entries = (
        ("First analysis", "first", _text(workflow.get("analyst"))),
        ("Independent analysis", "independent", _text(workflow.get("reviewer"))),
    )
    for title, key, model in entries:
        result = panel.get(key)
        pdf.section(_joined(title, model, separator=" — "))
        if not isinstance(result, dict):
            pdf.empty(
                "This stage was unavailable. Other completed provider results were "
                "preserved."
            )
            continue
        if result.get("responseTruncated"):
            pdf.callout(
                "This model hit its output limit mid-answer. The complete leading "
                "part of its response is reproduced; later sections are missing."
            )
        pdf.body(_field(result, "summary"))
        urgent = _items(result.get("urgentActions"))
        if urgent:
            pdf.subheading("Urgent actions surfaced by this model")
            for action in urgent:
                pdf.bullet(
                    _joined(
                        _field(action, "action", "Action to confirm"),
                        _field(action, "timing"),
                        _field(action, "owner"),
                        separator=" — ",
                    )
                )
        issues = _items(result.get("issues"))
        if issues:
            pdf.subheading("Issues identified")
            for issue in issues:
                pdf.bullet(
                    _joined(
                        _field(issue, "issue"),
                        _field(issue, "provisionalConclusion"),
                        f"confidence: {_field(issue, 'confidence', 'unclear')}",
                        separator=" — ",
                    )
                )


def _render_case(pdf: _Report, case_data: dict[str, Any], labels: dict[str, str]) -> None:
    entries = [
        (labels.get(key, key), _text(value))
        for key, value in _mapping(case_data).items()
        if _text(value)
    ]
    if not entries:
        return
    pdf.section("Case as submitted")
    for label, value in entries:
        pdf.subheading(label)
        pdf.body(value, size=9)


def _render_discussion(pdf: _Report, discussion: list[Any]) -> None:
    turns = [turn for turn in _items(discussion) if isinstance(turn, dict)]
    if not turns:
        return
    pdf.section("Next-step discussion")
    for turn in turns:
        question = _field(turn, "question")
        if question:
            pdf.subheading(f"Q: {question}")
        response = _mapping(turn.get("response"))
        pdf.body(_field(response, "answer", "No answer returned."), size=9)
        for action in _items(response.get("nextActions")):
            pdf.bullet(
                _joined(
                    _field(action, "action"),
                    _field(action, "owner"),
                    _field(action, "timing"),
                    separator=" — ",
                )
            )
        unknowns = [_text(item) for item in _items(response.get("unknowns"))]
        unknowns = [item for item in unknowns if item]
        if unknowns:
            pdf.note("Still unknown: " + ", ".join(unknowns))


def build_case_pdf(
    case_data: dict[str, Any],
    panel: dict[str, Any],
    *,
    field_labels: dict[str, str] | None = None,
    discussion: list[Any] | None = None,
) -> bytes:
    """Render the panel record as a printable PDF."""
    if not isinstance(panel, dict) or not panel:
        raise AppError("Run the panel analysis before downloading a PDF.")

    workflow = _mapping(panel.get("workflow"))
    generated = _timestamp(panel)
    pdf = _Report(f"Mariner Advocate — case review · {generated}")
    pdf.title_block(
        "Seafarer case review",
        [
            f"Generated {generated}",
            _joined(
                f"First analysis: {_text(workflow.get('analyst')) or 'unknown'}",
                f"Independent review: {_text(workflow.get('reviewer')) or 'unknown'}",
            ),
            f"Senior arbitration: {_text(workflow.get('arbiter')) or 'unknown'}",
        ],
    )
    pdf.callout(DISCLAIMER)

    _render_coverage(pdf, panel)

    arbitration = panel.get("arbitration")
    if isinstance(arbitration, dict):
        _render_arbitration(pdf, arbitration)
    else:
        pdf.section("Executive summary")
        pdf.empty(
            "Senior arbitration was unavailable, so there is no arbitrated synthesis. "
            "The individual analyses below are reproduced as they were returned."
        )

    critique = panel.get("critique")
    if isinstance(critique, dict):
        _render_disputes(pdf, critique)

    _render_evidence(pdf, panel)
    _render_analyses(pdf, panel)
    _render_discussion(pdf, discussion or [])
    _render_case(pdf, case_data or {}, field_labels or {})

    return bytes(pdf.output())


def build_document_pdf(
    draft: dict[str, Any], *, generated_at: str | None = None
) -> bytes:
    """Render a drafted letter as a printable PDF."""
    if not isinstance(draft, dict) or not draft:
        raise AppError("Create a draft before downloading a PDF.")

    title = _field(draft, "title", "Legal draft")
    generated = _text(generated_at) or datetime.now(timezone.utc).strftime(
        "%d %B %Y, %H:%M UTC"
    )
    pdf = _Report(f"Mariner Advocate — draft · {generated}")
    pdf.title_block(title, [f"Prepared {generated}", "Draft for review before sending"])
    pdf.callout(
        _field(draft, "reviewWarning")
        or "Have a qualified maritime lawyer, union representative, or competent "
        "adviser review this draft before it is sent or signed."
    )

    pdf.section("Draft")
    pdf.body(_field(draft, "documentText", "No draft text was returned."), size=10)

    attachments = [_text(item) for item in _items(draft.get("attachmentsChecklist"))]
    attachments = [item for item in attachments if item]
    if attachments:
        pdf.section("Attachments checklist")
        for item in attachments:
            pdf.bullet(item, marker="☐")

    fields = [_text(item) for item in _items(draft.get("fieldsToConfirm"))]
    fields = [item for item in fields if item]
    if fields:
        pdf.section("Confirm before use")
        for item in fields:
            pdf.bullet(item, marker="☐")

    return bytes(pdf.output())
