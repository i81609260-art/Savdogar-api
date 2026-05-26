"""SAIR integratsiya API — webhook va boshqaruv."""

from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from app.services.sair_integration_service import SairIntegrationService

router = APIRouter(prefix="/api/integrations/sair", tags=["SAIR Integration"])


def _get_sio(request: Request):
    """Socket.io server from app state."""
    return getattr(request.app.state, "sio", None)


@router.post("/webhook", summary="SAIR webhook (tashqi)")
async def sair_webhook(
    request: Request,
    x_sair_signature: Optional[str] = Header(None, alias="X-Sayr-Signature"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    SAIR platformasidan hodisalar:
    - integration.approved / user.provisioned
    - booking.created / booking.confirmed (CRM/POS)
    - tour.sync
    """
    raw = await request.body()
    body = await request.json()
    event_type = body.get("event") or body.get("type", "unknown")
    data = body.get("data", body)

    service = SairIntegrationService(db, _get_sio(request))
    return await service.handle_webhook(
        event_type,
        data,
        signature=x_sair_signature,
        raw_body=raw,
    )


@router.post(
    "/connect",
    summary="SAIR bilan ulanish arizasi",
    dependencies=[Depends(role_required(UserRole.ADMIN))],
)
async def connect_sair(
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Savdogar admin SAIR integratsiyasini so'raydi."""
    if not current_user.company_id:
        return {"detail": "Kompaniyaga biriktirilmagansiz"}
    service = SairIntegrationService(db)
    return await service.request_sair_integration(current_user.company_id)


@router.get(
    "/status",
    summary="Integratsiya holati",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR))],
)
async def integration_status(
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """SAIR ulanish holati va statistika."""
    if not current_user.company_id:
        return {"status": "no_company"}
    service = SairIntegrationService(db)
    return await service.get_integration_status(current_user.company_id)


@router.get(
    "/pos-sales",
    summary="SAIR orqali sotuvlar (CRM/POS)",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR))],
)
async def pos_sales(
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> list:
    """SAIR dan kelgan sotuvlar — kim, nima sotib oldi."""
    if not current_user.company_id:
        return []
    service = SairIntegrationService(db)
    return await service.list_pos_notifications(current_user.company_id)
