"""Notification creation and delivery service."""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User
from app.utils.push_notify import send_web_push


class NotificationService:
    """Handles in-app, socket, and web push notifications."""

    def __init__(self, db: AsyncSession, sio=None):
        """Initialize with database session and optional Socket.io server."""
        self.db = db
        self.sio = sio

    async def create_and_send(
        self,
        user: User,
        title: str,
        message: str,
        notif_type: str = "info",
        link: Optional[str] = None,
    ) -> Notification:
        """Persist notification and push via Socket.io + Web Push."""
        notification = Notification(
            user_id=user.id,
            title=title,
            message=message,
            type=notif_type,
            link=link,
        )
        self.db.add(notification)
        await self.db.flush()
        await self.db.refresh(notification)

        if self.sio:
            await self.sio.emit(
                "notification",
                {
                    "id": notification.id,
                    "title": title,
                    "message": message,
                    "type": notif_type,
                    "link": link,
                    "created_at": notification.created_at.isoformat(),
                },
                room=f"user_{user.id}",
            )

        if user.push_subscription:
            await send_web_push(
                user.push_subscription,
                title,
                message,
                link,
            )

        return notification

    async def notify_company_staff(
        self,
        company_id: int,
        title: str,
        message: str,
        notif_type: str = "info",
        link: Optional[str] = None,
        roles: Optional[list] = None,
    ) -> None:
        """Send notification to all active staff of a company."""
        from sqlalchemy import select

        from app.models.user import User, UserRole

        allowed = roles or [UserRole.ADMIN, UserRole.OPERATOR]
        result = await self.db.execute(
            select(User).where(
                User.company_id == company_id,
                User.is_active == True,  # noqa: E712
            )
        )
        staff = result.scalars().all()
        for member in staff:
            if member.role in allowed:
                await self.create_and_send(member, title, message, notif_type, link)
