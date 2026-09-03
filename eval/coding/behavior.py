"""BEHAVIOUR metrics from the session log — reported, never scored.

The score measures *what was delivered*. This file measures *how it
worked*: how many tools it called, whether it verified its own code,
whether it wrote a plan, how many tokens it burned. The two are kept
apart because behaviour is a source of HYPOTHESES, not a target: reward
"wrote a plan" and the agent will write plans while the code still fails.

The honesty rule applies here too: every metric is grounded in a CONCRETE
record in the session log. A metric with no evidence returns `None`
("could not be extracted"), never 0 — "did not verify" and "could not
read it from the log" are different things.

Log format (dornick.events.EventLog, JSONL):
  {"kind":"meta","content":"tool_start","meta":{"tool":"shell","input":{...}}}
  {"kind":"meta","content":"tool_end","meta":{"tool":"...","error":bool,"ms":int}}
  {"kind":"message","role":"assistant","content":[...],"meta":{"usage":{...}}}
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

# Self-verification trail: checkers run from the shell.
VERIFY_COMMAND = re.compile(
    r"\bpytest\b|\bunittest\b|python\s+-m\s+py_compile|\bpy_compile\b|"
    r"\bruff\b|\bmypy\b|node\s+--test|node\s+--check|\bnpm\s+test\b|"
    r"php\s+-l\b|\bphpunit\b|\bcurl\b|Invoke-WebRequest|\bwget\b|"
    r"python\s+-c|py\s+-c|node\s+-e|php\s+-r",
    re.IGNORECASE,
)
# Actually running the product is verification too: `py servis.py`, `node app.js …`
RUN_COMMAND = re.compile(
    r"^\s*(py|python|python3|node|php)\s+[\w./\\-]+\.(py|js|mjs|php)\b",
    re.IGNORECASE | re.MULTILINE,
)
# Diagnostic/browser tools: the name alone is evidence.
VERIFY_TOOLS = {"denetle", "browser"}

# Plan trail: at least three numbered or bulleted lines before the first tool call.
PLAN_LINE = re.compile(r"^\s*(?:\d+[.)]\s+|[-*•]\s+|\[[ x]\]\s*)", re.MULTILINE)


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(str(b.get("text", "")) for b in content
                     if isinstance(b, dict) and b.get("type") == "text")


def events(log: Path) -> list[dict[str, Any]]:
    if not log.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def extract(log: Path, *, gate: dict[str, Any] | None = None,
            model_name: str = "", state_dir: Path | None = None) -> dict[str, Any]:
    """Extract behaviour metrics from a session log.

    `gate`: the dict returned by the external gate (POST /api/gate) — wall
    time and changed files come from there; they are not in the log.
    """
    records = events(log)
    if not records:
        return {"unextractable": f"session log unreadable: {log}"}

    tools: Counter[str] = Counter()
    tool_errors = 0
    tool_ms = 0.0
    error_kinds: Counter[str] = Counter()
    primes: list[set[str]] = []      # distinctive traces of each prime block
    primes_used = 0
    later_text: list[str] = []       # assistant text + tool input AFTER a prime
    verify_trail: list[str] = []
    run_trail: list[str] = []
    first_tool_seq: int | None = None
    plan_evidence = ""
    turns = 0
    output_tokens = 0
    last_prompt = 0
    prompt_total = 0
    cache_read = 0
    calls = 0
    api_errors = 0

    for ev in records:
        kind = ev.get("kind")
        content = ev.get("content")
        meta = ev.get("meta") or {}

        if kind == "meta" and content == "tool_start":
            name = str(meta.get("tool") or "")
            tools[name] += 1
            later_text.append(json.dumps(meta.get("input") or {},
                                         ensure_ascii=False))
            if first_tool_seq is None:
                first_tool_seq = int(ev.get("seq") or 0)
            payload = meta.get("input")
            command = ""
            if isinstance(payload, dict):
                command = str(payload.get("command") or payload.get("path") or "")
            if name in VERIFY_TOOLS:
                verify_trail.append(f"{name}: {command[:70]}")
            elif name == "shell" and command:
                if VERIFY_COMMAND.search(command):
                    verify_trail.append(f"shell: {command[:90]}")
                elif RUN_COMMAND.search(command):
                    run_trail.append(f"shell: {command[:90]}")

        elif kind == "meta" and content == "tool_end":
            tool_ms += float(meta.get("ms") or 0)
            if meta.get("error"):
                tool_errors += 1

        elif kind == "meta" and content == "api_error":
            api_errors += 1

        elif kind == "message" and ev.get("role") == "user":
            # Error texts inside tool results: top patterns go to the report.
            for b in (content if isinstance(content, list) else []):
                if isinstance(b, dict) and b.get("type") == "tool_result"                         and b.get("is_error"):
                    ozet = " ".join(str(b.get("content"))[:64].split())
                    error_kinds[ozet] += 1

        elif kind == "message" and ev.get("role") == "system":
            # Spontaneous-recall blocks: for every injected record, keep
            # its distinctive traces (words of >=6 letters) for the
            # later-usage check.
            metin = _text(content)
            if "kendiliginden hatirlandi" in metin:
                for satir in metin.splitlines():
                    if satir.startswith("- ["):
                        izler = {k.casefold() for k in satir.split()
                                 if len(k) >= 6 and k[0].isalpha()}
                        if izler:
                            primes.append(izler)

        elif kind == "message" and ev.get("role") == "assistant":
            later_text.append(_text(content))
            turns += 1
            usage = meta.get("usage")
            if isinstance(usage, dict) and usage.get("prompt_total"):
                last_prompt = int(usage.get("prompt_total") or 0)
                prompt_total += last_prompt
                output_tokens += int(usage.get("output") or 0)
                cache_read += int(usage.get("cache_read") or 0)
                calls += 1
            # Plan: a listed narrative BEFORE the first tool call.
            if first_tool_seq is None and not plan_evidence:
                body = _text(ev.get("content"))
                if len(PLAN_LINE.findall(body)) >= 3:
                    plan_evidence = " ".join(body.split())[:120]

    # Injected-but-unused: does a distinctive trace from the prime block
    # appear in assistant text or tool input AFTER the block?
    # (A rough measure — the first-class metric the external review asked for.)
    sonrasi = " ".join(later_text).casefold()
    for izler in primes:
        if any(iz in sonrasi for iz in izler):
            primes_used += 1

    cost = _cost(model_name, prompt_total, output_tokens, state_dir)

    out: dict[str, Any] = {
        "tool_calls": sum(tools.values()),
        "tools": dict(tools.most_common()),
        "tool_errors": tool_errors,
        "model_turns": turns,
        "api_errors": api_errors,
        "verified": bool(verify_trail),
        "verify_trail": verify_trail[:8],
        "run_trail": run_trail[:5],
        "wrote_plan": bool(plan_evidence),
        "plan_evidence": plan_evidence,
        # `prompt_tokens_last` is how full the context ended up;
        # `prompt_tokens_total` is what the bill sees (every call pays for
        # its own prompt).
        "prompt_tokens_last": last_prompt or None,
        "prompt_tokens_total": prompt_total or None,
        "output_tokens": output_tokens or None,
        "cache_read_tokens": cache_read or None,
        "model_calls": calls or None,
        "cost_usd": cost,
        # Time split (the review's prerequisite metric): tool time is the
        # sum of tool_end.ms; model time = wall - tool (when the gate gave one).
        "tool_time_s": round(tool_ms / 1000, 1) or None,
        "primes_injected": len(primes) or None,
        "primes_used": primes_used if primes else None,
        "error_kinds": dict(error_kinds.most_common(3)) or None,
    }
    if gate:
        out["duration_s"] = gate.get("gecen_sn")
        try:
            out["model_time_s"] = round(float(gate.get("gecen_sn") or 0)
                                        - tool_ms / 1000, 1)
        except (TypeError, ValueError):
            pass
        out["changed_files"] = len(gate.get("dosyalar") or [])
        out["gate_ok"] = bool(gate.get("ok"))
        if not gate.get("ok"):
            out["gate_error"] = gate.get("error")
    if not calls:
        # If the provider gave no counters, we do not invent numbers.
        out["token_note"] = "provider returned no token counters — unmeasured"
    return out


def _cost(model_name: str, prompt_tokens: int, output_tokens: int,
          state_dir: Path | None) -> float | None:
    """USD cost from the product's own price table. Unknown price → None.

    `fiyat.etiket` returns None for models missing from the catalogue or
    for other providers; so do we. No invented figures.
    """
    if not model_name or not prompt_tokens:
        return None
    try:
        from dornick.config import ModelConfig, OPENROUTER_URL
        from dornick import pricing as price_module
    except Exception:
        return None
    try:
        tag = price_module.etiket(
            ModelConfig(name=model_name, base_url=OPENROUTER_URL),
            state_dir, ag=False)
    except Exception:
        return None
    if not tag:
        return None
    return round(prompt_tokens * tag["girdi"] + output_tokens * tag["cikti"], 4)
