"""AI chat endpoint — ML-powered company assistant."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.company import Company
from app.models.tour import Tour
from app.services.ml_chat_service import (
    Company as MLCompany,
    Tour as MLTour,
    ml_chat,
)

router = APIRouter(prefix="/api/chat", tags=["Chat"])


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class ChatResponse(BaseModel):
    reply: str
    intent: str | None = None


@router.post("/{company_id}", response_model=ChatResponse)
async def chat(
    company_id: int,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """ML chat — answers questions about a company's tours."""
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")

    tours_result = await db.execute(
        select(Tour).where(Tour.company_id == company_id, Tour.is_active == True)  # noqa: E712
    )
    tours = tours_result.scalars().all()

    ml_tours = [
        MLTour(
            id=t.id,
            title=t.title,
            description=t.description or "",
            city=t.city,
            country=t.country,
            price=t.price,
            duration_days=t.duration_days,
            start_date=str(t.start_date),
            available_slots=t.available_slots,
        )
        for t in tours
    ]
    ml_company = MLCompany(
        name=company.name,
        description=company.description or "",
        city=company.city,
        phone=company.phone,
        email=company.email,
    )

    # Re-index if tours changed (simple cache invalidation by count)
    cached = ml_chat._tour_data.get(company_id)
    if cached is None or len(cached) != len(ml_tours):
        ml_chat.index_company_tours(company_id, ml_tours)

    intent = ml_chat._detect_intent(body.message)
    reply = ml_chat.respond(company_id, ml_company, body.message, body.history)

    return ChatResponse(reply=reply, intent=intent)
