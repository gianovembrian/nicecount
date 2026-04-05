from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import (
    DEFAULT_GLOBAL_CONFIDENCE,
    DEFAULT_MOTORCYCLE_MIN_CONFIDENCE,
    DEFAULT_VEHICLE_MIN_CONFIDENCE,
)
from app.models import DetectionSettings


def get_or_create_detection_settings(db: Session) -> DetectionSettings:
    settings_row = db.scalar(select(DetectionSettings).limit(1))
    if settings_row:
        return settings_row

    settings_row = DetectionSettings(
        id=1,
        global_confidence=DEFAULT_GLOBAL_CONFIDENCE,
        motorcycle_min_confidence=DEFAULT_MOTORCYCLE_MIN_CONFIDENCE,
        vehicle_min_confidence=DEFAULT_VEHICLE_MIN_CONFIDENCE,
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
        "vehicle_min_confidence": float(settings_row.vehicle_min_confidence),
    }
