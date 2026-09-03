// Capsule: runs and shows an in-system app INSIDE Dornick, in a live frame.
//
// The distinction is the user's intent: an EXTERNAL app is simply a separate
// external application — it opens in its own window/tab. An IN-SYSTEM one is a
// capsule bound to Dornick: Dornick runs the process in the background (shell
// auto-background) while the capsule WATCHES it (live address, uptime,
// liveness), CONTROLS it (reload, stop) and shows it. That way both Dornick
// itself and the user through the UI can use it — a stock tracker, a modbus
// viewer, a web dashboard opens like a page inside the system.
//
// Sources: /api/apps/run (start → pid), /api/apps/running (pid → live
// address + start time), /api/apps/stop (stop).

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

  // app: { name, pid, address?, started? }. If an address is given, loads it
  // right away; if not (freshly started) polls until the process binds a port.
  function open(app) {
    current = { name: app.name || "Uygulama", pid: app.pid, address: app.address || "",
                started: app.started || 0 };
    nameEl.textContent = current.name;
    uptimeEl.textContent = "";
    dot.classList.remove("dead");
    panel.hidden = false;
    document.body.classList.add("capsule-open");
    if (current.address) loadFrame(current.address);
    else { showWait("Dornick uygulamayı başlatıyor…"); findAddress(); }
    startPoll();
  }

  function loadFrame(address) {
    current.address = address;
    addrEl.textContent = address;
    hideWait();
    if (frame.getAttribute("src") !== address) frame.setAttribute("src", address);
  }

  // Poll until the address the pid listens on shows up (a server can take a
  // few seconds to bind its port). If the process dies or no address appears
  // within a reasonable time, say so explicitly.
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
        showWait("Uygulama kapandı. Sunucu başlamadan çıktıysa Dornick'e " +
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

  // Watch the process live while the panel is open: keep the uptime ticking,
  // make death visible, and load the frame if the address appeared late.
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
    } catch { /* swallow: the poll will see the death anyway */ }
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
