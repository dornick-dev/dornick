"""Kodlama ölçüm düzeneğinin kendi testleri (`eval/coding/`).

Bir puanlayıcı ölçülmeden kullanılamaz: hatalı bir ölçüt, modelin
başarısızlığı gibi görünür ve haftalarca yanlış yere bakılır. Buradaki
testler üç şeyi çiviliyor:

  1. **Doğru çözüm yüksek alıyor.** Referans çözümler test içinde
     üretiliyor (depoya yazılmıyor) ve puanlayıcıdan geçiriliyor.
  2. **Bozuk/eksik teslim düşük alıyor** ve "bozuk teslim" bayrağı kalkıyor.
  3. **Ölçemediğini ölçtüm demiyor.** Ölçülemeyen eksen `None` dönüyor,
     paydadan düşüyor; istenmemiş iş puana katılmıyor.

Ayrıca davranış çıkarımı sahte bir oturum günlüğüyle sınanıyor: uydurma yok,
kanıt yoksa "çıkarılamadı".
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
OLCUM = KOK / "eval" / "coding"
sys.path.insert(0, str(OLCUM))

import davranis  # noqa: E402
import puanla  # noqa: E402


def olcut(ad: str):
    """Bir görevin puanlayıcı modülünü yükler."""
    yol = OLCUM / "gorevler" / ad / "olcut.py"
    spec = importlib.util.spec_from_file_location(f"olcut_test_{ad}", yol)
    assert spec and spec.loader
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def tohumla(ad: str, hedef: Path) -> Path:
    kaynak = OLCUM / "gorevler" / ad / "tohum"
    hedef.mkdir(parents=True, exist_ok=True)
    if kaynak.is_dir():
        shutil.copytree(kaynak, hedef, dirs_exist_ok=True)
    return hedef


# -- düzeneğin bütünlüğü ------------------------------------------------


def test_dokuz_gorev_uc_zorlukta_ve_uc_dilde() -> None:
    """Görev seti sözleşmesi: 9 görev, üç zorluk, üç dil, hepsi eksiksiz."""
    klasorler = sorted(p for p in (OLCUM / "gorevler").iterdir() if p.is_dir())
    assert len(klasorler) == 9, [p.name for p in klasorler]

    zorluklar: dict[str, int] = {}
    diller: set[str] = set()
    for p in klasorler:
        assert (p / "gorev.md").is_file(), f"{p.name}: ham istem yok"
        assert (p / "olcut.py").is_file(), f"{p.name}: puanlayıcı yok"
        m = olcut(p.name)
        zorluklar[m.ZORLUK] = zorluklar.get(m.ZORLUK, 0) + 1
        diller.add(m.DIL)
        assert m.BASLIK and m.ISTEM_YOK is None if hasattr(m, "ISTEM_YOK") else True
    assert zorluklar == {"kolay": 3, "orta": 3, "zor": 3}, zorluklar
    assert diller == {"python", "php", "node"}, diller


def test_ham_istemde_disiplin_telkini_yok() -> None:
    """İstem kullanıcının yazacağı gibi olmalı: "önce test yaz", "doğrula",
    "adım adım plan çıkar" gibi telkinler ölçümü sahteleştirir — ajanın
    kendiliğinden yapıp yapmadığını ölçüyoruz."""
    yasak = ("önce test", "test-driven", "adım adım plan", "doğrulamayı unutma",
             "kendini doğrula", "checklist", "temiz kod ilkeleri")
    for p in sorted((OLCUM / "gorevler").iterdir()):
        if not p.is_dir():
            continue
        metin = (p / "gorev.md").read_text(encoding="utf-8").casefold()
        for kalip in yasak:
            assert kalip not in metin, f"{p.name}: «{kalip}» telkini var"


# -- Eksen / Karne dürüstlüğü -------------------------------------------


def test_olculemeyen_eksen_paydadan_dusuyor() -> None:
    k = puanla.Karne("x", [
        puanla.Eksen("calisir", 40, 40.0),
        puanla.Eksen("kapsam", 25, 25.0),
        puanla.Eksen("saglik", 20, None, sebep="php yok"),
        puanla.Eksen("test", 15, 15.0),
    ])
    assert k.olculen_tavan == 80
    assert k.puan == pytest.approx(100.0)
    assert k.olculemeyen == ["kod sağlığı"]


def test_istenmemis_eksen_puana_katilmiyor_ama_raporlaniyor() -> None:
    e = puanla.Eksen("test", 15, 0.0, harici=True)
    k = puanla.Karne("x", [puanla.Eksen("calisir", 40, 20.0), e])
    assert k.olculen_tavan == 40
    assert k.puan == pytest.approx(50.0)
    assert "istenmedi" in e.yaz()


def test_calisir_olculemediyse_puan_yok() -> None:
    """Taşıyıcı eksen ölçülemediyse ortada puan yoktur.

    Gerçek koşudan gelen kural: ajan kendi `php -S`'ini açık bırakınca ölçüm
    portu tutulu buldu, çalışır/kapsam "ölçülemedi" oldu, geriye yalnız kod
    sağlığı 20/20 kaldı ve normalize puan **100.0** çıktı. Çalıştığını hiç
    göremediğimiz bir teslim tam puan alamaz.
    """
    k = puanla.Karne("z2", [
        puanla.Eksen("calisir", 40, None, sebep="port tutuluydu"),
        puanla.Eksen("kapsam", 25, None, sebep="port tutuluydu"),
        puanla.Eksen("saglik", 20, 20.0),
        puanla.Eksen("test", 15, 0.0, harici=True),
    ])
    assert k.puan is None
    assert k.sozluk()["puan"] is None
    # Çalışır ölçüldüyse, başka bir eksenin ölçülememesi puanı engellemez.
    saglam = puanla.Karne("x", [
        puanla.Eksen("calisir", 40, 40.0),
        puanla.Eksen("saglik", 20, None, sebep="php yok"),
    ])
    assert saglam.puan == pytest.approx(100.0)


def test_hicbir_eksen_olculemezse_puan_none() -> None:
    k = puanla.Karne("x", [puanla.Eksen(ad, tav, None)
                           for ad, tav in puanla.EKSENLER.items()])
    assert k.puan is None
    assert k.sozluk()["puan"] is None


def test_bozuk_teslim_bayragi_calisir_ekseninden_geliyor() -> None:
    bozuk = puanla.Karne("x", [puanla.Eksen("calisir", 40, 0.0)])
    saglam = puanla.Karne("x", [puanla.Eksen("calisir", 40, 1.0)])
    olculemedi = puanla.Karne("x", [puanla.Eksen("calisir", 40, None)])
    assert bozuk.bozuk_teslim
    assert not saglam.bozuk_teslim
    assert not olculemedi.bozuk_teslim, "ölçülemeyen koşu bozuk sayılmaz"


def test_sayac_atlanan_madde_tavandan_da_dusuyor() -> None:
    s = puanla.Sayac()
    s.madde("a", 10, True)
    s.atla("b", "araç yok")
    e = s.eksen("calisir", 40)
    assert e.alinan == pytest.approx(40.0), "atlanan madde puanı seyreltmemeli"
    assert any("ölçülemedi" in k for k in e.kanit)


def test_sayac_hicbir_madde_olcelemezse_eksen_olculemedi() -> None:
    s = puanla.Sayac()
    s.atla("a", "php yok")
    e = s.eksen("calisir", 40)
    assert e.alinan is None and e.sebep


# -- kod sağlığı --------------------------------------------------------


def test_saglik_bos_atolyede_olculemedi(tmp_path: Path) -> None:
    e = puanla.saglik_ekseni(tmp_path)
    assert e.alinan is None and "kaynak dosya yok" in e.sebep


def test_saglik_bozuk_sozdizimini_yakaliyor(tmp_path: Path) -> None:
    (tmp_path / "temiz.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    temiz = puanla.saglik_ekseni(tmp_path)
    (tmp_path / "bozuk.py").write_text("def f(:\n  ???\n", encoding="utf-8")
    bozuk = puanla.saglik_ekseni(tmp_path)
    assert bozuk.alinan is not None and temiz.alinan is not None
    assert bozuk.alinan < temiz.alinan


def test_tekrar_orani_kopyala_yapistiri_goruyor(tmp_path: Path) -> None:
    blok = "\n".join(f"    x{i} = {i} + 1" for i in range(8))
    (tmp_path / "a.py").write_text(f"def a():\n{blok}\n", encoding="utf-8")
    tek, _ = puanla.tekrar_orani([tmp_path / "a.py"])
    (tmp_path / "b.py").write_text(f"def b():\n{blok}\n", encoding="utf-8")
    cift, blok_sayisi = puanla.tekrar_orani(
        [tmp_path / "a.py", tmp_path / "b.py"])
    assert tek == 0.0
    assert cift > 0.3 and blok_sayisi >= 1


# -- test kalitesi ------------------------------------------------------


def test_test_yoksa_gercek_sifir_olculemedi_degil(tmp_path: Path) -> None:
    (tmp_path / "kod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    e = puanla.test_ekseni(tmp_path, kritik=("f",))
    assert e.alinan == 0.0, "bakıldı ve yoktu — bu ölçülemedi değil"


def test_bedava_gecen_iddialar_puani_dusuruyor(tmp_path: Path) -> None:
    iyi = tmp_path / "iyi"
    kotu = tmp_path / "kotu"
    for yer in (iyi, kotu):
        yer.mkdir()
        (yer / "kod.py").write_text("def topla(a, b):\n    return a + b\n",
                                    encoding="utf-8")
    (iyi / "test_kod.py").write_text(
        "from kod import topla\n"
        "def test_bir():\n    assert topla(1, 2) == 3\n"
        "def test_iki():\n    assert topla(-1, 1) == 0\n",
        encoding="utf-8")
    (kotu / "test_kod.py").write_text(
        "def test_bir():\n    assert True\n"
        "def test_iki():\n    assert True\n",
        encoding="utf-8")
    a = puanla.test_ekseni(iyi, kritik=("topla",))
    b = puanla.test_ekseni(kotu, kritik=("topla",))
    assert a.alinan is not None and b.alinan is not None
    assert a.alinan > b.alinan


# -- görev puanlayıcıları: doğru çözüm yüksek, bozuk teslim düşük -------


DOGRU_TCKN = (
    "def dogrula(no):\n"
    "    if not isinstance(no, str) or len(no) != 11 or not no.isdigit():\n"
    "        return False\n"
    "    d = [int(c) for c in no]\n"
    "    if d[0] == 0:\n"
    "        return False\n"
    "    onuncu = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7\n"
    "              - (d[1] + d[3] + d[5] + d[7])) % 10\n"
    "    if onuncu != d[9]:\n"
    "        return False\n"
    "    return sum(d[:10]) % 10 == d[10]\n"
)


def test_k1_dogru_cozum_tam_puana_yakin(tmp_path: Path) -> None:
    m = olcut("k1-modul")
    (tmp_path / "tckn.py").write_text(DOGRU_TCKN, encoding="utf-8")
    (tmp_path / "test_tckn.py").write_text(
        "from tckn import dogrula\n"
        "def test_gecerli():\n    assert dogrula('10000000146') is True\n"
        "def test_gecersiz():\n    assert dogrula('12345678901') is False\n"
        "def test_cop():\n    assert dogrula(None) is False\n",
        encoding="utf-8")
    karne = puanla.Karne("k1", m.olc(tmp_path))
    assert karne.eksen("calisir").alinan == pytest.approx(40.0)
    assert karne.eksen("kapsam").alinan == pytest.approx(25.0)
    assert karne.puan is not None and karne.puan > 80


def test_k1_hic_dosya_yoksa_bozuk_teslim(tmp_path: Path) -> None:
    m = olcut("k1-modul")
    karne = puanla.Karne("k1", m.olc(tmp_path))
    assert karne.bozuk_teslim
    assert karne.puan == pytest.approx(0.0)


def test_k1_yalan_modul_kapsamdan_geciremiyor(tmp_path: Path) -> None:
    """Her şeye True diyen bir modül "çalışıyor" ama kapsamdan geçemez."""
    m = olcut("k1-modul")
    (tmp_path / "tckn.py").write_text("def dogrula(no):\n    return True\n",
                                      encoding="utf-8")
    karne = puanla.Karne("k1", m.olc(tmp_path))
    assert karne.eksen("calisir").alinan == pytest.approx(40.0)
    assert (karne.eksen("kapsam").alinan or 0) < 13, "geçersizleri hiç elemiyor"


@pytest.mark.skipif(not puanla.php_var(), reason="makinede php yok")
def test_k3_duzeltilmis_dosya_tam_puan(tmp_path: Path) -> None:
    m = olcut("k3-tamir")
    tohumla("k3-tamir", tmp_path)
    metin = (tmp_path / "fatura.php").read_text(encoding="utf-8")
    metin = metin.replace("return $tutar + $oran;",
                          "return $tutar * (1 + $oran / 100);")
    metin = metin.replace("count($satirlar) - 1", "count($satirlar)")
    (tmp_path / "fatura.php").write_text(metin, encoding="utf-8")
    karne = puanla.Karne("k3", m.olc(tmp_path))
    assert karne.eksen("kapsam").alinan == pytest.approx(25.0)
    assert karne.puan is not None and karne.puan > 85


@pytest.mark.skipif(not puanla.php_var(), reason="makinede php yok")
def test_k3_dokunulmamis_tohum_kapsamdan_kaliyor(tmp_path: Path) -> None:
    m = olcut("k3-tamir")
    tohumla("k3-tamir", tmp_path)
    karne = puanla.Karne("k3", m.olc(tmp_path))
    # Dosya çalışıyor (çağrılabiliyor) ama hiçbir vaka tutmuyor.
    assert (karne.eksen("calisir").alinan or 0) > 30
    assert (karne.eksen("kapsam").alinan or 0) < 5


def test_z3_dokunulmamis_tohum_regresyondan_gecemiyor(tmp_path: Path) -> None:
    m = olcut("z3-gizli-hata")
    tohumla("z3-gizli-hata", tmp_path)
    karne = puanla.Karne("z3", m.olc(tmp_path))
    assert (karne.eksen("kapsam").alinan or 0) < 6, "üç hata da duruyor"
    kanit = " ".join(karne.eksen("calisir").kanit)
    assert "regresyon takımı tamamen yeşil" in kanit


def test_z3_uc_hata_duzeltilince_yesil(tmp_path: Path) -> None:
    m = olcut("z3-gizli-hata")
    tohumla("z3-gizli-hata", tmp_path)
    yol = tmp_path / "sepet" / "sepet.py"
    metin = yol.read_text(encoding="utf-8")
    metin = metin.replace(
        '    sepet[urun] = {"adet": adet, "fiyat": float(fiyat)}',
        '    varsa = sepet.get(urun)\n'
        '    if varsa:\n'
        '        varsa["adet"] += adet\n'
        '    else:\n'
        '        sepet[urun] = {"adet": adet, "fiyat": float(fiyat)}')
    metin = metin.replace("if tutar > 1000:", "if tutar >= 1000:")
    metin = metin.replace("if tutar > 500:", "if tutar >= 500:")
    metin = metin.replace("return round(net)", "return round(net, 2)")
    yol.write_text(metin, encoding="utf-8")
    karne = puanla.Karne("z3", m.olc(tmp_path))
    assert karne.eksen("kapsam").alinan == pytest.approx(25.0)
    assert karne.eksen("calisir").alinan == pytest.approx(40.0)


def test_z3_testi_gevseterek_puan_alinamiyor(tmp_path: Path) -> None:
    """Kaçamak kapalı: testi silmek regresyonu yeşile çeviremiyor."""
    m = olcut("z3-gizli-hata")
    tohumla("z3-gizli-hata", tmp_path)
    (tmp_path / "sepet" / "test_regresyon.py").write_text(
        "def test_hepsi_iyi():\n    assert True\n", encoding="utf-8")
    karne = puanla.Karne("z3", m.olc(tmp_path))
    kanit = " ".join(karne.eksen("calisir").kanit)
    assert "- regresyon takımı tamamen yeşil" in kanit, kanit


@pytest.mark.skipif(not puanla.node_var(), reason="makinede node yok")
def test_o3_tohum_haliyle_ozellik_yok_ama_regresyon_yesil(tmp_path: Path) -> None:
    m = olcut("o3-ozellik")
    tohumla("o3-ozellik", tmp_path)
    karne = puanla.Karne("o3", m.olc(tmp_path))
    kanit = " ".join(karne.eksen("calisir").kanit)
    assert "+ bozulmamış testler yeşil" in kanit
    assert (karne.eksen("kapsam").alinan or 0) < 8, "ödünç özelliği henüz yok"


# -- sayfa sağlamlığı: bugün kırıldığımız yer ---------------------------


def test_z2_giris_formunun_hedefini_okuyor() -> None:
    """Form nereye gönderiyorsa oraya gönderilmeli; `index.php` varsayımı
    formu `giris.php`'ye yollayan bir paneli haksız yere sıfırlıyordu."""
    m = olcut("z2-panel")
    assert m._hedef('<form method="post" action="giris.php">') == "giris.php"
    assert m._hedef('<form method="post" action="">') == "index.php"
    assert m._hedef('<form method="post">') == "index.php"
    assert m._hedef('<form action="/index.php?git=1">') == "index.php"


def test_z2_alan_adlarini_formdan_cikariyor() -> None:
    m = olcut("z2-panel")
    form = ('<input type="text" name="username">'
            '<input type="password" name="password">')
    assert m._alan_adlari(form) == ("username", "password")
    # Alan bulunamazsa yaygın adlara düşülüyor, patlanmıyor.
    assert m._alan_adlari("<p>form yok</p>") == ("kullanici", "sifre")


def test_sayfa_saglam_200_yetmiyor() -> None:
    dolu = puanla.Yanit(200, "<html>" + "x" * 300 + "</html>", {}, "u")
    bos = puanla.Yanit(200, "<html></html>", {}, "u")
    kazali = puanla.Yanit(
        200, "<html>" + "x" * 300 + "<br />Fatal error: Call to undefined "
        "function baglan() in /panel/ozet.php on line 12</html>", {}, "u")
    uyarili = puanla.Yanit(
        200, "y" * 300 + "Warning: Undefined variable $kullanici", {}, "u")
    assert puanla.sayfa_saglam(dolu)[0]
    assert not puanla.sayfa_saglam(bos)[0]
    assert not puanla.sayfa_saglam(kazali)[0]
    assert not puanla.sayfa_saglam(uyarili)[0]


# -- sayı/sıra yardımcıları ---------------------------------------------


def test_sayi_var_turkce_ve_ingilizce_bicimi_kabul_ediyor() -> None:
    assert puanla.sayi_var("Toplam: 47.553,25 TL", 47553.25)
    assert puanla.sayi_var("Toplam: 47553.25 TL", 47553.25)
    assert puanla.sayi_var("Toplam: 47,553.25 TL", 47553.25)
    # Bir kuruşluk yuvarlama kayması kabul, hesap hatası değil.
    assert puanla.sayi_var("Toplam: 47.553,26 TL", 47553.25)
    assert not puanla.sayi_var("Toplam: 47.553,30 TL", 47553.25)
    assert not puanla.sayi_var("Toplam: 4.755,25 TL", 47553.25)


def test_sayi_var_komsu_satirlari_birbirine_yapistirmiyor() -> None:
    """Çok satırlı raporda her sayı ayrı okunmalı. (Ölçülen yara: ayraç
    sınıfına satır sonu girince "47553.25\\n  2026" tek sayı sanılıyor ve
    doğru rapordaki üç aydan ikisi görünmüyordu.)"""
    metin = ("Aylik ciro:\n  2026-01: 47553.25\n  2026-02: 33938.45\n"
             "  2026-03: 99286.90\n")
    for beklenen in (47553.25, 33938.45, 99286.90):
        assert puanla.sayi_var(metin, beklenen), beklenen


def test_sira_var_sadece_dogru_sirada_geciyor() -> None:
    assert puanla.sira_var("1. Pompa 2. PLC 3. Sensor", ["Pompa", "PLC", "Sensor"])
    assert not puanla.sira_var("1. PLC 2. Pompa 3. Sensor",
                               ["Pompa", "PLC", "Sensor"])


# -- davranış çıkarımı --------------------------------------------------


def gunluk_yaz(yol: Path, olaylar: list[dict]) -> Path:
    yol.write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in olaylar),
                   encoding="utf-8")
    return yol


def test_davranis_dogrulama_izini_kabuktan_okuyor(tmp_path: Path) -> None:
    yol = gunluk_yaz(tmp_path / "o.jsonl", [
        {"seq": 0, "kind": "meta", "content": "session_start", "meta": {}},
        {"seq": 1, "kind": "message", "role": "assistant",
         "content": [{"type": "text", "text": "yazıyorum"}],
         "meta": {"usage": {"prompt_total": 1000, "output": 200}}},
        {"seq": 2, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "write_file", "input": {"path": "a.py"}}},
        {"seq": 3, "kind": "meta", "content": "tool_end",
         "meta": {"tool": "write_file", "error": False}},
        {"seq": 4, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "shell", "input": {"command": "py -m pytest -q"}}},
        {"seq": 5, "kind": "meta", "content": "tool_end",
         "meta": {"tool": "shell", "error": True}},
    ])
    d = davranis.cikar(yol)
    assert d["dogruladi_mi"] is True
    assert any("pytest" in x for x in d["dogrulama_izi"])
    assert d["arac_cagrisi"] == 2
    assert d["hatali_arac"] == 1
    assert d["token_prompt_toplam"] == 1000
    assert d["token_cikti"] == 200


def test_davranis_dogrulamayan_kosuyu_uydurmuyor(tmp_path: Path) -> None:
    yol = gunluk_yaz(tmp_path / "o.jsonl", [
        {"seq": 0, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "write_file", "input": {"path": "a.py"}}},
        {"seq": 1, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "shell", "input": {"command": "mkdir yeni"}}},
    ])
    d = davranis.cikar(yol)
    assert d["dogruladi_mi"] is False
    assert d["dogrulama_izi"] == []
    assert d["token_prompt_toplam"] is None
    assert "ölçülemedi" in d["token_notu"]


def test_davranis_denetle_ve_tarayici_da_dogrulama(tmp_path: Path) -> None:
    yol = gunluk_yaz(tmp_path / "o.jsonl", [
        {"seq": 0, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "denetle", "input": {"path": "panel"}}},
        {"seq": 1, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "browser", "input": {"action": "goto"}}},
    ])
    d = davranis.cikar(yol)
    assert d["dogruladi_mi"] is True
    assert len(d["dogrulama_izi"]) == 2


def test_davranis_plan_yalniz_ilk_aractan_once_sayiliyor(tmp_path: Path) -> None:
    plan = "Şöyle yapacağım:\n1. modülü yaz\n2. testleri yaz\n3. koştur\n"
    once = gunluk_yaz(tmp_path / "a.jsonl", [
        {"seq": 0, "kind": "message", "role": "assistant",
         "content": [{"type": "text", "text": plan}], "meta": {}},
        {"seq": 1, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "write_file", "input": {}}},
    ])
    sonra = gunluk_yaz(tmp_path / "b.jsonl", [
        {"seq": 0, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "write_file", "input": {}}},
        {"seq": 1, "kind": "message", "role": "assistant",
         "content": [{"type": "text", "text": plan}], "meta": {}},
    ])
    assert davranis.cikar(once)["plan_yazdi_mi"] is True
    assert davranis.cikar(sonra)["plan_yazdi_mi"] is False, \
        "iş bittikten sonra yazılan özet plan değildir"


def test_davranis_gunluk_yoksa_cikarilamadi(tmp_path: Path) -> None:
    d = davranis.cikar(tmp_path / "olmayan.jsonl")
    assert "cikarilamadi" in d and "dogruladi_mi" not in d


def test_davranis_kapi_yanitini_tasiyor(tmp_path: Path) -> None:
    yol = gunluk_yaz(tmp_path / "o.jsonl", [
        {"seq": 0, "kind": "meta", "content": "tool_start",
         "meta": {"tool": "shell", "input": {"command": "ls"}}}])
    d = davranis.cikar(yol, kapi={"ok": True, "gecen_sn": 42.5,
                                  "dosyalar": ["a.py", "b.py"]})
    assert d["sure_sn"] == 42.5 and d["degisen_dosya"] == 2 and d["kapi_ok"]


def test_davranis_maliyet_bilinmiyorsa_none(tmp_path: Path) -> None:
    yol = gunluk_yaz(tmp_path / "o.jsonl", [
        {"seq": 0, "kind": "message", "role": "assistant", "content": [],
         "meta": {"usage": {"prompt_total": 500, "output": 100}}}])
    d = davranis.cikar(yol, model_adi="hicbir/katalogda-yok-9999",
                       durum_dizini=tmp_path)
    assert d["maliyet_usd"] is None, "fiyat bilinmiyorsa rakam uydurulmaz"


# -- rapor üretimi ------------------------------------------------------


def test_rapor_olculemedi_ve_gurultu_uyarisini_yaziyor(tmp_path: Path) -> None:
    import kosucu

    karne = puanla.Karne("k1-modul", [
        puanla.Eksen("calisir", 40, 40.0, ["+ tckn.py var (10p)"]),
        puanla.Eksen("kapsam", 25, 12.5, []),
        puanla.Eksen("saglik", 20, None, [], sebep="php yok"),
        puanla.Eksen("test", 15, 3.0, [], harici=True),
    ], davranis={"arac_cagrisi": 7, "dogruladi_mi": False, "kapi_ok": False,
                 "plan_yazdi_mi": True, "maliyet_usd": None})
    sonuc = {
        "zaman": "20260827T000000Z", "model": "deneme/model", "tekrar": 1,
        "gorevler": [{"ad": "k1-modul", "baslik": "B", "zorluk": "kolay",
                      "dil": "python", "ozet": karne.sozluk(),
                      "puan_sapma": None, "bozuk_teslim": 0,
                      "devralindi": ""}],
        "kosulmayan": ["z2-panel"], "eksen_tavanlari": puanla.EKSENLER,
    }
    yol = tmp_path / "RAPOR.md"
    kosucu.rapor_yaz(sonuc, yol)
    metin = yol.read_text(encoding="utf-8")
    assert "ölçülemedi" in metin
    assert "Tek koşu gürültüdür" in metin
    assert "Koşulmadı:** z2-panel" in metin
    assert "12.5" in metin and "3.0*" in metin
    assert "boş bir zihinle" in metin, "izolasyonun sınırı raporda yazmalı"
    assert "Turu bitmeden puanlanan görevler:** k1-modul" in metin, \
        "yarım turu gizlemek puanı olduğundan iyi gösterir"


def test_rapor_devralinan_satiri_isaretliyor(tmp_path: Path) -> None:
    """Tek bir görev yeniden koşulup rapor bütün halinde üretilince, eski
    koşudan gelen satır gizlenmemeli — okuyan hangi rakamın ne zamandan
    olduğunu görmeli."""
    import kosucu

    def satir(ad: str, devralindi: str) -> dict:
        k = puanla.Karne(ad, [puanla.Eksen("calisir", 40, 40.0)],
                         davranis={"kapi_ok": True})
        return {"ad": ad, "baslik": ad, "zorluk": "kolay", "dil": "python",
                "ozet": k.sozluk(), "puan_sapma": None, "bozuk_teslim": 0,
                "devralindi": devralindi}

    yol = tmp_path / "RAPOR.md"
    kosucu.rapor_yaz({
        "zaman": "20260827T120000Z", "model": "m", "tekrar": 1,
        "gorevler": [satir("k1-modul", ""), satir("k2-cli", "20260827T100000Z")],
        "kosulmayan": [], "eksen_tavanlari": puanla.EKSENLER,
    }, yol)
    metin = yol.read_text(encoding="utf-8")
    assert "| k2-cli† |" in metin
    assert "| k1-modul |" in metin
    assert "k2-cli (20260827T100000Z)" in metin


@pytest.mark.skipif(sys.platform != "win32", reason="süreç süpürme Windows'a özgü")
def test_alan_kapaninca_arkada_surec_kalmiyor(tmp_path: Path) -> None:
    """Tur bitince o alana bağlı süreçler de inmeli — ve YALNIZ onlar.

    Eskiden inmiyordu: ajanın `php -S`'i ve neo'nun kendi Chrome'u turdan
    sonra yaşamaya devam ediyordu. Bedeli ölçümdeydi — tutulu port yüzünden
    bir görev SAHTE 100.0 aldı ve Temp'te silinemeyen profil klasörleri
    birikti.
    """
    import subprocess
    import time

    import kosucu

    def _uzun(icinde: str) -> subprocess.Popen:
        # Yol komut satırına HAM geçmeli: `!r` ile kaçırılmış çift ters bölü
        # gerçek durumu (`ornek.py --alan C:\...`) taklit etmez ve süpürgenin
        # deseni tutmaz — bu testi ilk yazışımda yakalanan tuzak buydu.
        return subprocess.Popen(
            [sys.executable, "-c", f'import time; _ = r"{icinde}"; time.sleep(120)'])

    alan = tmp_path / "alan"
    alan.mkdir()
    bagli = _uzun(str(alan))       # komut satırında alanın yolu geçiyor
    yabanci = _uzun("alakasiz")
    try:
        time.sleep(1.5)
        assert bagli.poll() is None and yabanci.poll() is None

        assert kosucu.alani_bosalt(alan) == 1
        time.sleep(1.0)
        assert bagli.poll() is not None, "alana bağlı süreç kapatılmalıydı"
        assert yabanci.poll() is None, "alakasız süreç ASLA kapatılmamalı"

        assert kosucu.alani_bosalt(alan) == 0, "boş alanda sayı sıfır olmalı"
    finally:
        for p in (bagli, yabanci):
            p.kill()


def test_devir_dosyasi_kosudan_once_dogrulaniyor(tmp_path: Path) -> None:
    """`--onceki` yanlışsa bu KOŞUDAN ÖNCE anlaşılmalı.

    Eskiden dosya koşunun sonunda okunuyordu: saatler süren, para harcayan
    bir koşunun ardından "yol yanlış" deyip her şeyi çöpe atıyordu.
    Klasör verilince en yeni koşu seçilir — kullanıcı tarih yazmak zorunda
    kalmasın diye.
    """
    import kosucu

    icerik, hata = kosucu._onceki_oku(tmp_path / "yok.json")
    assert icerik is None and "okunamadı" in hata

    (tmp_path / "bos").mkdir()
    icerik, hata = kosucu._onceki_oku(tmp_path / "bos")
    assert icerik is None and "bulunamadı" in hata

    (tmp_path / "yanlis.json").write_text('{"baska": 1}', encoding="utf-8")
    icerik, hata = kosucu._onceki_oku(tmp_path / "yanlis.json")
    assert icerik is None and "koşu dosyası değil" in hata

    # `yanlis.json` klasörde duruyor ve ada göre sıralamada en sona düşüyor:
    # seçim ada göre yapılsaydı koşu dosyası olmayan bu dosya seçilirdi.
    for zaman in ("20260827T111835Z", "20260827T100000Z"):
        (tmp_path / f"{zaman}-m.json").write_text(
            json.dumps({"zaman": zaman, "gorevler": []}), encoding="utf-8")
    icerik, hata = kosucu._onceki_oku(tmp_path)
    assert hata == "", hata
    assert icerik is not None and icerik["zaman"] == "20260827T100000Z", \
        "klasörden en SON YAZILAN koşu seçilmeli"


def test_haric_dosyalar_olcumden_dusuyor(tmp_path: Path) -> None:
    """Açılışta atölyeye konan ve ajanın DOKUNMADIĞI dosyalar kod sağlığına
    girmemeli; dokunduğu dosya girmeli."""
    import kosucu

    yetenek = tmp_path / "yetenekler"
    yetenek.mkdir()
    (yetenek / "pdf_uret.py").write_text(
        "def run(a, c):\n" + "".join(
            f"{'    ' * (i + 1)}if a.get('{i}'):\n" for i in range(8))
        + "        " * 4 + "    return 1\n", encoding="utf-8")
    tohum = tmp_path / "tohum_kod.py"
    tohum.write_text("def eski():\n    return 1\n", encoding="utf-8")

    onceki = kosucu.parmak_izi(tmp_path)
    # Ajan turu: kendi dosyasını yazıyor, tohumu düzenliyor, yeteneğe dokunmuyor.
    (tmp_path / "benim.py").write_text("def yeni():\n    return 2\n",
                                       encoding="utf-8")
    tohum.write_text("def eski():\n    return 42\n", encoding="utf-8")

    assert kosucu.haric_yaz(tmp_path, onceki) == 1
    kalanlar = {p.name for p in puanla.kaynaklar(tmp_path)}
    assert kalanlar == {"benim.py", "tohum_kod.py"}, kalanlar
