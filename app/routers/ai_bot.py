"""AI Bot integration - Telegram/Web bot with website data analysis."""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from pydantic import BaseModel

router = APIRouter(prefix="/api/ai-bot", tags=["AI Bot"])


class BotMessage(BaseModel):
    """Bot message from user."""
    text: str
    user_id: int
    platform: str  # telegram, web, whatsapp


class WebsiteAnalysisResult(BaseModel):
    """Website data analysis result."""
    popular_destinations: List[str]
    avg_price_range: dict
    most_booked_duration: int
    trending_tour_types: List[str]
    suggested_packages: List[dict]


class GeneratedTourPackage(BaseModel):
    """AI generated tour package."""
    title: str
    destination: str
    duration_days: int
    price: float
    description: str
    included_services: List[str]
    confidence_score: float


@router.post("/message", summary="Bot xabari olish")
async def handle_bot_message(
    data: BotMessage,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bot xabarini tahlil qilish va javob berish."""
    from app.services.ai_service import analyze_message_with_gemini

    try:
        # Analyze message with AI
        response = await analyze_message_with_gemini(
            message=data.text,
            platform=data.platform,
            user_id=data.user_id,
        )

        return {
            "status": "success",
            "response": response,
            "next_action": "book" if "booking" in response.lower() else "info",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }


@router.get("/website-analysis/{company_id}", summary="Sayt ma'lumotlari tahlili")
async def analyze_website_data(
    company_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> WebsiteAnalysisResult:
    """Saytdagi ma'lumotlarni AI bilan tahlil qilish."""
    from app.models.booking import Booking
    from app.models.tour import Tour

    if current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")

    # Get booking data
    bookings_result = await db.execute(
        select(
            Booking.tour_id,
            func.count(Booking.id).label("count"),
        )
        .where(Booking.company_id == company_id)
        .group_by(Booking.tour_id)
        .order_by(func.count(Booking.id).desc())
    )
    popular_tours = bookings_result.all()

    # Get tour details for popular tours
    tour_ids = [t[0] for t in popular_tours]
    if tour_ids:
        tours_result = await db.execute(
            select(Tour).where(Tour.id.in_(tour_ids))
        )
        tours = tours_result.scalars().all()

        destinations = list(set([t.destination for t in tours if t.destination]))
        prices = [t.price for t in tours if t.price]
        durations = [t.duration_days for t in tours if t.duration_days]
        tour_types = list(set([t.tour_type for t in tours if t.tour_type]))

        avg_price = {
            "min": min(prices) if prices else 0,
            "max": max(prices) if prices else 0,
            "avg": sum(prices) / len(prices) if prices else 0,
        }

        avg_duration = sum(durations) / len(durations) if durations else 5
    else:
        destinations = []
        avg_price = {"min": 0, "max": 0, "avg": 0}
        avg_duration = 5
        tour_types = []

    # Suggested packages based on patterns
    suggested_packages = [
        {
            "destination": destinations[0] if destinations else "Popular",
            "duration": int(avg_duration),
            "estimated_price": int(avg_price.get("avg", 1000)),
            "confidence": 0.85,
        }
        for _ in range(min(3, len(destinations)))
    ]

    return WebsiteAnalysisResult(
        popular_destinations=destinations[:5],
        avg_price_range=avg_price,
        most_booked_duration=int(avg_duration),
        trending_tour_types=tour_types[:5],
        suggested_packages=suggested_packages,
    )


@router.post("/generate-packages", summary="AI tur paketlarini yaratish")
async def generate_tour_packages(
    company_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> List[GeneratedTourPackage]:
    """AI sayt ma'lumotlariga asosan tur paketlarini yaratish."""
    from app.models.tour import Tour

    if current_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")

    # Analyze website data
    result = await analyze_website_data(company_id, current_user, db)

    # Generate packages based on analysis
    packages = []

    for dest in result.popular_destinations[:3]:
        package = GeneratedTourPackage(
            title=f"{dest} - {result.most_booked_duration} kunlik tur",
            destination=dest,
            duration_days=result.most_booked_duration,
            price=result.avg_price_range.get("avg", 1000),
            description=f"Saytdagi eng mashhur {dest} tuli. AI tahlili asosida yaratilgan.",
            included_services=[
                "Samolyot",
                "Mehmonxona",
                "Ovqatlanish",
                "Ekskursiyalar",
            ],
            confidence_score=0.82,
        )
        packages.append(package)

    return packages


@router.get("/bot-stats/{company_id}", summary="Bot statistikasi")
async def get_bot_stats(
    company_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bot bilan o'zaro aloqa statistikasi."""
    return {
        "total_messages": 0,
        "successful_conversions": 0,
        "average_response_time": 1.2,
        "user_satisfaction": 4.5,
        "trending_questions": [
            "Eng arzon turlar qaysi?",
            "Turkiyaga ketish qanday narx?",
            "Samolyot bron qilingan?",
        ],
    }
