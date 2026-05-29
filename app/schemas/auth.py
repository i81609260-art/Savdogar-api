"""Authentication request/response schemas."""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class RegisterRequest(BaseModel):
    """Company + admin registration payload."""
    company_name: str = Field(..., min_length=2, max_length=255)
    company_description: Optional[str] = None
    company_city: str = Field(..., min_length=2)
    company_phone: str = Field(..., min_length=9)
    company_email: EmailStr
    company_logo_url: Optional[str] = None
    admin_email: EmailStr
    admin_password: str = Field(..., min_length=8)
    admin_full_name: str = Field(..., min_length=2)
    admin_phone: Optional[str] = None
    model_config = {"extra": "allow"}


class UserRegisterRequest(BaseModel):
    """End-user registration."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2)
    phone: Optional[str] = None
    model_config = {"extra": "allow"}


class LoginRequest(BaseModel):
    """Login credentials."""
    email: str
    password: str
    model_config = {"extra": "allow"}


class TokenResponse(BaseModel):
    """JWT token pair response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    model_config = {"extra": "allow"}


class RefreshRequest(BaseModel):
    """Refresh token payload."""
    refresh_token: str
    model_config = {"extra": "allow"}


class UserResponse(BaseModel):
    """Public user profile."""
    id: int
    email: str
    full_name: str
    phone: Optional[str]
    role: UserRole
    company_id: Optional[int]
    company_status: Optional[str] = None
    model_config = {"from_attributes": True}


class SuperAdminUserResponse(BaseModel):
    """Superadmin uchun to'liq user ma'lumotlari."""
    id: int
    email: str
    full_name: str
    phone: Optional[str]
    role: UserRole
    company_id: Optional[int]
    company_status: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None
    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """Login response with user and tokens."""
    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    model_config = {"extra": "allow"}


class PushSubscriptionRequest(BaseModel):
    """Browser push subscription JSON."""
    subscription: str
    model_config = {"extra": "allow"}
