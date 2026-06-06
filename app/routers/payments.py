"""Payment processing — Click/Payme integrations."""

import asyncio
import aiohttp
import base64
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


class ValidationRequest(BaseModel):
    """Payment credentials validation."""
    merchant_id: str
    merchant_key: str = None
    api_key: str = None


class ValidationResponse(BaseModel):
    """Validation result."""
    success: bool
    message: str
    details: str = None


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

    # Fetch tour to verify company
    result = await db.execute(
        select(Booking.user_id).where(Booking.id == data.booking_id)
    )
    tour_owner_id = result.scalar_one_or_none()

    result = await db.execute(
        select(User).where(User.id == tour_owner_id)
    )
    tour_owner = result.scalar_one_or_none()
    if not tour_owner or not tour_owner.payme_merchant_id:
        raise HTTPException(status_code=400, detail="Tour egasi Payme to'lovni qabul qilmaydi")

    # Amount in tiyn (1 USD = 12,500 UZS approximately, stored as tiyn in Payme)
    amount_tiyn = int(data.amount * 100)  # Convert to cents for Payme

    # Create Payme checkout URL with proper parameters
    payment_url = (
        f"https://checkout.paycom.uz/"
        f"?account[user_id]={current_user.id}"
        f"&account[booking_id]={booking.id}"
        f"&merchant_id={tour_owner.payme_merchant_id}"
        f"&amount={amount_tiyn}"
        f"&return_url=https://savdogar.vercel.app/my-bookings"
    )

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


@router.post("/click/validate", response_model=ValidationResponse, summary="Click credentials validate")
async def validate_click_credentials(
    data: ValidationRequest,
    current_user: User = Depends(get_current_user),
) -> ValidationResponse:
    """Validate Click merchant credentials."""
    if not data.merchant_id or not data.merchant_key:
        raise HTTPException(status_code=400, detail="Merchant ID va Key talab qilinadi")

    try:
        async with aiohttp.ClientSession() as session:
            auth_header = base64.b64encode(
                f"{data.merchant_id}:{data.merchant_key}".encode()
            ).decode()

            async with session.post(
                "https://api.click.uz/v2/merchant/check/user",
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/json",
                },
                json={"phone_number": "998901234567"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return ValidationResponse(
                        success=True,
                        message="✅ Click hisobi muvaffaqiyatli ulandi!",
                        details="Merchant ID va Secret Key to'g'ri",
                    )
                elif resp.status == 401:
                    return ValidationResponse(
                        success=False,
                        message="❌ Merchant ID yoki Secret Key noto'g'ri",
                        details="Click bilan ulanib bo'lmadi — ma'lumotlarni tekshiring",
                    )
                else:
                    return ValidationResponse(
                        success=False,
                        message=f"❌ Click xatosi: {resp.status}",
                        details="Keyinroq qayta urinib ko'ring",
                    )
    except asyncio.TimeoutError:
        return ValidationResponse(
            success=False,
            message="❌ Ulanish timeout",
            details="Click serverlariga ulanib bo'lmadi",
        )
    except Exception as e:
        return ValidationResponse(
            success=False,
            message="❌ Tekshirishda xatolik",
            details=str(e),
        )


@router.post("/payme/validate", response_model=ValidationResponse, summary="Payme credentials validate")
async def validate_payme_credentials(
    data: ValidationRequest,
    current_user: User = Depends(get_current_user),
) -> ValidationResponse:
    """Validate Payme merchant credentials."""
    if not data.merchant_id or not data.api_key:
        raise HTTPException(status_code=400, detail="Merchant ID va API Key talab qilinadi")

    try:
        async with aiohttp.ClientSession() as session:
            auth_header = base64.b64encode(
                f"{data.merchant_id}:{data.api_key}".encode()
            ).decode()

            async with session.post(
                "https://checkout.paycom.uz/api/",
                headers={
                    "X-Auth": auth_header,
                    "Content-Type": "application/json",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "CheckPerformTransaction",
                    "params": {
                        "account": {
                            "user_id": "999"
                        },
                        "amount": 1000,
                    }
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if "error" in result and result["error"] is not None:
                        if result["error"].get("code") == -32504:
                            return ValidationResponse(
                                success=True,
                                message="✅ Payme hisobi muvaffaqiyatli ulandi!",
                                details="Merchant ID va API Key to'g'ri",
                            )
                        else:
                            return ValidationResponse(
                                success=False,
                                message="❌ Payme xatosi",
                                details=result["error"].get("message", "Noma'lum xato"),
                            )
                    return ValidationResponse(
                        success=True,
                        message="✅ Payme hisobi muvaffaqiyatli ulandi!",
                        details="Merchant ID va API Key to'g'ri",
                    )
                else:
                    return ValidationResponse(
                        success=False,
                        message=f"❌ Payme xatosi: {resp.status}",
                        details="Keyinroq qayta urinib ko'ring",
                    )
    except asyncio.TimeoutError:
        return ValidationResponse(
            success=False,
            message="❌ Ulanish timeout",
            details="Payme serverlariga ulanib bo'lmadi",
        )
    except Exception as e:
        return ValidationResponse(
            success=False,
            message="❌ Tekshirishda xatolik",
            details=str(e),
        )
