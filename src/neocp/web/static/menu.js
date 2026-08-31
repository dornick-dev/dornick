// Ortak sağ tık menüsü. Liste satırları (sohbet, görev, uygulama, git)
// tarayıcının kendi menüsü yerine buradan işlem görür: arşiv, sil, aç.
//
// Madde adı DOM'da textContent ile kuruluyor; işaretleme dizesi yok.

const Menu = (() => {
  let kutu = null;
  let kapatFn = null;

  function kapat() {
    if (kutu) kutu.remove();
    kutu = null;
    if (kapatFn) {
      document.removeEventListener("mousedown", kapatFn, true);
      document.removeEventListener("keydown", kapatFn, true);
      window.removeEventListener("blur", kapatFn);
      kapatFn = null;
    }
  }

  function ac(ev, maddeler) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
    }
    kapat();
    const liste = (maddeler || []).filter(Boolean);
    if (!liste.length) return;

    const box = document.createElement("div");
    box.className = "ctx-menu";
    box.setAttribute("role", "menu");

    for (const m of liste) {
      if (m.ayrac) {
        const cizgi = document.createElement("div");
        cizgi.className = "ctx-sep";
        cizgi.setAttribute("role", "separator");
        box.append(cizgi);
        continue;
      }
      const btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("role", "menuitem");
      btn.className = "ctx-item" + (m.risk ? " risk" : "");
      btn.textContent = t(m.ad);
      if (m.ipucu) btn.title = t(m.ipucu);
      if (m.kapali) {
        btn.disabled = true;
        btn.classList.add("off");
      }
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        kapat();
        if (typeof m.is === "function") m.is();
      });
      box.append(btn);
    }

    document.body.append(box);
    box.addEventListener("contextmenu", (e) => e.preventDefault());
    const pad = 8;
    const w = box.offsetWidth;
    const h = box.offsetHeight;
    let x = ev && ev.clientX != null ? ev.clientX : pad;
    let y = ev && ev.clientY != null ? ev.clientY : pad;
    if (x + w > innerWidth - pad) x = Math.max(pad, innerWidth - w - pad);
    if (y + h > innerHeight - pad) y = Math.max(pad, innerHeight - h - pad);
    box.style.left = x + "px";
    box.style.top = y + "px";
    kutu = box;

    kapatFn = (e) => {
      if (e.type === "keydown" && e.key !== "Escape") return;
      if (e.type === "mousedown" && box.contains(e.target)) return;
      kapat();
    };
    document.addEventListener("mousedown", kapatFn, true);
    document.addEventListener("keydown", kapatFn, true);
    window.addEventListener("blur", kapatFn);
  }

  // --- pano menüsü ------------------------------------------------------
  //
  // WebView2'nin varsayılan sağ tık menüsünü pywebview ÜRETİMDE kapatıyor
  // (yalnız debug'da açık): kopyala/yapıştır menüsüz kalıyordu (natif tur,
  // 31.08). Pano erişimi pywebview köprüsünden (pano_oku/pano_yaz) —
  // tarayıcı izin kapısına takılmaz; köprü yoksa (tarayıcı önizleme)
  // navigator.clipboard'a düşer.

  function panoYaz(metin) {
    try {
      if (window.pywebview && window.pywebview.api.pano_yaz) {
        window.pywebview.api.pano_yaz(String(metin));
        return;
      }
    } catch { /* köprü yok */ }
    try { navigator.clipboard.writeText(String(metin)); } catch { /* izin yok */ }
  }

  async function panoOku() {
    try {
      if (window.pywebview && window.pywebview.api.pano_oku) {
        return String(await window.pywebview.api.pano_oku() || "");
      }
    } catch { /* köprü yok */ }
    try { return String(await navigator.clipboard.readText() || ""); }
    catch { return ""; }
  }

  function alanaEkle(hedef, metin) {
    hedef.focus();
    const b = hedef.selectionStart ?? hedef.value.length;
    const e = hedef.selectionEnd ?? b;
    hedef.value = hedef.value.slice(0, b) + metin + hedef.value.slice(e);
    hedef.selectionStart = hedef.selectionEnd = b + metin.length;
    hedef.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function secimiSil(hedef) {
    const b = hedef.selectionStart ?? 0, e = hedef.selectionEnd ?? 0;
    hedef.value = hedef.value.slice(0, b) + hedef.value.slice(e);
    hedef.selectionStart = hedef.selectionEnd = b;
    hedef.dispatchEvent(new Event("input", { bubbles: true }));
  }

  document.addEventListener("contextmenu", (ev) => {
    // Kendi menüsü olan satırlar (sohbet listesi vb.) kendi yollarını
    // kullanıyor; onlar stopPropagation ile buraya hiç düşmez.
    const hedef = ev.target.closest("input, textarea");
    const yazilabilir = hedef && !hedef.readOnly && !hedef.disabled
      && hedef.type !== "checkbox" && hedef.type !== "radio";
    const secim = String(window.getSelection() || "");
    const alanSecimi = yazilabilir
      ? String(hedef.value || "").slice(hedef.selectionStart ?? 0, hedef.selectionEnd ?? 0)
      : "";
    const kopyalanacak = alanSecimi || secim;
    if (!yazilabilir && !kopyalanacak) return;   // menülük bir şey yok
    const maddeler = [];
    if (kopyalanacak) {
      maddeler.push({ ad: "Kopyala", is: () => panoYaz(kopyalanacak) });
    }
    if (yazilabilir && alanSecimi) {
      maddeler.push({ ad: "Kes", is: () => { panoYaz(alanSecimi); secimiSil(hedef); } });
    }
    if (yazilabilir) {
      maddeler.push({ ad: "Yapıştır",
                      is: () => { panoOku().then((m) => { if (m) alanaEkle(hedef, m); }); } });
      maddeler.push({ ad: "Tümünü seç",
                      is: () => { hedef.focus(); hedef.select && hedef.select(); } });
    }
    ac(ev, maddeler);
  });

  return { ac, kapat };
})();
