// UI language.
//
// Source texts are TURKISH and stay in the code as they are — English comes
// at display time through a TR→EN mapping. No invented keys: the mapping key
// is the Turkish text itself. Text missing from the map shows up in Turkish —
// a missing translation beats a silently half-English UI: the gap is
// immediately visible and gets added to the map.
//
// Each file registers its own translations (Dil.ekle) — the translation sits
// at the top of the file where the text lives, so no giant dictionary file
// rots.

const Dil = (() => {
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

  function ekle(pairs) { Object.assign(EN, pairs); }

  // Translation: exact match; otherwise the Turkish stays.
  function t(text) {
    if (mode !== "en" || text == null) return text;
    return EN[String(text)] ?? text;
  }

  function sec(next) {
    try { localStorage.setItem("dornick-dil", next); } catch { /* file:// */ }
    location.reload();
  }

  // Static HTML: id → English text/attribute. Once, when the page loads.
  const STATIC_ROWS = [];
  function statik(id, text, attr) { STATIC_ROWS.push([id, text, attr]); }

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
  function secici(sel, text) { SELECTOR_ROWS.push([sel, text]); }

  // Page language: CSS `text-transform: uppercase` respects the locale, and
  // in the Turkish locale "i" → "İ". In the English UI the "SIMPLE" badge came
  // out as "SİMPLE" — a very visible consequence of a supposedly invisible
  // setting.
  try { document.documentElement.lang = (mode === "en") ? "en" : "tr"; }
  catch { /* file:// */ }

  document.addEventListener("DOMContentLoaded", apply);

  return { t, ekle, sec, statik, secici, get mode() { return mode; } };
})();

// Short alias: used as `t("...")` in every file.
const t = Dil.t;

// --- index.html's static texts ------------------------------------------
Dil.secici("#welcome h1", "What would you like me to do?");
Dil.secici("#welcome p", "I work on your computer. What I learn is woven into the web around me.");
Dil.secici("#cam-stage-ask", "Look at this frame");
Dil.secici("#cam-stage-pop", "Open in a new window");
Dil.secici("#cam-stage-full", "Full screen");
Dil.secici(".cam-stage-tag", "Camera");
Dil.statik("cam-close", "Hide the panel", "aria-label");
Dil.statik("input", "Talk…", "placeholder");
Dil.statik("plus", "Add — file, connector, skill", "title");
Dil.statik("mic", "Push to talk", "title");
Dil.statik("clip", "Attach file", "title");
Dil.statik("stop", "Stop", "title");
Dil.statik("jump", "Jump to latest", "title");
Dil.statik("goals-head", "Click to fold or unfold", "title");
Dil.statik("goals-head", "Goals — fold/unfold", "aria-label");
Dil.statik("mute", "Toggle voice", "title");
Dil.statik("hear", "Listening is off — click to enable", "title");
Dil.statik("eye", "Viewer", "title");
Dil.statik("viewer-add", "New terminal", "title");
Dil.statik("viewer-add", "New terminal", "aria-label");
Dil.statik("viewer-max", "Maximize / restore", "title");
Dil.statik("viewer-max", "Maximize / restore", "aria-label");
Dil.statik("apps", "Apps", "title");
Dil.statik("new-chat", "New chat", "title");
Dil.statik("history", "Toggle sidebar", "title");
Dil.statik("orchestra", "Orchestra", "title");
Dil.statik("focus", "Focus", "title");
Dil.statik("theme", "Theme", "title");
Dil.statik("gear", "Settings", "title");
// The stragglers: these buttons had no mapping at all and showed Turkish
// titles in the English UI.
Dil.statik("reveal", "Show every memory in the web", "title");
Dil.statik("authority", "Permissions", "title");
Dil.statik("jobs", "Tasks", "title");
Dil.statik("tanima-ikon", "Learn me", "title");
Dil.statik("cams", "Camera off — click to turn on", "title");
Dil.statik("cam-index", "Device index", "title");
Dil.statik("cam-head", "Drag — keep over the brain", "title");

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
  Dil.statik(id, text, "aria-label");
}

// Tooltips of the viewer and the live-app capsule.
Dil.statik("side-jobs-head", "Toggle the tasks section", "title");
Dil.statik("side-jobs-head", "Toggle the tasks section", "aria-label");
Dil.statik("side-apps-head", "Toggle the apps section", "title");
Dil.statik("side-apps-head", "Toggle the apps section", "aria-label");
Dil.secici("#side-jobs-head span", "Tasks · Automations");
Dil.secici("#side-apps-head span", "Apps");
Dil.statik("more-tools", "More tools", "title");
Dil.statik("more-tools", "More tools", "aria-label");
Dil.statik("hist-filter-toggle", "Toggle filters", "title");
Dil.statik("hist-filter-toggle", "Toggle filters", "aria-label");
Dil.secici(".side-label", "Chats");
Dil.statik("mind-grip", "Drag to resize", "title");
Dil.statik("mind-grip", "Resize panel", "aria-label");
Dil.statik("dock-grip", "Drag to resize height", "title");
Dil.statik("dock-grip", "Resize viewer and brain", "aria-label");
Dil.statik("cam-head", "Drag — keep on the brain", "title");
Dil.statik("cam-kind", "Camera type", "aria-label");
Dil.statik("legend-toggle", "Toggle the colour key", "title");
Dil.statik("legend-toggle", "Toggle the colour key", "aria-label");
Dil.statik("mind-close", "Hide the brain panel", "title");
Dil.statik("mind-close", "Hide the brain panel", "aria-label");
Dil.statik("mind-open", "Show the brain panel", "title");
Dil.statik("mind-open", "Show the brain panel", "aria-label");
Dil.statik("mind-search", "Search memories", "aria-label");
Dil.statik("mind-search", "Search memories", "placeholder");
Dil.statik("mind", "Brain", "aria-label");
Dil.secici(".mind-tag", "Brain");
Dil.statik("viewer-max", "Maximize / restore", "title");
Dil.statik("viewer-max", "Maximize / restore", "aria-label");
Dil.statik("viewer-grip", "Drag to resize", "title");
Dil.statik("capsule-dot", "Live", "title");
Dil.statik("capsule-addr", "Open the address in a new tab", "title");
Dil.statik("capsule-external", "Open in your browser", "title");
Dil.statik("capsule-external", "Open in browser");
Dil.statik("dock-model", "Model — opens settings", "title");
Dil.statik("dock-effort", "Thinking depth — click to change", "title");
Dil.statik("dock-mode", "Permission mode — click to change", "title");
    Dil.statik("dock-cost", "Estimated total spend — click for the breakdown", "title");
Dil.statik("dock-ctx", "Context usage", "title");
Dil.statik("settings-save", "Save");
Dil.statik("lens-snap", "Take frame");
Dil.secici(".lens-tag", "Vision");
Dil.secici(".panel-head b", "SETTINGS");
Dil.secici("#jobs-panel .jobs-tag", "Tasks");
Dil.secici("#jobs-panel .jobs-desc", "Scheduled work · live runs");
// Settings tabs (data-tab buttons) and group headings.
Dil.secici('[data-tab="model"]', "Model");
Dil.secici('[data-tab="voice"]', "Voice");
Dil.secici('[data-tab="hearing"]', "Microphone");
Dil.secici('[data-tab="eyes"]', "Cameras");
Dil.secici('[data-tab="place"]', "Location");
Dil.secici('[data-tab="devices"]', "Assets");
Dil.secici('[data-tab="skills"]', "Skills");
Dil.secici('[data-tab="connectors"]', "Connectors");
Dil.secici('[data-tab="mail"]', "Mail");
Dil.secici('[data-tab="tasks"]', "Tasks");
Dil.secici('[data-tab="access"]', "Permissions");
Dil.secici('[data-tab="machine"]', "Machine");
Dil.secici('[data-tab="files"]', "Files");
Dil.secici('[data-tab="transfer"]', "Transfer");
Dil.statik("side-ver", "Dornick version", "title");
// Working-folder strip and provider chip (02.09).
Dil.statik("workdir-id", "Working folder — click to change", "title");
Dil.statik("dock-provider", "Provider — click: open settings", "title");
Dil.secici("#workdir-pick", "Choose folder");
Dil.secici("#workdir-new", "New folder");
