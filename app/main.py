from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import Base, engine
from app.routers.auth import router as auth_router
from app.routers.settings import router as settings_router
from app.routers.ui import router as ui_router
from app.routers.users import router as users_router
from app.routers.videos import router as videos_router
from app.services.bootstrap import ensure_bootstrap_data
from app.services.storage import ensure_storage_layout


settings = get_settings()
APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
WEB_DIR = APP_DIR / "web"
METRONIC_ASSETS_DIR = PROJECT_DIR / "templates" / "metronic" / "dist" / "assets"
app = FastAPI(title=settings.app_name)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    same_site="lax",
    https_only=False,
)


@app.on_event("startup")
def on_startup() -> None:
    ensure_storage_layout()
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        ensure_bootstrap_data(db)
    finally:
        db.close()


app.mount("/assets", StaticFiles(directory=str(WEB_DIR)), name="assets")
app.mount("/metronic/assets", StaticFiles(directory=str(METRONIC_ASSETS_DIR)), name="metronic_assets")
app.mount("/storage", StaticFiles(directory=str(settings.storage_root)), name="storage")
app.include_router(ui_router)
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(users_router)
app.include_router(videos_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
