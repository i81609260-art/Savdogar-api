"""Superadmin platform management business logic."""

from typing import List

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.company import Company, CompanyStatus
from app.models.user import User, UserRole
from app.schemas.company import CompanyResponse
from app.schemas.auth import UserResponse


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
        """Approve company and activate admin account."""
        result = await self.db.execute(
            select(Company).options(selectinload(Company.users)).where(Company.id == company_id)
        )
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Kompaniya topilmadi")
        if company.status != CompanyStatus.PENDING:
            raise HTTPException(status_code=400, detail="Kompaniya allaqachon ko'rib chiqilgan")

        company.status = CompanyStatus.APPROVED
        admin_result = await self.db.execute(
            select(User).where(
                User.company_id == company.id,
                User.role == UserRole.ADMIN,
            )
        )
        admin = admin_result.scalar_one_or_none()
        if admin:
            admin.is_active = True

        await self.db.flush()
        return CompanyResponse.model_validate(company)

    async def reject_company(self, company_id: int, reason: str) -> CompanyResponse:
        """Reject company application."""
        result = await self.db.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Kompaniya topilmadi")

        company.status = CompanyStatus.REJECTED
        company.rejection_reason = reason
        await self.db.flush()
        return CompanyResponse.model_validate(company)

    async def list_all_users(self) -> List[UserResponse]:
        """List all platform users."""
        result = await self.db.execute(select(User).order_by(User.created_at.desc()))
        return [UserResponse.model_validate(u) for u in result.scalars().all()]
