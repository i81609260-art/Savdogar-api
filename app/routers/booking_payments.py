"""Booking payment processing and management."""

import hashlib
import hmac
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from pydantic import BaseModel

router = APIRouter(prefix="/api/payments", tags=["Payments"])


class PaymentMethodsResponse(BaseModel):
    """Payment methods available for company."""

    click_enabled: bool
    payme_enabled: bool
    card_enabled: bool


class CreatePaymentData(BaseModel):
    """Create payment request."""

    booking_id: int
    amount: float
    payment_method: str  # click, payme, card


class PaymentStatusUpdate(BaseModel):
    """Payment status update."""

    booking_id: int
    status: str  # success, failed, pending
    transaction_id: Optional[str] = None
    error_message: Optional[str] = None


@router.get("/{booking_id}/methods", summary="To'lov usullari")
async def get_payment_methods(
    booking_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get available payment methods for booking."""
    from app.models.booking import Booking

    result = await db.execute(
        select(Booking).where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(status_code=404, detail="Bron topilmadi")

    if booking.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")

    # Check company payment methods
    result = await db.execute(
        select(User).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()

    return {
        "click_enabled": bool(user.click_merchant_id),
        "payme_enabled": bool(user.payme_merchant_id),
        "card_enabled": True,
    }


@router.post("/click/init", summary="Click to'lovini boshlash")
async def init_click_payment(
    data: CreatePaymentData,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Initialize Click payment."""
    from app.models.booking import Booking

    result = await db.execute(
        select(Booking).where(Booking.id == data.booking_id)
    )
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(status_code=404, detail="Bron topilmadi")

    # Create payment record
    result = await db.execute(
        select(User).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()

    if not user.click_merchant_id:
        raise HTTPException(status_code=400, detail="Click to'lov sozlanmagan")

    # Generate Click payment token (simplified)
    payment_id = f"click_{data.booking_id}_{int(__import__('time').time())}"

    return {
        "payment_id": payment_id,
        "amount": data.amount,
        "status": "pending",
        "redirect_url": f"https://my.click.uz/pay/{user.click_merchant_id}",
    }


@router.post("/payme/init", summary="Payme to'lovini boshlash")
async def init_payme_payment(
    data: CreatePaymentData,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Initialize Payme payment."""
    from app.models.booking import Booking

    result = await db.execute(
        select(Booking).where(Booking.id == data.booking_id)
    )
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(status_code=404, detail="Bron topilmadi")

    result = await db.execute(
        select(User).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()

    if not user.payme_merchant_id:
        raise HTTPException(status_code=400, detail="Payme to'lov sozlanmagan")

    # Generate Payme payment token (simplified)
    payment_id = f"payme_{data.booking_id}_{int(__import__('time').time())}"

    return {
        "payment_id": payment_id,
        "amount": data.amount,
        "status": "pending",
        "checkout_url": f"https://checkout.paymeuz.com/?account={user.payme_merchant_id}",
    }


@router.post("/webhook/click", summary="Click webhook")
async def handle_click_webhook(
    data: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Handle Click payment webhook."""
    from app.models.booking import Booking

    booking_id = data.get("merchant_trans_id")
    if not booking_id:
        return {"error": "Invalid webhook"}

    result = await db.execute(
        select(Booking).where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()

    if booking and data.get("status") == "success":
        booking.status = "completed"
        booking.paid_at = __import__("datetime").datetime.utcnow()
        await db.commit()

        return {
            "success": True,
            "message": "To'lov qabul qilindi",
        }

    return {"success": False, "message": "To'lov amalga oshmadi"}


@router.post("/webhook/payme", summary="Payme webhook")
async def handle_payme_webhook(
    data: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Handle Payme payment webhook."""
    from app.models.booking import Booking

    # Payme webhook processing
    account = data.get("account", {})
    booking_id = account.get("booking_id")

    if not booking_id:
        return {"error": "Invalid webhook"}

    result = await db.execute(
        select(Booking).where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()

    if booking and data.get("result", {}).get("state") == 4:  # Paid
        booking.status = "completed"
        booking.paid_at = __import__("datetime").datetime.utcnow()
        await db.commit()

        return {"result": {"state": 4}}

    return {"result": {"state": 1}}
