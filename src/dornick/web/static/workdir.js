// Çalışma klasörü şeridi + klasör seçici/oluşturucu.
//
// Neden var: sohbet ekranında "şu an nerede çalışıyorum?" sorusunun cevabı
// hiçbir yerde yazmıyordu. Atölyede miyiz, bağlı bir klasörde mi —
// kullanıcı ancak ayarları açıp bakarak anlayabiliyordu (canlı yara,
// 02.09). Şerit bunu söylüyor ve tek tıkla değiştirmeyi açıyor.
//
// Klasör seçimi kullanıcının RIZASIDIR: atölye dışı bir dizin de seçilebilir
// (sandbox'ın kuralı da bu). Sunucu yalnız gerçekten tehlikeli kökleri
// (sürücü kökü, Windows/Program Files, ev dizininin kendisi) reddediyor.

Dil.ekle({
  "Çalışma klasörü": "Working folder",
  "Atölye": "Workshop",
  "atölye (varsayılan)": "workshop (default)",
  "bağlı klasör": "bound folder",
  "Klasör seç": "Choose folder",
  "Yeni klasör": "New folder",
  "Klasör seç — tıkla: değiştir": "Working folder — click to change",
  "Bu klasörde çalış": "Work here",
  "Üst klasör": "Parent",
  "Yeni klasörün adı": "New folder name",
  "Oluştur ve çalış": "Create and work here",
  "Atölyeye dön": "Back to workshop",
  "Kapat": "Close",
  "Yükleniyor…": "Loading…",
  "Bu klasör seçilemez": "This folder cannot be selected",
  "Bir ad yaz": "Type a name",
  "Klasör oluşturulamadı": "Could not create the folder",
  "Buradasın": "You are here",
});

const WorkDir = (() => {
  const bar = document.getElementById("workdir-bar");
  const nameEl = document.getElementById("workdir-name");
  const kindEl = document.getElementById("workdir-kind");
  const iconEl = document.getElementById("workdir-icon");
  const idBtn = document.getElementById("workdir-id");
  const pickBtn = document.getElementById("workdir-pick");
  const newBtn = document.getElementById("workdir-new");

  let acikYol = "";      // şu an bağlı klasör ("" = atölye)
  let atolye = "";       // atölye kökü (workspace)
  let panel = null;      // açık seçici paneli
  let gezinen = "";      // seçicide gezilen dizin

  const kisaAd = (yol) => String(yol || "").replace(/[\\/]+$/, "").split(/[\\/]/).pop() || yol;

  // Şeridi boya: atölyedeysek "Atölye", değilse klasör adı + tam yol ipucu.
  function ciz(proje, workspace) {
    if (!bar) return;
    acikYol = String(proje || "");
    atolye = String(workspace || "");
    bar.hidden = false;
    if (acikYol) {
      nameEl.textContent = kisaAd(acikYol);
      kindEl.textContent = Dil.t("bağlı klasör");
      iconEl.textContent = "📁";
      idBtn.title = acikYol;
      bar.classList.add("bound");
    } else {
      nameEl.textContent = Dil.t("Atölye");
      kindEl.textContent = Dil.t("atölye (varsayılan)");
      iconEl.textContent = "🗂";
      idBtn.title = atolye || Dil.t("Atölye");
      bar.classList.remove("bound");
    }
  }

  // --- seçici paneli ---------------------------------------------------

  function kapat() {
    if (panel) { panel.remove(); panel = null; }
  }

  function ac(kip) {
    kapat();
    panel = document.createElement("div");
    panel.className = "workdir-panel";
    const bas = document.createElement("div");
    bas.className = "workdir-panel-head";
    bas.textContent = Dil.t(kip === "yeni" ? "Yeni klasör" : "Klasör seç");
    const kapa = document.createElement("button");
    kapa.type = "button";
    kapa.className = "workdir-close";
    kapa.textContent = "✕";
    kapa.title = Dil.t("Kapat");
    kapa.onclick = kapat;
    bas.append(kapa);
    panel.append(bas);

    const govde = document.createElement("div");
    govde.className = "workdir-body";
    panel.append(govde);
    bar.parentElement.insertBefore(panel, bar);
    gozat(gezinen || acikYol || atolye || "", govde, kip);
  }

  // Sunucudaki /api/gozat ile dizin gezme (yerel dosya diyaloğu yok:
  // masaüstü katmanı ayrı süreç, bu tarayıcı içi gezgin bilinçli).
  async function gozat(yol, govde, kip) {
    govde.textContent = Dil.t("Yükleniyor…");
    let veri;
    try {
      veri = await (await fetch("/api/gozat?yol=" + encodeURIComponent(yol || ""))).json();
    } catch {
      govde.textContent = Dil.t("Bu klasör seçilemez");
      return;
    }
    gezinen = veri.yol || "";
    govde.textContent = "";

    // Konum satırı + üst klasör.
    const konum = document.createElement("div");
    konum.className = "workdir-crumb";
    const yolYazi = document.createElement("code");
    yolYazi.textContent = veri.yol || Dil.t("Buradasın");
    konum.append(yolYazi);
    if (veri.ust) {
      const ust = document.createElement("button");
      ust.type = "button";
      ust.className = "workdir-up";
      ust.textContent = "↑ " + Dil.t("Üst klasör");
      ust.onclick = () => gozat(veri.ust, govde, kip);
      konum.append(ust);
    }
    govde.append(konum);

    if (veri.hata) {
      const h = document.createElement("div");
      h.className = "workdir-warn";
      h.textContent = veri.hata;
      govde.append(h);
    }
    if (veri.uyari) {
      const u = document.createElement("div");
      u.className = "workdir-warn";
      u.textContent = veri.uyari;
      govde.append(u);
    }

    // Alt klasörler.
    const liste = document.createElement("div");
    liste.className = "workdir-list";
    for (const k of (veri.klasorler || [])) {
      const satir = document.createElement("button");
      satir.type = "button";
      satir.className = "workdir-row";
      satir.textContent = "📁 " + k.ad;
      satir.onclick = () => gozat(k.yol, govde, kip);
      liste.append(satir);
    }
    if (!(veri.klasorler || []).length) {
      const bos = document.createElement("div");
      bos.className = "workdir-empty";
      bos.textContent = "—";
      liste.append(bos);
    }
    govde.append(liste);

    // Eylem satırı.
    const eylem = document.createElement("div");
    eylem.className = "workdir-actions";
    if (kip === "yeni") {
      const ad = document.createElement("input");
      ad.type = "text";
      ad.className = "input-text";
      ad.placeholder = Dil.t("Yeni klasörün adı");
      const olustur = document.createElement("button");
      olustur.type = "button";
      olustur.className = "workdir-go";
      olustur.textContent = Dil.t("Oluştur ve çalış");
      olustur.onclick = async () => {
        const isim = ad.value.trim();
        if (!isim) { ad.focus(); return; }
        olustur.disabled = true;
        let c;
        try {
          c = await (await fetch("/api/klasor/olustur", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ust: veri.yol, ad: isim }),
          })).json();
        } catch { c = { ok: false }; }
        olustur.disabled = false;
        if (!c || !c.ok) {
          const h = document.createElement("div");
          h.className = "workdir-warn";
          h.textContent = (c && c.hata) || Dil.t("Klasör oluşturulamadı");
          eylem.append(h);
          return;
        }
        await bagla(c.yol);
      };
      eylem.append(ad, olustur);
    } else {
      const sec = document.createElement("button");
      sec.type = "button";
      sec.className = "workdir-go";
      sec.textContent = Dil.t("Bu klasörde çalış");
      sec.disabled = !!veri.engel || !veri.yol;
      if (veri.engel) sec.title = veri.engel;
      sec.onclick = () => bagla(veri.yol);
      eylem.append(sec);
      if (acikYol) {
        const geri = document.createElement("button");
        geri.type = "button";
        geri.className = "workdir-plain";
        geri.textContent = Dil.t("Atölyeye dön");
        geri.onclick = () => bagla("");
        eylem.append(geri);
      }
    }
    govde.append(eylem);
  }

  // Klasörü BU SOHBETE bağla (oturum metası; küresel ayar değişmiyor).
  async function bagla(yol) {
    const sid = (typeof oturumId !== "undefined" && oturumId) ? oturumId : "";
    if (!sid) { kapat(); return; }
    try {
      await fetch("/api/session/meta", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: sid, path: String(yol || "") }),
      });
    } catch { /* aşağıda durum yine tazelenir */ }
    kapat();
    ciz(yol, atolye);
    // Sunucu tarafı canlıya uygulandıktan sonra gerçeği geri oku.
    setTimeout(() => { if (typeof loadState === "function") loadState(); }, 250);
    if (typeof GitBar !== "undefined" && GitBar.refresh) GitBar.refresh();
  }

  if (idBtn) idBtn.onclick = () => (panel ? kapat() : ac("sec"));
  if (pickBtn) pickBtn.onclick = () => ac("sec");
  if (newBtn) newBtn.onclick = () => ac("yeni");

  return { ciz, kapat };
})();
