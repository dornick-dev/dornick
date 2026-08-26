// Görüntüleyici: ajanın o an dokunduğu şey.
//
// Sohbet ne yapıldığını anlatıyor ama gösteremiyor. Ajan bir betik yazdığında
// "yazdım" cümlesini okumakla dosyayı görmek aynı şey değil; bir site kurunca
// da kaynağı değil sitenin kendisini görmek gerekiyor.
//
// Bu yüzden panel iki kip taşıyor:
//
//   kaynak    dosya, biçimlendiriciden geçmiş halde
//   sahne     .html ise gerçekten çalışan hali, yalıtılmış bir çerçevede
//
// Kendiliğinden açılıyor: ajan bir dosyaya dokunduğunda panel o dosyaya
// geçiyor. Kullanıcı kapatırsa bir daha zorlamıyor — kapatmak bir karar.

const Viewer = (() => {
  const panel = document.getElementById("viewer");
  const title = document.getElementById("viewer-path");
  const body = document.getElementById("viewer-body");
  const modes = document.getElementById("viewer-modes");

  // Bu araçlar bir dosyaya dokunuyor; hangisinin hangi argümanda olduğu
  // araca göre değişiyor.
  const WATCHED = new Set(["read_file", "write_file", "edit_file", "copy_in", "draw"]);

  // Çizim bir dosya değil bir sunum: ajan onu göstermek için çağırıyor.
  // Kullanıcı paneli daha önce kapattıysa bile açılıyor ve kaynak değil
  // sahne kipinde geliyor — çizimin HTML'ini okumak istenen şey değil.
  const PRESENTS = new Set(["draw"]);

  let current = "";
  let mode = "source";
  let dismissed = false;
  let loading = null;

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  // --- dışarıya açık -----------------------------------------------------

  function watch(tool, args) {
    if (!WATCHED.has(tool) || !args) return;
    if (PRESENTS.has(tool)) return;   // yolu araç bitince geliyor
    const path = args.to || args.path;
    if (typeof path === "string" && path.trim()) show(path.trim());
  }

  // Ajan bir çizim koydu: paneli aç, sahne kipine geç.
  function present(path) {
    if (typeof path !== "string" || !path.trim()) return;
    dismissed = false;
    mode = "live";
    show(path.trim());
  }

  // İş bittiğinde gösterileni tazele: yazma tamamlandığında panelde hâlâ
  // eski içerik duruyordu. Aracın bildirdiği yol çözülmüş halde geliyor,
  // o yüzden `current` ile birebir tutmayabilir — panel açıksa ve dokunulan
  // araç izlenenlerdense yeniden yüklemek en doğrusu.
  function refresh(tool, path) {
    if (PRESENTS.has(tool)) { present(path); return; }
    if (panel.hidden || !WATCHED.has(tool)) return;
    if (typeof path === "string" && path.trim()) { current = path.trim(); }
    load(current);
  }

  function show(path) {
    current = path;
    if (dismissed) return;      // kullanıcı kapattı; zorlamıyoruz
    panel.hidden = false;
    document.body.classList.add("viewing");
    load(path);
  }

  function close() {
    panel.hidden = true;
    dismissed = true;
    document.body.classList.remove("viewing");
  }

  function toggle() {
    if (panel.hidden) {
      dismissed = false;
      panel.hidden = false;
      document.body.classList.add("viewing");
      load(current);
    } else {
      close();
    }
  }

  // --- yükleme -----------------------------------------------------------

  // Basliga son iki parca yaziliyor: tam yol satiri dolduruyor ve kirpilinca
  // geriye "…html" gibi hicbir sey soylemeyen bir kalinti kaliyordu.
  function label(path) {
    const parts = String(path || "").split(/[\/]/).filter(Boolean);
    return parts.length > 2 ? "…/" + parts.slice(-2).join("/") : parts.join("/");
  }

  async function load(path) {
    title.textContent = label(path) || "—";
    title.title = path || "";
    if (!path) { blank("Henüz bir şeye dokunulmadı"); return; }

    // Aynı dosya art arda birkaç kez tetiklenebiliyor; son istek kazanmalı.
    const token = {};
    loading = token;

    let data;
    try {
      data = await (await fetch("/api/files?path=" + encodeURIComponent(path))).json();
    } catch {
      if (loading === token) blank("Okunamadı");
      return;
    }
    if (loading !== token) return;

    if (data.error || data.entries) { blank("Bu bir dizin"); return; }
    render(data);
  }

  function blank(text) {
    body.textContent = "";
    modes.textContent = "";
    body.append(el("p", "viewer-blank", text));
  }

  function render(data) {
    body.textContent = "";
    drawModes(data);

    if (data.binary) { body.append(el("p", "viewer-blank", "İkili dosya")); return; }

    if (mode === "live" && isPage(data.path)) {
      body.append(frame(data.text || ""));
      return;
    }

    const holder = el("div", "viewer-source");
    holder.append(Markdown.render(fenced(data)));
    body.append(holder);
    if (data.truncated) body.append(el("p", "viewer-blank", "Dosyanın başı gösteriliyor"));
  }

  // .md dosyası biçimlendirilmiş görünmeli; gerisi kod bloğu olarak.
  function fenced(data) {
    const text = data.text || "";
    if (/\.mdx?$/i.test(data.path)) return text;
    return "```" + language(data.path) + "\n" + text + "\n```";
  }

  function drawModes(data) {
    modes.textContent = "";
    if (!isPage(data.path)) { mode = "source"; return; }

    for (const [id, label] of [["source", "Kaynak"], ["live", "Sahne"]]) {
      const button = el("button", mode === id ? "on" : "", label);
      button.type = "button";
      button.addEventListener("click", () => { mode = id; render(data); });
      modes.append(button);
    }
  }

  // Ajanın kurduğu sayfa gerçekten çalışsın diye çerçevede gösteriliyor ama
  // yalıtılmış: `allow-same-origin` verilmiyor, yani sayfa bu programın
  // DOM'una, çerezlerine ve `/api` uçlarına erişemiyor.
  function frame(html) {
    const node = document.createElement("iframe");
    node.className = "viewer-frame";
    node.setAttribute("sandbox", "allow-scripts");
    node.setAttribute("referrerpolicy", "no-referrer");
    node.srcdoc = html;
    return node;
  }

  const isPage = (path) => /\.html?$/i.test(path || "");

  const EXT = { py: "python", js: "javascript", ts: "typescript", ps1: "powershell",
                sh: "bash", json: "json", css: "css", html: "html", htm: "html",
                sql: "sql", yml: "yaml", yaml: "yaml", toml: "toml", jsonl: "json" };

  const language = (path) => EXT[(path.split(".").pop() || "").toLowerCase()] || "";

  // --- bağlama -----------------------------------------------------------

  document.getElementById("eye").addEventListener("click", toggle);
  document.getElementById("viewer-close").addEventListener("click", close);

  // Panel kenarından sürükleyip genişletme. Genişlik tek bir CSS
  // değişkeninde (`--viewer-w`); onu değiştirmek hem paneli hem de sohbet
  // sütununun kaymasını birlikte güncelliyor. Sınırlar: çok darda başlık
  // okunmuyor, çok genişte sohbete yer kalmıyor.
  (() => {
    const grip = document.getElementById("viewer-grip");
    if (!grip) return;
    const MIN = 320;
    const root = document.documentElement;
    let active = false;

    const width = () => panel.getBoundingClientRect().width;

    const move = (e) => {
      if (!active) return;
      const max = Math.min(window.innerWidth - 200, window.innerWidth * 0.7);
      const w = Math.max(MIN, Math.min(max, window.innerWidth - e.clientX));
      root.style.setProperty("--viewer-w", w + "px");
    };

    const stop = () => {
      active = false;
      document.body.classList.remove("viewer-resize");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };

    grip.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      active = true;
      // Sürüklemeye başlarken mevcut genişliği piksele sabitle: değişken
      // hâlâ `min(...)` formülündeyse ilk hareket sıçrardı.
      root.style.setProperty("--viewer-w", Math.round(width()) + "px");
      document.body.classList.add("viewer-resize");
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", stop);
    });
  })();

  return { present, watch, refresh, show, close, toggle };
})();
