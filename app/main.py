"""Savdogar FastAPI — CRM/POS + SAIR integratsiya."""

import os
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.database import Base, engine
from app.utils.limiter import limiter
from app.routers import (
    admin,
    auth,
    bookings,
    crm,
    integrations,
    notifications,
    payments,
    promo,
    reports,
    superadmin,
    tours,
    upload,
    company_settings,
    requests as requests_router,
)
from app.routers import waitlist, reviews, telegram as telegram_router
from app.routers import company_public
from app.routers import chat as chat_router
from app.routers.tour_groups import public_router as tour_groups_public_router
from app.routers.tour_groups import admin_router as tour_groups_admin_router
from app.routers.company_bot import admin_router as company_bot_admin_router
from app.routers.company_bot import webhook_router as company_bot_webhook_router
from app.routers import (
    tour_creator,
    telegram_miniapp,
    analytics,
    booking_payments,
    ai_bot,
    advanced_analytics,
    localization,
    white_label,
    membership_bookings,
    guest_bookings,
)

settings = get_settings()

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
)

socket_app = socketio.ASGIApp(sio, socketio_path="")

# sid → {user_id, role, company_id} for room access control
_sid_auth: dict[str, dict] = {}

# Initialize WebSocket handlers (delayed to avoid circular imports)
from app.routers import requests_ws
requests_ws.set_socket_io(sio, _sid_auth)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables, patch missing columns, and seed superadmin on startup."""
    if settings.data_dir:
        os.makedirs(settings.data_dir, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safely add any columns/tables introduced after initial deploy
        for stmt in [
            "ALTER TABLE companies ADD COLUMN sair_integrated BOOLEAN DEFAULT 0",
            "ALTER TABLE users ADD COLUMN telegram_chat_id VARCHAR(50)",
            "ALTER TABLE users ADD COLUMN click_merchant_id VARCHAR(100)",
            "ALTER TABLE users ADD COLUMN click_merchant_key VARCHAR(100)",
            "ALTER TABLE users ADD COLUMN payme_merchant_id VARCHAR(100)",
            "ALTER TABLE users ADD COLUMN payme_api_key VARCHAR(255)",
            "ALTER TABLE companies ADD COLUMN logo_url VARCHAR(500)",
            "ALTER TABLE companies ADD COLUMN slug VARCHAR(255)",
            "ALTER TABLE companies ADD COLUMN custom_domain VARCHAR(255)",
            "ALTER TABLE companies ADD COLUMN company_type VARCHAR(20) DEFAULT 'multi'",
            "ALTER TABLE bookings ADD COLUMN phone VARCHAR(20)",
            "ALTER TABLE bookings ADD COLUMN group_id INTEGER",
            "ALTER TABLE companies ADD COLUMN company_info TEXT",
            "ALTER TABLE companies ADD COLUMN website_customization TEXT",
            "ALTER TABLE reviews ADD COLUMN company_id INTEGER REFERENCES companies(id)",
            "ALTER TABLE integration_configs ADD COLUMN sair_company_id VARCHAR(100)",
            "ALTER TABLE integration_configs ADD COLUMN sair_api_key VARCHAR(255)",
            "ALTER TABLE tours ADD COLUMN booking_type VARCHAR(20) DEFAULT 'group'",
            "ALTER TABLE tours ADD COLUMN currency VARCHAR(10) DEFAULT 'UZS'",
            """CREATE TABLE IF NOT EXISTS membership_bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan VARCHAR(50) NOT NULL,
                price VARCHAR(20) NOT NULL,
                full_name VARCHAR(255) NOT NULL,
                phone VARCHAR(50) NOT NULL,
                email VARCHAR(255),
                people_count VARCHAR(20),
                duration VARCHAR(30),
                message TEXT,
                status VARCHAR(20) NOT NULL DEFAULT 'new',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS company_telegram_bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL UNIQUE REFERENCES companies(id),
                bot_token VARCHAR(255) NOT NULL UNIQUE,
                bot_username VARCHAR(100),
                webhook_set BOOLEAN NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS tour_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id),
                lead_name VARCHAR(255) NOT NULL,
                lead_phone VARCHAR(20) NOT NULL,
                lead_email VARCHAR(255) NOT NULL,
                destination VARCHAR(100),
                group_type VARCHAR(50),
                group_size INTEGER,
                start_date VARCHAR(10),
                end_date VARCHAR(10),
                hotel_rating VARCHAR(10),
                meal_plan VARCHAR(50),
                tour_type VARCHAR(50),
                budget FLOAT,
                status VARCHAR(50) NOT NULL DEFAULT 'Yangi',
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY(company_id) REFERENCES companies(id)
            )""",
        ]:
            try:
                await conn.execute(__import__("sqlalchemy").text(stmt))
            except Exception:
                pass  # Column already exists — ignore
    await seed_superadmin()
    yield


async def seed_superadmin():
    """Create default superadmin if none exists, or update existing."""
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.user import User, UserRole
    from app.utils.security import hash_password

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.role == UserRole.SUPERADMIN)
        )
        admin = result.scalar_one_or_none()

        if admin:
            # Update existing superadmin with correct credentials
            admin.email = "admin@turify.xyz"
            admin.hashed_password = hash_password("Turify@Admin2026!")
            admin.full_name = "Turify Super Admin"
            db.add(admin)
            await db.commit()
            return

        # Create new superadmin if none exists
        admin = User(
            email="admin@turify.xyz",
            hashed_password=hash_password("admin123"),
            full_name="Turify Super Admin",
            role=UserRole.SUPERADMIN,
            is_active=True,
        )
        db.add(admin)
        await db.commit()


app = FastAPI(
    title=settings.app_name,
    description="Savdogar — CRM/POS tizimi, SAIR tur platformasi bilan API integratsiya",
    version="1.2.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

upload_path = settings.persistent_upload_dir
os.makedirs(upload_path, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_path), name="uploads")

app.include_router(auth.router)
app.include_router(tours.router)
app.include_router(bookings.router)
app.include_router(crm.router)
app.include_router(requests_router.router)
app.include_router(reports.router)
app.include_router(admin.router)
app.include_router(superadmin.router)
app.include_router(notifications.router)
app.include_router(integrations.router)
app.include_router(waitlist.router)
app.include_router(reviews.router)
app.include_router(upload.router)
app.include_router(payments.router)
app.include_router(promo.router)
app.include_router(company_settings.router)
app.include_router(telegram_router.router)
app.include_router(company_public.router)
app.include_router(chat_router.router)
app.include_router(tour_groups_public_router)
app.include_router(tour_groups_admin_router)
app.include_router(company_bot_admin_router)
app.include_router(company_bot_webhook_router)
app.include_router(tour_creator.router)
app.include_router(telegram_miniapp.router)
app.include_router(analytics.router)
app.include_router(booking_payments.router)
app.include_router(ai_bot.router)
app.include_router(advanced_analytics.router)
app.include_router(localization.router)
app.include_router(white_label.router)
app.include_router(membership_bookings.router)
app.include_router(guest_bookings.router)

app.state.sio = sio


from fastapi.responses import RedirectResponse


@app.get("/")
async def root():
    """Redirect root path to API docs."""
    return RedirectResponse(url="/docs")


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "app": settings.app_name}


@sio.event
async def connect(sid, environ, auth):
    """Validate JWT token before allowing Socket.io connection."""
    from app.utils.security import decode_token

    token = auth.get("token") if isinstance(auth, dict) else None
    if not token:
        return False

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return False

    _sid_auth[sid] = {
        "user_id": str(payload.get("sub")),
        "role": payload.get("role", ""),
        "company_id": payload.get("company_id"),
    }


@sio.event
async def disconnect(sid):
    """Clean up auth state on disconnect."""
    _sid_auth.pop(sid, None)


@sio.event
async def join_room(sid, data):
    """Join user or company room — validates that the requester owns the room."""
    user_info = _sid_auth.get(sid)
    if not user_info:
        return

    room = data.get("room")
    if not room:
        return

    if room.startswith("user_"):
        # Users can only join their own room
        if room != f"user_{user_info['user_id']}":
            return
    elif room.startswith("company_"):
        # Only staff roles can join company rooms
        if user_info["role"] not in ("admin", "superadmin", "operator"):
            return

    await sio.enter_room(sid, room)


# Mount Socket.io at /socket.io
app.mount("/socket.io", socket_app)
