// Sözdizimi renklendirme — bağımlılıksız ve DOM tabanlı.
//
// Neden elle yazıldı, [[md.js]] ile aynı gerekçe: buraya akan metni model
// (ya da diskteki, güvenilmeyen bir dosya) üretiyor. Hazır bir vurgulayıcı
// (highlight.js, Prism) HTML dizesi kurup `innerHTML` ile basıyor — bir
// dosyanın içeriğini etiket olarak yorumlatmak açık bir yol. Bu dosya hiç
// HTML dizesi üretmiyor: her parça `createElement` + `textContent`, yani
// koda gömülü bir `<script>` hiçbir koşulda çalışmıyor, yalnızca renklenir.
//
// Tam bir ayrıştırıcı değil, bir belirteçleyici (tokenizer): dil ailesine
// göre yorumları, dizeleri, sayıları, anahtar sözcükleri ve işlevleri
// ayırıyor. Amaç doğruluk değil okunurluk — bir dosyaya bakınca "bu kod"
// hissi versin, düz metin duvarı olmasın.

// Ad `Syntax`, `Highlight` değil: tarayıcıların CSS Custom Highlight API'si
// zaten global bir `Highlight` sınıfı tanımlıyor — aynı adı kullanmak
// `typeof Highlight !== "undefined"` denetimini yanıltıyordu (yerleşik sınıf
// hep var, ama `.paint`i yok).
const Syntax = (() => {
  // Dil aileleri. Uzantı → aile; her ailenin kendi tarayıcısı var.
  const FAMILY = {
    html: "markup", htm: "markup", xml: "markup", svg: "markup",
    css: "css", scss: "css", less: "css",
    json: "json", jsonl: "json",
    javascript: "clike", typescript: "clike", js: "clike", ts: "clike",
    python: "clike", py: "clike", powershell: "clike", ps1: "clike",
    bash: "clike", sh: "clike", sql: "clike", toml: "clike", yaml: "clike",
    yml: "clike", c: "clike", cpp: "clike", go: "clike", rust: "clike",
    java: "clike",
    // PHP burada yoktu ve PHP dosyaları renksiz düz metin kalıyordu; aynı
    // aileden komşuları da eklendi. Kabalık bilinçli: yanlış ailede birkaç
    // sözcük renklenmek, hiç renklenmemekten iyi.
    php: "clike", cs: "clike", ruby: "clike", rb: "clike", lua: "clike",
    kotlin: "clike", kt: "clike", swift: "clike",
  };

  // Anahtar sözcükler. Kabaca — birkaç dilin sözcüğü ortak havuzda; yanlış
  // dilde bir sözcüğü renklendirmek, hiç renklendirmemekten iyi.
  const WORDS = (
    "if else elif for while do done then fi case esac switch return break " +
    "continue function func def fn class struct interface enum import from " +
    "export default const let var val new delete typeof instanceof in of is " +
    "and or not try catch finally throw raise with as async await yield " +
    "lambda pass global nonlocal public private protected static readonly " +
    "type namespace declare extends implements super this self param begin " +
    "process end foreach select where insert update join values create table " +
    "drop alter into group order by having union all set match " +
    "echo use require include elseif endif endforeach"
  ).split(" ");
  const KEYWORDS = new Set(WORDS);

  // Değişmez değerler — anahtar sözcükten ayrı renk.
  const LITERALS = new Set(
    "true false null nil none undefined nan True False None NaN yes no".split(" ")
  );

  const el = (cls, text) => {
    const node = document.createElement("span");
    if (cls) node.className = cls;
    node.textContent = text;
    return node;
  };

  // Bir parça listesini ([sınıf, metin]) <code> içine döker. Sınıfsız
  // (null) parçalar düz metin düğümü olarak gidiyor.
  function emit(target, parts) {
    for (const [cls, text] of parts) {
      if (!text) continue;
      if (cls) target.append(el("hl-" + cls, text));
      else target.append(document.createTextNode(text));
    }
  }

  // --- genel C-benzeri -------------------------------------------------

  // Yorumlar (//  #  --  /* */), dizeler (" ' `  ve üçlüler), sayılar,
  // anahtar sözcükler, işlev çağrıları. Tek bir ana ifadeyle taranıyor;
  // aradaki boşluklar düz metin.
  const CLIKE = new RegExp(
    [
      "\\/\\*[\\s\\S]*?(?:\\*\\/|$)",          // /* blok yorum */
      "(?:\\/\\/|#|--)[^\\n]*",                 // satır yorumu
      '"""[\\s\\S]*?(?:"""|$)',                 // üçlü çift
      "'''[\\s\\S]*?(?:'''|$)",                 // üçlü tek
      "`(?:\\\\.|[^`\\\\])*`?",                 // şablon dizesi
      '"(?:\\\\.|[^"\\\\\\n])*"?',              // çift tırnak
      "'(?:\\\\.|[^'\\\\\\n])*'?",              // tek tırnak
      "\\b0[xX][0-9a-fA-F]+\\b",                // onaltılık
      "\\b\\d[\\d_]*(?:\\.\\d+)?(?:[eE][+-]?\\d+)?\\b",  // sayı
      "[A-Za-z_$@][\\w$]*",                     // tanımlayıcı
    ].join("|"),
    "g"
  );

  function clike(code) {
    const parts = [];
    let last = 0, m;
    CLIKE.lastIndex = 0;
    while ((m = CLIKE.exec(code))) {
      if (m.index > last) parts.push([null, code.slice(last, m.index)]);
      const t = m[0];
      const c = t[0];
      if (t.startsWith("/*") || t.startsWith("//") || c === "#" || t.startsWith("--")) {
        parts.push(["com", t]);
      } else if (c === '"' || c === "'" || c === "`") {
        parts.push(["str", t]);
      } else if (c >= "0" && c <= "9") {
        parts.push(["num", t]);
      } else if (KEYWORDS.has(t)) {
        parts.push(["key", t]);
      } else if (LITERALS.has(t)) {
        parts.push(["lit", t]);
      } else if (c === "@") {
        parts.push(["var", t]);          // dekoratör / PS değişkeni
      } else if (code[CLIKE.lastIndex] === "(") {
        parts.push(["fn", t]);           // işlev çağrısı
      } else {
        parts.push([null, t]);
      }
      last = CLIKE.lastIndex;
    }
    if (last < code.length) parts.push([null, code.slice(last)]);
    return parts;
  }

  // --- json ------------------------------------------------------------

  function json(code) {
    const parts = [];
    const re = /"(?:\\.|[^"\\])*"|\b-?\d[\d.eE+-]*\b|\b(?:true|false|null)\b|[{}\[\]:,]/g;
    let last = 0, m;
    while ((m = re.exec(code))) {
      if (m.index > last) parts.push([null, code.slice(last, m.index)]);
      const t = m[0];
      if (t[0] === '"') {
        // İki noktadan önceki dize anahtar, sonraki değer.
        const after = code.slice(re.lastIndex).match(/^\s*:/);
        parts.push([after ? "prop" : "str", t]);
      } else if (t === "true" || t === "false" || t === "null") {
        parts.push(["lit", t]);
      } else if (/\d/.test(t[0]) || t[0] === "-") {
        parts.push(["num", t]);
      } else {
        parts.push(["punc", t]);
      }
      last = re.lastIndex;
    }
    if (last < code.length) parts.push([null, code.slice(last)]);
    return parts;
  }

  // --- css -------------------------------------------------------------

  function cssLang(code) {
    const parts = [];
    // Bağlam: süslü parantez içinde iki noktadan önce özellik, sonra değer.
    const re = /\/\*[\s\S]*?(?:\*\/|$)|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|@[\w-]+|[.#][\w-]+|-?\d[\d.]*(?:px|em|rem|%|vh|vw|s|ms|deg|fr)?|[\w-]+|[{}();:,]/g;
    let last = 0, m, inBlock = false, afterColon = false;
    while ((m = re.exec(code))) {
      if (m.index > last) parts.push([null, code.slice(last, m.index)]);
      const t = m[0];
      if (t.startsWith("/*")) parts.push(["com", t]);
      else if (t[0] === '"' || t[0] === "'") parts.push(["str", t]);
      else if (t[0] === "@") parts.push(["key", t]);
      else if (t === "{") { inBlock = true; afterColon = false; parts.push(["punc", t]); }
      else if (t === "}") { inBlock = false; parts.push(["punc", t]); }
      else if (t === ":") { afterColon = true; parts.push(["punc", t]); }
      else if (t === ";") { afterColon = false; parts.push(["punc", t]); }
      else if (/^[{}();:,]$/.test(t)) parts.push(["punc", t]);
      else if (t[0] === "." || t[0] === "#") parts.push(["fn", t]);   // seçici
      else if (/^-?\d/.test(t)) parts.push(["num", t]);
      else if (inBlock && !afterColon) parts.push(["prop", t]);        // özellik
      else parts.push([null, t]);
    }
    if (last < code.length) parts.push([null, code.slice(last)]);
    return parts;
  }

  // --- markup (html / xml) ---------------------------------------------

  function markup(code) {
    const parts = [];
    let i = 0;
    const n = code.length;
    while (i < n) {
      if (code.startsWith("<!--", i)) {
        let e = code.indexOf("-->", i);
        e = e < 0 ? n : e + 3;
        parts.push(["com", code.slice(i, e)]); i = e; continue;
      }
      if (code[i] === "<") {
        let e = code.indexOf(">", i);
        e = e < 0 ? n : e + 1;
        tag(code.slice(i, e), parts); i = e; continue;
      }
      let e = code.indexOf("<", i);
      e = e < 0 ? n : e;
      parts.push([null, code.slice(i, e)]); i = e;
    }
    return parts;
  }

  function tag(s, parts) {
    const open = s.match(/^<[/!?]?[A-Za-z][\w:-]*/) || s.match(/^<[/!?]?/);
    parts.push(["tag", open[0]]);
    const rest = s.slice(open[0].length);
    const re = /"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[\w:-]+|[=/>]|[\s\S]/g;
    let m;
    while ((m = re.exec(rest))) {
      const t = m[0];
      if (t[0] === '"' || t[0] === "'") parts.push(["str", t]);
      else if (/^[\w:-]+$/.test(t)) parts.push(["atn", t]);   // öznitelik adı
      else if (t === "=" || t === ">" || t === "/") parts.push(["punc", t]);
      else parts.push([null, t]);
    }
  }

  const SCAN = { markup, css: cssLang, json, clike };

  // Dışarıya açık: <code> düğümünü temizler, dile göre renkli parçalarla
  // yeniden doldurur. Dil tanınmıyorsa düz metin — renklendirememek, yanlış
  // renklendirmekten iyi.
  function paint(target, text, lang) {
    target.textContent = "";
    const family = FAMILY[(lang || "").toLowerCase()];
    if (!family) { target.textContent = text; return; }
    try {
      emit(target, SCAN[family](text));
    } catch {
      target.textContent = text;   // tarayıcı patlarsa metin yine görünsün
    }
  }

  return { paint };
})();
