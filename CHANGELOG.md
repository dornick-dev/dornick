# Changelog

## 1.3.1 — 2026-08-31

Packaging completeness pass — nothing to install by hand, ever:

* An import sweep with the installer's own embedded Python now proves
  every third-party package the product touches is bundled (PDF, vision,
  audio, tray, browser — 19/19; `ultralytics` is deliberately the
  developer-only CUDA path, the shipped path is ONNX).
* The YOLO weight (`yolov8n.onnx`) ships inside the camera component:
  the first camera glance no longer downloads anything and works offline.
* Plus the owner's laptop batch: consistent launcher environment,
  AppUserModelID for proper taskbar identity, Windows toast
  notifications, speech-recognition and audio-decode refinements,
  PNG logo support, camera-handling optimisations.


## 1.3.0 — 2026-08-30

**The camera stage.** Built on a branch, tried live on a laptop, then
merged — with substantial work contributed directly by the project owner.

* **Camera watch area.** A deck lists the built-in webcam and any IP/RTSP
  cameras you add; tiles refresh with fresh frames (the camera opens per
  frame and closes — nothing stays recording). A status icon up top shows
  the truth at a glance: slashed when the camera master switch is off
  (click to enable), and the active mode when on.
* **Local vision (YOLO).** With a capable NVIDIA GPU, a local yolov8n
  model analyses frames on-device; without one, the LLM takes snapshots
  on demand. Motion frames never reach a hosted model without an explicit
  consent switch — same privacy pattern as the night school.
* **A real `camera` tool** for the model: list cameras, take 1-4
  snapshots (permission-gated — the model cannot open your camera on its
  own), see them, answer.
* **Voice & hearing controls** reworked: power toggles with live status,
  a hearing sync that follows configuration, echo handling improvements.
* **Listening latency fixed** (live complaint: 10-20 s behind on a weak
  laptop): models warm in the background at startup so the first sentence
  no longer pays the load cost, and a self-measuring downshift drops the
  recogniser one size (small → base) if CPU decoding repeatedly lags
  behind the audio — session-only, your setting is untouched.
* **A `git` tool** (status/commit/push and friends) so the agent stops
  shelling out for version control.


## 1.2.0 — 2026-08-29

**Parallel sessions.** Every session now runs on its own lane — its own
agent, queue and pump. Starting a new chat no longer waits for the running
turn: the old turn finishes in the background, the sidebar badges every
running chat, and a notice arrives when a background chat completes.
Background lane events never leak into the active view (approvals
excepted); the model client is shared per endpoint so a local server is
never double-loaded. Session switching also stopped dragging finished
helper channels into the new chat.

UI feedback batch from live use:

* Code blocks follow the theme — light theme gets a light code well with
  its own syntax palette (the black-on-cream patch is gone).
* The status line is modeled, not decorative: "Reasoning" while the
  reasoning channel streams, "Writing" while the answer streams,
  "Thinking" before anything flows — labels no longer rotate randomly,
  and tool verbs are deterministic.
* Plan cards show live step progress (✓ done / ▸ in progress / ○ waiting)
  driven by a new `step` action on the plan tool; approved plans keep
  their place with decision buttons hidden. The plan reflex threshold was
  raised so small tasks start immediately instead of drawing a plan.
* File links in chat act by type (download archives, open PDF/media,
  view code); decided earlier in 1.1.1, now with the plan-card and
  status fixes on top.


## 1.1.1 — 2026-08-29

Live-complaint fixes from a real research session, plus a behaviour rule.

* **File links in chat now work.** "[Download the ZIP](report.zip)" was
  dead text (zip was not a recognised extension) and PDF links depended on
  the viewer chain. Explicit file links now act by type: archives/office
  files download directly (`attachment` header, path-traversal guarded),
  PDF/images/media open in a new tab, text/code opens in the viewer. The
  viewer's binary screen gained a Download button.
* **Decided plan cards stay put.** An approved plan card used to be
  re-pinned below the final answer with its Approve/Edit/Cancel buttons
  still showing. Only cards awaiting a decision pin to the bottom now;
  decided ones keep their place in the flow, buttons hidden.
* **Visuals only when they earn their place.** The agent can produce
  charts, diagrams, screenshots and pages as evidence — the identity now
  carries one rule for when: only if the visual shows at a glance what
  text cannot. Text is the default; no decorative charts.


## 1.1.0 — 2026-08-29

Review hardening. Night-school privacy gate (hosted labeling now behind an
explicit consent switch; local models unchanged), held-out personal exam +
stock-anchored drift floor, young-mind gate on spontaneous recall. Speed
work measured honestly: per-call time/prime/error metrics, discovery
downshift (**per-call model time −28%** on the slowest tasks), per-call
silence window for hanging provider calls, `read_many` batch reads +
workspace briefing (not yet adopted by the flash model — stated plainly).
First sweep with every task's best repetition at 100/100; a grading
port-poisoning chain and a shell working-directory trap fixed. Full
detail: [the benchmark page](docs/benchmark-2026-08.md).

## 1.0.0 — 2026-08-29

The benchmark release. neo's harness now measures as a statistical tie with
Claude Code in delivery quality on a nine-task suite (897.3 vs **896.7** vs
OpenCode's 894.9 out of 900) — on a ~free flash model, ahead of the
same-model competitor. Full method, raw data and honest caveats:
[docs/benchmark-2026-08.md](docs/benchmark-2026-08.md).

* **Memory that measurably pays.** Seeded true facts cut a task's prompt
  tokens 24% and rescued a failing rep to 100; a mechanical end-of-run
  capsule made a warm continuation **twice as fast** (−38% tokens) with
  equal correctness. A 50-junk-memory pollution attack that leaked into
  the prompt through a single-stem overlap is sealed — hit-rate unchanged,
  precision and trap-silence up.
* **Tool errors become lessons.** A repeated error pattern is written to
  memory once and attached to the same error in future sessions
  ("[Memory] …"); known PowerShell traps are taught in the tool
  description *before* the first failure.
* **Two new delivery gates.** A written test file that was never run
  blocks the "done" claim (a red suite got shipped exactly this way), and
  negative requirements ("must reject", "must redirect") must be proven
  with a command — the PHP auth panel went 55.9 → 100 on this rule alone.
* Screenshot gallery: [docs/gallery](docs/gallery/README.md).

## 0.x — 2026-08-26 → 28 (pre-1.0, condensed)

Nine releases in three days, kept here as a digest; the git history has
every detail. Highlights in order: first public cut (memory graph, soul,
tools); automations as node graphs with live-lit steps and limited
self-repair; the local base rewriter (10.8M, byte-level TR/EN) shipping
in-product with the nightly fine-tune loop and its exam gate; session
titles written by the model; per-chat model pinning; viewer tabs; the
connectors directory; shell hardening (stdin, process-tree kill,
taught-first traps); whitespace-tolerant edits; the reasoning-effort cap
that took the hard tasks off the 900-second ceiling; and the release gate
that requires all benchmark tasks green on the build.
