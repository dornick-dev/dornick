// Brain regions (roadmap Phase 6.1) and the day view (6.3).
//
// The network in scene.js is the hippocampus. Around it sits a FIXED
// template — the other regions are gauges, not a second graph:
//
//   prefrontal   goal strip at the top (Mind.goals)
//   cortex       frozen grey band — the remote model; never animates
//   cortex patch the small colour on it — the base writer (tanima.durum())
//   cold store   the ring around the network (scene.js draws it) + badge
//   amygdala     a small node that flashes with surprise (remember())
//   thalamus     ring gauge: pressure, rhythm clock, wakefulness, 4 states
//   brainstem    a single pulse line — the timer (uyku)
//   identity     a sheet: kimlik.md, sentence → evidence nodes
//   temperament  a sheet: five axes, three marks
//   world map    a colour inside the hippocampus (scene.js)
//
// Simple by default, details on demand (live: "too complicated, even I
// drown in this much detail"): the panel shows ONE status block — an icon,
// a plain sentence, a sleep-need bar — and the instrument strip above
// opens only with "Ayrıntılar". Both render from the same `state`; the
// SSE / poll path is one.
//
// Honesty limit: the regions are a metaphor. Every region's tooltip names
// the code it represents (REGIONS below); the mapping is instructive
// because it is consistent, not because it is biologically true.

Lang.add({
  "Hipokampus": "Hippocampus", "Soğuk depo": "Cold store", "Korteks": "Cortex",
  "Korteks yaması": "Cortex patch", "Prefrontal": "Prefrontal", "Amigdala": "Amygdala",
  "Talamus": "Thalamus", "Beyin sapı": "Brainstem", "Kimlik": "Identity",
  "Mizaç": "Temperament", "Dünya haritası": "World map", "Ağ": "Web", "Gece": "Night",
  "Bölge bir metafordur; biyolojik sadakat iddiası yok.":
    "The region is a metaphor; no claim of biological fidelity.",
  "Temsil ettiği kod": "Code it stands for",
  "hedef yok": "no goals", "tamam": "done", "düştü": "dropped",
  "uyanık": "awake", "uykulu": "sleepy", "uyuyor": "asleep", "uyanıyor": "waking",
  "kestirme": "nap", "yorgun": "tired", "basınç": "pressure", "eşik": "threshold",
  "borç": "debt", "uyanıklık": "wakefulness", "ritim": "rhythm",
  "tahmini uyanma": "expected wake", "kafein": "caffeine", "döngü": "cycle",
  "derin": "deep", "hafif": "light", "rem": "REM",
  "bu bölge donmuş: uzak model": "this region is frozen: the remote model",
  "yama: taban yazıcı": "patch: the base writer",
  "eğitimde": "training", "sınavı geçti": "passed the exam", "kapalı": "off", "hazır değil": "not ready",
  "Kanıt düğümleri hipokampusta yanar": "Evidence nodes light in the hippocampus",
  "İtiraz et": "Object", "Kimlik belgesi boş — gece henüz cümle yazmadı.":
    "The identity document is empty — the night has not written a sentence yet.",
  "İtiraz sohbete gider: cümle belgeden düşer, kanıtına ders bağlanır.":
    "The objection goes to the conversation: the sentence leaves the document, a lesson attaches to its evidence.",
  "Kimlik belgesindeki şu cümleye itiraz ediyorum": "I object to this sentence in the identity document",
  "Bu model böyle geldi": "This is how the model came", "model tabanı (ölçülen)": "model baseline (measured)",
  "hedef (öğrenilen / elle)": "target (learned / by hand)", "ulaşılan": "reached",
  "ulaşılan: henüz ölçülmüyor": "reached: not measured yet",
  "yenilik": "novelty", "sonuc": "outcome", "sosyal": "social", "sebat": "persistence", "temkin": "caution",
  "sürpriz": "surprise", "kaldıraç": "leverage", "kelime": "words",
  "Kayıt açıldı": "Record opened", "soğuk depodan ısındı": "warmed from the cold store",
  // The simple block.
  "Uyanık. Sen yokken uyuyup öğrendiklerini pekiştirir.":
    "Awake. While you are away it sleeps and consolidates what it learned.",
  "Uyanık — bu gece uyumayacak (kafein).": "Awake — it will not sleep tonight (caffeine).",
  "Uykulu — birazdan uyur.": "Sleepy — it will sleep soon.",
  "Uyuyor: günün konuşmalarını tekrar ediyor": "Asleep: replaying the day's conversations",
  "Uyanıyor.": "Waking up.", "Kestiriyor: kısa bir mola.": "Napping: a short break.",
  "Dün gece": "Last night", "gecesi": "night", "konuşma tekrar edildi": "conversations replayed",
  "ders çıkardı": "lessons drawn", "Uyku ihtiyacı": "Sleep need",
  "Ayrıntılar ▸": "Details ▸", "Ayrıntıları gizle ▾": "Hide details ▾",
  "Uyanıklık": "Wakefulness", "Basınç": "Pressure", "Sürpriz": "Surprise",
  "sakin": "calm", "orta": "medium", "yüksek": "high",
  "Genelde": "Usually", "arası buradasın": "you are here", "tahmini gece": "expected night",
  "Ritmini henüz öğreniyor": "Still learning your rhythm", "gün": "days",
});

const Regions = (() => {
  // The table from the roadmap (6.1): name, what it stands for, and the
  // SOURCE — the code the region represents. Shown in every tooltip.
  const REGIONS = {
    hippocampus: { name: "Hipokampus",
      what: "sıcak düğümler (sicak=1) ve kenarları: indeks ve çağrışım",
      code: "store.links(), recall() izi" },
    cold: { name: "Soğuk depo",
      what: "sicak=0 düğümler: FTS'ten ulaşılır, kendiliğinden gelmez; open() edilince halkadan merkeze süzülür",
      code: "node.sicak" },
    cortex: { name: "Korteks",
      what: "uzak model: dünya bilgisi, dil; yazılamaz — bu bölge donmuş: uzak model",
      code: "yok (uzak model)" },
    patch: { name: "Korteks yaması",
      what: "taban yazıcı (10.8M), plastik tek parça; gece ince ayarında nabız atar, sınavı geçince kalıcı renk",
      code: "tanima.durum()" },
    prefrontal: { name: "Prefrontal",
      what: "hedef yığını ve açık goal düğümleri; aktif hedefler yanar, done sönerek düşer",
      code: "Mind.goals()" },
    amygdala: { name: "Amigdala",
      what: "sürpriz / önem işaretleyici; yüksek sürprizli kayıt yazılırken parlar",
      code: "remember() olayı (mind_write)" },
    thalamus: { name: "Talamus",
      what: "uyarılma kapısı: eşik, basınç, ritim, durum makinesi (uyanık / uykulu / uyuyor / uyanıyor)",
      code: "uyku.Bekci — GET /api/uyku" },
    brainstem: { name: "Beyin sapı",
      what: "tetikleyici / zamanlayıcı; tek nabız çizgisi",
      code: "uyku (zamanlayıcı)" },
    identity: { name: "Kimlik paneli",
      what: "anlatı kimliği; her cümle tıklanınca kanıt düğümleri hipokampusta yanar",
      code: ".dornick/kimlik.md — GET /api/kimlik" },
    temperament: { name: "Mizaç paneli",
      what: "beş eksen: yenilik, sonuç, sosyal, sebat, temkin; taban (ölçülen), hedef, ulaşılan",
      code: ".dornick/mizac.json — GET /api/mizac" },
    world: { name: "Dünya haritası",
      what: "world düğümleri: hipokampus içinde ayrı renk; doğrulanmamış olanlar soluk",
      code: "world düğümleri (recall.store kind=world)" },
  };

  const SLEEP_STATES = ["uyanik", "uykulu", "uyuyor", "uyaniyor"];
  const STATE_LABEL = { uyanik: "uyanık", uykulu: "uykulu", uyuyor: "uyuyor",
                        uyaniyor: "uyanıyor", kestirme: "kestirme" };
  // Phase colours (6.2): deep blue, light teal, REM purple — and a
  // pattern per phase for the ring so colour is not alone.
  const PHASE = { derin: { color: "user", dash: "" }, hafif: { color: "lesson", dash: "4 3" },
                  rem: { color: "preference", dash: "1 4" } };
  const NARROW = 430;     // below this panel width the gauges stack
  const DETAILS_KEY = "dornick-beyin-ayrinti";   // "acik" | "kapali", default closed
  const SURPRISE_FADE_MS = 90000;                // the amygdala caption calms down after this

  const $ = (id) => document.getElementById(id);
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue("--" + n).trim();
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, Number(v) || 0));
  const fmt = (v) => (Math.round(clamp(v, 0, 99) * 100) / 100).toFixed(2);

  let mind, tip, sheet, tabs;
  let state = {
    sleep: "uyanik", nap: false, tired: false, cycle: 0, phase: "",
    wakeAt: "", caffeine: "", pressure: null, threshold: null, debt: null,
    goals: new Map(), patch: {}, cold: 0, world: 0,
    // The simple block's extra facts: the last finished night and the
    // progress of the night now playing (fed by night.js).
    lastNight: null,                 // { date, replayed, lessons, report, summary }
    night: { done: 0, total: 0 },
    nextNight: "", rhythmHours: [], rhythmDays: 0,
  };
  let raf = null, lastBeat = 0;
  let amygdalaLevel = 0, amygdalaAt = 0;
  let sheetName = "";
  let details = false;
  let lastNightLooked = false;      // the /api/gece fallback ran once

  // --- tooltips: every region says what code it stands for --------------
  function tipText(key) {
    const r = REGIONS[key];
    if (!r) return "";
    return t(r.name) + " — " + t(r.what) + "\n" + t("Temsil ettiği kod") + ": " + r.code
      + "\n" + t("Bölge bir metafordur; biyolojik sadakat iddiası yok.");
  }

  function showTip(key, x, y, extra) {
    if (!tip) return;
    tip.textContent = tipText(key) + (extra ? "\n" + extra : "");
    tip.hidden = false;
    const w = tip.offsetWidth || 240, h = tip.offsetHeight || 60;
    tip.style.left = Math.max(6, Math.min(window.innerWidth - w - 6, x - w / 2)) + "px";
    tip.style.top = Math.max(6, y - h - 14) + "px";
  }
  const hideTip = () => { if (tip) tip.hidden = true; };

  function bindTips(root) {
    for (const el of root.querySelectorAll("[data-region]")) {
      const key = el.dataset.region;
      // Native title too: reachable by keyboard and screen readers.
      el.title = tipText(key);
      el.addEventListener("mouseenter", (ev) => {
        const r = el.getBoundingClientRect();
        showTip(key, r.left + r.width / 2, r.top, el.dataset.extra || "");
        ev.stopPropagation();
      });
      el.addEventListener("mouseleave", hideTip);
    }
  }

  // --- init ---------------------------------------------------------------
  function init() {
    mind = $("mind");
    tip = $("region-tip");
    sheet = $("regions-sheet");
    tabs = $("regions-tabs");
    if (!mind || !tabs) return;
    bindTips(mind);

    // The cold ring lives on the canvas; the scene reports hover and the
    // overlay draws the tooltip.
    if (typeof Scene !== "undefined" && Scene.onColdRing) {
      Scene.onColdRing((at) => {
        if (!at) { hideTip(); return; }
        showTip("cold", at.x, at.y, state.cold.toLocaleString("tr-TR") + " " + t("soğuk"));
      });
    }

    tabs.addEventListener("click", (ev) => {
      const b = ev.target.closest("button[data-sheet]");
      if (!b) return;
      openSheet(b.dataset.sheet === sheetName ? "" : b.dataset.sheet);
    });

    // Details on demand: the strip opens with the toggle, the choice is
    // remembered; default closed.
    let saved = null;
    try { saved = localStorage.getItem(DETAILS_KEY); } catch { /* file:// */ }
    setDetails(saved === "acik", false);
    const toggle = $("brain-details-toggle");
    if (toggle) toggle.addEventListener("click", () => setDetails(!details, true));
    const reportLink = $("brain-simple-report");
    if (reportLink) reportLink.addEventListener("click", () => openSheet(sheetName === "report" ? "" : "report"));

    // Narrow panel: the gauges stack instead of sitting in a row.
    const watch = new ResizeObserver(() => {
      mind.classList.toggle("narrow", mind.getBoundingClientRect().width < NARROW);
    });
    watch.observe(mind);

    refresh();
    setInterval(refresh, 30000);
    document.addEventListener("visibilitychange", () => document.hidden ? stopLoop() : startLoop());
    startLoop();
  }

  // --- data: what the template reads --------------------------------------
  async function refresh() {
    try {
      const u = await (await fetch("/api/uyku")).json();
      if (u && u.basinc) {
        state.pressure = u.basinc;
        state.threshold = u.esik || null;
        state.debt = u.borc || null;
      }
      // The watchman's own state machine, when a daemon runs. A replay in
      // progress owns the state word; the poll must not fight it.
      if (u && SLEEP_STATES.includes(u.durum) && !replaying()) state.sleep = u.durum;
      if (u && "kafein" in u) state.caffeine = String(u.kafein || "");
      if (u && "sonraki_gece" in u) state.nextNight = String(u.sonraki_gece || "");
      if (u && u.ritim) {
        state.rhythmDays = Number(u.ritim.gun) || 0;
        state.rhythmHours = Array.isArray(u.ritim.saatler) ? u.ritim.saatler.map(Number) : [];
      }
      if (u && u.son_gece && u.son_gece.rapor && Object.keys(u.son_gece.rapor).length) {
        const r = u.son_gece.rapor;
        state.lastNight = { date: String(u.son_gece.bitti || "").slice(0, 10),
                            replayed: Number(r.replayed) || 0, lessons: Number(r.lessons_written) || 0,
                            report: r, summary: null };
        lastNightLooked = true;
      }
    } catch { /* server not up yet */ }
    if (!lastNightLooked) await lookupLastNight();
    try {
      const b = await (await fetch("/api/bolgeler")).json();
      if (b) {
        state.cold = Number(b.soguk) || 0;
        state.world = Number(b.dunya) || 0;
        if (typeof Scene !== "undefined" && Scene.cold) Scene.cold(state.cold);
        state.goals = new Map((b.hedefler || []).map((g) => [g.id, { text: g.metin, status: g.durum }]));
        state.patch = b.yama || {};
        renderGoals();
        renderPatch();
      }
    } catch { /* same */ }
    renderThalamus();
  }

  // --- prefrontal: the goal strip -------------------------------------------
  function renderGoals() {
    const box = $("prefrontal-goals");
    if (!box) return;
    box.textContent = "";
    const rows = [...state.goals.entries()].filter(([, g]) => g.status !== "dropped");
    if (!rows.length) {
      const none = document.createElement("span");
      none.className = "goal-chip none";
      none.textContent = t("hedef yok");
      box.append(none);
      return;
    }
    for (const [id, g] of rows.slice(-6)) {
      const chip = document.createElement("span");
      chip.className = "goal-chip " + (g.status === "active" ? "lit" : "done");
      chip.dataset.goal = id;
      chip.textContent = g.text.length > 26 ? g.text.slice(0, 25) + "…" : g.text;
      chip.title = g.text + (g.status === "active" ? "" : " · " + t("tamam"));
      box.append(chip);
    }
  }

  // A goal was pushed: the strip lights.
  function goalAdded(id, text) {
    state.goals.set(id, { text: String(text || id), status: "active" });
    renderGoals();
    const chip = $("prefrontal-goals") && $("prefrontal-goals").querySelector('[data-goal="' + CSS.escape(id) + '"]');
    if (chip) { chip.classList.add("born"); setTimeout(() => chip.classList.remove("born"), 1200); }
  }

  // done: fades and drops off the strip.
  function goalStatus(id, status) {
    const g = state.goals.get(id);
    if (!g) return;
    g.status = status;
    const chip = $("prefrontal-goals") && $("prefrontal-goals").querySelector('[data-goal="' + CSS.escape(id) + '"]');
    if (chip && status !== "active") {
      chip.classList.add("fall");
      setTimeout(() => { if (status === "done") state.goals.delete(id); renderGoals(); }, 1400);
    } else renderGoals();
  }

  // --- cortex patch: the base writer ------------------------------------------
  function renderPatch() {
    const el = $("cortex-patch");
    if (!el) return;
    const p = state.patch || {};
    el.classList.toggle("training", !!p.kosuyor);
    el.classList.toggle("passed", !!p.hazir);
    el.classList.toggle("off", !p.on);
    const word = p.kosuyor ? t("eğitimde") : p.hazir ? t("sınavı geçti") : p.on ? t("hazır değil") : t("kapalı");
    el.dataset.extra = t("yama: taban yazıcı") + " · " + word + (p.son ? " · " + p.son : "");
    el.title = tipText("patch") + "\n" + el.dataset.extra;
  }
  function patch(stateWord) {
    // From the SSE `tanima` event: running → pulse, ready → permanent colour.
    state.patch = { ...(state.patch || {}), kosuyor: stateWord === "running" || stateWord === "kosuyor",
                    hazir: stateWord === "ready" || stateWord === "hazir" || !!(state.patch && state.patch.hazir),
                    on: true };
    renderPatch();
  }

  // --- amygdala: surprise ------------------------------------------------------
  function amygdala(surprise) {
    amygdalaLevel = clamp(surprise === undefined || surprise === null ? 0.6 : surprise, 0.1, 1);
    amygdalaAt = Date.now();
    renderAmygdalaNote();
    const dot = $("amygdala-dot");
    if (!dot) return;
    dot.style.setProperty("--level", amygdalaLevel.toFixed(2));
    dot.classList.remove("flash");
    void dot.offsetWidth;          // restart the animation
    dot.classList.add("flash");
    const box = dot.closest("[data-region]");
    if (box) box.dataset.extra = t("sürpriz") + ": " + amygdalaLevel.toFixed(2);
  }

  // --- thalamus: the ring gauge -----------------------------------------------
  const R = 44, C = 60;              // ring radius and centre in the 120×120 box
  const arc = (a0, a1, r) => {
    const p = (a) => [C + Math.cos(a) * r, C + Math.sin(a) * r];
    const [x0, y0] = p(a0), [x1, y1] = p(a1);
    const large = a1 - a0 > Math.PI ? 1 : 0;
    return "M" + x0.toFixed(2) + " " + y0.toFixed(2) + " A" + r + " " + r + " 0 " + large + " 1 " + x1.toFixed(2) + " " + y1.toFixed(2);
  };

  function renderThalamus() {
    const svg = $("thalamus");
    if (!svg) return;
    const p = state.pressure || { total: 0, strengthening: 0, debt: 0, heat: 0 };
    const upper = state.threshold && state.threshold.ust ? Number(state.threshold.ust) : 1;
    const lower = state.threshold && state.threshold.alt ? Number(state.threshold.alt) : upper / 3;
    const fill = clamp(p.total / upper, 0, 1);
    // Slices per component, sized by their share of the total. The
    // weights live in sleep.py; here only the proportion is shown, and the
    // tooltip says so.
    const parts = [["strengthening", "solid"], ["debt", "dash"], ["heat", "dot"]];
    const sum = parts.reduce((s, [k]) => s + Math.max(0, Number(p[k]) || 0), 0) || 1;
    const start = -Math.PI / 2, span = Math.PI * 2 * fill;
    let a = start;
    for (const [key, pat] of parts) {
      const el = svg.querySelector("[data-slice=" + key + "]");
      if (!el) continue;
      const share = Math.max(0, Number(p[key]) || 0) / sum;
      const a1 = a + span * share;
      el.setAttribute("d", share > 0 && span > 0.01 ? arc(a, a1, R) : "");
      el.dataset.pattern = pat;
      a = a1;
    }
    // Threshold ticks.
    const tick = (name, value) => {
      const el = svg.querySelector("[data-tick=" + name + "]");
      if (!el) return;
      const ang = start + Math.PI * 2 * clamp(value / upper, 0, 1);
      el.setAttribute("x1", (C + Math.cos(ang) * (R - 6)).toFixed(1));
      el.setAttribute("y1", (C + Math.sin(ang) * (R - 6)).toFixed(1));
      el.setAttribute("x2", (C + Math.cos(ang) * (R + 6)).toFixed(1));
      el.setAttribute("y2", (C + Math.sin(ang) * (R + 6)).toFixed(1));
    };
    tick("ust", upper); tick("alt", lower);

    // State pattern: the class drives the SVG (four distinct drawings).
    for (const s of SLEEP_STATES) svg.classList.toggle("state-" + s, state.sleep === s);
    svg.classList.toggle("nap", !!state.nap);
    svg.classList.toggle("tired", !!state.tired);
    const stateWord = svg.querySelector("[data-text=state]");
    if (stateWord) stateWord.textContent = t(state.nap ? "kestirme" : STATE_LABEL[state.sleep] || state.sleep);
    const cyc = svg.querySelector("[data-text=cycle]");
    if (cyc) cyc.textContent = state.cycle ? state.cycle + " · " + t(state.phase || "") : "";
    const ring = svg.querySelector("[data-ring=phase]");
    if (ring) {
      const ph = PHASE[state.phase];
      ring.setAttribute("stroke", ph ? css(ph.color) : "transparent");
      ring.setAttribute("stroke-dasharray", ph ? ph.dash : "");
    }
    // Wakefulness: derived here as 1 − pressure/threshold. The endpoint
    // carries no `uyaniklik` of its own yet; the tooltip says derived.
    const wake = clamp(1 - fill, 0, 1);
    const wakeEl = $("thalamus-wake");
    if (wakeEl) wakeEl.textContent = t("Uyanıklık") + " %" + Math.round(wake * 100);
    const pressEl = $("thalamus-pressure");
    if (pressEl) pressEl.textContent = t("Basınç") + " " + num(p.total) + " / " + num(upper);
    const caff = $("thalamus-caffeine");
    if (caff) { caff.hidden = !state.caffeine; caff.textContent = state.caffeine ? t("kafein") + " · " + state.caffeine : ""; }
    const box = svg.closest("[data-region]") || svg;
    box.dataset.extra = t("basınç") + " " + fmt(p.total) + " / " + t("eşik") + " " + fmt(upper)
      + (state.debt ? " · " + t("borç") + " " + (state.debt.oturum || 0) : "")
      + " · " + t("uyanıklık") + " " + wake.toFixed(2) + " (1 − basınç/eşik)";
    box.title = tipText("thalamus") + "\n" + box.dataset.extra;
    renderClock();
    renderAmygdalaNote();
    renderSimple();
  }

  // One decimal, Turkish comma: "2,1".
  const num = (v) => clamp(v, 0, 99).toLocaleString("tr-TR", { maximumFractionDigits: 1 });
  const pad2 = (h) => String(h).padStart(2, "0");

  // Is a recorded night being replayed? Then night.js owns the state word.
  function replaying() {
    if (typeof Night === "undefined" || !Night.stats) return false;
    const st = Night.stats();
    return !!(st.date && !st.live);
  }

  // The last finished night, when no daemon reports one: newest file's summary.
  async function lookupLastNight() {
    lastNightLooked = true;
    try {
      const list = await (await fetch("/api/gece")).json();
      const date = list && Array.isArray(list.geceler) ? list.geceler[0] : "";
      if (!date) return;
      const data = await (await fetch("/api/gece/" + encodeURIComponent(date))).json();
      if (!data || !data.ozet) return;
      if (state.lastNight && state.lastNight.report) return;   // the daemon answered meanwhile
      state.lastNight = { date, replayed: Number(data.ozet.tekrar) || 0, lessons: null,
                          report: null, summary: data.ozet };
      renderSimple();
    } catch { /* offline */ }
  }

  // --- the simple block: icon + sentence + bar ------------------------------
  function sentence() {
    const n = state.night;
    if (state.nap) return t("Kestiriyor: kısa bir mola.");
    switch (state.sleep) {
      case "uykulu": return t("Uykulu — birazdan uyur.");
      case "uyuyor": {
        const count = n.total > n.done ? n.done + "/" + n.total : n.done ? String(n.done) : "";
        return t("Uyuyor: günün konuşmalarını tekrar ediyor") + (count ? " (" + count + ")" : "") + ".";
      }
      case "uyaniyor": return t("Uyanıyor.");
      default:
        return state.caffeine ? t("Uyanık — bu gece uyumayacak (kafein).")
                              : t("Uyanık. Sen yokken uyuyup öğrendiklerini pekiştirir.");
    }
  }

  function nightLabel(date) {
    const d = new Date();
    const today = d.toISOString().slice(0, 10);
    d.setDate(d.getDate() - 1);
    const yesterday = d.toISOString().slice(0, 10);
    return date === today || date === yesterday ? t("Dün gece") : date + " " + t("gecesi");
  }

  function renderSimple() {
    const box = $("brain-simple");
    if (!box) return;
    const word = state.nap ? "uykulu" : (SLEEP_STATES.includes(state.sleep) ? state.sleep : "uyanik");
    box.dataset.state = word;
    const line = $("brain-simple-line");
    if (line) line.textContent = sentence();
    // "Dün gece 18 konuşma tekrar edildi, 2 ders çıkardı."
    const last = $("brain-simple-last"), lastText = $("brain-simple-last-text");
    if (last && lastText) {
      const ln = state.lastNight;
      if (ln && ln.date) {
        lastText.textContent = nightLabel(ln.date) + " " + ln.replayed + " " + t("konuşma tekrar edildi")
          + (ln.lessons ? ", " + ln.lessons + " " + t("ders çıkardı") : "") + ".";
        last.hidden = false;
      } else last.hidden = true;
    }
    // Sleep need: pressure over the upper threshold, whole percent only.
    const p = state.pressure ? Number(state.pressure.total) || 0 : 0;
    const upper = state.threshold && state.threshold.ust ? Number(state.threshold.ust) : 1;
    const pct = Math.round(clamp(p / upper, 0, 1) * 100);
    const fill = $("brain-simple-fill"), pctEl = $("brain-simple-pct"), bar = $("brain-simple-bar");
    if (fill) fill.style.width = pct + "%";
    if (pctEl) pctEl.textContent = "%" + pct;
    if (bar) bar.setAttribute("aria-valuenow", String(pct));
    box.classList.toggle("high", pct >= 80);
  }

  // The strip opens and closes; the night tab lives in it.
  function setDetails(on, remember) {
    details = !!on;
    if (mind) mind.classList.toggle("details", details);
    const strip = $("regions-bottom");
    if (strip) strip.hidden = !details;
    const toggle = $("brain-details-toggle");
    if (toggle) {
      toggle.textContent = details ? t("Ayrıntıları gizle ▾") : t("Ayrıntılar ▸");
      toggle.setAttribute("aria-expanded", details ? "true" : "false");
      toggle.classList.toggle("on", details);
    }
    if (!details && sheetName === "night") openSheet("");
    if (remember) { try { localStorage.setItem(DETAILS_KEY, details ? "acik" : "kapali"); } catch { /* file:// */ } }
    if (typeof Scene !== "undefined" && Scene.resume) Scene.resume();   // the hole moved
  }

  // Night hooks for the simple block (night.js calls them).
  function nightProgress(done, total) {
    state.night = { done: Number(done) || 0, total: Number(total) || 0 };
    renderSimple();
  }
  function lastNight(info) {
    if (!info || !info.date) return;
    state.lastNight = { date: String(info.date), replayed: Number(info.replayed) || 0,
                        lessons: info.lessons === null || info.lessons === undefined ? null : Number(info.lessons) || 0,
                        report: info.report || null, summary: info.summary || null };
    lastNightLooked = true;
    renderSimple();
  }

  // The amygdala caption: "Sürpriz: sakin" — the last flash, fading with time.
  function renderAmygdalaNote() {
    const note = $("amygdala-note");
    if (!note) return;
    const fresh = amygdalaAt && Date.now() - amygdalaAt < SURPRISE_FADE_MS;
    const level = fresh ? amygdalaLevel : 0;
    note.textContent = t("Sürpriz") + ": " + t(level >= 0.7 ? "yüksek" : level >= 0.3 ? "orta" : "sakin");
  }

  // The rhythm clock: a 24h dial, the hour hand now, a marker at the
  // expected wake time. The rhythm curve itself is not on an endpoint
  // yet; the dial shows only what it has.
  function renderClock() {
    const svg = $("rhythm");
    if (!svg) return;
    const now = new Date();
    const hour = now.getHours() + now.getMinutes() / 60;
    const ang = (hour / 24) * Math.PI * 2 - Math.PI / 2;
    const hand = svg.querySelector("[data-hand]");
    if (hand) {
      hand.setAttribute("x2", (40 + Math.cos(ang) * 26).toFixed(1));
      hand.setAttribute("y2", (40 + Math.sin(ang) * 26).toFixed(1));
    }
    const mark = svg.querySelector("[data-mark=wake]");
    if (mark) {
      const m = /(\d{1,2}):(\d{2})/.exec(state.wakeAt || "");
      if (m) {
        const h = (Number(m[1]) + Number(m[2]) / 60) / 24 * Math.PI * 2 - Math.PI / 2;
        mark.setAttribute("cx", (40 + Math.cos(h) * 31).toFixed(1));
        mark.setAttribute("cy", (40 + Math.sin(h) * 31).toFixed(1));
        mark.removeAttribute("hidden");
      } else mark.setAttribute("hidden", "");
    }
    const label = svg.querySelector("[data-text=wake]");
    if (label) label.textContent = state.wakeAt ? state.wakeAt.slice(-5) : "";
    const box = svg.closest("[data-region]");
    if (box) box.dataset.extra = t("ritim") + (state.wakeAt ? " · " + t("tahmini uyanma") + " " + state.wakeAt : "");
    // "Genelde 09–18 arası buradasın · tahmini gece 23:00" — from the
    // watchman's rhythm; before a week of data it says it is learning.
    const note = $("rhythm-note");
    if (note) {
      const parts = [];
      const hours = state.rhythmHours;
      if (hours.length) parts.push(t("Genelde") + " " + pad2(Math.min(...hours)) + "–" + pad2(Math.max(...hours) + 1) + " " + t("arası buradasın"));
      else if (state.rhythmDays < 7) parts.push(t("Ritmini henüz öğreniyor") + " (" + Math.floor(state.rhythmDays) + "/7 " + t("gün") + ")");
      const m = /T(\d{2}:\d{2})/.exec(state.nextNight || "");
      if (m) parts.push(t("tahmini gece") + " " + m[1]);
      else if (state.wakeAt) parts.push(t("tahmini uyanma") + " " + state.wakeAt.slice(-5));
      note.textContent = parts.join(" · ");
    }
  }

  // Night hooks (called by night.js).
  function sleep(word) { if (SLEEP_STATES.includes(word)) state.sleep = word; renderThalamus(); }
  function cycle(no, phase) { state.cycle = Number(no) || 0; state.phase = String(phase || ""); renderThalamus(); }
  function wakeAt(text) { state.wakeAt = String(text || ""); renderClock(); }
  function caffeine(text) { state.caffeine = String(text || ""); renderThalamus(); }
  function nap(on) { state.nap = !!on; renderThalamus(); }
  function tired(on) { state.tired = !!on; renderThalamus(); }
  function flash() {
    const svg = $("thalamus");
    if (!svg) return;
    svg.classList.remove("flash"); void svg.getBoundingClientRect(); svg.classList.add("flash");
  }

  // --- brainstem: the pulse line -------------------------------------------
  // One line, beating. Faster under pressure, slow and shallow asleep. This
  // is the timer, so it keeps ticking through a frozen night picture.
  const BEATS = 160;
  const beats = new Float32Array(BEATS);
  let beatPhase = 0;

  function loop(now) {
    raf = requestAnimationFrame(loop);
    if (now - lastBeat < 40) return;
    lastBeat = now;
    const p = state.pressure ? clamp(state.pressure.total / ((state.threshold && state.threshold.ust) || 1), 0, 1) : 0;
    const asleep = state.sleep === "uyuyor";
    const period = asleep ? 2400 : 1400 - p * 600;
    beatPhase = (beatPhase + 40 / period) % 1;
    const k = beatPhase;
    const spike = k < 0.08 ? Math.sin(k / 0.08 * Math.PI) : k < 0.16 ? -0.35 * Math.sin((k - 0.08) / 0.08 * Math.PI) : 0;
    beats.copyWithin(0, 1);
    beats[BEATS - 1] = spike * (asleep ? 0.45 : 0.6 + p * 0.4);
    const line = $("brainstem-line");
    if (line) {
      let d = "";
      for (let i = 0; i < BEATS; i++) d += (i ? " " : "") + i + "," + (12 - beats[i] * 10).toFixed(1);
      line.setAttribute("points", d);
    }
  }
  const startLoop = () => { if (raf === null) raf = requestAnimationFrame(loop); };
  const stopLoop = () => { if (raf !== null) { cancelAnimationFrame(raf); raf = null; } };

  // --- sheets: identity, temperament, night ---------------------------------
  function openSheet(name) {
    sheetName = name || "";
    for (const b of tabs.querySelectorAll("button[data-sheet]")) {
      b.classList.toggle("on", b.dataset.sheet === sheetName);
    }
    if (!sheet) return;
    sheet.hidden = !sheetName;
    sheet.textContent = "";
    sheet.dataset.sheet = sheetName;
    if (sheetName === "identity") renderIdentity();
    else if (sheetName === "temperament") renderTemperament();
    else if (sheetName === "night" && typeof Night !== "undefined") Night.renderSheet(sheet);
    else if (sheetName === "report" && typeof Night !== "undefined") Night.renderReportSheet(sheet, state.lastNight, () => openSheet(""));
    if (typeof Scene !== "undefined" && Scene.resume) Scene.resume();   // the hole moved
  }

  async function renderIdentity() {
    let doc = { cumleler: [], kelime: 0 };
    try { doc = await (await fetch("/api/kimlik")).json(); } catch { /* offline */ }
    if (sheetName !== "identity") return;
    sheet.textContent = "";
    const head = document.createElement("div");
    head.className = "sheet-head";
    head.dataset.region = "identity";
    head.textContent = t("Kimlik") + " · " + (doc.kelime || 0) + " " + t("kelime")
      + (doc.sinir ? " / " + doc.sinir : "");
    sheet.append(head);
    const note = document.createElement("p");
    note.className = "sheet-note";
    note.textContent = t("Kanıt düğümleri hipokampusta yanar");
    sheet.append(note);
    if (!doc.cumleler || !doc.cumleler.length) {
      const empty = document.createElement("p");
      empty.className = "sheet-empty";
      empty.textContent = t("Kimlik belgesi boş — gece henüz cümle yazmadı.");
      sheet.append(empty);
    }
    for (const row of doc.cumleler || []) {
      const line = document.createElement("div");
      line.className = "identity-sentence";
      const text = document.createElement("button");
      text.type = "button";
      text.className = "identity-text";
      text.textContent = row.metin;
      text.title = (row.kanit || []).join(", ");
      text.addEventListener("click", () => {
        for (const el of sheet.querySelectorAll(".identity-sentence")) el.classList.remove("on");
        line.classList.add("on");
        if (typeof Scene !== "undefined") {
          Scene.thaw();
          Scene.lightSequence(row.kanit || [], { kind: "evidence", numbered: true, group: "self" });
        }
      });
      const object = document.createElement("button");
      object.type = "button";
      object.className = "identity-object";
      object.textContent = t("İtiraz et");
      object.title = t("İtiraz sohbete gider: cümle belgeden düşer, kanıtına ders bağlanır.");
      object.addEventListener("click", () => {
        fetch("/api/chat", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: t("Kimlik belgesindeki şu cümleye itiraz ediyorum") + ': "' + row.metin + '"' }),
        }).catch(() => {});
        line.classList.add("objected");
      });
      line.append(text, object);
      sheet.append(line);
    }
    bindTips(sheet);
  }

  async function renderTemperament() {
    let data = { taban: {}, hedef: {}, ulasilan: null, model_id: "", eksenler: [] };
    try { data = await (await fetch("/api/mizac")).json(); } catch { /* offline */ }
    if (sheetName !== "temperament") return;
    sheet.textContent = "";
    const head = document.createElement("div");
    head.className = "sheet-head";
    head.dataset.region = "temperament";
    head.textContent = t("Mizaç");
    sheet.append(head);
    const note = document.createElement("p");
    note.className = "sheet-note";
    note.textContent = t("Bu model böyle geldi") + (data.model_id ? ": " + data.model_id : "") + " · "
      + t("model tabanı (ölçülen)") + " ○ · " + t("hedef (öğrenilen / elle)") + " ◆ · "
      + (data.ulasilan ? t("ulaşılan") + " ●" : t("ulaşılan: henüz ölçülmüyor"));
    sheet.append(note);
    const axes = (data.eksenler && data.eksenler.length) ? data.eksenler
      : ["yenilik", "sonuc", "sosyal", "sebat", "temkin"];
    for (const axis of axes) {
      const row = document.createElement("div");
      row.className = "axis";
      const name = document.createElement("span");
      name.className = "axis-name";
      name.textContent = t(axis);
      const bar = document.createElement("span");
      bar.className = "axis-bar";
      const put = (cls, value, glyph, label) => {
        if (value === undefined || value === null) return;
        const m = document.createElement("i");
        m.className = "axis-mark " + cls;
        m.style.left = (clamp(value, 0, 1) * 100).toFixed(1) + "%";
        m.textContent = glyph;
        m.title = label + " " + fmt(value);
        bar.append(m);
      };
      put("base", (data.taban || {})[axis], "○", t("model tabanı (ölçülen)"));
      put("target", (data.hedef || {})[axis], "◆", t("hedef (öğrenilen / elle)"));
      put("reached", data.ulasilan ? data.ulasilan[axis] : null, "●", t("ulaşılan"));
      const lev = document.createElement("span");
      lev.className = "axis-lev";
      const key = { yenilik: "novelty", sonuc: "outcome", sosyal: "social", sebat: "persistence", temkin: "caution" }[axis];
      lev.textContent = data.kaldirac && key in data.kaldirac ? t("kaldıraç") + " ×" + data.kaldirac[key] : "";
      row.append(name, bar, lev);
      sheet.append(row);
    }
    bindTips(sheet);
  }

  // --- day view: opened records --------------------------------------------
  // open(): the record glows; a cold one warms in from the ring.
  function opened(id, kind) {
    if (typeof Scene === "undefined") return;
    Scene.thaw();
    Scene.warm(id, undefined, kind);
  }

  return { init, refresh, goalAdded, goalStatus, patch, amygdala, sleep, cycle,
           wakeAt, caffeine, nap, tired, flash, opened, openSheet, tipText, REGIONS,
           nightProgress, lastNight, setDetails, details: () => details, sentence };
})();
