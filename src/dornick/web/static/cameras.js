// Kamera — izleme her zaman ayrı OS penceresi (`watch.html`).
// Ana Dornick sohbet/beyin olarak kalır; tarayıcı tam ekranı ana belgeye
// uygulanmaz (Dornick kaybolur). Ayarlar Ayarlar › Kameralar’da.
// GPU kutuları sunucuda JPEG üzerine çizilir (`?boxes=1`).

const Cameras = (() => {
  Dil.ekle({
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

  Dil.ekle({
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
  const ikon = document.getElementById("cams");
  const pop = document.getElementById("cam-pop");
  let timer = null;
  let cams = [];
  let hazir = true;
  let acikMi = false;
  let kip = "kesit";
  let gpuAd = "";
  let secili = "usb";
  let ozet = "";
  let liveUrl = "";
  const thumbUrls = new Map();

  function ikonTazele() {
    ikon.classList.toggle("cam-off", !aktifVar());
    ikon.classList.toggle("cam-on", aktifVar());
    ikon.classList.toggle("on", aktifVar());
    ikon.setAttribute("aria-pressed", acikMi ? "true" : "false");
    ikon.title = aktifVar()
      ? t("Kamera açık — tıkla: pencerede izle")
      : t("Kamera kapalı — tıkla: aç");
  }

  function asamaAcik() {
    return !!(deck && !deck.hidden);
  }

  function usb0(c) {
    const src = String(c.source || "0");
    return src === "0" && (!c.kind || c.kind === "usb");
  }

  function netAktif() {
    return cams.some((c) => !usb0(c) && c.enabled);
  }

  function aktifVar() {
    return !!(acikMi || netAktif());
  }

  function adlar() {
    const dahili = cams.find(usb0);
    const extras = cams.filter((c) => !usb0(c));
    return [
      {
        key: "usb",
        ad: (dahili && dahili.name) || t("Bilgisayar kamerası"),
        q: dahili ? "id=" + encodeURIComponent(dahili.id) : "source=0",
        id: dahili ? dahili.id : "",
        izleniyor: !!(dahili && dahili.enabled),
        analyze: dahili ? dahili.analyze !== false : true,
      },
      ...extras.map((c) => ({
        key: c.id,
        ad: c.name,
        q: "id=" + encodeURIComponent(c.id),
        id: c.id,
        izleniyor: !!c.enabled,
        analyze: c.analyze !== false,
      })),
    ];
  }

  function secilen() {
    return adlar().find((w) => w.key === secili) || adlar()[0];
  }

  async function yukle(opts) {
    const redraw = !!(opts && opts.redraw);
    let d = null;
    try {
      d = await (await fetch("/api/cameras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "list" }),
      })).json();
    } catch { return; }
    hazir = !!d.available;
    acikMi = !!d.enabled && (d.live !== false);
    kip = d.vision_mode || "kesit";
    cams = d.cameras || [];
    const gpu = (d.gpus || [])[0];
    gpuAd = gpu ? gpu.name + " · " + Math.round(gpu.total_mb / 1024) + " GB" : "";
    const kisa = !hazir
      ? t("opencv kurulu değil")
      : kip === "gpu"
        ? t("GPU analiz ediyor") + (gpuAd ? " · " + gpuAd : "")
      : kip === "izleme" && gpu
        ? t("GPU hazır") + (gpuAd ? " · " + gpuAd : "")
        : t("GPU yok — sorulunca kesit");
    if (spec) {
      spec.textContent = kisa;
      spec.title = !hazir
        ? t("opencv kurulu değil — kurulumda kamera bileşenini seç")
        : kip === "gpu"
          ? t("GPU analiz ediyor") + ": " + gpuAd + " — "
            + t("kare yerelde okunuyor, sohbet modeline metin gidiyor")
        : kip === "izleme" && gpu
          ? t("GPU hazır") + ": " + gpuAd + " — "
            + ((d.sight && d.sight.reason)
                ? d.sight.reason
                : t("analiz henüz yüklenmedi; şimdilik LLM kesitle bakıyor"))
          : t("GPU yok — LLM sorulduğunda kesitle bakar");
    }
    const lab = document.getElementById("cam-gpu-lab");
    const box = document.getElementById("cam-analyze");
    if (lab && box) {
      const varGpu = kip === "gpu" || kip === "izleme";
      lab.hidden = !varGpu;
      if (varGpu) box.checked = true;
    }
    ikonTazele();
    if (!aktifVar() && asamaAcik()) kapat();
    if (redraw && asamaAcik()) ciz();
    const goz = d.sight || {};
    if (kip === "izleme" && !goz.ready
        && (!goz.tried || goz.reason === "yükleniyor")) {
      setTimeout(() => yukle({ redraw: false }), 2500);
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
      btn.dataset.key = w.key;
      const img = document.createElement("img");
      img.alt = "";
      img.dataset.q = w.q;
      img.dataset.key = w.key;
      const cap = document.createElement("span");
      cap.textContent = w.ad;
      btn.append(img, cap);
      btn.onclick = () => {
        secili = w.key;
        ciz();
      };
      if (w.id && w.key !== "usb") {
        const sil = document.createElement("i");
        sil.textContent = "×";
        sil.title = t("sil");
        sil.onclick = async (ev) => {
          ev.stopPropagation();
          await fetch("/api/cameras", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "remove", id: w.id }),
          });
          if (secili === w.key) secili = "usb";
          yukle({ redraw: true });
        };
        btn.append(sil);
      }
      strip.append(btn);
    });
  }

  function ciz() {
    if (!hazir || !asamaAcik()) return;
    const w = secilen();
    if (titleEl) titleEl.textContent = w ? w.ad : t("Bilgisayar kamerası");
    if (live) live.alt = w ? w.ad : "";
    serit();
    tazele();
  }

  async function kareYukle(img, q, boxes, follow) {
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

  function tazele() {
    clearInterval(timer);
    if (!asamaAcik() || document.hidden || !hazir) return;
    const tick = async () => {
      if (!asamaAcik() || document.hidden) return;
      const w = secilen();
      if (!w || !live) return;
      const thumb = strip && [...strip.querySelectorAll("img")]
        .find((el) => el.dataset.key === w.key);
      const seen = await kareYukle(live, w.q, w.analyze !== false, thumb);
      if (seen) {
        ozet = seen;
        if (sightEl) sightEl.textContent = seen;
      }
      for (const img of strip.querySelectorAll("img")) {
        if (img.dataset.key === w.key) continue;
        kareYukle(img, img.dataset.q, false);
      }
    };
    tick();
    timer = setInterval(tick, 450);
  }

  function yerTut() {
    const input = document.getElementById("input");
    if (!input) return;
    input.placeholder = aktifVar()
      ? t("Kamerada ne görüyorsun? Sesli veya yazılı sor…")
      : t("Konuş…");
  }

  async function ac() {
    if (!aktifVar() || !hazir) return;
    if (deck) deck.hidden = true;
    if (layer) layer.hidden = true;
    const w = secilen();
    try {
      if (window.pywebview && window.pywebview.api
          && window.pywebview.api.open_camera_window) {
        await window.pywebview.api.open_camera_window(w ? w.key : "");
        yerTut();
        ikonTazele();
        return;
      }
    } catch { /* tarayıcı / eski kabuk */ }
    window.open("/watch.html?cam=" + encodeURIComponent(w ? w.key : "usb"),
                "dornick-cam", "popup=yes,width=980,height=640");
    yerTut();
    ikonTazele();
  }

  function gizle() {
    if (deck) deck.hidden = true;
    if (layer) layer.hidden = true;
    document.body.classList.remove("cam-stage", "cam-open");
    clearInterval(timer);
    yerTut();
    ikonTazele();
  }

  function kapat() {
    gizle();
    document.body.classList.remove("cam-open");
  }

  async function guc(on) {
    try {
      const d = await (await fetch("/api/cameras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "power", enabled: !!on }),
      })).json();
      acikMi = !!(d && d.enabled && (on ? d.live : false));
      if (d && d.enabled === false) acikMi = false;
      ikonTazele();
      if (!aktifVar()) kapat();
      else if (on) ac();
      yukle({ redraw: asamaAcik() });
    } catch { /* */ }
  }

  function durum(e) {
    acikMi = !!(e && e.enabled && e.live);
    if (e && e.enabled && !e.live && e.note) acikMi = false;
    ikonTazele();
    if (!aktifVar()) kapat();
  }

  function baglam() {
    if (!aktifVar()) return "";
    const w = secilen();
    const ad = (w && w.ad) || t("Bilgisayar kamerası");
    const ne = ozet || t("kare alınamadı");
    return `[Kamera] Şu an "${ad}" bakıyorsun. Yerel GPU: ${ne}. `
      + "Görüntü hakkında soru sorulduğunda kamera aracını kullan.";
  }

  function turAlanlari() {
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

  ikon.addEventListener("click", () => {
    if (!aktifVar()) {
      pop.hidden = !pop.hidden;
      return;
    }
    pop.hidden = true;
    ac();
  });
  document.getElementById("cam-enable").addEventListener("click", async () => {
    pop.hidden = true;
    await guc(true);
  });
  document.getElementById("cam-settings").addEventListener("click", () => {
    pop.hidden = true;
    const s = document.getElementById("settings-open") || document.getElementById("gear");
    if (s) s.click();
  });
  document.addEventListener("click", (ev) => {
    if (!pop.hidden && !pop.contains(ev.target) && ev.target !== ikon
        && !ikon.contains(ev.target)) pop.hidden = true;
  });
  yukle({ redraw: false });
  const camClose = document.getElementById("cam-close");
  if (camClose) camClose.addEventListener("click", gizle);
  const dur = document.getElementById("cam-stop");
  if (dur) dur.addEventListener("click", () => guc(false));
  const popWin = document.getElementById("cam-stage-pop");
  if (popWin) popWin.addEventListener("click", ac);
  const kindEl = document.getElementById("cam-kind");
  if (kindEl) kindEl.addEventListener("change", turAlanlari);
  turAlanlari();
  document.getElementById("cam-add").addEventListener("click", async () => {
    const kind = document.getElementById("cam-kind").value;
    const ad = document.getElementById("cam-name").value.trim();
    const analyze = !!(document.getElementById("cam-analyze") || {}).checked;
    const body = { action: "add", kind, name: ad, analyze };
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
    yukle({ redraw: true });
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearInterval(timer);
    else if (asamaAcik()) tazele();
  });

  return { ac, kapat, gizle, durum, baglam, get ozet() { return ozet; } };
})();
