"""CRM customer management business logic."""

from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, BookingStatus
from app.models.user import User, UserRole
from app.schemas.booking import BookingResponse
from app.schemas.crm import CustomerResponse, CustomerCreateRequest
from app.utils.pagination import PaginatedResponse, paginate


class CRMService:
    """Customer relationship management for tour companies."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    def _segment(self, confirmed_count: int, total_spent: float) -> str:
        """Determine customer segment by booking count and spend."""
        if confirmed_count >= 5 or total_spent >= 1000:
            return "vip"
        if confirmed_count >= 1:
            return "returning"
        return "new"

    async def list_customers(
        self, user: User, page: int = 1, page_size: int = 20
    ) -> PaginatedResponse[CustomerResponse]:
        """List all customers who booked with the company (paginated)."""
        if not user.company_id:
            raise HTTPException(status_code=403, detail="Kompaniyaga biriktirilmagansiz")

        subq = (
            select(Booking.user_id)
            .where(Booking.company_id == user.company_id)
            .distinct()
            .subquery()
        )

        count_q = select(func.count(User.id)).where(
            User.id.in_(select(subq)), User.role == UserRole.USER
        )
        total = (await self.db.execute(count_q)).scalar() or 0

        result = await self.db.execute(
            select(User)
            .where(User.id.in_(select(subq)), User.role == UserRole.USER)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        users = result.scalars().all()
        customers = []
        for u in users:
            customers.append(await self._build_customer(u.id, user.company_id))
        return paginate(customers, total, page, page_size)

    async def get_customer(
        self, user: User, customer_id: int, include_bookings: bool = True
    ) -> CustomerResponse:
        """Get customer profile with booking history."""
        if not user.company_id:
            raise HTTPException(status_code=403, detail="Kompaniyaga biriktirilmagansiz")
        return await self._build_customer(
            customer_id, user.company_id, include_bookings
        )

    async def _build_customer(
        self,
        user_id: int,
        company_id: int,
        include_bookings: bool = False,
    ) -> CustomerResponse:
        """Build customer response with stats."""
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        customer = user_result.scalar_one_or_none()
        if not customer:
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")

        bookings_result = await self.db.execute(
            select(Booking)
            .options(selectinload(Booking.tour), selectinload(Booking.user))
            .where(Booking.user_id == user_id, Booking.company_id == company_id)
            .order_by(Booking.created_at.desc())
        )
        bookings = bookings_result.scalars().all()
        confirmed = [b for b in bookings if b.status == BookingStatus.CONFIRMED]
        total_spent = sum(b.total_price for b in confirmed)

        booking_responses = []
        if include_bookings:
            booking_responses = [
                BookingResponse(
                    id=b.id,
                    user_id=b.user_id,
                    user_name=customer.full_name,
                    user_email=customer.email,
                    tour_id=b.tour_id,
                    tour_title=b.tour.title if b.tour else None,
                    company_id=b.company_id,
                    status=b.status,
                    guests_count=b.guests_count,
                    total_price=b.total_price,
                    notes=b.notes,
                    cancel_reason=b.cancel_reason,
                    created_at=b.created_at,
                    updated_at=b.updated_at,
                )
                for b in bookings
            ]

        last_booking = bookings[0].created_at if bookings else None

        return CustomerResponse(
            id=customer.id,
            email=customer.email,
            full_name=customer.full_name,
            phone=customer.phone,
            total_bookings=len(bookings),
            confirmed_bookings=len(confirmed),
            total_spent=total_spent,
            segment=self._segment(len(confirmed), total_spent),
            last_booking_at=last_booking,
            bookings=booking_responses,
        )

    async def update_customer_note(
        self, user: User, customer_id: int, note: str
    ) -> dict:
        """Operator limited write — add note via latest booking."""
        if user.role not in (UserRole.ADMIN, UserRole.OPERATOR):
            raise HTTPException(status_code=403, detail="Ruxsat yo'q")

        result = await self.db.execute(
            select(Booking)
            .where(
                Booking.user_id == customer_id,
                Booking.company_id == user.company_id,
            )
            .order_by(Booking.created_at.desc())
            .limit(1)
        )
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=404, detail="Bron topilmadi")
        booking.notes = note
        await self.db.flush()
        return {"message": "Izoh saqlandi"}

    async def create_customer(
        self, user: User, data: CustomerCreateRequest
    ) -> CustomerResponse:
        """Create a new customer (User with UserRole.USER) and confirm their booking for a tour."""
        from app.models.tour import Tour
        from app.utils.security import hash_password

        if not user.company_id:
            raise HTTPException(status_code=403, detail="Kompaniyaga biriktirilmagansiz")

        # 1. Fetch tour and verify ownership
        tour_result = await self.db.execute(
            select(Tour).where(Tour.id == data.tour_id)
        )
        tour = tour_result.scalar_one_or_none()
        if not tour or tour.company_id != user.company_id:
            raise HTTPException(status_code=404, detail="Tur topilmadi yoki kompaniyaga tegishli emas")

        # 2. Check if user already exists
        user_result = await self.db.execute(
            select(User).where(User.email == data.email)
        )
        customer = user_result.scalar_one_or_none()

        if not customer:
            customer = User(
                email=data.email,
                full_name=data.full_name,
                phone=data.phone,
                role=UserRole.USER,
                hashed_password=hash_password(f"User_{data.phone}!"),
                is_active=True,
            )
            self.db.add(customer)
            await self.db.flush()
        else:
            # Update phone if it was empty/changed
            if data.phone:
                customer.phone = data.phone
            self.db.add(customer)
            await self.db.flush()

        # 3. Create confirmed booking for the tour
        total_price = tour.price * data.guests_count
        booking = Booking(
            user_id=customer.id,
            tour_id=tour.id,
            company_id=user.company_id,
            status=BookingStatus.CONFIRMED,
            guests_count=data.guests_count,
            total_price=total_price,
            phone=data.phone,
            notes=data.notes,
        )
        self.db.add(booking)
        await self.db.flush()
        await self.db.commit()

        return await self._build_customer(customer.id, user.company_id, include_bookings=True)
