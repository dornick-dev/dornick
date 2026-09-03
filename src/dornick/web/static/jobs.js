// Main-screen Tasks: the scheduled + automation list and the run detail.
// HUD icon (#jobs) → panel. The settings tab is a summary; the real UX is here.
// Left: run dates · Right: the selected run's report (about chat width).

(() => {
  const panel = document.getElementById("jobs-panel");
  if (!panel) return;

  Dil.ekle({
    "Görevler": "Tasks",
    "Basit": "Simple",
    "Otomasyon": "Automation",
    "Tümü": "All",
    "Çalıştır": "Run",
    "Durdur": "Pause",
    "Durduruluyor…": "Stopping…",
    "Durdurulamadı": "Could not stop",
    "tur": "calls",
    "araç": "tools",
    "son": "last",
    "Sürdür": "Resume",
    "Tanım": "Definition",
    "Son koşu": "Latest run",
    "Akış": "Flow",
    "Ayarlar": "Settings",
    "Koşum yok": "No runs yet",
    "Raporu aç": "Open report",
    "Yükleniyor…": "Loading…",
    "Görev yok": "No tasks",
    "detay": "detail",
    "Aç": "Open",
    "Kaydet": "Save",
    "Sil": "Delete",
    "Ad": "Name",
    "Ne yapsın": "What should it do",
    "Tetiklenince yardımcıya gidecek metin (sohbet değil)":
      "Text sent to the background helper when triggered (not chat)",
    "Tekrar": "Repeat",
    "Belirli aralıklarla": "At intervals",
    "Her gün belirli saatte": "Daily at a set time",
    "Aralık": "Interval",
    "Dakikada bir": "Minutes between runs",
    "Saat (HH:MM)": "Time (HH:MM)",
    "Görev metni boş": "Task text is empty",
    "Kaydedildi": "Saved",
    "Kaydedilemedi": "Could not save",
    "Sırada": "Next",
    "Son koşu": "Last run",
    "Son": "Last",
    "Durduruldu": "Paused",
    "Bu görev şu an çalışıyor": "This task is running now",
    "Otomasyon akışı Akış sekmesinde düzenlenir.":
      "Edit the automation flow on the Flow tab.",
    "Görevi silmek istediğine emin misin?": "Delete this task?",
    "Aktif": "Active",
    "Zamanlayıcı kapalı": "Scheduler off",
    "＋ Yeni görev": "＋ New task",
    "Kur": "Create",
    "Yeni görev": "New task",
    "Her sabah borsayı kontrol et ve özetle":
      "Check the market every morning and summarize",
    "Planlanmış": "Scheduled",
    "Canlı": "Live",
    "Canlı adımlar": "Live steps",
    "Adımlar yükleniyor…": "Loading steps…",
    "Araç bekleniyor…": "Waiting for a tool…",
    "Model bekleniyor": "Waiting for model",
    "Model yanıt vermedi": "Model did not respond",
    "tur": "calls",
    "Canlı uygulamayı aç": "Open live app",
    "Yayınlanan raporu aç": "Open published report",
    "(rapor yok)": "(no report)",
    "Şu an": "Now",
    "Tür": "Type",
    "Basit — tek yönerge": "Simple — one instruction",
    "Otomasyon — akış grafiği": "Automation — flow graph",
    "(kayıtlı akış yok)": "(no saved flow)",
    "Akışı ajana kurdurabilirsin: “… için bir otomasyon kur” de.":
      "Ask the agent to build one: “set up an automation for …”.",
    "Adımlar Akış sekmesinde düzenlenir.": "Steps are edited on the Flow tab.",
    "Önce bir akış gerekli": "A flow is required first",
  });

  const t = (s) => (typeof Dil !== "undefined" && Dil.t ? Dil.t(s) : s);

  // The repeat description arrives from the server in Turkish
  // (`Task.describe()`); translating all backend texts is a separate job,
  // but this is the MOST visible line in the list. The pattern is narrow and
  // the numbers are preserved; an unrecognized shape is left as-is — better
  // Turkish than mistranslated.
  function describeRepeat(text) {
    const raw = String(text || "");
    if (typeof Dil === "undefined" || Dil.mode !== "en") return raw;
    let m = raw.match(/^her gün (\d{1,2}:\d{2})$/);
    if (m) return `daily at ${m[1]}`;
    m = raw.match(/^her (\d+) saatte$/);
    if (m) return `every ${m[1]} h`;
    m = raw.match(/^her (\d+) dakikada$/);
    if (m) return `every ${m[1]} min`;
    return raw;
  }
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  let tasks = [];
  let view = "scheduled"; // scheduled | live
  let filter = "all"; // all | simple | automation
  let selectedId = null;
  let selectedRunId = null;
  let runs = [];
  let tab = "runs"; // runs | def | flow | settings
  let workflow = null;
  let livePoll = null;
  let liveSnap = null; // { son_arac, son_hedef, wait, oturum, deliverable, adimlar }

  function viewChips() {
    const chips = el("div", "jobs-chips jobs-view-chips");
    for (const [key, label] of [["scheduled", "Planlanmış"], ["live", "Canlı"]]) {
      const b = el("button", "jobs-chip" + (view === key ? " on" : ""), t(label));
      b.type = "button";
      b.onclick = () => {
        if (view === key) return;
        view = key;
        if (view === "live") {
          if (typeof Gorevler !== "undefined") Gorevler.setVisible(false);
          renderLive();
          if (typeof Gorevler !== "undefined") Gorevler.setVisible(true);
        } else {
          if (typeof Gorevler !== "undefined") Gorevler.setVisible(false);
          load();
        }
      };
      chips.append(b);
    }
    return chips;
  }

  function renderLive() {
    const body = document.getElementById("jobs-body");
    body.replaceChildren();
    const toolbar = el("div", "jobs-toolbar");
    toolbar.append(viewChips());
    body.append(toolbar);
    const host = el("div", "jobs-live-host");
    body.append(host);
    if (typeof Gorevler !== "undefined") Gorevler.mount(host);
  }

  // Solo mode: entered from the sidebar — no list in the center, only the
  // chosen task's detail (the list is already on the left). The HUD button
  // gives the full view.
  let solo = false;

  function open() {
    solo = false;
    openInner();
  }

  function openInner() {
    // One surface in the center: if the apps panel is open it withdraws
    // (no stacking).
    if (typeof Apps !== "undefined") Apps.close();
    panel.classList.toggle("jobs-solo", solo);
    panel.hidden = false;
    document.body.classList.add("jobs-open");
    if (view === "live") {
      renderLive();
      if (typeof Gorevler !== "undefined") Gorevler.setVisible(true);
    } else {
      if (typeof Gorevler !== "undefined") Gorevler.setVisible(false);
      load();
    }
  }
  function openLive() {
    view = "live";
    open();
  }
  // openInner shares its body with open; open resets the solo flag,
  // show keeps it.
  function close() {
    panel.hidden = true;
    document.body.classList.remove("jobs-open");
    stopLivePoll();
    stopFlowPoll();   // a closed panel must not keep polling in the background
    if (typeof Gorevler !== "undefined") Gorevler.setVisible(false);
  }
  function toggle() {
    if (panel.hidden) open(); else close();
  }

  async function load() {
    // In the live view do not draw the task list — it would wipe the ledger.
    if (view === "live") {
      if (typeof Gorevler !== "undefined" && Gorevler.tazele) Gorevler.tazele();
      return;
    }
    const body = document.getElementById("jobs-body");
    body.replaceChildren(el("p", "jobs-blank dugum-yukleniyor", t("Yükleniyor…")));
    try {
      const res = await (await fetch("/api/jobs")).json();
      tasks = res.tasks || [];
    } catch {
      tasks = [];
    }
    if (!selectedId && tasks[0]) selectedId = tasks[0].id;
    render();
  }

  async function loadRuns(tid) {
    runs = [];
    selectedRunId = null;
    if (!tid) return;
    try {
      const res = await (await fetch("/api/jobs/runs?id=" + encodeURIComponent(tid))).json();
      runs = res.runs || [];
      if (runs[0]) selectedRunId = runs[0].id;
    } catch { runs = []; }
  }

  // The single timer that refreshes the diagram while a flow runs. It stops
  // itself when the run finishes: polling a finished job every second would
  // be silent request traffic behind a closed panel.
  let flowTimer = null;

  function stopFlowPoll() {
    if (flowTimer) { clearInterval(flowTimer); flowTimer = null; }
  }

  function trackFlowLive(task, run) {
    const running = run && (run.status || "").startsWith("koş");
    if (!running) { stopFlowPoll(); return; }
    if (flowTimer) return;
    flowTimer = setInterval(async () => {
      if (tab !== "flow") { stopFlowPoll(); return; }
      const prevPick = selectedRunId;
      await loadRuns(task.id);
      // If the user picked a run, stay on it: switching it under them would
      // move what they are looking at.
      if (prevPick && runs.some((r) => r.id === prevPick)) {
        selectedRunId = prevPick;
      }
      const fresh = runs.find((r) => r.id === selectedRunId);
      if (!fresh || !(fresh.status || "").startsWith("koş")) stopFlowPoll();
      render();
    }, 1500);
  }

  async function loadWorkflow(wid) {
    workflow = null;
    if (!wid) return;
    try {
      const res = await (await fetch("/api/workflows", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "get", id: wid }),
      })).json();
      if (res.ok) workflow = res.workflow;
    } catch { workflow = null; }
  }

  function filtered() {
    if (filter === "simple") return tasks.filter((x) => (x.kind_ui || "simple") !== "automation");
    if (filter === "automation") return tasks.filter((x) => x.kind_ui === "automation");
    return tasks;
  }

  function taskRunning(task) {
    return task.last_status === "koşuyor" && !!task.last_child_id;
  }

  async function openTask(task) {
    selectedId = task.id;
    tab = "runs";
    await loadRuns(task.id);
    if (task.kind_ui === "automation" && task.workflow_id) await loadWorkflow(task.workflow_id);
    else workflow = null;
    render();
  }

  async function toggleRun(task) {
    if (taskRunning(task)) {
      const cid = task.last_child_id;
      if (!cid) return;
      let res = null;
      try {
        res = await (await fetch("/api/gorevler/durdur", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: "c:" + cid }),
        })).json();
      } catch { res = null; }
      if (res && res.ok === false && typeof toast === "function") {
        toast(res.error || t("Durdurulamadı"));
      }
      await loadRuns(task.id);
    } else {
      await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "run", id: task.id }),
      });
      await loadRuns(task.id);
    }
    await load();
    document.dispatchEvent(new Event("dornick-side-tazele"));
  }

  async function deleteTask(task) {
    if (!confirm(t("Görevi silmek istediğine emin misin?"))) return;
    if (await saveTask({ action: "remove", id: task.id })) {
      selectedId = null;
      tab = "runs";
      document.dispatchEvent(new Event("dornick-side-tazele"));
    }
  }

  function gorevMenu(task, ev) {
    if (typeof Menu === "undefined") return;
    const running = taskRunning(task);
    Menu.ac(ev, [
      { ad: "Aç", is: () => { if (panel.hidden) show(task.id); else openTask(task); } },
      { ad: running ? "Durdur" : "Çalıştır", is: () => toggleRun(task) },
      { ayrac: true },
      { ad: "Sil", risk: true, is: () => deleteTask(task) },
    ]);
  }

  function rowDotClass(task) {
    if (taskRunning(task)) return "live";
    if (!task.enabled) return "off";
    if (task.last_status === "hata" || task.last_status === "başlatılamadı") return "bad";
    return "";
  }

  function render() {
    const body = document.getElementById("jobs-body");
    body.replaceChildren();

    const toolbar = el("div", "jobs-toolbar");
    toolbar.append(viewChips());
    const chips = el("div", "jobs-chips");
    for (const [key, label] of [["all", "Tümü"], ["simple", "Basit"], ["automation", "Otomasyon"]]) {
      const b = el("button", "jobs-chip" + (filter === key ? " on" : ""), t(label));
      b.type = "button";
      b.onclick = () => { filter = key; render(); };
      chips.append(b);
    }
    toolbar.append(chips);
    const rows = filtered();
    toolbar.append(el("span", "jobs-count", rows.length + " / " + tasks.length));
    body.append(toolbar);

    const layout = el("div", "jobs-layout");
    const list = el("div", "jobs-list");
    if (!rows.length) {
      list.append(el("p", "jobs-blank", t("Görev yok")));
    }
    for (const task of rows) {
      const row = el("button", "jobs-row" + (task.id === selectedId ? " on" : ""));
      row.type = "button";
      const top = el("div", "jobs-row-top");
      top.append(el("span", "jobs-row-dot " + rowDotClass(task)));
      top.append(el("b", "jobs-row-name", task.title || task.id));
      row.append(top);
      const sub = el("div", "jobs-row-sub");
      const badge = el("span", "jobs-badge" + (task.kind_ui === "automation" ? " auto" : ""),
        task.kind_ui === "automation" ? t("Otomasyon") : t("Basit"));
      sub.append(badge);
      if (task.describe) sub.append(el("span", "jobs-row-when", describeRepeat(task.describe)));
      row.append(sub);
      if (taskRunning(task)) {
        row.append(el("span", "jobs-row-status live", t("Bu görev şu an çalışıyor")));
      } else if (task.last_status && task.last_status !== "koşuyor") {
        row.append(el("span", "jobs-row-status", task.last_status));
      } else if (!task.enabled) {
        row.append(el("span", "jobs-row-status", t("Durduruldu")));
      }
      row.onclick = async () => { await openTask(task); };
      row.addEventListener("contextmenu", (ev) => gorevMenu(task, ev));
      list.append(row);
    }
    const addRow = el("button", "jobs-row jobs-row-add", t("＋ Yeni görev"));
    addRow.type = "button";
    addRow.onclick = () => {
      selectedId = null;
      tab = "new";
      render();
    };
    list.append(addRow);
    layout.append(list);

    const detail = el("div", "jobs-detail");
    if (tab === "new") {
      const inner = el("div", "jobs-detail-body");
      inner.append(el("h2", "jobs-detail-title", t("Yeni görev")));
      const card = el("div", "jobs-card");
      card.append(renderNewTaskForm());
      inner.append(card);
      detail.append(inner);
    } else {
      const task = tasks.find((x) => x.id === selectedId);
      if (!task) {
        detail.append(el("p", "jobs-blank", t("Görev yok")));
      } else {
        detail.append(detailHead(task));
        detail.append(detailTabs(task));
        detail.append(detailBody(task));
      }
    }
    layout.append(detail);
    body.append(layout);
  }

  function detailHead(task) {
    const head = el("div", "jobs-detail-head");
    const titWrap = el("div", "jobs-detail-title-wrap");
    titWrap.append(el("h2", "jobs-detail-title", task.title || task.id));
    const subParts = [];
    if (task.describe) subParts.push(describeRepeat(task.describe));
    if (task.enabled && task.next_run) subParts.push(t("Sırada") + ": " + short(task.next_run));
    if (!task.enabled) subParts.push(t("Durduruldu"));
    if (subParts.length) titWrap.append(el("p", "jobs-detail-sub", subParts.join(" · ")));
    head.append(titWrap);
    const acts = el("div", "jobs-detail-acts");
    const running = taskRunning(task);

    const toggle = el("button", "jobs-act" + (running ? " jobs-act-stop" : ""),
      t(running ? "Durdur" : "Çalıştır"));
    toggle.type = "button";
    toggle.onclick = async () => {
      toggle.disabled = true;
      if (running) toggle.textContent = t("Durduruluyor…");
      await toggleRun(task);
    };
    acts.append(toggle);
    head.append(acts);
    return head;
  }

  function detailTabs(task) {
    const bar = el("div", "jobs-tabs");
    const tabs = [
      ["runs", "Son koşu"],
      ["def", "Tanım"],
      ["settings", "Ayarlar"],
    ];
    if (task.kind_ui === "automation") tabs.splice(2, 0, ["flow", "Akış"]);
    for (const [key, label] of tabs) {
      const b = el("button", "jobs-tab" + (tab === key ? " on" : ""), t(label));
      b.type = "button";
      b.onclick = async () => {
        tab = key;
        if (key === "runs" && !runs.length) await loadRuns(task.id);
        if (key === "flow" && task.workflow_id) await loadWorkflow(task.workflow_id);
        render();
      };
      bar.append(b);
    }
    return bar;
  }

  function detailBody(task) {
    const box = el("div", "jobs-detail-body");
    if (tab === "def") {
      const card = el("div", "jobs-card");
      card.append(renderDefForm(task));
      box.append(card);
      return box;
    }
    if (tab === "settings") {
      const card = el("div", "jobs-card");
      card.append(renderSettingsForm(task));
      box.append(card);
      return box;
    }
    if (tab === "flow") {
      if (typeof WorkflowView !== "undefined" && WorkflowView.render) {
        // The selected run's live state flows into the diagram: steps take
        // color while running, the output stays on the same screen.
        const run = runs.find((r) => r.id === selectedRunId) || runs[0] || null;
        const status = run ? {
          progress: run.nodes_progress || [],
          rapor: run.report || "",
          cikti: run.deliverable || null,
        } : null;
        trackFlowLive(task, run);
        box.append(WorkflowView.render(workflow, async (wf) => {
          await fetch("/api/workflows", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "save", workflow: wf }),
          });
          await loadWorkflow(wf.id);
          render();
        }, status));
      } else {
        box.append(el("pre", "jobs-prompt",
          workflow ? JSON.stringify(workflow, null, 2) : t("Akış yok")));
      }
      return box;
    }
    // runs: dates on the left + content on the right
    if (!runs.length) {
      const empty = el("div", "jobs-blank-box");
      empty.append(el("p", "jobs-blank", t("Koşum yok")));
      box.append(empty);
      return box;
    }
    const split = el("div", "jobs-run-split");
    const dates = el("div", "jobs-run-dates");
    for (const r of runs) {
      const row = el("button", "jobs-run-date" + (r.id === selectedRunId ? " on" : ""));
      row.type = "button";
      row.append(el("span", null, short(r.started || r.finished)));
      row.append(el("i", null, r.status || ""));
      const tip = formatRunMeter(r, null);
      if (tip) row.title = tip;
      row.onclick = () => {
        selectedRunId = r.id;
        liveSnap = null;
        stopLivePoll();
        render();
      };
      dates.append(row);
    }
    const content = el("div", "jobs-run-content");
    const run = runs.find((r) => r.id === selectedRunId) || runs[0];
    const running = (run.status || "") === "koşuyor" || (run.status || "") === "kosuyor";
    content.append(el("div", "jobs-run-meta",
      (run.status || "") + (run.finished ? " · " + short(run.finished) : "")));
    const meter = formatRunMeter(run, liveSnap);
    content.append(el("div", "jobs-run-meter",
      meter || t("(ölçüm yok — koşu kısa kesildi veya model yanıt vermedi)")));

    const deliv = (liveSnap && liveSnap.deliverable) || run.deliverable || null;
    if (deliv && deliv.url) {
      const openApp = el("button", "jobs-act jobs-act-primary",
        t(deliv.kind === "artifact" ? "Yayınlanan raporu aç" : "Canlı uygulamayı aç"));
      openApp.type = "button";
      openApp.onclick = () => {
        if (typeof Viewer !== "undefined" && Viewer.page) {
          Viewer.page(deliv.url, task.title || deliv.url);
        }
      };
      content.append(openApp);
    } else if (run.child_id) {
      const openReport = el("button", "jobs-act", t("Raporu aç"));
      openReport.type = "button";
      openReport.onclick = () => {
        if (typeof Viewer !== "undefined" && Viewer.page) {
          Viewer.page("/gorev-rapor/" + encodeURIComponent(run.child_id) + "/",
                      run.title || task.title);
        }
      };
      content.append(openReport);
    }

    if (running) {
      content.append(renderLiveRun());
      startLivePoll(run, task);
    } else {
      stopLivePoll();
      content.append(el("pre", "jobs-report",
        run.report || t("(rapor yok)")));
    }
    if (run.nodes_progress && run.nodes_progress.length) {
      const ul = el("ul", "jobs-nodes");
      for (const n of run.nodes_progress) {
        ul.append(el("li", null,
          (n.status === "bitti" ? "✓ " : n.status === "hata" ? "✗ " : "… ") +
          (n.title || n.id) + (n.detail ? " — " + n.detail : "")));
      }
      content.append(ul);
    }
    split.append(dates, content);
    box.append(split);
    return box;
  }

  function renderLiveRun(_run, _task) {
    const wrap = el("div", "jobs-live-run");
    wrap.append(el("div", "jobs-live-run-head", t("Canlı adımlar")));
    const status = el("div", "jobs-live-status");
    const snap = liveSnap || {};
    if (snap.wait) {
      const mode = snap.wait.kip || "";
      let msg = mode === "hata" ? t("Model yanıt vermedi") : t("Model bekleniyor");
      if (snap.wait.deneme && snap.wait.toplam) {
        msg += ` (${snap.wait.deneme}/${snap.wait.toplam})`;
      }
      if (snap.wait.saniye) msg += ` · ${snap.wait.saniye}s`;
      status.append(el("span", "jobs-live-wait", msg));
    } else if (snap.son_arac) {
      let line = "▶ " + snap.son_arac;
      if (snap.son_hedef) line += " · " + snap.son_hedef;
      status.append(el("span", "jobs-live-tool", line));
    } else {
      status.append(el("span", "jobs-live-tool", t("Araç bekleniyor…")));
    }
    wrap.append(status);

    const steps = el("div", "jobs-live-steps");
    const stepData = snap.adimlar;
    if (stepData === undefined) {
      steps.append(el("div", "jobs-live-empty", t("Adımlar yükleniyor…")));
    } else if (!stepData || !stepData.length) {
      steps.append(el("div", "jobs-live-empty", t("Araç bekleniyor…")));
    } else {
      for (const a of stepData.slice(-40)) {
        if (a.tur === "arac") {
          const row = el("div", "jobs-live-step" + (a.hata ? " err" : ""));
          row.append(el("span", "jobs-live-mark", a.hata ? "✗" : "·"));
          row.append(el("b", null, a.ad || ""));
          if (a.hedef) row.append(el("span", "jobs-live-hedef", a.hedef));
          if (a.ms) row.append(el("span", "jobs-live-ms",
            a.ms >= 1000 ? (a.ms / 1000).toFixed(1) + " sn" : a.ms + " ms"));
          steps.append(row);
        } else if (a.tur === "soz" && a.metin) {
          steps.append(el("div", "jobs-live-say", a.metin));
        }
      }
    }
    wrap.append(steps);
    return wrap;
  }

  function stopLivePoll() {
    if (livePoll) {
      clearInterval(livePoll);
      livePoll = null;
    }
  }

  function startLivePoll(run, task) {
    const cid = run.child_id || task.last_child_id;
    if (!cid) return;
    // Do not open a second interval for the same run.
    if (livePoll && liveSnap && liveSnap._cid === cid) return;
    stopLivePoll();
    const tick = async () => {
      if (panel.hidden || view !== "scheduled" || tab !== "runs") {
        stopLivePoll();
        return;
      }
      try {
        const data = await (await fetch("/api/gorevler")).json();
        const row = ((data && data.gorevler) || [])
          .find((g) => g.id === "c:" + cid);
        const next = {
          _cid: cid,
          son_arac: (row && row.son_arac) || "",
          son_hedef: (row && row.son_hedef) || "",
          wait: (row && row.wait) || null,
          oturum: (row && row.oturum) || "",
          deliverable: (row && row.deliverable) || null,
          model: (row && row.model) || "",
          usage: (row && row.usage) || null,
          adimlar: (liveSnap && liveSnap.adimlar) || undefined,
        };
        if (next.oturum) {
          const dok = await (await fetch(
            "/api/gorevler/dokum?oturum=" + encodeURIComponent(next.oturum)
          )).json();
          if (dok && dok.ok) next.adimlar = dok.adimlar || [];
        } else {
          next.adimlar = next.adimlar || [];
        }
        liveSnap = next;
        paintLiveHost();
        if (row && row.durum && row.durum !== "kosuyor") {
          stopLivePoll();
          liveSnap = null;
          await loadRuns(task.id);
          await load();
        }
      } catch { /* no network — next tick */ }
    };
    tick();
    livePoll = setInterval(tick, 2500);
  }

  function paintLiveHost() {
    const host = panel.querySelector(".jobs-live-run");
    if (!host) return;
    const neu = renderLiveRun();
    host.replaceWith(neu);
    // CTA button (app) — the deliverable may have arrived late.
    const content = panel.querySelector(".jobs-run-content");
    if (!content || !liveSnap || !liveSnap.deliverable || !liveSnap.deliverable.url) return;
    if (content.querySelector(".jobs-act-primary")) return;
    const deliv = liveSnap.deliverable;
    const openApp = el("button", "jobs-act jobs-act-primary",
      t(deliv.kind === "artifact" ? "Yayınlanan raporu aç" : "Canlı uygulamayı aç"));
    openApp.type = "button";
    openApp.onclick = () => {
      if (typeof Viewer !== "undefined" && Viewer.page) {
        Viewer.page(deliv.url, deliv.url);
      }
    };
    const meta = content.querySelector(".jobs-run-meta");
    if (meta && meta.nextSibling) content.insertBefore(openApp, meta.nextSibling);
    else content.prepend(openApp);
  }

  function refreshLive() {
    if (view !== "scheduled" || tab !== "runs" || panel.hidden) return;
    const task = tasks.find((x) => x.id === selectedId);
    const run = runs.find((r) => r.id === selectedRunId) || runs[0];
    if (!task || !run) return;
    const running = (run.status || "") === "koşuyor" || (run.status || "") === "kosuyor";
    if (running) startLivePoll(run, task);
  }

  function short(stamp) {
    if (!stamp) return "—";
    const when = new Date(stamp);
    return isNaN(when) ? stamp : when.toLocaleString("tr-TR", {
      day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    });
  }

  function formatRunMeter(run, snap) {
    const model = (snap && snap.model) || (run && run.model) || "";
    const usage = (snap && snap.usage) || (run && run.usage) || null;
    const cost = run && run.cost_usd != null ? Number(run.cost_usd) : null;
    const tools = (snap && snap.tools) != null ? snap.tools
      : (run && run.tools) != null ? run.tools : 0;
    const lastTool = (snap && snap.last_tool) || (run && run.last_tool) || "";
    let durationS = (run && run.duration_s) || 0;
    if (!durationS && run && run.started) {
      const a = Date.parse(run.started);
      const b = run.finished ? Date.parse(run.finished) : Date.now();
      if (!isNaN(a) && !isNaN(b) && b >= a) durationS = Math.round((b - a) / 1000);
    }
    const parts = [];
    if (model) {
      const s = String(model);
      const i = s.lastIndexOf("/");
      parts.push(i < 0 ? s : s.slice(i + 1));
    }
    if (usage) {
      const tok = Number(usage.girdi || 0) + Number(usage.cikti || 0);
      if (tok) {
        parts.push(tok >= 1000 ? (tok / 1000).toFixed(1) + "k tok" : tok + " tok");
      }
      if (usage.cagri) parts.push(String(usage.cagri) + " " + t("tur"));
    }
    if (tools) parts.push(String(tools) + " " + t("araç"));
    if (durationS) parts.push(fmtDuration(durationS));
    if (cost != null && !Number.isNaN(cost)) {
      parts.push(cost >= 0.01 || cost === 0
        ? "≈$" + cost.toFixed(2)
        : "≈$" + cost.toFixed(3));
    }
    if (lastTool) parts.push(t("son") + ": " + String(lastTool).slice(0, 60));
    return parts.join(" · ");
  }

  function fmtDuration(sec) {
    const s = Math.max(0, Math.round(Number(sec) || 0));
    if (s < 60) return s + " sn";
    const m = Math.floor(s / 60);
    const r = s % 60;
    if (m < 60) return r ? m + " dk " + r + " sn" : m + " dk";
    const h = Math.floor(m / 60);
    return h + " sa " + (m % 60) + " dk";
  }

  async function saveTask(body) {
    try {
      const res = await (await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })).json();
      if (!res.ok && res.error) throw new Error(res.error);
      const wasAdd = body.action === "add";
      const title = body.title || "";
      await load();
      if (wasAdd && tasks.length) {
        const hit = tasks.find((x) => x.title === title);
        selectedId = (hit || tasks[tasks.length - 1]).id;
      }
      return true;
    } catch (err) {
      const msg = (err && err.message) || t("Kaydedilemedi");
      if (typeof say === "function") say(msg, true);
      else alert(msg);
      return false;
    }
  }

  function field(label, hint, control) {
    const row = el("label", "jobs-field");
    row.append(el("span", "jobs-field-label", t(label)));
    row.append(control);
    if (hint) row.append(el("span", "jobs-field-hint", t(hint)));
    return row;
  }

  function inputText(value, onChange, placeholder) {
    const node = el("input", "jobs-input");
    node.type = "text";
    node.value = value ?? "";
    if (placeholder) node.placeholder = placeholder;
    node.addEventListener("input", () => onChange(node.value));
    return node;
  }

  function inputArea(value, onChange, placeholder) {
    const node = el("textarea", "jobs-textarea");
    node.value = value ?? "";
    if (placeholder) node.placeholder = placeholder;
    node.rows = 6;
    node.addEventListener("input", () => onChange(node.value));
    return node;
  }

  function inputNumber(value, onChange) {
    const node = el("input", "jobs-input jobs-input-num");
    node.type = "number";
    node.min = "1";
    node.value = value ?? 1;
    node.addEventListener("input", () => onChange(node.value));
    return node;
  }

  function selectOption(value, label, selected) {
    const o = el("option", null, t(label));
    o.value = value;
    if (selected) o.selected = true;
    return o;
  }

  function renderDefForm(task) {
    const box = el("div", "jobs-form");
    const draft = {
      action: "update",
      id: task.id,
      title: task.title || "",
      prompt: task.prompt || "",
    };

    box.append(field("Ad", "", inputText(draft.title, (v) => (draft.title = v), t("Ad"))));

    if (task.kind_ui === "automation") {
      box.append(el("p", "jobs-meta", t("Otomasyon akışı Akış sekmesinde düzenlenir.")));
      if (task.workflow_id) {
        box.append(el("p", "jobs-meta", "workflow: " + task.workflow_id));
      }
    }
    box.append(field("Ne yapsın", "Tetiklenince yardımcıya gidecek metin (sohbet değil)",
      inputArea(draft.prompt, (v) => (draft.prompt = v))));

    const save = el("button", "jobs-act jobs-act-primary", t("Kaydet"));
    save.type = "button";
    save.onclick = async () => {
      if (!String(draft.prompt || "").trim() && task.kind_ui !== "automation") {
        if (typeof say === "function") say(t("Görev metni boş"), true);
        return;
      }
      if (await saveTask(draft)) tab = "def";
    };
    box.append(save);
    return box;
  }

  function renderSettingsForm(task) {
    const box = el("div", "jobs-form");
    const running = task.last_status === "koşuyor";
    const draft = {
      action: "update",
      id: task.id,
      kind: task.kind || "every",
      every_s: Number(task.every_s) || 3600,
      at: task.at || "09:00",
      enabled: task.enabled !== false,
    };

    const kind = el("select", "jobs-input");
    kind.append(selectOption("every", "Belirli aralıklarla", draft.kind === "every"));
    kind.append(selectOption("daily", "Her gün belirli saatte", draft.kind === "daily"));
    box.append(field("Tekrar", "", kind));

    const slot = el("div", "jobs-slot");
    const every = inputNumber(Math.max(1, Math.round(draft.every_s / 60)),
      (v) => (draft.every_s = Number(v) * 60));
    const at = inputText(draft.at, (v) => (draft.at = v));
    function fillSlot() {
      slot.replaceChildren();
      if (draft.kind === "daily") {
        slot.append(at, el("span", "jobs-field-hint", t("Saat (HH:MM)")));
      } else {
        slot.append(every, el("span", "jobs-field-hint", t("Dakikada bir")));
      }
    }
    fillSlot();
    box.append(field("Aralık", "", slot));
    kind.addEventListener("change", () => {
      draft.kind = kind.value;
      fillSlot();
    });

    const enabledRow = el("label", "jobs-field jobs-field-check");
    const en = el("input", "jobs-check");
    en.type = "checkbox";
    en.checked = draft.enabled;
    en.addEventListener("change", () => { draft.enabled = en.checked; });
    enabledRow.append(en, el("span", null, en.checked ? t("Aktif") : t("Zamanlayıcı kapalı")));
    en.addEventListener("change", () => {
      enabledRow.querySelector("span:last-child").textContent =
        en.checked ? t("Aktif") : t("Zamanlayıcı kapalı");
    });
    box.append(enabledRow);

    const parts = [];
    if (running) parts.push(t("Bu görev şu an çalışıyor"));
    else if (draft.enabled && task.next_run) parts.push(t("Sırada") + ": " + short(task.next_run));
    else if (!draft.enabled) parts.push(t("Durduruldu"));
    if (task.last_run) parts.push(t("Son koşu") + ": " + short(task.last_run));
    if (task.last_status && task.last_status !== "koşuyor") {
      parts.push(t("Son") + ": " + task.last_status);
    }
    if (parts.length) box.append(el("p", "jobs-meta", parts.join(" · ")));

    const acts = el("div", "jobs-form-acts");
    const save = el("button", "jobs-act jobs-act-primary", t("Kaydet"));
    save.type = "button";
    save.onclick = async () => {
      if (await saveTask(draft)) tab = "settings";
    };
    const del = el("button", "jobs-act jobs-act-risk", t("Sil"));
    del.type = "button";
    del.onclick = () => deleteTask(task);
    acts.append(save, del);
    box.append(acts);
    return box;
  }

  function renderNewTaskForm() {
    const box = el("div", "jobs-form");
    const draft = { action: "add", kind: "every", every_s: 3600, at: "09:00" };

    box.append(field("Ad", "", inputText("", (v) => (draft.title = v), t("Yeni görev"))));

    // Task kind: simple (one instruction) or automation (flow graph). The
    // automation's carrier is not a prompt but the FLOW; asking for both in
    // one form would push the user to invent meaningless text.
    const kindSel = el("select", "jobs-input");
    kindSel.append(selectOption("simple", "Basit — tek yönerge", true));
    kindSel.append(selectOption("automation", "Otomasyon — akış grafiği", false));
    box.append(field("Tür", "", kindSel));

    const bodySlot = el("div", "jobs-slot jobs-slot-col");
    const flowSelect = el("select", "jobs-input");
    const flowHint = el("span", "jobs-field-hint", "");
    async function fillFlows() {
      flowSelect.replaceChildren();
      let list = [];
      try {
        const res = await (await fetch("/api/workflows")).json();
        list = res.workflows || [];
      } catch { list = []; }
      if (!list.length) {
        flowSelect.append(selectOption("", t("(kayıtlı akış yok)"), true));
        flowHint.textContent = t("Akışı ajana kurdurabilirsin: “… için bir otomasyon kur” de.");
        return;
      }
      flowHint.textContent = t("Adımlar Akış sekmesinde düzenlenir.");
      list.forEach((w, i) => {
        flowSelect.append(selectOption(
          w.id, `${w.title || w.id} · ${w.nodes} adım`, i === 0));
      });
      draft.workflow_id = list[0].id;
    }
    flowSelect.addEventListener("change", () => { draft.workflow_id = flowSelect.value; });

    const promptArea = inputArea("", (v) => (draft.prompt = v),
      t("Her sabah borsayı kontrol et ve özetle"));

    function fillBody() {
      bodySlot.replaceChildren();
      if (kindSel.value === "automation") {
        bodySlot.append(flowSelect, flowHint);
        fillFlows();
      } else {
        draft.workflow_id = "";
        bodySlot.append(promptArea);
      }
    }
    fillBody();
    kindSel.addEventListener("change", fillBody);
    box.append(field("Ne yapsın", "", bodySlot));

    const kind = el("select", "jobs-input");
    kind.append(selectOption("every", "Belirli aralıklarla", true));
    kind.append(selectOption("daily", "Her gün belirli saatte", false));
    box.append(field("Tekrar", "", kind));

    const slot = el("div", "jobs-slot");
    const every = inputNumber(60, (v) => (draft.every_s = Number(v) * 60));
    const at = inputText("09:00", (v) => (draft.at = v));
    function fillSlot() {
      slot.replaceChildren();
      if (draft.kind === "daily") {
        slot.append(at, el("span", "jobs-field-hint", t("Saat (HH:MM)")));
      } else {
        slot.append(every, el("span", "jobs-field-hint", t("Dakikada bir")));
      }
    }
    fillSlot();
    box.append(field("Aralık", "", slot));
    kind.addEventListener("change", () => {
      draft.kind = kind.value;
      fillSlot();
    });

    const add = el("button", "jobs-act jobs-act-primary", t("Kur"));
    add.type = "button";
    add.onclick = async () => {
      if (kindSel.value === "automation") {
        if (!String(draft.workflow_id || "").trim()) {
          if (typeof say === "function") say(t("Önce bir akış gerekli"), true);
          return;
        }
      } else if (!String(draft.prompt || "").trim()) {
        if (typeof say === "function") say(t("Görev metni boş"), true);
        return;
      }
      if (await saveTask(draft)) {
        selectedId = tasks[tasks.length - 1]?.id || null;
        tab = "def";
      }
    };
    box.append(add);
    return box;
  }

  document.getElementById("jobs")?.addEventListener("click", toggle);
  document.getElementById("jobs-close")?.addEventListener("click", close);
  document.getElementById("jobs-refresh")?.addEventListener("click", () => {
    if (view === "live" && typeof Gorevler !== "undefined") Gorevler.tazele();
    else load();
  });

  // From the sidebar: open with a specific task's detail, WITHOUT the list.
  function show(id) {
    view = "scheduled";
    selectedId = id;
    solo = true;
    openInner();
  }

  window.JobsPanel = { open, openLive, close, load, toggle, refreshLive, show,
                       menu: gorevMenu };
})();
