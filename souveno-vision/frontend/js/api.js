const API = {
  async upload(file) {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/sessions/upload", { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json()).detail || "Upload failed");
    return res.json();
  },
  async getSession(id) {
    const res = await fetch(`/api/sessions/${id}`);
    return res.json();
  },
  frameUrl(sessionId, seconds) {
    return `/api/sessions/${sessionId}/frame?seconds=${seconds}`;
  },
  async saveZones(sessionId, zones) {
    const res = await fetch("/api/zones", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, zones }),
    });
    if (!res.ok) throw new Error("Failed to save zones");
    return res.json();
  },
  async getDefaultZones() {
    const res = await fetch("/api/zones/defaults");
    return res.json();
  },
  async getSessionZones(sessionId) {
    const res = await fetch(`/api/zones/session/${sessionId}`);
    return res.json();
  },
  async getZoneTypes() {
    const res = await fetch("/api/zones/types");
    return res.json();
  },
  async startAnalysis(sessionId) {
    const res = await fetch(`/api/sessions/${sessionId}/start`, { method: "POST" });
    return res.json();
  },
  async resetSession(sessionId) {
    const res = await fetch(`/api/sessions/${sessionId}/reset`, { method: "POST" });
    return res.json();
  },
  async getSummary(sessionId) {
    const res = await fetch(`/api/sessions/${sessionId}/summary`);
    if (!res.ok) return null;
    return res.json();
  },
  async listEvents(sessionId) {
    const res = await fetch(`/api/events/session/${sessionId}`);
    return res.json();
  },
  async modelStatus() {
    const res = await fetch("/api/config/models");
    return res.json();
  },
  async getRules() {
    const res = await fetch("/api/config/rules");
    return res.json();
  },
  async estimateCost(payload) {
    const res = await fetch("/api/cost/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Estimate failed");
    return res.json();
  },
  async testCamera(payload) {
    const res = await fetch("/api/cameras/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return res.json();
  },
  async health() {
    const res = await fetch("/api/health");
    return res.json();
  },
};
