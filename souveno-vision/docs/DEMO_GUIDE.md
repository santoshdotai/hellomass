# Souveno Vision Intelligence — Client Demo Guide

**Product:** SOUVENO AI · Souveno Vision Intelligence · *“Existing Cameras. Operational Intelligence.”*
**Positioning:** an intelligence layer for existing CCTV infrastructure. The camera provides video;
Souveno converts it into operational events, alerts, evidence and management insights.

This is a single/few-stream proof of concept to validate use cases before hardware sizing. It does
**not** process 348 cameras; the pilot benchmarks real streams first (see `CLIENT_PILOT_PLAN.md`).

## Before the meeting (15 minutes)

1. Laptop on mains power, Wi-Fi off if not needed, notifications silenced, screen never sleeps.
2. `cd souveno-vision`, activate the venv, run `python app.py`. The browser opens at
   `http://127.0.0.1:8501`. Check the top bar shows **AI: ultralytics-yolo** once a source runs
   (if it says `opencv-hog (fallback)`, PyTorch/Ultralytics failed to install — see README troubleshooting).
3. Open **Demo Mode** → **Start Recorded Factory Demo** → confirm boxes and `Person N` labels appear.
   Stop it again (Dashboard → Stop) so the demo starts clean.
4. Open **Demo Mode** → **Start Webcam Demo** once to confirm the webcam is free (close Teams/Zoom).
   Press **Enable Restricted Zone** so the demo layout (restricted area on the right, entry line in
   the middle, work area on the left) is saved for the webcam. Adjust it in Settings → Zone editor
   if the room needs it. Stop the source.
5. Settings → Detection: confirm **Dwell threshold** = 10 s and working hours match the local time
   (or the “after hours” rule will fire during the demo — which can also be a talking point).
6. Optional: Settings → Rules → untick *Line crossed inward/outward* **notify** so the event panel
   stays focused on alerts. Event History → **Clear** filters. Health → check disk free.
7. Have a colleague ready to walk in front of the webcam.

## Presentation sequence (strict order, ~5 minutes)

| # | Action | Say |
|---|---|---|
| 1 | Open **Dashboard** | “This is the operator view: live video with AI overlays, KPIs, and the alert panel. Everything runs on this laptop, nothing goes to the cloud.” |
| 2 | **Demo Mode → Start Recorded Factory Demo** | “Recorded footage first. Every person gets a temporary anonymous ID — `Person 12` — no faces, no names. Counts update live.” |
| 3 | **Start Webcam Demo** | “Now the same intelligence on a live camera. In production this is your RTSP camera or NVR channel.” |
| 4 | **Enable Restricted Zone** (or draw it in Settings → Zone editor) | “Zones are drawn once per camera in normalised coordinates, so they survive resolution changes.” |
| 5 | Colleague steps into the restricted zone | Point at the red box and the new **HIGH** card: “Restricted-zone intrusion: timestamp, camera, zone, person ID, snapshot.” |
| 6 | Show the alert card / click the thumbnail | “Evidence is saved locally with the overlays; a short before/after clip follows a few seconds later.” |
| 7 | Colleague stays in the zone ≥ 10 s (or press **Trigger / Verify Dwell Alert** to lower the threshold to 6 s for 2 minutes) | “Dwell / loitering: someone staying too long in a place they should pass through.” |
| 8 | Show the dwell-time alert | “Medium severity by default; every rule has its own severity, cooldown, schedule and evidence setting.” |
| 9 | Colleague crosses the virtual line (arrow shows the *in* direction) | “Directional line crossing with jitter protection — no double counting.” |
| 10 | Point at **Entries / Exits / Current occupancy** | “Counts feed occupancy, shift reports and safety thresholds.” |
| 11 | **Open Event History** | “Filter by date, camera, type, severity, status. Export to CSV for management.” |
| 12 | Press **Acknowledge** on an event, add a note | “Acknowledgement is audited: who, when, note — the start of an operator workflow.” |
| 13 | Click **snapshot** / **clip** | “Evidence lives on premise with configurable retention and automatic cleanup.” |
| 14 | Settings → Video source → **RTSP / NVR** tab (do not type real credentials on screen) | “The webcam is a stand-in. In production the source is RTSP, ONVIF discovery, the NVR/VMS API, or a vendor SDK — not every camera speaks RTSP, and the **Camera Audit** page grades each one A–D.” |
| 15 | **Privacy** page / closing | “The pilot benchmarks 8–12 of your existing cameras, measures accuracy and false alerts, and only then do we size hardware for 348 cameras. Sizing depends on streams, resolution, FPS, codec, model and latency — not camera count alone.” |

## Recovery during the demo

* **Webcam busy / black:** close Teams/Zoom/browser camera tabs, then **Start Webcam Demo** again; or
  continue with **Start Recorded Factory Demo**.
* **No alert fires:** check the zone actually covers where the person stands (foot point = bottom
  centre of the box), confidence slider ≤ 0.4, and that the rule is enabled (Settings → Rules).
* **Too many alerts:** press **Reset Counts**; raise cooldowns in Settings → Rules.
* **Camera disconnected banner (RTSP):** the app reconnects automatically with back-off; the
  dashboard never freezes. Switch to the recorded demo if the network is down.
* **Everything else:** `Ctrl+C` in the terminal, `python app.py` again — startup is ~10 s.

## Key sentences to repeat

* “Anonymous, camera-local IDs. No facial recognition. No employee names.”
* “On-premise. The video never leaves your network.”
* “We validate on your cameras before we size anything.”
