"""Shared FastAPI dependencies re-exported for convenience."""

from app.database import get_db
from app.middleware.auth import get_current_user, get_optional_user
from app.middleware.role_guard import company_member_required, role_required

__all__ = [
    "get_db",
    "get_current_user",
    "get_optional_user",
    "role_required",
    "company_member_required",
]
