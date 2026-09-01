// Pencere düğmeleri + tek şerit sürükleme / kenar resize.
//
// Tarayıcıda `window.pywebview` yok; düğmeler o zaman gizli kalır.

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

    // Kenar resize: üst kenarın ORTASI şerit sürüklemesine aittir —
    // yalnız köşelerde "t" (üst) resize; aksi halde üst 8px drag'i çalıyordu.
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
        // Üst orta: HUD / kamera şeridi içindeyse resize etme (sürükleme).
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

    // Şerit sürükleme → HTCAPTION (Python UI thread'de SendMessage).
    if (typeof window.pywebview.api.drag === "function") {
      const hud = document.querySelector(".hud") || document.querySelector(".watch-bar");
      const syncZoom = (zoomed) => {
        if (maxBtn) maxBtn.classList.toggle("zoomed", !!zoomed);
      };
      if (hud) {
        const startDrag = (e) => {
          if (e.button !== 0) return;
          if (e.target.closest("button, a, input, textarea, select")) return;
          // Üst köşe resize'a bırak.
          const EDGE = 8;
          const w = window.innerWidth;
          if (e.clientY < EDGE && (e.clientX < EDGE || e.clientX >= w - EDGE)) return;
          e.preventDefault();
          // Hemen çağır — Promise bekleme; fare basılıyken UI thread'e ulaşsın.
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
