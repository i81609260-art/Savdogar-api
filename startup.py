"""
Startup migration patch — runs BEFORE uvicorn.

Safely adds any missing columns to the SQLite database that may have been
introduced in code but not yet applied via Alembic (e.g. on Railway with a
persistent volume that pre-dates the migration).

Usage (Procfile):
    python startup.py && uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""

import os
import re
import sqlite3
import sys


def get_sqlite_path() -> str | None:
    """Resolve the SQLite file path from DATABASE_URL or DATA_DIR env vars."""
    database_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./savdogar.db")
    data_dir = os.environ.get("DATA_DIR", "")

    # If persistent volume is configured, use that path
    if data_dir and "sqlite" in database_url:
        return os.path.join(data_dir, "savdogar.db")

    # Strip SQLAlchemy async prefix to get raw path
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if database_url.startswith(prefix):
            path = database_url[len(prefix):]
            # Handle relative paths — resolve from CWD (repo root on Railway)
            if not os.path.isabs(path):
                path = os.path.join(os.getcwd(), path.lstrip("./"))
            return path

    return None


# ─── Column patch definitions ────────────────────────────────────────────────
# Each entry: (table_name, column_name, column_definition)
REQUIRED_COLUMNS = [
    ("companies", "logo_url",       "VARCHAR(500)"),
    ("companies", "sair_integrated","BOOLEAN DEFAULT 0"),
    ("companies", "slug",           "VARCHAR(255)"),
    ("companies", "custom_domain",  "VARCHAR(255)"),
    ("companies", "company_type",   "VARCHAR(20) DEFAULT 'multi'"),
    ("companies", "site_enabled",   "BOOLEAN DEFAULT 1"),
    ("users",     "telegram_chat_id","VARCHAR(50)"),
    ("bookings",  "group_id",       "INTEGER"),
    ("integration_configs", "sair_company_id", "VARCHAR(100)"),
    ("integration_configs", "sair_api_key",    "VARCHAR(255)"),
    ("tours",               "booking_type",    "VARCHAR(20) DEFAULT 'group'"),
    ("tours",               "currency",        "VARCHAR(10) DEFAULT 'UZS'"),
]


# ─── Table patch definitions ──────────────────────────────────────────────────
# Tables that must exist (created if missing); SQLite-compatible DDL.
REQUIRED_TABLES = [
    (
        "tour_groups",
        """CREATE TABLE IF NOT EXISTS tour_groups (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            tour_id       INTEGER NOT NULL REFERENCES tours(id),
            company_id    INTEGER NOT NULL REFERENCES companies(id),
            departure_date DATE NOT NULL,
            return_date   DATE NOT NULL,
            hotel_stars   SMALLINT,
            price         REAL NOT NULL,
            total_slots   INTEGER NOT NULL DEFAULT 50,
            booked_slots  INTEGER NOT NULL DEFAULT 0,
            notes         TEXT,
            is_active     BOOLEAN NOT NULL DEFAULT 1,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
        )""",
    ),
]


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def _column_is_not_null(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    for row in cursor.fetchall():  # (cid, name, type, notnull, dflt, pk)
        if row[1] == column:
            return bool(row[3])
    return False


def drop_not_null(conn: sqlite3.Connection, table: str, columns: list) -> bool:
    """Rebuild `table` so the given columns become nullable (SQLite has no
    ALTER COLUMN). Rebuilds from the real CREATE TABLE DDL so foreign keys,
    defaults and other columns are preserved exactly; indexes are recreated.

    Returns True if a rebuild was performed.
    """
    cur = conn.cursor()
    if not table_exists(cur, table):
        return False
    targets = [c for c in columns if _column_is_not_null(cur, table, c)]
    if not targets:
        return False  # already nullable

    cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    create_sql = cur.fetchone()[0]

    # Strip "NOT NULL" from each target column line only.
    new_sql = create_sql
    for col in targets:
        # Handles: `<col> DATE NOT NULL,`  ->  `<col> DATE,`
        pattern = re.compile(
            rf"(\b{re.escape(col)}\b[^,\n]*?)\s+NOT\s+NULL", re.IGNORECASE
        )
        new_sql = pattern.sub(r"\1", new_sql)

    tmp = f"{table}__rebuild_tmp"
    new_sql = re.sub(
        rf"CREATE\s+TABLE\s+[\"']?{re.escape(table)}[\"']?",
        f'CREATE TABLE "{tmp}"',
        new_sql,
        count=1,
        flags=re.IGNORECASE,
    )

    # Preserve index definitions to recreate after the swap.
    cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? "
        "AND sql IS NOT NULL",
        (table,),
    )
    index_sqls = [r[0] for r in cur.fetchall()]

    cur.execute(f"PRAGMA table_info({table})")
    col_names = ", ".join(f'"{r[1]}"' for r in cur.fetchall())

    cur.execute("PRAGMA foreign_keys=OFF")
    try:
        cur.execute("BEGIN")
        cur.execute(new_sql)
        cur.execute(
            f'INSERT INTO "{tmp}" ({col_names}) SELECT {col_names} FROM "{table}"'
        )
        cur.execute(f'DROP TABLE "{table}"')
        cur.execute(f'ALTER TABLE "{tmp}" RENAME TO "{table}"')
        for idx_sql in index_sqls:
            cur.execute(idx_sql)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.execute("PRAGMA foreign_keys=ON")
    return True


def patch_sqlite(db_path: str) -> None:
    print(f"[startup] Connecting to SQLite at: {db_path}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    patched = 0

    # ── Create missing tables ────────────────────────────────────────────────
    for tbl_name, ddl in REQUIRED_TABLES:
        if not table_exists(cur, tbl_name):
            try:
                cur.execute(ddl)
                conn.commit()
                print(f"[startup] ✅ Created table '{tbl_name}'")
                patched += 1
            except sqlite3.OperationalError as e:
                print(f"[startup] ⚠️  Could not create '{tbl_name}': {e}")
        else:
            print(f"[startup] ✔  Table '{tbl_name}' already exists")

    # ── Add missing columns ──────────────────────────────────────────────────
    for table, col, col_def in REQUIRED_COLUMNS:
        if not table_exists(cur, table):
            print(f"[startup] Table '{table}' does not exist yet — skipping '{col}'")
            continue
        if not column_exists(cur, table, col):
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
                conn.commit()
                print(f"[startup] ✅ Added column '{col}' to '{table}'")
                patched += 1
            except sqlite3.OperationalError as e:
                print(f"[startup] ⚠️  Could not add '{col}' to '{table}': {e}")
        else:
            print(f"[startup] ✔  Column '{col}' already exists in '{table}'")

    # ── Relax NOT NULL on optional columns ───────────────────────────────────
    try:
        if drop_not_null(conn, "tours", ["start_date", "end_date"]):
            print("[startup] ✅ tours.start_date/end_date are now nullable")
            patched += 1
        else:
            print("[startup] ✔  tours date columns already nullable")
    except Exception as e:
        print(f"[startup] ⚠️  Could not relax tours date columns: {e}")

    conn.close()
    if patched:
        print(f"[startup] Schema patch complete — {patched} change(s) applied.")
    else:
        print("[startup] Schema is up-to-date — no changes needed.")


def main() -> None:
    db_path = get_sqlite_path()
    if db_path is None:
        print(
            "[startup] DATABASE_URL is not SQLite — skipping column patch "
            "(Alembic migrations handle this for PostgreSQL)."
        )
        return

    if not os.path.exists(db_path):
        print(f"[startup] Database file not found at '{db_path}' — will be created on first run.")
        return

    patch_sqlite(db_path)


if __name__ == "__main__":
    main()
