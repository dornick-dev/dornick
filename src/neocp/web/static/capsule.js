// Kapsül: sistem içi bir uygulamayı neo'nun İÇİNDE, canlı bir çerçevede
// çalıştırır ve gösterir.
//
// Ayrım kullanıcının niyeti: DIŞ uygulama zaten ayrı bir dış uygulamadır —
// kendi penceresinde/sekmesinde açılır. SİSTEM İÇİ olan ise neo'ya bağlı bir
// kapsüldür: neo arkada süreci çalıştırır (shell auto-background), kapsül onu
// İZLER (canlı adres, çalışma süresi, canlılık), KONTROL eder (yenile, durdur)
// ve gösterir. Böylece hem neo kendi kullanabilir hem kullanıcı arayüz
// üzerinden — bir stok takibi, bir modbus görüntüleyici, bir web panosu
// sistemin içinde bir sayfa gibi açılır.
//
// Kaynaklar: /api/apps/run (başlat → pid), /api/apps/running (pid → canlı
// adres + başlangıç), /api/apps/stop (durdur).

const Capsule = (() => {
  const panel = document.getElementById("capsule");
  const frame = document.getElementById("capsule-frame");
  const nameEl = document.getElementById("capsule-name");
  const addrEl = document.getElementById("capsule-addr");
  const uptimeEl = document.getElementById("capsule-uptime");
  const dot = document.getElementById("capsule-dot");
  const wait = document.getElementById("capsule-wait");
  const waitText = document.getElementById("capsule-wait-text");

  let current = null;   // { name, pid, address, started }
  let poll = null;
  let findTimer = null;

  // app: { name, pid, address?, started? }. Adres verilmişse hemen yükler;
  // verilmemişse (yeni başlatıldıysa) süreç portu bağlayana dek yoklar.
  function open(app) {
    current = { name: app.name || "Uygulama", pid: app.pid, address: app.address || "",
                started: app.started || 0 };
    nameEl.textContent = current.name;
    uptimeEl.textContent = "";
    dot.classList.remove("dead");
    panel.hidden = false;
    document.body.classList.add("capsule-open");
    if (current.address) loadFrame(current.address);
    else { showWait("neo uygulamayı başlatıyor…"); findAddress(); }
    startPoll();
  }

  function loadFrame(address) {
    current.address = address;
    addrEl.textContent = address;
    hideWait();
    if (frame.getAttribute("src") !== address) frame.setAttribute("src", address);
  }

  // pid'in dinlediği adres belirene dek yokla (sunucu portu birkaç saniyede
  // bağlayabilir). Süreç ölürse ya da makul sürede adres çıkmazsa açıkça söyle.
  function findAddress() {
    clearTimeout(findTimer);
    let tries = 0;
    const tick = async () => {
      if (!current) return;
      tries++;
      const proc = await procFor(current.pid);
      if (proc && proc.address) {
        if (proc.started) current.started = proc.started;
        loadFrame(proc.address);
        return;
      }
      if (!proc) {
        markDead();
        showWait("Uygulama kapandı. Sunucu başlamadan çıktıysa neo'ya " +
                 "“" + (current.name || "uygulama") + " neden kapandı?” diye sorabilirsin.");
        return;
      }
      if (tries > 25) {
        showWait("Bir web adresi açılmadı. Bu bir sunucu değilse kapsülde " +
                 "gösterilecek bir sayfa yok; yine de arka planda çalışıyor.");
        return;
      }
      findTimer = setTimeout(tick, 600);
    };
    tick();
  }

  async function procFor(pid) {
    try {
      const data = await (await fetch("/api/apps/running")).json();
      return (data.running || []).find((p) => p.pid === pid) || null;
    } catch { return null; }
  }

  // Panel açıkken süreci canlı izle: çalışma süresi ilerlesin, ölürse belli
  // olsun, adres sonradan belirdiyse çerçeveyi yükle.
  function startPoll() {
    clearInterval(poll);
    poll = setInterval(async () => {
      if (!current) return;
      const proc = await procFor(current.pid);
      if (!proc) { markDead(); return; }
      dot.classList.remove("dead");
      if (proc.started) { current.started = proc.started; uptimeEl.textContent = uptime(proc.started); }
      if (proc.address && !current.address) loadFrame(proc.address);
    }, 3000);
  }

  function markDead() {
    dot.classList.add("dead");
    uptimeEl.textContent = "durdu";
    clearInterval(poll); poll = null;
  }

  function uptime(started) {
    const s = Math.max(0, Math.round(Date.now() / 1000 - started));
    if (s < 60) return s + " sn";
    const m = Math.floor(s / 60);
    if (m < 60) return m + " dk";
    return Math.floor(m / 60) + " sa " + (m % 60) + " dk";
  }

  function showWait(text) { waitText.textContent = text; wait.hidden = false; }
  function hideWait() { wait.hidden = true; }

  async function stop() {
    if (!current) return;
    try {
      await fetch("/api/apps/stop", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pid: current.pid }),
      });
    } catch { /* yut: yoklama zaten ölümü görecek */ }
    markDead();
    if (typeof Apps !== "undefined" && Apps.load) Apps.load();
  }

  function close() {
    panel.hidden = true;
    document.body.classList.remove("capsule-open");
    frame.setAttribute("src", "about:blank");
    clearInterval(poll); poll = null;
    clearTimeout(findTimer);
    current = null;
  }

  document.getElementById("capsule-close").addEventListener("click", close);
  document.getElementById("capsule-stop").addEventListener("click", stop);
  document.getElementById("capsule-reload").addEventListener("click", () => {
    if (current && current.address) { frame.setAttribute("src", "about:blank"); requestAnimationFrame(() => frame.setAttribute("src", current.address)); }
  });
  const external = () => { if (current && current.address) window.open(current.address, "_blank", "noopener"); };
  document.getElementById("capsule-external").addEventListener("click", external);
  addrEl.addEventListener("click", external);

  return { open, close };
})();
