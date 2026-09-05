// Orchestra: sub-agent channels — "conductor mode".
//
// When Dornick splits a job, sub-agents are born (the task tool). Their tool
// calls do not mix into the main conversation; this deck shows every channel
// as a live card: its title, model, the tool it is running right now, how
// many tools it has called, and its state (running · done · failed).
// Background helpers get a badge; finished channels are not deleted right
// away — the last five stay, and clicking a card opens the result summary.
//
// The source is live SSE events: child_start / child_tool / child_end. NOT a
// memory — momentary coordination. It opens on its own while running, and can
// be pinned. On page load it is seeded with the real channel list from
// /api/state (seed): no ghost "running" card is left over, and helpers left
// unfinished by the previous session show as a faded "yarım kaldı" row.

Lang.add({
  "Şu an alt ajan yok. Dornick bir işi böldüğünde kanallar burada belirir.":
    "No helpers right now. Channels appear here when Dornick splits a job.",
  "Şef bekliyor · ": "Conductor waiting · ",
  " kanal çalışıyor": " channel(s) running",
  "Şef sürüyor · tüm kanallar bitti": "Conductor going · all channels done",
  "Şef hazır": "Conductor ready",
  "Eşzamanlı yardımcı sınırı: ": "Concurrent helper limit: ",
  " · ayarlardan değişir": " · set in settings",
  "Düşünüyor…": "Thinking…",
  "Hata verdi": "Failed",
  "Bitti": "Done",
  "Yarım kaldı": "Left unfinished",
  "Yarım kalan yardımcı var — istersen sürdürülebilir":
    "Some helpers were left unfinished — they can be resumed",
  " araç": " tools",
  "arka plan": "background",
  "(özet yok)": "(no summary)",
  "Raporu aç": "Open report",
  "Model bekleniyor": "Waiting for model",
  "Model yanıt vermedi": "Model did not respond",
  "Devam et": "Continue",
  "İptal et": "Cancel",
  "İptal ediliyor…": "Cancelling…",
  "Sürdürülüyor…": "Resuming…",
});

const Orchestra = (() => {
  const deck = document.getElementById("orch-deck");
  const body = document.getElementById("orch-body");
  const status = document.getElementById("orch-status");
  const foot = document.getElementById("orch-foot");

  // id → channel state (without an id the title is the key — compatible
  // with older events).
  const channels = new Map();
  let pinned = false;      // user opened it by hand: keep open after the run
  let fadeTimer = null;

  // At most this many finished channels are kept; the oldest is dropped.
  const KEEP_DONE = 5;
  // The last N tool rows on a running channel (short act list).
  const KEEP_ACTS = 8;

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  const keyOf = (ev) => ev.id || ev.title;

  // --- events (called by app.js from the SSE stream) -------------------

  function start(ev) {
    channels.set(keyOf(ev), {
      title: ev.title, model: ev.model || "", id: ev.id || "",
      bg: !!ev.bg, tool: "", hedef: "", tools: 0, state: "run",
      ozet: "", open: false, acts: [],
    });
    prune();
    open();
    render();
  }

  function tool(ev) {
    // Tool events arrive with the title (they carry no channel id); they
    // are written onto the running channel with the same title.
    const ch = [...channels.values()].find(c => c.title === ev.title && c.state === "run")
      || channels.get(ev.title);
    if (!ch) return;
    if (!ch.acts) ch.acts = [];
    if (ev.phase === "start") {
      ch.tool = ev.tool;
      ch.hedef = ev.hedef || "";
      ch.tools += 1;
      ch.acts.push({
        name: ev.tool || "",
        hedef: ev.hedef || "",
        phase: "run",
      });
      if (ch.acts.length > KEEP_ACTS) ch.acts.shift();
    } else {
      ch.tool = ev.tool + (ev.phase === "fail" ? " ✗" : " ✓");
      if (ev.hedef) ch.hedef = ev.hedef;
      const last = ch.acts[ch.acts.length - 1];
      if (last && last.name === ev.tool) {
        last.phase = ev.phase === "fail" ? "fail" : "ok";
        if (ev.hedef) last.hedef = ev.hedef;
      } else {
        ch.acts.push({
          name: ev.tool || "",
          hedef: ev.hedef || "",
          phase: ev.phase === "fail" ? "fail" : "ok",
        });
        if (ch.acts.length > KEEP_ACTS) ch.acts.shift();
      }
    }
    render();
  }

  function end(ev) {
    const ch = channels.get(keyOf(ev)) || channels.get(ev.title);
    if (!ch) return;
    ch.state = ev.ok ? "done" : "fail";
    ch.tool = "";
    ch.wait = null;
    ch.turns = ev.turns; ch.tools = ev.tools != null ? ev.tools : ch.tools;
    if (ev.ozet) ch.ozet = ev.ozet;
    if (ev.deliverable) ch.deliverable = ev.deliverable;
    if (ev.model) ch.model = ev.model;
    if (ev.usage) ch.usage = ev.usage;
    prune();
    render();
    // If everything finished and the deck is not pinned, it withdraws after
    // a while — the channels are NOT deleted: clicking the badge shows the
    // last five again.
    if (!pinned && [...channels.values()].every(c => c.state !== "run")) {
      clearTimeout(fadeTimer);
      fadeTimer = setTimeout(() => { if (!anyRunning()) hide(); }, 6000);
    }
  }

  function wait(ev) {
    const ch = channels.get(keyOf(ev))
      || [...channels.values()].find(c => c.title === ev.title && c.state === "run");
    if (!ch || ch.state !== "run") return;
    if (ev.kip === "bitti" || ev.kip === "iptal") {
      ch.wait = null;
      if (!ch.tool || String(ch.tool).startsWith(t("Model bekleniyor"))
          || String(ch.tool).startsWith(t("Model yanıt vermedi"))) {
        ch.tool = "";
      }
      render();
      return;
    }
    let msg = ev.kip === "hata"
      ? t("Model yanıt vermedi")
      : t("Model bekleniyor");
    if (ev.deneme && ev.toplam) msg += ` (${ev.deneme}/${ev.toplam})`;
    if (ev.saniye) msg += ` · ${ev.saniye}s`;
    ch.tool = msg;
    ch.wait = ev;
    if (ev.kip === "hata") {
      ch.state = "fail";
      ch.wait = null;
    }
    open();
    render();
  }

  const anyRunning = () => [...channels.values()].some(c => c.state === "run");

  // Startup seed: the panel is event-driven, but after a page refresh or an
  // app restart the events have already passed. The single source of truth is
  // the real channel list in /api/state (the agent's ledger): the map is
  // rebuilt from scratch — a "running" channel absent from the snapshot is a
  // ghost and is not drawn. Orphans (left unfinished by the previous session)
  // are listed as a faded "yarım kaldı" row.
  function seed(list) {
    channels.clear();
    for (const ev of list || []) {
      if (!ev || (!ev.id && !ev.title)) continue;
      channels.set(keyOf(ev), {
        title: ev.title || ev.id, model: ev.model || "", id: ev.id || "",
        bg: !!ev.bg, tool: "", tools: 0, state: ev.state || "done",
        ozet: ev.ozet || "", open: false,
      });
    }
    prune();
    render();
    // If a channel is genuinely running, the deck comes up open; otherwise
    // the badge suffices — the orphan/finished inventory shows on click.
    if (anyRunning()) open();
    else if (!pinned) hide();
  }

  // The finished-channel inventory is bounded: the oldest finished ones
  // drop, running ones stay.
  function prune() {
    const done = [...channels.entries()].filter(([, c]) => c.state !== "run");
    for (let i = 0; i < done.length - KEEP_DONE; i++) channels.delete(done[i][0]);
  }

  // --- drawing ---------------------------------------------------------

  function render() {
    body.replaceChildren();
    const list = [...channels.values()];
    if (!list.length) {
      body.append(el("p", "orch-blank", t("Şu an alt ajan yok. Dornick bir işi böldüğünde kanallar burada belirir.")));
    }
    for (const ch of list) body.append(card(ch));

    const running = list.filter(c => c.state === "run").length;
    if (running > 0) {
      status.textContent = t("Şef bekliyor · ") + running + t(" kanal çalışıyor");
      status.className = "orch-status waiting";
    } else if (list.some(c => c.state === "yetim")) {
      status.textContent = t("Yarım kalan yardımcı var — istersen sürdürülebilir");
      status.className = "orch-status yetim";
    } else if (list.length) {
      status.textContent = t("Şef sürüyor · tüm kanallar bitti");
      status.className = "orch-status done";
    } else {
      status.textContent = t("Şef hazır");
      status.className = "orch-status";
    }

    // Footer: the limit on concurrently running helpers (context.max_agents).
    foot.replaceChildren();
    if (maxAgents != null) {
      foot.append(el("span", "orch-cap",
        t("Eşzamanlı yardımcı sınırı: ") + maxAgents + t(" · ayarlardan değişir")));
    }
  }

  function card(ch) {
    const wrap = el("div", "orch-ch " + ch.state);
    const top = el("div", "orch-ch-top");
    top.append(el("span", "orch-ch-dot"));
    top.append(el("span", "orch-ch-title", ch.title));
    if (ch.bg) top.append(el("span", "orch-ch-bg", t("arka plan")));
    if (ch.model) top.append(el("span", "orch-ch-model", shortModel(ch.model)));
    wrap.append(top);

    const line = el("div", "orch-ch-line");
    if (ch.state === "run") {
      const act = (ch.tool ? "▶ " + ch.tool : t("Düşünüyor…"))
        + (ch.hedef ? " · " + ch.hedef : "");
      line.append(el("span", "orch-ch-act", act));
    } else if (ch.state === "fail") {
      line.append(el("span", "orch-ch-act fail", t("Hata verdi")));
    } else if (ch.state === "yetim") {
      line.append(el("span", "orch-ch-act yetim", t("Yarım kaldı")));
    } else {
      line.append(el("span", "orch-ch-act ok", t("Bitti")));
    }
    // No tool counter on an orphan: the previous session's count is unknown
    // and writing "0 tools" would be wrong information.
    if (ch.state !== "yetim") {
      line.append(el("span", "orch-ch-count", ch.tools + t(" araç")));
    }
    const meter = formatUsage(ch.usage);
    if (meter) line.append(el("span", "orch-ch-meter", meter));
    wrap.append(line);

    if (ch.state === "run" && ch.acts && ch.acts.length) {
      const list = el("div", "orch-ch-acts");
      for (const a of ch.acts.slice(-KEEP_ACTS)) {
        const mark = a.phase === "fail" ? "✗"
          : a.phase === "ok" ? "✓" : "·";
        const row = el("div", "orch-ch-act-row" + (a.phase === "fail" ? " err" : ""));
        row.append(el("span", "orch-ch-act-mark", mark));
        row.append(el("b", null, a.name || ""));
        if (a.hedef) row.append(el("span", "orch-ch-act-hedef", a.hedef));
        list.append(row);
      }
      wrap.append(list);
    }

    if (ch.state === "yetim" && ch.id) {
      const acts = el("div", "orch-ch-resume-row");
      const resumeBtn = el("button", "orch-resume", t("Devam et"));
      resumeBtn.type = "button";
      resumeBtn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        resumeBtn.disabled = true;
        resumeBtn.textContent = t("Sürdürülüyor…");
        try {
          await fetch("/api/gorevler/devam", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: "c:" + ch.id }),
          });
        } catch { /* polling/SSE will update */ }
        // Refresh the snapshot — once running, the card turns to run.
        try {
          const s = await (await fetch("/api/state")).json();
          if (s && s.channels) seed(s.channels);
        } catch { render(); }
      });
      // Cancel: a job left unfinished must not rise again ("there is a
      // continue but no cancel" — live request, 31.08). Permanent: the server
      // writes a shutdown into the child's log; the startup scan skips it
      // from then on.
      const cancelBtn = el("button", "orch-resume orch-cancel", t("İptal et"));
      cancelBtn.type = "button";
      cancelBtn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        cancelBtn.disabled = true;
        cancelBtn.textContent = t("İptal ediliyor…");
        try {
          await fetch("/api/gorevler/iptal", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: "c:" + ch.id }),
          });
        } catch { /* the channel event will update */ }
        try {
          const s = await (await fetch("/api/state")).json();
          if (s && s.channels) seed(s.channels);
        } catch { render(); }
      });
      acts.append(resumeBtn, cancelBtn);
      wrap.append(acts);
    }

    // Finished channel: a click opens not the summary but the FULL report —
    // in the Viewer, like an artifact.
    if (ch.state !== "run") {
      wrap.classList.add("clickable");
      wrap.title = t("Raporu aç");
      wrap.addEventListener("click", (ev) => {
        ev.stopPropagation();
        if (ch.deliverable && ch.deliverable.url && typeof Viewer !== "undefined" && Viewer.page) {
          Viewer.page(ch.deliverable.url, ch.title);
          return;
        }
        if (ch.id && typeof Viewer !== "undefined" && Viewer.page) {
          Viewer.page("/gorev-rapor/" + encodeURIComponent(ch.id) + "/", ch.title);
          return;
        }
        ch.open = !ch.open;
        render();
      });
      if (ch.open && !ch.id) {
        wrap.append(el("div", "orch-ch-ozet", ch.ozet || t("(özet yok)")));
      }
    }
    return wrap;
  }

  const shortModel = (m) => {
    const s = String(m);
    const cut = s.split("/").pop();
    return cut.length > 22 ? cut.slice(0, 22) + "…" : cut;
  };

  function formatUsage(u) {
    if (!u) return "";
    const g = Number(u.girdi || 0) + Number(u.cikti || 0);
    if (!g) return "";
    return g >= 1000 ? (g / 1000).toFixed(1) + "k tok" : g + " tok";
  }

  // Read to display the helper limit from the settings (informational).
  let maxAgents = null;
  async function loadCap() {
    try {
      const s = await (await fetch("/api/settings")).json();
      const ma = s && s.context && s.context.max_agents;
      if (typeof ma === "number") maxAgents = ma;
    } catch { /* not important */ }
  }

  // --- deck ------------------------------------------------------------

  function open() {
    deck.hidden = false;
    clearTimeout(fadeTimer);
    document.body.classList.add("orch-open");
  }
  function hide() {
    if (!deck.hidden) keepPanel();
    deck.hidden = true;
    document.body.classList.remove("orch-open");
  }
  // Closing the deck closes the DECK, not the right pane. With the brain in
  // ambient mode the column folds to zero width the moment `orch-open`
  // drops (live wound, 05.09: "I close the orchestra and the whole right
  // window closes"). If nothing else holds the column open, the brain
  // stays put in the panel — the same switch Settings offers; ambient can
  // be turned back on there.
  function keepPanel() {
    const b = document.body.classList;
    const brainOn = b.contains("mind-on") && !b.contains("mind-off");
    const held = b.contains("viewing") || b.contains("cam-open") || b.contains("no-ambient");
    if (brainOn && !held && typeof window.brainCentered === "function") window.brainCentered(false);
  }
  function toggle() {
    if (deck.hidden) { pinned = true; open(); render(); }
    else { pinned = false; hide(); }
  }

  document.getElementById("orchestra").addEventListener("click", toggle);
  document.getElementById("orch-close").addEventListener("click", () => { pinned = false; hide(); });
  loadCap();

  return { start, tool, end, wait, toggle, seed };
})();
