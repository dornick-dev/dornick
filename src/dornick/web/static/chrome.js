// Window buttons + single-strip dragging / edge resize.
//
// In a browser `window.pywebview` does not exist; the buttons then stay hidden.

(() => {
  const chrome = document.getElementById("chrome");
  const ready = () => !!(window.pywebview && window.pywebview.api);

  let bound = false;

  function bind() {
    if (!ready()) return false;
    if (chrome) chrome.hidden = false;
    const api = window.pywebview.api;
    if (typeof api.minimize !== "function" || typeof api.close !== "function") {
      return false;
    }
    if (bound) return true;
    bound = true;

    const maxBtn = document.getElementById("win-max");
    const acts = {
      "win-min": () => api.minimize(),
      "win-max": () => api.maximize().then((zoomed) => {
        if (maxBtn) maxBtn.classList.toggle("zoomed", !!zoomed);
      }),
      "win-close": () => api.close(),
    };

    for (const [id, act] of Object.entries(acts)) {
      const button = document.getElementById(id);
      if (!button) continue;
      button.hidden = false;
      button.addEventListener("click", () => {
        if (button.dataset.busy) return;
        button.dataset.busy = "1";
        Promise.resolve(act()).finally(() => {
          setTimeout(() => delete button.dataset.busy, 250);
        });
      });
    }

    // Edge resize: the MIDDLE of the top edge belongs to the strip drag —
    // "t" (top) resize only at the corners; otherwise the top 8px stole the drag.
    if (typeof window.pywebview.api.resize === "function") {
      const EDGE = 8;
      const zone = (e) => {
        const w = window.innerWidth, h = window.innerHeight;
        const l = e.clientX < EDGE, r = e.clientX >= w - EDGE;
        const t = e.clientY < EDGE, b = e.clientY >= h - EDGE;
        if (t && l) return "tl"; if (t && r) return "tr";
        if (b && l) return "bl"; if (b && r) return "br";
        if (l) return "l"; if (r) return "r";
        if (b) return "b";
        // Top middle: if inside the HUD / camera strip, do not resize (dragging).
        if (t && !e.target.closest(".hud, .watch-bar")) return "t";
        return "";
      };
      const CUR = { l: "ew-resize", r: "ew-resize", t: "ns-resize", b: "ns-resize",
                    tl: "nwse-resize", br: "nwse-resize", tr: "nesw-resize", bl: "nesw-resize" };
      document.addEventListener("pointermove", (e) => {
        const z = zone(e);
        document.documentElement.style.cursor = z ? CUR[z] : "";
      });
      document.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        const z = zone(e);
        if (!z) return;
        e.preventDefault();
        e.stopPropagation();
        window.pywebview.api.resize(z);
      }, true);
    }

    // Strip dragging → HTCAPTION (SendMessage on the Python UI thread).
    if (typeof window.pywebview.api.drag === "function") {
      const hud = document.querySelector(".hud") || document.querySelector(".watch-bar");
      const syncZoom = (zoomed) => {
        if (maxBtn) maxBtn.classList.toggle("zoomed", !!zoomed);
      };
      if (hud) {
        const startDrag = (e) => {
          if (e.button !== 0) return;
          if (e.target.closest("button, a, input, textarea, select")) return;
          // Leave the top corners to resize.
          const EDGE = 8;
          const w = window.innerWidth;
          if (e.clientY < EDGE && (e.clientX < EDGE || e.clientX >= w - EDGE)) return;
          e.preventDefault();
          // Call immediately — no awaiting the Promise; it must reach the UI thread while the mouse is down.
          const p = window.pywebview.api.drag();
          if (p && typeof p.then === "function") p.then(syncZoom).catch(() => {});
        };
        hud.addEventListener("pointerdown", startDrag);
        hud.addEventListener("dblclick", (e) => {
          if (e.target.closest("button, a, input, textarea, select")) return;
          Promise.resolve(window.pywebview.api.maximize()).then(syncZoom);
        });
      }
    }
    return true;
  }

  if (!bind()) {
    window.addEventListener("pywebviewready", bind, { once: true });
    let tries = 0;
    const timer = setInterval(() => {
      if (bind() || ++tries > 40) clearInterval(timer);
    }, 100);
  }
})();
