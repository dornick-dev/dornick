"""Atölye sınırı.

Buradaki tek kural — okuma her yerde, yazma yalnızca atölyede — sessizce
delinebilecek üç yer var: `..` ile yukarı çıkmak, sembolik bağ üzerinden
dışarı taşmak, ve henüz var olmayan bir dosyanın nerede olduğunun yanlış
hesaplanması. Üçü de aşağıda.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dornick.config import Config
from dornick.events import EventLog
from dornick.sandbox import OutsideSandbox, Sandbox
from dornick.session import Session
from dornick.tools import ToolContext, ToolRegistry
from dornick.tools import files as file_tools


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "gizli.txt").write_text("kullanıcının dosyası", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def ctx(workspace: Path) -> ToolContext:
    config = Config.load(workspace)
    config.ensure_dirs()
    session = Session(EventLog(workspace / ".dornick" / "s.jsonl"), "test")
    return ToolContext(config=config, session=session, cancel=asyncio.Event())


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    file_tools.register(reg)
    return reg


async def call(registry: ToolRegistry, name: str, ctx: ToolContext, **args):
    return await registry.get(name).handler(args, ctx)


# -- sınır hesabı ------------------------------------------------------


def test_a_path_that_does_not_exist_yet_is_still_placed(tmp_path: Path) -> None:
    """Yazma çoğunlukla henüz olmayan bir dosyaya yapılıyor; sınır kontrolü
    dosyanın varlığına bağlı olamaz."""
    box = Sandbox.open(tmp_path)

    assert box.contains(box.root / "site" / "index.html")
    assert not box.contains(tmp_path / "baska" / "index.html")


def test_climbing_out_with_dot_dot_is_caught(tmp_path: Path) -> None:
    box = Sandbox.open(tmp_path)

    with pytest.raises(OutsideSandbox):
        box.check(box.root / ".." / "kacak.txt")


def test_a_symlink_pointing_outside_is_caught(tmp_path: Path) -> None:
    """Bağ çözülmeden karşılaştırılırsa sınır kâğıt üstünde kalıyor."""
    box = Sandbox.open(tmp_path)
    outside = tmp_path / "disarisi"
    outside.mkdir()
    try:
        (box.root / "kopru").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("bu sistemde sembolik bağ kurulamıyor")

    with pytest.raises(OutsideSandbox):
        box.check(box.root / "kopru" / "kacak.txt")


def test_the_root_itself_counts_as_inside(tmp_path: Path) -> None:
    box = Sandbox.open(tmp_path)
    assert box.contains(box.root)


def test_a_disabled_sandbox_lets_everything_through(tmp_path: Path) -> None:
    """Kapatmak bilinçli bir karar; kapalıyken kısıt hiç uygulanmamalı."""
    box = Sandbox.open(tmp_path, enabled=False)
    assert box.check(tmp_path / "her" / "yer.txt")


def test_an_absolute_directory_can_be_used(tmp_path: Path) -> None:
    elsewhere = tmp_path / "baska" / "yer"
    box = Sandbox.open(tmp_path / "ws", str(elsewhere))

    assert box.root == elsewhere.resolve()
    assert box.root.is_dir()


# -- araçlar -----------------------------------------------------------


async def test_relative_writes_land_in_the_workshop(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """Ajan "site/index.html" yazdığında bunun kendi klasöründe olmasını
    bekliyor; çalışma alanının köküne düşmesi kullanıcının dosyalarının
    arasına karışmak demek."""
    result = await call(registry, "write_file", ctx, path="site/index.html", content="<h1>x</h1>")

    assert not result.is_error
    assert (ctx.sandbox.root / "site" / "index.html").read_text(encoding="utf-8") == "<h1>x</h1>"


async def test_writing_outside_is_refused_with_a_way_forward(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    """"İzin yok" demek yetmiyor: model bir sonraki turda ne yapacağını
    bilmeli, yoksa aynı çağrıyı tekrarlıyor."""
    result = await call(
        registry, "write_file", ctx, path=str(workspace / "gizli.txt"), content="ezildi"
    )

    assert result.is_error
    assert "copy_in" in result.content
    assert workspace.joinpath("gizli.txt").read_text(encoding="utf-8") == "kullanıcının dosyası"


async def test_editing_outside_is_refused_too(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    """write_file kapatılıp edit_file açık kalırsa sınır hiç yok demektir."""
    target = str(workspace / "gizli.txt")
    await call(registry, "read_file", ctx, path=target)

    result = await call(registry, "edit_file", ctx, path=target, old="kullanıcının", new="benim")

    assert result.is_error
    assert workspace.joinpath("gizli.txt").read_text(encoding="utf-8") == "kullanıcının dosyası"


async def test_reading_outside_stays_free(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    """Kısıt yazmada; ajan bilgisayardaki her şeyi görebilmeli."""
    result = await call(registry, "read_file", ctx, path=str(workspace / "gizli.txt"))

    assert not result.is_error
    assert "kullanıcının dosyası" in result.content


async def test_copy_in_brings_a_file_without_touching_the_original(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    result = await call(registry, "copy_in", ctx, path=str(workspace / "gizli.txt"))

    assert not result.is_error
    copy = ctx.sandbox.root / "gizli.txt"
    assert copy.read_text(encoding="utf-8") == "kullanıcının dosyası"
    assert workspace.joinpath("gizli.txt").exists()


async def test_the_copy_is_immediately_editable(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    """Kopyayı az önce bu süreç yazdı; bayatlık kontrolü modeli gereksiz bir
    read_file turuna zorlamamalı."""
    await call(registry, "copy_in", ctx, path=str(workspace / "gizli.txt"), to="calisma.txt")

    result = await call(registry, "edit_file", ctx, path="calisma.txt",
                        old="kullanıcının", new="benim")

    assert not result.is_error
    assert (ctx.sandbox.root / "calisma.txt").read_text(encoding="utf-8") == "benim dosyası"


async def test_copy_in_cannot_be_used_to_escape(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    """Hedef de sınır kontrolünden geçmeli; yoksa kopyalama bir kaçış yolu."""
    result = await call(
        registry, "copy_in", ctx, path=str(workspace / "gizli.txt"), to="../kacak.txt"
    )

    assert result.is_error
    assert not (workspace / "kacak.txt").exists()


async def test_copy_in_does_not_overwrite(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    await call(registry, "copy_in", ctx, path=str(workspace / "gizli.txt"), to="a.txt")
    result = await call(registry, "copy_in", ctx, path=str(workspace / "gizli.txt"), to="a.txt")

    assert result.is_error
    assert "zaten var" in result.content


async def test_a_whole_directory_can_be_copied(
    registry: ToolRegistry, ctx: ToolContext, workspace: Path
) -> None:
    source = workspace / "proje"
    (source / "src").mkdir(parents=True)
    (source / "src" / "a.py").write_text("print(1)", encoding="utf-8")
    (source / "okuma.md").write_text("# proje", encoding="utf-8")

    result = await call(registry, "copy_in", ctx, path=str(source), to="proje")

    assert not result.is_error
    assert (ctx.sandbox.root / "proje" / "src" / "a.py").exists()
    assert result.detail["files"] == 2


# -- prompt ------------------------------------------------------------


def test_the_agent_is_told_where_it_lives(tmp_path: Path) -> None:
    """Kural sistem promptunda yazmazsa model her yazmada duvara çarpıp
    deneme yanılmayla öğreniyor."""
    briefing = Sandbox.open(tmp_path).briefing()

    assert "atolye" in briefing.lower()
    assert "copy_in" in briefing


def test_a_disabled_sandbox_says_nothing(tmp_path: Path) -> None:
    assert Sandbox.open(tmp_path, enabled=False).briefing() == ""


async def test_the_workshop_name_is_not_nested(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """Model atölyenin adını yola kendisi ekliyor.

    Sistem promptunda klasörün tam yolu yazıyor ve oradan çıkarım yapıp
    "atolye/merhaba.txt" diyor. Olduğu gibi birleştirmek `atolye/atolye/...`
    üretiyordu — gerçek bir koşuda tam olarak bu oldu ve dosya bir alt
    klasöre düştü.
    """
    name = ctx.sandbox.root.name
    result = await call(registry, "write_file", ctx, path=f"{name}/merhaba.txt", content="selam")

    assert not result.is_error
    assert (ctx.sandbox.root / "merhaba.txt").read_text(encoding="utf-8") == "selam"
    assert not (ctx.sandbox.root / name).exists()


async def test_a_deeper_path_keeps_its_shape(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    name = ctx.sandbox.root.name
    await call(registry, "write_file", ctx, path=f"{name}/site/index.html", content="<h1>x</h1>")

    assert (ctx.sandbox.root / "site" / "index.html").exists()


async def test_a_folder_that_only_shares_the_name_is_untouched(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """Kırpma yalnızca ilk parçada; içeride aynı adı taşıyan bir klasör
    olabilir ve o kalmalı."""
    name = ctx.sandbox.root.name
    await call(registry, "write_file", ctx, path=f"proje/{name}/not.txt", content="x")

    assert (ctx.sandbox.root / "proje" / name / "not.txt").exists()


def test_the_briefing_says_relative_paths_land_here(tmp_path: Path) -> None:
    briefing = Sandbox.open(tmp_path).briefing()
    assert "Göreli yol" in briefing


# -- proje kipi --------------------------------------------------------
#
# "Benim projemde vibe-coding yapacaksam klasörü seçmem gerekiyor." Bir
# AĞACI atölyeye kopyalamak işi imkânsız kılıyor: kopyası orijinali
# olmuyor. Kullanıcı klasörü açıkça seçince orası da yazılabilir oluyor —
# seçimin kendisi onaydır. Atölye her koşulda açık kalıyor.

from dornick import sandbox as sandbox_module   # noqa: E402


def test_a_chosen_project_becomes_writable(tmp_path: Path) -> None:
    proje = tmp_path / "musteri-projesi"
    proje.mkdir()
    box = Sandbox.open(tmp_path, "atolye", project=str(proje))

    assert box.contains(proje / "src" / "yeni.py")     # henüz olmayan dosya da
    assert box.check(proje / "app.py") is not None
    # Atölye kaybolmuyor: dornick'nun kendi işleri oraya gitmeye devam ediyor.
    assert box.contains(box.root / "deneme.txt")
    assert box.project == proje.resolve()
    assert box.roots[0] == box.root                     # atölye her zaman ilk


def test_everything_outside_the_open_roots_is_still_refused(tmp_path: Path) -> None:
    proje = tmp_path / "proje"
    proje.mkdir()
    (tmp_path / "baska").mkdir()
    box = Sandbox.open(tmp_path, "atolye", project=str(proje))

    with pytest.raises(OutsideSandbox) as caught:
        box.check(tmp_path / "baska" / "dosya.txt")
    # Hata ne yapılacağını söylemeli; "izin yok" tek başına bir yol açmıyor.
    assert "Ayarlar › Proje" in str(caught.value)
    assert str(proje.resolve()) in str(caught.value)


def test_without_a_project_the_old_rule_holds(tmp_path: Path) -> None:
    box = Sandbox.open(tmp_path, "atolye")
    assert box.project is None
    assert box.roots == (box.root,)
    with pytest.raises(OutsideSandbox):
        box.check(tmp_path / "disarida.txt")


def test_dangerous_roots_are_refused_with_a_reason(tmp_path: Path) -> None:
    r"""Kullanıcı seçse bile bazı kökler kabul edilemez: `C:\` seçmek
    "her yere yazabilirsin" demenin uzun yoludur."""
    kok = Path(tmp_path.anchor or "/")
    assert sandbox_module.kok_engeli(kok) is not None

    ev = Path.home()
    assert sandbox_module.kok_engeli(ev) is not None, "kullanıcı klasörü fazla geniş"
    # Ev DİZİNİNİN ALTI serbest: asıl projeler orada duruyor.
    alt = tmp_path / "kod" / "proje"
    alt.mkdir(parents=True)
    assert sandbox_module.kok_engeli(alt) is None

    # Olmayan ve klasör olmayan yollar da sebebiyle reddediliyor.
    assert sandbox_module.kok_engeli(tmp_path / "yok") is not None
    dosya = tmp_path / "dosya.txt"
    dosya.write_text("x", encoding="utf-8")
    assert sandbox_module.kok_engeli(dosya) is not None


def test_system_folders_are_refused(tmp_path: Path) -> None:
    """İşletim sistemi klasörleri: adı yeterli kanıt, var olmaları şart değil."""
    sahte = tmp_path / "Windows"
    sahte.mkdir()
    assert "işletim sistemi" in (sandbox_module.kok_engeli(sahte) or "")


def test_an_invalid_project_falls_back_instead_of_breaking(tmp_path: Path) -> None:
    """Ayar dosyası elle düzenlenmiş ya da klasör silinmiş olabilir:
    program AÇILMAZ hâle gelmemeli, sessizce atölyeye dönmeli."""
    box = Sandbox.open(tmp_path, "atolye", project=str(tmp_path / "silinmis"))
    assert box.project is None
    assert box.contains(box.root / "x.txt")


def test_covering_neos_own_state_warns_but_does_not_block(tmp_path: Path) -> None:
    """Kendi kodunu dornick'ya düzelttirmek meşru bir istek — bu depo tam
    olarak öyle geliştiriliyor. Engelleme değil, uyarı."""
    durum = tmp_path / ".dornick"
    durum.mkdir()
    box = Sandbox.open(tmp_path / "ws", "atolye", project=str(tmp_path),
                       state_dir=durum)
    assert box.project == tmp_path.resolve()      # engellenmedi
    assert "hafızasına" in box.note               # ama söylendi


def test_the_briefing_tells_the_model_which_folder_is_which(tmp_path: Path) -> None:
    """Model hangisinin ne olduğunu bilmeli, yoksa kullanıcının projesine
    kendi denemelerini bırakır."""
    proje = tmp_path / "musteri"
    proje.mkdir()

    yalin = Sandbox.open(tmp_path, "atolye").briefing()
    assert "yazma yalnızca bu klasörde" in yalin
    assert "Çalışılan proje" not in yalin

    projeli = Sandbox.open(tmp_path, "atolye", project=str(proje)).briefing()
    assert f"Çalışılan proje: {proje.resolve()}" in projeli
    assert "yazma serbest" in projeli
    # Atölye de görünmeye devam ediyor: ikisi ayrı işler.
    assert str(Sandbox.open(tmp_path, "atolye").root) in projeli
    assert "kendi işlerin" in projeli


def test_relative_paths_resolve_against_the_nearest_open_root(tmp_path: Path) -> None:
    proje = tmp_path / "proje"
    (proje / "src").mkdir(parents=True)
    box = Sandbox.open(tmp_path, "atolye", project=str(proje))
    assert box.relative(proje / "src" / "app.py") == "src/app.py"
    assert box.relative(box.root / "not.md") == "not.md"


def test_recent_projects_are_remembered_in_order(tmp_path: Path) -> None:
    """Son projeler tek tıkla geçiş için; en son seçilen başta."""
    durum = tmp_path / ".dornick"
    assert sandbox_module.son_projeler(durum) == []

    sandbox_module.proje_hatirla(durum, "C:/a")
    sandbox_module.proje_hatirla(durum, "C:/b")
    assert sandbox_module.son_projeler(durum) == ["C:/b", "C:/a"]

    # Aynı proje iki kez listelenmiyor, başa geçiyor.
    sandbox_module.proje_hatirla(durum, "C:/a")
    assert sandbox_module.son_projeler(durum) == ["C:/a", "C:/b"]

    # Defter sınırlı: liste sonsuza kadar uzamıyor.
    for i in range(20):
        sandbox_module.proje_hatirla(durum, f"C:/p{i}")
    assert len(sandbox_module.son_projeler(durum)) == sandbox_module.MAX_RECENT


def test_a_corrupt_recent_file_does_not_break_settings(tmp_path: Path) -> None:
    durum = tmp_path / ".dornick"
    durum.mkdir()
    (durum / sandbox_module.PROJECTS_FILE).write_text("{bozuk", encoding="utf-8")
    assert sandbox_module.son_projeler(durum) == []


def test_the_project_survives_a_settings_round_trip(tmp_path: Path) -> None:
    from dornick import settings

    proje = tmp_path / "musteri"
    proje.mkdir()
    config = Config.load(tmp_path)
    config.ensure_dirs()

    updated = settings.apply(config, {"sandbox": {"project": str(proje)}})
    assert updated.sandbox.project == str(proje)
    assert Config.load(tmp_path).sandbox.project == str(proje)
    # Seçim son projeler defterine de düşüyor.
    assert str(proje) in sandbox_module.son_projeler(updated.state_dir)
    # Ve gerçekten yazılabilir.
    assert updated.open_sandbox().contains(proje / "yeni.py")


def test_settings_refuses_a_dangerous_project_with_a_reason(tmp_path: Path) -> None:
    """Doğrulama arayüzde değil burada: geçersiz bir kök ancak ajan oraya
    yazmaya çalışınca patlardı ve o çok geç."""
    from dornick import settings

    config = Config.load(tmp_path)
    config.ensure_dirs()
    with pytest.raises(ValueError) as caught:
        settings.apply(config, {"sandbox": {"project": str(Path(tmp_path.anchor or "/"))}})
    assert "sürücü kökü" in str(caught.value) or "işletim sistemi" in str(caught.value)
    # Reddedilen seçim diske yazılmamalı.
    assert Config.load(tmp_path).sandbox.project == ""
