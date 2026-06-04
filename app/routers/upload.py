"""File upload router — images and media."""

import os
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.middleware.role_guard import role_required
from app.models.user import UserRole
import aiofiles

router = APIRouter(prefix="/api", tags=["Upload"])
settings = get_settings()

_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_MAX_BYTES = settings.max_upload_size_mb * 1024 * 1024


class UploadResponse(BaseModel):
    """Upload response."""
    url: str


def _validate_image(content: bytes, filename: str) -> str:
    """Validate image file and return safe extension."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Faqat rasm fayllari qabul qilinadi: {', '.join(_ALLOWED_EXTENSIONS)}",
        )
    if len(content) > _MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Fayl hajmi {settings.max_upload_size_mb}MB dan oshmasligi kerak",
        )
    # Validate magic bytes
    magic_ok = (
        content[:3] == b"\xff\xd8\xff"  # JPEG
        or content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG
        or content[:6] in (b"GIF87a", b"GIF89a")  # GIF
        or (content[:4] == b"RIFF" and content[8:12] == b"WEBP")  # WebP
    )
    if not magic_ok:
        raise HTTPException(status_code=400, detail="Yaroqsiz rasm formati")
    return ext


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Rasm yuklash",
)
async def upload_image(file: UploadFile = File(...)) -> UploadResponse:
    """Upload an image and return its URL."""
    content = await file.read()
    ext = _validate_image(content, file.filename or "unknown.jpg")

    os.makedirs(settings.upload_dir, exist_ok=True)
    filename = f"{uuid.uuid4()}{ext}"
    filepath = os.path.join(settings.upload_dir, filename)

    async with aiofiles.open(filepath, "wb") as f:
        await f.write(content)

    image_url = f"/uploads/{filename}"
    return UploadResponse(url=image_url)
