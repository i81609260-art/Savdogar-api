"""TourGroup schemas."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class TourGroupBase(BaseModel):
    departure_date: date
    return_date: date
    hotel_stars: Optional[int] = Field(None, ge=1, le=5)
    price: float = Field(..., gt=0)
    total_slots: int = Field(50, ge=1)
    notes: Optional[str] = None
    is_active: bool = True


class TourGroupCreate(TourGroupBase):
    pass


class TourGroupUpdate(BaseModel):
    departure_date: Optional[date] = None
    return_date: Optional[date] = None
    hotel_stars: Optional[int] = Field(None, ge=1, le=5)
    price: Optional[float] = Field(None, gt=0)
    total_slots: Optional[int] = Field(None, ge=1)
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class TourGroupResponse(TourGroupBase):
    id: int
    tour_id: int
    company_id: int
    booked_slots: int
    available_slots: int
    duration_days: int
    created_at: datetime

    model_config = {"from_attributes": True}


class UpcomingGroupResponse(TourGroupResponse):
    """Used in the public 'upcoming departures' block."""

    tour_title: str
    tour_destination: str  # city
