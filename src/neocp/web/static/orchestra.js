// Orkestra: alt ajan kanalları — "şef modu".
//
// neo bir işi böldüğünde alt ajanlar doğuyor (task aracı). Onların araç
// çağrıları ana sohbete karışmıyor; bu güverte her kanalı canlı bir kart
// olarak gösteriyor: başlığı, modeli, o an çalıştırdığı araç, kaç araç
// çağırdığı ve durumu (çalışıyor · bitti · hata). Ana ajan (şef) bu kanallar
// biterken bekliyor ve kaç kanalı beklediğini söylüyor.
//
// Kaynak canlı SSE olayları: child_start / child_tool / child_end. Bir anı
// DEĞİL — anlık koordinasyon. Kendisi çalışırken açılıyor, sabitlenebiliyor.

const Orchestra = (() => {
  const deck = document.getElementById("orch-deck");
  const body = document.getElementById("orch-body");
  const status = document.getElementById("orch-status");
  const foot = document.getElementById("orch-foot");

  // title → kanal durumu. Aynı başlıkla ikinci kez doğarsa tazeleniyor.
  const channels = new Map();
  let pinned = false;      // kullanıcı elle açtı: koşu bitince kapanmasın
  let fadeTimer = null;

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  // --- olaylar (app.js SSE'den çağırıyor) ------------------------------

  function start(ev) {
    channels.set(ev.title, {
      title: ev.title, model: ev.model || "", id: ev.id || "",
      tool: "", tools: 0, state: "run",
    });
    open();
    render();
  }

  function tool(ev) {
    const ch = channels.get(ev.title);
    if (!ch) return;
    if (ev.phase === "start") { ch.tool = ev.tool; ch.tools += 1; }
    else { ch.tool = ev.tool + (ev.phase === "fail" ? " ✗" : " ✓"); }
    render();
  }

  function end(ev) {
    const ch = channels.get(ev.title);
    if (!ch) return;
    ch.state = ev.ok ? "done" : "fail";
    ch.tool = "";
    ch.turns = ev.turns; ch.tools = ev.tools != null ? ev.tools : ch.tools;
    render();
    // Hepsi bittiyse ve sabitli değilse güverteyi bir süre sonra çek.
    if (!pinned && [...channels.values()].every(c => c.state !== "run")) {
      clearTimeout(fadeTimer);
      fadeTimer = setTimeout(() => { if (!anyRunning()) hide(); }, 6000);
    }
  }

  const anyRunning = () => [...channels.values()].some(c => c.state === "run");

  // --- çizim -----------------------------------------------------------

  function render() {
    body.replaceChildren();
    const list = [...channels.values()];
    if (!list.length) {
      body.append(el("p", "orch-blank", "Şu an alt ajan yok. neo bir işi böldüğünde kanallar burada belirir."));
    }
    for (const ch of list) body.append(card(ch));

    const running = list.filter(c => c.state === "run").length;
    if (running > 0) {
      status.textContent = "Şef bekliyor · " + running + " kanal çalışıyor";
      status.className = "orch-status waiting";
    } else if (list.length) {
      status.textContent = "Şef sürüyor · tüm kanallar bitti";
      status.className = "orch-status done";
    } else {
      status.textContent = "Şef hazır";
      status.className = "orch-status";
    }

    // Alt bilgi: eşzamanlılık sınırı (maks kanal). Ayarlardaki max_parallel.
    foot.replaceChildren();
    if (maxParallel != null) {
      foot.append(el("span", "orch-cap", "Eşzamanlı sınır: " + maxParallel + " · ayarlardan değişir"));
    }
  }

  function card(ch) {
    const wrap = el("div", "orch-ch " + ch.state);
    const top = el("div", "orch-ch-top");
    top.append(el("span", "orch-ch-dot"));
    top.append(el("span", "orch-ch-title", ch.title));
    if (ch.model) top.append(el("span", "orch-ch-model", shortModel(ch.model)));
    wrap.append(top);

    const line = el("div", "orch-ch-line");
    if (ch.state === "run") {
      line.append(el("span", "orch-ch-act", ch.tool ? "▶ " + ch.tool : "Düşünüyor…"));
    } else if (ch.state === "fail") {
      line.append(el("span", "orch-ch-act fail", "Hata verdi"));
    } else {
      line.append(el("span", "orch-ch-act ok", "Bitti"));
    }
    line.append(el("span", "orch-ch-count", ch.tools + " araç"));
    wrap.append(line);
    return wrap;
  }

  const shortModel = (m) => {
    const s = String(m);
    const cut = s.split("/").pop();
    return cut.length > 22 ? cut.slice(0, 22) + "…" : cut;
  };

  // Ayarlardaki eşzamanlılık sınırını göstermek için okunuyor (bilgi amaçlı).
  let maxParallel = null;
  async function loadCap() {
    try {
      const s = await (await fetch("/api/settings")).json();
      const mp = s && s.context && s.context.max_parallel;
      if (typeof mp === "number") maxParallel = mp;
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

  return { start, tool, end, toggle };
})();
