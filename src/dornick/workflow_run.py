"""Automation graph runner — executes the nodes in order.

Open node types: known helpers (agent, skill, http, shell, mail_read)
and `custom` (falls back to the skill name). Unknown type = agent step
(prompt config). On error it follows the fail edge; otherwise progress
is written for the heal hook.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .workflows import Workflow, WorkflowNode

# How many steps may attempt repair in one run. Unlimited repair means
# an automation that keeps breaking itself all night long.
MAX_REPAIRS = 3


async def execute_workflow(
    wf: Workflow,
    agent: Any,
    handle: Any,
    on_progress: Any = None,
) -> tuple[str, list[dict[str, Any]], bool]:
    """Run the graph. Returns: (report, progress, ok).

    `on_progress(progress)` is called whenever a node's status changes —
    on start and on finish. Without this, progress was only written when
    the run FINISHED; that is, "seeing where it is while running" was
    impossible, the flow diagram sat dead for the whole run.
    """
    if not wf.nodes:
        return ("Akışta düğüm yok.", [], False)

    def _announce(entries: list[dict[str, Any]], agent: Any, handle: Any) -> None:
        """Deliver progress to disk and (if any) to the listener.

        Errors are swallowed: the run itself matters more than watching
        it — the flow must not fall over because progress could not be
        written."""
        if on_progress is not None:
            try:
                on_progress([dict(p) for p in entries])
            except Exception:
                pass
        if not (getattr(handle, "schedule_id", None)
                and getattr(handle, "run_id", None)):
            return
        try:
            from . import task_runs
            lines = "\n".join(
                ("✓" if p.get("status") == "bitti"
                 else "…" if p.get("status") == "koşuyor" else "✗")
                + " " + str(p.get("title") or p.get("id"))
                for p in entries
            )
            task_runs.patch_run(
                agent.config.state_dir, handle.schedule_id, handle.run_id,
                report=lines or "(koşuyor)",
                nodes_progress=[dict(p) for p in entries],
                model=getattr(handle, "model", "") or "",
            )
        except Exception:
            pass

    by_id = {n.id: n for n in wf.nodes}
    # Start: nodes with no incoming edge; otherwise the first node.
    targets = {e.to for e in wf.edges}
    starts = [n.id for n in wf.nodes if n.id not in targets] or [wf.nodes[0].id]

    ctx: dict[str, Any] = {"last": "", "vars": {}}
    progress: list[dict[str, Any]] = []
    # Repair ledger: once per step, at most MAX_REPAIRS per run.
    repaired: set[str] = set()
    current = starts[0]
    visited = 0
    max_steps = max(40, len(wf.nodes) * 4)
    ok = True

    while current and visited < max_steps:
        visited += 1
        node = by_id.get(current)
        if node is None:
            progress.append({"id": current, "status": "hata", "detail": "düğüm yok"})
            ok = False
            break
        step = {"id": node.id, "title": node.title or node.id,
                "type": node.type, "status": "koşuyor"}
        progress.append(step)
        # Live trace: like an Orchestra tool event.
        try:
            agent.io.on_child_tool(handle.title, f"node:{node.id}", "start")
        except Exception:
            pass
        # Write at the START too. Writing only at the end showed nothing
        # running on screen during a long step: the previous node green,
        # the next one not there yet — the flow looked dead. The moment
        # we actually want to watch is exactly that gap.
        _announce(progress, agent, handle)

        try:
            out = await _run_node(node, ctx, agent)
            step["status"] = "bitti"
            step["detail"] = str(out)[:500]
            ctx["last"] = out
            ctx["vars"][node.id] = out
            edge_on = "ok"
        except Exception as exc:
            # The lesson is written no matter what: whether the repair
            # sticks or not, the fact that this step once broke must
            # persist.
            await _try_heal_lesson(agent, node, exc, wf.id)

            repair = ""
            if node.id not in repaired and len(repaired) < MAX_REPAIRS:
                repaired.add(node.id)
                step["status"] = "onarılıyor"
                _announce(progress, agent, handle)
                repair = await _try_repair(
                    wf, node, exc, agent, getattr(agent.config, "state_dir", None))

            if repair:
                try:
                    out = await _run_node(node, ctx, agent)
                except Exception as exc2:
                    step["status"] = "hata"
                    step["detail"] = (
                        f"onarım denendi ({repair}) ama yine düştü — "
                        f"{type(exc2).__name__}: {exc2}")
                    step["onarim"] = repair
                    ok = False
                    edge_on = "hata"
                else:
                    step["status"] = "bitti"
                    step["detail"] = str(out)[:500]
                    step["onarim"] = repair
                    ctx["last"] = out
                    ctx["vars"][node.id] = out
                    edge_on = "ok"
            else:
                step["status"] = "hata"
                step["detail"] = f"{type(exc).__name__}: {exc}"
                ok = False
                edge_on = "hata"
                step["heal"] = True
        try:
            agent.io.on_child_tool(handle.title, f"node:{node.id}", "end")
        except Exception:
            pass

        _announce(progress, agent, handle)

        nxt = _next_node(wf, current, edge_on)
        if nxt is None and edge_on == "hata":
            break
        current = nxt or ""

    report_lines = [f"# {wf.title}", ""]
    for p in progress:
        mark = "✓" if p.get("status") == "bitti" else ("…" if p.get("status") == "koşuyor" else "✗")
        report_lines.append(f"{mark} [{p.get('type')}] {p.get('title')}: {p.get('detail') or ''}")
    if ctx.get("last"):
        report_lines.extend(["", "## Son çıktı", str(ctx["last"])[:4000]])
    return "\n".join(report_lines), progress, ok


def _next_node(wf: Workflow, from_id: str, on: str) -> str | None:
    exact = [e for e in wf.edges if e.from_ == from_id and (e.on or "ok") == on]
    if exact:
        return exact[0].to
    any_edge = [e for e in wf.edges if e.from_ == from_id and not e.on]
    if any_edge and on == "ok":
        return any_edge[0].to
    return None


async def _run_node(node: WorkflowNode, ctx: dict[str, Any], agent: Any) -> str:
    kind = (node.type or "custom").strip().lower()
    cfg = dict(node.config or {})
    last = str(ctx.get("last") or "")

    if kind == "skill":
        name = node.skill or str(cfg.get("skill") or "")
        if not name:
            raise RuntimeError("skill düğümü için skill adı gerekli")
        return await _call_tool(agent, name, dict(cfg.get("args") or {}), last)

    if kind == "http":
        # An http node can carry arbitrary method/body/headers — i.e. a
        # surface that sends data out (POST/PUT…) or hammers the local
        # API (127.0.0.1). It used to run through urlopen directly: both
        # the permission gate and the hooks were bypassed. Now it goes
        # through the gate like `shell` — every non-read http call asks
        # for approval (security review, 01.09). Read-only (GET/HEAD,
        # non-local) falls to the `fetch` tool.
        url = str(cfg.get("url") or "")
        if not url:
            raise RuntimeError("http düğümü için url gerekli")
        method = str(cfg.get("method") or "GET").upper()
        local = _is_local_address(url)
        if method in ("GET", "HEAD") and not local and not cfg.get("headers") \
                and cfg.get("body") is None:
            return await _run_gated(agent, "fetch", {"url": url}, last)
        # Mutating/secret surface: push it through the permission gate.
        # It is not a registered tool, so a synthetic approval request
        # is built.
        approved = await _http_approval(agent, node, url, method, local)
        if not approved:
            raise RuntimeError(
                "http düğümü kullanıcı tarafından onaylanmadı "
                f"({method} {url}).")
        return await _http_raw(cfg, url, method)

    if kind == "shell":
        cmd = str(cfg.get("command") or cfg.get("cmd") or "")
        if not cmd:
            raise RuntimeError("shell düğümü için command gerekli")
        # Through the permission engine + hooks: it used to call
        # create_subprocess_shell directly and touched no gate at all
        # (security review, 01.09). Now it goes through approval and
        # hooks like the real `shell` tool.
        return await _run_gated(agent, "shell", {"command": cmd}, last)

    if kind in ("mail_read", "mail"):
        args = dict(cfg.get("args") or {
            "action": "list", "limit": int(cfg.get("limit") or 10)})
        return await _call_tool(agent, "mail_read", args, last)

    # agent / custom / unknown: model step (the open node model)
    prompt = str(cfg.get("prompt") or cfg.get("instruction") or node.title or "")
    if last:
        prompt = f"{prompt}\n\nÖnceki adım çıktısı:\n{last[:3000]}"
    if node.skill:
        prompt += f"\n\nGerekirse `{node.skill}` yeteneğini kullan."
    if not prompt.strip():
        prompt = f"Adımı tamamla: {node.title or node.id}"
    return await agent._spawn(node.title or node.id, prompt, "")


def _is_local_address(url: str) -> bool:
    """Does the URL target a local/private network (127.0.0.1, localhost,
    RFC1918, link-local)? Hammering the local API is the most dangerous
    http surface."""
    import ipaddress
    import urllib.parse

    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1", ""):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


async def _http_approval(agent: Any, node: WorkflowNode, url: str, method: str,
                         local: bool) -> bool:
    """Ask approval for the http node. There is no registered tool; it is
    pushed onto the permission surface (io.approve) with a synthetic spec —
    so the user sees what is being sent."""
    from .tools.base import object_schema, ToolSpec

    async def _empty(_a: dict[str, Any], _c: Any) -> Any:  # pragma: no cover
        return None

    spec = ToolSpec(
        name="workflow_http", description="Otomasyon http düğümü",
        input_schema=object_schema({}), handler=_empty, mutates=True)
    label = f"{method} {url}" + (" (YEREL AĞ)" if local else "")
    try:
        return bool(await agent.io.approve(spec, {"istek": label, "düğüm": node.id}))
    except Exception:
        return False


async def _http_raw(cfg: dict[str, Any], url: str, method: str) -> str:
    """Actually performs the approved http call."""
    import urllib.request

    data = cfg.get("body")
    body = None if data is None else (
        data if isinstance(data, (bytes, bytearray))
        else json.dumps(data).encode("utf-8"))
    req = urllib.request.Request(url, data=body, method=method)
    for hk, hv in (cfg.get("headers") or {}).items():
        req.add_header(str(hk), str(hv))
    with urllib.request.urlopen(req, timeout=float(cfg.get("timeout") or 30)) as resp:
        return resp.read()[:8000].decode("utf-8", errors="replace")


async def _call_tool(agent: Any, name: str, args: dict[str, Any], last: str) -> str:
    if last and "input" not in args:
        args = {**args, "input": last}
    return await _run_gated(agent, name, args, last, merge_input=False)


async def _run_gated(agent: Any, name: str, args: dict[str, Any], last: str,
                     *, merge_input: bool = True) -> str:
    """Runs a tool through the agent's REAL permission gate and hooks.

    The old `_call_tool` invoked `spec.handler` directly; the schema gate,
    the permission engine and both hook phases were skipped. Now it goes
    through `executor.execute`, the same path the real turn uses — the
    same approval, hooks and schema (security review, 01.09).
    """
    from .session import PendingToolUse
    from .tools.base import ToolContext
    from .tools.executor import execute

    spec = agent.registry.get(name)
    if spec is None:
        raise RuntimeError(f"Araç yok: {name}")
    if merge_input and last and "input" not in args:
        args = {**args, "input": last}

    tctx = ToolContext(
        config=agent.config, session=agent.session,
        cancel=getattr(agent, "cancel", None) or __import__("asyncio").Event(),
        schedule=agent.schedule)
    blocks = await execute(
        [PendingToolUse(id="wf", name=name, input=dict(args))],
        registry=agent.registry,
        permissions=agent.permissions,
        ctx=tctx,
        approve=agent.io.approve,
        observe=getattr(agent, "_observe", lambda *_: None),
    )
    block = blocks[0] if blocks else {}
    content = block.get("content", "")
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    if block.get("is_error"):
        raise RuntimeError(text or "araç hata verdi")
    return text


async def _try_heal_lesson(agent: Any, node: WorkflowNode, exc: BaseException,
                           wf_id: str = "") -> None:
    """Failure lesson — written to memory with a fixed template.

    The template being fixed matters for the personal fine-tune that runs
    at night: if the same event is not written the same way every time,
    there is no pattern left to learn.
    """
    from . import workflow_mind

    workflow_mind.recall_lesson(getattr(agent, "mind", None), wf_id, node, exc)


async def _try_repair(
    wf: Workflow, node: WorkflowNode, exc: BaseException, agent: Any,
    state_dir: Any,
) -> str:
    """Tries once to repair the broken step. Returns: what changed (empty if nothing).

    The limits are deliberately tight:

      * ONE attempt per step per run (the caller counts). Unlimited repair
        means an automation that keeps breaking itself all night long.
      * A step with `elle=True` is NOT TOUCHED. The model rewriting a step
        the user deliberately wrote is not a fix but a silent revert.
      * Only `config` and `skill` may change; the node's type, its id and
        the shape of the graph are not left to the model.
      * What changed is returned and written into the report — a silent
        repair is not a repair, it is a surprise.
    """
    if node.elle:
        return ""
    if not hasattr(agent, "_spawn"):
        return ""

    from . import workflows as store

    prompt = (
        "Bir otomasyon adımı hata verdi. Görevin YALNIZCA bu adımın "
        "ayarını düzeltmek.\n\n"
        f"Adım türü: {node.type}\n"
        f"Adım başlığı: {node.title or node.id}\n"
        f"Şu anki config (JSON): {json.dumps(node.config, ensure_ascii=False)}\n"
        f"Yetenek: {node.skill or '(yok)'}\n"
        f"Hata: {type(exc).__name__}: {exc}\n\n"
        "Yalnızca düzeltilmiş config'i JSON nesnesi olarak döndür. Başka "
        "hiçbir şey yazma. Düzeltilecek bir şey göremiyorsan {} döndür."
    )
    try:
        reply = await agent._spawn(f"onar:{node.id}", prompt, "")
    except Exception:
        return ""

    new_config = _json_object(str(reply or ""))
    if not new_config or new_config == node.config:
        return ""

    old = dict(node.config)
    node.config = new_config
    try:
        store.save(state_dir, store.to_dict(wf))
    except Exception:
        node.config = old   # if it could not be written, revert the in-memory state too
        return ""

    changed = sorted(set(old) ^ set(new_config)) or [
        k for k in new_config if old.get(k) != new_config.get(k)]
    return ", ".join(str(k) for k in changed[:6]) or "config"


def _json_object(text: str) -> dict[str, Any] | None:
    """The first JSON object in the model's reply. None if not found.

    Raw `loads` is not enough in case the model adds a code fence or an
    explanation; but we do not guess either — if no object is found, no
    repair happens.
    """
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None
