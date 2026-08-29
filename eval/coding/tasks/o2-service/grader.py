"""o2 — medium/Python: a small HTTP service + its tests.

A service "working" is only knowable by making requests from the outside.
So the grader actually boots the process, waits for the port and fires
HTTP requests at the endpoints. The agent's own tests being green does not
enter this axis — that is a different axis.

The process is killed when measuring ends; no run leaves a listening
server behind.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import grading  # noqa: E402
from grading import Axis, Tally  # noqa: E402

TITLE = "Short-link HTTP service + tests"
DIFFICULTY = "medium"
LANGUAGE = "python"
CRITICAL = ("kisalt", "saglik")
PORT = 8099
TARGET = "https://ornek.gov.tr/ihale/2026/sondaj"


def _extract_code(r: grading.Response) -> str:
    """Pull the short code from the answer: JSON expected, plain text tolerated."""
    import json
    import re

    try:
        data = json.loads(r.body)
    except ValueError:
        data = None
    if isinstance(data, dict):
        for key in ("kod", "code", "kisa", "short", "id", "slug"):
            if isinstance(data.get(key), str) and data[key].strip():
                return data[key].strip().rsplit("/", 1)[-1]
        for value in data.values():
            if isinstance(value, str) and re.fullmatch(r"[\w-]{3,32}", value.strip()):
                return value.strip()
    m = re.search(r"[\w-]{4,32}", r.body.strip())
    return m.group(0) if m else ""


def score(root: Path) -> list[Axis]:
    service = grading.find(root, "servis.py")
    health = grading.health_axis(root)
    tests = grading.tests_axis(root, critical=CRITICAL)

    if service is None:
        w = Tally()
        for name, weight in (("servis.py exists", 8), ("process boots", 12),
                             ("port opens", 10), ("/saglik 200", 10)):
            w.item(name, weight, False, "servis.py not found")
        s = Tally()
        for name, weight in (("POST /kisalt returns a code", 10),
                             ("GET /<kod> redirects 302", 10),
                             ("unknown code 404", 5)):
            s.item(name, weight, False, "servis.py not found")
        return [w.axis("works", 40), s.axis("scope", 25), health, tests]

    if not grading.port_free(PORT):
        reason = f"port {PORT} is held by someone else — cannot measure"
        return [Axis("works", 40, None, [], reason=reason),
                Axis("scope", 25, None, [], reason=reason), health, tests]

    w = Tally()
    s = Tally()
    w.item("servis.py exists", 8, True, str(service.relative_to(root)))

    with grading.Server([sys.executable, service.name], cwd=service.parent,
                        port=PORT, ready_s=30.0) as srv:
        w.item("process boots", 12, not srv.dead or srv.opened,
               srv.crash or ("process died immediately"
                             if srv.dead and not srv.opened else "up"))
        w.item("port opens", 10, srv.opened,
               f"127.0.0.1:{PORT} " + ("opened" if srv.opened
                                       else "did not open in 30s"))

        browser = grading.Browser()
        base = f"http://127.0.0.1:{PORT}"
        if not srv.opened:
            w.item("/saglik 200", 10, False, "port never opened")
            for name, weight in (("POST /kisalt returns a code", 10),
                                 ("GET /<kod> redirects 302", 10),
                                 ("unknown code 404", 5)):
                s.item(name, weight, False, "port never opened")
        else:
            healthz = browser.request(f"{base}/saglik")
            w.item("/saglik 200", 10, healthz.code == 200,
                   f"HTTP {healthz.code}"
                   f"{(' ' + healthz.error) if healthz.error else ''}")

            shorten = browser.request(f"{base}/kisalt",
                                      json_body={"url": TARGET})
            code = _extract_code(shorten) if shorten.code in (200, 201) else ""
            s.item("POST /kisalt returns a code", 10, bool(code),
                   f"HTTP {shorten.code}, code «{code}»; "
                   f"body {shorten.body[:80]!r}")

            if code:
                visit = browser.request(f"{base}/{code}", follow=False)
                location = (visit.headers.get("Location", "")
                            or visit.headers.get("location", ""))
                s.item("GET /<kod> redirects 302", 10,
                       visit.code in (301, 302, 303, 307, 308)
                       and TARGET in location,
                       f"HTTP {visit.code}, Location «{location[:80]}»")
            else:
                s.item("GET /<kod> redirects 302", 10, False, "no code obtained")

            missing = browser.request(f"{base}/definitely-missing-4242",
                                      follow=False)
            s.item("unknown code 404", 5, missing.code == 404,
                   f"HTTP {missing.code}")

    return [w.axis("works", 40), s.axis("scope", 25), health, tests]


if __name__ == "__main__":
    raise SystemExit(grading.standalone(score, "o2-service"))
