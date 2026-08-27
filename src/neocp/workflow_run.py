"""Otomasyon grafiği koşucusu — düğümleri sırayla işletir.

Açık düğüm türleri: bilinen yardımcılar (agent, skill, http, shell, mail_read)
ve `custom` (skill adına düşer). Bilinmeyen tür = agent adımı (prompt config).
Hata olursa fail kenarına gider; yoksa heal kancası için progress'e yazılır.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .workflows import Workflow, WorkflowNode

# Bir koşuda kaç adım onarılmayı deneyebilir. Sınırsız onarım,
# gece boyunca kendi kendini bozan bir otomasyon demek.
AZAMI_ONARIM = 3


async def execute_workflow(
    wf: Workflow,
    agent: Any,
    handle: Any,
    on_progress: Any = None,
) -> tuple[str, list[dict[str, Any]], bool]:
    """Grafiği koştur. Dönüş: (rapor, progress, ok).

    `on_progress(progress)` her düğüm durumu değiştiğinde çağrılıyor —
    başlarken ve biterken. Bu olmadan ilerleme yalnızca koşu BİTİNCE
    yazılıyordu; yani "çalışırken nerede olduğunu görmek" mümkün değildi,
    akış şeması koşu boyunca ölü duruyordu.
    """
    if not wf.nodes:
        return ("Akışta düğüm yok.", [], False)

    def _duyur(kayit: list[dict[str, Any]], ajan: Any, tutamac: Any) -> None:
        """İlerlemeyi diske ve (varsa) dinleyiciye ver.

        Hata yutuluyor: koşunun kendisi, izlenmesinden önemli — ilerleme
        yazılamadı diye akış düşmemeli."""
        if on_progress is not None:
            try:
                on_progress([dict(p) for p in kayit])
            except Exception:
                pass
        if not (getattr(tutamac, "schedule_id", None)
                and getattr(tutamac, "run_id", None)):
            return
        try:
            from . import task_runs
            satir = "\n".join(
                ("✓" if p.get("status") == "bitti"
                 else "…" if p.get("status") == "koşuyor" else "✗")
                + " " + str(p.get("title") or p.get("id"))
                for p in kayit
            )
            task_runs.patch_run(
                ajan.config.state_dir, tutamac.schedule_id, tutamac.run_id,
                report=satir or "(koşuyor)",
                nodes_progress=[dict(p) for p in kayit],
                model=getattr(tutamac, "model", "") or "",
            )
        except Exception:
            pass

    by_id = {n.id: n for n in wf.nodes}
    # Başlangıç: kimseye kenar gelmeyen düğümler; yoksa ilk düğüm.
    targets = {e.to for e in wf.edges}
    starts = [n.id for n in wf.nodes if n.id not in targets] or [wf.nodes[0].id]

    ctx: dict[str, Any] = {"last": "", "vars": {}}
    progress: list[dict[str, Any]] = []
    # Onarım defteri: adım başına bir kez, koşu başına en fazla AZAMI_ONARIM.
    onarilanlar: set[str] = set()
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
        # Canlı iz: Orkestra tool olayı gibi.
        try:
            agent.io.on_child_tool(handle.title, f"node:{node.id}", "start")
        except Exception:
            pass
        # BAŞLARKEN de yaz. Yalnız bitişte yazmak, uzun süren bir adım
        # boyunca ekranda koşan hiçbir şey göstermiyordu: önceki düğüm
        # yeşil, sonraki henüz yok — akış ölü görünüyordu. Asıl izlenmek
        # istenen an tam da bu ara.
        _duyur(progress, agent, handle)

        try:
            out = await _run_node(node, ctx, agent)
            step["status"] = "bitti"
            step["detail"] = str(out)[:500]
            ctx["last"] = out
            ctx["vars"][node.id] = out
            edge_on = "ok"
        except Exception as exc:
            # Ders her hâlükârda yazılıyor: onarım tutsa da tutmasa da bu
            # adımın bir kez bozulduğu bilgisi kalıcı olmalı.
            await _try_heal_lesson(agent, node, exc, wf.id)

            onarildi = ""
            if node.id not in onarilanlar and len(onarilanlar) < AZAMI_ONARIM:
                onarilanlar.add(node.id)
                step["status"] = "onarılıyor"
                _duyur(progress, agent, handle)
                onarildi = await _onarmayi_dene(
                    wf, node, exc, agent, getattr(agent.config, "state_dir", None))

            if onarildi:
                try:
                    out = await _run_node(node, ctx, agent)
                except Exception as exc2:
                    step["status"] = "hata"
                    step["detail"] = (
                        f"onarım denendi ({onarildi}) ama yine düştü — "
                        f"{type(exc2).__name__}: {exc2}")
                    step["onarim"] = onarildi
                    ok = False
                    edge_on = "hata"
                else:
                    step["status"] = "bitti"
                    step["detail"] = str(out)[:500]
                    step["onarim"] = onarildi
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

        _duyur(progress, agent, handle)

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
        import urllib.request
        url = str(cfg.get("url") or "")
        if not url:
            raise RuntimeError("http düğümü için url gerekli")
        method = str(cfg.get("method") or "GET").upper()
        data = cfg.get("body")
        body = None if data is None else (
            data if isinstance(data, (bytes, bytearray))
            else json.dumps(data).encode("utf-8"))
        req = urllib.request.Request(url, data=body, method=method)
        for hk, hv in (cfg.get("headers") or {}).items():
            req.add_header(str(hk), str(hv))
        with urllib.request.urlopen(req, timeout=float(cfg.get("timeout") or 30)) as resp:
            return resp.read()[:8000].decode("utf-8", errors="replace")

    if kind == "shell":
        import asyncio
        cmd = str(cfg.get("command") or cfg.get("cmd") or "")
        if not cmd:
            raise RuntimeError("shell düğümü için command gerekli")
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await proc.communicate()
        text = (out or b"").decode("utf-8", errors="replace")[:8000]
        if proc.returncode:
            raise RuntimeError(text or f"exit {proc.returncode}")
        return text

    if kind in ("mail_read", "mail"):
        args = dict(cfg.get("args") or {
            "action": "list", "limit": int(cfg.get("limit") or 10)})
        return await _call_tool(agent, "mail_read", args, last)

    # agent / custom / bilinmeyen: model adımı (açık düğüm modeli)
    prompt = str(cfg.get("prompt") or cfg.get("instruction") or node.title or "")
    if last:
        prompt = f"{prompt}\n\nÖnceki adım çıktısı:\n{last[:3000]}"
    if node.skill:
        prompt += f"\n\nGerekirse `{node.skill}` yeteneğini kullan."
    if not prompt.strip():
        prompt = f"Adımı tamamla: {node.title or node.id}"
    return await agent._spawn(node.title or node.id, prompt, "")


async def _call_tool(agent: Any, name: str, args: dict[str, Any], last: str) -> str:
    import asyncio

    from .tools.base import ToolContext

    spec = agent.registry.get(name)
    if spec is None:
        raise RuntimeError(f"Araç yok: {name}")
    if last and "input" not in args:
        args = {**args, "input": last}
    tctx = ToolContext(
        config=agent.config, session=agent.session,
        cancel=asyncio.Event(), schedule=agent.schedule)
    result = await spec.handler(args, tctx)
    if getattr(result, "error", False):
        raise RuntimeError(str(result.content))
    return str(result.content)


async def _try_heal_lesson(agent: Any, node: WorkflowNode, exc: BaseException,
                           wf_id: str = "") -> None:
    """Hata dersi — hafızaya sabit kalıpla yazılır.

    Kalıbın sabit olması gece koşan kişisel ince ayar için önemli: aynı
    olay her seferinde aynı biçimde yazılmazsa ortada öğrenilecek bir
    örüntü kalmıyor.
    """
    from . import workflow_mind

    workflow_mind.dersi_hatirla(getattr(agent, "mind", None), wf_id, node, exc)


async def _onarmayi_dene(
    wf: Workflow, node: WorkflowNode, exc: BaseException, agent: Any,
    state_dir: Any,
) -> str:
    """Bozulan adımı bir kez onarmayı dener. Döndürdüğü: ne değiştiği (boşsa yok).

    Sınırlar bilerek dar:

      * Adım başına koşuda TEK deneme (çağıran sayıyor). Sınırsız onarma,
        gece boyunca kendi kendini bozan bir otomasyon demek.
      * `elle=True` adıma DOKUNULMAZ. Kullanıcının bilerek yazdığı bir adımı
        modelin arkasından yeniden yazması düzeltme değil, sessizce geri
        alma olur.
      * Yalnızca `config` ve `skill` değişebilir; düğümün türü, kimliği ve
        grafiğin şekli modele bırakılmıyor.
      * Ne değiştiği geri döndürülüyor ve rapora yazılıyor — sessiz onarım,
        onarım değil sürprizdir.
    """
    if node.elle:
        return ""
    if not hasattr(agent, "_spawn"):
        return ""

    from . import workflows as store

    istem = (
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
        cevap = await agent._spawn(f"onar:{node.id}", istem, "")
    except Exception:
        return ""

    yeni = _json_nesnesi(str(cevap or ""))
    if not yeni or yeni == node.config:
        return ""

    eski = dict(node.config)
    node.config = yeni
    try:
        store.save(state_dir, store.to_dict(wf))
    except Exception:
        node.config = eski      # yazılamadıysa bellekteki hâli de geri al
        return ""

    degisen = sorted(set(eski) ^ set(yeni)) or [
        k for k in yeni if eski.get(k) != yeni.get(k)]
    return ", ".join(str(k) for k in degisen[:6]) or "config"


def _json_nesnesi(metin: str) -> dict[str, Any] | None:
    """Modelin cevabından ilk JSON nesnesi. Bulamazsa None.

    Model kod bloğu ya da açıklama eklerse diye ham `loads` yetmiyor; ama
    tahmin de yürütmüyoruz — nesne bulunamazsa onarım yapılmıyor.
    """
    metin = metin.strip()
    if metin.startswith("```"):
        metin = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", metin).strip()
    bas = metin.find("{")
    son = metin.rfind("}")
    if bas < 0 or son <= bas:
        return None
    try:
        veri = json.loads(metin[bas:son + 1])
    except ValueError:
        return None
    return veri if isinstance(veri, dict) else None
