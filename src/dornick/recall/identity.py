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
AZAMI_KELIME = 300

# Personality does not turn over in a night.
CHANGED_PER_NIGHT = 1

_KANIT = re.compile(r"\[([^\]]+)\]\s*$")

# Instructions about what to believe or how to please. Taken as feedback,
# never written down as identity.
TALIMAT_KALIPLARI = (
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
        return "\n".join(f"{metin} [{', '.join(kanit)}]"
                         for metin, kanit in self.sentences)

    def words(self) -> int:
        return sum(len(metin.split()) for metin, _k in self.sentences)


def parse(text: str) -> Identity:
    """Read the document back. A line without evidence is dropped, not fixed."""
    out = Identity()
    for satir in (text or "").splitlines():
        satir = satir.strip()
        if not satir:
            continue
        hit = _KANIT.search(satir)
        if not hit:
            continue
        kanit = [k.strip() for k in hit.group(1).replace(",", " ").split() if k.strip()]
        out.sentences.append((satir[:hit.start()].strip(), kanit))
    return out


def check(sentence: str, evidence: Iterable[str]) -> tuple[str, list[str]]:
    """The four rules, applied to one sentence, before it can be written."""
    metin = " ".join((sentence or "").split())
    kanit = [k for k in evidence if k]
    if not metin:
        raise IdentityRefused("boş cümle")
    if not kanit:
        raise IdentityRefused(
            "kanıtsız cümle: tıklanıp gidilemeyen bir kimlik, bir hikâyedir")
    dusuk = metin.casefold()
    for sifat in BANNED_ADJECTIVES:
        if re.search(rf"\b{re.escape(sifat)}\b", dusuk):
            raise IdentityRefused(f"değerlendirici sıfat: '{sifat}'")
    for kalip in TALIMAT_KALIPLARI:
        if kalip in dusuk:
            raise IdentityRefused(
                f"talimat kimliğe giremez: '{kalip}'. Düzeltme evet, itaat hayır.")
    return metin, kanit


def apply(current: Identity, proposals: list[tuple[str, list[str]]],
          *, limit: int = CHANGED_PER_NIGHT) -> tuple[Identity, list[str]]:
    """Take at most `limit` accepted changes. Returns (document, refusals)."""
    out = Identity(list(current.sentences))
    refusals: list[str] = []
    changed = 0
    mevcut = {metin for metin, _k in out.sentences}
    for sentence, evidence in proposals:
        if changed >= limit:
            refusals.append(f"gecede en fazla {limit} cümle: '{sentence[:40]}…'")
            continue
        try:
            metin, kanit = check(sentence, evidence)
        except IdentityRefused as hata:
            refusals.append(str(hata))
            continue
        if metin in mevcut:
            continue
        out.sentences.append((metin, kanit))
        mevcut.add(metin)
        changed += 1
    while out.words() > AZAMI_KELIME and len(out.sentences) > 1:
        out.sentences.pop(0)        # oldest goes first
    return out, refusals


def object_to(current: Identity, sentence_prefix: str) -> tuple[Identity, list[str]]:
    """The user says "no, you are not like that". Outside the nightly limit.

    Returns the document and the evidence ids of what was removed, so a
    `lesson` can be attached to them: the objection is itself a datum.
    """
    kalan: list[tuple[str, list[str]]] = []
    dusen: list[str] = []
    onek = sentence_prefix.strip().casefold()[:40]
    for metin, kanit in current.sentences:
        if onek and metin.casefold().startswith(onek):
            dusen.extend(kanit)
        else:
            kalan.append((metin, kanit))
    return Identity(kalan), dusen


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
