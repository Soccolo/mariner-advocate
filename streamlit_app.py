"""Streamlit interface for Mariner Advocate."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any
from urllib.parse import urlparse

import streamlit as st

from mariner_core import (
    AppError,
    ProviderConfig,
    analyze_case,
    answer_followup,
    draft_document,
)


st.set_page_config(
    page_title="Mariner Advocate",
    page_icon="⚓",
    layout="wide",
    initial_sidebar_state="expanded",
)


STATIC_CSS = """
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&family=Barlow+Condensed:wght@500;600;700&display=swap" rel="stylesheet">
<style>
  /* ---- Industry: steel-blue blueprint on a light technical ground ---- */
  :root {
    --bg: #f2f2f3;
    --surface: #e9e9ea;
    --ink: #1d1f20;
    --muted: #5d5d60;
    --faint: #7a7a7d;
    --line: rgba(29, 31, 32, .16);
    --rule: rgba(29, 31, 32, .28);
    --accent: #5980a6;
    --accent-deep: #416180;
    --accent-field: #1d2d3d;
    --heading: "Barlow Condensed", system-ui, sans-serif;
    --body: "Barlow", system-ui, sans-serif;
    /* corner registration marks, drawn as background layers */
    --mk:
      linear-gradient(#1d1f208c,#1d1f208c) left -4px top 0/9px 1px no-repeat,
      linear-gradient(#1d1f208c,#1d1f208c) left 0 top -4px/1px 9px no-repeat,
      linear-gradient(#1d1f208c,#1d1f208c) right -4px top 0/9px 1px no-repeat,
      linear-gradient(#1d1f208c,#1d1f208c) right 0 top -4px/1px 9px no-repeat,
      linear-gradient(#1d1f208c,#1d1f208c) left -4px bottom 0/9px 1px no-repeat,
      linear-gradient(#1d1f208c,#1d1f208c) left 0 bottom -4px/1px 9px no-repeat,
      linear-gradient(#1d1f208c,#1d1f208c) right -4px bottom 0/9px 1px no-repeat,
      linear-gradient(#1d1f208c,#1d1f208c) right 0 bottom -4px/1px 9px no-repeat;
    --mk-light:
      linear-gradient(#f2f2f3a8,#f2f2f3a8) left -4px top 0/9px 1px no-repeat,
      linear-gradient(#f2f2f3a8,#f2f2f3a8) left 0 top -4px/1px 9px no-repeat,
      linear-gradient(#f2f2f3a8,#f2f2f3a8) right -4px top 0/9px 1px no-repeat,
      linear-gradient(#f2f2f3a8,#f2f2f3a8) right 0 top -4px/1px 9px no-repeat,
      linear-gradient(#f2f2f3a8,#f2f2f3a8) left -4px bottom 0/9px 1px no-repeat,
      linear-gradient(#f2f2f3a8,#f2f2f3a8) left 0 bottom -4px/1px 9px no-repeat,
      linear-gradient(#f2f2f3a8,#f2f2f3a8) right -4px bottom 0/9px 1px no-repeat,
      linear-gradient(#f2f2f3a8,#f2f2f3a8) right 0 bottom -4px/1px 9px no-repeat;
  }

  /* ---- ground and type ---- */
  .stApp { background: var(--bg); }
  html, body, .stApp, [class*="css"] { font-family: var(--body); color: var(--ink); }
  .block-container { max-width: 1500px; padding-top: 1.8rem; padding-bottom: 4rem; }
  h1, h2, h3, h4, h5, h6,
  .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {
    font-family: var(--heading); font-weight: 600; letter-spacing: -.01em; line-height: 1.08;
  }
  .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 { text-transform: uppercase; letter-spacing: .02em; }
  .stMarkdown p, .stMarkdown li { font-size: 14.5px; line-height: 1.6; }
  a, a:visited { color: var(--accent-deep); text-underline-offset: 3px; }
  a:hover { color: #2c455d; }
  ::selection { background: #d6ebff; }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  footer, #MainMenu { visibility: hidden; }

  /* ---- hero: a spec-sheet plate on the paper ground, not a gradient card ---- */
  .hero {
    position: relative;
    margin-bottom: .9rem;
    padding: 1.9rem 2rem;
    border: 1px solid var(--line);
    background: transparent;
    color: var(--ink);
  }
  .hero::before { content: ""; position: absolute; inset: 0; background: var(--mk); pointer-events: none; }
  .hero .eyebrow {
    font-family: var(--heading); font-weight: 600; font-size: .72rem;
    letter-spacing: .16em; text-transform: uppercase; color: var(--accent-deep); opacity: 1;
  }
  .hero h1 {
    font-size: clamp(2.2rem, 3.6vw, 3.5rem); line-height: 1.02;
    margin: .5rem 0 .6rem; max-width: 22ch; letter-spacing: -.02em;
  }
  .hero p { max-width: 74ch; font-size: 1rem; line-height: 1.6; color: #424244; opacity: 1; margin: 0; }

  /* ---- workflow cards: transparent line drawings with corner marks ---- */
  .workflow-card {
    position: relative;
    border: 1px solid var(--line);
    border-radius: 0;
    background: transparent;
    padding: .95rem 1rem;
    min-height: 112px;
  }
  .workflow-card::before { content: ""; position: absolute; inset: 0; background: var(--mk); pointer-events: none; }
  .workflow-card .number {
    font-family: var(--heading); font-weight: 600; font-size: .72rem;
    letter-spacing: .14em; color: var(--accent-deep);
  }
  .workflow-card strong {
    display: block; margin: .3rem 0 .25rem;
    font-family: var(--heading); font-weight: 600; font-size: 1.06rem;
    letter-spacing: .02em; text-transform: uppercase; color: var(--ink);
  }
  .workflow-card small { color: var(--muted); font-size: .8rem; line-height: 1.45; }

  /* ---- the waiting plate ---- */
  .case-empty {
    border: 1px dashed var(--rule);
    border-radius: 0;
    background: transparent;
    padding: 3.4rem 2rem;
    text-align: center;
    color: var(--muted);
  }
  .case-empty h3 {
    color: var(--ink); margin: .6rem 0 .5rem;
    font-family: var(--heading); font-size: 1.9rem; text-transform: uppercase;
  }
  .small-note { color: var(--faint); font-size: .82rem; }

  /* ---- forms: square-cornered, hairline, surface-filled inputs ---- */
  div[data-testid="stForm"] {
    border: 1px solid var(--line); border-radius: 0;
    background: transparent; padding: 1.2rem 1.3rem;
  }
  .stTextInput label, .stTextArea label, .stSelectbox label, .stCheckbox label {
    font-family: var(--body) !important; font-size: 12px !important; color: #424244 !important;
  }
  .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div,
  .stNumberInput input {
    background: var(--surface) !important;
    border: 1px solid var(--line) !important;
    border-radius: 4px !important;
    color: var(--ink) !important;
    font-family: var(--body) !important;
  }
  .stTextInput input:focus, .stTextArea textarea:focus { border-color: var(--accent) !important; box-shadow: none !important; }
  .stTextInput input::placeholder, .stTextArea textarea::placeholder { color: #98989b !important; }

  /* ---- buttons: the primary is the one solid object on the board ---- */
  .stButton button, .stDownloadButton button, .stFormSubmitButton button, .stLinkButton a {
    border-radius: 0 !important;
    font-family: var(--heading) !important; font-weight: 600 !important;
    letter-spacing: .07em; text-transform: uppercase;
    border: 1px solid var(--rule) !important;
    background: transparent !important; color: var(--ink) !important;
    transition: background .12s ease;
  }
  .stButton button:hover, .stDownloadButton button:hover, .stLinkButton a:hover {
    background: rgba(29,31,32,.07) !important;
  }
  .stFormSubmitButton button[kind="primaryFormSubmit"],
  .stButton button[kind="primary"] {
    position: relative;
    background: var(--accent) !important; border-color: var(--accent) !important;
    color: var(--bg) !important; padding: .8rem 1.1rem !important; font-size: 1.05rem !important;
  }
  .stFormSubmitButton button[kind="primaryFormSubmit"]::before,
  .stButton button[kind="primary"]::before {
    content: ""; position: absolute; inset: 0; background: var(--mk-light); pointer-events: none;
  }
  .stFormSubmitButton button[kind="primaryFormSubmit"]:hover,
  .stButton button[kind="primary"]:hover { background: #597ea3 !important; border-color: #597ea3 !important; }

  /* ---- containers, expanders, tabs ---- */
  div[data-testid="stVerticalBlockBorderWrapper"] > div:has(> div[data-testid="stVerticalBlock"]) { border-radius: 0; }
  div[data-testid="stExpander"] details {
    border: 1px solid var(--line) !important; border-radius: 0 !important; background: transparent !important;
  }
  div[data-testid="stExpander"] summary p {
    font-family: var(--heading) !important; font-weight: 600; letter-spacing: .05em; text-transform: uppercase;
  }
  .stTabs [data-baseweb="tab-list"] { gap: 0; border-bottom: 1px solid var(--line); }
  .stTabs [data-baseweb="tab"] {
    font-family: var(--heading); font-weight: 600; font-size: .95rem;
    letter-spacing: .08em; text-transform: uppercase; color: var(--faint);
    padding: .7rem .9rem; border-radius: 0;
  }
  .stTabs [aria-selected="true"] { color: var(--ink); }
  .stTabs [data-baseweb="tab-highlight"] { background: var(--accent); }

  /* ---- metrics read as spec-sheet numbers ---- */
  [data-testid="stMetric"] { border: 1px solid var(--line); padding: .8rem .9rem; }
  [data-testid="stMetricLabel"] p {
    font-size: 11px !important; letter-spacing: .12em; text-transform: uppercase; color: var(--faint) !important;
  }
  [data-testid="stMetricValue"] {
    color: var(--accent-deep); font-family: var(--heading); font-weight: 600; font-size: 1.9rem;
  }

  /* ---- callouts: mono palette, one steel edge, no decorative colour ---- */
  div[data-testid="stAlert"] {
    border-radius: 0; border: 1px solid var(--line); border-left: 3px solid var(--accent);
    background: var(--surface); color: #424244;
  }
  div[data-testid="stAlert"] p { font-size: 13.5px; line-height: 1.55; }
  div[data-testid="stAlert"] svg { color: var(--accent-deep); }
  /* the executive summary st.info reads as the one reversed field */
  div[data-testid="stAlert"]:has(svg[title="info"]),
  .exec-field {
    background: var(--accent-field); color: #f2f2f3; border-color: var(--accent-field);
    border-left-color: var(--accent);
  }
  div[data-testid="stAlert"]:has(svg[title="info"]) p { color: #f2f2f3; font-size: 15px; }

  /* ---- sidebar ---- */
  section[data-testid="stSidebar"] {
    background: var(--surface); border-right: 1px solid var(--line);
  }
  section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h1 {
    font-family: var(--heading); text-transform: uppercase; letter-spacing: .04em;
  }
  section[data-testid="stSidebar"] .stCode, section[data-testid="stSidebar"] pre {
    background: transparent !important; border: 1px solid var(--line); border-radius: 0;
  }
  hr, div[data-testid="stDivider"] hr { border-color: var(--line); }
  div[data-testid="stStatusWidget"], div[data-testid="stStatus"] {
    border-radius: 0 !important; border: 1px solid var(--line) !important;
  }
</style>
"""


def get_setting(name: str, default: Any = "") -> Any:
    """Read a setting from environment or Streamlit secrets without exposing it."""
    env_value = os.getenv(name)
    if env_value not in (None, ""):
        return env_value
    try:
        if name in st.secrets:
            return st.secrets[name]
    except (FileNotFoundError, KeyError, RuntimeError):
        pass
    return default


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


PUBLIC_DEMO_ONLY = as_bool(get_setting("PUBLIC_DEMO_ONLY", False))
DEMO_MODE = PUBLIC_DEMO_ONLY or as_bool(get_setting("DEMO_MODE", False))


def build_config() -> ProviderConfig:
    try:
        timeout = int(get_setting("REQUEST_TIMEOUT_SECONDS", 420))
    except (TypeError, ValueError):
        timeout = 420
    return ProviderConfig(
        openai_key=str(get_setting("OPENAI_API_KEY", "") or ""),
        anthropic_key=str(get_setting("ANTHROPIC_API_KEY", "") or ""),
        zai_key=str(get_setting("ZAI_API_KEY", "") or ""),
        openai_model=str(get_setting("OPENAI_MODEL", "gpt-5.6-sol") or "gpt-5.6-sol"),
        anthropic_model=str(
            get_setting("ANTHROPIC_MODEL", "claude-opus-4-8") or "claude-opus-4-8"
        ),
        zai_model=str(get_setting("ZAI_MODEL", "glm-5.1") or "glm-5.1"),
        demo_mode=DEMO_MODE,
        timeout_seconds=max(60, min(timeout, 900)),
    )


def require_shared_password() -> None:
    expected = str(get_setting("APP_PASSWORD", "") or "")
    if not expected or st.session_state.get("authenticated"):
        return
    st.markdown(STATIC_CSS, unsafe_allow_html=True)
    st.title("⚓ Mariner Advocate")
    st.caption("Private workspace access")
    entered = st.text_input("Shared password", type="password", autocomplete="current-password")
    if st.button("Open workspace", type="primary"):
        if hmac.compare_digest(entered.encode("utf-8"), expected.encode("utf-8")):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("That password is not correct.")
    st.info(
        "This shared-password gate is a basic safeguard, not enterprise authentication. "
        "A real deployment still needs TLS, access controls, logging safeguards, and a privacy review."
    )
    st.stop()


def collect_case_data() -> dict[str, str]:
    keys = [
        "situation",
        "shipName",
        "imoNumber",
        "flagState",
        "role",
        "employer",
        "shipowner",
        "incidentDate",
        "incidentLocation",
        "medicalStatus",
        "contractTerms",
        "evidence",
        "communications",
        "desiredOutcome",
    ]
    return {key: str(st.session_state.get(f"case_{key}", "") or "") for key in keys}


def safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def item_text(item: Any, key: str, default: str = "") -> str:
    if not isinstance(item, dict):
        return default
    return str(item.get(key) or default)


def dedupe(items: list[Any], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        marker = str(item.get(key) or "").strip().lower()
        if not marker or marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def valid_web_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def slug(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value)
    return "-".join(part for part in cleaned.split("-") if part)[:70] or "legal-draft"


def render_sidebar(config: ProviderConfig) -> None:
    with st.sidebar:
        st.header("Workspace")
        if PUBLIC_DEMO_ONLY:
            st.error("Public demo: fictional data only")
            st.caption("Provider calls are disabled and deterministic demo responses are used.")
        elif config.demo_mode:
            st.info("Demo mode is on. No provider calls will be made.")
        else:
            st.caption("Server-side provider status")
            statuses = {
                "OpenAI": bool(config.openai_key),
                "Anthropic": bool(config.anthropic_key),
                "Z.AI": bool(config.zai_key),
            }
            for name, ready in statuses.items():
                st.write(f"{'✅' if ready else '❌'} {name}")
        st.divider()
        st.caption("Configured models")
        st.code(
            f"Z.AI: {config.zai_model}\nClaude: {config.anthropic_model}\nOpenAI: {config.openai_model}",
            language=None,
        )

        panel = st.session_state.get("panel")
        case_data = st.session_state.get("submitted_case")
        if isinstance(panel, dict) and isinstance(case_data, dict):
            export = json.dumps(
                {"caseData": case_data, "panel": panel}, ensure_ascii=False, indent=2
            )
            st.download_button(
                "Download case export",
                export,
                file_name="mariner-advocate-case.json",
                mime="application/json",
                use_container_width=True,
            )

        if st.button("Clear this session", use_container_width=True):
            for key in list(st.session_state):
                if key == "authenticated":
                    continue
                del st.session_state[key]
            st.rerun()

        st.divider()
        st.caption(
            "API keys are read only from server environment variables or Streamlit secrets; "
            "they are never entered in this page or included in case exports."
        )


def render_header() -> None:
    st.markdown(
        """
        <div class="hero">
          <div class="eyebrow">LEGAL ISSUE-SPOTTING FOR SEAFARERS</div>
          <h1>A clearer path through a difficult moment.</h1>
          <p>Describe the incident once. Two models form independent views, a reviewer
          maps disagreements, and a senior model turns the supported result into practical
          next steps and careful document drafts.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if PUBLIC_DEMO_ONLY:
        st.error(
            "This public deployment is for fictional demonstrations only. Do not enter real "
            "names, medical facts, employment details, documents, or other personal data. "
            "Streamlit Community Cloud must not be used for this family's real case."
        )
    else:
        st.warning(
            "This supports, but does not replace, a qualified maritime lawyer, union representative, "
            "insurer, competent authority, or medical team. Do not delay treatment. Case facts are "
            "sent to the three configured AI providers when a live panel runs."
        )

    cards = [
        ("01", "Independent analysis", "Z.AI reviews facts and possible legal routes."),
        ("02", "Blind cross-check", "Claude commits its own view before seeing AI 1."),
        ("03", "Dispute review", "Claude compares the committed views and maps gaps."),
        ("04", "Senior arbitration", "OpenAI resolves supported disputes and flags uncertainty."),
    ]
    columns = st.columns(4)
    for column, (number, title, detail) in zip(columns, cards):
        with column:
            st.markdown(
                f'<div class="workflow-card"><span class="number">{number}</span>'
                f"<strong>{title}</strong><small>{detail}</small></div>",
                unsafe_allow_html=True,
            )


def render_intake(config: ProviderConfig) -> None:
    missing = []
    if not config.demo_mode:
        if not config.zai_key:
            missing.append("ZAI_API_KEY")
        if not config.anthropic_key:
            missing.append("ANTHROPIC_API_KEY")
        if not config.openai_key:
            missing.append("OPENAI_API_KEY")
    if missing:
        st.error(
            "Live review is disabled until these server-side settings are added: "
            + ", ".join(missing)
        )

    st.subheader("Case intake")
    st.caption("Use facts you know and mark uncertain details as uncertain.")
    with st.form("case_intake", border=True):
        st.text_area(
            "What happened? *",
            height=220,
            key="case_situation",
            placeholder=(
                "Describe the incident in chronological order: what happened, where the person "
                "was, what work was underway, the injury, the medical response, and what the "
                "company has said."
            ),
        )

        st.markdown("#### Vessel and employment")
        col_a, col_b = st.columns(2)
        with col_a:
            st.text_input("Ship name", key="case_shipName")
            st.text_input("Flag state (high priority)", key="case_flagState")
            st.text_input("Employer / crewing agency", key="case_employer")
        with col_b:
            st.text_input("IMO number", key="case_imoNumber")
            st.text_input("Role on board", key="case_role")
            st.text_input("Shipowner / operator", key="case_shipowner")

        st.markdown("#### Incident and treatment")
        col_c, col_d = st.columns(2)
        with col_c:
            st.text_input("Incident date and time", key="case_incidentDate")
        with col_d:
            st.text_input("Location / port / waters", key="case_incidentLocation")
        st.text_area(
            "Injury and current treatment",
            height=110,
            key="case_medicalStatus",
            placeholder="Use clinicians' wording where possible; do not speculate.",
        )

        st.markdown("#### Documents and communications")
        st.text_area(
            "Employment agreement / CBA",
            height=90,
            key="case_contractTerms",
            placeholder="Paste relevant clauses or note which documents are available.",
        )
        st.text_area(
            "Incident report and evidence",
            height=90,
            key="case_evidence",
            placeholder="Logbook, witnesses, CCTV, photos, weather, risk assessment, medical report, receipts.",
        )
        st.text_area(
            "What has the company or insurer said?",
            height=90,
            key="case_communications",
            placeholder="Paste exact wording where possible, including dates and who said it.",
        )
        st.text_area(
            "Desired outcome",
            height=75,
            key="case_desiredOutcome",
            placeholder="Medical payment, sick wages, repatriation, disability benefit, evidence, complaint...",
        )

        with st.expander("Privacy checklist before submitting"):
            st.write(
                "Remove passport numbers, banking details, full home addresses, passwords, and "
                "unrelated medical history. Share only what is necessary. This app does not "
                "persist cases to a database, but live case facts are sent to all three providers."
            )

        fictional_confirmed = True
        if PUBLIC_DEMO_ONLY:
            fictional_confirmed = st.checkbox(
                "I confirm that I am using entirely fictional data in this public demo.",
                key="fictional_data_confirmed",
            )

        submitted = st.form_submit_button(
            "Run the legal review panel",
            type="primary",
            use_container_width=True,
            disabled=bool(missing),
        )

    if not submitted:
        return
    if not fictional_confirmed:
        st.error("Confirm that the public demo contains fictional data before continuing.")
        return

    case_data = collect_case_data()
    try:
        with st.status("Panel in session", expanded=True) as status:
            panel = analyze_case(case_data, config, progress=status.write)
            status.update(label="Panel review complete", state="complete", expanded=False)
        st.session_state.panel = panel
        st.session_state.submitted_case = case_data
        st.session_state.pop("draft", None)
        st.session_state.pop("discussion", None)
        st.success("The panel completed its review.")
    except AppError as exc:
        st.error(str(exc))
    except Exception:
        st.error("The panel could not finish because of an unexpected server error.")


def render_overview(panel: dict[str, Any]) -> None:
    arbitration = panel.get("arbitration") or {}
    workflow = panel.get("workflow") or {}
    st.info(str(arbitration.get("executiveSummary") or "No synthesis was returned."))
    metric_a, metric_b, metric_c = st.columns(3)
    metric_a.metric("Overall confidence", str(arbitration.get("overallConfidence") or "unclear").title())
    metric_b.metric("Recommended actions", len(safe_list(arbitration.get("recommendedActions"))))
    metric_c.metric("Open questions", len(safe_list(arbitration.get("unresolvedQuestions"))))

    st.subheader("What to do next")
    actions = safe_list(arbitration.get("recommendedActions"))
    for index, action in enumerate(actions, start=1):
        if not isinstance(action, dict):
            continue
        order = action.get("order") or index
        title = item_text(action, "action", "Action")
        with st.container(border=True):
            st.markdown(f"**{order}. {title}**")
            details = [
                item_text(action, "purpose"),
                f"Owner: {item_text(action, 'owner')}" if item_text(action, "owner") else "",
                f"Timing: {item_text(action, 'timing')}" if item_text(action, "timing") else "",
            ]
            st.caption(" · ".join(detail for detail in details if detail))

    st.subheader("Possible rights and claims")
    for right in safe_list(arbitration.get("provisionalRights")):
        if not isinstance(right, dict):
            continue
        with st.expander(
            f"{item_text(right, 'rightOrClaim', 'Possible claim')} — {item_text(right, 'status', 'unclear')}"
        ):
            st.write(item_text(right, "basis", "Basis not returned."))
            st.caption("Verification needed: " + item_text(right, "verification", "Not specified."))

    warnings = safe_list(arbitration.get("doNotDoYet"))
    if warnings:
        st.subheader("Do not do these yet")
        for warning in warnings:
            if isinstance(warning, dict):
                st.error(f"{item_text(warning, 'action')} — {item_text(warning, 'reason')}")

    st.caption(
        str(workflow.get("anchoringControl") or "")
        + " This output is decision support, not legal representation."
    )


def render_disputes(panel: dict[str, Any]) -> None:
    critique = panel.get("critique") or {}
    arbitration = panel.get("arbitration") or {}
    disagreements = safe_list(critique.get("disagreements"))
    st.subheader("Where the models disagreed")
    if not disagreements:
        st.info("No material disagreement was returned.")
    for disagreement in disagreements:
        if not isinstance(disagreement, dict):
            continue
        topic = item_text(disagreement, "topic", "Disagreement")
        materiality = item_text(disagreement, "materiality", "unclear")
        with st.expander(f"{topic} — {materiality} materiality", expanded=True):
            left, right = st.columns(2)
            with left:
                st.caption("First analyst")
                st.write(item_text(disagreement, "firstPosition", "Not returned."))
            with right:
                st.caption("Independent reviewer")
                st.write(item_text(disagreement, "reviewerPosition", "Not returned."))
            st.write("**Why:**", item_text(disagreement, "reason", "Not returned."))
            st.write(
                "**Evidence that may resolve it:**",
                item_text(disagreement, "evidenceThatWouldResolve", "Not returned."),
            )

    st.subheader("Senior resolutions")
    for resolution in safe_list(arbitration.get("resolvedDisputes")):
        if not isinstance(resolution, dict):
            continue
        with st.container(border=True):
            st.markdown(f"**{item_text(resolution, 'topic')}**")
            st.write(item_text(resolution, "resolution"))
            st.caption(
                f"{item_text(resolution, 'reason')} · Confidence: {item_text(resolution, 'confidence', 'unclear')}"
            )

    unsupported = safe_list(critique.get("unsupportedClaims"))
    if unsupported:
        st.subheader("Unsupported claims caught")
        for claim in unsupported:
            if isinstance(claim, dict):
                st.error(
                    f"{item_text(claim, 'claim')} — {item_text(claim, 'problem')} "
                    f"Correction: {item_text(claim, 'correction')}"
                )

    st.subheader("Questions no model should guess")
    for question in safe_list(arbitration.get("unresolvedQuestions")):
        if isinstance(question, dict):
            st.warning(
                f"{item_text(question, 'question')}\n\nNeeded: {item_text(question, 'neededEvidence')}\n\n"
                f"Why it matters: {item_text(question, 'consequence')}"
            )


def render_evidence(panel: dict[str, Any]) -> None:
    first = panel.get("first") or {}
    independent = panel.get("independent") or {}
    arbitration = panel.get("arbitration") or {}
    missing = dedupe(
        safe_list(first.get("missingFacts")) + safe_list(independent.get("missingFacts")),
        "question",
    )
    evidence = dedupe(
        safe_list(first.get("evidenceChecklist"))
        + safe_list(independent.get("evidenceChecklist")),
        "item",
    )

    st.subheader("Questions to answer")
    for item in missing:
        with st.container(border=True):
            st.markdown(
                f"**{item_text(item, 'question')}** · priority: {item_text(item, 'priority', 'unclear')}"
            )
            st.caption(item_text(item, "whyItMatters"))

    st.subheader("Evidence preservation checklist")
    panel_id = str(panel.get("generatedAt") or "panel")
    for index, item in enumerate(evidence):
        marker = hashlib.sha256(
            f"{panel_id}:{index}:{item_text(item, 'item')}".encode("utf-8")
        ).hexdigest()[:12]
        st.checkbox(item_text(item, "item", "Evidence item"), key=f"evidence_{marker}")
        details = " · ".join(
            value
            for value in [item_text(item, "reason"), item_text(item, "howToPreserve")]
            if value
        )
        if details:
            st.caption(details)

    sources: list[dict[str, Any]] = []
    for analysis in (first, independent):
        for issue in safe_list(analysis.get("issues")):
            if isinstance(issue, dict):
                sources.extend(safe_list(issue.get("sources")))
    sources = dedupe(sources, "url")
    st.subheader("Sources surfaced — verify with counsel")
    for source in sources:
        title = item_text(source, "title", "Source")
        url = item_text(source, "url")
        status = item_text(source, "status", "needs-verification")
        if valid_web_url(url):
            st.link_button(f"{title} ({status})", url)
        else:
            st.write(f"{title} — invalid or missing URL — {status}")

    triggers = safe_list(arbitration.get("lawyerEscalationTriggers"))
    if triggers:
        st.subheader("Get qualified help promptly if...")
        for trigger in triggers:
            st.error(str(trigger))


def render_documents(panel: dict[str, Any], case_data: dict[str, Any], config: ProviderConfig) -> None:
    arbitration = panel.get("arbitration") or {}
    plan = safe_list(arbitration.get("documentPlan"))
    st.subheader("Recommended document set")
    for item in plan:
        if not isinstance(item, dict):
            continue
        with st.container(border=True):
            st.markdown(
                f"**{item_text(item, 'document', 'Document')} → {item_text(item, 'recipient', 'Recipient to confirm')}**"
            )
            st.write(item_text(item, "purpose"))
            st.caption("Inputs needed: " + ", ".join(map(str, safe_list(item.get("inputsNeeded")))))

    standard_types = [
        "Incident and benefits notification",
        "Medical payment guarantee request",
        "Evidence preservation request",
        "On-board complaint",
        "Claim chronology",
    ]
    document_types = []
    for item in plan:
        if isinstance(item, dict) and item_text(item, "document"):
            document_types.append(item_text(item, "document"))
    document_types = list(dict.fromkeys(document_types + standard_types))

    st.subheader("Create a careful first draft")
    with st.form("document_form", border=True):
        document_type = st.selectbox("Document type", document_types)
        recipient = st.text_input(
            "Recipient", placeholder="Company, shipowner, insurer, P&I correspondent, authority..."
        )
        language = st.selectbox("Language", ["English", "Romanian"])
        extra = st.text_area(
            "Extra drafting instructions",
            placeholder="Optional preferences only. Do not paste new sensitive facts here unless necessary.",
        )
        make_draft = st.form_submit_button(
            "Create reviewed draft", type="primary", use_container_width=True
        )

    if make_draft:
        try:
            with st.status("OpenAI is drafting from the arbitrated record...", expanded=True) as status:
                draft = draft_document(
                    case_data,
                    panel,
                    config,
                    document_type=document_type,
                    recipient=recipient,
                    language=language,
                    extra_instructions=extra,
                )
                status.update(label="Draft complete", state="complete", expanded=False)
            st.session_state.draft = draft
        except AppError as exc:
            st.error(str(exc))
        except Exception:
            st.error("The draft could not be completed because of an unexpected server error.")

    draft = st.session_state.get("draft")
    if not isinstance(draft, dict):
        return
    title = str(draft.get("title") or "Legal draft")
    st.markdown(f"### {title}")
    draft_text = st.text_area(
        "Draft text — editable",
        value=str(draft.get("documentText") or ""),
        height=520,
        key=f"draft_text_{hashlib.sha256(title.encode('utf-8')).hexdigest()[:10]}",
    )
    st.download_button(
        "Download draft as .txt",
        draft_text,
        file_name=f"{slug(title)}.txt",
        mime="text/plain",
    )
    attachments = safe_list(draft.get("attachmentsChecklist"))
    fields = safe_list(draft.get("fieldsToConfirm"))
    if attachments:
        st.write("**Attachments checklist:**", ", ".join(map(str, attachments)))
    if fields:
        st.write("**Confirm before use:**", ", ".join(map(str, fields)))
    st.warning(
        str(draft.get("reviewWarning") or "Have a qualified adviser review this draft before use.")
    )


def render_followup(panel: dict[str, Any], case_data: dict[str, Any], config: ProviderConfig) -> None:
    st.subheader("Discuss the next required steps")
    st.caption(
        "Answers use the arbitrated record. They cannot verify new law, deadlines, medical facts, or documents."
    )
    history = st.session_state.setdefault("discussion", [])
    for turn in history:
        if not isinstance(turn, dict):
            continue
        with st.chat_message("user"):
            st.write(str(turn.get("question") or ""))
        response = turn.get("response") or {}
        with st.chat_message("assistant"):
            st.write(str(response.get("answer") or "No answer returned."))
            actions = safe_list(response.get("nextActions"))
            if actions:
                st.write("**Suggested sequence**")
                for action in actions:
                    if isinstance(action, dict):
                        st.write(
                            f"- {item_text(action, 'action')} — {item_text(action, 'owner')} — {item_text(action, 'timing')}"
                        )
            unknowns = safe_list(response.get("unknowns"))
            if unknowns:
                st.caption("Still unknown: " + ", ".join(map(str, unknowns)))
            if response.get("reviewWarning"):
                st.warning(str(response["reviewWarning"]))

    with st.form("followup_form", border=True):
        question = st.text_area(
            "Your question",
            placeholder="For example: What should we request from the company today?",
            height=90,
        )
        asked = st.form_submit_button("Ask about next steps", type="primary")
    if asked:
        try:
            with st.spinner("Reviewing the arbitrated record..."):
                response = answer_followup(
                    case_data,
                    panel,
                    config,
                    question=question,
                    history=history,
                )
            history.append({"question": question.strip(), "response": response})
            st.rerun()
        except AppError as exc:
            st.error(str(exc))
        except Exception:
            st.error("The follow-up could not be completed because of an unexpected server error.")

    if history and st.button("Clear discussion"):
        st.session_state.discussion = []
        st.rerun()


def render_results(config: ProviderConfig) -> None:
    panel = st.session_state.get("panel")
    case_data = st.session_state.get("submitted_case")
    if not isinstance(panel, dict) or not isinstance(case_data, dict):
        st.markdown(
            """
            <div class="case-empty">
              <div style="font-size:2rem">✦</div>
              <h3>Your review will appear here</h3>
              <p>The panel will separate facts from assumptions, compare legal views,
              identify missing evidence, and propose careful documents.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.subheader("Arbitrated case review")
    tabs = st.tabs(["Overview", "Disputes", "Evidence", "Documents", "Ask next steps"])
    with tabs[0]:
        render_overview(panel)
    with tabs[1]:
        render_disputes(panel)
    with tabs[2]:
        render_evidence(panel)
    with tabs[3]:
        render_documents(panel, case_data, config)
    with tabs[4]:
        render_followup(panel, case_data, config)


def main() -> None:
    require_shared_password()
    config = build_config()
    st.markdown(STATIC_CSS, unsafe_allow_html=True)
    render_sidebar(config)
    render_header()
    if not PUBLIC_DEMO_ONLY and not config.demo_mode and not str(get_setting("APP_PASSWORD", "") or ""):
        st.error(
            "Live mode has no APP_PASSWORD configured. Do not expose this app to the internet. "
            "Use private authentication and a controlled self-hosted deployment for real cases."
        )
    intake, results = st.columns([0.92, 1.08], gap="large")
    with intake:
        render_intake(config)
    with results:
        render_results(config)
    st.divider()
    st.caption(
        "Mariner Advocate is decision support, not legal representation. No database is included. "
        "Review provider retention and data-processing terms before live use."
    )


if __name__ == "__main__":
    main()
