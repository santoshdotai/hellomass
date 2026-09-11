# SOUVENO AI — Souveno Vision Intelligence

**Existing Cameras. Operational Intelligence.**

An intelligence layer for existing CCTV infrastructure: the camera provides video; Souveno converts
it into operational events, alerts, evidence and management insights — anonymous person detection
and tracking, occupancy / entry / exit counts, virtual lines, restricted zones, dwell-time alerts,
after-hours detection, an event timeline with snapshots and clips, acknowledgement workflow, a local
dashboard, health page, camera audit tool and an optional webhook — all **offline, on-premise**.

> **Scope of this build:** a single/few-stream proof of concept to validate use cases before hardware
> sizing. It does **not** process 348 cameras simultaneously. Inputs implemented: **laptop webcam**,
> **local video file (MP4/AVI/MOV)**, **RTSP camera / NVR channel**. Production integration may also
> use ONVIF discovery, the NVR/VMS API or a manufacturer SDK — those connectors are reserved in the
> code but not built here (`src/sources/factory.py`).
>
> **Privacy:** anonymous, camera-local tracking IDs (`Person 12`). No facial recognition, no employee
> names. See `docs/PRIVACY_AND_SECURITY.md`. **Licensing:** the demo detector is AGPL-3.0 — see
> `LICENSING.md` before any commercial deployment.

Documentation: [DEMO_GUIDE](docs/DEMO_GUIDE.md) · [CAMERA_AUDIT](docs/CAMERA_AUDIT.md) ·
[PRODUCTION_ARCHITECTURE](docs/PRODUCTION_ARCHITECTURE.md) · [PRIVACY_AND_SECURITY](docs/PRIVACY_AND_SECURITY.md) ·
[CLIENT_PILOT_PLAN](docs/CLIENT_PILOT_PLAN.md) · [LICENSING](LICENSING.md)

---

## 1. Requirements

* **Windows 10/11** (64-bit), macOS or Linux. Instructions below are for Windows; macOS/Linux differ only in the venv activation line.
* **Python 3.10 or 3.11** (3.11 recommended; 3.12+ not tested). Install from https://www.python.org/downloads/windows/ and tick **“Add python.exe to PATH”**.
* ~6 GB free disk for the Python environment (PyTorch), 8 GB RAM, any recent laptop CPU. An NVIDIA GPU with CUDA is optional.
* A webcam (for the live demo) and/or a video file and/or an RTSP camera reachable on the network.
* Internet **once** for `pip install` and the model download; the app then runs fully offline.

## 2. Installation (Windows, step by step)

Open **PowerShell** (Start → type `PowerShell`), then:

```powershell
cd path\to\hellomass\souveno-vision

# 1. create and activate an isolated Python environment
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
#   if PowerShell refuses to run the script once:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   (answer Y), then re-run the Activate line

# 2. install dependencies
python -m pip install --upgrade pip
# CPU-only laptops (recommended — smaller download, ~1 GB):
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
# NVIDIA GPU laptops instead: skip the CPU line and run only
#   pip install -r requirements.txt        (pulls the CUDA build of PyTorch, ~3 GB)

# 3. model preparation — downloads yolo11n.pt (~6 MB) into models\object_detection\
python scripts/download_models.py

# 4. optional recorded demo clip (OpenCV's Apache-2.0 pedestrian sample, ~8 MB) -> demo_assets\
python scripts/create_sample_video.py

# 5. configuration (optional)
copy .env.example .env      # then edit .env for RTSP credentials — never commit it
```

`python scripts/download_models.py` is the only step that needs the model download; the app also
downloads the weights automatically the first time a source starts if the file is missing.

## 3. Running the application

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

The dashboard opens at **http://127.0.0.1:8501** (the terminal prints the URL; add `--no-browser`
to suppress the auto-open). Useful flags:

```powershell
python app.py --source webcam                 # start the webcam immediately
python app.py --source file --path demo_assets\my_factory.mp4
python app.py --source rtsp                   # URL + credentials from .env (SOUVENO_RTSP_*)
python app.py --device cpu --port 9000
```

**Stop the application safely:** press `Ctrl+C` once in the PowerShell window. The capture thread,
clip writers and database are closed cleanly; wait for the prompt to return before closing the window.

### Dashboard tour

| View | What it shows |
|---|---|
| **Dashboard** | Live/recorded video with boxes, `Person N` IDs, confidence, zones, virtual line with direction arrow, counts; KPI cards (occupancy, entries, exits, active alerts, restricted-zone violations today, average dwell, camera health, total events today); latest event cards with snapshot, Acknowledge / Dismiss / Resolve |
| **Demo Mode** | Large buttons: Start Webcam Demo · Start Recorded Factory Demo · Connect RTSP · Reset Counts · Enable Restricted Zone · Trigger/Verify Dwell Alert · Open Event History · Fullscreen; big counters and live event feed |
| **Event History** | Date / source / type / severity / status / text filters, snapshot preview, clip link, acknowledge, CSV export |
| **Settings** | Source (webcam index, video file upload/select with loop, RTSP URL + separate username/password, main/substream, TCP/UDP); confidence, analytics FPS, CPU/CUDA; zone & line editor (add, drag, remove, reset, save per camera); rules (enable, severity, threshold, cooldown, schedule, evidence, notify); working hours; occupancy & dwell thresholds; evidence retention & clips; webhook |
| **Camera Audit** | Probe one source and get an A/B/C/D suitability class with notes |
| **Health** | Capture/inference FPS, latency, skipped frames, reconnections, last frame time, detector/tracker/database/evidence status, disk space, CPU/GPU mode, webhook deliveries, recent errors, health log |
| **Privacy** | The privacy & integration position, links to docs and to the legacy café demo |

## 4. The three demos

### 4.1 Webcam demo
Demo Mode → **Start Webcam Demo** (index 0 by default; change it in Settings → Video source →
“Detect webcams”). Press **Enable Restricted Zone** to apply the demo layout (restricted area right,
entry line centre, work area left), then adjust in Settings → Zone editor. Follow `docs/DEMO_GUIDE.md`.

### 4.2 MP4 / recorded demo
Drop a file into `demo_assets\` (or upload it in Settings → Video source → Video file) and press
**Start Recorded Factory Demo**. Files loop by default so the presentation never ends mid-scene.
Event timestamps carry both the wall-clock time and the playback position (`media_time`). If no
file exists the app falls back to the built-in **synthetic factory scene** (clearly labelled).

### 4.3 RTSP demo
1. **VLC pre-check (strongly recommended):** VLC → Media → Open Network Stream → paste the URL, e.g.
   `rtsp://192.168.1.50:554/Streaming/Channels/102` (Hikvision substream) or
   `rtsp://192.168.1.60:554/cam/realmonitor?channel=1&subtype=1` (Dahua substream). If VLC cannot
   play it, Souveno cannot either — fix URL / credentials / network first.
2. Put the URL and credentials in `.env` (`SOUVENO_RTSP_URL`, `SOUVENO_RTSP_USERNAME`,
   `SOUVENO_RTSP_PASSWORD`) **or** type them in Demo Mode → **Connect RTSP** (kept in memory only).
3. Prefer the **substream** (640–1280 px, 8–15 fps) and **TCP** transport. Credentials are masked
   in every log line (`rtsp://***:***@host/...`) and never stored in the database.
4. If the camera drops, the app shows *Disconnected — reconnecting* and retries with exponential
   back-off (1 s → 30 s) without freezing the dashboard; a `camera_disconnected` /
   `camera_reconnected` event is recorded.

**Windows Firewall:** outbound RTSP (TCP 554, or the port in your URL) must be allowed; Windows
normally allows outbound traffic. If the camera is on a different VLAN, ask IT to route it to the
laptop. If you bind the dashboard to the LAN (`--host 0.0.0.0`), Windows will ask to allow
`python.exe` inbound on the chosen port — only do this on a trusted network; the dashboard has no login.

## 5. Where things are stored

| What | Where |
|---|---|
| Events, zones, rules, settings, acknowledgements, health log | `data\souveno_vision_intelligence.db` (SQLite) |
| Snapshots | `data\evidence\snapshots\` |
| Evidence clips (MP4, or AVI if the MP4 encoder is unavailable) | `data\evidence\clips\` |
| Uploaded videos | `data\uploads\` |
| Logs (rotating text + JSON-lines, credentials redacted) | `logs\souveno_vision_intelligence.log` / `.jsonl` |
| Model weights | `models\object_detection\yolo11n.pt` |
| Configuration | `config\default.yaml` (defaults), `config\local.yaml` (your overrides, git-ignored), `.env` (secrets) |
| Legacy café demo data | `data\souveno_vision.db`, `uploads\`, `outputs\`, `screenshots\` |

Evidence older than the retention setting (default 14 days) or above the storage cap (2 GB) is
deleted automatically every 30 minutes.

## 6. CPU versus CUDA

* Default `model.device: auto` uses CUDA when PyTorch reports it, otherwise CPU. The top bar shows
  **CPU** or **CUDA GPU**; the Health page shows the GPU name.
* Force a mode in Settings → Detection device, with `SOUVENO_MODEL__DEVICE=cpu|cuda` in `.env`, or `python app.py --device cpu`.
* CPU laptops: YOLO11n at 640 px runs at roughly 8–12 fps on a modern quad-core; the default
  analytics rate is 8 fps (Settings → Analytics FPS). Lower it to 4–6 on slower machines.
* CUDA: install the CUDA build of PyTorch (plain `pip install -r requirements.txt` on Windows pulls
  it) and an up-to-date NVIDIA driver. Check with `python -c "import torch; print(torch.cuda.is_available())"`.

## 7. Troubleshooting

**Camera access**
* *Webcam could not be opened / no image:* close Teams, Zoom, browser tabs using the camera; check
  Windows Settings → Privacy & security → Camera → “Let desktop apps access your camera”; try index 1.
* *RTSP not reachable:* test in VLC; check port, path, credentials (special characters are handled
  when typed into the separate username/password fields), VLAN routing, firewall.
* *Connected but no frames:* wrong channel path, or an H.265 stream the bundled decoder cannot
  handle — switch the substream to H.264 in the camera/NVR settings.

**Missing codecs**
* *Could not decode video file:* re-encode to H.264 MP4 (HandBrake / VLC → Convert). MKV/MOV work when
  the bundled FFmpeg supports the codec; AVI with old codecs may not.
* *Clips saved as .avi:* the MP4 (`mp4v`) writer was unavailable; Motion-JPEG AVI is used instead and still plays in VLC.

**AI**
* *Top bar shows `opencv-hog (fallback)`:* PyTorch/Ultralytics failed to import — re-run the pip
  install steps in an activated venv; the HOG fallback keeps the demo alive with lower accuracy.
* *First start is slow:* the model is loaded (and downloaded once); wait ~10–20 s.
* *Too many / too few detections:* adjust the confidence slider (0.35–0.5 typical).

**General**
* Dashboard not loading: make sure `python app.py` is still running; try `http://127.0.0.1:8501` (not `localhost` if IPv6 is odd on the machine).
* Port already in use: `python app.py --port 9000`.
* Reset everything: stop the app, delete `data\souveno_vision_intelligence.db` and the `data\evidence\*` files.

## 8. Configuration

All settings live in `config/default.yaml` (source, model, device, confidence, analytics FPS, frame
size, tracking, zone/line analytics, business hours, rule thresholds, cooldowns, evidence, retention,
database, logging, webhook). Override without editing it via `config/local.yaml`, environment
variables `SOUVENO_<SECTION>__<KEY>` (e.g. `SOUVENO_MODEL__CONFIDENCE=0.5`), or the Settings page
(persisted in the database). Credentials only ever come from `.env` or runtime input.

## 9. Tests

```powershell
python -m pytest
```

Covers geometry (point-in-polygon, polygon validation), directional line crossing and jitter
debouncing, dwell calculation, occupancy hysteresis, rule cooldowns / thresholds / schedules /
after-hours / camera disconnect, event creation with evidence and acknowledgement audit, SQLite
repositories and corruption recovery, RTSP credential redaction (URLs, logs, repr), source
disconnection and reconnection with a mock camera, webhook delivery with retries, configuration
overrides, a deterministic synthetic end-to-end pipeline run, and the HTTP API. The original café
demo tests are kept under `tests/legacy/`.

## 10. Project layout

```
souveno-vision/
├── app.py                    launcher (uvicorn)              ├── config/default.yaml   all defaults
├── src/                                                       ├── .env.example          secrets template
│   ├── sources/   base.py webcam.py video_file.py rtsp.py synthetic.py factory.py
│   ├── inference/ detector.py (Ultralytics / ONNX / HOG / ground-truth) preprocess.py
│   ├── tracking/  tracker.py (ByteTrack via supervision, simple IoU)
│   ├── analytics/ geometry.py zones.py line_crossing.py occupancy.py dwell.py spatial.py
│   ├── rules/     models.py engine.py
│   ├── events/    service.py evidence.py webhook.py
│   ├── storage/   database.py migrations.py repositories.py
│   ├── monitoring/ health.py logging_config.py camera_audit.py
│   ├── security/  redaction.py
│   ├── utils/     config.py time_utils.py
│   ├── ui/        dashboard.py api.py components.py overlay.py static/ (HTML/CSS/JS)
│   └── pipeline.py           orchestrator (capture thread → analytics thread → state)
├── data/  evidence/{snapshots,clips}  uploads/   ├── logs/          ├── demo_assets/
├── docs/  DEMO_GUIDE CAMERA_AUDIT PRODUCTION_ARCHITECTURE PRIVACY_AND_SECURITY CLIENT_PILOT_PLAN
├── tests/ test_geometry test_line_crossing test_dwell test_rules test_redaction test_database
│          test_events test_sources test_webhook test_config test_pipeline_synthetic test_api  legacy/
├── backend/ frontend/ config/settings.py …   the original café demo (unchanged), served at /cafe
└── LICENSING.md  requirements.txt  pytest.ini
```

## 11. Legacy café demo

The original SOUVENO VISION café intelligence prototype (queue, idle staff, table turnover, pickup
delay, spill simulation, AI summary, cost estimator) is preserved unchanged. It is served by the
same process at **http://127.0.0.1:8501/cafe** (its API stays at `/api/sessions`, `/api/zones`,
`/api/events`, `/api/config`, `/api/cost`, `/api/cameras`, `/api/health`, `/ws/analysis/…`) and can
still be started on its own with `python run.py` (port 8000). Its settings come from `.env`
(`DEMO_MODE`, `USE_GPU`, …) as before; its tests are in `tests/legacy/`.

## 12. Expo Agent

The Souveno Expo Agent lives in `../expo-backend` and `../expo-frontend` (own READMEs); it is not
part of this application.
