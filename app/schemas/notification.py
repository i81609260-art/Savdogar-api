"""Notification schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    """Notification item."""

    id: int
    title: str
    message: str
    type: str
    link: Optional[str]
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
