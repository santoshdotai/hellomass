"""Layer 3 — person detection behind an abstract `Detector` interface.

Backends
--------
* UltralyticsDetector  – YOLO11n via the `ultralytics` package (AGPL-3.0, see LICENSING.md).
                         Best accuracy; CPU or CUDA; auto-downloads weights the first time.
* OnnxDetector         – YOLO-style ONNX file through onnxruntime (MIT) — the path to a
                         commercially clean deployment once a suitably-licensed model is chosen.
* HogPersonDetector    – OpenCV's built-in HOG+SVM pedestrian detector (Apache-2.0). No download,
                         no torch. Low accuracy — a fallback that keeps the demo alive.
* GroundTruthDetector  – reads boxes published by the SyntheticSource. Deterministic; tests only.

`create_detector()` picks the requested backend and falls back gracefully so the
dashboard always has something to show, and reports which backend is active."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from loguru import logger

from src.inference.preprocess import letterbox, unletterbox_box

PERSON_CLASS_ID = 0


@dataclass
class Detection:
    box: tuple[float, float, float, float]   # x1, y1, x2, y2 in pixels of the image passed to detect()
    confidence: float
    class_id: int = PERSON_CLASS_ID
    class_name: str = "person"

    def scaled(self, factor: float) -> "Detection":
        x1, y1, x2, y2 = self.box
        return Detection((x1 * factor, y1 * factor, x2 * factor, y2 * factor), self.confidence, self.class_id,
                         self.class_name)


def detect_gpu() -> dict:
    """Report CUDA availability without importing torch when it is not installed."""
    info = {"cuda_available": False, "device_name": "", "torch": ""}
    try:
        import torch  # noqa: WPS433
        info["torch"] = torch.__version__
        if torch.cuda.is_available():
            info["cuda_available"] = True
            info["device_name"] = torch.cuda.get_device_name(0)
    except Exception:
        pass
    return info


def resolve_device(preference: str = "auto") -> str:
    pref = (preference or "auto").lower()
    if pref == "cpu":
        return "cpu"
    gpu = detect_gpu()
    if pref in ("auto", "cuda") or pref.startswith("cuda:"):
        if gpu["cuda_available"]:
            return pref if pref.startswith("cuda:") else "cuda"
        if pref != "auto":
            logger.warning(f"Device '{preference}' requested but CUDA is not available — using CPU")
    return "cpu"


class Detector(ABC):
    backend: str = "base"
    license_note: str = ""

    def __init__(self, confidence: float = 0.4, image_size: int = 640, device: str = "cpu"):
        self.confidence = float(confidence)
        self.image_size = int(image_size)
        self.device = device
        self.loaded = False
        self.last_latency_ms = 0.0
        self.error: str = ""

    @abstractmethod
    def load(self) -> None:
        ...

    @abstractmethod
    def _detect(self, image: np.ndarray, metadata: dict | None) -> list[Detection]:
        ...

    def detect(self, image: np.ndarray, metadata: dict | None = None) -> list[Detection]:
        if not self.loaded:
            self.load()
        t0 = time.perf_counter()
        try:
            dets = self._detect(image, metadata)
        finally:
            self.last_latency_ms = (time.perf_counter() - t0) * 1000.0
        return [d for d in dets if d.confidence >= self.confidence]

    @property
    def device_label(self) -> str:
        return "CUDA GPU" if str(self.device).startswith("cuda") else "CPU"

    def info(self) -> dict:
        return {"backend": self.backend, "device": self.device, "device_label": self.device_label,
                "confidence": self.confidence, "image_size": self.image_size, "loaded": self.loaded,
                "license_note": self.license_note, "error": self.error,
                "last_latency_ms": round(self.last_latency_ms, 1)}


class UltralyticsDetector(Detector):
    backend = "ultralytics-yolo"
    license_note = "ultralytics package + YOLO11 weights: AGPL-3.0 (commercial licence required for closed deployment)"

    def __init__(self, weights: str | Path = "yolo11n.pt", confidence: float = 0.4, image_size: int = 640,
                 device: str = "auto", iou: float = 0.5, classes: list[int] | None = None, models_dir: Path | None = None):
        super().__init__(confidence, image_size, resolve_device(device))
        self.iou = iou
        self.classes = classes or [PERSON_CLASS_ID]
        self.weights = Path(weights)
        if not self.weights.is_absolute() and models_dir is not None:
            candidate = models_dir / "object_detection" / self.weights.name
            self.weights = candidate
        self._model = None

    def load(self) -> None:
        from ultralytics import YOLO  # AGPL-3.0
        self.weights.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Loading YOLO weights {self.weights.name} on {self.device}")
        self._model = YOLO(str(self.weights))
        self.loaded = True

    def _detect(self, image: np.ndarray, metadata: dict | None) -> list[Detection]:
        results = self._model.predict(image, imgsz=self.image_size, conf=self.confidence, iou=self.iou,
                                      device=self.device, classes=self.classes, verbose=False)
        out: list[Detection] = []
        if not results:
            return out
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return out
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        clss = boxes.cls.cpu().numpy().astype(int)
        names = results[0].names
        for b, c, k in zip(xyxy, confs, clss):
            out.append(Detection((float(b[0]), float(b[1]), float(b[2]), float(b[3])), float(c), int(k),
                                 str(names.get(int(k), "person"))))
        return out


class OnnxDetector(Detector):
    backend = "onnxruntime"
    license_note = "onnxruntime: MIT. Model licence depends on the exported weights."

    def __init__(self, model_path: str | Path, confidence: float = 0.4, image_size: int = 640,
                 device: str = "auto", iou: float = 0.5, classes: list[int] | None = None):
        super().__init__(confidence, image_size, "cpu")
        self.model_path = Path(model_path)
        self.iou = iou
        self.classes = set(classes or [PERSON_CLASS_ID])
        self._session = None
        self._input_name = ""
        self._pref = device

    def load(self) -> None:
        import onnxruntime as ort  # MIT
        providers = ["CPUExecutionProvider"]
        if self._pref != "cpu" and "CUDAExecutionProvider" in ort.get_available_providers():
            providers.insert(0, "CUDAExecutionProvider")
            self.device = "cuda"
        self._session = ort.InferenceSession(str(self.model_path), providers=providers)
        self._input_name = self._session.get_inputs()[0].name
        self.loaded = True

    def _detect(self, image: np.ndarray, metadata: dict | None) -> list[Detection]:
        import cv2
        h, w = image.shape[:2]
        canvas, scale, pad = letterbox(image, self.image_size)
        blob = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        output = self._session.run(None, {self._input_name: blob})[0]
        preds = output[0]
        if preds.shape[0] < preds.shape[1]:  # (84, N) -> (N, 84)
            preds = preds.T
        boxes, scores, class_ids = [], [], []
        for row in preds:
            cls_scores = row[4:]
            cid = int(np.argmax(cls_scores))
            score = float(cls_scores[cid])
            if score < self.confidence or cid not in self.classes:
                continue
            cx, cy, bw, bh = row[:4]
            boxes.append([float(cx - bw / 2), float(cy - bh / 2), float(bw), float(bh)])
            scores.append(score)
            class_ids.append(cid)
        keep = cv2.dnn.NMSBoxes(boxes, scores, self.confidence, self.iou) if boxes else []
        out = []
        for i in np.array(keep).flatten():
            x, y, bw, bh = boxes[i]
            box = unletterbox_box((x, y, x + bw, y + bh), scale, pad, w, h)
            out.append(Detection(box, scores[i], class_ids[i], "person"))
        return out


class HogPersonDetector(Detector):
    backend = "opencv-hog"
    license_note = "OpenCV HOG people detector: Apache-2.0. Low accuracy — fallback only."

    def __init__(self, confidence: float = 0.4, image_size: int = 640, device: str = "cpu"):
        super().__init__(confidence, image_size, "cpu")
        self._hog = None

    def load(self) -> None:
        import cv2
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self.loaded = True

    def _detect(self, image: np.ndarray, metadata: dict | None) -> list[Detection]:
        import cv2
        h, w = image.shape[:2]
        scale = min(1.0, 640.0 / max(w, 1))
        small = cv2.resize(image, (int(w * scale), int(h * scale))) if scale < 1.0 else image
        rects, weights = self._hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
        out = []
        for (x, y, bw, bh), wt in zip(rects, weights):
            conf = float(min(0.99, 0.45 + 0.25 * float(wt)))  # map SVM margin to a pseudo-confidence
            out.append(Detection((x / scale, y / scale, (x + bw) / scale, (y + bh) / scale), conf))
        return out


class GroundTruthDetector(Detector):
    backend = "ground-truth"
    license_note = "Synthetic ground truth — testing only."

    def load(self) -> None:
        self.loaded = True

    def _detect(self, image: np.ndarray, metadata: dict | None) -> list[Detection]:
        boxes = (metadata or {}).get("gt_boxes") or []
        return [Detection(tuple(float(v) for v in b["box"]), float(b.get("confidence", 0.9))) for b in boxes]


def create_detector(model_cfg: dict, models_dir: Path | None = None, force_backend: str | None = None) -> Detector:
    """Build the configured detector with graceful fallback (never raises)."""
    backend = (force_backend or model_cfg.get("backend") or "auto").lower()
    conf = float(model_cfg.get("confidence", 0.4))
    size = int(model_cfg.get("image_size", 640))
    device = model_cfg.get("device", "auto")
    weights = str(model_cfg.get("weights", "yolo11n.pt"))
    classes = list(model_cfg.get("classes", [PERSON_CLASS_ID]))
    iou = float(model_cfg.get("iou", 0.5))
    attempts: list[str] = []
    if backend == "groundtruth":
        det = GroundTruthDetector(conf, size, "cpu")
        det.load()
        return det
    if backend in ("auto", "onnx") and weights.lower().endswith(".onnx"):
        attempts.append("onnx")
    if backend in ("auto", "ultralytics"):
        attempts.append("ultralytics")
    if backend == "onnx" and "onnx" not in attempts:
        attempts.append("onnx")
    attempts.append("hog")
    last_error = ""
    for name in attempts:
        try:
            if name == "ultralytics":
                det = UltralyticsDetector(weights, conf, size, device, iou, classes, models_dir)
            elif name == "onnx":
                det = OnnxDetector(weights, conf, size, device, iou, classes)
            else:
                det = HogPersonDetector(conf, size)
            det.load()
            if last_error:
                det.error = f"Fallback active — {last_error}"
            return det
        except Exception as exc:
            last_error = f"{name} unavailable: {type(exc).__name__}: {exc}"
            logger.warning(last_error)
    det = HogPersonDetector(conf, size)
    det.load()
    det.error = last_error
    return det
