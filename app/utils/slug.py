"""Slug generation utility for company names (Uzbek-aware)."""

import re

_UZ_CHARS = {
    "ʻ": "",  # ʻ
    "’": "",  # '
    "ʼ": "",  # ʼ
    "ə": "e",  # ə
    "\xf6": "o",  # ö
    "\xfc": "u",  # ü
    "ğ": "g",  # ğ
}


def slugify(name: str) -> str:
    """Convert a company name to a URL-safe slug."""
    name = name.lower()
    for char, replacement in _UZ_CHARS.items():
        name = name.replace(char, replacement)
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    name = re.sub(r"[\s-]+", "-", name).strip("-")
    return name or "company"


async def unique_slug(name: str, db, exclude_id: int | None = None) -> str:
    """Generate a unique slug, appending -2, -3, ... if needed.

    Falls back to a timestamp-based slug when the slug column doesn't exist yet
    (e.g. fresh SQLite deployment before startup.py patch has run).
    """
    import time
    from sqlalchemy import select, text
    from app.models.company import Company

    base = slugify(name)

    # Guard: if the slug column doesn't exist, return a safe unique value
    try:
        await db.execute(text("SELECT slug FROM companies LIMIT 1"))
    except Exception:
        return f"{base}-{int(time.time())}"

    slug = base
    counter = 2
    while True:
        q = select(Company.id).where(Company.slug == slug)
        if exclude_id is not None:
            q = q.where(Company.id != exclude_id)
        result = await db.execute(q)
        if result.scalar_one_or_none() is None:
            return slug
        slug = f"{base}-{counter}"
        counter += 1
