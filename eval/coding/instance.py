"""Isolated dornick instance: no window, just the server.

The runner gives every task its OWN dornick. The reason fits in one sentence:
a measurement must not pollute the user's real mind, workshop or sessions,
and tasks must not pollute each other. If the `servis.py` written in one
task is still sitting in the next task's workshop, what we measure is not
the agent — it is leftover files.

The isolation pattern (using the product's own boot path):

  * `desktop._boot` is called directly — NOT `desktop.run`. `run` opens a
    pywebview window and used `_kill_ghosts` to kill other dornick instances
    on the machine; a measurement must never close the user's open app.
  * The workspace is passed to `Config.load` as an EXPLICIT argument. The
    `DORNICK_WORKSPACE` environment variable is not used: that variable
    would pin the user's HOME pointer (`~/.dornick/home`) to a temp folder
    via `config._pin_home` — after the measurement, dornick's home would be a
    deleted tmp directory.
  * `DORNICK_STATE_DIR` is set only in this process's environment; it does
    not touch the home pointer but pulls shared caches (auto-model list,
    price table) into the temp folder too.
  * The port differs per run, and the browser port is shifted so it never
    collides with the user's open dornick.

Shutdown: one line on stdin (or EOF) triggers `_teardown` — no MCP
subprocesses or open files left behind.

Standalone use (for manual experiments):
    py eval/coding/instance.py --workspace C:\\tmp\\trial --port 8790
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import threading
from pathlib import Path

READY_PREFIX = "READY "


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="isolated dornick instance")
    parser.add_argument("--workspace", required=True,
                        help="workspace (home) directory")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    state = workspace / ".dornick"
    state.mkdir(parents=True, exist_ok=True)

    # Shared caches go to the temp folder too. The home pointer is NOT touched.
    os.environ["DORNICK_STATE_DIR"] = str(state)
    os.environ.pop("DORNICK_WORKSPACE", None)

    source = Path(__file__).resolve().parents[2] / "src"
    if source.is_dir():
        sys.path.insert(0, str(source))

    from dornick import desktop
    from dornick.config import Config

    # Explicit argument: `_resolve_workspace` does NOT pin it (see config.py).
    config = Config.load(workspace)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        runtime = loop.run_until_complete(desktop._boot(config, args.port, False))
    except Exception as exc:  # if boot blows up, the runner must see why
        print(f"BOOT-FAILED {type(exc).__name__}: {exc}", flush=True)
        return 1

    print(f"{READY_PREFIX}{runtime.url} session={runtime.session.id}", flush=True)

    def watchdog() -> None:
        """Clean shutdown when stdin closes or receives a line."""
        try:
            sys.stdin.readline()
        except Exception:
            pass
        # Benchmark-only sweep of DETACHED apps the agent started (e.g. a
        # service under test). In the product they deliberately outlive the
        # window; here a survivor holds its port and poisons the NEXT
        # grading pass ("port held by someone else — cannot measure", seen
        # twice on o2-service, 29.08). Tree-kill via the app ledger.
        try:
            from dornick import apps
            for pid in list(getattr(apps, "_PROCS", {})):
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True, timeout=10,
                ) if sys.platform == "win32" else os.kill(pid, 9)
        except Exception:
            pass
        try:
            desktop._teardown(loop, runtime)
        except Exception:
            pass
        # `_teardown` already queues the loop stop; if a thread hangs
        # anyway, the process must still exit.
        threading.Timer(8.0, lambda: os._exit(0)).start()

    threading.Thread(target=watchdog, daemon=True, name="dornick-eval-watchdog").start()

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
