"""REST API for the Solution Designer — mounted under /api/designer."""
from __future__ import annotations

import io
import json

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.solution_designer import csv_io, pricing, storage
from backend.solution_designer.catalog import CODECS, GPU_CATALOG, RESOLUTIONS, USE_CASES
from backend.solution_designer.engine import run_assessment
from backend.solution_designer.report import export_capabilities, render_docx, render_html, render_pdf
from backend.solution_designer.sample import sample_request
from backend.solution_designer.schemas import AssessmentRequest, PricingConfigIn

router = APIRouter(prefix="/api/designer", tags=["solution-designer"])

_PRICING_KEY = "designer.pricing"


# ---------------------------------------------------------------- reference data
@router.get("/catalog")
def catalog():
    return {
        "use_cases": [{"id": k, **v} for k, v in USE_CASES.items()],
        "codecs": CODECS,
        "resolutions": {k: {"width": v[0], "height": v[1], "megapixels": v[2]} for k, v in RESOLUTIONS.items()},
        "gpus": GPU_CATALOG,
        "export_capabilities": export_capabilities(),
    }


# ---------------------------------------------------------------- pricing config
def _load_pricing(db: Session) -> dict:
    from backend.db import models as core_models
    row = db.query(core_models.Setting).filter(core_models.Setting.key == _PRICING_KEY).first()
    if row and row.value:
        try:
            return pricing.validate_pricing(json.loads(row.value))
        except (ValueError, json.JSONDecodeError):
            pass
    return pricing.default_pricing()


@router.get("/pricing")
def get_pricing(db: Session = Depends(get_db)):
    return {"pricing": _load_pricing(db), "defaults": pricing.default_pricing()}


@router.put("/pricing")
def put_pricing(payload: PricingConfigIn, db: Session = Depends(get_db)):
    from backend.db import models as core_models
    try:
        cfg = pricing.validate_pricing(payload.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, str(e))
    row = db.query(core_models.Setting).filter(core_models.Setting.key == _PRICING_KEY).first()
    if not row:
        row = core_models.Setting(key=_PRICING_KEY)
        db.add(row)
    row.value = json.dumps(cfg)
    db.commit()
    return {"pricing": cfg}


@router.post("/pricing/reset")
def reset_pricing(db: Session = Depends(get_db)):
    from backend.db import models as core_models
    db.query(core_models.Setting).filter(core_models.Setting.key == _PRICING_KEY).delete()
    db.commit()
    return {"pricing": pricing.default_pricing()}


@router.get("/pricing/estimate")
def quick_estimate(active_cameras: int = Query(..., ge=0, le=100000), include_pilot: bool = True,
                   db: Session = Depends(get_db)):
    return pricing.commercial_estimate(active_cameras, _load_pricing(db), include_pilot)


# ---------------------------------------------------------------- assessments
@router.post("/assessments/preview")
def preview_assessment(payload: AssessmentRequest, db: Session = Depends(get_db)):
    """Run the engine without persisting — used by the UI while editing."""
    if payload.pricing_overrides is None:
        payload.pricing_overrides = _load_pricing(db)
    return run_assessment(payload)


@router.post("/assessments")
def create_assessment(payload: AssessmentRequest, db: Session = Depends(get_db)):
    if payload.pricing_overrides is None:
        payload.pricing_overrides = _load_pricing(db)
    result = run_assessment(payload)
    html = render_html(result)
    asmt = storage.save_assessment(db, payload, result, html)
    result["id"] = asmt.id
    result["assessment_uid"] = asmt.assessment_uid
    return result


@router.get("/assessments")
def list_assessments(db: Session = Depends(get_db)):
    return {"assessments": storage.list_assessments(db)}


@router.get("/assessments/{assessment_id}")
def get_assessment(assessment_id: int, db: Session = Depends(get_db)):
    data = storage.load_assessment(db, assessment_id)
    if not data:
        raise HTTPException(404, "Assessment not found")
    return data


@router.get("/assessments/{assessment_id}/report")
def get_report(assessment_id: int, format: str = "html", db: Session = Depends(get_db)):
    from backend.solution_designer import models as m
    asmt = db.query(m.Assessment).filter(m.Assessment.id == assessment_id).first()
    if not asmt or not asmt.proposals:
        raise HTTPException(404, "Assessment or proposal not found")
    proposal = asmt.proposals[-1]
    if format == "html":
        return HTMLResponse(proposal.report_html)
    caps = export_capabilities()
    if format not in ("docx", "pdf"):
        raise HTTPException(400, "format must be html, docx or pdf")
    if not caps.get(format):
        raise HTTPException(501, f"{format.upper()} export needs the optional '{'python-docx' if format == 'docx' else 'weasyprint'}' "
                                 "package, which is not installed. Use the HTML report and print to PDF from the browser.")
    # Re-run to rebuild the full dict (only the HTML is stored verbatim).
    req = AssessmentRequest(**json.loads(asmt.input_json))
    result = run_assessment(req)
    if format == "docx":
        return Response(render_docx(result), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f"attachment; filename=souveno-solution-design-{assessment_id}.docx"})
    return Response(render_pdf(result), media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=souveno-solution-design-{assessment_id}.pdf"})


@router.get("/sample")
def sample():
    """The built-in 348-camera sample request, for the UI 'Load sample' button."""
    return sample_request().model_dump()


# ---------------------------------------------------------------- CSV
@router.get("/cameras/csv-template", response_class=PlainTextResponse)
def csv_template():
    return PlainTextResponse(csv_io.template_csv(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=camera-inventory-template.csv"})


@router.post("/cameras/import")
async def import_cameras(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV must be UTF-8 encoded")
    cameras, errors = csv_io.parse_csv(text)
    return {"cameras": [c.model_dump() for c in cameras], "errors": errors,
            "imported": len(cameras), "rejected": len(errors)}


@router.get("/sites/{site_id}/cameras.csv")
def export_site_cameras(site_id: int, db: Session = Depends(get_db)):
    rows = storage.site_cameras_for_export(db, site_id)
    if not rows:
        raise HTTPException(404, "Site not found or has no camera inventory")
    return PlainTextResponse(csv_io.to_csv(rows), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=site-{site_id}-cameras.csv"})
