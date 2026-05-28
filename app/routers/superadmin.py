"""Superadmin API routes."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.company import CompanyStatus
from app.models.user import User, UserRole
from app.schemas.auth import SuperAdminUserResponse, UserResponse
from app.schemas.company import CompanyDetailResponse, CompanyRejectRequest, CompanyResponse
from app.schemas.reports import SuperAdminStats
from app.services.reports_service import ReportsService
from app.services.superadmin_service import SuperAdminService
from app.utils.security import hash_password


class ResetPasswordRequest(BaseModel):
    new_password: str

router = APIRouter(prefix="/api/superadmin", tags=["SuperAdmin"])


@router.get(
    "/companies/pending",
    response_model=List[CompanyResponse],
    summary="Kutilayotgan kompaniyalar",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def pending_companies(
    db: AsyncSession = Depends(get_db),
) -> List[CompanyResponse]:
    service = SuperAdminService(db)
    return await service.list_pending_companies()


@router.get(
    "/companies",
    response_model=List[CompanyDetailResponse],
    summary="Barcha kompaniyalar (to'liq)",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def all_companies(
    status: Optional[CompanyStatus] = None,
    db: AsyncSession = Depends(get_db),
) -> List[CompanyDetailResponse]:
    """Barcha kompaniyalar — foydalanuvchilar va turlar soni bilan."""
    service = SuperAdminService(db)
    return await service.list_all_companies_detail(status)


@router.get(
    "/companies/{company_id}",
    response_model=CompanyDetailResponse,
    summary="Kompaniya to'liq ma'lumotlari",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def company_detail(
    company_id: int,
    db: AsyncSession = Depends(get_db),
) -> CompanyDetailResponse:
    service = SuperAdminService(db)
    return await service.get_company_detail(company_id)


@router.post(
    "/companies/{company_id}/approve",
    response_model=CompanyResponse,
    summary="Kompaniyani tasdiqlash",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def approve_company(
    company_id: int,
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    service = SuperAdminService(db)
    return await service.approve_company(company_id)


@router.post(
    "/companies/{company_id}/reject",
    response_model=CompanyResponse,
    summary="Kompaniyani rad etish",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def reject_company(
    company_id: int,
    data: CompanyRejectRequest,
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    service = SuperAdminService(db)
    return await service.reject_company(company_id, data.reason)


@router.get(
    "/users",
    response_model=List[SuperAdminUserResponse],
    summary="Barcha foydalanuvchilar (to'liq)",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def all_users(
    db: AsyncSession = Depends(get_db),
) -> List[SuperAdminUserResponse]:
    """Barcha userlar — email, rol, kompaniya, faollik holati."""
    service = SuperAdminService(db)
    return await service.list_all_users()


@router.patch(
    "/users/{user_id}/reset-password",
    summary="Foydalanuvchi parolini o'zgartirish",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def reset_user_password(
    user_id: int,
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    user.hashed_password = hash_password(data.new_password)
    await db.flush()
    return {"message": "Parol muvaffaqiyatli o'zgartirildi"}


@router.patch(
    "/users/{user_id}/toggle-active",
    summary="Foydalanuvchini faollashtirish/o'chirish",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def toggle_user_active(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    user.is_active = not user.is_active
    await db.flush()
    return {"is_active": user.is_active}


@router.get(
    "/stats",
    response_model=SuperAdminStats,
    summary="Platforma statistikasi",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def platform_stats(
    db: AsyncSession = Depends(get_db),
) -> SuperAdminStats:
    service = ReportsService(db)
    return await service.superadmin_stats()
