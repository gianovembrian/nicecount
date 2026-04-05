from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from uuid import UUID

from app.config import get_settings
from app.services.storage import ensure_storage_layout


@dataclass
class PreviewState:
    frame_sequence: int = 0
    is_active: bool = False
    is_finished: bool = False
    updated_at: float = field(default_factory=time.time)
    condition: threading.Condition = field(default_factory=threading.Condition)


_STATES: dict[UUID, PreviewState] = {}
_STATES_LOCK = threading.Lock()


def _get_state(job_id: UUID, create: bool = False) -> Optional[PreviewState]:
    with _STATES_LOCK:
        state = _STATES.get(job_id)
        if state or not create:
            return state

        state = PreviewState()
        _STATES[job_id] = state
        return state


def _preview_image_path(job_id: UUID) -> Path:
    return get_settings().preview_dir / f"{job_id}.jpg"


def _preview_meta_path(job_id: UUID) -> Path:
    return get_settings().preview_dir / f"{job_id}.json"


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        tmp_path.write_bytes(payload)
        try:
            tmp_path.replace(path)
        except FileNotFoundError:
            path.write_bytes(payload)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _write_meta(job_id: UUID, *, frame_sequence: int, is_finished: bool, has_frame: bool, updated_at: float) -> None:
    meta = {
        "job_id": str(job_id),
        "frame_sequence": frame_sequence,
        "is_finished": is_finished,
        "has_frame": has_frame,
        "updated_at": updated_at,
    }
    _write_bytes_atomic(
        _preview_meta_path(job_id),
        json.dumps(meta, ensure_ascii=True).encode("utf-8"),
    )


def _read_meta(job_id: UUID) -> dict:
    meta_path = _preview_meta_path(job_id)
    if not meta_path.exists():
        return {}

    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def start_preview(job_id: UUID) -> None:
    ensure_storage_layout()
    state = _get_state(job_id, create=True)
    now = time.time()

    image_path = _preview_image_path(job_id)
    if image_path.exists():
        try:
            image_path.unlink()
        except OSError:
            pass

    with state.condition:
        state.frame_sequence = 0
        state.is_active = True
        state.is_finished = False
        state.updated_at = now
        state.condition.notify_all()

    try:
        _write_meta(job_id, frame_sequence=0, is_finished=False, has_frame=False, updated_at=now)
    except OSError:
        pass


def publish_preview_frame(job_id: UUID, frame_bytes: bytes) -> None:
    ensure_storage_layout()
    state = _get_state(job_id, create=True)
    now = time.time()

    with state.condition:
        state.frame_sequence += 1
        state.is_active = True
        state.is_finished = False
        state.updated_at = now
        frame_sequence = state.frame_sequence
        state.condition.notify_all()

    try:
        _write_bytes_atomic(_preview_image_path(job_id), frame_bytes)
        _write_meta(job_id, frame_sequence=frame_sequence, is_finished=False, has_frame=True, updated_at=now)
    except OSError:
        pass


def finish_preview(job_id: UUID) -> None:
    ensure_storage_layout()
    state = _get_state(job_id, create=True)
    now = time.time()

    with state.condition:
        state.is_active = False
        state.is_finished = True
        state.updated_at = now
        frame_sequence = state.frame_sequence
        state.condition.notify_all()

    try:
        _write_meta(
            job_id,
            frame_sequence=frame_sequence,
            is_finished=True,
            has_frame=_preview_image_path(job_id).exists(),
            updated_at=now,
        )
    except OSError:
        pass


def preview_stream(job_id: UUID):
    last_sequence = -1
    max_idle_seconds = 30.0

    while True:
        frame_bytes, frame_sequence, is_finished = get_latest_preview_frame(job_id)
        meta = _read_meta(job_id)
        last_updated = float(meta.get("updated_at") or 0.0)

        if frame_bytes and frame_sequence != last_sequence:
            last_sequence = frame_sequence
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Cache-Control: no-cache\r\n\r\n" + frame_bytes + b"\r\n"
            )
            time.sleep(0.2)
            continue

        if is_finished:
            break

        if last_updated and time.time() - last_updated > max_idle_seconds:
            break

        time.sleep(0.3)


def get_latest_preview_frame(job_id: UUID) -> tuple[Optional[bytes], int, bool]:
    state = _get_state(job_id, create=False)
    meta = _read_meta(job_id)
    image_path = _preview_image_path(job_id)

    frame_bytes = None
    if image_path.exists():
        try:
            frame_bytes = image_path.read_bytes()
        except OSError:
            frame_bytes = None

    frame_sequence = 0
    is_finished = False

    if state:
        with state.condition:
            frame_sequence = state.frame_sequence
            is_finished = state.is_finished

    if not frame_sequence:
        frame_sequence = int(meta.get("frame_sequence") or 0)
    if not is_finished:
        is_finished = bool(meta.get("is_finished") or False)

    return frame_bytes, frame_sequence, is_finished


def clear_preview(job_id: UUID) -> None:
    with _STATES_LOCK:
        _STATES.pop(job_id, None)


def delete_preview_artifacts(job_id: UUID) -> None:
    for path in (_preview_image_path(job_id), _preview_meta_path(job_id)):
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
