# Client Pilot Plan — Souveno Vision Intelligence

**Client context:** ~348 existing CCTV cameras, ~1,000 employees.
**Goal of the pilot:** prove measurable operational value on a small, representative subset of the
existing cameras, quantify accuracy and false alerts, and measure compute cost per stream — so that
a scale-up proposal is based on evidence. **No 348-camera performance, accuracy or cost guarantee
is given before the pilot.**

## Scope

| Item | Proposal |
|---|---|
| Cameras | **8–12 existing cameras**, chosen after the compatibility audit (prefer class A/B) |
| Areas | **Two representative operational areas**, e.g. (1) a plant entrance / material gate, (2) a restricted machine bay or hazardous store |
| Use cases | **Two or three measurable ones:** restricted-zone intrusion; entry/exit counting → occupancy; dwell/loitering in a restricted or high-value area. Optional: after-hours presence |
| Identity | **Anonymous tracking only** — no face recognition, no names, camera-local IDs |
| Processing | **On-premise** edge PC/server in the client's network (GPU recommended for > 4 streams) |
| Duration | 6–8 weeks: 1 week audit & setup, 1 week zone/rule tuning, 3–4 weeks measurement, 1 week report |
| Integration | Webhook to the client's preferred channel (WhatsApp / e-mail / Teams) for one alert type |

## Work plan

1. **Camera compatibility audit** (docs/CAMERA_AUDIT.md) of 20–30 candidate cameras → pick 8–12.
   Record access method per camera (RTSP / ONVIF / NVR API / SDK) — not all cameras support RTSP.
2. **Install** the edge node, read-only NVR/camera credentials, camera VLAN routing, dashboard on
   the client's operator PC.
3. **Configure** zones, lines, business hours and thresholds with the area supervisors; agree
   severities and who receives what.
4. **Ground-truth validation**: for each camera, sample 2–4 hours of footage across shifts; a human
   annotates true intrusions/crossings/dwell episodes. Compare with system events.
5. **Accuracy & false-alert measurement** (per camera and per use case):
   precision, recall, false alerts per hour, counting error (%), median time-to-alert.
   Targets to *aim for*, set with the client: counting error ≤ 10 %, intrusion recall ≥ 90 %,
   false alerts ≤ 2 per camera per shift. Results are reported as measured, not assumed.
6. **Compute benchmarking**: per-stream decode + inference cost at the chosen FPS/resolution/model,
   streams per CPU core / per GPU, memory, disk growth per day, network load. Both CPU-only and GPU
   configurations if hardware permits.
7. **Operational review**: how operators use acknowledgements, which alerts are actionable, what
   gets dismissed and why; adjust cooldowns and schedules.
8. **Scale-up report**: audited camera classes for all 348 cameras (extrapolated from the audit
   sample + full audit where feasible), recommended stream settings, node count and GPU class,
   licensing plan (see LICENSING.md), integration plan (NVR/VMS API vs RTSP), storage and retention,
   phased rollout (e.g. 50 → 150 → 348), and the measured accuracy per use case that the client can
   expect — with the explicit statement that sizing depends on streams, resolution, FPS, codec,
   model and latency, not camera count alone.

## Deliverables

* Audit sheet for all tested cameras (class A–D with fixes).
* Configured pilot system with 8–12 cameras and tuned rules.
* Weekly event/KPI export (CSV) and a final accuracy & false-alert report.
* Compute benchmark table (streams per node, latency, utilisation).
* Scale-up proposal with phased plan, hardware options and licensing costs.
* Privacy pack: privacy notice draft, retention policy, RBAC requirements.

## Client responsibilities

* Read-only credentials and VLAN access for the pilot cameras; a network contact.
* An operator/supervisor per area for zone definition and alert review (2–3 h/week).
* Employee communication / policy review with HR before live alerts start.

## Exit criteria

The pilot is successful if the agreed use cases meet the measured targets on the pilot cameras and
the operators find the alerts actionable. Only then is a 348-camera proposal written.
