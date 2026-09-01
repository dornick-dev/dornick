// Orkestra: alt ajan kanalları — "şef modu".
//
// Dornick bir işi böldüğünde alt ajanlar doğuyor (task aracı). Onların araç
// çağrıları ana sohbete karışmıyor; bu güverte her kanalı canlı bir kart
// olarak gösteriyor: başlığı, modeli, o an çalıştırdığı araç, kaç araç
// çağırdığı ve durumu (çalışıyor · bitti · hata). Arka planda koşan
// yardımcılar rozetle ayrılıyor; biten kanallar hemen silinmiyor — son
// beşi duruyor, karta tıklayınca sonucun özeti açılıyor.
//
// Kaynak canlı SSE olayları: child_start / child_tool / child_end. Bir anı
// DEĞİL — anlık koordinasyon. Kendisi çalışırken açılıyor, sabitlenebiliyor.
// Sayfa açılışında /api/state'teki gerçek kanal listesiyle tohumlanıyor
// (seed): hayalet "çalışıyor" kartı kalmıyor, geçen oturumdan yarım kalan
// yardımcılar soluk "yarım kaldı" satırıyla görünüyor.

Dil.ekle({
  "Şu an alt ajan yok. Dornick bir işi böldüğünde kanallar burada belirir.":
    "No helpers right now. Channels appear here when Dornick splits a job.",
  "Şef bekliyor · ": "Conductor waiting · ",
  " kanal çalışıyor": " channel(s) running",
  "Şef sürüyor · tüm kanallar bitti": "Conductor going · all channels done",
  "Şef hazır": "Conductor ready",
  "Eşzamanlı yardımcı sınırı: ": "Concurrent helper limit: ",
  " · ayarlardan değişir": " · set in settings",
  "Düşünüyor…": "Thinking…",
  "Hata verdi": "Failed",
  "Bitti": "Done",
  "Yarım kaldı": "Left unfinished",
  "Yarım kalan yardımcı var — istersen sürdürülebilir":
    "Some helpers were left unfinished — they can be resumed",
  " araç": " tools",
  "arka plan": "background",
  "(özet yok)": "(no summary)",
  "Raporu aç": "Open report",
  "Model bekleniyor": "Waiting for model",
  "Model yanıt vermedi": "Model did not respond",
  "Devam et": "Continue",
  "İptal et": "Cancel",
  "İptal ediliyor…": "Cancelling…",
  "Sürdürülüyor…": "Resuming…",
});

const Orchestra = (() => {
  const deck = document.getElementById("orch-deck");
  const body = document.getElementById("orch-body");
  const status = document.getElementById("orch-status");
  const foot = document.getElementById("orch-foot");

  // id → kanal durumu (id yoksa başlık anahtar olur — eski olaylarla uyum).
  const channels = new Map();
  let pinned = false;      // kullanıcı elle açtı: koşu bitince kapanmasın
  let fadeTimer = null;

  // Bitmiş kanallardan en fazla bu kadarı tutuluyor; en eskisi düşüyor.
  const KEEP_DONE = 5;
  // Koşan kanalda son N araç satırı (kısa act listesi).
  const KEEP_ACTS = 8;

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  const keyOf = (ev) => ev.id || ev.title;

  // --- olaylar (app.js SSE'den çağırıyor) ------------------------------

  function start(ev) {
    channels.set(keyOf(ev), {
      title: ev.title, model: ev.model || "", id: ev.id || "",
      bg: !!ev.bg, tool: "", hedef: "", tools: 0, state: "run",
      ozet: "", open: false, acts: [],
    });
    prune();
    open();
    render();
  }

  function tool(ev) {
    // Araç olayları başlıkla geliyor (kanal kimliği taşımıyorlar); aynı
    // başlıklı koşan kanala yazılıyor.
    const ch = [...channels.values()].find(c => c.title === ev.title && c.state === "run")
      || channels.get(ev.title);
    if (!ch) return;
    if (!ch.acts) ch.acts = [];
    if (ev.phase === "start") {
      ch.tool = ev.tool;
      ch.hedef = ev.hedef || "";
      ch.tools += 1;
      ch.acts.push({
        name: ev.tool || "",
        hedef: ev.hedef || "",
        phase: "run",
      });
      if (ch.acts.length > KEEP_ACTS) ch.acts.shift();
    } else {
      ch.tool = ev.tool + (ev.phase === "fail" ? " ✗" : " ✓");
      if (ev.hedef) ch.hedef = ev.hedef;
      const last = ch.acts[ch.acts.length - 1];
      if (last && last.name === ev.tool) {
        last.phase = ev.phase === "fail" ? "fail" : "ok";
        if (ev.hedef) last.hedef = ev.hedef;
      } else {
        ch.acts.push({
          name: ev.tool || "",
          hedef: ev.hedef || "",
          phase: ev.phase === "fail" ? "fail" : "ok",
        });
        if (ch.acts.length > KEEP_ACTS) ch.acts.shift();
      }
    }
    render();
  }

  function end(ev) {
    const ch = channels.get(keyOf(ev)) || channels.get(ev.title);
    if (!ch) return;
    ch.state = ev.ok ? "done" : "fail";
    ch.tool = "";
    ch.wait = null;
    ch.turns = ev.turns; ch.tools = ev.tools != null ? ev.tools : ch.tools;
    if (ev.ozet) ch.ozet = ev.ozet;
    if (ev.deliverable) ch.deliverable = ev.deliverable;
    if (ev.model) ch.model = ev.model;
    if (ev.usage) ch.usage = ev.usage;
    prune();
    render();
    // Hepsi bittiyse ve sabitli değilse güverte bir süre sonra çekiliyor —
    // kanallar SİLİNMİYOR: rozete tıklayınca son beşi yine görünür.
    if (!pinned && [...channels.values()].every(c => c.state !== "run")) {
      clearTimeout(fadeTimer);
      fadeTimer = setTimeout(() => { if (!anyRunning()) hide(); }, 6000);
    }
  }

  function wait(ev) {
    const ch = channels.get(keyOf(ev))
      || [...channels.values()].find(c => c.title === ev.title && c.state === "run");
    if (!ch || ch.state !== "run") return;
    if (ev.kip === "bitti" || ev.kip === "iptal") {
      ch.wait = null;
      if (!ch.tool || String(ch.tool).startsWith(t("Model bekleniyor"))
          || String(ch.tool).startsWith(t("Model yanıt vermedi"))) {
        ch.tool = "";
      }
      render();
      return;
    }
    let msg = ev.kip === "hata"
      ? t("Model yanıt vermedi")
      : t("Model bekleniyor");
    if (ev.deneme && ev.toplam) msg += ` (${ev.deneme}/${ev.toplam})`;
    if (ev.saniye) msg += ` · ${ev.saniye}s`;
    ch.tool = msg;
    ch.wait = ev;
    if (ev.kip === "hata") {
      ch.state = "fail";
      ch.wait = null;
    }
    open();
    render();
  }

  const anyRunning = () => [...channels.values()].some(c => c.state === "run");

  // Açılış tohumu: panel olay güdümlü ama sayfa yenilenince/uygulama yeniden
  // açılınca olaylar kaçmış oluyor. Tek doğru kaynak /api/state'teki gerçek
  // kanal listesi (ajanın defteri): harita baştan kurulur — snapshot'ta
  // olmayan "çalışıyor" kanalı hayalettir, çizilmez. Yetimler (geçen
  // oturumdan yarım kalanlar) soluk "yarım kaldı" satırı olarak listelenir.
  function seed(list) {
    channels.clear();
    for (const ev of list || []) {
      if (!ev || (!ev.id && !ev.title)) continue;
      channels.set(keyOf(ev), {
        title: ev.title || ev.id, model: ev.model || "", id: ev.id || "",
        bg: !!ev.bg, tool: "", tools: 0, state: ev.state || "done",
        ozet: ev.ozet || "", open: false,
      });
    }
    prune();
    render();
    // Gerçekten koşan kanal varsa güverte açık gelsin; yoksa rozet yeter —
    // yetim/bitmiş envanter kullanıcı tıklayınca görünür.
    if (anyRunning()) open();
    else if (!pinned) hide();
  }

  // Bitmiş kanal envanteri sınırlı: en eski bitenler düşer, koşanlar kalır.
  function prune() {
    const done = [...channels.entries()].filter(([, c]) => c.state !== "run");
    for (let i = 0; i < done.length - KEEP_DONE; i++) channels.delete(done[i][0]);
  }

  // --- çizim -----------------------------------------------------------

  function render() {
    body.replaceChildren();
    const list = [...channels.values()];
    if (!list.length) {
      body.append(el("p", "orch-blank", t("Şu an alt ajan yok. Dornick bir işi böldüğünde kanallar burada belirir.")));
    }
    for (const ch of list) body.append(card(ch));

    const running = list.filter(c => c.state === "run").length;
    if (running > 0) {
      status.textContent = t("Şef bekliyor · ") + running + t(" kanal çalışıyor");
      status.className = "orch-status waiting";
    } else if (list.some(c => c.state === "yetim")) {
      status.textContent = t("Yarım kalan yardımcı var — istersen sürdürülebilir");
      status.className = "orch-status yetim";
    } else if (list.length) {
      status.textContent = t("Şef sürüyor · tüm kanallar bitti");
      status.className = "orch-status done";
    } else {
      status.textContent = t("Şef hazır");
      status.className = "orch-status";
    }

    // Alt bilgi: aynı anda koşabilecek yardımcı sınırı (context.max_agents).
    foot.replaceChildren();
    if (maxAgents != null) {
      foot.append(el("span", "orch-cap",
        t("Eşzamanlı yardımcı sınırı: ") + maxAgents + t(" · ayarlardan değişir")));
    }
  }

  function card(ch) {
    const wrap = el("div", "orch-ch " + ch.state);
    const top = el("div", "orch-ch-top");
    top.append(el("span", "orch-ch-dot"));
    top.append(el("span", "orch-ch-title", ch.title));
    if (ch.bg) top.append(el("span", "orch-ch-bg", t("arka plan")));
    if (ch.model) top.append(el("span", "orch-ch-model", shortModel(ch.model)));
    wrap.append(top);

    const line = el("div", "orch-ch-line");
    if (ch.state === "run") {
      const act = (ch.tool ? "▶ " + ch.tool : t("Düşünüyor…"))
        + (ch.hedef ? " · " + ch.hedef : "");
      line.append(el("span", "orch-ch-act", act));
    } else if (ch.state === "fail") {
      line.append(el("span", "orch-ch-act fail", t("Hata verdi")));
    } else if (ch.state === "yetim") {
      line.append(el("span", "orch-ch-act yetim", t("Yarım kaldı")));
    } else {
      line.append(el("span", "orch-ch-act ok", t("Bitti")));
    }
    // Yetimde araç sayacı yok: geçen oturumun sayısı bilinmiyor, "0 araç"
    // yazmak yanlış bilgi olurdu.
    if (ch.state !== "yetim") {
      line.append(el("span", "orch-ch-count", ch.tools + t(" araç")));
    }
    const meter = formatUsage(ch.usage);
    if (meter) line.append(el("span", "orch-ch-meter", meter));
    wrap.append(line);

    if (ch.state === "run" && ch.acts && ch.acts.length) {
      const list = el("div", "orch-ch-acts");
      for (const a of ch.acts.slice(-KEEP_ACTS)) {
        const mark = a.phase === "fail" ? "✗"
          : a.phase === "ok" ? "✓" : "·";
        const row = el("div", "orch-ch-act-row" + (a.phase === "fail" ? " err" : ""));
        row.append(el("span", "orch-ch-act-mark", mark));
        row.append(el("b", null, a.name || ""));
        if (a.hedef) row.append(el("span", "orch-ch-act-hedef", a.hedef));
        list.append(row);
      }
      wrap.append(list);
    }

    if (ch.state === "yetim" && ch.id) {
      const acts = el("div", "orch-ch-resume-row");
      const devam = el("button", "orch-resume", t("Devam et"));
      devam.type = "button";
      devam.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        devam.disabled = true;
        devam.textContent = t("Sürdürülüyor…");
        try {
          await fetch("/api/gorevler/devam", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: "c:" + ch.id }),
          });
        } catch { /* yoklama/SSE günceller */ }
        // Snapshot tazelensin — koşuya geçince kart run olur.
        try {
          const s = await (await fetch("/api/state")).json();
          if (s && s.channels) seed(s.channels);
        } catch { render(); }
      });
      // İptal: yarım kalan iş bir daha dirilmesin ("devam et var ama
      // iptal et yok" — canlı istek, 31.08). Kalıcı: sunucu çocuğun
      // günlüğüne kapanış yazar; açılış taraması artık atlar.
      const iptal = el("button", "orch-resume orch-cancel", t("İptal et"));
      iptal.type = "button";
      iptal.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        iptal.disabled = true;
        iptal.textContent = t("İptal ediliyor…");
        try {
          await fetch("/api/gorevler/iptal", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: "c:" + ch.id }),
          });
        } catch { /* kanal olayı günceller */ }
        try {
          const s = await (await fetch("/api/state")).json();
          if (s && s.channels) seed(s.channels);
        } catch { render(); }
      });
      acts.append(devam, iptal);
      wrap.append(acts);
    }

    // Biten kanal: tıklayınca özet değil TAM rapor — artifact gibi Viewer.
    if (ch.state !== "run") {
      wrap.classList.add("clickable");
      wrap.title = t("Raporu aç");
      wrap.addEventListener("click", (ev) => {
        ev.stopPropagation();
        if (ch.deliverable && ch.deliverable.url && typeof Viewer !== "undefined" && Viewer.page) {
          Viewer.page(ch.deliverable.url, ch.title);
          return;
        }
        if (ch.id && typeof Viewer !== "undefined" && Viewer.page) {
          Viewer.page("/gorev-rapor/" + encodeURIComponent(ch.id) + "/", ch.title);
          return;
        }
        ch.open = !ch.open;
        render();
      });
      if (ch.open && !ch.id) {
        wrap.append(el("div", "orch-ch-ozet", ch.ozet || t("(özet yok)")));
      }
    }
    return wrap;
  }

  const shortModel = (m) => {
    const s = String(m);
    const cut = s.split("/").pop();
    return cut.length > 22 ? cut.slice(0, 22) + "…" : cut;
  };

  function formatUsage(u) {
    if (!u) return "";
    const g = Number(u.girdi || 0) + Number(u.cikti || 0);
    if (!g) return "";
    return g >= 1000 ? (g / 1000).toFixed(1) + "k tok" : g + " tok";
  }

  // Ayarlardaki yardımcı sınırını göstermek için okunuyor (bilgi amaçlı).
  let maxAgents = null;
  async function loadCap() {
    try {
      const s = await (await fetch("/api/settings")).json();
      const ma = s && s.context && s.context.max_agents;
      if (typeof ma === "number") maxAgents = ma;
    } catch { /* önemli değil */ }
  }

  // --- güverte ---------------------------------------------------------

  function open() {
    deck.hidden = false;
    clearTimeout(fadeTimer);
    document.body.classList.add("orch-open");
  }
  function hide() {
    deck.hidden = true;
    document.body.classList.remove("orch-open");
  }
  function toggle() {
    if (deck.hidden) { pinned = true; open(); render(); }
    else { pinned = false; hide(); }
  }

  document.getElementById("orchestra").addEventListener("click", toggle);
  document.getElementById("orch-close").addEventListener("click", () => { pinned = false; hide(); });
  loadCap();

  return { start, tool, end, wait, toggle, seed };
})();
