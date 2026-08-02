"""File upload router — images and media."""

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from app.utils.images import save_image
from app.utils.limiter import limiter

router = APIRouter(prefix="/api", tags=["Upload"])
settings = get_settings()


class UploadResponse(BaseModel):
    """Upload response."""
    url: str


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Rasm yuklash",
)
@limiter.limit("30/minute")
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    # Ilgari bu endpoint ochiq edi: istalgan odam serverga cheksiz fayl
    # yuklab, diskni to'ldirishi yoki tekin fayl hosting sifatida
    # ishlatishi mumkin edi.
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
) -> UploadResponse:
    """Upload an image and return its URL."""
    url = await save_image(
        file,
        settings.persistent_upload_dir,
        settings.max_upload_size_mb * 1024 * 1024,
    )
    return UploadResponse(url=url)
