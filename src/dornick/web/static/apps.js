// Apps panel: shows the things the agent produced in the workshop as a
// runnable catalog.
//
// Reading "I built a dashboard" in the chat and actually opening and using
// that dashboard are not the same thing. The panel draws projects in two
// groups by SCOPE —
//
//   In-app     apps that live inside Dornick (in a capsule)
//   External   separate apps that run on their own
//
// — with whatever is currently running on top. Every card carries what it
// is (kind badge), what it does (one-sentence summary) and its state (green
// dot = running). The search box and kind filter find things in a crowded
// workshop.
//
// The source is `/api/projects`; classification happens on the server, only
// drawing happens here.

// English translations of the texts this file shows the user. The source
// text stays Turkish; it is translated at display time with t("...").
Lang.add({
  "Aç": "Open",
  "Başlat": "Start",
  "Durdur": "Stop",
  "Klasörü göster": "Show folder",
  "Durduruluyor…": "Stopping…",
  "Arşivle": "Archive",
  "çalışıyor": "running",
  "durdu": "stopped",
  "eksik": "incomplete",
  "web": "web",
  "servis": "service",
  "betik": "script",
  "belge": "document",
  "sistem içi": "in-app",
  "dış": "external",
  "belirsiz": "unsorted",
  "Tümü": "All",
  "Web": "Web",
  "Servis": "Service",
  "Betik": "Script",
  "Belge": "Document",
  "Sistem içi": "In-app",
  "Dış uygulamalar": "External apps",
  "Belirsiz": "Unsorted",
  "Sorunlu manifestler": "Broken manifests",
  "Dornick'in içinde çalışır": "runs inside Dornick",
  "kendi başına çalışır": "runs on its own",
  "kapsamı sorulmadı — Dornick'e sorabilirsin": "scope unknown — you can ask Dornick",
  "yanlış yere yazılmış — uygulama sayılmadı":
    "written in the wrong place — not counted as an app",
  "toplu temizlik: artık kullanmadıklarını Arşivle ile kaldırabilirsin":
    "bulk cleanup: archive the ones you no longer use",
  "Henüz uygulama yok — Dornick bir şey üretince burada belirir.":
    "No apps yet — anything Dornick builds will show up here.",
  "Aramana uyan uygulama yok.": "Nothing matches your search.",
  "Okunamadı": "Could not read",
  "Ulaşılamadı": "Unreachable",
  "arşivlendi (atolye/.geri-donusum içinde — geri alınabilir)":
    "archived (in atolye/.geri-donusum — recoverable)",
  "Arşivlenemedi — çalışıyorsa önce durdur":
    "Could not archive — stop it first if it is running",
  "Dornick (kendisi)": "Dornick (itself)",
  "Dornick'in kendi süreci — panelden durdurulmuyor":
    "Dornick's own process — not stoppable from the panel",
  "Açıklama yok — Dornick'e sorup app.json'a yazdırabilirsin.":
    "No description — you can ask Dornick to write one into app.json.",
  "Bu uygulamanın klasörünü dosya gezgininde aç":
    "Open this app's folder in the file explorer",
  "Emin misin?": "Are you sure?",
  "Açılacak giriş dosyası bulunamadı": "No entry file to open",
  "Bu uygulama arşivlensin mi? atolye/.geri-donusum içine taşınır.":
    "Archive this app? It moves into atolye/.geri-donusum.",
});

const Apps = (() => {
  const panel = document.getElementById("apps-panel");
  const body = document.getElementById("apps-body");

  const folded = new Set();   // collapsed scope groups
  let all = [];               // last projects read
  let procs = [];             // last running processes read
  let query = "";             // search text
  let kindFilter = "";        // "" | web | service | tool | doc
  let brokenManifests = [];   // manifests written in the wrong place

  // Text always goes through t(): the source is Turkish, the display follows
  // the user's language. (Anything missing from the mapping stays Turkish —
  // so a missing translation is conspicuous.)
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = (typeof t === "function") ? t(text) : text;
    return node;
  };

  // The panel's OWN styles live with the panel: badges, the broken-manifest
  // section, the action row. The apps panel carries its own look without
  // bloating the main stylesheet (app.css).
  (function style() {
    if (document.getElementById("apps-ek-stil")) return;
    const s = document.createElement("style");
    s.id = "apps-ek-stil";
    s.textContent = `
/* Badges, reason, address and actions align with the description line
   (30px from the left): the card should read as a single column. */
.proj-badges {
  display: flex; gap: 5px; align-items: center; flex-wrap: wrap;
  margin: 0 8px 6px 30px;
}
.proj-name { flex: 1 1 auto; min-width: 0; }
.proj-state {
  font: 9px/1.5 var(--mono); letter-spacing: .04em; text-transform: uppercase;
  padding: 1px 6px; border-radius: 999px; white-space: nowrap;
}
.proj-state.live { color: var(--mint); background: #86EFAC18; box-shadow: inset 0 0 0 1px #86EFAC40; }
.proj-state.idle { color: var(--dim); background: var(--raise); }
.proj-state.gap  { color: var(--amber); background: #F0A02018; box-shadow: inset 0 0 0 1px #F0A02040; }
.proj-why {
  font: 10px/1.5 var(--mono); color: var(--amber); margin: 0 8px 6px 30px;
  overflow-wrap: anywhere;
}
.proj-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.proj .proj-actions { margin: 0 8px 10px 30px; }
.proj-view .proj-actions { margin-top: 8px; }
.proj-addr {
  font: 10px var(--mono); color: var(--mint); background: none; border: 0;
  cursor: pointer; padding: 0; margin: 0 8px 6px 30px; display: block;
  text-align: left; overflow-wrap: anywhere;
}
.proj-addr:hover { text-decoration: underline; }
.apps-group-hint.tidy { color: var(--amber); }
.apps-sorun { margin: 6px 4px 12px; }
.apps-sorun-row {
  padding: 7px 9px; margin: 5px 0; border-radius: 7px;
  background: #F0A0200d; box-shadow: inset 0 0 0 1px #F0A02033;
}
.apps-sorun-name { font: 11px var(--mono); color: var(--amber); }
.apps-sorun-why { font-size: 11px; color: var(--dim); margin-top: 3px; line-height: 1.5; }
.apps-sorun-fix { font: 10px var(--mono); color: var(--faint); margin-top: 5px; line-height: 1.55; }
.apps-proc.self .apps-proc-dot { background: var(--faint); animation: none; }
.apps-proc-self-note { font: 9px var(--mono); color: var(--faint); flex: 0 0 auto; }
`;
    document.head.append(s);
  })();

  // Project kind → glyph and label.
  const PKIND = {
    web: { glyph: "◈", tag: "web" },
    service: { glyph: "⧉", tag: "servis" },
    desktop: { glyph: "▣", tag: "masaüstü" },
    tool: { glyph: "▶", tag: "betik" },
    doc: { glyph: "≡", tag: "belge" },
  };
  // Scope badge: in-app (inside Dornick) or external (on its own).
  const SCOPE = {
    "in-app": { label: "sistem içi", cls: "inapp" },
    external: { label: "dış", cls: "ext" },
    "": { label: "belirsiz", cls: "unknown" },
  };

  // --- search + filter --------------------------------------------------

  const search = document.getElementById("apps-search");
  const chips = document.getElementById("apps-chips");

  if (search) {
    search.addEventListener("input", () => { query = search.value.trim(); render(); });
  }
  if (chips) {
    const KINDS = [["", "Tümü"], ["web", "Web"], ["desktop", "Masaüstü"],
                   ["service", "Servis"], ["tool", "Betik"], ["doc", "Belge"]];
    for (const [key, label] of KINDS) {
      const chip = el("button", "apps-chip" + (key === "" ? " on" : ""), label);
      chip.dataset.kind = key;
      chip.onclick = () => {
        kindFilter = key;
        chips.querySelectorAll(".apps-chip").forEach((c) =>
          c.classList.toggle("on", c === chip));
        render();
      };
      chips.append(chip);
    }
  }

  function matches(p) {
    if (kindFilter && (p.kind || "doc") !== kindFilter) return false;
    if (!query) return true;
    const hay = [p.name, p.desc, p.howto, p.path, p.run]
      .join(" ").toLocaleLowerCase("tr");
    return query.toLocaleLowerCase("tr").split(/\s+/)
      .every((w) => hay.includes(w));
  }

  // --- loading ---------------------------------------------------------

  async function load() {
    body.textContent = "";
    await drawRunning();   // running processes on top, before projects
    drawArts();            // artifacts: permanent pages, before the catalog
    try {
      const data = await (await fetch("/api/projects")).json();
      all = data.projects || [];
      brokenManifests = data.sorunlar || [];
    } catch {
      body.append(el("p", "apps-blank", "Okunamadı"));
      return;
    }
    render();
  }

  // Redraws the projects (without touching the running section). Search and
  // filter call this on every keystroke; the running section has its own poll.
  function render() {
    body.querySelectorAll(".apps-catalog").forEach((n) => n.remove());
    const box = el("div", "apps-catalog");
    body.append(box);

    // Solo: only the chosen app's card, with its detail OPEN. No catalog,
    // search, running section or groups — the list is already in the sidebar.
    panel.classList.toggle("apps-solo", !!solo);
    if (solo) {
      const p = all.find((x) => x.name === solo);
      if (p) {
        const back = el("button", "apps-solo-back", "← Tüm uygulamalar");
        back.onclick = () => { solo = ""; panel.classList.remove("apps-solo"); render(); };
        box.append(back);
        const card = projectCard(p);
        box.append(card);
        toggleView(p, card);   // detail view open from the start
        markCards();
        return;
      }
      // If the app no longer exists (archived?) fall back to the catalog.
      solo = "";
      panel.classList.remove("apps-solo");
    }

    drawBrokenManifests(box);

    if (!all.length) {
      if (!procs.length && !brokenManifests.length) {
        box.append(el("p", "apps-blank",
          "Henüz uygulama yok — Dornick bir şey üretince burada belirir."));
      }
      return;
    }
    const found = all.filter(matches);
    if (!found.length) {
      box.append(el("p", "apps-blank", "Aramana uyan uygulama yok."));
      return;
    }
    // Grouped by SCOPE: in-app ones live inside Dornick (in a capsule);
    // external ones are separate apps on their own; the unsorted await
    // Dornick's scope question.
    const groups = [
      { key: "in-app", title: "Sistem içi", hint: "Dornick'in içinde çalışır" },
      { key: "external", title: "Dış uygulamalar", hint: "kendi başına çalışır" },
      { key: "", title: "Belirsiz", hint: "kapsamı sorulmadı — Dornick'e sorabilirsin" },
    ];
    for (const g of groups) {
      const items = found.filter((p) => (p.scope || "") === g.key);
      if (!items.length) continue;
      // With a search active the groups are always open: the user is looking
      // for something, and hiding a match inside a collapsed group would make
      // the search useless.
      const isOpen = !!query || !folded.has(g.key);
      const head = el("div", "apps-group scope-" + (g.key || "unknown"));
      head.append(el("span", "apps-fold", isOpen ? "▾" : "▸"));
      head.append(el("span", null, g.title));
      // When the unsorted box gets crowded (old experiments, three copies of
      // the same job) a cleanup hint appears: every card has Archive, one
      // click moves it into .geri-donusum, and it can be recovered.
      const hint = (g.key === "" && items.length >= 8)
        ? "toplu temizlik: artık kullanmadıklarını Arşivle ile kaldırabilirsin"
        : g.hint;
      head.append(el("i", "apps-group-hint" + (hint === g.hint ? "" : " tidy"), hint));
      head.append(el("b", "apps-group-count", String(items.length)));
      const groupBody = el("div", "apps-group-body");
      groupBody.hidden = !isOpen;
      head.style.cursor = "pointer";
      head.onclick = () => {
        isOpen ? folded.add(g.key) : folded.delete(g.key);
        render();
      };
      box.append(head, groupBody);
      for (const p of items) groupBody.append(projectCard(p));
    }
    markCards();
  }

  // A project card. The four questions the user wants answered at a glance,
  // in order: WHAT (name + kind badge), WHAT DOES IT DO (one-line
  // description), WHAT STATE (running / stopped / incomplete) and WHAT CAN I
  // DO (Open · Start/Stop · Show folder). The old card had only a single
  // "Run" button and never stated the state.
  function projectCard(p) {
    const wrap = el("div", "proj");
    wrap.dataset.path = p.path || "";
    wrap.dataset.entry = p.entry || "";
    const head = el("div", "proj-head " + p.kind);
    const meta = PKIND[p.kind] || PKIND.doc;
    head.append(el("span", "proj-glyph", meta.glyph));
    head.append(el("span", "proj-dot"));   // running mark (CSS shows it)
    const name = el("span", "proj-name", p.name);
    name.title = p.name;
    head.append(name);
    head.onclick = () => toggleView(p, wrap);
    wrap.append(head);

    // Badges UNDER THE NAME, on their own row. The panel is narrow (256px):
    // laying badges beside the name crushed it to zero width — the user
    // could not tell which app the card was.
    const badges = el("div", "proj-badges");
    badges.append(el("span", "proj-kind-tag " + p.kind, meta.tag));
    // State badge: the card's most asked-for fact. An "incomplete" app does
    // NOT drop off the list — the reason is written underneath.
    const st = state(p);
    badges.append(el("span", "proj-state " + st.cls, st.label));
    const scope = SCOPE[p.scope] || SCOPE[""];
    badges.append(el("span", "proj-scope " + scope.cls, scope.label));
    wrap.append(badges);
    // One-sentence summary: WHAT this app DOES. "I hit Run but I don't know
    // what happened" was exactly the absence of this line. Comes from `desc`
    // in app.json, else the first line of the README/docstring.
    wrap.append(el("div", "proj-desc" + (p.desc ? "" : " empty"),
      p.desc || "Açıklama yok — Dornick'e sorup app.json'a yazdırabilirsin."));
    // If incomplete, WHY: "entry bulunamadı: static/index.html". Both the
    // user and the model should be able to read what is wrong.
    if (p.eksik && p.neden) wrap.append(el("p", "proj-why", p.neden));

    // The live address sits on the card: reaching a running app should not
    // require opening the card.
    const live = liveOf(p);
    if (live && live.address) {
      const addr = el("button", "proj-addr", live.address);
      addr.onclick = (ev) => { ev.stopPropagation(); openLive(p, live); };
      wrap.append(addr);
    }

    wrap.append(actionRow(p, live, "card"));
    wrap.addEventListener("contextmenu", (ev) => appMenu(p, ev));
    return wrap;
  }

  // The card's action row. The same row is used in the project view too —
  // two different button sets in two places was confusing.
  function actionRow(p, live, where) {
    const row = el("div", "proj-actions");
    const stop = (ev) => ev.stopPropagation();

    // Open: live address, desktop (Start), or the entry file.
    if ((live && live.address) || p.entry || p.kind === "desktop") {
      const open = el("button", "proj-btn primary", "Aç");
      open.onclick = (ev) => { stop(ev); openApp(p, live); };
      row.append(open);
    }
    // Start / Stop: a single DYNAMIC button — it acts on the state at the
    // MOMENT of the click and the 4s poll refreshes its label (live
    // complaint: the state did not change without a page refresh; the button
    // stayed frozen in the first draw's snapshot).
    if (live || runnable(p)) {
      const st = el("button", "proj-btn act-run", "");
      const repaint = () => {
        const running = liveOf(p) || (live && procs.some((q) => q.pid === live.pid) ? live : null);
        st.textContent = t(running ? "Durdur" : "Başlat");
        st.classList.toggle("danger", !!running);
        st.hidden = running ? running.stoppable === false : !runnable(p);
      };
      repaint();
      st.onclick = (ev) => {
        stop(ev);
        const running = liveOf(p);
        if (running && running.stoppable !== false) stopProc(running);
        else if (!running && runnable(p)) launchProject(p);
        setTimeout(drawRunning, 800);
      };
      row.append(st);
    }
    // Show folder: "where is this thing?" — the card printed the path, but
    // finding it on disk was left to the user.
    const show = el("button", "proj-btn", "Klasörü göster");
    show.title = t("Bu uygulamanın klasörünü dosya gezgininde aç");
    show.onclick = async (ev) => { stop(ev); await revealApp(p); };
    row.append(show);

    // Archive only on the card (the project view keeps the detailed
    // "Delete"): to tidy the unsorted crowd with one click.
    if (where === "card" && !(p.scope || "")) {
      const arch = el("button", "proj-btn", "Arşivle");
      arch.onclick = (ev) => { stop(ev); archive(p, arch); };
      row.append(arch);
    }
    return row;
  }

  // State badge. Three states, three colors: live (green), stopped (grey),
  // incomplete (amber).
  function state(p) {
    if (liveOf(p)) return { cls: "live", label: "çalışıyor" };
    if (p.eksik) return { cls: "gap", label: "eksik" };
    return { cls: "idle", label: "durdu" };
  }

  const runnable = (p) => !!(p.run || p.kind === "service" || p.kind === "tool"
                             || p.kind === "desktop");

  // Does this project have a running process? Two sources: (1) the running
  // list (process ledger), (2) live info the server attached to the card
  // itself — after a Dornick restart the process is not in the ledger, but
  // the app keeps listening on its port.
  function liveOf(p) {
    const r = procs.find((q) =>
      q.path === p.path || (p.entry && q.path === p.entry));
    if (r) return r;
    if (p.address) {
      return { pid: p.pid, name: p.name, path: p.path,
               address: p.address, stoppable: p.stoppable !== false };
    }
    return null;
  }

  // "Open": live address → capsule; desktop → Start (window); else the entry.
  function openApp(p, live) {
    if (live && live.address) { openLive(p, live); return; }
    if (p.kind === "desktop" || (p.entry && /\.exe$/i.test(p.entry || ""))) {
      launchProject(p);
      return;
    }
    if (typeof Viewer !== "undefined" && p.entry) { Viewer.present(p.entry); close(); return; }
    toast(p.name + ": " + (p.neden || t("Açılacak giriş dosyası bulunamadı")));
  }

  // Refreshes the live state on the cards: green dot + state badge + action.
  // Cards are marked in place instead of being redrawn — the open project
  // view and search focus must not break.
  function paintViewLive(view, p) {
    view.querySelector(".proj-live")?.remove();
    const r = liveOf(p) || procs.find((q) => q.path === (p.path || ""));
    if (!r) return;
    const live = el("div", "proj-live");
    live.append(el("span", "apps-proc-dot"));
    live.append(el("span", null, "Çalışıyor" + (r.pid ? " · PID " + r.pid : "")));
    if (r.address) {
      const link = el("button", "apps-proc-addr", r.address);
      link.onclick = () => openLive(p, r);
      live.append(link);
    }
    view.prepend(live);
  }

  function markCards() {
    body.querySelectorAll(".proj").forEach((w) => {
      const p = all.find((q) => (q.path || "") === w.dataset.path);
      const r = p ? liveOf(p) : procs.find((q) => q.path === w.dataset.path);
      w.classList.toggle("running", !!r);
      const badge = w.querySelector(".proj-state");
      if (badge && p) {
        const st = state(p);
        badge.className = "proj-state " + st.cls;
        badge.textContent = t(st.label);
      }
      // The card and its open detail breathe together: the live row and the
      // Start/Stop labels are pulled to the current truth.
      if (p) {
        const running = liveOf(p);
        w.querySelectorAll(".proj-btn.act-run").forEach((btn) => {
          btn.disabled = false;   // the "Stopping…" lock is released by the real state
          btn.textContent = t(running ? "Durdur" : "Başlat");
          btn.classList.toggle("danger", !!running);
          btn.hidden = running ? running.stoppable === false : !runnable(p);
        });
        const view = w.querySelector(".proj-view");
        if (view) paintViewLive(view, p);
      }
    });
  }

  function openLive(p, live) {
    if (typeof Capsule !== "undefined") {
      Capsule.open({ name: p.name, pid: live.pid, address: live.address,
                     started: live.started });
      close();
    } else window.open(live.address, "_blank", "noopener");
  }

  async function revealApp(p) {
    let res;
    try {
      res = await (await fetch("/api/apps/reveal", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: p.path || p.entry }),
      })).json();
    } catch { res = { ok: false, error: t("Ulaşılamadı") }; }
    if (!res.ok) toast(res.error || t("Ulaşılamadı"));
  }

  function appMenu(p, ev) {
    if (typeof Menu === "undefined") return;
    const live = liveOf(p);
    const items = [];
    if ((live && live.address) || p.entry) {
      items.push({ label: "Aç", action: () => openApp(p, live) });
    }
    if (live && live.stoppable !== false) {
      items.push({ label: "Durdur", action: () => stopProc(live) });
    } else if (!live && runnable(p)) {
      items.push({ label: "Başlat", action: () => launchProject(p) });
    }
    items.push({ label: "Klasörü göster", action: () => revealApp(p) });
    items.push({ sep: true });
    items.push({ label: "Arşivle", risk: true, action: () => archiveNow(p) });
    Menu.open(ev, items);
  }

  async function archiveNow(p) {
    if (!confirm(t("Bu uygulama arşivlensin mi? atolye/.geri-donusum içine taşınır."))) return;
    const fake = { dataset: { armed: "1" } };
    await archive(p, fake);
  }

  // Archive: moves into .geri-donusum (no permanent delete). Two-step
  // confirmation — a stray click must not take a project away.
  async function archive(p, btn) {
    if (!btn.dataset.armed) {
      btn.dataset.armed = "1";
      btn.textContent = t("Emin misin?");
      setTimeout(() => { delete btn.dataset.armed; btn.textContent = t("Arşivle"); }, 3500);
      return;
    }
    let res;
    try {
      res = await (await fetch("/api/apps/remove", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: p.path }),
      })).json();
    } catch { res = { ok: false, error: t("Ulaşılamadı") }; }
    if (res.ok) {
      toast(p.name + " " + t("arşivlendi (atolye/.geri-donusum içinde — geri alınabilir)"));
      load();
      document.dispatchEvent(new Event("dornick-side-tazele"));
    } else {
      toast(res.error || t("Arşivlenemedi — çalışıyorsa önce durdur"));
    }
  }

  // Manifests written in the wrong place. Ignoring them silently left both
  // the model and the user in the dark ("I built the app but it's not in the
  // panel"): here they stand WITH THE REASON and THE FIX.
  function drawBrokenManifests(box) {
    if (!brokenManifests.length) return;
    const section = el("div", "apps-sorun");
    const head = el("div", "apps-group");
    head.append(el("span", null, "Sorunlu manifestler"));
    head.append(el("i", "apps-group-hint", "yanlış yere yazılmış — uygulama sayılmadı"));
    head.append(el("b", "apps-group-count", String(brokenManifests.length)));
    section.append(head);
    for (const s of brokenManifests) {
      const row = el("div", "apps-sorun-row");
      row.append(el("div", "apps-sorun-name", "atolye/" + s.path));
      row.append(el("div", "apps-sorun-why", s.uyari || ""));
      if (s.ogretici) row.append(el("div", "apps-sorun-fix", s.ogretici));
      section.append(row);
    }
    box.append(section);
  }

  // Project view: README/how-to-run + actions + live state.
  function toggleView(p, wrap) {
    const open = wrap.querySelector(".proj-view");
    if (open) { open.remove(); return; }
    body.querySelectorAll(".proj-view").forEach((n) => n.remove());

    const view = el("div", "proj-view");
    view.dataset.path = p.path || "";

    // Live state: while running, the address and duration show here too.
    // A separate function: the 4s poll also refreshes an OPEN detail (live
    // complaint, 31.08: the state did not arrive without a page refresh —
    // the cards refreshed but the open detail stayed frozen in the first
    // moment's snapshot).
    paintViewLive(view, p);
    // The incomplete manifest's reason here too: "entry bulunamadı: static/index.html".
    if (p.eksik && p.neden) view.append(el("p", "proj-why", p.neden));

    // How to run (README). Rendered as markdown when available, else plain text.
    if (p.howto) {
      const how = el("div", "proj-howto");
      if (typeof Markdown !== "undefined" && Markdown.into) Markdown.into(how, p.howto);
      else how.textContent = p.howto;
      view.append(el("div", "proj-howto-tag", "Nasıl çalıştırılır"), how);
    } else {
      view.append(el("p", "proj-howto empty", "README yok. Dornick'e sorabilirsin."));
    }

    // Where it is + what runs it: the user should find it on disk and see
    // the command. The path can already arrive with atolye/ — do not prepend
    // it again and write "atolye/atolye/…".
    const rel = p.path || p.entry || "";
    view.append(el("p", "proj-path", rel.startsWith("atolye") ? rel : "atolye/" + rel));
    if (p.run) view.append(el("p", "proj-cmd", "» " + p.run));

    // Open · Start/Stop · Show folder — the SAME row as the card: two
    // different button sets for the same job in two places was confusing.
    const row = actionRow(p, r, "view");

    // Open outside the system: a static web page runs fully from a file in a
    // real browser, no server — "it opens inside but I want it in the
    // browser too". ONLY for things that are the browser's job: Word/Excel
    // style documents do not get this button — trying to open them in a
    // browser sets the wrong expectation.
    const inBrowser = /\.(html?|svg)$/i.test(p.entry || "");
    if (p.entry && inBrowser) {
      const ext = el("button", "proj-btn", "Tarayıcıda");
      ext.title = "Varsayılan tarayıcıda aç (server gerekmez)";
      ext.onclick = async () => {
        let res;
        try {
          res = await (await fetch("/api/apps/open", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: p.entry }),
          })).json();
        } catch { res = { ok: false, error: "Ulaşılamadı" }; }
        toast(res.ok ? p.name + " tarayıcıda açıldı" : (res.error || "Açılamadı"));
      };
      row.append(ext);
    }
    // "Ask Dornick: how do I run this" — hands the project over as context.
    if (typeof setAppContext === "function") {
      const ask = el("button", "proj-btn", "Dornick'e sor");
      ask.title = "Bu projeyi konuşmanın bağlamına ver";
      ask.onclick = () => {
        setAppContext({ name: p.name, path: p.path, type: p.kind,
                        title: (p.desc || p.howto || "").slice(0, 120) });
        toast(p.name + " bağlama alındı");
        close();
      };
      row.append(ask);
    }

    // Delete: two-step confirmation (a stray click must not take a project
    // away). Not permanent — it moves into the workshop's .geri-donusum
    // folder; recoverable by hand.
    const del = el("button", "proj-btn danger", "Sil");
    del.onclick = async () => {
      if (!del.dataset.armed) {
        del.dataset.armed = "1";
        del.textContent = "Emin misin? Sil";
        setTimeout(() => { delete del.dataset.armed; del.textContent = "Sil"; }, 3500);
        return;
      }
      let res;
      try {
        res = await (await fetch("/api/apps/remove", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: p.path }),
        })).json();
      } catch { res = { ok: false, error: "Ulaşılamadı" }; }
      if (res.ok) {
        toast(p.name + " kaldırıldı (atolye/.geri-donusum içinde — geri alınabilir)");
        load();
      } else {
        toast(res.error || "Silinemedi — çalışıyorsa önce durdur");
      }
    };
    row.append(del);

    view.append(row);
    wrap.append(view);
  }

  // Launch the project. For folder projects the PROJECT PATH is sent: the
  // server runs the manifest's `run` command (npm start, dotnet run...) in
  // the project's own folder — not just Python scripts. IN-APP service/web
  // projects open the result in a capsule INSIDE Dornick; an external
  // project lives in its own window. Web/document → viewer.
  async function launchProject(p) {
    if (runnable(p)) {
      const target = p.single ? (p.entry || p.path) : p.path;
      let res;
      try {
        res = await (await fetch("/api/apps/run", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: target }),
        })).json();
      } catch { toast(p.name + " başlatılamadı"); return; }
      if (!res.ok) { toast(res.error || "Başlatılamadı"); return; }
      if (res.already) {
        toast(res.note || (p.name + " zaten çalışıyor"));
        drawRunning();
        return;
      }
      drawRunning(); setTimeout(drawRunning, 1400);
      // The capsule is ONLY for service/web projects. Desktop gets its own window.
      const servesWeb = p.kind === "service" || p.kind === "web";
      if (servesWeb && p.scope !== "external" && typeof Capsule !== "undefined" && res.pid) {
        toast(p.name + " başlatıldı");
        Capsule.open({ name: p.name, pid: res.pid });
        close();
      } else if (p.kind === "desktop") {
        toast(res.note || (p.name + " açıldı — görev çubuğunda penceresini ara"));
      } else {
        toast(p.name + " başlatıldı…");
        if (res.pid) {
          setTimeout(async () => {
            let alive = false;
            try {
              const data = await (await fetch("/api/apps/running")).json();
              alive = (data.running || []).some((q) => q.pid === res.pid);
            } catch { /* could not poll: stay silent */ }
            toast(alive
              ? p.name + " çalışıyor — panelin üstünde Çalışıyor bölümünde"
              : p.name + " çalıştı ve tamamlandı");
            drawRunning();
          }, 2500);
        }
      }
      return;
    }
    // Not runnable: web/document → viewer.
    if (typeof Viewer !== "undefined" && p.entry) { Viewer.present(p.entry); close(); return; }
    // No entry file: do not stay silent — the user must not live through
    // "I click and nothing happens"; say what they can do.
    toast(p.name + ": açılacak giriş dosyası bulunamadı — \"Dornick'e sor\" ile sorabilirsin");
  }

  // --- artifacts -------------------------------------------------------
  //
  // Permanent pages the agent published (report, dashboard, visualization).
  // The card in the chat can drift away; the gallery keeps them all in one
  // place: open (in-app viewer) + delete (two-step confirmation — the
  // server does not delete permanently, it moves to the trash).

  const artAddress = (a) => "/artifact/" + a.id + "/";

  // Converts an ISO stamp to a short local date: "26.08 14:05".
  function artWhen(iso) {
    const d = new Date(iso || "");
    if (isNaN(d)) return "";
    return d.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit" })
      + " " + d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  }

  async function drawArts() {
    const old = body.querySelector(".apps-arts");
    if (old) old.remove();

    const section = el("div", "apps-arts");
    const head = el("div", "apps-group", "Artifact'lar");
    head.append(el("i", "apps-group-hint", "kalıcı sayfalar"));
    const holder = el("div", "arts-body");
    holder.append(el("p", "apps-blank dugum-yukleniyor", "Yükleniyor…"));
    section.append(head, holder);
    // Sits before the catalog, after the running section.
    body.insertBefore(section, body.querySelector(".apps-catalog"));

    let rows;
    try {
      rows = (await (await fetch("/api/artifacts")).json()).artifacts || [];
    } catch {
      holder.textContent = "";
      holder.append(el("p", "apps-blank", "Okunamadı"));
      return;
    }
    renderArts(holder, rows);
  }

  function renderArts(holder, rows) {
    holder.textContent = "";
    const count = holder.parentElement.querySelector(".apps-group b");
    if (count) count.remove();
    if (!rows.length) {
      holder.append(el("p", "apps-blank",
        "Henüz artifact yok. Dornick kalıcı bir rapor ya da pano yayınladığında burada belirir."));
      return;
    }
    holder.parentElement.querySelector(".apps-group")
      .append(el("b", "apps-group-count", String(rows.length)));
    for (const a of rows) holder.append(artRow(a, holder));
  }

  function artRow(a, holder) {
    const row = el("div", "arts-row");
    row.tabIndex = 0;
    row.setAttribute("role", "button");
    row.title = (a.title || a.id) + " — görüntüleyicide aç";

    // The glyph comes from artGlyphSvg in app.js (DOM API — no markup
    // strings); a plain character fallback in case it did not load.
    const glyph = el("span", "arts-glyph");
    if (typeof artGlyphSvg === "function") glyph.append(artGlyphSvg());
    else glyph.textContent = "⬒";

    const main = el("div", "arts-main");
    main.append(el("div", "arts-name", a.title || a.id));
    main.append(el("div", "arts-meta",
      "v" + (a.surum || 1) + (a.updated ? " · " + artWhen(a.updated) : "")));

    const openArt = () => {
      if (typeof Viewer !== "undefined" && Viewer.page) {
        Viewer.page(artAddress(a), a.title || a.id);
        close();
      } else {
        window.open(artAddress(a), "_blank", "noopener");
      }
    };

    const openBtn = el("button", "arts-btn", "Aç");
    openBtn.onclick = (ev) => { ev.stopPropagation(); openArt(); };

    const dlBtn = el("button", "arts-btn", "İndir");
    dlBtn.title = "İndir (.html)";
    dlBtn.onclick = (ev) => {
      ev.stopPropagation();
      const url = artAddress(a);
      if (typeof Viewer !== "undefined" && Viewer.downloadArtifact) Viewer.downloadArtifact(url);
      else window.location.href = url + "?download=1";
    };
    const prBtn = el("button", "arts-btn", "Yazdır");
    prBtn.onclick = (ev) => {
      ev.stopPropagation();
      const url = artAddress(a);
      if (typeof Viewer !== "undefined" && Viewer.printPage) Viewer.printPage(url);
      else window.open(url, "_blank", "noopener");
    };

    // Delete: two-step confirmation — a stray click must not take a
    // deliverable away. The server does not delete permanently, it moves to
    // the trash; intent is asked anyway.
    const del = el("button", "arts-btn danger", "Sil");
    del.onclick = async (ev) => {
      ev.stopPropagation();
      if (!del.dataset.armed) {
        del.dataset.armed = "1";
        del.textContent = "Emin misin?";
        setTimeout(() => { delete del.dataset.armed; del.textContent = "Sil"; }, 3500);
        return;
      }
      let res;
      try {
        res = await (await fetch("/api/artifacts", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "remove", id: a.id }),
        })).json();
      } catch { res = { ok: false, error: "Ulaşılamadı" }; }
      if (res.ok) {
        toast((a.title || a.id) + " kaldırıldı (çöpe taşındı — geri alınabilir)");
        renderArts(holder, res.artifacts || []);
      } else {
        toast(res.error || "Silinemedi");
      }
    };

    row.append(glyph, main, openBtn, dlBtn, prBtn, del);
    row.onclick = openArt;
    row.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openArt(); }
    });
    return row;
  }

  // --- running apps ----------------------------------------------------
  //
  // If the agent started a script/server, it shows live here: when it bound
  // a web server, clicking the address opens it in a capsule, and each one
  // can be stopped. Polled periodically while the panel is open; the green
  // dots on the cards refresh with the same poll.

  let pollTimer = null;

  const mmss = (started) => {
    if (!started) return "";
    const s = Math.max(0, Math.floor(Date.now() / 1000 - started));
    const m = Math.floor(s / 60);
    return m ? `${m} dk ${s % 60} sn` : `${s} sn`;
  };

  async function drawRunning() {
    try {
      const data = await (await fetch("/api/apps/running")).json();
      procs = data.running || [];
    } catch { procs = []; }

    const old = body.querySelector(".apps-running");
    if (old) old.remove();
    markCards();
    if (!procs.length) return;

    const section = el("div", "apps-running");
    section.append(el("div", "apps-group", "Çalışıyor"));
    for (const p of procs) {
      // Dornick's OWN copy (when the model ran `dornick --web ...`): visible
      // but not like "your app" — separate name, dim dot, no Stop. Hiding it
      // would be wrong too; the user should know something runs there.
      const r = el("div", "apps-proc" + (p.self ? " self" : ""));
      r.append(el("span", "apps-proc-dot"));
      const name = el("span", "apps-proc-name", p.self ? t("Dornick (kendisi)") : p.name);
      name.title = (p.run || p.path || "") + (p.started ? " · " + mmss(p.started) : "");
      r.append(name);
      r.append(el("span", "apps-proc-time", mmss(p.started)));
      if (p.self) {
        r.append(el("i", "apps-proc-self-note",
          "Dornick'in kendi süreci — panelden durdurulmuyor"));
        section.append(r);
        continue;
      }
      if (p.address) {
        // Live server: opens in-system in a capsule (inside Dornick). The
        // capsule's own "open outside" button is there for whoever wants a
        // separate tab.
        const link = el("button", "apps-proc-addr", p.address);
        link.title = "Sistem içinde aç (kapsül)";
        link.onclick = () => {
          if (typeof Capsule !== "undefined") {
            Capsule.open({ name: p.name, pid: p.pid, address: p.address, started: p.started });
            close();
          } else window.open(p.address, "_blank", "noopener");
        };
        r.append(link);
      }
      const stop = el("button", "apps-proc-stop", "Durdur");
      stop.onclick = () => stopProc(p);
      r.append(stop);
      section.append(r);
    }
    // If the catalog is already drawn, go to the very top; else stand alone.
    body.insertBefore(section, body.firstChild);
  }

  // Stop and REPORT THE OUTCOME. The old version said "stopped" without
  // looking at the answer; when the process had not gone down the user lived
  // through "I say stop and it doesn't stop".
  async function stopProc(p) {
    // Optimistic UI: the button says "Stopping…" IMMEDIATELY. Killing a
    // process tree can take a second or two in the OS; the old version still
    // showed "Stop" in the meantime ("states don't update in realtime" —
    // live, 31.08). A burst of polls brings the transition to the screen
    // within seconds; the regular 4s poll tidies up the rest.
    const targets = body.querySelectorAll(
      '.proj[data-path="' + (p.path || "") + '"] .proj-btn.act-run');
    targets.forEach((b) => { b.disabled = true; b.textContent = t("Durduruluyor…"); });
    let res;
    try {
      res = await (await fetch("/api/apps/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pid: p.pid }),
      })).json();
    } catch { res = { ok: false, error: "Ulaşılamadı" }; }
    toast(res.ok ? (p.name || "süreç") + " durduruldu"
                 : (res.error || "Durdurulamadı"));
    for (const ms of [600, 1600, 3200]) setTimeout(drawRunning, ms);
    drawRunning();
  }

  // A short notification: a launched script has its own window, but the
  // "it started" feedback should show in the UI too.
  let toastTimer = null;
  function toast(text) {
    let bar = document.getElementById("apps-toast");
    if (!bar) {
      bar = el("div", "apps-toast");
      bar.id = "apps-toast";
      document.body.append(bar);
    }
    bar.textContent = text;
    bar.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => bar.classList.remove("show"), 2600);
  }

  // --- panel -----------------------------------------------------------

  function toggle() {
    if (panel.hidden) open(); else close();
  }

  // Solo mode: a single app was picked from the sidebar — not the catalog
  // but that app's detail page. The HUD button opens the full catalog.
  let solo = "";

  function show(name) {
    solo = name || "";
    open(true);
  }

  function open(keepSolo) {
    if (!keepSolo) solo = "";
    // On a wide screen the panel is a CENTER surface: it does not touch the
    // rail. In a narrow window the left overlays collide — there the
    // conversations close (old behavior).
    if (innerWidth <= 860 && typeof History !== "undefined") History.close();
    // One surface in the center: if the tasks panel is open, it withdraws.
    if (window.JobsPanel) JobsPanel.close();
    panel.classList.toggle("apps-solo", !!solo);
    {
      panel.hidden = false;
      document.body.classList.add("apps-open");
      // Re-read on EVERY open. Previously, after the first open only the
      // cache was drawn: if Dornick produced an app AFTER the panel opened
      // (or wrote its manifest later) the user saw the stale list until they
      // manually hit "refresh" — the direct cause of the "the app it built
      // didn't show in the panel" complaint.
      load();
      // Keep the running section live while the panel is open (the live
      // address appears late, a process can finish on its own). The poll
      // stops when the panel closes.
      clearInterval(pollTimer);
      pollTimer = setInterval(drawRunning, 4000);
    }
  }

  function close() {
    panel.hidden = true;
    document.body.classList.remove("apps-open");
    clearInterval(pollTimer);
    pollTimer = null;
  }

  document.getElementById("apps").addEventListener("click", toggle);
  document.getElementById("apps-close").addEventListener("click", close);
  document.getElementById("apps-refresh").addEventListener("click", load);

  return { toggle, open, close, load, show, menu: appMenu };
})();
