from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import (
    DEFAULT_BUS_MIN_CONFIDENCE,
    DEFAULT_CAR_MIN_CONFIDENCE,
    DEFAULT_FRAME_STRIDE,
    DEFAULT_GLOBAL_CONFIDENCE,
    DEFAULT_IOU_THRESHOLD,
    DEFAULT_MOTORCYCLE_MIN_CONFIDENCE,
    DEFAULT_PREVIEW_FPS,
    DEFAULT_PREVIEW_JPEG_QUALITY,
    DEFAULT_PREVIEW_MAX_WIDTH,
    DEFAULT_TARGET_ANALYSIS_FPS,
    DEFAULT_TRUCK_MIN_CONFIDENCE,
    DEFAULT_VEHICLE_MIN_CONFIDENCE,
    DEFAULT_WORKING_MAX_WIDTH,
)
from app.models import DetectionSettings


def get_or_create_detection_settings(db: Session) -> DetectionSettings:
    settings_row = db.scalar(select(DetectionSettings).limit(1))
    if settings_row:
        updated = False
        if settings_row.car_min_confidence is None:
            settings_row.car_min_confidence = float(
                settings_row.vehicle_min_confidence or DEFAULT_CAR_MIN_CONFIDENCE
            )
            updated = True
        if settings_row.bus_min_confidence is None:
            settings_row.bus_min_confidence = max(
                float(settings_row.vehicle_min_confidence or DEFAULT_CAR_MIN_CONFIDENCE) + 0.04,
                DEFAULT_BUS_MIN_CONFIDENCE,
            )
            updated = True
        if settings_row.truck_min_confidence is None:
            settings_row.truck_min_confidence = max(
                float(settings_row.vehicle_min_confidence or DEFAULT_CAR_MIN_CONFIDENCE) + 0.08,
                DEFAULT_TRUCK_MIN_CONFIDENCE,
            )
            updated = True
        if settings_row.iou_threshold is None:
            settings_row.iou_threshold = DEFAULT_IOU_THRESHOLD
            updated = True
        if settings_row.frame_stride is None:
            settings_row.frame_stride = DEFAULT_FRAME_STRIDE
            updated = True
        if settings_row.target_analysis_fps is None:
            settings_row.target_analysis_fps = DEFAULT_TARGET_ANALYSIS_FPS
            updated = True
        if settings_row.preview_fps is None:
            settings_row.preview_fps = DEFAULT_PREVIEW_FPS
            updated = True
        if settings_row.working_max_width is None:
            settings_row.working_max_width = DEFAULT_WORKING_MAX_WIDTH
            updated = True
        if settings_row.preview_max_width is None:
            settings_row.preview_max_width = DEFAULT_PREVIEW_MAX_WIDTH
            updated = True
        if settings_row.preview_jpeg_quality is None:
            settings_row.preview_jpeg_quality = DEFAULT_PREVIEW_JPEG_QUALITY
            updated = True
        if updated:
            db.commit()
            db.refresh(settings_row)
        return settings_row

    settings_row = DetectionSettings(
        id=1,
        global_confidence=DEFAULT_GLOBAL_CONFIDENCE,
        motorcycle_min_confidence=DEFAULT_MOTORCYCLE_MIN_CONFIDENCE,
        car_min_confidence=DEFAULT_CAR_MIN_CONFIDENCE,
        bus_min_confidence=DEFAULT_BUS_MIN_CONFIDENCE,
        truck_min_confidence=DEFAULT_TRUCK_MIN_CONFIDENCE,
        vehicle_min_confidence=DEFAULT_VEHICLE_MIN_CONFIDENCE,
        iou_threshold=DEFAULT_IOU_THRESHOLD,
        frame_stride=DEFAULT_FRAME_STRIDE,
        target_analysis_fps=DEFAULT_TARGET_ANALYSIS_FPS,
        preview_fps=DEFAULT_PREVIEW_FPS,
        working_max_width=DEFAULT_WORKING_MAX_WIDTH,
        preview_max_width=DEFAULT_PREVIEW_MAX_WIDTH,
        preview_jpeg_quality=DEFAULT_PREVIEW_JPEG_QUALITY,
    )
    db.add(settings_row)
    db.commit()
    db.refresh(settings_row)
    return settings_row


def build_detection_settings_overrides(db: Session) -> dict:
    settings_row = get_or_create_detection_settings(db)
    return {
        "confidence_threshold": float(settings_row.global_confidence),
        "motorcycle_min_confidence": float(settings_row.motorcycle_min_confidence),
        "car_min_confidence": float(settings_row.car_min_confidence),
        "bus_min_confidence": float(settings_row.bus_min_confidence),
        "truck_min_confidence": float(settings_row.truck_min_confidence),
        "iou_threshold": float(settings_row.iou_threshold),
        "frame_stride": int(settings_row.frame_stride),
        "target_analysis_fps": float(settings_row.target_analysis_fps),
        "preview_fps": float(settings_row.preview_fps),
        "working_max_width": int(settings_row.working_max_width),
        "preview_max_width": int(settings_row.preview_max_width),
        "preview_jpeg_quality": int(settings_row.preview_jpeg_quality),
    }
