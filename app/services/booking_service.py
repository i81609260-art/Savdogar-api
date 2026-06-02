"""Booking business logic."""

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, BookingStatus
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate, BookingResponse, BookingStatusUpdate
from app.services.notification_service import NotificationService
from app.utils.pagination import PaginatedResponse, paginate


class BookingService:
    """Booking creation and status management."""

    def __init__(self, db: AsyncSession, sio=None):
        """Initialize with database session and optional Socket.io."""
        self.db = db
        self.notifier = NotificationService(db, sio)

    def _to_response(self, booking: Booking) -> BookingResponse:
        """Map booking ORM to response."""
        return BookingResponse(
            id=booking.id,
            user_id=booking.user_id,
            user_name=booking.user.full_name if booking.user else None,
            user_email=booking.user.email if booking.user else None,
            tour_id=booking.tour_id,
            tour_title=booking.tour.title if booking.tour else None,
            company_id=booking.company_id,
            status=booking.status,
            guests_count=booking.guests_count,
            total_price=booking.total_price,
            notes=booking.notes,
            cancel_reason=booking.cancel_reason,
            created_at=booking.created_at,
            updated_at=booking.updated_at,
        )

    async def create_booking(self, user: User, data: BookingCreate) -> BookingResponse:
        """User creates a pending booking."""
        # with_for_update() prevents race conditions when multiple users book simultaneously
        result = await self.db.execute(
            select(Tour)
            .options(selectinload(Tour.company))
            .where(Tour.id == data.tour_id, Tour.is_active == True)  # noqa: E712
            .with_for_update()
        )
        tour = result.scalar_one_or_none()
        if not tour:
            raise HTTPException(status_code=404, detail="Tur topilmadi")
        if tour.available_slots < data.guests_count:
            raise HTTPException(status_code=400, detail="Yetarli joy yo'q")

        total_price = tour.price * data.guests_count
        booking = Booking(
            user_id=user.id,
            tour_id=tour.id,
            company_id=tour.company_id,
            status=BookingStatus.PENDING,
            guests_count=data.guests_count,
            total_price=total_price,
            notes=data.notes,
        )
        self.db.add(booking)
        await self.db.flush()
        await self.db.refresh(booking)

        await self.notifier.notify_company_staff(
            tour.company_id,
            "Yangi bron",
            f"{user.full_name} «{tour.title}» turiga bron qildi",
            "booking",
            f"/bookings",
        )

        result = await self.db.execute(
            select(Booking)
            .options(selectinload(Booking.user), selectinload(Booking.tour))
            .where(Booking.id == booking.id)
        )
        booking = result.scalar_one()
        return self._to_response(booking)

    async def update_status(
        self, user: User, booking_id: int, data: BookingStatusUpdate
    ) -> BookingResponse:
        """Admin confirms or cancels a booking."""
        result = await self.db.execute(
            select(Booking)
            .options(selectinload(Booking.user), selectinload(Booking.tour))
            .where(Booking.id == booking_id)
        )
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=404, detail="Bron topilmadi")

        if user.role == UserRole.OPERATOR:
            raise HTTPException(status_code=403, detail="Operator status o'zgartira olmaydi")

        if user.role in (UserRole.ADMIN,) and booking.company_id != user.company_id:
            raise HTTPException(status_code=403, detail="Bu bron sizga tegishli emas")

        if booking.status != BookingStatus.PENDING and user.role != UserRole.SUPERADMIN:
            raise HTTPException(status_code=400, detail="Faqat kutilayotgan bronlarni o'zgartirish mumkin")

        old_status = booking.status
        booking.status = data.status
        if data.status == BookingStatus.CANCELLED:
            booking.cancel_reason = data.cancel_reason

        if data.status == BookingStatus.CONFIRMED and old_status == BookingStatus.PENDING:
            tour_result = await self.db.execute(
                select(Tour).where(Tour.id == booking.tour_id).with_for_update()
            )
            tour = tour_result.scalar_one()
            if tour.available_slots < booking.guests_count:
                raise HTTPException(status_code=400, detail="Yetarli joy yo'q")
            tour.available_slots -= booking.guests_count

        if data.status == BookingStatus.CANCELLED and old_status == BookingStatus.CONFIRMED:
            tour_result = await self.db.execute(
                select(Tour).where(Tour.id == booking.tour_id).with_for_update()
            )
            tour = tour_result.scalar_one()
            tour.available_slots += booking.guests_count
            # Navbatdagi birinchi foydalanuvchiga xabar berish
            from app.services.waitlist_service import WaitlistService
            await WaitlistService(self.db, self.notifier.sio).notify_first(booking.tour_id)

        await self.db.flush()

        status_labels = {
            BookingStatus.CONFIRMED: "tasdiqlandi",
            BookingStatus.CANCELLED: "bekor qilindi",
        }
        label = status_labels.get(data.status, data.status.value)
        booking_user = booking.user
        if booking_user:
            await self.notifier.create_and_send(
                booking_user,
                f"Bron {label}",
                f"«{booking.tour.title}» broningiz {label}",
                "booking",
                "/my-bookings",
            )

        if self.notifier.sio:
            await self.notifier.sio.emit(
                "booking_updated",
                {"booking_id": booking.id, "status": data.status.value},
                room=f"company_{booking.company_id}",
            )

        return self._to_response(booking)

    async def list_bookings(
        self,
        user: User,
        page: int = 1,
        page_size: int = 20,
        status_filter: Optional[BookingStatus] = None,
        company_id: Optional[int] = None,
    ) -> PaginatedResponse[BookingResponse]:
        """List bookings based on user role."""
        query = select(Booking).options(
            selectinload(Booking.user), selectinload(Booking.tour)
        )

        if user.role == UserRole.USER:
            query = query.where(Booking.user_id == user.id)
        elif user.role in (UserRole.ADMIN, UserRole.OPERATOR):
            query = query.where(Booking.company_id == user.company_id)
        elif company_id:
            query = query.where(Booking.company_id == company_id)

        if status_filter:
            query = query.where(Booking.status == status_filter)

        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        query = query.order_by(Booking.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        bookings = result.scalars().all()
        items = [self._to_response(b) for b in bookings]
        return paginate(items, total, page, page_size)

    async def get_booking(self, user: User, booking_id: int) -> BookingResponse:
        """Get single booking with access check."""
        result = await self.db.execute(
            select(Booking)
            .options(selectinload(Booking.user), selectinload(Booking.tour))
            .where(Booking.id == booking_id)
        )
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=404, detail="Bron topilmadi")

        if user.role == UserRole.USER and booking.user_id != user.id:
            raise HTTPException(status_code=403, detail="Ruxsat yo'q")
        if user.role in (UserRole.ADMIN, UserRole.OPERATOR):
            if booking.company_id != user.company_id:
                raise HTTPException(status_code=403, detail="Ruxsat yo'q")

        return self._to_response(booking)

    async def recent_bookings(self, company_id: int, limit: int = 5) -> List[BookingResponse]:
        """Get recent bookings for dashboard."""
        result = await self.db.execute(
            select(Booking)
            .options(selectinload(Booking.user), selectinload(Booking.tour))
            .where(Booking.company_id == company_id)
            .order_by(Booking.created_at.desc())
            .limit(limit)
        )
        return [self._to_response(b) for b in result.scalars().all()]
