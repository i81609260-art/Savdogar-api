"""Company settings — Company info & website customization."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.company import Company
from app.models.user import User
from app.schemas.company import CompanyInfoUpdate, WebsiteCustomizationRequest, WebsiteCustomizationResponse

router = APIRouter(prefix="/api/admin/company", tags=["Company Settings"])
logger = logging.getLogger(__name__)


@router.get("/info", summary="Get company information")
async def get_company_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get company information for AI context."""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Company yo'q")

    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company topilmadi")

    return {
        "company_info": company.company_info or "",
        "name": company.name,
        "description": company.description,
    }


@router.patch("/info", summary="Update company information")
async def update_company_info(
    data: CompanyInfoUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update company information for AI context. Supports template selection with colors."""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Company yo'q")

    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company topilmadi")

    company.company_info = data.company_info
    await db.merge(company)
    await db.commit()

    return {"success": True, "message": "Kompaniya ma'lumoti saqlandi", "company_id": current_user.company_id}


async def _gemini_css(instruction: str) -> dict:
    """Buyruqni Gemini'ga yuborib CSS oladi. Kalit serverda qoladi.

    Ilgari bu chaqiruv brauzerdan `NEXT_PUBLIC_GEMINI_API_KEY` bilan
    bajarilardi — ya'ni kalit JS bundle ichida hammaga ochiq edi va istalgan
    tashrifchi uni olib, hisobingiz hisobidan foydalanishi mumkin edi.
    """
    import httpx

    settings = get_settings()
    if not settings.gemini_api_key:
        return {}

    prompt = (
        "Siz veb-sayt dizayni uchun CSS generatorsiz. Foydalanuvchi buyrug'i: "
        f'"{instruction}". Faqat CSS qoidalarini qaytaring, boshqa matnsiz.'
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                url,
                params={"key": settings.gemini_api_key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
        if resp.status_code != 200:
            logger.warning("Gemini CSS xatosi %s", resp.status_code)
            return {}
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as exc:  # noqa: BLE001 — AI yo'q bo'lsa ham ishlashi kerak
        logger.warning("Gemini CSS olinmadi: %s", exc)
        return {}

    css = text.strip().removeprefix("```css").removeprefix("```").removesuffix("```")
    css = css.strip()
    return {"css": css} if css else {}


@router.post("/website/customize", response_model=WebsiteCustomizationResponse, summary="AI website customization")
async def customize_website(
    data: WebsiteCustomizationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    AI-powered website customization.

    User instruction: "O'zgarish matni rang qizil qil"
    ML processes instruction and generates CSS/config changes
    Changes only apply to this company's website
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Company yo'q")

    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company topilmadi")

    instruction = data.instruction.lower()

    changes = {}

    if "rang" in instruction or "color" in instruction or "oq" in instruction or "qora" in instruction:
        if "qizil" in instruction or "red" in instruction:
            changes["primary_color"] = "#ff0000"
            changes["css"] = ".primary { color: #ff0000; }"
        elif "ko'k" in instruction or "blue" in instruction:
            changes["primary_color"] = "#0000ff"
            changes["css"] = ".primary { color: #0000ff; }"
        elif "yashil" in instruction or "green" in instruction:
            changes["primary_color"] = "#00aa00"
            changes["css"] = ".primary { color: #00aa00; }"
        elif "oq" in instruction or "white" in instruction:
            changes["primary_color"] = "#ffffff"
            changes["css"] = ".primary { color: #ffffff; }"

    if "shrift" in instruction or "font" in instruction or "kattalash" in instruction or "kichiklash" in instruction:
        if "kattalash" in instruction or "bigger" in instruction or "large" in instruction:
            changes["font_size"] = "18px"
            changes["css"] = ".body { font-size: 18px; }"
        elif "kichiklash" in instruction or "smaller" in instruction or "small" in instruction:
            changes["font_size"] = "12px"
            changes["css"] = ".body { font-size: 12px; }"

    if "fon" in instruction or "background" in instruction:
        if "qora" in instruction or "dark" in instruction:
            changes["background"] = "#1a1a1a"
            changes["css"] = "body { background: #1a1a1a; }"
        elif "oq" in instruction or "light" in instruction:
            changes["background"] = "#ffffff"
            changes["css"] = "body { background: #ffffff; }"

    if "tugma" in instruction or "button" in instruction:
        if "qizil" in instruction or "red" in instruction:
            changes["button_color"] = "#ff0000"
            changes["css"] = "button { background-color: #ff0000; }"

    if not changes:
        # Kalit so'zlar mos kelmadi — Gemini'dan so'raymiz (kalit serverda).
        changes = await _gemini_css(data.instruction)

    if not changes:
        return WebsiteCustomizationResponse(
            success=False,
            message="❌ Buyruqni tushuna olmadim. Masalan: 'Rang qizil qil', 'Shrift kattalash'",
        )

    customization_json = json.dumps(changes)
    company.website_customization = customization_json
    await db.merge(company)
    await db.commit()

    return WebsiteCustomizationResponse(
        success=True,
        message=f"✅ O'zgarish tayyor! {', '.join(changes.keys())} o'zgartirildi",
        changes=changes,
        preview_url=f"/company/{company.slug or company.id}/preview",
    )


@router.get("/website/customization", summary="Get website customization")
async def get_website_customization(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current website customization for a company."""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Company yo'q")

    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company topilmadi")

    customization = {}
    if company.website_customization:
        try:
            customization = json.loads(company.website_customization)
        except:
            pass

    return {"customization": customization}


class RecommenderToggle(BaseModel):
    enabled: bool


@router.get("/recommender", summary="Tavsiyaga qo'shilish holati")
async def get_recommender_state(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Firma tavsiyalovchida qatnashayaptimi."""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Company yo'q")
    company = (
        await db.execute(
            select(Company).where(Company.id == current_user.company_id)
        )
    ).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company topilmadi")
    return {"enabled": bool(company.recommender_enabled)}


@router.patch("/recommender", summary="Tavsiyaga qo'shilish")
async def set_recommender_state(
    data: RecommenderToggle,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Firma o'z turlarini tavsiyalovchiga qo'shadi yoki chiqaradi.

    Bu qaror AGENTLIKNIKI, superadminniki emas: o'z turlarini kimga
    ko'rsatishni firma o'zi hal qiladi. Superadminda ham shunday tugma
    bor, lekin u faqat suiiste'mol holatida ishlatiladi.

    O'chirilganda turlar KATALOGDA qoladi — faqat tavsiyadan chiqadi.
    """
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Company yo'q")
    company = (
        await db.execute(
            select(Company).where(Company.id == current_user.company_id)
        )
    ).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company topilmadi")
    company.recommender_enabled = data.enabled
    await db.commit()
    return {"enabled": company.recommender_enabled}
