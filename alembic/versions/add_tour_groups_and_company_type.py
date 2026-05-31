"""Add tour_groups table, company_type to companies, group_id to bookings

Revision ID: add_tour_groups_company_type
Revises: add_company_slug_domain
Create Date: 2026-05-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_tour_groups_company_type'
down_revision: Union[str, None] = 'add_company_slug_domain'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # tour_groups table
    op.create_table(
        "tour_groups",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tour_id", sa.Integer, sa.ForeignKey("tours.id"), nullable=False, index=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("departure_date", sa.Date, nullable=False, index=True),
        sa.Column("return_date", sa.Date, nullable=False),
        sa.Column("hotel_stars", sa.SmallInteger, nullable=True),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("total_slots", sa.Integer, nullable=False, server_default="50"),
        sa.Column("booked_slots", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # company_type enum + column
    company_type_enum = sa.Enum("multi", "single_direction", name="companytype")
    company_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "companies",
        sa.Column("company_type", company_type_enum, nullable=True, server_default="multi"),
    )

    # group_id on bookings
    op.add_column(
        "bookings",
        sa.Column("group_id", sa.Integer, sa.ForeignKey("tour_groups.id"), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_column("bookings", "group_id")
    op.drop_column("companies", "company_type")
    op.drop_table("tour_groups")
    sa.Enum(name="companytype").drop(op.get_bind(), checkfirst=True)
