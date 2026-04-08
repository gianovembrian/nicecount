from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.constants import (
    DEFAULT_GLOBAL_CONFIDENCE,
    DEFAULT_MOTORCYCLE_MIN_CONFIDENCE,
    DEFAULT_VEHICLE_MIN_CONFIDENCE,
)
from app.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DetectionSettings(TimestampMixin, Base):
    __tablename__ = "detection_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    global_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=DEFAULT_GLOBAL_CONFIDENCE)
    motorcycle_min_confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=DEFAULT_MOTORCYCLE_MIN_CONFIDENCE,
    )
    vehicle_min_confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=DEFAULT_VEHICLE_MIN_CONFIDENCE,
    )


class MasterClass(TimestampMixin, Base):
    __tablename__ = "master_classes"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)


class Site(TimestampMixin, Base):
    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location_description: Mapped[Optional[str]] = mapped_column(Text)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    direction_normal_label: Mapped[str] = mapped_column(String(255), nullable=False, default="Normal")
    direction_opposite_label: Mapped[str] = mapped_column(String(255), nullable=False, default="Opposite")

    count_lines: Mapped[list["CountLine"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
        order_by="CountLine.line_order",
    )
    videos: Mapped[list["VideoUpload"]] = relationship(back_populates="site")


class CountLine(TimestampMixin, Base):
    __tablename__ = "count_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    line_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    start_x: Mapped[float] = mapped_column(Float, nullable=False)
    start_y: Mapped[float] = mapped_column(Float, nullable=False)
    end_x: Mapped[float] = mapped_column(Float, nullable=False)
    end_y: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    site: Mapped["Site"] = relationship(back_populates="count_lines")


class VideoUpload(TimestampMixin, Base):
    __tablename__ = "video_uploads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"))
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    stored_filename: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    mime_type: Mapped[Optional[str]] = mapped_column(String(255))
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    recorded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    video_fps: Mapped[Optional[float]] = mapped_column(Float)
    frame_width: Mapped[Optional[int]] = mapped_column(Integer)
    frame_height: Mapped[Optional[int]] = mapped_column(Integer)
    frame_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)
    processing_error: Mapped[Optional[str]] = mapped_column(Text)

    site: Mapped["Site"] = relationship(back_populates="videos")
    analysis_job: Mapped[Optional["AnalysisJob"]] = relationship(
        back_populates="video_upload",
        cascade="all, delete-orphan",
        uselist=False,
    )
    vehicle_events: Mapped[list["VehicleEvent"]] = relationship(
        back_populates="video_upload",
        cascade="all, delete-orphan",
        order_by="VehicleEvent.sequence_no",
    )
    count_lines: Mapped[list["VideoCountLine"]] = relationship(
        back_populates="video_upload",
        cascade="all, delete-orphan",
        order_by="VideoCountLine.line_order",
    )
    count_aggregates: Mapped[list["VideoCountAggregate"]] = relationship(
        back_populates="video_upload",
        cascade="all, delete-orphan",
    )
    golongan_totals: Mapped[list["AnalysisGolonganTotal"]] = relationship(
        back_populates="video_upload",
        cascade="all, delete-orphan",
        order_by="AnalysisGolonganTotal.golongan_code",
    )


class VideoCountLine(TimestampMixin, Base):
    __tablename__ = "video_count_lines"
    __table_args__ = (
        UniqueConstraint("video_upload_id", "line_order", name="uq_video_count_line_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("video_uploads.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    line_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    start_x: Mapped[float] = mapped_column(Float, nullable=False)
    start_y: Mapped[float] = mapped_column(Float, nullable=False)
    end_x: Mapped[float] = mapped_column(Float, nullable=False)
    end_y: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    video_upload: Mapped["VideoUpload"] = relationship(back_populates="count_lines")


class AnalysisJob(TimestampMixin, Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("video_uploads.id", ondelete="CASCADE"),
        unique=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[Optional[str]] = mapped_column(String(255))
    config_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    summary_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    annotated_relative_path: Mapped[Optional[str]] = mapped_column(Text)
    report_relative_path: Mapped[Optional[str]] = mapped_column(Text)
    total_frames: Mapped[Optional[int]] = mapped_column(BigInteger)
    processed_frames: Mapped[Optional[int]] = mapped_column(BigInteger)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    video_upload: Mapped["VideoUpload"] = relationship(back_populates="analysis_job")
    vehicle_events: Mapped[list["VehicleEvent"]] = relationship(
        back_populates="analysis_job",
        cascade="all, delete-orphan",
    )
    count_aggregates: Mapped[list["VideoCountAggregate"]] = relationship(
        back_populates="analysis_job",
        cascade="all, delete-orphan",
    )
    golongan_totals: Mapped[list["AnalysisGolonganTotal"]] = relationship(
        back_populates="analysis_job",
        cascade="all, delete-orphan",
        order_by="AnalysisGolonganTotal.golongan_code",
    )


class VehicleEvent(Base):
    __tablename__ = "vehicle_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    video_upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("video_uploads.id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"))
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    track_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    vehicle_class: Mapped[str] = mapped_column(String(50), nullable=False)
    detected_label: Mapped[Optional[str]] = mapped_column(String(100))
    vehicle_type_code: Mapped[Optional[str]] = mapped_column(String(100))
    vehicle_type_label: Mapped[Optional[str]] = mapped_column(String(255))
    golongan_code: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("master_classes.code", ondelete="RESTRICT"),
        nullable=False,
    )
    golongan_label: Mapped[str] = mapped_column(String(100), nullable=False)
    source_label: Mapped[Optional[str]] = mapped_column(String(100))
    count_line_order: Mapped[Optional[int]] = mapped_column(Integer)
    count_line_name: Mapped[Optional[str]] = mapped_column(String(255))
    direction: Mapped[str] = mapped_column(String(50), nullable=False)
    crossed_at_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    crossed_at_frame: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    speed_kph: Mapped[Optional[float]] = mapped_column(Float)
    bbox_x1: Mapped[Optional[float]] = mapped_column(Float)
    bbox_y1: Mapped[Optional[float]] = mapped_column(Float)
    bbox_x2: Mapped[Optional[float]] = mapped_column(Float)
    bbox_y2: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    video_upload: Mapped["VideoUpload"] = relationship(back_populates="vehicle_events")
    analysis_job: Mapped["AnalysisJob"] = relationship(back_populates="vehicle_events")


class AnalysisGolonganTotal(Base):
    __tablename__ = "analysis_golongan_totals"
    __table_args__ = (
        UniqueConstraint("analysis_job_id", "golongan_code", name="uq_analysis_golongan_total_job"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("video_uploads.id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    golongan_code: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("master_classes.code", ondelete="RESTRICT"),
        nullable=False,
    )
    golongan_label: Mapped[str] = mapped_column(String(100), nullable=False)
    vehicle_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    video_upload: Mapped["VideoUpload"] = relationship(back_populates="golongan_totals")
    analysis_job: Mapped["AnalysisJob"] = relationship(back_populates="golongan_totals")


class VideoCountAggregate(Base):
    __tablename__ = "video_count_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "video_upload_id",
            "bucket_type",
            "bucket_index",
            "direction",
            "vehicle_class",
            name="uq_video_count_aggregate_bucket",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("video_uploads.id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"))
    bucket_type: Mapped[str] = mapped_column(String(50), nullable=False)
    bucket_index: Mapped[int] = mapped_column(Integer, nullable=False)
    bucket_start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    bucket_end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    bucket_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    bucket_ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    direction: Mapped[str] = mapped_column(String(50), nullable=False)
    vehicle_class: Mapped[str] = mapped_column(String(50), nullable=False)
    vehicle_count: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_speed_kph: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    video_upload: Mapped["VideoUpload"] = relationship(back_populates="count_aggregates")
    analysis_job: Mapped["AnalysisJob"] = relationship(back_populates="count_aggregates")
