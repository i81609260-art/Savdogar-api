"""Company schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from app.models.company import CompanyStatus, CompanyType


class CompanyResponse(BaseModel):
    """Company public data."""

    id: int
    name: str
    slug: Optional[str] = None
    custom_domain: Optional[str] = None
    company_type: Optional[CompanyType] = CompanyType.MULTI
    description: Optional[str]
    city: str
    phone: str
    email: str
    status: CompanyStatus
    rejection_reason: Optional[str]
    logo_url: Optional[str] = None
    company_info: Optional[str] = None
    sair_integrated: Optional[bool] = False
    click_merchant_id: Optional[str] = None
    payme_merchant_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyDetailResponse(BaseModel):
    """Superadmin uchun kompaniya to'liq ma'lumotlari."""
    id: int
    name: str
    slug: Optional[str] = None
    custom_domain: Optional[str] = None
    description: Optional[str]
    city: str
    phone: str
    email: str
    status: CompanyStatus
    rejection_reason: Optional[str]
    logo_url: Optional[str] = None
    owner_id: Optional[int]
    company_info: Optional[str] = None
    website_customization: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    users_count: Optional[int] = 0
    tours_count: Optional[int] = 0

    model_config = {"from_attributes": True}



class CompanyRejectRequest(BaseModel):
    """Reject company application."""

    reason: str


class CompanyInfoUpdate(BaseModel):
    """Update company information for AI context."""
    company_info: str


class WebsiteCustomizationRequest(BaseModel):
    """Website customization instruction."""
    instruction: str


class WebsiteCustomizationResponse(BaseModel):
    """Website customization response."""
    success: bool
    message: str
    changes: dict = {}
    preview_url: Optional[str] = None
