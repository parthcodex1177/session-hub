"use strict";

const state = {
  tool: "", project: "", model: "", tag: "", q: "", from: "", to: "",
  includeEmpty: false, sort: "ended_at", dir: "desc",
  limit: 50, offset: 0, total: 0,
  activeRefreshTimer: null,
};
const COLSPAN = 11;          // keep in sync with the table header
let charts = [];

const $ = (id) => document.getElementById(id);

function toast(msg, ms = 2500) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add("hidden"), ms);
}

function fmtTokens(n) {
  if (!n) return "0";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(n);
}

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function relTime(iso) {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + "m ago";
  if (s < 86400) return Math.floor(s / 3600) + "h ago";
  return Math.floor(s / 86400) + "d ago";
}

function esc(s) {
  const div = document.createElement("div");
  div.textContent = s ?? "";
  return div.innerHTML;
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

// ---------- token → cost estimation ----------

// Approximate public API pricing, USD per 1,000,000 tokens. Matched by the
// model-name family substring so new minor versions inherit a tier. Cache
// tokens are excluded — this is a deliberate ballpark, not a billing figure.
const PRICING = [
  { match: "opus",   input: 15.0,  output: 75.0  },
  { match: "sonnet", input: 3.0,   output: 15.0  },
  { match: "haiku",  input: 0.80,  output: 4.0   },
  { match: "gemini-2.5-pro",   input: 1.25, output: 10.0  },
  { match: "gemini-2.5-flash", input: 0.15, output: 0.60  },
  { match: "gemini-3-flash",   input: 0.15, output: 0.60  },
  { match: "gemini-2.0-flash", input: 0.10, output: 0.40  },
  { match: "gemini-flash",     input: 0.15, output: 0.60  },
  { match: "gemini-pro",       input: 1.25, output: 10.0  },
];

function priceFor(model) {
  const m = (model || "").toLowerCase();
  return PRICING.find((p) => m.includes(p.match)) || null;
}

// Returns { cost, model } or null when no known model applies (e.g. Antigravity,
// which records no model). Uses the first recognised model in the list.
function estimateCost(inputTokens, outputTokens, models) {
  const list = Array.isArray(models) ? models : models ? [models] : [];
  for (const model of list) {
    const tier = priceFor(model);
    if (tier) {
      const cost = (inputTokens || 0) / 1e6 * tier.input + (outputTokens || 0) / 1e6 * tier.output;
      return { cost, model };
    }
  }
  return null;
}

function fmtCost(est) {
  if (!est) return "";
  if (est.cost === 0) return "$0.00";
  if (est.cost < 0.01) return "<$0.01";
  if (est.cost < 1000) return "$" + est.cost.toFixed(2);
  return "$" + Math.round(est.cost).toLocaleString();
}

// ---------- sessions table ----------

function sessionsQuery() {
  const p = new URLSearchParams();
  if (state.tool) p.set("tool", state.tool);
  if (state.project) p.set("project", state.project);
  if (state.model) p.set("model", state.model);
  if (state.tag) p.set("tag", state.tag);
  if (state.q) p.set("q", state.q);
  if (state.from) p.set("date_from", state.from);
  if (state.to) p.set("date_to", state.to);
  if (state.includeEmpty) p.set("include_empty", "true");
  p.set("sort", state.sort);
  p.set("dir", state.dir);
  p.set("limit", state.limit);
  p.set("offset", state.offset);
  return p.toString();
}

function exportQuery(fmt) {
  const p = new URLSearchParams();
  if (state.tool) p.set("tool", state.tool);
  if (state.project) p.set("project", state.project);
  if (state.model) p.set("model", state.model);
  if (state.tag) p.set("tag", state.tag);
  if (state.q) p.set("q", state.q);
  if (state.from) p.set("date_from", state.from);
  if (state.to) p.set("date_to", state.to);
  if (state.includeEmpty) p.set("include_empty", "true");
  p.set("format", fmt);
  return p.toString();
}

function renderSkeleton(rows = 8) {
  const body = $("sessions-body");
  body.innerHTML = "";
  for (let i = 0; i < rows; i++) {
    const tr = document.createElement("tr");
    tr.className = "skel-row";
    tr.innerHTML = Array.from({ length: COLSPAN }, () => '<td class="skel"><span></span></td>').join("");
    body.appendChild(tr);
  }
}

function renderEmpty() {
  $("sessions-body").innerHTML = `
    <tr><td colspan="${COLSPAN}">
      <div class="empty-state">
        <div class="big">⬡</div>
        <div>No sessions match these filters.</div>
      </div>
    </td></tr>`;
}

async function loadSessions() {
  clearTimeout(state.activeRefreshTimer);
  state.activeRefreshTimer = null;
  renderSkeleton();
  let data;
  try {
    data = await api("/api/sessions?" + sessionsQuery());
  } catch (e) {
    $("sessions-body").innerHTML =
      `<tr><td colspan="${COLSPAN}"><div class="empty-state">Failed to load: ${esc(e.message)}</div></td></tr>`;
    return;
  }
  state.total = data.total;
  const body = $("sessions-body");
  body.innerHTML = "";

  if (!data.items.length) {
    renderEmpty();
  } else {
    for (const s of data.items) body.appendChild(buildRow(s));
  }

  const from = state.total ? state.offset + 1 : 0;
  const to = Math.min(state.offset + state.limit, state.total);
  $("pg-info").textContent = `${from}–${to} of ${state.total}`;
  $("pg-prev").disabled = state.offset === 0;
  $("pg-next").disabled = to >= state.total;

  // auto-refresh if any session on this page is still active
  if (data.items.some((s) => s.is_active)) {
    state.activeRefreshTimer = setTimeout(loadSessions, 30000);
  }
}

function buildRow(s) {
  const tr = document.createElement("tr");
  tr.className = "session-row";
  tr.dataset.id = s.id;

  const models = s.models.length
    ? s.models.map((m) => `<span class="model-chip">${esc(m)}</span>`).join(" ")
    : `<span class="muted" title="model not recorded by this tool">—</span>`;
  const status = s.is_active
    ? `<span class="pill pill-active"><span class="dot"></span>${esc(s.active_status || "active")}</span>`
    : `<span class="pill pill-closed">closed</span>`;
  const est = estimateCost(s.input_tokens, s.output_tokens, s.models);
  const cost = est
    ? `<div class="cost" title="Estimated from ${esc(est.model)} pricing — excludes cache tokens">~${fmtCost(est)}</div>`
    : "";

  const tagChips = (s.tags || []).map(
    (t) => `<span class="tag-chip" data-tag="${esc(t)}">${esc(t)}</span>`
  ).join("");

  tr.innerHTML = `
    <td><span class="badge ${esc(s.tool)}">${esc(s.tool)}</span></td>
    <td class="title-cell" title="${esc(s.title)}"><span class="chev" title="Show details">▸</span>${esc(s.title)}${tagChips}</td>
    <td class="desc-cell" title="${esc(s.description)}">${esc(s.description || "")}</td>
    <td title="${esc(s.project_path)}">${esc(s.project_name || "—")}</td>
    <td>${models}</td>
    <td title="${esc(s.started_at)}">${fmtDate(s.started_at)}</td>
    <td title="${esc(s.ended_at)}">${relTime(s.ended_at)}</td>
    <td class="num">${s.message_count}</td>
    <td class="num">${fmtTokens(s.input_tokens)} / ${fmtTokens(s.output_tokens)}${cost}</td>
    <td>${status}</td>
    <td>
      <button class="btn sm act-resume" title="Resume session">▶</button>
      <button class="btn sm act-copy" title="Copy resume command">⧉</button>
    </td>`;
  tr.querySelector(".act-resume").onclick = (e) => { e.stopPropagation(); doResume(s.id); };
  tr.querySelector(".act-copy").onclick = (e) => { e.stopPropagation(); doCopy(s.id); };
  tr.onclick = () => toggleRow(tr, s);
  return tr;
}

async function doResume(id) {
  try {
    const r = await api(`/api/resume/${id}`, { method: "POST" });
    toast(`Opened ${r.terminal_used}`);
  } catch (e) {
    toast("Resume failed: " + e.message, 4000);
  }
}

async function doCopy(id) {
  try {
    const r = await api(`/api/resume/${id}/command`);
    await navigator.clipboard.writeText(r.command);
    toast("Command copied to clipboard");
  } catch (e) {
    toast("Copy failed: " + e.message, 4000);
  }
}

// ---------- expandable row (accordion) ----------

function collapseRow(tr) {
  tr.classList.remove("expanded");
  tr.querySelector(".chev")?.classList.remove("open");
  const detail = tr.nextElementSibling;
  if (detail && detail.classList.contains("detail-row")) detail.remove();
}

function toggleRow(tr, s) {
  const isOpen = tr.classList.contains("expanded");
  document.querySelectorAll("tr.session-row.expanded").forEach(collapseRow);   // accordion: one at a time
  if (!isOpen) expandRow(tr, s);
}

function metaRows(s) {
  const est = estimateCost(s.input_tokens, s.output_tokens, s.models);
  return [
    ["Session ID", s.id],
    ["Project", s.project_path || "—"],
    ["Git branch", s.git_branch || "—"],
    ["Model", s.models.join(", ") || "—"],
    ["CLI version", s.cli_version || "—"],
    ["Started", fmtDate(s.started_at)],
    ["Last activity", fmtDate(s.ended_at)],
    ["Messages", s.message_count],
    ["User prompts", s.user_prompt_count],
    ["Tokens in/out", `${fmtTokens(s.input_tokens)} / ${fmtTokens(s.output_tokens)}`],
    ["Est. cost", est ? `~${fmtCost(est)}` : "—"],
    ["Cache create/read", `${fmtTokens(s.cache_creation_tokens)} / ${fmtTokens(s.cache_read_tokens)}`],
    ["Source file", s.file_path],
    ["Status", s.is_active ? (s.active_status || "active") : "closed"],
  ];
}

function expandRow(tr, s) {
  tr.classList.add("expanded");
  tr.querySelector(".chev")?.classList.add("open");

  const detail = document.createElement("tr");
  detail.className = "detail-row";
  const meta = metaRows(s)
    .map(([k, v]) => `<div><span class="k">${esc(k)}</span><span class="v">${esc(String(v))}</span></div>`)
    .join("");
  detail.innerHTML = `
    <td colspan="${COLSPAN}"><div class="detail-inner">
      ${s.description ? `<div class="detail-desc">${esc(s.description)}</div>` : ""}
      <div class="detail-grid">${meta}</div>
      <div class="detail-actions">
        <button class="btn primary d-resume" title="Resume session">▶ Resume session</button>
        <button class="btn d-copy" title="Copy resume command">⧉ Copy command</button>
      </div>
      <div class="detail-tags"><span class="detail-tags-label">Tags</span><span class="tags-chips"></span><input class="tag-input toolbar" placeholder="Add tag…" maxlength="30"><button class="btn sm tag-add">Add</button></div>
      <div class="detail-prompts"><h4>Prompt timeline</h4><div class="dp-body muted">Loading…</div></div>
      <details class="diff-section">
        <summary>Git commits during this session</summary>
        <div class="diff-body muted">Loading…</div>
      </details>
    </div></td>`;
  tr.after(detail);

  detail.querySelector(".d-resume").onclick = () => doResume(s.id);
  detail.querySelector(".d-copy").onclick = () => doCopy(s.id);

  // render removable tag chips in the detail panel
  function renderDetailTags(tags) {
    const container = detail.querySelector(".tags-chips");
    if (!container) return;
    container.innerHTML = (tags || []).map(
      (t) => `<span class="tag-chip removable" data-tag="${esc(t)}">${esc(t)} <button class="tag-rm" aria-label="Remove tag ${esc(t)}">✕</button></span>`
    ).join("");
    container.querySelectorAll(".tag-rm").forEach((btn) => {
      btn.onclick = async () => {
        const tag = btn.closest(".tag-chip").dataset.tag;
        try {
          const res = await api(`/api/sessions/${s.id}/tags/${encodeURIComponent(tag)}`, { method: "DELETE" });
          renderDetailTags(res.tags);
          refreshRowChips(res.tags);
        } catch (e) {
          toast("Remove tag failed: " + e.message, 3000);
        }
      };
    });
  }

  // update chips in the summary row too
  function refreshRowChips(tags) {
    const titleCell = tr.querySelector(".title-cell");
    if (!titleCell) return;
    titleCell.querySelectorAll(".tag-chip").forEach((c) => c.remove());
    (tags || []).forEach((t) => {
      const chip = document.createElement("span");
      chip.className = "tag-chip";
      chip.dataset.tag = t;
      chip.textContent = t;
      titleCell.appendChild(chip);
    });
  }

  // tag add button
  const tagInput = detail.querySelector(".tag-input");
  detail.querySelector(".tag-add").onclick = async () => {
    const val = tagInput.value.trim();
    if (!val) return;
    try {
      const res = await api(`/api/sessions/${s.id}/tags`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tag: val }),
      });
      tagInput.value = "";
      renderDetailTags(res.tags);
      refreshRowChips(res.tags);
    } catch (e) {
      toast("Add tag failed: " + e.message, 3000);
    }
  };
  tagInput.onkeydown = (e) => { if (e.key === "Enter") detail.querySelector(".tag-add").click(); };

  // lazy-load diff on <details> toggle
  const diffSection = detail.querySelector(".diff-section");
  let diffLoaded = false;
  diffSection.addEventListener("toggle", () => {
    if (!diffSection.open || diffLoaded) return;
    diffLoaded = true;
    api(`/api/sessions/${s.id}/diff`).then((res) => {
      if (!detail.isConnected) return;
      const body = detail.querySelector(".diff-body");
      body.classList.remove("muted");
      if (res.error) {
        body.textContent = res.error;
      } else if (!res.commits || !res.commits.length) {
        body.textContent = "No commits found in this time range.";
      } else {
        body.innerHTML = `<ul>${res.commits.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`;
      }
    }).catch((e) => {
      const body = detail.querySelector(".diff-body");
      if (body) body.textContent = "Failed to load commits: " + e.message;
    });
  });

  // Lazy-load prompts + resume availability from the per-session endpoint.
  api(`/api/sessions/${s.id}`).then((full) => {
    if (!detail.isConnected) return;
    const dp = detail.querySelector(".dp-body");
    dp.classList.remove("muted");
    dp.innerHTML = full.prompts.length
      ? full.prompts.map((p) => `<div class="prompt"><div class="pts">${fmtDate(p.ts)}</div>${esc(p.text)}</div>`).join("")
      : '<span class="muted">No prompts recorded.</span>';
    const resume = detail.querySelector(".d-resume");
    const copy = detail.querySelector(".d-copy");
    resume.disabled = !full.resume_command;
    copy.disabled = !full.resume_command;
    if (full.resume_blocked_reason) resume.title = full.resume_blocked_reason;
    renderDetailTags(full.tags || s.tags || []);
  }).catch((e) => {
    const dp = detail.querySelector(".dp-body");
    if (dp) dp.textContent = "Failed to load prompts: " + e.message;
    renderDetailTags(s.tags || []);
  });
}

// ---------- stats ----------

async function loadStats() {
  const s = await api("/api/stats");
  const t = s.totals;
  $("stat-cards").innerHTML = [
    ["Sessions", t.sessions],
    ["Prompts", t.prompts],
    ["Projects", t.projects],
    ["Input tokens", fmtTokens(t.input_tokens)],
    ["Output tokens", fmtTokens(t.output_tokens)],
    ["Est. Cost", fmtCost({ cost: s.total_cost || 0 })],
  ].map(([k, v]) => `<div class="card"><div class="v">${v ?? 0}</div><div class="k">${k}</div></div>`).join("");

  charts.forEach((c) => c.destroy());
  charts = [];
  const grid = { color: "rgba(123,138,153,.15)" };
  const ticks = { color: "#7b8a99" };
  const opts = { responsive: true, plugins: { legend: { labels: { color: "#d8e1ea" } } },
    scales: { x: { grid, ticks }, y: { grid, ticks } } };

  charts.push(new Chart($("ch-day"), {
    type: "bar",
    data: {
      labels: s.per_day.map((d) => d.date),
      datasets: [
        { label: "Claude", data: s.per_day.map((d) => d.claude), backgroundColor: "#e8833a" },
        { label: "Antigravity", data: s.per_day.map((d) => d.antigravity), backgroundColor: "#4f9cf9" },
      ],
    },
    options: { ...opts, scales: { x: { ...opts.scales.x, stacked: true }, y: { ...opts.scales.y, stacked: true } } },
  }));

  const topProjects = s.per_project.slice(0, 12);
  charts.push(new Chart($("ch-project"), {
    type: "bar",
    data: {
      labels: topProjects.map((p) => p.name),
      datasets: [{ label: "Sessions", data: topProjects.map((p) => p.count), backgroundColor: "#3b82f6" }],
    },
    options: { ...opts, indexAxis: "y" },
  }));

  charts.push(new Chart($("ch-model"), {
    type: "doughnut",
    data: {
      labels: s.per_model.map((m) => m.model),
      datasets: [{ data: s.per_model.map((m) => m.count),
        backgroundColor: ["#e8833a", "#3b82f6", "#2ecc71", "#9b59b6", "#f1c40f", "#e74c3c", "#1abc9c"] }],
    },
    options: { responsive: true, plugins: { legend: { labels: { color: "#d8e1ea" } } } },
  }));

  charts.push(new Chart($("ch-tokens"), {
    type: "line",
    data: {
      labels: s.tokens_per_day.map((d) => d.date),
      datasets: [
        { label: "Input", data: s.tokens_per_day.map((d) => d.input), borderColor: "#3b82f6", tension: .3 },
        { label: "Output", data: s.tokens_per_day.map((d) => d.output), borderColor: "#2ecc71", tension: .3 },
      ],
    },
    options: opts,
  }));

  if (s.cost_per_day && s.cost_per_day.length) {
    charts.push(new Chart($("ch-cost"), {
      type: "bar",
      data: {
        labels: s.cost_per_day.map((d) => d.date),
        datasets: [{ label: "Est. cost ($)", data: s.cost_per_day.map((d) => Number(d.cost) || 0), backgroundColor: "#e8833a" }],
      },
      options: { ...opts },
    }));
  }

  if (s.last_scan_at) $("last-scan").textContent = "indexed " + relTime(s.last_scan_at);
}

// ---------- filters / wiring ----------

async function loadFilterOptions() {
  const s = await api("/api/stats");
  $("f-project").innerHTML = '<option value="">All projects</option>' +
    s.projects.map((p) => `<option value="${esc(p)}">${esc(p.split("/").pop())}</option>`).join("");
  $("f-model").innerHTML = '<option value="">All models</option>' +
    s.per_model.map((m) => `<option value="${esc(m.model)}">${esc(m.model)}</option>`).join("");
  if (s.tags && s.tags.length) {
    $("f-tag").innerHTML = '<option value="">All tags</option>' +
      s.tags.map((t) => `<option value="${esc(t.tag)}">${esc(t.tag)} (${t.count})</option>`).join("");
  }
  if (s.last_scan_at) $("last-scan").textContent = "indexed " + relTime(s.last_scan_at);
}

function bindFilters() {
  const reload = () => { state.offset = 0; loadSessions().catch((e) => toast(e.message)); };
  $("f-tool").onchange = (e) => { state.tool = e.target.value; reload(); };
  $("f-project").onchange = (e) => { state.project = e.target.value; reload(); };
  $("f-model").onchange = (e) => { state.model = e.target.value; reload(); };
  $("f-tag").onchange = (e) => { state.tag = e.target.value; reload(); };
  $("f-from").onchange = (e) => { state.from = e.target.value; reload(); };
  $("f-to").onchange = (e) => { state.to = e.target.value; reload(); };
  $("f-empty").onchange = (e) => { state.includeEmpty = e.target.checked; reload(); };
  let timer;
  $("f-search").oninput = (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => { state.q = e.target.value.trim(); reload(); }, 300);
  };
  document.querySelectorAll("th.sortable").forEach((th) => {
    th.onclick = () => {
      const col = th.dataset.sort;
      if (state.sort === col) state.dir = state.dir === "asc" ? "desc" : "asc";
      else { state.sort = col; state.dir = "desc"; }
      document.querySelectorAll("th.sortable").forEach((h) => h.classList.remove("sorted-asc", "sorted-desc"));
      th.classList.add(state.dir === "asc" ? "sorted-asc" : "sorted-desc");
      reload();
    };
  });
  $("pg-prev").onclick = () => { state.offset = Math.max(0, state.offset - state.limit); loadSessions(); };
  $("pg-next").onclick = () => { state.offset += state.limit; loadSessions(); };

  // export button / dropdown
  const exportBtn = $("btn-export");
  const exportMenu = $("export-menu");
  const exportWrap = exportBtn.closest(".export-wrap");
  exportBtn.onclick = (e) => {
    e.stopPropagation();
    exportMenu.classList.toggle("hidden");
  };
  exportMenu.querySelectorAll("button[data-fmt]").forEach((btn) => {
    btn.onclick = () => {
      window.location.href = "/api/sessions/export?" + exportQuery(btn.dataset.fmt);
      exportMenu.classList.add("hidden");
    };
  });
  document.addEventListener("click", (e) => {
    if (!exportWrap.contains(e.target)) exportMenu.classList.add("hidden");
  });
}

function bindTabs() {
  $("tab-sessions").onclick = () => {
    $("tab-sessions").classList.add("active");
    $("tab-stats").classList.remove("active");
    $("view-sessions").classList.remove("hidden");
    $("view-stats").classList.add("hidden");
  };
  $("tab-stats").onclick = () => {
    $("tab-stats").classList.add("active");
    $("tab-sessions").classList.remove("active");
    $("view-stats").classList.remove("hidden");
    $("view-sessions").classList.add("hidden");
    clearTimeout(state.activeRefreshTimer);
    state.activeRefreshTimer = null;
    loadStats().catch((e) => toast(e.message));
  };
}

$("btn-refresh").onclick = async () => {
  const btn = $("btn-refresh");
  btn.disabled = true;
  btn.textContent = "Scanning…";
  try {
    const r = await api("/api/scan", { method: "POST" });
    toast(`Scanned ${r.files_parsed} changed file(s) in ${r.duration_ms}ms`);
    await Promise.all([loadSessions(), loadFilterOptions()]);
    if (!$("view-stats").classList.contains("hidden")) await loadStats();
  } catch (e) {
    toast("Scan failed: " + e.message, 4000);
  } finally {
    btn.disabled = false;
    btn.textContent = "⟳ Refresh";
  }
};

// keyboard: "/" focuses search, Esc collapses any open row
const TYPING_TAGS = new Set(["INPUT", "SELECT", "TEXTAREA"]);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    document.querySelectorAll("tr.session-row.expanded").forEach(collapseRow);
  } else if (e.key === "/" && !TYPING_TAGS.has(document.activeElement?.tagName)) {
    e.preventDefault();
    $("f-search").focus();
  }
});

// ---------- theme toggle ----------

(function initTheme() {
  const saved = localStorage.getItem("theme");
  if (saved === "light") {
    document.documentElement.setAttribute("data-theme", "light");
  }
  const btn = $("btn-theme");
  function updateIcon() {
    const isLight = document.documentElement.getAttribute("data-theme") === "light";
    btn.textContent = isLight ? "☾" : "☀";
  }
  updateIcon();
  btn.onclick = () => {
    const isLight = document.documentElement.getAttribute("data-theme") === "light";
    if (isLight) {
      document.documentElement.removeAttribute("data-theme");
      localStorage.setItem("theme", "dark");
    } else {
      document.documentElement.setAttribute("data-theme", "light");
      localStorage.setItem("theme", "light");
    }
    updateIcon();
  };
})();

bindTabs();
bindFilters();
loadFilterOptions().catch(() => {});
loadSessions().catch((e) => toast(e.message, 4000));
