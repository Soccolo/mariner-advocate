const form = document.querySelector("#caseForm");
const analyzeButton = document.querySelector("#analyzeButton");
const exportButton = document.querySelector("#exportButton");
const retryButton = document.querySelector("#retryButton");
const saveStatus = document.querySelector("#saveStatus");
const providerSummary = document.querySelector("#providerSummary");
const emptyState = document.querySelector("#emptyState");
const loadingState = document.querySelector("#loadingState");
const errorState = document.querySelector("#errorState");
const errorMessage = document.querySelector("#errorMessage");
const results = document.querySelector("#results");
const resultContent = document.querySelector("#resultContent");
const confidenceBadge = document.querySelector("#confidenceBadge");
const progressBar = document.querySelector("#progressBar");
const loadingTitle = document.querySelector("#loadingTitle");
const loadingText = document.querySelector("#loadingText");

const STORAGE_KEY = "mariner-advocate-case-v1";
let panel = null;
let activeTab = "overview";
let saveTimer;
let progressTimer;

restoreCase();
checkStatus();

form.addEventListener("input", () => {
  saveStatus.textContent = "Saving…";
  saveStatus.classList.add("saving");
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(getCaseData()));
    saveStatus.textContent = "Saved locally";
    saveStatus.classList.remove("saving");
  }, 350);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  await runAnalysis();
});

retryButton.addEventListener("click", runAnalysis);
exportButton.addEventListener("click", () => {
  const bundle = { exportedAt: new Date().toISOString(), caseData: getCaseData(), panel };
  download(`mariner-advocate-case-${dateStamp()}.json`, JSON.stringify(bundle, null, 2), "application/json");
});

document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
  activeTab = tab.dataset.tab;
  document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === tab));
  renderPanel();
}));

async function checkStatus() {
  try {
    const status = await api("/api/status");
    if (status.demoMode) {
      providerSummary.textContent = "Demo mode · no external API calls";
      providerSummary.style.color = "#b06b27";
      return;
    }
    const configured = Object.entries(status.providers).filter(([, value]) => value.configured).map(([name]) => name);
    providerSummary.textContent = configured.length === 3 ? "All 3 providers configured" : `${configured.length}/3 providers configured · check .env`;
    if (configured.length !== 3) providerSummary.style.color = "#c7563d";
  } catch {
    providerSummary.textContent = "Server status unavailable";
  }
}

async function runAnalysis() {
  setView("loading");
  analyzeButton.disabled = true;
  startProgress();
  try {
    panel = await api("/api/analyze", { method: "POST", body: JSON.stringify({ caseData: getCaseData() }) });
    progressBar.style.width = "100%";
    await delay(350);
    activeTab = "overview";
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === activeTab));
    renderPanel();
    setView("results");
    document.querySelector("#resultsPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    errorMessage.textContent = error.message;
    setView("error");
  } finally {
    clearInterval(progressTimer);
    analyzeButton.disabled = false;
  }
}

function startProgress() {
  let value = 8;
  progressBar.style.width = `${value}%`;
  document.querySelectorAll(".stage").forEach((stage, index) => stage.classList.toggle("active", index === 0));
  progressTimer = setInterval(() => {
    value = Math.min(91, value + (value < 45 ? 5 : value < 72 ? 2 : .7));
    progressBar.style.width = `${value}%`;
    if (value > 42) {
      loadingTitle.textContent = "The reviewer is mapping disagreements";
      loadingText.textContent = "Claims, assumptions and missing evidence are being compared.";
      document.querySelector('[data-stage="1"]').classList.remove("active");
      document.querySelector('[data-stage="2"]').classList.add("active");
    }
    if (value > 72) {
      loadingTitle.textContent = "The senior model is arbitrating";
      loadingText.textContent = "Only supported disputes will be resolved; remaining gaps stay visible.";
      document.querySelector('[data-stage="2"]').classList.remove("active");
      document.querySelector('[data-stage="3"]').classList.add("active");
    }
  }, 1500);
}

function setView(view) {
  emptyState.classList.toggle("hidden", view !== "empty");
  loadingState.classList.toggle("hidden", view !== "loading");
  results.classList.toggle("hidden", view !== "results");
  errorState.classList.toggle("hidden", view !== "error");
}

function renderPanel() {
  if (!panel) return;
  confidenceBadge.textContent = `Confidence: ${panel.arbitration?.overallConfidence || "unclear"}`;
  const renderers = { overview: renderOverview, disputes: renderDisputes, evidence: renderEvidence, documents: renderDocuments };
  resultContent.innerHTML = renderers[activeTab]();
  bindDynamicActions();
}

function renderOverview() {
  const a = panel.arbitration || {};
  return `
    <div class="summary-card"><div class="card-label">Senior synthesis</div><p>${e(a.executiveSummary || "No summary returned.")}</p></div>
    <div class="result-card">
      <div class="card-label">Priority sequence</div><h3>What to do next</h3>
      <ol class="action-list">${items(a.recommendedActions, (item, index) => `<li><span class="order">${e(item.order || index + 1)}</span><div><strong>${e(item.action)}</strong><small>${e(joinParts(item.purpose, item.owner && `Owner: ${item.owner}`, item.timing && `Timing: ${item.timing}`))}</small></div></li>`)}</ol>
    </div>
    <div class="result-card">
      <div class="card-label">Provisional only</div><h3>Possible rights and claims</h3>
      <div class="rights-grid">${items(a.provisionalRights, (item) => `<div class="right-item"><strong>${e(item.rightOrClaim)}</strong><span>${e(item.basis)}</span><span class="status-tag">${e(item.status)}</span><span>${e(item.verification)}</span></div>`)}</div>
    </div>
    ${a.doNotDoYet?.length ? `<div class="result-card danger-card"><div class="card-label">Protect the claim</div><h3>Do not do these yet</h3><ul class="clean-list">${items(a.doNotDoYet, (item) => `<li><strong>${e(item.action)}</strong><small>${e(item.reason)}</small></li>`)}</ul></div>` : ""}
    <div class="method-note">${e(panel.workflow?.anchoringControl)} Generated ${formatDate(panel.generatedAt)}. This output is decision support, not legal representation.</div>`;
}

function renderDisputes() {
  const critique = panel.critique || {};
  const a = panel.arbitration || {};
  return `
    <div class="result-card"><div class="card-label">Cross-review</div><h3>Where the models disagreed</h3>
      ${items(critique.disagreements, (item) => `<div class="result-card dispute ${e(item.materiality)}"><strong>${e(item.topic)}</strong><div class="split-view"><div class="view"><span>First analyst</span><p>${e(item.firstPosition)}</p></div><div class="view"><span>Independent reviewer</span><p>${e(item.reviewerPosition)}</p></div></div><p><b>Why:</b> ${e(item.reason)}</p><p><b>What could resolve it:</b> ${e(item.evidenceThatWouldResolve)}</p></div>`) || "<p>No material disagreements were returned.</p>"}
    </div>
    <div class="result-card"><div class="card-label">Arbitration</div><h3>Senior resolutions</h3><ul class="clean-list">${items(a.resolvedDisputes, (item) => `<li><strong>${e(item.topic)} — ${e(item.resolution)}</strong><small>${e(item.reason)} · Confidence: ${e(item.confidence)}</small></li>`)}</ul></div>
    <div class="result-card warning-card"><div class="card-label">Still open</div><h3>Questions no AI should guess</h3><ul class="clean-list">${items(a.unresolvedQuestions, (item) => `<li><strong>${e(item.question)}</strong><small>Needed: ${e(item.neededEvidence)} · Why it matters: ${e(item.consequence)}</small></li>`)}</ul></div>
    ${critique.unsupportedClaims?.length ? `<div class="result-card danger-card"><div class="card-label">Quality control</div><h3>Unsupported claims caught</h3><ul class="clean-list">${items(critique.unsupportedClaims, (item) => `<li><strong>${e(item.claim)}</strong><small>${e(item.problem)} Correction: ${e(item.correction)}</small></li>`)}</ul></div>` : ""}`;
}

function renderEvidence() {
  const a = panel.arbitration || {};
  const first = panel.first || {};
  const missing = dedupe([...(first.missingFacts || []), ...(panel.independent?.missingFacts || [])], (item) => item.question);
  const evidence = dedupe([...(first.evidenceChecklist || []), ...(panel.independent?.evidenceChecklist || [])], (item) => item.item);
  const sources = dedupe([...(first.issues || []), ...(panel.independent?.issues || [])].flatMap((issue) => issue.sources || []), (item) => item.url);
  return `
    <div class="result-card"><div class="card-label">Missing facts</div><h3>Questions to answer</h3><ul class="clean-list">${items(missing, (item) => `<li><strong>${e(item.question)} <span class="status-tag">${e(item.priority)}</span></strong><small>${e(item.whyItMatters)}</small></li>`)}</ul></div>
    <div class="result-card"><div class="card-label">Preservation</div><h3>Evidence checklist</h3><ul class="clean-list">${items(evidence, (item) => `<li><strong>□ ${e(item.item)}</strong><small>${e(item.reason)} ${item.howToPreserve ? `· ${e(item.howToPreserve)}` : ""}</small></li>`)}</ul></div>
    <div class="result-card"><div class="card-label">Sources surfaced</div><h3>Verify with counsel</h3><ul class="clean-list">${items(sources, (item) => `<li><strong>${e(item.title)}</strong><small><a class="source-link" href="${safeUrl(item.url)}" target="_blank" rel="noreferrer">${e(item.url)}</a> · ${e(item.status)}</small></li>`) || "<li>No source links returned.</li>"}</ul></div>
    <div class="result-card warning-card"><div class="card-label">Escalate</div><h3>Get qualified help promptly if…</h3><ul class="clean-list">${items(a.lawyerEscalationTriggers, (item) => `<li><strong>${e(item)}</strong></li>`)}</ul></div>`;
}

function renderDocuments() {
  const plan = panel.arbitration?.documentPlan || [];
  return `
    <div class="result-card"><div class="card-label">Recommended set</div><h3>Document plan</h3><ul class="clean-list">${items(plan, (item) => `<li><strong>${e(item.document)} → ${e(item.recipient)}</strong><small>${e(item.purpose)} · Needs: ${e((item.inputsNeeded || []).join(", "))}</small></li>`)}</ul></div>
    <div class="result-card">
      <div class="card-label">Careful first draft</div><h3>Draft a document</h3>
      <div class="draft-controls">
        <select id="documentType" aria-label="Document type">
          ${plan.map((item) => `<option value="${attr(item.document)}">${e(item.document)}</option>`).join("")}
          <option>Incident and benefits notification</option><option>Medical payment guarantee request</option><option>Evidence preservation request</option><option>On-board complaint</option><option>Claim chronology</option>
        </select>
        <input id="documentRecipient" placeholder="Recipient (company, insurer, flag authority…)" aria-label="Recipient">
        <select id="documentLanguage" aria-label="Language"><option>English</option><option>Romanian</option></select>
        <button class="primary-button" id="draftButton" type="button">Create reviewed draft <span>→</span></button>
      </div>
      <div class="draft-output hidden" id="draftOutput"></div>
    </div>`;
}

function bindDynamicActions() {
  const draftButton = document.querySelector("#draftButton");
  if (!draftButton) return;
  draftButton.addEventListener("click", async () => {
    const output = document.querySelector("#draftOutput");
    draftButton.disabled = true;
    output.classList.remove("hidden");
    output.innerHTML = "<p>Drafting carefully…</p>";
    try {
      const draft = await api("/api/draft", { method: "POST", body: JSON.stringify({
        caseData: getCaseData(), panel,
        documentType: document.querySelector("#documentType").value,
        recipient: document.querySelector("#documentRecipient").value,
        language: document.querySelector("#documentLanguage").value,
      }) });
      output.innerHTML = `<div class="draft-text">${e(draft.documentText)}</div><p><b>Confirm before use:</b> ${e((draft.fieldsToConfirm || []).join(", "))}</p><p>${e(draft.reviewWarning)}</p><div class="button-row"><button class="small-button" id="copyDraft" type="button">Copy text</button><button class="small-button" id="downloadDraft" type="button">Download .txt</button></div>`;
      document.querySelector("#copyDraft").addEventListener("click", () => navigator.clipboard.writeText(draft.documentText));
      document.querySelector("#downloadDraft").addEventListener("click", () => download(`${slug(draft.title || "legal-draft")}.txt`, draft.documentText, "text/plain"));
    } catch (error) {
      output.innerHTML = `<p>${e(error.message)}</p>`;
    } finally { draftButton.disabled = false; }
  });
}

function getCaseData() { return Object.fromEntries(new FormData(form).entries()); }
function restoreCase() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    for (const [name, value] of Object.entries(saved)) if (form.elements[name]) form.elements[name].value = value;
  } catch { /* Ignore malformed local state. */ }
}

async function api(url, options = {}) {
  const response = await fetch(url, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function items(list, render) { return Array.isArray(list) ? list.map(render).join("") : ""; }
function dedupe(list, keyFn) { const seen = new Set(); return list.filter((item) => { const key = keyFn(item); if (!key || seen.has(key)) return false; seen.add(key); return true; }); }
function joinParts(...parts) { return parts.filter(Boolean).join(" · "); }
function e(value) { return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]); }
function attr(value) { return e(value); }
function safeUrl(value) { try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) ? e(url.href) : "#"; } catch { return "#"; } }
function delay(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }
function dateStamp() { return new Date().toISOString().slice(0, 10); }
function formatDate(value) { try { return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); } catch { return ""; } }
function slug(value) { return String(value).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 70); }
function download(name, content, type) { const url = URL.createObjectURL(new Blob([content], { type })); const anchor = document.createElement("a"); anchor.href = url; anchor.download = name; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
