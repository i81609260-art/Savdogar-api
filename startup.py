"""
Startup migration patch — runs BEFORE uvicorn.

Safely adds any missing columns to the SQLite database that may have been
introduced in code but not yet applied via Alembic (e.g. on Railway with a
persistent volume that pre-dates the migration).

Usage (Procfile):
    python startup.py && uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""

import os
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
    ("companies", "logo_url", "VARCHAR(500)"),
    ("companies", "sair_integrated", "BOOLEAN DEFAULT 0"),
    ("users", "telegram_chat_id", "VARCHAR(50)"),
    ("integration_configs", "sair_company_id", "VARCHAR(100)"),
    ("integration_configs", "sair_api_key", "VARCHAR(255)"),
]


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def patch_sqlite(db_path: str) -> None:
    print(f"[startup] Connecting to SQLite at: {db_path}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    patched = 0
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

    conn.close()
    if patched:
        print(f"[startup] Schema patch complete — {patched} column(s) added.")
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
