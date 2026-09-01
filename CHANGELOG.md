# Changelog

## 1.3.9 - 2026-09-01

Public-facing polish for the single current release:

* README: release/license/platform badges; honest notes that the project
  is **not on PyPI** (install from a clone or the installer) and that the
  unsigned installer triggers the **Windows SmartScreen "unknown
  publisher"** warning (expected; auditable/rebuildable from
  `installer/`); fixed a duplicated screenshot with a wrong caption and a
  dangling sentence; light-theme automation screenshot wired in. Turkish
  note added to the eval README explaining the frozen Turkish seed
  fixtures.
* A small version badge now sits at the bottom of the sidebar, so the
  installed version is visible without hunting.
* **Fixed: helpers spawned on a different model were silently reverted
  to the parent's model on their first turn.** The pending-model-swap
  hook (new in the previous commit) runs before every model call; the
  child-side handler adopted the parent client unconditionally. It now
  adopts only when the parent's client has actually changed - the task
  tool's per-helper model routing works again (caught by the test
  suite once it was re-pointed at this tree).
* An oversized `max_tokens` is clamped to the window instead of refused,
  matching the new auto-adopted model caps.
* All pre-1.3.9 releases and tags were removed at the maintainer's
  request - this is the single current build.

## 1.3.8 - 2026-08-31

The final batch of the marathon day - every item a live request:

* **Panels resize in both directions.** The right column's drag cap was
  420 px - exactly its default width, so it could only shrink. The cap is
  now half the window.
* **Start a conversation in a folder.** A folder button next to "New
  conversation" opens a mini browser (drives -> folders); "Start here"
  opens a fresh chat with that working folder applied - like picking a
  workspace in Claude Code.
* **The git bar lives even without a repo.** It now shows the working
  folder with a one-click "Create repo" (git init), and clicking the
  folder name opens it in Explorer - the missing "go to the project
  folder from the chat" path.
* **The task mirror docks to the right panel** (it used to float over
  the chat column *behind* the text) and sits above every surface.
* **Half-done orchestra channels can be cancelled** - next to "Continue"
  there is now "Cancel", persisted so a dismissed orphan never comes
  back at the next launch.
* **"Thought" opens in one click.** Clicking the sealed thinking header
  used to reveal only a collapsed one-line step ("just a line appears");
  it now expands straight into the full reasoning.
* pyproject BOM introduced by a PowerShell write in 1.3.7 removed.

## 1.3.7 - 2026-08-31

* **No more phantom horizontal scrollbar under the chat.** The strip's
  second line (thinking label) had a 100% flex basis plus a 16 px left
  margin, overflowing the column by 16 px in narrow layouts - found by
  resizing the real window edge-by-edge in the deepened native tour.
  Also verified natively in that pass: the 900 px window minimum, the
  1100 px drawer band, maximize, and the live strip + terminal mirror
  during a running task.

## 1.3.6 â€” 2026-08-31

Findings from the first real mouse-and-keyboard tour of the installed
package (driven live on a desktop, every click verified):

* **Clicking anywhere in the composer focuses the input.** Clicking the
  box's empty area gave no focus, so a following Ctrl+V vanished â€” the
  missing half of "paste doesn't work".
* **Right-click clipboard menu.** pywebview disables WebView2's default
  context menu outside debug mode, so copy/paste had no menu at all.
  dornick now ships its own: Copy / Cut / Paste / Select all on inputs and
  selected text, with clipboard access over the pywebview bridge (no
  browser permission wall) and a `navigator.clipboard` fallback.
* **Control glow.** While dornick drives the hand/screen tools the window
  edge pulses â€” you can tell at a glance that it is using the computer.
* Caret honesty from the previous batch (blink only while text actually
  streams) ships in this installer.

## 1.3.5 â€” 2026-08-31

* **The goal ledger no longer hijacks the conversation.** The bare
  "active goals" note injected into the chat read like an instruction to
  a small model â€” asked to just say "hi", it would answer by discussing a
  ledger item instead. The note (and the soul's goal block) now carries a
  one-line precedence frame: the ledger is a reminder, the user's last
  word sets the agenda. Reproduced live before the fix and verified
  after: same setup now answers exactly "selam", zero goal chatter.
* **Context tools moved into the title bar.** The floating icon pill
  (voice, mic, viewer, orchestra, camera, â‹®) hovered over the chat text;
  it now lives in the title bar next to the window controls, stays
  visible in full-screen viewer, and a narrow-window rule keeps the bar
  from crowding below 700 px.
* **The ambient brain no longer writes over the chat.** The colour key
  and branch name labels drew behind the conversation and produced
  unreadable layered text; in ambient mode they are gone â€” names appear
  on hover, while a branch is in use, or in the panel/lens where the
  brain is the front surface. Panel branch rows are now an accordion, so
  an opened branch always fits above the panel footer instead of
  clipping below it.
* **The running thought box is readable.** Clicking it toggles the full
  reasoning so far (previously only the finished summary was clickable),
  and its inner scroll no longer yanks to the bottom while you are
  reading. Clicking a work-strip header with an empty body is no longer
  a dead toggle, and opening a strip scrolls the detail into view.
* **Orientation during long answers.** When you scroll away while the
  model streams, the jump chip now carries the live state ("Writing Â·
  â†“ 3 new") so one click returns you to the live edge.
* **Right-click menus were silently dead.** `menu.js` was loaded by the
  page but missing from the server's static allowlist (404). Added â€” and
  a regression test now asserts every script the page references is
  actually served. A second new test scans the whole tree for provider
  API-key patterns on every run.
* **Tool groups now read like a transcript.** When the model narrates
  between tools, the finished step cluster seals into its own clickable
  summary line ("1 command Â· echo alpha Â· 6 s â€º") and later tools open a
  fresh cluster below the text â€” the text / tools / text rhythm, each
  group expanding from its own row. Detail wells grew from ~200 px
  mini-windows to half-screen panes.
* **Copy and select work in the app again.** The desktop window was
  created without `text_select` â€” pywebview's default silently disables
  text selection, so generated answers could not be copied in the
  installed app (invisible in browser preview). Both windows fixed.
* **Chats are named immediately.** The title call now fires in parallel
  with the run's start instead of after it ends, and the sidebar polls
  every 5 s while a chat is running â€” the name lands within seconds.
* **App stop is honest.** Stop now flips the button to "Stoppingâ€¦"
  instantly and re-polls in a burst, so card, badge and open detail
  reflect the real process state within a couple of seconds.
* **Brain panel usability.** Branch rows clamp above the composer (they
  were sliding beneath it and becoming unclickable in small windows) and
  behave as an accordion so an opened branch always fits.
* **Reuse before rebuild.** A new standing principle in the system
  prompt: read a value through the registered device / running app /
  existing skill that already carries it instead of writing fresh
  scripts, and mint a skill unprompted when the same kind of request
  keeps recurring.


## 1.3.4 â€” 2026-08-31

Session-hygiene batch from a live multi-chat transcript â€” every item
reproduced against a running instance before and after the fix:

* **Joining a running chat showed nothing.** After a page reload or a
  sidebar switch into a busy session, the live work strip was built
  before the transcript and stranded at the top â€” the user saw a stop
  button and "running" but no living indicator. The strip now re-docks
  to the end of the flow after the transcript loads (verified live: strip
  visible at the bottom, ticking, honest label).
* **"Loading modelâ€¦" lied mid-run.** The waiting banner now appears only
  while the turn has produced nothing at all, and reads "Waiting for the
  modelâ€¦" â€” once text, thinking, or a tool starts, the real state speaks.
* **"Regenerate" piled up under every interim note.** The button now
  lives only under the last assistant bubble, and its label no longer
  leaks into copied conversations.
* **Chats bled into each other.** The goal ledger was mind-global: a
  goal opened in one chat resurfaced in another (the agent would close a
  PDF task by discussing an unrelated home-automation goal, and the
  acceptance gate nagged about foreign items). Goals are now scoped to
  their session everywhere the loop reads them â€” soul, digest notes,
  acceptance gate, panel; the brain graph still sees all of them.
* **Sessions listed as "e" or "b" forever.** Two roots: a stray one-key
  first message anchored the derived title, and the model-generated
  title path gave up forever after one failed attempt while accepting
  single-letter junk as a permanent name. Derived titles now skip
  one-letter keystrokes, generated titles must be real words (4-60
  chars), and the generator retries across the first few exchanges.


## 1.3.3 â€” 2026-08-31

Interface trio from live complaints, each reproduced with hit-testing
before the fix and verified clickable after:

* **"Thinking" details would not open on click.** Root cause: the desk
  auto-opens the viewer at startup, and between 861-1160 px the sidebar +
  viewer + chat cannot share the window â€” the work strip slid under the
  viewer's tab bar and real clicks landed there. The drawer band now
  covers the full 861-1160 range, and opening a right surface in that
  band folds the sidebar automatically.
* **The Tasks panel floated over the page from the left** (even starting
  off-screen). It now docks to the right edge like the viewer.
* **App running/stopped state needed a page refresh.** The Start/Stop
  button is now a single dynamic control that reflects the state at
  click time, and the open project view refreshes with the existing 4 s
  poll â€” start, stop and open-in-browser all reflect without a reload.


## 1.3.2 â€” 2026-08-31

Responsive repair, driven by live screenshots and programmatic overflow
measurement at 375/620/890/1020 px:

* **861-1020 px band**: sidebar + viewer + chat no longer fight over a
  window they cannot share â€” with a right panel open the sidebar becomes
  a floating drawer instead of reserving width (the "leaking letters"
  screen is gone; measured: zero horizontal overflow).
* **<= 860 px**: opening the viewer now takes the full surface instead of
  squeezing the chat (at 375 px the chat was left 88 px wide).
* **<= 620 px**: the composer stretches nearly full width (273 -> 355 px
  on a phone); the camera deck follows suit.
* **New setting â€” "Brain takes the stage"**: when off, the brain stays in
  the side panel and the centre scene dims, so text is never covered by
  the visualisation. Stored per browser; the default keeps today's look.


## 1.3.1 â€” 2026-08-31

Packaging completeness pass â€” nothing to install by hand, ever:

* An import sweep with the installer's own embedded Python now proves
  every third-party package the product touches is bundled (PDF, vision,
  audio, tray, browser â€” 19/19; `ultralytics` is deliberately the
  developer-only CUDA path, the shipped path is ONNX).
* The YOLO weight (`yolov8n.onnx`) ships inside the camera component:
  the first camera glance no longer downloads anything and works offline.
* Plus the owner's laptop batch: consistent launcher environment,
  AppUserModelID for proper taskbar identity, Windows toast
  notifications, speech-recognition and audio-decode refinements,
  PNG logo support, camera-handling optimisations.


## 1.3.0 â€” 2026-08-30

**The camera stage.** Built on a branch, tried live on a laptop, then
merged â€” with substantial work contributed directly by the project owner.

* **Camera watch area.** A deck lists the built-in webcam and any IP/RTSP
  cameras you add; tiles refresh with fresh frames (the camera opens per
  frame and closes â€” nothing stays recording). A status icon up top shows
  the truth at a glance: slashed when the camera master switch is off
  (click to enable), and the active mode when on.
* **Local vision (YOLO).** With a capable NVIDIA GPU, a local yolov8n
  model analyses frames on-device; without one, the LLM takes snapshots
  on demand. Motion frames never reach a hosted model without an explicit
  consent switch â€” same privacy pattern as the night school.
* **A real `camera` tool** for the model: list cameras, take 1-4
  snapshots (permission-gated â€” the model cannot open your camera on its
  own), see them, answer.
* **Voice & hearing controls** reworked: power toggles with live status,
  a hearing sync that follows configuration, echo handling improvements.
* **Listening latency fixed** (live complaint: 10-20 s behind on a weak
  laptop): models warm in the background at startup so the first sentence
  no longer pays the load cost, and a self-measuring downshift drops the
  recogniser one size (small â†’ base) if CPU decoding repeatedly lags
  behind the audio â€” session-only, your setting is untouched.
* **A `git` tool** (status/commit/push and friends) so the agent stops
  shelling out for version control.


## 1.2.0 â€” 2026-08-29

**Parallel sessions.** Every session now runs on its own lane â€” its own
agent, queue and pump. Starting a new chat no longer waits for the running
turn: the old turn finishes in the background, the sidebar badges every
running chat, and a notice arrives when a background chat completes.
Background lane events never leak into the active view (approvals
excepted); the model client is shared per endpoint so a local server is
never double-loaded. Session switching also stopped dragging finished
helper channels into the new chat.

UI feedback batch from live use:

* Code blocks follow the theme â€” light theme gets a light code well with
  its own syntax palette (the black-on-cream patch is gone).
* The status line is modeled, not decorative: "Reasoning" while the
  reasoning channel streams, "Writing" while the answer streams,
  "Thinking" before anything flows â€” labels no longer rotate randomly,
  and tool verbs are deterministic.
* Plan cards show live step progress (âœ“ done / â–¸ in progress / â—‹ waiting)
  driven by a new `step` action on the plan tool; approved plans keep
  their place with decision buttons hidden. The plan reflex threshold was
  raised so small tasks start immediately instead of drawing a plan.
* File links in chat act by type (download archives, open PDF/media,
  view code); decided earlier in 1.1.1, now with the plan-card and
  status fixes on top.


## 1.1.1 â€” 2026-08-29

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
  charts, diagrams, screenshots and pages as evidence â€” the identity now
  carries one rule for when: only if the visual shows at a glance what
  text cannot. Text is the default; no decorative charts.


## 1.1.0 â€” 2026-08-29

Review hardening. Night-school privacy gate (hosted labeling now behind an
explicit consent switch; local models unchanged), held-out personal exam +
stock-anchored drift floor, young-mind gate on spontaneous recall. Speed
work measured honestly: per-call time/prime/error metrics, discovery
downshift (**per-call model time âˆ’28%** on the slowest tasks), per-call
silence window for hanging provider calls, `read_many` batch reads +
workspace briefing (not yet adopted by the flash model â€” stated plainly).
First sweep with every task's best repetition at 100/100; a grading
port-poisoning chain and a shell working-directory trap fixed. Full
detail: [the benchmark page](docs/benchmark-2026-08.md).

## 1.0.0 â€” 2026-08-29

The benchmark release. dornick's harness now measures as a statistical tie with
Claude Code in delivery quality on a nine-task suite (897.3 vs **896.7** vs
OpenCode's 894.9 out of 900) â€” on a ~free flash model, ahead of the
same-model competitor. Full method, raw data and honest caveats:
[docs/benchmark-2026-08.md](docs/benchmark-2026-08.md).

* **Memory that measurably pays.** Seeded true facts cut a task's prompt
  tokens 24% and rescued a failing rep to 100; a mechanical end-of-run
  capsule made a warm continuation **twice as fast** (âˆ’38% tokens) with
  equal correctness. A 50-junk-memory pollution attack that leaked into
  the prompt through a single-stem overlap is sealed â€” hit-rate unchanged,
  precision and trap-silence up.
* **Tool errors become lessons.** A repeated error pattern is written to
  memory once and attached to the same error in future sessions
  ("[Memory] â€¦"); known PowerShell traps are taught in the tool
  description *before* the first failure.
* **Two new delivery gates.** A written test file that was never run
  blocks the "done" claim (a red suite got shipped exactly this way), and
  negative requirements ("must reject", "must redirect") must be proven
  with a command â€” the PHP auth panel went 55.9 â†’ 100 on this rule alone.
* Screenshot gallery: [docs/gallery](docs/gallery/README.md).

## 0.x â€” 2026-08-26 â†’ 28 (pre-1.0, condensed)

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

