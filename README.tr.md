# neo

**Yaşayan, beyin-gibi hafızalı, yerel-öncelikli kişisel yapay zekâ ajanı.**

[English README](README.md)

neo bir kod asistanı değil. Bilgisayarında yaşayan, bilgisayarı senin
kullandığın gibi kullanabilen — ekran, fare, klavye, tarayıcı, dosyalar —
ve hafızası, hedefleri, geçmişi birinci sınıf, sorgulanabilir yapılar olan
kişisel bir ajan. Senin hakkında öğrendikleri, ekranda büyüdüğünü
izleyebildiğin bir hafıza ağına yazılır.

![neo karşılama ekranı](docs/screenshots/karsilama.png)

## İçinde ne var

* **Yaşayan hafıza.** Her konuşma anı bırakır. Hatırlama SQLite FTS5
  indeksi + 256-bit parmak izi (SimHash) katmanından gelir — karşılaştırma
  başına tek XOR — bu yüzden 1 anıda da 50.000 anıda da hatırlama süresi
  ~sabittir. Yeni anı en yakın komşularına kendiliğinden bağlanır; ağ
  zamanla kendini örer.
* **Kendine ait minik bir beyin.** 10.8M parametrelik bayt-düzeyi model
  (*taban yazıcı*), hafıza aramasından önce soruyu eş anlamlılar,
  kısaltmalar ve zamir çözümleriyle genişletir. Saf numpy ile CPU'da,
  milisaniyelerde, tamamen çevrimdışı koşar. Repoyla birlikte gelir
  (`src/neocp/assets/taban.npz`, ~20 MB).
* **"Beni tanı" gece okulu.** Anahtar açıksa neo, taban yazıcısını *senin*
  anılarınla, gece, senin makinende, düşük öncelikle ince ayarlar. Her aday
  model bir sınav kapısından geçmek zorundadır — benchmark'ta mevcut modeli
  geçecek, tuzak sorularda susacak, hızlı kalacak — yoksa çöpe gider.
  Verin bilgisayardan çıkmaz.
* **Bilgisayar kullanımı.** Ekran görüntüsü, fare/klavye kontrolü, pencere
  yönetimi ve DevTools protokolüyle sürülen gerçek bir tarayıcı
  (`neo chrome`) — oturumlar kendi profilinde kalıcıdır.
* **Dış kapı (API).** Başka ajanlar ve araçlar neo'yla programla konuşabilir:
  `127.0.0.1`'e `POST /api/gate`, gövde `{"text": "..."}` — yanıtın tamamı
  döner. Varsayılan kapalı.
* **MCP bağlayıcıları ve yetenekler.** Ayar sayfasından Model Context
  Protocol sunucuları bağlanır; neo ayrıca kendi yeteneklerini
  (öğrenip yeniden kullandığı küçük betikler) kendisi yazar ve saklar.
* **Modelden bağımsız.** Anthropic API ya da OpenAI-uyumlu her sunucu —
  LM Studio, Ollama, vLLM, llama.cpp, OpenRouter.
* **Türkçe ve İngilizce** arayüz; hafıza katmanı sondan eklemeli Türkçe
  için kurulmuştur (önek eşleyen FTS) ve İngilizcede de çalışır.

![Hafıza ağı sahnesi](docs/screenshots/beyin.png)

## Hızlı başlangıç

### Kurulum sihirbazıyla (Windows)

[Releases](../../releases) sayfasından `neo-setup-<sürüm>.exe` indir,
çalıştır, Başlat menüsünden **neo**'yu aç. Uygulamanın ayar sayfasından
model seçilir (yerel sunucu ya da API anahtarı). İsteğe bağlı
bileşenler: beni tanı eğitimi, dinleme (mikrofon), kamera izleme.

### Kaynaktan

```bash
git clone https://github.com/fatihkutuk/neo
cd neo
pip install -e ".[app,local]"
neocp setup     # LM Studio / Ollama / vLLM / API anahtarlarını yoklar
neocp --app     # masaüstü penceresi (WebView2)
```

| komut | ne yapar |
|---|---|
| `neocp --app` | masaüstü penceresi |
| `neocp` | terminalde |
| `neocp --web` | tarayıcıda, `127.0.0.1:8765` |
| `neocp --resume` | son oturumu sürdürür |
| `neocp --mode plan` | salt okunur başlatır |

İlk açılışta zihin boştur. Konuştukça kendi kendine dolar; ikinci oturumda
seni hatırlamaya başlar.

## Mimari

### Hafıza akışı

![Hafıza akışı](docs/hafiza-akisi.svg)

Soru önce taban yazıcıdan geçer; arama için gerçekten gereken terimler
(eş anlamlılar, açılımlar, çözülmüş zamirler) eklenir — eklenecek bir şey
yoksa model susar. Genişletilmiş sorgu iki indekse birden vurur (terim
kataloğu + parmak izleri), kalibre bir birleşim adayları süzer ve modelin
bağlamına yalnızca ilgili kartlar ulaşır.

Projenin ölçek benchmark'ında ölçülen:

* hatırlama isabeti, taban yazıcı öndeyken **0.87 → 0.93**
* eş anlamlıyla sorulmuş sorular **0.50 → 1.00**
* tam sorgu genişletme CPU'da ~**300 ms**, mesaj başına bir kez; erken
  susma (eklenecek şey yok) 50 ms'nin altında
* hatırlama gecikmesi 1 kayıtta da 50.001 kayıtta da ~**0.05 ms**

### Gece okulu

![Gece okulu döngüsü](docs/gece-okulu.svg)

Gecelik kişisel döngü yeni anıları hasat eder, onlardan soru→terim
çiftleri damıtır, taban modeli düşük öncelikle ince ayarlar ve adayı
sınava sokar. Yalnızca konuşlu modeli geçen aday konuşlanır. Her şey
yerelde koşar.

### Ayarlar

![Ayar sayfası](docs/screenshots/ayarlar.png)

## Eğitim düzeneği

[`training/`](training/) dizini taban yazıcının tam, kendine yeter eğitim
düzeneğini içerir — **verisiyle birlikte**: ~164.5k örneklik iki dilli
öğretmen korpusu, eğitilmiş taban checkpoint'i
(`training/checkpoints/base.pt`) ve korpus üretiminden kabul sınavına ve
gecelik kişisel döngüye kadar bütün betikler. İsteyen modeli yeniden
eğitebilir ya da ileri götürebilir; hat, dondurulmuş veri biçimi ve
oynamaya değer vidalar için bkz. [`training/README.md`](training/README.md)
(bu klasörün kodu, ML topluluğu okuyabilsin diye İngilizce adlandırılmıştır).

![Eğitim hattı](docs/training-pipeline.svg)

## Değerlendirme

neo'ya dış kapı API'sinden üç kodlama görevi (kolay / orta / zor) verdik ve her
çıktıyı bağımsız denetledik — sonra aynı görevleri hem değerlendiricinin
kendisiyle hem de neo'nun kendi modelinin **çıplak, tek atış** haliyle koşturduk.
neo **294/300** aldı: değerlendiricisiyle baş başa (289) ve kendi çıplak
modelinin (280) önünde — aynı model, kabuk içinde +14 puan ve sıfır bozuk
teslimat. Tam rapor: [docs/evaluation.tr.md](docs/evaluation.tr.md)
([English](docs/evaluation.md)).

## Yol haritası

* Daha güçlü İngilizce taban modeli (eğitim verisi bugün Türkçe ağırlıklı)
* Daha çok duyu: sürekli dinleme ve kamera izleme var, devamı gelecek
* Bugün birincil hedef Windows; daha geniş platform desteği sonra

## Katkı

Özellik dalı → pull request → `main` (korumalı). Bkz.
[CONTRIBUTING.md](CONTRIBUTING.md). Not: proje geleneği gereği **kod
kimlikleri ve yorumlar Türkçedir**.

## Emeği geçenler

neo, **Fatih Kütük** ve **Claude'un (Anthropic)** birlikte yürüttüğü bir
geliştirmedir — bu depodaki mimari, kod ve fikirler o ortak çalışmadan
doğdu.

## Lisans

[MIT](LICENSE) © 2026 Fatih Kütük
