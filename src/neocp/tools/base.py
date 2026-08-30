"""Araç tipleri ve kayıt defteri.

Araç şeması modelin gördüğü tek dokümantasyondur. İki tasarım kuralı:

  1. Az sayıda, güçlü araç. Onlarca düz araç modeli boğar; ilgili eylemleri
     bir `action` enum'u altında topla.
  2. Hatalar öğretici olsun. "element bulunamadı" değil, "element bulunamadı —
     ekran değişmiş olabilir, yeni bir görüntü al" de. Model bir sonraki turda
     kendini düzeltir; sen bir tur kazanırsın.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Config
    from ..session import Session

Block = dict[str, Any]


@dataclass(slots=True)
class ToolResult:
    """Bir araç çağrısının sonucu.

    content düz metin ya da blok listesi olabilir (görüntü döndüren araçlar
    için blok listesi şart).
    """

    content: str | list[Block]
    is_error: bool = False
    # Modele gitmeyen, günlüğe ve zihin arayüzüne giden ek bilgi.
    detail: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def error(cls, message: str, **detail: Any) -> ToolResult:
        return cls(content=message, is_error=True, detail=detail)

    def to_block(self, tool_use_id: str) -> Block:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": self.content,
            "is_error": self.is_error,
        }


class JobFailed(Exception):
    """Arka plan işi bitti ama başarısız.

    Mesajı kullanıcı raporudur — ham traceback değil. `_job_round` bunu
    `hata` durumuna çevirir; aksi halde koşu 'tamamlandı' görünür.
    """


@dataclass(slots=True)
class ToolContext:
    config: "Config"
    session: "Session"
    # Kullanıcı kesmesi. Uzun süren araçlar bunu periyodik yoklamalı.
    cancel: asyncio.Event

    # Alt ajan başlatıcı. Döngü kuruyor; araç katmanı `Agent`i tanımıyor
    # (tanısaydı içe aktarma çemberi olurdu) ve None ise `task` aracı hiç
    # kaydedilmiyor.
    spawn: Callable[[str, str, str], Awaitable[str]] | None = None

    # Arka plan yardımcı başlatıcı: hemen defter kaydını (handle) döndürür,
    # iş arkada koşar ve bitince ana ajana bildirilir. None ise `task`
    # aracının `arka_plan` seçeneği çalışmaz.
    spawn_bg: Callable[[str, str, str], Any] | None = None

    # Koşan ya da bitmiş bir yardımcıya sonradan mesaj (task_say) ve
    # yardımcıların durum özeti (task_status). Döngü veriyor; alt ajanda None.
    child_say: Callable[[str, str], tuple[bool, str]] | None = None
    child_status: Callable[[str], str] | None = None

    # Uzun ama BİTEN bir işi (derleme, kurulum, test koşusu) arka plana
    # alır: kayıt defterine yazar, bitince çıktısı harness notuyla ajana
    # bildirilir. `shell` gibi araçların `arka_plan` seçeneği bunu kullanır.
    # Runner kendi kesme bayrağını alır; ana interrupt hepsini kurar.
    job_bg: Callable[[str, Callable[[asyncio.Event], Awaitable[str]]], Any] | None = None

    # Zamanlanmış görev defteri. Döngü veriyor; None ise `schedule`
    # aracı kendini kullanılamaz ilan ediyor.
    schedule: Any = None

    # Otomasyon grafiği koşturucu (workflow run). None ise araç stub döner.
    run_workflow: Callable[[str], Awaitable[Any]] | None = None

    # Yerel kameranın sürekli açık tamponu. Kareler burada duruyor ve
    # kendiliğinden modele gitmiyor; `look` aracı istediğinde alınıyor.
    lens: Any = None

    # Sürekli dinleyen kulak. `senses` aracı bununla susturuyor — kulağı
    # kapatamayan bir ajan, "kapalıyım" deyip dinlemeye devam ediyordu.
    ear: Any = None

    # Ağ kameralarının izleyicisi. "Beni izleme" onları da kapsıyor.
    watcher: Any = None

    # HUD/sohbet kamera anahtarı: True açar, False aygıtı bırakır.
    camera_power: Callable[[bool], str] | None = None

    # Atölye ilk erişimde açılıyor: klasörü oluşturmak bir yan etki ve
    # her ToolContext kurulduğunda değil, gerçekten gerektiğinde olmalı.
    _sandbox: Any = None

    @property
    def workspace(self) -> Path:
        return self.config.workspace

    @property
    def sandbox(self) -> Any:
        """Ajanın kendi klasörü. Yazma yalnızca burada serbest."""
        if self._sandbox is None:
            self._sandbox = self.config.open_sandbox()
        return self._sandbox


Handler = Callable[[dict[str, Any], ToolContext], Awaitable[ToolResult]]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Handler
    # Sistem durumunu değiştiriyor mu? İzin motoru buna bakar.
    mutates: bool = False
    # `mutates` olsa bile onay GEREKTİRMEYEN eylemler (`action` alanı).
    #
    # Kanıtlanmış yara: ajanın KENDİ defterine yazması (`mind_memory
    # save`) mutasyon sayılıyordu. Sonuç: her hatıra için kullanıcıya onay
    # penceresi, plan kipinde ise düpedüz RET. Zihin iki gün boyunca
    # hiçbir tercih/ders/olgu kaydetmedi — konuşma dökümü akmaya devam
    # ederken kalıcı bellek durdu. Kendi not defterine yazmak bir sistem
    # mutasyonu değil; SİLMEK (forget) hâlâ öyle ve gated kalıyor.
    safe_actions: tuple[str, ...] = ()
    # Aynı turda diğer araçlarla eşzamanlı çalışabilir mi?
    parallel_safe: bool = True
    # Hangi MCP sunucusundan geldi (yerel araçlar için None).
    source: str | None = None

    def api_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"Araç zaten kayıtlı: {spec.name}")
        self._tools[spec.name] = spec
        return spec

    def replace(self, spec: ToolSpec) -> ToolSpec:
        """Var olan bir yeteneğin üstüne taze halini koyar.

        Yalnızca yetenekler: ajan kendi yazdığı dosyayı düzeltip yeniden
        yüklediğinde bellekteki eski hali çalışmaya devam ediyordu — ajan
        bunu fark edip "cache'li hal eski kodu kullanıyor" diyerek her
        seferinde kabuğa düşüyordu. Yerleşik bir aracın üzerine yazmaksa
        yasak: `shell` adında bir yetenek, izin kapısını değiştirirdi.
        """
        current = self._tools.get(spec.name)
        if current is not None and current.source != spec.source:
            raise ValueError(f"Yerleşik aracın üzerine yazılamaz: {spec.name}")
        self._tools[spec.name] = spec
        return spec

    def unregister(self, name: str) -> bool:
        """Yeteneği defterden düşürür. Yerleşik araçlar düşürülemez."""
        spec = self._tools.get(name)
        if spec is None or spec.source is None:
            return False
        del self._tools[name]
        return True

    def tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        *,
        mutates: bool = False,
        parallel_safe: bool = True,
        safe_actions: tuple[str, ...] = (),
    ) -> Callable[[Handler], Handler]:
        def decorate(fn: Handler) -> Handler:
            self.register(
                ToolSpec(
                    name=name,
                    description=description.strip(),
                    input_schema=input_schema,
                    handler=fn,
                    mutates=mutates,
                    parallel_safe=parallel_safe,
                    safe_actions=safe_actions,
                )
            )
            return fn

        return decorate

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def all(self) -> list[ToolSpec]:
        """Ada göre sıralı. Sıra deterministik olmalı.

        Araçlar istekte 0. pozisyonda render edilir; sıraları değişirse
        önbelleğin tamamı geçersiz olur.
        """
        return [self._tools[k] for k in sorted(self._tools)]

    def api_schemas(self, *, brief: bool = False) -> list[dict[str, Any]]:
        """Araçların API şeması.

        `brief` küçük pencereli modeller için: açıklamanın yalnızca ilk
        paragrafı gönderiliyor. 4096 token'lık bir modelde araç açıklamaları
        tek başına pencerenin dörtte birini yiyor ve konuşmaya yer kalmıyor.
        """
        schemas = [t.api_schema() for t in self.all()]
        if not brief:
            return schemas

        for schema in schemas:
            schema["description"] = _first_paragraph(schema.get("description", ""))
        return schemas


def object_schema(
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }


# -- şema doğrulaması ---------------------------------------------------
#
# Kanıtlanmış zincir: model `write_file`'ı `path` olmadan çağırdı → araç
# içinde `args["path"]` patladı → modele HAM `KeyError: 'path'` gitti →
# model bunu "araç bozuk" sanıp gerçek çağrı yerine çağrı XML'ini düz metin
# yazdı → kullanıcı ekranında ham XML.
#
# Zincirin ilk halkası burada kırılıyor: handler ÇAĞRILMADAN önce çağrı
# şemaya vuruluyor ve uymuyorsa modele istisna değil YÖNERGE dönüyor —
# hangi alan eksik, ne verdin, şema ne. Tek merkezden: her araç için aynı
# güvence, tek tek araçlara yama gerekmiyor.

# JSON Schema tipleri → Python karşılıkları. `number` int'i de kabul eder
# (JSON'da 1 hem integer hem number); `bool` int'in alt sınıfı olduğu için
# sayı kontrollerinde ayrıca eleniyor.
_JSON_TIPLERI: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def _tip_uyar(deger: Any, tip: str) -> bool:
    beklenen = _JSON_TIPLERI.get(tip)
    if beklenen is None:
        return True   # tanımadığımız tip: karışma
    if tip in ("number", "integer") and isinstance(deger, bool):
        return False  # True bir sayı değil; model karıştırdıysa söylensin
    return isinstance(deger, beklenen)


def _sema_ozeti(schema: dict[str, Any], limit: int = 6) -> str:
    """Şemanın tek satırlık hali: "path (string, zorunlu), text (string)".

    Modelin şemayı zaten görmüş olması yetmiyor — hatanın yanında tekrar
    görmek düzeltmeyi aynı turda mümkün kılıyor.
    """
    props = schema.get("properties")
    if not isinstance(props, dict):
        return ""
    zorunlu = set(schema.get("required") or [])
    parcalar: list[str] = []
    for ad, tanim in list(props.items())[:limit]:
        tip = (tanim or {}).get("type", "any") if isinstance(tanim, dict) else "any"
        etiket = f"{ad} ({tip}"
        if ad in zorunlu:
            etiket += ", zorunlu"
        parcalar.append(etiket + ")")
    if len(props) > limit:
        parcalar.append("…")
    return ", ".join(parcalar)


def sema_ihlali(spec: ToolSpec, args: dict[str, Any]) -> str | None:
    """Çağrı şemaya uyuyor mu? Uyuyorsa None, uymuyorsa öğretici mesaj.

    Yalnızca modelin gerçekten düzeltebileceği üç ihlale bakılıyor: eksik
    zorunlu alan, yanlış tip, enum dışı değer. Fazladan alan hata değil —
    bir çağrıyı fazladan alan yüzünden reddetmek, çalışan aracı bozardı.
    """
    schema = spec.input_schema or {}
    props = schema.get("properties")
    if not isinstance(props, dict):
        return None
    ozet = _sema_ozeti(schema)
    kuyruk = f" Şema: {ozet}." if ozet else ""
    verilen = ", ".join(args) or "hiçbiri"

    eksik = [ad for ad in (schema.get("required") or []) if ad not in args]
    if eksik:
        alanlar = ", ".join(f"`{ad}`" for ad in eksik)
        cogul = "alanları zorunlu" if len(eksik) > 1 else "alanı zorunlu"
        return (
            f"'{spec.name}' çağrın eksik: {alanlar} {cogul}. "
            f"Verdiğin alanlar: {verilen}.{kuyruk} "
            "Aracı bu alanları ekleyerek yeniden çağır."
        )

    for ad, deger in args.items():
        tanim = props.get(ad)
        if not isinstance(tanim, dict):
            continue
        if (secenekler := tanim.get("enum")) and deger not in secenekler:
            gecerli = ", ".join(str(s) for s in secenekler)
            return (
                f"'{spec.name}' çağrısında `{ad}` için geçerli değerler: "
                f"{gecerli}. Sen {deger!r} verdin. Birini seçip yeniden çağır."
            )
        tip = tanim.get("type")
        if isinstance(tip, str) and not _tip_uyar(deger, tip):
            return (
                f"'{spec.name}' çağrısında `{ad}` alanı {tip} olmalı; sen "
                f"{type(deger).__name__} verdin.{kuyruk} "
                "Değeri doğru tipte verip yeniden çağır."
            )
    return None


def _first_paragraph(text: str, limit: int = 220) -> str:
    """Açıklamanın özü: ilk boş satıra kadarı.

    Aracın ne yaptığı ilk paragrafta yazıyor; gerisi ne zaman kullanılacağı
    ve örnekler. Yer darken ilki kalmalı.
    """
    head = (text or "").strip().split("\n\n", 1)[0]
    head = " ".join(head.split())
    return head if len(head) <= limit else head[:limit].rsplit(" ", 1)[0] + "…"
