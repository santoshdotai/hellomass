"""Build the phone command-center HTML from the frontend template + live engine data.

    python scripts/build_dashboard.py ../expo-frontend/dashboard/command_center_template.html \
        ../expo-frontend/dashboard/souveno-expo-command-center.html
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.core.expo import finance, floorplan, planner, scoring, subsidy  # noqa: E402
from backend.core.expo import funds as fe  # noqa: E402
from backend.core.expo import applications as ae  # noqa: E402
from backend.core.expo.catalog import list_events, meta  # noqa: E402
from backend.core.expo.playbook import playbook  # noqa: E402


def build() -> dict:
    evs = list_events()
    rows = []
    for e in evs:
        r = scoring.evaluate(e)
        tp = planner.travel_plan(e)
        rows.append({**{k: e[k] for k in ("id", "name", "edition", "category", "icp", "start", "end", "city", "venue", "venue_area", "organiser", "website", "mode", "tentative", "footfall_history", "expected", "why", "stall") if k in e},
                     "icp_vision": e.get("icp_vision", []), "stars": r["stars"], "total": r["total_score"], "lead_product": r["lead_product"], "quote_fit": r["quote_fit"], "vision_fit": r["vision_fit"],
                     "components": r["components"], "explain": r["explain"], "funnel": r["funnel"], "funnel_alt": r["funnel_alt"], "budget": r["budget"], "cpc": r["cost_per_expected_client_inr"],
                     "travel": tp, "hotels": (e.get("travel") or {}).get("hotels", []), "airport": (e.get("travel") or {}).get("airport"), "fare": (e.get("travel") or {}).get("flight_oneway_inr", [0, 0]),
                     "contact": e.get("exhibitor_contact"), "subsidy": subsidy.for_event(e), "competitors": e.get("competitors", [])})
    plans = {}
    for e in evs:
        if e["mode"] != "exhibit":
            continue
        rec = floorplan.recommend(e["id"])
        lay = floorplan.layout_for_event(e["id"])
        if rec and lay:
            plans[e["id"]] = {"svg": rec.get("svg") or floorplan.to_svg(lay), "top": rec.get("top", []), "avoid": rec.get("avoid", []), "stall_count": rec.get("stall_count", len(lay.stalls)), "name": rec.get("name", lay.name)}
    m = meta()
    return {"meta": {"prepared_on": date.today().isoformat(), "icp": m.get("icp_segments"), "icp_segments": m.get("icp_segments"), "assumptions": m.get("funnel_assumptions"),
                     "company": {**planner.SOUVENO_PROFILE, "company_email": "souveno30@gmail.com", "travel_email": "santoshdotai@gmail.com", "payment": "Souveno current account"}},
            "events": rows, "itinerary": planner.attend_all_itinerary(evs), "clashes": planner.clashes(evs), "playbook": playbook(), "floorplans": plans,
            "finance": finance.all_horizons(), "funds": fe.funds("all"), "pavilions": fe.pavilions(), "applications": ae.applications()}


if __name__ == "__main__":
    tpl, out = Path(sys.argv[1]), Path(sys.argv[2])
    html = tpl.read_text(encoding="utf-8").replace("__DATA__", json.dumps(build(), ensure_ascii=False, separators=(",", ":")))
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
