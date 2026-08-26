// Sohbet, canlı akış ve onay.
// Sunucuyla iki kanal: POST ile komut gider, SSE ile her şey geri gelir.

// Bu dosyanın kullanıcıya gösterdiği metinlerin İngilizceleri. Kaynak
// metin Türkçe kalıyor; görüntüleme noktasında t("...") ile çevriliyor.
Dil.ekle({
  "Ses su an uretilemiyor — ses servisine ulasilamiyor olabilir (internet gerekli). Metin ekranda; ses duzelince kendiliginden devam eder.":
    "Speech is unavailable right now — the voice service may be unreachable (internet required). The text stays on screen; audio resumes once the service is back.",
  // Araya girme ve yardımcı onayı
  "araya girdi": "interjected",
  "yardımcı": "helper",
  // Karşılama
  "Ne yapmamı istersin?": "What would you like me to do?",
  "Bilgisayarında çalışıyorum. Öğrendiklerim etrafımdaki ağa yazılıyor.":
    "I work on your computer. What I learn is woven into the web around me.",
  // Durum şeridi ve kipler
  "Hazır": "Ready", "Uyanıyor": "Waking", "Çalışıyor": "Working",
  "Düşünüyor": "Thinking", "Yazıyor": "Writing", "Hatırlıyor": "Recalling",
  "Konuş…": "Talk…",
  "Model yükleniyor…": "Loading model…",
  "Sunucu yok": "No server",
  "Bağlantı koptu": "Connection lost",
  // Dönen düşünme kelimeleri
  "Tartıyor": "Weighing", "Evirip çeviriyor": "Mulling",
  "Kurcalıyor": "Tinkering", "Süzüyor": "Sifting", "Demliyor": "Brewing",
  "Yokluyor": "Probing", "Harmanlıyor": "Blending",
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
  "Tıkla — muhakemenin tamamını gör": "Click to see the full reasoning",
  "Tıkla — tamamını gör": "Click to see all",
  "Hatırlananlar — tıkla, tamamını gör": "Recalled — click to see all",
  "Devamı": "More", "Kısalt": "Collapse",
  "Sırada": "Queued",
  " argüman": " arguments",
  // Kamera ve ses
  "Kamera açılıyor…": "Opening camera…",
  "Kamera açılamadı. İzin verilmemiş ya da başka bir program kullanıyor olabilir.":
    "Camera could not be opened. Permission may be missing or another program may be using it.",
  "Bakıyor…": "Looking…",
  "Ses duyuyor": "Hearing sound",
  "Gönderilen görsel": "Attached image",
  "Elle konuş (arkada zaten dinliyor)": "Push to talk (already listening in the background)",
  "Tıkla ve konuş": "Click and talk",
  "Sesi kapat": "Mute voice", "Sesi aç": "Unmute voice",
  // Kompozer + menüsü ve ekler
  "Dosya ekle": "Add file", "belge, görsel, veri": "document, image, data",
  "Kameradan kare": "Camera frame", "önizlemeyi aç": "open the preview",
  "Bağlantılar": "Connectors", "MCP sunucuları": "MCP servers",
  "Yetenekler": "Skills", "kendi araçların": "your own tools",
  "Yeni görev": "New task", "zamanlanmış iş": "scheduled job",
  "Listeden çıkar": "Remove from list",
  "Konuşulan": "Talking about", "Bağlamdan çıkar": "Remove from context",
  // Yetki
  "Yetki: ": "Access: ",
  " — hiçbir şey sorulmuyor": " — nothing is asked",
  " · tıkla: tam yetki": " · click: full access",
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
  "Sorgu": "Query", ". sicrama": ". hop", "Bakildi": "Glanced",
  " kayda daha bakıldı": " more records glanced",
});

const $ = (id) => document.getElementById(id);
const thread = $("thread"), input = $("input"), overlay = $("overlay");
const statusEl = $("status"), metaEl = $("meta"), stopBtn = $("stop");

let agentLine = null;      // akmakta olan cevabın kabı
let busy = false;
let approvalId = null;
let lastQuery = "";

Scene.init({
  canvas: $("scene"), probe: $("probe"), reveal: $("reveal"),
  onRoute: renderRoute,
});
Scene.load();

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
  w.append(h, p);
  thread.append(w);
}

const scroll = () => { thread.scrollTop = thread.scrollHeight; };

function line(kind, text) {
  clearWelcome();
  const el = document.createElement("div");
  el.className = "line " + kind;
  if (text) el.textContent = text;
  thread.append(el);
  scroll();
  return el;
}

// Sürdürülen bir konuşmanın geçmiş dökümünü thread'e basar: kullanıcı
// kaldığı yeri görsün, yeni mesaj oraya eklensin.
async function loadTranscript(id) {
  let data;
  try { data = await (await fetch("/api/session?id=" + encodeURIComponent(id))).json(); }
  catch { return; }
  for (const t of (data.turns || [])) {
    if (t.role === "user") { line("user", t.text); continue; }
    // Ajan satırları geçmişte de MARKDOWN: düz textContent basmak
    // "**kalın**" ve backtick'leri çıplak gösteriyordu — canlı akışta
    // render edilen konuşma, geçmişten yüklenince bozuk görünüyordu.
    const el = line("agent", "");
    Markdown.into(el, t.text || "");
    el.classList.add("done");
  }
  scroll();
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
  setStatus(ready ? "ready" : "busy", stage || (ready ? t("Hazır") : t("Uyanıyor")));

  input.disabled = !ready;
  input.placeholder = ready ? t("Konuş…") : (stage || t("Uyanıyor")) + "…";
  $("send").disabled = !ready;
  if (ready) input.focus();
}

function setBusy(value) {
  busy = value;
  stopBtn.hidden = !value;
  // Düğme yalnızca meşgulken kilitlenir. Boş metni send() zaten eliyor;
  // kilidi metnin varlığına bağlamak, değer programatik değiştiğinde
  // (yapıştırma, otomatik doldurma, IME) düğmeyi kilitli bırakıyordu.
  // Meşgulken de yazılabiliyor: gönderilen mesaj sıraya giriyor.
  $("send").disabled = !ready;
  setMode(value ? "thinking" : "idle");
  waiting(value);
  // Canlı "yaşıyor" sayacı meşgul olduğu sürece ilerlesin, bitince dursun.
  if (value) startBusyTicker(); else stopBusyTicker();
  if (!value) sealLine();
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
  read_file: "Okuyor", list_dir: "Bakıyor", write_file: "Oluşturuyor",
  edit_file: "Düzenliyor", copy_in: "Kopyalıyor", draw: "Çiziyor",
  shell: "Çalıştırıyor",
  mind_recall: "Hatırlıyor", mind_memory: "Aklına yazıyor", mind_goals: "Planlıyor",
  screen: "Ekrana bakıyor", hand: "Bilgisayarı kullanıyor", look: "Bakıyor",
  browser: "İnternette geziniyor",
  device: "Cihaza bağlanıyor", skill: "Yetenek yazıyor", models: "Model seçiyor",
  task: "Yardımcı çalıştırıyor", schedule: "Zamanlıyor",
  mail_read: "Posta okuyor", mail_send: "Posta gönderiyor", place: "Konuma bakıyor",
};

// Araç satırının simgesi. Model seçmiyor, tür sabit eşleniyor: simgenin işi
// süslemek değil, satırlar taranırken türün bir bakışta ayrılması.
const TOOL_ICON = {
  shell: "❯", read_file: "≡", list_dir: "≡", write_file: "✎", edit_file: "✎",
  copy_in: "✎", draw: "✎", search: "◌", fetch: "◌", web: "◌",
  mind_recall: "◍", mind_memory: "◍", mind_goals: "◍",
  screen: "▣", hand: "▣", look: "◉", browser: "⌾", device: "⇄", skill: "✦",
  models: "✦", task: "⑃", schedule: "◔", mail_read: "✉", mail_send: "✉",
  place: "⌖",
};

// Dönen düşünme kelimeleri. Yapay zekâ yok — sabit listeden birkaç saniyede
// bir sıradaki; sıfır maliyet ama algılanan "canlılığın" çoğunu bu taşıyor.
// İlk kelime her turda "Düşünüyor": tanıdık olan önce, oyun sonra.
const MULL = ["Düşünüyor", "Tartıyor", "Evirip çeviriyor", "Kurcalıyor",
              "Süzüyor", "Demliyor", "Yokluyor", "Harmanlıyor"];
let mullTick = 0;

function mull() {
  // Çeviri burada, görüntüleme noktasında: MULL tanımı Türkçe kalıyor.
  return t(MULL[Math.floor(mullTick / 3) % MULL.length]);
}

let modeTimer = null;

// Yerel sunucular modeli ilk istekte belleğe yüklüyor ve bu 20-60 saniye
// sürebiliyor. O sürede hiçbir şey akmıyor; ekranda "düşünüyor" yazması
// yanlış — düşünmüyor, yükleniyor. Bir şey akmadan bu süre geçerse durum
// satırı bunu söylüyor.
const WAITING_AFTER = 4000;
let waitTimer = null;

function waiting(on) {
  clearTimeout(waitTimer);
  if (!on) return;
  waitTimer = setTimeout(() => {
    if (busy) setStatus("busy", t("Model yükleniyor…"));
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
  if (!agentLine) { agentLine = line("agent", ""); raw = ""; }
  raw += chunk;
  bumpStream(chunk);
  if (pending) return;
  pending = setTimeout(() => {
    pending = null;
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
  // Yeni tur: ara-anlatım güvenlik ağı bayrakları da sıfırdan.
  lastNarr = ""; answerKept = false;
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
  const s = Math.round((Date.now() - turnStart) / 1000);
  busyNote = s + " sn";
  showMeta();
  if (!work) return;
  // Açık araç satırlarının canlı süresi ("SHELL … 8 sn").
  const openRows = [...work.open.values()];
  for (const row of openRows) {
    if (!row._start) continue;
    const t = Math.round((Date.now() - row._start) / 1000);
    const took = row.querySelector(".took");
    if (took) took.textContent = t + " sn";
  }
  // İş başlığı: bir araç çalışıyorsa adı + süresi; cevap akıyorsa (üst sayaç
  // zaten canlı) dokunma; ikisi de yoksa model adım üretiyor → düşünme süresi.
  if (openRows.length) {
    const first = openRows[0];
    const name = first.querySelector(".who").textContent;
    const t = Math.round((Date.now() - (first._start || work.since)) / 1000);
    workHead(name + " · " + t + " sn");
  } else if (!agentLine) {
    workHead(mull() + since(work.since) + streamNote());
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
function think(chunk) {
  const w = ensureWork();
  if (!w.thought) {
    w.thought = document.createElement("div");
    w.thought.className = "act note think";
    w.body.append(w.thought);
    w.thinkStart = Date.now();
    thought = "";
  }
  thought += chunk;
  bumpStream(chunk);
  // Ekrana yalnızca KUYRUK yazılıyor: akan muhakemenin son birkaç cümlesi.
  // Tam metni her parçada baştan basmak hem O(n²) hem de şeridi devasa
  // yapıyordu; tamamı blok kapanınca tek satıra katlanıyor ve tıklayınca
  // açılıyor (aşağıda closeThought).
  const tail = thought.length > 600 ? "…" + thought.slice(-600) : thought;
  w.thought.textContent = tail.trim();
  workHead(mull() + since(w.since) + streamNote());
  // Muhakeme kutusu kendi içinde en alta kaysın: en son cümle görünür kalsın
  // ama sayfa aşağı zıplamasın. Detay açıkken sayfayı itmek, kullanıcının
  // yukarı çıkıp başlığı kapatmasını imkânsız kılıyordu.
  w.thought.scrollTop = w.thought.scrollHeight;
  if (w.body.hidden) scroll();   // katlıyken alta bak; açıkken kullanıcıya bırak
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
      if (!full) box.remove();
      else {
        const secs = Math.round((Date.now() - (work.thinkStart || work.since)) / 1000);
        const words = full.split(/\s+/).length;
        const label = t("✻ Düşündü") + (secs > 0 ? " · " + secs + " sn" : "")
                    + " · " + words + t(" kelime");
        box.classList.add("done");
        box.textContent = label;
        box.title = t("Tıkla — muhakemenin tamamını gör");
        let open = false;
        box.onclick = (ev) => {
          ev.stopPropagation();
          open = !open;
          box.textContent = open ? full : label;
          box.classList.toggle("open", open);
        };
      }
    }
    work.thought = null;
  }
  thought = "";
}

// Uzun bir cevabın tamamı ekranda durunca sonuç kayboluyor. Tur bitince
// ilk paragraf açıkta kalıyor, gerisi "devamı" ile katlanıyor: kullanıcı
// sonucu okuyup geçebiliyor, isterse alta inip nasıl varıldığına bakıyor.
// Bundan uzun bir cevap katlanıyor. Eşik yükseltildi: ara anlatım artık
// şeride giriyor ve burada kalan şey cevabın kendisi — onu erkenden
// katlamak "ne dediği belli değil" demek oluyordu.
const FOLD_AFTER = 1400;

// Akmakta olan metin bloğunu kapatır ve ekranda bırakır.
function finishAgentLine() {
  clearTimeout(pending);
  pending = null;
  if (!agentLine) return;

  // Model araç çağırmadan önce sık sık boşluk akıtıyor; bu bomboş bir
  // satır bırakıyordu.
  if (!raw.trim()) agentLine.remove();
  else {
    Markdown.into(agentLine, raw);
    agentLine.classList.add("done");
    if (raw.length > FOLD_AFTER) fold(agentLine);
    answerKept = true;   // ekranda tam boy bir cevap kaldı: güvenlik ağı gerekmez
  }
  agentLine = null;
  raw = "";
}

function sealLine() {
  closeThought();
  closeWork();
  finishAgentLine();
  // Güvenlik ağı: tur bir araçla bitti ve ekranda tam boy bir cevap kalmadıysa
  // (ör. model son sözünü söyleyip ardından mind_memory çağırdı, o metin şeride
  // katlandı), son ara-anlatımı cevap olarak göster — yoksa kullanıcı yalnızca
  // kapalı şeridi görüp "cevap nerede" derdi.
  if (!answerKept && lastNarr) {
    const row = line("agent", "");
    Markdown.into(row, lastNarr);
    row.classList.add("done");
    answerKept = true;
  }
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
$("composer").addEventListener("submit", (ev) => { ev.preventDefault(); send(); });

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
  const posted = withContext(withFiles(text));
  // Gönderilen görsel ve dosyalar SSE echo'sunda taşınmıyor (görüntü ağır,
  // ayrıca araçtan gelen kareler `internal`). İstemci elindeki veriyle:
  // mesaj satırı geldiğinde küçük resmi ve dosya etiketlerini ona iliştir.
  if (frame || attached.length) {
    pendingMedia.set(posted, { frame, files: attached.map(a => a.name) });
  }
  post("/api/chat", { text: posted, image: frame });
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

// Kamera düğmesi önizlemeyi açıyor, doğrudan kare almıyor: ne gönderdiğini
// görmeden göndermek, kameranın ne yakaladığını bilmemek demek.
$("cam").addEventListener("click", async () => {
  if (Camera.on) { Camera.close(); return; }
  setStatus("busy", t("Kamera açılıyor…"));
  const opened = await Camera.open();
  setStatus(busy ? "busy" : "ready", busy ? t("Çalışıyor") : t("Hazır"));
  if (!opened) line("alert", t("Kamera açılamadı. İzin verilmemiş ya da başka bir program kullanıyor olabilir."));
});

$("lens-snap").addEventListener("click", () => Camera.snap());
$("lens-close").addEventListener("click", () => Camera.close());

// --- kompozer + menüsü --------------------------------------------------
//
// Ekleme kısayolları tek yerde: dosya, kamera, ve ilgili ayar sekmeleri.
// Claude Code'daki + menüsünün karşılığı — kompozerden çıkmadan.
$("plus").addEventListener("click", () => {
  const pop = $("plus-pop");
  if (!pop.hidden) { pop.hidden = true; return; }
  pop.textContent = "";

  const openTab = (name) => {
    $("gear").click();
    const tab = document.querySelector('[data-tab="' + name + '"]');
    if (tab) tab.click();
  };
  const items = [
    ["Dosya ekle", "belge, görsel, veri", () => $("file-input").click()],
    ["Kameradan kare", "önizlemeyi aç", () => $("cam").click(), () => !$("cam").hidden],
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
    chip.className = "chip";
    chip.textContent = item.name + " · " + size(item.bytes);
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

// Orkestra güvertesine köprü: modül yoksa (yüklenmemişse) sessiz geç.
function orchStart(e) { if (typeof Orchestra !== "undefined") Orchestra.start(e); }
function orchTool(e) { if (typeof Orchestra !== "undefined") Orchestra.tool(e); }
function orchEnd(e) { if (typeof Orchestra !== "undefined") Orchestra.end(e); }

function withContext(text) {
  if (!appContext) return text;
  const a = appContext;
  const kind = KIND_TR[a.type] || a.type;
  let line = `[Bağlam] Atölyendeki "${a.name}" adlı ${kind} üzerine konuşuyoruz (yol: ${a.path}).`;
  if (a.address) line += ` Şu an çalışıyor: ${a.address}.`;
  else if (a.url) line += ` Adres: ${a.url}.`;
  if (a.title) line += ` Tanım: ${a.title}.`;
  clearAppContext();
  return line + (text ? "\n\n" + text : "");
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
  else if (state === "basladi") tanimaKosuyor = true;
  else if (state === "bitti") { tanimaKosuyor = false; tanimaSon = new Date().toISOString(); }
  ikon.classList.toggle("kosuyor", tanimaKosuyor);
  ikon.title = tanimaKosuyor
    ? t("Şu an seni tanıyorum — eğitim arka planda sürüyor")
    : t("Beni tanı açık") + " · " + t("son eğitim") + ": " + tanimaTarih()
      + " · " + t("tıkla: şimdi eğit");
}

$("tanima-ikon").addEventListener("click", () => {
  // Koşarken tıklama sessizce yok sayılır: ipucu zaten durumu söylüyor,
  // ikinci bir koşu açmak da mümkün değil (süreç tekil).
  if (tanimaKosuyor) return;
  post("/api/tanima", { simdi: true });
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
  const move = (e) => {
    if (!active) return;
    const max = Math.min(window.innerWidth - 260, window.innerWidth * 0.6);
    const w = Math.max(240, Math.min(max, e.clientX));
    root.style.setProperty("--left-w", w + "px");
  };
  const stop = () => {
    active = false;
    document.body.classList.remove("left-resize");
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", stop);
  };
  document.addEventListener("pointerdown", (e) => {
    const grip = e.target.closest("[data-left-grip]");
    if (!grip) return;
    e.preventDefault();
    active = true;
    document.body.classList.add("left-resize");
    window.addEventListener("pointermove", move);
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
  const mic = $("mic");
  if (mic.hidden) return;
  // Python tarafındaki RMS daha küçük ölçekli; ikisi aynı görünsün diye
  // büyütülüyor.
  const shown = Math.min(1, level * 8);
  mic.style.setProperty("--level", shown.toFixed(3));
  mic.classList.toggle("hot", shown > 0.12);

  // Sahnedeki mikrofon organı da duyduğunu göstersin. Eşik düğmenin
  // eşiğinden yüksek: her nefes sahnede nabız attırmasın.
  if (shown > 0.3) Scene.use("mic", t("Ses duyuyor"));
}

function setListening(enabled, wake) {
  $("mic").hidden = !enabled;
  // Sürekli dinleme artık Python tarafında: tarayıcıda duramıyordu çünkü
  // pencere gizlendiğinde Chromium arka plan zamanlayıcılarını dakikaya
  // kısıyor ve dinleme ölüyor. Buradaki mikrofon düğmesi yalnızca elle
  // konuşmak için — sürekli dinleme onsuz da sürüyor.
  $("mic").title = wake ? t("Elle konuş (arkada zaten dinliyor)") : t("Tıkla ve konuş");
}

// Tıkla-konuş-tıkla. Basılı tutmak değildi: kullanıcı düğmeye tıklayıp
// bırakıyor, o da sıfır saniyelik bir kayıt üretip sessizce atılıyordu.
$("mic").addEventListener("click", async () => {
  const on = await Listen.toggle();
  $("mic").classList.toggle("live", Listen.mode === "push");
  if (on === false) return;
});

// --- ses ----------------------------------------------------------------
// Düğme yalnızca ses açıkken görünüyor: kapalıyken susturma düğmesi
// göstermek anlamsız. Susturmak ayarı değiştirmiyor, o anki konuşmayı
// kesiyor.

function setVoice(enabled) {
  Speech.enable(enabled);
  const button = $("mute");
  button.hidden = !enabled;
  button.classList.remove("off");
  button.title = t("Sesi kapat");
}

$("mute").addEventListener("click", () => {
  const next = !Speech.on;
  // Kapatmak o an konuşulanı da kesiyor: "sus" dendiğinde cümlenin bitmesini
  // beklemek istenen şey değil.
  Speech.enable(next);
  const button = $("mute");
  button.classList.toggle("off", !next);
  button.title = next ? t("Sesi kapat") : t("Sesi aç");
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

function setAuthority(next) {
  mode = next;
  const button = $("authority");
  button.classList.toggle("full", next === "yolo");
  button.title = t("Yetki: ") + (t(AUTHORITY[next]) || next) +
                 (next === "yolo" ? t(" — hiçbir şey sorulmuyor") : t(" · tıkla: tam yetki"));
  if (next !== "yolo") previous = next;
  // Kilit ile kompozer altındaki kip çipi aynı gerçeği göstersin.
  dockRender();
}

$("authority").addEventListener("click", async () => {
  const next = mode === "yolo" ? previous : "yolo";
  setAuthority(next);
  const answer = await post("/api/settings", { permissions: { mode: next } });
  // Sunucu reddederse ekranı gerçeğe döndür; sessizce yanlış göstermek,
  // kullanıcının tam yetki sandığı halde soruların gelmesi demek.
  if (answer && answer.ok === false) setAuthority(mode === "yolo" ? previous : "yolo");
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
function dockContext(promptTotal) {
  if (!contextWindow || !promptTotal) return;
  const pct = Math.min(100, Math.round((promptTotal / contextWindow) * 100));
  $("dock-ctx-pct").textContent = "%" + pct;
  $("dock-ctx-fill").style.width = pct + "%";
  const box = $("dock-ctx");
  box.classList.toggle("warn", pct >= 70 && pct < 90);
  box.classList.toggle("hot", pct >= 90);
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
        const answer = await post("/api/settings", { model: { name: item.id } });
        if (answer && answer.ok === false) { modelName = was; showMeta(); dockRender(); }
      }));
    }
    if (!shown) list.append(mk("div", "pop-note", t("Eşleşen yok.")));
  };
  search.addEventListener("input", paint);
  paint();
  placePop($("dock-model"));
  search.focus();
}

// Bağlam çipi: yüzdenin arkasındaki sayılar.
$("dock-ctx").addEventListener("click", () => {
  const pop = dockPop($("dock-ctx"));
  if (!pop) return;
  pop.append(mk("div", "pop-head", t("Bağlam")));
  const window_ = contextWindow;
  const used = lastUsage ? lastUsage.prompt_total : 0;
  const pct = window_ && used ? Math.min(100, Math.round(used / window_ * 100)) : 0;
  const bar = mk("div", "pop-bar");
  bar.append(mk("i"));
  bar.firstChild.style.width = pct + "%";
  pop.append(bar);
  const tr = (n) => (n || 0).toLocaleString("tr-TR");
  pop.append(mk("div", "pop-note", t("Pencere: ") + tr(window_) + t(" token — dolu: %") + pct));
  if (lastUsage) {
    pop.append(mk("div", "pop-note", t("Son istem: ") + tr(lastUsage.prompt_total) +
      (lastUsage.cache_read ? t(" (önbellekten ") + tr(lastUsage.cache_read) + ")" : "")));
    pop.append(mk("div", "pop-note", t("Son cevap: ") + tr(lastUsage.output) + t(" token")));
  } else {
    pop.append(mk("div", "pop-note", t("Bu oturumda henüz tur yok.")));
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

// --- iş şeridi --------------------------------------------------------
//
// Bir turda olan biten tek bir satırda toplanıyor: düşünme, araç çağrıları
// ve ara anlatım. Önceki hal her düşünme ve her araç için ayrı bir satır
// bırakıyordu; dört adımlık bir işte sohbet on beş satırlık bir merdivene
// dönüyor ve asıl okunacak şey olan cevap aralarda kayboluyordu.
//
// Ayrıntı kayboluyor değil, katlanıyor: başlığa tıklayınca hepsi açılıyor.

let work = null;   // { head, body, steps, since, thought, open }
let lastNarr = "";     // son katlanan ara-anlatım (tur araçla biterse cevaba yükseltilir)
let answerKept = false; // bu turda ekranda tam boy bir cevap kaldı mı

function ensureWork() {
  if (work) return work;
  clearWelcome();
  const head = document.createElement("div");
  head.className = "acts-head";
  const body = document.createElement("div");
  body.className = "acts-body";
  body.hidden = true;
  head.onclick = () => {
    body.hidden = !body.hidden;
    head.classList.toggle("open", !body.hidden);
    scroll();
  };
  thread.append(head, body);
  head.classList.add("busy");   // çalışıyor: başlık nabız atıyor
  work = { head, body, steps: 0, since: Date.now(), thought: null, open: new Map() };
  return work;
}

// Başlık her adımda tazeleniyor: çalışırken o an ne yapıldığı, bitince
// kaç adım sürdüğü.
function workHead(label) {
  if (work) work.head.textContent = label;
}

// "N adım" özeti. Test ham kaynağı grepliyor (steps + " adım") — birim
// ifadesi burada duruyor, İngilizce karşılığı da buradan çıkıyor.
const stepsWord = (steps) => Dil.mode === "en" ? steps + " steps" : steps + " adım";

function running() {
  if (!work || !work.open.size) return "";
  const row = [...work.open.values()][0];
  return row.querySelector(".who").textContent;
}

function closeWork() {
  if (!work) return;
  workHead(work.steps ? stepsWord(work.steps) + since(work.since)
                      : t("Düşündü") + since(work.since));
  work.head.classList.remove("busy");   // nabız durur
  work.head.classList.add("done");       // bitti: ✓
  work = null;
}

// Araçtan ÖNCE gelen metin ara anlatımdır — uzun olsa bile. Bir araç çağrısı
// takip ettiği için tanımı gereği "ara adım", nihai cevap değil. Eskiden
// uzunluğa bakılıyordu (140+ ise cevap sayılıp ekranda bırakılıyordu); ama çok
// konuşan yerel modeller her adımda paragraflarca "düşünce" yazınca sohbet
// sayfalarca "NEO" bloğuna boğuluyor, kullanıcı ne yukarıyı ne aşağıyı takip
// edebiliyordu ("sendeki gibi olsun, sayfalarca yazıyor, kontrol edilemez").
// Artık hepsi katlanan şeridin İÇİNE giriyor (başlığa tıkla → hepsi açılır).
// Nihai cevap — ardından araç GELMEYEN metin — buraya hiç uğramaz, sohbette
// tam boy kalır. Güvenlik ağı sealLine'da: tur bir araçla bitip ekranda hiç
// cevap kalmazsa son anlatım cevaba yükseltilir.
function foldNarration() {
  if (!agentLine || !work) return;
  const text = raw.trim();

  clearTimeout(pending);
  pending = null;
  agentLine.remove();
  agentLine = null;
  raw = "";
  if (!text) return;
  // Anlatım da kompakt: ilk satır açıkta, tamamı tıklayınca (markdown'la).
  // Çok konuşan model her araçtan önce paragraf yazınca şerit açıldığında
  // yine sayfalarca metin çıkıyordu.
  const note = document.createElement("div");
  note.className = "act note";
  const first = text.split("\n")[0];
  const short = first.length > 100 ? first.slice(0, 100) + "…" : first;
  note.textContent = short;
  if (short !== text) {
    note.title = t("Tıkla — tamamını gör");
    let open = false;
    note.onclick = (ev) => {
      ev.stopPropagation();
      open = !open;
      if (open) { note.textContent = ""; Markdown.into(note, text); }
      else note.textContent = short;
      note.classList.toggle("open", open);
    };
  }
  work.body.append(note);
  lastNarr = text;   // güvenlik ağı: tur araçla biterse bu cevaba yükseltilir
}

function actLine(e) {
  const w = ensureWork();
  foldNarration();
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
  const verb = t(ACTION[e.tool]) || e.tool;
  const who = document.createElement("span"); who.className = "who"; who.textContent = verb;
  who.title = e.tool;
  const what = document.createElement("span"); what.className = "what";
  what.textContent = summarize(e.input);
  const took = document.createElement("span"); took.className = "took";
  row.append(spark, who, what, took);

  w.body.append(row);
  row._start = Date.now();   // canlı süre için: ticker bunu saniyede bir günceller
  w.open.set(e.id, row);
  workHead(verb + "…");
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
    // Sonuç izi: araç satırının altına "⎿ ilk satır (+N satır)". Sunucu
    // özetliyor (executor._brief) — ham çıktı buraya hiç gelmiyor.
    if (e.summary) {
      const trace = document.createElement("div");
      trace.className = "act-result" + (e.error ? " err" : "");
      trace.textContent = "⎿ " + e.summary;
      row.after(trace);
    }
  }
  const name = running();
  workHead(name ? name + "…" : stepsWord(work.steps) + since(work.since));
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

// --- olay akışı -------------------------------------------------------
function handle(e) {
  switch (e.type) {
    case "assistant_delta":
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
    case "thinking_delta": waiting(false); think(e.text); setMode("thinking", undefined, 2500); break;

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
    case "araya": {
      const row = line("user", e.text);
      const badge = document.createElement("span");
      badge.className = "queue-badge araya";
      badge.textContent = t("araya girdi");
      row.appendChild(badge);
      break;
    }

    case "message":
      if (e.role === "user") {
        // Sırası geldi: bekleyen satır gerçek satırla değiştiriliyor.
        const at = waitingLines.findIndex((w) => w.text === e.text);
        if (at >= 0) { waitingLines[at].row.remove(); waitingLines.splice(at, 1); renumberQueue(); }
        sealLine();
        resetStream();          // yeni tur: canlı token sayacı sıfırdan
        const row = line("user", e.text);
        const media = pendingMedia.get(e.text);
        if (media) { attachMedia(row, media); pendingMedia.delete(e.text); scroll(); }
      }
      else if (e.role === "system") note(e.text);
      break;

    case "tool_start": {
      actLine(e);
      setMode("working", t(ACTION[e.tool]) || t("Çalışıyor"));
      // Aygıt kullanılıyorsa sahnede o organ canlanıyor: soluk duran
      // kamera ya da modül, çekirdekten gelen bir uyarıyla yanıyor.
      const limb = organFor(e.tool);
      if (limb) Scene.use(limb, summarize(e.input));
      // Ajan bir dosyaya dokunduysa panel o dosyaya geçsin:
      // "yazdım" cümlesini okumakla dosyayı görmek aynı şey değil.
      Viewer.watch(e.tool, e.input);
      break;
    }
    case "tool_end": {
      closeAct(e);
      Viewer.refresh(e.tool, e.path);
      if (busy) setMode("thinking");
      const done = organFor(e.tool);
      // İz hemen silinmiyor: sahnede birkaç saniye daha duruyor ki neyin
      // kullanıldığı okunabilsin.
      if (done) setTimeout(() => Scene.release(done), 4000);
      break;
    }
    case "tool_cancelled": closeAct({ ...e, error: true, ms: 0 }); break;

    // Oturum değişti (yeni ya da devam): thread temizlenir; devam eden bir
    // konuşmaysa geçmiş dökümü yüklenir ki kullanıcı kaldığı yeri görsün.
    case "session_reset": {
      thread.replaceChildren();
      waitingLines.length = 0;
      work = null; agentLine = null; raw = "";
      if (e.resumed && e.id) loadTranscript(e.id);
      else showWelcome();   // taze oturum: karşılama geri gelsin (boş ekran değil)
      if (typeof History !== "undefined") History.close();
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
    case "api_error": clearWelcome(); line("alert", e.detail); break;
    case "refusal": clearWelcome(); line("alert", t("Model bu isteği reddetti.")); break;
    case "interrupted":
      clearWelcome();
      // Sesi de kes: metin durup hoparlörün cümleyi bitirmeye devam
      // etmesi, sözü kesilmiş ama konuşmayı sürdüren biri gibi.
      Speech.stop();
      line("alert", t("Kesildi."));
      break;

    case "approval_request": askApproval(e); break;
    case "approval_done":
      if (e.id === approvalId) { overlay.hidden = true; approvalId = null; }
      break;

    case "status": setBusy(e.busy); break;
    case "waking": setWaking(e.stage, e.ready); break;

    // Orkestra: alt ajan kanalları (şef modu). Ana sohbete karışmıyorlar;
    // canlı olarak orkestra güvertesinde izleniyorlar.
    case "child_start": orchStart(e); break;
    case "child_tool": orchTool(e); break;
    case "child_end": orchEnd(e); break;
    // Python tarafındaki kulağın duyduğu seviye: mikrofon simgesi
    // canlanıyor, yani arkada dinlendiği görünüyor.
    case "level": showLevel(e.value); break;
    case "turn_end": sealLine(); Speech.flush(); break;

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
    case "goal_push": case "goal_status":
      Scene.ripple(); Scene.load(); break;

    // Ajan iki kaydı bilinçli olarak bağladı: ağda yeni bir köprü kuruldu.
    // Grafı tazelemek yetmiyor — kurulan bağın görünmesi gerekiyor.
    case "mind_link":
      Scene.ripple();
      Scene.load(() => Scene.bridge(e.src, e.dst));
      note(t("Köprü: ") + (e.reason || t("bağlandı")));
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
        dockContext(e.prompt_total);
        lastUsage = e;
      }
      break;
  }
}

// Akış bağlantısı. Tek olması şart: `onerror` bir kopmada birden çok kez
// tetiklenebiliyor ve her biri yeni bir bağlantı açtırınca aynı olay iki üç
// kez işleniyordu. Metinde fark edilmiyor (aynı harf iki kez eklenince
// gözden kaçıyor) ama **ses iki kez çalıyor** — kopyalanan kuyruk.
let stream = null;
let retry = null;

function connect() {
  if (stream) { stream.close(); stream = null; }
  clearTimeout(retry);

  const source = new EventSource("/api/events");
  stream = source;
  // Hata ayıklama için erişilebilir olsun: açık SSE bağlantısı "ağ boşta"
  // bekleyen araçları süresiz bloke ediyor.
  window.__stream = source;

  source.onopen = () => setBusy(busy);
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
    modelName = s.model || "";
    showMeta();
    setVoice(!!s.voice);
    Speech.setCharacter(s.character);
    setListening(!!s.listen, !!s.wake);
    $("cam").hidden = !s.camera;
    if (s.mode) { previous = s.mode; setAuthority(s.mode); }
    dockEffort = s.effort || "";
    contextWindow = Number(s.context_window) || 0;
    dockRender();
    // Süren oturumun son kullanımı: yenilenen sayfa kaldığı yerden başlasın.
    if (Number(s.prompt_total)) {
      dockContext(Number(s.prompt_total));
      if (!lastUsage) lastUsage = { prompt_total: Number(s.prompt_total) };
    }
    // Yenileme oturumu bitirmiyor: sayfa hangi sebeple yenilenirse yenilensin
    // (dil değişimi, F5) süren konuşmanın dökümü geri gelsin. Eskiden yenileme
    // sonrası ekran bomboş açılıyordu — oysa oturum sunucuda sürüyordu.
    // Döküm boşsa karşılama zaten yerinde duruyor: loadTranscript boş dökümde
    // thread'e dokunmuyor, ilk satır çizilirken karşılama kendiliğinden kalkıyor.
    if (s.session) loadTranscript(s.session);
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
