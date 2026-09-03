// Automation flow editor — nodes + edges (simple canvas).
// WorkflowView.render(wf, onSave, status) → DOM node.
//
// `status`: {progress: [{id, status, detail}], cikti: {…}} — live progress
// arriving during a run. The flow diagram must stay readable while running:
// if you need a separate list to see which step you are on, the diagram has
// done only half its job. Without a status the editor behaves as before.

const WorkflowView = (() => {
  if (typeof Dil !== "undefined" && Dil.ekle) {
    Dil.ekle({
      "+ Düğüm": "+ Node",
      "Kaydet": "Save",
      "Uygula": "Apply",
      "Tür": "Type",
      "Başlık": "Title",
      "Prompt / config": "Prompt / config",
      "Prompt": "Prompt",
      "Model": "Model",
      "Secrets": "Secrets",
      "gizli alan adları (virgüllü)": "secret names (comma separated)",
      "type (custom, http, skill, …)": "type (custom, http, skill, …)",
      "Model adımı": "Model step",
      "Model adımı (agent)": "Model step (agent)",
      "HTTP isteği": "HTTP request",
      "Kabuk komutu": "Shell command",
      "Yetenek / araç": "Skill / tool",
      "Posta oku": "Read mail",
      "Yöntem": "Method",
      "Gövde": "Body",
      "gövde (JSON, isteğe bağlı)": "body (JSON, optional)",
      "Komut": "Command",
      "komut": "command",
      "Yetenek": "Skill",
      "yetenek adı": "skill name",
      "Argümanlar (JSON)": "Arguments (JSON)",
      "Kaç posta": "How many emails",
      "Bu adımda modele ne söylensin?": "What should the model do in this step?",
      "model (boş = varsayılan)": "model (empty = default)",
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

  // Node id → run status. An unknown node counts as "waiting": showing a
  // step whose turn has not come yet as failed would be wrong.
  function statusMap(status) {
    const map = {};
    for (const p of (status && status.progress) || []) {
      if (p && p.id) map[p.id] = p;
    }
    return map;
  }

  // Node type → color family. Color is not decoration, it is classification:
  // at a glance one should see "does this step go outside, touch a file, or
  // ask the model". An unknown type stays neutral — a made-up color carries
  // no information.
  const CATEGORY = {
    mail_read: "gelen", mail: "gelen", http: "ag", browser: "ag",
    shell: "sistem", skill: "yetenek", agent: "model", custom: "model",
  };
  const categoryOf = (kind) => CATEGORY[String(kind || "").toLowerCase()] || "notr";

  // The edge label uses its own dictionary: the same Turkish word wants two
  // different renderings in two contexts — node status "hata" → *failed*,
  // branch condition "hata" → *on error*. In a single dictionary one crushed
  // the other.
  const BRANCH_LABEL = { hata: "on error", fail: "on error", ok: "on ok" };
  function branchLabel(on) {
    const raw = String(on || "");
    if (typeof Dil === "undefined" || Dil.mode !== "en") return raw;
    return BRANCH_LABEL[raw.toLowerCase()] || raw;
  }

  const STATE_CLASS = { "koşuyor": "wf-run", "kosuyor": "wf-run",
                        "onarılıyor": "wf-run",
                        "bitti": "wf-done", "hata": "wf-fail" };
  const STATE_MARK = { "koşuyor": "…", "kosuyor": "…", "onarılıyor": "⟳",
                       "bitti": "✓", "hata": "✗" };

  // -- layout -----------------------------------------------------------
  //
  // Unless dragged by hand, node positions are computed FROM THE GRAPH.
  // Position-less nodes used to be laid out on a grid of three; the grid
  // knew nothing about the flow, so arrows crossed between cards and the
  // order was unreadable. Layer = the longest path needed to reach a node;
  // nodes on the same layer stack vertically. The result is a left-to-right,
  // non-overlapping diagram.

  const CARD_W = 168;   // card width
  const CARD_H = 76;    // card height (minimum)
  const H_GAP  = 88;    // gap between layers
  const V_GAP  = 30;    // gap between cards on the same layer
  const MARGIN = 20;    // canvas edge margin

  function layerize(nodes, edges) {
    const incoming = {};
    const pairs = [];
    for (const n of nodes) incoming[n.id] = 0;
    for (const e of edges) {
      const a = e.from || e.from_;
      const b = e.to;
      if (!(a in incoming) || !(b in incoming)) continue;
      pairs.push([a, b]);
      incoming[b] += 1;
    }
    // Source nodes (nothing points at them); otherwise the first node.
    let order = nodes.filter((n) => incoming[n.id] === 0).map((n) => n.id);
    if (!order.length && nodes.length) order = [nodes[0].id];

    const layer = {};
    for (const id of order) layer[id] = 0;
    // Step count is bounded so it halts even with a cycle.
    const cap = nodes.length * nodes.length + 4;
    let step = 0;
    let queue = order.slice();
    while (queue.length && step++ < cap) {
      const id = queue.shift();
      for (const [a, b] of pairs) {
        if (a !== id) continue;
        const depth = (layer[id] || 0) + 1;
        if (layer[b] === undefined || layer[b] < depth) {
          layer[b] = depth;
          queue.push(b);
        }
      }
    }
    // A node never connected to the graph still needs a place.
    for (const n of nodes) if (layer[n.id] === undefined) layer[n.id] = 0;
    return layer;
  }

  function autoPlace(nodes, edges) {
    const layer = layerize(nodes, edges);
    const columns = {};
    for (const n of nodes) (columns[layer[n.id]] ||= []).push(n);

    const tallest = Math.max(1, ...Object.values(columns).map((k) => k.length));
    const positions = {};
    for (const [k, list] of Object.entries(columns)) {
      const colH = list.length * CARD_H + (list.length - 1) * V_GAP;
      const fullH = tallest * CARD_H + (tallest - 1) * V_GAP;
      const top = MARGIN + (fullH - colH) / 2;    // center the column vertically
      list.forEach((n, i) => {
        positions[n.id] = {
          x: MARGIN + Number(k) * (CARD_W + H_GAP),
          y: top + i * (CARD_H + V_GAP),
        };
      });
    }
    return positions;
  }

  function render(wf, onSave, status) {
    const wrap = el("div", "wf-editor");
    if (!wf) {
      wrap.append(el("p", "jobs-blank", t("Akış yok — ajan oluşturabilir veya Kaydet ile başlat.")));
      return wrap;
    }

    const steps = statusMap(status);
    const running = Object.keys(steps).find(
      (k) => (steps[k].status || "").startsWith("koş")
             || (steps[k].status || "").startsWith("kos"));
    const canvas = el("div", "wf-canvas");
    const nodes = wf.nodes || [];
    const edges = wf.edges || [];
    const auto = autoPlace(nodes, edges);
    // Fit is ON by default: the first time the user opens a flow they should
    // see all of it. Dragging a node by hand snaps the scale back to 1 —
    // they are working on the layout at that moment, and shrinking it under
    // them would be jarring.
    let fit = true;
    let scale = 1;
    // The button is read inside `draw()`; declared first, its body below.
    let fitBtn = null;

    // Plane: the scale is applied here. A five-step flow (~1280 px) did not
    // fit a narrow panel and the user could not see half the diagram;
    // horizontal scrolling is not enough for "seeing where you are".
    const plane = el("div", "wf-plane");
    canvas.append(plane);

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "wf-edges");
    plane.append(svg);

    // Arrowheads: without a visible direction the flow is unreadable. Three
    // kinds — normal, running, error branch — because the mark's color does
    // not come from the line via `context-stroke` (Safari/WebView2 support
    // is unreliable), so each is separate.
    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    for (const [id, cls] of [["wf-ok", "wf-arrow"], ["wf-ok-canli", "wf-arrow-live"],
                             ["wf-ok-hata", "wf-arrow-fail"]]) {
      const m = document.createElementNS("http://www.w3.org/2000/svg", "marker");
      m.setAttribute("id", id);
      m.setAttribute("viewBox", "0 0 10 10");
      m.setAttribute("refX", "9");
      m.setAttribute("refY", "5");
      m.setAttribute("markerWidth", "7");
      m.setAttribute("markerHeight", "7");
      m.setAttribute("orient", "auto-start-reverse");
      const u = document.createElementNS("http://www.w3.org/2000/svg", "path");
      u.setAttribute("d", "M 0 1 L 9 5 L 0 9 z");
      u.setAttribute("class", cls);
      m.append(u);
      defs.append(m);
    }
    svg.append(defs);

    const byId = {};
    nodes.forEach((n) => {
      const pos = (n.position && Number.isFinite(n.position.x)) ? n.position : auto[n.id];
      const x = pos ? pos.x : MARGIN;
      const y = pos ? pos.y : MARGIN;
      const step = steps[n.id];
      const cls = step ? (STATE_CLASS[step.status] || "") : "";
      const card = el("div", "wf-node" + (cls ? " " + cls : ""));
      card.style.left = x + "px";
      card.style.top = y + "px";
      card.dataset.id = n.id;
      card.tabIndex = 0;

      const typeTag = el("span", "wf-node-type", n.type || "custom");
      typeTag.dataset.tur = categoryOf(n.type);
      card.append(typeTag);
      card.append(el("b", "wf-node-title", n.title || n.id));
      if (step) {
        const badge = el("span", "wf-node-state",
          (STATE_MARK[step.status] || "·") + " " + t(step.status || ""));
        badge.setAttribute("role", "status");
        card.append(badge);
        if (step.detail) {
          const detail = el("span", "wf-node-detail", String(step.detail).slice(0, 120));
          detail.title = String(step.detail);
          card.append(detail);
        }
      }
      const foot = el("div", "wf-node-foot");
      if ((n.secrets_needed || []).length) {
        foot.append(el("span", "wf-node-sec", "🔑 " + n.secrets_needed.join(", ")));
      }
      if (n.elle) {
        const lock = el("span", "wf-node-lock", "✎ " + t("elle"));
        lock.title = t("Elle düzenlendi — otomatik onarım bu adıma dokunmaz.");
        foot.append(lock);
      }
      if (foot.childNodes.length) card.append(foot);

      const openIt = (ev) => { ev.stopPropagation(); openInspector(wrap, wf, n, onSave); };
      card.onclick = openIt;
      card.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openIt(e); }
      };

      let drag = null;
      card.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        drag = { px: e.clientX, py: e.clientY,
                 x0: parseFloat(card.style.left) || 0,
                 y0: parseFloat(card.style.top) || 0 };
        card.setPointerCapture(e.pointerId);
        card.classList.add("wf-dragging");
        if (fit) { fit = false; draw(); }
      });
      card.addEventListener("pointermove", (e) => {
        if (!drag) return;
        // Mouse movement is in screen pixels; the card sits on the scaled
        // plane. Without dividing, at a small scale the card outruns the mouse.
        const nx = Math.max(0, drag.x0 + (e.clientX - drag.px) / scale);
        const ny = Math.max(0, drag.y0 + (e.clientY - drag.py) / scale);
        card.style.left = nx + "px";
        card.style.top = ny + "px";
        n.position = { x: nx, y: ny };
        draw();
      });
      const release = () => { drag = null; card.classList.remove("wf-dragging"); };
      card.addEventListener("pointerup", release);
      card.addEventListener("pointercancel", release);

      byId[n.id] = {
        n, card,
        get x() { return parseFloat(card.style.left) || 0; },
        get y() { return parseFloat(card.style.top) || 0; },
        get h() { return card.offsetHeight || CARD_H; },
      };
      plane.append(card);
    });

    function draw() {
      while (svg.lastChild && svg.lastChild !== defs) svg.removeChild(svg.lastChild);
      let rightMost = 0, bottomMost = 0;
      for (const k of Object.values(byId)) {
        rightMost = Math.max(rightMost, k.x + CARD_W);
        bottomMost = Math.max(bottomMost, k.y + k.h);
      }
      const width = rightMost + MARGIN;
      const height = bottomMost + MARGIN;
      svg.setAttribute("width", String(width));
      svg.setAttribute("height", String(height));
      plane.style.width = width + "px";
      plane.style.height = height + "px";

      // Fitting only SHRINKS. Enlarging a small flow to fill the panel gives
      // an odd picture of three giant boxes.
      const avail = canvas.clientWidth - 2;
      scale = (fit && avail > 0 && width > avail)
        ? Math.max(0.45, avail / width) : 1;
      plane.style.transform = scale === 1 ? "" : `scale(${scale})`;
      canvas.classList.toggle("wf-fit", scale !== 1);
      // The canvas shrinks to its content. A fixed height left half a panel
      // of emptiness under a three-step flow and the screen looked unfinished.
      canvas.style.height = Math.max(150, Math.round(height * scale) + 2) + "px";
      if (fitBtn) {
        fitBtn.hidden = (scale === 1 && fit);
        fitBtn.textContent = fit
          ? `${t("Sığdır")} · %${Math.round(scale * 100)}`
          : t("Sığdır");
        fitBtn.setAttribute("aria-pressed", String(fit));
      }

      for (const e of edges) {
        const a = byId[e.from || e.from_];
        const b = byId[e.to];
        if (!a || !b) continue;
        const isFail = (e.on || "") === "hata" || (e.on || "") === "fail";
        const fromStep = steps[e.from || e.from_];
        const live = e.to === running && fromStep && fromStep.status === "bitti";
        const passed = fromStep && fromStep.status === "bitti";

        // Leaves from the card's EDGE and enters at the edge; drawing center
        // to center ran the line under the card. Rightward flow is a
        // horizontal bezier, up/down branching exits vertically.
        const x1 = a.x + CARD_W, y1 = a.y + a.h / 2;
        const x2 = b.x,          y2 = b.y + b.h / 2;
        const sideways = b.x > a.x + CARD_W / 2;
        let d;
        if (sideways) {
          const k = Math.max(28, (x2 - x1) / 2);
          d = `M ${x1} ${y1} C ${x1 + k} ${y1}, ${x2 - k} ${y2}, ${x2} ${y2}`;
        } else {
          // Same or earlier layer: go around the bottom.
          const ax = a.x + CARD_W / 2, ay = a.y + a.h;
          const bx = b.x + CARD_W / 2, by = b.y;
          const k = Math.max(28, (by - ay) / 2);
          d = `M ${ax} ${ay} C ${ax} ${ay + k}, ${bx} ${by - k}, ${bx} ${by}`;
        }
        const pathEl = document.createElementNS("http://www.w3.org/2000/svg", "path");
        pathEl.setAttribute("d", d);
        pathEl.setAttribute("fill", "none");
        pathEl.setAttribute("class",
          "wf-edge" + (isFail ? " wf-edge-fail" : "") + (live ? " wf-edge-live" : "")
          + (passed && !live ? " wf-edge-done" : ""));
        pathEl.setAttribute("marker-end",
          `url(#${live ? "wf-ok-canli" : isFail ? "wf-ok-hata" : "wf-ok"})`);
        svg.append(pathEl);

        // Conditional branch label: the "hata" branch looked the same as a
        // normal one.
        if (e.on && e.on !== "ok") {
          const tag = document.createElementNS("http://www.w3.org/2000/svg", "text");
          tag.setAttribute("x", String((x1 + x2) / 2));
          tag.setAttribute("y", String((y1 + y2) / 2 - 6));
          tag.setAttribute("text-anchor", "middle");
          tag.setAttribute("class", "wf-edge-tag" + (isFail ? " wf-edge-tag-fail" : ""));
          tag.textContent = branchLabel(e.on);
          svg.append(tag);
        }
      }
    }
    draw();
    // The cards' real heights are only known once they enter the DOM.
    requestAnimationFrame(draw);

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

    fitBtn = el("button", "jobs-act wf-fit-btn", t("Sığdır"));
    fitBtn.type = "button";
    fitBtn.hidden = true;
    fitBtn.title = t("Akışın tamamını panele sığdır");
    fitBtn.onclick = () => { fit = !fit; draw(); };

    bar.append(add, save, fitBtn);

    wrap.append(bar, canvas);

    // The output lives HERE. Even when the automation ends up producing an
    // app, we do not send the user to the Apps panel: the screen that builds
    // the flow, runs it and reads its result is the same one. The apps list
    // is not a source — at most an example.
    if (status && (status.rapor || status.cikti)) {
      const out = el("div", "wf-out");
      out.append(el("h3", null, t("Çıktı")));
      if (status.cikti && status.cikti.yol) {
        const openBtn = el("button", "jobs-act jobs-act-primary",
          status.cikti.baslik || t("Çıktıyı aç"));
        openBtn.type = "button";
        openBtn.onclick = () => {
          // On the same screen: opens in the viewer panel.
          if (typeof Viewer !== "undefined" && Viewer.open) Viewer.open(status.cikti.yol);
        };
        out.append(openBtn);
      }
      if (status.rapor) out.append(el("pre", "wf-out-text", status.rapor));
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

    const KINDS = [
      ["custom", "Model adımı"],
      ["agent", "Model adımı (agent)"],
      ["http", "HTTP isteği"],
      ["shell", "Kabuk komutu"],
      ["skill", "Yetenek / araç"],
      ["mail_read", "Posta oku"],
    ];
    const type = el("select", "input-text wf-type");
    for (const [id, label] of KINDS) {
      const o = document.createElement("option");
      o.value = id;
      o.textContent = t(label);
      if ((node.type || "custom") === id) o.selected = true;
      type.append(o);
    }
    // Old/custom types missing from the list are added as an option.
    const known = new Set(KINDS.map((x) => x[0]));
    if (node.type && !known.has(node.type)) {
      const o = document.createElement("option");
      o.value = node.type;
      o.textContent = node.type;
      o.selected = true;
      type.append(o);
    }

    const title = el("input", "input-text");
    title.value = node.title || "";
    title.placeholder = t("Başlık");

    const fields = el("div", "wf-fields");
    function drawFields() {
      fields.replaceChildren();
      const kind = (type.value || "custom").toLowerCase();
      const cfg = node.config || {};
      if (kind === "http") {
        const url = el("input", "input-text");
        url.value = cfg.url || "";
        url.placeholder = "https://…";
        const method = el("select", "input-text");
        for (const m of ["GET", "POST", "PUT", "PATCH", "DELETE"]) {
          const o = document.createElement("option");
          o.value = m; o.textContent = m;
          if ((cfg.method || "GET").toUpperCase() === m) o.selected = true;
          method.append(o);
        }
        const body = el("textarea", "input-text");
        body.rows = 3;
        body.value = typeof cfg.body === "string" ? cfg.body
          : (cfg.body != null ? JSON.stringify(cfg.body, null, 2) : "");
        body.placeholder = t("gövde (JSON, isteğe bağlı)");
        fields.append(
          el("label", null, "URL"), url,
          el("label", null, t("Yöntem")), method,
          el("label", null, t("Gövde")), body,
        );
        fields._reader = () => {
          let parsed = body.value.trim();
          if (parsed) {
            try { parsed = JSON.parse(parsed); } catch { /* plain text */ }
          } else parsed = undefined;
          return {
            url: url.value.trim(),
            method: method.value,
            ...(parsed !== undefined ? { body: parsed } : {}),
            ...(cfg.headers ? { headers: cfg.headers } : {}),
            ...(cfg.timeout ? { timeout: cfg.timeout } : {}),
          };
        };
      } else if (kind === "shell") {
        const cmd = el("textarea", "input-text");
        cmd.rows = 3;
        cmd.value = cfg.command || cfg.cmd || "";
        cmd.placeholder = t("komut");
        fields.append(el("label", null, t("Komut")), cmd);
        fields._reader = () => ({ command: cmd.value });
      } else if (kind === "skill") {
        const skill = el("input", "input-text");
        skill.value = node.skill || cfg.skill || "";
        skill.placeholder = t("yetenek adı");
        const args = el("textarea", "input-text");
        args.rows = 3;
        args.value = cfg.args ? JSON.stringify(cfg.args, null, 2) : "";
        args.placeholder = '{"arg": "…"}';
        fields.append(
          el("label", null, t("Yetenek")), skill,
          el("label", null, t("Argümanlar (JSON)")), args,
        );
        fields._reader = () => {
          let a = {};
          try { a = args.value.trim() ? JSON.parse(args.value) : {}; } catch { a = {}; }
          return { skill: skill.value.trim(), args: a };
        };
        fields._skill = () => skill.value.trim();
      } else if (kind === "mail_read" || kind === "mail") {
        const limit = el("input", "input-text");
        limit.type = "number";
        limit.value = String(cfg.limit || 10);
        fields.append(el("label", null, t("Kaç posta")), limit);
        fields._reader = () => ({
          action: "list", limit: Math.max(1, parseInt(limit.value, 10) || 10),
        });
      } else {
        const prompt = el("textarea", "input-text");
        prompt.rows = 4;
        prompt.value = cfg.prompt || cfg.instruction || "";
        prompt.placeholder = t("Bu adımda modele ne söylensin?");
        const model = el("input", "input-text");
        model.value = cfg.model || "";
        model.placeholder = t("model (boş = varsayılan)");
        fields.append(
          el("label", null, t("Prompt")), prompt,
          el("label", null, t("Model")), model,
        );
        fields._reader = () => ({
          prompt: prompt.value,
          ...(model.value.trim() ? { model: model.value.trim() } : {}),
        });
      }
    }
    type.onchange = drawFields;
    drawFields();

    const secrets = el("input", "input-text");
    secrets.value = (node.secrets_needed || []).join(", ");
    secrets.placeholder = t("gizli alan adları (virgüllü)");

    const apply = el("button", "jobs-act", t("Uygula"));
    apply.type = "button";
    apply.onclick = () => {
      node.type = type.value.trim() || "custom";
      node.title = title.value.trim() || node.id;
      const reader = fields._reader;
      const next = reader ? reader() : {};
      if (fields._skill) node.skill = fields._skill();
      else if (next.skill) { node.skill = next.skill; delete next.skill; }
      node.config = Object.assign({}, node.config || {}, next);
      node.secrets_needed = secrets.value.split(",").map((s) => s.trim()).filter(Boolean);
      node.elle = true;
      if (onSave) onSave(wf);
    };
    box.append(
      el("label", null, t("Tür")), type,
      el("label", null, t("Başlık")), title,
      fields,
      el("label", null, t("Secrets")), secrets,
      apply,
    );
  }

  return { render };
})();
