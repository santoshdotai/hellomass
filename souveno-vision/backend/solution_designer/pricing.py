"""Commercial estimate with an editable pricing configuration.

All amounts are INR. GST is always shown separately. The output is a
preliminary estimate until the technical pilot has been completed.
"""
from __future__ import annotations

from copy import deepcopy

DEFAULT_PRICING: dict = {
    "currency": "INR",
    "gst_rate": 0.18,
    "technical_pilot_fee": 250_000,
    "pilot_max_cameras": 10,
    "pilot_max_use_cases": 3,
    "production_implementation_fee": 600_000,
    # Tiered per-camera monthly licence. `up_to` None = open-ended.
    "licence_tiers": [
        {"label": "First 50 active AI cameras", "up_to": 50, "rate_per_camera_month": 1500},
        {"label": "Cameras 51–150", "up_to": 150, "rate_per_camera_month": 1200},
        {"label": "Cameras 151 onward", "up_to": None, "rate_per_camera_month": 900},
    ],
    # Amount of the pilot fee credited against the production implementation
    # fee if the client proceeds. 0 = pilot is charged in full in addition.
    "pilot_credit_on_production": 0,
    "hardware_note": "Hardware (GPU server, switches, storage) is excluded and will be quoted after benchmarking.",
    "exclusions": [
        "Hardware — quoted after stream and GPU benchmarking",
        "Custom model training for client-specific objects or PPE classes",
        "External integrations (ERP, HRMS, access control, PA systems)",
        "New cameras, cabling, repositioning or lighting improvements",
    ],
}


def default_pricing() -> dict:
    return deepcopy(DEFAULT_PRICING)


def validate_pricing(cfg: dict) -> dict:
    """Merge a partial config over the defaults and sanity-check it."""
    merged = default_pricing()
    merged.update({k: v for k, v in cfg.items() if v is not None})
    if not 0 <= merged["gst_rate"] < 1:
        raise ValueError("gst_rate must be between 0 and 1")
    tiers = merged["licence_tiers"]
    if not tiers:
        raise ValueError("At least one licence tier is required")
    last_bound = 0
    for i, t in enumerate(tiers):
        if t["rate_per_camera_month"] < 0:
            raise ValueError("Tier rates must be non-negative")
        if t["up_to"] is None:
            if i != len(tiers) - 1:
                raise ValueError("Only the last tier may be open-ended")
        else:
            if t["up_to"] <= last_bound:
                raise ValueError("Tier upper bounds must be strictly increasing")
            last_bound = t["up_to"]
    for key in ("technical_pilot_fee", "production_implementation_fee", "pilot_credit_on_production"):
        if merged[key] < 0:
            raise ValueError(f"{key} must be non-negative")
    return merged


def tiered_monthly_licence(active_cameras: int, tiers: list[dict]) -> dict:
    """Split `active_cameras` across the tiers and price each slice."""
    if active_cameras < 0:
        raise ValueError("active_cameras must be non-negative")
    remaining = active_cameras
    lower = 0
    breakdown = []
    total = 0
    for t in tiers:
        upper = t["up_to"]
        slice_size = remaining if upper is None else max(0, min(remaining, upper - lower))
        amount = slice_size * t["rate_per_camera_month"]
        breakdown.append({
            "tier": t["label"],
            "cameras": slice_size,
            "rate_per_camera_month": t["rate_per_camera_month"],
            "monthly_amount": amount,
        })
        total += amount
        remaining -= slice_size
        if upper is not None:
            lower = upper
        if remaining <= 0:
            remaining = 0
    return {"active_cameras": active_cameras, "monthly_licence": total, "breakdown": breakdown}


def commercial_estimate(active_cameras: int, pricing: dict | None = None, include_pilot: bool = True) -> dict:
    cfg = validate_pricing(pricing or {})
    gst = cfg["gst_rate"]
    licence = tiered_monthly_licence(active_cameras, cfg["licence_tiers"])
    monthly = licence["monthly_licence"]
    annual = monthly * 12
    pilot_fee = cfg["technical_pilot_fee"] if include_pilot else 0
    pilot_credit = min(cfg["pilot_credit_on_production"], pilot_fee) if include_pilot else 0
    implementation = cfg["production_implementation_fee"]
    one_time_subtotal = pilot_fee + implementation - pilot_credit

    first_year_ex_gst = one_time_subtotal + annual
    second_year_ex_gst = annual

    def with_gst(x: float) -> dict:
        return {"ex_gst": round(x), "gst": round(x * gst), "incl_gst": round(x * (1 + gst))}

    return {
        "status": "PRELIMINARY ESTIMATE — valid only after the technical pilot is completed and stream/GPU benchmarks exist.",
        "currency": cfg["currency"],
        "gst_rate": gst,
        "active_ai_cameras": active_cameras,
        "licence_breakdown": licence["breakdown"],
        "monthly_licence": with_gst(monthly),
        "annual_licence": with_gst(annual),
        "technical_pilot": {
            **with_gst(pilot_fee),
            "included": include_pilot,
            "covers": f"up to {cfg['pilot_max_cameras']} cameras and {cfg['pilot_max_use_cases']} use cases",
        },
        "pilot_adjustment": {
            "description": "Pilot fee credited against production implementation" if pilot_credit else
                           "No pilot credit configured — pilot is charged in addition to implementation",
            "amount_ex_gst": -pilot_credit,
        },
        "one_time_implementation": with_gst(implementation),
        "one_time_total": with_gst(one_time_subtotal),
        "first_year_total": with_gst(first_year_ex_gst),
        "second_year_software_total": with_gst(second_year_ex_gst),
        "hardware": cfg["hardware_note"],
        "exclusions": cfg["exclusions"],
        "pricing_config_used": cfg,
    }
