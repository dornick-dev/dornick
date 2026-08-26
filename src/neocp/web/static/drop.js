// Sohbete bırakılan dosyalar.
//
// Üç yol da aynı yere çıkıyor: sürükle-bırak, kopyala-yapıştır, ve gözat.
// Tarayıcı yerel dosyanın yolunu vermiyor (güvenlik gereği), yalnızca
// içeriğini; o yüzden dosya atölyeye kopyalanıyor ve ajana **yol**
// veriliyor. Oradan `read_file` ile açıp inceleyebiliyor.
//
// Görüntüler ayrı ele alınıyor: mesaja doğrudan iliştiriliyor ve model
// bakabiliyor. Yine de dosya olarak da atölyede kalıyor — sonra tekrar
// açması gerekebilir.

const Drop = (() => {
  // Tarayıcı içeriği base64 ile taşıyor (üçte bir şişme) ve bellekte
  // tutuyor. Sunucu tarafında da aynı sınır var.
  const LIMIT = 25 * 1024 * 1024;

  let onFile = () => {};
  let onImage = () => {};
  let onNote = () => {};

  function init(opts) {
    onFile = opts.onFile || onFile;
    onImage = opts.onImage || onImage;
    onNote = opts.onNote || onNote;
    bind();
  }

  const isImage = (file) => (file.type || "").startsWith("image/");

  async function take(file) {
    if (!file) return;
    if (file.size > LIMIT) {
      onNote(`${file.name} çok büyük (${(file.size / 1024 / 1024).toFixed(0)} MB, en fazla 25 MB)`);
      return;
    }

    const data = await read(file);
    if (!data) { onNote(`${file.name} okunamadı`); return; }

    // Görüntü mesaja iliştiriliyor: model bakabilsin.
    if (isImage(file)) onImage(data);

    let answer = {};
    try {
      answer = await (await fetch("/api/drop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: file.name, data }),
      })).json();
    } catch {
      onNote(`${file.name} atölyeye yazılamadı`);
      return;
    }

    if (!answer.ok) { onNote(answer.error || "Yazılamadı"); return; }
    onFile(answer);
  }

  function read(file) {
    return new Promise((done) => {
      const reader = new FileReader();
      reader.onload = () => done(String(reader.result || ""));
      reader.onerror = () => done("");
      reader.readAsDataURL(file);
    });
  }

  // --- bağlama -----------------------------------------------------------

  function bind() {
    const zone = document.body;

    // Varsayılan davranış dosyayı pencerede **açıyor** ve uygulamadan
    // çıkıyor; her ikisinde de engellenmeli.
    for (const name of ["dragenter", "dragover"]) {
      zone.addEventListener(name, (ev) => {
        if (!hasFiles(ev)) return;
        ev.preventDefault();
        zone.classList.add("dropping");
      });
    }
    for (const name of ["dragleave", "drop"]) {
      zone.addEventListener(name, (ev) => {
        // dragleave iç öğelere geçerken de tetikleniyor; yalnızca pencereden
        // gerçekten çıkıldığında kapatılıyor.
        if (name === "dragleave" && ev.relatedTarget) return;
        zone.classList.remove("dropping");
      });
    }

    zone.addEventListener("drop", (ev) => {
      if (!hasFiles(ev)) return;
      ev.preventDefault();
      for (const file of ev.dataTransfer.files) take(file);
    });

    // Yapıştırma: ekran görüntüsü panoda görüntü olarak duruyor.
    document.addEventListener("paste", (ev) => {
      const items = ev.clipboardData ? ev.clipboardData.files : null;
      if (!items || !items.length) return;   // düz metin: yazma satırına gitsin
      ev.preventDefault();
      for (const file of items) take(file);
    });

    // Gözat.
    const picker = document.getElementById("file-input");
    document.getElementById("clip").addEventListener("click", () => picker.click());
    picker.addEventListener("change", () => {
      for (const file of picker.files) take(file);
      picker.value = "";   // aynı dosya art arda seçilebilsin
    });
  }

  const hasFiles = (ev) =>
    ev.dataTransfer && [...(ev.dataTransfer.types || [])].includes("Files");

  return { init, take };
})();
