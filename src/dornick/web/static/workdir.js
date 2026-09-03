// Working-folder strip + folder picker/creator.
//
// Why it exists: nowhere on the chat screen did the question "where am I
// working right now?" have an answer. Workshop or a bound folder — the user
// could only tell by opening the settings (live wound, 02.09). The strip
// says it, and opens a one-click way to change it.
//
// Picking a folder is the user's CONSENT: a directory outside the workshop
// can also be chosen (that is the sandbox's rule too). The server only
// rejects the genuinely dangerous roots (drive root, Windows/Program Files,
// the home directory itself).

Lang.add({
  "Çalışma klasörü": "Working folder",
  "Atölye": "Workshop",
  "atölye (varsayılan)": "workshop (default)",
  "bağlı klasör": "bound folder",
  "Klasör seç": "Choose folder",
  "Yeni klasör": "New folder",
  "Klasör seç — tıkla: değiştir": "Working folder — click to change",
  "Bu klasörde çalış": "Work here",
  "Üst klasör": "Parent",
  "Yeni klasörün adı": "New folder name",
  "Oluştur ve çalış": "Create and work here",
  "Atölyeye dön": "Back to workshop",
  "Kapat": "Close",
  "Yükleniyor…": "Loading…",
  "Bu klasör seçilemez": "This folder cannot be selected",
  "Bir ad yaz": "Type a name",
  "Klasör oluşturulamadı": "Could not create the folder",
  "Buradasın": "You are here",
});

const WorkDir = (() => {
  const bar = document.getElementById("workdir-bar");
  const nameEl = document.getElementById("workdir-name");
  const kindEl = document.getElementById("workdir-kind");
  const iconEl = document.getElementById("workdir-icon");
  const idBtn = document.getElementById("workdir-id");
  const pickBtn = document.getElementById("workdir-pick");
  const newBtn = document.getElementById("workdir-new");

  let boundPath = "";    // currently bound folder ("" = workshop)
  let workshop = "";     // workshop root (workspace)
  let panel = null;      // open picker panel
  let browsing = "";     // directory being browsed in the picker

  const shortName = (path) => String(path || "").replace(/[\\/]+$/, "").split(/[\\/]/).pop() || path;

  // Paint the strip: "Workshop" when in the workshop, otherwise the folder
  // name plus a full-path tooltip.
  function draw(project, workspace) {
    if (!bar) return;
    boundPath = String(project || "");
    workshop = String(workspace || "");
    bar.hidden = false;
    if (boundPath) {
      nameEl.textContent = shortName(boundPath);
      kindEl.textContent = Lang.t("bağlı klasör");
      iconEl.textContent = "📁";
      idBtn.title = boundPath;
      bar.classList.add("bound");
    } else {
      nameEl.textContent = Lang.t("Atölye");
      kindEl.textContent = Lang.t("atölye (varsayılan)");
      iconEl.textContent = "🗂";
      idBtn.title = workshop || Lang.t("Atölye");
      bar.classList.remove("bound");
    }
  }

  // --- picker panel ----------------------------------------------------

  function close() {
    if (panel) { panel.remove(); panel = null; }
  }

  function openPicker(mode) {
    close();
    panel = document.createElement("div");
    panel.className = "workdir-panel";
    const head = document.createElement("div");
    head.className = "workdir-panel-head";
    head.textContent = Lang.t(mode === "new" ? "Yeni klasör" : "Klasör seç");
    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "workdir-close";
    closeBtn.textContent = "✕";
    closeBtn.title = Lang.t("Kapat");
    closeBtn.onclick = close;
    head.append(closeBtn);
    panel.append(head);

    const bodyEl = document.createElement("div");
    bodyEl.className = "workdir-body";
    panel.append(bodyEl);
    bar.parentElement.insertBefore(panel, bar);
    browse(browsing || boundPath || workshop || "", bodyEl, mode);
  }

  // Directory browsing via the server's /api/gozat (no native file dialog:
  // the desktop layer is a separate process; this in-browser explorer is
  // deliberate).
  async function browse(path, bodyEl, mode) {
    bodyEl.textContent = Lang.t("Yükleniyor…");
    let data;
    try {
      data = await (await fetch("/api/gozat?yol=" + encodeURIComponent(path || ""))).json();
    } catch {
      bodyEl.textContent = Lang.t("Bu klasör seçilemez");
      return;
    }
    browsing = data.yol || "";
    bodyEl.textContent = "";

    // Location row + parent folder.
    const crumb = document.createElement("div");
    crumb.className = "workdir-crumb";
    const pathCode = document.createElement("code");
    pathCode.textContent = data.yol || Lang.t("Buradasın");
    crumb.append(pathCode);
    if (data.ust) {
      const upBtn = document.createElement("button");
      upBtn.type = "button";
      upBtn.className = "workdir-up";
      upBtn.textContent = "↑ " + Lang.t("Üst klasör");
      upBtn.onclick = () => browse(data.ust, bodyEl, mode);
      crumb.append(upBtn);
    }
    bodyEl.append(crumb);

    if (data.hata) {
      const h = document.createElement("div");
      h.className = "workdir-warn";
      h.textContent = data.hata;
      bodyEl.append(h);
    }
    if (data.uyari) {
      const u = document.createElement("div");
      u.className = "workdir-warn";
      u.textContent = data.uyari;
      bodyEl.append(u);
    }

    // Subfolders.
    const list = document.createElement("div");
    list.className = "workdir-list";
    for (const k of (data.klasorler || [])) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "workdir-row";
      row.textContent = "📁 " + k.ad;
      row.onclick = () => browse(k.yol, bodyEl, mode);
      list.append(row);
    }
    if (!(data.klasorler || []).length) {
      const blank = document.createElement("div");
      blank.className = "workdir-empty";
      blank.textContent = "—";
      list.append(blank);
    }
    bodyEl.append(list);

    // Action row.
    const actions = document.createElement("div");
    actions.className = "workdir-actions";
    if (mode === "new") {
      const nameInput = document.createElement("input");
      nameInput.type = "text";
      nameInput.className = "input-text";
      nameInput.placeholder = Lang.t("Yeni klasörün adı");
      const createBtn = document.createElement("button");
      createBtn.type = "button";
      createBtn.className = "workdir-go";
      createBtn.textContent = Lang.t("Oluştur ve çalış");
      createBtn.onclick = async () => {
        const name = nameInput.value.trim();
        if (!name) { nameInput.focus(); return; }
        createBtn.disabled = true;
        let c;
        try {
          c = await (await fetch("/api/klasor/olustur", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ust: data.yol, ad: name }),
          })).json();
        } catch { c = { ok: false }; }
        createBtn.disabled = false;
        if (!c || !c.ok) {
          const h = document.createElement("div");
          h.className = "workdir-warn";
          h.textContent = (c && c.hata) || Lang.t("Klasör oluşturulamadı");
          actions.append(h);
          return;
        }
        await bind(c.yol);
      };
      actions.append(nameInput, createBtn);
    } else {
      const chooseBtn = document.createElement("button");
      chooseBtn.type = "button";
      chooseBtn.className = "workdir-go";
      chooseBtn.textContent = Lang.t("Bu klasörde çalış");
      chooseBtn.disabled = !!data.engel || !data.yol;
      if (data.engel) chooseBtn.title = data.engel;
      chooseBtn.onclick = () => bind(data.yol);
      actions.append(chooseBtn);
      if (boundPath) {
        const backBtn = document.createElement("button");
        backBtn.type = "button";
        backBtn.className = "workdir-plain";
        backBtn.textContent = Lang.t("Atölyeye dön");
        backBtn.onclick = () => bind("");
        actions.append(backBtn);
      }
    }
    bodyEl.append(actions);
  }

  // Bind the folder to THIS CONVERSATION (session meta; the global setting
  // does not change).
  async function bind(path) {
    const sid = (typeof sessionId !== "undefined" && sessionId) ? sessionId : "";
    if (!sid) { close(); return; }
    try {
      await fetch("/api/session/meta", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: sid, path: String(path || "") }),
      });
    } catch { /* the state is refreshed again below */ }
    close();
    draw(path, workshop);
    // Read the truth back once the server side applied it to the live agent.
    setTimeout(() => { if (typeof loadState === "function") loadState(); }, 250);
    if (typeof GitBar !== "undefined" && GitBar.refresh) GitBar.refresh();
  }

  if (idBtn) idBtn.onclick = () => (panel ? close() : openPicker("pick"));
  if (pickBtn) pickBtn.onclick = () => openPicker("pick");
  if (newBtn) newBtn.onclick = () => openPicker("new");

  return { draw, close };
})();
