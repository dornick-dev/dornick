// Konuşma geçmişi paneli: geçmiş oturumlar.
//
// Önemli ayrım — bu bir ANI listesi DEĞİL. Bir konuşma bir anı demek
// değil: anılar konuşmalardan ayrıca oluşuyor (bir konuşmadan hiç, ya da
// birden fazla). Sahnedeki ağ anıları gösteriyor; bu panel ham
// konuşmaların kendisini. İkisi bağlanabilir ama aynı şey değil.
//
// Opt-in: varsayılan minimal görünümde yok, isteyince açılıyor. Kaynak
// `/api/sessions` (liste) ve `/api/session?id=` (döküm).

// Bu dosyanın kullanıcıya gösterdiği metinlerin İngilizceleri. Kaynak
// metin Türkçe kalıyor; görüntüleme noktasında t("...") ile çevriliyor.
Dil.ekle({
  "şu an açık": "open now",
  "koşuyor": "running",
  "biten": "done",
  "Tümü": "All",
  "Açık": "Open",
  "Koşuyor": "Running",
  "Biten": "Done",
  "Geçiliyor…": "Switching…",
  "Tur bitince geçilebilir": "You can switch when the turn ends",
  "Geçilemedi — neo meşgul olabilir, tur bitince dene.":
    "Could not switch — neo may be busy; try again after the turn.",
  "Okunamadı": "Could not load",
  "Eşleşen konuşma yok": "No matching conversation",
  "Henüz konuşma yok": "No conversations yet",
  "Aranıyor…": "Searching…",
  "Yükleniyor…": "Loading…",
  "içinde ara": "search inside",
  "Konuşmaların İÇİNDE ara — başlıkta değil, dökümde geçen söz":
    "Search inside conversations — the words spoken, not just the title",
  "Yeniden adlandır": "Rename",
  "Etiketle": "Tag",
  "Projeye taşı": "Move to project",
  "Klasör bağla": "Bind folder",
  "Model ata": "Set model",
  "Ad (boş = tarihten türet)": "Name (empty = derive from the talk)",
  "Etiketler — virgülle ayır (boş = kaldır)": "Tags — comma separated (empty = clear)",
  "Proje adı (boş = çıkar)": "Project name (empty = remove)",
  "Çalışma klasörü (boş = kaldır)": "Work folder (empty = clear)",
  "Model adı (boş = global ayar)": "Model name (empty = global setting)",
  "Etiket süzgeci": "Tag filter",
  "süzgeci kaldır": "clear filter",
  " tur": " turns",
  " eşleşme": " matches",
  "Yeni oturum için yeniden başlat": "Restart for a new session",
  " Yeni konuşma": " New conversation",
  "Yeni konuşma": "New conversation",
  "— Projesiz —": "— No project —",
  "Projesiz": "No project",
  "Konuşmalarda ara": "Search conversations",
  "Konuşmalar": "Conversations",
  "Görevler · Otomasyonlar": "Tasks · Automations",
  "Uygulamalar": "Apps",
  "Aç": "Open",
  "Arşivle": "Archive",
  "Bu sohbet arşivlensin mi? Listeden kalkar, geri alınabilir.":
    "Archive this chat? It leaves the list; you can still get it back.",
  "Açık sohbet arşivlensin mi? Yeni boş konuşma açılır; bu sohbet listeden kalkar.":
    "Archive the open chat? A new empty conversation opens; this one leaves the list.",
  "koşan sohbet arşivlenemez — tur bitince dene":
    "can't archive a running chat — try after the turn",
  "Arşivlenemedi": "Could not archive",
});

const History = (() => {
  const panel = document.getElementById("hist-panel");
  const body = document.getElementById("hist-body");
  const search = document.getElementById("hist-search");

  let sessions = [];
  let knownProjects = [];       // var olan proje adları (atama için öneri)
  let knownTags = [];           // var olan etiketler (öneri + süzgeç)
  let collapsed = new Set();    // kapalı proje klasörleri
  let loaded = false;
  let deep = false;             // "içinde ara": döküm araması açık mı
  let searching = false;        // sunucu araması sürüyor
  let tagFilter = "";           // seçili etiket süzgeci
  let statusFilter = "";        // "" | açık | koşuyor | biten
  let deepTimer = null;
  // Uzun liste kaydırma çubuğuyla değil "Daha fazla göster" ile açılır
  // (Claude Code'un Show more'u). Arama/filtre varken sınır yok.
  let hepsi = false;
  const GOSTER = 16;
  const UNFILED = "— Projesiz —";

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  // --- yükleme ---------------------------------------------------------

  // `ara` verilirse sunucu DÖKÜMLERİN içinde de arıyor ve eşleşen satırları
  // (`hits`) gönderiyor. Verilmezse bu yalnızca liste tazelemesi.
  function panelAcik() {
    return document.body.classList.contains("hist-open");
  }

  async function load(ara) {
    if (!loaded) { body.textContent = ""; body.append(el("p", "hist-blank", t("Yükleniyor…"))); }
    let data;
    try {
      const url = ara ? "/api/sessions?ara=" + encodeURIComponent(ara) : "/api/sessions";
      data = await (await fetch(url)).json();
    } catch {
      body.textContent = "";
      body.append(el("p", "hist-blank", t("Okunamadı")));
      return;
    }
    sessions = data.sessions || [];
    knownProjects = data.projects || [];
    knownTags = data.tags || [];
    loaded = true;
    searching = false;
    render();
    // Koşan sohbet varken liste nefes alır: başlık artık koşunun BAŞINDA
    // üretiliyor (loop._oturum_basligi) ve buradaki yoklama onu birkaç
    // saniye içinde sola taşır ("ismi bittikten sonra düzeltiyor" —
    // canlı, 31.08). Koşan yoksa yoklama durur; panel kapaliyken de.
    clearTimeout(canliTazele);
    if (!ara && panelAcik() && sessions.some((s) => s.status === "koşuyor")) {
      canliTazele = setTimeout(() => { if (panelAcik()) load(); }, 5000);
    }
  }
  let canliTazele = null;

  // Döküm araması sunucuya gidiyor; her tuşta istek atmamak için kısa bir
  // bekleme. Kutu boşalırsa arama iptal ve liste tazeleniyor.
  const DEEP_DELAY = 320;

  function scheduleDeep() {
    clearTimeout(deepTimer);
    const q = (search.value || "").trim();
    if (!deep || q.length < 2) {
      searching = false;
      // Derin arama kapandı: eşleşme izleri kalmasın.
      for (const s of sessions) s.hits = [];
      render();
      return;
    }
    searching = true;
    render();
    deepTimer = setTimeout(() => load(q), DEEP_DELAY);
  }

  function render() {
    body.textContent = "";
    const q = (search.value || "").trim().toLowerCase();
    // Yerel süzgeç her zaman çalışıyor (ad, önizleme, proje, etiket); derin
    // arama açıkken sunucudan gelen eşleşmeler de kabul ediliyor — söz
    // başlıkta değil dökümün ortasında geçiyor olabilir.
    let shown = q
      ? sessions.filter(s =>
          (s.title + " " + s.preview + " " + (s.project || "") + " " + (s.tags || []).join(" "))
            .toLowerCase().includes(q) || (s.hits || []).length)
      : sessions;
    if (tagFilter) shown = shown.filter(s => (s.tags || []).includes(tagFilter));
    if (statusFilter === "açık") {
      shown = shown.filter(s => s.current || s.status === "açık" || s.status === "koşuyor");
    } else if (statusFilter === "koşuyor") {
      shown = shown.filter(s => s.status === "koşuyor");
    } else if (statusFilter === "biten") {
      shown = shown.filter(s => !s.current && s.status !== "koşuyor");
    }

    drawTools();

    if (searching) {
      body.append(el("p", "hist-blank", t("Aranıyor…")));
      return;
    }

    if (!shown.length) {
      body.append(el("p", "hist-blank",
        loaded ? (q || tagFilter ? t("Eşleşen konuşma yok") : t("Henüz konuşma yok"))
               : t("Yükleniyor…")));
      return;
    }

    // Önce PROJEYE göre klasörle (sohbetleri grupla), sonra her klasörün
    // içinde aktif olan başta. Projesiz olanlar en sonda tek bir kümede.
    // Bir konuşma bir anı değil — bu yalnızca gezinme düzeni.
    const byProject = new Map();
    for (const s of shown) {
      const key = s.project || UNFILED;
      if (!byProject.has(key)) byProject.set(key, []);
      byProject.get(key).push(s);
    }
    // Liste sınırı: kırpma proje gruplamasından ÖNCE — en yeni 16.
    let kirpilan = 0;
    if (!hepsi && !q && !tagFilter && !statusFilter && shown.length > GOSTER) {
      kirpilan = shown.length - GOSTER;
      shown = shown.slice(0, GOSTER);
      byProject.clear();
      for (const s of shown) {
        const key = s.project || UNFILED;
        if (!byProject.has(key)) byProject.set(key, []);
        byProject.get(key).push(s);
      }
    }
    // Projeler alfabetik, projesiz en sonda.
    const names = [...byProject.keys()].filter(n => n !== UNFILED).sort((a, b) => a.localeCompare(b, "tr"));
    if (byProject.has(UNFILED)) names.push(UNFILED);

    for (const name of names) {
      const items = byProject.get(name);
      // Aktifi tepeye taşımak listeyi SIÇRATIYORDU ("yerinde durmuyor"):
      // sıra hep yenilik sırası; aktif yalnız vurguyla belli olur.
      const isOpen = !collapsed.has(name);
      const head = el("div", "hist-folder" + (name === UNFILED ? " unfiled" : ""));
      head.append(el("span", "hist-fold", isOpen ? "▾" : "▸"));
      head.append(el("span", "hist-folder-name",
                     name === UNFILED ? t(UNFILED) : name));
      head.append(el("span", "hist-folder-count", String(items.length)));
      head.onclick = () => { isOpen ? collapsed.add(name) : collapsed.delete(name); render(); };
      body.append(head);
      if (isOpen) items.forEach(s => body.append(row(s)));
    }
    if (kirpilan) body.append(dahaFazla(kirpilan));
  }

  // Arama kutusunun altındaki şerit: "içinde ara" anahtarı ve (varsa)
  // etkin etiket süzgeci. Kutunun kendisi işaretlemede duruyor; bu şerit
  // onun hemen altına bir kez kuruluyor.
  function drawTools() {
    let strip = document.getElementById("hist-tools");
    if (!strip) {
      strip = el("div", "hist-tools");
      strip.id = "hist-tools";
      search.parentElement.insertBefore(strip, search.nextSibling);
    }
    strip.textContent = "";

    const filters = el("div", "hist-status-filters");
    for (const [id, label] of [
      ["", "Tümü"],
      ["açık", "Açık"],
      ["koşuyor", "Koşuyor"],
      ["biten", "Biten"],
    ]) {
      const chip = el("button", "hist-status" + (statusFilter === id ? " on" : ""));
      chip.type = "button";
      chip.textContent = t(label);
      chip.onclick = () => { statusFilter = id; render(); };
      filters.append(chip);
    }
    strip.append(filters);

    const anahtar = el("button", "hist-deep" + (deep ? " on" : ""));
    anahtar.type = "button";
    anahtar.textContent = (deep ? "◉ " : "○ ") + t("içinde ara");
    anahtar.title = t("Konuşmaların İÇİNDE ara — başlıkta değil, dökümde geçen söz");
    anahtar.onclick = () => { deep = !deep; scheduleDeep(); };
    strip.append(anahtar);

    if (tagFilter) {
      const cip = el("button", "hist-label on");
      cip.type = "button";
      cip.textContent = "#" + tagFilter + " ×";
      cip.title = t("süzgeci kaldır");
      cip.onclick = () => { tagFilter = ""; render(); };
      strip.append(cip);
    }
  }

  function row(s) {
    const wrap = el("div", "hist-item" + (s.current ? " current" : "")
      + (s.status === "koşuyor" ? " running" : ""));
    const line = el("div", "hist-row");
    const dot = el("span", "hist-dot"
      + (s.status === "koşuyor" ? " run" : (s.current ? " on" : "")));
    line.append(dot);
    const baslik = el("span", "hist-title" + (s.named ? " named" : ""), s.title);
    baslik.title = s.named ? s.title : s.preview || s.title;
    line.append(baslik);
    if (s.status === "koşuyor") line.append(el("span", "hist-live", t("koşuyor")));
    else if (s.current) line.append(el("span", "hist-live", t("şu an açık")));
    const bits = [_time(s.date)];
    if (s.turns) bits.push(s.turns + t(" tur"));
    if (s.model) {
      const short = String(s.model).includes("/")
        ? String(s.model).split("/").pop() : s.model;
      bits.push(short);
    }
    if (s.path) {
      const leaf = String(s.path).replace(/\\/g, "/").split("/").filter(Boolean).pop();
      if (leaf) bits.push("📁 " + leaf);
    }
    line.append(el("span", "hist-meta", bits.join(" · ")));
    const acts = el("div", "hist-acts");
    for (const [glif, ipucu, islev] of [
      ["✎", "Yeniden adlandır", editName],
      ["#", "Etiketle", editTags],
      ["⌗", "Projeye taşı", assignProject],
      ["📁", "Klasör bağla", assignPath],
      ["◈", "Model ata", assignModel],
    ]) {
      const dugme = el("button", "hist-assign", glif);
      dugme.title = t(ipucu);
      dugme.onclick = (ev) => { ev.stopPropagation(); islev(s, wrap); };
      acts.append(dugme);
    }
    line.append(acts);
    // Satıra tıklamak: AKTİF konuşmada panel kapanır ve süren sohbet görünür —
    // geçiş çağrısı gerekmediği için neo meşgulken de her zaman çalışır.
    // Başka konuşmada o konuşmaya geçilir (sürdürür); meşgulse resume
    // kullanıcıya söylüyor, tık sessiz ölmüyor.
    line.onclick = () => {
      if (s.current) { if (innerWidth <= 860) close(); }
      else resume(s, wrap);
    };
    wrap.append(line);

    wrap.addEventListener("contextmenu", (ev) => sohbetMenu(s, wrap, ev));

    // Etiket rozetleri: tıklayınca o etikete süzülüyor. Etiket bir klasör
    // değil — bir konuşma birden çok etiket taşıyabiliyor, proje ise tek.
    if ((s.tags || []).length) {
      const şerit = el("div", "hist-tags");
      for (const etiket of s.tags) {
        const cip = el("button", "hist-label" + (etiket === tagFilter ? " on" : ""));
        cip.type = "button";
        cip.textContent = "#" + etiket;
        cip.onclick = (ev) => {
          ev.stopPropagation();
          tagFilter = (tagFilter === etiket) ? "" : etiket;
          render();
        };
        şerit.append(cip);
      }
      wrap.append(şerit);
    }

    // Döküm araması eşleşmeleri: hangi sözün nerede geçtiği. Satıra
    // tıklamak yine konuşmayı açıyor.
    for (const hit of (s.hits || [])) {
      const iz = el("div", "hist-hit");
      iz.append(el("span", "hist-hit-who", hit.role === "user" ? "sen" : "neo"));
      iz.append(el("span", "hist-hit-text", hit.text));
      iz.onclick = () => {
        if (s.current) { if (innerWidth <= 860) close(); }
        else resume(s, wrap);
      };
      wrap.append(iz);
    }

    return wrap;
  }

  function sohbetMenu(s, wrap, ev) {
    if (typeof Menu === "undefined") return;
    const kosuyor = s.status === "koşuyor";
    Menu.ac(ev, [
      { ad: "Aç", is: () => {
        if (s.current) { if (innerWidth <= 860) close(); }
        else resume(s, wrap);
      } },
      { ad: "Yeniden adlandır", is: () => editName(s, wrap) },
      { ad: "Etiketle", is: () => editTags(s, wrap) },
      { ad: "Projeye taşı", is: () => assignProject(s, wrap) },
      { ad: "Klasör bağla", is: () => assignPath(s, wrap) },
      { ad: "Model ata", is: () => assignModel(s, wrap) },
      { ayrac: true },
      { ad: "Arşivle", risk: true, kapali: kosuyor,
        ipucu: kosuyor ? "koşan sohbet arşivlenemez — tur bitince dene" : "",
        is: () => arsivle(s) },
    ]);
  }

  async function arsivle(s) {
    const uyari = s.current
      ? t("Açık sohbet arşivlensin mi? Yeni boş konuşma açılır; bu sohbet listeden kalkar.")
      : t("Bu sohbet arşivlensin mi? Listeden kalkar, geri alınabilir.");
    if (!confirm(uyari)) return;
    let res;
    try {
      res = await (await fetch("/api/session/archive", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: s.id }),
      })).json();
    } catch { res = { ok: false }; }
    if (res && res.ok) {
      await load();
      setTimeout(load, 600);
      return;
    }
    status((res && res.error) ? res.error : t("Arşivlenemedi"));
  }

  // Yeniden adlandırma: satır içi tek kutu. Boş bırakmak adı kaldırıyor ve
  // başlık yine konuşmanın ilk sözünden türetiliyor — "adı sil" ayrı bir
  // düğme istemiyor.
  function editName(s, wrap) {
    const existing = wrap.querySelector(".hist-assign-box");
    if (existing) { existing.remove(); return; }

    const box = el("div", "hist-assign-box");
    const input = el("input", "hist-assign-input");
    input.type = "text";
    input.placeholder = t("Ad (boş = tarihten türet)");
    input.value = s.named ? s.title : "";

    const save = async () => {
      const ad = input.value.trim();
      box.remove();
      const kayit = await saveMeta(s.id, { ad });
      if (kayit) {
        s.named = !!kayit.ad;
        if (kayit.ad) s.title = kayit.ad;
      }
      // Ad silindiyse türetilen başlığı sunucu biliyor: listeyi tazele.
      if (!ad) await load();
      else render();
    };
    input.onkeydown = (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); save(); }
      else if (ev.key === "Escape") { box.remove(); }
    };
    box.append(input);
    wrap.append(box);
    input.focus();
    input.select();
  }

  // Etiketler: virgülle ayrılmış serbest metin. Var olanlar öneriliyor.
  function editTags(s, wrap) {
    const existing = wrap.querySelector(".hist-assign-box");
    if (existing) { existing.remove(); return; }

    const box = el("div", "hist-assign-box");
    const input = el("input", "hist-assign-input");
    input.type = "text";
    input.placeholder = t("Etiketler — virgülle ayır (boş = kaldır)");
    input.value = (s.tags || []).join(", ");
    input.setAttribute("list", "hist-tags-list");
    let list = document.getElementById("hist-tags-list");
    if (!list) { list = el("datalist"); list.id = "hist-tags-list"; document.body.append(list); }
    list.replaceChildren(...knownTags.map(x => { const o = el("option"); o.value = x; return o; }));

    const save = async () => {
      const etiketler = input.value.split(",").map(x => x.trim()).filter(Boolean);
      box.remove();
      const kayit = await saveMeta(s.id, { etiketler });
      if (kayit) s.tags = kayit.etiketler || [];
      for (const etiket of s.tags) {
        if (!knownTags.includes(etiket)) knownTags.push(etiket);
      }
      render();
    };
    input.onkeydown = (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); save(); }
      else if (ev.key === "Escape") { box.remove(); }
    };
    box.append(input);
    wrap.append(box);
    input.focus();
    input.select();
  }

  // Ad/etiket yazımı. Gönderilmeyen alan sunucuda DOKUNULMADAN kalıyor:
  // yalnız etiket değiştiren bir istek adı silmemeli.
  async function saveMeta(id, alanlar) {
    try {
      const res = await (await fetch("/api/session/meta", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, ...alanlar }),
      })).json();
      if (res && res.ok) return res.meta || {};
      status((res && res.error) || t("Okunamadı"));
    } catch { status(t("Okunamadı")); }
    return null;
  }

  // Küçük satır-içi düzenleyici: oturuma proje adı ata (ya da boş bırakıp
  // çıkar). Var olan projeler datalist ile öneriliyor; Enter kaydeder.
  function assignProject(s, wrap) {
    const existing = wrap.querySelector(".hist-assign-box");
    if (existing) { existing.remove(); return; }

    const box = el("div", "hist-assign-box");
    const input = el("input", "hist-assign-input");
    input.type = "text";
    input.placeholder = t("Proje adı (boş = çıkar)");
    input.value = s.project || "";
    input.setAttribute("list", "hist-projects");
    let list = document.getElementById("hist-projects");
    if (!list) { list = el("datalist"); list.id = "hist-projects"; document.body.append(list); }
    list.replaceChildren(...knownProjects.map(p => { const o = el("option"); o.value = p; return o; }));

    const save = async () => {
      const name = input.value.trim();
      if (name === (s.project || "")) { box.remove(); return; }
      try {
        const res = await (await fetch("/api/session/project", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: s.id, project: name }),
        })).json();
        if (res && res.ok) { knownProjects = res.projects || knownProjects; }
      } catch { /* yut */ }
      s.project = name;
      render();
    };
    input.onkeydown = (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); save(); }
      else if (ev.key === "Escape") { box.remove(); }
    };
    box.append(input);
    wrap.append(box);
    input.focus();
    input.select();
  }

  function assignPath(s, wrap) {
    const existing = wrap.querySelector(".hist-assign-box");
    if (existing) { existing.remove(); return; }
    const box = el("div", "hist-assign-box");
    const input = el("input", "hist-assign-input");
    input.type = "text";
    input.placeholder = t("Çalışma klasörü (boş = kaldır)");
    input.value = s.path || "";
    const save = async () => {
      const path = input.value.trim();
      box.remove();
      const kayit = await saveMeta(s.id, { path });
      if (kayit) s.path = kayit.path || "";
      // Aktif sohbetse hemen uygula (geçişte de uygulanır).
      if (s.current) {
        try {
          await fetch("/api/session/resume", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: s.id }),
          });
        } catch { /* yut */ }
      }
      render();
    };
    input.onkeydown = (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); save(); }
      else if (ev.key === "Escape") { box.remove(); }
    };
    box.append(input);
    wrap.append(box);
    input.focus();
    input.select();
  }

  function assignModel(s, wrap) {
    const existing = wrap.querySelector(".hist-assign-box");
    if (existing) { existing.remove(); return; }
    const box = el("div", "hist-assign-box");
    const input = el("input", "hist-assign-input");
    input.type = "text";
    input.placeholder = t("Model adı (boş = global ayar)");
    input.value = s.model || "";
    const save = async () => {
      const model = input.value.trim();
      box.remove();
      const kayit = await saveMeta(s.id, { model });
      if (kayit) s.model = kayit.model || "";
      if (s.current) {
        try {
          await fetch("/api/session/resume", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: s.id }),
          });
        } catch { /* yut */ }
      }
      render();
    };
    input.onkeydown = (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); save(); }
      else if (ev.key === "Escape") { box.remove(); }
    };
    box.append(input);
    wrap.append(box);
    input.focus();
    input.select();
  }

  // Yeni konuşma: taze bir oturum başlatır. Sunucu desteklemiyorsa (eski
  // süreç) kullanıcıya söylenir — sessizce yutulmaz.
  async function newConversation() {
    let res;
    try {
      res = await (await fetch("/api/session/new", { method: "POST" })).json();
    } catch {
      res = { ok: false };
    }
    const btn = document.getElementById("hist-new");
    if (res && res.ok) {
      // Rail kalıcı: yeni konuşma onu KAPATMAZ (canlı şikâyet). Dar
      // pencerede overlay çekilir; genişte liste tazelenip yeni oturum
      // işaretlenir.
      if (innerWidth <= 860) close(); else { load(); setTimeout(load, 600); }
    } else {
      // Canlı yeni oturum henüz köprüde yok: kırık görünmesin, söyle.
      btn.textContent = "Yeni oturum için yeniden başlat";
      setTimeout(() => {
        btn.replaceChildren();
        const plus = el("span", "hist-new-plus", "+");
        btn.append(plus, " Yeni konuşma");
      }, 2200);
    }
  }

  // Geçmiş bir konuşmayı sürdür: sunucu oturumu değiştirip session_reset
  // yayınlıyor; ana akış thread'i temizleyip dökümü yüklüyor.
  async function resume(s, wrap) {
    status(t("Geçiliyor…"));
    let res;
    try {
      res = await (await fetch("/api/session/resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: s.id }),
      })).json();
    } catch { res = { ok: false }; }
    if (res && res.ok) {
      // Geniş ekranda rail kalıcı bir sütun: konuşma değiştirmek onu
      // KAPATMAZ. Liste tazelenir; sunucu geçişi işlerken yarış olursa
      // "şu an açık" işareti ilk yüklemeye yetişemeyebiliyor — kısa bir
      // gecikmeyle ikinci tazeleme işareti oturtur.
      if (innerWidth > 860) { load(); setTimeout(load, 600); } else close();
      return;
    }
    if (res && res.busy) {
      // Meşgulken tık sessiz ölmüyor: kısa geri bildirim + satır görsel
      // olarak "beklemede" işaretleniyor. Tur bitince tekrar tıklanır.
      status(t("Tur bitince geçilebilir"));
      if (wrap) {
        wrap.classList.add("waiting");
        setTimeout(() => wrap.classList.remove("waiting"), 4000);
      }
      return;
    }
    // Görünür hata: köprü yoksa ya da oturum bulunamadıysa.
    status((res && res.error) ? res.error : t("Geçilemedi — neo meşgul olabilir, tur bitince dene."));
  }

  // "Daha fazla göster": kırpılan satır sayısıyla, listenin dibinde.
  function dahaFazla(kirpilan) {
    const dugme = el("button", "hist-more", t("Daha fazla göster") + " · " + kirpilan);
    dugme.type = "button";
    dugme.addEventListener("click", () => { hepsi = true; render(); });
    return dugme;
  }

  // Panelin üstünde kısa bir durum/hata satırı.
  function status(text) {
    let bar = document.getElementById("hist-status");
    if (!bar) {
      bar = el("div", "hist-status");
      bar.id = "hist-status";
      body.parentElement.insertBefore(bar, body);
    }
    bar.textContent = text || "";
    bar.hidden = !text;
    if (text) setTimeout(() => { if (bar.textContent === text) { bar.hidden = true; } }, 4000);
  }

  // --- yardımcılar -----------------------------------------------------

  const _time = (date) => (date || "").slice(11, 16) || (date || "").slice(0, 10);

  // --- panel -----------------------------------------------------------

  function toggle_panel() {
    if (panel.hidden) open();
    else close();
  }
  function open() {
    userClosed = false;
    if (innerWidth <= 860 && typeof Apps !== "undefined") Apps.close();   // dar: overlay çakışmasın
    panel.hidden = false;
    document.body.classList.add("hist-open");
    document.getElementById("history").classList.add("on");
    try { localStorage.setItem("neo-rail", "acik"); } catch { /* dosya:// */ }
    load();
  }
  let userClosed = false;   // bu oturumda elle kapatıldı mı
  function close() {
    panel.hidden = true;
    userClosed = true;
    document.body.classList.remove("hist-open");
    document.getElementById("history").classList.remove("on");
    // Bilinçli karar: tercih DİSKE YAZILMAZ. Kenar çubuğu kalıcı bir
    // yapı (Claude Code gibi "sürekli açık"); X yalnız bu oturumda
    // gizler, sonraki açılışta yine gelir.
  }

  document.getElementById("history").addEventListener("click", toggle_panel);
  // Panelin kendi X'i kalktı (Claude Code: ☰ tek anahtar); id bir gün
  // geri gelirse yine bağlanır.
  const kapat = document.getElementById("hist-close");
  if (kapat) kapat.addEventListener("click", close);
  // Süzgeç hunisi: filtre çipleri istenince görünür — varsayılan sade.
  const huni = document.getElementById("hist-filter-toggle");
  if (huni) huni.addEventListener("click", () => {
    const acik = panel.classList.toggle("filters-on");
    huni.classList.toggle("on", acik);
  });
  document.getElementById("hist-new").addEventListener("click", newConversation);
  // HUD'daki ayrı yeni-konuşma ikonu kalktı: sidebar'daki "+ Yeni
  // konuşma" tek giriş (kullanıcı: "zaten yazıyor, icon gereksiz").
  // Her tuşta: yerel süzgeç anında, döküm araması gecikmeli.
  search.addEventListener("input", () => { render(); scheduleDeep(); });

  // Rail varsayılan AÇIK ve KALICI (Claude Code alışkanlığı: konuşmalar
  // hep solda). Dar pencerede overlay'i kendiliğinden açmak sohbetin
  // üstüne binmek olurdu — orada kapalı başlar. Pencere genişleyince
  // (kullanıcı bu oturumda elle kapatmadıysa) kendiliğinden geri gelir.
  if (innerWidth > 860) open();
  window.addEventListener("resize", () => {
    if (innerWidth > 860 && panel.hidden && !userClosed) open();
    if (innerWidth <= 860 && !panel.hidden) { close(); userClosed = false; }
  });

  return { open, close, toggle: toggle_panel, newChat: newConversation,
           // Şerit olayı (paralel oturumlar): arka planda koşan/biten
           // sohbetin rozeti canlı tazelensin — panel açıkken liste
           // yeniden yüklenir, kapalıyken bir sonraki açılış zaten taze.
           laneChanged: () => { try { if (panelAcik()) load(); } catch {} },
           // Sahneden gelen "konuşmaya git": önce panel açılır — geçiş
           // ve olası hata mesajı GÖRÜNÜR bir yerde yaşasın (kapalı
           // paneldeki durum satırı sessiz ölüyordu).
           resumeById: (id) => { open(); resume({ id }); } };
})();


// --- kenar bölümleri: Görevler · Otomasyonlar ve Uygulamalar ------------
// Rail tek kenar çubuğu: konuşmaların altında katlanır iki bölüm. Satıra
// tıklamak ilgili DETAYI ORTA alanda açar (JobsPanel.show / Apps.open).
Dil.ekle({
  "Henüz görev yok": "No tasks yet",
  "Uygulama yok": "No apps yet",
  "otomasyon": "automation",
  "çalışıyor": "running",
  "eksik": "incomplete",
});

(() => {
  const elx = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  async function doldurGorevler(list, say) {
    let tasks = [];
    try { tasks = (await (await fetch("/api/jobs")).json()).tasks || []; } catch { /* sunucu yok */ }
    say.textContent = tasks.length || "";
    list.textContent = "";
    if (!tasks.length) { list.append(elx("div", "side-blank", t("Henüz görev yok"))); return; }
    for (const task of tasks.slice(0, 40)) {
      const row = elx("button", "side-row");
      row.type = "button";
      const durum = task.last_status === "koşuyor" ? " run"
        : (task.last_status === "hata" || task.last_status === "başlatılamadı") ? " bad"
        : task.kind_ui === "automation" ? " auto"
        : task.enabled ? " on" : "";
      row.append(elx("i", "side-row-dot" + durum),
                 elx("span", "side-row-name", task.title || task.id));
      if (task.kind_ui === "automation") row.append(elx("span", "side-row-meta", t("otomasyon")));
      row.addEventListener("click", () => { if (window.JobsPanel) JobsPanel.show(task.id); });
      row.addEventListener("contextmenu", (ev) => {
        if (window.JobsPanel && JobsPanel.menu) JobsPanel.menu(task, ev);
      });
      list.append(row);
    }
  }

  async function doldurUygulamalar(list, say) {
    let projeler = [];
    try { projeler = (await (await fetch("/api/projects")).json()).projects || []; } catch { /* sunucu yok */ }
    // Kenar çubuğu yalnız GERÇEK uygulamaları gösterir: türü belli ve
    // eksik olmayanlar. Atölyedeki başıboş dosyalar (rapor.txt, betik.ps1)
    // katalogda "belirsiz" diye dursun ama burada liste çöplüğü yapmasın.
    projeler = projeler.filter((p) => p.kind && !p.eksik);
    say.textContent = projeler.length || "";
    list.textContent = "";
    if (!projeler.length) { list.append(elx("div", "side-blank", t("Uygulama yok"))); return; }
    for (const p of projeler.slice(0, 40)) {
      const row = elx("button", "side-row");
      row.type = "button";
      row.append(elx("i", "side-row-dot" + (p.eksik ? " bad" : "")),
                 elx("span", "side-row-name", p.name));
      // Orta alan yalnız SEÇİLENİN detayı: katalog değil, o uygulamanın
      // sayfası (liste zaten burada, solda).
      row.addEventListener("click", () => {
        if (typeof Apps !== "undefined") Apps.show(p.name);
      });
      row.addEventListener("contextmenu", (ev) => {
        if (typeof Apps !== "undefined" && Apps.menu) Apps.menu(p, ev);
      });
      list.append(row);
    }
  }

  const BOLUMLER = [
    ["side-jobs-head", "side-jobs-list", "side-jobs-count", "neo-side-jobs", doldurGorevler],
    ["side-apps-head", "side-apps-list", "side-apps-count", "neo-side-apps", doldurUygulamalar],
  ];

  for (const [headId, listId, countId, anahtar, doldur] of BOLUMLER) {
    const head = document.getElementById(headId);
    const list = document.getElementById(listId);
    const say = document.getElementById(countId);
    if (!head || !list) continue;

    const uygula = (acik) => {
      list.hidden = !acik;
      head.querySelector(".side-fold").textContent = acik ? "▾" : "▸";
      try { localStorage.setItem(anahtar, acik ? "acik" : "kapali"); } catch { /* dosya:// */ }
      if (acik) doldur(list, say);
    };
    head.addEventListener("click", () => uygula(list.hidden));

    let kayit = null;
    try { kayit = localStorage.getItem(anahtar); } catch { /* dosya:// */ }
    // Varsayılan açık: kenar çubuğu tek bakışta her şeyi göstersin.
    uygula(kayit !== "kapali");
    document.addEventListener("neo-side-tazele", () => {
      if (!list.hidden) doldur(list, say);
    });
  }
})();

// --- hızlı gezinti satırları: detay orta alanda -------------------------
(() => {
  const g = document.getElementById("side-jobs-nav");
  if (g) g.addEventListener("click", () => { if (window.JobsPanel) JobsPanel.open(); });
  const u = document.getElementById("side-apps-nav");
  if (u) u.addEventListener("click", () => { if (typeof Apps !== "undefined") Apps.open(); });
})();

// --- statik kabuk etiketleri çeviriden geçer ---------------------------
// Sidebar v4 bu metinleri HTML'e gömdü; İngilizce kipte Türkçe kalıyorlardı
// (vitrin çekiminde yakalandı). Çeviri, metnin doğduğu yerde uygulanır.
(() => {
  const yeniBtn = document.getElementById("hist-new");
  if (yeniBtn && yeniBtn.lastChild && yeniBtn.lastChild.nodeType === 3) {
    yeniBtn.lastChild.textContent = " " + t("Yeni konuşma");
  }
  const ara = document.getElementById("hist-search");
  if (ara) ara.placeholder = t("Konuşmalarda ara");
  for (const nav of document.querySelectorAll(".side-nav span")) {
    nav.textContent = t(nav.textContent.trim());
  }
  const etiket = document.querySelector(".side-label");
  if (etiket) etiket.textContent = t(etiket.textContent.trim());
})();
