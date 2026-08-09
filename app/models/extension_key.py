"""Brauzer kengaytmasi uchun API kalit.

Nega kerak: kengaytma turagentning O'Z brauzerida ishlaydi va operator
kabinetidagi narxlarni serverga yuboradi. Serverdagi brauzer bu ishni
qila olmaydi — ma'lumot markazi IP'si operator saytlarida bloklanadi
(haqiqiy saytlarda sinab ko'rildi).

Kengaytma odatdagi JWT bilan ishlay olmaydi: u qisqa muddatli va brauzer
yopilganda yo'qoladi. Shuning uchun alohida, uzoq muddatli kalit.

Kalit PAROL kabi saqlanadi — faqat xesh. Ochiq qiymat yaratilganda BIR
MARTA ko'rsatiladi va boshqa hech qachon qaytarilmaydi. Baza sizib
chiqsa ham kalitlar bilan hech narsa qilib bo'lmaydi.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ExtensionKey(Base):
    """Turagentning brauzer kengaytmasi uchun kaliti."""

    __tablename__ = "extension_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Kalit QAYSI firmaga tegishli. Kengaytma yuborgan narxlar aynan shu
    # firmaning ro'yxatiga tushadi — boshqasiga emas.
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True, nullable=False
    )
    # Kim yaratgan — audit uchun. Xodim ketsa kalitini topib bekor qilish
    # mumkin bo'lsin.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Faqat XESH. Ochiq kalit hech qayerda saqlanmaydi.
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Ro'yxatda tanish uchun boshlanish qismi ("trf_a1b2..."). Sir emas.
    key_prefix: Mapped[str] = mapped_column(String(16), index=True, nullable=False)

    label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # O'chirish o'rniga bekor qilish: kalit qachon va kim tomonidan
    # ishlatilgani tarixi saqlanib qolsin.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="1"
    )
