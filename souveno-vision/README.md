# SOUVENO VISION — Café Intelligence Demo

**See. Understand. Act. Measure.**

SOUVENO VISION turns a recorded café video into operational business intelligence: anonymous
person/object detection and tracking, zone-based business events (queues, idle staff, table
turnover, pickup delays), live metrics, and an end-of-video AI operations summary — all running
locally on your machine, no cloud required.

> **Privacy by design:** anonymous tracking IDs only (e.g. "Person #014"). No facial recognition,
> no names, no biometric identification.

This is a **prototype (V0.1)** built for pre-recorded MP4/MOV/AVI/MKV video. The architecture is
deliberately layered (see [Architecture](#architecture)) so that upgrading to live RTSP/NVR camera
feeds later is a configuration change, not a rewrite.

---

## 1. Installation (beginner-friendly, step by step)

You need **Python 3.11+**. Everything else is installed automatically.

```bash
# 1. Clone / open this folder, then create an isolated Python environment
python -m venv venv

# 2. Activate it
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows

# 3. Install dependencies (this also installs PyTorch — first run can take a few minutes)
pip install -r requirements.txt

# 4. (Optional but recommended) pre-download the vision model so the first video you
#    analyse doesn't pause to download it
python scripts/download_models.py

# 5. Run the app
python run.py
```

Then open **http://localhost:8000** in your browser.

### Don't have a café video handy?

```bash
python scripts/create_sample_video.py
```

This downloads a small (~8MB), freely-licensed pedestrian test clip (OpenCV's own `vtest.avi`,
BSD-3 licensed) into `data/sample_videos/`. It's real people walking — not café footage — but it's
enough to prove the whole pipeline (detection → tracking → zones → events → metrics → AI summary)
works end to end. Upload it from the home screen like any other video. For a real demo, upload your
own recorded café footage instead.

---

## 2. GPU configuration

SOUVENO VISION auto-detects an NVIDIA GPU (CUDA) via PyTorch and falls back to CPU automatically —
nothing to configure. The active device is shown in the top-right badge ("Inference Device: NVIDIA
GPU" or "Inference Device: CPU") and in **Configuration → Model Manager**.

To force CPU even if a GPU is present, set in `.env`:

```
USE_GPU=false
```

CPU-only machines will still run the full demo — YOLO11n is small enough for near-real-time
analysis on a modern laptop CPU, though a GPU will be noticeably faster on longer/higher-resolution
video.

---

## 3. Using the app

1. **Upload a video** — drag & drop an MP4/MOV/AVI/MKV onto the home screen. SOUVENO VISION
   validates the file, reads its FPS/resolution/duration, and creates an analysis session.
2. **Define zones** — click **Draw Zones** to open the zone builder over a frame of your video, and
   draw `COUNTER_ZONE`, `QUEUE_ZONE`, `DINING_ZONE`, `PREP_ZONE`, `PICKUP_ZONE`, `ENTRANCE_LINE`,
   and/or individual `TABLE` polygons. Click to place vertices, **Finish Shape** (or Enter) to close
   a polygon (lines need exactly 2 points), then **Save Zones**. Prefer to skip this step? Click
   **Load Default Layout** for a ready-made café floor plan.
3. **Start AI Analysis** — click the big **START AI ANALYSIS** button. The left panel shows your
   video being analysed live, with bounding boxes, anonymous track IDs, zone outlines, dwell timers,
   and movement trails drawn directly on the frame. The right panel updates live: people/zone
   counts, queue length, table status, active alerts, and a scrolling event feed.
4. **Watch business events fire** — queue warnings, potential idle-staff detection in the prep
   zone, table clearing delays, potential pickup delays, and (if you click **Simulate Spill Event**)
   an experimental spill event, all appear as alert cards and timeline entries in real time.
5. **When the video ends**, switch to the **Insights** tab for the SOUVENO AI operations summary
   (deterministic statistics + a plain-English interpretation) and the illustrative **Cost Impact
   Estimator**.
6. **Events tab** lists every recorded event with a **VIEW CLIP** button — SOUVENO VISION generates
   a short MP4 clip (5s before/after) from the original recording on first request.
7. **Reset Demo Data** on the home screen clears all events/metrics for the current session so you
   can re-run the analysis cleanly.

### A note on "watching" the video

The left panel is not the raw uploaded file playing back — it is the actual frame-by-frame AI
output, streamed live over a WebSocket as SOUVENO VISION processes your recording. This is what
lets it show live overlays and metrics in sync, and it's exactly the mechanism that would later
consume a live RTSP camera instead of a file, unchanged.

---

## 4. Architecture

```
VIDEO SOURCE → DETECTOR → TRACKER → ZONE ENGINE → ACTIVITY ENGINE
   → RULE ENGINE → EVENT ENGINE → METRICS → AI REASONING → DASHBOARD / ALERTS
```

| Layer | File | Responsibility |
|---|---|---|
| Video Source | `backend/core/video_source.py` | `FileVideoSource` (V0.1), `RTSPVideoSource`, `NVRVideoSource`, `WebcamVideoSource` — swappable, same interface |
| Detector | `backend/core/detector.py` | Ultralytics YOLO11 (person/chair/table/cup/bottle/bowl/…), CPU/GPU auto |
| Tracker | `backend/core/tracker.py` | ByteTrack / BoT-SORT (config-switchable), persistent anonymous track IDs |
| Zone Engine | `backend/core/zones.py` | Normalized-coordinate polygon/line membership, dwell time, entrance line crossing |
| Activity Engine | `backend/core/activity.py` | Motion/idle detection from centroid displacement (pose model plug-in point for later) |
| Table Tracker | `backend/core/tables.py` | OCCUPIED / VACATED / CLEARING_DELAY / AVAILABLE state machine |
| Rule Engine | `backend/core/rules.py` | Configurable thresholds → event *intents* (pure, unit-tested) |
| Event Engine | `backend/core/events.py` | Persists events/alerts, builds the timeline (the only layer touching the DB) |
| Metrics | `backend/core/metrics.py` | Live status + business metrics + session aggregates |
| Spill Detector | `backend/core/spill.py` | Experimental — manual demo trigger today, real model plug-in point |
| AI Summary | `backend/core/ai_summary.py` | Deterministic stats + rule-based summary, or LLM summary if `LLM_API_KEY` is set |
| Notifications | `backend/core/notifications.py` | Console today; WhatsApp Cloud API client ready for Stage 6 |
| Pipeline | `backend/core/pipeline.py` | Orchestrates every layer above per frame, draws all overlays |

The **video upload → RTSP camera** upgrade path (Stage 2/3 of the original brief) touches exactly
one line: swap `FileVideoSource(path)` for `RTSPVideoSource(url, user, pass)` in
`backend/api/routers/analysis.py`. Everything downstream is already source-agnostic. A **Test
Camera** flow already exists at `POST /api/cameras/test` / Configuration tab.

### Why this isn't literally a `<video>` tag

A native `<video>` element can't show frame-synchronized AI overlays. Instead the backend decodes,
analyses, and burns overlays onto each frame, then streams it to the browser as JPEG frames over a
WebSocket alongside the JSON metrics/events for that same frame — the standard approach for
CV-annotated live video, and the same approach a live camera feed would use.

---

## 5. What's honestly experimental

- **Spill / wastage detection** is explicitly labelled "Experimental / Demo Spill Detection" in the
  UI. No generic COCO-trained model can reliably see liquid spills, so V0.1 ships a manual demo
  trigger (Configuration → simulate) behind the same `SpillDetector` interface a real trained model
  (custom YOLO checkpoint, segmentation, VLM, or anomaly detector) will plug into later —
  set `SPILL_MODEL_PATH` in `.env` once you have one.
- **Staff vs. customer role** is a zone-dominance heuristic (prep/counter zones lean "staff", dining
  leans "customer") unless manually overridden — there is no uniform/clothing classification yet.
- **Table clearing delay** cannot distinguish "nobody has bussed this table" from "nobody has sat
  down here yet after it was cleaned" — it only knows people stopped overlapping the table polygon.
- Every AI-inferred business event uses "**potential**" in its name/label (potential idle staff,
  potential abandonment, potential clearing delay) because intent and cause can't be known from
  video alone.
- The **Cost Impact Estimator** always labels its numbers "ILLUSTRATIVE ESTIMATE" — they are
  extrapolated from one recorded session, not proven savings, and are not connected to POS/payroll.

---

## 6. Demo Mode

`DEMO_MODE=true` (default) shortens every threshold so a short recorded clip still produces a full
range of events:

| Rule | Demo | Production |
|---|---|---|
| Idle staff | 25s | 10 min |
| Table clearing delay | 30s | 10 min |
| Pickup delay | 25s | 5 min |
| Queue warning / critical | 4 / 7 people | 4 / 7 people |

Set `DEMO_MODE=false` in `.env` for production-realistic thresholds. Current thresholds are visible
at **Configuration → Rule Engine**.

---

## 7. Running tests

```bash
pytest
```

Covers zone geometry, line crossing, dwell calculations, idle/queue/table rule logic, event
creation & closing, database round-trips, and the API health endpoint.

---

## 8. Project layout

```
souveno-vision/
├── backend/
│   ├── core/          # detection/tracking/zones/activity/rules/events/metrics/pipeline
│   ├── db/             # SQLAlchemy models + CRUD (SQLite by default)
│   ├── api/routers/    # FastAPI routes + the live-analysis WebSocket
│   ├── services/       # clip + screenshot generation
│   └── schemas/        # Pydantic request/response models
├── frontend/            # Plain HTML/CSS/JS dashboard (no build step)
├── models/              # Downloaded YOLO weights (object_detection/pose/segmentation/custom)
├── config/               # Central settings, model registry, rule thresholds
├── data/                 # SQLite DB + sample test videos
├── uploads/              # Uploaded videos
├── outputs/event_clips/  # Auto-generated event clips
├── screenshots/          # Alert screenshots
├── tests/                 # pytest suite
├── scripts/                # download_models.py / create_sample_video.py / reset_demo.py
├── requirements.txt
├── .env.example
└── run.py
```

---

## 9. Roadmap beyond V0.1 (already scaffolded, not fully wired up)

These are real, working interfaces — not TODOs — that intentionally stop short of being switched on
by default, so the local demo stays simple:

- **Stage 2/3 — Live RTSP/NVR cameras**: `RTSPVideoSource`/`NVRVideoSource` in `video_source.py`,
  with reconnect/timeout handling and a credential-safe `test_connection()`; `POST /api/cameras/test`
  and the Configuration tab already call it.
- **Stage 5 — Cloud database**: swap `DATABASE_URL` to Postgres/Supabase; the SQLAlchemy models are
  already structured to map onto a multi-tenant `business_id`/`branch_id` schema.
- **Stage 6 — WhatsApp alerts**: `NotificationService` → `WhatsAppNotificationService` in
  `notifications.py`, cooldown-protected; set `NOTIFICATION_PROVIDER=whatsapp` and the Meta Cloud
  API credentials in `.env`.
- **Stage 7 — AI reasoning**: `ai_summary.py`'s LLM path only ever receives structured
  metrics/events, never raw video — set `LLM_API_KEY` to switch from the rule-based summary to an
  LLM-written one.

---

## 10. Troubleshooting

- **"Could not open video file"** — re-encode with `ffmpeg -i input.xyz -c:v libx264 output.mp4` if
  your file uses an unusual codec.
- **First analysis run is slow** — the YOLO model is downloading; run
  `python scripts/download_models.py` ahead of time to avoid this during a live demo.
- **Analysis is slower than real-time on CPU** — expected; the frame budget lets it fall behind
  smoothly rather than skip processing (no results are faked to keep up). Lower `INPUT_RESOLUTION`
  or raise `PROCESS_EVERY_N_FRAMES` in `.env` to speed it up.

---

## 9. Expo Agent (exhibition intelligence, travel desk, lead funnel)

Open **http://localhost:8000/expo** after `python run.py`. The Expo Agent is a self-contained module
(`backend/core/expo/`, `backend/api/routers/expo.py`, `frontend/expo.html`) that turns the researched
show catalogue in `data/expo/events.json` into:

| Capability | Where |
|---|---|
| 23 shows for 2026-27 scored 1-5 stars (ICP fit, footfall, decision-makers, geography, competition, timing) with client probability, expected leads/pilots and an illustrative budget | `GET /api/expo/events`, Events tab |
| Attend-everything itinerary that resolves date clashes, plus an `.ics` feed with flight days | `GET /api/expo/itinerary`, `GET /api/expo/calendar.ics` |
| Travel desk: pre-filled flight/hotel searches and hotel picks per venue, booking status per show | Travel tab, `PUT /api/expo/plans/{event_id}` |
| Registration auto-fill: pre-written organiser-form answers and a bookmarklet that fills any exhibitor/visitor form | `GET /api/expo/events/{id}` → `registration_answers`, `GET /api/expo/profile/autofill.js` |
| Visitor-card scanner (Anthropic vision if `LLM_API_KEY` is set, `pytesseract` if installed, regex parser otherwise) | `POST /api/expo/cards/scan`, `POST /api/expo/cards/parse` |
| Card exchange: QR on your card opens `/expo/card`; the visitor leaves details and gets Souveno's vCard, WhatsApp and Calendly links | `POST /api/expo/exchange`, `GET /api/expo/profile/vcard` |
| Live funnel: leads → qualified → demo → pilot → converted / not converted / left midway, with mandatory drop reasons, per-day capture, developments log, collaborations | `/api/expo/leads`, `/api/expo/collaborations`, `GET /api/expo/dashboard` |
| Playbook: stall selection, favourable stall numbers, where to stand, how to get clients, checklist, 0-50 qualification scorecard | `GET /api/expo/playbook` |

All ratings, footfall figures and budgets are the agent's estimates from public organiser figures and the
Souveno strategy documents; edit `data/expo/events.json` to change them (scores recompute automatically).
Tests: `pytest tests/test_expo.py` (runs without the vision stack).

### Approvals: propose → one tap → execute

The agent never spends money on its own. `POST /api/expo/approvals/propose` creates a proposal for every
booking due within the horizon (stall advance = 50% of sqm × rate + 18% GST, flights from the fare range,
hotel from the mid-tier pick). The **Approvals** tab (with a badge count) lists them on your phone; one tap
approves or rejects. Approved items execute through whichever rail is configured in `.env`:

| Rail | Settings | What happens |
|---|---|---|
| RazorpayX payouts | `RAZORPAYX_KEY_ID`, `RAZORPAYX_KEY_SECRET`, `RAZORPAYX_ACCOUNT_NUMBER`, plus the payee's `fund_account_id` in the proposal details | NEFT/IMPS payout to the organiser for the stall advance |
| Duffel flights | `DUFFEL_ACCESS_TOKEN` (test token = sandbox orders, live token = real tickets), passenger details in the proposal | Searches the round trip, books the cheapest direct offer if within 125% of the approved amount |
| none | — | You get the exact payment / booking instruction and tap **Done** with the UTR or PNR; the stall, flight or hotel status flips to booked |

`EXPO_AUTO_EXECUTE=true` runs the rail immediately on approval; otherwise tap **Execute now**.

### Phone app

`/expo` ships a web-app manifest and service worker. Open it in Chrome (Android) or Safari (iPhone) and use
**Add to Home Screen**; it opens full-screen, caches the shell for the expo floor, and shows the approvals
badge. The public card page `/expo/card` is what the QR on your printed card points to.

### Stall Picker

`GET /api/expo/floorplans/{event_id}` returns a modelled layout of the venue's hall (entrance south, main
aisle north, 3 m shell stalls numbered per row) with every stall scored 0-100 and an SVG heat map;
`POST /api/expo/floorplans/score` ranks stalls you traced on the organiser's real plan (mark entrance,
registration, food court, washrooms, anchors, noisy zones, pillars, then the candidate stalls). Scoring:
traffic 30, main/cross aisle 20, corner 20, anchor 10, amenities 10, minus back wall, dead-end, noisy zone
and pillar penalties. The **Stall Picker** tab shows both and can save the best number to the event plan.
