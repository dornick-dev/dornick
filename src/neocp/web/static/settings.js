// Ayar sayfası.
//
// Sunucudan tek bir görüntü geliyor (`/api/settings`) ve tek bir yamayla
// geri gidiyor. Alanlar tek tek kaydedilmiyor: yarısı yazılmış bir
// yapılandırma açılmayan bir programa dönüşüyor.
//
// API anahtarları buraya hiçbir zaman gelmiyor — sunucu yalnızca "var mı"
// diyor. Girilen anahtar bir kez gidiyor, bir daha okunamıyor.

// TR→EN çeviriler (dil.js): kaynak metin Türkçe kalır, İngilizce görüntüde gelir.
Dil.ekle({
  // proje kipi
  "Çalışılan proje": "Working project",
  "boş — yalnızca atölye": "empty — workshop only",
  "Klasör seç…": "Choose a folder…",
  "Bu klasörü seç": "Use this folder",
  "Son projeler": "Recent projects",
  "yukarı": "up",
  "Bu bilgisayar": "This computer",
  "Alt klasör yok": "No subfolders",
  " dosya": " files",
  " klasör": " folders",
  "Proje seçilmedi — yazma yalnızca atölyede serbest.":
    "No project selected — writing is allowed only in the workshop.",
  "Kaydedince burada çalışmaya başlayacağım.":
    "Once you save, I'll start working here.",
  "Şu an burada çalışıyorum; yazma izni bu klasörde geçerli.":
    "I'm working here now; write access applies to this folder.",
  "Kendi kodunda çalışmamı istediğin klasör. Seçmek bir ONAYDIR: orası yazılabilir olur. Atölye ayrıca durmaya devam eder — neo'nun kendi işleri oraya gider. Proje değiştirmek konuşmayı, anıları ve oturum geçmişini ETKİLEMEZ; yalnızca nerede çalışıldığını değiştirir.":
    "The folder where you want me to work on your own code. Choosing it is "
    + "an APPROVAL: that folder becomes writable. The workshop stays as it "
    + "is — neo's own work still goes there. Switching projects does NOT "
    + "affect the conversation, memories or session history; it only changes "
    + "where the work happens.",
  "neo'nun KENDİ alanı — kendi işleri, denemeleri buraya. Şu an: ":
    "neo's OWN area — its own work and experiments go here. Now: ",
  // yedek model
  "Yedek model": "Fallback model",
  "boş — yedek yok": "empty — no fallback",
  // Anahtar TEK parça olmalı: nesne anahtarı bir ifade olamaz ("a" + "b"
  // sözdizimi hatası) ve dosyanın tamamı yüklenmezdi. Kaynak metin
  // `field()` çağrısında birleştiriliyor; buradaki anahtar onun birleşmiş
  // hâliyle birebir aynı olmak zorunda.
  "Asıl model kalıcı olarak yanıt vermezse (kredi bitti, kimlik geçersiz) tur burada sürer ve sohbete tek satır düşer. Geçici hatalar zaten yeniden deneniyor — yedeğe düşmezler.":
    "If the main model fails permanently (out of credit, invalid id) the "
    + "turn continues here and one line appears in the chat. Transient "
    + "errors are already retried — they never reach the fallback.",
  // durum satırı / genel
  "Yükleniyor…": "Loading…",
  "Yukleniyor…": "Loading…",
  "Ayarlar okunamadı": "Could not load settings",
  "Kaydedilmedi": "Unsaved changes",
  "Kaydediliyor…": "Saving…",
  "Kaydedildi": "Saved",
  "Kaydedilemedi": "Could not save",
  "Değişiklik yok": "No changes",
  "Sunucuya ulaşılamadı": "Could not reach the server",

  // taşı / yedek
  "neo'nun burada biriktirdikleri — anılar, bağlar, hedefler, ruh, yetenekler — tek bir pakette taşınır. İçe alma üzerine yazmaz, katar: aynı anı iki kez girmez, kimliği ezmez.":
    "Everything neo has gathered here — memories, links, goals, persona, skills — travels in a single bundle. Importing does not overwrite, it merges: the same memory never enters twice, the identity is never crushed.",
  "Dışa aktar": "Export",
  "Paketi indir": "Download the bundle",
  "İçe al": "Import",
  "Paket seç ve birleştir": "Pick a bundle & merge",
  "Birleştiriliyor…": "Merging…",
  "Paket okunamadı": "Could not read the bundle",
  "Birleştirilemedi": "Merge failed",
  " anı": " memories",
  " bağ": " links",
  " hedef": " goals",
  " yetenek": " skills",
  "ruh": "persona",
  "Katıldı: ": "Merged in: ",
  "Yeni bir şey yoktu (hepsi zaten vardı)": "Nothing new (it was all here already)",
  // taşı: parçalar + sıfırlama
  "Parçalar": "Parts",
  "Anılar": "Memories",
  "Projeler (atölye)": "Projects (workshop)",
  "Ayarlar (anahtarsız)": "Settings (no keys)",
  " tanıma dosyası": " learn-me files",
  " proje dosyası": " project files",
  "ayarlar": "settings",
  " · yedek: ": " · backup: ",
  "Sıfırla": "Reset",
  "Anıları sıfırla": "Reset memories",
  "Beni tanımayı sıfırla": "Reset learn-me",
  "Emin misin?": "Are you sure?",
  "Sıfırlanıyor…": "Resetting…",
  "Sıfırlandı — yedek: ": "Reset done — backup: ",
  "Sıfırlandı (taşınacak bir şey yoktu)": "Reset done (nothing to move)",
  "Sıfırlanamadı": "Could not reset",

  // model
  "Resmî API": "Official API",
  "Anahtar yok": "No key",
  "Sağlayıcı": "Provider",
  "Yüklü modeller soruluyor…": "Asking for available models…",
  "Adres (base URL)": "Address (base URL)",
  "Özel/yerel bir OpenAI-uyumlu uç için düzenle. Boşsa sağlayıcının resmî adresi kullanılır.":
    "Edit for a custom or local OpenAI-compatible endpoint. Left empty, the provider's official address is used.",
  "Seçili sağlayıcının resmi adresi. Gerekirse özel proxy için değiştir.":
    "Official address for the selected provider. Change only for a custom proxy.",
  "Yerel sunucu adresi (LM Studio / Ollama / vLLM). Port farklıysa düzenle.":
    "Local server address (LM Studio / Ollama / vLLM). Edit if the port differs.",
  "Gerekiyorsa API anahtarı / token": "API key / token if required",
  "https://… ya da http://localhost:1234/v1": "https://… or http://localhost:1234/v1",
  "Bağlam": "Context",
  "Bağlam penceresi (token)": "Context window (tokens)",
  "Algıla": "Detect",
  "Soruluyor…": "Asking…",
  "Tek yanıtta azami token": "Max tokens per reply",
  "Geçmişte tutulan görüntü": "Images kept in history",
  "Kabuk ortamından geliyor": "Coming from the shell environment",
  "Kayıtlı — değiştirmek için yaz": "Saved — type to replace",
  "Yapıştır": "Paste",
  " — API anahtarı": " — API key",
  "LM Studio / özel bir uç kimlik doğrulaması istiyorsa buraya yaz. Anahtarlar diske ayrı yazılır, bir daha okunmaz.":
    "If LM Studio or a custom endpoint wants authentication, enter it here. Keys are written to disk separately and never read back.",
  "Bu sağlayıcının API anahtarı. Anahtarlar diske ayrı yazılır, bir daha okunmaz.":
    "API key for this provider. Keys are written to disk separately and never read back.",
  "Yerel sunucu auth istiyorsa buraya yaz. Anahtarlar diske ayrı yazılır, bir daha okunmaz.":
    "If the local server wants authentication, enter it here. Keys are written to disk separately and never read back.",
  "Çaba": "Effort",
  "Düşünen modellerde ne kadar akıl yürüteceği. Ölçüm (qwen3-27b, tek kelimelik istem): high 8,97 sn — low 1,60 sn. Sohbet için low, gerçek iş için high":
    "How much a thinking model reasons. Measured (qwen3-27b, one-word prompt): high 8.97 s — low 1.60 s. Low for chat, high for real work",
  "Düşünme": "Thinking",
  "Kapatmak yerel küçük modellerde daha kararlı sonuç veriyor":
    "Turning it off gives steadier results on small local models",
  "Bu sekmede seçim ANINDA uygulanır — Kaydet yok; konuşma geçmişi yeni modele taşınır. Ajan o sırada çalışıyorsa değişiklik turun bitmesini bekler — akan bir cevabı yarıda kesmemek için.":
    "Choices on this tab apply INSTANTLY — no Save; the conversation history moves to the new model. If the agent is mid-turn, the change waits for the turn to finish — so a streaming answer is not cut off.",
  "Uygulanıyor…": "Applying…",
  "Uygulanacak — yazım bitince": "Will apply once you finish typing",
  "Sunucuya ulaşılamadı ya da liste vermiyor — kimliği elle yaz":
    "Could not reach the server, or it lists nothing — type the id by hand",
  "Sunucu liste vermiyor — kimliği elle yaz":
    "The server lists no models — type the id by hand",
  " model içinde ara…": " models — search…",
  "Kimliği elle yaz…": "Type the id by hand…",
  "Eşleşen model yok": "No matching model",
  " model daha — aramayı daralt": " more models — narrow the search",
  " model": " models",
  "araç kullanır": "uses tools",
  "görüntü okur": "reads images",
  "görüntü yok": "no vision",
  "düşünür": "thinks",
  "düşünmez": "does not think",
  ["Oto modda OpenRouter'ın ücretsiz modelleri kullanılır; kalite ve hız " +
   "düşebilir, model istek sırasında değişebilir. Bazı ücretsiz uçlar " +
   "veriyi eğitimde kullanabilir; istekler 'veri toplama: reddet' " +
   "tercihiyle gönderilir."]:
    "Auto mode uses OpenRouter's free models; quality and speed may drop, " +
    "and the model can change per request. Some free endpoints may use " +
    "your data for training; requests are sent with 'data collection: deny'.",
  "En fazla ": "Up to ",
  " token": " tokens",
  "şu an yüklü: ": "loaded now: ",
  "yüklü değil": "not loaded",

  // anahtarlar
  "Kayıtlı — değiştirmek için yaz": "Saved — type to replace",
  "Yapıştır": "Paste",
  "Kabuk ortamından geliyor": "Comes from the shell environment",
  "Anahtarlar ": "Keys live in ",
  "\\keys.json içinde tutuluyor ve bu sayfaya bir daha gönderilmiyor. Silmek için alanı boşaltıp kaydet.":
    "\\keys.json and are never sent back to this page. To delete one, clear the field and save.",

  // bağlam
  "Algıla": "Detect",
  "Soruluyor…": "Asking…",
  "Sunucu pencere boyutunu bildirmiyor — elle gir":
    "The server does not report a window size — enter it by hand",
  "Sunucu bu modelin yeteneklerini bildirmiyor — elle gir":
    "The server does not report this model's capabilities — enter them by hand",
  "Bağlam penceresi (token)": "Context window (tokens)",
  "Modelin gerçek sınırı. Fazla büyük yazmak sıkıştırmayı hiç tetiklememek, yani sunucunun istemin başını atması demek":
    "The model's real limit. Setting it too high means compaction never triggers — the server silently drops the start of the prompt",
  "Tek yanıtta azami token": "Max tokens per answer",
  "Küçük tutmak uzun cevapların ortasından kesilmesine yol açıyor":
    "Keeping it small cuts long answers off mid-way",
  "Geçmişte tutulan görüntü": "Images kept in history",
  "Bir ekran görüntüsü ~1.5–4.8k token; eskiler metne çevriliyor":
    "A screenshot is ~1.5–4.8k tokens; older ones become text",
  "Pencere %75 dolunca konuşma özetlenip sürüyor; özet aynı anda kalıcı belleğe de yazılıyor, yani oturum kapansa da kaybolmuyor.":
    "Once the window is 75% full the conversation is summarized and continues; the summary is also written to persistent memory, so it survives the session.",

  // kurallar
  "Kurallar okunamadi": "Could not load rules",
  "İzin verilenler": "Allowed",
  "Yasaklananlar": "Denied",
  "Hic kural yok — her sey kipe gore soruluyor":
    "No rules — everything is asked according to the mode",
  "Hic kural yok": "No rules",
  "Kurali kaldir": "Remove rule",
  "Ekle": "Add",

  // posta
  "Kayitli — degistirmek icin yaz": "Saved — type to replace",
  "Hesap tanimlaninca `mail_read` ve `mail_send` araclari aciliyor — yeniden baslatmak gerekiyor. Gonderme her seferinde onaydan geciyor: geri alinamaz ve disariya aciliyor.":
    "Once an account is set up, the `mail_read` and `mail_send` tools open up — a restart is needed. Sending always goes through approval: it is irreversible and leaves the machine.",
  "Gelen posta guvenilmeyen bir kaynak. Govdesinde ajana verilmis gibi gorunen bir talimat varsa uygulanmiyor, sana soyleniyor.":
    "Incoming mail is an untrusted source. If its body carries what looks like an instruction to the agent, it is not followed — you are told instead.",

  // görevler
  "Gorevler okunamadi": "Could not load tasks",
  "durdu": "paused",
  "Çalıştır": "Run",
  "Durdur": "Pause",
  "Sürdür": "Resume",
  "Sil": "Delete",
  "Sırada: ": "Next: ",
  "Durduruldu": "Paused",
  "  ·  Son: ": "  ·  Last: ",
  "＋ Yeni görev": "＋ New task",
  "Kaydet": "Save",
  "Ayarlarda ara": "Search settings",
  "Raporu aç": "Open report",
  "Ana ekranda aç": "Open on main screen",
  "Bu görev şu an çalışıyor": "This task is running now",
  "Son koşu: ": "Last run: ",
  "Sırada: ": "Next: ",
  "Durduruldu": "Paused",
  "Kurulu görev yok. Yukarıdan ekleyebilir ya da ajana söyleyebilirsin: \"her sabah 9'da borsayı kontrol et\".":
    "No tasks set up. Add one above, or just tell the agent: \"check the market every morning at 9\".",
  "Yeni gorev": "New task",
  "Ad": "Name",
  "Ne yapsin": "What it should do",
  "Tetiklendiginde ajana gonderilecek metin": "Text sent to the agent when it fires",
  "Her sabah borsayi kontrol et ve ozetle": "Check the market every morning and summarize",
  "Belirli araliklarla": "At a fixed interval",
  "Her gun belirli saatte": "Daily at a set time",
  "Tekrar": "Repeat",
  "Dakikada bir": "minutes between runs",
  "Aralik": "Interval",
  "Saat (HH:MM)": "Time (HH:MM)",
  "Kur": "Set up",
  "Gorev metni bos": "Task text is empty",

  // ses
  "Ses paketi kurulu degil. Kurmak icin: pip install \"neocp[voice]\"":
    "Voice package not installed. To install: pip install \"neocp[voice]\"",
  "Ses paketi bu kurulumda eksik gorunuyor. Kurulum sihirbazini yeniden calistirmak eksigi onarir.":
    "The voice package appears to be missing from this installation. Re-running the setup wizard repairs it.",
  "Sesli konus": "Speak aloud",
  "Cevaplar cumle cumle sesletilir; ses bulutta uretiliyor, internet gerekiyor":
    "Answers are spoken sentence by sentence; audio is generated in the cloud, so internet is required",
  "Ses": "Voice",
  "Hiz": "Rate",
  "edge-tts bicimi: +0%, -10%, +20%. Hiz kisiye gore cok degisiyor":
    "edge-tts format: +0%, -10%, +20%. Preferred speed varies a lot from person to person",
  "Perde": "Pitch",
  "Karakter": "Character",
  "Solda insan, sagda makine. Ortada bir yerde: ne santral kaydi ne de birebir insan taklidi":
    "Human on the left, machine on the right. Somewhere in between: neither a switchboard recording nor a note-perfect human imitation",
  "Saf insan sesi": "Pure human voice",
  "Hafif yapay": "Slightly synthetic",
  "İnsan-makine karisimi": "Human-machine blend",
  "Belirgin yapay zeka": "Distinctly AI",
  "Tamamen makine": "Fully machine",
  "Tonlama cumle cumle degisiyor: soru yukselir, uyari alcalir, kisa cevap canlanir. Kod bloklari, tablolar ve adresler sesletilmiyor — sesli okunmasi anlamsiz olan seyler metinde kaliyor.":
    "Intonation shifts sentence by sentence: questions rise, warnings fall, short answers perk up. Code blocks, tables and URLs are not spoken — what makes no sense aloud stays in text.",
  "Ses listesi alinamadi — kayitli ses kullaniliyor":
    "Could not fetch the voice list — using the saved voice",
  " ses": " voices",

  // mikrofon
  "Tanima paketi kurulu degil. Kurmak icin: pip install \"neocp[listen]\"":
    "Recognition package not installed. To install: pip install \"neocp[listen]\"",
  "Dinleme bu kuruluma dahil edilmemis. Kurulum sihirbazini yeniden calistirip 'Dinleme (mikrofon)' bilesenini isaretleyerek ekleyebilirsin.":
    "Listening isn't included in this installation. Re-run the setup wizard and tick the 'Listening (microphone)' component to add it.",
  "Mikrofon": "Microphone",
  "Acinca yazma satirinda bas-konus dugmesi cikar; ses bilgisayardan cikmaz":
    "When on, a push-to-talk button appears in the input line; audio never leaves the computer",
  "Bu makinede giris yapan bir ses aygiti bulunamadi":
    "No audio input device found on this machine",
  "Uyandirma sozu": "Wake word",
  "Surekli dinleme acikken aranan kelime. Bos birakirsan yalnizca bas-konus calisir — mikrofon surekli acik kalmaz":
    "The word listened for while always-on listening is active. Leave it empty and only push-to-talk works — the microphone never stays open",
  "Serbest dinleme": "Open listening",
  "Acikken uyandirma sozu hic gerekmiyor: duyulan her cumle neo'ya gidiyor. Evde tek basina calisiyorsan dogrusu bu — \"hava nasil?\" derken baska kime soruyor olabilirsin ki. Odada televizyon varsa ya da baskalariyla konusuyorsan kapali birak":
    "When on, no wake word is needed: every sentence heard goes to neo. Working alone at home this is the right choice — who else would you be asking \"how's the weather?\". If a TV is on or others are talking, leave it off",
  "Kapaliyken bile her cumlede adini soylemek gerekmiyor: bir kez \"neo\" deyip baslattiktan sonra karsilik verdigi her seferde sohbet 3 dakika daha acik kaliyor.":
    "Even when this is off you don't have to say the name in every sentence: once a \"neo\" starts it, each time it answers the conversation stays open for another 3 minutes.",
  "Alan sozlugu": "Domain vocabulary",
  "Tanicinin bilmedigi ozel kelimeler: cihaz adlari, marka, jargon. Virgullu liste. Cihaz ve yetenek adlari kendiliginden ekleniyor; buraya yazdiklarin onlara eklenir":
    "Special words the recognizer doesn't know: device names, brands, jargon. Comma-separated. Device and skill names are added automatically; what you write here is added on top",
  "Omron, Envest, debimetre": "Omron, Envest, flow meter",
  "en hizli, en az dogru (~75 MB)": "fastest, least accurate (~75 MB)",
  "orta (~145 MB)": "middling (~145 MB)",
  "hizli (~500 MB)": "fast (~500 MB)",
  "iyi (~1.5 GB)": "good (~1.5 GB)",
  "en dogru; ekran karti ister (~3 GB)": "most accurate; wants a GPU (~3 GB)",
  "Tanima modeli": "Recognition model",
  "İlk kullanimda indirilir, sonra diskte kalir": "Downloaded on first use, then stays on disk",
  "Dil": "Language",
  "Turkce icin 'tr'. Bos birakmak tahmine birakmak demek ve gozle gorulur bicimde kotu sonuc veriyor":
    "'tr' for Turkish. Leaving it empty means guessing, and the results are visibly worse",
  "Bas-konus sonucu dogrudan gonderilmiyor, yazma satirina dusuyor — tanima her zaman dogru degil ve duzeltme sansin olmali.":
    "Push-to-talk results are not sent directly — they land in the input line. Recognition isn't always right and you should get a chance to fix it.",
  "Kamera": "Camera",
  "Üstteki kamera ikonuyla aynı anahtar. Açınca LED yanar ve önizleme akar; kapatınca aygıt bırakılır.":
    "Same switch as the top camera icon. On: LED and preview. Off: the device is released.",
  "NVIDIA GPU varsa karedeki nesneler yerelde okunur (~400 MB VRAM); sohbet modeline resim değil kısa metin gider. GPU yoksa yalnız önizleme — sorduğunda kesit alınır. Bu ağır gelirse ikondan kapat.":
    "With an NVIDIA GPU, objects are read locally (~400 MB VRAM); the chat model gets short text, not the image. Without a GPU, preview only — a snapshot is taken when you ask. If that is too heavy, turn it off from the icon.",
  "Acinca ustteki kamera ikonundan izleme alani acilir. Kamera surekli acik tamponda durur; kareler kendiliginden modele gitmez":
    "When on, the camera icon in the top bar opens the watch area. The camera stays in an open buffer; frames do not go to the model on their own",
  "Goruntuyu modelin anlamasi ayri bir mesele: yerel modellerin cogu goruntu kabul etmiyor. NVIDIA GPU varsa kare yerelde analiz edilir, sohbet modeline metin gider. GPU yoksa Claude ve GPT kareyi kendisi okur.":
    "Whether the model understands the image is a separate matter: most local models don't accept images. With an NVIDIA GPU the frame is analyzed locally and the chat model gets text. Without a GPU, Claude and GPT read the frame themselves.",

  // izlenen kameralar
  "kameralar okunamadi": "could not load cameras",
  "Goruntu paketi kurulu degil. Kurmak icin: pip install \"neocp[watch]\"":
    "Vision package not installed. To install: pip install \"neocp[watch]\"",
  "Kamera izleme bu kuruluma dahil edilmemis. Kurulum sihirbazini yeniden calistirip 'Kamera izleme' bilesenini isaretleyerek ekleyebilirsin.":
    "Camera watching isn't included in this installation. Re-run the setup wizard and tick the 'Camera watching' component to add it.",
  "genel bakış": "general view",
  " sn": " s",
  "＋ Yeni kamera": "＋ New camera",
  "İzlenen kamera yok. Yerel kamera için kaynak \"0\", ağ kamerası için tam adres yaz (rtsp://... ya da http://...).":
    "No cameras watched. Use \"0\" as the source for a local camera, or a full address for a network camera (rtsp://... or http://...).",
  "Değişiklikler yeniden başlatınca geçerli olur: izleyici kendi thread'inde dönüyor ve çalışırken kamera eklemek açık bir akışın ortasına girmek demek.":
    "Changes take effect after a restart: the watcher spins on its own thread, and adding a camera while it runs means stepping into an open stream.",
  "Yeni kamera": "New camera",
  "Bilgisayar": "Computer",
  "Tür": "Type",
  "Host": "Host",
  "Port / yol": "Port / path",
  "Kullanıcı": "User",
  "Şifre": "Password",
  "şifre": "password",
  "Kaynak / indeks": "Source / index",
  "Bilgisayar kamerası için 0 · ağ için host aşağıda":
    "0 for the computer camera · host below for a network camera",
  "IP veya ad (RTSP/HTTP)": "IP or hostname (RTSP/HTTP)",
  "Yalnız bu makinede cameras.json içinde durur":
    "Stays on this machine in cameras.json",
  "Giris kapisi": "Front door",
  "Kaynak": "Source",
  "Yerel kamera icin 0, 1 … · ag kamerasi icin tam adres":
    "0, 1 … for a local camera · a full address for a network camera",
  "Ne sorsun": "What it should ask",
  "Hareket goruldugunde modele gidecek soru": "The question sent to the model when motion is seen",
  "Kapi acik kalmis mi bak": "Check whether the door was left open",
  "% duyarlilik": "% sensitivity",
  "sn sessizlik": "s of quiet",
  "Esikler": "Thresholds",
  "Kameraya bir ad ver": "Give the camera a name",

  // varlıklar
  "Cihazlar okunamadı": "Could not load devices",
  "＋ Yeni varlık": "＋ New asset",
  "Örneği kendi varlığına göre değiştir. Bilmediğin bir alanı boş bırak — yanlış bir adres fiziksel bir sonuç doğuruyor.":
    "Adapt the example to your own asset. Leave a field you don't know empty — a wrong address has physical consequences.",
  "Okunamayan dosyalar:\n": "Unreadable files:\n",
  "Kayıtlı varlık yok. Bir PLC, bir kapı, bir ağ kamerası, başka bir bilgisayar — neo'nun tanıdığı her şey buraya yazılır. Elle ekleyebilirsin; neo da bir varlık tarif ettiğinde kendisi kaydediyor.":
    "No assets recorded. A PLC, a door, a network camera, another computer — everything neo knows lives here. You can add one by hand; neo also saves one itself when you describe an asset.",
  "Varlık kaydı tek başına bir şey yapmıyor: nereye bağlanılacağını söylüyor. İşi yapan şey ona bağlanan yetenek — neo'ya \"bu varlık için bir yetenek yaz\" dediğinde kendisi yazıyor.":
    "An asset record does nothing by itself: it says where to connect. The work is done by a skill attached to it — tell neo \"write a skill for this asset\" and it writes one.",
  " nokta": " points",
  "Düzenle": "Edit",
  "Evet, sil": "Yes, delete",
  "Vazgeç": "Cancel",
  "Yetenekler": "Skills",
  "Neo'nun araç olarak yüklediği Python betikleri. Satıra tıkla → düzenle.":
    "Python scripts neo loads as tools. Click a row to edit.",
  "Bu yetenek dosyadan ve araç defterinden silinir. Geri gelmez.":
    "This skill is removed from disk and the tool ledger. It will not come back.",
  "Yetenek kaydedilemedi": "Could not save the skill",
  "Neo'nun araç olarak yüklediği Python betikleri. Satıra tıkla → detay.":
    "Python scripts neo loads as tools. Click a row for details.",
  "Kodu göster": "Show code",
  "Kodu gizle": "Hide code",
  "Açıklama yok — dosyanın başındaki docstring buraya düşer.":
    "No description — the file's leading docstring shows up here.",
  "Bağlantılar (MCP)": "Connections (MCP)",
  "Dış araç sunucuları. Listele → düzenle → bağlan. Ham JSON ileri seviye.":
    "External tool servers. List → edit → connect. Raw JSON is advanced.",
  "Bu MCP sunucusu listeden çıkarılır.": "This MCP server will be removed from the list.",
  "ham tanım — ileri seviye": "raw definition — advanced",
  "yeni token (boş = eskisi kalsın)": "new token (empty = keep current)",
  "Token Model → anahtarlara yazıldı: ": "Token saved under Model → keys: ",
  "token — Model anahtarlarına kaydedilir, dosyaya adı yazılır":
    "token — saved to Model keys; only the name is written to the file",
  "Ad gerekli: yalnızca harf, rakam, - ve _": "Name required: letters, digits, - and _ only",
  "Komut boş": "Command is empty",
  "Adres http(s):// ile başlamalı": "Address must start with http(s)://",
  "Token boş": "Token is empty",
  "Token kaydedilemedi": "Could not save the token",
  "Yetenek: ": "Skills: ",
  "Bağlı yetenek yok": "No skills attached",
  "  ·  Ekleyen: ": "  ·  Added by: ",
  "Kaydet": "Save",
  "JSON okunamadı: ": "Invalid JSON: ",

  // yetenekler
  "Yetenekler okunamadı": "Could not load skills",
  "yüklenemedi": "failed to load",
  "＋ Yeni yetenek": "＋ New skill",
  "ad — ör. rapor_ozeti": "name — e.g. report_summary",
  "ne işe yarar, ne zaman kullanılmalı": "what it does, when to use it",
  "Oluştur": "Create",
  "Yeteneğe bir ad ver": "Give the skill a name",
  "Python — NAME, DESCRIPTION, SCHEMA, run(args, ctx). Boşsa iskelet açılır.":
    "Python — NAME, DESCRIPTION, SCHEMA, run(args, ctx). Leave empty for a skeleton.",
  "Kaydedilen yetenek anında araç olarak yüklenir; silinen hem dosyadan hem defterden gider. Standart yetenekler ilk açılışta gelir — silersen geri gelmez. neo da iş sırasında kendine yetenek yazar.":
    "A saved skill loads as a tool instantly; a deleted one is gone from both the file and the ledger. The standard skills arrive on first launch — delete one and it doesn't come back. neo also writes itself skills while working.",
  "Dosya okunamadı": "Could not read the file",
  "Kaydet ve yükle": "Save & load",

  // bağlantılar (MCP)
  "Bağlanılıyor…": "Connecting…",
  "Tarayıcıda giriş bekleniyor…": "Waiting for the browser login…",
  "Bağlayıcılar okunamadı": "Could not load connectors",
  "Giriş yap": "Log in",
  "Çıkış": "Log out",
  "Kaldır": "Remove",
  "adres · ": "address · ",
  "komut · ": "command · ",
  "streamable HTTP; url yeter, kaydedince tarayıcıda OAuth girişi açılır":
    "streamable HTTP; a url is enough — saving opens the OAuth login in the browser",
  "Authorization: Bearer başlığı; token Model → anahtarlara yazılır":
    "Authorization: Bearer header; the token is stored under Model → keys",
  "npx / py gibi bir komut başlatılır (Claude Desktop / Cursor'daki stdio)":
    "starts a command like npx / py (the same stdio as Claude Desktop / Cursor)",
  "stdio — yerel komut": "stdio — local command",
  " araç": " tools",
  "bağlanamadı": "connection failed",
  "araç bildirmedi": "no tools reported",
  "sebep bilinmiyor": "reason unknown",
  "＋ Yeni bağlantı": "＋ New connection",
  "Özel bağlantı": "Custom connection",
  "Hazır dizin veya kendi sunucun. OAuth tarayıcıda açılır; ham JSON ileri seviye.":
    "Ready-made directory or your own server. OAuth opens in the browser; raw JSON is advanced.",
  "Dizin": "Directory",
  "Tek tıkla forma dolar — adres ezberleme.":
    "One click fills the form — no URLs to memorize.",
  "İş": "Work",
  "Tasarım": "Design",
  "Bulut": "Cloud",
  "Yerel": "Local",
  "OAuth": "OAuth",
  "Token": "Token",
  "Tarayıcıda giriş — URL yeter": "Browser login — a URL is enough",
  "Bearer anahtarı, Model → anahtarlar": "Bearer token, stored under Model → keys",
  "npx / py komutu (stdio)": "npx / py command (stdio)",
  "depo, PR ve issue": "repos, PRs and issues",
  "issue ve proje": "issues and projects",
  "sayfa ve veritabanı": "pages and databases",
  "Jira ve Confluence": "Jira and Confluence",
  "kanal ve mesaj": "channels and messages",
  "görev ve proje": "tasks and projects",
  "hata ve izleme": "errors and tracing",
  "ödeme nesneleri": "payment objects",
  "ödeme ve sipariş": "payments and orders",
  "tasarım dosyaları": "design files",
  "veritabanı ve auth": "database and auth",
  "proje ve dağıtım": "projects and deploys",
  "model ve dataset": "models and datasets",
  "Postgres (sunucusuz)": "Postgres (serverless)",
  "tarayıcı otomasyonu": "browser automation",
  "yerel klasör": "local folder",
  "kalıcı bilgi grafiği": "persistent knowledge graph",
  "status, diff, commit": "status, diff, commit",
  "kütüphane belgeleri": "library docs",
  "zincirleme düşünme": "sequential thinking",
  "URL içeriği çek": "fetch URL content",
  "Uzak — girişli": "Remote — with login",
  "adres yeter; kaydedince tarayıcıda giriş açılır":
    "just an address; saving opens a browser login",
  "Uzak — sabit token": "Remote — fixed token",
  "token dosyaya değil Model'e yazılır": "the token goes under Model, not into the file",
  "Yerel komut": "Local command",
  "npx / py gibi bir komut başlatılır (LM Studio biçimi)":
    "starts a command like npx / py (LM Studio format)",
  "ad — ör. notion": "name — e.g. notion",
  "token — Model'e kaydedilir, dosyaya adı yazılır":
    "token — saved under Model; only its name goes into the file",
  "komut ve argümanlar — ör. npx -y bir-mcp":
    "command and arguments — e.g. npx -y some-mcp",
  "Ekle ve bağlan": "Add & connect",
  "Ad gerekli: yalnızca harf, rakam, - ve _": "Name required: letters, digits, - and _ only",
  "Komut boş": "Command is empty",
  "Adres http(s):// ile başlamalı": "The address must start with http(s)://",
  "Token boş": "Token is empty",
  "Token kaydedilemedi": "Could not save the token",
  "sunucu tanımlarını düzenle": "edit the server definitions",
  "Yeniden bağlan": "Reconnect",
  "Biçim Claude Code'unkiyle aynı (mcpServers): yerel sunucu için command/args, uzak sunucu için url/headers. Gizli değeri dosyaya yazma — \"${AD}\" yaz, değeri Model sekmesindeki anahtar alanına AD adıyla ekle.":
    "The format matches Claude Code's (mcpServers): command/args for a local server, url/headers for a remote one. Don't write secrets into the file — write \"${NAME}\" and add the value under NAME in the Model tab key field.",
  "Kaydet ve bağlan": "Save & connect",

  // konum ve açılış
  "Bulunduğun yer": "Where you are",
  "Yazarsan kesin kaynak bu olur; neo sorduğunda burayı okur ve bir daha sormaz":
    "If you type it, this becomes the definitive source; when neo wonders, it reads this and never asks again",
  "IP'den konum bul": "Locate by IP",
  "Açıkken adresin iki konum servisine gidiyor. Sonuç şehir düzeyinde güvenilmez — ölçümde iki servis iki ayrı şehir söyledi — ve neo onu kesin değil, teyit edilecek bir ipucu olarak kullanıyor":
    "When on, your address goes to two location services. The result is unreliable at city level — in one measurement two services named two different cities — and neo treats it as a hint to verify, not a fact",
  "Kapalıyken bile ülke biliniyor: makinenin saat diliminden geliyor, ağa çıkmıyor. Şehir gerekiyorsa neo sana soruyor.":
    "Even when off, the country is known: it comes from the machine's timezone and never touches the network. If the city matters, neo asks you.",
  "Bilgisayar açılınca başlat": "Start when the computer boots",
  "Yalnızca Windows'ta": "Windows only",
  "Yok": "Not available",
  "bilgisayar açılınca başlat": "Start when the computer boots",
  "Tepside çalışan, \"hey neo\" ile uyanan bir ajanı her açılışta elle başlatmak gerekmesin":
    "An agent that sits in the tray and wakes to \"hey neo\" shouldn't need starting by hand at every boot",
  "Çalıştırılacak satır": "Command that runs",
  "Kayıt: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run · Görev Yöneticisi › Başlangıç'tan da görebilirsin":
    "Registry: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run · also visible under Task Manager › Startup",

  // makine
  "Aynı anda model isteği": "Concurrent model requests",
  "Yerel sunucularda 1 kalmalı: LM Studio meşgul bir modele ikinci istek gelince modelin ikinci bir kopyasını yüklüyor":
    "Keep it at 1 for local servers: when a second request hits a busy model, LM Studio loads a second copy of it",
  "Yerel model optimizasyonu": "Local model optimization",
  "Açıkken: diğer modelleri boşaltır, tek kopya tutar, VRAM/model boyutuna göre bağlamı düşürür. Kapalıysa normal kullanım.":
    "When on: unloads other models, keeps a single copy, fits context to VRAM/model size. When off: normal use.",
  "Ekran kartı": "Graphics card",
  "nvidia-smi yok — VRAM otomatik ölçülemeyecek; yine de diğer modeller boşaltılır":
    "nvidia-smi missing — VRAM won't be measured automatically; other models are still unloaded",
  "Aynı anda araç": "Concurrent tools",
  "Model bir turda on araç birden isteyebiliyor; hepsini aynı anda başlatmak zayıf bir makinede belleği tüketiyor":
    "The model can request ten tools in one turn; launching them all at once exhausts memory on a weak machine",
  "Aynı anda alt ajan": "Concurrent subagents",
  "İşler yoğunken neo işi yardımcılara dağıtıyor; bu sayıdan fazlası sıraya girer. Yerel sunucuda model tek kopyaysa 1 mantıklı":
    "When work piles up neo hands it to helpers; beyond this number they queue. With a single model copy on a local server, 1 makes sense",
  "Modeli yüklü tut (saniye)": "Keep the model loaded (seconds)",
  "0 = sunucunun kendi davranışı. Her istekte yeniden yükleme onlarca saniye sürüyor ve ilk cevabı bekletiyor":
    "0 = the server's own behavior. Reloading on every request takes tens of seconds and delays the first answer",
  "neo chrome (tarayıcı)": "neo chrome (browser)",
  "neo kendi Chrome/Edge profiliyle sayfa açar, okur, görüntü alır. Girişleri o pencerede sen yaparsın; oturumlar profilinde kalıcıdır":
    "neo opens, reads and screenshots pages with its own Chrome/Edge profile. You do the logins in that window yourself; sessions persist in the profile",
  "Sunucuda yüklü olanlar": "Loaded on the server",
  "Sunucu yüklü model listesi vermiyor": "The server does not list loaded models",
  " — aynı model birden çok kez yüklü. \"Aynı anda model isteği\" 1 olduğunda yenisi oluşmaz; duranları LM Studio'da Eject ile kaldır.":
    " — the same model is loaded more than once. With \"Concurrent model requests\" at 1 no new copy appears; remove the idle ones with Eject in LM Studio.",

  // yetki
  "İzin kipi": "Permission mode",
  "Kurallar": "Rules",
  "arac:hedef-deseni · deny her zaman kazanir": "tool:target-pattern · deny always wins",
  "İzin kipi anında geçerli olur — yeniden başlatmak gerekmez. \"Tam yetki\" seçiliyken hiçbir komut sorulmadan çalışır.":
    "The permission mode applies instantly — no restart needed. With \"full authority\" selected, every command runs without asking.",
  "Atölye klasörü": "Workshop folder",
  "Ajanın kendi alanı — yazma yalnızca burada serbest. Şu an: ":
    "The agent's own space — writing is only free here. Currently: ",
  "Atölye sınırı açık": "Workshop boundary on",
  "Kapatmak ajanın bilgisayardaki her yere yazabilmesi demek":
    "Turning it off means the agent can write anywhere on the computer",

  // dosyalar
  "Dizin okunamadı": "Could not read the directory",
  "Çalışma alanı": "Workspace",
  "Boş": "Empty",
  "← Geri": "← Back",
  "İkili dosya — burada gösterilemez": "Binary file — can't be shown here",
  "Dosyanın başı gösteriliyor": "Showing the start of the file",

  // dış kapı
  "Dış kapı (API)": "External gate (API)",
  "Başka ajanlar ve araçlar sohbete programla yazıp yanıtın tamamını alabilir: POST 127.0.0.1'e /api/gate, gövde {\"text\": \"...\"}. Yalnızca bu makineden erişilir":
    "Other agents and tools can write to the chat programmatically and " +
    "receive the full response: POST /api/gate on 127.0.0.1 with body " +
    "{\"text\": \"...\"}. Reachable only from this machine",
  "Dış kapı açıldı": "External gate opened",
  "Dış kapı kapandı": "External gate closed",

  // beni tanı
  "Beni tanı": "Learn me",
  "Beyin ortada dursun": "Brain takes the stage",
  "Açıkken hiçbir panel açık değilse beyin ekranın ortasında büyür; kapatırsan sağ panelde kalır ve yazılar hiç örtülmez":
    "When on, the brain grows into the centre when no panel is open; when off it stays in the right panel and text is never covered",
  "Beyin ortada büyüyecek": "The brain will take the stage",
  "Beyin sağ panelde kalacak": "The brain will stay in the side panel",
  "neo'nun yerel taban modeli anılarından gece sessizce öğrenir: birikince arka planda, düşük öncelikle ince ayar koşar; gerileyen aday sınav kapısında çöpe gider. Etiketleme seçili modelle yapılır: yerel modelde veri makineden çıkmaz; bulut modelde bu adım açık onay vermedikçe atlanır (onay verilirse anı metni o sağlayıcıya gider)":
    "neo's local base model quietly learns from your memories at night: once enough has gathered, a low-priority fine-tune runs in the background; a regressing candidate is discarded at the exam gate. Labeling uses your selected model: with a local model data never leaves the machine; with a hosted model this step is skipped unless you explicitly opt in (opting in sends memory text to that provider)",
  "Tanıma eğitimi açıldı": "Personal training enabled",
  "Tanıma eğitimi kapatıldı": "Personal training disabled",
  "Bulut modelle etiketlemeye izin ver": "Allow labeling with a hosted model",
  "Kapalıyken (varsayılan) gece etiketlemesi yalnız yerel modelle çalışır ve anıların makineden çıkmaz. Açarsan anı metinleri etiketleme için seçili bulut sağlayıcısına gönderilir":
    "When off (default), nightly labeling only runs with a local model and your memories never leave the machine. When on, memory text is sent to your selected hosted provider for labeling",
  "Bulut etiketleme onayı verildi": "Cloud labeling consent granted",
  "Bulut etiketleme onayı geri alındı": "Cloud labeling consent withdrawn",
  " · eğitim düzeneği bu makinede kurulu değil": " · the training rig is not installed on this machine",

  // bölüm başlıkları (pane-head): sekme adı + tek cümlelik ne-işe-yarar
  "Anahtarlar": "Keys",
  "Bağlam": "Context",
  "Kameralar": "Cameras",
  "Konum": "Location",
  "Varlıklar": "Assets",
  "Yetenekler": "Skills",
  "Bağlantılar": "Connectors",
  "Posta": "Mail",
  "Görevler": "Tasks",
  "Yetki": "Permissions",
  "Makine": "Machine",
  "Dosyalar": "Files",
  "Taşı": "Transfer",
  "Sağlayıcı, anahtar, model ve bağlam — hepsi burada.":
    "Provider, key, model and context — all here.",
  "Sağlayıcı, model ve düşünme derinliği.": "Provider, model and thinking depth.",
  "Sağlayıcı anahtarları — diske ayrı yazılır, geri okunmaz.":
    "Provider keys — written to disk separately, never read back.",
  "Pencere boyutu, yanıt uzunluğu ve görüntü bütçesi.":
    "Window size, answer length and the image budget.",
  "neo'nun sesi: açık/kapalı, ton ve karakter.":
    "neo's voice: on/off, tone and character.",
  "Dinleme ve uyandırma sözü.":
    "Listening and the wake word.",
  "Kamera aç/kapa ve izlenen kameralar.":
    "Camera on/off and watched cameras.",
  "Nerede olduğun ve bilgisayar açılınca başlatma.":
    "Where you are, and starting at boot.",
  "neo'nun tanıdığı cihazlar ve sistemler.":
    "The devices and systems neo knows.",
  "neo'nun araç olarak yüklediği betikler.":
    "The scripts neo loads as tools.",
  "Dış araç sunucuları (MCP).": "External tool servers (MCP).",
  "Posta okuma ve gönderme hesabı.": "The account for reading and sending mail.",
  "Zamanlanmış işler: ne, ne zaman, en son ne oldu.":
    "Scheduled jobs: what, when, and what happened last.",
  "Neye izin var: kip, kurallar ve atölye sınırı.":
    "What is allowed: mode, rules and the workshop boundary.",
  "Sürüm, eşzamanlılık, arayüz dili, tarayıcı ve dış kapı.":
    "Version, concurrency, interface language, browser and the external gate.",

  // sürüm
  "Sürüm": "Version",
  "kurulum": "installed",
  "geliştirme": "development",
  "Güncellemeleri denetle": "Check for updates",
  "Denetim yalnız bu düğmeyle yapılır — arka planda kendiliğinden ağa çıkılmaz":
    "Checks run only with this button — nothing phones home in the background",
  " mevcut — indir": " available — download",
  "Güncel — daha yeni sürüm yok": "Up to date — no newer release",
  "Ağa ulaşılamadı — internet bağlantısını denetle":
    "Could not reach the network — check your internet connection",
  "Yayınlanmış sürüm bulunamadı": "No published release found",
  "Atölyede üretilen dosyalar.": "Files produced in the workshop.",
  "Paketle taşı, birleştir, sıfırla.": "Bundle, merge, reset.",
});

const Settings = (() => {
  const panel = document.getElementById("settings");
  const note = document.getElementById("settings-note");
  const panes = {
    model: document.getElementById("pane-model"),
    mail: document.getElementById("pane-mail"),
    tasks: document.getElementById("pane-tasks"),
    voice: document.getElementById("pane-voice"),
    hearing: document.getElementById("pane-hearing"),
    eyes: document.getElementById("pane-eyes"),
    devices: document.getElementById("pane-devices"),
    place: document.getElementById("pane-place"),
    skills: document.getElementById("pane-skills"),
    connectors: document.getElementById("pane-connectors"),
    machine: document.getElementById("pane-machine"),
    access: document.getElementById("pane-access"),
    files: document.getElementById("pane-files"),
    transfer: document.getElementById("pane-transfer"),
  };

  let state = null;
  // Kaydedilmemiş değişiklikler. Sunucudan gelen görüntü değil, kullanıcının
  // dokunduğu alanlar burada birikiyor.
  let patch = {};

  // Model sekmesi ANINDA uygulanır (Cursor/Claude alışkanlığı: seç = aktif;
  // "aşağı inip Kaydet" yok). Kısa bekleme art arda tıklamaları tek kayda
  // indiriyor; metin alanları yazım bitince (change) kaydediliyor, harf harf
  // değil. save(true): otomatik kayıt panelleri YENİDEN ÇİZMEZ — kullanıcı
  // yazarken alan elinden alınmasın.
  let saveTimer = null;
  function saveSoon(ms) {
    clearTimeout(saveTimer);
    say("Uygulanıyor…");
    saveTimer = setTimeout(() => save(true), ms || 450);
  }
  // Metin/sayı alanı: yazım bitince kaydet.
  const applyOnChange = (node) => {
    node.addEventListener("change", () => saveSoon(150));
    return node;
  };

  // Oto kipinin açıklaması: yalnız OpenRouter + "oto" seçiliyken görünür.
  const OTO_NOTU =
    "Oto modda OpenRouter'ın ücretsiz modelleri kullanılır; kalite ve hız " +
    "düşebilir, model istek sırasında değişebilir. Bazı ücretsiz uçlar " +
    "veriyi eğitimde kullanabilir; istekler 'veri toplama: reddet' " +
    "tercihiyle gönderilir.";

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  function say(text, bad, good) {
    // Çeviri burada, tek noktada: sunucudan gelen hata eşleşmez, olduğu
    // gibi görünür; buradaki sabit metinler İngilizceye döner.
    note.textContent = t(text) || "";
    note.className = "panel-note" + (bad ? " bad" : good ? " good" : "");
  }

  // --- açılış / kapanış -------------------------------------------------

  async function open(tab) {
    const already = !panel.hidden;
    if (!already) {
      panel.hidden = false;
      // Sohbet sola kaysin: panelin altinda kalan metin okunmuyor ve
      // kenarlardan sizan parcalar arayuzu bozuk gosteriyordu.
      document.body.classList.add("settling");
      say("Yükleniyor…");
      try {
        state = await (await fetch("/api/settings")).json();
      } catch {
        say("Ayarlar okunamadı", true);
        return;
      }
      patch = {};
      say("");
      draw();
    } else {
      panel.hidden = false;
      document.body.classList.add("settling");
    }
    if (tab) {
      const button = document.querySelector('#tabs [data-tab="' + tab + '"]');
      if (button) button.click();
    }
    const onTab = document.querySelector("#tabs button.on");
    if (onTab && onTab.dataset.tab) syncSaveFoot(onTab.dataset.tab);
  }

  const close = () => {
    panel.hidden = true;
    document.body.classList.remove("settling");
  };
  const toggle = () => (panel.hidden ? open() : close());

  function draw() {
    drawModel();
    drawMail();
    drawVoice();
    drawHearing();
    drawMachine();
    drawAccess();
    drawTransfer();
  }

  // --- taşı / yedek -----------------------------------------------------
  //
  // neo'nun bu makinede biriktirdikleri (anılar, bağlar, hedefler, ruh,
  // yetenekler) tek bir taşınabilir pakete konup başka bir neo'ya
  // BİRLEŞTİRİLEBİLİR. İçe alma üzerine yazmıyor — katıyor: aynı anı iki
  // kez girmiyor, kimlik (ruh) ezilmiyor.

  function drawTransfer() {
    const pane = panes.transfer;
    if (!pane) return;
    pane.textContent = "";
    head(pane, "Taşı", "Paketle taşı, birleştir, sıfırla.");

    pane.append(el("p", "pane-note",
      t("neo'nun burada biriktirdikleri — anılar, bağlar, hedefler, ruh, " +
      "yetenekler — tek bir pakette taşınır. İçe alma üzerine yazmaz, katar: " +
      "aynı anı iki kez girmez, kimliği ezmez.")));

    // Parça seçimi: dışa VE içe aktarma bu kutulara bakıyor. Varsayılan
    // yalnız anılar — eski paketle birebir aynı; sunucuya taşınırken
    // "beni tanı" modeli, atölye ve (anahtarsız) ayarlar da eklenebilir.
    const parca = { anilar: true, tanima: false, projeler: false, ayarlar: false };
    const PARCA_AD = [["anilar", "Anılar"], ["tanima", "Beni tanı"],
                      ["projeler", "Projeler (atölye)"], ["ayarlar", "Ayarlar (anahtarsız)"]];
    const secili = () => PARCA_AD.map(([ad]) => ad).filter((ad) => parca[ad]);
    const disaUrl = () => "/api/transfer/export?parcalar=" + secili().join(",");

    const parts = el("div", "xfer-parts");
    parts.append(el("span", "xfer-lead", t("Parçalar")));
    for (const [ad, etiket] of PARCA_AD) {
      const kutu = el("label", "xfer-part");
      const chk = el("input");
      chk.type = "checkbox";
      chk.className = "input-check";
      chk.checked = parca[ad];
      chk.addEventListener("change", () => { parca[ad] = chk.checked; dl.href = disaUrl(); });
      kutu.append(chk, el("span", null, t(etiket)));
      parts.append(kutu);
    }
    pane.append(parts);

    // Dışa aktar: paketi indir.
    const out = el("div", "xfer-row");
    const dl = el("a", "xfer-btn out", t("Paketi indir"));
    dl.href = disaUrl();
    dl.setAttribute("download", "");
    out.append(el("span", "xfer-lead", t("Dışa aktar")), dl);
    pane.append(out);

    // İçe al: dosya seç → birleştir (yalnızca seçili parçalar işlenir).
    const inp = el("input");
    inp.type = "file";
    inp.accept = ".neobundle,.zip";
    inp.className = "xfer-file";
    inp.addEventListener("change", () => importBundle(inp.files[0], report, secili()));

    const pick = el("button", "xfer-btn in", t("Paket seç ve birleştir"));
    pick.type = "button";
    pick.addEventListener("click", () => inp.click());

    const inrow = el("div", "xfer-row");
    inrow.append(el("span", "xfer-lead", t("İçe al")), pick, inp);
    pane.append(inrow);

    // Sıfırlamalar: iki adımlı onay (apps.js'teki silme kalıbı) — yanlış
    // tık bir zihni götürmesin. Sunucu silmeden önce yedek alıyor
    // (.neocp/yedek-<tarih>/); yine de düğme tehlikeli görünmeli.
    const sifirlaBtn = (etiket, hedef) => {
      const btn = el("button", "xfer-btn danger", t(etiket));
      btn.type = "button";
      btn.addEventListener("click", async () => {
        if (!btn.dataset.armed) {
          btn.dataset.armed = "1";
          btn.textContent = t("Emin misin?") + " " + t(etiket);
          setTimeout(() => { delete btn.dataset.armed; btn.textContent = t(etiket); }, 3500);
          return;
        }
        delete btn.dataset.armed;
        btn.textContent = t(etiket);
        report.className = "xfer-report";
        report.textContent = t("Sıfırlanıyor…");
        let res;
        try {
          res = await (await fetch("/api/reset", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ hedef }),
          })).json();
        } catch { res = { ok: false, error: t("Sunucuya ulaşılamadı") }; }
        if (res && res.ok) {
          report.className = "xfer-report good";
          report.textContent = res.yedek
            ? t("Sıfırlandı — yedek: ") + res.yedek
            : t("Sıfırlandı (taşınacak bir şey yoktu)");
        } else {
          report.className = "xfer-report bad";
          report.textContent = (res && res.error) || t("Sıfırlanamadı");
        }
      });
      return btn;
    };
    // Tehlike bölgesi: sıfırlamalar görsel olarak da ayrık dursun.
    const resetRow = el("div", "xfer-row danger-zone");
    resetRow.append(el("span", "xfer-lead", t("Sıfırla")),
                    sifirlaBtn("Anıları sıfırla", "anilar"),
                    sifirlaBtn("Beni tanımayı sıfırla", "tanima"));
    pane.append(resetRow);

    const report = el("p", "xfer-report");
    pane.append(report);
  }

  async function importBundle(file, report, parcalar) {
    if (!file) return;
    report.className = "xfer-report";
    report.textContent = t("Birleştiriliyor…");
    let res;
    try {
      const buf = await file.arrayBuffer();
      res = await (await fetch("/api/transfer/import?parcalar=" + (parcalar || []).join(","), {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: buf,
      })).json();
    } catch {
      report.className = "xfer-report bad";
      report.textContent = t("Paket okunamadı");
      return;
    }
    if (!res || !res.ok) {
      report.className = "xfer-report bad";
      report.textContent = (res && res.error) ? res.error : t("Birleştirilemedi");
      return;
    }
    const parts = [];
    if (res.memories) parts.push(res.memories + t(" anı"));
    if (res.links) parts.push(res.links + t(" bağ"));
    if (res.goals) parts.push(res.goals + t(" hedef"));
    if (res.skills) parts.push(res.skills + t(" yetenek"));
    if (res.persona) parts.push(t("ruh"));
    if (res.tanima) parts.push(res.tanima + t(" tanıma dosyası"));
    if (res.projeler) parts.push(res.projeler + t(" proje dosyası"));
    if (res.ayarlar) parts.push(t("ayarlar"));
    report.className = "xfer-report good";
    report.textContent = parts.length
      ? t("Katıldı: ") + parts.join(" · ")
      : t("Yeni bir şey yoktu (hepsi zaten vardı)");
    if (res.yedek) report.textContent += t(" · yedek: ") + res.yedek;
  }

  // --- alan yardımcıları ------------------------------------------------

  // Bölüm başlığı: her sekmenin üstünde büyükçe ad + tek cümlelik açıklama.
  // Sekme listesi adı zaten söylüyor ama içerik alanı başlıksız açılınca
  // sayfa ortasından başlıyormuş gibi duruyordu.
  function head(pane, title, desc) {
    const box = el("div", "pane-head");
    box.append(el("h2", "pane-title", t(title)));
    if (desc) box.append(el("p", "pane-desc", t(desc)));
    pane.append(box);
  }

  function field(label, hint, control) {
    // Etiket ve ipucu görüntüleme anında çevriliyor: sunucudan ya da
    // değişkenden gelen metin eşleşmez ve olduğu gibi kalır.
    const row = el("label", "field");
    const head = el("span", "field-label", t(label));
    row.append(head, control);
    if (hint) row.append(el("span", "field-hint", t(hint)));
    return row;
  }

  function text(value, onChange, placeholder) {
    const node = el("input", "input-text");
    node.type = "text";
    node.value = value ?? "";
    if (placeholder) node.placeholder = placeholder;
    node.addEventListener("input", () => onChange(node.value));
    return node;
  }

  function number(value, onChange) {
    const node = el("input", "input-text input-num");
    node.type = "number";
    node.value = value ?? 0;
    node.addEventListener("input", () => onChange(node.value));
    return node;
  }

  function toggleBox(value, onChange) {
    const node = el("input");
    node.type = "checkbox";
    node.className = "input-check";
    node.checked = !!value;
    node.addEventListener("change", () => onChange(node.checked));
    return node;
  }

  // Yamaya iç içe bir alan yazar: patch.model.max_tokens gibi.
  function set(section, key, value) {
    patch[section] = patch[section] || {};
    patch[section][key] = value;
    say("Kaydedilmedi");
  }

  function chosenProvider() {
    const id = patch.provider || state.provider;
    return (state.providers || []).find((p) => p.id === id) || null;
  }

  function isLocalBase() {
    const url = String((patch.model || {}).base_url ?? state.model.base_url ?? "");
    return /localhost|127\.0\.0\.1|\[::1\]/i.test(url);
  }

  function baseUrlHint() {
    if (isLocalBase()) {
      return "Yerel sunucu adresi (LM Studio / Ollama / vLLM). Port farklıysa düzenle.";
    }
    return "Seçili sağlayıcının resmi adresi. Gerekirse özel proxy için değiştir.";
  }

  function apiKeyHintKey() {
    if (isLocalBase() || !(chosenProvider() && chosenProvider().env)) {
      return "Yerel sunucu auth istiyorsa buraya yaz. Anahtarlar diske ayrı yazılır, bir daha okunmaz.";
    }
    return "Bu sağlayıcının API anahtarı. Anahtarlar diske ayrı yazılır, bir daha okunmaz.";
  }

  // --- model ------------------------------------------------------------

  function drawModel() {
    const pane = panes.model;
    pane.textContent = "";
    head(pane, "Model", "Sağlayıcı, anahtar, model ve bağlam — hepsi burada.");

    const chosen = () => patch.provider || state.provider;
    const picker = el("div", "choices");

    for (const entry of state.providers) {
      const card = el("button", "choice" + (entry.id === chosen() ? " on" : ""));
      card.type = "button";
      card.append(el("b", null, entry.label));
      card.append(el("span", null, entry.base_url || t("Resmî API")));
      if (entry.env && !entry.has_key) card.append(el("i", "warn", t("Anahtar yok")));
      card.addEventListener("click", () => {
        if (entry.id === chosen()) return;
        patch.provider = entry.id;
        // Adres ve anahtar değişkeni sağlayıcıyla birlikte gidiyor; sunucu
        // da aynısını yapıyor ama kullanıcı sonucu hemen görmeli.
        //
        // Ad da düşüyor: bir sağlayıcının modeli ötekinde yok. Eskisi
        // kalınca kullanıcı yeni sağlayıcıyı seçiyor ama kaydedilen ad
        // eskisi oluyor ve "seçtiğim model yüklenmiyor" oluyordu. Yeni
        // katalog gelince ilki kendiliğinden seçiliyor.
        patch.model = { ...(patch.model || {}), base_url: entry.base_url,
                        provider: entry.provider, api_key_env: entry.env,
                        name: "" };
        drawModel();
        saveSoon(900);   // katalog ilk modeli yazana kadar küçük pay
      });
      picker.append(card);
    }

    pane.append(field("Sağlayıcı", "", picker));

    // Kimliği elle yazdırmak hataya davetiye: "qwen3.5-9b" ile
    // "qwen/qwen3.5-9b" arasındaki fark 404 demek ve hata ancak ilk
    // mesajda görünüyor. Sunucu listeyi veriyorsa seçtiriyoruz.
    const slot = el("div", "model-pick");
    slot.append(applyOnChange(text((patch.model || {}).name ?? state.model.name,
                     (v) => set("model", "name", v.trim()))));
    pane.append(field(
      "Model",
      "Yüklü modeller soruluyor…",
      slot
    ));
    fillModels(slot);

    // Yedek model: asıl model KALICI olarak susarsa (kredi bitti, kimlik
    // geçersiz) tur ölmek yerine bununla sürüyor. Boş bırakmak bugünkü
    // davranış — hata olduğu gibi yüzeye çıkar. Geçici hatalar buraya hiç
    // uğramıyor; onlar zaten yeniden deneniyor.
    const yedek = applyOnChange(text((patch.model || {}).fallback_model ?? state.model.fallback_model ?? "",
                       (v) => set("model", "fallback_model", v.trim())));
    yedek.placeholder = t("boş — yedek yok");
    yedek.setAttribute("list", "yedek-modeller");
    const yedekListe = el("datalist");
    yedekListe.id = "yedek-modeller";
    const yedekAlan = field(
      "Yedek model",
      "Asıl model kalıcı olarak yanıt vermezse (kredi bitti, kimlik " +
      "geçersiz) tur burada sürer ve sohbete tek satır düşer. Geçici " +
      "hatalar zaten yeniden deneniyor — yedeğe düşmezler.",
      yedek
    );
    yedekAlan.append(yedekListe);
    pane.append(yedekAlan);
    fillFallback(yedekListe);

    // Adres (base URL): preset yalnızca başlangıç. Özel bir port, uzak bir
    // sunucu ya da başka bir OpenAI-uyumlu uç için elle düzenlenebilir.
    const url = applyOnChange(text((patch.model || {}).base_url ?? state.model.base_url ?? "",
                     (v) => set("model", "base_url", v.trim())));
    url.placeholder = isLocalBase()
      ? t("http://localhost:1234/v1")
      : t("https://…");
    pane.append(field("Adres (base URL)", baseUrlHint(), url));

    // API anahtarı: yalnız seçili sağlayıcı (ayrı Anahtarlar sayfası yok).
    const pMeta = chosenProvider();
    const authKey = el("input", "input-text");
    authKey.type = "password";
    authKey.autocomplete = "off";
    const keyVar = (patch.model || {}).api_key_env ?? state.model.api_key_env
      ?? (pMeta && pMeta.env) ?? null;
    const keyKnown = !!(pMeta && pMeta.has_key);
    authKey.placeholder = keyKnown
      ? t("Kayıtlı — değiştirmek için yaz")
      : t("Yapıştır");
    authKey.addEventListener("input", () => {
      const v = authKey.value;
      const env = keyVar || "OPENAI_API_KEY";
      patch.keys = patch.keys || {};
      // Boş = silme isteği (keys.json'dan düşer).
      patch.keys[env] = v;
      if (!((patch.model || {}).api_key_env ?? state.model.api_key_env)) {
        set("model", "api_key_env", env);
      }
      say("Uygulanacak — yazım bitince");
    });
    authKey.addEventListener("change", () => saveSoon(150));
    const keyLabel = pMeta && pMeta.label
      ? (pMeta.label + (keyKnown ? " ✓" : ""))
      : t("API anahtarı");
    pane.append(field(keyLabel, apiKeyHintKey(), authKey));
    if (pMeta && pMeta.env && !isLocalBase()) {
      const note = authKey.parentElement && authKey.parentElement.querySelector(".field-hint");
      if (note) {
        const kabuk = pMeta.from_env
          ? (" · " + t("Kabuk ortamından geliyor"))
          : "";
        note.textContent = t(apiKeyHintKey())
          + " · " + (pMeta.hint || "") + " · " + pMeta.env + kabuk;
      }
    } else if (pMeta && pMeta.from_env) {
      const note = authKey.parentElement && authKey.parentElement.querySelector(".field-hint");
      if (note) {
        note.textContent = t("Kabuk ortamından geliyor") + " (" + pMeta.env + ")";
      }
    }

    const effort = el("select", "input-text");
    for (const level of ["low", "medium", "high", "xhigh", "max"]) {
      const option = el("option", null, level);
      option.value = level;
      if (level === ((patch.model || {}).effort ?? state.model.effort)) option.selected = true;
      effort.append(option);
    }
    effort.addEventListener("change", () => { set("model", "effort", effort.value); saveSoon(); });
    pane.append(field(
      "Çaba",
      "Düşünen modellerde ne kadar akıl yürüteceği. Ölçüm (qwen3-27b, tek " +
      "kelimelik istem): high 8,97 sn — low 1,60 sn. Sohbet için low, " +
      "gerçek iş için high",
      effort
    ));

    const thinkingBox = toggleBox((patch.model || {}).thinking ?? state.model.thinking,
                (v) => { set("model", "thinking", v); saveSoon(); });
    thinkingBox.id = "model-thinking";
    pane.append(field(
      "Düşünme",
      "Kapatmak yerel küçük modellerde daha kararlı sonuç veriyor",
      thinkingBox
    ));

    // Bağlam — ayrı sekme yok; seçili modelin penceresi burada.
    pane.append(el("h3", "pane-sub", t("Bağlam")));
    const window_ = applyOnChange(number((patch.model || {}).context_window ?? state.model.context_window,
                           (v) => set("model", "context_window", v)));
    window_.id = "model-window";
    const detect = el("button", "detect", t("Algıla"));
    detect.type = "button";
    detect.addEventListener("click", async () => {
      detect.textContent = t("Soruluyor…");
      let answer = {};
      try {
        answer = await (await fetch("/api/detect-window", { method: "POST" })).json();
      } catch { /* aşağıda */ }
      detect.textContent = t("Algıla");
      const got = adoptAnswer(answer);
      if (got) {
        saveSoon();
      } else {
        say("Sunucu bu modelin yeteneklerini bildirmiyor — elle gir", true);
      }
    });
    const winRow = el("div", "with-action");
    winRow.append(window_, detect);
    pane.append(field(
      "Bağlam penceresi (token)",
      "Modelin gerçek sınırı. Fazla büyük yazmak sıkıştırmayı hiç tetiklememek, " +
      "yani sunucunun istemin başını atması demek",
      winRow
    ));
    pane.append(field(
      "Tek yanıtta azami token",
      "Küçük tutmak uzun cevapların ortasından kesilmesine yol açıyor",
      applyOnChange(number((patch.model || {}).max_tokens ?? state.model.max_tokens,
             (v) => set("model", "max_tokens", v)))
    ));
    pane.append(field(
      "Geçmişte tutulan görüntü",
      "Bir ekran görüntüsü ~1.5–4.8k token; eskiler metne çevriliyor",
      applyOnChange(number((patch.context || {}).keep_recent_images ?? state.context.keep_recent_images,
             (v) => set("context", "keep_recent_images", Number(v))))
    ));

    pane.append(el("p", "pane-note",
      t("Bu sekmede seçim ANINDA uygulanır — Kaydet yok; konuşma geçmişi " +
      "yeni modele taşınır. Ajan çalışıyorsa değişiklik bir sonraki " +
      "adımda (araç turu arasında) geçer — akan cevabı yarıda kesmez. " +
      "Bağlam penceresi katalogdan otomatik dolar; Algıla elle yenilemedir.")));
  }

  // Yedek model alanının önerileri. Aynı katalog, ama seçim ZORUNLU değil:
  // alan serbest metin kalıyor — sunucu liste vermeyen bir uçta da yedek
  // yazılabilmeli.
  async function fillFallback(listNode) {
    let answer = {};
    const pending = patch.model || {};
    try {
      answer = await (await fetch("/api/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_url: pending.base_url ?? state.model.base_url,
          provider: pending.provider ?? state.model.provider,
          api_key_env: pending.api_key_env ?? state.model.api_key_env,
        }),
      })).json();
    } catch { return; }
    const asil = pending.name ?? state.model.name;
    for (const m of (answer.models || []).slice(0, 400)) {
      // Asıl modeli yedek diye önermek anlamsız: aynı model iki kez
      // denenmiş olurdu.
      if (m.id === asil) continue;
      const option = el("option");
      option.value = m.id;
      listNode.append(option);
    }
  }

  async function fillModels(slot) {
    let answer = {};
    // Henüz kaydedilmemiş sağlayıcı da sorulmalı: sağlayıcıya tıklandığında
    // değişiklik kaydedilmemiş oluyor ve katalog eski sunucudan geliyordu —
    // LM Studio'ya geçip OpenRouter'ın listesini görmek gibi.
    const pending = patch.model || {};
    try {
      answer = await (await fetch("/api/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_url: pending.base_url ?? state.model.base_url,
          provider: pending.provider ?? state.model.provider,
          api_key_env: pending.api_key_env ?? state.model.api_key_env,
        }),
      })).json();
    } catch { /* aşağıda ele alınıyor */ }

    const hint = slot.parentElement.querySelector(".field-hint");
    const found = answer.models || [];
    if (!found.length) {
      // Sunucu listeyi vermiyorsa elle yazma yolu açık kalıyor.
      if (hint) {
        const why = answer.error ? (" — " + answer.error) : "";
        const base = ((patch.model || {}).base_url ?? state.model.base_url)
          ? t("Sunucuya ulaşılamadı ya da liste vermiyor — kimliği elle yaz")
          : t("Sunucu liste vermiyor — kimliği elle yaz");
        hint.textContent = base + why;
      }
      return;
    }

    let chosen = (patch.model || {}).name ?? state.model.name;
    // Sağlayıcı yeni değiştiyse ad boş: kataloğun ilki seçiliyor. Boş ad
    // kaydetmek çalışmayan bir yapılandırma demek.
    if (!chosen) {
      chosen = found[0].id;
      set("model", "name", chosen);
      set("model", "can_think", null);
      set("model", "vision", null);
      if (chosen !== "oto") adoptCaps(found[0]);
      saveSoon(200);   // sağlayıcı değişiminin ikinci yarısı: ad da gitsin
    }
    // Native <select> yerine ARAMA + TIKLANABİLİR LİSTE. Neden: 400+ modelde
    // native select süzülünce ilk seçenek kendiliğinden "seçili" gelir ama
    // "change" olayı atmaz (zaten seçili), üstüne tıklamak da bir şey
    // değiştirmez → kullanıcı aradığı modeli görür ama SEÇEMEZ, elle yazmak
    // zorunda kalırdı ("burada bozulmuş, seçemiyorum modeli"). Liste satırı
    // ise apaçık bir tıklama: seçileni set eder, işaretler, ipucunu günceller.
    let selected = chosen;

    const search = el("input", "input-text");
    search.type = "search";
    search.placeholder = found.length + t(" model içinde ara…");

    const list = el("div", "model-list");

    const manual = el("button", "model-manual");
    manual.type = "button";
    manual.textContent = t("Kimliği elle yaz…");
    manual.addEventListener("click", () => {
      slot.textContent = "";
      const t = applyOnChange(text(selected, (v) => set("model", "name", v.trim())));
      slot.append(t);
      t.focus();
    });

    function pick(id) {
      selected = id;
      set("model", "name", id);   // seçim beklemedeki yapılandırmaya yazılır
      set("model", "can_think", null);
      set("model", "vision", null);
      if (id !== "oto") adoptCaps(found.find((x) => x.id === id));
      saveSoon();                 // ve ANINDA uygulanır — Kaydet'e inmek yok
      note(id);
      renderList();               // işareti taşı
    }

    function renderList() {
      const needle = search.value.trim().toLowerCase();
      const matched = needle
        ? found.filter((m) => (m.id + " " + (m.name || "")).toLowerCase().includes(needle))
        : found;
      list.textContent = "";
      if (!matched.length) {
        list.append(el("div", "model-empty", t("Eşleşen model yok")));
        return;
      }
      let shown = 0;
      let selVisible = false;
      for (const m of matched) {
        if (shown >= 200) {   // 400+ modelde DOM'u şişirme; arama daraltıyor
          list.append(el("div", "model-more",
            (matched.length - 200) + t(" model daha — aramayı daralt")));
          break;
        }
        const on = m.id === selected;
        selVisible = selVisible || on;
        const row = el("button", "model-row" + (on ? " on" : ""));
        row.type = "button";
        row.append(el("span", "model-row-id", m.id));
        if (m.name && m.name !== m.id) row.append(el("span", "model-row-note", m.name));
        row.addEventListener("click", () => pick(m.id));
        list.append(row);
        // Seçili satır görünür değilse (uzun listede aşağıda) ona kaydır.
        if (on) requestAnimationFrame(() => row.scrollIntoView({ block: "nearest" }));
        shown++;
      }
    }

    search.addEventListener("input", renderList);

    slot.textContent = "";
    slot.append(search, list, manual);
    renderList();
    note(selected);

    // Modelin ne yapabildiği seçimin altında yazıyor: görüntü kabul etmeyen
    // bir modelde kamerayı açmanın anlamı yok. Katalogda yoksa uydurulmaz.
    function note(id) {
      if (!hint) return;
      // Oto: gerçek bir model kimliği değil, ücretsiz havuzla çalışan kip.
      // Not YALNIZ OpenRouter'da (Oto zaten yalnız orada listeleniyor).
      if (id === "oto" && (patch.provider || state.provider) === "openrouter") {
        hint.textContent = t(OTO_NOTU);
        return;
      }
      const m = found.find((x) => x.id === id);
      if (!m) { hint.textContent = found.length + t(" model"); return; }

      const can = [];
      if (m.tools) can.push(t("araç kullanır"));
      if (m.vision === true) can.push(t("görüntü okur"));
      else if (m.vision === false) can.push(t("görüntü yok"));
      if (m.thinking === true) can.push(t("düşünür"));
      else if (m.thinking === false) can.push(t("düşünmez"));
      const parts = [];
      if (m.max_context !== undefined) {
        parts.push(t("En fazla ") + m.max_context.toLocaleString("tr-TR") + t(" token"));
      }
      if (can.length) parts.push(can.join(" · "));
      if (Array.isArray(m.loaded)) {
        const loaded = m.loaded.map((i) => i.context.toLocaleString("tr-TR")).join(", ");
        parts.push(loaded ? t("şu an yüklü: ") + loaded : t("yüklü değil"));
      }
      hint.textContent = parts.length ? parts.join(" · ") : found.length + t(" model");
    }
  }

  // Katalog ya da Algıla yanıtındaki bilinen yetenekler. Eksik alan
  // dokunulmaz — sağlayıcı söylemediyse varsayılan uydurulmaz.
  function adoptCaps(m) {
    if (!m) return;
    adoptAnswer({
      window: m.max_context,
      thinking: m.thinking,
      vision: m.vision,
    });
  }

  function adoptAnswer(answer) {
    let got = false;
    if (typeof answer.window === "number" && answer.window > 0) {
      set("model", "context_window", answer.window);
      const win = document.getElementById("model-window");
      if (win) win.value = answer.window;
      got = true;
    }
    if (answer.thinking !== undefined) {
      set("model", "can_think", !!answer.thinking);
      set("model", "thinking", !!answer.thinking);
      const box = document.getElementById("model-thinking");
      if (box) box.checked = !!answer.thinking;
      got = true;
    }
    if (answer.vision !== undefined) {
      set("model", "vision", !!answer.vision);
      got = true;
    }
    return got;
  }

  // Anahtarlar / Bağlam ayrı sekme değil: seçili sağlayıcıyla Model'de.

  async function loadRules(box, body) {
    let answer = {};
    try {
      answer = await (await fetch("/api/rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || { action: "list" }),
      })).json();
    } catch {
      box.textContent = "";
      box.append(el("p", "pane-note bad", t("Kurallar okunamadi")));
      return;
    }
    if (answer.error) say(answer.error, true);
    drawRules(box, answer);
  }

  function drawRules(box, data) {
    box.textContent = "";

    for (const side of ["allow", "deny"]) {
      const list = data[side] || [];
      const title = side === "allow" ? t("İzin verilenler") : t("Yasaklananlar");
      box.append(el("div", "rules-title " + side, title + " (" + list.length + ")"));

      if (!list.length) {
        box.append(el("p", "rules-empty", side === "allow"
          ? t("Hic kural yok — her sey kipe gore soruluyor")
          : t("Hic kural yok")));
      }

      for (const rule of list) {
        const row = el("div", "rule " + side);
        row.append(el("code", null, rule));
        const drop = el("button", "rule-drop", "×");
        drop.type = "button";
        drop.title = t("Kurali kaldir");
        drop.addEventListener("click", () =>
          loadRules(box, { action: "remove", side, rule }));
        row.append(drop);
        box.append(row);
      }

      const add = el("div", "rule-add");
      const input = el("input", "input-text");
      input.type = "text";
      input.placeholder = side === "allow" ? "shell:git *" : "shell:rm -rf *";
      const go = el("button", "rule-go", t("Ekle"));
      go.type = "button";
      const submit = () => {
        if (!input.value.trim()) return;
        loadRules(box, { action: "add", side, rule: input.value.trim() });
      };
      go.addEventListener("click", submit);
      input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") submit(); });
      add.append(input, go);
      box.append(add);
    }
  }

  // --- posta ------------------------------------------------------------
  //
  // Kimlik bilgileri API anahtarlariyla ayni dosyada duruyor ve bu sayfaya
  // geri gonderilmiyor.

  function drawMail() {
    const pane = panes.mail;
    pane.textContent = "";
    head(pane, "Posta", "Posta okuma ve gönderme hesabı.");

    for (const entry of state.mail) {
      const node = el("input", "input-text");
      node.type = entry.secret === "1" ? "password" : "text";
      node.placeholder = entry.filled ? t("Kayitli — degistirmek icin yaz") : entry.hint;
      node.autocomplete = "off";
      node.addEventListener("input", () => {
        patch.keys = patch.keys || {};
        patch.keys[entry.env] = node.value;
        say("Kaydedilmedi");
      });
      pane.append(field(entry.label + (entry.filled ? " ✓" : ""), entry.hint, node));
    }

    pane.append(el("p", "pane-note",
      t("Hesap tanimlaninca `mail_read` ve `mail_send` araclari aciliyor — " +
      "yeniden baslatmak gerekiyor. Gonderme her seferinde onaydan geciyor: " +
      "geri alinamaz ve disariya aciliyor.")));

    pane.append(el("p", "pane-note",
      t("Gelen posta guvenilmeyen bir kaynak. Govdesinde ajana verilmis gibi " +
      "gorunen bir talimat varsa uygulanmiyor, sana soyleniyor.")));
  }

  // --- gorevler ---------------------------------------------------------
  //
  // Ajanin kurdugu bir otomasyonun kullanicidan gizli calismasi kabul
  // edilemez: ne oldugu, ne zaman calistigi ve en son ne oldugu burada.

  async function loadTasks(body) {
    let answer = {};
    try {
      answer = await (await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || { action: "list" }),
      })).json();
    } catch {
      panes.tasks.textContent = "";
      panes.tasks.append(el("p", "pane-note bad", t("Gorevler okunamadi")));
      return;
    }
    if (answer.error) say(answer.error, true);
    drawTasks(answer.tasks || []);
  }

  function drawTasks(tasks) {
    const pane = panes.tasks;
    pane.textContent = "";
    head(pane, "Görevler",
      "Zamanlanmış işler — asıl yüzey ana ekran Görevler menüsü (liste + koşu geçmişi).");
    const openMain = el("button", "job-act", t("Ana ekranda aç"));
    openMain.type = "button";
    openMain.addEventListener("click", () => {
      if (window.JobsPanel) JobsPanel.open();
      // Ayarlar panelini kapat
      const settings = document.getElementById("settings");
      if (settings) settings.hidden = true;
    });
    pane.append(openMain);

    const list = el("div", "rows");
    for (const task of tasks) {
      const kosuyor = task.last_status === "koşuyor";
      const line = row({
        name: task.title,
        desc: task.prompt,
        meta: kosuyor
          ? t("Bu görev şu an çalışıyor")
          : (task.enabled ? task.describe + " · " + short(task.next_run) : t("durdu")),
        state: kosuyor ? "live" : (task.enabled ? "" : "off"),
        click: true,
        acts: [
          [t("Çalıştır"), () => loadTasks({ action: "run", id: task.id })],
          [task.enabled ? t("Durdur") : t("Sürdür"),
            () => loadTasks({ action: "update", id: task.id, enabled: !task.enabled })],
          [t("Sil"), () => loadTasks({ action: "remove", id: task.id }), true],
        ],
      });
      line.addEventListener("click", () => detail(line, (box) => {
        box.append(editTaskForm(task));
        const durum = el("p", "job-prompt dim");
        const parcalar = [];
        if (kosuyor) parcalar.push(t("Bu görev şu an çalışıyor"));
        else if (task.enabled) parcalar.push(t("Sırada: ") + short(task.next_run));
        else parcalar.push(t("Durduruldu"));
        if (task.last_run) parcalar.push(t("Son koşu: ") + short(task.last_run));
        if (task.last_status && task.last_status !== "koşuyor") {
          parcalar.push(t("Son: ") + task.last_status);
        }
        durum.textContent = parcalar.join("  ·  ");
        box.append(durum);
        if (task.last_child_id) {
          const ac = el("button", "job-act", t("Raporu aç"));
          ac.type = "button";
          ac.addEventListener("click", (ev) => {
            ev.stopPropagation();
            if (typeof Viewer !== "undefined" && Viewer.page) {
              Viewer.page("/gorev-rapor/" + encodeURIComponent(task.last_child_id) + "/",
                          task.title || task.last_child_id);
            }
          });
          box.append(ac);
        }
      }, "edit"));
      list.append(line);
    }

    const adder = row({ name: t("＋ Yeni görev"), state: "off", click: true });
    adder.addEventListener("click", () => detail(adder, (box) => box.append(newTaskForm()), "new"));
    list.append(adder);
    pane.append(list);

    if (!tasks.length) {
      pane.append(el("p", "pane-note",
        t("Kurulu görev yok. Yukarıdan ekleyebilir ya da ajana söyleyebilirsin: " +
        "\"her sabah 9'da borsayı kontrol et\".")));
    }
  }

  function action(label, run, risky) {
    const node = el("button", "job-act" + (risky ? " risky" : ""), label);
    node.type = "button";
    node.addEventListener("click", run);
    return node;
  }

  // Uzun ISO damgasi okunmuyor; gun ve saat yeter.
  function short(stamp) {
    if (!stamp) return "—";
    const when = new Date(stamp);
    return isNaN(when) ? stamp : when.toLocaleString("tr-TR", {
      day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    });
  }

  function newTaskForm() {
    // Satir detayinin icine gomuluyor; kendi kart cercevesi tasimiyor.
    const box = el("div");
    const draft = { action: "add", kind: "every", every_s: 3600, at: "09:00" };

    box.append(field("Yeni gorev", "", text("", (v) => (draft.title = v), t("Ad"))));
    box.append(field("Ne yapsin", "Tetiklendiginde ajana gonderilecek metin",
                     text("", (v) => (draft.prompt = v), t("Her sabah borsayi kontrol et ve ozetle"))));

    const kind = el("select", "input-text");
    kind.append(option("every", t("Belirli araliklarla"), true));
    kind.append(option("daily", t("Her gun belirli saatte")));
    box.append(field("Tekrar", "", kind));

    const detail = el("div", "with-action");
    const every = number(60, (v) => (draft.every_s = Number(v) * 60));
    const at = text("09:00", (v) => (draft.at = v));
    detail.append(every, el("span", "field-hint", t("Dakikada bir")));
    box.append(field("Aralik", "", detail));

    kind.addEventListener("change", () => {
      draft.kind = kind.value;
      detail.textContent = "";
      if (kind.value === "daily") detail.append(at, el("span", "field-hint", t("Saat (HH:MM)")));
      else detail.append(every, el("span", "field-hint", t("Dakikada bir")));
    });

    const add = el("button", "job-act add", t("Kur"));
    add.type = "button";
    add.addEventListener("click", () => {
      if (!draft.prompt) { say("Gorev metni bos", true); return; }
      loadTasks(draft);
    });
    box.append(add);
    return box;
  }

  function editTaskForm(task) {
    const box = el("div");
    const draft = {
      action: "update",
      id: task.id,
      title: task.title || "",
      prompt: task.prompt || "",
      kind: task.kind || "every",
      every_s: Number(task.every_s) || 3600,
      at: task.at || "09:00",
    };

    box.append(field("Ad", "", text(draft.title, (v) => (draft.title = v), t("Ad"))));
    box.append(field("Ne yapsın", "Tetiklenince yardımcıya gidecek metin (sohbet değil)",
                     text(draft.prompt, (v) => (draft.prompt = v))));

    const kind = el("select", "input-text");
    kind.append(option("every", t("Belirli araliklarla"), draft.kind === "every"));
    kind.append(option("daily", t("Her gun belirli saatte"), draft.kind === "daily"));
    box.append(field("Tekrar", "", kind));

    const slot = el("div", "with-action");
    const every = number(Math.max(1, Math.round(draft.every_s / 60)),
                         (v) => (draft.every_s = Number(v) * 60));
    const at = text(draft.at, (v) => (draft.at = v));
    function fillSlot() {
      slot.textContent = "";
      if (draft.kind === "daily") {
        slot.append(at, el("span", "field-hint", t("Saat (HH:MM)")));
      } else {
        slot.append(every, el("span", "field-hint", t("Dakikada bir")));
      }
    }
    fillSlot();
    box.append(field("Aralık", "", slot));
    kind.addEventListener("change", () => {
      draft.kind = kind.value;
      fillSlot();
    });

    const save = el("button", "job-act add", t("Kaydet"));
    save.type = "button";
    save.addEventListener("click", () => {
      if (!String(draft.prompt || "").trim()) { say("Gorev metni bos", true); return; }
      loadTasks(draft);
    });
    box.append(save);
    return box;
  }

  // --- ses --------------------------------------------------------------
  //
  // Isletim sisteminin kendi sentezleyicisi robot gibi konusuyor; buradaki
  // sesler sinirsel ve gercek insan tonunda. Bedeli internet.

  function drawVoice() {
    const pane = panes.voice;
    pane.textContent = "";
    head(pane, "Ses", "neo'nun sesi: açık/kapalı, ton ve karakter.");

    if (!state.voice.available) {
      // Kurulu duzende pip onermek anlamsiz: paket kuruluma dahil,
      // yoklugu eksik/bozuk kurulum demek — sihirbaz onarir.
      pane.append(el("p", "pane-note bad", t(state.installed
        ? "Ses paketi bu kurulumda eksik gorunuyor. Kurulum sihirbazini yeniden calistirmak eksigi onarir."
        : "Ses paketi kurulu degil. Kurmak icin: pip install \"neocp[voice]\"")));
      return;
    }

    pane.append(field(
      "Sesli konus",
      "Cevaplar cumle cumle sesletilir; ses bulutta uretiliyor, internet gerekiyor",
      toggleBox((patch.voice || {}).enabled ?? state.voice.enabled,
                (v) => set("voice", "enabled", v))
    ));

    const picker = el("select", "input-text");
    picker.append(option(state.voice.name, state.voice.name));
    picker.addEventListener("change", () => set("voice", "name", picker.value));
    pane.append(field("Ses", "Yukleniyor…", picker));
    fillVoices(picker);

    pane.append(field(
      "Hiz",
      "edge-tts bicimi: +0%, -10%, +20%. Hiz kisiye gore cok degisiyor",
      text((patch.voice || {}).rate ?? state.voice.rate,
           (v) => set("voice", "rate", v.trim()), "+0%")
    ));

    pane.append(field(
      "Perde",
      "+0Hz, -5Hz, +8Hz",
      text((patch.voice || {}).pitch ?? state.voice.pitch,
           (v) => set("voice", "pitch", v.trim()), "+0Hz")
    ));

    // Karakter: sentezleyici gercek bir insan sesi uretiyor ve tek basina
    // duz duruyor. Turkce seslerde SSML duygu stili de yok (hepsi
    // "General"), yani uretim tarafindan alinabilecek bir sey kalmiyor.
    // Bu katman sesin ustune biniyor ve tarayicida uygulaniyor.
    const current = (patch.voice || {}).character ?? state.voice.character ?? 0;
    const slider = el("input");
    slider.type = "range";
    slider.className = "input-range";
    slider.min = "0"; slider.max = "1"; slider.step = "0.05";
    slider.value = String(current);

    const shown = el("span", "field-hint", t(describeCharacter(current)));
    slider.addEventListener("input", () => {
      shown.textContent = t(describeCharacter(Number(slider.value)));
      set("voice", "character", Number(slider.value));
    });

    const row = el("div", "with-action");
    row.append(slider, shown);
    pane.append(field(
      "Karakter",
      "Solda insan, sagda makine. Ortada bir yerde: ne santral kaydi ne de " +
      "birebir insan taklidi",
      row
    ));

    pane.append(el("p", "pane-note",
      t("Tonlama cumle cumle degisiyor: soru yukselir, uyari alcalir, kisa " +
      "cevap canlanir. Kod bloklari, tablolar ve adresler sesletilmiyor — " +
      "sesli okunmasi anlamsiz olan seyler metinde kaliyor.")));
  }

  function describeCharacter(value) {
    if (value < 0.08) return "Saf insan sesi";
    if (value < 0.3) return "Hafif yapay";
    if (value < 0.6) return "İnsan-makine karisimi";
    if (value < 0.85) return "Belirgin yapay zeka";
    return "Tamamen makine";
  }

  function option(value, label, selected) {
    const node = el("option", null, label);
    node.value = value;
    if (selected) node.selected = true;
    return node;
  }

  async function fillVoices(picker) {
    let answer = {};
    try {
      answer = await (await fetch("/api/voices", { method: "POST" })).json();
    } catch { /* asagida ele aliniyor */ }

    const list = answer.voices || [];
    const hint = picker.parentElement.querySelector(".field-hint");
    if (!list.length) {
      if (hint) hint.textContent = t("Ses listesi alinamadi — kayitli ses kullaniliyor");
      return;
    }
    if (hint) hint.textContent = list.length + t(" ses");

    const chosen = (patch.voice || {}).name ?? state.voice.name;
    picker.textContent = "";
    for (const v of list) {
      const label = v.id + (v.gender ? " · " + v.gender.toLowerCase() : "") +
                    (v.tone ? " · " + v.tone.toLowerCase() : "");
      picker.append(option(v.id, label, v.id === chosen));
    }
  }

  // --- mikrofon ---------------------------------------------------------
  //
  // Tanima sunucuda ve yerel: ses bilgisayardan cikmiyor. Tarayicinin kendi
  // SpeechRecognition API'si kullanilmiyor — WebView2'de yok, oldugu yerde
  // de sesi Google'a gonderiyor.

  function drawHearing() {
    const pane = panes.hearing;
    pane.textContent = "";
    head(pane, "Mikrofon", "Dinleme ve uyandırma sözü.");

    if (!state.listen.available) {
      // Kuruluda dogru oneri sihirbazdaki bilesen — pip degil.
      pane.append(el("p", "pane-note bad", t(state.installed
        ? "Dinleme bu kuruluma dahil edilmemis. Kurulum sihirbazini yeniden calistirip 'Dinleme (mikrofon)' bilesenini isaretleyerek ekleyebilirsin."
        : "Tanima paketi kurulu degil. Kurmak icin: pip install \"neocp[listen]\"")));
      return;
    }

    // Makinede mikrofon yoksa düğmeyi açılabilir göstermek, çalışmayan
    // bir şeye tıklatmak demek — ve neden çalışmadığı hiçbir yerde yazmaz.
    const micBox = toggleBox((patch.listen || {}).enabled ?? state.listen.enabled,
                             (v) => set("listen", "enabled", v));
    const hasMic = (state.hardware || {}).microphone !== false;
    if (!hasMic) { micBox.disabled = true; micBox.checked = false; }

    pane.append(field(
      "Mikrofon",
      hasMic
        ? "Acinca yazma satirinda bas-konus dugmesi cikar; ses bilgisayardan cikmaz"
        : "Bu makinede giris yapan bir ses aygiti bulunamadi",
      micBox
    ));
    if (!hasMic) return;

    pane.append(field(
      "Uyandirma sozu",
      "Surekli dinleme acikken aranan kelime. Bos birakirsan yalnizca " +
      "bas-konus calisir — mikrofon surekli acik kalmaz",
      text((patch.listen || {}).wake ?? state.listen.wake,
           (v) => set("listen", "wake", v.trim()), "neo")
    ));

    pane.append(field(
      "Serbest dinleme",
      "Acikken uyandirma sozu hic gerekmiyor: duyulan her cumle neo'ya " +
      "gidiyor. Evde tek basina calisiyorsan dogrusu bu — \"hava nasil?\" " +
      "derken baska kime soruyor olabilirsin ki. Odada televizyon varsa ya " +
      "da baskalariyla konusuyorsan kapali birak",
      toggleBox((patch.listen || {}).open ?? state.listen.open,
                (v) => set("listen", "open", v))
    ));

    pane.append(el("p", "pane-note",
      t("Kapaliyken bile her cumlede adini soylemek gerekmiyor: bir kez " +
      "\"neo\" deyip baslattiktan sonra karsilik verdigi her seferde " +
      "sohbet 3 dakika daha acik kaliyor.")));

    pane.append(field(
      "Alan sozlugu",
      "Tanicinin bilmedigi ozel kelimeler: cihaz adlari, marka, jargon. " +
      "Virgullu liste. Cihaz ve yetenek adlari kendiliginden ekleniyor; " +
      "buraya yazdiklarin onlara eklenir",
      text((patch.listen || {}).vocab ?? state.listen.vocab,
           (v) => set("listen", "vocab", v), t("Omron, Envest, debimetre"))
    ));

    const size = el("select", "input-text");
    const chosen = (patch.listen || {}).size ?? state.listen.size;
    const NOTE = { tiny: "en hizli, en az dogru (~75 MB)", base: "orta (~145 MB)",
                   small: "hizli (~500 MB)", medium: "iyi (~1.5 GB)",
                   "large-v3": "en dogru; ekran karti ister (~3 GB)" };
    for (const name of state.listen.sizes) {
      size.append(option(name, name + " — " + t(NOTE[name] || ""), name === chosen));
    }
    size.addEventListener("change", () => set("listen", "size", size.value));
    pane.append(field("Tanima modeli", "İlk kullanimda indirilir, sonra diskte kalir", size));

    pane.append(field(
      "Dil",
      "Turkce icin 'tr'. Bos birakmak tahmine birakmak demek ve gozle gorulur " +
      "bicimde kotu sonuc veriyor",
      text((patch.listen || {}).language ?? state.listen.language,
           (v) => set("listen", "language", v.trim()), "tr")
    ));

    pane.append(el("p", "pane-note",
      t("Bas-konus sonucu dogrudan gonderilmiyor, yazma satirina dusuyor — " +
      "tanima her zaman dogru degil ve duzeltme sansin olmali.")));
  }

  // --- izlenen kameralar ------------------------------------------------
  //
  // Model her kareye bakmiyor: hareket yerelde olculuyor ve yalnizca bir sey
  // degistiginde soru soruluyor. Bos bir odada saatlerce hicbir istek gitmiyor.

  async function loadCameras(body) {
    let answer = {};
    try {
      answer = await (await fetch("/api/cameras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || { action: "list" }),
      })).json();
    } catch {
      panes.eyes.textContent = "";
      panes.eyes.append(el("p", "pane-note bad", t("kameralar okunamadi")));
      return;
    }
    drawCameras(answer);
  }

  function drawCameras(data) {
    const pane = panes.eyes;
    pane.textContent = "";
    head(pane, "Kameralar", "Kamera aç/kapa ve izlenen kameralar.");

    pane.append(field(
      "Kamera",
      "Üstteki kamera ikonuyla aynı anahtar. Açınca LED yanar ve önizleme akar; kapatınca aygıt bırakılır.",
      toggleBox((patch.camera || {}).enabled ?? state.camera.enabled,
                (v) => { set("camera", "enabled", v); saveSoon(); })
    ));
    pane.append(el("p", "pane-note",
      t("NVIDIA GPU varsa karedeki nesneler yerelde okunur (~400 MB VRAM); sohbet modeline resim değil kısa metin gider. GPU yoksa yalnız önizleme — sorduğunda kesit alınır. Bu ağır gelirse ikondan kapat.")));

    if (!data.available) {
      pane.append(el("p", "pane-note bad", t((state && state.installed)
        ? "Kamera izleme bu kuruluma dahil edilmemis. Kurulum sihirbazini yeniden calistirip 'Kamera izleme' bilesenini isaretleyerek ekleyebilirsin."
        : "Goruntu paketi kurulu degil. Kurmak icin: pip install \"neocp[watch]\"")));
      return;
    }

    const cameras = data.cameras || [];

    const list = el("div", "rows");
    for (const cam of cameras) {
      const line = row({
        name: cam.name,
        desc: cam.source + " · " + (cam.ask || t("genel bakış")),
        meta: "%" + Math.round(cam.sensitivity * 100) + " · " + cam.cooldown_s + t(" sn"),
        state: cam.enabled ? "" : "off",
        acts: [
          [cam.enabled ? t("Durdur") : t("Sürdür"),
            () => loadCameras({ action: "update", id: cam.id, enabled: !cam.enabled })],
          [t("Sil"), () => loadCameras({ action: "remove", id: cam.id }), true],
        ],
      });
      list.append(line);
    }

    const adder = row({ name: t("＋ Yeni kamera"), state: "off", click: true });
    adder.addEventListener("click", () => detail(adder, (box) => box.append(newCameraForm())));
    list.append(adder);
    pane.append(list);

    if (!cameras.length) {
      pane.append(el("p", "pane-note",
        t("İzlenen kamera yok. Yerel kamera için kaynak \"0\", ağ kamerası için " +
        "tam adres yaz (rtsp://... ya da http://...).")));
    }
    pane.append(el("p", "pane-note",
      t("Değişiklikler yeniden başlatınca geçerli olur: izleyici kendi " +
      "thread'inde dönüyor ve çalışırken kamera eklemek açık bir akışın " +
      "ortasına girmek demek.")));
  }

  function newCameraForm() {
    const box = el("div");
    const draft = {
      action: "add", kind: "usb", source: "0", host: "", port: 0, path: "",
      user: "", password: "", sensitivity: 0.06, cooldown_s: 60, analyze: true,
    };

    box.append(field("Yeni kamera", "", text("", (v) => (draft.name = v), t("Giris kapisi"))));
    const tur = el("select", "field-input");
    for (const [v, l] of [["usb", t("Bilgisayar")], ["rtsp", "RTSP (IP)"], ["http", "HTTP / MJPEG"]]) {
      const o = el("option", null, l); o.value = v; tur.append(o);
    }
    tur.addEventListener("change", () => { draft.kind = tur.value; });
    box.append(field("Tür", "", tur));
    box.append(field("Kaynak / indeks", "Bilgisayar kamerası için 0 · ağ için host aşağıda",
                     text("0", (v) => (draft.source = v), "0")));
    box.append(field("Host", "IP veya ad (RTSP/HTTP)",
                     text("", (v) => (draft.host = v), "192.168.1.10")));
    box.append(field("Port / yol", "", text("", (v) => {
      const p = v.split("/");
      draft.port = parseInt(p[0], 10) || 0;
      draft.path = v.includes("/") ? "/" + v.split("/").slice(1).join("/") : "";
    }, "554/stream")));
    box.append(field("Kullanıcı", "", text("", (v) => (draft.user = v), "admin")));
    const sifre = el("input", "field-input");
    sifre.type = "password";
    sifre.placeholder = t("şifre");
    sifre.addEventListener("input", () => { draft.password = sifre.value; });
    box.append(field("Şifre", "Yalnız bu makinede cameras.json içinde durur", sifre));
    box.append(field("Ne sorsun", "Hareket goruldugunde modele gidecek soru",
                     text("", (v) => (draft.ask = v), t("Kapi acik kalmis mi bak"))));

    const detail = el("div", "with-action");
    detail.append(number(6, (v) => (draft.sensitivity = Number(v) / 100)),
                  el("span", "field-hint", t("% duyarlilik")));
    detail.append(number(60, (v) => (draft.cooldown_s = Number(v))),
                  el("span", "field-hint", t("sn sessizlik")));
    box.append(field("Esikler", "", detail));

    const add = el("button", "job-act add", t("Ekle"));
    add.type = "button";
    add.addEventListener("click", () => {
      if (!draft.name) { say("Kameraya bir ad ver", true); return; }
      loadCameras(draft);
    });
    box.append(add);
    return box;
  }

  // --- cihazlar ---------------------------------------------------------
  //
  // Bir PLC, bir kamera, bir seri porttaki kol, bir MCP sunucusu. Hepsi
  // birbirinden çok farklı ama üç şeyleri ortak: ne oldukları, nasıl
  // bağlanılacağı, neresine dokunulacağı. Biçim yalnızca onu sabitliyor.
  //
  // Ajan da aynı dosyalara yazıyor (`device` aracı). İki ayrı depo tutmak,
  // buradan eklenen bir PLC'yi ajanın görmemesi demekti.

  const DEVICE_TEMPLATE = {
    id: "kapi-plc",
    name: "kapı PLC",
    kind: "plc",
    summary: "atölye kapısını süren PLC",
    link: { protocol: "modbus-tcp", host: "192.168.1.50", port: 502 },
    points: [
      { name: "kapı aç", address: "%QX0.1", access: "write", note: "1 yazınca açılıyor" }
    ],
    skills: [],
    notes: ""
  };

  async function loadDevices(body) {
    let answer = {};
    try {
      answer = await (await fetch("/api/devices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || { action: "list" }),
      })).json();
    } catch {
      panes.devices.textContent = "";
      panes.devices.append(el("p", "pane-note bad", t("Cihazlar okunamadı")));
      return;
    }
    if (answer.ok === false) say(answer.error || "Kaydedilemedi", true);
    drawDevices(answer);
  }

  function drawDevices(data) {
    const pane = panes.devices;
    pane.textContent = "";
    head(pane, "Varlıklar", "neo'nun tanıdığı cihazlar ve sistemler.");

    const list = el("div", "rows");
    for (const device of data.devices || []) list.append(deviceRow(device));

    const adder = row({ name: t("＋ Yeni varlık"), state: "off", click: true });
    adder.addEventListener("click", () => detail(adder, (box) => {
      box.append(el("p", "pane-note",
        t("Örneği kendi varlığına göre değiştir. Bilmediğin bir alanı boş " +
        "bırak — yanlış bir adres fiziksel bir sonuç doğuruyor.")));
      box.append(jsonEditor(DEVICE_TEMPLATE));
    }));
    list.append(adder);
    pane.append(list);

    if ((data.broken || []).length) {
      pane.append(el("p", "pane-note bad", t("Okunamayan dosyalar:\n") + data.broken.join("\n")));
    }
    if (!(data.devices || []).length) {
      pane.append(el("p", "pane-note",
        t("Kayıtlı varlık yok. Bir PLC, bir kapı, bir ağ kamerası, başka bir " +
        "bilgisayar — neo'nun tanıdığı her şey buraya yazılır. Elle " +
        "ekleyebilirsin; neo da bir varlık tarif ettiğinde kendisi kaydediyor.")));
    }
    pane.append(el("p", "pane-note",
      t("Varlık kaydı tek başına bir şey yapmıyor: nereye bağlanılacağını " +
      "söylüyor. İşi yapan şey ona bağlanan yetenek — neo'ya \"bu varlık için " +
      "bir yetenek yaz\" dediğinde kendisi yazıyor.")));
  }

  document.addEventListener("neo:devices", () => loadDevices());

  function deviceRow(device) {
    const where = Object.entries(device.link || {})
      .map(([key, value]) => key + "=" + value).join("  ");
    const line = row({
      name: device.name,
      desc: device.summary || where,
      meta: device.kind + " · " + (device.points || []).length + t(" nokta"),
      click: true,
      acts: [
        [t("Düzenle"), () => detail(line, (box) => box.append(jsonEditor(device)), "edit")],
        [t("Sil"), () => loadDevices({ action: "remove", id: device.id }), true],
      ],
    });
    // Satira tiklayinca: baglanti, adresler, bagli yetenekler — asil bilgi.
    line.addEventListener("click", () => detail(line, (box) => {
      if (where) box.append(el("p", "job-prompt dim", where));
      for (const point of device.points || []) {
        box.append(el("p", "job-prompt dim", "· " + point.name +
          (point.address ? "  [" + point.address + "]" : "") +
          "  (" + (point.access || "read") + ")" +
          (point.note ? " — " + point.note : "")));
      }
      box.append(el("p", "job-prompt dim",
        ((device.skills || []).length
          ? t("Yetenek: ") + device.skills.join(", ")
          : t("Bağlı yetenek yok")) +
        t("  ·  Ekleyen: ") + (device.source || "neo") +
        "  ·  " + device.id));
    }, "info"));
    return line;
  }

  // Ham JSON düzenleyici. `link` ve `points` bilerek şemasız — her
  // protokolün kendi alanları var ve hepsini alan alan forma dökmek ya
  // her cihaza uymayan bir kalıp ya da otuz satırlık bir form üretiyordu.
  function jsonEditor(device) {
    // Satir detayinin icine gomuluyor; kendi kart cercevesi tasimiyor.
    const box = el("div");
    const area = el("textarea", "input-text input-area");
    area.rows = 12;
    area.value = JSON.stringify(device, null, 2);
    box.append(area);

    const save = el("button", "job-act add", t("Kaydet"));
    save.type = "button";
    save.addEventListener("click", () => {
      let parsed;
      try {
        parsed = JSON.parse(area.value);
      } catch (err) {
        say(t("JSON okunamadı: ") + err.message, true);
        return;
      }
      loadDevices({ action: "save", device: parsed });
    });
    box.append(save);
    return box;
  }

  // --- yetenekler -------------------------------------------------------
  //
  // Ajanın kendine yazdığı betikler. Buradan silmek gerçekten siliyor:
  // işe yaramayan, yarım kalmış ya da ikinci kez yazılmış bir yetenek
  // (aynı işi yapan `modbus_oku` ve `modbus_read` gibi) birikiyor ve her
  // turda araç listesinde yer kaplıyor.

  async function loadSkills(body) {
    let answer = {};
    try {
      answer = await (await fetch("/api/skills", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || { action: "list" }),
      })).json();
    } catch {
      panes.skills.textContent = "";
      panes.skills.append(el("p", "pane-note bad", t("Yetenekler okunamadı")));
      return;
    }
    if (answer.ok === false) {
      say(answer.error || t("Yetenek kaydedilemedi"), true);
      // Listeyi yine çiz — kullanıcı bozulmuş hali görsün.
    }
    drawSkills(answer);
    if (typeof loadOrgans === "function") loadOrgans();
    // Oluştur → hemen kod editörü: ayrı "Düzenle" adımı yok.
    if (body && body.action === "new" && answer.ok !== false) {
      const name = String(body.name || "").trim().toLowerCase();
      const line = [...panes.skills.querySelectorAll(".row")].find((r) => {
        const n = r.querySelector(".row-name");
        return n && n.textContent === name;
      });
      if (line) editSkill(name, line);
    }
  }

  // --- kompakt satirlar -------------------------------------------------
  //
  // Kart yerine satir: kartlar uc kayitta guzeldi, on bes yetenekte sayfa
  // yonetilemez bir duvara donuyor. Bir kayit tek satir; detay tiklayinca
  // satirin altina acilir — sayfa yalnizca bakilan seye yer harcar.

  function row(opts) {
    const line = el("div", "row" + (opts.click ? " click" : "")
      + (opts.adder ? " adder" : "")
      + (opts.advanced ? " advanced" : "")
      + (opts.stay ? " stay" : ""));
    line.append(el("span", "row-dot" + (opts.state ? " " + opts.state : "")));
    if (opts.icon) line.append(opts.icon);
    line.append(el("b", "row-name", opts.name));
    line.append(el("span", "row-desc", opts.desc || ""));
    if (opts.meta) line.append(el("span", "row-meta", opts.meta));
    if (opts.acts && opts.acts.length) {
      const acts = el("span", "row-acts");
      for (const [label, run, risky] of opts.acts) {
        const button = el("button", "row-act" + (risky ? " risky" : ""), label);
        button.type = "button";
        button.addEventListener("click", (ev) => { ev.stopPropagation(); run(); });
        acts.append(button);
      }
      line.append(acts);
    }
    return line;
  }

  // Satirin altindaki detay kutusu. Ayni tur detaya ikinci tiklama kapatir;
  // farkli tur (bilgi acikken Duzenle gibi) oncekinin yerine gecer.
  function detail(line, build, kind) {
    const open = line.nextElementSibling;
    const opened = open && open.classList.contains("row-detail");
    const same = opened && (!kind || open.dataset.kind === kind);
    if (opened) {
      open.remove();
      line.classList.remove("open");
      if (same) return;
    }
    const box = el("div", "row-detail");
    if (kind) box.dataset.kind = kind;
    build(box);
    line.after(box);
    line.classList.add("open");
  }

  function confirmRow(line, message, onYes) {
    detail(line, (box) => {
      box.append(el("p", "pane-note", message));
      const yes = action(t("Evet, sil"), () => {
        box.remove();
        line.classList.remove("open");
        onYes();
      });
      yes.classList.add("risky");
      const no = action(t("Vazgeç"), () => {
        box.remove();
        line.classList.remove("open");
      });
      box.append(yes, no);
    }, "confirm");
  }

  function drawSkills(data) {
    const pane = panes.skills;
    pane.textContent = "";
    head(pane, "Skills",
      t("Neo'nun araç olarak yüklediği Python betikleri. Satıra tıkla → detay."));

    if (data.error) pane.append(el("p", "pane-note bad", data.error));

    const list = el("div", "rows");
    for (const skill of data.skills || []) {
      const line = row({
        name: skill.name,
        desc: (skill.description || "").split("\n")[0],
        stay: true,
        click: true,
        acts: [
          [t("Düzenle"), () => editSkill(skill.name, line, skill)],
          [t("Sil"), () => confirmRow(line,
            t("Bu yetenek dosyadan ve araç defterinden silinir. Geri gelmez."),
            () => loadSkills({ action: "remove", name: skill.name })), true],
        ],
      });
      line.title = skill.path;
      line.addEventListener("click", () => editSkill(skill.name, line, skill));
      list.append(line);
    }

    for (const problem of data.broken || []) {
      const line = row({ name: t("yüklenemedi"), desc: problem.split("\n")[0], state: "bad", stay: true });
      line.title = problem;
      list.append(line);
    }

    const adder = row({ name: t("＋ Yeni yetenek"), state: "off", click: true, adder: true });
    adder.addEventListener("click", () => detail(adder, (box) => {
      const nameBox = el("input", "input-text");
      nameBox.placeholder = t("ad — ör. rapor_ozeti");
      const descBox = el("input", "input-text");
      descBox.placeholder = t("ne işe yarar, ne zaman kullanılmalı");
      const codeBox = el("textarea", "input-text input-area");
      codeBox.rows = 8;
      codeBox.spellcheck = false;
      codeBox.placeholder = t("Python — NAME, DESCRIPTION, SCHEMA, run(args, ctx). Boşsa iskelet açılır.");
      const make = action(t("Oluştur"), () => {
        if (!nameBox.value.trim()) { say(t("Yeteneğe bir ad ver"), true); return; }
        const code = codeBox.value.trim();
        if (code) {
          loadSkills({ action: "write", name: nameBox.value.trim(), code: codeBox.value });
        } else {
          loadSkills({
            action: "new",
            name: nameBox.value.trim(),
            description: descBox.value.trim(),
          });
        }
      });
      make.classList.add("add");
      box.append(nameBox, descBox, codeBox, make);
      nameBox.focus();
    }));
    list.append(adder);
    pane.append(list);

    pane.append(el("p", "pane-note",
      t("Kaydedilen yetenek anında araç olarak yüklenir; silinen hem dosyadan " +
      "hem defterden gider. Standart yetenekler ilk açılışta gelir — silersen " +
      "geri gelmez. neo da iş sırasında kendine yetenek yazar.")));
  }

  // Skill detayı (Claude Code kalıbı): satıra tıklayınca önce KART —
  // ad, dosya, tam açıklama (docstring) ve eylemler. Ham kod duvarı
  // ancak "Kodu göster" denince açılır; Kaydet anında yükler.
  async function editSkill(name, line, meta) {
    const open = line.nextElementSibling;
    if (open && open.classList.contains("row-detail") && open.dataset.kind !== "confirm") {
      open.remove();
      line.classList.remove("open");
      return;
    }

    let answer = {};
    try {
      answer = await (await fetch("/api/skills", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "read", name }),
      })).json();
    } catch { say(t("Dosya okunamadı"), true); return; }
    if (!answer.ok) { say(answer.error || t("Dosya okunamadı"), true); return; }

    detail(line, (box) => {
      const kart = el("div", "skill-card");
      const bas = el("div", "skill-card-head");
      bas.append(el("b", "skill-card-name", name));
      if (meta && meta.path) bas.append(el("span", "skill-card-path", meta.path));
      kart.append(bas);
      const aciklama = (meta && meta.description) || "";
      kart.append(el("p", "skill-card-desc" + (aciklama ? "" : " empty"),
        aciklama || t("Açıklama yok — dosyanın başındaki docstring buraya düşer.")));
      box.append(kart);

      const area = el("textarea", "input-text input-area");
      area.rows = 16;
      area.spellcheck = false;
      area.value = answer.code || "";
      area.hidden = true;
      const keep = action(t("Kaydet ve yükle"), () =>
        loadSkills({ action: "write", name, code: area.value }));
      keep.classList.add("add");
      keep.hidden = true;

      const goster = action(t("Kodu göster"), () => {
        const acik = area.hidden;
        area.hidden = !acik;
        keep.hidden = !acik;
        goster.textContent = acik ? t("Kodu gizle") : t("Kodu göster");
        if (acik) area.focus();
      });
      box.append(goster, area, keep);
    }, "edit");
  }

  // --- bağlantılar (MCP) ------------------------------------------------
  //
  // Dış araç sunucuları. Biçim Claude Code'un `mcpServers` biçimiyle aynı:
  // başka bir istemci için yazılmış bir tanım buraya olduğu gibi
  // yapıştırılabilir. Gizli değer dosyaya yazılmaz — "${AD}" yazılır,
  // değeri Anahtarlar sekmesine girilir, bağlanırken doldurulur.

  async function loadConnectors(body) {
    const pane = panes.connectors;
    if (!pane.childElementCount) pane.append(el("p", "pane-note", t("Yükleniyor…")));
    if (body) say("Bağlanılıyor…");   // npx ilk seferde paket indirebiliyor

    if (body && body.action === "login") {
      // Tarayıcıda bir giriş sekmesi açıldı; cevap giriş bitince gelecek.
      say("Tarayıcıda giriş bekleniyor…");
    }
    let answer = {};
    try {
      answer = await (await fetch("/api/connectors", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || { action: "list" }),
      })).json();
    } catch {
      say("Bağlayıcılar okunamadı", true);
      return;
    }
    if (answer.ok === false) {
      // Bozuk JSON kaydedilmedi; ekrandaki metne dokunma — kullanıcı
      // düzeltip yeniden denesin.
      say(answer.error || "Kaydedilemedi", true);
      return;
    }
    say(answer.note || (body && body.action === "save" ? "Kaydedildi" : ""));
    drawConnectors(answer);
    if (typeof loadOrgans === "function") loadOrgans();
  }

  // Dizin: resmi uzak OAuth uçları + bilinen stdio paketleri.
  // Adres/komut ezberlenmez; kart tıklanınca forma dolar.
  const CONN_KATALOG = [
    { id: "github", ad: "GitHub", kind: "oauth", url: "https://api.githubcopilot.com/mcp/", cmd: "", ne: "depo, PR ve issue", cat: "is" },
    { id: "linear", ad: "Linear", kind: "oauth", url: "https://mcp.linear.app/mcp", cmd: "", ne: "issue ve proje", cat: "is" },
    { id: "notion", ad: "Notion", kind: "oauth", url: "https://mcp.notion.com/mcp", cmd: "", ne: "sayfa ve veritabanı", cat: "is" },
    { id: "atlassian", ad: "Atlassian", kind: "oauth", url: "https://mcp.atlassian.com/v1/sse", cmd: "", ne: "Jira ve Confluence", cat: "is" },
    { id: "slack", ad: "Slack", kind: "oauth", url: "https://mcp.slack.com/mcp", cmd: "", ne: "kanal ve mesaj", cat: "is" },
    { id: "asana", ad: "Asana", kind: "oauth", url: "https://mcp.asana.com/sse", cmd: "", ne: "görev ve proje", cat: "is" },
    { id: "sentry", ad: "Sentry", kind: "oauth", url: "https://mcp.sentry.dev/mcp", cmd: "", ne: "hata ve izleme", cat: "is" },
    { id: "stripe", ad: "Stripe", kind: "oauth", url: "https://mcp.stripe.com", cmd: "", ne: "ödeme nesneleri", cat: "is" },
    { id: "paypal", ad: "PayPal", kind: "oauth", url: "https://mcp.paypal.com/mcp", cmd: "", ne: "ödeme ve sipariş", cat: "is" },
    { id: "figma", ad: "Figma", kind: "oauth", url: "https://mcp.figma.com/mcp", cmd: "", ne: "tasarım dosyaları", cat: "tasarim" },
    { id: "supabase", ad: "Supabase", kind: "oauth", url: "https://mcp.supabase.com/mcp", cmd: "", ne: "veritabanı ve auth", cat: "bulut" },
    { id: "vercel", ad: "Vercel", kind: "oauth", url: "https://mcp.vercel.com", cmd: "", ne: "proje ve dağıtım", cat: "bulut" },
    { id: "huggingface", ad: "Hugging Face", kind: "oauth", url: "https://huggingface.co/mcp", cmd: "", ne: "model ve dataset", cat: "bulut" },
    { id: "neon", ad: "Neon", kind: "oauth", url: "https://mcp.neon.tech/mcp", cmd: "", ne: "Postgres (sunucusuz)", cat: "bulut" },
    { id: "playwright", ad: "Playwright", kind: "stdio", url: "", cmd: "npx -y @playwright/mcp@latest", ne: "tarayıcı otomasyonu", cat: "yerel" },
    { id: "dosyalar", ad: "Dosya sistemi", kind: "stdio", url: "", cmd: "npx -y @modelcontextprotocol/server-filesystem .", ne: "yerel klasör", cat: "yerel" },
    { id: "bellek", ad: "Bellek", kind: "stdio", url: "", cmd: "npx -y @modelcontextprotocol/server-memory", ne: "kalıcı bilgi grafiği", cat: "yerel" },
    { id: "git", ad: "Git", kind: "stdio", url: "", cmd: "npx -y @modelcontextprotocol/server-git", ne: "status, diff, commit", cat: "yerel" },
    { id: "context7", ad: "Context7", kind: "stdio", url: "", cmd: "npx -y @upstash/context7-mcp", ne: "kütüphane belgeleri", cat: "yerel" },
    { id: "dusunme", ad: "Adım adım", kind: "stdio", url: "", cmd: "npx -y @modelcontextprotocol/server-sequential-thinking", ne: "zincirleme düşünme", cat: "yerel" },
    { id: "fetch", ad: "Fetch", kind: "stdio", url: "", cmd: "npx -y @modelcontextprotocol/server-fetch", ne: "URL içeriği çek", cat: "yerel" },
  ];
  // Marka renkli kare + çizim: Claude / Cursor dizinindeki gibi tanınsın.
  // Yollar Simple Icons (CC0) veya aynı okunur sadeleştirme — ağdan logo çekilmez.
  const CONN_MARKS = {
    github: {
      bg: "#181717", fg: "#fff",
      aka: ["github", "githubcopilot.com"],
      d: ["M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"],
    },
    notion: {
      bg: "#000", fg: "#fff",
      aka: ["notion", "mcp.notion.com"],
      d: ["M4.459 4.208c.746.606 1.026.56 2.428.466l13.215-.98c.28 0 .047-.37-.038-.515-.197-.322-.51-.237-.51-.237s-3.094 1.83-4.356 2.56c-.28.176-.51.237-.51.98v12.124c0 .56.51.747 1.065.56l1.832-.84c.56-.28.65-.84.65-1.26V6.354s.42-.98 1.682-.84l.28.047c.466.084.42.56.42.56l.047 12.544c0 .237-.092.56-.51.84l-3.75 2.24c-.466.28-1.12.466-1.682.28l-5.622-1.4c-.56-.176-.98-.653-.98-1.213V6.728c0-.56.373-.98.84-1.166.84-.322 2.56-.84 2.56-.84s-1.682.887-2.428 1.26c-.746.373-1.12.56-1.12 1.12v11.2c0 .56-.28 1.026-.84 1.213L3.75 19.96c-.56.176-1.026-.092-1.026-.653V5.748c0-.466.28-.84.746-1.026.84-.28 2.24-.84 2.24-.84s-.933.56-1.25.84z"],
    },
    linear: {
      bg: "#5E6AD2", fg: "#fff",
      aka: ["linear", "mcp.linear.app"],
      d: ["M3.4 18.2 16.8 4.8a1.6 1.6 0 0 1 2.3 2.3L5.7 20.5a1.6 1.6 0 1 1-2.3-2.3z"],
    },
    sentry: {
      bg: "#362D59", fg: "#fff",
      aka: ["sentry", "mcp.sentry.dev"],
      d: ["M12 2.2 1.2 21.2h5.4l1.7-3h7.4l1.7 3h5.4L12 2.2zm0 6.4 3.1 5.6H8.9L12 8.6z"],
    },
    stripe: {
      bg: "#635BFF", fg: "#fff",
      aka: ["stripe", "mcp.stripe.com"],
      d: ["M13.976 9.15c-2.172-.806-3.356-1.426-3.356-2.409 0-.831.683-1.305 1.901-1.305 2.227 0 4.515.858 6.09 1.631l.89-5.494C18.252.975 15.697 0 12.165 0 9.667 0 7.589.759 6.104 2.24c-1.49 1.47-2.27 3.56-2.27 5.873 0 4.002 2.444 6.73 6.378 8.203 2.168.814 3.354 1.428 3.354 2.415 0 .96-.84 1.522-2.354 1.522-1.875 0-4.965-.921-6.99-2.109l-.9 5.555C5.175 22.99 8.385 24 11.714 24c2.641 0 4.843-.624 6.328-1.813 1.664-1.305 2.525-3.236 2.525-5.732 0-4.128-2.524-6.9-6.591-8.305z"],
    },
    playwright: {
      bg: "#2EAD33", fg: "#fff",
      aka: ["playwright"],
      d: [
        "M4.2 7.1c0-1.7 1.8-3.1 4.1-3.1s4.1 1.4 4.1 3.1v7.8c0 1.7-1.8 3.1-4.1 3.1s-4.1-1.4-4.1-3.1V7.1z",
        { d: "M6.6 9.4a1.15 1.15 0 1 1 0 2.3 1.15 1.15 0 0 1 0-2.3zm3.4 0a1.15 1.15 0 1 1 0 2.3 1.15 1.15 0 0 1 0-2.3z", fill: "#2EAD33" },
        { d: "M11.6 7.1c0-1.7 1.8-3.1 4.1-3.1s4.1 1.4 4.1 3.1v7.8c0 1.7-1.8 3.1-4.1 3.1s-4.1-1.4-4.1-3.1V7.1z", opacity: ".85" },
        { d: "M14 9.4a1.15 1.15 0 1 1 0 2.3 1.15 1.15 0 0 1 0-2.3zm3.4 0a1.15 1.15 0 1 1 0 2.3 1.15 1.15 0 0 1 0-2.3z", fill: "#2EAD33" },
      ],
    },
    dosyalar: {
      bg: "#3E4A3A", fg: "#E8E4D8",
      aka: ["dosyalar", "filesystem", "server-filesystem"],
      d: ["M2.4 6.2h6.2l1.6 1.8H21.6v10.6H2.4V6.2z"],
    },
    bellek: {
      bg: "#3D3558", fg: "#E8E4D8",
      aka: ["bellek", "memory", "server-memory"],
      d: [
        "M6 3.8a2.4 2.4 0 1 1 0 4.8 2.4 2.4 0 0 1 0-4.8z",
        "M18 3.8a2.4 2.4 0 1 1 0 4.8 2.4 2.4 0 0 1 0-4.8z",
        "M12 15.4a2.4 2.4 0 1 1 0 4.8 2.4 2.4 0 0 1 0-4.8z",
        { d: "M7.8 8.2 10.4 15.6", stroke: true },
        { d: "M16.2 8.2 13.6 15.6", stroke: true },
      ],
    },
    figma: {
      bg: "#1E1E1E", fg: "#fff",
      aka: ["figma", "mcp.figma.com"],
      d: [
        { d: "M8 2.4h4a3 3 0 0 1 0 6H8V2.4z", fill: "#F24E1E" },
        { d: "M12 2.4a3 3 0 1 1 0 6 3 3 0 0 1 0-6z", fill: "#FF7262" },
        { d: "M8 8.4h4a3 3 0 1 1 0 6H8V8.4z", fill: "#A259FF" },
        { d: "M12 8.4a3 3 0 1 1 0 6 3 3 0 0 1 0-6z", fill: "#1ABCFE" },
        { d: "M8 14.4a3 3 0 1 0 3 3v-3H8z", fill: "#0ACF83" },
      ],
    },
    slack: {
      bg: "#4A154B", fg: "#fff",
      aka: ["slack", "mcp.slack.com"],
      d: [
        { d: "M5.4 10.2a2.1 2.1 0 1 1 0-4.2h2.1v2.1a2.1 2.1 0 0 1-2.1 2.1z", fill: "#E01E5A" },
        { d: "M10.2 5.4a2.1 2.1 0 1 1 4.2 0v2.1h-2.1a2.1 2.1 0 0 1-2.1-2.1z", fill: "#36C5F0" },
        { d: "M18.6 10.2a2.1 2.1 0 1 1 0 4.2h-2.1v-2.1a2.1 2.1 0 0 1 2.1-2.1z", fill: "#2EB67D" },
        { d: "M13.8 18.6a2.1 2.1 0 1 1-4.2 0v-2.1h2.1a2.1 2.1 0 0 1 2.1 2.1z", fill: "#ECB22E" },
      ],
    },
    atlassian: {
      bg: "#0052CC", fg: "#fff",
      aka: ["atlassian", "jira", "confluence", "mcp.atlassian.com"],
      d: ["M12.2 3 6.4 16.4h4.7L16.9 3h-4.7zM8.2 21 2.4 7.6h4.7L13 21H8.2z"],
    },
    asana: {
      bg: "#F06A6A", fg: "#fff",
      aka: ["asana", "mcp.asana.com"],
      d: [
        { circle: true, cx: 12, cy: 7.2, r: 3.1 },
        { circle: true, cx: 7.2, cy: 16.2, r: 3.1 },
        { circle: true, cx: 16.8, cy: 16.2, r: 3.1 },
      ],
    },
    huggingface: {
      bg: "#FFD21E", fg: "#111",
      aka: ["huggingface", "hugging", "huggingface.co"],
      d: [
        { circle: true, cx: 12, cy: 12, r: 9.2, fill: "#FFD21E" },
        { circle: true, cx: 8.6, cy: 10.2, r: 1.35, fill: "#111" },
        { circle: true, cx: 15.4, cy: 10.2, r: 1.35, fill: "#111" },
        { d: "M8.2 14.4c1.1 1.6 2.4 2.4 3.8 2.4s2.7-.8 3.8-2.4", stroke: true, width: "1.6", fill: "none" },
      ],
    },
    supabase: {
      bg: "#1C1C1C", fg: "#3ECF8E",
      aka: ["supabase", "mcp.supabase.com"],
      d: ["M13.2 2.2 4.6 13.4h6.4L9.2 21.8 19.4 10.6h-6.5L15.1 2.2z"],
    },
    vercel: {
      bg: "#000", fg: "#fff",
      aka: ["vercel", "mcp.vercel.com"],
      d: ["M12 3.2 22 20.8H2z"],
    },
    neon: {
      bg: "#00E599", fg: "#0A0A0A",
      aka: ["neon", "mcp.neon.tech"],
      d: ["M13.6 2.4 6.2 13.2h5.1L9.8 21.6 18.4 10.4h-5.2L15.4 2.4z"],
    },
    paypal: {
      bg: "#003087", fg: "#fff",
      aka: ["paypal", "mcp.paypal.com"],
      d: [
        "M7.2 4.2h6.4c2.6 0 4.2 1.4 4.2 3.6 0 2.6-1.9 4.2-4.6 4.2H9.6L8.6 19.8H5.4L7.2 4.2z",
        { d: "M9.4 7.2h4.1c1.2 0 1.9.6 1.9 1.6 0 1.1-.8 1.7-2.1 1.7H10.2L9.4 7.2z", fill: "#009CDE" },
      ],
    },
    git: {
      bg: "#F05032", fg: "#fff",
      aka: ["git", "server-git"],
      d: ["M12.9 2.3a1.2 1.2 0 0 0-1.8 0L2.3 11.1a1.2 1.2 0 0 0 0 1.8l8.8 8.8a1.2 1.2 0 0 0 1.8 0l8.8-8.8a1.2 1.2 0 0 0 0-1.8L12.9 2.3zM12 7.2a1.6 1.6 0 1 1 0 3.2 1.6 1.6 0 0 1 0-3.2zm-2.4 6.2a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8zm5.6.4a1.2 1.2 0 1 1 0 2.4 1.2 1.2 0 0 1 0-2.4z"],
    },
    context7: {
      bg: "#00DC82", fg: "#052E1C",
      aka: ["context7", "upstash"],
      d: ["M5.2 5.2h13.6v2.2H5.2zM5.2 9.4h13.6v9.4H5.2zM8 12.2h8v1.6H8zM8 15.2h5.4v1.6H8z"],
    },
    dusunme: {
      bg: "#4C3D73", fg: "#EDE6FF",
      aka: ["dusunme", "sequential-thinking", "sequential"],
      d: [
        "M7.2 5.2a2.4 2.4 0 1 1 0 4.8 2.4 2.4 0 0 1 0-4.8z",
        "M16.8 9.2a2.4 2.4 0 1 1 0 4.8 2.4 2.4 0 0 1 0-4.8z",
        "M9.6 16.2a2.4 2.4 0 1 1 0 4.8 2.4 2.4 0 0 1 0-4.8z",
        { d: "M9.2 9.4 14.8 11.4", stroke: true },
        { d: "M15.2 14.4 11.6 16.8", stroke: true },
      ],
    },
    fetch: {
      bg: "#2B6CB0", fg: "#fff",
      aka: ["fetch", "server-fetch"],
      d: [
        "M12 3.2a8.8 8.8 0 1 1 0 17.6 8.8 8.8 0 0 1 0-17.6zm0 1.8a7 7 0 1 0 0 14 7 7 0 0 0 0-14z",
        { d: "M4.6 12h14.8M12 4.8c2.4 2.2 3.6 4.6 3.6 7.2s-1.2 5-3.6 7.2C9.6 17 8.4 14.6 8.4 12s1.2-5 3.6-7.2z", stroke: true, width: "1.5" },
      ],
    },
  };

  function connMarkId(name, where) {
    const hay = ((name || "") + " " + (where || "")).toLowerCase();
    for (const [id, spec] of Object.entries(CONN_MARKS)) {
      if (id === (name || "").toLowerCase()) return id;
      if ((spec.aka || []).some((a) => hay.includes(a))) return id;
    }
    return "";
  }

  function connMark(id) {
    const spec = CONN_MARKS[id];
    if (!spec) return null;
    const wrap = el("span", "conn-mark");
    wrap.style.setProperty("--conn-bg", spec.bg);
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", spec.box || "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    for (const item of spec.d) {
      if (item && item.circle) {
        const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        c.setAttribute("cx", item.cx);
        c.setAttribute("cy", item.cy);
        c.setAttribute("r", item.r);
        c.setAttribute("fill", item.fill || spec.fg);
        svg.append(c);
        continue;
      }
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      if (typeof item === "string") {
        path.setAttribute("d", item);
        path.setAttribute("fill", spec.fg);
      } else {
        path.setAttribute("d", item.d);
        if (item.stroke) {
          path.setAttribute("fill", "none");
          path.setAttribute("stroke", spec.fg);
          path.setAttribute("stroke-width", item.width || "1.8");
          path.setAttribute("stroke-linecap", "round");
        } else {
          path.setAttribute("fill", item.fill || spec.fg);
        }
        if (item.opacity) path.setAttribute("opacity", item.opacity);
      }
      svg.append(path);
    }
    wrap.append(svg);
    return wrap;
  }

  const connFiltre = { q: "", only: "", cat: "" };   // only: "" | "ok" | "bad"
  let connSonVeri = null;

  function drawConnectors(data) {
    connSonVeri = data;
    const pane = panes.connectors;
    pane.textContent = "";
    head(pane, t("Bağlayıcılar"),
      t("Hazır dizin veya kendi sunucun. OAuth tarayıcıda açılır; ham JSON ileri seviye."));

    // Arama + durum filtreleri: Claude'daki dizinle aynı okuma düzeni.
    const bar = el("div", "conn-bar");
    const ara = el("input", "input-text conn-search");
    ara.type = "search";
    ara.placeholder = t("Bağlayıcı ara…");
    ara.value = connFiltre.q;
    ara.addEventListener("input", () => {
      connFiltre.q = ara.value.trim().toLowerCase();
      drawConnectors(connSonVeri);
      const geri = pane.querySelector(".conn-search");
      if (geri) { geri.focus(); geri.setSelectionRange(geri.value.length, geri.value.length); }
    });
    bar.append(ara);
    for (const [kod, ad] of [["", "Tümü"], ["ok", "Bağlı"], ["bad", "Bağlı değil"]]) {
      const cip = el("button", "conn-chip" + (connFiltre.only === kod ? " on" : ""));
      cip.type = "button";
      cip.textContent = t(ad);
      cip.addEventListener("click", () => {
        connFiltre.only = kod;
        drawConnectors(connSonVeri);
      });
      bar.append(cip);
    }
    pane.append(bar);

    for (const problem of data.problems || []) {
      pane.append(el("p", "pane-note bad", problem));
    }

    const list = el("div", "rows");

    const parseRaw = () => {
      let current = {};
      try { current = JSON.parse(data.raw || "{}"); } catch { current = {}; }
      if (!current.mcpServers || typeof current.mcpServers !== "object") {
        current = { mcpServers: (current && typeof current === "object" && !Array.isArray(current))
          ? (current.mcpServers || {}) : {} };
      }
      return current;
    };

    const saveServers = (current) =>
      loadConnectors({ action: "save", raw: JSON.stringify(current, null, 2) });

    const fillConnectorForm = (box, pref) => {
      let kind = pref.kind || "oauth";
      const kinds = el("div", "choices conn-kinds");
      const KINDS = [
        ["oauth", "OAuth", "Tarayıcıda giriş — URL yeter"],
        ["token", "Token", "Bearer anahtarı, Model → anahtarlar"],
        ["stdio", "Yerel", "npx / py komutu (stdio)"],
      ];
      const nameBox = el("input", "input-text");
      nameBox.placeholder = t("ad — ör. notion");
      nameBox.value = pref.name || "";
      if (pref.lockName) nameBox.readOnly = true;
      const urlBox = el("input", "input-text");
      urlBox.placeholder = "https://…/mcp";
      urlBox.value = pref.url || "";
      const tokenBox = el("input", "input-text");
      tokenBox.type = "password";
      tokenBox.placeholder = pref.tokenHint
        || t("token — Model anahtarlarına kaydedilir, dosyaya adı yazılır");
      const cmdBox = el("input", "input-text");
      cmdBox.placeholder = t("komut ve argümanlar — ör. npx -y bir-mcp");
      cmdBox.value = pref.cmd || "";

      const fit = () => {
        urlBox.hidden = kind === "stdio";
        tokenBox.hidden = kind !== "token";
        cmdBox.hidden = kind !== "stdio";
      };
      for (const [id, label, hint] of KINDS) {
        const card = el("button", "choice" + (id === kind ? " on" : ""));
        card.type = "button";
        card.title = t(hint);
        card.append(el("b", null, t(label)));
        card.append(el("span", null, t(hint)));
        card.addEventListener("click", () => {
          kind = id;
          for (const other of kinds.children) other.classList.toggle("on", other === card);
          fit();
        });
        kinds.append(card);
      }
      fit();

      const make = action(pref.saveLabel || t("Ekle ve bağlan"), async () => {
        const name = nameBox.value.trim().toLowerCase();
        if (!/^[a-z0-9_-]+$/.test(name)) {
          say(t("Ad gerekli: yalnızca harf, rakam, - ve _"), true);
          return;
        }
        let entry;
        if (kind === "stdio") {
          const parts = cmdBox.value.trim().split(/\s+/).filter(Boolean);
          if (!parts.length) { say(t("Komut boş"), true); return; }
          entry = { command: parts[0], args: parts.slice(1) };
        } else {
          const where = urlBox.value.trim();
          if (!/^https?:\/\//.test(where)) {
            say(t("Adres http(s):// ile başlamalı"), true);
            return;
          }
          entry = { url: where };
          if (kind === "token") {
            const secret = tokenBox.value.trim();
            if (secret) {
              const env = name.toUpperCase().replace(/[^A-Z0-9]/g, "_") + "_MCP_TOKEN";
              const kept = await post("/api/settings", { keys: { [env]: secret } });
              if (!kept || kept.ok === false) {
                say((kept && kept.error) || t("Token kaydedilemedi"), true);
                return;
              }
              entry.headers = { Authorization: "Bearer ${" + env + "}" };
              say(t("Token Model → anahtarlara yazıldı: ") + env);
            } else if (pref.keepHeaders) {
              entry.headers = pref.keepHeaders;
            } else {
              say(t("Token boş"), true);
              return;
            }
          } else if (pref.keepHeaders) {
            entry.headers = pref.keepHeaders;
          }
        }

        const current = parseRaw();
        if (pref.renameFrom && pref.renameFrom !== name) {
          delete current.mcpServers[pref.renameFrom];
        }
        current.mcpServers[name] = entry;
        await saveServers(current);
        if (kind === "oauth" && !pref.lockName) {
          loadConnectors({ action: "login", name });
        }
      });
      make.classList.add("add");
      box.append(kinds, nameBox, urlBox, tokenBox, cmdBox, make);
      nameBox.focus();
    };

    const kurulu = new Set((data.servers || []).map((s) => s.name));
    const populer = CONN_KATALOG.filter((c) => !kurulu.has(c.id)
      && (!connFiltre.q || (c.id + " " + c.ad + " " + c.ne).toLowerCase().includes(connFiltre.q))
      && (!connFiltre.cat || c.cat === connFiltre.cat));
    if (populer.length && connFiltre.only !== "ok") {
      const sec = el("div", "conn-sec");
      const bas = el("div", "conn-sec-head");
      const copy = el("div", "conn-sec-copy");
      copy.append(el("h3", "conn-sec-title", t("Dizin")));
      copy.append(el("p", "conn-sec-sub", t("Tek tıkla forma dolar — adres ezberleme.")));
      bas.append(copy);
      const cats = el("div", "conn-cats");
      for (const [kod, ad] of [["", "Tümü"], ["is", "İş"], ["tasarim", "Tasarım"],
                               ["bulut", "Bulut"], ["yerel", "Yerel"]]) {
        const cip = el("button", "conn-chip" + (connFiltre.cat === kod ? " on" : ""));
        cip.type = "button";
        cip.textContent = t(ad);
        cip.addEventListener("click", () => {
          connFiltre.cat = kod;
          drawConnectors(connSonVeri);
        });
        cats.append(cip);
      }
      bas.append(cats);
      sec.append(bas);
      const raf = el("div", "conn-pop");
      for (const c of populer) {
        const kart = el("button", "conn-card");
        kart.type = "button";
        const mark = connMark(c.id);
        if (mark) kart.append(mark);
        const meta = el("span", "conn-card-meta");
        meta.append(el("b", null, c.ad), el("span", "conn-card-ne", t(c.ne)));
        kart.append(meta);
        kart.append(el("i", "conn-kind", c.kind === "stdio" ? "stdio" : "OAuth"));
        kart.title = c.kind === "stdio" ? c.cmd : c.url;
        kart.addEventListener("click", () => {
          const adder2 = pane.querySelector(".row.adder");
          if (!adder2) return;
          adder2.scrollIntoView({ block: "nearest" });
          detail(adder2, (box) => {
            fillConnectorForm(box, { name: c.id, kind: c.kind, url: c.url, cmd: c.cmd });
          }, "add");
        });
        raf.append(kart);
      }
      sec.append(raf);
      pane.append(sec);
    }

    for (const server of data.servers || []) {
      // Arama ve durum filtresi listeyi süzer; veri olduğu gibi durur.
      if (connFiltre.q && !server.name.toLowerCase().includes(connFiltre.q)) continue;
      if (connFiltre.only === "ok" && !server.ok) continue;
      if (connFiltre.only === "bad" && server.ok) continue;
      const acts = [];
      if (server.kind === "http" && !server.auth) {
        acts.push([t("Giriş yap"), () => loadConnectors({ action: "login", name: server.name })]);
      }
      if (server.auth) {
        acts.push([t("Çıkış"), () => loadConnectors({ action: "logout", name: server.name }), true]);
      }
      acts.push([t("Düzenle"), () => {
        detail(line, (box) => {
          const current = parseRaw();
          const entry = (current.mcpServers || {})[server.name] || {};
          const isStdio = !!(entry.command);
          const cmd = isStdio
            ? [entry.command].concat(entry.args || []).join(" ")
            : "";
          fillConnectorForm(box, {
            kind: isStdio ? "stdio" : (entry.headers ? "token" : "oauth"),
            name: server.name,
            lockName: true,
            url: entry.url || server.where || "",
            cmd,
            keepHeaders: entry.headers,
            tokenHint: t("yeni token (boş = eskisi kalsın)"),
            saveLabel: t("Kaydet ve bağlan"),
            renameFrom: server.name,
          });
        }, "edit");
      }]);
      acts.push([t("Kaldır"), () => confirmRow(line,
        t("Bu MCP sunucusu listeden çıkarılır."),
        () => {
          const current = parseRaw();
          delete current.mcpServers[server.name];
          saveServers(current);
        }), true]);
      var line = row({
        name: server.name,
        desc: (server.kind === "http" ? "HTTP · " : "stdio · ") + server.where,
        meta: (server.auth ? "OAuth · " : "") +
              (server.ok ? server.tools.length + t(" araç") : t("bağlanamadı")),
        state: server.ok ? "" : "bad",
        click: true,
        stay: true,
        icon: connMark(connMarkId(server.name, server.where)),
        acts,
      });
      line.addEventListener("click", () => detail(line, (box) => {
        if (server.ok) {
          if (!server.tools.length) {
            box.append(el("p", "job-prompt dim", t("araç bildirmedi")));
            return;
          }
          const chips = el("div", "tool-chips");
          for (const tool of server.tools) chips.append(el("span", "tool-chip", tool));
          box.append(chips);
        } else {
          box.append(el("p", "pane-note bad", server.error || t("sebep bilinmiyor")));
        }
      }, "tools"));
      list.append(line);
    }

    const adder = row({ name: t("Özel bağlantı"), state: "off", click: true, adder: true });
    adder.classList.add("adder");
    adder.addEventListener("click", () => detail(adder, (box) => {
      fillConnectorForm(box, {});
    }, "add"));
    list.append(adder);

    const editRow = row({
      name: "mcp.json",
      desc: t("ham tanım — ileri seviye"),
      state: "off",
      click: true,
      advanced: true,
      stay: true,
      acts: [[t("Yeniden bağlan"), () => loadConnectors({ action: "reload" })]],
    });
    editRow.addEventListener("click", () => detail(editRow, (box) => {
      box.append(el("p", "pane-note",
        t("Biçim Claude Code'unkiyle aynı (mcpServers): yerel sunucu için " +
        "command/args, uzak sunucu için url/headers. Gizli değeri dosyaya " +
        "yazma — \"${AD}\" yaz, değeri Model sekmesindeki anahtar alanına AD adıyla ekle.")));
      const area = el("textarea", "input-text input-area");
      area.rows = 12;
      area.spellcheck = false;
      area.value = data.raw || "";
      box.append(area);
      const keep = action(t("Kaydet ve bağlan"), () =>
        loadConnectors({ action: "save", raw: area.value }));
      keep.classList.add("add");
      box.append(keep);
    }, "raw"));
    list.append(editRow);
    pane.append(list);
  }

  // --- konum ve açılış --------------------------------------------------
  //
  // "Yarın hava nasıl?" sorusunun cevabı nereye bakılacağına bağlıydı ve
  // model bunu hiçbir yerden öğrenemiyordu — İstanbul varsayıp cevap
  // veriyordu.
  //
  // Üç kaynak var ve güvenilirlikleri çok farklı. Elle yazılan kesin.
  // Saat dilimi ülkeyi veriyor, şehri vermiyor. IP şehir iddia ediyor ama
  // tutmayabiliyor: aynı anda iki servise soruldu, biri "Manisa" dedi
  // diğeri "Kayseri". O yüzden IP kapalı geliyor ve ayrı izin istiyor.

  function drawPlace() {
    const pane = panes.place;
    pane.textContent = "";
    head(pane, "Konum", "Nerede olduğun ve bilgisayar açılınca başlatma.");

    pane.append(field(
      "Bulunduğun yer",
      "Yazarsan kesin kaynak bu olur; neo sorduğunda burayı okur ve bir " +
      "daha sormaz",
      text((patch.place || {}).manual ?? state.place.manual,
           (v) => set("place", "manual", v.trim()), "Kayseri")
    ));

    pane.append(field(
      "IP'den konum bul",
      "Açıkken adresin iki konum servisine gidiyor. Sonuç şehir düzeyinde " +
      "güvenilmez — ölçümde iki servis iki ayrı şehir söyledi — ve neo onu " +
      "kesin değil, teyit edilecek bir ipucu olarak kullanıyor",
      toggleBox((patch.place || {}).enabled ?? state.place.enabled,
                (v) => set("place", "enabled", v))
    ));

    pane.append(el("p", "pane-note",
      t("Kapalıyken bile ülke biliniyor: makinenin saat diliminden geliyor, " +
      "ağa çıkmıyor. Şehir gerekiyorsa neo sana soruyor.")));

    // --- açılışta başlat ---
    if (!state.startup.available) {
      pane.append(field("Bilgisayar açılınca başlat",
                        "Yalnızca Windows'ta", el("span", "pane-note", t("Yok"))));
    } else {
      pane.append(field(
        "bilgisayar açılınca başlat",
        "Tepside çalışan, \"hey neo\" ile uyanan bir ajanı her açılışta elle " +
        "başlatmak gerekmesin",
        toggleBox((patch.startup || {}).enabled ?? state.startup.enabled,
                  (v) => set("startup", "enabled", v))
      ));

      // Ne yazıldığı görünsün: açılışa sessizce bir şey eklemek doğru değil.
      const line = el("p", "pane-note mono", state.startup.command);
      pane.append(field("Çalıştırılacak satır",
                        "Kayıt: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run · " +
                        "Görev Yöneticisi › Başlangıç'tan da görebilirsin",
                        line));
    }

    // --- Explorer sağ tık ---
    const shell = state.shell_assoc || {};
    if (!shell.available) {
      pane.append(field("Sağ tık · Neo ile aç",
                        "Yalnızca Windows'ta", el("span", "pane-note", t("Yok"))));
    } else {
      pane.append(field(
        "Sağ tık menüsünde Neo ile aç",
        "Dosya veya klasöre sağ tık → yeni sohbette o klasörle açar",
        toggleBox((patch.shell_assoc || {}).enabled ?? shell.enabled,
                  (v) => set("shell_assoc", "enabled", v))
      ));
    }
  }

  // --- makine -----------------------------------------------------------
  //
  // Yerel bir modelde asıl sınır makinenin kendisi. Buradaki üç ayar da
  // gerçekten yaşanmış bir soruna karşılık geliyor.

  function drawMachine() {
    const pane = panes.machine;
    pane.textContent = "";
    head(pane, "Makine", "Sürüm, eşzamanlılık, arayüz dili, tarayıcı ve dış kapı.");

    // Sürüm: salt-okunur. Sahada "hangi sürüm kurulu?" sorusu cevapsızdı —
    // tek gerçek kaynak pyproject, buraya /api/settings'ten geliyor.
    // Kurulu/geliştirme ayrımı önemli: iki kopya aynı makinede yaşayabiliyor.
    const surumYazi = el("span", "surum-deger",
      (state.surum || "?") + " · " + t(state.installed ? "kurulum" : "geliştirme"));
    const denetle = el("button", "detect", t("Güncellemeleri denetle"));
    denetle.type = "button";
    const surumKutu = el("div", "with-action");
    surumKutu.append(surumYazi, denetle);
    const surumAlan = field(
      "Sürüm",
      "Denetim yalnız bu düğmeyle yapılır — arka planda kendiliğinden ağa çıkılmaz",
      surumKutu
    );
    pane.append(surumAlan);
    denetle.addEventListener("click", async () => {
      denetle.disabled = true;
      denetle.textContent = t("Soruluyor…");
      let cevap = {};
      try {
        cevap = await (await fetch("/api/surum", { method: "POST" })).json();
      } catch { /* aşağıda ele alınıyor */ }
      denetle.disabled = false;
      denetle.textContent = t("Güncellemeleri denetle");

      // Önceki sonucu temizle: art arda basınca satırlar birikmesin.
      const eski = surumAlan.querySelector(".surum-sonuc");
      if (eski) eski.remove();
      const sonuc = el("span", "surum-sonuc");
      if (cevap.yeni) {
        const uc = el("a", "surum-yeni",
          "v" + cevap.yeni + t(" mevcut — indir"));
        uc.href = cevap.url || "#";
        // pywebview penceresinde dış bağlantı sistem tarayıcısına gider.
        uc.addEventListener("click", (e) => {
          e.preventDefault();
          if (cevap.url) window.open(cevap.url, "_blank", "noopener");
        });
        sonuc.append(uc);
      } else if (cevap.ok) {
        sonuc.textContent = t("Güncel — daha yeni sürüm yok");
      } else {
        sonuc.className += " bad";
        sonuc.textContent = cevap.hata ? t(cevap.hata) : t("Ağa ulaşılamadı — internet bağlantısını denetle");
      }
      surumKutu.append(sonuc);
    });

    pane.append(field(
      "Yerel model optimizasyonu",
      "Açıkken: diğer modelleri boşaltır, tek kopya tutar, VRAM/model boyutuna göre bağlamı düşürür. Kapalıysa normal kullanım.",
      toggleBox(
        (patch.model || {}).local_optimize ?? state.model.local_optimize ?? false,
        (v) => {
          set("model", "local_optimize", !!v);
          if (v) {
            set("model", "max_calls", 1);
            set("context", "max_agents", 1);
          }
        }
      )
    ));

    const gpus = ((state.hardware || {}).gpu) || [];
    if (gpus.length) {
      const info = el("div", "field-hint");
      info.textContent = gpus.map((g) =>
        `${g.name}: ${g.free_mb} / ${g.total_mb} MB boş`
      ).join(" · ");
      pane.append(field("Ekran kartı", "", info));
    } else {
      pane.append(field(
        "Ekran kartı",
        "nvidia-smi yok — VRAM otomatik ölçülemeyecek; yine de diğer modeller boşaltılır",
        el("span", null, "—")
      ));
    }

    pane.append(field(
      "Aynı anda model isteği",
      "Yerel sunucularda 1 kalmalı: LM Studio meşgul bir modele ikinci istek " +
      "gelince modelin ikinci bir kopyasını yüklüyor",
      number((patch.model || {}).max_calls ?? state.model.max_calls,
             (v) => set("model", "max_calls", Number(v)))
    ));

    pane.append(field(
      "Aynı anda araç",
      "Model bir turda on araç birden isteyebiliyor; hepsini aynı anda " +
      "başlatmak zayıf bir makinede belleği tüketiyor",
      number((patch.context || {}).max_parallel ?? state.context.max_parallel,
             (v) => set("context", "max_parallel", Number(v)))
    ));

    pane.append(field(
      "Aynı anda alt ajan",
      "İşler yoğunken neo işi yardımcılara dağıtıyor; bu sayıdan fazlası " +
      "sıraya girer. Yerel sunucuda model tek kopyaysa 1 mantıklı",
      number((patch.context || {}).max_agents ?? state.context.max_agents ?? 3,
             (v) => set("context", "max_agents", Number(v)))
    ));

    pane.append(field(
      "Modeli yüklü tut (saniye)",
      "0 = sunucunun kendi davranışı. Her istekte yeniden yükleme onlarca " +
      "saniye sürüyor ve ilk cevabı bekletiyor",
      number((patch.model || {}).keep_loaded ?? state.model.keep_loaded,
             (v) => set("model", "keep_loaded", Number(v)))
    ));

    // Arayüz dili: kaynak Türkçe, İngilizce görüntülemede çevrilir (dil.js).
    // Sayfa yenilenerek geçilir — yarım çevrili canlı geçiş kafa karıştırır.
    const dilKutu = el("div", "choices");
    for (const [kod, ad] of [["tr", "Türkçe"], ["en", "English"]]) {
      const secim = el("button", "choice" + (Dil.mode === kod ? " on" : ""));
      secim.type = "button";
      secim.append(el("b", null, ad));
      secim.addEventListener("click", () => { if (Dil.mode !== kod) Dil.sec(kod); });
      dilKutu.append(secim);
    }
    pane.append(field("Arayüz dili / Interface language", "", dilKutu));

    // neo chrome: DevTools kapısıyla sürülen tarayıcı. Kapalı geliyor —
    // kendi kendine sayfa açan bir asistan istenerek açılmalı.
    pane.append(field(
      "neo chrome (tarayıcı)",
      "neo kendi Chrome/Edge profiliyle sayfa açar, okur, görüntü alır. " +
      "Girişleri o pencerede sen yaparsın; oturumlar profilinde kalıcıdır",
      toggleBox((patch.browser || {}).enabled ?? (state.browser || {}).enabled ?? false,
                (v) => set("browser", "enabled", v))
    ));

    // Dış kapı: harici araçlar/ajanlar sohbete HTTP'den yazıp tüm yanıtı
    // alabilir (POST /api/gate). Değerlendirme için var; varsayılan kapalı.
    const kapiAnahtar = toggleBox(false, async (v) => {
      try {
        await fetch("/api/gate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ on: v }),
        });
        say(v ? "Dış kapı açıldı" : "Dış kapı kapandı");
      } catch { say("Kaydedilemedi"); }
    });
    fetch("/api/gate").then((r) => r.json()).then((d) => {
      kapiAnahtar.checked = !!d.on;
    }).catch(() => {});
    pane.append(field(
      "Dış kapı (API)",
      "Başka ajanlar ve araçlar sohbete programla yazıp yanıtın tamamını " +
      "alabilir: POST 127.0.0.1'e /api/gate, gövde {\"text\": \"...\"}. " +
      "Yalnızca bu makineden erişilir",
      kapiAnahtar
    ));

    // Beyin ortada büyüsün mü: görsel tercih — sunucuya değil tarayıcıya
    // yazılır (localStorage). "Yazılar beynin altında kayboluyor" (31.08).
    let beyinIlk = true;
    try { beyinIlk = localStorage.getItem("neo-brain-ambient") !== "kapali"; } catch {}
    const beyinAnahtar = toggleBox(beyinIlk, (v) => {
      if (window.beyinOrtada) window.beyinOrtada(v);
      say(v ? "Beyin ortada büyüyecek" : "Beyin sağ panelde kalacak");
    });
    pane.append(field(
      "Beyin ortada dursun",
      "Açıkken hiçbir panel açık değilse beyin ekranın ortasında büyür; " +
      "kapatırsan sağ panelde kalır ve yazılar hiç örtülmez",
      beyinAnahtar
    ));

    // Beni tanı: kişisel ince ayar döngüsü (eğitim düzeneği ayrı depoda).
    // Ayar sunucuda tanima.json'da; kaydet düğmesini beklemeden anında
    // gidiyor — dış kapı anahtarıyla aynı kalıp.
    const taniAnahtar = toggleBox(false, async (v) => {
      try {
        await fetch("/api/tanima", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ on: v }),
        });
        say(v ? "Tanıma eğitimi açıldı" : "Tanıma eğitimi kapatıldı");
      } catch { say("Kaydedilemedi"); }
    });
    const taniAlan = field(
      "Beni tanı",
      "neo'nun yerel taban modeli anılarından gece sessizce öğrenir: " +
      "birikince arka planda, düşük öncelikle ince ayar koşar; gerileyen " +
      "aday sınav kapısında çöpe gider. Etiketleme seçili modelle yapılır: " +
      "yerel modelde veri makineden çıkmaz; bulut modelde bu adım açık onay " +
      "vermedikçe atlanır (onay verilirse anı metni o sağlayıcıya gider)",
      taniAnahtar
    );
    pane.append(taniAlan);
    // Mahremiyet onayı: bulut modelle gece etiketlemesi. Varsayılan kapalı;
    // açmak anı metnini seçili sağlayıcıya gönderir — ipucu bunu açıkça der.
    const bulutAnahtar = toggleBox(false, async (v) => {
      try {
        await fetch("/api/tanima", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ learn_cloud_ok: v }),
        });
        say(v ? "Bulut etiketleme onayı verildi" : "Bulut etiketleme onayı geri alındı");
      } catch { say("Kaydedilemedi"); }
    });
    const bulutAlan = field(
      "Bulut modelle etiketlemeye izin ver",
      "Kapalıyken (varsayılan) gece etiketlemesi yalnız yerel modelle çalışır " +
      "ve anıların makineden çıkmaz. Açarsan anı metinleri etiketleme için " +
      "seçili bulut sağlayıcısına gönderilir",
      bulutAnahtar
    );
    pane.append(bulutAlan);
    fetch("/api/tanima").then((r) => r.json()).then((d) => {
      taniAnahtar.checked = !!d.on;
      bulutAnahtar.checked = !!d.learn_cloud_ok;
      // Düzenek kurulu değilse anahtar boşa çevrilir; ipucuna not düşülüyor.
      if (!d.hazir) {
        const ipucu = taniAlan.querySelector(".field-hint");
        if (ipucu) ipucu.textContent += t(" · eğitim düzeneği bu makinede kurulu değil");
      }
    }).catch(() => {});

    const slot = el("div", "loaded");
    slot.append(el("p", "pane-note", t("Yükleniyor…")));
    pane.append(field("Sunucuda yüklü olanlar", "", slot));
    showLoaded(slot);
  }

  async function showLoaded(slot) {
    let answer = {};
    try {
      answer = await (await fetch("/api/loaded", { method: "POST" })).json();
    } catch { /* asagida ele aliniyor */ }

    slot.textContent = "";
    const models = answer.models || [];
    if (!models.length) {
      slot.append(el("p", "pane-note", t("Sunucu yüklü model listesi vermiyor")));
      return;
    }

    // Aynı taban addan birden çok kopya varsa bellek boşa gidiyor demektir.
    const counts = {};
    for (const m of models) counts[m.base] = (counts[m.base] || 0) + 1;

    for (const model of models) {
      const row = el("div", "loaded-row");
      row.append(el("span", "loaded-id", model.id));
      if (model.window) row.append(el("span", "loaded-window", model.window + t(" token")));
      slot.append(row);
    }

    const doubled = Object.entries(counts).filter(([, n]) => n > 1);
    if (doubled.length) {
      slot.append(el("p", "pane-note bad",
        doubled.map(([name, n]) => name + " × " + n).join(", ") +
        t(" — aynı model birden çok kez yüklü. \"Aynı anda model isteği\" 1 " +
        "olduğunda yenisi oluşmaz; duranları LM Studio'da Eject ile kaldır.")));
    }
  }

  // --- yetki ------------------------------------------------------------

  function drawAccess() {
    const pane = panes.access;
    pane.textContent = "";
    head(pane, "Yetki", "Neye izin var: kip, kurallar ve atölye sınırı.");

    const chosen = () => (patch.permissions || {}).mode ?? state.permissions.mode;
    const picker = el("div", "choices");

    for (const mode of state.modes) {
      const card = el("button", "choice" + (mode.id === chosen() ? " on" : "") +
                                (mode.id === "yolo" ? " risky" : ""));
      card.type = "button";
      card.append(el("b", null, mode.label));
      card.append(el("span", null, mode.hint));
      card.addEventListener("click", () => {
        set("permissions", "mode", mode.id);
        drawAccess();
      });
      picker.append(card);
    }

    pane.append(field("İzin kipi", "", picker));

    // Kural listesi: "hep izin ver" dendiginde buraya bir satir yaziliyor.
    // Verilen izni geri alabilecegi bir yer olmadan o dugme tek yonlu bir
    // kapi oluyordu.
    const rules = el("div", "rules");
    rules.append(el("p", "pane-note", t("Yukleniyor…")));
    pane.append(field("Kurallar", "arac:hedef-deseni · deny her zaman kazanir", rules));
    loadRules(rules);
    pane.append(el("p", "pane-note",
      t("İzin kipi anında geçerli olur — yeniden başlatmak gerekmez. " +
      "\"Tam yetki\" seçiliyken hiçbir komut sorulmadan çalışır.")));

    pane.append(el("hr", "md-rule"));

    // --- proje ---
    //
    // Kullanıcının kendi klasöründe çalışmak: "atölyeye kopyala" yolu bir
    // AĞAÇ için işlemiyor (kopyası orijinali olmuyor). Klasörü seçmek bir
    // onaydır; seçilen yer yazılabilir oluyor. Atölye her koşulda kalıyor.
    projectSection(pane);

    pane.append(el("hr", "md-rule"));

    pane.append(field(
      "Atölye klasörü",
      t("neo'nun KENDİ alanı — kendi işleri, denemeleri buraya. " +
      "Şu an: ") + state.sandbox.root,
      text((patch.sandbox || {}).directory ?? state.sandbox.directory,
           (v) => set("sandbox", "directory", v), "atolye")
    ));

    pane.append(field(
      "Atölye sınırı açık",
      "Kapatmak ajanın bilgisayardaki her yere yazabilmesi demek",
      toggleBox((patch.sandbox || {}).enabled ?? state.sandbox.enabled,
                (v) => set("sandbox", "enabled", v))
    ));
  }

  // --- proje -------------------------------------------------------------
  //
  // "Benim projemde çalışacaksan klasörü seçmem gerekiyor." Atölye neo'nun
  // kendi işleri için kalıyor; proje kullanıcının kodu. Seçim bir onaydır:
  // seçilen klasör yazılabilir oluyor.
  //
  // Proje bir OTURUM değil — değiştirmek zihni, anıları ya da konuşma
  // geçmişini etkilemiyor. Bu, kullanıcıya da açıkça yazılıyor.

  function projectSection(pane) {
    const kutu = el("div", "proj-pick");
    const secili = (patch.sandbox || {}).project ?? state.sandbox.project ?? "";

    const alan = text(secili, (v) => set("sandbox", "project", v.trim()),
                      t("boş — yalnızca atölye"));
    kutu.append(alan);

    // Durum satırı: neyin geçerli olduğu, hata ve uyarı.
    const durum = el("div", "proj-state");
    kutu.append(durum);

    function durumCiz() {
      durum.textContent = "";
      const yol = (patch.sandbox || {}).project ?? state.sandbox.project ?? "";
      if (!yol.trim()) {
        durum.append(el("span", "pane-note",
          t("Proje seçilmedi — yazma yalnızca atölyede serbest.")));
        return;
      }
      if (state.sandbox.project_error && yol === state.sandbox.project) {
        durum.append(el("span", "pane-note bad", state.sandbox.project_error));
        return;
      }
      if (yol !== state.sandbox.project) {
        durum.append(el("span", "pane-note",
          t("Kaydedince burada çalışmaya başlayacağım.")));
        return;
      }
      const satir = el("span", "pane-note good",
        t("Şu an burada çalışıyorum; yazma izni bu klasörde geçerli.")
        + " " + (state.sandbox.project_root || yol));
      durum.append(satir);
      if (state.sandbox.project_note) {
        durum.append(el("span", "pane-note bad", state.sandbox.project_note));
      }
    }
    durumCiz();

    // Gezgin: native diyalog yok, seçici sayfanın kendi içinde.
    const gezginKutu = el("div", "proj-browse");
    gezginKutu.hidden = true;
    const ac = el("button", "job-act add", t("Klasör seç…"));
    ac.type = "button";
    ac.addEventListener("click", () => {
      gezginKutu.hidden = !gezginKutu.hidden;
      if (!gezginKutu.hidden) gozat("");
    });
    kutu.append(ac);
    kutu.append(gezginKutu);

    async function gozat(yol) {
      gezginKutu.textContent = "";
      gezginKutu.append(el("p", "pane-note", t("Yukleniyor…")));
      let veri;
      try {
        veri = await (await fetch("/api/gozat?yol=" + encodeURIComponent(yol))).json();
      } catch {
        gezginKutu.textContent = "";
        gezginKutu.append(el("p", "pane-note bad", t("Sunucuya ulaşılamadı")));
        return;
      }
      gezginKutu.textContent = "";
      if (veri.hata) {
        gezginKutu.append(el("p", "pane-note bad", veri.hata));
        return;
      }

      // Başlık: nerede olduğumuz + yukarı çık.
      const bas = el("div", "proj-crumb");
      if (veri.ust !== null && veri.ust !== undefined) {
        const yukari = el("button", "crumb-link", "↑ " + t("yukarı"));
        yukari.type = "button";
        yukari.addEventListener("click", () => gozat(veri.ust));
        bas.append(yukari);
      }
      bas.append(el("span", "proj-here", veri.yol || t("Bu bilgisayar")));
      gezginKutu.append(bas);

      // Buradaki klasörü SEÇ: yalnızca gerçek bir klasördeysek ve engel yoksa.
      if (veri.yol) {
        const ozet = [];
        if (typeof veri.dosya === "number") ozet.push(veri.dosya + t(" dosya"));
        if (veri.klasorler) ozet.push(veri.klasorler.length + t(" klasör"));
        if (veri.tur) ozet.push(veri.tur);
        gezginKutu.append(el("p", "pane-note", ozet.join(" · ")));

        if (veri.engel) {
          gezginKutu.append(el("p", "pane-note bad", veri.engel));
        } else {
          if (veri.uyari) gezginKutu.append(el("p", "pane-note bad", veri.uyari));
          const sec = el("button", "job-act add", t("Bu klasörü seç"));
          sec.type = "button";
          sec.addEventListener("click", () => {
            alan.value = veri.yol;
            set("sandbox", "project", veri.yol);
            gezginKutu.hidden = true;
            durumCiz();
          });
          gezginKutu.append(sec);
        }
      }

      const liste = el("div", "proj-list");
      for (const klasor of (veri.klasorler || [])) {
        const satir = el("button", "proj-row");
        satir.type = "button";
        satir.textContent = "▸ " + klasor.ad;
        satir.addEventListener("click", () => gozat(klasor.yol));
        liste.append(satir);
      }
      if (!(veri.klasorler || []).length) {
        liste.append(el("p", "pane-note", t("Alt klasör yok")));
      }
      gezginKutu.append(liste);
    }

    // Son projeler: tek tıkla geçiş.
    const gecmis = state.sandbox.recent || [];
    if (gecmis.length) {
      const serit = el("div", "proj-recent");
      for (const yol of gecmis) {
        const cip = el("button", "proj-chip" + (yol === secili ? " on" : ""));
        cip.type = "button";
        cip.textContent = yol.split(/[\\/]/).filter(Boolean).pop() || yol;
        cip.title = yol;
        cip.addEventListener("click", () => {
          alan.value = yol;
          set("sandbox", "project", yol);
          durumCiz();
        });
        serit.append(cip);
      }
      kutu.append(el("span", "field-hint", t("Son projeler")));
      kutu.append(serit);
    }

    alan.addEventListener("input", durumCiz);

    pane.append(field(
      "Çalışılan proje",
      "Kendi kodunda çalışmamı istediğin klasör. Seçmek bir ONAYDIR: " +
      "orası yazılabilir olur. Atölye ayrıca durmaya devam eder — neo'nun " +
      "kendi işleri oraya gider. Proje değiştirmek konuşmayı, anıları ve " +
      "oturum geçmişini ETKİLEMEZ; yalnızca nerede çalışıldığını değiştirir.",
      kutu
    ));
  }

  // --- dosyalar ---------------------------------------------------------

  // Gezinme atölyeden başlıyor: izlenmek istenen şey ajanın ürettikleri,
  // çalışma alanının tamamı değil. Yukarı çıkmak yine mümkün.
  let here = null;

  async function browse(path) {
    const pane = panes.files;
    pane.textContent = "";
    head(pane, "Dosyalar", "Atölyede üretilen dosyalar.");
    here = path;

    let data;
    try {
      data = await (await fetch("/api/files?path=" + encodeURIComponent(path || ""))).json();
    } catch {
      pane.append(el("p", "pane-note", t("Dizin okunamadı")));
      return;
    }

    if (data.file) { showFile(pane, data); return; }

    const crumb = el("div", "crumb");
    crumb.append(pathLink(t("Çalışma alanı"), ""));
    if (data.path) {
      let walked = "";
      for (const part of data.path.split("/")) {
        walked = walked ? walked + "/" + part : part;
        crumb.append(el("span", "sep", "/"));
        crumb.append(pathLink(part, walked));
      }
    }
    pane.append(crumb);

    if (!data.entries.length) { pane.append(el("p", "pane-note", t("Boş"))); return; }

    const list = el("div", "files");
    for (const entry of data.entries) {
      const row = el("button", "file" + (entry.dir ? " dir" : ""));
      row.type = "button";
      row.append(el("span", "file-name", entry.name));
      row.append(el("span", "file-size", entry.dir ? "" : size(entry.size)));
      row.addEventListener("click", () => browse(entry.path));
      list.append(row);
    }
    pane.append(list);
  }

  function pathLink(label, path) {
    const node = el("button", "crumb-link", label);
    node.type = "button";
    node.addEventListener("click", () => browse(path));
    return node;
  }

  function showFile(pane, data) {
    const back = el("button", "crumb-link", t("← Geri"));
    back.type = "button";
    back.addEventListener("click", () => browse(data.path.split("/").slice(0, -1).join("/")));
    pane.append(back);

    pane.append(el("div", "file-head", data.path + " · " + size(data.size)));

    if (data.binary) {
      pane.append(el("p", "pane-note", t("İkili dosya — burada gösterilemez")));
      return;
    }
    // Kod da olabilir düz metin de; biçimlendirici ikisini de doğru çiziyor.
    const body = el("div", "file-body");
    const fenced = "```" + guess(data.path) + "\n" + (data.text || "") + "\n```";
    body.append(Markdown.render(fenced));
    pane.append(body);

    if (data.truncated) pane.append(el("p", "pane-note", t("Dosyanın başı gösteriliyor")));
  }

  const EXT = { py: "python", js: "javascript", ts: "typescript", ps1: "powershell",
                sh: "bash", json: "json", md: "markdown", css: "css", html: "html",
                sql: "sql", yml: "yaml", yaml: "yaml", toml: "toml" };

  const guess = (path) => EXT[(path.split(".").pop() || "").toLowerCase()] || "";

  function size(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  }

  // --- kaydetme ---------------------------------------------------------

  async function save(auto) {
    // Sağlayıcı değişince ad bir anlığına boş: katalog gelmeden otokayıt
    // düşerse boş adı diske YAZMA — "Model değişti: ." diye anlamsız bir
    // satır düşüyor ve yapılandırma çalışmaz hale geliyordu (canlıda
    // görüldü). Ad, katalog ilk modeli seçince ya da kullanıcı yazınca
    // kendi kaydını tetikliyor.
    if (auto && patch.model && patch.model.name === "") delete patch.model.name;
    if (!Object.keys(patch).length) { if (!auto) say("Değişiklik yok"); return; }
    say("Kaydediliyor…");

    let answer;
    try {
      answer = await (await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      })).json();
    } catch {
      say("Sunucuya ulaşılamadı", true);
      return;
    }

    if (!answer.ok) { say(answer.error || "Kaydedilemedi", true); return; }

    state = answer.settings;
    patch = {};
    say("Kaydedildi", false, true);
    // Ana ekran da tazelensin: model değişti ama üst şeritte eskisi
    // yazmaya devam ediyordu.
    if (typeof loadState === "function") loadState();
    if (typeof loadOrgans === "function") loadOrgans();
    // Otomatik kayıt yeniden çizmez: ekrandaki değerler zaten kaydedilen
    // değerler; çizim, yazılmakta olan alanı elden alıyordu.
    if (!auto) draw();
  }

  // --- bağlama ----------------------------------------------------------

  document.getElementById("gear").addEventListener("click", toggle);
  document.getElementById("settings-close").addEventListener("click", close);
  // Claude Code alışkanlığı: Escape diyaloğu kapatır.
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !panel.hidden) close();
  });

  // Nav araması: sekme adlarını süzer (Claude Code'daki Search kutusu).
  // Boş grup başlıkları da gizlenir; kutu boşalınca hepsi geri gelir.
  (() => {
    const nav = document.getElementById("tabs");
    const ara = el("input", "tabs-search");
    ara.type = "search";
    ara.placeholder = t("Ayarlarda ara");
    ara.setAttribute("aria-label", t("Ayarlarda ara"));
    nav.prepend(ara);
    ara.addEventListener("input", () => {
      const q = ara.value.trim().toLocaleLowerCase("tr");
      let grup = null;
      for (const dugme of nav.children) {
        if (dugme === ara) continue;
        if (dugme.classList.contains("tab-group")) { grup = dugme; dugme.hidden = !!q; continue; }
        const uyan = !q || dugme.textContent.toLocaleLowerCase("tr").includes(q);
        dugme.hidden = !uyan;
        if (uyan && q === "" && grup) grup.hidden = false;
      }
    });
  })();
  document.getElementById("settings-save").addEventListener("click", () => save());

  document.getElementById("tabs").addEventListener("click", (ev) => {
    const name = ev.target.dataset ? ev.target.dataset.tab : null;
    if (!name) return;
    for (const button of ev.currentTarget.children) {
      button.classList.toggle("on", button === ev.target);
    }
    for (const [key, pane] of Object.entries(panes)) pane.hidden = key !== name;
    syncSaveFoot(name);
    if (name === "files") browse(here ?? state.sandbox.directory);
    if (name === "tasks") loadTasks();
    if (name === "eyes") loadCameras();
    if (name === "devices") loadDevices();
    if (name === "place") drawPlace();
    if (name === "skills") loadSkills();
    if (name === "connectors") loadConnectors();
  });

  // Skills / MCP / dosya gibi anlık API sekmelerinde alttaki "Kaydet"
  // yanıltıcı — patch kaydı değil, o sekmenin kendi düğmesi var.
  const LIVE_TABS = new Set([
    "model", "skills", "connectors", "files", "devices", "tasks", "eyes",
  ]);
  function syncSaveFoot(tab) {
    const foot = document.querySelector(".panel-foot");
    if (!foot) return;
    foot.classList.toggle("save-hidden", LIVE_TABS.has(tab));
  }
  const onTab = document.querySelector("#tabs button.on");
  if (onTab && onTab.dataset.tab) syncSaveFoot(onTab.dataset.tab);

  return { open, close, toggle };
})();
