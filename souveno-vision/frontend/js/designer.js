/* Souveno Vision Solution Designer — form state, camera inventory grid, preview/save, result tabs. */
const Designer = {
  state: null,
  catalog: null,
  pricing: null,
  result: null,
  activeTab: "summary",

  blank() {
    return {
      client: { company_name: "", contact_name: "", industry: "other" },
      site: { name: "", city: "", employees: null, shifts: null, existing_camera_count: null },
      cameras: [],
      nvr: {}, server: {}, network: {},
      requirements: { use_cases: [], required_alert_latency_s: null, operating_schedule: "", privacy_requirements: "",
        employee_identification_requested: false, evidence_retention_days: 30, events_per_camera_per_day: 20, average_clip_size_mb: 5 },
      settings: { network_safety_factor: 1.5, analytics_fps: 5, assumed_bitrate_mbps: null, model_size: "small" },
      include_pilot_in_estimate: true,
    };
  },

  async init() {
    if (!document.getElementById("view-designer")) return;
    this.state = this.blank();
    try {
      this.catalog = await (await fetch("/api/designer/catalog")).json();
      this.pricing = (await (await fetch("/api/designer/pricing")).json()).pricing;
    } catch (e) { this.status("Could not load designer catalog: " + e.message, true); return; }
    this.renderUseCases();
    this.renderPricing();
    this.bindForm();
    document.getElementById("sdLoadSample").onclick = () => this.loadSample();
    document.getElementById("sdClear").onclick = () => { this.state = this.blank(); this.result = null; this.syncForm(); this.renderCameras(); this.renderOut(); };
    document.getElementById("sdAddCamera").onclick = () => { this.state.cameras.push({ name: "", count: 1, use_cases: [] }); this.renderCameras(); };
    document.getElementById("sdCsvFile").onchange = (e) => this.importCsv(e.target.files[0]);
    document.getElementById("sdExportCsv").onclick = () => this.exportCsv();
    document.getElementById("sdPreview").onclick = () => this.run(false);
    document.getElementById("sdSave").onclick = () => this.run(true);
    document.querySelectorAll("#sdTabs button").forEach((b) => b.onclick = () => {
      this.activeTab = b.dataset.tab;
      document.querySelectorAll("#sdTabs button").forEach((x) => x.classList.toggle("active", x === b));
      this.renderOut();
    });
    this.renderCameras();
  },

  status(msg, isError) {
    const el = document.getElementById("sdStatus");
    el.textContent = msg; el.style.color = isError ? "var(--critical)" : "";
  },

  // ---------------------------------------------------------------- form binding
  getPath(obj, path) { return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj); },
  setPath(obj, path, val) {
    const keys = path.split("."); let o = obj;
    keys.slice(0, -1).forEach((k) => { if (o[k] == null) o[k] = {}; o = o[k]; });
    o[keys[keys.length - 1]] = val;
  },
  coerce(el) {
    const v = el.value;
    if (el.dataset.type === "bool") return v === "" ? null : v === "true";
    if (el.dataset.type === "boolstrict") return v === "true";
    if (el.type === "number") return v === "" ? null : Number(v);
    return v === "" ? null : v;
  },
  bindForm() {
    document.querySelectorAll("#view-designer [data-path]").forEach((el) => {
      el.addEventListener("change", () => this.setPath(this.state, el.dataset.path, this.coerce(el)));
    });
  },
  syncForm() {
    document.querySelectorAll("#view-designer [data-path]").forEach((el) => {
      const v = this.getPath(this.state, el.dataset.path);
      if (el.dataset.type === "bool") el.value = v == null ? "" : String(v);
      else if (el.dataset.type === "boolstrict") el.value = String(!!v);
      else el.value = v == null ? "" : v;
    });
    document.querySelectorAll("#sdUseCases input").forEach((cb) => { cb.checked = this.state.requirements.use_cases.includes(cb.value); });
  },

  renderUseCases() {
    const box = document.getElementById("sdUseCases");
    box.innerHTML = this.catalog.use_cases.map((u) =>
      `<label title="${this.esc(u.required_view)}"><input type="checkbox" value="${u.id}" /> ${this.esc(u.name)}</label>`).join("");
    box.querySelectorAll("input").forEach((cb) => cb.onchange = () => {
      const set = new Set(this.state.requirements.use_cases);
      cb.checked ? set.add(cb.value) : set.delete(cb.value);
      this.state.requirements.use_cases = [...set];
    });
  },

  renderPricing() {
    const p = this.pricing;
    const box = document.getElementById("sdPricing");
    box.innerHTML = `
      <label>Technical pilot fee (₹)<input id="pr_pilot" type="number" value="${p.technical_pilot_fee}" /></label>
      <label>Production implementation (₹)<input id="pr_impl" type="number" value="${p.production_implementation_fee}" /></label>
      <label>GST rate<input id="pr_gst" type="number" step="0.01" value="${p.gst_rate}" /></label>
      <label>Pilot credit on production (₹)<input id="pr_credit" type="number" value="${p.pilot_credit_on_production}" /></label>
      ${p.licence_tiers.map((t, i) => `<label>${this.esc(t.label)} (₹/cam/month)<input data-tier="${i}" type="number" value="${t.rate_per_camera_month}" /></label>`).join("")}
      <div class="full"><button id="pr_save" class="btn secondary">Save pricing</button><button id="pr_reset" class="btn ghost">Reset defaults</button>
      <span class="hint">Pricing is stored server-side and applied to every new estimate.</span></div>`;
    box.querySelector("#pr_save").onclick = async () => {
      const tiers = p.licence_tiers.map((t, i) => ({ ...t, rate_per_camera_month: Number(box.querySelector(`[data-tier="${i}"]`).value) }));
      const body = { technical_pilot_fee: Number(box.querySelector("#pr_pilot").value), production_implementation_fee: Number(box.querySelector("#pr_impl").value),
        gst_rate: Number(box.querySelector("#pr_gst").value), pilot_credit_on_production: Number(box.querySelector("#pr_credit").value), licence_tiers: tiers };
      const res = await fetch("/api/designer/pricing", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!res.ok) { this.status((await res.json()).detail || "Pricing rejected", true); return; }
      this.pricing = (await res.json()).pricing; this.renderPricing(); this.status("Pricing saved.");
    };
    box.querySelector("#pr_reset").onclick = async () => {
      this.pricing = (await (await fetch("/api/designer/pricing/reset", { method: "POST" })).json()).pricing; this.renderPricing(); this.status("Pricing reset.");
    };
  },

  // ---------------------------------------------------------------- camera grid
  opts(list, val, labels) {
    return `<option value="">?</option>` + list.map((k) => `<option value="${k}" ${val === k ? "selected" : ""}>${labels ? labels[k] : k}</option>`).join("");
  },
  boolOpts(val) { return `<option value="">?</option><option value="true" ${val === true ? "selected" : ""}>Y</option><option value="false" ${val === false ? "selected" : ""}>N</option>`; },
  renderCameras() {
    const tbody = document.getElementById("sdCamRows");
    const types = ["ip_fixed", "ip_ptz", "ip_fisheye", "analog_dvr", "usb", "unknown"];
    const res = Object.keys(this.catalog.resolutions);
    const codecs = Object.keys(this.catalog.codecs);
    const f = (i, k, v, type = "text", cls = "") => `<input type="${type}" class="${cls}" data-i="${i}" data-k="${k}" value="${v == null ? "" : this.esc(String(v))}" />`;
    const s = (i, k, html) => `<select data-i="${i}" data-k="${k}">${html}</select>`;
    tbody.innerHTML = this.state.cameras.map((c, i) => `<tr>
      <td>${f(i, "ref", c.ref)}</td><td>${f(i, "name", c.name, "text", "wide")}</td><td>${f(i, "count", c.count, "number")}</td>
      <td>${f(i, "area", c.area)}</td><td>${s(i, "camera_type", this.opts(types, c.camera_type))}</td>
      <td>${s(i, "resolution", this.opts(res, c.resolution))}</td><td>${f(i, "fps", c.fps, "number")}</td>
      <td>${f(i, "bitrate_mbps", c.bitrate_mbps, "number")}</td><td>${s(i, "codec", this.opts(codecs, c.codec))}</td>
      <td>${s(i, "rtsp_available", this.boolOpts(c.rtsp_available))}</td><td>${s(i, "onvif_available", this.boolOpts(c.onvif_available))}</td>
      <td>${s(i, "substream_available", this.boolOpts(c.substream_available))}</td>
      <td>${s(i, "view_type", this.opts(["overhead", "oblique", "eye_level"], c.view_type))}</td>
      <td>${s(i, "lighting", this.opts(["good", "variable", "low", "ir_night", "backlit"], c.lighting))}</td>
      <td>${s(i, "occlusion", this.opts(["none", "partial", "heavy"], c.occlusion))}</td>
      <td>${s(i, "stream_stability", this.opts(["stable", "occasional_drops", "frequent_drops"], c.stream_stability))}</td>
      <td>${f(i, "subject_distance_m", c.subject_distance_m, "number")}</td><td>${f(i, "subject_height_px", c.subject_height_px, "number")}</td>
      <td><button class="btn ghost" data-del="${i}" title="Remove">✕</button></td></tr>`).join("");
    tbody.querySelectorAll("input,select").forEach((el) => el.onchange = () => {
      const c = this.state.cameras[Number(el.dataset.i)]; const k = el.dataset.k; const v = el.value;
      if (el.tagName === "SELECT" && (k.endsWith("_available") || k === "is_ptz")) c[k] = v === "" ? null : v === "true";
      else if (el.type === "number") c[k] = v === "" ? null : Number(v);
      else c[k] = v === "" ? null : v;
      if (k === "camera_type") c.is_ptz = v === "ip_ptz" ? true : (v === "" ? null : false);
    });
    tbody.querySelectorAll("[data-del]").forEach((b) => b.onclick = () => { this.state.cameras.splice(Number(b.dataset.del), 1); this.renderCameras(); });
  },

  async importCsv(file) {
    if (!file) return;
    const form = new FormData(); form.append("file", file);
    const res = await fetch("/api/designer/cameras/import", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) { this.status(data.detail || "Import failed", true); return; }
    this.state.cameras.push(...data.cameras);
    const errBox = document.getElementById("sdCsvErrors");
    errBox.classList.toggle("hidden", !data.errors.length);
    errBox.innerHTML = data.errors.map((e) => `Row ${e.row} (${this.esc(e.name || "")}): ${this.esc(e.error)}`).join("<br/>");
    this.renderCameras();
    this.status(`Imported ${data.imported} row(s), rejected ${data.rejected}.`);
    document.getElementById("sdCsvFile").value = "";
  },
  exportCsv() {
    const cols = ["ref", "name", "count", "area", "make_model", "camera_type", "resolution", "fps", "bitrate_mbps", "codec", "rtsp_available",
      "onvif_available", "mainstream_available", "substream_available", "is_ptz", "view_type", "lighting", "occlusion", "motion_blur",
      "stream_stability", "subject_distance_m", "subject_height_px", "use_cases", "notes"];
    const cell = (v) => { if (v == null) return ""; if (Array.isArray(v)) return v.join(";"); if (typeof v === "boolean") return v ? "yes" : "no"; const s = String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    const csv = [cols.join(",")].concat(this.state.cameras.map((c) => cols.map((k) => cell(c[k])).join(","))).join("\n");
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); a.download = "camera-inventory.csv"; a.click();
  },

  async loadSample() {
    this.state = await (await fetch("/api/designer/sample")).json();
    this.syncForm(); this.renderCameras(); this.status("Sample loaded — 348 cameras, 1,000 employees, unknown GPU/NVR capability.");
  },

  // ---------------------------------------------------------------- run
  payload() {
    const p = JSON.parse(JSON.stringify(this.state));
    ["nvr", "server", "network"].forEach((k) => { if (!p[k] || !Object.values(p[k]).some((v) => v != null && v !== "")) p[k] = null; });
    p.pricing_overrides = null;
    return p;
  },
  async run(save) {
    this.status(save ? "Saving assessment…" : "Running assessment…");
    const res = await fetch(save ? "/api/designer/assessments" : "/api/designer/assessments/preview",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(this.payload()) });
    const data = await res.json();
    if (!res.ok) {
      const msg = Array.isArray(data.detail) ? data.detail.map((d) => `${d.loc.slice(1).join(".")}: ${d.msg}`).join(" | ") : (data.detail || "Request failed");
      this.status(msg, true); return;
    }
    this.result = data;
    this.status(save ? `Saved as assessment #${data.id}. Report: /api/designer/assessments/${data.id}/report` : "Preview complete (not saved).");
    if (save) window.open(`/api/designer/assessments/${data.id}/report`, "_blank");
    this.activeTab = "summary";
    document.querySelectorAll("#sdTabs button").forEach((x) => x.classList.toggle("active", x.dataset.tab === "summary"));
    this.renderOut();
  },

  // ---------------------------------------------------------------- output
  esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); },
  inr(n) { return "₹" + Number(n).toLocaleString("en-IN"); },
  table(headers, rows) {
    return `<table><thead><tr>${headers.map((h) => `<th>${this.esc(h)}</th>`).join("")}</tr></thead><tbody>${
      rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  },
  ul(items) { return items && items.length ? `<ul>${items.map((i) => `<li>${this.esc(i)}</li>`).join("")}</ul>` : `<p class="muted">None.</p>`; },

  async renderOut() {
    const out = document.getElementById("sdOut");
    if (this.activeTab === "saved") { out.innerHTML = await this.savedHtml(); return; }
    const a = this.result;
    if (!a) { out.innerHTML = `<p class="muted">Fill in the form (or load the sample) and click Preview.</p>`; return; }
    const e = (s) => this.esc(s);
    const t = this.activeTab;
    if (t === "summary") {
      const s = a.suitability_summary;
      out.innerHTML = `
        <div class="decision"><strong>${e(a.decision.recommendation)}</strong> — ${e(a.decision.reason)}</div>
        <div class="kpi-row">
          <div class="kpi"><div class="v">${s.total_cameras}</div><div class="l">Cameras</div></div>
          <div class="kpi"><div class="v cls-A">${s.by_class.A.cameras}</div><div class="l">A · AI ready</div></div>
          <div class="kpi"><div class="v cls-B">${s.by_class.B.cameras}</div><div class="l">B · after config</div></div>
          <div class="kpi"><div class="v cls-C">${s.by_class.C.cameras}</div><div class="l">C · basic only</div></div>
          <div class="kpi"><div class="v cls-D">${s.by_class.D.cameras}</div><div class="l">D · unsuitable</div></div>
          <div class="kpi"><div class="v">${s.validation_required_cameras}</div><div class="l">need site validation</div></div>
        </div>
        <h4>Executive summary <span class="hint">(${e(a.narrative_generated_by)})</span></h4><p>${e(a.narrative.executive_summary)}</p>
        <h4>Client objectives</h4><p>${e(a.narrative.client_objectives)}</p>
        <div class="warn-box">${e(a.compute.capacity_statement)}</div>
        <h4>Safety rules applied</h4>${this.ul(a.safety_rules_applied)}`;
    } else if (t === "suitability") {
      out.innerHTML = this.table(["Camera / group", "Count", "Score", "Class", "Blockers / validation", "Actions"],
        a.suitability.map((r) => [e(r.label), r.count, r.score, `<span class="cls-${r.classification}">${r.classification}</span> ${e(r.class_label)}`,
          e(r.hard_blockers.join("; ") || (r.validation_items.length ? "Site validation required" : "—")), e(r.required_actions.join("; ") || "—")]))
        + a.suitability.map((r) => `<details><summary>${e(r.label)} — factor breakdown</summary>${
          this.table(["Factor", "Points", "Reason"], r.factors.map((f) => [e(f.factor), `${f.points}/${f.max_points}`, e(f.reason) + (f.action ? ` <em>→ ${e(f.action)}</em>` : "")]))}</details>`).join("");
    } else if (t === "calcs") {
      out.innerHTML = this.table(["Calculation", "Result", "Formula", "Inputs", "Assumptions / warnings"],
        Object.values(a.calculations).map((c) => [e(c.name), c.value == null ? "—" : `${c.value} ${e(c.unit)}`, `<code>${e(c.formula)}</code>`,
          e(Object.entries(c.inputs).map(([k, v]) => `${k}=${v}`).join(", ")), e([...c.assumptions, ...c.warnings].join(" "))]))
        + `<h4>Assumptions</h4>${this.ul(a.assumptions)}`;
    } else if (t === "compute") {
      const c = a.compute;
      out.innerHTML = `<div class="warn-box"><strong>${e(c.capacity_statement)}</strong></div>
        <p>${e(c.recommendation)}</p><h4>Findings</h4>${this.ul(c.findings)}<h4>Warnings</h4>${this.ul(c.warnings)}
        <h4>Workload profile</h4>${this.table(["Metric", "Value"], Object.entries(c.workload_profile).filter(([k]) => k !== "note").map(([k, v]) => [e(k), e(v)]))}
        <p class="hint">${e(c.workload_profile.note)}</p><h4>Factors considered</h4>${this.ul(c.factors_considered)}`;
    } else if (t === "usecases") {
      out.innerHTML = a.use_cases.map((u) => `<h4>${e(u.name)} <span class="hint">${u.candidate_camera_count} candidate cameras</span></h4>${
        this.table(["Item", "Recommendation"], [["Required view", u.required_camera_view], ["Resolution", u.suggested_resolution], ["Analytics FPS", u.suggested_analytics_fps],
          ["Placement", u.camera_placement_requirements], ["Model", u.model_category], ["Business rule", u.business_rule], ["Alert workflow", u.alert_workflow],
          ["Evidence", u.evidence], ["Limitations", u.limitations], ["Success metric", u.success_metric], ["Approvals", u.approvals_required.join("; ") || "—"]].map(([k, v]) => [e(k), e(v)]))}${u.note ? `<div class="warn-box">${e(u.note)}</div>` : ""}`).join("");
    } else if (t === "pilot") {
      const p = a.pilot;
      out.innerHTML = `<p>${e(a.narrative.pilot_narrative)}</p>${p.warnings.length ? `<div class="warn-box">${e(p.warnings.join(" "))}</div>` : ""}
        ${this.table(["Pilot camera", "Area", "Class", "Score", "Why"], p.cameras.map((c) => [e(c.unit), e(c.area), `<span class="cls-${c.classification}">${c.classification}</span>`, c.score, e(c.reason)]))}
        <h4>Use cases</h4>${this.table(["Use case", "Success metric"], p.use_cases.map((u) => [e(u.name), e(u.success_metric)]))}
        <h4>Validation plan</h4>${this.table(["Measurement", "Method"], Object.entries(p.validation_plan).map(([k, v]) => [e(k), e(v)]))}
        <h4>Scale-up decision criteria</h4>${this.ul(p.scale_up_decision_criteria)}`;
    } else if (t === "arch") {
      const r = a.architecture;
      out.innerHTML = this.table(["Element", "Design"], [["NVR/VMS integration", `<strong>${e(r.nvr_integration_approach)}</strong><br/>${e(r.nvr_integration_detail)}`],
        ["Stream source", e(r.stream_source)], ["Stream profile", e(r.stream_profile)], ["Topology", e(r.deployment_topology)], ["Network placement", e(r.network_placement)], ["Privacy", e(r.privacy)]])
        + `<h4>Deployment phases</h4>${this.ul(r.phased_rollout)}`;
    } else if (t === "risks") {
      out.innerHTML = this.table(["ID", "Risk", "Severity", "Impact", "Mitigation", "Owner"],
        a.risks.map((r) => [r.id, e(r.title), `<span class="sev-${r.severity}">${e(r.severity)}</span>`, e(r.impact), e(r.mitigation), e(r.owner)]));
    } else if (t === "commercial") {
      const c = a.commercial; const m = (b) => `${this.inr(b.ex_gst)} + GST ${this.inr(b.gst)} = <strong>${this.inr(b.incl_gst)}</strong>`;
      out.innerHTML = `<div class="warn-box">${e(c.status)}</div>
        ${this.table(["Tier", "Cameras", "Rate", "Monthly"], c.licence_breakdown.map((t) => [e(t.tier), t.cameras, this.inr(t.rate_per_camera_month), this.inr(t.monthly_amount)]))}
        ${this.table(["Line", "Amount"], [["Monthly licence", m(c.monthly_licence)], ["Annual licence", m(c.annual_licence)],
          [`Technical pilot (${e(c.technical_pilot.covers)})`, m(c.technical_pilot)], [`Pilot adjustment — ${e(c.pilot_adjustment.description)}`, this.inr(c.pilot_adjustment.amount_ex_gst)],
          ["One-time implementation", m(c.one_time_implementation)], ["One-time total", m(c.one_time_total)], ["First-year total", m(c.first_year_total)], ["Second-year software", m(c.second_year_software_total)]])}
        <p><strong>Hardware:</strong> ${e(c.hardware)}</p><h4>Exclusions</h4>${this.ul(c.exclusions)}
        <p class="hint">Scenario if all ${a.commercial_scenario_all_cameras.active_cameras} cameras were licensed: ${this.inr(a.commercial_scenario_all_cameras.monthly_licence)} / month + GST.</p>`;
    } else if (t === "actions") {
      out.innerHTML = `<h4>Required client actions</h4>${this.ul(a.required_client_actions)}`;
    }
  },

  async savedHtml() {
    const data = await (await fetch("/api/designer/assessments")).json();
    if (!data.assessments.length) return `<p class="muted">No saved assessments yet.</p>`;
    return this.table(["#", "Client", "Site", "Cameras", "Candidates", "Recommendation", "Monthly (ex GST)", "Report"],
      data.assessments.map((a) => [a.id, this.esc(a.client), this.esc(a.site), a.total_cameras, a.candidate_ai_cameras, this.esc(a.recommendation),
        a.monthly_licence_ex_gst == null ? "—" : this.inr(a.monthly_licence_ex_gst),
        `<a href="/api/designer/assessments/${a.id}/report" target="_blank">HTML</a> · <a href="/api/designer/assessments/${a.id}" target="_blank">JSON</a>`]));
  },
};

document.addEventListener("DOMContentLoaded", () => Designer.init());
