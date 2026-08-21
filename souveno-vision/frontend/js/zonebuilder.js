const ZONE_COLORS = {
  COUNTER_ZONE: "#3ba7ff",
  QUEUE_ZONE: "#f5a623",
  DINING_ZONE: "#7ed957",
  PREP_ZONE: "#d93bff",
  PICKUP_ZONE: "#ff5b5b",
  ENTRANCE_LINE: "#ffffff",
  TABLE: "#33ccaa",
};

const ZoneBuilder = {
  sessionId: null,
  canvas: null,
  ctx: null,
  image: null,
  zones: [],       // {name, zone_type, shape_type, points: [[x,y]...] normalized, color}
  currentPoints: [], // pixel-space points of shape in progress

  async open(sessionId) {
    this.sessionId = sessionId;
    document.getElementById("zoneBuilderModal").classList.remove("hidden");
    this.canvas = document.getElementById("zoneCanvas");
    this.ctx = this.canvas.getContext("2d");

    await this.populateZoneTypes();
    await this.loadFrame();
    await this.loadExisting();
    this.bindEvents();
    this.render();
  },

  close() {
    document.getElementById("zoneBuilderModal").classList.add("hidden");
  },

  async populateZoneTypes() {
    const sel = document.getElementById("zoneType");
    if (sel.dataset.populated) return;
    const { zone_types } = await API.getZoneTypes();
    sel.innerHTML = zone_types.map((t) => `<option value="${t}">${t}</option>`).join("");
    sel.dataset.populated = "1";
  },

  async loadFrame() {
    return new Promise((resolve) => {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => {
        this.image = img;
        this.canvas.width = img.naturalWidth;
        this.canvas.height = img.naturalHeight;
        resolve();
      };
      img.src = API.frameUrl(this.sessionId, 2.0) + `&_=${Date.now()}`;
    });
  },

  async loadExisting() {
    const data = await API.getSessionZones(this.sessionId);
    if (data.zones && data.zones.length) {
      this.zones = data.zones.map((z) => ({ ...z, zone_id: undefined }));
    } else {
      this.zones = [];
    }
    this.renderZoneList();
  },

  loadPreset(zones) {
    this.zones = zones.map((z) => ({ ...z }));
    this.renderZoneList();
    this.render();
  },

  bindEvents() {
    if (this._bound) return;
    this._bound = true;
    this.canvas.addEventListener("click", (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const scaleX = this.canvas.width / rect.width;
      const scaleY = this.canvas.height / rect.height;
      const x = (e.clientX - rect.left) * scaleX;
      const y = (e.clientY - rect.top) * scaleY;
      this.currentPoints.push([x, y]);
      this.render();
    });
    document.getElementById("finishShapeBtn").addEventListener("click", () => this.finishShape());
    document.getElementById("undoPointBtn").addEventListener("click", () => {
      this.currentPoints.pop();
      this.render();
    });
    document.getElementById("clearZonesBtn").addEventListener("click", () => {
      if (confirm("Remove all zones?")) {
        this.zones = [];
        this.renderZoneList();
        this.render();
      }
    });
    document.getElementById("saveZonesBtn").addEventListener("click", () => this.save());
    document.addEventListener("keydown", (e) => {
      if (!document.getElementById("zoneBuilderModal").classList.contains("hidden") && e.key === "Enter") {
        this.finishShape();
      }
    });
  },

  finishShape() {
    const shapeType = document.getElementById("shapeType").value;
    const zoneType = document.getElementById("zoneType").value;
    const name = document.getElementById("zoneName").value.trim() || zoneType;

    if (shapeType === "line" && this.currentPoints.length !== 2) {
      alert("A line needs exactly 2 points.");
      return;
    }
    if (shapeType === "polygon" && this.currentPoints.length < 3) {
      alert("A polygon needs at least 3 points.");
      return;
    }

    const normalized = this.currentPoints.map(([x, y]) => [x / this.canvas.width, y / this.canvas.height]);
    this.zones.push({
      name, zone_type: zoneType, shape_type: shapeType, points: normalized,
      color: ZONE_COLORS[zoneType] || "#3ba7ff",
    });
    this.currentPoints = [];
    document.getElementById("zoneName").value = "";
    this.renderZoneList();
    this.render();
  },

  deleteZone(idx) {
    this.zones.splice(idx, 1);
    this.renderZoneList();
    this.render();
  },

  renderZoneList() {
    const el = document.getElementById("zoneList");
    if (!this.zones.length) {
      el.innerHTML = `<div class="muted small">No zones yet</div>`;
      return;
    }
    el.innerHTML = this.zones
      .map(
        (z, i) => `
      <div class="zone-list-item">
        <span><span class="swatch" style="background:${z.color}"></span>${z.name} <span class="muted">(${z.zone_type})</span></span>
        <button class="btn ghost" onclick="ZoneBuilder.deleteZone(${i})">✕</button>
      </div>`
      )
      .join("");
  },

  render() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    if (this.image) ctx.drawImage(this.image, 0, 0, this.canvas.width, this.canvas.height);

    for (const z of this.zones) {
      const pts = z.points.map(([x, y]) => [x * this.canvas.width, y * this.canvas.height]);
      ctx.strokeStyle = z.color;
      ctx.fillStyle = z.color + "33";
      ctx.lineWidth = 2;
      ctx.beginPath();
      pts.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
      if (z.shape_type === "polygon") {
        ctx.closePath();
        ctx.fill();
      }
      ctx.stroke();
      ctx.fillStyle = "#fff";
      ctx.font = "16px sans-serif";
      ctx.fillText(z.name, pts[0][0] + 4, pts[0][1] - 6);
    }

    if (this.currentPoints.length) {
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      this.currentPoints.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
      ctx.stroke();
      this.currentPoints.forEach(([x, y]) => {
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fillStyle = "#ffffff";
        ctx.fill();
      });
    }
  },

  async save() {
    if (!this.zones.length) {
      alert("Draw at least one zone first.");
      return;
    }
    const payload = this.zones.map(({ zone_id, ...z }) => z);
    await API.saveZones(this.sessionId, payload);
    this.close();
    document.dispatchEvent(new CustomEvent("zones-saved", { detail: { zones: this.zones } }));
  },
};
