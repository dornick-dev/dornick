"""Kancalar: kullanıcının kendi komutlarını araç yaşam döngüsüne takması.

Sınanan vaat: `.dornick/kancalar.json` dosyasına yazılan bir komut aracın
önünde ya da arkasında koşmalı; `arac_oncesi` sıfırdan farklı bir kodla
dönerse araç HİÇ çalışmamalı ve gerekçe modele gitmeli.

İkinci ve daha önemli vaat GÜVENLİK: kancalar izin motorunun dışında
çalışır (kullanıcının kendi komutudur), bu yüzden model onları
DEĞİŞTİREMEMELİ. Değiştirebilseydi, kendisini engelleyen kancayı silerek
izin kapısını tümüyle atlardı.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from dornick import kancalar
from dornick.config import Config
from dornick.events import EventLog
from dornick.permissions import PermissionEngine
from dornick.session import PendingToolUse, Session
from dornick.tools import ToolContext, ToolRegistry, ToolResult, execute, object_schema
from dornick.tools import files as file_tools

PY = sys.executable


@pytest.fixture(autouse=True)
def temiz_bellek():
    kancalar.bellegi_temizle()
    yield
    kancalar.bellegi_temizle()


def yaz(state_dir: Path, maddeler: list[dict]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "kancalar.json").write_text(
        json.dumps(maddeler, ensure_ascii=False), encoding="utf-8")


def betik(kod: str) -> str:
    """Kanca komutu olarak koşacak küçük bir Python satırı."""
    return f'& "{PY}" -c "{kod}"'


# -- yapılandırmayı okumak ---------------------------------------------


def test_no_file_means_no_hooks(tmp_path: Path) -> None:
    """Kanca kullanmayan kullanıcı hiçbir bedel ödememeli."""
    assert kancalar.yukle(tmp_path) == []


def test_hooks_are_parsed(tmp_path: Path) -> None:
    yaz(tmp_path, [{"olay": "arac_oncesi", "arac": "write_file",
                    "komut": "echo x", "zaman_asimi": 5}])
    (kanca,) = kancalar.yukle(tmp_path)
    assert kanca.olay == "arac_oncesi"
    assert kanca.komut == "echo x"
    assert kanca.zaman_asimi == 5


def test_broken_entries_drop_but_good_ones_survive(tmp_path: Path) -> None:
    """Bir yazım hatası bütün araç katmanını durdurmamalı."""
    yaz(tmp_path, [
        {"olay": "yanlis_olay", "komut": "echo a"},     # tanınmayan olay
        {"olay": "arac_oncesi"},                        # komut yok
        "düz metin",                                    # madde bile değil
        {"olay": "arac_sonrasi", "komut": "echo b"},    # sağlam
    ])
    kancalar_ = kancalar.yukle(tmp_path)
    assert [k.komut for k in kancalar_] == ["echo b"]


def test_broken_json_disables_hooks_but_is_reportable(tmp_path: Path) -> None:
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "kancalar.json").write_text("{bozuk", encoding="utf-8")
    assert kancalar.yukle(tmp_path) == []
    assert "geçerli JSON değil" in kancalar.bozuk_mu(tmp_path)


def test_a_missing_file_is_not_broken(tmp_path: Path) -> None:
    assert kancalar.bozuk_mu(tmp_path) == ""


def test_the_cache_follows_the_user_edit(tmp_path: Path) -> None:
    """Kullanıcı dosyayı düzenleyince yeniden başlatmak gerekmemeli."""
    yaz(tmp_path, [{"olay": "arac_oncesi", "komut": "echo bir"}])
    assert [k.komut for k in kancalar.yukle(tmp_path)] == ["echo bir"]
    yaz(tmp_path, [{"olay": "arac_oncesi", "komut": "echo iki"}])
    assert [k.komut for k in kancalar.yukle(tmp_path)] == ["echo iki"]


def test_the_timeout_is_capped(tmp_path: Path) -> None:
    yaz(tmp_path, [{"olay": "arac_oncesi", "komut": "echo x",
                    "zaman_asimi": 99999}])
    assert kancalar.yukle(tmp_path)[0].zaman_asimi == kancalar.MAX_ZAMAN_ASIMI


# -- fnmatch eşleşmesi -------------------------------------------------


@pytest.mark.parametrize("desen,arac,bekleniyor", [
    ("write_file", "write_file", True),
    ("write_file", "edit_file", False),
    ("*", "shell", True),
    ("*_file", "write_file", True),
    ("*_file", "shell", False),
    ("write_file|edit_file", "edit_file", True),
    ("write_file|edit_file", "shell", False),
    ("write_file | edit_file", "edit_file", True),   # boşluk toleransı
])
def test_tool_patterns(desen: str, arac: str, bekleniyor: bool) -> None:
    kanca = kancalar.Kanca("arac_oncesi", desen, "echo x")
    assert kanca.uyar_mi(arac) is bekleniyor


def test_matching_respects_the_event(tmp_path: Path) -> None:
    yaz(tmp_path, [
        {"olay": "arac_oncesi", "arac": "*", "komut": "echo once"},
        {"olay": "arac_sonrasi", "arac": "*", "komut": "echo sonra"},
    ])
    once = kancalar.eslesenler(tmp_path, "arac_oncesi", "shell")
    assert [k.komut for k in once] == ["echo once"]


# -- arac_oncesi: veto -------------------------------------------------


async def test_a_zero_exit_lets_the_tool_run(tmp_path: Path) -> None:
    yaz(tmp_path, [{"olay": "arac_oncesi", "arac": "write_file",
                    "komut": betik("pass")}])
    karar = await kancalar.arac_oncesi(tmp_path, "write_file", {}, cwd=tmp_path)
    assert karar.izin
    assert karar.gerekce == ""


async def test_a_nonzero_exit_blocks_the_tool(tmp_path: Path) -> None:
    """Çekirdek senaryo: yasaklı dosyaya yazmayı engelle."""
    yaz(tmp_path, [{"olay": "arac_oncesi", "arac": "write_file",
                    "komut": betik("import sys; print('uretim dosyasi, dokunma'); "
                                   "sys.exit(1)")}])
    karar = await kancalar.arac_oncesi(tmp_path, "write_file", {}, cwd=tmp_path)
    assert not karar.izin
    assert "Kanca reddetti" in karar.gerekce
    assert "uretim dosyasi, dokunma" in karar.gerekce
    # Model kuralı aşmaya çalışmasın diye kaynağı söyleniyor.
    assert "kullanıcının kendi kuralı" in karar.gerekce


async def test_an_unmatched_tool_is_untouched(tmp_path: Path) -> None:
    yaz(tmp_path, [{"olay": "arac_oncesi", "arac": "write_file",
                    "komut": betik("import sys; sys.exit(1)")}])
    karar = await kancalar.arac_oncesi(tmp_path, "read_file", {}, cwd=tmp_path)
    assert karar.izin


async def test_the_first_refusal_stops_the_chain(tmp_path: Path) -> None:
    """Karar verildikten sonra ikinci bekçiye sormanın anlamı yok."""
    iz = tmp_path / "iz.txt"
    yaz(tmp_path, [
        {"olay": "arac_oncesi", "arac": "*",
         "komut": betik("import sys; print('ilk'); sys.exit(3)")},
        {"olay": "arac_oncesi", "arac": "*",
         "komut": betik(f"open(r'{iz}', 'w').write('kostum')")},
    ])
    karar = await kancalar.arac_oncesi(tmp_path, "shell", {}, cwd=tmp_path)
    assert not karar.izin
    assert "çıkış kodu 3" in karar.gerekce
    assert not iz.exists()          # ikinci kanca hiç koşmadı


async def test_a_timeout_blocks_on_the_safe_side(tmp_path: Path) -> None:
    """Bekçi cevap vermiyorsa 'herhalde izin verirdi' demek, bekçiyi
    ortadan kaldırmak olur."""
    yaz(tmp_path, [{"olay": "arac_oncesi", "arac": "*",
                    "komut": betik("import time; time.sleep(60)"),
                    "zaman_asimi": 2}])
    import time as _t

    basla = _t.monotonic()
    karar = await kancalar.arac_oncesi(tmp_path, "shell", {}, cwd=tmp_path)
    gecen = _t.monotonic() - basla
    assert not karar.izin
    assert "cevap vermedi" in karar.gerekce
    assert "güvenli taraf" in karar.gerekce
    # Zaman aşımı GERÇEKTEN zaman aşımı süresinde dönmeli: kabuğu öldürüp
    # asıl süreci bırakmak (borular açık kalıyor) 2 saniyelik sınırı 60
    # saniyelik bir bekleyişe çeviriyordu.
    assert gecen < 20, f"kanca zaman aşımı {gecen:.0f} sn asılı kaldı"


async def test_a_hook_that_cannot_start_is_skipped_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kancanın kendi arızası aracı öldürmemeli — ama saklanmamalı da."""
    async def patla(*_a, **_k):
        raise OSError("kabuk bulunamadı")

    monkeypatch.setattr(kancalar, "_baslat", patla)
    yaz(tmp_path, [{"olay": "arac_oncesi", "arac": "*", "komut": "her neyse"}])
    karar = await kancalar.arac_oncesi(tmp_path, "shell", {}, cwd=tmp_path)
    assert karar.izin                       # araç çalışmaya devam
    assert karar.notlar
    assert "çalıştırılamadı" in karar.notlar[0]
    assert "uygulanmadı" in karar.notlar[0]


# -- ortam değişkenleri ------------------------------------------------


async def test_the_hook_receives_its_context_in_the_environment(tmp_path: Path) -> None:
    """JSON'u komut satırına gömmek kaçış cehennemi; ortam değişkeni değil.

    Kanca gerçek bir kullanıcı kancası gibi kuruluyor: ayrı bir betik
    dosyası, `os.environ`dan okuyor.
    """
    hedef = tmp_path / "cikti.json"
    kanca_py = tmp_path / "bekci.py"
    kanca_py.write_text(
        "import json, os, pathlib\n"
        "pathlib.Path(r'''" + str(hedef) + "''').write_text(json.dumps({\n"
        "    'arac': os.environ.get('DORNICK_ARAC'),\n"
        "    'args': os.environ.get('DORNICK_ARGS'),\n"
        "    'yol': os.environ.get('DORNICK_YOL'),\n"
        "    'oturum': os.environ.get('DORNICK_OTURUM'),\n"
        "}), encoding='utf-8')\n",
        encoding="utf-8")
    yaz(tmp_path, [{"olay": "arac_oncesi", "arac": "*",
                    "komut": f'& "{PY}" "{kanca_py}"'}])

    await kancalar.arac_oncesi(
        tmp_path, "write_file",
        {"path": "C:/proje/app.py", "content": "x = 1"},
        oturum="20260101T0000Z", cwd=tmp_path)

    gorulen = json.loads(hedef.read_text(encoding="utf-8"))
    assert gorulen["arac"] == "write_file"
    assert gorulen["yol"] == "C:/proje/app.py"
    assert gorulen["oturum"] == "20260101T0000Z"
    # Argümanların tamamı JSON olarak da geçiyor.
    assert json.loads(gorulen["args"])["content"] == "x = 1"


async def test_a_pathless_call_still_defines_the_variable(tmp_path: Path) -> None:
    """`$DORNICK_YOL` tanımsız olursa kullanıcının kancası patlardı."""
    hedef = tmp_path / "yol.txt"
    kanca_py = tmp_path / "yoku.py"
    kanca_py.write_text(
        "import os, pathlib\n"
        "pathlib.Path(r'''" + str(hedef) + "''').write_text("
        "repr(os.environ.get('DORNICK_YOL')))\n",
        encoding="utf-8")
    yaz(tmp_path, [{"olay": "arac_oncesi", "arac": "*",
                    "komut": f'& "{PY}" "{kanca_py}"'}])
    await kancalar.arac_oncesi(tmp_path, "shell", {"command": "ls"}, cwd=tmp_path)
    assert hedef.read_text() == "''"


# -- arac_sonrasi: bilgilendirme ---------------------------------------


async def test_a_post_hook_reports_its_output(tmp_path: Path) -> None:
    yaz(tmp_path, [{"olay": "arac_sonrasi", "arac": "write_file",
                    "komut": betik("print('bicimlendirildi')")}])
    notlar = await kancalar.arac_sonrasi(tmp_path, "write_file", {}, cwd=tmp_path)
    assert notlar == ["kanca: bicimlendirildi"]


async def test_a_post_hook_cannot_veto(tmp_path: Path) -> None:
    """İş çoktan oldu; 'reddediyorum' demenin karşılığı yok."""
    yaz(tmp_path, [{"olay": "arac_sonrasi", "arac": "*",
                    "komut": betik("import sys; print('begenmedim'); sys.exit(2)")}])
    notlar = await kancalar.arac_sonrasi(tmp_path, "shell", {}, cwd=tmp_path)
    assert len(notlar) == 1
    assert "çıkış 2" in notlar[0] and "begenmedim" in notlar[0]


async def test_a_silent_post_hook_says_nothing(tmp_path: Path) -> None:
    """Gürültü üretmemek şart: her yazmanın altına boş bir satır eklemek,
    gerçek uyarıların da okunmamasına yol açar."""
    yaz(tmp_path, [{"olay": "arac_sonrasi", "arac": "*", "komut": betik("pass")}])
    assert await kancalar.arac_sonrasi(tmp_path, "shell", {}, cwd=tmp_path) == []


async def test_multiline_output_becomes_one_line(tmp_path: Path) -> None:
    yaz(tmp_path, [{"olay": "arac_sonrasi", "arac": "*",
                    "komut": betik("print('bir'); print('iki')")}])
    (not_,) = await kancalar.arac_sonrasi(tmp_path, "shell", {}, cwd=tmp_path)
    assert "\n" not in not_
    assert "bir iki" in not_


async def test_stderr_is_used_when_stdout_is_empty(tmp_path: Path) -> None:
    yaz(tmp_path, [{"olay": "arac_sonrasi", "arac": "*",
                    "komut": betik("import sys; print('uyari', file=sys.stderr)")}])
    (not_,) = await kancalar.arac_sonrasi(tmp_path, "shell", {}, cwd=tmp_path)
    assert "uyari" in not_


async def test_post_hook_timeout_is_reported_not_fatal(tmp_path: Path) -> None:
    yaz(tmp_path, [{"olay": "arac_sonrasi", "arac": "*",
                    "komut": betik("import time; time.sleep(60)"),
                    "zaman_asimi": 2}])
    (not_,) = await kancalar.arac_sonrasi(tmp_path, "shell", {}, cwd=tmp_path)
    assert "bitmedi ve durduruldu" in not_


# -- kanca dosyasının korunması ---------------------------------------


@pytest.mark.parametrize("yol,korunuyor", [
    (".dornick/kancalar.json", True),
    (".dornick/KANCALAR.JSON", True),
    ("proje/.dornick/kancalar.json", True),       # başka projenin dosyası da
    (".dornick/ayarlar.json", False),
    ("kancalar.json", False),                   # .dornick altında değil
    ("src/kancalar.json", False),
])
def test_which_paths_are_protected(yol: str, korunuyor: bool) -> None:
    assert kancalar.korunan_mu(Path(yol)) is korunuyor


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    config = Config.load(tmp_path)
    config.ensure_dirs()
    return ToolContext(
        config=config,
        session=Session(EventLog(tmp_path / ".dornick" / "s.jsonl"), "test-kanca"),
        cancel=asyncio.Event(),
    )


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    file_tools.register(reg)
    return reg


async def test_the_model_cannot_write_the_hook_file(
    registry: ToolRegistry, ctx: ToolContext, tmp_path: Path
) -> None:
    """Güvenliğin bel kemiği. Model bu dosyayı yazabilseydi, kendisini
    engelleyen kancayı silerek izin kapısını tümüyle atlardı."""
    hedef = ctx.config.state_dir / "kancalar.json"
    sonuc = await registry.get("write_file").handler(
        {"path": str(hedef), "content": "[]"}, ctx)
    assert sonuc.is_error
    assert "yazmaya kapalıdır" in sonuc.content
    assert "kendin düzenleme" in sonuc.content
    assert not hedef.exists()


async def test_the_model_cannot_edit_the_hook_file(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    hedef = ctx.config.state_dir / "kancalar.json"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text('[{"olay": "arac_oncesi", "komut": "x"}]', encoding="utf-8")
    await registry.get("read_file").handler({"path": str(hedef)}, ctx)
    sonuc = await registry.get("edit_file").handler(
        {"path": str(hedef), "old": "arac_oncesi", "new": "hicbirsey"}, ctx)
    assert sonuc.is_error
    assert "yazmaya kapalıdır" in sonuc.content
    # Dosya olduğu gibi duruyor.
    assert "arac_oncesi" in hedef.read_text(encoding="utf-8")


def _kabuk_kaydi() -> tuple[ToolRegistry, list[str]]:
    """Kabuk gibi davranan tek araçlık defter: yazma aracı DEĞİL, `mutates`."""
    izler: list[str] = []
    reg = ToolRegistry()

    @reg.tool(name="shell", description="deneme",
              input_schema=object_schema({"command": {"type": "string"}}),
              mutates=True)
    async def _kos_komut(args, _ctx) -> ToolResult:
        izler.append(str(args.get("command")))
        return ToolResult("koştu")

    @reg.tool(name="list_dir", description="deneme",
              input_schema=object_schema({"path": {"type": "string"}}))
    async def _listele(args, _ctx) -> ToolResult:
        izler.append(str(args.get("path")))
        return ToolResult("listelendi")

    return reg, izler


async def test_the_model_cannot_reach_the_hook_file_through_the_shell(
    ctx: ToolContext
) -> None:
    """Yazma araçlarının kapısı kabuğu kapsamıyordu — asıl delik buydu.

    `write_file` engelleniyordu ama `Set-Content .dornick/kancalar.json`
    hiçbir kapıdan geçmiyordu; model kendisini durduran çiti kabukla
    sökebilirdi.
    """
    registry, izler = _kabuk_kaydi()
    bloklar = await execute(
        [PendingToolUse(id="c1", name="shell", input={
            "command": "Set-Content .dornick/kancalar.json '[]'"})],
        registry=registry,
        permissions=PermissionEngine("yolo", [], []),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )
    assert bloklar[0]["is_error"]
    assert "kanca dosyası" in bloklar[0]["content"]
    assert "read_file" in bloklar[0]["content"], "okumanın yolu gösterilmeli"
    assert izler == [], "komut HİÇ çalışmamalı"


async def test_an_unrelated_command_is_untouched(ctx: ToolContext) -> None:
    """Kanca kullanmayan kullanıcı bu kapıyı hiç görmemeli."""
    registry, izler = _kabuk_kaydi()
    bloklar = await execute(
        [PendingToolUse(id="c1", name="shell",
                        input={"command": "py -m pytest -q"})],
        registry=registry,
        permissions=PermissionEngine("yolo", [], []),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )
    assert not bloklar[0]["is_error"]
    assert izler == ["py -m pytest -q"]


async def test_a_read_only_tool_may_still_name_the_hook_file(
    ctx: ToolContext
) -> None:
    """Kapı yalnız DEĞİŞTİREN araçlar için: model kuralını okuyabilmeli."""
    registry, izler = _kabuk_kaydi()
    bloklar = await execute(
        [PendingToolUse(id="c1", name="list_dir",
                        input={"path": ".dornick/kancalar.json"})],
        registry=registry,
        permissions=PermissionEngine("yolo", [], []),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )
    assert not bloklar[0]["is_error"]
    assert izler == [".dornick/kancalar.json"]


async def test_the_model_can_still_read_the_hook_file(
    registry: ToolRegistry, ctx: ToolContext
) -> None:
    """Okumak yasak değil: model hangi kuralın altında çalıştığını bilmeli."""
    hedef = ctx.config.state_dir / "kancalar.json"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text("[]", encoding="utf-8")
    sonuc = await registry.get("read_file").handler({"path": str(hedef)}, ctx)
    assert not sonuc.is_error


# -- yürütücüyle uçtan uca ---------------------------------------------


def _kayit() -> tuple[ToolRegistry, list[str]]:
    """Çalıştığında iz bırakan tek araçlık bir defter."""
    izler: list[str] = []
    reg = ToolRegistry()

    @reg.tool(name="write_file", description="deneme",
              input_schema=object_schema({"path": {"type": "string"}}),
              mutates=True)
    async def _yaz(args, _ctx) -> ToolResult:
        izler.append(str(args.get("path")))
        return ToolResult(f"{args.get('path')} yazıldı.")

    return reg, izler


async def _kos(registry: ToolRegistry, ctx: ToolContext, args: dict) -> dict:
    bloklar = await execute(
        [PendingToolUse(id="c1", name="write_file", input=args)],
        registry=registry,
        permissions=PermissionEngine("yolo", [], []),
        ctx=ctx,
        approve=lambda *_: asyncio.sleep(0, result=True),
    )
    return bloklar[0]


async def test_the_executor_blocks_a_refused_call(ctx: ToolContext) -> None:
    yaz(ctx.config.state_dir, [{
        "olay": "arac_oncesi", "arac": "write_file",
        "komut": betik("import sys; print('bu depoda yazma'); sys.exit(1)")}])
    registry, izler = _kayit()
    blok = await _kos(registry, ctx, {"path": "app.py"})
    assert blok["is_error"]
    assert "bu depoda yazma" in blok["content"]
    assert izler == []              # araç HİÇ çalışmadı


async def test_the_executor_lets_an_approved_call_through(ctx: ToolContext) -> None:
    yaz(ctx.config.state_dir, [{
        "olay": "arac_oncesi", "arac": "write_file", "komut": betik("pass")}])
    registry, izler = _kayit()
    blok = await _kos(registry, ctx, {"path": "app.py"})
    assert not blok["is_error"]
    assert izler == ["app.py"]


async def test_the_executor_appends_post_hook_output(ctx: ToolContext) -> None:
    yaz(ctx.config.state_dir, [{
        "olay": "arac_sonrasi", "arac": "write_file",
        "komut": betik("print('black ile bicimlendirildi')")}])
    registry, _izler = _kayit()
    blok = await _kos(registry, ctx, {"path": "app.py"})
    assert "app.py yazıldı." in blok["content"]
    assert "kanca: black ile bicimlendirildi" in blok["content"]


async def test_without_a_hook_file_nothing_changes(ctx: ToolContext) -> None:
    """Kanca kullanmayan kullanıcının çıktısı bir harf bile değişmemeli."""
    registry, izler = _kayit()
    blok = await _kos(registry, ctx, {"path": "app.py"})
    assert blok["content"] == "app.py yazıldı."
    assert izler == ["app.py"]


async def test_a_broken_hook_layer_never_kills_the_tool(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kanca katmanının kendi çöküşü aracı düşürmemeli."""
    async def patla(*_a, **_k):
        raise RuntimeError("kanca katmanı bozuldu")

    monkeypatch.setattr(kancalar, "arac_oncesi", patla)
    registry, izler = _kayit()
    blok = await _kos(registry, ctx, {"path": "app.py"})
    assert izler == ["app.py"]
    assert "kanca katmanı çalışmadı" in blok["content"]
