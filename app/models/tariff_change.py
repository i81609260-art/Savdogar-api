"""Log of company subscription-plan switches (for the superadmin view)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TariffChange(Base):
    """One row per plan switch — who moved from which plan to which."""

    __tablename__ = "tariff_changes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    company_name: Mapped[str] = mapped_column(String(255))
    from_tariff: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_tariff: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
