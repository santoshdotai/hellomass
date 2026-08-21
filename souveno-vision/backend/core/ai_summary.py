"""SOUVENO AI Summary (Phase 21) + SOUVENO AI Reasoning foundation (Stage 7).

Two-stage design, always in this order:
  1. Deterministic statistics computed directly from detected events/metrics.
  2. A natural-language interpretation layered on top of ONLY those numbers
     — via an LLM if LLM_API_KEY is configured, otherwise a rule-based
     template. The demo must work with zero paid API calls, so the
     rule-based path is the real fallback, not a stub.

The LLM is never allowed to invent events: it receives only the structured
`stats` dict below as context and is instructed accordingly.
"""
from __future__ import annotations

from config.settings import settings
from backend.core.events import format_hms


def build_stats(duration_seconds: float, metrics_snapshot: dict, events: list[dict]) -> dict:
    agg = metrics_snapshot["aggregate"]
    biz = metrics_snapshot["business_metrics"]

    event_type_counts: dict[str, int] = {}
    for e in events:
        event_type_counts[e["event_type"]] = event_type_counts.get(e["event_type"], 0) + 1

    # Busiest window: bucket queue-related/warning events into 2-minute windows.
    busiest_window = _find_busiest_window(events)

    longest_table_delay = max(
        (e for e in events if e["event_type"] == "POTENTIAL_TABLE_CLEARING_DELAY"),
        key=lambda e: e.get("duration_seconds") or 0,
        default=None,
    )

    return {
        "video_duration_label": format_hms(duration_seconds),
        "video_duration_seconds": duration_seconds,
        "peak_people_visible": agg["peak_people"],
        "peak_queue": agg["peak_queue"],
        "average_queue_dwell_label": format_hms(agg["average_queue_dwell_seconds"]),
        "potential_queue_abandonments": agg["potential_abandonments"],
        "potential_idle_staff_events": agg["potential_idle_staff_events"],
        "total_potential_idle_time_label": format_hms(agg["potential_idle_staff_minutes"] * 60),
        "table_clearing_delay_events": agg["table_clearing_delay_events"],
        "potential_pickup_delays": agg["potential_pickup_delays"],
        "visible_spill_events": agg["visible_spill_events"],
        "footfall": agg["footfall"],
        "tables_occupied_at_end": biz["tables_occupied"],
        "event_type_counts": event_type_counts,
        "busiest_window_label": busiest_window,
        "longest_table_delay_zone": (longest_table_delay or {}).get("zone_id"),
        "longest_table_delay_seconds": (longest_table_delay or {}).get("duration_seconds"),
    }


def _find_busiest_window(events: list[dict], window_seconds: int = 120) -> str | None:
    queue_events = [e for e in events if e["event_type"] in ("QUEUE_WARNING", "QUEUE_CRITICAL")]
    if not queue_events:
        return None
    buckets: dict[int, int] = {}
    for e in queue_events:
        bucket = int(e["start_time"] // window_seconds)
        buckets[bucket] = buckets.get(bucket, 0) + 1
    busiest_bucket = max(buckets, key=buckets.get)
    start = busiest_bucket * window_seconds
    end = start + window_seconds
    return f"{format_hms(start)}–{format_hms(end)}"


def generate_rule_based_summary(stats: dict) -> str:
    lines = ["SOUVENO AI OPERATIONS SUMMARY", ""]
    lines.append(f"Video analysed: {stats['video_duration_label']}")
    lines.append(f"Peak people visible: {stats['peak_people_visible']}")
    lines.append(f"Peak queue: {stats['peak_queue']}")
    lines.append(f"Average queue dwell: {stats['average_queue_dwell_label']}")
    lines.append(f"Potential queue abandonments: {stats['potential_queue_abandonments']}")
    lines.append(f"Potential idle staff events: {stats['potential_idle_staff_events']}")
    lines.append(f"Total potential idle time: {stats['total_potential_idle_time_label']}")
    lines.append(f"Table clearing delay events: {stats['table_clearing_delay_events']}")
    lines.append("")

    concerns = []
    if stats["potential_idle_staff_events"] >= 2:
        concerns.append("the preparation zone, where multiple low-activity periods were detected")
    if stats["table_clearing_delay_events"] >= 2:
        concerns.append("table turnover, with several tables left uncleared after customers departed")
    if stats["potential_queue_abandonments"] >= 1:
        concerns.append("checkout queueing, where at least one customer appears to have left before being served")
    if stats["visible_spill_events"] >= 1:
        concerns.append("an experimental spill detection near the beverage counter (unverified — review footage)")

    if concerns:
        lines.append(f"The largest operational concern in this session was {concerns[0]}.")
        if len(concerns) > 1:
            lines.append("Additional areas worth reviewing: " + "; ".join(concerns[1:]) + ".")
    else:
        lines.append("No significant operational concerns were detected in this session.")

    if stats["busiest_window_label"]:
        lines.append(f"The counter experienced its highest congestion between {stats['busiest_window_label']}.")

    if stats["longest_table_delay_zone"]:
        lines.append(
            f"{stats['longest_table_delay_zone']} had the longest clearing delay "
            f"({format_hms(stats['longest_table_delay_seconds'] or 0)})."
        )

    lines.append("")
    lines.append("Recommendation:")
    recs = []
    if stats["potential_idle_staff_events"] >= 2:
        recs.append("review staff deployment during low-demand periods")
    if stats["table_clearing_delay_events"] >= 1:
        recs.append("reduce table clearing response time during peak occupancy")
    if stats["potential_queue_abandonments"] >= 1:
        recs.append("add counter coverage during the busiest queue windows")
    if not recs:
        recs.append("continue current staffing patterns — no material issues detected in this session")
    lines.append(" and ".join(recs).capitalize() + ".")

    lines.append("")
    lines.append("(Generated by rule-based analysis — no LLM configured. This summary strictly reflects "
                  "detected events; it is not a substitute for on-site review.)")
    return "\n".join(lines)


def generate_llm_summary(stats: dict) -> str | None:
    """Returns None if no LLM is configured/available, so the caller can
    fall back to the rule-based summary — the demo must never depend on
    a paid API being reachable."""
    if not settings.llm_api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None

    prompt = f"""You are SOUVENO AI, an operations analyst for a cafe. You are given ONLY the
structured metrics below, extracted from computer-vision analysis of one recorded video session.
Do not invent any event, number, or zone that is not present in this data. Write a concise,
management-style operations summary (150-220 words) in the exact structure:

SOUVENO AI OPERATIONS SUMMARY

<statistics recap, one line per metric>

<2-4 sentences of interpretation, referencing only the data given>

Recommendation:
<1-3 sentences of actionable recommendation>

DATA:
{stats}
"""
    try:
        client = anthropic.Anthropic(api_key=settings.llm_api_key)
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if hasattr(block, "text"))
    except Exception:
        return None


def generate_summary(duration_seconds: float, metrics_snapshot: dict, events: list[dict]) -> dict:
    stats = build_stats(duration_seconds, metrics_snapshot, events)
    llm_text = generate_llm_summary(stats)
    if llm_text:
        return {"stats": stats, "summary_text": llm_text, "generated_by": "llm"}
    return {"stats": stats, "summary_text": generate_rule_based_summary(stats), "generated_by": "rule_based"}
