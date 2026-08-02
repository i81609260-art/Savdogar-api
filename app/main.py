"""Savdogar FastAPI — CRM/POS + SAIR integratsiya."""

import logging
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
from app.routers import exports as exports_router
from app.routers import tariff as tariff_router
from app.routers import branches as branches_router
from app.routers import calls as calls_router
from app.routers import company_public
from app.routers import chat as chat_router
from app.routers.tour_groups import public_router as tour_groups_public_router
from app.routers.tour_groups import admin_router as tour_groups_admin_router
from app.routers.company_bot import admin_router as company_bot_admin_router
from app.routers.company_bot import webhook_router as company_bot_webhook_router
from app.routers.instagram import admin_router as instagram_admin_router
from app.routers.instagram import webhook_router as instagram_webhook_router
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
    track as track_router,
    assistant as assistant_router,
)

settings = get_settings()

sio = socketio.AsyncServer(
    async_mode="asgi",
    # "*" emas. Standart rejimda ([]) engineio CORS sarlavhalarini o'zi
    # qo'shmaydi — buni pastdagi CORSMiddleware bajaradi, u naqsh orqali
    # firma subdomenlarini ham taniydi. Batafsil: config.socket_cors_list.
    cors_allowed_origins=settings.socket_cors_list,
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
    if settings.secret_key_is_default and not settings.debug:
        # Kalit almashtirilmagan bo'lsa istalgan odam superadmin tokeni yasay
        # oladi. Ilovani to'xtatmaymiz (deploy sinmasin), lekin logda baland
        # ovozda ogohlantiramiz.
        logging.getLogger(__name__).critical(
            "XAVFSIZLIK: SECRET_KEY hali ham standart qiymatda! "
            "Railway -> Variables -> SECRET_KEY ga uzun tasodifiy matn qo'ying, "
            "aks holda istalgan odam soxta JWT token yasay oladi."
        )
    if settings.data_dir:
        os.makedirs(settings.data_dir, exist_ok=True)
    os.makedirs(os.path.join(settings.private_dir, "calls"), exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Safely add any columns/tables introduced after initial deploy. Each
    # statement runs in its OWN transaction — on Postgres a failed statement
    # (e.g. duplicate column) aborts the transaction, so sharing one would
    # silently skip every migration that follows the first conflict.
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
            "ALTER TABLE bookings ADD COLUMN branch_id INTEGER",
            "ALTER TABLE companies ADD COLUMN company_info TEXT",
            "ALTER TABLE companies ADD COLUMN website_customization TEXT",
            "ALTER TABLE companies ADD COLUMN site_enabled BOOLEAN DEFAULT TRUE",
            "ALTER TABLE companies ADD COLUMN tariff VARCHAR(30) DEFAULT 'boshlangich'",
            "ALTER TABLE companies ADD COLUMN paid_until TIMESTAMP",
            # OpenTour is the flagship aggregator — special free unlimited plan.
            "UPDATE companies SET tariff = 'cheksiz' WHERE slug IN ('open-tour', 'opentour')",
            "ALTER TABLE users ADD COLUMN branch_id INTEGER",
            """CREATE TABLE IF NOT EXISTS branches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id),
                name VARCHAR(255) NOT NULL,
                city VARCHAR(100) NOT NULL,
                address VARCHAR(500),
                phone VARCHAR(50),
                lat FLOAT,
                lng FLOAT,
                is_main BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )""",
            "ALTER TABLE branches ADD COLUMN lat FLOAT",
            "ALTER TABLE branches ADD COLUMN lng FLOAT",
            # Filialni kim qoshgani (audit) — qaysi firma va kim/qachon
            "ALTER TABLE branches ADD COLUMN created_by INTEGER",
            """CREATE TABLE IF NOT EXISTS tariff_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id),
                company_name VARCHAR(255) NOT NULL,
                from_tariff VARCHAR(30),
                to_tariff VARCHAR(30) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )""",
            "ALTER TABLE reviews ADD COLUMN company_id INTEGER REFERENCES companies(id)",
            "ALTER TABLE integration_configs ADD COLUMN sair_company_id VARCHAR(100)",
            "ALTER TABLE integration_configs ADD COLUMN sair_api_key VARCHAR(255)",
            "ALTER TABLE tours ADD COLUMN booking_type VARCHAR(20) DEFAULT 'group'",
            "ALTER TABLE tours ADD COLUMN currency VARCHAR(10) DEFAULT 'UZS'",
            "ALTER TABLE tours ADD COLUMN branch_id INTEGER",
            "ALTER TABLE tour_requests ADD COLUMN source VARCHAR(20) DEFAULT 'qolda'",
            "ALTER TABLE tour_requests ADD COLUMN branch_id INTEGER",
            # Dashboard metrikalari — foydalanuvchi faolligi (DAU/MAU) va tashriflar
            "ALTER TABLE users ADD COLUMN last_active_at TIMESTAMP",
            """CREATE TABLE IF NOT EXISTS site_visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER REFERENCES companies(id),
                path VARCHAR(500),
                visitor_key VARCHAR(64),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS ix_site_visits_created_at ON site_visits (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_site_visits_company_id ON site_visits (company_id)",
            # ML yordamchi oʻrgangan misollar (oʻz-oʻzini kuchaytirish)
            """CREATE TABLE IF NOT EXISTS assistant_examples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER REFERENCES companies(id),
                text VARCHAR(500) NOT NULL,
                intent VARCHAR(40) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS ix_assistant_examples_intent ON assistant_examples (intent)",
            """CREATE TABLE IF NOT EXISTS call_recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id),
                user_id INTEGER,
                request_id INTEGER,
                title VARCHAR(255),
                phone VARCHAR(50),
                file_url VARCHAR(500) NOT NULL,
                duration_sec INTEGER,
                status VARCHAR(20) DEFAULT 'kutilmoqda',
                error VARCHAR(500),
                transcript TEXT,
                summary TEXT,
                sentiment VARCHAR(20),
                score INTEGER,
                destination VARCHAR(255),
                topics VARCHAR(500),
                next_step TEXT,
                operator_notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )""",
            "ALTER TABLE call_recordings ADD COLUMN branch_id INTEGER",
            # Optional tour dates (Postgres; SQLite handled by startup.py rebuild)
            "ALTER TABLE tours ALTER COLUMN start_date DROP NOT NULL",
            "ALTER TABLE tours ALTER COLUMN end_date DROP NOT NULL",
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
            # Instagram (Meta) integratsiyasi — lead yigish
            """CREATE TABLE IF NOT EXISTS instagram_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL UNIQUE REFERENCES companies(id),
                ig_user_id VARCHAR(50) NOT NULL UNIQUE,
                ig_username VARCHAR(100),
                login_type VARCHAR(20) NOT NULL DEFAULT 'instagram',
                page_id VARCHAR(50),
                page_name VARCHAR(255),
                page_access_token VARCHAR(500) NOT NULL,
                token_expires_at TIMESTAMP,
                webhook_subscribed BOOLEAN NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS instagram_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id),
                ig_sender_id VARCHAR(50) NOT NULL,
                ig_username VARCHAR(100),
                request_id INTEGER,
                stage VARCHAR(20) NOT NULL DEFAULT 'name',
                lead_name VARCHAR(255),
                lead_phone VARCHAR(20),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )""",
            # Instagram login yoli qoshilgach — Page majburiy emas.
            "ALTER TABLE instagram_accounts ADD COLUMN login_type VARCHAR(20) DEFAULT 'instagram'",
            "ALTER TABLE instagram_accounts ADD COLUMN token_expires_at TIMESTAMP",
            "ALTER TABLE instagram_accounts ADD COLUMN webhook_events INTEGER DEFAULT 0",
            "ALTER TABLE instagram_accounts ADD COLUMN last_webhook_at TIMESTAMP",
            "ALTER TABLE instagram_accounts ALTER COLUMN page_id DROP NOT NULL",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ig_thread ON instagram_threads (company_id, ig_sender_id)",
            "CREATE INDEX IF NOT EXISTS ix_instagram_threads_sender ON instagram_threads (ig_sender_id)",
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
            async with engine.begin() as conn:
                await conn.execute(__import__("sqlalchemy").text(stmt))
        except Exception as exc:
            # Odatda "ustun allaqachon bor" — bu normal. Lekin butunlay jim
            # qolish xatoni yashirardi (masalan DROP NOT NULL otmay qolgani).
            # Shuning uchun sababni logga yozamiz.
            logging.getLogger(__name__).debug(
                "Migratsiya otkazib yuborildi: %s -> %s", stmt.split("\n")[0][:80], exc
            )
    # Eski mehmon hisoblari paroli telefon raqamidan hisoblanardi
    # (`Guest_<telefon>!`) — ya'ni raqamni bilgan odam ularga kira olardi.
    # Ularni faolsizlantiramiz: bron yozuvlari saqlanadi, lekin login yopiladi.
    try:
        async with engine.begin() as conn:
            await conn.execute(
                __import__("sqlalchemy").text(
                    "UPDATE users SET is_active = 0 "
                    "WHERE email LIKE 'guest\\_%@ucharbeksam.uz' ESCAPE '\\' "
                    "AND role = 'USER'"
                )
            )
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).debug("Eski mehmon hisoblari yangilanmadi: %s", exc)

    await migrate_call_audio_to_private()
    await seed_superadmin()
    yield


async def migrate_call_audio_to_private():
    """Eski qo'ng'iroq yozuvlarini ochiq /uploads dan maxfiy papkaga ko'chiradi.

    Ilgari yozuvlar `/uploads/calls/<uuid>.mp3` sifatida statik tarqatilardi —
    havolani bilgan istalgan odam mijoz bilan bo'lgan suhbatni yuklab olishi
    mumkin edi. Endi fayllar `private/calls/` da yotadi va faqat
    `/api/calls/audio/<fayl>` orqali, o'z firmasining xodimiga beriladi.
    """
    import shutil

    from sqlalchemy import text as sql_text

    log = logging.getLogger(__name__)
    old_dir = os.path.join(settings.persistent_upload_dir, "calls")
    new_dir = os.path.join(settings.private_dir, "calls")
    os.makedirs(new_dir, exist_ok=True)

    moved = 0
    if os.path.isdir(old_dir):
        for name in os.listdir(old_dir):
            src = os.path.join(old_dir, name)
            if not os.path.isfile(src):
                continue
            dst = os.path.join(new_dir, name)
            try:
                if os.path.exists(dst):
                    os.remove(src)
                else:
                    shutil.move(src, dst)
                moved += 1
            except OSError as exc:
                log.warning("Yozuvni ko'chirib bo'lmadi %s: %s", name, exc)

    try:
        async with engine.begin() as conn:
            await conn.execute(
                sql_text(
                    "UPDATE call_recordings "
                    "SET file_url = REPLACE(file_url, '/uploads/calls/', "
                    "'/api/calls/audio/') "
                    "WHERE file_url LIKE '/uploads/calls/%'"
                )
            )
    except Exception as exc:  # noqa: BLE001 — jadval hali bo'lmasligi mumkin
        log.debug("call_recordings file_url yangilanmadi: %s", exc)

    if moved:
        log.info("%d ta qo'ng'iroq yozuvi maxfiy papkaga ko'chirildi", moved)


async def seed_superadmin():
    """Superadmin hisobi yo'q bo'lsa yaratadi. Mavjud parolga TEGMAYDI.

    Ilgari bu funksiya har startup'da parolni qayta yozardi — ya'ni panelda
    parol almashtirilsa ham, keyingi deploy'da eskisiga qaytib, kodda turgan
    parol bilan kirish mumkin bo'lib qolardi. Endi parol faqat hisob birinchi
    marta yaratilganda o'rnatiladi.

    Parolni unutib qo'yilsa: Railway'da SUPERADMIN_PASSWORD ni yangi parolga
    qo'yib, SUPERADMIN_FORCE_RESET=true bilan bir marta deploy qiling, so'ng
    o'zgaruvchini qaytib false qiling.
    """
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
            if settings.superadmin_force_reset:
                admin.hashed_password = hash_password(settings.superadmin_password)
                admin.is_active = True
                db.add(admin)
                await db.commit()
                logging.getLogger(__name__).warning(
                    "SUPERADMIN_FORCE_RESET yoqilgan — parol qayta o'rnatildi. "
                    "Endi bu o'zgaruvchini false qiling."
                )
            return

        admin = User(
            email=settings.superadmin_email,
            hashed_password=hash_password(settings.superadmin_password),
            full_name="Super Admin",
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

# Obuna to'lovi o'tib ketgan kompaniyalarni yozuv so'rovlaridan bloklaydi.
# CORS'dan OLDIN qo'shiladi, shunda CORS tashqarida qolib 402 javobga ham
# sarlavhalarni qo'shadi.
from app.middleware.subscription_guard import SubscriptionGuardMiddleware  # noqa: E402
from app.middleware.activity import ActivityMiddleware  # noqa: E402

app.add_middleware(SubscriptionGuardMiddleware)
# Foydalanuvchi faolligini (DAU/MAU) belgilaydi — o'zi fail-open.
app.add_middleware(ActivityMiddleware)


@app.middleware("http")
async def security_headers(request, call_next):
    """Brauzer himoyasini yoqadigan standart sarlavhalar."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
    )
    if not settings.debug:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


# "*" o'rniga aniq ro'yxat + naqsh: har firmaning o'z subdomeni bo'lgani uchun
# faqat ro'yxat yetmaydi, lekin butunlay ochiq qoldirish ham xavfli edi.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
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
app.include_router(track_router.router)
app.include_router(assistant_router.router)
app.include_router(exports_router.router)
app.include_router(tariff_router.router)
app.include_router(branches_router.router)
app.include_router(calls_router.router)
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
app.include_router(instagram_admin_router)
app.include_router(instagram_webhook_router)
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
        # Xodim rollari — lekin FAQAT o'z firmasining xonasi. Ilgari rol
        # tekshirilib, firma tekshirilmagani uchun istalgan firma admini
        # raqobatchining bron/lead yangilanishlarini tinglay olardi.
        if user_info["role"] not in ("admin", "superadmin", "operator"):
            return
        if user_info["role"] != "superadmin":
            own = user_info.get("company_id")
            if own is None or room != f"company_{own}":
                return
    else:
        # Noma'lum prefiksli xonalar taqiqlanadi.
        return

    await sio.enter_room(sid, room)


# Mount Socket.io at /socket.io
app.mount("/socket.io", socket_app)
