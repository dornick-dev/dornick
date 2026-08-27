// Koşan görevler paneli — arkada dönen HER işin tek defteri.
//
// Üç kaynak tek listede, çünkü kullanıcı için üçü de aynı şey ("arkada bir
// şey koşuyor"):
//
//   * arka plan kabuk işleri  — `shell` aracının `arka_plan: true` yolu
//   * arka plan yardımcıları  — `task` aracının doğurduğu alt ajanlar
//   * ayrılmış süreçler       — sunucular, panelden başlatılan uygulamalar
//
// Orkestra güvertesinden AYRI duruyor ve bu bilinçli: orkestra ŞU ANKİ
// turun koordinasyonunu gösteren, kendiliğinden açılıp kapanan bir sahne
// ("şef bekliyor, üç kanal çalışıyor"). Burası ise defter: süre sayıyor,
// tek tek durduruluyor, bitmiş işin çıktısına iniliyor ve turdan turaç
// geçse de duruyor. İkisini birleştirmek ya sahneyi kalıcı bir listeye ya
// da defteri kaybolan bir sahneye çevirirdi.
//
// Süre CANLI ama sunucu saniyede bir yoklanmıyor: satır `basladi` damgasını
// taşıyor, saymayı tarayıcı yapıyor. Ağa yalnızca durum değişince ya da
// birkaç saniyede bir çıkılıyor.

Dil.ekle({
  "Koşan görevler": "Running tasks",
  "Şu an arkada koşan bir iş yok.": "Nothing is running in the background.",
  "Bir işi arka plana aldığında ya da bir yardımcı doğurduğunda burada belirir.":
    "It shows up here when a job goes background or a helper is spawned.",
  " iş koşuyor": " job(s) running",
  "Hepsi bitti": "All done",
  "Durdur": "Stop",
  "Durduruluyor…": "Stopping…",
  "koşuyor": "running",
  "bitti": "done",
  "hata": "failed",
  "yarım kaldı": "left unfinished",
  "yardımcı": "helper",
  "iş": "job",
  "süreç": "process",
  "(çıktı yok)": "(no output)",
  "Adımlar yükleniyor…": "Loading steps…",
  "Adım bulunamadı.": "No steps found.",
  "Döküm okunamadı.": "Could not read the log.",
  "sonucu gör": "see the result",
  "bitti · ": "done · ",
  "hata verdi · ": "failed · ",
});

const Gorevler = (() => {
  const panel = document.getElementById("tasks-panel");
  const body = document.getElementById("tasks-body");
  const durumSatiri = document.getElementById("tasks-status");
  const rozet = document.getElementById("tasks-badge");

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  let satirlar = [];
  let acikOlan = new Set();     // hangi görevin çıktısı açık
  let dokumler = new Map();     // görev kimliği → adım listesi (bir kez çekilir)
  let yoklama = null;
  let saniye = null;

  const DURUM_ETIKET = {
    kosuyor: "koşuyor", bitti: "bitti", hata: "hata", yetim: "yarım kaldı",
  };

  // --- veri ------------------------------------------------------------

  async function tazele() {
    let veri;
    try { veri = await (await fetch("/api/gorevler")).json(); }
    catch { return; }
    satirlar = (veri && veri.gorevler) || [];
    rozetCiz(veri && veri.kosan);
    if (!panel.hidden) ciz();
  }

  function rozetCiz(kosan) {
    if (!rozet) return;
    const n = Number(kosan) || 0;
    rozet.hidden = n === 0;
    rozet.textContent = n > 9 ? "9+" : String(n);
  }

  // --- çizim -----------------------------------------------------------

  function ciz() {
    body.replaceChildren();
    if (!satirlar.length) {
      const bos = el("div", "tasks-blank");
      bos.append(el("p", null, t("Şu an arkada koşan bir iş yok.")));
      bos.append(el("p", "tasks-blank-hint",
        t("Bir işi arka plana aldığında ya da bir yardımcı doğurduğunda burada belirir.")));
      body.append(bos);
    }
    for (const g of satirlar) body.append(kart(g));

    const kosan = satirlar.filter(g => g.durum === "kosuyor").length;
    durumSatiri.textContent = kosan
      ? kosan + t(" iş koşuyor")
      : (satirlar.length ? t("Hepsi bitti") : "");
    durumSatiri.className = "tasks-status" + (kosan ? " live" : "");
  }

  function kart(g) {
    const wrap = el("div", "task " + g.durum);
    const top = el("div", "task-top");
    top.append(el("span", "task-dot"));
    top.append(el("span", "task-name", g.ad || g.id));
    top.append(el("span", "task-kind " + turSinifi(g.tur), t(g.tur)));
    wrap.append(top);

    const alt = el("div", "task-line");
    alt.append(el("span", "task-state", t(DURUM_ETIKET[g.durum] || g.durum)));
    const sure = el("span", "task-time");
    sure.dataset.basladi = String(g.basladi || 0);
    sure.dataset.bitti = String(g.bitti || 0);
    sure.dataset.kosuyor = g.durum === "kosuyor" ? "1" : "";
    sure.textContent = sureMetni(sure);
    alt.append(sure);
    if (g.model) alt.append(el("span", "task-model", kisaModel(g.model)));

    if (g.durdurulabilir) {
      const dur = el("button", "task-stop", t("Durdur"));
      dur.type = "button";
      dur.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        dur.disabled = true;
        dur.textContent = t("Durduruluyor…");
        await fetch("/api/gorevler/durdur", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: g.id }),
        }).catch(() => {});
        tazele();
      });
      alt.append(dur);
    }
    wrap.append(alt);

    // Çıktıya in: bitmiş işin özeti, yardımcının kendi adım listesi.
    const inilir = g.durum !== "kosuyor" || !!g.oturum;
    if (inilir) {
      wrap.classList.add("clickable");
      wrap.addEventListener("click", () => {
        if (acikOlan.has(g.id)) acikOlan.delete(g.id);
        else { acikOlan.add(g.id); if (g.oturum) dokumGetir(g); }
        ciz();
      });
    }
    if (acikOlan.has(g.id)) wrap.append(cikti(g));
    return wrap;
  }

  function cikti(g) {
    const kutu = el("div", "task-out");
    if (g.ozet) kutu.append(el("div", "task-ozet", g.ozet));
    if (g.komut) kutu.append(el("div", "task-cmd", "$ " + g.komut));
    if (!g.oturum) {
      if (!g.ozet && !g.komut) kutu.append(el("div", "task-ozet", t("(çıktı yok)")));
      return kutu;
    }
    const adimlar = dokumler.get(g.id);
    if (adimlar === undefined) {
      kutu.append(el("div", "task-ozet", t("Adımlar yükleniyor…")));
      return kutu;
    }
    if (adimlar === null) {
      kutu.append(el("div", "task-ozet", t("Döküm okunamadı.")));
      return kutu;
    }
    if (!adimlar.length) {
      kutu.append(el("div", "task-ozet", t("Adım bulunamadı.")));
      return kutu;
    }
    const liste = el("div", "task-steps");
    for (const a of adimlar) {
      if (a.tur === "arac") {
        const s = el("div", "task-step" + (a.hata ? " err" : ""));
        s.append(el("span", "task-step-mark", a.hata ? "✗" : "·"));
        s.append(el("b", null, a.ad));
        s.append(el("span", "task-step-target", a.hedef || ""));
        if (a.ms) s.append(el("span", "task-step-ms", ms(a.ms)));
        liste.append(s);
      } else {
        liste.append(el("div", "task-step say", a.metin));
      }
    }
    kutu.append(liste);
    return kutu;
  }

  async function dokumGetir(g) {
    if (dokumler.has(g.id)) return;
    let veri;
    try {
      veri = await (await fetch("/api/gorevler/dokum?oturum="
        + encodeURIComponent(g.oturum))).json();
    } catch { veri = null; }
    dokumler.set(g.id, veri && veri.ok ? (veri.adimlar || []) : null);
    if (!panel.hidden) ciz();
  }

  // --- süre ------------------------------------------------------------

  function sureMetni(node) {
    const basladi = Number(node.dataset.basladi) || 0;
    if (!basladi) return "";
    const bitti = Number(node.dataset.bitti) || 0;
    const son = node.dataset.kosuyor ? Date.now() / 1000 : (bitti || basladi);
    return kisaSure(Math.max(0, son - basladi));
  }

  function kisaSure(sn) {
    if (sn < 60) return Math.round(sn) + " sn";
    const dk = Math.floor(sn / 60);
    if (dk < 60) return dk + " dk " + Math.round(sn % 60) + " sn";
    return Math.floor(dk / 60) + " sa " + (dk % 60) + " dk";
  }

  const ms = (n) => (n >= 1000 ? (n / 1000).toFixed(1) + " sn" : n + " ms");

  const kisaModel = (m) => {
    const cut = String(m).split("/").pop();
    return cut.length > 20 ? cut.slice(0, 20) + "…" : cut;
  };

  const turSinifi = (tur) => (tur === "süreç" ? "proc"
    : tur === "iş" ? "job" : "helper");

  // --- panel -----------------------------------------------------------

  function ac() {
    panel.hidden = false;
    document.body.classList.add("tasks-open");
    tazele();
    baslatYoklama();
  }

  function kapat() {
    panel.hidden = true;
    document.body.classList.remove("tasks-open");
    durYoklama();
  }

  function toggle() { if (panel.hidden) ac(); else kapat(); }

  function baslatYoklama() {
    durYoklama();
    // Panel açıkken durum birkaç saniyede bir tazeleniyor: süreçler
    // (ayrılmış PID'ler) olay yaymıyor, ancak yoklamayla ölürken görülüyor.
    yoklama = setInterval(tazele, 4000);
    // Süre sayacı ayrı ve ucuz: DOM'u yeniden kurmadan yalnız rakamı yazar.
    saniye = setInterval(() => {
      for (const node of body.querySelectorAll(".task-time")) {
        node.textContent = sureMetni(node);
      }
    }, 1000);
  }

  function durYoklama() {
    clearInterval(yoklama); yoklama = null;
    clearInterval(saniye); saniye = null;
  }

  // --- sohbete bildirim ------------------------------------------------
  //
  // Arka plandaki bir iş bitince kullanıcı paneli açık tutmuyor olabilir.
  // Sohbete tek tıklanabilir satır düşüyor: tıklayınca panel açılıyor ve o
  // işin çıktısı açık geliyor. Yalnız ARKA PLAN işleri için — senkron bir
  // yardımcının sonucu zaten cevabın içinde.
  function bitti(ev) {
    tazele();
    if (!ev || !ev.bg) return;
    const satir = line("alert task-done");
    satir.replaceChildren();
    const dugme = el("button", "task-note");
    dugme.type = "button";
    dugme.append(el("span", "task-note-mark", ev.ok ? "✓" : "✗"));
    dugme.append(el("span", "task-note-name", ev.title || ""));
    dugme.append(el("span", "task-note-go",
      (ev.ok ? t("bitti · ") : t("hata verdi · ")) + t("sonucu gör")));
    dugme.addEventListener("click", () => {
      if (ev.id) acikOlan.add("c:" + ev.id);
      ac();
    });
    satir.append(dugme);
    scroll();
  }

  document.getElementById("tasks").addEventListener("click", toggle);
  document.getElementById("tasks-close").addEventListener("click", kapat);
  document.getElementById("tasks-refresh").addEventListener("click", tazele);

  // Açılışta bir kez: rozet gerçeği söylesin (panel kapalıyken de).
  tazele();

  return { ac, kapat, toggle, tazele, bitti, kisaSure };
})();
