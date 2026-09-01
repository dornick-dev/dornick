// Görüntüleyici: ajanın o an dokunduğu şey.
//
// Sohbet ne yapıldığını anlatıyor ama gösteremiyor. Ajan bir betik yazdığında
// "yazdım" cümlesini okumakla dosyayı görmek aynı şey değil; bir site kurunca
// da kaynağı değil sitenin kendisini görmek gerekiyor.
//
// Bu yüzden panel iki kip taşıyor:
//
//   kaynak    dosya, satır numaralı ve renklendirilmiş bir kod görünümünde
//   sahne     .html ise gerçekten çalışan hali, yalıtılmış bir çerçevede
//
// Kendiliğinden açılıyor: ajan bir dosyaya dokunduğunda panel o dosyaya
// geçiyor. Kullanıcı kapatırsa bir daha zorlamıyor — kapatmak bir karar.

const Viewer = (() => {
  const panel = document.getElementById("viewer");
  const title = document.getElementById("viewer-path");
  const body = document.getElementById("viewer-body");
  const modes = document.getElementById("viewer-modes");

  // Tam yol/adres etikette kırpık durur; tıklayınca TAMAMI panoya gider
  // ("tam dosya yolu göremiyorum" canlı yarası — başlığın title'ı fareyle
  // duruyor ama kopyalanamıyordu).
  if (title) {
    title.style.cursor = "copy";
    title.addEventListener("click", async () => {
      const full = title.title || title.textContent || "";
      if (!full) return;
      try {
        await navigator.clipboard.writeText(full);
        if (typeof say === "function") say(t("Yol kopyalandı ✓") + " " + full);
      } catch { /* pano izni yok */ }
    });
  }

  Dil.ekle({
    "Kaynak": "Source", "Sahne": "Stage",
    "Kopyala": "Copy", "Kopyalandı ✓": "Copied ✓", "Kopyalanamadı": "Copy failed",
    "Sar": "Wrap", "Uzun satırları sar / tek satırda kaydır": "Wrap long lines / scroll instead",
    "Dosyayı panoya kopyala": "Copy file to clipboard",
    "İkili dosya": "Binary file", "Bu bir dizin": "This is a directory",
    "Görsel açılamadı": "Could not open the image",
    "Tıkla — 1:1 boyut / sığdır": "Click — actual size / fit",
    "Tıkla — sığdır": "Click — fit",
    "Tarayıcıda aç": "Open in browser", "Klasörde göster": "Show in folder",
    "Açılamadı": "Could not open",
    "Okunamadı": "Could not read", "Henüz bir şeye dokunulmadı": "Nothing touched yet",
    "Dosyanın başı gösteriliyor": "Showing the head of the file",
    "Sayfa yok": "No page",
    "İndir": "Download", "Yazdır / PDF": "Print / PDF",
    "Gerçek tarayıcıda aç": "Open in your real browser",
    "İndirildi": "Saved", "Yol kopyalandı ✓": "Path copied ✓",
    "Tıkla — tam yolu kopyala": "Click — copy full path",
    "İndirilemedi": "Could not download",
    "Yazdırılamadı": "Could not print",
    "Adres yok": "No address",
    "Değişiklikler": "Changes",
    "Tarayıcı": "Browser",
    "Yeni terminal": "New terminal",
    "Henüz bir sayfa yok. Dornick bir siteye gidince burada açılır.":
      "No page yet. When Dornick visits a site it opens here.",
    "Sekmeyi kapat": "Close tab",
  });

  // Bu araçlar bir dosyaya dokunuyor; hangisinin hangi argümanda olduğu
  // araca göre değişiyor.
  const WATCHED = new Set(["read_file", "write_file", "edit_file", "copy_in", "draw"]);

  // Çizim bir dosya değil bir sunum: ajan onu göstermek için çağırıyor.
  // Kullanıcı paneli daha önce kapattıysa bile açılıyor ve kaynak değil
  // sahne kipinde geliyor — çizimin HTML'ini okumak istenen şey değil.
  const PRESENTS = new Set(["draw"]);

  let current = "";
  let mode = "source";
  let dismissed = false;
  let loading = null;
  let sourceText = "";   // kopyala düğmesi için: o an gösterilen ham metin
  let wrap = false;      // uzun satırlar: kaydır (false) / sar (true)
  let lastUrl = "";
  const termLines = [];  // {kind: "cmd"|"out"|"err", text}
  const TERM_CAP = 120;

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  // --- dışarıya açık -----------------------------------------------------

  function watch(tool, args) {
    if (!WATCHED.has(tool) || !args) return;
    if (PRESENTS.has(tool)) return;   // yolu araç bitince geliyor
    const path = args.to || args.path;
    if (typeof path === "string" && path.trim()) show(path.trim());
  }

  // Ajan bir çizim koydu: paneli aç, sahne kipine geç.
  function present(path) {
    if (typeof path !== "string" || !path.trim()) return;
    dismissed = false;
    mode = "live";
    show(path.trim());
  }

  // Sunucudan servis edilen CANLI bir sayfa (artifact gibi): dosya değil
  // adres. İçerik her açılışta sunucudan taze çekilir ve çizimlerle AYNI
  // yalıtılmış çerçevede gösterilir (allow-same-origin yok): ajanın yazdığı
  // sayfa programın DOM'una ve /api uçlarına erişemiyor — kendi izin
  // kapısını betikle atlaması bu programda en pahalı hata olurdu.
  let pageLabel = "";

  function page(url, label) {
    if (typeof url !== "string" || !url.trim()) return;
    dismissed = false;
    rememberDesk(true);
    mode = "live";
    pageLabel = label || url;
    current = "url:" + url.trim();
    lastUrl = url.trim();
    foldSide();
    panel.hidden = false;
    document.body.classList.add("viewing");
    load(current);
  }

  // Bu adres şu an panelde açık mı? (artifact güncellenince tazelemek için)
  function showing(url) {
    return !panel.hidden && current === "url:" + url;
  }

  // İş bittiğinde gösterileni tazele: yazma tamamlandığında panelde hâlâ
  // eski içerik duruyordu. Aracın bildirdiği yol çözülmüş halde geliyor,
  // o yüzden `current` ile birebir tutmayabilir — panel açıksa ve dokunulan
  // araç izlenenlerdense yeniden yüklemek en doğrusu.
  function refresh(tool, path) {
    if (PRESENTS.has(tool)) { present(path); return; }
    if (panel.hidden || !WATCHED.has(tool)) return;
    if (typeof path === "string" && path.trim()) { current = path.trim(); }
    load(current);
  }


  // Dar bantta (<=1160) sag yuzey acilirken kenar cubugu KATLANIR: ikisi
  // birden sigmiyor (olculdu — cekmece kipi cubugu sohbetin ustune
  // yuzduruyordu ve "Dusunuyor" basligi tiklanamiyordu, 31.08).
  function foldSide() {
    if (innerWidth <= 1160 && typeof History !== "undefined" && History.close) {
      try { History.close(); } catch { /* panel yoksa */ }
    }
  }

  function show(path) {
    current = path;
    if (dismissed) return;      // kullanıcı kapattı; zorlamıyoruz
    foldSide();
    panel.hidden = false;
    document.body.classList.add("viewing");
    load(path);
  }

  // Sohbetteki bir dosya referansından geliniyor: paneli AÇ (kullanıcı daha
  // önce kapatmış olsa bile — bu bir kullanıcı isteği, ajanın dayatması
  // değil) ve satır verildiyse oraya kaydırıp vurgula.
  //
  // Satır beklemeli bir iş: dosya sunucudan geliyor ve satırlar ancak
  // çizildikten sonra var oluyor. `pendingLine` çizimin sonunda okunuyor.
  function open(path, line) {
    if (typeof path !== "string" || !path.trim()) return;
    dismissed = false;
    mode = "source";
    pendingLine = Number(line) > 0 ? Number(line) : 0;
    const target = path.trim();
    // Aynı dosya zaten açıksa yeniden yüklemeye gerek yok: sadece satıra git.
    if (!panel.hidden && current === target) { gotoLine(pendingLine); return; }
    show(target);
  }

  let pendingLine = 0;

  // Satıra git: kaydır ve kısa bir vurgu bırak. Vurgu kalıcı değil —
  // "hangi satırdı" sorusunu cevaplayacak kadar duruyor, sonra soluyor;
  // kalıcı olsa dosyada gezinirken yanlış yeri işaret eden bir leke olurdu.
  function gotoLine(line) {
    pendingLine = 0;
    if (!(line > 0)) return;
    const rows = body.querySelectorAll(".viewer-code .vl");
    const row = rows[line - 1];
    if (!row) return;
    for (const eski of body.querySelectorAll(".vl.hit")) eski.classList.remove("hit");
    row.classList.add("hit");
    row.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  const DESK = "dornick-desk";
  function rememberDesk(on) {
    try {
      if (on) localStorage.removeItem(DESK);
      else localStorage.setItem(DESK, "off");
    } catch { /* pywebview / gizli kip */ }
  }

  function close() {
    panel.hidden = true;
    dismissed = true;
    rememberDesk(false);
    document.body.classList.remove("viewing"); document.body.classList.remove("viewer-max");
  }

  function host(label, fill) {
    dismissed = false;
    rememberDesk(true);
    current = "git:pane";
    pageLabel = label || "Git";
    mode = "git";
    foldSide();
    panel.hidden = false;
    document.body.classList.add("viewing");
    title.textContent = pageLabel;
    title.title = pageLabel;
    modes.textContent = "";
    loading = null;
    if (typeof fill === "function") fill(body);
    noteTab();
  }

  function hosted() {
    return !panel.hidden && current === "git:pane";
  }

  function hostedGoals() {
    return !panel.hidden && current === "plan:goals";
  }

  function toggle() {
    if (panel.hidden) {
      dismissed = false;
      rememberDesk(true);
      if (!current) { openPin("git:pane"); return; }
      panel.hidden = false;
      document.body.classList.add("viewing");
      load(current);
    } else {
      close();
    }
  }

  // --- yükleme -----------------------------------------------------------

  // Basliga son iki parca yaziliyor: tam yol satiri dolduruyor ve kirpilinca
  // geriye "…html" gibi hicbir sey soylemeyen bir kalinti kaliyordu.
  function label(path) {
    const parts = String(path || "").split(/[\/]/).filter(Boolean);
    return parts.length > 2 ? "…/" + parts.slice(-2).join("/") : parts.join("/");
  }

  // Dosya boyutu başlıkta: "hangi dosya" kadar "ne kadarlık bir şey" de
  // bir bakışta okunmalı.
  function human(bytes) {
    if (typeof bytes !== "number") return "";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  }

  // --- sekmeler ---------------------------------------------------------
  //
  // Cursor sağ paneli: sabit güverte (Değişiklikler · Tarayıcı ·
  // powershell) + açılan dosya sekmeleri. Şerit her zaman durur —
  // tek dosyada da kaybolmaz.
  const PINNED = [
    { key: "git:pane", kind: "changes", label: () => t("Değişiklikler") },
    // İş listesi: yalnız madde varken pin — boşken Cursor'daki gibi yok.
    { key: "plan:goals", kind: "goals", label: () => t("İş listesi"), when: "goals" },
    { key: "desk:browser", kind: "browser", label: () => t("Tarayıcı") },
    { key: "desk:term", kind: "term", label: () => "powershell" },
  ];
  let goalsPin = false;
  function setGoalsPin(on) {
    const next = !!on;
    if (goalsPin === next) {
      if (next && current === "plan:goals") drawTabs();
      return;
    }
    goalsPin = next;
    if (!next && current === "plan:goals") {
      // Boşaldı: sabit güverteye dön.
      openPin("git:pane");
      return;
    }
    drawTabs();
  }
  const tabs = [];              // {key, mode, label} — dosya / url sekmeleri
  function pinOn(key) {
    if (key === "git:pane") return "git:pane";
    if (key === "plan:goals") return "plan:goals";
    if (key === "desk:term") return "desk:term";
    if (key === "desk:browser" || String(key).startsWith("url:")) return "desk:browser";
    return "";
  }
  function noteTab() {
    if (!current) return;
    // Adres, Tarayıcı sekmesinin kendisi: ayrı bir dosya sekmesi açma.
    if (PINNED.some((p) => p.key === current) || String(current).startsWith("url:")) {
      drawTabs();
      return;
    }
    const kayit = {
      key: current, mode,
      label: String(current).startsWith("url:")
        ? (pageLabel || current.slice(4)) : label(current),
    };
    const i = tabs.findIndex((s) => s.key === current);
    if (i >= 0) tabs[i] = kayit;
    else { tabs.push(kayit); if (tabs.length > 8) tabs.shift(); }
    drawTabs();
  }
  function iconFor(kind) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("aria-hidden", "true");
    const add = (tag, attrs) => {
      const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
      for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
      svg.append(n);
    };
    if (kind === "changes") {
      add("circle", { cx: "5", cy: "4", r: "1.6", fill: "none", stroke: "currentColor", "stroke-width": "1.4" });
      add("circle", { cx: "5", cy: "12", r: "1.6", fill: "none", stroke: "currentColor", "stroke-width": "1.4" });
      add("circle", { cx: "12", cy: "8.5", r: "1.6", fill: "none", stroke: "currentColor", "stroke-width": "1.4" });
      add("path", { d: "M5 5.6v4.8M6.6 4.6c2.2.4 4.2 1.4 5.2 3.2", fill: "none", stroke: "currentColor", "stroke-width": "1.3" });
    } else if (kind === "browser") {
      add("circle", { cx: "8", cy: "8", r: "5.5", fill: "none", stroke: "currentColor", "stroke-width": "1.4" });
      add("path", { d: "M2.5 8h11M8 2.5c1.8 2.2 1.8 8.8 0 11M8 2.5c-1.8 2.2-1.8 8.8 0 11", fill: "none", stroke: "currentColor", "stroke-width": "1.2" });
    } else if (kind === "term") {
      add("rect", { x: "2", y: "3", width: "12", height: "10", rx: "1.4", fill: "none", stroke: "currentColor", "stroke-width": "1.4" });
      add("path", { d: "M5 7.2 7 8.5 5 9.8M8.5 10.4H11", fill: "none", stroke: "currentColor", "stroke-width": "1.3", "stroke-linecap": "round" });
    } else if (kind === "goals") {
      add("path", { d: "M3.5 4.5h9M3.5 8h9M3.5 11.5h6", fill: "none", stroke: "currentColor", "stroke-width": "1.4", "stroke-linecap": "round" });
      add("circle", { cx: "12.2", cy: "11.5", r: "1.4", fill: "currentColor" });
    }
    return svg;
  }
  function drawTabs() {
    const serit = document.getElementById("viewer-tabs");
    if (!serit) return;
    serit.textContent = "";
    serit.hidden = false;
    const activePin = pinOn(current);
    for (const pin of PINNED) {
      if (pin.when === "goals" && !goalsPin) continue;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "v-tab pin" + (pin.key === current || pin.key === activePin ? " on" : "");
      b.title = pin.label();
      const ad = document.createElement("span");
      ad.textContent = pin.label();
      b.append(iconFor(pin.kind), ad);
      b.onclick = () => openPin(pin.key);
      serit.append(b);
    }
    for (const sk of tabs) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "v-tab" + (sk.key === current ? " on" : "");
      b.title = String(sk.key).startsWith("url:") ? sk.key.slice(4) : sk.key;
      const ad = document.createElement("span");
      ad.textContent = sk.label;
      const x = document.createElement("i");
      x.textContent = "×";
      x.setAttribute("aria-label", t("Sekmeyi kapat"));
      x.onclick = (ev) => { ev.stopPropagation(); dropTab(sk.key); };
      b.append(ad, x);
      b.onclick = () => {
        if (sk.key === current) return;
        mode = sk.mode;
        current = sk.key;
        if (String(sk.key).startsWith("url:")) pageLabel = sk.label;
        load(sk.key);
      };
      serit.append(b);
    }
  }
  function openPin(key) {
    dismissed = false;
    rememberDesk(true);
    if (key === "desk:browser" && lastUrl) {
      page(lastUrl);
      return;
    }
    if (key === current && !panel.hidden) return;
    if (key === "git:pane") {
      host(t("Değişiklikler"), (el) => {
        if (typeof GitBar !== "undefined") GitBar.paint(el);
      });
      return;
    }
    if (key === "plan:goals") {
      showGoals();
      return;
    }
    current = key;
    mode = key === "desk:term" ? "term" : "live";
    foldSide();
    panel.hidden = false;
    document.body.classList.add("viewing");
    load(key);
  }
  function showGoals() {
    dismissed = false;
    rememberDesk(true);
    current = "plan:goals";
    pageLabel = t("İş listesi");
    mode = "goals";
    foldSide();
    panel.hidden = false;
    document.body.classList.add("viewing");
    title.textContent = pageLabel;
    title.title = pageLabel;
    modes.textContent = "";
    loading = null;
    if (typeof Goals !== "undefined" && Goals.paint) Goals.paint(body);
    else {
      body.textContent = "";
      body.append(el("p", "viewer-blank", t("İş listesi yok.")));
    }
    noteTab();
  }
  function psPrefix() {
    const bar = document.getElementById("git-bar");
    const cwd = (bar && bar.dataset && bar.dataset.root) || "";
    return cwd ? ("PS " + cwd + "> ") : "PS> ";
  }
  function paintTerm() {
    body.textContent = "";
    const pane = el("div", "desk-term");
    pane.append(el("div", "desk-term-name", "powershell"));
    const ps = psPrefix();
    for (const line of termLines) {
      const row = el("div", "desk-term-line " + line.kind);
      if (line.kind === "cmd") {
        row.append(el("span", "desk-ps", ps), el("span", "", line.text));
      } else {
        row.textContent = line.text;
      }
      pane.append(row);
    }
    const prompt = el("div", "desk-term-line cmd");
    prompt.append(el("span", "desk-ps", ps), el("span", "desk-cursor", ""));
    pane.append(prompt);
    body.append(pane);
    body.scrollTop = body.scrollHeight;
  }
  function paintBrowserEmpty() {
    body.textContent = "";
    body.append(el("p", "viewer-blank", t("Henüz bir sayfa yok. Dornick bir siteye gidince burada açılır.")));
  }
  function shellOut(e) {
    const d = e.detail;
    if (d && typeof d === "object" && d.output) return String(d.output).trim();
    if (typeof d === "string" && d.trim()) return d.trim();
    return String(e.summary || "").trim();
  }
  function feed(e) {
    if (!e) return;
    if (e.tool === "shell" || e.tool === "kos") {
      const cmd = (e.input && (e.input.command || e.input.cmd)) || "";
      const started = e.ms == null && e.summary == null && !e.detail;
      if (cmd && started) {
        termLines.push({ kind: "cmd", text: String(cmd).trim() });
      } else {
        const trimmed = String(cmd).trim();
        if (cmd && !termLines.some((l) => l.kind === "cmd" && l.text === trimmed)) {
          termLines.push({ kind: "cmd", text: trimmed });
        }
        const text = shellOut(e);
        if (text) termLines.push({ kind: e.error ? "err" : "out", text });
      }
      while (termLines.length > TERM_CAP) termLines.shift();
      if (!panel.hidden) {
        if (started && current !== "desk:term") openPin("desk:term");
        else if (current === "desk:term") paintTerm();
      }
    }
    if (e.tool === "browser" && e.input && e.input.url) {
      const act = e.input.action;
      if (!act || act === "open" || act === "go") lastUrl = String(e.input.url);
    }
  }
  function dropTab(key) {
    const i = tabs.findIndex((s) => s.key === key);
    if (i < 0) return;
    tabs.splice(i, 1);
    if (key === current) {
      const nxt = tabs[Math.min(i, tabs.length - 1)];
      if (nxt) { mode = nxt.mode; current = nxt.key; load(nxt.key); return; }
      openPin("git:pane");
      return;
    }
    drawTabs();
  }

  async function load(path) {
    noteTab();
    // Yol etiketi: `hidden = true` bir daha hiç açılmıyordu — dosya/adres
    // başlıkta hiç görünmüyordu ("tam dosya yolu göremiyorum", 31.08).
    // Sabit güvertelerde (git/terminal) gizli kalır, içerikte görünür.
    title.hidden = true;
    // Git panosu: gövdeyi GitBar çizer; dosya API'sine gitme.
    if (path === "git:pane") {
      title.textContent = pageLabel || t("Değişiklikler");
      title.title = pageLabel || t("Değişiklikler");
      modes.textContent = "";
      if (typeof GitBar !== "undefined") GitBar.paint(body);
      return;
    }
    if (path === "plan:goals") {
      title.textContent = t("İş listesi");
      title.title = t("İş listesi");
      modes.textContent = "";
      if (typeof Goals !== "undefined" && Goals.paint) Goals.paint(body);
      else {
        body.textContent = "";
        body.append(el("p", "viewer-blank", t("İş listesi yok.")));
      }
      return;
    }
    if (path === "desk:term") {
      modes.textContent = "";
      paintTerm();
      return;
    }
    if (path === "desk:browser") {
      modes.textContent = "";
      if (lastUrl) { page(lastUrl, pageLabel); return; }
      paintBrowserEmpty();
      return;
    }
    // Adres kipi: sunucunun servis ettiği sayfa taze çekilip yalıtılmış
    // çerçevede açılıyor. Aynı yarış kuralı: son istek kazanır.
    if (typeof path === "string" && path.startsWith("url:")) {
      const url = path.slice(4);
      title.textContent = pageLabel || url;
      title.title = url.startsWith("/") ? (location.origin + url) : url;
      title.hidden = false;
      modes.textContent = "";
      const token = {};
      loading = token;
      // Canlı uygulama (localhost): srcdoc değil — kendi origin'inde iframe.
      if (/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?\//i.test(url)
          || /^https?:\/\/(127\.0\.0\.1|localhost):\d+/i.test(url)) {
        if (loading !== token) return;
        body.textContent = "";
        body.append(liveFrame(url));
        modes.append(pageExportActs(url));
        return;
      }
      let html = "";
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) {
          if (loading === token) blank(t("Sayfa yok") + " (" + res.status + ")");
          return;
        }
        html = await res.text();
      } catch {
        if (loading === token) blank(t("Okunamadı"));
        return;
      }
      if (loading !== token) return;
      body.textContent = "";
      body.append(frame(html));
      if (url.startsWith("/artifact/") || url.includes("/artifact/")
          || url.startsWith("/gorev-rapor/") || url.includes("/gorev-rapor/")) {
        modes.textContent = "";
        modes.append(pageExportActs(url));
      }
      return;
    }

    title.textContent = label(path) || "—";
    title.title = path || "";
    title.hidden = !path;
    if (!path) { blank(t("Henüz bir şeye dokunulmadı")); return; }

    // Aynı dosya art arda birkaç kez tetiklenebiliyor; son istek kazanmalı.
    const token = {};
    loading = token;

    let data;
    try {
      data = await (await fetch("/api/files?path=" + encodeURIComponent(path))).json();
    } catch {
      if (loading === token) blank(t("Okunamadı"));
      return;
    }
    if (loading !== token) return;

    if (data.error || data.entries) { blank(t("Bu bir dizin")); return; }
    render(data);
  }

  function blank(text) {
    body.textContent = "";
    modes.textContent = "";
    body.append(el("p", "viewer-blank", text));
  }

  function render(data) {
    body.textContent = "";
    sourceText = data.text || "";
    drawModes(data);

    // Başlıkta ad + boyut; tam yol üstüne gelince (title) duruyor,
    // tıklayınca panoya kopyalanıyor.
    const size = human(data.size);
    title.textContent = (label(data.path) || "—") + (size ? " · " + size : "");
    title.title = data.path || "";
    title.hidden = !data.path;

    // Medya: "İKİLİ DOSYA" yazmak bir görseli göstermemek demekti. Görsel,
    // ses, video ve PDF ham uçtan (`/api/raw`) gerçekten açılıyor.
    const tur = mediaKind(data.path);
    if (tur) { body.append(mediaView(tur, data)); return; }

    if (data.binary) { body.append(unknownBinary(data)); return; }

    if (mode === "live" && isPage(data.path)) {
      body.append(frame(data.text || ""));
      return;
    }

    // .md dosyası biçimlendirilmiş görünmeli; gerisi kod görünümünde.
    if (/\.mdx?$/i.test(data.path)) {
      const holder = el("div", "viewer-source");
      holder.append(Markdown.render(sourceText));
      body.append(holder);
    } else {
      body.append(codeView(sourceText, language(data.path)));
    }
    if (data.truncated) body.append(el("p", "viewer-blank", t("Dosyanın başı gösteriliyor")));
    // Sohbetteki bir referanstan gelindiyse (`loop.py:42`) satır ancak
    // burada, çizim bittikten sonra var: bekleyen istek şimdi karşılanıyor.
    if (pendingLine) gotoLine(pendingLine);
  }

  // --- medya -------------------------------------------------------------
  //
  // Bir PNG açıldığında panel "İKİLİ DOSYA" yazıyordu: ajan bir görsel
  // ürettiğinde ("grafiği çizdim") kullanıcı onu göremiyordu — sohbetin
  // anlatıp gösterememesi, bu panelin var olma sebebinin ta kendisi.
  //
  // Baytlar `/api/raw`dan geliyor (çalışma alanı içi, yol kaçışı korumalı,
  // nosniff). Türü uzantı söylüyor; tanınmayan ikili dosya eski mesajını
  // koruyor ama artık boyutu ve klasörde gösterme eylemiyle.

  const IMAGE = /\.(png|jpe?g|gif|webp|bmp|ico|svg)$/i;
  const AUDIO = /\.(mp3|wav|ogg|m4a|flac)$/i;
  const VIDEO = /\.(mp4|webm|mov)$/i;
  const PDF = /\.pdf$/i;

  function mediaKind(path) {
    const name = String(path || "");
    if (IMAGE.test(name)) return "image";
    if (AUDIO.test(name)) return "audio";
    if (VIDEO.test(name)) return "video";
    if (PDF.test(name)) return "pdf";
    return "";
  }

  const rawUrl = (path) => "/api/raw?path=" + encodeURIComponent(path || "");

  function mediaView(kind, data) {
    const box = el("div", "viewer-media " + kind);
    const url = rawUrl(data.path);

    if (kind === "image") {
      const img = document.createElement("img");
      img.className = "viewer-img";
      img.alt = data.name || data.path || "";
      img.src = url;
      // Piksel ölçüsü başlığa: bir görselde "ne kadar büyük" sorusunun
      // cevabı dosya boyutu değil, kenar uzunlukları.
      img.addEventListener("load", () => {
        const px = img.naturalWidth + "×" + img.naturalHeight;
        const size = human(data.size);
        title.textContent = (label(data.path) || "—") + " · " + px
                          + (size ? " · " + size : "");
      });
      img.addEventListener("error", () => {
        box.textContent = "";
        box.append(el("p", "viewer-blank", t("Görsel açılamadı")));
      });
      // Tıklayınca 1:1 ↔ sığdır. Sığdırılmış bir ekran görüntüsünde yazı
      // okunmuyor; 1:1 hali kutunun içinde kayıyor.
      img.title = t("Tıkla — 1:1 boyut / sığdır");
      img.addEventListener("click", () => {
        box.classList.toggle("full");
        img.title = box.classList.contains("full")
          ? t("Tıkla — sığdır") : t("Tıkla — 1:1 boyut / sığdır");
      });
      box.append(img);
      return box;
    }

    if (kind === "audio" || kind === "video") {
      const player = document.createElement(kind === "audio" ? "audio" : "video");
      player.className = kind === "audio" ? "viewer-audio" : "viewer-video";
      player.src = url;
      player.controls = true;
      player.preload = "metadata";
      box.append(player);
      return box;
    }

    // PDF: gömülü görüntüleyici tarayıcının kendi eklentisi — sayfa DOM'una
    // erişemiyor. Açılmazsa (eklenti kapalı) altındaki düğme kalıyor.
    const holder = document.createElement("iframe");
    holder.className = "viewer-pdf";
    holder.src = url;
    holder.setAttribute("referrerpolicy", "no-referrer");
    box.append(holder);
    box.append(openButton(url, t("Tarayıcıda aç")));
    return box;
  }

  // Gerçekten ikili ve tanınmayan tür: gösterilecek bir şey yok ama ölü bir
  // mesaj da bırakılmıyor — ne kadar yer kapladığı ve nerede olduğu.
  function unknownBinary(data) {
    const box = el("div", "viewer-media unknown");
    box.append(el("p", "viewer-blank", t("İkili dosya")));
    const size = human(data.size);
    if (size) box.append(el("p", "viewer-note", size));

    const acts = el("div", "viewer-acts");
    acts.append(openButton(rawUrl(data.path), t("Tarayıcıda aç")));
    // İndirme: octet-stream'i "tarayıcıda aç"maya çalışmak bazı türlerde
    // boş sekmeyle bitiyordu; attachment başlığı dosyayı doğrudan indirir.
    const indir = el("a", "viewer-open");
    indir.textContent = t("İndir");
    indir.href = rawUrl(data.path) + "&download=1";
    indir.setAttribute("download", "");
    acts.append(indir);

    // "Nerede bu şey?": dosyayı gezginde seçili açar. Uç atölyeyle sınırlı
    // (apps.reveal); dışarıdaki bir dosyada sebebini kendisi söylüyor.
    const show = el("button", "viewer-open", t("Klasörde göster"));
    show.type = "button";
    show.addEventListener("click", async () => {
      let answer = null;
      try {
        answer = await (await fetch("/api/apps/reveal", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: data.path }),
        })).json();
      } catch { /* sunucu cevap vermedi */ }
      if (!answer || answer.ok === false) {
        const why = el("p", "viewer-note bad", (answer && answer.error) || t("Açılamadı"));
        acts.after(why);
        setTimeout(() => why.remove(), 6000);
      }
    });
    acts.append(show);
    box.append(acts);
    return box;
  }

  function openButton(url, text) {
    const button = el("button", "viewer-open", text);
    button.type = "button";
    button.addEventListener("click", () => window.open(url, "_blank", "noopener"));
    return button;
  }

  // --- kod görünümü ------------------------------------------------------
  //
  // Satır numaralı, renklendirilmiş, ligatürsüz. Numaralar CSS sayacıyla
  // (::before) çiziliyor: seçilip kopyalanan metne satır numarası
  // karışmıyor. Uzun satır ya kendi içinde kayıyor ya da (sar düğmesi)
  // satır başına kırılıyor; panel dışına asla taşmıyor.

  // Bu kadar satırın üstünde numarasız düz metne düşülüyor: on binlerce
  // satır DOM düğümü kaydırmayı sürüklenemez yapıyor.
  const ROW_CAP = 60000;

  function codeView(source, lang) {
    const box = el("div", "viewer-code" + (wrap ? " wrap" : ""));
    const total = countRows(source);

    if (total > ROW_CAP) {
      const pre = el("pre", "viewer-plain");
      pre.textContent = source;
      box.append(pre);
      return box;
    }

    // Numara sütunu en geniş numaraya göre: 9 ile 999'un hizası aynı.
    box.style.setProperty("--gutter", (String(total).length + 3) + "ch");
    for (const fragment of paintRows(source, lang, total)) {
      const row = el("div", "vl");
      const text = el("span", "vl-tx");
      text.append(fragment);
      row.append(text);
      box.append(row);
    }
    return box;
  }

  // Kuyruktaki boş satır dosyanın son yeni-satırından; numaralamaya değmez.
  function countRows(source) {
    const rows = source.split("\n");
    if (rows.length > 1 && rows[rows.length - 1] === "") rows.pop();
    return Math.max(1, rows.length);
  }

  // Renklendirilmiş kaynağı satır satır parçalara böler. Vurgulayıcı tüm
  // metni tek seferde boyuyor (blok yorum gibi çok satırlı parçalar ancak
  // böyle doğru çıkıyor); satır numarası içinse her satırın kendi kutusu
  // gerekiyor. Boyanmış düğümler yeni-satırlardan bölünür, sınıf korunur.
  // HTML dizesi yok: her parça yine createElement + textContent.
  function paintRows(source, lang, total) {
    const scratch = document.createElement("code");
    if (lang && typeof Syntax !== "undefined" && Syntax.paint) {
      Syntax.paint(scratch, source, lang);
    } else {
      scratch.textContent = source;
    }

    const rows = [document.createDocumentFragment()];
    for (const node of [...scratch.childNodes]) {
      const pieces = String(node.textContent).split("\n");
      for (let i = 0; i < pieces.length; i++) {
        if (i > 0) rows.push(document.createDocumentFragment());
        if (!pieces[i]) continue;
        if (node.nodeType === Node.TEXT_NODE) {
          rows[rows.length - 1].append(document.createTextNode(pieces[i]));
        } else {
          const span = document.createElement("span");
          span.className = node.className;
          span.textContent = pieces[i];
          rows[rows.length - 1].append(span);
        }
      }
    }
    // Sayı gutter'la birebir: eksikse boş satır, fazlaysa (son yeni-satır) at.
    while (rows.length < total) rows.push(document.createDocumentFragment());
    rows.length = total;
    return rows;
  }

  function drawModes(data) {
    modes.textContent = "";

    if (isPage(data.path)) {
      for (const [id, name] of [["source", t("Kaynak")], ["live", t("Sahne")]]) {
        const button = el("button", mode === id ? "on" : "", name);
        button.type = "button";
        button.addEventListener("click", () => { mode = id; render(data); });
        modes.append(button);
      }
    } else {
      mode = "source";
    }

    // Sahne kipinde, medyada ve ikili dosyada kaynak araçlarının işi yok:
    // bir PNG'de "sar" ya da "kopyala" anlamsız.
    if (data.binary || mediaKind(data.path) || (mode === "live" && isPage(data.path))) return;

    if (!/\.mdx?$/i.test(data.path)) {
      const bend = el("button", wrap ? "on" : "", t("Sar"));
      bend.type = "button";
      bend.title = t("Uzun satırları sar / tek satırda kaydır");
      bend.addEventListener("click", () => { wrap = !wrap; render(data); });
      modes.append(bend);
    }

    const copy = el("button", "", t("Kopyala"));
    copy.type = "button";
    copy.title = t("Dosyayı panoya kopyala");
    copy.addEventListener("click", () => copyText(copy));
    modes.append(copy);
  }

  // Panoya kopyalar ve düğmenin üstünde kısa bir onay gösterir: tıklayıp
  // hiçbir şey olmaması "çalıştı mı" belirsizliği bırakıyordu. Asıl yol
  // Clipboard API; gömülü çerçeveler izni reddedebiliyor — o zaman eski
  // usul (geçici textarea + execCommand) devreye giriyor.
  function copyText(button) {
    const done = (msg, ok) => {
      button.textContent = msg;
      button.classList.toggle("ok", ok);
      setTimeout(() => {
        button.textContent = t("Kopyala");
        button.classList.remove("ok");
      }, 1400);
    };
    const fallback = () => {
      const ok = legacyCopy(sourceText);
      done(ok ? t("Kopyalandı ✓") : t("Kopyalanamadı"), ok);
    };
    try {
      navigator.clipboard.writeText(sourceText)
        .then(() => done(t("Kopyalandı ✓"), true), fallback);
    } catch {
      fallback();
    }
  }

  function legacyCopy(text) {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    area.remove();
    return ok;
  }

  // Ajanın kurduğu sayfa gerçekten çalışsın diye çerçevede gösteriliyor ama
  // yalıtılmış: `allow-same-origin` verilmiyor, yani sayfa bu programın
  // DOM'una, çerezlerine ve `/api` uçlarına erişemiyor.
  function frame(html) {
    const node = document.createElement("iframe");
    node.className = "viewer-frame";
    node.setAttribute("sandbox", "allow-scripts");
    node.setAttribute("referrerpolicy", "no-referrer");
    node.srcdoc = injectScrollCss(html);
    return node;
  }

  function liveFrame(url) {
    const node = document.createElement("iframe");
    node.className = "viewer-frame viewer-live";
    node.setAttribute("referrerpolicy", "no-referrer");
    // Canlı app kendi origin'inde: API çağrıları çalışsın.
    node.setAttribute("sandbox",
      "allow-scripts allow-forms allow-same-origin allow-popups allow-downloads");
    node.src = url;
    return node;
  }

  const isPage = (path) => /\.html?$/i.test(path || "");

  // Uzantı → vurgulayıcı dili. PHP'nin burada olmaması, PHP dosyalarını
  // renksiz düz metin yapıyordu; harita genişletildi.
  const EXT = { py: "python", js: "javascript", mjs: "javascript", jsx: "javascript",
                ts: "typescript", tsx: "typescript", ps1: "powershell",
                psm1: "powershell", sh: "bash", bash: "bash", bat: "bash",
                json: "json", jsonl: "json", css: "css", scss: "css", less: "css",
                html: "html", htm: "html", xml: "xml", svg: "svg",
                sql: "sql", yml: "yaml", yaml: "yaml", toml: "toml", ini: "toml",
                cfg: "toml", php: "php", phtml: "php", c: "c", h: "c",
                cpp: "cpp", hpp: "cpp", cc: "cpp", cs: "cs", go: "go",
                rs: "rust", java: "java", rb: "ruby", lua: "lua",
                kt: "kotlin", swift: "swift" };

  const language = (path) => EXT[(path.split(".").pop() || "").toLowerCase()] || "";

  // --- bağlama -----------------------------------------------------------

  document.getElementById("eye").addEventListener("click", toggle);
  document.getElementById("viewer-close").addEventListener("click", close);

  // Panel kenarından sürükleyip genişletme. Tek sağ sütun genişliği
  // `--mind-w-user` (beyin tutamacıyla aynı): sohbet `--right-w` ile kayar.
  (() => {
    const grip = document.getElementById("viewer-grip");
    if (!grip) return;
    const MIN = 240;
    const root = document.documentElement;
    let active = false;
    let originX = 0;
    let originW = 0;

    const width = () => {
      const col = document.getElementById("right-col");
      return (col || panel).getBoundingClientRect().width;
    };

    const move = (e) => {
      if (!active) return;
      // Sağ kenar sabit: sola çekince sütun genişler (origin delta).
      // Tavan mind-grip / CSS ile aynı — 420/32vw yalnız küçültmeye izin
      // veriyordu (canlı, 01.09).
      const max = Math.min(760, window.innerWidth * 0.55);
      const w = Math.max(MIN, Math.min(max, originW + originX - e.clientX));
      root.style.setProperty("--mind-w-user", Math.round(w) + "px");
    };

    const stop = () => {
      active = false;
      document.body.classList.remove("viewer-resize");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      window.removeEventListener("blur", stop);
      try {
        const w = parseInt(getComputedStyle(root).getPropertyValue("--mind-w-user"), 10);
        if (w) localStorage.setItem("dornick-mind-w", String(w));
      } catch { /* dosya:// */ }
    };

    grip.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      active = true;
      originX = e.clientX;
      originW = width();
      try { grip.setPointerCapture(e.pointerId); } catch { /* eski motor */ }
      window.addEventListener("pointercancel", stop);
      window.addEventListener("blur", stop);
      root.style.setProperty("--mind-w-user", Math.round(originW) + "px");
      document.body.classList.add("viewer-resize");
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", stop);
    });
  })();

  // Uygulama içi bir yolu kullanıcının GERÇEK tarayıcısında açar. Adresi
  // (gerçek portu) sunucu kurar — ajanın 8765 tahmini canlıda "bağlantı
  // reddedildi" ile bitmişti; pencere içinde window.open da güvenilmez.
  async function openOutside(path) {
    const p = String(path || "");
    if (!p.startsWith("/")) { window.open(p, "_blank", "noopener"); return; }
    let out = null;
    try {
      out = await (await fetch("/api/disari-ac", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: p }),
      })).json();
    } catch { /* sunucu cevap vermedi */ }
    if (!out || !out.ok) {
      if (typeof say === "function") say(t("Açılamadı") + (out && out.error ? ": " + out.error : ""), true);
    }
  }

  // Canlı sayfa: gerçek tarayıcıda aç + indir + yazdır.
  function pageExportActs(url) {
    const wrap = el("span", "viewer-export");
    const base = String(url).split("?")[0];
    const disari = el("button", "viewer-act", t("Tarayıcıda aç"));
    disari.type = "button";
    disari.title = t("Gerçek tarayıcıda aç");
    disari.addEventListener("click", (ev) => { ev.stopPropagation(); openOutside(base); });
    const dl = el("button", "viewer-act", t("İndir"));
    dl.type = "button";
    dl.title = t("İndir") + " (.html)";
    dl.addEventListener("click", (ev) => {
      ev.stopPropagation();
      downloadArtifact(base).catch((err) => {
        if (typeof say === "function") say(String(err.message || err), true);
      });
    });
    const pr = el("button", "viewer-act", t("Yazdır / PDF"));
    pr.type = "button";
    pr.addEventListener("click", (ev) => {
      ev.stopPropagation();
      printPage(base);
    });
    wrap.append(disari, dl, pr);
    return wrap;
  }

  async function downloadArtifact(url) {
    const base = String(url || "").split("?")[0];
    if (!base) throw new Error(t("Adres yok"));
    // Artifact: dosyayı SUNUCU kaydeder (İndirilenler) ve tam yol söylenir.
    // Pencere WebView2'de blob + <a download> sessizce ölüyordu; bu yol hem
    // pencerede hem tarayıcıda aynı ve kullanıcı dosyanın NEREDE olduğunu
    // görüyor ("indiremiyorum / yolu göremiyorum" canlı yarası).
    if (/^\/artifact\//.test(base)) {
      let out = null;
      try {
        out = await (await fetch("/api/artifact/indir", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: base }),
        })).json();
      } catch { /* sunucu cevap vermedi; blob yoluna düş */ }
      if (out && out.ok && out.path) {
        if (typeof say === "function") say(t("İndirildi") + ": " + out.path);
        return;
      }
      if (out && out.error) throw new Error(out.error);
    }
    const res = await fetch(base + (base.includes("?") ? "&" : "?") + "download=1",
                            { cache: "no-store" });
    if (!res.ok) throw new Error(t("İndirilemedi") + " (" + res.status + ")");
    const blob = await res.blob();
    let name = "download.html";
    const cd = res.headers.get("Content-Disposition") || "";
    const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
    const plain = /filename="?([^";]+)"?/i.exec(cd);
    if (star) {
      try { name = decodeURIComponent(star[1].trim()); } catch { name = star[1].trim(); }
    } else if (plain) {
      name = plain[1].trim();
    }
    const href = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = href;
    a.download = name;
    a.rel = "noopener";
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(href), 2000);
  }

  function printPage(url) {
    const base = String(url || "").split("?")[0];
    if (!base) return;
    fetch(base, { cache: "no-store" })
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.text(); })
      .then((html) => {
        const blob = new Blob([injectScrollCss(html)], { type: "text/html;charset=utf-8" });
        const href = URL.createObjectURL(blob);
        const iframe = document.createElement("iframe");
        iframe.setAttribute("aria-hidden", "true");
        iframe.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;opacity:0";
        iframe.onload = () => {
          try { iframe.contentWindow.focus(); iframe.contentWindow.print(); }
          catch { /* pywebview / sandbox */ }
          setTimeout(() => { iframe.remove(); URL.revokeObjectURL(href); }, 1500);
        };
        iframe.src = href;
        document.body.append(iframe);
      })
      .catch((err) => {
        if (typeof say === "function") say(t("Yazdırılamadı") + ": " + (err.message || err), true);
      });
  }

  function injectScrollCss(html) {
    const css = "<style id=\"dornick-scroll-theme\">"
      + "html{scrollbar-width:thin;scrollbar-color:rgba(240,160,32,.35) transparent}"
      + "::-webkit-scrollbar{width:8px;height:8px}"
      + "::-webkit-scrollbar-thumb{background:rgba(240,160,32,.3);border-radius:4px}"
      + "::-webkit-scrollbar-track{background:transparent}"
      + "</style>";
    const src = String(html || "");
    if (/<\/head>/i.test(src)) return src.replace(/<\/head>/i, css + "</head>");
    if (/<html[\s>]/i.test(src)) {
      return src.replace(/<html[^>]*>/i, (m) => m + "<head>" + css + "</head>");
    }
    return css + src;
  }

  function bootDesk() {
    if (innerWidth < 1021) return;
    try { if (localStorage.getItem(DESK) === "off") return; } catch { /* */ }
    openPin("desk:term");
  }
  bootDesk();
  window.addEventListener("resize", () => {
    if (innerWidth >= 1021 && panel.hidden && !dismissed &&
        (function wanted() {
          try { return localStorage.getItem(DESK) !== "off"; } catch { return true; }
        })()) {
      openPin("desk:term");
    }
  });

  return { present, page, showing, watch, refresh, show, open, close, toggle,
           host, hosted, hostedGoals, setGoalsPin, downloadArtifact, printPage,
           openOutside, feed, openPin };
})();

// Büyüt / yerine dön: görüntüleyici sağ bölgenin tamamını kaplar (beyin
// geçici çekilir); tekrar basınca dock düzenine döner. Sahne kapanışta
// kendini yeniden ölçüyor (mindRect her karede taze).
(() => {
  const dugme = document.getElementById("viewer-max");
  if (!dugme) return;
  dugme.addEventListener("click", () => {
    document.body.classList.toggle("viewer-max");
  });
})();

(() => {
  const add = document.getElementById("viewer-add");
  if (!add) return;
  add.title = t("Yeni terminal");
  add.setAttribute("aria-label", t("Yeni terminal"));
  add.addEventListener("click", () => {
    if (typeof Viewer !== "undefined" && Viewer.openPin) Viewer.openPin("desk:term");
  });
})();
