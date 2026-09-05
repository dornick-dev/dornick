// The scene: a holographic core in the middle, a neural web around it.
//
// Three decisions shape this entire file:
//
//   1. No humanoid figure. A hand-drawn silhouette never came close to
//      the reference render; the abstract core both looks better and can
//      animate to match the state.
//   2. The web sits dim by default. Showing every memory all the time
//      makes a map, not remembering. Nodes fire when the agent visits.
//   3. But the trace does not fade away. An animation that flashed and
//      passed in a second could not be followed; the recall path is
//      numbered and stays on screen, readable until the next recall.

// English translations of the texts this file shows the user. The source
// text stays Turkish; it is translated at display time with t("...").
Lang.add({
  // Memory kinds (probe + legend)
  "Ben": "Me", "Kullanıcı": "User", "Tercih": "Preference", "Ders": "Lesson",
  "Yordam": "Procedure", "Bilgi": "Fact", "Hedef": "Goal", "Oturum": "Session",
  "Dünya": "World", "Gördüklerim": "What I have seen",
  "doğrulanmamış": "unverified", "doğrulama": "verified", "soğuk": "cold",
  // Show/hide button
  "tüm hatıraları gizle": "hide all memories",
  "ağdaki tüm hatıraları göster": "show all memories in the web",
  // Status label under the core
  "Uyanıyor": "Waking", "Düşünüyor": "Thinking", "Yazıyor": "Writing",
  "Hatırlıyor": "Recalling", "Çalışıyor": "Working",
  // Branches
  "Duyular": "Senses", "Cihazlar": "Devices", "Yetenekler": "Skills",
  // Legend glosses
  "Seni tanıdıklarım": "What I know about you",
  // Memory card
  "Anahtar kelimeler": "Keywords", "Nasıl öğrendim": "How I learned it",
  "Konuşmaya git →": "Open the conversation →",
  "çift tık da açar": "double-click also opens it",
  "kaynak konuşma artık yok": "the source conversation is gone",
  "bu konuşmada": "in this conversation",
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
    episode: "Oturum", world: "Dünya"
  };

  // Rings: radius multiplier, speed (rad/s), part count, gap ratio.
  // The rings sit **around** the brain, not on it. The previous version
  // rode on top of the brain and the real subject was unclear; radii were
  // pushed out and brightness lowered. They still carry the mode
  // animation — what speeds up while thinking is these rings.
  const RINGS = [
    { scale: 1.62, speed: 0.08, parts: 3, gap: 0.30, width: 1.6, alpha: 0.30 },
    { scale: 1.86, speed: -0.12, parts: 6, gap: 0.42, width: 1.0, alpha: 0.22 },
    { scale: 2.10, speed: 0.20, parts: 12, gap: 0.55, width: 0.9, alpha: 0.16 },
    { scale: 2.38, speed: -0.04, parts: 2, gap: 0.72, width: 0.9, alpha: 0.12 }
  ];
  // Outermost ring + ticks (×2.24+9px). Whichever is bigger must fit
  // without touching the panel edge — else the silhouette overflows
  // right/left/up.
  const RING_OUTER = RINGS[RINGS.length - 1].scale;
  const TICK_SCALE = 2.24;
  const TICK_OUT = 9;
  const ringReach = (r) => Math.max(r * RING_OUTER, r * TICK_SCALE + TICK_OUT);

  // The core's states. What the agent is doing must be readable on
  // screen: the "busy / idle" pair showed all work the same — thinking and
  // reading a file fell into one animation. Each mode carries its own
  // character, with soft transitions between them (a hard jump breaks the
  // scene).
  //
  //   spin   rotation multiplier for the rings
  //   beat   pulse period, ms — smaller is more restless
  //   glow   strength of the aura
  //   wedge  speed of the conic sweep
  //   tint   colour of the core
  // Speeds are deliberately low: ring/sweep got dialled down until nobody
  // said "it spins way too fast, unpleasant". Alive, but easy on the eye.
  const MODES = {
    // Waking: slow, dim, cold. Nobody is here yet.
    waking:    { spin: 0.10, beat: 3200, glow: 0.04, wedge: 0.05, tint: [96, 88, 74] },
    idle:      { spin: 0.26, beat: 2400, glow: 0.10, wedge: 0.12, tint: [240, 160, 32] },
    thinking:  { spin: 0.42, beat: 1600, glow: 0.17, wedge: 0.32, tint: [196, 181, 253] },
    writing:   { spin: 0.34, beat: 1400, glow: 0.15, wedge: 0.24, tint: [134, 239, 172] },
    recalling: { spin: 0.48, beat: 1500, glow: 0.21, wedge: 0.40, tint: [245, 239, 228] },
    working:   { spin: 0.44, beat: 1500, glow: 0.18, wedge: 0.36, tint: [235, 120, 50] }
  };

  // The per-frame share of a mode transition. Nearer 1, harder the cut.
  const BLEND = 0.055;

  // Between steps. Shorter than the signal's journey: the next impulse
  // departs before the previous reaches its target and the chain flows.
  // Shortening it makes the flow unwatchable — being watched is the whole
  // point. Kept deliberately slow so the signal's walk toward the memories
  // can be followed by eye.
  const STEP_MS = 720;
  const FLASH_MS = 900;     // decay time of the firing flash
  const BRIDGE_MS = 2200;   // how long a forged link stays visible
  const PATH_FLOOR = 0.46;  // the path never fades below this level
  const LATENT = 0.13;      // the web's dim state
  const WEB_ALPHA = 0.055;  // the synapse links' dim state

  let canvas, ctx, probe, revealBtn, onRoute = () => {};
  let onSession = () => {};   // double-click / "Konuşmaya git": jump to the source
  let view = { w: 0, h: 0 };
  let nodes = [], byId = new Map(), web = [], stats = {};
  let core = { x: 0, y: 0, r: 0 };
  let ripples = [], bridges = [], reveal = false;
  // `look` holds the values currently on screen; `mode` the target mode.
  // Each frame closes some of the gap between the two.
  let mode = "idle", look = { ...MODES.idle, tint: [...MODES.idle.tint] };
  let route = [], focused = -1;
  let selected = null, hovered = null;
  let raf = null, pointer = { x: 0, y: 0 };
  let pane = null;         // current rect of the right brain panel (null if none)
  let hole = null;         // the hole the rings fit into (minus header/organs/legend)
  let searchHits = null;   // memory search: matching node ids (null if none)

  // --- the event clock (Phase 6) ----------------------------------------
  // Night events are drawn with the same signal/strike mechanics as the
  // recall trace, but on their own clock. `uyku.uyandi` freezes that clock:
  // every event-driven animation (flash decay, signals, stitches, births)
  // stops in place while the ambient rotation goes on. Thawing continues
  // from where it stopped — no jump.
  const animClock = { frozen: false, at: 0, offset: 0 };
  let animFrames = 0;      // frames in which the event clock advanced
  let plan = [];           // { at, fn } — scheduled on the event clock
  let stitches = [];       // dotted edges between far nodes (dikis)
  let marks = [];          // success / failure glyphs beside a node
  let injections = [];     // prime injection: core → context window
  let litLog = [];         // ids in the order they were struck
  let nightDim = 0;        // 0..1 hippocampus darkening
  let thinUntil = 0;       // edges drawn thin until this event-clock time
  // Cold store: the ring around the hippocampus. `count` is the badge,
  // `warm` the sparks of nodes being opened, `slice` the region local
  // sleep is working on.
  let coldRing = { count: 0, warm: [], slice: null, hover: false, badge: null };
  let onCold = () => {};

  const WARM_MS = 1400;    // cold node: ring → engram
  const STITCH_MS = 4200;  // a dotted stitch stays visible
  const PULL_MS = 1100;    // distillation: sources drawn together
  const BIRTH_MS = 900;    // a distilled node grows in
  const MARK_MS = 2600;    // ✓ / ✕ beside a node
  const INJECT_MS = 1500;  // core → context window flow
  const EDGE_MS = 1200;    // a night-born edge appears
  const THIN_MS = 900;     // "all edges thin for a moment"

  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue("--" + n).trim();

  // The scene was tuned for near-black: bright tint + low alpha is a star
  // on a dark ground and vanishes ON WHITE. In light mode we draw with the
  // CSS ink (already darkened for paper), not by dimming the neon.
  const isLight = () => document.documentElement.dataset.theme === "light";
  const now = () => performance.now();

  function hexRgb(hex) {
    const m = /^#([0-9a-f]{6})$/i.exec((hex || "").trim());
    if (!m) return null;
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  // Mode colour on paper: idle cyan, thinking violet, work amber — from
  // the tokens.
  function paperInk() {
    const key = {
      waking: "session", idle: "cyan", thinking: "violet",
      writing: "mint", recalling: "ice", working: "amber"
    }[mode] || "cyan";
    return hexRgb(css(key)) || [180, 112, 10];
  }

  // The floor for faint alpha on paper: 0.2 × colour is invisible on a
  // light ground.
  function paperAlpha(a) {
    return isLight() ? Math.min(1, a * 2.6 + 0.2) : a;
  }

  // A stable 0..1 number from a string. FNV-1a: the same id + the same
  // salt always gives the same result. Memories' places in the brain are
  // derived from this — positions should look random but not drift
  // between launches.
  function hash01(str, salt) {
    let h = (2166136261 ^ (salt || 0)) >>> 0;
    for (let i = 0; i < str.length; i++) {
      h = Math.imul(h ^ str.charCodeAt(i), 16777619);
    }
    return (h >>> 0) / 4294967296;
  }

  let _inited = false;

  function init(opts) {
    // Double init = two rAF loops = a double brain in the middle (script
    // rebinding / hot path). A second call only refreshes the references.
    canvas = opts.canvas;
    ctx = canvas.getContext("2d");
    probe = opts.probe;
    revealBtn = opts.reveal;
    onRoute = opts.onRoute || onRoute;
    onSession = opts.onSession || onSession;

    if (_inited) {
      resize();
      start();
      return;
    }
    _inited = true;

    // ResizeObserver beats the window event: a box that was 0 while hidden
    // reports by itself once visible.
    const watch = new ResizeObserver(resize);
    watch.observe(canvas);
    // As the chat column narrows and widens (viewer opening, window
    // resizing) the core's centre shifts too.
    const aside = document.querySelector(".stream");
    if (aside) watch.observe(aside);
    // The brain panel changes height too (camera/orchestra deck): the
    // canvas size stays the same, so unless #mind is watched the rings
    // overflow the shrinking box.
    const mindEl = document.getElementById("mind");
    if (mindEl) watch.observe(mindEl);
    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("mousedown", onDown);
    // Double-click: goes to the conversation where the memory WAS BORN (on
    // a session node, to the conversation itself). Meaningless on organs
    // and branch hubs.
    canvas.addEventListener("dblclick", (ev) => {
      const hitNode = at(ev);
      const canGo = hitNode && !hitNode.organ && !hitNode.branchHub
        && (hitNode.group === "session" || hitNode.kaynak_var !== false);
      const target = canGo
        ? (hitNode.kaynak || (hitNode.group === "session" ? hitNode.id : null))
        : null;
      if (target) { probe.hidden = true; selected = null; onSession(target); }
    });

    // Stop drawing when the window is minimised: animating an invisible
    // scene is battery burnt for nothing in a program open all day.
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
    // An icon, not text. The state is told by class and tooltip.
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
    if (!w || !h) return;            // still hidden: wait for the next report

    const ratio = window.devicePixelRatio || 1;
    view = { w, h };
    canvas.width = Math.round(w * ratio);
    canvas.height = Math.round(h * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    layout();
  }

  // --- layout ---------------------------------------------------------
  //
  // The scene centres on the **free area**, not the window. With the chat
  // a column on the right and the core dead-centre in the window, it sat
  // under the text: the flow of thought — the thing to watch — was
  // invisible.
  //
  // The column's width lives in CSS and varies with the window, so it is
  // not assumed here — it is measured.
  const NARROW = 380;   // with less free area, the column layout is pointless

  let freeLeft = 0;   // LEFT edge of the free area (right of the rail column, if any)

  function freeWidth() {
    const aside = document.querySelector(".stream");
    const rect = aside ? aside.getBoundingClientRect() : null;
    freeLeft = 0;
    if (!rect || !rect.width) return view.w;
    // With the left rail in column mode, the free area starts to its
    // RIGHT: the core used to centre behind the panel and disappear.
    const rail = document.getElementById("hist-panel");
    if (rail && !rail.hidden) {
      const rr = rail.getBoundingClientRect();
      if (rr.width && rr.left <= 1 && rr.right < rect.left) freeLeft = rr.right;
    }
    // The area to the left of the column. In a narrow window the text sits
    // over the scene anyway; the core stays centred there.
    const usable = rect.left - freeLeft;
    if (usable > NARROW) return usable;
    freeLeft = 0;
    return view.w;
  }

  // Chat at the side or at the bottom. Which side the scene leaves free
  // depends on this, and the organs line up there.
  const sideways = () => freeWidth() < view.w;

  // The right brain panel: if present, the core sits inside it. The rect
  // is measured fresh — the panel can open, close and grow by grip.
  function mindRect() {
    const m = document.getElementById("mind");
    if (!m) return null;
    const r = m.getBoundingClientRect();
    return r.width > 150 && r.height > 220 ? r : null;
  }

  // The header and the EXPLANATION are HTML; organ rows are on the
  // canvas, below the rings. The hole is header-to-foot only: subtracting
  // the organ share here left the brain a tiny stamp in the middle (space
  // reserved, rows still drawn at the ring's foot — bottom empty, graphic
  // small).
  function mindHole(box) {
    const mind = document.getElementById("mind");
    const head = mind && mind.querySelector(".mind-head");
    const foot = mind && mind.querySelector(".mind-foot");
    // The region strips (prefrontal above, thalamus & co. below) are HTML
    // and push the brain between them, like the header and the foot.
    const strip = (sel) => {
      const el = mind && mind.querySelector(sel);
      if (!el || el.hidden) return null;
      const r = el.getBoundingClientRect();
      return r.height > 0 ? r : null;
    };
    const topStrip = strip(".regions-top");
    // Below: the simple status block sits above the details strip; whichever
    // is drawn first (from the top) bounds the brain.
    const bottomStrip = strip(".brain-simple") || strip(".regions-bottom");
    const headB = topStrip ? topStrip.bottom
      : head ? head.getBoundingClientRect().bottom : box.top;
    const footT = bottomStrip ? bottomStrip.top
      : foot ? foot.getBoundingClientRect().top : box.bottom;
    const PAD = 8;
    const left = box.left + PAD;
    const right = box.right - PAD;
    const top = Math.max(box.top + PAD, headB + 6);
    const bottom = Math.min(box.bottom, footT) - PAD;
    return {
      left, right, top,
      bottom: Math.max(top + 36, bottom),
      clipTop: headB,
      clipBottom: footT,
    };
  }

  function rForReach(limit) {
    const byRing = limit / RING_OUTER;
    const byTick = limit > TICK_OUT ? (limit - TICK_OUT) / TICK_SCALE : byRing;
    return Math.max(4, Math.min(byRing, byTick));
  }

  function layout() {
    pane = mindRect();
    hole = null;
    if (pane) {
      // Fill the width, hang under the header. In a tall panel vertical
      // centring shrank the rings to a stamp; the 96 cap starved a wide
      // panel too.
      hole = mindHole(pane);
      const hw = (hole.right - hole.left) / 2;
      const nBr = BRANCHES.filter((b) => limbs.some((l) => branchOf(l) === b)).length;
      const below = (nBr ? nBr * 22 + 20 : 24) + (legendOn ? 72 : 0);
      const availH = hole.bottom - hole.top;
      const reachCap = Math.max(8, Math.min(hw, (availH - below) / 2));
      core.r = rForReach(reachCap);
      const reach = ringReach(core.r);
      core.x = (hole.left + hole.right) / 2;
      core.y = hole.top + reach;
    } else {
    const free = freeWidth();
    core.x = freeLeft + free / 2;
    // With the chat at the bottom the core is pulled up: centred, it ends
    // up under the text and the thing to watch is invisible.
    core.y = view.h * (free < view.w ? 0.46 : 0.42);
    core.r = Math.min(free * 0.11, view.h * 0.17, 150);
    }

    // Memories are no longer a flat 2D scatter but INSIDE the VOLUME of
    // the rotating brain. Each node gets a fixed 3D position derived from
    // its id (like an engram — the same memory always in the same place)
    // and its screen position is computed each frame through the same
    // rotation as the brain. So memories rotate with the brain, sitting
    // inside it.
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
    // Synapse links: what makes the web a web. Hierarchy edges are not
    // here.
    web = (data.edges || [])
      .filter(e => e.synapse && byId.has(e.source) && byId.has(e.target))
      .map(e => ({ a: byId.get(e.source), b: byId.get(e.target), weight: e.weight || 1 }));

    layout();
    if (selected) { selected = byId.get(selected.id) || null; if (!selected) probe.hidden = true; }
    if (then) then();
  }

  // --- recall trace ---------------------------------------------------
  // The nodes the agent actually visited, in the order it visited them.
  // Steps unfold one by one and the path stays on screen: so it can be
  // followed on the map.
  //
  // Each step is now two events: first an impulse departs, then the node
  // it reaches fires. When only the firing was shown, lights blinked in
  // sequence across the web; where things went from and to was invisible.
  //
  // Returns the total duration: the caller should know how long the scene
  // stays in recall mode, not guess the number.
  function activate(trace) {
    clearRoute();
    // The agent is recalling: whatever the night left frozen on screen
    // gives way to the day.
    thaw();
    if (!Array.isArray(trace) || !trace.length) { ripple(); return 0; }

    // Trace nodes MISSING from the graph must not kill the animation: the
    // graph draws the newest 24 records per bucket; when recall reached an
    // old record the node was not on screen, the trace filtered to nothing
    // and the electric walk NEVER showed (live wound, 31.08 — "the
    // animations are gone"). An unknown id gets a ghost node with a
    // persistent position: the same memory always lights in the same
    // place; the next graph load sweeps the ghost away.
    // A record not in the graph came from the cold store (FTS reach, not
    // spontaneous): it warms in from the ring rather than appearing from
    // nowhere.
    for (const step of trace) {
      if (!step || !step.node || byId.has(step.node)) continue;
      warm(step.node, step.label || "anı", step.kind);
    }
    place();

    // The trace carries only ids; we add the label for a readable list.
    route = trace
      .filter(step => byId.has(step.node))
      .map(step => ({ ...step, label: step.label || byId.get(step.node).label }));

    // Numbers go only to the ones actually used. Numbering every scanned
    // record gave the impression the mind had read them all — on "add a
    // modbus device" five records lit at once and two were the BTC price.
    // If none are marked (old records) all count as used.
    const marked = route.some(step => step.used);
    route.forEach(step => { step.used = marked ? !!step.used : true; });
    focused = -1;
    ripple();

    // SIGNALS FLY ONLY TO THE USED ONES. Drawing flights to the scanned-
    // and-dropped too gave the impression "light hops around at random" —
    // whereas the walk is the chain of records ACTUALLY put before the
    // model. The merely-looked-at get no flight, marked together with one
    // soft glow: touched, but not taken.
    const walked = route.filter(step => step.used);
    route.forEach(step => {
      if (!step.used) setTimeout(() => strike(step.node, 0, null), 140);
    });

    walked.forEach((step, i) => {
      // Where the impulse comes from: the node that relayed the activation
      // (it too must be used), else the previous used node in the chain,
      // else the core — that is, the question.
      const viaUsed = step.via && step.via !== "query" && byId.has(step.via)
        && walked.some(w => w.node === step.via);
      const via = viaUsed ? step.via : (i > 0 ? walked[i - 1].node : null);

      signal(via, step.node, via ? "weigh" : "ask", i * STEP_MS);
      setTimeout(() => {
        strike(step.node, i + 1, via);
        onRoute(route, route.indexOf(step));   // let the list fill step by step
      }, i * STEP_MS + SIGNAL_MS);
    });

    // The find is carried back: an impulse returning to the core from the
    // last USED stop.
    const last = walked[walked.length - 1];
    const walk = Math.max(0, walked.length - 1) * STEP_MS + SIGNAL_MS;
    if (last) signal(last.node, null, "recall", walk);
    if (!walked.length) onRoute(route, route.length - 1);   // if all were merely looked at, the list still arrives
    return walk + SIGNAL_MS;
  }

  // The order among the used ones. Scanned-and-dropped records do not
  // advance the count: expecting a list that goes "1, 2, 3" and seeing
  // "2, 5, 7" does not read.
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

  // Clicking a step in the list brings that node forward.
  function focusStep(index) {
    focused = index;
    const step = route[index];
    if (step) {
      const node = byId.get(step.node);
      if (node) { node.flash = 1; node.peak = 1; node.lit = tick(); showProbeAt(node); }
    }
    start();
  }

  function ripple() { ripples.push({ born: tick() }); start(); }

  // A link the agent forged deliberately. What separates it from the
  // automatic weave is visibility: the web growing by itself is silent,
  // the agent building a bridge is an event.
  function bridge(src, dst) {
    const from = byId.get(src);
    const to = byId.get(dst);
    if (!from || !to) return;
    bridges.push({ from, to, born: tick() });
    // While the link is drawn an impulse crosses it: what was forged
    // should be seen to carry a direction.
    signal(src, dst, "link");
    from.flash = 1; from.peak = 1; from.lit = tick();
    to.flash = 1; to.peak = 1; to.lit = tick();
    start();
  }

  function drawBridges(t) {
    t = anim(t);
    // Faded ones drop off the list; else they pile up over a long session.
    bridges = bridges.filter((b) => t - b.born < BRIDGE_MS);
    for (const b of bridges) {
      const k = (t - b.born) / BRIDGE_MS;
      // The line is drawn from source to target: show the link's direction.
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

  // The mode's counterpart written under the core. The colour comes from
  // the mode's own tint (thinking purple, working amber…); the text says
  // what it is doing right now. Without a specific action given (like a
  // tool call), the mode's default word is used.
  const MODE_TEXT = {
    waking: "Uyanıyor", idle: "", thinking: "Düşünüyor",
    writing: "Yazıyor", recalling: "Hatırlıyor", working: "Çalışıyor",
  };
  let statusLabel = "";

  function setMode(name, label) {
    mode = MODES[name] ? name : "idle";
    // Action label: show it if given, else the mode's word.
    statusLabel = label !== undefined ? label : (t(MODE_TEXT[mode]) || "");
    start();   // may have been stopped while hidden
  }

  // The old call surface: the busy/idle pair still works.
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

  // Returns the current colour at the given opacity.
  const tint = (alpha) => {
    const c = isLight() ? paperInk() : look.tint;
    return "rgba(" + c.map(Math.round).join(",") + "," + alpha + ")";
  };

  // --- signals ---------------------------------------------------------
  //
  // Recalling, writing and weighing appear here as **motion**: an impulse
  // walking from one end to the other. The previous version lit nodes in
  // sequence and the journey in between never showed — where something
  // flowed from and to could not be read, only the result blinked.
  //
  // The speed is deliberately low. A real signal passes in milliseconds,
  // but that cannot be watched, and being watched is the whole point here.
  const SIGNAL_MS = 1000;   // duration of one hop — the signal to a memory must be watchable
  const TAIL = 0.3;         // the tail's share of the path
  const BOW = 0.15;         // the path's bow share: a straight line looks like cable
  const DOTS = 18;          // number of dots forming the tail

  // What the signal carries is read from its colour.
  const CURRENT = {
    ask:    "cyan",         // core to web: a question
    weigh:  "violet",       // node to node: association, weighing
    recall: "ice",          // web to core: the find coming back
    write:  "mint",         // core to web: writing
    link:   "preference",   // a deliberately forged bridge
    limb:   "fact",         // core to a device: organ use
    // Night (Phase 6). Colour is never the only carrier: forward replay
    // draws solid dots with an arrowhead, reverse replay hollow dots with
    // the arrow pointing back; success / failure also get a glyph.
    forward:  "user",       // tekrar.ileri: the session's chain, in order
    success:  "mint",       // tekrar.geri, outcome good
    failure:  "rose",       // tekrar.geri, outcome bad
    evidence: "violet"      // identity sentence → its evidence nodes
  };

  let signals = [];

  // Endpoint: `null` means the core. The position is re-resolved every
  // frame so a window resize does not leave the signal hanging mid-air.
  function spot(id) {
    if (!id || id === "self" || id === "core") return { x: core.x, y: core.y };
    const node = byId.get(id);
    if (node) return { x: node.x, y: node.y };
    // Organs can be targets too: an impulse heading to a device.
    const limb = limbs.find(l => l.id === id);
    return limb ? { x: limb.x, y: limb.y } : null;
  }

  // `dur` scales one hop (replay speed); `style` carries the direction
  // arrow and the hollow-dot shape of a reverse replay.
  function signal(from, to, kind, delay, dur, style) {
    signals.push({ from, to, kind: kind || "ask", born: tick() + (delay || 0),
                   dur: dur || SIGNAL_MS, style: style || null });
    start();
  }

  // The path is not straight: the midpoint of the two ends is pushed away
  // from the core. A straight line looked like cable; the bow looks like
  // an axon. The direction comes from the endpoints' positions, not
  // random — else it would switch sides every frame.
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
    t = anim(t);
    // Faded ones drop off the list; else they pile up over a long session.
    signals = signals.filter(sig => t - sig.born < sig.dur * (1 + TAIL));

    for (const sig of signals) {
      if (t < sig.born) continue;              // delayed: not yet departed
      const a = spot(sig.from), b = spot(sig.to);
      if (!a || !b) continue;

      const head = (t - sig.born) / sig.dur;
      const c = curve(a, b);
      const color = css(CURRENT[sig.kind] || "cyan");
      // After the head arrives, the tail keeps flowing in.
      const left = head > 1 ? Math.max(0, 1 - (head - 1) / TAIL) : 1;
      const hollow = !!(sig.style && sig.style.hollow);

      ctx.shadowColor = color;
      ctx.fillStyle = color;
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.2;
      for (let i = 0; i < DOTS; i++) {
        const k = head - (i / DOTS) * TAIL;
        if (k < 0 || k > 1) continue;
        const p = bezier(a, c, b, k);
        const fade = (1 - i / DOTS) * left;
        ctx.globalAlpha = Math.min(1, fade * 1.05);
        ctx.shadowBlur = 20 * fade;
        ctx.beginPath();
        // The head bigger and brighter: the signal's walk toward the
        // memory should be easy to follow by eye (user request).
        ctx.arc(p.x, p.y, 0.9 + fade * 3.3, 0, Math.PI * 2);
        if (hollow) ctx.stroke(); else ctx.fill();
      }
      // Direction arrow at the head: which way the replay walks must be
      // readable without colour.
      if (sig.style && sig.style.arrow && head > 0.04 && head <= 1) {
        const p = bezier(a, c, b, head);
        const q = bezier(a, c, b, Math.max(0, head - 0.04));
        const ang = Math.atan2(p.y - q.y, p.x - q.x);
        ctx.globalAlpha = Math.min(1, left);
        ctx.shadowBlur = 0;
        ctx.beginPath();
        ctx.moveTo(p.x + Math.cos(ang) * 7, p.y + Math.sin(ang) * 7);
        ctx.lineTo(p.x + Math.cos(ang + 2.5) * 6, p.y + Math.sin(ang + 2.5) * 6);
        ctx.lineTo(p.x + Math.cos(ang - 2.5) * 6, p.y + Math.sin(ang - 2.5) * 6);
        ctx.closePath();
        if (hollow) ctx.stroke(); else ctx.fill();
      }
    }
    ctx.globalAlpha = 1; ctx.shadowBlur = 0;
  }

  // A node fired: let it flash and carry its order and where it came
  // from.
  function strike(id, order, from, level) {
    const node = byId.get(id);
    if (!node) return null;
    node.flash = level === undefined ? 1 : Math.max(0.05, Math.min(1, level));
    node.peak = node.flash;
    node.lit = tick();
    if (order) node.order = order;
    if (from !== undefined) node.from = from;
    litLog.push(id);
    start();
    return node;
  }

  // --- night layer (Phase 6) --------------------------------------------
  //
  // Everything below is driven by the frozen event schema
  // (recall/night_events.py) through night.js; the view never reads
  // recall.db. The drawing reuses signal() / strike() so a night replay
  // and a day recall have the same order and timing logic (STEP_MS,
  // SIGNAL_MS), only scaled by the replay speed.

  // The event clock. tick() stamps births; anim(t) maps a real frame time
  // onto it. Frozen: the clock stands, every stamp-relative animation
  // stands with it.
  function anim(t) {
    return animClock.frozen ? animClock.at : t - animClock.offset;
  }
  const tick = () => anim(performance.now());
  function freeze() {
    if (animClock.frozen) return;
    animClock.at = anim(performance.now());
    animClock.frozen = true;
  }
  function thaw() {
    if (!animClock.frozen) return;
    animClock.offset = performance.now() - animClock.at;
    animClock.frozen = false;
    start();
  }
  const frozen = () => animClock.frozen;

  // Scheduling on the event clock instead of setTimeout: a frozen clock
  // must hold the queued steps too, else the remaining chain lights up
  // behind a stopped picture.
  function schedule(delay, fn) {
    plan.push({ at: tick() + Math.max(0, delay || 0), fn });
    start();
  }
  function runPlan(ta) {
    if (!plan.length) return;
    const due = plan.filter((p) => p.at <= ta).sort((a, b) => a.at - b.at);
    if (!due.length) return;
    plan = plan.filter((p) => p.at > ta);
    for (const p of due) { try { p.fn(); } catch (err) { console.error(err); } }
  }

  // A node the graph does not carry (cold, old, or born tonight) gets a
  // persistent ghost: the same id always lands on the same engram, and the
  // next graph load sweeps it away.
  function ensureNode(id, label, kind) {
    const known = byId.get(id);
    if (known) return known;
    const ghost = {
      id, label: String(label || id), group: kind || "fact",
      size: 7, detail: "", ghost: true,
      flash: 0, lit: 0, order: 0, from: null,
    };
    ghost.p3 = insideBrain(ghost.id);
    nodes.push(ghost);
    byId.set(ghost.id, ghost);
    return ghost;
  }

  // A cold node opened: it starts on the ring and warms toward its place
  // in the hippocampus. The ring itself shows the spark (drawColdRing).
  function warm(id, label, kind) {
    const known = byId.has(id);
    const node = ensureNode(id, label, kind);
    if (!known) {
      const ang = hash01(id, 0xc01d) * Math.PI * 2;
      node.p3out = { x: Math.cos(ang) * 1.9, y: (hash01(id, 0xc02d) - 0.5) * 0.4,
                     z: Math.sin(ang) * 1.9 };
      node.warm = tick();
      coldRing.warm.push({ id, born: node.warm, ang });
    }
    node.flash = 1; node.peak = 1; node.lit = tick();
    start();
    return node;
  }

  // A chain of nodes lit one after another — the night's replay. Options:
  //   reverse   walk the chain backwards (tekrar.geri)
  //   kind      signal colour key (forward / success / failure / evidence)
  //   shares    id → 0..1, brightness of each strike (paylar)
  //   speed     1 / 10 / 60 — divides STEP_MS and SIGNAL_MS
  //   glyph     "✓" / "✕" drawn beside the last node
  //   labels    id → label for ghosts
  // Returns the total duration in event-clock ms.
  function lightSequence(ids, opts) {
    opts = opts || {};
    const speed = Math.max(0.1, opts.speed || 1);
    const step = STEP_MS / speed, hop = SIGNAL_MS / speed;
    const order = (opts.reverse ? [...ids].reverse() : [...ids]).filter(Boolean);
    if (!order.length) return 0;
    const kind = opts.kind || "forward";
    const style = { arrow: true, hollow: !!opts.reverse };
    order.forEach((id, i) => {
      ensureNode(id, opts.labels && opts.labels[id], opts.group);
      const prev = i > 0 ? order[i - 1] : null;
      const share = opts.shares && opts.shares[id] !== undefined
        ? Math.max(0, Math.min(1, Number(opts.shares[id]) || 0)) : 1;
      if (prev) signal(prev, id, kind, i * step, hop, style);
      schedule(i * step + (prev ? hop : 0), () => {
        strike(id, opts.numbered ? i + 1 : 0, prev, 0.4 + 0.6 * share);
      });
    });
    const total = (order.length - 1) * step + hop;
    if (opts.glyph) {
      schedule(total, () => mark(order[order.length - 1], opts.glyph, kind));
    }
    return total;
  }

  // dikis: a dotted edge between two far nodes; the node in between
  // flashes once.
  // Every night strike goes through schedule(): the plan runs in `at`
  // order inside the scene's frame, so two events played back to back
  // light their nodes in the order of the file, whichever rAF callback
  // (night.js or the scene) happens to run first.
  function stitch(a, b, via) {
    ensureNode(a); ensureNode(b);
    schedule(0, () => {
      stitches.push({ a, b, born: tick() });
      if (via) { ensureNode(via); strike(via, 0, null, 1); }
    });
  }

  // dokunus: a far, faint node blinks softly.
  function touch(id) {
    ensureNode(id);
    schedule(0, () => strike(id, 0, null, 0.55));
  }

  // damitma: the sources are drawn together; from between them a new node
  // is born (REM). `speed` scales the pull like the replay steps.
  function distil(sources, newId, label, speed) {
    const dur = PULL_MS / Math.max(0.1, speed || 1);
    const src = (sources || []).map((id) => ensureNode(id));
    if (!src.length) { ensureNode(newId, label); schedule(0, () => strike(newId)); return dur; }
    const c = { x: 0, y: 0, z: 0 };
    for (const n of src) { c.x += n.p3.x; c.y += n.p3.y; c.z += n.p3.z; }
    c.x /= src.length; c.y /= src.length; c.z /= src.length;
    schedule(0, () => {
      const born = tick();
      for (const n of src) {
        n.pull = { to: c, born, dur }; n.flash = 0.7; n.peak = 0.7; n.lit = born; litLog.push(n.id);
      }
    });
    schedule(dur, () => {
      const fresh = !byId.has(newId);
      const n = ensureNode(newId, label, "lesson");
      if (fresh) n.p3 = { x: c.x + (hash01(newId, 7) - 0.5) * 0.06,
                          y: c.y + (hash01(newId, 8) - 0.5) * 0.06,
                          z: c.z + (hash01(newId, 9) - 0.5) * 0.06 };
      n.born = tick();
      strike(newId);
      for (const s of src) signal(s.id, newId, "write", 0, Math.max(60, SIGNAL_MS * 0.6 / Math.max(0.1, speed || 1)));
    });
    return dur + BIRTH_MS / Math.max(0.1, speed || 1);
  }

  // A glyph beside a node: ✓ success, ✕ failure. The colour says it too,
  // but never alone.
  function mark(id, glyph, kind) {
    if (!byId.has(id)) return;
    marks.push({ id, glyph, kind: kind || "success", born: tick() });
    start();
  }

  // An edge the night wove: it appears growing from a to b and then stays
  // as part of the web until the next graph load.
  function addEdge(a, b, weight) {
    const na = ensureNode(a), nb = ensureNode(b);
    if (web.some((e) => (e.a === na && e.b === nb) || (e.a === nb && e.b === na))) return;
    web.push({ a: na, b: nb, weight: weight || 1, born: tick() });
    start();
  }

  // "All edges thin for a moment" — the local shrink at the end of a
  // regional sleep.
  function thinEdges() { thinUntil = tick() + THIN_MS; start(); }

  // Hippocampus darkening: 1 asleep, 0 awake, ~0.4 a nap.
  function dim(level) { nightDim = Math.max(0, Math.min(1, Number(level) || 0)); start(); }

  // Prime injection: the recalled records flow from the core into the
  // context window — drawn toward the chat column.
  function inject(ids) {
    injections.push({ born: tick(), n: Array.isArray(ids) ? ids.length : 1 });
    start();
  }

  // Cold store ring: the badge count and the slice local sleep works on.
  function cold(count) { coldRing.count = Math.max(0, Number(count) || 0); start(); }
  function coldSlice(name) { coldRing.slice = name ? { name: String(name), born: tick() } : null; start(); }
  function onColdRing(cb) { onCold = typeof cb === "function" ? cb : () => {}; }

  // Radius of the cold ring: just outside the HUD rings, so the two never
  // read as one.
  const coldRadius = () => ringReach(core.r) + 10;

  function drawStitches(t) {
    const ta = anim(t);
    stitches = stitches.filter((s) => ta - s.born < STITCH_MS);
    if (!stitches.length) return;
    ctx.save();
    ctx.setLineDash([2, 5]);
    for (const s of stitches) {
      const a = byId.get(s.a), b = byId.get(s.b);
      if (!a || !b) continue;
      const k = (ta - s.born) / STITCH_MS;
      const grow = Math.min(1, k * 4);
      ctx.strokeStyle = css("lesson");
      ctx.globalAlpha = 0.85 * (1 - Math.max(0, k - 0.6) / 0.4);
      ctx.lineWidth = 1.3;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(a.x + (b.x - a.x) * grow, a.y + (b.y - a.y) * grow);
      ctx.stroke();
    }
    ctx.restore();
    ctx.globalAlpha = 1;
  }

  function drawMarks(t) {
    const ta = anim(t);
    marks = marks.filter((m) => ta - m.born < MARK_MS);
    if (!marks.length) return;
    const family = getComputedStyle(document.body).fontFamily;
    ctx.save();
    ctx.font = "700 12px " + family;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    for (const m of marks) {
      const node = byId.get(m.id);
      if (!node) continue;
      const k = (ta - m.born) / MARK_MS;
      const color = css(CURRENT[m.kind] || "ice");
      ctx.globalAlpha = k < 0.7 ? 1 : 1 - (k - 0.7) / 0.3;
      ctx.fillStyle = color;
      ctx.shadowColor = color; ctx.shadowBlur = isLight() ? 0 : 10;
      ctx.fillText(m.glyph, node.x + 11, node.y - 11 - k * 6);
    }
    ctx.restore();
    ctx.globalAlpha = 1; ctx.shadowBlur = 0;
  }

  // The flow from the core toward the context window. The chat column is
  // the window; the nearest edge of it is the target.
  function drawInjections(t) {
    const ta = anim(t);
    injections = injections.filter((j) => ta - j.born < INJECT_MS);
    if (!injections.length) return;
    const chat = document.querySelector(".stream");
    const rect = chat ? chat.getBoundingClientRect() : null;
    if (!rect || !rect.width) return;
    const target = {
      x: Math.max(rect.left, Math.min(rect.right, core.x)),
      y: Math.max(rect.top, Math.min(rect.bottom, core.y)),
    };
    if (target.x === core.x && target.y === core.y) target.x = rect.left;
    const from = { x: core.x, y: core.y };
    const c = curve(from, target);
    const color = css("ice");
    ctx.save();
    ctx.fillStyle = color; ctx.shadowColor = color;
    for (const j of injections) {
      const head = (ta - j.born) / INJECT_MS;
      const lanes = Math.min(5, Math.max(1, j.n));
      for (let l = 0; l < lanes; l++) {
        for (let i = 0; i < 10; i++) {
          const k = head * 1.3 - i * 0.04 - l * 0.05;
          if (k < 0 || k > 1) continue;
          const p = bezier(from, c, target, k);
          const fade = (1 - i / 10) * (1 - Math.max(0, head - 0.7) / 0.3);
          ctx.globalAlpha = Math.max(0, fade * 0.9);
          ctx.shadowBlur = 12 * fade;
          ctx.beginPath();
          ctx.arc(p.x + (l - lanes / 2) * 3, p.y + (l - lanes / 2) * 3, 1 + fade * 2, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
    ctx.restore();
    ctx.globalAlpha = 1; ctx.shadowBlur = 0;
  }

  // The cold store: a faint dashed ring around the hippocampus with the
  // count badge. Sparks run inward while a cold node is opened; a slice
  // pulses while local sleep works on a region. Drawn only where the
  // brain is the front surface (panel) or the web is revealed.
  function drawColdRing(t) {
    const ta = anim(t);
    if (!pane && !reveal) { coldRing.badge = null; return; }
    const R = coldRadius();
    const light = isLight();
    const ink = light ? css("text") : css("dim");
    ctx.save();
    ctx.setLineDash([3, 7]);
    ctx.strokeStyle = ink;
    ctx.lineWidth = coldRing.hover ? 1.6 : 1;
    ctx.globalAlpha = (coldRing.hover ? 0.55 : 0.28) * (1 - nightDim * 0.5);
    ctx.beginPath(); ctx.arc(core.x, core.y, R, 0, Math.PI * 2); ctx.stroke();
    ctx.setLineDash([]);

    // Local sleep: one slice of the ring in the sleep pattern.
    if (coldRing.slice) {
      const a0 = hash01(coldRing.slice.name, 0x5e1) * Math.PI * 2;
      const pulse = 0.45 + 0.35 * (Math.sin(t / 700) + 1) / 2;
      ctx.strokeStyle = css("user");
      ctx.globalAlpha = pulse;
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(core.x, core.y, R, a0, a0 + Math.PI / 3); ctx.stroke();
    }

    // Sparks: ring → centre.
    coldRing.warm = coldRing.warm.filter((w) => ta - w.born < WARM_MS);
    ctx.fillStyle = css("cyan"); ctx.shadowColor = css("cyan"); ctx.strokeStyle = css("cyan");
    ctx.lineWidth = 1;
    for (const w of coldRing.warm) {
      const k = (ta - w.born) / WARM_MS;
      const node = byId.get(w.id);
      const tx = node ? node.x : core.x, ty = node ? node.y : core.y;
      const sx = core.x + Math.cos(w.ang) * R, sy = core.y + Math.sin(w.ang) * R;
      const e = 1 - Math.pow(1 - k, 3);
      ctx.globalAlpha = 0.9 * (1 - k * 0.6);
      ctx.shadowBlur = light ? 0 : 14;
      ctx.beginPath();
      ctx.arc(sx + (tx - sx) * e, sy + (ty - sy) * e, 3.2 - k * 1.5, 0, Math.PI * 2);
      ctx.fill();
      // The ring glows where the spark left it.
      ctx.globalAlpha = 0.6 * (1 - k);
      ctx.beginPath(); ctx.arc(sx, sy, 5 + k * 10, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.shadowBlur = 0;

    // Badge: "41.200 soğuk", lower right of the ring.
    if (coldRing.count > 0) {
      const family = getComputedStyle(document.body).fontFamily;
      ctx.font = "600 10px " + family;
      ctx.textAlign = "left"; ctx.textBaseline = "middle";
      ctx.globalAlpha = coldRing.hover ? 0.95 : 0.7;
      ctx.fillStyle = ink;
      const text = coldRing.count.toLocaleString("tr-TR") + " " + t_("soğuk");
      const bx = core.x + R * Math.cos(Math.PI / 4) + 4;
      const by = core.y + R * Math.sin(Math.PI / 4) + 4;
      ctx.fillText(text, bx, by);
      coldRing.badge = { x: bx, y: by, w: ctx.measureText(text).width };
    } else coldRing.badge = null;
    ctx.restore();
    ctx.globalAlpha = 1;
  }
  // t() is the translation function of lang.js; a local alias keeps the
  // frame time `t` readable in the drawing code above.
  const t_ = (s) => (typeof t === "function" ? t(s) : s);

  // Hover on the ring (no node under the pointer): the region tooltip.
  function coldHit(ev) {
    if (!pane && !reveal) return false;
    const d = Math.hypot(ev.clientX - core.x, ev.clientY - core.y);
    if (Math.abs(d - coldRadius()) <= 9) return true;
    const b = coldRing.badge;
    return !!(b && ev.clientX >= b.x - 4 && ev.clientX <= b.x + b.w + 4
              && Math.abs(ev.clientY - b.y) <= 9);
  }

  // What the region overlay needs to place itself around the brain.
  function geometry() {
    return { x: core.x, y: core.y, r: core.r, reach: ringReach(core.r),
             cold: coldRadius(), pane: !!pane, hole, dim: nightDim };
  }
  const litLogRead = () => litLog.slice();
  const clearLog = () => { litLog = []; };
  const frames = () => animFrames;

  // Writing: an impulse from the core into the web with the new record at
  // its tip. Called after the graph refreshes, else the target node does
  // not exist yet.
  function deposit(id) {
    if (!byId.has(id)) { ripple(); return; }
    signal(null, id, "write");
    setTimeout(() => strike(id), SIGNAL_MS);
  }

  // --- organs ----------------------------------------------------------
  //
  // The web shows what the agent knows; this layer what it can do:
  // microphone, cameras, speaker and the modules it wrote for itself
  // (map, PLC, USB — whatever it wrote).
  //
  // They sit faint by default. Making a memory and a camera the same node
  // left "what is it using right now" unanswered; as a separate ring the
  // answer reads at a glance.
  //
  // While in use, an impulse flows between it and the core and the organ
  // pulses. Hovering shows what it is doing at that moment.
  // Colour separates the type. `lesson` and `amber` are the same yellow:
  // device and skill could not be told apart on screen and the shape
  // difference alone was not enough.
  //
  //   blue    senses   — the machine's own organs
  //   yellow  devices  — physical things attached from outside
  //   purple  skills   — scripts the agent wrote itself
  const LIMB_COLOR = { sense: "fact", speech: "fact", module: "violet",
                       device: "amber" };

  // Branches. Organs used to be straight lines to the core, all leaving
  // from the same spot: the microphone and a script the agent wrote could
  // not be told apart. Now there are three branches and each organ hangs
  // from its own — the physical and the software separate at a glance.
  //
  //   duyular     the machine's own organs: microphone, camera, speaker
  //   cihazlar    attached from outside: PLC, remote camera, serial port
  //   yetenekler  scripts the agent wrote for itself
  const BRANCHES = [
    { id: "duyular", label: "Duyular", kinds: ["sense", "speech"], tone: "fact" },
    { id: "cihazlar", label: "Cihazlar", kinds: ["device"], tone: "amber" },
    { id: "yetenekler", label: "Yetenekler", kinds: ["module"], tone: "violet" },
  ];

  // The branch's distance from the core and the leaves' from the branch.
  const BRANCH_AT = 0.58;   // how far along the path it branches
  const LEAF_GAP = 0.34;    // angle between leaves

  // Shape separates the type. With everything a hexagon, a script the
  // agent wrote itself looked the same as the microphone on the desk.
  //
  //   hexagon  the machine's own sense — microphone, camera, speaker
  //   square   an externally attached device — PLC, remote camera, serial
  //   diamond  a skill the agent wrote itself: software, not hardware
  const LIMB_SIDES = { sense: 6, speech: 6, device: 4, module: 3 };
  const USE_MS = 1400;     // one cycle of the usage pulse
  const USE_HOLD = 6000;   // decay time of the usage trace
  const LIMB_DIM = 0.24;   // idle faintness

  let limbs = [];

  // Branches default CLOSED: five skills + three senses + devices in an
  // open fan filled the scene ("shoving it in our faces across huge
  // areas"). Closed, only the branch hub remains: "YETENEKLER · 5".
  // In the panel list two things open one: clicking the hub (persistent)
  // and an organ on the branch being in use right now. Hovering does not
  // open — rows are 21px apart, a hover-open shifted the ones below and
  // the mouse landed on another branch, fluttering open/closed. In the
  // fan (no panel) hover still opens temporarily: hubs stay put.
  const openBranches = new Set();
  const branchWake = {};   // branch id → opening moment (leaf fade-in)
  let hoverBranch = null;

  function organs(list) {
    const previous = new Map(limbs.map(l => [l.id, l]));
    limbs = (list || []).map(item => {
      const old = previous.get(item.id) || {};
      // What it is doing comes from usage, not the server: work in
      // progress must not vanish when the list refreshes.
      return { ...item, doing: old.doing || "", since: old.since || 0, organ: true };
    });
    // The branch count changes the hole's bottom share; refit the radius.
    layout();
    start();
  }

  // A row outside the memory belt, on the side the scene leaves free.
  //
  // The direction depends on where the chat is: with the column at the
  // side, the bottom is free and the organs descend there; with the
  // column at the bottom (narrow window) the bottom is full of text and
  // the organs go up. Picking a fixed arc meant labels sitting on the
  // welcome text in a narrow window.
  // Which organ belongs to which branch.
  const branchOf = (limb) =>
    BRANCHES.find((b) => b.kinds.includes(limb.kind)) || BRANCHES[0];

  let branches = [];

  // Panel mode: organs are a readable list under the brain, not a fan.
  // (The fan tangled into itself in a 340px column — "can't tell arm from
  // limb".) Row positions are laid out every frame in drawLimbRows
  // (branch open/close is live); only branch membership is built here.
  function placeRows() {
    const filled = BRANCHES.filter((b) => limbs.some((l) => branchOf(l) === b));
    branches = filled.map((meta) => ({
      ...meta,
      own: limbs.filter((l) => branchOf(l) === meta),
      below: true,
    }));
    for (const branch of branches) {
      for (const limb of branch.own) {
        limb.stem = branch;
        limb.below = true;
        if (limb.x === undefined) { limb.x = core.x; limb.y = core.y; }
      }
    }
  }

  function place() {
    if (!limbs.length) { branches = []; return; }
    if (pane) { placeRows(); return; }
    const free = freeWidth();
    const down = free < view.w ? 1 : -1;

    // The radius comes from the real free space, not a ratio. A fixed
    // ratio pushed the organs under the top strip in a narrow window:
    // hexagons off screen, labels never visible.
    //
    //   up    top strip (56) + label + body share
    //   down  bottom edge share
    const room = down > 0 ? view.h - core.y - 34 : core.y - 96;
    const radius = Math.min(free * 0.42, view.h * 0.34, Math.max(core.r * 2.4, room));

    // Spacing is fixed per organ, not divided over the arc: three organs
    // spanning the whole arc dropped two of them at the screen edges,
    // riding on the UI. It spreads as it crowds and stops when the arc is
    // full.
    const GAP = 0.3;
    const span = Math.min(Math.PI * 0.86, (limbs.length - 1) * GAP);

    // Only filled branches take space: drawing an empty "cihazlar" branch
    // would point at the place of something that does not exist.
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

    // Leaves fan out from the branch tip.
    for (const branch of branches) {
      const fan = Math.min(Math.PI * 0.5, (branch.own.length - 1) * LEAF_GAP) || 0;
      branch.own.forEach((limb, i) => {
        const t = branch.own.length === 1 ? 0.5 : i / (branch.own.length - 1);
        const angle = branch.angle - fan / 2 + t * fan;
        limb.angle = angle;
        limb.x = core.x + Math.cos(angle) * radius;
        limb.y = core.y + Math.sin(angle) * radius;
        limb.stem = branch;
        // The label on the organ's outer side: kept inside, it rides on
        // the core's bright rings.
        limb.below = down > 0;
      });
    }
  }

  // An organ is in use. `what` is the line read on hover.
  function use(id, what) {
    const limb = limbs.find(l => l.id === id);
    if (!limb) return;
    limb.doing = what || "";
    limb.since = now();
    // An impulse from the core to the device: something passing through
    // should be visible.
    signal(null, id, "limb");
    start();
  }

  function release(id) {
    const limb = limbs.find(l => l.id === id);
    if (limb) { limb.doing = ""; limb.since = 0; }
  }

  // The organ list in panel mode. Branch heading: coloured hub + arrow +
  // "DUYULAR · 3". An open branch's organs follow row by row; the organ IN
  // USE pulses, a spark descends from the core to its row (signal "limb")
  // and what it is doing is written next to its name — "what is it using
  // right now" reads at a glance.
  function drawLimbRows(t) {
    const family = getComputedStyle(document.body).fontFamily;
    const left = pane.left + 22;
    let y = core.y + ringReach(core.r) + 16;

    // The legend and the EXPLANATION sit at the panel's foot; the list
    // must not run into them. In a small window the COMPOSER rode on the
    // panel's foot and the row beneath it was unclickable ("pressing
    // senses doesn't open it" — live, 31.08): the ceiling is clamped to
    // the composer's top edge too.
    const kinds = new Set(nodes.map((n) => n.group)).size;
    const limbKinds = new Set(limbs.map((l) => branchOf(l).id)).size;
    const shell = document.querySelector(".compose-shell");
    const shellTop = shell ? shell.getBoundingClientRect().top - 10 : Infinity;
    const footTop = Math.min(hole ? hole.clipBottom : pane.bottom, shellTop);
    const maxY = legendOn
      ? footTop - (kinds + limbKinds + 1) * 19 - 12
      : footTop - 12;

    // Which branches are open: clicked, or in use right now. Hover does
    // not open (rows shift, hit circles overlap, open/close flutters).
    const expanded = new Set();
    for (const branch of branches) {
      const busy = branch.own.some((l) => l.since > 0 && t - l.since < USE_HOLD);
      if (openBranches.has(branch.id) || busy) {
        expanded.add(branch.id);
        if (!branchWake[branch.id]) branchWake[branch.id] = t;
      } else {
        delete branchWake[branch.id];
      }
    }

    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    for (const branch of branches) {
      const busy = branch.own.some((l) => l.since > 0 && t - l.since < USE_HOLD);
      const open = expanded.has(branch.id);
      const hovering = hoverBranch && hoverBranch.id === branch.id;
      const tone = css(branch.tone);
      branch.x = left; branch.y = y;
      branch.branchHub = true;
      // Row height 21px. A circle would swallow the neighbour: rect rows.
      branch._hit = y < maxY ? { x: left - 10, y, w: 220, h: 20 } : null;
      if (y > maxY) break;

      ctx.globalAlpha = paperAlpha(busy || hovering ? 0.95 : 0.55);
      ctx.fillStyle = tone;
      ctx.beginPath(); ctx.arc(left, y, 3.4, 0, Math.PI * 2); ctx.fill();
      ctx.font = "600 9.5px " + family;
      ctx.fillText(open ? "▾" : "▸", left + 9, y + 0.5);
      ctx.globalAlpha = paperAlpha(busy || hovering ? 0.95 : 0.6);
      ctx.fillText(Lang.t(branch.label).toUpperCase() + " · " + branch.own.length,
                   left + 20, y + 0.5);
      y += 21;

      if (!open) {
        // A closed branch's organ is not drawn; signals target the hub.
        for (const limb of branch.own) { limb._hit = null; limb.x = left; limb.y = branch.y; }
        continue;
      }

      const wake = Math.min(1, (t - (branchWake[branch.id] || t)) / 180);
      for (const limb of branch.own) {
        if (y > maxY) { limb._hit = null; limb.x = left; limb.y = branch.y; continue; }
        const lx = left + 14;
        limb.x = lx; limb.y = y;
        const busyL = limb.since > 0 && t - limb.since < USE_HOLD;
        const beat = busyL ? (Math.sin((t - limb.since) / USE_MS * Math.PI * 2) + 1) / 2 : 0;
        const heat = Math.max(limb.live ? 0.5 : LIMB_DIM,
                              busyL ? 0.7 + beat * 0.3 : 0,
                              limb === hovered ? 0.95 : 0);
        const color = css(LIMB_COLOR[limb.kind] || "fact");
        const r = 4.6;

        // The expanding ring while in use — same language as fan mode.
        if (busyL) {
          const k = ((t - limb.since) % USE_MS) / USE_MS;
          ctx.globalAlpha = (1 - k) * 0.5 * wake;
          ctx.strokeStyle = color;
          ctx.lineWidth = 1.2;
          ctx.beginPath(); ctx.arc(lx, y, r + 3 + k * 14, 0, Math.PI * 2); ctx.stroke();
        }

        // Body: the kind's shape (hexagon sense, square device, triangle
        // skill).
        ctx.globalAlpha = paperAlpha(heat) * wake;
        ctx.fillStyle = limb.live ? color + "33" : "rgba(0,0,0,0)";
        ctx.strokeStyle = color;
        ctx.lineWidth = isLight() ? 1.6 : 1.3;
        ctx.shadowColor = color;
        ctx.shadowBlur = busyL && !isLight() ? 12 : 0;
        const sides = LIMB_SIDES[limb.kind] || 6;
        const turn = sides === 4 ? Math.PI / 4 : -Math.PI / 2;
        ctx.beginPath();
        for (let i = 0; i < sides; i++) {
          const a = (i / sides) * Math.PI * 2 + turn;
          const px = lx + Math.cos(a) * r, py = y + Math.sin(a) * r;
          i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
        }
        ctx.closePath(); ctx.fill(); ctx.stroke();
        ctx.shadowBlur = 0;

        // Name + what it is doing now (as much as fits, clipped on
        // overflow).
        ctx.globalAlpha = (isLight() ? 0.95 : Math.min(1, heat + 0.35)) * wake;
        ctx.fillStyle = busyL || limb === hovered ? css("text") : css("dim");
        ctx.font = "500 11px " + family;
        ctx.fillText(limb.name, lx + 12, y + 0.5);
        if (busyL && limb.doing) {
          const nameW = ctx.measureText(limb.name).width;
          ctx.globalAlpha = 0.85 * wake;
          ctx.fillStyle = color;
          ctx.font = "500 10px " + family;
          const room = pane.right - (lx + 12 + nameW + 8) - 12;
          let doing = limb.doing;
          while (doing && ctx.measureText("· " + doing + "…").width > room) {
            doing = doing.slice(0, -2);
          }
          if (doing) {
            ctx.fillText("· " + (doing === limb.doing ? doing : doing + "…"),
                         lx + 12 + nameW + 8, y + 0.5);
          }
        }
        limb._hit = { x: lx - 10, y, w: 220, h: 18 };
        y += 19;
      }
      y += 5;
    }
    ctx.textBaseline = "alphabetic";
    ctx.globalAlpha = 1;
  }

  function drawLimbs(t) {
    if (!limbs.length) return;
    if (pane) { drawLimbRows(t); return; }
    const family = getComputedStyle(document.body).fontFamily;

    // Which branches are open: clicked, hovered, or in use right now.
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

    // Trunks: from the core to the branches. They always stand, whatever
    // the leaves' animation state — this is the tree's skeleton.
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

      // Hub: the branch's only face while closed — a bit more prominent,
      // clickable.
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

      // Branch name + its count while closed: "YETENEKLER · 5". In
      // ambient mode (brain BEHIND the chat) the name is not written — it
      // clashed with the chat text into an unreadable layer ("it stays
      // behind" — live complaint, 31.08); the name comes on use, hover or
      // reveal.
      const showName = reveal || busy || open
        || (hoverBranch && hoverBranch.id === branch.id);
      if (showName) {
        ctx.globalAlpha = paperAlpha(busy ? 0.85 : open ? 0.45 : 0.6);
        ctx.fillStyle = tone;
        ctx.textAlign = "center";
        ctx.font = "600 9px " + (getComputedStyle(document.body).fontFamily);
        // Lang.t: in this scope `t` is the frame time — the global
        // translator by its full name.
        const tag = open ? Lang.t(branch.label).toUpperCase()
                         : Lang.t(branch.label).toUpperCase() + " · " + branch.own.length;
        ctx.fillText(tag, branch.x, branch.y + (branch.below ? 18 : -13));
      }

      branch.branchHub = true;
      branch._hit = { x: branch.x, y: branch.y, r: 14 };
    }
    ctx.textAlign = "left";
    ctx.globalAlpha = 1;

    for (const limb of limbs) {
      // A closed branch's leaf is neither drawn nor clickable.
      if (!limb.stem || !expanded.has(limb.stem.id)) {
        limb._hit = null;
        continue;
      }
      // The opening is soft: leaves appear over 180 ms. It multiplies
      // every alpha assignment below (each block builds its own alpha).
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

      // The ring expanding around it while in use.
      if (busy) {
        const k = ((t - limb.since) % USE_MS) / USE_MS;
        ctx.globalAlpha = (1 - k) * 0.5 * wake;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(limb.x, limb.y, r + 3 + k * 18, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Its attachment to the branch should show: a faint nerve. It
      // connects to the branch, not the core — what makes the tree a
      // tree.
      const stem = limb.stem;
      ctx.globalAlpha = paperAlpha(heat * 0.22) * wake;
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(stem ? stem.x : core.x, stem ? stem.y : core.y);
      ctx.lineTo(limb.x, limb.y);
      ctx.stroke();

      // Body: a hexagon. Round, it could not be told from the memory
      // nodes — the two share the scene.
      ctx.globalAlpha = paperAlpha(heat) * wake;
      ctx.fillStyle = limb.live ? color + "33" : "rgba(0,0,0,0)";
      ctx.lineWidth = isLight() ? 1.7 : 1.4;
      ctx.shadowColor = color;
      ctx.shadowBlur = busy && !isLight() ? 16 : 0;
      const sides = LIMB_SIDES[limb.kind] || 6;
      // The square is rotated a little: an axis-aligned square looks
      // crooked when everything else on the scene is curved.
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

      // The label is always written: faint or not, what it owns should be
      // readable. Unlike web nodes these are fixed and few.
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

  // --- drawing --------------------------------------------------------
  function paint(t) {
    blend();
    // clearRect under the identity transform can leave a 1 px ghost at
    // the edge — when the panel opened and the centre shifted, the old
    // brain doubled for a moment. Clear in device pixels, then return to
    // the CSS scale.
    const ratio = window.devicePixelRatio || 1;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    // `t` is the frame time. The event-driven layers (ripples, signals,
    // stitches, marks, flashes) map it through anim() themselves: on the
    // frozen event clock they stand while the ambient rotation goes on.
    drawAura(t);
    drawRipples(t);
    // Memory screen positions derive from the brain's rotation: computed
    // once before drawing, then used by the web and the nodes.
    projectNodes(t);
    drawColdRing(t);
    drawWeb(t);
    drawStitches(t);
    // Memories always on top: the silhouette is ground, node/text stays
    // readable. (The old dark path printed the sparse cloud on top — once
    // the chalk sharpened it would swallow the memories.)
    drawCore(t);
    drawNodes(t);
    drawLimbs(t);
    drawSignals(t);
    drawBridges(t);
    drawMarks(t);
    drawInjections(t);
    drawMode(t);
    drawStatus(t);
    drawLegend();
  }

  // A single line right under the core saying what it is doing now. The
  // colour is the mode's own (purple thinking, amber working…), a slowly
  // beating dot beside it shows it is alive. Idle writes nothing:
  // silence is cleaner than a permanent "ready" on screen.
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
    // A beating dot before the word.
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

  // What the colours mean. Permanent but very faint: it should answer
  // "what was this colour" at a glance without splitting the scene. On
  // the left edge, vertically centred — the top corner belongs to the
  // chat in a narrow window, the bottom to the organs in a wide one; the
  // left edge is free in both.
  //
  // It writes only what is really on screen: showing an empty section
  // would draw something that does not exist as if it did.
  const LEGEND_ORDER = ["user", "preference", "lesson", "procedure",
                        "voice", "fact", "goal", "world", "episode", "session"];

  // NEXT TO each colour is written what it is. A single word ("bilgi",
  // "oturum") did not explain what it stood for; a short gloss is attached
  // so it reads at a glance. Dot = memory kind, shape = organ kind.
  const LEGEND_GLOSS = {
    user: "Seni tanıdıklarım",
    preference: "Tercihlerin",
    lesson: "Çıkardığım dersler",
    procedure: "Yöntemlerim",
    voice: "Konuşma biçimin",
    fact: "Öğrendiklerim",
    goal: "İş listesi",
    world: "Gördüklerim",
    episode: "Geçmiş konuşmalar",
    session: "Geçmiş konuşmalar",
  };

  // Focus mode: the legend and surrounding decoration fade, leaving core
  // + chat — like talking to someone. The scene stays alive; only the
  // reading aids (colour key) withdraw.
  let focusMode = false;
  function focus(on) { focusMode = !!on; }

  // The legend on demand: collapsible instead of a huge fixed block in
  // the panel.
  let legendOn = false;
  function legend(on) { legendOn = !!on; layout(); start(); }

  function drawLegend() {
    if (focusMode) return;
    if (pane && !legendOn) return;
    // Ambient mode (brain BEHIND the chat): the colour key is not drawn —
    // it clashed with the chat text into unreadable lines ("the things
    // showing the colours always stay behind" — live complaint). The
    // legend lives where the brain is the front surface (panel/lens) or
    // when the user opened the web deliberately (reveal).
    if (!pane && !reveal) return;
    const kinds = [...new Set(nodes.map(n => n.group))]
      .sort((a, b) => LEGEND_ORDER.indexOf(a) - LEGEND_ORDER.indexOf(b));
    const rows = kinds.map(g => ({
      color: css(g), shape: "dot",
      name: t(LABEL[g]) || g, gloss: t(LEGEND_GLOSS[g]) || "",
    }));

    // Limbs carry colour AND shape. On the scene a sense is a hexagon, a
    // device a square, a skill a diamond; the legend draws the same shape
    // so they match.
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
    const lh = pane ? 19 : 20, r = 5, x = pane ? pane.left + 22 : 16;
    const total = (rows.length + limbRows.length + gap) * lh;
    // In panel mode the legend sits at the very bottom; without a panel,
    // centred on the left edge.
    let y = pane ? Math.max(core.y + core.r * 2.4, pane.bottom - total - 18)
                 : Math.max(24, core.y - total / 2);
    // More readable: the old value (0.26) went unnoticed. Dot bright, text
    // medium, gloss faint — three levels apart at a glance.
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

  // Drawing is capped at 30 frames. rAF fires at 150 Hz on this machine
  // (measured) and painting a full-screen gradient + shadows + 2187 dots
  // every frame is GPU burnt for nothing in a window open all day. None
  // of the animations here need more than 30 — rotations are slow, the
  // pulse on the order of seconds.
  const PAINT_MS = 33;
  let lastPaint = 0;

  // Opening/closing panels (settings, viewer, history) does NOT grow the
  // canvas: #scene is fixed full-screen, what changes is the chat
  // column's PLACE (--gut). ResizeObserver does not see position changes
  // — the box size stays the same — and the centre only fixed itself when
  // the 30 s graph refresh called layout: the brain looked squeezed under
  // the panel, then centred "by itself". The free area is probed every
  // frame; on change the centre and layout update INSTANTLY — staying
  // correct during the panel's transition animation too.
  let lastFree = "";

  function frame() {
    raf = requestAnimationFrame(frame);
    const t = now();
    if (t - lastPaint >= PAINT_MS) {
      lastPaint = t;
      // The event clock: advances with the frame unless frozen.
      const ta = anim(t);
      if (!animClock.frozen) { animFrames += 1; runPlan(ta); }
      const mr = mindRect();
      // Height/top too: the camera deck shortens the pane while the width
      // stays — watching only left+width let the brain overflow with its
      // old radius.
      const free = mr
        ? [Math.round(mr.left), Math.round(mr.top),
           Math.round(mr.width), Math.round(mr.height)].join("x")
        : "f" + Math.round(freeWidth());
      if (free !== lastFree) { lastFree = free; layout(); }
      paint(t);
    }
  }

  function drawAura(t) {
    // NO coloured halo in light mode: cyan mist rings bleeding into the
    // paper sank the brain and the text into the ground (what the user
    // called 'the centre is invisible'). In the dark theme the halo IS
    // the scene's light.
    if (isLight()) return;
    const beat = (Math.sin(t / look.beat) + 1) / 2;
    const g = ctx.createRadialGradient(core.x, core.y, 0, core.x, core.y, core.r * 4.2);
    g.addColorStop(0, tint(look.glow * 0.5 + beat * 0.025));
    g.addColorStop(0.45, tint(0.03));
    g.addColorStop(1, tint(0));
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, view.w, view.h);
  }

  // The synapse web: faint but always there. Links on the path stand
  // out.
  function drawWeb(t) {
    const ta = anim(t);
    ctx.lineWidth = 1;
    const thin = ta < thinUntil ? 0.35 : 1;
    const night = 1 - nightDim * 0.6;
    for (const edge of web) {
      const onPath = edge.a.order && edge.b.order &&
        Math.abs(edge.a.order - edge.b.order) === 1;
      const light = isLight();
      // An edge born tonight grows in from a to b, bright, then settles.
      let grow = 1, fresh = 0;
      if (edge.born) {
        const k = (ta - edge.born) / EDGE_MS;
        if (k >= 1) edge.born = 0; else { grow = Math.min(1, k * 2); fresh = 1 - k; }
      }
      ctx.strokeStyle = onPath || fresh ? css(edge.b.group) : (light ? css("text") : "#8A8071");
      ctx.lineWidth = (light ? 1.35 : 1) * thin + fresh;
      ctx.globalAlpha = Math.min(1, (onPath ? (light ? 0.85 : 0.5)
        : (light ? 0.38 : WEB_ALPHA * (reveal ? 3 : 1))) * night + fresh * 0.6);
      ctx.beginPath();
      ctx.moveTo(edge.a.x, edge.a.y);
      ctx.lineTo(edge.a.x + (edge.b.x - edge.a.x) * grow, edge.a.y + (edge.b.y - edge.a.y) * grow);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  function drawNodes(t, ta) {
    if (ta === undefined) ta = anim(t);
    const night = 1 - nightDim * 0.55;
    const family = getComputedStyle(document.body).fontFamily;
    // The chat column is transparent: labels must not bleed through the
    // text.
    const chat = document.querySelector(".stream");
    const chatBox = chat ? chat.getBoundingClientRect() : null;
    const inChat = (x, y) => chatBox
      && x >= chatBox.left && x <= chatBox.right
      && y >= chatBox.top && y <= chatBox.bottom;

    // A far (behind-the-brain) memory must be drawn first so the near
    // ones stay on top — the same painter's order as the brain cloud.
    const ordered = [...nodes].sort((a, b) => (a.depth ?? 0) - (b.depth ?? 0));
    // "Show all memories": LABELLING all at once turned into unreadable
    // soup (seen live). The front ~10 get labels; as the brain rotates
    // every memory takes its turn — a rotating showcase.
    const showcase = reveal && !searchHits
      ? new Set(ordered.slice(-10).map((n) => n.id))
      : null;
    for (const node of ordered) {
      if (node.flash > 0 && node.lit) {
        // The decay is on the event clock: frozen, the flash holds. The
        // ceiling is the level the strike set (a touch is fainter than a
        // replay step), not always 1.
        const k = (ta - node.lit) / FLASH_MS;
        const peak = node.peak === undefined ? 1 : node.peak;
        node.flash = k >= 1 ? 0 : peak * (1 - Math.max(0, k));
      }
      // Born tonight: grows in from nothing.
      let grow = 1;
      if (node.born) {
        const k = (ta - node.born) / BIRTH_MS;
        if (k >= 1) node.born = 0; else grow = Math.max(0.05, k);
      }
      // A world record nobody verified yet stays faint: seen, not known.
      const unverified = node.group === "world" && !node.dogrulama;

      // Depth: near (front) bright and large, far (back) faint and small.
      const near = ((node.depth ?? 0) + 1.1) / 2.2;   // 0..1
      const depthAlpha = 0.4 + near * 0.6;
      const depthSize = 0.7 + near * 0.55;

      const onPath = node.order > 0;
      const isFocused = onPath && route[focused] && route[focused].node === node.id;
      const hit = searchHits ? searchHits.has(node.id) : false;
      const dim = searchHits && !hit ? 0.2 : 1;   // during a search, non-matches fade
      const base = onPath ? PATH_FLOOR : 0;
      const heat = Math.max(
        base + node.flash * (1 - base),
        node === selected || node === hovered ? 0.8 : 0,
        isFocused ? 1 : 0,
        hit ? 0.75 : 0,
        reveal ? 0.4 : 0
      );
      const color = css(node.group);
      const lightNode = isLight();

      // The arrow from the node that relayed the activation: show the
      // direction too.
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

      const r = (2.2 + heat * 4) * depthSize * (lightNode ? 1.35 : 1) * grow;
      if (heat > 0.05) {
        const alpha = Math.round(heat * (lightNode ? 200 : 150)).toString(16).padStart(2, "0");
        const g = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, r * 5);
        g.addColorStop(0, color + alpha);
        g.addColorStop(1, color + "00");
        ctx.globalAlpha = dim;
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(node.x, node.y, r * 5, 0, Math.PI * 2); ctx.fill();
      }

      const twk = 0.68 + 0.32 * (Math.sin(t / 1500 + (node.p3.x - node.p3.z) * 8) * 0.5 + 0.5);
      ctx.globalAlpha = Math.min(1, lightNode
        ? (0.78 + heat * 0.22) * depthAlpha
        : (LATENT * twk + heat * (1 - LATENT)) * depthAlpha) * dim
        * (unverified ? 0.55 : 1) * (heat > 0.05 ? 1 : night);
      ctx.shadowBlur = heat > 0.05 && !lightNode ? 14 : 0; ctx.shadowColor = color;
      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(node.x, node.y, r, 0, Math.PI * 2); ctx.fill();
      ctx.shadowBlur = 0;

      // A label only on genuinely interesting nodes: on the path,
      // selected, or hovered. Even with "show details" on, writing all of
      // them made the screen unreadable — dozens of labels rode on the
      // chat text.
      // With "show all memories" on, the FRONT-facing ones get their
      // names: in the light theme the nodes are bright anyway, so the
      // button looked "broken" — its visible effect is the labels.
      const named = onPath || node === selected || node === hovered || hit
        || (showcase && showcase.has(node.id));
      if (named && heat > 0.3) {
        // The label normally writes outward. On a node near the edge,
        // outward means off screen: the text gets cut or slides under the
        // chat. It flips inward then.
        const LABEL_ROOM = 130;
        let outward = Math.cos(node.angle) >= 0 ? 1 : -1;
        const rEdge = pane ? pane.right - 6 : freeLeft + freeWidth();
        const lEdge = pane ? pane.left + 6 : freeLeft;
        if (outward > 0 && node.x + LABEL_ROOM > rEdge) outward = -1;
        else if (outward < 0 && node.x - LABEL_ROOM < lEdge) outward = 1;
        ctx.textAlign = outward > 0 ? "left" : "right";
        ctx.globalAlpha = Math.min(1, (heat - 0.3) * 2.6);
        const lx = node.x + outward * (r + 9);
        const ly = node.y + 5;
        // Do not draw labels falling inside the chat rect — the centre
        // column and the left head must not overlap (live, 31.08).
        if (inChat(lx, ly) || inChat(node.x, node.y)) {
          node._hit = { x: node.x, y: node.y, r: r + 8 };
          continue;
        }
        // The order number: which stop on the map it is should read.
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
        // No band: a thin outline + the node's colour. Readable over the
        // brain too, without looking like a box.
        if (lightNode) {
          ctx.lineWidth = 3;
          ctx.lineJoin = "round";
          ctx.strokeStyle = "rgba(231, 237, 244, .92)";
          ctx.strokeText(label, lx, ly);
          ctx.fillStyle = isFocused ? css("text") : color;
        } else {
          ctx.shadowBlur = 12; ctx.shadowColor = "#000";
          ctx.fillStyle = isFocused ? "#ffffff" : "#EFE8DC";
        }
        ctx.fillText(label, lx, ly);
        ctx.shadowBlur = 0;
        ctx.lineWidth = 1;
      }

      node._hit = { x: node.x, y: node.y, r: r + 8 };
    }
    ctx.globalAlpha = 1; ctx.textAlign = "left";
  }

  // --- the brain ---------------------------------------------------------
  //
  // A rotating 3D point cloud. What produces the image is not a library —
  // three.js is unavailable (no CDN, CSP lets no request out, the program
  // must work offline too) but what is needed is a few dozen lines
  // anyway: generate points on a surface, rotate, project.
  //
  // The surface derives from a sphere:
  //   squash      a brain is longer than wide, wider than tall
  //   front taper the frontal lobe narrower than the back
  //   fissure     the two hemispheres split down the middle
  //   folds       ridges and grooves via a sum of sines
  //   cerebellum  a separate small lobe at the back bottom
  //
  // The point cloud is generated once and fixed; each frame is only
  // rotation and projection. No accumulation that is not a function of
  // time, so skipped frames while backgrounded cause no jump.

  const SPARKS = 6;        // points firing at once
  // The view is nearly from the side. Seen from above, the brain sat like
  // an oval smudge — the silhouette that makes a brain a brain (frontal
  // lobe, temple, cerebellum below) reads from the side. A small tilt is
  // enough for depth.
  const TILT = -0.12;

  let cloud = null;

  // The point cloud comes from `brain.js`: 2187 points decimated from a
  // real brain geometry.
  //
  // It used to be hand-built from a sphere + sine folds. It resembled a
  // brain from afar but was a walnut up close, and every attempt broke
  // somewhere else: the frontal lobe went pointy, the cerebellum turned
  // into a shelf, the folds lined up like a comb. The real geometry is
  // both correct and cheaper — ready-made points are rotated instead of
  // deriving them every frame.
  function brainCloud() {
    if (cloud) return cloud;

    // If the file failed to load the scene must still open: a brainless
    // core beats a window that never opens.
    const flat = typeof BRAIN_POINTS === "undefined" ? null : BRAIN_POINTS;
    if (!flat || !flat.length) { cloud = []; return cloud; }

    const points = [];
    for (let i = 0; i < flat.length; i += 3) {
      const x = flat[i], y = flat[i + 1], z = flat[i + 2];
      // Cerebellum: the ones at the back bottom. Not drawn separately but
      // a little dimmer — the texture difference separating it reads this
      // way.
      const back = z < -0.35 && y > 0.12;
      points.push({ x, y, z, fold: back ? 0.72 : 1 });
    }
    cloud = points;
    return cloud;
  }

  // The brain's rotation for that frame. Both the cloud and the memories
  // use the same rotation so they turn together — a memory belongs to a
  // place inside the brain.
  function brainSpin(t) {
    const s = t / 22000 * (0.5 + look.spin * 0.5);
    return { cosY: Math.cos(s), sinY: Math.sin(s), cosX: Math.cos(TILT), sinX: Math.sin(TILT) };
  }

  // Rotates a 3D point and projects it with perspective. Rotation: Y axis
  // + a forward tilt. Perspective: the front is bigger. Works in unit
  // space; screen scale is the caller's (× r).
  function project3(x, y, z, rot) {
    const rx = x * rot.cosY + z * rot.sinY;
    const rz = -x * rot.sinY + z * rot.cosY;
    const ry = y * rot.cosX - rz * rot.sinX;
    const rz2 = y * rot.sinX + rz * rot.cosX;
    const scale = 2.6 / (2.6 + rz2);
    return { x: rx * scale, y: ry * scale, z: rz2, scale };
  }

  // A memory's fixed 3D position inside the brain's VOLUME. A surface
  // point is chosen and pulled inward (interior, not shell); a small
  // id-noise is added. The same id always gives the same place — an
  // engram. If the brain failed to load, fall back to a position inside
  // a sphere.
  function insideBrain(id) {
    const c = brainCloud();
    if (c.length) {
      const p = c[Math.floor(hash01(id, 0x51ed3f) * c.length)];
      const pull = 0.34 + hash01(id, 0x77aa11) * 0.5;   // 0.34..0.84 inward
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

  // Every frame: computes the memories' screen positions through the
  // brain's rotation. Adds a slight drift (a small oscillation tied to
  // the id's phase) — alive inside the brain, not frozen. depth is
  // front/back; drawNodes uses it for brightness and size.
  function projectNodes(t, ta) {
    if (ta === undefined) ta = anim(t);
    const rot = brainSpin(t);
    const r = core.r * 1.45;
    for (const node of nodes) {
      if (!node.p3) node.p3 = insideBrain(node.id);
      let p = node.p3;
      // Warming: from the cold ring (outside the volume) to the engram.
      if (node.warm) {
        const k = (ta - node.warm) / WARM_MS;
        if (k >= 1) { node.warm = 0; node.p3out = null; }
        else if (node.p3out) {
          const e = 1 - Math.pow(1 - Math.max(0, k), 3);
          p = { x: node.p3out.x + (p.x - node.p3out.x) * e,
                y: node.p3out.y + (p.y - node.p3out.y) * e,
                z: node.p3out.z + (p.z - node.p3out.z) * e };
        }
      }
      // Distillation: drawn toward the sources' centre, then let go.
      if (node.pull) {
        const k = (ta - node.pull.born) / (node.pull.dur || PULL_MS);
        if (k >= 1) node.pull = null;
        else {
          const bell = Math.sin(Math.max(0, k) * Math.PI) * 0.6;
          p = { x: p.x + (node.pull.to.x - p.x) * bell,
                y: p.y + (node.pull.to.y - p.y) * bell,
                z: p.z + (node.pull.to.z - p.z) * bell };
        }
      }
      const ph = (node.p3.x + node.p3.z) * 6.283, d = 0.018;
      const pr = project3(
        p.x + Math.sin(t / 2600 + ph) * d,
        p.y + Math.cos(t / 3100 + ph) * d,
        p.z + Math.sin(t / 2900 + ph * 1.3) * d,
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
    const spin = t / 22000 * (0.5 + look.spin * 0.5);

    const cosY = Math.cos(spin), sinY = Math.sin(spin);
    const cosX = Math.cos(TILT), sinX = Math.sin(TILT);
    // Light: an INK silhouette (dark slate). Dark: a CHALK silhouette
    // (ice). The old dark path (mode tint + 0.10 alpha + half-size dots)
    // vanished among the HUD rings — crisp in light, washed out on black.
    // The mode colour blends into the chalk (purple thinking, amber
    // working still read).
    const light = isLight();
    const colour = light
      ? [28, 48, 68]
      : [
          Math.round(look.tint[0] * 0.28 + 210 * 0.72),
          Math.round(look.tint[1] * 0.28 + 232 * 0.72),
          Math.round(look.tint[2] * 0.28 + 248 * 0.72),
        ];

    // Far points must be drawn first or the near ones end up behind.
    // Sorted every frame: for 1500 points the cost is too small to
    // measure.
    const shown = [];
    for (let i = 0; i < points.length; i++) {
      const p = points[i];
      // Rotation around the Y axis, then the forward tilt.
      const rx = p.x * cosY + p.z * sinY;
      const rz = -p.x * sinY + p.z * cosY;
      const ry = p.y * cosX - rz * sinX;
      const rz2 = p.y * sinX + rz * cosX;

      // Perspective: near is big. In orthogonal projection the brain sat
      // flat, depth never read.
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
      // The same silhouette language in both modes: high alpha, legible
      // dot size. Depth via shade (far slightly dim); no "lift" toward
      // white — that path sank the dot into the ground in dark mode too.
      ctx.globalAlpha = (0.55 + near2 * 0.35) * p.f;
      const shade = light ? (0.88 + near2 * 0.12) : (0.78 + near2 * 0.22);
      ctx.fillStyle = "rgb(" + Math.round(colour[0] * shade) + ","
        + Math.round(colour[1] * shade) + "," + Math.round(colour[2] * shade) + ")";
      const size = (1.05 + near2 * 0.7) * p.s;
      ctx.fillRect(p.x - size / 2, p.y - size / 2, size, size);
    }

    // Firings: a few points glow. That the brain is working reads from
    // here and the rate follows the mode — denser while thinking. No glow
    // in light mode: a glare on white does nothing but wash the dot out.
    ctx.shadowColor = css("ice");
    ctx.shadowBlur = light ? 0 : 10;
    ctx.fillStyle = css("ice");
    const period = 2400 / (0.5 + look.spin);
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

    ctx.globalAlpha = 1;
    ctx.shadowBlur = 0;
  }

  // The holographic core: concentric arcs at different speeds.
  function drawCore(t) {
    const light = isLight();
    const cyan = tint(1);
    const seconds = t / 1000;
    const beat = (Math.sin(t / look.beat) + 1) / 2;

    ctx.save();
    // In the panel the canvas is full-screen: clip between header and
    // foot so an oversized frame does not spill onto the search box. The
    // scale follows the hole; this is the backstop.
    if (pane) {
      const top = hole ? hole.clipTop : pane.top;
      const bot = hole ? hole.clipBottom : pane.bottom;
      ctx.beginPath();
      ctx.rect(pane.left, top, pane.width, Math.max(0, bot - top));
      ctx.clip();
    }
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

    // Scale ticks: the technical feel comes from here.
    const tickR = core.r * 2.24;
    ctx.lineWidth = 1;
    ctx.globalAlpha = light ? 0.78 : 0.3;
    ctx.shadowBlur = 0;
    for (let i = 0; i < 60; i++) {
      const a = (i / 60) * Math.PI * 2 + seconds * 0.025;
      const out = tickR + (i % 5 === 0 ? 9 : 4);
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * tickR, Math.sin(a) * tickR);
      ctx.lineTo(Math.cos(a) * out, Math.sin(a) * out);
      ctx.stroke();
    }

    if (ctx.createConicGradient) {
      // The sweep lives in a ring band outside the brain: passing over
      // it, it washed out and swallowed the dots.
      const wedge = ctx.createConicGradient(seconds * look.wedge, 0, 0);
      // In light mode the sweep slice sat like a pale grey sector: dim
      // it.
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
    t = anim(t);
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

  // --- interaction ----------------------------------------------------
  function at(ev) {
    const near = (item) => {
      const h = item._hit;
      if (!h) return false;
      if (h.w && h.h) {
        return ev.clientX >= h.x && ev.clientX <= h.x + h.w
            && Math.abs(ev.clientY - h.y) <= h.h / 2;
      }
      return Math.hypot(h.x - ev.clientX, h.y - ev.clientY) <= h.r;
    };
    // Organs first: small and on top, a node must not swallow them.
    // Branch hubs after organs: a leaf on an open branch should be
    // selectable itself even near the hub.
    return limbs.find(near) || branches.find(near) || nodes.find(near) || null;
  }

  function onMove(ev) {
    pointer = { x: ev.clientX, y: ev.clientY };
    hovered = at(ev);
    // On hover, what it is reads without a click: a short identity. If a
    // clicked (pinned) card exists, hover does not override it.
    if (!selected) {
      if (hovered && !hovered.branchHub) showProbeAt(hovered, ev.clientX, ev.clientY, true);
      else probe.hidden = true;
    }
    // The cold ring: not a node, but a region with its own tooltip. The
    // overlay (regions.js) draws that tooltip; the scene only reports.
    const onRing = !hovered && coldHit(ev);
    if (onRing !== coldRing.hover) { coldRing.hover = onRing; onCold(onRing ? pointer : null); }
    // In the fan a branch opens temporarily on hover, and stays open over
    // a leaf (it must not close between hub and leaf). In the panel list
    // hover does not open — onMove still marks it, the row brightens, no
    // fan opens.
    hoverBranch = hovered && hovered.branchHub ? hovered
                : hovered && hovered.organ ? hovered.stem
                : null;
    canvas.style.cursor = hovered || coldRing.hover ? "pointer" : "default";
  }

  function onDown(ev) {
    selected = at(ev);
    if (!selected) { probe.hidden = true; return; }
    if (selected.branchHub) {
      // Clicking the hub opens/closes the branch — ACCORDION. With two
      // branches open, the lower rows sank under the panel's base
      // (legend/EXPLANATION) and it looked like "I opened it but nothing
      // opened" (live complaint, 31.08); a single open branch always fits
      // the list.
      if (openBranches.has(selected.id)) {
        openBranches.delete(selected.id);
      } else {
        openBranches.clear();
        openBranches.add(selected.id);
      }
      probe.hidden = true;
      start();
      return;
    }
    showProbeAt(selected, ev.clientX, ev.clientY);
  }

  // Converts an ISO stamp to a readable day: "2026-08-23T17:30" ->
  // "23.08 17:30".
  function dayStamp(ts) {
    const s = String(ts || "");
    return /^\d{4}-\d{2}-\d{2}T/.test(s)
      ? s.slice(8, 10) + "." + s.slice(5, 7) + " " + s.slice(11, 16)
      : "";
  }

  // mini: the short identity shown on hover (title + kind). The pinned
  // card (click) carries the detail, the keywords, "Nasıl öğrendim" and
  // the action leading to the source.
  function showProbeAt(node, x, y, mini) {
    probe.textContent = "";
    probe.classList.toggle("pinned", !mini);
    const title = document.createElement("div");
    title.className = "t";
    const kind = document.createElement("div");
    kind.className = "k";
    const body = document.createElement("div");
    body.className = "b";

    if (node.organ) {
      // On a device what you want to read is its state, not its order:
      // is it on, what is it doing now. "On" and "in use" are not the
      // same thing.
      title.textContent = node.name;
      kind.textContent = [node.state, node.doing].filter(Boolean).join(" · ");
      body.textContent = node.detail || "";
      probe.append(title, kind, body);
    } else {
      title.textContent = node.order ? node.order + ". " + node.label : node.label;
      kind.textContent = [t(LABEL[node.group]) || node.group,
                          mini ? "" : node.meta && node.group === "goal" ? node.meta : "",
                          node.group === "world"
                            ? (node.dogrulama ? t("doğrulama") + ": " + dayStamp(node.dogrulama)
                                              : t("doğrulanmamış"))
                            : "",
                          node.ghost && node.warm ? t("soğuk") : ""]
        .filter(Boolean).join(" · ");
      body.textContent = mini ? "" : (node.detail || "");
      probe.append(title, kind, body);

      if (!mini) {
        // Keywords: the tags on the record.
        if (node.meta && node.group !== "goal" && node.group !== "session") {
          const keys = document.createElement("div");
          keys.className = "probe-keys";
          keys.textContent = t("Anahtar kelimeler") + ": " + node.meta;
          probe.append(keys);
        }
        // How I learned it: when, in which conversation + the action to
        // the source. If the source session's file is gone (moved/merged
        // memories) the button does not appear AT ALL — instead of a
        // promise that clicks and goes nowhere, the card honestly states
        // the situation.
        const reachable = node.group === "session" || node.kaynak_var !== false;
        const target = reachable
          ? (node.kaynak || (node.group === "session" ? node.id : null))
          : null;
        if (target || dayStamp(node.ts) || (node.kaynak && !reachable)) {
          const learn = document.createElement("div");
          learn.className = "probe-learn";
          learn.textContent = t("Nasıl öğrendim") + ": "
            + [dayStamp(node.ts),
               target ? t("bu konuşmada") : (node.kaynak ? t("kaynak konuşma artık yok") : "")]
              .filter(Boolean).join(" · ");
          if (node.group === "session") learn.textContent = "";
          if (learn.textContent) probe.append(learn);
        }
        if (target) {
          const goBtn = document.createElement("button");
          goBtn.type = "button";
          goBtn.className = "probe-git";
          goBtn.textContent = t("Konuşmaya git →");
          goBtn.title = t("çift tık da açar");
          goBtn.addEventListener("click", () => {
            probe.hidden = true;
            selected = null;
            onSession(target);
          });
          probe.append(goBtn);
        }
      }
    }

    probe.hidden = false;
    const rect = probe.getBoundingClientRect();
    const px = x === undefined ? node.x + 16 : x + 18;
    const py = y === undefined ? node.y + 12 : y + 14;
    probe.style.left = Math.max(20, Math.min(px, innerWidth - rect.width - 20)) + "px";
    probe.style.top = Math.max(70, Math.min(py, innerHeight - rect.height - 20)) + "px";
  }

  // --- mode-specific layer ---------------------------------------------
  //
  // Everything here is stateless: position is a function of `t` alone, no
  // stored particle state. One reason: a particle system that accumulates
  // while the tab is backgrounded jumps on return, a pure function does
  // not.

  function drawMode(t) {
    ctx.save();
    if (pane) {
      const top = hole ? hole.clipTop : pane.top;
      const bot = hole ? hole.clipBottom : pane.bottom;
      ctx.beginPath();
      ctx.rect(pane.left, top, pane.width, Math.max(0, bot - top));
      ctx.clip();
    }
    if (mode === "waking") wakingPulse(t);
    else if (mode === "thinking") thinkingMotes(t);
    else if (mode === "writing") writingStream(t);
    else if (mode === "recalling") recallSweep(t);
    else if (mode === "working") workingPackets(t);
    ctx.restore();
  }

  // Waking: a single ring slowly opening outward. Like a pulse — nobody
  // is thinking yet, just a system coming up.
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

  // Thinking: traces spiralling inward toward the core. The feel of
  // something gathering, not yet spoken.
  function thinkingMotes(t) {
    const count = 14;
    const cycle = 3600;
    ctx.save();
    ctx.translate(core.x, core.y);
    for (let i = 0; i < count; i++) {
      const phase = ((t + i * (cycle / count)) % cycle) / cycle;
      const r = core.r * (3.1 - phase * 2.0);
      const a = (i / count) * Math.PI * 2 + phase * 1.4 + t / 7000;
      // Start and end faint: appearing as it enters, melting at the core.
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

  // Writing: short lines flowing from under the core toward the chat.
  // As text appears on screen, its source shows as the core.
  function writingStream(t) {
    const lanes = 7;
    const cycle = 1700;
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

  // Recalling: sonar rings spreading from the core into the web. This is
  // the activation walking outward; which node it reaches is shown by
  // `activate`.
  function recallSweep(t) {
    const cycle = 2200;
    const rings = 3;   // simultaneous sonar rings (was undefined: in recall
                       // mode a ReferenceError killed the frame loop)
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

  // Working: data packets orbiting the core. The feel of something being
  // carried and processed — mechanical, unlike thinking.
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
      // Staggered speed: packets pass scattered, not in file.
      const a = t / 1800 * (1 + (i % 3) * 0.14) + (i / count) * Math.PI * 2;
      ctx.globalAlpha = 0.35 + 0.45 * ((Math.sin(a * 3) + 1) / 2);
      ctx.fillRect(Math.cos(a) * r - size / 2, Math.sin(a) * r - size / 2, size, size);
    }
    ctx.restore();
    ctx.globalAlpha = 1; ctx.shadowBlur = 0;
  }


  // Memory search (the box in the panel header): matching nodes light up,
  // the rest fade. Over label + kind + detail, case-insensitive.
  function search(q) {
    const needle = String(q || "").trim().toLocaleLowerCase("tr");
    if (needle.length < 2) { searchHits = null; start(); return; }
    searchHits = new Set(nodes
      .filter((n) => ((n.label || "") + " " + (n.group || "") + " "
                      + (n.detail || "") + " " + (n.meta || ""))
        .toLocaleLowerCase("tr").includes(needle))
      .map((n) => n.id));
    start();
  }

  // With the panel closed the canvas is hidden too; drawing an invisible
  // scene is battery burnt for nothing. resume measures and picks up
  // where it left off.
  const pause = stop;
  const resume = () => { resize(); start(); };

  const summary = () => stats;

  return { init, load, activate, focusStep, clearRoute, ripple, bridge,
           signal, deposit, organs, use, release, search, pause, resume,
           setBusy, setMode, summary, redraw, focus, legend,
           // Phase 6 — regions and the night layer.
           geometry, freeze, thaw, frozen, frames, schedule, tick,
           lightSequence, stitch, touch, distil, mark, addEdge, thinEdges,
           dim, warm, inject, cold, coldSlice, onColdRing, ensureNode,
           strike, litLog: litLogRead, clearLog, planned: () => plan.length };
})();
