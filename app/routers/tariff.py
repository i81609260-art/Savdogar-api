"""Subscription plan (tariff) API — view current plan, switch, and audit log."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.role_guard import role_required
from app.models.company import Company
from app.models.tariff_change import TariffChange
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.services.tariff import DEFAULT_TARIFF, TARIFFS, get_tariff, tariff_list

router = APIRouter(prefix="/api/tariff", tags=["Tariff"])


class SwitchRequest(BaseModel):
    tariff: str


@router.get("/plans", summary="Barcha tariflar")
async def get_plans() -> dict:
    """All subscription plans, cheapest first."""
    return {"plans": tariff_list()}


@router.get("/current", summary="Joriy tarif va limitlar")
async def get_current(
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The company's active plan plus current usage against its limits."""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniyaga biriktirilmagansiz")

    company = (
        await db.execute(select(Company).where(Company.id == current_user.company_id))
    ).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")

    tariff = get_tariff(getattr(company, "tariff", DEFAULT_TARIFF))
    tours_used = (
        await db.execute(
            select(func.count(Tour.id)).where(Tour.company_id == company.id)
        )
    ).scalar() or 0
    operators_used = (
        await db.execute(
            select(func.count(User.id)).where(
                User.company_id == company.id,
                User.role.in_([UserRole.ADMIN, UserRole.OPERATOR]),
            )
        )
    ).scalar() or 0

    return {
        "tariff": tariff,
        "usage": {"tours": tours_used, "operators": operators_used},
    }


@router.post("/switch", summary="Boshqa tarifga o'tish")
async def switch_tariff(
    data: SwitchRequest,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Switch the company's plan. The new limits take effect immediately in the
    DB; the client should sign the user out so a fresh login picks them up."""
    if data.tariff not in TARIFFS:
        raise HTTPException(status_code=400, detail="Noma'lum tarif")
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniyaga biriktirilmagansiz")

    company = (
        await db.execute(select(Company).where(Company.id == current_user.company_id))
    ).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")

    old_tariff = getattr(company, "tariff", DEFAULT_TARIFF)
    if old_tariff == data.tariff:
        return {"tariff": get_tariff(data.tariff), "changed": False}

    company.tariff = data.tariff
    db.add(company)
    db.add(
        TariffChange(
            company_id=company.id,
            company_name=company.name,
            from_tariff=old_tariff,
            to_tariff=data.tariff,
        )
    )
    await db.commit()
    return {"tariff": get_tariff(data.tariff), "changed": True}


@router.get("/changes", summary="Tarif o'zgarishlari (superadmin)")
async def list_changes(
    current_user: User = Depends(role_required(UserRole.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Recent plan switches — which company moved to which plan."""
    rows = (
        await db.execute(
            select(TariffChange).order_by(TariffChange.created_at.desc()).limit(100)
        )
    ).scalars().all()
    return {
        "changes": [
            {
                "id": r.id,
                "company_id": r.company_id,
                "company_name": r.company_name,
                "from_tariff": r.from_tariff,
                "from_name": get_tariff(r.from_tariff)["name"] if r.from_tariff else None,
                "to_tariff": r.to_tariff,
                "to_name": get_tariff(r.to_tariff)["name"],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }
