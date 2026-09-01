// Kamera.
//
// Kare almadan önce canlı bir önizleme açılıyor: ne gönderdiğini görmeden
// göndermek, kameranın ne yakaladığını bilmemek demek. Önizleme çıplak bir
// video değil — köşe ayraçları, tarama çizgisi ve altında ajanın söyledikleri.
//
// Yüz çerçevesi konusunda dürüst olmak gerekiyor: **tanımayı model yapıyor,
// tarayıcı değil.** Chromium'un `FaceDetector` API'si varsa kutu gerçek bir
// yüzün etrafına oturuyor; yoksa ortada sabit bir nişangâh duruyor ve
// "burayı görüyorum" demiyor, yalnızca çerçeveliyor. Etiket ise karenin
// gönderilmesinden sonra modelin kendi cevabından geliyor.
//
// Kamera sürekli açık kalmıyor: önizleme kapanınca şerit bırakılıyor.

const Camera = (() => {
  // Gönderilecek karenin uzun kenarı. Daha büyüğü bağlamda yer yakıyor
  // (bir görüntü kabaca 1.5–4.8k token) ve fark edilir bir kazanç yok.
  const MAX_EDGE = 1024;
  const QUALITY = 0.82;

  const panel = document.getElementById("lens");
  const video = document.getElementById("lens-video");
  const overlay = document.getElementById("lens-frame");
  const label = document.getElementById("lens-label");

  let stream = null;
  let detector = null;
  let raf = null;
  let onFrame = () => {};

  function init(opts) {
    onFrame = opts.onFrame || onFrame;
    // Tarayıcıda gerçek bir yüz bulucu varsa kullanılıyor; yoksa çerçeve
    // ortada duruyor. İkisi de aynı görünüyor, farkı kutunun takip etmesi.
    if ("FaceDetector" in window) {
      try {
        detector = new window.FaceDetector({ fastMode: true, maxDetectedFaces: 3 });
      } catch { detector = null; }
    }
  }

  // --- önizleme ----------------------------------------------------------

  async function open() {
    if (stream) return true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 } },
      });
    } catch {
      return false;
    }

    video.srcObject = stream;
    video.muted = true;
    await video.play().catch(() => {});
    panel.hidden = false;
    document.body.classList.add("lensing");
    say("Taranıyor");
    loop();
    return true;
  }

  function close() {
    cancelAnimationFrame(raf);
    raf = null;
    panel.hidden = true;
    document.body.classList.remove("lensing");
    // Şerit bırakılmazsa kamera ışığı yanık kalıyor.
    if (stream) {
      for (const track of stream.getTracks()) track.stop();
      stream = null;
    }
    video.srcObject = null;
  }

  const open_ = () => (panel.hidden ? open() : (close(), false));

  function say(text) {
    label.textContent = text || "";
  }

  // --- çerçeve -----------------------------------------------------------

  // Yüz bulucu saniyede bu kadar çalışıyor. `raf % 6` güvenilir değildi:
  // istek kimliği sayaç değil, altıya bölümü rastgele. Zamanla ölçmek hem
  // doğru hem de ana thread'i boşta bırakıyor.
  const DETECT_MS = 250;
  let lastDetect = 0;

  function loop() {
    raf = requestAnimationFrame(loop);
    if (!detector) return;
    const now = performance.now();
    if (now - lastDetect < DETECT_MS) return;
    lastDetect = now;
    detect();
  }

  let detecting = false;

  async function detect() {
    if (detecting) return;
    detecting = true;
    try {
      const faces = await detector.detect(video);
      place(faces.map((f) => f.boundingBox));
    } catch {
      detector = null;   // bir kez patlıyorsa bir daha sorma
    } finally {
      detecting = false;
    }
  }

  // Kutuları video karesinden panel ölçüsüne taşır.
  function place(boxes) {
    const w = video.videoWidth || 1;
    const h = video.videoHeight || 1;
    overlay.textContent = "";

    for (const box of boxes.slice(0, 3)) {
      const node = document.createElement("div");
      node.className = "lens-box";
      node.style.left = (box.x / w) * 100 + "%";
      node.style.top = (box.y / h) * 100 + "%";
      node.style.width = (box.width / w) * 100 + "%";
      node.style.height = (box.height / h) * 100 + "%";
      overlay.append(node);
    }
  }

  // --- kare --------------------------------------------------------------

  function draw() {
    const w = video.videoWidth || 640;
    const h = video.videoHeight || 480;
    const scale = Math.min(1, MAX_EDGE / Math.max(w, h));

    const canvas = document.createElement("canvas");
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    // JPEG: aynı kare PNG'de üç dört kat büyük ve fotoğrafta fark yok.
    return canvas.toDataURL("image/jpeg", QUALITY);
  }

  async function snap() {
    if (!stream && !(await open())) return null;
    // Kamera yeni açıldıysa ilk kare siyah gelebiliyor: pozlama ayarlanıyor.
    // Eskiden kör bir 350 ms bekleme vardı — hızlı kamerada her mesajı
    // boşuna bekletiyor, yavaş kamerada yine siyah kare çekiyordu. Artık
    // gerçek kare olayı bekleniyor; 1 sn'de gelmezse eldekiyle devam.
    if (!video.videoWidth) {
      await new Promise((done) => {
        const timer = setTimeout(done, 1000);
        const ready = () => { clearTimeout(timer); done(); };
        if ("requestVideoFrameCallback" in video) video.requestVideoFrameCallback(ready);
        else video.addEventListener("loadeddata", ready, { once: true });
      });
    }

    const frame = draw();
    onFrame(frame);
    return frame;
  }

  return { init, open, close, toggle: open_, snap, say, get on() { return !!stream; } };
})();
