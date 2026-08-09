"""Tour package ORM model."""

from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import event, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.company import Company
    from app.models.tour_group import TourGroup


class Tour(Base):
    """Tour package offered by a company."""

    __tablename__ = "tours"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text)
    # Borish joyi.
    city: Mapped[str] = mapped_column(String(100), index=True)
    # Jo'nash shahri. Bo'sh bo'lsa firmaning shahri olinadi — turlarning
    # aksariyati agentlik joylashgan shahardan jo'naydi, shuning uchun uni
    # har turda qayta yozdirish ortiqcha ish bo'lardi.
    departure_city: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    country: Mapped[str] = mapped_column(String(100), default="Uzbekistan")
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="UZS")
    # Saralash va narx filtri UCHUN so'mga o'girilgan qiymat.
    #
    # `price` ning o'zi bilan solishtirib bo'lmaydi: u oddiy son, valyuta
    # esa alohida ustunda. Shu sababli 10 001 EUR (≈137 mln so'm) 12 mln
    # so'mlik turdan "arzonroq" bo'lib chiqardi.
    #
    # Ko'rsatishda ISHLATILMAYDI — mijoz asl valyutani ko'radi ("10 001 €").
    # Kurs o'zgarsa bu qiymat eskiradi: u buxgalteriya uchun emas,
    # TARTIBLASH uchun mo'ljallangan.
    price_uzs: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, index=True
    )
    duration_days: Mapped[int] = mapped_column(Integer, default=1)
    # Dates are optional — a tour may have "flexible / to be agreed" dates.
    start_date: Mapped[Optional[date]] = mapped_column(Date, index=True, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    available_slots: Mapped[int] = mapped_column(Integer)
    # Which branch offers this tour; null = shared across all branches.
    branch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("branches.id"), nullable=True, index=True
    )
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    booking_type: Mapped[str] = mapped_column(String(20), default="group")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship("Company", back_populates="tours")
    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="tour")
    groups: Mapped[list["TourGroup"]] = relationship("TourGroup", back_populates="tour")


# --------------------------------------------------------------------------
# `price_uzs` ni avtomatik hisoblash
# --------------------------------------------------------------------------
# Bu hisob ATAYLAB modelga bog'langan, servisga emas.
#
# Ilgari u faqat `TourService.create_tour` ichida edi va tur boshqa yo'l
# bilan yaratilsa (import skripti, sinov fikstursi, kelajakdagi yangi kod)
# `price_uzs` NULL bo'lib qolardi. Bunday tur saralashda ro'yxat oxiriga
# tushib ketardi va buni sezish qiyin — xato jimgina bo'lardi.
#
# Tinglovchi SINXRON: `to_uzs` keshdagi kursdan foydalanadi va tarmoqqa
# chiqmaydi, shuning uchun yozish amali sekinlashmaydi.
@event.listens_for(Tour, "before_insert")
@event.listens_for(Tour, "before_update")
def _hisobla_price_uzs(mapper, connection, target: "Tour") -> None:  # noqa: ARG001
    from app.services.currency import to_uzs

    target.price_uzs = to_uzs(target.price, target.currency)
