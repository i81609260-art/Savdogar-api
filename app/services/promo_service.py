"""Promo code validation and discount logic."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.promo import PromoCode


class PromoService:
    """Handle promo code validation and discount calculation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def validate_code(
        self,
        code: str,
        booking_amount: float,
        tour_id: Optional[int] = None,
    ) -> dict:
        """Validate promo code and calculate discount."""
        result = await self.db.execute(
            select(PromoCode).where(PromoCode.code == code.upper())
        )
        promo = result.scalar_one_or_none()

        if not promo:
            return {
                "valid": False,
                "message": "Promo kod topilmadi",
                "discount_amount": 0,
                "final_amount": booking_amount,
            }

        # Check if active
        if not promo.is_active:
            return {
                "valid": False,
                "message": "Bu promo kod faol emas",
                "discount_amount": 0,
                "final_amount": booking_amount,
            }

        # Check date validity
        now = datetime.now(timezone.utc)
        if promo.valid_until and promo.valid_until < now:
            return {
                "valid": False,
                "message": "Bu promo kod muddati tugagan",
                "discount_amount": 0,
                "final_amount": booking_amount,
            }

        # Check usage limit
        if promo.max_uses and promo.used_count >= promo.max_uses:
            return {
                "valid": False,
                "message": "Bu promo kod ishlatilish chegarasi tugagan",
                "discount_amount": 0,
                "final_amount": booking_amount,
            }

        # Check minimum amount
        if booking_amount < promo.min_booking_amount:
            return {
                "valid": False,
                "message": f"Minimal buyurtma summasi {promo.min_booking_amount:,.0f} so'm bo'lishi kerak",
                "discount_amount": 0,
                "final_amount": booking_amount,
            }

        # Check tour applicability
        if promo.tour_ids:
            tour_ids = [int(t.strip()) for t in promo.tour_ids.split(",")]
            if tour_id and tour_id not in tour_ids:
                return {
                    "valid": False,
                    "message": "Bu promo kod bu turga qo'llanmaydi",
                    "discount_amount": 0,
                    "final_amount": booking_amount,
                }

        # Calculate discount
        discount = 0
        if promo.discount_percent > 0:
            discount = booking_amount * (promo.discount_percent / 100)
        elif promo.discount_amount:
            discount = min(promo.discount_amount, booking_amount)

        final_amount = max(0, booking_amount - discount)

        return {
            "valid": True,
            "message": "Promo kod qabul qilindi",
            "discount_amount": discount,
            "final_amount": final_amount,
            "promo_id": promo.id,
        }

    async def apply_code(self, promo_id: int) -> None:
        """Increment usage count when code is applied."""
        result = await self.db.execute(
            select(PromoCode).where(PromoCode.id == promo_id)
        )
        promo = result.scalar_one_or_none()
        if promo:
            promo.used_count += 1
            self.db.add(promo)
            await self.db.flush()
