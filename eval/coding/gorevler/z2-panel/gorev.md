PHP ile küçük bir yönetim paneli yaz.

- `index.php` giriş sayfası olsun: kullanıcı adı `admin`, şifre `1234`.
- Girişten sonra üç sayfa çalışsın: `ozet.php`, `kullanicilar.php`,
  `ayarlar.php`. Her birinde o sayfaya ait gerçek bir içerik olsun (özet için
  birkaç rakam, kullanıcılar için bir liste, ayarlar için bir form).
- Giriş yapmadan bu üç sayfadan birine gidersem beni giriş sayfasına atsın.
- Yanlış şifre girersem içeri almasın.
- Bir de çıkış olsun.

`php -S 127.0.0.1:8098` ile çalıştıracağım.
