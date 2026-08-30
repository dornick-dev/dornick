// Ayrı kamera penceresi — ana Neo sohbet/beyin olarak kalır.
// En az bir canlı kamera yoksa boş durum; sahne açılmaz (ana penceredeki
// `aktifVar` kuralının kardeşi).

const Watch = (() => {
  Dil.ekle({
    "Bilgisayar kamerası": "Computer camera",
    "Aktif kamera yok": "No live camera",
    "sil": "remove",
  });

  const live = document.getElementById("watch-live");
  const empty = document.getElementById("watch-empty");
  const strip = document.getElementById("watch-strip");
  const titleEl = document.getElementById("watch-title");
  const sightEl = document.getElementById("watch-sight");
  let cams = [];
  let acikMi = false;
  let secili = "usb";
  let timer = null;
  const q = new URLSearchParams(location.search);
  if (q.get("cam")) secili = q.get("cam");

  function usb0(c) {
    const src = String(c.source || "0");
    return src === "0" && (!c.kind || c.kind === "usb");
  }

  function aktifVar() {
    return !!(acikMi || cams.some((c) => !usb0(c) && c.enabled));
  }

  function adlar() {
    const dahili = cams.find(usb0);
    const extras = cams.filter((c) => !usb0(c));
    const rows = [];
    if (acikMi || dahili) {
      rows.push({
        key: "usb",
        ad: (dahili && dahili.name) || t("Bilgisayar kamerası"),
        q: dahili ? "id=" + encodeURIComponent(dahili.id) : "source=0",
        analyze: dahili ? dahili.analyze !== false : true,
      });
    }
    for (const c of extras) {
      if (!c.enabled && !acikMi) continue;
      rows.push({
        key: c.id,
        ad: c.name,
        q: "id=" + encodeURIComponent(c.id),
        analyze: c.analyze !== false,
      });
    }
    return rows;
  }

  function secilen() {
    const rows = adlar();
    return rows.find((w) => w.key === secili) || rows[0];
  }

  async function kareYukle(img, query, boxes) {
    if (!img) return "";
    try {
      const r = await fetch(
        "/api/camera/frame?" + query + (boxes ? "&boxes=1" : "") + "&t=" + Date.now());
      if (!r.ok) {
        img.classList.add("dead");
        return "";
      }
      const raw = r.headers.get("X-Neo-Sight") || "";
      let seen = "";
      try { seen = decodeURIComponent(raw); } catch { seen = raw; }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const old = img.dataset.blob;
      img.src = url;
      img.dataset.blob = url;
      img.classList.remove("dead");
      if (old) URL.revokeObjectURL(old);
      return seen;
    } catch {
      if (img) img.classList.add("dead");
      return "";
    }
  }

  function serit() {
    if (!strip) return;
    const want = adlar();
    strip.replaceChildren();
    want.forEach((w) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cam-thumb" + (w.key === secili ? " on" : "");
      const img = document.createElement("img");
      img.alt = w.ad;
      img.dataset.q = w.q;
      img.dataset.key = w.key;
      const cap = document.createElement("span");
      cap.textContent = w.ad;
      btn.append(img, cap);
      btn.onclick = () => { secili = w.key; ciz(); };
      strip.append(btn);
    });
  }

  function ciz() {
    const bos = !aktifVar();
    if (empty) empty.hidden = !bos;
    if (live) live.hidden = bos;
    if (bos) {
      if (titleEl) titleEl.textContent = t("Aktif kamera yok");
      if (sightEl) sightEl.textContent = "";
      clearInterval(timer);
      return;
    }
    const w = secilen();
    if (titleEl) titleEl.textContent = w ? w.ad : t("Bilgisayar kamerası");
    if (live) live.alt = w ? w.ad : "";
    document.title = "neo · " + (w ? w.ad : t("Kamera"));
    serit();
    tazele();
  }

  function tazele() {
    clearInterval(timer);
    if (document.hidden || !aktifVar()) return;
    const tick = async () => {
      if (document.hidden || !aktifVar()) return;
      const w = secilen();
      if (!w || !live) return;
      const seen = await kareYukle(live, w.q, w.analyze !== false);
      if (seen && sightEl) sightEl.textContent = seen;
      for (const img of strip.querySelectorAll("img")) {
        if (img.dataset.key === secili) continue;
        kareYukle(img, img.dataset.q, false);
      }
    };
    tick();
    timer = setInterval(tick, 450);
  }

  async function yukle() {
    try {
      const d = await (await fetch("/api/cameras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "list" }),
      })).json();
      acikMi = !!d.enabled && d.live === true;
      cams = d.cameras || [];
    } catch { acikMi = false; cams = []; }
    ciz();
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearInterval(timer);
    else if (aktifVar()) tazele();
  });
  yukle();
  setInterval(yukle, 4000);
})();
