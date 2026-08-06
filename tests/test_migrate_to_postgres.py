"""`migrate_to_postgres.py` ning sof funksiyalariga testlar.

Eng xatoga moyil joy — SQLite qiymatlarini Postgres ustun turlariga moslash.
SQLite hamma narsani int/str qilib saqlaydi, asyncpg esa turlarni qat'iy
tekshiradi: `boolean` ustunga 0 yuborilsa yoki `timestamp` ustunga matn
yuborilsa xato beradi va ko'chirish yarim yo'lda to'xtaydi.
"""

from datetime import date, datetime, timezone

import pytest

from migrate_to_postgres import _coerce, _order_tables, _parse_dt, _pg_dsn


# --------------------------------------------------------------------------
# Sana tahlili
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-08-04 19:15:00", datetime(2026, 8, 4, 19, 15, 0)),
        ("2026-08-04T19:15:00", datetime(2026, 8, 4, 19, 15, 0)),
        ("2026-08-04T19:15:00Z", datetime(2026, 8, 4, 19, 15, 0)),
        ("2026-08-04 19:15:00.123456", datetime(2026, 8, 4, 19, 15, 0, 123456)),
        # SQLite ba'zan 6 xonadan uzun mikrosoniya yozadi — kesilishi kerak
        ("2026-08-04 19:15:00.1234567", datetime(2026, 8, 4, 19, 15, 0, 123456)),
        ("2026-08-04", datetime(2026, 8, 4, 0, 0, 0)),
        ("", None),
        ("allaqanday axlat", None),
    ],
)
def test_parse_dt(raw, expected):
    assert _parse_dt(raw) == expected


# --------------------------------------------------------------------------
# Boolean — SQLite 0/1 saqlaydi
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        (0, False),
        (1, True),
        (True, True),
        (False, False),
        ("1", True),
        ("0", False),
        ("true", True),
        ("f", False),
        (None, None),
    ],
)
def test_coerce_boolean(raw, expected):
    assert _coerce(raw, "boolean") is expected


# --------------------------------------------------------------------------
# Timestamp — tabiiy va vaqt mintaqali
# --------------------------------------------------------------------------
def test_coerce_timestamp_naive():
    got = _coerce("2026-08-04 19:15:00", "timestamp without time zone")
    assert got == datetime(2026, 8, 4, 19, 15, 0)
    assert got.tzinfo is None


def test_coerce_timestamp_aware_gets_utc():
    """`timestamp with time zone` ustuni tzinfo talab qiladi."""
    got = _coerce("2026-08-04 19:15:00", "timestamp with time zone")
    assert got.tzinfo is timezone.utc


def test_coerce_date():
    assert _coerce("2026-08-04 19:15:00", "date") == date(2026, 8, 4)


# --------------------------------------------------------------------------
# Sonlar
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,pg_type,expected",
    [
        (5, "integer", 5),
        ("5", "integer", 5),
        (5.0, "integer", 5),
        (True, "integer", 1),
        ("axlat", "integer", None),
        ("2.5", "double precision", 2.5),
        (2.5, "numeric", 2.5),
        ("axlat", "double precision", None),
    ],
)
def test_coerce_numbers(raw, pg_type, expected):
    assert _coerce(raw, pg_type) == expected


# --------------------------------------------------------------------------
# Matn / enum / bayt
# --------------------------------------------------------------------------
def test_coerce_text_passthrough():
    assert _coerce("Samarqand 3 kun", "character varying") == "Samarqand 3 kun"


def test_coerce_enum_stays_string():
    """Rollar `USER-DEFINED` (enum) — matn ko'rinishida qolishi kerak."""
    assert _coerce("SUPERADMIN", "USER-DEFINED") == "SUPERADMIN"


def test_coerce_bytes_decoded():
    assert _coerce(b"O'zbekiston", "text") == "O'zbekiston"


def test_coerce_none_always_none():
    for pg_type in ("boolean", "integer", "timestamp without time zone", "text"):
        assert _coerce(None, pg_type) is None


# --------------------------------------------------------------------------
# DSN normalizatsiyasi — Railway turli ko'rinishda beradi
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "given",
    [
        "postgres://u:p@host:5432/db",
        "postgresql://u:p@host:5432/db",
        "postgresql+asyncpg://u:p@host:5432/db",
    ],
)
def test_pg_dsn_normalises(monkeypatch, given):
    monkeypatch.delenv("TARGET_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", given)
    assert _pg_dsn() == "postgresql://u:p@host:5432/db"


def test_target_url_wins_over_database_url(monkeypatch):
    """Ko'chirish paytida ilova hali SQLite'da ishlashi kerak.

    `DATABASE_URL` ni Postgres'ga o'zgartirsak Railway qayta deploy qiladi
    va ilova bo'sh bazada yangi superadmin yaratadi.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./savdogar.db")
    monkeypatch.setenv("TARGET_DATABASE_URL", "postgresql://u:p@host:5432/db")
    assert _pg_dsn() == "postgresql://u:p@host:5432/db"


def test_pg_dsn_rejects_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./savdogar.db")
    with pytest.raises(SystemExit):
        _pg_dsn()


def test_pg_dsn_rejects_empty(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    with pytest.raises(SystemExit):
        _pg_dsn()


# --------------------------------------------------------------------------
# Jadval tartibi
# --------------------------------------------------------------------------
def test_order_tables_includes_raw_sql_tables():
    """Modelda yo'q, xom SQL bilan yaratilgan jadval ham ro'yxatga tushsin."""
    names = {"users", "companies", "membership_bookings"}
    ordered = _order_tables(names)
    assert set(ordered) == names
    assert len(ordered) == len(set(ordered)), "dublikat bo'lmasin"


def test_order_tables_parent_before_child():
    """Bolalar ota-onadan keyin kelsin (FK sikli bo'lmagan joyda)."""
    ordered = _order_tables({"companies", "tours", "bookings"})
    assert ordered.index("tours") < ordered.index("bookings")
