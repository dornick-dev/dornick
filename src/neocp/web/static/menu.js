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

  return { ac, kapat };
})();
