"""Review business logic."""

import math
from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, BookingStatus
from app.models.guest_review import GuestReview
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

    async def list_company_reviews_public(self, company_id: int, limit: int = 6) -> List[dict]:
        result = await self.db.execute(
            select(Review)
            .options(selectinload(Review.user), selectinload(Review.tour))
            .where(Review.company_id == company_id)
            .order_by(Review.created_at.desc())
            .limit(limit)
        )
        reviews = result.scalars().all()
        return [self._to_dict(r, r.user) for r in reviews]

    async def list_admin_reviews(self, user: User) -> List[dict]:
        """Admin sees reviews (regular + guest) for their company."""
        # Regular reviews
        query = (
            select(Review)
            .options(selectinload(Review.user), selectinload(Review.tour))
            .order_by(Review.created_at.desc())
        )
        if user.role in (UserRole.ADMIN, UserRole.OPERATOR):
            query = query.where(Review.company_id == user.company_id)

        result = await self.db.execute(query)
        reviews = [self._to_dict(r, r.user) for r in result.scalars().all()]

        # Guest reviews
        guest_query = select(GuestReview).order_by(GuestReview.created_at.desc())
        if user.role in (UserRole.ADMIN, UserRole.OPERATOR):
            guest_query = guest_query.where(GuestReview.company_id == user.company_id)

        guest_result = await self.db.execute(guest_query)
        guest_reviews = [self._guest_to_dict(gr) for gr in guest_result.scalars().all()]

        # Combine and sort by date
        all_reviews = reviews + guest_reviews
        all_reviews.sort(key=lambda r: r["created_at"], reverse=True)
        return all_reviews

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
            "is_guest": False,
        }

    def _ml_score(self, rating: int, comment: Optional[str], created_at: datetime) -> float:
        """Weighted ML-inspired ranking: rating + content depth + recency."""
        now = datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        age_days = max((now - created_at).days, 0)
        recency = max(0.0, 1.0 - age_days / 365.0)
        content = min(len(comment or ""), 300) / 300.0
        return rating * 0.6 + content * 0.25 + recency * 0.15

    async def create_guest_review(
        self, company_id: int, guest_name: str, rating: int, comment: Optional[str]
    ) -> dict:
        if not (1 <= rating <= 5):
            raise HTTPException(status_code=400, detail="Baho 1 dan 5 gacha bo'lishi kerak")
        gr = GuestReview(
            company_id=company_id,
            guest_name=guest_name.strip(),
            rating=rating,
            comment=comment,
        )
        self.db.add(gr)
        await self.db.commit()
        await self.db.refresh(gr)
        return self._guest_to_dict(gr)

    def _guest_to_dict(self, gr: GuestReview) -> dict:
        return {
            "id": f"g{gr.id}",
            "user_name": gr.guest_name,
            "rating": gr.rating,
            "comment": gr.comment,
            "created_at": gr.created_at.isoformat(),
            "is_guest": True,
            "tour_title": None,
        }

    async def list_company_reviews_all(self, company_id: int, limit: int = 50) -> List[dict]:
        """Merge regular + guest reviews, ML-score and rank them."""
        reg_result = await self.db.execute(
            select(Review)
            .options(selectinload(Review.user), selectinload(Review.tour))
            .where(Review.company_id == company_id)
            .order_by(Review.created_at.desc())
            .limit(limit)
        )
        reg_reviews = [self._to_dict(r, r.user) for r in reg_result.scalars().all()]

        guest_result = await self.db.execute(
            select(GuestReview)
            .where(GuestReview.company_id == company_id)
            .order_by(GuestReview.created_at.desc())
            .limit(limit)
        )
        guest_reviews = [self._guest_to_dict(gr) for gr in guest_result.scalars().all()]

        all_reviews = reg_reviews + guest_reviews

        def score(r: dict) -> float:
            created = datetime.fromisoformat(r["created_at"])
            return self._ml_score(r["rating"], r.get("comment"), created)

        all_reviews.sort(key=score, reverse=True)
        return all_reviews[:limit]
