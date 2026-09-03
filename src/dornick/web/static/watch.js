// Separate camera window — the main Dornick stays as chat/brain.
// With no live camera at all: empty state; the stage does not open (sibling of
// the `aktifVar` rule in the main window).

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
  let isOpen = false;
  let selected = "usb";
  let timer = null;
  const q = new URLSearchParams(location.search);
  if (q.get("cam")) selected = q.get("cam");

  function usb0(c) {
    const src = String(c.source || "0");
    return src === "0" && (!c.kind || c.kind === "usb");
  }

  function imgKey(img) {
    return img && img.dataset ? img.dataset.key : "";
  }

  function aktifVar() {
    return !!(isOpen || cams.some((c) => !usb0(c) && c.enabled));
  }

  function rowsFor() {
    const builtin = cams.find(usb0);
    const extras = cams.filter((c) => !usb0(c));
    const rows = [];
    if (isOpen || builtin) {
      rows.push({
        key: "usb",
        name: (builtin && builtin.name) || t("Bilgisayar kamerası"),
        q: builtin ? "id=" + encodeURIComponent(builtin.id) : "source=0",
        analyze: builtin ? builtin.analyze !== false : true,
      });
    }
    for (const c of extras) {
      if (!c.enabled && !isOpen) continue;
      rows.push({
        key: c.id,
        name: c.name,
        q: "id=" + encodeURIComponent(c.id),
        analyze: c.analyze !== false,
      });
    }
    return rows;
  }

  function selectedRow() {
    const rows = rowsFor();
    return rows.find((w) => w.key === selected) || rows[0];
  }

  async function loadFrame(img, query, boxes, follow) {
    if (!img) return "";
    try {
      const r = await fetch(
        "/api/camera/frame?" + query + (boxes ? "&boxes=1" : "") + "&t=" + Date.now());
      if (!r.ok) {
        img.classList.add("dead");
        return "";
      }
      const raw = r.headers.get("X-Dornick-Sight") || "";
      let seen = "";
      try { seen = decodeURIComponent(raw); } catch { seen = raw; }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const old = img.dataset.blob;
      img.src = url;
      img.dataset.blob = url;
      img.classList.remove("dead");
      if (follow) {
        follow.src = url;
        follow.classList.remove("dead");
      }
      if (old) URL.revokeObjectURL(old);
      return seen;
    } catch {
      if (img) img.classList.add("dead");
      return "";
    }
  }

  function paintStrip() {
    if (!strip) return;
    const want = rowsFor();
    const existing = [...strip.querySelectorAll(".cam-thumb")];
    if (existing.length === want.length
        && want.every((w, i) => existing[i] && existing[i].dataset.key === w.key)) {
      want.forEach((w, i) => {
        existing[i].classList.toggle("on", w.key === selected);
        const cap = existing[i].querySelector("span");
        if (cap) cap.textContent = w.name;
      });
      return;
    }
    strip.replaceChildren();
    want.forEach((w) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cam-thumb" + (w.key === selected ? " on" : "");
      btn.dataset.key = w.key;
      const img = document.createElement("img");
      img.alt = "";
      img.dataset.q = w.q;
      img.dataset.key = w.key;
      const cap = document.createElement("span");
      cap.textContent = w.name;
      btn.append(img, cap);
      btn.onclick = () => { selected = w.key; paint(); };
      strip.append(btn);
    });
  }

  function paint() {
    const blank = !aktifVar();
    if (empty) empty.hidden = !blank;
    if (live) live.hidden = blank;
    if (blank) {
      if (titleEl) titleEl.textContent = t("Aktif kamera yok");
      if (sightEl) sightEl.textContent = "";
      clearInterval(timer);
      return;
    }
    const w = selectedRow();
    if (titleEl) titleEl.textContent = w ? w.name : t("Bilgisayar kamerası");
    if (live) live.alt = w ? w.name : "";
    document.title = "Dornick · " + (w ? w.name : t("Kamera"));
    paintStrip();
    refresh();
  }

  function refresh() {
    clearInterval(timer);
    if (document.hidden || !aktifVar()) return;
    const tick = async () => {
      if (document.hidden || !aktifVar()) return;
      const w = selectedRow();
      if (!w || !live) return;
      const thumb = strip && [...strip.querySelectorAll("img")]
        .find((el) => imgKey(el) === w.key);
      const seen = await loadFrame(live, w.q, w.analyze !== false, thumb);
      if (seen && sightEl) sightEl.textContent = seen;
      for (const img of strip.querySelectorAll("img")) {
        if (imgKey(img) === w.key) continue;
        loadFrame(img, img.dataset.q, false);
      }
    };
    tick();
    timer = setInterval(tick, 450);
  }

  async function load() {
    try {
      const d = await (await fetch("/api/cameras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "list" }),
      })).json();
      isOpen = !!d.enabled && d.live === true;
      cams = d.cameras || [];
    } catch { isOpen = false; cams = []; }
    paint();
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearInterval(timer);
    else if (aktifVar()) refresh();
  });
  load();
  setInterval(load, 4000);
})();
