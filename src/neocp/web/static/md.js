// Modelin yazdığı metni biçimlendirir.
//
// Neden elle yazıldı: hazır bir kütüphane (marked, markdown-it) HTML dizesi
// üretiyor ve onu ham biçimde sayfaya basmak gerekiyor. Buraya akan metni model
// yazıyor — yani güvenilmeyen bir kaynak. Bu dosya HTML dizesi hiç üretmiyor,
// doğrudan DOM düğümü kuruyor: `textContent` ile giren bir şey hiçbir koşulda
// etiket olarak yorumlanmıyor.
//
// İkinci sebep akış. Cevap harf harf geliyor ve her parçada yeniden
// çiziliyor; yani kapanmamış bir kod çiti normal bir durum, hata değil.
// Kapanmamış çit "yazılmakta olan kod bloğu" gibi gösteriliyor.

const Markdown = (() => {
  // Çeviri köprüsü: dil.js normalde önce yüklenir ama bu dosya tek başına
  // (önizleme, eski önbellek) da çalışabilmeli — o durumda Türkçe kalır.
  const ceviri = (s) => (typeof t === "function" ? t(s) : s);
  if (typeof Dil !== "undefined") {
    Dil.ekle({
      "Kopyala": "Copy", "Kopyalandı ✓": "Copied ✓", "Kopyalanamadı": "Copy failed",
      "tümünü göster": "show all", "kısalt": "collapse",
      " satır": " lines",
      "Tıkla — görüntüleyicide aç": "Click — open in the viewer",
      "Tıkla — tarayıcıda aç": "Click — open in the browser",
      "Kaynaklar": "Sources",
    });
  }

  const FENCE = /^\s*```(\S*)\s*$/;
  const HEADING = /^(#{1,6})\s+(.*)$/;
  const BULLET = /^\s*[-*+]\s+(.*)$/;
  const NUMBER = /^\s*(\d+)[.)]\s+(.*)$/;
  const QUOTE = /^\s*>\s?(.*)$/;
  const RULE = /^\s*([-*_])\s*(\1\s*){2,}$/;
  // Tablo: en az bir boru işareti taşıyan satır, ardından hizalama satırı.
  const ROW = /^\s*\|(.+)\|\s*$/;
  const ALIGN = /^\s*\|?[\s:|-]+\|[\s:|-]*$/;
  // Onay kutulu madde. Ajan plan çıkardığında en çok bunu kullanıyor.
  const TASK = /^\s*[-*+]\s+\[([ xX])\]\s+(.*)$/;

  // Satır içi: kod > bağlantı > kalın > eğik. Sıra önemli — kodun içindeki
  // yıldız kalın yapmamalı, o yüzden kod önce yakalanıyor.
  const INLINE = /(`+)([\s\S]*?)\1|\[([^\]]*)\]\(([^)\s]+)[^)]*\)|(\*\*|__)([\s\S]+?)\5|(~~)([\s\S]+?)\7|(\*|_)([^\s*_][\s\S]*?)\9/;

  const el = (tag, cls) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    return node;
  };

  function render(text) {
    const out = document.createDocumentFragment();
    const lines = String(text || "").split("\n");
    let i = 0;

    // Atıf tanımları önce toplanıyor: metin içindeki `[1]` işaretinin nereye
    // gittiği ancak tanım okununca biliniyor ve tanımlar cevabın SONUNDA
    // duruyor. Tek geçişte çizseydik ilk `[1]` düz metin kalırdı.
    sources = collectSources(lines);

    while (i < lines.length) {
      const line = lines[i];

      const fence = line.match(FENCE);
      if (fence) { i = code(out, lines, i, fence[1]); continue; }

      if (!line.trim()) { i++; continue; }

      // Atıf tanımı satırı ("[1] https://…") kaynak listesine gitti; burada
      // ham URL olarak tekrar akmasın.
      if (SOURCE_DEF.test(line)) { i++; continue; }

      if (RULE.test(line)) { out.append(el("hr", "md-rule")); i++; continue; }

      const head = line.match(HEADING);
      if (head) {
        const node = el("div", "md-h md-h" + head[1].length);
        inline(node, head[2]);
        out.append(node);
        i++;
        continue;
      }

      if (QUOTE.test(line)) { i = quote(out, lines, i); continue; }
      // Tablo listeden önce denenmeli: hizalama satırı ("|---|---|") aynı
      // zamanda geçerli bir yatay çizgi gibi görünüyor.
      if (ROW.test(line) && ALIGN.test(lines[i + 1] || "")) { i = table(out, lines, i); continue; }
      if (BULLET.test(line) || NUMBER.test(line)) { i = list(out, lines, i); continue; }

      i = paragraph(out, lines, i);
    }

    // Numaralı atıf kullanıldıysa altta küçük bir kaynak listesi.
    if (sources.size) out.append(sourceList());

    return out;
  }

  // --- bloklar ---------------------------------------------------------

  function code(out, lines, i, lang) {
    const block = el("pre", "md-code");
    if (lang) {
      const tag = el("span", "md-lang");
      tag.textContent = lang;
      block.append(tag);
    }

    const body = el("code");
    const rows = [];
    let j = i + 1;
    // Kapanış çiti yoksa dosyanın sonuna kadar: akış sürerken normal hal.
    while (j < lines.length && !FENCE.test(lines[j])) rows.push(lines[j++]);
    const source = rows.join("\n");
    // Dil biliniyorsa sözdizimi renklendirmesi; yoksa düz metin. Vurgulayıcı
    // DOM kuruyor (HTML dizesi değil), yani gömülü bir <script> renklenir
    // ama çalışmaz. Yüklenmemişse (eski önbellek) düz metne düşülüyor.
    if (lang && typeof Syntax !== "undefined" && Syntax.paint) {
      Syntax.paint(body, source, lang);
    } else {
      body.textContent = source;
    }
    // Kopyala: sohbetteki kod bloğu da tek tıkla panoya. Akış sürerken blok
    // her karede yeniden kurulduğu için düğme durumsuz — sorun değil, onay
    // yalnızca son (bitmiş) çizimde okunuyor.
    block.append(copyButton(source));
    block.append(body);
    // Uzun blok katlanıyor: 300 satırlık bir dosya dökümü cevabın gerisini
    // ekrandan atıyordu. Kırpma YOK — metnin tamamı DOM'da, yalnızca kutu
    // alçak; yani seçim ve kopyalama tam içerik üzerinde çalışıyor.
    fold(block, body, rows.length);
    out.append(block);

    return j < lines.length ? j + 1 : j;
  }

  // Bundan uzun blok/liste varsayılan katlı gelir.
  const FOLD_ROWS = 40;

  // Katlama: kutu alçalır ve altına "… N satır · tümünü göster" düğmesi
  // düşer (adım kartlarındaki ⤢ ile aynı dil). Açılınca "kısalt"a döner.
  //
  // Neden max-height ile: metni gerçekten kesmek kopyalamayı da keserdi.
  // Burada içerik eksiksiz duruyor, yalnız görünen yüksekliği sınırlı.
  function fold(block, body, rows) {
    if (rows <= FOLD_ROWS) return;
    block.classList.add("md-folded");

    const button = el("button", "md-more");
    button.type = "button";
    const kapali = "… " + rows + ceviri(" satır") + " · " + ceviri("tümünü göster");
    button.textContent = kapali;
    button.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const acik = block.classList.toggle("md-open");
      button.textContent = acik ? ceviri("kısalt") : kapali;
    });
    block.append(button);
    return body;
  }

  // Kod bloğunun köşesindeki kopyalama düğmesi. Tıklayınca kısa bir onay
  // gösteriyor: hiçbir şey olmaması "çalıştı mı" belirsizliği bırakıyordu.
  function copyButton(source) {
    const button = el("button", "md-copy");
    button.type = "button";
    button.textContent = ceviri("Kopyala");
    button.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const done = (msg, ok) => {
        button.textContent = msg;
        button.classList.toggle("ok", ok);
        setTimeout(() => {
          button.textContent = ceviri("Kopyala");
          button.classList.remove("ok");
        }, 1400);
      };
      // Gömülü çerçeveler Clipboard API iznini reddedebiliyor; eski usul
      // (geçici textarea + execCommand) yedek yol.
      const fallback = () => {
        const ok = legacyCopy(source);
        done(ok ? ceviri("Kopyalandı ✓") : ceviri("Kopyalanamadı"), ok);
      };
      try {
        navigator.clipboard.writeText(source)
          .then(() => done(ceviri("Kopyalandı ✓"), true), fallback);
      } catch {
        fallback();
      }
    });
    return button;
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

  // Tablo, modelin veri gösterirken ilk uzandığı biçim. Düz metin olarak
  // akıtmak okunmuyordu: sütunlar kayıyor, uzun hücre satırı taşırıyordu.
  function table(out, lines, i) {
    const wrap = el("div", "md-table-wrap");
    const block = el("table", "md-table");

    const head = el("thead");
    head.append(row(cells(lines[i]), "th"));
    block.append(head);

    const body = el("tbody");
    let j = i + 2;
    // Akış sürerken son satır yarım gelebiliyor; boru işareti taşıdığı
    // sürece satır sayılıyor, kapanışı beklenmiyor.
    while (j < lines.length && lines[j].includes("|") && lines[j].trim()) {
      body.append(row(cells(lines[j++]), "td"));
    }
    block.append(body);

    wrap.append(block);
    // Yüz satırlık bir tablo cevabın gerisini ekrandan atıyordu; başlık
    // satırı ve ilk satırlar açıkta, gerisi tek tıkla.
    fold(wrap, block, body.childElementCount);
    out.append(wrap);
    return j;
  }

  const cells = (line) =>
    line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((c) => c.trim());

  function row(values, tag) {
    const node = el("tr");
    for (const value of values) {
      const cell = el(tag);
      inline(cell, value);
      node.append(cell);
    }
    return node;
  }

  function quote(out, lines, i) {
    const block = el("div", "md-quote");
    const rows = [];
    let j = i;
    while (j < lines.length && QUOTE.test(lines[j])) rows.push(lines[j++].match(QUOTE)[1]);
    inline(block, rows.join(" "));
    out.append(block);
    return j;
  }

  function list(out, lines, i) {
    const ordered = NUMBER.test(lines[i]);
    const block = el(ordered ? "ol" : "ul", "md-list");
    let j = i;

    while (j < lines.length) {
      const task = lines[j].match(TASK);
      const match = task || lines[j].match(ordered ? NUMBER : BULLET);
      if (!match) break;

      const item = el("li");
      if (task) {
        // Onay kutusu metin olarak çiziliyor, gerçek bir input değil:
        // tıklanabilir olsa kullanıcı işaretler ve hiçbir yere yazılmaz.
        item.className = "md-task" + (task[1].toLowerCase() === "x" ? " done" : "");
        inline(item, task[2]);
      } else {
        inline(item, ordered ? match[2] : match[1]);
      }
      block.append(item);
      j++;
    }

    // Uzun liste de katlanıyor. Liste kendi düğmesini içine alamaz (bir
    // <ul>'un çocuğu <li> olmalı), o yüzden bir sarmalayıcıya giriyor.
    if (block.childElementCount > FOLD_ROWS) {
      const wrap = el("div", "md-list-wrap");
      wrap.append(block);
      fold(wrap, block, block.childElementCount);
      out.append(wrap);
      return j;
    }

    out.append(block);
    return j;
  }

  function paragraph(out, lines, i) {
    const rows = [];
    let j = i;
    while (
      j < lines.length &&
      lines[j].trim() &&
      !FENCE.test(lines[j]) &&
      !HEADING.test(lines[j]) &&
      !BULLET.test(lines[j]) &&
      !NUMBER.test(lines[j]) &&
      !QUOTE.test(lines[j]) &&
      !(ROW.test(lines[j]) && ALIGN.test(lines[j + 1] || ""))
    ) rows.push(lines[j++]);

    const node = el("p", "md-p");
    inline(node, rows.join("\n"));
    out.append(node);
    return j;
  }

  // --- kaynaklar -------------------------------------------------------
  //
  // `search`/`fetch` sonrası cevapta çıplak URL akıyordu:
  // "https://www.example.com/2026/08/uzun-slug-burada?utm=..." — göz bunu
  // okumuyor, yalnızca satırı kirletiyor. Kaynak okunur bir şeye dönüşüyor:
  // başlık (varsa) + alan adı. Tıklanınca tarayıcıda açılıyor.
  //
  // Not: bağlantılar önce BİLEREK tıklanamazdı ("modelin ürettiği bir adrese
  // tıklamayı tek tuşluk yapmak istemiyoruz"). O kaygı adresin ne olduğunu
  // GÖRMEDEN tıklamaktı; alan adı artık satırın üstünde yazıyor ve tam adres
  // ipucunda duruyor — nereye gidildiği tıklamadan önce okunuyor.

  const SOURCE_DEF = /^\s*\[(\d+)\]:?\s+(https?:\/\/\S+)\s*(.*)$/;
  // Çıplak URL. Sondaki noktalama cümlenin kendisi olabilir; ayıklanıyor.
  const BARE_URL = /https?:\/\/[^\s<>"'`]+/;

  let sources = new Map();   // numara → { url, title }

  function collectSources(lines) {
    const found = new Map();
    for (const line of lines) {
      const hit = line.match(SOURCE_DEF);
      if (hit) found.set(hit[1], { url: trimUrl(hit[2]), title: hit[3].trim() });
    }
    return found;
  }

  // Sondaki cümle noktalaması adresin parçası değil: "…/sayfa." linki
  // kırıyordu. Kapanan parantez dengeliyse korunuyor (wikipedia kalıbı).
  function trimUrl(url) {
    let out = String(url);
    while (/[.,;:!?]$/.test(out)) out = out.slice(0, -1);
    if (out.endsWith(")") && (out.match(/\(/g) || []).length < (out.match(/\)/g) || []).length) {
      out = out.slice(0, -1);
    }
    return out;
  }

  // "https://www.example.com/a/b" → "example.com". Alan adı kaynağın
  // kimliği: göz önce oraya bakıyor, "hangi siteden" sorusu bir bakışta.
  function domainOf(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch {
      return url.replace(/^https?:\/\//, "").split("/")[0] || url;
    }
  }

  // Başlık verilmediyse adresin son parçasından okunur bir ad çıkarılıyor:
  // "/2026/08/tcmb-faiz-karari" → "tcmb faiz karari". Hiçbir şey çıkmazsa
  // yalnız alan adı kalıyor — uydurma başlık yazmaktansa az söylemek iyi.
  function slugTitle(url) {
    let parts = [];
    try {
      parts = new URL(url).pathname.split("/").filter(Boolean);
    } catch { return ""; }
    const last = parts.pop() || "";
    const stem = last.replace(/\.\w{1,5}$/, "").replace(/[-_+]+/g, " ").trim();
    if (!stem || /^\d+$/.test(stem) || stem.length < 3) return "";
    return stem.length > 70 ? stem.slice(0, 70) + "…" : stem;
  }

  // Okunur kaynak satırı: başlık + alan adı, tıklanınca tarayıcıda açılır.
  function sourceChip(url, title) {
    const chip = el("span", "md-source");
    const name = (title || "").trim() || slugTitle(url);
    if (name) chip.append(el2("span", "md-source-title", name));
    chip.append(el2("span", "md-source-host", domainOf(url)));
    chip.title = ceviri("Tıkla — tarayıcıda aç") + "\n" + url;
    chip.tabIndex = 0;
    const git = () => window.open(url, "_blank", "noopener,noreferrer");
    chip.addEventListener("click", git);
    chip.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); git(); }
    });
    return chip;
  }

  const el2 = (tag, cls, text) => {
    const node = el(tag, cls);
    if (text !== undefined) node.textContent = text;
    return node;
  };

  // Metindeki `[1]` işareti: tanımlıysa tıklanabilir üst-simge.
  function citation(no) {
    const source = sources.get(no);
    const mark = el("sup", "md-cite");
    mark.textContent = "[" + no + "]";
    mark.title = (source.title ? source.title + "\n" : "") + source.url;
    mark.tabIndex = 0;
    const git = () => window.open(source.url, "_blank", "noopener,noreferrer");
    mark.addEventListener("click", git);
    mark.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); git(); }
    });
    return mark;
  }

  // Alttaki kaynak listesi. Aynı adres birden çok numarayla geçtiyse tek
  // satır: "[1,3] başlık · example.com" — aynı kaynağı iki kez yazmak
  // listeyi uzatıp okunmaz yapıyordu.
  function sourceList() {
    const box = el("div", "md-sources");
    box.append(el2("div", "md-sources-head", ceviri("Kaynaklar")));

    const byUrl = new Map();
    for (const [no, source] of sources) {
      const kayit = byUrl.get(source.url)
                 || { numbers: [], title: source.title, url: source.url };
      kayit.numbers.push(no);
      if (!kayit.title && source.title) kayit.title = source.title;
      byUrl.set(source.url, kayit);
    }

    for (const kayit of byUrl.values()) {
      const row = el("div", "md-source-row");
      row.append(el2("span", "md-source-no", "[" + kayit.numbers.join(",") + "]"));
      row.append(sourceChip(kayit.url, kayit.title));
      box.append(row);
    }
    return box;
  }

  // --- dosya referansları ----------------------------------------------
  //
  // Cevaptaki `src/neocp/loop.py:42` düz metin kalıyordu: kullanıcı yolu
  // okuyup paneli elle açıp satırı elle arıyordu. Artık bağ — tıklayınca
  // görüntüleyici o dosyayı, satır verilmişse O SATIRA kaydırılmış açıyor.
  //
  // Asıl zorluk yanlış pozitif: cümlenin içindeki her `bir:iki` bağ olamaz.
  // Kural dar tutuldu — tanınan bir uzantı (ya da açık bir klasör yolu)
  // şart, `Node.js` gibi ürün adları eleniyor ve URL'in içi hiç taranmıyor.

  const EXTS = (
    "py js mjs cjs jsx ts tsx json jsonl yml yaml toml ini cfg conf env " +
    "md mdx txt csv tsv sql sh bash ps1 psm1 bat cmd " +
    "html htm css scss less php phtml rb go rs java kt swift lua vue svelte " +
    "c h cpp hpp cc cs xml svg " +
    "png jpg jpeg gif webp pdf log"
  ).split(" ");

  // Yol + isteğe bağlı `:satır` (ve `:sütun`). Sürücü harfi, `./`, `~/` ve
  // iki ayraç da tanınıyor: model Windows yolu da yazıyor.
  const FILE_REF = new RegExp(
    "(?:[A-Za-z]:[\\\\/])?(?:\\.{1,2}[\\\\/]|~[\\\\/])?" +
    "(?:[\\w.@+-]+[\\\\/])*" +
    "[\\w.@+-]+\\.(?:" + EXTS.join("|") + ")" +
    "(?::(\\d+))?(?::\\d+)?",
    "i"
  );

  // Klasör yolu: sonu ayraçla biten, en az iki parçalı ("atolye/borsa-ara/").
  const DIR_REF = /(?:[\w.@+-]+[\\/]){2,}/;

  // Alan adıyla başlayan bir şey dosya değil, adrestir: "example.com/a.php"
  // bağ olmamalı (URL yakalayıcısının işi).
  const HOSTISH = /^[\w-]+\.(com|net|org|io|dev|co|app|ai|gov|edu|info|tr|de|uk|fr|nl)([\\/:]|$)/i;

  function fileRef(text) {
    const hit = text.match(FILE_REF) || text.match(DIR_REF);
    if (!hit) return null;

    const raw = hit[0];
    const path = raw.replace(/:\d+(?::\d+)?$/, "");
    if (HOSTISH.test(path)) return null;

    const sep = /[\\/]/.test(path);
    const stem = path.split(/[\\/]/).pop();
    // "Node.js", "Vue.js", "Next.js": ürün adı, dosya değil. Ayraç ya da
    // satır numarası varsa gerçekten dosyadır; yoksa büyük harfle başlayan
    // tek parçaya dokunulmuyor.
    if (!sep && !hit[1] && /^[A-Z]/.test(stem)) return null;
    // Ayraçsız ve numarasız tek kelime çok zayıf bir işaret değil ama
    // "1.5" gibi şeyler zaten uzantı listesine takılmıyor.
    return { index: hit.index, raw, path, line: Number(hit[1] || 0) };
  }

  // Tıklanınca görüntüleyiciyi açan dosya bağı.
  function fileChip(path, line, label) {
    const chip = el("span", "md-file");
    chip.textContent = label;
    chip.title = ceviri("Tıkla — görüntüleyicide aç") + "\n" + path
               + (line ? ":" + line : "");
    chip.tabIndex = 0;
    const ac = () => {
      if (typeof Viewer !== "undefined" && Viewer.open) Viewer.open(path, line);
    };
    chip.addEventListener("click", ac);
    chip.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); ac(); }
    });
    return chip;
  }

  // Düz metin parçası: önce adres, sonra dosya yolu, sonra atıf, en sonda
  // işaretli sayı. Sıra konuma göre — hangisi önce geliyorsa o kazanıyor,
  // böylece bir URL'in içindeki ".php" dosya sanılmıyor.
  function plain(parent, text) {
    let rest = String(text ?? "");

    while (rest) {
      const url = rest.match(BARE_URL);
      const file = fileRef(rest);
      const cite = citeHit(rest);

      const adaylar = [
        url && { at: url.index, kind: "url", hit: url },
        file && { at: file.index, kind: "file", hit: file },
        cite && { at: cite.index, kind: "cite", hit: cite },
      ].filter(Boolean).sort((a, b) => a.at - b.at);

      if (!adaylar.length) { signed(parent, rest); return; }

      const first = adaylar[0];
      if (first.at > 0) signed(parent, rest.slice(0, first.at));

      let uzunluk;
      if (first.kind === "url") {
        const adres = trimUrl(first.hit[0]);
        parent.append(sourceChip(adres, ""));
        uzunluk = adres.length;
      } else if (first.kind === "file") {
        parent.append(fileChip(first.hit.path, first.hit.line, first.hit.raw));
        uzunluk = first.hit.raw.length;
      } else {
        parent.append(citation(first.hit[1]));
        uzunluk = first.hit[0].length;
      }
      rest = rest.slice(first.at + uzunluk);
    }
  }

  // Yalnızca TANIMLI atıflar işaretleniyor: tanımsız `[2]` düz metin kalır —
  // olmayan bir kaynağa götüren bir bağ, bağ değildir.
  function citeHit(text) {
    const re = /\[(\d+)\]/g;
    let hit;
    while ((hit = re.exec(text))) {
      if (sources.has(hit[1])) return hit;
    }
    return null;
  }

  // --- satır içi -------------------------------------------------------

  function inline(parent, text) {
    let rest = String(text ?? "");

    while (rest) {
      const hit = rest.match(INLINE);
      if (!hit) { plain(parent, rest); return; }

      if (hit.index > 0) plain(parent, rest.slice(0, hit.index));

      if (hit[1]) {
        const icerik = hit[2].trim();
        const node = el("code", "md-inline");
        node.textContent = icerik;
        // Model dosya yolunu en çok ters tırnak içinde yazıyor. İçerik
        // TAMAMEN bir yolsa kod görünümü kalıyor ama tıklanabilir oluyor —
        // kodun içinde bağ aramıyoruz, kodun KENDİSİ bir yol.
        const ref = fileRef(icerik);
        if (ref && ref.index === 0 && ref.raw === icerik) {
          node.classList.add("md-file-code");
          node.title = ceviri("Tıkla — görüntüleyicide aç") + "\n" + icerik;
          node.tabIndex = 0;
          const ac = () => {
            if (typeof Viewer !== "undefined" && Viewer.open) Viewer.open(ref.path, ref.line);
          };
          node.addEventListener("click", ac);
          node.addEventListener("keydown", (ev) => {
            if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); ac(); }
          });
        }
        parent.append(node);
      } else if (hit[4] !== undefined) {
        // Adres bağlantısı okunur bir kaynağa dönüşüyor (başlık + alan adı);
        // yol bağlantısı görüntüleyiciyi açıyor. Ötekiler eskisi gibi düz
        // metin: modelin ürettiği tanımadık bir şeye tıklatmıyoruz.
        const hedef = hit[4];
        const metin = hit[3] || hedef;
        if (/^https?:\/\//i.test(hedef)) {
          parent.append(sourceChip(trimUrl(hedef), hit[3] || ""));
        } else {
          const ref = fileRef(hedef);
          if (ref && ref.raw === hedef) parent.append(fileChip(ref.path, ref.line, metin));
          else {
            const node = el("span", "md-link");
            node.textContent = metin;
            node.title = hedef;
            parent.append(node);
          }
        }
      } else if (hit[5]) {
        const node = el("b");
        inline(node, hit[6]);
        parent.append(node);
      } else if (hit[7]) {
        const node = el("s");
        inline(node, hit[8]);
        parent.append(node);
      } else {
        const node = el("i");
        inline(node, hit[10]);
        parent.append(node);
      }

      rest = rest.slice(hit.index + hit[0].length);
    }
  }

  // İşaretli sayılar renklenir: `+0,18%` yeşil, `-41,95%` kırmızı.
  //
  // Bir tabloda otuz sayı varken hangisinin arttığını okumak için tek tek
  // işarete bakmak gerekiyordu; renk bunu bir bakışta veriyor. Yalnızca
  // **açık işaretli** olanlar renkleniyor — işaretsiz bir sayı fiyat da
  // olabilir, adet de.
  const SIGNED = /([+−-])\s?(\d[\d.,\s]*)\s?(%|puan\b|bp\b)?/g;

  function signed(parent, text) {
    let at = 0;
    for (const hit of text.matchAll(SIGNED)) {
      // Sayının solunda harf ya da rakam varsa bu bir işaret değil, tire:
      // "qwen3-9b" ya da "2026-08-23" renklenmemeli.
      const before = text[hit.index - 1] || " ";
      if (/[\w\d]/.test(before)) continue;
      // Yüzde ya da birim yoksa ve artı işareti de yoksa muhtemelen tarih
      // ya da eksi imli bir değer değil; dokunma.
      if (!hit[3] && hit[1] !== "+") continue;

      if (hit.index > at) parent.append(document.createTextNode(text.slice(at, hit.index)));
      const node = el("span", hit[1] === "+" ? "md-up" : "md-down");
      node.textContent = hit[0];
      parent.append(node);
      at = hit.index + hit[0].length;
    }
    if (at < text.length) parent.append(document.createTextNode(text.slice(at)));
  }

  // Bazı modeller (qwen, deepseek yerel biçimleri) araç çağrısını API yerine
  // DÜZ METİN olarak yazıyor: "<tool_call><function=shell>…</tool_call>".
  // Bu iç mekanik; sohbette ham XML olarak akması "konuşma tarafı bozuk"
  // görüntüsünün ta kendisi. Cevabın içinden ayıklanıp kısa bir nota
  // indirgeniyor — model biçimi düzelttiğinde hiçbir şey değişmiyor.
  const TOOL_LEAK = /<tool_call>[\s\S]*?(?:<\/tool_call>|$)/g;

  function sanitize(text) {
    return String(text || "").replace(TOOL_LEAK, "\n`⚙ araç çağrısı — model biçim hatası, ham hali gizlendi`\n");
  }

  // Metni bir kabın içine çizer; kabın önceki içeriği gider.
  function into(node, text) {
    node.textContent = "";
    node.append(render(sanitize(text)));
    return node;
  }

  return { render, into };
})();
