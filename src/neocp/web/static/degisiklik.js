// "Bu turda ne değişti" + geri al.
//
// Bir tur bitiyor ve model üç dosyaya dokunmuş oluyor. Hangileri? Cevap
// şimdiye kadar konuşmanın içinde dağınık duruyordu (araç kartları, "yazdım"
// cümleleri). Burada tek satır: "3 dosya değişti — göster". Açılınca liste,
// her satırda "farkı gör" ve üstte "bu turu geri al".
//
// Uydurma bir defter YOK: kaynak `tools/checkpoint.py`nin yazdığı değişiklik
// defteri — ajanın `undo` aracının okuduğu defterin aynısı. Geri alma da o
// aracın `restore` yolunu çağırıyor. Yani panelin gösterdiği şeyle ajanın
// bildiği şey tek gerçek.
//
// Tur sınırı `sira` numarasıyla çiziliyor: tur başlarken defterin son sırası
// alınıyor, tur bitince ondan sonrası soruluyor. Zaman damgasıyla değil —
// saniye çözünürlüğü aynı saniyede olan iki yazımı ayıramıyor.

Dil.ekle({
  " dosya değişti": " file(s) changed",
  "göster": "show",
  "gizle": "hide",
  "farkı gör": "see the diff",
  "farkı gizle": "hide the diff",
  "bu turu geri al": "undo this turn",
  "Emin misin? Bir daha tıkla": "Sure? Click again",
  "Geri alınıyor…": "Undoing…",
  "yeni dosya": "new file",
  "geri alınamaz": "cannot be undone",
  "Fark okunamadı.": "Could not read the diff.",
  "İkili ya da okunamayan dosya — fark çizilmiyor.":
    "Binary or unreadable file — no diff drawn.",
});

const Degisiklik = (() => {
  // Bu turun başlangıç sırası. Sayfa açılışında defterin O ANKİ sonu
  // alınıyor: geçmiş turların değişiklikleri "bu turda oldu" diye
  // gösterilmemeli.
  let taban = 0;
  let turBasi = 0;

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  async function defter(since) {
    try {
      const yol = "/api/degisiklikler" + (since ? "?since=" + since : "");
      return await (await fetch(yol)).json();
    } catch { return null; }
  }

  async function tabanAl() {
    const veri = await defter(0);
    taban = (veri && veri.son) || 0;
    return taban;
  }

  // --- tur sınırı ------------------------------------------------------

  function turBasladi() {
    turBasi = taban;
    // Tur başında defteri bir kez tazeliyoruz: arada başka bir yol
    // (ajanın kendi `undo`su, başka bir pencere) yazmış olabilir.
    tabanAl().then((son) => { turBasi = son; });
  }

  async function turBitti() {
    const veri = await defter(turBasi);
    if (!veri) return;
    taban = veri.son || taban;
    // Sınır HER tur sonunda ilerliyor. Yalnız `turBasladi`ya güvenmek
    // yetmiyor: bir yardımcı bitince açılan SÜRDÜRME turunun kullanıcı
    // mesajı yok, dolayısıyla başlangıcı da yok — o tur bir öncekinin
    // değişikliklerini kendi hanesine yazıyordu ("3 dosya" derken "6").
    const kayitlar = veri.kayitlar || [];
    turBasi = taban;
    if (!kayitlar.length) return;   // sessiz tur: şerit basılmaz
    serit(kayitlar);
  }

  // --- şerit -----------------------------------------------------------

  function serit(kayitlar) {
    // Kendi sınıfı: `system` satırı tek satırlık bir not için biçimlenmiş
    // (nowrap + ellipsis); açılan liste orada görünmez kalırdı.
    const satir = line("changed");
    satir.replaceChildren();

    const bas = el("button", "chg-head");
    bas.type = "button";
    const say = el("b", null, kayitlar.length + t(" dosya değişti"));
    const aksiyon = el("span", "chg-more", t("göster"));
    bas.append(say, aksiyon);
    satir.append(bas);

    const govde = el("div", "chg-body");
    govde.hidden = true;
    satir.append(govde);

    let kurulu = false;
    bas.addEventListener("click", () => {
      govde.hidden = !govde.hidden;
      aksiyon.textContent = govde.hidden ? t("göster") : t("gizle");
      if (!kurulu) { kurulu = true; govdeKur(govde, kayitlar); }
      scroll();
    });
    scroll();
    return satir;
  }

  function govdeKur(govde, kayitlar) {
    govde.append(geriAlDugmesi(kayitlar));
    for (const k of kayitlar) govde.append(dosyaSatiri(k));
  }

  // İki adımlı onay: ilk tık uyarır, ikinci tık uygular. Yanlışlıkla
  // basılan bir düğmenin turu silmesi kabul edilemez.
  function geriAlDugmesi(kayitlar) {
    const kutu = el("div", "chg-undo");
    const dugme = el("button", "chg-undo-btn", t("bu turu geri al"));
    dugme.type = "button";
    let onay = false;
    let zaman = null;
    dugme.addEventListener("click", async () => {
      if (!onay) {
        onay = true;
        dugme.classList.add("warn");
        dugme.textContent = t("Emin misin? Bir daha tıkla");
        // Onay penceresi kapanıyor: beş saniye sonra düğme eski hâline
        // dönüyor ki ekranda "silahı kurulu" bir düğme unutulmasın.
        zaman = setTimeout(() => {
          onay = false;
          dugme.classList.remove("warn");
          dugme.textContent = t("bu turu geri al");
        }, 5000);
        return;
      }
      clearTimeout(zaman);
      dugme.disabled = true;
      dugme.textContent = t("Geri alınıyor…");
      let cevap = null;
      try {
        cevap = await (await fetch("/api/degisiklikler/geri", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ n: kayitlar.length }),
        })).json();
      } catch { cevap = null; }
      if (!cevap || cevap.ok === false) {
        line("alert", (cevap && cevap.error) || t("Fark okunamadı."));
        dugme.disabled = false;
        dugme.classList.remove("warn");
        dugme.textContent = t("bu turu geri al");
        onay = false;
        return;
      }
      kutu.replaceChildren(el("span", "chg-undone",
        (cevap.yapilan || []).join("\n")));
      // Geri alma da deftere yazıldı (redo mümkün): taban tazelenmeli,
      // yoksa bir sonraki tur bu kayıtları "yeni" sanır.
      tabanAl();
    });
    kutu.append(dugme);
    return kutu;
  }

  function dosyaSatiri(k) {
    const satir = el("div", "chg-row");
    const bas = el("div", "chg-row-head");
    bas.append(el("span", "chg-mark", k.yoktu ? "+" : "~"));
    const ad = el("b", null, k.ad || k.dosya);
    ad.title = k.dosya;
    bas.append(ad);
    bas.append(el("span", "chg-tool", k.arac || ""));
    if (k.yoktu) bas.append(el("span", "chg-tag new", t("yeni dosya")));
    if (!k.gerialinabilir) bas.append(el("span", "chg-tag warn", t("geri alınamaz")));

    const fark = el("button", "chg-diff-btn", t("farkı gör"));
    fark.type = "button";
    bas.append(fark);
    satir.append(bas);

    const kutu = el("div", "chg-diff");
    kutu.hidden = true;
    satir.append(kutu);

    let yuklendi = false;
    fark.addEventListener("click", async () => {
      kutu.hidden = !kutu.hidden;
      fark.textContent = kutu.hidden ? t("farkı gör") : t("farkı gizle");
      if (yuklendi || kutu.hidden) { scroll(); return; }
      yuklendi = true;
      let veri = null;
      try {
        veri = await (await fetch("/api/degisiklikler/fark?sira=" + k.sira)).json();
      } catch { veri = null; }
      kutu.replaceChildren(farkKutusu(veri));
      scroll();
    });
    return satir;
  }

  // Fark ÇİZİMİ mevcut kartın aynısı: `diffHunk` app.js'te yaşıyor ve araç
  // kartlarında kullanılıyor. İkinci bir diff çizici yazmak, bir gün
  // ikisinin ayrı görünmesi demekti.
  function farkKutusu(veri) {
    if (!veri || !veri.ok) {
      return el("div", "diff-empty", (veri && veri.error) || t("Fark okunamadı."));
    }
    if (!veri.metin) {
      return el("div", "diff-empty", t("İkili ya da okunamayan dosya — fark çizilmiyor."));
    }
    return diffHunk(veri.eski, veri.yeni, 1);
  }

  // Açılışta tabanı al: bu oturumda daha önce yapılmış değişiklikler ilk
  // turun özetine karışmasın.
  tabanAl();

  return { turBasladi, turBitti, tabanAl, serit };
})();
