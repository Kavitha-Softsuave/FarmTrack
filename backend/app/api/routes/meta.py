import logging
from typing import get_args

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_db
from app.api.schemas import HealthOut, MetaOut
from app.domain.types import Lang
from app.services.container import Container

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meta"])

_PROVIDER_SETTINGS = ("llm_provider", "tts_provider", "embeddings_provider", "vector_store", "crop_id_provider",
                      "disease_provider", "zoho_provider", "iot_provider", "weather_provider", "push_provider")


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)):
    """Liveness plus a database ping. 503 with db=false when the database cannot be reached."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("health check: database unreachable")
        return JSONResponse({"status": "degraded", "db": False}, status_code=503)
    return HealthOut(status="ok", db=True)


@router.get("/v1/meta", response_model=MetaOut)
def meta(container: Container = Depends(get_container)) -> MetaOut:
    settings = container.settings
    return MetaOut(
        app_version=settings.app_version, env=settings.env,
        demo_clock=container.clock.now() if container.clock.is_fixed else None,
        supported_languages=list(get_args(Lang)), supported_crops=container.rules.supported_crops(),
        providers={name.removesuffix("_provider"): getattr(settings, name) for name in _PROVIDER_SETTINGS})
