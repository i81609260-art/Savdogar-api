"""Public company profile endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.company import Company
from app.schemas.company import CompanyResponse

router = APIRouter(prefix="/api/companies", tags=["Companies"])


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
