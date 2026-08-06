#!/usr/bin/env python3
"""SQLite -> Postgres ma'lumot ko'chirish (Railway uchun).

BU SKRIPT HECH QACHON MA'LUMOT O'CHIRMAYDI.
Faqat uchta amal bajaradi: CREATE (sxema), INSERT (ma'lumot), setval (ketma-ketlik).
DROP / TRUNCATE / DELETE / UPDATE umuman yozilmagan.

Manba SQLite fayli **faqat o'qish** rejimida ochiladi — ya'ni ko'chirishdan
keyin ham u to'liq saqlanib qoladi va zaxira nusxa bo'lib xizmat qiladi.

Xususiyatlari
-------------
* **Idempotent** — `ON CONFLICT DO NOTHING`. Necha marta ishga tushirsangiz
  ham dublikat yaratmaydi, borini buzmaydi. Yarim yo'lda uzilib qolsa,
  shunchaki qayta ishga tushiring.
* **FK sikliga chidamli** — `companies.owner_id -> users -> companies` va
  `branches` halqasi bor. Avval FK tekshiruvini o'chirib ko'radi (tez yo'l),
  imkoni bo'lmasa qatorlarni kechiktirib, bir necha marta qayta uradi.
* **Ketma-ketliklarni tiklaydi** — busiz Postgres keyingi INSERT'da `id=1`
  dan boshlab urinardi va mavjud yozuvlar bilan to'qnashardi.
* **Tekshiradi** — har jadval bo'yicha SQLite va Postgres qatorlarini
  solishtiradi; kamlik bo'lsa xato kodi bilan chiqadi.

Ishlatish (Railway shell yoki lokal)
-----------------------------------
    # 1) Avval nima bo'lishini ko'rish (hech nima yozmaydi)
    python migrate_to_postgres.py --dry-run

    # 2) Haqiqiy ko'chirish
    python migrate_to_postgres.py

O'zgaruvchilar:
    DATABASE_URL  — maqsad Postgres (Railway o'zi qo'yadi)
    SQLITE_PATH   — manba fayl. Bo'sh bo'lsa `$DATA_DIR/savdogar.db`,
                    u ham bo'lmasa `./savdogar.db`.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
from datetime import date, datetime, timezone
from typing import Any

import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.database import Base
from app.db_schema import ensure_schema

import app.models  # noqa: F401  — Base.metadata to'lishi uchun

# Ko'chirilmaydigan jadvallar: sxema/holat jadvallari, ma'lumot emas.
SKIP_TABLES = {"alembic_version", "sqlite_sequence"}

BATCH = 500


# --------------------------------------------------------------------------
# Yordamchilar
# --------------------------------------------------------------------------
def _resolve_sqlite_path() -> str:
    """Manba SQLite faylini topadi."""
    if os.getenv("SQLITE_PATH"):
        return os.environ["SQLITE_PATH"]
    data_dir = get_settings().data_dir
    if data_dir:
        candidate = os.path.join(data_dir, "savdogar.db")
        if os.path.exists(candidate):
            return candidate
    return "savdogar.db"


def _pg_dsn() -> str:
    """Maqsad Postgres manzilini asyncpg tushunadigan ko'rinishga keltiradi.

    Avval `TARGET_DATABASE_URL` qaraladi, keyin `DATABASE_URL`.

    Nega alohida o'zgaruvchi: ko'chirish PAYTIDA ilova hali SQLite'da
    ishlashi kerak. Agar to'g'ridan-to'g'ri `DATABASE_URL` ni Postgres'ga
    o'zgartirsak, Railway darhol qayta deploy qiladi va ilova BO'SH bazada
    ishga tushib, standart parolli yangi superadmin yaratadi — haqiqiy
    hisob ustidan tushib qoladi.

    To'g'ri tartib:
        1. TARGET_DATABASE_URL = Postgres      (ilova sezmaydi)
        2. ko'chirish
        3. DATABASE_URL = Postgres             (endi deploy xavfsiz)
    """
    url = os.getenv("TARGET_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    if not url:
        sys.exit(
            "XATO: TARGET_DATABASE_URL (yoki DATABASE_URL) o'rnatilmagan."
        )
    # Railway ba'zan `postgres://` beradi; SQLAlchemy uchun `+asyncpg` qo'shilgan
    # bo'lishi ham mumkin — asyncpg ikkalasini ham tushunmaydi.
    url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    url = url.replace("postgres://", "postgresql://", 1)
    if not url.startswith("postgresql://"):
        sys.exit(f"XATO: DATABASE_URL Postgres emas: {url.split('://')[0]}://...")
    return url


def _parse_dt(value: str) -> datetime | None:
    """SQLite matnli sanasini datetime ga o'giradi."""
    text = value.strip()
    if not text:
        return None
    text = text.replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]
    # Mikrosoniya 6 xonadan uzun bo'lsa kesamiz (SQLite ba'zan shunday yozadi).
    if "." in text:
        head, _, frac = text.partition(".")
        frac = "".join(c for c in frac if c.isdigit())[:6]
        text = f"{head}.{frac}" if frac else head
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _coerce(value: Any, pg_type: str) -> Any:
    """SQLite qiymatini Postgres ustun turiga moslaydi.

    asyncpg turlarni qat'iy tekshiradi: `boolean` ustunga 0 yuborilsa yoki
    `timestamp` ustunga matn yuborilsa xato beradi. SQLite esa bularning
    hammasini int/str qilib saqlaydi.
    """
    if value is None:
        return None

    if pg_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}

    if pg_type.startswith("timestamp"):
        dt = _parse_dt(value) if isinstance(value, str) else value
        if isinstance(dt, datetime) and pg_type.endswith("with time zone"):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt

    if pg_type == "date":
        if isinstance(value, str):
            dt = _parse_dt(value)
            return dt.date() if dt else None
        if isinstance(value, datetime):
            return value.date()
        return value if isinstance(value, date) else None

    if pg_type in {"integer", "bigint", "smallint"}:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value.strip()))
            except ValueError:
                return None
        return int(value) if isinstance(value, float) else value

    if pg_type in {"double precision", "real", "numeric"}:
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return None
        return value

    # text / varchar / json / jsonb / enum (USER-DEFINED) — matn ko'rinishida
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", "replace")
    if not isinstance(value, str):
        return str(value)
    return value


# --------------------------------------------------------------------------
# Ko'chirish
# --------------------------------------------------------------------------
async def _pg_tables(conn: asyncpg.Connection) -> dict[str, dict[str, str]]:
    """Postgres jadvallari -> {ustun: tur}."""
    rows = await conn.fetch(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """
    )
    out: dict[str, dict[str, str]] = {}
    for r in rows:
        out.setdefault(r["table_name"], {})[r["column_name"]] = r["data_type"]
    return out


def _sqlite_tables(sq: sqlite3.Connection) -> dict[str, list[str]]:
    """SQLite jadvallari -> [ustunlar]."""
    names = [
        r[0]
        for r in sq.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    out: dict[str, list[str]] = {}
    for name in names:
        cols = [r[1] for r in sq.execute(f'PRAGMA table_info("{name}")')]
        out[name] = cols
    return out


def _order_tables(names: set[str]) -> list[str]:
    """FK bog'liqligi bo'yicha tartiblaydi (imkon qadar)."""
    ordered: list[str] = []
    try:
        for table in Base.metadata.sorted_tables:
            if table.name in names:
                ordered.append(table.name)
    except Exception:  # noqa: BLE001 — sikl bo'lsa SQLAlchemy shikoyat qiladi
        ordered = []
    # Modelda yo'q, lekin xom SQL bilan yaratilgan jadvallar (masalan
    # membership_bookings) — oxiriga qo'shamiz.
    ordered += sorted(names - set(ordered))
    return ordered


async def _copy_table(
    conn: asyncpg.Connection,
    sq: sqlite3.Connection,
    table: str,
    cols: list[str],
    types: dict[str, str],
    dry_run: bool,
) -> tuple[int, list[tuple]]:
    """Bitta jadvalni ko'chiradi. -> (yozilgan, kechiktirilgan qatorlar)."""
    quoted = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
    sql = (
        f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders}) '
        f"ON CONFLICT DO NOTHING"
    )

    rows: list[tuple] = []
    for raw in sq.execute(f'SELECT {quoted} FROM "{table}"'):
        rows.append(tuple(_coerce(v, types[c]) for v, c in zip(raw, cols)))

    if dry_run or not rows:
        return len(rows), []

    written, deferred = 0, []
    for start in range(0, len(rows), BATCH):
        chunk = rows[start : start + BATCH]
        try:
            await conn.executemany(sql, chunk)
            written += len(chunk)
        except Exception:  # noqa: BLE001 — FK yoki tur xatosi; qatorma-qator
            for row in chunk:
                try:
                    await conn.execute(sql, *row)
                    written += 1
                except asyncpg.ForeignKeyViolationError:
                    deferred.append(row)
                except Exception as exc:  # noqa: BLE001
                    print(f"    ! {table}: qator o'tkazib yuborildi -> {exc}")
    return written, deferred


async def _reset_sequences(conn: asyncpg.Connection, tables: list[str]) -> None:
    """id ketma-ketliklarini eng katta id dan keyingi qiymatga qo'yadi.

    Busiz Postgres keyingi INSERT'da 1 dan boshlab urinadi va ko'chirilgan
    yozuvlar bilan to'qnashadi ("duplicate key value violates unique
    constraint") — ilova ishlamay qoladi.
    """
    for table in tables:
        seq = await conn.fetchval(
            "SELECT pg_get_serial_sequence($1, 'id')", f"public.{table}"
        )
        if not seq:
            continue
        await conn.execute(
            f'SELECT setval($1, GREATEST((SELECT COALESCE(MAX(id), 0) FROM "{table}"), 1))',
            seq,
        )


async def main() -> int:
    ap = argparse.ArgumentParser(description="SQLite -> Postgres ko'chirish")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Hech nima yozmaydi, faqat nima ko'chishini ko'rsatadi",
    )
    args = ap.parse_args()

    sqlite_path = _resolve_sqlite_path()
    if not os.path.exists(sqlite_path):
        print(f"XATO: SQLite fayli topilmadi: {sqlite_path}")
        print("SQLITE_PATH o'zgaruvchisi bilan yo'lni ko'rsating.")
        return 1

    dsn = _pg_dsn()
    size_kb = os.path.getsize(sqlite_path) / 1024
    print("=" * 68)
    print("  SQLite -> Postgres ko'chirish")
    print("=" * 68)
    print(f"  Manba  : {sqlite_path}  ({size_kb:.0f} KB)")
    print(f"  Maqsad : {dsn.split('@')[-1]}")
    if args.dry_run:
        print("  Rejim  : DRY-RUN (sxema yaratiladi, MA'LUMOT yozilmaydi)")
    print()

    # 1) Sxema — ilova ishlatadigan AYNAN o'sha kod.
    #
    # DRY-RUN'da ham bajariladi. Sabab: oldindan ko'rish maqsad jadvallarini
    # manba bilan solishtirishga tayanadi. Sxema yaratilmasa taqqoslash uchun
    # hech narsa bo'lmaydi va "0 ta jadval ko'chiriladi" degan foydasiz
    # natija chiqadi — ya'ni dry-run o'z vazifasini bajarmaydi.
    #
    # `CREATE TABLE IF NOT EXISTS` hech qanday MA'LUMOT yozmaydi va
    # idempotent, shuning uchun bu xavfsiz.
    print("[1/5] Postgres sxemasi tayyorlanmoqda...")
    engine = create_async_engine(
        dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    )
    try:
        await ensure_schema(engine)
    finally:
        await engine.dispose()
    print("      sxema tayyor" + (" (ma'lumot yozilmaydi)." if args.dry_run else "."))

    # 2) Manba va maqsadni solishtirish. SQLite FAQAT O'QISH uchun ochiladi.
    sq = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    conn = await asyncpg.connect(dsn)
    exit_code = 0
    try:
        print("[2/5] Jadvallar solishtirilmoqda...")
        src = _sqlite_tables(sq)
        dst = await _pg_tables(conn)
        shared = (set(src) & set(dst)) - SKIP_TABLES
        only_src = set(src) - set(dst) - SKIP_TABLES
        if only_src:
            print(f"      DIQQAT: Postgres'da yo'q jadvallar: {sorted(only_src)}")
            print("      (bular ko'chmaydi — modelga qo'shilmagan bo'lsa normal)")

        tables = _order_tables(shared)
        print(f"      {len(tables)} ta jadval ko'chiriladi.")

        # 3) FK tekshiruvini vaqtincha o'chirish — siklni chetlab o'tishning
        #    tez yo'li. Ruxsat bo'lmasa kechiktirish mexanizmi ishlaydi.
        fk_off = False
        if not args.dry_run:
            try:
                await conn.execute("SET session_replication_role = replica")
                fk_off = True
            except Exception:  # noqa: BLE001 — superuser emas, muammo emas
                pass
        print(
            f"[3/5] Ma'lumot ko'chirilmoqda "
            f"(FK tekshiruvi {'o‘chirildi' if fk_off else 'yoqiq — kechiktirish rejimi'})..."
        )

        deferred: list[tuple[str, list[str], list[tuple]]] = []
        for table in tables:
            cols = [c for c in src[table] if c in dst[table]]
            if not cols:
                continue
            missing = set(src[table]) - set(cols)
            written, defer = await _copy_table(
                conn, sq, table, cols, dst[table], args.dry_run
            )
            note = f"  (o'tkazilgan ustunlar: {sorted(missing)})" if missing else ""
            print(f"      {table:<28} {written:>7} qator{note}")
            if defer:
                deferred.append((table, cols, defer))

        # 4) Kechiktirilgan qatorlar (FK sikli) — o'zgarish bo'lmaguncha qaytaramiz.
        if deferred:
            print("[4/5] FK sikli tufayli kechikkan qatorlar qayta urinilmoqda...")
            for attempt in range(1, 6):
                still: list[tuple[str, list[str], list[tuple]]] = []
                progress = 0
                for table, cols, rows in deferred:
                    quoted = ", ".join(f'"{c}"' for c in cols)
                    ph = ", ".join(f"${i + 1}" for i in range(len(cols)))
                    sql = (
                        f'INSERT INTO "{table}" ({quoted}) VALUES ({ph}) '
                        f"ON CONFLICT DO NOTHING"
                    )
                    left = []
                    for row in rows:
                        try:
                            await conn.execute(sql, *row)
                            progress += 1
                        except Exception:  # noqa: BLE001
                            left.append(row)
                    if left:
                        still.append((table, cols, left))
                deferred = still
                print(f"      {attempt}-urinish: {progress} qator yozildi")
                if not deferred or progress == 0:
                    break
            for table, _cols, rows in deferred:
                print(f"      ! {table}: {len(rows)} qator ko'chmadi (FK yetishmadi)")
        else:
            print("[4/5] Kechikkan qator yo'q.")

        if fk_off:
            await conn.execute("SET session_replication_role = DEFAULT")

        # 5) Ketma-ketliklar + tekshiruv
        if not args.dry_run:
            print("[5/5] id ketma-ketliklari tiklanmoqda...")
            await _reset_sequences(conn, tables)
        else:
            print("[5/5] Tekshiruv (dry-run)...")

        print()
        print("-" * 68)
        print(f"  {'JADVAL':<28}{'SQLITE':>10}{'POSTGRES':>12}   HOLAT")
        print("-" * 68)
        for table in tables:
            n_src = sq.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            n_dst = await conn.fetchval(f'SELECT COUNT(*) FROM "{table}"')
            if n_dst >= n_src:
                status = "OK" if n_src else "-"
            else:
                status = "KAM!"
                exit_code = 2
            if n_src or n_dst:
                print(f"  {table:<28}{n_src:>10}{n_dst:>12}   {status}")
        print("-" * 68)
    finally:
        sq.close()
        await conn.close()

    print()
    if args.dry_run:
        print("DRY-RUN tugadi — bo'sh jadvallar yaratildi, ma'lumot ko'chmadi.")
        print("Yuqoridagi SQLITE ustuni — haqiqiy yurgizishda nima ko'chishi.")
    elif exit_code:
        print("TUGADI, LEKIN AYRIM JADVALLARDA QATOR KAM. Yuqoridagi 'KAM!' larni")
        print("tekshiring. SQLite fayli o'zgarmagan — xohlasangiz qayta urinasiz.")
    else:
        print("TAYYOR. Barcha ma'lumot ko'chdi.")
        print()
        print("Keyingi qadam: ilovani qayta deploy qiling. SQLite faylini")
        print("O'CHIRMANG — u zaxira nusxa bo'lib qolsin.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
