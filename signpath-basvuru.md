# SignPath Foundation — başvuru formu (canlı formdan alındı)

Form: <https://signpath.org/apply> (HubSpot gömülü form). Alanlar **02.09.2026**
tarihinde doğrudan sayfadan okundu. `*` = zorunlu. Aşağıdaki "Dornick değeri"
önerileri hazır; kopyala-yapıştır.

## Proje bilgileri

| Alan (formdaki etiket) | Zorunlu | Dornick değeri / not |
|---|---|---|
| **Project Name** | ✅ | `Dornick` |
| **Repository URL** | ✅ | `https://github.com/dornick-dev/dornick` (herkese açık olmalı) |
| **Homepage URL** | ✅ | `https://dornick.dev` |
| **Download URL** | — | `https://github.com/dornick-dev/dornick/releases` |
| **Privacy Policy URL** | — | Ayrı gizlilik sayfası yoksa boş bırak; README'deki "Code signing policy → Privacy" yeter |
| **Wikipedia URL (optional)** | — | boş |
| **Tagline** | ✅ | tek cümle. Öneri: `Local-first personal AI agent with a living memory.` |
| **Description** | ✅ | 2-4 cümle ne yaptığı. Öneri: `Dornick is a local-first desktop AI agent for Windows. It runs on the user's machine, drives tools (shell, files, web, browser, devices), and keeps a persistent memory of the user's context. Works with local models (LM Studio/Ollama) or hosted providers via OpenRouter.` |
| **Reputation** | ✅ | Projenin ciddiyetini gösteren kanıt: yıldız sayısı, indirmeler, kullanıcılar, yaş, basın. Yeni projede dürüst ol: `Actively developed open-source project (MIT). Public repo with releases and a full automated benchmark + test suite. <yıldız/indirme sayıları buraya>.` |

## Bakımcı

| Alan | Zorunlu | Dornick değeri |
|---|---|---|
| **Maintainer Type** (açılır) | — | `Individual maintainer(s)` |
| **First Name** | ✅ | `Fatih` |
| **Last Name** | ✅ | `Kütük` |
| **Email** | ✅ | `fatihktuk@gmail.com` |
| **Company Name** | — | boş (bireysel) |

> Maintainer Type seçenekleri: Independent community project · Non-profit
> foundation/research · For-profit/corporate-backed · **Individual maintainer(s)** · Other.

## Derleme / CI

| Alan | Zorunlu | Dornick değeri / not |
|---|---|---|
| **Build System** (açılır) | — | `GitHub Actions` seç. İmzalama workflow'u kuruldu: `.github/workflows/release-sign.yml` — release yayınlanınca installer'ı derleyip (SignPath yapılandırılınca) hem iç `dornick.exe`'yi hem kurulumu imzalar ve release'e ekler. |

## Nereden duydun

| Alan | Zorunlu | Dornick değeri |
|---|---|---|
| **Primary Discovery Channel** (açılır) | ✅ | `Developer platforms (e.g. GitHub)` (uygun olanı seç) |
| **Please specify the exact source (optional)** | — | serbest |

> Discovery seçenekleri: Organic search · AI/LLM tools · Developer platforms
> (e.g. GitHub) · Community platforms · Social media · Events · Referral ·
> Direct contact · Other.

## Onaylar (kutucuklar)

| Onay | Zorunlu |
|---|---|
| **Code of Conduct**'u okudum ve kabul ediyorum; sertifikanın SignPath Foundation adına verildiğini ve şartlar ihlal edilirse iptal edilebileceğini anlıyorum | ✅ |
| SignPath'ten diğer iletişimleri almayı kabul ediyorum | — |
| Kişisel verimin SignPath tarafından saklanıp işlenmesine izin veriyorum | ✅ |
| reCAPTCHA | ✅ (formda çözülür) |

## Başvurudan önce hazır olması gerekenler

- [ ] GitHub deposu **herkese açık** (`dornick-dev/dornick`)
- [ ] En az bir **yayınlanmış release** (1.4.0'ı yayınla)
- [ ] README'de **"Code signing policy"** bölümü — eklendi (roller + gizlilik)
- [ ] OSI lisansı, ticari dual-license yok — **MIT**, tamam
- [ ] SignPath ve GitHub hesaplarında **iki adımlı doğrulama (MFA)** açık
- [x] İmzalama **GitHub Actions** workflow'u kuruldu (`.github/workflows/release-sign.yml`)
- [ ] Onaydan sonra: repo Secrets/Variables'a SignPath değerlerini gir (workflow başındaki KURULUM bloğu)

## Onaydan sonra

- İmzada yayıncı **"SignPath Foundation"** görünür (senin adın değil).
- İmzalama, GitHub Actions workflow'una SignPath connector'ı ile bağlanır;
  `installer/build.ps1`'in ürettiği `.exe` imzalanıp release'e asset olarak
  yüklenir — uygulama içi güncelleme onu indirip kurar.
