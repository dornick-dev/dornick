// Arayüz dili.
//
// Kaynak metinler TÜRKÇE ve kodda olduğu gibi duruyor — İngilizce, görüntüleme
// anında TR→EN eşlemesiyle geliyor. Anahtar uydurma yok: eşlemenin anahtarı
// Türkçe metnin kendisi. Eşlemede olmayan metin Türkçe görünür — eksik çeviri
// sessiz bir İngilizce-yarım arayüzden iyidir: eksik hemen göze batar ve
// haritaya eklenir.
//
// Her dosya kendi çevirilerini kendisi kaydeder (Dil.ekle) — çeviri, metnin
// yaşadığı dosyanın başında durur, tek dev sözlük dosyası çürümez.

const Dil = (() => {
  const EN = {};
  let mode = "tr";
  try { mode = localStorage.getItem("neo-dil") || ""; } catch { /* dosya:// */ }
  if (!mode) {
    // İlk açılış: kurulum sihirbazında seçilen dil sunucudan okunuyor
    // (/api/dil → setup.json). Eşzamanlı istek bilinçli: çeviri kipi
    // daha ilk betik yüklenirken belli olmalı; yerel sunucuda bu bir
    // milisaniyelik iş. Cevap ne olursa olsun karar localStorage'a
    // yazılıyor ki bundan sonrası kullanıcının kendi seçimiyle aksın.
    try {
      const istek = new XMLHttpRequest();
      istek.open("GET", "/api/dil", false);
      istek.send();
      mode = (JSON.parse(istek.responseText).dil === "en") ? "en" : "tr";
    } catch { mode = "tr"; /* dosya:// ya da sunucusuz önizleme */ }
    try { localStorage.setItem("neo-dil", mode); } catch { /* dosya:// */ }
  }

  function ekle(pairs) { Object.assign(EN, pairs); }

  // Çeviri: birebir eşleşme; yoksa Türkçesi kalır.
  function t(text) {
    if (mode !== "en" || text == null) return text;
    return EN[String(text)] ?? text;
  }

  function sec(next) {
    try { localStorage.setItem("neo-dil", next); } catch { /* dosya:// */ }
    location.reload();
  }

  // Statik HTML: id → İngilizce metin/nitelik. Sayfa yüklenince bir kez.
  const STATIK = [];
  function statik(id, text, attr) { STATIK.push([id, text, attr]); }

  function uygula() {
    if (mode !== "en") return;
    for (const [id, text, attr] of STATIK) {
      const el = document.getElementById(id);
      if (!el) continue;
      if (attr) el.setAttribute(attr, text);
      else el.textContent = text;
    }
    // data-tab düğmeleri gibi id'siz statikler: seçici tabanlı ikinci liste.
    for (const [sel, text] of SECICI) {
      const el = document.querySelector(sel);
      if (el) el.textContent = text;
    }
  }

  const SECICI = [];
  function secici(sel, text) { SECICI.push([sel, text]); }

  // Sayfa dili: CSS `text-transform: uppercase` locale'e bakıyor ve Türkçe
  // locale'de "i" → "İ" oluyor. İngilizce arayüzde "SIMPLE" rozeti "SİMPLE"
  // diye çıkıyordu — görünmez sanılan bir ayarın çok görünür sonucu.
  try { document.documentElement.lang = (mode === "en") ? "en" : "tr"; }
  catch { /* dosya:// */ }

  document.addEventListener("DOMContentLoaded", uygula);

  return { t, ekle, sec, statik, secici, get mode() { return mode; } };
})();

// Kısa ad: her dosyada `t("...")` diye kullanılıyor.
const t = Dil.t;

// --- index.html'in statik metinleri -------------------------------------
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
Dil.statik("apps", "Apps", "title");
Dil.statik("new-chat", "New chat", "title");
Dil.statik("history", "Toggle sidebar", "title");
Dil.statik("orchestra", "Orchestra", "title");
Dil.statik("focus", "Focus", "title");
Dil.statik("theme", "Theme", "title");
Dil.statik("gear", "Settings", "title");
// Eksik kalanlar: bu düğmelerin hiçbir eşlemesi yoktu ve İngilizce arayüzde
// Türkçe başlık gösteriyorlardı.
Dil.statik("reveal", "Show every memory in the web", "title");
Dil.statik("authority", "Permissions", "title");
Dil.statik("jobs", "Tasks", "title");
Dil.statik("tanima-ikon", "Learn me", "title");
Dil.statik("cams", "Camera off — click to turn on", "title");
Dil.statik("cam-index", "Device index", "title");
Dil.statik("cam-head", "Drag — keep over the brain", "title");

// aria-label'lar da çevriliyor. Eskiden yalnız `title` eşleniyordu; ekran
// okuyucu kullanan biri İngilizce arayüzde Türkçe etiket duyuyordu —
// göze görünmeyen bir eksik, ama eksik.
for (const [id, metin] of [
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
  Dil.statik(id, metin, "aria-label");
}

// Görüntüleyici ve canlı-uygulama kapsülünün ipuçları.
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
Dil.statik("dock-grip", "Resize brain and orchestra", "aria-label");
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
Dil.statik("dock-cost", "Estimated spend — click for the breakdown", "title");
Dil.statik("dock-ctx", "Context usage", "title");
Dil.statik("settings-save", "Save");
Dil.statik("lens-snap", "Take frame");
Dil.secici(".lens-tag", "Vision");
Dil.secici(".panel-head b", "SETTINGS");
Dil.secici("#jobs-panel .jobs-tag", "Tasks");
Dil.secici("#jobs-panel .jobs-desc", "Scheduled work · live runs");
// Ayar sekmeleri (data-tab düğmeleri) ve grup başlıkları.
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
