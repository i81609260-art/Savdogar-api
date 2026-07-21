"""Obuna to'lovi o'tib ketgan kompaniyalarni API darajasida bloklash.

Frontend blokidan tashqari — bu server tomonida ishlaydi, shuning uchun
brauzerni chetlab to'g'ridan-to'g'ri API'ga so'rov yuborib ham yangi yozuv
yaratib bo'lmaydi.

Faqat yozuv o'zgartiruvchi so'rovlar (POST/PUT/PATCH/DELETE) tekshiriladi.
Auth, tarif/to'lov va public (tokensiz) so'rovlar tegilmaydi. Har qanday
kutilmagan xatoda so'rov o'tkaziladi (fail-open) — blok ilovani sindirmasligi
kerak.
"""

import logging

from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.database import AsyncSessionLocal
from app.models.company import Company
from app.models.user import User, UserRole
from app.services.billing import compute_billing
from app.services.tariff import DEFAULT_TARIFF, get_tariff
from app.utils.security import decode_token

logger = logging.getLogger(__name__)

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

# Bu prefikslar hech qachon bloklanmaydi — aks holda foydalanuvchi to'lay olmaydi
# yoki tizimga kira olmaydi.
_ALLOW_PREFIXES = (
    "/api/auth",
    "/api/tariff",
    "/api/payments",
    "/api/booking-payments",
    "/api/booking_payments",
    "/uploads",
    "/socket.io",
    "/docs",
    "/openapi",
)


class SubscriptionGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            if not self._should_check(request):
                return await call_next(request)

            token = self._bearer(request)
            if not token:
                # Public (tokensiz) yozuv — masalan mehmon bronlash. Tegmaymiz.
                return await call_next(request)

            payload = decode_token(token)
            if not payload or payload.get("type") != "access":
                return await call_next(request)  # auth qatlami 401 qaytaradi

            user_id = payload.get("sub")
            if not user_id:
                return await call_next(request)

            async with AsyncSessionLocal() as db:
                user = (
                    await db.execute(select(User).where(User.id == int(user_id)))
                ).scalar_one_or_none()
                if not user or user.role == UserRole.SUPERADMIN or not user.company_id:
                    return await call_next(request)

                company = (
                    await db.execute(
                        select(Company).where(Company.id == user.company_id)
                    )
                ).scalar_one_or_none()
                if not company:
                    return await call_next(request)

                plan = get_tariff(getattr(company, "tariff", DEFAULT_TARIFF))
                billing = compute_billing(company, plan)

            if billing["status"] == "overdue":
                return JSONResponse(
                    status_code=402,
                    content={
                        "detail": "Obuna tolovi muddati otgan. Iltimos, tolovni amalga oshiring.",
                        "billing": "overdue",
                    },
                )
        except Exception:  # noqa: BLE001 — blok hech qachon ilovani sindirmasin
            logger.exception("Subscription guard xatosi — so'rov o'tkazildi")

        return await call_next(request)

    @staticmethod
    def _should_check(request: Request) -> bool:
        if request.method not in _MUTATING:
            return False
        path = request.url.path
        return not any(path.startswith(p) for p in _ALLOW_PREFIXES)

    @staticmethod
    def _bearer(request: Request) -> str | None:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            return header[7:].strip()
        return None
