/* Souveno Vision Intelligence dashboard controller. */
const App = {
  state: null, ws: null, pollTimer: null, lastEventTs: "", eventsSeen: new Set(), currentSourceId: null, settings: null, rules: [],

  esc(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); },
  toast(msg, kind = "info", ms = 4500) {
    const el = document.createElement("div"); el.className = `toast ${kind}`; el.textContent = msg;
    document.getElementById("toasts").appendChild(el); setTimeout(() => el.remove(), ms);
  },
  modal(title, html) { document.getElementById("modalTitle").textContent = title; document.getElementById("modalBody").innerHTML = html; document.getElementById("modal").hidden = false; },

  init() {
    window.addEventListener("hashchange", () => this.route());
    this.route();
    document.querySelectorAll("[data-demo]").forEach((b) => b.addEventListener("click", () => this.demo(b.dataset.demo)));
    document.getElementById("btnPause").addEventListener("click", () => this.togglePause());
    document.getElementById("btnRestart").addEventListener("click", () => this.run(API.restartSource(), "Source restarting"));
    document.getElementById("btnStop").addEventListener("click", () => this.run(API.stopSource(), "Source stopped"));
    document.getElementById("btnFullscreenDash").addEventListener("click", () => this.fullscreen(document.querySelector("#view-dashboard .video-panel")));
    document.getElementById("btnFullscreenDemo").addEventListener("click", () => this.fullscreenDemo());
    document.getElementById("btnDemoRtsp").addEventListener("click", () => { document.getElementById("rtspModal").hidden = false; });
    document.getElementById("rtspModalClose").addEventListener("click", () => { document.getElementById("rtspModal").hidden = true; });
    document.getElementById("modalClose").addEventListener("click", () => { document.getElementById("modal").hidden = true; });
    document.getElementById("rtspQuickForm").addEventListener("submit", (e) => { e.preventDefault(); this.startFromForm(e.target, "rtsp"); document.getElementById("rtspModal").hidden = true; });
    document.getElementById("sourceForm").addEventListener("submit", (e) => { e.preventDefault(); this.startFromForm(e.target, this.sourceTab); });
    document.querySelectorAll("#sourceTabs button").forEach((b) => b.addEventListener("click", () => this.setSourceTab(b.dataset.src)));
    document.getElementById("btnProbeWebcams").addEventListener("click", () => this.probeWebcams());
    document.getElementById("uploadInput").addEventListener("change", (e) => this.upload(e.target.files[0]));
    document.getElementById("detectForm").addEventListener("submit", (e) => { e.preventDefault(); this.saveSettings(); });
    document.getElementById("detectForm").confidence.addEventListener("input", (e) => { document.getElementById("confVal").textContent = e.target.value; });
    document.getElementById("btnSaveRules").addEventListener("click", () => this.saveRules());
    document.getElementById("webhookForm").addEventListener("submit", (e) => { e.preventDefault(); this.saveWebhook(); });
    document.getElementById("btnWebhookTest").addEventListener("click", () => this.run(API.webhookTest().then((r) => this.toast(r.ok ? `Webhook OK (HTTP ${r.http_status})` : `Webhook failed: ${r.error}`, r.ok ? "ok" : "error"))));
    document.getElementById("eventFilters").addEventListener("submit", (e) => { e.preventDefault(); this.loadEvents(); });
    document.getElementById("btnClearFilters").addEventListener("click", () => { document.getElementById("eventFilters").reset(); this.loadEvents(); });
    document.getElementById("auditForm").addEventListener("submit", (e) => { e.preventDefault(); this.runAudit(e.target); });
    document.getElementById("btnAuditFromSettings").addEventListener("click", () => { location.hash = "#audit"; });
    document.getElementById("btnHealthRefresh").addEventListener("click", () => this.loadHealth());
    this.sourceTab = "webcam";
    ZoneEditor.init();
    this.connectLive();
    this.loadSourceOptions();
    document.getElementById("demoVideo").src = "/api/vi/stream.mjpg?fps=12";
  },

  route() {
    const view = (location.hash || "#dashboard").slice(1);
    document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
    if (view === "events") this.loadEvents();
    if (view === "settings") { this.loadSettings(); this.loadRules(); this.loadSourceOptions(); ZoneEditor.load(this.currentSourceId); }
    if (view === "health") this.loadHealth();
    if (view === "audit") this.loadAudits();
  },

  async run(promise, okMsg) {
    try { const r = await promise; if (okMsg) this.toast(okMsg, "ok"); return r; }
    catch (e) { this.toast(e.message, "error", 8000); return null; }
  },

  // ---------------- live state ----------------
  connectLive() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    try {
      this.ws = new WebSocket(`${proto}://${location.host}/ws/vi/live`);
      this.ws.onmessage = (m) => this.onState(JSON.parse(m.data));
      this.ws.onclose = () => { this.ws = null; this.startPolling(); setTimeout(() => this.connectLive(), 5000); };
      this.ws.onerror = () => {};
      this.ws.onopen = () => this.stopPolling();
    } catch (e) { this.startPolling(); }
  },
  startPolling() { if (!this.pollTimer) this.pollTimer = setInterval(async () => { try { this.onState(await API.state()); } catch (e) {} }, 1000); },
  stopPolling() { if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; } },

  onState(st) {
    this.state = st;
    const src = st.source || {};
    const status = src.status || "idle";
    document.getElementById("pillSource").textContent = src.name ? `${src.name} · ${src.kind}${src.stream_profile ? " (" + src.stream_profile + ")" : ""}` : "No source";
    document.getElementById("pillLive").innerHTML = `<span class="dot ${status}"></span>${status.charAt(0).toUpperCase() + status.slice(1)}`;
    const ai = st.ai || {};
    document.getElementById("pillAI").textContent = st.running ? `AI: ${ai.backend}${ai.fallback ? " (fallback)" : ""}${st.paused ? " · paused" : ""}` : "AI: idle";
    document.getElementById("pillDevice").textContent = ai.device || "CPU";
    document.getElementById("pillFps").textContent = `${(ai.inference_fps || 0).toFixed(1)} fps`;
    document.getElementById("pillClock").textContent = (st.time || "").split(" ")[1] || "";
    document.getElementById("btnPause").textContent = st.paused ? "▶ Resume" : "⏸ Pause";
    const errPanel = document.getElementById("sourceErrorPanel");
    if (src.last_error && status !== "live") { errPanel.hidden = false; errPanel.innerHTML = `<b>Source problem:</b> ${this.esc(src.last_error)}<br><span class="muted small">The dashboard keeps running; reconnection is automatic for cameras.</span>`; }
    else errPanel.hidden = true;
    if (src.id && src.id !== this.currentSourceId) { this.currentSourceId = src.id; if (location.hash === "#settings") ZoneEditor.load(src.id); }
    this.renderKpis(st);
    const c = st.counts || {};
    document.getElementById("bigPeople").textContent = c.people ?? 0;
    document.getElementById("bigEntries").textContent = c.entries ?? 0;
    document.getElementById("bigExits").textContent = c.exits ?? 0;
    document.getElementById("bigAlerts").textContent = (st.stats && st.stats.active_alerts) ?? c.active_alerts ?? 0;
    (st.new_events || []).forEach((e) => { if (!this.eventsSeen.has(e.event_id + e.status)) { this.eventsSeen.add(e.event_id + e.status); if (e.severity !== "low" && e.status === "new") this.toast(`${e.severity.toUpperCase()}: ${e.title}`, e.severity === "critical" ? "error" : "info"); } });
    this.renderEventCards(st.recent_events || []);
  },

  renderKpis(st) {
    const c = st.counts || {}, s = st.stats || {};
    const health = st.source && st.source.status;
    const tiles = [
      ["Current occupancy", c.occupancy ?? 0, ""], ["Entries", c.entries ?? 0, ""], ["Exits", c.exits ?? 0, ""],
      ["Active alerts", s.active_alerts ?? 0, (s.active_alerts || 0) > 0 ? "alert" : "ok"],
      ["Restricted-zone violations today", s.restricted_violations_today ?? 0, (s.restricted_violations_today || 0) > 0 ? "warn" : ""],
      ["Average dwell", `${(c.average_dwell_seconds || 0).toFixed(0)}s`, ""],
      ["Camera health", health ? health.toUpperCase() : "IDLE", health === "live" ? "ok" : (health ? "alert" : "")],
      ["Total events today", s.total_today ?? 0, ""],
    ];
    document.getElementById("kpiGrid").innerHTML = tiles.map(([l, n, k]) => `<div class="kpi ${k}"><div class="num">${n}</div><div class="lbl">${l}</div></div>`).join("");
  },

  eventCard(e) {
    const thumb = e.snapshot_url ? `<img class="thumb" src="${e.snapshot_url}" onclick="App.showEvent('${e.event_id}')" alt="snapshot">` : `<div class="thumb none">no snapshot</div>`;
    const actions = e.status === "new" ? `<button class="btn sm" onclick="App.act('${e.event_id}','ack')">Acknowledge</button><button class="btn sm ghost" onclick="App.act('${e.event_id}','dismiss')">Dismiss</button>`
      : e.status === "acknowledged" ? `<button class="btn sm ok" onclick="App.act('${e.event_id}','resolve')">Resolve</button><button class="btn sm ghost" onclick="App.act('${e.event_id}','dismiss')">Dismiss</button>` : `<span class="st">${e.status}</span>`;
    return `<div class="ecard ${e.severity} ${e.status}">${thumb}<div><div class="title"><span class="sev ${e.severity}">${e.severity}</span> ${this.esc(e.title)}</div>
      <div class="meta">${e.time_local} · ${this.esc(e.source_name)} · ${this.esc(e.metadata && e.metadata.rule_name || e.event_type)}${e.clip_url ? ` · <a class="link" href="${e.clip_url}" target="_blank">clip</a>` : ""}</div><div class="actions">${actions}</div></div></div>`;
  },
  renderEventCards(events) {
    const el = document.getElementById("eventCards");
    el.innerHTML = events.length ? events.slice(0, 25).map((e) => this.eventCard(e)).join("") : `<div class="muted small">No events yet.</div>`;
    document.getElementById("demoFeed").innerHTML = events.slice(0, 20).map((e) => `<div class="item ${e.severity}"><div class="t">${e.time_local.split(" ")[1]} · ${this.esc(e.source_name)}</div>${this.esc(e.title)}</div>`).join("");
  },
  async act(id, action) { const r = await this.run(API.eventAction(id, action), `Event ${action === "ack" ? "acknowledged" : action + "d"}`); if (r && location.hash === "#events") this.loadEvents(); },
  async showEvent(id) {
    const e = await this.run(API.event(id)); if (!e) return;
    const audit = (e.audit || []).map((a) => `<li>${a.created_at} — ${this.esc(a.action)} by ${this.esc(a.actor)}${a.note ? ": " + this.esc(a.note) : ""}</li>`).join("") || "<li class='muted'>none yet</li>";
    this.modal(e.title, `${e.snapshot_url ? `<img src="${e.snapshot_url}">` : ""}${e.clip_url ? `<video src="${e.clip_url}" controls style="margin-top:8px"></video>` : ""}
      <div class="kv" style="margin-top:10px"><span class="k">Event ID</span><span class="mono">${e.event_id}</span><span class="k">Time</span><span>${e.time_local}</span><span class="k">Camera</span><span>${this.esc(e.source_name)} (${this.esc(e.source_id)})</span>
      <span class="k">Zone</span><span>${this.esc(e.zone_name || "-")}</span><span class="k">Track</span><span>${e.track_id != null ? "Person " + e.track_id + " (temporary, camera-local)" : "-"}</span><span class="k">Severity</span><span class="sev ${e.severity}">${e.severity}</span>
      <span class="k">Status</span><span>${e.status}${e.acknowledged_by ? " by " + this.esc(e.acknowledged_by) + " at " + e.acknowledged_at : ""}</span><span class="k">Confidence</span><span>${e.confidence != null ? (e.confidence * 100).toFixed(0) + "%" : "-"}</span>
      <span class="k">Metadata</span><span class="mono small">${this.esc(JSON.stringify(e.metadata))}</span></div><h4>Audit trail</h4><ul>${audit}</ul>
      <div class="row"><input id="noteInput" placeholder="note (optional)"><button class="btn sm" onclick="App.actNote('${e.event_id}','ack')">Acknowledge</button><button class="btn sm ok" onclick="App.actNote('${e.event_id}','resolve')">Resolve</button><button class="btn sm ghost" onclick="App.actNote('${e.event_id}','dismiss')">Dismiss</button></div>`);
  },
  async actNote(id, action) { const note = document.getElementById("noteInput").value; await this.run(API.eventAction(id, action, note), "Updated"); document.getElementById("modal").hidden = true; if (location.hash === "#events") this.loadEvents(); },

  // ---------------- demo / source ----------------
  async demo(action) {
    const r = await this.run(API.demo(action));
    if (!r) return;
    if (r.note) this.toast(r.note, "info", 8000);
    if (r.message) this.toast(r.message, "ok", 10000);
    if (action === "enable-restricted") this.toast(`Restricted zone, entry line and work area applied (${r.zones.length} zones). Adjust them in Settings → Zone editor.`, "ok", 8000);
    if (action === "reset-counts") this.toast("Counts and track IDs reset", "ok");
    if (["webcam", "recorded", "synthetic"].includes(action)) this.toast("Source starting…", "ok");
  },
  async togglePause() { const p = !(this.state && this.state.paused); await this.run(API.pause(p), p ? "Paused" : "Resumed"); },
  fullscreen(el) { if (document.fullscreenElement) document.exitFullscreen(); else (el || document.documentElement).requestFullscreen().catch(() => {}); },
  fullscreenDemo() { document.body.classList.toggle("fullscreen-demo"); this.fullscreen(document.documentElement); },
  setSourceTab(t) { this.sourceTab = t; document.querySelectorAll("#sourceTabs button").forEach((b) => b.classList.toggle("active", b.dataset.src === t)); document.querySelectorAll("#sourceForm [data-pane]").forEach((p) => { p.hidden = p.dataset.pane !== t; }); },
  formData(form) { const o = {}; new FormData(form).forEach((v, k) => { o[k] = v; }); form.querySelectorAll("input[type=checkbox]").forEach((c) => { o[c.name] = c.checked; }); return o; },
  async startFromForm(form, type) {
    const d = this.formData(form);
    const spec = { type, name: d.name || undefined };
    if (type === "webcam") spec.index = +(d.index || 0);
    if (type === "file") { if (!d.path) { this.toast("Choose or upload a video file first", "error"); return; } spec.path = d.path; spec.loop = !!d.loop; }
    if (type === "rtsp") { spec.url = d.url || undefined; spec.username = d.username || undefined; spec.password = d.password || undefined; spec.stream_profile = d.stream_profile || "main"; spec.transport = d.transport || "tcp"; }
    const r = await this.run(API.startSource(spec), "Source started");
    if (r) { form.querySelectorAll("input[type=password]").forEach((i) => { i.value = ""; }); location.hash = "#dashboard"; }
  },
  async loadSourceOptions() {
    const d = await this.run(API.source()); if (!d) return;
    const sel = document.querySelector("#sourceForm select[name=path]");
    sel.innerHTML = `<option value="">— choose —</option>` + d.assets.map((a) => `<option value="${this.esc(a.path)}">${this.esc(a.name)} (${a.size_mb} MB, ${a.folder})</option>`).join("");
    document.getElementById("rtspEnvNote").textContent = d.rtsp_env_configured ? "SOUVENO_RTSP_URL is set in .env — leave the URL empty to use it. Credentials stay in memory and are masked in every log." : "Credentials stay in memory and are masked in every log. You can also put SOUVENO_RTSP_URL / USERNAME / PASSWORD in .env.";
  },
  async probeWebcams() { const el = document.getElementById("webcamProbe"); el.textContent = "probing…"; const d = await this.run(API.webcams()); el.textContent = d ? (d.webcams.length ? d.webcams.map((w) => `index ${w.index}: ${w.available ? "OK " + w.resolution : "opens but no image"}`).join(" · ") : "No webcam found — check the OS camera privacy setting or close other apps using the camera.") : ""; },
  async upload(file) { if (!file) return; const el = document.getElementById("uploadStatus"); el.textContent = `Uploading ${file.name}…`; const r = await this.run(API.upload(file)); if (r) { el.textContent = `Uploaded ${r.name}`; await this.loadSourceOptions(); document.querySelector("#sourceForm select[name=path]").value = r.path; } else el.textContent = ""; },

  // ---------------- settings ----------------
  async loadSettings() {
    const d = await this.run(API.settings()); if (!d) return;
    this.settings = d.settings; const s = d.settings, f = document.getElementById("detectForm");
    f.confidence.value = s.confidence; document.getElementById("confVal").textContent = s.confidence; f.analytics_fps.value = s.analytics_fps; f.device.value = s.device;
    f.trail_enabled.checked = !!s.trail_enabled; f.dwell_threshold_seconds.value = s.dwell_threshold_seconds; f.occupancy_threshold.value = s.occupancy_threshold;
    f.bh_start.value = s.business_hours.start; f.bh_end.value = s.business_hours.end; f.retention_days.value = s.retention_days; f.clip_enabled.checked = !!s.clip_enabled;
    const names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    document.getElementById("bhDays").innerHTML = names.map((n, i) => `<label class="check"><input type="checkbox" name="bh_day" value="${i}" ${s.business_hours.days.includes(i) ? "checked" : ""}>${n}</label>`).join("");
    const w = document.getElementById("webhookForm"); w.enabled.checked = !!s.webhook.enabled; w.url.value = s.webhook.url || ""; w.timeout_seconds.value = s.webhook.timeout_seconds; w.max_retries.value = s.webhook.max_retries; w.backoff_seconds.value = s.webhook.backoff_seconds;
    const m = d.config.model; document.getElementById("aiInfo").textContent = `Model: ${m.weights} (backend ${s.model_backend}, image size ${s.image_size}) · tracking ${d.config.tracking.backend}, timeout ${d.config.tracking.track_timeout_seconds}s · analysis width ${d.config.processing.analysis_max_width}px`;
  },
  async saveSettings() {
    const f = document.getElementById("detectForm");
    const days = [...f.querySelectorAll("input[name=bh_day]:checked")].map((c) => +c.value);
    const payload = { confidence: +f.confidence.value, analytics_fps: +f.analytics_fps.value, device: f.device.value, trail_enabled: f.trail_enabled.checked,
      dwell_threshold_seconds: +f.dwell_threshold_seconds.value, occupancy_threshold: +f.occupancy_threshold.value,
      business_hours: { start: f.bh_start.value, end: f.bh_end.value, days }, retention_days: +f.retention_days.value, clip_enabled: f.clip_enabled.checked };
    await this.run(API.saveSettings(payload), "Settings saved");
  },
  async saveWebhook() {
    const w = document.getElementById("webhookForm");
    await this.run(API.saveSettings({ webhook: { enabled: w.enabled.checked, url: w.url.value.trim(), timeout_seconds: +w.timeout_seconds.value, max_retries: +w.max_retries.value, backoff_seconds: +w.backoff_seconds.value } }), "Webhook settings saved");
  },
  async loadRules() {
    const d = await this.run(API.rules()); if (!d) return; this.rules = d.rules;
    const tb = document.querySelector("#rulesTable tbody");
    tb.innerHTML = d.rules.map((r, i) => `<tr data-i="${i}"><td><b>${this.esc(r.title)}</b><br><span class="muted small">${this.esc(r.description)}</span></td>
      <td><input type="checkbox" data-k="enabled" ${r.enabled ? "checked" : ""}></td>
      <td><select data-k="severity">${["low", "medium", "high", "critical"].map((s) => `<option ${r.severity === s ? "selected" : ""}>${s}</option>`).join("")}</select></td>
      <td>${["dwell_time_exceeded", "occupancy_threshold"].includes(r.rule_type) ? `<input type="number" data-k="threshold" value="${r.threshold ?? ""}" style="width:80px">` : "—"}</td>
      <td><input type="number" data-k="cooldown_seconds" value="${r.cooldown_seconds}" style="width:80px"></td>
      <td><select data-k="schedule_mode">${["always", "within_hours", "outside_hours"].map((m) => `<option value="${m}" ${(r.schedule.mode || "always") === m ? "selected" : ""}>${m.replace("_", " ")}</option>`).join("")}</select></td>
      <td><input type="checkbox" data-k="evidence_required" ${r.evidence_required ? "checked" : ""}></td>
      <td><input type="checkbox" data-k="notify" ${r.notify ? "checked" : ""}></td></tr>`).join("");
  },
  async saveRules() {
    const rows = [...document.querySelectorAll("#rulesTable tbody tr")].map((tr) => {
      const r = { rule_id: this.rules[+tr.dataset.i].rule_id };
      tr.querySelectorAll("[data-k]").forEach((el) => { const k = el.dataset.k; if (k === "schedule_mode") r.schedule = { mode: el.value }; else if (el.type === "checkbox") r[k] = el.checked; else if (el.type === "number") { if (el.value !== "") r[k] = +el.value; } else r[k] = el.value; });
      return r;
    });
    await this.run(API.saveRules(rows), "Rules saved");
  },

  // ---------------- events ----------------
  async loadEvents() {
    const f = document.getElementById("eventFilters");
    const params = {}; new FormData(f).forEach((v, k) => { if (v) params[k] = v; }); params.limit = 300;
    document.getElementById("btnExportCsv").href = "/api/vi/events/export.csv?" + new URLSearchParams(params).toString();
    const d = await this.run(API.events(params)); if (!d) return;
    const fill = (name, opts, fmt) => { const sel = f[name]; const cur = sel.value; sel.innerHTML = `<option value="">All</option>` + opts.map(fmt).join(""); sel.value = cur; };
    fill("event_type", d.options.event_type, (t) => `<option value="${t}">${t.replace(/_/g, " ")}</option>`);
    fill("severity", d.options.severity, (t) => `<option value="${t}">${t}</option>`);
    fill("status", d.options.status, (t) => `<option value="${t}">${t}</option>`);
    fill("source_id", d.options.source_id, (s) => `<option value="${this.esc(s.id)}">${this.esc(s.name)}</option>`);
    document.querySelector("#eventsTable tbody").innerHTML = d.events.map((e) => `<tr>
      <td class="mono">${e.time_local}</td><td><span class="sev ${e.severity}">${e.severity}</span></td><td>${this.esc(e.title)}</td><td>${this.esc(e.source_name)}</td><td>${this.esc(e.zone_name || "-")}</td><td>${e.track_id != null ? "Person " + e.track_id : "-"}</td>
      <td><span class="st">${e.status}</span>${e.acknowledged_by ? `<br><span class="muted small">${this.esc(e.acknowledged_by)}</span>` : ""}</td>
      <td>${e.snapshot_url ? `<a class="link" href="javascript:App.showEvent('${e.event_id}')">snapshot</a>` : "-"}${e.clip_url ? ` · <a class="link" href="${e.clip_url}" target="_blank">clip</a>` : ""}</td>
      <td>${e.status === "new" ? `<button class="btn sm" onclick="App.act('${e.event_id}','ack')">Ack</button>` : ""}${e.status !== "resolved" && e.status !== "dismissed" ? ` <button class="btn sm ghost" onclick="App.act('${e.event_id}','resolve')">Resolve</button>` : ` <button class="btn sm ghost" onclick="App.act('${e.event_id}','reopen')">Reopen</button>`}</td></tr>`).join("");
    document.getElementById("eventsTotal").textContent = `${d.events.length} of ${d.total} event(s) shown`;
  },

  // ---------------- audit ----------------
  async runAudit(form) {
    const d = this.formData(form);
    const spec = { type: d.type, name: d.name || undefined };
    if (d.type === "rtsp") { spec.url = d.url || undefined; spec.username = d.username || undefined; spec.password = d.password || undefined; spec.stream_profile = d.stream_profile; }
    if (d.type === "webcam") spec.index = +(d.index_or_path || 0);
    if (d.type === "file") spec.path = d.index_or_path;
    const r = await this.run(API.startAudit(spec, +d.duration_seconds || 8), "Audit started — probing the source…");
    if (!r) return; form.querySelectorAll("input[type=password]").forEach((i) => { i.value = ""; });
    const poll = async () => { const a = await API.audit(r.audit_id); if (a.status !== "done") { setTimeout(poll, 1000); } this.loadAudits(); };
    setTimeout(poll, 1500);
  },
  async loadAudits() {
    const d = await this.run(API.audits()); if (!d) return;
    const el = document.getElementById("auditReports");
    if (!d.audits.length) { el.innerHTML = `<div class="muted small">No audits yet.</div>`; return; }
    el.innerHTML = d.audits.map((a) => a.status !== "done" ? `<div class="audit-card">⏳ Probing ${this.esc(a.source_name)}…</div>` : `<div class="audit-card">
      <div class="row"><span class="grade ${a.classification}">${a.classification}</span><div><b>${this.esc(a.source_name)}</b> — ${this.esc(a.classification_label)}<br><span class="muted small mono">${this.esc(a.masked_url)}${a.stream_profile ? " · " + a.stream_profile + "-stream" : ""}</span></div></div>
      <div class="kv" style="margin-top:8px"><span class="k">Reachable</span><span class="${a.reachable ? "ok" : "bad"}">${a.reachable ? "yes" : "no"}</span><span class="k">Connect time</span><span>${a.connect_time_ms ?? "-"} ms</span><span class="k">Resolution</span><span>${a.resolution || "-"}</span>
      <span class="k">FPS reported / observed</span><span>${a.reported_fps ?? "-"} / ${a.observed_fps ?? "-"}</span><span class="k">Codec</span><span>${a.codec || "unknown"}</span><span class="k">Frame interval</span><span>${a.mean_frame_interval_ms ?? "-"} ms ± ${a.frame_interval_std_ms ?? "-"} (max gap ${a.max_gap_ms ?? "-"})</span>
      <span class="k">Stability</span><span>${a.frame_stability || "-"} · stale ${a.stale_events} · failures ${a.read_failures}</span><span class="k">Frames</span><span>${a.frames_read} in ${a.duration_seconds}s</span></div>
      <ul class="bullets small">${(a.notes || []).map((n) => `<li>${this.esc(n)}</li>`).join("")}</ul></div>`).join("");
  },

  // ---------------- health ----------------
  async loadHealth() {
    const h = await this.run(API.health()); if (!h) return;
    const H = h.health, sys = H.system || {};
    document.getElementById("healthKpis").innerHTML = [["Capture fps", H.capture_fps], ["Inference fps", H.inference_fps], ["Latency ms (avg / p95)", `${H.latency_ms} / ${H.latency_p95_ms}`], ["Frames skipped", H.dropped_frames], ["Reconnections", H.reconnects],
      ["Since last frame", H.seconds_since_last_frame != null ? H.seconds_since_last_frame + "s" : "—"], ["Disk free", sys.disk_free_mb != null ? (sys.disk_free_mb / 1000).toFixed(1) + " GB" : "—"], ["Mode", `${h.ai.device}${h.gpu.cuda_available ? " (" + h.gpu.device_name + ")" : ""}`]]
      .map(([l, n]) => `<div class="kpi"><div class="num" style="font-size:22px">${n}</div><div class="lbl">${l}</div></div>`).join("");
    const comp = Object.entries(H.components || {}).map(([k, v]) => `<span class="k">${k}</span><span class="${v.ok ? "ok" : "bad"}">${v.ok ? "OK" : "PROBLEM"} — ${this.esc(v.detail)}</span>`).join("");
    document.getElementById("healthComponents").innerHTML = comp + `<span class="k">detector latency</span><span>${h.detector.last_latency_ms ?? "-"} ms · ${this.esc(h.detector.license_note || "")}</span><span class="k">active tracks</span><span>${h.tracker.active_tracks ?? 0} (${this.esc(h.tracker.backend)})</span><span class="k">schema</span><span>v${h.database.schema_version} · ${h.database.size_mb} MB${h.database.recovered_from_corruption ? " · recovered from a corrupt file" : ""}</span><span class="k">evidence</span><span>${h.evidence.storage_mb} MB used · retention ${h.evidence.retention_days} d · clips ${h.evidence.clip_enabled ? "on" : "off"} · skipped ${h.evidence.clips_skipped}</span><span class="k">rules</span><span>${h.rules.enabled}/${h.rules.rules} enabled · fired ${h.rules.fired_total}</span><span class="k">log file</span><span class="mono small">${this.esc(h.log_file || "-")}</span>`;
    document.getElementById("healthSystem").innerHTML = `<span class="k">Platform</span><span>${this.esc(sys.platform)} · Python ${sys.python}</span><span class="k">CPU</span><span>${sys.cpu_percent ?? "-"} %</span><span class="k">Memory</span><span>${sys.memory_percent ?? "-"} %</span><span class="k">GPU</span><span>${h.gpu.cuda_available ? this.esc(h.gpu.device_name) : "not available (CPU mode)"}${h.gpu.torch ? " · torch " + h.gpu.torch : ""}</span><span class="k">Uptime</span><span>${H.uptime_seconds}s</span><span class="k">Time</span><span>${h.time}</span>`;
    const w = h.webhook;
    document.getElementById("healthWebhook").innerHTML = `<span class="k">Enabled</span><span>${w.enabled ? "yes" : "no"}</span><span class="k">URL</span><span class="mono small">${this.esc(w.url || "-")}</span><span class="k">Sent / failed / dropped</span><span>${w.sent} / ${w.failed} / ${w.dropped}</span>` + (w.recent || []).map((r) => `<span class="k">${r.at}</span><span class="${r.ok ? "ok" : "bad"}">${r.event_id} · ${r.ok ? "delivered" : "failed: " + this.esc(r.error)} (${r.attempts} attempt${r.attempts > 1 ? "s" : ""})</span>`).join("");
    document.getElementById("healthErrors").innerHTML = (H.recent_errors || []).map((e) => `<div class="item high"><div class="t">${e.at} · ${this.esc(e.component)}</div>${this.esc(e.message)}</div>`).join("") || `<div class="muted small">No errors recorded.</div>`;
    const logs = await this.run(API.healthLogs()); if (!logs) return;
    document.querySelector("#healthLogTable tbody").innerHTML = logs.logs.map((l) => `<tr><td class="mono">${l.recorded_at}</td><td>${this.esc(l.source_id || "-")}</td><td>${l.source_status || "-"}</td><td>${l.capture_fps ?? "-"}</td><td>${l.inference_fps ?? "-"}</td><td>${l.latency_ms ?? "-"}</td><td>${l.dropped_frames ?? "-"}</td><td>${l.reconnects ?? "-"}</td><td>${l.cpu_percent ?? "-"}</td><td>${l.disk_free_mb ?? "-"}</td></tr>`).join("") || `<tr><td colspan="10" class="muted">No health rows yet (one is written every minute).</td></tr>`;
  },
};
document.addEventListener("DOMContentLoaded", () => App.init());
