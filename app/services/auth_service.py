"""Authentication business logic."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company, CompanyStatus
from app.models.user import RefreshTokenBlacklist, User, UserRole
from app.utils.slug import unique_slug
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
)
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class AuthService:
    """Handles registration, login, token refresh, and logout."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def register_company(self, data: RegisterRequest) -> AuthResponse:
        """Register a tour company — starts with PENDING status (requires superadmin approval)."""
        existing = await self.db.execute(
            select(User).where(User.email == data.admin_email)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bu email allaqachon ro'yxatdan o'tgan",
            )

        company = Company(
            name=data.company_name,
            slug=await unique_slug(data.company_name, self.db),
            description=data.company_description,
            city=data.company_city,
            phone=data.company_phone,
            email=data.company_email,
            logo_url=data.company_logo_url,
            sair_integrated=bool(data.sair_integrated),
            status=CompanyStatus.PENDING,
        )
        self.db.add(company)
        await self.db.flush()

        admin = User(
            email=data.admin_email,
            hashed_password=hash_password(data.admin_password),
            full_name=data.admin_full_name,
            phone=data.admin_phone,
            role=UserRole.ADMIN,
            company_id=company.id,
            is_active=True,
        )
        self.db.add(admin)
        await self.db.flush()
        company.owner_id = admin.id
        await self.db.flush()
        await self.db.refresh(admin)

        token_data = {"sub": str(admin.id), "role": admin.role.value}
        access = create_access_token(token_data)
        refresh, _, _ = create_refresh_token(token_data)
        return AuthResponse(
            user=UserResponse.model_validate(admin),
            access_token=access,
            refresh_token=refresh,
        )

    async def register_user(self, data: UserRegisterRequest) -> UserResponse:
        """Register an end-user account."""
        result = await self.db.execute(select(User).where(User.email == data.email))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bu email allaqachon ro'yxatdan o'tgan",
            )

        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            phone=data.phone,
            role=UserRole.USER,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return UserResponse.model_validate(user)

    async def login(self, data: LoginRequest) -> AuthResponse:
        """Authenticate user and return JWT tokens."""
        from sqlalchemy.orm import selectinload
        login_email = data.email
        if login_email == "admin":
            login_email = "admin@turify.xyz"

        result = await self.db.execute(
            select(User)
            .options(selectinload(User.company))
            .where(User.email == login_email)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email yoki parol noto'g'ri",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akkaunt faol emas yoki tasdiqlanmagan",
            )

        token_data = {"sub": str(user.id), "role": user.role.value}
        access = create_access_token(token_data)
        refresh, _, _ = create_refresh_token(token_data)

        return AuthResponse(
            user=UserResponse.model_validate(user),
            access_token=access,
            refresh_token=refresh,
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """Issue new access token from valid refresh token. Old token is blacklisted."""
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Yaroqsiz refresh token",
            )

        jti = payload.get("jti")
        if jti:
            bl_result = await self.db.execute(
                select(RefreshTokenBlacklist).where(
                    RefreshTokenBlacklist.token_jti == jti
                )
            )
            if bl_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token bekor qilingan",
                )

        user_id = payload.get("sub")
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.company))
            .where(User.id == int(user_id))
        )
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Foydalanuvchi topilmadi",
            )

        # Blacklist the old refresh token (prevent replay attacks)
        if jti:
            expires = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
            self.db.add(RefreshTokenBlacklist(token_jti=jti, expires_at=expires))

        token_data = {"sub": str(user.id), "role": user.role.value}
        access = create_access_token(token_data)
        new_refresh, _, _ = create_refresh_token(token_data)

        return TokenResponse(access_token=access, refresh_token=new_refresh)

    async def logout(self, refresh_token: str) -> dict:
        """Blacklist refresh token on logout."""
        payload = decode_token(refresh_token)
        if payload and payload.get("jti"):
            expires = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
            entry = RefreshTokenBlacklist(
                token_jti=payload["jti"],
                expires_at=expires,
            )
            self.db.add(entry)
        return {"message": "Muvaffaqiyatli chiqildi"}

    async def save_push_subscription(self, user: User, subscription: str) -> dict:
        """Store browser push subscription for user."""
        user.push_subscription = subscription
        await self.db.flush()
        return {"message": "Push obuna saqlandi"}
