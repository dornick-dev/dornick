"""Gece geçişi — tekrar, sorumluluk, dikiş, örgü, küçültme.

Night school bugüne kadar *eğitim* yapıyordu; *tekrar* yapmıyordu. Beynin
gece yaptığı asıl iş günün dizilerini yeniden oynatmak, ve bundan çıkan
şeylerin hiçbiri dornick'te yoktu:

* kenarların tamamı "benzer içerik" — **birlikte yaşandı** bağı yok;
* `uses` sayacı yanlış cevaba götüren hatıraya da doğru cevaba götürene de
  aynı puanı veriyor — sorumluluk atama yok;
* `_weave` yazım anında donuyor, ağ sıraya bağımlı;
* gündüz güçlenen hiçbir şey küçülmüyor, kenarlar şişiyor.

Buradaki testler bu beş adımın her birini ayrı ayrı zorluyor. Adım 6
(damıtma) ayrı PR; burada yalnız **kapısı** test ediliyor: model yoksa
atlanıyor ve ilk beş adım yine koşuyor.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dornick.events import EventLog
from dornick.recall import activation as A
from dornick.recall import open_store, weave

SIMDI = datetime(2025, 6, 2, 9, 0, tzinfo=timezone.utc)   # pazartesi


class Takvim:
    def __init__(self, an: datetime) -> None:
        self.an = an

    def __call__(self) -> datetime:
        return self.an

    def ilerle(self, **delta) -> None:
        self.an += timedelta(**delta)

    def metin(self) -> str:
        return self.an.isoformat(timespec="milliseconds")


@pytest.fixture()
def takvim() -> Takvim:
    return Takvim(SIMDI)


@pytest.fixture()
def store(tmp_path: Path, takvim: Takvim):
    s = open_store(tmp_path / "bellek", clock=takvim)
    yield s
    s.close()


@pytest.fixture()
def oturumlar(tmp_path: Path) -> Path:
    yol = tmp_path / "sessions"
    yol.mkdir(parents=True, exist_ok=True)
    return yol


@pytest.fixture()
def watermark(tmp_path: Path) -> Path:
    return tmp_path / "filigran.json"


class Gunluk:
    """Bir oturumun olay günlüğünü yazan yardımcı — ürünün kendi EventLog'u."""

    def __init__(self, dizin: Path, oturum: str, takvim: Takvim) -> None:
        self.log = EventLog(dizin / f"{oturum}.jsonl", clock=takvim.metin)
        self.log.note("session_start", session_id=oturum)
        self.takvim = takvim

    def dokun(self, node_id: str, olay: str = "mind_open", **meta) -> Gunluk:
        self.takvim.ilerle(minutes=1)
        self.log.note(olay, memory_id=node_id, **meta)
        return self

    def arac(self, ad: str, *, hata: bool = False, ozet: str = "") -> Gunluk:
        self.takvim.ilerle(minutes=1)
        self.log.note("tool_start", tool=ad, input={})
        self.log.note("tool_end", tool=ad, error=hata, ms=10, ozet=ozet)
        return self

    def kapat(self, sonuc: str = "basarili") -> Gunluk:
        self.takvim.ilerle(minutes=1)
        self.log.note("sonuc", sonuc=sonuc)
        self.log.close()
        return self


def _gece(store, oturumlar, watermark, takvim, **kw):
    return weave.night_pass(store, oturumlar, clock=takvim, watermark=watermark, **kw)


# -- Adım 2: zaman komşuluğu -------------------------------------------


def test_ayni_oturumda_pes_pese_kullanilan_ikili_baglaniyor(
        store, oturumlar, watermark, takvim) -> None:
    """"O raporu yaparken kullandığım şey neydi" içerik aramasıyla bulunamaz."""
    a = store.remember("Vardiya raporu şablonu üç sayfalı bir Excel dosyası.",
                       kind="fact")
    b = store.remember("Kırmızı defterin arkasında modem PIN kodu yazıyor.",
                       kind="fact")
    Gunluk(oturumlar, "s1", takvim).dokun(a.id).dokun(b.id).kapat()

    rapor = _gece(store, oturumlar, watermark, takvim)
    assert rapor.new_edges >= 1

    komsular = {n.id: r for n, _w, r in store.neighbours_with_reasons(a.id)}
    assert b.id in komsular
    assert "birlikte kullanıldı" in komsular[b.id]


def test_zaman_komsulugu_prime_a_sizmiyor(store, oturumlar, watermark, takvim) -> None:
    """Kenar açık aramayı zenginleştirir, otomatik enjeksiyonu kirletmez."""
    from dornick.loop import select_prime
    from dornick.mind import open_mind

    a = store.remember("Vardiya raporu şablonu üç sayfalı Excel dosyası.", kind="fact")
    b = store.remember("Kırmızı defterin arkasında modem PIN kodu yazıyor.", kind="fact")
    Gunluk(oturumlar, "s1", takvim).dokun(a.id).dokun(b.id).kapat()
    _gece(store, oturumlar, watermark, takvim)

    mind = open_mind(store.path.parent, oturumlar, "t", clock=takvim)
    try:
        hits = select_prime(mind, "Vardiya raporu şablonu kaç sayfaydı?", limit=5)
        assert b.id not in {h.item.id for h in hits}
        acik = {h.item.id for h in mind.recall("Vardiya raporu şablonu", limit=5)}
        assert b.id in acik
    finally:
        mind.store.close()


def test_tekrarlanan_birliktelik_kenari_guclendiriyor(
        store, oturumlar, watermark, takvim) -> None:
    """Sıkça birlikte kullanılan şeyler güçlü bağlanmalı; max'ta donmamalı."""
    a = store.remember("Terfi istasyonu yolu yağmurda çamur oluyor.", kind="fact")
    orta = store.remember("Kırtasiye siparişi perşembe verilir.", kind="fact")
    b = store.remember("Faturalar muhasebeye ayın yirmisinde gönderiliyor.",
                       kind="fact")

    def _agirlik() -> float:
        return dict((n.id, w) for n, w, _r in store.neighbours_with_reasons(a.id))[b.id]

    # Uzaklığı iki olan çift ölçülüyor: bitişik çift 0.6'dan başlıyor ve
    # ağırlık tavanı 1.0 — "iki katı" orada matematiksel olarak imkânsız.
    Gunluk(oturumlar, "tek", takvim).dokun(a.id).dokun(orta.id).dokun(b.id).kapat()
    _gece(store, oturumlar, watermark, takvim)
    tek_seferlik = _agirlik()

    for i in range(4):
        takvim.ilerle(days=1)
        (Gunluk(oturumlar, f"tekrar{i}", takvim)
         .dokun(a.id).dokun(orta.id).dokun(b.id).kapat())
        _gece(store, oturumlar, watermark, takvim)

    assert _agirlik() > tek_seferlik * 2


# -- Adım 2b: şema tazelemesi ------------------------------------------


def test_kullanilanin_komsusu_tazeleniyor(store, oturumlar, watermark, takvim) -> None:
    """Eskinin pekişmesi taramayla değil, şemaya bağlı olmakla geliyor."""
    x = store.remember("Terfi hattı basınç sınırı altı bar.", kind="fact")
    y = store.remember("Terfi hattı basıncı manometreden okunuyor.", kind="fact")
    w = store.remember("Kapı kilidi silindirli.", kind="fact")
    store.link(x.id, y.id, weight=0.8, reason="benzer icerik")

    takvim.ilerle(days=30)
    Gunluk(oturumlar, "s1", takvim).dokun(y.id).kapat()
    _gece(store, oturumlar, watermark, takvim)

    assert any(k.etiket == A.SCHEMA for k in store.use_log(x.id))
    assert not any(k.etiket == A.SCHEMA for k in store.use_log(w.id))


def test_sema_tazelemesi_aktivasyonu_yukseltiyor(
        store, oturumlar, watermark, takvim) -> None:
    x = store.remember("Dozaj tankı kapasitesi bin litre.", kind="fact")
    y = store.remember("Dozaj tankı seviyesi haftalık kontrol ediliyor.", kind="fact")
    kontrol = store.remember("Merdiven korkuluğu galvanizli.", kind="fact")
    store.link(x.id, y.id, weight=0.8, reason="benzer icerik")

    takvim.ilerle(days=30)
    Gunluk(oturumlar, "s1", takvim).dokun(y.id).kapat()
    _gece(store, oturumlar, watermark, takvim)

    assert store.peek(x.id).activation > store.peek(kontrol.id).activation


# -- Adım 3: ters tekrar -----------------------------------------------


def test_basariya_goturen_hatira_hataya_goturenin_ustunde(
        store, oturumlar, watermark, takvim) -> None:
    iyi = store.remember("Gate servisi yeniden başlatılırken kuyruk boşaltılıyor.",
                         kind="procedure")
    kotu = store.remember("Gate servisi doğrudan kill ile durduruluyor.",
                          kind="procedure")
    Gunluk(oturumlar, "ok", takvim).dokun(iyi.id).arac("kos").kapat("basarili")
    takvim.ilerle(days=1)
    Gunluk(oturumlar, "hata", takvim).dokun(kotu.id).arac(
        "kos", hata=True, ozet="3 test kırıldı").kapat("basarisiz")

    _gece(store, oturumlar, watermark, takvim)

    sonuc = store.recall("Gate servisi yeniden başlatma", limit=8)
    sirali = [n.id for n in sonuc.hits]
    assert sirali.index(iyi.id) < sirali.index(kotu.id)
    assert store.track_record(iyi.id) == (1, 0)
    assert store.track_record(kotu.id) == (0, 1)


def test_hataya_goturen_yolun_yaninda_ders_duruyor(
        store, oturumlar, watermark, takvim) -> None:
    kotu = store.remember("Şema göçü doğrudan üretimde koşuluyor.", kind="procedure")
    Gunluk(oturumlar, "hata", takvim).dokun(kotu.id).arac(
        "kos", hata=True, ozet="göç yarıda kaldı").kapat("basarisiz")
    rapor = _gece(store, oturumlar, watermark, takvim)

    assert rapor.lessons_written >= 1
    dersler = [n for n in store.by_kind("lesson", limit=10)]
    assert dersler
    assert kotu.id in {n.id for n, _w, _r in store.neighbours_with_reasons(dersler[0].id)}


def test_basarili_dizi_yordam_yaziyor(store, oturumlar, watermark, takvim) -> None:
    ucu = [store.remember(f"Adım {i}: saha kontrolü {i}.", kind="fact")
           for i in range(3)]
    g = Gunluk(oturumlar, "ok", takvim)
    for n in ucu:
        g.dokun(n.id)
    g.arac("kos").arac("dosya_yaz").kapat("basarili")

    rapor = _gece(store, oturumlar, watermark, takvim)
    assert rapor.procedures_written >= 1


def test_karisik_sicil_hic_dokunulmamistan_guclu(
        store, oturumlar, watermark, takvim) -> None:
    kayit = store.remember("Bellek sızıntısı tracemalloc ile bulunuyor.",
                           kind="procedure")
    bakir = store.remember("Priz grubu topraklı tip.", kind="fact")
    for i in range(3):
        takvim.ilerle(days=1)
        Gunluk(oturumlar, f"ok{i}", takvim).dokun(kayit.id).kapat("basarili")
    takvim.ilerle(days=1)
    Gunluk(oturumlar, "hata", takvim).dokun(kayit.id).arac(
        "kos", hata=True, ozet="patladı").kapat("basarisiz")
    _gece(store, oturumlar, watermark, takvim)

    assert store.track_record(kayit.id) == (3, 1)
    assert store.peek(kayit.id).activation > store.peek(bakir.id).activation


def test_acik_hedef_kaldigin_yeri_yaziyor(store, oturumlar, watermark, takvim) -> None:
    a = store.remember("Kurulum paketi imzalanacak.", kind="fact")
    Gunluk(oturumlar, "acik", takvim).dokun(a.id).kapat("acik")
    _gece(store, oturumlar, watermark, takvim)
    assert store.by_kind("goal", limit=5)


# -- Adım 4: dikiş -----------------------------------------------------


def test_hic_yasanmamis_dizi_dikiliyor(store, oturumlar, watermark, takvim) -> None:
    """Pazartesi A→B, perşembe B→C. A ile C hiç birlikte yaşanmadı."""
    # Dolgu: küçük bir bellekte `_weave` her şeyi birbirine bağlar ve
    # dikilecek bir boşluk kalmaz. Gerçek bir bellekte durum bu değildir.
    for metin in ("Kırtasiye siparişi perşembe veriliyor.",
                  "Ofis bitkileri haftada iki kez sulanıyor.",
                  "Kapı zilinin pili bitmek üzere.",
                  "Yemek kartı her ayın ilk günü yükleniyor.",
                  "Asansör bakımı her çeyrekte yapılıyor.",
                  "Yazıcı kartuşu uyumlu marka alınıyor."):
        store.remember(metin, kind="fact")
    a = store.remember("Karatay deposu seviye ölçümü saatte bir alınıyor.", kind="fact")
    b = store.remember("Ölçüm verisi gece yarısı özetleniyor.", kind="fact")
    c = store.remember("Bordro dosyası muhasebeye kapalı zarfla veriliyor.",
                       kind="fact")
    assert c.id not in {n.id for n, _w, _r in store.neighbours_with_reasons(a.id)}
    Gunluk(oturumlar, "pzt", takvim).dokun(a.id).dokun(b.id).kapat()
    takvim.ilerle(days=1)
    Gunluk(oturumlar, "prs", takvim).dokun(b.id).dokun(c.id).kapat()

    rapor = _gece(store, oturumlar, watermark, takvim)
    assert rapor.dikis >= 1

    gerekceler = {n.id: r for n, _w, r in store.neighbours_with_reasons(a.id)}
    assert c.id in gerekceler
    assert b.id in gerekceler[c.id]          # üzerinden dikilen düğüm yazılı


# -- Adım 5: örgü ve küçültme ------------------------------------------


def test_dokunulmayan_kenar_her_gece_eriyor(store, oturumlar, watermark, takvim) -> None:
    a = store.remember("Kavanoz kapakları paslanıyor.", kind="fact")
    b = store.remember("Ütü masasının ayağı gevşek.", kind="fact")
    store.link(a.id, b.id, weight=1.0, reason="elle")
    onceki = dict((n.id, w) for n, w, _r in store.neighbours_with_reasons(a.id))[b.id]

    for i in range(20):
        takvim.ilerle(days=1)
        _gece(store, oturumlar, watermark, takvim)
    sonraki = dict((n.id, w) for n, w, _r in store.neighbours_with_reasons(a.id))[b.id]

    beklenen = onceki * (1 - weave.EPSILON) ** 20
    assert sonraki == pytest.approx(beklenen, rel=0.05)


def test_taban_altina_inen_kenar_siliniyor(store, oturumlar, watermark, takvim) -> None:
    """Kenar silinebilir, düğüm silinemez: kenar bilgi değil yol."""
    a = store.remember("Semt pazarı perşembe kuruluyor.", kind="fact")
    b = store.remember("Sokak lambası akşamları geç yanıyor.", kind="fact")
    store.link(a.id, b.id, weight=weave.EDGE_FLOOR + 0.001, reason="zayıf")
    takvim.ilerle(days=1)
    rapor = _gece(store, oturumlar, watermark, takvim)

    assert rapor.edges_removed >= 1
    assert b.id not in {n.id for n, _w, _r in store.neighbours_with_reasons(a.id)}
    assert store.peek(a.id) is not None and store.peek(b.id) is not None


def test_her_gece_dokunulan_kenar_tabanin_ustunde_kaliyor(
        store, oturumlar, watermark, takvim) -> None:
    a = store.remember("Jeneratör otomatiği el konumunda bırakılmamalı.", kind="fact")
    b = store.remember("Toplantı odası projektörü HDMI ile çalışıyor.", kind="fact")
    for i in range(20):
        takvim.ilerle(days=1)
        Gunluk(oturumlar, f"g{i}", takvim).dokun(a.id).dokun(b.id).kapat()
        _gece(store, oturumlar, watermark, takvim)
    agirlik = dict((n.id, w) for n, w, _r in store.neighbours_with_reasons(a.id))[b.id]
    assert agirlik > weave.EDGE_FLOOR * 3


def test_yeniden_orgu_sira_bagimliligini_kiriyor(tmp_path: Path) -> None:
    """Aynı yüz düğüm ters sırada yazılınca da benzer bir ağ çıkmalı."""
    govdeler = [f"Saha notu {i}: pompa {i} bakım kaydı ve ölçüm sonucu." % ()
                for i in range(40)]

    def _ag(sira: list[str], ad: str) -> set[tuple[str, str]]:
        takvim = Takvim(SIMDI)
        st = open_store(tmp_path / ad, clock=takvim)
        oturum_dizin = tmp_path / f"{ad}-oturum"
        oturum_dizin.mkdir(parents=True, exist_ok=True)
        try:
            kimlik = {}
            for govde in sira:
                kimlik[govde] = st.remember(govde, kind="fact").id
            for i in range(5):
                takvim.ilerle(days=1)
                g = Gunluk(oturum_dizin, f"g{i}", takvim)
                for govde in sira[i * 8:(i + 1) * 8]:
                    g.dokun(kimlik[govde])
                g.kapat()
                weave.night_pass(st, oturum_dizin, clock=takvim,
                                 watermark=tmp_path / f"{ad}.json")
            ters = {v: k for k, v in kimlik.items()}
            return {tuple(sorted((ters[a], ters[b])))
                    for a, b, _w in st.links(limit=5000)}
        finally:
            st.close()

    duz = _ag(govdeler, "duz")
    ters = _ag(list(reversed(govdeler)), "ters")
    ortusme = len(duz & ters) / max(len(duz | ters), 1)
    assert ortusme >= 0.5, f"örtüşme {ortusme:.2f}"


# -- öncelik, bütçe, filigran ------------------------------------------


def test_basarisiz_oturum_rutinden_once_tekrar_ediliyor(
        store, oturumlar, watermark, takvim) -> None:
    a = store.remember("Rutin saha notu.", kind="fact")
    b = store.remember("Göç sırasında veri kayboldu.", kind="fact")
    Gunluk(oturumlar, "rutin", takvim).dokun(a.id).kapat("basarili")
    Gunluk(oturumlar, "kotu", takvim).dokun(b.id).arac(
        "kos", hata=True, ozet="kırıldı").kapat("basarisiz")

    sirali = weave.prioritised_sessions(store, oturumlar, clock=takvim, watermark=watermark)
    assert sirali[0].id == "kotu"


def test_butce_bitince_kalan_oturumlar_devrediyor(
        store, oturumlar, watermark, takvim) -> None:
    """Kalanlar atlanmıyor, bir sonraki geceye geçiyor."""
    for i in range(6):
        n = store.remember(f"Saha kaydı {i}.", kind="fact")
        Gunluk(oturumlar, f"s{i}", takvim).dokun(n.id).kapat()

    rapor = _gece(store, oturumlar, watermark, takvim, budget_s=0.0)
    assert rapor.devreden > 0
    assert rapor.replayed <= 1          # ilk birim yine de tamamlanır

    ikinci = _gece(store, oturumlar, watermark, takvim, budget_s=300.0)
    assert ikinci.replayed >= rapor.devreden - 1


def test_islenen_oturum_ikinci_gece_tekrar_edilmiyor(
        store, oturumlar, watermark, takvim) -> None:
    """Çift sayım yok: aynı oturum iki kez pay dağıtmamalı."""
    n = store.remember("Kurulum paketi imzalandı.", kind="fact")
    Gunluk(oturumlar, "s1", takvim).dokun(n.id).kapat("basarili")
    _gece(store, oturumlar, watermark, takvim)
    ilk_sicil = store.track_record(n.id)

    takvim.ilerle(days=1)
    ikinci = _gece(store, oturumlar, watermark, takvim)
    assert ikinci.replayed == 0
    assert store.track_record(n.id) == ilk_sicil


def test_filigran_diske_yaziliyor(store, oturumlar, watermark, takvim) -> None:
    n = store.remember("Bir kayıt.", kind="fact")
    Gunluk(oturumlar, "s1", takvim).dokun(n.id).kapat()
    _gece(store, oturumlar, watermark, takvim)
    status = json.loads(watermark.read_text(encoding="utf-8"))
    assert "s1" in status["islenen"]


def test_kapanmamis_oturum_tekrar_edilmiyor(store, oturumlar, watermark, takvim) -> None:
    """Sonucu olmayan oturum kaynak değil: hâlâ sürüyor olabilir."""
    n = store.remember("Yarım kalan iş.", kind="fact")
    Gunluk(oturumlar, "acik", takvim).dokun(n.id)      # kapat() yok
    rapor = _gece(store, oturumlar, watermark, takvim)
    assert rapor.replayed == 0


# -- geriye dönük yakalama ---------------------------------------------


def test_surprizli_olayin_yanindaki_sakin_kayit_yakalaniyor(
        store, oturumlar, watermark, takvim) -> None:
    # Sıradan olmak bir bağlam işi: benzerleri olmayan kayıt sürprizlidir.
    for metin in ("Sabah kahvesi mutfakta içildi.",
                  "Sabah kahvesi bahçede içildi.",
                  "Sabah kahvesi toplantıda içildi."):
        store.remember(metin, kind="fact")
    sakin = store.remember("Sabah kahvesi ofiste içildi.", kind="fact")
    takvim.ilerle(minutes=10)
    surprizli = store.remember(
        "Ana pano yandı; bütün saha elektriksiz kaldı ve üretim durdu.",
        kind="lesson")
    g = Gunluk(oturumlar, "s1", takvim)
    g.dokun(sakin.id).dokun(surprizli.id).kapat("basarisiz")
    _gece(store, oturumlar, watermark, takvim)

    assert any(k.etiket == A.CAPTURED for k in store.use_log(sakin.id))


def test_uzaktaki_kayit_yakalanmiyor(store, oturumlar, watermark, takvim) -> None:
    """±60 dakika bir sınır, bir slogan değil."""
    for metin in ("Yeni kalem kutusu rafa kondu.", "Yeni kalem kutusu çekmeceye kondu.",
                  "Yeni kalem kutusu dolaba kondu."):
        store.remember(metin, kind="fact")
    uzak = store.remember("Yeni kalem kutusu masaya kondu.", kind="fact")
    takvim.ilerle(minutes=200)
    surprizli = store.remember(
        "Veritabanı bozuldu; son iki günün ölçümü kayboldu.", kind="lesson")
    g = Gunluk(oturumlar, "s1", takvim)
    g.dokun(uzak.id)
    takvim.ilerle(minutes=200)
    g.dokun(surprizli.id).kapat("basarisiz")
    _gece(store, oturumlar, watermark, takvim)

    assert not any(k.etiket == A.CAPTURED for k in store.use_log(uzak.id))


# -- damıtma kapısı (Adım 6 ayrı PR) -----------------------------------


def test_model_yoksa_damitma_atlaniyor_ama_gece_kosuyor(
        store, oturumlar, watermark, takvim) -> None:
    a = store.remember("Bir kayıt.", kind="fact")
    b = store.remember("Başka bir kayıt.", kind="fact")
    Gunluk(oturumlar, "s1", takvim).dokun(a.id).dokun(b.id).kapat()
    rapor = _gece(store, oturumlar, watermark, takvim, model=None)
    assert "atlandı" in rapor.distillation
    assert rapor.replayed == 1          # ilk beş adım yine koştu


# -- ablation ----------------------------------------------------------


def test_orgu_kapaliyken_gece_hicbir_kenar_yazmiyor(
        store, oturumlar, watermark, takvim) -> None:
    from dornick.recall import switches

    a = store.remember("Pano etiketleri Brother ile basılıyor.", kind="fact")
    b = store.remember("Ofis bitkileri haftada iki kez sulanıyor.", kind="fact")
    Gunluk(oturumlar, "s1", takvim).dokun(a.id).dokun(b.id).kapat()
    with switches.disabled("weave"):
        rapor = _gece(store, oturumlar, watermark, takvim)
    assert rapor.replayed == 0
    assert b.id not in {n.id for n, _w, _r in store.neighbours_with_reasons(a.id)}
