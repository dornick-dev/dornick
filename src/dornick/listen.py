"""Konuşmayı yazıya çevirme.

Tarayıcının kendi `SpeechRecognition` API'si kullanılmıyor: WebView2'de
yok, olduğu yerde de sesi Google'a gönderiyor. Burada tanıma yerel —
`faster-whisper` bilgisayarda çalışıyor, ses hiçbir yere gitmiyor.

Model ilk kullanımda indiriliyor (`tiny` ~75 MB, `small` ~500 MB) ve sonra
diskte kalıyor. İlk çağrının uzun sürmesinin sebebi bu; arayüz de bunu
söylüyor.

Uyandırma sözü ayrı bir mesele. Sürekli dinleyip her sesi modele vermek hem
işlemciyi hem pili tüketiyor. Bunun yerine tarayıcı kısa parçalar gönderiyor,
burada yazıya çevriliyor ve içinde uyandırma sözü geçiyorsa oturum açılıyor.
Küçük model bu iş için yeterli: aranan şey tek kelime.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

INSTALL_HINT = "Sesli komut için: pip install 'dornick[listen]'"


def hint() -> str:
    """Kullanıcıya gösterilecek eksik-özellik mesajı.

    Geliştirici deposunda pip önerisi doğru; kurulum sihirbazından
    geçmiş birine pip önermek anlamsız — ona sihirbazı yeniden
    çalıştırması söylenir (bileşen: Dinleme).
    """
    from . import environment

    if environment.kurulu_mu():
        return ("Dinleme özelliği bu kuruluma dahil edilmemiş. Kurulum "
                "sihirbazını yeniden çalıştırıp 'Dinleme (mikrofon)' "
                "bileşenini işaretleyerek ekleyebilirsin.")
    return INSTALL_HINT

# Boyut/doğruluk dengesi. `tiny` uyandırma sözü için yeter; dikte için
# `small` gözle görülür biçimde daha iyi.
# `large-v3` listede: 12 GB'lık bir kartta rahat çalışıyor ve Türkçe'de
# doğruluk sıçraması onda. Kartı olmayanda seçilirse işlemciye düşer ve
# yavaşlığı ayar sayfası söylüyor.
SIZES = ("tiny", "base", "small", "medium", "large-v3")

DEFAULT_WAKE = "dornick"

# Uyandırma sözü kontrolünde noktalama ve büyük/küçük harf yok sayılıyor:
# tanıyıcı "Dornick," ya da "dornick." yazabiliyor.
_CLEAN = re.compile(r"[^\w\s]", re.UNICODE)


@dataclass(slots=True)
class ListenConfig:
    """Sesli komut ayarları.

    enabled: kapalı geliyor. Mikrofonu kendiliğinden açan bir program kabul
        edilemez; açmak kullanıcının kararı.
    wake: sürekli dinleme açıkken aranan söz. Boşsa uyandırma kapalı,
        yalnızca bas-konuş çalışıyor.
    size: model boyutu. Büyüğü daha doğru ama daha yavaş ve daha çok yer.
    language: "tr" gibi. Boş bırakılırsa tanıyıcı kendi tahmin ediyor —
        Türkçe için tahmine bırakmak gözle görülür biçimde kötü sonuç veriyor.
    open: serbest dinleme. Açıkken uyandırma sözü hiç gerekmiyor: duyulan
        her cümle ajana gidiyor.

        Evde tek başına çalışan biri için doğru olan bu — "hava nasıl?"
        derken başka kime soruyor olabilir ki. Ama odada televizyon varsa
        ya da başkalarıyla konuşuluyorsa duyulan her şey modele gider. O
        yüzden kapalı geliyor ve açması kullanıcının kararı.
    """

    enabled: bool = False
    wake: str = DEFAULT_WAKE
    size: str = "small"
    language: str = "tr"
    open: bool = False
    # Alan sözlüğü: kullanıcının dünyasına özgü kelimeler (cihaz adları,
    # "Modbus", "SCADA" gibi). Whisper bunları duymamış gibi yazıyordu —
    # "Modbus" "mod bus", "SCADA" "eskada" çıkıyordu. Ayarlardan elle de
    # yazılabiliyor; cihaz ve yetenek adları açılışta kendiliğinden ekleniyor.
    vocab: str = ""


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def _cuda_ready() -> bool:
    """Ekran kartında çalışmak mümkün mü.

    Windows'ta ctranslate2 CUDA kütüphanelerini DLL yolundan arıyor ve pip
    ile kurulan `nvidia-*` paketleri onları site-packages içine koyuyor —
    yani varsayılan olarak bulunamıyorlar. Klasörler burada tanıtılıyor;
    yoksa "cublas64_12.dll bulunamadı" diye ilk konuşmada patlıyor.
    """
    try:
        import ctranslate2

        if not ctranslate2.get_cuda_device_count():
            return False
    except Exception:
        return False

    from . import gpu as gpu_module

    return gpu_module.cuda_libs_on_path()


class Listener:
    """Tanıyıcının sahibi.

    Model bir kez yükleniyor ve süreç boyunca bellekte kalıyor: her çağrıda
    yeniden yüklemek bas-konuş'u kullanılamaz yapıyordu (her seferinde
    saniyeler).
    """

    def __init__(self, config: ListenConfig) -> None:
        self.config = config
        self._model: Any = None
        self._loaded_size = ""
        # Hangi aygıtta çalıştığı: ayarlar sayfası bunu gösteriyor, çünkü
        # işlemcide çalışan bir tanıyıcı "geç duyuyor" şikâyetinin sebebi.
        self.device = ""
        # Kendini ölçen boyut düşürme (canlı şikâyet, 30.08: zayıf laptopta
        # sürekli dinleme 10-20 sn geride kalıyordu). Çözüm süresi ses
        # süresini üst üste iki kez belirgin aşarsa bir küçük boyuta inilir
        # — YALNIZ bu oturum için; kullanıcının ayar dosyasına yazılmaz.
        self._force_size = ""
        self._slow_hits = 0

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> Any:
        """Modeli yükler. İlk çağrı indirme yüzünden uzun sürebilir."""
        want = self._force_size or self.config.size
        if self._model is not None and self._loaded_size == want:
            return self._model

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - kurulum yolu
            raise RuntimeError(hint()) from exc

        size = want if want in SIZES else "small"
        self._model = self._open(WhisperModel, size)
        self._loaded_size = size
        return self._model

    # Boyut zinciri: yavaş çıkan CPU'da bir kademe inilir. `tiny` bilinçli
    # yok — Türkçede kalite uçurumu; base hâlâ kullanılabilir doğrulukta.
    _DOWNSHIFT = {"large": "medium", "medium": "small", "small": "base"}

    def _hiz_karari(self, ses_sn: float, gecen_sn: float) -> str | None:
        """CPU çözümü yavaşsa inilecek boyutu döndürür; değilse None.

        Ölçüt: çözüm, sesin kendisinden belirgin uzun (ve >2,5 sn) — bir
        kere değil ÜST ÜSTE iki kere. Tek yavaş çözüm ısınma/başka yük
        olabilir; ikincisi kalıptır.
        """
        if self.device != "cpu":
            return None
        if gecen_sn <= max(2.5, 1.3 * max(ses_sn, 0.1)):
            self._slow_hits = 0
            return None
        self._slow_hits += 1
        if self._slow_hits < 2:
            return None
        self._slow_hits = 0
        return self._DOWNSHIFT.get(self._loaded_size or self.config.size)

    def _belki_dusur(self, ses_sn: float, gecen_sn: float) -> None:
        kucuk = self._hiz_karari(ses_sn, gecen_sn)
        if not kucuk:
            return
        print(f"[dornick] dinleme: işlemci yavaş ({gecen_sn:.1f} sn / "
              f"{ses_sn:.1f} sn ses) — model {self._loaded_size} → {kucuk} "
              "(bu oturum için; ayar değişmedi)", flush=True)
        self._force_size = kucuk
        self._model = None          # bir sonraki çözümde küçük boyut yüklenir

    def _open(self, WhisperModel: Any, size: str) -> Any:
        """Modeli açar; ekran kartı varsa orada.

        Ölçüm (iki saniyelik söz, bu makine): `small` işlemcide 1,58 sn,
        `base` 0,42 sn. İki aşamalı dinlemede bu ikisi toplanıyor ve her
        söz için iki saniyeye yakın bir gecikme çıkıyor — konuşma değil
        telsiz gibi. Ekran kartında aynı iş onda bir sürüyor.

        Kart yoksa ya da CUDA kütüphaneleri kurulu değilse sessizce
        işlemciye düşülüyor: yavaş çalışmak, hiç çalışmamaktan iyi.
        """
        if _cuda_ready():
            try:
                model = WhisperModel(size, device="cuda", compute_type="float16")
                # Yükleme başarılı olup ilk çözümde patlayan bir kurulum
                # (eksik cublas gibi) mümkün: burada anlaşılsın, kullanıcı
                # konuşurken değil.
                import numpy as np

                list(model.transcribe(np.zeros(16_000, dtype="float32"), beam_size=1)[0])
                self.device = "cuda"
                return model
            except Exception:
                pass

        # int8 CPU'da belirgin biçimde hızlı ve doğruluk farkı bu iş için
        # fark edilmiyor.
        self.device = "cpu"
        return WhisperModel(size, device="cpu", compute_type="int8")

    def _bias(self) -> str | None:
        """Tanıyıcıya sözlük ipucu.

        Whisper `initial_prompt`i bir önceki konuşma gibi ele alıyor ve
        oradaki kelimelere meylediyor. Uyandırma sözünü buraya koymak onu
        duyulur hale getiriyor.
        """
        wake = self.config.wake.strip()
        parts = [f"{wake}. {wake}, merhaba." if wake else ""]
        # Alan kelimeleri: tanıyıcı bunlara meylediyor ve kullanıcının
        # jargonunu ("Modbus", cihaz adları) doğru yazma olasılığı artıyor.
        # Kısa tutuluyor — Whisper istemi ~200 token'da kesiyor ve uzun
        # liste gerçek konuşmayı gölgeliyor.
        if vocab := self.config.vocab.strip():
            parts.append(vocab[:400])
        return " ".join(p for p in parts if p) or None

    def transcribe_array(self, samples: Any, rate: int = 16_000) -> str:
        """Bellekteki ses örneklerini yazıya çevirir.

        Sürekli dinleme için: her söyleyiş için geçici dosya açıp silmek
        hem gereksiz hem de saniyede birkaç kez yapılınca diski yoruyor.
        faster-whisper doğrudan dizi kabul ediyor. Çözüm süresi burada
        ölçülüyor: CPU sesin gerisinde kalıyorsa boyut kendiliğinden düşer.
        """
        import time as _time
        ses_sn = float(getattr(samples, "shape", [0])[0] or 0) / max(rate, 1)
        t0 = _time.perf_counter()
        try:
            return self._decode(samples, endpointed=True)
        finally:
            self._belki_dusur(ses_sn, _time.perf_counter() - t0)

    def transcribe(self, audio: Path | str) -> str:
        """Ses dosyasını yazıya çevirir."""
        return self._decode(str(audio))

    def _decode(self, audio: Any, *, endpointed: bool = False) -> str:
        model = self.load()
        language = self.config.language.strip() or None
        # Kulak zaten enerjiyle kesiyor; Whisper VAD'ı üstüne binince hem
        # gecikiyor hem ilk heceyi yiyor. Dosya (bas-konuş) sessizlik
        # içerebilir — orada VAD kalsın.
        kwargs: dict[str, Any] = dict(
            language=language,
            vad_filter=not endpointed,
            beam_size=1,
            initial_prompt=self._bias(),
            temperature=0.0,
            condition_on_previous_text=False,
            compression_ratio_threshold=2.2,
            no_speech_threshold=0.55,
            log_prob_threshold=-0.7,
            without_timestamps=True,
        )
        try:
            segments, _info = model.transcribe(audio, **kwargs)
        except TypeError:
            for key in ("compression_ratio_threshold", "no_speech_threshold",
                        "log_prob_threshold", "without_timestamps"):
                kwargs.pop(key, None)
            segments, _info = model.transcribe(audio, **kwargs)
        return _join_segments(segments, self.config.vocab)


# Söz duyulurken tanıyıcı onu bitiştirebiliyor ya da uzatabiliyor:
# "dornick" → "ne o", "ne oldu", "neyo". Bitişik hale getirilmiş bir pencerenin
# sözle başlaması ve en fazla bu kadar uzun olması kabul ediliyor.
#
# Ödünleşim bilinçli: "neon" da uyandırıyor. Hiç uyanmayan bir asistan,
# arada bir fazladan uyanandan kötü.
WAKE_SLACK = 3


def _words(text: str) -> list[str]:
    return _CLEAN.sub(" ", (text or "").lower()).split()


def _windows(words: list[str]) -> list[str]:
    """Tek kelimeler ve bitişik ikililer.

    "ne oldu" iki kelime olarak geliyor; birleştirilmeden sözle
    karşılaştırılamıyor.
    """
    out = list(words)
    out += [a + b for a, b in zip(words, words[1:])]
    return out


# Gülüşme hecesi: yalnızca bu harflerden oluşan bir kelime, içinde en az
# iki "h" varsa gülmedir ("ahahah", "ıhıhıh", "hahaha").
_LAUGH = re.compile(r"^[haeıiouöüj]+$")
_UNLU = set("aeıiouöüâîû")
_BARE_URL = re.compile(
    r"(?:www\.)?[a-z0-9][a-z0-9.-]*\.(com|net|org|io|dev)$",
    re.I,
)
_JUNK = frozenset({
    "altyazı m.k", "altyazı mk", "altyazı m k", "altyazı mk.",
    "thanks for watching", "thank you for watching",
    "izlediğiniz için teşekkürler", "abone ol", "subscribe",
    # Whisper Türkçe sessizlik/yankıda YouTube kapanışını basıyor.
    # Gerçek veda "hoşça kal" / "görüşürüz".
    "hoşça kalın", "hosca kalin", "hoşçakalın", "hoscakalin",
})

# Tek başına anlam taşımayan kısa sesler: gülme heceleri, onay mırıltısı,
# düşünme dolgusu. Liste kasten kısa ve yalnızca **bütün** söz bunlardan
# oluşuyorsa devreye giriyor — "ahah tamam devam et" normal geçiyor.
_FILLER = frozenset({
    "ha", "he", "hı", "hi", "ho", "hu",
    "ah", "eh", "ıh", "ih", "oh", "öh", "uh", "üh",
    "hm", "hmm", "hmmm", "ee", "eee", "ıı", "ııı",
    "öö", "ööö", "aa", "aaa", "uu", "uuu",
})


def _groan(word: str) -> bool:
    """Öksürük/inleme: aynı ünlünün uzaması (öööö, eeee)."""
    letters = [c for c in word.lower() if c.isalpha()]
    if len(letters) < 4:
        return False
    top, n = Counter(letters).most_common(1)[0]
    if n / len(letters) >= 0.7 and top in _UNLU:
        return True
    squeezed = re.sub(r"(.)\1+", r"\1", word)
    return len(word) >= 8 and len(squeezed) / len(word) <= 0.35


def chatter(text: str) -> bool:
    """Söz konuşma mı, yoksa gülme/mırıltı/öksürük mü?

    Serbest dinlemede duyulan her şey ajana gidiyordu ve kullanıcı
    güldüğünde ajan her kahkahaya cevap yetiştiriyordu — kullanıcı ona
    bir şey söylememişken. Gülmek, "hı hı" demek, "hmm" diye düşünmek,
    öksürünce çıkan "öööö" konuşma değil; ajana hiç gitmiyor.

    Ölçüt bilinçli olarak dar: içinde tek bir gerçek kelime olan söz
    ("ahah tamam devam et") olduğu gibi geçiyor.
    """
    words = [w for w in (_CLEAN.sub("", p.lower()) for p in (text or "").split()) if w]
    if not words:
        return True

    for word in words:
        if word in _FILLER:
            continue
        if _LAUGH.match(word) and word.count("h") >= 2 and len(word) >= 4:
            continue
        if _groan(word):
            continue
        return False
    return True


def hallucinated(text: str, vocab: str = "") -> bool:
    """Tanıyıcı anlamayınca uydurduğu şey mi?

    Alan sözlüğü (Modbus, SCADA) `initial_prompt`e yazılıyor; Whisper
    öksürük/gürültüde o kelimeleri — bazen `modbus.com` diye — basıyor.
    Tek başına bir sözlük kelimesi veya çıplak bir adres konuşma değil.
    """
    raw = (text or "").strip().strip(" .,;:")
    if not raw:
        return True
    flat = " ".join(raw.casefold().split())
    if flat in _JUNK:
        return True
    if _BARE_URL.fullmatch(raw.rstrip(".")):
        return True
    tokens = {
        w.strip(" ,.;").casefold()
        for w in re.split(r"[,;\n]+", vocab or "")
        if w.strip()
    }
    if not tokens:
        return False
    words = _CLEAN.sub(" ", flat).split()
    if len(words) != 1:
        return False
    word = words[0]
    host = word.split(".")[0]
    return word in tokens or host in tokens


def _keep_segment(segment: Any) -> bool:
    """Whisper'ın 'emin' olduğu çöp segmenti de düşür.

    Öksürükte compression_ratio yüksek çıkar; konuşma yokken no_speech
    yükselir. İkisi de metin süzgecinden önce ucuz bir kapı.
    """
    cr = float(getattr(segment, "compression_ratio", 0.0) or 0.0)
    if cr > 2.2:
        return False
    nsp = float(getattr(segment, "no_speech_prob", 0.0) or 0.0)
    lp = float(getattr(segment, "avg_logprob", 0.0) or 0.0)
    if nsp > 0.55 and lp < -0.5:
        return False
    return True


def _join_segments(segments: Any, vocab: str = "") -> str:
    parts: list[str] = []
    for segment in segments:
        text = str(getattr(segment, "text", "") or "").strip()
        if not text or not _keep_segment(segment):
            continue
        if chatter(text) or hallucinated(text, vocab):
            continue
        parts.append(text)
    joined = " ".join(parts).strip()
    if not joined or chatter(joined) or hallucinated(joined, vocab):
        return ""
    return joined


def heard_wake(text: str, wake: str = DEFAULT_WAKE) -> bool:
    """Metinde uyandırma sözü geçiyor mu?

    Birebir eşleşme yetmiyor: tanıyıcı "dornick"yu Türkçede gerçek bir kelime
    olan "ne oldu"ya çeviriyor. Bitiştirilmiş pencere sözle başlıyorsa ve
    çok uzamamışsa duyulmuş sayılıyor.
    """
    word = _CLEAN.sub(" ", (wake or "").lower()).strip().replace(" ", "")
    if not word:
        return False

    return any(
        window.startswith(word) and len(window) <= len(word) + WAKE_SLACK
        for window in _windows(_words(text))
    )


# Cümleyi bitiren noktalama. Uyandırma sözü sonda geçtiğinde ("nasılsın
# dornick?") bu işaret sözün değil cümlenin: sözle birlikte atılırsa soru
# cümlesi düz cümleye dönüyor ve sesletilirken tonlama da bozuluyor.
_ENDING = re.compile(r"[?!.…]+$")


def after_wake(text: str, wake: str = DEFAULT_WAKE) -> str:
    """Uyandırma sözü çıkarılmış cümle. "dornick, borsayı aç" → "borsayı aç"

    Söz cümlenin **herhangi bir yerinde** olabiliyor. Önceki hal yalnızca
    sözden sonrasını alıyordu ve "nasılsın dornick?" gibi sözün sonda geçtiği
    bir cümlede geriye hiçbir şey kalmıyordu: ekranda "duydum: nasılsın
    dornick?" yazıyor, ajan hiç cevap vermiyordu.

    Sözün kendisi komutun parçası değil; modele göndermek "dornick" diye bir
    şey aranmasına yol açıyor. Tanıyıcı sözü iki kelimeye bölmüş
    olabileceği için ("ne oldu") ikili pencere de atlanıyor.

    Söz cümlenin ortasındaysa ("nasılsın dornick? iyi misin?") her iki taraf
    da kalır — önceki hal "dornick"den sonrasını alınca "nasılsın"ı atıyordu.
    """
    word = _CLEAN.sub(" ", (wake or "").lower()).strip().replace(" ", "")
    if not word:
        return (text or "").strip()

    raw = (text or "").split()
    clean = [_CLEAN.sub("", piece.lower()) for piece in raw]

    for index, piece in enumerate(clean):
        pair = piece + (clean[index + 1] if index + 1 < len(clean) else "")
        if piece.startswith(word) and len(piece) <= len(word) + WAKE_SLACK:
            return _without(raw, index, index + 1)
        if pair.startswith(word) and len(pair) <= len(word) + WAKE_SLACK:
            return _without(raw, index, index + 2)

    return (text or "").strip()


def _pre_wake_noise(raw: list[str]) -> bool:
    """Sözden önceki parça tanıyıcı gürültüsü mü, yoksa gerçek cümle mi?

    "şey ııı dornick raporu getir" → gürültü. "nasılsın dornick? iyi misin?" → değil.
    """
    if not raw:
        return True
    if chatter(" ".join(raw)):
        return True
    words = [w for w in (_CLEAN.sub("", p.lower()) for p in raw) if w]
    real = [w for w in words if w not in _FILLER and not _groan(w)]
    if not real:
        return True
    return len(real) == 1 and len(real[0]) <= 3


def _without(raw: list[str], start: int, stop: int) -> str:
    """Sözü cümleden çıkarır.

    Sözden **sonra** bir şey varsa: öncesi gürültüyse atılır ("şey ııı dornick
    raporu getir"); gerçek cümleyse ikisi de kalır ("nasılsın dornick? iyi
    misin?"). Sonrası boşsa öncesi komuttur ("nasılsın dornick?").
    """
    after = raw[stop:]
    if after:
        # Baştaki virgül sözün ayracıydı ("dornick, borsayı aç"), cümlenin değil.
        after_text = " ".join(after).strip(" ,;:")
        before = raw[:start]
        # Söz cümlenin ORTASINDAYSA ("nasılsın dornick? iyi misin?") her iki
        # taraf da komut. Öncesi yalnızca tanıyıcı gürültüsüyse ("şey ııı
        # dornick …") eskisi gibi atılır.
        if before and not _pre_wake_noise(before):
            if mark := _ENDING.search(raw[stop - 1]):
                before = before[:-1] + [before[-1] + mark.group()]
            return (" ".join(before) + " " + after_text).strip(" ,;:")
        return after_text

    before = raw[:start]
    # Söz cümleyi bitiriyorsa noktalaması cümleye geri veriliyor.
    if before and (mark := _ENDING.search(raw[stop - 1])):
        before = before[:-1] + [before[-1] + mark.group()]
    return " ".join(before).strip(" ,;:")
