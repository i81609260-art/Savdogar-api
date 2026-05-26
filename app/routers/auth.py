"""Authentication API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    PushSubscriptionRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/register", response_model=AuthResponse, summary="Kompaniya + admin ro'yxatdan o'tish")
async def register_company(
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Register tour company and auto-login."""
    service = AuthService(db)
    return await service.register_company(data)


@router.post("/register/user", response_model=UserResponse, summary="Foydalanuvchi ro'yxati")
async def register_user(
    data: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Register end-user account."""
    service = AuthService(db)
    return await service.register_user(data)


@router.post("/login", response_model=AuthResponse, summary="Tizimga kirish")
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Login and receive JWT tokens."""
    service = AuthService(db)
    return await service.login(data)


@router.post("/refresh", response_model=TokenResponse, summary="Token yangilash")
async def refresh(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Refresh access token using refresh token."""
    service = AuthService(db)
    return await service.refresh_token(data.refresh_token)


@router.post("/logout", summary="Tizimdan chiqish")
async def logout(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Blacklist refresh token on logout."""
    service = AuthService(db)
    return await service.logout(data.refresh_token)


@router.post("/push-subscribe", summary="Push obuna")
async def push_subscribe(
    data: PushSubscriptionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Save browser push subscription."""
    service = AuthService(db)
    return await service.save_push_subscription(current_user, data.subscription)
