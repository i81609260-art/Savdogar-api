"""Payment processing — Click/Payme integrations."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.booking import Booking, BookingStatus
from app.models.user import User

router = APIRouter(prefix="/api/payments", tags=["Payments"])


class PaymentRequest(BaseModel):
    """Payment initialization."""
    booking_id: int
    amount: float


class PaymentResponse(BaseModel):
    """Payment response."""
    success: bool
    message: str
    payment_url: str = None
    error: str = None


@router.post("/click/init", response_model=PaymentResponse, summary="Click to'lov ishga tushirish")
async def init_click_payment(
    data: PaymentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentResponse:
    """Initialize Click payment for booking."""
    result = await db.execute(
        select(Booking).where(Booking.id == data.booking_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Bron topilmadi")

    result = await db.execute(
        select(User).where(User.id == booking.user_id)
    )
    tour_owner = result.scalar_one_or_none()
    if not tour_owner or not tour_owner.click_merchant_id:
        raise HTTPException(status_code=400, detail="Tour egasi Click to'lovni qabul qilmaydi")

    # TODO: Click API ga so'rov yuborish
    payment_url = f"https://click.uz/pay?merchant_id={tour_owner.click_merchant_id}&amount={int(data.amount * 100)}"

    return PaymentResponse(
        success=True,
        message="Click to'lov sahifasiga yo'naltirilmoqda",
        payment_url=payment_url,
    )


@router.post("/payme/init", response_model=PaymentResponse, summary="Payme to'lov ishga tushirish")
async def init_payme_payment(
    data: PaymentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentResponse:
    """Initialize Payme payment for booking."""
    result = await db.execute(
        select(Booking).where(Booking.id == data.booking_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Bron topilmadi")

    result = await db.execute(
        select(User).where(User.id == booking.user_id)
    )
    tour_owner = result.scalar_one_or_none()
    if not tour_owner or not tour_owner.payme_merchant_id:
        raise HTTPException(status_code=400, detail="Tour egasi Payme to'lovni qabul qilmaydi")

    # TODO: Payme API ga so'rov yuborish
    payment_url = f"https://checkout.paycom.uz/?merchant={tour_owner.payme_merchant_id}&amount={int(data.amount * 100)}"

    return PaymentResponse(
        success=True,
        message="Payme to'lov sahifasiga yo'naltirilmoqda",
        payment_url=payment_url,
    )


@router.post("/click/callback", summary="Click callback")
async def click_callback(
    click_trans_id: str = Query(...),
    merchant_trans_id: str = Query(...),
    amount: float = Query(...),
    sign_string: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Handle Click payment callback."""
    # TODO: Signature verification
    # TODO: Update booking status
    return {"success": True, "message": "Callback qabul qilindi"}


@router.post("/payme/callback", summary="Payme callback")
async def payme_callback(
    data: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Handle Payme payment callback."""
    # TODO: Signature verification
    # TODO: Update booking status
    return {"success": True, "message": "Callback qabul qilindi"}
