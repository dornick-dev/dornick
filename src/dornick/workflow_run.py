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
        # http düğümü keyfi metot/gövde/başlık taşıyabiliyor — yani dışarı
        # veri gönderen (POST/PUT…) ya da yerel API'yi (127.0.0.1) döven bir
        # yüzey. Eskiden doğrudan urlopen ile koşuyordu: izin kapısı da
        # kancalar da devre dışıydı. Artık `shell` gibi kapıdan geçiyor —
        # okuma dışı her http çağrısı için onay sorulur (güvenlik denetimi,
        # 01.09). Salt-okuma (GET/HEAD, yerel olmayan) `fetch` aracına düşer.
        url = str(cfg.get("url") or "")
        if not url:
            raise RuntimeError("http düğümü için url gerekli")
        method = str(cfg.get("method") or "GET").upper()
        yerel = _yerel_adres(url)
        if method in ("GET", "HEAD") and not yerel and not cfg.get("headers") \
                and cfg.get("body") is None:
            return await _gecir(agent, "fetch", {"url": url}, last)
        # Mutasyon/gizli yüzey: izin kapısına sok. Kayıtlı bir araç değil,
        # o yüzden sentetik bir onay isteği kuruluyor.
        onay = await _http_onay(agent, node, url, method, yerel)
        if not onay:
            raise RuntimeError(
                "http düğümü kullanıcı tarafından onaylanmadı "
                f"({method} {url}).")
        return await _http_ham(cfg, url, method)

    if kind == "shell":
        cmd = str(cfg.get("command") or cfg.get("cmd") or "")
        if not cmd:
            raise RuntimeError("shell düğümü için command gerekli")
        # İzin motoru + kancalar üzerinden: eskiden doğrudan
        # create_subprocess_shell çağrılıyordu ve hiçbir kapıya değmiyordu
        # (güvenlik denetimi, 01.09). Artık gerçek `shell` aracı gibi
        # onaydan ve kancadan geçiyor.
        return await _gecir(agent, "shell", {"command": cmd}, last)

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


def _yerel_adres(url: str) -> bool:
    """URL yerel/özel bir ağı mı hedefliyor (127.0.0.1, localhost, RFC1918,
    link-local)? Yerel API'yi dövmek en tehlikeli http yüzeyi."""
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


async def _http_onay(agent: Any, node: WorkflowNode, url: str, method: str,
                     yerel: bool) -> bool:
    """http düğümü için onay iste. Kayıtlı araç yok; sentetik spec ile
    izin yüzeyine (io.approve) sokuluyor — kullanıcı ne gönderildiğini görsün."""
    from .tools.base import object_schema, ToolSpec

    async def _bos(_a: dict[str, Any], _c: Any) -> Any:  # pragma: no cover
        return None

    spec = ToolSpec(
        name="workflow_http", description="Otomasyon http düğümü",
        input_schema=object_schema({}), handler=_bos, mutates=True)
    etiket = f"{method} {url}" + (" (YEREL AĞ)" if yerel else "")
    try:
        return bool(await agent.io.approve(spec, {"istek": etiket, "düğüm": node.id}))
    except Exception:
        return False


async def _http_ham(cfg: dict[str, Any], url: str, method: str) -> str:
    """Onaylanmış http çağrısını gerçekten yapar."""
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
    return await _gecir(agent, name, args, last, birlestir=False)


async def _gecir(agent: Any, name: str, args: dict[str, Any], last: str,
                 *, birlestir: bool = True) -> str:
    """Bir aracı ajanın GERÇEK izin kapısından ve kancalarından geçirerek
    koşturur.

    Eski `_call_tool` doğrudan `spec.handler`'ı çağırıyordu; şema kapısı,
    izin motoru ve iki kanca aşaması es geçiliyordu. Artık asıl turun
    kullandığı `executor.execute` yoluyla — onay, kanca ve şema aynı
    (güvenlik denetimi, 01.09).
    """
    from .session import PendingToolUse
    from .tools.base import ToolContext
    from .tools.executor import execute

    spec = agent.registry.get(name)
    if spec is None:
        raise RuntimeError(f"Araç yok: {name}")
    if birlestir and last and "input" not in args:
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
    blok = blocks[0] if blocks else {}
    icerik = blok.get("content", "")
    metin = icerik if isinstance(icerik, str) else json.dumps(icerik, ensure_ascii=False)
    if blok.get("is_error"):
        raise RuntimeError(metin or "araç hata verdi")
    return metin


async def _try_heal_lesson(agent: Any, node: WorkflowNode, exc: BaseException,
                           wf_id: str = "") -> None:
    """Hata dersi — hafızaya sabit kalıpla yazılır.

    Kalıbın sabit olması gece koşan kişisel ince ayar için önemli: aynı
    olay her seferinde aynı biçimde yazılmazsa ortada öğrenilecek bir
    örüntü kalmıyor.
    """
    from . import workflow_mind

    workflow_mind.recall_lesson(getattr(agent, "mind", None), wf_id, node, exc)


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
