// Kompozer yüzeyleri: `/` komut defteri ve `@` dosya bahsi.
//
// İkisi de aynı şeyin iki hâli: kompozerde yazarken açılan, klavyeyle
// gezilen, Enter'la seçilen, Escape'le kapanan tek bir kutu. Bu yüzden
// TEK durum makinesi var — iki ayrı menü iki ayrı hata demekti (biri açıkken
// öteki de açılıyor, ok tuşu ikisine birden gidiyor).
//
// İki kural:
//
//   * Komut defterindeki her satır ZATEN VAR OLAN bir yola bağlanıyor.
//     Uydurma komut yok: `/model` dock'taki model kutusunu açıyor, `/durdur`
//     Durdur düğmesine basıyor. Yeni komut eklemek defterde tek satır.
//   * `@` ile seçilen dosya GİZLİCE eklenmiyor. Cip olarak görünüyor ve
//     mesaja giren cümle cipte yazan yolun aynısı: "Kullanıcı şu dosyayı
//     işaret etti: <yol>". Kullanıcı ne gönderdiğini okuyabiliyor.

Dil.ekle({
  "Yeni konuşma başlat": "Start a new conversation",
  "Geçmiş konuşmalar": "Past conversations",
  "Model seç — katalogda ara": "Pick a model — search the catalogue",
  "Yetki kipini değiştir": "Change the permission mode",
  "Koşan görevler — arka plan işleri ve yardımcılar":
    "Running tasks — background jobs and helpers",
  "Atölyedeki uygulamalar": "Apps in the workshop",
  "Yayınlanan artifact'lar — Uygulamalar panelinde":
    "Published artifacts — in the Apps panel",
  "Ayar sayfasını aç": "Open settings",
  "Bağlamı sıkıştır — konuşma kesilmez": "Compact the context — the conversation continues",
  "Koşan turu durdur": "Stop the running turn",
  "Komutlar ve kısayollar": "Commands and shortcuts",
  "Eşleşen komut yok.": "No matching command.",
  "Komutlar": "Commands",
  "Dosya ara": "Search files",
  "Eşleşen dosya yok.": "No matching file.",
  "Aranıyor…": "Searching…",
  "Bahisten çıkar": "Remove mention",
  "Kısayollar": "Shortcuts",
  "Enter — gönder · Shift+Enter — alt satır": "Enter — send · Shift+Enter — new line",
  "/ — komut defteri · @ — dosya işaret et": "/ — command book · @ — mention a file",
  "Escape — açık kutuyu kapat": "Escape — close the open box",
  "Bağlam sıkıştırılamadı.": "Could not compact the context.",
  "işaret edilen dosya": "mentioned file",
});

const Komut = (() => {
  const input = document.getElementById("input");
  const pop = document.getElementById("compose-pop");
  const chipBox = document.getElementById("mentions");

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  const tik = (id) => { const b = document.getElementById(id); if (b) b.click(); };

  const gonder = (yol, govde) => fetch(yol, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(govde || {}),
  }).then(r => r.json()).catch(() => null);

  // --- komut defteri ---------------------------------------------------
  //
  // Tek gerçek kaynak. Yeni bir komut eklemek buraya tek satır yazmak;
  // menü, süzgeç, klavye gezinmesi ve `/yardim` listesi kendiliğinden
  // öğreniyor.
  const DEFTER = [
    { ad: "yeni", ne: "Yeni konuşma başlat", kos: () => tik("new-chat") },
    { ad: "gecmis", ne: "Geçmiş konuşmalar", kos: () => tik("history") },
    { ad: "model", ne: "Model seç — katalogda ara", kos: () => tik("dock-model") },
    { ad: "yetki", ne: "Yetki kipini değiştir", kos: () => tik("dock-mode") },
    { ad: "gorevler", ne: "Koşan görevler — arka plan işleri ve yardımcılar",
      kos: () => {
        if (window.JobsPanel && JobsPanel.openLive) JobsPanel.openLive();
        else tik("jobs");
      } },
    { ad: "uygulamalar", ne: "Atölyedeki uygulamalar", kos: () => tik("apps") },
    { ad: "artifact", ne: "Yayınlanan artifact'lar — Uygulamalar panelinde",
      kos: () => tik("apps") },
    { ad: "ayarlar", ne: "Ayar sayfasını aç", kos: () => tik("gear") },
    { ad: "sifirla", ne: "Bağlamı sıkıştır — konuşma kesilmez", kos: sikistir },
    // Durdurma kendi düğmesinden geçiyor: ikinci bir kesme yolu açmak,
    // günün birinde biri değişip öteki kalmak demek.
    { ad: "durdur", ne: "Koşan turu durdur", kos: () => tik("stop") },
    { ad: "yardim", ne: "Komutlar ve kısayollar", kos: yardim },
  ];

  async function sikistir() {
    const cevap = await gonder("/api/compact");
    if (cevap && cevap.ok === false) {
      line("alert", cevap.error || t("Bağlam sıkıştırılamadı."));
    }
  }

  // `/yardim`: defterin kendisinden çizilen kart. Elle tutulan ikinci bir
  // liste bir gün defterden ayrı düşerdi.
  function yardim() {
    // Kendi sınıfı: `system` satırı tek satırlık bir not için biçimlenmiş
    // (nowrap + ellipsis) ve çok satırlı bir kartı görünmez yapıyor.
    const kart = line("help");
    kart.replaceChildren();
    kart.append(el("div", "help-head", t("Komutlar")));
    for (const k of DEFTER) {
      const satir = el("div", "help-row");
      satir.append(el("b", null, "/" + k.ad));
      satir.append(el("span", null, t(k.ne)));
      kart.append(satir);
    }
    kart.append(el("div", "help-head", t("Kısayollar")));
    for (const s of ["Enter — gönder · Shift+Enter — alt satır",
                     "/ — komut defteri · @ — dosya işaret et",
                     "Escape — açık kutuyu kapat"]) {
      kart.append(el("div", "help-row hint", t(s)));
    }
    scroll();
  }

  // --- durum makinesi --------------------------------------------------
  //
  // kip: "" (kapalı) · "komut" · "dosya"
  // at:  tetikleyen karakterin metindeki yeri — seçim yapılınca `@sorgu` ya
  //      da `/sorgu` parçası tam olarak buradan silinir.
  const durum = { kip: "", sorgu: "", at: -1, liste: [], secili: 0, baslik: "" };

  // `/` YALNIZCA satır başında komuttur: cümlenin ortasındaki eğik çizgi
  // (bir yol, bir kesir) menü açmamalı.
  const KOMUT_KALIBI = /(?:^|\n)\/([\wğüşıöçĞÜŞİÖÇ.-]*)$/;
  // `@` boşluktan sonra ya da satır başında. İçinde boşluk ve ikinci bir
  // `@` olmayan her şey sorgu.
  const DOSYA_KALIBI = /(?:^|\s)@([^\s@]*)$/;

  function bak() {
    const caret = input.selectionStart;
    const onu = input.value.slice(0, caret);
    let m = KOMUT_KALIBI.exec(onu);
    if (m) return ac("komut", m[1], caret - m[1].length - 1);
    m = DOSYA_KALIBI.exec(onu);
    if (m) return ac("dosya", m[1], caret - m[1].length - 1);
    kapat();
  }

  function ac(kip, sorgu, at) {
    const yeniKip = durum.kip !== kip;
    durum.kip = kip;
    durum.sorgu = sorgu;
    durum.at = at;
    if (yeniKip) durum.secili = 0;
    if (kip === "komut") komutlariCiz();
    else dosyalariAra();
  }

  function kapat() {
    durum.kip = "";
    durum.liste = [];
    durum.secili = 0;
    pop.hidden = true;
  }

  const acikMi = () => !pop.hidden && durum.kip !== "";

  // Klavye: kutu açıkken ok tuşları gezer, Enter seçer, Escape kapatır.
  // Dinleyici BELGEDE ve yakalama evresinde: app.js'in Enter → gönder
  // dinleyicisi kompozerin üzerinde duruyor ve kutu açıkken mesajın
  // gitmemesi gerekiyor.
  function tus(ev) {
    if (!acikMi() || ev.target !== input) return;
    if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); kapat(); return; }
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      if (!durum.liste.length) return;
      ev.preventDefault(); ev.stopPropagation();
      const yon = ev.key === "ArrowDown" ? 1 : -1;
      durum.secili = (durum.secili + yon + durum.liste.length) % durum.liste.length;
      ciz();
      return;
    }
    if (ev.key === "Enter" || ev.key === "Tab") {
      if (!durum.liste.length) return;
      ev.preventDefault(); ev.stopPropagation();
      sec(durum.secili);
    }
  }

  function sec(i) {
    const madde = durum.liste[i];
    if (!madde) return;
    const kip = durum.kip;
    kirp();
    kapat();
    if (kip === "komut") madde.kos();
    else bahisEkleYol(madde.path);
    input.focus();
  }

  // Tetikleyici parçayı metinden çıkarır: seçim yapıldıktan sonra kompozerde
  // yarım kalmış bir `/mod` ya da `@src/a` durmamalı.
  function kirp() {
    if (durum.at < 0) return;
    const caret = input.selectionStart;
    input.value = input.value.slice(0, durum.at) + input.value.slice(caret);
    input.selectionStart = input.selectionEnd = durum.at;
    input.dispatchEvent(new Event("input"));
  }

  // --- çizim -----------------------------------------------------------

  function komutlariCiz() {
    const want = durum.sorgu.toLowerCase();
    durum.liste = DEFTER.filter(k => !want || k.ad.includes(want));
    if (durum.secili >= durum.liste.length) durum.secili = 0;
    ciz(t("Komutlar"));
  }

  // Başlık durumda saklanıyor: ok tuşuyla yeniden çizerken parametre
  // gelmiyor ve kutunun başlığı ("KOMUTLAR") her gezinmede kayboluyordu.
  function ciz(baslik) {
    if (baslik !== undefined) durum.baslik = baslik;
    pop.replaceChildren();
    pop.hidden = false;
    if (durum.baslik) pop.append(el("div", "pop-head", durum.baslik));
    if (!durum.liste.length) {
      pop.append(el("div", "pop-note",
        durum.kip === "komut" ? t("Eşleşen komut yok.") : t("Eşleşen dosya yok.")));
    }
    durum.liste.forEach((madde, i) => {
      const satir = el("div", "pop-row" + (i === durum.secili ? " sel" : ""));
      satir.append(el("b", null, durum.kip === "komut" ? "/" + madde.ad : madde.name));
      satir.append(el("span", null, durum.kip === "komut" ? t(madde.ne) : madde.path));
      // Fareyle seçim de aynı yoldan: iki ayrı seçim mantığı olmasın.
      satir.addEventListener("mousedown", (ev) => { ev.preventDefault(); sec(i); });
      pop.append(satir);
    });
    yerlestir();
  }

  function yerlestir() {
    const at = input.getBoundingClientRect();
    pop.style.left = Math.max(8, at.left) + "px";
    pop.style.bottom = (window.innerHeight - at.top + 10) + "px";
    pop.style.maxWidth = Math.min(560, window.innerWidth - 24) + "px";
  }

  // --- dosya arama -----------------------------------------------------
  //
  // Her tuşta ağa çıkmıyor: kısa bir gecikme ve bir jeton. Geç dönen eski
  // bir cevap yeni sorgunun listesini EZMEMELİ — yazarken listenin bir
  // öncekine geri atlaması tam olarak böyle oluyordu.
  let aramaTimer = null;
  let jeton = 0;

  function dosyalariAra() {
    clearTimeout(aramaTimer);
    const benim = ++jeton;
    const q = durum.sorgu;
    aramaTimer = setTimeout(async () => {
      let bulunan = [];
      try {
        const cevap = await (await fetch("/api/files/search?q=" + encodeURIComponent(q))).json();
        bulunan = (cevap && cevap.files) || [];
      } catch { bulunan = []; }
      if (benim !== jeton || durum.kip !== "dosya") return;
      durum.liste = bulunan;
      if (durum.secili >= durum.liste.length) durum.secili = 0;
      ciz(t("Dosya ara"));
    }, 110);
    // Bekletirken kutu boş kalmasın.
    if (!durum.liste.length) {
      pop.replaceChildren(el("div", "pop-head", t("Dosya ara")),
                          el("div", "pop-note", t("Aranıyor…")));
      pop.hidden = false;
      yerlestir();
    }
  }

  // --- bahisler --------------------------------------------------------

  let bahis = [];

  function bahisEkleYol(path) {
    if (!path || bahis.includes(path)) return;
    bahis.push(path);
    bahisCiz();
  }

  function bahisCiz() {
    chipBox.replaceChildren();
    chipBox.hidden = !bahis.length;
    for (const yol of bahis) {
      const cip = el("span", "chip mention");
      cip.append(el("span", "mention-at", "@"));
      cip.append(el("span", "mention-yol", yol));
      cip.title = yol;
      const x = el("button", null, "×");
      x.type = "button";
      x.title = t("Bahisten çıkar");
      x.onclick = () => { bahis = bahis.filter(p => p !== yol); bahisCiz(); };
      cip.append(x);
      chipBox.append(cip);
    }
  }

  // Mesaja giren cümle. Gizli enjeksiyon yok: yazan şey cipte görünenin
  // aynısı ve gönderilen metinde de duruyor.
  function bahisEkle(text) {
    if (!bahis.length) return text;
    const satirlar = bahis.map(p => "Kullanıcı şu dosyayı işaret etti: " + p).join("\n");
    bahis = [];
    bahisCiz();
    return (text ? text + "\n\n" : "") + satirlar;
  }

  // --- bağlama ---------------------------------------------------------

  input.addEventListener("input", bak);
  input.addEventListener("click", bak);
  input.addEventListener("keyup", (ev) => {
    if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") bak();
  });
  input.addEventListener("blur", () => setTimeout(kapat, 120));
  document.addEventListener("keydown", tus, true);

  return { DEFTER, durum, ac, kapat, tus, sec, acikMi, bahisEkle, bahisler: () => bahis.slice() };
})();
