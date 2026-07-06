// script.js — talks to the FastAPI backend, renders the plan, and
// drives the plan -> refine -> generate-doc flow.

const API_BASE = "http://localhost:8000";

// ---------- Element refs ----------

const requestInput = document.getElementById("request-input");
const submitBtn = document.getElementById("submit-btn");

const logPanel = document.getElementById("log-panel");
const logText = document.getElementById("log-text");

const planPanel = document.getElementById("plan-panel");
const planTitle = document.getElementById("plan-title");
const planIdBadge = document.getElementById("plan-id-badge");
const taskTbody = document.getElementById("task-tbody");
const agentMessage = document.getElementById("agent-message");

const decisionRow = document.getElementById("decision-row");
const looksGoodBtn = document.getElementById("looks-good-btn");
const needsChangesBtn = document.getElementById("needs-changes-btn");

const feedbackRow = document.getElementById("feedback-row");
const feedbackInput = document.getElementById("feedback-input");
const refineBtn = document.getElementById("refine-btn");
const cancelFeedbackBtn = document.getElementById("cancel-feedback-btn");

const resultPanel = document.getElementById("result-panel");
const resultFilename = document.getElementById("result-filename");
const downloadLink = document.getElementById("download-link");

const errorBanner = document.getElementById("error-banner");

// ---------- State ----------

let currentPlanId = null;

// ---------- Helpers ----------

function showError(msg) {
  errorBanner.textContent = msg;
  errorBanner.classList.remove("hidden");
}

function clearError() {
  errorBanner.classList.add("hidden");
}

function setBusy(button, busyLabel) {
  button.dataset.originalLabel = button.querySelector(".btn-label")?.textContent || button.textContent;
  button.disabled = true;
  const label = button.querySelector(".btn-label");
  if (label) label.textContent = busyLabel;
  else button.textContent = busyLabel;
}

function clearBusy(button) {
  button.disabled = false;
  const label = button.querySelector(".btn-label");
  if (label) label.textContent = button.dataset.originalLabel;
  else button.textContent = button.dataset.originalLabel;
}

function statusClass(status) {
  const s = (status || "").toLowerCase();
  if (s.includes("done") || s.includes("complete")) return "status-done";
  if (s.includes("progress")) return "status-in-progress";
  return "status-not-started";
}

function renderTasks(tasks) {
  taskTbody.innerHTML = "";
  tasks.forEach((task, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="row-tag">T${i + 1}</td>
      <td>${escapeHtml(task.task)}</td>
      <td>${escapeHtml(task.notes || "")}</td>
      <td><span class="status-pill ${statusClass(task.status)}">${escapeHtml(task.status || "Not started")}</span></td>
      <td class="deadline-tag">${escapeHtml(task.deadline || "—")}</td>
    `;
    taskTbody.appendChild(tr);
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderPlan(data) {
  currentPlanId = data.plan_id;
  planTitle.textContent = data.title;
  planIdBadge.textContent = data.plan_id;
  renderTasks(data.tasks);
  agentMessage.textContent = data.message;

  planPanel.classList.remove("hidden");
  feedbackRow.classList.add("hidden");
  decisionRow.classList.remove("hidden");
  resultPanel.classList.add("hidden");
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

// ---------- Event handlers ----------

submitBtn.addEventListener("click", async () => {
  const request = requestInput.value.trim();
  if (!request) {
    showError("Type what you need done first — a rough idea is enough.");
    return;
  }
  clearError();
  logPanel.classList.remove("hidden");
  logText.innerHTML = `thinking<span class="dots"><span>.</span><span>.</span><span>.</span></span>`;
  planPanel.classList.add("hidden");
  resultPanel.classList.add("hidden");
  setBusy(submitBtn, "Planning…");

  try {
    const data = await callApi("/agent", { request });
    renderPlan(data);
  } catch (err) {
    showError(err.message);
  } finally {
    logPanel.classList.add("hidden");
    clearBusy(submitBtn);
  }
});

needsChangesBtn.addEventListener("click", () => {
  feedbackRow.classList.remove("hidden");
  feedbackInput.focus();
});

cancelFeedbackBtn.addEventListener("click", () => {
  feedbackRow.classList.add("hidden");
  feedbackInput.value = "";
});

refineBtn.addEventListener("click", async () => {
  const feedback = feedbackInput.value.trim();
  if (!feedback) {
    showError("Add a note on what to change before updating the plan.");
    return;
  }
  clearError();
  setBusy(refineBtn, "Updating…");

  try {
    const data = await callApi("/agent/refine", { plan_id: currentPlanId, feedback });
    renderPlan(data);
    feedbackInput.value = "";
  } catch (err) {
    showError(err.message);
  } finally {
    clearBusy(refineBtn);
  }
});

looksGoodBtn.addEventListener("click", async () => {
  clearError();
  setBusy(looksGoodBtn, "Generating…");

  try {
    const data = await callApi("/generate-doc", { plan_id: currentPlanId });
    resultFilename.textContent = data.doc_filename;
    downloadLink.href = `${API_BASE}${data.download_url}`;
    downloadLink.setAttribute("download", data.doc_filename);
    resultPanel.classList.remove("hidden");
    decisionRow.classList.add("hidden");
  } catch (err) {
    showError(err.message);
  } finally {
    clearBusy(looksGoodBtn);
  }
});