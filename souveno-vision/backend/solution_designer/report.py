"""Client proposal generator.

Primary output is print-ready HTML (self-contained, A4 print stylesheet).
DOCX and PDF exports are offered only when the optional libraries
(`python-docx`, `weasyprint`) are importable — they are not project
dependencies, so the HTML path is the guaranteed one.
"""
from __future__ import annotations

import html
from datetime import datetime

from backend.solution_designer.narrative import _fmt_inr

SECTIONS = [
    "Executive summary", "Client objectives", "Existing infrastructure", "Camera suitability",
    "NVR/VMS integration approach", "Proposed stream architecture", "Use-case recommendations",
    "Network calculations", "Preliminary compute assessment", "Pilot scope", "Deployment phases",
    "Security and privacy", "Assumptions", "Risks and limitations", "Commercial estimate",
    "Required client actions", "Next steps",
]


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def _ul(items) -> str:
    return "<ul>" + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ul>" if items else "<p class='muted'>None.</p>"


def _table(headers, rows) -> str:
    h = "".join(f"<th>{_e(x)}</th>" for x in headers)
    b = "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>"


def _money(block: dict) -> str:
    return f"{_fmt_inr(block['ex_gst'])} + GST {_fmt_inr(block['gst'])} = {_fmt_inr(block['incl_gst'])}"


def report_sections(a: dict) -> list[dict]:
    n = a["narrative"]
    s = a["suitability_summary"]
    est = a["commercial"]
    comp = a["compute"]
    arch = a["architecture"]
    calcs = a["calculations"]
    pil = a["pilot"]

    suit_rows = [(r["label"], r["count"], r["score"], f"{r['classification']} — {r['class_label']}",
                  "; ".join(r["hard_blockers"]) or ("Site validation required" if r["validation_items"] else "—"),
                  "; ".join(r["required_actions"][:3]) or "—") for r in a["suitability"]]
    suit_html = (
        _table(["Class", "Label", "Cameras"], [(k, v["label"], v["cameras"]) for k, v in s["by_class"].items()])
        + _table(["Camera / group", "Count", "Score", "Class", "Blocker / validation", "Required actions"], suit_rows)
        + "<details><summary>Score breakdown per camera group</summary>"
        + "".join(f"<h4>{_e(r['label'])} — {r['score']}/100</h4>" +
                  _table(["Factor", "Points", "Reason"], [(f["factor"], f"{f['points']}/{f['max_points']}", f["reason"]) for f in r["factors"]])
                  for r in a["suitability"]) + "</details>"
    )

    uc_html = "".join(
        f"<h4>{_e(u['name'])}</h4>" + _table(["Item", "Recommendation"], [
            ("Required camera view", u["required_camera_view"]), ("Suggested resolution", u["suggested_resolution"]),
            ("Suggested analytics FPS", u["suggested_analytics_fps"]), ("Camera placement", u["camera_placement_requirements"]),
            ("Model category", u["model_category"]), ("Business rule", u["business_rule"]),
            ("Alert workflow", u["alert_workflow"]), ("Evidence", u["evidence"]), ("Limitations", u["limitations"]),
            ("Success metric", u["success_metric"]),
            ("Candidate cameras", f"{u['candidate_camera_count']} ({', '.join(u['candidate_cameras']) or 'none yet'})"),
            ("Approvals required", "; ".join(u["approvals_required"]) or "None beyond standard privacy notice"),
        ]) + (f"<p class='warn'>{_e(u['note'])}</p>" if u.get("note") else "")
        for u in a["use_cases"] if "name" in u)

    calc_rows = [(c["name"], "—" if c["value"] is None else f"{c['value']} {c['unit']}", c["formula"],
                  "; ".join(f"{k}={v}" for k, v in c["inputs"].items()), " ".join(c["assumptions"] + c["warnings"]))
                 for c in calcs.values()]
    net_html = f"<p>{_e(n['network_narrative'])}</p>" + _table(["Calculation", "Result", "Formula", "Inputs", "Assumptions / warnings"], calc_rows)

    comp_html = (f"<p>{_e(n['compute_narrative'])}</p><p><strong>{_e(comp['capacity_statement'])}</strong></p>"
                 + "<h4>Workload profile</h4>" + _table(["Metric", "Value"], [(k, v) for k, v in comp["workload_profile"].items() if k != "note"])
                 + f"<p class='muted'>{_e(comp['workload_profile']['note'])}</p>"
                 + "<h4>Factors considered</h4>" + _ul(comp["factors_considered"]))

    pilot_html = (f"<p>{_e(n['pilot_narrative'])}</p>"
                  + _table(["Pilot camera", "Area", "Class", "Score", "Why included"],
                           [(c["unit"], c["area"], c["classification"], c["score"], c["reason"]) for c in pil["cameras"]])
                  + "<h4>Validation plan</h4>" + _table(["Measurement", "Method"], list(pil["validation_plan"].items()))
                  + "<h4>Scale-up decision criteria</h4>" + _ul(pil["scale_up_decision_criteria"])
                  + (_ul(pil["warnings"]) if pil["warnings"] else ""))

    comm_html = (f"<p class='warn'><strong>{_e(est['status'])}</strong></p><p>{_e(n['commercial_narrative'])}</p>"
                 + _table(["Tier", "Cameras", "Rate / camera / month", "Monthly"],
                          [(t["tier"], t["cameras"], _fmt_inr(t["rate_per_camera_month"]), _fmt_inr(t["monthly_amount"])) for t in est["licence_breakdown"]])
                 + _table(["Line", "Amount"], [
                     ("Monthly licence", _money(est["monthly_licence"])), ("Annual licence", _money(est["annual_licence"])),
                     ("Technical pilot (" + est["technical_pilot"]["covers"] + ")", _money(est["technical_pilot"])),
                     ("Pilot adjustment — " + est["pilot_adjustment"]["description"], _fmt_inr(est["pilot_adjustment"]["amount_ex_gst"])),
                     ("One-time production implementation", _money(est["one_time_implementation"])),
                     ("One-time total", _money(est["one_time_total"])),
                     ("First-year total", _money(est["first_year_total"])),
                     ("Second-year software total", _money(est["second_year_software_total"])),
                 ])
                 + f"<p><strong>Hardware:</strong> {_e(est['hardware'])}</p><h4>Exclusions</h4>" + _ul(est["exclusions"])
                 + f"<p class='muted'>Scenario for reference only — if all {a['commercial_scenario_all_cameras']['active_cameras']} cameras "
                   f"were licensed: {_fmt_inr(a['commercial_scenario_all_cameras']['monthly_licence'])} per month + GST.</p>")

    risk_html = _table(["ID", "Risk", "Severity", "Likelihood", "Impact", "Mitigation", "Owner"],
                       [(r["id"], r["title"], r["severity"], r["likelihood"], r["impact"], r["mitigation"], r["owner"]) for r in a["risks"]])

    privacy_html = ("<p>All analytics in this design use anonymous detection and tracking: people are numbered objects, "
                    "not identities. No facial recognition, no biometric templates and no employee identification are included.</p>"
                    f"<p>{_e(arch['privacy'])}</p>"
                    + _ul([
                        "Video stays on the client's network; only alert metadata and approved evidence clips leave the inference server.",
                        f"Evidence retention: {a['input']['requirements']['evidence_retention_days']} days, then automatic deletion.",
                        "Role-based access to evidence; audit log of every evidence view/export.",
                        "HR and legal sign-off required for any use case whose evidence shows identifiable staff (e.g. PPE compliance).",
                        f"Client privacy requirements recorded: {a['input']['requirements'].get('privacy_requirements') or 'none stated'}.",
                    ]))

    phases_html = _ul(arch["phased_rollout"])
    next_steps = [
        "Client reviews this preliminary design and confirms the pilot areas and use cases.",
        "Site validation visit: stream tests per camera group, NVR export test, nvidia-smi capture, network check.",
        "Pilot agreement and HR/legal approvals signed.",
        f"{pil['duration_days']}-day technical pilot with benchmarks.",
        "Pilot report with measured accuracy, false alerts, stream stability, GPU and network utilisation.",
        "Final architecture, hardware specification and commercial proposal issued from pilot evidence.",
    ]

    return [
        {"title": SECTIONS[0], "html": f"<p>{_e(n['executive_summary'])}</p><p class='decision'><strong>Recommendation: {_e(a['decision']['recommendation'])}.</strong> {_e(a['decision']['reason'])}</p>"},
        {"title": SECTIONS[1], "html": f"<p>{_e(n['client_objectives'])}</p>"},
        {"title": SECTIONS[2], "html": f"<p>{_e(n['existing_infrastructure'])}</p>"},
        {"title": SECTIONS[3], "html": suit_html},
        {"title": SECTIONS[4], "html": f"<p><strong>{_e(arch['nvr_integration_approach'])}</strong></p><p>{_e(arch['nvr_integration_detail'])}</p>"},
        {"title": SECTIONS[5], "html": _table(["Element", "Design"], [
            ("Stream source", arch["stream_source"]), ("Stream profile", arch["stream_profile"]),
            ("Deployment topology", arch["deployment_topology"]), ("Network placement", arch["network_placement"])])},
        {"title": SECTIONS[6], "html": uc_html},
        {"title": SECTIONS[7], "html": net_html},
        {"title": SECTIONS[8], "html": comp_html},
        {"title": SECTIONS[9], "html": pilot_html},
        {"title": SECTIONS[10], "html": phases_html},
        {"title": SECTIONS[11], "html": privacy_html},
        {"title": SECTIONS[12], "html": _ul(a["assumptions"])},
        {"title": SECTIONS[13], "html": risk_html},
        {"title": SECTIONS[14], "html": comm_html},
        {"title": SECTIONS[15], "html": _ul(a["required_client_actions"])},
        {"title": SECTIONS[16], "html": _ul(next_steps)},
    ]


CSS = """
body{font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#1a1f2b;margin:0;background:#fff;line-height:1.5;font-size:13px}
.page{max-width:900px;margin:0 auto;padding:32px}
header{border-bottom:3px solid #1c5f99;padding-bottom:12px;margin-bottom:24px}
header h1{margin:0;font-size:24px;color:#1c5f99}
header .meta{color:#5a647a;font-size:12px}
.banner{background:#fff6e5;border:1px solid #f5a623;padding:10px 14px;border-radius:6px;margin:16px 0;font-weight:600}
h2{font-size:16px;color:#1c5f99;border-bottom:1px solid #d9e1ee;padding-bottom:4px;margin-top:28px;page-break-after:avoid}
h4{margin:14px 0 6px;font-size:13px}
table{border-collapse:collapse;width:100%;margin:8px 0;font-size:12px;page-break-inside:auto}
th,td{border:1px solid #d9e1ee;padding:5px 7px;text-align:left;vertical-align:top}
th{background:#eef3fa}
tr{page-break-inside:avoid}
.muted{color:#5a647a}.warn{color:#9a5b00}.decision{background:#eef8e8;border-left:4px solid #3c8a2e;padding:8px 12px}
details summary{cursor:pointer;color:#1c5f99;margin:8px 0}
footer{margin-top:32px;border-top:1px solid #d9e1ee;padding-top:8px;font-size:11px;color:#5a647a}
@media print{.page{padding:0}.no-print{display:none}details{display:block}details summary{display:none}details>*{display:block}}
"""


def render_html(a: dict, sections: list[dict] | None = None) -> str:
    sections = sections or report_sections(a)
    client = a["input"]["client"]["company_name"]
    site = a["input"]["site"]["name"]
    date = datetime.utcnow().strftime("%d %b %Y")
    toc = "<ol>" + "".join(f"<li><a href='#s{i}'>{_e(s['title'])}</a></li>" for i, s in enumerate(sections, 1)) + "</ol>"
    body = "".join(f"<section id='s{i}'><h2>{i}. {_e(s['title'])}</h2>{s['html']}</section>" for i, s in enumerate(sections, 1))
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Souveno Vision — Solution Design for {_e(client)}</title><style>{CSS}</style></head><body><div class="page">
<header><h1>Souveno Vision — AI Video Analytics Solution Design</h1>
<div class="meta">Prepared for {_e(client)} · {_e(site)} · {date} · Narrative generated by: {_e(a.get('narrative_generated_by', 'rule_based'))}</div></header>
<div class="banner">PRELIMINARY — all figures, camera classifications and the commercial estimate are provisional until the technical pilot is completed and stream/GPU benchmarks exist.</div>
<div class="no-print"><button onclick="window.print()">Print / Save as PDF</button></div>
<h2>Contents</h2>{toc}{body}
<footer>Souveno Vision Solution Designer · Calculations are deterministic and traceable (formula, inputs and assumptions shown in section 8). This document does not guarantee camera compatibility, GPU capacity or detection accuracy.</footer>
</div></body></html>"""


def export_capabilities() -> dict:
    caps = {"html": True, "docx": False, "pdf": False}
    try:
        import docx  # noqa: F401
        caps["docx"] = True
    except ImportError:
        pass
    try:
        import weasyprint  # noqa: F401
        caps["pdf"] = True
    except ImportError:
        pass
    return caps


def _strip_tags(s: str) -> str:
    import re
    return html.unescape(re.sub(r"<[^>]+>", " ", s)).strip()


def render_docx(a: dict) -> bytes:
    """Requires python-docx (optional). Tables are flattened to text rows."""
    import io
    from docx import Document  # type: ignore

    doc = Document()
    doc.add_heading("Souveno Vision — AI Video Analytics Solution Design", 0)
    doc.add_paragraph(f"Prepared for {a['input']['client']['company_name']} · {a['input']['site']['name']}")
    doc.add_paragraph("PRELIMINARY — provisional until the technical pilot is completed and stream/GPU benchmarks exist.")
    for i, s in enumerate(report_sections(a), 1):
        doc.add_heading(f"{i}. {s['title']}", 1)
        for para in [p for p in _strip_tags(s["html"].replace("</tr>", "\n").replace("</li>", "\n").replace("</p>", "\n")).split("\n") if p.strip()]:
            doc.add_paragraph(" ".join(para.split()))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def render_pdf(a: dict) -> bytes:
    """Requires weasyprint (optional)."""
    from weasyprint import HTML  # type: ignore
    return HTML(string=render_html(a)).write_pdf()
