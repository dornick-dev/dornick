// Spoken speech.
//
// Waiting for the whole answer and then reading it would be an announcement,
// not a conversation: no sound until the model finishes writing. Instead,
// each sentence is queued as it completes and the queue flows without gaps —
// while the first sentence is being spoken the second is already being
// generated.
//
// Speech generation goes over the network and may not always work. Staying
// silent is acceptable; the text is on screen anyway. So no error is ever
// shown to the user, the sound simply does not come.

const Speech = (() => {
  // Sentence end. Turkish has few abbreviations; dot+space is reliable enough.
  const SENTENCE = /[^.!?…\n]+[.!?…]+["')\]]*|\n+/g;

  // Text that reaches this length without punctuation is spoken too: a model
  // writing bullet points may never place a period. It was 220; the voice
  // fell two-three seconds behind the text — shorter chunks track closer,
  // and prefetch already closes the gap between chunks.
  const FLUSH_AT = 110;

  // The threshold for the first chunk is much lower: waiting for the first
  // sentence to finish before any sound means seconds of silence on a long
  // opening sentence. Once speech has started we return to the normal
  // threshold — otherwise the answer comes out choppy and breathless.
  const FIRST_AT = 60;

  let on = false;
  let buffer = "";

  // The queue now holds **promising** chunks, not text: the moment a sentence
  // enters the queue its audio starts generating and is ready by its turn.
  //
  // The old state was serial — generate, play, generate, play — and since
  // generation alone took ~1.2 seconds, it fell that far behind on every
  // sentence. In a five-sentence answer the voice trailed the text by six
  // seconds.
  const queue = [];
  let playing = false;
  let current = null;
  // Finish hook of the chunk playing right now. Muting calls `pause()`, and
  // pause fires no event — the pending promise must be finished by hand.
  let ending = null;

  // How many chunks to generate at once. Unlimited means dozens of
  // concurrent requests on a long answer; two already zeroes out the lag.
  const PREFETCH = 2;
  let building = 0;

  // --- the voice's character --------------------------------------------
  //
  // The synthesizer produces a real human voice, and on its own that sounds
  // flat: like someone reading text, not like a thing that speaks. Turkish
  // voices also have no SSML emotion styles (all "General"), so there is
  // nothing more to be had from the generation side.
  //
  // So the character rides on top of the sound, here. Three layers:
  //
  //   doubling  a second copy delayed by 20 ms, with a slowly drifting
  //             delay. This is what gives the not-from-a-single-mouth feel.
  //   timbre    a boost at 2.4 kHz + a cut below 140 Hz. Takes out the
  //             chest tone and puts an electronic clarity in its place.
  //   flutter   a very slow, very small delay oscillation. Unnoticeable,
  //             but keeps the voice sitting at "alive but not human".
  //
  // None of it is overdone: once intelligibility suffers it reads as a
  // malfunction, not character. With `character` at 0 this layer is skipped
  // entirely and the sound plays directly.
  let character = 0;
  let audio = null;   // AudioContext, opened on first use

  function setCharacter(value) {
    character = Math.max(0, Math.min(1, Number(value) || 0));
  }

  function context() {
    if (!audio) audio = new (window.AudioContext || window.webkitAudioContext)();
    // A context opened without user interaction starts suspended.
    if (audio.state === "suspended") audio.resume().catch(() => {});
    return audio;
  }

  function enable(value) {
    on = !!value;
    if (!on) stop();
    else warmAcks();
  }

  // --- acknowledgement clips --------------------------------------------
  //
  // Short sounds played the moment the user goes quiet, before the model has
  // produced its first word. What carries the perceived latency is this
  // first reaction, not the answer — a person hearing a question also says
  // "let me see" first, then thinks.
  //
  // The server caches these on disk (clip: true) and the browser keeps them
  // as Blobs: generated once when voice is enabled, instant afterwards.
  const ACKS = ["bakıyorum", "bir saniye", "şimdi bakayım",
                "hemen bakıyorum", "bakalım"];

  const ackStock = new Map();   // text → Blob, kept for the whole session

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
    // If speech has already started, or a promise waits in the queue,
    // cutting in would not hide latency, it would interrupt.
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

  // Splits completed sentences out of the streaming text and queues them.
  function feed(chunk) {
    if (!on) return;
    buffer += chunk;

    let taken = 0;
    for (const match of buffer.matchAll(SENTENCE)) {
      push(match[0]);
      taken = match.index + match[0].length;
    }
    if (taken) buffer = buffer.slice(taken);

    // For the first chunk a comma is enough: waiting for the first full
    // sentence means the voice starts seconds late. After that, sentence
    // boundaries are used, or the speech comes out choppy and breathless.
    const started = queue.length > 0 || playing;
    const limit = started ? FLUSH_AT : FIRST_AT;
    if (buffer.length > limit) {
      const cut = split(buffer, limit);
      push(buffer.slice(0, cut));
      buffer = buffer.slice(cut);
    }
  }

  // To avoid cutting a word in half, look for a comma first, then a space.
  function split(text, limit) {
    for (const mark of [", ", " "]) {
      const at = text.lastIndexOf(mark, limit);
      if (at > 30) return at + mark.length;
    }
    return limit;
  }

  // The turn ended: speak whatever half-sentence is left over too.
  function flush() {
    if (!on) return;
    push(buffer);
    buffer = "";
  }

  function push(text) {
    const words = String(text || "").trim();
    // Lone punctuation or a letter or two is not worth generating audio for.
    if (words.length < 3) return;

    // Generation starts here, not when its turn comes: while playback runs,
    // the next chunk is prepared in the background.
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
      build();   // let the freed slot start generating the next one
      try {
        await play(await item.audio, item.text);
      } catch {
        // No network, no sound; the text is on screen, work must not stop.
      }
    }
    playing = false;
  }

  // url → Blob: the character layer wants the raw bytes. The blob URL used
  // to be fetched a second time — downloading our own data from ourselves,
  // tens of ms per clip. The Blob is kept on the side and dropped at play
  // time.
  const clips = new Map();

  // The first time speech generation fails, the user is told ONCE.
  // It used to be swallowed silently: the user enabled voice, heard
  // nothing, and could see nowhere why it did not work.
  let troubled = false;
  function voiceTrouble() {
    if (troubled) return;
    troubled = true;
    try {
      document.dispatchEvent(new CustomEvent("dornick:voice-trouble"));
    } catch { /* very old webview: no notice, but work goes on */ }
  }

  async function synth(text) {
    const response = await fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    // 204: nothing left to say (e.g. it was only a code block).
    if (response.status === 204) return null;
    if (!response.ok) {
      // 501 package missing, 503 service/network — no sound either way; say so.
      voiceTrouble();
      return null;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    clips.set(url, blob);
    return url;
  }

  // The ear closes while the agent speaks: sound from the speaker feeds back
  // into the microphone, and the assistant would hear its own sentence and
  // try to answer it. OS-level echo cancellation does not always work.
  function deafen(on, text) {
    // Let the speaker organ on the stage show it is talking too. This file
    // loads before the scene; even `typeof` throws before a const's
    // definition point, hence the try.
    try {
      on ? Scene.use("voice", "Konuşuyor") : Scene.release("voice");
    } catch { /* no scene yet: play the sound anyway */ }
    fetch("/api/speaking", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on, text: on ? String(text || "") : "" }),
    }).catch(() => {});
  }

  function play(url, text) {
    if (!url) return Promise.resolve();
    if (character > 0.01) {
      // The character layer wants the raw audio. If it fails (context did
      // not open, decode blew up) we fall back to plain playback: no sound
      // at all is worse than sound without character.
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

    // Timbre: the chest tone goes down, electronic clarity comes up.
    //
    // `lowshelf` — not `highshelf`. Highshelf attenuates everything **above**
    // 160 Hz, i.e. the entire voice: measured at full character, sound power
    // dropped 57%. The intent is only to take out the low-end rumble.
    const cut = ctx.createBiquadFilter();
    cut.type = "lowshelf";
    cut.frequency.value = 160;
    cut.gain.value = -7 * character;

    const edge = ctx.createBiquadFilter();
    edge.type = "peaking";
    edge.frequency.value = 2400;
    edge.Q.value = 0.9;
    edge.gain.value = 5 * character;

    // Doubling: a second copy delayed by 20 ms. This is what gives the
    // not-from-a-single-mouth feel.
    const twin = ctx.createDelay(0.1);
    twin.delayTime.value = 0.02;
    const twinLevel = ctx.createGain();
    twinLevel.gain.value = 0.42 * character;

    // Flutter: a very slow, very small oscillation. Unnoticeable, but keeps
    // the voice at "alive but not human".
    const drift = ctx.createOscillator();
    drift.frequency.value = 0.28;
    const depth = ctx.createGain();
    depth.gain.value = 0.0016 * character;
    drift.connect(depth).connect(twin.delayTime);
    drift.start();

    const out = ctx.createGain();
    // Summing the two paths raises the level; take it back down.
    out.gain.value = 1 / (1 + 0.42 * character);

    source.connect(cut).connect(edge);
    edge.connect(out);
    edge.connect(twin).connect(twinLevel).connect(out);
    out.connect(ctx.destination);

    return new Promise((done) => {
      const finish = () => {
        URL.revokeObjectURL(url);
        try { drift.stop(); } catch { /* already stopped */ }
        current = null;
        ending = null;
        // Opening the ear while sentences remain queued turned the speaker
        // echo in the inter-sentence gap into new speech.
        if (!queue.length) deafen(false);
        done();
      };
      // Muting calls this: `stop()` fires no event.
      current = { pause: () => { try { source.stop(); } catch { /* finished */ } } };
      ending = finish;
      deafen(true, text);
      source.onended = finish;
      // Safety: if the audio context stays suspended, `onended` never fires
      // and the ear stayed closed forever. The chunk's duration is known;
      // leave some margin and finish it ourselves.
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
      // If the object URL is not released, memory piles up for the whole
      // conversation.
      clips.delete(url);
      const finish = () => {
        URL.revokeObjectURL(url);
        current = null;
        ending = null;
        if (!queue.length) deafen(false);
        done();
      };
      // Muting calls this. `pause()` fires no event: without it the wait
      // below hangs forever, and when voice was re-enabled nothing ever
      // played again.
      ending = finish;
      audio.onended = finish;
      audio.onerror = finish;
      audio.play().catch(finish);
    });
  }

  function stop() {
    deafen(false);
    // Object URLs of chunks still generating must be released too.
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
    // Finish the pending promise: otherwise the play loop hangs and, once
    // voice is re-enabled, new sentences queue up and never play.
    if (ending) { const finish = ending; ending = null; finish(); }
  }

  return { enable, setCharacter, feed, flush, stop, ack, get on() { return on; } };
})();
