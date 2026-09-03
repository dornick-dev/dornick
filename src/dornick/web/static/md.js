// Formats the text the model writes.
//
// Why hand-written: an off-the-shelf library (marked, markdown-it) produces
// an HTML string that must be injected raw into the page. The text flowing in
// here is written by the model — an untrusted source. This file never builds
// an HTML string, it constructs DOM nodes directly: anything entering via
// `textContent` is never interpreted as markup under any circumstances.
//
// The second reason is streaming. The answer arrives letter by letter and is
// redrawn on every chunk; an unclosed code fence is therefore a normal state,
// not an error. An unclosed fence is shown as "a code block being written".

const Markdown = (() => {
  // Translation bridge: dil.js normally loads first, but this file must also
  // work standalone (preview, stale cache) — Turkish remains in that case.
  const translate = (s) => (typeof t === "function" ? t(s) : s);
  if (typeof Dil !== "undefined") {
    Dil.ekle({
      "Kopyala": "Copy", "Kopyalandı ✓": "Copied ✓", "Kopyalanamadı": "Copy failed",
      "tümünü göster": "show all", "kısalt": "collapse",
      " satır": " lines",
      "Tıkla — görüntüleyicide aç": "Click — open in the viewer",
      "Tıkla — tarayıcıda aç": "Click — open in the browser",
      "Tıkla — indir": "Click — download",
      "Kaynaklar": "Sources",
    });
  }

  const FENCE = /^\s*```(\S*)\s*$/;
  const HEADING = /^(#{1,6})\s+(.*)$/;
  const BULLET = /^\s*[-*+]\s+(.*)$/;
  const NUMBER = /^\s*(\d+)[.)]\s+(.*)$/;
  const QUOTE = /^\s*>\s?(.*)$/;
  const RULE = /^\s*([-*_])\s*(\1\s*){2,}$/;
  // Table: a line carrying at least one pipe, followed by the alignment line.
  const ROW = /^\s*\|(.+)\|\s*$/;
  const ALIGN = /^\s*\|?[\s:|-]+\|[\s:|-]*$/;
  // Checkbox list item. What the agent reaches for most when writing a plan.
  const TASK = /^\s*[-*+]\s+\[([ xX])\]\s+(.*)$/;

  // Inline: code > link > bold > italic. Order matters — an asterisk inside
  // code must not bold, so code is captured first.
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

    // Citation definitions are collected first: where an in-text `[1]` mark
    // points is only known once its definition is read, and definitions sit
    // at the END of the answer. Drawing in a single pass would leave the
    // first `[1]` as plain text.
    sources = collectSources(lines);

    while (i < lines.length) {
      const line = lines[i];

      const fence = line.match(FENCE);
      if (fence) { i = code(out, lines, i, fence[1]); continue; }

      if (!line.trim()) { i++; continue; }

      // The citation definition line ("[1] https://…") went to the source
      // list; do not let it flow through here again as a raw URL.
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
      // The table must be tried before the list: the alignment line
      // ("|---|---|") also looks like a valid horizontal rule.
      if (ROW.test(line) && ALIGN.test(lines[i + 1] || "")) { i = table(out, lines, i); continue; }
      if (BULLET.test(line) || NUMBER.test(line)) { i = list(out, lines, i); continue; }

      i = paragraph(out, lines, i);
    }

    // If numbered citations were used, a small source list at the bottom.
    if (sources.size) out.append(sourceList());

    return out;
  }

  // --- blocks ----------------------------------------------------------

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
    // No closing fence: run to the end — the normal state mid-stream.
    while (j < lines.length && !FENCE.test(lines[j])) rows.push(lines[j++]);
    const source = rows.join("\n");
    // Syntax colouring when the language is known; plain text otherwise. The
    // highlighter builds DOM (not an HTML string), so an embedded <script>
    // gets coloured but never runs. If not loaded (stale cache), fall back
    // to plain text.
    if (lang && typeof Syntax !== "undefined" && Syntax.paint) {
      Syntax.paint(body, source, lang);
    } else {
      body.textContent = source;
    }
    // Copy: a code block in the chat also goes to the clipboard in one
    // click. While streaming, the block is rebuilt every frame so the button
    // is stateless — fine, the confirmation is only read on the final
    // (finished) render.
    block.append(copyButton(source));
    block.append(body);
    // Long blocks fold: a 300-line file dump pushed the rest of the answer
    // off screen. NO trimming — the whole text stays in the DOM, only the
    // box is short; selection and copying work on the full content.
    fold(block, body, rows.length);
    out.append(block);

    return j < lines.length ? j + 1 : j;
  }

  // Blocks/lists longer than this come folded by default.
  const FOLD_ROWS = 40;

  // Folding: the box gets short and a "… N lines · show all" button drops
  // below it (same language as the ⤢ on step cards). Once open it flips to
  // "collapse".
  //
  // Why via max-height: truly cutting the text would cut copying too. Here
  // the content stays complete, only the visible height is limited.
  function fold(block, body, rows) {
    if (rows <= FOLD_ROWS) return;
    block.classList.add("md-folded");

    const button = el("button", "md-more");
    button.type = "button";
    const closedLabel = "… " + rows + translate(" satır") + " · " + translate("tümünü göster");
    button.textContent = closedLabel;
    button.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const opened = block.classList.toggle("md-open");
      button.textContent = opened ? translate("kısalt") : closedLabel;
    });
    block.append(button);
    return body;
  }

  // The copy button in the code block's corner. Shows a brief confirmation
  // on click: nothing happening left a "did it work" ambiguity.
  function copyButton(source) {
    const button = el("button", "md-copy");
    button.type = "button";
    button.textContent = translate("Kopyala");
    button.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const done = (msg, ok) => {
        button.textContent = msg;
        button.classList.toggle("ok", ok);
        setTimeout(() => {
          button.textContent = translate("Kopyala");
          button.classList.remove("ok");
        }, 1400);
      };
      // Embedded frames may deny Clipboard API permission; the old way
      // (temporary textarea + execCommand) is the fallback.
      const fallback = () => {
        const ok = legacyCopy(source);
        done(ok ? translate("Kopyalandı ✓") : translate("Kopyalanamadı"), ok);
      };
      try {
        navigator.clipboard.writeText(source)
          .then(() => done(translate("Kopyalandı ✓"), true), fallback);
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

  // The table is the first format the model reaches for when showing data.
  // Streaming it as plain text was unreadable: columns drifted, a long cell
  // overflowed the row.
  function table(out, lines, i) {
    const wrap = el("div", "md-table-wrap");
    const block = el("table", "md-table");

    const head = el("thead");
    head.append(row(cells(lines[i]), "th"));
    block.append(head);

    const body = el("tbody");
    let j = i + 2;
    // Mid-stream the last row can arrive half-finished; as long as it
    // carries a pipe it counts as a row, no closing is awaited.
    while (j < lines.length && lines[j].includes("|") && lines[j].trim()) {
      body.append(row(cells(lines[j++]), "td"));
    }
    block.append(body);

    wrap.append(block);
    // A hundred-row table pushed the rest of the answer off screen; the
    // header row and the first rows stay visible, the rest is one click away.
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
        // The checkbox is drawn as text, not a real input: were it
        // clickable, the user would tick it and it would be written nowhere.
        item.className = "md-task" + (task[1].toLowerCase() === "x" ? " done" : "");
        inline(item, task[2]);
      } else {
        inline(item, ordered ? match[2] : match[1]);
      }
      block.append(item);
      j++;
    }

    // Long lists fold too. A list cannot hold its own button (a child of a
    // <ul> must be an <li>), so it goes into a wrapper.
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

  // --- sources ---------------------------------------------------------
  //
  // After `search`/`fetch`, bare URLs flowed through the answer:
  // "https://www.example.com/2026/08/long-slug-here?utm=..." — the eye does
  // not read that, it only dirties the line. A source becomes something
  // readable: title (if any) + domain. Clicking opens it in the browser.
  //
  // Note: links used to be DELIBERATELY unclickable ("we do not want
  // clicking a model-produced address to be one keystroke"). That worry was
  // about clicking WITHOUT SEEING the address; the domain is now written on
  // the line and the full address sits in the tooltip — where you are going
  // is read before the click.

  const SOURCE_DEF = /^\s*\[(\d+)\]:?\s+(https?:\/\/\S+)\s*(.*)$/;
  // Bare URL. Trailing punctuation may belong to the sentence; stripped.
  const BARE_URL = /https?:\/\/[^\s<>"'`]+/;

  let sources = new Map();   // number → { url, title }

  function collectSources(lines) {
    const found = new Map();
    for (const line of lines) {
      const hit = line.match(SOURCE_DEF);
      if (hit) found.set(hit[1], { url: trimUrl(hit[2]), title: hit[3].trim() });
    }
    return found;
  }

  // Trailing sentence punctuation is not part of the address: "…/page."
  // broke the link. A closing parenthesis is kept when balanced (the
  // wikipedia pattern).
  function trimUrl(url) {
    let out = String(url);
    while (/[.,;:!?]$/.test(out)) out = out.slice(0, -1);
    if (out.endsWith(")") && (out.match(/\(/g) || []).length < (out.match(/\)/g) || []).length) {
      out = out.slice(0, -1);
    }
    return out;
  }

  // "https://www.example.com/a/b" → "example.com". The domain is the
  // source's identity: the eye looks there first, "which site" is answered
  // at a glance.
  function domainOf(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch {
      return url.replace(/^https?:\/\//, "").split("/")[0] || url;
    }
  }

  // With no title given, a readable name is derived from the address's last
  // segment: "/2026/08/tcmb-faiz-karari" → "tcmb faiz karari". If nothing
  // comes out, only the domain remains — saying less beats inventing a
  // title.
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

  // Readable source row: title + domain, opens in the browser on click.
  function sourceChip(url, title) {
    // A real <a>: on hover the browser shows the address in the status bar,
    // right-click → "copy link address" works. As a span the URL showed
    // nowhere — a live complaint.
    const chip = el("a", "md-source");
    chip.href = url;
    chip.target = "_blank";
    chip.rel = "noopener noreferrer";
    const name = (title || "").trim() || slugTitle(url);
    if (name) chip.append(el2("span", "md-source-title", name));
    chip.append(el2("span", "md-source-host", domainOf(url)));
    chip.title = url;
    return chip;
  }

  const el2 = (tag, cls, text) => {
    const node = el(tag, cls);
    if (text !== undefined) node.textContent = text;
    return node;
  };

  // The in-text `[1]` mark: a clickable superscript when defined.
  function citation(no) {
    const source = sources.get(no);
    const mark = el("sup", "md-cite");
    const git = el("a");
    git.textContent = "[" + no + "]";
    git.href = source.url;
    git.target = "_blank";
    git.rel = "noopener noreferrer";
    git.title = (source.title ? source.title + "\n" : "") + source.url;
    mark.append(git);
    return mark;
  }

  // The source list at the bottom. An address cited under several numbers
  // gets one row: "[1,3] title · example.com" — writing the same source
  // twice stretched the list into unreadability.
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

  // --- file references -------------------------------------------------
  //
  // `src/dornick/loop.py:42` in an answer stayed plain text: the user read
  // the path, opened the panel by hand and searched for the line by hand.
  // Now a link — clicking opens the viewer on that file, scrolled to THAT
  // LINE when one is given.
  //
  // The real difficulty is false positives: not every `one:two` in a
  // sentence can be a link. The rule is kept narrow — a recognised extension
  // (or an explicit folder path) is required, product names like `Node.js`
  // are filtered out, and the inside of a URL is never scanned.

  const EXTS = (
    "py js mjs cjs jsx ts tsx json jsonl yml yaml toml ini cfg conf env " +
    "md mdx txt csv tsv sql sh bash ps1 psm1 bat cmd " +
    "html htm css scss less php phtml rb go rs java kt swift lua vue svelte " +
    "c h cpp hpp cc cs xml svg " +
    "png jpg jpeg gif webp pdf log " +
    // Archives and office: the viewer cannot render them but the link must
    // not stay DEAD — "download the ZIP archive" was a live complaint (zip
    // was missing from the list).
    "zip rar 7z tar gz tgz xlsx docx pptx"
  ).split(" ");

  // Path + optional `:line` (and `:column`). Drive letters, `./`, `~/` and
  // both separators are recognised: the model writes Windows paths too.
  const FILE_REF = new RegExp(
    "(?:[A-Za-z]:[\\\\/])?(?:\\.{1,2}[\\\\/]|~[\\\\/])?" +
    "(?:[\\w.@+-]+[\\\\/])*" +
    "[\\w.@+-]+\\.(?:" + EXTS.join("|") + ")" +
    "(?::(\\d+))?(?::\\d+)?",
    "i"
  );

  // Folder path: ends with a separator, at least two segments
  // ("atolye/borsa-ara/").
  const DIR_REF = /(?:[\w.@+-]+[\\/]){2,}/;

  // Something starting with a domain is an address, not a file:
  // "example.com/a.php" must not become a file link (the URL catcher's job).
  const HOSTISH = /^[\w-]+\.(com|net|org|io|dev|co|app|ai|gov|edu|info|tr|de|uk|fr|nl)([\\/:]|$)/i;

  function fileRef(text) {
    const hit = text.match(FILE_REF) || text.match(DIR_REF);
    if (!hit) return null;

    const raw = hit[0];
    const path = raw.replace(/:\d+(?::\d+)?$/, "");
    if (HOSTISH.test(path)) return null;

    const sep = /[\\/]/.test(path);
    const stem = path.split(/[\\/]/).pop();
    // "Node.js", "Vue.js", "Next.js": product names, not files. With a
    // separator or a line number it really is a file; otherwise a single
    // capitalised segment is left alone.
    if (!sep && !hit[1] && /^[A-Z]/.test(stem)) return null;
    // A single word with no separator and no number is a weak-ish signal,
    // but things like "1.5" never match the extension list anyway.
    return { index: hit.index, raw, path, line: Number(hit[1] || 0) };
  }

  // Types the browser can render itself: a new tab suffices, no download
  // header needed (it can be saved from there too).
  const MEDIA_EXT = /\.(pdf|png|jpe?g|gif|webp|bmp|svg|mp3|wav|ogg|m4a|flac|mp4|webm|mov)$/i;
  // Does it look like a path: has an extension or carries a separator.
  // Enough evidence for an explicit link target — whoever wrote the link
  // already said "this is a file".
  const PATHISH = /^(?:[A-Za-z]:[\\/])?[\w.@ +\-\\/()]+\.[A-Za-z0-9]{1,5}$/;

  // Turns an explicit link target into a real <a>: media opens in a new
  // tab, unrecognised types (zip, archives...) download as an attachment.
  function downloadChip(path, label) {
    const url = "/api/raw?path=" + encodeURIComponent(path);
    const inline = MEDIA_EXT.test(path);
    const chip = el("a", "md-file");
    chip.textContent = label;
    chip.href = inline ? url : url + "&download=1";
    if (inline) {
      chip.target = "_blank";
      chip.rel = "noopener noreferrer";
      chip.title = ceviri("Tıkla — tarayıcıda aç") + "\n" + path;
    } else {
      chip.setAttribute("download", "");
      chip.title = ceviri("Tıkla — indir") + "\n" + path;
    }
    return chip;
  }

  // File link that opens the viewer on click.
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

  // A plain-text fragment: address first, then file path, then citation,
  // signed number last. Order is by position — whichever comes first wins,
  // so a ".php" inside a URL is never mistaken for a file.
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

  // Only DEFINED citations are marked: an undefined `[2]` stays plain text —
  // a link leading to a source that does not exist is not a link.
  function citeHit(text) {
    const re = /\[(\d+)\]/g;
    let hit;
    while ((hit = re.exec(text))) {
      if (sources.has(hit[1])) return hit;
    }
    return null;
  }

  // --- inline ----------------------------------------------------------

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
        // The model most often writes file paths in backticks. If the
        // content is ENTIRELY a path, the code look stays but it becomes
        // clickable — we do not search for links inside code, the code
        // ITSELF is a path.
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
        // An address link becomes a readable source (title + domain); a
        // path link opens the viewer. Everything else stays plain text as
        // before: we do not make the user click something unrecognised the
        // model produced.
        const hedef = hit[4];
        const metin = hit[3] || hedef;
        if (/^https?:\/\//i.test(hedef)) {
          parent.append(sourceChip(trimUrl(hedef), hit[3] || ""));
        } else {
          // In an explicit link the intent is clear: the author (the model)
          // linked to a FILE. Live complaint: "[open the PDF report]
          // (rapor.pdf)" was dead text, "[download the ZIP archive]
          // (rapor.zip)" was not recognised at all (zip missing from the
          // extension list). The type decides: text/code in the viewer,
          // what the browser can render (pdf/image/media) in a new tab, the
          // rest (zip etc.) as a direct download.
          const ref = fileRef(hedef);
          if (ref && ref.raw === hedef && !MEDIA_EXT.test(hedef)) {
            parent.append(fileChip(ref.path, ref.line, metin));
          } else if (PATHISH.test(hedef) && !HOSTISH.test(hedef)) {
            parent.append(downloadChip(hedef, metin));
          } else {
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

  // Signed numbers get colour: `+0,18%` green, `-41,95%` red.
  //
  // With thirty numbers in a table, reading which one went up meant checking
  // each sign one by one; colour gives it at a glance. Only **explicitly
  // signed** ones are coloured — an unsigned number may be a price or a
  // count.
  const SIGNED = /([+−-])\s?(\d[\d.,\s]*)\s?(%|puan\b|bp\b)?/g;

  function signed(parent, text) {
    let at = 0;
    for (const hit of text.matchAll(SIGNED)) {
      // A letter or digit to the left means this is a hyphen, not a sign:
      // "qwen3-9b" or "2026-08-23" must not be coloured.
      const before = text[hit.index - 1] || " ";
      if (/[\w\d]/.test(before)) continue;
      // No percent or unit and no plus sign: probably a date, not a
      // minus-signed value; leave it.
      if (!hit[3] && hit[1] !== "+") continue;

      if (hit.index > at) parent.append(document.createTextNode(text.slice(at, hit.index)));
      const node = el("span", hit[1] === "+" ? "md-up" : "md-down");
      node.textContent = hit[0];
      parent.append(node);
      at = hit.index + hit[0].length;
    }
    if (at < text.length) parent.append(document.createTextNode(text.slice(at)));
  }

  // Some models (qwen, deepseek local formats) write the tool call as PLAIN
  // TEXT instead of using the API: "<tool_call><function=shell>…</tool_call>".
  // That is internal mechanics; streaming it as raw XML into the chat is the
  // very image of "the conversation side is broken". It is stripped out of
  // the answer and reduced to a short note — nothing changes once the model
  // fixes its format.
  const TOOL_LEAK = /<tool_call>[\s\S]*?(?:<\/tool_call>|$)/g;

  function sanitize(text) {
    return String(text || "").replace(TOOL_LEAK, "\n`⚙ araç çağrısı — model biçim hatası, ham hali gizlendi`\n");
  }

  // Draws the text into a container; the container's previous content goes.
  function into(node, text) {
    node.textContent = "";
    node.append(render(sanitize(text)));
    return node;
  }

  return { render, into };
})();
