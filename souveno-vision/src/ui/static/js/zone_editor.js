/* Zone & virtual-line editor on a canvas over a live snapshot. Normalised coordinates (0..1). */
const ZoneEditor = {
  canvas: null, ctx: null, img: null, zones: [], current: [], drag: null, sourceId: null,
  COLORS: { restricted: "#ff4d4f", roi: "#40a9ff", occupancy: "#36cfc9", line: "#ffd666" },

  init() {
    this.canvas = document.getElementById("zeCanvas");
    this.ctx = this.canvas.getContext("2d");
    this.canvas.addEventListener("mousedown", (e) => this.onDown(e));
    this.canvas.addEventListener("mousemove", (e) => this.onMove(e));
    window.addEventListener("mouseup", () => { if (this.drag) { this.drag = null; this.render(); } });
    this.canvas.addEventListener("contextmenu", (e) => { e.preventDefault(); this.onRightClick(e); });
    this.canvas.addEventListener("dblclick", () => this.finish());
    document.getElementById("zeFinish").addEventListener("click", () => this.finish());
    document.getElementById("zeUndo").addEventListener("click", () => { this.current.pop(); this.render(); });
    document.getElementById("zeReset").addEventListener("click", () => { if (confirm("Remove all zones for this camera?")) { this.zones = []; this.current = []; this.renderList(); this.render(); } });
    document.getElementById("zeRefresh").addEventListener("click", () => this.loadSnapshot());
    document.getElementById("zeSave").addEventListener("click", () => this.save());
    document.getElementById("zePresetDemo").addEventListener("click", async () => {
      const d = await API.zones(); this.zones = d.presets.demo_layout.map(z => ({ ...z })); this.renderList(); this.render();
    });
  },

  async load(sourceId) {
    this.sourceId = sourceId || null;
    await this.loadSnapshot();
    try {
      const d = await API.zones(this.sourceId);
      this.sourceId = d.source_id || this.sourceId;
      this.zones = (d.zones || []).map(z => ({ ...z }));
    } catch (e) { this.zones = []; }
    this.current = [];
    this.renderList(); this.render();
  },

  loadSnapshot() {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => { this.img = img; this.canvas.width = img.naturalWidth; this.canvas.height = img.naturalHeight; this.render(); resolve(); };
      img.onerror = () => resolve();
      img.src = `/api/vi/snapshot.jpg?raw=1&_=${Date.now()}`;
    });
  },

  pos(e) {
    const r = this.canvas.getBoundingClientRect();
    return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height];
  },
  hit(p) {
    const tol = 0.012;
    for (let zi = 0; zi < this.zones.length; zi++) {
      const z = this.zones[zi];
      for (let pi = 0; pi < z.points.length; pi++) {
        const q = z.points[pi];
        if (Math.abs(q[0] - p[0]) < tol && Math.abs(q[1] - p[1]) < tol * (this.canvas.width / this.canvas.height)) return { zi, pi };
      }
    }
    return null;
  },
  onDown(e) {
    if (e.button !== 0) return;
    const p = this.pos(e);
    const h = this.hit(p);
    if (h) { this.drag = h; return; }
    const kind = document.getElementById("zeKind").value;
    if (kind === "line" && this.current.length >= 2) return;
    this.current.push([+p[0].toFixed(4), +p[1].toFixed(4)]);
    if (kind === "line" && this.current.length === 2) this.finish();
    this.render();
  },
  onMove(e) {
    if (!this.drag) return;
    const p = this.pos(e);
    this.zones[this.drag.zi].points[this.drag.pi] = [+Math.min(1, Math.max(0, p[0])).toFixed(4), +Math.min(1, Math.max(0, p[1])).toFixed(4)];
    this.render();
  },
  onRightClick(e) {
    const h = this.hit(this.pos(e));
    if (!h) { this.current.pop(); this.render(); return; }
    const z = this.zones[h.zi];
    const min = z.kind === "line" ? 2 : 3;
    if (z.points.length <= min) { App.toast(`A ${z.kind === "line" ? "line" : "zone"} needs at least ${min} points — delete the zone instead.`, "error"); return; }
    z.points.splice(h.pi, 1); this.render();
  },
  finish() {
    const kind = document.getElementById("zeKind").value;
    const need = kind === "line" ? 2 : 3;
    if (this.current.length < need) { App.toast(`Add at least ${need} points first.`, "error"); return; }
    if (kind === "line" && this.current.length !== 2) { App.toast("A line needs exactly 2 points.", "error"); return; }
    const nameInput = document.getElementById("zeName");
    const name = nameInput.value.trim() || `${kind.charAt(0).toUpperCase() + kind.slice(1)} ${this.zones.length + 1}`;
    const z = { name, kind, points: this.current, color: this.COLORS[kind], enabled: true };
    if (kind === "restricted") z.dwell_threshold_seconds = null;
    if (kind === "occupancy") z.occupancy_limit = 3;
    if (kind === "line") { z.direction_flipped = false; z.in_label = "Entry"; z.out_label = "Exit"; }
    this.zones.push(z); this.current = []; nameInput.value = "";
    this.renderList(); this.render();
  },
  remove(i) { this.zones.splice(i, 1); this.renderList(); this.render(); },
  update(i, key, value) { this.zones[i][key] = value; this.render(); },

  renderList() {
    const el = document.getElementById("zeList");
    if (!this.zones.length) { el.innerHTML = `<div class="muted small">No zones yet — draw one on the picture.</div>`; return; }
    el.innerHTML = this.zones.map((z, i) => {
      let extra = "";
      if (z.kind === "line") extra = `<label class="check"><input type="checkbox" ${z.direction_flipped ? "checked" : ""} onchange="ZoneEditor.update(${i},'direction_flipped',this.checked)"> flip direction</label>`;
      else if (z.kind === "occupancy") extra = `limit <input type="number" min="1" value="${z.occupancy_limit ?? ""}" onchange="ZoneEditor.update(${i},'occupancy_limit',this.value?+this.value:null)">`;
      else extra = `dwell s <input type="number" min="1" placeholder="default" value="${z.dwell_threshold_seconds ?? ""}" onchange="ZoneEditor.update(${i},'dwell_threshold_seconds',this.value?+this.value:null)">`;
      return `<div class="ze-item"><div class="row"><span class="swatch" style="background:${z.color}"></span><b>${App.esc(z.name)}</b> <span class="muted">${z.kind}</span><span class="spacer"></span><button class="btn sm ghost" onclick="ZoneEditor.remove(${i})">✕</button></div>
        <div class="row">${extra}<label class="check"><input type="checkbox" ${z.enabled !== false ? "checked" : ""} onchange="ZoneEditor.update(${i},'enabled',this.checked)"> enabled</label></div></div>`;
    }).join("");
  },

  render() {
    const c = this.ctx, W = this.canvas.width, H = this.canvas.height;
    c.clearRect(0, 0, W, H);
    if (this.img) c.drawImage(this.img, 0, 0, W, H); else { c.fillStyle = "#111"; c.fillRect(0, 0, W, H); }
    const drawPts = (pts, color, closed) => {
      c.strokeStyle = color; c.lineWidth = 3; c.beginPath();
      pts.forEach(([x, y], i) => i ? c.lineTo(x * W, y * H) : c.moveTo(x * W, y * H));
      if (closed) { c.closePath(); c.fillStyle = color + "33"; c.fill(); }
      c.stroke();
      pts.forEach(([x, y]) => { c.beginPath(); c.arc(x * W, y * H, 6, 0, Math.PI * 2); c.fillStyle = "#fff"; c.fill(); c.strokeStyle = color; c.lineWidth = 2; c.stroke(); });
    };
    for (const z of this.zones) {
      const col = z.color || this.COLORS[z.kind] || "#40a9ff";
      drawPts(z.points, col, z.kind !== "line");
      const [x, y] = z.points[0];
      c.font = "bold 16px sans-serif"; c.fillStyle = col; c.fillText(z.name, x * W + 8, y * H - 8);
      if (z.kind === "line" && z.points.length === 2) {
        const [a, b] = z.points; const mx = (a[0] + b[0]) / 2 * W, my = (a[1] + b[1]) / 2 * H;
        const dx = (b[0] - a[0]) * W, dy = (b[1] - a[1]) * H, L = Math.hypot(dx, dy) || 1;
        const s = z.direction_flipped ? -1 : 1; const nx = -dy / L * s, ny = dx / L * s;
        c.strokeStyle = col; c.lineWidth = 3; c.beginPath(); c.moveTo(mx - nx * 30, my - ny * 30); c.lineTo(mx + nx * 30, my + ny * 30); c.stroke();
        c.beginPath(); c.arc(mx + nx * 30, my + ny * 30, 6, 0, Math.PI * 2); c.fillStyle = col; c.fill();
        c.fillStyle = col; c.font = "13px sans-serif"; c.fillText((z.in_label || "Entry") + " →", mx + nx * 38, my + ny * 38);
      }
    }
    if (this.current.length) drawPts(this.current, "#ffffff", false);
  },

  async save() {
    const problems = document.getElementById("zeProblems");
    problems.hidden = true;
    try {
      const d = await API.saveZones(this.sourceId, this.zones);
      this.zones = d.zones; this.sourceId = d.source_id; this.renderList(); this.render();
      App.toast(`Saved ${d.zones.length} zone(s) for ${d.source_id}`, "ok");
    } catch (e) {
      const p = e.detail && e.detail.problems;
      problems.hidden = false;
      problems.innerHTML = p ? Object.entries(p).map(([n, list]) => `<b>${App.esc(n)}</b>: ${list.join("; ")}`).join("<br>") : App.esc(e.message);
    }
  },
};
