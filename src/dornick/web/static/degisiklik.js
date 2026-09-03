// "What changed this turn" + Keep / Undo / Accept All.
//
// Source: the tools/checkpoint.py ledger. Keep is UI only (the file is
// already written). Undo: /api/degisiklikler/geri {sira} or {n} / {siralar}.

Dil.ekle({
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
  "İkili ya da okunamayan dosya — diffBtn çizilmiyor.":
    "Binary or unreadable file — no diff drawn.",
});

const Degisiklik = (() => {
  let base = 0;
  let turBasi = 0;

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

  async function tabanAl() {
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

  function turBasladi() {
    turBasi = base;
    tabanAl().then((last) => { turBasi = last; });
  }

  async function turBitti() {
    const data = await ledger(turBasi);
    if (!data) return;
    base = data.son || base;
    const kayitlar = data.kayitlar || [];
    turBasi = base;
    if (!kayitlar.length) return;
    serit(kayitlar);
  }

  function serit(kayitlar) {
    const row = line("changed");
    row.replaceChildren();

    const head = el("button", "chg-head");
    head.type = "button";
    const countEl = el("b", null, kayitlar.length + t(" dosya değişti"));
    const action = el("span", "chg-more", t("göster"));
    head.append(countEl, action);
    row.append(head);

    const body = el("div", "chg-body");
    body.hidden = true;
    row.append(body);

    // Oldest to newest (review order).
    const ordered = [...kayitlar].sort((a, b) => (a.sira || 0) - (b.sira || 0));
    const durum = new Map(); // sira → kept|undone

    let built = false;
    head.addEventListener("click", () => {
      body.hidden = !body.hidden;
      action.textContent = body.hidden ? t("göster") : t("gizle");
      if (!built) {
        built = true;
        buildBody(body, ordered, durum, () => {
          const remaining = ordered.filter((k) => !durum.has(k.sira)).length;
          countEl.textContent = (remaining || ordered.length) + t(" dosya değişti");
          if (!remaining) action.textContent = t("gizle");
        });
      }
      scroll();
    });
    scroll();
    return row;
  }

  function buildBody(body, kayitlar, durum, onChange) {
    const bar = el("div", "chg-undo");
    bar.append(acceptAllButton(kayitlar, durum, onChange));
    bar.append(geriAlDugmesi(kayitlar, durum, onChange));
    body.append(bar);
    for (const k of kayitlar) body.append(fileRow(k, durum, onChange));
  }

  function acceptAllButton(kayitlar, durum, onChange) {
    const btn = el("button", "chg-accept-btn", t("hepsini kabul et"));
    btn.type = "button";
    btn.addEventListener("click", () => {
      for (const k of kayitlar) {
        if (durum.has(k.sira)) continue;
        durum.set(k.sira, "kept");
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

  function geriAlDugmesi(kayitlar, durum, onChange) {
    const btn = el("button", "chg-undo-btn", t("bu turu geri al"));
    btn.type = "button";
    let onay = false;
    let timer = null;
    btn.addEventListener("click", async () => {
      const active = kayitlar.filter((k) => !durum.has(k.sira) && k.gerialinabilir);
      if (!active.length) {
        btn.disabled = true;
        return;
      }
      if (!onay) {
        onay = true;
        btn.classList.add("warn");
        btn.textContent = t("Emin misin? Bir daha tıkla");
        timer = setTimeout(() => {
          onay = false;
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
        onay = false;
        return;
      }
      for (const k of active) {
        durum.set(k.sira, "undone");
        const row = rowFor(k.sira);
        if (row) mark(row, "undone");
      }
      btn.replaceWith(el("span", "chg-undone",
        (answer.yapilan || []).join("\n") || t("geri alındı")));
      tabanAl();
      onChange();
    });
    return btn;
  }

  function fileRow(k, durum, onChange) {
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
        durum.set(k.sira, "kept");
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
        durum.set(k.sira, "undone");
        mark(row, "undone");
        tabanAl();
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

  function diffBox(veri) {
    if (!veri || !veri.ok) {
      return el("div", "diff-empty", (veri && veri.error) || t("Fark okunamadı."));
    }
    if (!veri.metin) {
      return el("div", "diff-empty", t("İkili ya da okunamayan dosya — diffBtn çizilmiyor."));
    }
    return diffHunk(veri.eski, veri.yeni, 1);
  }

  // Card Keep/Undo — called by app.js diffBlock.
  async function kartUndo(sira) {
    if (!sira) return { ok: false, error: "sira yok" };
    const answer = await undoRequest({ sira });
    if (answer && answer.ok) tabanAl();
    return answer || { ok: false };
  }

  async function kartUndoDosya(dosya) {
    if (!dosya) return { ok: false, error: "dosya yok" };
    const answer = await undoRequest({ dosya });
    if (answer && answer.ok) tabanAl();
    return answer || { ok: false };
  }

  tabanAl();

  return { turBasladi, turBitti, tabanAl, serit, kartUndo, kartUndoDosya };
})();
