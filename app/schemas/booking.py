"""Booking schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.booking import BookingStatus


class BookingCreate(BaseModel):
    """Create booking request."""

    tour_id: int
    guests_count: int = Field(default=1, ge=1)
    notes: Optional[str] = None


class BookingStatusUpdate(BaseModel):
    """Admin updates booking status."""

    status: BookingStatus
    cancel_reason: Optional[str] = None


class BookingResponse(BaseModel):
    """Booking detail."""

    id: int
    user_id: int
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    tour_id: int
    tour_title: Optional[str] = None
    company_id: int
    status: BookingStatus
    guests_count: int
    total_price: float
    notes: Optional[str]
    cancel_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
