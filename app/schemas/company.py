"""Company schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from app.models.company import CompanyStatus


class CompanyResponse(BaseModel):
    """Company public data."""

    id: int
    name: str
    description: Optional[str]
    city: str
    phone: str
    email: str
    status: CompanyStatus
    rejection_reason: Optional[str]
    logo_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyDetailResponse(BaseModel):
    """Superadmin uchun kompaniya to'liq ma'lumotlari."""
    id: int
    name: str
    description: Optional[str]
    city: str
    phone: str
    email: str
    status: CompanyStatus
    rejection_reason: Optional[str]
    logo_url: Optional[str] = None
    owner_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    users_count: Optional[int] = 0
    tours_count: Optional[int] = 0

    model_config = {"from_attributes": True}



class CompanyRejectRequest(BaseModel):
    """Reject company application."""

    reason: str
