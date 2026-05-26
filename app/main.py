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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
