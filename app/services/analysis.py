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
    DEFAULT_BUS_MIN_CONFIDENCE,
    DEFAULT_CAR_MIN_CONFIDENCE,
    COCO_CLASS_TO_VEHICLE_CLASS,
    DEFAULT_MOTORCYCLE_MIN_CONFIDENCE,
    DEFAULT_TRUCK_MIN_CONFIDENCE,
    DEFAULT_VEHICLE_MIN_CONFIDENCE,
    DIRECTION_NORMAL,
    DIRECTION_OPPOSITE,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_PROCESSING,
    RAW_DETECTION_LABELS,
    TRACKABLE_CLASS_IDS,
    VEHICLE_CLASS_BICYCLE,
    VEHICLE_CLASS_BUS,
    VEHICLE_CLASS_CAR,
    VEHICLE_CLASS_MOTORCYCLE,
    VEHICLE_CLASS_TRUCK,
    VIDEO_STATUS_FAILED,
    VIDEO_STATUS_PROCESSING,
    VIDEO_STATUS_PROCESSED,
    VIDEO_STATUS_UPLOADED,
)
from app.database import SessionLocal
from app.models import AnalysisGolonganTotal, AnalysisJob, CountLine, Site, VehicleEvent, VideoCountAggregate, VideoCountLine, VideoUpload
from app.services.live_preview import clear_preview, delete_preview_artifacts, finish_preview, publish_preview_frame, start_preview
from app.services.master_classes import build_master_class_lookup, get_or_create_master_classes
from app.services.storage import delete_relative_file, ensure_storage_layout
from app.services.vehicle_classification import classify_vehicle
from app.services.video_conversion import resolve_analysis_video_path

CLASS_MIN_AREA_RATIO = {
    VEHICLE_CLASS_BICYCLE: 0.000008,
    VEHICLE_CLASS_MOTORCYCLE: 0.000008,
    VEHICLE_CLASS_CAR: 0.00018,
    VEHICLE_CLASS_BUS: 0.00018,
    VEHICLE_CLASS_TRUCK: 0.00035,
}

LARGE_VEHICLE_MIN_LONG_SIDE_RATIO = {
    VEHICLE_CLASS_BUS: 0.032,
    VEHICLE_CLASS_TRUCK: 0.03,
}

ROAD_ROI_DEFAULT_TOP_RATIO = 0.06
ROAD_ROI_CONTEXT_ABOVE_LINE_RATIO = 0.40
ROAD_ROI_MIN_HEIGHT_RATIO = 0.72
ROAD_ROI_MAX_TOP_RATIO = 0.30

TRACK_BBOX_SMOOTHING_ALPHA = 0.68
TRACK_CONFIDENCE_SMOOTHING_ALPHA = 0.65
TRACK_SCORE_DECAY = 0.92
TRACK_SCORE_FLOOR = 0.02
TRACK_CLASS_SWITCH_MARGIN = 1.8
TRACK_LARGE_TO_MOTORCYCLE_SWITCH_MARGIN = 1.60
TRACK_MOTORCYCLE_TO_LARGE_SWITCH_MARGIN = 2.50
TRACK_STATE_RESET_GAP_FRAMES = 90
SUPPLEMENTAL_MOTORCYCLE_TRACK_ID_START = 800000
SUPPLEMENTAL_MOTORCYCLE_TRACK_MAX_GAP_FRAMES = 45
SUPPLEMENTAL_MOTORCYCLE_TILE_MIN_SIZE = 160
SUPPLEMENTAL_MOTORCYCLE_TILE_OVERLAP_RATIO = 0.16
SUPPLEMENTAL_MOTORCYCLE_CONFIDENCE_FLOOR = 0.08
LINE_INTERSECTION_EPSILON = 1e-6
CLOSE_LINE_PAIR_MAX_ANGLE_DEGREES = 12.0
CLOSE_LINE_PAIR_MAX_GAP_RATIO = 0.12
CLOSE_LINE_PAIR_MAX_TIME_GAP_SECONDS = 5.0
CLOSE_LINE_PAIR_MAX_TANGENT_GAP_RATIO = 0.18
CLOSE_LINE_PAIR_MIN_MATCHES = 5

_STOP_EVENTS: dict[UUID, threading.Event] = {}
_STOP_EVENTS_LOCK = threading.Lock()


class AnalysisStopRequested(Exception):
    pass


@dataclass
class TrackState:
    bbox: tuple[float, float, float, float]
    confidence: float
    last_seen_frame: int
    seen_frames: int
    class_scores: dict[str, float]
    label_scores: dict[str, float]
    class_reference_boxes: dict[str, tuple[float, float, float, float]]
    class_reference_scores: dict[str, float]
    class_reference_labels: dict[str, str]
    last_center: tuple[float, float]
    last_velocity: tuple[float, float]
    reference_bbox: tuple[float, float, float, float]
    reference_score: float
    reference_vehicle_class: str
    reference_source_label: str


@dataclass
class SupplementalTrack:
    bbox: tuple[float, float, float, float]
    last_seen_frame: int
    last_center: tuple[float, float]
    last_velocity: tuple[float, float]


@dataclass(frozen=True)
class AnalysisRoi:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return max(self.x2 - self.x1, 1)

    @property
    def height(self) -> int:
        return max(self.y2 - self.y1, 1)

    def to_summary(self) -> dict[str, float | int]:
        return {
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class TrackProfile:
    vehicle_class: str
    source_label: str
    detected_label: str
    vehicle_type_code: str
    vehicle_type_label: str
    golongan_code: str
    golongan_label: str


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
    car_min_confidence: float
    bus_min_confidence: float
    truck_min_confidence: float
    iou_threshold: float
    save_annotated_video: bool


def _get_stop_event(job_id: UUID, create: bool = False) -> Optional[threading.Event]:
    with _STOP_EVENTS_LOCK:
        event = _STOP_EVENTS.get(job_id)
        if event or not create:
            return event
        event = threading.Event()
        _STOP_EVENTS[job_id] = event
        return event


def request_analysis_stop(job_id: UUID) -> None:
    _get_stop_event(job_id, create=True).set()


def clear_analysis_stop(job_id: UUID) -> None:
    with _STOP_EVENTS_LOCK:
        _STOP_EVENTS.pop(job_id, None)


def is_analysis_stop_requested(job_id: UUID) -> bool:
    event = _get_stop_event(job_id, create=False)
    return bool(event and event.is_set())


def _raise_if_stop_requested(job_id: UUID) -> None:
    if is_analysis_stop_requested(job_id):
        raise AnalysisStopRequested("Analysis stopped by user")


def _cleanup_stopped_analysis(db, video_id: UUID, job_id: UUID) -> None:
    video = db.get(VideoUpload, video_id)
    job = db.get(AnalysisJob, job_id)
    if not video or not job:
        return

    db.execute(delete(VehicleEvent).where(VehicleEvent.video_upload_id == video.id))
    db.execute(delete(AnalysisGolonganTotal).where(AnalysisGolonganTotal.video_upload_id == video.id))
    db.execute(delete(VideoCountAggregate).where(VideoCountAggregate.video_upload_id == video.id))

    delete_relative_file(job.annotated_relative_path)
    delete_relative_file(job.report_relative_path)
    delete_relative_file(f"reports/{job.id}.overlay.json")
    delete_preview_artifacts(job.id)

    job.status = JOB_STATUS_PENDING
    job.summary_json = None
    job.annotated_relative_path = None
    job.report_relative_path = None
    job.total_frames = None
    job.processed_frames = None
    job.finished_at = _utc_now()
    job.error_message = None

    video.status = VIDEO_STATUS_UPLOADED
    video.processing_error = None
    db.commit()


def _persist_vehicle_events(
    db,
    *,
    video: VideoUpload,
    job: AnalysisJob,
    site: Site,
    totals_map: dict[str, AnalysisGolonganTotal],
    events: list[dict],
) -> tuple[list[dict], dict[str, int]]:
    db.execute(delete(VehicleEvent).where(VehicleEvent.video_upload_id == video.id))

    counts_by_golongan = {code: 0 for code in totals_map}
    for total_row in totals_map.values():
        total_row.vehicle_count = 0

    ordered_events = sorted(
        (dict(event) for event in events),
        key=lambda event: (
            float(event.get("crossed_at_seconds") or 0.0),
            int(event.get("count_line_order") or 0),
            int(event.get("track_id") or 0),
        ),
    )

    for sequence_no, event in enumerate(ordered_events, start=1):
        event["sequence_no"] = sequence_no
        golongan_code = str(event["golongan_code"])
        counts_by_golongan[golongan_code] += 1
        totals_map[golongan_code].vehicle_count += 1

        db.add(
            VehicleEvent(
                video_upload_id=video.id,
                analysis_job_id=job.id,
                site_id=site.id,
                sequence_no=sequence_no,
                track_id=int(event["track_id"]) if event.get("track_id") is not None else None,
                vehicle_class=str(event["vehicle_class"]),
                detected_label=event.get("detected_label"),
                vehicle_type_code=event.get("vehicle_type_code"),
                vehicle_type_label=event.get("vehicle_type_label"),
                golongan_code=golongan_code,
                golongan_label=str(event["golongan_label"]),
                source_label=event.get("source_label"),
                count_line_order=int(event["count_line_order"]) if event.get("count_line_order") is not None else None,
                count_line_name=event.get("count_line_name"),
                direction=str(event["direction"]),
                crossed_at_seconds=float(event["crossed_at_seconds"]),
                crossed_at_frame=int(event["crossed_at_frame"]),
                confidence=float(event["confidence"]) if event.get("confidence") is not None else None,
                speed_kph=float(event["speed_kph"]) if event.get("speed_kph") is not None else None,
                bbox_x1=float(event["bbox_x1"]) if event.get("bbox_x1") is not None else None,
                bbox_y1=float(event["bbox_y1"]) if event.get("bbox_y1") is not None else None,
                bbox_x2=float(event["bbox_x2"]) if event.get("bbox_x2") is not None else None,
                bbox_y2=float(event["bbox_y2"]) if event.get("bbox_y2") is not None else None,
            )
        )

    db.commit()
    return ordered_events, counts_by_golongan


def build_process_config(overrides: Optional[dict] = None) -> ProcessConfig:
    settings = get_settings()
    overrides = overrides or {}
    configured_model_path = str(overrides.get("model_path") or settings.default_model_path).strip() or "yolov8s.pt"
    if configured_model_path == "yolov8n.pt":
        configured_model_path = "yolov8s.pt"
    target_analysis_fps = max(
        float(
            overrides.get("target_analysis_fps")
            if overrides.get("target_analysis_fps") is not None
            else settings.default_target_analysis_fps
        ),
        15.0,
    )
    preview_fps = max(
        float(
            overrides.get("preview_fps")
            if overrides.get("preview_fps") is not None
            else settings.default_preview_fps
        ),
        6.0,
    )
    inference_imgsz = max(
        int(
            overrides.get("inference_imgsz")
            if overrides.get("inference_imgsz") is not None
            else settings.default_inference_imgsz
        ),
        1152,
    )
    legacy_vehicle_min_confidence = float(
        overrides.get("vehicle_min_confidence")
        if overrides.get("vehicle_min_confidence") is not None
        else DEFAULT_VEHICLE_MIN_CONFIDENCE
    )
    return ProcessConfig(
        model_path=configured_model_path,
        tracker_config=overrides.get("tracker_config") or settings.default_tracker_config,
        frame_stride=max(int(overrides.get("frame_stride") or settings.default_frame_stride), 1),
        target_analysis_fps=target_analysis_fps,
        preview_fps=preview_fps,
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
        inference_imgsz=inference_imgsz,
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
        car_min_confidence=float(
            overrides.get("car_min_confidence")
            if overrides.get("car_min_confidence") is not None
            else legacy_vehicle_min_confidence
            if overrides.get("vehicle_min_confidence") is not None
            else DEFAULT_CAR_MIN_CONFIDENCE
        ),
        bus_min_confidence=float(
            overrides.get("bus_min_confidence")
            if overrides.get("bus_min_confidence") is not None
            else min(max(legacy_vehicle_min_confidence + 0.04, DEFAULT_BUS_MIN_CONFIDENCE), 1.0)
            if overrides.get("vehicle_min_confidence") is not None
            else DEFAULT_BUS_MIN_CONFIDENCE
        ),
        truck_min_confidence=float(
            overrides.get("truck_min_confidence")
            if overrides.get("truck_min_confidence") is not None
            else min(max(legacy_vehicle_min_confidence + 0.08, DEFAULT_TRUCK_MIN_CONFIDENCE), 1.0)
            if overrides.get("vehicle_min_confidence") is not None
            else DEFAULT_TRUCK_MIN_CONFIDENCE
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
    clear_analysis_stop(job_id)
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
    stop_requested = False

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
        _raise_if_stop_requested(job_id)

        site = db.get(Site, video.site_id)
        if not site:
            raise RuntimeError("The default site was not found")

        lines = _load_count_lines(db, video, site)
        if not lines:
            raise RuntimeError("No active count line is available")
        master_class_rows = get_or_create_master_classes(db)
        master_class_lookup = build_master_class_lookup(master_class_rows)
        if not master_class_lookup:
            raise RuntimeError("No master vehicle class configuration is available")

        config = build_process_config(overrides or job.config_json or {})
        settings = get_settings()
        ensure_storage_layout()
        _raise_if_stop_requested(job_id)

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
            "car_min_confidence": config.car_min_confidence,
            "bus_min_confidence": config.bus_min_confidence,
            "truck_min_confidence": config.truck_min_confidence,
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

        absolute_video_path = resolve_analysis_video_path(video)
        capture = cv2.VideoCapture(str(absolute_video_path))
        if not capture.isOpened():
            raise RuntimeError(f"Failed to open video: {absolute_video_path}")
        _raise_if_stop_requested(job_id)

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
        analysis_roi = _resolve_analysis_roi(lines, working_width, working_height)
        motorcycle_focus_rois = _build_motorcycle_focus_rois(analysis_roi, working_width, working_height)
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
        supplemental_motorcycle_model = YOLO(config.model_path) if motorcycle_focus_rois else None
        inference_device = _resolve_inference_device(config.inference_device)
        try:
            model.to(inference_device)
            if supplemental_motorcycle_model is not None:
                supplemental_motorcycle_model.to(inference_device)
        except Exception:
            inference_device = "cpu"
            model.to(inference_device)
            if supplemental_motorcycle_model is not None:
                supplemental_motorcycle_model.to(inference_device)
        _raise_if_stop_requested(job_id)

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
            "analysis_roi": analysis_roi.to_summary(),
            "small_object_strategy": "road_roi_plus_motorcycle_focus_tiles",
            "motorcycle_focus_rois": [roi.to_summary() for roi in motorcycle_focus_rois],
            "inference_imgsz": config.inference_imgsz,
            "inference_device": inference_device,
            "class_thresholds": {
                "global": round(config.confidence_threshold, 3),
                "motorcycle": round(config.motorcycle_min_confidence, 3),
                "car": round(config.car_min_confidence, 3),
                "bus": round(config.bus_min_confidence, 3),
                "truck": round(config.truck_min_confidence, 3),
            },
            "raw_detection_total": 0,
            "raw_detection_by_class": {
                VEHICLE_CLASS_MOTORCYCLE: 0,
                VEHICLE_CLASS_CAR: 0,
                VEHICLE_CLASS_BUS: 0,
                VEHICLE_CLASS_TRUCK: 0,
                VEHICLE_CLASS_BICYCLE: 0,
            },
            "accepted_detection_total": 0,
            "accepted_detection_by_class": {
                VEHICLE_CLASS_MOTORCYCLE: 0,
                VEHICLE_CLASS_CAR: 0,
                VEHICLE_CLASS_BUS: 0,
                VEHICLE_CLASS_TRUCK: 0,
                VEHICLE_CLASS_BICYCLE: 0,
            },
            "rejected_detection_total": 0,
            "rejected_detection_by_reason": {},
            "supplemental_motorcycle_raw_total": 0,
            "supplemental_motorcycle_duplicate_total": 0,
            "supplemental_motorcycle_accepted_total": 0,
            "supplemental_motorcycle_track_created_total": 0,
            "supplemental_motorcycle_track_matched_total": 0,
            "supplemental_motorcycle_active_track_count": 0,
            "supplemental_motorcycle_max_active_tracks": 0,
            "frames_with_motorcycle_detection": 0,
            "stabilized_class_switch_total": 0,
            "stabilized_class_switch_by_pair": {},
        }

        job.total_frames = effective_total_frames
        job.annotated_relative_path = annotated_relative_path
        db.commit()

        track_last_points: dict[int, tuple[float, float]] = {}
        counted_track_lines: dict[int, set[int]] = {}
        track_states: dict[int, TrackState] = {}
        supplemental_motorcycle_tracks: dict[int, SupplementalTrack] = {}
        next_supplemental_motorcycle_track_id = SUPPLEMENTAL_MOTORCYCLE_TRACK_ID_START
        frame_number = 0
        processed_frames = 0
        sequence_no = 0
        report_events: list[dict] = []
        overlay_frames: list[dict] = []
        started_monotonic = time.perf_counter()

        while True:
            _raise_if_stop_requested(job_id)
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
            annotated_frame = working_frame.copy()

            # Pipeline order: road ROI -> model inference -> raw detections -> early filtering
            # -> track smoothing -> final vehicle classification -> overlay/event output.
            roi_frame = working_frame[analysis_roi.y1:analysis_roi.y2, analysis_roi.x1:analysis_roi.x2]
            raw_frame_detections: list[dict] = []
            results = model.track(
                roi_frame,
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
            boxes = getattr(result, "boxes", None)
            event_found = False
            frame_detections: list[dict] = []

            if boxes is not None and boxes.id is not None:
                track_ids = boxes.id.int().cpu().tolist()
                class_ids = boxes.cls.int().cpu().tolist()
                confidences = boxes.conf.float().cpu().tolist()
                box_values = boxes.xyxy.cpu().tolist()
                names = result.names
                performance_meta["raw_detection_total"] += len(track_ids)

                for track_id, class_id, confidence, xyxy in zip(track_ids, class_ids, confidences, box_values):
                    vehicle_class = COCO_CLASS_TO_VEHICLE_CLASS.get(class_id)
                    if not vehicle_class:
                        continue
                    performance_meta["raw_detection_by_class"][vehicle_class] = (
                        int(performance_meta["raw_detection_by_class"].get(vehicle_class, 0)) + 1
                    )

                    raw_bbox = _translate_bbox_from_roi(tuple(float(value) for value in xyxy), analysis_roi)
                    x1, y1, x2, y2 = raw_bbox
                    rejection_reason = _detection_candidate_rejection_reason(
                        vehicle_class=vehicle_class,
                        confidence=float(confidence),
                        bbox=raw_bbox,
                        frame_width=max(working_width, 1),
                        frame_height=max(working_height, 1),
                        config=config,
                    )
                    if rejection_reason:
                        performance_meta["rejected_detection_total"] += 1
                        rejected_by_reason = performance_meta["rejected_detection_by_reason"]
                        rejected_by_reason[rejection_reason] = int(rejected_by_reason.get(rejection_reason, 0)) + 1
                        continue
                    performance_meta["accepted_detection_total"] += 1
                    performance_meta["accepted_detection_by_class"][vehicle_class] = (
                        int(performance_meta["accepted_detection_by_class"].get(vehicle_class, 0)) + 1
                    )

                    source_label = _resolve_source_label(names, class_id)
                    raw_frame_detections.append(
                        {
                            "track_id": int(track_id),
                            "vehicle_class": vehicle_class,
                            "source_label": source_label,
                            "confidence": float(confidence),
                            "bbox": raw_bbox,
                            "source": "main_roi",
                        }
                    )

            supplemental_motorcycle_detections = _collect_supplemental_motorcycle_detections(
                model=supplemental_motorcycle_model,
                working_frame=working_frame,
                focus_rois=motorcycle_focus_rois,
                config=config,
                inference_device=inference_device,
            )
            _prune_supplemental_motorcycle_tracks(supplemental_motorcycle_tracks, frame_number)
            performance_meta["supplemental_motorcycle_raw_total"] += len(supplemental_motorcycle_detections)
            for supplemental_detection in supplemental_motorcycle_detections:
                raw_bbox = supplemental_detection["bbox"]
                if _is_duplicate_supplemental_motorcycle_detection(raw_bbox, raw_frame_detections):
                    performance_meta["supplemental_motorcycle_duplicate_total"] += 1
                    continue

                rejection_reason = _detection_candidate_rejection_reason(
                    vehicle_class=VEHICLE_CLASS_MOTORCYCLE,
                    confidence=float(supplemental_detection["confidence"]),
                    bbox=raw_bbox,
                    frame_width=max(working_width, 1),
                    frame_height=max(working_height, 1),
                    config=config,
                    min_confidence_override=SUPPLEMENTAL_MOTORCYCLE_CONFIDENCE_FLOOR,
                )
                if rejection_reason:
                    performance_meta["rejected_detection_total"] += 1
                    rejected_by_reason = performance_meta["rejected_detection_by_reason"]
                    reason = f"supplemental_{rejection_reason}"
                    rejected_by_reason[reason] = int(rejected_by_reason.get(reason, 0)) + 1
                    continue

                track_id, next_supplemental_motorcycle_track_id, track_status = _assign_supplemental_motorcycle_track_id(
                    tracks=supplemental_motorcycle_tracks,
                    bbox=raw_bbox,
                    frame_number=frame_number,
                    frame_width=max(working_width, 1),
                    frame_height=max(working_height, 1),
                    next_track_id=next_supplemental_motorcycle_track_id,
                )
                if track_status == "created":
                    performance_meta["supplemental_motorcycle_track_created_total"] += 1
                else:
                    performance_meta["supplemental_motorcycle_track_matched_total"] += 1

                performance_meta["accepted_detection_total"] += 1
                performance_meta["accepted_detection_by_class"][VEHICLE_CLASS_MOTORCYCLE] = (
                    int(performance_meta["accepted_detection_by_class"].get(VEHICLE_CLASS_MOTORCYCLE, 0)) + 1
                )
                performance_meta["supplemental_motorcycle_accepted_total"] += 1
                raw_frame_detections.append(
                    {
                        "track_id": int(track_id),
                        "vehicle_class": VEHICLE_CLASS_MOTORCYCLE,
                        "source_label": VEHICLE_CLASS_MOTORCYCLE,
                        "confidence": float(supplemental_detection["confidence"]),
                        "bbox": raw_bbox,
                        "source": "motorcycle_focus_tile",
                    }
                )

            performance_meta["supplemental_motorcycle_active_track_count"] = len(supplemental_motorcycle_tracks)
            performance_meta["supplemental_motorcycle_max_active_tracks"] = max(
                int(performance_meta.get("supplemental_motorcycle_max_active_tracks") or 0),
                len(supplemental_motorcycle_tracks),
            )

            if any(detection["vehicle_class"] == VEHICLE_CLASS_MOTORCYCLE for detection in raw_frame_detections):
                performance_meta["frames_with_motorcycle_detection"] += 1

            for raw_detection in raw_frame_detections:
                track_id = int(raw_detection["track_id"])
                vehicle_class = str(raw_detection["vehicle_class"])
                source_label = str(raw_detection["source_label"])
                confidence = float(raw_detection["confidence"])
                raw_bbox = raw_detection["bbox"]
                stabilized = _stabilize_track_detection(
                    track_states=track_states,
                    track_id=int(track_id),
                    frame_number=frame_number,
                    vehicle_class=vehicle_class,
                    source_label=source_label,
                    confidence=float(confidence),
                    bbox=raw_bbox,
                    frame_width=max(working_width, 1),
                    frame_height=max(working_height, 1),
                )
                stable_vehicle_class = stabilized["vehicle_class"]
                stable_source_label = stabilized["source_label"]
                stable_confidence = stabilized["confidence"]
                reference_vehicle_class = stabilized["reference_vehicle_class"]
                reference_source_label = stabilized["reference_source_label"]
                if reference_vehicle_class != vehicle_class:
                    performance_meta["stabilized_class_switch_total"] += 1
                    switch_key = f"{vehicle_class}->{reference_vehicle_class}"
                    switched_by_pair = performance_meta["stabilized_class_switch_by_pair"]
                    switched_by_pair[switch_key] = int(switched_by_pair.get(switch_key, 0)) + 1
                x1, y1, x2, y2 = stabilized["bbox"]
                stable_bbox = (x1, y1, x2, y2)
                classification_result = classify_vehicle(
                    vehicle_class=reference_vehicle_class,
                    source_label=reference_source_label,
                    bbox=stabilized["reference_bbox"],
                    frame_width=max(working_width, 1),
                    frame_height=max(working_height, 1),
                    master_class_lookup=master_class_lookup,
                )
                display_label = _resolve_detection_label(
                    classification_result.vehicle_type_code,
                    classification_result.vehicle_type_label,
                    reference_vehicle_class,
                )

                frame_detections.append(
                    {
                        "track_id": int(track_id),
                        "vehicle_class": reference_vehicle_class,
                        "source_label": reference_source_label,
                        "detected_label": classification_result.raw_detected_label,
                        "vehicle_type_code": classification_result.vehicle_type_code,
                        "vehicle_type_label": classification_result.vehicle_type_label,
                        "display_label": display_label,
                        "golongan_code": classification_result.golongan_code,
                        "golongan_label": classification_result.golongan_label,
                        "detection_source": raw_detection.get("source"),
                        "confidence": round(float(stable_confidence), 4),
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
                        direction = _detect_line_crossing(line_start, line_end, previous_point, point)
                        if direction:
                            crossed_lines.append((line_order, direction, line))

                    if crossed_lines:
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
                                    vehicle_class=reference_vehicle_class,
                                    detected_label=classification_result.raw_detected_label,
                                    vehicle_type_code=classification_result.vehicle_type_code,
                                    vehicle_type_label=classification_result.vehicle_type_label,
                                    golongan_code=classification_result.golongan_code,
                                    golongan_label=classification_result.golongan_label,
                                    source_label=reference_source_label,
                                    count_line_order=line_order,
                                    count_line_name=line.name,
                                    direction=direction,
                                    crossed_at_seconds=float(frame_number / fps),
                                    crossed_at_frame=frame_number,
                                    confidence=float(stable_confidence),
                                    speed_kph=None,
                                    bbox_x1=x1 * scale_x,
                                    bbox_y1=y1 * scale_y,
                                    bbox_x2=x2 * scale_x,
                                    bbox_y2=y2 * scale_y,
                                )
                            )

                            totals_map[classification_result.golongan_code].vehicle_count += 1
                            counts_by_golongan[classification_result.golongan_code] += 1
                            report_events.append(
                                {
                                    "sequence_no": sequence_no,
                                    "track_id": int(track_id),
                                    "vehicle_class": reference_vehicle_class,
                                    "detected_label": classification_result.raw_detected_label,
                                    "vehicle_type_code": classification_result.vehicle_type_code,
                                    "vehicle_type_label": classification_result.vehicle_type_label,
                                    "golongan_code": classification_result.golongan_code,
                                    "golongan_label": classification_result.golongan_label,
                                    "source_label": reference_source_label,
                                    "count_line_order": line_order,
                                    "count_line_name": line.name,
                                    "direction": direction,
                                    "crossed_at_seconds": float(frame_number / fps),
                                    "crossed_at_frame": frame_number,
                                    "confidence": float(stable_confidence),
                                    "speed_kph": None,
                                    "bbox_x1": x1 * scale_x,
                                    "bbox_y1": y1 * scale_y,
                                    "bbox_x2": x2 * scale_x,
                                    "bbox_y2": y2 * scale_y,
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

            _draw_detection_boxes(
                annotated_frame,
                frame_detections,
                working_width,
                working_height,
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

        report_events = _build_report_events_from_overlay_frames(
            overlay_frames,
            lines=lines,
            source_width=source_width,
            source_height=source_height,
            master_class_lookup=master_class_lookup,
        )
        report_events = _reconcile_close_parallel_line_events(
            report_events,
            lines=lines,
            frame_width=max(source_width, 1),
            frame_height=max(source_height, 1),
            fps=fps,
        )
        report_events, counts_by_golongan = _persist_vehicle_events(
            db,
            video=video,
            job=job,
            site=site,
            totals_map=totals_map,
            events=report_events,
        )
        sequence_no = len(report_events)
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
                    "note": "Vehicle groups are estimated from detector output plus single-camera geometry heuristics. Re-run analysis after changing the official class mapping.",
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
    except AnalysisStopRequested:
        db.rollback()
        stop_requested = True
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
        if stop_requested:
            try:
                finish_preview(job_id)
            except OSError:
                pass
            _cleanup_stopped_analysis(db, video_id, job_id)
        db.close()
        clear_preview(job_id)
        clear_analysis_stop(job_id)


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
        "classification_note": (
            "Vehicle groups are inferred from detector output and single-camera geometry heuristics; "
            "axle configuration is estimated, not physically counted."
        ),
        "performance": performance or {},
    }


def _resolve_effective_frame_stride(source_fps: float, configured_stride: int, target_analysis_fps: float) -> int:
    configured_stride = max(int(configured_stride), 1)
    if source_fps <= 0 or target_analysis_fps <= 0:
        return configured_stride

    max_stride_for_target = max(int(math.floor(source_fps / target_analysis_fps)), 1)
    return max(min(configured_stride, max_stride_for_target), 1)


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


def _build_motorcycle_focus_rois(
    analysis_roi: AnalysisRoi,
    frame_width: int,
    frame_height: int,
) -> list[AnalysisRoi]:
    safe_width = max(int(frame_width), 1)
    safe_height = max(int(frame_height), 1)
    if analysis_roi.width < SUPPLEMENTAL_MOTORCYCLE_TILE_MIN_SIZE * 2:
        return []
    if analysis_roi.height < SUPPLEMENTAL_MOTORCYCLE_TILE_MIN_SIZE * 2:
        return []

    column_count = 2 if analysis_roi.width >= 800 else 1
    row_count = 2 if column_count == 1 and analysis_roi.height >= 600 else 1
    if column_count == 1 and row_count == 1:
        # ROI is not large enough to split into tiles but still big enough for a single
        # supplemental pass. Running motorcycle-only at lower confidence on the same region
        # catches bikes that fell below the main inference threshold.
        return [analysis_roi]

    overlap_x = int(round(analysis_roi.width * SUPPLEMENTAL_MOTORCYCLE_TILE_OVERLAP_RATIO))
    overlap_y = int(round(analysis_roi.height * SUPPLEMENTAL_MOTORCYCLE_TILE_OVERLAP_RATIO))
    cell_width = analysis_roi.width / float(column_count)
    cell_height = analysis_roi.height / float(row_count)
    focus_rois: list[AnalysisRoi] = []

    for row_index in range(row_count):
        for column_index in range(column_count):
            x1 = int(round(analysis_roi.x1 + (column_index * cell_width)))
            x2 = int(round(analysis_roi.x1 + ((column_index + 1) * cell_width)))
            y1 = int(round(analysis_roi.y1 + (row_index * cell_height)))
            y2 = int(round(analysis_roi.y1 + ((row_index + 1) * cell_height)))
            if column_index > 0:
                x1 -= overlap_x
            if column_index < column_count - 1:
                x2 += overlap_x
            if row_index > 0:
                y1 -= overlap_y
            if row_index < row_count - 1:
                y2 += overlap_y

            roi = AnalysisRoi(
                x1=max(min(x1, safe_width - 1), 0),
                y1=max(min(y1, safe_height - 1), 0),
                x2=max(min(x2, safe_width), 1),
                y2=max(min(y2, safe_height), 1),
            )
            if roi.width >= SUPPLEMENTAL_MOTORCYCLE_TILE_MIN_SIZE and roi.height >= SUPPLEMENTAL_MOTORCYCLE_TILE_MIN_SIZE:
                focus_rois.append(roi)

    return focus_rois


def _supplemental_motorcycle_confidence(config: ProcessConfig) -> float:
    return max(
        min(config.confidence_threshold, config.motorcycle_min_confidence, SUPPLEMENTAL_MOTORCYCLE_CONFIDENCE_FLOOR),
        SUPPLEMENTAL_MOTORCYCLE_CONFIDENCE_FLOOR,
    )


def _collect_supplemental_motorcycle_detections(
    *,
    model,
    working_frame,
    focus_rois: list[AnalysisRoi],
    config: ProcessConfig,
    inference_device: str,
) -> list[dict]:
    detections: list[dict] = []
    if model is None or not focus_rois:
        return detections

    for focus_roi in focus_rois:
        tile_frame = working_frame[focus_roi.y1:focus_roi.y2, focus_roi.x1:focus_roi.x2]
        if tile_frame.size == 0:
            continue
        results = model.predict(
            tile_frame,
            verbose=False,
            device=inference_device,
            imgsz=config.inference_imgsz,
            conf=_supplemental_motorcycle_confidence(config),
            iou=max(config.iou_threshold, 0.55),
            classes=[3],
        )
        if not results:
            continue
        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            continue

        confidences = boxes.conf.float().cpu().tolist()
        box_values = boxes.xyxy.cpu().tolist()
        for confidence, xyxy in zip(confidences, box_values):
            bbox = _translate_bbox_from_roi(tuple(float(value) for value in xyxy), focus_roi)
            detections.append(
                {
                    "vehicle_class": VEHICLE_CLASS_MOTORCYCLE,
                    "source_label": VEHICLE_CLASS_MOTORCYCLE,
                    "confidence": float(confidence),
                    "bbox": bbox,
                    "source": "motorcycle_focus_tile",
                }
            )

    return detections


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


def _resolve_analysis_roi(
    lines: list[CountLine | VideoCountLine],
    frame_width: int,
    frame_height: int,
) -> AnalysisRoi:
    safe_width = max(int(frame_width), 1)
    safe_height = max(int(frame_height), 1)
    active_lines = [line for line in lines if getattr(line, "is_active", True)]
    top_ratio = ROAD_ROI_DEFAULT_TOP_RATIO

    if active_lines:
        highest_line_ratio = min(
            min(float(line.start_y), float(line.end_y))
            for line in active_lines
        )
        top_ratio = max(highest_line_ratio - ROAD_ROI_CONTEXT_ABOVE_LINE_RATIO, 0.0)
        top_ratio = min(top_ratio, ROAD_ROI_MAX_TOP_RATIO)

    top_ratio = max(min(top_ratio, ROAD_ROI_MAX_TOP_RATIO), 0.0)
    if (1.0 - top_ratio) < ROAD_ROI_MIN_HEIGHT_RATIO:
        top_ratio = max(1.0 - ROAD_ROI_MIN_HEIGHT_RATIO, 0.0)

    return AnalysisRoi(
        x1=0,
        y1=max(int(round(safe_height * top_ratio)), 0),
        x2=safe_width,
        y2=safe_height,
    )


def _translate_bbox_from_roi(
    bbox: tuple[float, float, float, float],
    roi: AnalysisRoi,
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = bbox
    return (
        float(x1) + float(roi.x1),
        float(y1) + float(roi.y1),
        float(x2) + float(roi.x1),
        float(y2) + float(roi.y1),
    )


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    return max(float(bbox[2]) - float(bbox[0]), 0.0) * max(float(bbox[3]) - float(bbox[1]), 0.0)


def _bbox_contains_point(bbox: tuple[float, float, float, float], point: tuple[float, float]) -> bool:
    return float(bbox[0]) <= point[0] <= float(bbox[2]) and float(bbox[1]) <= point[1] <= float(bbox[3])


def _is_duplicate_supplemental_motorcycle_detection(
    bbox: tuple[float, float, float, float],
    accepted_detections: list[dict],
) -> bool:
    center = _bbox_center(bbox)
    supplemental_area = max(_bbox_area(bbox), 1.0)
    for accepted_detection in accepted_detections:
        accepted_bbox = accepted_detection.get("bbox")
        if not accepted_bbox:
            continue
        accepted_vehicle_class = str(accepted_detection.get("vehicle_class") or "")
        iou = _bbox_iou(bbox, accepted_bbox)
        if iou >= 0.38:
            return True
        if accepted_vehicle_class == VEHICLE_CLASS_MOTORCYCLE and _bbox_contains_point(accepted_bbox, center):
            return True
        if accepted_vehicle_class != VEHICLE_CLASS_MOTORCYCLE:
            accepted_area = max(_bbox_area(accepted_bbox), 1.0)
            if iou >= 0.22 and supplemental_area >= accepted_area * 0.55:
                return True
    return False


def _assign_supplemental_motorcycle_track_id(
    *,
    tracks: dict[int, SupplementalTrack],
    bbox: tuple[float, float, float, float],
    frame_number: int,
    frame_width: int,
    frame_height: int,
    next_track_id: int,
) -> tuple[int, int, str]:
    _prune_supplemental_motorcycle_tracks(tracks, frame_number)

    center = _bbox_center(bbox)
    width = max(float(bbox[2]) - float(bbox[0]), 1.0)
    height = max(float(bbox[3]) - float(bbox[1]), 1.0)
    diagonal = max(math.hypot(width, height), 8.0)
    frame_diagonal = max(math.hypot(float(frame_width), float(frame_height)), 1.0)
    distance_limit = max(diagonal * 3.2, frame_diagonal * 0.035, 18.0)
    best_track_id: Optional[int] = None
    best_score = float("inf")

    for track_id, track in tracks.items():
        if track.last_seen_frame == frame_number:
            continue
        predicted_center = (
            track.last_center[0] + track.last_velocity[0],
            track.last_center[1] + track.last_velocity[1],
        )
        distance = math.hypot(center[0] - predicted_center[0], center[1] - predicted_center[1])
        iou = _bbox_iou(bbox, track.bbox)
        score = (distance / distance_limit) - (iou * 0.55)
        if score < best_score:
            best_track_id = track_id
            best_score = score

    if best_track_id is not None and best_score <= 1.0:
        track = tracks[best_track_id]
        velocity = (center[0] - track.last_center[0], center[1] - track.last_center[1])
        tracks[best_track_id] = SupplementalTrack(
            bbox=bbox,
            last_seen_frame=frame_number,
            last_center=center,
            last_velocity=velocity,
        )
        return best_track_id, next_track_id, "matched"

    track_id = next_track_id
    tracks[track_id] = SupplementalTrack(
        bbox=bbox,
        last_seen_frame=frame_number,
        last_center=center,
        last_velocity=(0.0, 0.0),
    )
    return track_id, next_track_id + 1, "created"


def _prune_supplemental_motorcycle_tracks(
    tracks: dict[int, SupplementalTrack],
    frame_number: int,
) -> None:
    for track_id, track in list(tracks.items()):
        if (frame_number - track.last_seen_frame) > SUPPLEMENTAL_MOTORCYCLE_TRACK_MAX_GAP_FRAMES:
            tracks.pop(track_id, None)


def _resolve_detection_label(vehicle_type_code: str, vehicle_type_label: str, vehicle_class: str) -> str:
    if vehicle_type_code == "motorcycle_three_wheeler":
        return "motorcycle"
    if vehicle_type_code in {"passenger_car", "medium_passenger", "pickup_micro_delivery"}:
        return "car"
    if vehicle_type_code in {"small_bus", "large_bus"}:
        return "bus"
    if vehicle_type_code in {
        "light_truck_2_axle",
        "medium_truck_2_axle",
        "truck_3_axle",
        "articulated_truck",
        "semi_trailer_truck",
    }:
        return "truck"
    if vehicle_type_code == "non_motorized":
        return "non-motorized"
    return str(vehicle_type_label or vehicle_class or "-")


def _resolve_class_min_confidence(vehicle_class: str, config: ProcessConfig) -> float:
    if vehicle_class in {VEHICLE_CLASS_BICYCLE, VEHICLE_CLASS_MOTORCYCLE}:
        return max(config.confidence_threshold, config.motorcycle_min_confidence)
    if vehicle_class == VEHICLE_CLASS_CAR:
        return max(config.confidence_threshold, config.car_min_confidence)
    if vehicle_class == VEHICLE_CLASS_BUS:
        return max(config.confidence_threshold, config.bus_min_confidence)
    if vehicle_class == VEHICLE_CLASS_TRUCK:
        return max(config.confidence_threshold, config.truck_min_confidence)
    return config.confidence_threshold


def _decay_score_map(scores: dict[str, float]) -> dict[str, float]:
    next_scores: dict[str, float] = {}
    for key, value in scores.items():
        decayed = float(value) * TRACK_SCORE_DECAY
        if decayed >= TRACK_SCORE_FLOOR:
            next_scores[key] = decayed
    return next_scores


def _detection_evidence_score(
    vehicle_class: str,
    confidence: float,
    bbox: tuple[float, float, float, float],
    frame_width: int,
    frame_height: int,
    previous_bbox: Optional[tuple[float, float, float, float]] = None,
    previous_velocity: Optional[tuple[float, float]] = None,
    dominant_vehicle_class: Optional[str] = None,
) -> float:
    width = max(float(bbox[2]) - float(bbox[0]), 1.0)
    height = max(float(bbox[3]) - float(bbox[1]), 1.0)
    area = width * height
    frame_area = max(float(frame_width * frame_height), 1.0)
    normalized_area = min(max(area / frame_area, 0.0), 1.0)
    area_term = 0.78 + min(math.sqrt(normalized_area / 0.01), 1.0) * 0.28
    confidence_term = 0.45 + (max(float(confidence), 0.01) * 0.95)
    class_bias = {
        VEHICLE_CLASS_MOTORCYCLE: 1.22,
        VEHICLE_CLASS_BICYCLE: 1.06,
        VEHICLE_CLASS_CAR: 1.0,
        VEHICLE_CLASS_BUS: 1.0,
        VEHICLE_CLASS_TRUCK: 1.0,
    }.get(vehicle_class, 1.0)
    continuity_term = 1.0
    if previous_bbox is not None:
        continuity_term = _track_continuity_score(previous_bbox, bbox, previous_velocity)
    if dominant_vehicle_class:
        consistency_bonus = 1.16 if dominant_vehicle_class == vehicle_class else 0.84
    else:
        consistency_bonus = 1.0
    return max(confidence_term * area_term * class_bias * continuity_term * consistency_bonus, 0.01)


def _bbox_center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((float(bbox[0]) + float(bbox[2])) / 2.0, (float(bbox[1]) + float(bbox[3])) / 2.0)


def _bbox_iou(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    inter_x1 = max(float(left[0]), float(right[0]))
    inter_y1 = max(float(left[1]), float(right[1]))
    inter_x2 = min(float(left[2]), float(right[2]))
    inter_y2 = min(float(left[3]), float(right[3]))
    inter_w = max(inter_x2 - inter_x1, 0.0)
    inter_h = max(inter_y2 - inter_y1, 0.0)
    inter_area = inter_w * inter_h
    if inter_area <= 0:
        return 0.0
    left_area = max((float(left[2]) - float(left[0])) * (float(left[3]) - float(left[1])), 0.0)
    right_area = max((float(right[2]) - float(right[0])) * (float(right[3]) - float(right[1])), 0.0)
    union = max(left_area + right_area - inter_area, 1e-6)
    return inter_area / union


def _track_continuity_score(
    previous_bbox: tuple[float, float, float, float],
    current_bbox: tuple[float, float, float, float],
    previous_velocity: Optional[tuple[float, float]],
) -> float:
    previous_center = _bbox_center(previous_bbox)
    current_center = _bbox_center(current_bbox)
    displacement = math.hypot(current_center[0] - previous_center[0], current_center[1] - previous_center[1])
    previous_width = max(float(previous_bbox[2]) - float(previous_bbox[0]), 1.0)
    previous_height = max(float(previous_bbox[3]) - float(previous_bbox[1]), 1.0)
    previous_diagonal = max(math.hypot(previous_width, previous_height), 1.0)
    normalized_displacement = displacement / max(previous_diagonal * 1.8, 8.0)
    proximity_term = max(0.45, 1.22 - min(normalized_displacement, 1.1))
    iou_term = 0.72 + (_bbox_iou(previous_bbox, current_bbox) * 0.58)
    velocity_term = 1.0
    if previous_velocity is not None:
        current_velocity = (current_center[0] - previous_center[0], current_center[1] - previous_center[1])
        velocity_delta = math.hypot(
            current_velocity[0] - previous_velocity[0],
            current_velocity[1] - previous_velocity[1],
        )
        velocity_scale = max(previous_diagonal * 1.4, 8.0)
        velocity_term = max(0.7, 1.15 - min(velocity_delta / velocity_scale, 0.45))
    return max(min(proximity_term * iou_term * velocity_term, 1.75), 0.55)


def _draw_detection_boxes(
    frame,
    detections: list[dict],
    frame_width: int,
    frame_height: int,
) -> None:
    import cv2

    class_colors = {
        VEHICLE_CLASS_MOTORCYCLE: (0, 221, 109),
        VEHICLE_CLASS_CAR: (82, 184, 255),
        VEHICLE_CLASS_BUS: (87, 88, 255),
        VEHICLE_CLASS_TRUCK: (0, 192, 255),
        VEHICLE_CLASS_BICYCLE: (186, 107, 255),
    }

    for detection in detections:
        x1 = int(round(float(detection["x1"]) * max(frame_width, 1)))
        y1 = int(round(float(detection["y1"]) * max(frame_height, 1)))
        x2 = int(round(float(detection["x2"]) * max(frame_width, 1)))
        y2 = int(round(float(detection["y2"]) * max(frame_height, 1)))
        vehicle_class = str(detection.get("vehicle_class") or "").strip().lower()
        color = class_colors.get(vehicle_class, (82, 184, 255))
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        display_label = str(
            detection.get("display_label")
            or detection.get("vehicle_type_label")
            or detection.get("detected_label")
            or detection.get("vehicle_class")
            or "-"
        )
        track_id = detection.get("track_id")
        confidence = float(detection.get("confidence") or 0.0)
        label = f"{track_id if track_id is not None else '-'} {display_label} {confidence * 100:.0f}%"
        text_scale = 0.5
        text_thickness = 1
        (text_width, text_height), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, text_scale, text_thickness)
        label_y = max(y1 - text_height - baseline - 8, 0)
        label_x2 = min(x1 + text_width + 12, frame_width - 1)
        cv2.rectangle(frame, (x1, label_y), (label_x2, max(y1 - 2, label_y + text_height + baseline + 6)), (12, 28, 46), thickness=-1)
        cv2.putText(
            frame,
            label,
            (x1 + 6, label_y + text_height + 1),
            cv2.FONT_HERSHEY_SIMPLEX,
            text_scale,
            (255, 255, 255),
            text_thickness,
            cv2.LINE_AA,
        )



def _pick_dominant_score(scores: dict[str, float], fallback: str) -> str:
    if not scores:
        return fallback
    return max(scores.items(), key=lambda item: item[1])[0]


def _pick_dominant_track_class(
    class_scores: dict[str, float],
    class_reference_scores: dict[str, float],
    fallback: str,
) -> str:
    if not class_scores and not class_reference_scores:
        return fallback

    candidate_keys = set(class_scores) | set(class_reference_scores)
    best_key = max(
        candidate_keys,
        key=lambda key: _combined_track_class_score(key, class_scores, class_reference_scores),
    )
    fallback_key = str(fallback or "").strip().lower()
    if fallback_key in candidate_keys and best_key != fallback_key:
        best_score = _combined_track_class_score(best_key, class_scores, class_reference_scores)
        fallback_score = _combined_track_class_score(fallback_key, class_scores, class_reference_scores)
        if best_score < (fallback_score * _track_class_switch_margin(fallback_key, best_key)):
            return fallback_key
    return best_key


def _combined_track_class_score(
    vehicle_class: str,
    class_scores: dict[str, float],
    class_reference_scores: dict[str, float],
) -> float:
    return (float(class_reference_scores.get(vehicle_class, 0.0)) * 0.68) + (
        float(class_scores.get(vehicle_class, 0.0)) * 0.32
    )


def _track_class_switch_margin(current_class: str, candidate_class: str) -> float:
    large_classes = {VEHICLE_CLASS_BUS, VEHICLE_CLASS_TRUCK}
    small_vehicle_classes = {VEHICLE_CLASS_MOTORCYCLE, VEHICLE_CLASS_BICYCLE}
    if current_class in large_classes and candidate_class in small_vehicle_classes:
        return TRACK_LARGE_TO_MOTORCYCLE_SWITCH_MARGIN
    if current_class in small_vehicle_classes and candidate_class in large_classes:
        return TRACK_MOTORCYCLE_TO_LARGE_SWITCH_MARGIN
    if {current_class, candidate_class}.issubset(large_classes):
        return TRACK_CLASS_SWITCH_MARGIN
    return 1.35


def _blend_bbox(
    previous_bbox: tuple[float, float, float, float],
    current_bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    return tuple(
        (float(previous_value) * (1.0 - TRACK_BBOX_SMOOTHING_ALPHA)) + (float(current_value) * TRACK_BBOX_SMOOTHING_ALPHA)
        for previous_value, current_value in zip(previous_bbox, current_bbox)
    )


def _stabilize_track_detection(
    track_states: dict[int, TrackState],
    track_id: int,
    frame_number: int,
    vehicle_class: str,
    source_label: str,
    confidence: float,
    bbox: tuple[float, float, float, float],
    frame_width: int,
    frame_height: int,
) -> dict:
    fallback_label = source_label or RAW_DETECTION_LABELS.get(vehicle_class, vehicle_class)
    state = track_states.get(track_id)
    current_center = _bbox_center(bbox)
    previous_reference_class = state.reference_vehicle_class if state is not None else None
    reference_score = _detection_evidence_score(
        vehicle_class,
        confidence,
        bbox,
        frame_width,
        frame_height,
        previous_bbox=state.bbox if state is not None else None,
        previous_velocity=state.last_velocity if state is not None else None,
        dominant_vehicle_class=previous_reference_class,
    )

    if state is None or (frame_number - state.last_seen_frame) > TRACK_STATE_RESET_GAP_FRAMES:
        state = TrackState(
            bbox=bbox,
            confidence=float(confidence),
            last_seen_frame=frame_number,
            seen_frames=1,
            class_scores={vehicle_class: reference_score},
            label_scores={fallback_label: reference_score},
            class_reference_boxes={vehicle_class: bbox},
            class_reference_scores={vehicle_class: reference_score},
            class_reference_labels={vehicle_class: fallback_label},
            last_center=current_center,
            last_velocity=(0.0, 0.0),
            reference_bbox=bbox,
            reference_score=reference_score,
            reference_vehicle_class=vehicle_class,
            reference_source_label=fallback_label,
        )
        track_states[track_id] = state
        return {
            "bbox": bbox,
            "confidence": float(confidence),
            "vehicle_class": vehicle_class,
            "source_label": fallback_label,
            "reference_bbox": bbox,
            "reference_vehicle_class": vehicle_class,
            "reference_source_label": fallback_label,
        }

    state.class_scores = _decay_score_map(state.class_scores)
    state.label_scores = _decay_score_map(state.label_scores)
    state.class_scores[vehicle_class] = state.class_scores.get(vehicle_class, 0.0) + reference_score
    state.label_scores[fallback_label] = state.label_scores.get(fallback_label, 0.0) + reference_score
    state.bbox = _blend_bbox(state.bbox, bbox)
    state.confidence = (state.confidence * (1.0 - TRACK_CONFIDENCE_SMOOTHING_ALPHA)) + (
        float(confidence) * TRACK_CONFIDENCE_SMOOTHING_ALPHA
    )
    current_velocity = (
        current_center[0] - state.last_center[0],
        current_center[1] - state.last_center[1],
    )
    state.last_center = current_center
    state.last_velocity = current_velocity
    state.seen_frames += 1

    existing_class_reference_score = float(state.class_reference_scores.get(vehicle_class, 0.0))
    if reference_score >= existing_class_reference_score:
        state.class_reference_boxes[vehicle_class] = bbox
        state.class_reference_scores[vehicle_class] = reference_score
        state.class_reference_labels[vehicle_class] = fallback_label

    dominant_vehicle_class = _pick_dominant_track_class(
        state.class_scores,
        state.class_reference_scores,
        previous_reference_class or vehicle_class,
    )
    dominant_reference_bbox = state.class_reference_boxes.get(dominant_vehicle_class, state.bbox)
    dominant_reference_score = float(state.class_reference_scores.get(dominant_vehicle_class, reference_score))
    dominant_source_label = state.class_reference_labels.get(
        dominant_vehicle_class,
        _pick_dominant_score(state.label_scores, fallback_label),
    )
    state.reference_bbox = dominant_reference_bbox
    state.reference_score = dominant_reference_score
    state.reference_vehicle_class = dominant_vehicle_class
    state.reference_source_label = dominant_source_label
    state.last_seen_frame = frame_number

    return {
        "bbox": state.bbox,
        "confidence": float(state.confidence),
        "vehicle_class": dominant_vehicle_class,
        "source_label": dominant_source_label,
        "reference_bbox": state.reference_bbox,
        "reference_vehicle_class": state.reference_vehicle_class,
        "reference_source_label": state.reference_source_label,
    }


def _point_side(line_start: tuple[float, float], line_end: tuple[float, float], point: tuple[float, float]) -> float:
    return ((line_end[0] - line_start[0]) * (point[1] - line_start[1])) - (
        (line_end[1] - line_start[1]) * (point[0] - line_start[0])
    )


def _vector_subtract(left: tuple[float, float], right: tuple[float, float]) -> tuple[float, float]:
    return (float(left[0]) - float(right[0]), float(left[1]) - float(right[1]))


def _dot_2d(left: tuple[float, float], right: tuple[float, float]) -> float:
    return (float(left[0]) * float(right[0])) + (float(left[1]) * float(right[1]))


def _cross_2d(left: tuple[float, float], right: tuple[float, float]) -> float:
    return (float(left[0]) * float(right[1])) - (float(left[1]) * float(right[0]))


def _line_unit_vectors(
    line_start: tuple[float, float],
    line_end: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float]]:
    tangent = _vector_subtract(line_end, line_start)
    magnitude = math.hypot(tangent[0], tangent[1]) or 1.0
    unit_tangent = (tangent[0] / magnitude, tangent[1] / magnitude)
    unit_normal = (-unit_tangent[1], unit_tangent[0])
    return unit_tangent, unit_normal


def _line_midpoint(line: CountLine | VideoCountLine) -> tuple[float, float]:
    return ((float(line.start_x) + float(line.end_x)) / 2.0, (float(line.start_y) + float(line.end_y)) / 2.0)


def _line_projection(line: CountLine | VideoCountLine, unit_normal: tuple[float, float]) -> float:
    midpoint = _line_midpoint(line)
    return _dot_2d(midpoint, unit_normal)


def _segments_intersect(
    segment_start: tuple[float, float],
    segment_end: tuple[float, float],
    line_start: tuple[float, float],
    line_end: tuple[float, float],
    epsilon: float = LINE_INTERSECTION_EPSILON,
) -> bool:
    segment_vector = _vector_subtract(segment_end, segment_start)
    line_vector = _vector_subtract(line_end, line_start)
    origin_delta = _vector_subtract(line_start, segment_start)

    cross_value = _cross_2d(segment_vector, line_vector)
    collinear_value = _cross_2d(origin_delta, segment_vector)

    if abs(cross_value) <= epsilon and abs(collinear_value) <= epsilon:
        return False
    if abs(cross_value) <= epsilon:
        return False

    segment_ratio = _cross_2d(origin_delta, line_vector) / cross_value
    line_ratio = _cross_2d(origin_delta, segment_vector) / cross_value
    return (
        (-epsilon <= segment_ratio <= 1.0 + epsilon)
        and (-epsilon <= line_ratio <= 1.0 + epsilon)
    )


def _detect_line_crossing(
    line_start: tuple[float, float],
    line_end: tuple[float, float],
    previous_point: tuple[float, float],
    current_point: tuple[float, float],
) -> Optional[str]:
    if not _segments_intersect(previous_point, current_point, line_start, line_end):
        return None

    _, unit_normal = _line_unit_vectors(line_start, line_end)
    motion_vector = _vector_subtract(current_point, previous_point)
    motion_along_normal = _dot_2d(motion_vector, unit_normal)
    if abs(motion_along_normal) <= LINE_INTERSECTION_EPSILON:
        previous_side = _point_side(line_start, line_end, previous_point)
        current_side = _point_side(line_start, line_end, current_point)
        if previous_side * current_side >= 0:
            return None
        motion_along_normal = current_side - previous_side

    return DIRECTION_NORMAL if motion_along_normal > 0 else DIRECTION_OPPOSITE


def _line_anchor_projection(
    event: dict,
    unit_tangent: tuple[float, float],
    frame_width: int,
    frame_height: int,
) -> float:
    x1 = float(event.get("bbox_x1") or 0.0) / max(float(frame_width), 1.0)
    x2 = float(event.get("bbox_x2") or 0.0) / max(float(frame_width), 1.0)
    y2 = float(event.get("bbox_y2") or 0.0) / max(float(frame_height), 1.0)
    anchor_point = ((x1 + x2) / 2.0, y2)
    return _dot_2d(anchor_point, unit_tangent)


def _close_parallel_line_pair(lines: list[CountLine | VideoCountLine]) -> bool:
    if len(lines) != 2:
        return False

    first_tangent, first_normal = _line_unit_vectors(
        (float(lines[0].start_x), float(lines[0].start_y)),
        (float(lines[0].end_x), float(lines[0].end_y)),
    )
    second_tangent, _ = _line_unit_vectors(
        (float(lines[1].start_x), float(lines[1].start_y)),
        (float(lines[1].end_x), float(lines[1].end_y)),
    )
    tangent_alignment = abs(_dot_2d(first_tangent, second_tangent))
    max_angle_radians = math.radians(CLOSE_LINE_PAIR_MAX_ANGLE_DEGREES)
    if tangent_alignment < math.cos(max_angle_radians):
        return False

    gap_ratio = abs(_line_projection(lines[0], first_normal) - _line_projection(lines[1], first_normal))
    return gap_ratio <= CLOSE_LINE_PAIR_MAX_GAP_RATIO


def _expected_line_orders(
    lines_by_order: dict[int, CountLine | VideoCountLine],
    unit_normal: tuple[float, float],
    direction: str,
) -> tuple[int, int]:
    ordered_line_orders = sorted(lines_by_order, key=lambda order: _line_projection(lines_by_order[order], unit_normal))
    if direction == DIRECTION_NORMAL:
        return ordered_line_orders[0], ordered_line_orders[1]
    return ordered_line_orders[1], ordered_line_orders[0]


def _match_reconciled_line_events(
    first_events: list[dict],
    second_events: list[dict],
    unit_tangent: tuple[float, float],
    frame_width: int,
    frame_height: int,
) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    first_ordered = sorted(first_events, key=lambda event: float(event.get("crossed_at_seconds") or 0.0))
    second_ordered = sorted(second_events, key=lambda event: float(event.get("crossed_at_seconds") or 0.0))
    used_second_indexes: set[int] = set()
    pairs: list[tuple[dict, dict]] = []
    unmatched_first: list[dict] = []

    for first_event in first_ordered:
        first_time = float(first_event.get("crossed_at_seconds") or 0.0)
        first_projection = _line_anchor_projection(first_event, unit_tangent, frame_width, frame_height)
        best_index: Optional[int] = None
        best_score: Optional[float] = None

        for second_index, second_event in enumerate(second_ordered):
            if second_index in used_second_indexes:
                continue

            second_time = float(second_event.get("crossed_at_seconds") or 0.0)
            delta_seconds = second_time - first_time
            if delta_seconds < -0.2 or delta_seconds > CLOSE_LINE_PAIR_MAX_TIME_GAP_SECONDS:
                continue

            second_projection = _line_anchor_projection(second_event, unit_tangent, frame_width, frame_height)
            tangent_gap = abs(second_projection - first_projection)
            if tangent_gap > CLOSE_LINE_PAIR_MAX_TANGENT_GAP_RATIO:
                continue

            class_penalty = 0.0
            if str(second_event.get("vehicle_class") or "") != str(first_event.get("vehicle_class") or ""):
                class_penalty = 0.35
            score = delta_seconds + (tangent_gap * 4.0) + class_penalty
            if best_score is None or score < best_score:
                best_score = score
                best_index = second_index

        if best_index is None:
            unmatched_first.append(first_event)
            continue

        used_second_indexes.add(best_index)
        pairs.append((first_event, second_ordered[best_index]))

    unmatched_second = [
        event
        for second_index, event in enumerate(second_ordered)
        if second_index not in used_second_indexes
    ]
    return pairs, unmatched_first, unmatched_second


def _synthesize_line_event(
    event: dict,
    *,
    target_line: CountLine | VideoCountLine,
    time_offset_seconds: float,
    fps: float,
) -> dict:
    synthesized = dict(event)
    target_seconds = max(float(event.get("crossed_at_seconds") or 0.0) + float(time_offset_seconds), 0.0)
    synthesized["count_line_order"] = int(target_line.line_order)
    synthesized["count_line_name"] = target_line.name
    synthesized["crossed_at_seconds"] = round(target_seconds, 4)
    synthesized["crossed_at_frame"] = max(int(round(target_seconds * fps)), 1)
    return synthesized


def _build_track_profiles_from_overlay_frames(
    overlay_frames: list[dict],
    *,
    source_width: int,
    source_height: int,
    master_class_lookup: dict[str, dict],
) -> dict[int, TrackProfile]:
    track_states: dict[int, TrackState] = {}

    for frame in overlay_frames:
        source_frame_number = int(frame.get("source_frame") or 0)
        detections = frame.get("detections") or []
        for detection in detections:
            track_id = int(detection.get("track_id") or 0)
            if track_id <= 0:
                continue

            vehicle_class = str(detection.get("vehicle_class") or "").strip().lower()
            if not vehicle_class:
                continue

            source_label = str(
                detection.get("source_label")
                or detection.get("detected_label")
                or RAW_DETECTION_LABELS.get(vehicle_class, vehicle_class)
            ).strip().lower()
            bbox = (
                float(detection.get("x1") or 0.0) * max(float(source_width), 1.0),
                float(detection.get("y1") or 0.0) * max(float(source_height), 1.0),
                float(detection.get("x2") or 0.0) * max(float(source_width), 1.0),
                float(detection.get("y2") or 0.0) * max(float(source_height), 1.0),
            )
            confidence = float(detection.get("confidence") or 0.0)
            _stabilize_track_detection(
                track_states=track_states,
                track_id=track_id,
                frame_number=source_frame_number,
                vehicle_class=vehicle_class,
                source_label=source_label,
                confidence=confidence,
                bbox=bbox,
                frame_width=max(source_width, 1),
                frame_height=max(source_height, 1),
            )

    track_profiles: dict[int, TrackProfile] = {}
    for track_id, state in track_states.items():
        if not state.class_scores:
            continue

        dominant_vehicle_class = _pick_dominant_track_class(
            state.class_scores,
            state.class_reference_scores,
            state.reference_vehicle_class or VEHICLE_CLASS_CAR,
        )
        dominant_bbox = state.class_reference_boxes.get(dominant_vehicle_class)
        if dominant_bbox is None:
            continue

        dominant_source_label = str(
            state.class_reference_labels.get(
                dominant_vehicle_class,
                RAW_DETECTION_LABELS.get(dominant_vehicle_class, dominant_vehicle_class),
            )
        )
        classification_result = classify_vehicle(
            vehicle_class=dominant_vehicle_class,
            source_label=dominant_source_label,
            bbox=dominant_bbox,
            frame_width=max(source_width, 1),
            frame_height=max(source_height, 1),
            master_class_lookup=master_class_lookup,
        )
        track_profiles[track_id] = TrackProfile(
            vehicle_class=dominant_vehicle_class,
            source_label=dominant_source_label,
            detected_label=classification_result.raw_detected_label,
            vehicle_type_code=classification_result.vehicle_type_code,
            vehicle_type_label=classification_result.vehicle_type_label,
            golongan_code=classification_result.golongan_code,
            golongan_label=classification_result.golongan_label,
        )

    return track_profiles


def _build_report_events_from_overlay_frames(
    overlay_frames: list[dict],
    *,
    lines: list[CountLine | VideoCountLine],
    source_width: int,
    source_height: int,
    master_class_lookup: dict[str, dict],
) -> list[dict]:
    if not overlay_frames or not lines:
        return []

    normalized_line_segments = [
        (
            (float(line.start_x), float(line.start_y)),
            (float(line.end_x), float(line.end_y)),
        )
        for line in lines
    ]
    track_profiles = _build_track_profiles_from_overlay_frames(
        overlay_frames,
        source_width=source_width,
        source_height=source_height,
        master_class_lookup=master_class_lookup,
    )

    counted_track_lines: dict[int, set[int]] = {}
    track_last_points: dict[int, tuple[float, float]] = {}
    report_events: list[dict] = []

    ordered_frames = sorted(
        overlay_frames,
        key=lambda frame: (
            int(frame.get("source_frame") or 0),
            float(frame.get("time_seconds") or 0.0),
        ),
    )

    for frame in ordered_frames:
        time_seconds = float(frame.get("time_seconds") or 0.0)
        source_frame = int(frame.get("source_frame") or 0)
        detections = frame.get("detections") or []

        for detection in detections:
            if detection is None:
                continue

            track_id = int(detection.get("track_id") or 0)
            x1_ratio = float(detection.get("x1") or 0.0)
            y1_ratio = float(detection.get("y1") or 0.0)
            x2_ratio = float(detection.get("x2") or 0.0)
            y2_ratio = float(detection.get("y2") or 0.0)
            point = ((x1_ratio + x2_ratio) / 2.0, y2_ratio)
            previous_point = track_last_points.get(track_id)

            if previous_point is not None:
                counted_lines = counted_track_lines.setdefault(track_id, set())
                stable_vehicle_class = str(detection.get("vehicle_class") or "")
                stable_source_label = str(detection.get("source_label") or stable_vehicle_class)
                stable_confidence = float(detection.get("confidence") or 0.0)
                source_bbox = (
                    x1_ratio * max(float(source_width), 1.0),
                    y1_ratio * max(float(source_height), 1.0),
                    x2_ratio * max(float(source_width), 1.0),
                    y2_ratio * max(float(source_height), 1.0),
                )
                classification_result = classify_vehicle(
                    vehicle_class=stable_vehicle_class,
                    source_label=stable_source_label,
                    bbox=source_bbox,
                    frame_width=max(source_width, 1),
                    frame_height=max(source_height, 1),
                    master_class_lookup=master_class_lookup,
                )
                track_profile = track_profiles.get(track_id)
                final_vehicle_class = track_profile.vehicle_class if track_profile else stable_vehicle_class
                final_source_label = track_profile.source_label if track_profile else stable_source_label
                final_detected_label = track_profile.detected_label if track_profile else classification_result.raw_detected_label
                final_vehicle_type_code = track_profile.vehicle_type_code if track_profile else classification_result.vehicle_type_code
                final_vehicle_type_label = track_profile.vehicle_type_label if track_profile else classification_result.vehicle_type_label
                final_golongan_code = track_profile.golongan_code if track_profile else classification_result.golongan_code
                final_golongan_label = track_profile.golongan_label if track_profile else classification_result.golongan_label

                for line, (line_start, line_end) in zip(lines, normalized_line_segments):
                    line_order = int(line.line_order)
                    if line_order in counted_lines:
                        continue

                    direction = _detect_line_crossing(line_start, line_end, previous_point, point)
                    if not direction:
                        continue

                    counted_lines.add(line_order)
                    report_events.append(
                        {
                            "track_id": track_id,
                            "vehicle_class": final_vehicle_class,
                            "detected_label": final_detected_label,
                            "vehicle_type_code": final_vehicle_type_code,
                            "vehicle_type_label": final_vehicle_type_label,
                            "golongan_code": final_golongan_code,
                            "golongan_label": final_golongan_label,
                            "source_label": final_source_label,
                            "count_line_order": line_order,
                            "count_line_name": line.name,
                            "direction": direction,
                            "crossed_at_seconds": time_seconds,
                            "crossed_at_frame": source_frame,
                            "confidence": stable_confidence,
                            "speed_kph": None,
                            "bbox_x1": source_bbox[0],
                            "bbox_y1": source_bbox[1],
                            "bbox_x2": source_bbox[2],
                            "bbox_y2": source_bbox[3],
                        }
                    )

            track_last_points[track_id] = point

    return report_events


def _reconcile_close_parallel_line_events(
    events: list[dict],
    *,
    lines: list[CountLine | VideoCountLine],
    frame_width: int,
    frame_height: int,
    fps: float,
) -> list[dict]:
    if len(events) == 0 or not _close_parallel_line_pair(lines):
        return events

    lines_by_order = {int(line.line_order): line for line in lines}
    if len(lines_by_order) != 2:
        return events

    first_line = lines[0]
    unit_tangent, unit_normal = _line_unit_vectors(
        (float(first_line.start_x), float(first_line.start_y)),
        (float(first_line.end_x), float(first_line.end_y)),
    )

    preserved_events: list[dict] = []
    events_by_group: dict[tuple[int, str], list[dict]] = {}
    for event in events:
        line_order = int(event.get("count_line_order") or 0)
        direction = str(event.get("direction") or "")
        if line_order not in lines_by_order or direction not in {DIRECTION_NORMAL, DIRECTION_OPPOSITE}:
            preserved_events.append(event)
            continue
        events_by_group.setdefault((line_order, direction), []).append(event)

    reconciled_events = list(preserved_events)
    match_results: dict[str, tuple[tuple[int, int], list[tuple[dict, dict]], list[dict], list[dict]]] = {}
    all_delta_seconds: list[float] = []

    for direction in (DIRECTION_NORMAL, DIRECTION_OPPOSITE):
        first_order, second_order = _expected_line_orders(lines_by_order, unit_normal, direction)
        first_events = events_by_group.get((first_order, direction), [])
        second_events = events_by_group.get((second_order, direction), [])
        pairs, unmatched_first, unmatched_second = _match_reconciled_line_events(
            first_events,
            second_events,
            unit_tangent=unit_tangent,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        match_results[direction] = ((first_order, second_order), pairs, unmatched_first, unmatched_second)
        all_delta_seconds.extend(
            max(float(second_event.get("crossed_at_seconds") or 0.0) - float(first_event.get("crossed_at_seconds") or 0.0), 0.0)
            for first_event, second_event in pairs
        )

    default_delta_seconds = (
        max(float(sorted(all_delta_seconds)[len(all_delta_seconds) // 2]), 0.0)
        if all_delta_seconds
        else min(CLOSE_LINE_PAIR_MAX_TIME_GAP_SECONDS / 2.0, 1.0)
    )
    if default_delta_seconds <= 0:
        default_delta_seconds = min(CLOSE_LINE_PAIR_MAX_TIME_GAP_SECONDS / 2.0, 1.0)

    for direction in (DIRECTION_NORMAL, DIRECTION_OPPOSITE):
        (first_order, second_order), pairs, unmatched_first, unmatched_second = match_results[direction]
        first_events = events_by_group.get((first_order, direction), [])
        second_events = events_by_group.get((second_order, direction), [])
        if not first_events and not second_events:
            continue

        delta_seconds_samples = [
            max(float(second_event.get("crossed_at_seconds") or 0.0) - float(first_event.get("crossed_at_seconds") or 0.0), 0.0)
            for first_event, second_event in pairs
        ]
        median_delta_seconds = (
            max(float(sorted(delta_seconds_samples)[len(delta_seconds_samples) // 2]), 0.0)
            if delta_seconds_samples
            else default_delta_seconds
        )
        if median_delta_seconds <= 0:
            median_delta_seconds = default_delta_seconds

        reconciled_events.extend(first_events)
        reconciled_events.extend(second_events)

        if len(first_events) > len(second_events):
            deficit = len(first_events) - len(second_events)
            source_events = sorted(
                unmatched_first,
                key=lambda event: float(event.get("confidence") or 0.0),
                reverse=True,
            )
            for source_event in source_events[:deficit]:
                reconciled_events.append(
                    _synthesize_line_event(
                        source_event,
                        target_line=lines_by_order[second_order],
                        time_offset_seconds=median_delta_seconds,
                        fps=fps,
                    )
                )
        elif len(second_events) > len(first_events):
            deficit = len(second_events) - len(first_events)
            source_events = sorted(
                unmatched_second,
                key=lambda event: float(event.get("confidence") or 0.0),
                reverse=True,
            )
            for source_event in source_events[:deficit]:
                reconciled_events.append(
                    _synthesize_line_event(
                        source_event,
                        target_line=lines_by_order[first_order],
                        time_offset_seconds=-median_delta_seconds,
                        fps=fps,
                    )
                )

    return reconciled_events


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

    overlay_x = 18
    overlay_y = 18
    panel_width = 355
    panel_height = 128
    panel = frame.copy()
    cv2.rectangle(
        panel,
        (overlay_x, overlay_y),
        (overlay_x + panel_width, overlay_y + panel_height),
        (12, 28, 46),
        thickness=-1,
    )
    cv2.addWeighted(panel, 0.55, frame, 0.45, 0, frame)

    title_y = overlay_y + 24
    cv2.putText(frame, "Vehicle Analysis", (overlay_x + 12, title_y), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (38, 255, 120), 2)
    progress_text = f"Frame {processed_frames}/{total_frames or '-'}"
    cv2.putText(frame, progress_text, (overlay_x + 12, title_y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1)

    legend_x = overlay_x + 12
    legend_y = title_y + 46
    for index in range(len(line_segments)):
        line_color = line_colors[index % len(line_colors)]
        cv2.line(frame, (legend_x, legend_y), (legend_x + 18, legend_y), line_color, 3)
        cv2.putText(
            frame,
            f"L{index + 1}",
            (legend_x + 26, legend_y + 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            (255, 255, 255),
            1,
        )
        legend_x += 56

    counts_x = overlay_x + 12
    counts_y = legend_y + 26
    column_width = 106
    row_height = 18
    for index, code in enumerate(master_class_lookup):
        column_index = index // 4
        row_index = index % 4
        text_x = counts_x + (column_index * column_width)
        text_y = counts_y + (row_index * row_height)
        text = f"{code}: {counts_by_golongan.get(code, 0)}"
        cv2.putText(frame, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.47, (255, 255, 255), 1)


def _is_detection_candidate(
    vehicle_class: str,
    confidence: float,
    bbox: tuple[float, float, float, float],
    frame_width: int,
    frame_height: int,
    config: ProcessConfig,
) -> bool:
    return _detection_candidate_rejection_reason(
        vehicle_class=vehicle_class,
        confidence=confidence,
        bbox=bbox,
        frame_width=frame_width,
        frame_height=frame_height,
        config=config,
    ) is None


def _detection_candidate_rejection_reason(
    vehicle_class: str,
    confidence: float,
    bbox: tuple[float, float, float, float],
    frame_width: int,
    frame_height: int,
    config: ProcessConfig,
    min_confidence_override: Optional[float] = None,
) -> Optional[str]:
    x1, y1, x2, y2 = bbox
    box_width = max(x2 - x1, 1.0)
    box_height = max(y2 - y1, 1.0)
    safe_frame_area = max(float(frame_width * frame_height), 1.0)
    area_ratio = (box_width * box_height) / safe_frame_area
    width_ratio = box_width / max(float(frame_width), 1.0)
    height_ratio = box_height / max(float(frame_height), 1.0)
    minimum_confidence = (
        min_confidence_override
        if min_confidence_override is not None
        else _resolve_class_min_confidence(vehicle_class, config)
    )

    if confidence < minimum_confidence:
        return f"{vehicle_class}:confidence"

    if area_ratio < CLASS_MIN_AREA_RATIO.get(vehicle_class, 0.0001):
        return f"{vehicle_class}:area"

    if vehicle_class in LARGE_VEHICLE_MIN_LONG_SIDE_RATIO:
        long_side_ratio = max(width_ratio, height_ratio)
        if long_side_ratio < LARGE_VEHICLE_MIN_LONG_SIDE_RATIO[vehicle_class]:
            return f"{vehicle_class}:large_vehicle_size"

    return None


def _resolve_source_label(names, class_id: int) -> str:
    if isinstance(names, dict):
        return str(names.get(class_id, class_id))
    if isinstance(names, list) and 0 <= class_id < len(names):
        return str(names[class_id])
    return str(class_id)
