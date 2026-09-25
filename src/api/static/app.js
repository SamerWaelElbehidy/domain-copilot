"use strict";
/* Domain Copilot UI. Plain JavaScript, no framework and no build step.
   Every piece of server or model text is inserted as plain text nodes, never as
   markup, so a poisoned document or a hostile answer cannot inject markup.
   The role only decides which tabs are shown; the server enforces every
   permission again on each request. */

const $ = (id) => document.getElementById(id);
let token = sessionStorage.getItem("token");
let role = sessionStorage.getItem("role");
let username = sessionStorage.getItem("username");
let askAbort = null;
let runAbort = null;
let currentRunId = null;

function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") el.className = v;
    else if (k === "onclick") el.addEventListener("click", v);
    else el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

function toast(message) {
  const t = $("toast");
  t.textContent = message;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 3500);
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (token) headers["Authorization"] = "Bearer " + token;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.json);
  }
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401 && token) {
    signOut();
    throw new Error("Your session expired. Please sign in again.");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch (_) { /* keep statusText */ }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

/* EventSource cannot send an Authorization header, so read the SSE stream
   from fetch and parse the frames by hand. */
async function readSse(path, options, onEvent, signal) {
  const headers = { Authorization: "Bearer " + token };
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.json);
  }
  const response = await fetch(path, { ...options, headers, signal });
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* ignore */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (line) onEvent(JSON.parse(line.slice(6)));
    }
  }
}

/* ---------- session ---------- */

const TABS = {
  technician: [["ask", "Ask"], ["runs", "Work orders"], ["history", "History"]],
  supervisor: [["ask", "Ask"], ["approvals", "Approvals"], ["runs", "All runs"], ["history", "History"]],
  admin: [["ask", "Ask"], ["runs", "All runs"], ["documents", "Documents & usage"], ["history", "History"]],
};

function showApp() {
  $("login-view").hidden = true;
  $("app-view").hidden = false;
  $("whoami").hidden = false;
  $("who").textContent = username + " (" + role + ")";
  const nav = $("tabs");
  nav.replaceChildren(
    ...TABS[role].map(([id, label]) =>
      h("button", { role: "tab", "data-tab": id, onclick: () => openTab(id) }, label)),
  );
  $("run-form").hidden = role !== "technician";
  $("run-live").hidden = true;
  loadEquipment();
  openTab("ask");
}

function signOut() {
  token = role = username = null;
  sessionStorage.clear();
  if (askAbort) askAbort.abort();
  if (runAbort) runAbort.abort();
  $("login-view").hidden = false;
  $("app-view").hidden = true;
  $("whoami").hidden = true;
  $("password").value = "";
}

$("logout").addEventListener("click", signOut);

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("login-error").textContent = "";
  try {
    const body = await api("/auth/login", {
      method: "POST",
      json: { username: $("username").value.trim(), password: $("password").value },
    });
    token = body.access_token;
    role = body.role;
    username = $("username").value.trim();
    sessionStorage.setItem("token", token);
    sessionStorage.setItem("role", role);
    sessionStorage.setItem("username", username);
    showApp();
  } catch (err) {
    $("login-error").textContent = err.message;
  }
});

function openTab(id) {
  document.querySelectorAll(".tab").forEach((t) => (t.hidden = t.id !== "tab-" + id));
  document.querySelectorAll("#tabs button").forEach((b) =>
    b.setAttribute("aria-selected", String(b.dataset.tab === id)));
  const loaders = {
    runs: loadRuns, approvals: loadApprovals, history: loadHistory, documents: loadDocuments,
  };
  if (loaders[id]) loaders[id]().catch((e) => toast(e.message));
}

/* ---------- ask ---------- */

async function loadEquipment() {
  try {
    const list = await api("/equipment");
    const select = $("equipment");
    select.replaceChildren(h("option", { value: "" }, "Any equipment"),
      ...list.map((e) => h("option", { value: e.equipment_id }, e.name)));
  } catch (_) { /* optional filter; the form still works without it */ }
}

function renderAnswer(answer) {
  const box = $("ask-final");
  box.replaceChildren();
  if (answer.status === "refused") {
    box.append(h("div", { class: "refusal" },
      h("strong", {}, "Not enough information to answer safely. "),
      REFUSAL_TEXT[answer.reason] || answer.reason || "",
      answer.detail ? h("div", { class: "hint" }, answer.detail) : null));
    return;
  }
  box.append(h("div", { class: "answer" }, answer.answer));
  if (answer.citations.length) {
    box.append(h("h3", {}, "Sources"),
      h("ol", { class: "cites" }, answer.citations.map((c) =>
        h("li", {}, c.section_title, " ", h("code", {}, c.source_ref || c.document_id)))));
  }
}

const REFUSAL_TEXT = {
  no_evidence: "No relevant passage was found.",
  below_relevance_threshold: "The manuals do not seem to cover this question.",
  invalid_model_output: "The model's reply could not be used, so nothing was shown.",
  model_judged_insufficient: "The retrieved passages do not contain the answer.",
  ungrounded_answer: "The draft answer did not cite the manuals, so it was withheld.",
  unsupported_answer: "The draft answer was not supported by the cited text, so it was withheld.",
  conflicting_sources: "Sources disagree, so a supervisor should confirm.",
};

$("ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (askAbort) askAbort.abort();
  askAbort = new AbortController();
  $("ask-out").hidden = false;
  $("ask-final").replaceChildren();
  $("ask-draft").hidden = true;
  $("ask-draft").textContent = "";
  $("ask-progress").textContent = "Searching the manuals...";
  $("ask-stop").hidden = false;
  $("ask-btn").disabled = true;
  try {
    await readSse("/ask/stream", {
      method: "POST",
      json: { question: $("question").value, equipment_id: $("equipment").value || null },
    }, (e) => {
      if (e.type === "session" && Object.keys(e.redactions || {}).length) {
        toast("Personal details were removed from your question before it was processed.");
      } else if (e.type === "retrieval") {
        $("ask-progress").textContent = e.excerpts.length
          ? "Found " + e.excerpts.length + " passages. Drafting an answer..."
          : "No relevant passages found.";
      } else if (e.type === "token") {
        $("ask-draft").hidden = false;
        $("ask-draft").textContent += e.text;
      } else if (e.type === "answer") {
        $("ask-progress").textContent = "Checked against the sources.";
        $("ask-draft").hidden = true;
        renderAnswer(e.answer);
      }
    }, askAbort.signal);
  } catch (err) {
    if (err.name === "AbortError") {
      $("ask-progress").textContent = "Stopped.";
    } else {
      $("ask-progress").textContent = "";
      $("ask-final").replaceChildren(h("div", { class: "bad verdict" }, err.message));
    }
  } finally {
    $("ask-stop").hidden = true;
    $("ask-btn").disabled = false;
  }
});

$("ask-stop").addEventListener("click", () => askAbort && askAbort.abort());

/* ---------- runs ---------- */

const STATE_LABEL = {
  pending_approval: ["Waiting for supervisor", "warn"], dispatched: ["Dispatched", "ok"],
  approved: ["Approved", "ok"], rejected: ["Rejected", "bad"], failed: ["Failed", "bad"],
  refused_low_evidence: ["Refused: not enough evidence", "warn"],
  degraded_plain_rag: ["Answered without the workflow", "warn"],
};

function stateBadge(state) {
  const [label, kind] = STATE_LABEL[state] || [state.replaceAll("_", " "), ""];
  return h("span", { class: "badge " + kind }, label);
}

function runTable(runs) {
  if (!runs.length) return h("p", { class: "hint" }, "Nothing here yet.");
  return h("table", {},
    h("thead", {}, h("tr", {}, h("th", {}, "Started"), h("th", {}, "Equipment"), h("th", {}, "State"))),
    h("tbody", {}, runs.map((r) =>
      h("tr", { class: "click", onclick: () => openRun(r.run_id) },
        h("td", {}, new Date(r.started_at).toLocaleString()),
        h("td", {}, r.equipment_id || "-"),
        h("td", {}, stateBadge(r.state))))));
}

async function loadRuns() {
  $("run-list").replaceChildren(runTable(await api("/runs")));
}

const EVENT_TEXT = {
  step_started: (e) => "Working on " + e.step.replaceAll("_", " ") + "...",
  step_finished: (e) => "Finished " + e.step.replaceAll("_", " "),
  awaiting_approval: () => "Work order drafted. Waiting for a supervisor to approve it.",
  refused: (e) => "Stopped: " + (e.reason || "not enough evidence"),
  degraded: () => "The workflow could not finish, so a plain answer was given instead.",
  failed: (e) => "Run failed: " + (e.reason || "unknown"),
  rejected: () => "Rejected by supervisor.",
  dispatched: () => "Approved and dispatched.",
};

$("run-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const { run_id, redactions } = await api("/runs", {
      method: "POST", json: { symptom: $("symptom").value },
    });
    if (Object.keys(redactions || {}).length) toast("Personal details were removed before processing.");
    currentRunId = run_id;
    $("run-steps").replaceChildren();
    $("run-live").hidden = false;
    $("run-cancel").hidden = false;
    if (runAbort) runAbort.abort();
    runAbort = new AbortController();
    await readSse("/runs/" + run_id + "/events", {}, (e) => {
      const text = EVENT_TEXT[e.event];
      if (text) $("run-steps").append(h("li", {}, text(e)));
    }, runAbort.signal);
    $("run-cancel").hidden = true;
    await loadRuns();
  } catch (err) {
    if (err.name !== "AbortError") toast(err.message);
  }
});

$("run-cancel").addEventListener("click", async () => {
  try {
    await api("/runs/" + currentRunId + "/cancel", { method: "POST" });
    toast("Cancelling...");
  } catch (err) { toast(err.message); }
});

/* ---------- approvals ---------- */

function workOrderView(wo) {
  return h("div", { class: "wo" },
    h("p", {}, h("strong", {}, wo.symptom_description)),
    h("h4", {}, "Safety checklist (copied from the manual, cannot be removed)"),
    h("ol", {}, wo.safety_checklist.map((s) => h("li", {}, s))),
    h("h4", {}, "Diagnostic steps"),
    h("ol", {}, wo.diagnostic_steps.map((s) => h("li", {}, s))),
    h("h4", {}, "Sources"),
    h("ul", {}, wo.citations.map((c) => h("li", {}, c.section_title, " ", h("code", {}, c.source_ref)))));
}

async function decide(runId, decision, extra = {}) {
  const comment = window.prompt(decision === "reject" ? "Reason for rejecting:" : "Comment (optional):", "");
  if (comment === null) return;
  try {
    await api("/runs/" + runId + "/decision", {
      method: "POST", json: { decision, comment, ...extra },
    });
    toast(decision === "reject" ? "Rejected." : "Approved and dispatched.");
    await loadApprovals();
  } catch (err) { toast(err.message); }
}

async function loadApprovals() {
  const items = await api("/approvals");
  $("approval-list").replaceChildren(...(items.length
    ? items.map((item) => h("div", { class: "card" },
      h("div", { class: "row" },
        h("h3", {}, item.equipment_id || "Work order"),
        h("button", { class: "ghost", onclick: () => openRun(item.run_id) }, "Audit trail")),
      item.work_order ? workOrderView(item.work_order) : null,
      h("div", { class: "row" },
        h("span", { class: "left" },
          h("button", { onclick: () => decide(item.run_id, "approve") }, "Approve and dispatch"),
          h("button", { class: "danger", onclick: () => decide(item.run_id, "reject") }, "Reject")))))
    : [h("p", { class: "hint" }, "Nothing is waiting for approval.")]));
}

$("refresh-approvals").addEventListener("click", () => loadApprovals().catch((e) => toast(e.message)));

/* ---------- run detail, audit trail, replay ---------- */

async function openRun(runId) {
  document.querySelectorAll(".tab").forEach((t) => (t.hidden = t.id !== "tab-detail"));
  document.querySelectorAll("#tabs button").forEach((b) => b.setAttribute("aria-selected", "false"));
  try {
    const [run, trace] = await Promise.all([api("/runs/" + runId), api("/runs/" + runId + "/trace")]);
    $("detail-title").textContent = "Run " + run.run_id;
    const badge = $("chain-badge");
    badge.textContent = trace.chain_valid ? "Audit log verified" : "AUDIT LOG TAMPERED";
    badge.className = "badge " + (trace.chain_valid ? "ok" : "bad");
    $("detail-body").replaceChildren(
      h("p", {}, stateBadge(run.state), " ", h("span", { class: "hint" }, "started ",
        new Date(run.started_at).toLocaleString())),
      h("p", { class: "hint" }, "Model usage: ", trace.usage.calls, " calls, ",
        trace.usage.input_tokens + trace.usage.output_tokens, " tokens, $", trace.usage.cost_usd.toFixed(4)),
      run.work_order ? workOrderView(run.work_order) : null);
    renderTrace(trace.steps);
    const replayBtn = $("detail-replay");
    replayBtn.hidden = !["supervisor", "admin"].includes(role);
    replayBtn.onclick = () => replay(runId);
  } catch (err) { toast(err.message); }
}

function renderTrace(steps) {
  $("trace").replaceChildren(...steps.map((s) => h("li", {},
    h("strong", {}, s.name.replaceAll("_", " ")), " ",
    h("span", { class: "badge " + (s.status === "success" ? "ok" : "warn") }, s.status),
    h("div", { class: "meta" }, (s.agent || "orchestrator"), " | ", s.input_tokens + s.output_tokens,
      " tokens | ", h("code", {}, s.step_hash.slice(0, 12))),
    h("details", {}, h("summary", {}, "Recorded output"),
      h("pre", {}, JSON.stringify(s.output, null, 2))))));
}

async function replay(runId) {
  try {
    const result = await api("/runs/" + runId + "/replay");
    renderTrace(result.frames.map((f) => ({
      name: f.name, status: f.status, agent: f.agent_name, output: f.output_snapshot,
      input_tokens: f.input_tokens, output_tokens: f.output_tokens,
      step_hash: "replayed",
    })));
    toast("Replayed from the recorded log. No model was called.");
  } catch (err) { toast(err.message); }
}

/* ---------- history ---------- */

async function loadHistory() {
  const sessions = await api("/sessions");
  const box = $("session-list");
  if (!sessions.length) { box.replaceChildren(h("p", { class: "hint" }, "No questions yet.")); return; }
  box.replaceChildren(...sessions.map((s) => h("details", {},
    h("summary", {}, s.title, " ", h("span", { class: "hint" }, new Date(s.created_at).toLocaleString())),
    h("div", { "data-session": s.session_id }, "..."),
  )));
  box.querySelectorAll("details").forEach((d) => d.addEventListener("toggle", async () => {
    const holder = d.querySelector("[data-session]");
    if (!d.open || holder.dataset.loaded) return;
    try {
      const detail = await api("/sessions/" + holder.dataset.session);
      holder.dataset.loaded = "1";
      holder.replaceChildren(...detail.messages.map((m) => h("p", {},
        h("strong", {}, m.role === "user" ? "You: " : "Copilot: "), m.content,
        m.status === "refused" ? h("span", { class: "badge warn" }, "refused") : null)));
    } catch (err) { holder.textContent = err.message; }
  }));
}

/* ---------- documents and usage (admin) ---------- */

async function loadDocuments() {
  const docs = await api("/documents");
  $("doc-list").replaceChildren(h("table", {},
    h("thead", {}, h("tr", {}, ["Document", "Rev.", "Type", "Revision status", "Ingestion"].map((c) => h("th", {}, c)))),
    h("tbody", {}, docs.map((d) => h("tr", {},
      h("td", {}, d.title, h("div", { class: "hint" }, d.document_id)),
      h("td", {}, d.revision), h("td", {}, d.doc_type),
      h("td", {}, h("span", { class: "badge " + (d.status === "current" ? "ok" : "warn") }, d.status)),
      h("td", {}, h("span", { class: "badge " + (d.ingestion_status === "ingested" ? "ok" : "bad") },
        d.ingestion_status), d.ingestion_error ? h("div", { class: "hint" }, d.ingestion_error) : null))))));
  const usage = await api("/usage");
  $("usage-list").replaceChildren(usage.length ? h("table", {},
    h("thead", {}, h("tr", {}, ["User", "Calls", "Tokens in/out", "Cost (USD)"].map((c) => h("th", {}, c)))),
    h("tbody", {}, usage.map((u) => h("tr", {},
      h("td", {}, u.user_id || "system"), h("td", {}, u.calls),
      h("td", {}, u.input_tokens + " / " + u.output_tokens), h("td", {}, u.cost_usd.toFixed(4))))))
    : h("p", { class: "hint" }, "No model calls yet."));
}

$("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData();
  form.append("file", $("file").files[0]);
  const fields = {
    equipment_id: "m-equipment-id", equipment_name: "m-equipment-name", document_id: "m-document-id",
    revision: "m-revision", effective_date: "m-date", doc_type: "m-type",
  };
  for (const [name, id] of Object.entries(fields)) if ($(id).value) form.append(name, $(id).value);
  $("upload-result").textContent = "Uploading and indexing...";
  try {
    const r = await api("/documents", { method: "POST", body: form });
    $("upload-result").textContent = r.status === "ingested"
      ? "Indexed " + r.chunks + " passages from " + r.document_id + "."
      : "Saved but indexing failed: " + r.error;
    await loadDocuments();
  } catch (err) { $("upload-result").textContent = err.message; }
});

if (token && role) showApp();
