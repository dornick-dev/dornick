// Uygulamalar paneli: ajanın atölyede ürettiği şeyleri çalıştırılabilir
// bir katalog olarak gösterir.
//
// Sohbette "bir pano kurdum" cümlesini okumakla o panoyu açıp kullanmak
// aynı şey değil. Panel projeleri KAPSAMA göre iki grupta çizer —
//
//   Sistem içi   Dornick'in içinde (kapsülde) yaşayan uygulamalar
//   Dış          kendi başına çalışan ayrı uygulamalar
//
// — üstte de o an çalışanlar. Her kart ne olduğunu (tür rozeti), ne
// yaptığını (tek cümle özet) ve durumunu (yeşil nokta = çalışıyor) taşır.
// Arama kutusu ve tür süzgeci kalabalık atölyede aranan şeyi bulur.
//
// Kaynak `/api/projects`; sınıflama sunucuda, burada yalnızca çizim var.

// Bu dosyanın kullanıcıya gösterdiği metinlerin İngilizceleri. Kaynak metin
// Türkçe kalıyor; görüntüleme noktasında t("...") ile çevriliyor.
Dil.ekle({
  "Aç": "Open",
  "Başlat": "Start",
  "Durdur": "Stop",
  "Klasörü göster": "Show folder",
  "Durduruluyor…": "Stopping…",
  "Arşivle": "Archive",
  "çalışıyor": "running",
  "durdu": "stopped",
  "eksik": "incomplete",
  "web": "web",
  "servis": "service",
  "betik": "script",
  "belge": "document",
  "sistem içi": "in-app",
  "dış": "external",
  "belirsiz": "unsorted",
  "Tümü": "All",
  "Web": "Web",
  "Servis": "Service",
  "Betik": "Script",
  "Belge": "Document",
  "Sistem içi": "In-app",
  "Dış uygulamalar": "External apps",
  "Belirsiz": "Unsorted",
  "Sorunlu manifestler": "Broken manifests",
  "Dornick'in içinde çalışır": "runs inside Dornick",
  "kendi başına çalışır": "runs on its own",
  "kapsamı sorulmadı — Dornick'e sorabilirsin": "scope unknown — you can ask Dornick",
  "yanlış yere yazılmış — uygulama sayılmadı":
    "written in the wrong place — not counted as an app",
  "toplu temizlik: artık kullanmadıklarını Arşivle ile kaldırabilirsin":
    "bulk cleanup: archive the ones you no longer use",
  "Henüz uygulama yok — Dornick bir şey üretince burada belirir.":
    "No apps yet — anything Dornick builds will show up here.",
  "Aramana uyan uygulama yok.": "Nothing matches your search.",
  "Okunamadı": "Could not read",
  "Ulaşılamadı": "Unreachable",
  "arşivlendi (atolye/.geri-donusum içinde — geri alınabilir)":
    "archived (in atolye/.geri-donusum — recoverable)",
  "Arşivlenemedi — çalışıyorsa önce durdur":
    "Could not archive — stop it first if it is running",
  "Dornick (kendisi)": "Dornick (itself)",
  "Dornick'in kendi süreci — panelden durdurulmuyor":
    "Dornick's own process — not stoppable from the panel",
  "Açıklama yok — Dornick'e sorup app.json'a yazdırabilirsin.":
    "No description — you can ask Dornick to write one into app.json.",
  "Bu uygulamanın klasörünü dosya gezgininde aç":
    "Open this app's folder in the file explorer",
  "Emin misin?": "Are you sure?",
  "Açılacak giriş dosyası bulunamadı": "No entry file to open",
  "Bu uygulama arşivlensin mi? atolye/.geri-donusum içine taşınır.":
    "Archive this app? It moves into atolye/.geri-donusum.",
});

const Apps = (() => {
  const panel = document.getElementById("apps-panel");
  const body = document.getElementById("apps-body");

  const folded = new Set();   // kapalı kapsam grupları
  let all = [];               // son okunan projeler
  let procs = [];             // son okunan çalışanlar
  let query = "";             // arama metni
  let kindFilter = "";        // "" | web | service | tool | doc
  let sorunlar = [];          // yanlış yere yazılmış manifestler

  // Metin her zaman t()'den geçiyor: kaynak Türkçe, görüntü kullanıcının
  // diline göre. (Dil eşlemede yoksa Türkçesi kalıyor — eksik çeviri göze
  // batsın diye.)
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = (typeof t === "function") ? t(text) : text;
    return node;
  };

  // Panelin KENDİ stilleri panelle birlikte duruyor: rozetler, sorunlu
  // bölümü, eylem sırası. Ana sayfa yaprağını (app.css) şişirmeden
  // uygulamalar paneli kendi görünümünü taşıyor.
  (function stil() {
    if (document.getElementById("apps-ek-stil")) return;
    const s = document.createElement("style");
    s.id = "apps-ek-stil";
    s.textContent = `
/* Rozetler, neden, adres ve eylemler açıklama satırıyla AYNI hizada
   (soldan 30px): kart tek bir sütun gibi okunsun. */
.proj-badges {
  display: flex; gap: 5px; align-items: center; flex-wrap: wrap;
  margin: 0 8px 6px 30px;
}
.proj-name { flex: 1 1 auto; min-width: 0; }
.proj-state {
  font: 9px/1.5 var(--mono); letter-spacing: .04em; text-transform: uppercase;
  padding: 1px 6px; border-radius: 999px; white-space: nowrap;
}
.proj-state.live { color: var(--mint); background: #86EFAC18; box-shadow: inset 0 0 0 1px #86EFAC40; }
.proj-state.idle { color: var(--dim); background: var(--raise); }
.proj-state.gap  { color: var(--amber); background: #F0A02018; box-shadow: inset 0 0 0 1px #F0A02040; }
.proj-why {
  font: 10px/1.5 var(--mono); color: var(--amber); margin: 0 8px 6px 30px;
  overflow-wrap: anywhere;
}
.proj-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.proj .proj-actions { margin: 0 8px 10px 30px; }
.proj-view .proj-actions { margin-top: 8px; }
.proj-addr {
  font: 10px var(--mono); color: var(--mint); background: none; border: 0;
  cursor: pointer; padding: 0; margin: 0 8px 6px 30px; display: block;
  text-align: left; overflow-wrap: anywhere;
}
.proj-addr:hover { text-decoration: underline; }
.apps-group-hint.tidy { color: var(--amber); }
.apps-sorun { margin: 6px 4px 12px; }
.apps-sorun-row {
  padding: 7px 9px; margin: 5px 0; border-radius: 7px;
  background: #F0A0200d; box-shadow: inset 0 0 0 1px #F0A02033;
}
.apps-sorun-name { font: 11px var(--mono); color: var(--amber); }
.apps-sorun-why { font-size: 11px; color: var(--dim); margin-top: 3px; line-height: 1.5; }
.apps-sorun-fix { font: 10px var(--mono); color: var(--faint); margin-top: 5px; line-height: 1.55; }
.apps-proc.self .apps-proc-dot { background: var(--faint); animation: none; }
.apps-proc-self-note { font: 9px var(--mono); color: var(--faint); flex: 0 0 auto; }
`;
    document.head.append(s);
  })();

  // Proje türü → simge ve etiket.
  const PKIND = {
    web: { glyph: "◈", tag: "web" },
    service: { glyph: "⧉", tag: "servis" },
    desktop: { glyph: "▣", tag: "masaüstü" },
    tool: { glyph: "▶", tag: "betik" },
    doc: { glyph: "≡", tag: "belge" },
  };
  // Kapsam rozeti: sistem içi mi (Dornick'in içinde), dış mı (kendi başına).
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
    const KINDS = [["", "Tümü"], ["web", "Web"], ["desktop", "Masaüstü"],
                   ["service", "Servis"], ["tool", "Betik"], ["doc", "Belge"]];
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
      const data = await (await fetch("/api/projects")).json();
      all = data.projects || [];
      sorunlar = data.sorunlar || [];
    } catch {
      body.append(el("p", "apps-blank", "Okunamadı"));
      return;
    }
    render();
  }

  // Projeleri (çalışanlar bölümüne dokunmadan) baştan çizer. Arama ve
  // süzgeç her tuşta burayı çağırıyor; çalışanlar kendi yoklamasında.
  function render() {
    body.querySelectorAll(".apps-catalog").forEach((n) => n.remove());
    const box = el("div", "apps-catalog");
    body.append(box);

    // Solo: yalnız seçilen uygulamanın kartı, detayı AÇIK. Katalog, arama,
    // çalışanlar ve gruplar yok — liste zaten kenar çubuğunda.
    panel.classList.toggle("apps-solo", !!solo);
    if (solo) {
      const p = all.find((x) => x.name === solo);
      if (p) {
        const geri = el("button", "apps-solo-back", "← Tüm uygulamalar");
        geri.onclick = () => { solo = ""; panel.classList.remove("apps-solo"); render(); };
        box.append(geri);
        const kart = projectCard(p);
        box.append(kart);
        toggleView(p, kart);   // detay görünümü baştan açık
        markCards();
        return;
      }
      // Uygulama artık yoksa (arşivlendi?) kataloga düş.
      solo = "";
      panel.classList.remove("apps-solo");
    }

    drawSorunlar(box);

    if (!all.length) {
      if (!procs.length && !sorunlar.length) {
        box.append(el("p", "apps-blank",
          "Henüz uygulama yok — Dornick bir şey üretince burada belirir."));
      }
      return;
    }
    const found = all.filter(matches);
    if (!found.length) {
      box.append(el("p", "apps-blank", "Aramana uyan uygulama yok."));
      return;
    }
    // KAPSAMA göre gruplu: sistem içi olanlar Dornick'in içinde (kapsülde)
    // yaşar; dış olanlar kendi başına ayrı uygulamalardır; belirsizler
    // Dornick'in kapsam sorusunu bekler.
    const groups = [
      { key: "in-app", title: "Sistem içi", hint: "Dornick'in içinde çalışır" },
      { key: "external", title: "Dış uygulamalar", hint: "kendi başına çalışır" },
      { key: "", title: "Belirsiz", hint: "kapsamı sorulmadı — Dornick'e sorabilirsin" },
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
      // Belirsiz kutusu kalabalıklaştığında (eski denemeler, aynı işin üç
      // kopyası) temizlik ipucu veriliyor: her kartta Arşivle var, bir
      // tıkla .geri-donusum'a taşınıyor ve geri alınabiliyor.
      const hint = (g.key === "" && items.length >= 8)
        ? "toplu temizlik: artık kullanmadıklarını Arşivle ile kaldırabilirsin"
        : g.hint;
      head.append(el("i", "apps-group-hint" + (hint === g.hint ? "" : " tidy"), hint));
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

  // Bir proje kartı. Kullanıcının bir bakışta cevabını istediği dört soru,
  // sırayla: NE (ad + tür rozeti), NE YAPAR (tek satır açıklama), NE
  // DURUMDA (çalışıyor / durdu / eksik) ve NE YAPABİLİRİM (Aç ·
  // Başlat/Durdur · Klasörü göster). Eskiden kartta yalnız tek bir
  // "Çalıştır" düğmesi vardı ve durum hiç yazmıyordu.
  function projectCard(p) {
    const wrap = el("div", "proj");
    wrap.dataset.path = p.path || "";
    wrap.dataset.entry = p.entry || "";
    const head = el("div", "proj-head " + p.kind);
    const meta = PKIND[p.kind] || PKIND.doc;
    head.append(el("span", "proj-glyph", meta.glyph));
    head.append(el("span", "proj-dot"));   // çalışıyor işareti (CSS gösterir)
    const name = el("span", "proj-name", p.name);
    name.title = p.name;
    head.append(name);
    head.onclick = () => toggleView(p, wrap);
    wrap.append(head);

    // Rozetler ADIN ALTINDA, kendi satırında. Panel dar (256px): rozetleri
    // ada yandaş dizmek adı sıfır genişliğe eziyordu — kullanıcı kartın
    // hangi uygulama olduğunu göremiyordu.
    const badges = el("div", "proj-badges");
    badges.append(el("span", "proj-kind-tag " + p.kind, meta.tag));
    // Durum rozeti: kartın en çok sorulan bilgisi. "eksik" olan uygulama
    // listeden DÜŞMÜYOR — nedeni altında yazıyor.
    const st = state(p);
    badges.append(el("span", "proj-state " + st.cls, st.label));
    const scope = SCOPE[p.scope] || SCOPE[""];
    badges.append(el("span", "proj-scope " + scope.cls, scope.label));
    wrap.append(badges);
    // Tek cümlelik özet: bu uygulama NE YAPAR. "Çalıştır'a bastım ama ne
    // olduğunu bilmiyorum" tam da bu satırın yokluğuydu. app.json'daki
    // `desc`ten, yoksa README/docstring ilk satırından geliyor.
    wrap.append(el("div", "proj-desc" + (p.desc ? "" : " empty"),
      p.desc || "Açıklama yok — Dornick'e sorup app.json'a yazdırabilirsin."));
    // Eksikse NEDENİ: "entry bulunamadı: static/index.html". Kullanıcı da
    // model de neyin yanlış olduğunu okuyabilsin.
    if (p.eksik && p.neden) wrap.append(el("p", "proj-why", p.neden));

    // Canlı adres kartın üstünde: çalışan bir uygulamaya ulaşmak için
    // kartı açmak gerekmesin.
    const live = liveOf(p);
    if (live && live.address) {
      const addr = el("button", "proj-addr", live.address);
      addr.onclick = (ev) => { ev.stopPropagation(); openLive(p, live); };
      wrap.append(addr);
    }

    wrap.append(actionRow(p, live, "card"));
    wrap.addEventListener("contextmenu", (ev) => appMenu(p, ev));
    return wrap;
  }

  // Kartın eylem sırası. Aynı satır proje görünümünde de kullanılıyor —
  // iki yerde iki farklı düğme kümesi olması kafa karıştırıyordu.
  function actionRow(p, live, where) {
    const row = el("div", "proj-actions");
    const stop = (ev) => ev.stopPropagation();

    // Aç: canlı adres, masaüstü (Başlat), ya da giriş dosyası.
    if ((live && live.address) || p.entry || p.kind === "desktop") {
      const open = el("button", "proj-btn primary", "Aç");
      open.onclick = (ev) => { stop(ev); openApp(p, live); };
      row.append(open);
    }
    // Başlat / Durdur: tek DİNAMİK düğme — tıklandığı ANIN durumuna göre
    // davranır ve 4 sn'lik yoklama etiketini tazeler (canlı şikâyet:
    // durum sayfa yenilenmeden değişmiyordu; düğme ilk çizimin
    // fotoğrafında kalıyordu).
    if (live || runnable(p)) {
      const st = el("button", "proj-btn act-run", "");
      const boya = () => {
        const kosan = liveOf(p) || (live && procs.some((q) => q.pid === live.pid) ? live : null);
        st.textContent = t(kosan ? "Durdur" : "Başlat");
        st.classList.toggle("danger", !!kosan);
        st.hidden = kosan ? kosan.stoppable === false : !runnable(p);
      };
      boya();
      st.onclick = (ev) => {
        stop(ev);
        const kosan = liveOf(p);
        if (kosan && kosan.stoppable !== false) stopProc(kosan);
        else if (!kosan && runnable(p)) launchProject(p);
        setTimeout(drawRunning, 800);
      };
      row.append(st);
    }
    // Klasörü göster: "nerede bu şey?" — kartta yol yazıyordu ama diskte
    // bulmak kullanıcının işiydi.
    const show = el("button", "proj-btn", "Klasörü göster");
    show.title = t("Bu uygulamanın klasörünü dosya gezgininde aç");
    show.onclick = async (ev) => { stop(ev); await revealApp(p); };
    row.append(show);

    // Arşivle yalnız kartta (proje görünümünde ayrıntılı "Sil" duruyor):
    // kapsamı belirsiz kalabalığı tek tıkla toparlamak için.
    if (where === "card" && !(p.scope || "")) {
      const arch = el("button", "proj-btn", "Arşivle");
      arch.onclick = (ev) => { stop(ev); archive(p, arch); };
      row.append(arch);
    }
    return row;
  }

  // Durum rozeti. Üç hal, üç renk: canlı (yeşil), durdu (gri), eksik (amber).
  function state(p) {
    if (liveOf(p)) return { cls: "live", label: "çalışıyor" };
    if (p.eksik) return { cls: "gap", label: "eksik" };
    return { cls: "idle", label: "durdu" };
  }

  const runnable = (p) => !!(p.run || p.kind === "service" || p.kind === "tool"
                             || p.kind === "desktop");

  // Bu projenin çalışan bir süreci var mı? İki kaynak: (1) çalışanlar
  // listesi (süreç defteri), (2) sunucunun kartın kendisine iliştirdiği
  // canlı bilgisi — Dornick yeniden başlatılmışsa süreç defterde yoktur ama
  // uygulama portunu dinlemeye devam eder.
  function liveOf(p) {
    const r = procs.find((q) =>
      q.path === p.path || (p.entry && q.path === p.entry));
    if (r) return r;
    if (p.address) {
      return { pid: p.pid, name: p.name, path: p.path,
               address: p.address, stoppable: p.stoppable !== false };
    }
    return null;
  }

  // "Aç": canlı adres → kapsül; masaüstü → Başlat (pencere); yoksa giriş.
  function openApp(p, live) {
    if (live && live.address) { openLive(p, live); return; }
    if (p.kind === "desktop" || (p.entry && /\.exe$/i.test(p.entry || ""))) {
      launchProject(p);
      return;
    }
    if (typeof Viewer !== "undefined" && p.entry) { Viewer.present(p.entry); close(); return; }
    toast(p.name + ": " + (p.neden || t("Açılacak giriş dosyası bulunamadı")));
  }

  // Kartlardaki canlı durumu tazeler: yeşil nokta + durum rozeti + eylem.
  // Kartları baştan çizmek yerine yerinde işaretleniyor — açık proje
  // görünümü ve arama odağı bozulmasın.
  function paintViewLive(view, p) {
    view.querySelector(".proj-live")?.remove();
    const r = liveOf(p) || procs.find((q) => q.path === (p.path || ""));
    if (!r) return;
    const live = el("div", "proj-live");
    live.append(el("span", "apps-proc-dot"));
    live.append(el("span", null, "Çalışıyor" + (r.pid ? " · PID " + r.pid : "")));
    if (r.address) {
      const link = el("button", "apps-proc-addr", r.address);
      link.onclick = () => openLive(p, r);
      live.append(link);
    }
    view.prepend(live);
  }

  function markCards() {
    body.querySelectorAll(".proj").forEach((w) => {
      const p = all.find((q) => (q.path || "") === w.dataset.path);
      const r = p ? liveOf(p) : procs.find((q) => q.path === w.dataset.path);
      w.classList.toggle("running", !!r);
      const badge = w.querySelector(".proj-state");
      if (badge && p) {
        const st = state(p);
        badge.className = "proj-state " + st.cls;
        badge.textContent = t(st.label);
      }
      // Kart + açık detay birlikte nefes alır: canlı satır ve
      // Başlat/Durdur etiketleri o anki gerçeğe çekilir.
      if (p) {
        const kosan = liveOf(p);
        w.querySelectorAll(".proj-btn.act-run").forEach((eylem) => {
          eylem.disabled = false;   // "Durduruluyor…" kilidi gerçek durumla çözülür
          eylem.textContent = t(kosan ? "Durdur" : "Başlat");
          eylem.classList.toggle("danger", !!kosan);
          eylem.hidden = kosan ? kosan.stoppable === false : !runnable(p);
        });
        const view = w.querySelector(".proj-view");
        if (view) paintViewLive(view, p);
      }
    });
  }

  function openLive(p, live) {
    if (typeof Capsule !== "undefined") {
      Capsule.open({ name: p.name, pid: live.pid, address: live.address,
                     started: live.started });
      close();
    } else window.open(live.address, "_blank", "noopener");
  }

  async function revealApp(p) {
    let res;
    try {
      res = await (await fetch("/api/apps/reveal", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: p.path || p.entry }),
      })).json();
    } catch { res = { ok: false, error: t("Ulaşılamadı") }; }
    if (!res.ok) toast(res.error || t("Ulaşılamadı"));
  }

  function appMenu(p, ev) {
    if (typeof Menu === "undefined") return;
    const live = liveOf(p);
    const maddeler = [];
    if ((live && live.address) || p.entry) {
      maddeler.push({ ad: "Aç", is: () => openApp(p, live) });
    }
    if (live && live.stoppable !== false) {
      maddeler.push({ ad: "Durdur", is: () => stopProc(live) });
    } else if (!live && runnable(p)) {
      maddeler.push({ ad: "Başlat", is: () => launchProject(p) });
    }
    maddeler.push({ ad: "Klasörü göster", is: () => revealApp(p) });
    maddeler.push({ ayrac: true });
    maddeler.push({ ad: "Arşivle", risk: true, is: () => archiveNow(p) });
    Menu.ac(ev, maddeler);
  }

  async function archiveNow(p) {
    if (!confirm(t("Bu uygulama arşivlensin mi? atolye/.geri-donusum içine taşınır."))) return;
    const fake = { dataset: { armed: "1" } };
    await archive(p, fake);
  }

  // Arşivle: .geri-donusum'a taşır (kalıcı silmez). İki adımlı onay —
  // yanlış tık bir projeyi götürmesin.
  async function archive(p, btn) {
    if (!btn.dataset.armed) {
      btn.dataset.armed = "1";
      btn.textContent = t("Emin misin?");
      setTimeout(() => { delete btn.dataset.armed; btn.textContent = t("Arşivle"); }, 3500);
      return;
    }
    let res;
    try {
      res = await (await fetch("/api/apps/remove", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: p.path }),
      })).json();
    } catch { res = { ok: false, error: t("Ulaşılamadı") }; }
    if (res.ok) {
      toast(p.name + " " + t("arşivlendi (atolye/.geri-donusum içinde — geri alınabilir)"));
      load();
      document.dispatchEvent(new Event("dornick-side-tazele"));
    } else {
      toast(res.error || t("Arşivlenemedi — çalışıyorsa önce durdur"));
    }
  }

  // Yanlış yere yazılmış manifestler. Sessizce yok saymak modeli de
  // kullanıcıyı da karanlıkta bırakıyordu ("uygulamayı yaptım ama panelde
  // yok"): burada NEDENİYLE ve DOĞRUSUYLA duruyorlar.
  function drawSorunlar(box) {
    if (!sorunlar.length) return;
    const sec = el("div", "apps-sorun");
    const head = el("div", "apps-group");
    head.append(el("span", null, "Sorunlu manifestler"));
    head.append(el("i", "apps-group-hint", "yanlış yere yazılmış — uygulama sayılmadı"));
    head.append(el("b", "apps-group-count", String(sorunlar.length)));
    sec.append(head);
    for (const s of sorunlar) {
      const row = el("div", "apps-sorun-row");
      row.append(el("div", "apps-sorun-name", "atolye/" + s.path));
      row.append(el("div", "apps-sorun-why", s.uyari || ""));
      if (s.ogretici) row.append(el("div", "apps-sorun-fix", s.ogretici));
      sec.append(row);
    }
    box.append(sec);
  }

  // Proje görünümü: README/nasıl-çalıştır + eylemler + canlı durum.
  function toggleView(p, wrap) {
    const open = wrap.querySelector(".proj-view");
    if (open) { open.remove(); return; }
    body.querySelectorAll(".proj-view").forEach((n) => n.remove());

    const view = el("div", "proj-view");
    view.dataset.path = p.path || "";

    // Canlı durum: çalışıyorsa adresi ve süresi burada da görünsün.
    // Ayrı fonksiyon: 4 sn'lik yoklama AÇIK detayı da tazeler (canlı
    // şikâyet, 31.08: durum sayfa yenilenmeden gelmiyordu — kartlar
    // tazeleniyordu ama açık detay ilk anın fotoğrafında kalıyordu).
    paintViewLive(view, p);
    // Eksik manifestin nedeni burada da: "entry bulunamadı: static/index.html".
    if (p.eksik && p.neden) view.append(el("p", "proj-why", p.neden));

    // Nasıl çalıştırılır (README). Markdown varsa render, yoksa düz metin.
    if (p.howto) {
      const how = el("div", "proj-howto");
      if (typeof Markdown !== "undefined" && Markdown.into) Markdown.into(how, p.howto);
      else how.textContent = p.howto;
      view.append(el("div", "proj-howto-tag", "Nasıl çalıştırılır"), how);
    } else {
      view.append(el("p", "proj-howto empty", "README yok. Dornick'e sorabilirsin."));
    }

    // Nerede olduğu + neyle çalıştığı: kullanıcı diskte bulabilsin,
    // komutu görebilsin. Yol zaten atolye/ ile gelebiliyor — bir daha
    // ekleyip "atolye/atolye/…" yazma.
    const rel = p.path || p.entry || "";
    view.append(el("p", "proj-path", rel.startsWith("atolye") ? rel : "atolye/" + rel));
    if (p.run) view.append(el("p", "proj-cmd", "» " + p.run));

    // Aç · Başlat/Durdur · Klasörü göster — kartla AYNI sıra: aynı işin
    // iki yerde iki farklı düğme kümesi olması kafa karıştırıyordu.
    const row = actionRow(p, r, "view");

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
    // "Dornick'e sor: nasıl çalıştırırım" — projeyi bağlam olarak verir.
    if (typeof setAppContext === "function") {
      const ask = el("button", "proj-btn", "Dornick'e sor");
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
  // servis/web projeler sonucu Dornick'in İÇİNDE bir kapsülde açar; dış proje
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
      if (res.already) {
        toast(res.note || (p.name + " zaten çalışıyor"));
        drawRunning();
        return;
      }
      drawRunning(); setTimeout(drawRunning, 1400);
      // Kapsül YALNIZCA servis/web projeler için. Masaüstü kendi penceresinde.
      const servesWeb = p.kind === "service" || p.kind === "web";
      if (servesWeb && p.scope !== "external" && typeof Capsule !== "undefined" && res.pid) {
        toast(p.name + " başlatıldı");
        Capsule.open({ name: p.name, pid: res.pid });
        close();
      } else if (p.kind === "desktop") {
        toast(res.note || (p.name + " açıldı — görev çubuğunda penceresini ara"));
      } else {
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
    toast(p.name + ": açılacak giriş dosyası bulunamadı — \"Dornick'e sor\" ile sorabilirsin");
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
    holder.append(el("p", "apps-blank dugum-yukleniyor", "Yükleniyor…"));
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
        "Henüz artifact yok. Dornick kalıcı bir rapor ya da pano yayınladığında burada belirir."));
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

    const dlBtn = el("button", "arts-btn", "İndir");
    dlBtn.title = "İndir (.html)";
    dlBtn.onclick = (ev) => {
      ev.stopPropagation();
      const url = artAddress(a);
      if (typeof Viewer !== "undefined" && Viewer.downloadArtifact) Viewer.downloadArtifact(url);
      else window.location.href = url + "?download=1";
    };
    const prBtn = el("button", "arts-btn", "Yazdır");
    prBtn.onclick = (ev) => {
      ev.stopPropagation();
      const url = artAddress(a);
      if (typeof Viewer !== "undefined" && Viewer.printPage) Viewer.printPage(url);
      else window.open(url, "_blank", "noopener");
    };

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

    row.append(glyph, main, openBtn, dlBtn, prBtn, del);
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
      // Dornick'in KENDİ kopyası (model `dornick --web ...` çalıştırdıysa):
      // görünür ama "uygulaman" gibi değil — ayrı ad, sönük nokta,
      // Durdur yok. Gizlemek de yanlış olurdu; kullanıcı orada bir şey
      // çalıştığını bilmeli.
      const r = el("div", "apps-proc" + (p.self ? " self" : ""));
      r.append(el("span", "apps-proc-dot"));
      const name = el("span", "apps-proc-name", p.self ? t("Dornick (kendisi)") : p.name);
      name.title = (p.run || p.path || "") + (p.started ? " · " + mmss(p.started) : "");
      r.append(name);
      r.append(el("span", "apps-proc-time", mmss(p.started)));
      if (p.self) {
        r.append(el("i", "apps-proc-self-note",
          "Dornick'in kendi süreci — panelden durdurulmuyor"));
        sec.append(r);
        continue;
      }
      if (p.address) {
        // Canlı sunucu: sistem içinde kapsülde aç (Dornick'in içinde). Kapsülün
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
    // İyimser arayüz: düğme ANINDA "Durduruluyor…" der. Süreç ağacının
    // ölümü işletim sisteminde bir-iki saniye sürebiliyor; eski hal o
    // arada hâlâ "Durdur" gösteriyordu ("durumlar güncellenmiyor
    // realtime" — canlı, 31.08). Yoklama patlaması geçişi saniyeler
    // içinde ekrana taşır; 4 sn'lik olağan yoklama gerisini toparlar.
    const hedefler = body.querySelectorAll(
      '.proj[data-path="' + (p.path || "") + '"] .proj-btn.act-run');
    hedefler.forEach((b) => { b.disabled = true; b.textContent = t("Durduruluyor…"); });
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
    for (const ms of [600, 1600, 3200]) setTimeout(drawRunning, ms);
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
    if (panel.hidden) open(); else close();
  }

  // Solo kip: kenar çubuğundan tek uygulama seçildi — katalog değil,
  // o uygulamanın detay sayfası. HUD düğmesi tam kataloğu açar.
  let solo = "";

  function show(name) {
    solo = name || "";
    open(true);
  }

  function open(soloKoru) {
    if (!soloKoru) solo = "";
    // Geniş ekranda panel ORTA yüzey: rail'e dokunmaz. Dar pencerede
    // sol overlay'ler çakışır — orada konuşmalar kapanır (eski davranış).
    if (innerWidth <= 860 && typeof History !== "undefined") History.close();
    // Orta alanda tek yüzey: görevler açıksa çekilir.
    if (window.JobsPanel) JobsPanel.close();
    panel.classList.toggle("apps-solo", !!solo);
    {
      panel.hidden = false;
      document.body.classList.add("apps-open");
      // HER açılışta yeniden okunuyor. Eskiden ilk açılıştan sonra yalnız
      // önbellek çiziliyordu: Dornick bir uygulamayı panel açıldıktan SONRA
      // ürettiyse (ya da manifestini sonradan yazdıysa) kullanıcı elle
      // "yenile"ye basana kadar eski listeyi görüyordu — "yaptığı uygulama
      // panelde görünmedi" şikâyetinin doğrudan sebebi buydu.
      load();
      // Çalışanları panel açıkken canlı tut (canlı adres gecikmeli belirir,
      // süreç kendi kendine bitebilir). Kapanınca yoklamayı durduruyoruz.
      clearInterval(pollTimer);
      pollTimer = setInterval(drawRunning, 4000);
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

  return { toggle, open, close, load, show, menu: appMenu };
})();
