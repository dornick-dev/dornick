"""Sürekli dinleyen kulak.

Dinleme tarayıcıda duruyordu ve orada duramaz: pencere gizlendiğinde
Chromium arka plan zamanlayıcılarını dakikaya kısıyor, yani üç saniyelik
parça döngüsü ölüyor. "Program kapalıyken 'hey neo' de, uyansın" isteğinin
karşılığı tarayıcıda yok — burada var.

Kamerada olduğu gibi iş ikiye bölünüyor:

    yerelde   ses var mı? — RMS enerjisi. Mikrosaniyeler sürüyor, tanıyıcı
              hiç uyanmıyor. Sessiz bir odada saatlerce hiçbir şey olmuyor.
    tanıyıcı  konuşma bittiğinde o parça bir kez yazıya çevriliyor.

Sonra da uyandırma sözü aranıyor. Söz yoksa metin atılıyor — kimse dinlemiş
olmuyor, hiçbir yere yazılmıyor, modele gitmiyor.

Ses hiçbir zaman bilgisayardan çıkmıyor: yakalama burada, tanıma burada.

İki ayrı thread var ve bu şart. Tanıma bloklayan bir iş — ölçüm: `small`
modeli işlemcide iki saniyelik bir sözü 1,58 saniyede çözüyor. Aynı
thread'de yapılınca o süre boyunca mikrofondan hiç okuma yapılmıyor,
aygıtın tamponu doluyor ve **konuşmanın devamı düşüyor**. Kullanıcı
tarafında görünen şey tam olarak buydu: bir cümle söyleniyor, hemen
ardından söylenen ikinci cümle hiç duyulmuyor.

    yakalama thread'i  yalnızca okuyor ve enerji ölçüyor — mikrosaniyeler
    tanıma thread'i    kuyruktan alıp çözüyor — saniyeler

Kuyruk sınırlı. Tanıyıcı yetişemiyorsa **en eskisi düşüyor**: geç kalmış
bir cümleyi çözmek, o sırada söylenen yeni cümleyi kaçırmaya değmez.
"""

from __future__ import annotations

import queue
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

INSTALL_HINT = "Sürekli dinleme için: pip install 'neocp[listen]'"

# Tanıyıcının beklediği örnekleme hızı. Aygıt başka bir hızda çalışsa da
# sounddevice bu hıza indiriyor.
RATE = 16_000

# Blok uzunluğu. Kısa olması gerekiyor: konuşmanın başlangıcı bir bloğun
# ortasına denk gelirse ilk hece kesiliyor.
BLOCK = 1600           # 0.1 sn

# Konuşma eşiği (RMS, 0..1). Sessiz bir odanın taban gürültüsü genellikle
# 0.002 altında; normal konuşma 0.02'nin üstünde. 0.012 kısık sesi
# kaçırıyordu: kullanıcı 2–3 kez tekrarlıyor, kuyrukta aynı cümle birikiyor.
SPEECH = 0.008

# Konuşmadan sonra bu kadar sessizlik olunca cümle bitmiş sayılıyor.
# Kısası cümleyi ortadan kesiyor (nefes araları), uzunu geç tepki demek.
# 0.7 idi; toplam tepki bütçesinde (hang + tanıma ~2 sn) en ucuz kazanç
# buradaydı. Nefes arası tipik ~0.3-0.4 sn; 0.55 hâlâ payın üstünde.
HANG_S = 0.55

# Bundan kısa bir ses konuşma sayılmıyor: öksürük, kapı, klavye. Tanıyıcıyı
# bunlar için uyandırmak hem boşuna hem de sessizlikten cümle uydurtuyor.
MIN_S = 0.35

# Kendi sesini duymayı bırakması için hoparlör sustuktan sonra beklenen pay.
# Oda yankısı bir anda kesilmiyor. 0.5 idi: ajan susar susmaz verilen cevap
# (uyandırma sözü yoksa) bu pencerede tümden atılıyor ve "duymadı" gibi
# görünüyordu — yankının kuyruğu için 0.25 yetiyor.
DEAF_TAIL_S = 0.25
# Serbest dinlemede uyandırma kapısı yok: kuyruk kısa kalırsa hoparlör
# yankısı yeni bir söz sayılıp ajan kendi kendine cevap veriyor.
DEAF_TAIL_OPEN_S = 0.7
# Sustuktan sonra tanıma hâlâ hoparlör cümlesine benzerse düşür (oda yankısı).
# Pay, yakalama + Whisper gecikmesini de kapsar (~1,5 sn tanıma); 2 sn
# yetmeyince "Duydum: evet, seni gör" hoparlör cümlesi yeni istek oluyordu.
ECHO_HOLD_S = 4.0
# Aynı söz iki kez: kullanıcı "duymadı" sanıp tekrarlıyor, Whisper gecikince
# ikisi birden düşüyor. Bu pencerede benzer komut tek istek.
DUP_S = 4.5
# Enerji barge için yankı tabanı: boşken TTS'in ilk bloğu BARGE_FLOOR'u
# aşıp kendi sesini "kullanıcı araya girdi" sanıyordu.
ECHO_PRIME = 6

# Hoparlör yankısı SPEECH eşiğini de aşıyor; kullanıcı mikrofona konuşunca
# daha yüksek. Yankı tabanının üstüne çıkınca TTS hemen kesilir — "neo"
# demeden, cümleyi baştan kurmadan.
BARGE_HOLD_S = 0.22
BARGE_FLOOR = 0.028
ECHO_BLOCKS = 12

# Sağırlığın azami süresi. Önceki hal `float("inf")` idi ve "konuşmam
# bitti" haberinin tarayıcıdan gelmesine bel bağlıyordu. O haber gelmezse
# — sekme yenilenirse, ses bağlamı askıda kalıp `onended` hiç tetiklenmezse
# — kulak sonsuza kadar kapalı kalıyordu. Ekranda seviye çubuğu hâlâ
# oynuyor (o ölçüm sağırlıktan önce yapılıyor), yani dışarıdan "duyuyor
# ama umursamıyor" gibi görünüyordu.
#
# Artık her sağırlık kendiliğinden bitiyor. Cümleler kısa; hoparlör
# konuşmaya devam ediyorsa tarayıcı her cümlede yeniden haber veriyor ve
# süre tazeleniyor.
DEAF_MAX_S = 20.0

# Tek bir söyleyişin azami uzunluğu. Uzun bir monolog tanıyıcıyı bekletiyor
# ve uyandırma sözü zaten başta geçiyor.
MAX_S = 12.0

# Konuşmanın başından geriye alınan pay: eşik aşıldığında ilk hece çoktan
# geçmiş oluyor.
PRE_S = 0.4

# Konuşma penceresi. Bir kez konuşmaya başlandıktan sonra her cümlede adını
# söylemek gerekmiyor: karşındaki insana da "Ahmet" diye başlamıyorsun,
# sohbet sürerken devam ediyorsun.
#
# Uyandırma sözü sohbeti **başlatmak** için gerekli. Başladıktan sonra bu
# süre boyunca söylenen her şey ona söylenmiş sayılıyor ve her karşılıkta
# süre tazeleniyor. Süre dolduğunda söz yine gerekiyor — yoksa odadaki her
# konuşma modele gitmeye başlar.
#
# Süre kasıtlı olarak uzun: konuşmanın ortasında düşünmek, bakmak, bir şey
# yazmak için verilen aralar kırk beş saniyeyi rahatça geçiyordu ve pencere
# tam da konuşmanın ortasında kapanıyordu.
ENGAGED_S = 180.0

# Sohbetin tek uyandırmayla açık kalabileceği azami süre.
#
# Sınırsızdı ve pencere kendi kendini besliyordu: duyulan her söz ve ajanın
# her cevabı süreyi tazeliyor, kullanıcı oyunda takım arkadaşlarına
# konuşurken her "merhaba" modele gidiyor, cevap pencereyi yine açıyordu.
# Gerçek kayıtta bu döngü yarım saat sürdü. Artık son "neo"dan bu kadar
# süre sonra pencere ne olursa olsun kapanıyor; devamı için adı yine
# söylemek gerekiyor.
ENGAGED_MAX_S = 600.0

# Tanınmayı bekleyen söz sayısı. Küçük olması kasıtlı: tanıyıcı yetişemiyorsa
# biriken kuyruk ajanı dakikalarca geride bırakıyor. Sınıra gelindiğinde en
# eski söz düşüyor — geç kalmış bir cümle, o an söylenen cümleden değersiz.
BACKLOG = 3


def available() -> bool:
    try:
        import sounddevice  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass(slots=True)
class Heard:
    text: str
    wake: bool
    command: str
    at: float
    # neo konuşurken (TTS) uyandırma sözüyle araya girildi: "neo ile kes".
    # Köprü bunu görünce önce konuşmayı susturuyor, sonra komutu işliyor.
    barge: bool = False


def _words(text: str) -> list[str]:
    """Noktalama dökülmüş sözcükler. 'gör.' ile 'görüyorum' aynı kök sayılsın."""
    cleaned = re.sub(r"[^\w\s]", " ", (text or "").casefold(), flags=re.UNICODE)
    return [w for w in cleaned.split() if w]


def _kin(a: str, b: str) -> bool:
    """Aynı kök / çekim: gör–görüyorum–görürüm. Tam eşitlik şart değil."""
    if a == b:
        return True
    if len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a) or a in b or b in a):
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n >= 4 and n >= 0.5 * min(len(a), len(b))


def echo_of_self(said: str, tts: str) -> bool:
    """Duyulan, hoparlörde çalan cümlenin yankısı mı?

    Enerji eşiği yanlışlıkla TTS'i keserse tanıma metni burada düşer —
    ajan kendi sözünü yeni bir istek sanmasın. Whisper cümleyi kısaltır
    veya çeker ('evet, seni gör' / 'görürüm' ← 'görüyorum'); noktalama
    ve çekim yüzünden tam cümle eşleşmesi yetmez.
    """
    a, b = _words(said), _words(tts)
    got, src = " ".join(a), " ".join(b)
    if len(got) < 4 or len(src) < 4:
        return False
    if got in src or src in got:
        return True
    if not a:
        return False
    hits = sum(1 for w in a if any(_kin(w, t) for t in b))
    if len(a) == 1:
        return hits == 1 and len(a[0]) >= 6
    return hits >= 2 and hits / len(a) >= 0.5


class Ear:
    """Mikrofonu sürekli açık tutar, yalnızca konuşulanı yazıya çevirir.

    Kendi thread'inde dönüyor ve tanıma da orada yapılıyor: ikisi de
    bloklayan işler ve ajanın döngüsüne dokunmamaları gerekiyor.
    """

    def __init__(
        self,
        listener: Any,
        heard: Callable[[Heard], None],
        *,
        wake: str = "neo",
        level: Callable[[float], None] | None = None,
        scout: Any = None,
        open: bool = False,
    ) -> None:
        self.listener = listener
        # Serbest dinleme: uyandırma sözü hiç aranmıyor. Evde tek başına
        # çalışan biri için doğru olan bu — "hava nasıl?" derken başka
        # kime soruyor olabilir ki.
        self.open = open
        # Uyandırma taraması için küçük ve hızlı model. Ölçüm: `base` 0,47
        # saniyede sözü yakalıyor, `small` 1,43 saniyede doğru çözüyor.
        # İkisini birlikte kullanmak hem çabuk hem doğru: önce küçüğü
        # "söz geçti mi" diye bakıyor, geçtiyse büyüğü cümleyi çözüyor.
        self.scout = scout or listener
        self.heard = heard
        self.wake = wake
        self.level = level
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Yakalama ile tanıma arasındaki tek bağ. Tanıma bloklayan bir iş
        # ve yakalama thread'inde yapılamaz: o süre boyunca mikrofondan
        # okunmuyor ve konuşmanın devamı düşüyor.
        self._work: queue.Queue[Any] = queue.Queue(maxsize=BACKLOG)
        self._dropped = 0
        self._loud = 0.0
        # Kendi sesi. Hoparlörden çıkan konuşmayı mikrofon duyuyor ve
        # "biri konuşuyor" sanıyordu — sürekli açık bir mikrofonda bu
        # kendi kendine konuşan bir asistan demek.
        self._deaf_until = 0.0
        # Sohbetin açık olduğu ana kadar. Bu süre içinde uyandırma sözü
        # aranmıyor.
        self._engaged_until = 0.0
        # Son uyandırmanın anı: pencere bunun ENGAGED_MAX_S ötesine
        # tazelenemiyor.
        self._wake_at = 0.0
        # Uyandırıldığında birlikte açılacak öteki duyular (göz gibi).
        # "Ben gelince seslenirim" tek bir sesleniş demek: "neo" hepsini
        # geri açıyor, kullanıcı duyu duyu saymak zorunda kalmıyor.
        self.companions: list[Any] = []
        # Susturma. Kullanıcı "beni dinleme" dediğinde ajan `hearing`
        # aracıyla bunu açıyor. Önceki halde böyle bir kapı yoktu ve ajan
        # "kapalıyım" deyip dinlemeye devam ediyordu — yapamadığı bir şeyi
        # yaptım demek, en kötü tür yalan. Uyandırma sözü susturmayı deler:
        # kullanıcı "neo" diyerek her zaman geri çağırabilir.
        self._snooze_until = 0.0
        # Mikrofonun gerçek hali. Akış açılamadığında thread sessizce
        # ölüyordu ve organ hâlâ "dinliyor" diyordu: kullanıcı "uyan neo"
        # diyor, hiçbir şey olmuyor ve sebebi hiçbir yerde yazmıyordu.
        self.live = False
        self.failure = ""
        self._barge_open = False
        self._tts_text = ""
        self._tts_until = 0.0
        self._echo: deque[float] = deque(maxlen=ECHO_BLOCKS)
        self._last_ask = ""
        self._last_ask_at = 0.0
        # En son yakalanan sözün anı: tanıma dakikalarca sürerse eski sonuç
        # yeni sözle aynı anda düşmesin (kullanıcı "neo" deyince ikisi birden).
        self._latest_at = 0.0

    def speaking(self, on: bool, text: str = "") -> None:
        """Ajan konuşurken kulağı kapatır.

        Hoparlörden çıkan ses mikrofona geri geliyor. Yankı iptali işletim
        sistemi seviyesinde her zaman çalışmıyor ve çalışmadığında asistan
        kendi cümlesini duyup cevap vermeye kalkıyor.

        Kullanıcı hoparlörün üstünden konuşursa enerji eşiği sağırlığı
        kırar (`_trip_barge`). O sırada `speaking(False)` gelirse kuyruk
        payı (`DEAF_TAIL_S`) cümlenin devamını yine sağır bırakırdı —
        araya giren sözün geri kalanı duyulsun diye kuyruk atlanır.
        """
        now = time.monotonic()
        if on:
            already = now < self._deaf_until
            self._deaf_until = now + DEAF_MAX_S
            chunk = (text or "").strip()
            if chunk:
                if already and self._tts_text:
                    merged = (self._tts_text + " " + chunk).strip()
                    self._tts_text = merged[-280:]
                else:
                    self._tts_text = chunk
            self._tts_until = now + DEAF_MAX_S + ECHO_HOLD_S
            # Ardışık cümleler aynı konuşma: tabanı silmek TTS'in ilk
            # bloğunu yine BARGE_FLOOR'un üstüne çıkarıp kendi sesini
            # "araya girme" sanıyordu.
            if not already:
                self._barge_open = False
                self._echo.clear()
            return
        if self._barge_open:
            self._deaf_until = 0.0
            return
        tail = DEAF_TAIL_OPEN_S if self.open else DEAF_TAIL_S
        self._deaf_until = now + tail
        self._tts_until = now + ECHO_HOLD_S

    def _barge_loud(self, loud: float) -> bool:
        """Hoparlör yankısının üstünde, kullanıcı mikrofona mı konuşuyor?"""
        if len(self._echo) < ECHO_PRIME:
            return False
        ordered = sorted(self._echo)
        base = ordered[len(ordered) // 2]
        return loud >= max(BARGE_FLOOR, base * 1.8 + 0.008)

    def _echoing(self) -> bool:
        """Hoparlör cümlesi hâlâ havada / tanıma kuyruğunda mı?"""
        return bool(self._tts_text) and time.monotonic() < self._tts_until

    def _repeat_ask(self, command: str) -> bool:
        """Az önce işlenen komutun tekrarı mı — kuyrukta biriken aynı söz."""
        text = (command or "").strip()
        if not text:
            return False
        now = time.monotonic()
        prev = self._last_ask
        if prev and now - self._last_ask_at < DUP_S:
            if (echo_of_self(text, prev) or echo_of_self(prev, text)):
                return True
            a, b = " ".join(_words(text)), " ".join(_words(prev))
            if a and b and (a == b or a in b or b in a):
                return True
        self._last_ask = text
        self._last_ask_at = now
        return False

    def _trip_barge(self) -> None:
        """TTS'i hemen kes, kulağı aç — tanımayı bekleme."""
        self._barge_open = True
        self._deaf_until = 0.0
        hush = getattr(self, "on_hush", None)
        if hush is None:
            return
        try:
            hush()
        except Exception:
            pass

    @property
    def deaf(self) -> bool:
        return time.monotonic() < self._deaf_until

    @property
    def snoozed(self) -> bool:
        """Susturulmuş mu — yalnızca uyandırma sözü geçer."""
        return time.monotonic() < self._snooze_until

    def snooze(self, seconds: float = 0.0) -> None:
        """Kulağı susturur. Süresiz de olabilir; "neo" demek her zaman açar.

        Süresiz hali sonsuz bir bekleme değil: çıkışı belirsiz bir olaya
        değil, uyandırma sözüne ya da `resume` çağrısına bağlı.
        """
        self._snooze_until = (
            time.monotonic() + seconds if seconds > 0 else float("inf")
        )
        self._engaged_until = 0.0
        from . import prefs as prefs_mod
        prefs_mod.tell(getattr(self, "on_snooze", None), True)

    def unsnooze(self) -> None:
        was = self.snoozed
        self._snooze_until = 0.0
        if was:
            from . import prefs as prefs_mod
            prefs_mod.tell(getattr(self, "on_snooze", None), False)

    @property
    def engaged(self) -> bool:
        """Sohbet açık mı — bu sürede uyandırma sözü gerekmiyor."""
        if self.snoozed:
            return False
        return self.open or time.monotonic() < self._engaged_until

    def engage(self, seconds: float = ENGAGED_S) -> None:
        """Sohbeti açar ya da süresini tazeler.

        Ajan bir karşılık verdiğinde çağrılıyor: konuşma başlamış demektir
        ve devamında adının söylenmesini beklemek, her cümlede "Ahmet" diye
        başlamayı beklemek gibi.

        İki sınır var. Susturulmuşken hiç açılmıyor. Ve tazeleme son
        uyandırmanın ENGAGED_MAX_S ötesine geçemiyor: geçebilseydi duyulan
        her söz ve verilen her cevap pencereyi ileri itiyor, oda konuşması
        modele sonsuza kadar akıyordu — gerçek kayıtta yarım saat sürdü.
        """
        if self.snoozed:
            return
        wanted = time.monotonic() + max(0.0, seconds)
        if self._wake_at:
            wanted = min(wanted, self._wake_at + ENGAGED_MAX_S)
        self._engaged_until = wanted

    def disengage(self) -> None:
        self._engaged_until = 0.0

    @property
    def loudness(self) -> float:
        """Son ölçülen ses seviyesi. Arayüz bunu gösteriyor."""
        return self._loud

    @property
    def backlog(self) -> int:
        """Tanınmayı bekleyen söz sayısı. Sıfır değilse ajan geride."""
        return self._work.qsize()

    @property
    def dropped(self) -> int:
        """Tanıyıcı yetişemediği için düşürülen söz sayısı."""
        return self._dropped

    def start(self) -> bool:
        if not available():
            return False
        # Tanıma önce başlıyor: yakalama ilk sözü kuyruğa koyduğunda
        # karşısında çalışan bir işçi bulsun.
        threading.Thread(target=self._recognise, daemon=True, name="neo-ear-asr").start()
        # Isıtma: model yüklemesi (ilk kurulumda indirme + diskten açma)
        # İLK SÖZÜN sırtına binmesin — canlı şikâyet (30.08): ilk cümle
        # 10-20 sn gecikiyordu ve bunun büyük payı yüklemeydi. Arka planda,
        # açılışı bloke etmeden; çökerse ilk söz eski yoldan yükler.
        def _isit() -> None:
            try:
                self.listener.load()
                if self.scout is not self.listener:
                    self.scout.load()
            except Exception:
                pass
        threading.Thread(target=_isit, daemon=True, name="neo-ear-warm").start()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="neo-ear")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    # -- döngü ---------------------------------------------------------

    def _loop(self) -> None:
        import numpy as np
        import sounddevice as sd

        speech: list[Any] = []
        recent: list[Any] = []          # konuşmadan hemen önceki bloklar
        quiet_since = 0.0
        started = 0.0
        deaf_seg = False                # o an yakalanan segment TTS sırasında mı

        try:
            stream = sd.InputStream(
                samplerate=RATE, channels=1, dtype="float32", blocksize=BLOCK
            )
            stream.start()
        except Exception as exc:
            # Mikrofon yok ya da başka bir program tutmuş. Program çalışmaya
            # devam ediyor ama sebep artık kayıtlı: önceki hal sessizce
            # dönüyordu ve organ "dinliyor" demeye devam ediyordu.
            self.failure = f"{type(exc).__name__}: {exc}"
            self.live = False
            return

        self.live = True
        self.failure = ""

        try:
            while not self._stop.is_set():
                try:
                    block, _overflow = stream.read(BLOCK)
                except Exception:
                    self._stop.wait(0.5)
                    continue

                mono = block[:, 0]
                loud = float(np.sqrt(np.mean(mono * mono)))
                self._loud = loud
                if self.level is not None:
                    self.level(loud)

                now = time.monotonic()
                deaf = now < self._deaf_until
                # Neo konuşurken SPEECH eşiği yankıyı da yakalıyor. Kullanıcı
                # hoparlörün üstünden konuşunca enerji tabanın üstüne çıkar;
                # o anda TTS kesilir ve aynı tampon dinlemeye devam eder.
                waiting = deaf and not self._barge_open and not self.snoozed

                if waiting:
                    if not speech:
                        self._echo.append(loud)
                    if self._barge_loud(loud):
                        if not speech:
                            speech = [mono.copy()]
                            started = now
                            deaf_seg = True
                        else:
                            speech.append(mono.copy())
                        quiet_since = 0.0
                        if now - started >= BARGE_HOLD_S:
                            self._trip_barge()
                    elif speech:
                        if now - started < BARGE_HOLD_S:
                            speech, quiet_since, started, deaf_seg = (
                                [], 0.0, 0.0, False
                            )
                        else:
                            speech.append(mono.copy())
                            quiet_since = quiet_since or now
                            if now - quiet_since >= HANG_S or now - started >= MAX_S:
                                if now - started >= MIN_S:
                                    self._hand_over(
                                        np.concatenate(speech), deaf_seg
                                    )
                                speech, quiet_since, started = [], 0.0, 0.0
                    recent = []
                    continue

                if loud >= SPEECH:
                    if not speech:
                        # Eşik aşıldığında ilk hece çoktan geçmiş oluyor;
                        # hemen öncesindeki bloklar da alınıyor.
                        speech = list(recent)
                        started = now
                        deaf_seg = deaf
                    speech.append(mono.copy())
                    quiet_since = 0.0
                elif speech:
                    speech.append(mono.copy())
                    quiet_since = quiet_since or now
                    if now - quiet_since >= HANG_S or now - started >= MAX_S:
                        # Çok kısa sesler konuşma değil: öksürük, kapı,
                        # klavye. Tanıyıcıyı bunlar için uyandırmıyoruz.
                        if now - started >= MIN_S:
                            self._hand_over(np.concatenate(speech), deaf_seg)
                        speech, quiet_since = [], 0.0
                elif not deaf:
                    recent.append(mono.copy())
                    del recent[: -int(PRE_S * RATE / BLOCK) or None]
                else:
                    recent = []
        finally:
            self.live = False
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def _hand_over(self, audio: Any, deaf: bool = False) -> None:
        """Sözü tanıma thread'ine devreder. Asla beklemez.

        Yakalama thread'inde bir milisaniye bile beklemek, o sürede gelen
        sesin düşmesi demek. Kuyruk doluysa en eski söz atılıyor: geç
        kalmış bir cümleyi çözmek, o an söyleneni kaçırmaya değmez.

        `deaf`: segment neo konuşurken (TTS) yakalandı. Enerji eşiği
        kulağı açtıysa (`_barge_open`) cümlenin tamamı tutulur; yoksa
        tanıma yalnızca uyandırma sözüne bakar.

        Yankı damgası yakalama anında konur: Whisper 1–2 sn sürer, o
        sırada ECHO_HOLD bitmiş olsa da hoparlör cümlesi yeni istek olmaz.
        """
        echo = bool(deaf or self._barge_open or self._echoing())
        captured = time.monotonic()
        self._latest_at = captured
        while True:
            try:
                self._work.put_nowait((audio, deaf, echo, captured))
                return
            except queue.Full:
                try:
                    self._work.get_nowait()
                    self._dropped += 1
                except queue.Empty:
                    return

    def _recognise(self) -> None:
        """Kuyruktan alıp çözer. Bloklaması serbest: burada kimse beklemiyor."""
        while not self._stop.is_set():
            try:
                item = self._work.get(timeout=0.25)
            except queue.Empty:
                continue
            # Kuyrukta bekleyen eski sözleri at: kullanıcı tekrarladıysa
            # yalnızca sonuncusu geçerli. Aksi halde Whisper bitince
            # dakikalar önceki cümle ile "neo" aynı anda düşer.
            while True:
                try:
                    item = self._work.get_nowait()
                    self._dropped += 1
                except queue.Empty:
                    break
            audio, deaf = item[0], item[1]
            echo = item[2] if len(item) > 2 else bool(deaf)
            captured = item[3] if len(item) > 3 else time.monotonic()
            try:
                self._settle(audio, deaf, echo=echo, captured=captured)
            except Exception:
                # Tanıyıcıdaki bir hata kulağı sağır bırakmamalı.
                continue

    def _settle(self, audio: Any, deaf: bool = False, *, echo: bool = False,
                captured: float | None = None) -> None:
        """Bir söyleyiş bitti: uyandırma sözünü ara, geçtiyse cümleyi çöz.

        İki aşama, çünkü ikisi farklı işler. "Söz geçti mi" sorusu için
        küçük model yeter ve dört kat hızlı; ama komutu ona çözdürmek
        anlamsız bir cümle üretiyor. Ölçüm: `base` 0,47 sn, `small` 1,43 sn.
        """
        from . import listen as recogniser

        captured = time.monotonic() if captured is None else captured
        # Daha yeni bir söz yakalandıysa bunu tanıma — Whisper gecikince
        # dakikalar önceki cümle ile "neo" aynı anda sohbete düşüyordu.
        if captured < self._latest_at:
            self._barge_open = False
            return

        # Gözcü yalnızca işlemcide işe yarıyor. Ölçüm (gerçek Türkçe cümle,
        # bu makine): işlemcide `small` 1,58 sn, `base` 0,42 sn — iki aşama
        # toplamda 2 sn ve kazanç büyük. Ekran kartında `small` 0,18 sn,
        # `base` 0,12 sn: ikisini çalıştırmak 0,30 sn ediyor, yani gözcü
        # **yavaşlatıyor**.
        #
        # Karar burada veriliyor çünkü hangi aygıtta çalışıldığı ancak model
        # yüklendikten sonra belli oluyor ve yüklemeyi açılışta yapmak
        # pencereyi bir indirme boyunca kapalı tutuyordu.
        #
        # Gözcünün işi KAPI: söz geçti mi, echo mu, susturulmuş muyuz. Sohbet
        # zaten açıkken (open/engaged) kapı yok — her söz nasılsa büyük modele
        # gidiyor ve gözcü yalnızca 0,42 sn ek bekleme oluyordu. O durumda
        # doğrudan büyük modelle tek geçiş: cümle başı ~2,0 sn yerine ~1,6 sn.
        gate_needed = deaf or self.snoozed or not (self.open or self.engaged)
        scout = self.scout if gate_needed else self.listener
        if scout is not self.listener and getattr(self.listener, "device", "") == "cuda":
            scout = self.listener

        try:
            scan = scout.transcribe_array(audio, RATE)
        except Exception:
            return

        if not scan.strip():
            return

        vocab = str(getattr(getattr(self.listener, "config", None), "vocab", "") or "")

        # Sohbet açıkken söz aranmıyor: bir kez konuşmaya başlandıktan
        # sonra her cümlede adını söylemek gerekmiyor.
        woken = recogniser.heard_wake(scan, self.wake)
        barged = bool(self._barge_open)

        # BARGE-IN: neo konuşurken yakalanan ses. Enerji eşiği kulağı
        # açtıysa (`_barge_open`) uyandırma sözü gerekmez — kullanıcı
        # hoparlörün üstünden konuşmuştur, cümle tutulur. Aksi halde
        # yalnızca "neo" araya girebilir; yoksa yankı yok sayılır.
        if deaf and not barged:
            if not woken:
                return
            self._deaf_until = 0.0
            barged = True
        elif barged:
            self._deaf_until = 0.0

        # Susturulmuşken yalnızca uyandırma sözü geçiyor — ve geçtiği anda
        # susturma kalkıyor: "neo" demek geri çağırmaktır.
        if self.snoozed:
            if not woken:
                return
            self.unsnooze()

        if woken:
            self._wake_at = time.monotonic()
            # Sesleniş kulağı (ve companions: ağ kameraları) geri açar.
            # Dahili kamera HUD/sohbet anahtarıdır; "neo" onu yakmaz.
            for sense in self.companions:
                try:
                    sense.unsnooze()
                except Exception:
                    pass

        if not woken and not self.open and not self.engaged and not barged:
            # Söz yok ve sohbet kapalı: burada bitiyor. Büyük model hiç
            # uyanmıyor, metin hiçbir yere yazılmıyor, modele gitmiyor.
            return

        # Öksürük / mırıltı / uydurma adres — büyük modeli de uyandırma.
        if not woken and (recogniser.chatter(scan)
                          or recogniser.hallucinated(scan, vocab)):
            self._barge_open = False
            return

        # Şimdi düzgün çöz.
        try:
            said = (
                scan if scout is self.listener
                else self.listener.transcribe_array(audio, RATE)
            )
        except Exception:
            said = scan

        if not (said or "").strip():
            self._barge_open = False
            return

        # Gülme, öksürük ve tanıyıcının uydurduğu kelime konuşma değil.
        # Serbest dinlemede kullanıcı güldüğünde ajan her kahkahaya cevap
        # yetiştiriyordu — ona bir şey söylenmemişken. Sözle çağrıldıysa
        # geçiyor: "neo hahaha" bilinçli. Pencere de tazelenmiyor: gülmek
        # sohbeti açık tutmaz.
        if not woken and (recogniser.chatter(said)
                          or recogniser.hallucinated(said, vocab)):
            self._barge_open = False
            return

        # Enerji eşiği TTS'i yanlışlıkla kestiysa — ya da serbest
        # dinlemede hoparlör sustuktan sonra oda yankısı yeni söz olduysa —
        # tanıma metni hoparlördeki cümleye benzer. Kendi sözü istek değil.
        if (barged or echo or self._echoing()) and (
            echo_of_self(said, self._tts_text)
            or echo_of_self(scan, self._tts_text)
        ):
            self._barge_open = False
            return

        if woken:
            # Büyük model sözü başka türlü yazmış olabilir; ikisinde de
            # aranıyor ki komut kaybolmasın.
            command = (recogniser.after_wake(said, self.wake) or
                       recogniser.after_wake(scan, self.wake))
        else:
            # Sohbetin ortası: söylenenin tamamı komut.
            command = said.strip()

        if self._repeat_ask(command or said.strip()):
            self._barge_open = False
            return

        if captured < self._latest_at:
            self._barge_open = False
            return

        # Konuşma sürüyor: pencere tazeleniyor.
        self.engage()
        self._barge_open = False

        self.heard(Heard(text=said, wake=woken, command=command,
                         at=time.time(), barge=barged or deaf))
