// Viewer: what the agent is touching right now.
//
// The chat tells what was done but cannot show it. When the agent writes a
// script, reading the sentence "I wrote it" and seeing the file are not the
// same thing; when it builds a site you need the site itself, not its
// source.
//
// So the panel carries two modes:
//
//   source    the file, in a line-numbered, coloured code view
//   stage     for .html the genuinely running form, in an isolated frame
//
// It opens by itself: when the agent touches a file the panel switches to
// it. If the user closes it, we never force it again — closing is a
// decision.

const Viewer = (() => {
  const panel = document.getElementById("viewer");
  const title = document.getElementById("viewer-path");
  const body = document.getElementById("viewer-body");
  const modes = document.getElementById("viewer-modes");

  // The full path/address sits clipped in the label; a click sends ALL of
  // it to the clipboard (the "I can't see the full file path" live wound —
  // the header's title showed on hover but could not be copied).
  if (title) {
    title.style.cursor = "copy";
    title.addEventListener("click", async () => {
      const full = title.title || title.textContent || "";
      if (!full) return;
      try {
        await navigator.clipboard.writeText(full);
        if (typeof say === "function") say(t("Yol kopyalandı ✓") + " " + full);
      } catch { /* no clipboard permission */ }
    });
  }

  Lang.add({
    "Kaynak": "Source", "Sahne": "Stage",
    "Kopyala": "Copy", "Kopyalandı ✓": "Copied ✓", "Kopyalanamadı": "Copy failed",
    "Sar": "Wrap", "Uzun satırları sar / tek satırda kaydır": "Wrap long lines / scroll instead",
    "Dosyayı panoya kopyala": "Copy file to clipboard",
    "İkili dosya": "Binary file", "Bu bir dizin": "This is a directory",
    "Görsel açılamadı": "Could not open the image",
    "Tıkla — 1:1 boyut / sığdır": "Click — actual size / fit",
    "Tıkla — sığdır": "Click — fit",
    "Tarayıcıda aç": "Open in browser", "Klasörde göster": "Show in folder",
    "Açılamadı": "Could not open",
    "Aç": "Open", "Varsayılan uygulamada aç": "Open in the default app",
    "Okunamadı": "Could not read", "Henüz bir şeye dokunulmadı": "Nothing touched yet",
    "Dosyanın başı gösteriliyor": "Showing the head of the file",
    "Sayfa yok": "No page",
    "İndir": "Download", "Yazdır / PDF": "Print / PDF",
    "Gerçek tarayıcıda aç": "Open in your real browser",
    "İndirildi": "Saved", "Yol kopyalandı ✓": "Path copied ✓",
    "Tıkla — tam yolu kopyala": "Click — copy full path",
    "İndirilemedi": "Could not download",
    "Yazdırılamadı": "Could not print",
    "Adres yok": "No address",
    "Değişiklikler": "Changes",
    "Tarayıcı": "Browser",
    "Yeni terminal": "New terminal",
    "Henüz bir sayfa yok. Dornick bir siteye gidince burada açılır.":
      "No page yet. When Dornick visits a site it opens here.",
    "Sekmeyi kapat": "Close tab",
  });

  // These tools touch a file; which argument holds it varies by tool.
  const WATCHED = new Set(["read_file", "write_file", "edit_file", "copy_in", "draw"]);

  // A drawing is a presentation, not a file: the agent calls it to show
  // something. It opens even if the user closed the panel earlier, and in
  // stage mode, not source — reading the drawing's HTML is not the point.
  const PRESENTS = new Set(["draw"]);

  let current = "";
  let mode = "source";
  let dismissed = false;
  let loading = null;
  let sourceText = "";   // for the copy button: the raw text on display
  let wrap = false;      // long lines: scroll (false) / wrap (true)
  let lastUrl = "";
  const termLines = [];  // {kind: "cmd"|"out"|"err", text}
  const TERM_CAP = 120;

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  // --- public surface ----------------------------------------------------

  function watch(tool, args) {
    if (!WATCHED.has(tool) || !args) return;
    if (PRESENTS.has(tool)) return;   // the path arrives when the tool finishes
    const path = args.to || args.path;
    if (typeof path === "string" && path.trim()) show(path.trim());
  }

  // The agent placed a drawing: open the panel, switch to stage mode.
  function present(path) {
    if (typeof path !== "string" || !path.trim()) return;
    dismissed = false;
    mode = "live";
    show(path.trim());
  }

  // A LIVE page served by the server (like an artifact): an address, not a
  // file. The content is fetched fresh on every open and shown in the SAME
  // isolated frame as drawings (no allow-same-origin): a page the agent
  // wrote cannot reach the program's DOM or the /api endpoints — scripting
  // its way past its own permission gate would be this program's most
  // expensive bug.
  let pageLabel = "";

  function page(url, label) {
    if (typeof url !== "string" || !url.trim()) return;
    dismissed = false;
    rememberDesk(true);
    mode = "live";
    pageLabel = label || url;
    current = "url:" + url.trim();
    lastUrl = url.trim();
    foldSide();
    panel.hidden = false;
    document.body.classList.add("viewing");
    load(current);
  }

  // Is this address open in the panel right now? (to refresh on artifact
  // updates)
  function showing(url) {
    return !panel.hidden && current === "url:" + url;
  }

  // Refresh what is shown when the work finishes: after a write completed,
  // the panel still held the old content. The path the tool reports comes
  // resolved, so it may not match `current` exactly — with the panel open
  // and a watched tool touched, reloading is the safest.
  function refresh(tool, path) {
    if (PRESENTS.has(tool)) { present(path); return; }
    if (panel.hidden || !WATCHED.has(tool)) return;
    if (typeof path === "string" && path.trim()) { current = path.trim(); }
    load(current);
  }


  // In the narrow band (<=1160) the sidebar FOLDS while the right surface
  // opens: both do not fit (measured — drawer mode floated the bar over the
  // chat and the "Dusunuyor" heading was unclickable, 31.08).
  function foldSide() {
    if (innerWidth <= 1160 && typeof History !== "undefined" && History.close) {
      try { History.close(); } catch { /* no panel */ }
    }
  }

  function show(path) {
    current = path;
    if (dismissed) return;      // the user closed it; we do not force
    foldSide();
    panel.hidden = false;
    document.body.classList.add("viewing");
    load(path);
  }

  // Coming from a file reference in the chat: OPEN the panel (even if the
  // user closed it earlier — this is a user request, not the agent's
  // imposition) and, with a line given, scroll there and highlight.
  //
  // The line is deferred work: the file comes from the server and the rows
  // only exist after drawing. `pendingLine` is read at the end of the
  // render.
  function open(path, line) {
    if (typeof path !== "string" || !path.trim()) return;
    dismissed = false;
    mode = "source";
    pendingLine = Number(line) > 0 ? Number(line) : 0;
    const target = path.trim();
    // If the same file is already open there is no need to reload: just go
    // to the line.
    if (!panel.hidden && current === target) { gotoLine(pendingLine); return; }
    show(target);
  }

  let pendingLine = 0;

  // Go to line: scroll and leave a brief highlight. The highlight is not
  // permanent — it stays long enough to answer "which line was it", then
  // fades; permanent, it would be a stain pointing at the wrong place
  // while browsing the file.
  function gotoLine(line) {
    pendingLine = 0;
    if (!(line > 0)) return;
    const rows = body.querySelectorAll(".viewer-code .vl");
    const row = rows[line - 1];
    if (!row) return;
    for (const old of body.querySelectorAll(".vl.hit")) old.classList.remove("hit");
    row.classList.add("hit");
    row.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  const DESK = "dornick-desk";
  function rememberDesk(on) {
    try {
      if (on) localStorage.removeItem(DESK);
      else localStorage.setItem(DESK, "off");
    } catch { /* pywebview / private mode */ }
  }

  function close() {
    panel.hidden = true;
    dismissed = true;
    rememberDesk(false);
    document.body.classList.remove("viewing"); document.body.classList.remove("viewer-max");
  }

  function host(label, fill) {
    dismissed = false;
    rememberDesk(true);
    current = "git:pane";
    pageLabel = label || "Git";
    mode = "git";
    foldSide();
    panel.hidden = false;
    document.body.classList.add("viewing");
    title.textContent = pageLabel;
    title.title = pageLabel;
    modes.textContent = "";
    loading = null;
    if (typeof fill === "function") fill(body);
    noteTab();
  }

  function hosted() {
    return !panel.hidden && current === "git:pane";
  }

  function hostedGoals() {
    return !panel.hidden && current === "plan:goals";
  }

  function toggle() {
    if (panel.hidden) {
      dismissed = false;
      rememberDesk(true);
      if (!current) { openPin("git:pane"); return; }
      panel.hidden = false;
      document.body.classList.add("viewing");
      load(current);
    } else {
      close();
    }
  }

  // --- loading -----------------------------------------------------------

  // The last two segments go into the header: the full path filled the row
  // and, clipped, left a residue like "…html" that said nothing.
  function label(path) {
    const parts = String(path || "").split(/[\/]/).filter(Boolean);
    return parts.length > 2 ? "…/" + parts.slice(-2).join("/") : parts.join("/");
  }

  // File size in the header: "how big a thing" should read at a glance as
  // much as "which file".
  function human(bytes) {
    if (typeof bytes !== "number") return "";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  }

  // --- tabs -------------------------------------------------------------
  //
  // The Cursor right panel: a fixed deck (Değişiklikler · Tarayıcı ·
  // powershell) + file tabs as they open. The strip always stays — it does
  // not vanish with a single file either.
  const PINNED = [
    { key: "git:pane", kind: "changes", label: () => t("Değişiklikler") },
    // To-do list: pinned only while items exist — absent when empty, as in
    // Cursor.
    { key: "plan:goals", kind: "goals", label: () => t("İş listesi"), when: "goals" },
    { key: "desk:browser", kind: "browser", label: () => t("Tarayıcı") },
    { key: "desk:term", kind: "term", label: () => "powershell" },
  ];
  let goalsPin = false;
  function setGoalsPin(on) {
    const next = !!on;
    if (goalsPin === next) {
      if (next && current === "plan:goals") drawTabs();
      return;
    }
    goalsPin = next;
    if (!next && current === "plan:goals") {
      // Emptied: return to the fixed deck.
      openPin("git:pane");
      return;
    }
    drawTabs();
  }
  const tabs = [];              // {key, mode, label} — file / url tabs
  function pinOn(key) {
    if (key === "git:pane") return "git:pane";
    if (key === "plan:goals") return "plan:goals";
    if (key === "desk:term") return "desk:term";
    if (key === "desk:browser" || String(key).startsWith("url:")) return "desk:browser";
    return "";
  }
  function noteTab() {
    if (!current) return;
    // An address IS the Browser tab itself: do not open a separate file
    // tab.
    if (PINNED.some((p) => p.key === current) || String(current).startsWith("url:")) {
      drawTabs();
      return;
    }
    const entry = {
      key: current, mode,
      label: String(current).startsWith("url:")
        ? (pageLabel || current.slice(4)) : label(current),
    };
    const i = tabs.findIndex((s) => s.key === current);
    if (i >= 0) tabs[i] = entry;
    else { tabs.push(entry); if (tabs.length > 8) tabs.shift(); }
    drawTabs();
  }
  function iconFor(kind) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("aria-hidden", "true");
    const add = (tag, attrs) => {
      const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
      for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
      svg.append(n);
    };
    if (kind === "changes") {
      add("circle", { cx: "5", cy: "4", r: "1.6", fill: "none", stroke: "currentColor", "stroke-width": "1.4" });
      add("circle", { cx: "5", cy: "12", r: "1.6", fill: "none", stroke: "currentColor", "stroke-width": "1.4" });
      add("circle", { cx: "12", cy: "8.5", r: "1.6", fill: "none", stroke: "currentColor", "stroke-width": "1.4" });
      add("path", { d: "M5 5.6v4.8M6.6 4.6c2.2.4 4.2 1.4 5.2 3.2", fill: "none", stroke: "currentColor", "stroke-width": "1.3" });
    } else if (kind === "browser") {
      add("circle", { cx: "8", cy: "8", r: "5.5", fill: "none", stroke: "currentColor", "stroke-width": "1.4" });
      add("path", { d: "M2.5 8h11M8 2.5c1.8 2.2 1.8 8.8 0 11M8 2.5c-1.8 2.2-1.8 8.8 0 11", fill: "none", stroke: "currentColor", "stroke-width": "1.2" });
    } else if (kind === "term") {
      add("rect", { x: "2", y: "3", width: "12", height: "10", rx: "1.4", fill: "none", stroke: "currentColor", "stroke-width": "1.4" });
      add("path", { d: "M5 7.2 7 8.5 5 9.8M8.5 10.4H11", fill: "none", stroke: "currentColor", "stroke-width": "1.3", "stroke-linecap": "round" });
    } else if (kind === "goals") {
      add("path", { d: "M3.5 4.5h9M3.5 8h9M3.5 11.5h6", fill: "none", stroke: "currentColor", "stroke-width": "1.4", "stroke-linecap": "round" });
      add("circle", { cx: "12.2", cy: "11.5", r: "1.4", fill: "currentColor" });
    }
    return svg;
  }
  function drawTabs() {
    const strip = document.getElementById("viewer-tabs");
    if (!strip) return;
    strip.textContent = "";
    strip.hidden = false;
    const activePin = pinOn(current);
    for (const pin of PINNED) {
      if (pin.when === "goals" && !goalsPin) continue;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "v-tab pin" + (pin.key === current || pin.key === activePin ? " on" : "");
      b.title = pin.label();
      const nameEl = document.createElement("span");
      nameEl.textContent = pin.label();
      b.append(iconFor(pin.kind), nameEl);
      b.onclick = () => openPin(pin.key);
      strip.append(b);
    }
    for (const sk of tabs) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "v-tab" + (sk.key === current ? " on" : "");
      b.title = String(sk.key).startsWith("url:") ? sk.key.slice(4) : sk.key;
      const nameEl = document.createElement("span");
      nameEl.textContent = sk.label;
      const x = document.createElement("i");
      x.textContent = "×";
      x.setAttribute("aria-label", t("Sekmeyi kapat"));
      x.onclick = (ev) => { ev.stopPropagation(); dropTab(sk.key); };
      b.append(nameEl, x);
      b.onclick = () => {
        if (sk.key === current) return;
        mode = sk.mode;
        current = sk.key;
        if (String(sk.key).startsWith("url:")) pageLabel = sk.label;
        load(sk.key);
      };
      strip.append(b);
    }
  }
  function openPin(key) {
    dismissed = false;
    rememberDesk(true);
    if (key === "desk:browser" && lastUrl) {
      page(lastUrl);
      return;
    }
    if (key === current && !panel.hidden) return;
    if (key === "git:pane") {
      host(t("Değişiklikler"), (el) => {
        if (typeof GitBar !== "undefined") GitBar.paint(el);
      });
      return;
    }
    if (key === "plan:goals") {
      showGoals();
      return;
    }
    current = key;
    mode = key === "desk:term" ? "term" : "live";
    foldSide();
    panel.hidden = false;
    document.body.classList.add("viewing");
    load(key);
  }
  function showGoals() {
    dismissed = false;
    rememberDesk(true);
    current = "plan:goals";
    pageLabel = t("İş listesi");
    mode = "goals";
    foldSide();
    panel.hidden = false;
    document.body.classList.add("viewing");
    title.textContent = pageLabel;
    title.title = pageLabel;
    modes.textContent = "";
    loading = null;
    if (typeof Goals !== "undefined" && Goals.paint) Goals.paint(body);
    else {
      body.textContent = "";
      body.append(el("p", "viewer-blank", t("İş listesi yok.")));
    }
    noteTab();
  }
  function psPrefix() {
    const bar = document.getElementById("git-bar");
    const cwd = (bar && bar.dataset && bar.dataset.root) || "";
    return cwd ? ("PS " + cwd + "> ") : "PS> ";
  }
  function paintTerm() {
    body.textContent = "";
    const pane = el("div", "desk-term");
    pane.append(el("div", "desk-term-name", "powershell"));
    const ps = psPrefix();
    for (const line of termLines) {
      const row = el("div", "desk-term-line " + line.kind);
      if (line.kind === "cmd") {
        row.append(el("span", "desk-ps", ps), el("span", "", line.text));
      } else {
        row.textContent = line.text;
      }
      pane.append(row);
    }
    const prompt = el("div", "desk-term-line cmd");
    prompt.append(el("span", "desk-ps", ps), el("span", "desk-cursor", ""));
    pane.append(prompt);
    body.append(pane);
    body.scrollTop = body.scrollHeight;
  }
  function paintBrowserEmpty() {
    body.textContent = "";
    body.append(el("p", "viewer-blank", t("Henüz bir sayfa yok. Dornick bir siteye gidince burada açılır.")));
  }
  function shellOut(e) {
    const d = e.detail;
    if (d && typeof d === "object" && d.output) return String(d.output).trim();
    if (typeof d === "string" && d.trim()) return d.trim();
    return String(e.summary || "").trim();
  }
  function feed(e) {
    if (!e) return;
    if (e.tool === "shell" || e.tool === "kos") {
      const cmd = (e.input && (e.input.command || e.input.cmd)) || "";
      const started = e.ms == null && e.summary == null && !e.detail;
      if (cmd && started) {
        termLines.push({ kind: "cmd", text: String(cmd).trim() });
      } else {
        const trimmed = String(cmd).trim();
        if (cmd && !termLines.some((l) => l.kind === "cmd" && l.text === trimmed)) {
          termLines.push({ kind: "cmd", text: trimmed });
        }
        const text = shellOut(e);
        if (text) termLines.push({ kind: e.error ? "err" : "out", text });
      }
      while (termLines.length > TERM_CAP) termLines.shift();
      if (!panel.hidden) {
        if (started && current !== "desk:term") openPin("desk:term");
        else if (current === "desk:term") paintTerm();
      }
    }
    if (e.tool === "browser" && e.input && e.input.url) {
      const act = e.input.action;
      if (!act || act === "open" || act === "go") lastUrl = String(e.input.url);
    }
  }
  function dropTab(key) {
    const i = tabs.findIndex((s) => s.key === key);
    if (i < 0) return;
    tabs.splice(i, 1);
    if (key === current) {
      const nxt = tabs[Math.min(i, tabs.length - 1)];
      if (nxt) { mode = nxt.mode; current = nxt.key; load(nxt.key); return; }
      openPin("git:pane");
      return;
    }
    drawTabs();
  }

  async function load(path) {
    noteTab();
    // The path label: `hidden = true` never turned back on — the
    // file/address never showed in the header ("I can't see the full file
    // path", 31.08). It stays hidden on the fixed decks (git/terminal),
    // visible on content.
    title.hidden = true;
    // The git board: GitBar draws the body; do not hit the file API.
    if (path === "git:pane") {
      title.textContent = pageLabel || t("Değişiklikler");
      title.title = pageLabel || t("Değişiklikler");
      modes.textContent = "";
      if (typeof GitBar !== "undefined") GitBar.paint(body);
      return;
    }
    if (path === "plan:goals") {
      title.textContent = t("İş listesi");
      title.title = t("İş listesi");
      modes.textContent = "";
      if (typeof Goals !== "undefined" && Goals.paint) Goals.paint(body);
      else {
        body.textContent = "";
        body.append(el("p", "viewer-blank", t("İş listesi yok.")));
      }
      return;
    }
    if (path === "desk:term") {
      modes.textContent = "";
      paintTerm();
      return;
    }
    if (path === "desk:browser") {
      modes.textContent = "";
      if (lastUrl) { page(lastUrl, pageLabel); return; }
      paintBrowserEmpty();
      return;
    }
    // Address mode: the server-served page is fetched fresh and opened in
    // the isolated frame. Same race rule: the last request wins.
    if (typeof path === "string" && path.startsWith("url:")) {
      const url = path.slice(4);
      title.textContent = pageLabel || url;
      title.title = url.startsWith("/") ? (location.origin + url) : url;
      title.hidden = false;
      modes.textContent = "";
      const token = {};
      loading = token;
      // A live app (localhost): not srcdoc — an iframe on its own origin.
      if (/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?\//i.test(url)
          || /^https?:\/\/(127\.0\.0\.1|localhost):\d+/i.test(url)) {
        if (loading !== token) return;
        body.textContent = "";
        body.append(liveFrame(url));
        modes.append(pageExportActs(url));
        return;
      }
      let html = "";
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) {
          if (loading === token) blank(t("Sayfa yok") + " (" + res.status + ")");
          return;
        }
        html = await res.text();
      } catch {
        if (loading === token) blank(t("Okunamadı"));
        return;
      }
      if (loading !== token) return;
      body.textContent = "";
      body.append(frame(html));
      if (url.startsWith("/artifact/") || url.includes("/artifact/")
          || url.startsWith("/gorev-rapor/") || url.includes("/gorev-rapor/")) {
        modes.textContent = "";
        modes.append(pageExportActs(url));
      }
      return;
    }

    title.textContent = label(path) || "—";
    title.title = path || "";
    title.hidden = !path;
    if (!path) { blank(t("Henüz bir şeye dokunulmadı")); return; }

    // The same file can trigger several times in a row; the last request
    // must win.
    const token = {};
    loading = token;

    let data;
    try {
      data = await (await fetch("/api/files?path=" + encodeURIComponent(path))).json();
    } catch {
      if (loading === token) blank(t("Okunamadı"));
      return;
    }
    if (loading !== token) return;

    if (data.error || data.entries) { blank(t("Bu bir dizin")); return; }
    render(data);
  }

  function blank(text) {
    body.textContent = "";
    modes.textContent = "";
    body.append(el("p", "viewer-blank", text));
  }

  function render(data) {
    body.textContent = "";
    sourceText = data.text || "";
    drawModes(data);

    // Name + size in the header; the full path sits in the hover title and
    // is copied to the clipboard on click.
    const size = human(data.size);
    title.textContent = (label(data.path) || "—") + (size ? " · " + size : "");
    title.title = data.path || "";
    title.hidden = !data.path;

    // Media: printing "İKİLİ DOSYA" meant not showing an image. Images,
    // audio, video and PDF genuinely open from the raw endpoint
    // (`/api/raw`).
    const kind = mediaKind(data.path);
    if (kind) { body.append(mediaView(kind, data)); return; }

    if (data.binary) { body.append(unknownBinary(data)); return; }

    if (mode === "live" && isPage(data.path)) {
      body.append(frame(data.text || ""));
      return;
    }

    // An .md file should appear formatted; the rest in the code view.
    if (/\.mdx?$/i.test(data.path)) {
      const holder = el("div", "viewer-source");
      holder.append(Markdown.render(sourceText));
      body.append(holder);
    } else {
      body.append(codeView(sourceText, language(data.path)));
    }
    if (data.truncated) body.append(el("p", "viewer-blank", t("Dosyanın başı gösteriliyor")));
    // Coming from a chat reference (`loop.py:42`) the line only exists
    // here, after drawing: the pending request is now fulfilled.
    if (pendingLine) gotoLine(pendingLine);
  }

  // --- media -------------------------------------------------------------
  //
  // Opening a PNG made the panel print "İKİLİ DOSYA": when the agent
  // produced an image ("I drew the chart") the user could not see it — the
  // chat telling without showing is the very reason this panel exists.
  //
  // Bytes come from `/api/raw` (inside the workspace, path-escape guarded,
  // nosniff). The extension names the type; an unrecognised binary keeps
  // its old message but now with its size and a show-in-folder action.

  const IMAGE = /\.(png|jpe?g|gif|webp|bmp|ico|svg)$/i;
  const AUDIO = /\.(mp3|wav|ogg|m4a|flac)$/i;
  const VIDEO = /\.(mp4|webm|mov)$/i;
  const PDF = /\.pdf$/i;

  function mediaKind(path) {
    const name = String(path || "");
    if (IMAGE.test(name)) return "image";
    if (AUDIO.test(name)) return "audio";
    if (VIDEO.test(name)) return "video";
    if (PDF.test(name)) return "pdf";
    return "";
  }

  const rawUrl = (path) => "/api/raw?path=" + encodeURIComponent(path || "");

  function mediaView(kind, data) {
    const box = el("div", "viewer-media " + kind);
    const url = rawUrl(data.path);

    if (kind === "image") {
      const img = document.createElement("img");
      img.className = "viewer-img";
      img.alt = data.name || data.path || "";
      img.src = url;
      // Pixel dimensions in the header: for an image the answer to "how
      // big" is the edge lengths, not the file size.
      img.addEventListener("load", () => {
        const px = img.naturalWidth + "×" + img.naturalHeight;
        const size = human(data.size);
        title.textContent = (label(data.path) || "—") + " · " + px
                          + (size ? " · " + size : "");
      });
      img.addEventListener("error", () => {
        box.textContent = "";
        box.append(el("p", "viewer-blank", t("Görsel açılamadı")));
      });
      // Click toggles 1:1 ↔ fit. Text in a fitted screenshot is
      // unreadable; the 1:1 form scrolls inside the box.
      img.title = t("Tıkla — 1:1 boyut / sığdır");
      img.addEventListener("click", () => {
        box.classList.toggle("full");
        img.title = box.classList.contains("full")
          ? t("Tıkla — sığdır") : t("Tıkla — 1:1 boyut / sığdır");
      });
      box.append(img);
      return box;
    }

    if (kind === "audio" || kind === "video") {
      const player = document.createElement(kind === "audio" ? "audio" : "video");
      player.className = kind === "audio" ? "viewer-audio" : "viewer-video";
      player.src = url;
      player.controls = true;
      player.preload = "metadata";
      box.append(player);
      return box;
    }

    // PDF: the embedded viewer is the browser's own plugin — it cannot
    // reach the page DOM. If it fails to open (plugin off) the button below
    // remains.
    const holder = document.createElement("iframe");
    holder.className = "viewer-pdf";
    holder.src = url;
    holder.setAttribute("referrerpolicy", "no-referrer");
    box.append(holder);
    // Even if the embedded viewer fails, the user must be able to REACH the
    // file: open / download / show in folder. There used to be only
    // "Tarayıcıda aç", and when a report was produced the user could
    // neither open nor find it (live wound, 02.09: "it wrote a report, says
    // I couldn't read it").
    box.append(fileActions(data.path, url));
    return box;
  }

  // The shared action strip for a disk file: open in system · open in
  // browser · download · show in folder. PDF and unknown binaries use the
  // same strip.
  function fileActions(path, url) {
    const acts = el("div", "viewer-acts");

    const sysBtn = el("button", "viewer-open", t("Aç"));
    sysBtn.type = "button";
    sysBtn.title = t("Varsayılan uygulamada aç");
    sysBtn.addEventListener("click", () => post("/api/apps/file-open", path, acts));
    acts.append(sysBtn);

    acts.append(openButton(url, t("Tarayıcıda aç")));

    const dlLink = el("a", "viewer-open");
    dlLink.textContent = t("İndir");
    dlLink.href = url + "&download=1";
    dlLink.setAttribute("download", "");
    acts.append(dlLink);

    const show = el("button", "viewer-open", t("Klasörde göster"));
    show.type = "button";
    show.addEventListener("click", () => post("/api/apps/reveal", path, acts));
    acts.append(show);
    return acts;
  }

  // Shared POST + error display: silent failure is the worst state.
  async function post(endpoint, path, acts) {
    let answer = null;
    try {
      answer = await (await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      })).json();
    } catch { /* the server did not answer */ }
    if (!answer || answer.ok === false) {
      const why = el("p", "viewer-note bad", (answer && answer.error) || t("Açılamadı"));
      acts.after(why);
      setTimeout(() => why.remove(), 6000);
    }
  }

  // Genuinely binary and unrecognised: nothing to show, but no dead message
  // either — how much space it takes and where it lives.
  function unknownBinary(data) {
    const box = el("div", "viewer-media unknown");
    box.append(el("p", "viewer-blank", t("İkili dosya")));
    const size = human(data.size);
    if (size) box.append(el("p", "viewer-note", size));

    // The same action strip (open · open in browser · download · show in
    // folder).
    box.append(fileActions(data.path, rawUrl(data.path)));
    return box;
  }

  function openButton(url, text) {
    const button = el("button", "viewer-open", text);
    button.type = "button";
    button.addEventListener("click", () => window.open(url, "_blank", "noopener"));
    return button;
  }

  // --- code view ---------------------------------------------------------
  //
  // Line-numbered, coloured, ligature-free. Numbers are drawn with a CSS
  // counter (::before): they never mix into selected-and-copied text. A
  // long line either scrolls within itself or (the wrap button) breaks at
  // the line start; it never spills outside the panel.

  // Above this many rows we fall back to numberless plain text: tens of
  // thousands of DOM row nodes make scrolling drag.
  const ROW_CAP = 60000;

  function codeView(source, lang) {
    const box = el("div", "viewer-code" + (wrap ? " wrap" : ""));
    const total = countRows(source);

    if (total > ROW_CAP) {
      const pre = el("pre", "viewer-plain");
      pre.textContent = source;
      box.append(pre);
      return box;
    }

    // The number column sizes to the widest number: 9 and 999 align the
    // same.
    box.style.setProperty("--gutter", (String(total).length + 3) + "ch");
    for (const fragment of paintRows(source, lang, total)) {
      const row = el("div", "vl");
      const text = el("span", "vl-tx");
      text.append(fragment);
      row.append(text);
      box.append(row);
    }
    return box;
  }

  // The trailing empty row comes from the file's final newline; not worth
  // numbering.
  function countRows(source) {
    const rows = source.split("\n");
    if (rows.length > 1 && rows[rows.length - 1] === "") rows.pop();
    return Math.max(1, rows.length);
  }

  // Splits the coloured source into per-line pieces. The highlighter
  // paints the whole text in one go (multi-line tokens like block comments
  // only come out right that way); line numbers, though, need a box per
  // line. Painted nodes are split at newlines, classes preserved. No HTML
  // strings: every piece is again createElement + textContent.
  function paintRows(source, lang, total) {
    const scratch = document.createElement("code");
    if (lang && typeof Syntax !== "undefined" && Syntax.paint) {
      Syntax.paint(scratch, source, lang);
    } else {
      scratch.textContent = source;
    }

    const rows = [document.createDocumentFragment()];
    for (const node of [...scratch.childNodes]) {
      const pieces = String(node.textContent).split("\n");
      for (let i = 0; i < pieces.length; i++) {
        if (i > 0) rows.push(document.createDocumentFragment());
        if (!pieces[i]) continue;
        if (node.nodeType === Node.TEXT_NODE) {
          rows[rows.length - 1].append(document.createTextNode(pieces[i]));
        } else {
          const span = document.createElement("span");
          span.className = node.className;
          span.textContent = pieces[i];
          rows[rows.length - 1].append(span);
        }
      }
    }
    // Exactly in step with the gutter: pad with empty rows when short, drop
    // (the final newline) when over.
    while (rows.length < total) rows.push(document.createDocumentFragment());
    rows.length = total;
    return rows;
  }

  function drawModes(data) {
    modes.textContent = "";

    if (isPage(data.path)) {
      for (const [id, name] of [["source", t("Kaynak")], ["live", t("Sahne")]]) {
        const button = el("button", mode === id ? "on" : "", name);
        button.type = "button";
        button.addEventListener("click", () => { mode = id; render(data); });
        modes.append(button);
      }
    } else {
      mode = "source";
    }

    // Source tools have no business in stage mode, media or binaries:
    // "wrap" or "copy" on a PNG is meaningless.
    if (data.binary || mediaKind(data.path) || (mode === "live" && isPage(data.path))) return;

    if (!/\.mdx?$/i.test(data.path)) {
      const bend = el("button", wrap ? "on" : "", t("Sar"));
      bend.type = "button";
      bend.title = t("Uzun satırları sar / tek satırda kaydır");
      bend.addEventListener("click", () => { wrap = !wrap; render(data); });
      modes.append(bend);
    }

    const copy = el("button", "", t("Kopyala"));
    copy.type = "button";
    copy.title = t("Dosyayı panoya kopyala");
    copy.addEventListener("click", () => copyText(copy));
    modes.append(copy);
  }

  // Copies to the clipboard and shows a brief confirmation on the button:
  // clicking with nothing happening left a "did it work" ambiguity. The
  // main path is the Clipboard API; embedded frames may deny the
  // permission — then the old way (temporary textarea + execCommand) steps
  // in.
  function copyText(button) {
    const done = (msg, ok) => {
      button.textContent = msg;
      button.classList.toggle("ok", ok);
      setTimeout(() => {
        button.textContent = t("Kopyala");
        button.classList.remove("ok");
      }, 1400);
    };
    const fallback = () => {
      const ok = legacyCopy(sourceText);
      done(ok ? t("Kopyalandı ✓") : t("Kopyalanamadı"), ok);
    };
    try {
      navigator.clipboard.writeText(sourceText)
        .then(() => done(t("Kopyalandı ✓"), true), fallback);
    } catch {
      fallback();
    }
  }

  function legacyCopy(text) {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    area.remove();
    return ok;
  }

  // The page the agent built is shown in a frame so it genuinely runs, but
  // isolated: `allow-same-origin` is not granted, so the page cannot reach
  // this program's DOM, cookies or `/api` endpoints.
  function frame(html) {
    const node = document.createElement("iframe");
    node.className = "viewer-frame";
    node.setAttribute("sandbox", "allow-scripts");
    node.setAttribute("referrerpolicy", "no-referrer");
    node.srcdoc = injectScrollCss(html);
    return node;
  }

  function liveFrame(url) {
    const node = document.createElement("iframe");
    node.className = "viewer-frame viewer-live";
    node.setAttribute("referrerpolicy", "no-referrer");
    // A live app on its own origin: its API calls must work.
    node.setAttribute("sandbox",
      "allow-scripts allow-forms allow-same-origin allow-popups allow-downloads");
    node.src = url;
    return node;
  }

  const isPage = (path) => /\.html?$/i.test(path || "");

  // Extension → highlighter language. PHP missing here made PHP files
  // colourless plain text; the map was widened.
  const EXT = { py: "python", js: "javascript", mjs: "javascript", jsx: "javascript",
                ts: "typescript", tsx: "typescript", ps1: "powershell",
                psm1: "powershell", sh: "bash", bash: "bash", bat: "bash",
                json: "json", jsonl: "json", css: "css", scss: "css", less: "css",
                html: "html", htm: "html", xml: "xml", svg: "svg",
                sql: "sql", yml: "yaml", yaml: "yaml", toml: "toml", ini: "toml",
                cfg: "toml", php: "php", phtml: "php", c: "c", h: "c",
                cpp: "cpp", hpp: "cpp", cc: "cpp", cs: "cs", go: "go",
                rs: "rust", java: "java", rb: "ruby", lua: "lua",
                kt: "kotlin", swift: "swift" };

  const language = (path) => EXT[(path.split(".").pop() || "").toLowerCase()] || "";

  // --- wiring ------------------------------------------------------------

  document.getElementById("eye").addEventListener("click", toggle);
  document.getElementById("viewer-close").addEventListener("click", close);

  // Widening by dragging the panel edge. The single right-column width is
  // `--mind-w-user` (same as the brain grip): the chat shifts via
  // `--right-w`.
  (() => {
    const grip = document.getElementById("viewer-grip");
    if (!grip) return;
    const MIN = 240;
    const root = document.documentElement;
    let active = false;
    let originX = 0;
    let originW = 0;

    const width = () => {
      const col = document.getElementById("right-col");
      return (col || panel).getBoundingClientRect().width;
    };

    const move = (e) => {
      if (!active) return;
      // The right edge is fixed: dragging left widens the column (origin
      // delta). The ceiling matches mind-grip / CSS — 420/32vw allowed only
      // shrinking (live, 01.09).
      const max = Math.min(760, window.innerWidth * 0.55);
      const w = Math.max(MIN, Math.min(max, originW + originX - e.clientX));
      root.style.setProperty("--mind-w-user", Math.round(w) + "px");
    };

    const stop = () => {
      active = false;
      document.body.classList.remove("viewer-resize");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      window.removeEventListener("blur", stop);
      try {
        const w = parseInt(getComputedStyle(root).getPropertyValue("--mind-w-user"), 10);
        if (w) localStorage.setItem("dornick-mind-w", String(w));
      } catch { /* file:// */ }
    };

    grip.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      active = true;
      originX = e.clientX;
      originW = width();
      try { grip.setPointerCapture(e.pointerId); } catch { /* old engine */ }
      window.addEventListener("pointercancel", stop);
      window.addEventListener("blur", stop);
      root.style.setProperty("--mind-w-user", Math.round(originW) + "px");
      document.body.classList.add("viewer-resize");
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", stop);
    });
  })();

  // Opens an in-app path in the user's REAL browser. The server builds the
  // address (the real port) — the agent's guess of 8765 ended in
  // "connection refused" live; window.open inside the window is unreliable
  // too.
  async function openOutside(path) {
    const p = String(path || "");
    if (!p.startsWith("/")) { window.open(p, "_blank", "noopener"); return; }
    let out = null;
    try {
      out = await (await fetch("/api/disari-ac", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: p }),
      })).json();
    } catch { /* the server did not answer */ }
    if (!out || !out.ok) {
      if (typeof say === "function") say(t("Açılamadı") + (out && out.error ? ": " + out.error : ""), true);
    }
  }

  // Live page: open in the real browser + download + print.
  function pageExportActs(url) {
    const wrap = el("span", "viewer-export");
    const base = String(url).split("?")[0];
    const outBtn = el("button", "viewer-act", t("Tarayıcıda aç"));
    outBtn.type = "button";
    outBtn.title = t("Gerçek tarayıcıda aç");
    outBtn.addEventListener("click", (ev) => { ev.stopPropagation(); openOutside(base); });
    const dl = el("button", "viewer-act", t("İndir"));
    dl.type = "button";
    dl.title = t("İndir") + " (.html)";
    dl.addEventListener("click", (ev) => {
      ev.stopPropagation();
      downloadArtifact(base).catch((err) => {
        if (typeof say === "function") say(String(err.message || err), true);
      });
    });
    const pr = el("button", "viewer-act", t("Yazdır / PDF"));
    pr.type = "button";
    pr.addEventListener("click", (ev) => {
      ev.stopPropagation();
      printPage(base);
    });
    wrap.append(outBtn, dl, pr);
    return wrap;
  }

  async function downloadArtifact(url) {
    const base = String(url || "").split("?")[0];
    if (!base) throw new Error(t("Adres yok"));
    // Artifact: the SERVER saves the file (Downloads) and the full path is
    // announced. In the WebView2 window blob + <a download> died silently;
    // this path is the same in the window and the browser and the user sees
    // WHERE the file is (the "can't download / can't see the path" live
    // wound).
    if (/^\/artifact\//.test(base)) {
      let out = null;
      try {
        out = await (await fetch("/api/artifact/indir", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: base }),
        })).json();
      } catch { /* the server did not answer; fall back to the blob path */ }
      if (out && out.ok && out.path) {
        if (typeof say === "function") say(t("İndirildi") + ": " + out.path);
        return;
      }
      if (out && out.error) throw new Error(out.error);
    }
    const res = await fetch(base + (base.includes("?") ? "&" : "?") + "download=1",
                            { cache: "no-store" });
    if (!res.ok) throw new Error(t("İndirilemedi") + " (" + res.status + ")");
    const blob = await res.blob();
    let name = "download.html";
    const cd = res.headers.get("Content-Disposition") || "";
    const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
    const plain = /filename="?([^";]+)"?/i.exec(cd);
    if (star) {
      try { name = decodeURIComponent(star[1].trim()); } catch { name = star[1].trim(); }
    } else if (plain) {
      name = plain[1].trim();
    }
    const href = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = href;
    a.download = name;
    a.rel = "noopener";
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(href), 2000);
  }

  function printPage(url) {
    const base = String(url || "").split("?")[0];
    if (!base) return;
    fetch(base, { cache: "no-store" })
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.text(); })
      .then((html) => {
        const blob = new Blob([injectScrollCss(html)], { type: "text/html;charset=utf-8" });
        const href = URL.createObjectURL(blob);
        const iframe = document.createElement("iframe");
        iframe.setAttribute("aria-hidden", "true");
        iframe.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;opacity:0";
        iframe.onload = () => {
          try { iframe.contentWindow.focus(); iframe.contentWindow.print(); }
          catch { /* pywebview / sandbox */ }
          setTimeout(() => { iframe.remove(); URL.revokeObjectURL(href); }, 1500);
        };
        iframe.src = href;
        document.body.append(iframe);
      })
      .catch((err) => {
        if (typeof say === "function") say(t("Yazdırılamadı") + ": " + (err.message || err), true);
      });
  }

  function injectScrollCss(html) {
    const css = "<style id=\"dornick-scroll-theme\">"
      + "html{scrollbar-width:thin;scrollbar-color:rgba(240,160,32,.35) transparent}"
      + "::-webkit-scrollbar{width:8px;height:8px}"
      + "::-webkit-scrollbar-thumb{background:rgba(240,160,32,.3);border-radius:4px}"
      + "::-webkit-scrollbar-track{background:transparent}"
      + "</style>";
    const src = String(html || "");
    if (/<\/head>/i.test(src)) return src.replace(/<\/head>/i, css + "</head>");
    if (/<html[\s>]/i.test(src)) {
      return src.replace(/<html[^>]*>/i, (m) => m + "<head>" + css + "</head>");
    }
    return css + src;
  }

  function bootDesk() {
    if (innerWidth < 1021) return;
    try { if (localStorage.getItem(DESK) === "off") return; } catch { /* */ }
    openPin("desk:term");
  }
  bootDesk();
  window.addEventListener("resize", () => {
    if (innerWidth >= 1021 && panel.hidden && !dismissed &&
        (function wanted() {
          try { return localStorage.getItem(DESK) !== "off"; } catch { return true; }
        })()) {
      openPin("desk:term");
    }
  });

  return { present, page, showing, watch, refresh, show, open, close, toggle,
           host, hosted, hostedGoals, setGoalsPin, downloadArtifact, printPage,
           openOutside, feed, openPin };
})();

// Maximize / restore: the viewer covers the whole right region (the brain
// steps aside for the moment); pressing again returns to the dock layout.
// The scene re-measures itself on close (mindRect fresh every frame).
(() => {
  const btn = document.getElementById("viewer-max");
  if (!btn) return;
  btn.addEventListener("click", () => {
    document.body.classList.toggle("viewer-max");
  });
})();

(() => {
  const add = document.getElementById("viewer-add");
  if (!add) return;
  add.title = t("Yeni terminal");
  add.setAttribute("aria-label", t("Yeni terminal"));
  add.addEventListener("click", () => {
    if (typeof Viewer !== "undefined" && Viewer.openPin) Viewer.openPin("desk:term");
  });
})();
