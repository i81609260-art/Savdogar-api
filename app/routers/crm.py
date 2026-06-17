"""CRM API routes."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from app.schemas.crm import CustomerResponse, CustomerCreateRequest
from app.services.crm_service import CRMService
from app.utils.pagination import PaginatedResponse

router = APIRouter(prefix="/api/crm", tags=["CRM"])


class CustomerNoteRequest(BaseModel):
    """Add note to customer booking."""

    note: str


@router.get(
    "/customers",
    response_model=PaginatedResponse[CustomerResponse],
    summary="Mijozlar ro'yxati",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR))],
)
async def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[CustomerResponse]:
    """List company customers with segments (paginated)."""
    service = CRMService(db)
    return await service.list_customers(current_user, page=page, page_size=page_size)


@router.get(
    "/customers/{customer_id}",
    response_model=CustomerResponse,
    summary="Mijoz profili",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR))],
)
async def get_customer(
    customer_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    """Get customer profile with booking history."""
    service = CRMService(db)
    return await service.get_customer(current_user, customer_id)


@router.patch(
    "/customers/{customer_id}/note",
    summary="Mijozga izoh qo'shish",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR))],
)
async def add_customer_note(
    customer_id: int,
    data: CustomerNoteRequest,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Operator adds note to latest booking."""
    service = CRMService(db)
    return await service.update_customer_note(current_user, customer_id, data.note)


@router.post(
    "/customers",
    response_model=CustomerResponse,
    summary="Yangi mijoz qo'shish (telefon orqali sotib olinganda)",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR))],
)
async def create_customer(
    data: CustomerCreateRequest,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    """Create a new manual customer with a confirmed tour booking."""
    service = CRMService(db)
    return await service.create_customer(current_user, data)
