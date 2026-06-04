"""User and authentication-related ORM models."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.company import Company
    from app.models.notification import Notification


class UserRole(str, enum.Enum):
    """Platform user roles."""

    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"


class User(Base):
    """Platform user account."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id"), nullable=True
    )
    push_subscription: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    click_merchant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    click_merchant_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payme_merchant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payme_api_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped[Optional["Company"]] = relationship(
        "Company", back_populates="users", foreign_keys=[company_id]
    )
    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="user")
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user"
    )

    @property
    def company_status(self) -> Optional[str]:
        """Get the status of the associated company safely without lazy loading."""
        if "company" in self.__dict__ and self.company:
            return self.company.status.value
        return None

    @property
    def company_sair_integrated(self) -> Optional[bool]:
        """Get SAIR integration status of the associated company."""
        if "company" in self.__dict__ and self.company:
            return bool(self.company.sair_integrated)
        return False


class RefreshTokenBlacklist(Base):
    """Blacklisted refresh tokens after logout."""

    __tablename__ = "refresh_token_blacklist"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token_jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
