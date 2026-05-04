from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _as_bool(value: str, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: str, default: float) -> float:
    if value is None:
        return default
    return float(value)


def _as_int(value: str, default: int) -> int:
    if value is None:
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    app_host: str
    app_port: int
    app_base_url: str
    session_secret_key: str
    database_url: str
    auto_create_tables: bool
    storage_root: Path
    upload_dir: Path
    playback_dir: Path
    thumbnail_dir: Path
    annotated_dir: Path
    reports_dir: Path
    preview_dir: Path
    default_model_path: str
    default_tracker_config: str
    default_confidence: float
    default_iou: float
    default_frame_stride: int
    default_target_analysis_fps: float
    default_preview_fps: float
    default_working_max_width: int
    default_preview_max_width: int
    default_preview_jpeg_quality: int
    default_inference_imgsz: int
    default_inference_device: str
    save_annotated_video: bool
    bootstrap_admin_username: str
    bootstrap_admin_password: str
    bootstrap_admin_full_name: str
    default_site_code: str
    default_site_name: str
    default_site_direction_normal_label: str
    default_site_direction_opposite_label: str
    default_line_start_x: float
    default_line_start_y: float
    default_line_end_x: float
    default_line_end_y: float


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    storage_root_value = os.getenv("STORAGE_ROOT", "storage")
    storage_root = (BASE_DIR / storage_root_value).resolve()

    return Settings(
        app_name=os.getenv("APP_NAME", "NiceCount"),
        app_env=os.getenv("APP_ENV", "development"),
        app_host=os.getenv("APP_HOST", "0.0.0.0"),
        app_port=_as_int(os.getenv("APP_PORT"), 8000),
        app_base_url=os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/"),
        session_secret_key=os.getenv("SESSION_SECRET_KEY", "vehicle-count-local-secret"),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:5432/vehicle_count",
        ),
        auto_create_tables=_as_bool(os.getenv("AUTO_CREATE_TABLES"), False),
        storage_root=storage_root,
        upload_dir=(storage_root / "uploads"),
        playback_dir=(storage_root / "playback"),
        thumbnail_dir=(storage_root / "thumbnails"),
        annotated_dir=(storage_root / "annotated"),
        reports_dir=(storage_root / "reports"),
        preview_dir=(storage_root / "previews"),
        default_model_path=os.getenv("DEFAULT_MODEL_PATH", "yolov8s.pt"),
        default_tracker_config=os.getenv("DEFAULT_TRACKER_CONFIG", "bytetrack.yaml"),
        default_confidence=_as_float(os.getenv("DEFAULT_CONFIDENCE"), 0.12),
        default_iou=_as_float(os.getenv("DEFAULT_IOU"), 0.45),
        default_frame_stride=max(_as_int(os.getenv("DEFAULT_FRAME_STRIDE"), 1), 1),
        default_target_analysis_fps=max(_as_float(os.getenv("DEFAULT_TARGET_ANALYSIS_FPS"), 8.0), 1.0),
        default_preview_fps=max(_as_float(os.getenv("DEFAULT_PREVIEW_FPS"), 6.0), 0.1),
        default_working_max_width=max(_as_int(os.getenv("DEFAULT_WORKING_MAX_WIDTH"), 1600), 0),
        default_preview_max_width=max(_as_int(os.getenv("DEFAULT_PREVIEW_MAX_WIDTH"), 960), 0),
        default_preview_jpeg_quality=min(max(_as_int(os.getenv("DEFAULT_PREVIEW_JPEG_QUALITY"), 70), 30), 95),
        default_inference_imgsz=max(_as_int(os.getenv("DEFAULT_INFERENCE_IMGSZ"), 1152), 320),
        default_inference_device=os.getenv("DEFAULT_INFERENCE_DEVICE", "auto").strip() or "auto",
        save_annotated_video=_as_bool(os.getenv("SAVE_ANNOTATED_VIDEO"), True),
        bootstrap_admin_username=os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin").strip(),
        bootstrap_admin_password=os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "admin123").strip(),
        bootstrap_admin_full_name=os.getenv("BOOTSTRAP_ADMIN_FULL_NAME", "Administrator").strip(),
        default_site_code=os.getenv("DEFAULT_SITE_CODE", "DEFAULT").strip(),
        default_site_name=os.getenv("DEFAULT_SITE_NAME", "Default Site").strip(),
        default_site_direction_normal_label=os.getenv("DEFAULT_SITE_DIRECTION_NORMAL_LABEL", "Normal").strip(),
        default_site_direction_opposite_label=os.getenv("DEFAULT_SITE_DIRECTION_OPPOSITE_LABEL", "Opposite").strip(),
        default_line_start_x=_as_float(os.getenv("DEFAULT_LINE_START_X"), 0.15),
        default_line_start_y=_as_float(os.getenv("DEFAULT_LINE_START_Y"), 0.58),
        default_line_end_x=_as_float(os.getenv("DEFAULT_LINE_END_X"), 0.85),
        default_line_end_y=_as_float(os.getenv("DEFAULT_LINE_END_Y"), 0.58),
    )
