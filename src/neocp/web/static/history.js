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
  "Ad (boş = tarihten türet)": "Name (empty = derive from the talk)",
  "Etiketler — virgülle ayır (boş = kaldır)": "Tags — comma separated (empty = clear)",
  "Proje adı (boş = çıkar)": "Project name (empty = remove)",
  "Etiket süzgeci": "Tag filter",
  "süzgeci kaldır": "clear filter",
  " tur": " turns",
  " eşleşme": " matches",
  "Yeni oturum için yeniden başlat": "Restart for a new session",
  " Yeni konuşma": " New conversation",
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
  let deepTimer = null;
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
  }

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
    // Projeler alfabetik, projesiz en sonda.
    const names = [...byProject.keys()].filter(n => n !== UNFILED).sort((a, b) => a.localeCompare(b, "tr"));
    if (byProject.has(UNFILED)) names.push(UNFILED);

    for (const name of names) {
      const items = byProject.get(name);
      items.sort((a, b) => (b.current ? 1 : 0) - (a.current ? 1 : 0));
      const isOpen = !collapsed.has(name);
      const head = el("div", "hist-folder" + (name === UNFILED ? " unfiled" : ""));
      head.append(el("span", "hist-fold", isOpen ? "▾" : "▸"));
      head.append(el("span", "hist-folder-name", name));
      head.append(el("span", "hist-folder-count", String(items.length)));
      head.onclick = () => { isOpen ? collapsed.add(name) : collapsed.delete(name); render(); };
      body.append(head);
      if (isOpen) items.forEach(s => body.append(row(s)));
    }
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
    const wrap = el("div", "hist-item" + (s.current ? " current" : ""));
    const line = el("div", "hist-row");
    // Durum noktası: dolu = çalışıyor, boş = tamamlandı.
    line.append(el("span", "hist-dot"));
    const baslik = el("span", "hist-title" + (s.named ? " named" : ""), s.title);
    // Kullanıcının verdiği ad ile türetilen başlık ayırt edilebilmeli:
    // türetilen başlık konuşmanın ilk sözü, ad ise bir karar.
    baslik.title = s.named ? s.title : s.preview || s.title;
    line.append(baslik);
    // Aktif konuşma yazıyla da işaretli: nokta ve renk tek başına
    // okunmuyordu — hangi satırın "şu an açık" olduğu sözle söyleniyor.
    if (s.current) line.append(el("span", "hist-live", t("şu an açık")));
    const meta = el("span", "hist-meta", _time(s.date) + (s.turns ? " · " + s.turns + t(" tur") : ""));
    line.append(meta);
    // Eylemler: yeniden adlandır · etiketle · projeye taşı. Hepsi satır
    // tıklamasını yutuyor, yoksa düzenlemeye başlarken konuşma değişirdi.
    // Eylemler AYRI bir katmanda, satırın sağ ucunda: yerinde dursalardı
    // dar panelde başlığın genişliğini yerlerdi (üç düğme ~54px) ve satırda
    // yalnız saat görünüyordu — canlıda ölçüldü. Şimdi ancak üzerine
    // gelince beliriyorlar, başlık her zaman tam genişlikte.
    const acts = el("div", "hist-acts");
    for (const [glif, ipucu, islev] of [
      ["✎", "Yeniden adlandır", editName],
      ["#", "Etiketle", editTags],
      ["⌗", "Projeye taşı", assignProject],
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
    line.onclick = () => { if (s.current) close(); else resume(s, wrap); };
    wrap.append(line);

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
      iz.onclick = () => { if (s.current) close(); else resume(s, wrap); };
      wrap.append(iz);
    }

    return wrap;
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
      close();
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
    if (res && res.ok) { close(); return; }
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
    if (typeof Apps !== "undefined") Apps.close();   // iki sol panel çakışmasın
    panel.hidden = false;
    document.body.classList.add("hist-open");
    load();
  }
  function close() {
    panel.hidden = true;
    document.body.classList.remove("hist-open");
  }

  document.getElementById("history").addEventListener("click", toggle_panel);
  document.getElementById("hist-close").addEventListener("click", close);
  document.getElementById("hist-new").addEventListener("click", newConversation);
  // Doğrudan yeni konuşma: HUD'daki düğme geçmiş panelini açmaya gerek
  // bırakmıyor (kullanıcı "illa sohbetleri açıp oradan yeni demem gerekiyor"
  // dedi). Başarılıysa session_reset akışı thread'i temizliyor.
  const newBtn = document.getElementById("new-chat");
  if (newBtn) newBtn.addEventListener("click", newConversation);
  // Her tuşta: yerel süzgeç anında, döküm araması gecikmeli.
  search.addEventListener("input", () => { render(); scheduleDeep(); });

  return { open, close, toggle: toggle_panel, newChat: newConversation };
})();
