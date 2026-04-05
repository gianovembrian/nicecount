from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.constants import DEFAULT_MASTER_CLASSES
from app.database import get_db
from app.models import User
from app.schemas import (
    DetectionSettingsRead,
    DetectionSettingsUpdate,
    MasterClassRead,
    MasterClassUpdate,
)
from app.services.detection_settings import get_or_create_detection_settings
from app.services.master_classes import get_or_create_master_classes


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/detection", response_model=DetectionSettingsRead)
def get_detection_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> DetectionSettingsRead:
    settings_row = get_or_create_detection_settings(db)
    return DetectionSettingsRead.model_validate(settings_row)


@router.put("/detection", response_model=DetectionSettingsRead)
def update_detection_settings(
    payload: DetectionSettingsUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DetectionSettingsRead:
    settings_row = get_or_create_detection_settings(db)
    settings_row.global_confidence = payload.global_confidence
    settings_row.motorcycle_min_confidence = payload.motorcycle_min_confidence
    settings_row.vehicle_min_confidence = payload.vehicle_min_confidence
    db.commit()
    db.refresh(settings_row)
    return DetectionSettingsRead.model_validate(settings_row)


@router.get("/master-classes", response_model=list[MasterClassRead])
def get_master_classes(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[MasterClassRead]:
    rows = get_or_create_master_classes(db)
    return [MasterClassRead.model_validate(row) for row in rows]


@router.put("/master-classes", response_model=list[MasterClassRead])
def update_master_classes(
    payload: MasterClassUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[MasterClassRead]:
    rows = get_or_create_master_classes(db)
    row_map = {row.code: row for row in rows}
    valid_codes = set(DEFAULT_MASTER_CLASSES)
    received_codes: set[str] = set()

    for item in payload.items:
        normalized_code = (item.code or "").strip()
        if normalized_code not in valid_codes:
            raise HTTPException(status_code=400, detail=f"Unknown master class code: {normalized_code}")
        if normalized_code in received_codes:
            raise HTTPException(status_code=400, detail=f"Duplicate master class code: {normalized_code}")
        received_codes.add(normalized_code)

        row = row_map.get(normalized_code)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Master class not found: {normalized_code}")

        row.label = item.label.strip()
        row.description = (item.description or "").strip() or None

    db.commit()
    refreshed_rows = get_or_create_master_classes(db)
    return [MasterClassRead.model_validate(row) for row in refreshed_rows]
