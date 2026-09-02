"""Ajan döngüsü.

Döngünün kendisi utanç verecek kadar basittir — modeli çağır, söylediğini yap,
sonucu geri ver, tekrarla. Değerin tamamı döngünün *etrafındaki* şeylerde:
bağlam yönetimi, izin kapısı, kesme güvenliği, kalıcılık.

Kesme güvenliği burada iki noktada zorlanır:
  * akış ortasında kesilirse yarım asistan mesajı atılır (yarım tool_use
    input'u bir sonraki isteği bozar),
  * araç yürütme ortasında kesilirse karşılıksız kalan her tool_use'a iptal
    sonucu enjekte edilir (eksik tool_result = 400).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4

from . import compaction, prompt
from .backends import Backend, Callbacks, TurnResult
from .config import Config
from .context import ContextPolicy, Prepared, cache_report
from .permissions import PermissionEngine
from .session import PendingToolUse, Session, cancelled_result
from .tools import ToolContext, ToolRegistry, build_registry, execute
from .tools.base import JobFailed, ToolSpec

# Uzun koşu kontrol noktası aralığı. Eskiden SERT tavandı: 60. turda döngü
# durur, saatlik bir iş yarıda kalırdı. Artık her 60 turda bir ajan kısa bir
# ilerleme notu yazmaya çağrılıyor ve iş SÜRÜYOR; gerçek fren kullanıcı
# (durdurma ilk andan işliyor) + aşağıdaki mutlak sigorta.
MAX_TURNS = 60

# Koşu başına mutlak tur sigortası. Kaçak döngüye karşı son emniyet.
# 600 tur token yakıyordu (Market Lens ~80+ adım); 240 ≈ 4× soft MAX_TURNS.
HARD_TURN_LIMIT = 240

# Tavana carpan bir yanit kac kez surdurulsun. Sinirsiz birakmak, uzun
# uzun yazip hicbir zaman bitirmeyen bir modelde donguye doner. Sayaç,
# araç çağıran (yani ilerleyen) her turda sıfırlanır: uzun bir koşuda
# arada bir tavana çarpmak işi kapanış turuna sürüklememeli.
MAX_CONTINUATIONS = 4

# Model hatasında (bağlantı, 5xx, zaman aşımı) yeniden deneme aralıkları.
# Üstel geri çekilme: tek bir sağlayıcı hıçkırığı saatlik bir işi
# öldürmemeli. Testler kısaltmak için modül değişkenini yamalıyor.
RETRY_DELAYS = (15.0, 30.0, 60.0, 120.0, 300.0)

# Denemeler tükenince ANA ajan işi PARK eder: ölmez, seyrek yoklamayla
# bekler. Alt ajan / zamanlı görev PARK ETMEZ — sonsuz "Model bekleniyor
# (5/5)" kilidi yerine hata ile biter (chat çalışırken görev takılı kalmasın).
PARK_PROBE_S = 180.0

# Park kaydı: uygulama kapansa bile yarım işin izi diskte durur; açılışta
# görülürse koşu otomatik sürdürülür.
PARK_DOSYASI = "park.json"

# Alt ajan yuvalanma sınırı. 1 demek: ana ajan yardımcı çıkarabilir,
# yardımcı çıkaramaz. Sınırsız bırakmak tek bir isteği ağaç gibi açar ve
# ne kadar iş yapıldığını kimse bilemez.
MAX_DEPTH = 1

# Yardımcı defterinin boyu. Bitmiş kayıtlar sınırsız birikmesin diye en
# eski bitmişler düşürülür; koşan bir yardımcı asla düşürülmez. Oturumlar
# diskte durmaya devam ediyor — defterden düşmek veri kaybı değil.
MAX_CHILDREN = 8

# Bildirim notundaki sonucun tavanı: yardımcının cevabı ana bağlama girer,
# sınırsız girerse bağlamı bölme amacı boşa çıkar.
CHILD_RESULT_CLIP = 2000

# Her kullanici mesajindan once zihinden onune konacak hatira sayisi.
# Fazlası bağlam israfı: ilgisiz hatira modeli konudan uzaklastiriyor.
RECALL_PRIME_LIMIT = 5

# Dar pencerede aynı sayı bağlamın önemli bir kısmını yiyor.
LEAN_PRIME_LIMIT = 2

# Anlık encode için asgari uzunluk. "evet", "tamam", "ok" gibi turlar bir
# konuya atıf taşımıyor; belleğe yazmak yalnızca gürültü. Eşik + _worth_recalling
# birlikte selamı ve tek kelimelik onayları eliyor.
ENCODE_MIN_CHARS = 25

# Kendiliğinden hatırlananlar için asgari güç. Kalibre birleşimden sonra
# skor SIRA değil BÜYÜKLÜK: küçük bir hafızada tek gerçek eşleşme ~0.24
# alabiliyor (bm25 gücü korpusla büyüyor), kalabalık hafızada ~0.9'a
# doyuyor. Eski 0.3 tabanı eski sıra-ölçeğine göreydi ve genç hafızada
# prime'ı sessizce kapatıyordu. Alaka süzgeci artık eşik değil: doğrudan
# eşleşme şartı + harf zemini (_grounded) taşıyor; taban yalnızca gürültü
# tabanını kesiyor.
RECALL_PRIME_FLOOR = 0.12

# Önyükleme sorgusundan atılan sayı biçimleri: IP adresi, port, register
# adresi, uzun ölçüm değerleri.
#
# Sayılar imza katmanında birbirine benziyor ve alakasız kayıtları
# çekiyorlar. Ölçüldü: "5.11.239.227 ... 5004 portunda ... 404195
# adresinde depo seviye" sorgusu üç BTC fiyat kaydını getiriyordu (BTC
# 3.715.633 TL). Sayılar çıkarılınca üçü de listeden tümden düşüyor.
#
# Yalnızca **kendiliğinden** önyüklemede uygulanıyor. Modelin kendi
# `mind_recall` çağrısında sayı gerçekten aranan şey olabiliyor
# ("404195 hangi register?") ve orada dokunulmuyor.
_NUMERIC = re.compile(r"\b[\d][\d.,:/-]*\b")

# Selam ve hâl hatır. Bunlar bir konuya atıf değil; zihni açmaya değmez.
# Liste kısa tutuluyor: uzun bir yasak listesi bakımı zor ve asıl işi
# uzunluk ölçütü yapıyor.
SMALL_TALK = frozenset(
    {
        "selam", "merhaba", "naber", "nabersin", "nasilsin", "nasılsın",
        "gunaydin", "günaydın", "iyi", "iyiyim", "sagol", "sağol",
        "tesekkur", "teşekkür", "tesekkurler", "teşekkürler", "eyvallah",
        "gorusuruz", "görüşürüz", "hosgeldin", "hoşgeldin", "hello", "hey",
    }
)

_WORDS = re.compile(r"\w+", re.UNICODE)

RECALL_PRIME_HEADER = (
    "Kullanicinin son mesaji zihninde arandi; asagidakiler kendiliginden "
    "hatirlandi. Ilgiliyse kullan, degilse yoksay — bunlari kullanici "
    "yazmadi, sana hatirlatildi."
)

# Surdurme durtusu. Kullanici kanalindan gidiyor cunku kesilen turdan
# sonra sondaki mesaj asistanin kendisi ve system notu bir user mesajini
# takip etmek zorunda. Arayuzde gizleniyor: kullanicinin yazmadigi bir
# mesaj sohbette kullanici mesaji gibi gorunmemeli.
CONTINUE_NOTE = (
    "Önceki yanıtın uzunluk sınırında kesildi. Kaldığın yerden devam et. "
    "Yazdıklarını baştan tekrarlama, girişi yeniden yapma, kod bloğunu "
    "yeniden açma; tam olarak kestiğin karakterden sonrasını yaz."
)

# Sürdürme hakkı bittiğinde verilen son tur.
#
# Önceki hal burada duruyor ve kullanıcıya "isteği daha küçük parçalara
# bölmek gerekebilir" diyordu. Ama ajan iş yapmıştı: araçları çağırmış,
# değerleri okumuş, yalnızca bitirememişti. Kullanıcının eline hiçbir şey
# geçmiyordu — hem yapılan iş hem de sorusu kayboluyordu.
#
# Bu tur araçsız veriliyor: tekrar araç çağırmasına izin vermek, kilitlenen
# döngünün bir turunu daha çalıştırmak demek.
CLOSING_NOTE = (
    "Sürdürme hakkın bitti. Şimdi elindekiyle bitir: yeni araç çağırma, "
    "yeni plan yapma, baştan anlatma. Birkaç cümlede şunu yaz — ne buldun, "
    "hangi değeri okudun, hangi soru cevapsız kaldı. Emin olmadığın bir şeyi "
    "kesin gibi yazma; eksikse eksik olduğunu söyle."
)

# Kamera karesi metinsiz gonderildiginde eklenen yonerge. Bakmasi gerekeni
# saymak, tek cumlelik gecistirmeyi engelliyor.
LOOK_NOTE = (
    "Kameradan bir kare. Gerçekten bak ve gördüğünü anlat: ortam, kişi, "
    "elinde ya da önünde ne var, yüz ifadesi nasıl duruyor, genel hâli ne "
    "anlatıyor. Bunlar görünenden çıkarım — kesin bilgi gibi yazma, "
    "\"öyle duruyor\" diye yaz. Göremediğin bir şeyi uydurma; kare bulanıksa "
    "ya da karanlıksa onu söyle."
)

# Ajan kendisi baktığında (kamera karesi ya da ekran görüntüsü) görüntünün
# yanına konan not. "Kameranın gördüğü" diye yazmıyor: aynı yoldan artık
# `screen` görüntüsü de geliyor ve yanlış adlandırmak modeli şaşırtıyordu.
SEEN_NOTE = (
    "Yukarıdaki görüntü senin kendi bakışın — kameradan bir kare ya da "
    "ekran görüntüsü. Kullanıcı göndermedi, sen baktın. Ne gördüğünü "
    "söyle ve işine o gördüğünle devam et; göremediğin bir şeyi uydurma."
)

# Yalnizca akil yurutup duran tura verilen durtu.
ACT_NOTE = (
    "Planını yazdın ama uygulamadın. Şimdi yap: gereken aracı çağır ya da "
    "cevabı doğrudan kullanıcıya yaz. Planı tekrar anlatma."
)

# Model gerçek araç çağrısı yerine çağrı XML'ini DÜZ METİN yazdı. Bu bir
# cevap değil, başarısız bir araç denemesi: kullanıcıya gösterilmiyor
# (arayüz çizmiyor) ve model tek satırlık bir notla düzeltiliyor. Tur
# devam ediyor — burada durmak, kullanıcıyı sessizce yarım bırakırdı.
SAHTE_CAGRI_NOTU = (
    "[Harness notu] Az önce bir araç çağrısını DÜZ METİN olarak yazdın "
    "(<function_calls>… gibi). O metin çalıştırılmadı ve kullanıcıya "
    "gösterilmedi. Araçları yalnızca gerçek araç çağrısı kanalıyla "
    "çağırabilirsin: aynı isteği araç çağrısı olarak yap."
)

# Aynı turda tekrarladı: not sertleşiyor. Yumuşak not işe yaramadıysa
# sebebi çoğu zaman modelin önceki hatayı "araç bozuk" diye okuması.
SAHTE_CAGRI_SERT_NOTU = (
    "[Harness notu] Araç çağrısını YİNE metin olarak yazdın. Yazdığın XML "
    "hiçbir şey çalıştırmıyor. Araçlar çalışıyor; sorun çağrı biçiminde. "
    "Ya aracı gerçek araç çağrısı olarak çağır ya da araç kullanmadan "
    "kullanıcıya doğrudan cevap yaz. Üçüncü bir seçenek yok."
)

# Sahte çağrı düzeltme denemesinin mutlak sigortası. Not sertleştikçe
# düzelmeyen model (çoğu zaman araç çağıramayan ücretsiz bir uç) turu
# sonsuza kadar meşgul etmesin: bu sayıdan sonra tur kendi akışına
# bırakılıyor ve kullanıcıya durum bildiriliyor — model değiştirebilsin.
SAHTE_CAGRI_TAVANI = 5

# Asistan metninde araç çağrısı XML'i. Arayüzdeki savunmayla (app.js
# SAHTE_CAGRI_KALIBI) aynı kalıp — biri kaçarsa diğeri tutuyor.
SAHTE_CAGRI_DESENI = re.compile(
    r"<\s*/?\s*(function_calls|invoke\b|parameter\b|antml:)", re.IGNORECASE)


def sahte_arac_cagrisi(text: str) -> bool:
    """Metin, araç çağrısı XML'i taşıyor mu?

    Model araç kanalını kullanamadığını sandığında (ör. ham bir istisna
    mesajını "araç bozuk" diye okuduğunda) çağrıyı düz metin olarak
    yazıyor. Kullanıcı ekranında ham XML olarak göründüğü kanıtlandı.
    """
    return bool(SAHTE_CAGRI_DESENI.search(text or ""))


# -- zihin yazma refleksi ----------------------------------------------
#
# Ölçülmüş regresyon: son altı oturumda `mind_memory` çağrısı SIFIR — 91
# araç çağrısı yapılan turda bile. Otomatik yol (episode encode) akmaya
# devam ediyordu ama model-güdümlü kalıcı yazma tamamen durmuştu; iki gün
# boyunca tek bir tercih/ders/olgu kaydedilmedi.
#
# Kök asimetri: HATIRLAMA bir refleks (her kullanıcı mesajından önce
# `_prime_recall` kendiliğinden koşuyor), YAZMA ise yalnızca bir öğüt.
# Zayıf ya da orta bir model o öğüdü hiç seçmiyor. Simetri kuruluyor:
# hatırlama nasıl sistem tarafından tetikleniyorsa, yazmaya GEÇİŞ de
# tetikleniyor — kararı yine model veriyor.
#
# Sezgi bilerek UCUZ ve DÜRÜST: anahtar kelime düzeyinde, model çağrısı
# yok. Yanlış pozitifin zararı yok çünkü not "değmezse yok say" diyor.
KALICI_SINYALLER = (
    # Kalıcı kural / tercih bildirimi
    r"\bbundan sonra\b", r"\bbundan böyle\b", r"\bher zaman\b", r"\bhep\b",
    r"\basla\b", r"\bhiçbir zaman\b", r"\bşunu yapma\b", r"\byapma artık\b",
    r"\btercih ediyorum\b", r"\bsevmiyorum\b", r"\bistemiyorum\b",
    r"\bşöyle olsun\b", r"\bböyle olsun\b", r"\bkuralımız\b",
    r"\bunutma\b", r"\baklında tut\b", r"\bnot al\b",
    # Düzeltme: modelin yanlışını gösteren cümleler
    r"\byanlış\b", r"\böyle değil\b", r"\bdüzelt\b", r"\bhayır,",
    # Kullanıcıya ait bir olgu bildirimi
    r"\bbenim\b", r"\bbizim\b", r"\badım\b", r"\bçalıştığım\b",
    r"\bkullanıyorum\b", r"\bprojem\b", r"\bişim\b",
    # İngilizce karşılıklar: kullanıcı iki dilde de yazıyor
    r"\bfrom now on\b", r"\balways\b", r"\bnever\b", r"\bdon't\b",
    r"\bi prefer\b", r"\bremember that\b", r"\bmy name is\b",
    r"\bactually,", r"\bthat's wrong\b",
)

_KALICI = re.compile("|".join(KALICI_SINYALLER), re.IGNORECASE)


def kalici_koku(text: str) -> bool:
    """Bu mesajda kalıcı olabilecek bir şey geçti mi?

    Kesinlik iddiası yok — bir koku. Kararı model veriyor; buradaki tek iş
    konuyu modelin önüne getirmek.
    """
    return bool(_KALICI.search(text or ""))


# Kokunun karşılığı: tek satır, iç kanaldan. Sohbete DÜŞMEZ (internal).
# Emir değil davet: yanlış pozitifte model yok sayıp geçiyor.
ZIHIN_DURTUSU = (
    "[Zihin] Bu turda kalıcı olabilecek bir şey geçti: \"{alinti}\" "
    "Kaydetmeye değerse `mind_memory` ile yaz — oturum kapanınca bağlam "
    "gider, zihin kalır. Değmezse bu notu yok say."
)

# Dürtüdeki alıntının uzunluğu: konuyu hatırlatmaya yetecek kadar.
DURTU_ALINTI = 160


# Arka planda biten yardımcının sonucu tur başında ana ajanın önüne bu
# notla konuyor. Kanal harness'ın: kullanıcı yazmadı, model bunu bilmeli.
CHILD_DONE_NOTE = "[Yardımcı bitti · {title} (id={id})] Sonucu: {result}"
CHILD_FAIL_NOTE = "[Yardımcı hata verdi · {title} (id={id})] {result}"

# Ana ajan boştayken bir yardımcı bittiğinde açılan sürdürme turunun
# girdisi. Kullanıcı mesajı DEĞİL: continuation kanalından gidiyor,
# arayüzde görünmüyor.
CHILDREN_RESUME_NOTE = (
    "Arka plandaki yardımcı(lar) bitti: {titles}. "
    "Tam rapor Orkestra / Görevler panelinde duruyor; kullanıcı tıklayınca "
    "ayrı görüntüleyicide açılıyor (sohbet balonu değil). "
    "Sohbete raporu veya uzun özeti YAPIŞTIRMA — en fazla bir cümle: "
    "'X hazır; soldaki Orkestra'dan aç.' Kullanıcı yeni bir şey istemedi, "
    "yeni iş başlatma."
)

# Zamanlanmış görev yardımcısına verilen zarf: çıktı rapor, sohbet değil.
SCHEDULE_CHILD_WRAP = (
    "[Zamanlanmış görev · {title}]\n{prompt}\n\n"
    "Bu bir zamanlanmış iş. Sonucu sohbet cevabı gibi değil, kendi başına "
    "okunabilir bir RAPOR olarak yaz (başlık + maddeler + kaynaklar). "
    "Rapor Orkestra panelinden açılacak; ana sohbete yapıştırılmayacak."
)

# Tur ortasında kullanıcıdan gelen mesajın zarfı. Köprü (desktop) gelen
# kutusuna bu zarfla koyuyor; buradan tanımlı çünkü testler de kullanıyor.
BARGE_NOTE = (
    "[Kullanıcı bu arada yazdı] {text} — koşan işi sürdürürken bunu da "
    "ele al; öncelik gerekiyorsa yön değiştir."
)

# `task_say`: ana ajandan koşan yardımcıya giden ara mesajın zarfı.
SAY_NOTE = (
    "[Ana ajandan ara mesaj] {message} — işini sürdürürken bunu da hesaba "
    "kat; öncelik gerekiyorsa yön değiştir."
)

# Arka plan İŞİ (uzun komut/derleme/test koşusu) bittiğinde düşen notlar.
# Yardımcı (model koşan alt ajan) notlarından ayrı: bu bir süreç çıktısı.
JOB_DONE_NOTE = "[Arka plan işi bitti · {title} (id={id})] Çıktısı: {result}"
JOB_FAIL_NOTE = "[Arka plan işi hata verdi · {title} (id={id})] {result}"

# Açılışta bulunan yetim yardımcılar (geçen oturumda uygulamayla birlikte
# ölen arka plan alt ajanları) modele bu notla tanıtılıyor: kullanıcı
# "sürdür" derse `task_say` bitmiş/diskteki oturumu zaten diriltebiliyor.
YETIM_NOTU = (
    "[Harness notu] Geçen oturumdan {n} yardımcı yarım kaldı: {liste}. "
    "Uygulama kapanınca arka plan yardımcıları durur; oturumları diskte "
    "duruyor. Kullanıcı sürdürmek isterse `task_say` (id + yönerge) ile "
    "kaldıkları yerden devam ettirebilirsin; kullanıcı istemeden "
    "kendiliğinden başlatma."
)

# Yetim yardımcının defterdeki sonucu — panel ve `task_status` bunu gösteriyor.
YETIM_SONUC = (
    "Uygulama kapanınca yarım kaldı. Oturumu diskte duruyor; `task_say` ile "
    "kaldığı yerden sürdürülebilir."
)

# -- plan refleksi -------------------------------------------------------
#
# İstemde "büyük işte önce modül planı yaz" YAZIYOR ve ÇALIŞMIYOR: yedi
# görevlik bir ölçümde yedisinde de plan yazılmadı. Hafıza yazmada
# öğrenilen ders burada da geçerli — öğüt yetmiyor, refleks gerekiyor.
#
# Kapı UCUZ: model çağrısı yok, regex ve uzunluk düzeyinde. Yanlış
# pozitifin bedeli gereksiz bir plan cümlesi (kabul edilebilir); yanlış
# negatifin bedeli plansız başlayan bir koşu (asıl kaçınılan). Yine de
# seyrek tetiklenmesi için üç sinyalin BİRLİKTE aranması şart: yapım
# fiili + (ölçek sözü ya da madde listesi ya da uzun metin).

BUYUK_IS_UZUNLUK = 350      # bu kadar karakterden uzun istek
# 180'di; ölçülen yara: 10 satırlık o1-rapor görevi bile "[Plan] Bu iş
# büyük görünüyor" dürtüsü yedi (kullanıcı: "her şeye plan çizmene
# gerek yok — kapsam fazlaysa plan, yoksa hemen yap"). Uzun bir
# paragraf tek başına büyüklük kanıtı değil; ölçek sözü ve madde
# sayısı sinyalleri duruyor.
BUYUK_IS_MADDE = 3          # ya da bu kadar madde/teslimat

# "Bir şey ÜRETMEMİ istiyor" fiilleri. Soru sormak, okumak, açmak,
# düzeltmek burada yok — onlar plan gerektiren işler değil.
_YAPIM_FIILI = re.compile(
    r"\b(yap|yapar\s+mısın|kur|geliştir|gelistir|tamamla|oluştur|olustur|"
    r"inşa\s+et|insa\s+et|tasarla|hazırla|hazirla|yazar\s+mısın|"
    r"build|create|implement|develop|make)\w*\b",
    re.IGNORECASE,
)

# Ölçek sözü: tek dosyalık bir betik değil, birden çok parçası olan bir şey.
_OLCEK_SOZU = re.compile(
    r"\b(panel|dashboard|sistem|system|uygulama|app|servis|service|site|"
    r"web\s*sitesi|proje|project|platform|api|arayüz|arayuz|altyapı|altyapi|"
    r"modül|modul|module|oyun|game|bot|editör|editor|yönetim|yonetim|"
    r"admin|crm|erp|panosu|pano)\w*\b",
    re.IGNORECASE,
)

# Madde listesi: "şunlar olsun: - a - b - c" biçimindeki çoklu teslimat.
_MADDE_SATIRI = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+\S", re.MULTILINE)


def buyuk_is(text: str) -> bool:
    """Bu istek "büyük / ucu açık" mı görünüyor?

    Kesinlik iddiası yok — `kalici_koku` gibi bir koku. Karar yine modelin;
    buradaki tek iş plan yazma sırasını modelin önüne koymak.
    """
    metin = (text or "").strip()
    if not metin or not _YAPIM_FIILI.search(metin):
        # Yapım fiili yoksa bu bir soru, bir sohbet ya da küçük bir düzeltme.
        # Plan istemek gürültü olurdu.
        return False
    if len(_MADDE_SATIRI.findall(metin)) >= BUYUK_IS_MADDE:
        return True
    if _OLCEK_SOZU.search(metin):
        return True
    return len(metin) >= BUYUK_IS_UZUNLUK


# Kokunun karşılığı: TEK satır, iç kanaldan, tur başında bir kez. Sohbete
# düşmez. Emir değil sıra kuralı — istemdeki uzun anlatımın refleks hali.
PLAN_NOTU = (
    "[Plan] Bu iş büyük görünüyor. İlk cevabında modül listesi + her modül "
    "için kabul ölçütü yaz, sonra başla."
)


# -- kırmızıyken "bitti" deme kapısı -------------------------------------
#
# Ölçümde bir görev kendi test takımı KIRMIZIYKEN teslim edildi. İstemde
# "bitti demeden doğrula" yazıyor; yazmak yetmiyor.
#
# Kırmızının izi araç sonuçlarından okunuyor. Araç katmanı `detail`i modele
# ve döngüye taşımıyor (executor `_card` ile kırpıyor), o yüzden okunan şey
# döngünün gerçekten gördüğü iki alan: `error` (ToolResult.is_error) ve
# aracın KENDİ başlık satırı. Tool başına ne anlama geldikleri farklı:
#
#   kos      — kırmızıyı kendisi işaretliyor (is_error): başarısız test,
#              sıfırdan farklı çıkış kodu, zaman aşımı, kesilme.
#   denetle  — hatayı is_error ile işaretlemiyor (bir denetim bulgusu
#              yazmayı düşürmemeli); kırmızı kendi metninde yazıyor.
#   browser  — konsol/ağ dökümü hiç hata döndürmüyor; sayılar başlıkta.
#
# Yalnız bu üçü sayılıyor: başarısız bir `read_file` kırmızı bir koşu değil.

DOGRULAMA_ARACLARI = frozenset({"kos", "denetle", "browser"})

_DENETIM_HATASI = re.compile(r",\s*\d+\s+hata:")
_KONSOL_HATASI = re.compile(r"\((\d+)\s+hata\)")
_AG_HATASI = re.compile(r"(\d+)\s+başarısız")
# Executor'ın hacim eki ("  (+22 satır)"): aracın hükmü değil, arayüz izi.
_HACIM_EKI = re.compile(r"\s*\(\+\d+\s+satır\)\s*$")


def kirmizi_iz(tool: str, note: dict[str, Any]) -> str:
    """Bu araç sonucu kırmızı mı? Kırmızıysa tek satırlık özeti, değilse "".

    `note` executor'ın `tool_end` gözlem yükü: {tool, error, summary,
    detail: {output, exit_code, …}}.
    """
    if tool not in DOGRULAMA_ARACLARI:
        return ""
    ozet = _HACIM_EKI.sub("", str(note.get("summary") or "").strip())
    govde = ozet + "\n" + str((note.get("detail") or {}).get("output") or "")

    if tool == "kos":
        return (ozet or "test koşumu başarısız") if note.get("error") else ""

    if tool == "denetle":
        return (ozet or "denetimde hata var") if _DENETIM_HATASI.search(govde) else ""

    # browser: konsolda hata ya da başarısız istek.
    if (m := _KONSOL_HATASI.search(govde)) and int(m.group(1)) > 0:
        return f"tarayıcı konsolunda {m.group(1)} hata"
    if (m := _AG_HATASI.search(govde)) and int(m.group(1)) > 0:
        return f"{m.group(1)} başarısız istek"
    return ""


# "Bitti" iddiası: model turu araçsız kapatırken işi bitmiş ilan ediyor mu.
_BITTI_IDDIASI = re.compile(
    r"\b(bitti|bitirdim|tamamlandı|tamamlandi|tamamladım|tamamladim|"
    r"hazır|hazir|hazırdır|hazirdir|çalışıyor|calisiyor|sorunsuz|"
    r"done|completed?|finished|ready|works|working)\b",
    re.IGNORECASE,
)

# Kırmızıyı zaten söylüyorsa dürtme: dürüst rapor, yanlış "bitti" değil.
_KIRMIZI_ITIRAFI = re.compile(
    r"\b(başarısız|basarisiz|kırmızı|kirmizi|geçmedi|gecmedi|hata\s+var|"
    r"düzeltemedim|duzeltemedim|kaldı|kaldi|eksik|çalışmıyor|calismiyor|"
    r"fail(ing|ed|s)?|broken|not\s+working)\b",
    re.IGNORECASE,
)


def bitti_iddiasi(text: str) -> bool:
    """Araçsız kapanan bu cevap işi bitmiş ilan ediyor mu?

    Kırmızıyı zaten söyleyen bir cevap "bitti" dese de dürüsttür —
    dürtülmez. Yanlış pozitifin bedeli tek bir fazladan tur ve o tur
    yalnızca ortada gerçekten kırmızı bir koşum varken açılıyor.
    """
    metin = text or ""
    if not _BITTI_IDDIASI.search(metin):
        return False
    return not _KIRMIZI_ITIRAFI.search(metin)


KIRMIZI_NOTU = (
    "[Doğrulama] Son koşumun kırmızıydı ({ozet}). Bitti demeden önce ya "
    "düzelt ya da neyin çalışmadığını açıkça söyle."
)

# Kabul-listesi kapısı: iş defterinde AÇIK maddeler dururken "bitti"
# denirse bir tur geri veriliyor. Ölçülen yara (CMS koşusu): plan M4'te
# "zengin metin editörü" yazarken teslim düz textarea çıktı ve hiçbir şey
# yakalamadı — madde sessizce düşmüştü.
# Başlığı MODEL koyar (Claude Code gibi): kullanıcının ilk cümlesinin ilk
# 30 karakteri başlık değildir. İlk alışverişten sonra tek küçük çağrı.
BASLIK_ISTEMI = (
    "Aşağıdaki konuşma için 2-5 kelimelik kısa bir başlık üret. Yalnız "
    "başlığı yaz: tırnak, nokta, emoji, açıklama yok. Konuşmanın dilinde."
)

def _baslik_gecerli(baslik: str) -> bool:
    """Üretilen oturum başlığı kaydedilmeye değer mi?

    Tek harflik çöp ("e", "b") kalıcı ad olarak yapışıyordu ve ad bir kez
    yazılınca bir daha üretilmiyordu — sohbet solda o harfle listeleniyordu.
    Anlamlı bir başlık en az birkaç karakterdir ve tek bir noktalama değildir.
    """
    if not baslik or len(baslik) < 4 or len(baslik) > 60:
        return False
    return any(ch.isalnum() for ch in baslik)


KABUL_NOTU = (
    "[Kabul] İş listende hâlâ açık maddeler var: {ozet}. Bitti demeden "
    "önce her birini ya tamamla (mind_goals ile kapat) ya da neden açık "
    "kaldığını tek cümleyle söyle — plan maddesi sessizce düşmez."
)


# -- teslim edileni ÇALIŞTIRMA kapısı ------------------------------------
#
# Ölçümün en keskin sonucu: bir görev 14 geçen test, 18 gerçek iddia ve
# kod sağlığı 20/20 ile teslim edildi — ve istemin asıl istediği komut
# satırı HİÇ çalışmıyordu. `py ara.py bul "salmastra"` her sorguda kendi
# kullanım satırını basıp 1 ile çıkıyordu. Testler iç fonksiyonları
# kapsamış; kullanıcının yazacağı giriş noktasına hiçbir şey dokunmamış.
#
# Bu vaka kırmızı kapısını AŞIYOR: takım yeşildi, orada durduracak bir şey
# yoktu. Yakalayan tek şey, teslim edileni kullanıcının çalıştıracağı gibi
# çalıştırmak.
#
# Kapı dar tutuluyor. Yalnızca KENDİNİ ÇALIŞTIRILMAK ÜZERE İLAN EDEN bir
# dosya sayılıyor: `__main__` bloğu, `sys.argv`/`argparse`, `process.argv`,
# PHP `$argv`. Kütüphane modülü, sınıf dosyası, yapılandırma bunu taşımaz —
# onları doğrudan koşmak zaten yanlış olurdu.

_GIRIS_IZLERI = (
    re.compile(r"""if\s+__name__\s*==\s*['"]__main__['"]"""),
    re.compile(r"\bsys\.argv\b|\bargparse\b|\bclick\.command\b"),
    re.compile(r"\bprocess\.argv\b|\brequire\.main\s*===\s*module\b"),
    re.compile(r"\$argv\b|\bgetopt\b"),
)

# Girişi olabilecek dosyalar. HTML/CSS/JSON dışarıda: onları "çalıştırmak"
# başka bir şey (tarayıcı kapısının işi), burada karıştırılmamalı.
_KOSULABILIR_UZANTI = frozenset({".py", ".js", ".mjs", ".cjs", ".ts", ".php", ".sh", ".ps1"})


def giris_noktasi_mi(metin: str) -> bool:
    """Bu dosya kendini komut satırından çalıştırılmak üzere ilan ediyor mu?"""
    return any(d.search(metin or "") for d in _GIRIS_IZLERI)


TEST_NOTU = (
    "[Doğrulama] Bu turda test dosyası yazdın ({dosya}) ama onu hiç "
    "KOŞMADIN. Yazılmış ama koşulmamış test, test değildir — kırmızı da "
    "olabilir. Bitti demeden önce test komutunu çalıştır; kırmızıysa "
    "düzelt, yeşilse turu kapat."
)

GIRIS_NOTU = (
    "[Doğrulama] Bu turda {dosya} yazdın ve o dosya kendini komut "
    "satırından çalıştırılmak üzere ilan ediyor — ama onu hiç "
    "ÇALIŞTIRMADIN. Testlerin yeşil olması yetmiyor: testler iç "
    "fonksiyonları çağırıyor, kullanıcı ise komutu yazıyor. Bitti demeden "
    "önce kullanıcının yazacağı komutu aynen çalıştır ve çıktısına bak."
)


# Uzun koşu kontrol noktası: yumuşak dürtü — kabul ölçütü geçildiyse
# `end_turn` serbest. Eski "iş bitmeden durma" uzun tarama işlerini
# sonsuz döngüye sokuyordu.
CHECKPOINT_NOTE = (
    "[Uzun koşu kontrol noktası — {turns} tur] Bir-iki cümleyle ilerleme "
    "durumunu yaz (ne bitti, ne kaldı) — bu satırı kullanıcıya da yaz. "
    "Kabul ölçütü sağlandıysa araç çağırmadan bitir (`end_turn`). "
    "Eksik kaldıysa yalnız eksikleri tamamla; aynı tarama/doğrulama "
    "ritüelini tekrarlama."
)


# -- park kaydı ---------------------------------------------------------
#
# Model kesintisinde koşunun durumu zaten diskte (oturum jsonl + notlar);
# park kaydı yalnızca "yarım bir iş var ve bekliyor" işareti. Açılışta
# görülürse koşu otomatik sürdürülür; kullanıcı keserse ya da iş biterse
# silinir.


def read_park(state_dir: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads((state_dir / PARK_DOSYASI).read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) and raw.get("session") else None
    except (OSError, ValueError):
        return None


def write_park(state_dir: Path, session_id: str, reason: str) -> None:
    (state_dir / PARK_DOSYASI).write_text(
        json.dumps({"session": session_id, "ts": time.time(),
                    "reason": (reason or "")[:300]}, ensure_ascii=False),
        encoding="utf-8")


def clear_park(state_dir: Path) -> None:
    try:
        (state_dir / PARK_DOSYASI).unlink(missing_ok=True)
    except OSError:
        pass


# -- yetim yardımcılar ---------------------------------------------------
#
# Uygulama kapanınca arka planda koşan yardımcılar süreçle birlikte ölür:
# ana oturumun günlüğünde subagent_start olur ama subagent_end olmaz.
# Kullanıcıya hiçbir şey söylenmezse sabah "ne oldu bilmiyorum" kalıyor.
# Açılışta bu iz taranır (yetim_tara), kullanıcıya ve modele bir kez haber
# verilir, çocuk günlüğüne subagent_end(orphaned=True) düşülür
# (yetim_isaretle) — ikinci açılış aynı yetimi yeniden bildirmesin.

# Taramanın dosya tavanı: son bu kadar oturum günlüğüne bakılır. Yıllık bir
# arşivi her açılışta baştan sona okumanın alemi yok; yetimler doğaları
# gereği en son oturumlardadır.
YETIM_TARAMA_TAVANI = 40


def _gunluk_oku(path: Path) -> list[dict[str, Any]]:
    """Oturum günlüğünü ham satırlar halinde okur — en iyi çaba.

    Sert kapanan bir süreç son satırı yarım bırakmış olabilir; bozuk satır
    sessizce atlanır. `EventLog` burada bilerek kullanılmıyor: o bozuk
    satırda ValueError fırlatıyor ve açılış taraması bir teşhis, tamir değil.
    """
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict):
            out.append(ev)
    return out


def _cocuk_gunlugu_mu(events: list[dict[str, Any]]) -> bool:
    """Bir günlük çocuk (alt ajan) oturumuna mı ait?

    Çocuk oturumun ilk notlarından biri parent'lı subagent_start — ana
    oturumdaki aynı adlı notta parent değil session (çocuğun kimliği) var.
    """
    return any(
        ev.get("content") == "subagent_start" and (ev.get("meta") or {}).get("parent")
        for ev in events
    )


def yetim_tara(sessions_dir: Path | str) -> list[dict[str, str]]:
    """Geçen oturum(lar)dan yetim kalan yardımcıları bulur.

    Ana oturum günlüklerinde subagent_start olup karşılığında subagent_end
    olmayan çocuklar aranır (çocuk oturum kimliği start notunun meta'sında).
    Eşleşme kimlikle; eski kayıtlar (end notunda session yokken) başlıkla
    eşleşir. Çocuğun kendi günlüğünde herhangi bir subagent_end (normal
    bitiş ya da önceki açılışın orphaned işareti) varsa yetim sayılmaz.

    En iyi çaba: okunamayan/bozuk günlükte sessizce boş liste — açılış
    taraması uygulamayı düşürmemeli.
    """
    try:
        files = sorted(Path(sessions_dir).glob("*.jsonl"))[-YETIM_TARAMA_TAVANI:]
        adaylar: list[dict[str, str]] = []
        for path in files:
            try:
                events = _gunluk_oku(path)
            except OSError:
                continue
            if _cocuk_gunlugu_mu(events):
                continue
            # Bu ana oturumun açtığı çocuklar: end'i görülen start düşer.
            starts: list[dict[str, str]] = []
            for ev in events:
                if ev.get("kind") != "meta":
                    continue
                meta = ev.get("meta") or {}
                if ev.get("content") == "subagent_start" and meta.get("session"):
                    starts.append({
                        "title": str(meta.get("title") or ""),
                        "session": str(meta["session"]),
                    })
                elif ev.get("content") in ("subagent_end", "subagent_failed"):
                    # subagent_failed da bir kapanış: çöken yardımcı zaten
                    # bildirildi, bir de yetim diye anons edilmesin.
                    sid = str(meta.get("session") or "")
                    title = str(meta.get("title") or "")
                    for i, s in enumerate(starts):
                        if s["session"] == sid or (not sid and s["title"] == title):
                            del starts[i]
                            break
            adaylar.extend(starts)

        yetimler: list[dict[str, str]] = []
        for aday in adaylar:
            child = Path(sessions_dir) / f"{aday['session']}.jsonl"
            if not child.is_file():
                # Oturum dosyası hiç doğmamış: sürdürülecek bir iz de yok.
                continue
            try:
                child_events = _gunluk_oku(child)
            except OSError:
                continue
            if any(ev.get("content") == "subagent_end" for ev in child_events):
                continue   # önceki açılışta işaretlenmiş ya da kapanmış
            yetimler.append(aday)
        return yetimler
    except Exception:
        return []


def yetim_isaretle(sessions_dir: Path | str, yetimler: list[dict[str, str]]) -> None:
    """Yetimlerin çocuk günlüğüne subagent_end(orphaned=True) düşer.

    İşaret bir mezar taşı: bir sonraki açılış aynı yardımcıyı yeniden
    "yarım kaldı" diye bildirmesin. Oturum diskte duruyor — `task_say`
    istenirse yine diriltebiliyor.
    """
    from .events import EventLog

    for y in yetimler:
        path = Path(sessions_dir) / f"{y['session']}.jsonl"
        try:
            log = EventLog(path)
            log.note("subagent_end", title=y["title"], orphaned=True)
            log.close()
        except Exception:
            # Sert kapanış son satırı yarım bırakmış olabilir ve EventLog
            # bozuk satırda açılmıyor. İşaret yine de düşmeli — yoksa aynı
            # yetim her açılışta yeniden bildirilir. Satır elle ekleniyor;
            # tarama (yetim_tara) ham JSON okuduğu için bunu görüyor.
            try:
                with path.open("a", encoding="utf-8") as fh:
                    fh.write("\n" + json.dumps({
                        "seq": -1, "ts": time.time(), "kind": "meta",
                        "role": None, "content": "subagent_end",
                        "meta": {"title": y["title"], "orphaned": True},
                    }, ensure_ascii=False) + "\n")
            except OSError:
                continue   # tek bozuk günlük diğerlerini engellemesin


@dataclass(slots=True)
class AgentIO:
    """Harness ile arayüz arasındaki tek temas yüzeyi."""

    on_text: Callable[[str], None] = lambda _: None
    on_thinking: Callable[[str], None] = lambda _: None
    on_tool_start: Callable[[str, dict[str, Any]], None] = lambda *_: None
    on_tool_end: Callable[[str, bool, int], None] = lambda *_: None
    on_notice: Callable[[str], None] = lambda _: None
    # Model kesintisinde bekleme durumunun YAPISAL kanalı. Arayüz bunu
    # çalışma şeridinde tek canlı satır olarak çizer (geri sayım, deneme
    # sayacı, katlanır ayrıntı) — sohbete ham hata duvarı basılmaz.
    # None kalırsa (CLI, testler) eski düz-metin on_notice yolu işler.
    # Sözleşme: {"kip": "deneme"|"park"|"bitti"|"iptal",
    #            "deneme": int, "toplam": int, "saniye": int, "detay": str}
    on_wait: Callable[[dict[str, Any]], None] | None = None
    on_usage: Callable[[dict[str, int]], None] = lambda _: None
    # Modelin koyduğu oturum başlığı — kenar listesi anında güncellenir.
    on_session_title: Callable[[str, str], None] = lambda *_: None  # sid, ad
    # Bütçe freni. Her model çağrısından ÖNCE soruluyor: boş dize "sınır
    # yok ya da aşılmadı", dolu dize ise sohbete basılacak tek satır ve
    # "dur" emri. Fiyat bilgisi harness'ta değil köprüde duruyor (bkz.
    # desktop.Bridge._butce_freni) — döngü yalnızca kararı soruyor, tur
    # yolunda ağ isteği ya da fiyat tablosu okuması yapmıyor.
    butce_freni: Callable[[], str] = lambda: ""
    # Alt ajan (orkestra) kanalları: bir alt ajan doğduğunda, bir araç
    # çağırdığında ve bittiğinde. Arayüz bunları canlı kanal olarak çiziyor;
    # ana sohbete karışmadan "kimin ne yaptığı" görünür oluyor. Varsayılan
    # boş: alt ajan kullanmayan çağıranlar (testler, salt-metin) etkilenmiyor.
    on_child_start: Callable[[str, str, str, bool], None] = lambda *_: None  # title, model, id, bg
    on_child_tool: Callable[..., None] = lambda *_: None  # title, tool, phase, hedef=""
    on_child_end: Callable[[str, bool, int, int, str, str], None] = lambda *_: None  # title, ok, turns, tools, id, özet
    # Alt ajan bekleme/retry (model boş yanıt vb.) — panel kanalı.
    on_child_wait: Callable[[dict[str, Any]], None] | None = None
    approve: Callable[[ToolSpec, dict[str, Any]], Awaitable[bool]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.approve is None:
            async def deny_all(spec: ToolSpec, args: dict[str, Any]) -> bool:
                return False

            self.approve = deny_all


@dataclass(slots=True)
class ChildHandle:
    """Bir yardımcının defter kaydı.

    Senkron yardımcı da buraya yazılıyor (task_say bitmiş bir yardımcıyı
    sürdürebilsin diye) ama asıl müşteri arka plan yardımcısı: `task`
    aracı hemen dönüyor, iş bu kayıt üzerinden izleniyor ve bitince
    sonucu buradan bildiriliyor.
    """

    id: str
    title: str
    model: str
    # "yardımcı": model koşan alt ajan · "iş": arka plan süreci (uzun komut).
    # İkisi aynı defteri ve aynı bildirim yolunu paylaşıyor.
    kind: str = "yardımcı"
    arka_plan: bool = False
    session_id: str = ""
    state: str = "kosuyor"          # kosuyor | bitti | hata
    sonuc: str = ""
    # Ne zaman başladı. Kayıt işin başladığı anda kuruluyor, o yüzden
    # varsayılan "şimdi" doğru cevap: görevler paneli süreyi buradan
    # canlı sayıyor ("2 dk 14 sn"). Yetim kayıtlarında (geçen oturumdan
    # devralınan) gerçek başlangıç bilinmiyor; panel orada süre çizmiyor.
    baslangic_ts: float = field(default_factory=time.time)
    bitis_ts: float = 0.0
    # Sonuç ana ajana duyuruldu mu. Senkron yolda araç sonucu zaten döndü;
    # arka planda tur başındaki bildirim notu bunu True yapar.
    bildirildi: bool = False
    # Arka plan görevinin referansı: referanssız asyncio.Task çöp
    # toplayıcıya gidebilir ve iş sessizce kaybolur.
    task: asyncio.Task | None = None
    # Koşarken canlı ajan nesnesi (task_say notu buna gidiyor); bitince None.
    agent: "Agent | None" = None
    # Çocuğun KENDİ kesme bayrağı. Ananınkini paylaşmak olmuyordu: ana her
    # `run`da bayrağını tazeliyor ve arka plandaki çocuk eski bayrakta
    # sahipsiz kalıyordu. Ana `interrupt()` hepsini türev olarak kurar.
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    # Zamanlanmış görev kimliği (varsa): bitince deftere yazılıyor.
    schedule_id: str = ""
    # Sessiz: bitince ana ajan sürdürme turu AÇMAZ — rapor panellerde kalır.
    # Zamanlanmış işler için: sohbet Q&A değil, görev alanı.
    sessiz: bool = False
    # task_runs arşivindeki koşum kimliği.
    run_id: str = ""
    # Otomasyon workflow kimliği (varsa).
    workflow_id: str = ""
    # Bitişte açılacak teslimat: {kind: app|artifact|json|text, url?, body?}
    deliverable: dict[str, Any] | None = None
    # Canlı panel: son araç adı / model bekleme durumu.
    son_arac: str = ""
    son_hedef: str = ""
    wait: dict[str, Any] | None = None
    # Koşum ölçümü: {girdi, cikti, cagri} — chat dock ile aynı birimler.
    usage: dict[str, int] = field(
        default_factory=lambda: {"girdi": 0, "cikti": 0, "cagri": 0})
    # Mid-run task_runs.patch_run throttle.
    last_patch_ts: float = 0.0
    # Kaç araç çağrısı başladı (panel + koşum arşivi).
    tools_count: int = 0


@dataclass(slots=True)
class TurnStats:
    turns: int = 0
    tool_calls: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    interrupted: bool = False
    stop_reason: str | None = None
    # Art arda kaç model çağrısı hata verdi. Başarılı turda sıfırlanır;
    # geri çekilme merdiveni ve park kararı buna bakıyor.
    api_errors: int = 0
    # Tavana carpip surdurulen tur sayisi.
    continuations: int = 0
    # Kapanis turu verildi mi. Bir kez: yoksa kilitlenen dongu kapanis
    # turunda da kilitlenir ve ayni yere geri gelinir.
    closing: bool = False
    # Model bu turda kaç kez araç çağrısını DÜZ METİN olarak yazdı
    # (gerçek çağrı yerine XML). Tekrar ederse not sertleşiyor.
    sahte_cagri: int = 0
    # Kırmızı kapısı bu turda bir kez açıldı mı. En fazla bir kez: model
    # ikinci turda yine bitirmek isterse bırakılıyor — sonsuz döngü yok.
    kirmizi_uyarildi: bool = False
    kabul_uyarildi: bool = False
    test_uyarildi: bool = False
    # Teslim-edileni-çalıştır kapısı bu turda açıldı mı. Aynı sebeple bir kez.
    giris_uyarildi: bool = False
    # Alt ajan: max retry sonrası model hatası metni (park yerine).
    fail_reason: str | None = None


def _without_numbers(text: str) -> str:
    """Önyükleme sorgusundan sayıları atar.

    Bir cihaz eklemek isteyen mesaj IP, port ve register adresi taşıyor ve
    bunlar zihindeki her sayılı kaydı çekiyor. Kullanıcının gördüğü şey
    "modbus cihazı ekle" derken BTC fiyat ölçümlerinin taranmasıydı.
    """
    return _NUMERIC.sub(" ", text or "").strip()


class Agent:
    def __init__(
        self,
        *,
        config: Config,
        session: Session,
        registry: ToolRegistry,
        client: Backend,
        io: AgentIO,
        permissions: PermissionEngine | None = None,
        policy: ContextPolicy | None = None,
        mind: Any = None,
        depth: int = 0,
        cancel: asyncio.Event | None = None,
        schedule: Any = None,
        lens: Any = None,
    ) -> None:
        self.config = config
        self.session = session
        self.registry = registry
        self.client = client
        self.io = io
        self.mind = mind
        # 0 ana ajan, 1 alt ajan. Derinlik `task` aracının varlığını da
        # belirliyor.
        self.depth = depth
        # Zamanlanmış görev defteri; `schedule` aracı buradan okuyor.
        self.schedule = schedule
        # Yerel kameranın tamponu; `look` aracı buradan kare alıyor.
        self.lens = lens
        self.camera_power: Any = None
        # Kulak ve izleyici masaüstü tarafında sonradan bağlanıyor
        # (açılışta ajan onlardan önce kuruluyor); `senses` aracı buradan
        # erişiyor.
        self.ear: Any = None
        self.watcher: Any = None
        self.permissions = permissions or PermissionEngine.from_config(config.permissions)
        self.policy = policy or ContextPolicy(config.context)
        # Kesme bayrağı dışarıdan verilebiliyor: alt ajan ana ajanınkini
        # paylaşıyor. Paylaşmasa kullanıcı durdur dediğinde arkada
        # çalışmaya devam ederdi.
        self.cancel = cancel or asyncio.Event()
        self._owns_cancel = cancel is None
        # Ruh oturum başında bir kez yüklenir ve oturum boyunca sabit kalır.
        # Sabit olması şart: sistem promptunun parçası, ortasında değişirse
        # o noktadan sonraki tüm önbellek düşer. Oturum içinde kaydedilen
        # yeni hatıralar bir sonraki açılışta ruha girer.
        self.soul = mind.soul(persona=prompt.read_persona(config)) if mind else None
        self._system = prompt.build(config, registry, soul=self.soul)
        self._last_goal_digest = self.mind.goal_digest() if mind else ""
        # Son turun kullanim raporu. Sikistirma karari buna bakiyor;
        # istekten once token saymak ekstra bir tur maliyeti demekti.
        self._last_usage: dict[str, int] = {}
        # Dar pencereli model: sistem promptu kısalıyor, araç
        # açıklamaları tek paragrafa iniyor, hatırlama önyüklemesi
        # azalıyor. 4096 token'lık bir modelde bunlar olmadan konuşmaya
        # hiç yer kalmıyor.
        self.lean = prompt.is_lean(config)
        # Küçük aile: tam şema (~11k token) yerine kısa şema (~6k). Dar
        # pencere zaten kısaydı; flash sınıfı geniş pencerede de kısayı
        # hak ediyor — kıyasta tur başına taşınan yükün ana kalemi buydu.
        self.kisa_sema = self.lean or prompt.kucuk_aile(config.model.name)
        # Yanlış pencere ayarı bir kez söylenip bırakılıyor: her turda
        # tekrarlamak uyarıyı gürültüye çeviriyor.
        self._window_warned = False
        # Alt ajanlar için kurulan ek istemciler; model adına göre
        # saklanıyor ki aynı model üç kez istendiğinde üç bağlantı
        # havuzu açılmasın.
        self._clients: dict[str, tuple[Any, Config]] = {}
        # Anlık encode'da peş peşe aynı metni iki kez yazmayı önler.
        self._last_encoded: str = ""
        # Bu oturumda zaten öne konmuş hatıralar. Eski not geçmişte DURUYOR
        # (mesajlar her istekte baştan oynatılıyor); aynı hatırayı yeniden
        # enjekte etmek modele yeni bilgi vermez, yalnızca token yakar.
        # Sıkıştırmada sıfırlanır — notlar özete katlanınca hak geri gelir.
        #
        # Küme ruhla başlıyor: ruhun TAM GÖVDEYLE prompta koyduğu kayıtlar
        # (user/preference/lesson/voice) da "zaten bağlamda". Ölçüldü
        # (scale_bench): aynı isabetle sorgu başına ~%9 daha az token ve
        # "hava nasıl" sorusuna çay-tercihi türü sızıntıların bir kısmı
        # kendiliğinden susuyor. Yordamlar girmiyor — ruhta yalnız başlıkları
        # var, gövdeleri önyüklemede hâlâ değerli.
        self._primed: set[str] = self._soul_resident()
        # Alt ajan kapısı: aynı anda en fazla `max_agents` yardımcı koşar.
        # Sınırı aşan spawn reddedilmiyor, sıraya giriyor — model beş iş
        # dağıttığında beşi de yapılır, ama makine ezilmeden. Araç
        # sınırından (max_parallel) ayrı çünkü bir alt ajan tek araçtan
        # çok daha ağır.
        self._agent_gate = asyncio.Semaphore(
            max(1, getattr(config.context, "max_agents", 3)))
        # Yardımcı defteri: id → kayıt. Arka planda koşanlar, bitmişler ve
        # (task_say için) senkron koşmuş olanlar burada.
        self._children: dict[str, ChildHandle] = {}
        # Tur ortası gelen kutusu: koşan tur bitmeden araya giren kullanıcı
        # mesajları (ve çocukta: task_say notları). Her turun başında
        # boşaltılıp harness notu olarak geçmişe giriyor.
        self._inbox: deque[str] = deque()
        # Bir yardımcı bitince köprüye (varsa) haber: ana ajan boştaysa
        # köprü bir sürdürme turu açar. Masaüstü katmanı bağlıyor.
        self.on_children_settled: Callable[[], None] | None = None
        # Model kesintisinde her yeniden denemeden önce çağrılır. Köprü
        # buraya bekleyen model/ayar değişikliğini uygulayan çağrıyı bağlar:
        # bozuk adres/anahtar düzeltildiyse yeni istemci ancak böyle devreye
        # girer (normalde değişiklik tur SONUNU bekler, parklı tur bitmez).
        self.on_retry_wait: Callable[[], None] | None = None
        # İş park edildi mi (model ulaşılamıyor, bekliyor).
        self._parked = False
        # Zihin yazma refleksi (bkz. _zihin_kapisi): bu turda model kendi
        # defterine yazdı mı, ve en son hangi cümle için dürtüldü.
        self._zihin_yazildi = False
        self._son_durtu = ""
        # Kırmızı defteri: doğrulama aracı → o aracın son KIRMIZI izi.
        # Araç başına tutuluyor ki model düzeltip yeniden koşturunca kayıt
        # temizlensin — yeşile dönen bir koşum artık kırmızı değil. Her
        # kullanıcı turunda sıfırlanıyor (bkz. run).
        self._kirmizi: dict[str, str] = {}
        # Teslim defteri: bu turda YAZILAN dosya yolları ve bu turda
        # KOŞULAN komutların metni. Kapı ikisini karşılaştırıyor —
        # yazdığın ama hiç çalıştırmadığın bir giriş noktası var mı?
        # Her kullanıcı turunda sıfırlanıyor (bkz. run).
        self._yazilan: list[str] = []
        self._komutlar: list[str] = []
        # Hata kalıbı sayacı (koşu başına): aynı kalıba İKİNCİ düşüş derstir.
        self._hata_kalibi: dict[str, int] = {}
        self._kapsul_yazildi = False

    def _soul_resident(self) -> set[str]:
        """Ruhun tam gövdesiyle prompta koyduğu kayıtların kimlikleri."""
        if self.soul is None:
            return set()
        return {
            m.id
            for group in (self.soul.user, self.soul.preferences,
                          self.soul.lessons, self.soul.voice)
            for m in group
        }

    @property
    def system_prompt(self) -> str:
        return self._system.rendered()

    def reconfigure(self, config: Config) -> None:
        """Ayar değişince çekirdeği yeniden kurar — yeniden başlatmadan.

        Model değiştiğinde pencere boyutu da değişebiliyor (200k Claude ↔
        4096 yerel): o zaman `lean` kararı, gönderilen araç şemaları ve
        sistem promptundaki ortam/duyu/cihaz özeti hepsi değişmeli. İstemciyi
        `Bridge` zaten değiştiriyor; burada geri kalanı tazeliyoruz.

        **Ruh dokunulmadan kalıyor.** Kimlik bloğu oturum boyunca sabit
        olmalı (önbellek önek eşleşmesi ona bağlı) ve oturum ortasında
        öğrenilen kullanıcı adı, tanışma bağlamı kaybolmamalı. Yalnızca
        `core` yeniden kuruluyor; `soul` aynı nesne olarak geçiyor.

        Tur ortasında çağrılmamalı: akan bir isteğin altından şemaları
        çekmek o cevabı bozar. `Bridge` bunu tur bittiğinde uyguluyor.
        """
        self.config = config
        self.policy = ContextPolicy(config.context)
        self.lean = prompt.is_lean(config)
        self.kisa_sema = self.lean or prompt.kucuk_aile(config.model.name)
        self._system = prompt.build(config, self.registry, soul=self.soul)

    def interrupt(self) -> None:
        """Dur: ana turu VE koşan tüm yardımcıları durdurur.

        Kullanıcı beklentisi "dur = her şey durur". Yardımcıların bayrağı
        ayrı (bkz. ChildHandle.cancel) ama karar türev: buradan hepsine
        yayılıyor.
        """
        self.cancel.set()
        for handle in self._children.values():
            if handle.state == "kosuyor":
                handle.cancel.set()

    def take_note(self, note: str, *, encode: str = "") -> None:
        """Koşan turun bir sonraki adımına girecek harness notu.

        Tur ortasında araya giren kullanıcı mesajı (köprüden) ve koşan bir
        yardımcıya `task_say` ile verilen yön buradan giriyor. Not kuyruğu
        her turun başında boşaltılır; tur o sırada bitmişse bir adım daha
        verilir ki mesaj kaybolmasın.

        `encode` doluysa metin anlık belleğe de yazılır — araya giren söz
        de söylenmiş bir sözdür.
        """
        self._inbox.append(note)
        if encode:
            self._encode_turn("kullanıcı", encode)

    def inbox_full(self) -> bool:
        """Gelen kutusu taştı mı? Köprü doluysa eski kuyruk yoluna düşer."""
        return len(self._inbox) >= 8

    def _arm(self) -> None:
        """Yeni bir istek için kesmeyi sıfırlar.

        Bayrak dışarıdan geldiyse dokunulmuyor: onu sıfırlamak, paylaşan
        tarafın kesme kararını sessizce iptal etmek olurdu.
        """
        if self._owns_cancel:
            self.cancel = asyncio.Event()

    # -- ana akış ------------------------------------------------------

    async def run(self, user_input: str, image: str = "") -> TurnStats:
        """Bir kullanıcı isteğini baştan sona koşturur.

        `image` verilirse (base64 veri adresi) mesaja görüntü bloğu olarak
        ekleniyor — kameradan gelen kare bu yoldan giriyor. Model görüntü
        kabul etmiyorsa sağlayıcı katmanı bunu anlaşılır bir hataya çeviriyor.
        """
        self._arm()
        if image:
            self.session.add_user_blocks(_with_image(user_input, image))
        else:
            self.session.add_user_text(user_input)
        # Cevap dili: kullanıcının BU mesajının dili. Kimlik bloğundaki
        # kural tek başına yetmiyordu — sistem promptunun tamamı, anıların
        # çoğu ve geçmiş turlar Türkçe olduğu için model İngilizce yazana
        # bile Türkçe cevap veriyordu (canlı yara, 02.09). Hatırlatma tur
        # başına, modelin EN SON okuduğu yerde: yakınlık kuralı kazandırıyor.
        self._dil_notu(user_input)
        # Kullanıcının söylediği o an belleğe geçiyor: gece değil, şimdi.
        self._encode_turn("kullanıcı", user_input)
        self._prime_recall(user_input)
        # Yazma refleksinin kapısı: bu turda model kendi defterine yazdı mı?
        self._zihin_yazildi = False
        # Plan refleksi: iş büyük görünüyorsa modelin önüne tek satır not.
        # İLK model çağrısından ÖNCE ve tur başına bir kez — sonradan
        # hatırlatmanın anlamı yok, plan sıradan sonra yazılmaz.
        self._plan_refleksi(user_input)
        # Kırmızı defteri her kullanıcı turunda sıfırdan: "yalnız BU TURDA
        # üretilmiş kırmızı" sayılıyor, geçen turun kırmızısı değil.
        self._kirmizi.clear()
        # Teslim defterleri de her turda sıfırdan: geçen turda yazılıp
        # çalıştırılmış bir dosya bu turun borcu değil.
        self._yazilan.clear()
        self._komutlar.clear()
        self._hata_kalibi.clear()
        self._kapsul_yazildi = False
        stats = await self._drive()
        self._zihin_kapisi(user_input)
        return stats

    def _plan_refleksi(self, user_input: str) -> None:
        """Büyük/ucu açık istekte plan sırasını modelin önüne koyar.

        Yalnız ana ajanda (`depth == 0`): alt ajana verilen yönerge zaten
        dar ve tanımlı bir iş, ondan modül planı istemek gürültü.
        """
        if self.depth or not buyuk_is(user_input):
            return
        # Plan işin BAŞININ işi. İş zaten yürüyorken (defterde açık madde
        # ya da oturumda önceki alışveriş) dürtü saçmalıyor: canlıda 240
        # turluk koşunun ortasında "sıfırdan" plan kartı çıktı — 97 dosya
        # değişmişken. Yürüyen işte kapılar (kabul/giriş) devrede zaten.
        try:
            if self.mind is not None and self.mind.goals(active_only=True):
                return
        except Exception:
            pass
        if sum(1 for m in self.session.messages()
               if m.get("role") == "user") > 1:
            return
        self.session.add_harness_note(PLAN_NOTU)
        self.session.log.note("plan_refleksi")

    def _teslim_izi(self, tool: str, args: dict[str, Any]) -> None:
        """Bu turda ne yazıldı, ne koşuldu — kapının okuduğu iki defter."""
        if tool in ("write_file", "edit_file"):
            if yol := str(args.get("path") or "").strip():
                self._yazilan.append(yol)
        elif tool in ("shell", "kos"):
            # `kos` komutu kendi bulur; onun da neyi koşturduğu argümanda
            # olmayabiliyor, o yüzden yol/desen alanları da toplanıyor.
            for alan in ("command", "cmd", "path", "hedef", "argv"):
                if (deger := args.get(alan)) is not None:
                    self._komutlar.append(str(deger))

    def _kosulmayan_test(self) -> str:
        """Yazılıp hiç koşulmamış bir test dosyası varsa adı, yoksa boş.

        Ölçülen yara (28.08 dokuz-görev, o2): test dosyası yazıldı, hiç
        koşulmadı, KIRMIZI çıktı ve teslim edildi — kırmızı kapısı ancak
        koşulan testi görür. Test adı herhangi bir komutta geçtiyse (pytest
        yolu toplu koşturur: `pytest`, `pytest .`) koşulmuş sayılır; çıplak
        `pytest`/`node --test` çağrısı da tümünü kapsar.
        """
        komut_metni = "\n".join(self._komutlar)
        # Toplu koşucular: çıplak pytest / node --test her test dosyasını
        # kapsar — dosya adı komutta geçmese de koşulmuş sayılır.
        toplu = ("pytest" in komut_metni or "node --test" in komut_metni
                 or "node --run" in komut_metni)
        for yol in self._yazilan:
            ad = Path(yol).name
            if not (ad.startswith("test_") or ad.endswith((".test.js", ".spec.js"))
                    or ad.endswith("_test.py")):
                continue
            if toplu or (ad and ad in komut_metni):
                continue
            return ad
        return ""

    def _test_kapisi(self, stats: TurnStats, blocks: list[dict[str, Any]]) -> bool:
        """Yazılmış-koşulmamış testle "bitti" denirse bir tur geri verilir."""
        if stats.test_uyarildi or self.depth:
            return False
        if not bitti_iddiasi(_text_of_blocks(blocks)):
            return False
        dosya = self._kosulmayan_test()
        if not dosya:
            return False
        stats.test_uyarildi = True
        self.session.log.note("test_kapisi", dosya=dosya)
        self.session.add_harness_note(TEST_NOTU.format(dosya=dosya))
        return True

    def _kosulmayan_giris(self) -> str:
        """Yazılıp hiç çalıştırılmamış bir giriş noktası varsa onun yolu.

        Dosya diskten okunuyor: "çalıştırılmak üzere ilan edildi mi"
        sorusunun cevabı içeriğinde. Okunamayan dosya sayılmıyor —
        emin olamadığımız bir şey için modeli dürtmek yanlış.
        """
        komut_metni = "\n".join(self._komutlar)
        for yol in self._yazilan:
            p = Path(yol)
            if p.suffix.lower() not in _KOSULABILIR_UZANTI:
                continue
            # Adı herhangi bir komutta geçtiyse çalıştırılmış sayılıyor.
            if p.name and p.name in komut_metni:
                continue
            try:
                metin = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if giris_noktasi_mi(metin):
                return p.name
        return ""

    def _giris_kapisi(self, stats: TurnStats, blocks: list[dict[str, Any]]) -> bool:
        """Yazılan giriş noktası hiç çalıştırılmadan "bitti" deniyorsa bir tur daha.

        True dönerse tur SÜRÜYOR. Kırmızı kapısıyla aynı üç fren:
          * Ortada bu turda yazılmış, kendini çalıştırılabilir ilan eden ve
            hiç koşulmamış bir dosya olacak.
          * Cevap araçsız (`end_turn`) ve işi bitmiş ilan ediyor olacak —
            neyin eksik olduğunu zaten söyleyen dürüst bir cevap dürtülmez.
          * Tur başına EN FAZLA BİR KEZ.
        """
        if stats.giris_uyarildi or not self._yazilan:
            return False
        if not bitti_iddiasi(_text_of_blocks(blocks)):
            return False
        dosya = self._kosulmayan_giris()
        if not dosya:
            return False
        stats.giris_uyarildi = True
        self.session.log.note("giris_kapisi", dosya=dosya)
        self.session.add_harness_note(GIRIS_NOTU.format(dosya=dosya))
        return True

    def _kirmizi_kapisi(self, stats: TurnStats, blocks: list[dict[str, Any]]) -> bool:
        """Kırmızı bir koşumun üstüne "bitti" deniyorsa bir tur daha ver.

        True dönerse tur SÜRÜYOR. Üç fren var:
          * Ortada bu turda üretilmiş kırmızı bir koşum olacak.
          * Cevap araçsız olacak (`end_turn`) ve gerçekten bitmiş ilan
            edecek — kırmızıyı zaten söyleyen dürüst bir cevap dürtülmez.
          * Tur başına EN FAZLA BİR KEZ. Model ikinci turda yine bitirmek
            isterse bırakılıyor; sonsuz bir "hayır bitmedi" döngüsü, yarım
            bir cevaptan kötü.
        """
        if stats.kirmizi_uyarildi or not self._kirmizi:
            return False
        if not bitti_iddiasi(_text_of_blocks(blocks)):
            return False
        stats.kirmizi_uyarildi = True
        ozet = "; ".join(self._kirmizi.values())[:200]
        self.session.log.note("kirmizi_kapisi", ozet=ozet)
        self.session.add_harness_note(KIRMIZI_NOTU.format(ozet=ozet))
        return True

    def _kabul_kapisi(self, stats: TurnStats, blocks: list[dict[str, Any]]) -> bool:
        """Açık iş maddeleri varken "bitti" deniyorsa bir tur daha ver.

        Kırmızı kapısıyla aynı sözleşme: yalnız araçsız bitirme cevabında,
        tur başına EN FAZLA BİR KEZ, ve yalnız gerçekten açık madde varsa.
        Alt ajanlar muaf — defter ana koşunun.
        """
        if stats.kabul_uyarildi or self.depth or self.mind is None:
            return False
        if not bitti_iddiasi(_text_of_blocks(blocks)):
            return False
        try:
            acik = [g.text for g in self.mind.goals(active_only=True)]
        except Exception:
            return False
        if not acik:
            return False
        stats.kabul_uyarildi = True
        ozet = "; ".join(t[:60] for t in acik[:5])
        if len(acik) > 5:
            ozet += f"; (+{len(acik) - 5})"
        self.session.log.note("kabul_kapisi", acik=len(acik))
        self.session.add_harness_note(KABUL_NOTU.format(ozet=ozet))
        return True

    def _zihin_kapisi(self, user_input: str) -> None:
        """Tur sonu refleksi: kalıcı bir şey geçtiyse ve model yazmadıysa dürt.

        `_prime_recall`ın kardeşi ve tersi: o hatırlamayı, bu yazmayı
        sistemden tetikliyor. Not modelin ÖNÜNE konuyor (harness kanalı,
        `internal` — sohbette görünmez); kararı yine model veriyor.

        Üç fren var: model zaten yazdıysa dürtme (gereksiz), koku yoksa
        dürtme (gürültü), ve art arda dürtme (bıkkınlık) — kullanıcı yeni
        bir şey söylemedikçe not tekrarlanmıyor.
        """
        if self.depth or self.mind is None or self._zihin_yazildi:
            return
        if not kalici_koku(user_input):
            return
        alinti = _one_line(user_input)[:DURTU_ALINTI]
        if alinti == self._son_durtu:
            return   # aynı konuda ikinci kez dürtmek bıkkınlık
        self._son_durtu = alinti
        self.session.add_harness_note(ZIHIN_DURTUSU.format(alinti=alinti))
        self.session.log.note("zihin_durtusu")

    def _encode_turn(self, role: str, text: str) -> None:
        """Bir konuşma turunu **anlık** olarak aranabilir belleğe yazar.

        Fatih'in çekirdek şartı: "biri bir şey söylerken direk hafızada
        kalmalı" — gece değil, o an. İnsan hafızası da böyle kodlar
        (hipokampus tek seferde yazar); konsolidasyon ayrı ve yavaştır.

        Ekran-kartsız makinede hızlı olmalı ve öyle: imza saf hashing
        (torch yok), tam yazma yolu ~2 ms. Bu yüzden senkron çalışıyor,
        kullanıcı gecikme hissetmiyor. Kayıt `episode` türünde: küratörlü
        `mind_memory` olgularına karışmıyor (ruha ve kendiliğinden
        önyüklemeye girmiyor) ama `mind_recall` ile bulunabiliyor.

        Gürültü kapısı: çok kısa turlar ("evet", "tamam") ve selam yazılmaz;
        aynı metin peş peşe iki kez gelmişse atlanır. Bir yazma hatası
        konuşmayı ASLA düşürmemeli — bellek en fazla bir turu kaçırır.
        """
        if self.mind is None:
            return
        body = (text or "").strip()
        if len(body) < ENCODE_MIN_CHARS or not self._worth_recalling(body):
            return
        if body == self._last_encoded:
            return
        self._last_encoded = body
        try:
            self.mind.remember(
                body, kind="episode",
                title=f"{role}: {_one_line(body)}"[:140],
            )
        except Exception as exc:  # bellek yazımı konuşmayı düşürmemeli
            self.session.log.note("encode_turn_failed", error=str(exc))

    # Türkçeye özgü harfler: kaba ama yeterli bir ayrım. Amaç dili
    # "tespit etmek" değil, modele hangi dilde yazıldığını hatırlatmak.
    _TR_HARF = set("çğıöşüÇĞİÖŞÜ")

    def _dil_notu(self, user_input: str) -> None:
        """Bu turun cevap dili hatırlatmasını hazırlar.

        Oturum günlüğüne YAZILMIYOR — yalnız bu turun isteğine iliştiriliyor
        (bkz. `_dil_hatirlatmasini_ekle`). Günlüğe yazmak iki şeyi bozuyordu:
        "tur başına tek sistem notu" kotasını yiyip HATIRLAMA notunu
        (`_prime_recall`) engelliyor, ve kullanıcının dökümüne her turda
        teknik bir satır bırakıyordu.
        """
        metin = (user_input or "").strip()
        if len(metin) < 8:
            self._dil_hatirlatma = ""   # tek sözcükte dil çıkarımı anlamsız
            return
        if self._TR_HARF & set(metin):
            self._dil_hatirlatma = (
                "Bu turda kullanıcı TÜRKÇE yazdı — cevabın, ara anlatımların "
                "ve ürettiğin dosyaların içeriği Türkçe olsun.")
        else:
            self._dil_hatirlatma = (
                "This turn the user wrote in a language other than Turkish "
                "(most likely English). Reply in the SAME language they used — "
                "your answer, your progress notes and the contents of any file "
                "you produce. Do not switch to Turkish just because your "
                "instructions are written in Turkish.")

    def _dil_hatirlatmasini_ekle(self, prepared: Any) -> None:
        """Dil hatırlatmasını isteğin SONUNA geçici bir sistem mesajı olarak
        koyar. Önbellek kırılmıyor: son breakpoint'ten sonra duruyor."""
        not_ = getattr(self, "_dil_hatirlatma", "")
        if not not_:
            return
        try:
            prepared.messages.append(
                {"role": "system", "content": [{"type": "text", "text": not_}]})
        except Exception:
            pass

    def _prime_recall(self, user_input: str) -> None:
        """Kullanicinin mesajini zihinde arar ve bulduklarini onune koyar.

        Arac olarak birakmak yetmiyordu: model hatirlamasi gerektigini once
        fark etmek zorunda kaliyor, cogu zaman fark etmiyor ve zaten bildigi
        bir seyi bilmiyormus gibi cevapliyordu. Burada tersi yapiliyor —
        hatirlama sorulmadan calisiyor, model masaya oturdugunda ilgili
        hatiralar zaten onunde.

        Bunu yapmayi mumkun kilan sey hatirlamanin ucuz olmasi: ters indeks
        ve imza taramasi birkac milisaniye suruyor, ek model turu yok. Bir
        arac cagrisi olsaydi her mesaj icin bir gidis-donus daha demekti.
        """
        if self.mind is None or not self._worth_recalling(user_input):
            return
        try:
            # Taban yazıcı: sorgu aramadan önce yerel küçük modelle eşanlamlı
            # terimlere açılır (eşanlam sınıfı 0.50→1.00, isabet 0.87→0.93 —
            # scale_bench). Model yoksa zenginlestir sorguyu aynen döndürür.
            from .recall import taban
            query = taban.zenginlestir(user_input, getattr(self.config, "state_dir", None))
            limit = LEAN_PRIME_LIMIT if self.lean else RECALL_PRIME_LIMIT
            hits = select_prime(self.mind, query, limit=limit, ham=user_input)
        except Exception as exc:  # hatirlama coktuyse konusma yine surmeli
            self.session.log.note("recall_prime_failed", error=str(exc))
            return

        # Zaten öne konmuş hatıra yeniden enjekte edilmiyor: eski not
        # geçmişte duruyor, model onu hâlâ görüyor.
        hits = [h for h in hits if h.item.id not in self._primed]
        if not hits:
            return
        self._primed.update(h.item.id for h in hits)
        self.session.add_system_note(prime_note(hits))
        # Gece tekrarı (recall/orgu.py) bu notu okuyor: önüne konan kayıt
        # da "dokunulmuş" sayılır — model onu gördü, o turda kullandı.
        self.session.log.note("prime", ids=[h.item.id for h in hits],
                              query=_one_line(user_input, 120))

        # Arayuz bu gezinmeyi de canlandirabilmeli: kullanici modelin neyi
        # nereden hatirladigini adim adim izliyor. Aracla yapilan
        # hatirlamayla ayni olay yayilıyor, arayuzde ayrimi yok.
        if trace := getattr(self.mind, "last_trace", None):
            # Taranan ile kullanılan aynı şey değil. Zihin bir sorguda
            # onlarca kayda dokunuyor ve hepsini ekranda yakmak "her
            # şeyi karıştırdı" gibi duruyor — oysa önüne konan yalnızca
            # süzgeçten geçenler.
            used = {hit.item.id for hit in hits}
            from .mind.tools import _adim_etiket
            self.session.log.note(
                "recall_trace",
                query=user_input,
                trace=[{**asdict(step), "used": step.node in used,
                        "label": _adim_etiket(self.mind, step.node)}
                       for step in trace],
            )

    def _uyanik_ters_tekrar(self, sonuc: str) -> None:
        """Sonuç anında sorumluluğu dağıtır ve dersi hemen yazar.

        Arka planda değil, tur içinde: tek oturumun tekrarı iki yüz düğümde
        elli milisaniyenin altında (ölçüldü, tests/test_awake.py). Bir hata
        olursa sohbet yine sürmeli — hafıza bakımı konuşmayı düşürmez.
        """
        if self.mind is None:
            return
        try:
            from .recall import awake

            awake.on_result(self.mind.store, self.session.log.path, sonuc,
                            log=self.session.log)
        except Exception as exc:
            self.session.log.note("uyanik_tekrar_failed", error=str(exc))

    def _worth_recalling(self, text: str) -> bool:
        return worth_recalling(text)

    async def resume_after_interrupt(self) -> TurnStats:
        """Kesme sonrası karşılıksız kalanları kapatıp devam eder."""
        self._arm()
        self._settle_pending()
        return await self._drive()

    async def _drive(self) -> TurnStats:
        stats = TurnStats()
        ctx = ToolContext(
            config=self.config,
            session=self.session,
            cancel=self.cancel,
            # Alt ajanın alt ajanı olmuyor: None geçince `task` aracı
            # kendini kullanılamaz ilan ediyor. Aynı sınır arka plan ve
            # yönlendirme uçları için de geçerli.
            spawn=self._spawn if self.depth < MAX_DEPTH else None,
            spawn_bg=self._spawn_bg if self.depth < MAX_DEPTH else None,
            child_say=self._child_say if self.depth < MAX_DEPTH else None,
            child_status=self._child_status if self.depth < MAX_DEPTH else None,
            # Uzun süreçler yalnız ana ajanda arka plana alınabiliyor: alt
            # ajan işi bitmeden ölürse bildirimin gideceği kimse kalmaz.
            job_bg=self._job_bg if self.depth < MAX_DEPTH else None,
            schedule=self.schedule,
            run_workflow=self.run_workflow if self.depth < MAX_DEPTH else None,
            lens=self.lens,
            ear=self.ear,
            watcher=self.watcher,
            camera_power=getattr(self, "camera_power", None),
        )
        callbacks = Callbacks(
            on_text=self.io.on_text,
            on_thinking=self.io.on_thinking,
            on_tool_start=lambda name: None,
        )

        while stats.turns < HARD_TURN_LIMIT:
            # Bütçe freni: bu oturum için konmuş üst sınıra ulaşıldıysa YENİ
            # bir model çağrısı yapılmıyor. Kesme mevcut yoldan gidiyor
            # (`interrupt`: koşan yardımcılar da duruyor) ve yarım iş
            # KAYBOLMUYOR — kullanıcı mesajı geçmişte, gelen kutusundaki
            # notlar yerinde, oturum olduğu gibi duruyor. Sınır yükseltilince
            # konuşma kaldığı yerden sürüyor.
            #
            # Yalnız ana ajanda: alt ajanın kendi turunu ayrıca kesmek,
            # ananın zaten kestiği işi iki kez kesmek olurdu.
            if self.depth == 0 and (fren := self.io.butce_freni()):
                self.session.log.note("butce_freni", detay=_clip(fren, 200))
                self.io.on_notice(fren)
                self.interrupt()
                stats.interrupted = True
                break

            stats.turns += 1

            # Uzun koşu kontrol noktası: eski sert tavan (60. turda dur)
            # yumuşak bir dürtüye çevrildi — ajan kısa bir ilerleme notu
            # yazar ve İŞ SÜRER. Gerçek fren kullanıcı + mutlak sigorta.
            if stats.turns > 1 and stats.turns % MAX_TURNS == 0:
                self.session.log.note("turn_checkpoint", turns=stats.turns)
                self.session.add_harness_note(CHECKPOINT_NOTE.format(turns=stats.turns))
                self.io.on_notice(
                    f"Uzun koşu: {stats.turns} tur — ilerleme notu istendi, iş sürüyor.")

            await self._relieve_pressure()
            self._sync_goals()
            # Bu arada biten yardımcılar ve araya giren kullanıcı mesajları
            # modelin önüne bu adımda konuyor: tur başında, istek gitmeden.
            self._drain_children()
            self._drain_inbox()
            # Bekleyen model değişimi: akan stream'i kesmeden, bir sonraki
            # çağrıdan itibaren yeni istemci (meşgulken de geçiş).
            if self.on_retry_wait is not None:
                try:
                    self.on_retry_wait()
                except Exception:
                    pass
            prepared = self.policy.prepare(self._system, self.session.messages())
            self._dil_hatirlatmasini_ekle(prepared)
            try:
                result = await self.client.turn(
                    prepared,
                    # Kapanis turu araçsız: tekrar araç çağırmasına izin vermek,
                    # kilitlenen döngünün bir turunu daha çalıştırmak demek.
                    [] if stats.closing else self.registry.api_schemas(brief=self.kisa_sema),
                    cancel=self.cancel,
                    callbacks=callbacks,
                )
            except Exception as exc:
                # Bağlantı hiç kurulamadı (adres kapalı, DNS, soket). Eskiden
                # buradan yükselen istisna koşuyu düşürüyordu; artık hata
                # yoluna girer ve yeniden dener.
                result = TurnResult(error=f"{type(exc).__name__}: {exc}")

            if result.interrupted:
                self.session.log.note("interrupted", stage="stream", dropped=result.partial_text)
                self.io.on_notice("Kesildi. Yarım kalan yanıt atıldı.")
                stats.interrupted = True
                break

            if result.error:
                self.session.log.note("api_error", detail=result.error)
                # Bozuk istek (400 vb.) yeniden denemekle düzelmez: eski
                # davranış. Geçici hata (bağlantı, 5xx, zaman aşımı, 429)
                # uzun işi ÖLDÜRMEZ: geri çekilerek dener, sonra park eder.
                if _fatal_error(result.error):
                    self.io.on_notice(result.error)
                    self._unpark()
                    break
                stats.api_errors += 1
                stats.turns -= 1   # deneme turdan sayılmaz; sigorta kaçmasın
                if await self._await_model(stats, result.error):
                    continue
                stats.interrupted = True
                break

            if stats.api_errors:
                # Kesinti atlatıldı: sayaç sıfır, park kaydı (varsa) kalksın.
                denemeler = stats.api_errors
                stats.api_errors = 0
                self._unpark()
                # Şerit varsa toparlanma da şeritte yaşar (tek yeşil satır);
                # sohbete ayrıca bildirim düşmez.
                if not self._bekleme_olayi(kip="bitti", deneme=denemeler):
                    self.io.on_notice("Model geri geldi — iş kaldığı yerden sürüyor.")

            report = cache_report(result.usage)
            stats.usage = report
            self._last_usage = report
            self.io.on_usage(report)

            # Boş içerikli asistan turu geçmişe yazılmaz: hem tur boşa gider
            # hem de boş content dizisi bir sonraki isteği bozabilir. Reddetme
            # (refusal) turları meşru olarak boş gelir; durum yine de aşağıda
            # işlenir.
            # Sahte araç çağrısı: model gerçek çağrı yerine XML'i DÜZ METİN
            # yazdı. Geçmişe girmesi doğru (model ne yaptığını görmeli) ama
            # kullanıcıya CEVAP DEĞİL — `internal` ile işaretleniyor, yoksa
            # oturum sürdürülünce ham XML ajan mesajı olarak geri gelirdi.
            sahte_metin = bool(
                result.content and result.stop_reason == "end_turn"
                and sahte_arac_cagrisi(_text_of_blocks(result.content)))

            if blocks := result.content:
                # `empty_turn`: model turu YALNIZCA akıl yürüterek bitirdi ve
                # sağlayıcı katmanı o muhakemeyi metin bloğuna çevirdi (bkz.
                # openai_backend: reasoning-only tur). Model kendi planını
                # görsün diye geçmişe giriyor — ama bu KULLANICIYA CEVAP
                # DEĞİL. `internal` işareti tam da bunun için: sohbete ve
                # döküme çıkmıyor (iç not sızıntısıyla aynı savunma hattı;
                # ham muhakemenin sohbete italik paragraflar hâlinde
                # düştüğü görüldü). Muhakeme kaybolmuyor: arayüzde katlı
                # "✻ Düşündü" başlığının altında yaşıyor.
                self.session.add_assistant(
                    blocks, usage=report,
                    internal=(result.stop_reason == "empty_turn" or sahte_metin))
                # Asistanın söylediği de anlık belleğe: bir ölçüm sonucu ya
                # da bir açıklama, sonra "az önce ne demiştin" ile bulunsun.
                self._encode_turn("dornick", _text_of_blocks(blocks))
            else:
                self.session.log.note("empty_assistant_turn", stop_reason=result.stop_reason)

            stats.stop_reason = result.stop_reason
            # Sahte araç çağrısı: model gerçek çağrı yerine XML'i düz metin
            # yazıp turu bitirdi. Cevap sayılmaz — düzeltme notuyla bir tur
            # daha veriliyor. Gerçek bir araç çağrısı VARSA (tool_use)
            # karışılmıyor: iş yürüyor demektir.
            if result.stop_reason == "end_turn" and self._sahte_cagriyi_duzelt(stats, blocks):
                continue
            # Kırmızıyken "bitti" deme kapısı: bu turda kırmızı bir koşum
            # varken model araçsız bir bitirme cevabıyla kapatmaya
            # çalışıyorsa bir tur daha veriliyor.
            if result.stop_reason == "end_turn" and self._kirmizi_kapisi(stats, blocks):
                continue
            # Teslim edileni çalıştırma kapısı: yeşil testle bitirilen ama
            # kullanıcının yazacağı komutu hiç koşmamış bir turu bir kez
            # geri çeviriyor. Kırmızı kapısından SONRA: kırmızı varsa asıl
            # söylenmesi gereken odur.
            if result.stop_reason == "end_turn" and self._giris_kapisi(stats, blocks):
                continue
            # Test kapısı: yazılan test dosyası koşulmadan tur kapanmaz.
            if result.stop_reason == "end_turn" and self._test_kapisi(stats, blocks):
                continue
            # Kabul kapısı: iş defterinde açık madde dururken "bitti" deniyor
            # — kapılar zincirinin sonuncusu, en genel olanı.
            if result.stop_reason == "end_turn" and self._kabul_kapisi(stats, blocks):
                continue
            if await self._handle_stop(result, ctx, stats):
                continue
            # Tur normal bitti ama kullanıcı bu arada araya yazdıysa mesaj
            # kaybolmamalı: not düşülür ve AYNI tur içinde bir adım daha
            # verilir (MAX_TURNS tavanı hâlâ geçerli).
            if result.stop_reason == "end_turn" and self._inbox and not self.cancel.is_set():
                self._drain_inbox()
                continue
            break

        else:
            # Mutlak sigorta: normal iş buraya çarpmaz (kontrol noktaları işi
            # sürdürür); burası kaçak döngünün son freni.
            self.io.on_notice(
                f"{HARD_TURN_LIMIT} turluk mutlak sigortaya ulaşıldı, koşu durduruldu.")
            self.session.log.note("turn_limit", limit=HARD_TURN_LIMIT)

        # Koşu bitti: park kaydı (kalmışsa) düşsün — açılışta bitmiş bir işi
        # yeniden sürdürmeye kalkmayalım.
        if self.depth == 0:
            self._parked = False
            clear_park(self.config.state_dir)
            # Koşunun izi kapsül olarak zihne: bir sonraki oturum keşfi atlar.
            self._is_kapsulu()
            # İlk alışveriş bittiyse başlığı model koysun (adsız oturumda).
            await self._oturum_basligi()
        return stats

    def _hata_dersi(self, calls: list[Any], blocks: list[dict[str, Any]]) -> None:
        """Araç hatalarını ders hafızasına köprüler (kullanıcının önerisi).

        İki yön: (1) aynı bilinen kalıba bu koşuda İKİNCİ düşüş kalıcı bir
        derse dönüşür — bir kez düşmek öğrenme, iki kez düşmek alışkanlıktır;
        (2) GEÇMİŞ oturumlardan o kalıp için ders varsa hatanın yanına
        "[Hafıza]" olarak iliştirilir — statik ipucu turu kurtarıyor, ders
        oturumlar arası taşıyor.
        """
        if self.mind is None or self.depth:
            return
        from .tools.shell import kabuk_ipucu
        adlar = {c.id: c.name for c in calls}
        for b in blocks:
            if not (isinstance(b, dict) and b.get("is_error")):
                continue
            metin = str(b.get("content") or "")
            arac = adlar.get(str(b.get("tool_use_id") or ""), "")
            anahtar = tarif = ""
            if arac == "edit_file" and "Aranan metin" in metin:
                anahtar = "edit-anchor"
                tarif = ("edit_file'a old metnini dosyanın GERÇEK halinden "
                         "kopyala: önce read_file, sonra düzenle; girinti ve "
                         "satır sonu birebir.")
            elif ipucu := kabuk_ipucu(metin):
                anahtar = "kabuk:" + ipucu[:24]
                tarif = ipucu
            if not anahtar:
                continue
            baslik = "araç dersi: " + anahtar
            # Geçmiş ders varsa hatanın yanına iliştir (bu koşuda bir kez).
            if self._hata_kalibi.get(anahtar, 0) == 0:
                try:
                    for hit in self.mind.recall(baslik, limit=3):
                        if hit.item.title == baslik and hit.item.session_id != self.session.id:
                            b["content"] = (metin + "\n\n[Hafıza] "
                                            + hit.item.content)
                            break
                except Exception:
                    pass
            sayi = self._hata_kalibi.get(anahtar, 0) + 1
            self._hata_kalibi[anahtar] = sayi
            if sayi != 2:
                continue   # ilk düşüş: ipucu yeter; üçüncü+: ders zaten var
            try:
                if any(h.item.title == baslik
                       for h in self.mind.recall(baslik, limit=3)):
                    continue
                self.mind.remember(
                    f"{arac or 'araç'} hatası tekrar etti — {tarif}",
                    kind="lesson", title=baslik)
                self.session.log.note("hata_dersi", anahtar=anahtar)
            except Exception:
                pass

    def _is_kapsulu(self) -> None:
        """Koşu sonunda mekanik iş kapsülü: ne istendi, ne üretildi, ne koştu.

        Ölçülen kazanç (28.08 hafıza deneyi B kolu): bir sonraki oturumda
        bu kapsül kendiliğinden hatırlanınca model keşif çağrısını atlıyor
        (−%24 token). Kapsül modelden değil defterden: uydurma riski yok.
        """
        if (self.mind is None or self.depth or self._kapsul_yazildi
                or not self._yazilan):
            return
        ilk = ""
        for m in self.session.messages():
            if m.get("role") == "user":
                g = m.get("content")
                ilk = g if isinstance(g, str) else _text_of_blocks(g or [])
                break
        if not ilk.strip():
            return
        dosyalar = []
        for yol in self._yazilan:
            ad = Path(yol).name
            if ad and ad not in dosyalar:
                dosyalar.append(ad)
        komutlar = [k.strip()[:80] for k in self._komutlar[-2:] if k.strip()]
        icerik = (_one_line(ilk)[:200]
                  + " — üretilen: " + ", ".join(dosyalar[:6])
                  + ((". çalıştırılan: " + "; ".join(komutlar)) if komutlar else "")
                  + ".")
        baslik = "iş kapsülü: " + _one_line(ilk)[:40]
        try:
            if any(h.item.title == baslik
                   for h in self.mind.recall(baslik, limit=3)):
                return
            self.mind.remember(icerik, kind="fact", title=baslik)
            self._kapsul_yazildi = True
            self.session.log.note("is_kapsulu", dosyalar=dosyalar[:6])
        except Exception:
            pass

    async def _oturum_basligi(self, on_izleme: str = "") -> None:
        """Adsız oturumun ilk alışverişinden kısa bir başlık üretir.

        Kullanıcı adının ilk 30 karakteri başlık değildir ("bana
        profesonel bir cms yapa ama plan oluştur..." diye listelenmesi
        canlı şikâyetti). Tek küçük çağrı; her hata sessizce yutulur —
        başlık süs, koşunun sonucu değil.

        `on_izleme`: koşu henüz kullanıcı mesajını günlüğe yazmadan
        paralel başlık üretirken (desktop._isle) metni buradan alır —
        aksi halde boş günlüğe bakıp sessizce vazgeçiyordu.
        """
        if self.depth or self.mind is None or self.cancel.is_set():
            return
        try:
            meta = (self.mind.session_meta() or {}).get(self.session.id) or {}
            if meta.get("ad"):
                return
            mesajlar = self.session.messages()
            # İlk denemede başlık üretilemeyebiliyor (küçük model boş/çöp
            # dönebiliyor, çağrı patlayabiliyor). Eski `> 2` kapısı tek bir
            # aksaklıkta sonsuza dek vazgeçiyordu — sohbet solda hep ilk
            # sözün kırıntısıyla listeleniyordu ("sohbet ismi oluşmuyor",
            # canlı şikâyet). Pencere ilk birkaç alışverişe genişledi.
            if sum(1 for m in mesajlar if m.get("role") == "user") > 6:
                return   # ilk alışverişler çoktan geçmiş: başlığı kurcalama
            soru = cevap = ""
            for m in mesajlar:
                govde = m.get("content")
                metin = govde if isinstance(govde, str) else _text_of_blocks(govde or [])
                if m.get("role") == "user" and not soru:
                    soru = metin
                elif m.get("role") == "assistant" and metin:
                    cevap = metin
            if not soru and on_izleme:
                soru = on_izleme
            if not soru.strip():
                return
            alinti = ("KULLANICI: " + _one_line(soru)[:400]
                      + "\nASISTAN: " + _one_line(cevap)[:300])
            hazir = Prepared(
                system=[{"type": "text", "text": BASLIK_ISTEMI}],
                messages=[{"role": "user", "content": alinti}],
                betas=[], context_management=None)
            # Başlık çağrısı GERÇEK kesme olayını taşıyor ve süreyle sınırlı:
            # eski hali (taze Event + sınırsız bekleme) tek kanallı API
            # kapısını iptal edilemez biçimde tutabiliyordu — asıl tur ve
            # Durdur dahil her şey arkasında bekliyordu (canlı yara, 01.09:
            # "10 dakika durdu, olduğu yerde devam etmedi").
            sonuc = await asyncio.wait_for(
                self.client.turn(hazir, [], cancel=self.cancel), timeout=60)
            baslik = _one_line(_text_of_blocks(
                getattr(sonuc.message, "content", None) or [])).strip().strip("\"'.!*# ")
            if _baslik_gecerli(baslik):
                self.mind.set_session_meta(self.session.id, ad=baslik)
                self.session.log.note("baslik", ad=baslik)
                # Kenar listesi 5 sn yoklamayı beklemesin — anında taşınsın.
                try:
                    self.io.on_session_title(self.session.id, baslik)
                except Exception:
                    pass
        except Exception:
            pass   # başlık üretilemedi: türetilmiş başlık zaten var

    async def _handle_stop(
        self, result: TurnResult, ctx: ToolContext, stats: TurnStats
    ) -> bool:
        """Döngü devam etmeli mi? True -> devam."""
        reason = result.stop_reason

        if reason == "tool_use":
            calls = [
                PendingToolUse(id=b["id"], name=b["name"], input=dict(b.get("input") or {}))
                for b in result.tool_uses()
            ]
            stats.tool_calls += len(calls)
            # Araç çağıran tur ilerliyor demektir: sürdürme hakkı tazelenir.
            # Uzun bir koşuda arada bir max_tokens tavanına çarpmak, işi
            # kapanış turuna sürüklememeli.
            if not stats.closing:
                stats.continuations = 0
            blocks = await execute(
                calls,
                registry=self.registry,
                permissions=self.permissions,
                ctx=ctx,
                approve=self.io.approve,
                observe=self._observe,
            )
            # Bir araç görüntü döndürdüyse (kameraya bakmak gibi) blokta
            # taşınamıyor: OpenAI sözleşmesi role=tool içeriğinin dize
            # olmasını istiyor. Görüntü ayrılıp bir sonraki kullanıcı turuna
            # iliştiriliyor — model o turda gerçekten bakıyor.
            seen = []
            for b in blocks:
                v = b.pop("_image", None)
                if isinstance(v, list):
                    seen.extend(x for x in v if x)   # kamera kesitleri
                elif v:
                    seen.append(v)
            # Hafıza köprüsü: bilinen hata kalıbı derse dönüşür; geçmiş
            # oturumlardan ders varsa hatanın YANINA iliştirilir.
            self._hata_dersi(calls, blocks)
            self.session.add_tool_results(blocks)
            if seen:
                # `internal`: kullanıcının yazmadığı bir mesaj sohbette
                # kullanıcı mesajı gibi görünmemeli. Gerçek bir koşuda
                # "Yukarıdaki kare kendi kameranın gördüğü…" notu ekrana
                # cevap gibi düştü.
                self.session.add_user_blocks(_seen_blocks(seen), internal=True)
            if self.cancel.is_set():
                stats.interrupted = True
                self.io.on_notice("Kesildi. Çalışan araçlar durduruldu.")
                return False
            return True

        if reason == "pause_turn":
            # Sunucu taraflı araç kendi yineleme sınırına çarptı. Ek kullanıcı
            # mesajı ekleme — geçmişi olduğu gibi tekrar göndermek yeterli.
            self.session.log.note("pause_turn")
            return True

        if reason == "max_tokens":
            # Model cevabini bitiremeden tavana carpti. Burada durmak
            # kullaniciya yarim cumle birakiyordu; oysa gecmis zaten yazildi,
            # bir tur daha vermek kaldigi yerden surdurmesi icin yeterli.
            #
            # Kesinti bir arac cagrisinin ortasinda olduysa yarim kalan
            # tool_use'lar karsiliksiz kalir; karsiliksiz tool_use bir sonraki
            # istegi 400 ile dusurur.
            self._settle_pending()
            return self._continue(stats, CONTINUE_NOTE, "max_tokens")

        if reason == "empty_turn":
            # Model yalnizca akil yurutup durdu: plan yapti, "simdi sunu
            # yapmaliyim" dedi ve turu bitirdi. Akil yurutmeyi cevap diye
            # sunmak kullaniciyi yarim birakiyordu; plani zaten gecmiste,
            # yapmasi gerekeni yapmasi icin bir tur daha veriliyor.
            return self._continue(stats, ACT_NOTE, "empty_turn")

        if reason == "refusal":
            detail = getattr(result.message, "stop_details", None)
            category = getattr(detail, "category", None)
            self.session.log.note("refusal", category=category)
            self.io.on_notice(f"Model bu isteği reddetti (kategori: {category or 'belirtilmemiş'}).")
            return False

        if reason == "model_context_window_exceeded":
            # Sunucu pencereyi bizden once tuketti (tahminimiz sapmis ya da
            # context_window ayari gercegin ustunde). Durmak yerine
            # sikistir / sikı / son care — is surer.
            self.session.log.note("context_exhausted")
            if await self._yenile_baglam("pencere tasti"):
                return True
            # _yenile_baglam False donerse bile durma: hedef ozetiyle
            # devam notu — kullaniciya "yeni oturum ac" demiyoruz.
            self.session.add_continuation_note(
                "Bağlam yenilendi. İş listendeki açık maddelerden kaldığın "
                "yerden devam et; baştan anlatma."
            )
            self.io.on_notice("Bağlam yenilendi — iş sürüyor.")
            return True

        return False  # end_turn ve bilinmeyenler: sıra kullanıcıda

    def _continue(self, stats: TurnStats, note: str, why: str) -> bool:
        """Yarim kalan bir turu surdurur. Sinir dolduysa False.

        Iki ayri sebeple ayni sey gerekiyor (tavana carpma ve yalnizca akil
        yurutup durma), ve ikisinde de tek bir tavan sayilmali: bir turun
        surdurulme hakki toplamda sinirli.
        """
        if stats.continuations >= MAX_CONTINUATIONS:
            if stats.closing:
                # Kapanis turu da bitmedi. Burada gercekten yapilacak bir
                # sey kalmiyor.
                self.io.on_notice(
                    f"Yanıt {MAX_CONTINUATIONS} kez sürdürüldü ve kapanış turu da "
                    "bitmedi; durduruldu."
                )
                self.session.log.note(why, exhausted=True)
                return False

            # Ajan is yapti, yalnizca bitiremedi. Elindekiyle bir kapanis
            # yazmasi isteniyor: kullanicinin eline hicbir sey gecmemesi,
            # yarim bir cevaptan kotu.
            stats.closing = True
            self.io.on_notice("Yanıt uzadı; elindekiyle özetlemesi istendi.")
            self.session.add_continuation_note(CLOSING_NOTE)
            self.session.log.note(why, exhausted=True, closing=True)
            return True

        stats.continuations += 1
        self.session.add_continuation_note(note)
        self.session.log.note(why, continuation=stats.continuations)
        return True

    # -- model kesintisi dayanıklılığı ---------------------------------

    async def _await_model(self, stats: TurnStats, error: str) -> bool:
        """Model hatasında bekler; True → yeniden dene, False → kullanıcı kesti.

        İlk denemeler üstel geri çekilme (RETRY_DELAYS); tükenince iş PARK
        edilir: ölmez, PARK_PROBE_S aralıklarla yoklamaya düşer — yoklama
        isteğin kendisi. Oto kipinde her yeni deneme sağlık sıralamasından
        geçer ve havuzdaki başka bir modele düşebilir; belirli model
        seçiliyse model DEĞİŞTİRİLMEZ, yalnızca beklenir.
        """
        retries = len(RETRY_DELAYS)
        if stats.api_errors <= retries:
            delay = RETRY_DELAYS[stats.api_errors - 1]
            # Yapısal kanal varsa ham hata sohbete DÜŞMEZ: çalışma şeridi
            # tek canlı satırda geri sayımı işletir, ayrıntı tık ile açılır.
            if not self._bekleme_olayi(
                kip="deneme", deneme=stats.api_errors, toplam=retries,
                saniye=int(delay), detay=_clip(error, 1500),
            ):
                self.io.on_notice(
                    f"Model yanıt vermiyor; {delay:.0f} sn sonra yeniden denenecek "
                    f"({stats.api_errors}/{retries}). ({_clip(error, 120)})")
        elif self.depth > 0:
            # Alt ajan: ana sohbet çalışsa bile burada sonsuz park YOK.
            # Orkestra "Model bekleniyor (5/5) · 300s"de kilitlenmesin.
            stats.fail_reason = _clip(error, 400)
            self._bekleme_olayi(
                kip="hata", deneme=stats.api_errors, toplam=retries,
                saniye=0, detay=stats.fail_reason,
            )
            self.io.on_notice(
                f"Model {retries} denemede yanıt vermedi — görev durdu. "
                f"({_clip(error, 120)})")
            return False
        else:
            delay = PARK_PROBE_S
            self._park(error)
            # Her yoklama turunda şerit tazelenir: "iş bekletiliyor" satırı
            # canlı kalır (sayfa yenilense de bir sonraki yoklamada geri gelir).
            self._bekleme_olayi(
                kip="park", saniye=int(delay), detay=_clip(error, 1500))

        # Kesilebilir bekleyiş: kullanıcı "dur" derse bekleme anında biter.
        try:
            await asyncio.wait_for(self.cancel.wait(), timeout=delay)
        except asyncio.TimeoutError:
            # Süre doldu: yeniden dene. Bekleyen bir model/ayar değişikliği
            # varsa önce uygula — bozuk adres/anahtar düzeltildiyse yeni
            # istemci ancak böyle devreye girer.
            if self.on_retry_wait is not None:
                try:
                    self.on_retry_wait()
                except Exception:
                    pass
            return True

        # Kullanıcı kesti: bilinçli durdurma — park kaydı da düşer.
        self._unpark()
        self._bekleme_olayi(kip="iptal")   # şeritteki bekleme satırı kapansın
        self.io.on_notice("Kesildi.")
        return False

    # -- sahte araç çağrısı --------------------------------------------

    def _sahte_cagriyi_duzelt(
        self, stats: TurnStats, blocks: list[dict[str, Any]]
    ) -> bool:
        """Model araç çağrısını metin olarak mı yazdı? Yazdıysa düzelt.

        True dönerse tur SÜRÜYOR: modele tek satırlık bir not düşüldü ve
        bir tur daha veriliyor. Burada durmak kullanıcıyı ham XML'le (ya
        da arayüz onu çizmediği için hiçbir şeyle) baş başa bırakırdı.
        """
        if not sahte_arac_cagrisi(_text_of_blocks(blocks)):
            return False

        stats.sahte_cagri += 1
        self.session.log.note("sahte_arac_cagrisi", deneme=stats.sahte_cagri)
        # Oto havuzunda bu bir sağlık sinyali: araç çağıramayan uç elensin.
        self._kusurlu("sahte araç çağrısı")

        if stats.sahte_cagri > SAHTE_CAGRI_TAVANI:
            # Mutlak sigorta: model düzelmiyor (çoğu zaman araç çağrısını
            # hiç desteklemeyen bir uç). Turu kendi akışına bırak ve
            # kullanıcıya söyle — çözüm onun elinde: model değiştirmek.
            self.io.on_notice(
                "Model araç çağrılarını metin olarak yazmayı sürdürüyor ve "
                "düzelmedi. Ayarlar › Model'den başka bir model denemek "
                "gerekebilir.")
            return False

        self.session.add_harness_note(
            SAHTE_CAGRI_NOTU if stats.sahte_cagri == 1 else SAHTE_CAGRI_SERT_NOTU)
        return True

    def _kusurlu(self, sebep: str) -> None:
        """Tur teknik olarak başarılı ama İÇERİĞİ kusurlu.

        Şema ihlali ve sahte araç çağrısı, hata/zaman aşımı kadar gerçek
        birer başarısızlık: ikisi de turu boşa harcıyor. Oto kipinde bu
        sinyal sağlık defterine yazılıyor, model havuzun sonuna itiliyor
        ve ücretsiz havuzda araç çağıramayan uç kendiliğinden eleniyor.
        Başka sağlayıcıda karşılığı yok — sessizce geçiliyor.
        """
        kaydet = getattr(self.client, "kusurlu", None)
        if kaydet is None:
            return
        try:
            kaydet(sebep)
        except Exception:
            pass   # sağlık defteri koşuyu düşürmemeli

    def _bekleme_olayi(self, **payload: Any) -> bool:
        """Bekleme durumunu yapısal kanala yazar.

        True dönerse arayüz canlı satırı üstlendi demektir; çağıran düz
        metin bildirimini basmaz. Kanal yoksa (CLI/test) False döner ve
        eski davranış aynen sürer. Kanalın hatası koşuyu düşürmez.
        """
        if self.io.on_wait is None:
            return False
        try:
            self.io.on_wait(payload)
        except Exception:
            pass
        return True

    def _park(self, error: str) -> None:
        if self._parked:
            return
        self._parked = True
        if self.depth == 0:
            try:
                write_park(self.config.state_dir, self.session.id, error)
            except OSError:
                pass
        self.session.log.note("parked", error=_clip(error, 300))
        self.io.on_notice(
            "Model ulaşılamıyor — işin bekletiliyor; bağlantı gelince kaldığı "
            f"yerden sürecek (her {int(PARK_PROBE_S)} sn'de bir yoklanıyor). "
            "İpucu: Ayarlar › model'de Oto kipi, kesintide havuzdaki başka "
            "modellerle sürmemi sağlar.")

    def _unpark(self) -> None:
        if self.depth == 0:
            clear_park(self.config.state_dir)
        if self._parked:
            self._parked = False
            self.session.log.note("unparked")

    # -- alt ajanlar ---------------------------------------------------

    def _child_registry(self) -> ToolRegistry:
        """Alt ajanın araç defteri: yerleşikler (task hariç) + dinamikler.

        Taze defter `build_registry(subagents=False)` yalnızca yerleşikleri
        taşıyor. Yetenekler ve MCP araçları açılıştan SONRA yalnızca ana
        deftere ekleniyordu — alt ajan bir cihaz için yazılmış yeteneği ya
        da bağlanmış bir MCP sunucusunu göremiyordu. Yerleşiklerin `source`u
        None; yetenek/MCP'nin dolu ("yetenek", "mcp:<ad>"). Dolu olanları
        ana defterden kopyalıyoruz — o an ne varsa alt ajana da o iner.
        """
        registry = build_registry(self.mind, subagents=False)
        for spec in self.registry.all():
            if spec.source and spec.name not in registry:
                registry.register(spec)
        return registry

    async def _spawn(self, title: str, instruction: str, model: str = "") -> str:
        """Alt ajanı kendi oturumunda koşturur ve yalnızca son sözünü döndürür.

        Ayrı oturum asıl mesele: alt ajanın otuz araç çağrısı kendi
        günlüğüne yazılıyor, ana konuşmanın penceresine değil. Geriye kalan
        tek şey cevabın kendisi.

        İzin motoru ve atölye sınırı paylaşılıyor — "ben alt ajanım" diyerek
        atlanabilen bir kapı, kapı değildir.
        """
        handle = ChildHandle(id=uuid4().hex[:6], title=title,
                             model=model or self.config.model.name)
        self._register_child(handle)
        answer = await self._child_round(handle, instruction)
        # Sonuç araç sonucuyla zaten döndü; bir de bildirim notu düşülmesin.
        handle.bildirildi = True
        return answer

    def _spawn_bg(self, title: str, instruction: str, model: str = "") -> ChildHandle:
        """Yardımcıyı arka planda başlatır ve HEMEN döner.

        Ana ajan beklemeden işine devam ediyor; yardımcı bitince sonucu
        tur başındaki bildirim notuyla (ya da ana ajan boştaysa köprünün
        açtığı sürdürme turuyla) ana ajanın önüne konuyor.
        """
        handle = ChildHandle(id=uuid4().hex[:6], title=title,
                             model=model or self.config.model.name, arka_plan=True)
        self._register_child(handle)
        # Referans defterde saklanıyor: referanssız task çöp toplanabilir.
        handle.task = asyncio.get_running_loop().create_task(
            self._bg_round(handle, instruction))
        return handle

    def spawn_scheduled(self, title: str, prompt: str, schedule_id: str) -> ChildHandle:
        """Zamanlanmış görevi sessiz arka plan yardımcı olarak koşturur.

        Sohbet kuyruğuna düşmez; bitince ana ajanı konuşturmaz. Rapor
        Orkestra / Görevler + Viewer'da kalır. Her koşum task_runs'a yazılır.
        """
        from . import task_runs

        instruction = SCHEDULE_CHILD_WRAP.format(
            title=title or "görev", prompt=(prompt or "").strip())
        handle = ChildHandle(
            id=uuid4().hex[:6],
            title=title or "zamanlanmış",
            model=self.config.model.name,
            arka_plan=True,
            schedule_id=str(schedule_id or ""),
            sessiz=True,
            deliverable=_infer_deliverable(prompt or ""),
        )
        if schedule_id:
            try:
                run = task_runs.start_run(
                    self.config.state_dir, schedule_id,
                    title=title or "", child_id=handle.id)
                handle.run_id = run.id
            except Exception:
                pass
        self._register_child(handle)
        handle.task = asyncio.get_running_loop().create_task(
            self._bg_round(handle, instruction))
        return handle

    async def run_workflow(self, workflow_id: str,
                           schedule_id: str = "") -> dict[str, Any]:
        """Otomasyon grafiğini sessiz yardımcı olarak koşturur.

        `schedule_id` verilmişse koşum O GÖREVİN defterine yazılıyor.
        Şarttır: arayüz koşum geçmişini görev kimliğiyle soruyor
        (`/api/jobs/runs?id=<görev>`). Akıştan türetilmiş bir kimlik
        kullanmak, koşumları kimsenin bakmadığı bir çekmeceye yazmak
        demekti — geçmiş boş görünüyor, canlı ilerleme hiç gelmiyordu.
        Görevsiz (doğrudan akış) koşumlar için eski türetme duruyor.
        """
        from . import task_runs, workflows
        from .workflow_run import execute_workflow

        wf = workflows.get(self.config.state_dir, workflow_id)
        if wf is None:
            return {"ok": False, "error": f"Akış yok: {workflow_id}"}

        handle = ChildHandle(
            id=uuid4().hex[:6],
            title=wf.title or workflow_id,
            model=self.config.model.name,
            arka_plan=True,
            sessiz=True,
            workflow_id=wf.id,
            schedule_id=(schedule_id or f"wf_{wf.id}")[:48],
        )
        try:
            run = task_runs.start_run(
                self.config.state_dir, handle.schedule_id,
                title=handle.title, child_id=handle.id)
            handle.run_id = run.id
        except Exception:
            pass
        self._register_child(handle)
        # Orkestra kanalı: düğüm tool olayları kanalsız düşmesin.
        try:
            self.io.on_child_start(
                handle.title, handle.model, handle.id, handle.arka_plan)
        except Exception:
            pass

        async def _go() -> None:
            progress: list = []
            try:
                report, progress, ok = await execute_workflow(
                    wf, self, handle)
                handle.state = "bitti" if ok else "hata"
                handle.sonuc = report
                handle.bitis_ts = time.time()
                if not handle.deliverable:
                    handle.deliverable = _infer_deliverable(
                        wf.title or "", report or "")
                self.io.on_child_end(
                    handle.title, ok, 0, len(progress or []),
                    handle.id, _clip(report, 200))
            except Exception as exc:
                handle.state = "hata"
                handle.sonuc = f"{type(exc).__name__}: {exc}"
                handle.bitis_ts = time.time()
                self.io.on_child_end(
                    handle.title, False, 0, 0, handle.id,
                    _clip(handle.sonuc, 200))
            if handle.sessiz:
                handle.bildirildi = True
            if handle.schedule_id and handle.run_id:
                try:
                    from . import task_runs as tr
                    meter = _run_meter(handle, self.config)
                    tr.finish_run(
                        self.config.state_dir, handle.schedule_id, handle.run_id,
                        status="bitti" if handle.state == "bitti" else "hata",
                        report=_report_with_meter(handle, self.config),
                        child_id=handle.id,
                        nodes_progress=progress or None,
                        model=meter["model"],
                        usage=meter["usage"],
                        cost_usd=meter["cost_usd"],
                        tools=meter["tools"],
                        duration_s=meter["duration_s"],
                        last_tool=meter["last_tool"],
                    )
                except Exception:
                    pass
            self._children_settled()

        handle.task = asyncio.get_running_loop().create_task(_go())
        return {"ok": True, "id": handle.id, "workflow_id": wf.id,
                "run_id": handle.run_id}

    async def _bg_round(self, handle: ChildHandle, instruction: str,
                        *, resume: bool = False) -> None:
        """Arka plan sarmalayıcı: koştur, ne olursa olsun defteri düşür,
        köprüye haber ver."""
        try:
            await self._child_round(handle, instruction, resume=resume)
        except Exception as exc:  # arka plandaki çöküş sessiz kalmamalı
            handle.state = "hata"
            handle.sonuc = f"Alt ajan hata verdi: {type(exc).__name__}: {exc}"
            handle.bitis_ts = time.time()
            self.session.log.note("subagent_failed", title=handle.title,
                                  session=handle.session_id, error=str(exc))
        if handle.sessiz:
            # Zamanlı iş: ana sohbet sürdürme turu yok — rapor panelde.
            handle.bildirildi = True
        if handle.schedule_id and self.schedule is not None:
            try:
                durum = ("bitti" if handle.state == "bitti"
                         else f"hata: {_clip(handle.sonuc, 80)}")
                self.schedule.note_run(handle.schedule_id, durum)
            except Exception:
                pass
        if handle.schedule_id and handle.run_id:
            try:
                from . import task_runs
                meter = _run_meter(handle, self.config)
                task_runs.finish_run(
                    self.config.state_dir, handle.schedule_id, handle.run_id,
                    status="bitti" if handle.state == "bitti" else "hata",
                    report=_report_with_meter(handle, self.config),
                    child_id=handle.id,
                    model=meter["model"],
                    usage=meter["usage"],
                    cost_usd=meter["cost_usd"],
                    tools=meter["tools"],
                    duration_s=meter["duration_s"],
                    last_tool=meter["last_tool"],
                )
            except Exception:
                pass
        self._children_settled()

    async def _child_round(self, handle: ChildHandle, instruction: str,
                           *, resume: bool = False) -> str:
        """Bir yardımcının tam turu: oturum aç (ya da diskten sürdür),
        koştur, defteri güncelle, sonucu döndür."""
        from .session import Session

        # Alt ajan başka bir modelle koşabiliyor: tarama işi küçük ve hızlı
        # bir modele, görüntü gerektiren iş görüntü okuyan bir modele
        # gidebilsin. Aynı model isteniyorsa istemci paylaşılıyor — ikinci
        # bir istemci ikinci bir bağlantı havuzu demek.
        client, config = self.client, self.config
        if handle.model and handle.model != self.config.model.name:
            client, config = self._client_for(handle.model)

        # Ajan kapısı: makinenin taşıyabileceği kadarı aynı anda koşar,
        # gerisi sırada bekler. Durdur (cancel) kapıda beklerken de işlesin —
        # yoksa "koşuyor" görünen görev Durdur'a cevap vermiyordu.
        try:
            await self._acquire_agent_gate(handle)
        except asyncio.CancelledError:
            handle.state = "hata"
            handle.sonuc = "(kesildi)"
            handle.bildirildi = True
            handle.bitis_ts = time.time()
            self.io.on_child_end(handle.title, False, 0, 0, handle.id, "(kesildi)")
            return handle.sonuc

        try:
            if resume:
                child = Session.resume(
                    self.config.sessions_dir / f"{handle.session_id}.jsonl")
            else:
                child = Session.create(self.config.sessions_dir)
                handle.session_id = child.id
                child.log.note("subagent_start", title=handle.title, parent=self.session.id)
                self.session.log.note("subagent_start", title=handle.title, session=child.id)
            # Orkestra kanalı doğdu: arayüz canlı göstersin.
            self.io.on_child_start(handle.title, handle.model, handle.id, handle.arka_plan)

            agent = Agent(
                config=config,
                session=child,
                # Alt ajanın kendi defteri: `task` aracı olmadan.
                registry=self._child_registry(),
                client=client,
                io=self._child_io(handle.title, handle.id),
                permissions=self.permissions,
                policy=self.policy,
                mind=self.mind,
                depth=self.depth + 1,
                schedule=self.schedule,
                # Çocuğun KENDİ bayrağı; ana `interrupt()` türev olarak
                # kurar ("dur = her şey durur"). Paylaşmak olmuyordu: ana
                # her `run`da bayrağını tazeliyor ve arka plandaki çocuk
                # eski bayrakta sahipsiz kalıyordu.
                cancel=handle.cancel,
            )
            # Ana sohbet ayardan model değiştirdiyse retry'de çocuğa da geçsin
            # — chat çalışırken görev ölü modelde kilitlenmesin.
            def _child_retry_wait(
                _agent=agent, _handle=handle, _parent=self,
                _dogum=self.client,
            ) -> None:
                if _parent.on_retry_wait is not None:
                    try:
                        _parent.on_retry_wait()
                    except Exception:
                        pass
                # Yalnız ebeveynin istemcisi GERÇEKTEN değiştiyse benimse.
                # Kanca artık her model çağrısından önce koşuyor (bekleyen
                # değişim akışı); koşulsuz benimseme, farklı modelle açılan
                # çocuğun istemcisini İLK turda ebeveyne çeviriyordu —
                # task'ın model yönlendirmesi kırılıyordu (kök, 01.09).
                if _parent.client is _dogum:
                    return
                _agent.client = _parent.client
                _agent.config = _parent.config
                _handle.model = _parent.config.model.name

            agent.on_retry_wait = _child_retry_wait
            handle.agent = agent

            try:
                stats = await agent.run(instruction)
            except Exception as exc:  # yardımcının çökmesi ana turu düşürmemeli
                self.session.log.note("subagent_failed", title=handle.title,
                                      session=handle.session_id, error=str(exc))
                handle.state = "hata"
                handle.sonuc = f"Alt ajan hata verdi: {type(exc).__name__}: {exc}"
                self.io.on_child_end(handle.title, False, 0, 0, handle.id,
                                     _clip(handle.sonuc, 200))
                return handle.sonuc
            finally:
                handle.agent = None
                handle.bitis_ts = time.time()
                # Günlük kapanıyor ama oturum diskte duruyor: `task_say`
                # bitmiş bir yardımcıyı Session.resume ile geri açabiliyor.
                child.close()
        finally:
            self._agent_gate.release()

        answer = _last_text(child)
        if stats.interrupted:
            # Kesilen yardımcı için bildirim turu açılmaz: durduran zaten
            # kullanıcının kendisi — ya da model max retry ile durdu.
            handle.state = "hata"
            if stats.fail_reason:
                handle.sonuc = (
                    f"Model {len(RETRY_DELAYS)} denemede yanıt vermedi.\n"
                    f"{stats.fail_reason}"
                )
            else:
                handle.sonuc = answer or "(kesildi)"
            handle.bildirildi = True
        else:
            handle.state = "bitti"
            handle.sonuc = answer
        if not handle.deliverable:
            handle.deliverable = _infer_deliverable(instruction, handle.sonuc or "")
        # `session` yetim taraması için: açılışta start/end eşleşmesi
        # kimlikle yapılıyor (başlık benzersiz olmak zorunda değil).
        self.session.log.note(
            "subagent_end", title=handle.title, session=handle.session_id,
            turns=stats.turns, tools=stats.tool_calls
        )
        self.io.on_child_end(handle.title, not stats.interrupted, stats.turns,
                             stats.tool_calls, handle.id,
                             _clip(handle.sonuc or answer, 200))
        return handle.sonuc or answer

    def _register_child(self, handle: ChildHandle) -> None:
        self._children[handle.id] = handle
        # Defter sınırlı: koşan atılmaz, en eski bitmişler düşer.
        while len(self._children) > MAX_CHILDREN:
            finished = [h for h in self._children.values() if h.state != "kosuyor"]
            if not finished:
                break
            oldest = min(finished, key=lambda h: h.bitis_ts)
            self._children.pop(oldest.id, None)

    def adopt_orphans(self, yetimler: list[dict[str, str]]) -> list[ChildHandle]:
        """Geçen oturumun yetim yardımcılarını deftere alır.

        Defter kaydı iki kapıyı birden açıyor: arayüz paneli yetimi soluk
        bir "yarım kaldı" satırı olarak çizebiliyor (snapshot kanalları) ve
        kullanıcı "sürdür" derse `task_say` diskteki oturumu handle
        üzerinden diriltebiliyor. Modele tek toplu harness notu düşer —
        gelen kutusundan, yani ilk turun başında önüne konur.
        """
        adopted: list[ChildHandle] = []
        for y in yetimler:
            sid = str(y.get("session") or "")
            if not sid:
                continue
            handle = ChildHandle(
                id=uuid4().hex[:6],
                title=str(y.get("title") or "") or sid,
                model="",
                arka_plan=True,
                session_id=sid,
                state="yetim",
                sonuc=YETIM_SONUC,
                bitis_ts=time.time(),
                # Bildirim turu açılmasın: haber notu zaten aşağıda.
                bildirildi=True,
            )
            self._register_child(handle)
            adopted.append(handle)
        if adopted:
            liste = ", ".join(f"{h.title} (id={h.id})" for h in adopted)
            self.take_note(YETIM_NOTU.format(n=len(adopted), liste=liste))
        return adopted

    def _children_settled(self) -> None:
        """Bir yardımcı bitti: köprüye (varsa) haber ver.

        Köprü, ana ajan boştaysa bir sürdürme turu açar; meşgulse haber
        kuyruğa düşer ve tur bitince değerlendirilir. Köprüsüz kullanımda
        (test, salt-metin) sonuç bir sonraki turun başında zaten bildirilir.
        """
        callback = self.on_children_settled
        if callback is not None:
            try:
                callback()
            except Exception:
                pass

    def _drain_children(self) -> None:
        """Biten ve henüz bildirilmemiş yardımcı/iş sonuçlarını nota döker."""
        for handle in self._children.values():
            if handle.state == "kosuyor" or handle.bildirildi:
                continue
            handle.bildirildi = True
            if handle.kind == "iş":
                template = JOB_DONE_NOTE if handle.state == "bitti" else JOB_FAIL_NOTE
            else:
                template = CHILD_DONE_NOTE if handle.state == "bitti" else CHILD_FAIL_NOTE
            self.session.add_harness_note(template.format(
                title=handle.title, id=handle.id,
                # Panele tam metin gidiyor; modele yalnızca kısa özet —
                # uzun bülteni sohbete yapıştırmasın.
                result=_clip(handle.sonuc, 400)))

    def _drain_inbox(self) -> None:
        """Gelen kutusunu geçmişe harness notu olarak boşaltır."""
        while self._inbox:
            self.session.add_harness_note(self._inbox.popleft())

    def has_unreported_children(self) -> bool:
        return any(h.state != "kosuyor" and not h.bildirildi
                   for h in self._children.values())

    async def resume_for_children(self) -> TurnStats | None:
        """Boştayken biten yardımcıları değerlendiren sürdürme turu.

        Girdisi kullanıcı mesajı değil: continuation kanalından bir not
        (arayüzde görünmez) + sonuçların harness notları. Hiç bekleyen
        bildirim yoksa None döner ve model hiç çağrılmaz.
        """
        done = [h for h in self._children.values()
                if h.state != "kosuyor" and not h.bildirildi]
        if not done:
            return None
        self._arm()
        titles = ", ".join(f"{h.title} (id={h.id})" for h in done)
        self.session.add_continuation_note(CHILDREN_RESUME_NOTE.format(titles=titles))
        self._drain_children()
        return await self._drive()

    def _child_say(self, cid: str, message: str) -> tuple[bool, str]:
        """`task_say`: koşan yardımcıya not, bitmiş yardımcıya devam turu."""
        handle = self._children.get((cid or "").strip())
        if handle is None:
            known = ", ".join(self._children) or "(defter boş)"
            return False, (f"'{cid}' diye bir yardımcı yok. Defterdekiler: {known}. "
                           "`task_status` ile bak.")
        if handle.kind == "iş":
            return False, (f"'{handle.title}' bir arka plan işi (süreç), mesaj almaz. "
                           "Bitince çıktısı zaten sana bildirilecek.")
        if handle.state == "kosuyor":
            if handle.agent is None:
                # Ajan kapısında sırada: nesne henüz kurulmadı.
                return False, (f"'{handle.title}' henüz sırada (ajan kapısı dolu); "
                               "birazdan tekrar dene.")
            handle.agent.take_note(SAY_NOTE.format(message=message))
            return True, (f"İletildi: '{handle.title}' (id={handle.id}) bir sonraki "
                          "adımında bu notu görecek.")
        if not handle.session_id:
            return False, f"'{handle.title}' oturumsuz bitti; sürdürülemiyor."
        # Bitmiş yardımcı: oturumu diskten açılıp arka planda sürdürülüyor.
        handle.state = "kosuyor"
        handle.bildirildi = False
        handle.sonuc = ""
        handle.cancel = asyncio.Event()
        handle.task = asyncio.get_running_loop().create_task(
            self._bg_round(handle, message, resume=True))
        return True, (f"'{handle.title}' (id={handle.id}) bitmişti; oturumu diskten "
                      "açılıp arka planda sürdürülüyor — bitince sonucu bildirilecek.")

    def _child_status(self, cid: str = "") -> str:
        """`task_status`: tek/tüm yardımcıların durum özeti."""
        if not self._children:
            return "Defter boş: başlatılmış yardımcı yok."
        wanted = (cid or "").strip()
        rows = []
        for h in self._children.values():
            if wanted and h.id != wanted:
                continue
            row = f"- id={h.id} · {h.title} · {h.state}"
            if h.kind == "iş":
                row += " · süreç"
            if h.arka_plan:
                row += " · arka plan"
            if h.state != "kosuyor" and h.sonuc:
                row += f" · sonuç: {_clip(h.sonuc, 300)}"
            rows.append(row)
        if not rows:
            return (f"'{wanted}' diye bir yardımcı yok. "
                    f"Defterdekiler: {', '.join(self._children)}")
        return "\n".join(rows)

    # -- arka plan işleri (uzun süreçler) ------------------------------

    def _job_bg(self, title: str, runner: Callable[[asyncio.Event], Awaitable[str]]) -> ChildHandle:
        """Uzun bir işi (derleme, kurulum, test koşusu) arka plana alır.

        Yardımcı defterinin AYNISI kullanılıyor: kayıt, bildirim notu,
        boştayken sürdürme turu ve türev kesme — hepsi hazır altyapı.
        Fark: model koşan bir alt ajan değil, tek bir eşyordam (süreç).
        `runner` kendi kesme bayrağını alır — ana `interrupt()` onu kurar.
        """
        handle = ChildHandle(id=uuid4().hex[:6], title=title, model="",
                             kind="iş", arka_plan=True)
        self._register_child(handle)
        self.session.log.note("job_start", title=title, id=handle.id)
        self.io.on_child_start(handle.title, "süreç", handle.id, True)
        handle.task = asyncio.get_running_loop().create_task(
            self._job_round(handle, runner))
        return handle

    async def _job_round(self, handle: ChildHandle,
                         runner: Callable[[asyncio.Event], Awaitable[str]]) -> None:
        try:
            # Tam çıktı panellerde/Viewer'da; harness notuna kısaltma ayrı.
            handle.sonuc = await runner(handle.cancel)
            handle.state = "bitti"
        except JobFailed as exc:
            # Komut bitti ama başarısız — 'tamamlandı' demeyelim.
            handle.state = "hata"
            handle.sonuc = str(exc)
        except Exception as exc:  # işin çökmesi ajanı düşürmemeli
            handle.state = "hata"
            handle.sonuc = f"{type(exc).__name__}: {exc}"
        handle.bitis_ts = time.time()
        self.session.log.note("job_end", title=handle.title, id=handle.id,
                              state=handle.state)
        self.io.on_child_end(handle.title, handle.state == "bitti", 0, 0,
                             handle.id, _clip(handle.sonuc, 200))
        self._children_settled()

    async def _acquire_agent_gate(self, handle: "ChildHandle") -> None:
        """Ajan semaforunu al; Durdur gelirse CancelledError.

        Düz `async with gate` cancel'i dinlemiyordu — planlanmış görev
        kapıda beklerken UI 'koşuyor' diyordu, Durdur hiçbir işe yaramıyordu.
        """
        if handle.cancel.is_set():
            raise asyncio.CancelledError()
        acquire = asyncio.ensure_future(self._agent_gate.acquire())
        stopper = asyncio.ensure_future(handle.cancel.wait())
        try:
            done, pending = await asyncio.wait(
                {acquire, stopper}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            if stopper in done and acquire not in done:
                raise asyncio.CancelledError()
            # acquire tamamlandı (veya ikisi birden — yine de kapı alınmış).
            if acquire.cancelled() or acquire.exception():
                raise asyncio.CancelledError()
        except asyncio.CancelledError:
            if not acquire.done():
                acquire.cancel()
                try:
                    await acquire
                except (asyncio.CancelledError, Exception):
                    pass
            elif not acquire.cancelled() and acquire.exception() is None:
                # Kapıyı almışken kesildik — serbest bırak.
                self._agent_gate.release()
            raise

    def _client_for(self, model: str) -> tuple[Any, Config]:
        """Başka bir model için istemci kurar.

        Sağlayıcı ve adres aynı kalıyor, yalnızca model adı değişiyor: aynı
        LM Studio üzerindeki başka bir model ya da aynı API'deki başka bir
        model. Farklı bir sağlayıcı istemek ayarların işi, alt ajanın değil.

        Kurulan istemci saklanıyor: aynı modeli üç alt ajan isterse üç
        bağlantı havuzu açmanın anlamı yok.
        """
        from dataclasses import replace as _replace

        from .backends import build_client

        if model in self._clients:
            return self._clients[model]

        config = _replace(self.config, model=_replace(self.config.model, name=model))
        pair = (build_client(config.model), config)
        self._clients[model] = pair
        return pair

    def _child_io(self, title: str, cid: str) -> AgentIO:
        """Alt ajanın arayüz bağlantısı.

        Metni akıtmıyor: alt ajanın ara cümleleri ana sohbete karışsa
        kullanıcı kimin konuştuğunu ayırt edemezdi. Araç olayları geçiyor —
        ne yaptığı izlenebilmeli.

        Onay isteği kanal kimliğiyle gidiyor: kullanıcı diyalogda hangi
        yardımcının izin istediğini görsün. Köprünün onayı üçüncü bir
        `channel` parametresi alabiliyor; testlerin iki parametreli onayları
        olduğu gibi çalışmaya devam ediyor.
        """
        import inspect

        approve = self.io.approve
        try:
            takes_channel = len(inspect.signature(approve).parameters) >= 3
        except (TypeError, ValueError):
            takes_channel = False
        if takes_channel:
            channel = {"id": cid, "title": title}

            async def child_approve(spec: ToolSpec, args: dict[str, Any]) -> bool:
                return await approve(spec, args, channel)
        else:
            child_approve = approve

        def on_tool_start(name: str, args: dict[str, Any]) -> None:
            hedef = _tool_hedef(args)
            self._child_tool_mark(cid, name, "start", hedef)
            self.io.on_child_tool(title, name, "start", hedef)

        def on_tool_end(name: str, ok: bool, ms: float) -> None:
            self._child_tool_mark(cid, name, "ok" if ok else "fail")
            self.io.on_child_tool(title, name, "ok" if ok else "fail", "")

        def on_usage(report: dict[str, int], _c: str = cid) -> None:
            h = self._children.get(_c)
            if h is None:
                return
            h.usage["girdi"] = int(h.usage.get("girdi") or 0) + int(
                report.get("prompt_total") or 0)
            h.usage["cikti"] = int(h.usage.get("cikti") or 0) + int(
                report.get("output") or 0)
            h.usage["cagri"] = int(h.usage.get("cagri") or 0) + 1

        return AgentIO(
            # Araç olayları alt ajanın kanalına yazılıyor (ana sohbete değil):
            # "kim ne yapıyor" orkestra panelinde görünür olsun.
            on_tool_start=on_tool_start,
            on_tool_end=on_tool_end,
            on_usage=on_usage,
            # Ham BadRequestError duvarı ana sohbete sarı cevap gibi
            # dökülmesin — kısa özet; tam metin arayüzde tıkla-aç.
            # Bekleme/retry sohbete spam olmasın: yapısal child_wait.
            on_notice=lambda text: self.io.on_notice(_child_notice_line(title, text)),
            on_wait=lambda payload, _t=title, _c=cid: self._child_wait(_t, _c, payload),
            approve=child_approve,
        )

    def _child_tool_mark(self, cid: str, name: str, phase: str,
                         hedef: str = "") -> None:
        handle = self._children.get(cid)
        if handle is None:
            return
        if phase == "start":
            handle.son_arac = name
            handle.son_hedef = hedef or ""
            handle.wait = None
            handle.tools_count = int(handle.tools_count or 0) + 1
        else:
            handle.son_arac = name + (" ✗" if phase == "fail" else " ✓")
            if not handle.son_hedef and hedef:
                handle.son_hedef = hedef
        self._maybe_patch_run(handle)

    def _maybe_patch_run(self, handle: ChildHandle) -> None:
        """Zamanlı koşum arşivine canlı özet yazar (throttle)."""
        if not handle.schedule_id or not handle.run_id:
            return
        now = time.time()
        if now - (handle.last_patch_ts or 0) < 3.0:
            return
        handle.last_patch_ts = now
        try:
            from . import task_runs
            meter = _run_meter(handle, self.config)
            lines: list[str] = ["(koşuyor)"]
            if meter.get("line"):
                lines.append(str(meter["line"]))
            if handle.son_arac:
                line = f"Araç: {handle.son_arac}"
                if handle.son_hedef:
                    line += f" · {handle.son_hedef}"
                lines.append(line)
            if handle.wait:
                w = handle.wait
                msg = "Model bekleniyor"
                if w.get("deneme") and w.get("toplam"):
                    msg += f" ({w['deneme']}/{w['toplam']})"
                lines.append(msg)
            task_runs.patch_run(
                self.config.state_dir, handle.schedule_id, handle.run_id,
                report="\n".join(lines),
                model=meter.get("model") or handle.model,
                usage=meter.get("usage"),
                cost_usd=meter.get("cost_usd"),
                tools=meter.get("tools"),
                duration_s=meter.get("duration_s"),
                last_tool=meter.get("last_tool"),
            )
        except Exception:
            pass

    def _child_wait(self, title: str, cid: str, payload: dict[str, Any]) -> None:
        """Alt ajan model beklemesi → panel (sohbet duvarı değil)."""
        body = dict(payload or {})
        body.setdefault("title", title)
        body.setdefault("id", cid)
        kip = str(body.get("kip") or "")
        handle = self._children.get(cid)
        if handle is not None:
            if kip in ("bitti", "iptal"):
                handle.wait = None
            else:
                handle.wait = body
                handle.son_arac = ""
                handle.son_hedef = ""
            if kip in ("deneme", "park", "hata"):
                self._maybe_patch_run(handle)
        # Bridge / CLI: on_child_wait yoksa notice'a düşme — kip bitti/iptal
        # hariç kısa satır.
        emit = getattr(self.io, "on_child_wait", None)
        if callable(emit):
            try:
                emit(body)
                return
            except Exception:
                pass
        if kip in ("bitti", "iptal"):
            return
        if kip in ("deneme", "park", "hata"):
            detay = _clip(str(body.get("detay") or ""), 120)
            sn = body.get("saniye")
            den = body.get("deneme")
            top = body.get("toplam")
            msg = f"[{title}] Model yanıt vermiyor"
            if kip == "hata":
                msg = f"[{title}] Model yanıt vermedi — görev durdu"
            if den and top:
                msg += f" ({den}/{top})"
            if sn:
                msg += f"; {sn} sn"
            if detay:
                msg += f". ({detay})"
            self.io.on_notice(msg)

    # -- bağlam basıncı ------------------------------------------------

    async def _relieve_pressure(self) -> None:
        """Pencere dolmaya yaklaştıysa sıkıştırır.

        Tavana çarpmadan önce yapılıyor: özet isteğinin kendisi de aynı
        pencereye sığmak zorunda.
        """
        if not self._last_usage:
            return
        pressure = compaction.measure(self._last_usage, self.config.model.context_window)
        self._warn_if_window_is_wrong(pressure)
        if pressure.full:
            await self._yenile_baglam(f"pencere %{pressure.percent} dolu")

    def _warn_if_window_is_wrong(self, pressure: compaction.Pressure) -> None:
        """Ayardaki pencere gerçeğin üstündeyse söyler.

        Belirtisi sinsi: sıkıştırma hiç tetiklenmiyor, istem modelin gerçek
        sınırını aşıyor ve sunucu istemin **başını** sessizce atıyor. Model o
        noktada kim olduğunu ve ne istendiğini unutmuş oluyor — dışarıdan
        "sapıtıyor" gibi görünüyor, oysa ayar yanlış.

        İstem penceresini aştığı halde cevap gelmeye devam ediyorsa kanıt
        kesin: sunucu kırpıyor demektir.
        """
        if self._window_warned or pressure.used <= pressure.window:
            return
        self._window_warned = True
        self.session.log.note(
            "window_mismatch", used=pressure.used, configured=pressure.window
        )
        self.io.on_notice(
            f"İstem {pressure.used:,} token'a ulaştı ama ayardaki bağlam penceresi "
            f"{pressure.window:,}. Sunucu istemin başını atıyor olabilir — model "
            "kim olduğunu ve ne istendiğini unutur. Ayarlar › bağlam'dan "
            "pencereyi modelin gerçek sınırına çek.".replace(",", ".")
        )

    async def _yenile_baglam(self, reason: str) -> bool:
        """Bağlamı sıkıştırır; olmazsa sıkı / son çare horizon.

        True = pencere yenilendi (iş sürebilir). False = dokunulamadı.
        """
        if await self._compact(reason=reason):
            return True
        if await self._compact(reason=f"{reason} — sıkı", keep=2):
            return True
        return self._force_horizon(reason)

    async def _compact(self, *, reason: str, keep: int | None = None) -> bool:
        """Pencereyi özetleyip daraltır. Sıkıştırılamadıysa False."""
        plan = (
            self.session.compaction_plan(keep=keep)
            if keep is not None
            else self.session.compaction_plan()
        )
        if plan is None and keep is None:
            plan = self.session.compaction_plan(keep=2)
        if plan is None:
            return False

        from_seq, text = plan
        self.io.on_notice(f"Bağlam sıkıştırılıyor ({reason}) — konuşma kesilmeyecek.")

        summary = await self._summarize(text)
        if not summary:
            self.session.log.note("compact_failed", reason=reason)
            return False

        # İş durumu özetin BAŞINA sabitleniyor: kaybolan bağlamda en kritik
        # şey "neyin peşindeydim, nerede kalmıştım". Özetleyici bunu bazen
        # gömüyor; burada garanti altına alınıyor.
        if state := self._is_durumu(from_seq):
            summary = state + "\n\n" + summary

        self.session.compact(summary, from_seq)
        # Hedef notu özete katlandı; canlı hedefler bir sonraki turda
        # yeniden enjekte edilebilsin (aksi halde dijest değişmediği için
        # _sync_goals susar ve hedefler bağlamdan tümden düşerdi).
        self._last_goal_digest = ""
        self._last_usage = {}
        # Eski prime notları özete katlandı; artık bağlamda durmuyorlar.
        # Tekrar hakkı geri gelmeli, yoksa özetin kaybettiği bir hatıra
        # oturum boyunca bir daha öne konamaz. Ruh tohumları kalıyor —
        # ruh sistem promptunda, sıkıştırma ona dokunmuyor.
        self._primed = self._soul_resident()
        self.session.log.note("compacted", from_seq=from_seq, chars=len(summary))

        # Özet yalnızca bağlama değil zihne de yazılıyor. Aksi halde
        # sıkıştırma kontrollü bir unutma olurdu: oturum kapandığında özet
        # de giderdi. Zihne düştüğü için aylar sonra çağrışımla geri gelebilir.
        if self.mind is not None:
            try:
                self.mind.remember(
                    summary,
                    kind="episode",
                    title=f"oturum {self.session.id} — özet",
                    tags=("özet", "oturum"),
                )
            except Exception as exc:  # zihin yazılamazsa konuşma yine sürmeli
                self.session.log.note("compact_memory_failed", error=str(exc))

        self.io.on_notice("Bağlam özetlendi; kalıcı belleğe de yazıldı.")
        return True

    def _force_horizon(self, reason: str) -> bool:
        """Özetlenecek tur yoksa ufku son mesaja çek — iş dursun diye değil."""
        try:
            events = self.session._live_events()
        except Exception:
            return False
        if len(events) < 2:
            return False
        from_seq = events[-1].seq
        summary = (
            self._is_durumu(from_seq)
            or "Bağlam yenilendi; açık iş listesinden devam."
        )
        self.session.compact(summary, from_seq)
        self._last_goal_digest = ""
        self._last_usage = {}
        self._primed = self._soul_resident()
        self.session.log.note(
            "compacted", from_seq=from_seq, chars=len(summary), force=True, reason=reason
        )
        self.io.on_notice("Bağlam yenilendi — iş sürüyor.")
        return True

    async def _summarize(self, text: str) -> str:
        """Dökümü özetlemesi için modele tek seferlik bir istek gönderir.

        Araçsız ve önbelleksiz: bu istek konuşmanın parçası değil, onun
        hakkında bir soru. Geçmişe de yazılmıyor.
        """
        prepared = Prepared(
            system=[{"type": "text", "text": compaction.SUMMARY_SYSTEM}],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": compaction.SUMMARY_REQUEST.format(transcript=text)}
                    ],
                }
            ],
            betas=[],
            context_management=None,
        )
        result = await self.client.turn(prepared, [], cancel=self.cancel)
        if result.error or result.interrupted:
            return ""
        return "\n".join(
            str(block.get("text", ""))
            for block in result.content
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()

    def _is_durumu(self, before_seq: int) -> str:
        """Sıkıştırmada özetin başına sabitlenen iş durumu bölümü.

        İki parça: hedef yığını (varsa) + katlanan bölgedeki son asistan
        sözü ("son ilerleme"). Uzun bir koşuda özetin kaybetmemesi gereken
        şey tam olarak bu ikisi.
        """
        parts: list[str] = []
        if self.mind is not None:
            try:
                if digest := self.mind.goal_digest():
                    parts.append(digest)
            except Exception:
                pass
        if progress := self._son_ilerleme(before_seq):
            parts.append(f"Son ilerleme: {_clip(progress, 600)}")
        if not parts:
            return ""
        return "[İŞ DURUMU]\n" + "\n".join(parts)

    def _son_ilerleme(self, before_seq: int) -> str:
        """Katlanan bölgedeki son asistan metni — modelin kendi anlatımı."""
        for event in reversed(self.session.log.messages()):
            if event.seq >= before_seq or event.role != "assistant":
                continue
            blocks = event.content if isinstance(event.content, list) else []
            text = "\n".join(
                str(b.get("text", "")) for b in blocks
                if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
            if text:
                return text
        return ""

    # -- yardımcılar ---------------------------------------------------

    def _sync_goals(self) -> None:
        """Hedef yığını değiştiyse operatör kanalından geri hatırlatır.

        Sistem promptuna yazılamaz — orası bayt bayt sabit kalmak zorunda,
        yoksa her hedef değişiminde tüm önbellek düşer. role="system" mesajı
        geçmişin sonuna eklenir: önek korunur, kanal taklit edilemez.
        """
        if self.mind is None:
            return
        digest = self.mind.goal_digest()
        if digest == self._last_goal_digest:
            return
        self._last_goal_digest = digest
        if digest:
            # Çıplak liste küçük modelde TALİMAT gibi okunuyordu: kullanıcı
            # "selam yaz" derken model defterdeki hedefi tartışmaya
            # girişiyordu (canlı yara, 31.08). Öncelik tek cümleyle nota
            # gömülü: gündemi kullanıcının son sözü belirler.
            self.session.add_system_note(
                digest + "\n(Hatırlatma, talimat değil: gündemi kullanıcının "
                "son sözü belirler. Hedefe sırası gelince ya da kullanıcı "
                "sorunca dönersin; bu notu cevabında tartışmazsın.)")

    def _settle_pending(self) -> None:
        pending = self.session.pending_tool_uses()
        if not pending:
            return
        self.session.add_tool_results([cancelled_result(p.id) for p in pending])
        self.session.log.note("settled_pending", count=len(pending))

    def _observe(self, event: str, data: dict[str, Any]) -> None:
        self.session.log.note(event, **data)
        if event == "tool_start":
            # Model kendi defterine yazdıysa tur sonu dürtüsü gereksiz.
            if data.get("tool") == "mind_memory":
                self._zihin_yazildi = True
            self._teslim_izi(str(data.get("tool") or ""), data.get("input") or {})
            self.io.on_tool_start(data["tool"], data.get("input") or {})
        elif event == "tool_end":
            # Kırmızı defteri: doğrulama araçlarının verdiği son hüküm.
            # Yeşile dönen bir koşum kaydı SİLİYOR — model düzeltip yeniden
            # koşturduysa kapı açılmamalı.
            tool = data["tool"]
            if tool in DOGRULAMA_ARACLARI:
                if iz := kirmizi_iz(tool, data):
                    self._kirmizi[tool] = iz
                else:
                    self._kirmizi.pop(tool, None)
            self.io.on_tool_end(tool, not data["error"], data["ms"])
            if data["error"]:
                # Uyanık ters tekrar (yol haritası 3.12.1): sorumluluk sonuç
                # belli olduğu an dağıtılıyor, geceyi beklemeden. Dersi
                # sabaha bırakmak, aynı hatayı aynı oturumda tekrar etmeye
                # izin vermek demekti.
                self._uyanik_ters_tekrar("basarisiz")
        elif event == "sema_ihlali":
            # Şemaya uymayan çağrı da boşa giden bir tur: oto havuzunda
            # sağlık sinyali sayılıyor (bkz. _kusurlu). Araç hiç çalışmadı,
            # arayüzde adım satırı da yok — yalnızca günlükte ve defterde.
            self._kusurlu("şema ihlali")


def worth_recalling(text: str) -> bool:
    """Bu mesaj için zihne bakmaya değer mi?

    "naber" bir soru değil, bir selam. Zihni her mesajda modelin önüne
    boşaltmak istenen şey değildi — istenen, **lazım olduğunda hızlıca
    bulabilmesi**. Gerçek bir koşuda "naber" dendiğinde model geçmiş
    oturum özetiyle, kullanıcı profiliyle ve BTC zinciriyle karşılaştı
    ve sohbet etmek yerine "ne yapmak istersin" diye sordu.

    Ölçüt basit: içerik taşıyan bir kelime var mı. Selam ve hâl hatır
    sormada yok; bir konuya atıf yapan mesajda var.
    """
    words = [w for w in _WORDS.findall((text or "").lower()) if len(w) >= 4]
    return any(word not in SMALL_TALK for word in words)


def select_prime(mind: Any, user_input: str, *, limit: int = RECALL_PRIME_LIMIT,
                 ham: str | None = None) -> list[Any]:
    """Kendiliğinden önyüklemenin seçim çekirdeği: ara, süz, kuyruğu kes.

    Modül fonksiyonu olması bilinçli — ölçek benchmark'ı
    (eval/context_memory/scale_bench.py) ürünle BİREBİR aynı yolu ölçmeli;
    kopyalanmış bir seçim mantığı sessizce ayrışır ve ölçülen şey ürün olmaz.

    Süzme kuralları (hepsi gerçek koşularda kanayan yaralardan):

    * Yalnızca **doğrudan eşleşenler** (hop 0). Çağrışımla sıçrayarak gelen
      kayıt ("borsa" sorusuna ağın öteki ucundaki SCADA) modeli konudan
      çıkarıyor; o yol modelin kendi `mind_recall` çağrısına kalıyor.
    * `episode` düğümleri girmiyor: konuşma turları uzun ve neredeyse her
      sorguyla eşleşiyor, gerçek eşleşmeyi boğuyorlar.
    * Harf zemini (`_grounded`): kayıt, sorgunun içerik kelimelerinden en az
      birinin gövdesini gerçekten içermeli — skorlar doygunlaşınca eşik tek
      başına ayıramıyor, salt imza-benzerliğiyle gelen kayıt sızıyordu.
    * Taban eşiği en güçlü kayda uygulanmıyor: genç hafızada bm25 çöküyor
      (tek belgeli korpusta kusursuz eşleşme 0.0) ve mutlak eşik prime'ı
      tümden kapatıyordu. Zemini olan en iyi kayıt her zaman gösterilir;
      eşik yalnızca kuyruğu keser.
    """
    query = _without_numbers(user_input)
    hits = mind.recall(query, limit=limit)

    trace = getattr(mind, "last_trace", None) or []
    direct = {step.node for step in trace if step.hop == 0}
    if not direct:
        return []
    stems = _query_stems(query)
    # Zengin sorguda (>=5 gövde) TEK gövdeyle tutunan kayıt önyüklemeye
    # giremez: 50 alakasız saha notu "ayın" ↔ "ayında" gibi tek örtüşmeyle
    # tam bu yoldan sızdı (28.08 hafıza deneyi, C kolu: +%28 token,
    # +1 çağrı). Kendiliğinden enjeksiyonun çıtası açık aramadan yüksek —
    # tek-konulu gerçek ihtiyaç için modelin `mind_recall` yolu duruyor.
    # Kısaltma sorguları (btc, plc) zarar görmez: gövdeleri az, kural uyumaz.
    # Zenginlik HAM kullanıcı sorgusundan ölçülür: sinonim genişletmesi
    # (taban.zenginlestir + köprü) sorguyu yapay şişiriyor ve üç kelimelik
    # meşru bir soru "zengin" sayılıp genç hafızadaki tek-gövdeli gerçek
    # kaydı kesiyordu (test bunu yakaladı). Çağıran ham metni verir;
    # vermezse eldeki sorgudan köprüsüz gövdelere düşülür.
    zengin = len(_query_stems(ham if ham is not None else query,
                              genislet=False)) >= 5
    def _gecer(item: Any) -> bool:
        if not stems:
            return True
        text = f"{item.title} {item.content} {' '.join(item.tags)}".casefold()
        vuranlar = [g for g in stems if g in text]
        if not vuranlar:
            return False
        # Önek kopyaları tek sayılır: "ayı" ve "ayın" aynı kelimenin iki
        # kesimi — ikisini iki kanıt saymak süzgeci deliyordu.
        tekil = [g for g in vuranlar
                 if not any(g != d and d.startswith(g) for d in vuranlar)]
        return len(tekil) >= 2 if zengin else True
    passed = [
        hit
        for hit in hits
        if hit.item.kind != "episode"
        and hit.item.id in direct
        and _gecer(hit.item)
    ]
    if not passed:
        return []
    top = max(passed, key=lambda h: h.score)
    if top.score < RECALL_PRIME_FLOOR:
        # Koşulsuz-top istisnası yalnız GENÇ zihinde. İstisnanın yazılma
        # sebebi genç korpusta bm25'in çökmesiydi (tek belgeli korpusta
        # kusursuz eşleşme 0.0 — mutlak eşik prime'ı tümden kapatıyordu).
        # Olgun zihinde aynı istisna düşük-IDF tek kazananı HER turda
        # bağlama taşıyordu — dış incelemenin bulduğu kök neden: ilgisiz
        # 9-görev dizisindeki +%9 istem tokeni buradan geliyordu.
        try:
            genc = mind.store.count() < 30
        except Exception:
            genc = True
        if not genc:
            return []
    return [h for h in passed if h is top or h.score >= RECALL_PRIME_FLOOR][:limit]


def prime_note(hits: list[Any]) -> str:
    """Önüne konan hatıraların sistem notu — maliyeti bu metnin uzunluğu.

    `render()` kullanılmıyor: o `(tür) başlık [etiketler]` diye açıyor ve
    satır başındaki `[tür]` ile türü iki kez basıyordu; otomatik başlıklı
    kayıtlarda (başlık = gövdenin ilk satırı) başlık gövdeyle bir daha
    tekrarlanıyordu. Etiketler de girmiyor — model için sinyal değil dolgu.
    """
    lines = [RECALL_PRIME_HEADER]
    for hit in hits:
        item = hit.item
        body = " ".join((item.content or "").split())
        title = " ".join((item.title or "").split())
        # Başlık gövdenin başıyla aynıysa (otomatik başlık) yalnız gövde.
        if title and not body.casefold().startswith(title.casefold()[:40]):
            body = f"{title} — {body}"
        lines.append(f"- [{item.kind}] {_one_line(body)}")
    return "\n".join(lines)


def _query_stems(query: str, *, genislet: bool = True) -> set[str]:
    """Sorgunun içerik kelimelerinin gövdeleri (ilk 5 harf, küçük harf).

    İşlev kelimeleri (ve/bir/için...) atılıyor — onlar her kayıtta var ve
    zemin saymak süzgeci deler. Kısaltmalar (btc, plc) 3 harfte de içerik
    taşıyor; o yüzden eşik 4 değil 3.

    Sorgu önce sinonim köprüsünden geçer: arama "bitcoin"i BTC kaydına
    köprüyle ulaştırıyorsa zemin kapısı da o köprüyü tanımalı — yoksa
    bulunan kayıt "kelimesi geçmiyor" diye önyüklemeden düşer.
    """
    from .recall import bridge
    from .recall.vector import STOPWORDS

    metin = bridge.expand(query or "") if genislet else (query or "")
    return {
        w[:5]
        for w in _WORDS.findall(metin.casefold())
        if len(w) >= 3 and w not in STOPWORDS
    }


def _grounded(item: Any, stems: set[str]) -> bool:
    """Kayıt, sorgu gövdelerinden en az birini gerçekten içeriyor mu?

    Gövde yoksa (sorgu yalnız işlev kelimesi) kapı açık kalıyor: süzgecin
    işi imza-tek kanıtlı sızıntıyı kesmek, hatırlamayı tümden kapatmak değil.
    """
    if not stems:
        return True
    text = f"{item.title} {item.content} {' '.join(item.tags)}".casefold()
    return any(stem in text for stem in stems)


def _fatal_error(text: str) -> bool:
    """Yeniden denemenin işe yaramayacağı hata mı?

    Bozuk istek (400/404/405/413/422) ve pencere taşması (n_ctx) aynı
    istekle tekrar denemekle düzelmez — eski davranış korunur, hemen durur.
    Bağlantı, zaman aşımı, 401/403 (anahtar sonradan düzelebilir), 408/429
    ve 5xx geçici sayılır: uzun işi tek bir sağlayıcı hıçkırığı öldürmemeli.
    """
    t = text or ""
    if re.search(r"\b(400|404|405|413|422)\b", t):
        return True
    return "n_ctx" in t


def _clip(text: str, limit: int) -> str:
    """Uzun bir sonucu keser — bildirim notu bağlamı boğmasın."""
    flat = (text or "").strip()
    return flat if len(flat) <= limit else flat[:limit] + "…"


_APP_URL_RE = re.compile(
    r"https?://(?:127\.0\.0\.1|localhost):\d+(?:/[^\s\"'<>]*)?",
    re.I,
)
_ARTIFACT_RE = re.compile(r"/artifact/[A-Za-z0-9_-]+/?", re.I)


def _tool_hedef(args: Any, limit: int = 100) -> str:
    """Araç argümanından tek satır: komut / yol / url."""
    if not isinstance(args, dict):
        return ""
    for key in ("command", "path", "query", "url", "title", "id", "text", "run"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            flat = " ".join(value.split())
            return flat if len(flat) <= limit else flat[:limit] + "…"
    return ""


def _report_with_deliverable(handle: ChildHandle) -> str:
    """task_runs.report: özet + varsa canlı app/artifact adresi."""
    text = str(handle.sonuc or "").strip()
    d = handle.deliverable if isinstance(handle.deliverable, dict) else None
    if not d or not d.get("url"):
        return text
    url = str(d["url"])
    if url in text:
        return text or "(özet yok)"
    kind = str(d.get("kind") or "")
    if kind == "app":
        footer = f"\n\n---\nCanlı uygulama: {url}"
    elif kind == "artifact":
        footer = f"\n\n---\nYayınlanan rapor: {url}"
    else:
        footer = f"\n\n---\nTeslimat: {url}"
    return (text or "(özet yok)") + footer


def _run_meter(handle: ChildHandle, config: Any) -> dict[str, Any]:
    """Koşum ölçümü: model + token + süre + araç + tahmini USD."""
    from dataclasses import replace

    from . import fiyat

    usage = {
        "girdi": int((handle.usage or {}).get("girdi") or 0),
        "cikti": int((handle.usage or {}).get("cikti") or 0),
        "cagri": int((handle.usage or {}).get("cagri") or 0),
    }
    cost: float | None = None
    model_name = str(handle.model or "")
    model_cfg = getattr(config, "model", None)
    state_dir = getattr(config, "state_dir", None)
    if model_cfg is not None and model_name:
        try:
            model_cfg = replace(model_cfg, name=model_name)
        except Exception:
            pass
    if model_cfg is not None and state_dir is not None:
        try:
            tag = fiyat.etiket(model_cfg, state_dir)
        except Exception:
            tag = None
        if tag and (usage["girdi"] or usage["cikti"]):
            cost = (
                usage["girdi"] * float(tag["girdi"])
                + usage["cikti"] * float(tag["cikti"])
            )
    end = handle.bitis_ts or time.time()
    start = handle.baslangic_ts or end
    duration_s = max(0, int(end - start)) if start else 0
    tools = int(handle.tools_count or 0)
    last_tool = ""
    if handle.son_arac:
        last_tool = handle.son_arac
        if handle.son_hedef:
            last_tool += f" · {handle.son_hedef}"
    return {
        "model": model_name,
        "usage": usage,
        "cost_usd": cost,
        "tools": tools,
        "duration_s": duration_s,
        "last_tool": last_tool[:200],
        "line": _meter_line(
            model_name, usage, cost, tools, duration_s, last_tool),
    }


def _meter_line(
    model: str,
    usage: dict[str, int],
    cost: float | None,
    tools: int,
    duration_s: int,
    last_tool: str = "",
) -> str:
    """Tek satır özet — rapor dosyasında ve panelde kalır."""
    parts: list[str] = []
    if model:
        parts.append(model.rsplit("/", 1)[-1])
    tok = int(usage.get("girdi") or 0) + int(usage.get("cikti") or 0)
    if tok:
        parts.append(f"{tok} tok")
    if usage.get("cagri"):
        parts.append(f"{usage['cagri']} tur")
    if tools:
        parts.append(f"{tools} araç")
    if duration_s:
        parts.append(_fmt_duration(duration_s))
    if cost is not None:
        parts.append(
            f"≈${cost:.2f}" if cost >= 0.01 or cost == 0 else f"≈${cost:.3f}")
    if last_tool:
        parts.append(f"son: {last_tool[:80]}")
    return " · ".join(parts)


def _fmt_duration(seconds: int) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return f"{s} sn"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} dk {s} sn" if s else f"{m} dk"
    h, m = divmod(m, 60)
    return f"{h} sa {m} dk"


def _report_with_meter(handle: ChildHandle, config: Any, body: str = "") -> str:
    """Rapor gövdesi + kalıcı meter satırı (uygulama kapanınca da kalsın)."""
    text = (body if body is not None else _report_with_deliverable(handle)).strip()
    meter = _run_meter(handle, config)
    line = meter.get("line") or ""
    if not line:
        return text
    if line in text:
        return text
    return (text or "(özet yok)") + "\n\n---\n" + line


def _infer_deliverable(*texts: str) -> dict[str, Any] | None:
    """Prompt/çıktıdan bitiş teslimatı çıkar: canlı app veya artifact adresi."""
    from urllib.parse import urlparse

    blob = "\n".join(str(t) for t in texts if t)
    if not blob.strip():
        return None
    m = _APP_URL_RE.search(blob)
    if m:
        raw = m.group(0).rstrip(".,;)\"]'")
        parsed = urlparse(raw)
        # /api/refresh gibi uçlar yerine uygulamanın kökünü aç.
        url = f"{parsed.scheme}://{parsed.netloc}/"
        return {"kind": "app", "url": url}
    m = _ARTIFACT_RE.search(blob)
    if m:
        path = m.group(0)
        if not path.endswith("/"):
            path += "/"
        return {"kind": "artifact", "url": path}
    return None


def _child_notice_line(title: str, text: str) -> str:
    """Alt ajan uyarısını ana sohbete kısa satır olarak taşır.

    Ham BadRequestError / JSON duvarı sarı "cevap" gibi ekranı kaplıyordu.
    Mesaj çıkarılabiliyorsa onu kullan; yoksa ilk satırı kısalt.
    """
    raw = (text or "").strip()
    if not raw:
        return f"[{title}]"
    msg = re.search(r"'message':\s*'([^']+)'", raw) or re.search(
        r'"message"\s*:\s*"([^"]+)"', raw
    )
    if msg:
        return f"[{title}] {msg.group(1)}"
    err = re.match(r"^(\w+Error)\b", raw)
    if err and ("Error code" in raw or "{" in raw):
        return f"[{title}] {err.group(1)}"
    first = raw.split("\n", 1)[0].strip()
    return f"[{title}] {_clip(first, 140)}"


def _one_line(text: str, limit: int = 220) -> str:
    """Hatirayi tek satira indirir.

    Sistem notu kisa kalmali: her mesajdan once ekleniyor ve uzunlugu
    dogrudan her turun maliyetine biniyor.
    """
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


def _text_of_blocks(blocks: list[dict[str, Any]]) -> str:
    """Asistan turundaki metin bloklarını birleştirir.

    Araç çağrıları ve düşünme blokları atlanıyor: belleğe giren, asistanın
    kullanıcıya söylediği söz — araç argümanları değil.
    """
    parts = [b.get("text", "") for b in blocks
             if isinstance(b, dict) and b.get("type") == "text"]
    return "\n".join(p for p in parts if p).strip()


def _last_text(session: "Session") -> str:
    """Oturumun son asistan turundaki metin.

    Alt ajanın "sonucu" bu: araç sonuçları kendi günlüğünde kalıyor, geriye
    yalnızca son söz dönüyor.
    """
    for event in reversed(session.log.messages()):
        if event.role != "assistant":
            continue
        blocks = event.content if isinstance(event.content, list) else []
        text = "\n".join(
            str(b.get("text", ""))
            for b in blocks
            if isinstance(b, dict) and b.get("type") == "text"
        ).strip()
        if text:
            return text
    return ""


def _with_image(text: str, data_url: str) -> list[dict[str, Any]]:
    """Metin + görüntüyü Anthropic blok biçimine çevirir.

    Tarayıcı `data:image/png;base64,...` gönderiyor; API tür ve veriyi ayrı
    alanlarda istiyor.
    """
    header, _, payload = data_url.partition(",")
    media = "image/png"
    if ";" in header and ":" in header:
        media = header.split(":", 1)[1].split(";", 1)[0] or media

    blocks: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": media, "data": payload},
        }
    ]
    # Görüntü önce, metin sonra: model önce baktığı şeyi, sonra soruyu görüyor.
    # Soru yoksa da bakması gerekeni söylüyoruz — yalnızca bir kare gönderip
    # "ne diyeceksin bakalım" demek modelin tek cümleyle geçiştirmesine
    # yol açıyordu.
    blocks.append({"type": "text", "text": text.strip() or LOOK_NOTE})
    return blocks


def _seen_blocks(images: list[str]) -> list[dict[str, Any]]:
    """Araçtan gelen görüntüleri kullanıcı turuna çevirir.

    Araç sonucunda taşınamadığı için buraya düşüyorlar. Yanlarına kısa bir
    not konuyor: modelin bunu kullanıcının gönderdiği bir fotoğraf değil,
    kendi bakışının sonucu olarak okuması gerekiyor.
    """
    blocks: list[dict[str, Any]] = []
    for data in images:
        header, _, payload = data.partition(",")
        media = "image/jpeg"
        if ";" in header and ":" in header:
            media = header.split(":", 1)[1].split(";", 1)[0] or media
        blocks.append(
            {"type": "image", "source": {"type": "base64", "media_type": media, "data": payload}}
        )
    blocks.append({"type": "text", "text": SEEN_NOTE})
    return blocks
