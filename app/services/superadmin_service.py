"""Superadmin platform management business logic."""

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.company import Company, CompanyStatus
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.schemas.auth import SuperAdminUserResponse, UserResponse
from app.schemas.company import CompanyDetailResponse, CompanyResponse


class SuperAdminService:
    """Company approval and platform oversight."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def list_pending_companies(self) -> List[CompanyResponse]:
        """List companies awaiting approval."""
        result = await self.db.execute(
            select(Company)
            .where(Company.status == CompanyStatus.PENDING)
            .order_by(Company.created_at.desc())
        )
        return [CompanyResponse.model_validate(c) for c in result.scalars().all()]

    async def list_all_companies(
        self, status_filter: CompanyStatus | None = None
    ) -> List[CompanyResponse]:
        """List all companies with optional status filter."""
        query = select(Company).order_by(Company.created_at.desc())
        if status_filter:
            query = query.where(Company.status == status_filter)
        result = await self.db.execute(query)
        return [CompanyResponse.model_validate(c) for c in result.scalars().all()]

    async def approve_company(self, company_id: int) -> CompanyResponse:
        """Re-activate a previously rejected company and its users."""
        result = await self.db.execute(
            select(Company).where(Company.id == company_id)
        )
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Kompaniya topilmadi")

        company.status = CompanyStatus.APPROVED
        company.rejection_reason = None
        users_result = await self.db.execute(
            select(User).where(User.company_id == company.id)
        )
        for u in users_result.scalars().all():
            u.is_active = True

        await self.db.flush()
        return CompanyResponse.model_validate(company)

    async def reject_company(self, company_id: int, reason: str) -> CompanyResponse:
        """Reject company and deactivate all its users."""
        result = await self.db.execute(
            select(Company).where(Company.id == company_id)
        )
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Kompaniya topilmadi")

        company.status = CompanyStatus.REJECTED
        company.rejection_reason = reason
        users_result = await self.db.execute(
            select(User).where(User.company_id == company.id)
        )
        for u in users_result.scalars().all():
            u.is_active = False

        await self.db.flush()
        return CompanyResponse.model_validate(company)

    async def list_all_users(self) -> List[SuperAdminUserResponse]:
        """List all platform users with full details."""
        try:
            result = await self.db.execute(
                select(User).options(selectinload(User.company)).order_by(User.created_at.desc())
            )
            users = result.scalars().all()
            out = []
            for u in users:
                comp_status = None
                if u.company:
                    comp_status = str(u.company.status.value) if hasattr(u.company.status, "value") else str(u.company.status)
                
                out.append(SuperAdminUserResponse(
                    id=u.id,
                    email=u.email,
                    full_name=u.full_name,
                    phone=u.phone,
                    role=u.role,
                    company_id=u.company_id,
                    company_status=comp_status,
                    is_active=u.is_active,
                    created_at=u.created_at.isoformat() if u.created_at else None,
                ))
            return out
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"ERROR IN list_all_users: {tb}")
            raise HTTPException(status_code=500, detail=f"Database error in list_all_users: {str(e)}\n{tb}")

    async def get_company_detail(self, company_id: int) -> CompanyDetailResponse:
        """Get full company details with user and tour counts."""
        try:
            result = await self.db.execute(
                select(Company).options(selectinload(Company.users)).where(Company.id == company_id)
            )
            company = result.scalar_one_or_none()
            if not company:
                raise HTTPException(status_code=404, detail="Kompaniya topilmadi")

            tours_count_r = await self.db.execute(
                select(func.count()).where(Tour.company_id == company_id)
            )
            tours_count = tours_count_r.scalar() or 0

            logo_url_val = getattr(company, "logo_url", None)

            return CompanyDetailResponse(
                id=company.id,
                name=company.name,
                description=company.description,
                city=company.city,
                phone=company.phone,
                email=company.email,
                status=company.status,
                rejection_reason=company.rejection_reason,
                logo_url=logo_url_val,
                owner_id=company.owner_id,
                created_at=company.created_at,
                updated_at=company.updated_at,
                users_count=len(company.users),
                tours_count=tours_count,
            )
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            import traceback
            tb = traceback.format_exc()
            raise HTTPException(status_code=500, detail=f"Error in get_company_detail: {str(e)}\n{tb}")

    async def list_all_companies_detail(
        self, status_filter: Optional[CompanyStatus] = None
    ) -> List[CompanyDetailResponse]:
        """List all companies with user and tour counts."""
        try:
            query = (
                select(Company)
                .options(selectinload(Company.users))
                .order_by(Company.created_at.desc())
            )
            if status_filter:
                query = query.where(Company.status == status_filter)
            result = await self.db.execute(query)
            companies = result.scalars().all()

            out = []
            for c in companies:
                tours_count_r = await self.db.execute(
                    select(func.count()).where(Tour.company_id == c.id)
                )
                tours_count = tours_count_r.scalar() or 0
                
                logo_url_val = getattr(c, "logo_url", None)
                
                out.append(CompanyDetailResponse(
                    id=c.id,
                    name=c.name,
                    description=c.description,
                    city=c.city,
                    phone=c.phone,
                    email=c.email,
                    status=c.status,
                    rejection_reason=c.rejection_reason,
                    logo_url=logo_url_val,
                    owner_id=c.owner_id,
                    created_at=c.created_at,
                    updated_at=c.updated_at,
                    users_count=len(c.users),
                    tours_count=tours_count,
                ))
            return out
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"ERROR IN list_all_companies_detail: {tb}")
            raise HTTPException(status_code=500, detail=f"Database error in list_all_companies_detail: {str(e)}\n{tb}")
