"""Persistence for assessments: writes the normalised input rows and the
JSON outputs, and reads them back for the API and report endpoints."""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from backend.solution_designer import models as m
from backend.solution_designer.schemas import AssessmentRequest


def _j(x) -> str:
    return json.dumps(x, default=str)


def get_or_create_client(db: Session, spec: dict) -> m.Client:
    obj = db.query(m.Client).filter(m.Client.company_name == spec["company_name"]).first()
    if obj:
        for k in ("contact_name", "contact_email", "contact_phone", "industry"):
            if spec.get(k):
                setattr(obj, k, spec[k])
        return obj
    obj = m.Client(company_name=spec["company_name"], contact_name=spec.get("contact_name") or "",
                   contact_email=spec.get("contact_email") or "", contact_phone=spec.get("contact_phone") or "",
                   industry=spec.get("industry") or "other")
    db.add(obj)
    db.flush()
    return obj


def get_or_create_site(db: Session, client: m.Client, spec: dict) -> m.Site:
    obj = db.query(m.Site).filter(m.Site.client_id == client.id, m.Site.name == spec["name"]).first()
    if not obj:
        obj = m.Site(client_id=client.id, name=spec["name"])
        db.add(obj)
    for k in ("address", "city", "employees", "shifts", "existing_camera_count", "operating_hours"):
        v = spec.get(k)
        if v is not None:
            setattr(obj, k, v)
    db.flush()
    return obj


def replace_site_inventory(db: Session, site: m.Site, req: AssessmentRequest) -> None:
    """The latest assessment is the source of truth for the site's inventory."""
    for rel in (site.cameras, site.camera_groups, site.nvrs, site.servers, site.networks):
        for row in list(rel):
            db.delete(row)
    db.flush()
    for c in req.cameras:
        spec = c.model_dump()
        if c.count > 1:
            db.add(m.CameraGroup(site_id=site.id, ref=c.ref or "", name=c.name, count=c.count, area=c.area or "",
                                 spec_json=_j(spec)))
        else:
            db.add(m.Camera(site_id=site.id, ref=c.ref or "", name=c.name, area=c.area or "", make_model=c.make_model or "",
                            camera_type=c.camera_type, resolution=c.resolution, fps=c.fps, bitrate_mbps=c.bitrate_mbps,
                            codec=c.codec, rtsp_available=c.rtsp_available, onvif_available=c.onvif_available,
                            mainstream_available=c.mainstream_available, substream_available=c.substream_available,
                            is_ptz=c.is_ptz, spec_json=_j(spec)))
    if req.nvr:
        d = req.nvr.model_dump()
        db.add(m.NVR(site_id=site.id, brand=d.get("brand") or "", model=d.get("model") or "", firmware=d.get("firmware") or "",
                     channel_count=d.get("channel_count"), rtsp_available=d.get("rtsp_available"),
                     api_sdk_available=d.get("api_sdk_available"), outbound_stream_limit=d.get("outbound_stream_limit"),
                     is_dvr=d.get("is_dvr"), notes=d.get("notes") or ""))
    if req.server:
        d = req.server.model_dump()
        db.add(m.Server(site_id=site.id, has_gpu=d.get("has_gpu"), cpu_model=d.get("cpu_model") or "", cpu_cores=d.get("cpu_cores"),
                        ram_gb=d.get("ram_gb"), gpu_model=d.get("gpu_model") or "", gpu_vram_gb=d.get("gpu_vram_gb"),
                        gpu_count=d.get("gpu_count"), nvidia_smi_output=d.get("nvidia_smi_output") or "",
                        existing_gpu_utilization_pct=d.get("existing_gpu_utilization_pct"),
                        existing_cpu_utilization_pct=d.get("existing_cpu_utilization_pct"), os=d.get("os") or "",
                        notes=d.get("notes") or ""))
    if req.network:
        d = req.network.model_dump()
        db.add(m.Network(site_id=site.id, link_speed_mbps=d.get("link_speed_mbps"), camera_vlan=d.get("camera_vlan") or "",
                         internet_restricted=d.get("internet_restricted"), cloud_allowed=d.get("cloud_allowed"),
                         poe_switch_capacity_ok=d.get("poe_switch_capacity_ok"), notes=d.get("notes") or ""))
    db.flush()


def save_assessment(db: Session, req: AssessmentRequest, result: dict, report_html: str) -> m.Assessment:
    client = get_or_create_client(db, req.client.model_dump())
    site = get_or_create_site(db, client, req.site.model_dump())
    replace_site_inventory(db, site, req)

    reqs = req.requirements
    asmt = m.Assessment(
        site_id=site.id, status="completed", input_json=_j(req.model_dump()),
        summary_json=_j({"suitability_summary": result["suitability_summary"], "decision": result["decision"],
                         "monthly_licence_ex_gst": result["commercial"]["monthly_licence"]["ex_gst"]}),
        required_alert_latency_s=reqs.required_alert_latency_s, operating_schedule=reqs.operating_schedule or "",
        privacy_requirements=reqs.privacy_requirements or "", evidence_retention_days=reqs.evidence_retention_days,
    )
    db.add(asmt)
    db.flush()

    pilot_ids = {u["id"] for u in result["pilot"]["use_cases"]}
    for u in result["use_cases"]:
        if "name" not in u:
            continue
        db.add(m.UseCase(assessment_id=asmt.id, use_case_id=u["id"], name=u["name"], in_pilot=u["id"] in pilot_ids,
                         recommendation_json=_j(u)))
    for c in result["calculations"].values():
        db.add(m.Calculation(assessment_id=asmt.id, name=c["name"], value=c["value"], unit=c["unit"], formula=c["formula"],
                             inputs_json=_j(c["inputs"]), assumptions_json=_j(c["assumptions"]), warnings_json=_j(c["warnings"])))
    for kind in ("suitability", "suitability_summary", "compute", "architecture", "pilot", "risks",
                 "required_client_actions", "decision", "assumptions"):
        db.add(m.Recommendation(assessment_id=asmt.id, kind=kind, payload_json=_j(result[kind]), generated_by="rule_based"))
    db.add(m.Recommendation(assessment_id=asmt.id, kind="narrative", payload_json=_j(result["narrative"]),
                            generated_by=result["narrative_generated_by"]))
    db.add(m.Proposal(assessment_id=asmt.id, version=1, status="preliminary", commercial_json=_j(result["commercial"]),
                      pricing_config_json=_j(result["commercial"]["pricing_config_used"]), report_html=report_html,
                      narrative_generated_by=result["narrative_generated_by"]))
    db.commit()
    db.refresh(asmt)
    return asmt


def load_assessment(db: Session, assessment_id: int) -> Optional[dict]:
    asmt = db.query(m.Assessment).filter(m.Assessment.id == assessment_id).first()
    if not asmt:
        return None
    recs = {r.kind: json.loads(r.payload_json) for r in asmt.recommendations}
    proposal = asmt.proposals[-1] if asmt.proposals else None
    return {
        "id": asmt.id, "assessment_uid": asmt.assessment_uid, "created_at": asmt.created_at.isoformat(),
        "site": {"id": asmt.site.id, "name": asmt.site.name, "client": asmt.site.client.company_name},
        "input": json.loads(asmt.input_json),
        "calculations": {c.name: {"name": c.name, "value": c.value, "unit": c.unit, "formula": c.formula,
                                  "inputs": json.loads(c.inputs_json), "assumptions": json.loads(c.assumptions_json),
                                  "warnings": json.loads(c.warnings_json)} for c in asmt.calculations},
        "use_cases": [json.loads(u.recommendation_json) for u in asmt.use_cases],
        **recs,
        "commercial": json.loads(proposal.commercial_json) if proposal else None,
        "proposal": {"id": proposal.id, "uid": proposal.proposal_uid, "status": proposal.status, "version": proposal.version,
                     "narrative_generated_by": proposal.narrative_generated_by} if proposal else None,
    }


def list_assessments(db: Session) -> list[dict]:
    rows = db.query(m.Assessment).order_by(m.Assessment.created_at.desc()).all()
    out = []
    for a in rows:
        summ = json.loads(a.summary_json)
        out.append({"id": a.id, "assessment_uid": a.assessment_uid, "created_at": a.created_at.isoformat(),
                    "client": a.site.client.company_name, "site": a.site.name,
                    "total_cameras": summ.get("suitability_summary", {}).get("total_cameras"),
                    "candidate_ai_cameras": summ.get("suitability_summary", {}).get("candidate_ai_cameras"),
                    "recommendation": summ.get("decision", {}).get("recommendation"),
                    "monthly_licence_ex_gst": summ.get("monthly_licence_ex_gst")})
    return out


def site_cameras_for_export(db: Session, site_id: int) -> list[dict]:
    site = db.query(m.Site).filter(m.Site.id == site_id).first()
    if not site:
        return []
    rows = [json.loads(g.spec_json) for g in site.camera_groups] + [json.loads(c.spec_json) for c in site.cameras]
    return rows
