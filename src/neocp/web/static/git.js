// Git çubuğu + Viewer'daki commit/diff panosu.
//
// Çubuk composer'ın üstünde: repo + dal; kirliyken +N −M ve Commit;
// uzak yoksa Yayınla. Tıklanınca mevcut Viewer açılır (yeni kabuk yok).

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
      // Depo yok ama çalışma klasörü VAR: çubuk yine görünür — "Repo aç"
      // (git init) tek tık uzakta ve klasör adı Explorer'ı açar. Eski hal
      // çubuğu tamamen gizliyordu; kullanıcı repo açmayı arayüzden hiç
      // yapamıyordu ("create repo diyemiyorum" — canlı istek, 31.08).
      const yol = snap && snap.root;
      if (!yol) {
        bar.hidden = true;
        document.body.style.setProperty("--git-h", "0px");
        return;
      }
      bar.hidden = false;
      bar.dataset.root = yol;
      nameEl.textContent = snap.name || String(yol).split(/[\\/]/).pop();
      nameEl.title = yol + " — " + t("klasörü aç");
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
    const satir = el("div", "chg-row");
    const bas = el("div", "chg-row-head");
    const mark = row.status === "?" || row.status === "A" ? "+"
      : row.status === "D" ? "−" : "~";
    bas.append(el("span", "chg-mark", mark));
    const ad = el("b", null, row.path);
    ad.title = row.path;
    bas.append(ad);
    if (row.plus || row.minus) {
      const st = el("span", "chg-tool",
        "+" + fmt(row.plus) + " −" + fmt(row.minus));
      bas.append(st);
    }
    const acts = el("div", "chg-row-acts");
    const fark = el("button", "chg-diff-btn", t("farkı gör"));
    fark.type = "button";
    acts.append(fark);
    if (row.open && typeof Viewer !== "undefined") {
      const open = el("button", "git-open-btn", t("Dosyayı aç"));
      open.type = "button";
      open.addEventListener("click", () => Viewer.open(row.open));
      acts.append(open);
    }
    bas.append(acts);
    satir.append(bas);
    const kutu = el("div", "chg-diff");
    kutu.hidden = true;
    satir.append(kutu);
    satir.addEventListener("contextmenu", (ev) => {
      if (typeof Menu === "undefined") return;
      const maddeler = [];
      if (row.open && typeof Viewer !== "undefined") {
        maddeler.push({ ad: "Dosyayı aç", is: () => Viewer.open(row.open) });
      }
      maddeler.push({
        ad: kutu.hidden ? "farkı gör" : "farkı gizle",
        is: () => fark.click(),
      });
      Menu.ac(ev, maddeler);
    });
    let yuklendi = false;
    fark.addEventListener("click", async () => {
      kutu.hidden = !kutu.hidden;
      fark.textContent = kutu.hidden ? t("farkı gör") : t("farkı gizle");
      if (yuklendi || kutu.hidden) return;
      yuklendi = true;
      kutu.replaceChildren(el("div", "diff-empty", t("Yükleniyor…")));
      let veri = null;
      try {
        veri = await (await fetch("/api/git", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "diff", path: row.path }),
        })).json();
      } catch { veri = null; }
      kutu.replaceChildren(diffBox(veri));
    });
    return satir;
  }

  function diffBox(veri) {
    if (!veri || veri.ok === false) {
      return el("div", "diff-empty", (veri && veri.error) || t("Fark okunamadı."));
    }
    if (veri.binary) {
      return el("div", "diff-empty", t("İkili dosya — fark çizilmiyor."));
    }
    if (typeof diffHunk !== "function") {
      return el("div", "diff-empty", (veri.path || "") + "  +" + fmt(veri.plus)
        + " −" + fmt(veri.minus));
    }
    return diffHunk(veri.old, veri.new, 1);
  }

  async function act(action, extra) {
    if (busy) return;
    busy = true;
    drawBar();
    if (hosted()) paint();
    let veri = null;
    try {
      veri = await (await fetch("/api/git", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...(extra || {}) }),
      })).json();
    } catch {
      veri = { ok: false, error: t("Açılamadı") };
    }
    busy = false;
    if (veri && veri.ok === false) {
      snap = snap || {};
      drawBar();
      if (hosted()) paint();
      const pane = document.querySelector(".git-pane");
      if (pane && pane._err) {
        pane._err.hidden = false;
        pane._err.textContent = veri.error || "";
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

  // Çalışma klasörünü Explorer'da açar — "sohbetten klasöre gidemiyorum"
  // (canlı istek, 31.08): çubuktaki ad artık kapı.
  async function klasoruAc() {
    const yol = (snap && snap.root) || bar.dataset.root || "";
    if (!yol) return;
    try {
      await fetch("/api/apps/reveal", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: yol }),
      });
    } catch { /* sessiz: en iyi çaba */ }
  }

  if (bar) {
    document.getElementById("git-id").title = t("Değişiklikler");
    document.getElementById("git-id").addEventListener("click", openPane);
    nameEl.style.cursor = "pointer";
    nameEl.addEventListener("click", (ev) => { ev.stopPropagation(); klasoruAc(); });
    statEl.addEventListener("click", openPane);
    commitBtn.addEventListener("click", openPane);
    publishBtn.addEventListener("click", (ev) => {
      // Depo yokken "Repo aç": doğrudan git init — panoya gitmeden.
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
