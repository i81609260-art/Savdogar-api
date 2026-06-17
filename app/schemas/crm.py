"""CRM customer schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from app.models.booking import BookingStatus
from app.schemas.booking import BookingResponse


class CustomerSegment(str):
    """Customer segment constants."""

    NEW = "new"
    RETURNING = "returning"
    VIP = "vip"


class CustomerResponse(BaseModel):
    """CRM customer profile."""

    id: int
    email: str
    full_name: str
    phone: Optional[str]
    total_bookings: int
    confirmed_bookings: int
    total_spent: float
    segment: str
    last_booking_at: Optional[datetime]
    bookings: List[BookingResponse] = []


class CustomerCreateRequest(BaseModel):
    """Payload to manually create a customer with a tour booking."""

    full_name: str
    phone: str
    email: str
    tour_id: int
    guests_count: int = 1
    notes: Optional[str] = None
