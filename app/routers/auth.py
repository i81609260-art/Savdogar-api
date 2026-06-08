"""Authentication API routes."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    PaymentSettingsUpdate,
    PushSubscriptionRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import AuthService
from app.utils.limiter import limiter

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/register", response_model=AuthResponse, summary="Kompaniya + admin ro'yxatdan o'tish")
async def register_company(
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Register tour company — status starts as PENDING until superadmin approval."""
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
@limiter.limit("10/minute")
async def login(
    request: Request,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Login and receive JWT tokens. Rate-limited to 10 attempts per minute per IP."""
    service = AuthService(db)
    return await service.login(data)


@router.post("/refresh", response_model=TokenResponse, summary="Token yangilash")
async def refresh(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Refresh access token — old refresh token is blacklisted."""
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


@router.get("/user", response_model=UserResponse, summary="Joriy foydalanuvchi ma'lumotlari")
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Get current logged-in user information."""
    return UserResponse.model_validate(current_user)


@router.post("/push-subscribe", summary="Push obuna")
async def push_subscribe(
    data: PushSubscriptionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Save browser push subscription."""
    service = AuthService(db)
    return await service.save_push_subscription(current_user, data.subscription)


@router.patch("/payment-settings", response_model=UserResponse, summary="To'lov sozlamalari")
async def update_payment_settings(
    data: PaymentSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Update user Click/Payme merchant credentials."""
    if data.click_merchant_id:
        current_user.click_merchant_id = data.click_merchant_id
    if data.click_merchant_key:
        current_user.click_merchant_key = data.click_merchant_key
    if data.payme_merchant_id:
        current_user.payme_merchant_id = data.payme_merchant_id
    if data.payme_api_key:
        current_user.payme_api_key = data.payme_api_key
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)
