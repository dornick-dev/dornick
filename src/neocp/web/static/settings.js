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
  "Gerekiyorsa API anahtarı / token": "API key / token if required",
  "https://… ya da http://localhost:1234/v1": "https://… or http://localhost:1234/v1",
  "API anahtarı": "API key",
  "LM Studio / özel bir uç kimlik doğrulaması istiyorsa buraya yaz. Anahtarlar diske ayrı yazılır, bir daha okunmaz.":
    "If LM Studio or a custom endpoint wants authentication, enter it here. Keys are written to disk separately and never read back.",
  "Çaba": "Effort",
  "Düşünen modellerde ne kadar akıl yürüteceği. Ölçüm (qwen3-27b, tek kelimelik istem): high 8,97 sn — low 1,60 sn. Sohbet için low, gerçek iş için high":
    "How much a thinking model reasons. Measured (qwen3-27b, one-word prompt): high 8.97 s — low 1.60 s. Low for chat, high for real work",
  "Düşünme": "Thinking",
  "Kapatmak yerel küçük modellerde daha kararlı sonuç veriyor":
    "Turning it off gives steadier results on small local models",
  "Model değişikliği kaydeder kaydetmez geçerli olur; konuşma geçmişi yeni modele taşınır. Ajan o sırada çalışıyorsa değişiklik turun bitmesini bekler — akan bir cevabı yarıda kesmemek için.":
    "A model change takes effect the moment you save; the conversation history moves to the new model. If the agent is mid-turn, the change waits for the turn to finish — so a streaming answer is not cut off.",
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
  "Acinca yazma satirinda kare alma dugmesi cikar. Kamera surekli acik kalmiyor: kare alinirken acilip hemen kapaniyor":
    "When on, a snap button appears in the input line. The camera doesn't stay open: it opens for the frame and closes right away",
  "Goruntuyu modelin anlamasi ayri bir mesele: yerel modellerin cogu goruntu kabul etmiyor. Claude ve GPT ediyor.":
    "Whether the model understands the image is a separate matter: most local models don't accept images. Claude and GPT do.",

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
  "girişli · ": "logged in · ",
  " araç": " tools",
  "bağlanamadı": "connection failed",
  "araç bildirmedi": "no tools reported",
  "sebep bilinmiyor": "reason unknown",
  "＋ Yeni bağlantı": "＋ New connection",
  "Uzak — girişli": "Remote — with login",
  "adres yeter; kaydedince tarayıcıda giriş açılır":
    "just an address; saving opens a browser login",
  "Uzak — sabit token": "Remote — fixed token",
  "token dosyaya değil Anahtarlar'a yazılır": "the token goes to Keys, not into the file",
  "Yerel komut": "Local command",
  "npx / py gibi bir komut başlatılır (LM Studio biçimi)":
    "starts a command like npx / py (LM Studio format)",
  "ad — ör. notion": "name — e.g. notion",
  "token — Anahtarlar'a kaydedilir, dosyaya adı yazılır":
    "token — saved to Keys; only its name goes into the file",
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
  "Biçim Claude Code'unkiyle aynı (mcpServers): yerel sunucu için command/args, uzak sunucu için url/headers. Gizli değeri dosyaya yazma — \"${AD}\" yaz, değeri Anahtarlar sekmesine AD adıyla ekle.":
    "The format matches Claude Code's (mcpServers): command/args for a local server, url/headers for a remote one. Don't write secrets into the file — write \"${NAME}\" and add the value under NAME in the Keys tab.",
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
  "neo'nun yerel taban modeli anılarından gece sessizce öğrenir: birikince arka planda, düşük öncelikle ince ayar koşar; gerileyen aday sınav kapısında çöpe gider":
    "neo's local base model quietly learns from your memories at night: once enough has gathered, a low-priority fine-tune runs in the background; a regressing candidate is discarded at the exam gate",
  "Tanıma eğitimi açıldı": "Personal training enabled",
  "Tanıma eğitimi kapatıldı": "Personal training disabled",
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
  "Sağlayıcı, model ve düşünme derinliği.": "Provider, model and thinking depth.",
  "Sağlayıcı anahtarları — diske ayrı yazılır, geri okunmaz.":
    "Provider keys — written to disk separately, never read back.",
  "Pencere boyutu, yanıt uzunluğu ve görüntü bütçesi.":
    "Window size, answer length and the image budget.",
  "neo'nun sesi: açık/kapalı, ton ve karakter.":
    "neo's voice: on/off, tone and character.",
  "Dinleme, uyandırma sözü ve kamera girişi.":
    "Listening, the wake word and camera input.",
  "İzlenen kameralar — hareket görülünce modele soru gider.":
    "Watched cameras — motion sends the model a question.",
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
  "Eşzamanlılık, arayüz dili, tarayıcı ve dış kapı.":
    "Concurrency, interface language, browser and the external gate.",
  "Atölyede üretilen dosyalar.": "Files produced in the workshop.",
  "Paketle taşı, birleştir, sıfırla.": "Bundle, merge, reset.",
});

const Settings = (() => {
  const panel = document.getElementById("settings");
  const note = document.getElementById("settings-note");
  const panes = {
    model: document.getElementById("pane-model"),
    keys: document.getElementById("pane-keys"),
    limits: document.getElementById("pane-limits"),
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

  async function open() {
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
  }

  const close = () => {
    panel.hidden = true;
    document.body.classList.remove("settling");
  };
  const toggle = () => (panel.hidden ? open() : close());

  function draw() {
    drawModel();
    drawKeys();
    drawMail();
    drawLimits();
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

  // --- model ------------------------------------------------------------

  function drawModel() {
    const pane = panes.model;
    pane.textContent = "";
    head(pane, "Model", "Sağlayıcı, model ve düşünme derinliği.");

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
        say("Kaydedilmedi");
        drawModel();
      });
      picker.append(card);
    }

    pane.append(field("Sağlayıcı", "", picker));

    // Kimliği elle yazdırmak hataya davetiye: "qwen3.5-9b" ile
    // "qwen/qwen3.5-9b" arasındaki fark 404 demek ve hata ancak ilk
    // mesajda görünüyor. Sunucu listeyi veriyorsa seçtiriyoruz.
    const slot = el("div", "model-pick");
    slot.append(text((patch.model || {}).name ?? state.model.name,
                     (v) => set("model", "name", v.trim())));
    pane.append(field(
      "Model",
      "Yüklü modeller soruluyor…",
      slot
    ));
    fillModels(slot);

    // Adres (base URL): preset yalnızca başlangıç. Özel bir port, uzak bir
    // sunucu ya da başka bir OpenAI-uyumlu uç için elle düzenlenebilir.
    const url = text((patch.model || {}).base_url ?? state.model.base_url ?? "",
                     (v) => set("model", "base_url", v.trim()));
    url.placeholder = t("https://… ya da http://localhost:1234/v1");
    pane.append(field("Adres (base URL)",
      "Özel/yerel bir OpenAI-uyumlu uç için düzenle. Boşsa sağlayıcının " +
      "resmî adresi kullanılır.", url));

    // API anahtarı / token: her sağlayıcı için — yerel dahil. LM Studio ya
    // da özel bir uç auth istiyorsa buraya. Anahtar hangi ortam değişkenine
    // yazılacaksa (yoksa OPENAI_API_KEY) oraya gidiyor; backend Bearer olarak
    // gönderiyor. Boş bırakılırsa kayıtlı anahtara dokunulmuyor.
    const authKey = el("input", "input-text");
    authKey.type = "password";
    authKey.autocomplete = "off";
    authKey.placeholder = t("Gerekiyorsa API anahtarı / token");
    authKey.addEventListener("input", () => {
      const v = authKey.value;
      if (!v) return;
      const env = (patch.model || {}).api_key_env ?? state.model.api_key_env ?? "OPENAI_API_KEY";
      patch.keys = patch.keys || {};
      patch.keys[env] = v;
      // Yerel sağlayıcıda env boşsa, backend'in okuyabilmesi için ayarla.
      if (!((patch.model || {}).api_key_env ?? state.model.api_key_env)) {
        set("model", "api_key_env", env);
      }
      say("Kaydedilmedi");
    });
    pane.append(field("API anahtarı",
      "LM Studio / özel bir uç kimlik doğrulaması istiyorsa buraya yaz. " +
      "Anahtarlar diske ayrı yazılır, bir daha okunmaz.", authKey));

    const effort = el("select", "input-text");
    for (const level of ["low", "medium", "high", "xhigh", "max"]) {
      const option = el("option", null, level);
      option.value = level;
      if (level === ((patch.model || {}).effort ?? state.model.effort)) option.selected = true;
      effort.append(option);
    }
    effort.addEventListener("change", () => set("model", "effort", effort.value));
    pane.append(field(
      "Çaba",
      "Düşünen modellerde ne kadar akıl yürüteceği. Ölçüm (qwen3-27b, tek " +
      "kelimelik istem): high 8,97 sn — low 1,60 sn. Sohbet için low, " +
      "gerçek iş için high",
      effort
    ));

    pane.append(field(
      "Düşünme",
      "Kapatmak yerel küçük modellerde daha kararlı sonuç veriyor",
      toggleBox((patch.model || {}).thinking ?? state.model.thinking,
                (v) => set("model", "thinking", v))
    ));

    pane.append(el("p", "pane-note",
      t("Model değişikliği kaydeder kaydetmez geçerli olur; konuşma geçmişi " +
      "yeni modele taşınır. Ajan o sırada çalışıyorsa değişiklik turun " +
      "bitmesini bekler — akan bir cevabı yarıda kesmemek için.")));
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
        hint.textContent = ((patch.model || {}).base_url ?? state.model.base_url)
          ? t("Sunucuya ulaşılamadı ya da liste vermiyor — kimliği elle yaz")
          : t("Sunucu liste vermiyor — kimliği elle yaz");
      }
      return;
    }

    let chosen = (patch.model || {}).name ?? state.model.name;
    // Sağlayıcı yeni değiştiyse ad boş: kataloğun ilki seçiliyor. Boş ad
    // kaydetmek çalışmayan bir yapılandırma demek.
    if (!chosen) {
      chosen = found[0].id;
      set("model", "name", chosen);
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
      const t = text(selected, (v) => set("model", "name", v.trim()));
      slot.append(t);
      t.focus();
    });

    function pick(id) {
      selected = id;
      set("model", "name", id);   // seçim beklemedeki yapılandırmaya YAZILIR
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
    // bir modelde kamerayı açmanın anlamı yok.
    function note(id) {
      if (!hint) return;
      // Oto: gerçek bir model kimliği değil, ücretsiz havuzla çalışan kip.
      // Not YALNIZ OpenRouter'da (Oto zaten yalnız orada listeleniyor).
      if (id === "oto" && (patch.provider || state.provider) === "openrouter") {
        hint.textContent = t(OTO_NOTU);
        return;
      }
      const m = found.find((x) => x.id === id);
      if (!m || m.max_context === undefined) { hint.textContent = found.length + t(" model"); return; }

      const can = [];
      if (m.tools) can.push(t("araç kullanır"));
      if (m.vision) can.push(t("görüntü okur"));
      const loaded = (m.loaded || []).map((i) => i.context.toLocaleString("tr-TR")).join(", ");
      hint.textContent = [
        t("En fazla ") + m.max_context.toLocaleString("tr-TR") + t(" token"),
        can.join(" · "),
        loaded ? t("şu an yüklü: ") + loaded : t("yüklü değil"),
      ].filter(Boolean).join(" · ");
    }
  }

  // --- anahtarlar -------------------------------------------------------

  function drawKeys() {
    const pane = panes.keys;
    pane.textContent = "";
    head(pane, "Anahtarlar", "Sağlayıcı anahtarları — diske ayrı yazılır, geri okunmaz.");

    const needs = state.providers.filter((p) => p.env);
    for (const entry of needs) {
      const input = el("input", "input-text");
      input.type = "password";
      input.placeholder = entry.has_key ? t("Kayıtlı — değiştirmek için yaz") : t("Yapıştır");
      input.autocomplete = "off";
      input.addEventListener("input", () => {
        patch.keys = patch.keys || {};
        patch.keys[entry.env] = input.value;
        say("Kaydedilmedi");
      });

      const hint = entry.from_env
        ? t("Kabuk ortamından geliyor") + " (" + entry.env + ")"
        : entry.hint + " · " + entry.env;
      pane.append(field(entry.label + (entry.has_key ? " ✓" : ""), hint, input));
    }

    pane.append(el("p", "pane-note",
      t("Anahtarlar ") + state.state_dir + t("\\keys.json içinde tutuluyor ve " +
      "bu sayfaya bir daha gönderilmiyor. Silmek için alanı boşaltıp kaydet.")));
  }

  // --- bağlam -----------------------------------------------------------

  function drawLimits() {
    const pane = panes.limits;
    pane.textContent = "";
    head(pane, "Bağlam", "Pencere boyutu, yanıt uzunluğu ve görüntü bütçesi.");

    // Yanlış pencere ayarının belirtisi sinsi: sıkıştırma hiç tetiklenmiyor,
    // sunucu istemin başını sessizce atıyor ve model kim olduğunu unutuyor.
    // Tahmin ettirmek yerine sunucuya soruyoruz.
    const window_ = number((patch.model || {}).context_window ?? state.model.context_window,
                           (v) => set("model", "context_window", v));
    const detect = el("button", "detect", t("Algıla"));
    detect.type = "button";
    detect.addEventListener("click", async () => {
      detect.textContent = t("Soruluyor…");
      let answer = {};
      try {
        answer = await (await fetch("/api/detect-window", { method: "POST" })).json();
      } catch { /* aşağıda ele alınıyor */ }
      detect.textContent = t("Algıla");

      if (answer.window) {
        window_.value = answer.window;
        set("model", "context_window", answer.window);
      } else {
        say("Sunucu pencere boyutunu bildirmiyor — elle gir", true);
      }
    });

    const row = el("div", "with-action");
    row.append(window_, detect);
    pane.append(field(
      "Bağlam penceresi (token)",
      "Modelin gerçek sınırı. Fazla büyük yazmak sıkıştırmayı hiç tetiklememek, " +
      "yani sunucunun istemin başını atması demek",
      row
    ));

    pane.append(field(
      "Tek yanıtta azami token",
      "Küçük tutmak uzun cevapların ortasından kesilmesine yol açıyor",
      number((patch.model || {}).max_tokens ?? state.model.max_tokens,
             (v) => set("model", "max_tokens", v))
    ));

    pane.append(field(
      "Geçmişte tutulan görüntü",
      "Bir ekran görüntüsü ~1.5–4.8k token; eskiler metne çevriliyor",
      number((patch.context || {}).keep_recent_images ?? state.context.keep_recent_images,
             (v) => set("context", "keep_recent_images", Number(v)))
    ));

    pane.append(el("p", "pane-note",
      t("Pencere %75 dolunca konuşma özetlenip sürüyor; özet aynı anda kalıcı " +
      "belleğe de yazılıyor, yani oturum kapansa da kaybolmuyor.")));
  }

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
    head(pane, "Görevler", "Zamanlanmış işler: ne, ne zaman, en son ne oldu.");

    const list = el("div", "rows");
    for (const task of tasks) {
      const line = row({
        name: task.title,
        desc: task.prompt,
        meta: task.enabled ? task.describe + " · " + short(task.next_run) : t("durdu"),
        state: task.enabled ? "" : "off",
        click: true,
        acts: [
          [t("Çalıştır"), () => loadTasks({ action: "run", id: task.id })],
          [task.enabled ? t("Durdur") : t("Sürdür"),
            () => loadTasks({ action: "update", id: task.id, enabled: !task.enabled })],
          [t("Sil"), () => loadTasks({ action: "remove", id: task.id }), true],
        ],
      });
      line.addEventListener("click", () => detail(line, (box) => {
        box.append(el("p", "job-prompt dim", task.prompt));
        box.append(el("p", "job-prompt dim",
          (task.enabled ? t("Sırada: ") + short(task.next_run) : t("Durduruldu")) +
          (task.last_status ? t("  ·  Son: ") + task.last_status : "")));
      }));
      list.append(line);
    }

    const adder = row({ name: t("＋ Yeni görev"), state: "off", click: true });
    adder.addEventListener("click", () => detail(adder, (box) => box.append(newTaskForm())));
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
    head(pane, "Mikrofon", "Dinleme, uyandırma sözü ve kamera girişi.");

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

    pane.append(el("hr", "md-rule"));

    pane.append(field(
      "Kamera",
      "Acinca yazma satirinda kare alma dugmesi cikar. Kamera surekli acik " +
      "kalmiyor: kare alinirken acilip hemen kapaniyor",
      toggleBox((patch.camera || {}).enabled ?? state.camera.enabled,
                (v) => set("camera", "enabled", v))
    ));

    pane.append(el("p", "pane-note",
      t("Goruntuyu modelin anlamasi ayri bir mesele: yerel modellerin cogu " +
      "goruntu kabul etmiyor. Claude ve GPT ediyor.")));
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
    head(pane, "Kameralar", "İzlenen kameralar — hareket görülünce modele soru gider.");

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
    // Satir detayinin icine gomuluyor; kendi kart cercevesi tasimiyor.
    const box = el("div");
    const draft = { action: "add", source: "0", sensitivity: 0.06, cooldown_s: 60 };

    box.append(field("Yeni kamera", "", text("", (v) => (draft.name = v), t("Giris kapisi"))));
    box.append(field("Kaynak", "Yerel kamera icin 0, 1 … · ag kamerasi icin tam adres",
                     text("0", (v) => (draft.source = v), "rtsp://192.168.1.10/stream")));
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
    drawSkills(answer);
    // Ana ekrandaki organ halkası da tazelensin: buradan silinen bir
    // yeteneğin sahnede durmaya devam etmesi, iki ayrı gerçek demek.
    if (typeof loadOrgans === "function") loadOrgans();
  }

  // --- kompakt satirlar -------------------------------------------------
  //
  // Kart yerine satir: kartlar uc kayitta guzeldi, on bes yetenekte sayfa
  // yonetilemez bir duvara donuyor. Bir kayit tek satir; detay tiklayinca
  // satirin altina acilir — sayfa yalnizca bakilan seye yer harcar.

  function row(opts) {
    const line = el("div", "row" + (opts.click ? " click" : ""));
    line.append(el("span", "row-dot" + (opts.state ? " " + opts.state : "")));
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

  function drawSkills(data) {
    const pane = panes.skills;
    pane.textContent = "";
    head(pane, "Yetenekler", "neo'nun araç olarak yüklediği betikler.");

    if (data.error) pane.append(el("p", "pane-note bad", data.error));

    const list = el("div", "rows");
    for (const skill of data.skills || []) {
      const line = row({
        name: skill.name,
        desc: (skill.description || "").split("\n")[0],
        acts: [
          [t("Düzenle"), () => editSkill(skill.name, line)],
          [t("Sil"), () => loadSkills({ action: "remove", name: skill.name }), true],
        ],
      });
      line.title = skill.path;
      list.append(line);
    }

    for (const problem of data.broken || []) {
      const line = row({ name: t("yüklenemedi"), desc: problem.split("\n")[0], state: "bad" });
      line.title = problem;
      list.append(line);
    }

    const adder = row({ name: t("＋ Yeni yetenek"), state: "off", click: true });
    adder.addEventListener("click", () => detail(adder, (box) => {
      const nameBox = el("input", "input-text");
      nameBox.placeholder = t("ad — ör. rapor_ozeti");
      const descBox = el("input", "input-text");
      descBox.placeholder = t("ne işe yarar, ne zaman kullanılmalı");
      const make = action(t("Oluştur"), () => {
        if (!nameBox.value.trim()) { say("Yeteneğe bir ad ver", true); return; }
        loadSkills({
          action: "new",
          name: nameBox.value.trim(),
          description: descBox.value.trim(),
        });
      });
      make.classList.add("add");
      box.append(nameBox, descBox, make);
      nameBox.focus();
    }));
    list.append(adder);
    pane.append(list);

    pane.append(el("p", "pane-note",
      t("Kaydedilen yetenek anında araç olarak yüklenir; silinen hem dosyadan " +
      "hem defterden gider. Standart yetenekler ilk açılışta gelir — silersen " +
      "geri gelmez. neo da iş sırasında kendine yetenek yazar.")));
  }

  // Yetenek düzenleyici: dosyanın tamamı satırın altında bir kod alanında.
  // Kaydet anında yükler; hata varsa o an söylenir.
  async function editSkill(name, line) {
    const open = line.nextElementSibling;
    if (open && open.classList.contains("row-detail")) {
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
    } catch { say("Dosya okunamadı", true); return; }
    if (!answer.ok) { say(answer.error || "Dosya okunamadı", true); return; }

    detail(line, (box) => {
      const area = el("textarea", "input-text input-area");
      area.rows = 16;
      area.spellcheck = false;
      area.value = answer.code || "";
      const keep = action(t("Kaydet ve yükle"), () =>
        loadSkills({ action: "write", name, code: area.value }));
      keep.classList.add("add");
      box.append(area, keep);
    });
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

  function drawConnectors(data) {
    const pane = panes.connectors;
    pane.textContent = "";
    head(pane, "Bağlantılar", "Dış araç sunucuları (MCP).");

    for (const problem of data.problems || []) {
      pane.append(el("p", "pane-note bad", problem));
    }

    const list = el("div", "rows");
    for (const server of data.servers || []) {
      const acts = [];
      // OAuth yalnızca uzak sunucularda: 401 dönen sunucu için tarayıcıda
      // giriş; girişliyken çıkış jetonları siler.
      if (server.kind === "http" && !server.auth) {
        acts.push([t("Giriş yap"), () => loadConnectors({ action: "login", name: server.name })]);
      }
      if (server.auth) {
        acts.push([t("Çıkış"), () => loadConnectors({ action: "logout", name: server.name }), true]);
      }
      acts.push([t("Kaldır"), () => {
        let current = {};
        try { current = JSON.parse(data.raw || "{}"); } catch { current = {}; }
        const servers = current.mcpServers || current;
        delete servers[server.name];
        loadConnectors({ action: "save", raw: JSON.stringify(current, null, 2) });
      }, true]);
      const line = row({
        name: server.name,
        desc: (server.kind === "http" ? t("adres · ") : t("komut · ")) + server.where,
        meta: (server.auth ? t("girişli · ") : "") +
              (server.ok ? server.tools.length + t(" araç") : t("bağlanamadı")),
        state: server.ok ? "" : "bad",
        click: true,
        acts,
      });
      // Bağlanamayan sunucuda çare düğmesi (Giriş yap) hover beklemesin:
      // kullanıcı düğmeyi görmezse hata çözümsüz görünüyor.
      if (!server.ok) line.classList.add("stay");
      // Detay tiklayinca: araclarin tam listesi ya da baglanti hatasi.
      line.addEventListener("click", () => detail(line, (box) => {
        if (server.ok) {
          box.append(el("p", "job-prompt dim",
            server.tools.length ? server.tools.join("\n") : t("araç bildirmedi")));
        } else {
          box.append(el("p", "pane-note bad", server.error || t("sebep bilinmiyor")));
        }
      }));
      list.append(line);
    }

    // Yeni bağlantı: tür seçimi + iki üç alan. JSON bilmeden ekleme yolu
    // bu; mcp.json editörü güç kullanıcıya kalıyor.
    const adder = row({ name: t("＋ Yeni bağlantı"), state: "off", click: true });
    adder.addEventListener("click", () => detail(adder, (box) => {
      let kind = "oauth";

      const kinds = el("div", "choices");
      const KINDS = [
        ["oauth", "Uzak — girişli", "adres yeter; kaydedince tarayıcıda giriş açılır"],
        ["token", "Uzak — sabit token", "token dosyaya değil Anahtarlar'a yazılır"],
        ["stdio", "Yerel komut", "npx / py gibi bir komut başlatılır (LM Studio biçimi)"],
      ];
      const nameBox = el("input", "input-text");
      nameBox.placeholder = t("ad — ör. notion");
      const urlBox = el("input", "input-text");
      urlBox.placeholder = "https://…/mcp";
      const tokenBox = el("input", "input-text");
      tokenBox.type = "password";
      tokenBox.placeholder = t("token — Anahtarlar'a kaydedilir, dosyaya adı yazılır");
      const cmdBox = el("input", "input-text");
      cmdBox.placeholder = t("komut ve argümanlar — ör. npx -y bir-mcp");

      const fit = () => {
        urlBox.hidden = kind === "stdio";
        tokenBox.hidden = kind !== "token";
        cmdBox.hidden = kind !== "stdio";
      };
      for (const [id, label, hint] of KINDS) {
        const card = el("button", "choice" + (id === kind ? " on" : ""));
        card.type = "button";
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

      const make = action(t("Ekle ve bağlan"), async () => {
        const name = nameBox.value.trim().toLowerCase();
        if (!/^[a-z0-9_-]+$/.test(name)) {
          say("Ad gerekli: yalnızca harf, rakam, - ve _", true);
          return;
        }
        let entry;
        if (kind === "stdio") {
          const parts = cmdBox.value.trim().split(/\s+/).filter(Boolean);
          if (!parts.length) { say("Komut boş", true); return; }
          entry = { command: parts[0], args: parts.slice(1) };
        } else {
          const where = urlBox.value.trim();
          if (!/^https?:\/\//.test(where)) { say("Adres http(s):// ile başlamalı", true); return; }
          entry = { url: where };
          if (kind === "token") {
            const secret = tokenBox.value.trim();
            if (!secret) { say("Token boş", true); return; }
            // Token mcp.json'a değil Anahtarlar'a: dosya sürüm kontrolüne
            // girebilir, gizli değer giremez.
            const env = name.toUpperCase().replace(/[^A-Z0-9]/g, "_") + "_MCP_TOKEN";
            const kept = await post("/api/settings", { keys: { [env]: secret } });
            if (!kept || kept.ok === false) {
              say((kept && kept.error) || "Token kaydedilemedi", true);
              return;
            }
            entry.headers = { Authorization: "Bearer ${" + env + "}" };
          }
        }

        let current = {};
        try { current = JSON.parse(data.raw || "{}"); } catch { current = {}; }
        if (!current.mcpServers || typeof current.mcpServers !== "object") {
          current = { mcpServers: current.mcpServers || {} };
        }
        current.mcpServers[name] = entry;
        await loadConnectors({ action: "save", raw: JSON.stringify(current, null, 2) });
        // Girişli sunucuda kayıttan sonra giriş kendiliğinden başlıyor:
        // "ekle, sonra bir de Giriş yap'ı bul" iki adımdı, bu tek adım.
        if (kind === "oauth") loadConnectors({ action: "login", name });
      });
      make.classList.add("add");
      box.append(kinds, nameBox, urlBox, tokenBox, cmdBox, make);
      nameBox.focus();
    }));
    list.append(adder);

    const editRow = row({
      name: "mcp.json",
      desc: t("sunucu tanımlarını düzenle"),
      state: "off",
      click: true,
      acts: [[t("Yeniden bağlan"), () => loadConnectors({ action: "reload" })]],
    });
    editRow.addEventListener("click", () => detail(editRow, (box) => {
      box.append(el("p", "pane-note",
        t("Biçim Claude Code'unkiyle aynı (mcpServers): yerel sunucu için " +
        "command/args, uzak sunucu için url/headers. Gizli değeri dosyaya " +
        "yazma — \"${AD}\" yaz, değeri Anahtarlar sekmesine AD adıyla ekle.")));
      const area = el("textarea", "input-text input-area");
      area.rows = 12;
      area.spellcheck = false;
      area.value = data.raw || "";
      box.append(area);
      const keep = action(t("Kaydet ve bağlan"), () =>
        loadConnectors({ action: "save", raw: area.value }));
      keep.classList.add("add");
      box.append(keep);
    }));
    list.append(editRow);
    pane.append(list);

    // Hiç sunucu yokken ekleme formu açık gelsin: boş listeye bakmak yol
    // göstermiyor, ham JSON editörü de ilk karşılama değil.
    if (!(data.servers || []).length) adder.click();
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
      return;
    }

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

  // --- makine -----------------------------------------------------------
  //
  // Yerel bir modelde asıl sınır makinenin kendisi. Buradaki üç ayar da
  // gerçekten yaşanmış bir soruna karşılık geliyor.

  function drawMachine() {
    const pane = panes.machine;
    pane.textContent = "";
    head(pane, "Makine", "Eşzamanlılık, arayüz dili, tarayıcı ve dış kapı.");

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
      "aday sınav kapısında çöpe gider",
      taniAnahtar
    );
    pane.append(taniAlan);
    fetch("/api/tanima").then((r) => r.json()).then((d) => {
      taniAnahtar.checked = !!d.on;
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

    pane.append(field(
      "Atölye klasörü",
      t("Ajanın kendi alanı — yazma yalnızca burada serbest. " +
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

  async function save() {
    if (!Object.keys(patch).length) { say("Değişiklik yok"); return; }
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
    draw();
  }

  // --- bağlama ----------------------------------------------------------

  document.getElementById("gear").addEventListener("click", toggle);
  document.getElementById("settings-close").addEventListener("click", close);
  document.getElementById("settings-save").addEventListener("click", save);

  document.getElementById("tabs").addEventListener("click", (ev) => {
    const name = ev.target.dataset ? ev.target.dataset.tab : null;
    if (!name) return;
    for (const button of ev.currentTarget.children) {
      button.classList.toggle("on", button === ev.target);
    }
    for (const [key, pane] of Object.entries(panes)) pane.hidden = key !== name;
    if (name === "files") browse(here ?? state.sandbox.directory);
    if (name === "tasks") loadTasks();
    if (name === "eyes") loadCameras();
    if (name === "devices") loadDevices();
    if (name === "place") drawPlace();
    if (name === "skills") loadSkills();
    if (name === "connectors") loadConnectors();
  });

  return { open, close, toggle };
})();
