"""AI Chat router for company and tour package analysis."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Any
import google.generativeai as genai

router = APIRouter(prefix="/api/ai", tags=["AI Chat"])

# Configure Gemini API
genai.configure(api_key="YOUR_GEMINI_API_KEY")  # Set via environment variable


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    type: str  # "company" or "tour-package"
    context: Optional[List[Message]] = None


class ChatResponse(BaseModel):
    response: str


@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(request: ChatRequest) -> ChatResponse:
    """Process user message with AI for company or tour package analysis."""

    if request.type not in ["company", "tour-package"]:
        raise HTTPException(status_code=400, detail="Invalid type")

    # Prepare context for Gemini
    system_prompt = ""
    if request.type == "company":
        system_prompt = """Siz turizm kompaniyasi haqida ma'lumotni tahlil qiluvchi AI asistentisiz.
        Foydalanuvchi kompaniya haqida ma'lumot berada, siz uni tahlil qilib quyidagilarni berish kerak:
        1. Kompaniyaning asosiy xizmatları
        2. Tavsiyalar va takomillashtirish
        3. Raqobatchilik afzalliklari
        4. Natijalarni chiroyli va tashkil qilib bering"""
    else:
        system_prompt = """Siz turizm tur paketlarini tahlil qiluvchi AI asistentisiz.
        Foydalanuvchi tur paket haqida ma'lumot berada, siz uni tahlil qilib quyidagilarni berish kerak:
        1. Paket tarkibi va xususiyatlari
        2. Narx va qiymat nisbati
        3. Maqsad auditoriyasi
        4. Takomillashtirish tavsiyalari
        5. Natijalarni chiroyli va tashkil qilib bering"""

    # Build conversation history
    messages = [
        {"role": "user", "parts": [system_prompt]},
    ]

    # Add context from previous messages
    if request.context:
        for msg in request.context:
            messages.append({
                "role": "user" if msg.role == "user" else "model",
                "parts": [msg.content]
            })

    # Add current message
    messages.append({
        "role": "user",
        "parts": [request.message]
    })

    try:
        # Use Gemini API
        model = genai.GenerativeModel("gemini-2.0-flash")

        # Create conversation
        chat = model.start_chat(history=messages[:-1] if len(messages) > 1 else [])
        response = chat.send_message(request.message)

        return ChatResponse(response=response.text)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")
