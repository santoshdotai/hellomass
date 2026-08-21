"""
Centralized vision-model configuration ("Model Manager", Phase 26).

Adding a new model or swapping model size is a config change here —
never a code change in the pipeline.
"""
from pathlib import Path
from config.settings import settings

# COCO classes SOUVENO VISION cares about for a cafe environment.
RELEVANT_CLASSES = {
    0: "person",
    56: "chair",
    60: "dining table",
    41: "cup",
    39: "bottle",
    45: "bowl",
    24: "backpack",
    26: "handbag",
    67: "cell phone",
}

MODEL_REGISTRY = {
    "detection": {
        "nano": "yolo11n.pt",
        "small": "yolo11s.pt",
        "medium": "yolo11m.pt",
    },
    "pose": {
        "nano": "yolo11n-pose.pt",
    },
    "segmentation": {
        "nano": "yolo11n-seg.pt",
    },
}


def get_model_path(kind: str, filename: str) -> Path:
    """Return the local path a model should live at (auto-downloaded by ultralytics on first use)."""
    subdir = {
        "detection": "object_detection",
        "pose": "pose",
        "segmentation": "segmentation",
        "custom": "custom",
    }.get(kind, "object_detection")
    return settings.models_dir / subdir / filename


CURRENT_MODEL_CONFIG = {
    "detection_model": settings.detection_model,
    "pose_model": settings.pose_model,
    "segmentation_model": settings.segmentation_model,
    "enable_pose": settings.enable_pose,
    "enable_segmentation": settings.enable_segmentation,
    "tracker": settings.tracker,
    "spill_model": "Not Installed" if not settings.spill_model_path else settings.spill_model_path,
}
