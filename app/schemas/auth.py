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
    admin_email: EmailStr
    admin_password: str = Field(..., min_length=8)
    admin_full_name: str = Field(..., min_length=2)
    admin_phone: Optional[str] = None


class UserRegisterRequest(BaseModel):
    """End-user registration."""

    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2)
    phone: Optional[str] = None


class LoginRequest(BaseModel):
    """Login credentials."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token pair response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Refresh token payload."""

    refresh_token: str


class UserResponse(BaseModel):
    """Public user profile."""

    id: int
    email: str
    full_name: str
    phone: Optional[str]
    role: UserRole
    company_id: Optional[int]

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """Login response with user and tokens."""

    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class PushSubscriptionRequest(BaseModel):
    """Browser push subscription JSON."""

    subscription: str
