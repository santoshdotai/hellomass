"""Souveno Vision Solution Designer.

Collects structured information about a prospective client's CCTV
environment and produces a technically responsible AI-video-analytics
solution: deterministic calculators, compatibility rules, camera
suitability scoring, a pilot design, a risk register, a preliminary
commercial estimate and a client-facing report.

Design rules (enforced in code, not in prompts):
  * every formula lives in `calculators.py` and is echoed back with its
    assumptions — nothing numeric is delegated to an LLM;
  * missing inputs are never guessed — they are reported as
    "Site validation required";
  * GPU capacity is never asserted without benchmark evidence.
"""
