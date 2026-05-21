"""Role-based access control dependency."""

from typing import Callable, List

from fastapi import Depends, HTTPException, status

from app.middleware.auth import get_current_user
from app.models.user import User, UserRole


def role_required(*allowed_roles: UserRole) -> Callable:
    """Factory that returns a dependency enforcing allowed roles."""

    async def checker(current_user: User = Depends(get_current_user)) -> User:
        """Verify the current user has one of the allowed roles."""
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Ruxsat yo'q. Kerakli rollar: {[r.value for r in allowed_roles]}",
            )
        return current_user

    return checker


def company_member_required(
    allowed_roles: List[UserRole] | None = None,
) -> Callable:
    """Require user to belong to an approved company with specific roles."""

    roles = allowed_roles or [UserRole.ADMIN, UserRole.OPERATOR]

    async def checker(current_user: User = Depends(get_current_user)) -> User:
        """Verify company membership and role."""
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Kompaniya xodimi uchun ruxsat yo'q",
            )
        if not current_user.company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Kompaniyaga biriktirilmagansiz",
            )
        return current_user

    return checker
