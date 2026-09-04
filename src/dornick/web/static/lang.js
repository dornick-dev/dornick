// UI language.
//
// Source texts are TURKISH and stay in the code as they are — English comes
// at display time through a TR→EN mapping. No invented keys: the mapping key
// is the Turkish text itself. Text missing from the map shows up in Turkish —
// a missing translation beats a silently half-English UI: the gap is
// immediately visible and gets added to the map.
//
// Each file registers its own translations (Lang.add) — the translation sits
// at the top of the file where the text lives, so no giant dictionary file
// rots.

const Lang = (() => {
  const EN = {};
  let mode = "tr";
  try { mode = localStorage.getItem("dornick-dil") || ""; } catch { /* file:// */ }
  if (!mode) {
    // First launch: the language picked in the setup wizard is read from
    // the server (/api/dil → setup.json). The synchronous request is
    // deliberate: the translation mode must be known while the very first
    // script loads; on a local server this is a millisecond's work. Whatever
    // the answer, the decision is written to localStorage so everything from
    // here on follows the user's own choice.
    try {
      const req = new XMLHttpRequest();
      req.open("GET", "/api/dil", false);
      req.send();
      // The server reports either the wizard's language or the machine's.
      // DEFAULT ENGLISH: Turkish only when "tr" comes back (user request,
      // 02.09 — the product opens to the world in English, ships Turkish in
      // Turkey).
      mode = (JSON.parse(req.responseText).dil === "tr") ? "tr" : "en";
    } catch {
      // Serverless preview: check the browser language, else English.
      const nav = (navigator.language || "").toLowerCase();
      mode = nav.startsWith("tr") ? "tr" : "en";
    }
    try { localStorage.setItem("dornick-dil", mode); } catch { /* file:// */ }
  }

  function add(pairs) { Object.assign(EN, pairs); }

  // Translation: exact match; otherwise the Turkish stays.
  function t(text) {
    if (mode !== "en" || text == null) return text;
    return EN[String(text)] ?? text;
  }

  function pick(next) {
    try { localStorage.setItem("dornick-dil", next); } catch { /* file:// */ }
    location.reload();
  }

  // Static HTML: id → English text/attribute. Once, when the page loads.
  const STATIC_ROWS = [];
  function statics(id, text, attr) { STATIC_ROWS.push([id, text, attr]); }

  function apply() {
    if (mode !== "en") return;
    for (const [id, text, attr] of STATIC_ROWS) {
      const el = document.getElementById(id);
      if (!el) continue;
      if (attr) el.setAttribute(attr, text);
      else el.textContent = text;
    }
    // Statics without an id, like the data-tab buttons: a second, selector-based list.
    for (const [sel, text] of SELECTOR_ROWS) {
      const el = document.querySelector(sel);
      if (el) el.textContent = text;
    }
  }

  const SELECTOR_ROWS = [];
  function selectors(sel, text) { SELECTOR_ROWS.push([sel, text]); }

  // Page language: CSS `text-transform: uppercase` respects the locale, and
  // in the Turkish locale "i" → "İ". In the English UI the "SIMPLE" badge came
  // out as "SİMPLE" — a very visible consequence of a supposedly invisible
  // setting.
  try { document.documentElement.lang = (mode === "en") ? "en" : "tr"; }
  catch { /* file:// */ }

  document.addEventListener("DOMContentLoaded", apply);

  return { t, add, pick, statics, selectors, get mode() { return mode; } };
})();

// Short alias: used as `t("...")` in every file.
const t = Lang.t;

// --- index.html's static texts ------------------------------------------
Lang.selectors("#welcome h1", "What would you like me to do?");
Lang.selectors("#welcome p", "I work on your computer. What I learn is woven into the web around me.");
Lang.selectors("#cam-stage-ask", "Look at this frame");
Lang.selectors("#cam-stage-pop", "Open in a new window");
Lang.selectors("#cam-stage-full", "Full screen");
Lang.selectors(".cam-stage-tag", "Camera");
Lang.statics("cam-close", "Hide the panel", "aria-label");
Lang.statics("input", "Talk…", "placeholder");
Lang.statics("plus", "Add — file, connector, skill", "title");
Lang.statics("mic", "Push to talk", "title");
Lang.statics("clip", "Attach file", "title");
Lang.statics("stop", "Stop", "title");
Lang.statics("jump", "Jump to latest", "title");
Lang.statics("goals-head", "Click to fold or unfold", "title");
Lang.statics("goals-head", "Goals — fold/unfold", "aria-label");
Lang.statics("mute", "Toggle voice", "title");
Lang.statics("hear", "Listening is off — click to enable", "title");
Lang.statics("eye", "Viewer", "title");
Lang.statics("viewer-add", "New terminal", "title");
Lang.statics("viewer-add", "New terminal", "aria-label");
Lang.statics("viewer-max", "Maximize / restore", "title");
Lang.statics("viewer-max", "Maximize / restore", "aria-label");
Lang.statics("apps", "Apps", "title");
Lang.statics("new-chat", "New chat", "title");
Lang.statics("history", "Toggle sidebar", "title");
Lang.statics("orchestra", "Orchestra", "title");
Lang.statics("focus", "Focus", "title");
Lang.statics("theme", "Theme", "title");
Lang.statics("gear", "Settings", "title");
// The stragglers: these buttons had no mapping at all and showed Turkish
// titles in the English UI.
Lang.statics("reveal", "Show every memory in the web", "title");
Lang.statics("authority", "Permissions", "title");
Lang.statics("jobs", "Tasks", "title");
Lang.statics("tanima-ikon", "Learn me", "title");
Lang.statics("cams", "Camera off — click to turn on", "title");
Lang.statics("cam-index", "Device index", "title");
Lang.statics("cam-head", "Drag — keep over the brain", "title");

// aria-labels are translated too. Only `title` used to be mapped; a screen
// reader user heard Turkish labels in the English UI — a gap invisible to the
// eye, but a gap.
for (const [id, text] of [
  ["reveal", "Show every memory in the web"],
  ["authority", "Permissions"],
  ["eye", "Viewer"],
  ["apps", "Apps"],
  ["new-chat", "New chat"],
  ["history", "Toggle sidebar"],
  ["jobs", "Tasks"],
  ["orchestra", "Subagents"],
  ["focus", "Focus mode"],
  ["tanima-ikon", "Learn me"],
  ["theme", "Light / dark mode"],
  ["gear", "Settings"],
  ["stop", "Stop"],
  ["mute", "Voice"],
  ["plus", "Add"],
  ["mic", "Microphone"],
  ["clip", "File"],
  ["jump", "Jump to latest"],
  ["send", "Send"],
  ["cams", "Camera watch"],
  ["win-min", "Minimize"],
  ["win-max", "Maximize"],
  ["viewer-grip", "Resize panel"],
  ["capsule-external", "Open outside"],
]) {
  Lang.statics(id, text, "aria-label");
}

// Tooltips of the viewer and the live-app capsule.
Lang.statics("side-jobs-head", "Toggle the tasks section", "title");
Lang.statics("side-jobs-head", "Toggle the tasks section", "aria-label");
Lang.statics("side-apps-head", "Toggle the apps section", "title");
Lang.statics("side-apps-head", "Toggle the apps section", "aria-label");
Lang.selectors("#side-jobs-head span", "Tasks · Automations");
Lang.selectors("#side-apps-head span", "Apps");
Lang.statics("more-tools", "More tools", "title");
Lang.statics("more-tools", "More tools", "aria-label");
Lang.statics("hist-filter-toggle", "Toggle filters", "title");
Lang.statics("hist-filter-toggle", "Toggle filters", "aria-label");
Lang.selectors(".side-label", "Chats");
Lang.statics("mind-grip", "Drag to resize", "title");
Lang.statics("mind-grip", "Resize panel", "aria-label");
Lang.statics("dock-grip", "Drag to resize height", "title");
Lang.statics("dock-grip", "Resize viewer and brain", "aria-label");
Lang.statics("cam-head", "Drag — keep on the brain", "title");
Lang.statics("cam-kind", "Camera type", "aria-label");
Lang.statics("legend-toggle", "Toggle the colour key", "title");
Lang.statics("legend-toggle", "Toggle the colour key", "aria-label");
Lang.statics("mind-close", "Hide the brain panel", "title");
Lang.statics("mind-close", "Hide the brain panel", "aria-label");
// Brain regions (Phase 6).
Lang.statics("thalamus", "Thalamus ring", "aria-label");
Lang.statics("rhythm", "Rhythm clock", "aria-label");
Lang.statics("brainstem", "Brainstem pulse", "aria-label");
Lang.statics("regions-tabs", "Brain tabs", "aria-label");
Lang.statics("mind-open", "Show the brain panel", "title");
Lang.statics("mind-open", "Show the brain panel", "aria-label");
Lang.statics("mind-search", "Search memories", "aria-label");
Lang.statics("mind-search", "Search memories", "placeholder");
Lang.statics("mind", "Brain", "aria-label");
Lang.selectors(".mind-tag", "Brain");
Lang.statics("viewer-max", "Maximize / restore", "title");
Lang.statics("viewer-max", "Maximize / restore", "aria-label");
Lang.statics("viewer-grip", "Drag to resize", "title");
Lang.statics("capsule-dot", "Live", "title");
Lang.statics("capsule-addr", "Open the address in a new tab", "title");
Lang.statics("capsule-external", "Open in your browser", "title");
Lang.statics("capsule-external", "Open in browser");
Lang.statics("dock-model", "Model — opens settings", "title");
Lang.statics("dock-effort", "Thinking depth — click to change", "title");
Lang.statics("dock-mode", "Permission mode — click to change", "title");
    Lang.statics("dock-cost", "Estimated total spend — click for the breakdown", "title");
Lang.statics("dock-ctx", "Context usage", "title");
Lang.statics("settings-save", "Save");
Lang.statics("lens-snap", "Take frame");
Lang.selectors(".lens-tag", "Vision");
Lang.selectors(".panel-head b", "SETTINGS");
Lang.selectors("#jobs-panel .jobs-tag", "Tasks");
Lang.selectors("#jobs-panel .jobs-desc", "Scheduled work · live runs");
// Settings tabs (data-tab buttons) and group headings.
Lang.selectors('[data-tab="model"]', "Model");
Lang.selectors('[data-tab="voice"]', "Voice");
Lang.selectors('[data-tab="hearing"]', "Microphone");
Lang.selectors('[data-tab="eyes"]', "Cameras");
Lang.selectors('[data-tab="place"]', "Location");
Lang.selectors('[data-tab="devices"]', "Assets");
Lang.selectors('[data-tab="skills"]', "Skills");
Lang.selectors('[data-tab="connectors"]', "Connectors");
Lang.selectors('[data-tab="mail"]', "Mail");
Lang.selectors('[data-tab="tasks"]', "Tasks");
Lang.selectors('[data-tab="access"]', "Permissions");
Lang.selectors('[data-tab="machine"]', "Machine");
Lang.selectors('[data-tab="files"]', "Files");
Lang.selectors('[data-tab="transfer"]', "Transfer");
Lang.statics("side-ver", "Dornick version", "title");
// Working-folder strip and provider chip (02.09).
Lang.statics("workdir-id", "Working folder — click to change", "title");
Lang.statics("dock-provider", "Provider — click: open settings", "title");
Lang.selectors("#workdir-pick", "Choose folder");
Lang.selectors("#workdir-new", "New folder");
