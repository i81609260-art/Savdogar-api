"""Add slug and custom_domain to companies

Revision ID: add_company_slug_domain
Revises: 8687308f8457
Create Date: 2026-05-31

"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = 'add_company_slug_domain'
down_revision: Union[str, None] = '8687308f8457'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UZ_CHARS = {
    "ʻ": "", "‘": "", "’": "", "ʼ": "",
    "ə": "e", "ö": "o", "ü": "u", "ğ": "g",
}


def _slugify(name: str) -> str:
    name = name.lower()
    for k, v in _UZ_CHARS.items():
        name = name.replace(k, v)
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    name = re.sub(r"[\s-]+", "-", name).strip("-")
    return name or "company"


def upgrade() -> None:
    op.add_column("companies", sa.Column("slug", sa.String(255), nullable=True))
    op.add_column("companies", sa.Column("custom_domain", sa.String(255), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(text("SELECT id, name FROM companies")).fetchall()
    for row in rows:
        base = _slugify(row.name)
        slug = base
        counter = 2
        while conn.execute(
            text("SELECT id FROM companies WHERE slug = :s AND id != :id"),
            {"s": slug, "id": row.id},
        ).fetchone():
            slug = f"{base}-{counter}"
            counter += 1
        conn.execute(
            text("UPDATE companies SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": row.id},
        )

    op.create_index("ix_companies_slug", "companies", ["slug"], unique=True)
    op.create_index("ix_companies_custom_domain", "companies", ["custom_domain"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_companies_custom_domain", table_name="companies")
    op.drop_index("ix_companies_slug", table_name="companies")
    op.drop_column("companies", "custom_domain")
    op.drop_column("companies", "slug")
