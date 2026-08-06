"""Qidiruv va topilgan tur takliflari — hammasi turagent bo'yicha ajratilgan.

`company_id` ikkala jadvalda ham MAJBURIY. Sabab shunchaki tartib emas:
narx turagentga bog'liq. Bir xil mehmonxona, bir xil sana uchun operator har
turagentga o'z shartnomasiga qarab boshqa narx va boshqa komissiya beradi.
Ya'ni bir agentning natijasini boshqasiga ko'rsatish — noto'g'ri narx
ko'rsatish demakdir.

O'chirish siyosati
------------------
Eskirgan takliflar **o'chirilmaydi**, faqat `expires_at` bo'yicha filtrlanadi.
Ikki sabab:
  1. Ma'lumot yo'qotmaslik qoidasi.
  2. To'plangan narx tarixi — vaqt o'tib bu platformaning eng qimmatli
     aktiviga aylanadi: bironta turagentda bunday baza yo'q.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OfferSource(StrEnum):
    """Taklif qaysi kanaldan keldi — ishonchlilikni baholashda ishlatiladi."""

    RPA = "rpa"                # konnektor B2B kabinetdan oldi
    EXTENSION = "extension"    # agent brauzeridagi kengaytma tutdi
    PRICELIST = "pricelist"    # Telegram/email price-list dan tahlil qilindi
    RFQ = "rfq"                # operatorga so'rov yuborilib, javobi tahlil qilindi
    CABINET = "cabinet"        # operator o'zi Savdogarga yukladi
    MANUAL = "manual"          # agent qo'lda kiritdi


class SearchStatus(StrEnum):
    RUNNING = "qidirilmoqda"
    DONE = "tugadi"
    FAILED = "xato"
    CANCELLED = "bekor_qilindi"


class OperatorSearch(Base):
    """Bitta qidiruv seansi — "18 tasini birdan qidir" bosilganda yaratiladi."""

    __tablename__ = "operator_searches"
    __table_args__ = (
        Index("ix_searches_company_created", "company_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # MAJBURIY — qidiruv aniq bir turagentniki.
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # Qaysi so'rovdan kelib chiqqan (CRM bilan bog'lash uchun).
    request_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- Qidiruv shartlari ---
    destination: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    date_from: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    date_to: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    nights: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    adults: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    children: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    star: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    board: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    price_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), default=SearchStatus.RUNNING, nullable=False
    )
    # Har operator holati: {"coral": {"status": "ok", "count": 12}, ...}
    # Socket.IO orqali jonli yangilanadi.
    progress: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    operators_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    operators_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    offers_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TourOffer(Base):
    """Bitta tur taklifi — normallashtirilgan, operatordan qat'i nazar bir xil.

    Turli operator turli formatda beradi (narx so'mda/dollarda, transfer
    alohida/ichida, komissiya ko'rsatilgan/yo'q). Bu jadval — o'sha
    xilma-xillik yagona ko'rinishga keltirilgandan keyingi natija.
    """

    __tablename__ = "tour_offers"
    __table_args__ = (
        Index("ix_tour_offers_company_search", "company_id", "search_id"),
        Index("ix_tour_offers_company_expires", "company_id", "expires_at"),
        # Dedup uchun: bir xil mehmonxona+sana+ovqat turli operatorlardan.
        Index("ix_tour_offers_dedup", "company_id", "hotel_name", "date_from"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # MAJBURIY — narx turagentga bog'liq, aralashtirib bo'lmaydi.
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    search_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("operator_searches.id"), nullable=True, index=True
    )
    operator_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tour_operators.id"), nullable=True, index=True
    )
    # Operator nomi matn sifatida ham saqlanadi — katalogdan o'chsa ham
    # taklif tarixi o'qilishi kerak.
    operator_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # --- Mehmonxona / yo'nalish ---
    hotel_name: Mapped[str] = mapped_column(String(300))
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    star: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    board: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # AI/HB/BB
    room: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    # --- Sana / mehmonlar ---
    date_from: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    nights: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    adults: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    children: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- Narx ---
    # `price_gross` — mijoz to'laydigan; `price_net` — agent operatorga
    # to'laydigan. Agentning foydasi ikkisining farqi — reyting AYNAN shu
    # bo'yicha, eng arzon narx bo'yicha emas.
    price_gross: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_net: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    commission_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    flight_included: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    transfer_included: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # --- Manba va ishonchlilik ---
    source: Mapped[str] = mapped_column(
        String(20), default=OfferSource.RPA, nullable=False
    )
    # 0..1 — RPA yangi natijasi yuqori, rasm price-list'dan o'qilgani pastroq.
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Operator kabinetidagi to'g'ridan-to'g'ri havola (bron qilish uchun).
    deep_link: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    # Asl javob (JSON) — qayta tahlil va nizoli holatlar uchun.
    raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Shu vaqtdan keyin narx eskirgan hisoblanadi va UI'da "tasdiqlang"
    # tugmasi bilan ko'rsatiladi. Yozuv O'CHIRILMAYDI.
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # Agent "tizimga qo'shish" bosgan — bu taklif endi doimiy.
    is_saved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Saqlangandan keyin yaratilgan tur paketi.
    tour_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tours.id"), nullable=True
    )

    @property
    def agent_margin(self) -> Optional[float]:
        """Agentning shu taklifdan foydasi (mutlaq son)."""
        if self.price_gross is None or self.price_net is None:
            return None
        return self.price_gross - self.price_net

    def is_fresh(self, now: datetime) -> bool:
        """Narx hali ishonchlimi?"""
        return self.expires_at is None or self.expires_at > now
