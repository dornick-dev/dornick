// Conversation history panel: past sessions.
//
// An important distinction — this is NOT a list of MEMORIES. A conversation
// is not a memory: memories form separately from conversations (none from
// one, or several). The web on the scene shows memories; this panel shows
// the raw conversations themselves. The two can be linked but are not the
// same thing.
//
// Opt-in: absent from the default minimal view, opens on demand. Sources:
// `/api/sessions` (list) and `/api/session?id=` (transcript).

// English translations of the texts this file shows the user. The source
// text stays Turkish; it is translated at display time with t("...").
Dil.ekle({
  "şu an açık": "open now",
  "koşuyor": "running",
  "biten": "done",
  "Tümü": "All",
  "Açık": "Open",
  "Koşuyor": "Running",
  "Biten": "Done",
  "Geçiliyor…": "Switching…",
  "Burada başlat": "Start here",
  "Vazgeç": "Cancel",
  "Sürücü seç": "Pick a drive",
  "üst klasör": "parent folder",
  "Başlatılıyor…": "Starting…",
  "Tur bitince geçilebilir": "You can switch when the turn ends",
  "Geçilemedi — Dornick meşgul olabilir, tur bitince dene.":
    "Could not switch — Dornick may be busy; try again after the turn.",
  "Okunamadı": "Could not load",
  "Eşleşen konuşma yok": "No matching conversation",
  "Henüz konuşma yok": "No conversations yet",
  "Aranıyor…": "Searching…",
  "Yükleniyor…": "Loading…",
  "içinde ara": "search inside",
  "Konuşmaların İÇİNDE ara — başlıkta değil, dökümde geçen söz":
    "Search inside conversations — the words spoken, not just the title",
  "Yeniden adlandır": "Rename",
  "Etiketle": "Tag",
  "Projeye taşı": "Move to project",
  "Klasör bağla": "Bind folder",
  "Model ata": "Set model",
  "Ad (boş = tarihten türet)": "Name (empty = derive from the talk)",
  "Etiketler — virgülle ayır (boş = kaldır)": "Tags — comma separated (empty = clear)",
  "Proje adı (boş = çıkar)": "Project name (empty = remove)",
  "Çalışma klasörü (boş = kaldır)": "Work folder (empty = clear)",
  "Model adı (boş = global ayar)": "Model name (empty = global setting)",
  "Etiket süzgeci": "Tag filter",
  "süzgeci kaldır": "clear filter",
  " tur": " turns",
  " eşleşme": " matches",
  "Yeni oturum için yeniden başlat": "Restart for a new session",
  "Dökümde ara": "Search in transcript",
  "Tüm konuşmalar": "All conversations",
  "Bitmemiş konuşmalar": "Open conversations",
  "Şu an çalışan": "Currently running",
  "Tamamlananlar": "Finished",
  "sağ tık: klasörde başlat": "right-click: start in a folder",
  " Yeni konuşma": " New conversation",
  "Yeni konuşma": "New conversation",
  "— Projesiz —": "— No project —",
  "Projesiz": "No project",
  "Konuşmalarda ara": "Search conversations",
  "Konuşmalar": "Conversations",
  "Görevler · Otomasyonlar": "Tasks · Automations",
  "Uygulamalar": "Apps",
  "Aç": "Open",
  "Arşivle": "Archive",
  "Bu sohbet arşivlensin mi? Listeden kalkar, geri alınabilir.":
    "Archive this chat? It leaves the list; you can still get it back.",
  "Açık sohbet arşivlensin mi? Yeni boş konuşma açılır; bu sohbet listeden kalkar.":
    "Archive the open chat? A new empty conversation opens; this one leaves the list.",
  "koşan sohbet arşivlenemez — tur bitince dene":
    "can't archive a running chat — try after the turn",
  "Arşivlenemedi": "Could not archive",
});

const History = (() => {
  const panel = document.getElementById("hist-panel");
  const body = document.getElementById("hist-body");
  const search = document.getElementById("hist-search");

  let sessions = [];
  let knownProjects = [];       // existing project names (suggested on assign)
  let knownTags = [];           // existing tags (suggestions + filter)
  let collapsed = new Set();    // collapsed project folders
  let loaded = false;
  let deep = false;             // "search inside": is transcript search on
  let searching = false;        // a server search is in flight
  let tagFilter = "";           // the chosen tag filter
  let statusFilter = "";        // "" | açık | koşuyor | biten
  let deepTimer = null;
  // A long list opens with "Daha fazla göster", not a scrollbar (Claude
  // Code's Show more). No cap while searching/filtering.
  let showAll = false;
  const SHOW_CAP = 16;
  const UNFILED = "— Projesiz —";

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  // --- loading ---------------------------------------------------------

  // With `query` given, the server searches inside the TRANSCRIPTS too and
  // sends the matching lines (`hits`). Without it, this is a mere list
  // refresh.
  function panelOpen() {
    return document.body.classList.contains("hist-open");
  }

  async function load(ara) {
    if (!loaded) { body.textContent = ""; body.append(el("p", "hist-blank dugum-yukleniyor", t("Yükleniyor…"))); }
    let data;
    try {
      const url = ara ? "/api/sessions?ara=" + encodeURIComponent(ara) : "/api/sessions";
      data = await (await fetch(url)).json();
    } catch {
      body.textContent = "";
      body.append(el("p", "hist-blank", t("Okunamadı")));
      return;
    }
    sessions = data.sessions || [];
    knownProjects = data.projects || [];
    knownTags = data.tags || [];
    loaded = true;
    searching = false;
    render();
    // With a running chat the list breathes: the title is now produced at
    // the START of the run (loop._oturum_basligi) and the session_title
    // event carries it instantly; this poll is the backup (a missed event
    // reaches the left side within 2 s).
    clearTimeout(liveRefresh);
    if (!ara && panelOpen() && sessions.some((s) => s.status === "koşuyor")) {
      liveRefresh = setTimeout(() => { if (panelOpen()) load(); }, 2000);
    }
  }
  let liveRefresh = null;

  function applyTitle(id, title) {
    if (!id || !title) return;
    const s = sessions.find((x) => x.id === id);
    if (s) {
      s.title = title;
      s.named = true;
      render();
      return;
    }
    // If the list has not loaded yet, fetch shortly.
    if (panelOpen()) load();
  }

  // Transcript search goes to the server; a short delay avoids a request
  // per keystroke. If the box empties, the search is cancelled and the
  // list refreshed.
  const DEEP_DELAY = 320;

  function scheduleDeep() {
    clearTimeout(deepTimer);
    const q = (search.value || "").trim();
    if (!deep || q.length < 2) {
      searching = false;
      // Deep search turned off: no leftover match traces.
      for (const s of sessions) s.hits = [];
      render();
      return;
    }
    searching = true;
    render();
    deepTimer = setTimeout(() => load(q), DEEP_DELAY);
  }

  function render() {
    body.textContent = "";
    const q = (search.value || "").trim().toLowerCase();
    // The local filter always runs (name, preview, project, tag); with deep
    // search on, matches from the server are accepted too — the phrase may
    // occur mid-transcript, not in the title.
    let shown = q
      ? sessions.filter(s =>
          (s.title + " " + s.preview + " " + (s.project || "") + " "
           + (s.path || "") + " " + (s.tags || []).join(" "))
            .toLowerCase().includes(q) || (s.hits || []).length)
      : sessions;
    if (tagFilter) shown = shown.filter(s => (s.tags || []).includes(tagFilter));
    if (statusFilter === "açık") {
      shown = shown.filter(s => s.current || s.status === "açık" || s.status === "koşuyor");
    } else if (statusFilter === "koşuyor") {
      shown = shown.filter(s => s.status === "koşuyor");
    } else if (statusFilter === "biten") {
      shown = shown.filter(s => !s.current && s.status !== "koşuyor");
    }

    drawTools();

    if (searching) {
      body.append(el("p", "hist-blank dugum-yukleniyor", t("Aranıyor…")));
      return;
    }

    if (!shown.length) {
      body.append(el("p", "hist-blank" + (loaded ? "" : " dugum-yukleniyor"),
        loaded ? (q || tagFilter ? t("Eşleşen konuşma yok") : t("Henüz konuşma yok"))
               : t("Yükleniyor…")));
      return;
    }

    // Folder name: the manual project label, else the last segment of the
    // bound path. So chats given a path via "Klasör bağla" also show under
    // Dornick/dornick (the Cursor Repositories layout).
    function klasorAdi(s) {
      if (s.project) return s.project;
      const p = String(s.path || "").replace(/\\/g, "/").replace(/\/+$/, "");
      if (!p) return UNFILED;
      const parts = p.split("/").filter(Boolean);
      return parts.length ? parts[parts.length - 1] : UNFILED;
    }

    // Group by PROJECT / folder first, then recency inside each folder.
    // The unfiled ones sit in a single cluster at the end.
    const byProject = new Map();
    for (const s of shown) {
      const key = klasorAdi(s);
      if (!byProject.has(key)) byProject.set(key, []);
      byProject.get(key).push(s);
    }
    // List cap: trimming happens BEFORE project grouping — newest 16.
    let trimmed = 0;
    if (!showAll && !q && !tagFilter && !statusFilter && shown.length > SHOW_CAP) {
      trimmed = shown.length - SHOW_CAP;
      shown = shown.slice(0, SHOW_CAP);
      byProject.clear();
      for (const s of shown) {
        const key = klasorAdi(s);
        if (!byProject.has(key)) byProject.set(key, []);
        byProject.get(key).push(s);
      }
    }
    // Projects alphabetical, unfiled last.
    const names = [...byProject.keys()].filter(n => n !== UNFILED).sort((a, b) => a.localeCompare(b, "tr"));
    if (byProject.has(UNFILED)) names.push(UNFILED);

    for (const name of names) {
      const items = byProject.get(name);
      // Moving the active one to the top made the list JUMP ("it won't stay
      // put"): order is always recency; the active one shows only through
      // emphasis.
      const isOpen = !collapsed.has(name);
      const head = el("div", "hist-folder" + (name === UNFILED ? " unfiled" : ""));
      head.append(el("span", "hist-fold", isOpen ? "▾" : "▸"));
      head.append(el("span", "hist-folder-name",
                     name === UNFILED ? t(UNFILED) : name));
      head.append(el("span", "hist-folder-count", String(items.length)));
      head.onclick = () => { isOpen ? collapsed.add(name) : collapsed.delete(name); render(); };
      body.append(head);
      if (isOpen) items.forEach(s => body.append(row(s)));
    }
    if (trimmed) body.append(showMore(trimmed));
  }

  // The strip under the search box: the "search inside" toggle and (if
  // any) the active tag filter. The box itself lives in the markup; this
  // strip is built right below it once.
  function drawTools() {
    let strip = document.getElementById("hist-tools");
    if (!strip) {
      strip = el("div", "hist-tools");
      strip.id = "hist-tools";
      search.parentElement.insertBefore(strip, search.nextSibling);
    }
    strip.textContent = "";

    const filters = el("div", "hist-status-filters");
    for (const [id, label, tip] of [
      ["", "Tümü", "Tüm konuşmalar"],
      ["açık", "Açık", "Bitmemiş konuşmalar"],
      ["koşuyor", "Koşuyor", "Şu an çalışan"],
      ["biten", "Biten", "Tamamlananlar"],
    ]) {
      const chip = el("button", "hist-status" + (statusFilter === id ? " on" : ""));
      chip.type = "button";
      chip.title = t(tip);
      chip.setAttribute("aria-pressed", statusFilter === id ? "true" : "false");
      chip.textContent = t(label);
      chip.onclick = () => { statusFilter = id; render(); };
      filters.append(chip);
    }
    strip.append(filters);

    const deepBtn = el("button", "hist-deep" + (deep ? " on" : ""));
    deepBtn.type = "button";
    deepBtn.replaceChildren();
    const ico = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    ico.setAttribute("viewBox", "0 0 16 16");
    ico.setAttribute("aria-hidden", "true");
    ico.classList.add("hist-deep-ico");
    const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("cx", "6.5"); c.setAttribute("cy", "6.5"); c.setAttribute("r", "4.2");
    c.setAttribute("fill", "none"); c.setAttribute("stroke", "currentColor");
    c.setAttribute("stroke-width", "1.5");
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    p.setAttribute("d", "M10.2 10.2 13.5 13.5");
    p.setAttribute("fill", "none"); p.setAttribute("stroke", "currentColor");
    p.setAttribute("stroke-width", "1.5");
    ico.append(c, p);
    const lbl = el("span", null, t("Dökümde ara"));
    deepBtn.append(ico, lbl);
    deepBtn.title = t("Konuşmaların İÇİNDE ara — başlıkta değil, dökümde geçen söz");
    deepBtn.onclick = () => { deep = !deep; scheduleDeep(); };
    strip.append(deepBtn);

    if (tagFilter) {
      const chip = el("button", "hist-label on");
      chip.type = "button";
      chip.textContent = "#" + tagFilter + " ×";
      chip.title = t("süzgeci kaldır");
      chip.onclick = () => { tagFilter = ""; render(); };
      strip.append(chip);
    }
  }

  function row(s) {
    const wrap = el("div", "hist-item" + (s.current ? " current" : "")
      + (s.status === "koşuyor" ? " running" : ""));
    const line = el("div", "hist-row");
    const dot = el("span", "hist-dot"
      + (s.status === "koşuyor" ? " run" : (s.current ? " on" : "")));
    line.append(dot);
    const titleEl = el("span", "hist-title" + (s.named ? " named" : ""), s.title);
    titleEl.title = s.named ? s.title : s.preview || s.title;
    line.append(titleEl);
    if (s.status === "koşuyor") line.append(el("span", "hist-live", t("koşuyor")));
    else if (s.current) line.append(el("span", "hist-live", t("şu an açık")));
    const bits = [_time(s.date)];
    if (s.turns) bits.push(s.turns + t(" tur"));
    if (s.model) {
      const short = String(s.model).includes("/")
        ? String(s.model).split("/").pop() : s.model;
      bits.push(short);
    }
    if (s.path) {
      const leaf = String(s.path).replace(/\\/g, "/").split("/").filter(Boolean).pop();
      if (leaf) bits.push("📁 " + leaf);
    }
    line.append(el("span", "hist-meta", bits.join(" · ")));
    const acts = el("div", "hist-acts");
    for (const [glyph, tip, action] of [
      ["✎", "Yeniden adlandır", editName],
      ["#", "Etiketle", editTags],
      ["⌗", "Projeye taşı", assignProject],
      ["📁", "Klasör bağla", assignPath],
      ["◈", "Model ata", assignModel],
    ]) {
      const btn = el("button", "hist-assign", glyph);
      btn.title = t(tip);
      btn.onclick = (ev) => { ev.stopPropagation(); action(s, wrap); };
      acts.append(btn);
    }
    line.append(acts);
    // Clicking the row: on the ACTIVE conversation the panel closes and the
    // ongoing chat shows — no switch call needed, so it always works even
    // while Dornick is busy. On another conversation we switch to it
    // (resume); if busy, resume tells the user — the click does not die
    // silently.
    line.onclick = () => {
      if (s.current) { if (innerWidth <= 860) close(); }
      else resume(s, wrap);
    };
    wrap.append(line);

    wrap.addEventListener("contextmenu", (ev) => sohbetMenu(s, wrap, ev));

    // Tag badges: clicking filters to that tag. A tag is not a folder — a
    // conversation can carry several tags, a project only one.
    if ((s.tags || []).length) {
      const tagStrip = el("div", "hist-tags");
      for (const etiket of s.tags) {
        const chip = el("button", "hist-label" + (etiket === tagFilter ? " on" : ""));
        chip.type = "button";
        chip.textContent = "#" + etiket;
        chip.onclick = (ev) => {
          ev.stopPropagation();
          tagFilter = (tagFilter === etiket) ? "" : etiket;
          render();
        };
        tagStrip.append(chip);
      }
      wrap.append(tagStrip);
    }

    // Transcript search matches: which phrase occurs where. Clicking the
    // row still opens the conversation.
    for (const hit of (s.hits || [])) {
      const trace = el("div", "hist-hit");
      trace.append(el("span", "hist-hit-who", hit.role === "user" ? "sen" : "Dornick"));
      trace.append(el("span", "hist-hit-text", hit.text));
      trace.onclick = () => {
        if (s.current) { if (innerWidth <= 860) close(); }
        else resume(s, wrap);
      };
      wrap.append(trace);
    }

    return wrap;
  }

  function sohbetMenu(s, wrap, ev) {
    if (typeof Menu === "undefined") return;
    const running = s.status === "koşuyor";
    Menu.ac(ev, [
      { ad: "Aç", is: () => {
        if (s.current) { if (innerWidth <= 860) close(); }
        else resume(s, wrap);
      } },
      { ad: "Yeniden adlandır", is: () => editName(s, wrap) },
      { ad: "Etiketle", is: () => editTags(s, wrap) },
      { ad: "Projeye taşı", is: () => assignProject(s, wrap) },
      { ad: "Klasör bağla", is: () => assignPath(s, wrap) },
      { ad: "Model ata", is: () => assignModel(s, wrap) },
      { ayrac: true },
      { ad: "Arşivle", risk: true, kapali: running,
        ipucu: running ? "koşan sohbet arşivlenemez — tur bitince dene" : "",
        is: () => archiveChat(s) },
    ]);
  }

  async function archiveChat(s) {
    const warning = s.current
      ? t("Açık sohbet arşivlensin mi? Yeni boş konuşma açılır; bu sohbet listeden kalkar.")
      : t("Bu sohbet arşivlensin mi? Listeden kalkar, geri alınabilir.");
    if (!confirm(warning)) return;
    let res;
    try {
      res = await (await fetch("/api/session/archive", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: s.id }),
      })).json();
    } catch { res = { ok: false }; }
    if (res && res.ok) {
      await load();
      setTimeout(load, 600);
      return;
    }
    status((res && res.error) ? res.error : t("Arşivlenemedi"));
  }

  // Renaming: a single inline box. Leaving it empty removes the name and
  // the title is again derived from the conversation's first words — no
  // separate "delete name" button needed.
  function editName(s, wrap) {
    const existing = wrap.querySelector(".hist-assign-box");
    if (existing) { existing.remove(); return; }

    const box = el("div", "hist-assign-box");
    const input = el("input", "hist-assign-input");
    input.type = "text";
    input.placeholder = t("Ad (boş = tarihten türet)");
    input.value = s.named ? s.title : "";

    const save = async () => {
      const ad = input.value.trim();
      box.remove();
      const saved = await saveMeta(s.id, { ad });
      if (saved) {
        s.named = !!saved.ad;
        if (saved.ad) s.title = saved.ad;
      }
      // If the name was deleted, the server knows the derived title: refresh.
      if (!ad) await load();
      else render();
    };
    input.onkeydown = (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); save(); }
      else if (ev.key === "Escape") { box.remove(); }
    };
    box.append(input);
    wrap.append(box);
    input.focus();
    input.select();
  }

  // Tags: comma-separated free text. Existing ones are suggested.
  function editTags(s, wrap) {
    const existing = wrap.querySelector(".hist-assign-box");
    if (existing) { existing.remove(); return; }

    const box = el("div", "hist-assign-box");
    const input = el("input", "hist-assign-input");
    input.type = "text";
    input.placeholder = t("Etiketler — virgülle ayır (boş = kaldır)");
    input.value = (s.tags || []).join(", ");
    input.setAttribute("list", "hist-tags-list");
    let list = document.getElementById("hist-tags-list");
    if (!list) { list = el("datalist"); list.id = "hist-tags-list"; document.body.append(list); }
    list.replaceChildren(...knownTags.map(x => { const o = el("option"); o.value = x; return o; }));

    const save = async () => {
      const etiketler = input.value.split(",").map(x => x.trim()).filter(Boolean);
      box.remove();
      const saved = await saveMeta(s.id, { etiketler });
      if (saved) s.tags = saved.etiketler || [];
      for (const tag of s.tags) {
        if (!knownTags.includes(tag)) knownTags.push(tag);
      }
      render();
    };
    input.onkeydown = (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); save(); }
      else if (ev.key === "Escape") { box.remove(); }
    };
    box.append(input);
    wrap.append(box);
    input.focus();
    input.select();
  }

  // Name/tag writes. A field not sent stays UNTOUCHED on the server: a
  // request changing only tags must not delete the name.
  async function saveMeta(id, fields) {
    try {
      const res = await (await fetch("/api/session/meta", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, ...fields }),
      })).json();
      if (res && res.ok) return res.meta || {};
      status((res && res.error) || t("Okunamadı"));
    } catch { status(t("Okunamadı")); }
    return null;
  }

  // A small inline editor: assign a project name to the session (or leave
  // empty to remove). Existing projects are suggested via datalist; Enter
  // saves.
  function assignProject(s, wrap) {
    const existing = wrap.querySelector(".hist-assign-box");
    if (existing) { existing.remove(); return; }

    const box = el("div", "hist-assign-box");
    const input = el("input", "hist-assign-input");
    input.type = "text";
    input.placeholder = t("Proje adı (boş = çıkar)");
    input.value = s.project || "";
    input.setAttribute("list", "hist-projects");
    let list = document.getElementById("hist-projects");
    if (!list) { list = el("datalist"); list.id = "hist-projects"; document.body.append(list); }
    list.replaceChildren(...knownProjects.map(p => { const o = el("option"); o.value = p; return o; }));

    const save = async () => {
      const name = input.value.trim();
      if (name === (s.project || "")) { box.remove(); return; }
      try {
        const res = await (await fetch("/api/session/project", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: s.id, project: name }),
        })).json();
        if (res && res.ok) { knownProjects = res.projects || knownProjects; }
      } catch { /* swallow */ }
      s.project = name;
      render();
    };
    input.onkeydown = (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); save(); }
      else if (ev.key === "Escape") { box.remove(); }
    };
    box.append(input);
    wrap.append(box);
    input.focus();
    input.select();
  }

  function assignPath(s, wrap) {
    const existing = wrap.querySelector(".hist-assign-box");
    if (existing) { existing.remove(); return; }
    const box = el("div", "hist-assign-box");
    const input = el("input", "hist-assign-input");
    input.type = "text";
    input.placeholder = t("Çalışma klasörü (boş = kaldır)");
    input.value = s.path || "";
    const save = async () => {
      const path = input.value.trim();
      box.remove();
      const saved = await saveMeta(s.id, { path });
      if (saved) s.path = saved.path || "";
      // Path → folder name: group the list right away (the server writes
      // set_project too).
      if (path) {
        const leaf = path.replace(/\\/g, "/").replace(/\/+$/, "").split("/").filter(Boolean).pop() || "";
        if (leaf && !s.project) s.project = leaf;
      }
      // If it is the active chat, apply immediately (also applied on
      // switch).
      if (s.current) {
        try {
          await fetch("/api/session/resume", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: s.id }),
          });
        } catch { /* swallow */ }
      }
      render();
    };
    input.onkeydown = (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); save(); }
      else if (ev.key === "Escape") { box.remove(); }
    };
    box.append(input);
    wrap.append(box);
    input.focus();
    input.select();
  }

  function assignModel(s, wrap) {
    const existing = wrap.querySelector(".hist-assign-box");
    if (existing) { existing.remove(); return; }
    const box = el("div", "hist-assign-box");
    const input = el("input", "hist-assign-input");
    input.type = "text";
    input.placeholder = t("Model adı (boş = global ayar)");
    input.value = s.model || "";
    const save = async () => {
      const model = input.value.trim();
      box.remove();
      const saved = await saveMeta(s.id, { model });
      if (saved) s.model = saved.model || "";
      if (s.current) {
        try {
          await fetch("/api/session/resume", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: s.id }),
          });
        } catch { /* swallow */ }
      }
      render();
    };
    input.onkeydown = (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); save(); }
      else if (ev.key === "Escape") { box.remove(); }
    };
    box.append(input);
    wrap.append(box);
    input.focus();
    input.select();
  }

  // Start in a folder (live request, 31.08 — "let me pick a folder and
  // start a conversation like yours"): a mini explorer via /api/gozat;
  // "Burada başlat" opens a new session + assigns the work folder +
  // applies it.
  function klasordeBaslat() {
    const existing = document.getElementById("hist-klasor-sec");
    if (existing) { existing.remove(); return; }
    const kutu = el("div", "hist-assign-box hist-klasor-kutu");
    kutu.id = "hist-klasor-sec";
    const titleEl = el("div", "hist-klasor-yol", "");
    const listEl = el("div", "hist-klasor-liste");
    const foot = el("div", "hist-klasor-alt");
    const startBtn = el("button", "plan-btn", t("Burada başlat"));
    startBtn.type = "button";
    const closeBtn = el("button", "plan-btn muted", t("Vazgeç"));
    closeBtn.type = "button";
    closeBtn.onclick = () => kutu.remove();
    foot.append(startBtn, closeBtn);
    kutu.append(titleEl, listEl, foot);
    let selected = "";
    async function browse(dirPath) {
      let data;
      try {
        data = await (await fetch("/api/gozat?yol=" + encodeURIComponent(dirPath || ""))).json();
      } catch { return; }
      selected = data.yol || "";
      titleEl.textContent = selected || t("Sürücü seç");
      startBtn.disabled = !selected;
      listEl.replaceChildren();
      if (data.ust !== null && data.ust !== undefined) {
        const upBtn = el("button", "hist-klasor-satir ust", "‹ " + t("üst klasör"));
        upBtn.type = "button";
        upBtn.onclick = () => browse(data.ust);
        listEl.append(upBtn);
      }
      for (const k of (data.klasorler || [])) {
        const satir = el("button", "hist-klasor-satir", k.ad || k.yol);
        satir.type = "button";
        satir.onclick = () => browse(k.yol);
        listEl.append(satir);
      }
    }
    startBtn.onclick = async () => {
      if (!selected) return;
      startBtn.disabled = true;
      startBtn.textContent = t("Başlatılıyor…");
      try {
        const res = await (await fetch("/api/session/new", { method: "POST" })).json();
        if (res && res.ok && res.id) {
          await saveMeta(res.id, { path: selected });
          await fetch("/api/session/resume", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: res.id }),
          });
        }
      } catch { /* the status row already speaks */ }
      kutu.remove();
      if (innerWidth <= 860) close(); else { load(); setTimeout(load, 600); }
    };
    // BELOW the row, not INSIDE it: hist-new.after shattered the flex row
    // (Yeni konuşma + Sürücü seç side by side — live, 01.09).
    const btn = document.getElementById("hist-new");
    const satir = (btn && btn.closest(".hist-new-row")) || btn;
    if (satir) satir.after(kutu);
    else document.getElementById("hist-panel")?.querySelector(".hist-head")?.after(kutu);
    browse("");
  }

  // New conversation: starts a fresh session. If the server does not
  // support it (old process), the user is told — not swallowed silently.
  async function newConversation() {
    let res;
    try {
      res = await (await fetch("/api/session/new", { method: "POST" })).json();
    } catch {
      res = { ok: false };
    }
    const btn = document.getElementById("hist-new");
    if (res && res.ok) {
      // The rail is permanent: a new conversation does NOT close it (live
      // complaint). Narrow windows retract the overlay; wide ones refresh
      // the list and mark the new session.
      if (innerWidth <= 860) close(); else { load(); setTimeout(load, 600); }
    } else {
      // Live new-session is not on the bridge yet: countEl so instead of
      // looking broken.
      btn.textContent = "Yeni oturum için yeniden başlat";
      setTimeout(() => {
        btn.replaceChildren();
        const plus = el("span", "hist-new-plus", "+");
        btn.append(plus, " Yeni konuşma");
      }, 2200);
    }
  }

  // Resume a past conversation: the server switches the session and emits
  // session_reset; the main stream clears the thread and loads the
  // transcript.
  async function resume(s, wrap) {
    status(t("Geçiliyor…"));
    let res;
    try {
      res = await (await fetch("/api/session/resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: s.id }),
      })).json();
    } catch { res = { ok: false }; }
    if (res && res.ok) {
      // On a wide screen the rail is a permanent column: switching
      // conversations does NOT close it. The list refreshes; if a race
      // happens while the server processes the switch, the "open now" mark
      // may miss the first load — a second refresh after a short delay
      // settles it.
      if (innerWidth > 860) { load(); } else close();
      return;
    }
    if (res && res.busy) {
      // A click while busy does not die silently: brief feedback + the row
      // is visually marked "waiting". Click again once the turn ends.
      status(t("Tur bitince geçilebilir"));
      if (wrap) {
        wrap.classList.add("waiting");
        setTimeout(() => wrap.classList.remove("waiting"), 4000);
      }
      return;
    }
    // A visible error: no bridge, or the session was not found.
    status((res && res.error) ? res.error : t("Geçilemedi — Dornick meşgul olabilir, tur bitince dene."));
  }

  // "Show more": with the trimmed row count, at the bottom of the list.
  function showMore(trimmed) {
    const btn = el("button", "hist-more", t("Daha fazla göster") + " · " + trimmed);
    btn.type = "button";
    btn.addEventListener("click", () => { showAll = true; render(); });
    return btn;
  }

  // A short status/error row above the panel.
  function status(text) {
    let bar = document.getElementById("hist-status");
    if (!bar) {
      bar = el("div", "hist-status");
      bar.id = "hist-status";
      body.parentElement.insertBefore(bar, body);
    }
    bar.textContent = text || "";
    bar.hidden = !text;
    if (text) setTimeout(() => { if (bar.textContent === text) { bar.hidden = true; } }, 4000);
  }

  // --- helpers ---------------------------------------------------------

  const _time = (date) => (date || "").slice(11, 16) || (date || "").slice(0, 10);

  // --- panel -----------------------------------------------------------

  function toggle_panel() {
    if (panel.hidden) open();
    else close();
  }
  function open() {
    userClosed = false;
    if (innerWidth <= 860 && typeof Apps !== "undefined") Apps.close();   // narrow: overlays must not clash
    panel.hidden = false;
    document.body.classList.add("hist-open");
    document.getElementById("history").classList.add("on");
    try { localStorage.setItem("dornick-rail", "acik"); } catch { /* file:// */ }
    load();
  }
  let userClosed = false;   // manually closed in this session
  function close() {
    panel.hidden = true;
    userClosed = true;
    document.body.classList.remove("hist-open");
    document.getElementById("history").classList.remove("on");
    // Deliberate decision: the choice is NOT WRITTEN TO DISK. The sidebar
    // is a permanent structure ("always open" like Claude Code); X hides
    // it only for this session, next launch it returns.
  }

  document.getElementById("history").addEventListener("click", toggle_panel);
  // The panel's own X is gone (Claude Code: ☰ as the single toggle); if
  // the id ever returns it gets wired again.
  const closeBtn = document.getElementById("hist-close");
  if (closeBtn) closeBtn.addEventListener("click", close);
  // The filter funnel: filter chips show on demand — plain by default.
  const funnel = document.getElementById("hist-filter-toggle");
  if (funnel) funnel.addEventListener("click", () => {
    const isOn = panel.classList.toggle("filters-on");
    funnel.classList.toggle("on", isOn);
  });
  document.getElementById("hist-new").addEventListener("click", newConversation);
  // Start-in-folder: the side button is gone — right-click / long press on
  // demand. A new conversation opens in the workshop; if a folder is
  // needed, Dornick opens one from the first message or the user picks
  // here.
  document.getElementById("hist-new").addEventListener("contextmenu", (ev) => {
    ev.preventDefault();
    klasordeBaslat();
  });
  document.getElementById("hist-new").title =
    t("Yeni konuşma") + " · " + t("sağ tık: klasörde başlat");
  search.addEventListener("input", () => { render(); scheduleDeep(); });

  // The rail defaults to OPEN and PERMANENT (the Claude Code habit:
  // conversations always on the left). Auto-opening the overlay in a
  // narrow window would ride on the chat — it starts closed there. When
  // the window widens it returns by itself (unless the user closed it by
  // hand this session).
  if (innerWidth > 860) open();
  window.addEventListener("resize", () => {
    if (innerWidth > 860 && panel.hidden && !userClosed) open();
    if (innerWidth <= 860 && !panel.hidden) { close(); userClosed = false; }
  });

  return { open, close, toggle: toggle_panel, newChat: newConversation,
           applyTitle,
           // Lane event (parallel sessions): the badge of a chat
           // running/finishing in the background refreshes live — with the
           // panel open the list reloads, closed the next opening is fresh
           // anyway.
           laneChanged: () => { try { if (panelOpen()) load(); } catch {} },
           // "Go to conversation" from the scene: the panel opens first —
           // the switch and any error message must live somewhere VISIBLE
           // (the status row in a closed panel died silently).
           resumeById: (id) => { open(); resume({ id }); } };
})();


// --- side sections: Tasks · Automations and Apps ------------------------
// The rail is the single sidebar: two collapsible sections under the
// conversations. Clicking a row opens the DETAIL in the CENTRE area
// (JobsPanel.show / Apps.open).
Dil.ekle({
  "Henüz görev yok": "No tasks yet",
  "Uygulama yok": "No apps yet",
  "otomasyon": "automation",
  "çalışıyor": "running",
  "eksik": "incomplete",
});

(() => {
  const elx = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  async function fillTasks(list, countEl) {
    let tasks = [];
    try { tasks = (await (await fetch("/api/jobs")).json()).tasks || []; } catch { /* no server */ }
    countEl.textContent = tasks.length || "";
    list.textContent = "";
    if (!tasks.length) { list.append(elx("div", "side-blank", t("Henüz görev yok"))); return; }
    for (const task of tasks.slice(0, 40)) {
      const row = elx("button", "side-row");
      row.type = "button";
      const stateCls = task.last_status === "koşuyor" ? " run"
        : (task.last_status === "hata" || task.last_status === "başlatılamadı") ? " bad"
        : task.kind_ui === "automation" ? " auto"
        : task.enabled ? " on" : "";
      row.append(elx("i", "side-row-dot" + stateCls),
                 elx("span", "side-row-name", task.title || task.id));
      if (task.kind_ui === "automation") row.append(elx("span", "side-row-meta", t("otomasyon")));
      row.addEventListener("click", () => { if (window.JobsPanel) JobsPanel.show(task.id); });
      row.addEventListener("contextmenu", (ev) => {
        if (window.JobsPanel && JobsPanel.menu) JobsPanel.menu(task, ev);
      });
      list.append(row);
    }
  }

  async function fillApps(list, countEl) {
    let projects = [];
    try { projects = (await (await fetch("/api/projects")).json()).projects || []; } catch { /* no server */ }
    // The sidebar shows only REAL apps: a known kind and not incomplete.
    // Stray workshop files (rapor.txt, betik.ps1) may sit as "unclear" in
    // the catalogue but must not litter the list here.
    projects = projects.filter((p) => p.kind && !p.eksik);
    countEl.textContent = projects.length || "";
    list.textContent = "";
    if (!projects.length) { list.append(elx("div", "side-blank", t("Uygulama yok"))); return; }
    for (const p of projects.slice(0, 40)) {
      const row = elx("button", "side-row");
      row.type = "button";
      row.append(elx("i", "side-row-dot" + (p.eksik ? " bad" : "")),
                 elx("span", "side-row-name", p.name));
      // The centre area holds only the CHOSEN one's detail: not the
      // catalogue, that app's page (the list is already here, on the
      // left).
      row.addEventListener("click", () => {
        if (typeof Apps !== "undefined") Apps.show(p.name);
      });
      row.addEventListener("contextmenu", (ev) => {
        if (typeof Apps !== "undefined" && Apps.menu) Apps.menu(p, ev);
      });
      list.append(row);
    }
  }

  const SECTIONS = [
    ["side-jobs-head", "side-jobs-list", "side-jobs-count", "dornick-side-jobs", fillTasks],
    ["side-apps-head", "side-apps-list", "side-apps-count", "dornick-side-apps", fillApps],
  ];

  for (const [headId, listId, countId, storeKey, fill] of SECTIONS) {
    const head = document.getElementById(headId);
    const list = document.getElementById(listId);
    const countEl = document.getElementById(countId);
    if (!head || !list) continue;

    const apply = (isOn) => {
      list.hidden = !isOn;
      head.querySelector(".side-fold").textContent = isOn ? "▾" : "▸";
      try { localStorage.setItem(storeKey, isOn ? "acik" : "kapali"); } catch { /* file:// */ }
      if (isOn) fill(list, countEl);
    };
    head.addEventListener("click", () => apply(list.hidden));

    let saved = null;
    try { saved = localStorage.getItem(storeKey); } catch { /* file:// */ }
    // Default open: the sidebar should show everything at a glance.
    apply(saved !== "kapali");
    document.addEventListener("dornick-side-tazele", () => {
      if (!list.hidden) fill(list, countEl);
    });
  }
})();

// --- quick navigation rows: detail in the centre area -------------------
(() => {
  const g = document.getElementById("side-jobs-nav");
  if (g) g.addEventListener("click", () => { if (window.JobsPanel) JobsPanel.open(); });
  const u = document.getElementById("side-apps-nav");
  if (u) u.addEventListener("click", () => { if (typeof Apps !== "undefined") Apps.open(); });
})();

// --- static shell labels go through translation -------------------------
// Sidebar v4 embedded these texts in the HTML; in English mode they stayed
// Turkish (caught in the showcase shoot). Translation is applied where the
// text is born.
(() => {
  const newChatBtn = document.getElementById("hist-new");
  if (newChatBtn && newChatBtn.lastChild && newChatBtn.lastChild.nodeType === 3) {
    newChatBtn.lastChild.textContent = " " + t("Yeni konuşma");
  }
  const searchBox = document.getElementById("hist-search");
  if (searchBox) searchBox.placeholder = t("Konuşmalarda ara");
  for (const nav of document.querySelectorAll(".side-nav span")) {
    nav.textContent = t(nav.textContent.trim());
  }
  const labelEl = document.querySelector(".side-label");
  if (labelEl) labelEl.textContent = t(labelEl.textContent.trim());
})();
