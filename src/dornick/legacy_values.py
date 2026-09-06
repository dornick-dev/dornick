"""One-time maps from the Turkish state values and schema keys used until 1.5.4.

`legacy_names` adopts files and folders; this module adopts what is INSIDE
them. Every value the product compares against or stores — a task state, a
sleep state, a helper kind, a usage counter, a temperament axis, a night
event kind — is English from 1.5.5 on. Records written by an older build
still sit on the user's disk with the old words in them, and a saved
permission rule, a hook file or a session log may name an old tool
parameter. The maps here are the ONLY place the old words survive: a
reader passes a loaded value through `state()`, `kind()`, `sleep_state()`
or `keys()` and never sees the old form again; a writer never produces it.

Nothing here rewrites a file on its own. Upgrading happens on read, so an
install that never opens an old record never pays for it, and a record
opened by an older build (a downgrade, a shared folder) is still what it
was. The one exception is the files whose readers ALSO write them back
(`temperament.json`, `sleep_debt.json`, `config.json`): those come out in
the new form the first time they are saved.
"""

from __future__ import annotations

from typing import Any, Mapping

# -- state values ----------------------------------------------------------

# Task, run, lane, schedule, workflow, plan, test-run and hook statuses.
# `koşuyor` (with the Turkish ş) was the task-run store's spelling and
# `kosuyor` the helper ledger's; both mean the same thing.
STATES: dict[str, str] = {
    "kosuyor": "running", "koşuyor": "running",
    "bitti": "done",
    "hata": "error",
    "yetim": "orphan",
    "kesildi": "interrupted",
    "iptal": "cancelled",
    "bekliyor": "waiting",
    "onaylandi": "approved",
    "yapiliyor": "in_progress",
    "atlandi": "skipped", "atlandı": "skipped",
    "baslatilamadi": "failed_to_start", "başlatılamadı": "failed_to_start",
    "onariliyor": "repairing", "onarılıyor": "repairing",
    "zaman_asimi": "timeout",
    "kostu": "ran",
    "temiz": "clean",
    "yok": "none",
    "acik": "open", "açık": "open",
    "biten": "finished",
}

# How a session ended (session.Session.outcome, read by the night).
OUTCOMES: dict[str, str] = {
    "basarisiz": "failed",
    "duzeltildi": "corrected",
    "acik": "open",
    "basarili": "succeeded",
    "rutin": "routine",
}

# Helper ledger kinds and the `kind` the panels draw.
KINDS: dict[str, str] = {
    "yardımcı": "helper", "yardimci": "helper",
    "iş": "job", "is": "job",
    "süreç": "process", "surec": "process",
}

# The sleep switch and the night's phases.
SLEEP_STATES: dict[str, str] = {
    "uyanik": "awake", "uyanık": "awake",
    "uykulu": "sleepy",
    "uyuyor": "asleep",
    "uyaniyor": "waking", "uyanıyor": "waking",
    "kestirme": "nap",
}
PHASES: dict[str, str] = {"derin": "deep", "hafif": "light", "rem": "rem"}

# Why the switch moved (journal `reason`, night event `reason`).
REASONS: dict[str, str] = {
    "basinc": "pressure", "basinc dustu": "pressure dropped", "hazir": "ready",
    "ritim": "rhythm", "atalet bitti": "inertia over", "oreksin": "orexin",
    "kullanici": "user", "kafein": "caffeine", "gece bitti": "night over",
    "orgu kapali": "weave off", "kapanis": "shutdown", "kullanici istedi": "user asked",
}

# The memory's use-log labels (`node.use_log[*].label`).
USE_LABELS: dict[str, str] = {
    "yazildi": "written", "acildi": "opened", "basari": "success",
    "hata": "error", "sema": "schema", "yakalandi": "caught",
}

# Workflow edge conditions (`edges[*].on` in a workflow file).
EDGE_CONDITIONS: dict[str, str] = {"hata": "error", "ok": "ok"}

# -- schema keys -----------------------------------------------------------

# Usage counters: the helper ledger, the task-run archive, the price table.
USAGE_KEYS: dict[str, str] = {"girdi": "input", "cikti": "output", "cagri": "calls"}

# Temperament axes and the blocks of `temperament.json`.
AXES: dict[str, str] = {"yenilik": "novelty", "sonuc": "outcome", "sosyal": "social",
                        "sebat": "persistence", "temkin": "caution"}
TEMPERAMENT_KEYS: dict[str, str] = {"taban": "baseline", "hedef": "target",
                                    "kazanc": "gain"}

# Decision exemplars (`decision_exemplars.json`) and the probe sets.
EXEMPLAR_KEYS: dict[str, str] = {"kararlar": "decisions", "eksen": "axis",
                                 "durum": "situation", "karar": "decision"}
PROBE_KEYS: dict[str, str] = {"ad": "name", "aciklama": "description", "surum": "version",
                              "kararlar": "decisions", "eksen": "axis", "mesaj": "message",
                              "secenekler": "options", "yuksek": "high",
                              "baglamlar": "contexts"}

# Session meta (`sessions/_meta.json`).
SESSION_META_KEYS: dict[str, str] = {"ad": "name", "etiketler": "tags"}

# The change ledger (`changes/<session>/ledger.jsonl`).
LEDGER_KEYS: dict[str, str] = {"sira": "seq", "dosya": "file", "arac": "tool",
                               "zaman": "time", "goruntu": "snapshot", "yoktu": "missing",
                               "atlandi": "skipped"}

# Hooks (`hooks.json`).
HOOK_KEYS: dict[str, str] = {"olay": "event", "arac": "tool", "komut": "command",
                             "zaman_asimi": "timeout"}
HOOK_EVENTS: dict[str, str] = {"arac_oncesi": "before_tool", "arac_sonrasi": "after_tool"}

# Sleep debt (`sleep_debt.json`) and the night watermark.
DEBT_KEYS: dict[str, str] = {"faz": "phase", "devreden": "carried"}
WATERMARK_KEYS: dict[str, str] = {"islenen": "processed", "son_kosu": "last_run"}

# The sleep journal (`sleep_journal.jsonl`).
JOURNAL_KEYS: dict[str, str] = {"eski": "old", "yeni": "new", "sebep": "reason"}

# Artifact meta (`meta.json` beside each artifact page).
ARTIFACT_KEYS: dict[str, str] = {"surum": "version"}

# Recognition status file.
RECOGNITION_KEYS: dict[str, str] = {"son_kosu": "last_run"}

# `setup.json` written by the installer.
SETUP_KEYS: dict[str, str] = {"dil": "language"}

# The `sleep` block of `config.json`.
SLEEP_CONFIG_KEYS: dict[str, str] = {"uyku_acik": "enabled"}

# The session log's own note names and meta keys.
SESSION_NOTES: dict[str, str] = {
    "ters_tekrar_kostu": "reverse_replay_done", "ileri_tekrar_kostu": "forward_replay_mark",
    "sonuc": "outcome", "baslik": "title", "butce_freni": "budget_brake",
    "giris_kapisi": "entry_gate", "hata_dersi": "error_lesson", "is_kapsulu": "job_capsule",
    "kabul_kapisi": "acceptance_gate", "kirmizi_kapisi": "red_gate",
    "plan_refleksi": "plan_reflex", "sahte_arac_cagrisi": "fake_tool_call",
    "test_kapisi": "test_gate", "uyanik_tekrar_failed": "awake_replay_failed",
    "zihin_durtusu": "mind_impulse",
}
SESSION_NOTE_META: dict[str, str] = {
    "sonuc": "outcome", "ozet": "summary", "oturum": "session", "dosya": "file",
    "dosyalar": "files", "ad": "name", "durum": "status", "acik": "open",
    "detay": "detail", "anahtar": "keys", "deneme": "attempts",
}

# Night events: kind names, then the fields of every kind.
NIGHT_KINDS: dict[str, str] = {
    "uyku.basladi": "sleep.started", "uyku.dongu": "sleep.cycle",
    "tekrar.ileri": "replay.forward", "tekrar.geri": "replay.reverse",
    "dikis": "stitch", "dokunus": "touch", "damitma": "distil",
    "uyku.uyandi": "sleep.woke", "uyku.bitti": "sleep.ended",
    "uyanik.ters": "awake.reverse",
    "mikro.basladi": "micro.started", "mikro.bitti": "micro.ended",
    "yerel.basladi": "local.started", "yerel.bitti": "local.ended",
}
NIGHT_FIELDS: dict[str, str] = {
    "tur": "kind", "basinc": "pressure", "tahmini_uyanma": "wake_estimate",
    "dongu_sayisi": "cycle_count", "faz": "phase", "oturum": "session",
    "dizi": "sequence", "kenarlar": "edges", "sonuc": "outcome", "paylar": "shares",
    "uzerinden": "via", "oturumlar": "sessions", "kaynaklar": "sources", "yeni": "new",
    "sebep": "reason", "dongu": "cycle", "tamamlanan": "completed",
    "devreden": "carried", "borc": "debt", "rapor": "report", "bolge": "region",
    "kuculen": "shrunk", "atlanan": "skipped",
}
NIGHT_SUMMARY_KEYS: dict[str, str] = {
    "dongu": "cycles", "tekrar": "replays", "kenar": "edges", "dikis": "stitches",
    "damitik": "distilled", "dokunus": "touches", "uyandi": "woke", "devreden": "carried",
}

# Character SSE events (`character{event}`) and their fields.
CHARACTER_EVENTS: dict[str, str] = {"karakter.hata": "character.error",
                                    "karakter.olcum": "character.measured"}
CHARACTER_FIELDS: dict[str, str] = {"onceki": "previous", "taban": "baseline",
                                    "kazanc": "gain", "emsal_kaydedildi": "precedent_recorded",
                                    "cagri": "calls", "hata": "error"}

# Context breakdown ids (the dock's segments; also CSS class names).
BREAKDOWN_IDS: dict[str, str] = {"sistem": "system", "arac": "tools", "ruh": "soul",
                                 "yetenek": "skills", "mcp": "mcp", "yardimci": "helpers",
                                 "sohbet": "chat"}

# Model-facing tool parameters (per tool) and enum values.
TOOL_PARAMS: dict[str, dict[str, str]] = {
    "run": {"komut": "command", "zaman_asimi": "timeout", "sadece_tespit": "detect_only"},
    "symbols": {"sorgu": "query", "tur": "kind", "dil": "language"},
    "browser": {"seviye": "level"},
    "camera": {"adet": "count"},
    "task": {"arka_plan": "background"},
    "shell": {"arka_plan": "job"},
}
TOOL_ENUMS: dict[str, dict[str, dict[str, str]]] = {
    "symbols": {"kind": {"tanim": "definitions", "kullanim": "usages", "hepsi": "all"}},
    "browser": {"level": {"hepsi": "all", "hata": "errors", "uyari": "warnings"},
                "action": {"konsol": "console", "ag": "network"}},
    "camera": {"action": {"liste": "list", "yol": "path", "kesit": "capture"}},
}

# The `_config` block inside a writer bundle (`base.npz`) and its arrays.
WRITER_CONFIG_KEYS: dict[str, str] = {"kat": "layers", "kafa": "heads"}
WRITER_ARRAYS: dict[str, str] = {"_ayar": "_config", "gomme": "embed", "konum": "pos",
                                 "son.w": "final.w", "son.b": "final.b"}

# Browser-side localStorage keys and their boolean words.
LOCAL_STORAGE_KEYS: dict[str, str] = {"dornick-dil": "dornick-language",
                                      "dornick-beyin-ayrinti": "dornick-brain-details"}


# -- helpers ----------------------------------------------------------------


def state(value: Any) -> str:
    """A task/run/plan/schedule status in its English form."""
    text = str(value or "")
    return STATES.get(text, STATES.get(text.strip().casefold(), text))


def outcome(value: Any) -> str:
    text = str(value or "")
    return OUTCOMES.get(text, text)


def kind(value: Any) -> str:
    text = str(value or "")
    return KINDS.get(text, text)


def sleep_state(value: Any) -> str:
    text = str(value or "")
    return SLEEP_STATES.get(text, text)


def phase(value: Any) -> str:
    text = str(value or "")
    return PHASES.get(text, text)


def reason(value: Any) -> str:
    text = str(value or "")
    return REASONS.get(text, text)


def use_label(value: Any) -> str:
    text = str(value or "")
    return USE_LABELS.get(text, text)


def edge_condition(value: Any) -> str:
    text = str(value or "")
    return EDGE_CONDITIONS.get(text, text)


def keys(data: Mapping[str, Any] | None, table: Mapping[str, str]) -> dict[str, Any]:
    """A shallow copy of `data` with every key in `table` renamed.

    A record that already carries the new key keeps it: the new form wins
    over the old when both are present (a file touched by two builds).
    """
    if not isinstance(data, Mapping):
        return {}
    out: dict[str, Any] = {}
    for key, value in data.items():
        new = table.get(str(key), str(key))
        if new != key and new in data:
            continue
        out[new] = value
    return out


def usage(data: Mapping[str, Any] | None) -> dict[str, int]:
    """`{input, output, calls}` from either spelling; missing counters are 0."""
    fixed = keys(data, USAGE_KEYS)
    return {name: int(fixed.get(name) or 0) for name in ("input", "output", "calls")}


def night_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """One night event with its kind and fields in the 1.5.5 vocabulary."""
    out = keys(event, NIGHT_FIELDS)
    if "kind" in out:
        out["kind"] = NIGHT_KINDS.get(str(out["kind"]), str(out["kind"]))
    if "phase" in out:
        out["phase"] = phase(out["phase"])
    if "outcome" in out:
        out["outcome"] = outcome(out["outcome"])
    if "reason" in out:
        out["reason"] = reason(out["reason"])
    if "debt" in out and isinstance(out["debt"], Mapping):
        out["debt"] = keys(out["debt"], DEBT_KEYS)
        if "phase" in out["debt"]:
            out["debt"]["phase"] = phase(out["debt"]["phase"])
    if "report" in out and isinstance(out["report"], Mapping):
        out["report"] = dict(out["report"])
    return out


def session_note(name: str, meta: Mapping[str, Any] | None) -> tuple[str, dict[str, Any]]:
    """A session-log note (name, meta) as a 1.5.5 build writes it."""
    new_name = SESSION_NOTES.get(name, name)
    fixed = keys(meta, SESSION_NOTE_META)
    if new_name in ("outcome", "reverse_replay_done") and "outcome" in fixed:
        fixed["outcome"] = outcome(fixed["outcome"])
    return new_name, fixed


def tool_args(tool: str, args: Mapping[str, Any] | None) -> dict[str, Any]:
    """Tool arguments with old parameter names and enum values translated.

    Used by the executor before validation and by the permission gate, so a
    session log replayed from an older build and a rule saved under the old
    words both mean what they meant.
    """
    if not isinstance(args, Mapping):
        return {}
    out = keys(args, TOOL_PARAMS.get(tool, {}))
    for field, values in TOOL_ENUMS.get(tool, {}).items():
        if field in out and isinstance(out[field], str):
            out[field] = values.get(out[field], out[field])
    return out


def temperament_axes(data: Mapping[str, Any] | None) -> dict[str, Any]:
    return keys(data, AXES)
