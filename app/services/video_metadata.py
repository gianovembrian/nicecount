from __future__ import annotations

from pathlib import Path


def probe_video(path: Path) -> dict:
    try:
        import cv2
    except ImportError:
        return {
            "video_fps": None,
            "frame_width": None,
            "frame_height": None,
            "frame_count": None,
            "duration_seconds": None,
        }

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return {
            "video_fps": None,
            "frame_width": None,
            "frame_height": None,
            "frame_count": None,
            "duration_seconds": None,
        }

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0) or None
    frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0) or None
    frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0) or None
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0) or None
    capture.release()

    duration_seconds = None
    if fps and frame_count:
        duration_seconds = frame_count / fps

    return {
        "video_fps": fps,
        "frame_width": frame_width,
        "frame_height": frame_height,
        "frame_count": frame_count,
        "duration_seconds": duration_seconds,
    }
