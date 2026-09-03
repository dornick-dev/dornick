"""The narrative identity document — slow, evidenced, and contestable.

`Soul.persona` is a fixed string from config. This replaces it with a short
document the night rewrites from `self`, `voice` and `lesson` records. Four
rules make it something other than a machine flattering itself, and all four
are enforced here rather than asked for in a prompt:

1. **Every sentence carries evidence.** A sentence without node ids is
   refused. An identity you cannot click through to is a story.
2. **At most one sentence changes per night.** Personality does not turn
   over in a night; stability is mechanical, not aspirational.
3. **No evaluative adjectives.** "Careful" cannot be checked. "Wrote tests
   first in 33 of 41 tasks" can.
4. **The user can object**, and an objection deletes that sentence outside
   the one-per-night limit. It is their description too.

And one refusal: an instruction is not a description. "Always agree",
"never criticise" are not written into the document or into `voice`. A
correction is taken; an order about what to believe is not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .subjects import BANNED_ADJECTIVES

# The document is part of every system prompt, so its length is a per-session
# tax. Short enough that nobody skims it.
MAX_WORDS = 300

# Personality does not turn over in a night.
CHANGED_PER_NIGHT = 1

_EVIDENCE = re.compile(r"\[([^\]]+)\]\s*$")

# Instructions about what to believe or how to please. Taken as feedback,
# never written down as identity. (Turkish phrases: the document is Turkish.)
INSTRUCTION_PATTERNS = (
    "hep katıl", "asla eleştirme", "her zaman haklı", "itiraz etme",
    "beni onayla", "hep evet", "sorgulama",
)


class IdentityRefused(ValueError):
    """A sentence that may not enter the document, and why."""


@dataclass(slots=True)
class Identity:
    """The document: sentences, each with the ids that back it."""

    sentences: list[tuple[str, list[str]]] = field(default_factory=list)

    def render(self) -> str:
        return "\n".join(f"{text} [{', '.join(evidence)}]"
                         for text, evidence in self.sentences)

    def words(self) -> int:
        return sum(len(text.split()) for text, _e in self.sentences)


def parse(text: str) -> Identity:
    """Read the document back. A line without evidence is dropped, not fixed."""
    out = Identity()
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        hit = _EVIDENCE.search(line)
        if not hit:
            continue
        evidence = [k.strip() for k in hit.group(1).replace(",", " ").split() if k.strip()]
        out.sentences.append((line[:hit.start()].strip(), evidence))
    return out


def check(sentence: str, evidence: Iterable[str]) -> tuple[str, list[str]]:
    """The four rules, applied to one sentence, before it can be written."""
    text = " ".join((sentence or "").split())
    ids = [k for k in evidence if k]
    if not text:
        raise IdentityRefused("boş cümle")
    if not ids:
        raise IdentityRefused(
            "kanıtsız cümle: tıklanıp gidilemeyen bir kimlik, bir hikâyedir")
    lowered = text.casefold()
    for adjective in BANNED_ADJECTIVES:
        if re.search(rf"\b{re.escape(adjective)}\b", lowered):
            raise IdentityRefused(f"değerlendirici sıfat: '{adjective}'")
    for pattern in INSTRUCTION_PATTERNS:
        if pattern in lowered:
            raise IdentityRefused(
                f"talimat kimliğe giremez: '{pattern}'. Düzeltme evet, itaat hayır.")
    return text, ids


def apply(current: Identity, proposals: list[tuple[str, list[str]]],
          *, limit: int = CHANGED_PER_NIGHT) -> tuple[Identity, list[str]]:
    """Take at most `limit` accepted changes. Returns (document, refusals)."""
    out = Identity(list(current.sentences))
    refusals: list[str] = []
    changed = 0
    present = {text for text, _e in out.sentences}
    for sentence, evidence in proposals:
        if changed >= limit:
            refusals.append(f"gecede en fazla {limit} cümle: '{sentence[:40]}…'")
            continue
        try:
            text, ids = check(sentence, evidence)
        except IdentityRefused as err:
            refusals.append(str(err))
            continue
        if text in present:
            continue
        out.sentences.append((text, ids))
        present.add(text)
        changed += 1
    while out.words() > MAX_WORDS and len(out.sentences) > 1:
        out.sentences.pop(0)        # oldest goes first
    return out, refusals


def object_to(current: Identity, sentence_prefix: str) -> tuple[Identity, list[str]]:
    """The user says "no, you are not like that". Outside the nightly limit.

    Returns the document and the evidence ids of what was removed, so a
    `lesson` can be attached to them: the objection is itself a datum.
    """
    kept: list[tuple[str, list[str]]] = []
    dropped: list[str] = []
    prefix = sentence_prefix.strip().casefold()[:40]
    for text, evidence in current.sentences:
        if prefix and text.casefold().startswith(prefix):
            dropped.extend(evidence)
        else:
            kept.append((text, evidence))
    return Identity(kept), dropped


# -- disk --------------------------------------------------------------


def load(state_dir: Path) -> Identity:
    try:
        return parse((Path(state_dir) / "kimlik.md").read_text("utf-8"))
    except OSError:
        return Identity()


def save(state_dir: Path, identity: Identity) -> None:
    path = Path(state_dir) / "kimlik.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(identity.render() + "\n", encoding="utf-8")


def reset(state_dir: Path) -> None:
    """A memory reset takes the narrative. Temperament lives elsewhere and
    stays — amnesia does not change what kind of person someone is."""
    try:
        (Path(state_dir) / "kimlik.md").unlink()
    except OSError:
        pass
