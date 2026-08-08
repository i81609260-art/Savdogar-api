"""Sxema yaratish va keyinchalik qo'shilgan ustun/jadval yamog'lari.

Bu ro'yxat ilgari `main.py` lifespan ichida inline turardi. Endi alohida
modulda — chunki uni IKKI joy ishlatadi:

  1. `app.main.lifespan` — ilova har ishga tushganda;
  2. `migrate_to_postgres.py` — SQLite'dan Postgres'ga ko'chirishda, ilova
     hali Postgres'ga ulanmasidan OLDIN sxemani tayyorlash uchun.

Har bir gap **idempotent** bo'lishi shart: qayta ishga tushirilganda xato
bersa ham (masalan "ustun allaqachon bor") tashlanadi, ma'lumot yo'qolmaydi.
Bu yerda hech qachon DROP TABLE / TRUNCATE / DELETE bo'lmasin.
"""

import importlib
import logging
import pkgutil

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.database import Base

log = logging.getLogger(__name__)


def _load_all_models() -> None:
    """`app.models` ichidagi HAMMA modulni yuklaydi.

    Model moduli import qilinmasa u `Base.metadata` ga tushmaydi va
    `create_all` uni yaratmaydi. `app/models/__init__.py` esa hammasini
    sanab o'tmagan (masalan `branch`, `promo`, `review` yo'q) — ilovada ular
    tasodifan, routerlar import qilingani uchun yuklanardi. Ya'ni sxema
    yaratish import tartibiga bog'liq edi: `bookings.branch_id` FK'si
    `branches` jadvalidan oldin ko'rilsa `NoReferencedTableError` chiqadi.

    Bu yerda paketni to'liq skanerlab, bog'liqlikni butunlay yo'qotamiz.
    Yangi model fayli qo'shilsa ham avtomatik tushadi.
    """
    import app.models as models_pkg

    for info in pkgutil.iter_modules(models_pkg.__path__):
        importlib.import_module(f"{models_pkg.__name__}.{info.name}")


_load_all_models()

SCHEMA_PATCHES: list[str] = [
# Konnektor retsepti — jadval yaratilgandan keyin qo'shilgan ustun.
"ALTER TABLE tour_operators ADD COLUMN connector_config TEXT",
# Tavsiya tizimiga rozilik. Mavjud firmalarga O'CHIQ holda qo'shiladi —
# hech kim so'ralmasdan tavsiya ro'yxatiga tushib qolmasin.
#
# `DEFAULT FALSE`, `DEFAULT 0` EMAS. Postgres BOOLEAN ustunga butun sonni
# qabul qilmaydi: "column is of type boolean but default expression is of
# type integer". Xato quyidagi `try/except` da yutilardi, ustun esa mavjud
# bazada umuman qo'shilmay qolardi — sinovlar SQLite'da o'tavergani uchun
# buni faqat ishlab chiqarishda sezgan bo'lardik.
"ALTER TABLE companies ADD COLUMN recommender_enabled BOOLEAN DEFAULT FALSE NOT NULL",
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
]


async def ensure_schema(engine: AsyncEngine) -> None:
    """Jadvallarni yaratadi va yamoqlarni qo'llaydi. Idempotent.

    Har bir yamoq O'Z tranzaksiyasida bajariladi — Postgres'da muvaffaqiyatsiz
    gap tranzaksiyani bekor qiladi, umumiy tranzaksiyada bo'lsa birinchi
    to'qnashuvdan keyingi barcha yamoqlar jimgina o'tkazib yuborilardi.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    for stmt in SCHEMA_PATCHES:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(stmt))
        except Exception as exc:  # noqa: BLE001 — odatda "allaqachon bor"
            log.debug(
                "Migratsiya otkazib yuborildi: %s -> %s",
                stmt.splitlines()[0][:80],
                exc,
            )
