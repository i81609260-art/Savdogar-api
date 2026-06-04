"""Promo code schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PromoCodeCreate(BaseModel):
    """Create promo code."""
    code: str
    description: Optional[str] = None
    discount_percent: float = 0
    discount_amount: Optional[float] = None
    max_uses: Optional[int] = None
    valid_until: Optional[datetime] = None
    min_booking_amount: float = 0
    tour_ids: Optional[str] = None  # comma-separated


class PromoCodeResponse(BaseModel):
    """Promo code response."""
    id: int
    code: str
    description: Optional[str]
    discount_percent: float
    discount_amount: Optional[float]
    is_active: bool
    used_count: int
    max_uses: Optional[int]
    valid_until: Optional[datetime]
    min_booking_amount: float
    tour_ids: Optional[str] = None

    model_config = {"from_attributes": True}


class PromoValidationRequest(BaseModel):
    """Validate promo code for booking."""
    code: str
    booking_amount: float
    tour_id: Optional[int] = None


class PromoValidationResponse(BaseModel):
    """Promo validation result."""
    valid: bool
    message: str
    discount_amount: float = 0
    final_amount: float = 0
