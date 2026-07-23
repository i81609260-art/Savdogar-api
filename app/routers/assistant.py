"""Har bir tur firma admini uchun ML yordamchi endpointi (LLM ishlatmaydi).

Yordamchi joriy foydalanuvchining firmasi bilan chegaralangan. Suhbat holati
(pending) mijoz bilan almashiladi, shuning uchun server holatsiz.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from app.services import ml_assistant

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assistant", tags=["AI Assistant"])


class ChatRequest(BaseModel):
    message: str
    # Yigʻilayotgan suhbat holati — oldingi javobdan qaytariladi.
    pending: Optional[dict[str, Any]] = None


class ChatReply(BaseModel):
    reply: str
    actions: list[str] = []
    pending: Optional[dict[str, Any]] = None


@router.get("/status", summary="AI yordamchi holati")
async def status() -> dict:
    """ML yordamchi doim mavjud (tashqi kalit kerak emas)."""
    return {"enabled": ml_assistant.is_configured()}


@router.post("/chat", response_model=ChatReply, summary="ML yordamchi bilan suhbat")
async def chat(
    data: ChatRequest,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> ChatReply:
    """Foydalanuvchi xabarini ML yordamchiga uzatib, javob va amallarni qaytaradi."""
    result = await ml_assistant.run_assistant(db, current_user, data.message, data.pending)
    return ChatReply(
        reply=result["reply"],
        actions=result.get("actions", []),
        pending=result.get("pending"),
    )
