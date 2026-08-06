"""Tur operator va turagentning o'sha operatordagi hisobi.

Ikkita alohida tushuncha — chalkashtirmaslik muhim:

* **`TourOperator`** — operatorning o'zi (Coral, Anex, ...). Maxfiy narsa yo'q:
  nomi, sayti, qaysi B2B dvigatelda ishlashi. `company_id` ustuni:
    - `NULL`  → platforma katalogi, hamma turagent ko'radi va ishlata oladi;
    - to'ldirilgan → **faqat o'sha turagentniki**, boshqalar ko'rmaydi.
  Katalog shuning uchun kerakki, bitta konnektor skripti o'nlab turagentga
  xizmat qiladi — har biri uchun qaytadan yozilmaydi.

* **`OperatorAccount`** — turagentning o'sha operatordagi **shaxsiy hisobi**:
  login, parol, sessiya. `company_id` MAJBURIY va hech qachon bo'sh emas.
  Bir turagentning hisobi boshqasiga ko'rinmaydi, aralashmaydi.

Ya'ni: "Coral Travel" ro'yxatda bitta bo'lishi mumkin, lekin unga ulanish
har turagentda O'ZINIKI. Ikkalasi ham `company_id` orqali qat'iy ajratilgan.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OperatorEngine(StrEnum):
    """Operator qaysi B2B qidiruv tizimida ishlaydi.

    Ko'p operator o'z tizimini yozmagan — tayyor dvigatel ishlatadi. Shuning
    uchun konnektor operatorga emas, DVIGATELGA yoziladi: 18 ta operatorni
    4-6 ta konnektor qoplashi mumkin.
    """

    CUSTOM = "custom"          # o'ziga xos sayt — alohida konnektor
    MASTER_TOUR = "master_tour"
    SAMO_TUR = "samo_tur"
    TOURINDEX = "tourindex"
    MANUAL = "manual"          # API/sayt yo'q — RFQ yoki price-list orqali


class AccountStatus(StrEnum):
    """Turagent hisobining holati."""

    NEW = "yangi"              # kiritildi, hali sinalmadi
    OK = "ishlayapti"          # oxirgi ulanish muvaffaqiyatli
    AUTH_FAILED = "parol_xato"
    CAPTCHA = "captcha_kerak"  # agent o'zi bosishi kerak
    BLOCKED = "bloklangan"
    DISABLED = "ochirilgan"    # agent o'zi o'chirgan


class TourOperator(Base):
    """Tur operator. Katalog yozuvi yoki turagentning shaxsiy qo'shgani."""

    __tablename__ = "tour_operators"
    __table_args__ = (
        # Bitta turagent ichida slug takrorlanmasin. Katalog (company_id IS NULL)
        # uchun ham shu qoida ishlaydi.
        UniqueConstraint("company_id", "slug", name="uq_operator_company_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # NULL = platforma katalogi (hamma ko'radi).
    # To'ldirilgan = FAQAT shu turagentniki.
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(120))
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # B2B kabinetga kirish manzili — konnektor shu yerdan boshlaydi.
    login_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    engine: Mapped[str] = mapped_column(
        String(30), default=OperatorEngine.CUSTOM, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Konnektor "retsepti" — JSON: qaysi maydonga nima yozish, natijani
    # qayerdan o'qish. Kod emas, ma'lumot: sayt o'zgarsa faqat selektor
    # almashadi va deploy kerak bo'lmaydi.
    #
    # Bo'sh bo'lsa avtomatik qidiruv ishlamaydi — lekin login qismi
    # retseptsiz ham ishlaydi (umumiy qoidalar bilan).
    connector_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Kim qo'shgani (audit).
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    @property
    def is_catalog(self) -> bool:
        """Platforma katalogidagi umumiy yozuvmi?"""
        return self.company_id is None


class OperatorAccount(Base):
    """Turagentning tur operatordagi hisobi (login/parol/sessiya).

    `company_id` — bu jadvalning butun ma'nosi. Har bir so'rov shu ustun
    bo'yicha filtrlanadi; hisoblar turagentlar orasida hech qachon
    aralashmaydi.
    """

    __tablename__ = "operator_accounts"
    __table_args__ = (
        # Bitta turagentda bitta operatorga bitta hisob.
        UniqueConstraint(
            "company_id", "operator_id", name="uq_account_company_operator"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # MAJBURIY — hisob doim aniq bir turagentga tegishli.
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    operator_id: Mapped[int] = mapped_column(
        ForeignKey("tour_operators.id"), nullable=False, index=True
    )

    # --- Maxfiy maydonlar: bazaga FAQAT shifrlangan holda yoziladi. ---
    # Yozish/o'qish `app.utils.crypto` orqali. Panelda niqoblab ko'rsatiladi,
    # API javobida hech qachon ochiq qaytmaydi.
    login_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    password_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Playwright `storage_state` (cookie'lar). Bu bo'lsa parol kerak emas —
    # agent bir marta qo'lda kirgan, keyin sessiya qayta ishlatiladi.
    session_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    session_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(20), default=AccountStatus.NEW, nullable=False
    )
    last_ok_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Qidiruvda ishtirok etsinmi (agent vaqtincha o'chirib qo'yishi mumkin).
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def has_session(self) -> bool:
        """Saqlangan sessiya bormi (parolsiz ishlash mumkinmi)?"""
        return bool(self.session_enc)

    @property
    def is_usable(self) -> bool:
        """Qidiruvga qo'shilsinmi?

        `is_enabled` ustunidagi `default=True` faqat INSERT paytida qo'llanadi
        — hali saqlanmagan obyektda u `None` bo'ladi. Shuning uchun `None` ni
        "yoqilgan" deb qaraymiz, aks holda yangi hisob jimgina tashlab
        ketilardi.
        """
        enabled = True if self.is_enabled is None else self.is_enabled
        return bool(enabled) and self.status not in {
            AccountStatus.DISABLED,
            AccountStatus.BLOCKED,
        }
