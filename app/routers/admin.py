"""Admin-specific API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from app.schemas.tour import TourResponse
from app.services.tour_service import TourService
from app.utils.pagination import PaginatedResponse

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get(
    "/tours",
    response_model=PaginatedResponse[TourResponse],
    summary="Kompaniya turlari",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR))],
)
async def company_tours(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[TourResponse]:
    """List tours belonging to admin's company."""
    service = TourService(db)
    return await service.list_tours(
        page=page,
        page_size=page_size,
        company_id=current_user.company_id,
        # Deleted tours are soft-deleted (is_active=False) and should not
        # linger in the admin list — only is_active tours are shown.
        active_only=True,
    )
