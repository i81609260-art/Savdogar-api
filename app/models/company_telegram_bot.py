"""Per-company Telegram bot configuration."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.company import Company


class CompanyTelegramBot(Base):
    """Stores Telegram bot token and config for a single company."""

    __tablename__ = "company_telegram_bots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), unique=True, index=True)
    bot_token: Mapped[str] = mapped_column(String(255), unique=True)
    bot_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    webhook_set: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped["Company"] = relationship("Company")
