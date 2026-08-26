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
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

INSTALL_HINT = "Sesli komut için: pip install 'neocp[listen]'"

# Boyut/doğruluk dengesi. `tiny` uyandırma sözü için yeter; dikte için
# `small` gözle görülür biçimde daha iyi.
# `large-v3` listede: 12 GB'lık bir kartta rahat çalışıyor ve Türkçe'de
# doğruluk sıçraması onda. Kartı olmayanda seçilirse işlemciye düşer ve
# yavaşlığı ayar sayfası söylüyor.
SIZES = ("tiny", "base", "small", "medium", "large-v3")

DEFAULT_WAKE = "neo"

# Uyandırma sözü kontrolünde noktalama ve büyük/küçük harf yok sayılıyor:
# tanıyıcı "Neo," ya da "neo." yazabiliyor.
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

    if not hasattr(os, "add_dll_directory"):  # Windows dışı: sistem yolu yeter
        return True

    try:
        import nvidia
    except ImportError:
        # Kart var ama kütüphaneler yok. Sistemde CUDA kurulu olabilir;
        # denemeye değer.
        return True

    # İki yol birden gerekiyor. `add_dll_directory` yalnızca arama
    # bayrağı kullanan yüklemelerde işe yarıyor; ctranslate2 düz
    # `LoadLibrary` çağırdığı için klasörün PATH'te de olması şart —
    # tek başına ilki denendiğinde DLL yine bulunamıyordu.
    found = []
    for parent in nvidia.__path__:
        for name in ("cublas", "cudnn"):
            folder = Path(parent) / name / "bin"
            if not folder.is_dir():
                continue
            found.append(str(folder))
            try:
                os.add_dll_directory(str(folder))
            except OSError:
                pass

    if found:
        path = os.environ.get("PATH", "")
        missing = [f for f in found if f not in path]
        if missing:
            os.environ["PATH"] = os.pathsep.join(missing) + os.pathsep + path
    return True


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

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> Any:
        """Modeli yükler. İlk çağrı indirme yüzünden uzun sürebilir."""
        if self._model is not None and self._loaded_size == self.config.size:
            return self._model

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - kurulum yolu
            raise RuntimeError(INSTALL_HINT) from exc

        size = self.config.size if self.config.size in SIZES else "small"
        self._model = self._open(WhisperModel, size)
        self._loaded_size = size
        return self._model

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
        faster-whisper doğrudan dizi kabul ediyor.
        """
        model = self.load()
        language = self.config.language.strip() or None
        segments, _info = model.transcribe(
            samples,
            language=language,
            vad_filter=True,
            beam_size=1,
            initial_prompt=self._bias(),
            # Sıfır sıcaklık: tanıyıcı duymadığını bağlamdan uydurmasın.
            temperature=0.0,
            # Önceki metne şartlanmak bir yanlışı sonraki sözlere
            # bulaştırıyor; her söyleyiş temiz başlasın.
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def transcribe(self, audio: Path | str) -> str:
        """Ses dosyasını yazıya çevirir."""
        model = self.load()
        language = self.config.language.strip() or None
        segments, _info = model.transcribe(
            str(audio),
            language=language,
            # Sessizliği atlamak hem hızlandırıyor hem de sessizlikten
            # uydurulmuş cümleleri ("Altyazı M.K.") engelliyor.
            vad_filter=True,
            beam_size=1,
            # Uyandırma sözü tanıyıcıya önceden söyleniyor. "neo" Türkçede
            # bir kelime değil; bias verilmeden tanıyıcı onu duyduğu en
            # yakın gerçek kelimeye çeviriyor ve "Neo, dışarısı sıcak mı"
            # cümlesi "Ne oldu dışarısı sıcak mı" diye çıkıyordu — yani söz
            # hiç duyulmuyordu.
            initial_prompt=self._bias(),
            # Dizili yolla aynı: uydurma ve hata bulaşması kapalı.
            temperature=0.0,
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()


# Söz duyulurken tanıyıcı onu bitiştirebiliyor ya da uzatabiliyor:
# "neo" → "ne o", "ne oldu", "neyo". Bitişik hale getirilmiş bir pencerenin
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

# Tek başına anlam taşımayan kısa sesler: gülme heceleri, onay mırıltısı,
# düşünme dolgusu. Liste kasten kısa ve yalnızca **bütün** söz bunlardan
# oluşuyorsa devreye giriyor — "ahah tamam devam et" normal geçiyor.
_FILLER = frozenset({
    "ha", "he", "hı", "hi", "ho", "hu",
    "ah", "eh", "ıh", "ih", "oh", "öh", "uh", "üh",
    "hm", "hmm", "hmmm", "ee", "eee", "ıı", "ııı",
})


def chatter(text: str) -> bool:
    """Söz konuşma mı, yoksa gülme/mırıltı mı?

    Serbest dinlemede duyulan her şey ajana gidiyordu ve kullanıcı
    güldüğünde ajan her kahkahaya cevap yetiştiriyordu — kullanıcı ona
    bir şey söylememişken. Gülmek, "hı hı" demek, "hmm" diye düşünmek
    konuşma değil; ajana hiç gitmiyor, hiçbir yere yazılmıyor.

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
        return False
    return True


def heard_wake(text: str, wake: str = DEFAULT_WAKE) -> bool:
    """Metinde uyandırma sözü geçiyor mu?

    Birebir eşleşme yetmiyor: tanıyıcı "neo"yu Türkçede gerçek bir kelime
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
# neo?") bu işaret sözün değil cümlenin: sözle birlikte atılırsa soru
# cümlesi düz cümleye dönüyor ve sesletilirken tonlama da bozuluyor.
_ENDING = re.compile(r"[?!.…]+$")


def after_wake(text: str, wake: str = DEFAULT_WAKE) -> str:
    """Uyandırma sözü çıkarılmış cümle. "neo, borsayı aç" → "borsayı aç"

    Söz cümlenin **herhangi bir yerinde** olabiliyor. Önceki hal yalnızca
    sözden sonrasını alıyordu ve "nasılsın neo?" gibi sözün sonda geçtiği
    bir cümlede geriye hiçbir şey kalmıyordu: ekranda "duydum: nasılsın
    neo?" yazıyor, ajan hiç cevap vermiyordu.

    Sözün kendisi komutun parçası değil; modele göndermek "neo" diye bir
    şey aranmasına yol açıyor. Tanıyıcı sözü iki kelimeye bölmüş
    olabileceği için ("ne oldu") ikili pencere de atlanıyor.
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


def _without(raw: list[str], start: int, stop: int) -> str:
    """Sözü cümleden çıkarır.

    Sözden **sonra** bir şey varsa söz cümleyi açmıştır ve öncesindeki şey
    komut değil: tanıyıcı sözün önüne gürültü uyduruyor ("şey ııı neo
    raporu getir"). Sonrası boşsa öncesi komuttur ("nasılsın neo?").
    """
    after = raw[stop:]
    if after:
        # Baştaki virgül sözün ayracıydı ("neo, borsayı aç"), cümlenin değil.
        return " ".join(after).strip(" ,;:")

    before = raw[:start]
    # Söz cümleyi bitiriyorsa noktalaması cümleye geri veriliyor.
    if before and (mark := _ENDING.search(raw[stop - 1])):
        before = before[:-1] + [before[-1] + mark.group()]
    return " ".join(before).strip(" ,;:")
