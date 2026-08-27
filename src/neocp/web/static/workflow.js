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

  const SINIF = { "koşuyor": "wf-run", "kosuyor": "wf-run",
                  "onarılıyor": "wf-run",
                  "bitti": "wf-done", "hata": "wf-fail" };
  const ISARET = { "koşuyor": "…", "kosuyor": "…", "onarılıyor": "⟳",
                   "bitti": "✓", "hata": "✗" };

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

    // Kenar çizgileri (SVG)
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "wf-edges");
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", "100%");
    canvas.append(svg);

    const byId = {};
    nodes.forEach((n, i) => {
      const x = (n.position && n.position.x) || 40 + (i % 3) * 180;
      const y = (n.position && n.position.y) || 40 + Math.floor(i / 3) * 100;
      const adim = adimlar[n.id];
      const sinif = adim ? (SINIF[adim.status] || "") : "";
      const card = el("div", "wf-node" + (sinif ? " " + sinif : ""));
      card.style.left = x + "px";
      card.style.top = y + "px";
      card.dataset.id = n.id;
      card.append(el("span", "wf-node-type", n.type || "custom"));
      card.append(el("b", "wf-node-title", n.title || n.id));
      if (adim) {
        // Durum hem renkle hem YAZIYLA: renk tek başına ne ekran
        // okuyucuya ne de renk ayrımı zor olan göze bir şey söyler.
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
      if ((n.secrets_needed || []).length) {
        card.append(el("span", "wf-node-sec", "🔑 " + n.secrets_needed.join(", ")));
      }
      if (n.elle) {
        // Kullanıcı bu adımı elle yazdı: onarım ona dokunmuyor, ve bunun
        // görünür olması gerekiyor — yoksa "niye düzeltmedi" sorusu doğar.
        const kilit = el("span", "wf-node-lock", "✎ " + t("elle"));
        kilit.title = t("Elle düzenlendi — otomatik onarım bu adıma dokunmaz.");
        card.append(kilit);
      }
      card.onclick = (ev) => {
        ev.stopPropagation();
        openInspector(wrap, wf, n, onSave);
      };
      // Sürükle
      let drag = null;
      card.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        drag = { ox: e.clientX - x, oy: e.clientY - y };
        card.setPointerCapture(e.pointerId);
      });
      card.addEventListener("pointermove", (e) => {
        if (!drag) return;
        const nx = e.clientX - drag.ox;
        const ny = e.clientY - drag.oy;
        card.style.left = nx + "px";
        card.style.top = ny + "px";
        n.position = { x: nx, y: ny };
        drawEdges();
      });
      card.addEventListener("pointerup", () => { drag = null; });
      byId[n.id] = { n, card, get x() { return parseFloat(card.style.left) || 0; },
                     get y() { return parseFloat(card.style.top) || 0; } };
      canvas.append(card);
    });

    function drawEdges() {
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      for (const e of edges) {
        const a = byId[e.from || e.from_];
        const b = byId[e.to];
        if (!a || !b) continue;
        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute("x1", String(a.x + 70));
        line.setAttribute("y1", String(a.y + 28));
        line.setAttribute("x2", String(b.x + 70));
        line.setAttribute("y2", String(b.y + 28));
        // Geçilmiş kenar belirgin, koşan adıma giden kenar vurgulu:
        // gözün akışta nerede olduğunu takip edebilmesi için.
        const gelinen = adimlar[e.from || e.from_];
        const aktif = e.to === kosan;
        const gecildi = gelinen && gelinen.status === "bitti";
        line.setAttribute("stroke", "currentColor");
        line.setAttribute("stroke-width", aktif ? "2.5" : "1.5");
        line.setAttribute("opacity", aktif ? "0.95" : gecildi ? "0.7" : "0.35");
        if (aktif) line.setAttribute("class", "wf-edge-live");
        svg.append(line);
      }
    }
    drawEdges();

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
    bar.append(add, save);

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
