"""Stall-layout engine: model a hall, score every stall, pick the best.

Two inputs are accepted:
  * a MODELLED layout generated from the venue's typical hall geometry
    (used until the organiser's plan arrives; every modelled layout says so)
  * a CUSTOM layout traced from the organiser's floor plan: the user marks
    the entrance, registration, food court, washrooms, anchor exhibitors,
    noisy zones and pillars, and clicks the candidate stalls.

Scoring (0-100) — the same rules the playbook states, made numeric:
  traffic     0-30  closeness to the entrance/registration (path length)
  aisle       0-20  on the main aisle (+20) or a cross aisle (+10)
  corner      0-20  open sides: 2 -> 15, 3+ -> 20
  anchor      0-10  within 15 m of an anchor exhibitor
  amenities   0-10  within 20 m of food court / washrooms (dwell traffic)
  base        10
  penalties   back wall -10, perimeter dead-end -5, noisy zone -10,
              pillar -8, farthest 20% of the hall -5
Distances are normalised by the hall diagonal, so pixel coordinates from a
traced plan work exactly like metres from a modelled one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------- model
@dataclass
class Stall:
    number: str
    x: float
    y: float
    w: float
    h: float
    open_sides: int = 1
    row: str = ""
    on_main_aisle: bool = False
    on_cross_aisle: bool = False
    back_wall: bool = False
    perimeter_end: bool = False

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass
class Layout:
    name: str
    width: float
    height: float
    units: str = "m"
    modelled: bool = True
    note: str = ""
    entrances: list[tuple[float, float]] = field(default_factory=list)
    registration: tuple[float, float] | None = None
    food_court: list[tuple[float, float]] = field(default_factory=list)
    washrooms: list[tuple[float, float]] = field(default_factory=list)
    anchors: list[dict[str, Any]] = field(default_factory=list)  # {name,x,y}
    noisy: list[tuple[float, float]] = field(default_factory=list)
    pillars: list[tuple[float, float]] = field(default_factory=list)
    aisles: list[dict[str, Any]] = field(default_factory=list)  # {x1,y1,x2,y2,main}
    stalls: list[Stall] = field(default_factory=list)

    @property
    def diagonal(self) -> float:
        return math.hypot(self.width, self.height)


def _d(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ---------------------------------------------------------------- generator
def generate_layout(name: str, hall_w: float, hall_h: float, stall: float = 3.0, aisle: float = 3.0, main_aisle: float = 5.0,
                    perimeter: float = 3.0, entrance_x: float | None = None, food_corner: str = "NE", washroom_corner: str = "NW",
                    anchors: list[dict[str, Any]] | None = None, noisy_zone: str | None = "N", pillars: list[tuple[float, float]] | None = None,
                    note: str = "", row_prefixes: str = "ABCDEFGHJKLMNPQRSTUVWXYZ") -> Layout:
    """Typical Indian shell-scheme hall: entrance on the south wall, a main
    aisle running north from it, rows of back-to-back 3 m stalls with 3 m
    aisles between them, numbering per row from the west."""
    ex = hall_w / 2 if entrance_x is None else entrance_x
    lay = Layout(name=name, width=hall_w, height=hall_h, note=note, entrances=[(ex, 0.0)], registration=(ex, perimeter / 2))
    corners = {"NE": (hall_w - 8, hall_h - 6), "NW": (8, hall_h - 6), "SE": (hall_w - 8, 6), "SW": (8, 6)}
    lay.food_court = [corners[food_corner]]
    lay.washrooms = [corners[washroom_corner]]
    lay.anchors = anchors or []
    lay.pillars = pillars or []
    if noisy_zone == "N":
        lay.noisy = [(hall_w * 0.25, hall_h - 8), (hall_w * 0.75, hall_h - 8)]
    lay.aisles.append({"x1": ex - main_aisle / 2, "y1": 0, "x2": ex + main_aisle / 2, "y2": hall_h, "main": True})
    # rows of double stalls: block = 2*stall deep, separated by `aisle`
    y = perimeter
    block = 2 * stall
    row_i = 0
    left_cols = int((ex - main_aisle / 2 - perimeter) // stall)
    right_cols = int((hall_w - (ex + main_aisle / 2) - perimeter) // stall)
    n_blocks = int((hall_h - 2 * perimeter + aisle) // (block + aisle))
    for b in range(n_blocks):
        for half in (0, 1):  # 0 = front row facing the aisle below (south), 1 = row facing the aisle above (north)
            prefix = row_prefixes[row_i % len(row_prefixes)]
            row_i += 1
            yy = y + half * stall
            num = 1
            for side, cols, x0 in (("L", left_cols, ex - main_aisle / 2 - left_cols * stall), ("R", right_cols, ex + main_aisle / 2)):
                for c in range(cols):
                    xx = x0 + c * stall
                    s = Stall(number=f"{prefix}{num:02d}", x=xx, y=yy, w=stall, h=stall, row=prefix)
                    end_west = side == "L" and c == 0
                    end_east = side == "R" and c == cols - 1
                    near_main = (side == "L" and c == cols - 1) or (side == "R" and c == 0)
                    s.open_sides = 1 + int(end_west or end_east) + int(near_main)
                    s.on_main_aisle = near_main
                    s.perimeter_end = end_west or end_east
                    s.back_wall = (b == n_blocks - 1 and half == 1)
                    # a cross aisle exists between blocks; the south-facing row of the first block faces the entrance concourse
                    s.on_cross_aisle = (half == 0 and b == 0)
                    lay.stalls.append(s)
                    num += 1
        cross_y = y + block + aisle / 2
        if b < n_blocks - 1:
            lay.aisles.append({"x1": perimeter, "y1": cross_y - aisle / 2, "x2": hall_w - perimeter, "y2": cross_y + aisle / 2, "main": False})
        y += block + aisle
    return lay


# ---------------------------------------------------------------- scoring
def score_stall(lay: Layout, s: Stall) -> dict[str, Any]:
    diag = lay.diagonal or 1.0
    c = (s.cx, s.cy)
    gate = min((_d(c, e) for e in lay.entrances), default=diag)
    reg = _d(c, lay.registration) if lay.registration else gate
    d_traffic = min(gate, reg) / diag  # 0 (at gate) .. ~1
    traffic = round(30 * max(0.0, 1 - d_traffic * 1.6), 1)
    aisle = 20 if s.on_main_aisle else (10 if s.on_cross_aisle else 0)
    corner = 20 if s.open_sides >= 3 else (15 if s.open_sides == 2 else 0)
    anchor = 0
    near_anchor = ""
    for a in lay.anchors:
        if _d(c, (a["x"], a["y"])) <= 15 * (diag / 100):
            anchor, near_anchor = 10, a.get("name", "anchor")
            break
    amen = 0
    if any(_d(c, p) <= 20 * (diag / 100) for p in lay.food_court + lay.washrooms):
        amen = 10
    reasons = []
    pen = 0
    if s.back_wall:
        pen -= 10; reasons.append("back wall")
    if s.perimeter_end and not s.on_main_aisle:
        pen -= 5; reasons.append("perimeter dead-end")
    if any(_d(c, n) <= 12 * (diag / 100) for n in lay.noisy):
        pen -= 10; reasons.append("next to noisy machinery zone")
    if any(_d(c, p) <= 2.5 * (diag / 100) for p in lay.pillars):
        pen -= 8; reasons.append("pillar blocks sight line")
    if d_traffic > 0.55:
        pen -= 5; reasons.append("far end of the hall")
    total = max(0, min(100, round(10 + traffic + aisle + corner + anchor + amen + pen)))
    pros = []
    if s.on_main_aisle:
        pros.append("on the main aisle from the entrance")
    if s.on_cross_aisle:
        pros.append("faces the entrance concourse / cross aisle")
    if s.open_sides >= 2:
        pros.append(f"corner, {s.open_sides} open sides")
    if traffic >= 20:
        pros.append("within the first third from the gate")
    if anchor:
        pros.append(f"near anchor {near_anchor}")
    if amen:
        pros.append("dwell traffic from food court / washrooms")
    return {"number": s.number, "score": total, "components": {"traffic": traffic, "aisle": aisle, "corner": corner, "anchor": anchor, "amenities": amen, "penalties": pen},
            "pros": pros, "cons": reasons, "x": s.x, "y": s.y, "w": s.w, "h": s.h, "open_sides": s.open_sides, "row": s.row}


def rank(lay: Layout) -> list[dict[str, Any]]:
    return sorted((score_stall(lay, s) for s in lay.stalls), key=lambda r: (-r["score"], r["number"]))


# ---------------------------------------------------------------- venue presets (modelled)
MODEL_NOTE = "MODELLED layout from the venue's typical hall geometry and last edition's zoning — not the organiser's plan. Upload the real floor plan to re-rank."

VENUE_MODELS: dict[str, dict[str, Any]] = {
    "bec-nesco": dict(name="Bombay Exhibition Centre (NESCO) — Hall 1 (modelled)", hall_w=120, hall_h=70, anchors=[{"name": "large processing-machinery anchor", "x": 75, "y": 22}, {"name": "association pavilion", "x": 45, "y": 22}], food_corner="NE", washroom_corner="NW"),
    "bharat-mandapam": dict(name="Bharat Mandapam — Hall 5 (modelled)", hall_w=100, hall_h=60, anchors=[{"name": "sponsor pavilion", "x": 62, "y": 20}], food_corner="NE", washroom_corner="SW"),
    "india-expo-mart": dict(name="India Expo Mart — Hall 9 (modelled)", hall_w=100, hall_h=60, anchors=[{"name": "switchgear major", "x": 62, "y": 20}, {"name": "cable major", "x": 38, "y": 20}], food_corner="NE", washroom_corner="SW"),
    "hitex": dict(name="HITEX — Hall 1 (modelled)", hall_w=100, hall_h=60, anchors=[{"name": "machine-tool anchor", "x": 62, "y": 20}, {"name": "sponsor pavilion", "x": 38, "y": 20}], food_corner="NE", washroom_corner="NW"),
    "gmdc-ground": dict(name="GMDC Ground, Ahmedabad — open-ground hangar (modelled)", hall_w=160, hall_h=90, entrance_x=60, anchors=[{"name": "machinery anchor", "x": 95, "y": 24}], food_corner="SE", washroom_corner="NW"),
    "piecc-moshi": dict(name="PIECC Moshi, Pune — main hall (modelled)", hall_w=120, hall_h=80, anchors=[{"name": "automation anchor", "x": 75, "y": 24}, {"name": "fastener pavilion", "x": 45, "y": 24}], food_corner="NE", washroom_corner="NW"),
    "vanita-vishram": dict(name="Vanita Vishram Ground, Surat — hangar (modelled)", hall_w=120, hall_h=70, anchors=[{"name": "textile-machinery anchor", "x": 75, "y": 22}], food_corner="SE", washroom_corner="NW"),
    "jecc": dict(name="JECC Sitapura, Jaipur — Hall A (modelled)", hall_w=100, hall_h=60, anchors=[{"name": "stone-machinery anchor", "x": 62, "y": 20}], food_corner="NE", washroom_corner="SW"),
    "yashobhoomi": dict(name="Yashobhoomi IICC, Dwarka — Hall 1 (modelled)", hall_w=110, hall_h=70, anchors=[{"name": "racking/automation anchor", "x": 70, "y": 22}], food_corner="NE", washroom_corner="NW"),
    "biec": dict(name="BIEC Bengaluru — Hall 3 (modelled)", hall_w=110, hall_h=70, anchors=[{"name": "robotics anchor", "x": 70, "y": 22}], food_corner="NE", washroom_corner="NW"),
}

EVENT_VENUE = {
    "plastivision-2027": "bec-nesco", "fastener-fair-india-2027": "bec-nesco", "automation-expo-2027": "bec-nesco", "indexpo-mumbai-2027": "bec-nesco",
    "elecrama-2027": "india-expo-mart",
    "acetech-hyderabad-2027": "hitex", "indexpo-hyderabad-2027": "hitex", "papexpo-2026": "hitex", "waremat-2026": "hitex", "india-pharma-expo-2027": "hitex",
    "engiexpo-ahmedabad-2026": "gmdc-ground", "engiexpo-pune-2026": "piecc-moshi", "engiexpo-surat-2027": "vanita-vishram", "engiexpo-jaipur-2027": "jecc",
    "india-warehousing-show-2027": "yashobhoomi", "ifsec-india-2026": "bharat-mandapam", "hardware-fair-india-2026": "bharat-mandapam",
    "startup-mahakumbh-2027": "bharat-mandapam", "convergence-india-2027": "bharat-mandapam",
    "india-automation-robotics-2027": "biec", "imtex-2027": "biec", "bts-2026": "biec",
}


def layout_for_event(event_id: str) -> Layout | None:
    key = EVENT_VENUE.get(event_id)
    if not key:
        return None
    cfg = dict(VENUE_MODELS[key])
    return generate_layout(note=MODEL_NOTE, **cfg)


def layout_from_dict(d: dict[str, Any]) -> Layout:
    lay = Layout(name=d.get("name", "custom"), width=float(d["width"]), height=float(d["height"]), units=d.get("units", "px"), modelled=False,
                 note=d.get("note", "traced from the organiser's floor plan"),
                 entrances=[tuple(p) for p in d.get("entrances", [])], registration=tuple(d["registration"]) if d.get("registration") else None,
                 food_court=[tuple(p) for p in d.get("food_court", [])], washrooms=[tuple(p) for p in d.get("washrooms", [])],
                 anchors=list(d.get("anchors", [])), noisy=[tuple(p) for p in d.get("noisy", [])], pillars=[tuple(p) for p in d.get("pillars", [])],
                 aisles=list(d.get("aisles", [])))
    for s in d.get("stalls", []):
        lay.stalls.append(Stall(number=str(s["number"]), x=float(s["x"]), y=float(s["y"]), w=float(s.get("w", 3)), h=float(s.get("h", 3)),
                                open_sides=int(s.get("open_sides", 1)), on_main_aisle=bool(s.get("on_main_aisle", False)),
                                on_cross_aisle=bool(s.get("on_cross_aisle", False)), back_wall=bool(s.get("back_wall", False)),
                                perimeter_end=bool(s.get("perimeter_end", False))))
    if not lay.entrances:
        lay.entrances = [(lay.width / 2, 0.0)]
    return lay


def layout_to_dict(lay: Layout, ranked: list[dict[str, Any]] | None = None, top: int = 5) -> dict[str, Any]:
    ranked = ranked or rank(lay)
    return {
        "name": lay.name, "width": lay.width, "height": lay.height, "units": lay.units, "modelled": lay.modelled, "note": lay.note,
        "entrances": lay.entrances, "registration": lay.registration, "food_court": lay.food_court, "washrooms": lay.washrooms,
        "anchors": lay.anchors, "noisy": lay.noisy, "pillars": lay.pillars, "aisles": lay.aisles,
        "stall_count": len(lay.stalls), "top": ranked[:top], "ranked": ranked,
        "avoid": [r for r in ranked[-5:]][::-1],
    }


# ---------------------------------------------------------------- SVG
def _heat(score: int) -> str:
    # 0 -> muted, 100 -> saturated orange; keep the top band clearly distinct
    if score >= 80:
        return "#D8781A"
    if score >= 65:
        return "#E9A65A"
    if score >= 50:
        return "#F2C89A"
    if score >= 35:
        return "#E8E1D3"
    return "#D9D2C4"


def to_svg(lay: Layout, ranked: list[dict[str, Any]] | None = None, top: int = 5, width_px: int = 720) -> str:
    ranked = ranked or rank(lay)
    scores = {r["number"]: r["score"] for r in ranked}
    top_nums = {r["number"] for r in ranked[:top]}
    k = width_px / lay.width
    H = lay.height * k
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -18 {width_px} {H + 44}" width="100%" role="img" aria-label="{lay.name}" style="max-width:100%;font-family:IBM Plex Sans,system-ui,sans-serif">']
    out.append(f'<rect x="0" y="0" width="{width_px}" height="{H:.1f}" fill="#FBF9F4" stroke="#8A8171" stroke-width="2"/>')
    for a in lay.aisles:
        out.append(f'<rect x="{a["x1"]*k:.1f}" y="{H - a["y2"]*k:.1f}" width="{(a["x2"]-a["x1"])*k:.1f}" height="{(a["y2"]-a["y1"])*k:.1f}" fill="{"#F0E6D2" if a.get("main") else "#F6F1E7"}"/>')
    for s in lay.stalls:
        sc = scores.get(s.number, 0)
        out.append(f'<rect x="{s.x*k+0.5:.1f}" y="{H-(s.y+s.h)*k+0.5:.1f}" width="{s.w*k-1:.1f}" height="{s.h*k-1:.1f}" fill="{_heat(sc)}" stroke="#fff" stroke-width="0.6"><title>{s.number}: {sc}/100</title></rect>')
    for s in lay.stalls:
        if s.number in top_nums:
            out.append(f'<text x="{s.cx*k:.1f}" y="{H-s.cy*k+3:.1f}" font-size="9" font-weight="700" text-anchor="middle" fill="#1a1004">{s.number}</text>')
    for (x, y) in lay.entrances:
        out.append(f'<rect x="{x*k-14:.1f}" y="{H-4:.1f}" width="28" height="8" fill="#1E7F7A"/><text x="{x*k:.1f}" y="{H+18:.1f}" font-size="10" text-anchor="middle" fill="#1E7F7A">ENTRANCE</text>')
    if lay.registration:
        out.append(f'<text x="{lay.registration[0]*k:.1f}" y="{H-lay.registration[1]*k+3:.1f}" font-size="8" text-anchor="middle" fill="#1E7F7A">REG</text>')
    for (x, y) in lay.food_court:
        out.append(f'<text x="{x*k:.1f}" y="{H-y*k:.1f}" font-size="9" text-anchor="middle" fill="#4A5468">FOOD</text>')
    for (x, y) in lay.washrooms:
        out.append(f'<text x="{x*k:.1f}" y="{H-y*k:.1f}" font-size="9" text-anchor="middle" fill="#4A5468">WC</text>')
    for a in lay.anchors:
        out.append(f'<circle cx="{a["x"]*k:.1f}" cy="{H-a["y"]*k:.1f}" r="5" fill="none" stroke="#B8342B" stroke-width="2"/><text x="{a["x"]*k+7:.1f}" y="{H-a["y"]*k+3:.1f}" font-size="8" fill="#B8342B">{a.get("name","anchor")}</text>')
    for (x, y) in lay.noisy:
        out.append(f'<text x="{x*k:.1f}" y="{H-y*k:.1f}" font-size="8" text-anchor="middle" fill="#8A4A0B">NOISY</text>')
    for (x, y) in lay.pillars:
        out.append(f'<rect x="{x*k-2:.1f}" y="{H-y*k-2:.1f}" width="4" height="4" fill="#141A26"/>')
    out.append(f'<text x="4" y="-6" font-size="10" fill="#4A5468">{lay.name} · {lay.width:.0f}×{lay.height:.0f} {lay.units} · {len(lay.stalls)} stalls · darker = better</text>')
    out.append("</svg>")
    return "".join(out)


def recommend(event_id: str, top: int = 5) -> dict[str, Any] | None:
    lay = layout_for_event(event_id)
    if not lay:
        return None
    ranked = rank(lay)
    d = layout_to_dict(lay, ranked, top)
    d["svg"] = to_svg(lay, ranked, top)
    d["event_id"] = event_id
    return d
