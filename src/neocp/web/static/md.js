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

    while (i < lines.length) {
      const line = lines[i];

      const fence = line.match(FENCE);
      if (fence) { i = code(out, lines, i, fence[1]); continue; }

      if (!line.trim()) { i++; continue; }

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
    block.append(body);
    out.append(block);

    return j < lines.length ? j + 1 : j;
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

  // --- satır içi -------------------------------------------------------

  function inline(parent, text) {
    let rest = String(text ?? "");

    while (rest) {
      const hit = rest.match(INLINE);
      if (!hit) { signed(parent, rest); return; }

      if (hit.index > 0) signed(parent, rest.slice(0, hit.index));

      if (hit[1]) {
        const node = el("code", "md-inline");
        node.textContent = hit[2].trim();
        parent.append(node);
      } else if (hit[4] !== undefined) {
        // Bağlantı metin olarak gösteriliyor, tıklanabilir değil: modelin
        // ürettiği bir adrese tıklamayı tek tuşluk yapmak istemiyoruz.
        const node = el("span", "md-link");
        node.textContent = hit[3] || hit[4];
        node.title = hit[4];
        parent.append(node);
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
  const SIGNED = /([+−-])\s?(\d[\d.,\s]*)\s?(%|puan|bp)?/g;

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
