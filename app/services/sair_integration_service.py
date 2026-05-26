"""SAYR platformasi bilan API integratsiya xizmati."""

import hashlib
import hmac
import json
import logging
from datetime import date
from typing import Any, Optional

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.booking import Booking, BookingStatus
from app.models.company import Company, CompanyStatus
from app.models.integration import (
    ExternalTourMapping,
    IntegrationConfig,
    IntegrationEvent,
    IntegrationProvider,
    IntegrationStatus,
    PosSaleNotification,
)
from app.models.notification import Notification
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.utils.security import hash_password

logger = logging.getLogger(__name__)
settings = get_settings()


class SairIntegrationService:
    """SAYR API client, webhook va CRM/POS bildirishnomalar."""

    def __init__(self, db: AsyncSession, sio=None):
        """Initialize with DB session and optional Socket.io."""
        self.db = db
        self.sio = sio

    def verify_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """HMAC-SHA256 webhook imzosini tekshirish."""
        if not secret or not signature:
            return False
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature.replace("sha256=", ""))

    async def log_event(
        self,
        event_type: str,
        payload: dict,
        company_id: Optional[int] = None,
        processed: bool = False,
        error: Optional[str] = None,
    ) -> IntegrationEvent:
        """Integratsiya hodisasini jurnalga yozish."""
        event = IntegrationEvent(
            company_id=company_id,
            provider=IntegrationProvider.SAYR,
            event_type=event_type,
            payload=json.dumps(payload, ensure_ascii=False),
            processed=processed,
            error_message=error,
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def handle_webhook(
        self,
        event_type: str,
        data: dict,
        signature: Optional[str] = None,
        raw_body: Optional[bytes] = None,
    ) -> dict:
        """SAYR dan kelgan webhookni qayta ishlash."""
        company_id = data.get("savdogar_company_id") or data.get("company_id")
        secret = settings.sayr_webhook_secret

        if secret and signature and raw_body:
            if not self.verify_webhook_signature(raw_body, signature, secret):
                raise HTTPException(status_code=401, detail="Webhook imzosi noto'g'ri")

        handlers = {
            "integration.approved": self._on_integration_approved,
            "integration.rejected": self._on_integration_rejected,
            "user.provisioned": self._on_user_provisioned,
            "booking.created": self._on_booking_created,
            "booking.confirmed": self._on_booking_confirmed,
            "tour.sync": self._on_tour_sync,
        }

        handler = handlers.get(event_type)
        if not handler:
            await self.log_event(event_type, data, company_id, processed=False, error="Noma'lum event")
            return {"message": "Event qabul qilindi, handler yo'q"}

        try:
            result = await handler(data)
            await self.log_event(event_type, data, company_id, processed=True)
            return result
        except Exception as exc:
            logger.exception("SAYR webhook xato: %s", exc)
            await self.log_event(event_type, data, company_id, processed=False, error=str(exc))
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    async def _on_integration_approved(self, data: dict) -> dict:
        """SAYR superadmin Savdogar integratsiyasini tasdiqlaganda."""
        company_id = int(data["savdogar_company_id"])
        result = await self.db.execute(
            select(IntegrationConfig).where(IntegrationConfig.company_id == company_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            config = IntegrationConfig(company_id=company_id, provider=IntegrationProvider.SAYR)
            self.db.add(config)

        config.status = IntegrationStatus.ACTIVE
        config.sayr_company_id = str(data.get("sayr_company_id", ""))
        config.sayr_api_key = data.get("api_key")

        company_result = await self.db.execute(select(Company).where(Company.id == company_id))
        company = company_result.scalar_one_or_none()
        if company:
            company.status = CompanyStatus.APPROVED

        await self._notify_company_admins(
            company_id,
            "SAYR integratsiyasi faollashdi",
            "SAYR platformasi Savdogar bilan muvaffaqiyatli ulandi. Turlar sinxronlanadi.",
        )
        return {"message": "Integratsiya faollashtirildi", "company_id": company_id}

    async def _on_integration_rejected(self, data: dict) -> dict:
        """SAYR integratsiyani rad etganda."""
        company_id = int(data["savdogar_company_id"])
        result = await self.db.execute(
            select(IntegrationConfig).where(IntegrationConfig.company_id == company_id)
        )
        config = result.scalar_one_or_none()
        if config:
            config.status = IntegrationStatus.REJECTED
        return {"message": "Integratsiya rad etildi"}

    async def _on_user_provisioned(self, data: dict) -> dict:
        """SAYR da user yaratilganda Savdogarda ham avtomatik user."""
        email = data["email"]
        existing = await self.db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            return {"message": "User allaqachon mavjud", "email": email}

        company_id = data.get("savdogar_company_id")
        user = User(
            email=email,
            hashed_password=hash_password(data.get("temp_password", "ChangeMe123!")),
            full_name=data.get("full_name", "SAYR User"),
            phone=data.get("phone"),
            role=UserRole(data.get("role", "user")),
            company_id=int(company_id) if company_id else None,
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()
        return {"message": "User yaratildi", "user_id": user.id, "email": email}

    async def _on_booking_created(self, data: dict) -> dict:
        """SAYR da bron qilinganda — Savdogar CRM/POS ga xabar."""
        return await self._create_pos_notification(data, BookingStatus.PENDING)

    async def _on_booking_confirmed(self, data: dict) -> dict:
        """SAYR da bron tasdiqlanganda."""
        return await self._create_pos_notification(data, BookingStatus.CONFIRMED)

    async def _create_pos_notification(self, data: dict, status: BookingStatus) -> dict:
        """CRM/POS sotuv bildirishnomasi va ichki bron."""
        company_id = int(data["savdogar_company_id"])
        external_booking_id = str(data["booking_id"])
        tour_title = data.get("tour_title", "SAYR tur")
        user_name = data.get("user_name", "Noma'lum")
        user_email = data.get("user_email")
        total_price = float(data.get("total_price", 0))
        guests = int(data.get("guests_count", 1))

        pos = PosSaleNotification(
            company_id=company_id,
            external_booking_id=external_booking_id,
            external_user_id=str(data.get("user_id", "")),
            external_user_name=user_name,
            external_user_email=user_email,
            tour_title=tour_title,
            total_price=total_price,
            guests_count=guests,
            source="sayr",
        )
        self.db.add(pos)
        await self.db.flush()

        local_user_id = None
        if user_email:
            ur = await self.db.execute(select(User).where(User.email == user_email))
            u = ur.scalar_one_or_none()
            if u:
                local_user_id = u.id

        tour_id = None
        ext_tour_id = str(data.get("tour_id", ""))
        if ext_tour_id:
            tr = await self.db.execute(
                select(ExternalTourMapping).where(
                    ExternalTourMapping.external_tour_id == ext_tour_id,
                    ExternalTourMapping.company_id == company_id,
                )
            )
            mapping = tr.scalar_one_or_none()
            if mapping:
                tour_id = mapping.tour_id

        if local_user_id and tour_id:
            booking = Booking(
                user_id=local_user_id,
                tour_id=tour_id,
                company_id=company_id,
                status=status,
                guests_count=guests,
                total_price=total_price,
                notes=f"SAYR bron #{external_booking_id}",
            )
            self.db.add(booking)
            await self.db.flush()
            pos.booking_id = booking.id

        status_uz = "sotib oldi" if status == BookingStatus.CONFIRMED else "bron qildi (kutilmoqda)"
        await self._notify_company_admins(
            company_id,
            f"SAYR: {user_name} {status_uz}",
            f"«{tour_title}» — {guests} mehmon, {total_price:,.0f} so'm. Manba: SAYR",
            link="/admin/bookings",
            notif_type="pos_sale",
        )

        if self.sio:
            await self.sio.emit(
                "pos_sale",
                {
                    "id": pos.id,
                    "user_name": user_name,
                    "tour_title": tour_title,
                    "total_price": total_price,
                    "source": "sayr",
                },
                room=f"company_{company_id}",
            )

        return {
            "message": "CRM/POS xabari yaratildi",
            "pos_notification_id": pos.id,
        }

    async def _on_tour_sync(self, data: dict) -> dict:
        """SAYR dan tur paket sinxronlash."""
        company_id = int(data["savdogar_company_id"])
        tours_data = data.get("tours", [])
        synced = 0

        def _parse_date(val: Any) -> date:
            if isinstance(val, date):
                return val
            return date.fromisoformat(str(val)[:10])

        for t in tours_data:
            ext_id = str(t["id"])
            tr = await self.db.execute(
                select(ExternalTourMapping).where(
                    ExternalTourMapping.external_tour_id == ext_id,
                    ExternalTourMapping.company_id == company_id,
                )
            )
            mapping = tr.scalar_one_or_none()

            if mapping:
                tour_r = await self.db.execute(select(Tour).where(Tour.id == mapping.tour_id))
                tour = tour_r.scalar_one_or_none()
                if tour:
                    tour.title = t.get("title", tour.title)
                    tour.price = float(t.get("price", tour.price))
                    tour.available_slots = int(t.get("available_slots", tour.available_slots))
                    synced += 1
            else:
                tour = Tour(
                    company_id=company_id,
                    title=t["title"],
                    description=t.get("description", ""),
                    city=t.get("city", ""),
                    country=t.get("country", "Uzbekistan"),
                    price=float(t["price"]),
                    duration_days=int(t.get("duration_days", 1)),
                    start_date=_parse_date(t["start_date"]),
                    end_date=_parse_date(t["end_date"]),
                    available_slots=int(t.get("available_slots", 10)),
                    image_url=t.get("image_url"),
                )
                self.db.add(tour)
                await self.db.flush()
                self.db.add(
                    ExternalTourMapping(
                        company_id=company_id,
                        tour_id=tour.id,
                        provider=IntegrationProvider.SAYR,
                        external_tour_id=ext_id,
                        external_title=t["title"],
                    )
                )
                synced += 1

        config_r = await self.db.execute(
            select(IntegrationConfig).where(IntegrationConfig.company_id == company_id)
        )
        config = config_r.scalar_one_or_none()
        if config:
            from datetime import datetime, timezone

            config.last_sync_at = datetime.now(timezone.utc)

        return {"message": f"{synced} tur sinxronlandi", "synced": synced}

    async def _notify_company_admins(
        self,
        company_id: int,
        title: str,
        message: str,
        link: Optional[str] = None,
        notif_type: str = "integration",
    ) -> None:
        """Kompaniya adminlariga ichki bildirishnoma."""
        result = await self.db.execute(
            select(User).where(
                User.company_id == company_id,
                User.role.in_([UserRole.ADMIN, UserRole.OPERATOR]),
                User.is_active == True,  # noqa: E712
            )
        )
        for admin in result.scalars().all():
            n = Notification(
                user_id=admin.id,
                title=title,
                message=message,
                type=notif_type,
                link=link,
            )
            self.db.add(n)
            if self.sio:
                await self.sio.emit(
                    "notification",
                    {"title": title, "message": message, "type": notif_type, "link": link},
                    room=f"user_{admin.id}",
                )

    async def request_sair_integration(self, company_id: int) -> dict:
        """Savdogar SAYR ga integratsiya arizasi yuboradi."""
        result = await self.db.execute(
            select(IntegrationConfig).where(IntegrationConfig.company_id == company_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            config = IntegrationConfig(
                company_id=company_id,
                provider=IntegrationProvider.SAYR,
                status=IntegrationStatus.PENDING,
            )
            self.db.add(config)
        else:
            config.status = IntegrationStatus.PENDING

        if settings.sayr_api_url and settings.sayr_api_key:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        f"{settings.sayr_api_url.rstrip('/')}/api/integrations/savdogar/register",
                        json={
                            "savdogar_company_id": company_id,
                            "webhook_url": f"{settings.savdogar_public_url.rstrip('/')}/api/integrations/sayr/webhook",
                        },
                        headers={"Authorization": f"Bearer {settings.sayr_api_key}"},
                    )
                    if resp.status_code < 400:
                        body = resp.json()
                        config.sayr_company_id = str(body.get("sayr_company_id", ""))
            except Exception as exc:
                logger.warning("SAYR API ulanmadi (mock rejim): %s", exc)

        return {
            "message": "SAYR ga integratsiya arizasi yuborildi",
            "status": config.status.value,
        }

    async def get_integration_status(self, company_id: int) -> dict:
        """Kompaniya integratsiya holati."""
        result = await self.db.execute(
            select(IntegrationConfig).where(IntegrationConfig.company_id == company_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return {"provider": "sayr", "status": "not_configured"}

        pos_count = await self.db.execute(
            select(PosSaleNotification).where(
                PosSaleNotification.company_id == company_id,
                PosSaleNotification.is_read == False,  # noqa: E712
            )
        )
        unread = len(pos_count.scalars().all())

        return {
            "provider": config.provider.value,
            "status": config.status.value,
            "sayr_company_id": config.sayr_company_id,
            "last_sync_at": config.last_sync_at.isoformat() if config.last_sync_at else None,
            "unread_pos_sales": unread,
        }

    async def list_pos_notifications(self, company_id: int) -> list[dict]:
        """CRM/POS SAYR sotuvlari ro'yxati."""
        result = await self.db.execute(
            select(PosSaleNotification)
            .where(PosSaleNotification.company_id == company_id)
            .order_by(PosSaleNotification.created_at.desc())
            .limit(50)
        )
        return [
            {
                "id": p.id,
                "external_booking_id": p.external_booking_id,
                "user_name": p.external_user_name,
                "user_email": p.external_user_email,
                "tour_title": p.tour_title,
                "total_price": p.total_price,
                "guests_count": p.guests_count,
                "source": p.source,
                "is_read": p.is_read,
                "created_at": p.created_at.isoformat(),
            }
            for p in result.scalars().all()
        ]
