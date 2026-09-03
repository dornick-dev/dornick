// Camera.
//
// A live preview opens before a frame is taken: sending without seeing what
// you send means not knowing what the camera captured. The preview is not a
// bare video — corner brackets, a scan line, and the agent's words below.
//
// Honesty is required about the face frame: **the model does the recognising,
// not the browser.** If Chromium's `FaceDetector` API exists, the box sits
// around a real face; otherwise a fixed reticle stays in the middle and does
// not claim "I see this spot", it only frames. The label comes from the
// model's own answer after the frame is sent.
//
// The camera does not stay on: the track is released when the preview closes.

const Camera = (() => {
  // Long edge of the frame to send. Anything bigger burns context space
  // (one image is roughly 1.5–4.8k tokens) with no noticeable gain.
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
    // If the browser has a real face detector it is used; otherwise the
    // frame stays centred. Both look the same, the difference is tracking.
    if ("FaceDetector" in window) {
      try {
        detector = new window.FaceDetector({ fastMode: true, maxDetectedFaces: 3 });
      } catch { detector = null; }
    }
  }

  // --- preview -----------------------------------------------------------

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
    // If the track is not released, the camera light stays on.
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

  // --- frame overlay -----------------------------------------------------

  // How often per second the face detector runs. `raf % 6` was unreliable:
  // the request id is not a counter, its modulo six is random. Measuring by
  // time is both correct and leaves the main thread idle.
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
      detector = null;   // if it blows up once, do not ask again
    } finally {
      detecting = false;
    }
  }

  // Maps the boxes from the video frame to panel dimensions.
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

  // --- snapshot ----------------------------------------------------------

  function draw() {
    const w = video.videoWidth || 640;
    const h = video.videoHeight || 480;
    const scale = Math.min(1, MAX_EDGE / Math.max(w, h));

    const canvas = document.createElement("canvas");
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    // JPEG: the same frame is three to four times bigger as PNG, with no
    // visible difference for a photo.
    return canvas.toDataURL("image/jpeg", QUALITY);
  }

  async function snap() {
    if (!stream && !(await open())) return null;
    // Right after opening, the first frame can come back black: exposure is
    // still settling. There used to be a blind 350 ms wait — on a fast camera
    // it delayed every message for nothing, on a slow one it still shot a
    // black frame. Now the real frame event is awaited; if it does not come
    // within 1 s, continue with what we have.
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
