// Otomasyon akış editörü — düğümler + kenarlar (basit canvas).
// WorkflowView.render(wf, onSave, durum) → DOM düğümü.
//
// `durum`: {progress: [{id, status, detail}], cikti: {…}} — koşu sırasında
// gelen canlı ilerleme. Akış şeması koşarken de okunabilir olmalı: adımın
// hangisinde olduğunu görmek için ayrı bir listeye bakmak gerekiyorsa
// şemanın işi yarım kalıyor. Durum verilmezse editör eskisi gibi duruyor.

const WorkflowView = (() => {
  if (typeof Dil !== "undefined" && Dil.ekle) {
    Dil.ekle({
      "+ Düğüm": "+ Node",
      "Kaydet": "Save",
      "Uygula": "Apply",
      "Tür": "Type",
      "Başlık": "Title",
      "Prompt / config": "Prompt / config",
      "Secrets": "Secrets",
      "gizli alan adları (virgüllü)": "secret names (comma separated)",
      "type (custom, http, skill, …)": "type (custom, http, skill, …)",
      "Çıktı": "Output",
      "Çıktıyı aç": "Open output",
      "elle": "manual",
      "Sığdır": "Fit",
      "Akışın tamamını panele sığdır": "Fit the whole flow in the panel",
      "Yeni adım": "New step",
      "koşuyor": "running",
      "onarılıyor": "repairing",
      "bitti": "done",
      "hata": "failed",
      "Elle düzenlendi — otomatik onarım bu adıma dokunmaz.":
        "Edited by hand — automatic repair leaves this step alone.",
      "Akış yok — ajan oluşturabilir veya Kaydet ile başlat.":
        "No flow yet — the agent can create one, or start with Save.",
    });
  }
  const t = (s) => (typeof Dil !== "undefined" && Dil.t ? Dil.t(s) : s);
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  // Düğüm kimliği → koşu durumu. Bilinmeyen düğüm "bekliyor" sayılıyor:
  // henüz sırası gelmemiş bir adımı hatalı göstermek yanlış olur.
  function durumHaritasi(durum) {
    const harita = {};
    for (const p of (durum && durum.progress) || []) {
      if (p && p.id) harita[p.id] = p;
    }
    return harita;
  }

  // Düğüm türü → renk ailesi. Renk süs değil, sınıflandırma: bir bakışta
  // "bu adım dışarı mı çıkıyor, dosyaya mı dokunuyor, modele mi soruyor"
  // görünsün. Bilinmeyen tür nötr kalıyor — uydurma renk bilgi taşımaz.
  const KATEGORI = {
    mail_read: "gelen", mail: "gelen", http: "ag", browser: "ag",
    shell: "sistem", skill: "yetenek", agent: "model", custom: "model",
  };
  const kategori = (tur) => KATEGORI[String(tur || "").toLowerCase()] || "notr";

  // Kenar etiketi kendi sözlüğünü kullanıyor: aynı Türkçe kelime iki
  // bağlamda iki ayrı karşılık istiyor — düğüm durumu "hata" → *failed*,
  // dal koşulu "hata" → *on error*. Tek sözlükte biri ötekini eziyordu.
  const DAL_ETIKETI = { hata: "on error", fail: "on error", ok: "on ok" };
  function dalEtiketi(on) {
    const ham = String(on || "");
    if (typeof Dil === "undefined" || Dil.mode !== "en") return ham;
    return DAL_ETIKETI[ham.toLowerCase()] || ham;
  }

  const SINIF = { "koşuyor": "wf-run", "kosuyor": "wf-run",
                  "onarılıyor": "wf-run",
                  "bitti": "wf-done", "hata": "wf-fail" };
  const ISARET = { "koşuyor": "…", "kosuyor": "…", "onarılıyor": "⟳",
                   "bitti": "✓", "hata": "✗" };

  // -- yerleşim ---------------------------------------------------------
  //
  // Düğümler elle sürüklenmediyse GRAFİKTEN hesaplanıyor. Eskiden konumsuz
  // düğümler üçlü bir ızgaraya diziliyordu; ızgara akışı bilmediği için
  // oklar kartların arasından geçiyor ve sıra okunmuyordu. Katman = bir
  // düğüme gelmek için geçilmesi gereken en uzun yol; aynı katmandakiler
  // alt alta. Soldan sağa akan, çakışmayan bir diyagram çıkıyor.

  const KART_G = 168;   // kart genişliği
  const KART_Y = 76;    // kart yüksekliği (asgari)
  const YATAY  = 88;    // katmanlar arası boşluk
  const DIKEY  = 30;    // aynı katmandaki kartlar arası boşluk
  const PAY    = 20;    // tuvalin kenar payı

  function katmanla(nodes, edges) {
    const gelen = {};
    const kenarlar = [];
    for (const n of nodes) gelen[n.id] = 0;
    for (const e of edges) {
      const a = e.from || e.from_;
      const b = e.to;
      if (!(a in gelen) || !(b in gelen)) continue;
      kenarlar.push([a, b]);
      gelen[b] += 1;
    }
    // Kaynak düğümler (kimse kendisine gelmiyor); yoksa ilk düğüm.
    let sira = nodes.filter((n) => gelen[n.id] === 0).map((n) => n.id);
    if (!sira.length && nodes.length) sira = [nodes[0].id];

    const katman = {};
    for (const id of sira) katman[id] = 0;
    // Döngü olsa bile durması için adım sayısı sınırlı.
    const tavan = nodes.length * nodes.length + 4;
    let adim = 0;
    let kuyruk = sira.slice();
    while (kuyruk.length && adim++ < tavan) {
      const id = kuyruk.shift();
      for (const [a, b] of kenarlar) {
        if (a !== id) continue;
        const derinlik = (katman[id] || 0) + 1;
        if (katman[b] === undefined || katman[b] < derinlik) {
          katman[b] = derinlik;
          kuyruk.push(b);
        }
      }
    }
    // Grafiğe hiç bağlanmamış düğüm de bir yere konmalı.
    for (const n of nodes) if (katman[n.id] === undefined) katman[n.id] = 0;
    return katman;
  }

  function yerlestir(nodes, edges) {
    const katman = katmanla(nodes, edges);
    const kolonlar = {};
    for (const n of nodes) (kolonlar[katman[n.id]] ||= []).push(n);

    const enUzun = Math.max(1, ...Object.values(kolonlar).map((k) => k.length));
    const yerler = {};
    for (const [k, liste] of Object.entries(kolonlar)) {
      const kolonY = liste.length * KART_Y + (liste.length - 1) * DIKEY;
      const tamY = enUzun * KART_Y + (enUzun - 1) * DIKEY;
      const ust = PAY + (tamY - kolonY) / 2;      // kolonu dikeyde ortala
      liste.forEach((n, i) => {
        yerler[n.id] = {
          x: PAY + Number(k) * (KART_G + YATAY),
          y: ust + i * (KART_Y + DIKEY),
        };
      });
    }
    return yerler;
  }

  function render(wf, onSave, durum) {
    const wrap = el("div", "wf-editor");
    if (!wf) {
      wrap.append(el("p", "jobs-blank", t("Akış yok — ajan oluşturabilir veya Kaydet ile başlat.")));
      return wrap;
    }

    const adimlar = durumHaritasi(durum);
    const kosan = Object.keys(adimlar).find(
      (k) => (adimlar[k].status || "").startsWith("koş")
             || (adimlar[k].status || "").startsWith("kos"));
    const canvas = el("div", "wf-canvas");
    const nodes = wf.nodes || [];
    const edges = wf.edges || [];
    const otomatik = yerlestir(nodes, edges);
    // Sığdırma varsayılan AÇIK: kullanıcı akışı ilk açtığında tamamını
    // görmeli. Bir düğümü elle sürüklerse ölçek 1'e dönüyor — o an
    // yerleşimle uğraşıyor demektir, altından küçültmek rahatsız eder.
    let sigdir = true;
    let olcek = 1;
    // Düğme `ciz()` içinde okunuyor; bildirimi önce, gövdesi aşağıda.
    let sigdirDugmesi = null;

    // Düzlem: ölçek buraya uygulanıyor. Beş adımlı bir akış (~1280 px) dar
    // bir panele sığmıyordu ve kullanıcı diyagramın yarısını göremiyordu;
    // yatay kaydırma "nerede olduğunu görmek" için yeterli değil.
    const duzlem = el("div", "wf-plane");
    canvas.append(duzlem);

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "wf-edges");
    duzlem.append(svg);

    // Ok uçları: yön görünmeden akış okunmuyor. Üç tür — normal, koşan,
    // hata dalı — çünkü işaretin rengi `context-stroke` ile çizgiden
    // gelmiyor (Safari/WebView2 desteği güvenilmez), her biri ayrı.
    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    for (const [ad, sinif] of [["wf-ok", "wf-arrow"], ["wf-ok-canli", "wf-arrow-live"],
                               ["wf-ok-hata", "wf-arrow-fail"]]) {
      const m = document.createElementNS("http://www.w3.org/2000/svg", "marker");
      m.setAttribute("id", ad);
      m.setAttribute("viewBox", "0 0 10 10");
      m.setAttribute("refX", "9");
      m.setAttribute("refY", "5");
      m.setAttribute("markerWidth", "7");
      m.setAttribute("markerHeight", "7");
      m.setAttribute("orient", "auto-start-reverse");
      const u = document.createElementNS("http://www.w3.org/2000/svg", "path");
      u.setAttribute("d", "M 0 1 L 9 5 L 0 9 z");
      u.setAttribute("class", sinif);
      m.append(u);
      defs.append(m);
    }
    svg.append(defs);

    const byId = {};
    nodes.forEach((n) => {
      const yer = (n.position && Number.isFinite(n.position.x)) ? n.position : otomatik[n.id];
      const x = yer ? yer.x : PAY;
      const y = yer ? yer.y : PAY;
      const adim = adimlar[n.id];
      const sinif = adim ? (SINIF[adim.status] || "") : "";
      const card = el("div", "wf-node" + (sinif ? " " + sinif : ""));
      card.style.left = x + "px";
      card.style.top = y + "px";
      card.dataset.id = n.id;
      card.tabIndex = 0;

      const tur = el("span", "wf-node-type", n.type || "custom");
      tur.dataset.tur = kategori(n.type);
      card.append(tur);
      card.append(el("b", "wf-node-title", n.title || n.id));
      if (adim) {
        const rozet = el("span", "wf-node-state",
          (ISARET[adim.status] || "·") + " " + t(adim.status || ""));
        rozet.setAttribute("role", "status");
        card.append(rozet);
        if (adim.detail) {
          const not = el("span", "wf-node-detail", String(adim.detail).slice(0, 120));
          not.title = String(adim.detail);
          card.append(not);
        }
      }
      const alt = el("div", "wf-node-foot");
      if ((n.secrets_needed || []).length) {
        alt.append(el("span", "wf-node-sec", "🔑 " + n.secrets_needed.join(", ")));
      }
      if (n.elle) {
        const kilit = el("span", "wf-node-lock", "✎ " + t("elle"));
        kilit.title = t("Elle düzenlendi — otomatik onarım bu adıma dokunmaz.");
        alt.append(kilit);
      }
      if (alt.childNodes.length) card.append(alt);

      const ac = (ev) => { ev.stopPropagation(); openInspector(wrap, wf, n, onSave); };
      card.onclick = ac;
      card.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); ac(e); }
      };

      let drag = null;
      card.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        drag = { px: e.clientX, py: e.clientY,
                 x0: parseFloat(card.style.left) || 0,
                 y0: parseFloat(card.style.top) || 0 };
        card.setPointerCapture(e.pointerId);
        card.classList.add("wf-dragging");
        if (sigdir) { sigdir = false; ciz(); }
      });
      card.addEventListener("pointermove", (e) => {
        if (!drag) return;
        // Fare hareketi ekran pikseli; kart ölçekli düzlemde duruyor.
        // Bölmezsek ölçek küçükken kart fareden hızlı kaçıyor.
        const nx = Math.max(0, drag.x0 + (e.clientX - drag.px) / olcek);
        const ny = Math.max(0, drag.y0 + (e.clientY - drag.py) / olcek);
        card.style.left = nx + "px";
        card.style.top = ny + "px";
        n.position = { x: nx, y: ny };
        ciz();
      });
      const birak = () => { drag = null; card.classList.remove("wf-dragging"); };
      card.addEventListener("pointerup", birak);
      card.addEventListener("pointercancel", birak);

      byId[n.id] = {
        n, card,
        get x() { return parseFloat(card.style.left) || 0; },
        get y() { return parseFloat(card.style.top) || 0; },
        get h() { return card.offsetHeight || KART_Y; },
      };
      duzlem.append(card);
    });

    function ciz() {
      while (svg.lastChild && svg.lastChild !== defs) svg.removeChild(svg.lastChild);
      let enSag = 0, enAlt = 0;
      for (const k of Object.values(byId)) {
        enSag = Math.max(enSag, k.x + KART_G);
        enAlt = Math.max(enAlt, k.y + k.h);
      }
      const genislik = enSag + PAY;
      const yukseklik = enAlt + PAY;
      svg.setAttribute("width", String(genislik));
      svg.setAttribute("height", String(yukseklik));
      duzlem.style.width = genislik + "px";
      duzlem.style.height = yukseklik + "px";

      // Sığdırma: yalnızca KÜÇÜLTÜYOR. Küçük bir akışı panele yaymak için
      // büyütmek, üç kutuyu dev gösteren tuhaf bir görüntü veriyor.
      const alan = canvas.clientWidth - 2;
      olcek = (sigdir && alan > 0 && genislik > alan)
        ? Math.max(0.45, alan / genislik) : 1;
      duzlem.style.transform = olcek === 1 ? "" : `scale(${olcek})`;
      canvas.classList.toggle("wf-fit", olcek !== 1);
      // Tuval içeriğe göre büzülüyor. Sabit yükseklik, üç adımlık bir akışın
      // altında yarım panel boşluk bırakıyor ve ekran bitmemiş görünüyordu.
      canvas.style.height = Math.max(150, Math.round(yukseklik * olcek) + 2) + "px";
      if (sigdirDugmesi) {
        sigdirDugmesi.hidden = (olcek === 1 && sigdir);
        sigdirDugmesi.textContent = sigdir
          ? `${t("Sığdır")} · %${Math.round(olcek * 100)}`
          : t("Sığdır");
        sigdirDugmesi.setAttribute("aria-pressed", String(sigdir));
      }

      for (const e of edges) {
        const a = byId[e.from || e.from_];
        const b = byId[e.to];
        if (!a || !b) continue;
        const hata = (e.on || "") === "hata" || (e.on || "") === "fail";
        const gelinen = adimlar[e.from || e.from_];
        const aktif = e.to === kosan && gelinen && gelinen.status === "bitti";
        const gecildi = gelinen && gelinen.status === "bitti";

        // Kartın KENARINDAN çıkıp kenarına giriyor; ortadan ortaya çizmek
        // çizgiyi kartın altından geçiriyordu. Sağa akış yatay bezier,
        // aşağı/yukarı dallanma dikey çıkışlı.
        const x1 = a.x + KART_G, y1 = a.y + a.h / 2;
        const x2 = b.x,          y2 = b.y + b.h / 2;
        const yan = b.x > a.x + KART_G / 2;
        let d;
        if (yan) {
          const k = Math.max(28, (x2 - x1) / 2);
          d = `M ${x1} ${y1} C ${x1 + k} ${y1}, ${x2 - k} ${y2}, ${x2} ${y2}`;
        } else {
          // Aynı ya da geri katman: alttan dolaş.
          const ax = a.x + KART_G / 2, ay = a.y + a.h;
          const bx = b.x + KART_G / 2, by = b.y;
          const k = Math.max(28, (by - ay) / 2);
          d = `M ${ax} ${ay} C ${ax} ${ay + k}, ${bx} ${by - k}, ${bx} ${by}`;
        }
        const yol = document.createElementNS("http://www.w3.org/2000/svg", "path");
        yol.setAttribute("d", d);
        yol.setAttribute("fill", "none");
        yol.setAttribute("class",
          "wf-edge" + (hata ? " wf-edge-fail" : "") + (aktif ? " wf-edge-live" : "")
          + (gecildi && !aktif ? " wf-edge-done" : ""));
        yol.setAttribute("marker-end",
          `url(#${aktif ? "wf-ok-canli" : hata ? "wf-ok-hata" : "wf-ok"})`);
        svg.append(yol);

        // Koşullu dal etiketi: "hata" dalı ile normal dal aynı görünüyordu.
        if (e.on && e.on !== "ok") {
          const et = document.createElementNS("http://www.w3.org/2000/svg", "text");
          et.setAttribute("x", String((x1 + x2) / 2));
          et.setAttribute("y", String((y1 + y2) / 2 - 6));
          et.setAttribute("text-anchor", "middle");
          et.setAttribute("class", "wf-edge-tag" + (hata ? " wf-edge-tag-fail" : ""));
          et.textContent = dalEtiketi(e.on);
          svg.append(et);
        }
      }
    }
    ciz();
    // Kartların gerçek yüksekliği ancak DOM'a girince belli oluyor.
    requestAnimationFrame(ciz);

    const bar = el("div", "wf-bar");
    const add = el("button", "jobs-act", t("+ Düğüm"));
    add.type = "button";
    add.onclick = () => {
      const id = "n" + Math.random().toString(36).slice(2, 8);
      (wf.nodes || (wf.nodes = [])).push({
        id, title: t("Yeni adım"), type: "custom",
        config: { prompt: "" }, secrets_needed: [], skill: "",
        position: { x: 60, y: 60 },
      });
      if (onSave) onSave(wf);
    };
    const save = el("button", "jobs-act", t("Kaydet"));
    save.type = "button";
    save.onclick = () => onSave && onSave(wf);

    sigdirDugmesi = el("button", "jobs-act wf-fit-btn", t("Sığdır"));
    sigdirDugmesi.type = "button";
    sigdirDugmesi.hidden = true;
    sigdirDugmesi.title = t("Akışın tamamını panele sığdır");
    sigdirDugmesi.onclick = () => { sigdir = !sigdir; ciz(); };

    bar.append(add, save, sigdirDugmesi);

    wrap.append(bar, canvas);

    // Çıktı BURADA duruyor. Otomasyon sonunda bir uygulama üretse bile
    // kullanıcıyı Uygulamalar paneline göndermiyoruz: akışı kuran, koşuran
    // ve sonucunu okuyan aynı ekran. Uygulamalar listesi bir kaynak değil,
    // olsa olsa örnek.
    if (durum && (durum.rapor || durum.cikti)) {
      const out = el("div", "wf-out");
      out.append(el("h3", null, t("Çıktı")));
      if (durum.cikti && durum.cikti.yol) {
        const ac = el("button", "jobs-act jobs-act-primary",
          durum.cikti.baslik || t("Çıktıyı aç"));
        ac.type = "button";
        ac.onclick = () => {
          // Aynı ekranda: görüntüleyici panelinde açılıyor.
          if (typeof Viewer !== "undefined" && Viewer.open) Viewer.open(durum.cikti.yol);
        };
        out.append(ac);
      }
      if (durum.rapor) out.append(el("pre", "wf-out-text", durum.rapor));
      wrap.append(out);
    }

    const insp = el("div", "wf-inspector");
    wrap.append(insp);
    return wrap;
  }

  function openInspector(wrap, wf, node, onSave) {
    const box = wrap.querySelector(".wf-inspector");
    if (!box) return;
    box.replaceChildren();
    box.append(el("h3", null, node.title || node.id));
    const type = el("input", "input-text");
    type.value = node.type || "custom";
    type.placeholder = "type (custom, http, skill, …)";
    const title = el("input", "input-text");
    title.value = node.title || "";
    const prompt = el("textarea", "input-text");
    prompt.rows = 4;
    prompt.value = (node.config && node.config.prompt) || "";
    const secrets = el("input", "input-text");
    secrets.value = (node.secrets_needed || []).join(", ");
    secrets.placeholder = t("gizli alan adları (virgüllü)");
    const apply = el("button", "jobs-act", t("Uygula"));
    apply.type = "button";
    apply.onclick = () => {
      node.type = type.value.trim() || "custom";
      node.title = title.value.trim() || node.id;
      node.config = node.config || {};
      node.config.prompt = prompt.value;
      node.secrets_needed = secrets.value.split(",").map((s) => s.trim()).filter(Boolean);
      // Elle dokunulan adım işaretleniyor: kendini onarma buna bakıp
      // uzak duruyor. Modelin, kullanıcının bilerek yazdığı bir adımı
      // arkasından yeniden yazması düzeltme değil, sessizce geri almadır.
      node.elle = true;
      if (onSave) onSave(wf);
    };
    box.append(
      el("label", null, t("Tür")), type,
      el("label", null, t("Başlık")), title,
      el("label", null, t("Prompt / config")), prompt,
      el("label", null, t("Secrets")), secrets,
      apply,
    );
  }

  return { render };
})();
