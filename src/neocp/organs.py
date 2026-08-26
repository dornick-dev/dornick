"""Ajanın bedeni: duyuları ve kendine taktığı modüller.

Sahnedeki ağ ajanın **bildiklerini** gösteriyor. Bu dosya ajanın
**yapabildiklerini** gösteriyor: mikrofon, kameralar, hoparlör ve kendi
yazdığı modüller (harita, PLC, USB — ne yazdıysa).

Neden ayrı bir katman: bir hatıra ile bir kamera aynı şey değil. Hatıra
çağrılır, kamera açılır. İkisini aynı düğüm türü yapmak, "şu an neyi
kullanıyor" sorusunu cevapsız bırakıyordu.

Burada hiçbir şey uydurulmuyor. Listede görünen her organın karşılığı
gerçekten var: mikrofon paketi kuruluysa mikrofon var, kamera ayarlanmışsa
kamera var, atölyede bir yetenek dosyası varsa modül var. Olmayan bir
şeyi soluk da olsa çizmek, ekranda çalışıyormuş gibi duran bir yalan olur.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Organ türleri. Sahnede her tür kendi rengini alıyor.
SENSE = "sense"      # duyu: mikrofon, kamera
SPEECH = "speech"    # hoparlör
MODULE = "module"    # ajanın kendine yazdığı yetenek
DEVICE = "device"    # kayıtlı cihaz: PLC, uzak kamera, seri port, MCP


@dataclass(slots=True)
class Organ:
    id: str
    name: str
    kind: str
    # Ne olduğu — üzerine gelince okunan satır.
    detail: str
    # O anki hali: "dinliyor", "kapalı", "açık". Kısa olmalı, etiketin
    # altına sığıyor.
    state: str
    # Gerçekten çalışıyor mu. Soluk/parlak ayrımı bu.
    live: bool = False
    # Bu organı kullanan araç adları. Araç çağrıldığında sahne hangi
    # organın canlanacağını bundan biliyor.
    tools: list[str] = field(default_factory=list)


# Kamera yoklaması aygıtı gerçekten açıyor ve ölçüldü: 518 ms. Ayar
# sayfası her açılışta bunu çağıramaz, o yüzden sonuç bir süre saklanıyor.
# Mikrofon listesi ise ölçülemeyecek kadar ucuz (<0,1 ms), orada saklama yok.
# 60 sn idi; arayüz organları 30 sn'de bir yokluyor ve kabaca her ikinci
# istek yarım saniyeyi HTTP iş parçacığında yakıyordu. Kamera takılıp
# çıkarılan bir şey değil — 5 dakika saklamak güvenli.
_CAMERA_TTL = 300.0
_camera_seen: tuple[float, bool] | None = None


def has_microphone() -> bool:
    """Makinede giriş yapan bir ses aygıtı var mı.

    Olmayan bir mikrofonu ayarda açılabilir göstermek, kullanıcıyı
    çalışmayan bir düğmeye tıklatmak demek — ve neden çalışmadığı hiçbir
    yerde yazmıyor.
    """
    try:
        import sounddevice
    except Exception:
        return False
    try:
        return any(d["max_input_channels"] > 0 for d in sounddevice.query_devices())
    except Exception:
        return False


def has_camera(lens: Any = None) -> bool:
    """Makinede bir kamera var mı.

    Açık bir tampon varsa soru zaten cevaplı: kamera var ve çalışıyor.
    Yoksa aygıt kısa süre açılıp kapatılıyor ve sonuç saklanıyor.
    """
    global _camera_seen
    import time

    if lens is not None and getattr(lens, "live", False):
        return True

    now = time.monotonic()
    if _camera_seen and now - _camera_seen[0] < _CAMERA_TTL:
        return _camera_seen[1]

    found = False
    try:
        import cv2

        capture = cv2.VideoCapture(0, getattr(cv2, "CAP_DSHOW", 0))
        found = bool(capture.isOpened())
        capture.release()
    except Exception:
        found = False

    _camera_seen = (now, found)
    return found


def _mic(config: Any, ear: Any) -> Organ:
    from . import ear as hearing

    # Kulak nesnesi VARSA paket/aygıt yoklamasına bakılmıyor: bir akış
    # açılmış ya da açılmaya çalışılmış demektir ve onun gerçek hali
    # (arıza, sağır, dinliyor) yoklamadan daha doğru. Yoklama araya girince
    # gerçek bir arıza "yok" diye raporlanıyordu.
    if ear is None:
        if not hearing.available():
            return Organ("mic", "Mikrofon", SENSE,
                         "ses paketi kurulu değil", "yok", False, [])
        if not has_microphone():
            return Organ("mic", "Mikrofon", SENSE,
                         "bu makinede giriş yapan bir ses aygıtı yok", "yok", False, [])
        # Donanım var ama kullanıcı ayarlardan kapatmış: sebep söylenmeli.
        # "Kapalı" tek başına arıza gibi okunuyor; bu bir tercih.
        if not bool(getattr(getattr(config, "listen", None), "enabled", False)):
            return Organ("mic", "Mikrofon", SENSE,
                         "kullanıcı ayarlardan kapatmış; o istemedikçe dinleme yok",
                         "kapalı", False, [])
        return Organ("mic", "Mikrofon", SENSE,
                     "sürekli dinleme kapalı", "kapalı", False, [])

    # Gerçek durum, iyimser durum değil. Akış açılamadıysa "dinliyor"
    # demek, kullanıcıyı olmayan bir kulağa konuşturmak.
    if failure := getattr(ear, "failure", ""):
        return Organ("mic", "Mikrofon", SENSE,
                     f"mikrofon akışı açılamadı — {failure}", "arıza", False, [])
    if not getattr(ear, "live", True):
        return Organ("mic", "Mikrofon", SENSE,
                     "kulak henüz açılmadı ya da kapandı", "kapalı", False, [])

    if getattr(ear, "snoozed", False):
        return Organ("mic", "Mikrofon", SENSE,
                     "kullanıcı istedi diye susturuldu; \"neo\" demek geri açar",
                     "susturuldu", False, [])

    word = getattr(getattr(config, "listen", None), "wake", "neo")
    return Organ(
        "mic", "Mikrofon", SENSE,
        f"sürekli açık; yalnızca \"{word}\" geçen söz ajana gidiyor",
        "sağır" if ear.deaf else "dinliyor",
        not ear.deaf,
        [],
    )


def _lens(config: Any, lens: Any) -> Organ:
    if lens is not None and getattr(lens, "snoozed", False):
        return Organ("lens", "Kamera", SENSE,
                     "kullanıcı istedi diye susturuldu; \"neo\" demek geri açar",
                     "susturuldu", False, ["look"])

    # Ayarlardan kapalıysa aygıta HİÇ dokunulmuyor. Yoklama kamerayı kısaca
    # gerçekten açıyor (LED yanıp sönüyor) — kamerayı bilerek kapatan
    # kullanıcı için bu "kapattım ama ışığı yanıyor" demek. Kapatan için
    # kamera yok hükmünde; var mı yok mu sorusu ancak açınca sorulur.
    if lens is None and not bool(getattr(getattr(config, "camera", None), "enabled", False)):
        return Organ("lens", "Kamera", SENSE,
                     "kullanıcı ayarlardan kapatmış; o istemedikçe bakılmaz, "
                     "aygıt yoklanmaz", "kapalı", False, ["look"])

    live = lens is not None and getattr(lens, "live", False)
    if not live and not has_camera(lens):
        return Organ("lens", "Kamera", SENSE,
                     "bu makinede kamera bulunamadı", "yok", False, ["look"])

    return Organ(
        "lens", "Kamera", SENSE,
        "sürekli açık tampon; kareler kendiliğinden modele gitmiyor, "
        "`look` istediğinde alınıyor",
        "açık" if live else "kapalı",
        live,
        ["look"],
    )


def _voice(config: Any) -> Organ:
    from . import voice as speaking

    setting = getattr(config, "voice", None)
    on = bool(getattr(setting, "enabled", False)) and speaking.available()
    return Organ(
        "voice", "Ses", SPEECH,
        getattr(setting, "name", "") or "sesli konuşma",
        "açık" if on else "kapalı",
        on,
        [],
    )


def _cameras(config: Any) -> list[Organ]:
    """Dışarıdan bağlanan kameralar. Ayarlanmamışsa liste boş."""
    from . import watch as watching

    try:
        cameras = watching.load(Path(config.state_dir))
    except Exception:
        return []

    return [
        Organ(
            f"cam:{camera.name}", camera.name, SENSE,
            "izlenen kamera; hareket yerelde ölçülüyor, yalnızca bir şey "
            "değiştiğinde soru soruluyor",
            "izliyor" if getattr(camera, "enabled", True) else "duruyor",
            bool(getattr(camera, "enabled", True)),
            [],
        )
        for camera in cameras
    ]


def _modules(config: Any) -> list[Organ]:
    """Ajanın kendine yazdığı yetenekler.

    Harita çizmek, PLC adresinden değer okumak, USB'den cihaz yoklamak:
    hangisini yazdıysa burada bir organ olarak duruyor. Elle eklenen bir
    liste değil — atölyedeki dosyalardan okunuyor.
    """
    from . import skills as authored

    try:
        found, _broken = authored.discover(config.open_sandbox().root)
    except Exception:
        return []

    return [
        Organ(
            f"skill:{skill.name}", skill.name, MODULE,
            (skill.description or "").strip().splitlines()[0][:160],
            "hazır", True, [skill.name],
        )
        for skill in found
    ]


def _devices(config: Any) -> list[Organ]:
    """Kayıtlı cihazlar: PLC, uzak kamera, seri porttaki kol, MCP sunucusu.

    Kaydın kendisi bir şey yapmıyor — nereye bağlanılacağını söylüyor.
    O yüzden `live` değil: bağlı olduğu doğrulanmış değil, yalnızca
    tanımlanmış. Sahnede soluk duruyor ve onu süren yetenek çağrıldığında
    canlanıyor.
    """
    from . import devices as declared

    try:
        found, _broken = declared.load(config.open_sandbox().root)
    except Exception:
        return []

    return [
        Organ(
            f"device:{device.id}", device.name, DEVICE,
            device.summary or declared.line(device),
            declared.KIND_STATE.get(device.kind, "tanımlı"),
            False,
            # Cihazı süren yetenek çağrıldığında sahnede bu organ canlanıyor:
            # kutunun kendisi bir araç değil, ona bağlanan betik araç.
            list(device.skills),
        )
        for device in found
    ]


def _hand(config: Any) -> Organ:
    """Ekran ve el: ajanın bilgisayarın kendisini kullanabilmesi."""
    from .tools import hands as control

    if not control.available():
        return Organ("hand", "El", SENSE,
                     "ekran ve fare kontrolü bu makinede yok (Windows + Pillow gerekli)",
                     "yok", False, ["screen", "hand"])
    return Organ(
        "hand", "El", SENSE,
        "ekranı görür (`screen`), fareyi ve klavyeyi sürer (`hand`)",
        "hazır", True, ["screen", "hand"],
    )


def senses(config: Any, *, ear: Any = None, lens: Any = None) -> list[Organ]:
    """Duyular ve uzuvlar: mikrofon, kamera, ses, el.

    Sahne bütün envanteri çiziyor; sistem promptunun ihtiyacı bu dördü.
    Ayrı duruyor ki prompt cihaz ve modülleri ikinci kez saymasın —
    onların kendi bölümleri var.
    """
    return [_mic(config, ear), _lens(config, lens), _voice(config), _hand(config)]


def inventory(config: Any, *, ear: Any = None, lens: Any = None) -> list[dict[str, Any]]:
    """Ajanın o anki bedeni. Sahne bunu çiziyor."""
    organs = senses(config, ear=ear, lens=lens)
    organs += _cameras(config)
    organs += _devices(config)
    organs += _modules(config)
    return [asdict(organ) for organ in organs]
