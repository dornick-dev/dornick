Node ile küçük bir görev listesi aracı yaz, adı `gorev.js` olsun.

Şöyle kullanacağım:

    node gorev.js ekle "süt al"
    node gorev.js liste
    node gorev.js bitir 1

`liste` görevleri numaralarıyla göstersin, biten görev listede bitmiş olduğu
belli olacak şekilde görünsün. Görevler `gorevler.json` dosyasında dursun,
programı kapatınca kaybolmasın.

Olmayan bir komut yazarsam ("node gorev.js zıpla") hata versin ve çıkış kodu
sıfırdan farklı olsun.
