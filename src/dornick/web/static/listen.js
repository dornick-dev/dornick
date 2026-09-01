// Mikrofon.
//
// İki kip var ve ikisi de aynı boruyu kullanıyor:
//
//   bas-konuş     mikrofon düğmesine basılı tut, konuş, bırak. Söylediğin
//                 yazı alanına düşüyor — göndermeden önce düzeltebilirsin.
//   uyandırma     sürekli dinleme açıkken kısa parçalar sunucuya gidiyor;
//                 içinde "dornick" geçen bir parça oturumu açıyor ve sözden
//                 sonrası doğrudan gönderiliyor.
//
// Tanıma sunucuda ve yerel: ses bilgisayardan çıkmıyor. Tarayıcının kendi
// `SpeechRecognition` API'si kullanılmıyor — WebView2'de yok, olduğu yerde
// de sesi Google'a gönderiyor.
//
// Mikrofon kendiliğinden açılmıyor. Kullanıcı düğmeye basana kadar
// `getUserMedia` hiç çağrılmıyor; sürekli dinleme de ayrı bir karar.

const Listen = (() => {
  // Uyandırma kipinde parça uzunluğu. Kısası daha çabuk tepki ama daha çok
  // tanıma; uzunu tersi. 3 saniye ikisinin arasında duruyor.
  const CHUNK_MS = 3000;

  // Aynı anda tek çözümleme. Bu olmadan her parça yeni bir istek açıyordu ve
  // ilk istek modeli indirirken (bir kez, ~70 sn) arkasına yenileri
  // diziliyordu. Tarayıcı bir kaynağa aynı anda altı bağlantı açabiliyor;
  // dolunca **her şey** sıraya giriyor — yazdığın mesaj bile gitmiyor.
  let busy = false;

  // Bu seviyenin altındaki kayıtta konuşma yok sayılıyor. Baytla ölçmek
  // yanıltıcıydı: opus sessizliği neredeyse hiç yer kaplamıyor ama kısa bir
  // "evet" de küçük bir dosya. Eşik düşük tutuldu — kaçırmaktansa arada bir
  // sessizlik göndermek yeğ.
  const SILENT = 0.008;

  // Sesin duyulup duyulmadığı görünmeli. "Konuştum ama hiçbir şey olmadı"
  // durumunda kabahat mikrofonda mı, tanımada mı, yoksa kayıt hiç mi
  // başlamadı — ölçer olmadan ayırt edilemiyor.
  const METER_HZ = 24;



  let stream = null;
  let recorder = null;
  let chunks = [];
  let mode = "off";          // off | push | wake
  let onText = () => {};
  let onCommand = () => {};
  let onState = () => {};
  let onLevel = () => {};

  // Seviye ölçer.
  let audio = null;
  let analyser = null;
  let meter = null;
  let peak = 0;

  function init(opts) {
    onText = opts.onText || onText;
    onCommand = opts.onCommand || onCommand;
    onState = opts.onState || onState;
    onLevel = opts.onLevel || onLevel;
  }

  async function mic() {
    if (stream) return stream;
    // Bu satır izin penceresini açıyor; kullanıcı istemeden buraya
    // gelinmiyor.
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    return stream;
  }

  function release() {
    stopMeter();
    if (recorder && recorder.state !== "inactive") recorder.stop();
    recorder = null;
    if (stream) {
      // Şeridi bırakmazsak tarayıcı "kayıt sürüyor" göstergesini açık
      // tutuyor ve mikrofon meşgul kalıyor.
      for (const track of stream.getTracks()) track.stop();
      stream = null;
    }
  }

  // --- seviye ölçer ------------------------------------------------------

  // Ölçer çalıştı mı? Çalışmadıysa seviyeye bakarak karar vermek yanlış:
  // hep sessizlik okuyor ve gerçekten konuşulan bir kayıt "ses duyulmadı"
  // diye atılıyordu.
  let metering = false;

  function startMeter() {
    if (analyser || !stream) return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      // Ses bağlamı kullanıcı hareketine kadar askıda başlıyor. Askıdayken
      // çözümleyici hep 128 (sessizlik) döndürüyor — ölçer sıfır gösteriyor
      // ve konuşulan kayıt bile "sessiz" sayılıyordu.
      if (audio.state === "suspended") audio.resume();
      analyser = audio.createAnalyser();
      analyser.fftSize = 512;
      audio.createMediaStreamSource(stream).connect(analyser);
      metering = true;
    } catch {
      analyser = null;
      metering = false;
      return;
    }

    const buffer = new Uint8Array(analyser.frequencyBinCount);
    peak = 0;
    meter = setInterval(() => {
      if (!analyser) return;
      analyser.getByteTimeDomainData(buffer);
      // Ortalama sapma: 128 sessizlik, uzaklık ses.
      let sum = 0;
      for (const value of buffer) sum += Math.abs(value - 128);
      const level = Math.min(1, sum / buffer.length / 40);
      peak = Math.max(peak, level);
      onLevel(level);
    }, 1000 / METER_HZ);
  }

  function stopMeter() {
    clearInterval(meter);
    meter = null;
    analyser = null;
    onLevel(0);
  }

  // Kayıtta konuşma var mı? Ölçer çalışmadıysa "var" sayılıyor: kararı
  // güvenilmeyen bir ölçüme dayandırıp kaydı atmak, sessizliği sunucuya
  // göndermekten çok daha kötü.
  const spoken = (loud) => !metering || loud === undefined || loud >= SILENT;

  // --- tıkla-konuş-tıkla -------------------------------------------------
  //
  // Basılı tutmak değil: kullanıcı düğmeye tıklıyor ve bırakıyor, o da
  // sıfır saniyelik bir kayıt üretip sessizce atılıyordu. Tıklamak
  // başlatıyor, tekrar tıklamak bitiriyor.

  async function toggle() {
    if (mode === "push") { stop(); return true; }
    return start();
  }

  async function start() {
    if (mode === "push") return true;
    try {
      await mic();
    } catch (err) {
      onState("Mikrofon açılamadı: " + (err && err.name ? err.name : "bilinmeyen"));
      return false;
    }

    // Uyandırma dinlemesi varsa duraklatılıyor: aynı şeridi iki kaydedici
    // paylaşamıyor.
    const listening = mode === "wake";
    mode = "push";
    chunks = [];
    startMeter();
    onState("Dinliyor");

    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (event) => chunks.push(event.data);
    recorder.onstop = () => {
      const loud = peak;
      stopMeter();
      send(new Blob(chunks, { type: "audio/webm" }), false, loud);
      // Uyandırma kipi kesildiyse geri dönsün.
      if (listening) { mode = "wake"; loop(); }
    };
    recorder.start();
    return true;
  }

  function stop() {
    if (mode !== "push") return;
    mode = "off";
    onState("Çözülüyor…");
    if (recorder && recorder.state !== "inactive") recorder.stop();
    // Şerit kapatılmıyor: art arda konuşulacaksa izni her seferinde
    // yeniden almak hem yavaş hem rahatsız edici.
  }

  // --- uyandırma ---------------------------------------------------------

  async function wake(on) {
    if (!on) {
      mode = "off";
      release();
      onState("");
      return;
    }
    try {
      await mic();
    } catch {
      onState("Mikrofon açılamadı");
      return;
    }
    mode = "wake";
    // Beklediğini yazmıyor. Bir insan odada beklerken "bekliyorum" diye
    // durmuyor; sessizce duruyor ve seslenilince dönüyor.
    //
    // Ama duyduğunu gösteriyor: ölçer arka planda da çalışıyor, konuşunca
    // mikrofon simgesi canlanıyor. "Dinliyor mu, duyuyor mu" sorusunun
    // cevabı yazıyla değil böyle veriliyor.
    onState("");
    startMeter();
    loop();
  }

  function loop() {
    // Bas-konuş sırasında uyandırma dinlemesi duruyor: aynı şeridi iki
    // kaydedici paylaşamıyor.
    if (mode !== "wake" || !stream) return;

    chunks = [];
    peak = 0;
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (event) => chunks.push(event.data);
    recorder.onstop = () => {
      const loud = peak;
      // Sessiz parça ve sırada bekleyen bir çözümleme varken hiç
      // gönderilmiyor: birincisi boşuna iş, ikincisi bağlantı kotasını
      // tüketip yazdığın mesajı bile sıraya sokuyordu.
      if (spoken(loud) && !busy) {
        send(new Blob(chunks, { type: "audio/webm" }), true, loud);
      }
      // Bir sonraki parça hemen başlıyor; arada boşluk kalırsa söz o
      // boşluğa denk gelip kaçıyor.
      loop();
    };
    recorder.start();
    setTimeout(() => {
      if (recorder && recorder.state !== "inactive") recorder.stop();
    }, CHUNK_MS);
  }

  // --- gönderme ----------------------------------------------------------

  async function send(blob, listening, loud) {
    if (!blob || !blob.size) {
      if (!listening) onState("Kayıt boş — mikrofon başka bir program tarafından kullanılıyor olabilir");
      return;
    }
    // Sessizliği baytla ölçmek yanıltıcıydı: opus sessizliği neredeyse hiç
    // yer kaplamıyor ama kısa bir "evet" de küçük bir dosya.
    if (!listening && !spoken(loud)) {
      onState("Ses duyulmadı — mikrofon seviyesini kontrol et");
      return;
    }

    let answer = {};
    busy = true;
    try {
      const response = await fetch("/api/hear", {
        method: "POST",
        headers: { "Content-Type": "audio/webm" },
        body: blob,
      });
      answer = await response.json();
    } catch {
      if (!listening) onState("Çözülemedi");
      return;
    } finally {
      busy = false;
    }

    if (!answer.ok) {
      if (!listening) onState(answer.error || "Çözülemedi");
      return;
    }
    if (!answer.text) {
      // Ses vardı ama kelime çıkmadı: gürültü ya da çok kısa.
      if (!listening) onState("Bir şey anlaşılmadı");
      return;
    }

    if (listening) {
      // Uyandırma kipinde her duyulan gönderilmiyor; yalnızca sözü taşıyan.
      if (answer.wake && answer.command) onCommand(answer.command);
      return;
    }

    onText(answer.text);
    onState("");
  }

  return { init, start, stop, toggle, wake, release, get mode() { return mode; } };
})();
