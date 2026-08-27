// Canlı koşum defteri — Görevler panelinin "Canlı" sekmesi.
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
  "Devam et": "Continue",
  "Sürdürülüyor…": "Resuming…",
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
  "raporu aç": "open report",
  "bitti · ": "done · ",
  "hata verdi · ": "failed · ",
  "Model bekleniyor": "Waiting for model",
  "Canlı uygulamayı aç": "Open live app",
});

const Gorevler = (() => {
  const rozet = document.getElementById("jobs-badge");

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  let body = null;
  let durumSatiri = null;
  let host = null;
  let gorunur = false;

  let satirlar = [];
  let acikOlan = new Set();     // hangi görevin çıktısı açık
  let dokumler = new Map();     // görev kimliği → {adimlar, ts}
  const DOKUM_TTL_MS = 2500;
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
    if (gorunur && body) {
      ciz();
      // Açık koşan kartların dökümü TTL ile yenilensin.
      for (const g of satirlar) {
        if (acikOlan.has(g.id) && g.oturum && g.durum === "kosuyor") {
          dokumGetir(g);
        }
      }
    }
  }

  function rozetCiz(kosan) {
    if (!rozet) return;
    const n = Number(kosan) || 0;
    rozet.hidden = n === 0;
    rozet.textContent = n > 9 ? "9+" : String(n);
  }

  // --- çizim -----------------------------------------------------------

  function mount(parent) {
    if (host && host.parentElement === parent) return host;
    host = el("div", "jobs-live");
    durumSatiri = el("div", "tasks-status");
    body = el("div", "tasks-body");
    host.append(durumSatiri, body);
    parent.replaceChildren(host);
    if (gorunur) ciz();
    return host;
  }

  function ciz() {
    if (!body) return;
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
    if (durumSatiri) {
      durumSatiri.textContent = kosan
        ? kosan + t(" iş koşuyor")
        : (satirlar.length ? t("Hepsi bitti") : "");
      durumSatiri.className = "tasks-status" + (kosan ? " live" : "");
    }
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
    if (g.durum === "kosuyor" && g.wait) {
      let msg = t("Model bekleniyor");
      const w = g.wait;
      if (w.deneme && w.toplam) msg += ` (${w.deneme}/${w.toplam})`;
      if (w.saniye) msg += ` · ${w.saniye}s`;
      alt.append(el("span", "task-wait", msg));
    } else if (g.durum === "kosuyor" && g.son_arac) {
      let line = "▶ " + g.son_arac;
      if (g.son_hedef) line += " · " + g.son_hedef;
      alt.append(el("span", "task-tool", line));
    }

    if (g.durdurulabilir) {
      const dur = el("button", "task-stop", t("Durdur"));
      dur.type = "button";
      dur.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        dur.disabled = true;
        dur.textContent = t("Durduruluyor…");
        let res = null;
        try {
          res = await (await fetch("/api/gorevler/durdur", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: g.id }),
          })).json();
        } catch { res = null; }
        if (res && res.ok === false) {
          dur.disabled = false;
          dur.textContent = t("Durdur");
        }
        tazele();
      });
      alt.append(dur);
    }
    if (g.surdurulebilir || g.durum === "yetim") {
      const devam = el("button", "task-resume", t("Devam et"));
      devam.type = "button";
      devam.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        devam.disabled = true;
        devam.textContent = t("Sürdürülüyor…");
        await fetch("/api/gorevler/devam", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: g.id }),
        }).catch(() => {});
        tazele();
      });
      alt.append(devam);
    }
    wrap.append(alt);

    const inilir = g.durum !== "kosuyor" || !!g.oturum;
    if (inilir) {
      wrap.classList.add("clickable");
      wrap.addEventListener("click", () => {
        if (g.durum !== "kosuyor" && g.deliverable && g.deliverable.url
            && typeof Viewer !== "undefined" && Viewer.page) {
          Viewer.page(g.deliverable.url, g.ad || g.id);
          return;
        }
        if (g.durum !== "kosuyor" && String(g.id || "").startsWith("c:")
            && typeof Viewer !== "undefined" && Viewer.page) {
          Viewer.page("/gorev-rapor/" + encodeURIComponent(g.id.slice(2)) + "/",
                      g.ad || g.id);
          return;
        }
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
    const cache = dokumler.get(g.id);
    const adimlar = cache === undefined ? undefined
      : (cache === null ? null : cache.adimlar);
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

  async function dokumGetir(g, { force = false } = {}) {
    const prev = dokumler.get(g.id);
    if (!force && prev && prev !== null
        && (Date.now() - (prev.ts || 0)) < DOKUM_TTL_MS) {
      return;
    }
    // Koşarken TTL dolunca yenile; bitmişse bir kez yeter.
    if (!force && g.durum !== "kosuyor" && prev !== undefined) return;
    let veri;
    try {
      veri = await (await fetch("/api/gorevler/dokum?oturum="
        + encodeURIComponent(g.oturum))).json();
    } catch { veri = null; }
    dokumler.set(g.id, veri && veri.ok
      ? { adimlar: veri.adimlar || [], ts: Date.now() }
      : null);
    if (gorunur && body) ciz();
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

  // --- görünürlük ------------------------------------------------------

  function setVisible(on) {
    gorunur = !!on;
    if (gorunur) {
      tazele();
      baslatYoklama();
    } else {
      durYoklama();
    }
  }

  function ac() {
    if (window.JobsPanel && JobsPanel.openLive) JobsPanel.openLive();
    else if (window.JobsPanel) JobsPanel.open();
  }

  function kapat() {
    if (window.JobsPanel) JobsPanel.close();
  }

  function toggle() { ac(); }

  function baslatYoklama() {
    durYoklama();
    yoklama = setInterval(tazele, 4000);
    saniye = setInterval(() => {
      if (!body) return;
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
      (ev.ok ? t("bitti · ") : t("hata verdi · ")) + t("raporu aç")));
    dugme.addEventListener("click", () => {
      const cid = ev.id || "";
      if (cid && typeof Viewer !== "undefined" && Viewer.page) {
        Viewer.page("/gorev-rapor/" + encodeURIComponent(cid) + "/", ev.title || cid);
        return;
      }
      if (cid) acikOlan.add("c:" + cid);
      ac();
    });
    satir.append(dugme);
    scroll();
  }

  // Açılışta bir kez: rozet gerçeği söylesin (panel kapalıyken de).
  tazele();

  return { ac, kapat, toggle, tazele, bitti, kisaSure, mount, setVisible, ciz };
})();
