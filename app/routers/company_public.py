"""Public company profile endpoint."""

import os
import uuid

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.models.company import Company
from app.schemas.company import CompanyResponse
from app.utils.limiter import limiter

router = APIRouter(prefix="/api/companies", tags=["Companies"])

settings = get_settings()

# Map each accepted MIME type to a safe, fixed extension. The stored extension
# is derived from the (validated) content type — never from the user-supplied
# filename — so a spoofed name like "x.svg"/"x.html" can't be saved and later
# served as executable content (stored XSS).
EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
ALLOWED_IMAGE_TYPES = set(EXT_BY_TYPE)
MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


@router.get("/by-slug/{slug}", response_model=CompanyResponse, summary="Slug orqali kompaniya profili")
async def get_company_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    """Kompaniyani slug yoki custom_domain orqali topish. Auth talab qilinmaydi. Includes owner's payment credentials."""
    result = await db.execute(
        select(Company)
        .options(selectinload(Company.owner))
        .where(
            (Company.slug == slug) | (Company.custom_domain == slug)
        )
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")

    # Create response with owner's payment credentials
    response_dict = CompanyResponse.model_validate(company).model_dump()
    if company.owner:
        response_dict["click_merchant_id"] = company.owner.click_merchant_id
        response_dict["payme_merchant_id"] = company.owner.payme_merchant_id
    return response_dict


@router.get("/{slug}/customization", summary="Website customization by slug")
async def get_website_customization_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """Get website customization for a company by slug — no auth required."""
    result = await db.execute(
        select(Company).where(
            (Company.slug == slug) | (Company.custom_domain == slug)
        )
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")

    customization = {}
    if company.website_customization:
        import json
        try:
            customization = json.loads(company.website_customization)
        except:
            pass

    return {"customization": customization}


@router.get("/{company_id}", response_model=CompanyResponse, summary="Kompaniya public profili")
async def get_company_public(
    company_id: int,
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    """Public company info — no auth required. Includes owner's payment credentials."""
    result = await db.execute(
        select(Company)
        .options(selectinload(Company.owner))
        .where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")

    # Create response with owner's payment credentials
    response_dict = CompanyResponse.model_validate(company).model_dump()
    if company.owner:
        response_dict["click_merchant_id"] = company.owner.click_merchant_id
        response_dict["payme_merchant_id"] = company.owner.payme_merchant_id
    return response_dict


@router.post("/upload-logo", summary="Logotip rasmini yuklash (public)")
@limiter.limit("10/minute")
async def upload_logo(
    request: Request,
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
    ext = EXT_BY_TYPE[content_type]
    filename = f"logo_{uuid.uuid4()}{ext}"
    filepath = os.path.join(settings.upload_dir, filename)

    async with aiofiles.open(filepath, "wb") as f:
        await f.write(content)

    api_base = settings.savdogar_public_url.rstrip("/")
    return {"url": f"{api_base}/uploads/{filename}"}
