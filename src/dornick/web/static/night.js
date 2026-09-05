// The night animation (roadmap Phase 6.2).
//
// One feed, two sources. Live events come over the SSE channel
// (`type: "gece"`) and the poll of the current night's file; a replay
// reads `/api/gece/<date>` — the same file, the same events, the same
// order. Both go through `feed()`; there is no second code path to drift.
//
// The view reads ONLY the frozen event schema (recall/night_events.py
// SCHEMA). It never looks at recall.db: while the night writes, a reader
// racing the writer would show a half-consolidated graph as the truth.
// HANDLERS below has one entry per schema event; a test pins that.
//
// Timing is the recall trace's: STEP_MS between nodes, SIGNAL_MS for a
// hop (scene.js), divided by the replay speed. `uyku.uyandi` freezes the
// scene's event clock and stops this loop — the remaining chain stays
// faint on the sheet, nothing advances until the next night or the user
// presses play again.

Lang.add({
  "Gece": "Night", "Canlı": "Live", "Oynat": "Play", "Devam": "Resume",
  "Kayıtlı gece yok": "No recorded night", "olay": "events",
  "kalan": "remaining", "hız": "speed", "Sabah raporu": "Morning report",
  "tekrar edildi": "replayed", "devretti": "carried over", "sebep": "reason",
  "oturum": "sessions", "yeni kenar": "new edges", "ders": "lessons", "yordam": "procedures",
  "çelişki": "contradictions", "borç": "debt", "döngü": "cycles", "dikiş": "stitches",
  "damıtık": "distilled", "dokunuş": "touches", "kenar": "edges", "tekrar": "replays",
  "rapor yok: gece bitmedi ya da kesildi": "no report: the night did not finish or was cut",
  "Rapor kaynağı": "Report source", "gece dosyası özeti": "night file summary",
  "kullanıcı": "user", "basınç": "pressure", "ritim": "rhythm",
  "animasyon durdu — kalan dizi soluk": "animation stopped — the remaining chain stays faint",
  "Bu gece": "Tonight", "Kapat": "Close",
});

const Night = (() => {
  const SPEEDS = [1, 10, 60];
  const BATCH = 100;              // events moved into the queue per frame
  const DROP_MS = 34;             // a frame later than this missed a vsync
  const POLL_MS = 15000;          // live: how often today's file is asked for more
  const NAP_DIM = 0.4;
  const $ = (id) => document.getElementById(id);

  let speed = 1;
  let queue = [];                 // events waiting to play, in file order
  let pending = [];               // fed but not yet moved into the queue
  let raf = null;
  let nextAt = 0;                 // event-clock time the next event may start
  let frozen = false;
  let played = 0, total = 0;
  let replayed = 0;               // tekrar.ileri events played: the simple block's "(12/30)"
  let sequences = new Map();      // oturum → dizi, from tekrar.ileri
  let seen = new Set();           // ts+tur signatures, so poll and SSE do not double
  let stats = { frames: 0, dropped: 0, last: 0 };
  let current = { date: "", summary: null, report: null, woke: null, badge: "", live: false };
  let live = { timer: null, date: "", seen: 0 };
  let sheet = null;

  const scene = () => (typeof Scene !== "undefined" ? Scene : null);
  const regions = () => (typeof Regions !== "undefined" ? Regions : null);
  const today = () => new Date().toISOString().slice(0, 10);

  // --- the feed -------------------------------------------------------------
  // Live and replay both land here. Batches of BATCH move into the queue
  // one per frame so a 5k-event night never stalls the page on arrival.
  function feed(events) {
    if (!Array.isArray(events) || !events.length) return 0;
    let took = 0;
    for (let i = 0; i < events.length; i += BATCH) {
      const batch = events.slice(i, i + BATCH).filter((ev) => {
        if (!ev || typeof ev.tur !== "string" || !(ev.tur in HANDLERS)) return false;
        const sig = String(ev.ts) + "|" + ev.tur;
        if (seen.has(sig)) return false;
        seen.add(sig);
        return true;
      });
      if (batch.length) { pending.push(batch); took += batch.length; }
    }
    if (seen.size > 20000) seen = new Set([...seen].slice(-10000));
    total += took;
    if (!frozen) startLoop();
    renderStatus();
    return took;
  }

  // --- replay ----------------------------------------------------------------
  async function replay(date) {
    reset();
    current.date = date;
    current.live = false;
    let data = null;
    try { data = await (await fetch("/api/gece/" + encodeURIComponent(date))).json(); } catch { /* offline */ }
    if (!data) return 0;
    current.summary = data.ozet || null;
    const n = feed(data.olaylar || []);
    renderStatus();
    return n;
  }

  // --- live ------------------------------------------------------------------
  // Today's file is polled with `?sonra=N`; the answer feeds the same way.
  // SSE `gece` events arrive through feed() directly (app.js).
  async function poll() {
    const date = today();
    if (live.date !== date) { live.date = date; live.seen = 0; }
    try {
      const data = await (await fetch("/api/gece/" + date + "?sonra=" + live.seen)).json();
      if (data && Array.isArray(data.olaylar)) {
        if (data.olaylar.length && !current.live) { current.live = true; current.date = date; }
        live.seen = Number(data.toplam) || live.seen + data.olaylar.length;
        if (current.summary === null || current.live) current.summary = data.ozet || current.summary;
        feed(data.olaylar);
      }
    } catch { /* server not up yet */ }
  }
  function watch(on) {
    clearInterval(live.timer);
    live.timer = null;
    if (on) { poll(); live.timer = setInterval(() => { if (!document.hidden) poll(); }, POLL_MS); }
  }

  // What the simple block shows while asleep: sessions replayed so far,
  // over the file's count when the night is a recording (live: unknown).
  function progress() {
    const r = regions();
    if (!r || !r.nightProgress) return;
    const known = !current.live && current.summary ? Number(current.summary.tekrar) || 0 : 0;
    r.nightProgress(replayed, known);
  }

  function reset() {
    const s = scene();
    queue = []; pending = []; played = 0; total = 0; nextAt = 0; replayed = 0;
    sequences = new Map(); seen = new Set();
    current = { date: "", summary: null, report: null, woke: null, badge: "", live: false };
    frozen = false;
    if (s) { s.thaw(); s.clearLog(); s.dim(0); s.coldSlice(null); }
    const r = regions();
    if (r) { r.sleep("uyanik"); r.cycle(0, ""); r.nap(false); r.tired(false); }
    progress();
    renderStatus();
  }

  // --- the loop ------------------------------------------------------------------
  function loop(now) {
    raf = requestAnimationFrame(loop);
    if (stats.last) { stats.frames += 1; if (now - stats.last > DROP_MS) stats.dropped += 1; }
    stats.last = now;
    if (frozen) { stopLoop(); return; }
    // One batch per frame into the queue.
    if (pending.length) queue.push(...pending.shift());
    const s = scene();
    const ta = s ? s.tick() : now;
    let guard = 0;
    while (queue.length && ta >= nextAt && guard < BATCH) {
      const ev = queue.shift();
      played += 1;
      const dur = play(ev);
      nextAt = ta + Math.max(0, dur);
      guard += 1;
      // The handler froze the night: the frame re-armed at the top of
      // this callback is cancelled too, so not one more frame counts.
      if (frozen) { stopLoop(); break; }
    }
    if (played % 10 === 0 || !queue.length) renderStatus();
    if (!queue.length && !pending.length) stopLoop();
  }
  const startLoop = () => { if (raf === null) { stats.last = 0; raf = requestAnimationFrame(loop); } };
  const stopLoop = () => { if (raf !== null) { cancelAnimationFrame(raf); raf = null; } };

  // Durations at 1×, for the events that are not a node chain.
  const BEAT = 600;
  const scaled = (ms) => ms / speed;

  // --- event → visual (the table in 6.2) --------------------------------------
  // Each handler returns how long the next event should wait, in
  // event-clock ms (already divided by the speed).
  const HANDLERS = {
    "uyku.basladi": (ev) => {
      const s = scene(), r = regions();
      if (s) { s.thaw(); s.dim(1); }
      if (r) { r.sleep("uyuyor"); r.wakeAt(ev.tahmini_uyanma); r.cycle(0, ""); }
      frozen = false;
      current.woke = null; current.badge = "";
      replayed = 0;
      progress();
      return scaled(BEAT * 2);
    },
    "uyku.dongu": (ev) => {
      const r = regions();
      if (r) r.cycle(ev.no, ev.faz);
      return scaled(BEAT);
    },
    "tekrar.ileri": (ev) => {
      const s = scene();
      const chain = Array.isArray(ev.dizi) ? ev.dizi : [];
      if (ev.oturum) sequences.set(ev.oturum, chain);
      replayed += 1;
      progress();
      if (!s) return scaled(BEAT);
      const dur = s.lightSequence(chain, { kind: "forward", speed, group: "session", numbered: true });
      // The edges appear between the nodes as the chain walks.
      for (const edge of ev.kenarlar || []) {
        if (Array.isArray(edge) && edge.length >= 2) s.schedule(dur * 0.5, () => s.addEdge(edge[0], edge[1], edge[2]));
      }
      return dur;
    },
    "tekrar.geri": (ev) => {
      const s = scene();
      const shares = ev.paylar && typeof ev.paylar === "object" ? ev.paylar : {};
      const chain = sequences.get(ev.oturum) || Object.keys(shares);
      if (!s || !chain.length) return scaled(BEAT);
      const good = isSuccess(ev.sonuc);
      return s.lightSequence(chain, {
        reverse: true, kind: good ? "success" : "failure", speed, shares,
        glyph: good ? "✓" : "✕", group: "session",
      });
    },
    "dikis": (ev) => {
      const s = scene();
      if (s) s.stitch(ev.a, ev.b, ev.uzerinden);
      return scaled(BEAT * 1.5);
    },
    "dokunus": (ev) => {
      const s = scene();
      if (s) s.touch(ev.id);
      return scaled(BEAT * 0.5);
    },
    "damitma": (ev) => {
      const s = scene();
      if (!s) return scaled(BEAT);
      return s.distil(Array.isArray(ev.kaynaklar) ? ev.kaynaklar : [], ev.yeni, undefined, speed);
    },
    "uyku.uyandi": (ev) => {
      const s = scene(), r = regions();
      const done = Number(ev.tamamlanan) || 0, carried = Number(ev.devreden) || 0;
      current.woke = ev;
      current.badge = done + "/" + (done + carried) + " " + t("tekrar edildi") + " · "
        + carried + " " + t("devretti") + " · " + t("sebep") + ": " + t(reasonWord(ev.sebep));
      if (r) { r.flash(); r.sleep("uyaniyor"); if (r.nightProgress) r.nightProgress(done, done + carried); }
      // The animation stops IN PLACE: the scene's event clock freezes and
      // this loop stops. Whatever was still queued stays faint.
      if (s) s.freeze();
      frozen = true;
      renderStatus();
      return 0;
    },
    "uyku.bitti": (ev) => {
      const s = scene(), r = regions();
      current.report = ev.rapor && typeof ev.rapor === "object" ? ev.rapor : null;
      if (s) s.dim(0);
      if (r) { r.sleep("uyanik"); r.cycle(0, ""); }
      // The simple block's "Dün gece 18 konuşma tekrar edildi, 2 ders çıkardı."
      if (r && r.lastNight) {
        const rep = current.report || {};
        r.lastNight({ date: current.date || String(ev.ts || "").slice(0, 10) || today(),
                      replayed: "replayed" in rep ? rep.replayed : replayed,
                      lessons: "lessons_written" in rep ? rep.lessons_written : null,
                      report: current.report, summary: current.summary });
      }
      renderStatus();
      return scaled(BEAT);
    },
    "uyanik.ters": (ev) => {
      // Day: the session's chain, backwards, a short glow — without
      // waiting for the morning.
      const s = scene();
      const chain = sequences.get(ev.oturum) || (ev.oturum ? [ev.oturum] : []);
      if (!s || !chain.length) return scaled(BEAT);
      const good = isSuccess(ev.sonuc);
      return s.lightSequence(chain, {
        reverse: true, kind: good ? "success" : "failure", speed: Math.max(speed, 2),
        glyph: good ? "✓" : "✕", group: "session",
      });
    },
    "mikro.basladi": () => {
      const s = scene(), r = regions();
      if (s) s.dim(NAP_DIM);
      if (r) r.nap(true);
      return scaled(BEAT);
    },
    "mikro.bitti": () => {
      const s = scene(), r = regions();
      if (s) s.dim(0);
      if (r) r.nap(false);
      return scaled(BEAT);
    },
    "yerel.basladi": (ev) => {
      // Local sleep: the hippocampus does NOT darken; one slice of the
      // cold ring takes the sleep pattern and the "tired" badge shows.
      const s = scene(), r = regions();
      if (s) s.coldSlice(ev.bolge || "yerel");
      if (r) r.tired(true);
      return scaled(BEAT);
    },
    "yerel.bitti": () => {
      const s = scene(), r = regions();
      if (s) { s.coldSlice(null); s.thinEdges(); }
      if (r) r.tired(false);
      return scaled(BEAT);
    },
  };

  function play(ev) {
    const handler = HANDLERS[ev.tur];
    if (!handler) return 0;
    try { return handler(ev) || 0; }
    catch (err) { console.error("gece olayı çizilemedi", ev.tur, err); return 0; }
  }

  const isSuccess = (word) => /^(basari|basarili|success|ok|true)$/i.test(String(word || ""));
  const reasonWord = (word) => ({ kullanici: "kullanıcı", user: "kullanıcı", basinc: "basınç", ritim: "ritim" })[word] || String(word || "");

  // --- speed bar & controls ---------------------------------------------------
  function setSpeed(value) {
    speed = SPEEDS.includes(Number(value)) ? Number(value) : 1;
    renderStatus();
  }

  // Play again after a freeze: the clock thaws and the remaining chain
  // goes on. Nothing thaws by itself — that is the point of the freeze.
  function resume() {
    const s = scene();
    if (s) s.thaw();
    frozen = false;
    if (queue.length || pending.length) startLoop();
    renderStatus();
  }

  // --- the sheet --------------------------------------------------------------
  async function renderSheet(el) {
    sheet = el;
    if (!sheet) return;
    sheet.textContent = "";
    const head = document.createElement("div");
    head.className = "sheet-head";
    head.textContent = t("Gece");
    sheet.append(head);

    const row = document.createElement("div");
    row.className = "night-row";
    const select = document.createElement("select");
    select.id = "night-select";
    select.setAttribute("aria-label", t("Gece"));
    const liveOpt = document.createElement("option");
    liveOpt.value = ""; liveOpt.textContent = t("Canlı") + " · " + t("Bu gece");
    select.append(liveOpt);
    let nights = [];
    try { nights = ((await (await fetch("/api/gece")).json()).geceler) || []; } catch { /* offline */ }
    for (const date of nights) {
      const o = document.createElement("option");
      o.value = date; o.textContent = date;
      select.append(o);
    }
    if (!nights.length) {
      const o = document.createElement("option");
      o.disabled = true; o.textContent = t("Kayıtlı gece yok");
      select.append(o);
    }
    if (current.date && !current.live) select.value = current.date;
    const play = document.createElement("button");
    play.type = "button"; play.id = "night-play"; play.className = "plan-btn";
    play.textContent = t("Oynat");
    play.addEventListener("click", () => {
      if (frozen) { resume(); return; }
      if (select.value) replay(select.value); else { reset(); watch(true); }
    });
    row.append(select, play);
    sheet.append(row);

    const bar = document.createElement("div");
    bar.className = "night-speed"; bar.id = "night-speed";
    bar.setAttribute("role", "group"); bar.setAttribute("aria-label", t("hız"));
    for (const v of SPEEDS) {
      const b = document.createElement("button");
      b.type = "button"; b.dataset.speed = String(v);
      b.textContent = v + "×";
      b.classList.toggle("on", v === speed);
      b.addEventListener("click", () => {
        setSpeed(v);
        for (const x of bar.querySelectorAll("button")) x.classList.toggle("on", x === b);
      });
      bar.append(b);
    }
    sheet.append(bar);

    const status = document.createElement("div");
    status.className = "night-status"; status.id = "night-status";
    sheet.append(status);
    const progress = document.createElement("div");
    progress.className = "night-progress"; progress.id = "night-progress";
    sheet.append(progress);
    const badge = document.createElement("div");
    badge.className = "night-badge"; badge.id = "night-badge"; badge.hidden = true;
    sheet.append(badge);

    const reportBtn = document.createElement("button");
    reportBtn.type = "button"; reportBtn.id = "night-report-btn"; reportBtn.className = "plan-btn muted";
    reportBtn.textContent = t("Sabah raporu");
    const report = document.createElement("div");
    report.className = "night-report"; report.id = "night-report"; report.hidden = true;
    reportBtn.addEventListener("click", () => { report.hidden = !report.hidden; renderReport(report); });
    sheet.append(reportBtn, report);
    renderStatus();
  }

  // The morning report alone — what "Sabah raporu" under the simple
  // block opens. No controls, no counters: the report and a close button.
  // `info` is Regions' last-night record; a night with neither report nor
  // summary in hand is read from its file.
  async function renderReportSheet(el, info, onClose) {
    if (!el) return;
    el.textContent = "";
    const head = document.createElement("div");
    head.className = "sheet-head night-report-head";
    const title = document.createElement("span");
    title.textContent = t("Sabah raporu") + (info && info.date ? " · " + info.date : "");
    const close = document.createElement("button");
    close.type = "button"; close.className = "sheet-close"; close.textContent = "×";
    close.setAttribute("aria-label", t("Kapat"));
    close.addEventListener("click", () => { if (onClose) onClose(); });
    head.append(title, close);
    el.append(head);
    const box = document.createElement("div");
    box.className = "night-report";
    el.append(box);
    let report = info ? info.report : null, summary = info ? info.summary : null;
    if (!report && !summary && info && info.date) {
      try {
        const data = await (await fetch("/api/gece/" + encodeURIComponent(info.date))).json();
        summary = data && data.ozet ? data.ozet : null;
      } catch { /* offline */ }
    }
    fillReport(box, report, summary, null);
  }

  function renderStatus() {
    const progress = $("night-progress");
    if (progress) {
      const left = queue.length + pending.reduce((n, b) => n + b.length, 0);
      progress.textContent = played + "/" + total + " " + t("olay")
        + (left ? " · " + t("kalan") + " " + left : "") + " · " + t("hız") + " " + speed + "×";
      progress.classList.toggle("faint", frozen);
    }
    const status = $("night-status");
    if (status) {
      status.textContent = (current.live ? t("Canlı") : current.date || "") + (frozen ? " · " + t("animasyon durdu — kalan dizi soluk") : "");
    }
    const badge = $("night-badge");
    if (badge) { badge.hidden = !current.badge; badge.textContent = current.badge; }
    const play = $("night-play");
    if (play) play.textContent = frozen ? t("Devam") : t("Oynat");
  }

  // The morning report: the NightReport dict from `uyku.bitti` when the
  // night finished, else the file summary. The keys are shown as they
  // are named in weave.NightReport, so the panel and the report cannot
  // drift.
  const REPORT_LABELS = {
    session_count: "oturum", replayed: "tekrar", new_edges: "yeni kenar",
    lessons_written: "ders", procedures_written: "yordam", contradictions: "çelişki",
    carried_over: "devretti", stitched: "dikiş", distilled_nodes: "damıtık",
    goals_written: "hedef", warmed: "ısınan", cooled: "soğuyan", rolled_back: "geri alınan",
    seconds: "saniye",
  };
  const SUMMARY_LABELS = { dongu: "döngü", tekrar: "tekrar", kenar: "kenar", dikis: "dikiş",
                           damitik: "damıtık", dokunus: "dokunuş", devreden: "devretti", uyandi: "sebep" };

  function renderReport(box) { fillReport(box, current.report, current.summary, current.woke); }

  function fillReport(box, report, summary, woke) {
    box.textContent = "";
    const src = document.createElement("div");
    src.className = "sheet-note";
    const dl = document.createElement("dl");
    const put = (label, value) => {
      const dt = document.createElement("dt"); dt.textContent = t(label);
      const dd = document.createElement("dd"); dd.textContent = String(value);
      dl.append(dt, dd);
    };
    if (report) {
      src.textContent = t("Rapor kaynağı") + ": uyku.bitti.rapor (weave.NightReport)";
      for (const [key, value] of Object.entries(report)) {
        if (Array.isArray(value)) continue;
        put(REPORT_LABELS[key] || key, typeof value === "number" ? Math.round(value * 100) / 100 : value);
      }
      if (woke && woke.borc) put("borç", JSON.stringify(woke.borc));
    } else if (summary) {
      src.textContent = t("Rapor kaynağı") + ": " + t("gece dosyası özeti") + " (night_events.summary)";
      for (const [key, value] of Object.entries(summary)) put(SUMMARY_LABELS[key] || key, value);
      if (woke && woke.borc) put("borç", JSON.stringify(woke.borc));
    } else {
      src.textContent = t("rapor yok: gece bitmedi ya da kesildi");
    }
    box.append(src, dl);
  }

  const statsRead = () => ({
    frames: stats.frames, dropped: stats.dropped,
    ratio: stats.frames ? stats.dropped / stats.frames : 0,
    played, total, queued: queue.length + pending.reduce((n, b) => n + b.length, 0),
    frozen, speed, live: current.live, date: current.date,
  });

  return { feed, replay, watch, poll, reset, resume, setSpeed, renderSheet, renderReportSheet,
           stats: statsRead, HANDLERS, SPEEDS, BATCH };
})();
