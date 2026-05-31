"""Tour company ORM model."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.tour import Tour
    from app.models.user import User


class CompanyStatus(str, enum.Enum):
    """Company approval workflow status."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CompanyType(str, enum.Enum):
    """Business model type — drives which UI is shown on the public page."""

    MULTI = "multi"              # Many distinct tour packages (Turkiya, Dubay, Misr…)
    SINGLE_DIRECTION = "single_direction"  # One direction, many departure dates (Umra, Haj…)


class Company(Base):
    """Tour agency company registered on SAIR."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    slug: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    custom_domain: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(255))
    status: Mapped[CompanyStatus] = mapped_column(
        Enum(CompanyStatus), default=CompanyStatus.PENDING
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sair_integrated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    company_type: Mapped[CompanyType] = mapped_column(
        Enum(CompanyType), default=CompanyType.MULTI, nullable=True
    )
    owner_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    users: Mapped[list["User"]] = relationship(
        "User", back_populates="company", foreign_keys="User.company_id"
    )
    tours: Mapped[list["Tour"]] = relationship("Tour", back_populates="company")
