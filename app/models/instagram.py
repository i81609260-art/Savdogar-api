"""Instagram (Meta) integratsiya modellari — DM va izohlardan lead yigish."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InstagramAccount(Base):
    """Kompaniyaning ulangan Instagram Business akkaunti.

    Bitta kompaniyaga bitta akkaunt. `ig_user_id` webhook'ni tegishli
    kompaniyaga yonaltirish uchun ishlatiladi, shuning uchun unique.
    """

    __tablename__ = "instagram_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), unique=True, index=True
    )

    # Instagram Business account ID (Facebook Page ga bogliq).
    ig_user_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    ig_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Qaysi yol bilan ulangan: "instagram" (graph.instagram.com) yoki
    # "facebook" (graph.facebook.com). Javob yuborish va obuna uchun kerak.
    login_type: Mapped[str] = mapped_column(String(20), default="instagram")

    # Facebook yolida — bogliq Page. Instagram yolida Page bolmaydi (bosh).
    page_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    page_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Instagram yolida bu Instagram User access token, Facebook yolida Page token.
    page_access_token: Mapped[str] = mapped_column(String(500))

    webhook_subscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InstagramThread(Base):
    """Bitta Instagram foydalanuvchisi bilan suhbat holati.

    Suhbat holati DB da saqlanadi (xotirada emas) — Railway bir nechta worker
    ishga tushirsa ham lead yigish oqimi uzilmaydi. `stage` qaysi malumot
    hali sorаlmaganini bildiradi: name -> phone -> destination -> done.
    """

    __tablename__ = "instagram_threads"
    __table_args__ = (
        UniqueConstraint("company_id", "ig_sender_id", name="uq_ig_thread"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)

    # DM yozayotgan Instagram foydalanuvchisining ID si.
    ig_sender_id: Mapped[str] = mapped_column(String(50), index=True)
    ig_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Yaratilgan pipeline lead (tour_requests.id). Telefon olingach toldiriladi.
    request_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    stage: Mapped[str] = mapped_column(String(20), default="name")

    # Yigilayotgan malumot (lead yaratilgunga qadar).
    lead_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    lead_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
