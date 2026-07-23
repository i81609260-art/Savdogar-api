"""Har bir tur firma admini uchun AI yordamchi endpointi.

Yordamchi joriy foydalanuvchining firmasi bilan chegaralangan — u faqat oʻz
kompaniyasining malumotini koradi va oʻzgartiradi.
"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from app.services import ai_assistant

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assistant", tags=["AI Assistant"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatReply(BaseModel):
    reply: str
    actions: list[str] = []


@router.get("/status", summary="AI yordamchi holati")
async def status() -> dict:
    """Frontend AI tugmasini korsatishi kerakmi."""
    return {"enabled": ai_assistant.is_configured()}


@router.post("/chat", response_model=ChatReply, summary="AI yordamchi bilan suhbat")
async def chat(
    data: ChatRequest,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> ChatReply:
    """Foydalanuvchi xabarini AI ga uzatib, javob va bajarilgan amallarni qaytaradi."""
    try:
        result = await ai_assistant.run_assistant(
            db,
            current_user,
            data.message,
            [m.model_dump() for m in data.history],
        )
    except ai_assistant.AssistantUnavailable as exc:
        return ChatReply(reply=str(exc), actions=[])
    return ChatReply(reply=result["reply"], actions=result.get("actions", []))
