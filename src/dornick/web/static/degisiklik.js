// "Bu turda ne değişti" + Keep / Undo / Accept All.
//
// Kaynak: tools/checkpoint.py defteri. Keep yalnızca UI (dosya zaten yazıldı).
// Undo: /api/degisiklikler/geri {sira} veya {n} / {siralar}.

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
  "İkili ya da okunamayan dosya — fark çizilmiyor.":
    "Binary or unreadable file — no diff drawn.",
});

const Degisiklik = (() => {
  let taban = 0;
  let turBasi = 0;

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  async function defter(since) {
    try {
      const yol = "/api/degisiklikler" + (since ? "?since=" + since : "");
      return await (await fetch(yol)).json();
    } catch { return null; }
  }

  async function tabanAl() {
    const veri = await defter(0);
    taban = (veri && veri.son) || 0;
    return taban;
  }

  async function geriIstek(govde) {
    try {
      return await (await fetch("/api/degisiklikler/geri", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(govde),
      })).json();
    } catch { return null; }
  }

  function turBasladi() {
    turBasi = taban;
    tabanAl().then((son) => { turBasi = son; });
  }

  async function turBitti() {
    const veri = await defter(turBasi);
    if (!veri) return;
    taban = veri.son || taban;
    const kayitlar = veri.kayitlar || [];
    turBasi = taban;
    if (!kayitlar.length) return;
    serit(kayitlar);
  }

  function serit(kayitlar) {
    const satir = line("changed");
    satir.replaceChildren();

    const bas = el("button", "chg-head");
    bas.type = "button";
    const say = el("b", null, kayitlar.length + t(" dosya değişti"));
    const aksiyon = el("span", "chg-more", t("göster"));
    bas.append(say, aksiyon);
    satir.append(bas);

    const govde = el("div", "chg-body");
    govde.hidden = true;
    satir.append(govde);

    // En eskiden yeniye (inceleme sırası).
    const sirali = [...kayitlar].sort((a, b) => (a.sira || 0) - (b.sira || 0));
    const durum = new Map(); // sira → kept|undone

    let kurulu = false;
    bas.addEventListener("click", () => {
      govde.hidden = !govde.hidden;
      aksiyon.textContent = govde.hidden ? t("göster") : t("gizle");
      if (!kurulu) {
        kurulu = true;
        govdeKur(govde, sirali, durum, () => {
          const kalan = sirali.filter((k) => !durum.has(k.sira)).length;
          say.textContent = (kalan || sirali.length) + t(" dosya değişti");
          if (!kalan) aksiyon.textContent = t("gizle");
        });
      }
      scroll();
    });
    scroll();
    return satir;
  }

  function govdeKur(govde, kayitlar, durum, onChange) {
    const bar = el("div", "chg-undo");
    bar.append(acceptAllDugmesi(kayitlar, durum, onChange));
    bar.append(geriAlDugmesi(kayitlar, durum, onChange));
    govde.append(bar);
    for (const k of kayitlar) govde.append(dosyaSatiri(k, durum, onChange));
  }

  function acceptAllDugmesi(kayitlar, durum, onChange) {
    const dugme = el("button", "chg-accept-btn", t("hepsini kabul et"));
    dugme.type = "button";
    dugme.addEventListener("click", () => {
      for (const k of kayitlar) {
        if (durum.has(k.sira)) continue;
        durum.set(k.sira, "kept");
        const row = govdeSatir(k.sira);
        if (row) isaretle(row, "kept");
      }
      dugme.disabled = true;
      onChange();
    });
    return dugme;
  }

  function govdeSatir(sira) {
    return document.querySelector('.chg-row[data-sira="' + sira + '"]');
  }

  function isaretle(row, kind) {
    row.classList.remove("kept", "undone");
    row.classList.add(kind);
    const acts = row.querySelector(".chg-row-acts");
    if (acts) acts.replaceChildren(el("span", "chg-tag " + kind,
      kind === "kept" ? t("kabul edildi") : t("geri alındı")));
  }

  function geriAlDugmesi(kayitlar, durum, onChange) {
    const dugme = el("button", "chg-undo-btn", t("bu turu geri al"));
    dugme.type = "button";
    let onay = false;
    let zaman = null;
    dugme.addEventListener("click", async () => {
      const aktif = kayitlar.filter((k) => !durum.has(k.sira) && k.gerialinabilir);
      if (!aktif.length) {
        dugme.disabled = true;
        return;
      }
      if (!onay) {
        onay = true;
        dugme.classList.add("warn");
        dugme.textContent = t("Emin misin? Bir daha tıkla");
        zaman = setTimeout(() => {
          onay = false;
          dugme.classList.remove("warn");
          dugme.textContent = t("bu turu geri al");
        }, 5000);
        return;
      }
      clearTimeout(zaman);
      dugme.disabled = true;
      dugme.textContent = t("Geri alınıyor…");
      const cevap = await geriIstek({ siralar: aktif.map((k) => k.sira) });
      if (!cevap || cevap.ok === false) {
        line("alert", (cevap && cevap.error) || t("Fark okunamadı."));
        dugme.disabled = false;
        dugme.classList.remove("warn");
        dugme.textContent = t("bu turu geri al");
        onay = false;
        return;
      }
      for (const k of aktif) {
        durum.set(k.sira, "undone");
        const row = govdeSatir(k.sira);
        if (row) isaretle(row, "undone");
      }
      dugme.replaceWith(el("span", "chg-undone",
        (cevap.yapilan || []).join("\n") || t("geri alındı")));
      tabanAl();
      onChange();
    });
    return dugme;
  }

  function dosyaSatiri(k, durum, onChange) {
    const satir = el("div", "chg-row");
    satir.dataset.sira = String(k.sira);
    const bas = el("div", "chg-row-head");
    bas.append(el("span", "chg-mark", k.yoktu ? "+" : "~"));
    const ad = el("b", null, k.ad || k.dosya);
    ad.title = k.dosya;
    bas.append(ad);
    bas.append(el("span", "chg-tool", k.arac || ""));
    if (k.yoktu) bas.append(el("span", "chg-tag new", t("yeni dosya")));
    if (!k.gerialinabilir) bas.append(el("span", "chg-tag warn", t("geri alınamaz")));

    const acts = el("div", "chg-row-acts");
    const fark = el("button", "chg-diff-btn", t("farkı gör"));
    fark.type = "button";
    acts.append(fark);

    if (k.gerialinabilir) {
      const keep = el("button", "chg-keep-btn", t("Keep"));
      keep.type = "button";
      keep.addEventListener("click", () => {
        durum.set(k.sira, "kept");
        isaretle(satir, "kept");
        onChange();
      });
      acts.append(keep);

      const undo = el("button", "chg-file-undo", t("Undo"));
      undo.type = "button";
      undo.addEventListener("click", async () => {
        undo.disabled = true;
        const cevap = await geriIstek({ sira: k.sira });
        if (!cevap || cevap.ok === false) {
          line("alert", (cevap && cevap.error) || t("Fark okunamadı."));
          undo.disabled = false;
          return;
        }
        durum.set(k.sira, "undone");
        isaretle(satir, "undone");
        tabanAl();
        onChange();
      });
      acts.append(undo);
    }
    bas.append(acts);
    satir.append(bas);

    const kutu = el("div", "chg-diff");
    kutu.hidden = true;
    satir.append(kutu);

    let yuklendi = false;
    fark.addEventListener("click", async () => {
      kutu.hidden = !kutu.hidden;
      fark.textContent = kutu.hidden ? t("farkı gör") : t("farkı gizle");
      if (yuklendi || kutu.hidden) { scroll(); return; }
      yuklendi = true;
      let veri = null;
      try {
        veri = await (await fetch("/api/degisiklikler/fark?sira=" + k.sira)).json();
      } catch { veri = null; }
      kutu.replaceChildren(farkKutusu(veri));
      scroll();
    });
    return satir;
  }

  function farkKutusu(veri) {
    if (!veri || !veri.ok) {
      return el("div", "diff-empty", (veri && veri.error) || t("Fark okunamadı."));
    }
    if (!veri.metin) {
      return el("div", "diff-empty", t("İkili ya da okunamayan dosya — fark çizilmiyor."));
    }
    return diffHunk(veri.eski, veri.yeni, 1);
  }

  // Kart Keep/Undo — app.js diffBlock çağırır.
  async function kartUndo(sira) {
    if (!sira) return { ok: false, error: "sira yok" };
    const cevap = await geriIstek({ sira });
    if (cevap && cevap.ok) tabanAl();
    return cevap || { ok: false };
  }

  async function kartUndoDosya(dosya) {
    if (!dosya) return { ok: false, error: "dosya yok" };
    const cevap = await geriIstek({ dosya });
    if (cevap && cevap.ok) tabanAl();
    return cevap || { ok: false };
  }

  tabanAl();

  return { turBasladi, turBitti, tabanAl, serit, kartUndo, kartUndoDosya };
})();
