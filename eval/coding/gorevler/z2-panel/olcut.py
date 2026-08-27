"""z2 — zor/PHP: giriş korumalı mini web panel.

Bu görev düzeneğin var olma sebebi. Bir panelde "sayfa açıldı" demek,
kullanıcı GİRİŞ YAPTIKTAN SONRA sayfanın gerçekten çalışması demek — ve
kırıldığımız yer tam orası: giriş ekranı güzel, arkası boş ya da ölümcül
hata. `php -S` bir Fatal error'ı da 200 ile servis eder.

O yüzden "çalışıyor" üç kata bağlandı (`puanla.sayfa_saglam`):
  1. HTTP 200,
  2. gövde gerçekten dolu (boş şablon sayılmaz),
  3. gövdede PHP hata izi yok (Fatal/Parse/Warning/Undefined).

Ölçüm çerezli bir istemciyle yapılıyor: önce girişsiz erişim denenip
korumanın var olduğu doğrulanıyor, sonra giriş yapılıp aynı sayfalar
yeniden isteniyor.
"""

from __future__ import annotations

import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import puanla  # noqa: E402
from puanla import Eksen, Sayac  # noqa: E402

BASLIK = "Giriş korumalı mini yönetim paneli"
ZORLUK = "zor"
DIL = "php"
KRITIK = ("giris", "oturum")
PORT = 8098
SAYFALAR = ("ozet.php", "kullanicilar.php", "ayarlar.php")
KULLANICI, SIFRE = "admin", "1234"


def _bos_port(taban: int = PORT) -> int | None:
    """Ölçüm için boş bir port.

    İstemdeki 8098 sabit DEĞİL: sunucuyu biz başlatıyoruz (`php -S ... -t dir`),
    port bizim seçimimiz. Ölçülen yara: ajan kendi denemesi için açtığı
    `php -S`'i tur bitince kapatmamıştı, 8098 tutuluydu ve iki taşıyıcı eksen
    birden "ölçülemedi" oldu — panelin gerçekten çalışıp çalışmadığı hiç
    öğrenilemedi. Boş bir porta kayarak ölçüm ajanın artığından bağımsızlaşıyor.
    """
    for port in range(taban, taban + 60):
        if puanla.port_bos_mu(port):
            return port
    return None


def _kok_bul(kok: Path) -> Path | None:
    """Sunucunun döküman kökü: index.php'nin durduğu klasör."""
    giris = puanla.bul(kok, "index.php")
    return giris.parent if giris else None


def _alan_adlari(gövde: str) -> tuple[str, str]:
    """Giriş formundaki kullanıcı ve şifre alanlarının adlarını çıkarır.

    Ajan `kullanici`/`username`/`user` diyebilir; şart koşmuyoruz, formu
    okuyup ne dediyse onu kullanıyoruz. Bulunamazsa yaygın adlara düşülür.
    """
    kullanici_ad = sifre_ad = ""
    for m in re.finditer(r"<input\b[^>]*>", gövde, re.IGNORECASE):
        etiket = m.group(0)
        ad = re.search(r"name\s*=\s*['\"]([^'\"]+)['\"]", etiket, re.IGNORECASE)
        tur = re.search(r"type\s*=\s*['\"]([^'\"]+)['\"]", etiket, re.IGNORECASE)
        if not ad:
            continue
        if tur and tur.group(1).lower() == "password":
            sifre_ad = sifre_ad or ad.group(1)
        elif not tur or tur.group(1).lower() in ("text", "email", ""):
            kullanici_ad = kullanici_ad or ad.group(1)
    return kullanici_ad or "kullanici", sifre_ad or "sifre"


def _hedef(gövde: str) -> str:
    """Giriş formunun `action` adresi. Boşsa sayfanın kendisi demektir.

    Şart koşmuyoruz: form `giris.php`'ye de gönderebilir, kendine de. Sayfayı
    okuyup nereye gönderiyorsa oraya gönderiyoruz — kullanıcının tarayıcısı
    da bunu yapıyor.
    """
    m = re.search(r"<form\b[^>]*action\s*=\s*['\"]([^'\"]*)['\"]",
                  gövde, re.IGNORECASE)
    yol = (m.group(1).strip() if m else "").split("?")[0]
    if not yol or yol in ("#", "."):
        return "index.php"
    return yol.lstrip("/")


def _giris_yap(t: puanla.Tarayici, taban: str, form: str,
               sifre: str) -> puanla.Yanit:
    kullanici_ad, sifre_ad = _alan_adlari(form)
    veri = urllib.parse.urlencode({kullanici_ad: KULLANICI, sifre_ad: sifre,
                                   "giris": "1", "submit": "1"}).encode()
    return t.iste(f"{taban}/{_hedef(form)}", veri=veri)


def _korumali_mi(y: puanla.Yanit) -> bool:
    """Girişsiz istek gerçekten engellendi mi?

    Kabul: yönlendirme (3xx), 401/403, ya da 200 ama gelen şey giriş formu.
    Reddedilen: 200 + panel içeriği (koruma yok) ve 500 (koruma değil, kaza).
    """
    if y.kod in (301, 302, 303, 307, 308, 401, 403):
        return True
    if y.kod != 200:
        return False
    return bool(re.search(r"type\s*=\s*['\"]password['\"]", y.govde, re.IGNORECASE))


def olc(kok: Path) -> list[Eksen]:
    saglik_e = puanla.saglik_ekseni(kok)
    test_e = puanla.test_ekseni(kok, kritik=KRITIK, harici=True)

    if not puanla.php_var():
        sebep = "makinede php yok"
        return [Eksen("calisir", 40, None, [], sebep=sebep),
                Eksen("kapsam", 25, None, [], sebep=sebep), saglik_e, test_e]

    belge_kok = _kok_bul(kok)
    if belge_kok is None:
        c = Sayac()
        for ad, ag in (("index.php var", 8), ("sunucu ayağa kalkıyor", 10),
                       ("giriş sayfası açılıyor", 10),
                       ("doğru şifreyle içeri giriliyor", 12)):
            c.madde(ad, ag, False, "index.php bulunamadı")
        k = Sayac()
        for sayfa in SAYFALAR:
            k.madde(f"{sayfa} giriş sonrası çalışıyor", 5, False, "index.php yok")
        k.madde("girişsiz erişim engelleniyor", 7, False, "index.php yok")
        k.madde("yanlış şifre reddediliyor", 3, False, "index.php yok")
        return [c.eksen("calisir", 40), k.eksen("kapsam", 25), saglik_e, test_e]

    port = _bos_port()
    if port is None:
        sebep = (f"{PORT}-{PORT + 59} aralığında boş port yok — ölçüm yapılamaz")
        return [Eksen("calisir", 40, None, [], sebep=sebep),
                Eksen("kapsam", 25, None, [], sebep=sebep), saglik_e, test_e]

    c = Sayac()
    k = Sayac()
    c.madde("index.php var", 8, True, str(belge_kok.relative_to(kok) or "."))
    if port != PORT:
        c.kanit.append(f"! {PORT} tutuluydu (ajan kendi sunucusunu açık "
                       f"bırakmış olabilir); ölçüm {port} portunda yapıldı")

    taban = f"http://127.0.0.1:{port}"
    with puanla.Sunucu(["php", "-S", f"127.0.0.1:{port}", "-t", str(belge_kok)],
                       cwd=belge_kok, port=port, hazir_sn=25.0) as s:
        c.madde("sunucu ayağa kalkıyor", 10, s.acildi,
                s.patlama or ("port açıldı" if s.acildi else "port 25 sn'de açılmadı"))
        if not s.acildi:
            c.madde("giriş sayfası açılıyor", 10, False, "port açılmadı")
            c.madde("doğru şifreyle içeri giriliyor", 12, False, "port açılmadı")
            for sayfa in SAYFALAR:
                k.madde(f"{sayfa} giriş sonrası çalışıyor", 5, False, "port açılmadı")
            k.madde("girişsiz erişim engelleniyor", 7, False, "port açılmadı")
            k.madde("yanlış şifre reddediliyor", 3, False, "port açılmadı")
            return [c.eksen("calisir", 40), k.eksen("kapsam", 25), saglik_e, test_e]

        # 1. Girişsiz erişim: koruma var mı?
        misafir = puanla.Tarayici()
        korumali = []
        for sayfa in SAYFALAR:
            y = misafir.iste(f"{taban}/{sayfa}", takip=False)
            korumali.append((sayfa, _korumali_mi(y), y.kod))
        tutan = sum(1 for _, ok, _ in korumali if ok)
        k.oranli("girişsiz erişim engelleniyor", 7, tutan / len(SAYFALAR),
                 "; ".join(f"{a}: {'engelli' if ok else f'AÇIK (HTTP {kod})'}"
                           for a, ok, kod in korumali))

        # 2. Giriş sayfasının kendisi.
        t = puanla.Tarayici()
        giris = t.iste(f"{taban}/index.php")
        form_var = bool(re.search(r"type\s*=\s*['\"]password['\"]",
                                  giris.govde, re.IGNORECASE))
        saglam, neden = puanla.sayfa_saglam(giris, en_az=60)
        c.madde("giriş sayfası açılıyor", 10, saglam and form_var,
                f"{neden}; şifre alanı: {form_var}")

        # 3. Yanlış şifre.
        yanlis_t = puanla.Tarayici()
        yanlis_t.iste(f"{taban}/index.php")
        _giris_yap(yanlis_t, taban, giris.govde, "yanlissifre")
        yanlis_sonuc = yanlis_t.iste(f"{taban}/{SAYFALAR[0]}", takip=False)
        k.madde("yanlış şifre reddediliyor", 3, _korumali_mi(yanlis_sonuc),
                f"yanlış şifreden sonra {SAYFALAR[0]} → HTTP {yanlis_sonuc.kod}")

        # 4. Doğru şifre → içeri.
        sonra = _giris_yap(t, taban, giris.govde, SIFRE)
        ilk = t.iste(f"{taban}/{SAYFALAR[0]}")
        girdi = ilk.kod == 200 and not re.search(
            r"type\s*=\s*['\"]password['\"]", ilk.govde, re.IGNORECASE)
        c.madde("doğru şifreyle içeri giriliyor", 12, girdi,
                f"giriş POST → HTTP {sonra.kod}; {SAYFALAR[0]} → HTTP {ilk.kod}"
                + ("" if girdi else " (hâlâ giriş formu geliyor)"))

        # 5. Asıl soru: giriş SONRASI sayfalar gerçekten çalışıyor mu?
        for sayfa in SAYFALAR:
            y = ilk if sayfa == SAYFALAR[0] else t.iste(f"{taban}/{sayfa}")
            saglam, neden = puanla.sayfa_saglam(y)
            hala_giris = bool(re.search(r"type\s*=\s*['\"]password['\"]",
                                        y.govde, re.IGNORECASE))
            k.madde(f"{sayfa} giriş sonrası çalışıyor", 5,
                    saglam and not hala_giris,
                    neden + (" — giriş formuna düşüyor" if hala_giris else ""))

        gunluk_notu = ""
        if s.olu:
            gunluk_notu = "php süreci ölçüm sırasında öldü"
        if gunluk_notu:
            c.kanit.append(f"! {gunluk_notu}")

    return [c.eksen("calisir", 40), k.eksen("kapsam", 25), saglik_e, test_e]


if __name__ == "__main__":
    raise SystemExit(puanla.tek_basina(olc, "z2-panel"))
