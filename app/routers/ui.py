from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user_optional
from app.models import User


TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

router = APIRouter(include_in_schema=False)


def _require_user(user: Optional[User]) -> Optional[RedirectResponse]:
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return None


def _user_initials(user: Optional[User]) -> str:
    if not user:
        return "NC"
    full_name = (user.full_name or "").strip()
    parts = [part for part in full_name.split() if part]
    if parts:
        return "".join(part[0].upper() for part in parts[:2])
    username = (user.username or "NC").strip()
    return username[:2].upper() or "NC"


def _render_page(
    request: Request,
    template_name: str,
    user: Optional[User],
    *,
    page_title: str,
    page_subtitle: str = "",
    active_nav: str = "",
):
    return TEMPLATES.TemplateResponse(
        template_name,
        {
            "request": request,
            "current_user": user,
            "current_user_initials": _user_initials(user),
            "page_title": page_title,
            "page_subtitle": page_subtitle,
            "active_nav": active_nav,
        },
    )


@router.get("/")
def index(user: Optional[User] = Depends(get_current_user_optional)):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url="/videos", status_code=302)


@router.get("/login")
def login_page(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    if user:
        return RedirectResponse(url="/videos", status_code=302)
    return _render_page(request, "pages/login.html", user, page_title="Sign In")


@router.get("/users")
def users_page(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    redirect = _require_user(user)
    if redirect:
        return redirect
    if not user.is_admin:
        return RedirectResponse(url="/videos", status_code=302)
    return _render_page(request, "pages/users.html", user, page_title="Users", active_nav="users")


@router.get("/settings")
def settings_page(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    redirect = _require_user(user)
    if redirect:
        return redirect
    if not user.is_admin:
        return RedirectResponse(url="/videos", status_code=302)
    return RedirectResponse(url="/settings/detection", status_code=302)


@router.get("/settings/detection")
def detection_settings_page(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    redirect = _require_user(user)
    if redirect:
        return redirect
    if not user.is_admin:
        return RedirectResponse(url="/videos", status_code=302)
    return _render_page(
        request,
        "pages/settings.html",
        user,
        page_title="Detection Settings",
        page_subtitle="Manage confidence thresholds used during vehicle detection and counting.",
        active_nav="settings-detection",
    )


@router.get("/settings/master-classes")
def master_classes_page(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    redirect = _require_user(user)
    if redirect:
        return redirect
    if not user.is_admin:
        return RedirectResponse(url="/videos", status_code=302)
    return _render_page(
        request,
        "pages/master_classes.html",
        user,
        page_title="Master Vehicle Classes",
        page_subtitle="Manage the official vehicle class codes, labels, and descriptions used in analysis results.",
        active_nav="settings-master-classes",
    )


@router.get("/settings/gpu-audit")
def gpu_audit_page(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    redirect = _require_user(user)
    if redirect:
        return redirect
    if not user.is_admin:
        return RedirectResponse(url="/videos", status_code=302)
    return _render_page(
        request,
        "pages/gpu_audit.html",
        user,
        page_title="GPU Audit",
        page_subtitle="Audit whether the current server is really using NVIDIA CUDA, Apple MPS, or falling back to CPU.",
        active_nav="settings-gpu-audit",
    )


@router.get("/videos")
def videos_page(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    redirect = _require_user(user)
    if redirect:
        return redirect
    return _render_page(request, "pages/videos.html", user, page_title="Videos", active_nav="videos")


@router.get("/analysis")
def analysis_page(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    redirect = _require_user(user)
    if redirect:
        return redirect
    return _render_page(
        request,
        "pages/analysis.html",
        user,
        page_title="Video Analysis",
        page_subtitle="Select an uploaded video, run analysis, and monitor detection results as they are processed.",
        active_nav="analysis",
    )


@router.get("/count-lines")
def count_lines_page(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    redirect = _require_user(user)
    if redirect:
        return redirect
    return _render_page(
        request,
        "pages/count_lines.html",
        user,
        page_title="Count Lines",
        page_subtitle="Select a video and draw up to two counting lines to use during analysis.",
        active_nav="count-lines",
    )
