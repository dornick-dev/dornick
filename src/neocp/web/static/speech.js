// Sesli konuşma.
//
// Cevabın tamamını bekleyip sonra okumak, konuşma değil anons olurdu:
// model yazmayı bitirene kadar ses başlamıyor. Bunun yerine cümle
// tamamlandıkça sıraya giriyor ve sıra kesintisiz akıyor — ilk cümle
// söylenirken ikincisi zaten üretiliyor.
//
// Ses üretimi ağa çıkıyor ve her zaman çalışmayabilir. Sessiz kalmak
// kabul edilebilir; metin zaten ekranda. O yüzden hiçbir hata kullanıcıya
// gösterilmiyor, yalnızca ses gelmiyor.

const Speech = (() => {
  // Cümle sonu. Türkçede kısaltma az; nokta+boşluk yeterince güvenilir.
  const SENTENCE = /[^.!?…\n]+[.!?…]+["')\]]*|\n+/g;

  // Bu uzunluğa gelmiş ama noktalanmamış metin de söyleniyor: madde madde
  // yazan bir model hiç nokta koymayabiliyor. 220 idi; ses metnin iki-üç
  // saniye arkasına düşüyordu — parça kısaldıkça takip yakınlaşıyor,
  // prefetch zaten parçalar arası boşluğu kapatıyor.
  const FLUSH_AT = 110;

  // İlk parça için eşik çok daha düşük: sesin başlaması için ilk cümlenin
  // bitmesini beklemek, uzun bir açılış cümlesinde saniyelerce sessizlik
  // demek. Konuşma bir kez başladıktan sonra normal eşiğe dönülüyor —
  // yoksa cevap parça parça, soluk soluğa çıkıyor.
  const FIRST_AT = 60;

  let on = false;
  let buffer = "";

  // Sıra artık metin değil **söz veren** parçalardan oluşuyor: bir cümle
  // kuyruğa girer girmez sesi üretilmeye başlıyor ve sırası gelene kadar
  // hazır oluyor.
  //
  // Önceki hal seriydi — üret, çal, üret, çal — ve üretim tek başına ~1.2
  // saniye sürdüğü için her cümlede o kadar geriye düşüyordu. Beş cümlelik
  // bir cevapta ses metnin altı saniye arkasında kalıyordu.
  const queue = [];
  let playing = false;
  let current = null;
  // O an çalan parçanın bitirme kancası. Susturmak `pause()` çağırıyor ve
  // pause hiçbir olay tetiklemiyor — bekleyen sözü elle bitirmek gerekiyor.
  let ending = null;

  // Aynı anda kaç parça üretilsin. Sınırsız bırakmak uzun bir cevapta
  // onlarca eşzamanlı istek demek; ikisi gecikmeyi zaten sıfırlıyor.
  const PREFETCH = 2;
  let building = 0;

  // --- sesin karakteri --------------------------------------------------
  //
  // Sentezleyici gerçek bir insan sesi üretiyor ve bu tek başına düz
  // duruyor: metin okuyan biri gibi, konuşan bir şey gibi değil. Türkçe
  // seslerde SSML duygu stili de yok (hepsi "General"), yani üretim
  // tarafından alınabilecek başka bir şey kalmıyor.
  //
  // O yüzden karakter burada, sesin üstüne biniyor. Üç katman:
  //
  //   ikizleme  20 ms geciken ikinci bir kopya, hafifçe kayan bir
  //             gecikmeyle. Tek bir ağızdan çıkmıyormuş hissi bundan.
  //   tını      2,4 kHz'de yükseltme + 140 Hz altında kesme. Göğüs
  //             tonunu alıp yerine elektronik bir netlik koyuyor.
  //   titreşim  çok yavaş, çok küçük bir gecikme salınımı. Fark edilmiyor
  //             ama sesin "canlı ama insan değil" durmasını sağlıyor.
  //
  // Hiçbiri abartılmadı: anlaşılırlık bozulunca karakter değil arıza
  // gibi duruyor. `character` 0 olduğunda bu katman tümden atlanıyor ve
  // ses doğrudan çalıyor.
  let character = 0;
  let audio = null;   // AudioContext, ilk kullanımda açılıyor

  function setCharacter(value) {
    character = Math.max(0, Math.min(1, Number(value) || 0));
  }

  function context() {
    if (!audio) audio = new (window.AudioContext || window.webkitAudioContext)();
    // Kullanıcı etkileşimi olmadan açılan bağlam askıda başlıyor.
    if (audio.state === "suspended") audio.resume().catch(() => {});
    return audio;
  }

  function enable(value) {
    on = !!value;
    if (!on) stop();
    else warmAcks();
  }

  // --- onay klipleri ----------------------------------------------------
  //
  // Kullanıcı sustuğu an, model daha ilk kelimesini üretmeden çalınan kısa
  // sesler. Algılanan gecikmeyi taşıyan şey cevap değil bu ilk tepki —
  // insan da soruyu duyunca önce "bakayım" der, sonra düşünür.
  //
  // Sunucu bunları diskte önbelliyor (clip: true), tarayıcı da Blob olarak
  // elde tutuyor: ses açıldığında bir kez üretiliyor, sonrası anında.
  const ACKS = ["bakıyorum", "bir saniye", "şimdi bakayım",
                "hemen bakıyorum", "bakalım"];

  const ackStock = new Map();   // metin → Blob, oturum boyunca duruyor

  async function fetchClip(text) {
    const response = await fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, clip: true }),
    });
    if (response.status === 204 || !response.ok) return null;
    return await response.blob();
  }

  function warmAcks() {
    for (const text of ACKS) {
      if (ackStock.has(text)) continue;
      fetchClip(text)
        .then((blob) => { if (blob) ackStock.set(text, blob); })
        .catch(() => {});
    }
  }

  function ack() {
    // Konuşma zaten başladıysa ya da sırada söz varsa araya girmek
    // gecikmeyi gizlemek değil, sözü bölmek olur.
    if (!on || playing || queue.length) return;
    const text = ACKS[Math.floor(Math.random() * ACKS.length)];
    const stock = ackStock.get(text);
    const audio = stock
      ? Promise.resolve().then(() => {
          const url = URL.createObjectURL(stock);
          clips.set(url, stock);
          return url;
        })
      : fetchClip(text).then((blob) => {
          if (!blob) return null;
          ackStock.set(text, blob);
          const url = URL.createObjectURL(blob);
          clips.set(url, blob);
          return url;
        });
    queue.push({ text, audio });
    if (!playing) drain();
  }

  // Akan metinden tamamlanmış cümleleri ayırıp sıraya koyar.
  function feed(chunk) {
    if (!on) return;
    buffer += chunk;

    let taken = 0;
    for (const match of buffer.matchAll(SENTENCE)) {
      push(match[0]);
      taken = match.index + match[0].length;
    }
    if (taken) buffer = buffer.slice(taken);

    // İlk parça için virgül de yeter: ilk cümlenin bitmesini beklemek sesin
    // saniyelerce sonra başlaması demek. Sonrasında cümle sınırı kullanılıyor,
    // yoksa konuşma parça parça ve soluk soluğa çıkıyor.
    const started = queue.length > 0 || playing;
    const limit = started ? FLUSH_AT : FIRST_AT;
    if (buffer.length > limit) {
      const cut = split(buffer, limit);
      push(buffer.slice(0, cut));
      buffer = buffer.slice(cut);
    }
  }

  // Kelimeyi ortadan kesmemek için önce virgül, sonra boşluk aranıyor.
  function split(text, limit) {
    for (const mark of [", ", " "]) {
      const at = text.lastIndexOf(mark, limit);
      if (at > 30) return at + mark.length;
    }
    return limit;
  }

  // Tur bitti: elde kalan yarım cümle de söylensin.
  function flush() {
    if (!on) return;
    push(buffer);
    buffer = "";
  }

  function push(text) {
    const words = String(text || "").trim();
    // Tek başına duran noktalama ya da bir iki harf ses üretmeye değmiyor.
    if (words.length < 3) return;

    // Üretim burada başlıyor, sırası geldiğinde değil: çalma sürerken bir
    // sonraki parça arka planda hazırlanıyor.
    queue.push({ text: words, audio: null });
    build();
    if (!playing) drain();
  }

  function build() {
    while (building < PREFETCH) {
      const next = queue.find((item) => item.audio === null);
      if (!next) return;
      building += 1;
      next.audio = synth(next.text).finally(() => {
        building -= 1;
        build();
      });
    }
  }

  async function drain() {
    playing = true;
    while (on && queue.length) {
      const item = queue.shift();
      build();   // boşalan yer bir sonrakini üretmeye başlasın
      try {
        await play(await item.audio, item.text);
      } catch {
        // Ağ yoksa ses de yok; metin ekranda duruyor, iş durmamalı.
      }
    }
    playing = false;
  }

  // url → Blob: karakter katmanı ham baytları istiyor. Eskiden blob URL
  // ikinci kez fetch ediliyordu — kendi ürettiğimiz veriyi kendimizden
  // indirmek klip başına onlarca ms. Blob kenarda tutuluyor, çalınırken
  // düşülüyor.
  const clips = new Map();

  // Ses uretimi ilk kez basarisiz oldugunda kullaniciya BIR KEZ soylenir.
  // Eskiden sessizce yutuluyordu: kullanici sesi aciyor, hicbir sey
  // duymuyor ve neden calismadigini hicbir yerde goremiyordu.
  let troubled = false;
  function voiceTrouble() {
    if (troubled) return;
    troubled = true;
    try {
      document.dispatchEvent(new CustomEvent("neo:voice-trouble"));
    } catch { /* cok eski webview: haber yok ama is durmaz */ }
  }

  async function synth(text) {
    const response = await fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    // 204: söylenecek bir şey kalmamış (yalnızca kod bloğuydu gibi).
    if (response.status === 204) return null;
    if (!response.ok) {
      // 501 paket yok, 503 servis/ag — ikisinde de ses yok; soyle.
      voiceTrouble();
      return null;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    clips.set(url, blob);
    return url;
  }

  // Ajan konuşurken kulak kapanıyor: hoparlörden çıkan ses mikrofona geri
  // geliyor ve asistan kendi cümlesini duyup cevap vermeye kalkıyordu.
  // Yankı iptali işletim sistemi seviyesinde her zaman çalışmıyor.
  function deafen(on, text) {
    // Sahnedeki hoparlör organı da konuştuğunu göstersin. Bu dosya
    // sahneden önce yükleniyor; `typeof` bile bir const'un tanımlanma
    // anından önce hata veriyor, o yüzden deneyerek geçiliyor.
    try {
      on ? Scene.use("voice", "Konuşuyor") : Scene.release("voice");
    } catch { /* sahne henüz yok: ses yine de çalsın */ }
    fetch("/api/speaking", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on, text: on ? String(text || "") : "" }),
    }).catch(() => {});
  }

  function play(url, text) {
    if (!url) return Promise.resolve();
    if (character > 0.01) {
      // Karakter katmanı ham sesi istiyor. Başarısız olursa (bağlam
      // açılmadı, çözümleme patladı) düz çalmaya dönülüyor: sesin hiç
      // çıkmaması, karaktersiz çıkmasından kötü.
      return shaped(url, text).catch(() => plain(url, text));
    }
    return plain(url, text);
  }

  async function shaped(url, text) {
    const ctx = context();
    const stash = clips.get(url);
    clips.delete(url);
    const bytes = stash ? await stash.arrayBuffer()
                        : await (await fetch(url)).arrayBuffer();
    const buffer = await ctx.decodeAudioData(bytes);

    const source = ctx.createBufferSource();
    source.buffer = buffer;

    // Tını: göğüs tonu iniyor, elektronik netlik çıkıyor.
    //
    // `lowshelf` — `highshelf` değil. Highshelf 160 Hz'in **üstündeki**
    // her şeyi, yani sesin tamamını kısıyor: ölçümde tam karakterde ses
    // gücü %57 düşmüştü. İstenen şey yalnızca alttaki gümbürtüyü almak.
    const cut = ctx.createBiquadFilter();
    cut.type = "lowshelf";
    cut.frequency.value = 160;
    cut.gain.value = -7 * character;

    const edge = ctx.createBiquadFilter();
    edge.type = "peaking";
    edge.frequency.value = 2400;
    edge.Q.value = 0.9;
    edge.gain.value = 5 * character;

    // İkizleme: 20 ms geciken ikinci kopya. Tek bir ağızdan çıkmıyormuş
    // hissini veren şey bu.
    const twin = ctx.createDelay(0.1);
    twin.delayTime.value = 0.02;
    const twinLevel = ctx.createGain();
    twinLevel.gain.value = 0.42 * character;

    // Titreşim: çok yavaş, çok küçük bir salınım. Fark edilmiyor ama ses
    // "canlı ama insan değil" duruyor.
    const drift = ctx.createOscillator();
    drift.frequency.value = 0.28;
    const depth = ctx.createGain();
    depth.gain.value = 0.0016 * character;
    drift.connect(depth).connect(twin.delayTime);
    drift.start();

    const out = ctx.createGain();
    // İki yol toplanınca ses yükseliyor; geri alınıyor.
    out.gain.value = 1 / (1 + 0.42 * character);

    source.connect(cut).connect(edge);
    edge.connect(out);
    edge.connect(twin).connect(twinLevel).connect(out);
    out.connect(ctx.destination);

    return new Promise((done) => {
      const finish = () => {
        URL.revokeObjectURL(url);
        try { drift.stop(); } catch { /* zaten durmuş */ }
        current = null;
        ending = null;
        // Sırada cümle varken kulağı açmak cümleler arası boşlukta
        // hoparlör yankısını yeni söz yapıyordu.
        if (!queue.length) deafen(false);
        done();
      };
      // Susturma bunu çağırıyor: `stop()` hiçbir olay tetiklemiyor.
      current = { pause: () => { try { source.stop(); } catch { /* bitmiş */ } } };
      ending = finish;
      deafen(true, text);
      source.onended = finish;
      // Emniyet: ses bağlamı askıda kalırsa `onended` hiç tetiklenmiyor ve
      // kulak sonsuza kadar kapalı kalıyordu. Parçanın süresi biliniyor;
      // biraz pay bırakıp kendimiz bitiriyoruz.
      const guard = setTimeout(finish, (buffer.duration + 1) * 1000);
      const clear = () => clearTimeout(guard);
      source.addEventListener("ended", clear);
      source.start();
    });
  }

  function plain(url, text) {
    return new Promise((done) => {
      const audio = new Audio(url);
      current = audio;
      deafen(true, text);
      // Nesne adresi bırakılmazsa bellek konuşma boyunca birikiyor.
      clips.delete(url);
      const finish = () => {
        URL.revokeObjectURL(url);
        current = null;
        ending = null;
        if (!queue.length) deafen(false);
        done();
      };
      // Susturma bunu çağırıyor. `pause()` hiçbir olay tetiklemiyor: onsuz
      // aşağıdaki bekleme sonsuza kadar asılı kalıyor ve ses tekrar
      // açıldığında bir daha hiç çalmıyordu.
      ending = finish;
      audio.onended = finish;
      audio.onerror = finish;
      audio.play().catch(finish);
    });
  }

  function stop() {
    deafen(false);
    // Üretimi bekleyen parçaların adresleri de bırakılmalı.
    for (const item of queue) {
      if (item.audio) item.audio.then((url) => {
        if (url) { URL.revokeObjectURL(url); clips.delete(url); }
      }).catch(() => {});
    }
    queue.length = 0;
    buffer = "";
    if (current) {
      current.pause();
      current = null;
    }
    // Bekleyen sözü bitir: yoksa çalma döngüsü asılı kalıyor ve ses tekrar
    // açıldığında yeni cümleler sıraya girip hiç çalmıyor.
    if (ending) { const finish = ending; ending = null; finish(); }
  }

  return { enable, setCharacter, feed, flush, stop, ack, get on() { return on; } };
})();
