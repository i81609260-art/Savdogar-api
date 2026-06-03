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


class UserCreateRequest(BaseModel):
    email: str
    password: str
    full_name: str
    phone: Optional[str] = None
    role: str = "user"
    company_id: Optional[int] = None
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    company_id: Optional[int] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class CompanyCreateRequest(BaseModel):
    name: str
    city: str
    phone: str
    email: str
    description: Optional[str] = None


class CompanyUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None


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


@router.get(
    "/users/{user_id}",
    response_model=SuperAdminUserResponse,
    summary="Foydalanuvchi ma'lumotlari",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def get_user_detail(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> SuperAdminUserResponse:
    """Bitta foydalanuvchi — email, rol, kompaniya, faollik holati."""
    from app.schemas.auth import SuperAdminUserResponse as Response
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    return Response(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        role=user.role.value,
        company_id=user.company_id,
        is_active=user.is_active,
        created_at=user.created_at,
    )


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


@router.post(
    "/users",
    summary="Yangi foydalanuvchi yaratish",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def create_user(
    data: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = SuperAdminService(db)
    return await service.create_user(data.model_dump())


@router.put(
    "/users/{user_id}",
    summary="Foydalanuvchi ma'lumotlarini yangilash",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def update_user(
    user_id: int,
    data: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = SuperAdminService(db)
    return await service.update_user(user_id, data.model_dump(exclude_none=True))


@router.delete(
    "/users/{user_id}",
    summary="Foydalanuvchini o'chirish",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = SuperAdminService(db)
    await service.delete_user(user_id)
    return {"message": "Foydalanuvchi o'chirildi"}


@router.post(
    "/companies",
    summary="Yangi kompaniya yaratish",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def create_company(
    data: CompanyCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = SuperAdminService(db)
    return await service.create_company(data.model_dump())


@router.put(
    "/companies/{company_id}",
    summary="Kompaniya ma'lumotlarini yangilash",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def update_company(
    company_id: int,
    data: CompanyUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = SuperAdminService(db)
    return await service.update_company(company_id, data.model_dump(exclude_none=True))


@router.delete(
    "/companies/{company_id}",
    summary="Kompaniyani o'chirish",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def delete_company(
    company_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = SuperAdminService(db)
    await service.delete_company(company_id)
    return {"message": "Kompaniya o'chirildi"}


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
