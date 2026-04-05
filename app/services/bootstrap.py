from __future__ import annotations

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.auth import hash_password, normalize_username
from app.config import get_settings
from app.constants import (
    DEFAULT_GLOBAL_CONFIDENCE,
    DEFAULT_MASTER_CLASSES,
    DEFAULT_MOTORCYCLE_MIN_CONFIDENCE,
    DEFAULT_VEHICLE_MIN_CONFIDENCE,
)
from app.models import CountLine, DetectionSettings, MasterClass, Site, User


def ensure_bootstrap_data(db: Session) -> None:
    inspector = inspect(db.bind)
    table_names = set(inspector.get_table_names())
    required_tables = {"users", "sites", "count_lines"}
    if not required_tables.issubset(table_names):
        return

    _ensure_admin_user(db)
    _ensure_default_site(db)
    if "detection_settings" in table_names:
        _ensure_detection_settings(db)
    if "master_classes" in table_names:
        _ensure_master_classes(db)


def _ensure_admin_user(db: Session) -> None:
    settings = get_settings()
    username = normalize_username(settings.bootstrap_admin_username)
    existing_user = db.scalar(select(User).where(User.username == username))
    if existing_user:
        return

    db.add(
        User(
            username=username,
            full_name=settings.bootstrap_admin_full_name,
            password_hash=hash_password(settings.bootstrap_admin_password),
            is_admin=True,
            is_active=True,
        )
    )
    db.commit()


def _ensure_default_site(db: Session) -> None:
    settings = get_settings()
    site = db.scalar(select(Site).where(Site.code == settings.default_site_code))
    if not site:
        site = Site(
            code=settings.default_site_code,
            name=settings.default_site_name,
            direction_normal_label=settings.default_site_direction_normal_label,
            direction_opposite_label=settings.default_site_direction_opposite_label,
        )
        db.add(site)
        db.commit()
        db.refresh(site)

    active_line = db.scalar(
        select(CountLine)
        .where(CountLine.site_id == site.id, CountLine.is_active.is_(True))
        .order_by(CountLine.line_order.asc(), CountLine.created_at.asc())
    )
    if active_line:
        return

    db.add(
        CountLine(
            site_id=site.id,
            name="Default Line",
            line_order=1,
            start_x=settings.default_line_start_x,
            start_y=settings.default_line_start_y,
            end_x=settings.default_line_end_x,
            end_y=settings.default_line_end_y,
            is_active=True,
        )
    )
    db.commit()


def _ensure_detection_settings(db: Session) -> None:
    settings_row = db.scalar(select(DetectionSettings).limit(1))
    if settings_row:
        return

    db.add(
        DetectionSettings(
            id=1,
            global_confidence=DEFAULT_GLOBAL_CONFIDENCE,
            motorcycle_min_confidence=DEFAULT_MOTORCYCLE_MIN_CONFIDENCE,
            vehicle_min_confidence=DEFAULT_VEHICLE_MIN_CONFIDENCE,
        )
    )
    db.commit()


def _ensure_master_classes(db: Session) -> None:
    existing_codes = set(db.scalars(select(MasterClass.code)))
    created = False

    for code, payload in DEFAULT_MASTER_CLASSES.items():
        if code in existing_codes:
            continue
        db.add(
            MasterClass(
                code=code,
                label=payload["label"],
                description=payload["description"],
                sort_order=payload["sort_order"],
            )
        )
        created = True

    if created:
        db.commit()
