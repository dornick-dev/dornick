"""The agent loop.

The loop itself is embarrassingly simple — call the model, do what it says,
hand the result back, repeat. All of the value lives in the things *around*
the loop: context management, the permission gate, interrupt safety,
persistence.

Interrupt safety is enforced at two points here:
  * if interrupted mid-stream the half-written assistant message is dropped
    (a half tool_use input corrupts the next request),
  * if interrupted mid tool execution, every unanswered tool_use gets a
    cancellation result injected (a missing tool_result = 400).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4

from . import compaction, prompt
from .backends import Backend, Callbacks, TurnResult
from .config import Config
from .context import ContextPolicy, Prepared, cache_report
from .permissions import PermissionEngine
from .session import PendingToolUse, Session, cancelled_result
from .tools import ToolContext, ToolRegistry, build_registry, execute
from .tools.base import JobFailed, ToolSpec

# Long-run checkpoint interval. It used to be a HARD ceiling: at turn 60 the
# loop stopped and an hour-long job was left half done. Now every 60 turns
# the agent is asked to write a short progress note and the work CONTINUES;
# the real brake is the user (stop works from the first moment) + the
# absolute fuse below.
MAX_TURNS = 60

# Absolute per-run turn fuse. Last line of defence against a runaway loop.
# 600 turns burned tokens (Market Lens ~80+ steps); 240 ≈ 4× soft MAX_TURNS.
HARD_TURN_LIMIT = 240

# How many times a reply that hits the ceiling gets continued. Leaving it
# unbounded turns into a loop with a model that writes and writes and never
# finishes. The counter resets on every turn that calls a tool (i.e. makes
# progress): occasionally hitting the ceiling during a long run must not
# drag the job into the closing turn.
MAX_CONTINUATIONS = 4

# Retry intervals on a model error (connection, 5xx, timeout). Exponential
# backoff: a single provider hiccup must not kill an hour-long job. Tests
# patch the module variable to shorten it.
RETRY_DELAYS = (15.0, 30.0, 60.0, 120.0, 300.0)

# When the retries run out the MAIN agent PARKS the job: it does not die, it
# waits with sparse probing. A subagent / scheduled task does NOT park — it
# ends with an error instead of an endless "Model bekleniyor (5/5)" lock
# (so a task does not stay stuck while chat is working).
PARK_PROBE_S = 180.0

# Park record: even if the app closes, the trace of the half-done job stays
# on disk; if seen at startup the run is resumed automatically.
PARK_FILE = "park.json"

# Subagent nesting limit. 1 means: the main agent can spawn a helper, the
# helper cannot. Leaving it unbounded fans one request out like a tree and
# nobody can tell how much work was done.
MAX_DEPTH = 1

# Size of the helper ledger. So finished records do not pile up without
# bound, the oldest finished ones are dropped; a running helper is never
# dropped. Sessions stay on disk — dropping from the ledger is not data loss.
MAX_CHILDREN = 8

# Cap on the result inside the notification note: the helper's answer enters
# the main context, and if it enters unbounded the whole point of splitting
# the context is lost.
CHILD_RESULT_CLIP = 2000

# Number of memories placed in front of the model before each user message.
# More is context waste: an irrelevant memory pulls the model off topic.
RECALL_PRIME_LIMIT = 5

# In a narrow window the same count eats a significant part of the context.
LEAN_PRIME_LIMIT = 2

# Minimum length for instant encoding. Turns like "evet", "tamam", "ok" carry
# no reference to a topic; writing them to memory is only noise. The
# threshold + _worth_recalling together filter out greetings and one-word
# acknowledgements.
ENCODE_MIN_CHARS = 25

# Minimum strength for spontaneously recalled items. After the calibrated
# fusion the score is a MAGNITUDE, not a RANK: in a small memory the single
# real match can get ~0.24 (bm25 strength grows with the corpus), in a
# crowded memory it saturates at ~0.9. The old 0.3 floor was for the old
# rank scale and silently switched priming off in a young memory. The
# relevance filter is no longer the threshold: the direct-match requirement
# + the letter grounding (_grounded) carry it; the floor only cuts the noise
# floor.
RECALL_PRIME_FLOOR = 0.12

# Number formats stripped from the priming query: IP address, port, register
# address, long measurement values.
#
# Numbers look alike at the signature layer and pull in unrelated records.
# Measured: the query "5.11.239.227 ... 5004 portunda ... 404195 adresinde
# depo seviye" brought up three BTC price records (BTC 3.715.633 TL). With
# the numbers removed all three drop off the list entirely.
#
# Applied only to **spontaneous** priming. In the model's own `mind_recall`
# call the number may be exactly what is being searched for ("404195 hangi
# register?") and is left untouched there.
_NUMERIC = re.compile(r"\b[\d][\d.,:/-]*\b")

# Greetings and small talk. These do not refer to a topic; not worth opening
# the mind for. The list is kept short: a long ban list is hard to maintain
# and the length criterion does the real work.
SMALL_TALK = frozenset(
    {
        "selam", "merhaba", "naber", "nabersin", "nasilsin", "nasılsın",
        "gunaydin", "günaydın", "iyi", "iyiyim", "sagol", "sağol",
        "tesekkur", "teşekkür", "tesekkurler", "teşekkürler", "eyvallah",
        "gorusuruz", "görüşürüz", "hosgeldin", "hoşgeldin", "hello", "hey",
    }
)

_WORDS = re.compile(r"\w+", re.UNICODE)

RECALL_PRIME_HEADER = (
    "Kullanicinin son mesaji zihninde arandi; asagidakiler kendiliginden "
    "hatirlandi. Ilgiliyse kullan, degilse yoksay — bunlari kullanici "
    "yazmadi, sana hatirlatildi."
)

# Continuation nudge. It goes through the user channel because after the
# cut-off turn the last message is the assistant's own and a system note has
# to follow a user message. Hidden in the UI: a message the user did not
# write must not look like a user message in the chat.
CONTINUE_NOTE = (
    "Önceki yanıtın uzunluk sınırında kesildi. Kaldığın yerden devam et. "
    "Yazdıklarını baştan tekrarlama, girişi yeniden yapma, kod bloğunu "
    "yeniden açma; tam olarak kestiğin karakterden sonrasını yaz."
)

# The final turn given when the continuation allowance runs out.
#
# The previous version stopped here and told the user "the request may need
# to be split into smaller pieces". But the agent had done work: it had
# called tools, read values, it just had not finished. The user got nothing
# — both the work done and their question were lost.
#
# This turn is given without tools: letting it call tools again means
# running one more turn of the loop that locked up.
CLOSING_NOTE = (
    "Sürdürme hakkın bitti. Şimdi elindekiyle bitir: yeni araç çağırma, "
    "yeni plan yapma, baştan anlatma. Birkaç cümlede şunu yaz — ne buldun, "
    "hangi değeri okudun, hangi soru cevapsız kaldı. Emin olmadığın bir şeyi "
    "kesin gibi yazma; eksikse eksik olduğunu söyle."
)

# Instruction attached when a camera frame is sent without text. Listing
# what it should look at prevents the one-sentence brush-off.
LOOK_NOTE = (
    "Kameradan bir kare. Gerçekten bak ve gördüğünü anlat: ortam, kişi, "
    "elinde ya da önünde ne var, yüz ifadesi nasıl duruyor, genel hâli ne "
    "anlatıyor. Bunlar görünenden çıkarım — kesin bilgi gibi yazma, "
    "\"öyle duruyor\" diye yaz. Göremediğin bir şeyi uydurma; kare bulanıksa "
    "ya da karanlıksa onu söyle."
)

# Note placed next to the image when the agent looked by itself (camera
# frame or screenshot). It does not say "what the camera saw": a `screen`
# image now arrives through the same path and misnaming it confused the
# model.
SEEN_NOTE = (
    "Yukarıdaki görüntü senin kendi bakışın — kameradan bir kare ya da "
    "ekran görüntüsü. Kullanıcı göndermedi, sen baktın. Ne gördüğünü "
    "söyle ve işine o gördüğünle devam et; göremediğin bir şeyi uydurma."
)

# Nudge given to a turn that only reasoned and stopped.
ACT_NOTE = (
    "Planını yazdın ama uygulamadın. Şimdi yap: gereken aracı çağır ya da "
    "cevabı doğrudan kullanıcıya yaz. Planı tekrar anlatma."
)

# The model wrote the call XML as PLAIN TEXT instead of a real tool call.
# This is not an answer, it is a failed tool attempt: it is not shown to the
# user (the UI does not draw it) and the model is corrected with a one-line
# note. The turn continues — stopping here would silently leave the user
# with half an answer.
FAKE_CALL_NOTE = (
    "[Harness notu] Az önce bir araç çağrısını DÜZ METİN olarak yazdın "
    "(<function_calls>… gibi). O metin çalıştırılmadı ve kullanıcıya "
    "gösterilmedi. Araçları yalnızca gerçek araç çağrısı kanalıyla "
    "çağırabilirsin: aynı isteği araç çağrısı olarak yap."
)

# Repeated within the same turn: the note hardens. When the soft note did
# not work the reason is usually that the model read the previous failure
# as "the tool is broken".
FAKE_CALL_HARD_NOTE = (
    "[Harness notu] Araç çağrısını YİNE metin olarak yazdın. Yazdığın XML "
    "hiçbir şey çalıştırmıyor. Araçlar çalışıyor; sorun çağrı biçiminde. "
    "Ya aracı gerçek araç çağrısı olarak çağır ya da araç kullanmadan "
    "kullanıcıya doğrudan cevap yaz. Üçüncü bir seçenek yok."
)

# Absolute fuse on the fake-call correction attempts. A model that does not
# recover as the note hardens (usually a free endpoint that cannot call
# tools) must not keep the turn busy forever: after this count the turn is
# left to its own flow and the user is told — so they can switch models.
SAHTE_CAGRI_TAVANI = 5

# Tool-call XML inside assistant text. Same pattern as the UI-side defence
# (app.js SAHTE_CAGRI_KALIBI) — if one misses, the other catches it.
FAKE_CALL_PATTERN = re.compile(
    r"<\s*/?\s*(function_calls|invoke\b|parameter\b|antml:)", re.IGNORECASE)


def fake_tool_call(text: str) -> bool:
    """Does the text carry tool-call XML?

    When the model believes it cannot use the tool channel (e.g. it read a
    raw exception message as "the tool is broken") it writes the call as
    plain text. Proven to show up as raw XML on the user's screen.
    """
    return bool(FAKE_CALL_PATTERN.search(text or ""))


# -- mind-writing reflex --------------------------------------------------
#
# Measured regression: ZERO `mind_memory` calls in the last six sessions —
# even in a turn with 91 tool calls. The automatic path (episode encode)
# kept flowing but model-driven persistent writing had stopped entirely;
# for two days not a single preference/lesson/fact was recorded.
#
# The root asymmetry: RECALL is a reflex (`_prime_recall` runs by itself
# before every user message), WRITING is only advice. A weak or mid-tier
# model never picks that advice. Symmetry is restored: just as recall is
# triggered by the system, the TRANSITION to writing is triggered too — the
# decision is still the model's.
#
# The heuristic is deliberately CHEAP and HONEST: keyword level, no model
# call. A false positive does no harm because the note says "ignore if not
# worth it".
PERSISTENT_SIGNALS = (
    # Persistent rule / preference statement
    r"\bbundan sonra\b", r"\bbundan böyle\b", r"\bher zaman\b", r"\bhep\b",
    r"\basla\b", r"\bhiçbir zaman\b", r"\bşunu yapma\b", r"\byapma artık\b",
    r"\btercih ediyorum\b", r"\bsevmiyorum\b", r"\bistemiyorum\b",
    r"\bşöyle olsun\b", r"\bböyle olsun\b", r"\bkuralımız\b",
    r"\bunutma\b", r"\baklında tut\b", r"\bnot al\b",
    # Correction: sentences pointing out the model's mistake
    r"\byanlış\b", r"\böyle değil\b", r"\bdüzelt\b", r"\bhayır,",
    # A fact about the user
    r"\bbenim\b", r"\bbizim\b", r"\badım\b", r"\bçalıştığım\b",
    r"\bkullanıyorum\b", r"\bprojem\b", r"\bişim\b",
    # English counterparts: the user writes in both languages
    r"\bfrom now on\b", r"\balways\b", r"\bnever\b", r"\bdon't\b",
    r"\bi prefer\b", r"\bremember that\b", r"\bmy name is\b",
    r"\bactually,", r"\bthat's wrong\b",
)

_PERSISTENT = re.compile("|".join(PERSISTENT_SIGNALS), re.IGNORECASE)


def persistent_root(text: str) -> bool:
    """Did something that might be persistent come up in this message?

    No claim of certainty — a scent. The model decides; the only job here is
    to put the topic in front of the model.
    """
    return bool(_PERSISTENT.search(text or ""))


# The counterpart of the scent: one line, via the internal channel. Does NOT
# land in the chat (internal). An invitation, not an order: on a false
# positive the model ignores it and moves on.
MIND_NUDGE = (
    "[Zihin] Bu turda kalıcı olabilecek bir şey geçti: \"{alinti}\" "
    "Kaydetmeye değerse `mind_memory` ile yaz — oturum kapanınca bağlam "
    "gider, zihin kalır. Değmezse bu notu yok say."
)

# Length of the quote in the nudge: enough to bring the topic back to mind.
NUDGE_QUOTE_CHARS = 160


# The result of a helper that finished in the background is placed in front
# of the main agent at the start of the turn with this note. The channel is
# the harness's: the user did not write it, and the model must know that.
CHILD_DONE_NOTE = "[Yardımcı bitti · {title} (id={id})] Sonucu: {result}"
CHILD_FAIL_NOTE = "[Yardımcı hata verdi · {title} (id={id})] {result}"

# Input of the resume turn opened when a helper finishes while the main
# agent is idle. NOT a user message: it goes through the continuation
# channel and is not shown in the UI.
CHILDREN_RESUME_NOTE = (
    "Arka plandaki yardımcı(lar) bitti: {titles}. "
    "Tam rapor Orkestra / Görevler panelinde duruyor; kullanıcı tıklayınca "
    "ayrı görüntüleyicide açılıyor (sohbet balonu değil). "
    "Sohbete raporu veya uzun özeti YAPIŞTIRMA — en fazla bir cümle: "
    "'X hazır; soldaki Orkestra'dan aç.' Kullanıcı yeni bir şey istemedi, "
    "yeni iş başlatma."
)

# Envelope given to the scheduled-task helper: the output is a report, not
# chat.
SCHEDULE_CHILD_WRAP = (
    "[Zamanlanmış görev · {title}]\n{prompt}\n\n"
    "Bu bir zamanlanmış iş. Sonucu sohbet cevabı gibi değil, kendi başına "
    "okunabilir bir RAPOR olarak yaz (başlık + maddeler + kaynaklar). "
    "Rapor Orkestra panelinden açılacak; ana sohbete yapıştırılmayacak."
)

# Envelope of a user message that arrives mid-turn. The bridge (desktop)
# puts it into the inbox with this envelope; defined here because the tests
# use it too.
BARGE_NOTE = (
    "[Kullanıcı bu arada yazdı] {text} — koşan işi sürdürürken bunu da "
    "ele al; öncelik gerekiyorsa yön değiştir."
)

# `task_say`: envelope of the interim message from the main agent to a
# running helper.
SAY_NOTE = (
    "[Ana ajandan ara mesaj] {message} — işini sürdürürken bunu da hesaba "
    "kat; öncelik gerekiyorsa yön değiştir."
)

# Notes dropped when a background JOB (long command/build/test run) ends.
# Separate from helper (model-running subagent) notes: this is a process
# output.
JOB_DONE_NOTE = "[Arka plan işi bitti · {title} (id={id})] Çıktısı: {result}"
JOB_FAIL_NOTE = "[Arka plan işi hata verdi · {title} (id={id})] {result}"

# Orphan helpers found at startup (background subagents that died together
# with the app in the previous session) are introduced to the model with
# this note: if the user says "continue", `task_say` can already revive the
# finished/on-disk session.
ORPHAN_NOTE = (
    "[Harness notu] Geçen oturumdan {n} yardımcı yarım kaldı: {liste}. "
    "Uygulama kapanınca arka plan yardımcıları durur; oturumları diskte "
    "duruyor. Kullanıcı sürdürmek isterse `task_say` (id + yönerge) ile "
    "kaldıkları yerden devam ettirebilirsin; kullanıcı istemeden "
    "kendiliğinden başlatma."
)

# The orphan helper's result in the ledger — the panel and `task_status`
# show this.
ORPHAN_RESULT = (
    "Uygulama kapanınca yarım kaldı. Oturumu diskte duruyor; `task_say` ile "
    "kaldığı yerden sürdürülebilir."
)

# -- plan reflex ----------------------------------------------------------
#
# The prompt SAYS "on a big job write a module plan first" and it DOES NOT
# WORK: in a seven-task measurement no plan was written in any of the seven.
# The lesson learned with memory writing applies here too — advice is not
# enough, a reflex is needed.
#
# The gate is CHEAP: no model call, regex and length level. The cost of a
# false positive is an unnecessary plan sentence (acceptable); the cost of a
# false negative is a run that starts without a plan (the thing actually
# being avoided). Still, so it fires rarely, three signals must be looked
# for TOGETHER: a build verb + (a scale word or an item list or long text).

BIG_JOB_CHARS = 350        # a request longer than this many characters
# Was 180; measured wound: even the 10-line o1-report task got the "[Plan]
# Bu iş büyük görünüyor" nudge (user: "you don't need to draw a plan for
# everything — plan if the scope is big, otherwise just do it"). A long
# paragraph alone is not proof of size; the scale-word and item-count
# signals remain.
BIG_JOB_ITEMS = 3          # or this many items/deliverables

# Verbs meaning "wants me to PRODUCE something". Asking, reading, opening,
# fixing are not here — they are not jobs that need a plan.
_BUILD_VERB = re.compile(
    r"\b(yap|yapar\s+mısın|kur|geliştir|gelistir|tamamla|oluştur|olustur|"
    r"inşa\s+et|insa\s+et|tasarla|hazırla|hazirla|yazar\s+mısın|"
    r"build|create|implement|develop|make)\w*\b",
    re.IGNORECASE,
)

# Scale word: not a single-file script, something with several parts.
_SCALE_WORD = re.compile(
    r"\b(panel|dashboard|sistem|system|uygulama|app|servis|service|site|"
    r"web\s*sitesi|proje|project|platform|api|arayüz|arayuz|altyapı|altyapi|"
    r"modül|modul|module|oyun|game|bot|editör|editor|yönetim|yonetim|"
    r"admin|crm|erp|panosu|pano)\w*\b",
    re.IGNORECASE,
)

# Item list: multiple deliverables in the form "şunlar olsun: - a - b - c".
_ITEM_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+\S", re.MULTILINE)


def buyuk_is(text: str) -> bool:
    """Does this request look "big / open-ended"?

    No claim of certainty — a scent, like `persistent_root`. The decision is
    still the model's; the only job here is to put the plan-writing order in
    front of the model.
    """
    body = (text or "").strip()
    if not body or not _BUILD_VERB.search(body):
        # Without a build verb this is a question, a chat or a small fix.
        # Asking for a plan would be noise.
        return False
    if len(_ITEM_LINE.findall(body)) >= BIG_JOB_ITEMS:
        return True
    if _SCALE_WORD.search(body):
        return True
    return len(body) >= BIG_JOB_CHARS


# The counterpart of the scent: ONE line, via the internal channel, once at
# the start of the turn. Does not land in the chat. Not an order but an
# ordering rule — the reflex form of the long passage in the prompt.
PLAN_NOTU = (
    "[Plan] Bu iş büyük görünüyor. İlk cevabında modül listesi + her modül "
    "için kabul ölçütü yaz, sonra başla."
)


# -- the "don't say done while red" gate ---------------------------------
#
# In the measurement a task was delivered while its own test suite was RED.
# The prompt says "verify before saying done"; saying it is not enough.
#
# The trace of red is read from tool results. The tool layer does not carry
# `detail` to the model or the loop (the executor trims it with `_card`), so
# what is read are the two fields the loop actually sees: `error`
# (ToolResult.is_error) and the tool's OWN headline. What they mean differs
# per tool:
#
#   kos      — marks red itself (is_error): failed test, non-zero exit code,
#              timeout, interruption.
#   denetle  — does not mark an error with is_error (a lint finding must not
#              fail a write); red is written in its own text.
#   browser  — the console/network dump never returns an error; the numbers
#              are in the headline.
#
# Only these three count: a failed `read_file` is not a red run.

VERIFICATION_TOOLS = frozenset({"kos", "denetle", "browser"})

_LINT_ERROR = re.compile(r",\s*\d+\s+hata:")
_CONSOLE_ERROR = re.compile(r"\((\d+)\s+hata\)")
_NETWORK_ERROR = re.compile(r"(\d+)\s+başarısız")
# The executor's volume suffix ("  (+22 satır)"): a UI trace, not the tool's
# verdict.
_VOLUME_SUFFIX = re.compile(r"\s*\(\+\d+\s+satır\)\s*$")


def kirmizi_iz(tool: str, note: dict[str, Any]) -> str:
    """Is this tool result red? If red, a one-line summary, otherwise "".

    `note` is the executor's `tool_end` observation payload: {tool, error,
    summary, detail: {output, exit_code, …}}.
    """
    if tool not in VERIFICATION_TOOLS:
        return ""
    summary = _VOLUME_SUFFIX.sub("", str(note.get("summary") or "").strip())
    body = summary + "\n" + str((note.get("detail") or {}).get("output") or "")

    if tool == "kos":
        return (summary or "test koşumu başarısız") if note.get("error") else ""

    if tool == "denetle":
        return (summary or "denetimde hata var") if _LINT_ERROR.search(body) else ""

    # browser: an error in the console or a failed request.
    if (m := _CONSOLE_ERROR.search(body)) and int(m.group(1)) > 0:
        return f"tarayıcı konsolunda {m.group(1)} hata"
    if (m := _NETWORK_ERROR.search(body)) and int(m.group(1)) > 0:
        return f"{m.group(1)} başarısız istek"
    return ""


# The "done" claim: does the model declare the job finished while closing
# the turn without tools.
_DONE_CLAIM = re.compile(
    r"\b(bitti|bitirdim|tamamlandı|tamamlandi|tamamladım|tamamladim|"
    r"hazır|hazir|hazırdır|hazirdir|çalışıyor|calisiyor|sorunsuz|"
    r"done|completed?|finished|ready|works|working)\b",
    re.IGNORECASE,
)

# Don't nudge if it already admits the red: an honest report, not a false
# "done".
_RED_ADMISSION = re.compile(
    r"\b(başarısız|basarisiz|kırmızı|kirmizi|geçmedi|gecmedi|hata\s+var|"
    r"düzeltemedim|duzeltemedim|kaldı|kaldi|eksik|çalışmıyor|calismiyor|"
    r"fail(ing|ed|s)?|broken|not\s+working)\b",
    re.IGNORECASE,
)


def done_claim(text: str) -> bool:
    """Does this tool-less closing answer declare the job finished?

    An answer that already admits the red is honest even if it says "done"
    — it is not nudged. The cost of a false positive is a single extra turn
    and that turn only opens while there really is a red run on the table.
    """
    body = text or ""
    if not _DONE_CLAIM.search(body):
        return False
    return not _RED_ADMISSION.search(body)


KIRMIZI_NOTU = (
    "[Doğrulama] Son koşumun kırmızıydı ({ozet}). Bitti demeden önce ya "
    "düzelt ya da neyin çalışmadığını açıkça söyle."
)

# Acceptance-list gate: if "done" is said while OPEN items sit in the job
# ledger, one turn is handed back. Measured wound (the CMS run): the plan
# said "rich text editor" at M4, the delivery came out as a plain textarea
# and nothing caught it — the item had silently dropped.
# The MODEL sets the title (like Claude Code): the first 30 characters of
# the user's first sentence are not a title. One small call after the first
# exchange.
TITLE_PROMPT = (
    "Aşağıdaki konuşma için 2-5 kelimelik kısa bir başlık üret. Yalnız "
    "başlığı yaz: tırnak, nokta, emoji, açıklama yok. Konuşmanın dilinde."
)

def _title_valid(title: str) -> bool:
    """Is the generated session title worth saving?

    Single-letter junk ("e", "b") stuck as the permanent name and once the
    name was written it was never generated again — the chat was listed on
    the left under that letter. A meaningful title is at least a few
    characters and not a single punctuation mark.
    """
    if not title or len(title) < 4 or len(title) > 60:
        return False
    return any(ch.isalnum() for ch in title)


ACCEPTANCE_NOTE = (
    "[Kabul] İş listende hâlâ açık maddeler var: {ozet}. Bitti demeden "
    "önce her birini ya tamamla (mind_goals ile kapat) ya da neden açık "
    "kaldığını tek cümleyle söyle — plan maddesi sessizce düşmez."
)


# -- the RUN-what-you-delivered gate -------------------------------------
#
# The sharpest finding of the measurement: a task was delivered with 14
# passing tests, 18 real assertions and code health 20/20 — and the command
# line the prompt actually asked for did NOT work at all. `py ara.py bul
# "salmastra"` printed its own usage line on every query and exited with 1.
# The tests had covered the internal functions; nothing had touched the
# entry point the user would type.
#
# This case gets PAST the red gate: the suite was green, there was nothing
# to stop it there. The only thing that catches it is running the delivered
# thing the way the user would run it.
#
# The gate is kept narrow. Only a file that DECLARES ITSELF TO BE RUN
# counts: a `__main__` block, `sys.argv`/`argparse`, `process.argv`, PHP
# `$argv`. A library module, a class file, a configuration does not carry
# that — running those directly would be wrong anyway.

_ENTRY_MARKS = (
    re.compile(r"""if\s+__name__\s*==\s*['"]__main__['"]"""),
    re.compile(r"\bsys\.argv\b|\bargparse\b|\bclick\.command\b"),
    re.compile(r"\bprocess\.argv\b|\brequire\.main\s*===\s*module\b"),
    re.compile(r"\$argv\b|\bgetopt\b"),
)

# Files that could be an entry point. HTML/CSS/JSON are out: "running" those
# is a different thing (the browser gate's job) and must not be mixed in.
_RUNNABLE_SUFFIXES = frozenset({".py", ".js", ".mjs", ".cjs", ".ts", ".php", ".sh", ".ps1"})


def is_entry_point(text: str) -> bool:
    """Does this file declare itself to be run from the command line?"""
    return any(d.search(text or "") for d in _ENTRY_MARKS)


TEST_NOTE = (
    "[Doğrulama] Bu turda test dosyası yazdın ({dosya}) ama onu hiç "
    "KOŞMADIN. Yazılmış ama koşulmamış test, test değildir — kırmızı da "
    "olabilir. Bitti demeden önce test komutunu çalıştır; kırmızıysa "
    "düzelt, yeşilse turu kapat."
)

ENTRY_NOTE = (
    "[Doğrulama] Bu turda {dosya} yazdın ve o dosya kendini komut "
    "satırından çalıştırılmak üzere ilan ediyor — ama onu hiç "
    "ÇALIŞTIRMADIN. Testlerin yeşil olması yetmiyor: testler iç "
    "fonksiyonları çağırıyor, kullanıcı ise komutu yazıyor. Bitti demeden "
    "önce kullanıcının yazacağı komutu aynen çalıştır ve çıktısına bak."
)


# Long-run checkpoint: a soft nudge — if the acceptance criterion is met,
# `end_turn` is free. The old "don't stop before the job is done" pushed
# long scanning jobs into an endless loop.
CHECKPOINT_NOTE = (
    "[Uzun koşu kontrol noktası — {turns} tur] Bir-iki cümleyle ilerleme "
    "durumunu yaz (ne bitti, ne kaldı) — bu satırı kullanıcıya da yaz. "
    "Kabul ölçütü sağlandıysa araç çağırmadan bitir (`end_turn`). "
    "Eksik kaldıysa yalnız eksikleri tamamla; aynı tarama/doğrulama "
    "ritüelini tekrarlama."
)


# -- park record -----------------------------------------------------------
#
# On a model outage the state of the run is already on disk (session jsonl +
# notes); the park record is only the "there is a half-done job and it is
# waiting" marker. If seen at startup the run is resumed automatically; if
# the user interrupts or the job finishes it is deleted.


def read_park(state_dir: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads((state_dir / PARK_FILE).read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) and raw.get("session") else None
    except (OSError, ValueError):
        return None


def write_park(state_dir: Path, session_id: str, reason: str) -> None:
    (state_dir / PARK_FILE).write_text(
        json.dumps({"session": session_id, "ts": time.time(),
                    "reason": (reason or "")[:300]}, ensure_ascii=False),
        encoding="utf-8")


def clear_park(state_dir: Path) -> None:
    try:
        (state_dir / PARK_FILE).unlink(missing_ok=True)
    except OSError:
        pass


# -- orphan helpers --------------------------------------------------------
#
# When the app closes, helpers running in the background die with the
# process: the main session's log has a subagent_start but no subagent_end.
# If nothing is said to the user, the morning brings "I don't know what
# happened". At startup this trace is scanned (yetim_tara), the user and the
# model are told once, and a subagent_end(orphaned=True) is written to the
# child's log (mark_orphan) — so the second startup does not report the same
# orphan again.

# File cap of the scan: the last this-many session logs are looked at. There
# is no point in reading a year's archive end to end at every startup;
# orphans are by nature in the most recent sessions.
ORPHAN_SCAN_LIMIT = 40


def _read_log(path: Path) -> list[dict[str, Any]]:
    """Reads a session log as raw lines — best effort.

    A hard-killed process may have left the last line half written; a broken
    line is skipped silently. `EventLog` is deliberately not used here: it
    raises ValueError on the broken line and the startup scan is a
    diagnosis, not a repair.
    """
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict):
            out.append(ev)
    return out


def _is_child_log(events: list[dict[str, Any]]) -> bool:
    """Does a log belong to a child (subagent) session?

    One of the child session's first notes is a subagent_start with a
    parent — the note of the same name in the main session has session (the
    child's id) rather than parent.
    """
    return any(
        ev.get("content") == "subagent_start" and (ev.get("meta") or {}).get("parent")
        for ev in events
    )


def yetim_tara(sessions_dir: Path | str) -> list[dict[str, str]]:
    """Finds the helpers orphaned by the previous session(s).

    Children with a subagent_start in the main session logs but no matching
    subagent_end are looked for (the child session id is in the start note's
    meta). Matching is by id; old records (from before the end note carried
    a session) match by title. If the child's own log has any subagent_end
    (a normal ending or the orphaned mark of a previous startup) it is not
    counted as an orphan.

    Best effort: on an unreadable/broken log, silently an empty list — the
    startup scan must not bring the app down.
    """
    try:
        files = sorted(Path(sessions_dir).glob("*.jsonl"))[-ORPHAN_SCAN_LIMIT:]
        candidates: list[dict[str, str]] = []
        for path in files:
            try:
                events = _read_log(path)
            except OSError:
                continue
            if _is_child_log(events):
                continue
            # Children opened by this main session: a start whose end was
            # seen drops out.
            starts: list[dict[str, str]] = []
            for ev in events:
                if ev.get("kind") != "meta":
                    continue
                meta = ev.get("meta") or {}
                if ev.get("content") == "subagent_start" and meta.get("session"):
                    starts.append({
                        "title": str(meta.get("title") or ""),
                        "session": str(meta["session"]),
                    })
                elif ev.get("content") in ("subagent_end", "subagent_failed"):
                    # subagent_failed is a closing too: the crashed helper
                    # was already reported, don't announce it as an orphan
                    # on top.
                    sid = str(meta.get("session") or "")
                    title = str(meta.get("title") or "")
                    for i, s in enumerate(starts):
                        if s["session"] == sid or (not sid and s["title"] == title):
                            del starts[i]
                            break
            candidates.extend(starts)

        orphans: list[dict[str, str]] = []
        for candidate in candidates:
            child = Path(sessions_dir) / f"{candidate['session']}.jsonl"
            if not child.is_file():
                # The session file was never born: there is no trace to
                # resume either.
                continue
            try:
                child_events = _read_log(child)
            except OSError:
                continue
            if any(ev.get("content") == "subagent_end" for ev in child_events):
                continue   # marked at a previous startup, or closed
            orphans.append(candidate)
        return orphans
    except Exception:
        return []


def mark_orphan(sessions_dir: Path | str, orphans: list[dict[str, str]]) -> None:
    """Writes subagent_end(orphaned=True) into the orphans' child logs.

    The mark is a tombstone: the next startup must not report the same
    helper as "left half done" again. The session stays on disk — `task_say`
    can still revive it if asked.
    """
    from .events import EventLog

    for y in orphans:
        path = Path(sessions_dir) / f"{y['session']}.jsonl"
        try:
            log = EventLog(path)
            log.note("subagent_end", title=y["title"], orphaned=True)
            log.close()
        except Exception:
            # A hard shutdown may have left the last line half written and
            # EventLog does not open on a broken line. The mark must still
            # land — otherwise the same orphan is reported at every startup.
            # The line is appended by hand; the scan (yetim_tara) reads raw
            # JSON so it sees it.
            try:
                with path.open("a", encoding="utf-8") as fh:
                    fh.write("\n" + json.dumps({
                        "seq": -1, "ts": time.time(), "kind": "meta",
                        "role": None, "content": "subagent_end",
                        "meta": {"title": y["title"], "orphaned": True},
                    }, ensure_ascii=False) + "\n")
            except OSError:
                continue   # one broken log must not block the others


@dataclass(slots=True)
class AgentIO:
    """The single contact surface between the harness and the UI."""

    on_text: Callable[[str], None] = lambda _: None
    on_thinking: Callable[[str], None] = lambda _: None
    on_tool_start: Callable[[str, dict[str, Any]], None] = lambda *_: None
    on_tool_end: Callable[[str, bool, int], None] = lambda *_: None
    on_notice: Callable[[str], None] = lambda _: None
    # The STRUCTURED channel of the waiting state during a model outage. The
    # UI draws it as a single live line in the work strip (countdown, retry
    # counter, collapsible detail) — no raw error wall is printed into the
    # chat. If it stays None (CLI, tests) the old plain-text on_notice path
    # applies.
    # Contract: {"kip": "deneme"|"park"|"bitti"|"iptal",
    #            "deneme": int, "toplam": int, "saniye": int, "detay": str}
    on_wait: Callable[[dict[str, Any]], None] | None = None
    on_usage: Callable[[dict[str, int]], None] = lambda _: None
    # The session title set by the model — the sidebar list updates at once.
    on_session_title: Callable[[str, str], None] = lambda *_: None  # sid, name
    # Budget brake. Asked BEFORE every model call: an empty string means "no
    # limit or not exceeded", a non-empty string is the single line to print
    # into the chat plus a "stop" order. The price information lives in the
    # bridge, not the harness (see desktop.Bridge._budget_brake) — the loop
    # only asks for the decision and does no network request or price-table
    # read on the turn path.
    butce_freni: Callable[[], str] = lambda: ""
    # Subagent (orchestra) channels: when a subagent is born, when it calls
    # a tool and when it ends. The UI draws these as a live channel; "who is
    # doing what" becomes visible without mixing into the main chat. Default
    # empty: callers that use no subagents (tests, text-only) are unaffected.
    on_child_start: Callable[[str, str, str, bool], None] = lambda *_: None  # title, model, id, bg
    on_child_tool: Callable[..., None] = lambda *_: None  # title, tool, phase, target=""
    on_child_end: Callable[[str, bool, int, int, str, str], None] = lambda *_: None  # title, ok, turns, tools, id, summary
    # Subagent wait/retry (empty model reply etc.) — panel channel.
    on_child_wait: Callable[[dict[str, Any]], None] | None = None
    approve: Callable[[ToolSpec, dict[str, Any]], Awaitable[bool]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.approve is None:
            async def deny_all(spec: ToolSpec, args: dict[str, Any]) -> bool:
                return False

            self.approve = deny_all


@dataclass(slots=True)
class ChildHandle:
    """A helper's ledger record.

    A synchronous helper is written here too (so task_say can resume a
    finished helper) but the real customer is the background helper: the
    `task` tool returns immediately, the work is tracked through this record
    and when it finishes the result is reported from here.
    """

    id: str
    title: str
    model: str
    # "yardımcı": a model-running subagent · "iş": a background process (long
    # command). Both share the same ledger and the same notification path.
    kind: str = "yardımcı"
    arka_plan: bool = False
    session_id: str = ""
    state: str = "kosuyor"          # kosuyor | bitti | hata
    sonuc: str = ""
    # When it started. The record is created the moment the work starts, so
    # the default "now" is the right answer: the tasks panel counts the
    # duration live from here ("2 dk 14 sn"). In orphan records (inherited
    # from the previous session) the real start is unknown; the panel draws
    # no duration there.
    baslangic_ts: float = field(default_factory=time.time)
    bitis_ts: float = 0.0
    # Has the result been announced to the main agent. On the synchronous
    # path the tool result already returned; in the background the
    # notification note at the start of the turn sets this True.
    bildirildi: bool = False
    # Reference to the background task: an unreferenced asyncio.Task can go
    # to the garbage collector and the work silently disappears.
    task: asyncio.Task | None = None
    # The live agent object while running (the task_say note goes to it);
    # None when finished.
    agent: "Agent | None" = None
    # The child's OWN cancel flag. Sharing the parent's did not work: the
    # parent refreshes its flag on every `run` and the background child was
    # left ownerless on the old flag. The parent's `interrupt()` sets them
    # all as derivatives.
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    # Scheduled task id (if any): written to the ledger when finished.
    schedule_id: str = ""
    # Silent: when finished the main agent does NOT open a resume turn — the
    # report stays in the panels. For scheduled jobs: a task area, not chat
    # Q&A.
    sessiz: bool = False
    # Run id in the task_runs archive.
    run_id: str = ""
    # Automation workflow id (if any).
    workflow_id: str = ""
    # Deliverable to open on finish: {kind: app|artifact|json|text, url?, body?}
    deliverable: dict[str, Any] | None = None
    # Live panel: last tool name / model wait state.
    son_arac: str = ""
    son_hedef: str = ""
    wait: dict[str, Any] | None = None
    # Run meter: {girdi, cikti, cagri} — same units as the chat dock.
    usage: dict[str, int] = field(
        default_factory=lambda: {"girdi": 0, "cikti": 0, "cagri": 0})
    # Mid-run task_runs.patch_run throttle.
    last_patch_ts: float = 0.0
    # How many tool calls started (panel + run archive).
    tools_count: int = 0


@dataclass(slots=True)
class TurnStats:
    turns: int = 0
    tool_calls: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    interrupted: bool = False
    stop_reason: str | None = None
    # How many consecutive model calls failed. Reset on a successful turn;
    # the backoff ladder and the park decision look at this.
    api_errors: int = 0
    # Number of turns that hit the ceiling and were continued.
    continuations: int = 0
    # Was the closing turn given. Once: otherwise the locked-up loop locks
    # up in the closing turn too and comes back to the same place.
    closing: bool = False
    # How many times in this turn the model wrote a tool call as PLAIN TEXT
    # (XML instead of a real call). If it repeats, the note hardens.
    sahte_cagri: int = 0
    # Was the red gate opened once in this turn. At most once: if the model
    # wants to finish again on the second turn it is let go — no endless
    # loop.
    kirmizi_uyarildi: bool = False
    kabul_uyarildi: bool = False
    test_warned: bool = False
    # Was the run-what-you-delivered gate opened in this turn. Once, for the
    # same reason.
    giris_uyarildi: bool = False
    # Subagent: model error text after max retries (instead of parking).
    fail_reason: str | None = None


def _without_numbers(text: str) -> str:
    """Strips numbers from the priming query.

    A message that wants to add a device carries an IP, a port and a
    register address, and these pull in every numbered record in the mind.
    What the user saw was BTC price measurements being scanned while saying
    "modbus cihazı ekle".
    """
    return _NUMERIC.sub(" ", text or "").strip()


class Agent:
    def __init__(
        self,
        *,
        config: Config,
        session: Session,
        registry: ToolRegistry,
        client: Backend,
        io: AgentIO,
        permissions: PermissionEngine | None = None,
        policy: ContextPolicy | None = None,
        mind: Any = None,
        depth: int = 0,
        cancel: asyncio.Event | None = None,
        schedule: Any = None,
        lens: Any = None,
    ) -> None:
        self.config = config
        self.session = session
        self.registry = registry
        self.client = client
        self.io = io
        self.mind = mind
        # 0 main agent, 1 subagent. The depth also decides whether the
        # `task` tool exists.
        self.depth = depth
        # Scheduled-task ledger; the `schedule` tool reads from here.
        self.schedule = schedule
        # The local camera's buffer; the `look` tool takes frames from here.
        self.lens = lens
        self.camera_power: Any = None
        # The ear and the watcher are attached later on the desktop side
        # (at startup the agent is built before them); the `senses` tool
        # reaches them from here.
        self.ear: Any = None
        self.watcher: Any = None
        self.permissions = permissions or PermissionEngine.from_config(config.permissions)
        self.policy = policy or ContextPolicy(config.context)
        # The cancel flag can be given from outside: the subagent shares the
        # main agent's. Without sharing it would keep working in the
        # background when the user says stop.
        self.cancel = cancel or asyncio.Event()
        self._owns_cancel = cancel is None
        # The soul is loaded once at session start and stays fixed for the
        # whole session. Fixed is a must: it is part of the system prompt,
        # and if it changes mid-way the whole cache from that point on is
        # lost. New memories saved during the session enter the soul at the
        # next startup.
        self.soul = mind.soul(persona=prompt.read_persona(config)) if mind else None
        self._system = prompt.build(config, registry, soul=self.soul)
        self._last_goal_digest = self.mind.goal_digest() if mind else ""
        # The usage report of the last turn. The compaction decision looks
        # at it; counting tokens before the request would have meant the
        # cost of an extra round trip.
        self._last_usage: dict[str, int] = {}
        # Narrow-window model: the system prompt gets shorter, tool
        # descriptions drop to a single paragraph, recall priming shrinks.
        # On a 4096-token model there is no room left for conversation
        # without these.
        self.lean = prompt.is_lean(config)
        # Small family: brief schema (~6k) instead of the full schema (~11k
        # tokens). The narrow window was already brief; the flash class
        # deserves brief on a wide window too — in the comparison this was
        # the main item of the per-turn payload.
        self.brief_schema = self.lean or prompt.kucuk_aile(config.model.name)
        # A wrong window setting is said once and left: repeating it every
        # turn turns the warning into noise.
        self._window_warned = False
        # Extra clients built for subagents; stored by model name so that
        # asking for the same model three times does not open three
        # connection pools.
        self._clients: dict[str, tuple[Any, Config]] = {}
        # Prevents writing the same text twice back to back in instant
        # encoding.
        self._last_encoded: str = ""
        # Memories already placed in front of the model in this session. The
        # old note STAYS in the history (messages are replayed from the
        # start on every request); re-injecting the same memory gives the
        # model no new information, it only burns tokens. Reset on
        # compaction — when the notes fold into the summary the right comes
        # back.
        #
        # The set starts with the soul: records the soul put into the prompt
        # WITH THEIR FULL BODY (user/preference/lesson/voice) are also
        # "already in context". Measured (scale_bench): same hit rate with
        # ~9% fewer tokens per query, and some of the tea-preference-type
        # leaks into a "how is the weather" question go quiet by themselves.
        # Procedures do not enter — the soul has only their titles, their
        # bodies are still valuable in priming.
        self._primed: set[str] = self._soul_resident()
        # Subagent gate: at most `max_agents` helpers run at the same time.
        # A spawn over the limit is not refused, it queues — when the model
        # hands out five jobs all five get done, but without crushing the
        # machine. Separate from the tool limit (max_parallel) because a
        # subagent is far heavier than a single tool.
        self._agent_gate = asyncio.Semaphore(
            max(1, getattr(config.context, "max_agents", 3)))
        # Helper ledger: id → record. Those running in the background, the
        # finished ones and (for task_say) those that ran synchronously are
        # here.
        self._children: dict[str, ChildHandle] = {}
        # Mid-turn inbox: user messages that barge in before the running
        # turn ends (and in a child: task_say notes). Drained at the start
        # of every turn and entered into the history as a harness note.
        self._inbox: deque[str] = deque()
        # When a helper finishes, tell the bridge (if any): if the main
        # agent is idle the bridge opens a resume turn. The desktop layer
        # attaches it.
        self.on_children_settled: Callable[[], None] | None = None
        # Called before every retry during a model outage. The bridge
        # attaches here the call that applies a pending model/setting
        # change: if a broken address/key was fixed, the new client only
        # takes effect this way (normally a change waits for the END of the
        # turn, and a parked turn does not end).
        self.on_retry_wait: Callable[[], None] | None = None
        # Is the job parked (model unreachable, waiting).
        self._parked = False
        # Mind-writing reflex (see _mind_gate): did the model write to its
        # own ledger in this turn, and for which sentence it was last
        # nudged.
        self._mind_written = False
        self._last_nudge = ""
        # Red ledger: verification tool → that tool's last RED trace. Kept
        # per tool so that when the model fixes and re-runs the record is
        # cleared — a run that turned green is no longer red. Reset on every
        # user turn (see run).
        self._kirmizi: dict[str, str] = {}
        # Delivery ledger: the file paths WRITTEN in this turn and the text
        # of the commands RUN in this turn. The gate compares the two — is
        # there an entry point you wrote but never ran? Reset on every user
        # turn (see run).
        self._written: list[str] = []
        self._commands: list[str] = []
        # Error-pattern counter (per run): the SECOND fall into the same
        # pattern is a lesson.
        self._error_patterns: dict[str, int] = {}
        self._capsule_written = False

    def _soul_resident(self) -> set[str]:
        """Ids of the records the soul put into the prompt with their full body."""
        if self.soul is None:
            return set()
        return {
            m.id
            for group in (self.soul.user, self.soul.preferences,
                          self.soul.lessons, self.soul.voice)
            for m in group
        }

    @property
    def system_prompt(self) -> str:
        return self._system.rendered()

    def reconfigure(self, config: Config) -> None:
        """Rebuilds the core when settings change — without a restart.

        When the model changes the window size can change too (200k Claude
        ↔ 4096 local): then the `lean` decision, the tool schemas sent and
        the environment/senses/device summary in the system prompt must all
        change. `Bridge` already swaps the client; here we refresh the rest.

        **The soul stays untouched.** The identity block must stay fixed
        for the whole session (the cache prefix match depends on it) and the
        user name and introduction context learned mid-session must not be
        lost. Only `core` is rebuilt; `soul` passes through as the same
        object.

        Must not be called mid-turn: pulling the schemas out from under a
        streaming request corrupts that answer. `Bridge` applies this when
        the turn ends.
        """
        self.config = config
        self.policy = ContextPolicy(config.context)
        self.lean = prompt.is_lean(config)
        self.brief_schema = self.lean or prompt.kucuk_aile(config.model.name)
        self._system = prompt.build(config, self.registry, soul=self.soul)

    def interrupt(self) -> None:
        """Stop: stops the main turn AND every running helper.

        The user's expectation is "stop = everything stops". The helpers'
        flags are separate (see ChildHandle.cancel) but the decision is
        derived: it fans out to all of them from here.
        """
        self.cancel.set()
        for handle in self._children.values():
            if handle.state == "kosuyor":
                handle.cancel.set()

    def take_note(self, note: str, *, encode: str = "") -> None:
        """A harness note that enters the next step of the running turn.

        A user message barging in mid-turn (from the bridge) and a direction
        given to a running helper with `task_say` enter from here. The note
        queue is drained at the start of every turn; if the turn has ended
        by then one more step is given so the message is not lost.

        If `encode` is non-empty the text is also written to instant memory
        — a word that barged in is still a word that was said.
        """
        self._inbox.append(note)
        if encode:
            self._encode_turn("kullanıcı", encode)

    def inbox_full(self) -> bool:
        """Has the inbox overflowed? If full, the bridge falls back to the old queue path."""
        return len(self._inbox) >= 8

    def _arm(self) -> None:
        """Resets the interrupt for a new request.

        If the flag came from outside it is not touched: resetting it would
        silently cancel the sharing side's stop decision.
        """
        if self._owns_cancel:
            self.cancel = asyncio.Event()

    # -- main flow -----------------------------------------------------

    async def run(self, user_input: str, image: str = "") -> TurnStats:
        """Runs one user request from start to finish.

        If `image` is given (a base64 data URL) it is added to the message
        as an image block — the camera frame enters this way. If the model
        does not accept images the provider layer turns that into an
        understandable error.
        """
        self._arm()
        if image:
            self.session.add_user_blocks(_with_image(user_input, image))
        else:
            self.session.add_user_text(user_input)
        # Reply language: the language of the user's THIS message. The rule
        # in the identity block alone was not enough — because the whole
        # system prompt, most of the memories and the past turns are
        # Turkish, the model replied in Turkish even when the user wrote in
        # English (live wound, 02.09). The reminder is per turn, at the
        # place the model reads LAST: the recency rule wins.
        self._language_note(user_input)
        # What the user said goes to memory that instant: now, not at night.
        self._encode_turn("kullanıcı", user_input)
        self._prime_recall(user_input)
        # The gate of the writing reflex: did the model write to its own
        # ledger in this turn?
        self._mind_written = False
        # Plan reflex: if the job looks big, a one-line note in front of the
        # model. BEFORE the FIRST model call and once per turn — reminding
        # later is pointless, a plan is not written after the order.
        self._plan_reflex(user_input)
        # The red ledger starts from scratch on every user turn: only "red
        # produced in THIS TURN" counts, not the previous turn's red.
        self._kirmizi.clear()
        # The delivery ledgers also start from scratch every turn: a file
        # written and run in the previous turn is not this turn's debt.
        self._written.clear()
        self._commands.clear()
        self._error_patterns.clear()
        self._capsule_written = False
        stats = await self._drive()
        self._mind_gate(user_input)
        return stats

    def _plan_reflex(self, user_input: str) -> None:
        """Puts the plan order in front of the model on a big/open-ended request.

        Only in the main agent (`depth == 0`): the instruction given to a
        subagent is already a narrow, defined job; asking it for a module
        plan is noise.
        """
        if self.depth or not buyuk_is(user_input):
            return
        # The plan is the job of the job's BEGINNING. While the work is
        # already under way (open items in the ledger or a previous exchange
        # in the session) the nudge talks nonsense: live, a "from scratch"
        # plan card popped up in the middle of a 240-turn run — with 97
        # files changed. In a running job the gates (acceptance/entry) are
        # already active.
        try:
            if self.mind is not None and self.mind.goals(active_only=True):
                return
        except Exception:
            pass
        if sum(1 for m in self.session.messages()
               if m.get("role") == "user") > 1:
            return
        self.session.add_harness_note(PLAN_NOTU)
        self.session.log.note("plan_refleksi")

    def _delivery_trace(self, tool: str, args: dict[str, Any]) -> None:
        """What was written, what was run in this turn — the two ledgers the gate reads."""
        if tool in ("write_file", "edit_file"):
            if path := str(args.get("path") or "").strip():
                self._written.append(path)
        elif tool in ("shell", "kos"):
            # `kos` finds its command by itself; what it ran may not be in
            # the argument either, so the path/pattern fields are collected
            # too.
            for key in ("command", "cmd", "path", "hedef", "argv"):
                if (value := args.get(key)) is not None:
                    self._commands.append(str(value))

    def _unrun_test(self) -> str:
        """The name of a test file written but never run, if any, else empty.

        Measured wound (28.08 nine-task, o2): a test file was written, never
        run, came out RED and was delivered — the red gate only sees a test
        that was run. If the test name appears in any command (the pytest
        path runs in bulk: `pytest`, `pytest .`) it counts as run; a bare
        `pytest`/`node --test` call also covers all of them.
        """
        command_text = "\n".join(self._commands)
        # Bulk runners: a bare pytest / node --test covers every test file —
        # it counts as run even if the file name is not in the command.
        bulk = ("pytest" in command_text or "node --test" in command_text
                or "node --run" in command_text)
        for path in self._written:
            name = Path(path).name
            if not (name.startswith("test_") or name.endswith((".test.js", ".spec.js"))
                    or name.endswith("_test.py")):
                continue
            if bulk or (name and name in command_text):
                continue
            return name
        return ""

    def _test_gate(self, stats: TurnStats, blocks: list[dict[str, Any]]) -> bool:
        """If "done" is said with a written-but-unrun test, one turn is handed back."""
        if stats.test_warned or self.depth:
            return False
        if not done_claim(_text_of_blocks(blocks)):
            return False
        file = self._unrun_test()
        if not file:
            return False
        stats.test_warned = True
        self.session.log.note("test_kapisi", dosya=file)
        self.session.add_harness_note(TEST_NOTE.format(dosya=file))
        return True

    def _unrun_entry_point(self) -> str:
        """The path of an entry point written but never run, if any.

        The file is read from disk: the answer to "did it declare itself to
        be run" is in its content. An unreadable file does not count —
        nudging the model for something we are not sure of is wrong.
        """
        command_text = "\n".join(self._commands)
        for path in self._written:
            p = Path(path)
            if p.suffix.lower() not in _RUNNABLE_SUFFIXES:
                continue
            # If its name appears in any command it counts as run.
            if p.name and p.name in command_text:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if is_entry_point(text):
                return p.name
        return ""

    def _entry_gate(self, stats: TurnStats, blocks: list[dict[str, Any]]) -> bool:
        """If "done" is said without ever running the written entry point, one more turn.

        If it returns True the turn CONTINUES. The same three brakes as the
        red gate:
          * There has to be a file written in this turn that declares itself
            runnable and was never run.
          * The answer has to be tool-less (`end_turn`) and declare the job
            finished — an honest answer that already says what is missing
            is not nudged.
          * AT MOST ONCE per turn.
        """
        if stats.giris_uyarildi or not self._written:
            return False
        if not done_claim(_text_of_blocks(blocks)):
            return False
        file = self._unrun_entry_point()
        if not file:
            return False
        stats.giris_uyarildi = True
        self.session.log.note("giris_kapisi", dosya=file)
        self.session.add_harness_note(ENTRY_NOTE.format(dosya=file))
        return True

    def _red_gate(self, stats: TurnStats, blocks: list[dict[str, Any]]) -> bool:
        """If "done" is said on top of a red run, give one more turn.

        If it returns True the turn CONTINUES. There are three brakes:
          * There has to be a red run produced in this turn.
          * The answer has to be tool-less (`end_turn`) and genuinely
            declare it finished — an honest answer that already admits the
            red is not nudged.
          * AT MOST ONCE per turn. If the model wants to finish again on
            the second turn it is let go; an endless "no, it's not done"
            loop is worse than a half answer.
        """
        if stats.kirmizi_uyarildi or not self._kirmizi:
            return False
        if not done_claim(_text_of_blocks(blocks)):
            return False
        stats.kirmizi_uyarildi = True
        summary = "; ".join(self._kirmizi.values())[:200]
        self.session.log.note("kirmizi_kapisi", ozet=summary)
        self.session.add_harness_note(KIRMIZI_NOTU.format(ozet=summary))
        return True

    def _acceptance_gate(self, stats: TurnStats, blocks: list[dict[str, Any]]) -> bool:
        """If "done" is said while there are open job items, give one more turn.

        Same contract as the red gate: only on a tool-less finishing answer,
        AT MOST ONCE per turn, and only if there really are open items.
        Subagents are exempt — the ledger belongs to the main run.
        """
        if stats.kabul_uyarildi or self.depth or self.mind is None:
            return False
        if not done_claim(_text_of_blocks(blocks)):
            return False
        try:
            open_items = [g.text for g in self.mind.goals(active_only=True)]
        except Exception:
            return False
        if not open_items:
            return False
        stats.kabul_uyarildi = True
        summary = "; ".join(t[:60] for t in open_items[:5])
        if len(open_items) > 5:
            summary += f"; (+{len(open_items) - 5})"
        self.session.log.note("kabul_kapisi", acik=len(open_items))
        self.session.add_harness_note(ACCEPTANCE_NOTE.format(ozet=summary))
        return True

    def _mind_gate(self, user_input: str) -> None:
        """End-of-turn reflex: if something persistent came up and the model did not write, nudge.

        The sibling and the inverse of `_prime_recall`: that one triggers
        recall from the system, this one triggers writing. The note is put
        in FRONT of the model (harness channel, `internal` — invisible in
        the chat); the decision is still the model's.

        There are three brakes: no nudge if the model already wrote
        (needless), no nudge without the scent (noise), and no back-to-back
        nudging (fatigue) — the note is not repeated unless the user said
        something new.
        """
        if self.depth or self.mind is None or self._mind_written:
            return
        if not persistent_root(user_input):
            return
        quote = _one_line(user_input)[:NUDGE_QUOTE_CHARS]
        if quote == self._last_nudge:
            return   # nudging a second time on the same topic is fatigue
        self._last_nudge = quote
        self.session.add_harness_note(MIND_NUDGE.format(alinti=quote))
        self.session.log.note("zihin_durtusu")

    def _encode_turn(self, role: str, text: str) -> None:
        """Writes a conversation turn to searchable memory **instantly**.

        Fatih's core requirement: "when someone says something it must stay
        in memory right away" — not at night, at that moment. Human memory
        encodes the same way (the hippocampus writes in one shot);
        consolidation is separate and slow.

        It has to be fast on a machine without a GPU and it is: the
        signature is pure hashing (no torch), the full write path ~2 ms.
        That is why it runs synchronously and the user feels no delay. The
        record is of kind `episode`: it does not mix with the curated
        `mind_memory` facts (it enters neither the soul nor spontaneous
        priming) but can be found with `mind_recall`.

        Noise gate: very short turns ("evet", "tamam") and greetings are not
        written; if the same text came twice in a row it is skipped. A
        write error must NEVER bring the conversation down — memory misses
        at most one turn.
        """
        if self.mind is None:
            return
        body = (text or "").strip()
        if len(body) < ENCODE_MIN_CHARS or not self._worth_recalling(body):
            return
        if body == self._last_encoded:
            return
        self._last_encoded = body
        try:
            self.mind.remember(
                body, kind="episode",
                title=f"{role}: {_one_line(body)}"[:140],
            )
        except Exception as exc:  # a memory write must not bring the conversation down
            self.session.log.note("encode_turn_failed", error=str(exc))

    # Letters specific to Turkish: a crude but sufficient distinction. The
    # aim is not to "detect" the language but to remind the model which
    # language was written in.
    _TR_LETTERS = set("çğıöşüÇĞİÖŞÜ")

    def _language_note(self, user_input: str) -> None:
        """Prepares this turn's reply-language reminder.

        NOT written to the session log — only attached to this turn's
        request (see `_add_language_reminder`). Writing it to the log broke
        two things: it used up the "one system note per turn" quota and
        blocked the RECALL note (`_prime_recall`), and it left a technical
        line in the user's transcript every turn.
        """
        body = (user_input or "").strip()
        if len(body) < 8:
            self._language_reminder = ""   # language inference on a single word is meaningless
            return
        if self._TR_LETTERS & set(body):
            self._language_reminder = (
                "Bu turda kullanıcı TÜRKÇE yazdı — cevabın, ara anlatımların "
                "ve ürettiğin dosyaların içeriği Türkçe olsun.")
        else:
            self._language_reminder = (
                "This turn the user wrote in a language other than Turkish "
                "(most likely English). Reply in the SAME language they used — "
                "your answer, your progress notes and the contents of any file "
                "you produce. Do not switch to Turkish just because your "
                "instructions are written in Turkish.")

    def _add_language_reminder(self, prepared: Any) -> None:
        """Puts the language reminder at the END of the request as a temporary
        system message. The cache is not broken: it sits after the last
        breakpoint."""
        note = getattr(self, "_language_reminder", "")
        if not note:
            return
        try:
            prepared.messages.append(
                {"role": "system", "content": [{"type": "text", "text": note}]})
        except Exception:
            pass

    def _prime_recall(self, user_input: str) -> None:
        """Searches the user's message in the mind and puts the findings in front of it.

        Leaving it as a tool was not enough: the model first had to notice
        that it should recall, most of the time it did not, and it answered
        as if it did not know something it already knew. Here the reverse is
        done — recall runs without being asked; when the model sits down at
        the table the relevant memories are already in front of it.

        What makes this possible is that recall is cheap: the inverted index
        and the signature scan take a few milliseconds, no extra model turn.
        Had it been a tool call it would have meant one more round trip per
        message.
        """
        if self.mind is None or not self._worth_recalling(user_input):
            return
        try:
            # Writer: before the search the query is expanded to synonymous
            # terms with the small local model (synonym class 0.50→1.00, hit
            # rate 0.87→0.93 — scale_bench). Without the model
            # zenginlestir returns the query unchanged.
            from .recall import writer
            query = writer.zenginlestir(user_input, getattr(self.config, "state_dir", None))
            limit = LEAN_PRIME_LIMIT if self.lean else RECALL_PRIME_LIMIT
            hits = select_prime(self.mind, query, limit=limit, ham=user_input)
        except Exception as exc:  # if recall crashed the conversation must still go on
            self.session.log.note("recall_prime_failed", error=str(exc))
            return

        # A memory already placed in front is not re-injected: the old note
        # stays in the history, the model still sees it.
        hits = [h for h in hits if h.item.id not in self._primed]
        if not hits:
            return
        self._primed.update(h.item.id for h in hits)
        self.session.add_system_note(prime_note(hits))
        # The night replay (recall/weave.py) reads this note: a record placed
        # in front also counts as "touched" — the model saw it, used it in
        # that turn.
        self.session.log.note("prime", ids=[h.item.id for h in hits],
                              query=_one_line(user_input, 120))

        # The UI must be able to animate this walk too: the user watches step
        # by step what the model recalled from where. The same event as
        # tool-driven recall is emitted; the UI does not distinguish.
        if trace := getattr(self.mind, "last_trace", None):
            # Scanned and used are not the same thing. The mind touches
            # dozens of records in one query and lighting them all up on
            # screen looks like "it mixed everything up" — whereas what was
            # put in front is only what passed the filter.
            used = {hit.item.id for hit in hits}
            from .mind.tools import _step_label
            self.session.log.note(
                "recall_trace",
                query=user_input,
                trace=[{**asdict(step), "used": step.node in used,
                        "label": _step_label(self.mind, step.node)}
                       for step in trace],
            )

    def _awake_reverse_replay(self, outcome: str) -> None:
        """Assigns responsibility the moment the outcome is known and writes the lesson at once.

        Not in the background, inside the turn: the replay of a single
        session on two hundred nodes is under fifty milliseconds (measured,
        tests/test_awake.py). If there is an error the chat must still go on
        — memory maintenance does not bring the conversation down.
        """
        if self.mind is None:
            return
        try:
            from .recall import awake

            awake.on_result(self.mind.store, self.session.log.path, outcome,
                            log=self.session.log)
        except Exception as exc:
            self.session.log.note("uyanik_tekrar_failed", error=str(exc))

    def _worth_recalling(self, text: str) -> bool:
        return worth_recalling(text)

    async def resume_after_interrupt(self) -> TurnStats:
        """Closes what was left unanswered after an interrupt and continues."""
        self._arm()
        self._settle_pending()
        return await self._drive()

    async def _drive(self) -> TurnStats:
        stats = TurnStats()
        ctx = ToolContext(
            config=self.config,
            session=self.session,
            cancel=self.cancel,
            # A subagent has no subagent: passing None makes the `task` tool
            # declare itself unavailable. The same limit applies to the
            # background and routing endpoints.
            spawn=self._spawn if self.depth < MAX_DEPTH else None,
            spawn_bg=self._spawn_bg if self.depth < MAX_DEPTH else None,
            child_say=self._child_say if self.depth < MAX_DEPTH else None,
            child_status=self._child_status if self.depth < MAX_DEPTH else None,
            # Long processes can only be backgrounded in the main agent: if
            # the subagent dies before the job ends nobody is left to
            # receive the notification.
            job_bg=self._job_bg if self.depth < MAX_DEPTH else None,
            schedule=self.schedule,
            run_workflow=self.run_workflow if self.depth < MAX_DEPTH else None,
            lens=self.lens,
            ear=self.ear,
            watcher=self.watcher,
            camera_power=getattr(self, "camera_power", None),
        )
        callbacks = Callbacks(
            on_text=self.io.on_text,
            on_thinking=self.io.on_thinking,
            on_tool_start=lambda name: None,
        )

        while stats.turns < HARD_TURN_LIMIT:
            # Budget brake: if the ceiling set for this session has been
            # reached, NO new model call is made. The interrupt goes the
            # existing way (`interrupt`: running helpers stop too) and the
            # half-done work is NOT LOST — the user message is in the
            # history, the notes in the inbox are in place, the session
            # stays as it is. When the limit is raised the conversation
            # continues where it left off.
            #
            # Only in the main agent: interrupting the subagent's own turn
            # separately would be interrupting twice the work the parent
            # already interrupted.
            if self.depth == 0 and (brake := self.io.butce_freni()):
                self.session.log.note("butce_freni", detay=_clip(brake, 200))
                self.io.on_notice(brake)
                self.interrupt()
                stats.interrupted = True
                break

            stats.turns += 1

            # Long-run checkpoint: the old hard ceiling (stop at turn 60) was
            # turned into a soft nudge — the agent writes a short progress
            # note and the WORK CONTINUES. The real brake is the user + the
            # absolute fuse.
            if stats.turns > 1 and stats.turns % MAX_TURNS == 0:
                self.session.log.note("turn_checkpoint", turns=stats.turns)
                self.session.add_harness_note(CHECKPOINT_NOTE.format(turns=stats.turns))
                self.io.on_notice(
                    f"Uzun koşu: {stats.turns} tur — ilerleme notu istendi, iş sürüyor.")

            await self._relieve_pressure()
            self._sync_goals()
            # Helpers that finished in the meantime and user messages that
            # barged in are put in front of the model at this step: at the
            # start of the turn, before the request goes out.
            self._drain_children()
            self._drain_inbox()
            # Pending model swap: without cutting the running stream, the
            # new client from the next call on (switching while busy too).
            if self.on_retry_wait is not None:
                try:
                    self.on_retry_wait()
                except Exception:
                    pass
            prepared = self.policy.prepare(self._system, self.session.messages())
            self._add_language_reminder(prepared)
            try:
                result = await self.client.turn(
                    prepared,
                    # The closing turn is tool-less: letting it call tools
                    # again means running one more turn of the loop that
                    # locked up.
                    [] if stats.closing else self.registry.api_schemas(brief=self.brief_schema),
                    cancel=self.cancel,
                    callbacks=callbacks,
                )
            except Exception as exc:
                # The connection could not be made at all (address down,
                # DNS, socket). The exception raised from here used to bring
                # the run down; now it enters the error path and retries.
                result = TurnResult(error=f"{type(exc).__name__}: {exc}")

            if result.interrupted:
                self.session.log.note("interrupted", stage="stream", dropped=result.partial_text)
                self.io.on_notice("Kesildi. Yarım kalan yanıt atıldı.")
                stats.interrupted = True
                break

            if result.error:
                self.session.log.note("api_error", detail=result.error)
                # A malformed request (400 etc.) is not fixed by retrying:
                # old behaviour. A transient error (connection, 5xx,
                # timeout, 429) does NOT KILL the long job: it retries with
                # backoff, then parks.
                if _fatal_error(result.error):
                    self.io.on_notice(result.error)
                    self._unpark()
                    break
                stats.api_errors += 1
                stats.turns -= 1   # a retry does not count as a turn; don't let the fuse slip
                if await self._await_model(stats, result.error):
                    continue
                stats.interrupted = True
                break

            if stats.api_errors:
                # The outage was survived: counter to zero, the park record
                # (if any) goes.
                attempts = stats.api_errors
                stats.api_errors = 0
                self._unpark()
                # If there is a strip the recovery lives in the strip too
                # (one green line); no separate notice lands in the chat.
                if not self._wait_event(kip="bitti", deneme=attempts):
                    self.io.on_notice("Model geri geldi — iş kaldığı yerden sürüyor.")

            report = cache_report(result.usage)
            stats.usage = report
            self._last_usage = report
            self.io.on_usage(report)

            # An assistant turn with empty content is not written to the
            # history: the turn is wasted and an empty content array can
            # also corrupt the next request. Refusal turns legitimately come
            # empty; the state is still handled below.
            # Fake tool call: the model wrote the XML as PLAIN TEXT instead
            # of a real call. Entering the history is right (the model must
            # see what it did) but it is NOT AN ANSWER to the user — marked
            # with `internal`, otherwise when the session is resumed the raw
            # XML came back as an agent message.
            fake_text = bool(
                result.content and result.stop_reason == "end_turn"
                and fake_tool_call(_text_of_blocks(result.content)))

            if blocks := result.content:
                # `empty_turn`: the model ended the turn ONLY by reasoning
                # and the provider layer turned that reasoning into a text
                # block (see openai_backend: reasoning-only turn). It enters
                # the history so the model sees its own plan — but this is
                # NOT AN ANSWER TO THE USER. The `internal` mark is exactly
                # for this: it does not surface in the chat or the
                # transcript (same line of defence as the internal-note
                # leak; raw reasoning was seen landing in the chat as italic
                # paragraphs). The reasoning is not lost: it lives in the UI
                # under the collapsed "✻ Düşündü" header.
                self.session.add_assistant(
                    blocks, usage=report,
                    internal=(result.stop_reason == "empty_turn" or fake_text))
                # What the assistant said goes to instant memory too: a
                # measurement result or an explanation, to be found later
                # with "what did you just say".
                self._encode_turn("dornick", _text_of_blocks(blocks))
            else:
                self.session.log.note("empty_assistant_turn", stop_reason=result.stop_reason)

            stats.stop_reason = result.stop_reason
            # Fake tool call: the model wrote the XML as plain text instead
            # of a real call and ended the turn. Does not count as an answer
            # — one more turn is given with a correction note. If there IS a
            # real tool call (tool_use) we do not interfere: the work is
            # under way.
            if result.stop_reason == "end_turn" and self._fix_fake_call(stats, blocks):
                continue
            # The "don't say done while red" gate: if the model tries to
            # close with a tool-less finishing answer while there is a red
            # run in this turn, one more turn is given.
            if result.stop_reason == "end_turn" and self._red_gate(stats, blocks):
                continue
            # The run-what-you-delivered gate: turns back once a turn that
            # finished with green tests but never ran the command the user
            # would type. AFTER the red gate: if there is red, that is what
            # actually needs to be said.
            if result.stop_reason == "end_turn" and self._entry_gate(stats, blocks):
                continue
            # Test gate: the turn does not close without running the
            # written test file.
            if result.stop_reason == "end_turn" and self._test_gate(stats, blocks):
                continue
            # Acceptance gate: "done" is said while an open item sits in the
            # job ledger — the last and the most general of the gate chain.
            if result.stop_reason == "end_turn" and self._acceptance_gate(stats, blocks):
                continue
            if await self._handle_stop(result, ctx, stats):
                continue
            # The turn ended normally but if the user barged in meanwhile
            # the message must not be lost: the note is written and one
            # more step is given within the SAME turn (the MAX_TURNS ceiling
            # still applies).
            if result.stop_reason == "end_turn" and self._inbox and not self.cancel.is_set():
                self._drain_inbox()
                continue
            break

        else:
            # Absolute fuse: normal work does not hit this (checkpoints keep
            # the work going); this is the last brake of a runaway loop.
            self.io.on_notice(
                f"{HARD_TURN_LIMIT} turluk mutlak sigortaya ulaşıldı, koşu durduruldu.")
            self.session.log.note("turn_limit", limit=HARD_TURN_LIMIT)

        # The run is over: the park record (if left) goes — let's not try to
        # resume a finished job at startup.
        if self.depth == 0:
            self._parked = False
            clear_park(self.config.state_dir)
            # The trace of the run goes to the mind as a capsule: the next
            # session skips the discovery.
            self._job_capsule()
            # If the first exchange is over let the model set the title (on
            # an unnamed session).
            await self._session_title()
        return stats

    def _error_lesson(self, calls: list[Any], blocks: list[dict[str, Any]]) -> None:
        """Bridges tool errors into lesson memory (the user's suggestion).

        Two directions: (1) the SECOND fall into the same known pattern in
        this run becomes a persistent lesson — falling once is learning,
        falling twice is a habit; (2) if there is a lesson for that pattern
        from PAST sessions it is attached next to the error as "[Hafıza]" —
        the static hint saves the turn, the lesson carries across sessions.
        """
        if self.mind is None or self.depth:
            return
        from .tools.shell import shell_hint
        names = {c.id: c.name for c in calls}
        for b in blocks:
            if not (isinstance(b, dict) and b.get("is_error")):
                continue
            text = str(b.get("content") or "")
            tool = names.get(str(b.get("tool_use_id") or ""), "")
            switches = recipe = ""
            if tool == "edit_file" and "Aranan metin" in text:
                switches = "edit-anchor"
                recipe = ("edit_file'a old metnini dosyanın GERÇEK halinden "
                          "kopyala: önce read_file, sonra düzenle; girinti ve "
                          "satır sonu birebir.")
            elif hint := shell_hint(text):
                switches = "kabuk:" + hint[:24]
                recipe = hint
            if not switches:
                continue
            title = "araç dersi: " + switches
            # If there is a past lesson attach it next to the error (once
            # per run).
            if self._error_patterns.get(switches, 0) == 0:
                try:
                    for hit in self.mind.recall(title, limit=3):
                        if hit.item.title == title and hit.item.session_id != self.session.id:
                            b["content"] = (text + "\n\n[Hafıza] "
                                            + hit.item.content)
                            break
                except Exception:
                    pass
            count = self._error_patterns.get(switches, 0) + 1
            self._error_patterns[switches] = count
            if count != 2:
                continue   # first fall: the hint is enough; third+: the lesson already exists
            try:
                if any(h.item.title == title
                       for h in self.mind.recall(title, limit=3)):
                    continue
                self.mind.remember(
                    f"{tool or 'araç'} hatası tekrar etti — {recipe}",
                    kind="lesson", title=title)
                self.session.log.note("hata_dersi", anahtar=switches)
            except Exception:
                pass

    def _job_capsule(self) -> None:
        """Mechanical job capsule at the end of the run: what was asked, what was produced, what ran.

        Measured gain (28.08 memory experiment, arm B): when this capsule is
        recalled spontaneously in the next session the model skips the
        discovery call (−24% tokens). The capsule comes from the ledger, not
        the model: no risk of fabrication.
        """
        if (self.mind is None or self.depth or self._capsule_written
                or not self._written):
            return
        first = ""
        for m in self.session.messages():
            if m.get("role") == "user":
                g = m.get("content")
                first = g if isinstance(g, str) else _text_of_blocks(g or [])
                break
        if not first.strip():
            return
        files = []
        for path in self._written:
            name = Path(path).name
            if name and name not in files:
                files.append(name)
        commands = [k.strip()[:80] for k in self._commands[-2:] if k.strip()]
        content = (_one_line(first)[:200]
                   + " — üretilen: " + ", ".join(files[:6])
                   + ((". çalıştırılan: " + "; ".join(commands)) if commands else "")
                   + ".")
        title = "iş kapsülü: " + _one_line(first)[:40]
        try:
            if any(h.item.title == title
                   for h in self.mind.recall(title, limit=3)):
                return
            self.mind.remember(content, kind="fact", title=title)
            self._capsule_written = True
            self.session.log.note("is_kapsulu", dosyalar=files[:6])
        except Exception:
            pass

    async def _session_title(self, preview: str = "") -> None:
        """Generates a short title from the first exchange of an unnamed session.

        The first 30 characters of the user's message are not a title
        (being listed as "bana profesonel bir cms yapa ama plan oluştur..."
        was a live complaint). One small call; every error is swallowed
        silently — the title is decoration, not the result of the run.

        `preview`: when the run generates the title in parallel before it
        has written the user message to the log (desktop._isle) it takes
        the text from here — otherwise it looked at the empty log and
        silently gave up.
        """
        if self.depth or self.mind is None or self.cancel.is_set():
            return
        try:
            meta = (self.mind.session_meta() or {}).get(self.session.id) or {}
            if meta.get("ad"):
                return
            messages = self.session.messages()
            # The title may fail to be generated on the first attempt (a
            # small model can return empty/junk, the call can blow up). The
            # old `> 2` gate gave up forever on a single hiccup — the chat
            # was listed on the left forever with the crumb of the first
            # words ("sohbet ismi oluşmuyor", live complaint). The window
            # was widened to the first few exchanges.
            if sum(1 for m in messages if m.get("role") == "user") > 6:
                return   # the first exchanges are long gone: leave the title alone
            question = answer = ""
            for m in messages:
                body = m.get("content")
                text = body if isinstance(body, str) else _text_of_blocks(body or [])
                if m.get("role") == "user" and not question:
                    question = text
                elif m.get("role") == "assistant" and text:
                    answer = text
            if not question and preview:
                question = preview
            if not question.strip():
                return
            excerpt = ("KULLANICI: " + _one_line(question)[:400]
                       + "\nASISTAN: " + _one_line(answer)[:300])
            prepared = Prepared(
                system=[{"type": "text", "text": TITLE_PROMPT}],
                messages=[{"role": "user", "content": excerpt}],
                betas=[], context_management=None)
            # The title call carries the REAL cancel event and is
            # time-limited: its old form (a fresh Event + unbounded wait)
            # could hold the single-channel API gate uncancellably — the
            # main turn and everything including Stop waited behind it
            # (live wound, 01.09: "it stopped for 10 minutes, didn't carry
            # on where it was").
            result = await asyncio.wait_for(
                self.client.turn(prepared, [], cancel=self.cancel), timeout=60)
            title = _one_line(_text_of_blocks(
                getattr(result.message, "content", None) or [])).strip().strip("\"'.!*# ")
            if _title_valid(title):
                self.mind.set_session_meta(self.session.id, ad=title)
                self.session.log.note("baslik", ad=title)
                # Don't make the sidebar list wait for the 5 s poll — carry
                # it over at once.
                try:
                    self.io.on_session_title(self.session.id, title)
                except Exception:
                    pass
        except Exception:
            pass   # the title could not be generated: the derived title already exists

    async def _handle_stop(
        self, result: TurnResult, ctx: ToolContext, stats: TurnStats
    ) -> bool:
        """Should the loop continue? True -> continue."""
        reason = result.stop_reason

        if reason == "tool_use":
            calls = [
                PendingToolUse(id=b["id"], name=b["name"], input=dict(b.get("input") or {}))
                for b in result.tool_uses()
            ]
            stats.tool_calls += len(calls)
            # A turn that calls tools is making progress: the continuation
            # allowance is refreshed. Occasionally hitting the max_tokens
            # ceiling in a long run must not drag the job into the closing
            # turn.
            if not stats.closing:
                stats.continuations = 0
            blocks = await execute(
                calls,
                registry=self.registry,
                permissions=self.permissions,
                ctx=ctx,
                approve=self.io.approve,
                observe=self._observe,
            )
            # If a tool returned an image (like looking at the camera) it
            # cannot be carried in the block: the OpenAI contract wants
            # role=tool content to be a string. The image is split off and
            # attached to the next user turn — the model really looks in
            # that turn.
            seen = []
            for b in blocks:
                v = b.pop("_image", None)
                if isinstance(v, list):
                    seen.extend(x for x in v if x)   # camera crops
                elif v:
                    seen.append(v)
            # Memory bridge: a known error pattern becomes a lesson; if
            # there is a lesson from past sessions it is attached NEXT TO
            # the error.
            self._error_lesson(calls, blocks)
            self.session.add_tool_results(blocks)
            if seen:
                # `internal`: a message the user did not write must not
                # look like a user message in the chat. In a real run the
                # "Yukarıdaki kare kendi kameranın gördüğü…" note landed on
                # screen like an answer.
                self.session.add_user_blocks(_seen_blocks(seen), internal=True)
            if self.cancel.is_set():
                stats.interrupted = True
                self.io.on_notice("Kesildi. Çalışan araçlar durduruldu.")
                return False
            return True

        if reason == "pause_turn":
            # A server-side tool hit its own iteration limit. Don't add a
            # user message — resending the history as it is suffices.
            self.session.log.note("pause_turn")
            return True

        if reason == "max_tokens":
            # The model hit the ceiling before finishing its answer.
            # Stopping here left the user with half a sentence; yet the
            # history is already written, one more turn is enough for it to
            # continue where it left off.
            #
            # If the cut-off happened in the middle of a tool call the
            # half-written tool_uses stay unanswered; an unanswered tool_use
            # drops the next request with a 400.
            self._settle_pending()
            return self._continue(stats, CONTINUE_NOTE, "max_tokens")

        if reason == "empty_turn":
            # The model only reasoned and stopped: it made a plan, said "now
            # I should do this" and ended the turn. Presenting the reasoning
            # as the answer left the user hanging; its plan is already in
            # the history, one more turn is given so it does what it has to
            # do.
            return self._continue(stats, ACT_NOTE, "empty_turn")

        if reason == "refusal":
            detail = getattr(result.message, "stop_details", None)
            category = getattr(detail, "category", None)
            self.session.log.note("refusal", category=category)
            self.io.on_notice(f"Model bu isteği reddetti (kategori: {category or 'belirtilmemiş'}).")
            return False

        if reason == "model_context_window_exceeded":
            # The server exhausted the window before we did (our estimate
            # drifted or the context_window setting is above reality).
            # Instead of stopping: compact / tight / last resort — the work
            # goes on.
            self.session.log.note("context_exhausted")
            if await self._refresh_context("pencere tasti"):
                return True
            # Even if _refresh_context returns False don't stop: a
            # continuation note with the goal summary — we don't tell the
            # user "open a new session".
            self.session.add_continuation_note(
                "Bağlam yenilendi. İş listendeki açık maddelerden kaldığın "
                "yerden devam et; baştan anlatma."
            )
            self.io.on_notice("Bağlam yenilendi — iş sürüyor.")
            return True

        return False  # end_turn and unknowns: the user's turn

    def _continue(self, stats: TurnStats, note: str, why: str) -> bool:
        """Continues a half-finished turn. False if the limit is full.

        The same thing is needed for two separate reasons (hitting the
        ceiling and only reasoning then stopping), and in both a single
        ceiling must be counted: a turn's continuation allowance is limited
        in total.
        """
        if stats.continuations >= MAX_CONTINUATIONS:
            if stats.closing:
                # The closing turn did not finish either. There is really
                # nothing left to do here.
                self.io.on_notice(
                    f"Yanıt {MAX_CONTINUATIONS} kez sürdürüldü ve kapanış turu da "
                    "bitmedi; durduruldu."
                )
                self.session.log.note(why, exhausted=True)
                return False

            # The agent did work, it only failed to finish. It is asked to
            # write a closing with what it has: the user getting nothing is
            # worse than a half answer.
            stats.closing = True
            self.io.on_notice("Yanıt uzadı; elindekiyle özetlemesi istendi.")
            self.session.add_continuation_note(CLOSING_NOTE)
            self.session.log.note(why, exhausted=True, closing=True)
            return True

        stats.continuations += 1
        self.session.add_continuation_note(note)
        self.session.log.note(why, continuation=stats.continuations)
        return True

    # -- model outage resilience --------------------------------------

    async def _await_model(self, stats: TurnStats, error: str) -> bool:
        """Waits on a model error; True → retry, False → the user interrupted.

        The first attempts use exponential backoff (RETRY_DELAYS); when they
        run out the job is PARKED: it does not die, it drops to probing at
        PARK_PROBE_S intervals — the probe is the request itself. In auto
        mode every new attempt goes through the health ranking and can fall
        to another model in the pool; if a specific model is selected the
        model is NOT CHANGED, we only wait.
        """
        retries = len(RETRY_DELAYS)
        if stats.api_errors <= retries:
            delay = RETRY_DELAYS[stats.api_errors - 1]
            # With a structured channel the raw error does NOT land in the
            # chat: the work strip runs the countdown in a single live line,
            # the detail opens on click.
            if not self._wait_event(
                kip="deneme", deneme=stats.api_errors, toplam=retries,
                saniye=int(delay), detay=_clip(error, 1500),
            ):
                self.io.on_notice(
                    f"Model yanıt vermiyor; {delay:.0f} sn sonra yeniden denenecek "
                    f"({stats.api_errors}/{retries}). ({_clip(error, 120)})")
        elif self.depth > 0:
            # Subagent: NO endless park here even while the main chat works.
            # The orchestra must not lock up at "Model bekleniyor (5/5) ·
            # 300s".
            stats.fail_reason = _clip(error, 400)
            self._wait_event(
                kip="hata", deneme=stats.api_errors, toplam=retries,
                saniye=0, detay=stats.fail_reason,
            )
            self.io.on_notice(
                f"Model {retries} denemede yanıt vermedi — görev durdu. "
                f"({_clip(error, 120)})")
            return False
        else:
            delay = PARK_PROBE_S
            self._park(error)
            # The strip is refreshed on every probe turn: the "iş
            # bekletiliyor" line stays live (even if the page is reloaded it
            # comes back on the next probe).
            self._wait_event(
                kip="park", saniye=int(delay), detay=_clip(error, 1500))

        # Interruptible wait: if the user says "stop" the wait ends at once.
        try:
            await asyncio.wait_for(self.cancel.wait(), timeout=delay)
        except asyncio.TimeoutError:
            # Time is up: retry. If there is a pending model/setting change
            # apply it first — if a broken address/key was fixed the new
            # client only takes effect this way.
            if self.on_retry_wait is not None:
                try:
                    self.on_retry_wait()
                except Exception:
                    pass
            return True

        # The user interrupted: a deliberate stop — the park record goes too.
        self._unpark()
        self._wait_event(kip="iptal")   # close the waiting line in the strip
        self.io.on_notice("Kesildi.")
        return False

    # -- fake tool call ------------------------------------------------

    def _fix_fake_call(
        self, stats: TurnStats, blocks: list[dict[str, Any]]
    ) -> bool:
        """Did the model write the tool call as text? If so, correct it.

        If it returns True the turn CONTINUES: a one-line note was written
        to the model and one more turn is given. Stopping here would leave
        the user alone with raw XML (or with nothing, since the UI does not
        draw it).
        """
        if not fake_tool_call(_text_of_blocks(blocks)):
            return False

        stats.sahte_cagri += 1
        self.session.log.note("sahte_arac_cagrisi", deneme=stats.sahte_cagri)
        # In the auto pool this is a health signal: an endpoint that cannot
        # call tools gets weeded out.
        self._kusurlu("sahte araç çağrısı")

        if stats.sahte_cagri > SAHTE_CAGRI_TAVANI:
            # Absolute fuse: the model does not recover (usually an endpoint
            # that does not support tool calls at all). Leave the turn to
            # its own flow and tell the user — the fix is in their hands:
            # switching models.
            self.io.on_notice(
                "Model araç çağrılarını metin olarak yazmayı sürdürüyor ve "
                "düzelmedi. Ayarlar › Model'den başka bir model denemek "
                "gerekebilir.")
            return False

        self.session.add_harness_note(
            FAKE_CALL_NOTE if stats.sahte_cagri == 1 else FAKE_CALL_HARD_NOTE)
        return True

    def _kusurlu(self, reason: str) -> None:
        """The turn technically succeeded but its CONTENT is flawed.

        A schema violation and a fake tool call are failures as real as an
        error/timeout: both waste the turn. In auto mode this signal is
        written to the health ledger, the model is pushed to the end of the
        pool and in the free pool an endpoint that cannot call tools gets
        weeded out by itself. Other providers have no equivalent — silently
        skipped.
        """
        save = getattr(self.client, "kusurlu", None)
        if save is None:
            return
        try:
            save(reason)
        except Exception:
            pass   # the health ledger must not bring the run down

    def _wait_event(self, **payload: Any) -> bool:
        """Writes the waiting state to the structured channel.

        If it returns True the UI took over the live line; the caller does
        not print the plain-text notice. Without the channel (CLI/test) it
        returns False and the old behaviour goes on as it is. An error in
        the channel does not bring the run down.
        """
        if self.io.on_wait is None:
            return False
        try:
            self.io.on_wait(payload)
        except Exception:
            pass
        return True

    def _park(self, error: str) -> None:
        if self._parked:
            return
        self._parked = True
        if self.depth == 0:
            try:
                write_park(self.config.state_dir, self.session.id, error)
            except OSError:
                pass
        self.session.log.note("parked", error=_clip(error, 300))
        self.io.on_notice(
            "Model ulaşılamıyor — işin bekletiliyor; bağlantı gelince kaldığı "
            f"yerden sürecek (her {int(PARK_PROBE_S)} sn'de bir yoklanıyor). "
            "İpucu: Ayarlar › model'de Oto kipi, kesintide havuzdaki başka "
            "modellerle sürmemi sağlar.")

    def _unpark(self) -> None:
        if self.depth == 0:
            clear_park(self.config.state_dir)
        if self._parked:
            self._parked = False
            self.session.log.note("unparked")

    # -- subagents -----------------------------------------------------

    def _child_registry(self) -> ToolRegistry:
        """The subagent's tool registry: built-ins (except task) + dynamics.

        A fresh registry `build_registry(subagents=False)` carries only the
        built-ins. Skills and MCP tools were added AFTER startup only to the
        main registry — the subagent could not see a skill written for a
        device or a connected MCP server. The built-ins' `source` is None;
        the skill/MCP one is set ("yetenek", "mcp:<ad>"). We copy the set
        ones from the main registry — whatever exists at that moment goes
        down to the subagent too.
        """
        registry = build_registry(self.mind, subagents=False)
        for spec in self.registry.all():
            if spec.source and spec.name not in registry:
                registry.register(spec)
        return registry

    async def _spawn(self, title: str, instruction: str, model: str = "") -> str:
        """Runs the subagent in its own session and returns only its last word.

        The separate session is the whole point: the subagent's thirty tool
        calls are written to its own log, not into the main conversation's
        window. All that remains is the answer itself.

        The permission engine and the workshop boundary are shared — a gate
        that can be skipped by saying "I'm a subagent" is not a gate.
        """
        handle = ChildHandle(id=uuid4().hex[:6], title=title,
                             model=model or self.config.model.name)
        self._register_child(handle)
        answer = await self._child_round(handle, instruction)
        # The result already returned with the tool result; don't drop a
        # notification note on top.
        handle.bildirildi = True
        return answer

    def _spawn_bg(self, title: str, instruction: str, model: str = "") -> ChildHandle:
        """Starts the helper in the background and returns IMMEDIATELY.

        The main agent carries on without waiting; when the helper finishes
        the result is put in front of the main agent with the notification
        note at the start of the turn (or, if the main agent is idle, with
        the resume turn the bridge opens).
        """
        handle = ChildHandle(id=uuid4().hex[:6], title=title,
                             model=model or self.config.model.name, arka_plan=True)
        self._register_child(handle)
        # The reference is kept in the ledger: an unreferenced task can be
        # garbage collected.
        handle.task = asyncio.get_running_loop().create_task(
            self._bg_round(handle, instruction))
        return handle

    def spawn_scheduled(self, title: str, prompt: str, schedule_id: str) -> ChildHandle:
        """Runs the scheduled task as a silent background helper.

        It does not land in the chat queue; when finished it does not make
        the main agent talk. The report stays in Orchestra / Tasks + the
        Viewer. Every run is written to task_runs.
        """
        from . import task_runs

        instruction = SCHEDULE_CHILD_WRAP.format(
            title=title or "görev", prompt=(prompt or "").strip())
        handle = ChildHandle(
            id=uuid4().hex[:6],
            title=title or "zamanlanmış",
            model=self.config.model.name,
            arka_plan=True,
            schedule_id=str(schedule_id or ""),
            sessiz=True,
            deliverable=_infer_deliverable(prompt or ""),
        )
        if schedule_id:
            try:
                run = task_runs.start_run(
                    self.config.state_dir, schedule_id,
                    title=title or "", child_id=handle.id)
                handle.run_id = run.id
            except Exception:
                pass
        self._register_child(handle)
        handle.task = asyncio.get_running_loop().create_task(
            self._bg_round(handle, instruction))
        return handle

    async def run_workflow(self, workflow_id: str,
                           schedule_id: str = "") -> dict[str, Any]:
        """Runs the automation graph as a silent helper.

        If `schedule_id` is given the run is written to THAT TASK's ledger.
        A must: the UI asks for the run history by task id
        (`/api/jobs/runs?id=<görev>`). Using an id derived from the workflow
        meant writing the runs into a drawer nobody looks at — the history
        looked empty, live progress never arrived. For task-less (direct
        workflow) runs the old derivation stays.
        """
        from . import task_runs, workflows
        from .workflow_run import execute_workflow

        wf = workflows.get(self.config.state_dir, workflow_id)
        if wf is None:
            return {"ok": False, "error": f"Akış yok: {workflow_id}"}

        handle = ChildHandle(
            id=uuid4().hex[:6],
            title=wf.title or workflow_id,
            model=self.config.model.name,
            arka_plan=True,
            sessiz=True,
            workflow_id=wf.id,
            schedule_id=(schedule_id or f"wf_{wf.id}")[:48],
        )
        try:
            run = task_runs.start_run(
                self.config.state_dir, handle.schedule_id,
                title=handle.title, child_id=handle.id)
            handle.run_id = run.id
        except Exception:
            pass
        self._register_child(handle)
        # Orchestra channel: node tool events must not land without a
        # channel.
        try:
            self.io.on_child_start(
                handle.title, handle.model, handle.id, handle.arka_plan)
        except Exception:
            pass

        async def _go() -> None:
            progress: list = []
            try:
                report, progress, ok = await execute_workflow(
                    wf, self, handle)
                handle.state = "bitti" if ok else "hata"
                handle.sonuc = report
                handle.bitis_ts = time.time()
                if not handle.deliverable:
                    handle.deliverable = _infer_deliverable(
                        wf.title or "", report or "")
                self.io.on_child_end(
                    handle.title, ok, 0, len(progress or []),
                    handle.id, _clip(report, 200))
            except Exception as exc:
                handle.state = "hata"
                handle.sonuc = f"{type(exc).__name__}: {exc}"
                handle.bitis_ts = time.time()
                self.io.on_child_end(
                    handle.title, False, 0, 0, handle.id,
                    _clip(handle.sonuc, 200))
            if handle.sessiz:
                handle.bildirildi = True
            if handle.schedule_id and handle.run_id:
                try:
                    from . import task_runs as tr
                    meter = _run_meter(handle, self.config)
                    tr.finish_run(
                        self.config.state_dir, handle.schedule_id, handle.run_id,
                        status="bitti" if handle.state == "bitti" else "hata",
                        report=_report_with_meter(handle, self.config),
                        child_id=handle.id,
                        nodes_progress=progress or None,
                        model=meter["model"],
                        usage=meter["usage"],
                        cost_usd=meter["cost_usd"],
                        tools=meter["tools"],
                        duration_s=meter["duration_s"],
                        last_tool=meter["last_tool"],
                    )
                except Exception:
                    pass
            self._children_settled()

        handle.task = asyncio.get_running_loop().create_task(_go())
        return {"ok": True, "id": handle.id, "workflow_id": wf.id,
                "run_id": handle.run_id}

    async def _bg_round(self, handle: ChildHandle, instruction: str,
                        *, resume: bool = False) -> None:
        """Background wrapper: run it, update the ledger whatever happens,
        tell the bridge."""
        try:
            await self._child_round(handle, instruction, resume=resume)
        except Exception as exc:  # a crash in the background must not stay silent
            handle.state = "hata"
            handle.sonuc = f"Alt ajan hata verdi: {type(exc).__name__}: {exc}"
            handle.bitis_ts = time.time()
            self.session.log.note("subagent_failed", title=handle.title,
                                  session=handle.session_id, error=str(exc))
        if handle.sessiz:
            # Scheduled job: no resume turn in the main chat — the report is
            # in the panel.
            handle.bildirildi = True
        if handle.schedule_id and self.schedule is not None:
            try:
                status = ("bitti" if handle.state == "bitti"
                          else f"hata: {_clip(handle.sonuc, 80)}")
                self.schedule.note_run(handle.schedule_id, status)
            except Exception:
                pass
        if handle.schedule_id and handle.run_id:
            try:
                from . import task_runs
                meter = _run_meter(handle, self.config)
                task_runs.finish_run(
                    self.config.state_dir, handle.schedule_id, handle.run_id,
                    status="bitti" if handle.state == "bitti" else "hata",
                    report=_report_with_meter(handle, self.config),
                    child_id=handle.id,
                    model=meter["model"],
                    usage=meter["usage"],
                    cost_usd=meter["cost_usd"],
                    tools=meter["tools"],
                    duration_s=meter["duration_s"],
                    last_tool=meter["last_tool"],
                )
            except Exception:
                pass
        self._children_settled()

    async def _child_round(self, handle: ChildHandle, instruction: str,
                           *, resume: bool = False) -> str:
        """A helper's full round: open a session (or resume from disk), run
        it, update the ledger, return the result."""
        from .session import Session

        # The subagent can run with another model: a scanning job can go to
        # a small fast model, a job that needs vision to a model that reads
        # images. If the same model is asked for the client is shared — a
        # second client means a second connection pool.
        client, config = self.client, self.config
        if handle.model and handle.model != self.config.model.name:
            client, config = self._client_for(handle.model)

        # Agent gate: as many as the machine can carry run at the same time,
        # the rest wait in line. Stop (cancel) must work while waiting at
        # the gate too — otherwise a task that looked "running" did not
        # respond to Stop.
        try:
            await self._acquire_agent_gate(handle)
        except asyncio.CancelledError:
            handle.state = "hata"
            handle.sonuc = "(kesildi)"
            handle.bildirildi = True
            handle.bitis_ts = time.time()
            self.io.on_child_end(handle.title, False, 0, 0, handle.id, "(kesildi)")
            return handle.sonuc

        try:
            if resume:
                child = Session.resume(
                    self.config.sessions_dir / f"{handle.session_id}.jsonl")
            else:
                child = Session.create(self.config.sessions_dir)
                handle.session_id = child.id
                child.log.note("subagent_start", title=handle.title, parent=self.session.id)
                self.session.log.note("subagent_start", title=handle.title, session=child.id)
            # The orchestra channel is born: let the UI show it live.
            self.io.on_child_start(handle.title, handle.model, handle.id, handle.arka_plan)

            agent = Agent(
                config=config,
                session=child,
                # The subagent's own registry: without the `task` tool.
                registry=self._child_registry(),
                client=client,
                io=self._child_io(handle.title, handle.id),
                permissions=self.permissions,
                policy=self.policy,
                mind=self.mind,
                depth=self.depth + 1,
                schedule=self.schedule,
                # The child's OWN flag; the parent's `interrupt()` sets it
                # as a derivative ("stop = everything stops"). Sharing did
                # not work: the parent refreshes its flag on every `run`
                # and the background child was left ownerless on the old
                # flag.
                cancel=handle.cancel,
            )
            # If the main chat changed the model from settings, let the
            # child switch too on retry — a task must not lock up on a dead
            # model while chat works.
            def _child_retry_wait(
                _agent=agent, _handle=handle, _parent=self,
                _birth=self.client,
            ) -> None:
                if _parent.on_retry_wait is not None:
                    try:
                        _parent.on_retry_wait()
                    except Exception:
                        pass
                # Adopt only if the parent's client REALLY changed. The hook
                # now runs before every model call (pending-swap flow);
                # unconditional adoption turned the client of a child opened
                # with a different model into the parent's on the FIRST turn
                # — task's model routing was broken (root cause, 01.09).
                if _parent.client is _birth:
                    return
                _agent.client = _parent.client
                _agent.config = _parent.config
                _handle.model = _parent.config.model.name

            agent.on_retry_wait = _child_retry_wait
            handle.agent = agent

            try:
                stats = await agent.run(instruction)
            except Exception as exc:  # a helper's crash must not bring the main turn down
                self.session.log.note("subagent_failed", title=handle.title,
                                      session=handle.session_id, error=str(exc))
                handle.state = "hata"
                handle.sonuc = f"Alt ajan hata verdi: {type(exc).__name__}: {exc}"
                self.io.on_child_end(handle.title, False, 0, 0, handle.id,
                                     _clip(handle.sonuc, 200))
                return handle.sonuc
            finally:
                handle.agent = None
                handle.bitis_ts = time.time()
                # The log closes but the session stays on disk: `task_say`
                # can reopen a finished helper with Session.resume.
                child.close()
        finally:
            self._agent_gate.release()

        answer = _last_text(child)
        if stats.interrupted:
            # No notification turn is opened for an interrupted helper: the
            # one who stopped it is the user themselves — or the model
            # stopped with max retries.
            handle.state = "hata"
            if stats.fail_reason:
                handle.sonuc = (
                    f"Model {len(RETRY_DELAYS)} denemede yanıt vermedi.\n"
                    f"{stats.fail_reason}"
                )
            else:
                handle.sonuc = answer or "(kesildi)"
            handle.bildirildi = True
        else:
            handle.state = "bitti"
            handle.sonuc = answer
        if not handle.deliverable:
            handle.deliverable = _infer_deliverable(instruction, handle.sonuc or "")
        # `session` is for the orphan scan: at startup the start/end match
        # is done by id (the title does not have to be unique).
        self.session.log.note(
            "subagent_end", title=handle.title, session=handle.session_id,
            turns=stats.turns, tools=stats.tool_calls
        )
        self.io.on_child_end(handle.title, not stats.interrupted, stats.turns,
                             stats.tool_calls, handle.id,
                             _clip(handle.sonuc or answer, 200))
        return handle.sonuc or answer

    def _register_child(self, handle: ChildHandle) -> None:
        self._children[handle.id] = handle
        # The ledger is bounded: a running one is not thrown out, the oldest
        # finished ones drop.
        while len(self._children) > MAX_CHILDREN:
            finished = [h for h in self._children.values() if h.state != "kosuyor"]
            if not finished:
                break
            oldest = min(finished, key=lambda h: h.bitis_ts)
            self._children.pop(oldest.id, None)

    def adopt_orphans(self, orphans: list[dict[str, str]]) -> list[ChildHandle]:
        """Takes the previous session's orphan helpers into the ledger.

        The ledger record opens two doors at once: the UI panel can draw the
        orphan as a faded "left half done" row (snapshot channels) and if
        the user says "continue" `task_say` can revive the on-disk session
        through the handle. A single bulk harness note is dropped for the
        model — from the inbox, i.e. put in front of it at the start of the
        first turn.
        """
        adopted: list[ChildHandle] = []
        for y in orphans:
            sid = str(y.get("session") or "")
            if not sid:
                continue
            handle = ChildHandle(
                id=uuid4().hex[:6],
                title=str(y.get("title") or "") or sid,
                model="",
                arka_plan=True,
                session_id=sid,
                state="yetim",
                sonuc=ORPHAN_RESULT,
                bitis_ts=time.time(),
                # Don't open a notification turn: the news note is already
                # below.
                bildirildi=True,
            )
            self._register_child(handle)
            adopted.append(handle)
        if adopted:
            listing = ", ".join(f"{h.title} (id={h.id})" for h in adopted)
            self.take_note(ORPHAN_NOTE.format(n=len(adopted), liste=listing))
        return adopted

    def _children_settled(self) -> None:
        """A helper finished: tell the bridge (if any).

        If the main agent is idle the bridge opens a resume turn; if busy
        the news drops into the queue and is evaluated when the turn ends.
        Without a bridge (test, text-only) the result is reported anyway at
        the start of the next turn.
        """
        callback = self.on_children_settled
        if callback is not None:
            try:
                callback()
            except Exception:
                pass

    def _drain_children(self) -> None:
        """Turns finished and not-yet-reported helper/job results into notes."""
        for handle in self._children.values():
            if handle.state == "kosuyor" or handle.bildirildi:
                continue
            handle.bildirildi = True
            if handle.kind == "iş":
                template = JOB_DONE_NOTE if handle.state == "bitti" else JOB_FAIL_NOTE
            else:
                template = CHILD_DONE_NOTE if handle.state == "bitti" else CHILD_FAIL_NOTE
            self.session.add_harness_note(template.format(
                title=handle.title, id=handle.id,
                # The full text goes to the panel; the model gets only a
                # short summary — so it does not paste a long bulletin into
                # the chat.
                result=_clip(handle.sonuc, 400)))

    def _drain_inbox(self) -> None:
        """Drains the inbox into the history as harness notes."""
        while self._inbox:
            self.session.add_harness_note(self._inbox.popleft())

    def has_unreported_children(self) -> bool:
        return any(h.state != "kosuyor" and not h.bildirildi
                   for h in self._children.values())

    async def resume_for_children(self) -> TurnStats | None:
        """The resume turn that evaluates helpers finished while idle.

        Its input is not a user message: a note from the continuation
        channel (invisible in the UI) + the harness notes of the results. If
        there is no pending notification it returns None and the model is
        never called.
        """
        done = [h for h in self._children.values()
                if h.state != "kosuyor" and not h.bildirildi]
        if not done:
            return None
        self._arm()
        titles = ", ".join(f"{h.title} (id={h.id})" for h in done)
        self.session.add_continuation_note(CHILDREN_RESUME_NOTE.format(titles=titles))
        self._drain_children()
        return await self._drive()

    def _child_say(self, cid: str, message: str) -> tuple[bool, str]:
        """`task_say`: a note to a running helper, a continuation turn to a finished one."""
        handle = self._children.get((cid or "").strip())
        if handle is None:
            known = ", ".join(self._children) or "(defter boş)"
            return False, (f"'{cid}' diye bir yardımcı yok. Defterdekiler: {known}. "
                           "`task_status` ile bak.")
        if handle.kind == "iş":
            return False, (f"'{handle.title}' bir arka plan işi (süreç), mesaj almaz. "
                           "Bitince çıktısı zaten sana bildirilecek.")
        if handle.state == "kosuyor":
            if handle.agent is None:
                # In line at the agent gate: the object is not built yet.
                return False, (f"'{handle.title}' henüz sırada (ajan kapısı dolu); "
                               "birazdan tekrar dene.")
            handle.agent.take_note(SAY_NOTE.format(message=message))
            return True, (f"İletildi: '{handle.title}' (id={handle.id}) bir sonraki "
                          "adımında bu notu görecek.")
        if not handle.session_id:
            return False, f"'{handle.title}' oturumsuz bitti; sürdürülemiyor."
        # Finished helper: its session is opened from disk and resumed in
        # the background.
        handle.state = "kosuyor"
        handle.bildirildi = False
        handle.sonuc = ""
        handle.cancel = asyncio.Event()
        handle.task = asyncio.get_running_loop().create_task(
            self._bg_round(handle, message, resume=True))
        return True, (f"'{handle.title}' (id={handle.id}) bitmişti; oturumu diskten "
                      "açılıp arka planda sürdürülüyor — bitince sonucu bildirilecek.")

    def _child_status(self, cid: str = "") -> str:
        """`task_status`: status summary of one/all helpers."""
        if not self._children:
            return "Defter boş: başlatılmış yardımcı yok."
        wanted = (cid or "").strip()
        rows = []
        for h in self._children.values():
            if wanted and h.id != wanted:
                continue
            row = f"- id={h.id} · {h.title} · {h.state}"
            if h.kind == "iş":
                row += " · süreç"
            if h.arka_plan:
                row += " · arka plan"
            if h.state != "kosuyor" and h.sonuc:
                row += f" · sonuç: {_clip(h.sonuc, 300)}"
            rows.append(row)
        if not rows:
            return (f"'{wanted}' diye bir yardımcı yok. "
                    f"Defterdekiler: {', '.join(self._children)}")
        return "\n".join(rows)

    # -- background jobs (long processes) ------------------------------

    def _job_bg(self, title: str, runner: Callable[[asyncio.Event], Awaitable[str]]) -> ChildHandle:
        """Moves a long job (build, install, test run) to the background.

        The SAME helper ledger is used: record, notification note, resume
        turn while idle and derived interrupt — all ready infrastructure.
        The difference: not a model-running subagent but a single coroutine
        (process). `runner` gets its own cancel flag — the parent's
        `interrupt()` sets it.
        """
        handle = ChildHandle(id=uuid4().hex[:6], title=title, model="",
                             kind="iş", arka_plan=True)
        self._register_child(handle)
        self.session.log.note("job_start", title=title, id=handle.id)
        self.io.on_child_start(handle.title, "süreç", handle.id, True)
        handle.task = asyncio.get_running_loop().create_task(
            self._job_round(handle, runner))
        return handle

    async def _job_round(self, handle: ChildHandle,
                         runner: Callable[[asyncio.Event], Awaitable[str]]) -> None:
        try:
            # The full output is in the panels/Viewer; the clip for the
            # harness note is separate.
            handle.sonuc = await runner(handle.cancel)
            handle.state = "bitti"
        except JobFailed as exc:
            # The command finished but failed — let's not say 'completed'.
            handle.state = "hata"
            handle.sonuc = str(exc)
        except Exception as exc:  # a job's crash must not bring the agent down
            handle.state = "hata"
            handle.sonuc = f"{type(exc).__name__}: {exc}"
        handle.bitis_ts = time.time()
        self.session.log.note("job_end", title=handle.title, id=handle.id,
                              state=handle.state)
        self.io.on_child_end(handle.title, handle.state == "bitti", 0, 0,
                             handle.id, _clip(handle.sonuc, 200))
        self._children_settled()

    async def _acquire_agent_gate(self, handle: "ChildHandle") -> None:
        """Acquire the agent semaphore; CancelledError if Stop arrives.

        A plain `async with gate` did not listen to cancel — while a
        scheduled task waited at the gate the UI said 'running' and Stop
        did nothing at all.
        """
        if handle.cancel.is_set():
            raise asyncio.CancelledError()
        acquire = asyncio.ensure_future(self._agent_gate.acquire())
        stopper = asyncio.ensure_future(handle.cancel.wait())
        try:
            done, pending = await asyncio.wait(
                {acquire, stopper}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            if stopper in done and acquire not in done:
                raise asyncio.CancelledError()
            # acquire completed (or both did — the gate is taken either way).
            if acquire.cancelled() or acquire.exception():
                raise asyncio.CancelledError()
        except asyncio.CancelledError:
            if not acquire.done():
                acquire.cancel()
                try:
                    await acquire
                except (asyncio.CancelledError, Exception):
                    pass
            elif not acquire.cancelled() and acquire.exception() is None:
                # We were cancelled while holding the gate — release it.
                self._agent_gate.release()
            raise

    def _client_for(self, model: str) -> tuple[Any, Config]:
        """Builds a client for another model.

        The provider and the address stay the same, only the model name
        changes: another model on the same LM Studio or another model on
        the same API. Asking for a different provider is the settings' job,
        not the subagent's.

        The built client is kept: if three subagents ask for the same model
        there is no point in opening three connection pools.
        """
        from dataclasses import replace as _replace

        from .backends import build_client

        if model in self._clients:
            return self._clients[model]

        config = _replace(self.config, model=_replace(self.config.model, name=model))
        pair = (build_client(config.model), config)
        self._clients[model] = pair
        return pair

    def _child_io(self, title: str, cid: str) -> AgentIO:
        """The subagent's UI connection.

        It does not stream text: if the subagent's interim sentences mixed
        into the main chat the user could not tell who was speaking. Tool
        events pass through — what it does must be observable.

        The approval request goes with the channel identity: the user
        should see in the dialog which helper is asking for permission. The
        bridge's approve can take a third `channel` parameter; the tests'
        two-parameter approvals keep working as they are.
        """
        import inspect

        approve = self.io.approve
        try:
            takes_channel = len(inspect.signature(approve).parameters) >= 3
        except (TypeError, ValueError):
            takes_channel = False
        if takes_channel:
            channel = {"id": cid, "title": title}

            async def child_approve(spec: ToolSpec, args: dict[str, Any]) -> bool:
                return await approve(spec, args, channel)
        else:
            child_approve = approve

        def on_tool_start(name: str, args: dict[str, Any]) -> None:
            target = _tool_target(args)
            self._child_tool_mark(cid, name, "start", target)
            self.io.on_child_tool(title, name, "start", target)

        def on_tool_end(name: str, ok: bool, ms: float) -> None:
            self._child_tool_mark(cid, name, "ok" if ok else "fail")
            self.io.on_child_tool(title, name, "ok" if ok else "fail", "")

        def on_usage(report: dict[str, int], _c: str = cid) -> None:
            h = self._children.get(_c)
            if h is None:
                return
            h.usage["girdi"] = int(h.usage.get("girdi") or 0) + int(
                report.get("prompt_total") or 0)
            h.usage["cikti"] = int(h.usage.get("cikti") or 0) + int(
                report.get("output") or 0)
            h.usage["cagri"] = int(h.usage.get("cagri") or 0) + 1

        return AgentIO(
            # Tool events are written to the subagent's channel (not the
            # main chat): "who is doing what" is visible in the orchestra
            # panel.
            on_tool_start=on_tool_start,
            on_tool_end=on_tool_end,
            on_usage=on_usage,
            # A raw BadRequestError wall must not spill into the main chat
            # like a yellow answer — a short summary; the full text opens on
            # click in the UI.
            # Wait/retry must not spam the chat: structured child_wait.
            on_notice=lambda text: self.io.on_notice(_child_notice_line(title, text)),
            on_wait=lambda payload, _t=title, _c=cid: self._child_wait(_t, _c, payload),
            approve=child_approve,
        )

    def _child_tool_mark(self, cid: str, name: str, phase: str,
                         target: str = "") -> None:
        handle = self._children.get(cid)
        if handle is None:
            return
        if phase == "start":
            handle.son_arac = name
            handle.son_hedef = target or ""
            handle.wait = None
            handle.tools_count = int(handle.tools_count or 0) + 1
        else:
            handle.son_arac = name + (" ✗" if phase == "fail" else " ✓")
            if not handle.son_hedef and target:
                handle.son_hedef = target
        self._maybe_patch_run(handle)

    def _maybe_patch_run(self, handle: ChildHandle) -> None:
        """Writes a live summary to the scheduled-run archive (throttled)."""
        if not handle.schedule_id or not handle.run_id:
            return
        now = time.time()
        if now - (handle.last_patch_ts or 0) < 3.0:
            return
        handle.last_patch_ts = now
        try:
            from . import task_runs
            meter = _run_meter(handle, self.config)
            lines: list[str] = ["(koşuyor)"]
            if meter.get("line"):
                lines.append(str(meter["line"]))
            if handle.son_arac:
                line = f"Araç: {handle.son_arac}"
                if handle.son_hedef:
                    line += f" · {handle.son_hedef}"
                lines.append(line)
            if handle.wait:
                w = handle.wait
                msg = "Model bekleniyor"
                if w.get("deneme") and w.get("toplam"):
                    msg += f" ({w['deneme']}/{w['toplam']})"
                lines.append(msg)
            task_runs.patch_run(
                self.config.state_dir, handle.schedule_id, handle.run_id,
                report="\n".join(lines),
                model=meter.get("model") or handle.model,
                usage=meter.get("usage"),
                cost_usd=meter.get("cost_usd"),
                tools=meter.get("tools"),
                duration_s=meter.get("duration_s"),
                last_tool=meter.get("last_tool"),
            )
        except Exception:
            pass

    def _child_wait(self, title: str, cid: str, payload: dict[str, Any]) -> None:
        """Subagent model wait → panel (not the chat wall)."""
        body = dict(payload or {})
        body.setdefault("title", title)
        body.setdefault("id", cid)
        mode = str(body.get("kip") or "")
        handle = self._children.get(cid)
        if handle is not None:
            if mode in ("bitti", "iptal"):
                handle.wait = None
            else:
                handle.wait = body
                handle.son_arac = ""
                handle.son_hedef = ""
            if mode in ("deneme", "park", "hata"):
                self._maybe_patch_run(handle)
        # Bridge / CLI: without on_child_wait fall back to notice — a short
        # line except for kip bitti/iptal.
        emit = getattr(self.io, "on_child_wait", None)
        if callable(emit):
            try:
                emit(body)
                return
            except Exception:
                pass
        if mode in ("bitti", "iptal"):
            return
        if mode in ("deneme", "park", "hata"):
            detail = _clip(str(body.get("detay") or ""), 120)
            secs = body.get("saniye")
            attempt = body.get("deneme")
            total = body.get("toplam")
            msg = f"[{title}] Model yanıt vermiyor"
            if mode == "hata":
                msg = f"[{title}] Model yanıt vermedi — görev durdu"
            if attempt and total:
                msg += f" ({attempt}/{total})"
            if secs:
                msg += f"; {secs} sn"
            if detail:
                msg += f". ({detail})"
            self.io.on_notice(msg)

    # -- context pressure ----------------------------------------------

    async def _relieve_pressure(self) -> None:
        """Compacts if the window is getting close to full.

        Done before hitting the ceiling: the summary request itself also
        has to fit into the same window.
        """
        if not self._last_usage:
            return
        pressure = compaction.measure(self._last_usage, self.config.model.context_window)
        self._warn_if_window_is_wrong(pressure)
        if pressure.full:
            await self._refresh_context(f"pencere %{pressure.percent} dolu")

    def _warn_if_window_is_wrong(self, pressure: compaction.Pressure) -> None:
        """Says so if the configured window is above reality.

        The symptom is insidious: compaction never triggers, the prompt
        exceeds the model's real limit and the server silently drops the
        **head** of the prompt. At that point the model has forgotten who
        it is and what was asked — from outside it looks like "it went
        haywire", whereas the setting is wrong.

        If answers keep coming although the prompt exceeded its window the
        proof is conclusive: the server is trimming.
        """
        if self._window_warned or pressure.used <= pressure.window:
            return
        self._window_warned = True
        self.session.log.note(
            "window_mismatch", used=pressure.used, configured=pressure.window
        )
        self.io.on_notice(
            f"İstem {pressure.used:,} token'a ulaştı ama ayardaki bağlam penceresi "
            f"{pressure.window:,}. Sunucu istemin başını atıyor olabilir — model "
            "kim olduğunu ve ne istendiğini unutur. Ayarlar › bağlam'dan "
            "pencereyi modelin gerçek sınırına çek.".replace(",", ".")
        )

    async def _refresh_context(self, reason: str) -> bool:
        """Compacts the context; failing that, tight / last-resort horizon.

        True = the window was refreshed (the work can go on). False = it
        could not be touched.
        """
        if await self._compact(reason=reason):
            return True
        if await self._compact(reason=f"{reason} — sıkı", keep=2):
            return True
        return self._force_horizon(reason)

    async def _compact(self, *, reason: str, keep: int | None = None) -> bool:
        """Summarises and narrows the window. False if it could not be compacted."""
        plan = (
            self.session.compaction_plan(keep=keep)
            if keep is not None
            else self.session.compaction_plan()
        )
        if plan is None and keep is None:
            plan = self.session.compaction_plan(keep=2)
        if plan is None:
            return False

        from_seq, text = plan
        self.io.on_notice(f"Bağlam sıkıştırılıyor ({reason}) — konuşma kesilmeyecek.")

        summary = await self._summarize(text)
        if not summary:
            self.session.log.note("compact_failed", reason=reason)
            return False

        # The job status is pinned to the HEAD of the summary: the most
        # critical thing in the lost context is "what was I after, where
        # did I leave off". The summariser sometimes buries it; here it is
        # guaranteed.
        if state := self._job_status(from_seq):
            summary = state + "\n\n" + summary

        self.session.compact(summary, from_seq)
        # The goal note folded into the summary; let the live goals be
        # re-injected on the next turn (otherwise, since the digest has not
        # changed, _sync_goals stays silent and the goals drop out of the
        # context entirely).
        self._last_goal_digest = ""
        self._last_usage = {}
        # The old prime notes folded into the summary; they are no longer
        # in the context. The right to repeat must come back, otherwise a
        # memory the summary lost can never be put in front again for the
        # rest of the session. The soul seeds stay — the soul is in the
        # system prompt, compaction does not touch it.
        self._primed = self._soul_resident()
        self.session.log.note("compacted", from_seq=from_seq, chars=len(summary))

        # The summary is written not only to the context but to the mind
        # too. Otherwise compaction would be a controlled forgetting: when
        # the session closed the summary would go too. Because it lands in
        # the mind it can come back by association months later.
        if self.mind is not None:
            try:
                self.mind.remember(
                    summary,
                    kind="episode",
                    title=f"oturum {self.session.id} — özet",
                    tags=("özet", "oturum"),
                )
            except Exception as exc:  # if the mind cannot be written the conversation must still go on
                self.session.log.note("compact_memory_failed", error=str(exc))

        self.io.on_notice("Bağlam özetlendi; kalıcı belleğe de yazıldı.")
        return True

    def _force_horizon(self, reason: str) -> bool:
        """If there is no turn to summarise pull the horizon to the last message — not so the work stops."""
        try:
            events = self.session._live_events()
        except Exception:
            return False
        if len(events) < 2:
            return False
        from_seq = events[-1].seq
        summary = (
            self._job_status(from_seq)
            or "Bağlam yenilendi; açık iş listesinden devam."
        )
        self.session.compact(summary, from_seq)
        self._last_goal_digest = ""
        self._last_usage = {}
        self._primed = self._soul_resident()
        self.session.log.note(
            "compacted", from_seq=from_seq, chars=len(summary), force=True, reason=reason
        )
        self.io.on_notice("Bağlam yenilendi — iş sürüyor.")
        return True

    async def _summarize(self, text: str) -> str:
        """Sends the model a one-off request to summarise the transcript.

        Tool-less and cache-less: this request is not part of the
        conversation, it is a question about it. Not written to the history
        either.
        """
        prepared = Prepared(
            system=[{"type": "text", "text": compaction.SUMMARY_SYSTEM}],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": compaction.SUMMARY_REQUEST.format(transcript=text)}
                    ],
                }
            ],
            betas=[],
            context_management=None,
        )
        result = await self.client.turn(prepared, [], cancel=self.cancel)
        if result.error or result.interrupted:
            return ""
        return "\n".join(
            str(block.get("text", ""))
            for block in result.content
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()

    def _job_status(self, before_seq: int) -> str:
        """The job-status section pinned to the head of the summary on compaction.

        Two parts: the goal stack (if any) + the last assistant word in the
        folded region ("last progress"). In a long run what the summary
        must not lose is exactly these two.
        """
        parts: list[str] = []
        if self.mind is not None:
            try:
                if digest := self.mind.goal_digest():
                    parts.append(digest)
            except Exception:
                pass
        if progress := self._last_progress(before_seq):
            parts.append(f"Son ilerleme: {_clip(progress, 600)}")
        if not parts:
            return ""
        return "[İŞ DURUMU]\n" + "\n".join(parts)

    def _last_progress(self, before_seq: int) -> str:
        """The last assistant text in the folded region — the model's own narrative."""
        for event in reversed(self.session.log.messages()):
            if event.seq >= before_seq or event.role != "assistant":
                continue
            blocks = event.content if isinstance(event.content, list) else []
            text = "\n".join(
                str(b.get("text", "")) for b in blocks
                if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
            if text:
                return text
        return ""

    # -- helpers -------------------------------------------------------

    def _sync_goals(self) -> None:
        """Reminds through the operator channel if the goal stack changed.

        It cannot be written into the system prompt — that has to stay
        byte-for-byte fixed, otherwise every goal change drops the whole
        cache. A role="system" message is appended to the end of the
        history: the prefix is preserved, the channel cannot be imitated.
        """
        if self.mind is None:
            return
        digest = self.mind.goal_digest()
        if digest == self._last_goal_digest:
            return
        self._last_goal_digest = digest
        if digest:
            # The bare list read like an INSTRUCTION on a small model: while
            # the user said "selam yaz" the model set about discussing the
            # goal in the ledger (live wound, 31.08). The priority is
            # embedded in the note in one sentence: the user's last word
            # sets the agenda.
            self.session.add_system_note(
                digest + "\n(Hatırlatma, talimat değil: gündemi kullanıcının "
                "son sözü belirler. Hedefe sırası gelince ya da kullanıcı "
                "sorunca dönersin; bu notu cevabında tartışmazsın.)")

    def _settle_pending(self) -> None:
        pending = self.session.pending_tool_uses()
        if not pending:
            return
        self.session.add_tool_results([cancelled_result(p.id) for p in pending])
        self.session.log.note("settled_pending", count=len(pending))

    def _observe(self, event: str, data: dict[str, Any]) -> None:
        self.session.log.note(event, **data)
        if event == "tool_start":
            # If the model wrote to its own ledger the end-of-turn nudge is
            # needless.
            if data.get("tool") == "mind_memory":
                self._mind_written = True
            self._delivery_trace(str(data.get("tool") or ""), data.get("input") or {})
            self.io.on_tool_start(data["tool"], data.get("input") or {})
        elif event == "tool_end":
            # Red ledger: the last verdict given by the verification tools.
            # A run that turned green DELETES the record — if the model
            # fixed and re-ran, the gate must not open.
            tool = data["tool"]
            if tool in VERIFICATION_TOOLS:
                if trace := kirmizi_iz(tool, data):
                    self._kirmizi[tool] = trace
                else:
                    self._kirmizi.pop(tool, None)
            self.io.on_tool_end(tool, not data["error"], data["ms"])
            if data["error"]:
                # Awake reverse replay (roadmap 3.12.1): responsibility is
                # assigned the moment the outcome is known, without waiting
                # for the night. Leaving the lesson to the morning meant
                # allowing the same mistake to be repeated in the same
                # session.
                self._awake_reverse_replay("basarisiz")
        elif event == "sema_ihlali":
            # A call that does not fit the schema is a wasted turn too: it
            # counts as a health signal in the auto pool (see _kusurlu).
            # The tool never ran, there is no step line in the UI either —
            # only in the log and the ledger.
            self._kusurlu("şema ihlali")


def worth_recalling(text: str) -> bool:
    """Is this message worth looking into the mind for?

    "naber" is not a question, it is a greeting. Dumping the mind in front
    of the model on every message was not the goal — the goal was **being
    able to find it quickly when needed**. In a real run, when "naber" was
    said the model met the previous session summary, the user profile and
    the BTC chain, and instead of chatting asked "what do you want to do".

    The criterion is simple: is there a word carrying content. Greetings
    and small talk have none; a message referring to a topic does.
    """
    words = [w for w in _WORDS.findall((text or "").lower()) if len(w) >= 4]
    return any(word not in SMALL_TALK for word in words)


def select_prime(mind: Any, user_input: str, *, limit: int = RECALL_PRIME_LIMIT,
                 ham: str | None = None, context: dict | None = None) -> list[Any]:
    """The selection core of spontaneous priming: search, filter, cut the tail.

    Being a module function is deliberate — the scale benchmark
    (eval/context_memory/scale_bench.py) must measure EXACTLY the same path
    as the product; a copied selection logic silently diverges and what is
    measured is no longer the product.

    Filtering rules (all from wounds that bled in real runs):

    * Only **direct matches** (hop 0). A record arriving by associative
      jump ("borsa" question → SCADA at the far end of the network) pulls
      the model off topic; that path is left to the model's own
      `mind_recall` call.
    * `episode` nodes do not enter: conversation turns are long and match
      almost every query, they drown the real match.
    * Letter grounding (`_grounded`): the record must actually contain the
      stem of at least one of the query's content words — once the scores
      saturate the threshold alone cannot separate, and records arriving
      on pure signature similarity leaked through.
    * The floor threshold is not applied to the strongest record: in a
      young memory bm25 collapses (a perfect match in a one-document corpus
      is 0.0) and the absolute threshold shut priming off entirely. The
      best grounded record is always shown; the threshold only cuts the
      tail.
    """
    query = _without_numbers(user_input)
    try:
        hits = mind.recall(query, limit=limit, context=context)
    except TypeError:
        # A mind that does not know context (an old version or a fake in a
        # test): context is an improvement, not a prerequisite.
        hits = mind.recall(query, limit=limit)

    trace = getattr(mind, "last_trace", None) or []
    direct = {step.node for step in trace if step.hop == 0}
    if not direct:
        return []
    stems = _query_stems(query)
    # In a rich query (>=5 stems) a record hanging on by a SINGLE stem
    # cannot enter priming: 50 unrelated field notes leaked in through
    # exactly this path on a single overlap like "ayın" ↔ "ayında" (28.08
    # memory experiment, arm C: +28% tokens, +1 call). The bar for
    # spontaneous injection is higher than for an explicit search — for a
    # single-topic real need the model's `mind_recall` path remains.
    # Abbreviation queries (btc, plc) are unharmed: few stems, the rule does
    # not fire. Richness is measured on the RAW user query: the synonym
    # expansion (writer.zenginlestir + bridge) inflates the query
    # artificially and a legitimate three-word question counted as "rich"
    # and cut the single-stem real record in a young memory (a test caught
    # this). The caller passes the raw text; if not, it falls back to the
    # bridge-less stems of the query at hand.
    rich = len(_query_stems(ham if ham is not None else query,
                            genislet=False)) >= 5
    def _passes(item: Any) -> bool:
        if not stems:
            return True
        text = f"{item.title} {item.content} {' '.join(item.tags)}".casefold()
        hitting = [g for g in stems if g in text]
        if not hitting:
            return False
        # Prefix copies count once: "ayı" and "ayın" are two cuts of the
        # same word — counting them as two pieces of evidence punched
        # through the filter.
        distinct = [g for g in hitting
                    if not any(g != d and d.startswith(g) for d in hitting)]
        return len(distinct) >= 2 if rich else True
    passed = [
        hit
        for hit in hits
        if hit.item.kind != "episode"
        and hit.item.id in direct
        and getattr(hit.item, "hot", True)
        and _passes(hit.item)
    ]
    # A cold record cannot enter priming. Its score is already low through
    # the activation multiplier but the rule must be explicit: the
    # young-memory exception (below) could pass it as the unconditional
    # top.
    if not passed:
        return []
    top = max(passed, key=lambda h: h.score)
    if top.score < RECALL_PRIME_FLOOR:
        # The unconditional-top exception only in a YOUNG mind. The reason
        # the exception was written was bm25 collapsing in a young corpus
        # (a perfect match in a one-document corpus is 0.0 — the absolute
        # threshold shut priming off entirely). In a mature mind the same
        # exception carried the single low-IDF winner into the context on
        # EVERY turn — the root cause found by the external review: the
        # +9% prompt tokens in the unrelated 9-task sequence came from
        # here.
        try:
            young = mind.store.count() < 30
        except Exception:
            young = True
        if not young:
            return []
    return [h for h in passed if h is top or h.score >= RECALL_PRIME_FLOOR][:limit]


def prime_note(hits: list[Any]) -> str:
    """The system note of the memories placed in front — the cost is the length of this text.

    `render()` is not used: it opens with `(tür) başlık [etiketler]` and
    printed the kind twice together with the `[tür]` at the start of the
    line; in auto-titled records (title = the first line of the body) the
    title was repeated again with the body. Tags do not enter either — for
    the model they are filler, not signal.
    """
    lines = [RECALL_PRIME_HEADER]
    for hit in hits:
        item = hit.item
        body = " ".join((item.content or "").split())
        title = " ".join((item.title or "").split())
        # If the title is the same as the head of the body (auto title),
        # only the body.
        if title and not body.casefold().startswith(title.casefold()[:40]):
            body = f"{title} — {body}"
        lines.append(f"- [{item.kind}] {_one_line(body)}")
    return "\n".join(lines)


def _query_stems(query: str, *, genislet: bool = True) -> set[str]:
    """The stems of the query's content words (first 5 letters, lower case).

    Function words (ve/bir/için...) are dropped — they are in every record
    and counting them as grounding punches through the filter.
    Abbreviations (btc, plc) carry content at 3 letters too; that is why
    the threshold is 3, not 4.

    The query first goes through the synonym bridge: if the search reaches
    the BTC record from "bitcoin" through the bridge, the grounding gate
    must recognise that bridge too — otherwise the found record drops out
    of priming as "the word does not appear".
    """
    from .recall import bridge
    from .recall.vector import STOPWORDS

    text = bridge.expand(query or "") if genislet else (query or "")
    return {
        w[:5]
        for w in _WORDS.findall(text.casefold())
        if len(w) >= 3 and w not in STOPWORDS
    }


def _grounded(item: Any, stems: set[str]) -> bool:
    """Does the record actually contain at least one of the query stems?

    If there are no stems (the query is only function words) the gate stays
    open: the filter's job is to cut the signature-only-evidence leak, not
    to shut recall off entirely.
    """
    if not stems:
        return True
    text = f"{item.title} {item.content} {' '.join(item.tags)}".casefold()
    return any(stem in text for stem in stems)


def _fatal_error(text: str) -> bool:
    """Is this an error that retrying will not help?

    A malformed request (400/404/405/413/422) and a window overflow (n_ctx)
    are not fixed by retrying the same request — the old behaviour is kept,
    it stops at once. Connection, timeout, 401/403 (the key can be fixed
    later), 408/429 and 5xx count as transient: a single provider hiccup
    must not kill a long job.
    """
    t = text or ""
    if re.search(r"\b(400|404|405|413|422)\b", t):
        return True
    return "n_ctx" in t


def _clip(text: str, limit: int) -> str:
    """Cuts a long result — so the notification note does not drown the context."""
    flat = (text or "").strip()
    return flat if len(flat) <= limit else flat[:limit] + "…"


_APP_URL_RE = re.compile(
    r"https?://(?:127\.0\.0\.1|localhost):\d+(?:/[^\s\"'<>]*)?",
    re.I,
)
_ARTIFACT_RE = re.compile(r"/artifact/[A-Za-z0-9_-]+/?", re.I)


def _tool_target(args: Any, limit: int = 100) -> str:
    """One line from the tool argument: command / path / url."""
    if not isinstance(args, dict):
        return ""
    for key in ("command", "path", "query", "url", "title", "id", "text", "run"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            flat = " ".join(value.split())
            return flat if len(flat) <= limit else flat[:limit] + "…"
    return ""


def _report_with_deliverable(handle: ChildHandle) -> str:
    """task_runs.report: summary + the live app/artifact address if any."""
    text = str(handle.sonuc or "").strip()
    d = handle.deliverable if isinstance(handle.deliverable, dict) else None
    if not d or not d.get("url"):
        return text
    url = str(d["url"])
    if url in text:
        return text or "(özet yok)"
    kind = str(d.get("kind") or "")
    if kind == "app":
        footer = f"\n\n---\nCanlı uygulama: {url}"
    elif kind == "artifact":
        footer = f"\n\n---\nYayınlanan rapor: {url}"
    else:
        footer = f"\n\n---\nTeslimat: {url}"
    return (text or "(özet yok)") + footer


def _run_meter(handle: ChildHandle, config: Any) -> dict[str, Any]:
    """Run meter: model + tokens + duration + tools + estimated USD."""
    from dataclasses import replace

    from . import pricing

    usage = {
        "girdi": int((handle.usage or {}).get("girdi") or 0),
        "cikti": int((handle.usage or {}).get("cikti") or 0),
        "cagri": int((handle.usage or {}).get("cagri") or 0),
    }
    cost: float | None = None
    model_name = str(handle.model or "")
    model_cfg = getattr(config, "model", None)
    state_dir = getattr(config, "state_dir", None)
    if model_cfg is not None and model_name:
        try:
            model_cfg = replace(model_cfg, name=model_name)
        except Exception:
            pass
    if model_cfg is not None and state_dir is not None:
        try:
            tag = pricing.etiket(model_cfg, state_dir)
        except Exception:
            tag = None
        if tag and (usage["girdi"] or usage["cikti"]):
            cost = (
                usage["girdi"] * float(tag["girdi"])
                + usage["cikti"] * float(tag["cikti"])
            )
    end = handle.bitis_ts or time.time()
    start = handle.baslangic_ts or end
    duration_s = max(0, int(end - start)) if start else 0
    tools = int(handle.tools_count or 0)
    last_tool = ""
    if handle.son_arac:
        last_tool = handle.son_arac
        if handle.son_hedef:
            last_tool += f" · {handle.son_hedef}"
    return {
        "model": model_name,
        "usage": usage,
        "cost_usd": cost,
        "tools": tools,
        "duration_s": duration_s,
        "last_tool": last_tool[:200],
        "line": _meter_line(
            model_name, usage, cost, tools, duration_s, last_tool),
    }


def _meter_line(
    model: str,
    usage: dict[str, int],
    cost: float | None,
    tools: int,
    duration_s: int,
    last_tool: str = "",
) -> str:
    """One-line summary — stays in the report file and the panel."""
    parts: list[str] = []
    if model:
        parts.append(model.rsplit("/", 1)[-1])
    tok = int(usage.get("girdi") or 0) + int(usage.get("cikti") or 0)
    if tok:
        parts.append(f"{tok} tok")
    if usage.get("cagri"):
        parts.append(f"{usage['cagri']} tur")
    if tools:
        parts.append(f"{tools} araç")
    if duration_s:
        parts.append(_fmt_duration(duration_s))
    if cost is not None:
        parts.append(
            f"≈${cost:.2f}" if cost >= 0.01 or cost == 0 else f"≈${cost:.3f}")
    if last_tool:
        parts.append(f"son: {last_tool[:80]}")
    return " · ".join(parts)


def _fmt_duration(seconds: int) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return f"{s} sn"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} dk {s} sn" if s else f"{m} dk"
    h, m = divmod(m, 60)
    return f"{h} sa {m} dk"


def _report_with_meter(handle: ChildHandle, config: Any, body: str = "") -> str:
    """Report body + the persistent meter line (so it stays after the app closes)."""
    text = (body if body is not None else _report_with_deliverable(handle)).strip()
    meter = _run_meter(handle, config)
    line = meter.get("line") or ""
    if not line:
        return text
    if line in text:
        return text
    return (text or "(özet yok)") + "\n\n---\n" + line


def _infer_deliverable(*texts: str) -> dict[str, Any] | None:
    """Extracts the final deliverable from the prompt/output: a live app or artifact address."""
    from urllib.parse import urlparse

    blob = "\n".join(str(t) for t in texts if t)
    if not blob.strip():
        return None
    m = _APP_URL_RE.search(blob)
    if m:
        raw = m.group(0).rstrip(".,;)\"]'")
        parsed = urlparse(raw)
        # Open the app's root instead of endpoints like /api/refresh.
        url = f"{parsed.scheme}://{parsed.netloc}/"
        return {"kind": "app", "url": url}
    m = _ARTIFACT_RE.search(blob)
    if m:
        path = m.group(0)
        if not path.endswith("/"):
            path += "/"
        return {"kind": "artifact", "url": path}
    return None


def _child_notice_line(title: str, text: str) -> str:
    """Carries a subagent warning into the main chat as a short line.

    A raw BadRequestError / JSON wall covered the screen like a yellow
    "answer". If the message can be extracted use it; otherwise shorten the
    first line.
    """
    raw = (text or "").strip()
    if not raw:
        return f"[{title}]"
    msg = re.search(r"'message':\s*'([^']+)'", raw) or re.search(
        r'"message"\s*:\s*"([^"]+)"', raw
    )
    if msg:
        return f"[{title}] {msg.group(1)}"
    err = re.match(r"^(\w+Error)\b", raw)
    if err and ("Error code" in raw or "{" in raw):
        return f"[{title}] {err.group(1)}"
    first = raw.split("\n", 1)[0].strip()
    return f"[{title}] {_clip(first, 140)}"


def _one_line(text: str, limit: int = 220) -> str:
    """Reduces a memory to a single line.

    The system note must stay short: it is added before every message and
    its length goes directly onto the cost of every turn.
    """
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


def _text_of_blocks(blocks: list[dict[str, Any]]) -> str:
    """Joins the text blocks of an assistant turn.

    Tool calls and thinking blocks are skipped: what enters memory is what
    the assistant said to the user — not tool arguments.
    """
    parts = [b.get("text", "") for b in blocks
             if isinstance(b, dict) and b.get("type") == "text"]
    return "\n".join(p for p in parts if p).strip()


def _last_text(session: "Session") -> str:
    """The text of the session's last assistant turn.

    This is the subagent's "result": the tool results stay in its own log,
    only the last word comes back.
    """
    for event in reversed(session.log.messages()):
        if event.role != "assistant":
            continue
        blocks = event.content if isinstance(event.content, list) else []
        text = "\n".join(
            str(b.get("text", ""))
            for b in blocks
            if isinstance(b, dict) and b.get("type") == "text"
        ).strip()
        if text:
            return text
    return ""


def _with_image(text: str, data_url: str) -> list[dict[str, Any]]:
    """Converts text + image into the Anthropic block format.

    The browser sends `data:image/png;base64,...`; the API wants the type
    and the data in separate fields.
    """
    header, _, payload = data_url.partition(",")
    media = "image/png"
    if ";" in header and ":" in header:
        media = header.split(":", 1)[1].split(";", 1)[0] or media

    blocks: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": media, "data": payload},
        }
    ]
    # Image first, text after: the model sees what it looked at first, then
    # the question. If there is no question we still say what it should
    # look at — sending only a frame and saying "let's see what you say"
    # led the model to brush it off in a single sentence.
    blocks.append({"type": "text", "text": text.strip() or LOOK_NOTE})
    return blocks


def _seen_blocks(images: list[str]) -> list[dict[str, Any]]:
    """Converts images coming from a tool into a user turn.

    They land here because they cannot be carried in the tool result. A
    short note is put next to them: the model has to read this not as a
    photo the user sent but as the result of its own looking.
    """
    blocks: list[dict[str, Any]] = []
    for data in images:
        header, _, payload = data.partition(",")
        media = "image/jpeg"
        if ";" in header and ":" in header:
            media = header.split(":", 1)[1].split(";", 1)[0] or media
        blocks.append(
            {"type": "image", "source": {"type": "base64", "media_type": media, "data": payload}}
        )
    blocks.append({"type": "text", "text": SEEN_NOTE})
    return blocks
