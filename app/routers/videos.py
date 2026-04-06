from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user
from app.config import get_settings
from app.constants import (
    DETECTED_TYPE_LABELS,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_PENDING,
    JOB_STATUS_PROCESSING,
    JOB_STATUS_QUEUED,
    VIDEO_STATUS_CONVERTING,
    VIDEO_STATUS_PROCESSING,
    VIDEO_STATUS_PROCESSED,
    VIDEO_STATUS_UPLOADED,
)
from app.database import get_db
from app.models import (
    AnalysisGolonganTotal,
    AnalysisJob,
    CountLine,
    Site,
    User,
    VehicleEvent,
    VideoCountAggregate,
    VideoCountLine,
    VideoUpload,
)
from app.schemas import (
    AnalysisJobRead,
    GolonganTotalRead,
    MasterClassRead,
    VideoAnalysisRead,
    VideoCountLineListRead,
    VideoCountLineRead,
    VideoCountLineUpsert,
    VideoEventRead,
    VideoUpdate,
    VideoUploadRead,
)
from app.services.analysis import build_process_config, launch_analysis_worker, request_analysis_stop
from app.services.detection_settings import build_detection_settings_overrides
from app.services.live_preview import delete_preview_artifacts, get_latest_preview_frame, preview_stream, start_preview
from app.services.master_classes import get_or_create_master_classes
from app.services.storage import (
    build_unique_upload_filename,
    build_storage_url,
    ensure_browser_playback,
    delete_relative_file,
    generate_video_thumbnail,
    is_standardized_upload_filename,
    playback_relative_path_for,
    save_upload_file,
    thumbnail_relative_path_for,
)
from app.services.video_metadata import probe_video
from app.services.video_conversion import (
    is_video_conversion_ready,
    launch_video_conversion_worker,
    playback_absolute_path_for,
    requires_video_conversion,
)


router = APIRouter(prefix="/api/videos", tags=["videos"])


def _video_query():
    return (
        select(VideoUpload)
        .options(joinedload(VideoUpload.analysis_job), joinedload(VideoUpload.count_lines))
        .order_by(VideoUpload.created_at.desc())
    )


def _get_default_site(db: Session) -> Site:
    settings = get_settings()
    site = db.scalar(select(Site).where(Site.code == settings.default_site_code))
    if site:
        return site

    site = db.scalar(select(Site).order_by(Site.created_at.asc()))
    if not site:
        raise HTTPException(status_code=500, detail="The default site is not available yet")
    return site


def _build_progress_percent(job: Optional[AnalysisJob]) -> float:
    if not job or not job.total_frames or not job.processed_frames:
        return 0.0
    if job.total_frames <= 0:
        return 0.0
    return max(0.0, min(100.0, (job.processed_frames / job.total_frames) * 100.0))


def _overlay_relative_path(job_id: UUID) -> str:
    return f"reports/{job_id}.overlay.json"


def _serialize_process_config(db: Session):
    config = build_process_config(build_detection_settings_overrides(db))
    return config, {
        "model_path": config.model_path,
        "tracker_config": config.tracker_config,
        "frame_stride": config.frame_stride,
        "target_analysis_fps": config.target_analysis_fps,
        "preview_fps": config.preview_fps,
        "working_max_width": config.working_max_width,
        "preview_max_width": config.preview_max_width,
        "preview_jpeg_quality": config.preview_jpeg_quality,
        "inference_imgsz": config.inference_imgsz,
        "inference_device": config.inference_device,
        "confidence_threshold": config.confidence_threshold,
        "motorcycle_min_confidence": config.motorcycle_min_confidence,
        "vehicle_min_confidence": config.vehicle_min_confidence,
        "iou_threshold": config.iou_threshold,
        "save_annotated_video": config.save_annotated_video,
    }


def _normalize_video_storage_filename(video: VideoUpload) -> bool:
    if is_standardized_upload_filename(video.stored_filename):
        return False

    settings = get_settings()
    old_absolute_path = settings.storage_root / video.relative_path
    if not old_absolute_path.exists():
        return False

    new_filename = build_unique_upload_filename(video.stored_filename, reference_time=video.created_at)
    new_absolute_path = settings.upload_dir / new_filename
    old_absolute_path.rename(new_absolute_path)

    delete_relative_file(thumbnail_relative_path_for(video.stored_filename))
    delete_relative_file(playback_relative_path_for(video.stored_filename))
    generate_video_thumbnail(new_absolute_path, new_filename)

    video.stored_filename = new_filename
    video.relative_path = new_absolute_path.relative_to(settings.storage_root).as_posix()
    return True


def _load_effective_count_lines(video: VideoUpload, db: Session) -> tuple[str, list[CountLine | VideoCountLine]]:
    video_lines = [line for line in (video.count_lines or []) if line.is_active]
    if video_lines:
        return "video", sorted(video_lines, key=lambda line: (line.line_order, line.created_at))

    site_lines = list(
        db.scalars(
            select(CountLine)
            .where(CountLine.site_id == video.site_id, CountLine.is_active.is_(True))
            .order_by(CountLine.line_order.asc(), CountLine.created_at.asc())
        )
    )
    if site_lines:
        return "site", site_lines[:1]

    return "empty", []


def _serialize_count_line(video_id: UUID, line: CountLine | VideoCountLine, source: str) -> VideoCountLineRead:
    payload = {
        "id": line.id,
        "video_upload_id": video_id if source == "video" else None,
        "name": line.name,
        "line_order": line.line_order,
        "start_x": line.start_x,
        "start_y": line.start_y,
        "end_x": line.end_x,
        "end_y": line.end_y,
        "is_active": line.is_active,
        "created_at": line.created_at,
        "updated_at": line.updated_at,
    }
    return VideoCountLineRead.model_validate(payload)


def _normalized_detected_label(vehicle_class: str, detected_label: Optional[str]) -> Optional[str]:
    normalized_vehicle_class = str(vehicle_class or "").strip().lower()
    if normalized_vehicle_class in DETECTED_TYPE_LABELS:
        return DETECTED_TYPE_LABELS[normalized_vehicle_class]
    return detected_label


def _serialize_golongan_total(row: AnalysisGolonganTotal, master_class_map: dict[str, str]) -> GolonganTotalRead:
    payload = {
        "id": row.id,
        "golongan_code": row.golongan_code,
        "golongan_label": master_class_map.get(row.golongan_code, row.golongan_label),
        "vehicle_count": row.vehicle_count,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    return GolonganTotalRead.model_validate(payload)


def _serialize_vehicle_event(row: VehicleEvent, master_class_map: dict[str, str]) -> VideoEventRead:
    payload = {
        "id": row.id,
        "sequence_no": row.sequence_no,
        "track_id": row.track_id,
        "vehicle_class": row.vehicle_class,
        "detected_label": _normalized_detected_label(row.vehicle_class, row.detected_label),
        "golongan_code": row.golongan_code,
        "golongan_label": master_class_map.get(row.golongan_code, row.golongan_label),
        "count_line_order": row.count_line_order,
        "count_line_name": row.count_line_name,
        "direction": row.direction,
        "crossed_at_seconds": row.crossed_at_seconds,
        "crossed_at_frame": row.crossed_at_frame,
        "confidence": row.confidence,
        "created_at": row.created_at,
    }
    return VideoEventRead.model_validate(payload)


def _reset_analysis_results(video: VideoUpload, db: Session) -> None:
    job = video.analysis_job

    db.execute(delete(VehicleEvent).where(VehicleEvent.video_upload_id == video.id))
    db.execute(delete(AnalysisGolonganTotal).where(AnalysisGolonganTotal.video_upload_id == video.id))
    db.execute(delete(VideoCountAggregate).where(VideoCountAggregate.video_upload_id == video.id))

    if job:
        delete_relative_file(job.annotated_relative_path)
        delete_relative_file(job.report_relative_path)
        delete_relative_file(_overlay_relative_path(job.id))
        delete_preview_artifacts(job.id)

        job.status = JOB_STATUS_PENDING
        job.summary_json = None
        job.annotated_relative_path = None
        job.report_relative_path = None
        job.total_frames = None
        job.processed_frames = None
        job.started_at = None
        job.finished_at = None
        job.error_message = None

    video.status = VIDEO_STATUS_UPLOADED
    video.processing_error = None


def _ensure_video_thumbnail(video: VideoUpload) -> None:
    settings = get_settings()
    thumbnail_relative_path = thumbnail_relative_path_for(video.stored_filename)
    thumbnail_absolute_path = settings.storage_root / thumbnail_relative_path
    if thumbnail_absolute_path.exists():
        return

    video_absolute_path = settings.storage_root / video.relative_path
    if not video_absolute_path.exists():
        return

    generate_video_thumbnail(video_absolute_path, video.stored_filename)


def _ensure_video_conversion_state(video: VideoUpload, *, auto_process: bool = False, force: bool = False) -> bool:
    if not requires_video_conversion(video.stored_filename, video.mime_type):
        return False

    if is_video_conversion_ready(video):
        if video.status == VIDEO_STATUS_CONVERTING:
            video.status = VIDEO_STATUS_UPLOADED
            video.processing_error = None
            return True
        return False

    if not force and video.status not in {VIDEO_STATUS_CONVERTING, VIDEO_STATUS_UPLOADED}:
        return False

    if video.status != VIDEO_STATUS_CONVERTING:
        video.status = VIDEO_STATUS_CONVERTING
        video.processing_error = None
        launch_video_conversion_worker(video.id, auto_process=auto_process)
        return True

    launch_video_conversion_worker(video.id, auto_process=auto_process)
    return False


def _resolve_playback_file(video: VideoUpload) -> tuple[str, str]:
    settings = get_settings()
    original_absolute_path = settings.storage_root / video.relative_path
    playback_absolute_path = playback_absolute_path_for(video)
    if playback_absolute_path.exists():
        return str(playback_absolute_path), "video/mp4"

    suffix = video.relative_path.rsplit(".", 1)[-1].lower() if "." in video.relative_path else ""
    if suffix == "mp4" and (video.mime_type or "").lower() in {"video/mp4", ""}:
        return str(original_absolute_path), "video/mp4"

    playback_relative_path = ensure_browser_playback(original_absolute_path, video.stored_filename)
    if playback_relative_path:
        playback_absolute_path = settings.storage_root / playback_relative_path
        if playback_absolute_path.exists():
            return str(playback_absolute_path), "video/mp4"
    return str(original_absolute_path), video.mime_type or "application/octet-stream"


def _playback_endpoint_url(video_id: UUID) -> str:
    return f"/api/videos/{video_id}/playback"


def _is_stale_running_job(job: Optional[AnalysisJob]) -> bool:
    if not job or job.status not in {JOB_STATUS_QUEUED, JOB_STATUS_PROCESSING}:
        return False

    reference_time = job.updated_at or job.started_at or job.created_at
    if reference_time is None:
        return False

    now = datetime.now(timezone.utc)
    return (now - reference_time.astimezone(timezone.utc)).total_seconds() > 45


def _build_analysis_response(video: VideoUpload, db: Session) -> VideoAnalysisRead:
    normalized_terminal_errors = False
    if video.analysis_job and video.analysis_job.status == JOB_STATUS_COMPLETED and video.analysis_job.error_message:
        video.analysis_job.error_message = None
        normalized_terminal_errors = True
    if video.status == VIDEO_STATUS_PROCESSED and video.processing_error:
        video.processing_error = None
        normalized_terminal_errors = True
    if normalized_terminal_errors:
        db.commit()
        db.refresh(video)

    line_source, effective_lines = _load_effective_count_lines(video, db)
    master_classes = get_or_create_master_classes(db)
    master_class_map = {row.code: row.label for row in master_classes}
    totals_rows = list(
        db.scalars(
            select(AnalysisGolonganTotal)
            .where(AnalysisGolonganTotal.video_upload_id == video.id)
            .order_by(AnalysisGolonganTotal.golongan_code.asc())
        )
    )
    totals_by_code = {row.golongan_code: row for row in totals_rows}
    ordered_totals = [
        _serialize_golongan_total(totals_by_code[golongan_code], master_class_map)
        for golongan_code in [row.code for row in master_classes]
        if golongan_code in totals_by_code
    ]

    event_rows = list(
        db.scalars(
            select(VehicleEvent)
            .where(VehicleEvent.video_upload_id == video.id)
            .order_by(VehicleEvent.sequence_no.asc())
        )
    )

    job_read = AnalysisJobRead.model_validate(video.analysis_job) if video.analysis_job else None
    overlay_url = None
    if video.analysis_job:
        overlay_relative_path = _overlay_relative_path(video.analysis_job.id)
        overlay_absolute_path = get_settings().storage_root / overlay_relative_path
        if overlay_absolute_path.exists():
            overlay_url = build_storage_url(overlay_relative_path)

    return VideoAnalysisRead(
        video=VideoUploadRead.model_validate(video),
        video_url=_playback_endpoint_url(video.id),
        annotated_video_url=build_storage_url(video.analysis_job.annotated_relative_path) if video.analysis_job else None,
        analysis_overlay_url=overlay_url,
        analysis_stream_url=(
            f"/api/videos/{video.id}/analysis/stream"
            if video.analysis_job and video.analysis_job.status in {JOB_STATUS_QUEUED, JOB_STATUS_PROCESSING}
            else None
        ),
        analysis_frame_url=(
            f"/api/videos/{video.id}/analysis/frame"
            if video.analysis_job and video.analysis_job.status in {JOB_STATUS_QUEUED, JOB_STATUS_PROCESSING}
            else None
        ),
        job=job_read,
        count_lines=[_serialize_count_line(video.id, line, line_source) for line in effective_lines],
        master_classes=[MasterClassRead.model_validate(row) for row in master_classes],
        totals=ordered_totals,
        recent_events=[_serialize_vehicle_event(row, master_class_map) for row in event_rows],
        progress_percent=_build_progress_percent(video.analysis_job),
    )


@router.get("", response_model=list[VideoUploadRead])
def list_videos(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[VideoUpload]:
    videos = list(db.scalars(_video_query()).unique())
    has_updates = False
    for video in videos:
        has_updates = _normalize_video_storage_filename(video) or has_updates
        has_updates = _ensure_video_conversion_state(video) or has_updates
        _ensure_video_thumbnail(video)
    if has_updates:
        db.commit()
    return videos


@router.post("", response_model=VideoUploadRead, status_code=status.HTTP_201_CREATED)
def upload_video(
    description: Optional[str] = Form(default=None),
    recorded_at: Optional[datetime] = Form(default=None),
    auto_process: bool = Form(default=False),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoUpload:
    site = _get_default_site(db)
    saved_file = save_upload_file(file)
    generate_video_thumbnail(saved_file.absolute_path, saved_file.stored_filename)
    metadata = probe_video(saved_file.absolute_path)
    requires_conversion = requires_video_conversion(saved_file.stored_filename, saved_file.mime_type)

    video = VideoUpload(
        site_id=site.id,
        original_filename=saved_file.original_filename,
        stored_filename=saved_file.stored_filename,
        relative_path=saved_file.relative_path,
        description=(description or "").strip() or None,
        mime_type=saved_file.mime_type,
        file_size_bytes=saved_file.file_size_bytes,
        recorded_at=recorded_at,
        uploaded_by=current_user.username,
        status=VIDEO_STATUS_CONVERTING if requires_conversion else VIDEO_STATUS_UPLOADED,
        **metadata,
    )
    db.add(video)
    db.flush()

    config, config_json = _serialize_process_config(db)
    job = AnalysisJob(
        video_upload_id=video.id,
        status=JOB_STATUS_PENDING,
        model_name=config.model_path,
        config_json=config_json,
    )
    db.add(job)
    db.commit()

    if requires_conversion:
        launch_video_conversion_worker(video.id, auto_process=auto_process)

    created_video = db.scalar(_video_query().where(VideoUpload.id == video.id))
    if auto_process and created_video and created_video.analysis_job and not requires_conversion:
        created_video.analysis_job.status = JOB_STATUS_QUEUED
        created_video.analysis_job.started_at = None
        created_video.analysis_job.finished_at = None
        created_video.analysis_job.processed_frames = None
        created_video.analysis_job.total_frames = None
        created_video.status = VIDEO_STATUS_PROCESSING
        db.commit()
        start_preview(created_video.analysis_job.id)
        launch_analysis_worker(created_video.id, created_video.analysis_job.id, None)
        created_video = db.scalar(_video_query().where(VideoUpload.id == video.id))

    if not created_video:
        raise HTTPException(status_code=500, detail="Failed to create the video record")
    return created_video


@router.get("/{video_id}", response_model=VideoUploadRead)
def get_video(video_id: UUID, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> VideoUpload:
    video = db.scalar(_video_query().where(VideoUpload.id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    has_updates = _normalize_video_storage_filename(video)
    has_updates = _ensure_video_conversion_state(video) or has_updates
    if has_updates:
        db.commit()
    _ensure_video_thumbnail(video)
    return video


@router.put("/{video_id}", response_model=VideoUploadRead)
def update_video(
    video_id: UUID,
    payload: VideoUpdate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoUpload:
    video = db.scalar(_video_query().where(VideoUpload.id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    video.description = (payload.description or "").strip() or None
    video.recorded_at = payload.recorded_at
    db.commit()
    db.refresh(video)
    return db.scalar(_video_query().where(VideoUpload.id == video_id))


@router.get("/{video_id}/playback")
def get_video_playback(
    video_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = db.scalar(_video_query().where(VideoUpload.id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    has_updates = _normalize_video_storage_filename(video)
    has_updates = _ensure_video_conversion_state(video, force=True) or has_updates
    if has_updates:
        db.commit()
        db.refresh(video)
    if requires_video_conversion(video.stored_filename, video.mime_type) and not is_video_conversion_ready(video):
        raise HTTPException(status_code=409, detail="Video conversion is still running. Please wait until the MP4 playback file is ready.")
    absolute_path, media_type = _resolve_playback_file(video)
    return FileResponse(absolute_path, media_type=media_type)


@router.get("/{video_id}/count-lines", response_model=VideoCountLineListRead)
def get_video_count_lines(
    video_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoCountLineListRead:
    video = db.scalar(_video_query().where(VideoUpload.id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    source, lines = _load_effective_count_lines(video, db)
    return VideoCountLineListRead(
        video_id=video.id,
        source=source,
        lines=[_serialize_count_line(video.id, line, source) for line in lines],
    )


@router.put("/{video_id}/count-lines", response_model=VideoCountLineListRead)
def upsert_video_count_lines(
    video_id: UUID,
    payload: VideoCountLineUpsert,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoCountLineListRead:
    video = db.scalar(_video_query().where(VideoUpload.id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.analysis_job and video.analysis_job.status in {JOB_STATUS_PROCESSING, JOB_STATUS_QUEUED} and not _is_stale_running_job(video.analysis_job):
        raise HTTPException(status_code=409, detail="Analysis is currently running. Stop or wait for it to finish before changing count lines")

    ordered_lines = sorted(payload.lines, key=lambda line: line.line_order)
    line_orders = [line.line_order for line in ordered_lines]
    if len(line_orders) != len(set(line_orders)):
        raise HTTPException(status_code=422, detail="Duplicate line order is not allowed")

    existing_lines = list(
        db.scalars(
            select(VideoCountLine)
            .where(VideoCountLine.video_upload_id == video.id)
            .order_by(VideoCountLine.line_order.asc(), VideoCountLine.created_at.asc())
        )
    )
    existing_by_order = {line.line_order: line for line in existing_lines}

    for existing_line in existing_lines:
        if existing_line.line_order not in line_orders:
            db.delete(existing_line)

    for item in ordered_lines:
        target = existing_by_order.get(item.line_order)
        if target is None:
            target = VideoCountLine(
                video_upload_id=video.id,
                line_order=item.line_order,
                name=item.name or f"Line {item.line_order}",
            )
            db.add(target)
        target.name = (item.name or f"Line {item.line_order}").strip() or f"Line {item.line_order}"
        target.start_x = item.start_x
        target.start_y = item.start_y
        target.end_x = item.end_x
        target.end_y = item.end_y
        target.is_active = item.is_active

    _reset_analysis_results(video, db)
    db.commit()
    db.expire_all()
    video = db.scalar(_video_query().where(VideoUpload.id == video_id))
    source, lines = _load_effective_count_lines(video, db)
    return VideoCountLineListRead(
        video_id=video.id,
        source=source,
        lines=[_serialize_count_line(video.id, line, source) for line in lines],
    )


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(video_id: UUID, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    video = db.scalar(_video_query().where(VideoUpload.id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.analysis_job and video.analysis_job.status in {JOB_STATUS_PROCESSING, JOB_STATUS_QUEUED}:
        raise HTTPException(status_code=409, detail="The video is currently being analyzed and cannot be deleted yet")

    delete_relative_file(video.relative_path)
    delete_relative_file(playback_relative_path_for(video.stored_filename))
    delete_relative_file(thumbnail_relative_path_for(video.stored_filename))
    if video.analysis_job:
        delete_relative_file(video.analysis_job.annotated_relative_path)
        delete_relative_file(video.analysis_job.report_relative_path)
        delete_relative_file(_overlay_relative_path(video.analysis_job.id))
        delete_preview_artifacts(video.analysis_job.id)

    db.delete(video)
    db.commit()


@router.post("/{video_id}/analysis/start", response_model=AnalysisJobRead)
def start_analysis(
    video_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisJob:
    video = db.scalar(_video_query().where(VideoUpload.id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if not video.analysis_job:
        video.analysis_job = AnalysisJob(video_upload_id=video.id, status=JOB_STATUS_PENDING)
        db.add(video.analysis_job)
        db.commit()
        db.refresh(video)

    conversion_state_updated = _ensure_video_conversion_state(video, auto_process=True, force=True)
    if conversion_state_updated:
        db.commit()
        db.refresh(video)

    if requires_video_conversion(video.stored_filename, video.mime_type) and not is_video_conversion_ready(video):
        raise HTTPException(
            status_code=409,
            detail="Video conversion is still running. Please wait until the MP4 playback file is ready before starting analysis.",
        )

    job = video.analysis_job
    if job.status in {JOB_STATUS_PROCESSING, JOB_STATUS_QUEUED}:
        if not _is_stale_running_job(job):
            raise HTTPException(status_code=409, detail="Analysis is already running")

    delete_preview_artifacts(job.id)
    delete_relative_file(_overlay_relative_path(job.id))

    config, config_json = _serialize_process_config(db)

    job.status = JOB_STATUS_QUEUED
    job.error_message = None
    job.summary_json = None
    job.annotated_relative_path = None
    job.report_relative_path = None
    job.started_at = None
    job.finished_at = None
    job.processed_frames = None
    job.total_frames = None
    job.model_name = config.model_path
    job.config_json = config_json
    video.status = VIDEO_STATUS_PROCESSING
    video.processing_error = None
    db.commit()

    start_preview(job.id)
    launch_analysis_worker(video.id, job.id, None)
    db.refresh(job)
    return job


@router.post("/{video_id}/analysis/stop", response_model=AnalysisJobRead)
def stop_analysis(
    video_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisJob:
    video = db.scalar(_video_query().where(VideoUpload.id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    job = video.analysis_job
    if not job or job.status not in {JOB_STATUS_PROCESSING, JOB_STATUS_QUEUED}:
        raise HTTPException(status_code=409, detail="Analysis is not currently running")

    if _is_stale_running_job(job):
        _reset_analysis_results(video, db)
        if video.analysis_job:
            video.analysis_job.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)
        return job

    request_analysis_stop(job.id)
    db.refresh(job)
    return job


@router.post("/{video_id}/analysis/clear", status_code=status.HTTP_204_NO_CONTENT)
def clear_analysis_logs(
    video_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    video = db.scalar(_video_query().where(VideoUpload.id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    job = video.analysis_job
    if job and job.status in {JOB_STATUS_PROCESSING, JOB_STATUS_QUEUED} and not _is_stale_running_job(job):
        raise HTTPException(status_code=409, detail="Analysis is currently running and logs cannot be cleared yet")

    _reset_analysis_results(video, db)
    db.commit()


@router.get("/{video_id}/analysis", response_model=VideoAnalysisRead)
def get_analysis(
    video_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoAnalysisRead:
    video = db.scalar(_video_query().where(VideoUpload.id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    has_updates = _normalize_video_storage_filename(video)
    has_updates = _ensure_video_conversion_state(video) or has_updates
    if has_updates:
        db.commit()
    _ensure_video_thumbnail(video)
    return _build_analysis_response(video, db)


@router.get("/{video_id}/analysis/events", response_model=list[VideoEventRead])
def list_analysis_events(
    video_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[VehicleEvent]:
    video = db.get(VideoUpload, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    rows = db.scalars(
        select(VehicleEvent)
        .where(VehicleEvent.video_upload_id == video_id)
        .order_by(VehicleEvent.sequence_no.asc())
    )
    return list(rows)


@router.get("/{video_id}/analysis/totals", response_model=list[GolonganTotalRead])
def list_analysis_totals(
    video_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AnalysisGolonganTotal]:
    video = db.get(VideoUpload, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    rows = db.scalars(
        select(AnalysisGolonganTotal)
        .where(AnalysisGolonganTotal.video_upload_id == video_id)
        .order_by(AnalysisGolonganTotal.golongan_code.asc())
    )
    return list(rows)


@router.get("/{video_id}/analysis/stream")
def stream_analysis_preview(
    video_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = db.scalar(_video_query().where(VideoUpload.id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if not video.analysis_job:
        raise HTTPException(status_code=404, detail="Analysis job is not available yet")

    return StreamingResponse(
        preview_stream(video.analysis_job.id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/{video_id}/analysis/frame")
def get_analysis_preview_frame(
    video_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = db.scalar(_video_query().where(VideoUpload.id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if not video.analysis_job:
        raise HTTPException(status_code=404, detail="Analysis job is not available yet")

    frame_bytes, frame_sequence, is_finished = get_latest_preview_frame(video.analysis_job.id)
    if not frame_bytes:
        return Response(status_code=204, headers={"X-Preview-Finished": "1" if is_finished else "0"})

    return Response(
        content=frame_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Frame-Sequence": str(frame_sequence),
            "X-Preview-Finished": "1" if is_finished else "0",
        },
    )
