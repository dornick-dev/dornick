// Composer surfaces: the `/` command book and the `@` file mention.
//
// Both are two states of the same thing: a single box that opens while
// typing in the composer, is navigated by keyboard, selected with Enter,
// closed with Escape. Hence ONE state machine — two separate menus meant
// two separate bugs (one opening while the other is open, arrow keys going
// to both at once).
//
// Two rules:
//
//   * Every row of the command book binds to a path that ALREADY EXISTS.
//     No invented commands: `/model` opens the model box in the dock,
//     `/durdur` presses the Stop button. Adding a command is one line in
//     the book.
//   * A file picked with `@` is not added SECRETLY. It shows as a chip and
//     the sentence entering the message is the very path written on the
//     chip: "Kullanıcı şu dosyayı işaret etti: <path>". The user can read
//     what they are sending.

Lang.add({
  "Yeni konuşma başlat": "Start a new conversation",
  "Geçmiş konuşmalar": "Past conversations",
  "Model seç — katalogda ara": "Pick a model — search the catalogue",
  "Yetki kipini değiştir": "Change the permission mode",
  "Koşan görevler — arka plan işleri ve yardımcılar":
    "Running tasks — background jobs and helpers",
  "Atölyedeki uygulamalar": "Apps in the workshop",
  "Yayınlanan artifact'lar — Uygulamalar panelinde":
    "Published artifacts — in the Apps panel",
  "Ayar sayfasını aç": "Open settings",
  "Bağlamı sıkıştır — konuşma kesilmez": "Compact the context — the conversation continues",
  "Koşan turu durdur": "Stop the running turn",
  "Komutlar ve kısayollar": "Commands and shortcuts",
  "Eşleşen komut yok.": "No matching command.",
  "Komutlar": "Commands",
  "Dosya ara": "Search files",
  "Eşleşen dosya yok.": "No matching file.",
  "Aranıyor…": "Searching…",
  "Bahisten çıkar": "Remove mention",
  "Kısayollar": "Shortcuts",
  "Enter — gönder · Shift+Enter — alt satır": "Enter — send · Shift+Enter — new line",
  "/ — komut defteri · @ — dosya işaret et": "/ — command book · @ — mention a file",
  "Escape — açık kutuyu kapat": "Escape — close the open box",
  "Bağlam sıkıştırılamadı.": "Could not compact the context.",
  "işaret edilen dosya": "mentioned file",
});

const Command = (() => {
  const input = document.getElementById("input");
  const pop = document.getElementById("compose-pop");
  const chipBox = document.getElementById("mentions");

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  const press = (id) => { const b = document.getElementById(id); if (b) b.click(); };

  const post = (path, payload) => fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  }).then(r => r.json()).catch(() => null);

  // --- command book ----------------------------------------------------
  //
  // The single source of truth. Adding a command is one line here; the
  // menu, the filter, the keyboard navigation and the `/yardim` listing
  // learn it by themselves.
  const BOOK = [
    { name: "yeni", what: "Yeni konuşma başlat", run: () => press("hist-new") },
    { name: "gecmis", what: "Geçmiş konuşmalar", run: () => press("history") },
    { name: "model", what: "Model seç — katalogda ara", run: () => press("dock-model") },
    { name: "yetki", what: "Yetki kipini değiştir", run: () => press("dock-mode") },
    { name: "gorevler", what: "Koşan görevler — arka plan işleri ve yardımcılar",
      run: () => {
        if (window.JobsPanel && JobsPanel.openLive) JobsPanel.openLive();
        else press("jobs");
      } },
    { name: "uygulamalar", what: "Atölyedeki uygulamalar", run: () => press("apps") },
    { name: "artifact", what: "Yayınlanan artifact'lar — Uygulamalar panelinde",
      run: () => press("apps") },
    { name: "ayarlar", what: "Ayar sayfasını aç", run: () => press("gear") },
    { name: "sifirla", what: "Bağlamı sıkıştır — konuşma kesilmez", run: compactContext },
    // Stopping goes through its own button: opening a second interrupt
    // path means one changes some day and the other stays behind.
    { name: "durdur", what: "Koşan turu durdur", run: () => press("stop") },
    { name: "yardim", what: "Komutlar ve kısayollar", run: showHelp },
  ];

  async function compactContext() {
    const answer = await post("/api/compact");
    if (answer && answer.ok === false) {
      line("alert", answer.error || t("Bağlam sıkıştırılamadı."));
    }
  }

  // `/yardim`: a card drawn from the book itself. A second, hand-kept list
  // would drift away from the book one day.
  function showHelp() {
    // Its own class: the `system` row is styled for a one-line note
    // (nowrap + ellipsis) and makes a multi-line card invisible.
    const card = line("help");
    card.replaceChildren();
    card.append(el("div", "help-head", t("Komutlar")));
    for (const k of BOOK) {
      const row = el("div", "help-row");
      row.append(el("b", null, "/" + k.name));
      row.append(el("span", null, t(k.what)));
      card.append(row);
    }
    card.append(el("div", "help-head", t("Kısayollar")));
    for (const s of ["Enter — gönder · Shift+Enter — alt satır",
                     "/ — komut defteri · @ — dosya işaret et",
                     "Escape — açık kutuyu kapat"]) {
      card.append(el("div", "help-row hint", t(s)));
    }
    scroll();
  }

  // --- state machine ---------------------------------------------------
  //
  // mode: "" (closed) · "komut" (command) · "dosya" (file)
  // at:  position of the trigger character in the text — on selection the
  //      `@query` or `/query` fragment is deleted from exactly here.
  const state = { mode: "", query: "", at: -1, items: [], selected: 0, title: "" };

  // `/` is a command ONLY at the start of a line: a slash mid-sentence
  // (a path, a fraction) must not open the menu.
  const COMMAND_PATTERN = /(?:^|\n)\/([\wğüşıöçĞÜŞİÖÇ.-]*)$/;
  // `@` after whitespace or at line start. Everything without whitespace
  // or a second `@` inside is the query.
  const FILE_PATTERN = /(?:^|\s)@([^\s@]*)$/;

  function check() {
    const caret = input.selectionStart;
    const before = input.value.slice(0, caret);
    let m = COMMAND_PATTERN.exec(before);
    if (m) return openPop("komut", m[1], caret - m[1].length - 1);
    m = FILE_PATTERN.exec(before);
    if (m) return openPop("dosya", m[1], caret - m[1].length - 1);
    closePop();
  }

  function openPop(mode, query, at) {
    const modeChanged = state.mode !== mode;
    state.mode = mode;
    state.query = query;
    state.at = at;
    if (modeChanged) state.selected = 0;
    if (mode === "komut") drawCommands();
    else searchFiles();
  }

  function closePop() {
    state.mode = "";
    state.items = [];
    state.selected = 0;
    pop.hidden = true;
  }

  const isOpen = () => !pop.hidden && state.mode !== "";

  // Keyboard: with the box open, arrow keys navigate, Enter selects,
  // Escape closes. The listener is on the DOCUMENT and in the capture
  // phase: app.js's Enter → send listener sits above the composer and the
  // message must not go out while the box is open.
  function onKey(ev) {
    if (!isOpen() || ev.target !== input) return;
    if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); closePop(); return; }
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      if (!state.items.length) return;
      ev.preventDefault(); ev.stopPropagation();
      const dir = ev.key === "ArrowDown" ? 1 : -1;
      state.selected = (state.selected + dir + state.items.length) % state.items.length;
      draw();
      return;
    }
    if (ev.key === "Enter" || ev.key === "Tab") {
      if (!state.items.length) return;
      ev.preventDefault(); ev.stopPropagation();
      select(state.selected);
    }
  }

  function select(i) {
    const item = state.items[i];
    if (!item) return;
    const mode = state.mode;
    trimTrigger();
    closePop();
    if (mode === "komut") item.run();
    else addMentionPath(item.path);
    input.focus();
  }

  // Removes the trigger fragment from the text: after a selection, a
  // half-typed `/mod` or `@src/a` must not linger in the composer.
  function trimTrigger() {
    if (state.at < 0) return;
    const caret = input.selectionStart;
    input.value = input.value.slice(0, state.at) + input.value.slice(caret);
    input.selectionStart = input.selectionEnd = state.at;
    input.dispatchEvent(new Event("input"));
  }

  // --- drawing ---------------------------------------------------------

  function drawCommands() {
    const want = state.query.toLowerCase();
    state.items = BOOK.filter(k => !want || k.name.includes(want));
    if (state.selected >= state.items.length) state.selected = 0;
    draw(t("Komutlar"));
  }

  // The title is kept in the state: redrawing on arrow keys passes no
  // parameter and the box title ("KOMUTLAR") vanished on every move.
  function draw(title) {
    if (title !== undefined) state.title = title;
    pop.replaceChildren();
    pop.hidden = false;
    if (state.title) pop.append(el("div", "pop-head", state.title));
    if (!state.items.length) {
      pop.append(el("div", "pop-note",
        state.mode === "komut" ? t("Eşleşen komut yok.") : t("Eşleşen dosya yok.")));
    }
    state.items.forEach((item, i) => {
      const row = el("div", "pop-row" + (i === state.selected ? " sel" : ""));
      row.append(el("b", null, state.mode === "komut" ? "/" + item.name : item.name));
      row.append(el("span", null, state.mode === "komut" ? t(item.what) : item.path));
      // Mouse selection goes the same way: no two separate selection logics.
      row.addEventListener("mousedown", (ev) => { ev.preventDefault(); select(i); });
      pop.append(row);
    });
    place();
  }

  function place() {
    const at = input.getBoundingClientRect();
    pop.style.left = Math.max(8, at.left) + "px";
    pop.style.bottom = (window.innerHeight - at.top + 10) + "px";
    pop.style.maxWidth = Math.min(560, window.innerWidth - 24) + "px";
  }

  // --- file search -----------------------------------------------------
  //
  // Not hitting the network on every keystroke: a short delay and a token.
  // A stale answer arriving late must NOT clobber the new query's list —
  // the list jumping back to the previous one while typing happened exactly
  // like that.
  let searchTimer = null;
  let token = 0;

  function searchFiles() {
    clearTimeout(searchTimer);
    const mine = ++token;
    const q = state.query;
    searchTimer = setTimeout(async () => {
      let found = [];
      try {
        const answer = await (await fetch("/api/files/search?q=" + encodeURIComponent(q))).json();
        found = (answer && answer.files) || [];
      } catch { found = []; }
      if (mine !== token || state.mode !== "dosya") return;
      state.items = found;
      if (state.selected >= state.items.length) state.selected = 0;
      draw(t("Dosya ara"));
    }, 110);
    // Do not leave the box empty while waiting.
    if (!state.items.length) {
      pop.replaceChildren(el("div", "pop-head", t("Dosya ara")),
                          el("div", "pop-note dugum-yukleniyor", t("Aranıyor…")));
      pop.hidden = false;
      place();
    }
  }

  // --- mentions --------------------------------------------------------

  let mentions = [];

  function addMentionPath(path) {
    if (!path || mentions.includes(path)) return;
    mentions.push(path);
    drawMentions();
  }

  function drawMentions() {
    chipBox.replaceChildren();
    chipBox.hidden = !mentions.length;
    for (const path of mentions) {
      const chip = el("span", "chip mention");
      chip.append(el("span", "mention-at", "@"));
      chip.append(el("span", "mention-yol", path));
      chip.title = path;
      const x = el("button", null, "×");
      x.type = "button";
      x.title = t("Bahisten çıkar");
      x.onclick = () => { mentions = mentions.filter(p => p !== path); drawMentions(); };
      chip.append(x);
      chipBox.append(chip);
    }
  }

  // The sentence that enters the message. No hidden injection: what is
  // written is exactly what the chip shows, and it stays in the sent text.
  function addHint(text) {
    if (!mentions.length) return text;
    const lines = mentions.map(p => "Kullanıcı şu dosyayı işaret etti: " + p).join("\n");
    mentions = [];
    drawMentions();
    return (text ? text + "\n\n" : "") + lines;
  }

  // --- wiring ----------------------------------------------------------

  input.addEventListener("input", check);
  input.addEventListener("click", check);
  input.addEventListener("keyup", (ev) => {
    if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") check();
  });
  input.addEventListener("blur", () => setTimeout(closePop, 120));
  document.addEventListener("keydown", onKey, true);

  return { BOOK, state, openPop, closePop, onKey, select, isOpen, addHint, hints: () => mentions.slice() };
})();
