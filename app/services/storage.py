from __future__ import annotations

import re
import secrets
import shutil
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from app.config import get_settings


STANDARDIZED_UPLOAD_FILENAME_RE = re.compile(r"^\d{12}_[0-9a-f]{4}\.[a-z0-9]+$")


@dataclass(frozen=True)
class SavedFile:
    original_filename: str
    stored_filename: str
    relative_path: str
    absolute_path: Path
    mime_type: Optional[str]
    file_size_bytes: int


def ensure_storage_layout() -> None:
    settings = get_settings()
    for path in (
        settings.storage_root,
        settings.upload_dir,
        settings.playback_dir,
        settings.thumbnail_dir,
        settings.annotated_dir,
        settings.reports_dir,
        settings.preview_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _safe_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix or ".bin"


def is_standardized_upload_filename(filename: str) -> bool:
    return bool(STANDARDIZED_UPLOAD_FILENAME_RE.fullmatch((filename or "").lower()))


def _build_standardized_filename(filename: str, reference_time: Optional[datetime] = None) -> str:
    timestamp_source = reference_time or datetime.now()
    timestamp = timestamp_source.strftime("%d%m%Y%H%M")
    random_hex = secrets.token_hex(2)
    return f"{timestamp}_{random_hex}{_safe_suffix(filename)}"


def build_unique_upload_filename(filename: str, reference_time: Optional[datetime] = None) -> str:
    settings = get_settings()
    for _ in range(10):
        stored_filename = _build_standardized_filename(filename, reference_time=reference_time)
        if not (settings.upload_dir / stored_filename).exists():
            return stored_filename
    raise RuntimeError("Failed to generate a unique upload filename")


def thumbnail_relative_path_for(stored_filename: str) -> str:
    stem = Path(stored_filename).stem
    return f"thumbnails/{stem}.jpg"


def playback_relative_path_for(stored_filename: str) -> str:
    stem = Path(stored_filename).stem
    return f"playback/{stem}.mp4"


def save_upload_file(file: UploadFile) -> SavedFile:
    settings = get_settings()
    ensure_storage_layout()

    source_filename = file.filename or "upload.bin"
    stored_filename = build_unique_upload_filename(source_filename)
    absolute_path = settings.upload_dir / stored_filename
    relative_path = absolute_path.relative_to(settings.storage_root).as_posix()

    with absolute_path.open("wb") as destination:
        shutil.copyfileobj(file.file, destination)

    return SavedFile(
        original_filename=file.filename or stored_filename,
        stored_filename=stored_filename,
        relative_path=relative_path,
        absolute_path=absolute_path,
        mime_type=file.content_type,
        file_size_bytes=absolute_path.stat().st_size,
    )


def generate_video_thumbnail(video_path: Path, stored_filename: str) -> Optional[str]:
    settings = get_settings()
    ensure_storage_layout()

    try:
        import cv2
    except ImportError:
        return None

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return None

    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    target_frame = max(int(frame_count * 0.1), 1) if frame_count > 1 else 0
    if target_frame > 0:
        capture.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

    ok, frame = capture.read()
    if not ok:
        capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, frame = capture.read()
    capture.release()

    if not ok or frame is None:
        return None

    height, width = frame.shape[:2]
    target_width = min(width, 320) if width else 320
    if width and height and width > target_width:
        target_height = max(int(height * (target_width / width)), 1)
        frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)

    relative_path = thumbnail_relative_path_for(stored_filename)
    absolute_path = settings.storage_root / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(absolute_path), frame):
        return None
    return relative_path


def ensure_browser_playback(video_path: Path, stored_filename: str, max_width: int = 1280) -> Optional[str]:
    settings = get_settings()
    ensure_storage_layout()

    relative_path = playback_relative_path_for(stored_filename)
    absolute_path = settings.storage_root / relative_path
    if absolute_path.exists() and absolute_path.stat().st_size > 0:
        return relative_path

    try:
        import cv2
    except ImportError:
        return None

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return None

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0) or 25.0
    frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0) or 0
    frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0) or 0
    if frame_width <= 0 or frame_height <= 0:
        capture.release()
        return None

    target_width = frame_width
    target_height = frame_height
    if max_width > 0 and frame_width > max_width:
        scale = max_width / float(frame_width)
        target_width = max_width
        target_height = max(int(round(frame_height * scale)), 1)

    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = absolute_path.with_suffix(".tmp.mp4")
    if temp_path.exists():
        temp_path.unlink()

    writer = None
    try:
        for codec in ("avc1", "H264", "mp4v"):
            writer = cv2.VideoWriter(
                str(temp_path),
                cv2.VideoWriter_fourcc(*codec),
                fps,
                (target_width, target_height),
            )
            if writer.isOpened():
                break
            writer.release()
            writer = None

        if writer is None or not writer.isOpened():
            return None

        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if target_width != frame_width or target_height != frame_height:
                frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
            writer.write(frame)
    finally:
        capture.release()
        if writer is not None:
            writer.release()

    if not temp_path.exists() or temp_path.stat().st_size <= 0:
        if temp_path.exists():
            temp_path.unlink()
        return None

    temp_path.replace(absolute_path)
    return relative_path


def build_storage_url(relative_path: Optional[str]) -> Optional[str]:
    if not relative_path:
        return None
    safe_relative_path = str(relative_path).lstrip("/")
    return f"/storage/{safe_relative_path}"


def delete_relative_file(relative_path: Optional[str]) -> None:
    if not relative_path:
        return

    settings = get_settings()
    absolute_path = settings.storage_root / relative_path
    if absolute_path.exists() and absolute_path.is_file():
        absolute_path.unlink()
