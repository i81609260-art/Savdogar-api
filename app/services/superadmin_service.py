"""Superadmin platform management business logic."""

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking
from app.models.company import Company, CompanyStatus
from app.models.review import Review
from app.models.tour import Tour
from app.utils.slug import unique_slug
from app.models.user import User, UserRole
from app.schemas.auth import SuperAdminUserResponse, UserResponse
from app.schemas.company import CompanyDetailResponse, CompanyResponse
from app.utils.security import hash_password


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

    async def create_user(self, data: dict) -> SuperAdminUserResponse:
        existing = await self.db.execute(select(User).where(User.email == data["email"]))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Bu email allaqachon ro'yxatdan o'tgan")
        user = User(
            email=data["email"],
            full_name=data["full_name"],
            phone=data.get("phone"),
            role=UserRole(data.get("role", "user")),
            company_id=data.get("company_id"),
            is_active=data.get("is_active", True),
            hashed_password=hash_password(data["password"]),
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return SuperAdminUserResponse(
            id=user.id, email=user.email, full_name=user.full_name,
            phone=user.phone, role=user.role, company_id=user.company_id,
            company_status=None, is_active=user.is_active,
            created_at=user.created_at.isoformat() if user.created_at else None,
        )

    async def update_user(self, user_id: int, data: dict) -> SuperAdminUserResponse:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
        for field in ("full_name", "email", "phone", "company_id", "is_active"):
            if field in data:
                setattr(user, field, data[field])
        if "role" in data:
            user.role = UserRole(data["role"])
        if data.get("password"):
            user.hashed_password = hash_password(data["password"])
        await self.db.commit()
        await self.db.refresh(user)
        return SuperAdminUserResponse(
            id=user.id, email=user.email, full_name=user.full_name,
            phone=user.phone, role=user.role, company_id=user.company_id,
            company_status=None, is_active=user.is_active,
            created_at=user.created_at.isoformat() if user.created_at else None,
        )

    async def delete_user(self, user_id: int) -> None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
        if user.role == UserRole.SUPERADMIN:
            raise HTTPException(status_code=403, detail="Superadmin o'chirib bo'lmaydi")
        await self.db.delete(user)
        await self.db.commit()

    async def update_company(self, company_id: int, data: dict) -> CompanyDetailResponse:
        result = await self.db.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Kompaniya topilmadi")
        for field in ("name", "description", "city", "phone", "email"):
            if field in data:
                setattr(company, field, data[field])
        if "status" in data:
            company.status = CompanyStatus(data["status"])
        await self.db.commit()
        return await self.get_company_detail(company_id)

    async def delete_company(self, company_id: int) -> None:
        result = await self.db.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Kompaniya topilmadi")
        tour_ids_r = await self.db.execute(
            select(Tour.id).where(Tour.company_id == company_id)
        )
        tour_ids = list(tour_ids_r.scalars().all())
        await self.db.execute(sa_delete(Review).where(Review.company_id == company_id))
        if tour_ids:
            await self.db.execute(sa_delete(Booking).where(Booking.tour_id.in_(tour_ids)))
        await self.db.execute(sa_delete(Tour).where(Tour.company_id == company_id))
        await self.db.execute(
            sa_update(User).where(User.company_id == company_id).values(company_id=None, is_active=False)
        )
        await self.db.delete(company)
        await self.db.commit()

    async def create_company(self, data: dict) -> CompanyDetailResponse:
        company = Company(
            name=data["name"],
            slug=await unique_slug(data["name"], self.db),
            description=data.get("description"),
            city=data["city"],
            phone=data["phone"],
            email=data["email"],
            status=CompanyStatus.APPROVED,
        )
        self.db.add(company)
        await self.db.commit()
        await self.db.refresh(company)
        return await self.get_company_detail(company.id)
