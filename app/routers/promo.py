"""Promo codes and discounts API."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.promo import PromoValidationRequest, PromoValidationResponse
from app.services.promo_service import PromoService

router = APIRouter(prefix="/api/promo", tags=["Promo"])


@router.post("/validate", response_model=PromoValidationResponse, summary="Promo kodni tekshirish")
async def validate_promo(
    data: PromoValidationRequest,
    db: AsyncSession = Depends(get_db),
) -> PromoValidationResponse:
    """Validate promo code and calculate discount."""
    service = PromoService(db)
    result = await service.validate_code(
        data.code,
        data.booking_amount,
        data.tour_id,
    )
    return PromoValidationResponse(**result)
