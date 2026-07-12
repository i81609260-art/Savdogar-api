"""Branch (filial) management — CRUD scoped to the admin's company."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.branch import Branch
from app.models.company import Company
from app.models.user import User, UserRole
from app.services.tariff import DEFAULT_TARIFF, get_tariff, within_branch_limit

router = APIRouter(prefix="/api/branches", tags=["Branches"])

_ADMIN = role_required(UserRole.ADMIN, UserRole.OPERATOR)
_ADMIN_ONLY = role_required(UserRole.ADMIN)


class BranchIn(BaseModel):
    name: str
    city: str
    address: Optional[str] = None
    phone: Optional[str] = None


class BranchOut(BaseModel):
    id: int
    name: str
    city: str
    address: Optional[str] = None
    phone: Optional[str] = None
    is_main: bool = False

    model_config = {"from_attributes": True}


async def _company_tariff(db: AsyncSession, company_id: int) -> str:
    company = (
        await db.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    return getattr(company, "tariff", DEFAULT_TARIFF) if company else DEFAULT_TARIFF


@router.get("", summary="Filiallar ro'yxati")
async def list_branches(
    current_user: User = Depends(_ADMIN),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Company branches plus the plan's branch limit."""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniyaga biriktirilmagansiz")

    rows = (
        await db.execute(
            select(Branch)
            .where(Branch.company_id == current_user.company_id)
            .order_by(Branch.is_main.desc(), Branch.id.asc())
        )
    ).scalars().all()
    tariff = get_tariff(await _company_tariff(db, current_user.company_id))
    return {
        "branches": [BranchOut.model_validate(b) for b in rows],
        "used": len(rows),
        "max_branches": tariff["max_branches"],
    }


@router.post("", response_model=BranchOut, summary="Filial qo'shish")
async def create_branch(
    data: BranchIn,
    current_user: User = Depends(_ADMIN_ONLY),
    db: AsyncSession = Depends(get_db),
) -> BranchOut:
    """Create a branch, enforcing the plan's branch limit."""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniyaga biriktirilmagansiz")

    count = (
        await db.execute(
            select(func.count(Branch.id)).where(
                Branch.company_id == current_user.company_id
            )
        )
    ).scalar() or 0
    tariff_key = await _company_tariff(db, current_user.company_id)
    if not within_branch_limit(tariff_key, count):
        limit = get_tariff(tariff_key)["max_branches"]
        raise HTTPException(
            status_code=403,
            detail=f"Tarif limiti: {limit} ta filial. Ko'proq uchun tarifni yangilang.",
        )

    branch = Branch(
        company_id=current_user.company_id,
        name=data.name,
        city=data.city,
        address=data.address,
        phone=data.phone,
        is_main=(count == 0),  # first branch is the main office
    )
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    return BranchOut.model_validate(branch)


@router.patch("/{branch_id}", response_model=BranchOut, summary="Filialni tahrirlash")
async def update_branch(
    branch_id: int,
    data: BranchIn,
    current_user: User = Depends(_ADMIN_ONLY),
    db: AsyncSession = Depends(get_db),
) -> BranchOut:
    branch = (
        await db.execute(select(Branch).where(Branch.id == branch_id))
    ).scalar_one_or_none()
    if not branch or branch.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    branch.name = data.name
    branch.city = data.city
    branch.address = data.address
    branch.phone = data.phone
    await db.commit()
    await db.refresh(branch)
    return BranchOut.model_validate(branch)


@router.delete("/{branch_id}", summary="Filialni o'chirish")
async def delete_branch(
    branch_id: int,
    current_user: User = Depends(_ADMIN_ONLY),
    db: AsyncSession = Depends(get_db),
) -> dict:
    branch = (
        await db.execute(select(Branch).where(Branch.id == branch_id))
    ).scalar_one_or_none()
    if not branch or branch.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    # Detach any staff assigned to this branch.
    staff = (
        await db.execute(select(User).where(User.branch_id == branch_id))
    ).scalars().all()
    for u in staff:
        u.branch_id = None
    await db.delete(branch)
    await db.commit()
    return {"status": "deleted"}
