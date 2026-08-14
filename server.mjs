import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
loadEnv(path.join(root, ".env"));

const PORT = Number(process.env.PORT || 3000);
const DEMO_MODE = /^(1|true|yes)$/i.test(process.env.DEMO_MODE || "");
const MAX_BODY_BYTES = 1_500_000;

const config = {
  openai: {
    key: process.env.OPENAI_API_KEY,
    model: process.env.OPENAI_MODEL || "gpt-5.6-sol",
  },
  anthropic: {
    key: process.env.ANTHROPIC_API_KEY,
    model: process.env.ANTHROPIC_MODEL || "claude-opus-4-8",
  },
  zai: {
    key: process.env.ZAI_API_KEY,
    model: process.env.ZAI_MODEL || "glm-5.1",
  },
};

const OFFICIAL_SOURCE_PACK = `
VERIFIED STARTING SOURCES (not a substitute for jurisdiction-specific verification):
1. ILO Maritime Labour Convention, 2006, as amended — Regulation 4.1 / Standard A4.1 (medical care): https://normlex.ilo.org/dyn/nrmlx_en/f?p=NORMLEXPUB:92:0::NO::P92_SECTION:MLC_A4
2. ILO MLC — Regulation 4.2 / Standards A4.2.1 and A4.2.2 (shipowners' liability and contractual claims): https://normlex.ilo.org/dyn/nrmlx_en/f?p=NORMLEXPUB:91:0::NO::P91_SECTION:MLCA_AMEND_A4
3. ILO MLC — Regulation 5.1.5 / Standard A5.1.5 (on-board complaints and protection against victimization): https://normlex.ilo.org/dyn/nrmlx_en/f?p=NORMLEXPUB:91:0::NO::P91_SECTION:MLCA_AMEND_A5
4. ILO MLC FAQ, 2026 edition: https://www.ilo.org/publications/frequently-asked-questions-about-maritime-labour-convention-mlc-2006
5. Romanian National Public Pension House — invalidity pension after workplace accident/occupational disease: https://www.cnpp.ro/-/in-caz-de-accident-de-munca-sau-boala-profesionala-pot-beneficia-de-pensie-de-invaliditate-

Do not present these sources as establishing the final governing law. The ship's flag-state implementation, SEA, CBA, insurer/P&I certificate, employment structure, accident facts, and relevant limitation periods must be checked. Never invent a statute, clause, deadline, contact, benefit amount, or source.
`;

const BASE_POLICY = `
You are assisting with legal issue-spotting for an injured seafarer. You are not the user's lawyer and must not claim to be one. This is high-stakes legal information.

Rules:
- Separate reported facts, assumptions, missing facts, legal rules, application, and conclusions.
- Use cautious language. Never treat nationality alone as deciding governing law.
- Identify urgent evidence-preservation and notification steps, but never invent a deadline.
- Cite only sources you can identify with a real URL or a precise document/clause supplied in the case.
- Label every proposition that needs current flag-state, contract, CBA, insurance, or local-law verification.
- Do not advise signing a release, settlement, medical declaration, resignation, or repatriation waiver without qualified review.
- Do not diagnose medically. Emergency care and treating clinicians take priority.
- Protect privacy: avoid repeating passport, banking, medical-record, or home-address details unless necessary.
- Return valid JSON only. No markdown fences.

${OFFICIAL_SOURCE_PACK}
`;

const ANALYSIS_SHAPE = `{
  "summary": "short neutral case summary",
  "urgentActions": [{"action":"", "why":"", "timing":"", "owner":""}],
  "factsReliedOn": [""],
  "assumptions": [""],
  "missingFacts": [{"question":"", "whyItMatters":"", "priority":"high|medium|low"}],
  "issues": [{"issue":"", "rule":"", "application":"", "provisionalConclusion":"", "confidence":"high|medium|low", "sources":[{"title":"", "url":"", "status":"verified-starting-source|needs-verification"}]}],
  "possibleEntitlements": [{"item":"", "basis":"", "againstWhom":"", "verificationNeeded":""}],
  "evidenceChecklist": [{"item":"", "reason":"", "howToPreserve":""}],
  "deadlineRisks": [{"risk":"", "action":"", "verifiedDeadline":null}],
  "nextSteps": [{"order":1, "step":"", "who":""}],
  "disclaimer": ""
}`;

function caseText(caseData) {
  const entries = Object.entries(caseData || {}).filter(([, value]) => String(value || "").trim());
  return entries.map(([key, value]) => `${key}: ${String(value).trim()}`).join("\n");
}

function analystPrompt(caseData) {
  return `${BASE_POLICY}\nYou are the FIRST ANALYST. Independently analyze the case. Focus on medical-cost responsibility, wages/sick pay, repatriation, occupational injury and disability compensation, reporting/complaint routes, evidence, and documents likely needed. Do not manufacture certainty.\n\nCASE:\n${caseText(caseData)}\n\nRequired JSON shape:\n${ANALYSIS_SHAPE}`;
}

function independentReviewerPrompt(caseData) {
  return `${BASE_POLICY}\nYou are the INDEPENDENT REVIEWER. You have not seen the first analyst's opinion. Form your own legal issue analysis now so you cannot be anchored by it. Focus on alternative governing-law routes, counterarguments, exclusions, missing evidence, and risks.\n\nCASE:\n${caseText(caseData)}\n\nRequired JSON shape:\n${ANALYSIS_SHAPE}`;
}

function critiquePrompt(caseData, first, independent) {
  return `${BASE_POLICY}\nYou are the REVIEWER. You already formed the independent view below. Now compare it with the first analyst. Identify concrete agreements, disagreements, unsupported claims, omissions, and corrections. Do not change your view merely to agree.\n\nCASE:\n${caseText(caseData)}\n\nFIRST ANALYST:\n${JSON.stringify(first)}\n\nYOUR PRECOMMITTED INDEPENDENT VIEW:\n${JSON.stringify(independent)}\n\nReturn JSON: {"agreements":[{"point":"","reason":""}],"disagreements":[{"topic":"","firstPosition":"","reviewerPosition":"","reason":"","materiality":"high|medium|low","evidenceThatWouldResolve":""}],"unsupportedClaims":[{"claim":"","problem":"","correction":""}],"omissions":[{"item":"","importance":""}],"questionsForArbiter":[""]}`;
}

function arbiterPrompt(caseData, first, independent, critique) {
  return `${BASE_POLICY}\nYou are the SENIOR ARBITER. Resolve only what the evidence and identified law support. For each dispute, state which view is better supported and why; if it cannot safely be resolved, say exactly what fact or authoritative source is needed. Produce an actionable synthesis suitable for later review by a qualified maritime lawyer.\n\nCASE:\n${caseText(caseData)}\n\nFIRST ANALYST:\n${JSON.stringify(first)}\n\nINDEPENDENT REVIEW:\n${JSON.stringify(independent)}\n\nCRITIQUE AND DISPUTES:\n${JSON.stringify(critique)}\n\nReturn JSON: {"executiveSummary":"","resolvedDisputes":[{"topic":"","resolution":"","reason":"","confidence":"high|medium|low"}],"unresolvedQuestions":[{"question":"","neededEvidence":"","consequence":""}],"provisionalRights":[{"rightOrClaim":"","basis":"","status":"likely|possible|unclear","verification":""}],"recommendedActions":[{"order":1,"action":"","purpose":"","owner":"","timing":""}],"documentPlan":[{"document":"","recipient":"","purpose":"","inputsNeeded":[""]}],"doNotDoYet":[{"action":"","reason":""}],"lawyerEscalationTriggers":[""],"overallConfidence":"high|medium|low","disclaimer":""}`;
}

async function callProvider(provider, prompt, { senior = false } = {}) {
  if (DEMO_MODE) return demoResponse(prompt);
  if (!config[provider]?.key) throw new AppError(400, `Missing ${provider} API key. Add it to .env or enable DEMO_MODE=true.`);
  if (provider === "openai") return callOpenAI(prompt, senior);
  if (provider === "anthropic") return callAnthropic(prompt);
  if (provider === "zai") return callZai(prompt);
  throw new AppError(400, `Unsupported provider: ${provider}`);
}

async function callOpenAI(prompt, senior) {
  const body = {
    model: config.openai.model,
    input: prompt,
    reasoning: senior ? { effort: "high", mode: "pro" } : { effort: "medium" },
    text: { verbosity: "medium" },
  };
  const data = await providerFetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${config.openai.key}` },
    body: JSON.stringify(body),
  }, "OpenAI");
  return parseModelJson(extractOpenAIText(data), "OpenAI");
}

async function callAnthropic(prompt) {
  const data = await providerFetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": config.anthropic.key,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({ model: config.anthropic.model, max_tokens: 10000, messages: [{ role: "user", content: prompt }] }),
  }, "Anthropic");
  const text = (data.content || []).filter((item) => item.type === "text").map((item) => item.text).join("\n");
  return parseModelJson(text, "Anthropic");
}

async function callZai(prompt) {
  const data = await providerFetch("https://api.z.ai/api/paas/v4/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${config.zai.key}` },
    body: JSON.stringify({
      model: config.zai.model,
      messages: [{ role: "user", content: prompt }],
      thinking: { type: "enabled" },
      max_tokens: 10000,
      temperature: 0.2,
    }),
  }, "Z.AI");
  return parseModelJson(data.choices?.[0]?.message?.content || "", "Z.AI");
}

async function providerFetch(url, options, label) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 240_000);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const raw = await response.text();
    let data;
    try { data = JSON.parse(raw); } catch { data = { raw }; }
    if (!response.ok) {
      const message = data?.error?.message || data?.message || raw.slice(0, 500) || `HTTP ${response.status}`;
      throw new AppError(502, `${label} request failed: ${message}`);
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new AppError(504, `${label} request timed out.`);
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function extractOpenAIText(data) {
  if (typeof data.output_text === "string") return data.output_text;
  return (data.output || []).flatMap((item) => item.content || []).filter((item) => item.type === "output_text").map((item) => item.text).join("\n");
}

function parseModelJson(text, label) {
  const cleaned = String(text || "").trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "");
  try { return JSON.parse(cleaned); } catch {
    const first = cleaned.indexOf("{");
    const last = cleaned.lastIndexOf("}");
    if (first >= 0 && last > first) {
      try { return JSON.parse(cleaned.slice(first, last + 1)); } catch { /* handled below */ }
    }
    throw new AppError(502, `${label} returned an unreadable response. Try again or use a different configured model.`);
  }
}

async function analyzeCase(caseData) {
  if (!caseData?.situation || String(caseData.situation).trim().length < 30) {
    throw new AppError(400, "Please describe the situation in at least a few sentences.");
  }
  const [first, independent] = await Promise.all([
    callProvider("zai", analystPrompt(caseData)),
    callProvider("anthropic", independentReviewerPrompt(caseData)),
  ]);
  const critique = await callProvider("anthropic", critiquePrompt(caseData, first, independent));
  const arbitration = await callProvider("openai", arbiterPrompt(caseData, first, independent, critique), { senior: true });
  return {
    generatedAt: new Date().toISOString(),
    workflow: {
      analyst: `Z.AI ${config.zai.model}`,
      reviewer: `Anthropic ${config.anthropic.model}`,
      arbiter: `OpenAI ${config.openai.model} (high reasoning, pro mode)`,
      anchoringControl: "The reviewer formed an independent view before seeing the first analysis.",
    },
    first,
    independent,
    critique,
    arbitration,
  };
}

async function draftDocument({ caseData, panel, documentType, recipient, language = "English", extraInstructions = "" }) {
  if (!panel?.arbitration) throw new AppError(400, "Run the panel analysis before drafting a document.");
  const prompt = `${BASE_POLICY}\nYou are a careful legal drafting assistant. Draft a ${documentType || "formal incident and benefit notification"} in ${language}. Recipient: ${recipient || "shipowner/employer and insurer"}. Use only facts in the case and panel record. Insert [TO CONFIRM] placeholders for missing facts. Do not overstate liability, waive rights, admit fault, or invent deadlines. Include a request for written acknowledgment, preservation of records, insurer/P&I and claims contact details, copies of incident and medical reports, payment/guarantee arrangements, and reservation of all rights where appropriate. Return JSON: {"title":"","documentText":"","attachmentsChecklist":[""],"fieldsToConfirm":[""],"reviewWarning":""}.\n\nCASE:\n${caseText(caseData)}\n\nARBITRATED PANEL:\n${JSON.stringify(panel.arbitration)}\n\nEXTRA INSTRUCTIONS:\n${extraInstructions}`;
  return callProvider("openai", prompt, { senior: true });
}

function demoResponse(prompt) {
  if (prompt.includes("SENIOR ARBITER")) return {
    executiveSummary: "The incident appears potentially work-related, but the governing flag-state law, SEA/CBA terms, and insurance certificate must be verified before any entitlement is stated conclusively.",
    resolvedDisputes: [{ topic: "Immediate medical costs", resolution: "Seek written payment/guarantee confirmation from the shipowner and insurer now.", reason: "MLC Regulation 4.2 is a strong starting point for injury during service, subject to implementation and facts.", confidence: "medium" }],
    unresolvedQuestions: [{ question: "What flag does the ship fly?", neededEvidence: "Registry/flag and Maritime Labour Certificate", consequence: "Determines national implementation and complaint authority." }],
    provisionalRights: [{ rightOrClaim: "Medical treatment and related costs", basis: "MLC Regulation 4.2 / SEA / CBA", status: "possible", verification: "Confirm service status, flag law, and insurance." }],
    recommendedActions: [{ order: 1, action: "Send a written incident and benefits notice", purpose: "Preserve the claim and obtain payment contacts", owner: "Family or representative", timing: "As soon as practicable" }],
    documentPlan: [{ document: "Incident and benefits notification", recipient: "Employer, shipowner, crewing agency and insurer/P&I correspondent", purpose: "Notify and request written arrangements", inputsNeeded: ["Ship name/IMO", "date/place", "medical summary"] }],
    doNotDoYet: [{ action: "Sign a release or final settlement", reason: "Long-term impairment may not yet be medically assessable." }],
    lawyerEscalationTriggers: ["Payment or surgery guarantee is refused", "Pressure to sign documents", "Disputed accident report", "Permanent impairment is suspected"],
    overallConfidence: "medium",
    disclaimer: "Demo output for product testing only; obtain qualified maritime legal advice."
  };
  if (prompt.includes("Now compare")) return {
    agreements: [{ point: "Flag, SEA/CBA, and insurer information are essential.", reason: "They affect governing rights and procedure." }],
    disagreements: [{ topic: "Certainty of disability compensation", firstPosition: "Potentially available", reviewerPosition: "Cannot yet quantify or confirm", reason: "Medical stabilization and contractual schedule are missing.", materiality: "high", evidenceThatWouldResolve: "CBA/SEA disability table and medical impairment assessment" }],
    unsupportedClaims: [], omissions: [{ item: "Preserve CCTV and weather records", importance: "May support causation and safety conditions." }], questionsForArbiter: ["Which notice should be sent first?"]
  };
  if (prompt.includes("legal drafting assistant")) return {
    title: "NOTICE OF SHIPBOARD ACCIDENT, MEDICAL TREATMENT AND RESERVATION OF RIGHTS",
    documentText: "To: [TO CONFIRM — employer/shipowner/insurer]\n\nWe notify you that [NAME — TO CONFIRM], serving as Chief Engineer aboard [SHIP/IMO — TO CONFIRM], suffered a fall on [DATE/TIME — TO CONFIRM] during service in conditions reported as heavy winds. He sustained a femur fracture and is receiving hospital treatment, with surgery planned or performed [TO CONFIRM].\n\nPlease confirm immediately in writing: (1) the arrangements and guarantee for all necessary medical treatment, medicines, accommodation and related costs; (2) the responsible insurer/P&I club and local correspondent, with claim reference; (3) wage, sick-pay, repatriation and disability-benefit arrangements under the SEA, CBA, applicable flag law and insurance; and (4) the contact responsible for coordinating the claim.\n\nPlease preserve and provide copies of the accident report, logbook entries, risk assessments, safety records, relevant CCTV, weather records, witness details, medical report form, SEA/CBA, Maritime Labour Certificate/DMLC, on-board complaint procedure, and applicable financial-security certificate.\n\nThis notice is made without admission and without waiver of any contractual, statutory, convention, tort or other rights. No release or final settlement is agreed. Please acknowledge receipt promptly.\n\nSincerely,\n[NAME / AUTHORITY — TO CONFIRM]",
    attachmentsChecklist: ["Medical note", "Incident details", "SEA/CBA if available", "Expense receipts"],
    fieldsToConfirm: ["Names and authority", "ship/IMO/flag", "date/time/place", "recipient and claim reference"],
    reviewWarning: "Have a maritime lawyer, union representative, or competent adviser review before sending."
  };
  return {
    summary: "A seafarer reportedly suffered a femur fracture after falling on shipboard stairs during heavy winds and is awaiting or receiving surgery.",
    urgentActions: [{ action: "Obtain written confirmation of medical-cost payment", why: "Avoid uncertainty around hospital and related costs", timing: "Now", owner: "Family/shipowner contact" }],
    factsReliedOn: ["Reported shipboard fall", "Reported femur fracture"], assumptions: [],
    missingFacts: [{ question: "What is the ship's flag and IMO number?", whyItMatters: "Identifies flag-state law and authorities", priority: "high" }],
    issues: [{ issue: "Shipowner liability for medical care", rule: "MLC Regulation 4.2 is a starting point.", application: "The injury was reportedly during service.", provisionalConclusion: "Potential coverage; verify facts and flag implementation.", confidence: "medium", sources: [{ title: "ILO MLC Title 4", url: "https://normlex.ilo.org/dyn/nrmlx_en/f?p=NORMLEXPUB:91:0::NO::P91_SECTION:MLCA_AMEND_A4", status: "verified-starting-source" }] }],
    possibleEntitlements: [{ item: "Medical costs", basis: "MLC/SEA/CBA/flag law", againstWhom: "Potentially shipowner/insurer", verificationNeeded: "Documents and flag law" }],
    evidenceChecklist: [{ item: "Accident report and logbook entry", reason: "Contemporaneous proof", howToPreserve: "Request copies in writing" }],
    deadlineRisks: [{ risk: "Contractual or statutory notice periods may apply", action: "Give prompt written notice without guessing a deadline", verifiedDeadline: null }],
    nextSteps: [{ order: 1, step: "Collect ship, contract, insurer and incident documents", who: "Family/representative" }],
    disclaimer: "Demo output only; not legal advice."
  };
}

const mime = { ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml" };

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === "GET" && req.url === "/api/status") return sendJson(res, 200, {
      demoMode: DEMO_MODE,
      providers: Object.fromEntries(Object.entries(config).map(([name, value]) => [name, { configured: Boolean(value.key), model: value.model }])),
    });
    if (req.method === "POST" && req.url === "/api/analyze") {
      const body = await readJson(req);
      return sendJson(res, 200, await analyzeCase(body.caseData));
    }
    if (req.method === "POST" && req.url === "/api/draft") {
      const body = await readJson(req);
      return sendJson(res, 200, await draftDocument(body));
    }
    if (req.method === "GET") return serveStatic(req, res);
    throw new AppError(404, "Not found");
  } catch (error) {
    const status = error instanceof AppError ? error.status : 500;
    console.error(error);
    sendJson(res, status, { error: status === 500 ? "Unexpected server error." : error.message });
  }
});

server.listen(PORT, "127.0.0.1", () => console.log(`Mariner Advocate running at http://127.0.0.1:${PORT}${DEMO_MODE ? " (demo mode)" : ""}`));

function serveStatic(req, res) {
  const requestPath = req.url === "/" ? "/index.html" : decodeURIComponent(req.url.split("?")[0]);
  const publicRoot = path.join(root, "public");
  const filePath = path.resolve(publicRoot, `.${requestPath}`);
  if (!filePath.startsWith(path.resolve(publicRoot) + path.sep)) throw new AppError(403, "Forbidden");
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) throw new AppError(404, "Not found");
  res.writeHead(200, { "Content-Type": mime[path.extname(filePath)] || "application/octet-stream", "Cache-Control": "no-store" });
  fs.createReadStream(filePath).pipe(res);
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let total = 0;
    const chunks = [];
    req.on("data", (chunk) => {
      total += chunk.length;
      if (total > MAX_BODY_BYTES) { reject(new AppError(413, "Request is too large.")); req.destroy(); return; }
      chunks.push(chunk);
    });
    req.on("end", () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}")); }
      catch { reject(new AppError(400, "Invalid JSON request.")); }
    });
    req.on("error", reject);
  });
}

function sendJson(res, status, payload) {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" });
  res.end(JSON.stringify(payload));
}

function loadEnv(file) {
  if (!fs.existsSync(file)) return;
  for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
    if (!match || match[1] in process.env) continue;
    let value = match[2];
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) value = value.slice(1, -1);
    process.env[match[1]] = value;
  }
}

class AppError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
