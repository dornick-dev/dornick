// Uygulamalar paneli: ajanın atölyede ürettiği şeyleri çalıştırılabilir
// bir katalog olarak gösterir.
//
// Sohbette "bir pano kurdum" cümlesini okumakla o panoyu açıp kullanmak
// aynı şey değil. Panel projeleri KAPSAMA göre iki grupta çizer —
//
//   Sistem içi   neo'nun içinde (kapsülde) yaşayan uygulamalar
//   Dış          kendi başına çalışan ayrı uygulamalar
//
// — üstte de o an çalışanlar. Her kart ne olduğunu (tür rozeti), ne
// yaptığını (tek cümle özet) ve durumunu (yeşil nokta = çalışıyor) taşır.
// Arama kutusu ve tür süzgeci kalabalık atölyede aranan şeyi bulur.
//
// Kaynak `/api/projects`; sınıflama sunucuda, burada yalnızca çizim var.

const Apps = (() => {
  const panel = document.getElementById("apps-panel");
  const body = document.getElementById("apps-body");

  let loaded = false;
  const folded = new Set();   // kapalı kapsam grupları
  let all = [];               // son okunan projeler
  let procs = [];             // son okunan çalışanlar
  let query = "";             // arama metni
  let kindFilter = "";        // "" | web | service | tool | doc

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  // Proje türü → simge ve etiket.
  const PKIND = {
    web: { glyph: "◈", tag: "web" },
    service: { glyph: "⧉", tag: "servis" },
    tool: { glyph: "▶", tag: "araç" },
    doc: { glyph: "≡", tag: "belge" },
  };
  // Kapsam rozeti: sistem içi mi (neo'nun içinde), dış mı (kendi başına).
  const SCOPE = {
    "in-app": { label: "sistem içi", cls: "inapp" },
    external: { label: "dış", cls: "ext" },
    "": { label: "belirsiz", cls: "unknown" },
  };

  // --- arama + süzgeç ---------------------------------------------------

  const search = document.getElementById("apps-search");
  const chips = document.getElementById("apps-chips");

  if (search) {
    search.addEventListener("input", () => { query = search.value.trim(); render(); });
  }
  if (chips) {
    const KINDS = [["", "Tümü"], ["web", "Web"], ["service", "Servis"],
                   ["tool", "Araç"], ["doc", "Belge"]];
    for (const [key, label] of KINDS) {
      const chip = el("button", "apps-chip" + (key === "" ? " on" : ""), label);
      chip.dataset.kind = key;
      chip.onclick = () => {
        kindFilter = key;
        chips.querySelectorAll(".apps-chip").forEach((c) =>
          c.classList.toggle("on", c === chip));
        render();
      };
      chips.append(chip);
    }
  }

  function matches(p) {
    if (kindFilter && (p.kind || "doc") !== kindFilter) return false;
    if (!query) return true;
    const hay = [p.name, p.desc, p.howto, p.path, p.run]
      .join(" ").toLocaleLowerCase("tr");
    return query.toLocaleLowerCase("tr").split(/\s+/)
      .every((w) => hay.includes(w));
  }

  // --- yükleme ---------------------------------------------------------

  async function load() {
    body.textContent = "";
    await drawRunning();   // çalışanlar en üstte, projelerden önce
    drawArts();            // artifact'lar: kalıcı sayfalar, katalogdan önce
    try {
      all = (await (await fetch("/api/projects")).json()).projects || [];
    } catch {
      body.append(el("p", "apps-blank", "Okunamadı"));
      return;
    }
    loaded = true;
    render();
  }

  // Projeleri (çalışanlar bölümüne dokunmadan) baştan çizer. Arama ve
  // süzgeç her tuşta burayı çağırıyor; çalışanlar kendi yoklamasında.
  function render() {
    body.querySelectorAll(".apps-catalog").forEach((n) => n.remove());
    const box = el("div", "apps-catalog");
    body.append(box);

    if (!all.length) {
      if (!procs.length) {
        box.append(el("p", "apps-blank",
          "Atölye henüz boş. neo bir proje ürettiğinde burada bir kart olarak belirir."));
      }
      return;
    }
    const found = all.filter(matches);
    if (!found.length) {
      box.append(el("p", "apps-blank", "Aramana uyan uygulama yok."));
      return;
    }
    // KAPSAMA göre gruplu: sistem içi olanlar neo'nun içinde (kapsülde)
    // yaşar; dış olanlar kendi başına ayrı uygulamalardır; belirsizler
    // neo'nun kapsam sorusunu bekler.
    const groups = [
      { key: "in-app", title: "Sistem içi", hint: "neo'nun içinde çalışır" },
      { key: "external", title: "Dış uygulamalar", hint: "kendi başına çalışır" },
      { key: "", title: "Belirsiz", hint: "kapsamı sorulmadı — neo'ya sorabilirsin" },
    ];
    for (const g of groups) {
      const items = found.filter((p) => (p.scope || "") === g.key);
      if (!items.length) continue;
      // Arama varken gruplar hep açık: kullanıcı bir şey arıyor, kapalı
      // grubun içindeki eşleşmeyi saklamak aramayı işe yaramaz yapar.
      const isOpen = !!query || !folded.has(g.key);
      const head = el("div", "apps-group scope-" + (g.key || "unknown"));
      head.append(el("span", "apps-fold", isOpen ? "▾" : "▸"));
      head.append(el("span", null, g.title));
      head.append(el("i", "apps-group-hint", g.hint));
      head.append(el("b", "apps-group-count", String(items.length)));
      const groupBody = el("div", "apps-group-body");
      groupBody.hidden = !isOpen;
      head.style.cursor = "pointer";
      head.onclick = () => {
        isOpen ? folded.add(g.key) : folded.delete(g.key);
        render();
      };
      box.append(head, groupBody);
      for (const p of items) groupBody.append(projectCard(p));
    }
    markCards();
  }

  // Bir proje kartı: ad, tür rozeti, kapsam rozeti, ana eylem
  // (Çalıştır/Aç/Durdur) ve tıklanınca açılan proje görünümü.
  function projectCard(p) {
    const wrap = el("div", "proj");
    wrap.dataset.path = p.path || "";
    wrap.dataset.entry = p.entry || "";
    const head = el("div", "proj-head " + p.kind);
    const meta = PKIND[p.kind] || PKIND.doc;
    head.append(el("span", "proj-glyph", meta.glyph));
    head.append(el("span", "proj-dot"));   // çalışıyor işareti (CSS gösterir)
    head.append(el("span", "proj-name", p.name));
    head.append(el("span", "proj-kind-tag " + p.kind, meta.tag));
    const scope = SCOPE[p.scope] || SCOPE[""];
    head.append(el("span", "proj-scope " + scope.cls, scope.label));

    const act = el("button", "proj-run", runnable(p) ? "Çalıştır" : "Aç");
    if (!runnable(p)) act.dataset.open = "1";
    act.onclick = (ev) => {
      ev.stopPropagation();
      const r = runningOf(p);
      if (r) stopProc(r); else launchProject(p);
    };
    head.append(act);

    head.onclick = () => toggleView(p, wrap);
    wrap.append(head);
    // Tek cümlelik özet: bu uygulama NE YAPAR. "Çalıştır'a bastım ama ne
    // olduğunu bilmiyorum" tam da bu satırın yokluğuydu. app.json'daki
    // `desc`ten, yoksa README/docstring ilk satırından geliyor.
    wrap.append(el("div", "proj-desc" + (p.desc ? "" : " empty"),
      p.desc || "Açıklama yok — neo'ya sorup app.json'a yazdırabilirsin."));
    return wrap;
  }

  const runnable = (p) => !!(p.run || p.kind === "service" || p.kind === "tool");

  // Bu projenin çalışan bir süreci var mı? (süreç defteri proje yolunu
  // ya da giriş dosyasını taşıyor olabilir — ikisine de bakılıyor)
  function runningOf(p) {
    return procs.find((r) =>
      r.path === p.path || (p.entry && r.path === p.entry)) || null;
  }

  // Kartlardaki canlı durumu tazeler: yeşil nokta + Durdur düğmesi.
  // Kartları baştan çizmek yerine yerinde işaretleniyor — açık proje
  // görünümü ve arama odağı bozulmasın.
  function markCards() {
    body.querySelectorAll(".proj").forEach((w) => {
      const r = procs.find((q) =>
        q.path === w.dataset.path || (w.dataset.entry && q.path === w.dataset.entry));
      w.classList.toggle("running", !!r);
      const act = w.querySelector(".proj-run");
      if (act) {
        act.textContent = r ? "Durdur" : (act.dataset.open === "1" ? "Aç" : "Çalıştır");
        act.classList.toggle("stop", !!r);
      }
    });
  }

  // Proje görünümü: README/nasıl-çalıştır + eylemler + canlı durum.
  function toggleView(p, wrap) {
    const open = wrap.querySelector(".proj-view");
    if (open) { open.remove(); return; }
    body.querySelectorAll(".proj-view").forEach((n) => n.remove());

    const view = el("div", "proj-view");

    // Canlı durum: çalışıyorsa adresi ve süresi burada da görünsün.
    const r = runningOf(p);
    if (r) {
      const live = el("div", "proj-live");
      live.append(el("span", "apps-proc-dot"));
      live.append(el("span", null, "Çalışıyor" + (r.pid ? " · PID " + r.pid : "")));
      if (r.address) {
        const link = el("button", "apps-proc-addr", r.address);
        link.onclick = () => {
          if (typeof Capsule !== "undefined") {
            Capsule.open({ name: p.name, pid: r.pid, address: r.address, started: r.started });
            close();
          } else window.open(r.address, "_blank", "noopener");
        };
        live.append(link);
      }
      view.append(live);
    }

    // Nasıl çalıştırılır (README). Markdown varsa render, yoksa düz metin.
    if (p.howto) {
      const how = el("div", "proj-howto");
      if (typeof Markdown !== "undefined" && Markdown.into) Markdown.into(how, p.howto);
      else how.textContent = p.howto;
      view.append(el("div", "proj-howto-tag", "Nasıl çalıştırılır"), how);
    } else {
      view.append(el("p", "proj-howto empty", "README yok. neo'ya sorabilirsin."));
    }

    // Nerede olduğu + neyle çalıştığı: kullanıcı diskte bulabilsin,
    // komutu görebilsin. Yol zaten atolye/ ile gelebiliyor — bir daha
    // ekleyip "atolye/atolye/…" yazma.
    const rel = p.path || p.entry || "";
    view.append(el("p", "proj-path", rel.startsWith("atolye") ? rel : "atolye/" + rel));
    if (p.run) view.append(el("p", "proj-cmd", "» " + p.run));

    const row = el("div", "proj-actions");
    if (r) {
      const stopBtn = el("button", "proj-btn danger", "Durdur");
      stopBtn.onclick = () => stopProc(r);
      row.append(stopBtn);
    } else {
      const run = el("button", "proj-btn primary", runnable(p) ? "Çalıştır" : "Aç");
      run.onclick = () => launchProject(p);
      row.append(run);
    }

    // Sistem dışında aç: statik bir web sayfası server'sız, gerçek tarayıcıda
    // dosyadan tam çalışır — "içeride açıyor ama tarayıcıda da istiyorum".
    // YALNIZCA tarayıcının işi olanlarda: Word/Excel gibi belgeler bu düğmeyi
    // almaz — tarayıcıda açmaya çalışmak yanlış beklenti kurar.
    const inBrowser = /\.(html?|svg)$/i.test(p.entry || "");
    if (p.entry && inBrowser) {
      const ext = el("button", "proj-btn", "Tarayıcıda");
      ext.title = "Varsayılan tarayıcıda aç (server gerekmez)";
      ext.onclick = async () => {
        let res;
        try {
          res = await (await fetch("/api/apps/open", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: p.entry }),
          })).json();
        } catch { res = { ok: false, error: "Ulaşılamadı" }; }
        toast(res.ok ? p.name + " tarayıcıda açıldı" : (res.error || "Açılamadı"));
      };
      row.append(ext);
    }
    // "neo'ya sor: nasıl çalıştırırım" — projeyi bağlam olarak verir.
    if (typeof setAppContext === "function") {
      const ask = el("button", "proj-btn", "neo'ya sor");
      ask.title = "Bu projeyi konuşmanın bağlamına ver";
      ask.onclick = () => {
        setAppContext({ name: p.name, path: p.path, type: p.kind,
                        title: (p.desc || p.howto || "").slice(0, 120) });
        toast(p.name + " bağlama alındı");
        close();
      };
      row.append(ask);
    }

    // Sil: iki adımlı onay (yanlış tık bir projeyi götürmesin). Kalıcı
    // silmiyor — atölyedeki .geri-donusum klasörüne taşınıyor; elle geri
    // alınabilir.
    const del = el("button", "proj-btn danger", "Sil");
    del.onclick = async () => {
      if (!del.dataset.armed) {
        del.dataset.armed = "1";
        del.textContent = "Emin misin? Sil";
        setTimeout(() => { delete del.dataset.armed; del.textContent = "Sil"; }, 3500);
        return;
      }
      let res;
      try {
        res = await (await fetch("/api/apps/remove", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: p.path }),
        })).json();
      } catch { res = { ok: false, error: "Ulaşılamadı" }; }
      if (res.ok) {
        toast(p.name + " kaldırıldı (atolye/.geri-donusum içinde — geri alınabilir)");
        load();
      } else {
        toast(res.error || "Silinemedi — çalışıyorsa önce durdur");
      }
    };
    row.append(del);

    view.append(row);
    wrap.append(view);
  }

  // Projeyi başlat. Klasör projelerde PROJE YOLU gönderiliyor: sunucu
  // manifestin `run` komutunu (npm start, dotnet run...) projenin kendi
  // klasöründe çalıştırıyor — yalnızca Python betikleri değil. SİSTEM İÇİ
  // servis/web projeler sonucu neo'nun İÇİNDE bir kapsülde açar; dış proje
  // kendi penceresinde yaşar. Web/belge → görüntüleyici.
  async function launchProject(p) {
    if (runnable(p)) {
      const target = p.single ? (p.entry || p.path) : p.path;
      let res;
      try {
        res = await (await fetch("/api/apps/run", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: target }),
        })).json();
      } catch { toast(p.name + " başlatılamadı"); return; }
      if (!res.ok) { toast(res.error || "Başlatılamadı"); return; }
      if (res.already) { toast(p.name + " zaten çalışıyor"); drawRunning(); return; }
      drawRunning(); setTimeout(drawRunning, 1400);
      // Kapsül YALNIZCA servis/web projeler için: bir adres bağlamaları
      // beklenir, kapsül onu gömer. Tek seferlik bir betik (tool) sunucu
      // değildir — çalışır, işini yapar, çıkar; onu kapsülde "süreç durdu"
      // diye göstermek yanlıştı. Betik kendi konsolunda çalışır, toast yeter.
      const servesWeb = p.kind === "service" || p.kind === "web";
      if (servesWeb && p.scope !== "external" && typeof Capsule !== "undefined" && res.pid) {
        toast(p.name + " başlatıldı");
        Capsule.open({ name: p.name, pid: res.pid });
        close();
      } else {
        // Betik/dış uygulama: akıbetini söyle. "Kendi penceresinde çalışıyor"
        // tek başına bilgi vermiyordu — kullanıcı nerede bulacağını
        // bilmiyordu. Kısa bir süre sonra bak: hâlâ yaşıyorsa Çalışıyor
        // bölümünü işaret et, bittiyse bittiğini söyle.
        toast(p.name + " başlatıldı…");
        if (res.pid) {
          setTimeout(async () => {
            let alive = false;
            try {
              const data = await (await fetch("/api/apps/running")).json();
              alive = (data.running || []).some((q) => q.pid === res.pid);
            } catch { /* yoklanamadı: sessiz kal */ }
            toast(alive
              ? p.name + " çalışıyor — panelin üstünde Çalışıyor bölümünde"
              : p.name + " çalıştı ve tamamlandı");
            drawRunning();
          }, 2500);
        }
      }
      return;
    }
    // Çalıştırılamayan: web/belge → görüntüleyici.
    if (typeof Viewer !== "undefined" && p.entry) { Viewer.present(p.entry); close(); return; }
    // Giriş dosyası yok: sessiz kalma — kullanıcı "tıklıyorum, hiçbir şey
    // olmuyor" yaşamasın, ne yapabileceğini söyle.
    toast(p.name + ": açılacak giriş dosyası bulunamadı — \"neo'ya sor\" ile sorabilirsin");
  }

  // --- artifact'lar ----------------------------------------------------
  //
  // Ajanın yayınladığı kalıcı sayfalar (rapor, pano, görselleştirme).
  // Sohbetteki kart akıp gidebilir; galeri hepsini bir arada tutar:
  // aç (uygulama içi görüntüleyici) + sil (iki adımlı onay — sunucu
  // kalıcı silmez, çöpe taşır).

  const artAddress = (a) => "/artifact/" + a.id + "/";

  // ISO damgayı kısa yerel tarihe çevirir: "26.08 14:05".
  function artWhen(iso) {
    const d = new Date(iso || "");
    if (isNaN(d)) return "";
    return d.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit" })
      + " " + d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  }

  async function drawArts() {
    const old = body.querySelector(".apps-arts");
    if (old) old.remove();

    const sec = el("div", "apps-arts");
    const head = el("div", "apps-group", "Artifact'lar");
    head.append(el("i", "apps-group-hint", "kalıcı sayfalar"));
    const holder = el("div", "arts-body");
    holder.append(el("p", "apps-blank", "Yükleniyor…"));
    sec.append(head, holder);
    // Katalogdan önce, çalışanlardan sonra dursun.
    body.insertBefore(sec, body.querySelector(".apps-catalog"));

    let rows;
    try {
      rows = (await (await fetch("/api/artifacts")).json()).artifacts || [];
    } catch {
      holder.textContent = "";
      holder.append(el("p", "apps-blank", "Okunamadı"));
      return;
    }
    renderArts(holder, rows);
  }

  function renderArts(holder, rows) {
    holder.textContent = "";
    const count = holder.parentElement.querySelector(".apps-group b");
    if (count) count.remove();
    if (!rows.length) {
      holder.append(el("p", "apps-blank",
        "Henüz artifact yok. neo kalıcı bir rapor ya da pano yayınladığında burada belirir."));
      return;
    }
    holder.parentElement.querySelector(".apps-group")
      .append(el("b", "apps-group-count", String(rows.length)));
    for (const a of rows) holder.append(artRow(a, holder));
  }

  function artRow(a, holder) {
    const row = el("div", "arts-row");
    row.tabIndex = 0;
    row.setAttribute("role", "button");
    row.title = (a.title || a.id) + " — görüntüleyicide aç";

    // Simge app.js'teki artGlyphSvg'den (DOM API — işaretleme metni yok);
    // bir ihtimal yüklenmemişse düz karakter yedeği.
    const glyph = el("span", "arts-glyph");
    if (typeof artGlyphSvg === "function") glyph.append(artGlyphSvg());
    else glyph.textContent = "⬒";

    const main = el("div", "arts-main");
    main.append(el("div", "arts-name", a.title || a.id));
    main.append(el("div", "arts-meta",
      "v" + (a.surum || 1) + (a.updated ? " · " + artWhen(a.updated) : "")));

    const openArt = () => {
      if (typeof Viewer !== "undefined" && Viewer.page) {
        Viewer.page(artAddress(a), a.title || a.id);
        close();
      } else {
        window.open(artAddress(a), "_blank", "noopener");
      }
    };

    const openBtn = el("button", "arts-btn", "Aç");
    openBtn.onclick = (ev) => { ev.stopPropagation(); openArt(); };

    // Sil: iki adımlı onay — yanlış tık bir teslimatı götürmesin. Sunucu
    // kalıcı silmiyor, çöpe taşıyor; yine de niyet sorulur.
    const del = el("button", "arts-btn danger", "Sil");
    del.onclick = async (ev) => {
      ev.stopPropagation();
      if (!del.dataset.armed) {
        del.dataset.armed = "1";
        del.textContent = "Emin misin?";
        setTimeout(() => { delete del.dataset.armed; del.textContent = "Sil"; }, 3500);
        return;
      }
      let res;
      try {
        res = await (await fetch("/api/artifacts", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "remove", id: a.id }),
        })).json();
      } catch { res = { ok: false, error: "Ulaşılamadı" }; }
      if (res.ok) {
        toast((a.title || a.id) + " kaldırıldı (çöpe taşındı — geri alınabilir)");
        renderArts(holder, res.artifacts || []);
      } else {
        toast(res.error || "Silinemedi");
      }
    };

    row.append(glyph, main, openBtn, del);
    row.onclick = openArt;
    row.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openArt(); }
    });
    return row;
  }

  // --- çalışan uygulamalar --------------------------------------------
  //
  // Ajan bir betik/sunucu başlattıysa burada canlı görünüyor: bir web
  // sunucusu bağladıysa adresi tıklanınca kapsülde açılıyor, her biri
  // durdurulabiliyor. Panel açıkken periyodik yoklanıyor; kartlardaki
  // yeşil noktalar da aynı yoklamayla tazeleniyor.

  let pollTimer = null;

  const mmss = (started) => {
    if (!started) return "";
    const s = Math.max(0, Math.floor(Date.now() / 1000 - started));
    const m = Math.floor(s / 60);
    return m ? `${m} dk ${s % 60} sn` : `${s} sn`;
  };

  async function drawRunning() {
    try {
      const data = await (await fetch("/api/apps/running")).json();
      procs = data.running || [];
    } catch { procs = []; }

    const old = body.querySelector(".apps-running");
    if (old) old.remove();
    markCards();
    if (!procs.length) return;

    const sec = el("div", "apps-running");
    sec.append(el("div", "apps-group", "Çalışıyor"));
    for (const p of procs) {
      const r = el("div", "apps-proc");
      r.append(el("span", "apps-proc-dot"));
      const name = el("span", "apps-proc-name", p.name);
      name.title = (p.run || p.path || "") + (p.started ? " · " + mmss(p.started) : "");
      r.append(name);
      r.append(el("span", "apps-proc-time", mmss(p.started)));
      if (p.address) {
        // Canlı sunucu: sistem içinde kapsülde aç (neo'nun içinde). Kapsülün
        // kendi "dışarıda aç" düğmesi ayrı sekme isteyene duruyor.
        const link = el("button", "apps-proc-addr", p.address);
        link.title = "Sistem içinde aç (kapsül)";
        link.onclick = () => {
          if (typeof Capsule !== "undefined") {
            Capsule.open({ name: p.name, pid: p.pid, address: p.address, started: p.started });
            close();
          } else window.open(p.address, "_blank", "noopener");
        };
        r.append(link);
      }
      const stop = el("button", "apps-proc-stop", "Durdur");
      stop.onclick = () => stopProc(p);
      r.append(stop);
      sec.append(r);
    }
    // Katalog zaten çizildiyse en başa, değilse tek başına.
    body.insertBefore(sec, body.firstChild);
  }

  // Durdur ve SONUCU söyle. Eski hal cevaba bakmadan "durduruldu" diyordu;
  // süreç inmemişse kullanıcı "durdur diyorum durmuyor" yaşıyordu.
  async function stopProc(p) {
    let res;
    try {
      res = await (await fetch("/api/apps/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pid: p.pid }),
      })).json();
    } catch { res = { ok: false, error: "Ulaşılamadı" }; }
    toast(res.ok ? (p.name || "süreç") + " durduruldu"
                 : (res.error || "Durdurulamadı"));
    drawRunning();
  }

  // Kısa bir bildirim: başlatılan bir betiğin kendi penceresi var, ama
  // "başladı" geri bildirimi arayüzde de görünmeli.
  let toastTimer = null;
  function toast(text) {
    let bar = document.getElementById("apps-toast");
    if (!bar) {
      bar = el("div", "apps-toast");
      bar.id = "apps-toast";
      document.body.append(bar);
    }
    bar.textContent = text;
    bar.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => bar.classList.remove("show"), 2600);
  }

  // --- panel -----------------------------------------------------------

  function toggle() {
    if (panel.hidden) {
      if (typeof History !== "undefined") History.close();  // iki sol panel çakışmasın
      panel.hidden = false;
      document.body.classList.add("apps-open");
      if (!loaded) load(); else { render(); drawRunning(); drawArts(); }
      // Çalışanları panel açıkken canlı tut (canlı adres gecikmeli belirir,
      // süreç kendi kendine bitebilir). Kapanınca yoklamayı durduruyoruz.
      clearInterval(pollTimer);
      pollTimer = setInterval(drawRunning, 4000);
    } else {
      close();
    }
  }

  function close() {
    panel.hidden = true;
    document.body.classList.remove("apps-open");
    clearInterval(pollTimer);
    pollTimer = null;
  }

  document.getElementById("apps").addEventListener("click", toggle);
  document.getElementById("apps-close").addEventListener("click", close);
  document.getElementById("apps-refresh").addEventListener("click", load);

  return { toggle, close, load };
})();
