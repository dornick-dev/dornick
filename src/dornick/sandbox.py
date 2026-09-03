"""Workshop and project: where the agent may write.

The rule is one sentence: **reading is free everywhere, writing only in the
workshop — plus the project the user explicitly chose.**

The reason for the distinction is practical. When asked to do something the
agent needs to be able to see everything on the computer — which file is
where, what it says. But what it produces (a script, a site, a report, its
own MCP) must not mix into the user's files. If a file is needed it gets
copied: `copy_in` exists exactly for this, the copy lands in the workshop and
the original is untouched.

Project mode is not an exception to this rule but its complement. When the
user wants work done in their own code ("fix this in that project"), copying
every file into the workshop makes the job impossible: a project is a tree,
not a file, and a copy of it is not the original. So when the user
EXPLICITLY picks a folder, that folder becomes writable too — **the choice
itself is the approval**. The workshop stays open in every case: Dornick's
own work keeps being written there and does not mix with the project.

The scope's limit must be stated honestly: this layer binds the **file
tools**. The shell is not bound — a command can write wherever it wants. The
shell's working directory is set to the workshop and the permission engine
holds the rest. A real prison is operating-system-level work (container,
AppContainer, seccomp) and heavier than this program's installation can
carry.

Path comparison goes through `resolve()`: `..`, symbolic links and Windows'
short names (`PROGRA~1`) can only be compared once resolved.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# The workshop's default name inside the workspace.
DEFAULT_DIR = "atolye"

# The recent-projects ledger (`.dornick/projeler.json`) and how many are kept.
PROJECTS_FILE = "projeler.json"
MAX_RECENT = 8

REFUSAL = (
    "Yazma yalnızca atölyende ve seçili projede serbest.\n"
    "Açık kökler: {roots}\n"
    "İstenen yol dışarıda: {path}\n"
    "Dışarıdaki bir dosya lazımsa `copy_in` ile atölyene kopyala; "
    "orijinali olduğu yerde kalır. Kullanıcı başka bir klasörde çalışmanı "
    "istiyorsa onu Ayarlar › Proje'den seçmeli — seçim bir onaydır ve "
    "senin verebileceğin bir karar değil."
)


class OutsideSandbox(Exception):
    """An attempt to write outside the open roots. The tool layer turns it into an error."""


# -- project root safety -------------------------------------------------
#
# Declaring a folder "writable" is a serious decision. Even if the user
# picks it, some roots are unacceptable: choosing `C:\` is the long way of
# saying "you may write anywhere", and the picker does not show what that
# means. This list is narrow and explicit: drive roots, operating-system
# folders and the user profile ITSELF (projects beneath it are free).

_DANGEROUS_NAMES = (
    "windows", "program files", "program files (x86)", "programdata",
    "system32", "syswow64", "$recycle.bin", "recovery",
    "/bin", "/sbin", "/usr", "/etc", "/var", "/lib", "/boot", "/dev", "/proc", "/sys",
)


def root_block(path: Path) -> str | None:
    """Can this folder be a project root? If not, says why.

    The returned text is shown directly to the user: "invalid" is not
    enough, it must say WHY it is invalid and what to do.
    """
    try:
        root = path.expanduser().resolve()
    except OSError:
        return "Bu yol çözümlenemedi."

    if not root.exists():
        return f"Böyle bir klasör yok: {root}"
    if not root.is_dir():
        return f"Bu bir klasör değil: {root}"

    # Drive/file-system root: `C:\` or `/`. If its parent is itself, it is a root.
    if root.parent == root:
        return (
            f"{root} bir sürücü kökü — proje olarak seçmek 'her yere yazabilirsin' "
            "demek olur. Üzerinde çalıştığın projenin kendi klasörünü seç."
        )

    flat = str(root).replace("\\", "/").lower()
    name = root.name.lower()
    for dangerous in _DANGEROUS_NAMES:
        if name == dangerous or flat == dangerous or flat.endswith("/" + dangerous.strip("/")):
            return (
                f"{root} bir işletim sistemi klasörü. Buraya yazmak sistemi "
                "bozabilir; projenin kendi klasörünü seç."
            )

    # The user profile ITSELF is too wide (Desktop, Documents, Downloads,
    # browser profiles all sit beneath it). A project folder beneath it is free.
    if (home := _home_dir()) is not None and root == home:
        return (
            f"{root} kullanıcı klasörünün kendisi — altındaki her şeyi (belgeler, "
            "masaüstü, indirilenler) yazılabilir yapardı. İçindeki proje "
            "klasörünü seç."
        )
    return None


def _home_dir() -> Path | None:
    try:
        return Path.home().resolve()
    except (OSError, RuntimeError):  # pragma: no cover - home may be undefined
        return None


def root_warning(path: Path, *, state_dir: Path | None = None) -> str:
    """Not a blocker, but cases that must be said. Empty string = nothing to say.

    A choice that covers Dornick's own source tree or its `.dornick` state
    is NOT BLOCKED: having Dornick fix its own code is a legitimate request
    and this repository is developed exactly that way. But we do not stay
    silent either — the user should choose knowing what is covered.
    """
    try:
        root = path.expanduser().resolve()
    except OSError:
        return ""

    notes: list[str] = []
    if state_dir is not None:
        try:
            state = state_dir.expanduser().resolve()
            if state == root or root in state.parents:
                notes.append(
                    "Dornick'in kendi durumu (.dornick: ayarlar, anılar, oturumlar) "
                    "bu klasörün altında — buraya yazmak Dornick'in hafızasına "
                    "dokunabilir."
                )
        except OSError:
            pass

    # The source tree: the package wherever this very file lives.
    try:
        source = Path(__file__).resolve().parent
        if source == root or root in source.parents:
            notes.append(
                "Dornick'in kendi kaynak kodu bu klasörün altında — kendi "
                "kodunu düzenletmek istiyorsan bu doğru; istemiyorsan daha "
                "dar bir klasör seç."
            )
    except OSError:  # pragma: no cover
        pass
    return " ".join(notes)


# -- recent-projects ledger ----------------------------------------------


def son_projeler(state_dir: Path) -> list[str]:
    """Project paths, most recently chosen first."""
    path = state_dir / PROJECTS_FILE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data if isinstance(x, str) and x.strip()][:MAX_RECENT]


def proje_hatirla(state_dir: Path, path: str) -> list[str]:
    """Moves the chosen project to the head of the ledger; drops duplicates, trims the list."""
    clean = (path or "").strip()
    if not clean:
        return son_projeler(state_dir)
    rest = [x for x in son_projeler(state_dir) if x.lower() != clean.lower()]
    updated = [clean, *rest][:MAX_RECENT]
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / PROJECTS_FILE).write_text(
            json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return updated


@dataclass(slots=True)
class Sandbox:
    root: Path
    enabled: bool = True
    # Writable roots OUTSIDE the workshop: the project the user chose.
    # Plural, because the concept is not bound to a single project; today
    # the UI gives one.
    open_roots: tuple[Path, ...] = ()
    # Cases that warrant a warning but are not blocked (see root_warning).
    note: str = ""

    @classmethod
    def open(
        cls,
        workspace: Path,
        directory: str = DEFAULT_DIR,
        *,
        enabled: bool = True,
        project: str = "",
        state_dir: Path | None = None,
    ) -> Sandbox:
        root = Path(directory).expanduser()
        if not root.is_absolute():
            root = workspace / root

        opened: list[Path] = []
        note = ""
        if (chosen := (project or "").strip()):
            candidate = Path(chosen).expanduser()
            if not candidate.is_absolute():
                candidate = workspace / candidate
            # An invalid project path must not make the program FAIL TO
            # START: the settings file may have been edited by hand or the
            # folder deleted. We fall back to the workshop silently; the
            # settings page says why.
            if root_block(candidate) is None:
                opened.append(candidate.resolve())
                note = root_warning(candidate, state_dir=state_dir)

        sandbox = cls(root=root.resolve(), enabled=enabled,
                      open_roots=tuple(opened), note=note)
        if enabled:
            sandbox.ensure()
        return sandbox

    @property
    def project(self) -> Path | None:
        """The chosen project root (if any). Today at most one."""
        return self.open_roots[0] if self.open_roots else None

    @property
    def roots(self) -> tuple[Path, ...]:
        """All roots where writing is free — the workshop always first."""
        return (self.root, *self.open_roots)

    def ensure(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    # -- boundary ------------------------------------------------------

    def contains(self, path: Path) -> bool:
        """Is the path inside one of the open roots?

        A path that does not exist must be answered correctly too: writing
        mostly targets a file that is not there yet. `Path.resolve()`
        resolves a non-existent path as well, so no separate path is needed.
        """
        try:
            resolved = path.expanduser().resolve()
        except OSError:  # on Windows a broken link can blow up here
            return False
        return any(resolved == root or root in resolved.parents for root in self.roots)

    def check(self, path: Path) -> Path:
        """Checks whether it is writable; if not, raises an explanatory error."""
        if not self.enabled:
            return path
        if not self.contains(path):
            raise OutsideSandbox(REFUSAL.format(
                roots=", ".join(str(r) for r in self.roots), path=path))
        return path

    def relative(self, path: Path) -> str:
        """The path relative to the nearest open root; the absolute form if under none."""
        try:
            resolved = path.resolve()
        except OSError:
            return str(path)
        for root in self.roots:
            try:
                return resolved.relative_to(root).as_posix()
            except ValueError:
                continue
        return str(resolved)

    # -- prompt --------------------------------------------------------

    def briefing(self) -> str:
        if not self.enabled:
            return ""

        workshop = (
            "Atölyen:\n"
            f"- Kendi klasörün: {self.root}\n"
            "- Dışarıdaki bir dosya lazımsa `copy_in` ile kopyala, "
            "orijinaline dokunma.\n"
            "- Burada istediğini kurabilirsin: her dilde proje (Python, Node, "
            ".NET, PHP...), site, veri çekici, kendi MCP sunucun. Ortamını da "
            "kendin kurarsın (venv, npm, ne gerekiyorsa). Proje başlatırken "
            "önce kendine bir alt klasör aç; hiyerarşi senin."
        )

        if (project := self.project) is None:
            return (
                workshop
                + "\n- Okuma her yerde serbest; **yazma yalnızca bu klasörde**.\n"
                f"- Göreli yol zaten buraya çözülüyor: `site/index.html` yaz, "
                f"`{self.root.name}/site/index.html` yazma."
            )

        # With a project chosen the order flips: the real work is in the
        # project, the workshop is for Dornick's own business. The model
        # must know which is which, or it leaves "its own experiments" in
        # the user's project.
        warning = f"\n- Dikkat: {self.note}" if self.note else ""
        return (
            "Nerede çalışıyorsun:\n"
            f"- **Çalışılan proje: {project}** — kullanıcının klasörü, yazma "
            "serbest. Kullanıcı bu klasörü Ayarlar › Proje'den bilerek seçti; "
            "asıl iş burada. Göreli yollar buraya çözülüyor.\n"
            f"- Dornick'in kendi atölyesi: {self.root} — kendi işlerin, "
            "denemelerin ve kullanıcının istemediği ara ürünler için. "
            "Projeye ait olmayan şeyleri buraya koy.\n"
            "- Okuma her yerde serbest; yazma yalnızca bu iki klasörde.\n"
            "- Projede çalışırken oranın kendi düzenine uy: var olan dosya "
            "yapısını, adlandırmayı ve araçları kullan; kendi kalıbını "
            "dayatma." + warning + "\n\n" + workshop
        )
