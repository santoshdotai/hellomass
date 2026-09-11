/* Thin fetch wrapper for the Souveno Vision Intelligence API (/api/vi). */
const API = {
  async _req(method, url, body, isForm) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      if (isForm) opts.body = body; else { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    }
    const res = await fetch(url, opts);
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) {
      const d = data && data.detail;
      const msg = typeof d === "string" ? d : (d && d.message) ? `${d.message}: ${JSON.stringify(d.problems || "")}` : `Request failed (${res.status})`;
      const err = new Error(msg); err.detail = d; throw err;
    }
    return data;
  },
  get: (u) => API._req("GET", u),
  post: (u, b) => API._req("POST", u, b || {}),
  put: (u, b) => API._req("PUT", u, b || {}),
  health: () => API.get("/api/vi/health"),
  state: () => API.get("/api/vi/state"),
  source: () => API.get("/api/vi/source"),
  startSource: (spec) => API.post("/api/vi/source/start", spec),
  stopSource: () => API.post("/api/vi/source/stop"),
  restartSource: () => API.post("/api/vi/source/restart"),
  pause: (p) => API.post("/api/vi/source/pause", { paused: p }),
  webcams: () => API.get("/api/vi/source/webcams"),
  upload: (file) => { const f = new FormData(); f.append("file", file); return API._req("POST", "/api/vi/source/upload", f, true); },
  demo: (action, body) => API.post(`/api/vi/demo/${action}`, body || {}),
  zones: (sid) => API.get("/api/vi/zones" + (sid ? `?source_id=${encodeURIComponent(sid)}` : "")),
  saveZones: (sid, zones) => API.put("/api/vi/zones", { source_id: sid, zones }),
  rules: () => API.get("/api/vi/rules"),
  saveRules: (rules) => API.put("/api/vi/rules", { rules }),
  settings: () => API.get("/api/vi/settings"),
  saveSettings: (s) => API.put("/api/vi/settings", s),
  webhookTest: () => API.post("/api/vi/webhook/test"),
  events: (params) => API.get("/api/vi/events?" + new URLSearchParams(params).toString()),
  event: (id) => API.get(`/api/vi/events/${id}`),
  eventAction: (id, action, note) => API.post(`/api/vi/events/${id}/${action}`, { actor: "operator", note: note || "" }),
  startAudit: (spec, duration) => API.post("/api/vi/audit", { spec, duration_seconds: duration }),
  audit: (id) => API.get(`/api/vi/audit/${id}`),
  audits: () => API.get("/api/vi/audit"),
  healthLogs: () => API.get("/api/vi/health/logs?limit=60"),
};
