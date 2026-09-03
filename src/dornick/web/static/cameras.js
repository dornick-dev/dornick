// Camera — watching always happens in a separate OS window (`watch.html`).
// The main Dornick stays as chat/brain; browser fullscreen is never applied
// to the main document (Dornick would vanish). Settings live under
// Settings › Cameras. GPU boxes are drawn onto the JPEG on the server
// (`?boxes=1`).

const Cameras = (() => {
  Lang.add({
    "Kameralar": "Cameras",
    "Bilgisayar kamerası": "Computer camera",
    "dahili kamera": "built-in camera",
    "kare alınamadı": "no frame",
    "izle": "watch",
    "sil": "remove",
    "Ekle": "Add",
    "GPU tanıma": "GPU detect",
    "opencv kurulu değil": "opencv not installed",
    "opencv kurulu değil — kurulumda kamera bileşenini seç":
      "opencv is not installed — pick the camera component in setup",
    "GPU yok — sorulunca kesit": "No GPU — snapshot on ask",
    "Kamera": "Camera",
    "Bu kareye bak": "Look at this frame",
    "Yeni pencerede": "New window",
    "Tam ekran": "Full screen",
    "Beyne dön": "Back to brain",
    "Kamerada ne görüyorsun? Sesli veya yazılı sor…":
      "What's on camera? Ask by voice or text…",
    "Konuş…": "Talk…",
  });

  Lang.add({
    "Kamerayı aç": "Turn camera on",
    "Kamerayı kapat": "Turn camera off",
    "Ayarları aç": "Open settings",
    "Kamera kapalı — tıkla: aç": "Camera off — click to turn on",
    "Kamera açık — tıkla: pencerede izle": "Camera on — click: watch in a window",
    "Kamera açık — tıkla: kapat": "Camera on — click to turn off",
    "Aktif kamera yok — önce bir kamera aç":
      "No live camera — turn one on first",
    "Kamera açık — tıkla: kapat": "Camera on — click to turn off",
    "Kamera açık": "Camera on",
    "Kamera kapandı": "Camera off",
    "Kamera açılamadı": "Could not open the camera",
    "GPU analiz ediyor": "GPU analyzing",
    "GPU hazır": "GPU ready",
    "kare yerelde okunuyor, sohbet modeline metin gidiyor":
      "the frame is read locally; the chat model gets text",
    "analiz henüz yüklenmedi; şimdilik LLM kesitle bakıyor":
      "analysis not loaded yet; for now the LLM looks via snapshots",
    "GPU yok — LLM sorulduğunda kesitle bakar":
      "No GPU — the LLM looks via snapshots on demand",
  });

  const deck = document.getElementById("cam-deck");
  const layer = document.getElementById("cam-layer");
  const live = document.getElementById("cam-live");
  const strip = document.getElementById("cam-strip");
  const sightEl = document.getElementById("cam-stage-sight");
  const titleEl = document.getElementById("cam-stage-title");
  const spec = document.getElementById("cam-spec");
  const icon = document.getElementById("cams");
  const pop = document.getElementById("cam-pop");
  let timer = null;
  let cams = [];
  let ready = true;
  let isOpen = false;
  let mode = "kesit";
  let gpuName = "";
  let selected = "usb";
  let summary = "";
  let liveUrl = "";
  const thumbUrls = new Map();

  function refreshIcon() {
    icon.classList.toggle("cam-off", !anyActive());
    icon.classList.toggle("cam-on", anyActive());
    icon.classList.toggle("on", anyActive());
    icon.setAttribute("aria-pressed", isOpen ? "true" : "false");
    icon.title = anyActive()
      ? t("Kamera açık — tıkla: pencerede izle")
      : t("Kamera kapalı — tıkla: aç");
  }

  function stageOpen() {
    return !!(deck && !deck.hidden);
  }

  function usb0(c) {
    const src = String(c.source || "0");
    return src === "0" && (!c.kind || c.kind === "usb");
  }

  function netLive() {
    return cams.some((c) => !usb0(c) && c.enabled);
  }

  function anyActive() {
    return !!(isOpen || netLive());
  }

  function rowsFor() {
    const builtin = cams.find(usb0);
    const extras = cams.filter((c) => !usb0(c));
    return [
      {
        key: "usb",
        name: (builtin && builtin.name) || t("Bilgisayar kamerası"),
        q: builtin ? "id=" + encodeURIComponent(builtin.id) : "source=0",
        id: builtin ? builtin.id : "",
        watched: !!(builtin && builtin.enabled),
        analyze: builtin ? builtin.analyze !== false : true,
      },
      ...extras.map((c) => ({
        key: c.id,
        name: c.name,
        q: "id=" + encodeURIComponent(c.id),
        id: c.id,
        watched: !!c.enabled,
        analyze: c.analyze !== false,
      })),
    ];
  }

  function selectedRow() {
    return rowsFor().find((w) => w.key === selected) || rowsFor()[0];
  }

  async function load(opts) {
    const redraw = !!(opts && opts.redraw);
    let d = null;
    try {
      d = await (await fetch("/api/cameras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "list" }),
      })).json();
    } catch { return; }
    ready = !!d.available;
    isOpen = !!d.enabled && (d.live !== false);
    mode = d.vision_mode || "kesit";
    cams = d.cameras || [];
    const gpu = (d.gpus || [])[0];
    gpuName = gpu ? gpu.name + " · " + Math.round(gpu.total_mb / 1024) + " GB" : "";
    const shortLabel = !ready
      ? t("opencv kurulu değil")
      : mode === "gpu"
        ? t("GPU analiz ediyor") + (gpuName ? " · " + gpuName : "")
      : mode === "izleme" && gpu
        ? t("GPU hazır") + (gpuName ? " · " + gpuName : "")
        : t("GPU yok — sorulunca kesit");
    if (spec) {
      spec.textContent = shortLabel;
      spec.title = !ready
        ? t("opencv kurulu değil — kurulumda kamera bileşenini seç")
        : mode === "gpu"
          ? t("GPU analiz ediyor") + ": " + gpuName + " — "
            + t("kare yerelde okunuyor, sohbet modeline metin gidiyor")
        : mode === "izleme" && gpu
          ? t("GPU hazır") + ": " + gpuName + " — "
            + ((d.sight && d.sight.reason)
                ? d.sight.reason
                : t("analiz henüz yüklenmedi; şimdilik LLM kesitle bakıyor"))
          : t("GPU yok — LLM sorulduğunda kesitle bakar");
    }
    const lab = document.getElementById("cam-gpu-lab");
    const box = document.getElementById("cam-analyze");
    if (lab && box) {
      const hasGpu = mode === "gpu" || mode === "izleme";
      lab.hidden = !hasGpu;
      if (hasGpu) box.checked = true;
    }
    refreshIcon();
    if (!anyActive() && stageOpen()) close();
    if (redraw && stageOpen()) paint();
    const sight = d.sight || {};
    if (mode === "izleme" && !sight.ready
        && (!sight.tried || sight.reason === "yükleniyor")) {
      setTimeout(() => load({ redraw: false }), 2500);
    }
  }

  function paintStrip() {
    if (!strip) return;
    const want = rowsFor();
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
      btn.onclick = () => {
        selected = w.key;
        paint();
      };
      if (w.id && w.key !== "usb") {
        const removeBtn = document.createElement("i");
        removeBtn.textContent = "×";
        removeBtn.title = t("sil");
        removeBtn.onclick = async (ev) => {
          ev.stopPropagation();
          await fetch("/api/cameras", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "remove", id: w.id }),
          });
          if (selected === w.key) selected = "usb";
          load({ redraw: true });
        };
        btn.append(removeBtn);
      }
      strip.append(btn);
    });
  }

  function paint() {
    if (!ready || !stageOpen()) return;
    const w = selectedRow();
    if (titleEl) titleEl.textContent = w ? w.name : t("Bilgisayar kamerası");
    if (live) live.alt = w ? w.name : "";
    paintStrip();
    refresh();
  }

  async function loadFrame(img, q, boxes, follow) {
    if (!img) return "";
    try {
      const r = await fetch(
        "/api/camera/frame?" + q + (boxes ? "&boxes=1" : "") + "&t=" + Date.now());
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
      img.onload = () => { img.classList.remove("dead"); };
      img.onerror = () => { img.classList.add("dead"); };
      img.src = url;
      img.dataset.blob = url;
      if (follow) {
        follow.src = url;
        follow.classList.remove("dead");
      }
      if (old) URL.revokeObjectURL(old);
      return seen;
    } catch {
      img.classList.add("dead");
      return "";
    }
  }

  function refresh() {
    clearInterval(timer);
    if (!stageOpen() || document.hidden || !ready) return;
    const tick = async () => {
      if (!stageOpen() || document.hidden) return;
      const w = selectedRow();
      if (!w || !live) return;
      const thumb = strip && [...strip.querySelectorAll("img")]
        .find((el) => el.dataset.key === w.key);
      const seen = await loadFrame(live, w.q, w.analyze !== false, thumb);
      if (seen) {
        summary = seen;
        if (sightEl) sightEl.textContent = seen;
      }
      for (const img of strip.querySelectorAll("img")) {
        if (img.dataset.key === w.key) continue;
        loadFrame(img, img.dataset.q, false);
      }
    };
    tick();
    timer = setInterval(tick, 450);
  }

  function placeholderSync() {
    const input = document.getElementById("input");
    if (!input) return;
    input.placeholder = anyActive()
      ? t("Kamerada ne görüyorsun? Sesli veya yazılı sor…")
      : t("Konuş…");
  }

  async function open() {
    if (!anyActive() || !ready) return;
    if (deck) deck.hidden = true;
    if (layer) layer.hidden = true;
    const w = selectedRow();
    try {
      if (window.pywebview && window.pywebview.api
          && window.pywebview.api.open_camera_window) {
        await window.pywebview.api.open_camera_window(w ? w.key : "");
        placeholderSync();
        refreshIcon();
        return;
      }
    } catch { /* browser / old shell */ }
    window.open("/watch.html?cam=" + encodeURIComponent(w ? w.key : "usb"),
                "dornick-cam", "popup=yes,width=980,height=640");
    placeholderSync();
    refreshIcon();
  }

  function hide() {
    if (deck) deck.hidden = true;
    if (layer) layer.hidden = true;
    document.body.classList.remove("cam-stage", "cam-open");
    clearInterval(timer);
    placeholderSync();
    refreshIcon();
  }

  function close() {
    hide();
    document.body.classList.remove("cam-open");
  }

  async function power(on) {
    try {
      const d = await (await fetch("/api/cameras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "power", enabled: !!on }),
      })).json();
      isOpen = !!(d && d.enabled && (on ? d.live : false));
      if (d && d.enabled === false) isOpen = false;
      refreshIcon();
      if (!anyActive()) close();
      else if (on) open();
      load({ redraw: stageOpen() });
    } catch { /* */ }
  }

  function status(e) {
    isOpen = !!(e && e.enabled && e.live);
    if (e && e.enabled && !e.live && e.note) isOpen = false;
    refreshIcon();
    if (!anyActive()) close();
  }

  function context() {
    if (!anyActive()) return "";
    const w = selectedRow();
    const camName = (w && w.name) || t("Bilgisayar kamerası");
    const seen = summary || t("kare alınamadı");
    return `[Kamera] Şu an "${camName}" bakıyorsun. Yerel GPU: ${seen}. `
      + "Görüntü hakkında soru sorulduğunda kamera aracını kullan.";
  }

  function kindFields() {
    const kindEl = document.getElementById("cam-kind");
    if (!kindEl) return;
    const kind = kindEl.value;
    const net = kind !== "usb";
    for (const id of ["cam-host", "cam-port", "cam-path", "cam-user", "cam-pass"]) {
      const n = document.getElementById(id);
      if (n) n.hidden = !net;
    }
    const idx = document.getElementById("cam-index");
    if (idx) idx.hidden = net;
    const port = document.getElementById("cam-port");
    if (port && net && !port.value) port.placeholder = kind === "rtsp" ? "554" : "80";
  }

  icon.addEventListener("click", () => {
    if (!anyActive()) {
      pop.hidden = !pop.hidden;
      return;
    }
    pop.hidden = true;
    open();
  });
  document.getElementById("cam-enable").addEventListener("click", async () => {
    pop.hidden = true;
    await power(true);
  });
  document.getElementById("cam-settings").addEventListener("click", () => {
    pop.hidden = true;
    const s = document.getElementById("settings-open") || document.getElementById("gear");
    if (s) s.click();
  });
  document.addEventListener("click", (ev) => {
    if (!pop.hidden && !pop.contains(ev.target) && ev.target !== icon
        && !icon.contains(ev.target)) pop.hidden = true;
  });
  load({ redraw: false });
  const camClose = document.getElementById("cam-close");
  if (camClose) camClose.addEventListener("click", hide);
  const stopBtn = document.getElementById("cam-stop");
  if (stopBtn) stopBtn.addEventListener("click", () => power(false));
  const popWin = document.getElementById("cam-stage-pop");
  if (popWin) popWin.addEventListener("click", open);
  const kindEl = document.getElementById("cam-kind");
  if (kindEl) kindEl.addEventListener("change", kindFields);
  kindFields();
  document.getElementById("cam-add").addEventListener("click", async () => {
    const kind = document.getElementById("cam-kind").value;
    const camName = document.getElementById("cam-name").value.trim();
    const analyze = !!(document.getElementById("cam-analyze") || {}).checked;
    const body = { action: "add", kind, name: camName, analyze };
    if (kind === "usb") {
      body.source = (document.getElementById("cam-index").value.trim() || "0");
      if (!body.name) body.name = body.source === "0" ? t("Bilgisayar kamerası") : "kamera";
    } else {
      body.host = document.getElementById("cam-host").value.trim();
      body.port = parseInt(document.getElementById("cam-port").value, 10) || 0;
      body.path = document.getElementById("cam-path").value.trim();
      body.user = document.getElementById("cam-user").value.trim();
      body.password = document.getElementById("cam-pass").value;
      if (!body.host) return;
      if (!body.name) body.name = body.host;
    }
    await fetch("/api/cameras", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    document.getElementById("cam-name").value = "";
    document.getElementById("cam-pass").value = "";
    load({ redraw: true });
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearInterval(timer);
    else if (stageOpen()) refresh();
  });

  return { open, close, hide, status, context, get summary() { return summary; } };
})();
