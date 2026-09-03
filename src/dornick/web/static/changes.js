// "What changed this turn" + Keep / Undo / Accept All.
//
// Source: the tools/checkpoint.py ledger. Keep is UI only (the file is
// already written). Undo: /api/degisiklikler/geri {sira} or {n} / {siralar}.

Lang.add({
  " dosya değişti": " file(s) changed",
  "göster": "show",
  "gizle": "hide",
  "farkı gör": "see the diff",
  "farkı gizle": "hide the diff",
  "bu turu geri al": "undo this turn",
  "hepsini kabul et": "accept all",
  "Keep": "Keep",
  "Undo": "Undo",
  "Emin misin? Bir daha tıkla": "Sure? Click again",
  "Geri alınıyor…": "Undoing…",
  "yeni dosya": "new file",
  "geri alınamaz": "cannot be undone",
  "kabul edildi": "accepted",
  "geri alındı": "undone",
  "Fark okunamadı.": "Could not read the diff.",
  "İkili ya da okunamayan dosya — fark çizilmiyor.":
    "Binary or unreadable file — no diff drawn.",
});

const Changes = (() => {
  let base = 0;
  let turnBase = 0;

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  async function ledger(since) {
    try {
      const url = "/api/degisiklikler" + (since ? "?since=" + since : "");
      return await (await fetch(url)).json();
    } catch { return null; }
  }

  async function takeBase() {
    const data = await ledger(0);
    base = (data && data.son) || 0;
    return base;
  }

  async function undoRequest(body) {
    try {
      return await (await fetch("/api/degisiklikler/geri", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })).json();
    } catch { return null; }
  }

  function turnStarted() {
    turnBase = base;
    takeBase().then((last) => { turnBase = last; });
  }

  async function turnEnded() {
    const data = await ledger(turnBase);
    if (!data) return;
    base = data.son || base;
    const records = data.kayitlar || [];
    turnBase = base;
    if (!records.length) return;
    strip(records);
  }

  function strip(records) {
    const row = line("changed");
    row.replaceChildren();

    const head = el("button", "chg-head");
    head.type = "button";
    const countEl = el("b", null, records.length + t(" dosya değişti"));
    const action = el("span", "chg-more", t("göster"));
    head.append(countEl, action);
    row.append(head);

    const body = el("div", "chg-body");
    body.hidden = true;
    row.append(body);

    // Oldest to newest (review order).
    const ordered = [...records].sort((a, b) => (a.sira || 0) - (b.sira || 0));
    const states = new Map(); // sira → kept|undone

    let built = false;
    head.addEventListener("click", () => {
      body.hidden = !body.hidden;
      action.textContent = body.hidden ? t("göster") : t("gizle");
      if (!built) {
        built = true;
        buildBody(body, ordered, states, () => {
          const remaining = ordered.filter((k) => !states.has(k.sira)).length;
          countEl.textContent = (remaining || ordered.length) + t(" dosya değişti");
          if (!remaining) action.textContent = t("gizle");
        });
      }
      scroll();
    });
    scroll();
    return row;
  }

  function buildBody(body, records, states, onChange) {
    const bar = el("div", "chg-undo");
    bar.append(acceptAllButton(records, states, onChange));
    bar.append(undoButton(records, states, onChange));
    body.append(bar);
    for (const k of records) body.append(fileRow(k, states, onChange));
  }

  function acceptAllButton(records, states, onChange) {
    const btn = el("button", "chg-accept-btn", t("hepsini kabul et"));
    btn.type = "button";
    btn.addEventListener("click", () => {
      for (const k of records) {
        if (states.has(k.sira)) continue;
        states.set(k.sira, "kept");
        const row = rowFor(k.sira);
        if (row) mark(row, "kept");
      }
      btn.disabled = true;
      onChange();
    });
    return btn;
  }

  function rowFor(sira) {
    return document.querySelector('.chg-row[data-sira="' + sira + '"]');
  }

  function mark(row, kind) {
    row.classList.remove("kept", "undone");
    row.classList.add(kind);
    const acts = row.querySelector(".chg-row-acts");
    if (acts) acts.replaceChildren(el("span", "chg-tag " + kind,
      kind === "kept" ? t("kabul edildi") : t("geri alındı")));
  }

  function undoButton(records, states, onChange) {
    const btn = el("button", "chg-undo-btn", t("bu turu geri al"));
    btn.type = "button";
    let confirmed = false;
    let timer = null;
    btn.addEventListener("click", async () => {
      const active = records.filter((k) => !states.has(k.sira) && k.gerialinabilir);
      if (!active.length) {
        btn.disabled = true;
        return;
      }
      if (!confirmed) {
        confirmed = true;
        btn.classList.add("warn");
        btn.textContent = t("Emin misin? Bir daha tıkla");
        timer = setTimeout(() => {
          confirmed = false;
          btn.classList.remove("warn");
          btn.textContent = t("bu turu geri al");
        }, 5000);
        return;
      }
      clearTimeout(timer);
      btn.disabled = true;
      btn.textContent = t("Geri alınıyor…");
      const answer = await undoRequest({ siralar: active.map((k) => k.sira) });
      if (!answer || answer.ok === false) {
        line("alert", (answer && answer.error) || t("Fark okunamadı."));
        btn.disabled = false;
        btn.classList.remove("warn");
        btn.textContent = t("bu turu geri al");
        confirmed = false;
        return;
      }
      for (const k of active) {
        states.set(k.sira, "undone");
        const row = rowFor(k.sira);
        if (row) mark(row, "undone");
      }
      btn.replaceWith(el("span", "chg-undone",
        (answer.yapilan || []).join("\n") || t("geri alındı")));
      takeBase();
      onChange();
    });
    return btn;
  }

  function fileRow(k, states, onChange) {
    const row = el("div", "chg-row");
    row.dataset.sira = String(k.sira);
    const head = el("div", "chg-row-head");
    head.append(el("span", "chg-mark", k.yoktu ? "+" : "~"));
    const nameEl = el("b", null, k.ad || k.dosya);
    nameEl.title = k.dosya;
    head.append(nameEl);
    head.append(el("span", "chg-tool", k.arac || ""));
    if (k.yoktu) head.append(el("span", "chg-tag new", t("yeni dosya")));
    if (!k.gerialinabilir) head.append(el("span", "chg-tag warn", t("geri alınamaz")));

    const acts = el("div", "chg-row-acts");
    const diffBtn = el("button", "chg-diff-btn", t("farkı gör"));
    diffBtn.type = "button";
    acts.append(diffBtn);

    if (k.gerialinabilir) {
      const keep = el("button", "chg-keep-btn", t("Keep"));
      keep.type = "button";
      keep.addEventListener("click", () => {
        states.set(k.sira, "kept");
        mark(row, "kept");
        onChange();
      });
      acts.append(keep);

      const undo = el("button", "chg-file-undo", t("Undo"));
      undo.type = "button";
      undo.addEventListener("click", async () => {
        undo.disabled = true;
        const answer = await undoRequest({ sira: k.sira });
        if (!answer || answer.ok === false) {
          line("alert", (answer && answer.error) || t("Fark okunamadı."));
          undo.disabled = false;
          return;
        }
        states.set(k.sira, "undone");
        mark(row, "undone");
        takeBase();
        onChange();
      });
      acts.append(undo);
    }
    head.append(acts);
    row.append(head);

    const box = el("div", "chg-diff");
    box.hidden = true;
    row.append(box);

    let loaded = false;
    diffBtn.addEventListener("click", async () => {
      box.hidden = !box.hidden;
      diffBtn.textContent = box.hidden ? t("farkı gör") : t("farkı gizle");
      if (loaded || box.hidden) { scroll(); return; }
      loaded = true;
      let data = null;
      try {
        data = await (await fetch("/api/degisiklikler/fark?sira=" + k.sira)).json();
      } catch { data = null; }
      box.replaceChildren(diffBox(data));
      scroll();
    });
    return row;
  }

  function diffBox(data) {
    if (!data || !data.ok) {
      return el("div", "diff-empty", (data && data.error) || t("Fark okunamadı."));
    }
    if (!data.metin) {
      return el("div", "diff-empty", t("İkili ya da okunamayan dosya — fark çizilmiyor."));
    }
    return diffHunk(data.eski, data.yeni, 1);
  }

  // Card Keep/Undo — called by app.js diffBlock.
  async function cardUndo(sira) {
    if (!sira) return { ok: false, error: "sira yok" };
    const answer = await undoRequest({ sira });
    if (answer && answer.ok) takeBase();
    return answer || { ok: false };
  }

  async function cardUndoFile(dosya) {
    if (!dosya) return { ok: false, error: "dosya yok" };
    const answer = await undoRequest({ dosya });
    if (answer && answer.ok) takeBase();
    return answer || { ok: false };
  }

  takeBase();

  return { turnStarted, turnEnded, takeBase, strip, cardUndo, cardUndoFile };
})();
