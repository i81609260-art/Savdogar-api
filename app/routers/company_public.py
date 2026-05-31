"""Public company profile endpoint."""

import os
import uuid

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.company import Company
from app.schemas.company import CompanyResponse

router = APIRouter(prefix="/api/companies", tags=["Companies"])

settings = get_settings()

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}
MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


@router.get("/{company_id}", response_model=CompanyResponse, summary="Kompaniya public profili")
async def get_company_public(
    company_id: int,
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    """Public company info — no auth required."""
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")
    return CompanyResponse.model_validate(company)


@router.post("/upload-logo", summary="Logotip rasmini yuklash (public)")
async def upload_logo(
    file: UploadFile = File(...),
) -> dict:
    """Upload a company logo image and return its URL. No auth required (used during registration)."""
    content_type = file.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Faqat rasm fayllari qabul qilinadi (JPEG, PNG, WEBP, GIF)",
        )

    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Fayl hajmi 5 MB dan oshmasligi kerak")

    os.makedirs(settings.upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    filename = f"logo_{uuid.uuid4()}{ext}"
    filepath = os.path.join(settings.upload_dir, filename)

    async with aiofiles.open(filepath, "wb") as f:
        await f.write(content)

    api_base = settings.savdogar_public_url.rstrip("/")
    return {"url": f"{api_base}/uploads/{filename}"}
