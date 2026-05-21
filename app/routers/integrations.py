"""SAYR integratsiya API — webhook va boshqaruv."""

from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from app.services.sayr_integration_service import SayrIntegrationService

router = APIRouter(prefix="/api/integrations/sayr", tags=["SAYR Integration"])


def _get_sio(request: Request):
    """Socket.io server from app state."""
    return getattr(request.app.state, "sio", None)


@router.post("/webhook", summary="SAYR webhook (tashqi)")
async def sayr_webhook(
    request: Request,
    x_sayr_signature: Optional[str] = Header(None, alias="X-Sayr-Signature"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    SAYR platformasidan hodisalar:
    - integration.approved / user.provisioned
    - booking.created / booking.confirmed (CRM/POS)
    - tour.sync
    """
    raw = await request.body()
    body = await request.json()
    event_type = body.get("event") or body.get("type", "unknown")
    data = body.get("data", body)

    service = SayrIntegrationService(db, _get_sio(request))
    return await service.handle_webhook(
        event_type,
        data,
        signature=x_sayr_signature,
        raw_body=raw,
    )


@router.post(
    "/connect",
    summary="SAYR bilan ulanish arizasi",
    dependencies=[Depends(role_required(UserRole.ADMIN))],
)
async def connect_sayr(
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Savdogar admin SAYR integratsiyasini so'raydi."""
    if not current_user.company_id:
        return {"detail": "Kompaniyaga biriktirilmagansiz"}
    service = SayrIntegrationService(db)
    return await service.request_sayr_integration(current_user.company_id)


@router.get(
    "/status",
    summary="Integratsiya holati",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR))],
)
async def integration_status(
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """SAYR ulanish holati va statistika."""
    if not current_user.company_id:
        return {"status": "no_company"}
    service = SayrIntegrationService(db)
    return await service.get_integration_status(current_user.company_id)


@router.get(
    "/pos-sales",
    summary="SAYR orqali sotuvlar (CRM/POS)",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR))],
)
async def pos_sales(
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> list:
    """SAYR dan kelgan sotuvlar — kim, nima sotib oldi."""
    if not current_user.company_id:
        return []
    service = SayrIntegrationService(db)
    return await service.list_pos_notifications(current_user.company_id)
