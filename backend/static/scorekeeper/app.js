(function () {
  const connEl = document.getElementById("sk-conn");
  const elTeams = document.getElementById("sk-teams");
  const elPlayers = document.getElementById("sk-players");
  const elTurn = document.getElementById("sk-turn");
  const elClock = document.getElementById("sk-clock");
  const elRecent = document.getElementById("sk-recent");

  function setConn(text, kind) {
    if (!connEl) return;
    connEl.textContent = text;
    connEl.className = "sk-conn" + (kind ? " sk-conn--" + kind : "");
  }

  function fmt(x) {
    if (x === null || x === undefined) return "—";
    if (typeof x === "object") return JSON.stringify(x);
    return String(x);
  }

  function render(s) {
    if (!s || typeof s !== "object") s = {};
    if (elTeams) {
      const teams = s.teams;
      elTeams.innerHTML = "";
      if (Array.isArray(teams) && teams.length) {
        teams.forEach((t, i) => {
          const d = document.createElement("div");
          d.className = "sk-team";
          d.innerHTML =
            "<span>" + escapeHtml(String(t && (t.name || t.id || "Team " + (i + 1)))) + "</span>" +
            "<span>" + escapeHtml(String(t && (t.score != null ? t.score : t.points != null ? t.points : "—"))) + "</span>";
          elTeams.appendChild(d);
        });
      } else {
        elTeams.innerHTML = '<p class="sk-na">No team rows yet (waiting for /state or events).</p>';
      }
    }
    if (elPlayers) {
      const pl = s.players;
      elPlayers.innerHTML = "";
      if (Array.isArray(pl) && pl.length) {
        pl.forEach((p, i) => {
          const d = document.createElement("div");
          d.className = "sk-prow";
          const name = p && (p.name || p.display_name || p.profile_id) ? p.name || p.display_name || p.profile_id : "Player " + (i + 1);
          const score = p && (p.score != null || p.team_score != null) ? p.score != null ? p.score : p.team_score : "—";
          d.innerHTML = "<span>" + escapeHtml(String(name)) + "</span><span>" + escapeHtml(String(score)) + "</span>";
          elPlayers.appendChild(d);
        });
      } else {
        elPlayers.innerHTML = '<p class="sk-na">No player rows (edge may not be publishing snapshots).</p>';
      }
    }
    if (elTurn) {
      const cur = s.current_player_idx;
      const ti = s.current_team_idx;
      const inn = s.inning;
      const shotN = s.shot_count;
      const gameType = s.game_type;
      const over = s.game_over_reason;
      const win = s.winner_team;
      const bih = s.ball_in_hand_for_team;
      const inShot = s.in_shot;
      const rows = [
        ["Game type", fmt(gameType)],
        ["Inning", fmt(inn)],
        ["Current player idx", fmt(cur)],
        ["Current team idx", fmt(ti)],
        ["Shots (counter)", fmt(shotN)],
        ["In shot", fmt(inShot)],
        ["Ball in hand (team)", fmt(bih)],
        ["Winner (team idx)", win != null ? fmt(win) : "—"],
        ["Game over", over != null ? fmt(over) : "—"],
      ];
      elTurn.innerHTML = rows
        .map(
          ([a, b]) => "<div><dt>" + escapeHtml(a) + "</dt><dd>" + escapeHtml(b) + "</dd></div>"
        )
        .join("");
    }
    if (elClock) {
      const tss = s.seconds_since_previous_shot_over;
      const lastShotOver = s.last_player_shot_over_ts;
      const le = s.latest_event;
      const evLabel =
        le && typeof le === "object" && le.type
          ? String(le.type)
          : le
            ? fmt(le)
            : "—";
      const rows2 = [
        ["Seconds since last shot over", tss == null || tss === undefined ? "—" : String(Number(tss).toFixed(2))],
        ["Last player shot over ts", lastShotOver == null ? "—" : fmt(lastShotOver)],
        ["Latest event", evLabel],
      ];
      elClock.innerHTML = rows2
        .map(
          ([a, b]) => "<div><dt>" + escapeHtml(a) + "</dt><dd>" + escapeHtml(b) + "</dd></div>"
        )
        .join("");
    }
    if (elRecent) {
      const ev = s.latest_event;
      const pck = s.recent_ball_pockets;
      const col = s.recent_collisions;
      const rai = s.recent_rail_hits;
      const items = [];
      if (ev && (ev.type || (typeof ev === "string" && ev)))
        items.push("Event: " + (typeof ev === "object" && ev.type ? ev.type : JSON.stringify(ev)));
      if (Array.isArray(pck) && pck.length) items.push("Pockets: " + pck.length + " in buffer");
      if (Array.isArray(col) && col.length) items.push("Collisions: " + col.length);
      if (Array.isArray(rai) && rai.length) items.push("Rail hits: " + rai.length);
      elRecent.innerHTML = items.length
        ? items.map((t) => "<li>" + escapeHtml(t) + "</li>").join("")
        : '<li class="sk-na">No recent line items yet.</li>';
    }
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  async function poll() {
    try {
      const r = await fetch("/live/state", { cache: "no-store" });
      if (!r.ok) {
        setConn("HTTP " + r.status, "bad");
        return;
      }
      const j = await r.json();
      render(j);
    } catch (_) {
      setConn("unreachable", "bad");
    }
  }

  function connectWs() {
    const p = location.protocol === "https:" ? "wss" : "ws";
    const u = p + "://" + location.host + "/ws";
    let ws;
    try {
      ws = new WebSocket(u);
    } catch (e) {
      setConn("no websocket", "bad");
      return;
    }
    ws.onopen = function () {
      setConn("live (WS) + poll", "ok");
    };
    ws.onmessage = function (e) {
      try {
        const m = JSON.parse(e.data);
        if (m && m.type === "live_state" && m.data) {
          render(m.data);
        }
        if (m && m.type === "event" && m.data) {
          void poll();
        }
      } catch (_) {
        /* ignore */
      }
    };
    ws.onclose = function () {
      setConn("reconnecting…", "dim");
      setTimeout(connectWs, 2000);
    };
    ws.onerror = function () {
      setConn("WS error (polling)", "dim");
    };
  }

  setConn("HTTP poll + WS", "dim");
  void poll();
  setInterval(poll, 1500);
  connectWs();
})();
