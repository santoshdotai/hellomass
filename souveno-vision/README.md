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

Scoring covers Souveno's two product lines: each show carries a quote-desk ICP fit and a `vision_fit` (Vision AI: workforce, stock & dispatch, vehicle gates); the stars use the better of the two and the card says which product to lead with.

All ratings, footfall figures and budgets are the agent's estimates from public organiser figures and the
Souveno strategy documents; edit `data/expo/events.json` to change them (scores recompute automatically).
Tests: `pytest tests/test_expo.py` (runs without the vision stack).

### Approvals: propose → one tap → you pay (manual mode, the default)

The agent never spends money on its own. `POST /api/expo/approvals/propose` creates a proposal for every
booking due within the horizon (stall advance = 50% of sqm × rate + 18% GST, flights from the fare range,
hotel from the mid-tier pick). The **Approvals** tab (with a badge count) lists them on your phone.

`EXPO_PAYMENT_MODE=manual` (default, and what Souveno runs today) means no card, bank key or payout API is
stored anywhere. The flow is:

1. **Approve** (or Edit amount / Reject). Nothing is charged.
2. The card turns into a numbered **checklist**: ask the organiser for the proforma invoice, pay by NEFT/UPI
   from the Souveno company bank app with the approval reference in the remarks, or open the flight/hotel
   search links and pay on the airline or hotel site with the company card using the Souveno email.
3. Tap **Done** and enter the UTR / PNR / confirmation number. The stall, flight or hotel status flips to
   booked and the reference is kept on the approval for the expense sheet.

`EXPO_PAYMENT_MODE=rails` switches the optional automated rails on (only when their keys are also set):

| Rail | Settings | What happens |
|---|---|---|
| RazorpayX payouts | `RAZORPAYX_KEY_ID`, `RAZORPAYX_KEY_SECRET`, `RAZORPAYX_ACCOUNT_NUMBER`, plus the payee's `fund_account_id` in the proposal details | NEFT/IMPS payout to the organiser for the stall advance |
| Duffel flights | `DUFFEL_ACCESS_TOKEN` (test token = sandbox orders, live token = real tickets), passenger details in the proposal | Searches the round trip, books the cheapest direct offer if within 125% of the approved amount |

In rails mode `EXPO_AUTO_EXECUTE=true` runs the rail immediately on approval; otherwise tap **Execute now**.
Alternatives to RazorpayX (Cashfree Payouts, your bank's API banking, a company card) plug in the same way:
one executor function in `backend/core/expo/approvals.py` and its keys in `.env`.

**Flight policy** (`flight_booking_window`): every flight is proposed with a booking window — domestic: preferred by 60 days before departure, hard deadline 30 days; international (Gulf etc.): preferred 90 days, hard deadline 45 days, plus a **visa** proposal due 21 days before departure (UAE e-visa, Saudi business e-visa). Automated ticketing for international trips needs passport fields in `DUFFEL_PASSENGERS_JSON`. Inside 60 days the item is marked urgent and jumps to the top of Approvals; inside 30 days it is marked late. A calendar reminder is placed on the 60-day mark for each away show.


### Subsidies, early-bird deadlines and the 3-day follow-up

Every event card has a green **Subsidy / money back** box (`backend/core/expo/subsidy.py`, data in each event's
`subsidy` block of `data/expo/events.json`). It lists the schemes that apply to that show, the estimated refund,
the **apply-by date** (PMS: 30 days before the show; MAI: 90 days; IC: the ministry's call), the claim window,
and the organiser's early-bird / last-date-to-book-with-discount when it is published (`null` = not published
yet, never a guess). Schemes in the catalogue: MSME PMS (domestic stall rent, confirmed), Telangana MSME Policy
2024 marketing assistance (being verified), MSME International Cooperation (foreign fairs, via an industry
association), MAI via ESC India (needs 12 months' EPC membership), DPIIT startup pods. `GET /api/expo/subsidies`
returns the whole table plus the next deadlines.

A Claude routine runs **every 3 days at 9:30am IST** ("Souveno expo: 3-day subsidy, early-bird and confirmation
follow-up"): it re-checks organiser early-bird deadlines and scheme pages, reads organiser replies and
Booking.com / airline confirmation e-mails in the Souveno inbox, marks the matching approvals Done, commits the
updated `subsidy` blocks, and e-mails santoshdotai@gmail.com a summary. A second routine sends the **8pm evening
brief** with the next day's programme, flights, hotel, stall advice and everything due in the next 3 days.

### Manual vs automate mode

The **Mode** button in the Approvals tab (in-app and on the phone dashboard) switches `EXPO_PAYMENT_MODE`:

| Mode | What happens after you tap Approve |
|---|---|
| **Manual** (default) | Checklist: pay from the Souveno bank app / open the pre-filled **Skyscanner** or **Booking.com** link, book with the Souveno e-mail, tap Done with the UTR / PNR / confirmation number. |
| **Automate** | Flights: the agent tickets via Duffel with the **frequent-flyer numbers saved once** in Travel & Booking (`PUT /api/expo/settings/travellers`) when `DUFFEL_ACCESS_TOKEN` is set; otherwise it hands you the Skyscanner link. Hotels: pre-filled Booking.com link (Booking.com has no booking API for guests, and the agent never takes your login). In both cases the 3-day routine reads the confirmation e-mail and marks the item Done. Stall advances: RazorpayX payout when keys exist, else the manual checklist. |

Nothing is ever charged without the Approve tap. Card numbers, portal passwords and Booking.com PINs are never
stored; only PNRs, confirmation numbers and UTRs.


### Finance / P&L tab

`GET /api/expo/finance?horizon=1m` (horizons: 1w, 2w, 3w, 1m … 12m) and the **Finance / P&L** tab on both
dashboards: every show starting inside the horizon, exhibits and visits separated, with total cost, subsidy
money back, assumed leads, pipeline worth, conversions (paid pilots that become clients), conversion % and
worth in ₹ and $, P&L (revenue minus cost net of subsidy), ROI, and the best bets on that floor (lead product,
ICP segments, who to target). Revenue uses `_meta.deal_economics` in `data/expo/events.json` (first-year value
per client: quote desk ₹1,69,000; Vision AI ₹3,50,000; 5.25% of captured leads convert; USD at ₹84) — edit the
numbers there and everything recomputes. Low case first, high case second; costs are public ranges, not quotes.

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

### Free public URL (expo-only mode)

Set `APP_MODE=expo` and the app serves only the Expo Agent (no OpenCV/YOLO), which fits free tiers:

* **Vercel (free Hobby)** — `api/index.py` + `vercel.json` are the entrypoint. Vercel installs from
  `requirements.txt`, so deploy with `requirements-expo.txt` copied over it (the file-tree deploy does this),
  and set `DATABASE_URL` to your Supabase Postgres connection string (Vercel's disk is not persistent;
  without it leads live in `/tmp` and vanish on cold start).
* **Render free / Hugging Face Space / Railway** — `render.yaml` and `Dockerfile.expo` are ready; same two env vars.

The full vision app still runs with `python run.py` and the original `requirements.txt`.
