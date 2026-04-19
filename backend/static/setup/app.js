(function () {
  const state = {
    steps: [],
    context: { project_root: "" },
    progress: {
      completed: {},
      checklist_done: {},
      notes: {},
      last_step_id: null,
    },
    activeId: null,
    saveTimer: null,
  };

  const $ = (sel) => document.querySelector(sel);
  const nav = $("#nav-steps");
  const content = $("#content");
  const toast = $("#status-toast");
  const prEl = $("#project-root");

  function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add("show");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => toast.classList.remove("show"), 2200);
  }

  function saveProgress() {
    fetch("/api/setup/progress", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.progress),
    })
      .then((r) => {
        if (!r.ok) throw new Error(r.statusText);
        showToast("Progress saved");
      })
      .catch(() => showToast("Save failed — is the backend running?"));
  }

  function scheduleSave() {
    clearTimeout(state.saveTimer);
    state.saveTimer = setTimeout(saveProgress, 600);
  }

  function renderNav() {
    nav.innerHTML = "";
    state.steps.forEach((step) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      const done = state.progress.completed[step.id];
      btn.innerHTML = `<span>${escapeHtml(step.title)}</span>${
        done ? '<span class="done-badge">✓</span>' : ""
      }`;
      if (state.activeId === step.id) btn.classList.add("active");
      btn.addEventListener("click", () => {
        state.activeId = step.id;
        state.progress.last_step_id = step.id;
        scheduleSave();
        renderNav();
        renderContent();
      });
      li.appendChild(btn);
      nav.appendChild(li);
    });
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function fillCommand(cmd) {
    return cmd.replace(/\{project_root\}/g, state.context.project_root || "$PROJECT_ROOT");
  }

  function copyText(text) {
    navigator.clipboard.writeText(text).then(
      () => showToast("Copied"),
      () => showToast("Copy failed")
    );
  }

  function renderContent() {
    const step = state.steps.find((s) => s.id === state.activeId) || state.steps[0];
    if (!step) {
      content.innerHTML = "<p>No steps loaded.</p>";
      return;
    }

    const checklist = step.checklist || [];
    let checklistHtml = "";
    if (checklist.length) {
      const arr = state.progress.checklist_done[step.id] || checklist.map(() => false);
      while (arr.length < checklist.length) arr.push(false);
      checklistHtml = `<section><h3>Checklist</h3><ul class="checklist">${checklist
        .map((line, i) => {
          const checked = arr[i] ? " checked" : "";
          return `<li><input type="checkbox" data-ci="${i}"${checked} id="cl-${step.id}-${i}"/><label for="cl-${step.id}-${i}">${escapeHtml(
            line
          )}</label></li>`;
        })
        .join("")}</ul></section>`;
    }

    const commands = step.commands || [];
    let cmdHtml = "";
    if (commands.length) {
      cmdHtml = `<section><h3>Commands</h3>${commands
        .map((c) => {
          const filled = fillCommand(c.command);
          return `<div class="command-block"><div class="label">${escapeHtml(c.label)}</div><pre>${escapeHtml(
            filled
          )}</pre><div class="row-actions"><button type="button" class="btn btn-primary copy-cmd">Copy</button></div></div>`;
        })
        .join("")}</section>`;
    }

    const hints = step.hints || [];
    const hintsHtml = hints.length
      ? `<section><h3>Tips</h3><ul class="hints">${hints.map((h) => `<li>${escapeHtml(h)}</li>`).join("")}</ul></section>`
      : "";

    const docs = step.doc_refs || [];
    const docsHtml = docs.length
      ? `<section><h3>Documentation</h3><div class="docs">${docs
          .map(
            (d) =>
              `<span>${escapeHtml(d.label)}: <code>${escapeHtml(d.path)}</code></span>`
          )
          .join("<br/>")}</div></section>`
      : "";

    const noteVal = state.progress.notes[step.id] || "";

    content.innerHTML = `
      <h2>${escapeHtml(step.title)}</h2>
      <p class="summary">${escapeHtml(step.summary || "")}</p>
      ${checklistHtml}
      ${cmdHtml}
      ${hintsHtml}
      ${docsHtml}
      <section class="notes"><h3>Your notes (this step)</h3>
        <textarea id="step-note" placeholder="Optional notes, corrections, dates…">${escapeHtml(noteVal)}</textarea>
      </section>
      <div class="step-actions">
        <label class="mark-done"><input type="checkbox" id="step-done" ${
          state.progress.completed[step.id] ? "checked" : ""
        }/> Mark step complete</label>
        <button type="button" class="btn btn-primary" id="btn-save">Save now</button>
      </div>
    `;

    content.querySelectorAll(".command-block").forEach((block) => {
      const pre = block.querySelector("pre");
      block.querySelector(".copy-cmd")?.addEventListener("click", () => {
        if (pre) copyText(pre.textContent || "");
      });
    });

    content.querySelectorAll('.checklist input[type="checkbox"]').forEach((el) => {
      el.addEventListener("change", () => {
        const i = parseInt(el.getAttribute("data-ci"), 10);
        if (!state.progress.checklist_done[step.id]) {
          state.progress.checklist_done[step.id] = checklist.map(() => false);
        }
        const row = state.progress.checklist_done[step.id];
        while (row.length < checklist.length) row.push(false);
        row[i] = el.checked;
        scheduleSave();
        renderNav();
      });
    });

    const ta = $("#step-note");
    if (ta) {
      ta.addEventListener("input", () => {
        state.progress.notes[step.id] = ta.value;
        scheduleSave();
      });
    }

    const doneCb = $("#step-done");
    if (doneCb) {
      doneCb.addEventListener("change", () => {
        state.progress.completed[step.id] = doneCb.checked;
        scheduleSave();
        renderNav();
      });
    }

    $("#btn-save")?.addEventListener("click", saveProgress);
  }

  async function init() {
    try {
      const [ctxRes, stepsRes, progRes] = await Promise.all([
        fetch("/api/setup/context"),
        fetch("/api/setup/steps"),
        fetch("/api/setup/progress"),
      ]);
      state.context = await ctxRes.json();
      const stepsPayload = await stepsRes.json();
      state.steps = stepsPayload.steps || [];
      state.progress = await progRes.json();

      prEl.textContent = state.context.project_root || "(unknown)";

      state.activeId =
        state.progress.last_step_id && state.steps.some((s) => s.id === state.progress.last_step_id)
          ? state.progress.last_step_id
          : state.steps[0]?.id || null;

      renderNav();
      renderContent();
    } catch (e) {
      content.innerHTML =
        "<p>Could not load setup data. Start the backend: <code>uvicorn backend.app:app --host 127.0.0.1 --port 8000</code></p>";
    }
  }

  init();
})();
