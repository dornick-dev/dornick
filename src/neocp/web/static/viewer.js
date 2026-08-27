// Görüntüleyici: ajanın o an dokunduğu şey.
//
// Sohbet ne yapıldığını anlatıyor ama gösteremiyor. Ajan bir betik yazdığında
// "yazdım" cümlesini okumakla dosyayı görmek aynı şey değil; bir site kurunca
// da kaynağı değil sitenin kendisini görmek gerekiyor.
//
// Bu yüzden panel iki kip taşıyor:
//
//   kaynak    dosya, satır numaralı ve renklendirilmiş bir kod görünümünde
//   sahne     .html ise gerçekten çalışan hali, yalıtılmış bir çerçevede
//
// Kendiliğinden açılıyor: ajan bir dosyaya dokunduğunda panel o dosyaya
// geçiyor. Kullanıcı kapatırsa bir daha zorlamıyor — kapatmak bir karar.

const Viewer = (() => {
  const panel = document.getElementById("viewer");
  const title = document.getElementById("viewer-path");
  const body = document.getElementById("viewer-body");
  const modes = document.getElementById("viewer-modes");

  Dil.ekle({
    "Kaynak": "Source", "Sahne": "Stage",
    "Kopyala": "Copy", "Kopyalandı ✓": "Copied ✓", "Kopyalanamadı": "Copy failed",
    "Sar": "Wrap", "Uzun satırları sar / tek satırda kaydır": "Wrap long lines / scroll instead",
    "Dosyayı panoya kopyala": "Copy file to clipboard",
    "İkili dosya": "Binary file", "Bu bir dizin": "This is a directory",
    "Görsel açılamadı": "Could not open the image",
    "Tıkla — 1:1 boyut / sığdır": "Click — actual size / fit",
    "Tıkla — sığdır": "Click — fit",
    "Tarayıcıda aç": "Open in browser", "Klasörde göster": "Show in folder",
    "Açılamadı": "Could not open",
    "Okunamadı": "Could not read", "Henüz bir şeye dokunulmadı": "Nothing touched yet",
    "Dosyanın başı gösteriliyor": "Showing the head of the file",
    "Sayfa yok": "No page",
  });

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
  let sourceText = "";   // kopyala düğmesi için: o an gösterilen ham metin
  let wrap = false;      // uzun satırlar: kaydır (false) / sar (true)

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

  // Sunucudan servis edilen CANLI bir sayfa (artifact gibi): dosya değil
  // adres. İçerik her açılışta sunucudan taze çekilir ve çizimlerle AYNI
  // yalıtılmış çerçevede gösterilir (allow-same-origin yok): ajanın yazdığı
  // sayfa programın DOM'una ve /api uçlarına erişemiyor — kendi izin
  // kapısını betikle atlaması bu programda en pahalı hata olurdu.
  let pageLabel = "";

  function page(url, label) {
    if (typeof url !== "string" || !url.trim()) return;
    dismissed = false;
    mode = "live";
    pageLabel = label || url;
    current = "url:" + url.trim();
    panel.hidden = false;
    document.body.classList.add("viewing");
    load(current);
  }

  // Bu adres şu an panelde açık mı? (artifact güncellenince tazelemek için)
  function showing(url) {
    return !panel.hidden && current === "url:" + url;
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

  // Sohbetteki bir dosya referansından geliniyor: paneli AÇ (kullanıcı daha
  // önce kapatmış olsa bile — bu bir kullanıcı isteği, ajanın dayatması
  // değil) ve satır verildiyse oraya kaydırıp vurgula.
  //
  // Satır beklemeli bir iş: dosya sunucudan geliyor ve satırlar ancak
  // çizildikten sonra var oluyor. `pendingLine` çizimin sonunda okunuyor.
  function open(path, line) {
    if (typeof path !== "string" || !path.trim()) return;
    dismissed = false;
    mode = "source";
    pendingLine = Number(line) > 0 ? Number(line) : 0;
    const target = path.trim();
    // Aynı dosya zaten açıksa yeniden yüklemeye gerek yok: sadece satıra git.
    if (!panel.hidden && current === target) { gotoLine(pendingLine); return; }
    show(target);
  }

  let pendingLine = 0;

  // Satıra git: kaydır ve kısa bir vurgu bırak. Vurgu kalıcı değil —
  // "hangi satırdı" sorusunu cevaplayacak kadar duruyor, sonra soluyor;
  // kalıcı olsa dosyada gezinirken yanlış yeri işaret eden bir leke olurdu.
  function gotoLine(line) {
    pendingLine = 0;
    if (!(line > 0)) return;
    const rows = body.querySelectorAll(".viewer-code .vl");
    const row = rows[line - 1];
    if (!row) return;
    for (const eski of body.querySelectorAll(".vl.hit")) eski.classList.remove("hit");
    row.classList.add("hit");
    row.scrollIntoView({ block: "center", behavior: "smooth" });
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

  // Dosya boyutu başlıkta: "hangi dosya" kadar "ne kadarlık bir şey" de
  // bir bakışta okunmalı.
  function human(bytes) {
    if (typeof bytes !== "number") return "";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  }

  async function load(path) {
    // Adres kipi: sunucunun servis ettiği sayfa taze çekilip yalıtılmış
    // çerçevede açılıyor. Aynı yarış kuralı: son istek kazanır.
    if (typeof path === "string" && path.startsWith("url:")) {
      const url = path.slice(4);
      title.textContent = pageLabel || url;
      title.title = url;
      modes.textContent = "";
      const token = {};
      loading = token;
      let html = "";
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) {
          if (loading === token) blank(t("Sayfa yok") + " (" + res.status + ")");
          return;
        }
        html = await res.text();
      } catch {
        if (loading === token) blank(t("Okunamadı"));
        return;
      }
      if (loading !== token) return;
      body.textContent = "";
      body.append(frame(html));
      return;
    }

    title.textContent = label(path) || "—";
    title.title = path || "";
    if (!path) { blank(t("Henüz bir şeye dokunulmadı")); return; }

    // Aynı dosya art arda birkaç kez tetiklenebiliyor; son istek kazanmalı.
    const token = {};
    loading = token;

    let data;
    try {
      data = await (await fetch("/api/files?path=" + encodeURIComponent(path))).json();
    } catch {
      if (loading === token) blank(t("Okunamadı"));
      return;
    }
    if (loading !== token) return;

    if (data.error || data.entries) { blank(t("Bu bir dizin")); return; }
    render(data);
  }

  function blank(text) {
    body.textContent = "";
    modes.textContent = "";
    body.append(el("p", "viewer-blank", text));
  }

  function render(data) {
    body.textContent = "";
    sourceText = data.text || "";
    drawModes(data);

    // Başlıkta ad + boyut; tam yol üstüne gelince (title) duruyor.
    const size = human(data.size);
    title.textContent = (label(data.path) || "—") + (size ? " · " + size : "");
    title.title = data.path || "";

    // Medya: "İKİLİ DOSYA" yazmak bir görseli göstermemek demekti. Görsel,
    // ses, video ve PDF ham uçtan (`/api/raw`) gerçekten açılıyor.
    const tur = mediaKind(data.path);
    if (tur) { body.append(mediaView(tur, data)); return; }

    if (data.binary) { body.append(unknownBinary(data)); return; }

    if (mode === "live" && isPage(data.path)) {
      body.append(frame(data.text || ""));
      return;
    }

    // .md dosyası biçimlendirilmiş görünmeli; gerisi kod görünümünde.
    if (/\.mdx?$/i.test(data.path)) {
      const holder = el("div", "viewer-source");
      holder.append(Markdown.render(sourceText));
      body.append(holder);
    } else {
      body.append(codeView(sourceText, language(data.path)));
    }
    if (data.truncated) body.append(el("p", "viewer-blank", t("Dosyanın başı gösteriliyor")));
    // Sohbetteki bir referanstan gelindiyse (`loop.py:42`) satır ancak
    // burada, çizim bittikten sonra var: bekleyen istek şimdi karşılanıyor.
    if (pendingLine) gotoLine(pendingLine);
  }

  // --- medya -------------------------------------------------------------
  //
  // Bir PNG açıldığında panel "İKİLİ DOSYA" yazıyordu: ajan bir görsel
  // ürettiğinde ("grafiği çizdim") kullanıcı onu göremiyordu — sohbetin
  // anlatıp gösterememesi, bu panelin var olma sebebinin ta kendisi.
  //
  // Baytlar `/api/raw`dan geliyor (çalışma alanı içi, yol kaçışı korumalı,
  // nosniff). Türü uzantı söylüyor; tanınmayan ikili dosya eski mesajını
  // koruyor ama artık boyutu ve klasörde gösterme eylemiyle.

  const IMAGE = /\.(png|jpe?g|gif|webp|bmp|ico|svg)$/i;
  const AUDIO = /\.(mp3|wav|ogg|m4a|flac)$/i;
  const VIDEO = /\.(mp4|webm|mov)$/i;
  const PDF = /\.pdf$/i;

  function mediaKind(path) {
    const name = String(path || "");
    if (IMAGE.test(name)) return "image";
    if (AUDIO.test(name)) return "audio";
    if (VIDEO.test(name)) return "video";
    if (PDF.test(name)) return "pdf";
    return "";
  }

  const rawUrl = (path) => "/api/raw?path=" + encodeURIComponent(path || "");

  function mediaView(kind, data) {
    const box = el("div", "viewer-media " + kind);
    const url = rawUrl(data.path);

    if (kind === "image") {
      const img = document.createElement("img");
      img.className = "viewer-img";
      img.alt = data.name || data.path || "";
      img.src = url;
      // Piksel ölçüsü başlığa: bir görselde "ne kadar büyük" sorusunun
      // cevabı dosya boyutu değil, kenar uzunlukları.
      img.addEventListener("load", () => {
        const px = img.naturalWidth + "×" + img.naturalHeight;
        const size = human(data.size);
        title.textContent = (label(data.path) || "—") + " · " + px
                          + (size ? " · " + size : "");
      });
      img.addEventListener("error", () => {
        box.textContent = "";
        box.append(el("p", "viewer-blank", t("Görsel açılamadı")));
      });
      // Tıklayınca 1:1 ↔ sığdır. Sığdırılmış bir ekran görüntüsünde yazı
      // okunmuyor; 1:1 hali kutunun içinde kayıyor.
      img.title = t("Tıkla — 1:1 boyut / sığdır");
      img.addEventListener("click", () => {
        box.classList.toggle("full");
        img.title = box.classList.contains("full")
          ? t("Tıkla — sığdır") : t("Tıkla — 1:1 boyut / sığdır");
      });
      box.append(img);
      return box;
    }

    if (kind === "audio" || kind === "video") {
      const player = document.createElement(kind === "audio" ? "audio" : "video");
      player.className = kind === "audio" ? "viewer-audio" : "viewer-video";
      player.src = url;
      player.controls = true;
      player.preload = "metadata";
      box.append(player);
      return box;
    }

    // PDF: gömülü görüntüleyici tarayıcının kendi eklentisi — sayfa DOM'una
    // erişemiyor. Açılmazsa (eklenti kapalı) altındaki düğme kalıyor.
    const holder = document.createElement("iframe");
    holder.className = "viewer-pdf";
    holder.src = url;
    holder.setAttribute("referrerpolicy", "no-referrer");
    box.append(holder);
    box.append(openButton(url, t("Tarayıcıda aç")));
    return box;
  }

  // Gerçekten ikili ve tanınmayan tür: gösterilecek bir şey yok ama ölü bir
  // mesaj da bırakılmıyor — ne kadar yer kapladığı ve nerede olduğu.
  function unknownBinary(data) {
    const box = el("div", "viewer-media unknown");
    box.append(el("p", "viewer-blank", t("İkili dosya")));
    const size = human(data.size);
    if (size) box.append(el("p", "viewer-note", size));

    const acts = el("div", "viewer-acts");
    acts.append(openButton(rawUrl(data.path), t("Tarayıcıda aç")));

    // "Nerede bu şey?": dosyayı gezginde seçili açar. Uç atölyeyle sınırlı
    // (apps.reveal); dışarıdaki bir dosyada sebebini kendisi söylüyor.
    const show = el("button", "viewer-open", t("Klasörde göster"));
    show.type = "button";
    show.addEventListener("click", async () => {
      let answer = null;
      try {
        answer = await (await fetch("/api/apps/reveal", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: data.path }),
        })).json();
      } catch { /* sunucu cevap vermedi */ }
      if (!answer || answer.ok === false) {
        const why = el("p", "viewer-note bad", (answer && answer.error) || t("Açılamadı"));
        acts.after(why);
        setTimeout(() => why.remove(), 6000);
      }
    });
    acts.append(show);
    box.append(acts);
    return box;
  }

  function openButton(url, text) {
    const button = el("button", "viewer-open", text);
    button.type = "button";
    button.addEventListener("click", () => window.open(url, "_blank", "noopener"));
    return button;
  }

  // --- kod görünümü ------------------------------------------------------
  //
  // Satır numaralı, renklendirilmiş, ligatürsüz. Numaralar CSS sayacıyla
  // (::before) çiziliyor: seçilip kopyalanan metne satır numarası
  // karışmıyor. Uzun satır ya kendi içinde kayıyor ya da (sar düğmesi)
  // satır başına kırılıyor; panel dışına asla taşmıyor.

  // Bu kadar satırın üstünde numarasız düz metne düşülüyor: on binlerce
  // satır DOM düğümü kaydırmayı sürüklenemez yapıyor.
  const ROW_CAP = 60000;

  function codeView(source, lang) {
    const box = el("div", "viewer-code" + (wrap ? " wrap" : ""));
    const total = countRows(source);

    if (total > ROW_CAP) {
      const pre = el("pre", "viewer-plain");
      pre.textContent = source;
      box.append(pre);
      return box;
    }

    // Numara sütunu en geniş numaraya göre: 9 ile 999'un hizası aynı.
    box.style.setProperty("--gutter", (String(total).length + 3) + "ch");
    for (const fragment of paintRows(source, lang, total)) {
      const row = el("div", "vl");
      const text = el("span", "vl-tx");
      text.append(fragment);
      row.append(text);
      box.append(row);
    }
    return box;
  }

  // Kuyruktaki boş satır dosyanın son yeni-satırından; numaralamaya değmez.
  function countRows(source) {
    const rows = source.split("\n");
    if (rows.length > 1 && rows[rows.length - 1] === "") rows.pop();
    return Math.max(1, rows.length);
  }

  // Renklendirilmiş kaynağı satır satır parçalara böler. Vurgulayıcı tüm
  // metni tek seferde boyuyor (blok yorum gibi çok satırlı parçalar ancak
  // böyle doğru çıkıyor); satır numarası içinse her satırın kendi kutusu
  // gerekiyor. Boyanmış düğümler yeni-satırlardan bölünür, sınıf korunur.
  // HTML dizesi yok: her parça yine createElement + textContent.
  function paintRows(source, lang, total) {
    const scratch = document.createElement("code");
    if (lang && typeof Syntax !== "undefined" && Syntax.paint) {
      Syntax.paint(scratch, source, lang);
    } else {
      scratch.textContent = source;
    }

    const rows = [document.createDocumentFragment()];
    for (const node of [...scratch.childNodes]) {
      const pieces = String(node.textContent).split("\n");
      for (let i = 0; i < pieces.length; i++) {
        if (i > 0) rows.push(document.createDocumentFragment());
        if (!pieces[i]) continue;
        if (node.nodeType === Node.TEXT_NODE) {
          rows[rows.length - 1].append(document.createTextNode(pieces[i]));
        } else {
          const span = document.createElement("span");
          span.className = node.className;
          span.textContent = pieces[i];
          rows[rows.length - 1].append(span);
        }
      }
    }
    // Sayı gutter'la birebir: eksikse boş satır, fazlaysa (son yeni-satır) at.
    while (rows.length < total) rows.push(document.createDocumentFragment());
    rows.length = total;
    return rows;
  }

  function drawModes(data) {
    modes.textContent = "";

    if (isPage(data.path)) {
      for (const [id, name] of [["source", t("Kaynak")], ["live", t("Sahne")]]) {
        const button = el("button", mode === id ? "on" : "", name);
        button.type = "button";
        button.addEventListener("click", () => { mode = id; render(data); });
        modes.append(button);
      }
    } else {
      mode = "source";
    }

    // Sahne kipinde, medyada ve ikili dosyada kaynak araçlarının işi yok:
    // bir PNG'de "sar" ya da "kopyala" anlamsız.
    if (data.binary || mediaKind(data.path) || (mode === "live" && isPage(data.path))) return;

    if (!/\.mdx?$/i.test(data.path)) {
      const bend = el("button", wrap ? "on" : "", t("Sar"));
      bend.type = "button";
      bend.title = t("Uzun satırları sar / tek satırda kaydır");
      bend.addEventListener("click", () => { wrap = !wrap; render(data); });
      modes.append(bend);
    }

    const copy = el("button", "", t("Kopyala"));
    copy.type = "button";
    copy.title = t("Dosyayı panoya kopyala");
    copy.addEventListener("click", () => copyText(copy));
    modes.append(copy);
  }

  // Panoya kopyalar ve düğmenin üstünde kısa bir onay gösterir: tıklayıp
  // hiçbir şey olmaması "çalıştı mı" belirsizliği bırakıyordu. Asıl yol
  // Clipboard API; gömülü çerçeveler izni reddedebiliyor — o zaman eski
  // usul (geçici textarea + execCommand) devreye giriyor.
  function copyText(button) {
    const done = (msg, ok) => {
      button.textContent = msg;
      button.classList.toggle("ok", ok);
      setTimeout(() => {
        button.textContent = t("Kopyala");
        button.classList.remove("ok");
      }, 1400);
    };
    const fallback = () => {
      const ok = legacyCopy(sourceText);
      done(ok ? t("Kopyalandı ✓") : t("Kopyalanamadı"), ok);
    };
    try {
      navigator.clipboard.writeText(sourceText)
        .then(() => done(t("Kopyalandı ✓"), true), fallback);
    } catch {
      fallback();
    }
  }

  function legacyCopy(text) {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    area.remove();
    return ok;
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

  // Uzantı → vurgulayıcı dili. PHP'nin burada olmaması, PHP dosyalarını
  // renksiz düz metin yapıyordu; harita genişletildi.
  const EXT = { py: "python", js: "javascript", mjs: "javascript", jsx: "javascript",
                ts: "typescript", tsx: "typescript", ps1: "powershell",
                psm1: "powershell", sh: "bash", bash: "bash", bat: "bash",
                json: "json", jsonl: "json", css: "css", scss: "css", less: "css",
                html: "html", htm: "html", xml: "xml", svg: "svg",
                sql: "sql", yml: "yaml", yaml: "yaml", toml: "toml", ini: "toml",
                cfg: "toml", php: "php", phtml: "php", c: "c", h: "c",
                cpp: "cpp", hpp: "cpp", cc: "cpp", cs: "cs", go: "go",
                rs: "rust", java: "java", rb: "ruby", lua: "lua",
                kt: "kotlin", swift: "swift" };

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

  return { present, page, showing, watch, refresh, show, open, close, toggle };
})();
