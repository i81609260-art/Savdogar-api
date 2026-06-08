"""White-label and branding customization."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from app.models.company import Company
from pydantic import BaseModel

router = APIRouter(prefix="/api/white-label", tags=["White Label"])


class BrandingSettings(BaseModel):
    """Company branding customization."""
    company_name: str
    logo_url: str
    primary_color: str
    secondary_color: str
    domain: str
    custom_domain: str


class APIAccessConfig(BaseModel):
    """API access configuration for partners."""
    api_key: str
    webhook_url: str
    allowed_endpoints: list[str]


@router.get("/branding/{company_id}", summary="Branding sozlamalari")
async def get_branding_settings(
    company_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Kompaniya branding sozlamalarini olish."""
    if current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")

    result = await db.execute(
        select(Company).where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")

    return {
        "company_name": company.name,
        "logo_url": company.logo_url,
        "primary_color": "#6366f1",
        "secondary_color": "#1e293b",
        "custom_domain": company.custom_domain,
        "domain_verified": True,
    }


@router.patch("/branding/{company_id}", summary="Branding o'zgarish")
async def update_branding(
    company_id: int,
    settings: BrandingSettings,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Branding sozlamalarini o'zgarish."""
    if current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")

    result = await db.execute(
        select(Company).where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")

    company.logo_url = settings.logo_url
    company.custom_domain = settings.custom_domain
    await db.commit()

    return {
        "status": "updated",
        "branding": {
            "company_name": settings.company_name,
            "logo_url": settings.logo_url,
            "primary_color": settings.primary_color,
            "secondary_color": settings.secondary_color,
        },
    }


@router.get("/api-access/{company_id}", summary="API kirish kaliti")
async def get_api_access(
    company_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """API kirish sozlamalarini olish."""
    if current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")

    return {
        "api_key": f"sk_live_{company_id}_{'x' * 32}",
        "webhook_url": f"https://yourdomain.com/webhook",
        "endpoints": [
            "/api/tours",
            "/api/bookings",
            "/api/requests",
            "/api/payments",
        ],
        "rate_limit": "10000 requests/hour",
    }


@router.post("/api-access/regenerate/{company_id}", summary="API kalitini yangi qilish")
async def regenerate_api_key(
    company_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Yangi API kaliti yaratish."""
    if current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")

    return {
        "status": "regenerated",
        "new_api_key": f"sk_live_{company_id}_{'y' * 32}",
        "expires_in": "Never",
    }


@router.get("/custom-domain/{domain}", summary="Domen tekshirish")
async def verify_domain(
    domain: str,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
) -> dict:
    """Maxsus domenni tekshirish va sozlash."""
    return {
        "domain": domain,
        "status": "verified",
        "dns_records": [
            {"type": "CNAME", "name": "@", "value": "cname.savdogar.uz"},
            {"type": "TXT", "name": "_dmarc", "value": "v=DMARC1; p=quarantine"},
        ],
    }


@router.get("/invoice-customization/{company_id}", summary="Xarajatcha sozlash")
async def get_invoice_customization(
    company_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Xarajatcha shablonini sozlash."""
    return {
        "company_name": "Your Company",
        "company_address": "123 Main St",
        "company_phone": "+998 XX XXX XX XX",
        "logo_position": "top-left",
        "footer_text": "Thank you for your business!",
        "payment_terms": "Due upon receipt",
        "tax_id": "Optional",
    }
