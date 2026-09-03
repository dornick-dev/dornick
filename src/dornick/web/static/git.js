// Git bar + the commit/diff board inside the Viewer.
//
// The bar sits above the composer: repo + branch; +N −M and Commit when
// dirty; Publish when there is no remote. Clicking opens the existing
// Viewer (no new shell).

Dil.ekle({
  "Değişiklikler": "Changes",
  "Commit": "Commit",
  "Push": "Push",
  "Yayınla": "Publish",
  "Dosyayı aç": "Open file",
  "farkı gör": "see the diff",
  "farkı gizle": "hide the diff",
  "Commit mesajı": "Commit message",
  "Temiz.": "Clean.",
  "git deposu yok": "no git repo",
  "İkili dosya — fark çizilmiyor.": "Binary file — no diff drawn.",
  "Yükleniyor…": "Loading…",
  "Repo aç": "Create repo",
  "repo yok": "no repo",
  "klasörü aç": "open folder",
  "Açılamadı": "Could not open",
  "Fark okunamadı.": "Could not read the diff.",
});

const GitBar = (() => {
  const bar = document.getElementById("git-bar");
  const nameEl = document.getElementById("git-name");
  const branchEl = document.getElementById("git-branch");
  const statEl = document.getElementById("git-stat");
  const plusEl = document.getElementById("git-plus");
  const minusEl = document.getElementById("git-minus");
  const commitBtn = document.getElementById("git-commit");
  const publishBtn = document.getElementById("git-publish");

  let snap = null;
  let busy = false;
  let msgDraft = "";
  let poll = 0;

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  const fmt = (n) => Number(n || 0).toLocaleString("tr-TR");

  async function refresh() {
    let next = null;
    try {
      next = await (await fetch("/api/git")).json();
    } catch { next = null; }
    snap = next;
    drawBar();
    if (hosted()) paint();
  }

  function hosted() {
    return typeof Viewer !== "undefined" && Viewer.hosted && Viewer.hosted();
  }

  function drawBar() {
    if (!bar) return;
    if (!snap || !snap.present) {
      // No repo but the working folder EXISTS: the bar still shows —
      // "Repo aç" (git init) is one click away and the folder name opens
      // Explorer. The old version hid the bar entirely; the user could not
      // create a repo from the UI at all ("create repo diyemiyorum" —
      // live request, 31.08).
      const path = snap && snap.root;
      if (!path) {
        bar.hidden = true;
        document.body.style.setProperty("--git-h", "0px");
        return;
      }
      bar.hidden = false;
      bar.dataset.root = path;
      nameEl.textContent = snap.name || String(path).split(/[\\/]/).pop();
      nameEl.title = path + " — " + t("klasörü aç");
      branchEl.textContent = t("repo yok");
      statEl.hidden = true;
      commitBtn.hidden = true;
      publishBtn.hidden = false;
      publishBtn.textContent = t("Repo aç");
      document.body.style.setProperty("--git-h", bar.offsetHeight + "px");
      return;
    }
    bar.hidden = false;
    if (snap.root) bar.dataset.root = snap.root;
    nameEl.textContent = snap.name || "";
    branchEl.textContent = snap.branch || "";
    const dirty = !!snap.dirty;
    statEl.hidden = !dirty;
    if (dirty) {
      plusEl.textContent = "+" + fmt(snap.plus);
      minusEl.textContent = "−" + fmt(snap.minus);
    }
    commitBtn.hidden = !dirty;
    publishBtn.hidden = !!snap.remote;
    commitBtn.textContent = t("Commit");
    publishBtn.textContent = t("Yayınla");
    document.body.style.setProperty("--git-h", "0px");
  }

  function openPane() {
    if (typeof Viewer === "undefined" || !Viewer.host) return;
    Viewer.host((snap && snap.name) || "Git", paint);
  }

  function paint(body) {
    const host = body || document.getElementById("viewer-body");
    if (!host) return;
    const pane = el("div", "git-pane");
    const list = el("div", "git-pane-list");
    const files = (snap && snap.files) || [];
    if (!snap || !snap.present) {
      list.append(el("p", "viewer-blank", t("git deposu yok")));
    } else if (!files.length) {
      list.append(el("p", "viewer-blank", t("Temiz.")));
    } else {
      for (const row of files) list.append(fileRow(row));
    }
    pane.append(list);

    const foot = el("div", "git-pane-foot");
    const msg = document.createElement("textarea");
    msg.className = "git-msg";
    msg.rows = 2;
    msg.placeholder = t("Commit mesajı");
    msg.value = msgDraft;
    msg.addEventListener("input", () => { msgDraft = msg.value; });
    foot.append(msg);

    const acts = el("div", "git-pane-acts");
    const commit = el("button", "git-act", t("Commit"));
    commit.type = "button";
    commit.disabled = busy || !(snap && snap.dirty);
    commit.addEventListener("click", () => act("commit", { message: msg.value }));
    acts.append(commit);

    const push = el("button", "git-act", t("Push"));
    push.type = "button";
    push.disabled = busy || !(snap && snap.remote);
    push.hidden = !(snap && snap.remote);
    push.addEventListener("click", () => act("push"));
    acts.append(push);

    const pub = el("button", "git-act", t("Yayınla"));
    pub.type = "button";
    pub.disabled = busy;
    pub.hidden = !!(snap && snap.remote);
    pub.addEventListener("click", () => act("publish"));
    acts.append(pub);

    const err = el("div", "git-err");
    err.hidden = true;
    foot.append(acts, err);
    pane.append(foot);
    host.replaceChildren(pane);
    pane._err = err;
    pane._msg = msg;
  }

  function fileRow(row) {
    const rowEl = el("div", "chg-row");
    const head = el("div", "chg-row-head");
    const mark = row.status === "?" || row.status === "A" ? "+"
      : row.status === "D" ? "−" : "~";
    head.append(el("span", "chg-mark", mark));
    const nameB = el("b", null, row.path);
    nameB.title = row.path;
    head.append(nameB);
    if (row.plus || row.minus) {
      const st = el("span", "chg-tool",
        "+" + fmt(row.plus) + " −" + fmt(row.minus));
      head.append(st);
    }
    const acts = el("div", "chg-row-acts");
    const diffBtn = el("button", "chg-diff-btn", t("farkı gör"));
    diffBtn.type = "button";
    acts.append(diffBtn);
    if (row.open && typeof Viewer !== "undefined") {
      const open = el("button", "git-open-btn", t("Dosyayı aç"));
      open.type = "button";
      open.addEventListener("click", () => Viewer.open(row.open));
      acts.append(open);
    }
    head.append(acts);
    rowEl.append(head);
    const box = el("div", "chg-diff");
    box.hidden = true;
    rowEl.append(box);
    rowEl.addEventListener("contextmenu", (ev) => {
      if (typeof Menu === "undefined") return;
      const items = [];
      if (row.open && typeof Viewer !== "undefined") {
        items.push({ ad: "Dosyayı aç", is: () => Viewer.open(row.open) });
      }
      items.push({
        ad: box.hidden ? "farkı gör" : "farkı gizle",
        is: () => diffBtn.click(),
      });
      Menu.ac(ev, items);
    });
    let loaded = false;
    diffBtn.addEventListener("click", async () => {
      box.hidden = !box.hidden;
      diffBtn.textContent = box.hidden ? t("farkı gör") : t("farkı gizle");
      if (loaded || box.hidden) return;
      loaded = true;
      box.replaceChildren(el("div", "diff-empty dugum-yukleniyor", t("Yükleniyor…")));
      let data = null;
      try {
        data = await (await fetch("/api/git", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "diff", path: row.path }),
        })).json();
      } catch { data = null; }
      box.replaceChildren(diffBox(data));
    });
    return rowEl;
  }

  function diffBox(data) {
    if (!data || data.ok === false) {
      return el("div", "diff-empty", (data && data.error) || t("Fark okunamadı."));
    }
    if (data.binary) {
      return el("div", "diff-empty", t("İkili dosya — fark çizilmiyor."));
    }
    if (typeof diffHunk !== "function") {
      return el("div", "diff-empty", (data.path || "") + "  +" + fmt(data.plus)
        + " −" + fmt(data.minus));
    }
    return diffHunk(data.old, data.new, 1);
  }

  async function act(action, extra) {
    if (busy) return;
    busy = true;
    drawBar();
    if (hosted()) paint();
    let data = null;
    try {
      data = await (await fetch("/api/git", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...(extra || {}) }),
      })).json();
    } catch {
      data = { ok: false, error: t("Açılamadı") };
    }
    busy = false;
    if (data && data.ok === false) {
      snap = snap || {};
      drawBar();
      if (hosted()) paint();
      const pane = document.querySelector(".git-pane");
      if (pane && pane._err) {
        pane._err.hidden = false;
        pane._err.textContent = data.error || "";
      }
      return;
    }
    if (action === "commit") msgDraft = "";
    await refresh();
  }

  function touched(tool) {
    if (tool === "write_file" || tool === "edit_file" || tool === "copy_in"
        || tool === "git") refresh();
  }

  function tick() {
    if (document.hidden || !document.hasFocus()) return;
    refresh();
  }

  // Opens the working folder in Explorer — "I cannot get from the chat to
  // the folder" (live request, 31.08): the name on the bar is now the door.
  async function openFolder() {
    const path = (snap && snap.root) || bar.dataset.root || "";
    if (!path) return;
    try {
      await fetch("/api/apps/reveal", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
    } catch { /* silent: best effort */ }
  }

  if (bar) {
    document.getElementById("git-id").title = t("Değişiklikler");
    document.getElementById("git-id").addEventListener("click", openPane);
    nameEl.style.cursor = "pointer";
    nameEl.addEventListener("click", (ev) => { ev.stopPropagation(); openFolder(); });
    statEl.addEventListener("click", openPane);
    commitBtn.addEventListener("click", openPane);
    publishBtn.addEventListener("click", (ev) => {
      // Without a repo, "Repo aç": straight to git init — no board detour.
      if (snap && !snap.present) { ev.stopPropagation(); act("init"); return; }
      openPane();
    });
  }
  refresh();
  poll = setInterval(tick, 4000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });

  return { refresh, paint, openPane, touched };
})();
