from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from importlib import metadata

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import get_settings
from app.constants import DEFAULT_MASTER_CLASSES
from app.database import get_db
from app.models import AnalysisJob, User, VideoUpload
from app.schemas import (
    DetectionSettingsRead,
    DetectionSettingsUpdate,
    GpuAuditChecklistItemRead,
    GpuAuditCommandRead,
    GpuAuditConfigRead,
    GpuAuditRead,
    GpuAuditRecentJobRead,
    GpuAuditRuntimeRead,
    MasterClassRead,
    MasterClassUpdate,
)
from app.services.detection_settings import get_or_create_detection_settings
from app.services.master_classes import get_or_create_master_classes


router = APIRouter(prefix="/api/settings", tags=["settings"])


def _package_version(package_name: str) -> str | None:
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return None


def _read_nvidia_smi() -> tuple[bool, str | None]:
    command = shutil.which("nvidia-smi")
    if not command:
        return False, None

    try:
        result = subprocess.run(
            [
                command,
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False, None

    if result.returncode != 0:
        return False, None

    summary = " | ".join(line.strip() for line in result.stdout.splitlines() if line.strip())
    return True, summary or None


def _build_gpu_runtime_snapshot() -> GpuAuditRuntimeRead:
    torch_version = _package_version("torch")
    ultralytics_version = _package_version("ultralytics")
    nvidia_smi_available, nvidia_smi_summary = _read_nvidia_smi()
    ffmpeg_available = shutil.which("ffmpeg") is not None

    cuda_built_version = None
    cuda_available = False
    cuda_device_count = 0
    cuda_devices: list[str] = []
    mps_built = False
    mps_available = False
    torch_runtime_error = None

    try:
        import torch

        cuda_built_version = torch.version.cuda
        cuda_available = bool(torch.cuda.is_available())
        if cuda_available:
            cuda_device_count = int(torch.cuda.device_count())
            cuda_devices = [str(torch.cuda.get_device_name(index)) for index in range(cuda_device_count)]
        mps_backend = getattr(torch.backends, "mps", None)
        if mps_backend is not None:
            mps_built = bool(mps_backend.is_built())
            mps_available = bool(mps_backend.is_available())
    except Exception as exc:  # pragma: no cover - defensive runtime audit
        torch_runtime_error = str(exc)

    return GpuAuditRuntimeRead(
        platform_system=platform.system(),
        platform_release=platform.release(),
        platform_version=platform.version(),
        machine=platform.machine(),
        processor=platform.processor(),
        python_version=sys.version.split()[0],
        torch_version=torch_version,
        ultralytics_version=ultralytics_version,
        cuda_built_version=cuda_built_version,
        cuda_available=cuda_available,
        cuda_device_count=cuda_device_count,
        cuda_devices=cuda_devices,
        mps_built=mps_built,
        mps_available=mps_available,
        nvidia_smi_available=nvidia_smi_available,
        nvidia_smi_summary=nvidia_smi_summary,
        ffmpeg_available=ffmpeg_available,
        torch_runtime_error=torch_runtime_error,
    )


def _build_gpu_checklist(
    runtime: GpuAuditRuntimeRead,
    recent_jobs: list[GpuAuditRecentJobRead],
) -> tuple[str, str | None, list[GpuAuditChecklistItemRead]]:
    checklist: list[GpuAuditChecklistItemRead] = []
    host_note: str | None = None

    if runtime.platform_system != "Windows":
        host_note = (
            "This page is mainly intended for Windows + NVIDIA CUDA servers. "
            f"The current host is {runtime.platform_system}."
        )

    checklist.append(
        GpuAuditChecklistItemRead(
            key="torch-installed",
            title="PyTorch Runtime",
            status="pass" if runtime.torch_version else "fail",
            summary=f"PyTorch version: {runtime.torch_version or 'not installed'}",
            detail=runtime.torch_runtime_error or (
                f"CUDA build: {runtime.cuda_built_version or 'none'} | "
                f"MPS available: {'yes' if runtime.mps_available else 'no'}"
            ),
        )
    )

    checklist.append(
        GpuAuditChecklistItemRead(
            key="nvidia-smi",
            title="NVIDIA Driver / nvidia-smi",
            status="pass" if runtime.nvidia_smi_available else ("fail" if runtime.platform_system == "Windows" else "warning"),
            summary="nvidia-smi detected" if runtime.nvidia_smi_available else "nvidia-smi not available",
            detail=runtime.nvidia_smi_summary or "Install or repair the NVIDIA driver if this is a CUDA server.",
        )
    )

    checklist.append(
        GpuAuditChecklistItemRead(
            key="torch-cuda",
            title="PyTorch CUDA Access",
            status="pass" if runtime.cuda_available else ("warning" if runtime.mps_available else "fail"),
            summary=(
                f"CUDA available with {runtime.cuda_device_count} device(s)"
                if runtime.cuda_available
                else ("Using Apple MPS instead of CUDA" if runtime.mps_available else "CUDA not available to PyTorch")
            ),
            detail=", ".join(runtime.cuda_devices) or "If this is a Windows RTX server, PyTorch is likely falling back to CPU.",
        )
    )

    settings = get_settings()
    expected_device_ok = settings.default_inference_device in {"auto", "cuda"}
    checklist.append(
        GpuAuditChecklistItemRead(
            key="default-device",
            title="Default Inference Device Setting",
            status="pass" if expected_device_ok else "warning",
            summary=f"DEFAULT_INFERENCE_DEVICE={settings.default_inference_device}",
            detail="Recommended values for Windows RTX servers: auto or cuda.",
        )
    )

    latest_device = (recent_jobs[0].device or "").lower() if recent_jobs else ""
    latest_processing_fps = recent_jobs[0].processing_fps if recent_jobs else None
    recent_job_status = "warning"
    recent_job_summary = "No recent analysis job found"
    recent_job_detail = "Run one analysis job on the Windows server, then reload this page."

    if recent_jobs:
        if latest_device == "cuda":
            recent_job_status = "pass"
            recent_job_summary = f"Latest job used CUDA ({latest_processing_fps or 0:.2f} FPS)"
            recent_job_detail = "This is the strongest indicator that the server is really using the NVIDIA GPU."
        elif latest_device == "mps":
            recent_job_status = "warning"
            recent_job_summary = f"Latest job used MPS ({latest_processing_fps or 0:.2f} FPS)"
            recent_job_detail = "This is expected on Apple Silicon, but not on a Windows RTX server."
        elif latest_device:
            recent_job_status = "fail"
            recent_job_summary = f"Latest job used {latest_device.upper()}"
            recent_job_detail = "If this is a Windows RTX server, the analysis likely fell back to CPU."

    checklist.append(
        GpuAuditChecklistItemRead(
            key="recent-job-device",
            title="Latest Analysis Device",
            status=recent_job_status,
            summary=recent_job_summary,
            detail=recent_job_detail,
        )
    )

    throughput_status = "warning"
    throughput_summary = "No throughput sample available"
    throughput_detail = "This item is based on the latest completed or processing job."
    if latest_processing_fps is not None:
        if latest_processing_fps >= 8:
            throughput_status = "pass"
        elif latest_processing_fps < 3:
            throughput_status = "fail"
        throughput_summary = f"Latest processing FPS: {latest_processing_fps:.2f}"
        throughput_detail = (
            "For a Windows RTX server, a sustained value below 3 FPS usually indicates CPU fallback, "
            "an overly heavy model, or a very high-resolution workload."
        )

    checklist.append(
        GpuAuditChecklistItemRead(
            key="recent-job-throughput",
            title="Latest Analysis Throughput",
            status=throughput_status,
            summary=throughput_summary,
            detail=throughput_detail,
        )
    )

    status_rank = {"fail": 3, "warning": 2, "pass": 1}
    overall_status = "pass"
    worst_rank = 1
    for item in checklist:
        rank = status_rank.get(item.status, 1)
        if rank > worst_rank:
            worst_rank = rank
            overall_status = item.status

    return overall_status, host_note, checklist


def _build_recent_job_rows(db: Session) -> list[GpuAuditRecentJobRead]:
    rows = db.execute(
        select(AnalysisJob, VideoUpload.original_filename)
        .join(VideoUpload, VideoUpload.id == AnalysisJob.video_upload_id)
        .order_by(desc(AnalysisJob.updated_at))
        .limit(5)
    ).all()

    recent_jobs: list[GpuAuditRecentJobRead] = []
    for analysis_job, original_filename in rows:
        summary_json = analysis_job.summary_json or {}
        performance = summary_json.get("performance") or {}
        recent_jobs.append(
            GpuAuditRecentJobRead(
                video_name=original_filename,
                status=analysis_job.status,
                model_name=analysis_job.model_name,
                device=(
                    performance.get("inference_device")
                    or performance.get("device")
                    or (analysis_job.config_json or {}).get("inference_device")
                ),
                processing_fps=performance.get("processing_fps"),
                effective_analysis_fps=performance.get("effective_analysis_fps"),
                created_at=analysis_job.created_at,
                updated_at=analysis_job.updated_at,
            )
        )

    return recent_jobs


def _build_gpu_commands(runtime: GpuAuditRuntimeRead) -> list[GpuAuditCommandRead]:
    if runtime.platform_system == "Windows":
        python_bin = r".venv\Scripts\python"
        return [
            GpuAuditCommandRead(label="Check NVIDIA driver", command="nvidia-smi"),
            GpuAuditCommandRead(
                label="Check PyTorch CUDA",
                command=(
                    f'{python_bin} -c "import torch; '
                    "print({"
                    "'torch': torch.__version__, "
                    "'cuda_build': torch.version.cuda, "
                    "'cuda_available': torch.cuda.is_available(), "
                    "'device_count': torch.cuda.device_count(), "
                    "'device_names': [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]"
                    "})\""
                ),
            ),
            GpuAuditCommandRead(
                label="Watch GPU usage live",
                command="nvidia-smi -l 2",
            ),
        ]

    return [
        GpuAuditCommandRead(label="Check host runtime", command="python3 -c \"import platform, torch; print(platform.platform()); print('cuda', torch.cuda.is_available()); print('mps', getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available())\""),
        GpuAuditCommandRead(label="Check ffmpeg", command="which ffmpeg"),
    ]


@router.get("/detection", response_model=DetectionSettingsRead)
def get_detection_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> DetectionSettingsRead:
    settings_row = get_or_create_detection_settings(db)
    return DetectionSettingsRead.model_validate(settings_row)


@router.put("/detection", response_model=DetectionSettingsRead)
def update_detection_settings(
    payload: DetectionSettingsUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DetectionSettingsRead:
    settings_row = get_or_create_detection_settings(db)
    settings_row.global_confidence = payload.global_confidence
    settings_row.motorcycle_min_confidence = payload.motorcycle_min_confidence
    settings_row.vehicle_min_confidence = payload.vehicle_min_confidence
    db.commit()
    db.refresh(settings_row)
    return DetectionSettingsRead.model_validate(settings_row)


@router.get("/master-classes", response_model=list[MasterClassRead])
def get_master_classes(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[MasterClassRead]:
    rows = get_or_create_master_classes(db)
    return [MasterClassRead.model_validate(row) for row in rows]


@router.put("/master-classes", response_model=list[MasterClassRead])
def update_master_classes(
    payload: MasterClassUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[MasterClassRead]:
    rows = get_or_create_master_classes(db)
    row_map = {row.code: row for row in rows}
    valid_codes = set(DEFAULT_MASTER_CLASSES)
    received_codes: set[str] = set()

    for item in payload.items:
        normalized_code = (item.code or "").strip()
        if normalized_code not in valid_codes:
            raise HTTPException(status_code=400, detail=f"Unknown master class code: {normalized_code}")
        if normalized_code in received_codes:
            raise HTTPException(status_code=400, detail=f"Duplicate master class code: {normalized_code}")
        received_codes.add(normalized_code)

        row = row_map.get(normalized_code)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Master class not found: {normalized_code}")

        row.label = item.label.strip()
        row.description = (item.description or "").strip() or None

    db.commit()
    refreshed_rows = get_or_create_master_classes(db)
    return [MasterClassRead.model_validate(row) for row in refreshed_rows]


@router.get("/gpu-audit", response_model=GpuAuditRead)
def get_gpu_audit(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> GpuAuditRead:
    settings = get_settings()
    runtime = _build_gpu_runtime_snapshot()
    recent_jobs = _build_recent_job_rows(db)
    overall_status, host_note, checklist = _build_gpu_checklist(runtime, recent_jobs)

    return GpuAuditRead(
        overall_status=overall_status,
        host_note=host_note,
        runtime=runtime,
        config=GpuAuditConfigRead(
            default_inference_device=settings.default_inference_device,
            default_model_path=settings.default_model_path,
            target_analysis_fps=settings.default_target_analysis_fps,
            preview_fps=settings.default_preview_fps,
            inference_imgsz=settings.default_inference_imgsz,
            working_max_width=settings.default_working_max_width,
            save_annotated_video=settings.save_annotated_video,
        ),
        checklist=checklist,
        recent_jobs=recent_jobs,
        commands=_build_gpu_commands(runtime),
    )
