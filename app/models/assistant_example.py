"""ML yordamchi oʻrgangan misollar — oʻz-oʻzini kuchaytirish uchun.

Har muvaffaqiyatli suhbatdan (tasdiqlangan amal yoki javob berilgan sorov)
bitta (matn -> intent) misoli saqlanadi. Model shu misollar + boshlangʻich
dataset ustida qayta oʻqiydi, shuning uchun ishlatilgani sari kuchayadi.

Misol modelning KIRISHi (intent klassifikatsiyasi) uchun ishlatiladi; firma
ma'lumoti (turlar, narx) bu yerda saqlanmaydi — faqat buyruq matni va uning turi.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AssistantExample(Base):
    """Bitta oʻrganilgan (matn -> intent) misoli."""

    __tablename__ = "assistant_examples"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id"), nullable=True, index=True
    )
    text: Mapped[str] = mapped_column(String(500))
    intent: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
