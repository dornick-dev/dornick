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
});

const History = (() => {
  const panel = document.getElementById("hist-panel");
  const body = document.getElementById("hist-body");
  const search = document.getElementById("hist-search");

  let sessions = [];
  let knownProjects = [];       // var olan proje adları (atama için öneri)
  let collapsed = new Set();    // kapalı proje klasörleri
  let loaded = false;
  const UNFILED = "— Projesiz —";

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  // --- yükleme ---------------------------------------------------------

  async function load() {
    body.textContent = "";
    let data;
    try {
      data = await (await fetch("/api/sessions")).json();
    } catch {
      body.append(el("p", "hist-blank", "Okunamadı"));
      return;
    }
    sessions = data.sessions || [];
    knownProjects = data.projects || [];
    loaded = true;
    render();
  }

  function render() {
    body.textContent = "";
    const q = (search.value || "").trim().toLowerCase();
    const shown = q
      ? sessions.filter(s => (s.title + " " + s.preview + " " + (s.project || "")).toLowerCase().includes(q))
      : sessions;

    if (!shown.length) {
      body.append(el("p", "hist-blank",
        loaded ? (q ? "Eşleşen konuşma yok" : "Henüz konuşma yok") : "…"));
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

  function row(s) {
    const wrap = el("div", "hist-item" + (s.current ? " current" : ""));
    const line = el("div", "hist-row");
    // Durum noktası: dolu = çalışıyor, boş = tamamlandı.
    line.append(el("span", "hist-dot"));
    line.append(el("span", "hist-title", s.title));
    // Aktif konuşma yazıyla da işaretli: nokta ve renk tek başına
    // okunmuyordu — hangi satırın "şu an açık" olduğu sözle söyleniyor.
    if (s.current) line.append(el("span", "hist-live", t("şu an açık")));
    const meta = el("span", "hist-meta", _time(s.date) + (s.turns ? " · " + s.turns + " tur" : ""));
    line.append(meta);
    // Projeye taşı: klasör ikonu. Satır tıklamasını yutuyor.
    const move = el("button", "hist-assign", "⌗");
    move.title = "Projeye taşı";
    move.onclick = (ev) => { ev.stopPropagation(); assignProject(s, wrap); };
    line.append(move);
    // Satıra tıklamak: AKTİF konuşmada panel kapanır ve süren sohbet görünür —
    // geçiş çağrısı gerekmediği için neo meşgulken de her zaman çalışır.
    // Başka konuşmada o konuşmaya geçilir (sürdürür); meşgulse resume
    // kullanıcıya söylüyor, tık sessiz ölmüyor.
    line.onclick = () => { if (s.current) close(); else resume(s, wrap); };
    wrap.append(line);
    return wrap;
  }

  // Küçük satır-içi düzenleyici: oturuma proje adı ata (ya da boş bırakıp
  // çıkar). Var olan projeler datalist ile öneriliyor; Enter kaydeder.
  function assignProject(s, wrap) {
    const existing = wrap.querySelector(".hist-assign-box");
    if (existing) { existing.remove(); return; }

    const box = el("div", "hist-assign-box");
    const input = el("input", "hist-assign-input");
    input.type = "text";
    input.placeholder = "Proje adı (boş = çıkar)";
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
  search.addEventListener("input", render);

  return { open, close, toggle: toggle_panel, newChat: newConversation };
})();
