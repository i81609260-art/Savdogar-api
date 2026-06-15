"""Company settings — Company info & website customization."""

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.company import Company
from app.models.user import User
from app.schemas.company import CompanyInfoUpdate, WebsiteCustomizationRequest, WebsiteCustomizationResponse

router = APIRouter(prefix="/api/admin/company", tags=["Company Settings"])


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
