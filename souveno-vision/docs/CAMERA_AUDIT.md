# Camera / Source Compatibility Audit

The **Camera Audit** page (and `src/monitoring/camera_audit.py`) probes **one operator-supplied
source** for a few seconds and reports whether it is suitable for AI analytics. It never scans the
network; only the URL/index/file you enter is tested. Credentials are masked in the report and logs.

## What is measured

| Field | Meaning |
|---|---|
| Reachable | The stream opened and delivered at least one decoded frame |
| Connect time (ms) | Time from request to first frame — long times hint at DNS/route/auth problems |
| Resolution | Decoded frame size (main streams are often 1080p/4K, substreams 360p–720p) |
| FPS reported / observed | Camera-declared FPS vs. what actually arrived over the network |
| Codec | FourCC reported by the decoder (H264, HEVC/H265, MJPG …) |
| Frame interval mean ± std, max gap | Delivery regularity; large gaps = network congestion or camera CPU load |
| Stability | `stable`, `jittery`, `stalling`, `no-frames` |
| Stale / read failures | Frames later than 1.5 s or failed reads during the probe |
| Main-stream / substream label | Which profile you tested — test both |

## Classification

| Class | Label | Typical profile |
|---|---|---|
| **A** | AI ready | ≥ 720p, ≥ 10 fps observed, stable delivery |
| **B** | Usable after configuration | Good once you switch to the substream, lower the main-stream FPS/bitrate, force TCP, or move to a wired VLAN |
| **C** | Basic analytics only | Low FPS or low resolution: presence/occupancy and coarse intrusion OK; line crossing/tracking unreliable |
| **D** | Unsuitable for requested use case | Unreachable, undecodable, or delivering < 2 fps |

Scoring is deliberately simple (resolution + FPS + stability, each 0–2 points). The notes list the
concrete fix for each deduction.

## Procedure for the client pilot

1. Obtain a **read-only** camera/NVR account from the client's IT team.
2. Verify each RTSP URL in **VLC** first (Media → Open Network Stream). If VLC cannot play it, the
   audit will fail too — fix the URL/credentials/VLAN before blaming the software.
3. Run the audit on the **substream** first, then the main stream. Record both.
4. Run it at two times of day (quiet / busy network) for cameras that score B or C.
5. Fill the audit sheet below for the 8–12 pilot cameras and attach the reports (JSON from
   `GET /api/vi/audit`).

| Camera | Location | Make/model | Access (RTSP / ONVIF / NVR API / SDK) | Stream tested | Resolution | FPS obs. | Codec | Class | Notes |
|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | |

## Common findings and fixes

* **Unreachable (D):** wrong port (554 vs 8554), camera VLAN not routed to the analytics host,
  firewall, credentials with special characters (URL-encode them or type them in the separate fields).
* **Connected but no frame:** wrong channel path (e.g. Hikvision `/Streaming/Channels/101` main,
  `/102` sub; Dahua `/cam/realmonitor?channel=1&subtype=0`), H.265 not decodable by the bundled
  FFmpeg build — switch the substream to H.264.
* **Jittery / stalling:** use TCP transport, reduce main-stream bitrate, prefer the substream,
  check Wi-Fi bridges and PoE budget.
* **No RTSP at all:** older or consumer cameras may only expose a vendor app/SDK or the NVR's own
  API. These go through the NVR/VMS connector in production (see `PRODUCTION_ARCHITECTURE.md`).
