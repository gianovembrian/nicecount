from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.constants import (
    COCO_CLASS_TO_VEHICLE_CLASS,
    DEFAULT_MOTORCYCLE_MIN_CONFIDENCE,
    DEFAULT_VEHICLE_MIN_CONFIDENCE,
    DETECTED_TYPE_LABELS,
    DIRECTION_NORMAL,
    DIRECTION_OPPOSITE,
    GOLONGAN_I,
    GOLONGAN_II,
    GOLONGAN_III,
    GOLONGAN_IV,
    GOLONGAN_V,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PROCESSING,
    TRACKABLE_CLASS_IDS,
    VEHICLE_CLASS_BUS,
    VEHICLE_CLASS_CAR,
    VEHICLE_CLASS_MOTORCYCLE,
    VEHICLE_CLASS_TRUCK,
    VIDEO_STATUS_FAILED,
    VIDEO_STATUS_PROCESSING,
    VIDEO_STATUS_PROCESSED,
)
from app.database import SessionLocal
from app.models import AnalysisGolonganTotal, AnalysisJob, CountLine, Site, VehicleEvent, VideoCountAggregate, VideoCountLine, VideoUpload
from app.services.live_preview import clear_preview, finish_preview, publish_preview_frame, start_preview
from app.services.master_classes import build_master_class_lookup, get_or_create_master_classes
from app.services.storage import ensure_storage_layout

CLASS_MIN_AREA_RATIO = {
    VEHICLE_CLASS_MOTORCYCLE: 0.00002,
    VEHICLE_CLASS_CAR: 0.00018,
    VEHICLE_CLASS_BUS: 0.0003,
    VEHICLE_CLASS_TRUCK: 0.00035,
}


@dataclass
class ProcessConfig:
    model_path: str
    tracker_config: str
    frame_stride: int
    target_analysis_fps: float
    preview_fps: float
    working_max_width: int
    preview_max_width: int
    preview_jpeg_quality: int
    inference_imgsz: int
    inference_device: str
    confidence_threshold: float
    motorcycle_min_confidence: float
    vehicle_min_confidence: float
    iou_threshold: float
    save_annotated_video: bool


def build_process_config(overrides: Optional[dict] = None) -> ProcessConfig:
    settings = get_settings()
    overrides = overrides or {}
    return ProcessConfig(
        model_path=overrides.get("model_path") or settings.default_model_path,
        tracker_config=overrides.get("tracker_config") or settings.default_tracker_config,
        frame_stride=max(int(overrides.get("frame_stride") or settings.default_frame_stride), 1),
        target_analysis_fps=float(
            overrides.get("target_analysis_fps")
            if overrides.get("target_analysis_fps") is not None
            else settings.default_target_analysis_fps
        ),
        preview_fps=float(
            overrides.get("preview_fps")
            if overrides.get("preview_fps") is not None
            else settings.default_preview_fps
        ),
        working_max_width=max(
            int(
                overrides.get("working_max_width")
                if overrides.get("working_max_width") is not None
                else settings.default_working_max_width
            ),
            0,
        ),
        preview_max_width=max(
            int(
                overrides.get("preview_max_width")
                if overrides.get("preview_max_width") is not None
                else settings.default_preview_max_width
            ),
            0,
        ),
        preview_jpeg_quality=min(
            max(
                int(
                    overrides.get("preview_jpeg_quality")
                    if overrides.get("preview_jpeg_quality") is not None
                    else settings.default_preview_jpeg_quality
                ),
                30,
            ),
            95,
        ),
        inference_imgsz=max(
            int(
                overrides.get("inference_imgsz")
                if overrides.get("inference_imgsz") is not None
                else settings.default_inference_imgsz
            ),
            320,
        ),
        inference_device=str(
            overrides.get("inference_device")
            if overrides.get("inference_device") is not None
            else settings.default_inference_device
        ).strip()
        or "auto",
        confidence_threshold=float(
            overrides.get("confidence_threshold")
            if overrides.get("confidence_threshold") is not None
            else settings.default_confidence
        ),
        motorcycle_min_confidence=float(
            overrides.get("motorcycle_min_confidence")
            if overrides.get("motorcycle_min_confidence") is not None
            else DEFAULT_MOTORCYCLE_MIN_CONFIDENCE
        ),
        vehicle_min_confidence=float(
            overrides.get("vehicle_min_confidence")
            if overrides.get("vehicle_min_confidence") is not None
            else DEFAULT_VEHICLE_MIN_CONFIDENCE
        ),
        iou_threshold=float(
            overrides.get("iou_threshold")
            if overrides.get("iou_threshold") is not None
            else settings.default_iou
        ),
        save_annotated_video=(
            overrides.get("save_annotated_video")
            if overrides.get("save_annotated_video") is not None
            else settings.save_annotated_video
        ),
    )


def launch_analysis_worker(video_id: UUID, job_id: UUID, overrides: Optional[dict] = None) -> None:
    worker = threading.Thread(
        target=run_video_analysis,
        args=(video_id, job_id, overrides),
        daemon=True,
        name=f"analysis-{job_id}",
    )
    worker.start()


def run_video_analysis(video_id: UUID, job_id: UUID, overrides: Optional[dict] = None) -> None:
    db = SessionLocal()
    capture = None
    writer = None

    try:
        start_preview(job_id)

        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("opencv-python-headless is not installed") from exc

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("ultralytics is not installed") from exc

        video = db.scalar(
            select(VideoUpload)
            .options(joinedload(VideoUpload.analysis_job))
            .where(VideoUpload.id == video_id)
        )
        job = db.get(AnalysisJob, job_id)
        if not video or not job:
            return

        site = db.get(Site, video.site_id)
        if not site:
            raise RuntimeError("The default site was not found")

        lines = _load_count_lines(db, video, site)
        if not lines:
            raise RuntimeError("No active count line is available")
        master_class_rows = get_or_create_master_classes(db)
        master_class_lookup = build_master_class_lookup(master_class_rows)
        if not master_class_lookup:
            raise RuntimeError("No master class is available")

        config = build_process_config(overrides or job.config_json or {})
        settings = get_settings()
        ensure_storage_layout()

        job.status = JOB_STATUS_PROCESSING
        job.started_at = _utc_now()
        job.finished_at = None
        job.error_message = None
        job.model_name = config.model_path
        job.config_json = {
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
        job.summary_json = _build_summary({}, 0, 0, 0, master_class_lookup=master_class_lookup)
        video.status = VIDEO_STATUS_PROCESSING
        video.processing_error = None
        db.commit()

        db.execute(delete(VehicleEvent).where(VehicleEvent.video_upload_id == video.id))
        db.execute(delete(AnalysisGolonganTotal).where(AnalysisGolonganTotal.video_upload_id == video.id))
        db.execute(delete(VideoCountAggregate).where(VideoCountAggregate.video_upload_id == video.id))
        db.commit()

        totals_map: dict[str, AnalysisGolonganTotal] = {}
        counts_by_golongan = {code: 0 for code in master_class_lookup}
        for golongan_code, master_class in master_class_lookup.items():
            total_row = AnalysisGolonganTotal(
                video_upload_id=video.id,
                analysis_job_id=job.id,
                golongan_code=golongan_code,
                golongan_label=master_class["label"],
                vehicle_count=0,
            )
            db.add(total_row)
            totals_map[golongan_code] = total_row
        db.commit()

        absolute_video_path = settings.storage_root / video.relative_path
        capture = cv2.VideoCapture(str(absolute_video_path))
        if not capture.isOpened():
            raise RuntimeError(f"Failed to open video: {absolute_video_path}")

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0) or float(video.video_fps or 0.0) or 25.0
        source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0) or int(video.frame_width or 0)
        source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0) or int(video.frame_height or 0)
        source_total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0) or int(video.frame_count or 0)

        effective_frame_stride = _resolve_effective_frame_stride(fps, config.frame_stride, config.target_analysis_fps)
        effective_total_frames = (
            int(math.ceil(source_total_frames / effective_frame_stride))
            if source_total_frames > 0
            else 0
        )
        working_width, working_height = _fit_frame(source_width, source_height, config.working_max_width)
        scale_x = source_width / max(float(working_width), 1.0)
        scale_y = source_height / max(float(working_height), 1.0)
        output_fps = max(fps / max(effective_frame_stride, 1), 1.0)
        preview_publish_interval = _resolve_preview_publish_interval(output_fps, config.preview_fps)
        line_segments = _resolved_lines(lines, working_width, working_height)
        annotated_relative_path = None
        if config.save_annotated_video:
            annotated_filename = f"{job.id}.mp4"
            annotated_absolute_path = settings.annotated_dir / annotated_filename
            annotated_relative_path = annotated_absolute_path.relative_to(settings.storage_root).as_posix()
            writer = cv2.VideoWriter(
                str(annotated_absolute_path),
                cv2.VideoWriter_fourcc(*"mp4v"),
                output_fps,
                (working_width, working_height),
            )

        model = YOLO(config.model_path)
        inference_device = _resolve_inference_device(config.inference_device)
        try:
            model.to(inference_device)
        except Exception:
            inference_device = "cpu"
            model.to(inference_device)

        performance_meta = {
            "source_fps": round(fps, 3),
            "source_total_frames": source_total_frames,
            "source_resolution": {"width": source_width, "height": source_height},
            "effective_frame_stride": effective_frame_stride,
            "target_analysis_fps": config.target_analysis_fps,
            "effective_analysis_fps": round(output_fps, 3),
            "preview_fps": config.preview_fps,
            "preview_publish_interval": preview_publish_interval,
            "working_resolution": {"width": working_width, "height": working_height},
            "inference_imgsz": config.inference_imgsz,
            "inference_device": inference_device,
        }

        job.total_frames = effective_total_frames
        job.annotated_relative_path = annotated_relative_path
        db.commit()

        track_last_points: dict[int, tuple[float, float]] = {}
        counted_track_lines: dict[int, set[int]] = {}
        frame_number = 0
        processed_frames = 0
        sequence_no = 0
        report_events: list[dict] = []
        overlay_frames: list[dict] = []
        started_monotonic = time.perf_counter()

        while True:
            opened, frame = capture.read()
            if not opened:
                break

            frame_number += 1
            if effective_frame_stride > 1 and (frame_number - 1) % effective_frame_stride != 0:
                continue

            processed_frames += 1
            working_frame = (
                cv2.resize(frame, (working_width, working_height), interpolation=cv2.INTER_AREA)
                if working_width != source_width or working_height != source_height
                else frame
            )
            results = model.track(
                working_frame,
                persist=True,
                tracker=config.tracker_config,
                verbose=False,
                device=inference_device,
                imgsz=config.inference_imgsz,
                conf=config.confidence_threshold,
                iou=config.iou_threshold,
                classes=list(TRACKABLE_CLASS_IDS),
            )

            result = results[0]
            annotated_frame = result.plot()
            boxes = getattr(result, "boxes", None)
            event_found = False
            frame_detections: list[dict] = []

            if boxes is not None and boxes.id is not None:
                track_ids = boxes.id.int().cpu().tolist()
                class_ids = boxes.cls.int().cpu().tolist()
                confidences = boxes.conf.float().cpu().tolist()
                box_values = boxes.xyxy.cpu().tolist()
                names = result.names

                for track_id, class_id, confidence, xyxy in zip(track_ids, class_ids, confidences, box_values):
                    vehicle_class = COCO_CLASS_TO_VEHICLE_CLASS.get(class_id)
                    if not vehicle_class:
                        continue

                    x1, y1, x2, y2 = [float(value) for value in xyxy]
                    if not _is_detection_candidate(
                        vehicle_class=vehicle_class,
                        confidence=float(confidence),
                        bbox=(x1, y1, x2, y2),
                        frame_width=max(working_width, 1),
                        frame_height=max(working_height, 1),
                        config=config,
                    ):
                        continue

                    frame_detections.append(
                        {
                            "track_id": int(track_id),
                            "vehicle_class": vehicle_class,
                            "source_label": _resolve_source_label(names, class_id),
                            "confidence": round(float(confidence), 4),
                            "x1": round(x1 / max(float(working_width), 1.0), 6),
                            "y1": round(y1 / max(float(working_height), 1.0), 6),
                            "x2": round(x2 / max(float(working_width), 1.0), 6),
                            "y2": round(y2 / max(float(working_height), 1.0), 6),
                        }
                    )

                    point = ((x1 + x2) / 2.0, y2)
                    previous_point = track_last_points.get(track_id)

                    if previous_point is not None:
                        crossed_lines: list[tuple[int, str, CountLine | VideoCountLine]] = []
                        counted_lines = counted_track_lines.setdefault(int(track_id), set())
                        for line, (line_start, line_end) in zip(lines, line_segments):
                            line_order = int(line.line_order)
                            if line_order in counted_lines:
                                continue
                            previous_side = _point_side(line_start, line_end, previous_point)
                            current_side = _point_side(line_start, line_end, point)
                            if previous_side != 0 and current_side != 0 and previous_side * current_side < 0:
                                direction = DIRECTION_NORMAL if previous_side < 0 < current_side else DIRECTION_OPPOSITE
                                crossed_lines.append((line_order, direction, line))

                        if crossed_lines:
                            detected_label, golongan_code, golongan_label = _classify_golongan(
                                vehicle_class=vehicle_class,
                                bbox=(x1, y1, x2, y2),
                                frame_width=max(working_width, 1),
                                frame_height=max(working_height, 1),
                                master_class_lookup=master_class_lookup,
                            )

                            for line_order, direction, line in crossed_lines:
                                counted_lines.add(line_order)
                                sequence_no += 1
                                db.add(
                                    VehicleEvent(
                                        video_upload_id=video.id,
                                        analysis_job_id=job.id,
                                        site_id=site.id,
                                        sequence_no=sequence_no,
                                        track_id=int(track_id),
                                        vehicle_class=vehicle_class,
                                        detected_label=detected_label,
                                        golongan_code=golongan_code,
                                        golongan_label=golongan_label,
                                        source_label=_resolve_source_label(names, class_id),
                                        count_line_order=line_order,
                                        count_line_name=line.name,
                                        direction=direction,
                                        crossed_at_seconds=float(frame_number / fps),
                                        crossed_at_frame=frame_number,
                                        confidence=float(confidence),
                                        speed_kph=None,
                                        bbox_x1=x1 * scale_x,
                                        bbox_y1=y1 * scale_y,
                                        bbox_x2=x2 * scale_x,
                                        bbox_y2=y2 * scale_y,
                                    )
                                )

                                totals_map[golongan_code].vehicle_count += 1
                                counts_by_golongan[golongan_code] += 1
                                report_events.append(
                                    {
                                        "sequence_no": sequence_no,
                                        "track_id": int(track_id),
                                        "vehicle_class": vehicle_class,
                                        "detected_label": detected_label,
                                        "golongan_code": golongan_code,
                                        "golongan_label": golongan_label,
                                        "count_line_order": line_order,
                                        "count_line_name": line.name,
                                        "direction": direction,
                                        "crossed_at_seconds": float(frame_number / fps),
                                        "crossed_at_frame": frame_number,
                                        "confidence": float(confidence),
                                    }
                                )
                                event_found = True

                    track_last_points[int(track_id)] = point

            overlay_frames.append(
                {
                    "source_frame": frame_number,
                    "time_seconds": round(float(frame_number / fps), 4),
                    "detections": frame_detections,
                }
            )

            if writer is not None:
                _draw_overlay(
                    annotated_frame,
                    line_segments,
                    counts_by_golongan,
                    master_class_lookup,
                    processed_frames,
                    effective_total_frames,
                )
                writer.write(annotated_frame)
            else:
                _draw_overlay(
                    annotated_frame,
                    line_segments,
                    counts_by_golongan,
                    master_class_lookup,
                    processed_frames,
                    effective_total_frames,
                )

            should_publish_preview = (
                processed_frames == 1
                or event_found
                or processed_frames % preview_publish_interval == 0
            )
            if should_publish_preview:
                preview_frame = _prepare_preview_frame(annotated_frame, config.preview_max_width)
                encoded_ok, encoded_frame = cv2.imencode(
                    ".jpg",
                    preview_frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), config.preview_jpeg_quality],
                )
                if encoded_ok:
                    try:
                        publish_preview_frame(job_id, encoded_frame.tobytes())
                    except OSError:
                        pass

            elapsed_seconds = max(time.perf_counter() - started_monotonic, 0.001)
            performance_meta["processing_fps"] = round(processed_frames / elapsed_seconds, 3)

            if event_found or processed_frames % 15 == 0:
                job.processed_frames = processed_frames
                job.summary_json = _build_summary(
                    counts_by_golongan,
                    processed_frames,
                    effective_total_frames,
                    sequence_no,
                    master_class_lookup=master_class_lookup,
                    performance=performance_meta,
                )
                db.commit()

        job.processed_frames = processed_frames
        job.total_frames = effective_total_frames
        job.summary_json = _build_summary(
            counts_by_golongan,
            processed_frames,
            effective_total_frames,
            sequence_no,
            master_class_lookup=master_class_lookup,
            performance=performance_meta,
        )
        job.finished_at = _utc_now()
        job.status = JOB_STATUS_COMPLETED
        video.status = VIDEO_STATUS_PROCESSED
        video.processing_error = None

        report_filename = f"{job.id}.json"
        report_absolute_path = settings.reports_dir / report_filename
        report_relative_path = report_absolute_path.relative_to(settings.storage_root).as_posix()
        overlay_filename = f"{job.id}.overlay.json"
        overlay_absolute_path = settings.reports_dir / overlay_filename
        report_absolute_path.write_text(
            json.dumps(
                {
                    "video_id": str(video.id),
                    "analysis_job_id": str(job.id),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "summary": job.summary_json,
                    "events": report_events,
                    "golongan_totals": [
                        {
                            "golongan_code": code,
                            "golongan_label": payload["label"],
                            "vehicle_count": counts_by_golongan[code],
                        }
                        for code, payload in master_class_lookup.items()
                    ],
                    "note": "Classes II to V are currently estimated using object-size heuristics from a single camera view.",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        overlay_absolute_path.write_text(
            json.dumps(
                {
                    "video_id": str(video.id),
                    "analysis_job_id": str(job.id),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "source": {
                        "fps": round(fps, 6),
                        "frame_width": source_width,
                        "frame_height": source_height,
                        "frame_count": source_total_frames,
                        "duration_seconds": float(video.duration_seconds or 0.0),
                    },
                    "analysis": {
                        "effective_frame_stride": effective_frame_stride,
                        "processed_frames": processed_frames,
                        "line": {
                            "start_x": round(float(lines[0].start_x), 6),
                            "start_y": round(float(lines[0].start_y), 6),
                            "end_x": round(float(lines[0].end_x), 6),
                            "end_y": round(float(lines[0].end_y), 6),
                        },
                        "lines": [
                            {
                                "line_order": int(line.line_order),
                                "name": line.name,
                                "start_x": round(float(line.start_x), 6),
                                "start_y": round(float(line.start_y), 6),
                                "end_x": round(float(line.end_x), 6),
                                "end_y": round(float(line.end_y), 6),
                            }
                            for line in lines
                        ],
                        "master_classes": [
                            {
                                "code": code,
                                "label": payload["label"],
                                "description": payload["description"],
                                "sort_order": payload["sort_order"],
                            }
                            for code, payload in master_class_lookup.items()
                        ],
                        "performance": performance_meta,
                    },
                    "frames": overlay_frames,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        job.report_relative_path = report_relative_path
        job.error_message = None
        video.processing_error = None
        db.commit()
        try:
            finish_preview(job_id)
        except OSError:
            pass
    except Exception as exc:
        db.rollback()
        job = db.get(AnalysisJob, job_id)
        video = db.get(VideoUpload, video_id)
        if job:
            job.status = JOB_STATUS_FAILED
            job.finished_at = _utc_now()
            job.error_message = str(exc)
        if video:
            video.status = VIDEO_STATUS_FAILED
            video.processing_error = str(exc)
        db.commit()
        try:
            finish_preview(job_id)
        except OSError:
            pass
    finally:
        if capture is not None:
            capture.release()
        if writer is not None:
            writer.release()
        db.close()
        clear_preview(job_id)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _build_summary(
    counts_by_golongan: dict[str, int],
    processed_frames: int,
    total_frames: int,
    sequence_no: int,
    master_class_lookup: dict[str, dict],
    performance: Optional[dict] = None,
) -> dict:
    totals = {code: counts_by_golongan.get(code, 0) for code in master_class_lookup}
    return {
        "total_count": sum(totals.values()),
        "event_count": sequence_no,
        "processed_frames": processed_frames,
        "total_frames": total_frames,
        "totals_by_golongan": totals,
        "golongan_labels": {code: payload["label"] for code, payload in master_class_lookup.items()},
        "golongan_descriptions": {code: payload["description"] for code, payload in master_class_lookup.items()},
        "classification_note": "Classes II to V use object-size heuristics, not actual axle counting.",
        "performance": performance or {},
    }


def _resolve_effective_frame_stride(source_fps: float, configured_stride: int, target_analysis_fps: float) -> int:
    stride = max(configured_stride, 1)
    if source_fps > 0 and target_analysis_fps > 0:
        stride = max(stride, int(round(source_fps / target_analysis_fps)))
    return max(stride, 1)


def _fit_frame(width: int, height: int, max_width: int) -> tuple[int, int]:
    if max_width <= 0 or width <= max_width or width <= 0 or height <= 0:
        return max(width, 1), max(height, 1)

    scale = max_width / float(width)
    fitted_height = max(int(round(height * scale)), 1)
    return max_width, fitted_height


def _resolve_preview_publish_interval(processed_video_fps: float, preview_fps: float) -> int:
    if processed_video_fps <= 0 or preview_fps <= 0:
        return 1
    return max(int(round(processed_video_fps / preview_fps)), 1)


def _resolve_inference_device(preferred_device: str) -> str:
    normalized = (preferred_device or "auto").strip().lower()
    if normalized and normalized != "auto":
        return normalized

    try:
        import torch
    except Exception:
        return "cpu"

    if torch.cuda.is_available():
        return "cuda:0"

    mps_backend = getattr(torch.backends, "mps", None)
    if mps_backend and torch.backends.mps.is_available():
        return "mps"

    return "cpu"


def _prepare_preview_frame(frame, max_width: int):
    import cv2

    height, width = frame.shape[:2]
    target_width, target_height = _fit_frame(width, height, max_width)
    if target_width == width and target_height == height:
        return frame

    return cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)


def _point_side(line_start: tuple[float, float], line_end: tuple[float, float], point: tuple[float, float]) -> float:
    return ((line_end[0] - line_start[0]) * (point[1] - line_start[1])) - (
        (line_end[1] - line_start[1]) * (point[0] - line_start[0])
    )


def _load_count_lines(db, video: VideoUpload, site: Site) -> list[CountLine | VideoCountLine]:
    video_lines = list(
        db.scalars(
            select(VideoCountLine)
            .where(VideoCountLine.video_upload_id == video.id, VideoCountLine.is_active.is_(True))
            .order_by(VideoCountLine.line_order.asc(), VideoCountLine.created_at.asc())
        )
    )
    if video_lines:
        return video_lines

    site_lines = list(
        db.scalars(
            select(CountLine)
            .where(CountLine.site_id == site.id, CountLine.is_active.is_(True))
            .order_by(CountLine.line_order.asc(), CountLine.created_at.asc())
        )
    )
    return site_lines[:1]


def _resolved_line(line: CountLine | VideoCountLine, width: int, height: int) -> tuple[tuple[int, int], tuple[int, int]]:
    return (
        (int(line.start_x * width), int(line.start_y * height)),
        (int(line.end_x * width), int(line.end_y * height)),
    )


def _resolved_lines(lines: list[CountLine | VideoCountLine], width: int, height: int) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    return [_resolved_line(line, width, height) for line in lines]


def _draw_overlay(
    frame,
    line_segments: list[tuple[tuple[int, int], tuple[int, int]]],
    counts_by_golongan: dict[str, int],
    master_class_lookup: dict[str, dict],
    processed_frames: int,
    total_frames: int,
) -> None:
    import cv2

    line_colors = [(0, 255, 255), (255, 255, 0)]
    for index, (line_start, line_end) in enumerate(line_segments):
        cv2.line(frame, line_start, line_end, line_colors[index % len(line_colors)], 2)
    overlay_y = 30
    cv2.putText(frame, "Vehicle Analysis", (20, overlay_y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (30, 255, 30), 2)
    overlay_y += 28
    progress_text = f"Frame {processed_frames}/{total_frames or '-'}"
    cv2.putText(frame, progress_text, (20, overlay_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    overlay_y += 24
    for code, payload in master_class_lookup.items():
        text = f"{payload['label']}: {counts_by_golongan.get(code, 0)}"
        cv2.putText(frame, text, (20, overlay_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        overlay_y += 22


def _classify_golongan(
    vehicle_class: str,
    bbox: tuple[float, float, float, float],
    frame_width: int,
    frame_height: int,
    master_class_lookup: dict[str, dict],
) -> tuple[str, str, str]:
    def golongan_label(code: str) -> str:
        payload = master_class_lookup.get(code) or {}
        return str(payload.get("label") or code)

    x1, y1, x2, y2 = bbox
    box_width = max(x2 - x1, 1.0)
    box_height = max(y2 - y1, 1.0)
    area_ratio = (box_width * box_height) / max(float(frame_width * frame_height), 1.0)
    aspect_ratio = box_width / box_height

    if vehicle_class == VEHICLE_CLASS_MOTORCYCLE:
        return (DETECTED_TYPE_LABELS[VEHICLE_CLASS_MOTORCYCLE], GOLONGAN_I, golongan_label(GOLONGAN_I))
    if vehicle_class == VEHICLE_CLASS_CAR:
        return (DETECTED_TYPE_LABELS[VEHICLE_CLASS_CAR], GOLONGAN_I, golongan_label(GOLONGAN_I))
    if vehicle_class == VEHICLE_CLASS_BUS:
        return (DETECTED_TYPE_LABELS[VEHICLE_CLASS_BUS], GOLONGAN_I, golongan_label(GOLONGAN_I))

    if vehicle_class != VEHICLE_CLASS_TRUCK:
        return (vehicle_class, GOLONGAN_I, golongan_label(GOLONGAN_I))

    if area_ratio < 0.025:
        golongan = GOLONGAN_I
    elif area_ratio < 0.05:
        golongan = GOLONGAN_II
    elif area_ratio < 0.085:
        golongan = GOLONGAN_III
    elif area_ratio < 0.13:
        golongan = GOLONGAN_IV
    else:
        golongan = GOLONGAN_V

    if aspect_ratio > 2.2:
        golongan = {
            GOLONGAN_I: GOLONGAN_II,
            GOLONGAN_II: GOLONGAN_III,
            GOLONGAN_III: GOLONGAN_IV,
            GOLONGAN_IV: GOLONGAN_V,
            GOLONGAN_V: GOLONGAN_V,
        }[golongan]

    return (DETECTED_TYPE_LABELS[VEHICLE_CLASS_TRUCK], golongan, golongan_label(golongan))


def _is_detection_candidate(
    vehicle_class: str,
    confidence: float,
    bbox: tuple[float, float, float, float],
    frame_width: int,
    frame_height: int,
    config: ProcessConfig,
) -> bool:
    x1, y1, x2, y2 = bbox
    box_width = max(x2 - x1, 1.0)
    box_height = max(y2 - y1, 1.0)
    area_ratio = (box_width * box_height) / max(float(frame_width * frame_height), 1.0)

    if vehicle_class == VEHICLE_CLASS_MOTORCYCLE:
        minimum_confidence = max(config.confidence_threshold, config.motorcycle_min_confidence)
    elif vehicle_class in {VEHICLE_CLASS_CAR, VEHICLE_CLASS_BUS, VEHICLE_CLASS_TRUCK}:
        minimum_confidence = max(config.confidence_threshold, config.vehicle_min_confidence)
    else:
        minimum_confidence = config.confidence_threshold

    if confidence < minimum_confidence:
        return False

    if area_ratio < CLASS_MIN_AREA_RATIO.get(vehicle_class, 0.0001):
        return False

    return True


def _resolve_source_label(names, class_id: int) -> str:
    if isinstance(names, dict):
        return str(names.get(class_id, class_id))
    if isinstance(names, list) and 0 <= class_id < len(names):
        return str(names[class_id])
    return str(class_id)
