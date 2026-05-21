"""Superadmin API routes."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.company import CompanyStatus
from app.models.user import User, UserRole
from app.schemas.auth import UserResponse
from app.schemas.company import CompanyRejectRequest, CompanyResponse
from app.schemas.reports import SuperAdminStats
from app.services.reports_service import ReportsService
from app.services.superadmin_service import SuperAdminService

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
    """List companies awaiting approval."""
    service = SuperAdminService(db)
    return await service.list_pending_companies()


@router.get(
    "/companies",
    response_model=List[CompanyResponse],
    summary="Barcha kompaniyalar",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def all_companies(
    status: Optional[CompanyStatus] = None,
    db: AsyncSession = Depends(get_db),
) -> List[CompanyResponse]:
    """List all companies."""
    service = SuperAdminService(db)
    return await service.list_all_companies(status)


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
    """Approve company application."""
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
    """Reject company application."""
    service = SuperAdminService(db)
    return await service.reject_company(company_id, data.reason)


@router.get(
    "/users",
    response_model=List[UserResponse],
    summary="Barcha foydalanuvchilar",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def all_users(
    db: AsyncSession = Depends(get_db),
) -> List[UserResponse]:
    """List all platform users."""
    service = SuperAdminService(db)
    return await service.list_all_users()


@router.get(
    "/stats",
    response_model=SuperAdminStats,
    summary="Platforma statistikasi",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def platform_stats(
    db: AsyncSession = Depends(get_db),
) -> SuperAdminStats:
    """Platform-wide statistics."""
    service = ReportsService(db)
    return await service.superadmin_stats()
