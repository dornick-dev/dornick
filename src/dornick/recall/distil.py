"""Night step 6 — distillation, and the exam gate that can undo it.

The first five steps of the night are pure Python and SQLite: they record
what happened. This one is different in kind. It asks a model to read a
cluster of related memories and write down what is worth keeping, which
means it produces a **guess**, not a record. Everything about how it is
wired follows from that one distinction:

* It is the only step that needs a model, so it is the only step a
  model-less installation loses.
* It never sends memory text to a hosted endpoint unless the user has
  explicitly consented. No consent and no local model means the step is
  skipped and the report says so, in those words.
* It is the only step the exam gate can roll back. Replay, credit assignment
  and schema touches are records of things that actually happened; a
  distilled fact is an inference, and an inference that makes retrieval
  worse should not survive the night that produced it.

What distillation buys: an `episode` cannot enter the automatic prime — the
turn dumps are long and match almost every query. A distilled `fact` can.
So the substance of a conversation becomes injectable at a fraction of the
tokens, which is the whole point of the step.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from . import activation, switches
from .clock import Clock, wall_clock

# A cluster smaller than this has nothing to summarise; larger than this and
# the model starts inventing connective tissue.
MIN_CLUSTER = 3
MAX_CLUSTER = 12

# At most this many keepers per cluster. The instruction is also in the
# prompt, but the parser enforces it — a model that ignores the limit should
# not be able to flood the memory.
MAX_KEEPERS = 3

# Edges at or above this weight are treated as one cluster (roadmap 3.6).
CLUSTER_EDGE = 0.6

# What the source episodes lose once their substance lives in a short fact:
# pushed to the background, never deleted.
SOURCE_PENALTY = -0.2

# An edge the model calls unrelated is not cut, only weakened. Cutting it
# would throw away a path on a single opinion.
UNRELATED_WEIGHT = 0.1

PROMPT = """Aşağıdaki hatıralar birbirine yakın. En fazla {n} kalıcı bilgi çıkar.
Yalnızca kullanıcının SÖYLEDİĞİ ya da doğrulanmış olanı yaz; tahmin yazma.
Çelişen ikili varsa 'ÇELİŞKİ: <id1> vs <id2>' satırıyla bildir.
İlişkili gördüğün her ikili için 'İLİŞKİ: <id1> <id2> - <tek cümle>' yaz;
ilişkisizse cümle yerine 'ilişkisiz' yaz.
Kalıcı bilgi satırlarında kaynak id'lerini satır sonuna köşeli parantezle yaz.

{bodies}
"""

_CONTRADICTION = re.compile(r"^ÇELİŞKİ:\s*(\S+)\s+vs\s+(\S+)", re.IGNORECASE)
_RELATION = re.compile(r"^İLİŞKİ:\s*(\S+)\s+(\S+)\s*[-—:]\s*(.+)$", re.IGNORECASE)
_SOURCES = re.compile(r"\[([^\]]+)\]\s*$")


@dataclass(slots=True)
class DistilReport:
    """What the night's sixth step produced — or why it produced nothing."""

    status: str = ""
    clusters: int = 0
    written: int = 0
    contradictions: int = 0
    relations: int = 0
    cooled_sources: int = 0
    node_ids: list[str] = field(default_factory=list)
    rolled_back: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "clusters": self.clusters,
                "written": self.written, "contradictions": self.contradictions,
                "relations": self.relations, "cooled_sources": self.cooled_sources,
                "rolled_back": self.rolled_back}


# -- the gate ----------------------------------------------------------


def gate(model: Callable[[str], str] | None, *, local_model: bool,
         cloud_ok: bool) -> str:
    """Why distillation may not run. Empty string means it may.

    Privacy is decided here and nowhere else: memory text reaches a hosted
    endpoint only when the user has turned that on. A model-less machine
    still gets the first five steps of the night; it loses summaries, not
    consolidation.
    """
    if not switches.ACTIVE.distillation:
        return "atlandı: damıtma kapalı"
    if model is None:
        return "atlandı: yerel model yok"
    if not local_model and not cloud_ok:
        return "atlandı: barındırılan model, bulut onayı kapalı"
    return ""


# -- clustering --------------------------------------------------------


def clusters(store: Any, seeds: Sequence[str]) -> list[list[str]]:
    """Groups worth summarising: episodes and tightly linked fact groups.

    Grown from the nodes this night actually replayed, not from a scan of
    the whole graph. Distilling what nobody touched would be summarising the
    archive, which is not what the night is for.
    """
    seen: set[str] = set()
    out: list[list[str]] = []
    for node_id in dict.fromkeys(seeds):
        if node_id in seen:
            continue
        group = _grow(store, node_id, seen)
        if MIN_CLUSTER <= len(group) <= MAX_CLUSTER:
            out.append(group)
    return out


def _grow(store: Any, start: str, seen: set[str]) -> list[str]:
    node = store.peek(start)
    if node is None:
        return []
    group = [start]
    seen.add(start)
    for neighbour, weight in store.neighbours(start):
        if len(group) >= MAX_CLUSTER:
            break
        if neighbour.id in seen or weight < CLUSTER_EDGE:
            continue
        # Episodes cluster with anything they touched; facts only with facts.
        if node.kind == "episode" or neighbour.kind in ("episode", node.kind):
            group.append(neighbour.id)
            seen.add(neighbour.id)
    return group


# -- distillation ------------------------------------------------------


def distil(
    store: Any,
    seeds: Sequence[str],
    *,
    model: Callable[[str], str] | None,
    clock: Clock | None = None,
    local_model: bool = True,
    cloud_ok: bool = False,
    state_dir: Path | None = None,
) -> DistilReport:
    """Turn clusters of memories into a few short, sourced facts."""
    clock = clock or wall_clock
    report = DistilReport()
    if reason := gate(model, local_model=local_model, cloud_ok=cloud_ok):
        report.status = reason
        return report

    groups = clusters(store, seeds)
    report.clusters = len(groups)
    for group in groups:
        nodes = [n for n in (store.peek(i) for i in group) if n is not None]
        if len(nodes) < MIN_CLUSTER:
            continue
        try:
            answer = model(PROMPT.format(n=MAX_KEEPERS, bodies=_render(nodes)))
        except Exception as exc:
            report.status = f"kısmi: model hatası ({exc})"
            continue
        _apply(store, nodes, answer, report, clock, state_dir)
    report.status = report.status or f"{report.written} damıtık kayıt"
    return report


def _render(nodes: Sequence[Any]) -> str:
    return "\n".join(f"[{n.id}] ({n.kind}) {n.title}: {n.body[:600]}" for n in nodes)


def _apply(store: Any, nodes: Sequence[Any], answer: str, report: DistilReport,
           clock: Clock, state_dir: Path | None) -> None:
    ids = {n.id for n in nodes}
    tags = sorted({t for n in nodes for t in n.tags})
    written = 0
    for line in (answer or "").splitlines():
        line = line.strip()
        if not line:
            continue

        if hit := _CONTRADICTION.match(line):
            # The system does not resolve contradictions on its own. It
            # records them and shows them; superseding on a model's opinion
            # would let a guess overwrite something the user said.
            _record_contradiction(state_dir, hit.group(1), hit.group(2), clock)
            report.contradictions += 1
            continue

        if hit := _RELATION.match(line):
            a, b, reason = hit.group(1), hit.group(2), hit.group(3).strip()
            if a in ids and b in ids:
                if reason.lower().startswith("ilişkisiz"):
                    # Not cut, weakened: a path is not thrown away on a
                    # single opinion. If they are later used together,
                    # Step 2 strengthens it back.
                    store.update_edge(a, b, weight=UNRELATED_WEIGHT,
                                         reason="ilişkisiz (damıtma)")
                elif not store.update_edge(a, b, reason=reason[:200]):
                    store.connect(a, b, weight=CLUSTER_EDGE, reason=reason[:200])
                report.relations += 1
            continue

        if written >= MAX_KEEPERS:
            continue
        body, sources = _split_sources(line, ids)
        if len(body) < 12:
            continue
        node = store.remember(body, kind="fact", tags=[*tags, "damıtık"],
                              links=sources or list(ids))
        report.node_ids.append(node.id)
        written += 1
        report.written += 1

    if written:
        for node in nodes:
            if node.kind == "episode":
                store.add_use(node.id, w=SOURCE_PENALTY,
                                    label=activation.DISTILLED)
                report.cooled_sources += 1


def _split_sources(line: str, ids: set[str]) -> tuple[str, list[str]]:
    hit = _SOURCES.search(line)
    if not hit:
        return line.strip(), []
    sources = [s.strip() for s in hit.group(1).replace(",", " ").split()]
    return line[:hit.start()].strip(), [s for s in sources if s in ids]


def _record_contradiction(state_dir: Path | None, first: str, second: str,
                          clock: Clock) -> None:
    """Written to disk for the user, not acted on by the system."""
    if state_dir is None:
        return
    try:
        path = Path(state_dir) / "celiskiler.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {"ts": clock().isoformat(timespec="milliseconds"),
                 "a": first, "b": second}, ensure_ascii=False) + "\n")
    except OSError:
        pass


# -- the exam gate (roadmap 3.7) ---------------------------------------


def exam(
    store: Any,
    report: DistilReport,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> int:
    """Roll distilled nodes back if the night made retrieval worse.

    Only guesses are undone. Replay, credit assignment and schema touches
    stay: they are the record of something that happened, and a night that
    produced a bad summary did not thereby un-happen the day.

    Returns how many distilled nodes were tombstoned.
    """
    if not report.node_ids or not before or not after:
        return 0
    worse = False
    for key in ("prime_precision", "tuzak_sessizlik"):
        old, new = before.get(key), after.get(key)
        if old is not None and new is not None and new < old:
            worse = True
    if not worse:
        return 0
    for node_id in report.node_ids:
        store.forget(node_id)
    report.rolled_back = len(report.node_ids)
    report.status += " — sınavı geçemedi, geri alındı"
    return report.rolled_back
