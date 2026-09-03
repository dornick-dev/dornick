// Microphone.
//
// There are two modes and both use the same pipe:
//
//   push-to-talk  hold the mic button, speak, release. What you said lands
//                 in the composer — you can fix it before sending.
//   wake          with continuous listening on, short chunks go to the
//                 server; a chunk containing "Dornick" opens the session and
//                 what follows the word is sent directly.
//
// Recognition is on the server and local: audio never leaves the computer.
// The browser's own `SpeechRecognition` API is not used — WebView2 lacks it,
// and where it exists it sends the audio to Google.
//
// The microphone never opens by itself. `getUserMedia` is not called until
// the user presses the button; continuous listening is a separate decision.

const Listen = (() => {
  // Chunk length in wake mode. Shorter reacts faster but recognises more
  // often; longer is the reverse. 3 seconds sits between the two.
  const CHUNK_MS = 3000;

  // One transcription at a time. Without this, every chunk opened a new
  // request, and while the first one downloaded the model (once, ~70 s) new
  // ones piled up behind it. The browser can open six connections to one
  // origin; once full, **everything** queues — even the message you typed
  // stops going out.
  let busy = false;

  // A recording below this level is treated as having no speech. Measuring
  // in bytes was misleading: opus silence takes almost no space, but a short
  // "yes" is a small file too. The threshold is kept low — sending the odd
  // stretch of silence beats missing speech.
  const SILENT = 0.008;

  // Whether sound is heard must be visible. In the "I spoke and nothing
  // happened" case — is the fault the microphone, the recognition, or did
  // recording never start — without a meter you cannot tell.
  const METER_HZ = 24;



  let stream = null;
  let recorder = null;
  let chunks = [];
  let mode = "off";          // off | push | wake
  let onText = () => {};
  let onCommand = () => {};
  let onState = () => {};
  let onLevel = () => {};

  // Level meter.
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
    // This line opens the permission prompt; we never get here unless the
    // user asked.
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
      // If we do not release the track, the browser keeps its "recording"
      // indicator on and the microphone stays busy.
      for (const track of stream.getTracks()) track.stop();
      stream = null;
    }
  }

  // --- level meter -------------------------------------------------------

  // Did the meter actually run? If not, deciding by level is wrong: it reads
  // permanent silence, and a recording with real speech was being dropped as
  // "no sound heard".
  let metering = false;

  function startMeter() {
    if (analyser || !stream) return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      // The audio context starts suspended until a user gesture. While
      // suspended the analyser always returns 128 (silence) — the meter shows
      // zero and even a spoken recording counted as "silent".
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
      // Mean deviation: 128 is silence, distance from it is sound.
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

  // Does the recording carry speech? If the meter never ran, assume it does:
  // dropping a recording on an untrustworthy measurement is far worse than
  // sending silence to the server.
  const spoken = (loud) => !metering || loud === undefined || loud >= SILENT;

  // --- click-speak-click -------------------------------------------------
  //
  // Not hold-to-talk: the user clicked the button and let go, which produced
  // a zero-second recording that was silently discarded. A click starts,
  // another click finishes.

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

    // Wake listening, if any, is paused: two recorders cannot share the
    // same track.
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
      // If wake mode was interrupted, resume it.
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
    // The track is not closed: for back-to-back speech, re-acquiring the
    // permission every time is both slow and annoying.
  }

  // --- wake --------------------------------------------------------------

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
    // It does not announce that it is waiting. A person waiting in a room
    // does not stand there saying "I am waiting"; they stand quietly and turn
    // when called.
    //
    // But it does show that it hears: the meter runs in the background too,
    // and the mic icon comes alive when you speak. The answer to "is it
    // listening, does it hear" is given this way, not in words.
    onState("");
    startMeter();
    loop();
  }

  function loop() {
    // Wake listening stops during push-to-talk: two recorders cannot share
    // the same track.
    if (mode !== "wake" || !stream) return;

    chunks = [];
    peak = 0;
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (event) => chunks.push(event.data);
    recorder.onstop = () => {
      const loud = peak;
      // A silent chunk is never sent, nor anything while a transcription is
      // pending: the first is wasted work, the second ate the connection
      // quota and queued even the message you typed.
      if (spoken(loud) && !busy) {
        send(new Blob(chunks, { type: "audio/webm" }), true, loud);
      }
      // The next chunk starts immediately; leave a gap and the wake word
      // lands in the gap and escapes.
      loop();
    };
    recorder.start();
    setTimeout(() => {
      if (recorder && recorder.state !== "inactive") recorder.stop();
    }, CHUNK_MS);
  }

  // --- sending -----------------------------------------------------------

  async function send(blob, listening, loud) {
    if (!blob || !blob.size) {
      if (!listening) onState("Kayıt boş — mikrofon başka bir program tarafından kullanılıyor olabilir");
      return;
    }
    // Measuring silence in bytes was misleading: opus silence takes almost
    // no space, but a short "yes" is a small file too.
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
      // There was sound but no words came out: noise, or too short.
      if (!listening) onState("Bir şey anlaşılmadı");
      return;
    }

    if (listening) {
      // In wake mode not everything heard is sent; only what carries the word.
      if (answer.wake && answer.command) onCommand(answer.command);
      return;
    }

    onText(answer.text);
    onState("");
  }

  return { init, start, stop, toggle, wake, release, get mode() { return mode; } };
})();
