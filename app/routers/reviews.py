"""Reviews API — tur tugagandan keyin mijoz sharhlari."""

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from app.services.review_service import ReviewService

router = APIRouter(prefix="/api/reviews", tags=["Reviews"])


class ReviewCreate(BaseModel):
    booking_id: int
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None


@router.post(
    "",
    summary="Sharh yozish",
    dependencies=[Depends(role_required(UserRole.USER))],
)
async def create_review(
    data: ReviewCreate,
    current_user: User = Depends(role_required(UserRole.USER)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ReviewService(db).create_review(
        current_user, data.booking_id, data.rating, data.comment
    )


@router.get("/tours/{tour_id}", summary="Tur sharhlari")
async def tour_reviews(
    tour_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    return await ReviewService(db).get_tour_reviews(tour_id)


@router.get("/companies/{company_id}/rating", summary="Kompaniya reytingi")
async def company_rating(
    company_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ReviewService(db).get_company_rating(company_id)


@router.get("/companies/{company_id}/list", summary="Kompaniya sharhlar (public)")
async def company_reviews_public(
    company_id: int,
    limit: int = 6,
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    return await ReviewService(db).list_company_reviews_public(company_id, limit)


@router.get(
    "/admin",
    summary="Admin uchun sharhlar ro'yxati",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR, UserRole.SUPERADMIN))],
)
async def admin_reviews(
    current_user: User = Depends(
        role_required(UserRole.ADMIN, UserRole.OPERATOR, UserRole.SUPERADMIN)
    ),
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    return await ReviewService(db).list_admin_reviews(current_user)
