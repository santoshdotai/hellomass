# Licensing — Souveno Vision Intelligence (proof of concept)

This file lists the licence of every major model and library the demo introduces or relies on,
and flags anything that needs a commercial decision **before** a client deployment.

> **Bottom line:** the proof-of-concept detector (Ultralytics YOLO11 weights + the `ultralytics`
> package) is **AGPL-3.0**. It is fine for an internal evaluation/demo, but a closed, commercial,
> on-premise deployment at the client requires either an **Ultralytics Enterprise licence** or a
> switch to a differently licensed model. Do not represent this demo model as approved for
> production use.

## Components that need a commercial licensing decision

| Component | Version | Licence | Risk | Action before production |
|---|---|---|---|---|
| `ultralytics` (YOLO11 code) | 8.3.55 | **AGPL-3.0** | High — AGPL obligations apply to network-served software using it | Buy Ultralytics Enterprise licence **or** replace with an Apache/MIT model |
| YOLO11n weights (`yolo11n.pt`) | v8.3.0 release | **AGPL-3.0** (trained by Ultralytics on COCO) | High (same as above) | Same as above; the ONNX export of these weights is still AGPL |
| COCO dataset (training data of the weights) | 2017 | CC-BY 4.0 (annotations); images have individual Flickr licences | Low for inference use | Attribution only |

Commercially cleaner detector options the `Detector` interface already supports or can be added to
(`src/inference/detector.py`): YOLOX (Apache-2.0), PP-YOLOE (Apache-2.0), RT-DETR from the
`transformers`/PaddleDetection ecosystems (Apache-2.0), DAMO-YOLO (Apache-2.0), or an NVIDIA
TAO/DeepStream PeopleNet model (NVIDIA model EULA — check terms). Any of these can be exported to
ONNX and run through `OnnxDetector` (onnxruntime, MIT) or through TensorRT/OpenVINO.

## Libraries (permissive — no commercial blocker)

| Library | Version | Licence | Used for |
|---|---|---|---|
| PyTorch (`torch`, `torchvision`) | 2.5.1 / 0.20.1 | BSD-3-Clause | Runtime for the YOLO model |
| OpenCV (`opencv-python-headless`) | 4.10 | Apache-2.0 | Video decoding, drawing, HOG fallback detector, clip encoding |
| supervision | 0.25.1 | MIT | ByteTrack multi-object tracker |
| FastAPI / Starlette | 0.115.6 | MIT / BSD-3 | API + dashboard |
| uvicorn | 0.32.1 | BSD-3-Clause | ASGI server |
| websockets | 14.1 | BSD-3-Clause | Live state push |
| pydantic, pydantic-settings | 2.x | MIT | Request validation |
| SQLAlchemy | 2.0.36 | MIT | Legacy café demo storage |
| numpy | 1.26.4 | BSD-3-Clause | Arrays |
| pandas | 2.2.3 | BSD-3-Clause | Legacy café demo |
| PyYAML | 6.0.2 | MIT | Configuration |
| python-dotenv | 1.0.1 | BSD-3-Clause | `.env` loading |
| loguru | 0.7.3 | MIT | Logging |
| requests | 2.32.3 | Apache-2.0 | Webhook dispatcher |
| psutil | 6.1.0 | BSD-3-Clause | CPU/memory health |
| pytest, httpx | — | MIT / BSD-3 | Tests only |
| SQLite (stdlib `sqlite3`) | — | Public domain | Event storage |
| FFmpeg (bundled inside the OpenCV wheel) | 5.x/6.x | LGPL-2.1+ (the wheel build; check for GPL components if you rebuild OpenCV) | RTSP/H.264 decoding |
| onnxruntime (optional) | 1.20 | MIT | ONNX inference path |

## Demo assets

* `demo_assets/pedestrians_vtest.avi` is OpenCV's `vtest.avi` sample (part of the OpenCV project,
  Apache-2.0). It is generic pedestrian footage used only to prove the pipeline; it is **not**
  client footage and not a factory scene. It is git-ignored; download it with
  `python scripts/create_sample_video.py` or drop your own recording into `demo_assets/`.
* The synthetic scene (`src/sources/synthetic.py`) is generated code — no third-party content.

## Notes

* Nothing in this repository grants the client a licence to the AGPL components. The licensing
  decision (Ultralytics Enterprise vs. permissive model) must be made and costed in the pilot proposal.
* Client CCTV footage processed by the demo stays on the client's machine; no data is sent to Souveno
  or any third party unless the optional webhook is explicitly enabled.
