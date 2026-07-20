"""Qo'ng'iroq yozuvini AI bilan tahlil qilish.

Gemini audio'ni to'g'ridan-to'g'ri qabul qiladi, shuning uchun transkripsiya va
tahlil bitta so'rovda bajariladi — alohida STT serveri kerak emas. Kalit
berilmagan bo'lsa yozuv saqlanadi, lekin tahlil qilinmaydi.
"""

import base64
import json
import logging
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_PROMPT = """Sen tur agentligining sifat nazorati bo'yicha yordamchisisan.
Quyidagi audio — operator va mijoz o'rtasidagi telefon suhbati. Suhbat o'zbek,
rus yoki aralash tilda bo'lishi mumkin.

Audio'ni tinglab, FAQAT quyidagi JSON'ni qaytar (boshqa matnsiz):

{
  "transcript": "suhbatning to'liq matni, har bir gap oldida 'Operator:' yoki 'Mijoz:'",
  "summary": "2-4 gapda suhbat mazmuni, o'zbek tilida",
  "sentiment": "ijobiy | betaraf | salbiy",
  "score": 0 dan 100 gacha butun son — mijoz sotib olishga qanchalik yaqin,
  "destination": "mijoz qiziqqan yo'nalish yoki bo'sh satr",
  "topics": ["narx", "sana", "viza", "mehmonxona" kabi 1-5 ta teg],
  "next_step": "operator keyingi qadamda nima qilishi kerak, bir gapda",
  "operator_notes": "operator nimani o'tkazib yubordi yoki noto'g'ri qildi; yaxshi ishlagan bo'lsa shuni yoz"
}

Agar audio tushunarsiz yoki suhbat bo'lmasa, transcript'ni bo'sh qoldirib
summary'ga sababini yoz."""

# Gemini inline_data ~20MB so'rov chegarasiga ega; audio undan ancha kichik bo'lishi kerak.
MAX_AUDIO_BYTES = 15 * 1024 * 1024


class AnalysisUnavailable(RuntimeError):
    """AI kaliti sozlanmagan yoki xizmat javob bermadi."""


def is_configured() -> bool:
    """Tahlil yoqilganmi."""
    return bool(get_settings().gemini_api_key)


def _extract_json(raw: str) -> dict:
    """Modeldan kelgan matndan JSON obyektini ajratib olish."""
    raw = raw.strip()
    if raw.startswith("```"):
        # ```json ... ``` blokini tozalash
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise AnalysisUnavailable("AI javobida JSON topilmadi")
    return json.loads(raw[start : end + 1])


async def analyze_audio(content: bytes, mime_type: str) -> dict:
    """Audio baytlarini tahlil qilib, normallashtirilgan natija qaytarish."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise AnalysisUnavailable(
            "AI tahlili sozlanmagan — GEMINI_API_KEY o'zgaruvchisini qo'shing"
        )
    if len(content) > MAX_AUDIO_BYTES:
        raise AnalysisUnavailable(
            f"Audio juda katta ({len(content) // 1024 // 1024}MB), "
            f"{MAX_AUDIO_BYTES // 1024 // 1024}MB gacha bo'lishi kerak"
        )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": _PROMPT},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64.b64encode(content).decode(),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }

    url = _ENDPOINT.format(model=settings.gemini_model)
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            url, params={"key": settings.gemini_api_key}, json=payload
        )

    if resp.status_code != 200:
        logger.warning("Gemini xatosi %s: %s", resp.status_code, resp.text[:500])
        if resp.status_code == 429:
            raise AnalysisUnavailable("Kunlik tekin limit tugadi, ertaga qayta urining")
        raise AnalysisUnavailable(f"AI xizmati javob bermadi ({resp.status_code})")

    try:
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise AnalysisUnavailable("AI javobi kutilgan formatda emas") from exc

    data = _extract_json(text)

    topics = data.get("topics") or []
    if isinstance(topics, str):
        topics = [topics]

    score: Optional[int] = None
    try:
        if data.get("score") is not None:
            score = max(0, min(100, int(data["score"])))
    except (TypeError, ValueError):
        pass

    sentiment = str(data.get("sentiment") or "").lower().strip()
    if sentiment not in ("ijobiy", "betaraf", "salbiy"):
        sentiment = "betaraf"

    return {
        "transcript": (data.get("transcript") or "").strip() or None,
        "summary": (data.get("summary") or "").strip() or None,
        "sentiment": sentiment,
        "score": score,
        "destination": (data.get("destination") or "").strip() or None,
        "topics": ", ".join(str(t) for t in topics[:5]) or None,
        "next_step": (data.get("next_step") or "").strip() or None,
        "operator_notes": (data.get("operator_notes") or "").strip() or None,
    }
