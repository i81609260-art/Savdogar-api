"""Call recording model — operator qo'ng'iroqlari va ularning AI tahlili."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CallRecording(Base):
    """Yuklangan yoki brauzerda yozib olingan qo'ng'iroq va uning tahlili."""

    __tablename__ = "call_recordings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    # Qaysi filialga tegishli. Bo'sh bo'lsa — umumiy, hamma ko'radi.
    branch_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    # Kim yukladi.
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Ixtiyoriy — qaysi leadga tegishli.
    request_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Mijoz raqami, qo'lda kiritiladi (yozuvda bo'lmasligi mumkin).
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    file_url: Mapped[str] = mapped_column(String(500))
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # kutilmoqda | tahlilda | tayyor | xato
    status: Mapped[str] = mapped_column(String(20), default="kutilmoqda", index=True)
    error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # AI natijalari
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # ijobiy | betaraf | salbiy
    sentiment: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # 0-100: lead qanchalik qizg'in.
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    destination: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Vergul bilan ajratilgan teglar (narx, sana, viza, ...).
    topics: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    next_step: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Operator ishidagi kamchiliklar.
    operator_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
