// Files dropped into the chat.
//
// All three paths lead to the same place: drag-and-drop, copy-paste, and
// browse. The browser does not give a local file's path (by security
// design), only its content; so the file is copied into the workshop and
// the agent is given the **path**. From there it can open and inspect it
// with `read_file`.
//
// Images are handled separately: they are attached to the message directly
// and the model can look at them. They still stay in the workshop as files
// too — it may need to open them again later.

const Drop = (() => {
  // The browser carries content as base64 (a one-third bloat) and keeps it
  // in memory. The same limit exists on the server side.
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
    // An image is NOT split into a separate preview surface: one record,
    // with its thumbnail. (The old state spawned both a frame preview and a
    // name chip — "I have to hit two separate close buttons".) On send the
    // last image is attached to the message; the copy already sits in the
    // workshop.
    onFile(isImage(file) ? { ...answer, image: data } : answer);
  }

  function read(file) {
    return new Promise((done) => {
      const reader = new FileReader();
      reader.onload = () => done(String(reader.result || ""));
      reader.onerror = () => done("");
      reader.readAsDataURL(file);
    });
  }

  // --- wiring ------------------------------------------------------------

  function bind() {
    const zone = document.body;

    // The default behaviour **opens** the file in the window and leaves the
    // app; it must be blocked on both events.
    for (const name of ["dragenter", "dragover"]) {
      zone.addEventListener(name, (ev) => {
        if (!hasFiles(ev)) return;
        ev.preventDefault();
        zone.classList.add("dropping");
      });
    }
    for (const name of ["dragleave", "drop"]) {
      zone.addEventListener(name, (ev) => {
        // dragleave also fires when moving over inner elements; only close
        // when the window is genuinely left.
        if (name === "dragleave" && ev.relatedTarget) return;
        zone.classList.remove("dropping");
      });
    }

    zone.addEventListener("drop", (ev) => {
      if (!hasFiles(ev)) return;
      ev.preventDefault();
      for (const file of ev.dataTransfer.files) take(file);
    });

    // Paste: a screenshot sits on the clipboard as an image.
    document.addEventListener("paste", (ev) => {
      const items = ev.clipboardData ? ev.clipboardData.files : null;
      if (!items || !items.length) return;   // plain text: let it go to the composer
      ev.preventDefault();
      for (const file of items) take(file);
    });

    // Browse.
    const picker = document.getElementById("file-input");
    document.getElementById("clip").addEventListener("click", () => picker.click());
    picker.addEventListener("change", () => {
      for (const file of picker.files) take(file);
      picker.value = "";   // so the same file can be picked twice in a row
    });
  }

  const hasFiles = (ev) =>
    ev.dataTransfer && [...(ev.dataTransfer.types || [])].includes("Files");

  return { init, take };
})();
