"""App downloads: the phone and watch APKs, when this server is configured with them
(``GLUCORAG_PHONE_APK`` / ``GLUCORAG_WATCH_APK``). Public: the files carry no data, and the
help pages link to them before a phone is signed in."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter()

RELEASES_URL = "https://github.com/archdex-art/glucorag/releases"
APK_MEDIA_TYPE = "application/vnd.android.package-archive"
App = Literal["phone", "watch"]


class Downloads(BaseModel):
    phone_apk: str | None
    watch_apk: str | None
    releases_url: str


def _apk(request: Request, app: App) -> Path | None:
    path: Path | None = getattr(request.app.state, f"{app}_apk_path", None)
    return path if path is not None and path.is_file() else None


@router.get("/downloads")
def downloads(request: Request) -> Downloads:
    """Where to get the apps: this server's files when configured, else the releases page."""
    return Downloads(
        phone_apk="/download/phone.apk" if _apk(request, "phone") else None,
        watch_apk="/download/watch.apk" if _apk(request, "watch") else None,
        releases_url=RELEASES_URL,
    )


@router.get("/download/{app}.apk", response_class=FileResponse)
def download(app: App, request: Request) -> FileResponse:
    path = _apk(request, app)
    if path is None:
        raise HTTPException(404, f"No {app} app file on this server.")
    return FileResponse(
        path, media_type=APK_MEDIA_TYPE, filename=f"glucorag-{app}.apk",
        headers={"Cache-Control": "no-cache"},
    )
