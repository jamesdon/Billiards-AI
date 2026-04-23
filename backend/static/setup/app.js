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
    liveProfilesStatusTimer: null,
  };

  const $ = (sel) => document.querySelector(sel);
  const nav = $("#nav-steps");
  const content = $("#content");
  const toast = $("#status-toast");
  const prEl = $("#project-root");
  const mjpegInput = $("#mjpeg-port");
  const apiHealthLamp = $("#api-health-lamp");
  const apiPortShown = $("#api-port-shown");
  const edgePortLamp = $("#edge-port-lamp");
  const streamLamp = $("#stream-lamp");
  const edgePortLine = $("#edge-port-line");
  const mjpegHealthBlock = $("#mjpeg-health-block");
  const streamHrefEl = $("#stream-href");
  const tabSetup = $("#tab-setup");
  const tabSk = $("#tab-sk");
  const skEmbed = $("#sk-embed");
  const skIframe = $("#sk-iframe");
  const skQrBlock = $("#sk-qr-block");
  const skQrCanvas = $("#sk-qr-canvas");
  const skQrUrl = $("#sk-qr-url");
  let healthPollTimer = null;
  let skIframeSrcSet = false;

  const TEXT_SIZE_KEY = "billiards-setup-text-size";
  const UI_MODE_KEY = "billiards-setup-ui-mode";
  const PROGRESS_LSK = "billiards-setup-progress-v1";
  const SIDEBAR_W_LSK = "billiards-setup-sidebar-width-px";
  const DEFAULT_SIDEBAR_PX = 300;
  const MAIN_MIN_PX = 280;
  /** Must match inline <head> script in index.html (root px drives all rem). */
  const TEXT_ROOT_PX = { small: "16px", medium: "22px", large: "28px" };

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
    const skI = document.getElementById("sk-iframe");
    if (skI && skI.contentWindow) {
      try {
        skI.contentWindow.postMessage(
          { type: "billiards-text-size", size },
          window.location.origin
        );
      } catch (_) {
        /* ignore */
      }
    }
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

  function getInitialUiMode() {
    try {
      const v = localStorage.getItem(UI_MODE_KEY);
      if (v === "setup" || v === "scorekeeper") return v;
    } catch (_) {
      /* ignore */
    }
    return "setup";
  }

  function scorekeeperFrameSrc() {
    return new URL("/scorekeeper", window.location.origin).href;
  }

  function applySkQr(url) {
    if (!skQrUrl || !skQrCanvas || !url) return;
    skQrUrl.textContent = url;
    if (typeof window.QRCode !== "function") return;
    skQrCanvas.innerHTML = "";
    const QC = window.QRCode;
    const level = QC && QC.CorrectLevel ? QC.CorrectLevel.H : undefined;
    try {
      if (level !== undefined) {
        new QC(skQrCanvas, {
          text: url,
          width: 160,
          height: 160,
          colorDark: "#1a1d24",
          colorLight: "#e8eaed",
          correctLevel: level,
        });
      } else {
        new QC(skQrCanvas, {
          text: url,
          width: 160,
          height: 160,
          colorDark: "#1a1d24",
          colorLight: "#e8eaed",
        });
      }
    } catch (_) {
      /* ignore */
    }
  }

  function syncSkQrBlockVisibility() {
    if (!skQrBlock) return;
    const mode = document.body.getAttribute("data-ui-mode") || "setup";
    const url = state.context && state.context.scorekeeper_url;
    const hasUrl = typeof url === "string" && url.length > 0;
    if (mode === "scorekeeper" && hasUrl) {
      skQrBlock.removeAttribute("hidden");
    } else {
      skQrBlock.setAttribute("hidden", "");
    }
  }

  function updateScorekeeperFromContext() {
    const url = state.context && state.context.scorekeeper_url;
    if (typeof url !== "string" || !url) return;
    applySkQr(url);
    syncSkQrBlockVisibility();
  }

  function applyUiMode(mode) {
    if (mode !== "setup" && mode !== "scorekeeper") mode = "setup";
    document.body.setAttribute("data-ui-mode", mode);
    try {
      localStorage.setItem(UI_MODE_KEY, mode);
    } catch (_) {
      /* ignore */
    }

    if (tabSetup) {
      tabSetup.setAttribute("aria-selected", mode === "setup" ? "true" : "false");
      tabSetup.classList.toggle("sidebar-tab--active", mode === "setup");
    }
    if (tabSk) {
      tabSk.setAttribute("aria-selected", mode === "scorekeeper" ? "true" : "false");
      tabSk.classList.toggle("sidebar-tab--active", mode === "scorekeeper");
    }

    document.title = mode === "scorekeeper" ? "Billiards-AI — Score Keeper" : "Billiards-AI";

    if (mode === "scorekeeper" && skIframe && !skIframeSrcSet) {
      skIframe.src = scorekeeperFrameSrc();
      skIframeSrcSet = true;
    }
    syncSkQrBlockVisibility();
  }

  function initUiMode() {
    applyUiMode(getInitialUiMode());
    tabSetup?.addEventListener("click", () => applyUiMode("setup"));
    tabSk?.addEventListener("click", () => applyUiMode("scorekeeper"));
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

  function setLamp(el, s, ariaLabel) {
    if (!el) return;
    el.classList.remove("health-lamp--ok", "health-lamp--bad", "health-lamp--unknown");
    if (s === "ok") el.classList.add("health-lamp--ok");
    else if (s === "bad") el.classList.add("health-lamp--bad");
    else el.classList.add("health-lamp--unknown");
    if (ariaLabel) el.setAttribute("aria-label", ariaLabel);
  }

  function updateStreamLineHtml(port) {
    const u = "http://127.0.0.1:" + port + "/mjpeg";
    const a = streamHrefEl || document.getElementById("stream-href");
    if (a) {
      a.href = u;
      a.textContent = u;
    }
  }

  async function refreshApiHealth() {
    if (!apiHealthLamp) return;
    setLamp(apiHealthLamp, "unknown", "API health checking");
    if (apiPortShown) apiPortShown.textContent = String(getApiPort());
    try {
      const r = await fetch("/health", { cache: "no-store" });
      if (!r.ok) {
        setLamp(apiHealthLamp, "bad", "API /health not OK (HTTP " + r.status + ")");
        return;
      }
      const j = await r.json();
      if (j && j.ok === true) {
        setLamp(apiHealthLamp, "ok", "API is up (GET /health returned ok)");
        return;
      }
      setLamp(apiHealthLamp, "bad", "API /health body unexpected");
    } catch (_) {
      setLamp(apiHealthLamp, "bad", "API unreachable (is the backend running on this origin?)");
    }
  }

  async function refreshEdgeAndStreamHealth() {
    if (!edgePortLamp || !streamLamp || !edgePortLine) return;
    const port = getMjpegPort();
    mjpegHealthBlock && mjpegHealthBlock.classList.remove("mjpeg-ok", "mjpeg-bad");
    setLamp(edgePortLamp, "unknown", "Edge health checking");
    setLamp(streamLamp, "unknown", "Stream unknown");
    edgePortLine.textContent = "Port " + port + ": checking…";
    updateStreamLineHtml(port);

    try {
      const r = await fetch(
        "/api/setup/edge-health?port=" + encodeURIComponent(String(port))
      );
      if (!r.ok) {
        setLamp(edgePortLamp, "bad", "Edge check failed (HTTP " + r.status + ")");
        setLamp(streamLamp, "bad", "No MJPEG (edge check failed)");
        mjpegHealthBlock && mjpegHealthBlock.classList.add("mjpeg-bad");
        edgePortLine.textContent = "No edge (could not run server check, HTTP " + r.status + ").";
        return;
      }
      const j = await r.json();
      if (j.ok) {
        setLamp(edgePortLamp, "ok", "Edge is up on port " + port);
        setLamp(streamLamp, "ok", "MJPEG stream available at this port");
        mjpegHealthBlock && mjpegHealthBlock.classList.add("mjpeg-ok");
        edgePortLine.textContent = "Port " + port + ": edge is up.";
        return;
      }
      const d = (j.detail && String(j.detail)) || "no response";
      setLamp(edgePortLamp, "bad", "No edge on port " + port);
      setLamp(streamLamp, "bad", "No MJPEG (edge not listening)");
      mjpegHealthBlock && mjpegHealthBlock.classList.add("mjpeg-bad");
      edgePortLine.textContent = "No edge on port " + port + " (" + d + ").";
    } catch (_) {
      setLamp(edgePortLamp, "bad", "Edge check failed (backend cannot probe localhost — open from same machine?)");
      setLamp(streamLamp, "bad", "Stream unavailable");
      mjpegHealthBlock && mjpegHealthBlock.classList.add("mjpeg-bad");
      edgePortLine.textContent =
        "No edge on port " + port + " (health check failed: is the API running locally?).";
    }
  }

  async function refreshAllHealth() {
    await refreshApiHealth();
    await refreshEdgeAndStreamHealth();
  }

  function startHealthPollers() {
    if (healthPollTimer) {
      clearInterval(healthPollTimer);
      healthPollTimer = null;
    }
    void refreshAllHealth();
    healthPollTimer = setInterval(() => {
      void refreshAllHealth();
    }, 10000);
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

  function scrollSetupContentToTop() {
    if (content) content.scrollTo(0, 0);
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
        scrollSetupContentToTop();
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

  /** Private-use sentinels so {project_root} can be template-expanded after Markdown-ish parsing. */
  const _REPO_START = "\uE000";
  const _REPO_END = "\uE001";
  const REPO_PLACEHOLDER = _REPO_START + "BILLIARDS_PROJECT_ROOT" + _REPO_END;

  /** Expand API/MJPEG ports and mark project root (rendered as <code> later). */
  function applyTemplateForRich(raw) {
    if (raw == null) return "";
    return String(raw)
      .split("{api_port}")
      .join(String(getApiPort()))
      .split("{mjpeg_port}")
      .join(String(getMjpegPort()))
      .split("{project_root}")
      .join(REPO_PLACEHOLDER);
  }

  function applyBoldToLine(line) {
    const segs = String(line).split("**");
    if (segs.length === 1) return escapeHtml(line);
    let out = "";
    for (let k = 0; k < segs.length; k += 1) {
      if (k % 2 === 0) out += escapeHtml(segs[k]);
      else out += "<strong>" + escapeHtml(segs[k]) + "</strong>";
    }
    return out;
  }

  function applyBoldToSegment(s) {
    if (!s) return "";
    return s.split("\n").map(applyBoldToLine).join("<br />");
  }

  /** Single backticks = inline only (no Copy). */
  function renderProsePart(t) {
    const parts = String(t).split(/`([^`]*)`/);
    let h = "";
    for (let j = 0; j < parts.length; j += 1) {
      if (j % 2 === 0) h += applyBoldToSegment(parts[j]);
      else h += '<code class="setup-inline-code">' + escapeHtml(parts[j]) + "</code>";
    }
    return h;
  }

  function renderProseWithRepo(t) {
    if (!t) return "";
    if (t.indexOf(REPO_PLACEHOLDER) === -1) return renderProsePart(t);
    const root = state.context.project_root || "";
    return t.split(REPO_PLACEHOLDER)
      .map((seg, si) => {
        if (si % 2 === 0) return renderProsePart(seg);
        return `<code class="repo-path-inline">${escapeHtml(root)}</code>`;
      })
      .join("");
  }

  function extractFenceInner(inner) {
    let t = inner;
    if (t.startsWith("\r\n")) t = t.slice(2);
    else if (t.startsWith("\n")) t = t.slice(1);
    const nl = t.indexOf("\n");
    if (nl === -1) {
      if (/^[a-zA-Z][\w-]*$/.test(t)) return "";
      return t;
    }
    const first = t.slice(0, nl);
    if (/^[a-zA-Z][\w-]*$/.test(first)) return t.slice(nl + 1);
    return t;
  }

  function splitByFences(s) {
    const out = [];
    let i = 0;
    while (i < s.length) {
      if (s.startsWith("```", i)) {
        const afterTicks = i + 3;
        const closeIdx = s.indexOf("```", afterTicks);
        if (closeIdx === -1) {
          out.push({ type: "text", content: s.slice(i) });
          break;
        }
        const rawInner = s.slice(afterTicks, closeIdx);
        const code = extractFenceInner(rawInner);
        out.push({ type: "code", content: code });
        i = closeIdx + 3;
        if (s[i] === "\r" && s[i + 1] === "\n") i += 2;
        else if (s[i] === "\n" || s[i] === "\r") i += 1;
        continue;
      }
      const next = s.indexOf("```", i);
      if (next === -1) {
        out.push({ type: "text", content: s.slice(i) });
        break;
      }
      if (next > i) out.push({ type: "text", content: s.slice(i, next) });
      i = next;
    }
    if (out.length === 0) out.push({ type: "text", content: s });
    return out;
  }

  /**
   * Fenced ``` blocks = real commands (How to verify: optional Copy). Single backticks = inline (no Copy).
   * `**bold**` is supported in prose. Use triple backticks in setup_guide for paste-ready shell, not ad-hoc
   * backtick+Copy heuristics.
   */
  function formatSetupPageRichText(tIn, options) {
    const allowFenceCopy = options && options.allowFenceCopy;
    if (tIn == null || tIn === "") return "";
    const t = String(tIn);
    const segs = splitByFences(t);
    const parts = segs
      .map((seg) => {
        if (seg.type === "text") {
          return renderProseWithRepo(seg.content);
        }
        const root = state.context.project_root || "";
        let code = String(seg.content).replace(/\r\n/g, "\n").replace(/\n+$/, "");
        if (code.indexOf(REPO_PLACEHOLDER) !== -1) {
          code = code.split(REPO_PLACEHOLDER).join(root);
        }
        const enc = encodeURIComponent(code);
        const pre =
          '<div class="setup-fence-wrap"><pre class="setup-fence"><code>' +
          escapeHtml(code) +
          "</code></pre>";
        const btn = allowFenceCopy
          ? `<button type="button" class="btn btn-primary copy-inline-cmd" data-copy="${enc}" title="Copy to paste in Terminal">Copy</button>`
          : "";
        return pre + btn + "</div>";
      })
      .join("");
    return parts;
  }

  function formatChecklistField(raw) {
    if (!raw) return "";
    return formatSetupPageRichText(applyTemplateForRich(raw), { allowFenceCopy: false });
  }

  function formatChecklistWithBackticks(raw, allowCommandCopy) {
    if (!raw) return "";
    return formatSetupPageRichText(applyTemplateForRich(raw), { allowFenceCopy: !!allowCommandCopy });
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

  function   copyText(text) {
    navigator.clipboard.writeText(text).then(
      () => showToast("Copied — paste in Terminal"),
      () => showToast("Copy failed")
    );
  }

  /**
   * Checklist line booleans for this step, length = current checklist def (ignore stale extra entries).
   */
  function getChecklistDoneSnapshot(step) {
    const n = (step.checklist || []).length;
    const raw = state.progress.checklist_done[step.id];
    const arr = [];
    for (let k = 0; k < n; k += 1) {
      arr[k] = Array.isArray(raw) && k < raw.length ? !!raw[k] : false;
    }
    return arr;
  }

  /** @returns {'red'|'yellow'|'green'} */
  function stepSignal(step) {
    const id = step.id;
    const n = (step.checklist || []).length;
    const done = getChecklistDoneSnapshot(step);
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
        scrollSetupContentToTop();
      });
      li.appendChild(btn);
      nav.appendChild(li);
    });
  }

  /** Real-time `identities.json` / GET /profiles counts (edge vision step: detection + profiles). */
  function renderLiveProfilesPanel(step) {
    if (step.id !== "phase3") return "";
    return `<section class="setup-live-profiles" aria-live="polite" aria-atomic="true">
      <h3>Live profile status (same file as GET /profiles)</h3>
      <p class="setup-live-profiles-line" id="live-profiles-status">Loading…</p>
      <p class="terminal-hint">Polls the API every 4s. The path is always the repository’s <code>identities.json</code> (same file as <code>GET /profiles</code>). <strong>Green</strong> when at least one player or stick row exists—complete that before checking off naming.</p>
    </section>`;
  }

  function clearLiveProfilesStatusTimer() {
    if (state.liveProfilesStatusTimer) {
      clearInterval(state.liveProfilesStatusTimer);
      state.liveProfilesStatusTimer = null;
    }
  }

  function refreshLiveProfilesStatus() {
    const el = content && content.querySelector("#live-profiles-status");
    if (!el) return;
    fetch("/api/setup/profiles-status", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then((j) => {
        const p = j.player_count | 0;
        const s = j.stick_count | 0;
        const res = (j.identities_path_resolved || j.identities_path || "").toString();
        const ok = p + s > 0;
        el.className = "setup-live-profiles-line" + (ok ? " setup-live-ok" : " setup-live-warn");
        el.textContent = res + " — " + p + " player(s), " + s + " stick(s). " + (ok
          ? "OK: at least one profile row (ready for naming)."
          : "Still empty — keep people/cue in frame, or use Bootstrap (checklist) if you need a row without the camera.");
      })
      .catch(() => {
        el.className = "setup-live-profiles-line setup-live-err";
        el.textContent = "Could not load /api/setup/profiles-status. Is the backend running?";
      });
  }

  function mountLiveProfilesIfNeeded(step) {
    clearLiveProfilesStatusTimer();
    if (step.id !== "phase3") return;
    refreshLiveProfilesStatus();
    state.liveProfilesStatusTimer = setInterval(refreshLiveProfilesStatus, 4000);
  }

  function renderChecklist(step) {
    const checklist = step.checklist || [];
    if (!checklist.length) return "";

    const raw = state.progress.checklist_done[step.id];
    if (Array.isArray(raw) && raw.length > checklist.length) {
      state.progress.checklist_done[step.id] = getChecklistDoneSnapshot(step);
      scheduleSave();
    }
    const arr = getChecklistDoneSnapshot(step);

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
              <input type="checkbox" class="checklist-line-cb" data-step-id="${escapeHtml(
                step.id
              )}" data-ci="${i}" id="${id}"${checked}/>
              <div>
                <div class="item-text">${formatChecklistField(item.item || "")}</div>
                ${
                  rawV
                    ? `<div class="verify"><strong>How to verify:</strong> ${formatChecklistWithBackticks(
                        rawV,
                        true
                      )}</div>`
                    : ""
                }
                ${
                  Array.isArray(item.verify_actions) && item.verify_actions.length
                    ? `<div class="verify-actions" role="group" aria-label="Step actions">${item.verify_actions
                        .map((a) => {
                          if (!a) return "";
                          if (a.action === "bootstrap_minimal_profiles") {
                            return `<button type="button" class="btn btn-primary verify-action-btn" data-bootstrap-profiles="1">${escapeHtml(
                              a.label || "Bootstrap"
                            )}</button>`;
                          }
                          if (!a.href_template) return "";
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
                    ? `<div class="record"><strong>What to record:</strong> ${formatChecklistWithBackticks(
                        item.record,
                        false
                      )}</div>`
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
      .map((h) => `<li class="hint-line">${formatChecklistWithBackticks(h, false)}</li>`)
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

    const summaryHtml = formatSetupPageRichText(applyTemplateForRich(step.summary || ""), {
      allowFenceCopy: false,
    });
    content.innerHTML = `
      <h2>${signalHtml(sig)} ${escapeHtml(step.title)}</h2>
      <div class="summary">${summaryHtml}</div>
      ${renderLiveProfilesPanel(step)}
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

    content.querySelectorAll(".verify-action-btn[data-bootstrap-profiles]").forEach((btn) => {
      btn.addEventListener("click", () => {
        fetch("/api/setup/bootstrap-minimal-profiles", { method: "POST" })
          .then((r) => r.json().then((j) => ({ ok: r.ok, j })))
          .then(({ ok, j }) => {
            if (ok && j.ok) {
              showToast(j.message || "Bootstrap OK");
              refreshLiveProfilesStatus();
            } else
              showToast(
                (j && (j.detail || j.message)) || (ok ? "Bootstrap skipped" : "Request failed")
              );
          })
          .catch(() => showToast("Bootstrap request failed"));
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

    mountLiveProfilesIfNeeded(step);
  }

  async function init() {
    try {
      const [ctxRes, stepsRes, progRes] = await Promise.all([
        fetch("/api/setup/context"),
        fetch("/api/setup/steps"),
        fetch("/api/setup/progress"),
      ]);
      state.context = await ctxRes.json();
      updateScorekeeperFromContext();
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

      state.activeId =
        state.progress.last_step_id && state.steps.some((s) => s.id === state.progress.last_step_id)
          ? state.progress.last_step_id
          : state.steps[0]?.id || null;

      mjpegInput?.addEventListener("change", () => {
        state.progress.mjpeg_port = getMjpegPort();
        scheduleSave();
        void refreshEdgeAndStreamHealth();
        renderContent();
      });

      renderNav();
      renderContent();
      startHealthPollers();
    } catch (e) {
      content.innerHTML =
        "<p>Could not load setup data. Start the backend: <code>./scripts/run_backend.sh</code> or <code>uvicorn backend.app:app --host 127.0.0.1 --port 8000</code></p>";
    }
  }

  function onChecklistLineChange(e) {
    const t = e.target;
    if (!t || t.getAttribute("type") !== "checkbox" || !t.classList.contains("checklist-line-cb")) {
      return;
    }
    const sid = t.getAttribute("data-step-id");
    if (!sid) return;
    const st = state.steps.find((s) => s.id === sid);
    if (!st) return;
    const ch = st.checklist || [];
    const n = ch.length;
    if (n === 0) return;
    const i = parseInt(t.getAttribute("data-ci") || "0", 10);
    if (i < 0 || i >= n) return;
    const next = getChecklistDoneSnapshot(st);
    next[i] = t.checked;
    state.progress.checklist_done[sid] = next;
    scheduleSave();
    renderNav();
    if (state.activeId === sid) {
      const h2 = content.querySelector("h2");
      if (h2) h2.innerHTML = `${signalHtml(stepSignal(st))} ${escapeHtml(st.title)}`;
    }
  }

  content.addEventListener("change", onChecklistLineChange);

  initTextSizeControls();
  initSidebarResize();
  initUiMode();
  init();
  window.addEventListener("pagehide", flushProgressKeepalive);
  window.addEventListener("beforeunload", flushProgressKeepalive);
})();
