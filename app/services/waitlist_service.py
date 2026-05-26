"""Waitlist business logic."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tour import Tour
from app.models.user import User
from app.models.waitlist import Waitlist
from app.services.notification_service import NotificationService


class WaitlistService:
    def __init__(self, db: AsyncSession, sio=None):
        self.db = db
        self.notifier = NotificationService(db, sio)

    async def join(self, user: User, tour_id: int) -> dict:
        """Add user to waitlist for a fully-booked tour."""
        result = await self.db.execute(select(Tour).where(Tour.id == tour_id))
        tour = result.scalar_one_or_none()
        if not tour:
            raise HTTPException(status_code=404, detail="Tur topilmadi")
        if tour.available_slots > 0:
            raise HTTPException(status_code=400, detail="Turda joy bor, bron qiling")

        existing = await self.db.execute(
            select(Waitlist).where(Waitlist.user_id == user.id, Waitlist.tour_id == tour_id)
        )
        if existing.scalar_one_or_none():
            return {"status": "already_joined"}

        wl = Waitlist(user_id=user.id, tour_id=tour_id, company_id=tour.company_id)
        self.db.add(wl)
        await self.db.commit()
        return {"status": "joined", "tour_id": tour_id}

    async def leave(self, user: User, tour_id: int) -> dict:
        """Remove user from waitlist."""
        result = await self.db.execute(
            select(Waitlist).where(Waitlist.user_id == user.id, Waitlist.tour_id == tour_id)
        )
        wl = result.scalar_one_or_none()
        if not wl:
            raise HTTPException(status_code=404, detail="Navbatda emassiz")
        await self.db.delete(wl)
        await self.db.commit()
        return {"status": "left"}

    async def status(self, user: User, tour_id: int) -> dict:
        """Check if user is on the waitlist."""
        result = await self.db.execute(
            select(Waitlist).where(Waitlist.user_id == user.id, Waitlist.tour_id == tour_id)
        )
        wl = result.scalar_one_or_none()
        return {"in_waitlist": wl is not None}

    async def notify_first(self, tour_id: int) -> None:
        """Notify first un-notified user on waitlist that a slot opened."""
        result = await self.db.execute(
            select(Waitlist)
            .options(selectinload(Waitlist.user), selectinload(Waitlist.tour))
            .where(Waitlist.tour_id == tour_id, Waitlist.notified == False)  # noqa: E712
            .order_by(Waitlist.created_at)
            .limit(1)
        )
        wl = result.scalar_one_or_none()
        if not wl or not wl.user:
            return

        tour_title = wl.tour.title if wl.tour else f"Tur #{tour_id}"
        await self.notifier.create_and_send(
            wl.user,
            "Joy bo'shadi! 🎉",
            f"«{tour_title}» turida joy bo'shadi. Tez bron qiling!",
            "waitlist",
            f"/tours/{tour_id}",
        )
        wl.notified = True
        await self.db.commit()
