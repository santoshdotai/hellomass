const LiveAnalysis = {
  ws: null,
  sessionId: null,
  zones: [],
  activeAlerts: new Map(), // event_id -> alert dict
  eventLog: [],

  connect(sessionId) {
    this.sessionId = sessionId;
    this.activeAlerts.clear();
    this.eventLog = [];
    document.getElementById("eventsFeed").innerHTML = "";
    document.getElementById("alertsList").innerHTML = `<div class="muted small">No active alerts</div>`;

    const proto = location.protocol === "https:" ? "wss" : "ws";
    this.ws = new WebSocket(`${proto}://${location.host}/ws/analysis/${sessionId}`);

    this.ws.onopen = () => {
      document.getElementById("liveLayout").classList.remove("hidden");
      document.getElementById("setupPanel").classList.add("hidden");
    };

    this.ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.type === "started") this.onStarted(msg);
      else if (msg.type === "frame") this.onFrame(msg);
      else if (msg.type === "completed") this.onCompleted();
      else if (msg.type === "error") this.onError(msg);
    };

    this.ws.onclose = () => {};
    this.ws.onerror = () => this.showOverlay("Connection error — check the server logs.");
  },

  onStarted(msg) {
    this.zones = msg.zones || [];
    document.getElementById("demoBadge").classList.toggle("hidden", !msg.demo_mode);
    this.showOverlay(null);
  },

  onFrame(msg) {
    document.getElementById("videoFrame").src = msg.image;
    const payload = msg.payload;
    document.getElementById("videoTimeLabel").textContent = payload.video_time_label;
    document.getElementById("deviceBadge").textContent = `Inference Device: ${payload.device}`;
    this.renderLiveStatus(payload.metrics.live_status);
    this.renderBusinessMetrics(payload.metrics.business_metrics);
    (payload.new_events || []).forEach((ev) => this.handleEvent(ev));
  },

  handleEvent(ev) {
    this.eventLog.unshift(ev);
    this.eventLog = this.eventLog.slice(0, 60);
    this.renderEventsFeed();

    if (ev.status === "open" && (ev.severity === "warning" || ev.severity === "critical")) {
      this.activeAlerts.set(ev.event_id, ev);
    } else if (ev.status === "closed") {
      this.activeAlerts.delete(ev.event_id);
    }
    this.renderAlerts();
  },

  renderLiveStatus(status) {
    const rows = [
      ["People Visible", status.people_visible],
      ["Active Tracks", status.active_tracks],
    ];
    for (const [zoneType, count] of Object.entries(status.zone_counts || {})) {
      rows.push([this.prettyZoneType(zoneType), count]);
    }
    document.getElementById("liveStatus").innerHTML = rows
      .map(([k, v]) => `<div class="k">${k}</div><div class="v">${v}</div>`)
      .join("");
  },

  renderBusinessMetrics(m) {
    const rows = [
      ["Queue Length", m.queue_length],
      ["Peak Queue", m.peak_queue],
      ["Longest Wait", fmtSeconds(m.longest_wait_seconds)],
      ["Average Dwell", fmtSeconds(m.average_dwell_seconds)],
      ["Tables Occupied", m.tables_occupied],
      ["Tables Available", m.tables_available],
      ["Prep Staff Count", m.prep_staff_count],
      ["Potential Idle Staff", m.potential_idle_staff_now],
    ];
    document.getElementById("businessMetrics").innerHTML = rows
      .map(([k, v]) => `<div class="k">${k}</div><div class="v">${v}</div>`)
      .join("");
  },

  renderAlerts() {
    const el = document.getElementById("alertsList");
    const alerts = Array.from(this.activeAlerts.values());
    if (!alerts.length) {
      el.innerHTML = `<div class="muted small">No active alerts</div>`;
      return;
    }
    el.innerHTML = alerts
      .map(
        (a) => `
      <div class="alert-card ${a.severity}">
        <div class="alert-title">${a.label}</div>
        <div class="muted small">Started ${fmtSeconds(a.start_time)}</div>
      </div>`
      )
      .join("");
  },

  renderEventsFeed() {
    const el = document.getElementById("eventsFeed");
    el.innerHTML = this.eventLog
      .map(
        (ev) => `<div class="event-row ${ev.severity}"><span class="time mono">${fmtSeconds(
          ev.status === "closed" ? ev.end_time : ev.start_time
        )}</span><span>${ev.label}</span></div>`
      )
      .join("");
  },

  prettyZoneType(t) {
    return t.replace("_ZONE", "").replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
  },

  showOverlay(text) {
    const el = document.getElementById("videoOverlayMsg");
    if (!text) {
      el.classList.add("hidden");
      return;
    }
    el.textContent = text;
    el.classList.remove("hidden");
  },

  send(action, data = {}) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action, ...data }));
    }
  },

  triggerSpill() {
    const pickup = this.zones.find((z) => z.zone_type === "PICKUP_ZONE") ||
                   this.zones.find((z) => z.zone_type === "COUNTER_ZONE");
    const zoneId = pickup ? pickup.name : "Pickup";
    this.send("trigger_spill", { zone_id: zoneId, confidence: 0.55 });
  },

  async onCompleted() {
    this.showOverlay("Analysis complete — see the Insights tab for the SOUVENO AI summary.");
    const summary = await API.getSummary(this.sessionId);
    if (summary) App.renderSummary(summary);
    App.loadEvents();
  },

  onError(msg) {
    this.showOverlay(`Error: ${msg.message}`);
  },
};

function fmtSeconds(totalSeconds) {
  if (totalSeconds === null || totalSeconds === undefined) return "—";
  const s = Math.max(0, Math.round(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return [h, m, sec].map((v) => String(v).padStart(2, "0")).join(":");
}
