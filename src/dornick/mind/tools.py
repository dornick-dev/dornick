"""Zihni ajana araç olarak açar.

Dört araç, hepsi `action`/`aspect` enum'lu — otuz düz araç yerine dört
gezinilebilir yüzey. Açıklamalar bilinçli olarak *ne zaman çağrılacağını*
söyler; sadece ne yaptığını anlatan açıklamalar modeli tetiklemekte belirgin
şekilde daha zayıf.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from ..tools.base import ToolContext, ToolRegistry, ToolResult, object_schema
from .search import excerpt
from .store import MEMORY_KINDS, Mind

MAX_RECALL = 20

# Tek bir bellek isabetinin cevaba taşıyabileceği azami gövde. Sınırsızdı ve
# bir episode kaydı (sıkıştırma özeti 8.000 harfe kadar) tek başına binlerce
# token yiyebiliyordu — altı isabetlik bir cevapta gerçek eşleşme boğuluyordu.
# Kırpılan kayıt kaybolmuş değil: model sorguyu daraltıp yeniden arayabilir.
RECALL_BODY_CAP = 700


def _adim_etiket(mind: Mind, node_id: str) -> str:
    """İz adımının kısa etiketi — sahne grafikte olmayan düğümü de adıyla
    yakabilsin (hayalet düğüm; bkz. scene.js activate)."""
    try:
        node = mind.store.peek(node_id)
    except Exception:
        return ""
    if node is None:
        return ""
    metin = str(getattr(node, "title", "") or getattr(node, "content", "") or "")
    tek = " ".join(metin.split())
    return tek if len(tek) <= 34 else tek[:33] + "…"


def _sicil_notu(mind: Mind, node_id: str) -> str:
    """`[3 başarı / 1 hata]` — modelin "bu bazen yanıltıyor" bilgisi.

    Gece ters tekrarı bu sicili yazıyor (recall/orgu.py); burada yalnız
    görünür kılınıyor. Sicili olmayan kayıtta hiçbir şey eklenmiyor.
    """
    try:
        basari, hata = mind.store.sicil(node_id)
    except Exception:
        return ""
    return f"\n[{basari} başarı / {hata} hata]" if (basari or hata) else ""


def _one_satir(text: str, cap: int = 80) -> str:
    tek = " ".join((text or "").split())
    return tek if len(tek) <= cap else tek[:cap - 1] + "…"


def _bounded(text: str, cap: int = RECALL_BODY_CAP) -> str:
    if len(text) <= cap:
        return text
    return text[:cap] + "… (kırpıldı; gerekiyorsa sorguyu daraltıp yeniden ara)"


def register(registry: ToolRegistry, mind: Mind) -> None:
    _recall(registry, mind)
    _memory(registry, mind)
    _goals(registry, mind)
    _introspect(registry, mind)


# -- arama -------------------------------------------------------------


def _recall(registry: ToolRegistry, mind: Mind) -> None:
    @registry.tool(
        name="mind_recall",
        description="""
Kendi belleğinde arama yapar: kaydettiğin bilgiler ve geçmiş oturumlarında
gerçekte olanlar.

Şu durumlarda çağır: kullanıcı daha önce konuştuğunuz bir şeye atıf yapıyor;
bu makinede/projede daha önce bir şey denemiş olabileceğini düşünüyorsun;
bir tercihi ya da kararı hatırlaman gerekiyor; benzer bir görevi daha önce
çözmüş olabilirsin. Emin değilsen ara — hatırlamadığını varsayarak baştan
başlamak hem yavaş hem de kullanıcıyı kendini tekrar etmeye zorlar.

Mevcut oturum aramaya dahil değildir; o zaten önündeki bağlamda.
        """,
        input_schema=object_schema(
            {
                "query": {
                    "type": "string",
                    "description": "Aranacak konu. Doğal dil; anahtar kelimeler yeterli.",
                },
                "scope": {
                    "type": "string",
                    "enum": ["all", "memory", "episodes"],
                    "description": "memory: kaydettiğin bilgiler. episodes: geçmiş oturumlar. Varsayılan all.",
                },
                "kind": {
                    "type": "string",
                    "enum": list(MEMORY_KINDS),
                    "description": "Bellek türüyle daralt (yalnızca scope=memory için).",
                },
                "limit": {"type": "integer", "description": "Kaç sonuç (varsayılan 6)."},
            },
            required=["query"],
        ),
    )
    async def mind_recall(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = (args.get("query") or "").strip()
        if not query:
            return ToolResult.error("Boş sorgu. Ne aradığını `query` alanına yaz.")

        scope = args.get("scope") or "all"
        limit = max(1, min(int(args.get("limit") or 6), MAX_RECALL))
        sections: list[str] = []

        if scope in ("all", "memory"):
            hits = mind.recall(query, kind=args.get("kind"), limit=limit)
            # Aktivasyonun uğradığı yol arayüze gidiyor: hatırlarken hangi
            # düğümden hangisine geçtiği canlandırılabilsin. `used` işareti
            # ŞART: bu yol işaretsiz yayınlayınca arayüz "eski kayıt" sanıp
            # dokunulan HER kaydı numaralıyordu — 28 kayıtlık bir sorguda
            # BTC fiyatı bile "kullanıldı" görünüyordu; oysa modelin önüne
            # yalnız süzülen ilk birkaçı konur (loop.py'deki otomatik yol
            # bu işareti zaten koyuyordu, araç yolu unutulmuştu).
            if mind.last_trace:
                used = {h.item.id for h in hits}
                ctx.session.log.note(
                    "recall_trace",
                    query=query,
                    trace=[{**asdict(step), "used": step.node in used,
                            "label": _adim_etiket(mind, step.node)}
                           for step in mind.last_trace],
                )
            # Okunan hatıra kullanılmış hatıradır: iz güçleniyor ve olay
            # günlüğüne düşüyor. Önceki hal hiçbir yerde `open()` çağırmıyordu
            # — yani üretimde pekiştirme diye bir şey hiç olmuyordu.
            for h in hits:
                mind.store.open(h.item.id)
                ctx.session.log.note("mind_open", memory_id=h.item.id,
                                     kind=h.item.kind)
            sections.append(
                _section(
                    "Bellek",
                    [
                        f"[{h.item.id}] {_bounded(h.item.render())}"
                        + _sicil_notu(mind, h.item.id)
                        for h in hits
                    ],
                )
            )

        if scope in ("all", "episodes"):
            hits = mind.episodes(query, limit=limit)
            sections.append(
                _section(
                    "Geçmiş oturumlar",
                    [
                        f"[{h.item.session_id}] {h.item.turns} tur"
                        + (f" · araçlar: {', '.join(h.item.tools)}" if h.item.tools else "")
                        + f"\n{excerpt(h.item.digest, h.matched)}"
                        for h in hits
                    ],
                )
            )

        body = "\n\n".join(s for s in sections if s)
        if not body:
            return ToolResult(
                content=f"'{query}' için zihinde kayıt yok. Bu konu senin için yeni."
            )
        return ToolResult(content=body)


# -- yazma / silme -----------------------------------------------------


def _memory(registry: ToolRegistry, mind: Mind) -> None:
    @registry.tool(
        name="mind_memory",
        description="""
Belleğine yazar, siler ya da listeler.

Ne zaman kaydet: kullanıcı bir tercih belirttiğinde ("hep şöyle yap"),
bir düzeltme yaptığında (nedeniyle birlikte), bu makineye/projeye özgü ve
koddan çıkarılamayacak bir şey öğrendiğinde, ya da işe yarayan bir yordam
bulduğunda (kind=procedure).

Bunu O AN yap, tur sonuna bırakma — konu geçerken yazılmayan şey yazılmıyor.
İzin istemene gerek yok, kendi defterin. Yazmadığın şey, gelecekteki senin
bilmeyeceği şeydir: kullanıcı aynı şeyi ikinci kez anlatmak zorunda kalır.

Ne zaman kaydetme: repoda zaten yazılı olanı, konuşma bitince değeri
kalmayacak şeyleri, doğrulamadığın tahminleri.

Aynı konuda kayıt varsa `supersedes` ile güncelle: eski kaydın kimliğini
ver, yenisi onun yerini alsın. Hiçbir şey silinmiyor — eski sürüm `series`
ile hâlâ görülebiliyor, ama aramaya ve ruha artık yenisi giriyor. Çelişen
iki hatıra hiç hatıra olmamasından kötüdür; silmek de öyle.

Kimliği hatırlamıyorsan yine de kaydet: benzer bir kayıt varsa araç sana
onun kimliğini söyler, sen ikinci bir çağrıyla birleştirirsin.

Zihnin bir liste değil, bir ağ. Kayıtlar kendiliğinden birbirine benzeyene
bağlanıyor ama asıl bağları sen kuruyorsun: `link` ile iki kaydı bağlarken
**neden** bağlı olduğunu yaz. O gerekçe kenarda duruyor ve sonraki
hatırlamalar o yoldan yürüyor.

Ölçüm kaydediyorsan (fiyat, sıcaklık, doluluk) hepsine aynı etiketi ver ve
`series` ile zinciri getir. "Dünden bugüne ne oldu" sorusunun cevabı böyle
çıkıyor — tek tek hatırlayıp kafadan sıralamakla değil.
        """,
        input_schema=object_schema(
            {
                "action": {
                    "type": "string",
                    "enum": ["save", "forget", "list", "link", "series"],
                    "description": (
                        "save: yeni kayıt. forget: id ile sil. list: türe göre listele. "
                        "link: iki kaydı birbirine bağla. series: aynı etiketli "
                        "kayıtları eskiden yeniye getir."
                    ),
                },
                "content": {"type": "string", "description": "Kaydedilecek metin (save)."},
                "title": {"type": "string", "description": "Kısa başlık (save, isteğe bağlı)."},
                "kind": {
                    "type": "string",
                    "enum": list(MEMORY_KINDS),
                    "description": (
                        "fact: doğrulanmış bilgi. preference: kullanıcının tercihi. "
                        "lesson: yanlış gidenden çıkan ders. procedure: işe yarayan yordam."
                    ),
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Sonradan bulmayı kolaylaştıran etiketler. Aynı şeyin "
                        "zaman içindeki ölçümlerine aynı etiketi ver "
                        "(\"btc-fiyat\" gibi) — `series` o zinciri getirir."
                    ),
                },
                "id": {"type": "string", "description": "Kaydın kimliği (forget, link)."},
                "supersedes": {
                    "type": "string",
                    "description": (
                        "save ile birlikte: bu kayıt hangi kaydın yerini "
                        "alıyor. Eski kayıt silinmez, geçmişe düşer."
                    ),
                },
                "to": {"type": "string", "description": "Bağlanacak ikinci kaydın kimliği (link)."},
                "link_to": {
                    "type": "string",
                    "description": (
                        "save ile birlikte: yeni kaydı bu kayda bağla. Kaydedip "
                        "sonra ayrıca `link` çağırmak iki adım; bu tek adım ve "
                        "atlanması zor."
                    ),
                },
                "reason": {
                    "type": "string",
                    "description": (
                        "İki kaydın neden bağlı olduğu (link ya da save+link_to). "
                        "Kenarda duruyor ve "
                        "sonra çağrışım bu yoldan yürüyor: \"aynı ölçümün bir "
                        "sonraki günü\", \"bunun sebebi şu\" gibi."
                    ),
                },
                "tag": {"type": "string", "description": "Zaman dizisi etiketi (series)."},
            },
            required=["action"],
        ),
        mutates=True,
        # Kendi defterine yazmak sistem mutasyonu değil: onay penceresi
        # arkasında kalınca zihin iki gün boyunca hiçbir tercih/ders
        # kaydetmedi. `forget` (kalıcı silme) listede YOK — o gated kalıyor.
        safe_actions=("save", "list", "link", "series"),
        parallel_safe=False,
    )
    async def mind_memory(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        action = args.get("action")

        if action == "save":
            content = (args.get("content") or "").strip()
            if not content:
                return ToolResult.error("`content` boş. Ne hatırlaman gerektiğini yaz.")
            kind = args.get("kind") or "fact"
            eskisi = (args.get("supersedes") or "").strip()
            if eskisi:
                try:
                    memory = mind.guncelle(
                        eskisi, content, kind=kind,
                        title=args.get("title") or "",
                        tags=args.get("tags") or [])
                except ValueError as hata:
                    return ToolResult.error(
                        f"{hata} Kimlikleri mind_recall ya da action=list ile bul.")
                ctx.session.log.note("mind_write", memory_id=memory.id,
                                     kind=memory.kind, supersedes=eskisi)
                note = (f"Güncellendi [{eskisi}] → [{memory.id}] "
                        f"({memory.kind}) {memory.title}\n"
                        "Eski sürüm silinmedi; `series` ile hâlâ görülebilir.")
            else:
                # Aday YAZMADAN ÖNCE aranıyor: yazdıktan sonra en yakın
                # komşu kaydın kendisi olurdu.
                aday = mind.celiski_adayi(content, kind)
                memory = mind.remember(
                    content, kind=kind,
                    title=args.get("title") or "",
                    tags=args.get("tags") or [],
                )
                ctx.session.log.note("mind_write", memory_id=memory.id,
                                     kind=memory.kind)
                note = f"Kaydedildi [{memory.id}] ({memory.kind}) {memory.title}"
                # Model `supersedes` vermeyi unutmuş olabilir. Kayıt yine de
                # yazıldı — kaçırmamak temiz olmaktan önemli — ama aynı
                # konuda bir kayıt varsa kimliği söyleniyor; birleştirme
                # kararı modelin.
                if aday is not None and aday.id != memory.id:
                    note += (
                        f"\nBenzer kayıt var [{aday.id}]: "
                        f"'{_one_satir(aday.content)}'. Bunu güncelliyorsan "
                        f"supersedes={aday.id} ile tekrar çağır; farklı bir "
                        "şeyse olduğu gibi kaydedildi.")

            # Kaydetmekle bağlamak tek çağrıda: ayrı adım bırakıldığında
            # model çoğu zaman ikincisini atlıyor ve "bağladım" diyor.
            if target := (args.get("link_to") or "").strip():
                reason = args.get("reason") or ""
                if mind.bridge(memory.id, target, reason) is None:
                    note += f"\nUyarı: '{target}' bulunamadı, bağlanamadı."
                else:
                    ctx.session.log.note(
                        "mind_link", src=memory.id, dst=target, reason=reason
                    )
                    note += f"\nBağlandı → [{target}]" + (f" · {reason}" if reason else "")

            return ToolResult(content=note, detail={"id": memory.id})

        if action == "forget":
            memory_id = args.get("id") or ""
            removed = mind.forget(memory_id)
            if removed is None:
                return ToolResult.error(
                    f"'{memory_id}' diye bir kayıt yok ya da zaten silinmiş. "
                    "Kimlikleri mind_recall ya da action=list ile bul."
                )
            ctx.session.log.note("mind_forget", memory_id=memory_id)
            return ToolResult(content=f"Silindi [{memory_id}] {removed.title}")

        if action == "list":
            items = mind.memories(args.get("kind"))
            if not items:
                return ToolResult(content="Bellek boş.")
            return ToolResult(
                content="\n".join(
                    f"[{m.id}] ({m.kind}) {m.title}" for m in items[:MAX_RECALL]
                )
            )

        if action == "link":
            src, dst = args.get("id") or "", args.get("to") or ""
            if not src or not dst:
                return ToolResult.error(
                    "Bağlamak için iki kimlik gerekli: `id` ve `to`. "
                    "Kimlikleri mind_recall ya da action=list ile bul."
                )
            pair = mind.bridge(src, dst, args.get("reason") or "")
            if pair is None:
                return ToolResult.error(f"'{src}' ya da '{dst}' bulunamadı.")

            first, second = pair
            ctx.session.log.note("mind_link", src=src, dst=dst,
                                 reason=args.get("reason") or "")
            return ToolResult(
                content=f"Bağlandı: {first.title} → {second.title}",
                detail={"src": src, "dst": dst},
            )

        if action == "series":
            tag = args.get("tag") or ""
            items = mind.series(tag)
            if not items:
                return ToolResult(
                    content=f"'{tag}' etiketiyle kayıt yok. Ölçümleri kaydederken "
                    "aynı etiketi kullanırsan zaman dizisi oluşur."
                )
            lines = [f"'{tag}' — eskiden yeniye {len(items)} kayıt:"]
            for memory in items:
                lines.append(f"[{memory.ts[:16]}] {memory.content}")
            return ToolResult(content="\n".join(lines), detail={"tag": tag, "count": len(items)})

        return ToolResult.error(
            "`action` save, forget, list, link ya da series olmalı."
        )


# -- hedefler ----------------------------------------------------------


def _goals(registry: ToolRegistry, mind: Mind) -> None:
    @registry.tool(
        name="mind_goals",
        description="""
Hedef yığınını yönetir — üzerinde çalıştığın işin kaydı.

Çok adımlı bir göreve başlarken hedefi push et; bitirdiğinde done işaretle.
Aktif hedefler uzun görevlerin ortasında sana operatör kanalından geri
hatırlatılır, böylece asıl amacı kaybetmezsin.

Tek adımlık işler için kullanma; kayıt tutmanın maliyeti getirisinden fazla.
        """,
        input_schema=object_schema(
            {
                "action": {
                    "type": "string",
                    "enum": ["push", "done", "drop", "list"],
                    "description": "push: yeni hedef. done: tamamlandı. drop: vazgeçildi. list: aktifler.",
                },
                "text": {"type": "string", "description": "Hedef metni (push)."},
                "id": {"type": "string", "description": "Hedef kimliği (done/drop)."},
                "note": {"type": "string", "description": "Sonuç notu (done/drop)."},
            },
            required=["action"],
        ),
        mutates=True,
        # İş listesi de ajanın kendi defteri: her hedef için onay sormak
        # uzun bir işi soru yağmuruna çeviriyordu.
        safe_actions=("push", "done", "drop", "list"),
        parallel_safe=False,
    )
    async def mind_goals(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        action = args.get("action")

        if action == "push":
            text = (args.get("text") or "").strip()
            if not text:
                return ToolResult.error("`text` boş. Hedefi yaz.")
            goal = mind.push_goal(text)
            ctx.session.log.note("goal_push", goal_id=goal.id, text=text)
            return ToolResult(content=f"Hedef eklendi [{goal.id}]\n\n{mind.goal_digest()}")

        if action in ("done", "drop"):
            status = "done" if action == "done" else "dropped"
            goal = mind.set_goal_status(args.get("id") or "", status, args.get("note") or "")
            if goal is None:
                return ToolResult.error(
                    f"'{args.get('id')}' diye bir hedef yok. action=list ile aktifleri gör."
                )
            ctx.session.log.note("goal_status", goal_id=goal.id, status=status)
            digest = mind.goal_digest() or "Aktif hedef kalmadı."
            return ToolResult(content=f"[{goal.id}] {status}\n\n{digest}")

        if action == "list":
            return ToolResult(content=mind.goal_digest() or "Aktif hedef yok.")

        return ToolResult.error("`action` push, done, drop ya da list olmalı.")


# -- içgözlem ----------------------------------------------------------


def _introspect(registry: ToolRegistry, mind: Mind) -> None:
    @registry.tool(
        name="mind_introspect",
        description="""
Kendi anlık durumuna bakar: bu oturumda ne yaptın, hangi araçlar başarısız
oldu, bağlamın ne kadarını harcadın, önbellek çalışıyor mu.

Şu durumlarda çağır: aynı yerde ikinci kez takıldığını fark ettiğinde (ne
denediğine bak, tekrarlama); uzun bir görevin ortasında yönünü kaybettiğinde;
kullanıcı "ne yaptın" diye sorduğunda; bağlamın dolmakta olduğundan
şüphelendiğinde.
        """,
        input_schema=object_schema(
            {
                "aspect": {
                    "type": "string",
                    "enum": ["all", "session", "context", "goals", "memory"],
                    "description": "Hangi yüzey. Varsayılan all.",
                }
            }
        ),
    )
    async def mind_introspect(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        aspect = args.get("aspect") or "all"
        want = (lambda name: aspect in ("all", name))
        blocks: list[str] = []

        if want("session"):
            blocks.append(_session_report(ctx))
        if want("context"):
            blocks.append(_context_report(ctx))
        if want("goals"):
            blocks.append(_section("Hedefler", [mind.goal_digest() or "aktif hedef yok"]))
        if want("memory"):
            counts = {k: len(mind.memories(k)) for k in MEMORY_KINDS}
            total = sum(counts.values())
            detail = ", ".join(f"{k}: {v}" for k, v in counts.items() if v)
            blocks.append(_section("Bellek", [f"{total} kayıt" + (f" ({detail})" if detail else "")]))

        return ToolResult(content="\n\n".join(b for b in blocks if b))


def _session_report(ctx: ToolContext) -> str:
    log = ctx.session.log
    starts = log.notes("tool_start")
    ends = log.notes("tool_end")
    failures = [e for e in ends if e.meta.get("error")]
    denials = [e for e in log.notes("permission") if e.meta.get("decision") == "deny"]

    lines = [
        f"oturum: {ctx.session.id}",
        f"model turu: {sum(1 for m in log.messages() if m.role == 'assistant')}",
        f"araç çağrısı: {len(starts)} ({len(failures)} hata)",
    ]
    if denials:
        lines.append(f"engellenen çağrı: {len(denials)}")

    if failures:
        recent = [f"  - {e.meta.get('tool')}" for e in failures[-5:]]
        lines.append("son başarısız araçlar:")
        lines.extend(recent)

    # Aynı komutu tekrar tekrar denemek en sık takılma biçimi.
    commands = [
        json.dumps(e.meta.get("input"), ensure_ascii=False, sort_keys=True) for e in starts
    ]
    if repeats := [c for c in set(commands) if commands.count(c) >= 3]:
        lines.append(f"DİKKAT: {len(repeats)} çağrı 3+ kez aynı argümanlarla tekrarlandı.")

    return _section("Oturum", ["\n".join(lines)])


def _context_report(ctx: ToolContext) -> str:
    log = ctx.session.log
    last_usage = next(
        (m.meta.get("usage") for m in reversed(log.messages()) if m.meta.get("usage")),
        None,
    )
    lines = [
        f"mesaj: {len(log.messages())}",
        f"içerik bloğu: {ctx.session.block_count()}",
    ]
    if last_usage:
        lines.append(
            f"son istek: {last_usage.get('prompt_total', 0):,} token "
            f"(önbellekten {last_usage.get('cache_read', 0):,})"
        )
        if last_usage.get("cache_read", 0) == 0 and last_usage.get("prompt_total", 0) > 4096:
            lines.append("önbellek okuması sıfır — istek öneki her turda değişiyor olabilir.")
    return _section("Bağlam", ["\n".join(lines)])


def _section(title: str, items: list[str]) -> str:
    body = "\n\n".join(i for i in items if i)
    return f"## {title}\n{body}" if body else ""
