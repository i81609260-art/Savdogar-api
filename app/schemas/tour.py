"""Tour package schemas."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class TourCreate(BaseModel):
    """Create tour payload."""

    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=10)
    city: str
    country: str = "Uzbekistan"
    price: float = Field(..., gt=0)
    duration_days: int = Field(..., ge=1)
    start_date: date
    end_date: date
    available_slots: int = Field(..., ge=1)
    booking_type: str = Field(default="group")


class TourUpdate(BaseModel):
    """Partial tour update."""

    title: Optional[str] = None
    description: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    duration_days: Optional[int] = Field(None, ge=1)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    available_slots: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    booking_type: Optional[str] = None


class TourResponse(BaseModel):
    """Tour detail response."""

    id: int
    company_id: int
    company_name: Optional[str] = None
    title: str
    description: str
    city: str
    country: str
    price: float
    duration_days: int
    start_date: date
    end_date: date
    available_slots: int
    image_url: Optional[str]
    booking_type: str = "group"
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
