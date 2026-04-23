(function () {
  const state = {
    steps: [],
    context: { project_root: "", launch_enabled: false },
    progress: {
      completed: {},
      checklist_done: {},
      notes: {},
      last_step_id: null,
      mjpeg_port: 8001,
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
  const mjpegStatusEl = $("#mjpeg-edge-status");
  let edgeHealthTimer = null;

  const TEXT_SIZE_KEY = "billiards-setup-text-size";
  const PROGRESS_LSK = "billiards-setup-progress-v1";
  const SIDEBAR_W_LSK = "billiards-setup-sidebar-width-px";
  const DEFAULT_SIDEBAR_PX = 300;
  const MAIN_MIN_PX = 280;
  /** Must match inline <head> script in index.html (root px drives all rem). */
  const TEXT_ROOT_PX = { small: "14px", medium: "17px", large: "28px" };

  function applyTextSize(size) {
    if (size !== "small" && size !== "medium" && size !== "large") size = "medium";
    document.documentElement.setAttribute("data-text-size", size);
    document.documentElement.style.fontSize = TEXT_ROOT_PX[size];
    try {
      localStorage.setItem(TEXT_SIZE_KEY, size);
    } catch (_) {
      /* ignore */
    }
    try {
      document.cookie =
        "setup_text_size=" +
        encodeURIComponent(size) +
        "; path=/; max-age=31536000; SameSite=Lax";
    } catch (_) {
      /* ignore */
    }
    document.querySelectorAll('input[name="text-size"]').forEach((el) => {
      el.checked = el.value === size;
    });
  }

  function initTextSizeControls() {
    const saved = document.documentElement.getAttribute("data-text-size") || "medium";
    applyTextSize(saved);
    document.querySelectorAll('input[name="text-size"]').forEach((el) => {
      const onPick = () => {
        if (el.checked) applyTextSize(el.value);
      };
      el.addEventListener("change", onPick);
      el.addEventListener("input", onPick);
    });
  }

  function readSavedSidebarWidth() {
    try {
      const v = parseInt(localStorage.getItem(SIDEBAR_W_LSK) || "", 10);
      if (Number.isFinite(v) && v > 0) return v;
    } catch (_) {
      /* ignore */
    }
    return DEFAULT_SIDEBAR_PX;
  }

  function clampSidebarWidth(w) {
    const min = 200;
    const max = Math.max(min, window.innerWidth - MAIN_MIN_PX);
    return Math.min(max, Math.max(min, Math.round(w)));
  }

  function applySidebarWidth(px) {
    const layout = document.querySelector(".layout");
    if (!layout) return;
    const w = clampSidebarWidth(px);
    layout.style.setProperty("--sidebar-px", `${w}px`);
  }

  function initSidebarResize() {
    const handle = document.getElementById("sidebar-resize");
    const layout = document.querySelector(".layout");
    if (!handle || !layout) return;

    function persistCurrentWidth() {
      try {
        const raw = getComputedStyle(layout).getPropertyValue("--sidebar-px").trim();
        const n = parseInt(raw, 10);
        if (Number.isFinite(n)) {
          localStorage.setItem(SIDEBAR_W_LSK, String(clampSidebarWidth(n)));
        }
      } catch (_) {
        /* ignore */
      }
    }

    applySidebarWidth(readSavedSidebarWidth());

    let startX = 0;
    let startW = 0;

    function onPointerDown(e) {
      if (e.button !== 0) return;
      e.preventDefault();
      startX = e.clientX;
      const wStr = getComputedStyle(layout).getPropertyValue("--sidebar-px").trim();
      const parsed = parseInt(wStr, 10);
      startW = Number.isFinite(parsed) ? parsed : DEFAULT_SIDEBAR_PX;
      document.body.classList.add("is-resizing-sidebar");
      const move = (ev) => {
        ev.preventDefault();
        const delta = ev.clientX - startX;
        applySidebarWidth(startW + delta);
      };
      const up = () => {
        document.removeEventListener("pointermove", move);
        document.removeEventListener("pointerup", up);
        document.removeEventListener("pointercancel", up);
        document.body.classList.remove("is-resizing-sidebar");
        persistCurrentWidth();
      };
      document.addEventListener("pointermove", move);
      document.addEventListener("pointerup", up);
      document.addEventListener("pointercancel", up);
    }

    handle.addEventListener("pointerdown", onPointerDown);

    handle.addEventListener("keydown", (e) => {
      const step = e.shiftKey ? 24 : 8;
      let w = parseInt(getComputedStyle(layout).getPropertyValue("--sidebar-px") || "300", 10);
      if (!Number.isFinite(w)) w = DEFAULT_SIDEBAR_PX;
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        w += e.key === "ArrowRight" ? step : -step;
        applySidebarWidth(w);
        persistCurrentWidth();
      }
    });

    handle.addEventListener("dblclick", (e) => {
      e.preventDefault();
      applySidebarWidth(DEFAULT_SIDEBAR_PX);
      persistCurrentWidth();
    });

    let resizeT = null;
    window.addEventListener("resize", () => {
      clearTimeout(resizeT);
      resizeT = setTimeout(() => {
        const raw = getComputedStyle(layout).getPropertyValue("--sidebar-px").trim();
        const w = parseInt(raw, 10);
        if (Number.isFinite(w)) {
          applySidebarWidth(w);
          persistCurrentWidth();
        }
      }, 100);
    });
  }

  function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add("show");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => toast.classList.remove("show"), 2200);
  }

  function getMjpegPort() {
    const v = parseInt(mjpegInput?.value, 10);
    if (!Number.isFinite(v) || v < 1) return state.progress.mjpeg_port || 8001;
    return v;
  }

  function getApiPort() {
    const p = state.context && state.context.api_port;
    if (typeof p === "number" && p >= 1 && p <= 65535) return p;
    if (typeof p === "string" && /^\d+$/.test(p)) {
      const n = parseInt(p, 10);
      if (n >= 1 && n <= 65535) return n;
    }
    const d = state.context && state.context.api_default_port;
    if (typeof d === "number" && d >= 1) return d;
    return 8000;
  }

  function resolveLinkHref(tpl) {
    return String(tpl)
      .replace(/\{mjpeg_port\}/g, String(getMjpegPort()))
      .replace(/\{api_port\}/g, String(getApiPort()));
  }

  async function refreshMjpegEdgeHealth() {
    if (!mjpegStatusEl) return;
    const port = getMjpegPort();
    mjpegStatusEl.classList.remove("mjpeg-ok", "mjpeg-bad");
    mjpegStatusEl.textContent = "Checking 127.0.0.1:" + port + "…";
    try {
      const r = await fetch(
        "/api/setup/edge-health?port=" + encodeURIComponent(String(port))
      );
      if (!r.ok) {
        mjpegStatusEl.classList.add("mjpeg-bad");
        mjpegStatusEl.textContent =
          "Could not run health check (HTTP " + r.status + ").";
        return;
      }
      const j = await r.json();
      if (j.ok) {
        mjpegStatusEl.classList.add("mjpeg-ok");
        mjpegStatusEl.textContent = "";
        mjpegStatusEl.appendChild(
          document.createTextNode("Port " + port + ": edge is up.")
        );
        mjpegStatusEl.appendChild(document.createElement("br"));
        mjpegStatusEl.appendChild(
          document.createTextNode(
            "Stream: http://127.0.0.1:" + port + "/mjpeg"
          )
        );
        return;
      }
      mjpegStatusEl.classList.add("mjpeg-bad");
      const d = (j.detail && String(j.detail)) || "no response";
      const rsn = j.reason || "";
      const root = JSON.stringify((state.context && state.context.project_root) || ".");
      const example =
        "cd " +
        root +
        " && .venv/bin/python3 -m edge.main --camera usb --calib calibration.json --mjpeg-port " +
        port +
        " (or match your model/camera flags)";
      if (
        rsn === "connection_refused" ||
        /Connection refused|Errno 61|Errno 111/i.test(d)
      ) {
        mjpegStatusEl.textContent = "";
        mjpegStatusEl.appendChild(
          document.createTextNode(
            "Nothing is listening on port " +
              port +
              " right now (this page and scripts/run_backend only start the API on port " +
              getApiPort() +
              ", not edge). Start edge in a separate shell, or change the sidebar MJPEG port to match a running edge."
          )
        );
        mjpegStatusEl.appendChild(document.createElement("br"));
        mjpegStatusEl.appendChild(document.createTextNode("Example: " + example + "."));
        return;
      }
      mjpegStatusEl.textContent =
        "No response from edge on 127.0.0.1:" +
        port +
        ". " +
        example +
        ". " +
        d;
    } catch (_) {
      mjpegStatusEl.classList.add("mjpeg-bad");
      mjpegStatusEl.textContent =
        "Health check failed (is this page served from the local backend?).";
    }
  }

  function putProgress() {
    state.progress.mjpeg_port = getMjpegPort();
    persistProgressLocal();
    return fetch("/api/setup/progress", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.progress),
    });
  }

  function persistProgressLocal() {
    try {
      localStorage.setItem(PROGRESS_LSK, JSON.stringify(state.progress));
    } catch (_) {
      /* full storage / private mode */
    }
  }

  function loadProgressFromLocal() {
    try {
      const raw = localStorage.getItem(PROGRESS_LSK);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (_) {
      return null;
    }
  }

  /** Merge server progress with local backup so work is not lost if the user refreshed before a debounced server save. */
  function mergeServerAndLocalProgress(server) {
    const local = loadProgressFromLocal();
    if (!local || typeof local !== "object") return server;
    const out = { ...server, notes: { ...(server.notes || {}) } };
    const localNotes = local.notes && typeof local.notes === "object" ? local.notes : {};
    const noteIds = new Set([...Object.keys(out.notes), ...Object.keys(localNotes)]);
    for (const id of noteIds) {
      const a = (out.notes[id] || "").trim();
      const b = (localNotes[id] || "").trim();
      if (b.length > a.length) out.notes[id] = localNotes[id] ?? b;
    }
    out.checklist_done = { ...(server.checklist_done || {}) };
    for (const [id, row] of Object.entries(local.checklist_done || {})) {
      if (!Array.isArray(row)) continue;
      const srow = out.checklist_done[id] || [];
      const m = Math.max(srow.length, row.length);
      const merged = [];
      for (let i = 0; i < m; i++) {
        merged[i] = Boolean(srow[i] || row[i]);
      }
      out.checklist_done[id] = merged;
    }
    out.completed = { ...(server.completed || {}) };
    for (const [k, v] of Object.entries(local.completed || {})) {
      if (v) out.completed[k] = true;
    }
    return out;
  }

  function flushProgressKeepalive() {
    try {
      state.progress.mjpeg_port = getMjpegPort();
      persistProgressLocal();
      const body = JSON.stringify(state.progress);
      void fetch("/api/setup/progress", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body,
        keepalive: true,
      });
    } catch (_) {
      /* ignore */
    }
  }

  function saveProgress() {
    putProgress()
      .then((r) => {
        if (!r.ok) throw new Error(r.statusText);
        showToast("Progress saved");
      })
      .catch(() => showToast("Save failed — is the backend running?"));
  }

  function saveAndGoToNextStep() {
    const idx = state.steps.findIndex((s) => s.id === state.activeId);
    const next = idx >= 0 && idx < state.steps.length - 1 ? state.steps[idx + 1] : null;
    putProgress()
      .then((r) => {
        if (!r.ok) throw new Error(r.statusText);
        if (next) {
          state.activeId = next.id;
          state.progress.last_step_id = next.id;
        }
        showToast("Progress saved");
        renderNav();
        renderContent();
        const mainEl = $("#content");
        if (mainEl) mainEl.scrollTo(0, 0);
      })
      .catch(() => showToast("Save failed — is the backend running?"));
  }

  function scheduleSave() {
    persistProgressLocal();
    clearTimeout(state.saveTimer);
    state.saveTimer = setTimeout(saveProgress, 400);
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function escWithLineBreaks(s) {
    if (s == null) return "";
    return String(s)
      .split("\n")
      .map((line) => escapeHtml(line))
      .join("<br />");
  }

  /** Replaces {project_root} and wraps that path in <code> for readability. */
  function formatChecklistField(raw) {
    if (!raw) return "";
    const root = state.context.project_root || "";
    const ap = String(getApiPort());
    const mj = String(getMjpegPort());
    const withPort = String(raw).split("{api_port}").join(ap).split("{mjpeg_port}").join(mj);
    if (!withPort.includes("{project_root}")) return escWithLineBreaks(withPort);
    const segs = withPort.split("{project_root}");
    let out = "";
    segs.forEach((p, i) => {
      out += escWithLineBreaks(p);
      if (i < segs.length - 1) {
        out += `<code class="repo-path-inline">${escapeHtml(root)}</code>`;
      }
    });
    return out;
  }

  function applyTemplatePlaceholders(raw) {
    if (raw == null) return "";
    const root = state.context.project_root || "";
    return String(raw)
      .split("{api_port}").join(String(getApiPort()))
      .split("{mjpeg_port}").join(String(getMjpegPort()))
      .split("{project_root}").join(root);
  }

  /** Backtick text that is a label, expected output, or not worth pasting in a shell — no Copy button. */
  const NO_COPY_BACKTICKS = new Set([
    "OK",
    "H",
    "names:",
    "path:",
    "pockets",
    "cv2",
    "cd",
    "imports-ok",
    '{"ok":true}',
    /* File / label fragments, not shell (avoid Copy next to inline filenames) */
    "model.onnx",
    "start_calibration.sh",
    /* Shorthand in prose, not a runnable one-liner */
    "edge.main",
  ]);

  function shouldShowCopyForBacktick(s) {
    const t = (s || "").trim();
    if (!t) return false;
    if (NO_COPY_BACKTICKS.has(t)) return false;
    /* Notes / label lines (e.g. "0..4 ball..pockets"), not shell */
    if (/\d+\.\.\d+.*\.\./.test(t) && /ball|pocket/i.test(t)) return false;
    /* e.g. PHASE3_USB_INDEX, CUDA_VISIBLE_DEVICES — not a full shell command */
    if (/^[A-Z][A-Z0-9_]+$/.test(t)) return false;
    /* e.g. `--camera csi` (inline flags, not a runnable line) */
    if (t.startsWith("--") && !/\b(cd|source|bash|sh|python3?)\b/i.test(t) && !/&&|;\s*\S|^\s*ssh\s/.test(t)) {
      return false;
    }
    if (t.length < 2) return false;
    if (t.length === 2 && t !== "ls") return false;
    if (t.length === 3 && t !== "pwd" && t !== "ls" && t !== "set") return false;
    if (t.length < 4) {
      if (t === "ls" || t === "pwd" || t === "set") return true;
      return false;
    }
    if (/\s|&&|;\s*|\|/.test(t)) return true;
    if (/^(cd|test|ls|bash|curl|export|source|which|python|python3|\.venv|http)/i.test(t)) {
      return true;
    }
    if (t.length >= 8) return true;
    return false;
  }

  /**
   * Backticked segments: optional Copy (verify = real shell commands only). Record text never shows Copy.
   */
  function formatChecklistWithBackticks(raw, allowCommandCopy) {
    if (!raw) return "";
    if (!raw.includes("`")) {
      return formatChecklistField(raw);
    }
    const t = applyTemplatePlaceholders(raw);
    const parts = t.split(/`([^`]*)`/);
    let out = "";
    for (let j = 0; j < parts.length; j += 1) {
      if (j % 2 === 0) {
        out += escWithLineBreaks(parts[j]);
      } else {
        const seg = parts[j];
        out += `<code class="verify-inline-code">${escapeHtml(seg)}</code>`;
        if (
          allowCommandCopy &&
          shouldShowCopyForBacktick(seg)
        ) {
          out += ` <button type="button" class="btn btn-primary copy-inline-cmd" data-copy="${encodeURIComponent(
            seg
          )}" title="Copy command to paste in Terminal">Copy</button><br />`;
        } else {
          out += " ";
        }
      }
    }
    return out;
  }

  function getCurrentTextSize() {
    const a = document.documentElement.getAttribute("data-text-size");
    if (a === "small" || a === "medium" || a === "large") return a;
    try {
      const s = localStorage.getItem(TEXT_SIZE_KEY);
      if (s === "small" || s === "medium" || s === "large") return s;
    } catch (_) {
      /* ignore */
    }
    return "medium";
  }

  function docHref(relPath) {
    let u = "/api/setup/doc?path=" + encodeURIComponent(relPath);
    const size = getCurrentTextSize();
    u += "&textSize=" + encodeURIComponent(size);
    return u;
  }

  /** Use in innerHTML: raw `&` in href breaks Safari’s parser; must be &amp; in the attribute. */
  function docHrefForHtmlAttr(relPath) {
    return docHref(relPath).replace(/&/g, "&amp;");
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
      <p class="checklist-intro">Check a line only after you have done the <strong>How to verify</strong> steps. If <strong>What to record</strong> applies, add that in Notes (this step) or skip if nothing is worth saving.</p>
      ${checklist
        .map((entry, i) => {
          const item = typeof entry === "string" ? { item: entry, verify: "", record: "" } : entry;
          const checked = arr[i] ? " checked" : "";
          const id = `cl-${step.id}-${i}`;
          const rawV = item.verify || "";
          return `<div class="checklist-block">
            <div class="row-top">
              <input type="checkbox" data-ci="${i}" id="${id}"${checked}/>
              <div>
                <div class="item-text">${formatChecklistField(item.item || "")}</div>
                ${
                  rawV
                    ? `<p class="verify"><strong>How to verify:</strong> ${formatChecklistWithBackticks(
                        rawV,
                        true
                      )}</p>`
                    : ""
                }
                ${
                  Array.isArray(item.verify_actions) && item.verify_actions.length
                    ? `<div class="verify-actions" role="group" aria-label="Step actions">${item.verify_actions
                        .map((a) => {
                          if (!a || !a.href_template) return "";
                          const href = resolveLinkHref(a.href_template);
                          return `<button type="button" class="btn btn-primary verify-action-btn" data-open-href="${escapeHtml(
                            href
                          )}">${escapeHtml(a.label || "Open")}</button>`;
                        })
                        .filter(Boolean)
                        .join("")}</div>`
                    : ""
                }
                ${
                  item.record
                    ? `<p class="record"><strong>What to record:</strong> ${formatChecklistWithBackticks(
                        item.record,
                        false
                      )}</p>`
                    : ""
                }
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
          `<a class="doc-line-link" href="${docHrefForHtmlAttr(d.path)}" target="_blank" rel="noopener"><span class="doc-line-label">${escapeHtml(d.label)}</span> <span class="muted-path">(${escapeHtml(d.path)})</span></a>`
      )
      .join("")}</div></section>`;
  }

  function renderHintsSection(step) {
    const hints = step.hints || [];
    if (!hints.length) return "";
    return `<section class="setup-hints"><h3>Tips</h3><ul class="hints">${hints
      .map((h) => {
        if (h.includes("`")) {
          return `<li class="hint-line">${formatChecklistWithBackticks(h, true)}</li>`;
        }
        return `<li class="hint-line">${escWithLineBreaks(h)}</li>`;
      })
      .join("")}</ul></section>`;
  }

  function renderLinks(step) {
    const links = step.links || [];
    if (!links.length) return "";
    return `<section><h3>Quick links</h3><div class="quick-links">${links
      .map((L) => {
        if (L.href) {
          return `<div class="ql"><a href="${escapeHtml(L.href)}" target="_blank" rel="noopener">${escapeHtml(L.label)}</a>${L.note ? `<p class="ql-note">${escapeHtml(L.note)}</p>` : ""}</div>`;
        }
        if (L.href_template) {
          const href = resolveLinkHref(L.href_template);
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

    const isLastStep =
      state.steps.length > 0 && state.activeId === state.steps[state.steps.length - 1].id;
    const saveButtonLabel = isLastStep ? "Save" : "Save and go to next step";

    const checklist = step.checklist || [];
    const noteVal = state.progress.notes[step.id] || "";
    const sig = stepSignal(step);

    content.innerHTML = `
      <h2>${signalHtml(sig)} ${escapeHtml(step.title)}</h2>
      <p class="summary">${escapeHtml(step.summary || "")}</p>
      ${renderChecklist(step)}
      ${renderLinks(step)}
      ${renderDocs(step)}
      ${renderHintsSection(step)}
      <section class="notes"><h3>Notes (this step)</h3>
        <p class="terminal-hint">Use this field for command output, versions, ports, or reminders. Saved with the rest of your progress.</p>
        <textarea id="step-note" placeholder="Paste output, dates, non-secret reminders…">${escapeHtml(noteVal)}</textarea>
      </section>
      <div class="step-actions">
        <label class="mark-done"><input type="checkbox" id="step-done" ${
          state.progress.completed[step.id] ? "checked" : ""
        }/> Mark entire step complete</label>
        <button type="button" class="btn btn-primary" id="btn-save">${escapeHtml(saveButtonLabel)}</button>
      </div>
    `;

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
        persistProgressLocal();
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

    $("#btn-save")?.addEventListener("click", saveAndGoToNextStep);

    content.querySelectorAll(".copy-inline-cmd").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const enc = btn.getAttribute("data-copy");
        if (!enc) return;
        let text = enc;
        try {
          text = decodeURIComponent(enc);
        } catch (_) {
          /* use raw */
        }
        if (text.length === 0) return;
        copyText(text);
      });
    });

    content.querySelectorAll("button.verify-action-btn[data-open-href]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const u = btn.getAttribute("data-open-href");
        if (u) window.open(u, "_blank", "noopener");
      });
    });
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
      const serverProgress = await progRes.json();
      const merged = mergeServerAndLocalProgress(serverProgress);
      const needServerSync = JSON.stringify(merged) !== JSON.stringify(serverProgress);
      state.progress = merged;
      persistProgressLocal();
      if (needServerSync) {
        void putProgress().catch(() => {});
      }
      if (typeof state.progress.mjpeg_port !== "number" || state.progress.mjpeg_port < 1) {
        state.progress.mjpeg_port = 8001;
      }
      if (state.progress.mjpeg_port < 8001 || state.progress.mjpeg_port > 8005) {
        state.progress.mjpeg_port = 8001;
      }
      if (mjpegInput) mjpegInput.value = String(state.progress.mjpeg_port);

      prEl.textContent = state.context.project_root || "(unknown)";

      const apiHint = $("#api-hint");
      if (apiHint) {
        apiHint.textContent =
          "This guide: http://127.0.0.1:" +
          getApiPort() +
          "/setup (BACKEND_PORT default 8000; MJPEG 8001–8005, see docs/PORTS.md).";
      }

      state.activeId =
        state.progress.last_step_id && state.steps.some((s) => s.id === state.progress.last_step_id)
          ? state.progress.last_step_id
          : state.steps[0]?.id || null;

      mjpegInput?.addEventListener("change", () => {
        state.progress.mjpeg_port = getMjpegPort();
        scheduleSave();
        renderContent();
        void refreshMjpegEdgeHealth();
      });

      if (edgeHealthTimer) {
        clearInterval(edgeHealthTimer);
        edgeHealthTimer = null;
      }
      void refreshMjpegEdgeHealth();
      edgeHealthTimer = setInterval(() => {
        void refreshMjpegEdgeHealth();
      }, 10000);

      renderNav();
      renderContent();
    } catch (e) {
      content.innerHTML =
        "<p>Could not load setup data. Start the backend: <code>./scripts/run_backend.sh</code> or <code>uvicorn backend.app:app --host 127.0.0.1 --port 8000</code></p>";
    }
  }

  initTextSizeControls();
  initSidebarResize();
  init();
  window.addEventListener("pagehide", flushProgressKeepalive);
  window.addEventListener("beforeunload", flushProgressKeepalive);
})();
