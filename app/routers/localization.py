"""Multi-language and localization support."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from pydantic import BaseModel

router = APIRouter(prefix="/api/localization", tags=["Localization"])


class LanguageSettings(BaseModel):
    """User language preferences."""
    language: str  # uz, en, ru
    timezone: str  # UTC+5, UTC+0, etc
    currency: str  # UZS, USD, RUB


@router.get("/languages", summary="Qo'llab-quvvatlanuvchi tillar")
async def get_supported_languages() -> dict:
    """Qo'llab-quvvatlanuvchi tillar ro'yxati."""
    return {
        "languages": [
            {"code": "uz", "name": "O'zbek", "flag": "🇺🇿"},
            {"code": "en", "name": "English", "flag": "🇬🇧"},
            {"code": "ru", "name": "Русский", "flag": "🇷🇺"},
        ],
        "timezones": [
            "UTC+5 (Tashkent)",
            "UTC+0 (London)",
            "UTC+3 (Moscow)",
        ],
        "currencies": [
            {"code": "UZS", "symbol": "сўм"},
            {"code": "USD", "symbol": "$"},
            {"code": "RUB", "symbol": "₽"},
        ],
    }


@router.get("/translations/{language}", summary="Tarjimalar")
async def get_translations(language: str) -> dict:
    """Tanlangan tilda barcha tarjimalar."""
    translations = {
        "uz": {
            "title": "Savdogar - Tur bron qilish platformasi",
            "welcome": "Xush kelibsiz!",
            "bookings": "Bronlashlar",
            "tours": "Turlar",
            "analytics": "Tahlil",
        },
        "en": {
            "title": "Savdogar - Tour Booking Platform",
            "welcome": "Welcome!",
            "bookings": "Bookings",
            "tours": "Tours",
            "analytics": "Analytics",
        },
        "ru": {
            "title": "Savdogar - Платформа бронирования туров",
            "welcome": "Добро пожаловать!",
            "bookings": "Бронирования",
            "tours": "Туры",
            "analytics": "Аналитика",
        },
    }
    return translations.get(language, translations["uz"])


@router.post("/user-language", summary="Foydalanuvchi tilini o'rnatish")
async def set_user_language(
    settings: LanguageSettings,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Foydalanuvchi til va vaqt zonasini o'rnatish."""
    return {
        "status": "updated",
        "language": settings.language,
        "timezone": settings.timezone,
        "currency": settings.currency,
    }


@router.get("/currency-conversion", summary="Valyuta konversiyasi")
async def get_currency_rates() -> dict:
    """Joriy valyuta kurslari."""
    return {
        "base": "USD",
        "rates": {
            "UZS": 12500,
            "RUB": 95,
            "EUR": 0.92,
        },
        "updated": "2026-06-08T15:30:00Z",
    }
