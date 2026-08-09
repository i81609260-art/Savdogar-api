"""Savdogar FastAPI — CRM/POS + SAIR integratsiya."""

import asyncio
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
from app.db_schema import ensure_schema
from app.services.currency import daily_refresh_loop
from app.utils.limiter import limiter
from app.routers import (
    admin,
    auth,
    bookings,
    booking_messages,
    extension,
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
from app.routers import operators as operators_router
from app.routers import pricelists as pricelists_router
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
    # Jadvallar + keyinchalik qo'shilgan ustun/jadval yamoqlari.
    # Ro'yxatning o'zi `app/db_schema.py` da — SQLite'dan Postgres'ga
    # ko'chirish skripti ham AYNAN shu sxemadan foydalanadi.
    await ensure_schema(engine)

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
    await backfill_price_uzs()
    await seed_superadmin()

    # Kunlik kurs yangilash. `create_task` — bloklamasligi kerak, aks holda
    # ilova ishga tushishi birinchi so'rovni kutib turardi.
    rates_task = asyncio.create_task(daily_refresh_loop(recompute_all_price_uzs))

    yield

    # Yopilishda vazifani to'xtatamiz, aks holda test va qayta ishga
    # tushirishlarda "task was destroyed but it is pending" ogohlantirishi
    # chiqar va halqa fon rejimida qolib ketardi.
    rates_task.cancel()
    try:
        await rates_task
    except asyncio.CancelledError:
        pass


async def backfill_price_uzs():
    """Eski turlarga so'mdagi narxni bir marta hisoblab qo'yadi.

    `price_uzs` keyinchalik qo'shilgan ustun, shuning uchun mavjud turlarda
    u `NULL`. Saralashda ular `nulls_last` tufayli oxiriga tushardi — ya'ni
    eski turlar ro'yxat oxirida qolib ketardi.

    FAQAT `NULL` bo'lganlar yangilanadi: bu amal har startda ishlaydi va
    hammasini qayta hisoblasa, kurs har kuni o'zgargani uchun turlarning
    tartibi sababsiz o'zgarib turardi.

    Xato bo'lsa ilova ishga tushishi TO'XTAMAYDI — bu tuzatuv amali,
    mahsulotning ishlashi unga bog'liq emas.
    """
    from sqlalchemy import select as _select

    from app.database import AsyncSessionLocal
    from app.models.tour import Tour
    from app.services.currency import refresh_rates, to_uzs

    log = logging.getLogger(__name__)
    try:
        await refresh_rates()
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    _select(Tour).where(Tour.price_uzs.is_(None))
                )
            ).scalars().all()
            if not rows:
                return
            for tour in rows:
                tour.price_uzs = to_uzs(tour.price, tour.currency)
            await session.commit()
            log.info("price_uzs to'ldirildi: %s ta tur", len(rows))
    except Exception as exc:  # noqa: BLE001
        log.warning("price_uzs to'ldirilmadi: %s", exc)


async def recompute_all_price_uzs():
    """HAMMA turning so'mdagi narxini joriy kurs bo'yicha qayta hisoblaydi.

    `backfill_price_uzs` dan farqi: u faqat NULL bo'lganlarni to'ldiradi
    (bir martalik tuzatuv), bu esa hammasini yangilaydi — kurs o'zgargani
    uchun eski qiymatlar eskirgan bo'ladi.

    Model tinglovchisi (`models/tour.py`) qiymatni o'zi hisoblaydi,
    shuning uchun bu yerda faqat "tegib qo'yish" kifoya.
    """
    from sqlalchemy import select as _select

    from app.database import AsyncSessionLocal
    from app.models.tour import Tour

    log = logging.getLogger(__name__)
    async with AsyncSessionLocal() as session:
        tours = (await session.execute(_select(Tour))).scalars().all()
        for tour in tours:
            # Tinglovchi `before_update` da ishlaydi, lekin SQLAlchemy
            # o'zgarmagan obyektni yozmaydi. Shuning uchun maydonni ochiq
            # qayta hisoblaymiz.
            from app.services.currency import to_uzs

            tour.price_uzs = to_uzs(tour.price, tour.currency)
        await session.commit()
        log.info("price_uzs qayta hisoblandi: %s ta tur", len(tours))


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
    # `X-API-Key` — brauzer kengaytmasi narxni shu sarlavha bilan yuboradi.
    # Kengaytmaning o'zi `host_permissions` tufayli CORS'dan istisno, ya'ni
    # ro'yxatsiz ham ishlardi. Lekin bunday nozik bog'liqlikka tayanmaslik
    # kerak: brauzer qoidalari o'zgarsa yoki endpoint boshqa joydan
    # chaqirilsa, sababi topilishi qiyin xato bo'lardi.
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-API-Key"],
)

upload_path = settings.persistent_upload_dir
os.makedirs(upload_path, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_path), name="uploads")

app.include_router(auth.router)
app.include_router(tours.router)
app.include_router(bookings.router)
# Bron ichidagi mijoz ↔ agentlik yozishuvi.
app.include_router(booking_messages.router)
# Brauzer kengaytmasi: kalitlar va narx qabul qilish.
app.include_router(extension.router)
app.include_router(crm.router)
app.include_router(requests_router.router)
app.include_router(reports.router)
app.include_router(track_router.router)
app.include_router(assistant_router.router)
app.include_router(exports_router.router)
app.include_router(tariff_router.router)
app.include_router(branches_router.router)
app.include_router(operators_router.router)
app.include_router(pricelists_router.router)
app.include_router(pricelists_router.offers_router)
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
