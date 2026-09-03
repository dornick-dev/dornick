"""Kendi yazdığı yetenekler.

Her yeni işi araç olarak elle eklemek ölçeklenmiyor. Harita çizmek, bir PLC
adresinden değer okumak, USB'den gelen cihazı yoklamak, ikinci kamerayı
açmak — bunların ortak yanı, hepsinin **ajanın kendisinin yazabileceği**
kadar küçük olması. Uzun ve zor olanları araç olarak biz veriyoruz; gerisini
o yazsın.

Bir yetenek, atölyedeki `yetenekler/` klasöründe duran bir Python dosyası:

    NAME = "harita"
    DESCRIPTION = "Koordinatları haritaya işler ve PNG üretir."
    SCHEMA = {"type": "object", "properties": {...}, "required": [...]}

    def run(args, ctx):
        ...
        return "harita/rota.png yazıldı"

Dosya yazıldıktan sonra `skill action=load` ile araç haline geliyor ve o
turdan itibaren şemasıyla birlikte modele gidiyor. Bir sonraki açılışta
kendiliğinden yükleniyor.

Yetkiye dair dürüst olmak gerekiyor: yetenek aynı süreçte, tam Python'la
çalışıyor. Yani `shell` aracından daha fazla yetki vermiyor — ikisi de
bilgisayarda ne isterse yapabilir. Yeni bir kapı açmıyor, var olan kapıyı
düzenli hale getiriyor: iş adlandırılmış, şemalı ve tekrar kullanılabilir
oluyor. Yazma yeri atölyenin içinde kalıyor.
"""

from __future__ import annotations

import hashlib
import json
import sys
import traceback
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Atölye içinde yeteneklerin durduğu klasör.
FOLDER = "yetenekler"

# Onaylı yetenek manifesti (.dornick içinde): {dosya_adı: sha256}. Yalnız
# BURADAKİ karma ile eşleşen dosyalar AÇILIŞTA kendiliğinden exec edilir.
# Bir yetenek dosyası tam Python'la aynı süreçte koşuyor; atölyeye
# `write_file` ile düşürülen (ör. injection) rastgele bir .py'nin her
# açılışta sessizce çalışması kabul edilemezdi (güvenlik denetimi, 01.09).
# Manifest .dornick'te ve korumalar.py onu araç yazımına kapıyor — yoksa
# aynı injection dosyayı da karmayı da yazıp korumayı aşardı.
MANIFEST = "skills_onayli.json"


def _manifest_path(state_dir: Path | str) -> Path:
    return Path(state_dir) / MANIFEST


def _oku_manifest(state_dir: Path | str) -> dict[str, str] | None:
    """Onaylı karma haritası; dosya hiç yoksa None (göç sinyali)."""
    path = _manifest_path(state_dir)
    if not path.is_file():
        return None
    try:
        veri = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in veri.items()} if isinstance(veri, dict) else {}


def _write_manifest(state_dir: Path | str, harita: dict[str, str]) -> None:
    try:
        _manifest_path(state_dir).write_text(
            json.dumps(harita, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _karma(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _onayla(state_dir: Path | str, path: Path) -> None:
    """Bir dosyayı onaylı manifeste ekler (güvenilir oluşturma/yükleme)."""
    harita = _oku_manifest(state_dir) or {}
    try:
        harita[path.name] = _karma(path)
    except OSError:
        return
    _write_manifest(state_dir, harita)

# Bir yetenek dosyasında aranan alanlar.
REQUIRED = ("NAME", "DESCRIPTION", "SCHEMA")

TEMPLATE = '''"""{title}

Bunu Dornick kendisi yazdı. Değiştirebilir, silebilirsin.
"""

NAME = "{name}"
DESCRIPTION = """{description}"""

SCHEMA = {{
    "type": "object",
    "properties": {{}},
    "required": [],
}}


def run(args, ctx):
    """Yeteneğin gövdesi.

    args: şemaya göre gelen sözlük.
    ctx:  ToolContext — `ctx.sandbox.root` atölyen, `ctx.config` ayarlar.

    Dönen değer metin olmalı: modele o metin gidiyor.
    """
    return "henüz bir şey yapmıyor"
'''


class SkillError(Exception):
    """Yetenek yüklenemedi. Mesajı modele gidiyor, öğretici olmalı."""


@dataclass(slots=True)
class Skill:
    name: str
    description: str
    schema: dict[str, Any]
    run: Any
    path: Path


def folder(sandbox_root: Path) -> Path:
    place = sandbox_root / FOLDER
    place.mkdir(parents=True, exist_ok=True)
    return place


# Tohum izleme dosyası: hangi standart yeteneklerin kopyalandığı burada.
# Klasörün boş olup olmadığına bakılamazdı — kullanıcı standart bir yeteneği
# bilerek silmiş olabilir ve her açılışta geri gelmesi silmeyi anlamsız kılar.
SEEDED = ".tohumlar"


def seed(sandbox_root: Path, state_dir: Path | str | None = None) -> list[str]:
    """Paketle gelen standart yetenekleri atölyeye kopyalar — bir kez.

    Kopyalanan dosya artık kullanıcının: düzenlenir, silinir, geri gelmez.
    Yeni bir sürüm yeni bir standart yetenek getirirse yalnızca o eklenir
    (izleme dosyasında adı yoksa kopyalanır).
    """
    source = Path(__file__).parent / "assets" / "skills"
    if not source.is_dir():
        return []

    place = folder(sandbox_root)
    marker = place / SEEDED
    already = set()
    if marker.is_file():
        already = {line.strip() for line in marker.read_text(encoding="utf-8").splitlines()}

    planted: list[str] = []
    for packed in sorted(source.glob("*.py")):
        if packed.name in already:
            continue
        target = place / packed.name
        if not target.exists():
            target.write_text(packed.read_text(encoding="utf-8"), encoding="utf-8")
            planted.append(packed.stem)
            # Paketle gelen yetenek güvenilir: onaylı manifeste kaydet ki
            # açılışta yüklenebilsin (aksi halde "onaylanmadı" derdi).
            if state_dir is not None:
                _onayla(state_dir, target)
        already.add(packed.name)

    marker.write_text("\n".join(sorted(already)) + "\n", encoding="utf-8")
    return planted


def load_file(path: Path) -> Skill:
    """Tek bir dosyayı yetenek olarak yükler.

    Modül adı dosya yoluna göre benzersizleştiriliyor: iki farklı klasörde
    aynı adlı iki dosya birbirini ezmesin.
    """
    if not path.is_file():
        raise SkillError(f"Dosya yok: {path}")

    key = f"dornick_skill_{abs(hash(str(path)))}"

    # Kaynak elle okunup derleniyor — importlib'in yükleyicisi DEĞİL.
    #
    # Yükleyici `__pycache__`e bakıyor ve önbellek (mtime, boyut) ikilisiyle
    # anahtarlı: "a + b"yi "a * b" yapan bir düzeltme aynı boyutta kalıyor
    # ve aynı mtime tikine denk gelirse eski bytecode geri geliyor. Ajan
    # tam bunu yaşadı — dosyasını düzeltti, yeniden yükledi ve "cache'li
    # hal hâlâ eski kodu kullanıyor" diyerek her seferinde kabuğa düştü.
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillError(f"{path.name} okunamadı: {exc}") from exc

    module = types.ModuleType(key)
    module.__file__ = str(path)
    # Modül sys.modules'a konuyor: içinde dataclass ya da tipleme varsa
    # kendi adını çözebilmesi gerekiyor.
    sys.modules[key] = module
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)
    except Exception as exc:
        sys.modules.pop(key, None)
        # Yığın izi modele gidiyor: hangi satırda patladığını görmeden
        # düzeltemez.
        raise SkillError(
            f"{path.name} çalıştırılamadı:\n{traceback.format_exc(limit=3)}"
        ) from exc

    missing = [field for field in REQUIRED if not hasattr(module, field)]
    if missing:
        raise SkillError(
            f"{path.name} eksik: {', '.join(missing)}. "
            "Bir yetenek dosyası NAME, DESCRIPTION, SCHEMA ve run(args, ctx) içermeli."
        )
    if not callable(getattr(module, "run", None)):
        raise SkillError(f"{path.name} içinde `run(args, ctx)` fonksiyonu yok.")

    name = str(module.NAME).strip()
    if not name.replace("_", "").isalnum():
        raise SkillError(
            f"Geçersiz ad: {name!r}. Yalnızca harf, rakam ve alt çizgi kullan."
        )

    schema = module.SCHEMA
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise SkillError(f"{path.name}: SCHEMA bir JSON Schema nesnesi olmalı.")

    return Skill(
        name=name,
        description=str(module.DESCRIPTION).strip(),
        schema=schema,
        run=module.run,
        path=path,
    )


def discover(sandbox_root: Path, state_dir: Path | str | None = None,
             *, onayla: bool = False) -> tuple[list[Skill], list[str]]:
    """Klasördeki yetenekleri yükler. (yüklenenler, hatalar)

    Bozuk bir dosya diğerlerini engellemiyor: hata listeye giriyor ve
    program çalışmaya devam ediyor. Aksi halde tek bir yazım hatası ajanı
    tüm yeteneklerinden ediyor.

    Güvenlik (state_dir verilirse): yalnız onaylı manifestteki (karma
    eşleşen) dosyalar yüklenir. Manifest hiç yoksa İLK ÇALIŞTIRMA göçü —
    mevcut dosyalar güvenilir sayılıp kaydedilir (yükseltmede kimsenin
    kurulumu bozulmaz). `onayla=True` ise (araçla açık `write`/`load`,
    izin kapısından geçmiş insan eylemi) bulunan geçerli dosyalar
    manifeste yazılır; açılışta (onayla=False) onaysız dosya yüklenmez,
    "onaylanmadı" diye raporlanır.

    state_dir=None: eski davranış — hepsi yüklenir (testler ve salt-gözlem
    çağıranları için).
    """
    found: list[Skill] = []
    broken: list[str] = []
    files = [p for p in sorted(folder(sandbox_root).glob("*.py"))
             if not p.name.startswith("_")]

    manifest: dict[str, str] | None = None
    goc = False
    if state_dir is not None:
        manifest = _oku_manifest(state_dir)
        if manifest is None:
            # İlk çalıştırma: mevcut dosyalar güvenilir. Kaydet ve yükle.
            manifest = {}
            for p in files:
                try:
                    manifest[p.name] = _karma(p)
                except OSError:
                    pass
            _write_manifest(state_dir, manifest)
            goc = True

    for path in files:
        if manifest is not None and not goc:
            try:
                simdi = _karma(path)
            except OSError:
                continue
            if not onayla and manifest.get(path.name) != simdi:
                broken.append(
                    f"{path.name}: onaylanmadı — bu dosya `skill` aracıyla "
                    "yazılmadı ya da elle değişti; güvenlik gereği açılışta "
                    "kendiliğinden yüklenmedi. Onaylamak için içeriğini "
                    "`skill action=write` ile yeniden yaz ya da `skill "
                    "action=load` de (ikisi de izin kapısından geçer)."
                )
                continue
        try:
            skill = load_file(path)
        except SkillError as exc:
            broken.append(str(exc))
            continue
        found.append(skill)
        if onayla and state_dir is not None:
            _onayla(state_dir, path)
    return found, broken


def _clean_name(name: str) -> str:
    clean = name.strip().lower().replace(" ", "_")
    if not clean.replace("_", "").isalnum():
        raise SkillError(f"Geçersiz ad: {name!r}. Harf, rakam ve alt çizgi kullan.")
    return clean


def scaffold(sandbox_root: Path, name: str, description: str) -> Path:
    """Boş bir yetenek dosyası yazar ve yolunu döndürür.

    İskeleti biz veriyoruz çünkü biçimi hatırlamak modelin işi olmamalı:
    yanlış alan adıyla yazılmış bir dosya yüklenmiyor ve sebebi ancak
    denendiğinde anlaşılıyor.
    """
    clean = _clean_name(name)
    path = folder(sandbox_root) / f"{clean}.py"
    if path.exists():
        raise SkillError(
            f"{path.name} zaten var. Değiştirmek için `skill action=write` kullan."
        )

    path.write_text(
        TEMPLATE.format(
            title=description.strip() or clean,
            name=clean,
            description=description.strip() or clean,
        ),
        encoding="utf-8",
    )
    return path


def save(sandbox_root: Path, name: str, code: str,
         state_dir: Path | str | None = None) -> Skill:
    """Tam yetenek dosyasını yazar ve doğrular.

    Biçim bozuksa dosya diskte kalır (düzeltilebilsin) ama SkillError
    yükselir — bozuk kod araç defterine girmez.

    `state_dir` verilirse dosya onaylı manifeste kaydedilir: bu, izin
    kapısından geçmiş `skill action=write` yolu — güvenilir oluşturma.
    Doğrulama başarısızsa manifeste GİRMEZ (bozuk kod onaylı sayılmasın).
    """
    clean = _clean_name(name)
    if not (code or "").strip():
        raise SkillError("`code` boş olamaz. NAME, DESCRIPTION, SCHEMA ve run(args, ctx) yaz.")

    path = folder(sandbox_root) / f"{clean}.py"
    path.write_text(code, encoding="utf-8")
    skill = load_file(path)   # doğrulama önce; patlarsa manifeste yazılmaz
    if state_dir is not None:
        _onayla(state_dir, path)
    return skill


def register(registry: Any, skills: list[Skill]) -> tuple[list[str], list[str]]:
    """Yetenekleri araç defterine ekler. (yeni eklenenler, tazelenenler)

    Zaten yüklü bir yetenek **tazeleniyor**, atlanmıyor. Önceki hal
    atlıyordu ve ajan kendi dosyasını düzeltip yeniden yüklediğinde
    bellekteki eski hali çalışmaya devam ediyordu — ajan bunu fark edip
    "cache'li hal eski kodu kullanıyor" diyerek her seferinde kabuğa
    düşüyordu: yetenek, yeteneksizlikten daha yavaş hale gelmişti.

    Yerleşik bir araçla adı çakışan yetenek yine atlanıyor: `shell`
    adında bir yetenek izin kapısını değiştirirdi.
    """
    from .tools.base import ToolResult, ToolSpec

    added: list[str] = []
    updated: list[str] = []
    for skill in skills:
        existing = registry.get(skill.name)
        if existing is not None and existing.source != "yetenek":
            continue

        spec = ToolSpec(
            name=skill.name,
            description=skill.description,
            input_schema=skill.schema,
            handler=_handler(skill, ToolResult),
            # Ne yaptığı bilinmiyor: dosya yazabilir, ağa çıkabilir.
            # İzin kapısından geçmesi gerekiyor.
            mutates=True,
            parallel_safe=False,
            source="yetenek",
        )
        if existing is None:
            registry.register(spec)
            added.append(skill.name)
        else:
            registry.replace(spec)
            updated.append(skill.name)
    return added, updated


def _handler(skill: Skill, ToolResult: Any) -> Any:
    """Yeteneği araç arayüzüne sarar.

    `run` senkron da olabilir asenkron da: ajan kendi yazdığı basit bir
    yeteneği `async` yapmak zorunda kalmamalı. Senkron olan ayrı bir
    thread'de koşuyor, yoksa uzun süren bir yetenek tüm döngüyü kilitliyor.
    """
    import asyncio
    import inspect

    async def call(args: dict[str, Any], ctx: Any) -> Any:
        try:
            if inspect.iscoroutinefunction(skill.run):
                answer = await skill.run(args, ctx)
            else:
                answer = await asyncio.to_thread(skill.run, args, ctx)
        except Exception:
            # Yeteneğin çökmesi ajanı düşürmemeli; yığın izi modele gidiyor
            # ki kendi yazdığı kodu düzeltebilsin.
            return ToolResult.error(
                f"'{skill.name}' hata verdi:\n{traceback.format_exc(limit=4)}\n"
                f"Dosya: {skill.path}"
            )

        if isinstance(answer, ToolResult):
            return answer
        return ToolResult(content=str(answer) if answer is not None else "(boş sonuç)")

    return call
