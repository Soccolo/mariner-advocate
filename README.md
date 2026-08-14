# Mariner Advocate

Mariner Advocate is a Streamlit application for contract-assisted case intake,
multi-model legal issue-spotting, independent review, senior arbitration, next-step
discussion, and careful document drafting. It is initially tailored to injured seafarers.

## Critical privacy boundary

**Do not use Streamlit Community Cloud for a real family case or any health, legal,
employment, or other sensitive personal information.** Community Cloud is suitable
only for a fictional-data product demonstration. Its deployment terms are not a fit
for this app's intended real-world data.

For real cases, use a controlled private deployment after obtaining appropriate
security and privacy review. At minimum, use TLS, proper identity-aware access
control, restricted network access, safe logging, secrets management, monitoring,
and an agreed retention/deletion policy. Review each AI provider's data-processing
and retention terms before sending case facts. The included `APP_PASSWORD` is only a
basic shared gate; it is not a substitute for production authentication.
Live mode fails closed before case intake when `APP_PASSWORD` is missing.

This project has no database. Case details and results live in a Streamlit session
until that session ends, but live requests send the submitted facts to Z.AI,
Anthropic, and OpenAI. A downloaded PDF contains the case facts and the panel's
conclusions in one file, so treat it as sensitive: it is exactly what a lawyer or
union needs, and exactly what should not be left on a shared machine or emailed
unencrypted. If the user explicitly runs contract import, locally extracted
contract text is sent to OpenAI to populate contract-related intake fields.

## Review workflow

1. An optional PDF, DOCX, or TXT contract importer extracts text locally and asks
   OpenAI to populate only vessel, employment, and relevant contract-term fields.
2. Z.AI performs the first independent analysis.
3. Claude forms a separate view concurrently, without seeing the first answer.
4. After committing its view, Claude compares both analyses and identifies
   disagreements, omissions, and unsupported claims.
5. OpenAI acts as senior arbiter in high-reasoning pro mode, resolving only supported
   disputes and leaving genuine uncertainty visible.
6. OpenAI can draft a notification, payment request, evidence-preservation request,
   complaint, or chronology from the arbitrated record.
7. A follow-up workspace discusses the next required steps using that same record.
8. The review and any draft can be downloaded as PDFs to print, keep, or hand to a
   lawyer or union representative.

## Downloads

| Download | Where | Contents |
|---|---|---|
| Case review (PDF) | Sidebar and the **Overview** tab | Coverage notes, executive summary, next steps, possible rights, disputes, questions to answer, evidence checklist, sources, each model's analysis, the follow-up discussion, and the case as submitted |
| Draft (PDF or .txt) | **Documents** tab | The draft as currently edited on screen, plus its attachment and confirmation checklists |
| Full record (JSON) | Sidebar | The complete panel structure for archiving or re-import |

PDFs are generated locally with `fpdf2`; nothing is uploaded to produce them. Every
page repeats that the document is decision support rather than legal advice, and a
reduced-coverage review says so on the page, so a printed copy cannot hide that a
stage failed or was cut short. Text is drawn with the DejaVu face bundled in
`assets/` — the PDF core fonts cannot represent Romanian s-comma or t-comma, so a
core-font export would silently corrupt drafted wording. The font is redistributed
under the Bitstream Vera licence in `assets/LICENSE-DejaVu.txt`.

Provider stages are isolated. If Z.AI or either Claude stage fails or returns invalid
JSON, successful stages are preserved. When at least one independent analysis exists,
OpenAI still performs a confidence-limited synthesis. If neither independent analysis
completes, arbitration and downstream document actions are safely skipped. If OpenAI
arbitration fails, completed Z.AI and Claude analyses remain available in the
**Analyses** tab, while drafting and follow-up stay disabled. A malformed Z.AI response
is retried once with the same model, JSON mode, a larger output allowance, and hidden
thinking disabled.

### Reasoning models share one output allowance

Both `claude-opus-5` and `glm-5.3` reason before answering, and that reasoning is
billed from the same output allowance as the final JSON. If the allowance runs out
mid-answer, the model returns a partial document, so the budgets default to 32,000
tokens rather than the answer-sized budget a non-reasoning model would need.

- Claude requests stream, ask for the analysis shape as a **structured output**, and
  set `thinking` and `effort` explicitly. If a model or account does not accept the
  structured-output or effort fields, the request is retried without them instead of
  failing the stage.
- OpenAI arbitration streams for the same reason: it runs at high reasoning effort in
  pro mode, and a single non-streaming request has to finish inside one HTTP timeout
  while a stream only has to keep sending. Pro mode and the verbosity control are
  dropped one at a time if a model or account rejects them, and a deployment that
  blocks streamed responses falls back to a single request rather than losing the
  synthesis. If arbitration keeps timing out, raise `REQUEST_TIMEOUT_SECONDS`
  (maximum 900) before lowering reasoning effort.
- When a model still stops mid-answer, the complete leading part of its response is
  recovered and used. Cuts are only made at separators outside strings, so every value
  kept is one the model finished writing, and anything it was part-way through is
  dropped rather than guessed. The stage is flagged as partial in the **Analyses**
  tab, listed under **Provider status details**, marked in the arbiter's input, and
  the panel reports reduced coverage.
- Failures record the provider's machine-readable error code, HTTP status, and finish
  reason so a misconfigured model ID or exhausted budget is visible in the app. Only
  these enum-like codes are stored, never free-form provider text, because a provider
  can echo submitted case facts back inside an error message and the failure record is
  replayed into later provider prompts.

Contract import accepts files up to 10 MB and rejects encrypted, scanned/no-text,
macro-enabled, malformed, or excessively large documents. Existing case values are
preserved by default, and all imported values remain editable before panel analysis.
The upload control is not rendered when `PUBLIC_DEMO_ONLY=true`.

API keys are read only from Streamlit secrets or server environment variables. They
are never entered in the web page, returned to the browser, or included in exports.

## Run locally with fictional demo data

Python 3.11 or newer is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DEMO_MODE='true'
streamlit run streamlit_app.py
```

Demo mode makes no provider calls and needs no API keys.

## Run a live panel in a controlled local environment

Set the keys in the process environment:

```powershell
$env:OPENAI_API_KEY='...'
$env:ANTHROPIC_API_KEY='...'
$env:ZAI_API_KEY='...'
$env:APP_PASSWORD='use-a-long-random-value'
streamlit run streamlit_app.py
```

Alternatively, copy `.streamlit/secrets.toml.example` to
`.streamlit/secrets.toml`, add the values, and keep that file uncommitted. The
`.gitignore` already excludes it.

A live panel needs at least two provider keys. Missing stages are shown explicitly;
full three-model coverage is recommended for the intended review architecture.

Supported settings:

| Setting | Default | Purpose |
|---|---:|---|
| `OPENAI_API_KEY` | none | OpenAI contract extraction, arbitration, drafting, and follow-up |
| `ANTHROPIC_API_KEY` | none | Blind review and comparison |
| `ZAI_API_KEY` | none | First analysis |
| `OPENAI_MODEL` | `gpt-5.6-sol` | OpenAI model ID |
| `ANTHROPIC_MODEL` | `claude-opus-5` | Anthropic model ID |
| `ZAI_MODEL` | `glm-5.3` | Z.AI model ID |
| `ANTHROPIC_MAX_TOKENS` | `32000` | Claude output allowance, covering thinking and the answer (4,000-128,000) |
| `ANTHROPIC_EFFORT` | `high` | Claude reasoning depth: `low`, `medium`, `high`, `xhigh`, or `max` |
| `ZAI_MAX_TOKENS` | `32000` | Z.AI output allowance, covering reasoning and the answer (4,000-128,000) |
| `OPENAI_MAX_OUTPUT_TOKENS` | `32000` | OpenAI output allowance, covering reasoning and the answer (4,000-128,000) |
| `APP_PASSWORD` | none | Basic shared-password gate |
| `DEMO_MODE` | `false` | Use deterministic fake responses and no APIs |
| `PUBLIC_DEMO_ONLY` | `false` | Force demo mode and require fictional-data acknowledgment |
| `REQUEST_TIMEOUT_SECONDS` | `420` | Provider request timeout, bounded to 60-900 seconds |

The defaults use Anthropic's `claude-opus-5` and Z.AI's `glm-5.3` model IDs. Provider
model availability is account-specific, so `ZAI_MODEL` must match an exact model ID
enabled in the connected Z.AI account.

OpenAI's official model documentation identifies `gpt-5.6-sol` as the frontier model
for complex work and documents `reasoning.mode: "pro"` on the Responses API:

- <https://developers.openai.com/api/docs/models>
- <https://developers.openai.com/api/docs/guides/latest-model>

## Private self-hosting with Docker

Build the image:

```powershell
docker build -t mariner-advocate .
```

Run it on a private machine or private container platform:

```powershell
docker run --rm --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m `
  -p 127.0.0.1:8501:8501 `
  -e OPENAI_API_KEY `
  -e ANTHROPIC_API_KEY `
  -e ZAI_API_KEY `
  -e APP_PASSWORD `
  mariner-advocate
```

Binding to `127.0.0.1` keeps the container local. If remote access is needed, place
it behind a reviewed TLS reverse proxy or identity-aware access gateway. Do not
publish port 8501 directly to the internet for real cases.

The Docker image includes a Streamlit health check at `/_stcore/health`. Do not bake
secrets into the image or commit them to GitHub.

## Streamlit Community Cloud: fictional demo only

To show the user interface with fake data:

1. Push this directory to a GitHub repository.
2. In Streamlit Community Cloud, choose `streamlit_app.py` as the entry point.
3. Add only these Advanced Settings secrets:

```toml
DEMO_MODE = true
PUBLIC_DEMO_ONLY = true
```

4. Do not add provider keys and do not enter real case facts.

The app will display a public-demo warning, force deterministic demo responses, and
require confirmation that all submitted data is fictional.

## Immediate source foundation

- [ILO Maritime Labour Convention, Title 4](https://normlex.ilo.org/dyn/nrmlx_en/f?p=NORMLEXPUB:91:0::NO::P91_SECTION:MLCA_AMEND_A4)
- [ILO MLC on-board complaint procedures](https://normlex.ilo.org/dyn/nrmlx_en/f?p=NORMLEXPUB:91:0::NO::P91_SECTION:MLCA_AMEND_A5)
- [ILO 2026 MLC FAQ](https://www.ilo.org/publications/frequently-asked-questions-about-maritime-labour-convention-mlc-2006)
- [Romanian National Public Pension House: invalidity pension after workplace accident](https://www.cnpp.ro/-/in-caz-de-accident-de-munca-sau-boala-profesionala-pot-beneficia-de-pensie-de-invaliditate-)

These are starting sources, not a live citator. The ship's flag, SEA, CBA,
insurance/financial-security certificate, accident location, employment structure,
and applicable law can materially change the answer.

## Important limitations

- This is an MVP, not a law firm, lawyer, medical service, claims handler, or secure
  production records system.
- No model may determine governing law from nationality alone.
- Do not sign a release, settlement, medical declaration, resignation, or waiver
  without qualified review.
- Have a qualified maritime lawyer, seafarers' union representative, or competent
  authority review any draft before it is sent or signed.
- Before production use, add strong authentication, authorization, encrypted
  storage if needed, retention controls, redacted audit logging, rate limiting,
  abuse controls, jurisdiction-aware retrieval, file scanning, and systematic legal
  quality and privacy evaluations.

## Validation

```powershell
python -m py_compile mariner_core.py streamlit_app.py
python -m unittest discover -s tests -v
$env:DEMO_MODE='true'
python -c "from mariner_core import ProviderConfig, analyze_case; c={'situation':'A fictional seafarer fell on stairs during work and suffered a fracture.'}; print(analyze_case(c, ProviderConfig(demo_mode=True))['arbitration']['overallConfidence'])"
streamlit run streamlit_app.py --server.headless true
```

The original Node prototype remains in `server.mjs` and `public/`, but
`streamlit_app.py` is the deployment entry point. The prototype still carries the
original answer-sized output budgets and non-streaming requests, so it drops
reasoning-model responses that the Streamlit app now handles. Treat it as historical
reference, not a second supported entry point.
