"""z2 — hard/PHP: a login-guarded mini web panel.

This task is why the rig exists. For a panel, "the page opened" means the
page actually works AFTER the user LOGS IN — and that is exactly where we
got burned: pretty login screen, empty or fatally broken interior.
`php -S` happily serves a Fatal error with a 200.

So "works" is bound to three layers (`grading.page_healthy`):
  1. HTTP 200,
  2. a genuinely non-empty body (an empty template does not count),
  3. no PHP crash trail in the body (Fatal/Parse/Warning/Undefined).

Measurement uses a cookie-aware client: first the unauthenticated access
is tried to confirm the guard exists, then it logs in and requests the
same pages again.
"""

from __future__ import annotations

import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import grading  # noqa: E402
from grading import Axis, Tally  # noqa: E402

TITLE = "Login-guarded mini admin panel"
DIFFICULTY = "hard"
LANGUAGE = "php"
CRITICAL = ("giris", "oturum")
PORT = 8098
PAGES = ("ozet.php", "kullanicilar.php", "ayarlar.php")
USER, PASSWORD = "admin", "1234"


def _free_port(base: int = PORT) -> int | None:
    """A free port for the measurement.

    The 8098 in the brief is NOT fixed: we boot the server ourselves
    (`php -S ... -t dir`), the port is our choice. Measured wound: the
    agent had left its own trial `php -S` running, 8098 was held, and both
    carrier axes went "unmeasurable" at once — whether the panel actually
    worked was never learned. Sliding to a free port decouples the
    measurement from the agent's leftovers.
    """
    for port in range(base, base + 60):
        if grading.port_free(port):
            return port
    return None


def _docroot(root: Path) -> Path | None:
    """The server's document root: wherever index.php lives."""
    entry = grading.find(root, "index.php")
    return entry.parent if entry else None


def _field_names(body: str) -> tuple[str, str]:
    """Extract the login form's username and password field names.

    The agent may say `kullanici`/`username`/`user`; nothing is dictated —
    we read the form and use whatever it says. Fallbacks are the common
    names.
    """
    user_name = pass_name = ""
    for m in re.finditer(r"<input\b[^>]*>", body, re.IGNORECASE):
        tag = m.group(0)
        name = re.search(r"name\s*=\s*['\"]([^'\"]+)['\"]", tag, re.IGNORECASE)
        kind = re.search(r"type\s*=\s*['\"]([^'\"]+)['\"]", tag, re.IGNORECASE)
        if not name:
            continue
        if kind and kind.group(1).lower() == "password":
            pass_name = pass_name or name.group(1)
        elif not kind or kind.group(1).lower() in ("text", "email", ""):
            user_name = user_name or name.group(1)
    return user_name or "kullanici", pass_name or "sifre"


def _target(body: str) -> str:
    """The login form's `action`. Empty means the page itself.

    Not dictated: the form may post to `giris.php` or to itself. We read
    the page and post wherever it says — that is what a browser does.
    """
    m = re.search(r"<form\b[^>]*action\s*=\s*['\"]([^'\"]*)['\"]",
                  body, re.IGNORECASE)
    path = (m.group(1).strip() if m else "").split("?")[0]
    if not path or path in ("#", "."):
        return "index.php"
    return path.lstrip("/")


def _log_in(b: grading.Browser, base: str, form: str,
            password: str) -> grading.Response:
    user_name, pass_name = _field_names(form)
    data = urllib.parse.urlencode({user_name: USER, pass_name: password,
                                   "giris": "1", "submit": "1"}).encode()
    return b.request(f"{base}/{_target(form)}", data=data)


def _guarded(r: grading.Response) -> bool:
    """Was the unauthenticated request actually blocked?

    Accepted: a redirect (3xx), 401/403, or a 200 whose content is the
    login form. Rejected: 200 + panel content (no guard) and 500 (not a
    guard, an accident).
    """
    if r.code in (301, 302, 303, 307, 308, 401, 403):
        return True
    if r.code != 200:
        return False
    return bool(re.search(r"type\s*=\s*['\"]password['\"]", r.body,
                          re.IGNORECASE))


def score(root: Path) -> list[Axis]:
    health = grading.health_axis(root)
    tests = grading.tests_axis(root, critical=CRITICAL, external=True)

    if not grading.has_php():
        reason = "php missing on this machine"
        return [Axis("works", 40, None, [], reason=reason),
                Axis("scope", 25, None, [], reason=reason), health, tests]

    docroot = _docroot(root)
    if docroot is None:
        w = Tally()
        for name, weight in (("index.php exists", 8), ("server boots", 10),
                             ("login page renders", 10),
                             ("correct password gets in", 12)):
            w.item(name, weight, False, "index.php not found")
        s = Tally()
        for page in PAGES:
            s.item(f"{page} works after login", 5, False, "no index.php")
        s.item("unauthenticated access blocked", 7, False, "no index.php")
        s.item("wrong password rejected", 3, False, "no index.php")
        return [w.axis("works", 40), s.axis("scope", 25), health, tests]

    port = _free_port()
    if port is None:
        reason = f"no free port in {PORT}-{PORT + 59} — cannot measure"
        return [Axis("works", 40, None, [], reason=reason),
                Axis("scope", 25, None, [], reason=reason), health, tests]

    w = Tally()
    s = Tally()
    w.item("index.php exists", 8, True, str(docroot.relative_to(root) or "."))
    if port != PORT:
        w.evidence.append(f"! {PORT} was held (the agent may have left its "
                          f"own server running); measured on port {port}")

    base = f"http://127.0.0.1:{port}"
    with grading.Server(["php", "-S", f"127.0.0.1:{port}", "-t", str(docroot)],
                        cwd=docroot, port=port, ready_s=25.0) as srv:
        w.item("server boots", 10, srv.opened,
               srv.crash or ("port opened" if srv.opened
                             else "port did not open in 25s"))
        if not srv.opened:
            w.item("login page renders", 10, False, "port never opened")
            w.item("correct password gets in", 12, False, "port never opened")
            for page in PAGES:
                s.item(f"{page} works after login", 5, False, "port never opened")
            s.item("unauthenticated access blocked", 7, False, "port never opened")
            s.item("wrong password rejected", 3, False, "port never opened")
            return [w.axis("works", 40), s.axis("scope", 25), health, tests]

        # 1. Unauthenticated access: is there a guard?
        guest = grading.Browser()
        guarded = []
        for page in PAGES:
            r = guest.request(f"{base}/{page}", follow=False)
            guarded.append((page, _guarded(r), r.code))
        held = sum(1 for _, ok, _ in guarded if ok)
        s.ratio("unauthenticated access blocked", 7, held / len(PAGES),
                "; ".join(f"{p}: {'blocked' if ok else f'OPEN (HTTP {code})'}"
                          for p, ok, code in guarded))

        # 2. The login page itself.
        b = grading.Browser()
        login = b.request(f"{base}/index.php")
        has_form = bool(re.search(r"type\s*=\s*['\"]password['\"]",
                                  login.body, re.IGNORECASE))
        healthy, why = grading.page_healthy(login, min_chars=60)
        w.item("login page renders", 10, healthy and has_form,
               f"{why}; password field: {has_form}")

        # 3. Wrong password.
        wrong = grading.Browser()
        wrong.request(f"{base}/index.php")
        _log_in(wrong, base, login.body, "wrongpassword")
        after_wrong = wrong.request(f"{base}/{PAGES[0]}", follow=False)
        s.item("wrong password rejected", 3, _guarded(after_wrong),
               f"after a wrong password {PAGES[0]} → HTTP {after_wrong.code}")

        # 4. Correct password → in.
        after = _log_in(b, base, login.body, PASSWORD)
        first = b.request(f"{base}/{PAGES[0]}")
        got_in = first.code == 200 and not re.search(
            r"type\s*=\s*['\"]password['\"]", first.body, re.IGNORECASE)
        w.item("correct password gets in", 12, got_in,
               f"login POST → HTTP {after.code}; {PAGES[0]} → HTTP {first.code}"
               + ("" if got_in else " (still serving the login form)"))

        # 5. The real question: do the pages work AFTER login?
        for page in PAGES:
            r = first if page == PAGES[0] else b.request(f"{base}/{page}")
            healthy, why = grading.page_healthy(r)
            still_login = bool(re.search(r"type\s*=\s*['\"]password['\"]",
                                         r.body, re.IGNORECASE))
            s.item(f"{page} works after login", 5,
                   healthy and not still_login,
                   why + (" — falls back to the login form" if still_login
                          else ""))

        if srv.dead:
            w.evidence.append("! the php process died during measurement")

    return [w.axis("works", 40), s.axis("scope", 25), health, tests]


if __name__ == "__main__":
    raise SystemExit(grading.standalone(score, "z2-panel"))
