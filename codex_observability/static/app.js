"use strict";

const hash = new URLSearchParams(window.location.hash.slice(1));
const token = hash.get("token") || "";
history.replaceState(null, "", window.location.pathname);

const byId = (id) => document.getElementById(id);
const connection = byId("connection");
const errorBox = byId("error");

function node(tag, text, className = "") {
  const element = document.createElement(tag);
  element.textContent = String(text);
  if (className) element.className = className;
  return element;
}

async function api(path) {
  if (!token) throw new Error("Missing token. Open the complete URL printed by codex-observe.");
  const response = await fetch(path, {
    headers: {"Authorization": `Bearer ${token}`},
    cache: "no-store"
  });
  if (!response.ok) throw new Error(`API request failed (${response.status}).`);
  return response.json();
}

function renderCards(totals) {
  const successRate = totals.delegations
    ? `${Math.round((totals.successful_delegations / totals.delegations) * 100)}%`
    : "—";
  const workTokens = Math.max(0, totals.input_tokens - totals.cached_input_tokens) + totals.output_tokens;
  const definitions = [
    ["Tasks", totals.tasks],
    ["Delegations", totals.delegations],
    ["Luna success", successRate],
    ["Fix rounds", totals.fix_rounds],
    ["Review findings", totals.review_findings],
    ["Scope violations", totals.scope_violations],
    ["Decision returns", totals.decision_returns],
    ["Work tokens", workTokens.toLocaleString()]
  ];
  byId("cards").replaceChildren(...definitions.map(([label, value]) => {
    const card = node("article", "", "card");
    card.append(node("p", label, "label"), node("strong", value.toLocaleString()));
    return card;
  }));
}

function renderSkills(skills) {
  const items = skills.length ? skills.map((item) => {
    const line = node("li", "");
    line.append(node("span", item.skill), node("strong", item.count));
    return line;
  }) : [node("li", "No Skill observations yet.", "empty")];
  byId("skills").replaceChildren(...items);
}

async function showTask(taskId) {
  const detail = await api(`/api/v1/tasks/${encodeURIComponent(taskId)}`);
  byId("detail-title").textContent = taskId;
  const items = detail.events.map((event) => {
    const line = node("li", "");
    line.append(
      node("time", event.occurred_at),
      node("strong", event.event_type),
      node("span", `${event.actor} · ${event.outcome}`)
    );
    return line;
  });
  byId("timeline").replaceChildren(...items);
  byId("detail-panel").hidden = false;
}

function renderTasks(tasks) {
  const rows = tasks.map((task) => {
    const row = document.createElement("tr");
    const taskCell = document.createElement("td");
    const button = node("button", task.task_id, "task-link");
    button.type = "button";
    button.addEventListener("click", () => showTask(task.task_id).catch(showError));
    taskCell.append(button);
    const tokens = Math.max(0, task.input_tokens - task.cached_input_tokens) + task.output_tokens;
    row.append(
      taskCell,
      node("td", task.task_kind),
      node("td", task.outcome),
      node("td", task.event_count),
      node("td", tokens.toLocaleString()),
      node("td", task.scope_violations ? `${task.scope_violations} violation` : "clear")
    );
    return row;
  });
  byId("tasks").replaceChildren(...rows);
}

function showError(error) {
  connection.textContent = "Disconnected";
  connection.classList.add("bad");
  errorBox.textContent = error.message;
}

async function refresh() {
  errorBox.textContent = "";
  const [summary, tasks] = await Promise.all([
    api("/api/v1/summary"),
    api("/api/v1/tasks?limit=50")
  ]);
  renderCards(summary.totals);
  renderSkills(summary.skills);
  renderTasks(tasks);
  connection.textContent = "Local data";
  connection.classList.remove("bad");
}

byId("refresh").addEventListener("click", () => refresh().catch(showError));
refresh().catch(showError);
