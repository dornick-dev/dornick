// Chat, live stream and approval.
// Two channels to the server: commands go out via POST, everything comes back via SSE.

// English translations of the texts this file shows the user. The source
// text stays Turkish; it is translated at display time with t("...").
Lang.add({
  "Ses su an uretilemiyor — ses servisine ulasilamiyor olabilir (internet gerekli). Metin ekranda; ses duzelince kendiliginden devam eder.":
    "Speech is unavailable right now — the voice service may be unreachable (internet required). The text stays on screen; audio resumes once the service is back.",
  // Version suffix in the brand tooltip
  " · kurulum": " · installed",
  " · geliştirme": " · development",
  // Interjection and helper approval
  "araya girdi": "interjected",
  "Araya alındı": "Interjected",
  "İşleniyor": "Working it in",
  "yardımcı": "helper",
  // Welcome
  "Ne yapmamı istersin?": "What would you like me to do?",
  "Bilgisayarında çalışıyorum. Öğrendiklerim etrafımdaki ağa yazılıyor.":
    "I work on your computer. What I learn is woven into the web around me.",
  // Status strip and modes
  "Hazır": "Ready", "Uyanıyor": "Waking", "Çalışıyor": "Working",
  "Düşünüyor": "Thinking", "Yazıyor": "Writing", "Hatırlıyor": "Recalling",
  "Akıl yürütüyor": "Reasoning",
  "Arıyor": "Searching",
  "Exploring": "Exploring",
  "Editing": "Editing",
  "Running": "Running",
  "Konuş…": "Talk…",
  "Model yükleniyor…": "Loading model…",
  "Model yanıtı bekleniyor…": "Waiting for the model…",
  "Beyni öne al / geri": "Bring brain forward / back",
  "Sunucu yok": "No server",
  "Bağlantı koptu": "Connection lost",
  // Rotating thinking words
  "Tartıyor": "Weighing", "Evirip çeviriyor": "Mulling",
  "Kurcalıyor": "Tinkering", "Süzüyor": "Sifting", "Demliyor": "Brewing",
  "Yokluyor": "Probing", "Harmanlıyor": "Blending",
  "Eliyor": "Winnowing", "Çözüyor": "Untangling", "Örüyor": "Knitting",
  "Dokuyor": "Weaving", "Damıtıyor": "Distilling", "Ayıklıyor": "Culling",
  "Kazıyor": "Digging", "Sezinliyor": "Sensing", "Kurguluyor": "Plotting",
  "Yoğuruyor": "Kneading", "Mayalıyor": "Fermenting", "Cilalıyor": "Polishing",
  "Didikliyor": "Picking apart", "İz sürüyor": "Tracing",
  "Kafa yoruyor": "Puzzling", "Ölçüp biçiyor": "Sizing up",
  "Kıyaslıyor": "Comparing", "Derliyor": "Compiling",
  "Bağdaştırıyor": "Reconciling", "Tasarlıyor": "Sketching",
  // Action synonyms (picked consistently within a turn)
  "Koşturuyor": "Running", "Göz atıyor": "Skimming", "İnceliyor": "Examining",
  "Elden geçiriyor": "Reworking", "Kaleme alıyor": "Drafting",
  "Tarıyor": "Scanning", "Eşeliyor": "Digging around",
  "Sayfayı açıyor": "Opening the page", "Göz gezdiriyor": "Glancing over",
  "Anımsıyor": "Recollecting", "Not düşüyor": "Jotting down",
  // Tool actions
  "Araştırıyor": "Researching", "Okuyor": "Reading", "Bakıyor": "Looking",
  "Oluşturuyor": "Creating", "Düzenliyor": "Editing", "Kopyalıyor": "Copying",
  "Çiziyor": "Drawing", "Çalıştırıyor": "Running",
  "Aklına yazıyor": "Memorizing", "Planlıyor": "Planning",
  "Ekrana bakıyor": "Viewing screen", "Bilgisayarı kullanıyor": "Using computer",
  "İnternette geziniyor": "Browsing", "Cihaza bağlanıyor": "Connecting",
  "Yetenek yazıyor": "Writing skill", "Model seçiyor": "Picking model",
  "Yardımcı çalıştırıyor": "Running helper", "Zamanlıyor": "Scheduling",
  "Posta okuyor": "Reading mail", "Posta gönderiyor": "Sending mail",
  "Konuma bakıyor": "Checking location",
  // Work strip
  "Düşündü": "Thought", "✻ Düşündü": "✻ Thought", " kelime": " words",
  "Daha eskiyi göster": "Show older", " tur": " turns",
  // First-run setup card
  "Önce bir sağlayıcı bağla": "Connect a provider first",
  "Henüz bir model bağlı değil. Bir sağlayıcı seç (OpenRouter, OpenAI, Anthropic ya da LM Studio gibi yerel bir sunucu), API anahtarını gir ve kaydet; ardından Dornick'i kapatıp yeniden aç — sohbet ondan sonra başlar.":
    "No model is connected yet. Pick a provider (OpenRouter, OpenAI, Anthropic, or a local server like LM Studio), enter your API key and save; then close and reopen Dornick — chat starts after that.",
  "Sağlayıcı ve model seç": "Choose provider and model",
  "Tıkla — bu turun muhakemesini gör": "Click to see this turn's reasoning",
  " kez": " times",
  "Tıkla — tamamını gör": "Click to see all",
  "Hatırlananlar — tıkla, tamamını gör": "Recalled — click to see all",
  "Devamı": "More", "Kısalt": "Collapse",
  "Sırada": "Queued",
  " argüman": " arguments",
  // Model wait state (lives in the work strip, never lands in the chat)
  "Model bekleniyor": "Waiting for model",
  "deneme": "attempt",
  "yeniden deneniyor…": "retrying…",
  "İş bekletiliyor — model erişilebilir olunca sürecek":
    "Job on hold — resumes when the model is reachable",
  "İş bekletiliyor": "Job on hold",
  "Model çağrısı": "Model call",
  "bekletiliyor": "on hold",
  "Model geri geldi": "Model is back",
  " deneme sonrası": " attempts later",
  "kesildi": "interrupted",
  "Tıkla — ayrıntıyı gör": "Click to see details",
  "Tıkla — hatanın ayrıntısını gör": "Click to see the error detail",
  "Tıkla — adımın ayrıntısını gör": "Click to see the step detail",
  // Camera and voice
  "Bakıyor…": "Looking…",
  "Ses duyuyor": "Hearing sound",
  "Gönderilen görsel": "Attached image",
  "Tıkla: dinlemeyi durdur": "Click to stop listening",
  "Tıkla: dinlemeye devam": "Click to keep listening",
  "Elle konuş (arkada zaten dinliyor)": "Push to talk (already listening in the background)",
  "Tıkla ve konuş": "Click and talk",
  "Sesi aç": "Turn voice on",
  "Sesi kapat": "Turn voice off",
  "Ses kapalı — tıkla: aç": "Voice off — click to turn on",
  "Ses açık — tıkla: ayarla": "Voice on — click to adjust",
  "Dinlemeyi aç": "Turn listening on",
  "Dinlemeyi kapat": "Turn listening off",
  "Dinleme kapalı — tıkla: aç": "Listening off — click to turn on",
  "Dinleme açık — tıkla: ayarla": "Listening on — click to adjust",
  "Ayarları aç": "Open settings",
  // Composer + menu and attachments
  "Dosya ekle": "Add file", "belge, görsel, veri": "document, image, data",
  "Bağlantılar": "Connectors", "MCP sunucuları": "MCP servers",
  "Yetenekler": "Skills", "kendi araçların": "your own tools",
  "Yeni görev": "New task", "zamanlanmış iş": "scheduled job",
  "Kamera": "Camera", "aç/kapa, izleme": "on/off, watching",
  "Program kapalıyken zamanı geçmiş görevler var.":
    "Some scheduled tasks were due while Dornick was closed.",
  "Bu seferlik atla": "Skip this time",
  "Şimdi yap": "Run now",
  "Listeden çıkar": "Remove from list",
  "Konuşulan": "Talking about", "Bağlamdan çıkar": "Remove from context",
  // Authority
  "Yetki: ": "Access: ",
  " — hiçbir şey sorulmuyor": " — nothing is asked",
  " · tıkla: tam yetki": " · click: full access",
  " · tıkla: kip seç": " · click: choose mode",
  "otomatik": "auto", "sorar": "asks", "salt okunur": "read-only",
  "tam yetki": "full access",
  // Dock and its popups
  "Düşünme derinliği": "Thinking depth", "Yetki kipi": "Permission mode",
  "Bağlam": "Context",
  "en hızlı — kısa düşünür": "fastest — thinks briefly", "hızlı": "fast",
  "dengeli": "balanced", "derin": "deep", "en derin — en yavaş": "deepest — slowest",
  "okuma serbest, yazma sorulur": "reads freely, asks before writing",
  "en güvenlisi, en yavaşı": "safest, slowest",
  "hiçbir şeyi değiştiremez": "cannot change anything",
  "hiçbir şey sorulmaz": "asks nothing",
  "Katalog soruluyor…": "Fetching catalog…",
  "Sunucu liste vermiyor — ayarlardan elle yazılır.":
    "The server offers no list — set the model manually in settings.",
  "Ayarları aç": "Open settings",
  "model içinde ara…": "models — type to search…",
  "Eşleşen yok.": "No matches.",
  "Pencere: ": "Window: ", " token — dolu: %": " tokens — used: %",
  "Son istem: ": "Last prompt: ", " (önbellekten ": " (cached ",
  "Son cevap: ": "Last reply: ", " token": " tokens", " önbellek": " cached",
  "Bu oturumda henüz tur yok.": "No turns in this session yet.",
  " dolu": " Full",
  "Sistem istemi": "System prompt",
  "Araç tanımları": "Tool definitions",
  "Ruh / kurallar": "Rules",
  "Yetenekler": "Skills",
  "MCP ve dinamik araçlar": "MCP & dynamic tools",
  "Yardımcı tanımları": "Subagent definitions",
  "Konuşma": "Conversation",
  "Kapat": "Close",
  "Kalemler karakter/4 tahmini; toplam sağlayıcıdan.":
    "Line items are char/4 estimates; the total is from the provider.",
  // Cost chip
  "Bu turun tahmini harcaması — tıkla: kırılım":
    "This turn's estimated spend — click for the breakdown",
  "Bu oturumun tahmini toplam harcaması — tıkla: kırılım":
    "Estimated total spend for this chat — click for the breakdown",
  " · bu tur: ": " · this turn: ",
  " · premium model (çıktı > $20/M)": " · premium model (output > $20/M)",
  "Tahmini harcama": "Estimated spend",
  // Budget brake (in the cost chip's popup)
  " · oturum sınırı: ": " · session cap: ",
  "Bu oturum için üst sınır": "Cap for this session",
  "sınırsız": "no cap",
  "Uygula": "Apply",
  "Sınıra ulaşılınca koşan tur durur; yükseltince kaldığı yerden sürer.":
    "When the cap is hit the running turn stops; raise it and work resumes.",
  "Fiyat bilinmiyor (yerel sunucu ya da katalog dışı model) — fren çalışmaz.":
    "Price unknown (local server or model outside the catalogue) — the brake cannot work.",
  "Sınır kaydedilemedi.": "Could not save the cap.",
  "Premium model: çıktı priceı $20/M üstünde.":
    "Premium model: output price above $20/M.",
  "Bu tur: ": "This turn: ", "oturum: ": "session: ",
  "Girdi: ": "Input: ", "Çıktı: ": "Output: ",
  "Tahmin — önbellek indirimi hesaba katılmaz.":
    "An estimate — cache discounts are not counted.",
  "Fiyat bilinmiyor — yalnız token sayısı.":
    "Price unknown — token counts only.",
  // Approval dialog
  "Bir komut çalıştıracak.": "Will run a command.",
  "Bir dosyayı okuyacak.": "Will read a file.",
  "Bir dosyanın üzerine yazacak.": "Will overwrite a file.",
  "Bir dosyayı değiştirecek.": "Will edit a file.",
  "Bir dizini listeleyecek.": "Will list a directory.",
  "Zihninden bir kaydı silecek.": "Will erase a record from its mind.",
  "Zihnine kalıcı olarak yazacak.": "Will write permanently to its mind.",
  "Hedef listesini güncelleyecek.": "Will update the goal list.",
  "aracını çalıştıracak.": "tool will be run.",
  "Değişiklik yapar · ": "Makes changes · ", "Salt okuma · ": "Read-only · ",
  // Learn-me
  "Tanıma eğitimi arka planda": "Personal training in the background",
  "Tanıma eğitimi tamamlandı": "Personal training finished",
  "Beni tanı açık": "Learn-me is on",
  "son eğitim": "last training",
  "henüz yok": "not yet",
  "tıkla: şimdi eğit": "click to train now",
  "Şu an seni tanıyorum — eğitim arka planda sürüyor":
    "Learning you now — training in the background",
  // Notifications
  "Model bu isteği reddetti.": "The model refused this request.",
  "Kesildi.": "Interrupted.",
  // First-run guidance (verbatim copy of settings.KURULUM_YONLENDIRME)
  ["Henüz bir yapay zekâ sağlayıcısı tanımlı değil. Ayarlar › Model'den bir " +
   "sağlayıcı seçip API anahtarı girmelisin. Varsayılan sağlayıcı " +
   "OpenRouter'dır — anahtarını girdiğinde ücretsiz modellerle 'Oto' modda " +
   "hemen başlayabilirsin."]:
    "No AI provider is configured yet. Open Settings › Model, pick a " +
    "provider and enter an API key. The default provider is OpenRouter — " +
    "once you enter your key you can start right away in 'Auto' mode with " +
    "free models.",
  // Auto-mode note (only OpenRouter + "oto")
  ["Oto modda OpenRouter'ın ücretsiz modelleri kullanılır; kalite ve hız " +
   "düşebilir, model istek sırasında değişebilir. Bazı ücretsiz uçlar " +
   "veriyi eğitimde kullanabilir; istekler 'veri toplama: reddet' " +
   "tercihiyle gönderilir."]:
    "Auto mode uses OpenRouter's free models; quality and speed may drop, " +
    "and the model can change per request. Some free endpoints may use " +
    "your data for training; requests are sent with 'data collection: deny'.",
  "Köprü: ": "Bridge: ", "bağlandı": "linked",
  // Recall trace
  "İz · ": "Trace · ", "Hatırlama izi": "Recall trace",
  "Seçim bu sohbette kalır; yeni sohbet ve sonraki açılış onu devralır. Küresel varsayılan: Ayarlar → Model.":
    "The pick stays with this chat; new chats and the next launch inherit it. Global default: Settings → Model.",
  "Sorgu": "Query", ". sicrama": ". hop", "Bakildi": "Glanced",
  " kayda daha bakıldı": " more records glanced",
  // Smart scrolling
  " yeni": " new",
  // Step cards
  "çıkış ": "exit ",
  "hata": "error",
  "Tümünü genişlet": "Expand fully",
  "Kopyala": "Copy", "Kopyalanamadı": "Could not copy",
  "Dosyayı aç": "Open file",
  "düzenleme": "edit", "yazma": "write", "okuma": "read", "dizin": "dir",
  "değişiklik": "change",
  "Dosyayı aç": "Open file",
  "Keep": "Keep",
  "Undo": "Undo",
  "Düzenle": "Edit",
  "Yeniden gönder": "Resend",
  "Yeniden üret": "Regenerate",
  "Devamını göster": "Show more",
  "Daralt": "Collapse",
  " satır": " lines",
  "Durdur": "Stop",
  "Gönder": "Send",
  "Fark okunamadı.": "Could not read the diff.",
  "Diff yok — old/new gelmedi": "No diff — old/new missing",
  "(içerik aynı)": "(unchanged)",
  "dosya": "file",
  "Kartta kaydır": "Scroll in card",
  "Bağlam doluluğu": "Context usage",
  // Goal panel: management
  "Dornick'in kendine yazdığı iş listesi — tıkla: katla/aç":
    "Dornick's own task list — click to fold/unfold",
  " iş listesi": " task list", "İş listesi": "Task list",
  "Aktif madde yok.": "No active items.",
  "İş listesi yok.": "No task list.",
  "Aktif madde yok.": "No active items.",
  "Dornick'nun uzun işlerde kendi yazdığı adım listesi (Cursor görev listesi gibi). Sohbet geçmişi değil — madde yoksa sekme de yok. Sen de ekleyip silebilirsin.":
    "Dornick's step list for long jobs (like Cursor's todo list). Not chat history — no items, no tab. You can add or remove items too.",
  "Dornick'in kendine yazdığı adım listesi — tıkla: katla/aç":
    "Dornick's own step list — click to fold/unfold",
  "Bunlar Dornick'in kendine yazdığı iş listesi — uzun işlerde ne yaptığını takip etmek için. Sen de ekleyebilir, silebilirsin.":
    "This is Dornick's own task list — so you can follow what it is doing on long jobs. You can add and remove items too.",
  "＋ kendi maddeni yaz": "＋ add your own item",
  "Yeni iş maddesi": "New task item", "Ekle": "Add",
  "eski": "old", "Geçen oturumlardan kaldı": "Left over from earlier sessions",
  // "Train now" outcome — never silent, every case gets one plain line
  "Tanıma eğitimi başladı — arka planda sürüyor.":
    "Personal training started — running in the background.",
  "Yeni veri yok — yeni anılar biriktikçe kendiliğinden çalışacak.":
    "No new data — it will run on its own as new memories accumulate.",
  "Eğitim zaten koşuyor.": "Training is already running.",
  "Eğitim düzeneği bu makinede kurulu değil.":
    "The training setup is not installed on this machine.",
  "Beni tanı kapalı — Ayarlar'dan açabilirsin.":
    "Personal training is off — you can turn it on in Settings.",
  "Henüz sırası değil — yeni anılar biriktikçe kendiliğinden çalışacak.":
    "Not due yet — it will run on its own as new memories accumulate.",
  "Eğitim başlatılamadı.": "Could not start training.",
  "Tamamlandı": "Done", "Kaldır": "Remove",
  "tümünü temizle": "clear all", "Emin misin?": "Are you sure?",
  "Bağlam doluluğu — yaklaşık (geçmişten tahmin)":
    "Context usage — approximate (estimated from history)",
  "Kartta kaydır": "Scroll inside the card",
  "Tıkla — adımın ayrıntısını gör": "Click to see the step's detail",
  // Artifact card
  "Yayınlıyor": "Publishing",
  "yayınlandı": "published", "güncellendi": "updated",
  "yeni — indir": "new — download",
  "yeni — güncelle": "new — update",
  "hata": "error",
  "sürümü yayınlandı.": "is available.",
  "İndir ve kur": "Download & install",
  "İndir": "Download",
  "Kapat": "Dismiss",
  "Sağlayıcı: ": "Provider: ",
  "Sağlayıcı seçilmedi": "No provider selected",
  "anahtar yok": "no API key",
  "tıkla: ayarları aç": "click: open settings",
  "Başlamak için iki adım": "Two steps to start",
  "Dornick henüz bir modele bağlanamıyor. Sohbet başlamadan önce bir sağlayıcı seçip anahtarını girmen gerekiyor.":
    "Dornick can't reach a model yet. Pick a provider and enter its API key before chatting.",
  "Sağlayıcıyı seç — OpenRouter, OpenAI, Anthropic ya da LM Studio gibi yerel bir sunucu":
    "Pick a provider — OpenRouter, OpenAI, Anthropic, or a local server like LM Studio",
  "API anahtarını gir ve kaydet (yerel sunucuda anahtar gerekmez)":
    "Enter and save the API key (a local server needs none)",
  "Modeli seç — liste sağlayıcıdan otomatik gelir":
    "Choose the model — the list loads from the provider",
  "Sağlayıcı ve anahtar ayarla": "Set provider and key",
  "Varsayılan uygulamada aç": "Open in the default app",
  "Klasörde göster": "Show in folder",
  "Açılamadı": "Could not open",
  "Yeni sürüm yayınlandı — indirmek için tıkla":
    "A new release is out — click to download",
  "Yeni sürüm yayınlandı — indirip kurmak için tıkla":
    "A new release is out — click to download and install",
  "İndiriliyor": "Downloading",
  "Kurulum açılıyor…": "Opening the installer…",
  "Kurulum açıldı — yönergeleri izle (Dornick kapatılacak)":
    "Installer opened — follow the prompts (Dornick will close)",
  "Güncelleme başlatılamadı": "Could not start the update",
  "Aç": "Open", "Artifact": "Artifact",
  "İndir": "Download", "Yazdır / PDF": "Print / PDF",
  "Tarayıcıda aç": "Open in browser",
  "Gerçek tarayıcıda aç": "Open in your real browser",
  "Adres kopyalandı ✓": "Address copied ✓",
  "Tıkla — sayfayı görüntüleyicide aç": "Click — open page in viewer",
  "Tıkla — sayfayı görüntüleyicide aç": "Click to open the page in the viewer",
  // Goal panel
  "Hedefler": "Goals",
  "Tıkla — katla/aç": "Click to fold or unfold",
  "tamamlandı": "done", "bırakıldı": "dropped",
  // Plan-mode approval loop
  "Planı uygula": "Apply plan",
  "Planı uygula.": "Apply the plan.",
  "Plan hazır — uygulamak yetki ister": "Plan ready — applying needs authority",
  "Plan": "Plan", "Onayla": "Approve", "Düzenle": "Edit", "İptal": "Cancel",
  "Kaydet": "Save", "Vazgeç": "Cancel",
  "Otomasyon olarak kaydet": "Save as automation",
  "Adımları düzenle (satır = adım)": "Edit steps (one per line)",
});

const $ = (id) => document.getElementById(id);
const thread = $("thread"), input = $("input"), overlay = $("overlay");
const statusEl = $("status"), metaEl = $("meta"), stopBtn = $("stop");

let agentLine = null;      // container of the answer being streamed
let busy = false;
let approvalId = null;
let lastQuery = "";

// --- leak defence (second line) -----------------------------------------
//
// The first line is on the server: the hub filters `_payload` internal notes,
// and so does the transcript reader (mind/store.transcript). This second line
// keeps anything one of those filters misses one day away from the user's
// screen — both are proven wounds; the same thing must never hit the screen
// again.
//
// Two patterns are never drawn:
//
//   1. HARNESS NOTE — internal nudges the user did not write ("Planını
//      yazdın ama uygulamadın. Şimdi yap: …", "[Yardımcı bitti · …]").
//      They were seen landing in the chat like user messages; the user
//      reads a sentence that never left their own mouth.
//   2. FAKE TOOL CALL — the model wrote the call XML as PLAIN TEXT instead
//      of making a real tool call. That is not an answer but a failed
//      attempt; the raw XML must not be printed into the chat. (On the loop
//      side the model gets a "make a real tool call" note and the turn
//      continues.)
//
// The patterns are deliberately NARROW: the distinctive openings of the
// internal notes. A broad pattern (e.g. every square bracket) would swallow
// the user's own sentence.

const INTERNAL_NOTE_PATTERNS = [
  /^\s*\[(Harness notu|Yardımcı|Arka plan işi|Kullanıcı bu arada yazdı|Ana ajandan|Uzun koşu kontrol noktası)/,
  /^\s*Planını yazdın ama uygulamadın/,
  /^\s*Önceki yanıtın uzunluk sınırında kesildi/,
  /^\s*Sürdürme hakkın bitti/,
  /^\s*Yukarıdaki görüntü senin kendi bakışın/,
  /^\s*Arka plandaki yardımcı\(lar\) bitti/,
  /^\s*Kameradan bir kare\. Gerçekten bak/,
];

// Tool-call XML: appearing anywhere in the text is enough — the model
// usually writes a sentence or two first and only then slides into XML.
const FAKE_CALL_PATTERN = /<\/?(function_calls|invoke\b|parameter\b|antml:)/i;

function isInternalNote(text) {
  const s = String(text || "");
  return INTERNAL_NOTE_PATTERNS.some((k) => k.test(s));
}

function fakeCall(text) {
  return FAKE_CALL_PATTERN.test(String(text || ""));
}

// Should the user line be drawn? Not if it is an internal note — swallowed silently.
function drawable(text) {
  return !isInternalNote(text) && !fakeCall(text);
}

Scene.init({
  canvas: $("scene"), probe: $("probe"), reveal: $("reveal"),
  onRoute: renderRoute,
  // Double-clicking a memory / "Go to conversation" on the card switches to
  // the session the memory was born in — same path as the click in the
  // history panel (waits if busy).
  onSession: (id) => { if (typeof History !== "undefined") History.resumeById(id); },
});
Scene.load();
// Brain regions (Phase 6): the template around the network and the night
// feed. Live watching starts with the page; the sheet's "Gece" tab replays.
if (typeof Regions !== "undefined") Regions.init();
if (typeof Night !== "undefined") Night.watch(true);

Lang.add({ "Açıklama ▸": "Key ▸", "Açıklama ▾": "Key ▾" });

// --- context tools ⋮ menu ------------------------------------------------
(() => {
  const button = $("more-tools"), box = $("more-pop");
  if (!button || !box) return;
  button.addEventListener("click", (ev) => {
    ev.stopPropagation();
    box.hidden = !box.hidden;
  });
  box.addEventListener("click", () => { box.hidden = true; });
  document.addEventListener("click", () => { box.hidden = true; });
})();

// --- brain panel open/close ----------------------------------------------
// The right column is the brand layer; closing it means focus. The choice is
// remembered. While closed the canvas is hidden too (display:none) and scene
// drawing stops — animating an invisible scene is battery burnt for nothing.
(() => {
  const uygula = (on) => {
    document.body.classList.toggle("mind-on", on);
    document.body.classList.toggle("mind-off", !on);
    try { localStorage.setItem("dornick-mind", on ? "acik" : "kapali"); } catch { /* file:// */ }
    if (on) Scene.resume(); else Scene.pause();
  };
  let saved = null;
  try { saved = localStorage.getItem("dornick-mind"); } catch { /* file:// */ }
  uygula(saved !== "kapali");
  // Should the brain grow in the CENTRE (ambient)? Managed from Settings;
  // when off the brain stays in the right panel and the centre scene dims —
  // "the text disappears under the brain" (live request, 31.08).
  try {
    if (localStorage.getItem("dornick-brain-ambient") === "kapali")
      document.body.classList.add("no-ambient");
  } catch { /* file:// */ }
  window.brainCentered = (on) => {
    document.body.classList.toggle("no-ambient", !on);
    try { localStorage.setItem("dornick-brain-ambient", on ? "acik" : "kapali"); } catch {}
  };
  $("mind-close").addEventListener("click", () => uygula(false));
  // ◍ is now a two-way switch: no floating header (›) in ambient mode; this
  // is the permanent place to close and open the brain.
  $("mind-open").addEventListener("click", () =>
    uygula(document.body.classList.contains("mind-off")));
  // Memory search: matching nodes glow, the rest dim. When the box empties
  // the scene returns to normal.
  const search = $("mind-search");
  search.addEventListener("input", () => Scene.search(search.value));

  // The legend folds; default CLOSED ("it hogged a huge amount of space").
  const chips = $("legend-toggle");
  const applyLegend = (on) => {
    Scene.legend(on);
    chips.classList.toggle("on", on);
    chips.textContent = on ? t("Açıklama ▾") : t("Açıklama ▸");
    try { localStorage.setItem("dornick-legend", on ? "acik" : "kapali"); } catch { /* file:// */ }
  };
  let leg = null;
  try { leg = localStorage.getItem("dornick-legend"); } catch { /* file:// */ }
  applyLegend(leg === "acik");
  chips.addEventListener("click", () =>
    applyLegend(!chips.classList.contains("on")));

  // Restore the saved panel width / desk-brain split on startup.
  try {
    const w = parseInt(localStorage.getItem("dornick-mind-w") || "", 10);
    // If an old/corrupt record crushes the chat: ignore it. (Same ceiling as the grip: 760.)
    if (w >= 240 && w <= 760) {
      document.documentElement.style.setProperty("--mind-w-user", w + "px");
    } else if (Number.isFinite(w)) {
      try { localStorage.removeItem("dornick-mind-w"); } catch { /* */ }
      document.documentElement.style.removeProperty("--mind-w-user");
    }
    const dh = localStorage.getItem("dornick-dock-h");
    if (dh && /^\d+(\.\d+)?%$/.test(dh)) {
      document.documentElement.style.setProperty("--dock-h-user", dh);
    }
    const vh = localStorage.getItem("dornick-viewer-h");
    if (vh && /^\d+(\.\d+)?%$/.test(vh)) {
      document.documentElement.style.setProperty("--viewer-h-user", vh);
    }
    if (localStorage.getItem("dornick-mind-front") === "1") {
      document.body.classList.add("mind-front");
    }
  } catch { /* file:// */ }

  // Brain tag: with the desk open, clicking brings the brain forward / back.
  const tag = document.querySelector(".mind-tag");
  if (tag) {
    tag.style.cursor = "pointer";
    tag.title = t("Beyni öne al / geri");
    tag.addEventListener("click", () => {
      const on = document.body.classList.toggle("mind-front");
      try { localStorage.setItem("dornick-mind-front", on ? "1" : "0"); } catch { /* file:// */ }
    });
  }
})();

// Resize the brain panel by dragging its left edge — mirror of the left
// rail grip. The width is remembered.
(() => {
  const grip = $("mind-grip");
  if (!grip) return;
  const root = document.documentElement;
  let active = false;
  const onMove = (ev) => {
    if (!active) return;
    // The 420 ceiling turned the pane into a prison: with the default width
    // already 420 the panel could ONLY shrink ("it can't be resized, only
    // shrunk" — live, 31.08). The ceiling went up to half the screen.
    const max = Math.min(760, window.innerWidth * 0.55);
    const w = Math.max(240, Math.min(max, window.innerWidth - ev.clientX));
    root.style.setProperty("--mind-w-user", w + "px");
  };
  const stop = () => {
    if (!active) return;
    active = false;
    document.body.classList.remove("mind-resize");
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", stop);
    try {
      const w = parseInt(getComputedStyle(root).getPropertyValue("--mind-w-user"), 10);
      if (w) localStorage.setItem("dornick-mind-w", String(w));
    } catch { /* file:// */ }
  };
  grip.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    active = true;
    // Capture the pointer: even when the mouse escapes the window / over an
    // iframe, the release event comes to US. Without capture pointerup was
    // missed and the panel kept growing and shrinking with every mouse move
    // (live complaint).
    try { grip.setPointerCapture(ev.pointerId); } catch { /* old engine */ }
    document.body.classList.add("mind-resize");
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    window.addEventListener("blur", stop);
  });
})();

// Desk ↔ brain (or brain ↔ orchestra) vertical grip. The width grip spans
// the whole column; this one only splits the height.
(() => {
  const grip = $("dock-grip");
  const col = $("right-col");
  if (!grip || !col) return;
  const root = document.documentElement;
  const MIN_TOP = 120;
  const MIN_BOT = 140;
  const GRIP = 8;
  let active = false;

  const viewingSplit = () =>
    document.body.classList.contains("viewing") &&
    !document.body.classList.contains("mind-off");

  const apply = (clientY) => {
    const box = col.getBoundingClientRect();
    if (box.height < MIN_TOP + MIN_BOT + GRIP) return;
    if (viewingSplit()) {
      // Top = desk: dragging the grip down grows the desk.
      const maxTop = box.height - MIN_BOT - GRIP;
      const px = Math.max(MIN_TOP, Math.min(maxTop, clientY - box.top));
      const pct = ((px / box.height) * 100).toFixed(1) + "%";
      root.style.setProperty("--viewer-h-user", pct);
      document.body.classList.remove("mind-front");
      return pct;
    }
    // Orchestra: height from the bottom (old behaviour).
    const maxDock = box.height - MIN_BOT - GRIP;
    const px = Math.max(MIN_TOP, Math.min(maxDock, box.bottom - clientY));
    const pct = ((px / box.height) * 100).toFixed(1) + "%";
    root.style.setProperty("--dock-h-user", pct);
    return pct;
  };
  const onMove = (ev) => { if (active) apply(ev.clientY); };
  const stop = () => {
    if (!active) return;
    active = false;
    document.body.classList.remove("dock-resize");
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", stop);
    window.removeEventListener("pointercancel", stop);
    window.removeEventListener("blur", stop);
    try {
      if (viewingSplit()) {
        const v = getComputedStyle(root).getPropertyValue("--viewer-h-user").trim();
        if (v) localStorage.setItem("dornick-viewer-h", v);
        localStorage.setItem("dornick-mind-front", "0");
      } else {
        const v = getComputedStyle(root).getPropertyValue("--dock-h-user").trim();
        if (v) localStorage.setItem("dornick-dock-h", v);
      }
    } catch { /* file:// */ }
  };
  grip.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    active = true;
    try { grip.setPointerCapture(ev.pointerId); } catch { /* old engine */ }
    document.body.classList.add("dock-resize");
    apply(ev.clientY);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    window.addEventListener("blur", stop);
  });
  grip.addEventListener("dblclick", () => {
    if (viewingSplit()) {
      root.style.removeProperty("--viewer-h-user");
      try { localStorage.removeItem("dornick-viewer-h"); } catch { /* file:// */ }
    } else {
      root.style.removeProperty("--dock-h-user");
      try { localStorage.removeItem("dornick-dock-h"); } catch { /* file:// */ }
    }
  });
})();

// Returns the response: some calls (authority change) have to check whether
// the server accepted.
const post = async (path, body) => {
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
    return await response.json();
  } catch {
    return null;
  }
};

function clearWelcome() {
  const welcome = $("welcome");
  if (welcome) welcome.remove();
}

// Bring the welcome back in a fresh session: switching to a new conversation
// left the thread completely empty ("opened a new chat, blank screen"). Does
// not add it again if it is already there.
function showWelcome() {
  if ($("welcome")) return;
  const w = document.createElement("div");
  w.className = "welcome";
  w.id = "welcome";
  const h = document.createElement("h1");
  h.textContent = t("Ne yapmamı istersin?");
  const p = document.createElement("p");
  p.textContent = t("Bilgisayarında çalışıyorum. Öğrendiklerim etrafımdaki ağa yazılıyor.");
  const note = document.createElement("p");
  note.className = "wake-note";
  note.id = "wake-note";
  note.hidden = true;
  w.append(h, p, note);
  thread.append(w);
  // If the agent still cannot run (no key) the setup card comes with the welcome.
  if (modelKnown && !canRun) showSetupGuide();
}

// --- first-run guidance --------------------------------------------------
// With no provider/model connected the screen stayed silent: the user typed
// what they wanted, no answer came, and the reason was invisible (user
// request, 01.09). The welcome now carries a clear card: what is missing and
// where to complete it — one click opens Settings › Model.
let modelKnown = false;

// Step-by-step setup card: the user should see what to do IN ORDER.
// Previously only "is the model name empty" was checked; since the app ships
// with a default model ("oto") the card never showed, and on a keyless
// install the screen stayed silent — the user understood nothing until they
// typed a message (live wound, 02.09). The gate is now `can_run`: is there
// actually a key?
function showSetupGuide() {
  if ($("setup-guide")) return;
  const card = document.createElement("div");
  card.className = "setup-guide";
  card.id = "setup-guide";
  const heading = document.createElement("h2");
  heading.textContent = t("Başlamak için iki adım");
  const text = document.createElement("p");
  text.textContent = t(
    "Dornick henüz bir modele bağlanamıyor. Sohbet başlamadan önce bir "
    + "sağlayıcı seçip anahtarını girmen gerekiyor.");

  // Numbered steps: make the order clear (provider+key first, then model).
  const steps = document.createElement("ol");
  steps.className = "setup-steps";
  for (const [n, s] of [
    ["1", t("Sağlayıcıyı seç — OpenRouter, OpenAI, Anthropic ya da LM Studio gibi yerel bir sunucu")],
    ["2", t("API anahtarını gir ve kaydet (yerel sunucuda anahtar gerekmez)")],
    ["3", t("Modeli seç — liste sağlayıcıdan otomatik gelir")],
  ]) {
    const li = document.createElement("li");
    li.textContent = s;
    li.dataset.n = n;
    steps.append(li);
  }

  const button = document.createElement("button");
  button.type = "button";
  button.className = "setup-guide-btn";
  button.textContent = t("Sağlayıcı ve anahtar ayarla");
  button.onclick = () => { if (typeof Settings !== "undefined") Settings.open("model"); };
  card.append(heading, text, steps, button);
  const w = $("welcome");
  if (w) w.append(card); else thread.append(card);
}

function hideSetupGuide() {
  const card = $("setup-guide");
  if (card) card.remove();
}

// Thin bridge for the working-folder strip (workdir.js): loadState calls
// from here, the module does the drawing.
function setWorkdir(project, workspace) {
  if (typeof WorkDir !== "undefined") WorkDir.draw(project, workspace);
}

// --- smart scrolling ----------------------------------------------------
//
// The old version jumped to the bottom on every event — even while the user
// was reading an older answer above. The rule is simple: if the user is at
// the bottom (or very close) the follow continues; once they scroll up the
// auto-descent STOPS and a "↓ N new" button appears bottom-right. Clicking
// it (or scrolling to the bottom themselves) restores the follow. Every
// scroll goes through this single gate.

const NEAR_BOTTOM = 120;   // within this many pixels counts as "at the bottom"
let follow = true;         // is auto-follow on
let fresh = 0;             // new blocks arrived while follow was off
let seenBlocks = 0;        // comparison baseline for the counter
let transcriptBatch = false;  // no scrolling while painting history

const atBottom = () =>
  thread.scrollHeight - thread.scrollTop - thread.clientHeight < NEAR_BOTTOM;

function scroll() {
  if (transcriptBatch) return;
  const blocks = thread.childElementCount;
  if (follow) { thread.scrollTop = thread.scrollHeight; seenBlocks = blocks; return; }
  // Follow off: no descending. Count only new top-level blocks — each
  // redraw of the same answer must not inflate the counter.
  if (blocks > seenBlocks) { fresh += blocks - seenBlocks; seenBlocks = blocks; }
  paintJump();
}

function paintJump() {
  const button = $("jump");
  button.hidden = follow;
  // While busy the chip also carries the live verb: a user scrolled up in a
  // long stream reads "where are we / what is happening" here and returns to
  // the live tip with one click ("it says writing but it writes below,
  // I don't know where I am").
  if (!follow) {
    const live = busy ? mull() + " · " : "";
    button.textContent = live + (fresh ? "↓ " + fresh + t(" yeni") : "↓");
  }
}

function resumeFollow(smooth) {
  follow = true;
  fresh = 0;
  seenBlocks = thread.childElementCount;
  if (smooth) thread.scrollTo({ top: thread.scrollHeight, behavior: "smooth" });
  else thread.scrollTop = thread.scrollHeight;
  paintJump();
}

thread.addEventListener("scroll", () => {
  const was = follow;
  follow = atBottom();
  if (follow) { fresh = 0; seenBlocks = thread.childElementCount; }
  if (was !== follow) paintJump();
});

document.getElementById("jump").addEventListener("click", () => resumeFollow(true));

// When the strip / thought opens, rescue it from under the composer (z:25).
// Opened near the bottom the body stretched BEHIND the input; when the
// max-height CSS (52vh) exceeded the visible gap only a 1-2 px sliver
// remained ("it opens but it's tiny" — live, 01.09). Fix: fit the height
// above the composer + pull the strip header to the top of the visible area.
function revealAboveComposer(el) {
  if (!el || !thread.contains(el)) return;
  const go = () => {
    const shell = document.getElementById("compose-shell");
    const shellTop = shell ? shell.getBoundingClientRect().top : window.innerHeight;
    const streamBox = thread.getBoundingClientRect();
    const pad = 20;
    const avail = Math.max(160, Math.floor(shellTop - streamBox.top - pad));
    // Open thought / strip body: lock the ceiling to the visible room.
    if (el.classList.contains("acts-body") || el.classList.contains("think")) {
      const cap = el.classList.contains("think") ? 480 : 520;
      el.style.maxHeight = Math.min(avail, cap) + "px";
    }
    const head = el.classList.contains("acts-body")
      && el.previousElementSibling
      && el.previousElementSibling.classList.contains("acts-head")
      ? el.previousElementSibling
      : null;
    const topEl = head || el;
    // Pin the header (or the box) to the top of the chat's visible area —
    // keep a readable height like Cursor's thought panel.
    const wantTop = streamBox.top + 10;
    const tr = topEl.getBoundingClientRect();
    if (Math.abs(tr.top - wantTop) > 4) thread.scrollTop += tr.top - wantTop;
    const r = el.getBoundingClientRect();
    if (r.bottom > shellTop - 12) {
      thread.scrollTop += r.bottom - (shellTop - 12);
    }
  };
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      go();
      requestAnimationFrame(go);
    });
  });
}

function clearFitAboveComposer(el) {
  if (el && el.style) el.style.maxHeight = "";
}

function line(kind, text) {
  clearWelcome();
  // Long / technical alerts must not become a yellow wall like an answer:
  // one-line summary, raw text on click. Short notices stay plain.
  if (kind === "alert" && text && shouldFoldAlert(text)) {
    return alertFold(text);
  }
  const el = document.createElement("div");
  el.className = "line " + kind;
  // A long paste (code, log, document) must not swallow the chat: it arrives
  // folded and opens via "Devamını göster" (Claude Code's show more). The raw
  // text lives in _rawText — Edit/Resend keep working as-is.
  if (kind === "user" && text
      && (text.length > 800 || text.split("\n").length > 14)) {
    el._rawText = String(text);
    const rowCount = text.split("\n").length;
    const clip = document.createElement("div");
    clip.className = "msg-clip";
    clip.textContent = text;
    const more = document.createElement("button");
    more.type = "button";
    more.className = "msg-more";
    const paint = () => {
      const open = el.classList.contains("open");
      more.textContent = open ? t("Daralt")
        : t("Devamını göster") + " · " + rowCount + t(" satır");
    };
    more.addEventListener("click", () => { el.classList.toggle("open"); paint(); scroll(); });
    paint();
    el.append(clip, more);
    attachMsgActs(el, kind);
    thread.append(el);
    scroll();
    return el;
  }

  // Consecutive model chunks within the same turn should read as ONE message:
  // if the last speaker was the model again, this chunk is a "continuation" —
  // the "Dornick" header and the big gap do not repeat. The text is still IN
  // THE CHAT and visible (no folding); only the visual staircase is broken.
  if (kind === "agent") {
    // Walk backwards from the end: the old version copied the whole list on
    // every line ([...children].reverse()) — O(n²) while loading a huge
    // transcript, one of the things that froze the switch.
    let speaker = thread.lastElementChild;
    while (speaker && !(speaker.classList && speaker.classList.contains("line")
      && (speaker.classList.contains("agent") || speaker.classList.contains("user")))) {
      speaker = speaker.previousElementSibling;
    }
    if (speaker && speaker.classList.contains("agent")) el.classList.add("cont");
  }
  if (text) el.textContent = text;
  if (kind === "user" || kind === "agent") {
    if (text) el._rawText = String(text);
    attachMsgActs(el, kind);
  }
  thread.append(el);
  scroll();
  return el;
}

function attachMsgActs(el, kind) {
  const old = el.querySelector(".msg-acts");
  if (old) old.remove();
  const acts = document.createElement("div");
  acts.className = "msg-acts";
  if (kind === "user") {
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "msg-act";
    edit.textContent = t("Düzenle");
    edit.onclick = (ev) => {
      ev.stopPropagation();
      const raw = el._rawText || el.textContent || "";
      input.value = raw;
      input.focus();
      input.dispatchEvent(new Event("input"));
    };
    const resend = document.createElement("button");
    resend.type = "button";
    resend.className = "msg-act";
    resend.textContent = t("Yeniden gönder");
    resend.onclick = (ev) => {
      ev.stopPropagation();
      if (busy || !ready) return;
      const raw = (el._rawText || el.textContent || "").trim();
      if (!raw) return;
      post("/api/chat", { text: raw });
      resumeFollow(false);
    };
    acts.append(edit, resend);
  } else {
    // "Regenerate" only sits on the LAST agent bubble. Piling up under every
    // interim narration in a long run was noise ("every message says
    // regenerate" — live transcript); its meaning is "regenerate the last
    // answer" anyway. When a new agent bubble is born, the older ones lose it.
    for (const stale of thread.querySelectorAll(".line.agent .msg-acts")) {
      if (stale.parentElement !== el) stale.remove();
    }
    const regen = document.createElement("button");
    regen.type = "button";
    regen.className = "msg-act";
    regen.textContent = t("Yeniden üret");
    regen.onclick = (ev) => {
      ev.stopPropagation();
      if (busy || !ready) return;
      let prev = el.previousElementSibling;
      while (prev && !prev.classList.contains("user")) prev = prev.previousElementSibling;
      const raw = prev && (prev._rawText || prev.textContent || "").trim();
      if (!raw) return;
      post("/api/chat", { text: raw });
      resumeFollow(false);
    };
    acts.append(regen);
  }
  el.append(acts);
}

function shouldFoldAlert(text) {
  const s = String(text || "");
  if (s.length > 110) return true;
  return /Error code|BadRequest|Traceback|Exception|error['"]?\s*:/i.test(s);
}

function alertFold(text) {
  const el = document.createElement("div");
  el.className = "line alert folded";
  const head = document.createElement("button");
  head.type = "button";
  head.className = "alert-head";
  head.textContent = summarizeAlert(text);
  head.title = t("Tıkla — ayrıntıyı gör");
  const body = document.createElement("pre");
  body.className = "alert-detail";
  body.hidden = true;
  body.textContent = text;
  head.onclick = () => {
    const open = body.hidden;
    body.hidden = !open;
    head.classList.toggle("open", open);
    el.classList.toggle("open", open);
    scroll();
  };
  el.append(head, body);
  thread.append(el);
  scroll();
  return el;
}

function summarizeAlert(text) {
  const s = String(text || "").trim();
  // [channel] message — subagent
  const tagged = s.match(/^\[([^\]]+)\]\s*(.*)$/s);
  if (tagged) {
    const title = tagged[1];
    const rest = (tagged[2] || "").trim();
    const msg = rest.match(/'message':\s*'([^']+)'/)
      || rest.match(/"message"\s*:\s*"([^"]+)"/);
    if (msg) return "⚠ " + title + " · " + msg[1];
    const err = rest.match(/^(\w+Error)\b/);
    if (err) return "⚠ " + title + " · " + err[1];
    const one = rest.split("\n")[0].trim();
    return "⚠ " + title + (one ? " · " + (one.length > 72 ? one.slice(0, 72) + "…" : one) : "");
  }
  const msg = s.match(/'message':\s*'([^']+)'/) || s.match(/"message"\s*:\s*"([^"]+)"/);
  if (msg) return "⚠ " + msg[1];
  const one = s.split("\n")[0].trim();
  return "⚠ " + (one.length > 96 ? one.slice(0, 96) + "…" : one);
}

// Prints the past transcript of a resumed conversation into the thread: the
// user sees where they left off and new messages append there.
//
// Never drawn TWICE for the same session: session_reset calls this directly
// AND via loadState (the snapshot also calls it on page refresh) — when both
// ran, every message showed up twice on screen (live wound, 31.08:
// "reopening the conversation shows the same exchanges twice").
let transcriptFor = "";

// Max turns drawn on open: printing a huge chat to markdown in one go locked
// the screen for seconds (live wound, 01.09: "it freezes when I open the
// other chat"). Older turns come on demand via "Daha eskiyi göster".
const TRANSCRIPT_LAST = 80;

async function loadTranscript(id) {
  if (id && transcriptFor === id) return;
  transcriptFor = id || "";
  let data;
  try { data = await (await fetch("/api/session?id=" + encodeURIComponent(id))).json(); }
  catch { transcriptFor = ""; return; }
  // The chat may have CHANGED during the wait: on two quick clicks the old
  // transcript's response streamed onto the new screen (a mixing race). The
  // id is now checked at every step; on mismatch drawing is silently dropped.
  if (transcriptFor !== id) return;
  const turns = (data.turns || []).filter(
    (t) => drawable(t.text) || (t.adimlar && t.adimlar.length) || t.dusunme);
  const start = Math.max(0, turns.length - TRANSCRIPT_LAST);
  transcriptBatch = true;
  const prevFollow = follow;
  follow = false;
  try {
    if (start > 0) transcriptOlderButton(id, turns, start);
    for (let i = start; i < turns.length; i++) {
      if (transcriptFor !== id) return;   // switched away: stop drawing the rest
      transcriptTurn(turns[i]);
      if (i > start && (i - start) % 6 === 0) {
        await new Promise((r) => requestAnimationFrame(() => r()));
      }
    }
  } finally {
    transcriptBatch = false;
    follow = prevFollow;
  }
  scroll();
  if (busy) {
    if (work) dockWork(work);
    kickWork();
    scroll();
  }
}

// Prints one turn into the thread — same pieces as the live drawing: user
// bubble (with media chips); on an assistant turn first the trace strip
// (thinking + steps), then the markdown body. If `before` is given, the new
// nodes are moved IN FRONT of that node ("show older" prepends to the
// existing transcript).
function transcriptTurn(turn, before) {
  const last = thread.lastElementChild;
  if (turn.role === "user") {
    const el = line("user", turn.text);
    reviveUserMedia(el, turn.text || "");
  } else {
    if (turn.dusunme || (turn.adimlar && turn.adimlar.length)) historyStrip(turn);
    if (drawable(turn.text)) {
      const el = line("agent", "");
      el._rawText = turn.text || "";
      Markdown.into(el, turn.text || "");
      attachMsgActs(el, "agent");
      el.classList.add("done");
    }
  }
  if (before) {
    let n = last ? last.nextElementSibling : thread.firstElementChild;
    while (n) { const next = n.nextElementSibling; thread.insertBefore(n, before); n = next; }
  }
}

// "Show older": the trimmed head section renders on one click, again in
// batches — prepended ON TOP of the existing transcript.
function transcriptOlderButton(id, turns, count) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "msg-more transcript-older";
  button.textContent = t("Daha eskiyi göster") + " · " + count + t(" tur");
  button.onclick = async () => {
    button.disabled = true;
    transcriptBatch = true;
    try {
      for (let i = 0; i < count; i++) {
        if (transcriptFor !== id) return;
        transcriptTurn(turns[i], button);
        if (i > 0 && i % 6 === 0) {
          await new Promise((r) => requestAnimationFrame(() => r()));
        }
      }
    } finally {
      transcriptBatch = false;
    }
    button.remove();
  };
  thread.append(button);
}

// The trace strip of a past turn: same classes as the live strip
// (acts-head/acts-body) but static — no pulse, no live counter. The header
// is "N steps"; clicking opens the body: folded thinking line + step rows.
function historyStrip(turn) {
  const head = document.createElement("div");
  head.className = "acts-head";
  const body = document.createElement("div");
  body.className = "acts-body";
  body.hidden = true;

  const verb = document.createElement("span");
  verb.className = "head-verb";
  const stepCount = (turn.adimlar || []).length;
  verb.textContent = stepCount ? stepsWord(stepCount) : t("Düşündü");
  head.append(verb);
  head.onclick = () => {
    if (!body.childElementCount) return;
    body.hidden = !body.hidden;
    head.classList.toggle("open", !body.hidden);
  };

  if (turn.dusunme) {
    const think = document.createElement("div");
    think.className = "act note think done";
    const words = turn.dusunme.split(/\s+/).length;
    const label = t("✻ Düşündü") + " · " + words + t(" kelime");
    think.textContent = label;
    think.title = t("Tıkla — bu turun muhakemesini gör");
    let open = false;
    think.onclick = (ev) => {
      ev.stopPropagation();
      open = !open;
      think.textContent = open ? turn.dusunme : label;
      think.classList.toggle("open", open);
    };
    body.append(think);
  }
  for (const step of (turn.adimlar || [])) {
    const row = document.createElement("div");
    row.className = "act ok";
    const spark = document.createElement("span");
    spark.className = "spark";
    spark.textContent = TOOL_ICON[step.tool] || "·";
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = verbFor(step.tool) || step.tool;
    who.title = step.tool;
    const what = document.createElement("span");
    what.className = "what";
    what.textContent = step.ozet || "";
    what.title = step.ozet || "";
    if (CODE_TOOLS.has(step.tool)) { row.dataset.kod = "1"; what.classList.add("kod"); }
    row.append(spark, who, what);
    body.append(row);
  }
  thread.append(head, body);
}

// History used to show only paths; chip + image preview like the live view.
const IMG_EXT = /\.(png|jpe?g|gif|webp|bmp|svg)$/i;
function reviveUserMedia(row, text) {
  if (!row || !text) return;
  const paths = [];
  const attach = text.match(/Eklenen dosyalar \(atölyende\):\n((?:[-•]\s+.+\n?)+)/i);
  if (attach) {
    for (const row2 of attach[1].split("\n")) {
      const path = row2.replace(/^[-•]\s+/, "").trim();
      if (path) paths.push(path);
    }
  }
  for (const m of text.matchAll(/Kullanıcı şu dosyayı işaret etti:\s*(.+)/gi)) {
    const path = (m[1] || "").trim();
    if (path && !paths.includes(path)) paths.push(path);
  }
  if (!paths.length) return;
  const files = [];
  let frame = "";
  for (const path of paths) {
    const name = path.split(/[\\/]/).pop() || path;
    files.push(name);
    if (!frame && IMG_EXT.test(path)) {
      frame = "/api/raw?path=" + encodeURIComponent(path.replace(/\\/g, "/"));
    }
  }
  attachMedia(row, { frame, files });
  row.querySelectorAll(".msg-file").forEach((chip, i) => {
    const path = paths[i];
    if (!path) return;
    chip.style.cursor = "pointer";
    chip.title = path;
    chip.addEventListener("click", () => {
      if (typeof Viewer !== "undefined" && Viewer.present) Viewer.present(path);
    });
  });
}

function setStatus(state, label) {
  statusEl.className = "status " + state;
  statusEl.querySelector("b").textContent = label;
}

// --- waking up ----------------------------------------------------------
//
// Talking before the model is loaded is pointless: what you type goes
// unanswered. Until it is ready the input line stays disabled and the scene
// dim; once ready the core comes alive.

let ready = false;

function setWaking(stage, done) {
  ready = !!done;
  document.body.classList.toggle("waking", !ready);
  Scene.setMode(ready ? "idle" : "waking");
  const label = stage || (ready ? t("Hazır") : t("Uyanıyor"));
  setStatus(ready ? "ready" : "busy", label);

  input.disabled = !ready;
  input.placeholder = ready ? t("Konuş…") : label + "…";
  $("send").disabled = !ready;
  paintWakeNote(ready ? "" : label);
  if (ready) input.focus();
}

// On startup / while the model loads, a live line under the welcome — not
// just a pale composer; the user must not think "it froze".
function paintWakeNote(text) {
  let note = $("wake-note");
  if (!text) {
    if (note) { note.hidden = true; note.textContent = ""; }
    return;
  }
  if (!note) {
    note = document.createElement("p");
    note.className = "wake-note";
    note.id = "wake-note";
    const host = $("welcome");
    if (host) host.append(note);
    else {
      note.classList.add("solo");
      thread.prepend(note);
    }
  }
  note.hidden = false;
  note.textContent = text;
}

// The send button becomes STOP while running (Claude Code): ■ when the box
// is empty, still → when there is text (a message sent while busy queues).
function paintSend() {
  const g = $("send");
  const stop = busy && !input.value.trim();
  g.classList.toggle("stop", stop);
  g.textContent = stop ? "■" : "→";
  g.title = stop ? t("Durdur") : t("Gönder");
  g.setAttribute("aria-label", stop ? t("Durdur") : t("Gönder"));
}

function setBusy(value) {
  // Turn start: nothing has streamed yet. The waiting() countdown says
  // "Model yanıtı bekleniyor…" only while this flag is low — the header lying
  // "loading" through long tool-running stretches was a live wound.
  if (value && !busy) turnActivity = false;
  busy = value;
  // The brand node knits and unknits while work runs (CSS knot-knit).
  document.body.classList.toggle("mesgul", value);
  stopBtn.hidden = !value;
  paintSend();
  // The button locks only while busy. send() already rejects empty text;
  // tying the lock to text presence left the button locked when the value
  // changed programmatically (paste, autofill, IME). Typing while busy is
  // fine too: the sent message joins the queue.
  $("send").disabled = !ready;
  setMode(value ? "thinking" : "idle");
  waiting(value);
  // The live "alive" counter runs for as long as we are busy, stops after.
  if (value) {
    startBusyTicker();
    // Thread line at turn start — no gap until the first delta arrives.
    kickWork();
  } else {
    stopBusyTicker();
    // tool_end can be lost on an interrupt: the glow dies with the turn, always.
    controlGlowCount = 0;
    document.body.classList.remove("kontrol-canli");
    sealLine();
    // The plan card goes UNDER the turn's text: seal the text first, then the card.
    flushDeferredPlans();
  }
}

// Control glow: while Dornick uses the hand/screen tools the window edge
// pulses — "it is using the computer right now" at a glance (user request,
// 31.08: like Claude's screen frame). Counted: nested calls must not fade it
// early; when the turn ends it goes out no matter what.
let controlGlowCount = 0;
function controlGlow(delta) {
  controlGlowCount = Math.max(0, controlGlowCount + delta);
  document.body.classList.toggle("kontrol-canli", controlGlowCount > 0);
}

// While busy the strip immediately shows "Düşünüyor · N sn". Called from
// setBusy and from the user message (if busy came first, sealLine removes
// the empty strip).
function kickWork() {
  if (!busy) return;
  const w = ensureWork();
  w.head.classList.add("busy");
  if (waitState) { paintWait(); return; }
  if (!paintLive()) workHead(mull(), "", since(w.since) + streamNote());
  scroll();
}

// Single source for the scene and the status line. The busy/idle pair made
// every job look the same — thinking and reading a file were identical.
const MODE_LABEL = {
  waking: "Uyanıyor", idle: "Hazır", thinking: "Düşünüyor",
  writing: "Yazıyor", recalling: "Hatırlıyor", working: "Çalışıyor"
};

// "working" said too little while a tool ran: writing a file and searching,
// watching the screen and reading a PLC all looked alike. Every tool maps to
// an action — shown under the core (like Claude Code's "Creating /
// Researching" status; the colour comes from the mode too).
const ACTION = {
  search: "Araştırıyor", fetch: "Araştırıyor", web: "Araştırıyor",
  grep: "Arıyor", semboller: "Arıyor",
  read_file: "Okuyor", read_many: "Okuyor", list_dir: "Bakıyor", write_file: "Oluşturuyor",
  edit_file: "Düzenliyor", copy_in: "Kopyalıyor", draw: "Çiziyor",
  shell: "Çalıştırıyor",
  mind_recall: "Hatırlıyor", mind_memory: "Aklına yazıyor", mind_goals: "Planlıyor",
  screen: "Ekrana bakıyor", hand: "Bilgisayarı kullanıyor", look: "Bakıyor",
  browser: "İnternette geziniyor",
  device: "Cihaza bağlanıyor", skill: "Yetenek yazıyor", models: "Model seçiyor",
  task: "Yardımcı çalıştırıyor", schedule: "Zamanlıyor",
  mail_read: "Posta okuyor", mail_send: "Posta gönderiyor", place: "Konuma bakıyor",
  artifact: "Yayınlıyor",
  git: "Git",
};

// The tool row's icon. Not model-picked; the kind maps statically: the
// icon's job is not decoration but telling kinds apart while scanning rows.
const TOOL_ICON = {
  shell: "❯", read_file: "≡", read_many: "≡", list_dir: "≡", write_file: "✎", edit_file: "✎",
  copy_in: "✎", draw: "✎", search: "◌", fetch: "◌", web: "◌", grep: "◌", semboller: "◌",
  mind_recall: "◍", mind_memory: "◍", mind_goals: "◍",
  screen: "▣", hand: "▣", look: "◉", browser: "⌾", device: "⇄", skill: "✦",
  models: "✦", task: "⑃", schedule: "◔", mail_read: "✉", mail_send: "✉",
  place: "⌖", artifact: "⬒", git: "⌥",
};

// Rotating thinking words. No AI involved — the next one from a fixed list
// every few seconds; zero cost, yet it carries most of the perceived
// "aliveness". The state is MODELLED, not decorated (live complaint: "it
// keeps flipping between thinking, tinkering — these should be real metas").
// The label derives from what is REALLY happening and does not change until
// the state does: reasoning channel streaming → "Akıl yürütüyor", answer
// text streaming → "Yazıyor", nothing streaming yet → "Düşünüyor" (if it
// drags on, waiting() already says "Model yükleniyor…"). While a tool runs
// the label comes from ACTION — also real: the tool itself.
let mullTick = 0;      // old name: the since() counter reads this
let lastDelta = "";    // "" | "thinking" | "text" — last channel that streamed
let turnSeed = 0;      // action synonyms are gone; kept as a turn counter

function mull() {
  if (lastDelta === "text") return t("Yazıyor");
  if (lastDelta === "thinking") return t("Akıl yürütüyor");
  return t("Düşünüyor");
}

// Synonyms for the action heading. The definition lives in ACTION (single
// truth — icon and organ mapping come from there); the variety here is
// display-time only. Stable within a turn: the same tool always shows the
// same verb in the same turn.
const ACTION_VARIETY = {
  shell: ["Çalıştırıyor", "Koşturuyor"],
  read_file: ["Okuyor", "Göz atıyor", "İnceliyor"],
  edit_file: ["Düzenliyor", "Elden geçiriyor"],
  write_file: ["Oluşturuyor", "Kaleme alıyor"],
  search: ["Araştırıyor", "Tarıyor", "Eşeliyor"],
  fetch: ["Araştırıyor", "Sayfayı açıyor"],
  list_dir: ["Bakıyor", "Göz gezdiriyor"],
  mind_recall: ["Hatırlıyor", "Anımsıyor"],
  mind_memory: ["Aklına yazıyor", "Not düşüyor"],
};

function verbFor(tool) {
  // Deterministic: the same tool ALWAYS shows the same verb — the synonym
  // rotation is gone (states are model, not garnish; see the note above mull).
  const pool = ACTION_VARIETY[tool];
  if (pool) return t(pool[0]);
  return t(ACTION[tool]) || tool;
}

let modeTimer = null;

// Local servers load the model into memory on the first request, and that
// can take 20-60 seconds. Nothing streams during it; "thinking" on screen
// would be wrong — it is not thinking, it is loading. If this much time
// passes with nothing streaming, the status line says so.
const WAITING_AFTER = 1500;
let waitTimer = null;
// Did anything happen this turn (delta streamed / tool ran)? The waiting
// header only shows when REALLY nothing has happened; once work started it
// is no longer "loading" — the model's/tool's own state does the talking.
let turnActivity = false;

function waiting(on) {
  clearTimeout(waitTimer);
  if (!on) return;
  waitTimer = setTimeout(() => {
    if (busy && !turnActivity) setStatus("busy", t("Model yanıtı bekleniyor…"));
  }, WAITING_AFTER);
}

function setMode(name, label, holdMs) {
  clearTimeout(modeTimer);
  // Something streamed: the waiting notice no longer applies.
  if (name !== "thinking") waiting(false);
  const text = label || t(MODE_LABEL[name]) || name;
  // The scene's under-core label and the top strip say the same word.
  Scene.setMode(name, name === "idle" ? "" : text);
  setStatus(name === "idle" ? "ready" : "busy", text);

  // Short-lived modes (like recalling) fall back to thinking on their own;
  // otherwise the scene tells the wrong story while the agent works on.
  if (holdMs) modeTimer = setTimeout(() => { if (busy) setMode("thinking"); }, holdMs);
}

// --- streaming answer -------------------------------------------------
//
// The raw text is kept aside and redrawn every frame. Appending chunk by
// chunk to the DOM would be cheaper but does not work: a half-arrived code
// fence ("```powersh") only makes sense once it closes, so formatting always
// has to look at the whole text.
//
// Redraws are collapsed to one frame via rAF; otherwise a stream delivering
// hundreds of chunks per second redrew on every single chunk.

let raw = "";
let pending = null;

// This many redraws per second. Drawing every frame (60/s) clogged the main
// thread on a long answer: formatting re-reads the **entire** text and every
// frame gets pricier as the answer grows. At five thousand characters your
// keystrokes lag, clicks process late, the scene stutters.
//
// A tenth of a second is smooth enough for the eye and cuts the cost sixfold.
const REDRAW_MS = 100;

function write(chunk) {
  raw += chunk;
  lastChunkAt = Date.now();
  if (agentLine) agentLine.classList.remove("stall");
  bumpStream(chunk);
  if (!agentLine) {
    // WHITESPACE OPENS NO LINE. After a tool the model usually streams
    // "\n\n" first and the actual text comes seconds later. The old version
    // spawned the block on the first chunk: the strip settled ("▸ 1 step ·
    // 19 s") and then an empty "DORNICK ▮" blinked on screen for seconds —
    // the user had no idea what was happening. Now the strip stays live
    // ("Düşünüyor · N sn", driven by tickBusy) until real text arrives, and
    // the block is only born once there is something to write.
    if (!raw.trim()) return;
    raw = raw.replace(/^\s+/, "");   // leading whitespace stays out of the block
    // The answer starts streaming: the step cluster so far is sealed into
    // ITS OWN summary line and the strip SPLITS — later tools open a fresh
    // cluster below the text (Claude Code's "Ran 2 commands, used 3 tools ›"
    // rhythm; live request 31.08: "each narration's tool detail should open
    // from its own line, I want to click and see it").
    segmentWork();
    agentLine = line("agent", "");
  }
  if (pending) return;
  pending = setTimeout(() => {
    pending = null;
    // Fake tool call: the model wrote the XML as plain text instead of a
    // real call. Not an answer but a failed attempt — the block drops from
    // the DOM (the cursor goes with it). The model side is corrected in the
    // loop: a "you wrote your tool call as text" note goes out and the turn
    // continues.
    if (fakeCall(raw)) { agentLine.remove(); return; }
    Markdown.into(agentLine, raw);
    scroll();
  }, REDRAW_MS);
}

// --- thinking ---------------------------------------------------------
//
// Reasoning is not the answer: it stays out of the chat, streams dimly on a
// single line and disappears once the answer starts. All of it is kept, but
// only the last sentence stays on screen — the point is to watch what it is
// thinking, not to read it.

let thought = "";

// Two separate things live in the top strip: which model (identity) and how
// many tokens (state). The previous version wrote both to the same place and
// the first `usage` event erased the model name — after a model switch the
// new name never appeared on screen.
let modelName = "";
let sessionId = "";   // active chat — the per-chat model choice writes here
let tokenNote = "";
let busyNote = "";   // the "alive" note ticking second by second while busy

function showMeta() {
  // The model name and token total now live in the dock under the composer;
  // instead of repeating them, the top strip keeps only the LIVE work note —
  // streaming tokens and elapsed time. Idle, the top strip is silent.
  metaEl.textContent = [tokenNote, busyNote].filter(Boolean).join("  ·  ");
}

// Live stream counter. On a slow model the only clear tell between "stuck"
// and "working" is streaming tokens: counter growing → working, frozen →
// stuck. Elapsed seconds alone were not enough (a stuck request counts
// seconds too).
let streamStart = 0, streamTok = 0, streamRate = 0;

function bumpStream(chunk) {
  if (!streamStart) streamStart = Date.now();
  streamTok += Math.max(1, Math.round((chunk || "").length / 4));
  const secs = (Date.now() - streamStart) / 1000;
  streamRate = secs > 0.6 ? Math.round(streamTok / secs) : 0;
  tokenNote = "≈" + streamTok + " tok" + (streamRate ? " · " + streamRate + "/sn" : "");
  showMeta();
}

function resetStream() {
  streamStart = 0; streamTok = 0; streamRate = 0;
  // The word seed advances by one — thinking/action words vary from turn to
  // turn. (The interim-narration safety-net flags are gone: model text is no
  // longer folded, there is nothing to bring back.)
  turnSeed += 1;
  lastDelta = "";   // new turn: no channel has streamed yet
}

// The "alive" pulse. Root of the problem: a token-based counter only moves
// while tokens stream — but while a tool runs (shell, file write) or the
// model produces its next step, tokens do NOT stream, the counter freezes
// and the user is left with "is it stuck, how long do I wait, will it work".
// This ticker is independent of the stream: for as LONG as we are busy it
// advances, once a second, the top strip's elapsed time, the open tool rows'
// durations, and the work heading ("shell · 8 s"). So there is always a
// moving number on screen — it never looks frozen, and where it is and how
// long it took is clear at a glance.
let turnStart = 0;
let busyTicker = null;
// Time of the last text chunk: the cursor blinks only in genuinely
// streaming text; during a lull (tool/long thinking) it goes dark — no more
// "can't tell if it's working" ambiguity (see .line.agent.stall).
let lastChunkAt = 0;

function startBusyTicker() {
  if (busyTicker) return;
  if (!turnStart) turnStart = Date.now();
  mullTick = 0;   // every turn starts with "Düşünüyor"
  busyTicker = setInterval(tickBusy, 1000);
  tickBusy();
}

function stopBusyTicker() {
  if (busyTicker) { clearInterval(busyTicker); busyTicker = null; }
  turnStart = 0;
  busyNote = "";
  showMeta();
}

function tickBusy() {
  if (!busy) { stopBusyTicker(); return; }
  mullTick += 1;
  // If the stream stalls, the live cursor stops blinking (CSS .stall).
  if (agentLine) {
    agentLine.classList.toggle("stall", Date.now() - lastChunkAt > 2500);
  }
  const s = Math.round((Date.now() - turnStart) / 1000);
  busyNote = s + " sn";
  showMeta();
  if (!work) return;
  // Waiting for the model: the heading runs the countdown — not a frozen
  // "Düşünüyor" but the wait state itself (attempt counter + seconds left).
  if (waitState) { paintWait(); return; }
  // Live duration of the open tool rows ("SHELL … 8 s").
  const openRows = [...work.open.values()];
  for (const row of openRows) {
    if (!row._start) continue;
    const t = Math.round((Date.now() - row._start) / 1000);
    const took = row.querySelector(".took");
    if (took) took.textContent = t + " sn";
  }
  // Work heading: with a tool running, action + target + step count +
  // duration; with the answer streaming (top counter already live) hands
  // off; with neither, the model is producing a step → thinking time.
  if (openRows.length) {
    const first = openRows[0];
    const t = Math.round((Date.now() - (first._start || work.since)) / 1000);
    paintLive(" · " + t + " sn");
  } else if (!agentLine) {
    if (!paintLive()) workHead(mull(), "", since(work.since) + streamNote());
    paintThinkLine();
  }
}

// Live token note appended to the thinking/working heading while streaming.
function streamNote() {
  return streamTok ? " · " + streamTok + " tok" + (streamRate ? " · " + streamRate + "/sn" : "") : "";
}

// Messages waiting in the queue. When their turn comes the row is replaced
// with the real one; matching looks at the text to avoid double-drawing.
const waitingLines = [];

// Images/files that travel with a sent message. The SSE echo does not carry
// them; when the message row arrives they are matched by text and attached.
const pendingMedia = new Map();

// Attaches the sent image and file labels to the user message — a structure
// that shows "what did I send" at a glance.
function attachMedia(row, media) {
  const strip = document.createElement("div");
  strip.className = "msg-media";
  if (media.frame) {
    const img = document.createElement("img");
    img.className = "msg-thumb"; img.src = media.frame; img.alt = t("Gönderilen görsel");
    strip.appendChild(img);
  }
  for (const name of (media.files || [])) {
    const chip = document.createElement("span");
    chip.className = "msg-file"; chip.textContent = name;
    strip.appendChild(chip);
  }
  if (strip.childElementCount) row.appendChild(strip);
}

// Renumbers the queue badges: the position updates on every add/consume.
// A single waiter gets no number — "queued" is enough; with several, the
// position shows like "queued · 2".
function renumberQueue() {
  const many = waitingLines.length > 1;
  waitingLines.forEach((w, i) => {
    if (w.badge) w.badge.textContent = many ? t("Sırada") + " · " + (i + 1) : t("Sırada");
  });
}

// Raw reasoning scrolling across the screen used to take the answer's
// place: sentences the model spoke to itself ("No, let's keep it") sat in
// the chat and looked like something to read. What streams now is a single
// line — what it is doing and how long it has taken. The reasoning itself is
// not lost: clicking the line opens it, both while thinking and afterwards.
// When does a thinking line OPEN?
//
// Between tool steps the model thinks for a second or two, and the old
// version opened a line for each: a 30-step turn had thirty "✻ Düşündü ·
// 1 sn · 27 kelime" rows. When the strip opened, the thing worth reading
// (the steps) drowned in that noise. Trivial thinking opens NO line.
//
// Thresholds: a reasoning gets a line if it either took LONG (the user
// waited and has a right to see why) or is VOLUMINOUS (a real plan was
// laid). Below both it is the reflex thought between two tools — it has
// nothing to tell.
const THINK_MIN_S = 3;        // took this long: the user waited
const THINK_MIN_WORDS = 60;   // wrote this much: a plan was laid

function think(chunk) {
  const w = ensureWork();
  // Stream order is preserved: the answer text streamed so far is folded
  // into the strip as interim narration and the strip drops to the end of
  // the flow — the thinking box does not land ON TOP of already-written text
  // (at the top of the turn); chronology stays intact.
  foldNarration();
  dockWork(w);
  w.head.classList.add("busy");
  if (!w.thought) {
    // Consecutive thinking merges: with no step in between this is ONE
    // interrupted reasoning. Two separate lines would make it look like two
    // jobs.
    const last = w.body.lastElementChild;
    if (last && last.classList.contains("think") && last.classList.contains("done")) {
      w.thought = last;
      last.classList.remove("done", "open");
      last.onclick = null;
      thought = (last._full || "") + "\n\n";
      w.thinkStart = Date.now() - (last._secs || 0) * 1000;
    } else {
      w.thought = document.createElement("div");
      w.thought.className = "act note think";
      w.body.append(w.thought);
      w.thinkStart = Date.now();
      thought = "";
    }
    liveThoughtClickable(w.thought);
  }
  thought += chunk;
  bumpStream(chunk);
  // By default the TAIL is written to screen: the last few sentences of the
  // streaming reasoning. Reprinting the full text on every chunk made the
  // strip enormous. Clicking the box (`open`) shows all of it — readable
  // while running too (live wound: "I click the detail, nothing opens").
  const open = w.thought.classList.contains("open");
  const shown = open ? thought
    : (thought.length > 600 ? "…" + thought.slice(-600) : thought);
  w.thought.textContent = shown.trim();
  if (!paintLive()) workHead(mull(), "", since(w.since) + streamNote());
  paintThinkLine();
  // In-box scrolling: if the user is AT THE BOTTOM, follow the last
  // sentence; if they scrolled up to read, do not move them — pulling to the
  // bottom on every chunk made reading impossible ("it drifts behind" —
  // live complaint).
  const atBottom = w.thought.scrollHeight - w.thought.scrollTop
    - w.thought.clientHeight < 40;
  if (!open || atBottom) w.thought.scrollTop = w.thought.scrollHeight;
  if (w.body.hidden) scroll();   // folded: peek below; open: leave it to the user
}

// The RUNNING reasoning box is clickable too: toggles between the tail view
// and the full text. onclick used to attach only to finished thoughts —
// clicking the running one did nothing (live wound, 31.08).
function liveThoughtClickable(box) {
  box.title = t("Tıkla — akan muhakemenin tamamını gör");
  box.onclick = (ev) => {
    ev.stopPropagation();
    const open = box.classList.toggle("open");
    box.textContent = (open ? thought
      : (thought.length > 600 ? "…" + thought.slice(-600) : thought)).trim();
    if (open) {
      box.scrollTop = 0;
      revealAboveComposer(box);
    } else {
      box.scrollTop = box.scrollHeight;
      clearFitAboveComposer(box);
    }
  };
}

// Elapsed time. A static "thinking" line looks frozen in a long turn; the
// advancing counter shows it is working.
function since(started) {
  const seconds = Math.round((Date.now() - started) / 1000);
  return seconds > 0 ? " · " + seconds + " sn" : "";
}

// The operator note (spontaneous recalls, goal summary) arrives folded.
// Left open it drowned the chat: text the user did not write and mostly did
// not read stood taller than the answer.
function note(text) {
  const first = String(text || "").split("\n")[0];
  const short = first.length > 72 ? first.slice(0, 72) + "…" : first;

  // A note during a turn (spontaneous recalls, goal summary) is NOT a chat
  // line — it is the turn's activity. It folds INTO the work strip (like
  // Claude Code: user → strip → answer). So a separate "searched its mind"
  // line per turn does not bloat the chat; the curious open the strip.
  if (busy || work) {
    const w = ensureWork();
    const item = document.createElement("div");
    item.className = "act note recall";
    item.textContent = short;
    item.title = t("Hatırlananlar — tıkla, tamamını gör");
    let open = false;
    item.onclick = (ev) => { ev.stopPropagation(); open = !open; item.textContent = open ? text : short; };
    w.body.append(item);
    if (w.body.hidden) scroll();
    return;
  }

  // A standalone note outside a turn: a foldable top-level line as before.
  const head = line("system", "");
  head.textContent = short;
  const body = document.createElement("div");
  body.className = "note-body";
  body.textContent = text;
  body.hidden = true;
  thread.append(body);
  head.onclick = () => { body.hidden = !body.hidden; scroll(); };
  scroll();
}

// The thinking block ended: the full text folds into one line — "✻ Düşündü
// · 8 sn · 140 kelime". Leaving the huge reasoning full-size in the strip
// drowned the chat again when the strip opened. The text is not lost:
// clicking the line opens it.
function closeThought() {
  if (work) {
    const box = work.thought;
    const full = thought.trim();
    if (box) {
      const secs = Math.round((Date.now() - (work.thinkStart || work.since)) / 1000);
      const words = full ? full.split(/\s+/).length : 0;
      // The reasoning is kept NO MATTER WHAT — the threshold is only the
      // line-opening rule, not the retention rule. Swallowed thought also
      // enters the turn's archive and can be read from any opened
      // "✻ Düşündü" line.
      if (full) work.thinkAll.push(full);

      if (!full || (secs < THINK_MIN_S && words < THINK_MIN_WORDS)) {
        // Trivial: no line opens. (The text stays in the archive.)
        box.remove();
      } else {
        const label = t("✻ Düşündü") + (secs > 0 ? " · " + secs + " sn" : "")
                    + " · " + words + t(" kelime");
        box.classList.add("done");
        box.classList.remove("open");   // leave no trace of the live full view
        box.title = "";
        box.textContent = label;
        box.title = t("Tıkla — bu turun muhakemesini gör");
        // Carried on the row for merging and reopening.
        box._full = full;
        box._secs = secs;
        const archive = work.thinkAll;   // same array: later-swallowed ones show too
        let open = false;
        box.onclick = (ev) => {
          ev.stopPropagation();
          open = !open;
          box.textContent = open ? archive.join("\n\n———\n\n") : label;
          box.classList.toggle("open", open);
          // CSS max-height + inner scroll so the page does not stretch when
          // opened; here only keep the box in the visible area.
          if (open) {
            box.scrollTop = 0;
            revealAboveComposer(box);
          } else {
            clearFitAboveComposer(box);
          }
        };
      }
    }
    work.thought = null;
  }
  thought = "";
}

// The answer stays fully open. It used to fold into "Devamı" past the
// FOLD_AFTER threshold; in Q&A (product lists, explanations) the user had to
// click every single time — absurd. The tool trace already lives in the acts
// strip; the actual text does not fold.

// Closes the streaming text block and leaves it on screen.
function finishAgentLine() {
  clearTimeout(pending);
  pending = null;
  if (!agentLine) return;

  // The model often streams whitespace before calling a tool; that left a
  // completely empty line. A fake tool call is in the same basket: raw XML
  // does not stay in the chat (see fakeCall).
  if (!raw.trim() || fakeCall(raw)) agentLine.remove();
  else {
    Markdown.into(agentLine, raw);
    agentLine._rawText = raw;
    attachMsgActs(agentLine, "agent");
    agentLine.classList.add("done");
  }
  agentLine = null;
  raw = "";
}

// --- dangling stream cursor ---------------------------------------------
//
// The cursor (blinking ▮) is not a STATE but a CSS rule: `.line.agent` shows
// the cursor until it gets `.done`. So a block that never gets `.done` when
// the stream ends, or never closes at all, stays on screen as an empty
// "DORNICK ▮" blinking forever — the user thinks Dornick is still writing.
//
// Proven gaps: the "interrupted" event never sealed the line, and
// "empty_assistant_turn" (the model returned nothing) was never handled in
// the UI at all. Instead of patching one by one there is a BROOM here: on
// every path where the turn ends, all unsealed agent blocks outside the live
// stream are closed — empty ones are removed from the DOM, non-empty ones
// sealed. So even if a new path opens tomorrow, no cursor is left hanging.
function clearCursor() {
  for (const el of thread.querySelectorAll(".line.agent:not(.done)")) {
    if (el === agentLine) continue;   // the live stream: it earns its cursor
    if (el.textContent.trim()) el.classList.add("done");
    else el.remove();
  }
}

// A "safety net" used to live here: if the turn ended on a tool with no
// answer left on screen, it brought back the last narration folded into the
// strip. The patch became unnecessary — model text is never folded any more
// (see foldNarration), so there is nothing to bring back. The risk of the
// same text appearing twice is gone at the root.
function sealLine() {
  closeThought();
  closeWork();
  finishAgentLine();
  clearCursor();
}

// How many blocks stay visible. A block is usually a heading or a single
// sentence; leaving only that made the answer unreadable.
const FOLD_KEEP = 2;

function fold(box) {
  // The leading blocks stay visible: the answer's conclusion. The rest closes.
  const blocks = [...box.children];
  if (blocks.length < FOLD_KEEP + 2) return;

  const rest = document.createElement("div");
  rest.className = "fold-body";
  rest.hidden = true;
  rest.append(...blocks.slice(FOLD_KEEP));

  const more = document.createElement("div");
  more.className = "fold";
  more.textContent = t("Devamı");
  more.onclick = () => {
    rest.hidden = !rest.hidden;
    more.textContent = rest.hidden ? t("Devamı") : t("Kısalt");
    more.classList.toggle("open", !rest.hidden);
    scroll();
  };

  box.append(more, rest);
}

// --- chat -------------------------------------------------------------
$("composer").addEventListener("submit", (ev) => {
  ev.preventDefault();
  // Submitting with an empty box while running = stop; with text, the old queue behaviour.
  if (busy && !input.value.trim()) { post("/api/interrupt"); Speech.stop(); return; }
  send();
});
input.addEventListener("input", paintSend);

// WHEREVER the composer box is clicked, the text area takes focus. Native
// round (31.08): a user clicking the box's empty area got no focus and the
// following Ctrl+V went nowhere (half of "paste doesn't work" was this).
document.querySelector(".compose-shell").addEventListener("mousedown", (ev) => {
  if (ev.target.closest("button, a, input, textarea, select, .dock, .git-bar, .pop")) return;
  ev.preventDefault();   // don't steal focus — we assign it directly
  input.focus();
});

// When the shell height changes (textarea, git, dock) measure the chat's
// bottom gap — a fixed 128px buried the thought under the input on a tall
// shell.
(() => {
  const shell = document.getElementById("compose-shell");
  if (!shell) return;
  const syncComposeH = () => {
    const bottom = parseFloat(getComputedStyle(shell).bottom) || 14;
    const h = Math.ceil(shell.offsetHeight + bottom + 8);
    document.body.style.setProperty("--compose-h", Math.max(120, h) + "px");
  };
  new ResizeObserver(syncComposeH).observe(shell);
  window.addEventListener("resize", syncComposeH);
  syncComposeH();
})();

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 180) + "px";
});

input.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); send(); }
});

async function send() {
  if (!ready) return;
  const text = input.value.trim();

  // With the lens open the message carries the frame too. Asking "can you
  // see me" without sending an image defeated keeping the camera on: the
  // model found nothing to look at and stayed silent.
  if (Camera.on && !frame) {
    Camera.say(t("Bakıyor…"));
    await Camera.snap();
  }

  // A camera frame can be sent without text too (no need to say "look").
  //
  // Sending while busy works as well: the message queues and is handled when
  // the turn ends. The previous version dropped it silently — the user typed,
  // hit enter, and nothing happened.
  if (!text && !frame && !attached.length && !Camera.on) return;
  // No optimistic drawing: once written to the event log, the message comes
  // back via SSE. Drawing from two sources would duplicate.
  // Attachments are RESET inside withFiles: the name list and the image must
  // be taken BEFORE it (the old order always left the attached file labels
  // empty). With no camera frame, the last attached image goes on the message.
  const atts = attached.slice();
  const img = frame || (atts.filter((a) => a.image).pop() || {}).image || "";
  const posted = withContext(withFiles(withMentions(text)));
  // The sent image and files are not carried in the SSE echo (the image is
  // heavy, and frames from tools are `internal`). With the data the client
  // holds: when the message row arrives, pin the thumbnail and file labels
  // onto it.
  if (img || atts.length) {
    pendingMedia.set(posted, { frame: img, files: atts.map((a) => a.name) });
  }
  post("/api/chat", { text: posted, image: img });
  // The user spoke their own words: the pending "apply plan" offer is stale.
  hidePlanOffer();
  // A user who sends a message wants to see the answer: a scroll position
  // forgotten up above must not lock the follow.
  resumeFollow(false);
  dropFrame();
  // The frame is sent; the label on the preview awaits the answer.
  if (Camera.on) Camera.say(t("Bakıyor…"));
  input.value = "";
  input.style.height = "auto";
}

// --- camera -------------------------------------------------------------
//
// The frame is not sent directly; it previews above the input line. Sending
// without seeing what you send means not knowing what the camera caught.

let frame = "";

Camera.init({
  onFrame: (data) => {
    frame = data;
    $("shot-image").src = data;
    $("shot").hidden = false;
    input.focus();
  },
});

// The label must be short: there is one line of room under the preview.
let clause = "";

function firstClause(chunk) {
  clause = (clause + chunk).slice(0, 80);
  return clause.split(/[.!?\n]/)[0].trim();
}

function dropFrame() {
  clause = "";
  frame = "";
  $("shot").hidden = true;
  $("shot-image").removeAttribute("src");
}

// No camera button on the input line: the watch icon above already keeps
// the same device open; opening getUserMedia a second time made the browser
// say "could not open". To attach a frame: paperclip / drag.

$("lens-snap").addEventListener("click", () => Camera.snap());
$("lens-close").addEventListener("click", () => Camera.close());

// --- composer + menu ----------------------------------------------------
//
// The attach shortcuts in one place: files and the related settings tabs.
// The counterpart of Claude Code's + menu — without leaving the composer.
$("plus").addEventListener("click", () => {
  const pop = $("plus-pop");
  if (!pop.hidden) { pop.hidden = true; return; }
  pop.textContent = "";

  const openTab = (name) => Settings.open(name);
  const items = [
    ["Dosya ekle", "belge, görsel, veri", () => $("file-input").click()],
    ["Kamera", "aç/kapa, izleme", () => openTab("eyes")],
    ["Bağlantılar", "MCP sunucuları", () => openTab("connectors")],
    ["Yetenekler", "kendi araçların", () => openTab("skills")],
    ["Yeni görev", "zamanlanmış iş", () => openTab("tasks")],
  ];
  for (const [name, hint, run, when] of items) {
    if (when && !when()) continue;
    pop.append(popRow(t(name), t(hint), false, run));
  }
  pop.hidden = false;
  const at = $("plus").getBoundingClientRect();
  pop.style.left = at.left + "px";
  pop.style.bottom = (window.innerHeight - at.top + 8) + "px";
});

document.addEventListener("click", (ev) => {
  const pop = $("plus-pop");
  if (pop.hidden) return;
  if (!pop.contains(ev.target) && ev.target !== $("plus") && !$("plus").contains(ev.target)) {
    pop.hidden = true;
  }
});

$("shot-drop").addEventListener("click", dropFrame);

// --- attached files -----------------------------------------------------
//
// Drag, paste or browse — all three copy the file into the workshop and hand
// the agent its path. From there the agent can open it with `read_file`.
// Images are additionally pinned to the message: the model can look directly.

let attached = [];

Drop.init({
  onFile: (info) => {
    attached.push(info);
    drawDrops();
  },
  onImage: (data) => {
    frame = data;
    $("shot-image").src = data;
    $("shot").hidden = false;
  },
  onNote: (text) => line("alert", text),
});

function drawDrops() {
  const box = $("drops");
  box.textContent = "";
  box.hidden = !attached.length;

  for (const item of attached) {
    const chip = document.createElement("span");
    chip.className = "chip" + (item.image ? " img" : "");
    if (item.image) {
      const thumb = document.createElement("img");
      thumb.src = item.image;
      thumb.alt = item.name;
      chip.append(thumb);
    }
    chip.append(document.createTextNode(item.name + " · " + size(item.bytes)));
    const drop = document.createElement("button");
    drop.type = "button";
    drop.textContent = "×";
    drop.title = t("Listeden çıkar");
    drop.onclick = () => {
      attached = attached.filter((x) => x !== item);
      drawDrops();
    };
    chip.append(drop);
    box.append(chip);
  }
}

function size(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

// The attached files' paths are appended to the message: the browser gives
// no local path, but the workshop copy's path is enough for the agent.
function withFiles(text) {
  if (!attached.length) return text;
  const list = attached.map((f) => "- " + f.path).join("\n");
  attached = [];
  drawDrops();
  return (text ? text + "\n\n" : "") + "Eklenen dosyalar (atölyende):\n" + list;
}

// --- app context --------------------------------------------------------
//
// When an app is picked as "talk about" from the apps panel it enters the
// conversation's context: a short, explicit context line is added to the
// next message so the agent knows which app we mean. Honest: the addition is
// visible in the message, not a hidden injection. Not sticky — cleared once
// sent (so it doesn't bleed into the next topic).
let appContext = null;
const KIND_TR = { web: "web uygulaması", run: "çalıştırılabilir", doc: "belge", folder: "klasör" };

function setAppContext(app) {
  appContext = app;
  drawContext();
  input.focus();
}

function clearAppContext() {
  appContext = null;
  drawContext();
}

function drawContext() {
  const box = document.getElementById("ctx");
  box.replaceChildren();
  box.hidden = !appContext;
  if (!appContext) return;

  const glyph = { web: "◈", run: "▶", doc: "≡", folder: "▸" }[appContext.type] || "≡";
  const chip = document.createElement("span");
  chip.className = "ctx-chip " + appContext.type;
  chip.append(el2("span", "ctx-glyph", glyph));
  chip.append(el2("span", "ctx-name", appContext.name));
  if (appContext.address) chip.append(el2("span", "ctx-addr", appContext.address));
  const drop = el2("button", "ctx-x", "×");
  drop.type = "button";
  drop.title = t("Bağlamdan çıkar");
  drop.onclick = clearAppContext;
  chip.append(drop);
  box.append(el2("span", "ctx-lead", t("Konuşulan")), chip);
}

function el2(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

// Files pointed at with `@` are written into the message explicitly (see
// command.js). Without the module the text passes through untouched.
function withMentions(text) {
  return (typeof Command !== "undefined" && Command.addHint) ? Command.addHint(text) : text;
}

// Bridge to the orchestra deck: if the module is absent (not loaded), skip silently.
function orchStart(e) { if (typeof Orchestra !== "undefined") Orchestra.start(e); }
function orchTool(e) { if (typeof Orchestra !== "undefined") Orchestra.tool(e); }
function orchEnd(e) { if (typeof Orchestra !== "undefined") Orchestra.end(e); }
function orchSeed(list) { if (typeof Orchestra !== "undefined" && Orchestra.seed) Orchestra.seed(list); }

// Bridge to the running-tasks panel: same pattern. Refreshed even while the
// panel is closed — the top-bar badge must tell the truth.
function tasksRefresh() { if (typeof Tasks !== "undefined") Tasks.refresh(); }
function tasksDone(e) { if (typeof Tasks !== "undefined") Tasks.done(e); }

// Change-ledger bridge: turn boundaries.
function chgTurnStart() { if (typeof Changes !== "undefined") Changes.turnStarted(); }
function chgTurnEnd() { if (typeof Changes !== "undefined") Changes.turnEnded(); }

function withContext(text) {
  const bits = [];
  if (typeof Cameras !== "undefined" && Cameras.context) {
    const cam = Cameras.context();
    if (cam) bits.push(cam);
  }
  if (appContext) {
    const a = appContext;
    const kind = KIND_TR[a.type] || a.type;
    let line = `[Bağlam] Atölyendeki "${a.name}" adlı ${kind} üzerine konuşuyoruz (yol: ${a.path}).`;
    if (a.address) line += ` Şu an çalışıyor: ${a.address}.`;
    else if (a.url) line += ` Adres: ${a.url}.`;
    if (a.title) line += ` Tanım: ${a.title}.`;
    clearAppContext();
    bits.push(line);
  }
  if (!bits.length) return text;
  return bits.join("\n") + (text ? "\n\n" + text : "");
}

stopBtn.addEventListener("click", () => { post("/api/interrupt"); Speech.stop(); });

// --- focus mode ---------------------------------------------------------
//
// Every panel closes; what remains is the core and the input area — like
// talking to someone. The work/simulation panels (viewer, apps, history,
// settings) are optional; in focus mode they all withdraw. With the camera
// or voice on, this state turns into a genuine two-way conversation.
let focused = false;
function toggleFocus() {
  focused = !focused;
  document.body.classList.toggle("focus", focused);
  if (typeof Scene !== "undefined") Scene.focus(focused);
  if (focused) {
    // Close every open panel: focus on one thing.
    try { Viewer.close(); } catch {}
    try { Apps.close(); } catch {}
    try { History.close(); } catch {}
    try { if (window.JobsPanel) JobsPanel.close(); else Tasks.close(); } catch {}
    try { if (typeof Cameras !== "undefined") Cameras.hide(); } catch {}
    const s = document.getElementById("settings"); if (s) s.hidden = true;
    document.body.classList.remove("viewing", "settling");
  }
  document.getElementById("focus").classList.toggle("on", focused);
}
document.getElementById("focus").addEventListener("click", toggleFocus);

// --- night / day ---------------------------------------------------------
//
// Theme via `<html data-theme>`; since the colours live in CSS tokens the
// scene (canvas) adapts by itself on the next frame via getComputedStyle.
// The saved theme is applied in index.html before the page paints (no flash).
function paintThemeIcon() {
  const light = document.documentElement.dataset.theme === "light";
  const moon = document.querySelector("#theme .ic-moon");
  const sun = document.querySelector("#theme .ic-sun");
  if (moon) moon.hidden = light;   // in light mode the moon hides
  if (sun) sun.hidden = !light;    // in light mode the sun shows
}

// Flip the native (OS) title bar with the app theme: dark bar on the dark
// theme, light bar on the light theme. Without the desktop shell (pywebview)
// — opened in a browser — it is skipped silently.
function syncTitlebar() {
  const light = document.documentElement.dataset.theme === "light";
  try { window.pywebview.api.paint_titlebar(!light); } catch {}
}

document.getElementById("theme").addEventListener("click", () => {
  const light = document.documentElement.dataset.theme === "light";
  if (light) delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = "light";
  try { localStorage.setItem("dornick-theme", light ? "dark" : "light"); } catch {}
  paintThemeIcon();
  syncTitlebar();
});
paintThemeIcon();
// The pywebview API can become ready slightly after the page: wait for the
// ready event, else retry after a short delay (correct bar colour on first load).
window.addEventListener("pywebviewready", syncTitlebar);
setTimeout(syncTitlebar, 800);

// --- learn-me icon -------------------------------------------------------
//
// The sprout in the top bar: visible while the feature is on, pulses while
// training runs, trains immediately on click. Two sources: GET /api/tanima
// on startup, then SSE "tanima" events (acik/kapali/basladi/bitti) — even if
// the switch on the settings page is flipped in another tab, the icon
// adapts instantly.

let lastTrainedAt = "";        // ISO date of the last training; short form in the tooltip
let trainingRunning = false;
let trainingStartedAt = 0;     // start of the minimum time the pulse must show

// The pulse must not show shorter than this: on a sub-second run the user
// presses the button and it looks like nothing happened on screen.
const TRAINING_MIN_PULSE_MS = 3000;

function trainingDate() {
  if (!lastTrainedAt) return t("henüz yok");
  const d = new Date(lastTrainedAt);
  if (isNaN(d)) return lastTrainedAt;
  return d.toLocaleString(undefined, {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function trainingIcon(state) {
  const icon = $("tanima-ikon");
  if (!icon) return;
  if (state === "acik") icon.hidden = false;
  else if (state === "kapali") icon.hidden = true;
  else if (state === "basladi") { trainingRunning = true; trainingStartedAt = Date.now(); }
  else if (state === "bitti") {
    // The pulse must show for AT LEAST this long: training sometimes takes
    // under a second and when the user pressed the button it looked like
    // nothing had happened. "Something happened" must be visible.
    const left = TRAINING_MIN_PULSE_MS - (Date.now() - trainingStartedAt);
    if (left > 0) { setTimeout(() => trainingIcon("bitti"), left); return; }
    trainingRunning = false;
    lastTrainedAt = new Date().toISOString();
  }
  icon.classList.toggle("kosuyor", trainingRunning);
  icon.title = trainingRunning
    ? t("Şu an seni tanıyorum — eğitim arka planda sürüyor")
    : t("Beni tanı açık") + " · " + t("son eğitim") + ": " + trainingDate()
      + " · " + t("tıkla: şimdi eğit");
}

// "Train now" NEVER STAYS SILENT. The old version showed nothing on click;
// in reality the loop started and quit in under a second with "too little
// new data: 0/50". Every outcome is now stated in one line — whether it
// started, or WHY it could not.
const TRAINING_REASONS = {
  basladi: "Tanıma eğitimi başladı — arka planda sürüyor.",
  veri_yok: "Yeni veri yok — yeni anılar biriktikçe kendiliğinden çalışacak.",
  kosuyor: "Eğitim zaten koşuyor.",
  duzenek_yok: "Eğitim düzeneği bu makinede kurulu değil.",
  kapali: "Beni tanı kapalı — Ayarlar'dan açabilirsin.",
  ara_yok: "Henüz sırası değil — yeni anılar biriktikçe kendiliğinden çalışacak.",
  baslatilamadi: "Eğitim başlatılamadı.",
};

$("tanima-ikon").addEventListener("click", async () => {
  // A click while running is silently ignored: the tooltip already says the
  // state, and opening a second run is impossible anyway (singleton process).
  if (trainingRunning) return;
  const answer = await post("/api/tanima", { simdi: true });
  const reason = (answer && answer.sebep) || "baslatilamadi";
  line("alert", t(TRAINING_REASONS[reason] || TRAINING_REASONS.baslatilamadi));
});

fetch("/api/tanima").then((r) => r.json()).then((d) => {
  lastTrainedAt = d.son || "";
  trainingRunning = !!d.kosuyor;
  trainingIcon(d.on ? "acik" : "kapali");
}).catch(() => {});

// --- left panel resizing ------------------------------------------------
// The apps and conversations panels open from the left; they widen by
// dragging the grip on their right edge. The width lives in one variable
// (--left-w) — applied to whichever panel is open.
(() => {
  const root = document.documentElement;
  let active = false;
  let onMove = null;
  const stop = () => {
    active = false;
    document.body.classList.remove("left-resize");
    if (onMove) window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", stop);
    onMove = null;
  };
  document.addEventListener("pointerdown", (e) => {
    const grip = e.target.closest("[data-left-grip]");
    if (!grip) return;
    e.preventDefault();
    active = true;
    try { grip.setPointerCapture(e.pointerId); } catch { /* old engine */ }
    window.addEventListener("pointercancel", stop);
    window.addEventListener("blur", stop);
    const jobs = grip.closest(".jobs-panel");
    document.body.classList.add("left-resize");
    onMove = jobs
      ? (ev) => {
          if (!active) return;
          const max = Math.min(window.innerWidth - 48, window.innerWidth * 0.94);
          const w = Math.max(520, Math.min(max, ev.clientX));
          root.style.setProperty("--jobs-w", w + "px");
        }
      : (ev) => {
          if (!active) return;
          const max = Math.min(window.innerWidth - 260, window.innerWidth * 0.6);
          const w = Math.max(240, Math.min(max, ev.clientX));
          root.style.setProperty("--left-w", w + "px");
        };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", stop);
  });
})();
// Esc leaves focus mode: an escape hatch should always be at hand.
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && focused) toggleFocus();
});

// --- microphone ---------------------------------------------------------
//
// Hold, speak, release: what you said lands in the input area. We do not
// send directly — recognition is not always right and the user must get a
// chance to correct. The wake word is separate: that is a deliberate call.

Listen.init({
  onText: (text) => {
    input.value = (input.value ? input.value + " " : "") + text;
    input.focus();
    input.dispatchEvent(new Event("input"));
  },
  onCommand: (text) => {
    // Listening continues while the window is hidden; on hearing the word it
    // must come back, or the answer streams in an invisible window.
    post("/api/wake");
    if (!busy) post("/api/chat", { text });
  },
  onState: (label) => {
    if (label) setStatus("busy", label);
    else if (!busy) setStatus("ready", t("Hazır"));
  },
  // Whether sound is being heard must be visible: in the "I spoke and
  // nothing happened" case, the culprit is unknowable without a meter.
  onLevel: showLevel,
});

// The level can come from two places: the browser's meter during push-to-
// talk, the ear in Python while listening in the background. Both grow the
// same ring.
function showLevel(level) {
  const shown = Math.min(1, level * 8);
  const hear = $("hear");
  const mic = $("mic");
  // The HUD microphone pulses too: with the composer #mic hidden it looked
  // like "no movement at all".
  if (hear && !hear.classList.contains("off")) {
    hear.style.setProperty("--level", shown.toFixed(3));
    hear.classList.toggle("hot", shown > 0.12);
  }
  if (mic && !mic.hidden && !mic.classList.contains("mute")) {
    mic.style.setProperty("--level", shown.toFixed(3));
    mic.classList.toggle("hot", shown > 0.12);
  }
  if (shown > 0.3) Scene.use("mic", t("Ses duyuyor"));
}

let earOn = false;

function setListening(enabled, wake, open) {
  $("mic").hidden = !enabled;
  // Continuous listening lives on the Python side: it could not stay in the
  // browser because Chromium throttles background timers to a minute when
  // the window hides and listening dies. With a wake word or open listening
  // the button cuts the ear; otherwise push-to-talk.
  earOn = !!(enabled && (wake || open));
  setMicDeaf($("mic").classList.contains("mute"));
}

function setMicDeaf(off) {
  const mic = $("mic");
  mic.classList.toggle("mute", !!off);
  mic.setAttribute("aria-pressed", off ? "false" : "true");
  if (off) {
    mic.classList.remove("live", "hot");
    mic.style.setProperty("--level", "0");
  }
  mic.title = off
    ? t("Tıkla: dinlemeye devam")
    : earOn
      ? t("Tıkla: dinlemeyi durdur")
      : t("Tıkla ve konuş");
}

// Click: with continuous listening on, cut / restore the ear. Holding was
// wrong: the user clicked and released, which produced a zero-second
// recording that was silently discarded. Without a wake word, the old
// push-to-talk.
$("mic").addEventListener("click", async () => {
  if (earOn) {
    const d = await post("/api/senses", { action: "toggle" });
    if (d && d.ear) {
      setMicDeaf(!!d.snoozed);
      return;
    }
  }
  const on = await Listen.toggle();
  $("mic").classList.toggle("live", Listen.mode === "push");
  if (on === false) return;
});

// --- voice / listening HUD --------------------------------------------
// Same language as the camera: struck through when off, click → popup.

function paintMute(on) {
  const button = $("mute");
  button.hidden = false;
  button.classList.toggle("off", !on);
  button.setAttribute("aria-pressed", on ? "true" : "false");
  button.title = on ? t("Ses açık — tıkla: ayarla") : t("Ses kapalı — tıkla: aç");
  const go = $("mute-enable");
  if (go) go.textContent = on ? t("Sesi kapat") : t("Sesi aç");
}

function paintHear(on) {
  const button = $("hear");
  if (!button) return;
  button.classList.toggle("off", !on);
  button.setAttribute("aria-pressed", on ? "true" : "false");
  button.title = on
    ? t("Dinleme açık — tıkla: ayarla")
    : t("Dinleme kapalı — tıkla: aç");
  const go = $("hear-enable");
  if (go) go.textContent = on ? t("Dinlemeyi kapat") : t("Dinlemeyi aç");
}

function setVoice(enabled) {
  Speech.enable(enabled);
  paintMute(!!enabled);
}

function closeSensePops(keep) {
  for (const id of ["mute-pop", "hear-pop", "cam-pop"]) {
    const el = $(id);
    if (el && id !== keep) el.hidden = true;
  }
}

$("mute").addEventListener("click", (ev) => {
  ev.stopPropagation();
  const pop = $("mute-pop");
  const next = pop.hidden;
  closeSensePops("mute-pop");
  pop.hidden = !next;
});
$("mute-enable").addEventListener("click", async () => {
  $("mute-pop").hidden = true;
  const on = $("mute").classList.contains("off");
  const d = await post("/api/senses", { action: "power", what: "voice", enabled: on });
  if (d && d.ok) setVoice(on);
});
$("mute-settings").addEventListener("click", () => {
  $("mute-pop").hidden = true;
  if (typeof Settings !== "undefined") Settings.open("voice");
});

$("hear").addEventListener("click", (ev) => {
  ev.stopPropagation();
  const pop = $("hear-pop");
  const next = pop.hidden;
  closeSensePops("hear-pop");
  pop.hidden = !next;
});
$("hear-enable").addEventListener("click", async () => {
  $("hear-pop").hidden = true;
  const on = $("hear").classList.contains("off");
  const d = await post("/api/senses", { action: "power", what: "hearing", enabled: on });
  if (d && d.ok) {
    paintHear(on);
    setListening(on, on, on);
  }
});
$("hear-settings").addEventListener("click", () => {
  $("hear-pop").hidden = true;
  if (typeof Settings !== "undefined") Settings.open("hearing");
});

document.addEventListener("click", (ev) => {
  const mutePop = $("mute-pop");
  const hearPop = $("hear-pop");
  if (mutePop && !mutePop.hidden
      && !mutePop.contains(ev.target) && !$("mute").contains(ev.target))
    mutePop.hidden = true;
  if (hearPop && !hearPop.hidden
      && !hearPop.contains(ev.target) && !$("hear").contains(ev.target))
    hearPop.hidden = true;
});

// --- authority ----------------------------------------------------------
//
// "I must be able to grant full authority instantly if I want" — opening the
// settings page and switching tabs is not what is wanted at that moment. The
// strip button toggles between two states and does not hide it when full
// authority is on.

const AUTHORITY = { auto: "otomatik", ask: "sorar", plan: "salt okunur", yolo: "tam yetki" };

// Which mode to return to when leaving full authority. The first mode read
// is kept: a user coming from "ask" must return to "ask", not "auto".
let mode = "ask";
let previous = "ask";

// The mode before entering plan mode. The "apply plan" button flips the
// mode back to it; if the page opened in plan mode (prior unknown), falls
// back to auto.
let beforePlan = "auto";
// The first setAuthority call installs the truth from the server; the local
// default before it ("ask") must not count as a transition.
let modeKnown = false;

function setAuthority(next) {
  if (modeKnown && next === "plan" && mode !== "plan" && mode !== "yolo") beforePlan = mode;
  // If the mode left plan, the pending "apply plan" offer went stale.
  if (next !== "plan") hidePlanOffer();
  modeKnown = true;
  mode = next;
  const button = $("authority");
  button.classList.toggle("full", next === "yolo");
  button.title = t("Yetki: ") + (t(AUTHORITY[next]) || next) +
                 (next === "yolo" ? t(" — hiçbir şey sorulmuyor") : t(" · tıkla: kip seç"));
  if (next !== "yolo") previous = next;
  // The lock and the mode chip under the composer must show the same truth.
  dockRender();
}

$("authority").addEventListener("click", (ev) => {
  // The lock used to toggle only yolo↔previous on one click; what it did
  // was unclear. Same menu as the dock mode chip.
  ev.preventDefault();
  const pop = dockPop($("authority"));
  if (!pop) return;
  pop.append(mk("div", "pop-head", t("Yetki kipi")));
  for (const kind of MODE_ORDER) {
    pop.append(popRow(t(AUTHORITY[kind]), t(MODE_TELL[kind]), kind === mode, async () => {
      const was = mode;
      setAuthority(kind);
      const answer = await post("/api/settings", { permissions: { mode: kind } });
      if (answer && answer.ok === false) setAuthority(was);
    }));
  }
  placePop($("authority"));
});

// --- dock: the status strip under the composer --------------------------
//
// Model, thinking depth, authority mode and context usage — visible at a
// glance without opening the settings page. Clicking the model opens the
// settings' model tab; depth and mode advance on one click — opening a menu
// for four options takes longer than clicking.

const EFFORTS = ["low", "medium", "high", "xhigh", "max"];
const MODE_ORDER = ["auto", "ask", "plan", "yolo"];

let dockEffort = "";
let providerName = "";      // openrouter / ollama / anthropic …
let canRun = true;          // is there a key (else the setup card shows)
let contextWindow = 0;
let lastBreakdown = [];   // line-by-line breakdown (snapshot + usage)

function dockRender() {
  // Provider chip: with no key, in the warning colour and saying "no key".
  const prov = $("dock-provider");
  if (prov) {
    prov.textContent = providerName || "—";
    prov.classList.toggle("bad", !!providerName && !canRun);
    prov.title = (providerName ? t("Sağlayıcı: ") + providerName : t("Sağlayıcı seçilmedi"))
      + (canRun ? "" : " · " + t("anahtar yok"))
      + " · " + t("tıkla: ayarları aç");
  }
  $("dock-model").textContent = modelName || "model";
  $("dock-effort").textContent = dockEffort || "—";
  $("dock-mode").textContent = t(AUTHORITY[mode]) || mode || "—";
  $("dock-mode").classList.toggle("full", mode === "yolo");
  // The context gauge should show before the first turn too: an empty bar +
  // empty text read as "none" — 0% is information as well.
  if (!$("dock-ctx-pct").textContent) $("dock-ctx-pct").textContent = "%0";
}

// Context usage. The percentage comes from the `usage` event: prompt total
// / window. The colour shifts as it fills — noticeable without reading the
// number.
function shortNum(n) {
  n = Math.max(0, Number(n) || 0);
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(1) + "K";
  return String(Math.round(n));
}

function ctxUsed(promptTotal, breakdown) {
  const listed = (breakdown || []).reduce((s, p) => s + (Number(p.n) || 0), 0);
  return Number(promptTotal) || listed;
}

function paintCtxBar(bar, breakdown, window_, used) {
  if (!bar) return;
  bar.replaceChildren();
  const cap = window_ || used || 1;
  const parts = (breakdown || []).filter((p) => (p.n || 0) > 0);
  if (!parts.length && used) {
    const i = mk("i", "ctx-seg sohbet");
    i.style.width = Math.min(100, (used / cap) * 100) + "%";
    bar.append(i);
    return;
  }
  for (const p of parts) {
    const i = mk("i", "ctx-seg " + (p.id || ""));
    i.style.width = Math.max(0.4, (p.n / cap) * 100) + "%";
    i.title = t(p.ad) + " · " + shortNum(p.n);
    bar.append(i);
  }
}

function dockContext(promptTotal, estimate, breakdown) {
  if (breakdown) lastBreakdown = breakdown;
  const used = ctxUsed(promptTotal, lastBreakdown);
  if (!contextWindow) return;
  const pct = used ? Math.min(100, Math.round((used / contextWindow) * 100)) : 0;
  $("dock-ctx-pct").textContent = "%" + pct;
  paintCtxBar($("dock-ctx-bar"), lastBreakdown, contextWindow, used);
  const box = $("dock-ctx");
  box.classList.toggle("warn", pct >= 70 && pct < 90);
  box.classList.toggle("hot", pct >= 90);
  // In a resumed session the figure may not be the provider's real count
  // (old logs carry no usage): it is declared a rough estimate. Saying
  // "approximate" is honest; selling made-up precision is not.
  box.classList.toggle("tahmin", !!estimate);
  box.title = estimate ? t("Bağlam doluluğu — yaklaşık (geçmişten tahmin)")
                     : t("Bağlam doluluğu");
}

// --- cost chip ----------------------------------------------------------
//
// Session total, in the spirit of Claude Code's /usage: "≈$0.42". Reopening
// a conversation seeds past turns too. Price from the OpenRouter catalogue;
// unknown, the chip falls back to token counts. Clicking opens the
// this-turn + session breakdown.

let price = null;                              // {girdi, cikti} USD/token | null
let usage = { tur: null, oturum: null };    // totals from the usage event
// Spend cap for this session (USD); null = unlimited. The real brake is on
// the server (see desktop.Bridge._butce_freni): the counter there stops the
// turn loop. The copy here only displays and pre-fills the box.
let budget = null;

// With the output price $/M above this threshold the model is "premium":
// the chip turns amber and the title gets a note — warns without shouting.
const PREMIUM_USD_M = 20;

function money(n) {
  // Small amounts vanished as "0.00" at two decimals; below a cent three
  // decimals are shown.
  return "$" + (n >= 0.01 || n === 0 ? n.toFixed(2) : n.toFixed(3));
}

function costOf(k) { return k.girdi * price.girdi + k.cikti * price.cikti; }

function shortTok(n) { return (n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n)); }

function isPremium() { return !!(price && price.cikti * 1e6 > PREMIUM_USD_M); }

function dockCost() {
  const chip = $("dock-cost");
  const turn = usage.tur;
  const session = usage.oturum;
  // The chip shows the SESSION total — reopening a conversation seeds past
  // spend here too. "This turn" stays in the breakdown.
  const hasAny = session && (session.girdi || session.cikti || session.cagri);
  if (!hasAny && !budget) { chip.hidden = true; return; }
  chip.hidden = false;
  chip.classList.toggle("premium", isPremium());
  const spent = price && session ? costOf(session) : null;
  let text = !hasAny ? "≈$0.00"
    : price ? "≈" + money(spent)
    : shortTok((session.girdi || 0) + (session.cikti || 0)) + " tok";
  // With a cap the chip carries two numbers at once: what the session spent
  // and what the ceiling is. "How much is left" gets answered without
  // opening the box.
  if (budget) text += " · " + money(spent == null ? 0 : spent) + "/" + money(budget);
  chip.textContent = text;
  chip.classList.toggle("over", !!(budget && spent != null && spent >= budget));
  chip.title = t("Bu oturumun tahmini toplam harcaması — tıkla: kırılım")
    + (turn && (turn.girdi || turn.cikti) && price
      ? t(" · bu tur: ") + "≈" + money(costOf(turn)) : "")
    + (budget ? t(" · oturum sınırı: ") + money(budget) : "")
    + (isPremium() ? t(" · premium model (çıktı > $20/M)") : "");
}

// Breakdown box: session total + input/output × price.
$("dock-cost").addEventListener("click", () => {
  const pop = dockPop($("dock-cost"));
  if (!pop) return;
  pop.append(mk("div", "pop-head", t("Tahmini harcama")));
  const tr = (n) => (n || 0).toLocaleString("tr-TR");
  const row = (text) => pop.append(mk("div", "pop-note", text));
  const turn = usage.tur, session = usage.oturum;
  if (!session || !session.cagri) {
    row(t("Bu oturumda henüz tur yok."));
  } else if (price) {
    if (isPremium()) row(t("Premium model: çıktı priceı $20/M üstünde."));
    row(t("Bu tur: ") + "≈" + money(turn ? costOf(turn) : 0)
      + " · " + t("oturum: ") + "≈" + money(costOf(session)));
    row(t("Girdi: ") + tr(session.girdi) + t(" token") + " × $"
      + (price.girdi * 1e6).toFixed(2) + "/M = " + money(session.girdi * price.girdi));
    row(t("Çıktı: ") + tr(session.cikti) + t(" token") + " × $"
      + (price.cikti * 1e6).toFixed(2) + "/M = " + money(session.cikti * price.cikti));
    row(t("Tahmin — önbellek indirimi hesaba katılmaz."));
  } else {
    row(t("Fiyat bilinmiyor — yalnız token sayısı."));
    row(t("Girdi: ") + tr(session.girdi) + t(" token")
      + " · " + t("Çıktı: ") + tr(session.cikti) + t(" token"));
  }
  pop.append(budgetField());
  placePop($("dock-cost"));
});

// Budget brake: it sits NEXT TO the spend, not on the settings page. The
// cap belongs to this session — tomorrow's conversation must not silently
// stop on yesterday's cap. Leaving it empty means unlimited. With an unknown
// price the brake cannot work, and we say so instead of hiding it.
function budgetField() {
  const box = mk("div", "pop-butce");
  box.append(mk("div", "pop-head", t("Bu oturum için üst sınır")));
  const row = mk("div", "pop-butce-row");
  const dollar = mk("span", "pop-butce-dolar", "$");
  const field = mk("input", "pop-butce-input");
  field.type = "text";
  field.inputMode = "decimal";
  field.placeholder = t("sınırsız");
  field.value = budget ? String(budget) : "";
  const save = mk("button", "pop-butce-ok", t("Uygula"));
  save.type = "button";
  const hint = mk("div", "pop-note", price
    ? t("Sınıra ulaşılınca koşan tur durur; yükseltince kaldığı yerden sürer.")
    : t("Fiyat bilinmiyor (yerel sunucu ya da katalog dışı model) — fren çalışmaz."));

  const apply = async () => {
    const raw = field.value.trim().replace(",", ".");
    const answer = await post("/api/butce", { usd: raw === "" ? null : raw });
    if (!answer || answer.ok === false) {
      hint.textContent = (answer && answer.error) || t("Sınır kaydedilemedi.");
      return;
    }
    budget = answer.butce == null ? null : Number(answer.butce);
    dockCost();
    hidePop();
  };
  save.addEventListener("click", apply);
  field.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); apply(); }
  });
  row.append(dollar, field, save);
  box.append(row, hint);
  return box;
}

// Learn-me chip: a quiet mark in the dock while training runs in the
// background. Done, it says "finished" for five seconds and vanishes — not
// a permanent badge.
let trainingTimer = null;
function trainingChip(state) {
  const chip = $("dock-tanima");
  if (!chip) return;
  clearTimeout(trainingTimer);
  if (state === "basladi") {
    chip.textContent = "· " + t("Tanıma eğitimi arka planda");
    chip.hidden = false;
  } else if (state === "bitti") {
    chip.textContent = "· " + t("Tanıma eğitimi tamamlandı");
    chip.hidden = false;
    trainingTimer = setTimeout(() => { chip.hidden = true; }, 5000);
  }
}

// --- dock popups --------------------------------------------------------
//
// Clicking a chip does not cycle, it lets you choose: a small box opens
// above the chip (like Claude Code's model/mode boxes). Cycling meant four
// clicks across five values; the box reaches the wanted value in one click
// and says what each option is.

let popFor = null;      // which chip it is open for
let lastUsage = null;   // last `usage` event, for the context detail

function mk(tag, cls, textContent) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (textContent !== undefined) node.textContent = textContent;
  return node;
}

// Opens the box and returns it empty; a second click on the same chip
// closes it (returns null). After content is added it is positioned with
// `placePop` — the width is only known once content is in.
function dockPop(anchor) {
  const pop = $("dock-pop");
  if (popFor === anchor && !pop.hidden) { hidePop(); return null; }
  popFor = anchor;
  pop.textContent = "";
  pop.className = "pop";
  pop.hidden = false;
  return pop;
}

function placePop(anchor) {
  const pop = $("dock-pop");
  // Above the chip, aligned to its left edge; pulled in if it overflows the right edge.
  const at = anchor.getBoundingClientRect();
  pop.style.left = Math.max(8, Math.min(at.left, window.innerWidth - pop.offsetWidth - 12)) + "px";
  pop.style.bottom = (window.innerHeight - at.top + 8) + "px";
}

function hidePop() {
  $("dock-pop").hidden = true;
  popFor = null;
}

document.addEventListener("click", (ev) => {
  const pop = $("dock-pop");
  if (pop.hidden) return;
  if (!pop.contains(ev.target) && !(popFor && popFor.contains(ev.target))) hidePop();
});
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") hidePop(); });

function popRow(name, hint, on, run) {
  const line = mk("div", "pop-row" + (on ? " on" : ""));
  line.append(mk("b", null, name));
  line.append(mk("span", null, hint || ""));
  if (on) line.append(mk("i", "tick", "✓"));
  line.addEventListener("click", () => { hidePop(); run(); });
  return line;
}

// Depth: what each level costs is written next to it.
const EFFORT_TELL = {
  low: "en hızlı — kısa düşünür",
  medium: "hızlı",
  high: "dengeli",
  xhigh: "derin",
  max: "en derin — en yavaş",
};

$("dock-effort").addEventListener("click", () => {
  const pop = dockPop($("dock-effort"));
  if (!pop) return;
  pop.append(mk("div", "pop-head", t("Düşünme derinliği")));
  for (const level of EFFORTS) {
    pop.append(popRow(level, t(EFFORT_TELL[level]), level === dockEffort, async () => {
      const was = dockEffort;
      dockEffort = level;
      dockRender();
      const answer = await post("/api/settings", { model: { effort: level } });
      if (answer && answer.ok === false) { dockEffort = was; dockRender(); }
    }));
  }
  placePop($("dock-effort"));
});

// Authority modes: same definitions as the settings page (settings.PERMISSION_MODES).
const MODE_TELL = {
  auto: "okuma serbest, yazma sorulur",
  ask: "en güvenlisi, en yavaşı",
  plan: "hiçbir şeyi değiştiremez",
  yolo: "hiçbir şey sorulmaz",
};

$("dock-mode").addEventListener("click", () => {
  const pop = dockPop($("dock-mode"));
  if (!pop) return;
  pop.append(mk("div", "pop-head", t("Yetki kipi")));
  for (const kind of MODE_ORDER) {
    pop.append(popRow(t(AUTHORITY[kind]), t(MODE_TELL[kind]), kind === mode, async () => {
      const was = mode;
      setAuthority(kind);
      const answer = await post("/api/settings", { permissions: { mode: kind } });
      if (answer && answer.ok === false) setAuthority(was);
    }));
  }
  placePop($("dock-mode"));
});

// Model: the provider's catalogue in a searchable list. Without a catalogue
// (local server down, no list) the path to the settings page remains.
$("dock-model").addEventListener("click", () => {
  const pop = dockPop($("dock-model"));
  if (!pop) return;
  pop.append(mk("div", "pop-head", "Model"));
  const note = mk("div", "pop-note", t("Katalog soruluyor…"));
  pop.append(note);
  placePop($("dock-model"));
  fillModelPop(pop, note);
});

// The UI note for auto mode. Shown ONLY with OpenRouter + "oto" selected;
// on another provider/model this warning has no business.
const AUTO_MODE_NOTE =
  "Oto modda OpenRouter'ın ücretsiz modelleri kullanılır; kalite ve hız " +
  "düşebilir, model istek sırasında değişebilir. Bazı ücretsiz uçlar " +
  "veriyi eğitimde kullanabilir; istekler 'veri toplama: reddet' " +
  "tercihiyle gönderilir.";

async function fillModelPop(pop, note) {
  let catalog = [];
  let provider = "";
  try {
    const s = await (await fetch("/api/settings")).json();
    provider = s.provider || "";
    const answer = await post("/api/models", {
      base_url: s.model.base_url,
      provider: s.model.provider,
      api_key_env: s.model.api_key_env,
    });
    catalog = (answer && answer.models) || [];
  } catch { /* handled below */ }
  if (popFor !== $("dock-model")) return;   // the box closed in the meantime

  // With auto selected, what it means is written at the top of the box.
  if (provider === "openrouter" && modelName === "oto") {
    pop.insertBefore(mk("div", "pop-note", t(AUTO_MODE_NOTE)), note);
  }

  if (!catalog.length) {
    note.textContent = t("Sunucu liste vermiyor — ayarlardan elle yazılır.");
    pop.append(popRow(t("Ayarları aç"), "", false, () => {
      $("gear").click();
      const tab = document.querySelector('[data-tab="model"]');
      if (tab) tab.click();
    }));
    return;
  }
  note.remove();

  // The pick is per-chat: every conversation can carry its own model, a new
  // chat inherits the last one's pick. The global default lives in settings.
  pop.append(mk("div", "pop-note", t(
    "Seçim bu sohbette kalır; yeni sohbet ve sonraki açılış onu devralır. Küresel varsayılan: Ayarlar → Model.")));
  const search = mk("input", "pop-search");
  search.type = "search";
  search.placeholder = catalog.length + " " + t("model içinde ara…");
  const list = mk("div", "pop-list");
  pop.append(search, list);

  const paint = () => {
    const want = search.value.trim().toLowerCase();
    list.textContent = "";
    let shown = 0;
    for (const item of catalog) {
      if (want && !item.id.toLowerCase().includes(want)) continue;
      if (++shown > 60) break;   // don't drown the DOM at 400+ models; search narrows
      list.append(popRow(item.id, "", item.id === modelName, async () => {
        const was = modelName;
        modelName = item.id;
        showMeta(); dockRender();
        // Written to the chat (meta) and the server applies it to the active
        // session INSTANTLY; without a session id (old flow) falls back to
        // the global setting.
        const answer = sessionId
          ? await post("/api/session/meta", { id: sessionId, model: item.id })
          : await post("/api/settings", { model: { name: item.id } });
        if (answer && answer.ok === false) { modelName = was; showMeta(); dockRender(); }
      }));
    }
    if (!shown) list.append(mk("div", "pop-note", t("Eşleşen yok.")));
    if (sessionId && !search.value.trim()) {
      list.append(popRow(t("↺ Küresel varsayılana dön"), "", false, async () => {
        await post("/api/session/meta", { id: sessionId, model: "" });
        loadState();   // let the real model come from the server
      }));
    }
  };
  search.addEventListener("input", paint);
  paint();
  placePop($("dock-model"));
  search.focus();
}

// Context chip: the same layout as Cursor's Context Usage box — header +
// close, percent/total, pill bar, line-by-line list.
$("dock-ctx").addEventListener("click", () => {
  const pop = dockPop($("dock-ctx"));
  if (!pop) return;
  pop.classList.add("pop-ctx");
  const head = mk("div", "pop-ctx-head");
  head.append(mk("span", null, t("Bağlam doluluğu")));
  const close = mk("button", "pop-ctx-kapat", "×");
  close.type = "button";
  close.setAttribute("aria-label", t("Kapat"));
  close.addEventListener("click", (ev) => { ev.stopPropagation(); hidePop(); });
  head.append(close);
  pop.append(head);
  const window_ = contextWindow;
  const breakdown = lastBreakdown || [];
  const used = ctxUsed(lastUsage ? lastUsage.prompt_total : 0, breakdown);
  const pct = window_ && used ? Math.min(100, Math.round(used / window_ * 100)) : 0;
  const sum = mk("div", "pop-ctx-sum");
  sum.append(mk("b", null, pct + "%" + t(" dolu")));
  sum.append(mk("span", null, "~" + shortNum(used) + " / " + shortNum(window_) + t(" token")));
  pop.append(sum);
  const bar = mk("div", "pop-bar pop-bar-seg");
  paintCtxBar(bar, breakdown, window_, used);
  pop.append(bar);
  for (const p of breakdown) {
    const row = mk("div", "pop-ctx-row");
    row.append(mk("i", "ctx-dot " + (p.id || "")));
    row.append(mk("span", "pop-ctx-ad", t(p.ad)));
    row.append(mk("b", "pop-ctx-n", shortNum(p.n)));
    pop.append(row);
  }
  placePop($("dock-ctx"));
});

// --- approval ---------------------------------------------------------
// The tool name and raw JSON do not answer "what am I allowing". For each
// tool we produce a sentence that says in plain Turkish what it will do.
const INTENT = {
  shell:      (a) => [t("Bir komut çalıştıracak."), a.command],
  read_file:  (a) => [t("Bir dosyayı okuyacak."), a.path],
  write_file: (a) => [t("Bir dosyanın üzerine yazacak."), a.path],
  edit_file:  (a) => [t("Bir dosyayı değiştirecek."), a.path],
  list_dir:   (a) => [t("Bir dizini listeleyecek."), a.path],
  mind_memory: (a) => a.action === "forget"
    ? [t("Zihninden bir kaydı silecek."), a.id]
    : [t("Zihnine kalıcı olarak yazacak."), a.content || a.title],
  mind_goals: (a) => [t("Hedef listesini güncelleyecek."), a.text || a.id],
};

function intentOf(tool, args) {
  const build = INTENT[tool];
  if (!build) return [`"${tool}" ` + t("aracını çalıştıracak."), ""];
  const [why, target] = build(args || {});
  return [why, target || ""];
}

overlay.addEventListener("click", (ev) => {
  const answer = ev.target.dataset ? ev.target.dataset.answer : null;
  if (!answer || !approvalId) return;
  post("/api/approve", {
    id: approvalId,
    granted: answer !== "no",
    // "always allow": don't ask again for the same tool and same target.
    always: answer === "always",
  });
  approvalId = null;
  overlay.hidden = true;
});

addEventListener("keydown", (ev) => {
  if (overlay.hidden || !approvalId) return;
  if (ev.key === "Escape") overlay.querySelector('[data-answer="no"]').click();
  if (ev.key === "Enter") overlay.querySelector('[data-answer="yes"]').click();
});

function askApproval(e) {
  approvalId = e.id;
  const args = e.args || {};
  const [why, target] = intentOf(e.tool, args);

  $("approve-why").textContent = why;
  $("approve-target").textContent = target;
  $("approve-target").hidden = !target;

  const tag = $("approve-kind");
  let label = e.mutates ? t("Değişiklik yapar · ") + e.tool : t("Salt okuma · ") + e.tool;
  // If the requester is a helper the user must see it: whom they are granting.
  if (e.channel && e.channel.title) label += "  [" + t("yardımcı") + ": " + e.channel.title + "]";
  tag.textContent = label;
  tag.className = "tag" + (e.mutates ? " mutates" : "");

  // Raw arguments only when the summary is not enough.
  const keys = Object.keys(args).filter(k => args[k] !== undefined);
  const box = $("approve-args");
  box.textContent = JSON.stringify(args, null, 2);
  box.hidden = keys.length <= 1 && !!target;

  overlay.hidden = false;
}

// --- missed scheduled tasks (startup question) -------------------------

let missedOpen = false;

function showMissedTasks(e) {
  const tasks = e.tasks || [];
  if (!tasks.length || missedOpen) return;
  missedOpen = true;
  $("missed-why").textContent = t(
    "Program kapalıyken zamanı geçmiş görevler var.");
  const list = $("missed-list");
  list.replaceChildren();
  for (const task of tasks) {
    const li = document.createElement("li");
    const name = task.title || task.id || "?";
    const desc = task.describe || "";
    li.textContent = desc ? name + " — " + desc : name;
    list.append(li);
  }
  $("missed-overlay").hidden = false;
}

async function resolveMissed(action) {
  $("missed-overlay").hidden = true;
  missedOpen = false;
  try {
    await fetch("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: action === "run" ? "missed_run" : "missed_skip",
      }),
    });
  } catch { /* no server */ }
  if (window.JobsPanel) JobsPanel.load();
}

$("missed-run")?.addEventListener("click", () => resolveMissed("run"));
$("missed-skip")?.addEventListener("click", () => resolveMissed("skip"));

// --- work strip -------------------------------------------------------
//
// Everything that happens in a turn gathers on a single line: thinking, tool
// calls and interim narration. The previous version left a separate line for
// every thought and every tool; a four-step job turned the chat into a
// fifteen-line staircase and the thing worth reading — the answer — got lost
// in between.
//
// Detail is not lost, it folds: clicking the header opens all of it.

let work = null;   // { head, body, steps, since, thought, open }

function ensureWork() {
  if (work) return work;
  clearWelcome();
  const head = document.createElement("div");
  head.className = "acts-head";
  const body = document.createElement("div");
  body.className = "acts-body";
  body.hidden = true;
  head.onclick = () => {
    // Opening an empty body looked like "nothing happened" (clicking the
    // header on a stepless, thoughtless turn was dead) — with no content in
    // the body the click is silently ignored, and the cursor says so (CSS).
    if (!body.childElementCount) return;
    body.hidden = !body.hidden;
    head.classList.toggle("open", !body.hidden);
    // The user clicked to read the strip: the opened BODY must come into
    // view — aligning only the header left the body below the screen out of
    // sight ("it doesn't open, it stays behind" — live complaint).
    if (!body.hidden) {
      // ONE click reaches the content: if the body consists only of thought
      // lines, the folded "✻ Düşündü · N sn" step in between is skipped and
      // the reasoning opens directly. The old version was two layers deep —
      // the user burned repeatedly on "clicking just adds a line below, I
      // can't get to the content" (31.08).
      const kids = [...body.children];
      const thinkingOnly = kids.length > 0
        && kids.every((c) => c.classList.contains("think"));
      if (thinkingOnly) {
        const last = kids[kids.length - 1];
        if (last.classList.contains("done") && !last.classList.contains("open")) {
          last.click();
        } else if (!last.classList.contains("done") && !last.classList.contains("open")) {
          // Live "Düşünüyor": opening the body is not enough — open the box too.
          last.classList.add("open");
          if (thought) {
            last.textContent = thought.trim();
            last.scrollTop = 0;
          }
        }
      }
      revealAboveComposer(body);
    } else {
      clearFitAboveComposer(body);
      for (const c of body.querySelectorAll(".think")) clearFitAboveComposer(c);
    }
  };
  thread.append(head, body);
  head.classList.add("busy");   // working: the header pulses
  work = { head, body, steps: 0, since: Date.now(), thought: null, open: new Map(),
           gone: null, trimmed: 0,
           // ALL of this turn's reasoning — including what opened no line.
           // Nothing is deleted: the threshold is only the line-opening rule.
           thinkAll: [] };
  return work;
}

// The strip advances with the flow (Claude Code layout): the live indicator
// always sits RIGHT ABOVE the newest content instead of being nailed to the
// top of the turn. If another top-level block slipped under the strip (an
// interjected message, an artifact card) the strip moves to the end of the
// flow — same DOM nodes; its steps and folded thoughts travel along intact.
function dockWork(w) {
  if (!w || !w.body) return;
  if (w.body.nextElementSibling || w.head.nextElementSibling !== w.body) {
    thread.append(w.head, w.body);
  }
}

// The answer started streaming: the strip calms down. The pulse stops, the
// header turns into a summary of the work so far, and the strip drops to the
// end of the flow so new text writes right below it. If the model thinks or
// calls a tool again mid-turn, think/actLine reanimates the header.
function restWork() {
  if (!work) return;
  dockWork(work);
  if (!work.open.size) {
    // Don't kill the pulse while the turn still runs: the "closed / opened"
    // feeling in the gap between tools came from here.
    if (busy) {
      if (!paintLive()) workHead(mull(), "", since(work.since) + streamNote());
      paintThinkLine();
      return;
    }
    work.head.classList.remove("busy");
    const phrase = activityPhrase(work);
    workHead(phrase || (work.steps ? stepsWord(work.steps) : t("Düşündü")),
             "", since(work.since));
    paintThinkLine();
  }
}

// The strip's live header: the current action + its target + step number.
// The user should read "what is happening / how many steps" without opening
// the strip — the old header only said the verb ("Çalıştırıyor…") and in a
// long turn the file and the step number only showed once the strip opened.
const HEAD_ARG = 72;

// The strip header carries two KINDS of parts, and they cannot share one
// typography:
//
//   * NARRATION — verb and counters ("Koşturuyor", "15 adım", "18 sn").
//   * TARGET — a command or file path. This is CODE: never uppercased.
//
// The structure is a flex row: [verb] [target…] [meta] — no wrapping in a
// narrow column; target ellipsized, meta fixed on the right.

// Tools whose target must render as code: command and file path.
const CODE_TOOLS = new Set([
  "shell", "bash", "powershell", "read_file", "read_many", "write_file", "edit_file",
  "list_dir", "grep", "search_files", "checkpoint", "git",
]);

// Shell wrappers: what the user cares about is what is INSIDE them. In
// "powershell -NoProfile -Command "netstat -ano"" the part worth reading is
// `netstat -ano`; the wrapper is the same in every command and eats space.
const WRAPPERS =
  /^\s*(?:(?:pwsh|powershell(?:\.exe)?|cmd(?:\.exe)?|bash|sh|zsh)\b(?:\s+-[\w-]+)*\s*(?:-Command|-c|\/c)\s*)/i;

function commandSummary(text) {
  let s = String(text || "").trim();
  const inner = s.replace(WRAPPERS, "");
  if (inner !== s) {
    s = inner.trim();
    // The wrapper quotes the command; the quotes belonged to the wrapper.
    if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'")))
      s = s.slice(1, -1).trim();
  }
  // First meaningful line of a multi-line command: the rest sits in the step card.
  const first = s.split("\n").map((r) => r.trim()).find(Boolean) || "";
  return first.length > HEAD_ARG ? first.slice(0, HEAD_ARG).trimEnd() + "…" : first;
}

// Header parts of the live line. None → null — the caller writes its own
// fallback.
//
// Cursor's language: instead of a single tool verb, the turn's summary
// ("4 dosya okuyor, 7 arama" / "Exploring 4 files, 7 searches"). With an
// open step the target sits as a chip; what is being scanned reads without
// opening the strip.
function liveHead() {
  if (!work) return null;
  const phrase = activityPhrase(work);
  const row = work.open.size ? [...work.open.values()][0] : null;
  if (!phrase && !row) return null;
  let target = "";
  let code = false;
  if (row) {
    const what = row.querySelector(".what").textContent;
    code = row.dataset.kod === "1";
    target = code ? commandSummary(what)
      : (what.length > HEAD_ARG ? what.slice(0, HEAD_ARG) + "…" : what);
  }
  return {
    verb: phrase || (row && row.querySelector(".who").textContent) || mull(),
    target, code,
    tail: "",
  };
}

// Paints the live header. With no live line to draw, false — the caller
// writes its fallback (stands in for the old `workHead(liveHead() || …)`
// pattern).
function paintLive(extra) {
  const live = liveHead();
  if (!live) return false;
  workHead(live.verb, live.target, (live.tail || "") + (extra || ""), live.code);
  paintThinkLine();
  return true;
}

// The turn's tool tally: Cursor's "Exploring 4 files, 7 searches" line.
// Counted so the verb is not locked to one step; readable with the strip
// closed too.
const TALLY_FILES = new Set(["read_file", "read_many", "list_dir"]);
const TALLY_SEARCH = new Set(["grep", "search", "fetch", "web", "semboller"]);
const TALLY_EDIT = new Set(["edit_file", "write_file"]);
const TALLY_RUN = new Set(["shell"]);

function tallyWork(w) {
  const n = { files: 0, searches: 0, edits: 0, runs: 0 };
  if (!w || !w.body) return n;
  for (const row of w.body.querySelectorAll(".act")) {
    if (row.classList.contains("note")) continue;
    const tool = (row._card && row._card.tool) || "";
    if (TALLY_FILES.has(tool)) n.files += 1;
    else if (TALLY_SEARCH.has(tool)) n.searches += 1;
    else if (TALLY_EDIT.has(tool)) n.edits += 1;
    else if (TALLY_RUN.has(tool)) n.runs += 1;
  }
  return n;
}

function _count(n, one, many) {
  return n + " " + (n === 1 ? one : many);
}

function activityPhrase(w) {
  const n = tallyWork(w);
  const en = Lang.mode === "en";
  if (en) {
    const bits = [];
    if (n.files) bits.push(_count(n.files, "file", "files"));
    if (n.searches) bits.push(_count(n.searches, "search", "searches"));
    if (n.edits) bits.push(_count(n.edits, "edit", "edits"));
    if (n.runs) bits.push(_count(n.runs, "command", "commands"));
    if (!bits.length) return "";
    if (n.edits && !n.files && !n.searches && !n.runs)
      return "Editing " + _count(n.edits, "file", "files");
    if (n.runs && !n.files && !n.searches && !n.edits)
      return "Running " + _count(n.runs, "command", "commands");
    return "Exploring " + bits.join(", ");
  }
  const bits = [];
  if (n.files) bits.push(n.files + " dosya okuyor");
  if (n.searches) bits.push(n.searches + " arama");
  if (n.edits) bits.push(n.edits + " düzenleme");
  if (n.runs) bits.push(n.runs + " komut");
  return bits.join(", ");
}

// The second line while no answer is being written: "Düşünüyor" — Cursor's Thinking.
function paintThinkLine() {
  if (!work) return;
  let sub = work.head.querySelector(":scope > .head-sub");
  const show = !!(busy && lastDelta !== "text" && !work.head.classList.contains("done")
    && (!work.open.size || lastDelta === "thinking"));
  if (!show) {
    if (sub) sub.hidden = true;
    return;
  }
  if (!sub) {
    sub = document.createElement("span");
    sub.className = "head-sub";
    work.head.append(sub);
  }
  sub.hidden = false;
  const label = lastDelta === "thinking" ? t("Akıl yürütüyor") : t("Düşünüyor");
  if (sub.textContent !== label) sub.textContent = label;
}

// DOM brake: the strip body must not grow without bound in a turn with
// hundreds of steps. The old ones collapse into one summary line — no step
// is lost, the count is written; when the strip opens the browser does not
// have to carry thousands of nodes.
const STEP_DOM_CAP = 200;

function trimSteps(w) {
  if (w.body.childElementCount <= STEP_DOM_CAP) return;
  if (!w.gone) {
    w.gone = document.createElement("div");
    w.gone.className = "act note gone";
    w.trimmed = 0;
    w.body.prepend(w.gone);
  }
  while (w.body.childElementCount > STEP_DOM_CAP) {
    const first = w.gone.nextElementSibling;
    if (!first || first === w.thought) break;
    if ([...w.open.values()].includes(first)) break;   // don't touch a running row
    if (first.querySelector && first.querySelector(".who")) w.trimmed += 1;
    first.remove();
  }
  w.gone.textContent = Lang.mode === "en"
    ? "… first " + w.trimmed + " steps folded"
    : "… ilk " + w.trimmed + " adım katlandı";
}

// The header refreshes on every step: while running, what is being done
// right now; when done, how many steps it took.
//
// Rebuilding the DOM every second (replaceChildren) made the command chip
// vanish and reappear — the user thought "the CLI keeps opening and
// closing". The three children are fixed; only text/class update.
function workHead(label, target, tail, code) {
  if (!work) return;
  const head = work.head;
  let verb = head.querySelector(":scope > .head-verb");
  let box = head.querySelector(":scope > .head-target");
  let meta = head.querySelector(":scope > .head-meta");
  if (!verb) {
    verb = document.createElement("span");
    verb.className = "head-verb";
    head.prepend(verb);
  }
  if (verb.textContent !== label) verb.textContent = label;

  if (!target) {
    if (box) box.hidden = true;
  } else {
    if (!box) {
      box = document.createElement(code ? "code" : "span");
      box.className = code ? "head-target kod" : "head-target";
      verb.after(box);
    } else {
      const want = code ? "CODE" : "SPAN";
      if (box.tagName !== want) {
        const next = document.createElement(code ? "code" : "span");
        next.className = code ? "head-target kod" : "head-target";
        box.replaceWith(next);
        box = next;
      } else {
        box.className = code ? "head-target kod" : "head-target";
      }
    }
    box.hidden = false;
    if (box.textContent !== target) box.textContent = target;
    box.title = target;
  }

  const metaText = tail ? String(tail).replace(/^\s*·\s*/, "") : "";
  if (!metaText) {
    if (meta) meta.hidden = true;
    return;
  }
  if (!meta) {
    meta = document.createElement("span");
    meta.className = "head-meta";
    const sub = head.querySelector(":scope > .head-sub");
    if (sub) head.insertBefore(meta, sub);
    else head.append(meta);
  }
  meta.hidden = false;
  if (meta.textContent !== metaText) meta.textContent = metaText;
}

// The "N steps" summary. The test greps the raw source (steps + " adım") —
// the unit expression lives here, and the English variant comes from here too.
const stepsWord = (steps) => Lang.mode === "en" ? steps + " steps" : steps + " adım";

// If all of the turn's thinking stayed under the threshold there is not a
// single thinking line in the strip — and then no door into the archive
// either. NOTHING must be LOST: as the turn closes, one collective line is
// added. One line per TURN, not per step: a door, not noise.
function sealThinkArchive(w) {
  if (!w.thinkAll.length) return;
  if (w.body.querySelector(".think")) return;   // a door is already open
  const row = document.createElement("div");
  row.className = "act note think done";
  const times = w.thinkAll.length;
  const label = t("✻ Düşündü") + " · " + times + t(" kez");
  row.textContent = label;
  row.title = t("Tıkla — bu turun muhakemesini gör");
  const archive = w.thinkAll;
  let open = false;
  row.onclick = (ev) => {
    ev.stopPropagation();
    open = !open;
    row.textContent = open ? archive.join("\n\n———\n\n") : label;
    row.classList.toggle("open", open);
    if (open) {
      row.scrollTop = 0;
      row.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  };
  w.body.append(row);
}

// As narration begins the strip splits: the finished cluster collapses to
// its own clickable summary ("3 adım · 12 sn" / "2 dosya okuyor, 1 komut"),
// new tools open a fresh cluster BELOW the text. A long run then reads with
// the "text / tool cluster / text" rhythm of Claude Code, and each cluster's
// detail opens from its own line.
function segmentWork() {
  if (!work) return;
  // No split while a tool runs or a wait is on — the live line is the one truth.
  if (work.open.size || waitState) { restWork(); return; }
  closeThought();
  const empty = !work.steps && !(work.thinkAll && work.thinkAll.length)
    && !work.body.childElementCount;
  if (empty) { work.head.remove(); work.body.remove(); work = null; return; }
  sealThinkArchive(work);
  const phrase = activityPhrase(work);
  workHead(phrase || (work.steps ? stepsWord(work.steps) : t("Düşündü")),
           "", since(work.since));
  work.head.classList.remove("busy", "wait", "open");
  work.head.classList.add("done");
  paintThinkLine();
  work.body.hidden = true;
  work = null;
}

function closeWork() {
  if (!work) return;
  // If the turn closed while waiting (interrupt) the wait row is sealed too.
  if (waitState) closeWait(null);
  // The empty strip setBusy opened early: if sealed before the user message
  // arrives, leave no "Düşündü ✓" ghost line — remove it silently.
  const empty = !work.steps && !(work.thinkAll && work.thinkAll.length)
    && !work.body.childElementCount;
  if (empty) {
    work.head.remove();
    work.body.remove();
    work = null;
    return;
  }
  sealThinkArchive(work);
  const phrase = activityPhrase(work);
  workHead(phrase || (work.steps ? stepsWord(work.steps) : t("Düşündü")),
           "", since(work.since));
  work.head.classList.remove("busy", "wait");   // the pulse stops
  work.head.classList.add("done");       // done: ✓
  paintThinkLine();
  // The turn ended: the body folds into the summary — even if the user had
  // opened it mid-turn. A finished turn's step flood left open in the chat
  // drowned the thing worth reading (the answer) again; the curious click
  // the header to reopen.
  work.body.hidden = true;
  work.head.classList.remove("open");
  work = null;
}

// MODEL TEXT IS ALWAYS VISIBLE.
//
// The distinction is NOT "mid-turn vs end-of-turn" — it is "who wrote it":
//
//   model  → a normal answer block in the chat (even if written between two
//            tool calls: every sentence addressed to the user)
//   harness→ in the strip or hidden (tool steps, recall trace, goal sync,
//            continuation nudge, job status)
//   the model thinking to itself → folded in the strip ("✻ Düşündü")
//
// The old version folded every text arriving BEFORE a tool into the strip
// and tried to bring it back with a "safety net" in `sealLine`. When the
// user asked "did it stop halfway?", Dornick wrote the answer, the answer
// folded into the strip and only "▸ HARMANLIYOR · 13 SN" remained on screen
// — the user had to open the strip to see the answer to their own question.
// The patch is gone, the source is fixed: text stays where it arrived, as a
// normal block.
//
// So the only thing done here is SEALING the streaming block: the block
// stays in the chat, the next step moves the strip BELOW it (dockWork).
function foldNarration() {
  finishAgentLine();
}

function actLine(e) {
  const w = ensureWork();
  foldNarration();
  // The strip follows the flow: if another block slipped in (artifact card,
  // interjected message) the live line is born below it, at the flow's tip.
  dockWork(w);
  w.head.classList.add("busy");
  // Fold the previous thinking block into one line and let the next block
  // take its own. (It used to be merely nulled and the full text stayed
  // full-size in the strip.)
  closeThought();
  w.steps += 1;

  const row = document.createElement("div");
  // `run`: the row is still working. Removed when done — a running row is
  // bright, a finished one dim; an eye on the strip reads the position from
  // colour.
  row.className = "act run";
  const spark = document.createElement("span"); spark.className = "spark";
  // Icon from the kind mapping, name from the intent verb: "Çalıştırıyor",
  // not "shell". The raw tool name is not lost — it sits on the row (title).
  spark.textContent = TOOL_ICON[e.tool] || "·";
  const verb = verbFor(e.tool);
  const who = document.createElement("span"); who.className = "who"; who.textContent = verb;
  who.title = e.tool;
  const what = document.createElement("span"); what.className = "what";
  what.textContent = summarize(e.input);
  what.title = t("Tıkla — adımın ayrıntısını gör");
  // Steps whose target is CODE (command, file path) get marked: the strip
  // header must draw it mono and as-is, without uppercasing. Clipping is
  // DISPLAY-only — the full command sits in the step card (row._card).
  if (CODE_TOOLS.has(e.tool)) { row.dataset.kod = "1"; what.classList.add("kod"); }
  const took = document.createElement("span"); took.className = "took";
  row.append(spark, who, what, took);

  w.body.append(row);
  row._start = Date.now();   // for the live duration: the ticker updates it every second
  // The raw data for the rich card travels on the row; drawing is lazy —
  // the card is only built when the row is clicked (toggleCard below).
  row._card = { tool: e.tool, input: e.input || {} };
  row.onclick = () => toggleCard(row);
  w.open.set(e.id, row);
  paintLive();
  trimSteps(w);
  scroll();
  Scene.ripple();
}

function closeAct(e) {
  if (!work) return;
  const row = work.open.get(e.id);
  work.open.delete(e.id);
  if (row) {
    row.classList.remove("run");
    row.classList.add(e.error ? "err" : "ok");
    const took = row.querySelector(".took");
    if (took && e.ms != null) took.textContent = Math.round(e.ms) + " ms";
    if (row._card) { row._card.detail = e.detail || null; row._card.error = !!e.error; }

    // File change: like Cursor, a clear trace + diff card under the row.
    const tool = row._card && row._card.tool;
    if (tool === "edit_file" || tool === "write_file") {
      const trace = fileChangeTrace(row._card, e);
      if (trace) {
        const old = row.nextElementSibling;
        if (old && old.classList.contains("act-result")) old.remove();
        trace.onclick = () => toggleCard(row);
        row.after(trace);
      }
      if (!e.error) openCard(row);   // show the diff on its own
    } else if (e.summary) {
      const existing = row.nextElementSibling;
      if (existing && existing.classList.contains("act-result")) existing.remove();
      const trace = document.createElement("div");
      trace.className = "act-result" + (e.error ? " err" : "");
      requestAnimationFrame(() => trace.scrollIntoView({ block: "nearest", behavior: "smooth" }));
      trace.textContent = "⎿ " + e.summary;
      trace.onclick = () => toggleCard(row);
      row.after(trace);
    }
    // Refresh an open card in place (no close-open flicker).
    if (row._cardEl) refreshCard(row);
  }
  if (!paintLive()) {
    workHead(busy ? mull() : (activityPhrase(work) || stepsWord(work.steps)),
             "", since(work.since) + (busy ? streamNote() : ""));
    paintThinkLine();
  }
}

// after edit/write: "+3 −1 · path" — click for diff / content.
function fileChangeTrace(card, e) {
  const path = (card.input && card.input.path) || e.path || "";
  const name = String(path).replace(/\\/g, "/").split("/").pop() || path;
  if (!name && !e.summary) return null;
  const stats = diffStats(card);
  const line = document.createElement("div");
  line.className = "act-result file-change" + (e.error ? " err" : "");
  const mark = document.createElement("span");
  mark.className = "file-mark";
  mark.textContent = card.tool === "write_file" ? "✎" : "±";
  const file = document.createElement("span");
  file.className = "file-name";
  file.textContent = name || t("dosya");
  file.title = path;
  line.append(mark, file);
  if (stats) {
    const chip = document.createElement("span");
    chip.className = "file-stats";
    if (stats.add) {
      const a = document.createElement("b");
      a.className = "add"; a.textContent = "+" + stats.add;
      chip.append(a);
    }
    if (stats.del) {
      const d = document.createElement("b");
      d.className = "del"; d.textContent = "−" + stats.del;
      chip.append(d);
    }
    if (stats.line) {
      chip.append(document.createTextNode(" · L" + stats.line));
    }
    line.append(chip);
  } else if (e.summary) {
    line.append(document.createTextNode(" · " + e.summary));
  }
  // A way to REACH the produced file: open · show in folder. When the agent
  // wrote a report the user could neither open nor find it — only the path
  // was written (live wound, 02.09).
  if (path && !e.error) line.append(fileActions(path));
  return line;
}

// The small actions to the right of the file row. The event is stopped so
// the click does not trigger the row's own toggle.
function fileActions(path) {
  const box = document.createElement("span");
  box.className = "file-acts";
  const make = (label, hint, endpoint) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "file-act";
    b.textContent = label;
    b.title = t(hint);
    b.onclick = async (ev) => {
      ev.stopPropagation();
      let c = null;
      try {
        c = await (await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path }),
        })).json();
      } catch { /* server silent */ }
      if (!c || c.ok === false) {
        b.classList.add("bad");
        b.title = (c && c.error) || t("Açılamadı");
        setTimeout(() => b.classList.remove("bad"), 4000);
      }
    };
    return b;
  };
  box.append(
    make("↗", "Varsayılan uygulamada aç", "/api/apps/file-open"),
    make("🗂", "Klasörde göster", "/api/apps/reveal"),
  );
  return box;
}

function diffStats(card) {
  if (!card || card.tool !== "edit_file") {
    if (card && card.tool === "write_file") {
      const n = String(card.input.content || "").split("\n").length;
      return { add: n, del: 0, line: 1 };
    }
    return null;
  }
  const pairs = editPairs(card.input);
  let add = 0, del = 0;
  for (const [oldT, newT] of pairs) {
    const o = String(oldT || "").split("\n");
    const n = String(newT || "").split("\n");
    // Simple: changed line count (an upper bound before trimming the common prefix/suffix).
    del += o.length;
    add += n.length;
    // Subtract the common ends — more accurate +/- .
    let pre = 0;
    while (pre < o.length && pre < n.length && o[pre] === n[pre]) pre++;
    let post = 0;
    while (post < o.length - pre && post < n.length - pre
           && o[o.length - 1 - post] === n[n.length - 1 - post]) post++;
    del -= pre + post;
    add -= pre + post;
  }
  const line = card.detail && card.detail.line;
  return { add: Math.max(0, add), del: Math.max(0, del), line: line || null };
}

function editPairs(input) {
  if (!input) return [];
  if (Array.isArray(input.edits) && input.edits.length)
    return input.edits.map((e) => [e.old, e.new]);
  if ("old" in input || "new" in input) return [[input.old, input.new]];
  return [];
}

// --- model wait state -------------------------------------------------
//
// An outage prints NO error wall into the chat (Claude Code behaviour): the
// wait lives in the work strip itself. The strip's live header turns into a
// countdown state ("MODEL BEKLENİYOR · DENEME 4/5 · 118 SN" — the pulse in
// warning tone) while the error is ONE row in the step list: every retry
// updates the same row, and a click opens the raw detail in a height-capped
// code card. When the model returns, the same row turns green ("model came
// back · after N attempts") and the strip resumes its normal flow.

let waitState = null;   // {phase, attempt, total, deadline, row, detail}

function waitHead() {
  if (!waitState) return "";
  const left = Math.max(0, Math.ceil((waitState.deadline - Date.now()) / 1000));
  const secs = left > 0 ? left + " sn" : t("yeniden deneniyor…");
  if (waitState.phase === "park")
    return t("İş bekletiliyor — model erişilebilir olunca sürecek") + " · " + secs;
  return t("Model bekleniyor") + " · " + t("deneme") + " "
       + waitState.attempt + "/" + waitState.total + " · " + secs;
}

// The countdown runs in the header: tickBusy calls here every second — no
// new rows pile up, the SAME header stays live.
function paintWait() {
  if (waitState) workHead(waitHead());
}

function onWaiting(e) {
  if (e.kip === "bitti" || e.kip === "iptal") { closeWait(e); return; }

  const w = ensureWork();
  foldNarration();
  dockWork(w);
  closeThought();
  w.head.classList.add("busy", "wait");

  if (!waitState) {
    // The outage section's single step row: later attempts update it.
    const row = document.createElement("div");
    row.className = "act wait-adim";
    const spark = document.createElement("span");
    spark.className = "spark"; spark.textContent = "⏳";
    const who = document.createElement("span");
    who.className = "who"; who.textContent = t("Model çağrısı");
    const what = document.createElement("span"); what.className = "what";
    const took = document.createElement("span"); took.className = "took";
    row.append(spark, who, what, took);

    // The raw error: HIDDEN by default; a click-to-open, height-capped,
    // self-scrolling code card — the same gesture as the other step cards.
    const detail = document.createElement("pre");
    detail.className = "wait-detay";
    detail.hidden = true;
    row.title = t("Tıkla — hatanın ayrıntısını gör");
    row.onclick = (ev) => {
      ev.stopPropagation();
      detail.hidden = !detail.hidden;
      row.classList.toggle("opened", !detail.hidden);
      scroll();
    };

    w.body.append(row, detail);
    w.steps += 1;
    waitState = { row, detail };
    scroll();
  }

  waitState.phase = e.kip;
  waitState.attempt = e.deneme || 0;
  waitState.total = e.toplam || 0;
  waitState.deadline = Date.now() + (e.saniye || 0) * 1000;

  const brief = String(e.detay || "").split("\n")[0];
  waitState.row.querySelector(".what").textContent =
    brief.length > HEAD_ARG ? brief.slice(0, HEAD_ARG) + "…" : brief;
  waitState.row.querySelector(".took").textContent = e.kip === "park"
    ? t("bekletiliyor")
    : t("deneme") + " " + waitState.attempt + "/" + waitState.total;
  waitState.detail.textContent = e.detay || "";
  // The scene and top strip must tell the same truth: not a frozen
  // "Düşünüyor" but the wait state (like Claude Code's status line).
  setMode("thinking", e.kip === "park" ? t("İş bekletiliyor") : t("Model bekleniyor"));
  // The "Model yükleniyor…" sentinel tells the wrong story here: nothing
  // streams but the reason is known — the model is BEING WAITED FOR. The
  // sentinel is silenced.
  waiting(false);
  paintWait();
}

// The wait ended: "bitti" → the row turns green and the strip returns to
// normal; "iptal" → the row dims. In both cases the warning tone leaves the
// header.
function closeWait(e) {
  if (!waitState) return;
  const { row } = waitState;
  waitState = null;
  if (e && e.kip === "bitti") {
    row.classList.add("ok");
    row.querySelector(".spark").textContent = "✓";
    row.querySelector(".who").textContent = t("Model geri geldi");
    row.querySelector(".what").textContent =
      e.deneme ? e.deneme + t(" deneme sonrası") : "";
    row.querySelector(".took").textContent = "";
  } else {
    row.classList.add("err");
    row.querySelector(".took").textContent = t("kesildi");
  }
  if (work) {
    work.head.classList.remove("wait");
    if (!paintLive()) workHead(mull(), "", since(work.since) + streamNote());
    paintThinkLine();
  }
  // If the turn continues, the scene/top strip returns to the normal thinking flow.
  if (busy) setMode("thinking");
}

// --- step cards -------------------------------------------------------
//
// A step's row is a one-line trace; clicking opens the real operation:
// a highlighted command + its output + exit badge in the shell, a diff with
// the real old/new lines for an edit, a content preview for read/write, an
// argument table for other tools. Drawing is LAZY — the card is built on
// first open; folded, only one row exists in the DOM. The card is HEIGHT-
// CAPPED and scrolls within itself: a long output does not push the chat
// pages away (the "I open the detail, the latest things disappear"
// complaint). Toggling adds/removes below the row so the reading position
// does not shift.

function toggleCard(row) {
  if (!row._card) return;
  if (row._cardEl) {
    row._cardEl.remove();
    row._cardEl = null;
    row.classList.remove("opened");
    return;
  }
  openCard(row);
}

function openCard(row) {
  if (!row._card || row._cardEl) return;
  const box = buildCard(row._card);
  const next = row.nextElementSibling;
  const anchor = next && next.classList.contains("act-result") ? next : row;
  anchor.after(box);
  row._cardEl = box;
  row.classList.add("opened");
  // The card is usually born below the fold: bring it into view — this was
  // the root of the "I clicked and nothing happened" feeling.
  requestAnimationFrame(() => box.scrollIntoView({ block: "nearest", behavior: "smooth" }));
}

function refreshCard(row) {
  if (!row._card || !row._cardEl) return;
  const fresh = buildCard(row._card);
  row._cardEl.replaceWith(fresh);
  row._cardEl = fresh;
}

// No highlighting above this size: tokenisation runs on the main thread and
// noticeably delays the card opening on a huge output.
const CARD_PAINT_MAX = 20000;

function codeBlock(text, lang) {
  const pre = el2("pre", "card-code");
  const code = el2("code");
  if (lang && text.length <= CARD_PAINT_MAX && typeof Syntax !== "undefined") {
    Syntax.paint(code, text, lang);
  } else {
    code.textContent = text;
  }
  pre.append(code);
  return pre;
}

function outBlock(text) {
  const pre = codeBlock(String(text));
  pre.classList.add("card-out");
  return pre;
}

// Highlighting language from the file extension; unrecognised stays plain text.
function extLang(path) {
  const name = String(path || "");
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : "";
}

// Diff: the common head/tail is trimmed, the changed core drawn with little
// context. The line numbers are real: the server says where in the file the
// change sits (`line` in the edit_file result); otherwise counted from 1.
const DIFF_CTX = 2;

function diffBlock(card) {
  const wrap = el2("div", "card-diff-wrap");
  const path = card.input.path || "";
  const stats = diffStats(card);
  const bar = el2("div", "diff-bar");
  const title = el2("span", "diff-file", String(path).replace(/\\/g, "/").split("/").pop() || path);
  title.title = path;
  bar.append(title);
  if (stats) {
    const chips = el2("span", "diff-chips");
    if (stats.add) chips.append(el2("b", "add", "+" + stats.add));
    if (stats.del) chips.append(el2("b", "del", "−" + stats.del));
    if (stats.line) chips.append(document.createTextNode("L" + stats.line));
    bar.append(chips);
  }
  const actions = el2("span", "diff-actions");
  if (path && (card.tool === "edit_file" || card.tool === "write_file")) {
    const keep = el2("button", "diff-btn keep", t("Keep"));
    const undo = el2("button", "diff-btn undo", t("Undo"));
    keep.type = "button";
    undo.type = "button";
    keep.onclick = (ev) => {
      ev.stopPropagation();
      const cardEl = wrap.closest(".act-card");
      if (cardEl) cardEl.classList.add("kept");
      keep.disabled = true;
      undo.disabled = true;
    };
    undo.onclick = async (ev) => {
      ev.stopPropagation();
      undo.disabled = true;
      keep.disabled = true;
      let answer = null;
      if (typeof Changes !== "undefined" && Changes.cardUndoFile) {
        answer = await Changes.cardUndoFile(path);
      }
      if (!answer || answer.ok === false) {
        line("alert", (answer && answer.error) || t("Fark okunamadı."));
        undo.disabled = false;
        keep.disabled = false;
        return;
      }
      const cardEl = wrap.closest(".act-card");
      if (cardEl) cardEl.classList.add("undone");
    };
    actions.append(keep, undo);
  }
  if (path && typeof Viewer !== "undefined" && Viewer.present) {
    const open = el2("button", "diff-open", t("Dosyayı aç"));
    open.type = "button";
    open.onclick = (ev) => {
      ev.stopPropagation();
      Viewer.present(path);
    };
    actions.append(open);
  }
  bar.append(actions);
  wrap.append(bar);

  const pairs = editPairs(card.input);
  let lineBase = Number(card.detail && card.detail.line) || 1;
  if (!pairs.length) {
    if (card.tool === "write_file") {
      wrap.append(codeBlock(String(card.input.content || ""), extLang(path)));
      return wrap;
    }
    wrap.append(el2("div", "diff-empty", t("Diff yok — old/new gelmedi")));
    return wrap;
  }
  pairs.forEach(([oldT, newT], idx) => {
    if (pairs.length > 1) {
      wrap.append(el2("div", "diff-part", (idx + 1) + ". " + t("değişiklik")));
    }
    wrap.append(diffHunk(oldT, newT, idx === 0 ? lineBase : 1));
  });
  return wrap;
}

function diffHunk(oldText, newText, start) {
  const oldLines = String(oldText || "").split("\n");
  const newLines = String(newText || "").split("\n");
  let pre = 0;
  while (pre < oldLines.length && pre < newLines.length
         && oldLines[pre] === newLines[pre]) pre += 1;
  let post = 0;
  while (post < oldLines.length - pre && post < newLines.length - pre
         && oldLines[oldLines.length - 1 - post] === newLines[newLines.length - 1 - post]) post += 1;

  const box = el2("div", "card-diff");
  for (let i = Math.max(0, pre - DIFF_CTX); i < pre; i++) {
    box.append(diffRow(start + i, " ", oldLines[i]));
  }
  for (let i = pre; i < oldLines.length - post; i++) {
    box.append(diffRow(start + i, "-", oldLines[i]));
  }
  for (let i = pre; i < newLines.length - post; i++) {
    box.append(diffRow(start + i, "+", newLines[i]));
  }
  for (let i = 0; i < Math.min(DIFF_CTX, post); i++) {
    const at = oldLines.length - post + i;
    box.append(diffRow(start + at, " ", oldLines[at]));
  }
  if (!box.childElementCount) {
    box.append(diffRow(start, " ", t("(içerik aynı)")));
  }
  return box;
}

function diffRow(no, mark, text) {
  const row = el2("div", "diff-row" + (mark === "-" ? " del" : mark === "+" ? " add" : ""));
  row.append(el2("span", "diff-no", String(no)));
  row.append(el2("span", "diff-mark", mark));
  row.append(el2("span", "diff-text", text == null ? "" : text));
  return row;
}

// A readable argument table for unknown tools.
function argsBlock(input) {
  const table = el2("div", "card-args");
  for (const [key, value] of Object.entries(input || {}).slice(0, 12)) {
    const row = el2("div", "arg-row");
    row.append(el2("b", null, key));
    const flat = typeof value === "string" ? value : JSON.stringify(value);
    row.append(el2("span", null, flat.length > 400 ? flat.slice(0, 400) + "…" : flat));
    table.append(row);
  }
  return table;
}

function buildCard(card) {
  const box = el2("div", "act-card");

  const head = el2("div", "card-head");
  const toolLabel = ({
    shell: "shell", edit_file: t("düzenleme"), write_file: t("yazma"),
    read_file: t("okuma"), list_dir: t("dizin"),
  })[card.tool] || card.tool;
  head.append(el2("b", null, toolLabel));
  const target = card.input.path || card.input.command || card.input.url || card.input.query;
  if (typeof target === "string" && target) {
    const pathEl = el2("span", "card-path", clipArg(target));
    pathEl.title = target;
    head.append(pathEl);
  }
  const code = card.detail ? card.detail.exit_code : undefined;
  if (code !== undefined) {
    head.append(el2("i", "card-exit" + (code ? " err" : ""), t("çıkış ") + code));
  } else if (card.error) {
    head.append(el2("i", "card-exit err", t("hata")));
  }
  // Copy: what sits on the card is the FULL form (the command itself with
  // its wrapper, the file content, or the arguments). The clipping in the
  // strip header is display-only; the data here must be complete and
  // takeable.
  const copy = el2("button", "card-copy", "⧉");
  copy.type = "button";
  copy.title = t("Kopyala");
  copy.onclick = (ev) => {
    ev.stopPropagation();
    const text = card.input.command || card.input.content
      || card.input.path || JSON.stringify(card.input, null, 2);
    navigator.clipboard.writeText(String(text)).then(() => {
      copy.textContent = "✓";
      setTimeout(() => { copy.textContent = "⧉"; }, 1200);
    }).catch(() => { copy.title = t("Kopyalanamadı"); });
  };
  head.append(copy);

  const grow = el2("button", "card-grow", "⤢");
  grow.type = "button";
  grow.title = t("Tümünü genişlet");
  grow.onclick = (ev) => {
    ev.stopPropagation();
    box.classList.toggle("full");
    grow.title = box.classList.contains("full") ? t("Kartta kaydır") : t("Tümünü genişlet");
  };
  head.append(grow);
  box.append(head);

  const output = card.detail && card.detail.output;
  if (card.tool === "shell") {
    const cmd = codeBlock(String(card.input.command || ""), "powershell");
    cmd.classList.add("shell-cmd");
    box.append(cmd);
    if (output) box.append(outBlock(output));
  } else if (card.tool === "edit_file") {
    box.append(diffBlock(card));
  } else if (card.tool === "write_file") {
    box.append(diffBlock(card));
  } else if (card.tool === "read_file") {
    // Read output already arrives line-numbered; shown as-is.
    if (output) box.append(outBlock(output));
  } else {
    box.append(argsBlock(card.input));
    if (output) box.append(outBlock(output));
  }

  // Clicking inside the card (selecting text) must not trigger the row's toggle.
  box.addEventListener("click", (ev) => ev.stopPropagation());
  return box;
}

// --- organs -----------------------------------------------------------
//
// The agent's devices sit dimly on the scene: microphone, cameras, speaker,
// the modules it wrote for itself. The mapping lives here so that when a
// tool is called it is visible which one was touched — the server says
// which tool uses which organ, nothing is assumed here.
let limbs = [];

async function loadOrgans() {
  try {
    const answer = await (await fetch("/api/organs")).json();
    limbs = answer.organs || [];
    Scene.organs(limbs);
  } catch { /* no server response, no organ list */ }
}

const organFor = (tool) =>
  (limbs.find((limb) => (limb.tools || []).includes(tool)) || {}).id || null;

// The argument summary on the tool row. HARD-capped: a 40 KB write_file
// content must not enter the DOM — the row is one line anyway, the rest is
// noise.
const ARG_CAP = 120;
const clipArg = (s) => {
  const flat = String(s).replace(/\s+/g, " ").trim();
  return flat.length > ARG_CAP ? flat.slice(0, ARG_CAP) + "…" : flat;
};

function summarize(args) {
  if (!args) return "";
  for (const key of ["command", "path", "query", "url", "action", "target", "text", "content"]) {
    if (typeof args[key] === "string" && args[key].trim()) return clipArg(args[key]);
  }
  const keys = Object.keys(args);
  if (!keys.length) return "";
  const first = args[keys[0]];
  if (typeof first === "string" || typeof first === "number") return clipArg(first);
  return keys.length + t(" argüman");
}

// --- goal panel ---------------------------------------------------------
//
// The visible form of the goal stack in the mind (like Claude Code's to-do
// list): as the agent opens and closes goals via mind_goals, a small
// checklist lives at the chat's top right. The panel is event-driven — it
// advances on the SSE goal_push/goal_status events; on page refresh it is
// seeded with the active goals in /api/state. With no goals the panel never
// shows; a finished item first stays struck through, then quietly drops a
// few seconds later.

const GOAL_SHOW = 6;        // items shown; the rest is "…+N"
const GOAL_LINGER = 6000;   // finished/dropped items fall after this many ms

// In a narrow window the panel folds by itself: the chat column already
// takes the full width and an open list eats space above the text.
const GOAL_FOLD_WIDTH = 1020;   // same as the narrow-window threshold in CSS

// The folded/open preference is remembered: having to make the same call on
// every launch is tiring.
const GOAL_FOLD_KEY = "dornick.goals.folded";

// The panel explains ITSELF. This was the user's question: "I don't know
// who creates these tasks". The answer should stay on screen.
const GOAL_DESCRIPTION =
  "Dornick'nun uzun işlerde kendi yazdığı adım listesi (Cursor görev listesi gibi). "
  + "Sohbet geçmişi değil — madde yoksa sekme de yok. Sen de ekleyip silebilirsin.";

const Goals = (() => {
  const items = new Map();   // id → { text, status, eski } — in insertion order
  // FOLDED BY DEFAULT: the panel is born as one line ("3 iş listesi"), the
  // curious open it. A panel born open shoved a list the user never asked
  // for into their face on every launch.
  let folded = true;
  try {
    const saved = localStorage.getItem(GOAL_FOLD_KEY);
    if (saved !== null) folded = saved === "1";
  } catch { /* private tab / storage off: the default stays folded */ }
  if (window.innerWidth <= GOAL_FOLD_WIDTH) folded = true;
  let clearArmed = false;    // "clear all" is two-step: the second click applies

  function rememberFold() {
    try { localStorage.setItem(GOAL_FOLD_KEY, folded ? "1" : "0"); }
    catch { /* without storage the choice lasts this session */ }
  }

  // An item's action to the server: the same ledger the agent uses.
  function ask(action, id, text) {
    const payload = { action };
    if (id) payload.id = id;
    if (text) payload.text = text;
    return fetch("/api/goals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) => r.json()).catch(() => ({ ok: false }));
  }

  // Item action: ✓ done, × remove. The screen reacts immediately
  // (optimistic); if the server rejects, the item reverts.
  function act(id, action) {
    const got = items.get(id);
    if (!got) return;
    const prev = got.status;
    got.status = action === "done" ? "done" : "dropped";
    render();
    ask(action, id).then((res) => {
      if (res && res.ok) { settle(id); return; }
      got.status = prev;   // the server declined: put the truth back
      render();
    });
  }

  // Viewer tab (plan:goals): no floating card — never sits on the terminal.
  function paint(host) {
    if (!host) return;
    host.textContent = "";
    const pane = document.createElement("div");
    pane.className = "goals-pane";
    const rows = [...items.entries()];
    const done = rows.filter(([, g]) => g.status === "done").length;
    const head = document.createElement("div");
    head.className = "goals-pane-head";
    head.textContent = t("İş listesi") + (rows.length ? " · " + done + "/" + rows.length : "");
    head.title = t("Dornick'in kendine yazdığı iş listesi — tıkla: katla/aç");
    pane.append(head);
    const what = document.createElement("p");
    what.className = "goals-what";
    what.textContent = t(GOAL_DESCRIPTION);
    pane.append(what);
    if (!rows.length) {
      const blank = document.createElement("p");
      blank.className = "viewer-blank";
      blank.textContent = t("Aktif madde yok.");
      pane.append(blank);
    } else {
      let running = false;
      for (const [id, g] of rows.slice(0, 40)) {
        const row = document.createElement("div");
        const now = g.status === "active" && !running;
        if (now) running = true;
        row.className = "plan-step " + g.status + (now ? " now" : "");
        const mark = document.createElement("i");
        mark.textContent = g.status === "done" ? "✓"
          : g.status === "dropped" ? "×" : now ? "●" : "○";
        const label = document.createElement("span");
        label.textContent = g.text;
        label.title = g.text;
        row.append(mark, label);
        if (g.status === "active") {
          row.append(goalBtn("✓", t("Tamamlandı"), () => act(id, "done")),
                     goalBtn("×", t("Kaldır"), () => act(id, "drop")));
        }
        pane.append(row);
      }
      if (rows.length > 40) {
        const more = document.createElement("div");
        more.className = "plan-step more";
        more.textContent = "…+" + (rows.length - 40);
        pane.append(more);
      }
    }
    pane.append(addRow());
    if (rows.length) {
      const clear = document.createElement("button");
      clear.type = "button";
      clear.className = "goals-clear" + (clearArmed ? " armed" : "");
      clear.textContent = clearArmed ? t("Emin misin?") : t("tümünü temizle");
      clear.onclick = (ev) => {
        ev.stopPropagation();
        if (!clearArmed) { clearArmed = true; paint(host); return; }
        clearArmed = false;
        ask("clear").then((res) => { if (res && res.ok) items.clear(); render(); });
      };
      pane.append(clear);
    }
    host.append(pane);
  }

  function renderViewer() {
    if (typeof Viewer === "undefined" || !Viewer.hostedGoals || !Viewer.hostedGoals()) return;
    const el = document.getElementById("viewer-body");
    if (el) paint(el);
  }

  function render() {
    renderViewer();
    if (typeof Viewer !== "undefined" && Viewer.setGoalsPin)
      Viewer.setGoalsPin(items.size > 0);
    const box = $("goals");
    if (!box) return;
    if (!items.size) { box.hidden = true; clearArmed = false; return; }
    box.hidden = false;
    const active = [...items.values()].filter((g) => g.status === "active").length;
    $("goals-head").textContent = folded
      ? "◷ " + (active || items.size) + t(" iş listesi")
      : t("İş listesi") + (active ? " · " + active : "");
    $("goals-head").title = t("Dornick'in kendine yazdığı adım listesi — tıkla: katla/aç");
    box.classList.toggle("folded", folded);
    const body = $("goals-body");
    body.hidden = folded;
    if (folded) return;
    body.textContent = "";

    const what = document.createElement("p");
    what.className = "goals-what";
    what.textContent = t(GOAL_DESCRIPTION);
    body.append(what);

    const rows = [...items.entries()];
    rows.slice(0, GOAL_SHOW).forEach(([id, g]) => {
      const row = document.createElement("div");
      row.className = "goal-item " + g.status;
      const mark = document.createElement("i");
      mark.textContent = g.status === "done" ? "✓" : g.status === "dropped" ? "×" : "○";
      const label = document.createElement("span");
      label.textContent = g.text;
      label.title = g.text + (g.status === "done" ? " — " + t("tamamlandı")
                            : g.status === "dropped" ? " — " + t("bırakıldı") : "");
      row.append(mark, label);
      if (g.eski) {
        const badge = document.createElement("span");
        badge.className = "goal-eski";
        badge.textContent = t("eski");
        badge.title = t("Geçen oturumlardan kaldı");
        row.append(badge);
      }
      if (g.status === "active") {
        row.append(goalBtn("✓", t("Tamamlandı"), () => act(id, "done")),
                   goalBtn("×", t("Kaldır"), () => act(id, "drop")));
      }
      body.append(row);
    });
    if (rows.length > GOAL_SHOW) {
      const more = document.createElement("div");
      more.className = "goal-more";
      more.textContent = "…+" + (rows.length - GOAL_SHOW);
      body.append(more);
    }
    const clear = document.createElement("button");
    clear.type = "button";
    clear.className = "goals-clear" + (clearArmed ? " armed" : "");
    clear.textContent = clearArmed ? t("Emin misin?") : t("tümünü temizle");
    clear.onclick = (ev) => {
      ev.stopPropagation();
      if (!clearArmed) { clearArmed = true; render(); return; }
      clearArmed = false;
      ask("clear").then((res) => {
        if (res && res.ok) { items.clear(); }
        render();
      });
    };
    body.append(clear);
    body.append(addRow());
  }

  function addRow() {
    const wrap = document.createElement("div");
    wrap.className = "goals-add";
    const field = document.createElement("input");
    field.type = "text";
    field.placeholder = t("＋ kendi maddeni yaz");
    field.setAttribute("aria-label", t("Yeni iş maddesi"));
    const submit = () => {
      const text = field.value.trim();
      if (!text) return;
      field.value = "";
      ask("add", "", text).then((res) => {
        if (res && res.ok && res.id) items.set(res.id, { text, status: "active" });
        render();
      });
    };
    field.onkeydown = (ev) => {
      ev.stopPropagation();
      if (ev.key === "Enter") { ev.preventDefault(); submit(); }
    };
    field.onclick = (ev) => ev.stopPropagation();
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "＋";
    btn.title = t("Ekle");
    btn.onclick = (ev) => { ev.stopPropagation(); submit(); };
    wrap.append(field, btn);
    return wrap;
  }

  function goalBtn(sign, label, onClick) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "goal-act";
    b.textContent = sign;
    b.title = label;
    b.setAttribute("aria-label", label);
    b.onclick = (ev) => { ev.stopPropagation(); onClick(); };
    return b;
  }

  function settle(id) {
    setTimeout(() => { items.delete(id); render(); }, GOAL_LINGER);
  }

  function seed(list) {
    items.clear();
    for (const g of list || []) {
      if (g && g.id) items.set(g.id, { text: g.text || g.id, status: "active", eski: !!g.eski });
    }
    render();
  }

  function push(id, text) {
    if (!id) return;
    items.set(id, { text: text || id, status: "active" });
    render();
  }

  function status(id, state) {
    const got = items.get(id);
    if (!got) return;
    got.status = state === "done" ? "done" : "dropped";
    render();
    settle(id);
  }

  $("goals-head").addEventListener("click", () => {
    folded = !folded;
    rememberFold();
    render();
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth <= GOAL_FOLD_WIDTH && !folded) folded = true;
    render();
  });

  return { seed, push, status, paint };
})();

// --- artifact card ------------------------------------------------------
//
// When the agent publishes a permanent page, a card lands in the chat:
// title, version badge and Open. The card does not drift away like a chat
// line — when the same artifact updates NO new card is printed; the
// existing one is found and its badge refreshed (v1 → v2). Clicking opens
// the page in the in-app viewer from its live server address
// (/artifact/<id>/).

function artifactAddress(e) {
  return e.address || "/artifact/" + e.id + "/";
}

function openArtifact(e) {
  Viewer.page(artifactAddress(e), e.title || e.id);
}

// Document glyph: a page with a folded corner. Building and printing a
// markup string is forbidden (model output must never be interpreted as
// markup — test_static holds this); the glyph is built with the DOM API.
// The gallery in apps.js uses it too.
function artGlyphSvg() {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  for (const d of ["M3.5 1.5h6L13 5v9.5h-9.5z", "M9.5 1.5V5H13", "M5.5 8.5h5M5.5 11h5"]) {
    const path = document.createElementNS(NS, "path");
    path.setAttribute("d", d);
    path.setAttribute("fill", "none");
    svg.append(path);
  }
  return svg;
}

// Retriggers the badge animation: removing the class and putting it back a
// frame later makes it flash on back-to-back updates too.
function reflash(node) {
  node.classList.remove("flash");
  void node.offsetWidth;
  node.classList.add("flash");
}

function artifactCard(e) {
  if (!e.id) return;
  clearWelcome();

  const found = thread.querySelector('.artifact-card[data-id="' + e.id + '"]');
  if (found) {
    // Update: the card stays in place; the title and badge refresh.
    found.querySelector(".art-title").textContent = e.title || e.id;
    const badge = found.querySelector(".art-badge");
    badge.textContent = "v" + (e.surum || 1) + " · " + t("güncellendi");
    badge.classList.add("fresh");
    found._art = e;
    reflash(found);
    // If the page is open in the viewer right now, show the new version at once.
    if (Viewer.showing && Viewer.showing(artifactAddress(e))) openArtifact(e);
    scroll();
    return;
  }

  const card = el2("div", "artifact-card");
  card.dataset.id = e.id;
  card._art = e;
  card.setAttribute("role", "button");
  card.tabIndex = 0;
  card.title = t("Tıkla — sayfayı görüntüleyicide aç");

  const glyph = el2("span", "art-glyph");
  glyph.append(artGlyphSvg());

  const main = el2("div", "art-main");
  main.append(el2("div", "art-title", e.title || e.id));
  const meta = el2("div", "art-meta");
  meta.append(el2("span", "art-kind", t("Artifact")));
  const addr = el2("span", "art-addr", artifactAddress(e));
  // The full address shows on hover and copies on click — the card clips it.
  addr.title = location.origin + artifactAddress(e);
  addr.style.cursor = "copy";
  addr.addEventListener("click", async (ev) => {
    ev.stopPropagation();
    try {
      await navigator.clipboard.writeText(location.origin + artifactAddress(card._art));
      note(t("Adres kopyalandı ✓"));
    } catch { /* no clipboard permission */ }
  });
  meta.append(addr);
  main.append(meta);

  const badge = el2("span", "art-badge",
    "v" + (e.surum || 1) + " · " + t(e.surum > 1 ? "güncellendi" : "yayınlandı"));

  const open = el2("button", "art-open", t("Aç"));
  open.type = "button";
  open.setAttribute("aria-label", t("Aç") + " — " + (e.title || e.id));

  const ext = el2("button", "art-open art-export", t("Tarayıcıda aç"));
  ext.type = "button";
  ext.title = t("Gerçek tarayıcıda aç");
  const dl = el2("button", "art-open art-export", t("İndir"));
  dl.type = "button";
  dl.title = t("İndir") + " (.html)";
  const pr = el2("button", "art-open art-export", t("Yazdır / PDF"));
  pr.type = "button";

  card.append(glyph, main, badge, open, ext, dl, pr);

  const go = (ev) => { ev.stopPropagation(); openArtifact(card._art); };
  card.addEventListener("click", go);
  open.addEventListener("click", go);
  ext.addEventListener("click", (ev) => {
    ev.stopPropagation();
    // The real port lives on the server: the agent's URL guess proved wrong live.
    if (Viewer.openOutside) Viewer.openOutside(artifactAddress(card._art));
  });
  dl.addEventListener("click", (ev) => {
    ev.stopPropagation();
    const url = artifactAddress(card._art);
    if (Viewer.downloadArtifact) Viewer.downloadArtifact(url);
    else window.location.href = url + (url.includes("?") ? "&" : "?") + "download=1";
  });
  pr.addEventListener("click", (ev) => {
    ev.stopPropagation();
    const url = artifactAddress(card._art);
    if (Viewer.printPage) Viewer.printPage(url);
    else window.open(url, "_blank", "noopener");
  });
  card.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openArtifact(card._art); }
  });
  thread.append(card);
  reflash(card);
  scroll();
}

const deferredPlans = new Map();

function planCard(e) {
  if (!e || !e.id) return;
  clearWelcome();
  // Don't print the card mid-turn: the model is still writing text; the card
  // ended up above with "more stuff" dropping under it. Flush when the turn
  // ends.
  if (busy) {
    deferredPlans.set(e.id, e);
    const found = thread.querySelector('.plan-card[data-id="' + e.id + '"]');
    if (found) applyPlanData(found, e);
    return;
  }
  showPlanCard(e);
}

function flushDeferredPlans() {
  if (!deferredPlans.size) {
    pinPlanCards();
    return;
  }
  const batch = [...deferredPlans.values()];
  deferredPlans.clear();
  for (const e of batch) showPlanCard(e);
  pinPlanCards();
}

function pinPlanCards() {
  // ONLY cards awaiting a decision move to the end of the chat (above the
  // plan-apply offer). An approved/finished/cancelled card stays where it
  // was born in the flow — live complaint: work done, answer in, and the
  // approved plan card dropped again with its buttons BELOW the answer
  // ("what does that have to do with anything").
  const offer = planOffer;
  for (const card of [...thread.querySelectorAll(".plan-card")]) {
    if (!planPending(card)) continue;
    if (offer && offer.parentNode === thread) thread.insertBefore(card, offer);
    else thread.append(card);
  }
}

function planPending(card) {
  const status = (card._plan && card._plan.status) || "bekliyor";
  return status === "bekliyor";
}

function applyPlanDecision(card) {
  // Decision buttons have no business on a decided card: Approve/Edit/Cancel
  // only show in the "bekliyor" state.
  const acts = card.querySelector(".plan-acts");
  if (acts) acts.style.display = planPending(card) ? "" : "none";
}

function applyPlanData(card, e) {
  card._plan = e;
  const title = card.querySelector(".plan-title");
  const status = card.querySelector(".plan-status");
  if (title) title.textContent = e.title || e.id;
  if (status) status.textContent = e.status || "";
  if (!card.querySelector(".plan-edit")) renderPlanSteps(card, e);
  applyPlanDecision(card);
}

function showPlanCard(e) {
  const found = thread.querySelector('.plan-card[data-id="' + e.id + '"]');
  if (found) {
    applyPlanData(found, e);
    pinPlanCards();
    return;
  }
  const card = el2("div", "plan-card");
  card.dataset.id = e.id;
  card._plan = e;
  const head = el2("div", "plan-head");
  head.append(el2("span", "plan-kind", t("Plan")));
  head.append(el2("span", "plan-title", e.title || e.id));
  head.append(el2("span", "plan-status", e.status || "bekliyor"));
  card.append(head);
  renderPlanSteps(card, e);
  const acts = el2("div", "plan-acts");
  const ok = el2("button", "plan-btn", t("Onayla"));
  ok.type = "button";
  ok.onclick = async (ev) => {
    ev.stopPropagation();
    await fetch("/api/plans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "approve", id: e.id }),
    });
  };
  const edit = el2("button", "plan-btn", t("Düzenle"));
  edit.type = "button";
  edit.onclick = (ev) => {
    ev.stopPropagation();
    enterPlanEdit(card);
  };
  const cancel = el2("button", "plan-btn muted", t("İptal"));
  cancel.type = "button";
  cancel.onclick = async (ev) => {
    ev.stopPropagation();
    await fetch("/api/plans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "cancel", id: e.id }),
    });
  };
  // "Save as automation" is deliberately absent: turning a one-off project
  // plan into a recurring automation made no sense and confused the user
  // ("why would I have this project done repeatedly?"). The place to build
  // automations is the flow editor (Tasks) — not the plan card.
  acts.append(ok, edit, cancel);
  card.append(acts);
  thread.append(card);
  applyPlanDecision(card);
  pinPlanCards();
  scroll();
}

function enterPlanEdit(card) {
  if (card.querySelector(".plan-edit")) return;
  const plan = card._plan || {};
  const steps = (plan.steps || []).map((s) => (s.text || s)).join("\n");
  const list = card.querySelector(".plan-steps");
  if (list) list.remove();
  const acts = card.querySelector(".plan-acts");
  if (acts) acts.hidden = true;

  const box = el2("div", "plan-edit");
  const ta = document.createElement("textarea");
  ta.className = "plan-edit-area";
  ta.rows = Math.min(14, Math.max(4, steps.split("\n").length + 1));
  ta.value = steps;
  ta.setAttribute("aria-label", t("Adımları düzenle (satır = adım)"));
  const row = el2("div", "plan-edit-acts");
  const save = el2("button", "plan-btn", t("Kaydet"));
  save.type = "button";
  const abort = el2("button", "plan-btn muted", t("Vazgeç"));
  abort.type = "button";
  row.append(save, abort);
  box.append(ta, row);
  if (acts) card.insertBefore(box, acts);
  else card.append(box);
  ta.focus();

  const leave = () => {
    box.remove();
    if (acts) acts.hidden = false;
    renderPlanSteps(card, card._plan || plan);
  };
  abort.onclick = (ev) => { ev.stopPropagation(); leave(); };
  save.onclick = async (ev) => {
    ev.stopPropagation();
    const listSteps = ta.value.split("\n").map((s) => s.trim()).filter(Boolean);
    save.disabled = true;
    try {
      await fetch("/api/plans", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "update", id: plan.id || card.dataset.id, steps: listSteps,
        }),
      });
      card._plan = {
        ...plan,
        steps: listSteps.map((text, i) => ({ id: "s" + (i + 1), text, status: "bekliyor" })),
      };
    } finally {
      leave();
    }
  };
}

function renderPlanSteps(card, e) {
  let list = card.querySelector(".plan-steps");
  if (!list) {
    list = el2("ol", "plan-steps");
    const acts = card.querySelector(".plan-acts");
    if (acts) card.insertBefore(list, acts);
    else card.append(list);
  }
  list.replaceChildren();
  // Step status is visible (live request): ✓ done, ▸ in progress, ○ waiting.
  // As the agent marks via the `plan` tool's step action the card advances
  // live — on an approved plan, "which stage are we at" reads from here.
  for (const s of e.steps || []) {
    const st = (s && s.status) || "bekliyor";
    const li = el2("li", "plan-step " + st);
    li.append(el2("span", "plan-tick",
                  st === "bitti" ? "✓" : st === "yapiliyor" ? "▸" : "○"));
    li.append(el2("span", null, s.text || s.title || String(s)));
    list.append(li);
  }
}

// --- plan mode: the approval loop ---------------------------------------
//
// When a turn ends in plan mode, a "▶ Planı uygula" button appears under the
// last answer (Claude Code's plan-approval loop). Clicking flips the
// authority mode back to the one before plan (auto if unknown) and sends the
// "Planı uygula." message automatically. If the user types themselves or the
// mode leaves plan, the button quietly disappears — no stale offer stays on
// screen.

let planOffer = null;

function maybeOfferPlan() {
  if (mode !== "plan") return;
  hidePlanOffer();
  const row = document.createElement("div");
  row.className = "plan-apply";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = "▶ " + t("Planı uygula");
  btn.addEventListener("click", applyPlan);
  const hint = document.createElement("span");
  hint.className = "plan-hint";
  hint.textContent = t("Plan hazır — uygulamak yetki ister");
  row.append(btn, hint);
  thread.append(row);
  planOffer = row;
  scroll();
}

function hidePlanOffer() {
  if (planOffer) { planOffer.remove(); planOffer = null; }
}

async function applyPlan() {
  const back = beforePlan === "plan" ? "auto" : beforePlan;
  const was = mode;
  hidePlanOffer();
  setAuthority(back);
  // Mode first: if the server rejects the change, the message must never go
  // — saying "Planı uygula." while in plan mode drives the model into the
  // read-only gate again.
  const answer = await post("/api/settings", { permissions: { mode: back } });
  if (answer && answer.ok === false) { setAuthority(was); return; }
  post("/api/chat", { text: t("Planı uygula.") });
  resumeFollow(false);
}

// --- event flow -------------------------------------------------------
// Event types carrying chat CONTENT: these are drawn only on their own
// session's screen. The server stamps every piece of content with the
// session id (sid); if the id does not match the open screen the event is
// DROPPED — on a quick chat switch, old chunks waiting in the queue mixed
// into the new chat (live wound, 01.09: "it even blends with the previous
// conversation"). Approval requests are deliberately not on the list: a
// background lane's permission must be asked too.
const CHAT_ONLY = new Set([
  "assistant_delta", "thinking_delta", "message", "tool_start", "tool_end",
  "tool_cancelled", "queued", "araya", "artifact", "plan", "bekleme",
  "child_start", "child_tool", "child_wait", "turn_end", "recall_trace",
  "api_error", "interrupted", "empty_assistant_turn", "turn_limit", "refusal",
]);

// Prime injection (Phase 6.3): the ids of the last prime note, drawn as a
// line into the context window once their recall walk has landed.
let primeIds = null, primeTimer = null;

function handle(e) {
  if (CHAT_ONLY.has(e.type) && e.sid && sessionId && e.sid !== sessionId) {
    return;   // a piece of another chat — never drawn on this screen
  }
  switch (e.type) {
    case "assistant_delta":
      lastDelta = "text";
      turnActivity = true;
      // The strip does not close: the model calls a tool, writes, calls a
      // tool again — opening a new strip each time brought the staircase back.
      closeThought();
      // The model does the recognising: the preview's label comes from the
      // answer's first sentence, not from the browser.
      if (Camera.on) Camera.say(firstClause(e.text));
      write(e.text);
      // While text streams the scene must be writing too; the timer rebuilt
      // on every chunk falls back to thinking by itself once the stream stops.
      setMode("writing", undefined, 1200);
      // Spoken sentence by sentence as they complete: waiting for the whole
      // answer would be an announcement, not a conversation.
      Speech.feed(e.text);
      break;

    // The thinking channel is separate: while reasoning, the model is not writing yet.
    case "thinking_delta": waiting(false); lastDelta = "thinking"; turnActivity = true;
      think(e.text); setMode("thinking", undefined, 2500); break;

    // A message waiting in the queue. A message sent while busy does not
    // vanish silently: it shows with a "queued · N" badge and turns into the
    // real row when its turn comes. The user sees at a glance what happened
    // (it queued, and at what position) — no "what happened to it" wondering.
    case "queued": {
      const row = line("user waiting", e.text);
      const badge = document.createElement("span");
      badge.className = "queue-badge";
      row.appendChild(badge);
      waitingLines.push({ text: e.text, row, badge });
      renumberQueue();
      break;
    }

    // Interjection: a message typed while busy went not into the queue but
    // INTO the RUNNING turn (as a harness note). The bubble draws like a
    // normal user message + a small "interjected" badge. Since it never sits
    // in history as a user message there is no message-echo match; the row
    // here is permanent. The strip is pulled right below it so "work goes on
    // in the background / you interjected" reads at a single glance.
    case "araya": {
      if (agentLine) finishAgentLine();
      closeThought();
      const row = line("user", e.text);
      const badge = document.createElement("span");
      badge.className = "queue-badge araya";
      badge.textContent = t("araya girdi");
      row.appendChild(badge);
      if (work) {
        dockWork(work);
        work.head.classList.add("busy");
        workHead(t("Araya alındı") + " · " + (work.steps
          ? stepsWord(work.steps) + since(work.since)
          : t("İşleniyor") + since(work.since)));
        // If the strip is folded, don't force it open — just clarify the position.
        revealAboveComposer(work.head);
      }
      break;
    }

    case "message":
      // The second defence (`drawable`): if the server filter ever misses, an
      // internal note — a harness nudge — is NOT drawn as a user bubble. The
      // server side already filters via the `internal`/`continuation` marks;
      // this is the safety behind that filter.
      if (e.role === "user" && drawable(e.text)) {
        // Its turn came: the waiting row is replaced with the real one.
        const at = waitingLines.findIndex((w) => w.text === e.text);
        if (at >= 0) { waitingLines[at].row.remove(); waitingLines.splice(at, 1); renumberQueue(); }
        // A new turn begins: the pending "apply plan" offer went stale (the
        // user spoke their own words, or the offer was already used).
        hidePlanOffer();
        sealLine();
        resetStream();          // new turn: the live token counter from zero
        // New turn: the "what changed this turn" strip's boundary starts here.
        chgTurnStart();
        const row = line("user", e.text);
        const media = pendingMedia.get(e.text);
        if (media) { attachMedia(row, media); pendingMedia.delete(e.text); scroll(); }
        // If the busy status arrived BEFORE the user row, sealLine may have
        // removed the empty strip — reopen the live line immediately.
        if (busy) kickWork();
      }
      else if (e.role === "system") note(e.text);
      break;

    case "tool_start": {
      turnActivity = true;
      if (e.tool === "hand" || e.tool === "screen") controlGlow(+1);
      actLine(e);
      setMode("working", verbFor(e.tool) || t("Çalışıyor"));
      // If a device is in use, that organ comes alive on the scene: the
      // dim camera or module lights up on a signal from the core.
      const limb = organFor(e.tool);
      if (limb) Scene.use(limb, summarize(e.input));
      // If the agent touched a file, the panel switches to that file:
      // reading the sentence "I wrote it" is not the same as seeing the file.
      if (typeof Viewer !== "undefined" && Viewer.feed) Viewer.feed(e);
      Viewer.watch(e.tool, e.input);
      break;
    }
    case "tool_end": {
      if (e.tool === "hand" || e.tool === "screen") controlGlow(-1);
      closeAct(e);
      if (typeof Viewer !== "undefined" && Viewer.feed) Viewer.feed(e);
      Viewer.refresh(e.tool, e.path);
      if (typeof GitBar !== "undefined") GitBar.touched(e.tool);
      if (busy) setMode("thinking");
      const done = organFor(e.tool);
      // The trace is not erased at once: it lingers on the scene a few
      // seconds so what was used stays readable.
      if (done) setTimeout(() => Scene.release(done), 4000);
      break;
    }
    case "tool_cancelled": closeAct({ ...e, error: true, ms: 0 }); break;

    // An artifact was published or updated: a permanent card lands in the
    // chat. An update of the same artifact prints no new card — it refreshes
    // the existing card's badge (no duplicate cards flooding the chat).
    case "artifact": artifactCard(e); break;
    case "plan": planCard(e); break;
    case "git":
      if (typeof GitBar !== "undefined") GitBar.refresh();
      break;
    case "session_title":
      // The model set the title: the sidebar list updates without a page refresh.
      if (typeof History !== "undefined" && History.applyTitle)
        History.applyTitle(e.id, e.title);
      break;

    // In-app update: download progress + install start. Paints the status
    // line in Settings if open, and the sidebar badge in any case.
    case "guncelleme":
      updateStatus(e);
      break;

    // The session changed (new or resumed): the thread is cleared; for a
    // resumed conversation the past transcript loads so the user sees where
    // they left off.
    case "session_reset": {
      sessionId = e.id || "";
      thread.replaceChildren();
      waitingLines.length = 0;
      work = null; agentLine = null; raw = ""; waitState = null;
      planOffer = null;   // the button left with the thread; keep no reference
      deferredPlans.clear();
      // Per-chat leftovers go too: the pending-media map is keyed by text —
      // an image queued in A stuck to a message typed with the same words in
      // B. The half-finished thinking buffer also belongs to the old chat.
      pendingMedia.clear();
      thought = "";
      // The transcript sentinel resets: when a second reset arrives for the
      // same id (the screen was just cleared) the load must not assume
      // "already drawn" and leave a blank screen.
      transcriptFor = "";
      resumeFollow(false);   // fresh transcript: follow on from the start
      // The counters are per-chat: old spend must not dangle in a new
      // conversation; in a resumed chat loadState writes the past total.
      usage = { tur: null, oturum: null };
      budget = null;
      dockCost();
      // A resumed session: the COUNTERS must resume just like the transcript.
      // The state snapshot seeds the context bar and the spend chip from the
      // session log — otherwise a full conversation showed "%0" / "$0".
      if (e.resumed && e.id) { loadTranscript(e.id); loadState(); }
      else showWelcome();   // fresh session: bring the welcome back (not a blank screen)
      // The rail is a permanent column: switching conversations does NOT
      // close it ("I click a conversation, the sidebar goes away" — live
      // complaint; the second root was here). On a wide screen the list
      // refreshes so the "currently open" mark moves; only in a narrow
      // window does the overlay close.
      if (typeof History !== "undefined") {
        if (innerWidth <= 860) History.close(); else History.open();
      }
      // The session changed: the change ledger's boundary must be set to the
      // new session's ledger too — the previous conversation's records must
      // not blend into this turn's summary.
      if (typeof Changes !== "undefined") Changes.takeBase();
      // The folder/git context is per-chat: in a new conversation the old
      // repo name (Dornick / branch) must not dangle above the composer.
      if (typeof GitBar !== "undefined") GitBar.refresh();
      break;
    }
    // "Cut in on Dornick": someone interjected with the wake word while
    // Dornick was talking — the TTS must hush instantly so the user is heard
    // (it does not cut the turn; the command queues).
    case "ack":
      Speech.ack();
      break;
    case "hush":
      Speech.stop();
      break;
    // First-run guidance: the model was never called; the server points the
    // way. Drawn like an assistant line (not an alert strip) — this is the
    // answer to the user's question.
    case "setup_hint": {
      clearWelcome();
      const el = line("agent", t(e.text));
      el.classList.add("done");
      break;
    }
    case "notice": clearWelcome(); line("alert", e.text); break;
    // Model outage: NO line lands in the chat — the work strip's live header
    // turns into the state; the detail lives in the strip's step row.
    case "bekleme": onWaiting(e); break;
    // The api_error note in the log is NOT printed into the chat: a
    // transient error lives in the strip's wait row (raw detail on click)
    // and a fatal one already arrives as a notice. This event used to dump a
    // raw JSON wall into the chat — "someone unfamiliar would think it
    // crashed".
    case "api_error": break;
    case "refusal": clearWelcome(); line("alert", t("Model bu isteği reddetti.")); break;
    case "interrupted":
      clearWelcome();
      // Cut the voice too: text stopping while the speaker finishes the
      // sentence is like someone interrupted who keeps on talking.
      Speech.stop();
      // The stream stopped halfway: the block is SEALED. It used not to be,
      // and the half-finished (usually empty) "DORNICK ▮" block blinked on
      // screen forever — as if still writing in an interrupted turn.
      sealLine();
      line("alert", t("Kesildi."));
      break;

    // The model returned nothing (it only reasoned and stopped). The loop
    // grants a continuation turn; the UI's only job is to clean up the open
    // empty block and its cursor — otherwise an empty "DORNICK ▮" hangs on
    // screen for the whole continuation turn.
    case "empty_assistant_turn":
      finishAgentLine();
      clearCursor();
      break;

    case "approval_request": askApproval(e); break;
    case "approval_done":
      if (e.id === approvalId) { overlay.hidden = true; approvalId = null; }
      break;

    case "status": setBusy(e.busy); break;
    case "waking": setWaking(e.stage, e.ready); break;

    // Orchestra: subagent channels (conductor mode). They stay out of the
    // main chat; they are watched live on the orchestra deck.
    case "child_start": orchStart(e); tasksRefresh(); break;
    case "child_tool": orchTool(e);
      if (typeof Tasks !== "undefined" && Tasks.refresh) Tasks.refresh();
      if (window.JobsPanel && JobsPanel.refreshLive) JobsPanel.refreshLive();
      break;
    // A finished channel goes two places: the orchestra stage (the card
    // closes) and the task ledger (the row updates; a background job drops a
    // clickable notice into the chat).
    case "child_end":
      orchEnd(e); tasksDone(e);
      if (window.JobsPanel) JobsPanel.load();
      // App/artifact delivery: the live product instead of a weak 2-line report.
      if (e.ok && e.deliverable && e.deliverable.url && typeof Viewer !== "undefined") {
        const d = e.deliverable;
        if (d.kind === "app" || d.kind === "artifact") {
          Viewer.page(d.url, e.title || d.url);
        }
      }
      break;
    case "child_wait":
      if (typeof Tasks !== "undefined" && Tasks.refresh) Tasks.refresh();
      if (typeof Orchestra !== "undefined" && Orchestra.wait) Orchestra.wait(e);
      if (window.JobsPanel && JobsPanel.refreshLive) JobsPanel.refreshLive();
      break;
    // Show / Tasks from the tray: runs finished in the background must be visible.
    case "open_jobs":
      if (window.JobsPanel) JobsPanel.open();
      break;
    case "jobs_refresh":
      if (window.JobsPanel) JobsPanel.load();
      break;
    case "missed_tasks":
      showMissedTasks(e);
      break;
    case "missed_resolved":
      $("missed-overlay").hidden = true;
      missedOpen = false;
      break;
    // The server sent the real channel list (orphans found at startup): the
    // panel rebuilds — the page snapshot loaded during startup may have been
    // taken before the agent was ready.
    case "channels": orchSeed(e.channels || []); break;
    case "lane":
      // Parallel lane status: keeps the sidebar badge live.
      if (typeof History !== "undefined" && History.laneChanged)
        History.laneChanged(e);
      break;
    // The level the Python-side ear hears: the microphone icon comes alive,
    // showing that listening continues in the background.
    case "level": showLevel(e.value); break;
    case "hearing":
      setMicDeaf(!!e.snoozed);
      if ("live" in e || "enabled" in e)
        paintHear(!!(e.live || (e.enabled && (e.open || e.wake) && !e.snoozed)));
      break;
    case "voice":
      setVoice(!!e.enabled);
      break;
    case "camera":
      if (typeof Cameras !== "undefined" && Cameras.status) Cameras.status(e);
      break;
    case "turn_end":
      sealLine(); Speech.flush();
      // A turn finished in plan mode has left a plan: the apply offer.
      maybeOfferPlan();
      // Turn over: if files changed this turn, drop the one-line summary.
      chgTurnEnd();
      // If something runs in the background, the badge must tell the truth.
      tasksRefresh();
      break;

    // The path the agent actually walked: nodes fire in this order.
    case "recall_trace": {
      lastQuery = e.query || "";
      // The scene itself knows how long the walk takes; a number guessed
      // here went wrong every time the step duration changed.
      const walk = Scene.activate(e.trace) || 0;
      setMode("recalling", undefined, walk + 400);
      // Prime injection (Phase 6.3): once the walk lands, what was found
      // flows from the hippocampus into the context window.
      if (primeIds) {
        clearTimeout(primeTimer);
        const ids = primeIds; primeIds = null;
        primeTimer = setTimeout(() => Scene.inject(ids), walk);
      }
      break;
    }

    // The prime note lands just before its trace; the injection line is
    // drawn at the end of the walk. Without a trace (nothing to animate)
    // the line still flows, a moment later.
    case "prime":
      primeIds = Array.isArray(e.ids) ? e.ids : [];
      clearTimeout(primeTimer);
      primeTimer = setTimeout(() => { if (primeIds) { Scene.inject(primeIds); primeIds = null; } }, 2500);
      break;

    // open(): the record glows; a cold one warms in from the ring.
    case "mind_open":
      if (typeof Regions !== "undefined") Regions.opened(e.memory_id, e.kind);
      break;

    // Writing is also motion in the web: a signal from the core to the new
    // record. The graph refreshes first, else the target node is not there yet.
    // The amygdala flashes with the record's surprise (Phase 6.3); an event
    // without a surprise value gets a middling flash.
    case "mind_write":
      Scene.load(() => Scene.deposit(e.memory_id));
      if (typeof Regions !== "undefined") Regions.amygdala(e.surpriz ?? e.surprise ?? e.guc);
      break;

    // A night event on the live channel: the same feed a replay uses.
    case "gece":
      if (typeof Night !== "undefined") Night.feed([e.olay || e]);
      break;

    case "mind_forget":
      Scene.ripple(); Scene.load(); break;

    // The goal stack changed: a ripple on the scene + the top-right checklist
    // + the prefrontal strip (Phase 6.3).
    case "goal_push":
      Goals.push(e.goal_id, e.text);
      if (typeof Regions !== "undefined") Regions.goalAdded(e.goal_id, e.text);
      Scene.ripple(); Scene.load(); break;
    case "goal_status":
      Goals.status(e.goal_id, e.status);
      if (typeof Regions !== "undefined") Regions.goalStatus(e.goal_id, e.status);
      Scene.ripple(); Scene.load(); break;

    // The authority mode changed outside the UI (settings page, external
    // gate): the dock chip and the plan-approval button must match reality.
    case "mode":
      if (e.mode && e.mode !== mode) setAuthority(e.mode);
      break;

    // The agent deliberately linked two records: a new bridge was built in
    // the web. Refreshing the graph is not enough — the built link must show.
    case "mind_link":
      Scene.ripple();
      Scene.load(() => Scene.bridge(e.src, e.dst));
      note(t("Köprü: ") + (e.reason || t("bağlandı")));
      break;

    case "device_removed":
      loadOrgans();
      document.dispatchEvent(new CustomEvent("dornick:devices"));
      break;

    // Learn-me: the personal fine-tune started/finished in the background
    // (or was toggled from the settings page). Not worth a chat line; the
    // chip under the composer + the top-bar icon show the state quietly.
    case "tanima":
      trainingChip(e.state); trainingIcon(e.state);
      if (typeof Regions !== "undefined") Regions.patch(e.state);
      break;

    case "usage":
      if (e.prompt_total) {
        tokenNote = e.prompt_total.toLocaleString("tr-TR") + t(" token")
          + (e.cache_read ? " · " + e.cache_read.toLocaleString("tr-TR") + t(" önbellek") : "");
        showMeta();
        dockContext(e.prompt_total, false, e.kirilim);
        lastUsage = e;
      }
      // Cost chip: turn/session totals and the price tag arrive in the same
      // event (see the desktop._usage_yay contract).
      if (e.tur) usage = { tur: e.tur, oturum: e.oturum || usage.oturum };
      if (e.fiyat !== undefined && e.fiyat !== null) price = e.fiyat;
      dockCost();
      break;

    // The price tag arrived later in the background: the chip turns from
    // token counts to dollars — without waiting for the next turn.
    case "fiyat":
      price = e.fiyat || null;
      dockCost();
      break;
  }
}

// The stream connection. It must be single: `onerror` can fire several
// times on one drop, and with each opening a new connection the same event
// was handled two or three times. Unnoticeable in text (the same letter
// added twice slips by) but **the audio plays twice** — a duplicated queue.
let stream = null;
let retry = null;
// Did the connection drop once? A stream that drops and returns can mean
// the app restarted (closed at night, opened in the morning): a tab left
// open sat with stale "running" cards on its orchestra deck. On reconnect
// the real channel list is refreshed from the server.
let dropped = false;

async function resyncChannels() {
  try {
    const s = await (await fetch("/api/state")).json();
    orchSeed(s.channels || []);
  } catch { /* server not up yet; on the next connect */ }
}

function connect() {
  if (stream) { stream.close(); stream = null; }
  clearTimeout(retry);

  const source = new EventSource("/api/events");
  stream = source;
  // Keep it reachable for debugging: an open SSE connection blocks tools
  // waiting for "network idle" indefinitely.
  window.__stream = source;

  source.onopen = () => {
    setBusy(busy);
    if (dropped) { dropped = false; resyncChannels(); }
  };
  source.onmessage = (msg) => {
    // An event from an old stream that already yielded to a new connection
    // is ignored.
    if (source !== stream) { source.close(); return; }
    handle(JSON.parse(msg.data));
  };
  source.onerror = () => {
    if (source !== stream) { source.close(); return; }
    source.close();
    stream = null;
    dropped = true;
    setStatus("off", t("Bağlantı koptu"));
    clearTimeout(retry);
    retry = setTimeout(connect, 2000);
  };
}

async function loadState() {
  try {
    const s = await (await fetch("/api/state")).json();
    // Waking state first: if not ready, the busy indicator tells the wrong
    // story.
    setWaking(s.stage, s.ready);
    setBusy(!!s.busy);
    // The brand's tooltip in the top bar: which version, which layout. In
    // the field it was invisible which of two copies was open — hover the
    // brand and the answer is here.
    if (s.surum) {
      const brand = document.querySelector(".brand");
      if (brand) brand.title = "Dornick " + s.surum +
        (s.kurulu ? t(" · kurulum") : t(" · geliştirme"));
      // A small version badge at the bottom of the sidebar (user request,
      // 01.09): which version is installed shows without searching.
      const badge = document.getElementById("side-ver");
      if (badge) badge.textContent = "v" + s.surum;
    }
    modelName = s.model || "";
    providerName = s.provider || "";
    canRun = s.can_run !== false;
    modelKnown = true;
    // First run: can the agent actually work (is there a key)? Even with a
    // model name filled in ("oto"), no key means no work.
    if (!canRun) showSetupGuide(); else hideSetupGuide();
    // The working-folder gauge: are we in the workshop or a connected folder?
    setWorkdir(s.project || "", s.workspace || "");
    sessionId = s.session || sessionId;
    showMeta();
    setVoice(!!s.voice);
    Speech.setCharacter(s.character);
    setListening(!!s.listen, !!s.wake, !!s.open);
    setMicDeaf(!!s.snoozed);
    paintHear(!!s.ear);
    if (s.mode) { previous = s.mode; setAuthority(s.mode); }
    // Active goals: if the panel missed the event stream (refresh) it is
    // seeded from here and continues where it left off.
    Goals.seed(s.goals || []);
    // Orchestra channels for the same reason: after a refresh/reopen the
    // panel is built from the real list — no ghost "running" cards, and
    // helpers left unfinished from the last session show as "unfinished".
    orchSeed(s.channels || []);
    dockEffort = s.effort || "";
    contextWindow = Number(s.context_window) || 0;
    dockRender();
    if (s.kirilim) lastBreakdownSeed = s.kirilim;
    // The running session's last usage: a refreshed page resumes where it
    // was. The fixed items (system + tools) show before the first turn too.
    if (Number(s.prompt_total) || (s.kirilim && s.kirilim.length)) {
      dockContext(Number(s.prompt_total) || 0, s.tahmin, s.kirilim);
      if (!lastUsage && Number(s.prompt_total)) {
        lastUsage = { prompt_total: Number(s.prompt_total), kirilim: s.kirilim };
      }
    }
    // The cost chip is seeded from here for the same reason: a refresh must
    // not zero the spend gauge.
    if (s.fiyat) price = s.fiyat;
    if (s.kullanim && s.kullanim.oturum && s.kullanim.oturum.cagri) usage = s.kullanim;
    // The budget cap comes from the seed too: a refreshed page must not forget the seatbelt.
    budget = s.butce == null ? null : Number(s.butce);
    dockCost();
    // A refresh does not end the session: whatever the reason for the reload
    // (language change, F5) the running conversation's transcript must come
    // back. The screen used to open blank after a refresh — while the session
    // lived on at the server. With an empty transcript the welcome already
    // stands: loadTranscript leaves the thread alone on an empty dump, and
    // the welcome removes itself when the first line is drawn.
    if (s.session) loadTranscript(s.session);
    if (s.missed_tasks && s.missed_tasks.length) {
      showMissedTasks({ tasks: s.missed_tasks });
    }
  } catch { setStatus("off", t("Sunucu yok")); }
}

// On a page refresh the "I finished speaking" notice never goes out and the
// ear stays closed. Cleared once at startup.
fetch("/api/speaking", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ on: false }),
}).catch(() => {});

loadState();
connect();
setInterval(() => { Scene.load(); loadOrgans(); }, 30000);

// Quiet version check at startup (user request, 01.09): like community
// projects — GitHub releases are checked at most once a day, and with a new
// version the sidebar badge turns into a download link. The check starts
// delayed so it does not race startup traffic; without a network it gives
// up silently and leaves it for the next day.
setTimeout(async () => {
  const CHECK_KEY = "dornickSurumDenetim";
  try {
    const saved = JSON.parse(localStorage.getItem(CHECK_KEY) || "{}");
    if (saved.zaman && Date.now() - saved.zaman < 24 * 60 * 60 * 1000) {
      if (saved.yeni) refreshVersionBadge(saved);
      return;
    }
  } catch { /* corrupt record — carry on with the check */ }
  try {
    const answer = await (await fetch("/api/surum", { method: "POST" })).json();
    try {
      localStorage.setItem(CHECK_KEY, JSON.stringify({
        zaman: Date.now(), yeni: answer.yeni || "",
        url: answer.url || "", indirme: answer.indirme || "",
      }));
    } catch { /* localStorage may be off */ }
    if (answer.yeni) { refreshVersionBadge(answer); updateToast(answer); }
  } catch { /* no network — pass silently */ }
}, 8000);

// Update toast: top right, AT MOST ONCE a day and dismissible (user
// request, 02.09). Dismissed, it never shows again for that version — the
// badge stays put; whoever wants updates from there without the toast
// nagging.
function updateToast(info) {
  if (!info || !info.yeni || document.getElementById("update-toast")) return;
  const KEY = "dornickGuncellemeBildirim";
  try {
    const k = JSON.parse(localStorage.getItem(KEY) || "{}");
    if (k.kapatilan === info.yeni) return;                    // they handled this version
    if (k.zaman && Date.now() - k.zaman < 24 * 60 * 60 * 1000) return;  // once a day
  } catch { /* corrupt record — show */ }
  try {
    localStorage.setItem(KEY, JSON.stringify({ zaman: Date.now(), surum: info.yeni }));
  } catch { /* localStorage off */ }

  const box = document.createElement("div");
  box.className = "update-toast";
  box.id = "update-toast";
  const txt = document.createElement("span");
  txt.className = "u-txt";
  const bold = document.createElement("b");
  bold.textContent = "v" + info.yeni;
  txt.append(bold, document.createTextNode(" " + t("sürümü yayınlandı.")));
  const goBtn = document.createElement("button");
  goBtn.type = "button";
  goBtn.className = "u-go";
  goBtn.textContent = t(info.indirme ? "İndir ve kur" : "İndir");
  goBtn.onclick = async () => {
    if (!info.indirme) {
      if (info.url) window.open(info.url, "_blank", "noopener");
      return;
    }
    goBtn.disabled = true;
    goBtn.textContent = t("İndiriliyor");
    try { await fetch("/api/guncelle", { method: "POST" }); } catch { /* the event stream tells */ }
  };
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "u-x";
  closeBtn.textContent = "✕";
  closeBtn.title = t("Kapat");
  closeBtn.onclick = () => {
    try {
      localStorage.setItem(KEY, JSON.stringify({
        zaman: Date.now(), surum: info.yeni, kapatilan: info.yeni }));
    } catch { /* localStorage off */ }
    box.remove();
  };
  box.append(txt, goBtn, closeBtn);
  document.body.append(box);
}

function refreshVersionBadge(info) {
  const badge = document.getElementById("side-ver");
  if (!badge || !info.yeni) return;
  badge.textContent = "";
  const link = document.createElement("a");
  link.className = "surum-yeni";
  link.href = "#";
  if (info.indirme) {
    // Download+install from inside the app. The address does not come from
    // the client; the server finds the trusted GitHub link itself
    // (/api/guncelle).
    link.textContent = "v" + info.yeni + " " + t("yeni — güncelle");
    link.title = t("Yeni sürüm yayınlandı — indirip kurmak için tıkla");
    link.addEventListener("click", async (e) => {
      e.preventDefault();
      link.textContent = "v" + info.yeni + " · " + t("İndiriliyor");
      try {
        const c = await (await fetch("/api/guncelle", { method: "POST" })).json();
        if (c && c.ok === false) link.textContent = "v" + info.yeni + " · " + t("hata");
      } catch { link.textContent = "v" + info.yeni + " · " + t("hata"); }
    });
  } else {
    const target = info.url || "#";
    link.textContent = "v" + info.yeni + " " + t("yeni — indir");
    link.title = t("Yeni sürüm yayınlandı — indirmek için tıkla");
    link.href = target;
    link.addEventListener("click", (e) => {
      e.preventDefault();
      if (info.url) window.open(info.url, "_blank", "noopener");
    });
  }
  badge.append(link);
}

// Reflects the "guncelleme" SSE event on both the status line in settings
// (if present) and the sidebar badge. The progress percentage streams during
// the download; "kuruluyor/acildi" says the installer opened; "hata" is
// reported honestly.
function updateStatus(e) {
  const badge = document.getElementById("side-ver");
  const progress = document.querySelector(".surum-ilerleme");
  let text = "";
  let bad = false;
  if (e.asama === "indiriliyor") {
    const pct = Number(e.yuzde) || 0;
    text = t("İndiriliyor") + " %" + pct;
    if (badge) badge.setAttribute("data-guncelleme", "%" + pct);
  } else if (e.asama === "kuruluyor") {
    text = t("Kurulum açılıyor…");
  } else if (e.asama === "acildi") {
    text = t("Kurulum açıldı — yönergeleri izle (Dornick kapatılacak)");
  } else if (e.asama === "hata") {
    text = e.hata || t("Güncelleme başlatılamadı");
    bad = true;
  }
  if (progress && text) {
    progress.className = "surum-ilerleme" + (bad ? " bad" : "");
    progress.textContent = text;
  }
  // The badge: a short summary (long text must not break the sidebar).
  if (badge && (e.asama === "kuruluyor" || e.asama === "acildi")) {
    const link = badge.querySelector("a");
    if (link) link.textContent = t("Kurulum açılıyor…");
  }
}

// speech.js reports once when it cannot produce audio; the line lands in the chat.
document.addEventListener("dornick:voice-trouble", () => {
  line("alert", t("Ses su an uretilemiyor — ses servisine ulasilamiyor olabilir (internet gerekli). Metin ekranda; ses duzelince kendiliginden devam eder."));
});
loadOrgans();
input.focus();


// --- recall path ------------------------------------------------------
// As the scene opens step by step, the list fills too. Clicking a step
// highlights that node: the path can be followed like a map.
function renderRoute(route, upto) {
  const box = $("route");
  if (!route || !route.length) { box.hidden = true; return; }
  box.hidden = false;
  box.textContent = "";

  const head = document.createElement("div");
  head.className = "head";
  // The query is CLIPPED: when the user pasted a huge configuration text
  // the header covered the left half. The full text is in the chat anyway;
  // this is just a label reminding which query the trace belongs to.
  const q = (lastQuery || "").replace(/\s+/g, " ").trim();
  head.textContent = q ? t("İz · ") + (q.length > 48 ? q.slice(0, 48) + "…" : q) : t("Hatırlama izi");
  head.title = q;
  box.append(head);

  // Scanned and used are not the same thing. The mind touches dozens of
  // records per query, and numbering them all looked like "it mixed
  // everything up": while saying "add a modbus device" two BTC price records
  // showed numbered in the list, though only one was put before the model.
  //
  // Old records carry no mark; there, all count as used.
  const marked = route.some((step) => step.used);
  let used = 0;

  // The "glanced" flood crushed the list (and the legend below it): in a
  // query touching forty records, the three used ones got lost in the crowd.
  // Used ones are ALWAYS listed; of the glanced, the first few show and the
  // rest collapse into one summary line.
  const GLANCE_LIMIT = 5;
  let glancedShown = 0, glancedHidden = 0;

  route.slice(0, upto + 1).forEach((step, i) => {
    const took = marked ? !!step.used : true;
    if (!took) {
      if (glancedShown >= GLANCE_LIMIT) { glancedHidden += 1; return; }
      glancedShown += 1;
    }
    const row = document.createElement("div");
    row.className = took ? "step" : "step glanced";
    const no = document.createElement("span");
    no.className = "no";
    // Numbers only on the used, sequential among themselves: if the scanned-
    // and-dropped advanced the count, the list came out "1, 4, 6".
    if (took) { used += 1; no.textContent = used; }
    else no.textContent = "·";
    const what = document.createElement("span");
    what.className = "what";
    what.textContent = step.label || step.node;
    const hop = document.createElement("span");
    hop.className = "hop";
    hop.textContent = took ? (step.hop === 0 ? t("Sorgu") : step.hop + t(". sicrama"))
                           : t("Bakildi");
    row.append(no, what, hop);
    row.addEventListener("click", () => {
      [...box.querySelectorAll(".step")].forEach(el => el.classList.remove("on"));
      row.classList.add("on");
      Scene.focusStep(i);
    });
    box.append(row);
  });

  if (glancedHidden > 0) {
    const more = document.createElement("div");
    more.className = "step glanced more";
    const no = document.createElement("span"); no.className = "no"; no.textContent = "·";
    const what = document.createElement("span"); what.className = "what";
    what.textContent = "+" + glancedHidden + t(" kayda daha bakıldı");
    more.append(no, what);
    box.append(more);
  }
}
