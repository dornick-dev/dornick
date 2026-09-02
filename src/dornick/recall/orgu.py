"""Gece geçişi — günün dizilerini yeniden oynatmak.

Night school bugüne kadar *eğitim* yapıyordu: taban yazıcıyı kişisel korpusla
ince ayarlıyordu. *Tekrar* yapmıyordu. Oysa beynin gece yaptığı asıl iş
günün dizilerini yeniden oynatmak (sharp-wave ripple), ve bundan çıkan
şeylerin hiçbiri dornick'te yoktu:

1. Kenarların tamamı "benzer içerik" — **birlikte yaşandı** bağı yok.
   "Geçen hafta o raporu yaparken kullandığım şey neydi" içerik aramasıyla
   bulunamaz; o soru zamansal bir soru.
2. `uses` sayacı ayrım yapmıyor: yanlış cevaba götüren hatıra da doğru
   cevaba götüren de bir puan alıyor. **Sorumluluk atama** yok.
3. Tekrar önceliksiz: tetik "25 yeni anı birikti mi". Başarısız oturum,
   açık hedef, düzeltme turu rutin oturumla aynı muameleyi görüyor.
4. `_weave` yazım anında donuyor; ağ yazım sırasına bağımlı, erken kayıtlar
   zayıf bağlı kalıyor.
5. Gündüz güçlenen hiçbir şey küçülmüyor. Kenarlar şişiyor, `_weave`
   komşuları gürültüleniyor.

Altı adım var ve **ilk beşi model gerektirmez** — saf Python + SQLite.
Modeli olmayan bir kurulumda bile gece anlamlı iş yapar; damıtma (6. adım)
yalnızca yerel model varsa koşar.

Atomik birim tek bir oturumun tekrarıdır: bütçe biterse kalanlar atlanmaz,
bir sonraki geceye **devreder**. Filigran oturum bazında tutulur, böylece
yarıda kesilen bir gece iş kaybetmez ve tamamlanmış bir oturum ikinci kez
pay dağıtmaz.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

from . import aktivasyon, anahtar
from .saat import Saat, coz, duvar_saati

# Adım 1 — Mattar-Daw: kazanç × ihtiyaç. Başarısız ve düzeltilen oturumlar
# en çok öğreteceklerdir; rutin bir oturumdan öğrenilecek şey azdır.
KAZANC = {"basarisiz": 1.0, "duzeltildi": 1.0, "acik": 0.7,
          "basarili": 0.4, "rutin": 0.1}

# Rutin sayılmanın sınırı: araç hatası yok, hedef yok, düzeltme yok ve
# bu kadar az tur.
RUTIN_TUR = 3

# Tekrar penceresi: filigrandan beri kapanan oturumlar her zaman aday.
# Önceki bu kadar günün oturumları da aday ama önceliği yarılanarak düşer
# ve yalnız bütçe artarsa sıraya girer. Daha eskisi taranmaz — eskinin
# pekişmesi tarama ile değil şema tazelemesiyle olur.
GERIYE_GUN = 7
GERIYE_SONUMU = 0.5

# Adım 2 — zaman komşuluğu penceresi ve ağırlığı. Komşu 0.6, iki ötesi 0.42.
PENCERE = 4
KOMSULUK_AGIRLIK = 0.6
KOMSULUK_SONUMU = 0.7

# Adım 2b — şemaya bağlı komşunun aldığı tazeleme payı. Bir sıçrama; ötesi
# Faz 1 bozunmasına bırakılıyor.
SEMA_PAYI = 0.15

# Adım 3 — sorumluluk payları. Sonuca yakın olan çok alır.
# Kalibrasyon (yaşam bench, 2026-09-03): (0.5, -0.3) / (0.7, -0.5) /
# (0.5, -0.6) / (1.0, -0.8) tarandı. `sorumluluk_dogrulugu` yalnız sonuncuda
# hedefi geçiyor: 0.75 → 1.00. Yol haritasının önerdiği (0.5, -0.3) çifti
# çok zayıf — tek bir başarı/hata payı, kaydın kendi tazeliğinin altında
# kalıyor ve sıralamayı çeviremiyor. Diğer metrikler bu aralıkta duyarsız
# (precision 0.2758–0.2773).
PAY_SONUMU = 0.8
BASARI_PAYI = 1.0
HATA_PAYI = -0.8

# Adım 1 — geriye dönük yakalama (synaptic tagging and capture): yüksek
# sürprizli bir olayın ±60 dakikasındaki sıradan kayıtlar da pekişir.
# Zayıf iz, güçlü olayın yanında durduğu için kurtulur.
#
# Kalibrasyon DENENDİ ve SONUÇSUZ kaldı (yaşam bench, 2026-09-03): eşik
# 0.35'ten 0.70'e taranınca `yakalama` metriği hiç oynamadı (-0.108 sabit).
# Sebep ölçüldü: beş yüz düğümlük bir bellekte "sabah kahvesi içildi"nin
# sürprizi 0.389, "ana pano yandı, saha elektriksiz kaldı"nınki 0.422.
# Sürpriz vekili (1 − en yakın komşu skoru) bu ölçekte sıradan ile felaketi
# ayırt edemiyor; ayıramayan bir sinyalin eşiği de ayarlanamaz. Yol
# haritasının başlangıç değeri korundu ve bulgu rapora yazıldı — Faz 4'ün
# kodlama gücü aynı vekile dayanıyor, aynı duvara çarpması beklenir.
YAKALAMA_ESIK = 0.7
YAKALAMA_DAKIKA = 60
YAKALAMA_PAYI = 0.3

# Adım 5a — yeniden örgü: kaç aday çekilip kaçına bağlanılacağı.
ORGU_ADAY = 6
ORGU_BAGLANTI = 3

# Adım 5b — sinaptik homeostaz (Tononi-Cirelli): gündüz güçlenen her şey
# gece orantılı küçülür. Dokunulmayan kenar her gece bu oranda erir;
# %2 ile ~35 gecede yarıya, ~150 gecede tabana iner. Bu gece güçlenen
# kenarlar küçültmeden önce büyüdüğü için net kazançlı.
# Kalibrasyon: docs/hafiza-fazlar.md "Faz 3 kalibrasyonu".
EPSILON = 0.02
KENAR_TABAN = 0.05

# Faz 3.11 — sıcak/soğuk sınırı. Bu aktivasyonun altındaki (ve yedi günden
# eski) kayıt imza indeksinden düşüyor: kendiliğinden gelmiyor ama birebir
# kelimeyle hâlâ bulunuyor.
#
# Kalibrasyon hedefi yol haritasında sayı olarak değil ORAN olarak veriliyor:
# doksan günlük senaryoda sıcak oran %10-30 arasında kalmalı. Tarama
# (2026-09-03): -2.0 → %2.9 · -3.0 → %4.5 · -4.0 → %6.5 · **-5.0 → %25.2** ·
# -6.0 → %69 · -7.0 → %98.5. Banda düşen tek değer -5.0.
# Yan etki ölçüldü ve beklenendir: soğuk kayıt önyüklemeye giremediği için
# tuzak sessizliği 0.45 → 0.525'e çıkıyor, prime recall 0.99 → 0.75'e
# düşüyor. İkincisi mekaniğin amacının doğrudan sonucu, kusuru değil.
SOGUK_ESIK = -5.0


@dataclass(slots=True)
class Oturum:
    """Bir oturumun geceye taşınan özeti."""

    id: str
    dizi: list[str] = field(default_factory=list)
    damgalar: dict[str, datetime] = field(default_factory=dict)
    sonuc: str = ""
    araclar: list[str] = field(default_factory=list)
    hata_metni: str = ""
    hedef_acik: bool = False
    duzeltme: bool = False
    turlar: int = 0
    bitis: datetime | None = None
    oncelik: float = 0.0
    # Uyanık tekrar (recall/awake.py) bu oturumun sorumluluğunu sonuç anında
    # dağıttıysa gece onu bir daha dağıtmaz: bir başarı iki `basari` girdisi
    # bırakmamalı. İleri tekrar ve dikiş yine koşar — ikisi de birikimli
    # değil, tekrarı zararsız.
    ters_tekrar_kostu: bool = False
    ileri_tekrar_indeksi: int = 0

    @property
    def kapali(self) -> bool:
        return bool(self.sonuc)

    def kazanc_sinifi(self) -> str:
        if self.sonuc in ("basarisiz", "duzeltildi", "acik"):
            return self.sonuc
        if (not self.hata_metni and not self.hedef_acik and not self.duzeltme
                and self.turlar <= RUTIN_TUR):
            return "rutin"
        return self.sonuc or "rutin"


@dataclass(slots=True)
class GeceRaporu:
    """Gecenin ne yaptığı. `.dornick/gece.jsonl`'a yazılır; arayüz okur."""

    oturum_sayisi: int = 0
    tekrar_edilen: int = 0
    devreden: int = 0
    yeni_kenar: int = 0
    sema_dokunusu: int = 0
    yakalanan: int = 0
    basari_payi: int = 0
    hata_payi: int = 0
    yazilan_ders: int = 0
    yazilan_yordam: int = 0
    yazilan_hedef: int = 0
    damitik: int = 0
    isinan: int = 0
    soguyan: int = 0
    celiski: int = 0
    geri_alinan: int = 0
    dikis: int = 0
    orgu_kenari: int = 0
    kuculen_kenar: int = 0
    silinen_kenar: int = 0
    damitma: str = ""
    sure_sn: float = 0.0

    def sozluk(self) -> dict[str, Any]:
        return asdict(self)


# -- giriş noktası -----------------------------------------------------


def gece_gecisi(
    store: Any,
    sessions_dir: Path,
    *,
    saat: Saat | None = None,
    filigran: Path | None = None,
    model: Callable[[str], str] | None = None,
    butce_sn: float = 300.0,
    yerel_model: bool = True,
    bulut_onayi: bool = False,
    state_dir: Path | None = None,
    sinav: Callable[[], dict[str, Any]] | None = None,
) -> GeceRaporu:
    """Gecenin altı adımı. İlk beşi model gerektirmez.

    `butce_sn` bittiğinde koşan birim tamamlanır, sonraki başlamaz; kalan
    oturumlar filigranda işaretlenmeden kalır ve ertesi gece öne geçer.
    """
    basla = time.perf_counter()
    saat = saat or duvar_saati
    rapor = GeceRaporu()
    if not anahtar.AKTIF.orgu:
        rapor.damitma = "atlandı: örgü kapalı"
        return rapor

    durum = _filigran_oku(filigran)
    oturumlar = oncelikli_oturumlar(store, sessions_dir, saat=saat,
                                    filigran=filigran, durum=durum)
    rapor.oturum_sayisi = len(oturumlar)

    dokunulanlar: list[str] = []
    islenen: list[Oturum] = []
    for oturum in oturumlar:
        if islenen and time.perf_counter() - basla > butce_sn:
            break
        _ileri_tekrar(store, oturum, rapor)
        _sema_tazelemesi(store, oturum, rapor)
        _yakalama(store, oturum, rapor, saat)
        if not oturum.ters_tekrar_kostu:
            ters_tekrar(store, oturum, rapor=rapor)
        dokunulanlar.extend(oturum.dizi)
        islenen.append(oturum)
        durum.setdefault("islenen", {})[oturum.id] = _damga(saat)
        rapor.tekrar_edilen += 1
    rapor.devreden = len(oturumlar) - len(islenen)

    _dikis(store, islenen, rapor)
    _yeniden_orgu(store, dict.fromkeys(dokunulanlar), rapor)
    _kucultme(store, rapor)

    # Adım 6 — damıtma. Tek model gerektiren adım, tek geri alınabilen adım:
    # ilk beşi yaşananın kaydı, bu bir çıkarım. Gizlilik kapısı distil.gate'te.
    from . import distil

    onceki_sinav = sinav() if sinav is not None else None
    damitma = distil.distil(store, dokunulanlar, model=model, saat=saat,
                            local_model=yerel_model, cloud_ok=bulut_onayi,
                            state_dir=state_dir)
    rapor.damitik = damitma.written
    rapor.celiski = damitma.contradictions
    if damitma.node_ids and sinav is not None:
        # Sınav kapısı: geçiş önyükleme kalitesini düşürdüyse damıtık
        # düğümler mezar taşına gider. Tekrar ve sorumluluk geri alınmaz.
        rapor.geri_alinan = distil.exam(store, damitma, onceki_sinav, sinav())
    rapor.damitma = damitma.status

    # Adım 7 — sıcak/soğuk. Gece sonunda, her şey yerine oturduktan sonra:
    # aktif küme sınırlı tutulmazsa imza taraması ve RAM toplam hafızayla
    # doğrusal büyür (ölçüldü: 200k'da p95 33 ms, bütçe 20).
    rapor.isinan, rapor.soguyan = store.isi_guncelle(SOGUK_ESIK)

    durum["son_kosu"] = _damga(saat)
    _filigran_yaz(filigran, durum)
    rapor.sure_sn = round(time.perf_counter() - basla, 3)
    _gunluge_yaz(sessions_dir, rapor, saat)
    return rapor


# -- Adım 1: öncelik ---------------------------------------------------


def oncelikli_oturumlar(
    store: Any,
    sessions_dir: Path,
    *,
    saat: Saat,
    filigran: Path | None = None,
    durum: dict[str, Any] | None = None,
) -> list[Oturum]:
    """Tekrar edilecek oturumlar, kazanç × ihtiyaç sırasıyla.

    Kazanç sonuçtan gelir (başarısız oturum en çok öğretir), ihtiyaç
    dokunulan düğüm sayısından: çok hatıraya değen oturum gelecekte de
    değecektir.
    """
    durum = durum if durum is not None else _filigran_oku(filigran)
    islenen = set((durum.get("islenen") or {}).keys())
    simdi = saat()
    out: list[Oturum] = []
    for yol in sorted(sessions_dir.glob("*.jsonl")):
        if yol.stem in islenen:
            continue
        oturum = _oturum_oku(yol)
        if oturum is None or not oturum.kapali or not oturum.dizi:
            continue
        yas = _gun_farki(simdi, oturum.bitis)
        if yas > GERIYE_GUN:
            continue        # eskinin pekişmesi tarama ile değil, şemayla
        surpriz_ort = _surpriz_ortalamasi(store, oturum.dizi)
        oturum.oncelik = (
            KAZANC.get(oturum.kazanc_sinifi(), 0.1)
            * (1 + 0.1 * len(set(oturum.dizi)))
            * (1 + surpriz_ort)
            * (GERIYE_SONUMU ** max(0, yas))
        )
        out.append(oturum)
    out.sort(key=lambda o: (-o.oncelik, o.id))
    return out


def _gun_farki(simdi: datetime, an: datetime | None) -> int:
    if an is None:
        return 0
    return max(0, (simdi - an).days)


def surpriz(store: Any, body: str, *, haric: str = "") -> float:
    """Bu gövde ne kadar yeni? 0 = bilinen, 1 = hiç görülmemiş.

    `haric`: kaydın kendisi. Yazıldıktan sonra en yakın komşu kendisi olur
    ve her kayıt "hiç sürprizli değil" görünürdü — sessizce yanlış bir sıfır.

    Faz 4 aynı hesabı YAZIM ANINDA yapıp kodlama gücü olarak saklıyor
    (`aktivasyon.kodlama_gucu`). Buradaki hesap o anın değil ŞU ANIN
    sürprizi: gece, bugünün belleğine göre neyin sıradan olduğuna bakıyor.
    İkisi bilerek ayrı.
    """
    try:
        komsular = store._seed(body[:400], 4)          # noqa: SLF001
    except Exception:
        return 0.0
    for node_id, skor, _kind in komsular:
        if node_id != haric:
            return round(1.0 - skor, 4)
    return 1.0


def _surpriz_ortalamasi(store: Any, dizi: Iterable[str]) -> float:
    degerler = []
    for node_id in dict.fromkeys(dizi):
        node = store.peek(node_id)
        if node is not None:
            degerler.append(surpriz(store, f"{node.title} {node.body}",
                                    haric=node_id))
    return sum(degerler) / len(degerler) if degerler else 0.0


# -- Adım 2: ileri tekrar ----------------------------------------------


def _ileri_tekrar(store: Any, oturum: Oturum, rapor: GeceRaporu, *,
                  bastan: int = 0) -> None:
    """Oturum dizisindeki komşuları "birlikte kullanıldı" ile bağlar.

    Bu kenarlar `recall()` yayılmasında içerik kenarlarıyla aynı yoldan
    yürür ama **prime'a girmez** (prime hop-0 ile sınırlı). Yani zaman
    komşuluğu açık aramayı zenginleştirir, otomatik enjeksiyonu kirletmez.
    """
    dizi = list(dict.fromkeys(oturum.dizi))
    for i, a in enumerate(dizi):
        for j in range(i + 1, min(i + PENCERE, len(dizi))):
            if j < bastan:
                continue        # bu çift daha önce yazıldı (artımlı koşum)
            agirlik = round(KOMSULUK_AGIRLIK * KOMSULUK_SONUMU ** (j - i - 1), 3)
            if store.baglan(a, dizi[j], weight=agirlik,
                            reason=f"birlikte kullanıldı ({oturum.id})",
                            birikimli=True):
                rapor.yeni_kenar += 1


# -- Adım 2b: şema tazelemesi ------------------------------------------


def _sema_tazelemesi(store: Any, oturum: Oturum, rapor: GeceRaporu) -> None:
    """Bugünün anısına bağlı eski anı kendiliğinden tazelenir.

    Beynin "eskiyi tarayıp pekiştirme" yapmamasının, örtüşen örüntüyü
    yeniden oynatmasının karşılığı (Tse 2007: şemaya uyan bilgi hızlı
    konsolide olur). Bağlı olmayan tazelenmez — ve tazelenmemelidir.
    """
    dokunulan = set(oturum.dizi)
    for node_id in dict.fromkeys(oturum.dizi):
        for komsu, agirlik in store.neighbours(node_id):
            if komsu.id in dokunulan:
                continue
            store.kullanim_ekle(komsu.id, w=SEMA_PAYI * agirlik,
                                etiket=aktivasyon.SEMA)
            rapor.sema_dokunusu += 1


# -- Adım 1b: geriye dönük yakalama ------------------------------------


def _yakalama(store: Any, oturum: Oturum, rapor: GeceRaporu, saat: Saat) -> None:
    """Sürprizli olayın yanındaki sıradan kayıt da pekişir."""
    surprizli: list[datetime] = []
    for node_id in dict.fromkeys(oturum.dizi):
        node = store.peek(node_id)
        an = oturum.damgalar.get(node_id)
        if node is None or an is None:
            continue
        if surpriz(store, f"{node.title} {node.body}",
                   haric=node_id) >= YAKALAMA_ESIK:
            surprizli.append(an)
    if not surprizli:
        return
    pencere = timedelta(minutes=YAKALAMA_DAKIKA)
    for node_id in dict.fromkeys(oturum.dizi):
        an = oturum.damgalar.get(node_id)
        if an is None:
            continue
        node = store.peek(node_id)
        if node is None or surpriz(store, f"{node.title} {node.body}",
                                   haric=node_id) >= YAKALAMA_ESIK:
            continue
        if any(abs(an - buyuk) <= pencere for buyuk in surprizli):
            store.kullanim_ekle(node_id, w=YAKALAMA_PAYI,
                                etiket=aktivasyon.YAKALANDI)
            rapor.yakalanan += 1


# -- Adım 3: ters tekrar -----------------------------------------------


def ters_tekrar(store: Any, oturum: Oturum, *,
                rapor: GeceRaporu | None = None) -> GeceRaporu:
    """Sonuçtan geriye yürüyerek sorumluluğu dağıtır.

    `uses` sayacının yapmadığı ayrım: yanlış cevaba götüren hatıra da doğru
    cevaba götüren de bir puan alıyordu. Burada başarıya götüren artı,
    hataya götüren eksi ağırlıklı bir kullanım alıyor — ve hataya götürenin
    yanına bir `lesson` yazılıyor. Kayıt unutulmuyor, **geride kalıyor**.

    Uyanık tekrar (Faz 3.12) aynı fonksiyonu sonuç anında çağıracak; gece
    yalnız o koşumu kaçırmış oturumları topluyor.
    """
    rapor = rapor if rapor is not None else GeceRaporu()
    dizi = list(dict.fromkeys(oturum.dizi))
    if not dizi:
        return rapor

    if oturum.sonuc == "basarili":
        for k, node_id in enumerate(reversed(dizi)):
            store.kullanim_ekle(node_id, w=BASARI_PAYI * PAY_SONUMU ** k,
                                etiket=aktivasyon.BASARI)
            rapor.basari_payi += 1
        if len(dizi) >= 3 and len(oturum.araclar) >= 2:
            store.remember(
                "Bu yordam işe yaradı: " + " → ".join(oturum.araclar[:6]),
                kind="procedure", tags=["gece", "yordam"],
                links=dizi[-3:], session=oturum.id)
            rapor.yazilan_yordam += 1

    elif oturum.sonuc in ("basarisiz", "duzeltildi"):
        for k, node_id in enumerate(reversed(dizi)):
            store.kullanim_ekle(node_id, w=HATA_PAYI * PAY_SONUMU ** k,
                                etiket=aktivasyon.HATA)
            rapor.hata_payi += 1
        kaynak = dizi[-1]
        if oturum.hata_metni:
            store.remember(
                f"{oturum.hata_metni} — bu yolda {kaynak} kullanılmıştı",
                kind="lesson", tags=["gece", "hata"], links=[kaynak],
                session=oturum.id)
            rapor.yazilan_ders += 1

    elif oturum.sonuc == "acik":
        # Açık hedefe dokunulmuyor — Faz 1 bozunması işini yapsın. Ama
        # "kaldığın yer" bir sonraki oturumun bulabileceği bir düğüm olsun.
        store.remember(
            f"Yarım kalan iş ({oturum.id}): son dokunulan kayıtlar {', '.join(dizi[-2:])}",
            kind="goal", tags=["acik"], links=dizi[-2:], session=oturum.id)
        rapor.yazilan_hedef += 1
    return rapor


# -- Adım 4: dikiş -----------------------------------------------------


def _dikis(store: Any, oturumlar: list[Oturum], rapor: GeceRaporu) -> None:
    """Hiç yaşanmamış diziler: pazartesi A→B, perşembe B→C ⇒ A→C.

    Ağırlık düşük (0.3): yaşanmamış bir bağ, yaşanmışın yarısı kadar
    güvenilir. Sonradan gerçekten birlikte kullanılırsa Adım 2 ağırlığı
    artırır; kullanılmazsa küçültme onu düşürür.
    """
    # Zaman sırasına göre: dikiş yönlü bir iştir — önceki oturumdaki "o'dan
    # önce gelen" ile sonraki oturumdaki "o'dan sonra gelen" birleştirilir.
    # Öncelik sırası (Adım 1) burada yanlış yön verirdi.
    sirali = sorted(oturumlar, key=lambda o: (o.bitis is None, o.bitis, o.id))
    for i, birinci in enumerate(sirali):
        for ikinci in sirali[i + 1:]:
            d1 = list(dict.fromkeys(birinci.dizi))
            d2 = list(dict.fromkeys(ikinci.dizi))
            for ortak in set(d1) & set(d2):
                a = _onceki(d1, ortak)
                c = _sonraki(d2, ortak)
                if not a or not c or a == c:
                    continue
                if store.baglan(a, c, weight=0.3,
                                reason=f"{ortak} üzerinden dikildi "
                                       f"({birinci.id}→{ikinci.id})",
                                yalniz_yeni=True):
                    rapor.dikis += 1


def _onceki(dizi: list[str], node_id: str) -> str:
    i = dizi.index(node_id)
    return dizi[i - 1] if i > 0 else ""


def _sonraki(dizi: list[str], node_id: str) -> str:
    i = dizi.index(node_id)
    return dizi[i + 1] if i + 1 < len(dizi) else ""


# -- Adım 5: yeniden örgü ve küçültme ----------------------------------


def _yeniden_orgu(store: Any, dokunulanlar: Iterable[str],
                  rapor: GeceRaporu) -> None:
    """`_weave` yazım anında donuyordu; ağ yazım sırasına bağımlıydı.

    Artımlı: yalnız bu gece dokunulan düğümler yeniden örülüyor. Tam ağ
    50k düğümde 250 saniye ederdi; dokunulan küme birkaç saniye.
    """
    for node_id in dokunulanlar:
        node = store.peek(node_id)
        if node is None:
            continue
        adaylar = store._seed(f"{node.title} {node.body}"[:400], ORGU_ADAY)  # noqa: SLF001
        sira = 0
        for aday, _skor, _kind in adaylar:
            if aday == node_id:
                continue
            if store.baglan(node_id, aday, weight=round(0.8 - sira * 0.15, 3),
                            reason="benzer icerik (yeniden örgü)"):
                rapor.orgu_kenari += 1
            sira += 1
            if sira >= ORGU_BAGLANTI:
                break


def _kucultme(store: Any, rapor: GeceRaporu) -> None:
    """Sinaptik homeostaz: bütün kenarlar orantılı küçülür, gerekçe ayrımı yok.

    Bu gece güçlenenler küçültmeden önce büyüdüğü için net kazançlı;
    dokunulmayanlar her gece erir. Tabanın altına inen kenar siliniyor —
    kenar silinebilir, düğüm silinemez: kenar bilgi değil yol.
    """
    rapor.kuculen_kenar, rapor.silinen_kenar = store.kenarlari_kucult(
        EPSILON, KENAR_TABAN)


# -- oturum günlüğü ----------------------------------------------------


# Günlükte bir düğüme dokunulduğunu söyleyen olaylar. `prime` ile enjekte
# edilen kayıtlar da diziye giriyor: model onları GÖRDÜ, kullandı sayılır.
DOKUNMA = ("mind_open", "mind_write")


def _oturum_oku(yol: Path) -> Oturum | None:
    oturum = Oturum(id=yol.stem)
    try:
        satirlar = yol.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for satir in satirlar:
        if not satir.strip():
            continue
        try:
            olay = json.loads(satir)
        except ValueError:
            continue
        if olay.get("kind") != "meta":
            continue
        tur = olay.get("content")
        meta = olay.get("meta") or {}
        an = coz(olay.get("ts"))

        if tur in DOKUNMA:
            if node_id := meta.get("memory_id"):
                oturum.dizi.append(node_id)
                if an is not None:
                    oturum.damgalar.setdefault(node_id, an)
            oturum.turlar += 1
            if meta.get("kind") == "lesson" or meta.get("supersedes"):
                oturum.duzeltme = True
        elif tur == "prime":
            for node_id in meta.get("ids") or []:
                oturum.dizi.append(node_id)
                if an is not None:
                    oturum.damgalar.setdefault(node_id, an)
            oturum.turlar += 1
        elif tur == "tool_end":
            oturum.araclar.append(str(meta.get("tool") or ""))
            if meta.get("error"):
                oturum.hata_metni = str(meta.get("ozet") or meta.get("tool") or "hata")
        elif tur == "goal_push":
            oturum.hedef_acik = True
        elif tur == "goal_status":
            oturum.hedef_acik = False
        elif tur == "ters_tekrar_kostu":
            oturum.ters_tekrar_kostu = True
        elif tur == "ileri_tekrar_kostu":
            oturum.ileri_tekrar_indeksi = max(oturum.ileri_tekrar_indeksi,
                                              int(meta.get("n") or 0))
        elif tur == "sonuc":
            oturum.sonuc = str(meta.get("sonuc") or "")
            oturum.bitis = an
    if oturum.bitis is None:
        oturum.bitis = coz(json.loads(satirlar[-1]).get("ts")) if satirlar else None
    return oturum


# -- filigran ve rapor -------------------------------------------------


def _damga(saat: Saat) -> str:
    return saat().isoformat(timespec="milliseconds")


def _filigran_oku(yol: Path | None) -> dict[str, Any]:
    if yol is None or not Path(yol).exists():
        return {"islenen": {}}
    try:
        durum = json.loads(Path(yol).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"islenen": {}}
    durum.setdefault("islenen", {})
    return durum


def _filigran_yaz(yol: Path | None, durum: dict[str, Any]) -> None:
    if yol is None:
        return
    Path(yol).parent.mkdir(parents=True, exist_ok=True)
    Path(yol).write_text(json.dumps(durum, ensure_ascii=False), encoding="utf-8")


def _gunluge_yaz(sessions_dir: Path, rapor: GeceRaporu, saat: Saat) -> None:
    """Gecenin özeti diske: arayüzdeki "hafıza sağlığı" paneli bunu okuyor."""
    try:
        yol = Path(sessions_dir).parent / "gece.jsonl"
        yol.parent.mkdir(parents=True, exist_ok=True)
        with yol.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": _damga(saat), **rapor.sozluk()},
                                ensure_ascii=False) + "\n")
    except OSError:
        pass        # rapor yazılamadıysa gece yine de yapıldı
