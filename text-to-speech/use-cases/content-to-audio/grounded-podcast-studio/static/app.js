"use strict";

const STAGES = [
  { key: "research", title: "Research", sub: "GPT-5.6 Terra · AgentCore Web Search" },
  { key: "extraction", title: "Claim extraction", sub: "GPT-5.6 Luna · DynamoDB" },
  { key: "script", title: "Script writer", sub: "Claude Sonnet 5 · Knowledge Base" },
  { key: "factcheck", title: "Fact check", sub: "GPT-5.6 Sol · DynamoDB" },
  { key: "synthesis", title: "Speech synthesis", sub: "Amazon Polly" },
];
const STAGE_META = Object.fromEntries(STAGES.map((s) => [s.key, s]));

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let source = null;
let currentStage = null;
let currentRunId = null;
let activeRunId = null; // highlighted in history

// ---------------------------------------------------------------------------
// Stage cards (created dynamically)
// ---------------------------------------------------------------------------
function clearStages() {
  $("stages").innerHTML = "";
  $("audio-panel").hidden = true;
}

const CHEV_SVG = `<svg class="chev" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>`;

function getOrCreateStage(key) {
  let el = $(`stage-${key}`);
  if (el) return el;
  const meta = STAGE_META[key];
  el = document.createElement("section");
  el.className = "stage";
  el.id = `stage-${key}`;
  el.dataset.status = "idle";
  el.innerHTML = `
    <div class="head" role="button" tabindex="0" title="Click to expand/collapse">
      <span class="status"></span>
      <div class="titles"><div class="title">${meta.title}</div><div class="sub">${meta.sub}</div></div>
      <span class="spinner"></span>
      ${CHEV_SVG}
    </div>
    <div class="detail" id="detail-${key}"></div>`;
  el.querySelector(".head").addEventListener("click", () => el.classList.toggle("collapsed"));
  $("stages").appendChild(el);
  return el;
}

function setStageStatus(key, status) {
  getOrCreateStage(key).dataset.status = status;
}
function setStageDetail(key, html) {
  $(`detail-${key}`).innerHTML = html;
}

// ---------------------------------------------------------------------------
// Renderers (input = the stage's `data` payload)
// ---------------------------------------------------------------------------
const RENDER = {
  research: (d) =>
    "<ul>" +
    (d.sources || [])
      .map(
        (s) =>
          `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || s.url)}</a>` +
          `${s.publishedDate ? `<span class="tag">${esc(s.publishedDate)}</span>` : ""}` +
          `<div>${esc(s.snippet || "")}</div></li>`
      )
      .join("") +
    "</ul>",
  extraction: (d) =>
    `<div class="tag">${(d.facts || []).length} source-backed claims stored in DynamoDB</div><table>` +
    (d.facts || [])
      .map(
        (f) =>
          `<tr><td><b>${esc(f.subject)}</b></td><td>${esc(f.predicate)}</td>` +
          `<td>${esc(f.object)}<span class="tag">${esc(f.type)}</span></td></tr>`
      )
      .join("") +
    "</table>",
  script: (d) =>
    (d.script || [])
      .map((t) => `<div class="turn"><span class="who">${esc(t.speaker)}:</span> ${esc(t.text)}</div>`)
      .join(""),
  factcheck: (d) => {
    const r = d.report || {};
    const list = (items, cls) =>
      (items || []).length
        ? `<ul>${items.map((i) => `<li class="${cls}">${esc(i)}</li>`).join("")}</ul>`
        : `<div class="tag">none</div>`;
    return (
      `<div class="fc-group"><b class="pill-ok">Supported</b>${list(r.supported, "pill-ok")}</div>` +
      `<div class="fc-group"><b class="pill-warn">Missing</b>${list(r.missing, "pill-warn")}</div>` +
      `<div class="fc-group"><b class="pill-bad">Unsupported claims</b>${list(r.unsupported_claims, "pill-bad")}</div>`
    );
  },
  synthesis: (d) => `<div class="tag">${d.bytes} bytes · ${d.characters} billable Polly characters</div>`,
};

function showAudio(synthesis) {
  if (!synthesis || !synthesis.audio_url) return;
  $("player").src = synthesis.audio_url;
  $("audio-meta").textContent = `${synthesis.bytes} bytes · ${synthesis.characters} billable Polly characters`;
  $("audio-panel").hidden = false;
}

// ---------------------------------------------------------------------------
// Voices
// ---------------------------------------------------------------------------
async function loadVoices() {
  const newscaster = $("style").value === "newscaster";
  try {
    const res = await fetch(`/voices?newscaster=${newscaster}`);
    if (!res.ok) throw new Error(`/voices returned ${res.status}`);
    const voices = await res.json();
    if (!Array.isArray(voices) || !voices.length) throw new Error("no voices returned");
    const opts = voices
      .map((v) => `<option value="${esc(v.id)}">${esc(v.name)} — ${esc(v.lang)} (${esc(v.gender)})</option>`)
      .join("");
    $("host_voice").innerHTML = opts;
    $("cohost_voice").innerHTML = opts;
    if (voices[1]) $("cohost_voice").selectedIndex = 1;
  } catch (e) {
    const err = `<option value="">⚠ ${esc(e.message)} — check AWS creds / server</option>`;
    $("host_voice").innerHTML = err;
    $("cohost_voice").innerHTML = err;
    console.error("loadVoices failed:", e);
  }
}
$("style").addEventListener("change", loadVoices);

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------
function relTime(epoch) {
  if (!epoch) return "";
  const secs = Math.floor(Date.now() / 1000) - epoch;
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return new Date(epoch * 1000).toLocaleDateString();
}

const BIN_SVG = `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>`;

function renderHistory(items) {
  const list = $("history-list");
  if (!items.length) {
    list.innerHTML = `<li class="history-empty">No generations yet.</li>`;
    return;
  }
  list.innerHTML = items
    .map(
      (it) => `
      <li class="history-item ${it.run_id === activeRunId ? "active" : ""}" data-run="${esc(it.run_id)}">
        <div class="h-body">
          <div class="h-topic">${esc(it.topic || "(untitled)")}</div>
          <div class="h-meta"><span class="h-dot ${esc(it.status)}"></span>${esc(it.status)} · ${relTime(it.created_at)}</div>
        </div>
        <button class="h-del" title="Delete run" aria-label="Delete run" data-del="${esc(it.run_id)}">${BIN_SVG}</button>
      </li>`
    )
    .join("");
  list.querySelectorAll(".history-item .h-body").forEach((el) =>
    el.addEventListener("click", () => openRun(el.closest(".history-item").dataset.run))
  );
  list.querySelectorAll(".h-del").forEach((btn) =>
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteRun(btn.dataset.del, btn.closest(".history-item").querySelector(".h-topic").textContent);
    })
  );
}

async function deleteRun(runId, topic) {
  if (!confirm(`Delete this generation?\n\n"${topic}"\n\nThis removes its stored claims and audio and cannot be undone.`)) return;
  const res = await fetch(`/run/${runId}`, { method: "DELETE" });
  if (!res.ok) return alert("Delete failed.");
  if (runId === activeRunId) {
    activeRunId = null;
    $("view-banner").hidden = true;
    clearStages();
  }
  loadHistory();
}

async function loadHistory() {
  try {
    renderHistory(await (await fetch("/history")).json());
  } catch (e) {
    /* history is best-effort */
  }
}

async function openRun(runId) {
  if (source) source.close();
  const res = await fetch(`/run/${runId}`);
  if (!res.ok) return;
  const runData = await res.json();

  activeRunId = runId;
  $("run").disabled = false;
  clearStages();

  const byStage = {
    research: { sources: runData.sources },
    extraction: { facts: runData.facts },
    script: { script: runData.script },
    factcheck: { report: runData.report },
    synthesis: runData.synthesis || {},
  };
  const hasData = {
    research: (runData.sources || []).length,
    extraction: (runData.facts || []).length,
    script: (runData.script || []).length,
    factcheck: Object.keys(runData.report || {}).length,
    synthesis: (runData.synthesis || {}).audio_url,
  };

  let shown = 0;
  STAGES.forEach((s) => {
    if (!hasData[s.key]) return;
    shown++;
    const el = getOrCreateStage(s.key);
    setStageStatus(s.key, "done");
    setStageDetail(s.key, RENDER[s.key](byStage[s.key]));
    el.classList.add("collapsed"); // historical runs start compacted
  });

  $("view-banner").hidden = false;
  const partial =
    shown < STAGES.length
      ? ` · <span class="pill-warn">partial — ${shown}/${STAGES.length} stages captured</span>`
      : "";
  $("view-banner").innerHTML = `Viewing past run — <b>${esc(runData.topic)}</b> · ${esc(runData.status)}${partial}`;
  showAudio(runData.synthesis);
  renderHistory(await (await fetch("/history")).json());
}

// ---------------------------------------------------------------------------
// Live run
// ---------------------------------------------------------------------------
$("new-btn").addEventListener("click", () => {
  if (source) source.close();
  activeRunId = null;
  currentRunId = null;
  $("view-banner").hidden = true;
  clearStages();
  loadHistory();
  $("topic").focus();
});

$("run").addEventListener("click", () => {
  const topic = $("topic").value.trim();
  const hostVoice = $("host_voice").value;
  const cohostVoice = $("cohost_voice").value;
  if (!topic) return alert("Enter a topic.");
  if (!hostVoice || !cohostVoice) return alert("Voices are still loading.");

  $("view-banner").hidden = true;
  clearStages();
  $("run").disabled = true;
  if (source) source.close();

  const params = new URLSearchParams({
    topic,
    host_name: $("host_name").value || "Alex",
    cohost_name: $("cohost_name").value || "Sam",
    host_voice: hostVoice,
    cohost_voice: cohostVoice,
    newscaster: $("style").value === "newscaster",
  });

  source = new EventSource(`/stream?${params.toString()}`);
  source.onmessage = (e) => handleEvent(JSON.parse(e.data));
  source.onerror = () => {
    $("run").disabled = false;
    if (source) source.close();
  };
});

function handleEvent(ev) {
  const { stage, status, data } = ev;

  if (stage === "run") {
    if (status === "started") {
      currentRunId = data.run_id;
      activeRunId = data.run_id;
      loadHistory(); // the running session now exists server-side
    } else if (status === "done") {
      $("run").disabled = false;
      if (source) source.close();
      loadHistory();
    } else if (status === "error") {
      if (currentStage) setStageStatus(currentStage, "error");
      alert(`Pipeline failed: ${data.error}`);
      $("run").disabled = false;
      if (source) source.close();
      loadHistory();
    }
    return;
  }

  if (status === "started") {
    currentStage = stage;
    setStageStatus(stage, "running");
  } else if (status === "done") {
    setStageStatus(stage, "done");
    if (RENDER[stage]) setStageDetail(stage, RENDER[stage](data));
    if (stage === "synthesis") showAudio(data);
  }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
loadVoices();
loadHistory();
