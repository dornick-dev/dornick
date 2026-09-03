// Shared right-click menu. List rows (chat, task, app, git) get their
// actions here instead of the browser's own menu: archive, delete, open.
//
// The item label is built with textContent in the DOM; no markup strings.

const Menu = (() => {
  let openBox = null;
  let closeFn = null;

  function kapat() {
    if (openBox) openBox.remove();
    openBox = null;
    if (closeFn) {
      document.removeEventListener("mousedown", closeFn, true);
      document.removeEventListener("keydown", closeFn, true);
      window.removeEventListener("blur", closeFn);
      closeFn = null;
    }
  }

  function ac(ev, items) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
    }
    kapat();
    const rows = (items || []).filter(Boolean);
    if (!rows.length) return;

    const box = document.createElement("div");
    box.className = "ctx-menu";
    box.setAttribute("role", "menu");

    for (const m of rows) {
      if (m.ayrac) {
        const line = document.createElement("div");
        line.className = "ctx-sep";
        line.setAttribute("role", "separator");
        box.append(line);
        continue;
      }
      const btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("role", "menuitem");
      btn.className = "ctx-item" + (m.risk ? " risk" : "");
      btn.textContent = t(m.ad);
      if (m.ipucu) btn.title = t(m.ipucu);
      if (m.kapali) {
        btn.disabled = true;
        btn.classList.add("off");
      }
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        kapat();
        if (typeof m.is === "function") m.is();
      });
      box.append(btn);
    }

    document.body.append(box);
    box.addEventListener("contextmenu", (e) => e.preventDefault());
    const pad = 8;
    const w = box.offsetWidth;
    const h = box.offsetHeight;
    let x = ev && ev.clientX != null ? ev.clientX : pad;
    let y = ev && ev.clientY != null ? ev.clientY : pad;
    if (x + w > innerWidth - pad) x = Math.max(pad, innerWidth - w - pad);
    if (y + h > innerHeight - pad) y = Math.max(pad, innerHeight - h - pad);
    box.style.left = x + "px";
    box.style.top = y + "px";
    openBox = box;

    closeFn = (e) => {
      if (e.type === "keydown" && e.key !== "Escape") return;
      if (e.type === "mousedown" && box.contains(e.target)) return;
      kapat();
    };
    document.addEventListener("mousedown", closeFn, true);
    document.addEventListener("keydown", closeFn, true);
    window.addEventListener("blur", closeFn);
  }

  // --- clipboard menu ---------------------------------------------------
  //
  // pywebview disables WebView2's default right-click menu IN PRODUCTION
  // (open only in debug): copy/paste was left without a menu (native tour,
  // 31.08). Clipboard access goes through the pywebview bridge
  // (pano_oku/pano_yaz) — it does not hit the browser permission gate;
  // without the bridge (browser preview) it falls back to navigator.clipboard.

  function clipWrite(text) {
    try {
      if (window.pywebview && window.pywebview.api.pano_yaz) {
        window.pywebview.api.pano_yaz(String(text));
        return;
      }
    } catch { /* no bridge */ }
    try { navigator.clipboard.writeText(String(text)); } catch { /* no permission */ }
  }

  async function clipRead() {
    try {
      if (window.pywebview && window.pywebview.api.pano_oku) {
        return String(await window.pywebview.api.pano_oku() || "");
      }
    } catch { /* no bridge */ }
    try { return String(await navigator.clipboard.readText() || ""); }
    catch { return ""; }
  }

  function insertText(target, text) {
    target.focus();
    const b = target.selectionStart ?? target.value.length;
    const e = target.selectionEnd ?? b;
    target.value = target.value.slice(0, b) + text + target.value.slice(e);
    target.selectionStart = target.selectionEnd = b + text.length;
    target.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function cutSelection(target) {
    const b = target.selectionStart ?? 0, e = target.selectionEnd ?? 0;
    target.value = target.value.slice(0, b) + target.value.slice(e);
    target.selectionStart = target.selectionEnd = b;
    target.dispatchEvent(new Event("input", { bubbles: true }));
  }

  document.addEventListener("contextmenu", (ev) => {
    // Rows with a menu of their own (the chat list etc.) use their own
    // paths; with stopPropagation they never fall through to here.
    const target = ev.target.closest("input, textarea");
    const editable = target && !target.readOnly && !target.disabled
      && target.type !== "checkbox" && target.type !== "radio";
    const selection = String(window.getSelection() || "");
    const fieldSelection = editable
      ? String(target.value || "").slice(target.selectionStart ?? 0, target.selectionEnd ?? 0)
      : "";
    const toCopy = fieldSelection || selection;
    if (!editable && !toCopy) return;   // nothing worth a menu
    const items = [];
    if (toCopy) {
      items.push({ ad: "Kopyala", is: () => clipWrite(toCopy) });
    }
    if (editable && fieldSelection) {
      items.push({ ad: "Kes", is: () => { clipWrite(fieldSelection); cutSelection(target); } });
    }
    if (editable) {
      items.push({ ad: "Yapıştır",
                      is: () => { clipRead().then((m) => { if (m) insertText(target, m); }); } });
      items.push({ ad: "Tümünü seç",
                      is: () => { target.focus(); target.select && target.select(); } });
    }
    ac(ev, items);
  });

  return { ac, kapat };
})();
