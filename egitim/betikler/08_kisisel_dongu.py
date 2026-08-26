# -*- coding: utf-8 -*-
"""Kişisel ince ayar döngüsü — gece koşan, tamamen yerel öğrenme halkası.

Akış (her aşama tek başına güvenli, yarıda kesilse ertesi gece sürer):

  1. HASAT   — neocp'nin zihninden (recall.db, SALT OKUNUR) son koşudan beri
               eklenen anılar çekilir (episode hariç: onlar konuşma dökümü).
  2. ETİKET  — neocp'nin ana modeli (config.json'daki model + keys.json'daki
               anahtar) her anı için 3 soru üslubu + konu terimleri üretir.
               "Gece öğretmeni": gündüz beyin, gece etiketçi.
  3. İNCE AYAR — birikmiş kişisel çift sayısı eşiği aşınca eniyi.pt'den
               düşük öğrenme hızıyla sürdürülür. Unutmaya karşı her kişisel
               örneğe 4 taban korpusu örneği karıştırılır (tekrar tamponu).
  4. SINAV KAPISI — aday model konuşlu modelle AYNI koşuda yarışır:
               TR scale_bench + EN yoklama + kişisel yoklama. Gerileyen
               aday ÇÖPE gider, konuşlu model yerinde kalır.
  5. GÖLGELE — geçen aday .neocp/taban.npz'ye yazılır; ürün o dosyayı
               merkezi modele tercih eder (recall/taban.py).

Neden saat başı değil gece: saatlik yeni veri birkaç örnek — sinyal az,
unutma riski ve fan gürültüsü çok. Birikim eşiği + gece boşluğu doğru denge.
"""

from __future__ import annotations

import json
import random
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
# neocp kökü: .neocp durumu, src ve eval buradan türetiliyor. Kurulum
# düzeninde ürün (tanima.py) kendi kökünü `--neocp <yol>` ile geçiyor;
# argümansız çağrıda geliştirici yolu geçerli — davranış değişmiyor.
NEOCP = (KOK.parent if (KOK.parent / "src" / "neocp").is_dir()
         else Path("D:/Projects/Fatih/neocp"))
if "--neocp" in sys.argv:
    NEOCP = Path(sys.argv[sys.argv.index("--neocp") + 1]).resolve()
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "betikler"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import ortak  # noqa: E402
from model.cikarim import TabanYazici  # noqa: E402

# ortak'ın sınav sarmalı da neocp köküne bakıyor (src + eval yolları);
# bizim çözdüğümüz kökü oraya da geçir — iki ayrı doğru olmasın.
ortak.NEOCP = NEOCP

VERI = KOK / "veri"
OUT = KOK / "out"
DURUM = VERI / "kisisel_durum.json"
KORPUS_K = VERI / "kisisel_korpus.jsonl"
GUNLUK = VERI / "kisisel_gunluk.md"
DB = NEOCP / ".neocp" / "mind" / "recall.db"
KONUSLU = NEOCP / ".neocp" / "taban.npz"          # kişisel model buraya
MERKEZI = NEOCP / "src" / "neocp" / "assets" / "taban.npz"

ESIK = 150          # bu kadar eğitilmemiş kişisel çift birikince ince ayar
KOSU_TAVANI = 400   # bir gecede en fazla bu kadar anı etiketlenir
# Üç koşunun dersi (26.08): (a) 3e-5+23 tur → kişisel 0.82 ama genel ezildi;
# (b) 1e-5+4 tur → genel korundu, öğrenme sıfır; (c) alt-yarı donuk → bağlı
# çıkış katmanı da donduğu için öğrenme tıkandı. Çözüm hız/tur ayarı değil
# WISE-FT: bir kez agresif eğit, sonra taban ağırlıklarla farklı oranlarda
# HARMANLA ve kapıya birden çok adayı sok — kalıcılık/öğrenme dengesi eğitim
# anında değil harman oranında seçilir.
OGRENME_HIZI = 3e-5
TEKRAR_ORANI = 6    # 1 kişisel örneğe kaç taban örneği karışır
TEKRAR_SUSMA_PAYI = 0.25  # tekrar tamponunun en az bu kadarı susma örneği
TUR_SAYISI = 15     # karışım üzerinden kaç geçiş (epoch)
KISISEL_AGIRLIK = 2  # kişisel örnekler karışıma kaç kez girer
ALFALAR = (0.35, 0.55, 0.75)  # aday harmanları: ince ayarın payı


# -- durum --------------------------------------------------------------------

def durum_oku() -> dict:
    try:
        return json.loads(DURUM.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"son_created": "", "egitilen": 0}


def durum_yaz(d: dict) -> None:
    DURUM.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def gunluk(satir: str) -> None:
    zaman = datetime.now(timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M")
    with GUNLUK.open("a", encoding="utf-8") as f:
        f.write(f"- {zaman} — {satir}\n")
    print(satir)


# -- 1) hasat -----------------------------------------------------------------

def hasat(son_created: str) -> list[dict]:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        satirlar = con.execute(
            "SELECT id, kind, title, body, created FROM node "
            "WHERE kind != 'episode' AND deleted = 0 AND created > ? "
            "ORDER BY created LIMIT ?",
            (son_created, KOSU_TAVANI),
        ).fetchall()
    finally:
        con.close()
    return [{"id": i, "kind": k, "title": t or "", "body": b or "", "created": c}
            for i, k, t, b, c in satirlar]


# -- 2) etiketleme (ana model öğretmen) ---------------------------------------

ISTEM = """Aşağıda bir kişisel hafıza kaydı var. Bu kayda dair kullanıcının \
sorabileceği 4 FARKLI soru yaz: S1 doğrudan, S2 eşanlamlı kelimelerle \
(kayıttaki anahtar kelimeleri kullanMA), S3 kısa/belirsiz, S4 İNGİLİZCE \
(kullanıcı aynı şeyi İngilizce soruyor). Sonra kaydın konu terimlerini ver \
(T: 2-6 kelime, küçük harf, kayıt dilinde). BAŞKA HİÇBİR ŞEY yazma.

Biçim:
S1: ...
S2: ...
S3: ...
S4: ...
T: terim1 terim2 ...

Kayıt: {baslik}
{govde}"""


def coz(metin: str) -> list[tuple[str, str]]:
    """S1/S2/S3 + T satırlarını (soru, terimler) çiftlerine açar."""
    sorular, terim = [], ""
    for satir in metin.splitlines():
        satir = satir.strip()
        if satir[:3] in ("S1:", "S2:", "S3:", "S4:"):
            sorular.append(satir[3:].strip())
        elif satir[:2] == "T:":
            terim = " ".join(satir[2:].split()[:6]).casefold()
    if not terim or not sorular:
        return []
    return [(s, terim) for s in sorular if len(s) > 8]


def _urun_ogretmeni() -> tuple[str, str, str] | None:
    """neocp'nin SEÇİLİ modeli: (model adı, base_url, anahtar).

    Ürün hangi modelle konuşuyorsa gece öğretmeni de o: kullanıcı modeli
    değiştirdiğinde döngü kendiliğinden onu izliyor, burada ikinci bir
    model ayarı çürümüyor. Anahtar yalnızca OpenRouter için gerekiyor;
    LM Studio gibi yerel uçlar anahtarsız (Authorization gönderilmiyor).
    """
    try:
        cfg = json.loads((NEOCP / ".neocp" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    model = cfg.get("model") or {}
    ad = str(model.get("name") or "").strip()
    url = str(model.get("base_url") or "").strip()
    if not ad or not url:
        return None
    anahtar = ""
    if "openrouter" in url:
        try:
            anahtarlar = json.loads((NEOCP / ".neocp" / "keys.json").read_text(encoding="utf-8"))
            anahtar = str(anahtarlar.get("OPENROUTER_API_KEY") or "")
        except (OSError, ValueError):
            return None
        if not anahtar:
            return None
    return ad, url, anahtar


def _secili_sor(ad: str, url: str, anahtar: str, istem: str) -> str:
    """Seçili modele tek istek — OpenAI-uyumlu chat/completions ucu."""
    body = json.dumps({
        "model": ad,
        "messages": [{"role": "user", "content": istem}],
        "max_tokens": 400,
        "temperature": 0.6,
        # Canlı test (26.08): qwen düşünme modunda token bütçesini gizli
        # akıl yürütmeye harcıyor ve İÇERİK BOŞ dönüyor. reasoning kapalı
        # istekte temiz S1..S4/T geliyor (~25 sn/istek).
        "reasoning": {"enabled": False},
    }).encode("utf-8")
    basliklar = {"Content-Type": "application/json"}
    if anahtar:
        basliklar["Authorization"] = f"Bearer {anahtar}"
    req = urllib.request.Request(
        url.rstrip("/") + "/chat/completions", data=body, headers=basliklar)
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.load(r)
    return (out["choices"][0]["message"]["content"] or "").strip()


def etiketle(anilar: list[dict]) -> list[dict]:
    """Öğretmen = neocp'nin seçili modeli; düşerse gemini yedeği (ayarlar.py).

    Seçili model 3 istek üst üste boş/çözümlenemez içerik ya da hata
    verirse yedeğe düşülüyor. Yedek de yoksa hasat bırakılıyor — filigran
    ilerlemediği için anılar kaybolmuyor, sonraki gece yeniden denenir.
    """
    secili = _urun_ogretmeni()
    yedek = None
    try:
        import ayarlar
        yedek = ayarlar.ogretmen_sor
    except ImportError:
        pass
    if secili is None and yedek is None:
        gunluk("etiket atlandı: ne seçili model ne ayarlar.py var (veri sonra etiketlenir)")
        return []

    ciftler: list[dict] = []
    ardarda = 0   # seçili modelin üst üste boş/hata sayısı
    hata = 0      # yedek öğretmenin hata sayısı
    for ani in anilar:
        istem = ISTEM.format(baslik=ani["title"], govde=ani["body"][:600])
        yeni: list[tuple[str, str]] = []
        if secili is not None:
            try:
                yeni = coz(_secili_sor(*secili, istem))
            except Exception:
                yeni = []
            if yeni:
                ardarda = 0
            else:
                ardarda += 1
                if ardarda >= 3:
                    if yedek is not None:
                        gunluk("seçili model 3 kez boş/ulaşılamaz — gemini yedeğine düşüldü")
                        secili = None
                    else:
                        gunluk("etiket bırakıldı: seçili model 3 kez boş döndü, "
                               "yedek yok — hasat sonraki geceye kaldı")
                        return []
        if secili is None and not yeni and yedek is not None:
            try:
                yeni = coz(yedek([{"role": "user", "content": istem}],
                                 max_tokens=400, temperature=0.6))
            except Exception:
                hata += 1
                if hata >= 3:
                    gunluk(f"etiket yarıda: öğretmen {hata} kez ulaşılamadı")
                    break
                continue
        for soru, terim in yeni:
            ciftler.append({"girdi": soru, "cikti": terim,
                            "tur": "kisisel", "kaynak": ani["id"]})
    return ciftler


# -- 3) ince ayar -------------------------------------------------------------

def ince_ayar(kisisel: list[dict]) -> Path | None:
    try:
        import torch
    except ImportError:
        gunluk("ince ayar atlandı: torch yok (veri birikmeye devam eder)")
        return None
    from model.mimari import Ayar, TabanModel, kodla

    ck = torch.load(OUT / "eniyi.pt", map_location="cpu")
    ayar = Ayar(**ck["ayar"])
    model = TabanModel(ayar)
    model.load_state_dict(ck["model"])

    # Kişisel ince ayar HER ZAMAN CPU'da: kullanıcının ekran kartında o an
    # yerel bir dil modeli yüklü olabilir ve VRAM çekişmesi kullanıcıya
    # "bilgisayarım kastı" olarak döner. CPU'da ~5 dk ölçüldü ve süreç zaten
    # düşük öncelikte — hissedilmez. Geliştirici `--aygit cuda` ile zorlayabilir.
    aygit = "cpu"
    if "--aygit" in sys.argv:
        aygit = sys.argv[sys.argv.index("--aygit") + 1]
    model.to(aygit).train()

    # Tekrar tamponu: taban korpusundan örnekler unutmayı frenler. Susma
    # örnekleri ayrıca korunuyor — sessizlik ilk koşuda en çok kanayan metrikti.
    taban, susmalar = [], []
    for ad in ("korpus.jsonl", "korpus_en.jsonl"):
        yol = VERI / ad
        if yol.exists():
            for l in yol.read_text(encoding="utf-8").splitlines():
                r = json.loads(l)
                (susmalar if r.get("tur") == "susma" else taban).append(r)
    rng = random.Random(41)
    tekrar_n = min(len(taban), len(kisisel) * TEKRAR_ORANI)
    susma_n = min(len(susmalar), int(tekrar_n * TEKRAR_SUSMA_PAYI))
    karisim = [(r["girdi"], r["cikti"]) for r in kisisel] * KISISEL_AGIRLIK
    karisim += [(r["girdi"], r["cikti"]) for r in rng.sample(taban, tekrar_n - susma_n)]
    karisim += [(r["girdi"], r["cikti"]) for r in rng.sample(susmalar, susma_n)]
    rng.shuffle(karisim)
    veriler = [kodla(g, c, ayar.ctx) for g, c in karisim]

    # Parti düzeni 04_egit.toplu ile birebir: PAD dolgulu X/Y, kayıp modelin
    # kendi `kayip` metodunda (girdi kısmı orada maskeli).
    adim_sayisi = max(100, TUR_SAYISI * len(veriler) // 16)
    opt = torch.optim.AdamW(model.parameters(), lr=OGRENME_HIZI)
    PAD = 259
    for _ in range(adim_sayisi):
        parti = [veriler[rng.randrange(len(veriler))] for _ in range(16)]
        boy = max(len(g) for g, _ in parti)
        x = torch.full((len(parti), boy), PAD, dtype=torch.long)
        y = torch.full((len(parti), boy), PAD, dtype=torch.long)
        for j, (g, h) in enumerate(parti):
            x[j, :len(g)] = torch.tensor(g)
            y[j, :len(h)] = torch.tensor(h)
        kayip = model.kayip(x.to(aygit), y.to(aygit))
        opt.zero_grad(set_to_none=True)
        kayip.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

    model.cpu().eval()
    hedef = OUT / "kisisel.pt"
    torch.save({"ayar": ck["ayar"], "model": model.state_dict()}, hedef)
    gunluk(f"ince ayar bitti: {len(kisisel)} kişisel + {len(karisim)-len(kisisel)} "
           f"tekrar, {adim_sayisi} adım ({aygit})")
    return hedef


# -- 4) harman + sınav kapısı + 5) gölgeleme ---------------------------------

def harman_npz(ft_ck: Path, alfa: float, hedef: Path) -> None:
    """Wise-FT: θ = alfa·ince_ayar + (1-alfa)·taban, npz'ye aktarılır."""
    import torch
    taban = torch.load(OUT / "eniyi.pt", map_location="cpu")
    ft = torch.load(ft_ck, map_location="cpu")
    sd = {k: ((1 - alfa) * taban["model"][k].float()
              + alfa * ft["model"][k].float())
          for k in taban["model"]}
    ara = OUT / f"harman_{int(alfa * 100)}.pt"
    import copy
    torch.save({"ayar": copy.deepcopy(taban["ayar"]), "model": sd}, ara)
    ortak.npz_aktar(ara, hedef)


def urun_kisisel_puan(yazicilar: dict, kisisel: list[dict]) -> dict[str, float]:
    """Kişisel ölçütün ÜRÜN-GERÇEĞİ: kullanıcının zihin kopyasında arama.

    Kelime-kökü eşleşmesi vekil ölçüttü ve yanılttı: genişletme etiketle
    örtüşmese de doğru anıyı pekala bulabilir (ya da tersi). Burada her
    kişisel soru, kullanıcının GERÇEK anıları üzerinde select_prime ile
    aranır ve kaynak anının dönüp dönmediği sayılır — ürünün yaşayacağı
    şeyin ta kendisi. Veritabanı kopya üzerinde, salt okunur niyetle.
    """
    import shutil
    import tempfile

    sys.path.insert(0, str(NEOCP / "src"))
    from neocp.loop import select_prime
    from neocp.mind.store import Mind

    ornekler = random.Random(7).sample(kisisel, min(60, len(kisisel)))
    sonuc: dict[str, float] = {}
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for ek in ("", "-wal", "-shm"):
            kaynak = DB.parent / f"recall.db{ek}"
            if kaynak.exists():
                shutil.copy2(kaynak, t / f"recall.db{ek}")
        mind = Mind(t, t)
        try:
            for ad, y in yazicilar.items():
                tutan = 0
                for r in ornekler:
                    ek_terim = y.genislet(r["girdi"])
                    q = f"{r['girdi']} {ek_terim}".strip() if ek_terim else r["girdi"]
                    try:
                        hits = select_prime(mind, q)
                    except Exception:
                        hits = []
                    tutan += any(h.item.id == r.get("kaynak") for h in hits)
                sonuc[ad] = tutan / max(1, len(ornekler))
        finally:
            mind.store.close()
    return sonuc


def kapi_ve_konuslandir(ft_ck: Path, kisisel: list[dict]) -> bool:
    """Her harman oranı bir aday; hepsi konuşluyla AYNI koşuda yarışır.

    Geçenlerden kişiseli en iyi öğrenen konuşlanır. Hiçbiri geçemezse
    konuşlu model yerinde kalır — kötü gece ürünü bozamaz.
    """
    konuslu_yol = KONUSLU if KONUSLU.exists() else MERKEZI
    adaylar: dict[str, TabanYazici] = {}
    for alfa in ALFALAR:
        npz = OUT / f"kisisel_a{int(alfa * 100)}.npz"
        harman_npz(ft_ck, alfa, npz)
        adaylar[f"a{int(alfa * 100)}"] = TabanYazici(npz)

    yazicilar: dict = {"konuslu": TabanYazici(konuslu_yol), **adaylar}
    tr = ortak.tr_sinav(yazicilar)
    en = {ad: ortak.en_yoklama(y) for ad, y in yazicilar.items()}

    kisi = urun_kisisel_puan(yazicilar, kisisel)

    k = "konuslu"
    for ad in yazicilar:
        gunluk(f"  {ad:<8} TR {tr[ad]['isabet']:.2f} · sessiz {tr[ad]['sessizlik']:.2f} "
               f"· EN konu {en[ad]['konu']:.2f} · EN susma {en[ad]['susma']:.2f} "
               f"· kişisel {kisi[ad]:.2f}")

    # Paylar yoklama çözünürlüğüne göre: EN yoklaması 16/6 soruluk — yarım
    # sorudan dar bir pay, ölçüm gürültüsünü gerileme sanır. Pay ≈ 2 soru.
    gecenler = [
        ad for ad in adaylar
        if tr[ad]["isabet"] >= tr[k]["isabet"] - 0.03
        and tr[ad]["sessizlik"] >= tr[k]["sessizlik"] - 0.07
        and en[ad]["konu"] >= en[k]["konu"] - 0.13
        and en[ad]["susma"] >= en[k]["susma"] - 0.17
        # Ürün-gerçeği: aday, kullanıcının zihninde konuşludan STRİKT daha
        # çok doğru anı bulmalı — eşit bulan değişikliğe değmez.
        and kisi[ad] > kisi[k]
    ]
    if not gecenler:
        gunluk("KAPI RED: hiçbir harman geçemedi, konuşlu model yerinde kaldı")
        return False
    secilen = max(gecenler, key=lambda ad: kisi[ad])
    KONUSLU.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(OUT / f"kisisel_{secilen}.npz", KONUSLU)
    gunluk(f"KONUŞLANDI: {secilen} (kişisel {kisi[secilen]:.2f}) → {KONUSLU}")
    return True


# -- ana akış -----------------------------------------------------------------

def main() -> None:
    durum = durum_oku()
    anilar = hasat(durum.get("son_created", ""))
    if anilar:
        ciftler = etiketle(anilar)
        if ciftler:
            with KORPUS_K.open("a", encoding="utf-8") as f:
                for r in ciftler:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            durum["son_created"] = anilar[-1]["created"]
            durum_yaz(durum)
            gunluk(f"hasat: {len(anilar)} anı → {len(ciftler)} çift "
                   f"(toplam {sum(1 for _ in KORPUS_K.open(encoding='utf-8'))})")
    else:
        print("yeni anı yok")

    if not KORPUS_K.exists():
        return
    tumu = [json.loads(l) for l in KORPUS_K.read_text(encoding="utf-8").splitlines()]
    bekleyen = len(tumu) - durum.get("egitilen", 0)
    if bekleyen < ESIK:
        print(f"eşik dolmadı: {bekleyen}/{ESIK} bekleyen çift")
        return
    # Kapıdan geçemeyen bir denemeyi aynı veriyle her gece tekrarlamak boşa
    # GPU/CPU yakar: yeniden denemek için son denemeden beri anlamlı yeni
    # veri (≥50 çift) birikmiş olmalı.
    if len(tumu) - durum.get("denenen", 0) < 50 and durum.get("denenen"):
        print(f"yeni veri az: {len(tumu) - durum.get('denenen', 0)}/50 — deneme ertelendi")
        return

    ck = ince_ayar(tumu)
    if ck is None:
        return
    durum["denenen"] = len(tumu)
    if kapi_ve_konuslandir(ck, tumu):
        durum["egitilen"] = len(tumu)
    durum_yaz(durum)


if __name__ == "__main__":
    main()
