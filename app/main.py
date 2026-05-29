"""Savdogar FastAPI — CRM/POS + SAIR integratsiya."""

import os
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import Base, engine
from app.routers import (
    admin,
    auth,
    bookings,
    crm,
    integrations,
    notifications,
    reports,
    superadmin,
    tours,
)
from app.routers import waitlist, reviews, telegram as telegram_router
from app.routers import company_public
from app.routers import chat as chat_router

settings = get_settings()

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
)

socket_app = socketio.ASGIApp(sio, socketio_path="")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables and seed superadmin on startup."""
    if settings.data_dir:
        os.makedirs(settings.data_dir, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        def repair_schema(connection):
            raw_conn = connection.connection
            cursor = raw_conn.cursor()
            
            # 1. companies.logo_url
            try:
                cursor.execute("PRAGMA table_info(companies)")
                cols = [r[1] for r in cursor.fetchall()]
                if cols and "logo_url" not in cols:
                    cursor.execute("ALTER TABLE companies ADD COLUMN logo_url VARCHAR(500)")
                    print("Programmatic schema repair: Added logo_url to companies (SQLite)")
            except Exception:
                pass
            try:
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='companies'")
                cols = [r[0] for r in cursor.fetchall()]
                if cols and "logo_url" not in cols:
                    cursor.execute("ALTER TABLE companies ADD COLUMN logo_url VARCHAR(500)")
                    print("Programmatic schema repair: Added logo_url to companies (Postgres)")
            except Exception:
                pass

            # 2. users.telegram_chat_id
            try:
                cursor.execute("PRAGMA table_info(users)")
                cols = [r[1] for r in cursor.fetchall()]
                if cols and "telegram_chat_id" not in cols:
                    cursor.execute("ALTER TABLE users ADD COLUMN telegram_chat_id VARCHAR(50)")
                    print("Programmatic schema repair: Added telegram_chat_id to users (SQLite)")
            except Exception:
                pass
            try:
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users'")
                cols = [r[0] for r in cursor.fetchall()]
                if cols and "telegram_chat_id" not in cols:
                    cursor.execute("ALTER TABLE users ADD COLUMN telegram_chat_id VARCHAR(50)")
                    print("Programmatic schema repair: Added telegram_chat_id to users (Postgres)")
            except Exception:
                pass

        try:
            await conn.run_sync(repair_schema)
        except Exception as e:
            print(f"Error during programmatic schema repair: {e}")

    await seed_superadmin()
    yield


async def seed_superadmin():
    """Create default superadmin if none exists."""
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.user import User, UserRole
    from app.utils.security import hash_password

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.role == UserRole.SUPERADMIN)
        )
        if result.scalar_one_or_none():
            return

        admin = User(
            email="admin@savdogar.uz",
            hashed_password=hash_password("SavdogarAdmin123!"),
            full_name="Savdogar Super Admin",
            role=UserRole.SUPERADMIN,
            is_active=True,
        )
        db.add(admin)
        await db.commit()


app = FastAPI(
    title=settings.app_name,
    description="Savdogar — CRM/POS tizimi, SAIR tur platformasi bilan API integratsiya",
    version="1.1.0",
    lifespan=lifespan,
)

from fastapi import Response

@app.middleware("http")
async def custom_cors_middleware(request, call_next):
    origin = request.headers.get("origin")
    if request.method == "OPTIONS":
        response = Response()
        response.headers["Access-Control-Allow-Origin"] = origin or "*"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, PATCH, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, X-Access-Token, X-Sayr-Signature"
        return response
        
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = origin or "*"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, PATCH, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, X-Access-Token, X-Sayr-Signature"
    return response

os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

app.include_router(auth.router)
app.include_router(tours.router)
app.include_router(bookings.router)
app.include_router(crm.router)
app.include_router(reports.router)
app.include_router(admin.router)
app.include_router(superadmin.router)
app.include_router(notifications.router)
app.include_router(integrations.router)
app.include_router(waitlist.router)
app.include_router(reviews.router)
app.include_router(telegram_router.router)
app.include_router(company_public.router)
app.include_router(chat_router.router)

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
    """Handle Socket.io client connection."""
    print(f"Client connected: {sid}")


@sio.event
async def disconnect(sid):
    """Handle Socket.io disconnect."""
    print(f"Client disconnected: {sid}")


@sio.event
async def join_room(sid, data):
    """Join user or company room for targeted notifications."""
    room = data.get("room")
    if room:
        await sio.enter_room(sid, room)


# Mount Socket.io at /socket.io
app.mount("/socket.io", socket_app)
