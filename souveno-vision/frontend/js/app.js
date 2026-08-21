const App = {
  session: null,
  zonesReady: false,

  init() {
    document.querySelectorAll(".nav-btn").forEach((btn) => {
      btn.addEventListener("click", () => this.switchView(btn.dataset.view));
    });

    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("fileInput");
    dropzone.addEventListener("click", () => fileInput.click());
    dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.style.borderColor = "var(--accent)"; });
    dropzone.addEventListener("dragleave", () => { dropzone.style.borderColor = ""; });
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.style.borderColor = "";
      if (e.dataTransfer.files.length) this.handleUpload(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener("change", () => {
      if (fileInput.files.length) this.handleUpload(fileInput.files[0]);
    });

    document.getElementById("loadDefaultZonesBtn").addEventListener("click", () => this.loadDefaultZones());
    document.getElementById("openZoneBuilderBtn").addEventListener("click", () => ZoneBuilder.open(this.session.session_id));
    document.getElementById("closeZoneBuilder").addEventListener("click", () => ZoneBuilder.close());
    document.addEventListener("zones-saved", (e) => this.onZonesSaved(e.detail.zones));

    document.getElementById("startAnalysisBtn").addEventListener("click", () => this.startAnalysis());
    document.getElementById("resetDemoBtn").addEventListener("click", () => this.resetDemo());
    document.getElementById("pauseBtn").addEventListener("click", () => {
      LiveAnalysis.send("pause");
      document.getElementById("pauseBtn").classList.add("hidden");
      document.getElementById("resumeBtn").classList.remove("hidden");
    });
    document.getElementById("resumeBtn").addEventListener("click", () => {
      LiveAnalysis.send("resume");
      document.getElementById("resumeBtn").classList.add("hidden");
      document.getElementById("pauseBtn").classList.remove("hidden");
    });
    document.getElementById("triggerSpillBtn").addEventListener("click", () => LiveAnalysis.triggerSpill());

    document.getElementById("costForm").addEventListener("submit", (e) => this.handleCostEstimate(e));
    document.getElementById("rtspForm").addEventListener("submit", (e) => this.handleRtspTest(e));

    this.loadHealth();
    this.loadModelManager();
    this.loadRules();
  },

  switchView(view) {
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
    if (view === "events" && this.session) this.loadEvents();
    if (view === "insights" && this.session) this.refreshSummary();
  },

  async loadHealth() {
    try {
      const h = await API.health();
      document.getElementById("demoBadge").classList.toggle("hidden", !h.demo_mode);
      document.getElementById("deviceBadge").textContent = `Inference Device: ${h.inference_device}`;
    } catch (e) { /* non-fatal */ }
  },

  async handleUpload(file) {
    document.getElementById("uploadProgress").classList.remove("hidden");
    try {
      const session = await API.upload(file);
      this.session = session;
      document.getElementById("uploadProgress").classList.add("hidden");
      document.getElementById("sessionInfo").classList.remove("hidden");
      document.getElementById("sessionInfo").innerHTML = `
        <div><b>File:</b> ${session.filename}</div>
        <div><b>Resolution:</b> ${session.width}x${session.height}</div>
        <div><b>FPS:</b> ${session.fps.toFixed(1)}</div>
        <div><b>Duration:</b> ${fmtSeconds(session.duration_seconds)}</div>`;
      document.getElementById("zoneStep").classList.remove("hidden");
    } catch (e) {
      document.getElementById("uploadProgress").classList.add("hidden");
      alert(e.message);
    }
  },

  async loadDefaultZones() {
    const data = await API.getDefaultZones();
    await API.saveZones(this.session.session_id, data.zones);
    this.onZonesSaved(data.zones);
  },

  onZonesSaved(zones) {
    this.zonesReady = true;
    document.getElementById("zoneSummary").textContent = `${zones.length} zone(s) configured.`;
    document.getElementById("startStep").classList.remove("hidden");
  },

  startAnalysis() {
    LiveAnalysis.connect(this.session.session_id);
  },

  async resetDemo() {
    if (!this.session) return;
    await API.resetSession(this.session.session_id);
    alert("Demo data reset for this session.");
  },

  async loadEvents() {
    const data = await API.listEvents(this.session.session_id);
    const body = document.getElementById("eventsTableBody");
    body.innerHTML = data.events
      .map(
        (e) => `<tr>
        <td class="mono">${fmtSeconds(e.start_time)}</td>
        <td>${e.event_type.replaceAll("_", " ")}</td>
        <td>${e.zone_id || "-"}</td>
        <td><span class="sev-tag ${e.severity}">${e.severity}</span></td>
        <td>${e.duration_seconds ? fmtSeconds(e.duration_seconds) : "-"}</td>
        <td><a href="/api/events/${e.event_id}/clip" target="_blank" class="btn ghost">VIEW CLIP</a></td>
      </tr>`
      )
      .join("");
  },

  async refreshSummary() {
    const summary = await API.getSummary(this.session.session_id);
    if (summary) this.renderSummary(summary);
  },

  renderSummary(summary) {
    document.getElementById("summaryStatus").classList.add("hidden");
    const grid = document.getElementById("summaryStatsGrid");
    grid.classList.remove("hidden");
    const s = summary.stats;
    const tiles = [
      ["Video Analysed", s.video_duration_label],
      ["Peak People", s.peak_people_visible],
      ["Peak Queue", s.peak_queue],
      ["Avg Queue Dwell", s.average_queue_dwell_label],
      ["Abandonments", s.potential_queue_abandonments],
      ["Idle Staff Events", s.potential_idle_staff_events],
      ["Total Idle Time", s.total_potential_idle_time_label],
      ["Clearing Delays", s.table_clearing_delay_events],
      ["Pickup Delays", s.potential_pickup_delays],
      ["Spill Events", s.visible_spill_events],
      ["Footfall", s.footfall],
    ];
    grid.innerHTML = tiles.map(([label, num]) => `
      <div class="stat-tile"><div class="num">${num}</div><div class="label">${label}</div></div>
    `).join("");
    const textEl = document.getElementById("summaryText");
    textEl.classList.remove("hidden");
    textEl.textContent = summary.summary_text + (summary.generated_by === "llm" ? "" : "");
  },

  async handleCostEstimate(e) {
    e.preventDefault();
    if (!this.session) { alert("Load a video session first."); return; }
    try {
      const payload = {
        session_id: this.session.session_id,
        staff_hourly_cost: Number(document.getElementById("staffHourlyCost").value),
        average_order_value: Number(document.getElementById("averageOrderValue").value),
        estimated_monthly_spillage: Number(document.getElementById("estimatedSpillage").value),
        operating_hours_per_day: Number(document.getElementById("operatingHours").value),
        working_days_per_month: Number(document.getElementById("workingDays").value),
      };
      const result = await API.estimateCost(payload);
      const el = document.getElementById("costResult");
      el.classList.remove("hidden");
      el.innerHTML = `
        <div class="disclaimer">⚠ ${result.disclaimer}</div>
        <div class="stats-grid">
          <div class="stat-tile"><div class="num">${result.labour.potential_labour_inefficiency_hours_per_day_equivalent}</div><div class="label">Idle Hours/Day Equiv.</div></div>
          <div class="stat-tile"><div class="num">₹${result.labour.illustrative_monthly_labour_exposure}</div><div class="label">Monthly Labour Exposure</div></div>
          <div class="stat-tile"><div class="num">${result.queue_abandonment.estimated_monthly_abandonment_events}</div><div class="label">Monthly Abandonment Events</div></div>
          <div class="stat-tile"><div class="num">₹${result.queue_abandonment.illustrative_monthly_revenue_exposure}</div><div class="label">Monthly Revenue Exposure</div></div>
        </div>`;
    } catch (err) {
      alert(err.message);
    }
  },

  async loadModelManager() {
    const m = await API.modelStatus();
    document.getElementById("modelManager").innerHTML = `
      <div class="k">Person Detection</div><div class="v">${m.detection_model}</div>
      <div class="k">Tracking</div><div class="v">${m.tracker}</div>
      <div class="k">Pose</div><div class="v">${m.pose_enabled ? "Enabled" : "Disabled"}</div>
      <div class="k">Segmentation</div><div class="v">${m.segmentation_enabled ? "Enabled" : "Disabled"}</div>
      <div class="k">Spill Model</div><div class="v">${m.spill_model}</div>
      <div class="k">Inference Device</div><div class="v">${m.inference_device}</div>`;
  },

  async loadRules() {
    const r = await API.getRules();
    document.getElementById("rulesTableBody").innerHTML = r.rules
      .map(
        (rule) => `<tr>
        <td>${rule.rule_name}</td>
        <td>${rule.zone_type}</td>
        <td>${rule.threshold_seconds}</td>
        <td><span class="sev-tag ${rule.severity}">${rule.severity}</span></td>
        <td>${rule.enabled ? "✓" : "✕"}</td>
      </tr>`
      )
      .join("");
  },

  async handleRtspTest(e) {
    e.preventDefault();
    const payload = {
      camera_name: document.getElementById("cameraName").value || "Camera",
      rtsp_url: document.getElementById("rtspUrl").value,
      username: document.getElementById("rtspUser").value,
      password: document.getElementById("rtspPass").value,
    };
    const result = await API.testCamera(payload);
    const el = document.getElementById("rtspResult");
    el.classList.remove("hidden");
    if (result.connected) {
      el.innerHTML = `<div style="color:var(--accent-2)">Connected</div>
        <div>Resolution: ${result.resolution}</div><div>FPS: ${result.fps}</div>
        <div>Latency: ${result.latency_ms} ms</div>`;
    } else {
      el.innerHTML = `<div style="color:var(--critical)">Not connected</div><div>${result.error || ""}</div>`;
    }
  },
};

document.addEventListener("DOMContentLoaded", () => App.init());
