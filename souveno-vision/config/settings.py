"""
Central application settings for SOUVENO VISION.

All configuration is read from environment variables (see .env.example),
with safe defaults so the demo runs out of the box with no .env file.
"""
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    # --- General ---
    app_name: str = "SOUVENO VISION"
    tagline: str = "See. Understand. Act. Measure."
    app_env: str = "development"
    demo_mode: bool = True
    log_level: str = "INFO"

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000

    # --- Paths ---
    base_dir: Path = BASE_DIR
    uploads_dir: Path = BASE_DIR / "uploads"
    outputs_dir: Path = BASE_DIR / "outputs"
    clips_dir: Path = BASE_DIR / "outputs" / "event_clips"
    processed_dir: Path = BASE_DIR / "outputs" / "processed"
    screenshots_dir: Path = BASE_DIR / "screenshots"
    models_dir: Path = BASE_DIR / "models"
    data_dir: Path = BASE_DIR / "data"
    logs_dir: Path = BASE_DIR / "logs"

    # --- Database ---
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'souveno_vision.db').as_posix()}"

    # --- Vision models ---
    detection_model: str = "yolo11n.pt"
    pose_model: str = "yolo11n-pose.pt"
    segmentation_model: str = "yolo11n-seg.pt"
    enable_pose: bool = False
    enable_segmentation: bool = False
    tracker: Literal["bytetrack", "botsort"] = "bytetrack"
    use_gpu: str = "auto"  # "auto" | "true" | "false"

    # --- Performance ---
    process_every_n_frames: int = 2
    input_resolution: int = 960

    # --- Spill detection (experimental) ---
    demo_spill_mode: bool = True
    spill_model_path: str = ""

    # --- AI summary / reasoning ---
    llm_api_key: str = ""
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-5"

    # --- Notifications ---
    notification_provider: str = "console"
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_recipient_numbers: str = ""

    # --- Expo Agent booking executors (all optional; approvals stay manual without them) ---
    razorpayx_key_id: str = ""
    razorpayx_key_secret: str = ""
    razorpayx_account_number: str = ""  # your RazorpayX current-account number (debit source)
    duffel_access_token: str = ""  # Duffel flights API; live token issues real tickets
    expo_auto_execute: bool = False  # if True, approved items execute immediately via the configured rails
    expo_public_url: str = ""  # e.g. https://expo.souveno.ai — used in approval notifications

    # --- RTSP / NVR (Stage 3) ---
    rtsp_default_username: str = ""
    rtsp_default_password: str = ""

    def ensure_directories(self) -> None:
        for d in [
            self.uploads_dir,
            self.outputs_dir,
            self.clips_dir,
            self.processed_dir,
            self.screenshots_dir,
            self.models_dir,
            self.data_dir,
            self.logs_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
