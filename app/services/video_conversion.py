from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.constants import (
    JOB_STATUS_PROCESSING,
    JOB_STATUS_QUEUED,
    VIDEO_STATUS_CONVERTING,
    VIDEO_STATUS_FAILED,
    VIDEO_STATUS_PROCESSING,
    VIDEO_STATUS_UPLOADED,
)
from app.database import SessionLocal
from app.models import AnalysisJob, VideoUpload
from app.services.storage import ensure_browser_playback, playback_relative_path_for

_ACTIVE_CONVERSIONS: set[UUID] = set()
_ACTIVE_CONVERSIONS_LOCK = threading.Lock()


def requires_video_conversion(stored_filename: str, mime_type: Optional[str] = None) -> bool:
    suffix = Path(stored_filename or "").suffix.lower()
    normalized_mime = (mime_type or "").split(";", 1)[0].strip().lower()
    if suffix != ".mp4":
        return True
    return bool(normalized_mime) and normalized_mime not in {"video/mp4", "application/mp4"}


def playback_absolute_path_for(video: VideoUpload) -> Path:
    settings = get_settings()
    return settings.storage_root / playback_relative_path_for(video.stored_filename)


def is_video_conversion_ready(video: VideoUpload) -> bool:
    if not requires_video_conversion(video.stored_filename, video.mime_type):
        return True
    playback_path = playback_absolute_path_for(video)
    return playback_path.exists() and playback_path.stat().st_size > 0


def resolve_analysis_video_path(video: VideoUpload) -> Path:
    settings = get_settings()
    if requires_video_conversion(video.stored_filename, video.mime_type):
        playback_path = playback_absolute_path_for(video)
        if playback_path.exists() and playback_path.stat().st_size > 0:
            return playback_path
    return settings.storage_root / video.relative_path


def launch_video_conversion_worker(video_id: UUID, auto_process: bool = False) -> bool:
    with _ACTIVE_CONVERSIONS_LOCK:
        if video_id in _ACTIVE_CONVERSIONS:
            return False
        _ACTIVE_CONVERSIONS.add(video_id)

    worker = threading.Thread(
        target=run_video_conversion,
        args=(video_id, auto_process),
        daemon=True,
        name=f"conversion-{video_id}",
    )
    worker.start()
    return True


def run_video_conversion(video_id: UUID, auto_process: bool = False) -> None:
    db = SessionLocal()
    try:
        video = db.scalar(
            select(VideoUpload)
            .options(joinedload(VideoUpload.analysis_job))
            .where(VideoUpload.id == video_id)
        )
        if not video:
            return

        if not requires_video_conversion(video.stored_filename, video.mime_type):
            if video.status == VIDEO_STATUS_CONVERTING:
                video.status = VIDEO_STATUS_UPLOADED
                video.processing_error = None
                db.commit()
            return

        source_path = get_settings().storage_root / video.relative_path
        if not source_path.exists():
            video.status = VIDEO_STATUS_FAILED
            video.processing_error = "The original uploaded video file is missing."
            db.commit()
            return

        playback_relative_path = ensure_browser_playback(source_path, video.stored_filename)
        if not playback_relative_path:
            video.status = VIDEO_STATUS_FAILED
            video.processing_error = "Failed to convert the uploaded video to MP4 playback format."
            db.commit()
            return

        video.status = VIDEO_STATUS_UPLOADED
        video.processing_error = None
        db.commit()

        if auto_process and video.analysis_job:
            job = video.analysis_job
            if job.status not in {JOB_STATUS_PROCESSING, JOB_STATUS_QUEUED}:
                from app.services.analysis import launch_analysis_worker
                from app.services.live_preview import start_preview

                job.status = JOB_STATUS_QUEUED
                job.error_message = None
                job.summary_json = None
                job.annotated_relative_path = None
                job.report_relative_path = None
                job.started_at = None
                job.finished_at = None
                job.processed_frames = None
                job.total_frames = None
                video.status = VIDEO_STATUS_PROCESSING
                video.processing_error = None
                db.commit()

                start_preview(job.id)
                launch_analysis_worker(video.id, job.id, None)
    except Exception as exc:
        video = db.get(VideoUpload, video_id)
        if video:
            video.status = VIDEO_STATUS_FAILED
            video.processing_error = str(exc)
            db.commit()
    finally:
        with _ACTIVE_CONVERSIONS_LOCK:
            _ACTIVE_CONVERSIONS.discard(video_id)
        db.close()
