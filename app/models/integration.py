"""SAIR va boshqa tashqi platformalar integratsiya modellari."""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IntegrationProvider(str, enum.Enum):
    """Tashqi integratsiya provayderi."""

    SAIR = "sair"


class IntegrationStatus(str, enum.Enum):
    """Savdogar ↔ SAIR ulanish holati."""

    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    DISABLED = "disabled"


class IntegrationConfig(Base):
    """Savdogar kompaniyasining SAIR integratsiya sozlamalari."""

    __tablename__ = "integration_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), unique=True, index=True)
    provider: Mapped[IntegrationProvider] = mapped_column(
        Enum(IntegrationProvider), default=IntegrationProvider.SAIR
    )
    status: Mapped[IntegrationStatus] = mapped_column(
        Enum(IntegrationStatus), default=IntegrationStatus.PENDING
    )
    sayr_company_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sayr_api_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExternalTourMapping(Base):
    """SAIR tur ID ↔ Savdogar tur ID bog'lanishi."""

    __tablename__ = "external_tour_mappings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    tour_id: Mapped[int] = mapped_column(ForeignKey("tours.id"), index=True)
    provider: Mapped[IntegrationProvider] = mapped_column(Enum(IntegrationProvider))
    external_tour_id: Mapped[str] = mapped_column(String(100), index=True)
    external_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_synced: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IntegrationEvent(Base):
    """SAIR webhook va sync hodisalari jurnali."""

    __tablename__ = "integration_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.id"), nullable=True)
    provider: Mapped[IntegrationProvider] = mapped_column(Enum(IntegrationProvider))
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[str] = mapped_column(Text)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PosSaleNotification(Base):
    """SAYR orqali sotuv — Savdogar CRM/POS ga kelgan xabar."""

    __tablename__ = "pos_sale_notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    booking_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bookings.id"), nullable=True)
    external_booking_id: Mapped[str] = mapped_column(String(100), index=True)
    external_user_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    external_user_name: Mapped[str] = mapped_column(String(255))
    external_user_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tour_title: Mapped[str] = mapped_column(String(255))
    total_price: Mapped[float] = mapped_column()
    guests_count: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(50), default="sayr")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
