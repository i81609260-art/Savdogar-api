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
