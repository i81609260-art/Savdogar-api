"""Review business logic."""

from datetime import date
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, BookingStatus
from app.models.review import Review
from app.models.tour import Tour
from app.models.user import User, UserRole


class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_review(
        self, user: User, booking_id: int, rating: int, comment: Optional[str]
    ) -> dict:
        """Submit a review for a completed, confirmed booking."""
        if not (1 <= rating <= 5):
            raise HTTPException(status_code=400, detail="Baho 1 dan 5 gacha bo'lishi kerak")

        result = await self.db.execute(
            select(Booking)
            .options(selectinload(Booking.tour))
            .where(Booking.id == booking_id, Booking.user_id == user.id)
        )
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=404, detail="Bron topilmadi")
        if booking.status != BookingStatus.CONFIRMED:
            raise HTTPException(status_code=400, detail="Faqat tasdiqlangan bronlarga sharh yozish mumkin")

        if booking.tour and booking.tour.end_date > date.today():
            raise HTTPException(status_code=400, detail="Tur hali tugamagan")

        existing = await self.db.execute(
            select(Review).where(Review.booking_id == booking_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Bu bronga allaqachon sharh yozilgan")

        review = Review(
            user_id=user.id,
            tour_id=booking.tour_id,
            company_id=booking.company_id,
            booking_id=booking_id,
            rating=rating,
            comment=comment,
        )
        self.db.add(review)
        await self.db.commit()
        await self.db.refresh(review)
        return self._to_dict(review, user)

    async def get_tour_reviews(self, tour_id: int) -> List[dict]:
        result = await self.db.execute(
            select(Review)
            .options(selectinload(Review.user))
            .where(Review.tour_id == tour_id)
            .order_by(Review.created_at.desc())
        )
        reviews = result.scalars().all()
        return [self._to_dict(r, r.user) for r in reviews]

    async def get_company_rating(self, company_id: int) -> dict:
        result = await self.db.execute(
            select(func.avg(Review.rating), func.count(Review.id)).where(
                Review.company_id == company_id
            )
        )
        avg, count = result.one()
        return {"average": round(float(avg or 0), 1), "count": count}

    async def list_admin_reviews(self, user: User) -> List[dict]:
        """Admin sees reviews for their company."""
        query = (
            select(Review)
            .options(selectinload(Review.user), selectinload(Review.tour))
            .order_by(Review.created_at.desc())
        )
        if user.role in (UserRole.ADMIN, UserRole.OPERATOR):
            query = query.where(Review.company_id == user.company_id)

        result = await self.db.execute(query)
        reviews = result.scalars().all()
        return [self._to_dict(r, r.user) for r in reviews]

    def _to_dict(self, review: Review, user) -> dict:
        return {
            "id": review.id,
            "booking_id": review.booking_id,
            "tour_id": review.tour_id,
            "tour_title": review.tour.title if hasattr(review, "tour") and review.tour else None,
            "user_name": user.full_name if user else "Noma'lum",
            "rating": review.rating,
            "comment": review.comment,
            "created_at": review.created_at.isoformat(),
        }
