"""Git ve GitHub — alt süreç, uydurma yok.

Sohbet çubuğu ve `git` aracı aynı yüzeyi kullanır: durum, fark, commit,
push/pull, GitHub'da repo açma, yayın. Ağ yalnızca `create_repo` /
`publish` sırasında ve yalnızca `gh` ya da bir token varken çıkar.
İkisi de yoksa öğretici hata — sahte yayın yok.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import ortam
from . import settings

DIFF_CAP = 200_000
LOG_N = 20

GH_TEACH = (
    "GitHub'da repo açılamadı: `gh` yok veya giriş yapılmamış, "
    "GITHUB_TOKEN / GH_TOKEN de yok. Ayarlar → Model (anahtarlar) içine "
    "GITHUB_TOKEN yaz veya terminalde `gh auth login`."
)


class GitError(Exception):
    """git/gh çağrısı başarısız. Mesajı kullanıcıya ve modele gider."""


def find_root(start: Path) -> Path | None:
    """`start` ve üstündeki ilk `.git` dizininin çalışma ağacı."""
    try:
        cur = start.expanduser().resolve()
    except OSError:
        return None
    if not cur.exists():
        return None
    for p in [cur, *cur.parents]:
        if (p / ".git").exists():
            return p
    return None


def repo_root(config: Any) -> Path | None:
    """Seçili proje, yoksa atölye — yukarı doğru `.git` aranır."""
    box = config.open_sandbox()
    if box.project is not None:
        found = find_root(box.project)
        if found is not None:
            return found
    return find_root(box.root)


def github_token(state_dir: Path | None = None) -> str:
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    if state_dir is not None:
        keys = settings.load_keys(state_dir)
        for key in ("GITHUB_TOKEN", "GH_TOKEN"):
            val = (keys.get(key) or "").strip()
            if val:
                return val
    return ""


def snapshot(config: Any) -> dict[str, Any]:
    """Çubuk için özet. Repo yoksa `present: false` — çubuk gizlenir."""
    root = repo_root(config)
    if root is None:
        return {"ok": True, "present": False}
    try:
        data = status(root, workspace=Path(config.workspace))
    except GitError as exc:
        return {"ok": False, "present": True, "error": str(exc)}
    return {"ok": True, "present": True, **data}


def status(root: Path, *, workspace: Path | None = None) -> dict[str, Any]:
    _need_git()
    root = root.resolve()
    if find_root(root) != root and not (root / ".git").exists():
        raise GitError(f"Git deposu değil: {root}")

    branch = _git(root, "branch", "--show-current", check=False).stdout.strip()
    if not branch:
        ref = _git(root, "rev-parse", "--abbrev-ref", "HEAD", check=False)
        branch = (ref.stdout.strip() if ref.returncode == 0 else "") or "HEAD"

    remote = _git(root, "remote", "get-url", "origin", check=False).stdout.strip()
    ahead, behind = _ahead_behind(root)

    files, plus, minus = _files(root, workspace=workspace)
    return {
        "root": str(root),
        "name": root.name,
        "branch": branch,
        "remote": remote,
        "ahead": ahead,
        "behind": behind,
        "files": files,
        "plus": plus,
        "minus": minus,
        "dirty": bool(files),
    }


def diff(root: Path, path: str | None = None) -> dict[str, Any]:
    """Bir dosyanın (veya hepsinin) eski/yeni gövdesi — Viewer hunk için."""
    _need_git()
    root = root.resolve()
    if path:
        rel = _rel(root, path)
        return {"ok": True, **_one_diff(root, rel)}
    snap = status(root)
    rows = []
    for row in snap["files"]:
        rows.append(_one_diff(root, row["path"]))
    return {"ok": True, "files": rows, "plus": snap["plus"], "minus": snap["minus"]}


def log(root: Path, n: int = LOG_N) -> list[dict[str, str]]:
    _need_git()
    n = max(1, min(int(n), 50))
    fmt = "%h%x09%s%x09%an%x09%ar"
    r = _git(root, "log", f"-n{n}", f"--format={fmt}", check=False)
    if r.returncode != 0:
        return []
    out: list[dict[str, str]] = []
    for line in r.stdout.splitlines():
        parts = line.split("\t", 3)
        if len(parts) < 4:
            continue
        out.append({"hash": parts[0], "subject": parts[1],
                    "author": parts[2], "when": parts[3]})
    return out


def init(path: Path) -> dict[str, Any]:
    _need_git()
    path = path.expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    if (path / ".git").exists() or find_root(path) == path:
        return status(path)
    _git(path, "init")
    return status(path)


def commit(root: Path, message: str, paths: list[str] | None = None) -> dict[str, Any]:
    _need_git()
    msg = (message or "").strip()
    if not msg:
        raise GitError("Commit mesajı boş olamaz.")
    root = root.resolve()
    if paths:
        for p in paths:
            _git(root, "add", "--", _rel(root, p))
    else:
        _git(root, "add", "-A")
    _git(root, "commit", "-m", msg)
    return status(root)


def push(root: Path) -> dict[str, Any]:
    _need_git()
    root = root.resolve()
    upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name",
                    "@{u}", check=False)
    if upstream.returncode != 0:
        remote = _git(root, "remote", "get-url", "origin", check=False).stdout.strip()
        if not remote:
            raise GitError(
                "Uzak depo yok. Önce `publish` veya `create_repo` ile "
                "GitHub'da aç, sonra push."
            )
        _git(root, "push", "-u", "origin", "HEAD", timeout=120)
    else:
        _git(root, "push", timeout=120)
    return status(root)


def pull(root: Path) -> dict[str, Any]:
    _need_git()
    _git(root.resolve(), "pull", "--ff-only", timeout=120)
    return status(root.resolve())


def create_repo(
    name: str,
    *,
    private: bool = True,
    source: Path | None = None,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """GitHub'da repo açar. `gh` (girişliyse), yoksa token; ikisi de yoksa öğretir."""
    ad = (name or "").strip()
    if not ad:
        raise GitError("Repo adı boş olamaz.")
    if any(c in ad for c in " /\\"):
        raise GitError(f"Geçersiz repo adı: {ad!r}")

    src = source.resolve() if source is not None else None
    if src is not None and not (src / ".git").exists():
        init(src)

    if _gh_ready():
        return _create_via_gh(ad, private=private, source=src)

    token = github_token(state_dir)
    if not token:
        raise GitError(GH_TEACH)
    return _create_via_api(ad, private=private, source=src, token=token)


def publish(
    root: Path,
    *,
    name: str = "",
    private: bool = True,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """Remote yoksa GitHub'da aç + `git push -u`."""
    _need_git()
    root = root.resolve()
    remote = _git(root, "remote", "get-url", "origin", check=False).stdout.strip()
    if not remote:
        ad = (name or "").strip() or root.name
        created = create_repo(ad, private=private, source=root, state_dir=state_dir)
        remote = str(created.get("remote") or "")
        if not remote:
            # gh --source zaten origin eklemiş olabilir
            remote = _git(root, "remote", "get-url", "origin",
                          check=False).stdout.strip()
        if not remote:
            raise GitError("Uzak depo eklenemedi.")
    _git(root, "push", "-u", "origin", "HEAD", timeout=120)
    return status(root)


# -- iç iş -------------------------------------------------------------


def _need_git() -> None:
    if not shutil.which("git"):
        raise GitError("Bu makinede `git` yok. Git'i kurup PATH'e ekle.")


def _gh_ready() -> bool:
    if not shutil.which("gh"):
        return False
    try:
        r = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=8, **ortam.sessiz_bayraklar(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def _git(
    root: Path,
    *args: str,
    timeout: int = 30,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, **ortam.sessiz_bayraklar(),
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {' '.join(args)} zaman aşımı ({timeout}s)") from exc
    except OSError as exc:
        raise GitError(f"git çalışmadı: {exc}") from exc
    if check and r.returncode != 0:
        err = (r.stderr or r.stdout or "git hata").strip()[:800]
        raise GitError(err)
    return r


def _rel(root: Path, path: str) -> str:
    raw = (path or "").replace("\\", "/").strip()
    if not raw:
        raise GitError("Dosya yolu boş.")
    target = Path(raw)
    if not target.is_absolute():
        target = root / target
    try:
        rel = target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise GitError(f"Dosya depo dışında: {path}") from exc
    return rel.as_posix()


def _ahead_behind(root: Path) -> tuple[int, int]:
    r = _git(root, "rev-list", "--left-right", "--count", "@{u}...HEAD",
             check=False)
    if r.returncode != 0:
        return 0, 0
    parts = r.stdout.strip().split()
    if len(parts) != 2:
        return 0, 0
    try:
        return int(parts[1]), int(parts[0])  # ahead, behind
    except ValueError:
        return 0, 0


def _files(root: Path, *, workspace: Path | None = None) -> tuple[list[dict[str, Any]], int, int]:
    porcelain = _git(root, "status", "--porcelain=v1", "-uall")
    counts = _numstat(root)
    rows: list[dict[str, Any]] = []
    plus = minus = 0
    seen: set[str] = set()
    for line in porcelain.stdout.splitlines():
        if len(line) < 4:
            continue
        code, raw = line[:2], line[3:]
        rel = raw.split(" -> ", 1)[-1].replace("\\", "/").strip()
        if not rel or rel in seen:
            continue
        seen.add(rel)
        mark = _mark(code)
        p, m = counts.get(rel, (0, 0))
        if mark == "?" and rel not in counts:
            p, m = _untracked_stat(root, rel)
        plus += p
        minus += m
        item: dict[str, Any] = {
            "path": rel,
            "status": mark,
            "plus": p,
            "minus": m,
        }
        if workspace is not None:
            try:
                full = (root / rel).resolve()
                item["open"] = full.relative_to(workspace.resolve()).as_posix()
            except ValueError:
                pass
        rows.append(item)
    return rows, plus, minus


def _mark(code: str) -> str:
    a, b = (code + "  ")[:2]
    if a == "?" or b == "?":
        return "?"
    if "R" in code:
        return "R"
    if a == "A" or b == "A":
        return "A"
    if a == "D" or b == "D":
        return "D"
    return "M"


def _numstat(root: Path) -> dict[str, tuple[int, int]]:
    has_head = _git(root, "rev-parse", "--verify", "HEAD", check=False)
    args = ["diff", "--numstat", "HEAD"] if has_head.returncode == 0 else [
        "diff", "--numstat", "--cached",
    ]
    r = _git(root, *args, check=False)
    out: dict[str, tuple[int, int]] = {}
    for line in r.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        rel = parts[2].replace("\\", "/")
        try:
            p = 0 if parts[0] == "-" else int(parts[0])
            m = 0 if parts[1] == "-" else int(parts[1])
        except ValueError:
            continue
        out[rel] = (p, m)
    return out


def _untracked_stat(root: Path, rel: str) -> tuple[int, int]:
    target = root / rel
    try:
        if not target.is_file() or target.stat().st_size > DIFF_CAP:
            return (1 if target.exists() else 0, 0)
        data = target.read_bytes()
    except OSError:
        return 0, 0
    if b"\0" in data[:8192]:
        return 1, 0
    text = data.decode("utf-8", errors="replace")
    n = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
    return n, 0


def _one_diff(root: Path, rel: str) -> dict[str, Any]:
    old, new, binary = _sides(root, rel)
    plus = minus = 0
    if not binary:
        old_l = old.splitlines()
        new_l = new.splitlines()
        # Kabaca: ortak önek/sonek sonrası kalan satırlar.
        pre = 0
        while pre < len(old_l) and pre < len(new_l) and old_l[pre] == new_l[pre]:
            pre += 1
        post = 0
        while (post < len(old_l) - pre and post < len(new_l) - pre
               and old_l[len(old_l) - 1 - post] == new_l[len(new_l) - 1 - post]):
            post += 1
        minus = max(0, len(old_l) - pre - post)
        plus = max(0, len(new_l) - pre - post)
    mark = "?" if not old and new else "D" if old and not new else "M"
    return {
        "path": rel,
        "status": mark,
        "plus": plus,
        "minus": minus,
        "binary": binary,
        "old": old,
        "new": new,
    }


def _sides(root: Path, rel: str) -> tuple[str, str, bool]:
    working = root / rel
    new_b = b""
    exists = working.is_file()
    if exists:
        try:
            if working.stat().st_size > DIFF_CAP:
                return "", "", True
            new_b = working.read_bytes()
        except OSError:
            new_b = b""
    if exists and b"\0" in new_b[:8192]:
        return "", "", True

    old_r = _git(root, "show", f"HEAD:{rel}", check=False)
    old_b = old_r.stdout.encode("utf-8", errors="replace") if old_r.returncode == 0 else b""
    if old_b and b"\0" in old_b[:8192]:
        return "", "", True

    old = old_b.decode("utf-8", errors="replace") if old_r.returncode == 0 else ""
    new = new_b.decode("utf-8", errors="replace") if exists else ""
    if len(old) > DIFF_CAP:
        old = old[:DIFF_CAP]
    if len(new) > DIFF_CAP:
        new = new[:DIFF_CAP]
    return old, new, False


def _create_via_gh(name: str, *, private: bool, source: Path | None) -> dict[str, Any]:
    cmd = ["gh", "repo", "create", name, "--private" if private else "--public"]
    if source is not None:
        cmd.extend(["--source", str(source), "--remote", "origin"])
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, **ortam.sessiz_bayraklar(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"gh çalışmadı: {exc}") from exc
    if r.returncode != 0:
        raise GitError((r.stderr or r.stdout or "gh hata").strip()[:800])
    remote = ""
    if source is not None:
        remote = _git(source, "remote", "get-url", "origin", check=False).stdout.strip()
    url = (r.stdout or "").strip().splitlines()[-1] if r.stdout else ""
    return {"ok": True, "name": name, "private": private, "remote": remote or url,
            "via": "gh"}


def _create_via_api(
    name: str, *, private: bool, source: Path | None, token: str,
) -> dict[str, Any]:
    body = json.dumps({"name": name, "private": bool(private)}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/user/repos",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "neocp",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise GitError(f"GitHub API {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise GitError(f"GitHub'a ulaşılamadı: {exc}") from exc

    clone = str(data.get("clone_url") or data.get("html_url") or "")
    if source is not None and clone:
        have = _git(source, "remote", "get-url", "origin", check=False)
        if have.returncode != 0:
            _git(source, "remote", "add", "origin", clone)
    return {
        "ok": True,
        "name": name,
        "private": private,
        "remote": clone,
        "via": "token",
        "html_url": str(data.get("html_url") or ""),
    }
