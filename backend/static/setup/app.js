(function () {
  const state = {
    steps: [],
    context: { project_root: "", launch_enabled: false },
    progress: {
      completed: {},
      checklist_done: {},
      notes: {},
      last_step_id: null,
      mjpeg_port: 8080,
    },
    activeId: null,
    saveTimer: null,
  };

  const $ = (sel) => document.querySelector(sel);
  const nav = $("#nav-steps");
  const content = $("#content");
  const toast = $("#status-toast");
  const prEl = $("#project-root");
  const mjpegInput = $("#mjpeg-port");

  function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add("show");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => toast.classList.remove("show"), 2200);
  }

  function getMjpegPort() {
    const v = parseInt(mjpegInput?.value, 10);
    if (!Number.isFinite(v) || v < 1) return state.progress.mjpeg_port || 8080;
    return v;
  }

  function saveProgress() {
    state.progress.mjpeg_port = getMjpegPort();
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

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function fillCommand(cmd) {
    return cmd.replace(/\{project_root\}/g, state.context.project_root || "$PROJECT_ROOT");
  }

  function docHref(relPath) {
    return "/api/setup/doc?path=" + encodeURIComponent(relPath);
  }

  function vscodeFileUrl(absPath) {
    const p = absPath.replace(/\\/g, "/");
    return "vscode://file" + encodeURI(p);
  }

  function cursorFileUrl(absPath) {
    const p = absPath.replace(/\\/g, "/");
    return "cursor://file" + encodeURI(p);
  }

  function absProjectPath(rel) {
    const root = (state.context.project_root || "").replace(/\/$/, "");
    const r = String(rel || "").replace(/^\//, "");
    return root + "/" + r;
  }

  function copyText(text) {
    navigator.clipboard.writeText(text).then(
      () => showToast("Copied — paste in Terminal"),
      () => showToast("Copy failed")
    );
  }

  /** @returns {'red'|'yellow'|'green'} */
  function stepSignal(step) {
    const id = step.id;
    const n = (step.checklist || []).length;
    const done = state.progress.checklist_done[id] || [];
    const checked = done.filter(Boolean).length;
    const complete = state.progress.completed[id];
    const hasNotes = ((state.progress.notes[id] || "").trim().length > 0);
    if (complete || (n > 0 && checked === n)) return "green";
    if (checked > 0 || hasNotes) return "yellow";
    return "red";
  }

  function signalHtml(status) {
    const t = status === "green" ? "Complete" : status === "yellow" ? "In progress" : "Not started";
    return `<span class="signal ${status}" title="${escapeHtml(t)}"></span>`;
  }

  function renderNav() {
    nav.innerHTML = "";
    state.steps.forEach((step) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      const sig = stepSignal(step);
      btn.innerHTML = `${signalHtml(sig)}<span class="step-title">${escapeHtml(step.title)}</span>`;
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

  function renderChecklist(step) {
    const checklist = step.checklist || [];
    if (!checklist.length) return "";

    const arr = state.progress.checklist_done[step.id] || checklist.map(() => false);
    while (arr.length < checklist.length) arr.push(false);

    return `<section><h3>Checklist</h3>
      <p class="checklist-intro">Check each box only after you have <strong>verified</strong> it. Use <strong>Record</strong> hints to capture output in Notes below.</p>
      ${checklist
        .map((entry, i) => {
          const item = typeof entry === "string" ? { item: entry, verify: "", record: "" } : entry;
          const checked = arr[i] ? " checked" : "";
          const id = `cl-${step.id}-${i}`;
          return `<div class="checklist-block">
            <div class="row-top">
              <input type="checkbox" data-ci="${i}" id="${id}"${checked}/>
              <div>
                <div class="item-text">${escapeHtml(item.item || "")}</div>
                ${item.verify ? `<p class="verify"><strong>How to verify:</strong> ${escapeHtml(item.verify)}</p>` : ""}
                ${item.record ? `<p class="record"><strong>What to record:</strong> ${escapeHtml(item.record)}</p>` : ""}
              </div>
            </div>
          </div>`;
        })
        .join("")}</section>`;
  }

  function renderDocs(step) {
    const docs = step.doc_refs || [];
    if (!docs.length) return "";
    return `<section><h3>Documentation</h3><div class="doc-list">${docs
      .map(
        (d) =>
          `<a href="${docHref(d.path)}" target="_blank" rel="noopener">${escapeHtml(d.label)}</a> <span class="muted-path">(${escapeHtml(d.path)})</span>`
      )
      .join("")}</div></section>`;
  }

  function renderCommands(step) {
    const commands = step.commands || [];
    if (!commands.length) return "";
    const root = state.context.project_root || "";
    return `<section><h3>Commands</h3>
      <p class="terminal-hint">Browsers cannot start your OS terminal automatically. Copy the command, switch to Terminal, paste (⌘V / Ctrl+Shift+V), then Enter. Use the editor links to open a script for review.</p>
      ${commands
        .map((c) => {
          const filled = fillCommand(c.command);
          const ep = c.editor_path;
          const abs = ep ? absProjectPath(ep) : "";
          const ed = ep
            ? `<div class="row-actions">
                 <a class="btn" href="${vscodeFileUrl(abs)}" title="Open file in VS Code">Open in VS Code</a>
                 <a class="btn" href="${cursorFileUrl(abs)}" title="Open file in Cursor">Open in Cursor</a>
               </div>`
            : "";
          return `<div class="command-block"><div class="label">${escapeHtml(c.label)}</div><pre>${escapeHtml(filled)}</pre>
            <div class="row-actions"><button type="button" class="btn btn-primary copy-cmd">Copy command</button></div>
            ${ed}
          </div>`;
        })
        .join("")}</section>`;
  }

  function renderLinks(step) {
    const links = step.links || [];
    const port = getMjpegPort();
    if (!links.length) return "";
    return `<section><h3>Quick links</h3><div class="quick-links">${links
      .map((L) => {
        if (L.href) {
          return `<div class="ql"><a href="${escapeHtml(L.href)}" target="_blank" rel="noopener">${escapeHtml(L.label)}</a>${L.note ? `<p class="ql-note">${escapeHtml(L.note)}</p>` : ""}</div>`;
        }
        if (L.href_template) {
          const href = L.href_template.replace(/\{mjpeg_port\}/g, String(port));
          return `<div class="ql"><a href="${escapeHtml(href)}" target="_blank" rel="noopener">${escapeHtml(L.label)}</a>${L.note ? `<p class="ql-note">${escapeHtml(L.note)}</p>` : ""}</div>`;
        }
        if (L.launch) {
          const can = state.context.launch_enabled;
          return `<div class="ql"><button type="button" class="btn btn-primary launch-btn" data-launch="${escapeHtml(L.launch)}"${can ? "" : " disabled"}>${escapeHtml(L.label)}</button>${L.note ? `<p class="ql-note">${escapeHtml(L.note)}</p>` : ""}${!can ? `<p class="ql-note">Enable server-side launch: set <code>SETUP_ALLOW_LAUNCH=1</code> and restart uvicorn (localhost only).</p>` : ""}</div>`;
        }
        return "";
      })
      .join("")}</div></section>`;
  }

  function renderContent() {
    const step = state.steps.find((s) => s.id === state.activeId) || state.steps[0];
    if (!step) {
      content.innerHTML = "<p>No steps loaded.</p>";
      return;
    }

    const checklist = step.checklist || [];
    const hints = step.hints || [];
    const hintsHtml = hints.length
      ? `<section><h3>Tips</h3><ul class="hints">${hints.map((h) => `<li>${escapeHtml(h)}</li>`).join("")}</ul></section>`
      : "";

    const noteVal = state.progress.notes[step.id] || "";
    const sig = stepSignal(step);

    content.innerHTML = `
      <h2>${signalHtml(sig)} ${escapeHtml(step.title)}</h2>
      <p class="summary">${escapeHtml(step.summary || "")}</p>
      ${renderChecklist(step)}
      ${renderCommands(step)}
      ${renderLinks(step)}
      ${renderDocs(step)}
      ${hintsHtml}
      <section class="notes"><h3>Notes (this step)</h3>
        <p class="terminal-hint">Use this field for command output, versions, ports, or reminders. Saved with the rest of your progress.</p>
        <textarea id="step-note" placeholder="Paste output, dates, non-secret reminders…">${escapeHtml(noteVal)}</textarea>
      </section>
      <div class="step-actions">
        <label class="mark-done"><input type="checkbox" id="step-done" ${
          state.progress.completed[step.id] ? "checked" : ""
        }/> Mark entire step complete</label>
        <button type="button" class="btn btn-primary" id="btn-save">Save now</button>
      </div>
    `;

    content.querySelectorAll(".command-block").forEach((block) => {
      const pre = block.querySelector("pre");
      block.querySelector(".copy-cmd")?.addEventListener("click", () => {
        if (pre) copyText(pre.textContent || "");
      });
    });

    content.querySelectorAll('.checklist-block input[type="checkbox"]').forEach((el) => {
      el.addEventListener("change", () => {
        const i = parseInt(el.getAttribute("data-ci") || "0", 10);
        if (!state.progress.checklist_done[step.id]) {
          state.progress.checklist_done[step.id] = checklist.map(() => false);
        }
        const row = state.progress.checklist_done[step.id];
        while (row.length < checklist.length) row.push(false);
        row[i] = el.checked;
        scheduleSave();
        renderNav();
        const h2 = content.querySelector("h2");
        if (h2) h2.innerHTML = `${signalHtml(stepSignal(step))} ${escapeHtml(step.title)}`;
      });
    });

    content.querySelectorAll(".launch-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-launch");
        if (!id) return;
        fetch("/api/setup/launch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ launch: id }),
        })
          .then((r) => r.json().then((j) => ({ ok: r.ok, j })))
          .then(({ ok, j }) => {
            if (ok) showToast("Started (pid " + (j.pid || "?") + ")");
            else showToast(j.detail || "Launch failed");
          })
          .catch(() => showToast("Launch request failed"));
      });
    });

    const ta = $("#step-note");
    if (ta) {
      ta.addEventListener("input", () => {
        state.progress.notes[step.id] = ta.value;
        scheduleSave();
        renderNav();
        const h2 = content.querySelector("h2");
        if (h2) h2.innerHTML = `${signalHtml(stepSignal(step))} ${escapeHtml(step.title)}`;
      });
    }

    const doneCb = $("#step-done");
    if (doneCb) {
      doneCb.addEventListener("change", () => {
        state.progress.completed[step.id] = doneCb.checked;
        scheduleSave();
        renderNav();
        const h2 = content.querySelector("h2");
        if (h2) h2.innerHTML = `${signalHtml(stepSignal(step))} ${escapeHtml(step.title)}`;
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
      if (typeof state.progress.mjpeg_port !== "number" || state.progress.mjpeg_port < 1) {
        state.progress.mjpeg_port = 8080;
      }
      if (mjpegInput) mjpegInput.value = String(state.progress.mjpeg_port);

      prEl.textContent = state.context.project_root || "(unknown)";

      state.activeId =
        state.progress.last_step_id && state.steps.some((s) => s.id === state.progress.last_step_id)
          ? state.progress.last_step_id
          : state.steps[0]?.id || null;

      mjpegInput?.addEventListener("change", () => {
        state.progress.mjpeg_port = getMjpegPort();
        scheduleSave();
        renderContent();
      });

      renderNav();
      renderContent();
    } catch (e) {
      content.innerHTML =
        "<p>Could not load setup data. Start the backend: <code>uvicorn backend.app:app --host 127.0.0.1 --port 8000</code></p>";
    }
  }

  init();
})();
