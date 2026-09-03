// Live run ledger — the "Canlı" (Live) tab of the Tasks panel.
//
// Three sources in one list, because to the user all three are the same
// thing ("something is running in the background"):
//
//   * background shell jobs   — the `shell` tool's `arka_plan: true` path
//   * background helpers      — sub-agents spawned by the `task` tool
//   * detached processes      — servers, apps started from the panel
//
// It stands "Orkestra güvertesinden AYRI" (apart from the orchestra deck) and
// that is deliberate: the orchestra is a stage that shows the CURRENT turn's
// coordination and opens/closes on its own ("conductor waiting, three
// channels running"). This is the ledger: it counts durations, stops jobs one
// by one, drills into a finished job's output and survives turn changes.
// Merging the two would turn either the stage into a permanent list or the
// ledger into a vanishing stage.
//
// The duration is LIVE but the server is not polled every second: the row
// carries the `basladi` stamp and the browser does the counting. The network
// is hit only on a status change or every few seconds.

Lang.add({
  "Koşan görevler": "Running tasks",
  "Şu an arkada koşan bir iş yok.": "Nothing is running in the background.",
  "Bir işi arka plana aldığında ya da bir yardımcı doğurduğunda burada belirir.":
    "It shows up here when a job goes background or a helper is spawned.",
  " iş koşuyor": " job(s) running",
  "Hepsi bitti": "All done",
  "Durdur": "Stop",
  "Durduruluyor…": "Stopping…",
  "Devam et": "Continue",
  "Sürdürülüyor…": "Resuming…",
  "koşuyor": "running",
  "bitti": "done",
  "hata": "failed",
  "yarım kaldı": "left unfinished",
  "yardımcı": "helper",
  "iş": "job",
  "süreç": "process",
  "(çıktı yok)": "(no output)",
  "Adımlar yükleniyor…": "Loading steps…",
  "Adım bulunamadı.": "No steps found.",
  "Döküm okunamadı.": "Could not read the log.",
  "sonucu gör": "see the result",
  "raporu aç": "open report",
  "bitti · ": "done · ",
  "hata verdi · ": "failed · ",
  "Model bekleniyor": "Waiting for model",
  "Canlı uygulamayı aç": "Open live app",
});

const Tasks = (() => {
  const badge = document.getElementById("jobs-badge");

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  let body = null;
  let statusLine = null;
  let host = null;
  let visible = false;

  let rows = [];
  let openSet = new Set();      // which task's output is expanded
  let logCache = new Map();     // task id → {steps, ts}
  const DOKUM_TTL_MS = 2500;
  let pollTimer = null;
  let tickTimer = null;

  const STATUS_LABEL = {
    kosuyor: "koşuyor", bitti: "bitti", hata: "hata", yetim: "yarım kaldı",
  };

  // --- data ------------------------------------------------------------

  async function refresh() {
    let data;
    try { data = await (await fetch("/api/gorevler")).json(); }
    catch { return; }
    rows = (data && data.gorevler) || [];
    drawBadge(data && data.kosan);
    if (visible && body) {
      draw();
      // Refresh the log of expanded running cards with the TTL.
      for (const g of rows) {
        if (openSet.has(g.id) && g.oturum && g.durum === "kosuyor") {
          fetchLog(g);
        }
      }
    }
  }

  function drawBadge(running) {
    if (!badge) return;
    const n = Number(running) || 0;
    badge.hidden = n === 0;
    badge.textContent = n > 9 ? "9+" : String(n);
  }

  // --- drawing ---------------------------------------------------------

  function mount(parent) {
    if (host && host.parentElement === parent) return host;
    host = el("div", "jobs-live");
    statusLine = el("div", "tasks-status");
    body = el("div", "tasks-body");
    host.append(statusLine, body);
    parent.replaceChildren(host);
    if (visible) draw();
    return host;
  }

  function draw() {
    if (!body) return;
    body.replaceChildren();
    if (!rows.length) {
      const blank = el("div", "tasks-blank");
      blank.append(el("p", null, t("Şu an arkada koşan bir iş yok.")));
      blank.append(el("p", "tasks-blank-hint",
        t("Bir işi arka plana aldığında ya da bir yardımcı doğurduğunda burada belirir.")));
      body.append(blank);
    }
    for (const g of rows) body.append(card(g));

    const running = rows.filter(g => g.durum === "kosuyor").length;
    if (statusLine) {
      statusLine.textContent = running
        ? running + t(" iş koşuyor")
        : (rows.length ? t("Hepsi bitti") : "");
      statusLine.className = "tasks-status" + (running ? " live" : "");
    }
  }

  function card(g) {
    const wrap = el("div", "task " + g.durum);
    const top = el("div", "task-top");
    top.append(el("span", "task-dot"));
    top.append(el("span", "task-name", g.ad || g.id));
    top.append(el("span", "task-kind " + kindClass(g.tur), t(g.tur)));
    wrap.append(top);

    const line = el("div", "task-line");
    line.append(el("span", "task-state", t(STATUS_LABEL[g.durum] || g.durum)));
    const timeEl = el("span", "task-time");
    timeEl.dataset.basladi = String(g.basladi || 0);
    timeEl.dataset.bitti = String(g.bitti || 0);
    timeEl.dataset.kosuyor = g.durum === "kosuyor" ? "1" : "";
    timeEl.textContent = durationText(timeEl);
    line.append(timeEl);
    if (g.model) line.append(el("span", "task-model", shortModel(g.model)));
    if (g.durum === "kosuyor" && g.wait) {
      let msg = t("Model bekleniyor");
      const w = g.wait;
      if (w.deneme && w.toplam) msg += ` (${w.deneme}/${w.toplam})`;
      if (w.saniye) msg += ` · ${w.saniye}s`;
      line.append(el("span", "task-wait", msg));
    } else if (g.durum === "kosuyor" && g.son_arac) {
      let toolLine = "▶ " + g.son_arac;
      if (g.son_hedef) toolLine += " · " + g.son_hedef;
      line.append(el("span", "task-tool", toolLine));
    }

    if (g.durdurulabilir) {
      const stopBtn = el("button", "task-stop", t("Durdur"));
      stopBtn.type = "button";
      stopBtn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        stopBtn.disabled = true;
        stopBtn.textContent = t("Durduruluyor…");
        let res = null;
        try {
          res = await (await fetch("/api/gorevler/durdur", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: g.id }),
          })).json();
        } catch { res = null; }
        if (res && res.ok === false) {
          stopBtn.disabled = false;
          stopBtn.textContent = t("Durdur");
        }
        refresh();
      });
      line.append(stopBtn);
    }
    if (g.surdurulebilir || g.durum === "yetim") {
      const resumeBtn = el("button", "task-resume", t("Devam et"));
      resumeBtn.type = "button";
      resumeBtn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        resumeBtn.disabled = true;
        resumeBtn.textContent = t("Sürdürülüyor…");
        await fetch("/api/gorevler/devam", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: g.id }),
        }).catch(() => {});
        refresh();
      });
      line.append(resumeBtn);
    }
    wrap.append(line);

    const drillable = g.durum !== "kosuyor" || !!g.oturum;
    if (drillable) {
      wrap.classList.add("clickable");
      wrap.addEventListener("click", () => {
        if (g.durum !== "kosuyor" && g.deliverable && g.deliverable.url
            && typeof Viewer !== "undefined" && Viewer.page) {
          Viewer.page(g.deliverable.url, g.ad || g.id);
          return;
        }
        if (g.durum !== "kosuyor" && String(g.id || "").startsWith("c:")
            && typeof Viewer !== "undefined" && Viewer.page) {
          Viewer.page("/gorev-rapor/" + encodeURIComponent(g.id.slice(2)) + "/",
                      g.ad || g.id);
          return;
        }
        if (openSet.has(g.id)) openSet.delete(g.id);
        else { openSet.add(g.id); if (g.oturum) fetchLog(g); }
        draw();
      });
    }
    if (openSet.has(g.id)) wrap.append(output(g));
    return wrap;
  }

  function output(g) {
    const box = el("div", "task-out");
    if (g.ozet) box.append(el("div", "task-ozet", g.ozet));
    if (g.komut) box.append(el("div", "task-cmd", "$ " + g.komut));
    if (!g.oturum) {
      if (!g.ozet && !g.komut) box.append(el("div", "task-ozet", t("(çıktı yok)")));
      return box;
    }
    const cache = logCache.get(g.id);
    const steps = cache === undefined ? undefined
      : (cache === null ? null : cache.steps);
    if (steps === undefined) {
      box.append(el("div", "task-ozet", t("Adımlar yükleniyor…")));
      return box;
    }
    if (steps === null) {
      box.append(el("div", "task-ozet", t("Döküm okunamadı.")));
      return box;
    }
    if (!steps.length) {
      box.append(el("div", "task-ozet", t("Adım bulunamadı.")));
      return box;
    }
    const list = el("div", "task-steps");
    for (const a of steps) {
      if (a.tur === "arac") {
        const s = el("div", "task-step" + (a.hata ? " err" : ""));
        s.append(el("span", "task-step-mark", a.hata ? "✗" : "·"));
        s.append(el("b", null, a.ad));
        s.append(el("span", "task-step-target", a.hedef || ""));
        if (a.ms) s.append(el("span", "task-step-ms", ms(a.ms)));
        list.append(s);
      } else {
        list.append(el("div", "task-step say", a.metin));
      }
    }
    box.append(list);
    return box;
  }

  async function fetchLog(g, { force = false } = {}) {
    const prev = logCache.get(g.id);
    if (!force && prev && prev !== null
        && (Date.now() - (prev.ts || 0)) < DOKUM_TTL_MS) {
      return;
    }
    // While running, refresh when the TTL expires; once finished, one read is enough.
    if (!force && g.durum !== "kosuyor" && prev !== undefined) return;
    let data;
    try {
      data = await (await fetch("/api/gorevler/dokum?oturum="
        + encodeURIComponent(g.oturum))).json();
    } catch { data = null; }
    logCache.set(g.id, data && data.ok
      ? { steps: data.adimlar || [], ts: Date.now() }
      : null);
    if (visible && body) draw();
  }

  // --- duration --------------------------------------------------------

  function durationText(node) {
    const started = Number(node.dataset.basladi) || 0;
    if (!started) return "";
    const ended = Number(node.dataset.bitti) || 0;
    const last = node.dataset.kosuyor ? Date.now() / 1000 : (ended || started);
    return shortDuration(Math.max(0, last - started));
  }

  function shortDuration(secs) {
    if (secs < 60) return Math.round(secs) + " sn";
    const mins = Math.floor(secs / 60);
    if (mins < 60) return mins + " dk " + Math.round(secs % 60) + " sn";
    return Math.floor(mins / 60) + " sa " + (mins % 60) + " dk";
  }

  const ms = (n) => (n >= 1000 ? (n / 1000).toFixed(1) + " sn" : n + " ms");

  const shortModel = (m) => {
    const cut = String(m).split("/").pop();
    return cut.length > 20 ? cut.slice(0, 20) + "…" : cut;
  };

  const kindClass = (kind) => (kind === "süreç" ? "proc"
    : kind === "iş" ? "job" : "helper");

  // --- visibility ------------------------------------------------------

  function setVisible(on) {
    visible = !!on;
    if (visible) {
      refresh();
      startPolling();
    } else {
      stopPolling();
    }
  }

  function open() {
    if (window.JobsPanel && JobsPanel.openLive) JobsPanel.openLive();
    else if (window.JobsPanel) JobsPanel.open();
  }

  function close() {
    if (window.JobsPanel) JobsPanel.close();
  }

  function toggle() { open(); }

  function startPolling() {
    stopPolling();
    pollTimer = setInterval(refresh, 4000);
    tickTimer = setInterval(() => {
      if (!body) return;
      for (const node of body.querySelectorAll(".task-time")) {
        node.textContent = durationText(node);
      }
    }, 1000);
  }

  function stopPolling() {
    clearInterval(pollTimer); pollTimer = null;
    clearInterval(tickTimer); tickTimer = null;
  }

  // --- notifying the conversation --------------------------------------
  //
  // When a background job finishes the user may not have the panel open.
  // A single clickable row drops into the conversation: clicking it opens
  // the panel with that job's output expanded. Only for BACKGROUND jobs —
  // a synchronous helper's result is already inside the answer.
  function done(ev) {
    refresh();
    if (!ev || !ev.bg) return;
    const row = line("alert task-done");
    row.replaceChildren();
    const btn = el("button", "task-note");
    btn.type = "button";
    btn.append(el("span", "task-note-mark", ev.ok ? "✓" : "✗"));
    btn.append(el("span", "task-note-name", ev.title || ""));
    btn.append(el("span", "task-note-go",
      (ev.ok ? t("bitti · ") : t("hata verdi · ")) + t("raporu aç")));
    btn.addEventListener("click", () => {
      const cid = ev.id || "";
      if (cid && typeof Viewer !== "undefined" && Viewer.page) {
        Viewer.page("/gorev-rapor/" + encodeURIComponent(cid) + "/", ev.title || cid);
        return;
      }
      if (cid) openSet.add("c:" + cid);
      open();
    });
    row.append(btn);
    scroll();
  }

  // Once on startup: let the badge tell the truth (even with the panel closed).
  refresh();

  return { open, close, toggle, refresh, done, shortDuration, mount, setVisible, draw };
})();
