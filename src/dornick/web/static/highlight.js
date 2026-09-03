// Syntax colouring — dependency-free and DOM-based.
//
// Why hand-written: same rationale as [[md.js]] — the text flowing in is
// produced by the model (or by an untrusted file on disk). An off-the-shelf
// highlighter (highlight.js, Prism) builds an HTML string and injects it with
// `innerHTML` — letting a file's content be interpreted as markup is an open
// door. This file never produces an HTML string: every piece is
// `createElement` + `textContent`, so a `<script>` embedded in code never
// runs under any circumstances, it only gets coloured.
//
// Not a full parser, a tokenizer: by language family it separates comments,
// strings, numbers, keywords and functions. The goal is readability, not
// correctness — looking at a file should feel like "this is code", not a
// wall of plain text.

// The name is `Syntax`, not `Highlight`: browsers' CSS Custom Highlight API
// already defines a global `Highlight` class — using the same name fooled the
// `typeof Highlight !== "undefined"` check (the built-in class always exists,
// but has no `.paint`).
const Syntax = (() => {
  // Language families. Extension → family; each family has its own scanner.
  const FAMILY = {
    html: "markup", htm: "markup", xml: "markup", svg: "markup",
    css: "css", scss: "css", less: "css",
    json: "json", jsonl: "json",
    javascript: "clike", typescript: "clike", js: "clike", ts: "clike",
    python: "clike", py: "clike", powershell: "clike", ps1: "clike",
    bash: "clike", sh: "clike", sql: "clike", toml: "clike", yaml: "clike",
    yml: "clike", c: "clike", cpp: "clike", go: "clike", rust: "clike",
    java: "clike",
    // PHP was missing here and PHP files stayed colourless plain text; its
    // same-family neighbours were added too. The coarseness is deliberate: a
    // few words coloured in the wrong family beats no colouring at all.
    php: "clike", cs: "clike", ruby: "clike", rb: "clike", lua: "clike",
    kotlin: "clike", kt: "clike", swift: "clike",
  };

  // Keywords. Rough — several languages share one pool; colouring a word in
  // the wrong language beats not colouring it at all.
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

  // Literals — a colour separate from keywords.
  const LITERALS = new Set(
    "true false null nil none undefined nan True False None NaN yes no".split(" ")
  );

  const el = (cls, text) => {
    const node = document.createElement("span");
    if (cls) node.className = cls;
    node.textContent = text;
    return node;
  };

  // Dumps a list of pieces ([class, text]) into a <code>. Classless (null)
  // pieces go in as plain text nodes.
  function emit(target, parts) {
    for (const [cls, text] of parts) {
      if (!text) continue;
      if (cls) target.append(el("hl-" + cls, text));
      else target.append(document.createTextNode(text));
    }
  }

  // --- generic C-like --------------------------------------------------

  // Comments (//  #  --  /* */), strings (" ' `  and triples), numbers,
  // keywords, function calls. Scanned with a single master expression; the
  // gaps in between are plain text.
  const CLIKE = new RegExp(
    [
      "\\/\\*[\\s\\S]*?(?:\\*\\/|$)",          // /* block comment */
      "(?:\\/\\/|#|--)[^\\n]*",                 // line comment
      '"""[\\s\\S]*?(?:"""|$)',                 // triple double
      "'''[\\s\\S]*?(?:'''|$)",                 // triple single
      "`(?:\\\\.|[^`\\\\])*`?",                 // template string
      '"(?:\\\\.|[^"\\\\\\n])*"?',              // double quote
      "'(?:\\\\.|[^'\\\\\\n])*'?",              // single quote
      "\\b0[xX][0-9a-fA-F]+\\b",                // hexadecimal
      "\\b\\d[\\d_]*(?:\\.\\d+)?(?:[eE][+-]?\\d+)?\\b",  // number
      "[A-Za-z_$@][\\w$]*",                     // identifier
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
        parts.push(["var", t]);          // decorator / PS variable
      } else if (code[CLIKE.lastIndex] === "(") {
        parts.push(["fn", t]);           // function call
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
        // A string before a colon is a key, after it a value.
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
    // Context: inside braces, before the colon a property, after it a value.
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
      else if (t[0] === "." || t[0] === "#") parts.push(["fn", t]);   // selector
      else if (/^-?\d/.test(t)) parts.push(["num", t]);
      else if (inBlock && !afterColon) parts.push(["prop", t]);        // property
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
      else if (/^[\w:-]+$/.test(t)) parts.push(["atn", t]);   // attribute name
      else if (t === "=" || t === ">" || t === "/") parts.push(["punc", t]);
      else parts.push([null, t]);
    }
  }

  const SCAN = { markup, css: cssLang, json, clike };

  // The public surface: clears the <code> node and refills it with coloured
  // pieces per language. Unrecognised language: plain text — failing to
  // colour beats colouring wrongly.
  function paint(target, text, lang) {
    target.textContent = "";
    const family = FAMILY[(lang || "").toLowerCase()];
    if (!family) { target.textContent = text; return; }
    try {
      emit(target, SCAN[family](text));
    } catch {
      target.textContent = text;   // if the scanner blows up, still show the text
    }
  }

  return { paint };
})();
