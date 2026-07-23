"""Foydalanuvchi faolligini belgilash — DAU/MAU hisobi uchun.

Har bir autentifikatsiyalangan so'rovda foydalanuvchining `last_active_at`
vaqtini yangilaydi. Har so'rovda DB'ga yozmaslik uchun xotirada throttle
bor — bir foydalanuvchi uchun ko'pi bilan `_THROTTLE_SECONDS`da bir marta.

Fail-open: har qanday xato so'rovni to'xtatmaydi, faqat faollik yozilmaydi.
"""

import logging
import time

from sqlalchemy import update
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.database import AsyncSessionLocal
from app.models.user import User
from app.utils.security import decode_token

logger = logging.getLogger(__name__)

# Bir foydalanuvchi faolligini shuncha soniyada bir marta yozamiz.
_THROTTLE_SECONDS = 5 * 60

# {user_id: oxirgi yozilgan monotonik vaqt}. Worker'ga xos — ko'p worker bo'lsa
# eng yomon holatda bir necha ortiqcha yozuv bo'ladi, xolos.
_last_write: dict[int, float] = {}


class ActivityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            await self._touch(request)
        except Exception:  # noqa: BLE001 — faollik yozuvi ilovani sindirmasin
            logger.debug("Activity middleware xatosi", exc_info=True)
        return response

    async def _touch(self, request: Request) -> None:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            return
        payload = decode_token(header[7:].strip())
        if not payload or payload.get("type") != "access":
            return
        user_id = payload.get("sub")
        if not user_id:
            return
        user_id = int(user_id)

        now = time.monotonic()
        last = _last_write.get(user_id)
        if last is not None and (now - last) < _THROTTLE_SECONDS:
            return
        _last_write[user_id] = now

        async with AsyncSessionLocal() as db:
            from sqlalchemy import func

            await db.execute(
                update(User)
                .where(User.id == user_id)
                .values(last_active_at=func.now())
            )
            await db.commit()
