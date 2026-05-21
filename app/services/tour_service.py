"""Tour package business logic."""

from datetime import date
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.company import Company, CompanyStatus
from app.models.tour import Tour
from app.models.user import User
from app.schemas.tour import TourCreate, TourResponse, TourUpdate
from app.utils.pagination import PaginatedResponse, paginate


class TourService:
    """CRUD and search operations for tour packages."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    def _to_response(self, tour: Tour, company_name: Optional[str] = None) -> TourResponse:
        """Map ORM tour to response schema."""
        return TourResponse(
            id=tour.id,
            company_id=tour.company_id,
            company_name=company_name or (tour.company.name if tour.company else None),
            title=tour.title,
            description=tour.description,
            city=tour.city,
            country=tour.country,
            price=tour.price,
            duration_days=tour.duration_days,
            start_date=tour.start_date,
            end_date=tour.end_date,
            available_slots=tour.available_slots,
            image_url=tour.image_url,
            is_active=tour.is_active,
            created_at=tour.created_at,
        )

    async def list_tours(
        self,
        page: int = 1,
        page_size: int = 12,
        city: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        start_date: Optional[date] = None,
        min_slots: Optional[int] = None,
        search: Optional[str] = None,
        company_id: Optional[int] = None,
        active_only: bool = True,
    ) -> PaginatedResponse[TourResponse]:
        """List tours with filters and pagination."""
        query = select(Tour).options(selectinload(Tour.company))
        conditions = []

        if active_only:
            conditions.append(Tour.is_active == True)  # noqa: E712
        if city:
            conditions.append(Tour.city.ilike(f"%{city}%"))
        if min_price is not None:
            conditions.append(Tour.price >= min_price)
        if max_price is not None:
            conditions.append(Tour.price <= max_price)
        if start_date:
            conditions.append(Tour.start_date >= start_date)
        if min_slots is not None:
            conditions.append(Tour.available_slots >= min_slots)
        if company_id:
            conditions.append(Tour.company_id == company_id)
        if search:
            conditions.append(
                or_(
                    Tour.title.ilike(f"%{search}%"),
                    Tour.description.ilike(f"%{search}%"),
                    Tour.city.ilike(f"%{search}%"),
                )
            )

        if conditions:
            query = query.where(and_(*conditions))

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        query = query.order_by(Tour.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        tours = result.scalars().all()

        items = [self._to_response(t) for t in tours]
        return paginate(items, total, page, page_size)

    async def get_tour(self, tour_id: int) -> TourResponse:
        """Get single tour by ID."""
        result = await self.db.execute(
            select(Tour).options(selectinload(Tour.company)).where(Tour.id == tour_id)
        )
        tour = result.scalar_one_or_none()
        if not tour:
            raise HTTPException(status_code=404, detail="Tur topilmadi")
        return self._to_response(tour)

    async def create_tour(self, user: User, data: TourCreate) -> TourResponse:
        """Create tour for admin's company."""
        if not user.company_id:
            raise HTTPException(status_code=403, detail="Kompaniyaga biriktirilmagansiz")

        if data.end_date < data.start_date:
            raise HTTPException(status_code=400, detail="Tugash sanasi boshlanishdan oldin bo'lmasin")

        tour = Tour(
            company_id=user.company_id,
            title=data.title,
            description=data.description,
            city=data.city,
            country=data.country,
            price=data.price,
            duration_days=data.duration_days,
            start_date=data.start_date,
            end_date=data.end_date,
            available_slots=data.available_slots,
        )
        self.db.add(tour)
        await self.db.flush()
        await self.db.refresh(tour)
        result = await self.db.execute(
            select(Tour).options(selectinload(Tour.company)).where(Tour.id == tour.id)
        )
        tour = result.scalar_one()
        return self._to_response(tour)

    async def update_tour(
        self, user: User, tour_id: int, data: TourUpdate
    ) -> TourResponse:
        """Update tour belonging to admin's company."""
        result = await self.db.execute(select(Tour).where(Tour.id == tour_id))
        tour = result.scalar_one_or_none()
        if not tour:
            raise HTTPException(status_code=404, detail="Tur topilmadi")
        if tour.company_id != user.company_id:
            raise HTTPException(status_code=403, detail="Bu tur sizga tegishli emas")

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(tour, field, value)
        await self.db.flush()
        return await self.get_tour(tour_id)

    async def delete_tour(self, user: User, tour_id: int) -> dict:
        """Soft-delete tour by deactivating."""
        result = await self.db.execute(select(Tour).where(Tour.id == tour_id))
        tour = result.scalar_one_or_none()
        if not tour:
            raise HTTPException(status_code=404, detail="Tur topilmadi")
        if tour.company_id != user.company_id:
            raise HTTPException(status_code=403, detail="Bu tur sizga tegishli emas")
        tour.is_active = False
        return {"message": "Tur o'chirildi"}

    async def upload_image(self, user: User, tour_id: int, image_url: str) -> TourResponse:
        """Set tour image URL after file upload."""
        result = await self.db.execute(select(Tour).where(Tour.id == tour_id))
        tour = result.scalar_one_or_none()
        if not tour:
            raise HTTPException(status_code=404, detail="Tur topilmadi")
        if tour.company_id != user.company_id:
            raise HTTPException(status_code=403, detail="Bu tur sizga tegishli emas")
        tour.image_url = image_url
        await self.db.flush()
        return await self.get_tour(tour_id)
