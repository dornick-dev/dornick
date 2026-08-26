"""Ajan döngüsü.

Döngünün kendisi utanç verecek kadar basittir — modeli çağır, söylediğini yap,
sonucu geri ver, tekrarla. Değerin tamamı döngünün *etrafındaki* şeylerde:
bağlam yönetimi, izin kapısı, kesme güvenliği, kalıcılık.

Kesme güvenliği burada iki noktada zorlanır:
  * akış ortasında kesilirse yarım asistan mesajı atılır (yarım tool_use
    input'u bir sonraki isteği bozar),
  * araç yürütme ortasında kesilirse karşılıksız kalan her tool_use'a iptal
    sonucu enjekte edilir (eksik tool_result = 400).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Awaitable, Callable

from . import compaction, prompt
from .backends import Backend, Callbacks, TurnResult
from .config import Config
from .context import ContextPolicy, Prepared, cache_report
from .permissions import PermissionEngine
from .session import PendingToolUse, Session, cancelled_result
from .tools import ToolContext, ToolRegistry, build_registry, execute
from .tools.base import ToolSpec

# Tek kullanıcı isteği için azami model turu. Kaçak döngü emniyeti.
MAX_TURNS = 60

# Tavana carpan bir yanit kac kez surdurulsun. Sinirsiz birakmak, uzun
# uzun yazip hicbir zaman bitirmeyen bir modelde donguye doner.
MAX_CONTINUATIONS = 4

# Alt ajan yuvalanma sınırı. 1 demek: ana ajan yardımcı çıkarabilir,
# yardımcı çıkaramaz. Sınırsız bırakmak tek bir isteği ağaç gibi açar ve
# ne kadar iş yapıldığını kimse bilemez.
MAX_DEPTH = 1

# Her kullanici mesajindan once zihinden onune konacak hatira sayisi.
# Fazlası bağlam israfı: ilgisiz hatira modeli konudan uzaklastiriyor.
RECALL_PRIME_LIMIT = 5

# Dar pencerede aynı sayı bağlamın önemli bir kısmını yiyor.
LEAN_PRIME_LIMIT = 2

# Anlık encode için asgari uzunluk. "evet", "tamam", "ok" gibi turlar bir
# konuya atıf taşımıyor; belleğe yazmak yalnızca gürültü. Eşik + _worth_recalling
# birlikte selamı ve tek kelimelik onayları eliyor.
ENCODE_MIN_CHARS = 25

# Kendiliğinden hatırlananlar için asgari güç. Kalibre birleşimden sonra
# skor SIRA değil BÜYÜKLÜK: küçük bir hafızada tek gerçek eşleşme ~0.24
# alabiliyor (bm25 gücü korpusla büyüyor), kalabalık hafızada ~0.9'a
# doyuyor. Eski 0.3 tabanı eski sıra-ölçeğine göreydi ve genç hafızada
# prime'ı sessizce kapatıyordu. Alaka süzgeci artık eşik değil: doğrudan
# eşleşme şartı + harf zemini (_grounded) taşıyor; taban yalnızca gürültü
# tabanını kesiyor.
RECALL_PRIME_FLOOR = 0.12

# Önyükleme sorgusundan atılan sayı biçimleri: IP adresi, port, register
# adresi, uzun ölçüm değerleri.
#
# Sayılar imza katmanında birbirine benziyor ve alakasız kayıtları
# çekiyorlar. Ölçüldü: "5.11.239.227 ... 5004 portunda ... 404195
# adresinde depo seviye" sorgusu üç BTC fiyat kaydını getiriyordu (BTC
# 3.715.633 TL). Sayılar çıkarılınca üçü de listeden tümden düşüyor.
#
# Yalnızca **kendiliğinden** önyüklemede uygulanıyor. Modelin kendi
# `mind_recall` çağrısında sayı gerçekten aranan şey olabiliyor
# ("404195 hangi register?") ve orada dokunulmuyor.
_NUMERIC = re.compile(r"\b[\d][\d.,:/-]*\b")

# Selam ve hâl hatır. Bunlar bir konuya atıf değil; zihni açmaya değmez.
# Liste kısa tutuluyor: uzun bir yasak listesi bakımı zor ve asıl işi
# uzunluk ölçütü yapıyor.
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

# Surdurme durtusu. Kullanici kanalindan gidiyor cunku kesilen turdan
# sonra sondaki mesaj asistanin kendisi ve system notu bir user mesajini
# takip etmek zorunda. Arayuzde gizleniyor: kullanicinin yazmadigi bir
# mesaj sohbette kullanici mesaji gibi gorunmemeli.
CONTINUE_NOTE = (
    "Önceki yanıtın uzunluk sınırında kesildi. Kaldığın yerden devam et. "
    "Yazdıklarını baştan tekrarlama, girişi yeniden yapma, kod bloğunu "
    "yeniden açma; tam olarak kestiğin karakterden sonrasını yaz."
)

# Sürdürme hakkı bittiğinde verilen son tur.
#
# Önceki hal burada duruyor ve kullanıcıya "isteği daha küçük parçalara
# bölmek gerekebilir" diyordu. Ama ajan iş yapmıştı: araçları çağırmış,
# değerleri okumuş, yalnızca bitirememişti. Kullanıcının eline hiçbir şey
# geçmiyordu — hem yapılan iş hem de sorusu kayboluyordu.
#
# Bu tur araçsız veriliyor: tekrar araç çağırmasına izin vermek, kilitlenen
# döngünün bir turunu daha çalıştırmak demek.
CLOSING_NOTE = (
    "Sürdürme hakkın bitti. Şimdi elindekiyle bitir: yeni araç çağırma, "
    "yeni plan yapma, baştan anlatma. Birkaç cümlede şunu yaz — ne buldun, "
    "hangi değeri okudun, hangi soru cevapsız kaldı. Emin olmadığın bir şeyi "
    "kesin gibi yazma; eksikse eksik olduğunu söyle."
)

# Kamera karesi metinsiz gonderildiginde eklenen yonerge. Bakmasi gerekeni
# saymak, tek cumlelik gecistirmeyi engelliyor.
LOOK_NOTE = (
    "Kameradan bir kare. Gerçekten bak ve gördüğünü anlat: ortam, kişi, "
    "elinde ya da önünde ne var, yüz ifadesi nasıl duruyor, genel hâli ne "
    "anlatıyor. Bunlar görünenden çıkarım — kesin bilgi gibi yazma, "
    "\"öyle duruyor\" diye yaz. Göremediğin bir şeyi uydurma; kare bulanıksa "
    "ya da karanlıksa onu söyle."
)

# Ajan kendisi baktığında (kamera karesi ya da ekran görüntüsü) görüntünün
# yanına konan not. "Kameranın gördüğü" diye yazmıyor: aynı yoldan artık
# `screen` görüntüsü de geliyor ve yanlış adlandırmak modeli şaşırtıyordu.
SEEN_NOTE = (
    "Yukarıdaki görüntü senin kendi bakışın — kameradan bir kare ya da "
    "ekran görüntüsü. Kullanıcı göndermedi, sen baktın. Ne gördüğünü "
    "söyle ve işine o gördüğünle devam et; göremediğin bir şeyi uydurma."
)

# Yalnizca akil yurutup duran tura verilen durtu.
ACT_NOTE = (
    "Planını yazdın ama uygulamadın. Şimdi yap: gereken aracı çağır ya da "
    "cevabı doğrudan kullanıcıya yaz. Planı tekrar anlatma."
)


@dataclass(slots=True)
class AgentIO:
    """Harness ile arayüz arasındaki tek temas yüzeyi."""

    on_text: Callable[[str], None] = lambda _: None
    on_thinking: Callable[[str], None] = lambda _: None
    on_tool_start: Callable[[str, dict[str, Any]], None] = lambda *_: None
    on_tool_end: Callable[[str, bool, int], None] = lambda *_: None
    on_notice: Callable[[str], None] = lambda _: None
    on_usage: Callable[[dict[str, int]], None] = lambda _: None
    # Alt ajan (orkestra) kanalları: bir alt ajan doğduğunda, bir araç
    # çağırdığında ve bittiğinde. Arayüz bunları canlı kanal olarak çiziyor;
    # ana sohbete karışmadan "kimin ne yaptığı" görünür oluyor. Varsayılan
    # boş: alt ajan kullanmayan çağıranlar (testler, salt-metin) etkilenmiyor.
    on_child_start: Callable[[str, str, str], None] = lambda *_: None   # title, model, id
    on_child_tool: Callable[[str, str, str], None] = lambda *_: None    # title, tool, phase
    on_child_end: Callable[[str, bool, int, int], None] = lambda *_: None  # title, ok, turns, tools
    approve: Callable[[ToolSpec, dict[str, Any]], Awaitable[bool]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.approve is None:
            async def deny_all(spec: ToolSpec, args: dict[str, Any]) -> bool:
                return False

            self.approve = deny_all


@dataclass(slots=True)
class TurnStats:
    turns: int = 0
    tool_calls: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    interrupted: bool = False
    stop_reason: str | None = None
    # Tavana carpip surdurulen tur sayisi.
    continuations: int = 0
    # Kapanis turu verildi mi. Bir kez: yoksa kilitlenen dongu kapanis
    # turunda da kilitlenir ve ayni yere geri gelinir.
    closing: bool = False


def _without_numbers(text: str) -> str:
    """Önyükleme sorgusundan sayıları atar.

    Bir cihaz eklemek isteyen mesaj IP, port ve register adresi taşıyor ve
    bunlar zihindeki her sayılı kaydı çekiyor. Kullanıcının gördüğü şey
    "modbus cihazı ekle" derken BTC fiyat ölçümlerinin taranmasıydı.
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
        # 0 ana ajan, 1 alt ajan. Derinlik `task` aracının varlığını da
        # belirliyor.
        self.depth = depth
        # Zamanlanmış görev defteri; `schedule` aracı buradan okuyor.
        self.schedule = schedule
        # Yerel kameranın tamponu; `look` aracı buradan kare alıyor.
        self.lens = lens
        # Kulak ve izleyici masaüstü tarafında sonradan bağlanıyor
        # (açılışta ajan onlardan önce kuruluyor); `senses` aracı buradan
        # erişiyor.
        self.ear: Any = None
        self.watcher: Any = None
        self.permissions = permissions or PermissionEngine.from_config(config.permissions)
        self.policy = policy or ContextPolicy(config.context)
        # Kesme bayrağı dışarıdan verilebiliyor: alt ajan ana ajanınkini
        # paylaşıyor. Paylaşmasa kullanıcı durdur dediğinde arkada
        # çalışmaya devam ederdi.
        self.cancel = cancel or asyncio.Event()
        self._owns_cancel = cancel is None
        # Ruh oturum başında bir kez yüklenir ve oturum boyunca sabit kalır.
        # Sabit olması şart: sistem promptunun parçası, ortasında değişirse
        # o noktadan sonraki tüm önbellek düşer. Oturum içinde kaydedilen
        # yeni hatıralar bir sonraki açılışta ruha girer.
        self.soul = mind.soul(persona=prompt.read_persona(config)) if mind else None
        self._system = prompt.build(config, registry, soul=self.soul)
        self._last_goal_digest = self.mind.goal_digest() if mind else ""
        # Son turun kullanim raporu. Sikistirma karari buna bakiyor;
        # istekten once token saymak ekstra bir tur maliyeti demekti.
        self._last_usage: dict[str, int] = {}
        # Dar pencereli model: sistem promptu kısalıyor, araç
        # açıklamaları tek paragrafa iniyor, hatırlama önyüklemesi
        # azalıyor. 4096 token'lık bir modelde bunlar olmadan konuşmaya
        # hiç yer kalmıyor.
        self.lean = prompt.is_lean(config)
        # Yanlış pencere ayarı bir kez söylenip bırakılıyor: her turda
        # tekrarlamak uyarıyı gürültüye çeviriyor.
        self._window_warned = False
        # Alt ajanlar için kurulan ek istemciler; model adına göre
        # saklanıyor ki aynı model üç kez istendiğinde üç bağlantı
        # havuzu açılmasın.
        self._clients: dict[str, tuple[Any, Config]] = {}
        # Anlık encode'da peş peşe aynı metni iki kez yazmayı önler.
        self._last_encoded: str = ""
        # Bu oturumda zaten öne konmuş hatıralar. Eski not geçmişte DURUYOR
        # (mesajlar her istekte baştan oynatılıyor); aynı hatırayı yeniden
        # enjekte etmek modele yeni bilgi vermez, yalnızca token yakar.
        # Sıkıştırmada sıfırlanır — notlar özete katlanınca hak geri gelir.
        #
        # Küme ruhla başlıyor: ruhun TAM GÖVDEYLE prompta koyduğu kayıtlar
        # (user/preference/lesson/voice) da "zaten bağlamda". Ölçüldü
        # (scale_bench): aynı isabetle sorgu başına ~%9 daha az token ve
        # "hava nasıl" sorusuna çay-tercihi türü sızıntıların bir kısmı
        # kendiliğinden susuyor. Yordamlar girmiyor — ruhta yalnız başlıkları
        # var, gövdeleri önyüklemede hâlâ değerli.
        self._primed: set[str] = self._soul_resident()
        # Alt ajan kapısı: aynı anda en fazla `max_agents` yardımcı koşar.
        # Sınırı aşan spawn reddedilmiyor, sıraya giriyor — model beş iş
        # dağıttığında beşi de yapılır, ama makine ezilmeden. Araç
        # sınırından (max_parallel) ayrı çünkü bir alt ajan tek araçtan
        # çok daha ağır.
        self._agent_gate = asyncio.Semaphore(
            max(1, getattr(config.context, "max_agents", 3)))

    def _soul_resident(self) -> set[str]:
        """Ruhun tam gövdesiyle prompta koyduğu kayıtların kimlikleri."""
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
        """Ayar değişince çekirdeği yeniden kurar — yeniden başlatmadan.

        Model değiştiğinde pencere boyutu da değişebiliyor (200k Claude ↔
        4096 yerel): o zaman `lean` kararı, gönderilen araç şemaları ve
        sistem promptundaki ortam/duyu/cihaz özeti hepsi değişmeli. İstemciyi
        `Bridge` zaten değiştiriyor; burada geri kalanı tazeliyoruz.

        **Ruh dokunulmadan kalıyor.** Kimlik bloğu oturum boyunca sabit
        olmalı (önbellek önek eşleşmesi ona bağlı) ve oturum ortasında
        öğrenilen kullanıcı adı, tanışma bağlamı kaybolmamalı. Yalnızca
        `core` yeniden kuruluyor; `soul` aynı nesne olarak geçiyor.

        Tur ortasında çağrılmamalı: akan bir isteğin altından şemaları
        çekmek o cevabı bozar. `Bridge` bunu tur bittiğinde uyguluyor.
        """
        self.config = config
        self.policy = ContextPolicy(config.context)
        self.lean = prompt.is_lean(config)
        self._system = prompt.build(config, self.registry, soul=self.soul)

    def interrupt(self) -> None:
        self.cancel.set()

    def _arm(self) -> None:
        """Yeni bir istek için kesmeyi sıfırlar.

        Bayrak dışarıdan geldiyse dokunulmuyor: onu sıfırlamak, paylaşan
        tarafın kesme kararını sessizce iptal etmek olurdu.
        """
        if self._owns_cancel:
            self.cancel = asyncio.Event()

    # -- ana akış ------------------------------------------------------

    async def run(self, user_input: str, image: str = "") -> TurnStats:
        """Bir kullanıcı isteğini baştan sona koşturur.

        `image` verilirse (base64 veri adresi) mesaja görüntü bloğu olarak
        ekleniyor — kameradan gelen kare bu yoldan giriyor. Model görüntü
        kabul etmiyorsa sağlayıcı katmanı bunu anlaşılır bir hataya çeviriyor.
        """
        self._arm()
        if image:
            self.session.add_user_blocks(_with_image(user_input, image))
        else:
            self.session.add_user_text(user_input)
        # Kullanıcının söylediği o an belleğe geçiyor: gece değil, şimdi.
        self._encode_turn("kullanıcı", user_input)
        self._prime_recall(user_input)
        return await self._drive()

    def _encode_turn(self, role: str, text: str) -> None:
        """Bir konuşma turunu **anlık** olarak aranabilir belleğe yazar.

        Fatih'in çekirdek şartı: "biri bir şey söylerken direk hafızada
        kalmalı" — gece değil, o an. İnsan hafızası da böyle kodlar
        (hipokampus tek seferde yazar); konsolidasyon ayrı ve yavaştır.

        Ekran-kartsız makinede hızlı olmalı ve öyle: imza saf hashing
        (torch yok), tam yazma yolu ~2 ms. Bu yüzden senkron çalışıyor,
        kullanıcı gecikme hissetmiyor. Kayıt `episode` türünde: küratörlü
        `mind_memory` olgularına karışmıyor (ruha ve kendiliğinden
        önyüklemeye girmiyor) ama `mind_recall` ile bulunabiliyor.

        Gürültü kapısı: çok kısa turlar ("evet", "tamam") ve selam yazılmaz;
        aynı metin peş peşe iki kez gelmişse atlanır. Bir yazma hatası
        konuşmayı ASLA düşürmemeli — bellek en fazla bir turu kaçırır.
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
        except Exception as exc:  # bellek yazımı konuşmayı düşürmemeli
            self.session.log.note("encode_turn_failed", error=str(exc))

    def _prime_recall(self, user_input: str) -> None:
        """Kullanicinin mesajini zihinde arar ve bulduklarini onune koyar.

        Arac olarak birakmak yetmiyordu: model hatirlamasi gerektigini once
        fark etmek zorunda kaliyor, cogu zaman fark etmiyor ve zaten bildigi
        bir seyi bilmiyormus gibi cevapliyordu. Burada tersi yapiliyor —
        hatirlama sorulmadan calisiyor, model masaya oturdugunda ilgili
        hatiralar zaten onunde.

        Bunu yapmayi mumkun kilan sey hatirlamanin ucuz olmasi: ters indeks
        ve imza taramasi birkac milisaniye suruyor, ek model turu yok. Bir
        arac cagrisi olsaydi her mesaj icin bir gidis-donus daha demekti.
        """
        if self.mind is None or not self._worth_recalling(user_input):
            return
        try:
            # Taban yazıcı: sorgu aramadan önce yerel küçük modelle eşanlamlı
            # terimlere açılır (eşanlam sınıfı 0.50→1.00, isabet 0.87→0.93 —
            # scale_bench). Model yoksa zenginlestir sorguyu aynen döndürür.
            from .recall import taban
            query = taban.zenginlestir(user_input, getattr(self.config, "state_dir", None))
            limit = LEAN_PRIME_LIMIT if self.lean else RECALL_PRIME_LIMIT
            hits = select_prime(self.mind, query, limit=limit)
        except Exception as exc:  # hatirlama coktuyse konusma yine surmeli
            self.session.log.note("recall_prime_failed", error=str(exc))
            return

        # Zaten öne konmuş hatıra yeniden enjekte edilmiyor: eski not
        # geçmişte duruyor, model onu hâlâ görüyor.
        hits = [h for h in hits if h.item.id not in self._primed]
        if not hits:
            return
        self._primed.update(h.item.id for h in hits)
        self.session.add_system_note(prime_note(hits))

        # Arayuz bu gezinmeyi de canlandirabilmeli: kullanici modelin neyi
        # nereden hatirladigini adim adim izliyor. Aracla yapilan
        # hatirlamayla ayni olay yayilıyor, arayuzde ayrimi yok.
        if trace := getattr(self.mind, "last_trace", None):
            # Taranan ile kullanılan aynı şey değil. Zihin bir sorguda
            # onlarca kayda dokunuyor ve hepsini ekranda yakmak "her
            # şeyi karıştırdı" gibi duruyor — oysa önüne konan yalnızca
            # süzgeçten geçenler.
            used = {hit.item.id for hit in hits}
            self.session.log.note(
                "recall_trace",
                query=user_input,
                trace=[{**asdict(step), "used": step.node in used} for step in trace],
            )

    def _worth_recalling(self, text: str) -> bool:
        return worth_recalling(text)

    async def resume_after_interrupt(self) -> TurnStats:
        """Kesme sonrası karşılıksız kalanları kapatıp devam eder."""
        self._arm()
        self._settle_pending()
        return await self._drive()

    async def _drive(self) -> TurnStats:
        stats = TurnStats()
        ctx = ToolContext(
            config=self.config,
            session=self.session,
            cancel=self.cancel,
            # Alt ajanın alt ajanı olmuyor: None geçince `task` aracı
            # kendini kullanılamaz ilan ediyor.
            spawn=self._spawn if self.depth < MAX_DEPTH else None,
            schedule=self.schedule,
            lens=self.lens,
            ear=self.ear,
            watcher=self.watcher,
        )
        callbacks = Callbacks(
            on_text=self.io.on_text,
            on_thinking=self.io.on_thinking,
            on_tool_start=lambda name: None,
        )

        while stats.turns < MAX_TURNS:
            stats.turns += 1

            await self._relieve_pressure()
            self._sync_goals()
            prepared = self.policy.prepare(self._system, self.session.messages())
            result = await self.client.turn(
                prepared,
                # Kapanis turu araçsız: tekrar araç çağırmasına izin vermek,
                # kilitlenen döngünün bir turunu daha çalıştırmak demek.
                [] if stats.closing else self.registry.api_schemas(brief=self.lean),
                cancel=self.cancel,
                callbacks=callbacks,
            )

            if result.interrupted:
                self.session.log.note("interrupted", stage="stream", dropped=result.partial_text)
                self.io.on_notice("Kesildi. Yarım kalan yanıt atıldı.")
                stats.interrupted = True
                break

            if result.error:
                self.session.log.note("api_error", detail=result.error)
                self.io.on_notice(result.error)
                break

            report = cache_report(result.usage)
            stats.usage = report
            self._last_usage = report
            self.io.on_usage(report)

            # Boş içerikli asistan turu geçmişe yazılmaz: hem tur boşa gider
            # hem de boş content dizisi bir sonraki isteği bozabilir. Reddetme
            # (refusal) turları meşru olarak boş gelir; durum yine de aşağıda
            # işlenir.
            if blocks := result.content:
                self.session.add_assistant(blocks, usage=report)
                # Asistanın söylediği de anlık belleğe: bir ölçüm sonucu ya
                # da bir açıklama, sonra "az önce ne demiştin" ile bulunsun.
                self._encode_turn("neo", _text_of_blocks(blocks))
            else:
                self.session.log.note("empty_assistant_turn", stop_reason=result.stop_reason)

            stats.stop_reason = result.stop_reason
            if not await self._handle_stop(result, ctx, stats):
                break

        else:
            self.io.on_notice(f"{MAX_TURNS} tur sınırına ulaşıldı, döngü durduruldu.")
            self.session.log.note("turn_limit", limit=MAX_TURNS)

        return stats

    async def _handle_stop(
        self, result: TurnResult, ctx: ToolContext, stats: TurnStats
    ) -> bool:
        """Döngü devam etmeli mi? True -> devam."""
        reason = result.stop_reason

        if reason == "tool_use":
            calls = [
                PendingToolUse(id=b["id"], name=b["name"], input=dict(b.get("input") or {}))
                for b in result.tool_uses()
            ]
            stats.tool_calls += len(calls)
            blocks = await execute(
                calls,
                registry=self.registry,
                permissions=self.permissions,
                ctx=ctx,
                approve=self.io.approve,
                observe=self._observe,
            )
            # Bir araç görüntü döndürdüyse (kameraya bakmak gibi) blokta
            # taşınamıyor: OpenAI sözleşmesi role=tool içeriğinin dize
            # olmasını istiyor. Görüntü ayrılıp bir sonraki kullanıcı turuna
            # iliştiriliyor — model o turda gerçekten bakıyor.
            seen = [b.pop("_image") for b in blocks if "_image" in b]
            self.session.add_tool_results(blocks)
            if seen:
                # `internal`: kullanıcının yazmadığı bir mesaj sohbette
                # kullanıcı mesajı gibi görünmemeli. Gerçek bir koşuda
                # "Yukarıdaki kare kendi kameranın gördüğü…" notu ekrana
                # cevap gibi düştü.
                self.session.add_user_blocks(_seen_blocks(seen), internal=True)
            if self.cancel.is_set():
                stats.interrupted = True
                self.io.on_notice("Kesildi. Çalışan araçlar durduruldu.")
                return False
            return True

        if reason == "pause_turn":
            # Sunucu taraflı araç kendi yineleme sınırına çarptı. Ek kullanıcı
            # mesajı ekleme — geçmişi olduğu gibi tekrar göndermek yeterli.
            self.session.log.note("pause_turn")
            return True

        if reason == "max_tokens":
            # Model cevabini bitiremeden tavana carpti. Burada durmak
            # kullaniciya yarim cumle birakiyordu; oysa gecmis zaten yazildi,
            # bir tur daha vermek kaldigi yerden surdurmesi icin yeterli.
            #
            # Kesinti bir arac cagrisinin ortasinda olduysa yarim kalan
            # tool_use'lar karsiliksiz kalir; karsiliksiz tool_use bir sonraki
            # istegi 400 ile dusurur.
            self._settle_pending()
            return self._continue(stats, CONTINUE_NOTE, "max_tokens")

        if reason == "empty_turn":
            # Model yalnizca akil yurutup durdu: plan yapti, "simdi sunu
            # yapmaliyim" dedi ve turu bitirdi. Akil yurutmeyi cevap diye
            # sunmak kullaniciyi yarim birakiyordu; plani zaten gecmiste,
            # yapmasi gerekeni yapmasi icin bir tur daha veriliyor.
            return self._continue(stats, ACT_NOTE, "empty_turn")

        if reason == "refusal":
            detail = getattr(result.message, "stop_details", None)
            category = getattr(detail, "category", None)
            self.session.log.note("refusal", category=category)
            self.io.on_notice(f"Model bu isteği reddetti (kategori: {category or 'belirtilmemiş'}).")
            return False

        if reason == "model_context_window_exceeded":
            # Sunucu pencereyi bizden once tuketti (tahminimiz sapmis ya da
            # context_window ayari gercegin ustunde). Burada durmak konusmayi
            # bitirir; sikistirip devam etmek isi surdurur.
            self.session.log.note("context_exhausted")
            if await self._compact(reason="pencere tasti"):
                return True
            self.io.on_notice(
                "Bağlam penceresi doldu ve sıkıştırılacak tamamlanmış tur yok. "
                "Yeni bir oturum açman gerekiyor."
            )
            return False

        return False  # end_turn ve bilinmeyenler: sıra kullanıcıda

    def _continue(self, stats: TurnStats, note: str, why: str) -> bool:
        """Yarim kalan bir turu surdurur. Sinir dolduysa False.

        Iki ayri sebeple ayni sey gerekiyor (tavana carpma ve yalnizca akil
        yurutup durma), ve ikisinde de tek bir tavan sayilmali: bir turun
        surdurulme hakki toplamda sinirli.
        """
        if stats.continuations >= MAX_CONTINUATIONS:
            if stats.closing:
                # Kapanis turu da bitmedi. Burada gercekten yapilacak bir
                # sey kalmiyor.
                self.io.on_notice(
                    f"Yanıt {MAX_CONTINUATIONS} kez sürdürüldü ve kapanış turu da "
                    "bitmedi; durduruldu."
                )
                self.session.log.note(why, exhausted=True)
                return False

            # Ajan is yapti, yalnizca bitiremedi. Elindekiyle bir kapanis
            # yazmasi isteniyor: kullanicinin eline hicbir sey gecmemesi,
            # yarim bir cevaptan kotu.
            stats.closing = True
            self.io.on_notice("Yanıt uzadı; elindekiyle özetlemesi istendi.")
            self.session.add_continuation_note(CLOSING_NOTE)
            self.session.log.note(why, exhausted=True, closing=True)
            return True

        stats.continuations += 1
        self.session.add_continuation_note(note)
        self.session.log.note(why, continuation=stats.continuations)
        return True

    # -- alt ajanlar ---------------------------------------------------

    def _child_registry(self) -> ToolRegistry:
        """Alt ajanın araç defteri: yerleşikler (task hariç) + dinamikler.

        Taze defter `build_registry(subagents=False)` yalnızca yerleşikleri
        taşıyor. Yetenekler ve MCP araçları açılıştan SONRA yalnızca ana
        deftere ekleniyordu — alt ajan bir cihaz için yazılmış yeteneği ya
        da bağlanmış bir MCP sunucusunu göremiyordu. Yerleşiklerin `source`u
        None; yetenek/MCP'nin dolu ("yetenek", "mcp:<ad>"). Dolu olanları
        ana defterden kopyalıyoruz — o an ne varsa alt ajana da o iner.
        """
        registry = build_registry(self.mind, subagents=False)
        for spec in self.registry.all():
            if spec.source and spec.name not in registry:
                registry.register(spec)
        return registry

    async def _spawn(self, title: str, instruction: str, model: str = "") -> str:
        """Alt ajanı kendi oturumunda koşturur ve yalnızca son sözünü döndürür.

        Ayrı oturum asıl mesele: alt ajanın otuz araç çağrısı kendi
        günlüğüne yazılıyor, ana konuşmanın penceresine değil. Geriye kalan
        tek şey cevabın kendisi.

        İzin motoru ve atölye sınırı paylaşılıyor — "ben alt ajanım" diyerek
        atlanabilen bir kapı, kapı değildir.
        """
        from .session import Session

        # Alt ajan başka bir modelle koşabiliyor: tarama işi küçük ve hızlı
        # bir modele, görüntü gerektiren iş görüntü okuyan bir modele
        # gidebilsin. Aynı model isteniyorsa istemci paylaşılıyor — ikinci
        # bir istemci ikinci bir bağlantı havuzu demek.
        client, config = self.client, self.config
        if model and model != self.config.model.name:
            client, config = self._client_for(model)

        child = Session.create(self.config.sessions_dir)
        child.log.note("subagent_start", title=title, parent=self.session.id)
        self.session.log.note("subagent_start", title=title, session=child.id)
        # Orkestra kanalı doğdu: arayüz canlı göstersin.
        self.io.on_child_start(title, model or self.config.model.name, child.id)

        agent = Agent(
            config=config,
            session=child,
            # Alt ajanın kendi defteri: `task` aracı olmadan.
            registry=self._child_registry(),
            client=client,
            io=self._child_io(title),
            permissions=self.permissions,
            policy=self.policy,
            mind=self.mind,
            depth=self.depth + 1,
            schedule=self.schedule,
            # Kesme yukarıdan aşağı geçmeli: kullanıcı durdur dediğinde alt
            # ajan da durmalı, yoksa arkada çalışmaya devam ediyor.
            cancel=self.cancel,
        )

        try:
            # Ajan kapısı: makinenin taşıyabileceği kadarı aynı anda koşar,
            # gerisi sırada bekler (ayarlardan: context.max_agents).
            async with self._agent_gate:
                stats = await agent.run(instruction)
        except Exception as exc:  # alt ajanın çökmesi ana turu düşürmemeli
            self.session.log.note("subagent_failed", title=title, error=str(exc))
            self.io.on_child_end(title, False, 0, 0)
            return f"Alt ajan hata verdi: {type(exc).__name__}: {exc}"
        finally:
            child.close()

        answer = _last_text(child)
        self.session.log.note(
            "subagent_end", title=title, turns=stats.turns, tools=stats.tool_calls
        )
        self.io.on_child_end(title, True, stats.turns, stats.tool_calls)
        return answer

    def _client_for(self, model: str) -> tuple[Any, Config]:
        """Başka bir model için istemci kurar.

        Sağlayıcı ve adres aynı kalıyor, yalnızca model adı değişiyor: aynı
        LM Studio üzerindeki başka bir model ya da aynı API'deki başka bir
        model. Farklı bir sağlayıcı istemek ayarların işi, alt ajanın değil.

        Kurulan istemci saklanıyor: aynı modeli üç alt ajan isterse üç
        bağlantı havuzu açmanın anlamı yok.
        """
        from dataclasses import replace as _replace

        from .backends import build_client

        if model in self._clients:
            return self._clients[model]

        config = _replace(self.config, model=_replace(self.config.model, name=model))
        pair = (build_client(config.model), config)
        self._clients[model] = pair
        return pair

    def _child_io(self, title: str) -> AgentIO:
        """Alt ajanın arayüz bağlantısı.

        Metni akıtmıyor: alt ajanın ara cümleleri ana sohbete karışsa
        kullanıcı kimin konuştuğunu ayırt edemezdi. Araç olayları geçiyor —
        ne yaptığı izlenebilmeli.
        """
        return AgentIO(
            # Araç olayları alt ajanın kanalına yazılıyor (ana sohbete değil):
            # "kim ne yapıyor" orkestra panelinde görünür olsun.
            on_tool_start=lambda name, args: self.io.on_child_tool(title, name, "start"),
            on_tool_end=lambda name, ok, ms: self.io.on_child_tool(title, name, "ok" if ok else "fail"),
            on_notice=lambda text: self.io.on_notice(f"[{title}] {text}"),
            approve=self.io.approve,
        )

    # -- bağlam basıncı ------------------------------------------------

    async def _relieve_pressure(self) -> None:
        """Pencere dolmaya yaklaştıysa sıkıştırır.

        Tavana çarpmadan önce yapılıyor: özet isteğinin kendisi de aynı
        pencereye sığmak zorunda.
        """
        if not self._last_usage:
            return
        pressure = compaction.measure(self._last_usage, self.config.model.context_window)
        self._warn_if_window_is_wrong(pressure)
        if pressure.full:
            await self._compact(reason=f"pencere %{pressure.percent} dolu")

    def _warn_if_window_is_wrong(self, pressure: compaction.Pressure) -> None:
        """Ayardaki pencere gerçeğin üstündeyse söyler.

        Belirtisi sinsi: sıkıştırma hiç tetiklenmiyor, istem modelin gerçek
        sınırını aşıyor ve sunucu istemin **başını** sessizce atıyor. Model o
        noktada kim olduğunu ve ne istendiğini unutmuş oluyor — dışarıdan
        "sapıtıyor" gibi görünüyor, oysa ayar yanlış.

        İstem penceresini aştığı halde cevap gelmeye devam ediyorsa kanıt
        kesin: sunucu kırpıyor demektir.
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

    async def _compact(self, *, reason: str) -> bool:
        """Pencereyi özetleyip daraltır. Sıkıştırılamadıysa False."""
        plan = self.session.compaction_plan()
        if plan is None:
            return False

        from_seq, text = plan
        self.io.on_notice(f"Bağlam sıkıştırılıyor ({reason}) — konuşma kesilmeyecek.")

        summary = await self._summarize(text)
        if not summary:
            self.session.log.note("compact_failed", reason=reason)
            return False

        self.session.compact(summary, from_seq)
        self._last_usage = {}
        # Eski prime notları özete katlandı; artık bağlamda durmuyorlar.
        # Tekrar hakkı geri gelmeli, yoksa özetin kaybettiği bir hatıra
        # oturum boyunca bir daha öne konamaz. Ruh tohumları kalıyor —
        # ruh sistem promptunda, sıkıştırma ona dokunmuyor.
        self._primed = self._soul_resident()
        self.session.log.note("compacted", from_seq=from_seq, chars=len(summary))

        # Özet yalnızca bağlama değil zihne de yazılıyor. Aksi halde
        # sıkıştırma kontrollü bir unutma olurdu: oturum kapandığında özet
        # de giderdi. Zihne düştüğü için aylar sonra çağrışımla geri gelebilir.
        if self.mind is not None:
            try:
                self.mind.remember(
                    summary,
                    kind="episode",
                    title=f"oturum {self.session.id} — özet",
                    tags=("özet", "oturum"),
                )
            except Exception as exc:  # zihin yazılamazsa konuşma yine sürmeli
                self.session.log.note("compact_memory_failed", error=str(exc))

        self.io.on_notice("Bağlam özetlendi; kalıcı belleğe de yazıldı.")
        return True

    async def _summarize(self, text: str) -> str:
        """Dökümü özetlemesi için modele tek seferlik bir istek gönderir.

        Araçsız ve önbelleksiz: bu istek konuşmanın parçası değil, onun
        hakkında bir soru. Geçmişe de yazılmıyor.
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

    # -- yardımcılar ---------------------------------------------------

    def _sync_goals(self) -> None:
        """Hedef yığını değiştiyse operatör kanalından geri hatırlatır.

        Sistem promptuna yazılamaz — orası bayt bayt sabit kalmak zorunda,
        yoksa her hedef değişiminde tüm önbellek düşer. role="system" mesajı
        geçmişin sonuna eklenir: önek korunur, kanal taklit edilemez.
        """
        if self.mind is None:
            return
        digest = self.mind.goal_digest()
        if digest == self._last_goal_digest:
            return
        self._last_goal_digest = digest
        if digest:
            self.session.add_system_note(digest)

    def _settle_pending(self) -> None:
        pending = self.session.pending_tool_uses()
        if not pending:
            return
        self.session.add_tool_results([cancelled_result(p.id) for p in pending])
        self.session.log.note("settled_pending", count=len(pending))

    def _observe(self, event: str, data: dict[str, Any]) -> None:
        self.session.log.note(event, **data)
        if event == "tool_start":
            self.io.on_tool_start(data["tool"], data.get("input") or {})
        elif event == "tool_end":
            self.io.on_tool_end(data["tool"], not data["error"], data["ms"])


def worth_recalling(text: str) -> bool:
    """Bu mesaj için zihne bakmaya değer mi?

    "naber" bir soru değil, bir selam. Zihni her mesajda modelin önüne
    boşaltmak istenen şey değildi — istenen, **lazım olduğunda hızlıca
    bulabilmesi**. Gerçek bir koşuda "naber" dendiğinde model geçmiş
    oturum özetiyle, kullanıcı profiliyle ve BTC zinciriyle karşılaştı
    ve sohbet etmek yerine "ne yapmak istersin" diye sordu.

    Ölçüt basit: içerik taşıyan bir kelime var mı. Selam ve hâl hatır
    sormada yok; bir konuya atıf yapan mesajda var.
    """
    words = [w for w in _WORDS.findall((text or "").lower()) if len(w) >= 4]
    return any(word not in SMALL_TALK for word in words)


def select_prime(mind: Any, user_input: str, *, limit: int = RECALL_PRIME_LIMIT) -> list[Any]:
    """Kendiliğinden önyüklemenin seçim çekirdeği: ara, süz, kuyruğu kes.

    Modül fonksiyonu olması bilinçli — ölçek benchmark'ı
    (eval/context_memory/scale_bench.py) ürünle BİREBİR aynı yolu ölçmeli;
    kopyalanmış bir seçim mantığı sessizce ayrışır ve ölçülen şey ürün olmaz.

    Süzme kuralları (hepsi gerçek koşularda kanayan yaralardan):

    * Yalnızca **doğrudan eşleşenler** (hop 0). Çağrışımla sıçrayarak gelen
      kayıt ("borsa" sorusuna ağın öteki ucundaki SCADA) modeli konudan
      çıkarıyor; o yol modelin kendi `mind_recall` çağrısına kalıyor.
    * `episode` düğümleri girmiyor: konuşma turları uzun ve neredeyse her
      sorguyla eşleşiyor, gerçek eşleşmeyi boğuyorlar.
    * Harf zemini (`_grounded`): kayıt, sorgunun içerik kelimelerinden en az
      birinin gövdesini gerçekten içermeli — skorlar doygunlaşınca eşik tek
      başına ayıramıyor, salt imza-benzerliğiyle gelen kayıt sızıyordu.
    * Taban eşiği en güçlü kayda uygulanmıyor: genç hafızada bm25 çöküyor
      (tek belgeli korpusta kusursuz eşleşme 0.0) ve mutlak eşik prime'ı
      tümden kapatıyordu. Zemini olan en iyi kayıt her zaman gösterilir;
      eşik yalnızca kuyruğu keser.
    """
    query = _without_numbers(user_input)
    hits = mind.recall(query, limit=limit)

    trace = getattr(mind, "last_trace", None) or []
    direct = {step.node for step in trace if step.hop == 0}
    if not direct:
        return []
    stems = _query_stems(query)
    passed = [
        hit
        for hit in hits
        if hit.item.kind != "episode"
        and hit.item.id in direct
        and _grounded(hit.item, stems)
    ]
    if not passed:
        return []
    top = max(passed, key=lambda h: h.score)
    return [h for h in passed if h is top or h.score >= RECALL_PRIME_FLOOR][:limit]


def prime_note(hits: list[Any]) -> str:
    """Önüne konan hatıraların sistem notu — maliyeti bu metnin uzunluğu.

    `render()` kullanılmıyor: o `(tür) başlık [etiketler]` diye açıyor ve
    satır başındaki `[tür]` ile türü iki kez basıyordu; otomatik başlıklı
    kayıtlarda (başlık = gövdenin ilk satırı) başlık gövdeyle bir daha
    tekrarlanıyordu. Etiketler de girmiyor — model için sinyal değil dolgu.
    """
    lines = [RECALL_PRIME_HEADER]
    for hit in hits:
        item = hit.item
        body = " ".join((item.content or "").split())
        title = " ".join((item.title or "").split())
        # Başlık gövdenin başıyla aynıysa (otomatik başlık) yalnız gövde.
        if title and not body.casefold().startswith(title.casefold()[:40]):
            body = f"{title} — {body}"
        lines.append(f"- [{item.kind}] {_one_line(body)}")
    return "\n".join(lines)


def _query_stems(query: str) -> set[str]:
    """Sorgunun içerik kelimelerinin gövdeleri (ilk 5 harf, küçük harf).

    İşlev kelimeleri (ve/bir/için...) atılıyor — onlar her kayıtta var ve
    zemin saymak süzgeci deler. Kısaltmalar (btc, plc) 3 harfte de içerik
    taşıyor; o yüzden eşik 4 değil 3.

    Sorgu önce sinonim köprüsünden geçer: arama "bitcoin"i BTC kaydına
    köprüyle ulaştırıyorsa zemin kapısı da o köprüyü tanımalı — yoksa
    bulunan kayıt "kelimesi geçmiyor" diye önyüklemeden düşer.
    """
    from .recall import bridge
    from .recall.vector import STOPWORDS

    return {
        w[:5]
        for w in _WORDS.findall(bridge.expand(query or "").casefold())
        if len(w) >= 3 and w not in STOPWORDS
    }


def _grounded(item: Any, stems: set[str]) -> bool:
    """Kayıt, sorgu gövdelerinden en az birini gerçekten içeriyor mu?

    Gövde yoksa (sorgu yalnız işlev kelimesi) kapı açık kalıyor: süzgecin
    işi imza-tek kanıtlı sızıntıyı kesmek, hatırlamayı tümden kapatmak değil.
    """
    if not stems:
        return True
    text = f"{item.title} {item.content} {' '.join(item.tags)}".casefold()
    return any(stem in text for stem in stems)


def _one_line(text: str, limit: int = 220) -> str:
    """Hatirayi tek satira indirir.

    Sistem notu kisa kalmali: her mesajdan once ekleniyor ve uzunlugu
    dogrudan her turun maliyetine biniyor.
    """
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


def _text_of_blocks(blocks: list[dict[str, Any]]) -> str:
    """Asistan turundaki metin bloklarını birleştirir.

    Araç çağrıları ve düşünme blokları atlanıyor: belleğe giren, asistanın
    kullanıcıya söylediği söz — araç argümanları değil.
    """
    parts = [b.get("text", "") for b in blocks
             if isinstance(b, dict) and b.get("type") == "text"]
    return "\n".join(p for p in parts if p).strip()


def _last_text(session: "Session") -> str:
    """Oturumun son asistan turundaki metin.

    Alt ajanın "sonucu" bu: araç sonuçları kendi günlüğünde kalıyor, geriye
    yalnızca son söz dönüyor.
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
    """Metin + görüntüyü Anthropic blok biçimine çevirir.

    Tarayıcı `data:image/png;base64,...` gönderiyor; API tür ve veriyi ayrı
    alanlarda istiyor.
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
    # Görüntü önce, metin sonra: model önce baktığı şeyi, sonra soruyu görüyor.
    # Soru yoksa da bakması gerekeni söylüyoruz — yalnızca bir kare gönderip
    # "ne diyeceksin bakalım" demek modelin tek cümleyle geçiştirmesine
    # yol açıyordu.
    blocks.append({"type": "text", "text": text.strip() or LOOK_NOTE})
    return blocks


def _seen_blocks(images: list[str]) -> list[dict[str, Any]]:
    """Araçtan gelen görüntüleri kullanıcı turuna çevirir.

    Araç sonucunda taşınamadığı için buraya düşüyorlar. Yanlarına kısa bir
    not konuyor: modelin bunu kullanıcının gönderdiği bir fotoğraf değil,
    kendi bakışının sonucu olarak okuması gerekiyor.
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
