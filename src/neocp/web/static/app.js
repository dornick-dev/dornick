// Sohbet, canlı akış ve onay.
// Sunucuyla iki kanal: POST ile komut gider, SSE ile her şey geri gelir.

// Bu dosyanın kullanıcıya gösterdiği metinlerin İngilizceleri. Kaynak
// metin Türkçe kalıyor; görüntüleme noktasında t("...") ile çevriliyor.
Dil.ekle({
  "Ses su an uretilemiyor — ses servisine ulasilamiyor olabilir (internet gerekli). Metin ekranda; ses duzelince kendiliginden devam eder.":
    "Speech is unavailable right now — the voice service may be unreachable (internet required). The text stays on screen; audio resumes once the service is back.",
  // Marka ipucundaki sürüm eki
  " · kurulum": " · installed",
  " · geliştirme": " · development",
  // Araya girme ve yardımcı onayı
  "araya girdi": "interjected",
  "Araya alındı": "Interjected",
  "İşleniyor": "Working it in",
  "yardımcı": "helper",
  // Karşılama
  "Ne yapmamı istersin?": "What would you like me to do?",
  "Bilgisayarında çalışıyorum. Öğrendiklerim etrafımdaki ağa yazılıyor.":
    "I work on your computer. What I learn is woven into the web around me.",
  // Durum şeridi ve kipler
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
  // Dönen düşünme kelimeleri
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
  // Eylem eşanlamlıları (turda tutarlı seçiliyor)
  "Koşturuyor": "Running", "Göz atıyor": "Skimming", "İnceliyor": "Examining",
  "Elden geçiriyor": "Reworking", "Kaleme alıyor": "Drafting",
  "Tarıyor": "Scanning", "Eşeliyor": "Digging around",
  "Sayfayı açıyor": "Opening the page", "Göz gezdiriyor": "Glancing over",
  "Anımsıyor": "Recollecting", "Not düşüyor": "Jotting down",
  // Araç eylemleri
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
  // İş şeridi
  "Düşündü": "Thought", "✻ Düşündü": "✻ Thought", " kelime": " words",
  "Tıkla — bu turun muhakemesini gör": "Click to see this turn's reasoning",
  " kez": " times",
  "Tıkla — tamamını gör": "Click to see all",
  "Hatırlananlar — tıkla, tamamını gör": "Recalled — click to see all",
  "Devamı": "More", "Kısalt": "Collapse",
  "Sırada": "Queued",
  " argüman": " arguments",
  // Model bekleme durumu (çalışma şeridinde yaşar, sohbete düşmez)
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
  // Kamera ve ses
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
  // Kompozer + menüsü ve ekler
  "Dosya ekle": "Add file", "belge, görsel, veri": "document, image, data",
  "Bağlantılar": "Connectors", "MCP sunucuları": "MCP servers",
  "Yetenekler": "Skills", "kendi araçların": "your own tools",
  "Yeni görev": "New task", "zamanlanmış iş": "scheduled job",
  "Kamera": "Camera", "aç/kapa, izleme": "on/off, watching",
  "Program kapalıyken zamanı geçmiş görevler var.":
    "Some scheduled tasks were due while neo was closed.",
  "Bu seferlik atla": "Skip this time",
  "Şimdi yap": "Run now",
  "Listeden çıkar": "Remove from list",
  "Konuşulan": "Talking about", "Bağlamdan çıkar": "Remove from context",
  // Yetki
  "Yetki: ": "Access: ",
  " — hiçbir şey sorulmuyor": " — nothing is asked",
  " · tıkla: tam yetki": " · click: full access",
  " · tıkla: kip seç": " · click: choose mode",
  "otomatik": "auto", "sorar": "asks", "salt okunur": "read-only",
  "tam yetki": "full access",
  // Dock ve açılır kutuları
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
  // Maliyet çipi
  "Bu turun tahmini harcaması — tıkla: kırılım":
    "This turn's estimated spend — click for the breakdown",
  "Bu oturumun tahmini toplam harcaması — tıkla: kırılım":
    "Estimated total spend for this chat — click for the breakdown",
  " · bu tur: ": " · this turn: ",
  " · premium model (çıktı > $20/M)": " · premium model (output > $20/M)",
  "Tahmini harcama": "Estimated spend",
  // Bütçe freni (maliyet çipinin kutusunda)
  " · oturum sınırı: ": " · session cap: ",
  "Bu oturum için üst sınır": "Cap for this session",
  "sınırsız": "no cap",
  "Uygula": "Apply",
  "Sınıra ulaşılınca koşan tur durur; yükseltince kaldığı yerden sürer.":
    "When the cap is hit the running turn stops; raise it and work resumes.",
  "Fiyat bilinmiyor (yerel sunucu ya da katalog dışı model) — fren çalışmaz.":
    "Price unknown (local server or model outside the catalogue) — the brake cannot work.",
  "Sınır kaydedilemedi.": "Could not save the cap.",
  "Premium model: çıktı fiyatı $20/M üstünde.":
    "Premium model: output price above $20/M.",
  "Bu tur: ": "This turn: ", "oturum: ": "session: ",
  "Girdi: ": "Input: ", "Çıktı: ": "Output: ",
  "Tahmin — önbellek indirimi hesaba katılmaz.":
    "An estimate — cache discounts are not counted.",
  "Fiyat bilinmiyor — yalnız token sayısı.":
    "Price unknown — token counts only.",
  // Onay diyaloğu
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
  // Beni tanı
  "Tanıma eğitimi arka planda": "Personal training in the background",
  "Tanıma eğitimi tamamlandı": "Personal training finished",
  "Beni tanı açık": "Learn-me is on",
  "son eğitim": "last training",
  "henüz yok": "not yet",
  "tıkla: şimdi eğit": "click to train now",
  "Şu an seni tanıyorum — eğitim arka planda sürüyor":
    "Learning you now — training in the background",
  // Bildirimler
  "Model bu isteği reddetti.": "The model refused this request.",
  "Kesildi.": "Interrupted.",
  // İlk kurulum yönlendirmesi (settings.KURULUM_YONLENDIRME ile birebir)
  ["Henüz bir yapay zekâ sağlayıcısı tanımlı değil. Ayarlar › Model'den bir " +
   "sağlayıcı seçip API anahtarı girmelisin. Varsayılan sağlayıcı " +
   "OpenRouter'dır — anahtarını girdiğinde ücretsiz modellerle 'Oto' modda " +
   "hemen başlayabilirsin."]:
    "No AI provider is configured yet. Open Settings › Model, pick a " +
    "provider and enter an API key. The default provider is OpenRouter — " +
    "once you enter your key you can start right away in 'Auto' mode with " +
    "free models.",
  // Oto kipi notu (yalnız OpenRouter + "oto")
  ["Oto modda OpenRouter'ın ücretsiz modelleri kullanılır; kalite ve hız " +
   "düşebilir, model istek sırasında değişebilir. Bazı ücretsiz uçlar " +
   "veriyi eğitimde kullanabilir; istekler 'veri toplama: reddet' " +
   "tercihiyle gönderilir."]:
    "Auto mode uses OpenRouter's free models; quality and speed may drop, " +
    "and the model can change per request. Some free endpoints may use " +
    "your data for training; requests are sent with 'data collection: deny'.",
  "Köprü: ": "Bridge: ", "bağlandı": "linked",
  // Hatırlama izi
  "İz · ": "Trace · ", "Hatırlama izi": "Recall trace",
  "Seçim bu sohbette kalır; yeni sohbet ve sonraki açılış onu devralır. Küresel varsayılan: Ayarlar → Model.":
    "The pick stays with this chat; new chats and the next launch inherit it. Global default: Settings → Model.",
  "Sorgu": "Query", ". sicrama": ". hop", "Bakildi": "Glanced",
  " kayda daha bakıldı": " more records glanced",
  // Akıllı kaydırma
  " yeni": " new",
  // Adım kartları
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
  // Hedef paneli: yönetim
  "neo'nun kendine yazdığı iş listesi — tıkla: katla/aç":
    "neo's own task list — click to fold/unfold",
  " iş listesi": " task list", "İş listesi": "Task list",
  "Aktif madde yok.": "No active items.",
  "İş listesi yok.": "No task list.",
  "Aktif madde yok.": "No active items.",
  "Neo'nun uzun işlerde kendi yazdığı adım listesi (Cursor görev listesi gibi). Sohbet geçmişi değil — madde yoksa sekme de yok. Sen de ekleyip silebilirsin.":
    "Neo's step list for long jobs (like Cursor's todo list). Not chat history — no items, no tab. You can add or remove items too.",
  "neo'nun kendine yazdığı adım listesi — tıkla: katla/aç":
    "Neo's own step list — click to fold/unfold",
  "Bunlar neo'nun kendine yazdığı iş listesi — uzun işlerde ne yaptığını takip etmek için. Sen de ekleyebilir, silebilirsin.":
    "This is neo's own task list — so you can follow what it is doing on long jobs. You can add and remove items too.",
  "＋ kendi maddeni yaz": "＋ add your own item",
  "Yeni iş maddesi": "New task item", "Ekle": "Add",
  "eski": "old", "Geçen oturumlardan kaldı": "Left over from earlier sessions",
  // "Şimdi eğit" sonucu — sessiz kalmıyor, her durum tek satırla söyleniyor
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
  // Artifact kartı
  "Yayınlıyor": "Publishing",
  "yayınlandı": "published", "güncellendi": "updated",
  "Aç": "Open", "Artifact": "Artifact",
  "İndir": "Download", "Yazdır / PDF": "Print / PDF",
  "Tarayıcıda aç": "Open in browser",
  "Gerçek tarayıcıda aç": "Open in your real browser",
  "Adres kopyalandı ✓": "Address copied ✓",
  "Tıkla — sayfayı görüntüleyicide aç": "Click — open page in viewer",
  "Tıkla — sayfayı görüntüleyicide aç": "Click to open the page in the viewer",
  // Hedef paneli
  "Hedefler": "Goals",
  "Tıkla — katla/aç": "Click to fold or unfold",
  "tamamlandı": "done", "bırakıldı": "dropped",
  // Plan kipi onay döngüsü
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

let agentLine = null;      // akmakta olan cevabın kabı
let busy = false;
let approvalId = null;
let lastQuery = "";

// --- sızıntı savunması (ikinci hat) ------------------------------------
//
// Birinci hat sunucuda: hub `_payload` iç notları süzüyor, döküm okuyucusu
// (mind/store.transcript) da öyle. Buradaki ikinci hat, o süzgeçlerden
// birinin bir gün kaçırdığı hali kullanıcının ekranından uzak tutuyor —
// ikisi de kanıtlanmış yaralar, bir daha aynı şey ekrana düşmesin.
//
// İki kalıp çizilmiyor:
//
//   1. HARNESS NOTU — kullanıcının yazmadığı iç dürtüler ("Planını yazdın
//      ama uygulamadın. Şimdi yap: …", "[Yardımcı bitti · …]"). Sohbete
//      kullanıcı mesajı gibi düştüğü görüldü; kullanıcı kendi ağzından
//      çıkmamış bir cümle okuyor.
//   2. SAHTE ARAÇ ÇAĞRISI — model gerçek araç çağrısı yerine çağrı XML'ini
//      DÜZ METİN olarak yazdı. Bu bir cevap değil, başarısız bir deneme;
//      ham XML sohbete basılmamalı. (Döngü tarafında modele "gerçek araç
//      çağrısı yap" notu düşüyor ve tur sürüyor.)
//
// Kalıplar bilerek DAR: iç notların ayırt edici açılışları. Geniş bir
// desen (ör. her köşeli parantez) kullanıcının kendi cümlesini yutardı.

const IC_NOT_KALIPLARI = [
  /^\s*\[(Harness notu|Yardımcı|Arka plan işi|Kullanıcı bu arada yazdı|Ana ajandan|Uzun koşu kontrol noktası)/,
  /^\s*Planını yazdın ama uygulamadın/,
  /^\s*Önceki yanıtın uzunluk sınırında kesildi/,
  /^\s*Sürdürme hakkın bitti/,
  /^\s*Yukarıdaki görüntü senin kendi bakışın/,
  /^\s*Arka plandaki yardımcı\(lar\) bitti/,
  /^\s*Kameradan bir kare\. Gerçekten bak/,
];

// Araç çağrısı XML'i: metnin herhangi bir yerinde geçmesi yeter — model
// çoğu zaman önce bir-iki cümle yazıp sonra XML'e giriyor.
const SAHTE_CAGRI_KALIBI = /<\/?(function_calls|invoke\b|parameter\b|antml:)/i;

function icNot(text) {
  const s = String(text || "");
  return IC_NOT_KALIPLARI.some((k) => k.test(s));
}

function sahteCagri(text) {
  return SAHTE_CAGRI_KALIBI.test(String(text || ""));
}

// Kullanıcı satırı çizilmeli mi? İç not ise hayır — sessizce yutulur.
function cizilir(text) {
  return !icNot(text) && !sahteCagri(text);
}

Scene.init({
  canvas: $("scene"), probe: $("probe"), reveal: $("reveal"),
  onRoute: renderRoute,
  // Anıya çift tık / karttaki "Konuşmaya git": anının doğduğu oturuma
  // geçilir — geçmiş panelindeki tıkla aynı yol (meşgulse bekletir).
  onSession: (id) => { if (typeof History !== "undefined") History.resumeById(id); },
});
Scene.load();

Dil.ekle({ "Açıklama ▸": "Key ▸", "Açıklama ▾": "Key ▾" });

// --- bağlam araçları ⋮ menüsü --------------------------------------------
(() => {
  const dugme = $("more-tools"), kutu = $("more-pop");
  if (!dugme || !kutu) return;
  dugme.addEventListener("click", (ev) => {
    ev.stopPropagation();
    kutu.hidden = !kutu.hidden;
  });
  kutu.addEventListener("click", () => { kutu.hidden = true; });
  document.addEventListener("click", () => { kutu.hidden = true; });
})();

// --- beyin paneli aç/kapa ------------------------------------------------
// Sağ sütun marka katmanı; kapatmak odak demek. Tercih hatırlanıyor.
// Kapalıyken tuval de gizli (display:none) ve sahne çizimi duruyor —
// görünmeyen sahneyi canlandırmak boşa yakılan pil.
(() => {
  const uygula = (acik) => {
    document.body.classList.toggle("mind-on", acik);
    document.body.classList.toggle("mind-off", !acik);
    try { localStorage.setItem("neo-mind", acik ? "acik" : "kapali"); } catch { /* dosya:// */ }
    if (acik) Scene.resume(); else Scene.pause();
  };
  let kayit = null;
  try { kayit = localStorage.getItem("neo-mind"); } catch { /* dosya:// */ }
  uygula(kayit !== "kapali");
  // Beyin ORTADA büyüsün mü (ambient)? Ayarlardan yönetilir; kapalıyken
  // beyin sağ panelde kalır, orta sahne sönükleşir — "yazılar beynin
  // altında kayboluyor" (canlı istek, 31.08).
  try {
    if (localStorage.getItem("neo-brain-ambient") === "kapali")
      document.body.classList.add("no-ambient");
  } catch { /* dosya:// */ }
  window.beyinOrtada = (acik) => {
    document.body.classList.toggle("no-ambient", !acik);
    try { localStorage.setItem("neo-brain-ambient", acik ? "acik" : "kapali"); } catch {}
  };
  $("mind-close").addEventListener("click", () => uygula(false));
  // ◍ artık iki yönlü anahtar: ambient kipte yüzen başlık (›) yok, beyni
  // kapatıp açmanın kalıcı yeri burası.
  $("mind-open").addEventListener("click", () =>
    uygula(document.body.classList.contains("mind-off")));
  // Anı araması: eşleşen düğümler parlar, kalanı söner. Kutu boşalınca
  // sahne normale döner.
  const ara = $("mind-search");
  ara.addEventListener("input", () => Scene.search(ara.value));

  // Legend katlanır; varsayılan KAPALI ("kocaman yer kaplamış").
  const cips = $("legend-toggle");
  const legendUygula = (acik) => {
    Scene.legend(acik);
    cips.classList.toggle("on", acik);
    cips.textContent = acik ? t("Açıklama ▾") : t("Açıklama ▸");
    try { localStorage.setItem("neo-legend", acik ? "acik" : "kapali"); } catch { /* dosya:// */ }
  };
  let leg = null;
  try { leg = localStorage.getItem("neo-legend"); } catch { /* dosya:// */ }
  legendUygula(leg === "acik");
  cips.addEventListener("click", () =>
    legendUygula(!cips.classList.contains("on")));

  // Kayıtlı panel genişliği / masa-beyin oranı açılışta geri gelsin.
  try {
    const w = parseInt(localStorage.getItem("neo-mind-w") || "", 10);
    // Eski/bozuk kayıt sohbeti ezerse: yok say. (Tavan tutamaçla aynı: 760.)
    if (w >= 240 && w <= 760) {
      document.documentElement.style.setProperty("--mind-w-user", w + "px");
    } else if (Number.isFinite(w)) {
      try { localStorage.removeItem("neo-mind-w"); } catch { /* */ }
      document.documentElement.style.removeProperty("--mind-w-user");
    }
    const dh = localStorage.getItem("neo-dock-h");
    if (dh && /^\d+(\.\d+)?%$/.test(dh)) {
      document.documentElement.style.setProperty("--dock-h-user", dh);
    }
    const vh = localStorage.getItem("neo-viewer-h");
    if (vh && /^\d+(\.\d+)?%$/.test(vh)) {
      document.documentElement.style.setProperty("--viewer-h-user", vh);
    }
    if (localStorage.getItem("neo-mind-front") === "1") {
      document.body.classList.add("mind-front");
    }
  } catch { /* dosya:// */ }

  // Beyin etiketi: masa açıkken tıklayınca beyin öne / geri.
  const tag = document.querySelector(".mind-tag");
  if (tag) {
    tag.style.cursor = "pointer";
    tag.title = t("Beyni öne al / geri");
    tag.addEventListener("click", () => {
      const on = document.body.classList.toggle("mind-front");
      try { localStorage.setItem("neo-mind-front", on ? "1" : "0"); } catch { /* dosya:// */ }
    });
  }
})();

// Beyin panelini sol kenarından sürükleyerek boyutlandırma — sol rail
// tutamağının aynası. Genişlik hatırlanır.
(() => {
  const grip = $("mind-grip");
  if (!grip) return;
  const root = document.documentElement;
  let active = false;
  const onMove = (ev) => {
    if (!active) return;
    // 420 tavanı panoyu hapse çeviriyordu: varsayılan genişlik zaten 420
    // olduğundan panel YALNIZ küçülebiliyordu ("resize edilemiyor, sadece
    // küçültülebiliyor" — canlı, 31.08). Tavan yarım ekrana çıktı.
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
      if (w) localStorage.setItem("neo-mind-w", String(w));
    } catch { /* dosya:// */ }
  };
  grip.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    active = true;
    // İşaretçiyi yakala: fare pencere dışına/iframe üstüne kaçsa da
    // bırakma olayı BİZE gelir. Yakalanmayınca pointerup kaçıyor ve panel
    // fare her hareketinde büyüyüp küçülmeye devam ediyordu (canlı şikâyet).
    try { grip.setPointerCapture(ev.pointerId); } catch { /* eski motor */ }
    document.body.classList.add("mind-resize");
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    window.addEventListener("blur", stop);
  });
})();

// Masa ↔ beyin (veya beyin ↔ orkestra) dikey tutamak. Genişlik tutamacı
// bütün sütunu kaplar; bu tutamak yalnızca yüksekliği böler.
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
      // Üst = masa: tutamacı aşağı çekince masa büyür.
      const maxTop = box.height - MIN_BOT - GRIP;
      const px = Math.max(MIN_TOP, Math.min(maxTop, clientY - box.top));
      const pct = ((px / box.height) * 100).toFixed(1) + "%";
      root.style.setProperty("--viewer-h-user", pct);
      document.body.classList.remove("mind-front");
      return pct;
    }
    // Orkestra: alttan yükseklik (eski davranış).
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
        if (v) localStorage.setItem("neo-viewer-h", v);
        localStorage.setItem("neo-mind-front", "0");
      } else {
        const v = getComputedStyle(root).getPropertyValue("--dock-h-user").trim();
        if (v) localStorage.setItem("neo-dock-h", v);
      }
    } catch { /* dosya:// */ }
  };
  grip.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    active = true;
    try { grip.setPointerCapture(ev.pointerId); } catch { /* eski motor */ }
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
      try { localStorage.removeItem("neo-viewer-h"); } catch { /* dosya:// */ }
    } else {
      root.style.removeProperty("--dock-h-user");
      try { localStorage.removeItem("neo-dock-h"); } catch { /* dosya:// */ }
    }
  });
})();

// Cevabı dönüyor: bazı çağrılar (yetki değişimi) sunucunun kabul edip
// etmediğine bakmak zorunda.
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

// Taze bir oturumda karşılama geri gelsin: yeni konuşmaya geçince thread
// tamamen boşalıyordu ("yeni sohbet açtım, bomboş ekran"). Zaten varsa
// tekrar eklemiyor.
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
}

// --- akıllı kaydırma ----------------------------------------------------
//
// Eski hal her olayda en alta zıplıyordu — kullanıcı yukarıda eski bir
// cevabı okurken bile. Kural basit: kullanıcı en alttaysa (ya da çok
// yakınsa) takip sürer; yukarı kaydırdıysa otomatik inme DURUR ve sağ
// altta "↓ N yeni" düğmesi belirir. Tıklayınca (ya da kendisi en alta
// inince) takip geri gelir. Bütün kaydırmalar bu tek kapıdan geçiyor.

const NEAR_BOTTOM = 120;   // bu kadar piksel yakınsa "en altta" sayılır
let follow = true;         // otomatik takip açık mı
let fresh = 0;             // takip kapalıyken gelen yeni blok sayısı
let seenBlocks = 0;        // sayacın karşılaştırma tabanı
let transcriptBatch = false;  // geçmiş boyarken scroll yok

const atBottom = () =>
  thread.scrollHeight - thread.scrollTop - thread.clientHeight < NEAR_BOTTOM;

function scroll() {
  if (transcriptBatch) return;
  const blocks = thread.childElementCount;
  if (follow) { thread.scrollTop = thread.scrollHeight; seenBlocks = blocks; return; }
  // Takip kapalı: inme yok. Yalnızca yeni üst-düzey blokları say — aynı
  // cevabın her yeniden çizimi sayacı şişirmesin.
  if (blocks > seenBlocks) { fresh += blocks - seenBlocks; seenBlocks = blocks; }
  paintJump();
}

function paintJump() {
  const button = $("jump");
  button.hidden = follow;
  // Meşgulken çip canlı fiili de taşır: uzun bir akışta yukarı kaymış
  // kullanıcı "şu an nerede / ne oluyor"u buradan okur ve tek tıkla canlı
  // uca döner ("yazıyor diyor ama aşağıda yazıyor, neredeyim bilmiyorum").
  if (!follow) {
    const canli = busy ? mull() + " · " : "";
    button.textContent = canli + (fresh ? "↓ " + fresh + t(" yeni") : "↓");
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

// Şerit / düşünce açılınca composer (z:25) altından kurtar.
// Dipte açılınca gövde input'un ARKASINA uzuyor; max-height CSS'i
// (52vh) görünür boşluktan büyük olunca yalnızca 1-2 px'lik dilim
// kalıyordu ("açılıyor ama minicik" — canlı, 01.09). Çözüm: yüksekliği
// composer üstüne sığdır + şerit başlığını görünür alanın tepesine çek.
function revealAboveComposer(el) {
  if (!el || !thread.contains(el)) return;
  const go = () => {
    const shell = document.getElementById("compose-shell");
    const shellTop = shell ? shell.getBoundingClientRect().top : window.innerHeight;
    const streamBox = thread.getBoundingClientRect();
    const pad = 20;
    const avail = Math.max(160, Math.floor(shellTop - streamBox.top - pad));
    // Açık düşünce / şerit gövdesi: tavanı görünür odaya kilitle.
    if (el.classList.contains("acts-body") || el.classList.contains("think")) {
      const tav = el.classList.contains("think") ? 480 : 520;
      el.style.maxHeight = Math.min(avail, tav) + "px";
    }
    const head = el.classList.contains("acts-body")
      && el.previousElementSibling
      && el.previousElementSibling.classList.contains("acts-head")
      ? el.previousElementSibling
      : null;
    const topEl = head || el;
    // Başlığı (veya kutuyu) sohbet görünür alanının üstüne yasla —
    // Cursor thought paneli gibi okunur yükseklik kalsın.
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
  // Uzun / teknik uyarılar cevap gibi sarı duvar olmasın: tek satır özet,
  // tıklanınca ham metin. Kısa bilgilendirme düz kalır.
  if (kind === "alert" && text && shouldFoldAlert(text)) {
    return alertFold(text);
  }
  const el = document.createElement("div");
  el.className = "line " + kind;
  // Uzun yapıştırma (kod, günlük, belge) sohbeti kaplamasın: katlı gelir,
  // "Devamını göster" ile açılır (Claude Code'un show more'u). Ham metin
  // _rawText'te — Düzenle/Yeniden gönder aynen çalışır.
  if (kind === "user" && text
      && (text.length > 800 || text.split("\n").length > 14)) {
    el._rawText = String(text);
    const satir = text.split("\n").length;
    const kirp = document.createElement("div");
    kirp.className = "msg-clip";
    kirp.textContent = text;
    const ac = document.createElement("button");
    ac.type = "button";
    ac.className = "msg-more";
    const boya = () => {
      const acik = el.classList.contains("open");
      ac.textContent = acik ? t("Daralt")
        : t("Devamını göster") + " · " + satir + t(" satır");
    };
    ac.addEventListener("click", () => { el.classList.toggle("open"); boya(); scroll(); });
    boya();
    el.append(kirp, ac);
    attachMsgActs(el, kind);
    thread.append(el);
    scroll();
    return el;
  }

  // Aynı turda arka arkaya gelen model parçaları TEK mesaj gibi okunsun:
  // son konuşan yine modelse bu parça "devam"dır — "neo" başlığı ve koca
  // aralık tekrar etmez. Metin yine SOHBETTE ve görünür (katlama yok);
  // yalnız görsel merdiven kırılıyor.
  if (kind === "agent") {
    const konusan = [...thread.children].reverse().find((n) =>
      n.classList && n.classList.contains("line")
      && (n.classList.contains("agent") || n.classList.contains("user")));
    if (konusan && konusan.classList.contains("agent")) el.classList.add("cont");
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
    // "Yeniden üret" yalnız SON ajan balonunda durur. Uzun bir koşuda her
    // ara anlatımın altında birikmesi gürültüydü ("her mesajda yeniden
    // üret yazıyor" — canlı döküm); anlamı da zaten "son cevabı yeniden
    // üret". Yeni ajan balonu doğunca eskilerinki kalkar.
    for (const eski of thread.querySelectorAll(".line.agent .msg-acts")) {
      if (eski.parentElement !== el) eski.remove();
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
  // [kanal] mesaj  — alt ajan
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

// Sürdürülen bir konuşmanın geçmiş dökümünü thread'e basar: kullanıcı
// kaldığı yeri görsün, yeni mesaj oraya eklensin.
//
// Aynı oturum için İKİ KEZ çizilmez: session_reset hem doğrudan çağırıyor
// hem loadState üzerinden (snapshot da sayfa yenileme için çağırıyor) —
// ikisi birden koşunca her mesaj ekranda iki kez görünüyordu (canlı yara,
// 31.08: "konuşmayı tekrar açınca aynı yazışmalar iki kez geliyor").
let transcriptFor = "";

async function loadTranscript(id) {
  if (id && transcriptFor === id) return;
  transcriptFor = id || "";
  let data;
  try { data = await (await fetch("/api/session?id=" + encodeURIComponent(id))).json(); }
  catch { transcriptFor = ""; return; }
  const turns = (data.turns || []).filter((t) => cizilir(t.text));
  transcriptBatch = true;
  const oncekiFollow = follow;
  follow = false;
  try {
    for (let i = 0; i < turns.length; i++) {
      const t = turns[i];
      if (t.role === "user") {
        const el = line("user", t.text);
        reviveUserMedia(el, t.text || "");
      } else {
        const el = line("agent", "");
        el._rawText = t.text || "";
        Markdown.into(el, t.text || "");
        attachMsgActs(el, "agent");
        el.classList.add("done");
      }
      if (i > 0 && i % 12 === 0) {
        await new Promise((r) => requestAnimationFrame(() => r()));
      }
    }
  } finally {
    transcriptBatch = false;
    follow = oncekiFollow;
  }
  scroll();
  if (busy) {
    if (work) dockWork(work);
    kickWork();
    scroll();
  }
}

// Geçmişte yalnız yollar yazılıydı; canlıdaki gibi çip + görsel önizleme.
const IMG_EXT = /\.(png|jpe?g|gif|webp|bmp|svg)$/i;
function reviveUserMedia(row, text) {
  if (!row || !text) return;
  const yollar = [];
  const ek = text.match(/Eklenen dosyalar \(atölyende\):\n((?:[-•]\s+.+\n?)+)/i);
  if (ek) {
    for (const satir of ek[1].split("\n")) {
      const yol = satir.replace(/^[-•]\s+/, "").trim();
      if (yol) yollar.push(yol);
    }
  }
  for (const m of text.matchAll(/Kullanıcı şu dosyayı işaret etti:\s*(.+)/gi)) {
    const yol = (m[1] || "").trim();
    if (yol && !yollar.includes(yol)) yollar.push(yol);
  }
  if (!yollar.length) return;
  const files = [];
  let frame = "";
  for (const yol of yollar) {
    const ad = yol.split(/[\\/]/).pop() || yol;
    files.push(ad);
    if (!frame && IMG_EXT.test(yol)) {
      frame = "/api/raw?path=" + encodeURIComponent(yol.replace(/\\/g, "/"));
    }
  }
  attachMedia(row, { frame, files });
  row.querySelectorAll(".msg-file").forEach((chip, i) => {
    const yol = yollar[i];
    if (!yol) return;
    chip.style.cursor = "pointer";
    chip.title = yol;
    chip.addEventListener("click", () => {
      if (typeof Viewer !== "undefined" && Viewer.present) Viewer.present(yol);
    });
  });
}

function setStatus(state, label) {
  statusEl.className = "status " + state;
  statusEl.querySelector("b").textContent = label;
}

// --- uyanma -------------------------------------------------------------
//
// Model yüklenmeden konuşmak anlamsız: yazdığın cevapsız kalıyor. Hazır
// olana kadar giriş satırı kapalı ve sahne sönük duruyor; hazır olunca
// çekirdek canlanıyor.

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

// Açılışta / model yüklenirken welcome altında canlı satır — yalnız
// soluk composer değil; kullanıcı "dondu" sanmasın.
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

// Gönder düğmesi koşarken DURDUR olur (Claude Code): kutu boşken ■,
// kutuda yazı varsa yine → (meşgulken gönderilen sıraya girer).
function paintSend() {
  const g = $("send");
  const dur = busy && !input.value.trim();
  g.classList.toggle("stop", dur);
  g.textContent = dur ? "■" : "→";
  g.title = dur ? t("Durdur") : t("Gönder");
  g.setAttribute("aria-label", dur ? t("Durdur") : t("Gönder"));
}

function setBusy(value) {
  // Tur başlangıcı: henüz hiçbir şey akmadı. waiting() geri sayımı yalnız
  // bu bayrak düşükken "Model yanıtı bekleniyor…" der — araç koşan uzun
  // bölümlerde başlığın "yükleniyor" diye yalan söylemesi canlı yaraydı.
  if (value && !busy) turnActivity = false;
  busy = value;
  stopBtn.hidden = !value;
  paintSend();
  // Düğme yalnızca meşgulken kilitlenir. Boş metni send() zaten eliyor;
  // kilidi metnin varlığına bağlamak, değer programatik değiştiğinde
  // (yapıştırma, otomatik doldurma, IME) düğmeyi kilitli bırakıyordu.
  // Meşgulken de yazılabiliyor: gönderilen mesaj sıraya giriyor.
  $("send").disabled = !ready;
  setMode(value ? "thinking" : "idle");
  waiting(value);
  // Canlı "yaşıyor" sayacı meşgul olduğu sürece ilerlesin, bitince dursun.
  if (value) {
    startBusyTicker();
    // Tur anında thread satırı — ilk delta gelene kadar boşluk kalmasın.
    kickWork();
  } else {
    stopBusyTicker();
    // Kesmede tool_end kaçabilir: ışık turla birlikte her koşulda söner.
    kontrolSayaci = 0;
    document.body.classList.remove("kontrol-canli");
    sealLine();
    // Plan kartı tur metninin ALTINDA: önce metin mühürlensin, sonra kart.
    flushDeferredPlans();
  }
}

// Kontrol ışıması: neo el/ekran araçlarını kullanırken pencere çevresi
// nabızlı yanar — "şu an bilgisayarı o kullanıyor" tek bakışta belli
// (kullanıcı isteği, 31.08: Claude'un ekran çerçevesi gibi). Sayaçlı:
// iç içe çağrılar sönmeyi erkene almasın; tur bitince her koşulda söner.
let kontrolSayaci = 0;
function kontrolIsigi(delta) {
  kontrolSayaci = Math.max(0, kontrolSayaci + delta);
  document.body.classList.toggle("kontrol-canli", kontrolSayaci > 0);
}

// Meşgulken şeritte anında "Düşünüyor · N sn". setBusy ve kullanıcı
// mesajı (busy önce geldiyse sealLine boş şeridi siler) buradan çağırır.
function kickWork() {
  if (!busy) return;
  const w = ensureWork();
  w.head.classList.add("busy");
  if (waitState) { paintWait(); return; }
  if (!paintLive()) workHead(mull(), "", since(w.since) + streamNote());
  scroll();
}

// Sahnenin ve durum satırının tek kaynağı. "meşgul/boşta" ikilisi her işi
// aynı gösteriyordu — düşünmekle dosya okumak ayırt edilemiyordu.
const MODE_LABEL = {
  waking: "Uyanıyor", idle: "Hazır", thinking: "Düşünüyor",
  writing: "Yazıyor", recalling: "Hatırlıyor", working: "Çalışıyor"
};

// Araç çalışırken "çalışıyor" yeterince şey söylemiyordu: dosya yazmakla
// arama yapmak, ekrana bakmakla PLC okumak aynı görünüyordu. Her aracın
// karşılığı bir eylem — çekirdeğin altında bu yazıyor (Claude Code'un
// "Creating / Researching" durumu gibi, renk de kipten geliyor).
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

// Araç satırının simgesi. Model seçmiyor, tür sabit eşleniyor: simgenin işi
// süslemek değil, satırlar taranırken türün bir bakışta ayrılması.
const TOOL_ICON = {
  shell: "❯", read_file: "≡", read_many: "≡", list_dir: "≡", write_file: "✎", edit_file: "✎",
  copy_in: "✎", draw: "✎", search: "◌", fetch: "◌", web: "◌", grep: "◌", semboller: "◌",
  mind_recall: "◍", mind_memory: "◍", mind_goals: "◍",
  screen: "▣", hand: "▣", look: "◉", browser: "⌾", device: "⇄", skill: "✦",
  models: "✦", task: "⑃", schedule: "◔", mail_read: "✉", mail_send: "✉",
  place: "⌖", artifact: "⬒", git: "⌥",
};

// Dönen düşünme kelimeleri. Yapay zekâ yok — sabit listeden birkaç saniyede
// bir sıradaki; sıfır maliyet ama algılanan "canlılığın" çoğunu bu taşıyor.
// Durum MODELLENMİŞ, süslenmiş değil (canlı şikâyet: "düşünüyor,
// kurcalanıyor diye durmadan değişiyor — bunlar gerçek birer meta olmalı").
// Etiket o an GERÇEKTEN olan şeyden türetilir ve durum değişmeden etiket
// değişmez: akıl yürütme kanalı akıyorsa "Akıl yürütüyor", cevap metni
// akıyorsa "Yazıyor", henüz hiçbir şey akmıyorsa "Düşünüyor" (uzarsa
// waiting() zaten "Model yükleniyor…" der). Araç koşarken etiketi ACTION
// verir — o da gerçek: aracın kendisi.
let mullTick = 0;      // eski isim: since() sayacı buna bakıyor
let lastDelta = "";    // "" | "thinking" | "text" — son akan kanal
let turnSeed = 0;      // eylem eşanlamlıları kalktı; tur sayacı olarak kalır

function mull() {
  if (lastDelta === "text") return t("Yazıyor");
  if (lastDelta === "thinking") return t("Akıl yürütüyor");
  return t("Düşünüyor");
}

// Eylem başlığının eşanlamlıları. Tanım ACTION'da (tek gerçek — simge ve
// organ eşlemesi oradan); buradaki çeşitlilik yalnız görüntüleme anında.
// Turda sabit: aynı araç aynı turda hep aynı fiille görünür.
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
  // Belirlenimci: aynı araç HER ZAMAN aynı fiille görünür — eşanlamlı
  // rotasyonu kalktı (durumlar süs değil model; bkz. mull üstü not).
  const pool = ACTION_VARIETY[tool];
  if (pool) return t(pool[0]);
  return t(ACTION[tool]) || tool;
}

let modeTimer = null;

// Yerel sunucular modeli ilk istekte belleğe yüklüyor ve bu 20-60 saniye
// sürebiliyor. O sürede hiçbir şey akmıyor; ekranda "düşünüyor" yazması
// yanlış — düşünmüyor, yükleniyor. Bir şey akmadan bu süre geçerse durum
// satırı bunu söylüyor.
const WAITING_AFTER = 1500;
let waitTimer = null;
// Bu turda herhangi bir şey oldu mu (delta aktı / araç koştu)? Bekleme
// başlığı yalnız GERÇEKTEN hiçbir şey olmamışken görünür; bir kez iş
// başladıysa artık "yükleniyor" değil, modelin/aracın kendi durumu konuşur.
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
  // Bir şey aktı demektir: bekleme uyarısı artık geçersiz.
  if (name !== "thinking") waiting(false);
  const text = label || t(MODE_LABEL[name]) || name;
  // Sahnenin çekirdek-altı etiketi ve üst şerit aynı sözcüğü söylüyor.
  Scene.setMode(name, name === "idle" ? "" : text);
  setStatus(name === "idle" ? "ready" : "busy", text);

  // Kısa ömürlü kipler (hatırlama gibi) kendiliğinden düşünmeye dönüyor;
  // aksi halde ajan işe devam ederken sahne yanlış hikâyeyi anlatıyor.
  if (holdMs) modeTimer = setTimeout(() => { if (busy) setMode("thinking"); }, holdMs);
}

// --- akan cevap -------------------------------------------------------
//
// Ham metin ayrı tutuluyor ve her karede yeniden çiziliyor. Parça parça
// DOM'a eklemek daha ucuz olurdu ama olmuyor: yarım gelen bir kod çiti
// ("```powersh") ancak kapanınca ne olduğu anlaşılan bir şey, o yüzden
// biçimlendirme her zaman metnin tamamına bakmak zorunda.
//
// Yeniden çizim rAF ile bir kareye indiriliyor; yoksa saniyede yüzlerce
// parça gelen bir akışta her parçada yeniden çizim yapılıyordu.

let raw = "";
let pending = null;

// Yeniden çizim saniyede bu kadar. Her karede (60/sn) çizmek uzun bir
// cevapta ana thread'i tıkıyordu: biçimlendirme metnin **tamamını** baştan
// okuyor ve cevap büyüdükçe her kare pahalılaşıyor. Beş bin karakterlik bir
// cevapta yazdıkların gitmiyor, tıklamalar geç işleniyor, sahne takılıyor.
//
// Onda bir saniye göz için yeterince akıcı ve maliyeti altı kat düşürüyor.
const REDRAW_MS = 100;

function write(chunk) {
  raw += chunk;
  lastChunkAt = Date.now();
  if (agentLine) agentLine.classList.remove("stall");
  bumpStream(chunk);
  if (!agentLine) {
    // BOŞLUK SATIR AÇMAZ. Model araçtan sonra çoğu zaman önce "\n\n"
    // akıtıyor ve asıl metin saniyeler sonra geliyor. Eski hal ilk parçada
    // bloğu doğuruyordu: şerit sakinleşiyor ("▸ 1 adım · 19 sn"), sonra
    // ekranda boş bir "NEO ▮" saniyelerce yanıp sönüyordu — kullanıcı ne
    // olduğunu bilmiyor. Artık gerçek metin gelene kadar şerit canlı
    // kalıyor ("Düşünüyor · N sn", tickBusy işletiyor) ve blok ancak
    // yazılacak bir şey varken doğuyor.
    if (!raw.trim()) return;
    raw = raw.replace(/^\s+/, "");   // baştaki boşluk bloğa girmesin
    // Cevap akmaya başlıyor: o ana kadarki adım kümesi KENDİ özet
    // satırına mühürlenir ve şerit BÖLÜNÜR — sonraki araçlar metnin
    // altında yeni bir küme açar (Claude Code'un "Ran 2 commands, used
    // 3 tools ›" ritmi; canlı istek 31.08: "her anlatımın araç detayı
    // kendi satırından açılmalı, tıklayıp görebilmeliyim").
    segmentWork();
    agentLine = line("agent", "");
  }
  if (pending) return;
  pending = setTimeout(() => {
    pending = null;
    // Sahte araç çağrısı: model gerçek çağrı yerine XML'i düz metin yazdı.
    // Cevap değil, başarısız bir deneme — blok DOM'dan düşer (imleç de
    // onunla gider). Model tarafı döngüde düzeltiliyor: "araç çağrını metin
    // olarak yazdın" notu gidiyor ve tur sürüyor.
    if (sahteCagri(raw)) { agentLine.remove(); return; }
    Markdown.into(agentLine, raw);
    scroll();
  }, REDRAW_MS);
}

// --- düşünme ----------------------------------------------------------
//
// Akıl yürütme cevap değil: sohbete karışmıyor, tek satırda sönük akıyor
// ve cevap gelmeye başlayınca kayboluyor. Tamamı saklanıyor ama ekranda
// yalnızca son cümle duruyor — amaç ne düşündüğünü izlemek, okumak değil.

let thought = "";

// Üst şeritte iki ayrı şey duruyor: hangi model (kimlik) ve kaç token
// (durum). Önceki hal ikisini aynı yere yazıyordu ve ilk `usage` olayı
// model adını siliyordu — model değiştirildiğinde ekranda hiçbir zaman
// yeni ad görünmüyordu.
let modelName = "";
let oturumId = "";   // aktif sohbet — sohbete özel model seçimi buna yazar
let tokenNote = "";
let busyNote = "";   // meşgulken saniye saniye ilerleyen "yaşıyor" notu

function showMeta() {
  // Model adı ve token toplamı artık kompozer altındaki dock'ta duruyor;
  // üst şeritte tekrar etmek yerine yalnızca CANLI iş notu kalıyor —
  // akan token ve geçen süre. Boştayken üst şerit sessiz.
  metaEl.textContent = [tokenNote, busyNote].filter(Boolean).join("  ·  ");
}

// Canlı akış sayacı. Yavaş bir modelde "takıldı mı çalışıyor mu" ayrımını
// yapan tek net şey akan token: sayaç büyüyorsa çalışıyor, donmuşsa takılmış.
// Sadece geçen saniye yetmiyordu (takılı bir istek de saniye sayar).
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
  // Kelime tohumu bir ilerliyor — düşünme/eylem sözcükleri turdan tura
  // değişsin. (Ara-anlatım güvenlik ağı bayrakları kalktı: model metni
  // artık katlanmıyor, geri getirilecek bir şey yok.)
  turnSeed += 1;
  lastDelta = "";   // yeni tur: kanal henüz akmadı
}

// "Yaşıyor" nabzı. Sorunun kökü: token-tabanlı sayaç yalnızca token akarken
// ilerliyor — ama bir araç çalışırken (shell, dosya yazma) ya da model bir
// sonraki adımı üretirken token AKMAZ, sayaç donar ve kullanıcı "takıldı mı,
// ne kadar bekleyeceğim, çalışacak mı" diye kalır. Bu ticker akıştan
// bağımsız: meşgul olduğu SÜRECE saniyede bir hem üst şeridin geçen süresini,
// hem açık araç satırlarının süresini, hem de iş başlığını ("shell · 8 sn")
// ilerletir. Böylece ekranda her zaman ilerleyen bir sayı var — asla donmuş
// görünmez, nerede olduğu ve ne kadar sürdüğü bir bakışta belli.
let turnStart = 0;
let busyTicker = null;
// Son metin parçasının zamanı: imleç yalnız gerçekten akan metinde yanıp
// söner; duraksamada (araç/uzun düşünme) söner — "çalışıyor mu belli
// değil" belirsizliği kalksın (bkz. .line.agent.stall).
let lastChunkAt = 0;

function startBusyTicker() {
  if (busyTicker) return;
  if (!turnStart) turnStart = Date.now();
  mullTick = 0;   // her tur "Düşünüyor" ile başlasın
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
  // Akış duraksadıysa canlı imleç yanıp sönmeyi bırakır (CSS .stall).
  if (agentLine) {
    agentLine.classList.toggle("stall", Date.now() - lastChunkAt > 2500);
  }
  const s = Math.round((Date.now() - turnStart) / 1000);
  busyNote = s + " sn";
  showMeta();
  if (!work) return;
  // Model bekleniyor: başlık geri sayımı işletir — donuk "Düşünüyor" değil,
  // bekleme durumunun kendisi görünür (deneme sayacı + kalan saniye).
  if (waitState) { paintWait(); return; }
  // Açık araç satırlarının canlı süresi ("SHELL … 8 sn").
  const openRows = [...work.open.values()];
  for (const row of openRows) {
    if (!row._start) continue;
    const t = Math.round((Date.now() - row._start) / 1000);
    const took = row.querySelector(".took");
    if (took) took.textContent = t + " sn";
  }
  // İş başlığı: bir araç çalışıyorsa eylem + hedef + adım sayısı + süre;
  // cevap akıyorsa (üst sayaç zaten canlı) dokunma; ikisi de yoksa model
  // adım üretiyor → düşünme süresi.
  if (openRows.length) {
    const first = openRows[0];
    const t = Math.round((Date.now() - (first._start || work.since)) / 1000);
    paintLive(" · " + t + " sn");
  } else if (!agentLine) {
    if (!paintLive()) workHead(mull(), "", since(work.since) + streamNote());
    paintThinkLine();
  }
}

// Akış sürerken düşünme/çalışma başlığına eklenen canlı token notu.
function streamNote() {
  return streamTok ? " · " + streamTok + " tok" + (streamRate ? " · " + streamRate + "/sn" : "") : "";
}

// Sırada bekleyen mesajlar. Sırası gelince satırı gerçek satırla
// değiştiriliyor; iki kez çizmemek için eşleştirme metne bakıyor.
const waitingLines = [];

// Gönderilen mesajla birlikte giden görsel/dosyalar. SSE echo bunları
// taşımıyor; mesaj satırı geldiğinde metinden eşleştirilip iliştiriliyor.
const pendingMedia = new Map();

// Kullanıcı mesajına gönderdiği görseli ve dosya etiketlerini ekler —
// "ne gönderdim" bir bakışta görünür yapı.
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

// Kuyruk rozetlerini yeniden numaralar: kaçıncı sırada olduğu her
// eklemede/işlenmede güncelleniyor. Tek bekleyen varsa numara yok — "sırada"
// yeter; birden fazla varsa "sırada · 2" gibi konum görünüyor.
function renumberQueue() {
  const many = waitingLines.length > 1;
  waitingLines.forEach((w, i) => {
    if (w.badge) w.badge.textContent = many ? t("Sırada") + " · " + (i + 1) : t("Sırada");
  });
}

// Muhakeme akarken ham metnin ekrandan geçmesi cevabın yerini alıyordu:
// modelin kendi kendine konuştuğu cümleler ("No, let's keep it") sohbette
// duruyor ve okunacak şey sanılıyordu. Akan şey artık tek bir satır —
// ne yaptığı ve ne kadar sürdüğü. Muhakemenin kendisi kaybolmuyor:
// satıra tıklayınca açılıyor, düşünürken de bittikten sonra da.
// Düşünme satırı ne zaman AÇILIR?
//
// Her araç adımı arasında model bir-iki saniye düşünüyor ve eski hal her
// birine bir satır açıyordu: 30 adımlık bir turda 30 tane "✻ Düşündü · 1 sn
// · 27 kelime". Şerit açıldığında okunacak şey (adımlar) bu gürültünün
// içinde kayboluyordu. Önemsiz düşünme satır AÇMAZ.
//
// Eşikler: bir muhakeme ya UZUN sürmüşse (kullanıcı beklediyse, sebebini
// görmeye hakkı var) ya da HACİMLİyse (gerçekten bir plan kurulmuş)
// satır olur. İkisinin de altındaki, iki araç arasındaki refleks
// düşüncedir — anlatacak bir şeyi yok.
const THINK_MIN_S = 3;        // bu kadar sürdüyse: kullanıcı bekledi
const THINK_MIN_WORDS = 60;   // bu kadar yazdıysa: plan kurmuş

function think(chunk) {
  const w = ensureWork();
  // Akış sırası korunuyor: o ana kadar akan cevap metni ara-anlatım olarak
  // şeride katlanır ve şerit akışın sonuna iner — düşünme kutusu daha önce
  // yazılmış metnin ÜSTÜNE (turun tepesine) düşmez, kronoloji bozulmaz.
  foldNarration();
  dockWork(w);
  w.head.classList.add("busy");
  if (!w.thought) {
    // Ardışık düşünme birleşir: araya adım girmediyse bu, kesilmiş TEK bir
    // muhakemedir. İki ayrı satır açmak onu iki iş gibi gösterirdi.
    const son = w.body.lastElementChild;
    if (son && son.classList.contains("think") && son.classList.contains("done")) {
      w.thought = son;
      son.classList.remove("done", "open");
      son.onclick = null;
      thought = (son._full || "") + "\n\n";
      w.thinkStart = Date.now() - (son._secs || 0) * 1000;
    } else {
      w.thought = document.createElement("div");
      w.thought.className = "act note think";
      w.body.append(w.thought);
      w.thinkStart = Date.now();
      thought = "";
    }
    canliDusunceTiklanir(w.thought);
  }
  thought += chunk;
  bumpStream(chunk);
  // Ekrana varsayılan olarak KUYRUK yazılıyor: akan muhakemenin son birkaç
  // cümlesi. Tam metni her parçada baştan basmak şeridi devasa yapıyordu.
  // Kutuya tıklanınca (`open`) tamamı görünür — koşarken de okunabilir
  // (canlı yara: "detayına tıklıyorum açılmıyor").
  const acik = w.thought.classList.contains("open");
  const goster = acik ? thought
    : (thought.length > 600 ? "…" + thought.slice(-600) : thought);
  w.thought.textContent = goster.trim();
  if (!paintLive()) workHead(mull(), "", since(w.since) + streamNote());
  paintThinkLine();
  // Kutu içi kaydırma: kullanıcı DİPTEYSE son cümleyi takip et; yukarı
  // kaydırıp okuyorsa yerinden oynatma — her parçada dibe çekmek okumayı
  // imkânsız kılıyordu ("arkada kalıyor" — canlı şikâyet).
  const dipte = w.thought.scrollHeight - w.thought.scrollTop
    - w.thought.clientHeight < 40;
  if (!acik || dipte) w.thought.scrollTop = w.thought.scrollHeight;
  if (w.body.hidden) scroll();   // katlıyken alta bak; açıkken kullanıcıya bırak
}

// KOŞAN muhakeme kutusu da tıklanabilir: kuyruk görünümü ile tam metin
// arasında geçiş. Eskiden onclick yalnız bitmiş düşünceye takılıyordu —
// koşarkenkine tıklamak hiçbir şey yapmıyordu (canlı yara, 31.08).
function canliDusunceTiklanir(box) {
  box.title = t("Tıkla — akan muhakemenin tamamını gör");
  box.onclick = (ev) => {
    ev.stopPropagation();
    const acik = box.classList.toggle("open");
    box.textContent = (acik ? thought
      : (thought.length > 600 ? "…" + thought.slice(-600) : thought)).trim();
    if (acik) {
      box.scrollTop = 0;
      revealAboveComposer(box);
    } else {
      box.scrollTop = box.scrollHeight;
      clearFitAboveComposer(box);
    }
  };
}

// Geçen süre. Sabit bir "düşünüyor" satırı, uzun bir turda donmuş gibi
// duruyor; sayacın ilerlemesi çalıştığını gösteriyor.
function since(started) {
  const seconds = Math.round((Date.now() - started) / 1000);
  return seconds > 0 ? " · " + seconds + " sn" : "";
}

// Operatör notu (kendiliginden hatirlananlar, hedef ozeti) katlanmış
// geliyor. Açıkta bırakmak sohbeti boğuyordu: kullanicinin yazmadigi,
// çoğunlukla da okumadığı bir metin cevaptan uzun duruyordu.
function note(text) {
  const first = String(text || "").split("\n")[0];
  const short = first.length > 72 ? first.slice(0, 72) + "…" : first;

  // Tur sırasındaki bir not (kendiliğinden hatırlananlar, hedef özeti) bir
  // sohbet satırı DEĞİL — turun etkinliğidir. İş şeridinin İÇİNE katlanıyor
  // (Claude Code gibi: kullanıcı → şerit → cevap). Böylece her turda ayrı bir
  // "zihninde arandı" satırı sohbeti şişirmiyor; merak eden şeridi açıp görüyor.
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

  // Tur dışı bağımsız not: eskisi gibi katlanır bir üst-düzey satır.
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

// Düşünme bloğu bitti: tam metin tek satıra katlanıyor — "✻ Düşündü · 8 sn ·
// 140 kelime". Devasa muhakemeyi şeritte tam boy bırakmak, şerit açıldığında
// sohbeti yine boğuyordu. Metin kaybolmuyor: satıra tıklayınca açılıyor.
function closeThought() {
  if (work) {
    const box = work.thought;
    const full = thought.trim();
    if (box) {
      const secs = Math.round((Date.now() - (work.thinkStart || work.since)) / 1000);
      const words = full ? full.split(/\s+/).length : 0;
      // Muhakeme HER HÂLÜKÂRDA saklanıyor — eşik yalnızca satır açma
      // kuralı, saklama kuralı değil. Yutulan düşünce de turun arşivine
      // giriyor ve açılan herhangi bir "✻ Düşündü" satırından okunabiliyor.
      if (full) work.thinkAll.push(full);

      if (!full || (secs < THINK_MIN_S && words < THINK_MIN_WORDS)) {
        // Önemsiz: satır açılmaz. (Metin arşivde duruyor.)
        box.remove();
      } else {
        const label = t("✻ Düşündü") + (secs > 0 ? " · " + secs + " sn" : "")
                    + " · " + words + t(" kelime");
        box.classList.add("done");
        box.classList.remove("open");   // canlı tam-görünüm izi kalmasın
        box.title = "";
        box.textContent = label;
        box.title = t("Tıkla — bu turun muhakemesini gör");
        // Birleştirme ve yeniden açma için satırda taşınıyor.
        box._full = full;
        box._secs = secs;
        const arsiv = work.thinkAll;   // aynı dizi: sonra yutulanlar da görünür
        let open = false;
        box.onclick = (ev) => {
          ev.stopPropagation();
          open = !open;
          box.textContent = open ? arsiv.join("\n\n———\n\n") : label;
          box.classList.toggle("open", open);
          // Açılınca sayfa uzamasın diye CSS max-height + iç scroll;
          // burada yalnızca kutuyu görünür alanda tut.
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

// Cevap tam açık kalır. Eskiden FOLD_AFTER eşiğinde "Devamı"ya katlanıyordu;
// soru-cevapta (ürün listesi, açıklama) kullanıcı her seferinde tıklamak
// zorunda kalıyordu — mantıksız. Araç izi zaten acts şeridinde; asıl metin
// katlanmaz.

// Akmakta olan metin bloğunu kapatır ve ekranda bırakır.
function finishAgentLine() {
  clearTimeout(pending);
  pending = null;
  if (!agentLine) return;

  // Model araç çağırmadan önce sık sık boşluk akıtıyor; bu bomboş bir
  // satır bırakıyordu. Sahte araç çağrısı da aynı kefede: ham XML sohbette
  // kalmaz (bkz. sahteCagri).
  if (!raw.trim() || sahteCagri(raw)) agentLine.remove();
  else {
    Markdown.into(agentLine, raw);
    agentLine._rawText = raw;
    attachMsgActs(agentLine, "agent");
    agentLine.classList.add("done");
  }
  agentLine = null;
  raw = "";
}

// --- asılı akış imleci -------------------------------------------------
//
// İmleç (yanıp sönen ▮) bir DURUM değil, bir CSS kuralı: `.line.agent`
// `.done` almadıkça imleç basılıyor. Yani akış biterken `.done` almayan ya
// da hiç kapanmayan bir blok, ekranda sonsuza kadar yanıp sönen boş bir
// "NEO ▮" olarak kalıyor — kullanıcı neo hâlâ yazıyor sanıyor.
//
// Kanıtlanmış boşluklar: "interrupted" olayı satırı hiç mühürlemiyordu ve
// "empty_assistant_turn" (model hiçbir şey döndürmedi) arayüzde hiç
// karşılanmıyordu. Tek tek yamamak yerine burada bir SÜPÜRGE var: turun
// bittiği her yolda, canlı akış dışındaki bütün mühürsüz ajan blokları
// kapatılıyor — boşsa DOM'dan siliniyor, doluysa mühürleniyor. Böylece
// yarın yeni bir yol açılsa da imleç asılı kalmıyor.
function clearCursor() {
  for (const el of thread.querySelectorAll(".line.agent:not(.done)")) {
    if (el === agentLine) continue;   // canlı akış: imleci hak ediyor
    if (el.textContent.trim()) el.classList.add("done");
    else el.remove();
  }
}

// Eskiden burada bir "güvenlik ağı" vardı: tur araçla bitip ekranda cevap
// kalmadıysa, şeride katlanmış son anlatımı geri getiriyordu. Yamaya gerek
// kalmadı — model metni artık hiç katlanmıyor (bkz. foldNarration), yani
// geri getirilecek bir şey de yok. Aynı metnin iki kez görünme riski de
// böylece kökten kalktı.
function sealLine() {
  closeThought();
  closeWork();
  finishAgentLine();
  clearCursor();
}

// Kaç blok açıkta kalıyor. Bir blok çoğu zaman bir başlık ya da tek bir
// cümle; yalnızca onu bırakmak cevabı okunmaz yapıyordu.
const FOLD_KEEP = 2;

function fold(box) {
  // Baştaki bloklar açıkta: cevabın sonucu. Gerisi kapanıyor.
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

// --- sohbet -----------------------------------------------------------
$("composer").addEventListener("submit", (ev) => {
  ev.preventDefault();
  // Koşarken boş kutuyla basmak = durdur; yazı varsa eski kuyruk davranışı.
  if (busy && !input.value.trim()) { post("/api/interrupt"); Speech.stop(); return; }
  send();
});
input.addEventListener("input", paintSend);

// Kompozer kutusunun NERESİNE tıklanırsa tıklansın yazı alanı odaklanır.
// Natif tur (31.08): kutunun boş alanına tıklayan kullanıcı odak almıyor,
// ardından Ctrl+V boşa gidiyordu ("yapıştır çalışmıyor"un yarısı buydu).
document.querySelector(".compose-shell").addEventListener("mousedown", (ev) => {
  if (ev.target.closest("button, a, input, textarea, select, .dock, .git-bar, .pop")) return;
  ev.preventDefault();   // odağı çalma — doğrudan biz veriyoruz
  input.focus();
});

// Kabuk yüksekliği değişince (textarea, git, dock) sohbet alt boşluğunu
// ölç — sabit 128px uzun kabukta düşünceyi input altına gömüyordu.
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

  // Mercek açıkken mesaj kareyi de taşıyor. "Beni görüyor musun" diye
  // sorup görüntü göndermemek, kamerayı açık tutmanın anlamını
  // kaldırıyordu: model bakacak bir şey bulamıyor ve sessiz kalıyordu.
  if (Camera.on && !frame) {
    Camera.say(t("Bakıyor…"));
    await Camera.snap();
  }

  // Kamera karesi metinsiz de gönderilebiliyor ("şuna bak" demeden).
  //
  // Meşgulken de gönderiliyor: mesaj sıraya giriyor ve tur bitince
  // işleniyor. Önceki hal sessizce atıyordu — kullanıcı yazıp enter'a
  // basıyor ve hiçbir şey olmuyordu.
  if (!text && !frame && !attached.length && !Camera.on) return;
  // İyimser çizim yok: mesaj olay günlüğüne yazılınca SSE ile geri geliyor.
  // İki kaynaktan çizmek kopyalanmaya yol açardı.
  // Ekler withFiles içinde SIFIRLANIYOR: ad listesi ve görsel ondan ÖNCE
  // alınmalı (eski sıralama, iliştirilen dosya etiketlerini hep boş
  // bırakıyordu). Kamera karesi yoksa son eklenen görüntü mesaja gider.
  const ekler = attached.slice();
  const gorsel = frame || (ekler.filter((a) => a.image).pop() || {}).image || "";
  const posted = withContext(withFiles(withMentions(text)));
  // Gönderilen görsel ve dosyalar SSE echo'sunda taşınmıyor (görüntü ağır,
  // ayrıca araçtan gelen kareler `internal`). İstemci elindeki veriyle:
  // mesaj satırı geldiğinde küçük resmi ve dosya etiketlerini ona iliştir.
  if (gorsel || ekler.length) {
    pendingMedia.set(posted, { frame: gorsel, files: ekler.map((a) => a.name) });
  }
  post("/api/chat", { text: posted, image: gorsel });
  // Kullanıcı kendi sözünü söyledi: bekleyen "Planı uygula" teklifi bayat.
  hidePlanOffer();
  // Mesaj gönderen kullanıcı cevabı görmek istiyor: yukarıda unutulmuş bir
  // kaydırma konumu takibi kilitlemesin.
  resumeFollow(false);
  dropFrame();
  // Kare gönderildi; önizlemedeki etiket cevabı bekliyor.
  if (Camera.on) Camera.say(t("Bakıyor…"));
  input.value = "";
  input.style.height = "auto";
}

// --- kamera -------------------------------------------------------------
//
// Kare doğrudan gönderilmiyor; yazma satırının üstünde önizleniyor. Ne
// gönderdiğini görmeden göndermek, kameranın ne yakaladığını bilmemek demek.

let frame = "";

Camera.init({
  onFrame: (data) => {
    frame = data;
    $("shot-image").src = data;
    $("shot").hidden = false;
    input.focus();
  },
});

// Etiket kisa olmali: onizlemenin altinda tek satir yer var.
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

// Kamera düğmesi yazma satırında yok: üstteki izleme ikonu aynı aygıtı
// zaten açık tutuyor; tarayıcı getUserMedia ikinci kez açınca "açılamadı"
// diyordu. Kare eklemek için ataş / sürükle.

$("lens-snap").addEventListener("click", () => Camera.snap());
$("lens-close").addEventListener("click", () => Camera.close());

// --- kompozer + menüsü --------------------------------------------------
//
// Ekleme kısayolları tek yerde: dosya ve ilgili ayar sekmeleri.
// Claude Code'daki + menüsünün karşılığı — kompozerden çıkmadan.
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

// --- eklenen dosyalar ---------------------------------------------------
//
// Sürükle, yapıştır ya da gözat — üçü de dosyayı atölyeye kopyalıyor ve
// ajana yolunu veriyor. Ajan oradan `read_file` ile açıp inceleyebiliyor.
// Görüntüler ayrıca mesaja iliştiriliyor: model doğrudan bakabilsin.

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
      const kucuk = document.createElement("img");
      kucuk.src = item.image;
      kucuk.alt = item.name;
      chip.append(kucuk);
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

// Eklenen dosyaların yolları mesaja ekleniyor: tarayıcı yerel yolu vermiyor,
// ama atölyedeki kopyanın yolu ajan için yeterli.
function withFiles(text) {
  if (!attached.length) return text;
  const list = attached.map((f) => "- " + f.path).join("\n");
  attached = [];
  drawDrops();
  return (text ? text + "\n\n" : "") + "Eklenen dosyalar (atölyende):\n" + list;
}

// --- uygulama bağlamı ---------------------------------------------------
//
// Uygulamalar panelinden bir uygulama "konuş" olarak seçilince o
// konuşmanın bağlamına giriyor: bir sonraki mesaja kısa, açık bir bağlam
// satırı ekleniyor ki ajan hangi uygulamadan bahsettiğimizi bilsin. Dürüst:
// eklenen şey mesajda görünüyor, gizli bir enjeksiyon değil. Kalıcı değil —
// bir kez gönderilince temizleniyor (art arda başka konuya kaymasın).
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

// `@` ile işaret edilen dosyalar mesaja açıkça yazılıyor (bkz. komut.js).
// Modül yoksa metin olduğu gibi geçiyor.
function withMentions(text) {
  return (typeof Komut !== "undefined" && Komut.bahisEkle) ? Komut.bahisEkle(text) : text;
}

// Orkestra güvertesine köprü: modül yoksa (yüklenmemişse) sessiz geç.
function orchStart(e) { if (typeof Orchestra !== "undefined") Orchestra.start(e); }
function orchTool(e) { if (typeof Orchestra !== "undefined") Orchestra.tool(e); }
function orchEnd(e) { if (typeof Orchestra !== "undefined") Orchestra.end(e); }
function orchSeed(list) { if (typeof Orchestra !== "undefined" && Orchestra.seed) Orchestra.seed(list); }

// Koşan görevler paneline köprü: aynı kalıp. Panel kapalıyken de tazeleniyor
// — üst bardaki rozet gerçeği söylemeli.
function tasksRefresh() { if (typeof Gorevler !== "undefined") Gorevler.tazele(); }
function tasksDone(e) { if (typeof Gorevler !== "undefined") Gorevler.bitti(e); }

// Değişiklik defteri köprüsü: tur sınırları.
function chgTurnStart() { if (typeof Degisiklik !== "undefined") Degisiklik.turBasladi(); }
function chgTurnEnd() { if (typeof Degisiklik !== "undefined") Degisiklik.turBitti(); }

function withContext(text) {
  const bits = [];
  if (typeof Cameras !== "undefined" && Cameras.baglam) {
    const cam = Cameras.baglam();
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

// --- odak modu ----------------------------------------------------------
//
// Bütün paneller kapanıyor, geriye çekirdek ve yazma alanı kalıyor —
// biriyle konuşur gibi. Çalışma/simülasyon paneli (görüntüleyici, uygulama,
// geçmiş, ayar) isteğe bağlı; odak modunda hepsi çekiliyor. Kamera ya da
// ses açıksa bu hâl gerçekten karşılıklı bir konuşmaya dönüşüyor.
let focused = false;
function toggleFocus() {
  focused = !focused;
  document.body.classList.toggle("focus", focused);
  if (typeof Scene !== "undefined") Scene.focus(focused);
  if (focused) {
    // Açık her paneli kapat: odak tek bir şeye.
    try { Viewer.close(); } catch {}
    try { Apps.close(); } catch {}
    try { History.close(); } catch {}
    try { if (window.JobsPanel) JobsPanel.close(); else Gorevler.kapat(); } catch {}
    try { if (typeof Cameras !== "undefined") Cameras.gizle(); } catch {}
    const s = document.getElementById("settings"); if (s) s.hidden = true;
    document.body.classList.remove("viewing", "settling");
  }
  document.getElementById("focus").classList.toggle("on", focused);
}
document.getElementById("focus").addEventListener("click", toggleFocus);

// --- gece / gündüz -------------------------------------------------------
//
// Tema `<html data-theme>` ile; renkler CSS token'larında olduğundan sahne
// (canvas) getComputedStyle ile bir sonraki karede kendiliğinden uyuyor.
// Kayıtlı tema index.html'de sayfa çizilmeden uygulanıyor (flash yok).
function paintThemeIcon() {
  const light = document.documentElement.dataset.theme === "light";
  const moon = document.querySelector("#theme .ic-moon");
  const sun = document.querySelector("#theme .ic-sun");
  if (moon) moon.hidden = light;   // açıkta ay gizli
  if (sun) sun.hidden = !light;    // açıkta güneş görünür
}

// Native başlık çubuğunu (OS) uygulama temasıyla birlikte çevir: koyu temada
// koyu çubuk, açık temada açık çubuk. Masaüstü kabuğu (pywebview) yoksa —
// tarayıcıda açıldıysa — sessizce atlanır.
function syncTitlebar() {
  const light = document.documentElement.dataset.theme === "light";
  try { window.pywebview.api.paint_titlebar(!light); } catch {}
}

document.getElementById("theme").addEventListener("click", () => {
  const light = document.documentElement.dataset.theme === "light";
  if (light) delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = "light";
  try { localStorage.setItem("neo-theme", light ? "dark" : "light"); } catch {}
  paintThemeIcon();
  syncTitlebar();
});
paintThemeIcon();
// pywebview API'si sayfadan biraz sonra hazır olabiliyor: hazır olayını bekle,
// olmazsa kısa bir gecikmeyle yine dene (ilk yüklemede doğru çubuk rengi).
window.addEventListener("pywebviewready", syncTitlebar);
setTimeout(syncTitlebar, 800);

// --- beni tanı ikonu -----------------------------------------------------
//
// Üst bardaki filiz: özellik açıkken görünür, eğitim koşarken nabız atar,
// tıklanınca hemen eğitir. Kaynak iki yer: açılışta GET /api/tanima,
// sonrası SSE "tanima" olayları (acik/kapali/basladi/bitti) — ayar
// sayfasındaki anahtar başka sekmede çevrilse de ikon anında uyar.

let tanimaSon = "";        // son eğitimin ISO tarihi; ipucunda kısa biçim
let tanimaKosuyor = false;
let tanimaBasladi = 0;     // nabzın en az görünmesi gereken sürenin başı

// Nabız bu süreden kısa görünmesin: bir saniyeden kısa süren bir koşuda
// kullanıcı düğmeye basıyor ve ekranda hiçbir şey olmuyormuş gibi oluyor.
const TANIMA_EN_AZ_MS = 3000;

function tanimaTarih() {
  if (!tanimaSon) return t("henüz yok");
  const d = new Date(tanimaSon);
  if (isNaN(d)) return tanimaSon;
  return d.toLocaleString(undefined, {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function tanimaIkon(state) {
  const ikon = $("tanima-ikon");
  if (!ikon) return;
  if (state === "acik") ikon.hidden = false;
  else if (state === "kapali") ikon.hidden = true;
  else if (state === "basladi") { tanimaKosuyor = true; tanimaBasladi = Date.now(); }
  else if (state === "bitti") {
    // Nabız EN AZ bu kadar görünsün: eğitim bazen bir saniyeden kısa
    // sürüyor ve kullanıcı düğmeye bastığında ekranda hiçbir şey olmamış
    // gibi oluyordu. "Bir şey oldu" görülmeli.
    const kalan = TANIMA_EN_AZ_MS - (Date.now() - tanimaBasladi);
    if (kalan > 0) { setTimeout(() => tanimaIkon("bitti"), kalan); return; }
    tanimaKosuyor = false;
    tanimaSon = new Date().toISOString();
  }
  ikon.classList.toggle("kosuyor", tanimaKosuyor);
  ikon.title = tanimaKosuyor
    ? t("Şu an seni tanıyorum — eğitim arka planda sürüyor")
    : t("Beni tanı açık") + " · " + t("son eğitim") + ": " + tanimaTarih()
      + " · " + t("tıkla: şimdi eğit");
}

// "Şimdi eğit" SESSİZ KALMAZ. Eski hal düğmeye basınca ekranda hiçbir şey
// göstermiyordu; gerçekte döngü başlayıp bir saniyeden kısa sürede "yeni
// veri az: 0/50" deyip çıkıyordu. Artık her sonuç tek satırla söyleniyor —
// başladıysa da, başlayamadıysa NEDENİYLE.
const TANIMA_SEBEP = {
  basladi: "Tanıma eğitimi başladı — arka planda sürüyor.",
  veri_yok: "Yeni veri yok — yeni anılar biriktikçe kendiliğinden çalışacak.",
  kosuyor: "Eğitim zaten koşuyor.",
  duzenek_yok: "Eğitim düzeneği bu makinede kurulu değil.",
  kapali: "Beni tanı kapalı — Ayarlar'dan açabilirsin.",
  ara_yok: "Henüz sırası değil — yeni anılar biriktikçe kendiliğinden çalışacak.",
  baslatilamadi: "Eğitim başlatılamadı.",
};

$("tanima-ikon").addEventListener("click", async () => {
  // Koşarken tıklama sessizce yok sayılır: ipucu zaten durumu söylüyor,
  // ikinci bir koşu açmak da mümkün değil (süreç tekil).
  if (tanimaKosuyor) return;
  const cevap = await post("/api/tanima", { simdi: true });
  const sebep = (cevap && cevap.sebep) || "baslatilamadi";
  line("alert", t(TANIMA_SEBEP[sebep] || TANIMA_SEBEP.baslatilamadi));
});

fetch("/api/tanima").then((r) => r.json()).then((d) => {
  tanimaSon = d.son || "";
  tanimaKosuyor = !!d.kosuyor;
  tanimaIkon(d.on ? "acik" : "kapali");
}).catch(() => {});

// --- sol panel yeniden boyutlandırma ------------------------------------
// Uygulamalar ve konuşmalar panelleri soldan açılıyor; sağ kenarlarındaki
// tutamaktan sürüklenip genişliyorlar. Genişlik tek bir değişkende
// (--left-w) — hangi panel açıksa ona uygulanıyor.
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
    try { grip.setPointerCapture(e.pointerId); } catch { /* eski motor */ }
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
// Esc odak modundan çıkarır: kaçış her zaman elde olsun.
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && focused) toggleFocus();
});

// --- mikrofon -----------------------------------------------------------
//
// Basılı tut, konuş, bırak: söylediğin yazı alanına düşüyor. Doğrudan
// göndermiyoruz — tanıma her zaman doğru değil ve kullanıcının düzeltme
// şansı olmalı. Uyandırma sözü ayrı: o zaten bilinçli bir çağrı.

Listen.init({
  onText: (text) => {
    input.value = (input.value ? input.value + " " : "") + text;
    input.focus();
    input.dispatchEvent(new Event("input"));
  },
  onCommand: (text) => {
    // Pencere gizliyken de dinleniyor; söz duyulunca geri gelmeli, yoksa
    // cevap görünmeyen bir pencerede akıyor.
    post("/api/wake");
    if (!busy) post("/api/chat", { text });
  },
  onState: (label) => {
    if (label) setStatus("busy", label);
    else if (!busy) setStatus("ready", t("Hazır"));
  },
  // Sesin duyulup duyulmadığı görünmeli: "konuştum ama hiçbir şey olmadı"
  // durumunda kabahatin nerede olduğu ölçer olmadan anlaşılmıyor.
  onLevel: showLevel,
});

// Seviye iki yerden gelebiliyor: elle konuşurken tarayıcının ölçeri,
// arkada dinlerken Python'daki kulak. İkisi de aynı halkayı büyütüyor.
function showLevel(level) {
  const shown = Math.min(1, level * 8);
  const hear = $("hear");
  const mic = $("mic");
  // HUD mikrofonu da nabız atsın: kompozer #mic gizliyse "hiç hareket yok"
  // sanılıyordu.
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

let kulakAcik = false;

function setListening(enabled, wake, open) {
  $("mic").hidden = !enabled;
  // Sürekli dinleme Python tarafında: tarayıcıda duramıyordu çünkü
  // pencere gizlendiğinde Chromium arka plan zamanlayıcılarını dakikaya
  // kısıyor ve dinleme ölüyor. Uyandırma sözü veya serbest dinleme varken
  // düğme kulağı keser; yoksa bas-konuş.
  kulakAcik = !!(enabled && (wake || open));
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
    : kulakAcik
      ? t("Tıkla: dinlemeyi durdur")
      : t("Tıkla ve konuş");
}

// Tıkla: sürekli dinleme açıksa kulağı kes / aç. Basılı tutmak değildi:
// kullanıcı düğmeye tıklayıp bırakıyor, o da sıfır saniyelik bir kayıt
// üretip sessizce atılıyordu. Uyandırma yoksa eski bas-konuş.
$("mic").addEventListener("click", async () => {
  if (kulakAcik) {
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

// --- ses / dinleme HUD ------------------------------------------------
// Kamerayla aynı dil: kapalıyken üstü çizili, tıkla → popup.

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

function kapatDuyuPop(keep) {
  for (const id of ["mute-pop", "hear-pop", "cam-pop"]) {
    const el = $(id);
    if (el && id !== keep) el.hidden = true;
  }
}

$("mute").addEventListener("click", (ev) => {
  ev.stopPropagation();
  const pop = $("mute-pop");
  const next = pop.hidden;
  kapatDuyuPop("mute-pop");
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
  kapatDuyuPop("hear-pop");
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

// --- yetki --------------------------------------------------------------
//
// "İstersem anında tüm yetkileri verebilmeliyim" — ayar sayfasını açıp
// sekme değiştirmek o an istenen şey değil. Şeritteki düğme iki hal
// arasında gidip geliyor ve tam yetki açıkken bunu saklamıyor.

const AUTHORITY = { auto: "otomatik", ask: "sorar", plan: "salt okunur", yolo: "tam yetki" };

// Tam yetkiden çıkarken hangi kipe dönüleceği. İlk okunan kip saklanıyor:
// kullanıcı "sor"dan geldiyse "sor"a dönmeli, "otomatik"e değil.
let mode = "ask";
let previous = "ask";

// Plan kipine girmeden önceki kip. "Planı uygula" düğmesi kipi buna geri
// çevirir; sayfa plan kipinde açıldıysa (öncesi bilinmiyor) auto'ya döner.
let beforePlan = "auto";
// İlk setAuthority çağrısı sunucudan gelen gerçeği yerleştirir; ondan
// önceki yerel varsayılan ("ask") bir geçiş sayılmamalı.
let modeKnown = false;

function setAuthority(next) {
  if (modeKnown && next === "plan" && mode !== "plan" && mode !== "yolo") beforePlan = mode;
  // Kip plandan çıktıysa bekleyen "Planı uygula" teklifi bayatladı.
  if (next !== "plan") hidePlanOffer();
  modeKnown = true;
  mode = next;
  const button = $("authority");
  button.classList.toggle("full", next === "yolo");
  button.title = t("Yetki: ") + (t(AUTHORITY[next]) || next) +
                 (next === "yolo" ? t(" — hiçbir şey sorulmuyor") : t(" · tıkla: kip seç"));
  if (next !== "yolo") previous = next;
  // Kilit ile kompozer altındaki kip çipi aynı gerçeği göstersin.
  dockRender();
}

$("authority").addEventListener("click", (ev) => {
  // Kilit tek tıkta yalnız yolo↔önceki arasında gidip geliyordu; ne yaptığı
  // belirsizdi. Dock kip çipiyle aynı menü.
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

// --- dock: kompozer altındaki durum şeridi ------------------------------
//
// Model, düşünme derinliği, yetki kipi ve bağlam doluluğu — ayar sayfasını
// açmadan bir bakışta görünsün. Model tıklanınca ayarların model sekmesi
// açılıyor; derinlik ve kip tek tıkla sıradakine geçiyor — dört seçenek
// için menü açmak, tıklamaktan uzun sürüyor.

const EFFORTS = ["low", "medium", "high", "xhigh", "max"];
const MODE_ORDER = ["auto", "ask", "plan", "yolo"];

let dockEffort = "";
let contextWindow = 0;
let lastKirilim = [];   // kalem kalem kırılım (snapshot + usage)

function dockRender() {
  $("dock-model").textContent = modelName || "model";
  $("dock-effort").textContent = dockEffort || "—";
  $("dock-mode").textContent = t(AUTHORITY[mode]) || mode || "—";
  $("dock-mode").classList.toggle("full", mode === "yolo");
  // Bağlam göstergesi ilk turdan önce de görünsün: boş bir çubuk + boş
  // metin "yok" gibi duruyordu — %0 da bir bilgi.
  if (!$("dock-ctx-pct").textContent) $("dock-ctx-pct").textContent = "%0";
}

// Bağlam doluluğu. Yüzde `usage` olayından: istemin toplamı / pencere.
// Dolmaya yaklaşınca renk değişiyor — sayı okunmadan da fark edilsin.
function ctxKisa(n) {
  n = Math.max(0, Number(n) || 0);
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(1) + "K";
  return String(Math.round(n));
}

function ctxUsed(promptTotal, kirilim) {
  const listed = (kirilim || []).reduce((s, p) => s + (Number(p.n) || 0), 0);
  return Number(promptTotal) || listed;
}

function paintCtxBar(bar, kirilim, window_, used) {
  if (!bar) return;
  bar.replaceChildren();
  const cap = window_ || used || 1;
  const parts = (kirilim || []).filter((p) => (p.n || 0) > 0);
  if (!parts.length && used) {
    const i = mk("i", "ctx-seg sohbet");
    i.style.width = Math.min(100, (used / cap) * 100) + "%";
    bar.append(i);
    return;
  }
  for (const p of parts) {
    const i = mk("i", "ctx-seg " + (p.id || ""));
    i.style.width = Math.max(0.4, (p.n / cap) * 100) + "%";
    i.title = t(p.ad) + " · " + ctxKisa(p.n);
    bar.append(i);
  }
}

function dockContext(promptTotal, tahmin, kirilim) {
  if (kirilim) lastKirilim = kirilim;
  const used = ctxUsed(promptTotal, lastKirilim);
  if (!contextWindow) return;
  const pct = used ? Math.min(100, Math.round((used / contextWindow) * 100)) : 0;
  $("dock-ctx-pct").textContent = "%" + pct;
  paintCtxBar($("dock-ctx-bar"), lastKirilim, contextWindow, used);
  const box = $("dock-ctx");
  box.classList.toggle("warn", pct >= 70 && pct < 90);
  box.classList.toggle("hot", pct >= 90);
  // Sürdürülen bir oturumda rakam sağlayıcının saydığı gerçek değer
  // olmayabilir (eski günlükte usage yok): kaba tahmin olduğu söyleniyor.
  // Uydurma bir kesinlik satmaktansa "yaklaşık" demek dürüst.
  box.classList.toggle("tahmin", !!tahmin);
  box.title = tahmin ? t("Bağlam doluluğu — yaklaşık (geçmişten tahmin)")
                     : t("Bağlam doluluğu");
}

// --- maliyet çipi -------------------------------------------------------
//
// Oturum toplamı, Claude Code'un /usage ruhuyla: "≈$0.42". Konuşmayı
// yeniden açınca geçmiş turlar da tohumlanır. Fiyat OpenRouter
// kataloğundan; bilinmiyorsa çip token sayısına düşer. Tıklayınca bu tur
// + oturum kırılımı açılır.

let fiyat = null;                              // {girdi, cikti} USD/token | null
let kullanim = { tur: null, oturum: null };    // usage olayının toplamları
// Bu oturum için harcama üst sınırı (USD); null = sınırsız. Gerçek fren
// sunucuda (bkz. desktop.Bridge._butce_freni): oradaki sayaç tur döngüsünü
// durduruyor. Buradaki kopya yalnızca göstermek ve kutuyu doldurmak için.
let butce = null;

// Çıktı fiyatı $/M bu eşiğin üstündeyse model "premium": çip amber tona
// döner ve title'a not düşer — göze batmadan uyarır.
const PREMIUM_USD_M = 20;

function para(n) {
  // Küçük tutarlar iki basamakta "0.00" olup kayboluyordu; kuruş altı üç
  // basamak gösteriliyor.
  return "$" + (n >= 0.01 || n === 0 ? n.toFixed(2) : n.toFixed(3));
}

function maliyet(k) { return k.girdi * fiyat.girdi + k.cikti * fiyat.cikti; }

function kisaTok(n) { return (n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n)); }

function premiumMu() { return !!(fiyat && fiyat.cikti * 1e6 > PREMIUM_USD_M); }

function dockCost() {
  const chip = $("dock-cost");
  const tur = kullanim.tur;
  const oturum = kullanim.oturum;
  // Çip OTURUM toplamını gösterir — konuşmayı yeniden açınca geçmiş
  // harcama da buraya tohumlanır. "Bu tur" kırılımda kalır.
  const varMi = oturum && (oturum.girdi || oturum.cikti || oturum.cagri);
  if (!varMi && !butce) { chip.hidden = true; return; }
  chip.hidden = false;
  chip.classList.toggle("premium", premiumMu());
  const harcanan = fiyat && oturum ? maliyet(oturum) : null;
  let metin = !varMi ? "≈$0.00"
    : fiyat ? "≈" + para(harcanan)
    : kisaTok((oturum.girdi || 0) + (oturum.cikti || 0)) + " tok";
  // Sınır varken çip iki sayıyı birden taşıyor: oturumda ne harcandı ve
  // tavan ne. "Ne kadar kaldı" sorusu kutuyu açmadan cevaplansın.
  if (butce) metin += " · " + para(harcanan == null ? 0 : harcanan) + "/" + para(butce);
  chip.textContent = metin;
  chip.classList.toggle("over", !!(butce && harcanan != null && harcanan >= butce));
  chip.title = t("Bu oturumun tahmini toplam harcaması — tıkla: kırılım")
    + (tur && (tur.girdi || tur.cikti) && fiyat
      ? t(" · bu tur: ") + "≈" + para(maliyet(tur)) : "")
    + (butce ? t(" · oturum sınırı: ") + para(butce) : "")
    + (premiumMu() ? t(" · premium model (çıktı > $20/M)") : "");
}

// Kırılım kutusu: oturum toplamı + girdi/çıktı × fiyat.
$("dock-cost").addEventListener("click", () => {
  const pop = dockPop($("dock-cost"));
  if (!pop) return;
  pop.append(mk("div", "pop-head", t("Tahmini harcama")));
  const tr = (n) => (n || 0).toLocaleString("tr-TR");
  const satir = (metin) => pop.append(mk("div", "pop-note", metin));
  const tur = kullanim.tur, oturum = kullanim.oturum;
  if (!oturum || !oturum.cagri) {
    satir(t("Bu oturumda henüz tur yok."));
  } else if (fiyat) {
    if (premiumMu()) satir(t("Premium model: çıktı fiyatı $20/M üstünde."));
    satir(t("Bu tur: ") + "≈" + para(tur ? maliyet(tur) : 0)
      + " · " + t("oturum: ") + "≈" + para(maliyet(oturum)));
    satir(t("Girdi: ") + tr(oturum.girdi) + t(" token") + " × $"
      + (fiyat.girdi * 1e6).toFixed(2) + "/M = " + para(oturum.girdi * fiyat.girdi));
    satir(t("Çıktı: ") + tr(oturum.cikti) + t(" token") + " × $"
      + (fiyat.cikti * 1e6).toFixed(2) + "/M = " + para(oturum.cikti * fiyat.cikti));
    satir(t("Tahmin — önbellek indirimi hesaba katılmaz."));
  } else {
    satir(t("Fiyat bilinmiyor — yalnız token sayısı."));
    satir(t("Girdi: ") + tr(oturum.girdi) + t(" token")
      + " · " + t("Çıktı: ") + tr(oturum.cikti) + t(" token"));
  }
  pop.append(butceAlani());
  placePop($("dock-cost"));
});

// Bütçe freni: harcamanın YANINDA duruyor, ayar sayfasında değil. Sınır bu
// oturuma ait — yarın açılan konuşma dün konan sınırla sessizce durmamalı.
// Boş bırakmak sınırsız demek. Fiyat bilinmiyorsa fren çalışamıyor ve bunu
// saklamak yerine söylüyoruz.
function butceAlani() {
  const kutu = mk("div", "pop-butce");
  kutu.append(mk("div", "pop-head", t("Bu oturum için üst sınır")));
  const satir = mk("div", "pop-butce-row");
  const dolar = mk("span", "pop-butce-dolar", "$");
  const alan = mk("input", "pop-butce-input");
  alan.type = "text";
  alan.inputMode = "decimal";
  alan.placeholder = t("sınırsız");
  alan.value = butce ? String(butce) : "";
  const kaydet = mk("button", "pop-butce-ok", t("Uygula"));
  kaydet.type = "button";
  const not = mk("div", "pop-note", fiyat
    ? t("Sınıra ulaşılınca koşan tur durur; yükseltince kaldığı yerden sürer.")
    : t("Fiyat bilinmiyor (yerel sunucu ya da katalog dışı model) — fren çalışmaz."));

  const uygula = async () => {
    const ham = alan.value.trim().replace(",", ".");
    const cevap = await post("/api/butce", { usd: ham === "" ? null : ham });
    if (!cevap || cevap.ok === false) {
      not.textContent = (cevap && cevap.error) || t("Sınır kaydedilemedi.");
      return;
    }
    butce = cevap.butce == null ? null : Number(cevap.butce);
    dockCost();
    hidePop();
  };
  kaydet.addEventListener("click", uygula);
  alan.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); uygula(); }
  });
  satir.append(dolar, alan, kaydet);
  kutu.append(satir, not);
  return kutu;
}

// Beni tanı çipi: eğitim arka planda koşarken dock'ta sessiz bir işaret.
// Bitince beş saniye "tamamlandı" deyip kayboluyor — kalıcı bir rozet değil.
let tanimaTimer = null;
function tanimaChip(state) {
  const chip = $("dock-tanima");
  if (!chip) return;
  clearTimeout(tanimaTimer);
  if (state === "basladi") {
    chip.textContent = "· " + t("Tanıma eğitimi arka planda");
    chip.hidden = false;
  } else if (state === "bitti") {
    chip.textContent = "· " + t("Tanıma eğitimi tamamlandı");
    chip.hidden = false;
    tanimaTimer = setTimeout(() => { chip.hidden = true; }, 5000);
  }
}

// --- dock açılır kutuları -----------------------------------------------
//
// Çipe tıklamak sırayla döndürmüyor, seçtiriyor: çipin üstünde küçük bir
// kutu açılıyor (Claude Code'un model/kip kutuları gibi). Döndürme beş
// değerde dört tıklama demekti; kutu tek tıklamada istenen değere gidiyor
// ve her seçeneğin ne olduğunu söylüyor.

let popFor = null;      // hangi çip için açık
let lastUsage = null;   // bağlam detayı için son `usage` olayı

function mk(tag, cls, textContent) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (textContent !== undefined) node.textContent = textContent;
  return node;
}

// Kutuyu açar ve boş halini döndürür; aynı çipe ikinci tıklama kapatır
// (null döner). İçerik eklendikten sonra `placePop` ile yerleştirilir —
// genişlik ancak içerik girince belli oluyor.
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
  // Çipin üstüne, sol kenarına hizalı; sağ kenardan taşarsa içeri çekilir.
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

// Derinlik: her seviyenin ne pahasına geldiği yanında yazıyor.
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

// Yetki kipleri: ayar sayfasındaki tanımların aynısı (settings.PERMISSION_MODES).
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

// Model: sağlayıcının kataloğu aranabilir bir listede. Katalog yoksa
// (yerel sunucu kapalı, liste vermiyor) ayar sayfasına giden yol duruyor.
$("dock-model").addEventListener("click", () => {
  const pop = dockPop($("dock-model"));
  if (!pop) return;
  pop.append(mk("div", "pop-head", "Model"));
  const note = mk("div", "pop-note", t("Katalog soruluyor…"));
  pop.append(note);
  placePop($("dock-model"));
  fillModelPop(pop, note);
});

// Oto kipinin arayüz notu. YALNIZ OpenRouter + "oto" seçiliyken görünür;
// başka sağlayıcı/modelde bu uyarının işi yok.
const OTO_NOTU =
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
  } catch { /* aşağıda ele alınıyor */ }
  if (popFor !== $("dock-model")) return;   // kutu bu arada kapandı

  // Oto seçiliyken kutunun başında ne anlama geldiği yazıyor.
  if (provider === "openrouter" && modelName === "oto") {
    pop.insertBefore(mk("div", "pop-note", t(OTO_NOTU)), note);
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

  // Seçim bu sohbet için: her konuşma kendi modelini taşıyabilir, yeni
  // sohbet son sohbetin seçimini devralır. Küresel varsayılan ayarlarda.
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
      if (++shown > 60) break;   // 400+ modelde DOM'u boğma; arama daraltır
      list.append(popRow(item.id, "", item.id === modelName, async () => {
        const was = modelName;
        modelName = item.id;
        showMeta(); dockRender();
        // Sohbete yazılır (meta) ve sunucu aktif oturuma ANINDA uygular;
        // oturum kimliği yoksa (eski akış) küresel ayara düşer.
        const answer = oturumId
          ? await post("/api/session/meta", { id: oturumId, model: item.id })
          : await post("/api/settings", { model: { name: item.id } });
        if (answer && answer.ok === false) { modelName = was; showMeta(); dockRender(); }
      }));
    }
    if (!shown) list.append(mk("div", "pop-note", t("Eşleşen yok.")));
    if (oturumId && !search.value.trim()) {
      list.append(popRow(t("↺ Küresel varsayılana dön"), "", false, async () => {
        await post("/api/session/meta", { id: oturumId, model: "" });
        loadState();   // gerçek model sunucudan gelsin
      }));
    }
  };
  search.addEventListener("input", paint);
  paint();
  placePop($("dock-model"));
  search.focus();
}

// Bağlam çipi: Cursor'un Context Usage kutusunun aynı düzeni —
// başlık + kapat, yüzde/toplam, hap çubuk, kalem kalem liste.
$("dock-ctx").addEventListener("click", () => {
  const pop = dockPop($("dock-ctx"));
  if (!pop) return;
  pop.classList.add("pop-ctx");
  const head = mk("div", "pop-ctx-head");
  head.append(mk("span", null, t("Bağlam doluluğu")));
  const kapat = mk("button", "pop-ctx-kapat", "×");
  kapat.type = "button";
  kapat.setAttribute("aria-label", t("Kapat"));
  kapat.addEventListener("click", (ev) => { ev.stopPropagation(); hidePop(); });
  head.append(kapat);
  pop.append(head);
  const window_ = contextWindow;
  const kirilim = lastKirilim || [];
  const used = ctxUsed(lastUsage ? lastUsage.prompt_total : 0, kirilim);
  const pct = window_ && used ? Math.min(100, Math.round(used / window_ * 100)) : 0;
  const ozet = mk("div", "pop-ctx-sum");
  ozet.append(mk("b", null, pct + "%" + t(" dolu")));
  ozet.append(mk("span", null, "~" + ctxKisa(used) + " / " + ctxKisa(window_) + t(" token")));
  pop.append(ozet);
  const bar = mk("div", "pop-bar pop-bar-seg");
  paintCtxBar(bar, kirilim, window_, used);
  pop.append(bar);
  for (const p of kirilim) {
    const row = mk("div", "pop-ctx-row");
    row.append(mk("i", "ctx-dot " + (p.id || "")));
    row.append(mk("span", "pop-ctx-ad", t(p.ad)));
    row.append(mk("b", "pop-ctx-n", ctxKisa(p.n)));
    pop.append(row);
  }
  placePop($("dock-ctx"));
});

// --- onay -------------------------------------------------------------
// Araç adı ve ham JSON "neye izin veriyorum" sorusuna cevap vermiyor.
// Her araç için ne yapacağını düz Türkçe söyleyen bir cümle üretiyoruz.
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
    // "hep izin ver": ayni arac ve ayni hedef icin bir daha sorulmasin.
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
  // İsteyen bir yardımcıysa kullanıcı bunu görmeli: kime izin veriyor.
  if (e.channel && e.channel.title) label += "  [" + t("yardımcı") + ": " + e.channel.title + "]";
  tag.textContent = label;
  tag.className = "tag" + (e.mutates ? " mutates" : "");

  // Ham argümanlar yalnızca özet yetmediğinde.
  const keys = Object.keys(args).filter(k => args[k] !== undefined);
  const box = $("approve-args");
  box.textContent = JSON.stringify(args, null, 2);
  box.hidden = keys.length <= 1 && !!target;

  overlay.hidden = false;
}

// --- kaçırılan zamanlanmış görevler (açılış sorusu) --------------------

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
    const ad = task.title || task.id || "?";
    const tarif = task.describe || "";
    li.textContent = tarif ? ad + " — " + tarif : ad;
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
  } catch { /* sunucu yok */ }
  if (window.JobsPanel) JobsPanel.load();
}

$("missed-run")?.addEventListener("click", () => resolveMissed("run"));
$("missed-skip")?.addEventListener("click", () => resolveMissed("skip"));

// --- iş şeridi --------------------------------------------------------
//
// Bir turda olan biten tek bir satırda toplanıyor: düşünme, araç çağrıları
// ve ara anlatım. Önceki hal her düşünme ve her araç için ayrı bir satır
// bırakıyordu; dört adımlık bir işte sohbet on beş satırlık bir merdivene
// dönüyor ve asıl okunacak şey olan cevap aralarda kayboluyordu.
//
// Ayrıntı kayboluyor değil, katlanıyor: başlığa tıklayınca hepsi açılıyor.

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
    // Boş gövdeyi açmak "hiçbir şey olmadı" gibi görünüyordu (adımsız,
    // düşüncesiz turda başlığa tıklamak ölü kalıyordu) — gövdede içerik
    // yoksa tıklama sessizce yok sayılır, imleç de bunu söyler (CSS).
    if (!body.childElementCount) return;
    body.hidden = !body.hidden;
    head.classList.toggle("open", !body.hidden);
    // Kullanıcı şeridi okumak için tıkladı: açılan GÖVDE görünür alana
    // gelsin — yalnız başlığı hizalamak, ekranın altındaki gövdeyi görüş
    // dışında bırakıyordu ("açılmıyor, arkada kalıyor" — canlı şikâyet).
    if (!body.hidden) {
      // TEK tıklama içeriğe iner: gövde yalnız düşünce satırlarından
      // oluşuyorsa aradaki katlı "✻ Düşündü · N sn" basamağı atlanır ve
      // muhakeme doğrudan açılır. Eski hal iki katmandı — kullanıcı
      // "tıklayınca sadece alta bir çizgi geliyor, içeriğine
      // gidemiyorum" diye defalarca yandı (31.08).
      const cocuklar = [...body.children];
      const sadeceDusunce = cocuklar.length > 0
        && cocuklar.every((c) => c.classList.contains("think"));
      if (sadeceDusunce) {
        const son = cocuklar[cocuklar.length - 1];
        if (son.classList.contains("done") && !son.classList.contains("open")) {
          son.click();
        } else if (!son.classList.contains("done") && !son.classList.contains("open")) {
          // Canlı "Düşünüyor": gövdeyi açmak yetmez — kutuyu da aç.
          son.classList.add("open");
          if (thought) {
            son.textContent = thought.trim();
            son.scrollTop = 0;
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
  head.classList.add("busy");   // çalışıyor: başlık nabız atıyor
  work = { head, body, steps: 0, since: Date.now(), thought: null, open: new Map(),
           gone: null, trimmed: 0,
           // Bu turun BÜTÜN muhakemesi — satır açmayanlar dahil. Hiçbir
           // şey silinmiyor: eşik yalnızca satır açma kuralı.
           thinkAll: [] };
  return work;
}

// Şerit akışla birlikte ilerler (Claude Code düzeni): canlı gösterge her
// zaman yeni içeriğin HEMEN üstünde durur, turun tepesine çakılı kalmaz.
// Şeridin altına başka bir üst-düzey blok girdiyse (araya giren mesaj,
// artifact kartı) şerit akışın sonuna taşınır — DOM düğümleri aynı,
// içindeki adımlar ve katlanmış düşünceler olduğu gibi birlikte gelir.
function dockWork(w) {
  if (!w || !w.body) return;
  if (w.body.nextElementSibling || w.head.nextElementSibling !== w.body) {
    thread.append(w.head, w.body);
  }
}

// Cevap akmaya başladı: şerit sakinleşir. Nabız durur, başlık o ana kadarki
// işin özetine döner ve şerit akışın sonuna iner ki yeni metin hemen altında
// yazılsın. Tur sürerken model yine düşünür ya da araç çağırırsa think/actLine
// başlığı tekrar canlandırır.
function restWork() {
  if (!work) return;
  dockWork(work);
  if (!work.open.size) {
    // Tur hâlâ sürüyorsa nabzı söndürme: araçlar arası boşlukta
    // "kapandı / açıldı" hissi buradan geliyordu.
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

// Şeridin canlı başlığı: o anki eylem + hedefi + kaçıncı adım. Kullanıcı
// şeridi açmadan da "şu an ne oluyor / kaç adım oldu"yu okuyabilsin —
// eski başlık yalnız fiili söylüyordu ("Çalıştırıyor…") ve uzun bir turda
// hangi dosyada, kaçıncı adımda olunduğu ancak şerit açılınca görünüyordu.
const HEAD_ARG = 72;

// Şerit başlığı iki CİNS parça taşıyor ve ikisi aynı tipografiyle
// çizilemez:
//
//   * ANLATIM — fiil ve sayaçlar ("Koşturuyor", "15 adım", "18 sn").
//   * HEDEF — komut ya da dosya yolu. Bu KOD: büyük harfe çevrilmez.
//
// Yapı flex satır: [fiil] [hedef…] [meta] — dar sütunda kırılma yok;
// hedef ellipsis, meta sağda sabit.

// Hedefi kod gibi göstermesi gereken araçlar: komut ve dosya yolu.
const KOD_HEDEFLI = new Set([
  "shell", "bash", "powershell", "read_file", "read_many", "write_file", "edit_file",
  "list_dir", "grep", "search_files", "checkpoint", "git",
]);

// Kabuk sarmalayıcıları: kullanıcının ilgilendiği şey bunların İÇİ.
// "powershell -NoProfile -Command "netstat -ano"" satırında okunmaya değer
// olan `netstat -ano`; sarmalayıcı her komutta aynı ve yer kaplıyor.
const SARMALAYICILAR =
  /^\s*(?:(?:pwsh|powershell(?:\.exe)?|cmd(?:\.exe)?|bash|sh|zsh)\b(?:\s+-[\w-]+)*\s*(?:-Command|-c|\/c)\s*)/i;

function komutOzeti(text) {
  let s = String(text || "").trim();
  const ic = s.replace(SARMALAYICILAR, "");
  if (ic !== s) {
    s = ic.trim();
    // Sarmalayıcı komutu tırnağa alır; tırnaklar sarmalayıcıya aitti.
    if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'")))
      s = s.slice(1, -1).trim();
  }
  // Çok satırlı komutta ilk anlamlı satır: gerisi adım kartında duruyor.
  const ilk = s.split("\n").map((r) => r.trim()).find(Boolean) || "";
  return ilk.length > HEAD_ARG ? ilk.slice(0, HEAD_ARG).trimEnd() + "…" : ilk;
}

// Canlı satırın başlık parçaları. Yoksa null — çağıran kendi yedeğini yazar.
//
// Cursor dili: tek araç fiili yerine turun özeti ("4 dosya okuyor, 7 arama"
// / "Exploring 4 files, 7 searches"). Açık bir adım varsa hedef chip olarak
// durur; şerit açılmadan da ne tarandığı okunur.
function liveHead() {
  if (!work) return null;
  const phrase = activityPhrase(work);
  const row = work.open.size ? [...work.open.values()][0] : null;
  if (!phrase && !row) return null;
  let target = "";
  let kod = false;
  if (row) {
    const what = row.querySelector(".what").textContent;
    kod = row.dataset.kod === "1";
    target = kod ? komutOzeti(what)
      : (what.length > HEAD_ARG ? what.slice(0, HEAD_ARG) + "…" : what);
  }
  return {
    verb: phrase || (row && row.querySelector(".who").textContent) || mull(),
    target, kod,
    tail: "",
  };
}

// Canlı başlığı çizer. Çizecek canlı satır yoksa false — çağıran yedeğini
// yazsın (eski `workHead(liveHead() || …)` kalıbının yerini tutuyor).
function paintLive(extra) {
  const live = liveHead();
  if (!live) return false;
  workHead(live.verb, live.target, (live.tail || "") + (extra || ""), live.kod);
  paintThinkLine();
  return true;
}

// Turun araç dökümü: Cursor'un "Exploring 4 files, 7 searches" satırı.
// Fiil tek adıma kilitlenmesin diye sayılır; şerit kapalıyken de okunur.
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
  const en = Dil.mode === "en";
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

// Cevap yazılmıyorken ikinci satır: "Düşünüyor" — Cursor'daki Thinking.
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

// DOM freni: yüzlerce adımlı bir turda şerit gövdesi sınırsız büyümesin.
// Eskiler tek özet satıra iner — adım kaybolmuyor, sayısı yazıyor; şerit
// açıldığında tarayıcı binlerce düğüm taşımak zorunda kalmıyor.
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
    if ([...w.open.values()].includes(first)) break;   // koşan satıra dokunma
    if (first.querySelector && first.querySelector(".who")) w.trimmed += 1;
    first.remove();
  }
  w.gone.textContent = Dil.mode === "en"
    ? "… first " + w.trimmed + " steps folded"
    : "… ilk " + w.trimmed + " adım katlandı";
}

// Başlık her adımda tazeleniyor: çalışırken o an ne yapıldığı, bitince
// kaç adım sürdüğü.
//
// DOM'u her saniye yeniden kurmak (replaceChildren) komut chip'inin
// kaybolup gelmesine yol açıyordu — kullanıcı "CLI açılıp kapanıyor"
// sanıyordu. Üç çocuk sabit; yalnız metin/sınıf güncellenir.
function workHead(label, target, tail, kod) {
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
      box = document.createElement(kod ? "code" : "span");
      box.className = kod ? "head-target kod" : "head-target";
      verb.after(box);
    } else {
      const want = kod ? "CODE" : "SPAN";
      if (box.tagName !== want) {
        const next = document.createElement(kod ? "code" : "span");
        next.className = kod ? "head-target kod" : "head-target";
        box.replaceWith(next);
        box = next;
      } else {
        box.className = kod ? "head-target kod" : "head-target";
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

// "N adım" özeti. Test ham kaynağı grepliyor (steps + " adım") — birim
// ifadesi burada duruyor, İngilizce karşılığı da buradan çıkıyor.
const stepsWord = (steps) => Dil.mode === "en" ? steps + " steps" : steps + " adım";

// Turun bütün düşünmesi eşiğin altında kaldıysa şeritte tek bir düşünme
// satırı bile yoktur — ve o zaman arşive girecek kapı da kalmaz. Hiçbir
// şey KAYBOLMAMALI: tur kapanırken tek bir toplu satır ekleniyor.
// Adım başına değil TUR başına bir satır: gürültü değil, kapı.
function sealThinkArchive(w) {
  if (!w.thinkAll.length) return;
  if (w.body.querySelector(".think")) return;   // zaten açık bir kapı var
  const row = document.createElement("div");
  row.className = "act note think done";
  const kez = w.thinkAll.length;
  const label = t("✻ Düşündü") + " · " + kez + t(" kez");
  row.textContent = label;
  row.title = t("Tıkla — bu turun muhakemesini gör");
  const arsiv = w.thinkAll;
  let open = false;
  row.onclick = (ev) => {
    ev.stopPropagation();
    open = !open;
    row.textContent = open ? arsiv.join("\n\n———\n\n") : label;
    row.classList.toggle("open", open);
    if (open) {
      row.scrollTop = 0;
      row.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  };
  w.body.append(row);
}

// Anlatım başlarken şerit bölünür: biten küme kendi tıklanır özetine
// iner ("3 adım · 12 sn" / "2 dosya okuyor, 1 komut"), yeni araçlar
// metnin ALTINDA taze bir küme açar. Böylece uzun bir koşu Claude
// Code'daki gibi "metin / araç kümesi / metin" ritmiyle okunur ve her
// kümenin detayı kendi satırından açılır.
function segmentWork() {
  if (!work) return;
  // Koşan araç ya da bekleme varken bölünmez — canlı satır tek gerçek.
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
  // Tur beklerken kapandıysa (kesme) bekleme satırı da mühürlenir.
  if (waitState) closeWait(null);
  // setBusy'nin erken açtığı boş şerit: kullanıcı mesajı gelmeden
  // mühürlenirse "Düşündü ✓" hayalet satırı bırakma — sessizce kaldır.
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
  work.head.classList.remove("busy", "wait");   // nabız durur
  work.head.classList.add("done");       // bitti: ✓
  paintThinkLine();
  // Tur bitti: gövde özete katlanır — kullanıcı tur içinde açmış olsa
  // bile. Bitmiş turun adım seli sohbette açık kalınca asıl okunacak şey
  // (cevap) yine kayboluyordu; merak eden başlığa tıklayıp geri açıyor.
  work.body.hidden = true;
  work.head.classList.remove("open");
  work = null;
}

// MODEL METNİ HER ZAMAN GÖRÜNÜR.
//
// Ayrım "tur ortası mı, tur sonu mu" DEĞİL — "kim yazdı":
//
//   model  → sohbette normal cevap bloğu (iki araç çağrısının arasında
//            yazılmış olsa bile: kullanıcıya hitap eden her cümle)
//   harness→ şeritte ya da gizli (araç adımları, hatırlama izi, hedef
//            senkronu, sürdürme dürtüsü, iş durumu)
//   model'in kendi kendine düşünmesi → şeritte katlı ("✻ Düşündü")
//
// Eski hal araçtan ÖNCE gelen her metni şeride katlıyordu ve `sealLine`da
// bir "güvenlik ağı" ile geri getirmeye çalışıyordu. Kullanıcı "yarım mı
// kaldı?" diye sorduğunda neo cevabı yazdı, cevap şeridin içine katlandı
// ve ekranda yalnızca "▸ HARMANLIYOR · 13 SN" kaldı — kullanıcı sorduğu
// sorunun cevabını görmek için şeridi açmak zorunda kaldı. Yama kalktı,
// kaynak düzeldi: metin geldiği yerde, normal blok olarak duruyor.
//
// Bu yüzden burada yapılan tek şey akan bloğu MÜHÜRLEMEK: blok sohbette
// kalır, sıradaki adım şeridi onun ALTINA taşır (dockWork).
function foldNarration() {
  finishAgentLine();
}

function actLine(e) {
  const w = ensureWork();
  foldNarration();
  // Şerit akışı takip eder: araya başka bir blok girdiyse (artifact kartı,
  // araya giren mesaj) canlı satır onun altında, akışın ucunda doğar.
  dockWork(w);
  w.head.classList.add("busy");
  // Önceki düşünme bloğu tek satıra katlansın ve sıradaki blok kendi
  // satırını alsın. (Eskiden yalnızca null'lanıyordu ve tam metin şeritte
  // tam boy kalıyordu.)
  closeThought();
  w.steps += 1;

  const row = document.createElement("div");
  // `run`: satır hâlâ çalışıyor. Bitince kalkıyor — çalışan satır parlak,
  // biten soluk; şeride bakan göz nerede olunduğunu renkten okuyor.
  row.className = "act run";
  const spark = document.createElement("span"); spark.className = "spark";
  // Simge tür eşlemesinden, ad niyet fiilinden: "shell" değil "Çalıştırıyor".
  // Ham araç adı kayıp değil — satırın üstünde duruyor (title).
  spark.textContent = TOOL_ICON[e.tool] || "·";
  const verb = verbFor(e.tool);
  const who = document.createElement("span"); who.className = "who"; who.textContent = verb;
  who.title = e.tool;
  const what = document.createElement("span"); what.className = "what";
  what.textContent = summarize(e.input);
  what.title = t("Tıkla — adımın ayrıntısını gör");
  // Hedefi KOD olan adımlar (komut, dosya yolu) işaretleniyor: şerit
  // başlığı onu büyük harfe çevirmeden, mono ve olduğu gibi çizsin.
  // Kırpma yalnız GÖRÜNTÜDE — tam komut adım kartında duruyor (row._card).
  if (KOD_HEDEFLI.has(e.tool)) { row.dataset.kod = "1"; what.classList.add("kod"); }
  const took = document.createElement("span"); took.className = "took";
  row.append(spark, who, what, took);

  w.body.append(row);
  row._start = Date.now();   // canlı süre için: ticker bunu saniyede bir günceller
  // Zengin kart için ham veri satırda taşınıyor; çizim tembel — kart ancak
  // satıra tıklanınca kuruluyor (aşağıda toggleCard).
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

    // Dosya değişikliği: Cursor gibi satırın altında net iz + diff kartı.
    const tool = row._card && row._card.tool;
    if (tool === "edit_file" || tool === "write_file") {
      const trace = fileChangeTrace(row._card, e);
      if (trace) {
        const old = row.nextElementSibling;
        if (old && old.classList.contains("act-result")) old.remove();
        trace.onclick = () => toggleCard(row);
        row.after(trace);
      }
      if (!e.error) openCard(row);   // diff'i kendiliğinden göster
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
    // Açık kartı yerinde tazele (kapat-aç flicker yok).
    if (row._cardEl) refreshCard(row);
  }
  if (!paintLive()) {
    workHead(busy ? mull() : (activityPhrase(work) || stepsWord(work.steps)),
             "", since(work.since) + (busy ? streamNote() : ""));
    paintThinkLine();
  }
}

// edit/write sonrası: "+3 −1 · path" — tıklanınca diff / içerik.
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
  return line;
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
    // Basit: değişen satır sayısı (ortak prefix/suffix kırpılmadan üst sınır).
    del += o.length;
    add += n.length;
    // Ortak uçları çıkar — daha doğru +/- .
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

// --- model bekleme durumu ---------------------------------------------
//
// Kesinti sohbete hata duvarı BASMAZ (Claude Code davranışı): bekleme,
// çalışma şeridinin kendisinde yaşar. Şeridin canlı başlığı geri sayımlı
// duruma döner ("MODEL BEKLENİYOR · DENEME 4/5 · 118 SN" — nabız uyarı
// tonunda), hata ise adım listesinde TEK satırdır: her yeni denemede aynı
// satır güncellenir, tıklayınca sınırlı yükseklikte bir kod kartında ham
// ayrıntı açılır. Model dönünce aynı satır yeşile döner ("model geri
// geldi · N deneme sonrası") ve şerit normal akışını sürdürür.

let waitState = null;   // {kip, deneme, toplam, deadline, row, detail}

function waitHead() {
  if (!waitState) return "";
  const kalan = Math.max(0, Math.ceil((waitState.deadline - Date.now()) / 1000));
  const sn = kalan > 0 ? kalan + " sn" : t("yeniden deneniyor…");
  if (waitState.kip === "park")
    return t("İş bekletiliyor — model erişilebilir olunca sürecek") + " · " + sn;
  return t("Model bekleniyor") + " · " + t("deneme") + " "
       + waitState.deneme + "/" + waitState.toplam + " · " + sn;
}

// Geri sayım başlıkta işler: tickBusy her saniye burayı çağırır — üst üste
// yeni satır yığılmaz, AYNI başlık canlı kalır.
function paintWait() {
  if (waitState) workHead(waitHead());
}

function bekleme(e) {
  if (e.kip === "bitti" || e.kip === "iptal") { closeWait(e); return; }

  const w = ensureWork();
  foldNarration();
  dockWork(w);
  closeThought();
  w.head.classList.add("busy", "wait");

  if (!waitState) {
    // Kesinti bölümünün tek adım satırı: sonraki denemeler bunu günceller.
    const row = document.createElement("div");
    row.className = "act wait-adim";
    const spark = document.createElement("span");
    spark.className = "spark"; spark.textContent = "⏳";
    const who = document.createElement("span");
    who.className = "who"; who.textContent = t("Model çağrısı");
    const what = document.createElement("span"); what.className = "what";
    const took = document.createElement("span"); took.className = "took";
    row.append(spark, who, what, took);

    // Ham hata: varsayılan GİZLİ; tık ile açılan, sınırlı yükseklikte ve
    // kendi içinde kayan kod kartı — diğer adım kartlarıyla aynı jest.
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

  waitState.kip = e.kip;
  waitState.deneme = e.deneme || 0;
  waitState.toplam = e.toplam || 0;
  waitState.deadline = Date.now() + (e.saniye || 0) * 1000;

  const kisa = String(e.detay || "").split("\n")[0];
  waitState.row.querySelector(".what").textContent =
    kisa.length > HEAD_ARG ? kisa.slice(0, HEAD_ARG) + "…" : kisa;
  waitState.row.querySelector(".took").textContent = e.kip === "park"
    ? t("bekletiliyor")
    : t("deneme") + " " + waitState.deneme + "/" + waitState.toplam;
  waitState.detail.textContent = e.detay || "";
  // Sahne ve üst şerit de aynı gerçeği söylesin: donuk "Düşünüyor" değil,
  // bekleme durumu (Claude Code'un durum satırı gibi).
  setMode("thinking", e.kip === "park" ? t("İş bekletiliyor") : t("Model bekleniyor"));
  // "Model yükleniyor…" bekçisi bu durumda yanlış hikâye anlatır: akış yok
  // ama sebep belli — model BEKLENİYOR. Bekçi susturulur.
  waiting(false);
  paintWait();
}

// Bekleme bitti: "bitti" → satır yeşile döner ve şerit normale döner;
// "iptal" → satır söner. Her iki durumda başlıktaki uyarı tonu kalkar.
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
  // Tur sürüyorsa sahne/üst şerit normal düşünme akışına döner.
  if (busy) setMode("thinking");
}

// --- adım kartları ----------------------------------------------------
//
// Bir adımın satırı tek satırlık iz; tıklayınca gerçek işlem açılıyor:
// kabukta renklendirilmiş komut + çıktısı + çıkış rozeti, düzenlemede
// gerçek eski/yeni satırlarla diff, okuma/yazmada içerik önizlemesi,
// diğer araçlarda argüman tablosu. Çizim TEMBEL — kart ilk açılışta
// kurulur; katlıyken DOM'da yalnız tek satır var. Kart SINIRLI yükseklikte
// ve kendi içinde kayar: uzun bir çıktı sohbeti sayfalarca itmez
// ("detayı açıyorum, son şeyler görünmüyor" şikâyeti). Aç/kapa satırın
// altına ekleyip kaldırdığı için okunan yer kaymıyor.

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
  // Kart çoğu zaman ekranın altında doğuyor: görünür alana getir —
  // "tıkladım, hiçbir şey olmadı" hissinin köküydü.
  requestAnimationFrame(() => box.scrollIntoView({ block: "nearest", behavior: "smooth" }));
}

function refreshCard(row) {
  if (!row._card || !row._cardEl) return;
  const fresh = buildCard(row._card);
  row._cardEl.replaceWith(fresh);
  row._cardEl = fresh;
}

// Bu boyutun üstünde renklendirme yok: belirteçleme ana thread'de koşuyor
// ve dev bir çıktıda kartın açılmasını hissedilir biçimde geciktiriyor.
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

// Dosya uzantısından renklendirme dili; tanınmazsa düz metin kalır.
function extLang(path) {
  const name = String(path || "");
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : "";
}

// Diff: ortak baş/son kırpılıyor, değişen çekirdek az bağlamla çiziliyor.
// Satır numaraları gerçek: değişikliğin dosyadaki yerini sunucu söylüyor
// (edit_file sonucundaki `line`); yoksa 1'den sayılır.
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
      let cevap = null;
      if (typeof Degisiklik !== "undefined" && Degisiklik.kartUndoDosya) {
        cevap = await Degisiklik.kartUndoDosya(path);
      }
      if (!cevap || cevap.ok === false) {
        line("alert", (cevap && cevap.error) || t("Fark okunamadı."));
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

// Bilinmeyen araçlar için okunur argüman tablosu.
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
  // Kopyala: kartta duran şey TAM hâl (sarmalayıcısıyla birlikte komutun
  // kendisi, dosya içeriği ya da argümanlar). Şerit başlığındaki kırpma
  // yalnızca görüntüdedir; veri burada eksiksiz ve alınabilir olmalı.
  const kopya = el2("button", "card-copy", "⧉");
  kopya.type = "button";
  kopya.title = t("Kopyala");
  kopya.onclick = (ev) => {
    ev.stopPropagation();
    const metin = card.input.command || card.input.content
      || card.input.path || JSON.stringify(card.input, null, 2);
    navigator.clipboard.writeText(String(metin)).then(() => {
      kopya.textContent = "✓";
      setTimeout(() => { kopya.textContent = "⧉"; }, 1200);
    }).catch(() => { kopya.title = t("Kopyalanamadı"); });
  };
  head.append(kopya);

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
    // Okuma çıktısı zaten satır numaralı geliyor; olduğu gibi gösteriliyor.
    if (output) box.append(outBlock(output));
  } else {
    box.append(argsBlock(card.input));
    if (output) box.append(outBlock(output));
  }

  // Kartın içine tıklamak (metin seçmek) satırın aç/kapa'sını tetiklemesin.
  box.addEventListener("click", (ev) => ev.stopPropagation());
  return box;
}

// --- organlar ---------------------------------------------------------
//
// Ajanın aygıtları sahnede soluk duruyor: mikrofon, kameralar, hoparlör,
// kendine yazdığı modüller. Bir araç çağrıldığında hangisine dokunulduğu
// görünsün diye eşleme burada tutuluyor — hangi aracın hangi organı
// kullandığını sunucu söylüyor, burada varsayılmıyor.
let limbs = [];

async function loadOrgans() {
  try {
    const answer = await (await fetch("/api/organs")).json();
    limbs = answer.organs || [];
    Scene.organs(limbs);
  } catch { /* sunucu cevap vermiyorsa organ listesi de yok */ }
}

const organFor = (tool) =>
  (limbs.find((limb) => (limb.tools || []).includes(tool)) || {}).id || null;

// Araç satırındaki argüman özeti. SERT sınırlı: 40 KB'lık bir write_file
// içeriği DOM'a girmesin — satır zaten tek satır, gerisi gürültü.
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

// --- hedef paneli -------------------------------------------------------
//
// Zihindeki hedef yığınının görünür hali (Claude Code'un yapılacaklar
// listesi gibi): ajan mind_goals ile hedef açıp kapadıkça sohbetin sağ
// üstünde küçük bir kontrol listesi yaşıyor. Panel olay güdümlü — SSE'deki
// goal_push/goal_status olaylarıyla ilerliyor; sayfa yenilenince /api/state
// içindeki aktif hedeflerle tohumlanıyor. Hedef yokken panel hiç görünmez;
// biten madde önce üstü çizili durur, birkaç saniye sonra sessizce düşer.

const GOAL_SHOW = 6;        // açıkta duran madde sayısı; gerisi "…+N"
const GOAL_LINGER = 6000;   // biten/bırakılan madde bu kadar ms sonra düşer

// Dar pencerede panel kendiliğinden katlanır: sohbet sütunu zaten tüm
// genişliği kaplıyor ve açık bir liste metnin üstünde yer kaplıyor.
const GOAL_FOLD_WIDTH = 1020;   // CSS'teki dar-pencere eşiğiyle aynı

// Katlı/açık tercihi hatırlanıyor: her açılışta aynı kararı yeniden
// vermek zorunda kalmak yorucu.
const GOAL_FOLD_KEY = "neo.goals.folded";

// Panel ne olduğunu KENDİ anlatıyor. Kullanıcının sorusu buydu: "bu
// görevleri kim oluşturuyor bilmiyorum". Cevap ekranda dursun.
const GOAL_ACIKLAMA =
  "Neo'nun uzun işlerde kendi yazdığı adım listesi (Cursor görev listesi gibi). "
  + "Sohbet geçmişi değil — madde yoksa sekme de yok. Sen de ekleyip silebilirsin.";

const Goals = (() => {
  const items = new Map();   // id → { text, status, eski } — ekleniş sırasıyla
  // VARSAYILAN KATLI: panel tek satır doğuyor ("3 iş listesi"), merak eden
  // açıyor. Açık doğan panel, kullanıcının istemediği bir listeyi her
  // açılışta yüzüne dayıyordu.
  let folded = true;
  try {
    const kayit = localStorage.getItem(GOAL_FOLD_KEY);
    if (kayit !== null) folded = kayit === "1";
  } catch { /* gizli sekme / kapalı depolama: varsayılan katlı kalır */ }
  if (window.innerWidth <= GOAL_FOLD_WIDTH) folded = true;
  let clearArmed = false;    // "tümünü temizle" iki adımlı: ikinci tık uygular

  function rememberFold() {
    try { localStorage.setItem(GOAL_FOLD_KEY, folded ? "1" : "0"); }
    catch { /* depolama yoksa tercih bu oturumluk */ }
  }

  // Bir maddenin eylemi sunucuya: ajanın kullandığı defterin aynısı.
  function ask(action, id, text) {
    const yuk = { action };
    if (id) yuk.id = id;
    if (text) yuk.text = text;
    return fetch("/api/goals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(yuk),
    }).then((r) => r.json()).catch(() => ({ ok: false }));
  }

  // Madde eylemi: ✓ tamamlandı, × kaldır. Ekran hemen tepki veriyor
  // (iyimser), sunucu reddederse madde eski durumuna dönüyor.
  function act(id, action) {
    const got = items.get(id);
    if (!got) return;
    const onceki = got.status;
    got.status = action === "done" ? "done" : "dropped";
    render();
    ask(action, id).then((res) => {
      if (res && res.ok) { settle(id); return; }
      got.status = onceki;   // sunucu almadı: gerçeği geri koy
      render();
    });
  }

  // Viewer sekmesi (plan:goals): yüzen kart yok — terminal üstüne binmez.
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
    head.title = t("neo'nun kendine yazdığı iş listesi — tıkla: katla/aç");
    pane.append(head);
    const ne = document.createElement("p");
    ne.className = "goals-what";
    ne.textContent = t(GOAL_ACIKLAMA);
    pane.append(ne);
    if (!rows.length) {
      const blank = document.createElement("p");
      blank.className = "viewer-blank";
      blank.textContent = t("Aktif madde yok.");
      pane.append(blank);
    } else {
      let calisan = false;
      for (const [id, g] of rows.slice(0, 40)) {
        const row = document.createElement("div");
        const simdi = g.status === "active" && !calisan;
        if (simdi) calisan = true;
        row.className = "plan-step " + g.status + (simdi ? " now" : "");
        const mark = document.createElement("i");
        mark.textContent = g.status === "done" ? "✓"
          : g.status === "dropped" ? "×" : simdi ? "●" : "○";
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
      const temiz = document.createElement("button");
      temiz.type = "button";
      temiz.className = "goals-clear" + (clearArmed ? " armed" : "");
      temiz.textContent = clearArmed ? t("Emin misin?") : t("tümünü temizle");
      temiz.onclick = (ev) => {
        ev.stopPropagation();
        if (!clearArmed) { clearArmed = true; paint(host); return; }
        clearArmed = false;
        ask("clear").then((res) => { if (res && res.ok) items.clear(); render(); });
      };
      pane.append(temiz);
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
    $("goals-head").title = t("neo'nun kendine yazdığı adım listesi — tıkla: katla/aç");
    box.classList.toggle("folded", folded);
    const body = $("goals-body");
    body.hidden = folded;
    if (folded) return;
    body.textContent = "";

    const ne = document.createElement("p");
    ne.className = "goals-what";
    ne.textContent = t(GOAL_ACIKLAMA);
    body.append(ne);

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
        const rozet = document.createElement("span");
        rozet.className = "goal-eski";
        rozet.textContent = t("eski");
        rozet.title = t("Geçen oturumlardan kaldı");
        row.append(rozet);
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
    const alan = document.createElement("input");
    alan.type = "text";
    alan.placeholder = t("＋ kendi maddeni yaz");
    alan.setAttribute("aria-label", t("Yeni iş maddesi"));
    const gonder = () => {
      const metin = alan.value.trim();
      if (!metin) return;
      alan.value = "";
      ask("add", "", metin).then((res) => {
        if (res && res.ok && res.id) items.set(res.id, { text: metin, status: "active" });
        render();
      });
    };
    alan.onkeydown = (ev) => {
      ev.stopPropagation();
      if (ev.key === "Enter") { ev.preventDefault(); gonder(); }
    };
    alan.onclick = (ev) => ev.stopPropagation();
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "＋";
    btn.title = t("Ekle");
    btn.onclick = (ev) => { ev.stopPropagation(); gonder(); };
    wrap.append(alan, btn);
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

// --- artifact kartı -----------------------------------------------------
//
// Ajan kalıcı bir sayfa yayınladığında sohbete bir kart düşer: başlık,
// sürüm rozeti ve Aç. Kart sohbet satırı gibi akıp gitmez — aynı artifact
// güncellendiğinde YENİ kart basılmaz, mevcut kart bulunur ve rozeti
// tazelenir (v1 → v2). Tıklayınca sayfa uygulama içi görüntüleyicide,
// sunucudaki canlı adresinden (/artifact/<id>/) açılır.

function artifactAddress(e) {
  return e.address || "/artifact/" + e.id + "/";
}

function openArtifact(e) {
  Viewer.page(artifactAddress(e), e.title || e.id);
}

// Belge simgesi: köşesi kıvrık sayfa. İşaretleme dizesi kurup basmak yasak
// (model çıktısı asla işaretleme olarak yorumlanmasın — test_static bunu
// tutuyor); simge DOM API'siyle kuruluyor. apps.js'teki galeri de kullanıyor.
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

// Rozet animasyonunu yeniden tetikler: sınıfı kaldırıp bir kare sonra
// geri koymak, art arda güncellemelerde de yanıp sönmesini sağlıyor.
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
    // Güncelleme: kart yerinde kalır, başlık ve rozet tazelenir.
    found.querySelector(".art-title").textContent = e.title || e.id;
    const badge = found.querySelector(".art-badge");
    badge.textContent = "v" + (e.surum || 1) + " · " + t("güncellendi");
    badge.classList.add("fresh");
    found._art = e;
    reflash(found);
    // Sayfa o an görüntüleyicide açıksa yeni sürüm hemen görünsün.
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
  // Tam adres fareyle görünür, tıklayınca panoya gider — kart kırpıyor.
  addr.title = location.origin + artifactAddress(e);
  addr.style.cursor = "copy";
  addr.addEventListener("click", async (ev) => {
    ev.stopPropagation();
    try {
      await navigator.clipboard.writeText(location.origin + artifactAddress(card._art));
      note(t("Adres kopyalandı ✓"));
    } catch { /* pano izni yok */ }
  });
  meta.append(addr);
  main.append(meta);

  const badge = el2("span", "art-badge",
    "v" + (e.surum || 1) + " · " + t(e.surum > 1 ? "güncellendi" : "yayınlandı"));

  const open = el2("button", "art-open", t("Aç"));
  open.type = "button";
  open.setAttribute("aria-label", t("Aç") + " — " + (e.title || e.id));

  const dis = el2("button", "art-open art-export", t("Tarayıcıda aç"));
  dis.type = "button";
  dis.title = t("Gerçek tarayıcıda aç");
  const dl = el2("button", "art-open art-export", t("İndir"));
  dl.type = "button";
  dl.title = t("İndir") + " (.html)";
  const pr = el2("button", "art-open art-export", t("Yazdır / PDF"));
  pr.type = "button";

  card.append(glyph, main, badge, open, dis, dl, pr);

  const go = (ev) => { ev.stopPropagation(); openArtifact(card._art); };
  card.addEventListener("click", go);
  open.addEventListener("click", go);
  dis.addEventListener("click", (ev) => {
    ev.stopPropagation();
    // Gerçek port sunucuda: ajanın URL tahmini canlıda yanlış çıkıyordu.
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
  // Tur sürerken kartı hemen basma: model hâlâ metin yazıyor; kart üstte
  // kalıp altına "bir şeyler daha" düşüyordu. Tur bitince flush.
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
  // YALNIZ karar bekleyen kartlar sohbetin sonuna taşınır (plan-apply
  // teklifinin üstüne). Onaylanmış/bitmiş/iptal kart akışta doğduğu yerde
  // kalır — canlı şikâyet: iş bitmiş, cevap gelmiş, onaylanmış plan kartı
  // düğmeleriyle cevabın ALTINA yeniden düşüyordu ("ne alaka").
  const offer = planOffer;
  for (const card of [...thread.querySelectorAll(".plan-card")]) {
    if (!planBekliyor(card)) continue;
    if (offer && offer.parentNode === thread) thread.insertBefore(card, offer);
    else thread.append(card);
  }
}

function planBekliyor(card) {
  const durum = (card._plan && card._plan.status) || "bekliyor";
  return durum === "bekliyor";
}

function planKarariUygula(card) {
  // Karar verilmiş kartta karar düğmelerinin işi yok: Onayla/Düzenle/İptal
  // yalnız "bekliyor" durumunda görünür.
  const acts = card.querySelector(".plan-acts");
  if (acts) acts.style.display = planBekliyor(card) ? "" : "none";
}

function applyPlanData(card, e) {
  card._plan = e;
  const title = card.querySelector(".plan-title");
  const status = card.querySelector(".plan-status");
  if (title) title.textContent = e.title || e.id;
  if (status) status.textContent = e.status || "";
  if (!card.querySelector(".plan-edit")) renderPlanSteps(card, e);
  planKarariUygula(card);
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
  // "Otomasyon olarak kaydet" bilerek yok: tek seferlik bir proje planını
  // tekrarlanan otomasyona çevirmek anlamsızdı ve kullanıcıyı şaşırttı
  // ("bu projeyi neden sürekli yaptırayım?"). Otomasyon kurma yeri akış
  // editörü (Görevler) — plan kartı değil.
  acts.append(ok, edit, cancel);
  card.append(acts);
  thread.append(card);
  planKarariUygula(card);
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
  // Adım durumu görünür (canlı istek): ✓ bitti, ▸ yapılıyor, ○ bekliyor.
  // Ajan `plan` aracının step eylemiyle işaretledikçe kart canlı ilerler —
  // onaylanmış planda "hangi aşamadayız" buradan okunur.
  for (const s of e.steps || []) {
    const st = (s && s.status) || "bekliyor";
    const li = el2("li", "plan-step " + st);
    li.append(el2("span", "plan-tick",
                  st === "bitti" ? "✓" : st === "yapiliyor" ? "▸" : "○"));
    li.append(el2("span", null, s.text || s.title || String(s)));
    list.append(li);
  }
}

// --- plan kipi: onay döngüsü --------------------------------------------
//
// Plan kipinde tur bitince son cevabın altında "▶ Planı uygula" düğmesi
// belirir (Claude Code'un plan-onay döngüsü). Tıklanınca yetki kipi plana
// girmeden önceki kipe (bilinmiyorsa auto'ya) çevrilir ve "Planı uygula."
// mesajı kendiliğinden gönderilir. Kullanıcı kendisi yazarsa ya da kip
// plandan çıkarsa düğme sessizce kalkar — bayat bir teklif ekranda durmaz.

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
  // Önce kip: sunucu değişikliği reddederse mesaj hiç gitmemeli — plan
  // kipinde "Planı uygula." demek modeli yine salt okunur kapıya sürer.
  const answer = await post("/api/settings", { permissions: { mode: back } });
  if (answer && answer.ok === false) { setAuthority(was); return; }
  post("/api/chat", { text: t("Planı uygula.") });
  resumeFollow(false);
}

// --- olay akışı -------------------------------------------------------
function handle(e) {
  switch (e.type) {
    case "assistant_delta":
      lastDelta = "text";
      turnActivity = true;
      // Şerit kapanmıyor: model araç çağırıp yazıp yine araç çağırıyor ve
      // her seferinde yeni bir şerit açmak merdiveni geri getiriyordu.
      closeThought();
      // Tanimayi model yapiyor: onizlemenin etiketi cevabin ilk
      // cumlesinden geliyor, tarayicidan degil.
      if (Camera.on) Camera.say(firstClause(e.text));
      write(e.text);
      // Metin akarken sahne de yazıyor olmalı; her parçada yeniden
      // kurulan zamanlayıcı akış durunca kendiliğinden düşünmeye dönüyor.
      setMode("writing", undefined, 1200);
      // Cümle tamamlandıkça sesletiliyor: cevabın tamamını
      // beklemek konuşma değil anons olurdu.
      Speech.feed(e.text);
      break;

    // Düşünme kanalı ayrı: model akıl yürütürken henüz yazmıyor.
    case "thinking_delta": waiting(false); lastDelta = "thinking"; turnActivity = true;
      think(e.text); setMode("thinking", undefined, 2500); break;

    // Sırada bekleyen mesaj. Meşgulken gönderilen mesaj sessizce kaybolmuyor:
    // "sırada · N" rozetiyle görünüyor, sırası geldiğinde gerçek satıra
    // dönüşüyor. Kullanıcı ne yaptığını (kuyruğa girdiğini, kaçıncı olduğunu)
    // bir bakışta görüyor — "ne oldu buna" diye merak etmiyor.
    case "queued": {
      const row = line("user waiting", e.text);
      const badge = document.createElement("span");
      badge.className = "queue-badge";
      row.appendChild(badge);
      waitingLines.push({ text: e.text, row, badge });
      renumberQueue();
      break;
    }

    // Araya girme: meşgulken yazılan mesaj sıraya değil, KOŞAN turun içine
    // girdi (harness notu olarak). Balon normal kullanıcı mesajı gibi
    // çiziliyor + küçük bir "araya girdi" rozeti. Geçmişte user mesajı
    // olarak durmadığı için message-echo eşleşmesi yok; satır burada kalıcı.
    // Araya girme: meşgulken yazılan mesaj sıraya değil, KOŞAN turun içine
    // girdi (harness notu olarak). Balon + rozet; şerit hemen altına çekilir
    // ki "arka planda iş sürüyor / sen araya girdin" tek bakışta okunsun.
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
        // Şerit kapalıysa zorla açma — sadece konumu netleştir.
        revealAboveComposer(work.head);
      }
      break;
    }

    case "message":
      // İkinci savunma (`cizilir`): sunucu süzgeci bir gün kaçırırsa iç not
      // — harness dürtüsü — kullanıcı balonu olarak ÇİZİLMEZ. Sunucu
      // tarafında zaten `internal`/`continuation` işaretleriyle süzülüyor;
      // burası o süzgecin arkasındaki emniyet.
      if (e.role === "user" && cizilir(e.text)) {
        // Sırası geldi: bekleyen satır gerçek satırla değiştiriliyor.
        const at = waitingLines.findIndex((w) => w.text === e.text);
        if (at >= 0) { waitingLines[at].row.remove(); waitingLines.splice(at, 1); renumberQueue(); }
        // Yeni bir tur başlıyor: bekleyen "Planı uygula" teklifi bayatladı
        // (kullanıcı kendi sözünü söyledi ya da teklif zaten kullanıldı).
        hidePlanOffer();
        sealLine();
        resetStream();          // yeni tur: canlı token sayacı sıfırdan
        // Yeni tur: "bu turda ne değişti" şeridinin sınırı buradan başlıyor.
        chgTurnStart();
        const row = line("user", e.text);
        const media = pendingMedia.get(e.text);
        if (media) { attachMedia(row, media); pendingMedia.delete(e.text); scroll(); }
        // Busy status kullanıcı satırından ÖNCE geldiyse sealLine boş
        // şeridi silmiş olabilir — canlı satırı hemen yeniden aç.
        if (busy) kickWork();
      }
      else if (e.role === "system") note(e.text);
      break;

    case "tool_start": {
      turnActivity = true;
      if (e.tool === "hand" || e.tool === "screen") kontrolIsigi(+1);
      actLine(e);
      setMode("working", verbFor(e.tool) || t("Çalışıyor"));
      // Aygıt kullanılıyorsa sahnede o organ canlanıyor: soluk duran
      // kamera ya da modül, çekirdekten gelen bir uyarıyla yanıyor.
      const limb = organFor(e.tool);
      if (limb) Scene.use(limb, summarize(e.input));
      // Ajan bir dosyaya dokunduysa panel o dosyaya geçsin:
      // "yazdım" cümlesini okumakla dosyayı görmek aynı şey değil.
      if (typeof Viewer !== "undefined" && Viewer.feed) Viewer.feed(e);
      Viewer.watch(e.tool, e.input);
      break;
    }
    case "tool_end": {
      if (e.tool === "hand" || e.tool === "screen") kontrolIsigi(-1);
      closeAct(e);
      if (typeof Viewer !== "undefined" && Viewer.feed) Viewer.feed(e);
      Viewer.refresh(e.tool, e.path);
      if (typeof GitBar !== "undefined") GitBar.touched(e.tool);
      if (busy) setMode("thinking");
      const done = organFor(e.tool);
      // İz hemen silinmiyor: sahnede birkaç saniye daha duruyor ki neyin
      // kullanıldığı okunabilsin.
      if (done) setTimeout(() => Scene.release(done), 4000);
      break;
    }
    case "tool_cancelled": closeAct({ ...e, error: true, ms: 0 }); break;

    // Artifact yayınlandı ya da güncellendi: sohbete kalıcı bir kart düşer.
    // Aynı artifact'ın güncellemesi yeni kart basmaz — mevcut kartın
    // rozetini tazeler (sohbet kopya kartlarla dolmasın).
    case "artifact": artifactCard(e); break;
    case "plan": planCard(e); break;
    case "git":
      if (typeof GitBar !== "undefined") GitBar.refresh();
      break;
    case "session_title":
      // Model başlığı koydu: kenar listesi sayfa yenilemeden güncellensin.
      if (typeof History !== "undefined" && History.applyTitle)
        History.applyTitle(e.id, e.title);
      break;

    // Oturum değişti (yeni ya da devam): thread temizlenir; devam eden bir
    // konuşmaysa geçmiş dökümü yüklenir ki kullanıcı kaldığı yeri görsün.
    case "session_reset": {
      oturumId = e.id || "";
      thread.replaceChildren();
      waitingLines.length = 0;
      work = null; agentLine = null; raw = ""; waitState = null;
      planOffer = null;   // düğme thread ile birlikte gitti; referans kalmasın
      deferredPlans.clear();
      resumeFollow(false);   // yeni döküm: takip baştan açık
      // Sayaçlar sohbete özel: yeni konuşmada eski harcama asılı kalmasın;
      // sürdürülen sohbette loadState geçmiş toplamı yazar.
      kullanim = { tur: null, oturum: null };
      butce = null;
      dockCost();
      // Sürdürülen oturum: döküm kadar SAYAÇLAR da kaldığı yerden gelmeli.
      // Durum anlık görüntüsü bağlam çubuğunu ve harcama çipini oturum
      // günlüğünden tohumluyor — yoksa dolu bir konuşma "%0" / "$0" görünüyordu.
      if (e.resumed && e.id) { loadTranscript(e.id); loadState(); }
      else showWelcome();   // taze oturum: karşılama geri gelsin (boş ekran değil)
      // Rail kalıcı bir sütun: konuşma değişimi onu KAPATMAZ ("konuşmaya
      // tıklıyorum, sidebar gidiyor" — canlı şikâyet, ikinci kök buradaydı).
      // Geniş ekranda liste tazelenir ki "şu an açık" işareti taşınsın;
      // yalnız dar pencerede overlay kapanır.
      if (typeof History !== "undefined") {
        if (innerWidth <= 860) History.close(); else History.open();
      }
      // Oturum değişti: değişiklik defterinin sınırı da yeni oturumun
      // defterine göre kurulmalı — önceki konuşmanın kayıtları bu turun
      // özetine karışmasın.
      if (typeof Degisiklik !== "undefined") Degisiklik.tabanAl();
      // Klasör/git bağlamı sohbete özel: yeni konuşmada eski repo adı
      // (neocp / dal) composer üstünde asılı kalmasın.
      if (typeof GitBar !== "undefined") GitBar.refresh();
      break;
    }
    // "neo ile kes": neo konuşurken uyandırma sözüyle araya girildi —
    // TTS anında sussun ki kullanıcı dinlensin (turu kesmiyor, komut sıraya
    // giriyor).
    case "ack":
      Speech.ack();
      break;
    case "hush":
      Speech.stop();
      break;
    // İlk kurulum yönlendirmesi: model hiç çağrılmadı, sunucu yol
    // gösteriyor. Asistan satırı gibi çiziliyor (uyarı şeridi değil) —
    // kullanıcının sorusuna gelen cevap bu.
    case "setup_hint": {
      clearWelcome();
      const el = line("agent", t(e.text));
      el.classList.add("done");
      break;
    }
    case "notice": clearWelcome(); line("alert", e.text); break;
    // Model kesintisi: sohbete satır DÜŞMEZ — çalışma şeridinin canlı
    // başlığı duruma döner, ayrıntı şeritteki adım satırında yaşar.
    case "bekleme": bekleme(e); break;
    // Günlükteki api_error notu SOHBETE BASILMAZ: geçici hata çalışma
    // şeridindeki bekleme satırında yaşıyor (ham ayrıntı tık ile), ölümcül
    // hata ise zaten notice olarak geliyor. Eskiden bu olay ham JSON
    // duvarını sohbete döküyordu — "bilmeyen biri hata aldı sanır".
    case "api_error": break;
    case "refusal": clearWelcome(); line("alert", t("Model bu isteği reddetti.")); break;
    case "interrupted":
      clearWelcome();
      // Sesi de kes: metin durup hoparlörün cümleyi bitirmeye devam
      // etmesi, sözü kesilmiş ama konuşmayı sürdüren biri gibi.
      Speech.stop();
      // Akış yarıda kaldı: blok MÜHÜRLENİR. Eskiden mühürlenmiyordu ve
      // yarım kalan (çoğu zaman bomboş) "NEO ▮" bloğu ekranda sonsuza
      // kadar yanıp sönüyordu — kesilmiş bir turda hâlâ yazıyor gibi.
      sealLine();
      line("alert", t("Kesildi."));
      break;

    // Model hiçbir şey döndürmedi (yalnızca akıl yürütüp durdu). Döngü bir
    // sürdürme turu veriyor; arayüzde yapılacak tek şey açık kalmış boş
    // bloğu ve imlecini temizlemek — yoksa sürdürme turu boyunca ekranda
    // boş bir "NEO ▮" asılı kalıyor.
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

    // Orkestra: alt ajan kanalları (şef modu). Ana sohbete karışmıyorlar;
    // canlı olarak orkestra güvertesinde izleniyorlar.
    case "child_start": orchStart(e); tasksRefresh(); break;
    case "child_tool": orchTool(e);
      if (typeof Gorevler !== "undefined" && Gorevler.tazele) Gorevler.tazele();
      if (window.JobsPanel && JobsPanel.refreshLive) JobsPanel.refreshLive();
      break;
    // Biten kanal iki yere gidiyor: orkestra sahnesine (kart kapanır) ve
    // görevler defterine (satır güncellenir; arka plan işiyse sohbete
    // tıklanabilir bildirim düşer).
    case "child_end":
      orchEnd(e); tasksDone(e);
      if (window.JobsPanel) JobsPanel.load();
      // App/artifact teslimatı: zayıf 2 satır rapor yerine canlı ürün.
      if (e.ok && e.deliverable && e.deliverable.url && typeof Viewer !== "undefined") {
        const d = e.deliverable;
        if (d.kind === "app" || d.kind === "artifact") {
          Viewer.page(d.url, e.title || d.url);
        }
      }
      break;
    case "child_wait":
      if (typeof Gorevler !== "undefined" && Gorevler.tazele) Gorevler.tazele();
      if (typeof Orchestra !== "undefined" && Orchestra.wait) Orchestra.wait(e);
      if (window.JobsPanel && JobsPanel.refreshLive) JobsPanel.refreshLive();
      break;
    // Tepsiden Göster / Görevler: arka planda biten koşular görünsün.
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
    // Sunucu gerçek kanal listesini gönderdi (açılışta yetimler bulununca):
    // panel baştan kurulur — açılış sırasında yüklenen sayfa snapshot'ı
    // ajan hazır olmadan çekmiş olabilir.
    case "channels": orchSeed(e.channels || []); break;
    case "lane":
      // Paralel şerit durumu: kenar çubuğu rozetini canlı tutar.
      if (typeof History !== "undefined" && History.laneChanged)
        History.laneChanged(e);
      break;
    // Python tarafındaki kulağın duyduğu seviye: mikrofon simgesi
    // canlanıyor, yani arkada dinlendiği görünüyor.
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
      if (typeof Cameras !== "undefined" && Cameras.durum) Cameras.durum(e);
      break;
    case "turn_end":
      sealLine(); Speech.flush();
      // Plan kipinde biten tur bir plan bırakmıştır: uygulama teklifi.
      maybeOfferPlan();
      // Tur bitti: bu turda dosya değiştiyse tek satırlık özet düşsün.
      chgTurnEnd();
      // Arka planda koşan bir şey varsa rozet gerçeği söylesin.
      tasksRefresh();
      break;

    // Ajanin gercekten gezdigi yol: dugumler bu sirayla atesleniyor.
    case "recall_trace": {
      lastQuery = e.query || "";
      // Sahne yürüyüşün ne kadar süreceğini kendi biliyor; burada tahmin
      // edilen bir sayı, adım süresi her değiştiğinde yanlışa düşüyordu.
      const walk = Scene.activate(e.trace) || 0;
      setMode("recalling", undefined, walk + 400);
      break;
    }

    // Yazma da ağda bir hareket: çekirdekten yeni kayda giden bir uyarı.
    // Grafik önce tazeleniyor, yoksa hedef düğüm henüz orada değil.
    case "mind_write":
      Scene.load(() => Scene.deposit(e.memory_id));
      break;

    case "mind_forget":
      Scene.ripple(); Scene.load(); break;

    // Hedef yığını değişti: sahnede dalga + sağ üstteki kontrol listesi.
    case "goal_push":
      Goals.push(e.goal_id, e.text);
      Scene.ripple(); Scene.load(); break;
    case "goal_status":
      Goals.status(e.goal_id, e.status);
      Scene.ripple(); Scene.load(); break;

    // Yetki kipi arayüz dışından değişti (ayar sayfası, dış kapı): dock
    // çipi ve plan-onay düğmesi gerçeğe uysun.
    case "mode":
      if (e.mode && e.mode !== mode) setAuthority(e.mode);
      break;

    // Ajan iki kaydı bilinçli olarak bağladı: ağda yeni bir köprü kuruldu.
    // Grafı tazelemek yetmiyor — kurulan bağın görünmesi gerekiyor.
    case "mind_link":
      Scene.ripple();
      Scene.load(() => Scene.bridge(e.src, e.dst));
      note(t("Köprü: ") + (e.reason || t("bağlandı")));
      break;

    case "device_removed":
      loadOrgans();
      document.dispatchEvent(new CustomEvent("neo:devices"));
      break;

    // Beni tanı: kişisel ince ayar arka planda başladı/bitti (ya da ayar
    // sayfasından açıldı/kapandı). Sohbete satır düşürmeye değmez; kompozer
    // altındaki çip + üst bardaki ikon durumu sessizce gösteriyor.
    case "tanima": tanimaChip(e.state); tanimaIkon(e.state); break;

    case "usage":
      if (e.prompt_total) {
        tokenNote = e.prompt_total.toLocaleString("tr-TR") + t(" token")
          + (e.cache_read ? " · " + e.cache_read.toLocaleString("tr-TR") + t(" önbellek") : "");
        showMeta();
        dockContext(e.prompt_total, false, e.kirilim);
        lastUsage = e;
      }
      // Maliyet çipi: tur/oturum toplamları ve fiyat etiketi aynı olayda
      // geliyor (bkz. desktop._usage_yay sözleşmesi).
      if (e.tur) kullanim = { tur: e.tur, oturum: e.oturum || kullanim.oturum };
      if (e.fiyat !== undefined && e.fiyat !== null) fiyat = e.fiyat;
      dockCost();
      break;

    // Fiyat etiketi arka planda sonradan geldi: çip token sayısından
    // dolara döner — bir sonraki turu beklemeden.
    case "fiyat":
      fiyat = e.fiyat || null;
      dockCost();
      break;
  }
}

// Akış bağlantısı. Tek olması şart: `onerror` bir kopmada birden çok kez
// tetiklenebiliyor ve her biri yeni bir bağlantı açtırınca aynı olay iki üç
// kez işleniyordu. Metinde fark edilmiyor (aynı harf iki kez eklenince
// gözden kaçıyor) ama **ses iki kez çalıyor** — kopyalanan kuyruk.
let stream = null;
let retry = null;
// Bağlantı bir kez koptu mu? Kopup geri gelen akış, uygulamanın yeniden
// başladığı anlama gelebilir (gece kapandı, sabah açıldı): açık kalmış
// sekmenin orkestra güvertesi bayat "çalışıyor" kartlarıyla oturuyordu.
// Geri bağlanınca gerçek kanal listesi sunucudan tazeleniyor.
let dropped = false;

async function resyncChannels() {
  try {
    const s = await (await fetch("/api/state")).json();
    orchSeed(s.channels || []);
  } catch { /* sunucu henüz ayakta değil; bir sonraki bağlanışta */ }
}

function connect() {
  if (stream) { stream.close(); stream = null; }
  clearTimeout(retry);

  const source = new EventSource("/api/events");
  stream = source;
  // Hata ayıklama için erişilebilir olsun: açık SSE bağlantısı "ağ boşta"
  // bekleyen araçları süresiz bloke ediyor.
  window.__stream = source;

  source.onopen = () => {
    setBusy(busy);
    if (dropped) { dropped = false; resyncChannels(); }
  };
  source.onmessage = (msg) => {
    // Yerini yeni bir bağlantıya bırakmış eski bir akıştan gelen olay
    // yok sayılıyor.
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
    // Uyanma durumu önce: hazır değilse meşgul göstergesi yanlış hikâye
    // anlatıyor.
    setWaking(s.stage, s.ready);
    setBusy(!!s.busy);
    // Üst bardaki markanın ipucu: hangi sürüm, hangi düzen. Sahada iki
    // kopyanın hangisinin açık olduğu görünmüyordu — imleci markaya
    // getirince cevap burada.
    if (s.surum) {
      const marka = document.querySelector(".brand");
      if (marka) marka.title = "neo " + s.surum +
        (s.kurulu ? t(" · kurulum") : t(" · geliştirme"));
      // Küçük sürüm rozeti kenar çubuğunun dibinde (kullanıcı isteği,
      // 01.09): hangi sürümün kurulu olduğu aramadan görünsün.
      const rozet = document.getElementById("side-ver");
      if (rozet) rozet.textContent = "v" + s.surum;
    }
    modelName = s.model || "";
    oturumId = s.session || oturumId;
    showMeta();
    setVoice(!!s.voice);
    Speech.setCharacter(s.character);
    setListening(!!s.listen, !!s.wake, !!s.open);
    setMicDeaf(!!s.snoozed);
    paintHear(!!s.ear);
    if (s.mode) { previous = s.mode; setAuthority(s.mode); }
    // Aktif hedefler: panel olay akışını kaçırdıysa (yenileme) buradan
    // tohumlanıp kaldığı yerden sürüyor.
    Goals.seed(s.goals || []);
    // Orkestra kanalları da aynı sebepten: yenileme/yeniden açılış sonrası
    // panel gerçek listeyle kurulur — hayalet "çalışıyor" kartı kalmaz,
    // geçen oturumdan yarım kalan yardımcılar "yarım kaldı" olarak görünür.
    orchSeed(s.channels || []);
    dockEffort = s.effort || "";
    contextWindow = Number(s.context_window) || 0;
    dockRender();
    if (s.kirilim) lastKirilim = s.kirilim;
    // Süren oturumun son kullanımı: yenilenen sayfa kaldığı yerden başlasın.
    // Sabit kalemler (sistem + araç) ilk turdan önce de görünsün.
    if (Number(s.prompt_total) || (s.kirilim && s.kirilim.length)) {
      dockContext(Number(s.prompt_total) || 0, s.tahmin, s.kirilim);
      if (!lastUsage && Number(s.prompt_total)) {
        lastUsage = { prompt_total: Number(s.prompt_total), kirilim: s.kirilim };
      }
    }
    // Maliyet çipi de aynı sebepten buradan tohumlanıyor: yenileme
    // harcama göstergesini sıfırlamamalı.
    if (s.fiyat) fiyat = s.fiyat;
    if (s.kullanim && s.kullanim.oturum && s.kullanim.oturum.cagri) kullanim = s.kullanim;
    // Bütçe sınırı da tohumdan: yenilenen sayfa emniyet kemerini unutmasın.
    butce = s.butce == null ? null : Number(s.butce);
    dockCost();
    // Yenileme oturumu bitirmiyor: sayfa hangi sebeple yenilenirse yenilensin
    // (dil değişimi, F5) süren konuşmanın dökümü geri gelsin. Eskiden yenileme
    // sonrası ekran bomboş açılıyordu — oysa oturum sunucuda sürüyordu.
    // Döküm boşsa karşılama zaten yerinde duruyor: loadTranscript boş dökümde
    // thread'e dokunmuyor, ilk satır çizilirken karşılama kendiliğinden kalkıyor.
    if (s.session) loadTranscript(s.session);
    if (s.missed_tasks && s.missed_tasks.length) {
      showMissedTasks({ tasks: s.missed_tasks });
    }
  } catch { setStatus("off", t("Sunucu yok")); }
}

// Sayfa yenilenince "konuşmam bitti" haberi hiç gitmiyor ve kulak kapalı
// kalıyor. Açılışta bir kez temizleniyor.
fetch("/api/speaking", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ on: false }),
}).catch(() => {});

loadState();
connect();
setInterval(() => { Scene.load(); loadOrgans(); }, 30000);

// speech.js ses uretemediginde bir kez haber verir; satir sohbete duser.
document.addEventListener("neo:voice-trouble", () => {
  line("alert", t("Ses su an uretilemiyor — ses servisine ulasilamiyor olabilir (internet gerekli). Metin ekranda; ses duzelince kendiliginden devam eder."));
});
loadOrgans();
input.focus();


// --- hatirlama yolu ---------------------------------------------------
// Sahne adim adim actikca liste de doluyor. Bir adima tiklayinca o dugum
// one cikiyor: yol harita gibi takip edilebilsin.
function renderRoute(route, upto) {
  const box = $("route");
  if (!route || !route.length) { box.hidden = true; return; }
  box.hidden = false;
  box.textContent = "";

  const head = document.createElement("div");
  head.className = "head";
  // Sorgu KIRPILIR: kullanıcı koca bir yapılandırma metni yapıştırınca
  // başlık sol yarıyı kaplıyordu. Tam metin zaten sohbette; buradaki
  // yalnızca hangi sorgunun izi olduğunu hatırlatan bir etiket.
  const q = (lastQuery || "").replace(/\s+/g, " ").trim();
  head.textContent = q ? t("İz · ") + (q.length > 48 ? q.slice(0, 48) + "…" : q) : t("Hatırlama izi");
  head.title = q;
  box.append(head);

  // Taranan ile kullanılan aynı şey değil. Zihin bir sorguda onlarca kayda
  // dokunuyor ve hepsini numaralamak "her şeyi karıştırdı" gibi duruyordu:
  // "modbus cihazı ekle" derken listede iki BTC fiyat kaydı numaralı
  // görünüyordu, oysa modelin önüne yalnızca biri kondu.
  //
  // Eski kayıtlarda işaret yok; orada hepsi kullanılmış sayılıyor.
  const marked = route.some((step) => step.used);
  let used = 0;

  // "Bakıldı" seli listeyi (ve altındaki legend'i) eziyordu: kırk kayda
  // dokunulan bir sorguda kullanılan üç kayıt kalabalıkta kayboluyordu.
  // Kullanılanlar HEP listede; bakılanlardan ilk birkaçı görünür, gerisi tek
  // özet satıra iner.
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
    // Numara yalnızca kullanılanlarda ve kendi arasında sıralı: taranıp
    // bırakılanlar sayıyı ilerletirse "1, 4, 6" diye bir liste çıkıyor.
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
