from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    get_current_user,
    get_current_user_optional,
    login_user,
    logout_user,
    normalize_username,
    verify_password,
)
from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, SessionRead, UserRead


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=SessionRead)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> SessionRead:
    username = normalize_username(payload.username)
    user = db.scalar(select(User).where(User.username == username))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")

    login_user(request, user)
    return SessionRead(authenticated=True, user=UserRead.model_validate(user))


@router.post("/logout", response_model=SessionRead)
def logout(request: Request) -> SessionRead:
    logout_user(request)
    return SessionRead(authenticated=False, user=None)


@router.get("/me", response_model=SessionRead)
def me(user: Optional[User] = Depends(get_current_user_optional)) -> SessionRead:
    if not user:
        return SessionRead(authenticated=False, user=None)
    return SessionRead(authenticated=True, user=UserRead.model_validate(user))


@router.get("/required", response_model=UserRead)
def me_required(user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(user)
