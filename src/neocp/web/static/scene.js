// Sahne: ortada holografik çekirdek, etrafında bir sinir ağı.
//
// Üç karar bu dosyanın tamamını belirliyor:
//
//   1. İnsansı figür yok. Elle çizilen bir silüet, referanstaki render'a
//      hiçbir zaman yaklaşamıyordu; soyut çekirdek hem daha iyi görünüyor
//      hem de duruma göre canlanabiliyor.
//   2. Ağ normalde sönük. Bütün hatıraları sürekli göstermek harita olur,
//      hatırlama olmaz. Düğümler ajan oraya uğradığında ateşlenir.
//   3. Ama iz sönüp kaybolmuyor. Bir saniyede parlayıp geçen animasyon
//      izlenemiyordu; hatırlama yolu numaralanıp ekranda kalıyor, bir
//      sonraki hatırlamaya kadar okunabiliyor.

// Bu dosyanın kullanıcıya gösterdiği metinlerin İngilizceleri. Kaynak
// metin Türkçe kalıyor; görüntüleme noktasında t("...") ile çevriliyor.
Dil.ekle({
  // Hatıra türleri (probe + legend)
  "Ben": "Me", "Kullanıcı": "User", "Tercih": "Preference", "Ders": "Lesson",
  "Yordam": "Procedure", "Bilgi": "Fact", "Hedef": "Goal", "Oturum": "Session",
  // Göster/gizle düğmesi
  "tüm hatıraları gizle": "hide all memories",
  "ağdaki tüm hatıraları göster": "show all memories in the web",
  // Çekirdek altı durum etiketi
  "Uyanıyor": "Waking", "Düşünüyor": "Thinking", "Yazıyor": "Writing",
  "Hatırlıyor": "Recalling", "Çalışıyor": "Working",
  // Dallar
  "Duyular": "Senses", "Cihazlar": "Devices", "Yetenekler": "Skills",
  // Legend açıklamaları
  "Seni tanıdıklarım": "What I know about you",
  "Tercihlerin": "Your preferences",
  "Çıkardığım dersler": "Lessons I have drawn",
  "Yöntemlerim": "My methods",
  "Konuşma biçimin": "How you speak",
  "Öğrendiklerim": "Things I have learned",
  "İş listesi": "Task list",
  "Geçmiş konuşmalar": "Past conversations",
  "Mikrofon, kamera, ses": "Microphone, camera, voice",
  "PLC, sensör, seri port": "PLC, sensors, serial ports",
  "Kendi yazdığım betikler": "Scripts I wrote myself",
});

const Scene = (() => {
  const LABEL = {
    self: "Ben", user: "Kullanıcı", preference: "Tercih", lesson: "Ders",
    procedure: "Yordam", fact: "Bilgi", goal: "Hedef", session: "Oturum",
    episode: "Oturum"
  };

  // Halkalar: yarıçap çarpanı, hız (rad/sn), parça sayısı, boşluk oranı.
  // Halkalar beynin **çevresinde**, üstünde değil. Önceki hal beynin
  // üstüne biniyordu ve asıl özne kim belli olmuyordu; yarıçaplar dışarı
  // alındı ve parlaklık düşürüldü. Kip canlandırmasını yine bunlar
  // taşıyor — düşünürken hızlanan şey bu halkalar.
  const RINGS = [
    { scale: 1.62, speed: 0.16, parts: 3, gap: 0.30, width: 1.6, alpha: 0.30 },
    { scale: 1.86, speed: -0.26, parts: 6, gap: 0.42, width: 1.0, alpha: 0.22 },
    { scale: 2.10, speed: 0.46, parts: 12, gap: 0.55, width: 0.9, alpha: 0.16 },
    { scale: 2.38, speed: -0.09, parts: 2, gap: 0.72, width: 0.9, alpha: 0.12 }
  ];

  // Çekirdeğin halleri. Ajanın ne yaptığı ekranda okunabilir olmalı:
  // "meşgul / boşta" ikilisi her işi aynı gösteriyordu — düşünmekle dosya
  // okumak aynı animasyona düşüyordu. Her kip kendi karakterini taşıyor,
  // aralarında yumuşak geçiliyor (ani sıçrama sahneyi bozuyor).
  //
  //   spin   halkaların dönüş çarpanı
  //   beat   nabız periyodu, ms — küçük olan daha telaşlı
  //   glow   auranın gücü
  //   wedge  konik süpürmenin hızı
  //   tint   çekirdeğin rengi
  // Hızlar bilerek düşük: dönüş/süpürme/nabız "aşırı hızlı, göz yoruyor"du.
  // Sakin ama ölü değil — çalışırken canlı, ama izlemesi rahat. (Önceki
  // değerler yaklaşık iki katıydı.)
  const MODES = {
    // Uyanma: yavaş, sönük, soğuk. Henüz kimse yok.
    waking:    { spin: 0.16, beat: 3000, glow: 0.04, wedge: 0.08, tint: [58, 96, 128] },
    idle:      { spin: 0.50, beat: 2000, glow: 0.10, wedge: 0.28, tint: [79, 227, 255] },
    thinking:  { spin: 0.90, beat: 1200, glow: 0.17, wedge: 0.80, tint: [162, 142, 255] },
    writing:   { spin: 0.65, beat: 1000, glow: 0.15, wedge: 0.55, tint: [96, 242, 214] },
    recalling: { spin: 1.10, beat: 1050, glow: 0.21, wedge: 1.15, tint: [79, 227, 255] },
    working:   { spin: 1.00, beat: 1100, glow: 0.18, wedge: 0.95, tint: [255, 176, 84] }
  };

  // Kip geçişinin bir karedeki payı. 1'e yaklaştıkça geçiş sertleşir.
  const BLEND = 0.055;

  // Adımlar arası. Sinyalin yolculuğundan kısa: bir sonraki uyarı önceki
  // hedefine varmadan yola çıkıyor ve zincir akıyor. Kısaltmak akışı
  // izlenmez yapıyor — asıl istenen şey izlenmesi. Sinyalin anılara doğru
  // yürüyüşü gözle takip edilebilsin diye bilinçle yavaş tutuluyor.
  const STEP_MS = 720;
  const FLASH_MS = 900;     // ateşleme parlamasının sönme süresi
  const BRIDGE_MS = 2200;   // kurulan bağın görünür kaldığı süre
  const PATH_FLOOR = 0.46;  // yol sönmez, bu seviyede kalır
  const LATENT = 0.13;      // ağın sönük hali
  const WEB_ALPHA = 0.055;  // sinaps bağlarının sönük hali

  let canvas, ctx, probe, revealBtn, onRoute = () => {};
  let view = { w: 0, h: 0 };
  let nodes = [], byId = new Map(), web = [], stats = {};
  let core = { x: 0, y: 0, r: 0 };
  let ripples = [], bridges = [], reveal = false;
  // `look` ekranda o an gecerli olan degerler; `mode` hedef kip. Ikisi
  // arasinda her karede biraz yaklasiliyor.
  let mode = "idle", look = { ...MODES.idle, tint: [...MODES.idle.tint] };
  let route = [], focused = -1;
  let selected = null, hovered = null;
  let raf = null, pointer = { x: 0, y: 0 };

  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue("--" + n).trim();

  // Sahne near-black için ayarlanmıştı: parlak tint + düşük alfa koyu
  // zeminde yıldız gibi, BEYAZDA kayboluyor. Işıkta neon'u kısarak değil
  // CSS mürekkebini (zaten kâğıt için koyulmuş) kullanarak çiziyoruz.
  const isLight = () => document.documentElement.dataset.theme === "light";
  const now = () => performance.now();

  function hexRgb(hex) {
    const m = /^#([0-9a-f]{6})$/i.exec((hex || "").trim());
    if (!m) return null;
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  // Kip rengi kâğıtta: idle cyan, düşünme violet, iş amber — token'dan.
  function paperInk() {
    const key = {
      waking: "session", idle: "cyan", thinking: "violet",
      writing: "mint", recalling: "ice", working: "amber"
    }[mode] || "cyan";
    return hexRgb(css(key)) || [10, 122, 156];
  }

  // Soluk alfanın kâğıtta tabanı: 0.2 × renk, açık zeminde görünmez.
  function paperAlpha(a) {
    return isLight() ? Math.min(1, a * 2.6 + 0.2) : a;
  }

  // Bir metinden 0..1 arası sabit bir sayı. FNV-1a: aynı kimlik + aynı
  // tuz her zaman aynı sonucu verir. Hatıraların beyindeki yerini buradan
  // türetiyoruz — konum rastgele görünsün ama açılışlar arası kaymasın.
  function hash01(str, salt) {
    let h = (2166136261 ^ (salt || 0)) >>> 0;
    for (let i = 0; i < str.length; i++) {
      h = Math.imul(h ^ str.charCodeAt(i), 16777619);
    }
    return (h >>> 0) / 4294967296;
  }

  function init(opts) {
    canvas = opts.canvas;
    ctx = canvas.getContext("2d");
    probe = opts.probe;
    revealBtn = opts.reveal;
    onRoute = opts.onRoute || onRoute;

    // ResizeObserver pencere olayından üstün: gizliyken 0 olan kutu
    // görünür olunca kendiliğinden bildiriliyor.
    const watch = new ResizeObserver(resize);
    watch.observe(canvas);
    // Sohbet sütunu daralıp genişledikçe (görüntüleyici açılınca, pencere
    // yeniden boyutlanınca) çekirdeğin ortası da kayıyor.
    const aside = document.querySelector(".stream");
    if (aside) watch.observe(aside);
    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("mousedown", onDown);

    // Pencere küçültülünce çizimi durdur: görünmeyen sahneyi canlandırmak
    // gün boyu açık kalan bir programda boşa yakılan pil.
    document.addEventListener("visibilitychange", () => document.hidden ? stop() : start());

    if (revealBtn) revealBtn.addEventListener("click", toggleReveal);

    resize();
    start();
  }

  const start = () => { if (raf === null) raf = requestAnimationFrame(frame); };
  const stop = () => { if (raf !== null) { cancelAnimationFrame(raf); raf = null; } };
  const redraw = () => paint(now());

  function toggleReveal() {
    reveal = !reveal;
    // İkon; metin değil. Durum sınıfla ve tooltip'le anlatılıyor.
    if (revealBtn) {
      revealBtn.classList.toggle("on", reveal);
      revealBtn.title = reveal ? t("tüm hatıraları gizle") : t("ağdaki tüm hatıraları göster");
    }
    if (!reveal) { selected = null; probe.hidden = true; }
  }

  function resize() {
    const rect = canvas.getBoundingClientRect();
    const w = rect.width || view.w;
    const h = rect.height || view.h;
    if (!w || !h) return;            // hâlâ gizli: sonraki bildirimi bekle

    const ratio = window.devicePixelRatio || 1;
    view = { w, h };
    canvas.width = Math.round(w * ratio);
    canvas.height = Math.round(h * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    layout();
  }

  // --- yerleşim -------------------------------------------------------
  //
  // Sahne pencerenin değil **boş alanın** ortasına oturuyor. Sohbet sağda
  // bir sütun ve çekirdek pencerenin tam ortasındayken yazının altında
  // kalıyordu: asıl izlenecek şey olan düşünce akışı görünmüyordu.
  //
  // Sütunun genişliği CSS'te ve pencereye göre değişiyor, o yüzden burada
  // varsayılmıyor — ölçülüyor.
  const NARROW = 380;   // bundan az boş alan kalırsa sütun düzeni anlamsız

  function freeWidth() {
    const aside = document.querySelector(".stream");
    const rect = aside ? aside.getBoundingClientRect() : null;
    if (!rect || !rect.width) return view.w;
    // Sütunun soluna düşen alan. Dar pencerede yazı zaten sahnenin
    // üstünde duruyor; orada çekirdek yine ortada kalıyor.
    return rect.left > NARROW ? rect.left : view.w;
  }

  // Sohbet yanda mı, altta mı. Sahnenin boş bıraktığı taraf buna göre
  // değişiyor ve organlar oraya diziliyor.
  const sideways = () => freeWidth() < view.w;

  function layout() {
    const free = freeWidth();
    core.x = free / 2;
    // Sohbet altta olduğunda çekirdek yukarı çekiliyor: ortada kalırsa
    // yazının altında kalıyor ve izlenecek şey görünmüyor.
    core.y = view.h * (free < view.w ? 0.46 : 0.42);
    core.r = Math.min(free * 0.11, view.h * 0.17, 150);

    // Anılar artık düz bir 2B dağılımda değil, dönen beynin HACMİNİN
    // İÇİNDE. Her düğüme kimliğinden türeyen sabit bir 3B konum veriliyor
    // (bir engram gibi — aynı anı hep aynı yerde) ve ekran konumu her
    // karede beyinle aynı rotasyondan geçirilerek hesaplanıyor. Böylece
    // anılar beyinle birlikte dönüyor, içinde duruyor.
    for (const node of nodes) if (!node.p3) node.p3 = insideBrain(node.id);
    place();
  }

  async function load(then) {
    const data = await (await fetch("/api/graph")).json();
    stats = data.stats || {};

    const previous = new Map(nodes.map(n => [n.id, n]));
    nodes = data.nodes
      .filter(n => n.id !== "self" && !n.hub)
      .map(n => {
        const old = previous.get(n.id);
        return {
          ...n,
          flash: old ? old.flash : 0,
          lit: old ? old.lit : 0,
          order: old ? old.order : 0,
          from: old ? old.from : null
        };
      });

    byId = new Map(nodes.map(n => [n.id, n]));
    // Sinaps bağları: ağı ağ yapan şey. Hiyerarşi kenarları burada değil.
    web = (data.edges || [])
      .filter(e => e.synapse && byId.has(e.source) && byId.has(e.target))
      .map(e => ({ a: byId.get(e.source), b: byId.get(e.target), weight: e.weight || 1 }));

    layout();
    if (selected) { selected = byId.get(selected.id) || null; if (!selected) probe.hidden = true; }
    if (then) then();
  }

  // --- hatırlama izi --------------------------------------------------
  // Ajanın gerçekten uğradığı düğümler, gerçekten uğradığı sırayla.
  // Adımlar tek tek açılıyor ve yol ekranda kalıyor: haritada takip
  // edilebilsin diye.
  //
  // Her adım artık iki olay: önce bir uyarı yola çıkıyor, sonra vardığı
  // düğüm ateşleniyor. Yalnızca ateşleme gösterildiğinde ağda ışıklar
  // sırayla yanıp sönüyordu; nereden nereye gidildiği görünmüyordu.
  //
  // Toplam süreyi döndürüyor: sahnenin ne kadar hatırlama kipinde
  // kalacağını çağıran taraf bilsin, sayıyı tahmin etmesin.
  function activate(trace) {
    clearRoute();
    if (!Array.isArray(trace) || !trace.length) { ripple(); return 0; }

    // Iz yalnizca kimlik tasiyor; okunabilir liste icin etiketi ekliyoruz.
    route = trace
      .filter(step => byId.has(step.node))
      .map(step => ({ ...step, label: byId.get(step.node).label }));

    // Numaralar yalnızca gerçekten kullanılanlara veriliyor. Taranan her
    // kaydı numaralamak, zihnin hepsini okuduğu izlenimi veriyordu —
    // "modbus cihazı ekle" derken beş kayıt birden yanıyor ve ikisi BTC
    // fiyatı oluyordu. Hiçbiri işaretli değilse (eski kayıtlar) hepsi
    // kullanılmış sayılıyor.
    const marked = route.some(step => step.used);
    route.forEach(step => { step.used = marked ? !!step.used : true; });
    focused = -1;
    ripple();

    // SİNYALLER YALNIZ KULLANILANLARA uçuyor. Taranıp bırakılanlara da uçuş
    // çizmek "ışık oradan oraya rastgele gidiyor" izlenimi veriyordu — oysa
    // yürüyüş, modelin önüne GERÇEKTEN konan kayıtların zinciri. Bakılanlar
    // uçuşsuz, hep birlikte tek yumuşak parıltıyla işaretleniyor: dokunuldu
    // ama alınmadı.
    const walked = route.filter(step => step.used);
    route.forEach(step => {
      if (!step.used) setTimeout(() => strike(step.node, 0, null), 140);
    });

    walked.forEach((step, i) => {
      // Uyarı nereden geliyor: aktivasyonu ileten düğümden (o da kullanılmış
      // olmalı), yoksa zincirdeki bir önceki kullanılan düğümden, o da yoksa
      // çekirdekten — yani sorudan.
      const viaUsed = step.via && step.via !== "query" && byId.has(step.via)
        && walked.some(w => w.node === step.via);
      const via = viaUsed ? step.via : (i > 0 ? walked[i - 1].node : null);

      signal(via, step.node, via ? "weigh" : "ask", i * STEP_MS);
      setTimeout(() => {
        strike(step.node, i + 1, via);
        onRoute(route, route.indexOf(step));   // liste adım adım dolsun
      }, i * STEP_MS + SIGNAL_MS);
    });

    // Bulunan geri getiriliyor: son KULLANILAN duraktan çekirdeğe dönen uyarı.
    const last = walked[walked.length - 1];
    const walk = Math.max(0, walked.length - 1) * STEP_MS + SIGNAL_MS;
    if (last) signal(last.node, null, "recall", walk);
    if (!walked.length) onRoute(route, route.length - 1);   // hepsi bakıldıysa liste yine gelsin
    return walk + SIGNAL_MS;
  }

  // Kullanılanların kendi arasındaki sırası. Taranıp bırakılanlar sayıyı
  // ilerletmiyor: "1, 2, 3" diye giden bir liste beklenirken "2, 5, 7"
  // görmek okunmuyor.
  function order(index) {
    let count = 0;
    for (let i = 0; i <= index; i++) if (route[i] && route[i].used) count += 1;
    return count;
  }

  function clearRoute() {
    for (const node of nodes) { node.order = 0; node.from = null; node.flash = 0; }
    route = [];
    focused = -1;
  }

  // Listeden bir adıma tıklanınca o düğüm öne çıkıyor.
  function focusStep(index) {
    focused = index;
    const step = route[index];
    if (step) {
      const node = byId.get(step.node);
      if (node) { node.flash = 1; node.lit = now(); showProbeAt(node); }
    }
    start();
  }

  function ripple() { ripples.push({ born: now() }); start(); }

  // Ajanın bilinçli olarak kurduğu bağ. Otomatik örgüden farkı görünmesi:
  // ağın kendiliğinden büyümesi sessiz, ajanın köprü kurması bir olay.
  function bridge(src, dst) {
    const from = byId.get(src);
    const to = byId.get(dst);
    if (!from || !to) return;
    bridges.push({ from, to, born: now() });
    // Bağ çizilirken üzerinden bir uyarı geçiyor: kurulan şeyin bir yön
    // taşıdığı görünsün.
    signal(src, dst, "link");
    from.flash = 1; from.lit = now();
    to.flash = 1; to.lit = now();
    start();
  }

  function drawBridges(t) {
    // Sönmüş olanlar listeden düşüyor; yoksa uzun bir oturumda birikiyor.
    bridges = bridges.filter((b) => t - b.born < BRIDGE_MS);
    for (const b of bridges) {
      const k = (t - b.born) / BRIDGE_MS;
      // Çizgi kaynaktan hedefe doğru çiziliyor: bağın yönü görünsün.
      const grow = Math.min(1, k * 3);
      ctx.globalAlpha = (1 - k) * 0.9;
      ctx.strokeStyle = css("preference");
      ctx.shadowColor = css("preference");
      ctx.shadowBlur = 18;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(b.from.x, b.from.y);
      ctx.lineTo(b.from.x + (b.to.x - b.from.x) * grow, b.from.y + (b.to.y - b.from.y) * grow);
      ctx.stroke();
    }
    ctx.globalAlpha = 1; ctx.shadowBlur = 0;
  }

  // Kipin çekirdek altında yazan karşılığı. Renk kipin kendi tini'nden
  // geliyor (thinking mor, working amber…); yazı da o an ne yaptığını
  // söylüyor. Belirli bir eylem verilmezse (bir araç çağrısı gibi) kipin
  // varsayılan sözcüğü kullanılıyor.
  const MODE_TEXT = {
    waking: "Uyanıyor", idle: "", thinking: "Düşünüyor",
    writing: "Yazıyor", recalling: "Hatırlıyor", working: "Çalışıyor",
  };
  let statusLabel = "";

  function setMode(name, label) {
    mode = MODES[name] ? name : "idle";
    // Eylem etiketi: verildiyse onu, verilmediyse kipin sözcüğünü göster.
    statusLabel = label !== undefined ? label : (t(MODE_TEXT[mode]) || "");
    start();   // gizliyken durdurulmus olabilir
  }

  // Eski cagri yuzeyi: mesgul/bosta ikilisi hala calisiyor.
  const setBusy = (value) => setMode(value ? "working" : "idle");

  function blend() {
    const target = MODES[mode] || MODES.idle;
    for (const key of ["spin", "beat", "glow", "wedge"]) {
      look[key] += (target[key] - look[key]) * BLEND;
    }
    for (let i = 0; i < 3; i++) {
      look.tint[i] += (target.tint[i] - look.tint[i]) * BLEND;
    }
  }

  // Gecerli rengi verilen saydamlikla dondurur.
  const tint = (alpha) => {
    const c = isLight() ? paperInk() : look.tint;
    return "rgba(" + c.map(Math.round).join(",") + "," + alpha + ")";
  };

  // --- sinyaller -------------------------------------------------------
  //
  // Hatırlamak, yazmak ve tartmak burada **hareket** olarak görünüyor:
  // bir uçtan diğerine yürüyen bir uyarı. Önceki hal düğümleri sırayla
  // yakıyordu ve aradaki yolculuk hiç görünmüyordu — bir şeyin nereden
  // nereye aktığı okunmuyordu, yalnızca sonuç yanıp sönüyordu.
  //
  // Hız kasten düşük. Gerçek bir sinyal milisaniyelerde geçer ama o
  // izlenemez, ve buradaki bütün mesele izlenmesi.
  const SIGNAL_MS = 1000;   // bir sıçramanın süresi — anıya giden sinyal izlenebilsin
  const TAIL = 0.3;         // kuyruğun yol üzerindeki oranı
  const BOW = 0.15;         // yolun yay payı: düz çizgi kablo gibi duruyor
  const DOTS = 18;          // kuyruğu oluşturan nokta sayısı

  // Sinyalin ne taşıdığı renginden okunuyor.
  const CURRENT = {
    ask:    "cyan",         // çekirdekten ağa: soru
    weigh:  "violet",       // düğümden düğüme: çağrışım, tartma
    recall: "ice",          // ağdan çekirdeğe: bulunan geri geliyor
    write:  "mint",         // çekirdekten ağa: yazma
    link:   "preference",   // bilinçli kurulan köprü
    limb:   "fact"          // çekirdekten bir aygıta: organ kullanımı
  };

  let signals = [];

  // Uç noktası: `null` çekirdek demek. Konum her karede yeniden çözülüyor
  // ki pencere yeniden boyutlanınca sinyal havada asılı kalmasın.
  function spot(id) {
    if (!id || id === "self" || id === "core") return { x: core.x, y: core.y };
    const node = byId.get(id);
    if (node) return { x: node.x, y: node.y };
    // Organlar da hedef olabiliyor: aygıta giden uyarı.
    const limb = limbs.find(l => l.id === id);
    return limb ? { x: limb.x, y: limb.y } : null;
  }

  function signal(from, to, kind, delay) {
    signals.push({ from, to, kind: kind || "ask", born: now() + (delay || 0) });
    start();
  }

  // Yol düz değil: iki ucun ortası çekirdekten uzağa itiliyor. Düz çizgi
  // kablo gibi duruyordu; yay akson gibi duruyor. Yön uçların konumundan
  // çıkıyor, rastgele değil — yoksa her karede taraf değiştirirdi.
  function curve(a, b) {
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    const dx = b.x - a.x, dy = b.y - a.y;
    const side = (mx - core.x) * dy - (my - core.y) * dx >= 0 ? 1 : -1;
    return { x: mx - dy * BOW * side, y: my + dx * BOW * side };
  }

  const bezier = (a, c, b, k) => ({
    x: (1 - k) * (1 - k) * a.x + 2 * (1 - k) * k * c.x + k * k * b.x,
    y: (1 - k) * (1 - k) * a.y + 2 * (1 - k) * k * c.y + k * k * b.y
  });

  function drawSignals(t) {
    // Sönenler listeden düşüyor; yoksa uzun bir oturumda birikiyorlar.
    signals = signals.filter(sig => t - sig.born < SIGNAL_MS * (1 + TAIL));

    for (const sig of signals) {
      if (t < sig.born) continue;              // gecikmeli: henüz yola çıkmadı
      const a = spot(sig.from), b = spot(sig.to);
      if (!a || !b) continue;

      const head = (t - sig.born) / SIGNAL_MS;
      const c = curve(a, b);
      const color = css(CURRENT[sig.kind] || "cyan");
      // Baş hedefe vardıktan sonra kuyruk içeri akmaya devam ediyor.
      const left = head > 1 ? Math.max(0, 1 - (head - 1) / TAIL) : 1;

      ctx.shadowColor = color;
      ctx.fillStyle = color;
      for (let i = 0; i < DOTS; i++) {
        const k = head - (i / DOTS) * TAIL;
        if (k < 0 || k > 1) continue;
        const p = bezier(a, c, b, k);
        const fade = (1 - i / DOTS) * left;
        ctx.globalAlpha = Math.min(1, fade * 1.05);
        ctx.shadowBlur = 20 * fade;
        ctx.beginPath();
        // Baş daha büyük ve parlak: sinyalin anıya doğru yürüyüşü gözle
        // rahat izlenebilsin (kullanıcı isteği).
        ctx.arc(p.x, p.y, 0.9 + fade * 3.3, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.globalAlpha = 1; ctx.shadowBlur = 0;
  }

  // Bir düğüm ateşlendi: parlasın, sırasını ve nereden geldiğini taşısın.
  function strike(id, order, from) {
    const node = byId.get(id);
    if (!node) return null;
    node.flash = 1;
    node.lit = now();
    if (order) node.order = order;
    if (from !== undefined) node.from = from;
    start();
    return node;
  }

  // Yazma: çekirdekten ağa doğru giden bir uyarı, ucunda yeni kayıt.
  // Grafik tazelendikten sonra çağrılıyor, yoksa hedef düğüm henüz yok.
  function deposit(id) {
    if (!byId.has(id)) { ripple(); return; }
    signal(null, id, "write");
    setTimeout(() => strike(id), SIGNAL_MS);
  }

  // --- organlar --------------------------------------------------------
  //
  // Ağ ajanın bildiklerini gösteriyor; bu katman yapabildiklerini:
  // mikrofon, kameralar, hoparlör ve kendine yazdığı modüller (harita,
  // PLC, USB — ne yazdıysa).
  //
  // Normalde soluk duruyorlar. Bir hatıra ile bir kamerayı aynı düğüm
  // yapmak "şu an neyi kullanıyor" sorusunu cevapsız bırakıyordu; ayrı
  // bir halka olunca cevap tek bakışta okunuyor.
  //
  // Kullanıldığında çekirdekle arasında uyarı akıyor ve organ nabız
  // atıyor. Üzerine gelince o an ne yaptığı yazıyor.
  // Renk türü ayırıyor. `lesson` ile `amber` aynı sarı: cihazla yetenek
  // ekranda ayırt edilmiyordu ve şekil farkı tek başına yetmiyordu.
  //
  //   mavi   duyular   — makinenin kendi organları
  //   sarı   cihazlar  — dışarıdan bağlanan fiziksel şeyler
  //   mor    yetenekler— ajanın kendi yazdığı betikler
  const LIMB_COLOR = { sense: "fact", speech: "fact", module: "violet",
                       device: "amber" };

  // Dallar. Organlar tek tek çekirdeğe bağlı düz çizgilerdi ve hepsi aynı
  // yerden çıkıyordu: mikrofonla ajanın kendi yazdığı bir betik ayırt
  // edilemiyordu. Şimdi üç dal var ve her organ kendi dalından sarkıyor —
  // fiziksel olanla yazılım olan bakışta ayrılıyor.
  //
  //   duyular    makinenin kendi organları: mikrofon, kamera, hoparlör
  //   cihazlar   dışarıdan bağlanan: PLC, uzak kamera, seri port
  //   yetenekler ajanın kendine yazdığı betikler
  const BRANCHES = [
    { id: "duyular", label: "Duyular", kinds: ["sense", "speech"], tone: "fact" },
    { id: "cihazlar", label: "Cihazlar", kinds: ["device"], tone: "amber" },
    { id: "yetenekler", label: "Yetenekler", kinds: ["module"], tone: "violet" },
  ];

  // Dalın çekirdekten uzaklığı ve yaprakların daldan uzaklığı.
  const BRANCH_AT = 0.58;   // yolun ne kadarında dallanıyor
  const LEAF_GAP = 0.34;    // yapraklar arası açı

  // Şekil türü ayırıyor. Hepsi altıgen olunca ajanın kendi yazdığı bir
  // betik, masadaki mikrofonla aynı şey gibi görünüyordu.
  //
  //   altıgen  makinenin kendi duyusu — mikrofon, kamera, hoparlör
  //   kare     dışarıdan bağlanan cihaz — PLC, uzak kamera, seri port
  //   baklava  ajanın kendine yazdığı yetenek: donanım değil, yazılım
  const LIMB_SIDES = { sense: 6, speech: 6, device: 4, module: 3 };
  const USE_MS = 1400;     // kullanım nabzının bir turu
  const USE_HOLD = 6000;   // kullanım izinin sönme süresi
  const LIMB_DIM = 0.24;   // boştaki solukluk

  let limbs = [];

  // Dallar varsayılan KAPALI: beş yetenek + üç duyu + cihazlar açık
  // yelpazeyle sahneyi dolduruyordu ("kocaman alanlarda gözümüze
  // sokuyor"). Kapalıyken yalnız dal göbeği durur: "YETENEKLER · 5".
  // Açan üç şey: göbeğe tıklama (kalıcı), üzerine gelme (geçici),
  // ve daldaki bir organın o an kullanılıyor olması (kendiliğinden).
  const openBranches = new Set();
  const branchWake = {};   // dal id → açılma anı (yaprak fade-in'i)
  let hoverBranch = null;

  function organs(list) {
    const previous = new Map(limbs.map(l => [l.id, l]));
    limbs = (list || []).map(item => {
      const old = previous.get(item.id) || {};
      // Ne yaptığı sunucudan gelmiyor, kullanımdan geliyor: liste
      // tazelendiğinde o an süren iş kaybolmamalı.
      return { ...item, doing: old.doing || "", since: old.since || 0, organ: true };
    });
    place();
    start();
  }

  // Hatıra kuşağının dışında, sahnenin boş bıraktığı tarafta bir sıra.
  //
  // Yön sohbetin nerede olduğuna bağlı: sütun yandayken alt taraf boş ve
  // organlar oraya iniyor; sütun alttayken (dar pencere) alt taraf yazıyla
  // dolu ve organlar üste çıkıyor. Sabit bir yay seçmek, dar pencerede
  // etiketlerin karşılama metninin üstüne oturması demekti.
  // Hangi organ hangi dalda.
  const branchOf = (limb) =>
    BRANCHES.find((b) => b.kinds.includes(limb.kind)) || BRANCHES[0];

  let branches = [];

  function place() {
    if (!limbs.length) { branches = []; return; }
    const free = freeWidth();
    const down = free < view.w ? 1 : -1;

    // Yarıçap gerçek boşluktan çıkıyor, orana göre değil. Sabit bir oran
    // dar pencerede organları üst şeridin altına sokuyordu: altıgenler
    // ekranın dışında kalıyor, etiketleri hiç görünmüyordu.
    //
    //   yukarı  üst şerit (56) + etiket + gövde payı
    //   aşağı   alt kenar payı
    const room = down > 0 ? view.h - core.y - 34 : core.y - 96;
    const radius = Math.min(free * 0.42, view.h * 0.34, Math.max(core.r * 2.4, room));

    // Aralık organ başına sabit, yaya bölünmüş değil: üç organ bütün yayı
    // kaplayınca ikisi ekranın kenarlarına düşüyor ve arayüzün üstüne
    // biniyordu. Kalabalıklaştıkça açılıyor, yay dolunca duruyor.
    const GAP = 0.3;
    const span = Math.min(Math.PI * 0.86, (limbs.length - 1) * GAP);

    // Yalnızca dolu dallar yer kaplıyor: boş bir "cihazlar" dalı çizmek,
    // olmayan bir şeyin yerini göstermek olurdu.
    const filled = BRANCHES.filter((b) => limbs.some((l) => branchOf(l) === b));
    const spread = Math.min(Math.PI * 0.8, (filled.length - 1) * 0.62) || 0;

    branches = filled.map((meta, i) => {
      const t = filled.length === 1 ? 0.5 : i / (filled.length - 1);
      const angle = down * (Math.PI / 2 - spread / 2 + t * spread);
      const own = limbs.filter((l) => branchOf(l) === meta);
      return {
        ...meta,
        angle,
        own,
        x: core.x + Math.cos(angle) * radius * BRANCH_AT,
        y: core.y + Math.sin(angle) * radius * BRANCH_AT,
        below: down > 0,
      };
    });

    // Yapraklar dalın ucundan yelpaze gibi açılıyor.
    for (const branch of branches) {
      const fan = Math.min(Math.PI * 0.5, (branch.own.length - 1) * LEAF_GAP) || 0;
      branch.own.forEach((limb, i) => {
        const t = branch.own.length === 1 ? 0.5 : i / (branch.own.length - 1);
        const angle = branch.angle - fan / 2 + t * fan;
        limb.angle = angle;
        limb.x = core.x + Math.cos(angle) * radius;
        limb.y = core.y + Math.sin(angle) * radius;
        limb.stem = branch;
        // Etiket organın dış tarafında: içeride kalsa çekirdeğin parlak
        // halkalarının üstüne biniyor.
        limb.below = down > 0;
      });
    }
  }

  // Bir organ kullanılıyor. `what` üzerine gelince okunan satır.
  function use(id, what) {
    const limb = limbs.find(l => l.id === id);
    if (!limb) return;
    limb.doing = what || "";
    limb.since = now();
    // Çekirdekten aygıta giden uyarı: bir şeyin oradan geçtiği görünsün.
    signal(null, id, "limb");
    start();
  }

  function release(id) {
    const limb = limbs.find(l => l.id === id);
    if (limb) { limb.doing = ""; limb.since = 0; }
  }

  function drawLimbs(t) {
    if (!limbs.length) return;
    const family = getComputedStyle(document.body).fontFamily;

    // Hangi dallar açık: tıklanmış, üzerinde durulan ya da o an kullanılan.
    const expanded = new Set();
    for (const branch of branches) {
      const busy = branch.own.some((l) => l.since > 0 && t - l.since < USE_HOLD);
      const hovering = hoverBranch && hoverBranch.id === branch.id;
      if (openBranches.has(branch.id) || hovering || busy) {
        expanded.add(branch.id);
        if (!branchWake[branch.id]) branchWake[branch.id] = t;
      } else {
        delete branchWake[branch.id];
      }
    }

    // Gövdeler: çekirdekten dallara. Yaprakların ne zaman canlandığından
    // bağımsız olarak hep duruyorlar — ağacın iskeleti bu.
    for (const branch of branches) {
      const busy = branch.own.some((l) => l.since > 0 && t - l.since < USE_HOLD);
      const open = expanded.has(branch.id);
      const tone = css(branch.tone);
      ctx.strokeStyle = tone;
      ctx.globalAlpha = paperAlpha(busy ? 0.5 : 0.2);
      ctx.lineWidth = busy ? 1.6 : (isLight() ? 1.5 : 1.2);
      ctx.beginPath();
      ctx.moveTo(core.x, core.y);
      ctx.lineTo(branch.x, branch.y);
      ctx.stroke();

      // Göbek: kapalıyken dalın tek yüzü — biraz daha belirgin, tıklanır.
      ctx.globalAlpha = paperAlpha(busy ? 0.8 : open ? 0.4 : 0.55);
      ctx.fillStyle = tone;
      ctx.beginPath();
      ctx.arc(branch.x, branch.y, open ? 2.4 : 3.4, 0, Math.PI * 2);
      ctx.fill();
      if (!open) {
        ctx.globalAlpha = paperAlpha(0.3);
        ctx.strokeStyle = tone;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(branch.x, branch.y, 6.5, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Dal adı + kapalıyken içindeki sayı: "YETENEKLER · 5". Ayrıntı
      // istenince açılır; istenmeyince tek satır yer kaplar.
      ctx.globalAlpha = paperAlpha(busy ? 0.85 : open ? 0.45 : 0.6);
      ctx.fillStyle = tone;
      ctx.textAlign = "center";
      ctx.font = "600 9px " + (getComputedStyle(document.body).fontFamily);
      // Dil.t: bu kapsamda `t` kare zamanı — küresel çeviriciye tam adla.
      const tag = open ? Dil.t(branch.label).toUpperCase()
                       : Dil.t(branch.label).toUpperCase() + " · " + branch.own.length;
      ctx.fillText(tag, branch.x, branch.y + (branch.below ? 18 : -13));

      branch.branchHub = true;
      branch._hit = { x: branch.x, y: branch.y, r: 14 };
    }
    ctx.textAlign = "left";
    ctx.globalAlpha = 1;

    for (const limb of limbs) {
      // Kapalı dalın yaprağı çizilmez ve tıklanamaz.
      if (!limb.stem || !expanded.has(limb.stem.id)) {
        limb._hit = null;
        continue;
      }
      // Açılış yumuşak: yapraklar 180 ms'de belirir. Aşağıdaki her alpha
      // atamasına çarpan olarak biner (blok kendi alphasını kuruyor).
      const wake = Math.min(1, (t - (branchWake[limb.stem.id] || t)) / 180);
      const busy = limb.since > 0 && t - limb.since < USE_HOLD;
      const beat = busy ? (Math.sin((t - limb.since) / USE_MS * Math.PI * 2) + 1) / 2 : 0;
      const heat = Math.max(
        limb.live ? 0.42 : LIMB_DIM,
        busy ? 0.7 + beat * 0.3 : 0,
        limb === hovered ? 0.9 : 0
      );
      const color = css(LIMB_COLOR[limb.kind] || "fact");
      const r = 5.5;

      // Kullanımdayken çevresinde genişleyen halka.
      if (busy) {
        const k = ((t - limb.since) % USE_MS) / USE_MS;
        ctx.globalAlpha = (1 - k) * 0.5 * wake;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(limb.x, limb.y, r + 3 + k * 18, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Dalına bağlı olduğu görünsün: sönük bir sinir. Çekirdeğe değil
      // dala bağlanıyor — ağacı ağaç yapan şey bu.
      const stem = limb.stem;
      ctx.globalAlpha = paperAlpha(heat * 0.22) * wake;
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(stem ? stem.x : core.x, stem ? stem.y : core.y);
      ctx.lineTo(limb.x, limb.y);
      ctx.stroke();

      // Gövde: altıgen. Yuvarlak olsaydı hatıra düğümlerinden ayırt
      // edilemiyordu — ikisi aynı sahnede duruyor.
      ctx.globalAlpha = paperAlpha(heat) * wake;
      ctx.fillStyle = limb.live ? color + "33" : "rgba(0,0,0,0)";
      ctx.lineWidth = isLight() ? 1.7 : 1.4;
      ctx.shadowColor = color;
      ctx.shadowBlur = busy && !isLight() ? 16 : 0;
      const sides = LIMB_SIDES[limb.kind] || 6;
      // Kare biraz döndürülüyor: eksene oturan bir kare, sahnedeki her şey
      // eğri olduğu için yamuk duruyor.
      const turn = sides === 4 ? Math.PI / 4 : -Math.PI / 2;
      ctx.beginPath();
      for (let i = 0; i < sides; i++) {
        const a = (i / sides) * Math.PI * 2 + turn;
        const px = limb.x + Math.cos(a) * r, py = limb.y + Math.sin(a) * r;
        i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
      }
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      ctx.shadowBlur = 0;

      // Etiket her zaman yazılı: soluk da olsa neye sahip olduğu
      // okunabilmeli. Ağ düğümlerinin aksine bunlar sabit ve az sayıda.
      ctx.globalAlpha = (isLight() ? 0.95 : Math.min(1, heat + 0.15)) * wake;
      ctx.textAlign = "center";
      ctx.fillStyle = busy || limb === hovered ? css("text") : css("dim");
      ctx.font = (isLight() ? "600 11.5px " : "500 10.5px ") + family;
      ctx.shadowBlur = isLight() ? 0 : 10;
      ctx.shadowColor = "#000";
      ctx.fillText(limb.name, limb.x, limb.y + (limb.below ? r + 14 : -r - 9));
      ctx.shadowBlur = 0;

      limb._hit = { x: limb.x, y: limb.y, r: r + 10 };
    }
    ctx.globalAlpha = 1; ctx.textAlign = "left";
  }

  // --- çizim ----------------------------------------------------------
  function paint(t) {
    blend();
    ctx.clearRect(0, 0, view.w, view.h);
    drawAura(t);
    drawRipples(t);
    // Anıların ekran konumu beynin dönüşünden türetiliyor: çizimden önce
    // bir kez hesaplanıyor, sonra web ve düğümler onu kullanıyor.
    projectNodes(t);
    drawWeb();
    // Işıkta beyin MÜREKKEP silüeti anıların ÜSTÜNE basılınca düğümler ve
    // yazılar kayboluyordu. Koyuda nokta bulutu seyrek: anılar önce, beyin
    // yüzey olarak üstte. Işıkta tersi: silüet zemin, anılar üstte okunur.
    if (isLight()) {
      drawCore(t);
      drawNodes(t);
    } else {
      drawNodes(t);
      drawCore(t);
    }
    drawLimbs(t);
    drawSignals(t);
    drawBridges(t);
    drawMode(t);
    drawStatus(t);
    drawLegend();
  }

  // Çekirdeğin hemen altında, o an ne yaptığını söyleyen tek satır. Renk
  // kipin kendi rengi (düşünürken mor, çalışırken amber…), yanında yavaşça
  // atan bir nokta canlı olduğunu gösteriyor. Boştayken hiçbir şey yazmıyor:
  // "hazır" yazısı sürekli ekranda durmak yerine sessizlik daha temiz.
  function drawStatus(t) {
    if (!statusLabel || mode === "idle") return;
    const family = getComputedStyle(document.body).fontFamily;
    const color = isLight()
      ? "rgb(" + paperInk().join(",") + ")"
      : "rgb(" + look.tint.map(Math.round).join(",") + ")";
    const y = core.y + core.r + 30;
    const pulse = 0.6 + 0.4 * (Math.sin(t / 520) + 1) / 2;

    ctx.save();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = "600 12px " + family;
    ctx.letterSpacing = "0.14em";

    const label = statusLabel.toUpperCase();
    const w = ctx.measureText(label).width;
    // Sözcükten önce atan bir nokta.
    ctx.globalAlpha = pulse;
    ctx.fillStyle = color;
    ctx.shadowBlur = isLight() ? 0 : 12; ctx.shadowColor = color;
    ctx.beginPath();
    ctx.arc(core.x - w / 2 - 12, y, 3, 0, Math.PI * 2);
    ctx.fill();

    ctx.globalAlpha = 0.95;
    ctx.shadowBlur = isLight() ? 0 : 16;
    ctx.fillText(label, core.x, y);
    ctx.restore();
    ctx.globalAlpha = 1; ctx.shadowBlur = 0;
  }

  // Renklerin ne anlama geldiği. Sürekli ama çok soluk duruyor: sahneyi
  // bölmeden, "bu renk neydi" diye bakınca cevabı versin. Sol kenarda,
  // dikey ortalı — üst köşe dar pencerede sohbetin, alt köşe geniş
  // pencerede organların; sol kenar ikisinde de boş kalıyor.
  //
  // Yalnızca ekranda gerçekten olanı yazıyor: boş bir bölüm göstermek,
  // olmayan bir şeyi varmış gibi çizmek olurdu.
  const LEGEND_ORDER = ["user", "preference", "lesson", "procedure",
                        "voice", "fact", "goal", "episode", "session"];

  // Her rengin YANINDA ne olduğu yazıyor. Tek kelime ("bilgi", "oturum")
  // neyi temsil ettiğini anlatmıyordu; bir bakışta anlaşılsın diye kısa bir
  // açıklama ekli. Nokta = hatıra türü, şekil = organ türü.
  const LEGEND_GLOSS = {
    user: "Seni tanıdıklarım",
    preference: "Tercihlerin",
    lesson: "Çıkardığım dersler",
    procedure: "Yöntemlerim",
    voice: "Konuşma biçimin",
    fact: "Öğrendiklerim",
    goal: "İş listesi",
    episode: "Geçmiş konuşmalar",
    session: "Geçmiş konuşmalar",
  };

  // Odak modu: legend ve çevre süsü sönüyor, geriye çekirdek + sohbet
  // kalıyor — biriyle konuşur gibi. Sahne yine canlı; yalnızca okuma
  // yardımcıları (renk açıklaması) çekiliyor.
  let focusMode = false;
  function focus(on) { focusMode = !!on; }

  function drawLegend() {
    if (focusMode) return;
    const kinds = [...new Set(nodes.map(n => n.group))]
      .sort((a, b) => LEGEND_ORDER.indexOf(a) - LEGEND_ORDER.indexOf(b));
    const rows = kinds.map(g => ({
      color: css(g), shape: "dot",
      name: t(LABEL[g]) || g, gloss: t(LEGEND_GLOSS[g]) || "",
    }));

    // Uzuvlar: renk VE şekil taşıyor. Sahnede duyu altıgen, cihaz kare,
    // yetenek baklava; legend de aynı şekli çiziyor ki eşleşsin.
    const gap = rows.length ? 1 : 0;
    const limbRows = [];
    if (limbs.some(l => l.kind === "sense" || l.kind === "speech"))
      limbRows.push({ color: css("fact"), shape: "hex", name: t("Duyular"), gloss: t("Mikrofon, kamera, ses") });
    if (limbs.some(l => l.kind === "device"))
      limbRows.push({ color: css("amber"), shape: "square", name: t("Cihazlar"), gloss: t("PLC, sensör, seri port") });
    if (limbs.some(l => l.kind === "module"))
      limbRows.push({ color: css("violet"), shape: "diamond", name: t("Yetenekler"), gloss: t("Kendi yazdığım betikler") });

    if (!rows.length && !limbRows.length) return;

    const family = getComputedStyle(document.body).fontFamily;
    const lh = 20, r = 5, x = 16;
    const total = (rows.length + limbRows.length + gap) * lh;
    let y = Math.max(24, core.y - total / 2);
    // Daha okunur: eskisi (0.26) fark edilmiyordu. Nokta parlak, yazı orta,
    // açıklama sönük — üç kademe bir bakışta ayrışsın.
    const base = reveal ? 0.95 : (isLight() ? 0.92 : 0.5);

    ctx.save();
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";

    const glyph = (shape, cx, cy, color) => {
      ctx.fillStyle = color;
      ctx.beginPath();
      if (shape === "square") {
        ctx.rect(cx - r, cy - r, r * 2, r * 2);
      } else if (shape === "diamond") {
        ctx.moveTo(cx, cy - r); ctx.lineTo(cx + r, cy);
        ctx.lineTo(cx, cy + r); ctx.lineTo(cx - r, cy); ctx.closePath();
      } else if (shape === "hex") {
        for (let k = 0; k < 6; k++) {
          const a = Math.PI / 6 + k * Math.PI / 3;
          const px = cx + Math.cos(a) * r, py = cy + Math.sin(a) * r;
          k ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
        }
        ctx.closePath();
      } else {
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
      }
      ctx.fill();
    };

    const draw = (row) => {
      ctx.globalAlpha = base;
      glyph(row.shape, x + r, y, row.color);
      ctx.font = "600 12.5px " + family;
      ctx.fillStyle = css("text");
      const nx = x + r * 2 + 9;
      ctx.fillText(row.name, nx, y);
      const nameW = ctx.measureText(row.name).width;
      if (row.gloss) {
        ctx.globalAlpha = isLight() ? 0.88 : base * 0.62;
        ctx.font = "500 11.5px " + family;
        ctx.fillStyle = css("dim");
        ctx.fillText("— " + row.gloss, nx + nameW + 6, y + 0.5);
      }
      y += lh;
    };

    rows.forEach(draw);
    if (gap) y += lh * 0.5;
    limbRows.forEach(draw);

    ctx.restore();
    ctx.globalAlpha = 1;
  }

  // Çizim 30 kareye sınırlı. rAF bu makinede 150 Hz tetikleniyor (ölçüldü)
  // ve her karede tam ekran degrade + gölge + 2187 nokta çizmek, gün boyu
  // açık duran bir pencerede boşa yakılan GPU. Buradaki animasyonların
  // hiçbiri 30 karenin üstünü gerektirmiyor — dönüşler yavaş, nabız saniye
  // mertebesinde.
  const PAINT_MS = 33;
  let lastPaint = 0;

  // Panel aç/kapa (ayarlar, görüntüleyici, geçmiş) tuvali BÜYÜTMÜYOR:
  // #scene sabit tam ekran, değişen şey sohbet sütununun YERİ (--gut).
  // ResizeObserver konum değişimini görmez — kutu boyutu aynı kalıyor —
  // ve merkez ancak 30 sn'lik graf tazelemesi layout'u çağırınca
  // düzeliyordu: beyin panelin altında sıkışmış görünüyor, sonra
  // "kendiliğinden" ortalanıyordu. Boş alan her karede yoklanıyor;
  // değiştiyse merkez ve yerleşim ANINDA güncelleniyor — panelin geçiş
  // animasyonu sırasında da düzgün kalıyor.
  let lastFree = 0;

  function frame() {
    raf = requestAnimationFrame(frame);
    const t = now();
    if (t - lastPaint >= PAINT_MS) {
      lastPaint = t;
      const free = freeWidth();
      if (Math.abs(free - lastFree) > 0.5) { lastFree = free; layout(); }
      paint(t);
    }
  }

  function drawAura(t) {
    // Işıkta renkli hale YOK: kâğıda yayılan cyan sis halkaları, beyni ve
    // yazıyı zemine yediriyordu (kullanıcının 'orta alan görünmüyor' dediği
    // şey). Koyu temada hale, sahnenin ışığı.
    if (isLight()) return;
    const beat = (Math.sin(t / look.beat) + 1) / 2;
    const g = ctx.createRadialGradient(core.x, core.y, 0, core.x, core.y, core.r * 4.2);
    g.addColorStop(0, tint(look.glow * 0.5 + beat * 0.025));
    g.addColorStop(0.45, tint(0.03));
    g.addColorStop(1, tint(0));
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, view.w, view.h);
  }

  // Sinaps ağı: sönük ama hep orada. Yol üstündeki bağlar öne çıkıyor.
  function drawWeb() {
    ctx.lineWidth = 1;
    for (const edge of web) {
      const onPath = edge.a.order && edge.b.order &&
        Math.abs(edge.a.order - edge.b.order) === 1;
      const light = isLight();
      ctx.strokeStyle = onPath ? css(edge.b.group) : (light ? css("text") : "#5f86a8");
      ctx.lineWidth = light ? 1.35 : 1;
      ctx.globalAlpha = onPath ? (light ? 0.85 : 0.5) : (light ? 0.38 : WEB_ALPHA * (reveal ? 3 : 1));
      ctx.beginPath();
      ctx.moveTo(edge.a.x, edge.a.y);
      ctx.lineTo(edge.b.x, edge.b.y);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  function drawNodes(t) {
    const family = getComputedStyle(document.body).fontFamily;

    // Uzaktaki (beynin arkasındaki) anı önce çizilmeli ki öndekiler
    // üstünde kalsın — beyin bulutuyla aynı ressam sıralaması.
    const ordered = [...nodes].sort((a, b) => (a.depth ?? 0) - (b.depth ?? 0));
    for (const node of ordered) {
      if (node.flash > 0 && node.lit) {
        const k = (t - node.lit) / FLASH_MS;
        node.flash = k >= 1 ? 0 : 1 - k;
      }

      // Derinlik: yakın (ön) parlak ve büyük, uzak (arka) sönük ve küçük.
      const near = ((node.depth ?? 0) + 1.1) / 2.2;   // 0..1
      const depthAlpha = 0.4 + near * 0.6;
      const depthSize = 0.7 + near * 0.55;

      const onPath = node.order > 0;
      const isFocused = onPath && route[focused] && route[focused].node === node.id;
      const base = onPath ? PATH_FLOOR : 0;
      const heat = Math.max(
        base + node.flash * (1 - base),
        node === selected || node === hovered ? 0.8 : 0,
        isFocused ? 1 : 0,
        reveal ? 0.4 : 0
      );
      const color = css(node.group);
      const lightNode = isLight();

      // Aktivasyonu ileten düğümden gelen ok: yönü de görünsün.
      if (node.from && onPath) {
        const source = byId.get(node.from);
        if (source) {
          ctx.strokeStyle = color;
          ctx.globalAlpha = 0.45 + node.flash * 0.4;
          ctx.lineWidth = 1.4;
          ctx.beginPath();
          ctx.moveTo(source.x, source.y);
          ctx.lineTo(node.x, node.y);
          ctx.stroke();
        }
      }

      const r = (2.2 + heat * 4) * depthSize * (lightNode ? 1.35 : 1);
      if (heat > 0.05) {
        const alpha = Math.round(heat * (lightNode ? 200 : 150)).toString(16).padStart(2, "0");
        const g = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, r * 5);
        g.addColorStop(0, color + alpha);
        g.addColorStop(1, color + "00");
        ctx.globalAlpha = 1;
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(node.x, node.y, r * 5, 0, Math.PI * 2); ctx.fill();
      }

      const twk = 0.68 + 0.32 * (Math.sin(t / 1500 + (node.p3.x - node.p3.z) * 8) * 0.5 + 0.5);
      ctx.globalAlpha = Math.min(1, lightNode
        ? (0.78 + heat * 0.22) * depthAlpha
        : (LATENT * twk + heat * (1 - LATENT)) * depthAlpha);
      ctx.shadowBlur = heat > 0.05 && !lightNode ? 14 : 0; ctx.shadowColor = color;
      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(node.x, node.y, r, 0, Math.PI * 2); ctx.fill();
      ctx.shadowBlur = 0;

      // Etiket yalnızca gerçekten ilgilenilen düğümde: yolun üstündeyse,
      // seçiliyse ya da imleç üstündeyse. "Detayları göster" açıkken bile
      // hepsini birden yazmak ekranı okunmaz yapıyordu — onlarca etiket
      // sohbet metninin üstüne biniyordu.
      const named = onPath || node === selected || node === hovered;
      if (named && heat > 0.3) {
        // Etiket normalde dışa doğru yazılıyor. Kenara yakın bir düğümde
        // dışarısı ekranın dışı demek: yazı kesiliyor ya da sohbetin
        // altına giriyor. O durumda içeri dönüyor.
        const LABEL_ROOM = 130;
        let outward = Math.cos(node.angle) >= 0 ? 1 : -1;
        if (outward > 0 && node.x + LABEL_ROOM > freeWidth()) outward = -1;
        else if (outward < 0 && node.x - LABEL_ROOM < 0) outward = 1;
        ctx.textAlign = outward > 0 ? "left" : "right";
        ctx.globalAlpha = Math.min(1, (heat - 0.3) * 2.6);
        const lx = node.x + outward * (r + 9);
        const ly = node.y + 5;
        // Sıra numarası: haritada kaçıncı durak olduğu okunsun.
        let label = node.label;
        if (onPath) {
          ctx.fillStyle = color;
          ctx.font = "600 10px " + family;
          if (lightNode) {
            ctx.lineWidth = 3; ctx.lineJoin = "round";
            ctx.strokeStyle = "rgba(231, 237, 244, .92)";
            ctx.strokeText(String(node.order), lx, node.y - 8);
          }
          ctx.fillText(String(node.order), lx, node.y - 8);
        }
        ctx.font = "500 11.5px " + family;
        // Şerit yok: ince dış çizgi + düğüm rengi. Beyin üstünde de
        // okunur, kutu gibi durmaz.
        if (lightNode) {
          ctx.lineWidth = 3;
          ctx.lineJoin = "round";
          ctx.strokeStyle = "rgba(231, 237, 244, .92)";
          ctx.strokeText(label, lx, ly);
          ctx.fillStyle = isFocused ? css("text") : color;
        } else {
          ctx.shadowBlur = 12; ctx.shadowColor = "#000";
          ctx.fillStyle = isFocused ? "#ffffff" : "#dceefc";
        }
        ctx.fillText(label, lx, ly);
        ctx.shadowBlur = 0;
        ctx.lineWidth = 1;
      }

      node._hit = { x: node.x, y: node.y, r: r + 8 };
    }
    ctx.globalAlpha = 1; ctx.textAlign = "left";
  }

  // --- beyin ------------------------------------------------------------
  //
  // Dönen bir 3B nokta bulutu. Görüntüyü veren şey kütüphane değil —
  // three.js kullanılamıyor (CDN yok, CSP dışarıya hiçbir istek
  // bırakmıyor, program çevrimdışı da çalışmalı) ama gereken şey zaten
  // birkaç düzine satır: yüzey üzerinde noktalar üret, döndür, izdüşür.
  //
  // Yüzey bir küreden türetiliyor:
  //   ezme        beyin eninden uzun, yüksekliğinden geniş
  //   ön daralma  ön lob arkadan dar
  //   yarık       iki yarımküre ortadan ayrık
  //   kıvrım      yüzeye sinüs toplamıyla girinti-çıkıntı
  //   beyincik    arka altta ayrı, küçük bir lob
  //
  // Nokta bulutu bir kez üretiliyor ve sabit; her karede yalnızca döndürme
  // ve izdüşüm var. Zamanın fonksiyonu olmayan hiçbir birikim yok, yani
  // sekme arka plandayken kareler atlansa da sıçrama olmuyor.

  const SPARKS = 6;        // aynı anda ateşleyen nokta
  // Bakış neredeyse yandan. Tepeden bakınca beyin oval bir leke gibi
  // duruyordu — beyni beyin yapan siluet (ön lob, şakak, altta beyincik)
  // yandan okunuyor. Küçük bir eğim derinlik hissi için yetiyor.
  const TILT = -0.12;

  let cloud = null;

  // Nokta bulutu `brain.js`ten geliyor: gerçek bir beyin geometrisinden
  // seyreltilmiş 2187 nokta.
  //
  // Önce küre + sinüs kıvrımıyla elle kuruluyordu. Uzaktan beyne
  // benziyordu ama yakından bir cevizdi ve her deneme başka bir yerinden
  // bozuluyordu: ön lob sivriliyor, beyincik rafa dönüşüyor, kıvrımlar
  // tarak gibi diziliyordu. Gerçek geometri hem doğru hem de daha ucuz —
  // her karede türetmek yerine hazır noktalar döndürülüyor.
  function brainCloud() {
    if (cloud) return cloud;

    // Dosya yüklenmediyse sahne yine açılmalı: beyinsiz bir çekirdek,
    // hiç açılmayan bir pencereden iyi.
    const flat = typeof BRAIN_POINTS === "undefined" ? null : BRAIN_POINTS;
    if (!flat || !flat.length) { cloud = []; return cloud; }

    const points = [];
    for (let i = 0; i < flat.length; i += 3) {
      const x = flat[i], y = flat[i + 1], z = flat[i + 2];
      // Beyincik: arka altta kalanlar. Ayrı çizilmiyor ama biraz sönük —
      // beyni ondan ayıran doku farkı böyle okunuyor.
      const back = z < -0.35 && y > 0.12;
      points.push({ x, y, z, fold: back ? 0.72 : 1 });
    }
    cloud = points;
    return cloud;
  }

  // Beynin o karedeki dönüşü. Hem bulut hem anılar aynı rotasyonu
  // kullanıyor ki birlikte dönsünler — anı beynin içinde bir yere ait.
  function brainSpin(t) {
    const s = t / 13000 * (0.5 + look.spin * 0.5);
    return { cosY: Math.cos(s), sinY: Math.sin(s), cosX: Math.cos(TILT), sinX: Math.sin(TILT) };
  }

  // Bir 3B noktayı döndürüp perspektifle izdüşürür. Dönüş: Y ekseni +
  // öne eğim. Perspektif: öndeki büyük. Birim uzayda çalışır; ekran
  // ölçeği çağıran tarafta (× r).
  function project3(x, y, z, rot) {
    const rx = x * rot.cosY + z * rot.sinY;
    const rz = -x * rot.sinY + z * rot.cosY;
    const ry = y * rot.cosX - rz * rot.sinX;
    const rz2 = y * rot.sinX + rz * rot.cosX;
    const scale = 2.6 / (2.6 + rz2);
    return { x: rx * scale, y: ry * scale, z: rz2, scale };
  }

  // Bir anının beyin HACMİ içindeki sabit 3B konumu. Bir yüzey noktası
  // seçilip içeri çekiliyor (kabuk değil, iç); küçük bir kimlik-gürültüsü
  // ekleniyor. Aynı kimlik hep aynı yeri verir — engram. Beyin yüklenmediyse
  // küre-içi bir konuma düşülüyor.
  function insideBrain(id) {
    const c = brainCloud();
    if (c.length) {
      const p = c[Math.floor(hash01(id, 0x51ed3f) * c.length)];
      const pull = 0.34 + hash01(id, 0x77aa11) * 0.5;   // 0.34..0.84 içeri
      return {
        x: p.x * pull + (hash01(id, 0x110a) - 0.5) * 0.05,
        y: p.y * pull + (hash01(id, 0x220b) - 0.5) * 0.05,
        z: p.z * pull + (hash01(id, 0x330c) - 0.5) * 0.05,
      };
    }
    const a = hash01(id, 1) * 6.283, u = 2 * hash01(id, 2) - 1;
    const rr = Math.cbrt(hash01(id, 3)) * 0.55, s = Math.sqrt(1 - u * u);
    return { x: s * Math.cos(a) * rr, y: (hash01(id, 4) - 0.5) * 0.9, z: s * Math.sin(a) * rr };
  }

  // Her karede: anıların ekran konumunu beynin rotasyonundan geçirerek
  // hesaplar. Hafif bir akış (kimlik fazına bağlı ufak salınım) ekliyor —
  // beyin içinde canlı, sabit değil. depth ön/arka; drawNodes onu
  // parlaklık ve boyutta kullanıyor.
  function projectNodes(t) {
    const rot = brainSpin(t);
    const r = core.r * 1.45;
    for (const node of nodes) {
      if (!node.p3) node.p3 = insideBrain(node.id);
      const ph = (node.p3.x + node.p3.z) * 6.283, d = 0.018;
      const pr = project3(
        node.p3.x + Math.sin(t / 2600 + ph) * d,
        node.p3.y + Math.cos(t / 3100 + ph) * d,
        node.p3.z + Math.sin(t / 2900 + ph * 1.3) * d,
        rot);
      node.x = core.x + pr.x * r;
      node.y = core.y + pr.y * r;
      node.depth = pr.z;
      node.pscale = pr.scale;
      node.angle = Math.atan2(node.y - core.y, node.x - core.x);
    }
  }

  function drawBrain(t) {
    const points = brainCloud();
    const r = core.r * 1.25;
    const beat = (Math.sin(t / look.beat) + 1) / 2;
    const spin = t / 13000 * (0.5 + look.spin * 0.5);

    const cosY = Math.cos(spin), sinY = Math.sin(spin);
    const cosX = Math.cos(TILT), sinX = Math.sin(TILT);
    // Işık kipinde bulut MÜREKKEP: koyu ton, beyaza doğru açılma YOK. Koyu
    // kipteki "parlak cyan + beyaza kalkış" beyaz zeminde birebir görünmezlik
    // demekti ("renkler arka ile aynı olup kayboluyor"). Kip rengi korunuyor
    // ama koyultularak (0.30×) — düşünürken mor, çalışırken amber yine belli.
    const light = isLight();
    // Işıkta koyu slate silüet (kullanıcının beğendiği netlik) — anılar
    // drawNodes ile ÜSTTE çizildiği için düğümler/yazılar yutulmaz.
    const colour = (light
      ? [28, 48, 68]
      : look.tint).map(Math.round);

    // Uzaktaki nokta önce çizilmeli, yoksa yakındakiler arkada kalıyor.
    // Sıralama her karede: 1500 nokta için maliyeti ölçülemeyecek kadar az.
    const shown = [];
    for (let i = 0; i < points.length; i++) {
      const p = points[i];
      // Y ekseni etrafında dönüş, sonra öne eğim.
      const rx = p.x * cosY + p.z * sinY;
      const rz = -p.x * sinY + p.z * cosY;
      const ry = p.y * cosX - rz * sinX;
      const rz2 = p.y * sinX + rz * cosX;

      // Perspektif: öndekiler büyük. Ortogonal izdüşümde beyin yassı
      // duruyor, derinlik hiç okunmuyor.
      const depth = 2.6 + rz2;
      const scale = 2.6 / depth;
      shown.push({
        x: rx * r * scale,
        y: ry * r * scale,
        z: rz2,
        s: scale,
        f: p.fold,
        i,
      });
    }
    shown.sort((a, b) => a.z - b.z);

    ctx.shadowBlur = 0;
    for (const p of shown) {
      const near = (p.z + 1.1) / 2.2;
      const near2 = near * near;
      if (light) {
        // Net silüet, ama tam opak leke değil — üstteki renkli anılar okunur.
        ctx.globalAlpha = (0.58 + near2 * 0.32) * p.f;
        const shade = 0.88 + near2 * 0.12;
        ctx.fillStyle = "rgb(" + Math.round(colour[0] * shade) + ","
          + Math.round(colour[1] * shade) + "," + Math.round(colour[2] * shade) + ")";
        const size = (1.05 + near2 * 0.7) * p.s;
        ctx.fillRect(p.x - size / 2, p.y - size / 2, size, size);
      } else {
        ctx.globalAlpha = Math.min(1, (0.10 + near2 * 0.85) * p.f);
        const lift = near2 * 110;
        ctx.fillStyle = "rgb(" + Math.max(0, Math.min(255, colour[0] + lift)) + ","
          + Math.max(0, Math.min(255, colour[1] + lift)) + "," + Math.max(0, Math.min(255, colour[2] + lift)) + ")";
        const size = (0.5 + near2 * 0.9) * p.s;
        ctx.fillRect(p.x - size / 2, p.y - size / 2, size, size);
      }
    }

    // Ateşlemeler: birkaç nokta parlıyor. Beynin çalıştığı buradan
    // okunuyor ve hız kipe bağlı — düşünürken sıklaşıyor. Işıkta glow yok:
    // beyaz üstünde parlama, noktayı silikleştirmekten başka iş yapmıyor.
    ctx.shadowColor = css("ice");
    ctx.shadowBlur = light ? 0 : 10;
    ctx.fillStyle = css("ice");
    const period = 1600 / (0.5 + look.spin);
    for (let n = 0; n < SPARKS; n++) {
      const phase = ((t + n * (period / SPARKS)) % period) / period;
      const round = Math.floor((t + n * (period / SPARKS)) / period);
      const p = shown[(n * 271 + round * 97) % shown.length];
      if (!p) continue;
      ctx.globalAlpha = Math.sin(phase * Math.PI) * 0.9;
      ctx.beginPath();
      ctx.arc(p.x, p.y, 1.6 * p.s, 0, Math.PI * 2);
      ctx.fill();
    }

    if (!light) {
      ctx.globalAlpha = beat * 0.05 * (0.5 + look.glow * 4);
      ctx.fillStyle = `rgb(${colour[0]},${colour[1]},${colour[2]})`;
      ctx.beginPath();
      ctx.arc(0, 0, r * 0.95, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.globalAlpha = 1;
    ctx.shadowBlur = 0;
  }

  // Holografik çekirdek: eşmerkezli yaylar, farklı hızlarda.
  function drawCore(t) {
    const light = isLight();
    const cyan = tint(1);
    const seconds = t / 1000;
    const beat = (Math.sin(t / look.beat) + 1) / 2;

    ctx.save();
    ctx.translate(core.x, core.y);
    ctx.strokeStyle = cyan;
    ctx.shadowColor = cyan;

    for (const ring of RINGS) {
      const r = core.r * ring.scale;
      const turn = seconds * ring.speed * look.spin;
      const step = (Math.PI * 2) / ring.parts;
      const arc = step * (1 - ring.gap);

      ctx.lineWidth = ring.width * (light ? 1.55 : 1);
      ctx.globalAlpha = Math.min(1, ring.alpha * (0.85 + look.spin * 0.2) * (light ? 3.4 : 1));
      ctx.shadowBlur = light ? 0 : 6 + look.spin * 5;
      for (let i = 0; i < ring.parts; i++) {
        const from = turn + i * step;
        ctx.beginPath();
        ctx.arc(0, 0, r, from, from + arc);
        ctx.stroke();
      }
    }

    // Ölçek çentikleri: teknik his buradan geliyor.
    const tickR = core.r * 2.24;
    ctx.lineWidth = 1;
    ctx.globalAlpha = light ? 0.78 : 0.3;
    ctx.shadowBlur = 0;
    for (let i = 0; i < 60; i++) {
      const a = (i / 60) * Math.PI * 2 + seconds * 0.05;
      const out = tickR + (i % 5 === 0 ? 9 : 4);
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * tickR, Math.sin(a) * tickR);
      ctx.lineTo(Math.cos(a) * out, Math.sin(a) * out);
      ctx.stroke();
    }

    if (ctx.createConicGradient) {
      // Süpürme beynin dışında bir halka bandında: üstünden geçtiğinde
      // noktaları yıkayıp yutuyordu.
      const wedge = ctx.createConicGradient(seconds * look.wedge, 0, 0);
      // Işıkta süpürme dilimi soluk gri bir sektör gibi kalıyordu: kıs.
      wedge.addColorStop(0, tint(isLight() ? 0.14 : 0.16));
      wedge.addColorStop(0.09, tint(0));
      wedge.addColorStop(1, tint(0));
      ctx.globalAlpha = 1;
      ctx.fillStyle = wedge;
      ctx.beginPath();
      ctx.arc(0, 0, core.r * 2.3, 0, Math.PI * 2);
      ctx.arc(0, 0, core.r * 1.55, 0, Math.PI * 2, true);
      ctx.fill();
    }

    if (!light) {
      const orb = core.r * (0.3 + beat * 0.035);
      const glow = ctx.createRadialGradient(0, 0, 0, 0, 0, orb * 2.2);
      glow.addColorStop(0, tint(0.06 + beat * 0.04));
      glow.addColorStop(0.6, tint(0.02));
      glow.addColorStop(1, "rgba(20,120,160,0)");
      ctx.globalAlpha = 1;
      ctx.fillStyle = glow;
      ctx.beginPath(); ctx.arc(0, 0, orb * 2.2, 0, Math.PI * 2); ctx.fill();
    }

    drawBrain(t);

    ctx.restore();
    ctx.globalAlpha = 1; ctx.shadowBlur = 0;
  }

  function drawRipples(t) {
    const SPAN = 1800;
    ripples = ripples.filter(r => t - r.born < SPAN);
    for (const r of ripples) {
      const k = (t - r.born) / SPAN;
      ctx.strokeStyle = css("cyan");
      ctx.globalAlpha = (1 - k) * 0.3;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(core.x, core.y, core.r * 0.6 + k * core.r * 3.2, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  // --- etkileşim ------------------------------------------------------
  function at(ev) {
    const near = (item) => item._hit &&
      Math.hypot(item._hit.x - ev.clientX, item._hit.y - ev.clientY) <= item._hit.r;
    // Organlar önce: küçükler ve üstteler, düğüm onları yutmasın. Dal
    // göbekleri organlardan sonra: açık daldaki yaprak, göbeğe yakın olsa
    // bile kendisi seçilebilsin.
    return limbs.find(near) || branches.find(near) || nodes.find(near) || null;
  }

  function onMove(ev) {
    pointer = { x: ev.clientX, y: ev.clientY };
    hovered = at(ev);
    // Dal, üzerindeyken geçici açılır; yaprağın üstündeyken de açık kalır
    // (göbekten yaprağa giderken yelpaze kapanmasın).
    hoverBranch = hovered && hovered.branchHub ? hovered
                : hovered && hovered.organ ? hovered.stem
                : null;
    canvas.style.cursor = hovered ? "pointer" : "default";
  }

  function onDown(ev) {
    selected = at(ev);
    if (!selected) { probe.hidden = true; return; }
    if (selected.branchHub) {
      // Göbeğe tıklama: dalı kalıcı açar/kapatır — "istediğimde görürüm".
      if (openBranches.has(selected.id)) openBranches.delete(selected.id);
      else openBranches.add(selected.id);
      probe.hidden = true;
      start();
      return;
    }
    showProbeAt(selected, ev.clientX, ev.clientY);
  }

  function showProbeAt(node, x, y) {
    probe.textContent = "";
    const title = document.createElement("div");
    title.className = "t";
    const kind = document.createElement("div");
    kind.className = "k";
    const body = document.createElement("div");
    body.className = "b";

    if (node.organ) {
      // Aygıtta okunmak istenen şey sırası değil hali: açık mı, o an ne
      // yapıyor. "Açık" ile "kullanılıyor" aynı şey değil.
      title.textContent = node.name;
      kind.textContent = [node.state, node.doing].filter(Boolean).join(" · ");
      body.textContent = node.detail || "";
    } else {
      title.textContent = node.order ? node.order + ". " + node.label : node.label;
      kind.textContent = [t(LABEL[node.group]) || node.group, node.meta].filter(Boolean).join(" · ");
      body.textContent = node.detail || "";
    }
    probe.append(title, kind, body);

    probe.hidden = false;
    const rect = probe.getBoundingClientRect();
    const px = x === undefined ? node.x + 16 : x + 18;
    const py = y === undefined ? node.y + 12 : y + 14;
    probe.style.left = Math.max(20, Math.min(px, innerWidth - rect.width - 20)) + "px";
    probe.style.top = Math.max(70, Math.min(py, innerHeight - rect.height - 20)) + "px";
  }

  // --- kipe özel katman ------------------------------------------------
  //
  // Buradaki her şey türevsiz: konum yalnızca `t`nin fonksiyonu, saklanan
  // parçacık durumu yok. Sebebi tek: sekme arkaplana alınıp kareler
  // atlandığında biriken bir parçacık sistemi geri dönüldüğünde sıçrıyor,
  // saf fonksiyon sıçramıyor.

  function drawMode(t) {
    if (mode === "waking") wakingPulse(t);
    else if (mode === "thinking") thinkingMotes(t);
    else if (mode === "writing") writingStream(t);
    else if (mode === "recalling") recallSweep(t);
    else if (mode === "working") workingPackets(t);
  }

  // Uyanma: tek bir halka yavaşça dışarı açılıyor. Nabız gibi — henüz
  // düşünen kimse yok, yalnızca açılan bir sistem.
  function wakingPulse(t) {
    const cycle = 2600;
    const phase = (t % cycle) / cycle;
    const far = Math.min(view.w, view.h) * 0.3;

    ctx.save();
    ctx.translate(core.x, core.y);
    ctx.globalAlpha = Math.sin(phase * Math.PI) * 0.3;
    ctx.strokeStyle = tint(1);
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.arc(0, 0, core.r * 1.1 + phase * far, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
    ctx.globalAlpha = 1;
  }

  // Düşünme: dışarıdan çekirdeğe doğru sarmalanarak inen izler. Bir şeyin
  // toplandığı, henüz söylenmediği hissi.
  function thinkingMotes(t) {
    const count = 14;
    const cycle = 2600;
    ctx.save();
    ctx.translate(core.x, core.y);
    for (let i = 0; i < count; i++) {
      const phase = ((t + i * (cycle / count)) % cycle) / cycle;
      const r = core.r * (3.1 - phase * 2.0);
      const a = (i / count) * Math.PI * 2 + phase * 2.4 + t / 4000;
      // Baş ve son sönük: içeri girerken beliriyor, çekirdekte eriyor.
      const alpha = Math.sin(phase * Math.PI) * 0.75;

      ctx.globalAlpha = alpha;
      ctx.strokeStyle = tint(1);
      ctx.lineWidth = 1.3;
      ctx.shadowColor = tint(1);
      ctx.shadowBlur = isLight() ? 0 : 10;
      ctx.beginPath();
      ctx.arc(0, 0, r, a, a + 0.16);
      ctx.stroke();
    }
    ctx.restore();
    ctx.globalAlpha = 1; ctx.shadowBlur = 0;
  }

  // Yazma: çekirdeğin altından sohbete doğru akan kısa çizgiler. Metin
  // ekranda belirirken kaynağının çekirdek olduğu görünüyor.
  function writingStream(t) {
    const lanes = 7;
    const cycle = 1100;
    const reach = Math.min(view.h - core.y - core.r * 1.6, core.r * 3.4);
    if (reach <= 0) return;

    ctx.save();
    ctx.translate(core.x, core.y + core.r * 1.5);
    for (let i = 0; i < lanes; i++) {
      const phase = ((t + i * (cycle / lanes)) % cycle) / cycle;
      const y = phase * reach;
      const half = core.r * (0.42 - phase * 0.3) * (1 + (i % 3) * 0.22);
      if (half <= 0) continue;

      ctx.globalAlpha = (1 - phase) * 0.5;
      ctx.strokeStyle = tint(1);
      ctx.lineWidth = 1.6;
      ctx.shadowColor = tint(1);
      ctx.shadowBlur = isLight() ? 0 : 8;
      ctx.beginPath();
      ctx.moveTo(-half, y);
      ctx.lineTo(half, y);
      ctx.stroke();
    }
    ctx.restore();
    ctx.globalAlpha = 1; ctx.shadowBlur = 0;
  }

  // Hatırlama: çekirdekten ağa doğru yayılan sonar halkaları. Aktivasyonun
  // dışarı doğru yürüdüğü bu; hangi düğüme vardığını `activate` gösteriyor.
  function recallSweep(t) {
    const cycle = 1500;
    const rings = 3;
    const far = Math.min(view.w, view.h) * 0.52;

    ctx.save();
    ctx.translate(core.x, core.y);
    for (let i = 0; i < rings; i++) {
      const phase = ((t + i * (cycle / rings)) % cycle) / cycle;
      const r = core.r * 1.2 + phase * far;

      ctx.globalAlpha = (1 - phase) * 0.42;
      ctx.strokeStyle = tint(1);
      ctx.lineWidth = 1.8 - phase;
      ctx.shadowColor = tint(1);
      ctx.shadowBlur = 14;
      ctx.beginPath();
      ctx.arc(0, 0, r, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.restore();
    ctx.globalAlpha = 1; ctx.shadowBlur = 0;
  }

  // Çalışma: çekirdeğin çevresinde dönen veri paketleri. Bir şeyin
  // taşındığı, işlendiği hissi — düşünmenin aksine mekanik.
  function workingPackets(t) {
    const count = 8;
    const r = core.r * 2.35;
    const size = 3.4;

    ctx.save();
    ctx.translate(core.x, core.y);
    ctx.fillStyle = tint(1);
    ctx.shadowColor = tint(1);
    ctx.shadowBlur = 12;
    for (let i = 0; i < count; i++) {
      // Kademeli hız: paketler sıra sıra değil, dağınık geçiyor.
      const a = t / 900 * (1 + (i % 3) * 0.14) + (i / count) * Math.PI * 2;
      ctx.globalAlpha = 0.35 + 0.45 * ((Math.sin(a * 3) + 1) / 2);
      ctx.fillRect(Math.cos(a) * r - size / 2, Math.sin(a) * r - size / 2, size, size);
    }
    ctx.restore();
    ctx.globalAlpha = 1; ctx.shadowBlur = 0;
  }

  const summary = () => stats;

  return { init, load, activate, focusStep, clearRoute, ripple, bridge,
           signal, deposit, organs, use, release,
           setBusy, setMode, summary, redraw, focus };
})();
