import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.api.deps import get_container
from app.api.schemas import ErrorOut, VoiceCatalogueOut
from app.domain.types import Lang
from app.security.errors import ApiError
from app.security.paths import UnsafePathError, safe_join
from app.services.container import Container
from app.voice.catalogue import load_catalogue
from app.voice.package import build_package

router = APIRouter(tags=["voice"])

AUDIO_NAME_RE = re.compile(r"^[a-f0-9]{64}\.mp3$")          # content-addressed synthesised audio (storage_dir/audio)
PROMPT_NAME_RE = re.compile(r"^[a-z0-9_]{1,80}\.mp3$")      # fixed prompt audio (voice_dir/audio/<lang>/<id>.mp3)
IMMUTABLE = "public, max-age=31536000, immutable"
PROMPT_CACHE = "public, max-age=86400"                       # file names are not hashes: revalidate daily (ETag)


@router.get("/v1/voice/catalogue", response_model=VoiceCatalogueOut)
def voice_catalogue(request: Request, response: Response, lang: Lang = "hi", container: Container = Depends(get_container)):
    """All fixed voice prompts for a language (voice/prompts.json) with audio refs when generated. Public (no auth).

    The version doubles as an ETag, so an app that already has this version gets 304 and downloads nothing."""
    catalogue = load_catalogue(container.settings, lang, container.audio)
    etag = f'"{catalogue.version}-{lang}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "no-cache"          # revalidate every time; cheap thanks to the ETag
    return catalogue


@router.get("/v1/voice/package", response_class=Response,
            responses={200: {"content": {"application/zip": {}}}, 304: {"description": "The app already has this version"},
                       404: {"model": ErrorOut}})
def voice_package(request: Request, lang: Lang = "hi", container: Container = Depends(get_container)) -> Response:
    """The whole fixed-prompt audio of one language as one zip (manifest.json + <prompt id>.mp3), for a single download.

    Same version as GET /v1/voice/catalogue (also the ETag: 304 when the app is current). 404 `voice_package_empty` while no
    audio has been generated yet (the app then uses the phone's own voice). Public, like the catalogue."""
    version = load_catalogue(container.settings, lang).version
    etag = f'"{version}-{lang}-package"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})
    path = build_package(container.settings, lang)
    if path is None:
        raise ApiError(404, "voice_package_empty", "No prompt audio has been generated yet.")
    return FileResponse(path, media_type="application/zip", filename=f"voice-{lang}.zip", background=BackgroundTask(os.unlink, path),
                        headers={"ETag": etag, "Cache-Control": "no-cache"})


@router.get("/audio/{name}", response_class=Response, responses={200: {"content": {"audio/mpeg": {}}}, 404: {"model": ErrorOut}})
def get_audio(name: str, container: Container = Depends(get_container)) -> Response:
    """Serve cached audio by content-hash name (e.g. ab12...mp3). Public, immutable, cacheable."""
    path = _existing(container.settings.storage_dir / "audio", name) if AUDIO_NAME_RE.fullmatch(name) else None
    if path is None:
        raise ApiError(404, "audio_not_found", "That audio file was not found.")
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": IMMUTABLE, "ETag": f'"{name.removesuffix(".mp3")}"'})


@router.get("/audio-prompts/{lang}/{name}", response_class=Response,
            responses={200: {"content": {"audio/mpeg": {}}}, 404: {"model": ErrorOut}})
def get_prompt_audio(lang: Lang, name: str, container: Container = Depends(get_container)) -> Response:
    """Serve the generated audio of a fixed voice prompt (the urls in GET /v1/voice/catalogue). Public."""
    path = _existing(container.settings.voice_dir / "audio" / lang, name) if PROMPT_NAME_RE.fullmatch(name) else None
    if path is None:
        raise ApiError(404, "audio_not_found", "That audio file was not found.")
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": PROMPT_CACHE})


def _existing(root: Path, name: str) -> Path | None:
    try:
        path = safe_join(root, name)
    except UnsafePathError:
        return None
    return path if path.is_file() else None
