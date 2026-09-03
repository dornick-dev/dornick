"""Know me: scheduling the personal fine-tuning loop from inside the product.

The training rig lives in a separate repo (neocp-base-model); the night
loop (harvest → label → fine-tune → exam gate → .dornick/taban.npz) is
there. This place only decides **when** it runs: the feature is switched
on from settings, the watcher thread polls every fifteen minutes and starts
the loop as a low-priority child process either when enough new memories
have accumulated or when a day has passed since the last run (smart
trigger, constants below).

Why not schtasks: with scheduling inside the product the user can switch it
on and off with a single toggle, the run's start/finish shows in the UI and
on a machine without the rig the feature stays quietly passive.

`son_kosu` is written when the run FINISHES: a run cut short (computer shut
down, process killed) must stay repeatable. The loop's own state
(watermark, threshold) is in its own store anyway — a half run loses no data.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FILE = "tanima.json"

# Where the training rig lives. Install layout first: if the package lives
# under <root>/src/dornick the rig is looked for in <root>/egitim (the
# Windows installer puts it there). Otherwise the developer path — and if
# that is missing too the feature is passive: the settings page shows a
# "not installed" note next to the toggle.
_INSTALL_SCRIPT = (Path(__file__).resolve().parents[2]
                   / "egitim" / "betikler" / "08_kisisel_dongu.py")
_DEVELOPER_SCRIPT = (Path("D:/Projects/ai/neocp-base-model")
                     / "betikler" / "08_kisisel_dongu.py")
LOOP_SCRIPT = _INSTALL_SCRIPT if _INSTALL_SCRIPT.exists() else _DEVELOPER_SCRIPT

# The loop's watermark: up to which memory was last harvested lives here.
# The new-memory count is measured against it; a missing file/field means
# an empty watermark — everything counts as new, the right behaviour on a
# first install.
WATERMARK = LOOP_SCRIPT.parents[1] / "veri" / "kisisel_durum.json"

# Question→term pairs distilled from the user: the raw material of personal
# training. Transfer and reset handle these two files together.
CORPUS = LOOP_SCRIPT.parents[1] / "veri" / "kisisel_korpus.jsonl"

# Smart trigger: a poll runs the loop via one of two paths.
#   (a) NEW_MEMORY_THRESHOLD memories accumulated since the watermark AND at
#       least MIN_GAP_HOURS passed since the last run — waiting for the night
#       while there is fresh material is pointless; the lower bound keeps the
#       loop from firing back-to-back on a busy chat day and keeping the
#       machine busy.
#   (b) FRESHNESS_HOURS passed since the last run — the daily refresh
#       insurance: even without accumulated memories, harvest + threshold
#       poll should run once a day.
NEW_MEMORY_THRESHOLD = 25
MIN_GAP_HOURS = 2
FRESHNESS_HOURS = 20

# The watcher's steps: the first look is delayed so it does not slow startup.
FIRST_WAIT_S = 60.0
POLL_S = 15 * 60.0

# Process is module-global: the server is threaded and the question "is it
# already running" must have a single true answer.
_proc: subprocess.Popen | None = None
_lock = threading.Lock()


def status(state_dir: Path) -> dict:
    try:
        d = json.loads((state_dir / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"on": False, "son_kosu": "", "learn_cloud_ok": False}
    return {"on": bool(d.get("on")), "son_kosu": str(d.get("son_kosu") or ""),
            # Privacy consent: explicit permission for labelling with the
            # hosted model. Normalised here and WRITTEN BACK so that
            # read-modify-write flows like `configure` do not wipe the flag.
            # Not put in config.json: settings._write_config rebuilds the
            # file from dataclasses and drops an unknown key on first save.
            "learn_cloud_ok": bool(d.get("learn_cloud_ok"))}


def configure(state_dir: Path, on: bool) -> None:
    d = status(state_dir)
    d["on"] = bool(on)
    (state_dir / FILE).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def set_cloud_consent(state_dir: Path, ok: bool) -> None:
    """Explicit permission for night labelling with the cloud model (privacy consent).

    The night loop (08_kisisel_dongu / personal_loop) reads this flag:
    memory text goes to the hosted endpoint only while this is on.
    """
    d = status(state_dir)
    d["learn_cloud_ok"] = bool(ok)
    (state_dir / FILE).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def hazir() -> bool:
    """Is the training rig installed on this machine?"""
    return LOOP_SCRIPT.exists()


def running() -> bool:
    return _proc is not None and _proc.poll() is None


def _new_memory_count(state_dir: Path) -> int:
    """Number of memories accumulated since the watermark (episodes excluded).

    The database is opened READ-ONLY (harvest/gate pattern): the watcher's
    job is to count, not to touch the agent's mind. An unreadable
    db/watermark counts as zero — the smart path stays quiet, the daily
    insurance still works.
    """
    db = state_dir / "mind" / "recall.db"
    if not db.exists():
        return 0
    watermark = ""
    try:
        watermark = str(json.loads(WATERMARK.read_text(encoding="utf-8")).get("son_created") or "")
    except (OSError, ValueError):
        pass
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            (n,) = con.execute(
                "SELECT COUNT(*) FROM node "
                "WHERE kind != 'episode' AND deleted = 0 AND created > ?",
                (watermark,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return 0
    return int(n)


def maybe_start(state_dir: Path, hub: Any, *, zorla: bool = False) -> str:
    """Starts the loop if the conditions hold. The return value is a REASON code.

        basladi      the run started
        kapali       the feature is off
        duzenek_yok  the training rig is not installed
        kosuyor      already running
        veri_yok     no new data (nothing to train on)
        ara_yok      the time/accumulation condition has not formed yet
        baslatilamadi the process could not be opened

    Returning a reason is deliberate: the "Train now" button was silently
    doing nothing. The truth was — the loop started and in under a second
    said "little new data: 0/50" and exited; the user saw nothing on screen.
    Now the UI can say why nothing happened.

    `zorla` skips only the TIME condition (the "run now" button); it does
    not skip the disabled feature, the missing rig, the running process or
    the lack of training data — opening a process with no data would be
    showing the user an empty "started".
    """
    global _proc
    with _lock:
        d = status(state_dir)
        if not d["on"]:
            return "kapali"
        if not hazir():
            return "duzenek_yok"
        if running():
            return "kosuyor"
        if zorla and _new_memory_count(state_dir) <= 0:
            return "veri_yok"
        if not zorla and d["son_kosu"]:
            try:
                last = datetime.fromisoformat(d["son_kosu"])
                elapsed = (datetime.now(timezone.utc) - last).total_seconds()
            except ValueError:
                elapsed = float("inf")  # a broken date must not block
            # Smart trigger: fresh material + short gap, or the daily insurance.
            if elapsed < FRESHNESS_HOURS * 3600 and not (
                elapsed >= MIN_GAP_HOURS * 3600
                and _new_memory_count(state_dir) >= NEW_MEMORY_THRESHOLD
            ):
                return "ara_yok"

        # Appended to the log file: the loop's own output accumulates here
        # and this is also where live verification looks.
        logfile = (state_dir / "tanima.log").open("a", encoding="utf-8")
        # Low priority + windowless: training must run unnoticed; fan noise
        # and a frozen UI are the exact opposite of "night learning".
        try:
            # Our own root is passed to the script explicitly: in the install
            # layout the developer constant inside 08 is invalid, the
            # .dornick/src/eval paths are derived from here. In the developer
            # layout the same path is the constant itself — behaviour unchanged.
            _proc = subprocess.Popen(
                [sys.executable or "py", str(LOOP_SCRIPT),
                 "--dornick", str(Path(state_dir).resolve().parent)],
                cwd=str(LOOP_SCRIPT.parents[1]),
                stdout=logfile, stderr=subprocess.STDOUT,
                creationflags=(subprocess.BELOW_NORMAL_PRIORITY_CLASS
                               | subprocess.CREATE_NO_WINDOW),
            )
        except OSError:
            logfile.close()
            return "baslatilamadi"
        proc = _proc

    hub.emit({"type": "tanima", "state": "basladi"})

    def watch() -> None:
        try:
            proc.wait()
        finally:
            logfile.close()
        # `son_kosu` on finish: a half-finished run can be retried on the
        # next poll.
        d2 = status(state_dir)
        d2["son_kosu"] = datetime.now(timezone.utc).isoformat()
        (state_dir / FILE).write_text(json.dumps(d2, ensure_ascii=False), encoding="utf-8")
        hub.emit({"type": "tanima", "state": "bitti"})

    threading.Thread(target=watch, daemon=True, name="dornick-tanima").start()
    return "basladi"


def reset(state_dir: Path) -> dict:
    """Returns Know-me to the base model; everything personal goes to a backup.

    Nothing deleted, things moved: .dornick/taban.npz plus the corpus +
    watermark in the training rig go under .dornick/yedek-<date>/tanima/.
    The base cache is dropped immediately so the assets/taban.npz shipped
    with the product starts talking without waiting for the 5-minute hot
    refresh.
    """
    if running():
        return {"ok": False, "error": "Eğitim şu an koşuyor — bitince sıfırla."}

    import shutil

    from .recall import writer

    backup = Path(state_dir) / f"yedek-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    moved: list[str] = []
    for source in (Path(state_dir) / "taban.npz", CORPUS, WATERMARK):
        if not source.is_file():
            continue
        target = backup / "tanima" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(source), str(target))
        except OSError as exc:
            return {"ok": False, "error": f"Taşınamadı ({source.name}): {exc}",
                    "tasinan": moved}
        moved.append(source.name)

    writer.reset()
    return {"ok": True, "tasinan": moved,
            "yedek": str(backup) if moved else ""}


def start_watcher(state_dir: Path, hub: Any) -> None:
    """Watcher: polls maybe_start in the background every fifteen minutes.

    The first look is delayed by a minute — startup is already loading the
    model, no point piling a training poll on top. Errors are swallowed:
    the watcher dying means the feature silently stopping and nobody would
    notice.
    """
    def spin() -> None:
        time.sleep(FIRST_WAIT_S)
        while True:
            try:
                maybe_start(state_dir, hub)
            except Exception:
                pass
            time.sleep(POLL_S)

    threading.Thread(target=spin, daemon=True, name="dornick-tanima-gozcu").start()
