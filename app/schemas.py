from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=255)


class UserRead(ORMModel):
    id: UUID
    username: str
    full_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=6, max_length=255)
    is_admin: bool = False
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    is_admin: bool = False
    is_active: bool = True


class UserPasswordUpdate(BaseModel):
    password: str = Field(min_length=6, max_length=255)


class SessionRead(BaseModel):
    authenticated: bool
    user: Optional[UserRead] = None


class DetectionSettingsRead(ORMModel):
    id: int
    global_confidence: float = Field(ge=0.0, le=1.0)
    motorcycle_min_confidence: float = Field(ge=0.0, le=1.0)
    vehicle_min_confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime
    updated_at: datetime


class DetectionSettingsUpdate(BaseModel):
    global_confidence: float = Field(ge=0.0, le=1.0)
    motorcycle_min_confidence: float = Field(ge=0.0, le=1.0)
    vehicle_min_confidence: float = Field(ge=0.0, le=1.0)


class GpuAuditRuntimeRead(BaseModel):
    platform_system: str
    platform_release: str
    platform_version: str
    machine: str
    processor: str
    python_version: str
    torch_version: Optional[str] = None
    ultralytics_version: Optional[str] = None
    cuda_built_version: Optional[str] = None
    cuda_available: bool = False
    cuda_device_count: int = 0
    cuda_devices: list[str] = Field(default_factory=list)
    mps_built: bool = False
    mps_available: bool = False
    nvidia_smi_available: bool = False
    nvidia_smi_summary: Optional[str] = None
    ffmpeg_available: bool = False
    torch_runtime_error: Optional[str] = None


class GpuAuditConfigRead(BaseModel):
    default_inference_device: str
    default_model_path: str
    target_analysis_fps: float
    preview_fps: float
    inference_imgsz: int
    working_max_width: int
    save_annotated_video: bool


class GpuAuditChecklistItemRead(BaseModel):
    key: str
    title: str
    status: str
    summary: str
    detail: Optional[str] = None


class GpuAuditRecentJobRead(BaseModel):
    video_name: str
    status: str
    model_name: Optional[str] = None
    device: Optional[str] = None
    processing_fps: Optional[float] = None
    effective_analysis_fps: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GpuAuditCommandRead(BaseModel):
    label: str
    command: str


class GpuAuditRead(BaseModel):
    overall_status: str
    host_note: Optional[str] = None
    runtime: GpuAuditRuntimeRead
    config: GpuAuditConfigRead
    checklist: list[GpuAuditChecklistItemRead] = Field(default_factory=list)
    recent_jobs: list[GpuAuditRecentJobRead] = Field(default_factory=list)
    commands: list[GpuAuditCommandRead] = Field(default_factory=list)


class MasterClassRead(ORMModel):
    code: str
    label: str
    description: Optional[str]
    sort_order: int
    created_at: datetime
    updated_at: datetime


class MasterClassUpdateItem(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)


class MasterClassUpdate(BaseModel):
    items: list[MasterClassUpdateItem] = Field(default_factory=list, min_length=1, max_length=5)


class AnalysisJobRead(ORMModel):
    id: UUID
    video_upload_id: UUID
    status: str
    model_name: Optional[str]
    config_json: Optional[dict]
    summary_json: Optional[dict]
    annotated_relative_path: Optional[str]
    report_relative_path: Optional[str]
    total_frames: Optional[int]
    processed_frames: Optional[int]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class VideoUploadRead(ORMModel):
    id: UUID
    original_filename: str
    stored_filename: str
    relative_path: str
    description: Optional[str]
    mime_type: Optional[str]
    file_size_bytes: Optional[int]
    recorded_at: Optional[datetime]
    uploaded_by: Optional[str]
    status: str
    video_fps: Optional[float]
    frame_width: Optional[int]
    frame_height: Optional[int]
    frame_count: Optional[int]
    duration_seconds: Optional[float]
    processing_error: Optional[str]
    created_at: datetime
    updated_at: datetime
    analysis_job: Optional[AnalysisJobRead] = None


class VideoCountLineRead(ORMModel):
    id: UUID
    video_upload_id: Optional[UUID] = None
    name: str
    line_order: int
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


class VideoCountLineWrite(BaseModel):
    line_order: int = Field(ge=1, le=2)
    name: Optional[str] = Field(default=None, max_length=255)
    start_x: float = Field(ge=0.0, le=1.0)
    start_y: float = Field(ge=0.0, le=1.0)
    end_x: float = Field(ge=0.0, le=1.0)
    end_y: float = Field(ge=0.0, le=1.0)
    is_active: bool = True


class VideoCountLineUpsert(BaseModel):
    lines: list[VideoCountLineWrite] = Field(default_factory=list, max_length=2)


class VideoCountLineListRead(BaseModel):
    video_id: UUID
    source: str
    lines: list[VideoCountLineRead] = Field(default_factory=list)


class VideoUpdate(BaseModel):
    description: Optional[str] = None
    recorded_at: Optional[datetime] = None


class VideoEventRead(ORMModel):
    id: int
    sequence_no: int
    track_id: Optional[int]
    vehicle_class: str
    detected_label: Optional[str]
    golongan_code: str
    golongan_label: str
    count_line_order: Optional[int]
    count_line_name: Optional[str]
    direction: str
    crossed_at_seconds: float
    crossed_at_frame: int
    confidence: Optional[float]
    created_at: datetime


class GolonganTotalRead(ORMModel):
    id: UUID
    golongan_code: str
    golongan_label: str
    vehicle_count: int
    created_at: datetime
    updated_at: datetime


class VideoAnalysisRead(BaseModel):
    video: VideoUploadRead
    video_url: str
    annotated_video_url: Optional[str] = None
    analysis_overlay_url: Optional[str] = None
    analysis_stream_url: Optional[str] = None
    analysis_frame_url: Optional[str] = None
    job: Optional[AnalysisJobRead] = None
    count_lines: list[VideoCountLineRead] = Field(default_factory=list)
    master_classes: list[MasterClassRead] = Field(default_factory=list)
    totals: list[GolonganTotalRead] = Field(default_factory=list)
    recent_events: list[VideoEventRead] = Field(default_factory=list)
    progress_percent: float = 0.0
