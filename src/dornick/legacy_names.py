"""One-time renames of files and folders that had Turkish names before 1.5.1.

Every entry here is a name the product WRITES to the user's disk. The
English name is the only one the code uses from now on; the old one is
adopted (renamed, not copied) the first time the new name is looked for and
found missing. Nothing is deleted and nothing is read twice: an install
that already carries the English names never sees this module do anything.

Names that are NOT here on purpose (the reasons are in the changelog):

* `.dornick/taban.npz` — written by the external training rig; renaming it
  here would break the rig's hot deploy.
* the training rig's own layout (`veri/`, `betikler/`, `ayarlar.py`) — a
  separate repository owns those names.
* keys inside JSON/JSONL files, SQLite columns and SSE events — the wire.
"""

from __future__ import annotations

from pathlib import Path

# Inside `.dornick` (the state folder): old file name -> new file name.
STATE_FILES: dict[str, str] = {
    "karar_ornekleri.json": "decision_exemplars.json",
    "mizac.json": "temperament.json",
    "kimlik.md": "identity.md",
    "oto_havuz.json": "auto_pool.json",
    "kancalar.json": "hooks.json",
    "fiyat.json": "prices.json",
    "filigran.json": "watermark.json",
    "ritim.json": "rhythm.json",
    "uyku_gunlugu.jsonl": "sleep_journal.jsonl",
    "tanima.json": "recognition.json",
    "projeler.json": "projects.json",
    "skills_onayli.json": "skills_approved.json",
    "uyku_borcu.json": "sleep_debt.json",
    "bakim.json": "maintenance.json",
    "gece.jsonl": "nights.jsonl",
    # folders inside .dornick: adopt() renames a folder like a file
    "gece": "nights",
    "yedek": "backups",
    "degisiklikler": "changes",
}

# Inside the workshop: old folder name -> new folder name.
WORKSHOP_DIRS: dict[str, str] = {
    "yetenekler": "skills",
    ".geri-donusum": ".recycle-bin",
}

# The workshop itself, inside the workspace.
LEGACY_WORKSHOP = "atolye"

# The installed training rig, next to `src/`.
LEGACY_RIG = "egitim"


def adopt(old: Path, new: Path) -> bool:
    """Renames `old` to `new` when `new` is missing and `old` exists.

    Returns True only when a rename happened. A locked or vanished `old`
    is not an error: the caller goes on with the (absent) new name and the
    product starts from scratch exactly as it would on a fresh install.
    """
    old, new = Path(old), Path(new)
    if new.exists() or not old.exists():
        return False
    try:
        new.parent.mkdir(parents=True, exist_ok=True)
        old.rename(new)
        return True
    except OSError:
        return False


def migrate_state(state_dir: Path | str) -> list[str]:
    """Adopts every legacy file inside `.dornick`; returns the new names taken."""
    base = Path(state_dir)
    if not base.is_dir():
        return []
    return [new for old, new in STATE_FILES.items() if adopt(base / old, base / new)]


def migrate_workshop(root: Path | str) -> list[str]:
    """Adopts the legacy folders inside the workshop; returns the new names taken."""
    base = Path(root)
    if not base.is_dir():
        return []
    return [new for old, new in WORKSHOP_DIRS.items() if adopt(base / old, base / new)]
