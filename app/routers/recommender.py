"""Mijoz uchun tur tavsiyalovchi: anketa, suhbat va natija.

Endpointlar OCHIQ — mehmon ham tavsiya ola oladi. Bron qilish uchun
kirish talab qilinadi, lekin uni tavsiyadan OLDIN so'rash odamlarni
qaytarib yuborardi.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_optional_user
from app.models.tour import Tour
from app.models.user import User
from app.services import recommender
from app.services.travel_profile import (
    DIMENSION_LABELS,
    QUESTIONS,
    questions_payload,
    score,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recommender", tags=["Tavsiya"])


class RecommendRequest(BaseModel):
    # {savol_id: javob_id}
    answers: dict[str, str] = Field(default_factory=dict)
    # Erkin matn: "avgustda 2 kishi 12 mln gacha Turkiyaga"
    text: str = ""
    departure_city: Optional[str] = None
    lang: str = "uz"
    limit: int = Field(default=10, ge=1, le=30)


class EventRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    tour_id: int
    outcome: str = "opened"
    position: Optional[int] = None


@router.get("/questions", summary="Psixologik anketa savollari")
async def get_questions(lang: str = Query("uz")) -> dict:
    """Savollar va javob variantlari.

    Savollar SERVERDA turadi: ilova yangilanmasdan turib savollarni
    o'zgartirish va qo'shish mumkin bo'lsin.
    """
    return {
        "questions": questions_payload(lang),
        "total": len(QUESTIONS),
        "dimensions": {
            d: labels.get(lang, labels["uz"])
            for d, labels in DIMENSION_LABELS.items()
        },
    }


@router.post("", summary="Tur tavsiya qilish")
async def recommend(
    data: RecommendRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
) -> dict:
    """Anketa va/yoki erkin matndan tur paket tavsiya qiladi."""
    natija = await recommender.recommend(
        db,
        answers=data.answers,
        text=data.text,
        departure_city=data.departure_city,
        limit=data.limit,
        lang=data.lang,
        user_id=current_user.id if current_user else None,
    )
    return natija


@router.post("/event", summary="Tavsiya natijasini belgilash")
async def log_outcome(
    data: EventRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
) -> dict:
    """Mijoz turni ochdi yoki bron qildi.

    Tizim aynan shu yozuvlardan o'rganadi: qaysi profil qaysi toifani
    HAQIQATAN tanlaydi.
    """
    if data.outcome not in ("shown", "opened", "booked"):
        return {"ok": False, "detail": "noma'lum holat"}
    tur = (
        await db.execute(select(Tour).where(Tour.id == data.tour_id))
    ).scalar_one_or_none()
    if tur is None:
        return {"ok": False, "detail": "tur topilmadi"}
    await recommender.log_event(
        db, score(data.answers), tur, data.outcome,
        user_id=current_user.id if current_user else None,
        position=data.position,
    )
    return {"ok": True}


class ChatRequest(BaseModel):
    message: str
    answers: dict[str, str] = Field(default_factory=dict)
    departure_city: Optional[str] = None
    lang: str = "uz"
    history: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/chat", summary="Tavsiya bo'yicha suhbat")
async def chat(
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
) -> dict:
    """Mijoz bilan erkin suhbat: savolga javob beradi va tur taklif qiladi.

    Tashqi LLM YO'Q — bizning Tella: matndan byudjet, sana, yo'nalish va
    kishi sonini ajratib oladi, anketa bilan birlashtiradi va ro'yxat
    qaytaradi.
    """
    natija = await recommender.recommend(
        db,
        answers=data.answers,
        text=data.message,
        departure_city=data.departure_city,
        limit=5,
        lang=data.lang,
        user_id=current_user.id if current_user else None,
    )
    javob = recommender.compose_reply(
        message=data.message,
        query=recommender.extract_query(data.message)
        if data.message.strip() else None,
        reasons=natija.get("reasons", []),
        found=len(natija["items"]),
        answered=natija["profile"]["answered"],
        lang=data.lang,
    )
    return {**natija, "reply": javob}
