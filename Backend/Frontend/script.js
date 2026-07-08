// script.js — chat-driven flow. One input box drives everything:
// first message creates a plan, every message after that refines the
// existing plan (via /agent/refine) until the user clicks "Looks good"
// on the canvas panel, which finalizes the .docx.

const isLocal = ["localhost", "127.0.0.1"].includes(window.location.hostname);
const API_BASE = isLocal ? "http://localhost:8000" : window.location.origin;

// ---------- Element refs ----------

const chatScroll = document.getElementById("chat-scroll");
const chatInput = document.getElementById("chat-input");
const chatSendBtn = document.getElementById("chat-send-btn");

const errorBanner = document.getElementById("error-banner");

const canvasEmpty = document.getElementById("canvas-empty");
const canvasContent = document.getElementById("canvas-content");
const planTitle = document.getElementById("plan-title");
const revisionBadge = document.getElementById("revision-badge");
const taskTbody = document.getElementById("task-tbody");

const decisionRow = document.getElementById("decision-row");
const looksGoodBtn = document.getElementById("looks-good-btn");

const resultPanel = document.getElementById("result-panel");
const resultFilename = document.getElementById("result-filename");
const downloadLink = document.getElementById("download-link");

const STATUS_OPTIONS = [
  { value: "Not started", label: "○ Not started" },
  { value: "In progress", label: "◐ In progress" },
  { value: "Done", label: "✓ Done" },
];

// Casual acknowledgments/closers (e.g. "thanks", "ok that's a good planner")
// shouldn't be sent to the LLM as feedback — that wastes a call and falsely
// bumps the revision counter with a "no changes made" reply.
//
// Heuristic instead of exact-phrase matching (which was too brittle):
// short message + contains a positive/closing word + contains NO actionable
// verb implies the user is just acknowledging, not asking for a change.
const POSITIVE_WORDS = [
  "thanks", "thank", "good", "great", "perfect", "nice", "cool", "awesome",
  "sounds good", "looks good", "well done", "appreciate", "cheers", "bye",
  "goodbye", "ok", "okay", "fine", "sure",
];

const ACTION_VERBS = [
  "add", "remove", "delete", "change", "update", "modify", "edit", "fix",
  "shift", "push", "move", "increase", "decrease", "extend", "shorten",
  "replace", "include", "exclude", "adjust", "rename", "reduce", "combine",
  "split", "swap", "reorder", "insert",
];

function isClosingRemark(text) {
  const trimmed = text.trim().toLowerCase();
  if (trimmed.split(/\s+/).length > 8) return false; // longer messages are treated as real feedback

  const hasPositiveWord = POSITIVE_WORDS.some(w => trimmed.includes(w));
  const hasActionVerb = ACTION_VERBS.some(v => new RegExp(`\\b${v}\\b`).test(trimmed));

  return hasPositiveWord && !hasActionVerb;
}

const CLOSING_REPLIES = [
  "You're welcome! Come back anytime you need another plan.",
  "Glad it worked out — good luck with the build.",
  "Anytime. Ping me again whenever you need a new plan drafted.",
];

function pickClosingReply() {
  return CLOSING_REPLIES[Math.floor(Math.random() * CLOSING_REPLIES.length)];
}

let currentPlanId = null;
let currentTasks = [];

// ---------- Chat rendering ----------

function addChatMessage(role, text) {
  const div = document.createElement("div");
  div.className = `chat-msg ${role === "user" ? "user-msg" : "agent-msg"}`;
  div.innerHTML = `<span class="msg-tag">${role}</span><p></p>`;
  div.querySelector("p").textContent = text; // textContent -> safe from HTML injection
  chatScroll.appendChild(div);
  chatScroll.scrollTop = chatScroll.scrollHeight;
}

function showError(msg) {
  errorBanner.textContent = msg;
  errorBanner.classList.remove("hidden");
}

function clearError() {
  errorBanner.classList.add("hidden");
}

function addTypingIndicator() {
  const div = document.createElement("div");
  div.className = "chat-msg agent-msg typing-msg";
  div.id = "typing-indicator";
  div.innerHTML = `<span class="msg-tag"></span><p class="typing-dots"><span></span><span></span><span></span></p>`;
  chatScroll.appendChild(div);
  chatScroll.scrollTop = chatScroll.scrollHeight;
}

function removeTypingIndicator() {
  document.getElementById("typing-indicator")?.remove();
}

function setBusy(button, busyLabel) {
  button.dataset.originalLabel = button.querySelector(".btn-label")?.textContent || button.textContent;
  button.disabled = true;
  button.classList.add("btn-loading");
  const label = button.querySelector(".btn-label");
  if (label) label.textContent = busyLabel;
  else button.textContent = busyLabel;
}

function clearBusy(button) {
  button.disabled = false;
  button.classList.remove("btn-loading");
  const label = button.querySelector(".btn-label");
  if (label) label.textContent = button.dataset.originalLabel;
  else button.textContent = button.dataset.originalLabel;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function statusClass(status) {
  const s = (status || "").toLowerCase();
  if (s.includes("done") || s.includes("complete")) return "status-done";
  if (s.includes("progress")) return "status-in-progress";
  return "status-not-started";
}

const WEEKDAY_ABBR = {
  Monday: "Mon", Tuesday: "Tue", Wednesday: "Wed", Thursday: "Thu",
  Friday: "Fri", Saturday: "Sat", Sunday: "Sun",
};

function formatDeadline(deadline) {
  if (!deadline) return "—";
  let out = deadline;
  for (const [full, abbr] of Object.entries(WEEKDAY_ABBR)) {
    out = out.replace(full, abbr);
  }
  return out;
}

// ---------- Canvas (plan) rendering ----------

function renderTasks(tasks) {
  currentTasks = tasks.map(t => ({ ...t }));
  taskTbody.innerHTML = "";

  currentTasks.forEach((task, i) => {
    const tr = document.createElement("tr");
    const optionsHtml = STATUS_OPTIONS.map(opt =>
      `<option value="${opt.value}" ${opt.value === (task.status || "Not started") ? "selected" : ""}>${opt.label}</option>`
    ).join("");

    tr.innerHTML = `
      <td class="row-tag">T${i + 1}</td>
      <td>${escapeHtml(task.task)}</td>
      <td>${escapeHtml(task.notes || "")}</td>
      <td>
        <select class="status-select ${statusClass(task.status)}" data-index="${i}">
          ${optionsHtml}
        </select>
      </td>
      <td class="deadline-tag">${escapeHtml(formatDeadline(task.deadline))}</td>
    `;
    taskTbody.appendChild(tr);
  });

  taskTbody.querySelectorAll(".status-select").forEach(select => {
    select.addEventListener("change", (e) => {
      const idx = Number(e.target.dataset.index);
      currentTasks[idx].status = e.target.value;
      e.target.className = `status-select ${statusClass(e.target.value)}`;
    });
  });
}

function renderPlan(data) {
  if (data.is_plan === false) {
    // Not a planning request (a question, greeting, small talk) — just
    // reply in chat, leave the canvas panel untouched.
    addChatMessage("agent", data.message);
    return;
  }

  currentPlanId = data.plan_id;

  canvasEmpty.classList.add("hidden");
  canvasContent.classList.remove("hidden");
  resultPanel.classList.add("hidden");
  decisionRow.classList.remove("hidden");

  planTitle.textContent = data.title;
  revisionBadge.textContent = `Revision ${data.revision}`;
  renderTasks(data.tasks);

  addChatMessage("agent", `${data.summary} ${data.message}`.trim());
}

// ---------- API calls ----------

async function callApi(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

// ---------- Send handler: creates a plan, or refines the existing one ----------

async function handleSend() {
  const text = chatInput.value.trim();
  if (!text) return;

  clearError();
  addChatMessage("user", text);
  chatInput.value = "";

  // Casual acknowledgments (thanks, ok good, etc.) get a friendly reply
  // locally — no API call, no revision bump, no awkward "no changes" reply.
  if (currentPlanId && isClosingRemark(text)) {
    addChatMessage("agent", pickClosingReply());
    chatInput.focus();
    return;
  }

  addTypingIndicator();
  setBusy(chatSendBtn, "");

  try {
    const data = currentPlanId
      ? await callApi("/agent/refine", { plan_id: currentPlanId, feedback: text })
      : await callApi("/agent", { request: text });

    removeTypingIndicator();
    renderPlan(data);
  } catch (err) {
    removeTypingIndicator();
    showError(err.message);
  } finally {
    clearBusy(chatSendBtn);
    chatInput.focus();
  }
}

chatSendBtn.addEventListener("click", handleSend);

chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});

// ---------- Finalize: sync dropdown edits, then generate the .docx ----------

looksGoodBtn.addEventListener("click", async () => {
  clearError();
  setBusy(looksGoodBtn, "Generating…");

  try {
    await callApi("/agent/update-tasks", { plan_id: currentPlanId, tasks: currentTasks });
    const data = await callApi("/generate-doc", { plan_id: currentPlanId });

    resultFilename.textContent = data.doc_filename;
    downloadLink.href = `${API_BASE}${data.download_url}`;
    downloadLink.setAttribute("download", data.doc_filename);
    resultPanel.classList.remove("hidden");

    addChatMessage("agent", "Document generated — you can download it from the panel on the right, or keep sending feedback to revise it further.");
  } catch (err) {
    showError(err.message);
  } finally {
    clearBusy(looksGoodBtn);
  }
});