"""WebSocket handler for real-time tour request updates."""

import json
from typing import Dict, Set

from fastapi import WebSocketException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.main import sio, _sid_auth
from app.models.request import TourRequest
from app.utils.security import decode_token


@sio.event
async def request_join_room(sid, data):
    """Join request update room."""
    user_info = _sid_auth.get(sid)
    if not user_info:
        return False

    request_id = data.get("request_id")
    if not request_id:
        return False

    room = f"request_{request_id}"

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TourRequest).where(TourRequest.id == request_id)
        )
        request = result.scalar_one_or_none()

        if not request:
            return False

        if request.company_id != user_info.get("company_id"):
            return False

    await sio.enter_room(sid, room)
    await sio.emit(
        "request_joined",
        {"request_id": request_id, "status": "joined"},
        room=room,
    )


@sio.event
async def request_leave_room(sid, data):
    """Leave request update room."""
    request_id = data.get("request_id")
    if request_id:
        room = f"request_{request_id}"
        await sio.leave_room(sid, room)


async def broadcast_request_status_update(
    request_id: int,
    company_id: int,
    new_status: str,
    updated_by_user_id: int,
):
    """Broadcast request status update to all clients in the room."""
    room = f"request_{request_id}"

    await sio.emit(
        "request_status_changed",
        {
            "request_id": request_id,
            "status": new_status,
            "updated_by": updated_by_user_id,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
        },
        room=room,
    )

    room_company = f"company_{company_id}"
    await sio.emit(
        "request_list_updated",
        {
            "request_id": request_id,
            "status": new_status,
            "action": "status_changed",
        },
        room=room_company,
    )
