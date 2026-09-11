# Production Architecture — path from this proof of concept to ~348 cameras

This document describes **how** Souveno Vision Intelligence scales, not a commitment that it does
so at any particular size. **Hardware sizing depends on the number of concurrently analysed
streams, their resolution, FPS, codec, the model complexity and the required latency. A camera
count by itself is insufficient for server sizing. The pilot must benchmark actual streams before
a 348-camera proposal is made.**

## 1. What the proof of concept already establishes

```
 existing camera / NVR / file / webcam
        │  (VideoSource connector, worker thread, latest-frame buffer, reconnect w/ back-off)
        ▼
 frame scheduler (analytics FPS ≠ video FPS, aspect-preserving downscale)
        ▼
 Detector interface  ──►  Tracker interface  ──►  Spatial analytics (zones / lines / dwell / occupancy)
 (YOLO11 / ONNX / HOG)    (ByteTrack / IoU)            (normalised coordinates, hysteresis, debounce)
        ▼
 RulesEngine (8 rules, severity, cooldown, schedule, evidence, notify)  — no UI/detector coupling
        ▼
 EventService ─► SQLite repositories ─► dashboard / CSV
             ├─► EvidenceManager (snapshot, pre/post clip, retention)
             └─► WebhookDispatcher (async, retries)  ─► n8n / WhatsApp / e-mail / Slack / ERP / Supabase
```

Every arrow is an interface (`src/sources/base.py`, `src/inference/detector.py`,
`src/tracking/tracker.py`, `src/rules/engine.py`, `src/storage/repositories.py`). Production
replaces implementations behind them; it does not change the shape.

## 2. Target production topology

```
┌─────────────────────────────── plant network ───────────────────────────────┐
│  Camera VLAN (isolated)                                                      │
│   348 cameras ──► NVR / VMS (recording, main streams)                        │
│        │  substreams (H.264, 640–1280 px, 8–15 fps)                          │
│        ▼                                                                     │
│  Edge analytics nodes (on-premise, 1..N)                                     │
│   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                           │
│   │ node 1      │ │ node 2      │ │ node N      │  each: stream group of     │
│   │ 24–64 subs. │ │ 24–64 subs. │ │ ...         │  cameras, 1–4 GPUs,        │
│   │ DeepStream/ │ │             │ │             │  metadata-only output      │
│   │ GStreamer   │ │             │ │             │                            │
│   └──────┬──────┘ └──────┬──────┘ └──────┬──────┘                           │
│          └───────────────┴──── events (JSON) ─┘                              │
│                                  ▼                                           │
│   Central service: event store (PostgreSQL), rules config, evidence index,   │
│   alert router (WhatsApp / e-mail / Slack / ERP-HRMS), central dashboard,    │
│   monitoring (Prometheus/Grafana), RBAC                                       │
│   Evidence: snapshots/clips on the node or NAS; retrieval on demand from NVR │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Input: RTSP / ONVIF / NVR API / vendor SDK

* Prefer **camera substreams** for analytics (main streams stay with the NVR for recording).
  Typical: H.264, 640×360 – 1280×720, 8–15 fps, constant bitrate 512 kbps – 1.5 Mbps.
* **RTSP over TCP** from the camera or the NVR's per-channel RTSP endpoint.
* **ONVIF** for discovery, profile selection and event subscription (motion, tamper) where supported.
* **NVR/VMS API** (Milestone, Genetec, HikCentral, Dahua DSS, Uniview…) when cameras are not
  directly reachable or licensing forces access through the recorder; also the path for evidence
  retrieval from the NVR archive instead of duplicating recordings.
* **Manufacturer SDK** (HCNetSDK, NetSDK…) only when neither RTSP nor ONVIF is exposed.
  These are the `onvif`, `nvr` and `sdk` connector slots in `src/sources/factory.py`.

### Processing: stream grouping and GPUs

* Group cameras by **use case and load** (gate cameras need line-crossing at 10 fps; a warehouse
  aisle may need 2–4 fps intrusion only). Analytics FPS per camera is a per-source setting.
* **Multi-GPU** nodes run batched inference; **NVIDIA DeepStream / GStreamer** pipelines decode
  H.264/H.265 on the GPU (NVDEC) and batch frames into TensorRT — this is what makes tens of
  streams per GPU feasible. The current OpenCV+PyTorch path is the reference behaviour, not the
  scale path.
* Model optimisation: **ONNX → TensorRT** (NVIDIA) or **OpenVINO** (Intel CPU/iGPU) with INT8/FP16
  calibration; smaller input sizes for near-field cameras.
* **Metadata-only output**: nodes emit events and periodic counts, never continuous video. Evidence
  is a short clip/snapshot per event, or a pointer into the NVR archive.

### Central services

* PostgreSQL (schema mirrors the SQLite tables: sources, zones, rules, events, acknowledgements,
  settings, health_logs) with retention jobs.
* Central dashboard (this UI generalised to many sources), RBAC (viewer / operator / admin),
  SSO integration, audit log.
* Alert delivery through the webhook contract already used here (`souveno.vision.event` JSON):
  WhatsApp Business API, e-mail, Slack/Teams, ERP/HRMS tickets, Souveno Supabase backend.

### Security and operations

* Cameras stay on an **isolated camera VLAN**; analytics nodes have one interface on it and one
  on the corporate LAN; no inbound access from the camera VLAN.
* **Read-only service credentials** per node (never admin), rotated; secrets in a vault/env, never
  in config files or the database (already enforced in the PoC).
* Monitoring: per-stream capture FPS, inference FPS, latency, drops, reconnects, GPU utilisation,
  disk; alerts when a stream is down > N seconds (the `camera_disconnected` rule scaled up).
* **Failover**: stream groups are re-assignable between nodes; a node loss degrades the affected
  cameras, not the plant; central services run in HA (two nodes + managed DB).
* **Storage retention**: events 12 months (metadata is small), evidence 30–90 days configurable,
  automatic cleanup and quota per node.
* **Horizontal scaling**: add nodes, re-balance stream groups; central services scale independently.

## 3. Sizing method (what the pilot measures)

For each representative camera group, measure with the actual streams:

| Measurement | Why it matters |
|---|---|
| Decode cost per stream (codec, resolution, fps) | Often the real bottleneck before the model |
| Inference latency & throughput per model/size/precision | Streams per GPU |
| Analytics FPS needed per use case | Line crossing needs more than dwell detection |
| Event rate and evidence size | Disk and network budget |
| Accuracy / false-alert rate per camera class (A/B/C) | Which cameras need repositioning or replacement |

Only after those numbers exist can a 348-camera bill of materials be written responsibly.
Indicative public benchmarks (DeepStream, T4/L4-class GPUs, 720p H.264 substreams, small detector,
5–10 fps) land in the range of tens of streams per GPU; the pilot will replace that with measured
figures for this client's cameras and use cases.

## 4. Migration checklist from the PoC

1. Replace `UltralyticsDetector` with a licensed/permissive model exported to TensorRT/OpenVINO
   (`OnnxDetector` is the bridge) — see `LICENSING.md`.
2. Replace `FrameGrabber`+OpenCV per stream with a DeepStream/GStreamer pipeline that feeds the
   same `Detection` objects per stream.
3. Move `Repositories` from SQLite to PostgreSQL (same methods, parameterised SQL).
4. Run one `VisionPipeline` per stream inside a node process/container; add a node agent that
   reports health to the central service.
5. Keep the rules engine and event contract unchanged so the pilot's tuned rules carry over.
